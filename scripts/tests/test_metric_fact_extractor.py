from ivd_research.knowledge.fact_extractor import extract_metric_facts


def test_metric_fact_extractor_finds_performance_values():
    material = {
        "material_id": "MAT-000001",
        "raw_fields": {
            "abstract": (
                "The assay achieved AUC 0.92 for amyloid PET positivity. "
                "Sensitivity was 88% and specificity was 81%. "
                "The cut-off was 0.42 pg/mL in 320 participants."
            )
        },
    }

    facts = extract_metric_facts(material, evidence_card_id="EC-000001")
    by_type = {fact.metric_type: fact.value for fact in facts}

    assert by_type["AUC"] == "0.92"
    assert by_type["sensitivity"] == "88%"
    assert by_type["specificity"] == "81%"
    assert "cutoff" in by_type
    assert "sample_size" in by_type


def test_metric_fact_extractor_rejects_engineering_sensitivity_and_citation_numbers():
    material = {
        "material_id": "MAT-000021",
        "raw_fields": {
            "abstract": (
                "The sensitivity of the pH meter-based immunoassay was 9.77 pH ng/mL. "
                "High-sensitivity CRP detection at a level of 1 ng/mL is demanded [3,4]. "
                "For specificity, the FDA 510(k) tested cross-reactants. "
                "Analytical sensitivity was 95% for the sensor response. "
                "Engineering sensitivity was 96% in a circuit benchmark. "
                "Analytical assay sensitivity was 94% for the optical sensor. "
                "The signal was collected by filter2 or filter3, selected in turn."
            )
        },
    }

    facts = extract_metric_facts(material, evidence_card_id="EC-000021")

    assert not {"sensitivity", "specificity", "OR"}.intersection(
        fact.metric_type for fact in facts
    )


def test_metric_fact_extractor_preserves_lod_and_complete_cutoff_range():
    material = {
        "material_id": "MAT-000022",
        "raw_fields": {
            "abstract": (
                "The limit of detection was 5.9 pg/mL. "
                "The assay cutoff concentration was approximately 9 to 10 mIU/mL."
            )
        },
    }

    facts = extract_metric_facts(material, evidence_card_id="EC-000022")
    by_type = {fact.metric_type: fact.value for fact in facts}

    assert by_type["lod"] == "5.9 pg/mL"
    assert by_type["cutoff"] == "9 to 10 mIU/mL"


def test_metric_fact_extractor_preserves_spaced_inverse_volume_units():
    material = {
        "material_id": "MAT-000023",
        "raw_fields": {
            "abstract": (
                "The limit of detection was 0.015 mg L-1. "
                "A second platform had a LoD of 0.93 ng mL− 1."
            )
        },
    }

    facts = extract_metric_facts(material, evidence_card_id="EC-000023")

    assert [fact.value for fact in facts if fact.metric_type == "lod"] == [
        "0.015 mg L-1",
        "0.93 ng mL− 1",
    ]


def test_metric_fact_extractor_does_not_treat_assay_capacity_as_sample_size():
    material = {
        "material_id": "MAT-000024",
        "raw_fields": {
            "abstract": "The array accommodates 24 samples and 12 analytes in each run."
        },
    }

    facts = extract_metric_facts(material, evidence_card_id="EC-000024")

    assert all(fact.metric_type != "sample_size" for fact in facts)


def test_metric_fact_extractor_binds_paired_sensitivity_and_specificity_values():
    material = {
        "material_id": "MAT-000025",
        "raw_fields": {
            "abstract": (
                "Sensitivity and specificity were 88% and 81%, respectively. "
                "In validation, sensitivity/specificity: 0.90/0.82."
            )
        },
    }

    facts = extract_metric_facts(material, evidence_card_id="EC-000025")

    assert [(fact.metric_type, fact.value) for fact in facts] == [
        ("sensitivity", "88%"),
        ("specificity", "81%"),
        ("sensitivity", "0.90"),
        ("specificity", "0.82"),
    ]


def test_metric_fact_extractor_supports_common_diagnostic_and_chinese_forms():
    material = {
        "material_id": "MAT-000026",
        "raw_fields": {
            "abstract": (
                "Diagnostic sensitivity was 0.88 and clinical specificity: 0.81. "
                "The limit of detection (LoD) was 5.9 pg/mL. "
                "The cut-off value was 10 mg/L. "
                "诊断灵敏度：92%，特异性：89%。"
            )
        },
    }

    facts = extract_metric_facts(material, evidence_card_id="EC-000026")
    values = {(fact.metric_type, fact.value) for fact in facts}

    assert ("sensitivity", "0.88") in values
    assert ("specificity", "0.81") in values
    assert ("lod", "5.9 pg/mL") in values
    assert ("cutoff", "10 mg/L") in values
    assert ("sensitivity", "92%") in values
    assert ("specificity", "89%") in values
