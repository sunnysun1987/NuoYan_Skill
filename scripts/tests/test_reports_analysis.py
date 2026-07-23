from ivd_research.reports import (
    _display_publication_date,
    _screening_translation_items,
    _scenario_level,
    _scenario_status_text,
    build_business_decision,
    build_business_collection_gaps,
    build_business_action_rows,
    build_collection_gap_summary,
    build_expert_decision,
    build_metric_fact_rows,
    build_project_analysis_sections,
    build_screening_cards,
    build_section_evidence_rows,
    normalize_evidence_cards,
    normalize_materials,
)
from ivd_research.quality import build_collection_alerts


def _literature_material():
    return {
        "material_id": "MAT-000001",
        "source_scenario": "pubmed_literature",
        "material_type": "literature",
        "title": "Diagnostic Accuracy of a Plasma Phosphorylated Tau 217 Immunoassay for Alzheimer Disease Pathology",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/38252443/",
        "raw_fields": {
            "pmid": "38252443",
            "pmcid": "PMC1234567",
            "doi": "10.1000/test",
            "journal": "JAMA Neurology",
            "publication_date": "2024-01-01",
            "abstract_sections": [
                {
                    "label": "Objective",
                    "text": "To evaluate plasma p-tau217 for amyloid pathology detection.",
                },
                {
                    "label": "Methods",
                    "text": "A blood-based immunoassay was compared with amyloid PET and CSF biomarkers.",
                },
                {
                    "label": "Results",
                    "text": "The assay showed high diagnostic accuracy with AUC 0.92, sensitivity 91%, and specificity 88%.",
                },
            ],
            "abstract": "Objective: To evaluate plasma p-tau217.\nMethods: A blood-based immunoassay was compared with amyloid PET.\nResults: The assay showed high diagnostic accuracy with AUC 0.92, sensitivity 91%, and specificity 88%.",
            "keywords": ["Alzheimer disease", "blood biomarkers", "p-tau217"],
        },
        "download_status": "not_available",
        "extracted_text_status": "completed",
        "extracted_text_path": "extracted_text/literature/MAT-000001.txt",
    }


def test_screening_translation_reads_cache_without_creating_engine(tmp_path):
    import ivd_research.reports as reports

    assert not hasattr(reports, "TranslationEngine")
    material = _literature_material()

    items = _screening_translation_items(
        {"material_id": "MAT-000001", "excerpt_lines": []},
        material,
        translation_cache={},
        translation_capability={
            "configured": True,
            "command_available": True,
            "_task_dir": str(tmp_path),
        },
    )

    assert items[0]["status"] == "not_generated"


def test_partial_scenario_is_not_rendered_as_success():
    assert _scenario_level("completed_with_warnings", 3) == "warn"
    assert "部分完成" in _scenario_status_text("completed_with_warnings", 3)


def test_publication_date_uses_current_day_at_call_time(monkeypatch):
    from datetime import date as real_date

    class MutableDate(real_date):
        current = real_date(2026, 7, 23)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr("ivd_research.reports.date", MutableDate)
    assert "未来日期" in _display_publication_date("2026-07-24")

    MutableDate.current = real_date(2026, 7, 25)
    assert _display_publication_date("2026-07-24") == "2026-07-24"


def _hcg_literature_material():
    return {
        "material_id": "MAT-000002",
        "source_scenario": "pubmed_literature",
        "material_type": "literature",
        "title": "A Point-of-Care Immunosensor for Human Chorionic Gonadotropin in Clinical Urine Samples",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/example/",
        "raw_fields": {
            "abstract": "Human chorionic gonadotropin assays support pregnancy-related testing and tumor monitoring workflows.",
            "keywords": ["human chorionic gonadotropin", "pregnancy", "immunoassay"],
        },
    }


def _multiplex_method_material():
    return {
        "material_id": "MAT-000003",
        "source_scenario": "openalex_literature",
        "material_type": "literature",
        "title": "Potential-Resolved Multicolor Electrochemiluminescence for Multiplex Immunoassay in a Single Sample",
        "source_url": "https://doi.org/10.1021/jacs.8b09422",
        "raw_fields": {
            "abstract": (
                "Electrochemiluminescence supports multiplex immunoassay development "
                "for multiple biomarkers in a single sample."
            ),
            "keywords": ["multiplex immunoassay", "electrochemiluminescence"],
        },
    }


def _respiratory_method_material():
    return {
        "material_id": "MAT-000004",
        "source_scenario": "pmc_fulltext",
        "material_type": "literature",
        "title": "Microfluidic-based virus detection methods for respiratory diseases",
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7992628/",
        "raw_fields": {
            "abstract": (
                "This review summarizes microfluidic-based detection technologies "
                "for respiratory viruses."
            ),
            "keywords": ["respiratory disease", "virus detection", "biosensors"],
        },
    }


def _hcg_confirmations():
    return {
        "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
        "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
        "chinese_synonyms": "β-hCG；人绒毛膜促性腺激素；hCG",
        "sample_type": "血清/尿液",
        "platform": "荧光免疫层析",
        "methodology": "荧光免疫层析法",
        "intended_use": "妊娠相关检测/辅助评估",
    }


def _pct_confirmations():
    return {
        "primary_query": "降钙素原 PCT 定量检测试剂盒（化学发光法）",
        "english_keywords": "procalcitonin PCT immunoassay sepsis",
        "chinese_synonyms": "降钙素原；PCT",
        "sample_type": "血清/血浆",
        "platform": "化学发光",
        "methodology": "免疫分析",
        "intended_use": "细菌感染和脓毒症风险辅助评估",
    }


def test_normalize_materials_preserves_structured_abstract():
    normalized = normalize_materials([_literature_material()], [])

    material = normalized[0]
    assert material["structured_abstract"].startswith("Objective: To evaluate plasma p-tau217")
    assert "Methods: A blood-based immunoassay" in material["structured_abstract"]
    assert "Keywords: Alzheimer disease；blood biomarkers；p-tau217" in material["structured_abstract"]
    assert material["abstract_sections_display"][0] == {
        "label": "Objective",
        "text": "To evaluate plasma p-tau217 for amyloid pathology detection.",
    }
    assert material["abstract_sections_translated"] == []
    assert material["parameter_items"]


def test_chinese_reading_version_is_disabled_even_with_translation_cache(tmp_path):
    material = _literature_material()
    material["raw_fields"]["abstract_sections"] = [
        {
            "label": "Results",
            "text": (
                "First sentence reports amyloid PET. "
                "Second sentence reports plasma biomarkers. "
                "Third sentence reports AUC 0.92. "
                "Fourth sentence reports disease progression over time."
            ),
        }
    ]

    normalized = normalize_materials([material], [], task_dir=tmp_path)

    assert normalized[0]["abstract_sections_translated"] == []


def test_key_evidence_display_facts_exclude_section_blocks():
    normalized = normalize_evidence_cards(
        [
            {
                "title": "Blood biomarker evidence",
                "summary": "Blood biomarker evidence summary.",
                "material_type": "literature",
                "evidence_strength": "needs_review",
                "key_facts": [
                    "期刊：JAMA Neurology",
                    "样本类型：血浆",
                    "Abstract[Results]：AUC 0.92 with sensitivity 91%.",
                    "Keywords：Alzheimer disease；blood biomarkers",
                    "中文译文[结果]：AUC 0.92。",
                    "参数[AUC]：0.92",
                ],
            }
        ]
    )

    card = normalized[0]
    assert card["display_facts"] == ["样本类型：血浆"]
    assert card["translation_facts"] == []
    assert card["parameter_facts"] == ["参数[AUC]：0.92"]


def test_project_analysis_uses_literature_signals_and_current_marker():
    sections = build_project_analysis_sections(
        literature_materials=[_literature_material()],
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        materials=[_literature_material()],
    )

    joined = "\n".join(section["analysis"] for section in sections)
    assert "p-tau217" in joined.lower()
    assert "p-tau181" not in joined.lower()
    assert "结构化 Abstract" in joined or "含结构化 Abstract" in joined
    assert "amyloid PET" in joined


def test_hcg_project_analysis_does_not_fall_back_to_ad_template():
    confirmations = _hcg_confirmations()

    sections = build_project_analysis_sections(
        literature_materials=[_hcg_literature_material()],
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        materials=[_hcg_literature_material()],
        confirmations=confirmations,
    )
    joined = "\n".join(section["analysis"] for section in sections)

    for forbidden in ["AD", "MCI", "PET/CSF", "amyloid PET", "认知障碍", "阿尔茨海默"]:
        assert forbidden not in joined
    assert "beta-hCG" in joined or "hCG" in joined
    assert "妊娠" in joined or "绒毛膜促性腺激素" in joined


def test_hcg_business_actions_do_not_use_ad_supplement_tasks():
    rows = build_business_action_rows(
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        literature_materials=[_hcg_literature_material()],
        scenario_map={},
        confirmations=_hcg_confirmations(),
    )
    joined = "\n".join(row["action"] for row in rows)

    for forbidden in ["AD", "阿尔茨海默", "认知障碍"]:
        assert forbidden not in joined
    assert "hCG" in joined or "beta-hCG" in joined


def test_hcg_business_decision_is_generic_ivd_not_ad_specific():
    decision = build_business_decision(
        materials=[_hcg_literature_material()],
        literature_materials=[_hcg_literature_material()],
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        scenario_map={},
        confirmations=_hcg_confirmations(),
    )
    joined = "\n".join(
        [
            decision["conclusion"],
            "\n".join(decision["basis"]),
            "\n".join(decision["cannot_conclude"]),
            decision["recommendation"],
        ]
    )

    for forbidden in ["AD", "阿尔茨海默", "认知障碍", "PET/CSF"]:
        assert forbidden not in joined
    assert "hCG" in joined or "beta-hCG" in joined


def test_hcg_project_profile_ignores_broad_multiplex_and_respiratory_literature_titles():
    confirmations = _hcg_confirmations()
    materials = [
        _hcg_literature_material(),
        _multiplex_method_material(),
        _respiratory_method_material(),
    ]

    sections = build_project_analysis_sections(
        literature_materials=materials,
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        materials=materials,
        confirmations=confirmations,
    )
    decision = build_business_decision(
        materials=materials,
        literature_materials=materials,
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        scenario_map={},
        confirmations=confirmations,
    )
    expert = build_expert_decision(
        decision,
        materials=materials,
        screening_summary={"total": 3, "core": 1},
        knowledge_status={"metric_fact_count": 0},
        failed_scenarios=[],
        collection_gap_summary={"gap_count": 0},
        confirmations=confirmations,
    )
    joined = "\n".join(
        [section["analysis"] for section in sections]
        + [decision["conclusion"], "\n".join(decision["basis"]), expert["judgement"], expert["positioning"]]
    )

    for forbidden in ["甲型/乙型流感", "甲乙流", "发热门急诊", "呼吸道感染病原体", "流感季"]:
        assert forbidden not in joined
    assert "beta-hCG" in joined or "hCG" in joined


def test_confirmed_generic_project_cannot_be_overridden_by_unrelated_material_titles():
    confirmations = _pct_confirmations()
    materials = [
        _literature_material(),
        _multiplex_method_material(),
        _respiratory_method_material(),
    ]

    sections = build_project_analysis_sections(
        literature_materials=materials,
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        materials=materials,
        confirmations=confirmations,
    )
    decision = build_business_decision(
        materials=materials,
        literature_materials=materials,
        regulatory_materials=[],
        competitor_materials=[],
        standard_materials=[],
        patent_materials=[],
        scenario_map={},
        confirmations=confirmations,
    )
    expert = build_expert_decision(
        decision,
        materials=materials,
        screening_summary={"total": 3, "core": 1},
        knowledge_status={"metric_fact_count": 0},
        failed_scenarios=[],
        collection_gap_summary={"gap_count": 0},
        confirmations=confirmations,
    )
    joined = "\n".join(
        [section["analysis"] for section in sections]
        + [decision["conclusion"], expert["judgement"], expert["positioning"], expert["validation_focus"]]
    )

    assert "降钙素原" in joined
    assert "细菌感染和脓毒症风险辅助评估" in joined
    for forbidden in ["甲型/乙型流感", "发热门急诊", "AD 血液", "PET/CSF", "认知障碍专病门诊"]:
        assert forbidden not in joined


def test_screening_uses_confirmed_marker_aliases_without_taxonomy_entry():
    material = {
        "material_id": "MAT-PCT",
        "source_scenario": "pubmed_literature",
        "material_type": "literature",
        "title": "Serum procalcitonin for sepsis risk assessment",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/example/",
        "raw_fields": {
            "abstract": (
                "Procalcitonin was measured in serum samples; p-tau217 and influenza "
                "were mentioned only as unrelated comparators."
            )
        },
    }
    card = {
        "evidence_card_id": "EC-PCT",
        "material_id": "MAT-PCT",
        "title": material["title"],
        "summary": "Procalcitonin evidence for sepsis risk assessment.",
    }

    rows = build_screening_cards(
        normalize_materials([material], []),
        [card],
        confirmations={**_pct_confirmations(), "chinese_synonyms": "降钙素原；procalcitonin；PCT"},
    )

    assert rows[0]["markers"] == ["降钙素原"]


def test_collection_gaps_show_public_fallback_without_closing_official_task():
    scenario_statuses = [
        {
            "scenario_id": "standards_current",
            "label_zh": "现行标准查询",
            "status": "no_results",
            "last_message": "源站搜索未命中标准题录。",
        },
        {
            "scenario_id": "patenthub_patents",
            "label_zh": "专利信息查询",
            "status": "needs_login",
            "last_message": "PatentHub 需要登录。",
        },
        {
            "scenario_id": "cmde_regulatory",
            "label_zh": "CMDE 指导原则、征求意见和审评报告",
            "status": "no_results",
            "last_message": "未命中指导原则。",
        },
    ]
    materials = [
        {
            "material_id": "MAT-STD",
            "source_scenario": "web_search_public_fallback",
            "material_type": "standard",
            "title": "全国标准信息公共服务平台：YY/T 1164-2021",
            "source_url": "https://std.samr.gov.cn/example",
        },
        {
            "material_id": "MAT-PAT",
            "source_scenario": "life_science_research",
            "material_type": "literature",
            "title": "Google Patents CN107677837A: beta-HCG test kit",
            "source_url": "https://patents.google.com/patent/CN107677837A/zh",
            "raw_fields": {"source_database": "Google Patents", "evidence_lane": "patent_landscape"},
        },
    ]

    rows = build_business_collection_gaps(
        {},
        scenario_statuses,
        materials=materials,
        required_scenario_ids={"standards_current", "patenthub_patents", "cmde_regulatory"},
    )
    by_source = {row["source"]: row for row in rows}

    assert by_source["现行标准查询"]["status"] == "已公开兜底部分补齐"
    assert by_source["现行标准查询"]["status_level"] == "warn"
    assert by_source["专利信息查询"]["status"] == "已公开兜底部分补齐"
    assert by_source["专利信息查询"]["fallback_count"] == 1
    assert by_source["CMDE 指导原则、征求意见和审评报告"]["status"] == "未发现匹配材料"

    summary = build_collection_gap_summary(rows, materials=materials, evidence_cards=[])
    assert summary["gap_count"] == 1
    assert summary["fallback_covered_count"] == 2
    assert "已用公开兜底材料部分补齐" in summary["headline"]


def test_collection_alerts_report_fallback_covered_sources():
    alerts = build_collection_alerts(
        materials=[
            {
                "material_id": "MAT-STD",
                "source_scenario": "web_search_public_fallback",
                "material_type": "standard",
                "title": "YY/T 1164-2021",
                "source_url": "https://std.samr.gov.cn/example",
            }
        ],
        evidence_cards=[{"evidence_card_id": "EC-1"}],
        scenario_statuses=[
            {
                "scenario_id": "standards_current",
                "label_zh": "现行标准查询",
                "status": "no_results",
                "last_message": "标准站内检索未命中。",
            }
        ],
        required_scenario_ids={"standards_current"},
    )

    assert alerts["fallback_covered_count"] == 1
    assert any("公开兜底材料" in message for message in alerts["warning_messages"])


def test_chinese_literature_gap_is_not_covered_by_generic_pubmed_material():
    rows = build_business_collection_gaps(
        {},
        [
            {
                "scenario_id": "cma_lab_management",
                "label_zh": "中华临床实验室管理电子杂志文献",
                "status": "no_results",
                "last_message": "中文期刊源未命中。",
            }
        ],
        materials=[
            {
                "material_id": "MAT-PUB",
                "source_scenario": "pubmed_literature",
                "material_type": "literature",
                "title": "Generic PubMed hCG evidence",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/example/",
            }
        ],
        required_scenario_ids={"cma_lab_management"},
    )

    assert rows[0]["status"] == "未发现匹配材料"
    assert rows[0]["fallback_count"] == 0


def test_metric_fact_rows_use_chinese_labels_and_links():
    material = normalize_materials([_literature_material()], [])[0]
    rows = build_metric_fact_rows(
        [
            {
                "metric_fact_id": "MF-000001",
                "metric_type": "sensitivity",
                "value": "91%",
                "material_id": "MAT-000001",
                "evidence_card_id": "EC-000001",
                "excerpt": "The assay showed sensitivity 91%.",
            }
        ],
        materials_by_id={"MAT-000001": material},
        screening_cards=[
            {
                "card_id": "EC-000001",
                "title": "Evidence card title",
                "display_title": "证据卡标题",
            }
        ],
    )

    row = rows[0]
    assert row["metric_type_zh"] == "检出灵敏度"
    assert "漏检风险" in row["metric_explanation"]
    assert row["material_title"].startswith("Diagnostic Accuracy")
    assert row["material_href"] == "https://pubmed.ncbi.nlm.nih.gov/38252443/"
    assert row["evidence_card_anchor"] == "evidence-card-EC-000001"


def test_section_evidence_rows_are_paginated_in_ui_not_hard_limited():
    materials = []
    cards = []
    for index in range(9):
        material = _literature_material()
        material["material_id"] = f"MAT-{index:06d}"
        material["title"] = f"Clinical diagnostic evidence for influenza multiplex assay {index}"
        material["raw_fields"] = {
            **material["raw_fields"],
            "abstract": (
                "Clinical diagnostic evidence describes respiratory influenza multiplex assay "
                "performance in adult patients."
            ),
        }
        materials.append(material)
        cards.append(
            {
                "card_id": f"EC-{index:06d}",
                "material_id": material["material_id"],
                "title": material["title"],
                "display_title": material["title"],
                "summary": "Clinical diagnostic evidence for respiratory influenza multiplex assay.",
                "key_facts": ["临床诊断：呼吸道甲乙流多重联检"],
                "priority_label": "A 核心必读",
            }
        )

    rows = build_section_evidence_rows(
        "临床意义",
        materials=normalize_materials(materials, []),
        screening_cards=cards,
    )

    assert len(rows) == 9
    assert rows[0]["evidence_card_anchor"].startswith("evidence-card-EC-")
