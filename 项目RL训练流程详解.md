# Pi + Slime + ShopSimulator：RL 训练流程详解

> 本文记录 `pi-slime-shopsimulator` 项目的完整训练流程：数据来龙去脉、名词体系、策略设计与 GRPO 算法细节。
> 所有结论均来自本机代码与数据（路径见文末索引），历史指标来自仓库 README。

---

## 1. 项目总览

**目标**：在中文购物模拟环境 ShopSimulator 上，把 Qwen3.5-2B 训练成会多轮调用工具的购物 agent。训练路线为 **教师数据采集 → SFT → 在线 GRPO（RL）→ 评测** 四步。

**组件分工**（一句话版：slime 指挥，Megatron 学，SGLang 说，Pi 干活，ShopSimulator 打分）：

| 组件 | 角色 | 说明 |
| --- | --- | --- |
| **slime**（THUDM fork 修改版） | 总指挥 / RL 训练框架 | 编排训练循环、数据流、权重同步，底层用 Ray 调度 |
| **Megatron-LM** | 训练后端 | 前向/反传/optimizer step |
| **SGLang** | 推理后端 | 采样阶段的高吞吐 token 生成 |
| **Pi**（`@earendil-works/pi-coding-agent` 0.84.2） | agent 运行时（外壳） | 驱动"调模型→解析工具调用→执行工具→回喂结果"的循环 |
| **ShopSimulator** | 环境 | 中文购物模拟器：出任务、给观测、算 reward |
| **Ray** | 分布式运行时 | 进程编排、权重传输 IPC |

**关键认知**：RL 的标准划分是「agent ↔ 环境」。本项目里 **agent = 模型（由 SGLang 服务）+ Pi（行为循环）**，**环境 = ShopSimulator**。Pi 不是环境，它是被训练策略的"身体"。

---

## 2. 名词解释

### 2.1 RL 通用名词

| 名词 | 含义 |
| --- | --- |
| **trajectory（轨迹）** | agent 从任务开始到结束（下单/截断）的完整交互序列：多轮"模型输出 → 工具调用 → 环境观测" |
| **rollout（采样/展开）** | 让当前策略在环境里实际跑出一条（或多条）轨迹的过程。本项目也用它指代"一轮训练迭代" |
| **policy（策略）** | 即被训练的模型本身：给定上下文，输出下一个动作（文本/工具调用）的概率分布 π_θ |
| **reward（奖励）** | 环境对一条轨迹的评分。本项目只在下单时结算，取值 [0,1] 连续 |
| **advantage（优势）** | 某条轨迹相对"基线"好多少。GRPO 里基线 = 同组均值，advantage 决定梯度方向与大小 |
| **critic（价值网络）** | PPO 中用来估计状态价值的独立网络。**GRPO 没有 critic**，用组内均值替代 |
| **on-policy（在线策略）** | 训练数据由"当前最新策略"采得。本项目每训 1 step 就把新权重灌回推理引擎，严格在线 |

### 2.2 本项目专有名词

| 名词 | 含义 | 出处 |
| --- | --- | --- |
| **goal** | 环境手里的任务"标准答案"：目标 ASIN、期望属性、期望规格、价格上限、指令文本。agent 只看到指令，goal 不可见，仅用于结算打分 | `web_agent_site/engine/goal.py` |
| **task_id / idx** | 任务编号，即 goal 列表的下标。任务 jsonl 通过它与环境对齐（`reset(idx=...)`） | 数据文件 metadata |
| **candidate** | 同一任务的一次独立采样（一条轨迹）。GRPO 每组采 4 个 candidate | `shop_rl.json: n_samples_per_prompt=4` |
| **group（组）** | 同一任务的 4 个 candidate 构成的比较单位，advantage 在组内计算 | `generate.py:80` |
| **turn** | 一次模型生成（含工具调用）。轨迹按 turn 切片，最长 40 个模型 turn | `shop_rl.json: max_model_turns=40` |
| **fragment（片段）** | 一条轨迹按 turn 切出的训练样本。同一条轨迹的所有片段共享同一个 rollout_id 和最终 reward | `generate.py:27` |
| **r_loose** | 环境给出的总规则分（连续 0~1） | `common.py:48` |
| **r_hard** | 四个子分连乘（任一维度为 0 则归 0），更严格 | `common.py:41-43` |
| **r_success** | 严格成功：四个子分全为 1 | `common.py:50` |
| **right_product** | 是否买中 goal 指定的 ASIN（观测指标，不进 reward） | `common.py:51` |
| **零方差组** | 组内 4 条得分完全相同的组，advantage 全 0，不产生梯度（"零方差浪费"） | `generate.py:117` |
| **colocate** | 推理（SGLang）与训练（Megatron）共用同一张 GPU，交替上场 | `run_rl.sh:180` |
| **权重同步（weight update）** | 每个训练 step 后把 Megatron 最新权重传输覆盖到 SGLang 的副本 | `actor.py:596` |

---

## 3. 数据的来龙去脉

### 3.1 环境数据：商品库与 goal

**源头**：上游 ShopAgent-Team 发布的商品库（HuggingFace `wpei/ShopSimulator`），本机位于
`pi-slime-work/ShopSimulator/shop_env/data/items_eval_train.json`，共 **23,421 件真实中文电商商品**。

每件商品的关键字段：

| 字段 | 内容 | 示例（task 1674） |
| --- | --- | --- |
| `asin` | 商品 ID | `942315298748` |
| `tag` | 上游划分：train 21,962 / eval 1,459 | `train` |
| `domain_zh` | 9 个一级类目之一 | 美妆个护健康 |
| `title` / `shop_name` / `category` | 标题、店铺、类目路径 | 日本奥尔滨蜂胶粉霜… |
| `attribute` | 商品属性标签 | `["粉底液", "蜂浆"]` |
| `customization_options` | 规格树（维度→选项→价格/子ASIN） | 颜色分类 3 个色号 |
| `instructions` | **任务原料**：完整指令、简化指令、期望选项、期望属性、标注员 id | 见下 |
| `user_persona` | 用户画像（4,666 件有）：注册/地区/人口/行为/交易/兴趣六层结构 | 上海·35+·钻石会员… |

**goal 生成**（`goal.py:62 get_existed_goals`）：服务启动时，每件商品的 instruction 条目变成一个 goal：

```
goal = {
  asin,                        # 目标商品
  instruction_text,            # agent 可见的自然语言需求
  attributes,                  # 期望命中的属性（如 ["粉底液","蜂浆"]）
  goal_options,                # 期望选中的规格（如 OC101自然色）
  price_upper,                 # 价格上限（补丁后：按 ASIN+instruction 确定性生成）
  user_persona / reason_key,   # 画像任务专用
}
```

23,421 个 goal = 23,421 个可执行任务，其中 eval 划分 1,459 个。

### 3.2 任务池切分（训练数据的第一层来源）

`slime/examples/ShopSimulator/data/tasks_v2/` 把 23,421 个 goal **无重叠**切成四池（并集恰好 23,421，已验证）：

| 池 | 规模 | task_id 范围 | 用途 |
| --- | --- | --- | --- |
| `sft` | 13,156 | 1497–23418 | 教师采集来源 |
| `rl` | 6,577 | 1495–23420 | GRPO 训练 |
| `dev` | 2,193 | 1546–23417 | 开发验证/调参 |
| `official_test` | 1,495 | 0–1494 | 最终评测 |

实验实际使用三个子集（均为对应池真子集）：`sft_512`、`rl_500`、`official_test_200`。

任务 jsonl 每行仅含：`prompt`（固定说明语）+ `label`（空）+ `metadata`（task_id、类目、属性数、选项数、split、manifest_id）。**任务文件不含购物需求本身**，需求在环境的 goal 里。

### 3.3 SFT 数据：教师采集流水线（实验 1）

```
sft_512.jsonl (512 任务)
   │  每任务 1 次采样：DeepSeek（deepseek-v4-flash）作教师，
   │  通过与正式训练完全相同的 Pi harness + ShopSimulator 交互
   ▼
原始轨迹（$SFT_DATA_ROOT/raw/<task>/000.json）
   │  筛选：必须下单（done）且 reward 过阈值
   ▼
accepted.jsonl —— 本次运行：514 条候选 → 416 条通过（覆盖率 80.9%）
   │  prepare_sft：按 turn 拆成独立样本，tokenizer 校验，≤16384 token
   ▼
turn_examples.jsonl —— turn-level SFT 样本（历史运行：6153 条）
   │  loss mask：只对 assistant 生成 token 计 loss；
   │  模板注入的空 think 块视为 prompt 被 mask（slime 对本项目的定制修正）
   ▼
SFT 训练（1 epoch，GLOBAL_BATCH_SIZE=3，历史：2051 个 optimizer step）
```

要点：教师轨迹和学生 RL 轨迹**同构**（同一个 harness、同一套工具、同一个环境），保证 SFT 学到的行为分布能被 RL 直接延续。本次采集明细见 `runs/shop_sft_512/summary.json`。

### 3.4 RL 数据：在线生成（实验 3）

RL 不预先存数据——**数据即采即用**：

```
rl_500.jsonl (500 任务)
   │  每轮训练迭代取 5 个任务 × 4 candidate = 20 条轨迹（并发）
   │  轨迹由"当前 actor 权重 + Pi + ShopSimulator"在线产生
   ▼
20 条轨迹 → per-turn 切片 → 打分 → 组内归一化 → 一个 global batch（20）
   │  训 1 个 optimizer step，数据即弃
   ▼
共 100 轮：500 组 / 2000 条轨迹 / 100 个 step（1 epoch）
```

每轮原始样本落盘 `RUN_ROOT/rollout_dumps/rollout_{id}.pt` 供事后分析。

### 3.5 模型 checkpoint 数据流

```
Qwen/Qwen3.5-2B（HF 下载）
   ├── HF 格式：tokenizer + SGLang 推理权重
   └── convert_hf_to_torch_dist → Megatron torch_dist 格式：训练权重
        │
        │  SFT（实验 2）              GRPO（实验 3）
        ▼                             ▼
   runs/qwen35_2b_shop_sft/     runs/qwen35_2b_shop_rl/
   ├── checkpoints/ (Megatron)  ├── checkpoints/ (Megatron)
   └── hf/ (HF export)          └── hf/ (HF export)
```

任何阶段启动都必须**成对传入同一代模型的 HF + Megatron 两种格式**：HF 给 SGLang/分词器，Megatron 给训练。评测（实验 4）对 Base/SFT/RL 三套 checkpoint 各跑 200 次单样本 rollout，结果写入各自 `RUN_ROOT/eval_results.json`。

---

## 4. 策略（Policy）解释

### 4.1 策略的物理形态

策略 = **Qwen3.5-2B 权重 + 固定推理包装**。模型每次生成看到的上下文由 Pi harness 组装：系统提示（"你是购物 Agent…"）+ 任务指令 + 历史工具调用与观测（旧观测会被裁剪，只保留最近 3 条 `shop_act` 结果）。动作空间被锁死为两个工具：

- `shop_reset`：开局调用一次，领取任务指令
- `shop_act(action=...)`：发送环境原生动作 `search[关键词]` 或 `click[可点击元素]`

### 4.2 为什么先 SFT 后 RL

Base 模型在 `official_test_200` 上正奖励率只有 **2.0%**——纯 RL 冷启动时，几乎每条轨迹都是 0 分，GRPO 组内全同分（零方差），没有学习信号。SFT 用教师轨迹把模型"扶上马"：学会工具调用格式、搜索-甄别-选规格-下单的基本行为链，把正奖励率拉到 72.5%，此后 GRPO 组内才有分数分化可供比较。**SFT 解决"会不会"，RL 解决"好不好"**。

### 4.3 教师数据筛选策略

不是教师跑出来什么就学什么的盲目模仿，而是**结果过滤的模仿学习（rejection sampling）**：只有 `done` 且 reward 过阈值的轨迹进入 SFT 语料。本次运行 512 任务 → 416 条通过（`reward=1.0` 的 335 条，其余为中高分部分分轨迹）。

### 4.4 一次成功轨迹的行为样例（task 1674，教师，reward=1.0）

指令："能不能给我推荐一款适合自然肤色的日本粉底液？要带有蜂浆成分，价格在1400以内的。"

```
search[粉底液] → 150 条结果
click[942315298748] → 详情页：价格 1388，3 个色号
click[features] / click[description] → 验证成分（页面为空）
click[back to search] → search[蜂浆粉底液] → 确认目标排首位
click[942315298748] → 再进详情页
click[【日本直邮】新版oc101自然色] → 选中"自然色"（对应"适合自然肤色"）
click[buy now] → 结算：score 1.0
```

注意指令中每个约束都对应 goal 的一个维度：日本/粉底液→类目，蜂浆→属性，自然肤色→规格选项，1400 以内→价格上限。

---

## 5. 奖励函数

### 5.1 结算规则

**只在 `click[buy now]`（done）时结算一次**，过程（搜索质量、轮数、格式）完全不计分。环境拿"买到的商品"与隐藏 goal 按规则对比（`goal.py:224 get_reward`），算四个子分：

| 子分 | 规则 | 性质 |
| --- | --- | --- |
| `r_type` | 类目/标题/query 是否匹配目标品类 | 0.5 或 1.0，乘性因子 |
| `r_att` | 属性命中数 ÷ 属性总数（模糊匹配阈值 85） | 连续 0~1 |
| `r_option` | 规格命中数 ÷ 规格总数 | 连续 0~1 |
| `r_price` | 成交价 ≤ price_upper？ | 0 或 1 |

```
reward(r_loose) = (属性命中数 + 规格命中数 + r_price) / (属性总数 + 规格总数 + 1) × r_type
r_hard          = r_type × r_att × r_option × r_price   # 连乘，任一归零则归零
r_success       = 四项全为 1
```

关键性质：

- **终点非二元**：买错规格得 0.75、买错商品但类目对得部分分——连续分数是 GRPO 信号的来源
- **基于属性而非 ASIN**：买到属性全匹配的其他 ASIN 也可满分
- **不下单 = 0**：turn 上限、中途放弃一律 0 分（"拖到最后"被隐式硬惩罚）
- **确定性**：补丁保证价格按 ASIN 生成，同一任务无论何时何地采样，评分完全一致

### 5.2 失败的三六九等

| 结局 | reward | 训练待遇 |
| --- | --- | --- |
| 下单 | 环境规则分 | 正常进组 |
| turn 上限截断 | 0 | **保留**（真实负样本，压"拖延不决策"） |
| agent 自行停止/工具错误 | 0 | 保留 |
| 基础设施故障（崩溃/429/超时） | 0（ABORTED） | **整组 4 条原子丢弃**，假 0 分不进训练 |

### 5.3 训练侧入口

奖励进训练的唯一定制点是 `generate.py:275`：

```python
reward = float(result.reward) if result.done else 0.0
```

此处可得信号：环境分、四个子分、模型 turn 数、工具调用数、终止原因、买入 vs 目标 ASIN——所有 reward shaping（效率惩罚、子分加权等）都应在这一行做，且只影响训练，评测仍读环境原始分以保持与 baseline 可比。

---

## 6. GRPO 详解

### 6.1 算法原理

GRPO（Group Relative Policy Optimization，DeepSeekMath 2024）的核心思想：**抛弃 critic 价值网络，改用"同题多解的相对比较"估计优势**。

1. 对同一任务采样一组（本项目 4 条）candidate
2. 每条拿环境 reward
3. 组内归一化得 advantage：`A_i = (r_i − 组均值) / (组std + 1e-6)`
4. 用 PPO 的 clipped surrogate 目标函数更新策略

直觉：GRPO 不知道一条轨迹"绝对值多少分"，只知道它"比同组兄弟好还是差"。这正好匹配规则分 reward 的场景——不需要训练额外的价值网络，工程上轻一个数量级。

### 6.2 "GRPO" 与 "PPO loss" 的关系

两者不矛盾，是不同层面：

- `--advantage-estimator grpo`：advantage **怎么算**（组相对，替代 critic+GAE）
- `--loss-type policy_loss`：目标函数**长什么样**（PPO 的 clip 形式，GRPO 论文本来就沿用）

本项目未启用 `--advantage-estimator ppo`（那会需要 critic 网络和 GAE）。

### 6.3 本项目配置（`config/shop_rl.json` + `run_rl.sh`）

| 配置 | 值 | 说明 |
| --- | --- | --- |
| 组大小 `n_samples_per_prompt` | 4 | 每任务 4 candidate |
| `rollout_batch_size` | 5 | 每轮 5 个任务 = 5 组 |
| `global_batch_size` | 20 | = 5×4÷1，每轮恰好一个 batch |
| `num_steps_per_rollout` | 1 | 每批数据只训 1 step（on-policy） |
| 总轮数 | 100 | 500 任务 ÷ 5，即 100 个 optimizer step |
| advantage | (r−mean)/(std+1e-6) | 带 std 归一化（Dr.GRPO 争议点，可消融） |
| clip | ε_low=0.2, ε_high=0.28 | 非对称 clip（DAPO 的 Clip-Higher 组件） |
| KL | 0.001 × low_var_kl | 对 SFT checkpoint 的 k3 估计器，钳 ±10 |
| 熵系数 | 0 | 不加熵正则 |
| 优化器 | Adam, lr=1e-6 恒定, β=(0.9,0.98), wd=0.1, grad clip 1.0 | 保守配置 |
| loss 归约 | 样本内 token 均值 → batch 样本均值 | 非全局 token 级（非 DAPO token-level loss） |
| loss mask | qwen3_5 | 只对 assistant 生成 token 计 loss |

**总 loss**：

```
loss = mean_samples[ mean_tokens( −max(ratio·A, clip(ratio,0.8,1.28)·A) ) ] + 0.001·mean(low_var_kl)
其中 ratio = exp(logπ_θ − logπ_old)，π_old≈当前权重（每批只训一步，近似 on-policy）
```

### 6.4 零方差浪费

组内 4 条同分（全 1.0 太简单 / 全 0 太难 / 巧合同分）→ advantage 全 0 → 梯度为 0，算力白费但无害。历史运行：**500 组中 352 组有方差，148 组（29.6%）浪费**。本项目不做动态重采样（DAPO Dynamic Sampling），`SHOP_REQUIRE_NONZERO_VARIANCE_PER_ROLLOUT=0` 允许整轮零信号静默通过。改进方向：动态采样、按 SFT 通过率预筛任务（curriculum）、增大组内采样数。

### 6.5 与 DAPO 的对照

主体是**标准 GRPO**，只借了 DAPO 的 Clip-Higher。未采用：Dynamic Sampling（零方差组不重采）、Token-Level Loss（仍按样本归一）、Overlong Shaping（截断硬 0 分）、去 KL（保留 0.001 KL 锚定 SFT）。

---

## 7. 训练循环与权重同步

### 7.1 单轮迭代时间线（`train.py:49-91`）

```
① 采样：RolloutManager.generate
   5 任务 × 4 candidate 并发；每路一个独立 Pi 进程
   Pi 的模型请求 → 本地 OpenAIAdapter → SGLang（当前 actor 权重）
   轨迹 → per-turn 片段 + reward + 组内归一化 advantage
② 推理侧 offload：SGLang 释放显存（colocate 单卡错峰）
③ 训练：TrainActor
   ref 模型前向 → ref_log_probs（KL 用）
   actor 前向 → log_probs
   advantage 逐 token 广播 → PPO clip loss + 0.001·KL
   反传 + 1 个 optimizer step
④ 保存：到点写 Megatron checkpoint + HF export（本项目仅在最后）
⑤ 权重同步：UpdateWeightFromTensor
   收拢分布式参数 → 转 HF 布局 → GPU→CPU 序列化 → Gloo 收集
   → Ray IPC 灌进 SGLang 进程覆盖旧副本 → 清 KV cache
```

循环 100 轮。SGLang 推理的永远是**上一个 step 结束时的快照**；`num_steps_per_rollout=1` 保证采样模型与训练模型零滞后。

### 7.2 数值一致性

权重可逐 bit 一致，但 SGLang 与 Megatron 的 kernel/数值路径不同，同一 token 两边 logprob 有微小差异——由 PPO clip 吸收，观测指标为日志中的 `train_rollout_logprob_abs_diff` 与 `pg_clipfrac`。`--sglang-enable-deterministic-inference` 用于压缩推理侧数值抖动。

---

## 8. 实验全景与历史指标

| 阶段 | 内容 | 历史结果（本机复现会有漂移） |
| --- | --- | --- |
| 实验 1 | `sft_512` 教师采集（DeepSeek） | 512 任务 → 412 条通过（本机复跑 416 条）→ 6153 turn 样本 |
| 实验 2 | 全量 SFT 1 epoch | 2051 step，产出 HF+Megatron checkpoint |
| 实验 3 | `rl_500` 在线 GRPO 1 epoch | 500 组 / 2000 轨迹 / 100 step；352 组有方差 |
| 实验 4 | `official_test_200` k=1 评测 | 见下表 |

| 模型 | 正奖励 pass@1 | 严格成功 pass@1 | mean r_loose | mean r_hard |
| --- | ---: | ---: | ---: | ---: |
| Base | 2.0% | 0.0% | 0.004 | 0.000 |
| SFT | 72.5% | 10.5% | 0.390 | 0.124 |
| RL | 90.5% | 31.0% | 0.628 | 0.355 |

公开产物：SFT 模型 `mrzhao13/qwen3.5-2b-shopsimulator-sft-512-1ep`，RL 模型 `mrzhao13/qwen3.5-2b-shopsimulator-grpo-rl500-1ep`（HuggingFace）。

---

## 9. 关键文件索引

| 内容 | 路径 |
| --- | --- |
| 项目仓库 | `/root/autodl-tmp/pi-slime-shopsimulator/` |
| RL 入口脚本 | `slime/examples/ShopSimulator/run_rl.sh` |
| RL 超参配置 | `slime/examples/ShopSimulator/config/shop_rl.json` |
| rollout / reward / 组归一化 | `slime/examples/ShopSimulator/generate.py` |
| Pi 进程管理 | `slime/examples/ShopSimulator/pi_harness.py` |
| Pi 工具扩展 | `slime/examples/ShopSimulator/shop_extension.ts` |
| 任务池数据 | `slime/examples/ShopSimulator/data/tasks_v2/` |
| 评测指标计算 | `slime/examples/ShopSimulator/common.py` |
| 训练主循环 | `slime/train.py` |
| GRPO loss / advantage | `slime/slime/backends/megatron_utils/loss.py`、`slime/slime/utils/ppo_utils.py` |
| 权重同步 | `slime/slime/backends/megatron_utils/update_weight/` |
| 环境源码（已打补丁） | `/root/autodl-tmp/pi-slime-work/ShopSimulator/` |
| 环境 reward | `shop_env/web_agent_site/engine/goal.py` |
| 商品库 | `shop_env/data/items_eval_train.json` |
| 教师采集产物 | `/root/autodl-tmp/runs/shop_sft_512/` |
| SFT 产物 | `/root/autodl-tmp/runs/qwen35_2b_shop_sft/` |

---

## 10. ShopSimulator 背景补充

- **出处**：论文《ShopSimulator: Evaluating and Exploring RL-Driven LLM Agent for Shopping Assistants》（arXiv:2601.18225，2026-01），ShopAgent-Team，一作 Pei Wang 等 16 人。代码 `github.com/ShopAgent-Team/ShopSimulator`，数据 `huggingface.co/datasets/wpei/ShopSimulator`。
- **血统**：WebShop（NeurIPS 2022）的中文大规模化后继，动作空间同样只有 `search[...]` / `click[...]`。
- **实现**：Python/Flask 服务；搜索引擎为 Apache Lucene（经 pyserini 0.17.0 + pyjnius 调 JVM，BM25 词项检索）；页面真渲染 HTML 再由 BeautifulSoup 文本化。
- **论文结论**：顶级模型严格成功率 <40%；SFT+RL 组合训练显著提升——本项目的直接动机。
- **本项目补丁**（`shopsimulator-slime-integration.patch`，基线 `51bb260` → `3ab366b`，50 文件）：并发 rollout 会话隔离（20 槽环境池 + rollout_session_id）、确定性价格（按 ASIN）、文本环境适配、依赖与仓库清理。
