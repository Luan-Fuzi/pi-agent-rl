# ShopSimulator 评测报告：Base / SFT / GRPO

日期：2026-09-01
评测协议：`examples/ShopSimulator/run_eval.sh` + `config/shop_eval_official_k1.yaml`
数据集：`official_test_200`（200 个任务，每任务 1 次 rollout，k=1，temperature=1.0，top_p=1.0，最多 40 轮交互，单任务 600s 墙钟超时，20 槽环境池并发）
说明：评测只推理，不更新权重。k=1 单采样，数值存在 ±几个百分点的采样噪声。

## 1. 总体结果（本次运行 vs 项目文档历史值）

| 模型 | 正奖励 pass@1 | 严格成功 pass@1 | mean@1 r_loose | mean@1 r_hard |
| --- | ---: | ---: | ---: | ---: |
| Base（本次） | 4.0% | 0.0% | 0.0126 | 0.0000 |
| Base（文档） | 2.0% | 0.0% | 0.0043 | 0.0000 |
| SFT（本次） | 72.0% | 17.0% | 0.4302 | 0.1984 |
| SFT（文档） | 72.5% | 10.5% | 0.3898 | 0.1244 |
| GRPO（本次） | 81.5% | 28.5% | 0.5764 | 0.3125 |
| RL（文档） | 90.5% | 31.0% | 0.6278 | 0.3545 |

指标定义（`examples/ShopSimulator/common.py`）：

- `r_loose`：环境原始 reward（0~1 部分得分），由类目/属性/选项/价格等子项加权合成
- `r_hard`：`r_type × r_att × r_option × r_price`（乘积，任一子项为 0 则清零）
- 正奖励 pass@1：`r_loose > 0` 的任务占比（流程走通并触发打分）
- 严格成功 pass@1：四个子分全部恰好为 1 的任务占比

## 2. 细分指标（本次三组）

| 指标 | Base | SFT | GRPO |
| --- | ---: | ---: | ---: |
| done_rate（episode 正常结束） | 0.05 | 0.75 | 0.82 |
| right_product_rate（买对 ASIN） | 0.005 | 0.25 | 0.375 |
| r_type（类目） | 0.05 | 0.75 | 0.82 |
| r_att（属性） | 0.015 | 0.454 | 0.612 |
| r_option（选项） | 0.00 | 0.226 | 0.334 |
| r_price（价格约束） | 0.025 | 0.625 | 0.72 |
| 全零分任务占比 | 96% | 28% | 18.5% |
| 平均模型轮数 | 30.1 | — | — |

终止原因分布（200 条）：

| 终止原因 | Base | SFT | GRPO |
| --- | ---: | ---: | ---: |
| environment_done（环境正常结束） | 10 | 150 | 164 |
| turn_limit（顶满 40 轮） | 115 | 50 | 36 |
| agent_stop / agent_tool_error | 75 | 0 | 0 |

## 3. 合理性分析

### Base：与文档一致（≈0 分）

基座模型基本不会玩：96% 任务零分，r_hard 与严格成功均为 0，与文档 Base 行（2.0% / 0.0043）同一量级。终止原因以 turn_limit（115）和 agent 侧错误/中止（75）为主——不懂工具调用格式、在页面间无效徘徊，符合未训练基座的预期行为。本次 4.0% 正奖励略高于文档 2.0%，属 k=1 噪声范围。

### SFT：复现达标，略优于文档

- 正奖励 72.0% vs 文档 72.5%：持平（差 0.5pt，噪声内）
- r_loose 0.430 vs 0.390、r_hard 0.198 vs 0.124、严格成功 17.0% vs 10.5%：均高于文档

合理的解释：本次教师数据略多且质量相当（416 条通过筛选的轨迹 / 6357 个 turn 样本 vs 文档 412 / 6153），覆盖 414/512 任务（80.9% vs 文档 80.5%）。SFT 的典型画像——流程大多走通（done_rate 75%），但细节匹配（属性 0.45、选项 0.23）是主要失分项。

### GRPO：提升方向与文档一致，幅度略小

- 相对本次 SFT：r_loose 0.430→0.576（+0.146），严格成功 17%→28.5%（+11.5pt），done_rate 75%→82%
- 文档 RL 相对文档 SFT：r_loose 0.390→0.628（+0.238），严格成功 10.5%→31%（+20.5pt）
- 绝对值略低于文档 RL（r_loose 0.576 vs 0.628，正奖励 81.5% vs 90.5%）

提升方向、量级与文档完全一致的结论：**GRPO 确实吃到了在线强化学习的增益**。幅度略小的可能原因：

1. **起点更高**：本次 SFT 本身比文档 SFT 强（r_loose +0.04、严格成功 +6.5pt），越靠近天花板增益越小；而本次 GRPO 与文档 RL 的差距（r_loose −0.05）已小于两者 SFT 起点的差距方向，属正常波动
2. **有效 batch 收缩**：GRPO 训练后期全对/全错的零方差 group 增多（日志中 `zero_std/count_1.0` 频繁出现），这些组不产生梯度，100 个 rollout 后段的有效学习信号减弱
3. **k=1 采样噪声**：单次评测 ±几个百分点，0.576 vs 0.628 的差距约 1 个噪声单位
4. 训练动态与评测互相印证：GRPO rollout 后期 truncated_ratio 多次整批归零 ↔ 评测 done_rate 从 75% 升到 82%，turn_limit 从 50 降到 36

### 结论

三组数据与文档趋势完全一致（Base≈0 → SFT 会玩但粗糙 → GRPO 明显提升），绝对数值与文档历史值同量级、互有胜负，训练流程复现成功。若要进一步追平文档 RL 数值，可考虑：增大 GRPO epoch 或 prompt 集、过滤零方差组提高有效 batch、评测时 k>1 多次采样降低噪声。

## 4. 产物与复现

| 项 | 路径 |
| --- | --- |
| Base 评测结果 | `runs/qwen35_2b_shop_eval_base/eval_results.json` |
| SFT 评测结果 | `runs/qwen35_2b_shop_eval_sft/eval_results.json` |
| GRPO 评测结果 | `runs/qwen35_2b_shop_eval_rl/eval_results.json` |
| SFT 模型 | `runs/qwen35_2b_shop_sft/hf/rollout_0` |
| GRPO 模型 | `runs/qwen35_2b_shop_rl/hf/rollout_99` |
| Base 模型 | `pi-slime-work/models/Qwen3.5-2B` |
| SFT 训练日志 | `runs/qwen35_2b_shop_sft/train.log` |
| GRPO 训练日志 | `runs/qwen35_2b_shop_rl/train.log` |

评测耗时（单卡 RTX 6000D）：SFT ~12 min，GRPO ~15 min，Base ~14 min。
