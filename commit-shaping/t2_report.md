# T2 阶段报告：E0 冒烟验收通过

日期：2026-09-04（17:21 启动，17:56 完成，约 35 分钟 GPU）
RUN_ROOT：`runs/qwen35_2b_shop_rl_commit_e0_smoke/`（验收后已删，磁盘纪律）
配置：`shop_rl_smoke.json`（20 任务 × 4 candidate = 4 rollout / 4 step），从 T3 SFT checkpoint 起跑，`SLIME_ROLLOUT_THINKING=1`，`SHOP_REWARD_SHAPING=milestones+antiloop+efficiency`（全组件一次验）

## 验收三项

| 检查 | 结果 |
|---|---|
| 过程统计进 metadata | **80/80** candidate 均有 `process_stats` 与 `action_sequence`，无缺失 |
| shaping 触发 | 非 done 12 条全部拿到里程碑分（级别 1/2/3 = 2/7/3），antiloop 罚则按公式结算（例：lv3 0.15−0.07=0.08；罚额超阶梯分正确封底 0）；done 68 条 efficiency 生效（9 轮 →×1.0，25 轮 →×0.975） |
| 链路无回归 | 4/4 step 训完，Megatron checkpoint + HF export 正常落盘，Ray job succeeded；训练指标正常（logprob diff 0.009，与 T4 同量级） |

## 抽查样例（task 8390，agent_stop，37 轮）

动作序列真实还原"search→开页→规格→buy"链；统计：17 次搜索 / 3 开页（2 asin）/ 4 规格 / 1 buy → lv3 0.15 − 0.07 = 0.08。发现末位动作存在裸 `back to search`（无 `click[]` 包裹）——parser 正确归入 malformed，不污染里程碑。

## 启动事故记录（供复跑参考）

首次启动失败：`ray job submit` 的 train.py 入口按**提交时 cwd** 解析，从 `/root/autodl-tmp` 启动 run_rl.sh 会报 `can't open file '/root/autodl-tmp/train.py'`。修复：`commit-shaping/run_e0_smoke.sh` 内 `cd "$SLIME_DIR"` 后再调 run_rl.sh（历史 run 天然满足是因为从仓库目录起的）。launcher 脚本已带注释。

## 产物处置

RUN_ROOT（7.2G：checkpoint 3.6G + HF 3.6G + dumps 19M）验收后删除；`shop_env_server_commit.log` 与 launcher.log 保留（KB 级）。环境服务（bash-n6d1pb85）保持运行，供后续 E1 使用。

## 下一步

T3：E1 正式训练（`SHOP_REWARD_SHAPING=milestones`，rl_500，100 step，SAVE_INTERVAL=25，~13h）+ dev_200 双轴判（done ≥ T4+3pt 且 r_hard 不掉出 ±3pt；阴性即停）。
