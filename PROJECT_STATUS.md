# PROJECT_STATUS

## 当前目标

发布诺研 Skill 2.3.0：完善 Windows 离线资产安装与回退，并在指标事实环节提供中英双语速读。

## 正式文件

- `docs/superpowers/specs/2026-09-11-windows-offline-assets-and-bilingual-metrics-design.md`
- `docs/superpowers/plans/2026-09-11-windows-offline-assets-and-bilingual-metrics.md`

## 已完成

- 用户已确认 C 方案：轻量 bootstrap、标准离线资产包、可选 Java/Node 扩展包。
- 已定位翻译缺失根因：现有 Windows 安装依赖在线 pip、Playwright 和 Argos 模型下载，Skill 安装与运行时安装未形成同一闭环。
- 已定位指标事实缺口：双语标签只在 HTML 层临时派生，数据、Excel 和证据卡没有统一字段。
- 已实现 Windows 标准/扩展资产 manifest、路径/大小/SHA-256/许可证校验和只读 `windows-assets` CLI。

## 已验证

- 设计文档已通过回读与 `git diff --check`，提交为 `5a05f7a`。
- Task 1：`7 passed`；Ruff、compileall 和 `git diff --check` 通过。

## 待办

- 实现离线优先、内网/公网回退安装器。
- 实现指标事实双语数据和三端展示。
- 更新 Skill、版本、文档和发布验证记录。
- 在干净 Windows 10/11 主机做最终离线安装验收。

## 下一步

按实施计划执行 Task 2：Windows 离线安装与来源回退。
