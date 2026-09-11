# Windows 离线资产兼容与指标事实双语展示设计

## 目标

本次更新解决两个业务问题：

1. Windows 用户安装 Skill 后，不需要再手动寻找翻译器、英中模型或浏览器运行时；网络受限时仍能使用已批准的离线资产。
2. 研发人员在“指标事实”页可以同时看到中英文指标名称、业务解释和原始英文事实，便于快速定位和回到原文复核。

## 方案选择

采用 C 方案，但不制作一个不可维护的单体大安装包，而是拆成“轻量 bootstrap + 标准离线资产包 + 可选扩展资产包”：

- bootstrap 包包含安装脚本、版本清单、资产 manifest、SHA-256 校验和、内网/公网源配置和回退逻辑，目标 10–30 MB。
- 标准离线资产包包含当前真实运行所需的 Python wheels、Playwright Chromium、Argos Translate 依赖和 English→Chinese 模型，预计下载 350–700 MB，安装后约 700 MB–1.2 GB。
- Java/Node 不进入默认标准包。当前代码没有直接使用它们；如后续控件确实需要，作为带版本和许可证信息的可选扩展包，预计额外 200–450 MB 下载、400–900 MB 安装空间。

最终发布大小必须由构建命令根据锁定版本和实际文件统计，不能用估算值代替 manifest。

## 安装架构

### 资产目录

新增受版本控制的资产描述目录，不直接提交大二进制文件：

```text
packaging/windows/
  manifest.standard.json
  manifest.extra.json
  sources.example.json
  build-assets.ps1
  install-windows.ps1
```

实际离线资产由发布流水线生成 ZIP，并按 manifest 中的相对路径、大小、SHA-256 和许可证记录校验。

### 资产解析优先级

安装器按以下顺序寻找每个资产：

1. 安装器旁的离线资产 ZIP 或已解压缓存；
2. IT 配置的内网镜像或本地文件共享；
3. 官方公网源；
4. 全部失败时停止安装，输出缺失资产、尝试过的来源、错误摘要和可继续动作。

不得把“已下载 Python 包”误判为“翻译可用”：Argos Python 包和英中模型必须分别验收，Playwright Python 包和 Chromium 可启动性也必须分别验收。

### 安装状态

安装器写出 `install-state.json`，记录：Skill 版本、资产 manifest 版本、来源、文件哈希、安装路径、回退次数、失败项和时间。`doctor --profile standard --strict --json` 读取同一状态并把资产缺口映射为业务可读提示。

### 更新与重试

- 已存在且哈希一致的资产跳过下载。
- 资产版本变化时只替换对应缓存，不重建整个虚拟环境。
- `-VerifyOnly` 只读检查，不联网、不修改文件。
- 安装脚本不使用系统 PATH 中的 `nuoyan`、全局 Python 或全局 Playwright。

## 指标事实双语数据流

### 数据字段

扩展 `MetricFact` 及其导出对象，保留原字段并增加：

- `metric_type_en`：原始英文指标名或标准英文名；
- `metric_type_zh`：中文指标名；
- `metric_explanation_zh`：面向研发快速阅读的中文解释；
- `value_explanation_zh`：数值、比较符和单位的中文说明；
- `excerpt_zh`：缓存中的中文事实摘录，可为空；
- `translation_status`：`not_needed | completed | engine_not_ready | not_generated`。

已有 `metric_type` 作为兼容字段保留。中文标签优先使用稳定字典（AUC、灵敏度、特异性、cut-off、OR、HR、CI、样本量等），未知指标保留英文并标记待复核，不调用网络翻译。

### HTML

“指标事实”页每行展示：

- 中文指标名，下一行显示 English label；
- 数值与中文解释；
- 中文事实摘录（有缓存时）及可展开的英文原文；
- 样本、平台、参照方法的中英文可检索文本；
- 翻译不可用时显示英文原文和明确的状态标签，不再用大段通用占位文案替代事实。

全局搜索和字段过滤同时覆盖中英文值，保留现有材料与证据卡跳转。

### Excel 与证据卡

- Excel “指标事实”页新增英文指标、中文指标、中文解释、英文摘录、中文摘录、翻译状态列。
- Markdown 证据卡的指标事实区按“中文标签（English label）— 数值 — 中文解释 — 原文摘录”顺序输出，英文原文始终保留。

## 错误处理与门禁

- 本地资产存在但哈希不符：删除该资产缓存并按优先级重新获取；仍失败则 `standard_ready=false`。
- Argos 包已装、模型缺失：安装器尝试导入本地 `.argosmodel`；失败时明确显示模型缺口。
- 翻译引擎不可用：报告仍生成英文事实，`translation_status=engine_not_ready`，不伪造中文译文。
- 双语字段缺失不影响原始事实追溯，但会使报告的“快速阅读完整度”检查告警；核心事实和证据卡链接仍必须通过验收。
- 安装包不得把 Java/Node 的存在作为当前标准门禁，除非对应功能被启用并在 manifest 中声明为必需。

## 测试设计

采用测试先行，新增/更新以下测试组：

1. Windows 安装器：离线资产优先、内网回退、公网回退、哈希失败、`-VerifyOnly` 不写入、状态文件字段和可选扩展包。
2. 资产 manifest：路径安全、大小与 SHA-256 校验、版本一致性、许可证字段完整性。
3. 指标事实：中英文标签映射、未知指标降级、翻译缓存命中/缺失、字段搜索覆盖中英文、HTML/Excel/Markdown 三端字段一致。
4. 回归：现有翻译状态、报告渲染、指标抽取、打包和 `verify-package` 测试全部通过。
5. Windows 验收：在干净 Windows 10/11 64 位环境执行离线安装和断网重试，确认 `standard_ready=true`；联网环境确认回退下载和幂等更新。

## 文档与发布

同步更新 `SKILL.md`、`README.md`、`docs/windows-standard-environment.md`、`references/report-rules.md`、CLI contract 和发布检查清单。发布包必须附带实际资产清单、版本、大小、SHA-256、许可证和已验证的安装环境，不把估算体积写成承诺。
