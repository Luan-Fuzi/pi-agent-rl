# T3 新 SFT 报告（带思考蒸馏）

日期：2026-09-03
RUN_ROOT：`runs/qwen35_2b_shop_sft_thinking/`（HF 导出 `hf/rollout_0`，Megatron `checkpoints/`）
数据：`runs/thinking_sft/prepared/turn_examples_thinking_6357.jsonl`（与旧 SFT 同一批 6357 个 turn 样本，6164 条带思考）
快评：`runs/qwen35_2b_shop_eval_sft_thinking_dev/`（dev_200，k=1，`SLIME_ROLLOUT_THINKING=1`，其余口径与历史一致）

## 结论

**验收通过，进 T4。** 训练收敛；快评 done 率 77.5%（≥70%）、think 非空率 99.2%（>90%）；冒烟实证模型"先思考再行动"、思考自闭合、工具调用格式完好。

## 训练

- 2119 步（6357 样本 × 1 pass，GBS=3），全程 ~40 分钟
- loss 1.34 → 后期在 0.3~0.7 波动（逐步噪声来自动态 batch 组成），趋势正常下降
- 配置与旧 SFT 完全一致（同超参、同优化器、同 seed），唯一差异是数据带 `reasoning_content`

## dev_200 快评（对照 R2 RL 后基线仅作参考，SFT 直接比 RL 不公平）

| 指标 | 新 SFT（思考） | R2（RL 后，参考） |
|---|---|---|
| done_rate | 0.775 | 0.94 |
| r_hard | 0.572 | 0.613 |
| r_option | 0.573 | 0.623 |
| r_success | 0.535 | 0.56 |
| right_product | 0.695 | 0.78 |

终止原因：environment_done 155 / **agent_stop 33** / turn_limit 12。R2 dev 没有 agent_stop——新模型会在环境未判完成时自己收工（33/200=16.5%），疑似思考带来"过早自信"。T4 重点观察 RL 是否纠正此行为。

## 思考行为实测（4105 个模型 turn）

- 非空闭合率 **99.2%**（4073/4105）；空闭合 0；未闭合 32（全部撞 2048 上限）
- 思考长度（字符）：p10=67，中位=346，p90=1699，max=7786（教师中位 295，同量级）
- response token：mean 280 / p95 973 / max 2048；撞 2048 预算 33 例（0.8%）——思考挤压响应预算的风险实测很低
- 独立冒烟（直 curl adapter）：`reasoning_content` 正常返回，内容为约束列举式任务理解；pi 链路无会话文件落盘（`--no-session`），思考经 wire `reasoning_content` 流转，历史不回传

## 风险登记更新

- "2B 学成伪思考（复读指令）"：抽查未见复读；思考多为任务理解+动作宣告混合，约束核对浓度需 RL 后归因阶段细看
- agent_stop 16.5% 是新增观察项，T4 监控

## 下一步

T4：从 `runs/qwen35_2b_shop_sft_thinking/` 起跑 GRPO，逐项对齐 R0（rl_500、100 rollout、原始 env reward、shaping OFF），`SLIME_ROLLOUT_THINKING=1`。
