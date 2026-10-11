# T4 新 GRPO 报告（思考版，对齐 R0）

日期：2026-09-04（训练 2026-09-03 11:13 ~ 2026-09-04 00:15，约 13 小时）
RUN_ROOT：`runs/qwen35_2b_shop_rl_thinking/`（终版 `hf/rollout_99`；中期存档 24/49/74）
起点：`runs/qwen35_2b_shop_sft_thinking/`（T3 新 SFT）
配置：逐项对齐 R0——rl_500、100 rollout、n=4、lr 1e-6 constant、KL 0.001 low_var_kl、原始 env reward、shaping OFF、seed 全同。唯一差异：`SLIME_ROLLOUT_THINKING=1`

## 结论

**T4 验收通过**（100 rollout 训完、think 非空率全程保持 99%+）。终版进 T5 双集终判。

## 训练曲线（fragment 加权 raw_reward，10 轮桶，对照 R0）

| 轮段 | T4 | R0 |
|---|---|---|
| 1-10 | 0.638 | 0.420 |
| 11-20 | 0.667 | 0.489 |
| 21-30 | 0.488 | 0.501 |
| 31-40 | 0.524 | 0.477 |
| 41-50 | 0.614 | 0.549 |
| 51-60 | 0.591 | 0.701 |
| 61-70 | 0.664 | 0.702 |
| 71-80 | 0.647 | 0.604 |
| 81-90 | 0.783 | 0.814 |
| 91-100 | 0.554~0.662 | 0.645 |

起点高 R0 约 +20pt，后段两线收敛到同一水平（峰段 0.78 vs 0.81）。训练 reward 不是终判指标，判据在 T5 的 r_hard。

## 轨迹级行为（每 rollout 20 条轨迹；注意各 rollout 是不同任务子集）

| | rollout_0 | rollout_49 | rollout_99 |
|---|---|---|---|
| reward mean | 0.768 | 0.593 | 0.775 |
| env_done | 85% | 60% | 80% |
| agent_stop | 3/20 | 0 | 1/20 |
| turn_limit | 0 | 8/20 | 3/20 |
| 平均轮数 | 17.6 | 22.2 | 14.3 |

- **T3 的 agent_stop 问题（16.5%）被 RL 基本修掉**（rollout_99 仅 1/20）——RL 学会了不提前收工
- 中段（rollout_49 附近）出现过度坚持的摆荡（turn_limit 冲高），末段回落；平均轮数 17.6→14.3，购物效率提高
- think 非空率 99.1%→99.8%→99.7%，思考通道全程稳定；撞 2048 预算 ≤3 例/rollout，无挤压

## 事故记录

2026-09-03 ~10:10 首轮 T4 在 60/100 处被后台任务 16 MiB 输出上限误杀（bash trap 连带停 Ray 集群；save-interval=100 无中途存档，8.3 小时损失）。处置：输出全部重定向落盘、`run_rl.sh` 增加 `SAVE_INTERVAL` 覆盖口（本次按 25 存档，24/49/74 三份已验证可用）、旧目录留档 `runs/qwen35_2b_shop_rl_thinking_att1/`。第二轮一次通过。

## 下一步

T5：终版 `hf/rollout_99` 评 dev_200 + official_test_200（三态判据已预注册）；消融：新 SFT / base 各评 test 一次（仅归因）。
