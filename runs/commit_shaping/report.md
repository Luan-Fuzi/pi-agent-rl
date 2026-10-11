# Commit Shaping 总报告：过程级 reward 塑造治"不敢下单"

日期：2026-09-06（当日两次修订：补 k=3 复测新增 §1b；补 E1b 归因新增 §2b，§0/§4/§6 同步修正）
计划书：`commit-shaping/commit_shaping_plan.md`（2026-09-04，判据预注册于评测前）
代码分支：`commit-shaping`（工作区改动未提交；全部 env 门控、默认 off，逐位等于 T4 管线）
阶段报告：`commit-shaping/t1_report.md`（实现+单测+重放）→ `t2`（冒烟）→ `t3`（E1）→ `t4`（E2）→ `t5`（E3）

## 0. 结论

**dev 竞技场阳性；official_test 的 k=1 终判"未复现"经 k=3 配对复测修正为：done 轴弱阳性（+4.2pt，95% CI [+0.2, +8.3]，刚排除 0），r_hard 轴维持中性。收益真实但微小，且对最大失败源 turn_limit 无效。归因上，milestones 的收益是 shaping × thinking 的交互项——无思考对照臂 E1b 下效应消失（−1.0pt，CI 含 0）。**

- 预注册证伪门（E1 dev 双轴）**通过**：E1 done +7.5pt / r_hard +2.1pt，假设"在零方差组内制造排序可回收 done 率"在 dev 成立，与 R1/R2"信号变行为不动"形成对照
- k=1 终判（T6）双轴均未超噪声（done +2.0pt / r_hard −0.6pt）；k=3 配对复测（同 200 题 ×3 采样、同 seed，任务级配对差 + bootstrap CI，协议跑前书面固定）done **+4.2pt** 越过 +3pt 噪声带——**叙事由"未复现"修正为"done 弱阳性、幅度小"**
- r_hard 两轮 test 均中性（k=1 −0.6pt；k=3 +1.2pt，CI [−3.0, +5.4]）：shaping 没有"牺牲精度换数量"
- E1b 归因（§2b）：非思考 + milestones 相对非思考基线 R0 在 dev 上 done −1.0pt（CI [−5.5, +3.5]）——**没有思考，milestones 信号没有可推的杠杆**
- test 上最稳的收益是效率：done 均轮 k=1 −2.1（17.6→15.5）、k=3 −2.1（17.4→15.3），两轮一致；agent_stop 8→5；核心攻击目标 turn_limit 42→41 未动

一句话：shaping 信号确实进了训练、确实改变了行为，k=3 证据下 done 收益在 test 上大概率真实但只有 ~4pt，且该收益依赖思考开关；它治好了一部分"不敢下单"，却够不到 turn_limit 这个大头——数据侧路线因此仍是推荐主线。

## 1. 终判数字（official_test_200，k=1，seed 42，shaping OFF）

| 指标 | E3（冠军） | T4（基线） | Δ | 判据 |
|---|---|---|---|---|
| **done_rate** | 0.770 | 0.750 | **+2.0pt** | 未达 +3pt（k=3 后修正，见 §1b） |
| **r_hard** | 0.379 | 0.385 | **−0.6pt** | 在 ±3pt 内 |
| r_success | 0.330 | 0.340 | −1.0pt | |
| r_option | 0.426 | 0.414 | +1.2pt | |
| r_loose | 0.559 | 0.567 | −0.8pt | |
| right_product | 0.385 | 0.420 | −3.5pt | |
| turn_limit / agent_stop | 41 / 5 | 42 / 8 | −1 / −3 | |
| done 均轮 | **15.5** | 17.6 | **−2.1** | 效率收益（非判据轴） |

参照 R2 test（无思考基线，done 0.855 / r_hard 0.319）：E3 保住了 T4 的 r_hard 收益（+6.0pt vs R2），但 done 率仅回收至 0.770（R2 的 0.855 仍差 8.5pt）——"精度换数量"的代价只补回了一小部分。

## 1b. k=3 配对复测终判（official_test_200，2026-09-06 补做）

协议（跑前书面固定于 launcher 注释与 `commit-shaping/k3_compare.py`）：每题 3 采样、同 seed 42、温度 1.0、shaping OFF，两臂各 600 episodes；聚合为 per-task 均值后取配对差（E3−T4），bootstrap 95% CI（任务级重采样 10k 次，seed 0）；判据沿用原计划 ±3pt 噪声带。

| 指标 | E3 | T4 | Δ（配对） | 95% CI | 任务级 胜/平/负 |
|---|---|---|---|---|---|
| **done** | 0.805 | 0.763 | **+4.2pt** | [+0.2, +8.3] | 48 / 126 / 26 |
| **r_hard** | 0.403 | 0.392 | +1.2pt | [−3.0, +5.4] | 54 / 97 / 49 |
| r_loose | 0.587 | 0.579 | +0.8pt | [−2.8, +4.4] | 83 / 51 / 66 |
| r_success | 0.358 | 0.360 | −0.2pt | [−4.7, +4.3] | 48 / 106 / 46 |
| right_product | 0.410 | 0.430 | −2.0pt | [−6.5, +2.3] | 45 / 104 / 51 |
| done 均轮 | **15.3** | 17.4 | **−2.1** | — | 效率收益复现 |

pass@3 侧写（E3）：pass_done 0.93、pass_success 0.57、仅 7% 任务（14/200）三次全零——剩余失败以"发挥不稳定"为主，而非"做不到"；那 14 个全零任务与 §4.2 所述 k=1 下"开页没买"未救回的任务群高度重合，是数据侧路线的首要目标。

产物：`runs/qwen35_2b_shop_eval_commit_e3_official_k3/`、`runs/qwen35_2b_shop_eval_rl_thinking_official_k3/`（launcher `commit-shaping/eval_{e3,t4}_official_k3.sh`，配置 `shop_eval_official_k3.yaml`）。

## 2. dev_200 竞技场（三支消融，逐项对齐 T4 仅改 shaping 信号）

| 变体 | 配置 | done | r_hard | r_success | r_option | done 均轮 | 判定 |
|---|---|---|---|---|---|---|---|
| T4 | 基线 | 0.875 | 0.662 | 0.635 | 0.666 | 12.8 | — |
| E1 | milestones | **0.950** | 0.683 | 0.645 | 0.698 | 13.6 | **双轴阳性** |
| E2 | +antiloop | 0.885 | 0.705 | 0.685 | 0.711 | 14.6 | 不确定（r_hard 涨 / done 平） |
| E3 | +efficiency | 0.915 | **0.715** | **0.690** | **0.723** | **11.3** | **双轴阳性（冠军）** |

归因：milestones 是 done 回收主力（非 done 按进度分级 0.05/0.10/0.15，零方差全零组 80% 被拉出方差——T1f 重放实证）；antiloop 因"罚穿封底重建底部零方差 + 误伤合法坚持"抵消收益；efficiency 是唯一在 dev 上同时保住 done 并挤压精度/速度的组件。

## 2b. E1b 归因实验：milestones 的收益是否 thinking 特异（dev_200，k=1，2026-09-06 补做）

2×2 设计：思考臂从 `sft_thinking` 起跑且 rollout 开思考，非思考臂从旧 `sft` 起跑且不开思考；shaping 仅 milestones 开/关。四格全部为 dev_200、k=1、seed 42、评测 shaping OFF。

| | 无 shaping | + milestones | Δ shaping |
|---|---|---|---|
| **非思考** | R0：done 0.915 / r_hard 0.631 | E1b：done 0.905 / r_hard 0.614 | **−1.0pt / −1.7pt（配对 CI 均含 0，无效）** |
| **思考** | T4：done 0.875 / r_hard 0.662 | E1：done 0.950 / r_hard 0.683 | **+7.5pt / +2.1pt（双轴阳性）** |
| Δ thinking | −4.0pt / +3.1pt | +4.5pt / +6.9pt | |

E1b vs R0 任务级配对（`k3_compare.py`，bootstrap 95% CI，10k 次）：done −1.0pt [−5.5, +3.5]（胜/平/负 9/180/11），r_hard −1.67pt [−7.2, +3.8]。E1b 训练健康度与 E1/E2/E3 同包络（entropy 0.07–0.23 无塌缩，kl_loss→0.019 远低钳位）。

结论：**milestones 的 dev 收益是 shaping × thinking 的交互项，而非 shaping 主效应**。机制解读：里程碑分奖励的是"推进购物流程"的多步行为序列，只有带思考的模型才有可塑造的规划行为；非思考模型行为空间被压缩（done 均轮 10.5 vs 思考臂 13+，turn_limit 仅 18/200），信号没有杠杆可推。实践含义：后续数据侧路线与部署形态应锁定"思考开"。

产物：模型 `runs/qwen35_2b_shop_rl_commit_e1b/`（终版 `hf/rollout_99` + `checkpoints/iter_0000099`；中期存档待 prune）；评测 `runs/qwen35_2b_shop_eval_commit_e1b_dev/`；launcher `commit-shaping/run_e1b.sh`、`eval_e1b_dev.sh`。

## 3. 机制与工程验证（T1/T2 阶段产物）

- 过程统计采集：pi `tool_execution_start` 事件带 args，toolCallId 配对得动作序列（`PiRunResult.actions`）；metadata 新增 `process_stats` / `action_sequence`，冒烟 80/80 无缺失
- 单测 49/49 + 旧版回归 18/18；变体解析未知组件 import 期报错
- T4 dump 离线重放：解析器与计划 §0 归因数字精确互验（50 非 done = 42 tl + 8 as；buy 尝试 7 = 6+1）；E1 触发率 99.4%
- 训练健康（train.log 体检，E1/E2/E3/E1b vs T4 同包络）：entropy 缓降无塌缩；clipfrac/ppo_kl≈0 为 1-step-per-rollout 严格在线的预期形态；kl_loss 缓涨 ≪ 钳位；grad_norm 稳定；logprob 数值差稳定

## 4. dev→test 迁移幅度的讨论（诚实声明）

1. **噪声**：k=1 双侧 ±3pt 把 E3 test done +2.0pt 判入噪声带；k=3 复测收紧为 +4.2pt（95% CI [+0.2, +8.3]）——done 轴上修为弱阳性，但 CI 下沿贴 0，幅度仍小，r_hard 维持中性。**dev +7.5pt → test +4.2pt，迁移是打了折的，不是完全没有**
2. **分布差**：test 显著难于 dev（T4 done 0.875→0.750）；计划 §0 的回收上限估算（全回收 +17pt）基于 test 的 34 个新增失败，但其中 14 个"开页没买"在 E3 test 上并未被里程碑分救回（k=3 下同样是三次全零的 14 个任务，见 §1b）——dev 上学到的"及时收手"迁移到 test 的难任务时，收手点仍偏保守
3. **与 R1/R2 的对照权重**：三次 shaping 实验中两次（R1/R2）行为不动、一次（本次）dev 动、test 微动——"本 stack 上 reward shaping 推 test 泛化的幅度有限"的先验被进一步加固；E1b 进一步表明收益形态是 shaping × thinking 交互，单独调信号的空间更小
4. **数据侧路线**（计划 §0 证伪后的备选）因此保持推荐主线：SFT 混入"近似即下单"示范 / T4 rollout 偏好对，直接教行为而非靠信号挤

## 5. 产物索引

| 内容 | 路径 |
|---|---|
| 冠军模型（E3） | `runs/qwen35_2b_shop_rl_commit_e3/`（终版 `hf/rollout_99` + `checkpoints/iter_0000099`） |
| E1 / E2 / E1b 模型 | `runs/qwen35_2b_shop_rl_commit_e1/`、`runs/qwen35_2b_shop_rl_commit_e2/`、`runs/qwen35_2b_shop_rl_commit_e1b/`（终版同上；E1/E2 中期存档已 prune，E1b 待 prune） |
| 评测 | `runs/qwen35_2b_shop_eval_commit_e{1,2,3}_dev/`、`runs/qwen35_2b_shop_eval_commit_e1b_dev/`、`runs/qwen35_2b_shop_eval_commit_e3_official/`、k=3 复测 `runs/qwen35_2b_shop_eval_{commit_e3,rl_thinking}_official_k3/` |
| 阶段报告/脚本/单测/重放 | `commit-shaping/`（t1~t5 报告、run_e{1,2,3}.sh、run_e1b.sh、eval_*.sh（含 k3 与 e1b）、k3_compare.py、test_reward_shaping.py、replay_t4_dump.py + replay_t4_result.json） |
| 代码 | `pi-slime-shopsimulator` 仓库 `commit-shaping` 分支：`reward_shaping.py`（组件式变体）、`pi_harness.py`（动作序列采集）、`generate.py`（统计进 metadata）、`run_rl.sh`（8 个新 knob 透传）；`run_eval.sh` 刻意不动（评测 shaping 结构性关闭） |
| SwanLab | 项目 `@Luan_Fuzi/pi-slime-shopsimulator`（E1/E2/E3/E1b 四 run 实时记录；E0 冒烟未同步） |

## 6. 后续选项（按推荐序）

1. **数据侧路线**（仍为推荐主线）：SFT 混入"近似即下单"示范，直接教行为——k=3 已把 done 判成弱阳性（+4.2pt），但 turn_limit 未动、14 个全零任务顽固，大头收益仍在数据侧；E1b 归因建议数据侧与部署均锁定"思考开"
2. ~~k=3 复测收紧~~ **已完成（2026-09-06）**：done +4.2pt 站住（CI 刚不含 0），叙事由"未复现"修正为"弱阳性"（§1b）
3. ~~E1b 无思考对照臂~~ **已完成（2026-09-06）**：无思考下 milestones 无效（−1.0pt，CI 含 0），收益为 shaping × thinking 交互（§2b）
4. 归档决策：E1/E2 终版 checkpoint（各 7.6G）在不再需要复跑时可删，E3 冠军保留；E1b 中期存档（~15G）待 prune（权限模式拦截了 rm，待用户处理）
