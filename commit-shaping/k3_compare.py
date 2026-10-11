#!/usr/bin/env python3
"""Paired k=3 comparison of E3 vs T4 on official_test_200.

Pre-registered analysis (2026-09-06): per-task means over the k=3 samples,
paired E3-minus-T4 diffs across the same 200 task_ids, bootstrap 95% CI
(resample tasks with replacement, 10k iterations, seed 0). Headline axes:
done, r_hard; the rest are supplementary. Judgment band unchanged from the
plan: |diff| <= 3pt counts as noise.

Usage:
  $SLIME_PYTHON commit-shaping/k3_compare.py \
    --e3 runs/qwen35_2b_shop_eval_commit_e3_official_k3 \
    --t4 runs/qwen35_2b_shop_eval_rl_thinking_official_k3
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "slime"))
from examples.ShopSimulator.common import _candidate_outcome  # noqa: E402

AXES = ("done", "r_hard", "r_loose", "r_success", "right_product")


def load_records(run_root: Path) -> list[dict]:
    payload = json.loads((run_root / "eval_results.json").read_text(encoding="utf-8"))
    return payload["records"]


def per_task_means(records: list[dict]) -> dict:
    by_task = defaultdict(list)
    for row in records:
        by_task[row["task_id"]].append(_candidate_outcome(row))
    return {
        task_id: {axis: sum(o[axis] for o in outcomes) / len(outcomes) for axis in AXES}
        for task_id, outcomes in by_task.items()
    }


def done_model_turns(records: list[dict]) -> float | None:
    turns = [row["model_turns"] for row in records if row.get("done") and row.get("model_turns")]
    return round(sum(turns) / len(turns), 4) if turns else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--e3", type=Path, required=True)
    parser.add_argument("--t4", type=Path, required=True)
    parser.add_argument("--boots", type=int, default=10000)
    args = parser.parse_args()

    e3_records, t4_records = load_records(args.e3), load_records(args.t4)
    e3, t4 = per_task_means(e3_records), per_task_means(t4_records)
    common = sorted(set(e3) & set(t4))
    if len(common) != len(e3) or len(common) != len(t4):
        print(f"WARNING: task_id mismatch: e3={len(e3)} t4={len(t4)} common={len(common)}",
              file=sys.stderr)

    rng = random.Random(0)
    report: dict = {"tasks": len(common), "axes": {}}
    for axis in AXES:
        diffs = [e3[t][axis] - t4[t][axis] for t in common]
        mean_diff = sum(diffs) / len(diffs)
        boots = sorted(
            sum(diffs[rng.randrange(len(diffs))] for _ in range(len(diffs))) / len(diffs)
            for _ in range(args.boots)
        )
        wins = sum(1 for d in diffs if d > 0)
        losses = sum(1 for d in diffs if d < 0)
        report["axes"][axis] = {
            "e3_mean": round(sum(e3[t][axis] for t in common) / len(common), 6),
            "t4_mean": round(sum(t4[t][axis] for t in common) / len(common), 6),
            "mean_diff": round(mean_diff, 6),
            "boot_ci95": [round(boots[int(0.025 * args.boots)], 6),
                          round(boots[int(0.975 * args.boots)], 6)],
            "tasks_win": wins,
            "tasks_loss": losses,
            "tasks_tie": len(diffs) - wins - losses,
        }

    e3_turns, t4_turns = done_model_turns(e3_records), done_model_turns(t4_records)
    report["done_model_turns"] = {
        "e3": e3_turns, "t4": t4_turns,
        "diff": round(e3_turns - t4_turns, 4) if e3_turns and t4_turns else None,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
