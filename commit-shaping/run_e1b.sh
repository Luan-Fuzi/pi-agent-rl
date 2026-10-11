#!/usr/bin/env bash
# E1b: no-thinking attribution arm. milestones-only shaping, full rl_500
# (100 rollouts / 100 steps) from the OLD non-thinking SFT checkpoint
# (runs/qwen35_2b_shop_sft, not the thinking SFT). SLIME_ROLLOUT_THINKING is
# deliberately NOT exported (adapters/common.py defaults it to off).
# Differences vs E1: (1) non-thinking SFT start, (2) thinking off. Shaping and
# everything else identical => isolates "shaping vs thinking-switch" attribution.
# Launched only after the k=3 retests free the GPU.
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export HF_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_sft/hf/rollout_0
export REF_MODEL_PATH=/root/autodl-tmp/runs/qwen35_2b_shop_sft/checkpoints
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e1b
export RL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_rl.json"
export SHOP_REWARD_SHAPING='milestones'
export SAVE_INTERVAL=25

# run_rl.sh 的 ray job 入口以提交时 cwd 解析 train.py；必须从 SLIME_DIR 启动
cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_rl.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e1b.launcher.log 2>&1
