# 阶段 0 报告：隔离准备

日期：2026-09-01
计划依据：`/root/autodl-tmp/reward_shaping_plan.md` 第 11 节（隔离与可逆性方案）

## 执行内容

| 步骤 | 操作 | 结果 |
| --- | --- | --- |
| 1. git 分支 | `git switch -c reward-shaping`（仓库 `pi-slime-shopsimulator`） | 成功，当前分支 `reward-shaping` |
| 2. 既有修改核对 | `git status --short` | 5 个本地修改（`build_conda.sh`、`run_rl.sh`、`run_sft.sh`、`logging_utils.py`、`wandb_utils.py`）完好随工作区带入新分支，未做任何提交/改动 |
| 3. 工作目录 | `mkdir runs/reward_shaping/`；复制 `runs/asin_audit/prices.json` → `runs/reward_shaping/prices.json` | 完成（734 KB，23,421 条确定性定价） |

## 隔离状态确认

- `main` 分支无任何新提交，随时 `git switch main` 可回到实验前状态；
- ShopSimulator 环境仓库（detached HEAD + 补丁）未触碰；
- `runs/asin_audit/` 保持只读存档，本阶段仅从中复制出 `prices.json`；
- 本阶段无新增代码、无数据文件原地修改，零破坏面。

## 当前分支基线

- 分支点：`main`（含上述 5 个未提交修改的工作区状态）。
- 后续所有 shaping 代码（`reward_shaping.py`、`generate.py` hook）将只出现在本分支。

## 下一步

阶段 1：导出 `task_budget.json`（指令预算表）、生成 `rl_500_clean.jsonl`（黑名单任务文件）、切 `dev_200.jsonl`。
