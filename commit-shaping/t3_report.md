# T3 阶段报告：E1（milestones）阳性，双线继续

日期：2026-09-05（训练 09-04 18:00 → 09-05 06:22，约 12.4h；dev 评测 06:24–06:53）
RUN_ROOT：`runs/qwen35_2b_shop_rl_commit_e1/`（终版 `hf/rollout_99`）
评测：`runs/qwen35_2b_shop_eval_commit_e1_dev/`（dev_200，k=1，seed 42，shaping OFF，与 T4 同口径）
配置：逐项对齐 T4（rl_500、100 step、n=4、lr 1e-6、KL 0.001、seed 全同），唯一变量 `SHOP_REWARD_SHAPING=milestones`

## 1. 预注册双轴判定：**阳性**

| 判据轴 | E1 dev | T4 dev | Δ | 阈值 | 结论 |
|---|---|---|---|---|---|
| done_rate | **0.950** | 0.875 | **+7.5pt** | ≥ +3pt | ✓ 过线 |
| r_hard | **0.683** | 0.662 | **+2.1pt** | 不掉出 ±3pt | ✓ 过线（且同向改善） |

**核心假设成立**：非 done 轨迹的里程碑分级分在零方差组内制造了"买过 > 差点买 > 打转 > 放弃"的排序，回收了 done 率且没有吐回 r_hard——与 R1/R2 的"信号变行为不动"形成对照，本次差异（在 GRPO 此前完全无信号处制造信号）得到了验证。

## 2. 指标全景（E1 dev vs T4 dev）

| 指标 | E1 | T4 | Δ |
|---|---|---|---|
| done_rate | 0.950 | 0.875 | +7.5pt |
| r_hard（判据） | 0.683 | 0.662 | +2.1pt |
| r_loose | 0.841 | 0.782 | +5.9pt |
| r_option | 0.698 | 0.666 | +3.2pt |
| r_success | 0.645 | 0.635 | +1.0pt |
| right_product | 0.805 | 0.755 | +5.0pt |
| r_att / r_price / r_type | 0.862 / 0.930 / 0.950 | 0.804 / 0.845 / 0.875 | 全面上升 |

终止结构：非 done 仅 10 条（7 turn_limit + 3 agent_stop），T4 dev 为 25 条——**打转/放弃减半以上**，正是 E1 的靶向。

## 3. 审计口径（acceptance.py，dev_200）

- 象限：right_full 64.5% / right_partial 16.0% / wrong_high 5.5% / wrong_low 9.0% / no_buy 5.0%
- 高分规格落空率 **3.0%**（审计基线 RL 18%，T4 路线叠加 E1 后基本肃清）
- done 中 r_option 均值 0.735（acceptance 口径，全样本口径 0.698）
- 预算合规 69.3%（tol×1.05 口径；budget 明确不在本路线，仅记录）

## 4. 训练期观察

- 中途抽查（rollout_40）：20 candidate 中 13 done（均分 0.904），7 条非 done 全部拿到里程碑分（1×lv1 + 5×lv2 + 1×lv3），变体隔离正确（antiloop 未触发——属 E2）
- 100 rollout 全部完成，存档 24/49/74/99 + HF export 全齐；无事故

## 5. 产物处置与下一步

- 中期存档已 prune（iter_0000024/49/74 + hf/rollout_24/49/74，释放 ~21.6G）；保留终版 `checkpoints/iter_0000099` + `hf/rollout_99`（E1 若夺冠，T6 需要它跑 test）
- **T4（E2）启动**：`SHOP_REWARD_SHAPING=milestones+antiloop`，同 T3 SFT 起点，同 100 step。判定锚点仍是 T4 dev 双轴
