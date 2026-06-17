# Nuoyan_skill_V2.0 开发记录

日期：2026-06-16

## 本轮目标

围绕 NuoYan-Skill V2.0 第一批能力，补齐 PubMed、PMC 检索、全文获取和 PDF 下载动作，使文献证据能够进入诺研材料、证据卡和 Excel 审阅链路。

## 已完成内容

### 第一批：PubMed / PMC 能力

1. 新增 `pubmed_literature` 场景。
   - 使用 NCBI E-utilities `esearch` / `efetch` 官方接口。
   - 支持 PubMed 关键词检索。
   - 解析 PMID、PMCID、DOI、题名、作者、期刊、发表日期、摘要、MeSH 词。
   - 输出标准 `Material` 记录。

2. 新增 `pmc_fulltext` 场景。
   - 使用 NCBI E-utilities 检索 PMC 开放全文。
   - 解析 PMC XML 中的 PMID、PMCID、DOI、题名、作者、期刊、发表日期、摘要、正文片段。
   - 尝试通过 PMC 官方 PDF 链接下载 PDF。
   - PDF 不可用、下载失败、限流或网络失败时记录真实状态。

3. 接入 CLI 和场景注册。
   - `run-scenario --scenario pubmed_literature`
   - `run-scenario --scenario pmc_fulltext`
   - 新任务初始化后，场景状态中可见 PubMed/PMC 两个新场景。

4. 接入查询计划。
   - 默认使用英文关键词或课题关键词。
   - 默认 `retmax=20`，避免一次性高并发触发 NCBI 限流。

5. 增强证据卡。
   - 文献类证据卡新增 PMID、PMCID、DOI、期刊、全文状态、PDF 状态等关键事实。
   - PubMed 摘要和 PMC 正文片段可进入证据卡摘录。

6. 增强 Excel 审阅表。
   - 保留原有通用工作表。
   - 新增 `文献检索` 工作表，集中展示 PMID、PMCID、DOI、期刊、发表日期、摘要状态、全文状态、PDF 状态和补证建议。

7. 更新版本标识。
   - `WORKFLOW_VERSION = Nuoyan_skill_V2.0-2026-06-16`
   - `TAXONOMY_VERSION = nuoyan-2026-06-16`

### 第二批：标准交付物结构

1. 新增标准交付目录构建能力。
   - 新增 CLI 命令：`build-standard-delivery`
   - 默认交付目录为任务目录下的 `交付目录/`

2. 标准交付目录收敛为三件套。

```text
交付目录/
├── 00_立项调研综合报告.html
├── 01_证据审阅与补证任务表.xlsx
└── 90_系统追溯数据/
```

3. Excel 审阅表输出增强。
   - 旧路径 `review/evidence_review_v001.xlsx` 保留兼容。
   - 新增标准命名文件 `review/01_证据审阅与补证任务表.xlsx`。
   - 标准交付目录中复制为 `交付目录/01_证据审阅与补证任务表.xlsx`。

4. 系统追溯数据归集。
   - `data/`
   - `downloads/`
   - `extracted_text/`
   - `evidence_cards/`
   - `logs/`
   - `reports/`
   - `review/`
   - `staging/`

5. 默认完整流水线调整。
   - `run-full-pipeline` 默认生成标准三件套交付。
   - `run-delivery-pipeline` 默认生成标准三件套交付。
   - 默认不再生成 ZIP。
   - `package-task` 命令仍保留为显式可选内部归档动作。

6. `verify-package` 验收逻辑调整。
   - 以 `交付目录/00_立项调研综合报告.html`、`交付目录/01_证据审阅与补证任务表.xlsx`、`交付目录/90_系统追溯数据/` 作为交付物就绪判断依据。
   - `business_ready` 仍要求人工复核和正式场景覆盖，不因文件生成而直接置为 true。

## 验证结果

| 验证项 | 结果 | 说明 |
| --- | --- | --- |
| Python 编译检查 | 通过 | `compileall` 已通过 |
| CLI doctor | 通过 | 系统 Python 环境中 Typer、Pydantic、OpenPyXL、HTTPX、BeautifulSoup 等依赖可用 |
| 新任务初始化 | 通过 | 新任务状态中包含 `pubmed_literature` 和 `pmc_fulltext` |
| 离线 PubMed XML 解析 | 通过 | 可解析 PMID、PMCID、DOI、题名、摘要等字段 |
| 离线 PMC XML 解析 | 通过 | 可解析 PMCID、PMID、DOI、摘要、正文片段 |
| 证据卡链路 | 通过 | PubMed 字段可进入证据卡关键事实 |
| Excel 审阅表链路 | 通过 | 可生成含 `文献检索` 工作表的审阅表 |
| 标准交付目录 | 通过 | 可生成 `00_立项调研综合报告.html`、`01_证据审阅与补证任务表.xlsx`、`90_系统追溯数据/` |
| 默认 ZIP 输出 | 通过 | 完整流水线不再默认生成 `task_package_v001.zip` |
| 标准交付验收 | 通过 | `delivery_artifacts_ready=true`，自动草稿下 `business_ready=false` |
| 真实 NCBI 联网采集 | 待验证 | 当前沙箱网络 DNS 解析失败，联网授权审批通道返回 503，未能完成外网验证 |

## 当前边界

1. 本轮开发位置为项目内开发副本：

```text
04 SKILL/Nuoyan_skill_V2.0/
```

2. 未覆盖当前已安装的正式技能目录：

```text
/Users/sunjing/.codex/skills/nuoyan-skill/
```

3. 当前已实现官方来源采集逻辑，不包含非合规下载指引。

4. 标准 HTML 报告当前复用既有可行性报告内容生成 `00_立项调研综合报告.html`；业务页签化视觉和内容重组尚未完成。

5. 真实 PubMed/PMC 联网采集需要在可访问 NCBI 的网络环境下再次验收。

## 下一步

1. 在授权可用时安装或同步 V2.0 到正式 skill 目录。
2. 进行真实联网验证：
   - PubMed 检索。
   - PMC XML 获取。
   - PMC PDF 下载。
3. 将 `00_立项调研综合报告.html` 进一步改造为业务页签报告。
4. 继续补充 OpenAlex 检索和跨库去重。
