#!/usr/bin/env bash
# E3: milestones+efficiency, full rl_500 (100 rollouts / 100 steps) from the T3
# thinking SFT checkpoint. Stacks efficiency decay on the E1 winner lineage
# (plan §3 E3: "done 轨迹效率衰减，非 done 由 E1 管"). Also a clean ablation
# arm: E2 = E1+antiloop, E3 = E1+efficiency.
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export HF_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/hf/rollout_0
export REF_MODEL_PATH=/root/autodl-tmp/runs/qwen35_2b_shop_sft_thinking/checkpoints
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e3
export RL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_rl.json"
export SLIME_ROLLOUT_THINKING=1
export SHOP_REWARD_SHAPING='milestones+efficiency'
export SAVE_INTERVAL=25

# run_rl.sh 的 ray job 入口以提交时 cwd 解析 train.py；必须从 SLIME_DIR 启动
cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_rl.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e3.launcher.log 2>&1
