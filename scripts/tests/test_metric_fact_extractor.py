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

