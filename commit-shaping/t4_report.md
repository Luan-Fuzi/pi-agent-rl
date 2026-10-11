# T4 阶段报告：E2（milestones+antiloop）一涨一平，E1 保持胜者

日期：2026-09-05（训练 06:41 → 18:49，约 12.1h；dev 评测 18:50–19:22）
RUN_ROOT：`runs/qwen35_2b_shop_rl_commit_e2/`（终版 `hf/rollout_99`）
评测：`runs/qwen35_2b_shop_eval_commit_e2_dev/`（dev_200，k=1，seed 42，shaping OFF，同口径）
配置：与 E1 唯一差异 `SHOP_REWARD_SHAPING=milestones+antiloop`

## 1. 预注册双轴判定（vs T4 dev）：**不确定（一涨一平）**

| 判据轴 | E2 dev | T4 dev | Δ | 结论 |
|---|---|---|---|---|
| done_rate | 0.885 | 0.875 | +1.0pt | 未达 +3pt 阈值 |
| r_hard | **0.705** | 0.662 | **+4.3pt** | 超出 ±3pt 带上沿（超噪声改善） |

按预注册规则（双轴缺一不可），E2 不算干净的阳性；按"一涨一掉记不确定"的精神如实记录——实际是一涨（r_hard）一平（done）。

## 2. 三方对比（dev_200）

| 指标 | T4 | E1 | E2 |
|---|---|---|---|
| done_rate | 0.875 | **0.950** | 0.885 |
| r_hard | 0.662 | 0.683 | **0.705** |
| r_success | 0.635 | 0.645 | **0.685** |
| r_option | 0.666 | 0.698 | **0.711** |
| r_loose | 0.782 | **0.841** | 0.802 |
| right_product | 0.755 | **0.805** | 0.770 |
| 非 done 条数 | 25（18 tl + 7 as） | **10（7 tl + 3 as）** | 23（17 tl + 6 as） |

## 3. 归因：antiloop 的代价机制

E2 相对 E1：done -6.5pt 换回 r_hard +2.2pt / r_success +4.0pt。罚则压住了打转（罚面真实存在：训练中可见 lv3×penalty0.21 案例），但有两个未预期的反作用：

1. **罚穿封底重建零方差**：重打转轨迹 milestone 0.15 − penalty 0.21 → 地板 0，与"完全无推进"的 0 分再次同分——antiloop 在底部把 E1 辛苦制造的方差又抹掉了。这是设计内生的：罚则越强，触底越多。
2. **过度持续的合法部分被误伤**：turn_limit 从 E1 的 7 回到 17（T4 为 18）——"再坚持一下就买到"的轨迹与"纯打转"在过程统计上共享表面特征（重开、重复搜索），罚则无法区分意图，把 E1 回收的一部分坚持又罚了回去。

净效果：精度指标（r_hard/r_success/r_option 三高）提升，数量指标（done）回落。**按计划主线目标（治"不敢下单"、回收 done 率），E1 是胜者**；E2 证明精度还有挤压空间，但手段不是这个罚则。

## 4. 产物处置与下一步

- E2 中期存档已 prune（iter_0000024/49/74 + hf/rollout_24/49/74）；终版保留至 T6（若 E3 翻车，冠军在 E1/E2 间产生）
- **T5（E3）**：`milestones+efficiency`（胜者 E1 之上叠效率衰减，对齐计划 §3"非 done 由 E1 管"）。从 T3 SFT checkpoint 起跑，同 100 step。E3 同时构成 E1 的独立消融臂：E2=E1+antiloop、E3=E1+efficiency，归因干净
