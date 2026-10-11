#!/usr/bin/env bash
# k=3 retest of the T4 baseline on official_test_200 (pre-registered 2026-09-06).
# Identical protocol to eval_e3_official_k3.sh; only the checkpoint differs
# (T4 = runs/qwen35_2b_shop_rl_thinking/hf/rollout_99, same model the k=1
# official baseline runs/qwen35_2b_shop_eval_rl_thinking_official used).
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export EVAL_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_thinking/hf/rollout_99
export EVAL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_eval_official_k3.yaml"
export PROMPT_DATA="$SLIME_DIR/examples/ShopSimulator/data/tasks_v2/official_test_200.jsonl"
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_eval_rl_thinking_official_k3
export SLIME_ROLLOUT_THINKING=1

cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_eval.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_eval_rl_thinking_official_k3.launcher.log 2>&1
