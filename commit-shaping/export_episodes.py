#!/usr/bin/env python3
"""Export representative episodes from the k=3 official-test dumps to JSONL
transcripts readable without torch (for report / resume case studies).

Dump structure (verified 2026-09-06): each sample is one TURN fragment;
fragments of one episode share (task_id, rollout_id) and appear in turn order
in the samples list. The fragment `prompt` is the static instruction (context
lives in the pi session, not in the dump), so the recoverable transcript is
the per-turn model outputs (thinking + tool call) in list order, plus
metadata.action_sequence (tool calls with args) as the interaction skeleton.

Categories (E3 arm unless noted):
- hard_paired: tasks where all 3 E3 samples scored 0; one E3 episode AND one
  T4 episode of the same task (paired case study of the stubborn 14).
- turn_limit / agent_stop: E3 failure exemplars.
- success: E3 perfect-score episodes (all four official sub-scores == 1,
  same definition as common.py r_success), shortest first.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import torch

E3_DUMP = "/root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e3_official_k3/rollout_dumps/rollout_eval_0.pt"
T4_DUMP = "/root/autodl-tmp/runs/qwen35_2b_shop_eval_rl_thinking_official_k3/rollout_dumps/rollout_eval_0.pt"
OUT_DIR = Path("/root/autodl-tmp/handoff_pack/transcripts")

SUB_SCORES = ("r_type", "r_att", "r_option", "r_price")
N_TURN_LIMIT = 6
N_SUCCESS = 10


def load_episodes(dump_path: str) -> dict:
    payload = torch.load(dump_path, map_location="cpu", weights_only=False)
    episodes = defaultdict(list)
    for position, sample in enumerate(payload["samples"]):
        md = sample.get("metadata") or {}
        key = (md.get("task_id"), sample.get("rollout_id", sample.get("index")))
        episodes[key].append((position, sample))
    return {key: [s for _, s in sorted(frags)] for key, frags in episodes.items()}


def episode_record(category: str, arm: str, key: tuple, fragments: list) -> dict:
    md = fragments[-1].get("metadata") or {}
    instruction = (fragments[0].get("prompt") or [{}])[0].get("content", "")
    messages = [{"role": "user", "content": instruction}]
    for turn, fragment in enumerate(fragments, start=1):
        messages.append({"role": "assistant", "turn": turn,
                         "content": fragment.get("response") or ""})
    return {
        "category": category,
        "arm": arm,
        "task_id": key[0],
        "rollout_id": key[1],
        "done": bool(md.get("env_done")),
        "reward": float(fragments[-1].get("reward", 0.0) or 0.0),
        "reward_detail": md.get("reward_detail") or {},
        "model_turns": md.get("model_turns"),
        "termination_reason": md.get("termination_reason"),
        "goal_asin": md.get("goal_asin"),
        "purchase_asin": md.get("purchase_asin"),
        "action_sequence": md.get("action_sequence"),
        "process_stats": md.get("process_stats"),
        "messages": messages,
    }


def is_perfect(fragments: list) -> bool:
    md = fragments[-1].get("metadata") or {}
    detail = md.get("reward_detail") or {}
    return bool(md.get("env_done")) and bool(detail) and all(
        float(detail.get(name, 0.0)) == 1.0 for name in SUB_SCORES
    )


def main() -> None:
    e3 = load_episodes(E3_DUMP)
    t4 = load_episodes(T4_DUMP)
    print(f"episodes: e3={len(e3)} t4={len(t4)}", file=sys.stderr)

    by_task = defaultdict(list)
    for key, frags in e3.items():
        by_task[key[0]].append((key, frags))
    hard_tasks = sorted(
        task_id for task_id, eps in by_task.items()
        if all(float(frags[-1].get("reward", 0.0) or 0.0) == 0.0 for _, frags in eps)
    )

    records = []
    for task_id in hard_tasks:
        e3_eps = sorted(by_task[task_id], key=lambda item: str(item[0][1]))
        records.append(episode_record("hard_paired", "e3", *e3_eps[0]))
        t4_eps = sorted(
            [(key, frags) for key, frags in t4.items() if key[0] == task_id],
            key=lambda item: str(item[0][1]),
        )
        if t4_eps:
            records.append(episode_record("hard_paired", "t4", *t4_eps[0]))

    def pick(reason: str, limit: int) -> list:
        chosen = []
        for key, frags in sorted(e3.items(), key=lambda item: str(item[0])):
            md = frags[-1].get("metadata") or {}
            if md.get("termination_reason") == reason:
                chosen.append(episode_record(reason, "e3", key, frags))
                if len(chosen) >= limit:
                    break
        return chosen

    records += pick("turn_limit", N_TURN_LIMIT)
    records += pick("agent_stop", 99)

    successes = sorted(
        ((frags[-1].get("metadata") or {}).get("model_turns") or 999, key, frags)
        for key, frags in e3.items() if is_perfect(frags)
    )
    records += [episode_record("success", "e3", key, frags)
                for _, key, frags in successes[:N_SUCCESS]]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "e3_official_k3_episodes.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts = defaultdict(int)
    for record in records:
        counts[f"{record['category']}:{record['arm']}"] += 1
    print(f"wrote {len(records)} episodes -> {out_path}", file=sys.stderr)
    print(json.dumps(dict(sorted(counts.items())), ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
