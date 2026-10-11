#!/usr/bin/env bash
# E2: milestones+antiloop, full rl_500 (100 rollouts / 100 steps) from the T3
# thinking SFT checkpoint. Only variable vs E1: +antiloop component.
# Same pre-registered double-axis kill criterion vs T4 dev (plan §5).
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export HF_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/hf/rollout_0
export REF_MODEL_PATH=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/checkpoints
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e2
export RL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_rl.json"
export SLIME_ROLLOUT_THINKING=1
export SHOP_REWARD_SHAPING='milestones+antiloop'
export SAVE_INTERVAL=25

# run_rl.sh 的 ray job 入口以提交时 cwd 解析 train.py；必须从 SLIME_DIR 启动
cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_rl.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e2.launcher.log 2>&1
