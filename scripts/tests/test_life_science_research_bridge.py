from pathlib import Path

from ivd_research.jsonl import read_jsonl
from ivd_research.source_adapters.life_science_research_bridge import (
    import_life_science_findings,
)


def test_life_science_bridge_imports_plugin_findings(tmp_path: Path):
    result = import_life_science_findings(
        "TASK-001",
        tmp_path,
        [
            {
                "source_database": "UniProt",
                "evidence_lane": "protein",
                "entity": "MAPT",
                "query": "MAPT Alzheimer disease",
                "result_summary": "Tau protein is encoded by MAPT and is relevant to Alzheimer disease biology.",
                "source_url": "https://www.uniprot.org/uniprotkb/P10636/entry",
                "identifier": "P10636",
            }
        ],
        query="MAPT Alzheimer disease",
    )

    assert result["imported_count"] == 1
    materials = list(read_jsonl(tmp_path / "data" / "materials.jsonl"))
    source_runs = list(read_jsonl(tmp_path / "data" / "source_runs.jsonl"))
    assert materials[0]["source_scenario"] == "life_science_research"
    assert materials[0]["source_site_id"] == "life_science_research"
    assert materials[0]["raw_fields"]["source_database"] == "UniProt"
    assert source_runs[0]["evidence_lane"] == "life_science"

