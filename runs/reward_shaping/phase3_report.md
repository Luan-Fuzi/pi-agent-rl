# 阶段 3 报告：冒烟测试（shaping=full 短跑 GRPO）

日期：2026-09-01 · 分支：`reward-shaping` · 运行目录：`runs/qwen35_2b_shop_rl_smoke/`

## 1. 目的

在烧 3~4 个完整 GRPO run 之前，用最小规模（20 任务 × 4 rollout）验证三件事：

1. shaping 链路在真实训练栈（Ray runtime env → Megatron actor → custom generate）里**真的生效**；
2. 新增的 `env_reward_raw` / `reward_shaping` 元数据不破坏下游（reward 归一化、样本过滤、checkpoint 保存、SwanLab）；
3. shaped 分数的差异模式符合设计预期（budget 只减不增、option 加权双向微调）。

## 2. 代码改动（本阶段新增，全部在 `reward-shaping` 分支，未提交）

| 文件 | 改动 | 原因 |
|---|---|---|
| `slime/examples/ShopSimulator/run_rl.sh` | RUNTIME_ENV_JSON keys +4：`SHOP_REWARD_SHAPING/OPTION_WEIGHT/BUDGET_TOL/TABLE_DIR` | **关键**：`reward_shaping.py` 在 import 时读 env；ray worker 只继承白名单内的变量，不加则 shaping 永远 off |
| `slime/examples/ShopSimulator/run_eval.sh` | `PROMPT_DATA` 改为 env 可覆盖（默认仍 official_test_200） | 阶段 4 R0 dev 基线需要评 `dev_200.jsonl`；默认值不变，无破坏性 |
| `slime/examples/ShopSimulator/summarize_eval.py` | record 透传 `env_reward_raw`、`reward_shaping` 两字段 | 让 dev 评测产物自证"确为 shaping-off 运行"（应为空/缺省） |
| `config/shop_rl_smoke.json`（新增） | `shop_rl.json` 原样复制，仅数据集指向 `smoke_20.jsonl` | 冒烟配置与正式训练同路径同超参 |

产物（全部在 `runs/reward_shaping/`）：`smoke_20.jsonl`（rl_500_clean 前 20 行）、`acceptance.py`（阶段 4 验收脚本，asin_audit 逻辑的参数化版）、`dump_inspect.py`（dump 元数据/差异/零方差检查）、`smoke_launcher.log`、`shop_env_server.log`。

## 3. 运行设置与结果

- 服务：`pack_api.py`（PYTHONPATH 指向 `shop_env/` 后正常，capacity 20/20）；GPU 独占
- 命令：`run_rl.sh` + `RL_CONFIG=shop_rl_smoke.json` + `SHOP_REWARD_SHAPING=full`，从 SFT checkpoint（`runs/qwen35_2b_shop_sft`）起跑
- 规模：20 任务 ÷ 5/rollout = 4 rollout、3 个训练 step，**总耗时约 23 分钟**，exit 0
- 产物完整：`rollout_dumps/rollout_{0..3}.pt`、`checkpoints/iter_0000003`、`hf/rollout_3`、`train_command.txt`
- 日志检查：唯一 Traceback 是 SGLang 启动期 torchcodec/libavutil 可选依赖缺失（环境固有噪声，与 shaping 无关）

## 4. 验证结果

### 4.1 元数据完整性
- 1575/1575 fragment 带 `env_reward_raw`；747 条 done 全部带 `reward_shaping`，`shaping_variant` 均为 `full`（**证明 env 透传成功**）
- 无 `shaping_error` 记录（三张表全部命中，无回退）

### 4.2 shaped vs raw 差异
- **470/1575（30%）fragment 分数被改变**，delta ∈ [-0.143, +0.036]，均值 -0.053
- 手算复核两条（task 21705，n_attr=9、n_opt=2）：
  - opt 命中好（attr 1/9、opt 1/2）：0.2500 → 0.2857 ✅ 提分
  - opt 落空（attr 5/9、opt 1/2）：0.5833 → 0.5714 ✅ 降分
  - 两条 env 公式重算与 `env_reward_raw` 逐分一致，shaped 重算与 `reward` 逐分一致
- 方向符合设计：option_gate 让"规格选对的轨迹"相对提分、"规格落空的"相对降分

### 4.3 budget 修复实际触发
- 747 done 中 555 条任务有预算表项；**31 条 fragment 被收紧**（env r_price=1 → r_price_instr=0）
- 实例：task 10518 支付 201 > 预算 100；task 11022 支付 36 > 预算 23 —— 正是审计"超预算仍拿 r_price=1"问题在训练信号层面的直接修复

### 4.4 零方差与训练健康度
- 20 组中 7 组零方差（35%，含全满分组；GRPO 优势归零自然跳过，不阻碍训练）
- 3 个 step 的 loss/grad_norm/kl 均正常；SwanLab 同步成功；`normalize_candidate_group_rewards`、`validate_complete_groups` 无报错
- 观察：rollout 1/2 截断率偏高（0.66/0.56，SFT 模型在部分任务绕圈）——R0 原有现象，与 shaping 无关，记录在案

## 5. 结论

冒烟全部验收项通过。shaping 在真实训练栈端到端生效、元数据无侵入、budget 修复在真实轨迹上触发、差异方向符合设计。**可以进入阶段 4。**

## 6. 阶段 4 待办（已备齐）

1. **R0 dev 基线**：现有 RL checkpoint（`runs/qwen35_2b_shop_rl`）在 `dev_200.jsonl` 评测，shaping OFF（`PROMPT_DATA` env 已就绪）→ `runs/qwen35_2b_shop_eval_rl_r0_dev`
2. **R1**=`option_gate`、**R2**=`full`（均用原 `rl_500.jsonl`）、**R3**=`full`+`rl_500_clean.jsonl`，全部从同一 SFT checkpoint 重训 100 step
3. 每个 run 用 `acceptance.py` 出 dev 验收表（预算合规率 / r_option / right_product / 高分规格落空率）+ `dump_inspect.py` 出训练侧零方差
4. dev 选优 → official_test_200 只测一次 → 定稿 `report.md`

注意：阶段 4 是 3 个完整训练 run（每个数小时）+ 4 次 dev 评测，跑前需确认步数（100 全量 vs 50~70 缩短）。ShopSimulator 服务目前仍在后台运行，可直接复用。
