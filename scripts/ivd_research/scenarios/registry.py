from .base import ScenarioAdapter


def all_scenarios() -> list[ScenarioAdapter]:
    return [
        ScenarioAdapter(
            scenario_id="task_intake",
            label_zh="任务理解与关键词确认",
            material_type="unknown",
            adapter_id="task_intake",
            adapter_version="0.1.0",
            content_validation_rules=["确认项目对象、目标用途、地区和关键词池"],
        ),
        ScenarioAdapter(
            scenario_id="cmde_regulatory",
            label_zh="CMDE 指导原则、征求意见和审评报告",
            material_type="regulatory",
            adapter_id="cmde_regulatory",
            adapter_version="0.1.0",
            keyword_types=["primary_cn", "alternate_cn"],
            content_validation_rules=[
                "结果来源属于审评报告、指导原则或征求意见",
                "详情页包含标题、发布日期或附件信息",
            ],
        ),
        ScenarioAdapter(
            scenario_id="nmpa_competitor",
            label_zh="NMPA 竞品注册信息",
            material_type="competitor",
            adapter_id="nmpa_competitor",
            adapter_version="0.1.0",
            required_confirmations=["methodology"],
            keyword_types=["primary_cn", "product_or_indicator", "methodology"],
            content_validation_rules=[
                "结果包含注册证编号",
                "详情页包含注册人和产品名称",
            ],
        ),
        ScenarioAdapter(
            scenario_id="standards_current",
            label_zh="现行标准查询",
            material_type="standard",
            adapter_id="standards_current",
            adapter_version="0.1.0",
            keyword_types=["primary_cn", "alternate_cn"],
            content_validation_rules=[
                "标准状态为现行",
                "列表包含标准号和标准名称",
            ],
        ),
        ScenarioAdapter(
            scenario_id="patenthub_patents",
            label_zh="专利信息查询",
            material_type="patent",
            adapter_id="patenthub_patents",
            adapter_version="0.1.0",
            required_confirmations=["patent_scope"],
            keyword_types=["primary_cn", "primary_en", "alternate_en"],
            content_validation_rules=[
                "专利条目包含标题或公开号",
                "登录或访问阻挡必须记录为受限状态",
            ],
        ),
        ScenarioAdapter(
            scenario_id="yiigle_zhjyyxzz",
            label_zh="中华检验医学杂志文献",
            material_type="literature",
            adapter_id="yiigle_zhjyyxzz",
            adapter_version="0.1.0",
            keyword_types=["primary_cn", "alternate_cn"],
            content_validation_rules=["文献详情包含标题、作者、日期或 DOI"],
        ),
        ScenarioAdapter(
            scenario_id="yiigle_zhsjkzz",
            label_zh="中华神经科杂志文献",
            material_type="literature",
            adapter_id="yiigle_zhsjkzz",
            adapter_version="0.1.0",
            keyword_types=["primary_cn", "alternate_cn"],
            content_validation_rules=["文献详情包含标题、作者、日期或 DOI"],
        ),
        ScenarioAdapter(
            scenario_id="cma_lab_management",
            label_zh="中华临床实验室管理电子杂志文献",
            material_type="literature",
            adapter_id="cma_lab_management",
            adapter_version="0.1.0",
            keyword_types=["primary_cn", "alternate_cn"],
            content_validation_rules=["文献详情包含 DOI、摘要或期刊信息"],
        ),
        ScenarioAdapter(
            scenario_id="wiley_alz",
            label_zh="Wiley Alzheimer 文献",
            material_type="literature",
            adapter_id="wiley_alz",
            adapter_version="0.1.0",
            required_confirmations=["english_keywords"],
            keyword_types=["primary_en", "alternate_en"],
            content_validation_rules=[
                "文献详情包含标题、作者、DOI 或摘要",
                "Cloudflare 或访问限制必须记录",
            ],
        ),
        ScenarioAdapter(
            scenario_id="pubmed_literature",
            label_zh="PubMed 医学文献检索",
            material_type="literature",
            adapter_id="pubmed_literature",
            adapter_version="2.0.0",
            keyword_types=["primary_en", "alternate_en", "primary_cn"],
            content_validation_rules=[
                "使用 NCBI E-utilities 官方接口检索",
                "文献记录必须保留 PMID；DOI、PMCID、摘要缺失时如实标记",
                "触发 NCBI 限流或访问失败必须记录真实状态",
            ],
        ),
        ScenarioAdapter(
            scenario_id="pmc_fulltext",
            label_zh="PMC 开放全文与 PDF 获取",
            material_type="literature",
            adapter_id="pmc_fulltext",
            adapter_version="2.0.0",
            keyword_types=["primary_en", "alternate_en", "primary_cn"],
            content_validation_rules=[
                "使用 NCBI E-utilities 官方接口检索开放全文",
                "优先获取 PMC XML 正文，同时尝试官方下载 PDF",
                "PDF 不可用、下载失败或限流必须记录真实状态",
            ],
        ),
        ScenarioAdapter(
            scenario_id="openalex_literature",
            label_zh="OpenAlex 文献检索",
            material_type="literature",
            adapter_id="openalex_literature",
            adapter_version="2.0.0",
            keyword_types=["primary_en", "alternate_en", "primary_cn"],
            content_validation_rules=[
                "使用 OpenAlex 官方 Works API 检索",
                "文献记录应保留 OpenAlex ID、DOI、PMID、期刊、发表日期和开放获取状态",
                "开放 PDF 链接可用时必须进入材料台账，下载失败不得伪装为完成",
            ],
        ),
        ScenarioAdapter(
            scenario_id="yiigle_fulltext",
            label_zh="中华医学期刊全文数据库",
            material_type="literature",
            adapter_id="yiigle_fulltext",
            adapter_version="0.1.0",
            required_confirmations=["literature_date_range"],
            keyword_types=["primary_cn"],
            content_validation_rules=[
                "检索式使用篇关摘、文献类型和出版日期",
                "结果包含文献标题",
            ],
        ),
        ScenarioAdapter(
            scenario_id="local_import",
            label_zh="本地材料导入",
            material_type="local_import",
            adapter_id="local_import",
            adapter_version="0.1.0",
            content_validation_rules=["文件存在", "生成待确认材料类型"],
        ),
        ScenarioAdapter(
            scenario_id="life_science_research",
            label_zh="life-science-research 外部科学数据库证据",
            material_type="literature",
            adapter_id="life_science_research_bridge",
            adapter_version="2.1.0",
            keyword_types=["primary_en", "target", "disease", "evidence_lane"],
            content_validation_rules=[
                "插件结果必须回写材料管线",
                "每条结果保留 source_database、query、entity、source_url 和 source_run",
                "临床、遗传、通路证据不得直接外推为诊断性能证据",
            ],
        ),
    ]


def get_scenario(scenario_id: str) -> ScenarioAdapter:
    for scenario in all_scenarios():
        if scenario.scenario_id == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario: {scenario_id}")
