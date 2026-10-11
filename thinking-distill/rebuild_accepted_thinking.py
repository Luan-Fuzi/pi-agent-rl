#!/usr/bin/env python3
"""T2 离线重建：从既有 raw 轨迹导出"保留 thinking"的 accepted 数据集。

不碰 pi、不调 API。acceptance 结论直接复用 raw 文件里的既有判定
（accepted/rejection_reasons 与 thinking 保留与否无关——过滤条件只依赖
events/done/reward/context_trace_valid）。

用法：
  python3 rebuild_accepted_thinking.py \
    --input-dir /root/autodl-tmp/runs/shop_sft_512 \
    --output-dir /root/autodl-tmp/runs/thinking_sft/rebuild
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def rebuild_messages_with_thinking(candidate: dict) -> list[dict]:
    """等价于 collect_sft.authoritative_messages，但保留 thinking part。"""
    messages = []
    for event in candidate.get("events") or []:
        if event.get("type") != "message_end":
            continue
        message = event.get("message")
        if not isinstance(message, dict) or not message.get("role"):
            continue
        messages.append(json.loads(json.dumps(message, ensure_ascii=False)))
    return messages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    raw_files = sorted(
        p for p in (args.input_dir / "raw").rglob("*.json")
        if not any(part.startswith(".") for part in p.parts)
    )
    rows, skipped = [], Counter()
    think_turns = tool_turns = 0
    for path in raw_files:
        candidate = json.loads(path.read_text(encoding="utf-8"))
        if not candidate.get("accepted"):
            skipped["not_accepted"] += 1
            continue
        messages = rebuild_messages_with_thinking(candidate)
        if not messages:
            skipped["no_messages"] += 1
            continue
        # 统计：关键 turn 思考覆盖率（复核用）
        for m in messages:
            if m.get("role") != "assistant":
                continue
            parts = m.get("content") or []
            if not any(isinstance(x, dict) and x.get("type") == "toolCall" for x in parts):
                continue
            tool_turns += 1
            if any(isinstance(x, dict) and x.get("type") == "thinking" and x.get("thinking", "").strip() for x in parts):
                think_turns += 1
        rows.append({
            "messages": messages,
            "metadata": {
                "trajectory_id": candidate["trajectory_id"],
                "task_id": candidate["task_id"],
                "split": "sft",
                "reward": candidate["reward"],
                "raw_path": str(path.relative_to(args.input_dir)),
                "thinking_source": "events_default_mode",
            },
        })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "accepted_thinking.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    summary = {
        "input_files": len(raw_files),
        "accepted_rows": len(rows),
        "skipped": dict(skipped),
        "tool_turns": tool_turns,
        "think_turns": think_turns,
        "think_coverage": think_turns / tool_turns if tool_turns else 0,
    }
    (args.output_dir / "rebuild_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
