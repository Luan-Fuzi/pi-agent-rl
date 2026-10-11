# T1 Pilot 报告（修订版）：教师思考采样验证 + 档位机制实验

日期：2026-09-02（同日修订：初版只含 medium/low 两臂；修订纳入 base 同日重跑、wire 抓包、disabled / high / 真·max 补充臂，并推翻初版三处结论）
分支：`thinking-distill`（改动未提交）
产物目录：`/root/autodl-tmp/thinking-distill/t1_pilot/`（smoke/、full/=medium、low/、base/、max/=实为high、max2/=真max、disabled/）、`wire_probe/`
分析脚本：`analyze_pilot.py`（打转行为）、`analyze_pilot2.py`（goal join）、`analyze_pilot4.py`（七臂对比）

## TL;DR（修订）

思考蒸馏的**内容假设依然成立**（教师思考确实在做约束提取与规格核对），但初版的机制判断和 T2 参数被同日增补实验推翻：

1. **"开思考"从来不是从 0 到 1**：`--thinking off` 的默认采集根本没关思考——pi 一个 thinking 参数都不发，v4-flash 服务端默认开思考，教师 74% 的 output token 是 reasoning（初版"base reasoning=0"系按导出消息统计的误报）。
2. **真正的变量是"是否强制固定 reasoning_effort"，而非思考有无**：真·关闭档（`thinking:{disabled}`，零思考）与默认档成功率完全相同（19/24 vs 19/24）；而任何显式档位掉到 46~54%，且存在剂量效应——low 54% > medium 50% > high 46% > max 21%（max vs medium 配对 7:0）。失败全部表现为 40 轮打转。
3. **T2 方案改写**：默认档的思考内容 98% 的 turn 都在、且一直在 `events` 里完整落盘（初版管线只在导出时剥掉了）。新方案候选：**默认档采集 + 导出保留 thinking part**，预期覆盖率 ~80%（原方案 medium×2 发预期 ~67%），行为分布与既有 SFT/RL 完全同源。T2 前先人工抽读 10~20 条默认档思考做质检。

## 1. 代码改动（全部 env 门控，默认 off = 旧行为）

| 位置 | 改动 | 状态 |
|---|---|---|
| `pi_harness.py` run_pi | `SHOP_PI_THINKING` 控制 `--thinking` 档位 + models.json `reasoning`/`supportsReasoningEffort` | 初版 |
| `collect_sft.py` `thinking_enabled()` | on 时 `authoritative_messages` 保留 thinking part | 初版 |
| `collect_sft.py` `context_snapshots` | 历史 assistant 消息剥掉 thinking part（对齐 pi wire 行为） | 初版 |
| `collect_sft.py` 元数据 | `teacher.thinking` 记录档位字符串 | 初版 |
| `pi_harness.py` models.json | 加 `thinkingLevelMap: {"max": "max"}`：**否则 pi 的 `getSupportedThinkingLevels` 把 max/xhigh 排除出支持列表，`--thinking max` 被 clamp 成 "high"**。初版"max"臂（目录 `t1_pilot/max/`）实际发的是 high，已用抓包证实并重跑真 max（`max2/`） | 修订新增 |
| `pi_harness.py` | 新增特殊档 `SHOP_PI_THINKING=disabled`：模型注册 reasoning:True + CLI `--thinking off` → pi 发送 `thinking:{type:"disabled"}`，服务端真关闭。与默认 "off"（不发任何参数、服务器默认开思考）形成对照 | 修订新增 |

**smoke 发现的坑**（仍有效）：pi 在后续请求里**不回传历史思考**（wire 上历史 assistant 无 thinking part），重建快照若保留思考则全部 context_trace_mismatch。修复后 smoke 2/2 通过。附带含义：教师每轮独立思考、看不到自己过去的思考——SFT 数据应按此形态准备（历史无思考、目标 turn 有思考）。

## 2. Pilot 设计

24 任务（固定种子 20260902 从 **sft_512** 抽样：12 条多规格 option_count≥2 + 12 条单规格）。除档位外参数全同（max_turns=40, timeout=600, max_tokens=32768, concurrency=4, samples-per-task=1）。**每臂每任务单发**（k=1）。

| 臂 | 目录 | 采集日 | 实际发送（wire 抓包实证） |
|---|---|---|---|
| base_old | `runs/shop_sft_512/` | 8/31 | 无 thinking 参数（服务器默认思考） |
| base_new | `t1_pilot/base/` | 9/2 | 同上，同日重跑对照 |
| disabled | `t1_pilot/disabled/` | 9/2 | `thinking:{disabled}`（真关闭） |
| low / medium / high | `t1_pilot/{low,full,max}/` | 9/2 | `thinking:{enabled}` + `reasoning_effort: low/medium/high` |
| max（真） | `t1_pilot/max2/` | 9/2 | 同上，`"max"`（打 thinkingLevelMap 补丁后） |

抓包旁证：thinking 模式下 prompt_tokens=118，disabled 下=39（服务端换了非思考模板）；off_legacy 响应仍含 reasoning_content，disabled 不含。除 thinking 参数外请求体逐字节一致（无温度、无额外消息）——**harness 开关逻辑无 bug，行为差异来自服务端对参数的真实响应**。

## 3. 七臂全景

| 臂 | accepted | 40轮打转失败 | 平均turns | 总reasoning tok | 每turn中位 |
|---|---:|---:|---:|---:|---:|
| base_old（8/31） | 20/24 (83%) | 4 | 21.5 | 80k | 77 |
| base_new（9/2） | 19/24 (79%) | 5 | 21.7 | 145k | 137 |
| disabled（零思考） | 19/24 (79%) | 3 | 17.8 | **0** | — |
| low | 13/24 (54%) | 11 | 24.4 | 150k | 84 |
| medium | 12/24 (50%) | 12 | 26.7 | 135k | 100 |
| high（初版"max"臂） | 11/24 (46%) | 13 | 27.2 | 133k | — |
| max（真） | **5/24 (21%)** | 19 | 33.2 | 125k | — |

配对检验（McNemar 不和谐对，χ²）：

| 对比 | 结果 | χ² |
|---|---|---:|
| base_new vs base_old | 2:3 | 0.20（无漂移，旧基线有效） |
| base_new vs disabled | 4:4 | 0.00（**零思考 ≡ 默认档**） |
| base_new vs low / medium | 7:1 / 8:1 | 4.50 / 5.44（p<0.05） |
| disabled vs medium | 7:0 | 7.00 |
| medium vs high | 3:2 | 0.20（低中高三档无差异） |
| medium vs max / high vs max | 7:0 / 6:0 | 7.00 / 6.00（max 显著更差） |
| base_new vs max | 14:0 | 14.00 |

逐任务结局矩阵（7×24）见 `analyze_pilot4.py` 输出；max 的失败集合 ⊇ medium 的（max 把 medium 通过的 7 个任务也打转掉，自身未多过任何一个）。

## 4. 机制结论（修订）：打转与"思考"无关，与"强制固定 effort"有关

初版把打转归因于"思考让教师变谨慎"，修订版用两个对照臂把它钉死：

- **disabled（零思考）与默认档成功率相同**（19/24，4:4）——思考本身不是变量；
- **失败率随强制档位单调恶化**（54%→50%→46%→21%），而思考 token 量与成功率**无关联**（base_new 每 turn 中位 137 > medium 100；default 与 disabled 思考量差无穷倍但成功率相同）——"想得多所以打转"不成立。

当前最自洽的解释：v4-flash 服务端默认是**自适应思考**——模型自己决定每轮想多少、何时收摊；显式 `reasoning_effort` 强制每轮按固定强度推理，在下单决策点把"信息不全也先收摊"的自适应校准覆盖掉，在不可证实约束上陷入验证循环，且强度越高陷得越深。

打转轨迹的行为解剖（与初版一致，数据未变）：

- 失败 100% 是 40 轮封顶的"不下单"；medium 12 条失败中 **9 条在前 6 轮就访问过 goal 商品**，之后 17~37 轮反复验证不买；
- "思考里宣告满足/找到、下一动作仍不是 buy"：失败轨迹 41 次 vs 成功轨迹 14 次；
- 案例分叉：task 16907，base 与 medium 前 4 个动作完全相同（同商品同变体同 description 页），第 5 动 base `buy now`（17 轮满分），medium `back to search`（之后 8 轮循环不买）；
- 打转触发点集中在**环境不可证实或自相矛盾的约束**：5160（指令"价格不低于一万" vs goal 商品 6090 元）、3387（选项未标光色）、16907（188 元 vs "180 左右"）；
- 打转解剖：前半程动作重复率 ~0.2（正常探索），后半程 ~0.47（循环）；失败轨迹思考量约为成功轨迹 6 倍（31k vs 5.5k 字符）——**成本大头全烧在打转轨迹上**。

各臂失败形态差异：base/disabled 打转率 3~5/24 且 disabled 多出"快速失败"（6/11 轮 r=0，零思考的粗心单）；强制档位打转率 11~19/24。

## 5. 覆盖率经济学（修订）

| 并集 | 覆盖 |
|---|---:|
| medium ∪ low | 16/24 |
| medium ∪ low ∪ high（初版max） | 17/24（第 3 发只多捞 1 个） |
| **base_new ∪ disabled** | **23/24** |
| 全部七臂 | 23/24 |

- 思考三臂全败的 7 任务：3387, 10222, 12202, 15716, 16742, 20554, 22719——其中 6 个 base 臂能过，多为指令-环境矛盾/不可证实类；
- 思考臂独有的战绩：2991（两个 base 臂都打转，medium 7 轮满分、low 4 轮 0.88）——思考在部分任务是纯增益；
- 唯一七臂全败任务：10222；
- 单发方差大：medium vs low 翻转 7/24；12202 在 base_old（14 轮满分）与 base_new（40 轮打转）之间隔日翻转。**边际任务结局本身就是抛硬币，任何单发臂的 ±2~3 个任务都在噪声内**。

## 6. Token 与成本（修正）

初版"原版 reasoning=0"系误报（按导出消息的 thinking part 统计；默认档 thinking 在导出层被剥离）。按 usage 实测（24 任务）：

| 臂 | 总 output | 总 reasoning | 占比 |
|---|---:|---:|---:|
| base_old | 108k | 80k | 74% |
| base_new | 172k | 145k | 84% |
| disabled | 126k | 0 | 0% |
| medium | 174k | 135k | 78% |

注意 base_new 每 turn reasoning 中位较 base_old 近翻倍（77→137）而成功率不变（19 vs 20）——服务端默认思考强度可能有漂移，但对行为无影响；同时再次说明 token 量与成功率无关。

## 7. T2 方案（修订）

**初版方案**（medium × 每任务 2 发取并集，预期 ~67% 覆盖）作废。修订为：

1. **首选：默认档采集（`SHOP_PI_THINKING=off` 原配置）+ 导出保留 thinking part**。依据：默认档思考覆盖率 98% turn、长度中位 442 字符、50% 含约束核对词（medium 为 88%/408/51%，无实质差别）；成功率 79~83% 不受损；行为分布与既有 SFT/RL 完全同源（同一服务器默认模式）。所需改动一行级：把 `collect_sft.py` 的 `thinking_enabled()` 与 pi 档位解耦（如新增 `SHOP_PI_THINKING=default` 语义：pi 侧 off、导出侧保留）。
   - **前置质检门**：人工抽读 10~20 条默认档思考，确认是"约束核对"而非"动作宣告"（初版 badcase 分析发现旧 SFT 里 76% 规格选择无思考——那是导出剥离后的假象，但默认档思考的结构化程度仍需人工确认）。
2. 备选（若质检发现默认档思考质量不足）：回到 medium × 2 发并集（~67% 覆盖）；对 7 个"思考敌意"矛盾任务可用 disabled/off 档补行为数据（无思考可教，需分开记账）。
3. **档位调节路线正式封死**：low/medium/high 无差异且 max 显著有害；`reasoning_effort` 连思考长度都控制不了，对打转更无控制力。

2B 侧 token 预算结论不变：思考中位 ~250-300 token/turn，`max_response_len=2048` 余量充足。

## 8. 风险与开放问题（修订）

- 默认档思考的蒸馏价值待人工质检（见 §7 门）；若"自适应思考"里混有简略轮（部分 turn 只有一句话），需在 prepare_sft 侧决定短思考是否保留。
- 服务端默认行为是黑盒且可能漂移（8/31→9/2 思考量翻倍而行为不变）；采集方案越贴近默认档，受上游漂移的影响越直接——但这也是与既有训练数据同源的另一面。
- 7 个思考敌意任务与 ASIN 审计的"指令-goal 价格冲突"高度同源：环境里"认真读指令"在约两成任务上被 reward 惩罚。采集侧不处理，作为上游数据问题留档。
- 单日 k=1、n=24 的行为结论有噪声上限（±几个任务）；剂量曲线的两端（default/disabled 79% vs max 21%）显著，中间档位的精确排序不要求。

## 9. 产物清单（修订）

- 轨迹：`t1_pilot/{smoke,full,low,base,max,max2,disabled}/`（full=medium、max=实为 high、max2=真 max）
- 抓包：`wire_probe/{proxy.py,proxy_log.jsonl}`（四配置请求体 + 响应 usage；proxy 已停用）
- 分析脚本：`analyze_pilot.py`、`analyze_pilot2.py`、`analyze_pilot4.py`（七臂矩阵 + McNemar + 死因）
- 代码：`pi_harness.py`（档位开关 + thinkingLevelMap + disabled 档）、`collect_sft.py`（thinking 保留开关），均未提交
