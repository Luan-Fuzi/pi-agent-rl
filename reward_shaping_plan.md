# Reward 修改实施计划：基于 ASIN 审计的三项训练侧修复

日期：2026-09-01
项目：`pi-slime-shopsimulator`（Qwen3.5-2B + Pi + Slime + ShopSimulator，SFT → 在线 GRPO）
前置文档：`/root/autodl-tmp/asin_audit_report.md`（本计划是其第 6 节建议的落地）
性质：**只改训练侧 reward，不动环境、不动评测**。改动总量 <100 行，集中在 1 个文件 + 2 个小脚本。

---

## 1. 背景：审计发现的三类错位

本计划针对 ASIN 审计（见前置文档）在 `official_test_200` 上发现的三类 reward 失真：

| # | 审计发现 | 影响面 | 后果 |
| --- | --- | --- | --- |
| F1 | **规格落空代价低**：属性+价格匹配即可撑起 0.5~0.83 分；"买错但高分"47 条中 36 条 r_option=0；"买对但没满分"22 条全部只栽在 r_option | 约 10% 任务 | reward 系统性高估，规格选择短板被训练信号放任 |
| F2 | **价格约束脱节**：price_upper 由 goal 商品价向上采样生成（`goal.py:83-88`），不读指令预算；18.5% 的购买超指令预算仍 r_price=1（极端 5 倍超预算拿满分） | official_test 池 27.2% 任务严重冲突，全量 19.0% | r_price 指标掺水，模型在两成任务上面临"听指令还是听 reward"的矛盾 |
| F3 | **脏数据/错标**：脏价格（task 547 goal 价 38 万、734 约 96 倍冲突）、goal 商品错标（task 405） | 少量任务 | reward 信号本身错误，模型只能学到拧巴的折中 |

fuzzy 规格误判（task 1058 类，同义规格串匹配不上）**不在本计划修复范围**：metadata 中无买入规格串，训练侧无法可靠重判，作为上游数据反馈记录。

## 2. 设计原则（三条红线）

1. **只改训练侧，不动环境**。唯一入口 `slime/examples/ShopSimulator/generate.py:275`。环境是第三方打补丁仓库，且环境分一动，全部历史数字与 baseline 可比性作废。
2. **shaping 只对"组内相对差异"有意义**。GRPO 组内减均值，每项修改必须回答"它在同任务 4 条 candidate 之间制造了什么新排序"。
3. **原始分必须可复盘**。覆盖 reward 前把环境原始分写入 metadata；评测永远用环境原始分。

## 3. 修复方案

### Fix 1：规格对齐门控（治 F1）

位置：`generate.py:275`，约 3 行。`result.reward_detail` 已在此处可用（现代码 288 行在用），无需任何外部表。

```python
# 现状
reward = float(result.reward) if result.done else 0.0

# Fix 1
reward = float(result.reward) if result.done else 0.0
if result.done and result.reward_detail:
    reward *= 0.5 + 0.5 * float(result.reward_detail.get("r_option", 1.0))
```

效果：r_option=0 的轨迹分数减半，组内"规格选对"被系统性排到"规格落空"前面。无规格任务 r_option 恒 1，公式自然退化，不受影响。门控系数 0.5 是消融点（备选：0.25/0.75，或重合成公式 `(attr_hits + w_opt·opt_hits + r_price)/(n_attr + w_opt·n_opt + 1) × r_type`，w_opt=2，需预查 goal 表）。

### Fix 2：按指令预算收紧 r_price（治 F2）

两张小表 + `generate.py` 约 20 行（含加载）。

**离线导出**（约 20 行，复用审计代码）：

- `task_budget.json`：`task_id → 指令预算`，由审计的预算提取器对重建 goal 的 instruction_text 跑一遍导出（无预算表述的任务不收录，训练侧保持现状）；
- `prices.json`：`asin → 确定性价格`，审计已产出（`runs/asin_audit/prices.json`，23,421 条），直接复用。

**训练侧逻辑**（`generate.py`）：

```python
# 模块级（约 10 行）：_BUDGETS / _PRICES 懒加载，路径走环境变量，缺表则 Fix 2 自动跳过

# 275 行处（约 8 行，在 Fix 1 公式中把 r_price 换成 r_price_instr）
budget = _BUDGETS.get(task_id)
if budget is not None and result.reward_detail:
    price = _PRICES.get(result.purchase_asin)
    if price is not None and price > budget * 1.1:
        # 用 r_price_instr=0 重合成该轨迹的 shaped reward
```

只收紧、不放松：env 侧偏紧的 19 个反向任务不动。容差 1.1 是因为"40 元左右"是软表述，且防预算提取误差误伤（消融点：1.0/1.2）。

### Fix 3：脏任务黑名单（治 F3）

**训练代码零改动**。独立脚本（约 20 行）：按严重程度阈值（如 goal 价 > 指令预算 × 10，叠加人工复核清单 task 547/734/250/405 等）过滤 `rl_500.jsonl`，生成新任务文件，`run_rl.sh` 指向新文件即可。

附带收益：这些任务奖励极低或矛盾，剔除后零方差组比例下降，与 curriculum 方向天然合流。

## 4. 两个必须做的保护（各一行，漏了会出事）

1. **shaping 开关默认关**：`run_eval.sh` 与训练共用 `generate.py`，shaping 必须门控（如 `os.getenv("SHOP_REWARD_SHAPING") == "1"`，`os` 已 import）。训练开、评测关，否则评测数字被污染。
2. **原始分留存**：覆盖 reward 时在 `extra_metadata` 加 `"env_reward_raw": float(result.reward)`（当前 metadata 只有 `reward_detail` 子分，没有环境总分）。

## 5. 改动地图

| 项 | 动 `generate.py` | 动训练框架/环境 | 离线脚本 | 预估 |
| --- | --- | --- | --- | --- |
| Fix 1 规格门控 | ~5 行 | 否 | 不需要 | 0.5 h |
| Fix 2 预算收紧 | ~20 行（含表加载） | 否 | ~20 行（预算表导出，复用审计代码） | 2~3 h |
| Fix 3 黑名单 | 0 | 否 | ~20 行（过滤任务 jsonl） | 0.5 h |
| 保护措施（开关 + 原始分） | 2 行 | 否 | 否 | 含在 Fix 1 内 |
| shaping 函数单元自测 | 合成样本直接调函数验证 | — | — | 1 h |
| **合计** | **<30 行** | — | **<50 行** | **约 1 天人力** |

审计已备好全部原料：goal 重建表（`runs/asin_audit/goals_reconstructed.json`）、价格表（`prices.json`）、预算提取器（`budget_conflict.py`）、验收工具（象限统计，`audit.py`）。

## 6. 实验矩阵

对照现有 GRPO baseline（R0，已有 run + 评测）。每个变体一次训练 run（与既有 GRPO 同成本，可砍到 50~70 step 控制预算）+ dev 子集评测：

| 变体 | 配置 | 检验的假设 |
| --- | --- | --- |
| R1 | Fix 1 | 规格门控 → r_option、right_product 升 |
| R2 | Fix 1 + Fix 2 | 预算收紧 → 预算合规率升，高分规格落空率降 |
| R3 | Fix 2 + Fix 3 | 剔除脏任务 → 零方差率降，同预算有效梯度升 |

纪律：单变量递进；变体间比较全部在 **dev 子集**；`official_test_200` 只测最终版一次；评测协议与历史完全一致（k=1，环境原始分）。

## 7. 验证指标（用审计语言定义成功）

不看 r_loose 绝对值（收紧后可能自然下降），看审计定义的四把尺：

| 指标 | 基线（RL 现状） | 预期方向 |
| --- | ---: | --- |
| 预算合规率（购买 ≤ 指令预算×1.1 的比例） | 81.5% | ↑ |
| r_option | 0.334 | ↑ |
| right_product_rate | 37.5% | ↑ |
| 高分规格落空率（reward≥0.5 且 r_option=0 且有规格要求） | 18%（36/200） | ↓ |

副作用监控：零方差组占比（约束变紧会变稀疏）、done_rate、平均轮数。

## 8. 风险与对冲

| 风险 | 说明 | 对冲 |
| --- | --- | --- |
| reward 变稀疏 → 零方差组增多 | 约束收紧后 4 条 candidate 更易同分 | R3 黑名单剔除绝望任务；必要时上 curriculum 或拉长 step |
| 预算提取误差误伤 | 启发式正则，个别任务提取错 | 1.1 容差；只收紧不放松；黑名单人工复核 |
| R2 指标不动 | 大概率是有效梯度不足而非修复错误 | 负结果也有明确下一步（curriculum / 更多 step），如实写进报告 |
| 与 advantage 归一化耦合 | std 归一化下系数强度是相对的 | shaping 消融与去 std 消融分开做，不混变量 |

## 9. 时间线估算

- D1：Fix 1 + 保护措施 + 单元自测；预算表导出；Fix 2 实现；冒烟（短 step，确认 shaped reward 进日志、原始分进 metadata）
- D2 起：R1/R2/R3 训练 run（卡时为主）+ 每 run 后用审计脚本出验收表
- 收尾：dev 对比表 + 最终版 official_test 一次性评测 + 报告

## 10. 产物归属

| 内容 | 路径（计划） |
| --- | --- |
| shaping 逻辑（全部） | `pi-slime-shopsimulator/slime/examples/ShopSimulator/reward_shaping.py`（新模块） |
| shaping hook（3~4 行门控） | 同上仓库 `generate.py:275` 处 |
| 预算表 / 价格表 / 黑名单任务文件 | `runs/reward_shaping/{task_budget.json, prices.json, rl_500_clean.jsonl}` |
| 各变体训练/评测产物 | `runs/qwen35_2b_shop_rl_r{1,2,3}/`、`runs/qwen35_2b_shop_eval_rl_r{1,2,3}/`（R0 基线 `runs/qwen35_2b_shop_rl/` 封存不动） |
| 验收分析 | 复用 `runs/asin_audit/audit.py`、`budget_conflict.py`（该目录只读，作审计存档） |

## 11. 隔离与可逆性方案

原则：**不做任何破坏性改动**——不改已有文件的行为默认值，不原地编辑任何数据文件，不碰环境仓库；多次迭代靠 env 选变体，不靠改代码。

- **代码隔离**：shaping 全部逻辑收进独立新模块 `reward_shaping.py`；`generate.py` 只加 3~4 行门控 hook。变体与系数（门控权重、预算容差、表路径）由 env/配置决定：`SHOP_REWARD_SHAPING=off|option_gate|budget|full`，默认 `off` 即原行为（评测与 baseline 复现零影响）。实验变体 = 配置差异，任意一轮可精确重放。
- **git 隔离**：在 `reward-shaping` 分支上工作（`git switch -c reward-shaping`），main 保持干净；仓库现存的 5 个本地修改（`run_rl.sh` 等）随工作区带入分支，保留不动。
- **产物隔离**：原料与中间产物集中放 `runs/reward_shaping/`；每个变体独立 `RUN_ROOT`；黑名单任务文件放 `runs/` 而非仓库 `data/tasks_v2/`；`runs/asin_audit/` 只读。
- **环境隔离**：ShopSimulator 仓库（detached HEAD + 补丁）完全不碰。
- **回滚路径**：不设 env 变量 = 原行为；删 `runs/reward_shaping/` 与各变体目录 = 清掉全部产物；`git switch main` = 离开分支。三层互不依赖。

## 12. 一句话叙事

审计发现三类 reward 错位（19%~27% 任务受影响）→ 设计三种训练侧修复（<100 行，不动环境）→ 用同一套审计方法闭环验证：预算合规率、规格落空率、right_product 的迁移。发现问题、修复问题、闭环验证，三段均有据可查。
