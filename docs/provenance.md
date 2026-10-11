# 来源与恢复记录

整理日期：2026-10-11。实验记录日期：2026-09-06 及之前。

## 上游

基础代码来自 https://github.com/Piucente/pi-slime-shopsimulator ，本地基线为 `3eb68d8`（Initial release: Pi + Slime + ShopSimulator workflow）。本仓库保留该提交、作者信息、LICENSE、THIRD_PARTY.md、CHANGES.md 和原 README。上游历史结果属于原作者，不作为本人的新增实验成果。

## 个人修改恢复

从秋招资料目录的 `handoff_pack/repo_snapshot/changes.patch` 恢复 12 个已修改文件，并复制快照中的 5 个新增文件：奖励函数、dev 与 official k=3 评测配置、clean 与 smoke 训练配置。原状态清单和交接记录相互对应。

新增代码与修改覆盖：思考数据准备、rollout 思考开关、奖励整形、动作序列及过程统计、评测入口与 SwanLab 日志适配。原训练机上的改动当时未提交；现在以实际整理日期提交恢复快照，不伪造 9 月提交历史。

后续整理只将奖励测试和 k=3 复算脚本的模块路径改为相对仓库定位，筛选实验资料并补充文档。未重新运行 GPU 训练，未把历史测试结果当作本次运行结果。

## 仓库与备份

账号下已有公开上游 fork `Luan-Fuzi/pi-slime-shopsimulator`。本次先另建 `Luan-Fuzi/pi-agent-rl` 作为独立私有仓库，再于 2026-10-11 按用户要求改为公开；Git 历史仍保留上游基线，原公开 fork 未改动。

原始产物包 `handoff_artifacts_20260906.tar.gz` 继续保留本地，SHA-256：
`e8bb8a4693543b2720ddee9f068e370fd210f9d633ff7c6e922ec9de660ece17`。

整理后的文件与原始记录差异可通过 Git 查看；筛选范围及缺项见 reproduction.md。
