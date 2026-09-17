# 诺研 Skill 2.3.1 Windows 安装验证提示词

从 [GitHub Releases 最新版本](https://github.com/sunnysun1987/NuoYan_Skill/releases/latest) 下载 `nuoyan-windows-offline-installer-2.3.1.zip`、`SHA256SUMS.txt` 和 `WINDOWS_VALIDATION_PROMPT.md`。把文件放到 Windows 10/11 64 位电脑，在 `C:\NuoyanValidation` 完整解压安装包，再把下面整段提示词发送给 Windows 环境中的 Codex。

## 可复制提示词

```text
请执行“诺研 Skill 2.3.1 Windows 标准环境安装验证”。你负责运行命令、保存证据并给出结论，不要让我手工输入命令。

验证材料位于 C:\NuoyanValidation。先查找：
1. nuoyan-skill-v2 源码目录；
2. SHA256SUMS.txt；
3. nuoyan-windows-standard-assets-2.3.1.zip；
4. INSTALL_NUOYAN.cmd；
5. nuoyan-skill-v2\install-windows.ps1；
6. nuoyan-skill-v2\docs\windows-standard-environment.md。

验证目标：
- 确认源码包版本为 2.3.1，工作流版本为“诺研_skill-code-v2.3.1-2026-09-17”；
- 确认 GitHub Release 完整安装包包含 Python 3.13.15、Python wheelhouse、Playwright Chromium、Argos Translate 英中模型；
- 在干净 Windows 10/11 64 位环境验证断网安装；
- 确认 Argos 英中模型可实际翻译，不接受“Python 包已安装但模型缺失”；
- 确认指标事实的中英文字段、HTML、Excel 和 Markdown 证据卡回归测试通过；
- 恢复网络后运行严格环境体检，确认 standard_ready=true；
- 输出完整验证报告和原始日志，不执行 git push、打标签或发布。

安全与边界：
- 不读取、保存或展示密码、token、cookie、API Key 和私人账号凭据；
- 不从非官方来源下载 Python、Playwright 或 Argos 组件；
- 不绕过公司终端安全策略、代理、验证码或权限控制；
- 不修改业务数据；所有验证产物写入 C:\NuoyanValidation\results\<时间戳>；
- 每一步记录命令、退出码和关键结果。出现失败时保留原始日志，区分代码缺陷、环境限制、网络问题和插件未启用；
- 未完成对应验证前，不得写“已通过”。

请按以下顺序执行。

一、材料与环境预检
1. 使用 Get-FileHash -Algorithm SHA256 校验验证包和源码包，必须与 SHA256SUMS.txt 一致。
2. 读取 pyproject.toml、scripts\ivd_research\constants.py、packaging\windows\manifest.standard.json，确认版本和资产边界。
3. 记录 Windows 版本、系统架构、PowerShell 版本、可用磁盘、Codex 版本、py -0p 输出和网络/代理状态。建议至少预留 5 GB 可用磁盘。
4. 检查 Codex 中 Life Science Research、Browser、Chrome 插件是否安装并启用。插件缺失时记录为应用配置问题，不伪装成安装器缺陷。

二、GitHub Release 安装包检查
1. 使用 SHA256SUMS.txt 校验 `nuoyan-windows-offline-installer-2.3.1.zip`，并记录校验结果。
2. 确认完整解压后的根目录包含 `INSTALL_NUOYAN.cmd`、`README_FIRST.md`、`nuoyan-skill-v2` 和 `nuoyan-windows-standard-assets-2.3.1.zip`。
3. 检查标准资产 ZIP 内含：
   - manifest.standard.release.json
   - python\python-3.13.15-amd64.exe
   - python\wheelhouse.zip
   - browser\playwright-chromium.zip
   - translation\translate-en_zh.argosmodel
   - THIRD_PARTY_LICENSES.txt
4. release manifest 必须满足：release_ready=true；每个必需资产 size>0；SHA-256 不是全零；relative_path 不越界；license、version、required、sources 字段完整。
5. 对 ZIP 内每个资产重新计算实际大小和 SHA-256，与 release manifest 逐项比较。任一不一致即判定安装包完整性失败。
6. 审阅 THIRD_PARTY_LICENSES.txt，单独列出尚需法务或 IT 确认的模型许可证；不要把未确认写成“可以分发”。

三、代码和双语指标回归
在 `C:\NuoyanValidation\nuoyan-skill-v2` 建立独立验证虚拟环境，不使用系统级 pip --user：
1. py -3.13 -m venv .validation-venv
2. .\.validation-venv\Scripts\python.exe -m pip install -e ".[dev,browser,pdf,translation]"
3. .\.validation-venv\Scripts\python.exe -m pytest -q
4. .\.validation-venv\Scripts\ruff.exe check scripts\
5. .\.validation-venv\Scripts\python.exe -m compileall -q scripts
6. 额外确认下列测试文件通过：
   - scripts\tests\test_windows_assets.py
   - scripts\tests\test_windows_installer.py
   - scripts\tests\test_translation.py
   - scripts\tests\test_metric_fact_extractor.py
   - scripts\tests\test_package_verification.py
   - scripts\tests\test_packaging.py

四、干净环境断网安装
优先使用另一台干净 Windows 10/11 电脑、干净虚拟机或 Windows Sandbox。把完整解压后的安装包目录复制进去，然后断开网络。确认 `INSTALL_NUOYAN.cmd` 指向包内源码目录和标准资产 ZIP；自动化记录日志时可执行其对应的 PowerShell 命令：
1. 在源码根目录执行：
   powershell.exe -ExecutionPolicy Bypass -File C:\NuoyanValidation\nuoyan-skill-v2\install-windows.ps1 -AssetBundle C:\NuoyanValidation\nuoyan-windows-standard-assets-2.3.1.zip
2. 安装器结束后检查标准目录：
   %USERPROFILE%\.codex\skills\nuoyan-skill-v2
3. 必须存在：
   - .venv\Scripts\python.exe
   - .venv\Scripts\nuoyan.exe
   - .nuoyan\install-state.json
   - .nuoyan\ms-playwright 下的 Chromium
4. install-state.json 必须记录 manifest_version、skill_version、每项资产的 id、version、source_type、sha256 和 attempts。本地完整资产包安装时，必需资产的 source_type 应为 local。
5. 断网阶段运行：
   .\.venv\Scripts\nuoyan.exe doctor --profile standard --json
6. 断网时 network_preflight 未通过是预期网络状态。除此之外，runtime_source、distribution_conflict、skill_install、windows_install_state、playwright_browser、pdf_toolchain、translation_engine 必须通过。若安装命令最终仅因严格网络检查返回非零，要在报告中写成“离线组件安装通过、完整联网门禁待复查”，不能写成整体安装失败或整体通过。

五、翻译器实测
在标准安装目录执行：
1. .\.venv\Scripts\nuoyan.exe setup-translation-engine --provider argos --json
2. 结果必须满足 argos_installed=true、argos_model_ready=true、status=ready。
3. 使用 .venv 内 Python 调用 argostranslate.translate，把“The assay showed sensitivity of 91%.”从 en 翻译为 zh。
4. 译文必须非空并包含中文字符。若只安装了 argostranslate 包、没有 en→zh 模型，判定失败。

六、恢复网络后的严格验收
1. 恢复公司允许的网络或代理。
2. 在 Codex 中启用 Life Science Research、Browser、Chrome 插件并重启应用。
3. 执行：
   powershell.exe -ExecutionPolicy Bypass -File .\install-windows.ps1 -VerifyOnly
4. 再执行：
   .\.venv\Scripts\nuoyan.exe doctor --profile standard --network --strict --json
5. 最终必须退出码为 0，且 standard_ready=true、ok=true。若只有插件或公网通道失败，准确记录对应 check，不改写为安装资产失败。

七、回退和只读行为
1. 在可恢复的临时副本中移走一个本地资产，配置 sources.json 指向批准的企业镜像，验证安装器先记录 local 失败、再使用 mirror。
2. 只有企业策略允许时才测试 public fallback；禁止时设置 allow_public_fallback=false，并确认安装器不会访问公网资产源。
3. 对已安装环境运行 -VerifyOnly，比较运行前后的 install-state.json 哈希和修改时间，必须保持不变；同时确认没有新增下载缓存。
4. 不要破坏已通过的标准安装目录；回退测试使用临时虚拟机、快照或独立用户环境。

八、提交验证结果
在 results\<时间戳> 中保存：
- 00_验证结论.md
- 01_环境信息.txt
- 02_源码与安装包哈希.txt
- 03_构建日志.txt
- 04_release_manifest.json
- 05_离线安装日志.txt
- 06_install-state.json
- 07_translation-status.json
- 08_doctor-offline.json
- 09_doctor-online-strict.json
- 10_测试结果.txt
- 11_问题清单.md

验证结论必须按以下四类分别判断：
1. 源码与资产包完整性；
2. Windows 离线组件安装；
3. 翻译器与指标事实双语能力；
4. 恢复网络后的标准调研环境。

最后向我汇报：已验证项、失败项、未覆盖项、失败证据文件、是否可以交给业务用户、需要代码修复还是 IT/插件配置处理。不要只给“成功/失败”一句话。
```

## 验证设备建议

- 联网 Windows 电脑：校验 GitHub Release 文件并执行代码回归。
- 干净 Windows 10/11 64 位电脑或虚拟机：验证没有 Git、Python、Playwright、Argos 的情况下能否依赖标准资产包完成安装。
- 同一台电脑验证时，先校验 Release 安装包，再使用 Windows Sandbox、虚拟机快照或独立测试用户执行断网安装，避免已有环境造成假通过。
