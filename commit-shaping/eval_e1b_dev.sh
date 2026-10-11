#!/usr/bin/env bash
# E1b dev_200 eval: k=1, seed 42, NON-thinking (SLIME_ROLLOUT_THINKING
# deliberately not exported), shaping structurally OFF (run_eval.sh does not
# forward SHOP_REWARD_SHAPING). Attribution arm: same protocol as E1 dev eval
# (eval_e1_dev.sh) except thinking off, and vs the R2 non-thinking baseline.
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export EVAL_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e1b/hf/rollout_99
export EVAL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_eval_dev_k1.yaml"
export PROMPT_DATA=/root/autodl-tmp/runs/reward_shaping/dev_200.jsonl
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e1b_dev

cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_eval.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e1b_dev.launcher.log 2>&1
