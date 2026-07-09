from ivd_research.reports import (
    build_business_decision,
    build_business_action_rows,
    build_metric_fact_rows,
    build_project_analysis_sections,
    build_section_evidence_rows,
    normalize_evidence_cards,
    normalize_materials,
)


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
    assert "p-Tau217" in joined
    assert "p-Tau181" not in joined
    assert "结构化 Abstract" in joined or "含结构化 Abstract" in joined
    assert "amyloid PET" in joined


def test_hcg_project_analysis_does_not_fall_back_to_ad_template():
    confirmations = {
        "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
        "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
        "sample_type": "血清/尿液",
        "platform": "荧光免疫层析",
        "methodology": "荧光免疫层析法",
        "intended_use": "妊娠相关检测/辅助评估",
    }

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
        confirmations={
            "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
            "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
            "sample_type": "血清/尿液",
            "platform": "荧光免疫层析",
            "methodology": "荧光免疫层析法",
            "intended_use": "妊娠相关检测/辅助评估",
        },
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
        confirmations={
            "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
            "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
            "sample_type": "血清/尿液",
            "platform": "荧光免疫层析",
            "methodology": "荧光免疫层析法",
            "intended_use": "妊娠相关检测/辅助评估",
        },
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
