---
name: nuoyan-skill-v2
description: 用于 IVD 企业研发人员开展研发项目调研，组织调研范围确认、多源文献与科学数据库证据采集、材料包、增强证据卡、HTML 调研分析综述、Excel 证据审阅表和本地知识索引等产出。适用于体外诊断产品立项、竞品与法规证据整理、研发可行性评估和面向评审的材料准备。
---

# 诺研_skill_IVD研发项目调研

使用本 skill 时，先做项目理解和范围确认，再进入资料收集、证据整理、分析和报告生成。不要直接替用户假设产品边界、适用场景、目标市场、注册路径或证据标准。

> 命名规则：Codex 加载 ID 固定为 `nuoyan-skill-v2`，保持小写字母、数字和连字符格式，并与安装目录名一致。中文展示标题保留为“诺研_skill_IVD研发项目调研”。

## 工作原则

- 全程使用中文与用户沟通，必要时保留法规、技术和产品术语的英文原文。
- 默认把用户视为不熟悉 IVD 研发、注册和临床证据体系的业务提出方。用户需求可能模糊、不完整或含有专业误区时，Agent 必须先以产品经理视角理解真实目标，主动补全项目边界、指出关键假设和风险，并给出可执行推荐方案；不得机械照抄用户原话或要求用户先具备专业知识。
- 先确认调研范围：产品类型、检测项目、预期用途、目标地区、目标用户、竞品范围、时间范围和报告深度。
- V2.1 的第一步是补全检索条件，不得跳过。用户只给出模糊课题时，必须先围绕产品类型、检测项目、疾病/适应症、样本类型、检测平台/方法学、预期用途、目标地区、目标用户、竞品范围、文献时间范围、文献召回数量、文献 profile、专利范围和报告深度提问。用户回复“按推荐”时，也必须先明确推荐假设并写入确认项，再开始正式采集。
- 即使记忆、历史任务或本地文件中已有项目画像，也只能作为“推荐检索条件草案”。正式采集前必须把检索条件草案展示给用户确认；用户确认后再写入 `update-confirmations` 并执行采集。不得因为记忆中已有信息就直接开跑。
- 对不明确的问题提供文字 RPG 式选项，让用户通过编号或简短文字选择下一步，例如“1. 快速立项判断 / 2. 完整可行性报告 / 3. 只做竞品和法规证据”。
- 不得绕过验证码、登录、付费墙、访问控制或网站服务条款。遇到受限资料时，如实说明限制，并请求用户提供合法取得的文件或链接。
- CLI 只给 agent 使用，不面向非 IT 用户。不要让业务用户直接操作命令行。
- Codex Chrome 用于站点探索、登录态页面观察、验证码/权限限制确认和失败诊断；观察结果必须通过 `record-site-observation` 记录，后续沉淀为站点 adapter 或 site profile。不要让 Codex 每次自由点击网页来替代稳定 CLI。
- 当 HTTP/API adapter 无法覆盖真实网站流程时，使用 Playwright 持久化浏览器会话执行固定页面 workflow。登录、Cloudflare 真人验证或机构认证必须由用户在可见浏览器中合法完成，agent 只读取登录后合法可见内容。
- 遇到 DNS、HTTP 429、连接失败、页面结构变化、登录态、验证码、权限或下载失败时，不得直接跳过来源场景。必须记录真实失败状态，并执行兜底链路：缩短/改写检索式重试、官方/公开网页检索后用 `import-finding` 导入、浏览器 workflow 观察并记录、请求用户提供合法材料。所有兜底动作或阻塞原因都必须进入报告“缺口与任务”和 Excel 补证表。
- 当来源场景无结果或命中明显偏少时，不得只用一个“大而宽”的检索式结束。CMDE、标准、OpenAlex、中文全文和中文期刊等来源必须优先使用检测项目/靶标核心词，再追加产品提示、宽业务词和原始检索式作为后续兜底层级；NMPA、专利等产品型来源可保留产品/方法学提示，但不得把英文 Boolean、样本/平台长串和预期用途全部塞进第一检索式。场景状态或补证任务中必须记录使用过的检索层级。
- PubMed、PMC 和 OpenAlex 等英文文献来源必须优先使用英文核心词层级，例如靶标/检测项目 + assay/immunoassay，再追加方法学扩展词、产品提示、样本类型和预期用途等宽检索层级。涉及荧光免疫层析、免疫层析、侧向层析、POCT 等方法学时，必须自动增加 `fluorescence immunochromatographic assay`、`fluorescent immunochromatographic assay`、`lateral flow immunoassay`、`immunochromatographic assay` 或 `point-of-care immunoassay` 等英文扩展词。不得把完整产品描述、样本、平台、POCT、临床用途和同义词长串一次性塞进英文来源首个检索式。
- `no_results` 不是最终事实，只是某一来源、某一检索策略下的状态。标准交付必须运行或自动生成采集质量审计：检查是否存在单一检索式判空、缺少核心词层级、检索词过长、OpenAlex 与 PubMed/PMC/LSR 互相矛盾等假阴性风险。存在高风险疑似假阴性时，HTML 报告“资料缺口”、Excel“采集异常”和 `verify-package` 必须显式提示，并使 `business_ready=false`。
- Edge 缺失不得直接作为浏览器类场景的终点。除站点明确只能由 Edge/CDP 完成外，必须自动降级到 Playwright Chromium 或固定 DOM workflow；NMPA 应先尝试 HTTP/API，再尝试 Edge CDP，Edge 不可用时再尝试 Playwright DOM 兜底。只有 Playwright 也不可用、登录/验证码/权限限制或站点策略阻断时，才记录为 `needs_manual_review`、`needs_login` 或 `permission_required`。
- V2.1.4 证据地图中的正式来源场景必须按已确认项目画像动态装配。通用 IVD 项目覆盖法规、竞品、标准、专利、中文检验/实验室文献、PubMed、PMC、OpenAlex 和中文全文；神经/认知方向才加入中华神经科杂志，AD/认知障碍标志物项目才加入 Wiley Alzheimer。完整调研不得只跑局部来源后生成看似完整的报告；适用场景未完成、失败、延期或无结果时，必须在报告首页、证据地图和补证任务中集中展示，并使 `business_ready=false`。
- 原始文件、PDF、网页快照和全文抽取文件必须优先按材料标题命名，文件名格式建议为：`MAT-000001_材料标题前80字_来源_YYYYMMDD.ext`。标题需做文件名安全清理；只有无标题时才退回 `material_id` 命名。下载失败、权限受限或仅有题录/摘要时，必须在材料记录、证据卡和 Excel 补证表中写明“未取得原文”的原因。
- PubMed/PMC 文献采集必须保留页面 Abstract 的完整结构化内容，包括 Objective/Methods/Results/Interpretation/Keywords 等分段；不得只保存摘要前几句。PubMed 命中文献后，还要抓取 Similar articles 中高相关条目并记录为相关文献线索。若 PubMed 页面存在 Free full text / PMC 入口，应进入 PMC 全文页，优先下载 PDF；PDF 不可用时保存 PMC XML/HTML 全文和抽取文本，并记录不可下载原因。
- 文献召回数量默认必须设置合理上限，不得默认“有多少召回多少”。标准完整调研默认使用 `complete_literature`，英文文献源单源召回上限为 200 条；`quick_scan` 才允许 50 条左右的轻量上限。确认项中的低 `literature_retmax` 不得静默降低 `complete_literature`、`fulltext_first` 等正式 profile 的默认深度；需要轻量执行时必须显式选择 `quick_scan`。如果用户提出“不设上限”“全量执行”“有多少召回多少”等要求，必须先暂停并做二次风险确认，不得直接开跑。风险确认必须明确提示：命中数可能达到数百至数千条，执行时间可能超过 1 小时，原始 XML/HTML/全文抽取/PDF 和 ZIP 可能占用数 GB 磁盘空间，CLI 大 JSON 输出可能造成临时文件膨胀，批量全文/PDF/Similar articles 可能触发 NCBI/出版社限流，浏览器工作流和报告生成可能出现内存占用过高或进程超时。只有用户在看到这些风险后再次确认，才允许使用全量策略。
- 全量策略即使被二次确认，也必须先查询命中总数、向用户说明预计数据量，再分批获取详情；Similar articles、PDF 下载、出版社全文下载、网页快照和 ZIP 打包等二级动作必须设置可解释的策略上限或分阶段执行，不能让二级下载拖成主流程阻塞。
- 文献摘要不只在原始 JSON 中保留。HTML 报告、Excel 文献检索表和 Markdown 证据卡都必须展示结构化 Abstract 分段；如果来源只给出非结构化摘要，也要标注为 Abstract，而不是截成一段无法审阅的短文本。
- 英文材料必须保留完整原文摘要、结构化 Abstract、scope、basic_info_text、full_visible_text 或关键摘录；涉及 AUC、灵敏度、特异性、cut-off、OR/HR、相关系数、95%CI、样本量等参数时，必须另设“参数要点”并以换行列表呈现，不能揉进长段落里。诺研交付物必须面向研发人员提供中文阅读版：英文标题、结构化 Abstract、关键摘录等可见英文内容应在交付前由 `translate-materials` 自动生成中文缓存，HTML 报告优先展示中文标题和“专业中文阅读”，英文原文仅作为追溯保留。关键摘录和专业中文阅读不得把来源、检索式、题名、作者、期刊、Abstract 正文挤在同一长段里；必须按信息块和句群拆段展示，提高研发人员快速阅读和复核效率。`translation-status` 只作为 agent 内部体检命令，不面向研发用户；不得要求研发人员配置 OpenAI 账号、API Key、LibreTranslate 内网服务或手工执行翻译命令。默认翻译链路采用 GitHub 开源项目 Argos Translate 离线模型；如环境暂不可用，交付说明必须写明“诺研执行端尚未完成中文化”，而不是把配置任务转嫁给研发人员。
- HTML 报告页面标题不得只写成“可行性调研报告”，也不得保留“立项”作为展示标题词。标准交付报告的浏览器标题和 H1 应统一使用“XX项目调研分析综述”这类更宽口径标题；文件名 `00_立项调研综合报告.html` 可保持稳定，避免破坏既有交付目录链接。
- HTML 主报告默认采用“研发筛选版”工作台形态：顶部页签为“项目分析 / 研发阅读入口 / 指标事实 / 核心必读文献 / 全部证据卡 / 资料缺口”。不同页签应提供各自需要的目录或筛选器，不得在所有页签中固定保留全局证据筛选器；“项目分析”必须保留左侧章节目录，目录项要具备明显可点击、可跳转的视觉提示，并能跳转到 17 个分析章节；每个项目分析章节的“当前依据”必须包含依据清单表，展示原文标题超链、相关内容原文和可跳转到“全部证据卡”的证据卡锚点；依据清单不得在数据层默认截断为固定条数，必须保留完整匹配结果，并在页面上按章节独立分页展示；“研发阅读入口”的“先看结论”必须按研发专家口径输出研发定位、验证重点、证据读数、可信度和下一关口，不得只写浅层泛泛结论；“中文阅读覆盖”不作为研发阅读入口卡片展示；“研发阅读入口”的数字卡必须展示业务解释，但不要把“口径”二字直接写入卡片正文，并可点击跳转到证据地图、全部证据卡、核心必读、资料缺口和指标事实等对应内容；指标事实必须作为独立顶部页签展示，全部字段中文化，提供总查询框和指标、数值、材料、证据卡、样本、平台/方法等多字段组合筛选；指标事实中的材料必须使用原文标题超链，证据卡必须可点击跳转并锚定到“全部证据卡”相关卡片；“核心必读文献”和“全部证据卡”应各自提供局部筛选器。证据卡必须展示优先级、研发阶段、样本类型、检测平台/方法、参照标准、应用场景、目标人群、性能参数、组合标志物、地域/人群、证据类型、关键摘录、专业中文阅读状态和待复核点。
- HTML 报告中的采集异常、未命中、登录/权限受限和来源缺口必须转换成业务可读的“资料缺口与人工处理”清单，只说明缺少什么、影响什么、建议由谁补充和验收口径；不得向业务用户展示 HTTP/API、Playwright、DOM、Edge、命令行参数、adapter、内部 workflow 等 IT 实现细节。资料缺口必须区分“未补齐缺口”和“已公开兜底部分补齐”：后者只能表示已有同类型公开材料可供初步复核，不能替代官方通道闭环；中文特定来源不得被 PubMed/LSR 泛文献自动兜底，除非有中文公开补证或本地导入材料。
- 项目分析章节不得只输出固定模板句。报告生成时必须基于已采集文献和证据卡做聚合分析，至少统计并引用样本类型、应用场景、目标人群、参照方法、平台/方法学、性能指标、全文/摘要覆盖和关键证据题名；不能把上一项目的靶标、方法学、专科信源或竞品结论硬编码带入新项目。若初始任务标题含有旧项目词，已确认的 `primary_query` 和关键词池优先作为项目画像来源。
- V2.1 内置标准信源配置，运行时可通过 `source-sites` 导出。标准信源包括 CMDE、NMPA、国家标准平台、PatentHub、中华医学期刊、PubMed/PMC/OpenAlex、life-science-research 插件通道、本地导入和 Zotero 可选导入。信源配置必须进入 `90_系统追溯数据/01_原始材料数据_data/source_sites_v21.json`。
- 范围确认后，如果课题涉及标志物、蛋白、基因、疾病机制、通路、临床试验、遗传证据或公共科学数据库线索，应调用 life-science-research 插件能力。插件结果不得停留在聊天摘要中，必须通过 `import-life-science-findings` 或等价桥接写入 Material、SourceRun、EvidenceCard 和本地知识索引。
- 生物标志物、蛋白/基因、疾病机制、通路、临床试验或遗传证据项目必须先运行或生成 `life-science-plan`，再通过 life-science-research 插件查询并导入材料。默认最低覆盖为 12 条插件材料、5 个来源数据库和 4 个证据通道；未导入、导入过少或证据通道过窄时，`verify-package` 必须保持 `scenario_coverage_ready=false` 和 `business_ready=false`。
- life-science-research 采用保守触发机制，不依赖少量关键词白名单。完整 IVD 调研中，只要项目画像表现为检测项目、检测试剂盒、定量/定性检测、免疫分析、POCT、体外诊断、临床用途、样本或标志物/靶标相关内容，应默认先触发 `life-science-plan` 并完成插件导入；只有用户明确确认“本次仅做注册/竞品/标准，不做科学数据库证据”时，才允许通过 `life_science_required=false` 或 `life_science_scope=只做注册/竞品/标准` 记录豁免。
- 标准交付流水线必须执行 LSR-first gate：需要 life-science-research 且尚未导入达标材料时，应先生成查询计划并停止通用采集，不得先跑 PubMed/NMPA/标准/专利后再补 LSR。
- V2.1 证据卡必须尽量填充来源追溯、研发定位、指标事实、原文摘录、关系字段、局限和补证任务。涉及 AUC、灵敏度、特异性、cut-off、HR/OR、CI、样本量等参数时，应进入 `MetricFact`，并展示在 HTML、Excel 和 Markdown 证据卡中。
- 每次标准交付前应生成本地知识资产：`knowledge/metric_facts.jsonl`、`knowledge/literature_graph.json`、`knowledge/topic_index.json`、`knowledge/dedup_index.json` 和 `knowledge/relation_summary.md`。这些文件用于后续项目复用、主题关联和文献去重。
- 不要把中间 JSON、内部状态或调试字段暴露给非 IT 用户；面向用户时输出自然语言结论和可审阅的文件。
- 所有关键判断都要尽量绑定来源、日期、证据强度和不确定性。
- 每次 HTML 报告结构、页签、筛选器、翻译阅读、资料缺口或用户交互方式发生改造时，必须同步迭代 skill 代码、模板、样式、测试、README/SKILL 说明，并提交 Git 版本；不得只改某一个已生成 HTML 文件。

## 推荐流程

1. 理解项目：确认产品、适用场景、目标地区、评审目的和时间限制。
2. 补全检索条件：用文字 RPG 式选项补齐产品类型、检测项目、疾病、样本、平台、预期用途、地区、用户、竞品、文献、专利和报告深度；这是正式检索前的必要动作。
3. 收集材料：整理法规、指南、竞品、文献、市场和技术路线资料。
4. 生成证据卡：记录证据摘要、来源、关键结论、可信度、风险和待复核点。
5. 形成材料包：将原始资料索引、证据卡和状态文件组织成可追溯材料包。
6. 生成报告：输出 V2.1 标准交付目录中的 `00_立项调研综合报告.html`，报告必须采用研发筛选版工作台，含项目分析、研发阅读入口、核心必读文献、全部证据卡和资料缺口；证据地图、缺口任务、关键证据、文献、竞品、标准、专利和指标事实应在这些入口中以业务可读方式呈现。
7. 生成审阅表：输出 `01_证据审阅与补证任务表.xlsx`，便于专家逐条确认、修订和补充。
8. 复制证据卡：标准交付目录必须包含 `02_证据卡/`，其中放置全部 Markdown 证据卡，便于研发、医学和注册人员逐张审阅。
9. 生成知识索引：运行或由交付命令自动触发 `build-knowledge`，形成指标事实、主题索引、文献关系图和候选去重索引。
10. 采集质量审计：运行或由交付流水线自动执行 `source-quality`，检查 no_results 是否存在检索策略假阴性、缺少核心词层级或跨库矛盾。
11. 交付验证：运行 `verify-package`，确认检索条件、来源场景覆盖、失败兜底、采集质量审计、证据卡、人工复核、V2.1 资产和标准交付物是否满足交付门槛；不满足时必须说明 `business_ready=false` 的具体原因。

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
nuoyan life-science-plan --task-id <task_id> --json
```

```bash
ivd-research import-life-science-findings --task-id <task_id> \
  --findings-json-file external_findings.json \
  --query "plasma p-tau217 Alzheimer disease" \
  --json
```

每条 finding 建议包含 `source_database`、`evidence_lane`、`entity`、`query`、`result_summary`、`source_url` 和 `identifier`。导入后必须继续运行 `generate-evidence-cards`、`build-knowledge`、`export-review` 和 `build-standard-delivery`。

## V2.1 文献 profile 与本地知识资产

文献 profile 用于控制速度、召回量和二级下载范围。可选 profile 包括：

- `quick_scan`：快速扫描，默认 50 条/英文文献源，适合 30 分钟内判断是否值得深入。
- `complete_literature`：完整文献，默认 200 条/英文文献源，适合标准调研材料。
- `fulltext_first`：全文优先，默认 200 条/英文文献源并提高全文/PDF 获取优先级，适合方法学和性能参数抽取。
- `core_must_read`：核心必读，默认 100 条/英文文献源，适合研发阅读入口。
- `chinese_first`：中文优先，默认 100 条/英文文献源，适合国内临床应用和注册语境补充。

如需导入本地文献清单或腾讯文档导出表，可使用：

```bash
ivd-research import-literature-table --task-id <task_id> --path literature.xlsx --json
```

本地知识资产通过以下命令生成：

```bash
ivd-research build-knowledge --task-id <task_id> --json
```

采集质量审计用于复盘来源 no_results 是否可信：

```bash
ivd-research source-quality --task-id <task_id> --json
```

该命令是 agent/维护者内部体检工具。业务用户只需要在 HTML 报告“资料缺口”和 Excel“采集异常”中看到“疑似假阴性”和处理建议。

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
