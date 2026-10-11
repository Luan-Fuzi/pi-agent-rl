# Thinking 蒸馏终稿报告：默认档思考捕获 → 新 SFT → GRPO

日期：2026-09-04
主线模型：`runs/qwen35_2b_shop_rl_thinking/hf/rollout_99`（T3 新 SFT → T4 GRPO，全程思考通道启用）
判据与实验设计：`thinking-distill/thinking_distill_plan.md`（v2，判据预注册于评测之前）

## 0. 结论

**正结果，假设成立。** 按预注册三态判据（2026-09-03 钉死，评测前写入计划）：dev_200 与 official_test_200 的 r_hard 分别相对 R2 基线提升 **+4.9pt** 与 **+6.6pt**，双双超过 +3pt（k=1 噪声）阈值。

> 2B 模型学不会"下单前约束核对"的根因是思考通道从未启用。给足位置正确、风格统一、覆盖率拉满的思考示范并配套 rollout 开关后，r_option / r_hard / r_success 显著上升——与假设一致。

代价同样明确：done 率下降（turn_limit 打转增多），r_loose 等含部分分的均值指标被拉低。"精度换数量"，净效果为正。

## 1. 主线数字（T4 终版 vs R2，k=1、同口径、同 seed）

| 指标 | dev：T4 / R2 | Δ | test：T4 / R2 | Δ |
|---|---|---|---|---|
| **r_hard（判据）** | 0.662 / 0.613 | **+4.9pt** | 0.385 / 0.319 | **+6.6pt** |
| **r_option（假设靶点）** | 0.666 / 0.623 | **+4.3pt** | 0.414 / 0.355 | **+5.9pt** |
| r_success | 0.635 / 0.560 | +7.5pt | 0.340 / 0.290 | +5.0pt |
| r_loose | 0.782 / 0.806 | -2.4pt | 0.567 / 0.609 | -4.2pt |
| r_att | 0.804 / 0.841 | -3.6pt | 0.593 / 0.644 | -5.1pt |
| r_price | 0.845 / 0.900 | -5.5pt | 0.680 / 0.770 | -9.0pt |
| r_type | 0.875 / 0.940 | -6.5pt | 0.750 / 0.855 | -10.5pt |
| right_product | 0.755 / 0.780 | -2.5pt | 0.420 / 0.400 | +2.0pt |
| done_rate | 0.875 / 0.940 | -6.5pt | 0.750 / 0.855 | -10.5pt |

## 2. dev_200 五方对比

| run | 路线 | r_hard | r_option | r_success | done |
|---|---|---|---|---|---|
| R0 | 旧 SFT + GRPO | 0.631 | 0.638 | 0.605 | 0.915 |
| R1 | R0 + reward shaping v1 | 0.642 | 0.661 | 0.605 | 0.925 |
| R2 | R0 + reward shaping v2（基线） | 0.613 | 0.623 | 0.560 | 0.940 |
| P0 | R2 + 自检提示词探针 | 0.608 | 0.623 | 0.555 | 0.925 |
| **T4** | **思考 SFT + 思考 GRPO** | **0.662** | **0.666** | **0.635** | 0.875 |

T4 在 r_hard / r_option / r_success 上超过全部 R 系列；R 系列内部三项均在 ±3pt 噪声内互相覆盖，T4 跳出该区间。提示词路线（P0）确认无效——行为只能靠训练注入。

## 3. 消融阶梯（official_test_200 r_hard）

| 模型 | 思考 | r_hard | done |
|---|---|---|---|
| base（Qwen3.5-2B 基模） | 关 | 0.000 | 0.05 |
| base | 开 | 0.000 | 0.03 |
| 新 SFT（思考蒸馏，无 RL） | 开 | 0.271 | 0.52 |
| **T4 = 新 SFT + GRPO** | 开 | **0.385** | 0.75 |
| R2（旧 SFT + GRPO，参照） | 关 | 0.319 | 0.855 |

要点：

- base 开思考仍是 0 分（149 agent_stop + 39 tool_error，死因是格式层面用不来工具）——思考修不了格式无能，蒸馏 SFT 是必要前提
- 思考 SFT 单独不够（0.271 < R2 0.319），**GRPO 是过线的主力**（+11.4pt）
- 新 SFT 的 agent_stop 在 test 上高达 32%（64/200），T4 压到 4%——RL 修掉了"提前收工"，这正是 SFT→RL 接力价值的直接证据

## 4. 机制归因（完成任务子分明细，R2 → T4）

| | dev | test |
|---|---|---|
| 满分（reward=1.0） | 112 → **127** | 58 → **68** |
| r_option<1（规格漏选） | 74 → **47**（-36%） | 108 → **72**（-33%） |
| r_att<1（属性缺失） | 30 → 23 | 74 → 54 |
| r_price=0（超价） | 8 → 6 | 17 → 14 |
| 完成任务均分 | 0.858 → 0.893 | 0.712 → 0.756 |
| 完成任务平均轮数 | 12.1 → 12.8 | 14.1 → 17.6 |

假设指向的失败模式（r_option 归零，占 badcase 92/99）修复率约 1/3，与 r_hard 涨幅一致。

**代价侧**：turn_limit 失败 dev 12→18、test 29→42。思考让模型更坚持，一部分任务打到 40 轮上限；这些轨迹全零，拉低 done 率与 r_loose。agent_stop 则大幅下降（T3 SFT 时 test 32% → T4 后 4%）。

## 5. 思考行为指标（T4 终版，两集评测）

| | dev | test |
|---|---|---|
| think 非空闭合率 | 99.8%（3170 turn） | 99.8%（4483 turn） |
| 未闭合（撞 2048） | 7 | 10 |
| response token mean / p95 | 224 / 703 | 246 / 753 |

思考通道全程稳定，无预算挤压。T4 训练全程 think 非空率 99.1%→99.8%。

## 6. 产物索引

- 数据：`runs/thinking_sft/prepared/turn_examples_thinking_6357.jsonl`（6357 turn 样本，6164 带 `reasoning_content`，与旧 SFT 同一批样本）
- 模型：T3 SFT `runs/qwen35_2b_shop_sft_thinking/`；T4 GRPO `runs/qwen35_2b_shop_rl_thinking/`（终版 `hf/rollout_99`，中期存档 24/49/74）
- 评测：`runs/qwen35_2b_shop_eval_rl_thinking/`（dev）、`..._official/`（test）、`..._sft_thinking_official/`（消融 SFT）、`..._base_thinking_official/`（消融 base）
- 阶段报告：`thinking-distill/` 下 t0/t1/t15/t3/t4 报告、p0_prompt_probe/result.md
- 代码：`pi-slime-shopsimulator` 仓库 `thinking-distill` 分支（env 门控、默认 off、未提交）

## 7. 局限与后续方向

1. **turn_limit 治理是第一优先**：过度坚持/打转成为新主要失败模式（test 21%）。方向：max_turns  curriculum、对打转轨迹的 shaping 惩罚、或在 SFT 数据中混入"及时收工"示范
2. k=1 噪声 ±3pt：dev +4.9pt 过线但余量不大；如需对外宣称，建议 k=3 复测 dev
3. 思考内容质量未做系统分级（是否真"逐项核对"还是"动作宣告"），RL 后思考是否退化为装饰有待人工抽读
4. 教师思考是英文为主（DeepSeek 默认），中文任务下的语言一致性未优化
5. reward shaping 与本路线正交，可叠加重试（R1/R2 的 shaping 技巧用在 T4 之上）
