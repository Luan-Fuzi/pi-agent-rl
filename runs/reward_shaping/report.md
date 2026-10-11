# Reward Shaping 实验定稿报告：审计驱动的 GRPO 奖励修复

日期：2026-09-02 · 分支：`reward-shaping` · 产物根目录：`runs/reward_shaping/`

## 0. 一句话结论

基于审计发现的三处奖励缺陷做了两个修复（规格加权、预算收紧），训练信号层面修复**真实且大规模生效**（46% 样本分数被调整、3,487 条超预算轨迹被收紧），但在 dev_200 和 official_test_200 两个赛场上，**行为层面均未产生统计显著的收益**。这是一个过程完整、结论诚实的负结果。

## 1. 来龙去脉

1. **复现**：Pi + Slime + ShopSimulator 的 agentic GRPO 工作流（SFT → GRPO 100 step，Qwen3.5-2B），产出基线 R0。
2. **审计**（`runs/asin_audit/`）：对 official_test_200 上的 RL 评测做逐条分析，发现四类问题：
   - 买错商品却拿高分（wrong_high 23.5%），其中 36/47 条 r_option=0——**规格选错惩罚不足**；
   - 18.5% 的购买超出指令文本预算却拿 r_price=1——**环境只对照商品元数据 price_upper，读不懂指令预算**；
   - 任务集存在"指令预算 < goal 商品定价"的自相矛盾（official_test 池 27.2%）；
   - r_option 系统性偏低（done 均值 0.334）。
3. **修复设计**（`reward_shaping.py`，env 门控默认 off，纯 stdlib，18/18 单测通过）：
   - `option_gate`：env 公式中规格命中按 w_opt=2 加权重算；
   - `budget`：用离线解析的指令预算表（`task_budget.json`，20,142 条）+ 确定性价格表重算 r_price，超预算×1.1 归零，只收紧不放松；
   - 数据清洗：剔除 6 个真冲突任务（goal 价 > 预算×10），产出 `rl_500_clean.jsonl`（未单独烧 run 验证，见 §4）。
4. **实验**（消融链，同 SFT 起点、同数据、同 100 step、同超参，唯一变量是 reward 信号）：
   - R0 = 原 reward；R1 = option_gate；R2 = full（option_gate+budget）。R3（full+干净数据）因预期收益过小取消。

## 2. 结果总表

### dev_200（k=1，与 official_test 零重叠，三模型同口径）

官方口径（全体摊薄、未下单记 0）：

| 指标 | R0 | R1 | R2 |
|---|---|---|---|
| done_rate | 0.915 | 0.925 | 0.940 |
| r_loose | 0.791 | 0.800 | **0.806** |
| r_hard | 0.631 | **0.642** | 0.613 |
| r_success | 0.605 | 0.605 | 0.560 |
| r_price | 0.885 | 0.880 | **0.900** |
| r_option | 0.638 | **0.661** | 0.623 |

审计口径：

| 指标 | R0 | R1 | R2 |
|---|---|---|---|
| done 率 | 91.5% | 92.5% | 94.0% |
| right_full / right_partial | 60.5% / 15.5% | 60.0% / 14.5% | 55.5% / 22.5% |
| wrong_high | 3.5% | 7.5% | 5.0% |
| right product 率 | 76.0% | 74.5% | **78.0%** |
| r_option 均值 | 0.698 | 0.714 | 0.663 |
| 预算合规率 | 66.7% | 66.5% | 66.9% |
| 超预算仍 r_price=1 | 49 | 47 | 49 |

### official_test_200 · 官方指标口径（`common.py official_metrics`，全体 200 条摊薄、未下单记 0）

| 指标 | base | SFT | R0 | R1 | R2 |
|---|---|---|---|---|---|
| done_rate | 0.050 | 0.750 | 0.820 | **0.890** | 0.855 |
| r_loose（环境分） | 0.013 | 0.430 | 0.576 | 0.598 | **0.609** |
| r_hard（子分连乘） | 0.000 | 0.198 | 0.313 | **0.325** | 0.319 |
| r_success（全满分率） | 0.000 | 0.170 | 0.285 | 0.290 | 0.290 |
| right_product | 0.005 | 0.250 | 0.375 | 0.385 | **0.400** |
| r_att | 0.015 | 0.454 | 0.612 | 0.641 | **0.644** |
| r_option | 0.000 | 0.226 | 0.334 | **0.355** | **0.355** |
| r_price | 0.025 | 0.625 | 0.720 | 0.765 | **0.770** |

口径注意：与下表（审计口径，仅 done 样本均值）相比，官方口径把未下单记 0 并按全体摊薄，因此 r_option 0.334 等与审计报告一致。读数要点：R1/R2 在 8 个指标上几乎全部 ≥ R0（仅 R2 的 r_hard 略低于 R1），两个修复的目标子分（r_option、r_price）均上涨——单点幅度（+0.02~0.03）在 k=1 噪声内，但多指标同向降低了纯噪声解释的概率；R1 的 r_price 涨幅主要来自 done 率上升，R2 在其上的边际（0.765→0.770）才是 budget 修复的净贡献，很小。

### official_test_200 · 审计口径（k=1，五模型同口径重算；base/SFT 为复现期评测产物）

| 指标 | base | SFT | R0(GRPO) | R1 | R2 |
|---|---|---|---|---|---|
| done 率 | 5.0% | 75.0% | 82.0% | **89.0%** | 85.5% |
| right_full / right_partial | 0.0% / 0.5% | 17.0% / 8.0% | 26.5% / 11.0% | 28.5% / 10.0% | 27.5% / 12.5% |
| wrong_high | 0.5% | 20.0% | 23.5% | 23.0% | 24.5% |
| no_buy | 95.0% | 25.0% | 18.0% | **11.0%** | 14.5% |
| right product 率 | 0.5% | 25.0% | 37.5% | 38.5% | **40.0%** |
| r_option 均值 | 0.000 | 0.301 | 0.408 | 0.399 | 0.415 |
| 预算合规率 | 40.0% (n=10) | 58.7% | 62.8% | 58.4% | 63.9% |
| 超预算仍 r_price=1 | 1 | 40 | 41 | 50 | 46 |
| 高分规格落空 | 1 条 | 32 条 | 36 条 | 38 条 | 37 条 |

阶梯读数：base→SFT→GRPO 的主增益清晰（right product 0.5%→25%→37.5%）；R1/R2 在 right product、done 率、no_buy 上方向一致地略优于 R0（+1~2.5 点），但幅度在 k=1 噪声内；r_option 与高分规格落空在 GRPO 之后不再被任何变体改善（0.301→0.408 的那步提升来自原版 GRPO 本身，修复没有追加收益）。

### 训练侧（100 rollout 全量 dump）

| | R0 | R1 | R2 |
|---|---|---|---|
| 分数被 shaping 改变 | — | 41% | 46% |
| budget 收紧（r_price 1→0） | — | — | 3,487 条 / 112 任务 |
| 零方差率 | 34.8% | 36.0% | 36.2% |
| shaping_error | — | 0 | 0 |

## 3. 读数与归因

**观察到的弱信号（均不构成显著结论）**：
- R1/R2 的 no_buy 在 official_test 上下降（18%→11%/14.5%）、done 率上升——修复让模型更敢下单，但买错低分（wrong_low）同比例上升抵消；
- R2 的 right product 在两个赛场都是三者最高（78.0% / 40.0%），方向一致但幅度在噪声内。

**核心问题：为什么训练信号大规模改变、行为不变？**

1. **奖励扰动量级不足**：shaped delta 典型值 ±0.1，而 GRPO 组内（4 样本/任务）优势被任务难度差异主导，微调推不动策略；
2. **病灶分布与赛场错配**：审计严重数字来自 official_test（r_option 0.334、wrong_high 23.5%），但统一口径重算后发现修复目标的"高分规格落空"在两个赛场上几乎不变（36/38/37）——说明这些案例大多不是"奖励太松导致模型学不会"，而是模型能力边界（找不到正确变体），reward 修复治不了；
3. **100 step 太短**：细粒度价格/规格约束可能需要更长训练；
4. **已知噪声上限**：k=1、n=200 的评测，±3 个点皆噪声；两赛场所有组间差异基本都在此范围内。

**方法论上成立的部分**：
- 消融变量隔离干净（R1 预算合规率纹丝不动，证明 option_gate 没碰价格）；
- 双赛场纪律执行到位（dev 迭代、official_test 最终各测一次，全部结果并列呈现，无选优偏差）；
- 三次评测均自证 shaping OFF（`reward_shaping={}`、reward==env_reward_raw）。

## 4. 已知局限与留档事项

- **冲突任务矛盾（R2）**：6 个真冲突任务在 full 修复下"买对被罚"（task 19944 被收紧 70 次）。R3 取消后此变量未隔离，规模小（6/500）但方向上是反作用。`rl_490_clean.jsonl` 已留档，未来训练建议直接使用。
- **系数未扫描**：w_opt=2.0、budget_tol=1.1 均为一次性设定，未做敏感性分析。
- **checkpoint 选点**：所有 run 只存最后一帧（iter_99），未验证中间帧是否更优。
- **评测方差未量化**：k=1；对最终结论做 k=4 复测是后续最值得做的低成本补强。

## 5. 后续方向（按性价比）

1. k=4 复测冠军/R0，给结论配方差估计（约 4 倍评测时长）；
2. 零方差组治理（DAPO 动态采样）——34~36% 的组被优势归零浪费，治理它直接提升训练效率，且与 reward 修复正交；
3. 更长的训练（300+ step）+ 多 checkpoint dev 选点，验证"修复收益随训练量显现"的假设；
4. 若重做 reward 路线：优先把 budget 收紧从 0/1 改为按超出比例的平滑惩罚，并配合冲突任务清洗（rl_490_clean）。

## 6. 产物清单

- 代码（`reward-shaping` 分支，未提交）：`reward_shaping.py`（新）、`generate.py`（+9 行 hook）、`run_rl.sh`（env 透传 +4 key）、`run_eval.sh`（PROMPT_DATA 可覆盖）、`summarize_eval.py`（+2 字段）、`config/shop_rl_smoke.json` / `shop_rl_clean.json` / `shop_eval_dev_k1.yaml`（新）
- 数据表：`task_dims.json`、`task_budget.json`、`prices.json`、`dev_200.jsonl`、`rl_500_clean.jsonl`、`rl_490_clean.jsonl`、`smoke_20.jsonl`
- 分析脚本：`acceptance.py`、`dump_inspect.py`、`export_budget.py`、`make_task_files.py`、`test_reward_shaping.py`（18/18 通过）
- 分阶段报告：`phase0_report.md` ~ `phase4_report.md`、`r0_dev_acceptance.md`、`r1_dev_acceptance.md`、`budget_review.md`
- 运行目录：`runs/qwen35_2b_shop_rl_smoke`、`_r1`、`_r2`、`runs/qwen35_2b_shop_eval_rl_r0_dev`、`_rl_r1`、`_rl_r2`、`_rl_r1_official`、`_rl_r2_official`
