import os
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ivd_research.cli import app
from ivd_research.confirmations import update_confirmations
from ivd_research.evidence import generate_draft_evidence_cards
from ivd_research.jsonl import read_jsonl
from ivd_research.review_excel import export_review
from ivd_research.status import init_task


pytestmark = [
    pytest.mark.live_network,
    pytest.mark.skipif(
        os.getenv("NUOYAN_RUN_LIVE_TESTS") != "1",
        reason="Set NUOYAN_RUN_LIVE_TESTS=1 to run real public-source acceptance tests.",
    ),
]


def test_live_openalex_and_pubmed_flow_to_evidence_cards(tmp_path: Path):
    output_root = tmp_path / "live-output"
    state = init_task("CRP public literature live acceptance", output_root)
    task_dir = Path(state.task_dir)
    update_confirmations(
        task_dir,
        {
            "task_info": True,
            "keyword_pool": True,
            "collection_scope": True,
            "primary_query": "C反应蛋白 CRP 定量检测试剂盒",
            "english_keywords": "C-reactive protein CRP immunoassay",
            "sample_type": "serum/plasma",
            "platform": "immunoassay",
            "methodology": "quantitative immunoassay",
            "intended_use": "inflammation assessment",
            "target_region": "public international literature",
            "competitor_scope": "excluded from public literature acceptance test",
            "literature_date_range": {"start": "2021-01-01", "end": "2026-07-23"},
            "literature_profile": "quick_scan",
            "literature_retmax": 1,
            "patent_scope": "excluded from public literature acceptance test",
            "life_science_required": False,
            "life_science_scope": "public literature acceptance test only",
        },
    )

    runner = CliRunner()
    for scenario in ["openalex_literature", "pubmed_literature"]:
        result = runner.invoke(
            app,
            [
                "run-scenario",
                "--task-id",
                state.task_id,
                "--scenario",
                scenario,
                "--output-root",
                str(output_root),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output

    materials = list(read_jsonl(task_dir / "data" / "materials.jsonl"))
    by_source = {row["source_scenario"]: row for row in materials}
    assert len(materials) == 2
    assert (by_source["openalex_literature"].get("raw_fields") or {}).get("openalex_id")
    assert (by_source["pubmed_literature"].get("raw_fields") or {}).get("pmid")
    assert all(row.get("title") and row.get("source_url") for row in materials)

    evidence_result = generate_draft_evidence_cards(task_dir)
    cards = list(read_jsonl(task_dir / "data" / "evidence_cards.jsonl"))
    cards_by_source = {card["source_type"]: card for card in cards}
    review_result = export_review(task_dir)

    assert evidence_result["generated_count"] == 2
    assert evidence_result["committed_count"] == 2
    assert len(cards) == 2
    openalex_identifier = cards_by_source["openalex_literature"]["identifier"]
    openalex_raw = by_source["openalex_literature"].get("raw_fields") or {}
    expected_openalex_identifier = next(
        str(openalex_raw.get(key) or "").strip()
        for key in ["pmid", "pmcid", "doi", "openalex_id"]
        if str(openalex_raw.get(key) or "").strip()
    )
    assert openalex_identifier == expected_openalex_identifier
    assert re.fullmatch(
        r"(?:\d+|PMC\d+|10\..+|https://openalex\.org/W\d+)",
        openalex_identifier,
    )
    assert cards_by_source["pubmed_literature"]["identifier"].isdigit()
    assert Path(review_result["review_path"]).exists()
