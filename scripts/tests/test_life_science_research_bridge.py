from pathlib import Path

from ivd_research.jsonl import read_jsonl
from ivd_research.source_adapters.life_science_research_bridge import (
    import_life_science_findings,
)
from ivd_research.status import init_task


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


def test_life_science_bridge_sanitizes_source_database_filename(tmp_path: Path):
    result = import_life_science_findings(
        "TASK-001",
        tmp_path,
        [
            {
                "source_database": "EFO/OLS",
                "evidence_lane": "disease",
                "entity": "Alzheimer disease",
                "result_summary": "EFO/OLS ontology entry for Alzheimer disease.",
                "source_url": "https://www.ebi.ac.uk/ols4/ontologies/efo",
            }
        ],
        query="Alzheimer disease ontology",
    )

    materials = list(read_jsonl(tmp_path / "data" / "materials.jsonl"))

    assert result["imported_count"] == 1
    assert materials[0]["raw_fields"]["source_database"] == "EFO/OLS"
    assert materials[0]["extracted_text_path"] == (
        "extracted_text/life_science_research/MAT-000001_EFO-OLS.txt"
    )
    assert (tmp_path / materials[0]["extracted_text_path"]).exists()


def test_life_science_bridge_updates_task_scenario_status(tmp_path: Path):
    state = init_task("p-tau181 AD 血液标志物", tmp_path)
    task_dir = Path(state.task_dir)

    import_life_science_findings(
        state.task_id,
        task_dir,
        [
            {
                "source_database": "ClinicalTrials.gov",
                "evidence_lane": "clinical",
                "entity": "p-tau181",
                "result_summary": "Clinical trial record mentioning plasma p-tau181 biomarkers.",
            },
            {
                "source_database": "STRING",
                "evidence_lane": "network",
                "entity": "MAPT",
                "result_summary": "STRING network evidence for MAPT.",
            },
        ],
        query="plasma p-tau181 Alzheimer disease",
    )

    task = __import__("json").loads((task_dir / "task.json").read_text(encoding="utf-8"))
    scenario = task["scenario_statuses"]["life_science_research"]

    assert scenario["status"] == "completed"
    assert scenario["material_count"] == 2
    assert "覆盖 2 个数据库、2 个证据通道" in scenario["last_message"]
