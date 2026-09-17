# PROJECT_STATUS

## 当前目标

发布诺研 Skill 2.3.1：通过 GitHub Releases 交付 Windows 完整离线安装包，并在指标事实环节提供中英双语速读。

## 正式文件

- `docs/superpowers/specs/2026-09-11-windows-offline-assets-and-bilingual-metrics-design.md`
- `docs/superpowers/plans/2026-09-11-windows-offline-assets-and-bilingual-metrics.md`
- `docs/windows-installation-validation-prompt.md`

## 已完成

- 用户已确认 C 方案：轻量 bootstrap、标准离线资产包、可选 Java/Node 扩展包。
- 已定位翻译缺失根因：现有 Windows 安装依赖在线 pip、Playwright 和 Argos 模型下载，Skill 安装与运行时安装未形成同一闭环。
- 已定位指标事实缺口：双语标签只在 HTML 层临时派生，数据、Excel 和证据卡没有统一字段。
- 已实现 Windows 标准/扩展资产 manifest、路径/大小/SHA-256/许可证校验和只读 `windows-assets` CLI。
- 已实现本地离线资产、内网镜像、公网源三级回退安装器，支持打包 Python、wheelhouse、Chromium 和 Argos 英中模型。
- 已修复 Windows 翻译模型安装依赖裸 `argospm` PATH 的问题，改用 Argos Python API 或显式本地模型路径。
- doctor 已增加 Windows 安装状态、manifest 版本、资产来源和失败记录检查。
- 指标事实已增加中英文指标名、中文解释、数值解释、中文摘录和翻译状态，并贯通 HTML、Excel、Markdown 证据卡。
- 翻译命令已覆盖指标摘录缓存；混合中英文摘录不会再误判为“原文已是中文”。
- HTML 指标表使用独立横向滚动容器，移动端不再撑宽整页，证据卡 ID 不断词。
- Skill、README、Windows 安装指南、报告规则、CLI 契约和发布清单已同步为 2.3.1 行为。
- Windows 标准离线运行时固定为官方 Python 3.13.15；Java/Node 保持可选扩展。
- GitHub Release 流水线可在 Windows Runner 构建标准资产包、源码包、完整离线安装包、SHA-256 清单和验证提示词。
- Windows 官方 Python 已补充 `tzdata` 条件依赖；材料导入持久化路径已统一为跨平台正斜杠格式。
- Argos English→Chinese 1.9 模型的 OPUS-MT、作者和 CC BY 4.0 署名已写入第三方许可证清单。

## 已验证

- 设计文档已通过回读与 `git diff --check`，提交为 `5a05f7a`。
- Task 1：`7 passed`；Ruff、compileall 和 `git diff --check` 通过。
- Task 2：`35 passed`；Ruff、compileall、manifest CLI 和 `git diff --check` 通过。
- Task 3：`85 passed`；Ruff、compileall、模板一致性和 `git diff --check` 通过。
- 浏览器视觉验收：桌面端与 375px 移动端控制台 0 错误；移动端 body/viewport 为 375/375，指标表内部滚动宽度 1056px。
- 发布级本地验证：236 passed、1 skipped；Ruff、compileall、diff 检查和 2.3.0 wheel 资源检查通过；core doctor `ok=true`。
- 用户级安装验证：旧目录保存在 `/Users/sunjing/.codex/backups/nuoyan-skill-v2.backup-20260912-150445`；标准目录已同步提交 `fe16709`；editable 元数据为 `2.3.0`；安装目录全量测试 `236 passed, 1 skipped`；core doctor `ok=true`。备份位于 Skill 发现目录之外，不会被识别为同名 Skill。
- Windows 3.13 64 位 Argos 依赖预检已下载 64 个官方 PyPI wheel，共约 206 MB，包含 `ctranslate2`、`torch`、`spacy` 等关键二进制依赖。
- Windows 验证交接包已生成：`packages/nuoyan-windows-validation-2.3.0.zip`，SHA-256 为 `30c81676c39b2121382c6e5c9ad2cdafc6389b73307622dc151588877f9b4c0e`。
- GitHub Windows 分支门禁通过：244 项测试、Ruff、compileall、diff check、标准资产构建和完整安装包组装全部成功。

## 待办

- 发布 `v2.3.1` GitHub Release，并在干净 Windows 10/11 主机做最终离线安装验收。

## 下一步

从 GitHub Release 下载完整离线安装包，在干净 Windows 10/11 目标机完成安装验收。
