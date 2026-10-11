"""Training-side reward shaping for ShopSimulator rollouts (audit-driven).

Gated by SHOP_REWARD_SHAPING (default "off" => bit-identical passthrough, so
evaluation and baseline reproduction are unaffected). The variant string is a
"+"-separated component list; legacy single tokens map onto components:

  off         passthrough
  option_gate recompose the env formula with option hits weighted w_opt
  budget      recompose with r_price recomputed against the *instruction* budget
  full        option_gate + budget

Process-level components (commit-shaping plan, commit-shaping/commit_shaping_plan.md):

  milestones  non-done trajectories get a ladder score by furthest progress:
              0 / 0.05 (opened a product page) / 0.10 (clicked an option) /
              0.15 (clicked buy now). Done trajectories are untouched.
  antiloop    subtract loop penalties from the milestone score (floor 0):
              asin re-open -0.02, repeated search term -0.02, back-to-search
              without a new candidate -0.01. Non-done only.
  efficiency  done trajectories: reward * (1 - eps*max(0, turns-15)/40).

Composition example: "milestones+antiloop+efficiency". Unknown components
raise at import (fail fast beats a silently unshaped training run).

Recomposition replicates the environment formula exactly (validated offline
against eval records):  env = (attr_hits + opt_hits + r_price) / (n_attr + n_opt + 1) * r_type
Shaping only perturbs its components:
  option_gate: (attr_hits + w_opt*opt_hits + r_price) / (n_attr + w_opt*n_opt + 1) * r_type
  budget:      r_price -> min(env r_price, 1[price <= budget * tol])   (tighten-only)

Env knobs:
  SHOP_REWARD_SHAPING        off|option_gate|budget|full|<component>+<component>...  (default off)
  SHOP_REWARD_OPTION_WEIGHT  float, option weight w_opt    (default 2.0)
  SHOP_REWARD_BUDGET_TOL     float, budget tolerance tol   (default 1.1)
  SHOP_REWARD_TABLE_DIR      dir holding the three tables  (default below)
  SHOP_REWARD_MILESTONES     4 comma floats, ladder scores (default "0,0.05,0.10,0.15")
  SHOP_REWARD_REOPEN_PENALTY         float, per asin re-open     (default 0.02)
  SHOP_REWARD_REPEAT_SEARCH_PENALTY  float, per repeated term    (default 0.02)
  SHOP_REWARD_LOOP_BACK_PENALTY      float, per looping back     (default 0.01)
  SHOP_REWARD_REOPEN_FREE    int, free re-opens per asin   (default 0 = every
                             re-open penalized, per plan table "2nd open on";
                             1 = first re-check free per plan prose)
  SHOP_REWARD_EFFICIENCY_EPS         float, decay strength       (default 0.1)
  SHOP_REWARD_EFFICIENCY_FREE_TURNS  int, free model turns       (default 15)
  SHOP_REWARD_EFFICIENCY_SPAN        int, decay normalizer       (default 40)

Tables (produced offline, see runs/reward_shaping/phase1_report.md):
  task_dims.json   task_id -> {n_attr, n_opt, goal_asin}
  task_budget.json task_id -> {budget, method}
  prices.json      asin -> deterministic price

Pure stdlib on purpose: importable in unit tests without slime/torch.
"""

from __future__ import annotations

import json
import os
import re

_TABLE_DIR_DEFAULT = "/root/autodl-tmp/runs/reward_shaping"

_COMPONENTS_KNOWN = {"option_gate", "budget", "milestones", "antiloop", "efficiency"}
_LEGACY_VARIANTS = {
    "off": (),
    "option_gate": ("option_gate",),
    "budget": ("budget",),
    "full": ("option_gate", "budget"),
}

_VARIANT = os.getenv("SHOP_REWARD_SHAPING", "off").strip().lower()
if _VARIANT in _LEGACY_VARIANTS:
    _COMPONENTS = frozenset(_LEGACY_VARIANTS[_VARIANT])
else:
    _COMPONENTS = frozenset(
        part for part in (p.strip() for p in _VARIANT.replace(",", "+").split("+")) if part
    )
    unknown = _COMPONENTS - _COMPONENTS_KNOWN
    if unknown:
        raise ValueError(f"SHOP_REWARD_SHAPING has unknown components: {sorted(unknown)}")

_OPTION_WEIGHT = float(os.getenv("SHOP_REWARD_OPTION_WEIGHT", "2.0"))
_BUDGET_TOL = float(os.getenv("SHOP_REWARD_BUDGET_TOL", "1.1"))
_TABLE_DIR = os.getenv("SHOP_REWARD_TABLE_DIR", _TABLE_DIR_DEFAULT)


def _parse_milestones(raw: str) -> tuple[float, ...]:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError(f"SHOP_REWARD_MILESTONES needs 4 comma floats, got {raw!r}")
    scores = tuple(float(p) for p in parts)
    if any(s < 0.0 for s in scores) or any(b < a for a, b in zip(scores, scores[1:])):
        raise ValueError(f"SHOP_REWARD_MILESTONES must be non-decreasing >= 0, got {scores}")
    return scores


_MILESTONE_SCORES = _parse_milestones(os.getenv("SHOP_REWARD_MILESTONES", "0,0.05,0.10,0.15"))
_PENALTY_REOPEN = float(os.getenv("SHOP_REWARD_REOPEN_PENALTY", "0.02"))
_PENALTY_REPEAT_SEARCH = float(os.getenv("SHOP_REWARD_REPEAT_SEARCH_PENALTY", "0.02"))
_PENALTY_LOOP_BACK = float(os.getenv("SHOP_REWARD_LOOP_BACK_PENALTY", "0.01"))
_REOPEN_FREE = int(os.getenv("SHOP_REWARD_REOPEN_FREE", "0"))
_EFFICIENCY_EPS = float(os.getenv("SHOP_REWARD_EFFICIENCY_EPS", "0.1"))
_EFFICIENCY_FREE_TURNS = int(os.getenv("SHOP_REWARD_EFFICIENCY_FREE_TURNS", "15"))
_EFFICIENCY_SPAN = int(os.getenv("SHOP_REWARD_EFFICIENCY_SPAN", "40"))

_CACHE: dict[str, dict] = {}


def _table(name: str) -> dict:
    """Lazy-load a json table; missing file behaves as an empty table."""
    if name not in _CACHE:
        path = os.path.join(_TABLE_DIR, name)
        try:
            with open(path) as f:
                _CACHE[name] = json.load(f)
        except OSError:
            _CACHE[name] = {}
    return _CACHE[name]


def shaping_enabled() -> bool:
    return bool(_COMPONENTS)


_ACTION_RE = re.compile(r"^\s*([A-Za-z_]+)\s*\[(.*)\]\s*$", re.DOTALL)
_CLICK_INFO = {"description", "features"}
_CLICK_PAGINATION = {"next page", "prev page", "previous page"}


def compute_process_stats(actions: list[str]) -> dict:
    """Summarize one trajectory's env-processed action sequence.

    Input: raw DSL action strings ("search[...]", "click[...]") in execution
    order. Counting is knob-independent; penalty weights live in shape_reward.
    """
    search_count = 0
    seen_terms: set[str] = set()
    repeated_search_count = 0
    asin_open_counts: dict[str, int] = {}
    option_clicks = info_clicks = pagination_clicks = 0
    buy_attempts = 0
    back_to_search_count = loop_back_count = 0
    malformed_actions = other_actions = 0
    opened_new_since_back = False

    for action in actions or []:
        match = _ACTION_RE.match(action or "")
        if not match:
            malformed_actions += 1
            continue
        verb, arg = match.group(1).lower(), match.group(2).strip()
        if verb == "search":
            search_count += 1
            term = " ".join(arg.split()).casefold()
            if term in seen_terms:
                repeated_search_count += 1
            else:
                seen_terms.add(term)
        elif verb == "click":
            target = arg.casefold()
            if target == "buy now":
                buy_attempts += 1
            elif target == "back to search":
                back_to_search_count += 1
                if not opened_new_since_back:
                    loop_back_count += 1
                opened_new_since_back = False
            elif target in _CLICK_INFO:
                info_clicks += 1
            elif target in _CLICK_PAGINATION:
                pagination_clicks += 1
            elif arg.isdigit():
                asin_open_counts[arg] = asin_open_counts.get(arg, 0) + 1
                if asin_open_counts[arg] == 1:
                    opened_new_since_back = True
            else:
                option_clicks += 1
        else:
            other_actions += 1

    product_page_opens = sum(asin_open_counts.values())
    if buy_attempts > 0:
        milestone_level = 3
    elif option_clicks > 0:
        milestone_level = 2
    elif product_page_opens > 0:
        milestone_level = 1
    else:
        milestone_level = 0
    return {
        "n_actions": len(actions or []),
        "search_count": search_count,
        "unique_search_terms": len(seen_terms),
        "repeated_search_count": repeated_search_count,
        "product_page_opens": product_page_opens,
        "unique_asins": len(asin_open_counts),
        "asin_reopens": sum(max(0, count - 1) for count in asin_open_counts.values()),
        "asin_open_counts": asin_open_counts,
        "option_clicks": option_clicks,
        "info_clicks": info_clicks,
        "pagination_clicks": pagination_clicks,
        "buy_attempts": buy_attempts,
        "back_to_search_count": back_to_search_count,
        "loop_back_count": loop_back_count,
        "malformed_actions": malformed_actions,
        "other_actions": other_actions,
        "milestone_level": milestone_level,
    }


def _recompose_done(task_id: int, env_reward: float, reward_detail: dict, purchase_asin: str | None) -> tuple[float, dict]:
    """Fix 1 (option weighting) + Fix 2 (instruction budget) on a done trajectory."""
    dims = _table("task_dims.json").get(str(task_id))
    try:
        attr_hits = float(reward_detail["num_attr_matches"])
        opt_hits = float(reward_detail["num_option_matches"])
        r_type = float(reward_detail["r_type"])
        r_price_env = float(reward_detail["r_price"])
    except (KeyError, TypeError, ValueError):
        return env_reward, {"shaping_error": "reward_detail incomplete"}
    if dims is None:
        return env_reward, {"shaping_error": "task_id not in dims table"}

    n_attr, n_opt = float(dims["n_attr"]), float(dims["n_opt"])

    # Fix 2: tighten r_price with the instruction budget (never loosens).
    r_price_eff = r_price_env
    meta: dict = {}
    if "budget" in _COMPONENTS:
        entry = _table("task_budget.json").get(str(task_id))
        price = _table("prices.json").get(purchase_asin) if purchase_asin else None
        if entry is not None and price is not None:
            budget, limit = float(entry["budget"]), float(entry["budget"]) * _BUDGET_TOL
            if price > limit:
                r_price_eff = 0.0
            meta.update({"budget": budget, "limit": limit, "price_paid": price,
                         "r_price_instr": r_price_eff})

    # Fix 1: option weighting inside the env formula.
    w_opt = _OPTION_WEIGHT if "option_gate" in _COMPONENTS else 1.0

    denom = n_attr + w_opt * n_opt + 1.0
    if denom <= 0:
        return env_reward, {"shaping_error": "bad dims"}
    shaped = (attr_hits + w_opt * opt_hits + r_price_eff) / denom * r_type

    meta.update({"shaping_variant": _VARIANT, "w_opt": w_opt})
    return shaped, meta


def shape_reward(
    task_id: int,
    env_reward: float,
    reward_detail: dict | None,
    purchase_asin: str | None,
    *,
    done: bool = True,
    process_stats: dict | None = None,
    model_turns: int | None = None,
) -> tuple[float, dict]:
    """Return (shaped_reward, meta). meta is {} when shaping did nothing."""
    if not shaping_enabled():
        return env_reward, {}

    if done:
        shaped, meta = env_reward, {}
        if _COMPONENTS & {"option_gate", "budget"}:
            if not reward_detail:
                return env_reward, {}
            shaped, meta = _recompose_done(task_id, env_reward, reward_detail, purchase_asin)
            if "shaping_error" in meta:
                return shaped, meta
        if "efficiency" in _COMPONENTS and model_turns is not None:
            over = max(0, int(model_turns) - _EFFICIENCY_FREE_TURNS)
            factor = max(0.0, 1.0 - _EFFICIENCY_EPS * over / _EFFICIENCY_SPAN)
            shaped = shaped * factor
            meta.update({"efficiency_factor": factor, "efficiency_eps": _EFFICIENCY_EPS,
                         "model_turns": int(model_turns), "shaping_variant": _VARIANT})
        return shaped, meta

    if "milestones" in _COMPONENTS and process_stats:
        level = int(process_stats.get("milestone_level", 0))
        level = min(max(level, 0), len(_MILESTONE_SCORES) - 1)
        shaped = _MILESTONE_SCORES[level]
        meta = {"shaping_variant": _VARIANT, "milestone_level": level, "milestone_score": shaped}
        if "antiloop" in _COMPONENTS:
            counts = process_stats.get("asin_open_counts") or {}
            reopen_events = sum(max(0, int(c) - 1 - _REOPEN_FREE) for c in counts.values())
            p_reopen = reopen_events * _PENALTY_REOPEN
            p_search = int(process_stats.get("repeated_search_count", 0)) * _PENALTY_REPEAT_SEARCH
            p_back = int(process_stats.get("loop_back_count", 0)) * _PENALTY_LOOP_BACK
            penalty = p_reopen + p_search + p_back
            shaped = max(0.0, shaped - penalty)
            meta.update({"antiloop_penalty": penalty, "penalty_reopen": p_reopen,
                         "penalty_repeat_search": p_search, "penalty_loop_back": p_back})
        return shaped, meta

    return env_reward, {}
