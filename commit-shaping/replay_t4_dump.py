"""Offline replay of commit-shaping reward shaping on existing T4 dumps.

Parses per-candidate action sequences from turn-fragment response text,
recomputes process stats with the repo's reward_shaping module, and simulates
E1 (milestones) / E2 (+antiloop) / E3 (+efficiency) on top of the recorded
env rewards. Reports trigger rates, ladder ordering, and zero-variance group
rate changes -- the pre-registered T1f checks.

Run: python3 commit-shaping/replay_t4_dump.py [dump_dir ...]
Defaults: T4 training rollout dumps + T4 official-test eval dump.
"""

import glob
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict

import torch

MODULE = "/root/autodl-tmp/pi-slime-shopsimulator/slime/examples/ShopSimulator/reward_shaping.py"
ACTION_RE = re.compile(r"<parameter=action>\s*(.*?)\s*</parameter>", re.DOTALL)

DEFAULT_DUMPS = {
    "t4_train": "/root/autodl-tmp/runs/qwen35_2b_shop_rl_thinking/rollout_dumps",
    "t4_test_eval": "/root/autodl-tmp/runs/qwen35_2b_shop_eval_rl_thinking_official/rollout_dumps",
}


def load_module(variant):
    old = {k: os.environ.get(k) for k in ("SHOP_REWARD_SHAPING",)}
    try:
        os.environ["SHOP_REWARD_SHAPING"] = variant
        spec = importlib.util.spec_from_file_location(f"reward_shaping_replay_{variant}", MODULE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def parse_actions(response: str) -> list[str]:
    return [m.group(1).strip() for m in ACTION_RE.finditer(response or "") if m.group(1).strip()]


def load_candidates(dump_dir: str) -> list[dict]:
    """One record per candidate: env outcome + parsed action sequence."""
    candidates = {}
    for path in sorted(glob.glob(os.path.join(dump_dir, "*.pt"))):
        obj = torch.load(path, map_location="cpu", weights_only=False)
        file_rid = obj.get("rollout_id")
        for s in obj.get("samples", []):
            # training dumps: (file rollout_id, group_index, candidate rollout_id);
            # eval dumps: candidate rollout_id only (group_index None)
            cand_key = (file_rid, s.get("group_index"), s.get("rollout_id", s.get("index")))
            cand = candidates.setdefault(cand_key, {"actions": [], "fragments": 0})
            cand["fragments"] += 1
            cand["actions"].extend(parse_actions(s.get("response") or ""))
            if "meta" not in cand:
                md = s.get("metadata") or {}
                cand["meta"] = md
                cand["reward"] = float(s.get("reward") or 0.0)
                cand["remove_sample"] = bool(s.get("remove_sample"))
                cand["status"] = str(s.get("status"))
                cand["group_key"] = (file_rid, s.get("group_index")) if s.get("group_index") is not None else None
    return list(candidates.values())


def summarize(name: str, candidates: list[dict], modules: dict, out: dict) -> None:
    stats_mod = modules["off"]
    for cand in candidates:
        md = cand["meta"]
        cand["stats"] = stats_mod.compute_process_stats(cand["actions"])
        cand["done"] = bool(md.get("env_done"))
        cand["env_reward"] = float(md.get("env_reward_raw") or 0.0)
        cand["shaped"] = {}
        for label, mod in modules.items():
            if label == "off":
                continue
            shaped, _meta = mod.shape_reward(
                int(md.get("task_id") or 0),
                cand["env_reward"],
                md.get("reward_detail") if cand["done"] else None,
                md.get("purchase_asin"),
                done=cand["done"],
                process_stats=cand["stats"],
                model_turns=md.get("model_turns"),
            )
            cand["shaped"][label] = shaped

    n = len(candidates)
    done_c = [c for c in candidates if c["done"]]
    nondone_c = [c for c in candidates if not c["done"] and not c["remove_sample"]]
    print(f"\n=== {name}: {n} candidates, done {len(done_c)} ({len(done_c)/max(n,1):.1%}) ===")

    # parser sanity: actions vs pi_tool_calls (tool calls include shop_reset)
    mismatch = 0
    for cand in candidates:
        pi_calls = (cand["meta"].get("pi_tool_calls") or 0)
        if pi_calls and abs(len(cand["actions"]) - (pi_calls - 1)) > 1:
            mismatch += 1
    print(f"parser sanity: {mismatch}/{n} candidates with |actions-(pi_tool_calls-1)|>1")

    # trigger rates on non-done
    levels = Counter(c["stats"]["milestone_level"] for c in nondone_c)
    term = Counter((c["meta"].get("termination_reason") or "?") for c in nondone_c)
    print(f"non-done (kept): {len(nondone_c)}, termination {dict(term)}")
    print(f"non-done milestone levels: {dict(sorted(levels.items()))} "
          f"→ E1 触发(>0) {sum(v for k, v in levels.items() if k > 0)}/{len(nondone_c)}")
    buy = sum(1 for c in nondone_c if c["stats"]["buy_attempts"] > 0)
    reopen = sum(c["stats"]["asin_reopens"] for c in nondone_c)
    rep = sum(c["stats"]["repeated_search_count"] for c in nondone_c)
    loop = sum(c["stats"]["loop_back_count"] for c in nondone_c)
    print(f"non-done 行为: 试过 buy {buy} 条; 重开事件 {reopen}, 重复搜索 {rep}, loop back {loop}")

    # zero-variance groups (training dumps only)
    groups: dict = defaultdict(list)
    for cand in candidates:
        if cand["group_key"] is not None:
            groups[cand["group_key"]].append(cand)
    if groups:
        kept = {k: v for k, v in groups.items()
                if len(v) == 4 and not any(c["remove_sample"] for c in v)}
        zv_env = sum(1 for v in kept.values() if len({round(c["env_reward"], 9) for c in v}) == 1)
        print(f"complete groups: {len(kept)}, env 零方差: {zv_env} ({zv_env/max(len(kept),1):.1%})")
        for label in modules:
            if label == "off":
                continue
            zv = sum(1 for v in kept.values() if len({round(c["shaped"][label], 9) for c in v}) == 1)
            allzero_env = [v for v in kept.values() if all(c["env_reward"] == 0.0 for c in v)]
            fixed = sum(1 for v in allzero_env if len({round(c["shaped"][label], 9) for c in v}) > 1)
            print(f"  {label}: 零方差 {zv} ({zv/max(len(kept),1):.1%}); "
                  f"env 全零组 {len(allzero_env)} 中被拉出方差 {fixed}")
            out.setdefault("zero_variance", {})[label] = {
                "groups": len(kept), "zv": zv, "allzero_env": len(allzero_env), "allzero_fixed": fixed,
            }
        # ladder invariant: non-done shaped must stay below done rewards in-group
        for label in modules:
            if label == "off":
                continue
            viol = 0
            for v in kept.values():
                done_r = [c["shaped"][label] for c in v if c["done"]]
                nd_r = [c["shaped"][label] for c in v if not c["done"]]
                if done_r and nd_r and max(nd_r) >= min(done_r):
                    viol += 1
            print(f"  {label}: 组内非 done ≥ done 的组数 {viol}/{len(kept)}（里程碑不压过成交，应为 0 或极少）")

    # efficiency effect on done
    if "E3" in modules:
        factors = []
        for c in done_c:
            turns = c["meta"].get("model_turns")
            if c["env_reward"] > 0 and turns:
                factors.append(c["shaped"]["E3"] / c["env_reward"])
        if factors:
            print(f"E3 done 轨迹效率因子: mean {sum(factors)/len(factors):.4f}, min {min(factors):.4f}, "
                  f"n={len(factors)}")

    out[name] = {
        "candidates": n,
        "done": len(done_c),
        "nondone_milestone_levels": dict(levels),
    }


def main():
    dump_dirs = sys.argv[1:] or None
    modules = {
        "off": load_module("off"),
        "E1": load_module("milestones"),
        "E2": load_module("milestones+antiloop"),
        "E3": load_module("milestones+antiloop+efficiency"),
    }
    out = {}
    if dump_dirs:
        for d in dump_dirs:
            summarize(os.path.basename(d.rstrip("/")), load_candidates(d), modules, out)
    else:
        for name, d in DEFAULT_DUMPS.items():
            summarize(name, load_candidates(d), modules, out)
    result_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay_t4_result.json")
    with open(result_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果写入 {result_path}")


if __name__ == "__main__":
    main()
