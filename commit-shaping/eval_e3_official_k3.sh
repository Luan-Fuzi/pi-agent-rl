#!/usr/bin/env bash
# k=3 retest of champion E3 on official_test_200 (pre-registered 2026-09-06):
# - n_samples_per_eval_prompt=3, same rollout-seed 42, temperature 1.0, thinking on,
#   shaping structurally OFF (run_eval.sh never forwards SHOP_REWARD_SHAPING).
# - Aggregation: official_metrics over all 600 episodes; constant k=3 makes the
#   all-episode mean identical to the per-task mean, so numbers are directly
#   comparable to the k=1 T6 run. Judgment band unchanged (±3pt noise on
#   done / r_hard vs the T4 k=3 arm).
# - Question: does E3's done +2.0pt / r_hard -0.6pt vs T4 survive 3x sampling?
set -euo pipefail

source /root/autodl-tmp/pi-slime-env.sh

export EVAL_CHECKPOINT=/root/autodl-tmp/runs/qwen35_2b_shop_rl_commit_e3/hf/rollout_99
export EVAL_CONFIG="$SLIME_DIR/examples/ShopSimulator/config/shop_eval_official_k3.yaml"
export PROMPT_DATA="$SLIME_DIR/examples/ShopSimulator/data/tasks_v2/official_test_200.jsonl"
export RUN_ROOT=/root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e3_official_k3
export SLIME_ROLLOUT_THINKING=1

cd "$SLIME_DIR"

exec bash "$SLIME_DIR/examples/ShopSimulator/run_eval.sh" \
  > /root/autodl-tmp/runs/qwen35_2b_shop_eval_commit_e3_official_k3.launcher.log 2>&1
