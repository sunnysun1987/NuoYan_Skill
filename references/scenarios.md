# 场景清单

| scenario_id | 中文名称 | 材料类型 | 关键词策略 | 必要确认 | 失败处理 |
| --- | --- | --- | --- | --- | --- |
| task_intake | 任务理解与关键词确认 | unknown | 产品/指标、疾病、方法学、地区 | task_info | 不生成伪材料，只记录待确认项 |
| cmde_regulatory | CMDE 指导原则、征求意见和审评报告 | regulatory | 中文主关键词、别名、产品类别 | collection_scope | 记录无结果、下载失败、访问失败 |
| nmpa_competitor | NMPA 竞品注册信息 | competitor | 产品名、指标名、方法学、注册证关键词 | methodology | 记录无注册结果或查询限制 |
| standards_current | 现行标准查询 | standard | 指标、疾病、GB/YY/行业标准关键词 | collection_scope | 只把现行或明确有效标准纳入候选 |
| patenthub_patents | 专利信息查询 | patent | 中英文关键词、申请人、方法学 | patent_scope | 登录/验证码/限制必须如实记录 |
| yiigle_zhjyyxzz | 中华检验医学杂志文献 | literature | 中文指标、疾病、检测方法 | literature_date_range | 无全文时记录摘要可得性 |
| yiigle_zhsjkzz | 中华神经科杂志文献 | literature | 中文疾病、标志物、诊断关键词 | literature_date_range | 无全文时记录摘要可得性 |
| cma_lab_management | 中华临床实验室管理电子杂志文献 | literature | 实验室管理、检测流程、质量控制 | literature_date_range | 无全文时记录摘要可得性 |
| pubmed_literature | PubMed 文献题录与摘要 | literature | 英文疾病、靶标、样本、方法学、预期用途 | english_keywords、sample_type、intended_use、literature_date_range | DNS/429/连接失败时缩短检索式重试；仍失败则用 PubMed 页面、期刊官网或 DOI 检索后 `import-finding` 导入；不得直接跳过 |
| pmc_fulltext | PMC 开放全文 | literature | 英文疾病、靶标、样本、方法学、开放全文 | english_keywords、sample_type、literature_date_range | DNS/429/连接失败时缩短检索式重试；全文不可得时记录题录/摘要和全文缺口；不得把无全文写成无证据 |
| openalex_literature | OpenAlex 文献发现与 DOI/OA 信息 | literature | 英文疾病、靶标、样本、方法学、开放获取线索 | english_keywords、literature_date_range | OpenAlex-only 只能作为线索；必须回溯 DOI/PMID/PMCID/期刊官网后进入强证据 |
| wiley_alz | Wiley Alzheimer 文献 | literature | 英文疾病、biomarker、diagnosis | english_keywords | Cloudflare/访问限制不得绕过 |
| yiigle_fulltext | 中华医学期刊全文数据库 | literature | 篇关摘、文献类型、出版日期 | literature_date_range | 登录限制需提示用户提供合法材料 |
| local_import | 本地材料导入 | local_import | 文件名和用户说明 | 无 | 解析失败标记 needs_manual_review |

## 完整调研必要场景

完整可行性调研默认必须执行以下正式场景，除非用户在范围确认阶段明确排除，并在报告中说明排除原因：

- 法规/审评：`cmde_regulatory`
- 竞品注册：`nmpa_competitor`
- 标准：`standards_current`
- 专利：`patenthub_patents`
- 中文文献：`yiigle_zhjyyxzz`、`yiigle_zhsjkzz`、`cma_lab_management`、`yiigle_fulltext`
- 国际文献：`pubmed_literature`、`pmc_fulltext`、`openalex_literature`、`wiley_alz`

完整调研的场景状态不得停留在 `not_started`。失败、权限受限、登录受限、无结果和暂缓都必须有 `last_message`，说明检索式、失败原因、兜底动作和下一步补证任务。

## 失败状态处理口径

- `collection_failed`：说明具体错误，执行至少一次兜底动作；如 DNS 失败，应尝试缩短检索式、公开网页检索、浏览器观察或用户材料导入。
- `no_results`：说明检索式和范围，不能写成“来源不存在”。
- `needs_login` / `permission_required`：不得绕过；请求用户完成合法登录或提供材料。
- `deferred`：只允许用户确认范围排除或当前环境客观无法访问时使用；必须写明影响。
