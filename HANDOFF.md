# HANDOFF — 项目交接与打包记录

日期：2026-09-06 ｜ 工作目录：`/root/autodl-tmp` ｜ 磁盘：150G 总量，当时已用 ~133G

---

## 0. 一分钟速览

- **项目**：Qwen3.5-2B + Pi + Slime + ShopSimulator 的购物 agent RL（SFT → 在线 GRPO）。全流程文档见 `项目RL训练流程详解.md`。
- **当前结论**（commit-shaping 实验线，已闭环）：
  1. 过程级 reward shaping 首次在本 stack 上实现"信号→行为→test 泛化"闭环：test done **+4.2pt 弱阳性**（k=3 配对，95% CI [+0.2, +8.3]），r_hard 中性（无精度损失），done 均轮 **−12%**（17.4→15.3）。
  2. 归因（E1b 2×2）：收益是 **shaping × thinking 交互**——无思考臂效应消失（−1.0pt，CI 含 0）。
  3. 残余瓶颈：turn_limit 41/200 + 14 个三次全零任务；reward 侧已挤不出更多，**数据侧路线（SFT 混"近似即下单"示范）是下一步主线**。
- **权威记录**：`runs/commit_shaping/report.md`（总报告，含 §1b k=3、§2b E1b）；阶段报告 `commit-shaping/t1~t5_report.md`。
- **代码状态**：仓库 `pi-slime-shopsimulator` 分支 `commit-shaping`，**全部改动未提交**（12 改 + 5 新增）。打包即保存，或见 §6.1 提交建议。

---

## 1. 环境复现要点

`pi-slime-env.sh` 定义全部路径（source 后用 `$SLIME_DIR` 等变量）：

| 变量 | 值 |
|---|---|
| 仓库 / slime | `/root/autodl-tmp/pi-slime-shopsimulator` / 其下 `slime/` |
| Python 环境 | `/root/autodl-tmp/pi-slime-work/micromamba/envs/slime/bin/python` |
| Megatron | `/root/autodl-tmp/pi-slime-work/Megatron-LM` |
| 基座模型 | `pi-slime-work/models/Qwen3.5-2B`（HF）+ `Qwen3.5-2B_torch_dist`（Megatron 格式） |
| 环境服务代码 | `pi-slime-work/ShopSimulator` |
| SwanLab | 默认同步（`SLIME_SWANLAB_SYNC=1`），项目 `@Luan_Fuzi/pi-slime-shopsimulator` |

**环境服务启动**（所有训练/评测的前置）：
```bash
source /root/autodl-tmp/pi-slime-env.sh
cd "$SHOP_SIM_DIR/shop_env" && PYTHONPATH="$SHOP_SIM_DIR/shop_env" \
  "$SLIME_PYTHON" shop_env/pack_api.py > /root/autodl-tmp/runs/shop_env_server.log 2>&1
# 验证：curl -X POST http://127.0.0.1:5000/api/shop_agent -d '{"action":"status"}' 有响应即可
```

**关键坑（都踩过，勿再踩）**：
1. `run_rl.sh` 的 ray job 入口 `train.py` 按**提交时 cwd** 解析——必须 `cd "$SLIME_DIR"` 再启动（launcher 里已内置）。
2. 后台任务输出必须全部重定向落盘（管道直出有 16MiB 上限会杀任务）；长任务禁超时。
3. `run_eval.sh` **结构性关闭 shaping**（不转发 `SHOP_REWARD_SHAPING`），评测永远是无塑造策略——这是刻意的。
4. 训练日志里 `rollout/raw_reward` 的聚合口径与 candidate/fragment 加权都对不上，是 slime metric 路径问题，**不影响训练数据，不要追**。

**安全**：`pi-slime-work/deepseek_api_key.txt` 是 API 密钥，**不要打包、不要外传**（§4 的 tar 命令已整目录排除 pi-slime-work）。

---

## 2. 相比"刚克隆下来"新增了什么（完整清单）

### 2.1 仓库内（`pi-slime-shopsimulator`，分支 `commit-shaping`，未提交）

初始提交仅 1 个（"Initial release"）。工作区改动 = 三个阶段（thinking-distill → reward_shaping → commit-shaping）的全部代码积累，`git diff` 合计 277 插入 / 30 删除：

**修改（12）**：
| 文件 | 改了什么 |
|---|---|
| `slime/examples/ShopSimulator/reward_shaping.py` 相关逻辑入口在 `generate.py` | shaping 变体接入训练奖励（env 门控、默认 off） |
| `slime/examples/ShopSimulator/generate.py` | metadata 新增 `process_stats`/`action_sequence`；`shape_reward` 加 `done/process_stats/model_turns` 参数；过程统计进 rollout dump |
| `slime/examples/ShopSimulator/pi_harness.py` | `PiRunResult.actions`：pi `tool_execution_start` 事件取 args，toolCallId 配对非 error 非 terminal_noop 的 `tool_execution_end`，得动作序列 |
| `slime/examples/ShopSimulator/run_rl.sh` | 透传 8 个 `SHOP_REWARD_*` knob + SwanLab 同步 + cwd 注释 |
| `slime/examples/ShopSimulator/run_eval.sh` | 评测 launcher（EVAL_CONFIG env 化等；刻意不转发 shaping） |
| `slime/examples/ShopSimulator/summarize_eval.py` | 评测聚合口径（official_metrics 包装、dump→eval_results.json） |
| `slime/examples/ShopSimulator/collect_sft.py`、`prepare_sft.py`、`run_sft.sh` | thinking-distill 阶段的 SFT 数据构建/训练改动（细节见 `thinking-distill/` 各报告） |
| `slime/slime/agent/adapters/common.py` | `SLIME_ROLLOUT_THINKING` 思考开关（缺省=关） |
| `slime/slime/observability/logging_utils.py`、`wandb_utils.py` | SwanLab 实时同步 |
| `slime/build_conda.sh` | 环境构建修正 |

**新增（5）**：
| 文件 | 用途 |
|---|---|
| `slime/examples/ShopSimulator/reward_shaping.py` | 组件式 reward shaping（off/option_gate/budget/full 为 legacy；milestones/antiloop/efficiency 可 `+` 组合；`compute_process_stats` 纯函数；未知组件 import 期报错） |
| `slime/examples/ShopSimulator/config/shop_eval_dev_k1.yaml` | dev 评测配置（k=1） |
| `slime/examples/ShopSimulator/config/shop_eval_official_k3.yaml` | k=3 复测配置（`n_samples_per_eval_prompt: 3`） |
| `slime/examples/ShopSimulator/config/shop_rl_clean.json`、`shop_rl_smoke.json` | 清洗任务集 RL 配置 / 冒烟配置 |

### 2.2 仓库外（`/root/autodl-tmp/` 下新增）

| 路径 | 大小 | 内容 |
|---|---|---|
| `runs/` | 103G（去模型权重 **11G**） | 全部实验产物，细分见 §3/§4 |
| `commit-shaping/` | 140K | 本阶段计划书、t1~t5 报告、全部 launcher（`run_e{1,2,3}.sh`、`run_e1b.sh`、`eval_*.sh`、`run_e0_smoke.sh`）、单测 `test_reward_shaping.py`（49 用例）、`replay_t4_dump.py`+结果、`k3_compare.py`（配对 bootstrap 分析） |
| `thinking-distill/` | 286M | 思考蒸馏阶段工作区：`t1_pilot/`（264M pilot 数据）、`wire_probe/`、`p0_prompt_probe/`、分析与 QC 脚本、t15/t3_sft/t4_rl 等阶段报告、`thinking_distill_plan.md` |
| `项目RL训练流程详解.md` | 21K | 全流程详解文档 |
| `reward_shaping_plan.md` | 10K | reward_shaping 阶段计划书 |
| `asin_audit_report.md` | 13K | ASIN 审计报告 |
| `pi-slime-env.sh` / `shopsimulator.sh` | 2K | 环境变量 / 环境服务脚本 |
| `pi-slime-work/` | 37G | **环境目录，不建议打包**：micromamba 26G、基座模型 7.8G（可重下）、ray 1.7G、sglang 1.5G、ShopSimulator 319M、Megatron-LM 177M、`deepseek_api_key.txt`（密钥） |

---

## 3. 实验链与最终数字（速查）

时间线：**thinking-distill**（SFT + 思考数据）→ **reward_shaping**（R0/R1/R2 三轮 shaping，行为不动，失败）→ **commit-shaping**（T1–T6 + k=3 + E1b，闭环）。

### 3.1 dev_200 竞技场（k=1，shaping OFF 评测）

| 变体 | done | r_hard | 判定 |
|---|---|---|---|
| T4（思考基线） | 0.875 | 0.662 | — |
| E1（milestones） | **0.950** | 0.683 | 双轴阳性 |
| E2（+antiloop） | 0.885 | 0.705 | r_hard 涨 / done 平 |
| E3（+efficiency，冠军） | 0.915 | **0.715** | 双轴阳性 |

### 3.2 official_test_200 终判

k=1：E3 vs T4 done +2.0pt / r_hard −0.6pt（噪声内）→ **k=3 配对复测**（各 600 episodes）：

| 指标 | E3 | T4 | Δ | 95% CI |
|---|---|---|---|---|
| **done** | 0.805 | 0.763 | **+4.2pt** | [+0.2, +8.3] 弱阳性 |
| **r_hard** | 0.403 | 0.392 | +1.2pt | [−3.0, +5.4] 中性 |
| done 均轮 | **15.3** | 17.4 | **−2.1** | 效率收益复现 |

pass@3：pass_done 0.93，仅 14/200 任务三次全零（残余失败="不稳定"而非"做不到"）。

### 3.3 E1b 归因（dev_200，k=1）

| | 无 shaping | + milestones | Δ |
|---|---|---|---|
| 非思考 | R0：0.915 / 0.631 | E1b：0.905 / 0.614 | **−1.0pt，CI 含 0，无效** |
| 思考 | T4：0.875 / 0.662 | E1：0.950 / 0.683 | **+7.5pt，双轴阳性** |

→ 收益为 shaping × thinking 交互项；数据侧路线与部署应锁定"思考开"。

### 3.4 训练健康（全部 run 同包络）

entropy 缓降/波动无塌缩；clipfrac、ppo_kl≈0 是 1-step-per-rollout 严格在线的预期形态；kl_loss 缓涨远低钳位；grad_norm 稳定。

---

## 4. 大小明细与打包建议

### 4.1 runs/ 细分（总计 103G）

**训练 run**（每个含 `checkpoints/`+`hf/` 模型权重、`rollout_dumps/` 轨迹、`wandb/`、日志）：

| run | checkpoints | hf | rollout_dumps | 说明 |
|---|---|---|---|---|
| `qwen35_2b_shop_rl`（R0 非思考基线） | 3.6G | 3.6G | 1.3G | 最早 RL |
| `qwen35_2b_shop_rl_r1` / `_r2` | 3.6G ×2 | 3.6G ×2 | 1.4G ×2 | R1/R2 shaping 失败轮 |
| `qwen35_2b_shop_rl_thinking`（T4） | 3.6G | 3.6G | 482M | 思考基线 |
| `qwen35_2b_shop_rl_commit_e1` / `_e2` / `_e3` | 3.6G ×3 | 3.6G ×3 | ~450M ×3 | 本轮三支消融，E3 冠军 |
| `qwen35_2b_shop_rl_commit_e1b` | **15G**（中期未 prune） | **15G**（同上） | 1.3G | 归因臂；中期存档清理命令见 §6.3 |
| `qwen35_2b_shop_sft` / `_sft_thinking` | 3.6G ×2 | 3.6G ×2 | — | SFT 起点 |
| `shop_sft_512` | — | — | — | 655M，早期 SFT |

**评测 run**（各含 `rollout_dumps/rollout_eval_0.pt` + `eval_results.json`，35–230M）：base、sft、rl（R0）、rl_r0_dev、rl_r1、rl_r2、r2_p0probe、rl_thinking、rl_*_official、sft_thinking_{dev,official}、commit_e{1,2,3}_dev、commit_e1b_dev、commit_e3_official、k=3 两个（`commit_e3_official_k3` 181M、`rl_thinking_official_k3` 203M）。

**数据 / 审计 / 报告**：`runs/reward_shaping/`（69M：任务集 dev_200/rl_500_clean 等 + phase 报告 + acceptance.py）、`runs/thinking_sft/`（128M，含 SFT 训练集 `prepared/turn_examples_thinking_6357.jsonl`）、`runs/asin_audit/`（9.6M）、`runs/failure_audit/`（20K）、`runs/commit_shaping/`（12K，总报告）。

**汇总**：模型权重（checkpoints+hf）≈ 92G；rollout 轨迹全量 9.3G；其余（评测聚合、wandb、日志、数据）≈ 1.7G。

### 4.2 推荐打包方案（排除 checkpoint/模型权重，≈11.6G 原始）

```bash
cd /root/autodl-tmp
tar czf handoff_20260906.tar.gz \
  --exclude='*/checkpoints' --exclude='*/hf' \
  --exclude='*/.ipynb_checkpoints' \
  pi-slime-shopsimulator commit-shaping thinking-distill runs \
  pi-slime-env.sh shopsimulator.sh \
  项目RL训练流程详解.md reward_shaping_plan.md asin_audit_report.md HANDOFF.md
```

覆盖：仓库全部代码改动（含 .git）+ 三个工作目录 + runs 去权重（轨迹/评测/报告/数据）+ 根文档。**pi-slime-work 整目录不含**（环境可重建、基座可重下、且含密钥）。

**极限压缩版**（再排除轨迹 dump，≈2.3G 原始）：追加 `--exclude='*/rollout_dumps'`。轨迹是数据侧路线的原料，有续作打算建议保留。

校验：`tar tzf handoff_20260906.tar.gz | wc -l`。

---

## 5. 数据地图

| 数据 | 位置 |
|---|---|
| RL 任务集 | `slime/examples/ShopSimulator/data/tasks_v2/rl_500.jsonl`（500 题）；清洗版 `runs/reward_shaping/rl_{500,490}_clean.jsonl` |
| dev / test 集 | `runs/reward_shaping/dev_200.jsonl`；`slime/.../data/tasks_v2/official_test_200.jsonl` |
| RL 原始轨迹 | 各训练 run 的 `rollout_dumps/rollout_{0..99}.pt`（含 prompt/response/reward/metadata：`reward_detail` 子分、`process_stats`、`action_sequence`、`termination_reason`） |
| 评测轨迹+聚合 | 各评测 run 的 `rollout_dumps/rollout_eval_0.pt` + `eval_results.json` |
| SFT 训练集 | `runs/thinking_sft/prepared/turn_examples_thinking_6357.jsonl`（思考 SFT，6357 条）；`tasks_v2/sft.jsonl`、`sft_512.jsonl` |
| 数据侧路线原料 | `runs/qwen35_2b_shop_rl_thinking/rollout_dumps`（T4 轨迹）+ E3 dump 做偏好对 |

---

## 6. 遗留事项

1. **git 未提交**：12 改 + 5 新增在 `commit-shaping` 分支工作区。要么打包工作区（§4 已含），要么：
   `cd pi-slime-shopsimulator && git add -A && git commit`（或 `git diff > changes.patch` + `git stash` 另行保存 untracked）。
2. **后续主线（数据侧）**：SFT 混"近似即下单"示范，直接教行为；目标 turn_limit 41/200 与 14 个全零任务；锁定思考开。
3. **磁盘清理**（若继续用这台机器）：E1b 中期存档 ~15G（`runs/qwen35_2b_shop_rl_commit_e1b/{hf/rollout_{24,49,74},checkpoints/iter_00000{24,49,74}}`）；E1/E2 终版各 7.6G 可选删（E3 冠军保留）。
4. **环境服务**：打包时仍在后台运行（pack_api.py）；不需要了 `kill` 即可，日志 `runs/shop_env_server_commit.log`。

---

## 7. 关键文档索引

| 文档 | 内容 |
|---|---|
| `runs/commit_shaping/report.md` | **本轮总报告**（结论、全部数字、讨论、产物索引） |
| `commit-shaping/commit_shaping_plan.md` | 本轮计划书（判据预注册） |
| `commit-shaping/t1~t5_report.md` | 阶段报告（实现/冒烟/E1/E2/E3） |
| `项目RL训练流程详解.md` | 全流程详解 |
| `thinking-distill/` 各报告 | SFT/思考蒸馏阶段结论 |
| `runs/reward_shaping/` phase*_report.md、report.md | R0/R1/R2 失败轮记录 |
| `runs/reward_shaping/badcase_analysis.md`、`asin_audit_report.md` | 失败模式与 ASIN 审计 |
