#!/usr/bin/env bash
# E0 smoke: 4 rollouts from the T3 thinking SFT checkpoint with ALL shaping
# components on. Verify process stats + shaped rewards land in metadata, then
# delete the whole RUN_ROOT (disk discipline).
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export HF_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/hf/rollout_0
export REF_MODEL_PATH=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/checkpoints
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e0_smoke
export RL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_rl_smoke.json"
export SLIME_ROLLOUT_THINKING=1
export SHOP_REWARD_SHAPING='milestones+antiloop+efficiency'
export SLIME_SWANLAB_SYNC=0

# run_rl.sh 的 ray job 入口以提交时 cwd 解析 train.py；必须从 SLIME_DIR 启动
cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_rl.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e0_smoke.launcher.log 2>&1
