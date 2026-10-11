# 2026-10-11 整理验证

环境：macOS，uv 创建仓库内虚拟环境，CPython 3.13.11。无新增 Python 依赖。

- 恢复补丁：在上游 `3eb68d8` 上适用性检查通过并应用；复制状态清单列出的 5 个新增文件。
- 奖励函数：`uv run python commit-shaping/test_reward_shaping.py`，49 passed / 0 failed。
- 配对复算：E3 与 T4 各 600 条记录、200 个任务、每任务 3 条；运行 `k3_compare.py` 完成 10,000 次 bootstrap，输出 `recomputed-k3.json`。done 配对差 0.041667，95% CI [0.001667, 0.083333]；r_hard 配对差 0.011563，95% CI [-0.030440, 0.054105]。
- 静态检查：18 个恢复或整理涉及的 Python 文件通过 AST 解析；24 个配置或评测 JSON 可解析；12 个历史 shell launcher 通过 `bash -n`。语法通过不代表历史路径和运行依赖可用。
- Gitleaks 8.30.1：扫描待上传文件及完整保留历史。4 处初始命中经源文件核对，均为奖励变体字符串或上游 tokenizer 测试代码；使用限定路径和内容的 allowlist，以及一条特定历史 fingerprint 排除误报。认证配置、完整日志及环境未进入上传目录。
- 不含模型权重或完整原始 rollout；保留本地原始备份。未执行 GPU 训练、在线环境评测或全套上游 CUDA 测试。

本记录说明已做验证及其边界，不表示历史训练已重新复现，也不保证扫描能识别所有敏感信息。
