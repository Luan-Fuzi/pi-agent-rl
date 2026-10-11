# R0 基线 · dev_200 验收表

日期：2026-09-01 · 运行目录：`runs/qwen35_2b_shop_eval_rl_r0_dev/` · 评测口径：原始 env reward（shaping OFF，已自证：200/200 条 `reward_shaping={}` 且 reward==env_reward_raw）

模型：`runs/qwen35_2b_shop_rl`（rl_500 原始 reward GRPO 100 step，即复现基线）
数据：`dev_200.jsonl`（dev 池 2193 条抽 200，seed=20260901，与 official_test_200 零重叠，k=1）

## 指标

| 指标 | R0 @ dev_200 | 参考：R0 @ official_test_200（审计值） |
|---|---|---|
| done 率 | 91.5% (183/200) | 82%（未下单 18%） |
| right_full（买对满分） | 60.5% | 26.5% |
| right_partial（买对部分） | 15.5% | 11.0% |
| wrong_high（买错高分≥0.5） | 3.5% | 23.5% |
| wrong_low（买错低分） | 12.0% | 21.0% |
| no_buy | 8.5% | 18.0% |
| right product 率 | 76.0% 全体 / 83.1% done | 37.5% |
| r_option 均值（done） | 0.698 | 0.334 |
| r_att 均值（done） | 0.888 | — |
| 预算合规率（有预算的购买） | **66.7%** (106/159, tol×1.05) | 81.5% |
| 超预算仍 env r_price=1 | **49 条**（占有预算购买的 30.8%） | 18.5% |
| 高分规格落空（wrong_high 且 r_option=0 且有规格） | 6 条（3.0%） | 18% |

## 读数

1. **dev_200 明显比 official_test_200 简单**：right_full 60.5% vs 26.5%，r_option 0.698 vs 0.334。两集分布差异大，再次印证基线必须同集重测，不能挪用审计值。
2. **budget 病灶在 dev 赛场更严重**：30.8% 的有预算购买超预算仍拿 r_price=1（official_test 为 18.5%），预算合规率仅 66.7%。R2/R3 的 budget 修复收益在 dev 上应该比 official_test 上更可见。
3. **wrong_high 在 dev 上已很低（3.5%）**：R1 的 option_gate 主要应体现为 r_option 均值和 right_partial → right_full 的转化（31 条 partial 里多少因规格失分），而非 wrong_high 下降。
4. 后续对比以本表为分母：预算合规率、r_option、right product、right_full 四个主指标。
