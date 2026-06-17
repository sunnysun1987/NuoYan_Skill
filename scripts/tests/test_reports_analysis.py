from ivd_research.reports import (
    build_project_analysis_sections,
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
