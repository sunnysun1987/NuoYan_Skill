# Windows 标准调研环境安装与使用

## 适用对象

本方案用于公司 Windows 电脑部署诺研 Skill。业务同事不执行命令行，不自行安装 Python 包，也不配置 API Key。首次安装、更新和环境修复由 Codex 或 IT 使用仓库根目录的 `install-windows.ps1` 完成。

## 结论

仅把 `SKILL.md` 更新到新版本，不等于完整更新。标准调研环境同时依赖以下四层：

1. 标准目录中的最新诺研代码；
2. 诺研专用 Python 3.11 虚拟环境及 PDF、浏览器、翻译组件；
3. 可实际启动的 Playwright Chromium 和 English→Chinese 离线翻译模型；
4. Codex 中已启用的 Life Science Research、Browser、Chrome 插件，以及可用的公网采集通道。

开发电脑通常已经具备其中多数工具，因此只更新 Skill 也可能正常运行；业务电脑缺少这些组件时，Codex 会退化为聊天式调研，无法稳定执行标准流水线。这是两类电脑表现不一致的主要环境原因。

## IT 前置条件

- Windows 10/11 64 位；
- 已安装当前公司批准版本的 Codex 桌面应用；
- Git for Windows；
- Python 3.11 64 位，安装自 python.org，包含 `py` launcher；
- 可访问 GitHub、Playwright 浏览器下载、Argos 模型源、PubMed/NCBI 和 OpenAlex，或由 IT 提供对应离线包与代理；
- Codex 插件管理中安装并启用 Life Science Research、Browser、Chrome。

脚本只接受标准目录 `%USERPROFILE%\.codex\skills\nuoyan-skill-v2`，并在该目录内创建 `.venv`。它不会向系统 Python 执行 `pip install --user`，也不会自动修改 Codex 插件配置。

## 给业务同事的使用方式

业务同事在 Codex 中发送以下提示词，不需要打开 PowerShell：

> 请检查并更新本机的诺研 Skill 标准调研环境。请由你运行安装目录中的 install-windows.ps1，完成代码更新、专用虚拟环境、Playwright Chromium、PDF 和离线英中翻译组件检查，再运行标准环境严格体检。不要让我执行命令行。若 Codex 插件需要我在应用内启用，请明确告诉我插件名称和重启步骤；体检通过后再开始调研。

正式调研时仍使用自然语言提出业务课题。Codex 负责调用内部 CLI、生成调研文件并说明证据缺口，业务同事不直接操作 `nuoyan` 命令。

## IT 安装与更新

在公司允许的 PowerShell 中执行仓库根目录脚本。首次运行会克隆或更新标准目录、创建隔离环境、安装完整组件并执行严格体检：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install-windows.ps1
```

完成应用内插件启用并重启 Codex 后，只复查环境：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install-windows.ps1 -VerifyOnly
```

脚本最终执行的验收命令等价于：

```powershell
.venv\Scripts\nuoyan.exe doctor --profile standard --network --strict --json
```

退出码为 0 且 `standard_ready=true` 才表示标准调研环境可用。生成 HTML 或 Excel 文件只说明交付文件已生成，不代表 `business_ready=true`；正式项目仍需完成证据来源、人工复核和业务门禁。

## 常见结果与处理

| 失败项 | 含义 | 处理责任 |
| --- | --- | --- |
| `runtime_source` | 当前命令加载的不是标准安装目录，或包版本与工作流版本不一致 | IT 重新运行安装脚本，检查旧 PATH/旧包 |
| `distribution_conflict` | 旧版包仍占用 `ivd_research` 命名空间 | IT 删除旧虚拟环境并重建，不在系统 Python 混装 |
| `playwright_browser` | Python 包存在，但 Chromium 未安装或无法启动 | IT 检查下载、终端安全软件和执行权限 |
| `translation_engine` | Argos 包或 English→Chinese 模型缺失 | IT 允许模型下载或导入批准的离线模型 |
| `life_science_plugin` | 插件可能已缓存，但当前 Codex 未启用 | 用户在 Codex 插件管理中启用并重启 |
| `browser_plugin` / `chrome_plugin` | Codex 浏览器能力未启用 | 用户在 Codex 插件管理中启用并重启 |
| `network_preflight` | PubMed/OpenAlex 的 Python HTTPS 和 curl 通道均不可用 | IT 配置代理、DNS、证书或站点白名单 |
| `ocr_runtime` | 扫描件 OCR 不可用 | 可选项；需要扫描 PDF 时由 IT 补装 Tesseract |

## 验收记录

IT 应保存严格体检 JSON，并记录安装日期、代码版本、Python 路径、失败项和处理结果。出现同事间结果差异时，先比较 `runtime_source`、`distribution_version`、`python_executable` 和插件 `enabled` 字段，不再只比较界面显示的 Skill 名称。
