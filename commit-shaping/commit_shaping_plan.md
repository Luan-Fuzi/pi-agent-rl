# Commit Shaping 计划书：过程级 reward 塑造，治思考模型的"不敢下单"

日期：2026-09-04
性质：**只改训练侧 reward，不动环境、不动评测**。沿用 reward-shaping 的三条红线与工程纪律。
前置文档：`runs/thinking_sft/report.md`（T5 终稿，本计划的起点模型与基线）、`thinking-distill/thinking_distill_plan.md`、`runs/reward_shaping/report.md`（R1/R2 负结果教训，必读）
代码分支：`commit-shaping`（从 `thinking-distill` 切出；实现启动时建，git 操作前先经用户确认）

## 0. 目标与核心假设

T4 思考模型（`runs/qwen35_2b_shop_rl_thinking/hf/rollout_99`）r_hard 双集过线（dev +4.9pt / test +6.6pt vs R2），代价是 done 率下降（dev 0.875 vs 0.940，test 0.750 vs 0.855）。2026-09-04 对 T5 评测 dump 的轨迹级归因：

- test：T4 有 50 个非 done（42 turn_limit + 8 agent_stop；R2 为 29 turn_limit、0 agent_stop）。其中 **34 个是 R2 能完成的新增失败**，R2 在这些任务上均分 0.647，T4 全部归零。
- **34 个新增失败中 14 个打开过目标商品页（R2 买下得分的那个 ASIN）却没买**——"正确答案在眼前没选中"的决策版。
- 行为模式是**语义级打转**而非死循环复读：search → 开商品页 → 点规格 → back to search → 换词再 search。42 条 turn_limit 轨迹连续动作重复 ≤1 次/条，均值 17.9 次 search、3.4 个不同商品，**仅 6/42 尝试过 `click[buy now]`**。典型案 task 1094：第 2 轮打开目标商品、思考里逐条核对全 ✓，卡在"698 不是约 600"，同 ASIN 反复开 6 次，40 轮耗尽。
- agent_stop 8 条（test）只有 1 条试过买：逛 7~35 轮后主动放弃。
- 成功的轨迹也更慢：T4 done 均值 17.6 轮 vs R2 14.1，首次 buy 动作位置 13.0 vs 8.2——核对烧轮数，慢尾被 40 轮上限切掉。

**根因判断**：思考示范把"下单前约束核对"内化成了"全部约束满足才下单"，对"约/左右"类模糊约束施加了过严判据；而 env reward 是部分分制（买错规格也有 0.6+，不买=0）——**模型的决策效用与 reward 结构错位**。叠加结构性放大器：打转任务上 4 条 candidate 全 0 → GRPO 零方差零梯度（本就有 34~36% 零方差率），"何时收手"学不到信号。

> **假设**：把终局 0 分的非 done 轨迹按过程进度分级（里程碑分），辅以空转惩罚与效率衰减，可在组内制造"买过 > 差点买 > 打转 > 放弃"的稳定排序，回收 done 率且不吐回 r_hard。

**证伪条件**（预先声明，对齐 R1/R2 教训）：E1 训完后 dev_200 双轴（done、r_hard）均无超噪声变化，即"信号变了行为不动"复现 → 停止烧卡，转入数据侧路线（SFT 混"近似即下单"示范 / T4 rollout 偏好对）。

## 1. 设计原则（继承 reward-shaping，一条不改）

1. 只改训练侧，唯一入口仍是 `slime/examples/ShopSimulator/generate.py` 的 `shape_reward` 调用点；环境与评测口径不动，历史数字可比性保持。
2. shaping 只对**组内相对差异**有意义：每一项必须回答"它在同任务 4 条 candidate 间制造了什么新排序"。
3. 原始分必须可复盘：`env_reward_raw` 已进 metadata；评测永远 shaping OFF（`reward_shaping={}` 自证）。

## 1.5 R2（无思考）trace 对照：打转不是 thinking 带来的，但成分不同

2026-09-04 对 R2 official_test dump 的逐轮解析（回答"这些改动不开 thinking 是否成立"）：

| | R2 turn_limit(29) | T4 turn_limit(42) |
|---|---|---|
| 尝试过 buy | 2/29 | 6/42 |
| 打开过目标商品页 | **5/29（17%）** | **15/42（36%）** |
| 搜索词重复率 | 14%（103/737） | 8%（62/753） |
| 连续重复动作 | 22 次（22 条里有字面复读） | ≈0（语义循环） |
| 形态 | 空 think + 关键词汤搜索（"天发 天投珠 儿童 银色 腋下 模型组"），**找不到/认不出** | 逐条核对后否决近似品，**找到了不下单** |

结论：打转是 R2 就有的旧病（test 14.5%），thinking 把数量 29→42 但**换了成分**——R2 死于搜索空间迷航（能力/引导 bound），T4 死于过度核对（决策校准 bound）。对 shaping 的含义：

- **E1 里程碑分机制与 thinking 无关**：全零组零梯度的结构性问题两个模型都有，分级排序都成立；R2 的 buy 尝试率（2/29）比 T4 更缺这个信号。
- **E2 空转惩罚在 R2 上目标更多**（字面重复 22 次、重复搜索 103 条）。
- **E3 效率衰减是 thinking 特异的**（R2 done 轨迹本就高效，首次 buy 在 8.2 动作位，无头可砍）。
- **可回收上限不同**：R2 打转里只 17% 见过目标商品（多数不是 near-miss，里程碑分治不了"找不到"）；T4 有 36% 见过，直接可回收。所以主线仍打 T4 lineage；无思考臂只作可选对照（见 §4 E1b）。
- **诚实声明的反证据**：R1/R2 恰是在无思考模型上的 shaping 负结果（信号变、行为不动）——这是"本 stack 上 shaping 推不动策略"的真实先验；E1 值得试的理由是它作用于此前完全无信号的零方差组，而非微调已有信号，但该先验已计入证伪条件的权重。

## 2. 改动点（3 处，env 门控、默认行为不变）

| # | 位置 | 改动 |
|---|---|---|
| 1 | `slime/agent/adapters/common.py` / `generate.py` | **过程统计采集**：复用 per-turn debug callback（`common.py:336`）或 finish 时从 session 的 manager_message tool_calls 重建动作序列，汇总 per-session 计数器：search 次数、搜索词去重、商品页(asin)打开次数、重开次数、规格点击数、`click[buy now]` 次数、连续 back-to-search 数、model_turns |
| 2 | `reward_shaping.py` | `shape_reward` 扩展签名接收过程统计；新增 variant：`milestones`（E1）、`milestones+antiloop`（E2）、`+efficiency`（E3），与既有 off/option_gate/budget/full 并列、可组合；`SHOP_REWARD_SHAPING` 取值扩展；单测补齐（沿用 `test_reward_shaping.py` 18/18 传统） |
| 3 | `run_rl.sh` / `run_eval.sh` | 新 env 透传（shaping 变体、系数）；训练开、评测关 |

**不改的**：ShopSimulator 环境仓库、GRPO 算法配置、任务文件、评测口径、思考相关开关（`SLIME_ROLLOUT_THINKING=1` 全程保持）。

## 3. Shaping 设计（对应 E1~E3）

### E1：里程碑分级分（主攻零方差组，治"打转/放弃无梯度"）

非 done 轨迹按最远进度给阶梯分（从过程统计算）：

| 最远进度 | shaped 分 |
|---|---|
| 无有效推进（含报错/空转未开页） | 0 |
| 打开过候选商品页（click[asin]） | 0.05 |
| 选过规格（click 非 asin/description/features/back） | 0.10 |
| 点过 `buy now`（即使未成交） | 0.15 |

- 上限 0.15 低于任何真实 purchase（done 最低约 0.2+），不会鼓励"假装买"；done 轨迹分文不动。
- 组内机制：四条全打转的组第一次有了优势差，"离下单更近"拿正梯度；agent_stop（多无 buy 尝试）自然排在打转之下——RL 已证明能学这个梯度（agent_stop 32%→4% 就是终局信号教的）。

### E2：E1 + 空转惩罚（靶向打转）

| 模式 | 罚则 |
|---|---|
| 同一 asin 第 2 次打开起 | -0.02/次 |
| 重复相同搜索词 | -0.02/次 |
| 连续 back-to-search 无新候选 | -0.01/次 |

首次重开不罚（合法复查），只罚第 N≥2 次。组内效果："原地打转"稳定排在"果断推进"之后。罚额从里程碑分里扣（不下探到负，避免压过全废轨迹）。

### E3：胜者 + 效率衰减（治变慢与 40 轮尾部）

done 轨迹：`reward × (1 − ε·max(0, turns−15)/40)`，ε=0.1（消融点 0.05/0.2）。只对 done 生效，非 done 由 E1 管。给"快而对的买"相对"慢而对的买"的组内优势，间接给 turn_limit 解压。

**明确不叠**：R2 的 budget 收紧（方向相反——超预算归零会喂大"价格不完全吻合就不买"的过度严格）；option_gate 与思考路线同向，可选不默认。

## 4. 实验拆解与预算

单价实测（单卡）：非思考 100 step GRPO = 6.4h（R2，09-02 02:15→08:40）；思考版 = 13h（T4 实测）；dev_200/test_200 评测（思考版）= 20~30 min。所有 run 从 T3 SFT checkpoint（`runs/qwen35_2b_shop_sft_thinking/`）重跑 100 step，逐项对齐 T4（rl_500、n=4、lr 1e-6、KL 0.001、原始 env reward、seed 全同），**唯一变量是 shaping 信号**；baseline 就是 T4，不重跑。

| 阶段 | 内容 | 耗时 |
|---|---|---|
| T1 | 改动 #1/#2/#3 实现 + 单测 + 用 T4 现有 dump 离线重放验证（触发率、排序方向、零方差率变化） | 0.5~1 天，纯 CPU |
| T2 | E0 冒烟（smoke 规模，核查过程统计正确、shaping 触发、训练链路无回归） | ~1h GPU |
| T3 | E1 训练 + dev_200 双轴判 | 13h + 0.5h |
| T4 | E2 训练 + dev_200（E1 阳性才续） | 13h + 0.5h |
| T5 | E3 训练 + dev_200（前置胜者之上） | 13h + 0.5h |
| T6 | 冠军 official_test_200 终判 vs T4 test；报告 `runs/commit_shaping/report.md` | ~0.5h |
| （可选）E1b | **无思考对照臂**：E1 同款 milestones shaping 跑在旧 SFT lineage（从 `runs/qwen35_2b_shop_sft/` 起，非思考 100 step 仅 6.4h）+ dev_200。直接实证"里程碑分不开 thinking 是否成立"：若两臂同效则技术通用，若仅思考臂有效则证实"思考放大 shaping 可学性"的协同叙事。不影响主线决策，纯归因 | 6.4h + 0.3h |

预算：**全量 ~42 GPU 小时 / 约 2 天墙钟**；阶梯式带 kill 判据（E1 负结果即停）最短 ~15 GPU 小时。

事故纪律（T4 血泪教训）：`SAVE_INTERVAL=25`、输出全部重定向落盘、后台任务输出不得超上限。

## 5. 判据（预注册，评测前钉死）

每个 run 在 dev_200 上与 T4 同口径对比（k=1、shaping OFF、同 seed）：

- **正结果**：done ≥ T4 +3pt **且** r_hard 不掉出 T4 ±3pt——双轴缺一不可（防"修数量吐精度"）；
- **负结果**：双轴均在 ±3pt 内不动 → 触发 §0 证伪条件，停；
- **一涨一掉**：记"不确定"，如实写，不事后合理化。

T6 终判：冠军 test vs T4 test（done 0.750 / r_hard 0.385），同三态口径。参考回收上限：34 个新增失败全回收 = test done +17pt；第一梯队 14 个"开页没买"回收一半也有 +3~4pt。

## 6. 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| 复现 R1/R2"信号变行为不动" | **高（核心证伪点）** | E1 定生死；本次差异：在零方差组内制造方差，是 GRPO 此前完全无信号处，而非微调已有信号 |
| 效率衰减推回草率下单、r_option 回吐 | 中 | ε 小、只对 done 生效、双轴判据、E3 单独成 run 可隔离归因 |
| 里程碑分被钻空子（刷 buy 点击） | 低 | buy 点击是真实环境行为且 0.15 远低于真买；E0 冒烟核查分布 |
| 过程统计采集 bug 污染训练 | 中 | 单测 + T1 离线重放与 eval 记录对拍 + E0 冒烟触发率核查 |
| 与 thinking 路线耦合出意外行为 | 低 | shaping 全程 env 门控，OFF 时逐位等于 T4 管线 |

## 7. 产物与隔离约定

- 项目目录：`commit-shaping/`（本计划 + 阶段报告 t1~t6 + 脚本）；runs：`runs/qwen35_2b_shop_rl_commit_e1/` 等新 RUN_ROOT；`runs/thinking_sft/`、`runs/reward_shaping/`、T3/T4 目录只读。
- 代码：`pi-slime-shopsimulator` 仓库 `commit-shaping` 分支（从 `thinking-distill` 切出）；所有开关 env 门控、默认 off。
- 每阶段结束写阶段报告；git 提交/推送前必须先经用户确认。
