# Thinking 蒸馏方案 v2：默认档思考捕获 → 新 SFT → GRPO

日期：2026-09-03（v1 写于 2026-09-02；v2 吸收 T1 修订实验的全部结论）
状态：**全部完成，判据判正**。T5 双集终判：dev_200 r_hard 0.662（对 R2 +4.9pt）、official_test_200 0.385（+6.6pt），双过 +3pt 预注册线；消融阶梯与机制归因见终稿 `runs/thinking_sft/report.md`。阶段报告：t0/t1/t15/t3/t4 于本目录
前置文档：`thinking-distill/t1_pilot_report.md`（修订版，七臂实验）、`runs/reward_shaping/badcase_analysis.md`（§5 思考通道核查）

## 0. 目标与核心假设（不变）

用带思考的教师轨迹构建新 SFT 数据集（思考落在 `<think>` 区内），蒸馏给 Qwen3.5-2B，再接同配置 GRPO，验证：

> **假设**：2B 模型学不会"下单前约束核对"的根因是思考通道从未启用（R2 官方测试 43,390 个 think 块 100% 为空），而非容量不足。给它位置正确、风格统一、覆盖率拉满的思考示范后，r_option / r_hard / r_success 应显著上升。

**证伪条件**（预先声明）：新 SFT+GRPO 在 dev_200 上 r_hard 相对 R2 无提升 → 结论"2B 容量或任务结构不支持思考迁移"，转入 OPD 或放弃思考路线。

**v2 相对 v1 的关键变化**：T1 增补实验证明教师的思考在**默认档**下就完整存在（98% turn、中位 442 字符、50% 含约束核对词），且强制 `reasoning_effort` 反而把覆盖率从 79% 打到 46~54%（max 档 21%）。更重要的是**存量核查：既有 `runs/shop_sft_512/raw/` 的 512 条原始轨迹里，96.7% 的模型 turn 在 events 中保留了完整思考（accepted 的 414 条达 97.0%，零条完全无思考；1590 个选规格/buy 关键 turn 中 96.3% 带思考、51.4% 含约束核对词、仅 2.3% 极短）**。因此 T2 取消重新采集，改为**离线重建**：从既有 raw 直接重新导出保留 thinking 的 SFT 数据，零 API 成本，行为分布与既有 SFT/RL 完全同源。重采仅作质检不过的兜底。

## 1. 证据链（含 v1 后新事实）

1. r_hard 低的直接原因：92/99 条归零样本栽在 r_option=0（badcase §1-2）
2. 轨迹级归因：71% 是"正确答案在眼前但没选中"——候选核对动作缺失（§2-3）
3. 思考通道三层核查：SFT 教师数据的思考**被导出层剥离**（初版判断"教师没开 reasoning"已被推翻——教师一直在思考，usage 实证 74~84% output 是 reasoning）；2B 模型 think 块 100% 为空
4. 七臂剂量实验（t1_pilot 修订报告 §3-4）：打转与思考无关（disabled 零思考同样 79%），与"强制固定 effort"单调相关；`reasoning_effort` 连思考长度都控制不了
5. 默认档思考一直在 `events` 里完整落盘，旧管线只在导出时剥掉——思考数据是免费存量

## 2. 改动点（7 处，全部 env 门控、默认行为不变）

| # | 位置 | 改动 | 阶段 |
|---|---|---|---|
| 1 | `pi_harness.py` | `SHOP_PI_THINKING` 档位开关（含 `disabled`、`max` 直传，均已在 T1 落地） | 已完成 |
| 2 | `collect_sft.py` | thinking part 保留开关 | 已完成 |
| 3 | `collect_sft.py` | 新增 `SHOP_PI_THINKING=default` 语义（pi 侧 off、导出侧保留 thinking）——**仅兜底重采时需要**；主路径是 T2 离线重建，不经过 pi | 仅兜底 |
| 4 | `prepare_sft.py:38` | thinking part → `reasoning_content` 字段（T0 验证的路径 A）；events↔messages 对齐校验 + dotfile 过滤 | 已完成 |
| 5 | `adapters/common.py:66` | rollout 渲染传 `enable_thinking=True`（`SLIME_ROLLOUT_THINKING` 门控，已加入 run_eval/run_rl 的 RUNTIME_ENV 透传） | 已完成（待 T4 冒烟） |
| 6 | `pi_harness.py` / run_eval | 系统提示 env 覆盖开关（P0 探针用，如 `SHOP_SYSTEM_PROMPT_FILE`） | P0 |
| 7 | rollout 上下文一致性 | RL 侧确认 2B 模型的历史思考不累积进 context（对齐 pi wire 行为与 SFT 数据形态）。已闭环：`--sglang-reasoning-parser qwen3` 两个启动脚本本就有；adapter `openai.py:260-263` 的 manager_message 设计为不带 reasoning_content（与 pi 回显一致，轨迹树匹配不断链）；SFT 数据历史无思考。待 T4 冒烟实测复核 | 已闭环（待 T4 冒烟） |

**不改的**：ShopSimulator 环境仓库、GRPO 算法配置、任务文件、评测口径、reward（与 reward shaping 正交，不混合）。

## 3. 阶段拆解

### P0：提示词探针（约 1 小时 GPU，先做这个）

拿 R2 checkpoint（`runs/qwen35_2b_shop_rl_r2/hf`），系统提示加"下单前必须列出指令约束（数值/数量/型号）并与所选规格逐项核对"，dev_200 评一次（口径与历史完全一致）。

- 若能唤起核对行为（r_option/r_hard 上升）→ 能力在、只是没被触发，SFT 注入胜率大
- 若唤不起 → 行为不在分布里，更要靠 SFT 硬注入，但 2B 消化风险上升
- 两种结果都指向行动；此探针也给 T5 提供"提示词 vs 训练"的对照点
- 产物：`runs/reward_shaping/p0_prompt_probe/`（或独立 eval 目录）+ 一页结论

### T1.5：存量思考质检 + 重建链路打通（约 0.5 天，无 GPU）

- **质检门**：从 `runs/shop_sft_512/raw/` 的 414 条 accepted 轨迹（即真正要进炉的语料）抽 20 条人工读思考：是"约束核对"还是"动作宣告"？重点看 buy/选规格 turn。不达标才考虑重采（且用默认档，不用强制档位）
- 写离线重建脚本（纯 stdlib，约 50 行）：遍历既有 raw/*.json → events 重建 messages 时**保留 thinking part** → 复用 `evaluate_candidate` 重新过滤 → 输出 `accepted_thinking.jsonl`。不碰 pi、不调 API
- 改动 #4 落地：`prepare_sft.py` 产出带 `reasoning_content` 的 turn 样本；用真实 tokenizer 渲染 + mask 抽查（沿用 T0 方法：思考正文计梯度、壳不计）
- 验收：重建 smoke 通过；渲染/mask 抽查表写入 `t1.5_report.md`

### T2：离线重建 SFT 数据（约 2~3 小时，纯 CPU，零 API 成本）

**不重新采集**。从 `runs/shop_sft_512/raw/` 既有 512 条原始轨迹离线重建：

- 用"保留 thinking"逻辑重新导出 `accepted_thinking.jsonl`（events → messages 时不再剥 thinking part；`evaluate_candidate` 过滤条件不变，预期仍是 414 条 accepted）
- 改动 #4 落地：`prepare_sft.py` 把目标 turn 的 thinking 写入 `reasoning_content`，**历史 turn 的思考必须剥掉**（对齐 pi wire 行为：教师自己看不到历史思考，SFT 数据必须同形态，否则训推失配）
- 输出 `runs/thinking_sft/`（新目录，不动 `runs/shop_sft_512/`）
- 验收：turn 样本量与原版同量级（原版 6357 条）；思考长度分布合理（中位 295 字符，p10 62 / p90 1131）；`t2_collect_report.md`
- **兜底**（仅当 T1.5 质检判定默认档思考不可用）：才回到重新采集，且仍用默认档而非强制档位

### T3：新 SFT（约 3 小时 GPU）

- 训练配置与旧 SFT 完全一致（同超参同 epoch），新 RUN_ROOT `runs/qwen35_2b_shop_sft_thinking/`
- 数据质检：思考长度分布、人工抽读 20 条防"复读指令"伪思考
- 验收：loss 正常收敛；dev_200 快评一次（SFT sanity check）：done 率不显著低于旧 SFT（75%），think 块非空率 >90%
- `t3_sft_report.md`

### T4：新 GRPO（约 8~12 小时 GPU，思考可能膨胀到 1.5~2 倍）

- 从新 SFT checkpoint 起跑，配置逐项对齐 R0（rl_500、100 step、同超参、原始 env reward）
- 改动 #5 落地并确认 #7（历史思考不进 context）
- 监控：rollout 时长、truncated 率、think 非空率是否随训练保持、2B 思考长度是否挤压 2048 response 预算
- `t4_rl_report.md`

### T5：评测与对比（约 5~6 小时 GPU，主线两集 + 消融两集）

- dev_200 与 official_test_200 同轮各评新 GRPO 一次（同口径、shaping OFF；2026-09-03 用户决定两集都出数，不再设 test 门槛）
- 判据预先钉死（三态）：dev、test 的 r_hard 分别相对各自 R2 基线（0.613 / 0.319）≥+3 点（超 k=1 噪声）→ 正结果；两集均不达标 → 负结果；一涨一不涨 → 记"不确定"。三态都如实写，不挑有利口径、不事后合理化
- dev 侧与 R0/R1/R2/P0 四方对比；test 侧与 R2 official 基线对比
- 消融（2026-09-03 用户增补，仅归因不作裁判）：base + thinking 与 新 SFT + thinking 各在 official_test_200 评一次（base 不开思考已有 test 成绩 r_hard 0.0 / done 5%；新 SFT 已有 dev 成绩 0.572）。headline 判据不变——消融数字如实摆，即使新 SFT 噪声性超过 T4 也不用来替换最终模型
- 归因：复用 badcase 分类脚本统计 B/D 类修复率
- 终稿写入 `runs/thinking_sft/report.md`，回填本计划与 reward_shaping/report.md 的后续方向

## 4. 风险登记（v2 更新）

| 风险 | 等级 | 缓解 |
|---|---|---|
| 2B 学成伪思考（复读指令） | **高（核心证伪点）** | T3 质检人工抽样；SFT 后快评人工读 5 条 rollout；证伪条件预先声明 |
| 存量思考质量不足（8/31 的思考比 9/2 短：中位 295 vs 442 字符） | 中 | T1.5 质检门直接抽读存量语料；不过才回退重采 |
| 历史思考残留导致训推失配 | 中 | prepare_sft 必须剥掉历史 turn 的思考（pi wire 行为已实证：历史不回传）；重建后抽查 context 一致性 |
| rollout 思考烧 token 变慢 | 低 | 接受 1.5~2 倍时长，不砍 step（保持与 R0 可比） |
| 思考挤压 2048 response 预算 | 低 | pilot 实测思考中位 ~300 token/turn，余量充足；T4 监控 finish_reason=length |

## 5. 时间与资源预算

| 阶段 | 时长 | 资源 |
|---|---|---|
| P0 提示词探针 | ~1 小时 | 单卡 |
| T1.5 质检+重建链路 | ~0.5 天 | 无 GPU |
| T2 离线重建 | ~2~3 小时 | 纯 CPU，零 API |
| T3 SFT | ~3 小时 | 单卡 |
| T4 GRPO | ~8~12 小时 | 单卡 |
| T5 评测（主线两集 + 消融两集） | ~5~6 小时 | 单卡 |
| **合计** | **约 1.5~2 天** | |

## 6. 产物与隔离约定（不变）

- 代码：`thinking-distill` 分支（从 `reward-shaping` 切出）；所有开关 env 门控、默认 off，旧路径行为不变；main 始终干净
- 产物：`runs/thinking_sft/` 与新 RUN_ROOT；`runs/shop_sft_512/`、`runs/reward_shaping/` 只读
- 每阶段结束写阶段报告；git 提交/推送前必须先经用户确认

## 7. 成功判据汇总

| 阶段 | Go 条件 |
|---|---|
| P0 | 任何结果都继续（信息探针，非门） |
| T1.5 | 质检通过：buy/规格 turn 思考是真核对；链路 smoke 2/2 |
| T2 | 重建产出 turn 样本 ≥ 原版 90%（5700+）；关键 turn 思考覆盖率 ≥95%（存量实测 96.3%，重建后复核）；人工抽读 20 条通过 |
| T3 | loss 收敛；dev 快评 done 率 ≥70%、think 非空率 >90% |
| T4 | 训完 100 step；think 非空率保持 |
| T5 | **终点判据：dev_200 与 official_test_200 同轮各评一次；r_hard 分别相对 R2 基线（0.613 / 0.319）≥+3 点为正，双不达标为负，一涨一不涨记不确定，如实收尾** |
