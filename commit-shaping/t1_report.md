# T1 阶段报告：commit-shaping 实现 + 单测 + T4 dump 离线重放

日期：2026-09-04
分支：`commit-shaping`（从 `thinking-distill` 切出，工作区修改随分支带入）
性质：纯 CPU 阶段，未动 GPU；所有改动 env 门控、默认 off，逐位等于 T4 管线。

## 1. 三处改动（与计划 §2 对齐）

| # | 位置 | 实现 |
|---|---|---|
| 1 | `pi_harness.py` | `PiRunResult.actions`：pi stdout JSONL 的 `tool_execution_start` 事件**带 args**（`tool_execution_end` 不带，已查 pi 0.84.2 dist 源码确认），按 toolCallId 配对，仅记录非 error、非 terminal_noop 的 `shop_act` action 串。改动 #1 因此不需要碰 adapter——事件流天然带全量动作序列，比计划备选方案（manager_message 重建/debug callback）更简单 |
| 1 | `generate.py` | `finish_candidate_session` 处计算 `compute_process_stats(result.actions)`，传入 `shape_reward`；metadata 新增 `process_stats`（计数器）与 `action_sequence`（原始动作序列，供事后审计） |
| 2 | `reward_shaping.py` | 变体解析改为 `+` 分隔组件式（legacy token off/option_gate/budget/full 映射不变）；新组件 `milestones`（E1）、`antiloop`（E2）、`efficiency`（E3），可组合（如 `milestones+antiloop+efficiency`）；未知组件 **import 期报错**（fail fast，防配置笔误静默训练）；`compute_process_stats` 纯函数计数与 knob 解耦 |
| 3 | `run_rl.sh` | RUNTIME_ENV_JSON 透传 8 个新 knob；**`run_eval.sh` 刻意不动**——它从不转发 `SHOP_REWARD_SHAPING`，评测 worker 恒为 off，红线"评测 shaping OFF"由结构保证 |

## 2. 设计决策记录

- **REOPEN_FREE 默认 0**：计划 §3 E2 表格（"同一 asin 第 2 次打开起 -0.02/次"）与附文（"首次重开不罚"）相互矛盾。默认从表格（每次重开都罚），`SHOP_REWARD_REOPEN_FREE=1` 可切到附文语义，列为消融点。
- **里程碑分值走 env**：`SHOP_REWARD_MILESTONES`（默认 `0,0.05,0.10,0.15`），非法值 import 期报错。
- **E3 turns = model_turns**（adapter 口径的模型轮数，上限 40，与公式 /40 一致）。
- **antiloop 只罚非 done**（从里程碑分里扣、地板 0）；efficiency 只折 done；两者不交叉。
- **统计口径**：ASIN 点击 = `click[<纯数字>]`（23,421 件商品 ASIN 全数字已验证）；规格点击 = 非 asin/description/features/back/pagination/buy 的 click；搜索词按 strip+空白折叠+casefold 去重；loop back = 自上次 back 以来未开新 asin 的 back。
- **阶梯倒挂容忍**：重放发现 3/500 组存在"done 但 env 0 分/0.125 分"被非 done 里程碑反超（计划假设"done 最低约 0.2+"不总成立）。占比 0.6%，语义上可辩护（买错全 ≥ 没买接近 并不显然），E2 罚则进一步缩到 2/500。不处理，记录在案。

## 3. 单测（T1e）

- 新 `commit-shaping/test_reward_shaping.py`：**49/49 通过**（17 项 legacy 回归 + 32 项新增：stats 解析 7、里程碑 7、antiloop 5、efficiency 5、组合 3、变体解析 2、stats 边界 3）
- 旧 `runs/reward_shaping/test_reward_shaping.py` 对新模块：**18/18 通过**（向后兼容）
- 语法：generate.py / pi_harness.py / reward_shaping.py / run_rl.sh 全过

## 4. T4 dump 离线重放（T1f，`commit-shaping/replay_t4_dump.py` → `replay_t4_result.json`）

对象：T4 训练 dump（2000 candidate / 500 完整组）+ T4 official_test 评测 dump（200 candidate）。

### 4.1 解析器自证

- 动作数 vs `pi_tool_calls−1`：训练 10/2000、评测 1/200 偏差 >1（终端 noop/截断残差，可接受）
- **与计划 §0 归因数字精确互验**：test 非 done 50 条 = 42 turn_limit + 8 agent_stop ✓；试过 buy 7 条 = 6 turn_limit + 1 agent_stop ✓（计划原文 6/42 与 1/8）

### 4.2 触发率（核心检查）

| 集合 | 非 done | 里程碑 >0 触发 | 级别分布 0/1/2/3 |
|---|---|---|---|
| 训练 | 345 | **343（99.4%）** | 2 / 56 / 226 / 61 |
| test 评测 | 50 | **50（100%）** | 0 / 12 / 31 / 7 |

### 4.3 零方差率变化（核心假设）

| 变体 | 零方差组占比 | env 全零组（25 个）被拉出方差 |
|---|---|---|
| env 原始 | 235/500（47.0%） | — |
| E1 milestones | 215（43.0%） | **20/25（80%）** |
| E2 +antiloop | 216（43.2%） | 19/25 |
| E3 +efficiency | 87（17.4%） | 19/25 |

- E1 的机制精确命中设计目标：**全零组 80% 首次获得组内优势差**，而全局零方差率仅小幅下降（大部分零方差组是全 1.0 同分，本就不在 E1 射程）
- E3 的 17.4% 来自 efficiency 把"同分不同轮数"的 done 组也拉开（done 效率因子 mean 0.9918 / min 0.9375，温和）——注意这给"慢而对"制造了相对劣势，是计划内效果
- 罚则靶向面充足：训练非 done 345 条含重开 1247 次、重复搜索 557 次、loop back 663 次
- 注意：本次实测 env 零方差率 47.0%（完整组口径），高于计划 §0 引用的 34~36%——口径差异（是否含全 1.0 组/过滤组），前后对比自洽即可，不影响方向判断

## 5. 结论与下一步

T1 验收通过：三处改动完成且默认 off 逐位等于原管线；单测全绿；重放确认 E1 在全零组制造方差的机制成立、触发率近全覆盖、阶梯倒挂可忽略。

**T2 就绪**：E0 冒烟（核查过程统计进 metadata、shaping 触发进日志、训练链路无回归）。冒烟配置建议：`SHOP_REWARD_SHAPING=milestones+antiloop+efficiency` 全组件 + 短 step，一次跑完即删产物（磁盘纪律）。
