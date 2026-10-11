# T1.5 收尾报告：带思考的 SFT 数据就绪

日期：2026-09-03
分支：`thinking-distill`（未提交）
产物：`runs/thinking_sft/prepared/`（turn_examples.jsonl 6359 条）

## 结论

**数据就绪，可进 T3。** 改动 #4 落地，6359 个 turn 样本与旧版一一对应（同轨迹同 turn），6166 条（96.9%）目标 turn 带教师思考，0 条因超长被裁，渲染/mask 抽查 10/10 通过。

## 链路实现（改动 #4，`prepare_sft.py`）

- 思考来源：raw 文件的 `events`（`message_end` 事件），不是 `messages` 字段——后者在采集时就被剥了思考
- 对齐关系：events 不含 system 消息，events[i] ↔ `messages[i+1]`。逐条验证剥思考后 dict 全等：**414/414 全部对齐**，0 错位
- 目标 turn：思考写入 qwen 消息的 `reasoning_content` 字段（T0 路径 A，模板自己拼装 `<think>` 块）
- 历史 turn：trace 来自 context 快照，本就无思考（pi wire 不回传历史思考，采集侧已按此构建）——训推一致自动成立，无需额外剥离
- 防御：events 对齐失败按 `events_alignment_mismatch` 拒收（实测 0 例）；`rglob` 补了 dotfile 过滤（与重建脚本同款，防 `.ipynb_checkpoints` 重复文件混入）

## 产出对比（旧 → 新）

| 指标 | 旧版（无思考） | 新版（带思考） |
|---|---|---|
| candidates / accepted | 512 / 414 | 512 / 414 |
| turn examples | 6359 | 6359 |
| 带思考目标 turn | 0 | **6166（96.9%）** |
| 超长拒绝（>16384） | 0 | 0 |
| token_count mean / p95 / max | 2404 / 4492 / 13463 | 2569 / 4783 / 13719 |
| target_token_count mean | 40.7 | 207.1 |

思考长度（字符，n=6166）：p10=62，中位=295，p90=1131，max=15526。带思考样本的目标 token：mean 212，p95 631，max 4163。193 个无思考目标 turn 保留在数据集中（无 reasoning_content，行为同旧版）。

## mask 抽查（10 条随机带思考样本，`qc_prepared_thinking.py`）

逐条验证（10/10 通过）：

- `reasoning_content` 只出现在最后一条 assistant 消息（目标 turn）
- `<|im_start|>assistant\n<think>\n` 开壳紧邻第一个 mask=1 token 之前，开壳本身 mask=0
- 思考正文 mask=1；`</think>` 闭壳 mask=1；正文/工具调用/`<|im_end|>` mask=1
- 渲染全文仅 1 个非空 think 块（其余历史 assistant turn 为空壳），历史/系统/用户/工具全 mask=0

## 风险登记更新

- "历史思考残留导致训推失配"：数据侧已闭环（历史本无思考）。剩余一环在 rollout 侧——adapter `openai.py:135-137` 会透传 wire 上的 `reasoning_content`，需确认 pi 客户端不回传历史思考（teacher 链路 wire 抓包已证 pi 不回传；2B rollout 链路 T4 smoke 复核）
- 193 个无思考目标 turn（3.1%）混在训练里，模型学到的行为是"绝大多数 turn 思考、偶尔不思考"，与教师天然分布一致，不处理

## 下一步

T3：同配置新 SFT，数据指向 `runs/thinking_sft/prepared/turn_examples.jsonl`，RUN_ROOT `runs/qwen35_2b_shop_sft_thinking/`。
