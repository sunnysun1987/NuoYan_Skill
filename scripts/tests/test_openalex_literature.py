from pathlib import Path

from ivd_research.evidence import build_draft_evidence_card
from ivd_research.jsonl import append_jsonl
from ivd_research.jsonl import write_json
from ivd_research.models import Material
from ivd_research.review_excel import export_review
from ivd_research.scenarios.openalex_literature import (
    _abstract_from_inverted_index,
    format_openalex_text,
)
from ivd_research.status import create_task_directories


OPENALEX_WORK = {
    "id": "https://openalex.org/W3018431352",
    "display_name": "Blood phosphorylated tau 181 as a biomarker for Alzheimer's disease",
    "doi": "https://doi.org/10.1016/s1474-4422(20)30071-5",
    "ids": {"pmid": "https://pubmed.ncbi.nlm.nih.gov/32333900"},
    "publication_year": 2020,
    "publication_date": "2020-05-01",
    "primary_location": {
        "landing_page_url": "https://doi.org/10.1016/s1474-4422(20)30071-5",
        "source": {"display_name": "The Lancet Neurology"},
    },
    "best_oa_location": {
        "pdf_url": "https://discovery.ucl.ac.uk/10097597/3/Zetterberg_Blood%20phosphorylated%20tau%20181.pdf",
    },
    "open_access": {"is_oa": True, "oa_status": "green"},
    "abstract_inverted_index": {
        "Blood": [0],
        "p-tau181": [1],
        "supports": [2],
        "Alzheimer": [3],
        "biomarker": [4],
        "evaluation": [5],
    },
    "authorships": [{"author": {"display_name": "Thomas K. Karikari"}}],
    "concepts": [{"display_name": "Alzheimer's disease"}, {"display_name": "Biomarker"}],
    "cited_by_count": 1200,
}


def test_openalex_abstract_reconstruction():
    assert (
        _abstract_from_inverted_index(OPENALEX_WORK["abstract_inverted_index"])
        == "Blood p-tau181 supports Alzheimer biomarker evaluation"
    )


def test_openalex_material_flows_to_evidence_card_and_review(tmp_path: Path):
    task_dir = tmp_path / "task"
    create_task_directories(task_dir)
    write_json(
        task_dir / "task.json",
        {
            "task_id": "TEST",
            "topic": "test",
            "task_dir": str(task_dir),
            "created_at": "2026-06-16T00:00:00+08:00",
            "workflow_version": "test",
            "taxonomy_version": "test",
            "scenario_statuses": {},
        },
    )
    text = format_openalex_text(OPENALEX_WORK, "plasma p-tau181 Alzheimer disease")
    text_path = task_dir / "extracted_text" / "literature" / "MAT-000001_openalex.txt"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")
    material = Material(
        material_id="MAT-000001",
        task_id="TEST",
        source_scenario="openalex_literature",
        material_type="literature",
        title=OPENALEX_WORK["display_name"],
        source_url="https://doi.org/10.1016/s1474-4422(20)30071-5",
        search_keyword_or_query="plasma p-tau181 Alzheimer disease",
        collection_path={"scenario_id": "openalex_literature"},
        collection_time="2026-06-16T00:00:00+08:00",
        adapter_id="openalex_literature",
        adapter_version="2.0.0",
        raw_fields={
            "source_database": "OpenAlex",
            "openalex_id": OPENALEX_WORK["id"],
            "doi": "10.1016/s1474-4422(20)30071-5",
            "pmid": "32333900",
            "journal": "The Lancet Neurology",
            "publication_date": "2020-05-01",
            "abstract": _abstract_from_inverted_index(OPENALEX_WORK["abstract_inverted_index"]),
            "pdf_url": OPENALEX_WORK["best_oa_location"]["pdf_url"],
            "fulltext_status": "openalex_metadata",
            "pdf_status": "available_not_downloaded",
        },
        download_status="available_not_downloaded",
        extracted_text_status="completed",
        extracted_text_path=str(text_path.relative_to(task_dir)),
    )
    append_jsonl(task_dir / "data" / "materials.jsonl", material.model_dump(mode="json"))

    card = build_draft_evidence_card(task_dir, material.model_dump(mode="json"), "EC-000001")
    append_jsonl(task_dir / "data" / "evidence_cards.jsonl", card.model_dump(mode="json"))
    review = export_review(task_dir)

    facts = "；".join(card.key_facts)
    assert "PMID：32333900" in facts
    assert "DOI：10.1016/s1474-4422(20)30071-5" in facts
    assert "期刊：The Lancet Neurology" in facts
    assert Path(review["review_path"]).exists()
