#!/usr/bin/env python3
"""T1.5 抽查：带思考的 turn 样本在真实 tokenizer 下的渲染与 loss mask。

校验规则（沿用 T0 结论）：
- `<think>\n` 开壳 mask=0；思考正文 mask=1；`\n</think>\n\n` 闭壳 mask=1
- 正文/工具调用/`<|im_end|>` mask=1
- 历史 assistant turn 不带 reasoning_content，渲染出的 think 块为空壳且全 mask=0
- system/user/tool 全 mask=0

用法：
  python3 qc_prepared_thinking.py [--n 10] [--seed 0]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

SLIME_DIR = Path("/root/autodl-tmp/pi-slime-shopsimulator/slime")
sys.path.insert(0, str(SLIME_DIR))

from slime.utils.mask_utils import MultiTurnLossMaskGenerator  # noqa: E402
from slime.utils.processing_utils import load_tokenizer  # noqa: E402

DATA = Path("/root/autodl-tmp/runs/thinking_sft/prepared/turn_examples.jsonl")
TOKENIZER = "/root/autodl-tmp/pi-slime-work/models/Qwen3.5-2B"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rows = [json.loads(line) for line in DATA.open(encoding="utf-8")]
    thinking_rows = [r for r in rows if r["metadata"]["has_thinking"]]
    print(f"total={len(rows)} thinking={len(thinking_rows)}")
    sample = random.Random(args.seed).sample(thinking_rows, args.n)

    tokenizer = load_tokenizer(TOKENIZER, trust_remote_code=True)
    masker = MultiTurnLossMaskGenerator(tokenizer, tokenizer_type="qwen3_5")

    failures = []
    for row in sample:
        eid = row["metadata"]["example_id"]
        messages = row["messages"]
        tools = row["tools"]

        # schema: 只有目标 turn 带 reasoning_content，且只能是最后一条 assistant
        rc_idx = [i for i, m in enumerate(messages) if m.get("reasoning_content")]
        if rc_idx != [len(messages) - 1]:
            failures.append((eid, f"reasoning_content idx {rc_idx}, expected last only"))
            continue
        reasoning = messages[-1]["reasoning_content"]

        token_ids, loss_mask = masker.get_loss_mask(messages, tools=tools)
        assert len(token_ids) == len(loss_mask)

        masked_text = tokenizer.decode([t for t, m in zip(token_ids, loss_mask) if m == 1])
        full_text = tokenizer.decode(token_ids)

        checks = {
            "think_body_masked": reasoning[:60] in masked_text,
            "close_masked": "</think>" in masked_text,
            "open_not_masked": not masked_text.lstrip().startswith("<think>"),
            "im_end_masked": masked_text.rstrip().endswith("<|im_end|>"),
            "single_nonempty_think": full_text.count("<think>\n\n</think>") + 1 == full_text.count("<think>"),
        }
        # 开壳紧邻 mask=1 区之前
        first1 = loss_mask.index(1)
        prefix_text = tokenizer.decode(token_ids[:first1])
        checks["open_right_before"] = prefix_text.endswith("<|im_start|>assistant\n<think>\n")

        bad = [k for k, v in checks.items() if not v]
        status = "OK " if not bad else "FAIL"
        print(
            f"{status} {eid} tokens={len(token_ids)} target={sum(loss_mask)} "
            f"think_chars={len(reasoning)}"
            + (f" bad={bad}" if bad else "")
        )
        if bad:
            failures.append((eid, bad))

    print(f"\n{args.n - len(failures)}/{args.n} passed")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
