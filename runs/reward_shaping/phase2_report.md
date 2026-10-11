# 阶段 2 报告：Reward shaping 代码与单元自测

日期：2026-09-01
计划依据：`/root/autodl-tmp/reward_shaping_plan.md` 第 3~5 节
分支：`reward-shaping`（`pi-slime-shopsimulator`）

## 1. 产物清单

| 文件 | 内容 | 性质 |
| --- | --- | --- |
| `slime/examples/ShopSimulator/reward_shaping.py` | shaping 全部逻辑（新模块，115 行，纯 stdlib） | 仓库新增（分支内） |
| `slime/examples/ShopSimulator/generate.py` | 门控 hook：**+9/−1 行**（import 1 行、reward 行替换为 5 行、metadata +2 字段） | 仓库修改（分支内） |
| `runs/reward_shaping/task_dims.json` | `task_id → {n_attr, n_opt, goal_asin}`（重合成所需 goal 维度） | 23,421 条，新生成 |
| `runs/reward_shaping/test_reward_shaping.py` | 单元自测 18 例 | 新生成 |

## 2. 设计落地情况（对照计划）

- **公式**：采用"重合成"统一形式（替代计划初稿的门控近似）。先离线验证了重合成与环境公式逐分一致（用 RL 评测 164 条 done 记录对拍，`task_dims` 提供分母，**164/164 完全一致**），shaping 只是对公式成分的受控扰动：
  - `option_gate`（Fix 1）：`(attr_hits + w_opt·opt_hits + r_price) / (n_attr + w_opt·n_opt + 1) × r_type`，默认 w_opt=2.0；
  - `budget`（Fix 2）：`r_price → min(env r_price, 1[price ≤ budget×tol])`，只收紧不放松，默认 tol=1.1；
  - `full` = 两者叠加；`off` = 透传。
- **开关**：`SHOP_REWARD_SHAPING=off|option_gate|budget|full`，**默认 off 即逐字节原行为**（在 slime 环境内实测：off 时 `shape_reward` 原样透传、meta 为空）。
- **系数与表路径走 env**：`SHOP_REWARD_OPTION_WEIGHT`、`SHOP_REWARD_BUDGET_TOL`、`SHOP_REWARD_TABLE_DIR`，实验变体 = 配置差异，可精确重放。
- **原始分留存**：metadata 新增 `env_reward_raw`（任何模式下都记录）与 `reward_shaping`（变体/系数/预算判定明细；未生效时为 `{}`）。
- **健壮性**：reward_detail 缺字段、未知 task_id、表文件缺失，全部回退原始分并在 meta 标 `shaping_error`，绝不 crash rollout。

## 3. 单元自测（18/18 通过）

覆盖：off 透传 ×2；option_gate 满分/零分/部分命中 ×3；budget 预算内/超预算/边界值(=limit)/env 已为 0 不放松/无预算条目/无价格条目 ×6；full 双重生效；detail 缺失与不完整；未知 task_id；自定义 w_opt 与 tol；表目录缺失。

```bash
python3 /root/autodl-tmp/runs/reward_shaping/test_reward_shaping.py   # 18 passed, 0 failed
```

过程中唯一失败是测试自身的浮点精确比较（`100×1.1=110.00000000000001`），模块逻辑无误，已改为容差比较。

## 4. 集成验证（未到冒烟阶段）

- `py_compile` 两个文件通过；
- slime 环境（`micromamba/envs/slime/bin/python`）内：`from examples.ShopSimulator.reward_shaping import ...` 与 `import examples.ShopSimulator.generate` 均成功，off 透传实测一致（日志中的 torchao warning 为环境固有噪声，与本次改动无关）；
- `git diff generate.py` 确认改动恰为 hook 三处，无误伤；仓库其余 5 个修改文件均为用户既有改动，未触碰。

## 5. 隔离状态

- 代码：`reward_shaping.py` 仅存在于 `reward-shaping` 分支（untracked），`generate.py` diff 9 行；
- 产物：全部在 `runs/reward_shaping/`；
- 环境仓库、main 分支、`runs/asin_audit/` 均未触碰。

## 6. 下一步（阶段 3：冒烟）

确认 ShopSimulator 服务运行后，用 ~20 个任务的小文件 + `SHOP_REWARD_SHAPING=full` 短跑若干 rollout，验收：日志 shaped reward 正常、metadata 含 `env_reward_raw` 与 `reward_shaping`、无崩溃、零方差率无异常飙升。随后进入阶段 4 对照实验（R0 dev 基线 → R1/R2/R3）。
