# 复现范围与缺失材料

## 已恢复并可验证

- 原始基线 Git 提交、12 个文件改动和 5 个新增文件。
- 奖励函数的 49 项标准库测试；测试自建模拟表，不依赖真实商品数据。
- E3/T4 official k=3 两组 `eval_results.json`；可进行任务级配对 bootstrap 分析。
- 筛选后的实验计划、阶段报告、训练/评测命令与分析脚本。

## GPU 训练尚未重跑

原实验在 Linux CUDA 环境执行。本次为 macOS 上的代码恢复、资料整理和离线复算。不能据此声称整套训练已在当前仓库重新跑通。

完整重训还需要：

1. 按 UPSTREAM_README.md 准备 Pi、slime、Megatron-LM、SGLang 和外部 ShopSimulator 服务。
2. 准备 Qwen3.5-2B 以及对应的 HF / Megatron checkpoint；历史思考 SFT checkpoint 不在本仓库。
3. 查找或重新生成个人实验使用的数据。历史配置引用的 `runs/reward_shaping/dev_200.jsonl`、`rl_490_clean.jsonl`、`smoke_20.jsonl`，以及 legacy shaping 使用的 `task_dims.json`、`task_budget.json`、`prices.json` 未在本次资料中找到。上游自带任务切片不等于这些历史派生文件。
4. 准备思考蒸馏教师轨迹与训练样本；本次保存的是分析脚本和报告，没有上传全量教师样本。
5. 将历史 launcher、配置与命令中的 `/root/autodl-tmp` 路径适配至新机器，显式配置模型和环境路径。不要直接运行历史 launcher。

奖励函数在缺少某些表时会退回原奖励；不能把这种退回当作目标实验已正确复现。纯过程奖励与 legacy 表驱动变体的依赖不同，运行前按具体变体核对。

## 上传范围

纳入代码、报告、聚合指标、命令文本及 3 条代表性转写。排除模型权重、`.pt` rollout、全量日志、原始认证配置、环境目录和压缩备份。

历史 HANDOFF.md 和报告按原始记录保留，含当时机器路径、未提交状态和未随仓库上传的文件引用；它们是实验档案，不是当前仓库的安装说明。当前使用入口以根 README 为准。

代表性转写仅恢复模型输出和动作骨架，不包含完整的环境页面上下文。公开仓库前可再次检查这些案例和数据的展示范围。
