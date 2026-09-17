# Windows 标准调研环境安装与使用

## 适用对象

本方案用于公司 Windows 电脑部署诺研 Skill。业务同事可以从 GitHub Release 下载完整离线安装包并双击安装，不需要输入命令、不自行安装 Python 包，也不配置 API Key。环境体检未通过时，由 Codex 或 IT 根据日志完成修复。

## 结论

仅把 `SKILL.md` 更新到新版本，不等于完整更新。标准调研环境同时依赖以下四层：

1. 标准目录中的最新诺研代码；
2. 诺研专用 Python 3.13 虚拟环境及 PDF、浏览器、翻译组件；
3. 可实际启动的 Playwright Chromium 和 English→Chinese 离线翻译模型；
4. Codex 中已启用的 Life Science Research、Browser、Chrome 插件，以及可用的公网采集通道。

开发电脑通常已经具备其中多数工具，因此只更新 Skill 也可能正常运行；业务电脑缺少这些组件时，Codex 会退化为聊天式调研，无法稳定执行标准流水线。这是两类电脑表现不一致的主要环境原因。

## V2.3.0 安装包结构

- `install-windows.ps1`：轻量入口，委托给 `packaging/windows/install-windows.ps1`。
- `INSTALL_NUOYAN.cmd`：完整离线包中的双击安装入口。
- 标准离线资产包：Python 3.13.15 Windows 安装器、Python wheelhouse、Playwright Chromium、Argos Translate English→Chinese 模型、release manifest 和第三方许可证清单。
- 可选扩展资产包：仅为后续明确需要 Java/Node 的控件准备；Java/Node 不属于当前诺研标准运行时，也不进入 `standard_ready` 门禁。
- `sources.json`：可选的企业内网镜像和公网回退策略；参考 `packaging/windows/sources.example.json`。

安装器固定按“本地离线资产 → 企业内网镜像 → 官方公网源”查找。每个资产必须通过 manifest 中的大小和 SHA-256 校验。离线资产损坏时不会静默使用；安装器会删除无效下载缓存、尝试下一来源，全部失败后停止并指出缺失项。

仓库不提交数百 MB 的二进制运行时。`v2.3.0` 标签触发 GitHub Actions 在 Windows 环境构建和发布标准资产包、源码包、校验文件与完整离线安装包。企业也可以在批准的 Windows 构建机运行 `packaging\windows\build-assets.ps1`，通过内网镜像、U 盘、企业文件共享或软件分发平台交付相同资产。

## IT 前置条件

- Windows 10/11 64 位；
- 已安装当前公司批准版本的 Codex 桌面应用；
- 使用标准离线资产包时，不要求业务电脑预装 Git、Python、Playwright 或 Argos 模型；
- 未提供完整离线包时，需要企业内网镜像或允许访问对应官方源；
- 正式调研仍需访问 PubMed/NCBI、OpenAlex 等公开信源，或使用项目既有的合法浏览器/人工导入兜底；
- Codex 插件管理中安装并启用 Life Science Research、Browser、Chrome。

脚本只接受标准目录 `%USERPROFILE%\.codex\skills\nuoyan-skill-v2`，并在该目录内创建 `.venv` 和 `.nuoyan\install-state.json`。它不会向系统 Python 执行 `pip install --user`，也不会自动修改 Codex 插件配置。

## 给业务同事的使用方式

打开 [GitHub Releases 最新版本](https://github.com/sunnysun1987/NuoYan_Skill/releases/latest)，下载 `nuoyan-windows-offline-installer-2.3.0.zip`。完整解压后双击 `INSTALL_NUOYAN.cmd`，等待安装和体检完成。安装包内已包含 Skill 源码、Python 3.13、Python 依赖、Playwright Chromium 和 Argos 英中模型，不要求电脑预装 Git、Python、Node 或 Java。

安装完成后，在 Codex 插件管理中启用 Life Science Research、Browser、Chrome 并重启 Codex。命令窗口退出码为 0 且体检 JSON 中 `standard_ready=true`，才表示标准调研环境可用。体检失败时保留完整窗口内容并交给 Codex 或 IT。

业务同事在 Codex 中发送以下提示词，不需要打开 PowerShell：

> 请检查并更新本机的诺研 Skill 标准调研环境。请由你运行安装目录中的 install-windows.ps1，完成代码更新、专用虚拟环境、Playwright Chromium、PDF 和离线英中翻译组件检查，再运行标准环境严格体检。不要让我执行命令行。若 Codex 插件需要我在应用内启用，请明确告诉我插件名称和重启步骤；体检通过后再开始调研。

正式调研时仍使用自然语言提出业务课题。Codex 负责调用内部 CLI、生成调研文件并说明证据缺口，业务同事不直接操作 `nuoyan` 命令。

## IT 构建与高级部署

先在批准的 Windows 构建机生成标准离线资产包：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\packaging\windows\build-assets.ps1
```

构建完成后，必须审阅 release manifest、实际文件大小、SHA-256 和 `THIRD_PARTY_LICENSES.txt`，再把 `nuoyan-windows-standard-assets-2.3.0.zip` 与 Skill 源码包一起交付。模板 manifest 的 `release_ready=false` 和全零哈希不能用于正式安装。

在业务电脑执行离线安装：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install-windows.ps1 `
  -AssetBundle .\nuoyan-windows-standard-assets-2.3.0.zip
```

如本地包不完整，可以配置企业镜像并允许或禁止公网回退：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\install-windows.ps1 `
  -AssetRoot D:\NuoyanAssets `
  -SourcesConfig .\sources.json
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

构建或安装前可只读检查 manifest；指定 `--asset-root` 时同时校验本地文件：

```powershell
.venv\Scripts\nuoyan.exe windows-assets `
  --manifest .\manifest.standard.release.json `
  --asset-root D:\NuoyanAssets `
  --strict --json
```

`-VerifyOnly` 只运行检查，不联网、不下载、不改写安装状态。

## 常见结果与处理

| 失败项 | 含义 | 处理责任 |
| --- | --- | --- |
| `runtime_source` | 当前命令加载的不是标准安装目录，或包版本与工作流版本不一致 | IT 重新运行安装脚本，检查旧 PATH/旧包 |
| `windows_install_state` | 未找到有效 manifest 版本、资产来源或安装记录 | IT 使用 V2.3.0 标准包重新安装并保留 JSON |
| `distribution_conflict` | 旧版包仍占用 `ivd_research` 命名空间 | IT 删除旧虚拟环境并重建，不在系统 Python 混装 |
| `playwright_browser` | Python 包存在，但 Chromium 未安装或无法启动 | IT 检查下载、终端安全软件和执行权限 |
| `translation_engine` | Argos 包或 English→Chinese 模型缺失 | IT 允许模型下载或导入批准的离线模型 |
| `life_science_plugin` | 插件可能已缓存，但当前 Codex 未启用 | 用户在 Codex 插件管理中启用并重启 |
| `browser_plugin` / `chrome_plugin` | Codex 浏览器能力未启用 | 用户在 Codex 插件管理中启用并重启 |
| `network_preflight` | PubMed/OpenAlex 的 Python HTTPS 和 curl 通道均不可用 | IT 配置代理、DNS、证书或站点白名单 |
| `ocr_runtime` | 扫描件 OCR 不可用 | 可选项；需要扫描 PDF 时由 IT 补装 Tesseract |

## 验收记录

IT 应保存严格体检 JSON、release manifest 和 `.nuoyan\install-state.json`，记录安装日期、代码版本、Python 路径、资产来源、SHA-256、失败项和处理结果。出现同事间结果差异时，先比较 `runtime_source`、`distribution_version`、`python_executable`、`windows_install_state` 和插件 `enabled` 字段，不再只比较界面显示的 Skill 名称。
