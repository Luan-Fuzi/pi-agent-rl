#!/usr/bin/env bash
# T6 final: champion E3 on official_test_200. k=1, seed 42, thinking on,
# shaping structurally OFF (run_eval.sh never forwards SHOP_REWARD_SHAPING).
# Same protocol as T4 test baseline (runs/qwen35_2b_shop_eval_rl_thinking_official).
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export EVAL_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e3/hf/rollout_99
export EVAL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_eval_official_k1.yaml"
export PROMPT_DATA="$SLIME_DIR/examples/ShopSimulator/data/tasks_v2/official_test_200.jsonl"
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e3_official
export SLIME_ROLLOUT_THINKING=1

cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_eval.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e3_official.launcher.log 2>&1
