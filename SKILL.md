---
name: Nuoyan_skill_V2.0
description: 用于 IVD 企业研发人员开展立项可行性调研（诺研 V2.1），组织调研范围确认、多源文献与科学数据库证据采集、材料包、增强证据卡、HTML 调研分析综述、Excel 证据审阅表和本地知识索引等产出。适用于体外诊断产品立项、竞品与法规证据整理、研发可行性评估和面向评审的材料准备。
---

# Nuoyan_skill_V2.1 - IVD 立项可行性调研

使用本 skill 时，先做项目理解和范围确认，再进入资料收集、证据整理、分析和报告生成。不要直接替用户假设产品边界、适用场景、目标市场、注册路径或证据标准。

> 兼容说明：本地 skill 名称仍保留 `Nuoyan_skill_V2.0`，以兼容既有 Codex 安装和调用习惯；当前仓库能力已升级为 V2.1 文献证据增强版。

## 工作原则

- 全程使用中文与用户沟通，必要时保留法规、技术和产品术语的英文原文。
- 先确认调研范围：产品类型、检测项目、预期用途、目标地区、目标用户、竞品范围、时间范围和报告深度。
- V2.1 的第一步是补全检索条件，不得跳过。用户只给出模糊课题时，必须先围绕产品类型、检测项目、疾病/适应症、样本类型、检测平台/方法学、预期用途、目标地区、目标用户、竞品范围、文献时间范围、文献召回数量、文献 profile、专利范围和报告深度提问。用户回复“按推荐”时，也必须先明确推荐假设并写入确认项，再开始正式采集。
- 即使记忆、历史任务或本地文件中已有项目画像，也只能作为“推荐检索条件草案”。正式采集前必须把检索条件草案展示给用户确认；用户确认后再写入 `update-confirmations` 并执行采集。不得因为记忆中已有信息就直接开跑。
- 对不明确的问题提供文字 RPG 式选项，让用户通过编号或简短文字选择下一步，例如“1. 快速立项判断 / 2. 完整可行性报告 / 3. 只做竞品和法规证据”。
- 不得绕过验证码、登录、付费墙、访问控制或网站服务条款。遇到受限资料时，如实说明限制，并请求用户提供合法取得的文件或链接。
- CLI 只给 agent 使用，不面向非 IT 用户。不要让业务用户直接操作命令行。
- Codex Chrome 用于站点探索、登录态页面观察、验证码/权限限制确认和失败诊断；观察结果必须通过 `record-site-observation` 记录，后续沉淀为站点 adapter 或 site profile。不要让 Codex 每次自由点击网页来替代稳定 CLI。
- 当 HTTP/API adapter 无法覆盖真实网站流程时，使用 Playwright 持久化浏览器会话执行固定页面 workflow。登录、Cloudflare 真人验证或机构认证必须由用户在可见浏览器中合法完成，agent 只读取登录后合法可见内容。
- 遇到 DNS、HTTP 429、连接失败、页面结构变化、登录态、验证码、权限或下载失败时，不得直接跳过来源场景。必须记录真实失败状态，并执行兜底链路：缩短/改写检索式重试、官方/公开网页检索后用 `import-finding` 导入、浏览器 workflow 观察并记录、请求用户提供合法材料。所有兜底动作或阻塞原因都必须进入报告“缺口与任务”和 Excel 补证表。
- 当来源场景无结果或命中明显偏少时，不得只用一个“大而宽”的检索式结束。必须按“宽检索式 → 缩窄核心词 → 主关键词/产品名 → 方法学或样本限定”的顺序重试，并在场景状态或补证任务中记录使用过的检索层级。CMDE、标准、中文期刊、NMPA、专利等网站尤其要避免把英文 Boolean、样本/平台长串和预期用途全部塞进单一检索框。
- Edge 缺失不得直接作为浏览器类场景的终点。除站点明确只能由 Edge/CDP 完成外，必须自动降级到 Playwright Chromium 或固定 DOM workflow；NMPA 应先尝试 HTTP/API，再尝试 Edge CDP，Edge 不可用时再尝试 Playwright DOM 兜底。只有 Playwright 也不可用、登录/验证码/权限限制或站点策略阻断时，才记录为 `needs_manual_review`、`needs_login` 或 `permission_required`。
- V2.1 证据地图中的正式来源场景是完整调研的必要覆盖面。完整调研不得只跑局部来源后生成看似完整的报告；未完成、失败、延期或无结果的场景必须在报告首页、证据地图和补证任务中集中展示，并使 `business_ready=false`。
- 原始文件、PDF、网页快照和全文抽取文件必须优先按材料标题命名，文件名格式建议为：`MAT-000001_材料标题前80字_来源_YYYYMMDD.ext`。标题需做文件名安全清理；只有无标题时才退回 `material_id` 命名。下载失败、权限受限或仅有题录/摘要时，必须在材料记录、证据卡和 Excel 补证表中写明“未取得原文”的原因。
- PubMed/PMC 文献采集必须保留页面 Abstract 的完整结构化内容，包括 Objective/Methods/Results/Interpretation/Keywords 等分段；不得只保存摘要前几句。PubMed 命中文献后，还要抓取 Similar articles 中高相关条目并记录为相关文献线索。若 PubMed 页面存在 Free full text / PMC 入口，应进入 PMC 全文页，优先下载 PDF；PDF 不可用时保存 PMC XML/HTML 全文和抽取文本，并记录不可下载原因。
- 文献召回数量默认必须设置合理上限，不得默认“有多少召回多少”。如果用户提出“不设上限”“全量执行”“有多少召回多少”等要求，必须先暂停并做二次风险确认，不得直接开跑。风险确认必须明确提示：命中数可能达到数百至数千条，执行时间可能超过 1 小时，原始 XML/HTML/全文抽取/PDF 和 ZIP 可能占用数 GB 磁盘空间，CLI 大 JSON 输出可能造成临时文件膨胀，批量全文/PDF/Similar articles 可能触发 NCBI/出版社限流，浏览器工作流和报告生成可能出现内存占用过高或进程超时。只有用户在看到这些风险后再次确认，才允许使用全量策略。
- 全量策略即使被二次确认，也必须先查询命中总数、向用户说明预计数据量，再分批获取详情；Similar articles、PDF 下载、出版社全文下载、网页快照和 ZIP 打包等二级动作必须设置可解释的策略上限或分阶段执行，不能让二级下载拖成主流程阻塞。
- 文献摘要不只在原始 JSON 中保留。HTML 报告、Excel 文献检索表和 Markdown 证据卡都必须展示结构化 Abstract 分段；如果来源只给出非结构化摘要，也要标注为 Abstract，而不是截成一段无法审阅的短文本。
- 当前版本不在 HTML 报告、Excel 或 Markdown 证据卡中生成“中文阅读版 / 中文辅助译文”。英文材料必须保留完整原文摘要、结构化 Abstract、scope、basic_info_text、full_visible_text 或关键摘录；涉及 AUC、灵敏度、特异性、cut-off、OR/HR、相关系数、95%CI、样本量等参数时，必须另设“参数要点”并以换行列表呈现，不能揉进长段落里。完整翻译引擎作为下个版本迭代项；在翻译能力未达到完整、可审阅标准前，不得输出半截中文译文或术语替换式“中文阅读版”。
- HTML 报告页面标题不得只写成“可行性调研报告”，也不得保留“立项”作为展示标题词。标准交付报告的浏览器标题和 H1 应统一使用“XX项目调研分析综述”这类更宽口径标题；文件名 `00_立项调研综合报告.html` 可保持稳定，避免破坏既有交付目录链接。
- 项目分析章节不得只输出固定模板句。报告生成时必须基于已采集文献和证据卡做聚合分析，至少统计并引用样本类型、应用场景、目标人群、参照方法、平台/方法学、性能指标、全文/摘要覆盖和关键证据题名；不能把上一项目的靶标、方法学或竞品结论硬编码带入新项目。
- V2.1 内置标准信源配置，运行时可通过 `source-sites` 导出。标准信源包括 CMDE、NMPA、国家标准平台、PatentHub、中华医学期刊、PubMed/PMC/OpenAlex、life-science-research 插件通道、本地导入和 Zotero 可选导入。信源配置必须进入 `90_系统追溯数据/01_原始材料数据_data/source_sites_v21.json`。
- 范围确认后，如果课题涉及标志物、蛋白、基因、疾病机制、通路、临床试验、遗传证据或公共科学数据库线索，应调用 life-science-research 插件能力。插件结果不得停留在聊天摘要中，必须通过 `import-life-science-findings` 或等价桥接写入 Material、SourceRun、EvidenceCard 和本地知识索引。
- V2.1 证据卡必须尽量填充来源追溯、研发定位、指标事实、原文摘录、关系字段、局限和补证任务。涉及 AUC、灵敏度、特异性、cut-off、HR/OR、CI、样本量等参数时，应进入 `MetricFact`，并展示在 HTML、Excel 和 Markdown 证据卡中。
- 每次标准交付前应生成本地知识资产：`knowledge/metric_facts.jsonl`、`knowledge/literature_graph.json`、`knowledge/topic_index.json`、`knowledge/dedup_index.json` 和 `knowledge/relation_summary.md`。这些文件用于后续项目复用、主题关联和文献去重。
- 不要把中间 JSON、内部状态或调试字段暴露给非 IT 用户；面向用户时输出自然语言结论和可审阅的文件。
- 所有关键判断都要尽量绑定来源、日期、证据强度和不确定性。

## 推荐流程

1. 理解项目：确认产品、适用场景、目标地区、评审目的和时间限制。
2. 补全检索条件：用文字 RPG 式选项补齐产品类型、检测项目、疾病、样本、平台、预期用途、地区、用户、竞品、文献、专利和报告深度；这是正式检索前的必要动作。
3. 收集材料：整理法规、指南、竞品、文献、市场和技术路线资料。
4. 生成证据卡：记录证据摘要、来源、关键结论、可信度、风险和待复核点。
5. 形成材料包：将原始资料索引、证据卡和状态文件组织成可追溯材料包。
6. 生成报告：输出 V2.1 标准交付目录中的 `00_立项调研综合报告.html`，报告必须含总览、项目分析、证据地图、关键证据、文献检索、指标事实、竞品与注册、缺口与任务、材料台账。
7. 生成审阅表：输出 `01_证据审阅与补证任务表.xlsx`，便于专家逐条确认、修订和补充。
8. 复制证据卡：标准交付目录必须包含 `02_证据卡/`，其中放置全部 Markdown 证据卡，便于研发、医学和注册人员逐张审阅。
9. 生成知识索引：运行或由交付命令自动触发 `build-knowledge`，形成指标事实、主题索引、文献关系图和候选去重索引。
10. 交付验证：运行 `verify-package`，确认检索条件、来源场景覆盖、失败兜底、证据卡、人工复核、V2.1 资产和标准交付物是否满足交付门槛；不满足时必须说明 `business_ready=false` 的具体原因。

## CLI 使用约束

优先使用 `scripts/ivd_research` 下的 CLI 和工具函数处理可重复、可验证的文件生成任务。CLI 是 agent 的内部工具，用户只需要接收结果文件和结论摘要。

CLI 或脚本失败时，不要掩盖失败，不要编造结果。应说明失败步骤、已完成内容、未完成内容、错误信息摘要和可继续的最小下一步。

当 HTTP/API 采集失败、页面需要登录态或页面结构未知时，agent 可以使用 Codex Chrome 观察页面。但 Chrome 观察只用于诊断和适配器开发：

1. 先运行 `ivd-research site-profile --scenario <scenario_id> --json` 查看站点策略。
2. 在 Chrome 中观察搜索框、筛选项、结果列表、详情页和下载入口。
3. 遇到登录、验证码、Cloudflare、权限墙时停止自动化并如实记录。
4. 运行 `ivd-research record-site-observation --task-id <task_id> --scenario <scenario_id> --observation-json <json> --json` 记录观察结果。
5. 后续把稳定观察沉淀成 adapter 代码和测试，不要依赖每次临场点击。

当站点需要登录态、Cloudflare 真人验证、复杂分页、筛选或下载流程时，agent 应使用 Playwright 持久化会话：

1. 运行 `ivd-research browser-workflow --scenario <scenario_id> --query <query> --json` 查看固定页面 workflow 和目标搜索 URL。
2. 运行 `ivd-research prepare-browser-session --task-id <task_id> --scenario <scenario_id> --json` 创建会话目录。
3. 可先运行 `ivd-research probe-browser-workflow --task-id <task_id> --scenario <scenario_id> --query <query> --json` 做只读探测，判断当前登录态是否可用。
4. 对结构未知或动态阻塞的网站，运行 `ivd-research scout-browser-workflow --task-id <task_id> --scenario <scenario_id> --query <query> --launch-mode playwright --json` 保存 DOM/network 候选；NMPA 可改用 `--launch-mode edge-cdp`。
5. 如返回 `needs_login` 或 `permission_required`，运行 `ivd-research open-browser-session --task-id <task_id> --scenario <scenario_id> --json` 打开可见浏览器。
6. 引导用户在浏览器中手动完成登录、机构认证或真人验证。
7. 运行 `ivd-research run-browser-workflow --task-id <task_id> --scenario <scenario_id> --query <query> [--methodology <method>] [--launch-mode playwright|edge-cdp] --json` 执行固定搜索或正常导航流程，保存快照并记录状态；NMPA 竞品注册采集优先使用 `--launch-mode edge-cdp`，默认先尝试无头执行，只有需要用户登录、验证码、机构认证或排错时才主动加 `--headed`；如自动降级为可见浏览器，必须记录降级原因。
8. 后续采集使用同一任务目录下的 `browser_state/<scenario_id>`，保留登录态和验证状态。
9. 不得自动破解验证码、Cloudflare、付费墙或权限墙；无法合法访问时必须记录失败原因。

## 外部搜索结果导入

当 Agent 通过 WebSearch、Jina Reader 或其它外部渠道获取到有效证据时，使用 `import-finding` 命令将其写入材料管线：

```bash
ivd-research import-finding --task-id <task_id> \
  --title "证据标题" \
  --source "web_search" \
  --source-url "https://..." \
  --content "证据正文内容..." \
  --material-type "regulatory" \
  --json
```

支持 `--content-file` 从文件读取长文本。`--material-type` 可选值：`regulatory | competitor | standard | patent | literature | local_import`，省略时自动推断。

## life-science-research 插件证据导入

当 Codex 通过 `life-science-research:research-router-skill` 或其下游子 skill 得到 UniProt、STRING、Reactome、OpenTargets、ClinicalTrials、GWAS、ClinVar、Human Protein Atlas、PMC 等结果时，将结果整理为 JSON 列表，并导入材料管线：

```bash
ivd-research import-life-science-findings --task-id <task_id> \
  --findings-json-file external_findings.json \
  --query "plasma p-tau217 Alzheimer disease" \
  --json
```

每条 finding 建议包含 `source_database`、`evidence_lane`、`entity`、`query`、`result_summary`、`source_url` 和 `identifier`。导入后必须继续运行 `generate-evidence-cards`、`build-knowledge`、`export-review` 和 `build-standard-delivery`。

## V2.1 文献 profile 与本地知识资产

文献 profile 用于控制速度、召回量和二级下载范围。可选 profile 包括：

- `quick_scan`：快速扫描，适合 30 分钟内判断是否值得深入。
- `complete_literature`：完整文献，适合标准调研材料。
- `fulltext_first`：全文优先，适合方法学和性能参数抽取。
- `core_must_read`：核心必读，适合研发阅读入口。
- `chinese_first`：中文优先，适合国内临床应用和注册语境补充。

如需导入本地文献清单或腾讯文档导出表，可使用：

```bash
ivd-research import-literature-table --task-id <task_id> --path literature.xlsx --json
```

本地知识资产通过以下命令生成：

```bash
ivd-research build-knowledge --task-id <task_id> --json
```

## AI 分析章节生成流程

可行性报告的 17 个分析章节需要 Agent 基于已采集材料生成：

1. `ivd-research create-analysis-requests --task-id <task_id>` 生成分析请求模板
2. Agent 逐章阅读材料全文和证据卡，为每个章节写入 `staging/report_sections/<section_id>.json`
3. `ivd-research validate-staged --task-id <task_id> --type report-section` 校验章节
4. `ivd-research commit-staged --task-id <task_id> --type report-section` 提交入库
5. `ivd-research build-report --task-id <task_id> --type feasibility` 渲染最终报告

每个 report_section JSON 必须包含：
- `section_id`、`section_title`、`facts`、`analysis`
- `evidence_gaps`：没有充分证据时写明缺口，不得伪装确定结论
- `evidence_strength_summary`：`strong | moderate | weak | gap`（必填）
- `confidence_level`：`高 | 中 | 低`
- `supporting_evidence_refs`：`[{material_id, evidence_card_id, excerpt}]`（必须引用真实材料）

## 最终产出

一次完整调研通常应产出：

- `交付目录/00_立项调研综合报告.html`：唯一默认主入口，含多页签和 17 章项目分析。
- `交付目录/01_证据审阅与补证任务表.xlsx`：证据审阅、文献检索、补证任务和责任角色回填入口。
- `交付目录/02_证据卡/`：全部 Markdown 证据卡，是人工逐条复核的重要业务材料。
- `交付目录/90_系统追溯数据/`：材料、证据卡、日志、下载文件、内部报告、暂存数据、标准信源配置和本地知识索引。

如果用户只要求部分产出，只生成所需文件，并说明未生成的内容不在本次范围内。
