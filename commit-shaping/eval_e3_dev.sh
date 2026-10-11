#!/usr/bin/env bash
# E3 dev_200 eval: k=1, seed 42, thinking on, shaping structurally OFF
# (run_eval.sh does not forward SHOP_REWARD_SHAPING). Same protocol as T4 dev.
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export EVAL_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e3/hf/rollout_99
export EVAL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_eval_dev_k1.yaml"
export PROMPT_DATA=/root/autodl-tmp/runs/reward_shaping/dev_200.jsonl
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e3_dev
export SLIME_ROLLOUT_THINKING=1

cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_eval.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e3_dev.launcher.log 2>&1
