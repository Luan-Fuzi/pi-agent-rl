# T0 模板与管线可行性侦察报告

日期：2026-09-02
分支：`thinking-distill`（从 `reward-shaping` 切出，已创建；未做任何提交）
执行环境：无 GPU 占用；ShopSimulator 服务在 5000 端口运行中（`/status` 返回 404 属正常，Flask 服务在线）

结论：**Go**。四个开放问题全部有确定答案，且比 plan 预想更顺——模板和 loss mask **零改动**原生支持思考，教师模型**天生就开思考**。改动集中在 5~6 个开关点上。

---

## Q1：add_generation_prompt=True 时模板输出什么？（头号问题）

**答案：取决于 `enable_thinking` 开关，两种形态都原生支持。**

实测（tokenizer 路径 `runs/qwen35_2b_shop_sft/hf/rollout_0`，同一条 SFT 样本渲染）：

| 调用方式 | 生成提示尾部 | 形态 |
|---|---|---|
| 默认（不传 enable_thinking） | `<|im_start|>assistant\n<think>\n\n</think>\n\n` | **闭合空壳**——模型只能写正文，没机会思考 |
| `enable_thinking=True` | `<|im_start|>assistant\n<think>\n` | **打开的思考区**——模型生成思考内容，自行输出 `</think>` 闭合 |

模板源码 `chat_template.jinja:147-153` 确认：`add_generation_prompt` 时若 `enable_thinking is defined and enable_thinking is true` 则输出打开的 `<think>\n`，否则注入整个空块。

**含义**：SFT 数据带思考只是第一步；**rollout 侧必须显式传 `enable_thinking=True`**，否则模型在 GRPO/评测时仍被空壳封口（见"新发现的改动点 5"）。

## Q2：模板如何承载思考内容？

**答案：原生支持 `reasoning_content` 字段，两条路径都验证通过。**

- **路径 A（推荐）**：assistant message 带 `"reasoning_content": "..."` 字段 → 模板渲染为 `<think>\n...\n</think>\n\n正文`（jinja:90-101）。
- **路径 B**：content 字符串内嵌 `<think>\n...\n</think>\n\n正文` → 模板自动拆分，效果相同（jinja:94-97）。

多轮行为（jinja:68-77, 100-104）：模板定位**最后一条非 tool_response 的 user 消息**为 `last_query_index`；在 agent 轨迹里这就是初始任务指令，因此**之后所有 assistant turn 都保留 think 块**——正好覆盖 SFT 的全部目标 turn，无需手工裁剪历史思考。

**prepare_sft.py 实现建议**：把收集到的 thinking part 转成 `reasoning_content` 字段（路径 A），让模板自己拼装，比手工拼字符串更不容易和 mask 逻辑脱节。

## Q3：pi --thinking 对 DeepSeek API 的映射

**答案：教师 deepseek-v4-flash 是原生思考模型，API 默认就返回 `reasoning_content`；pi 侧有现成档位开关。**

实测（curl 直连 api.deepseek.com，key 从文件注入未读取内容）：

1. **裸请求**（无任何 reasoning 参数）：返回 `reasoning_content` 字段（例：问"1+1=?"，content="2"，reasoning_content="我们要求只回答数字，1+1=2。"）。**说明旧 SFT 采样时教师一直在思考、我们也一直在为思考 token 付费，只是管线把它扔了。**
2. **带 `reasoning_effort: "low"`**：API 正常接受、无报错，返回 reasoning_content。档位参数有效。
3. **pi CLI 0.84.2**：`--thinking` 支持 `off, minimal, low, medium, high, xhigh, max`；`--model provider/id:<level>` 简写也支持。

当前管线的封锁点（plan §2 已列，实测确认）：
- `pi_harness.py:259`：硬编码 `--thinking off`
- `pi_harness.py:222`：models.json `reasoning: False`
- `pi_harness.py:216`：models.json `compat.supportsReasoningEffort: False`（会阻止 pi 下发 effort 参数）

**改动方案（env 门控）**：`SHOP_PI_THINKING=medium` 时，pi_harness 改为 `--thinking medium` + `reasoning: True` + `supportsReasoningEffort: True`；默认行为不变。

## Q4：思考 token 的计费与预算影响

**答案：思考 token 计入 completion/max_tokens，两侧影响不对称。**

- **教师侧**：DeepSeek usage 实测 `completion_tokens=14`，其中 `completion_tokens_details.reasoning_tokens=12`——思考计入 completion 配额。collect_sft.py 的 `--max-tokens` 默认 32768，余量充足，**无风险**。
- **2B rollout 侧**：RL 配置 `max_response_len=2048`（`config/shop_rl*.json:26`）；slime OpenAI adapter 把请求体的 `max_tokens` 直接映射为 sglang 的 `max_new_tokens`（`adapters/common.py:442-444`，与 session 默认 4096 取 min）。sglang 眼里思考就是普通生成文本，**思考吃掉的每一 token 都来自这 2048**。思考写长了会挤压正文/工具调用，存在截断风险——**留到 T1 pilot 实测校准**（观测点：done 率、finish_reason=length 比例、思考长度分布）。

## Loss mask 验证（附带项）

用真实 tokenizer + 合成双轮带思考对话跑 `gen_multi_turn_loss_mask_qwen3_5`，逐 token 检查：

| 区段 | mask | 是否符合预期 |
|---|---|---|
| `<|im_start|>assistant\n` 头 | 0 | ✓ |
| `<think>\n` 开壳 | 0 | ✓ 不计 loss |
| **思考正文** | 1 | ✓ 计梯度 |
| `\n</think>\n\n` 闭壳 | 1 | ✓（模型需学会自己闭合） |
| 正文 + `<|im_end|>` | 1 | ✓ |
| system/user/tool 全部 | 0 | ✓ |

mask_utils.py:163-168 的注释本就写明了这个设计意图。**结论：SFT 训练侧零改动直接支持思考样本。**

## 新发现的改动点（plan §2 之外）

plan 列了 5 处（pi_harness×2、collect_sft×2、prepare_sft×1），T0 发现第 6 处，且是最关键的：

5. **（原 plan 已有）prepare_sft.py:38** 对 thinking 块 raise 报错 → 改为接受并写入 `reasoning_content`。
6. **（新）`slime/slime/agent/adapters/common.py:66` `_render_token_ids`**：rollout 渲染调 `apply_chat_template(..., add_generation_prompt=True)` 但**不传 `enable_thinking`** → 默认空壳封口。T4 GRPO 和 T5 评测要模型思考，必须 env 门控（如 `SLIME_ROLLOUT_THINKING=1`）传 `enable_thinking=True`。不改这个，SFT 学到的思考在 rollout 时完全发不出来。

另有一个 T1 待观测项：rollout 时模型自己产生的历史思考会随 `reasoning_content` 回传并累积进后续 context（openai.py:135-137 翻译回模板消息）。是否裁剪历史思考以省 context，T1 看 pilot 轨迹长度再定。

## 改动点总表（更新后）

| # | 位置 | 改动 | 门控 | 阶段 |
|---|---|---|---|---|
| 1 | `pi_harness.py:259` | `--thinking off` → 按 env 传档位 | `SHOP_PI_THINKING` | T1 采样 |
| 2 | `pi_harness.py:214-225` | models.json `reasoning`/`supportsReasoningEffort` 置 True | 同上 | T1 采样 |
| 3 | `collect_sft.py:113` | 保留 thinking part（而非丢弃） | 同上 | T1 采样 |
| 4 | `collect_sft.py:323` | 元数据记录思考档位 | 同上 | T1 采样 |
| 5 | `prepare_sft.py:38` | thinking 块 → `reasoning_content` 字段 | 自动（有思考才触发） | T2 准备 |
| 6 | `adapters/common.py:66` | rollout 渲染传 `enable_thinking=True` | `SLIME_ROLLOUT_THINKING` | T4/T5 |

全部 env 门控、默认 off，main 不动，与 reward shaping 正交不混合。

## Go/No-Go

**Go，进 T1**。理由：无阻塞项；最坏的两种设想（模板不认思考、mask 要重写）都被排除；教师思考是免费存量（API 本来就在返回）；改动面比 plan 预估还小。

T1 建议参数：`SHOP_PI_THINKING=medium`（先中档，pilot 看思考长度再调），24 任务（含 12 条带规格任务），重点观测：思考质量（是否真在核对规格/预算）、accepted 率（对照旧 81%）、单轨迹 token 增量。
