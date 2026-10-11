# Pi Agent RL：购物 Agent 后训练实验

基于 Qwen3.5-2B，在 ShopSimulator 中文购物环境中研究多轮工具调用的 SFT、在线 GRPO、思考蒸馏与过程奖励整形。本仓库整理个人实验代码、评测结果和失败分析，代码与实验资料现已公开，原始大体积产物继续保留本地备份。

本项目基于 [Piucente/pi-slime-shopsimulator](https://github.com/Piucente/pi-slime-shopsimulator) 的训练参考实现开展实验。上游提供 Pi、slime 与 ShopSimulator 的基础集成及教师采集、SFT、GRPO 和评测流程；本人在此基础上加入思考蒸馏、奖励整形、过程统计和相关评测分析。感谢原作者提供基础实现。上游原 README 保存在 [UPSTREAM_README.md](UPSTREAM_README.md)，具体修改边界见 [来源与恢复记录](docs/provenance.md)。

## 实验做了什么

- **思考蒸馏**：整理带思考的教师轨迹，调整 SFT 数据准备与 rollout 思考开关，比较精度和完成率的变化。
- **奖励整形**：先探索属性、规格和预算约束，再加入 `milestones`、`antiloop`、`efficiency` 过程奖励组件；默认关闭，通过环境变量选择实验变体。
- **行为与失败分析**：记录动作序列、过程统计、退出原因和交互轮数，分析未下单、重复探索与轮数耗尽。
- **对照评测**：保留 dev 消融与 official test 配对复测，评测时关闭 shaping，按环境原始指标比较。

Pi 是驱动模型调用工具、执行动作和接收反馈的 Agent 运行时；slime 编排训练，Megatron-LM 负责训练计算，SGLang 负责推理，ShopSimulator 提供交互与奖励。

## 主要结果

以下为 2026-09 的历史实验；2026-10-11 在本机从已保存的评测 JSON 复算，未重新训练模型。E3 为 `milestones+efficiency`，T4 为思考基线；同 200 个任务，每任务 3 次采样，两臂各 600 条轨迹。

| 指标 | T4 | E3 | 差值 |
|---|---:|---:|---:|
| 下单完成率 done | 76.3% | 80.5% | +4.2 个百分点；95% CI [+0.2, +8.3] |
| 严格质量分 r_hard | 0.392 | 0.403 | +0.012；95% CI [-0.030, +0.054] |
| 已完成轨迹平均模型轮数 | 17.4 | 15.3 | 约 -2.1 轮 |

完成率收益较小，`r_hard` 未显示明确提升；轮数耗尽仍是主要失败来源。非思考对照中未观察到相同的 milestones 收益。不能把这些结果概括为所有指标普遍提升。

- [完整结论与消融](runs/commit_shaping/report.md)
- [本机复算结果](docs/recomputed-k3.json)
- [奖励整形历史报告](runs/reward_shaping/report.md)
- [3 条代表性轨迹](examples/episodes.jsonl)：成功、轮数耗尽、Agent 停止各一条；仅含模型侧转写，不含完整环境页面。

## 本机可运行的检查

仅需要 Python 3.10+ 和 uv，不需要 GPU 或训练依赖。以下命令从仓库根目录执行：

```bash
uv venv
uv run python commit-shaping/test_reward_shaping.py
uv run python commit-shaping/k3_compare.py \
  --e3 runs/qwen35_2b_shop_eval_commit_e3_official_k3 \
  --t4 runs/qwen35_2b_shop_eval_rl_thinking_official_k3
```

第一条脚本覆盖奖励函数的 49 项测试；第二条以任务级配对差和 bootstrap 复算已保存的评测记录。复算历史指标不等于重现训练过程。

## 训练与环境准备

基础环境、Pi 版本、ShopSimulator 补丁与四阶段运行方法见 [上游使用说明](UPSTREAM_README.md)。本仓库保留其目录结构及 `slime/examples/ShopSimulator/` 入口。

个人实验的 `commit-shaping/*.sh`、`thinking-distill/` 脚本和 `runs/**/*command.txt` 是原训练机记录，仍可能包含 `/root/autodl-tmp` 路径，不能直接在新机器执行。完整重训前必须准备 CUDA 训练环境、模型 checkpoint、ShopSimulator 服务和实验数据，并按新机器修改配置；具体已知缺项见 [复现范围与缺失材料](docs/reproduction.md)。

## 文件导航

| 路径 | 内容 |
|---|---|
| `slime/` | 上游 vendored 代码及恢复的个人改动 |
| `shopsimulator_patch/` | 上游保留的 ShopSimulator 集成补丁，不包含完整环境源码 |
| `commit-shaping/` | 实验计划、原始 launcher、奖励测试、配对复算与阶段报告 |
| `thinking-distill/` | 思考蒸馏分析脚本与阶段报告 |
| `runs/` | 筛选的报告、聚合评测 JSON 与运行命令 |
| `examples/` | 少量代表性轨迹 |
| `docs/` | 来源、复现边界、本次验证与文件校验清单 |

模型权重、原始 `.pt` rollout、完整训练日志、密钥、探针认证配置和本地运行环境未上传；完整本地备份仍保留。历史报告中的路径可能指向这些未上传材料。

## 许可与来源

保留上游 [MIT LICENSE](LICENSE)、[第三方说明](THIRD_PARTY.md) 和 `slime/LICENSE`。根许可证不覆盖第三方组件，也不改变数据及模型的使用条件。上游记录指出 ShopSimulator 完整源码的再分发许可未明确，本仓库继续沿用外部获取与补丁方式。
