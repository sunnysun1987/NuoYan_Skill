from pathlib import Path

from ivd_research.jsonl import append_jsonl
from ivd_research.knowledge.literature_graph import build_literature_knowledge
from ivd_research.knowledge.topic_index import build_topic_index


def test_literature_knowledge_outputs_metric_topic_and_graph(tmp_path: Path):
    append_jsonl(
        tmp_path / "data" / "materials.jsonl",
        {
            "material_id": "MAT-000001",
            "material_type": "literature",
            "source_scenario": "pubmed_literature",
            "title": "Plasma p-tau217 predicts amyloid PET",
            "raw_fields": {
                "pmid": "12345678",
                "abstract": "Plasma p-tau217 showed AUC 0.91 against amyloid PET in plasma samples.",
            },
            "possible_duplicate_keys": ["pmid:12345678"],
        },
    )
    append_jsonl(
        tmp_path / "data" / "evidence_cards.jsonl",
        {
            "evidence_card_id": "EC-000001",
            "material_id": "MAT-000001",
            "title": "Plasma p-tau217 predicts amyloid PET",
            "summary": "p-tau217 evidence",
            "key_excerpts": [{"text": "AUC 0.91 against amyloid PET", "location": "abstract"}],
        },
    )

    result = build_literature_knowledge(tmp_path)

    assert result["metric_fact_count"] == 1
    assert (tmp_path / "knowledge" / "metric_facts.jsonl").exists()
    assert (tmp_path / "knowledge" / "topic_index.json").exists()
    assert (tmp_path / "knowledge" / "literature_graph.json").exists()


def test_topic_index_uses_confirmed_marker_aliases_for_new_projects():
    topics = build_topic_index(
        [
            {
                "material_id": "MAT-PCT",
                "title": "Serum procalcitonin for sepsis risk assessment",
                "raw_fields": {"abstract": "Procalcitonin was measured in serum."},
            }
        ],
        [],
        confirmations={
            "primary_query": "降钙素原 PCT 定量检测试剂盒",
            "chinese_synonyms": "降钙素原；procalcitonin；PCT",
        },
    )

    assert topics["marker"]["procalcitonin"] == ["MAT-PCT"]
