# 诺研 Skill Windows 离线安装

本安装包适用于 Windows 10/11 64 位电脑。安装过程会把诺研 Skill、Python 3.13 专用环境、Playwright Chromium、PDF 依赖和 Argos 英中离线翻译模型安装到当前用户的标准 Codex Skill 目录。

## 安装

1. 完整解压 ZIP，不要在压缩包预览窗口中直接运行文件。
2. 双击 `INSTALL_NUOYAN.cmd`。
3. 等待窗口完成安装和环境体检，不要中途关闭。
4. 在 Codex 插件管理中确认 Life Science Research、Browser、Chrome 已启用，然后重启 Codex。

命令窗口最后显示退出码 0 且体检 JSON 中 `standard_ready=true`，表示标准调研环境可用。如果网络或插件门禁未通过，保留完整窗口内容并交给 Codex 或 IT 排查。

安装器只写入 `%USERPROFILE%\.codex\skills\nuoyan-skill-v2`，不会向系统 Python 安装诺研依赖。
