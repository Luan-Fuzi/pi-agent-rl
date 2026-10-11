#!/usr/bin/env bash
# E1: milestones shaping, full rl_500 (100 rollouts / 100 steps) from the T3
# thinking SFT checkpoint. Only variable vs T4: SHOP_REWARD_SHAPING=milestones.
# Pre-registered kill criterion: dev_200 double-axis vs T4 (done >= +3pt and
# r_hard within ±3pt); negative => stop the line (plan §0/§5).
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export HF_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/hf/rollout_0
export REF_MODEL_PATH=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/checkpoints
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e1
export RL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_rl.json"
export SLIME_ROLLOUT_THINKING=1
export SHOP_REWARD_SHAPING='milestones'
export SAVE_INTERVAL=25

# run_rl.sh 的 ray job 入口以提交时 cwd 解析 train.py；必须从 SLIME_DIR 启动
cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_rl.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e1.launcher.log 2>&1
