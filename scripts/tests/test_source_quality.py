import json
from pathlib import Path

from ivd_research.jsonl import append_jsonl, write_json
from ivd_research.models import Material
from ivd_research.source_quality import (
    build_source_quality_audit,
    query_attempts_by_scenario,
)
from ivd_research.status import init_task


def _task_with_hcg_profile(tmp_path: Path) -> Path:
    state = init_task("beta-hCG 的定量检测试剂盒", tmp_path)
    task_dir = Path(state.task_dir)
    task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    task["confirmations"].update(
        {
            "task_info": True,
            "keyword_pool": True,
            "collection_scope": True,
            "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
            "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
            "sample_type": "血清/尿液",
            "platform": "荧光免疫层析",
            "methodology": "荧光免疫层析法",
            "intended_use": "妊娠相关检测",
            "target_region": "中国",
            "competitor_scope": "NMPA hCG 同类产品",
            "patent_scope": "中国",
        }
    )
    for scenario_id, status in task["scenario_statuses"].items():
        status["status"] = "completed"
        status["last_message"] = "离线测试：完成。"
    task["scenario_statuses"]["openalex_literature"]["status"] = "no_results"
    task["scenario_statuses"]["openalex_literature"]["material_count"] = 0
    task["scenario_statuses"]["openalex_literature"]["last_message"] = (
        "OpenAlex 未查询到与“beta-hCG human chorionic gonadotropin beta subunit "
        "quantitative fluorescence immunochromatographic assay point-of-care pregnancy "
        "ectopic serum plasma whole blood lateral flow immunoassay POCT sandwich”匹配的公开结果。"
    )
    write_json(task_dir / "task.json", task)
    return task_dir


def _append_pubmed_material(task_dir: Path) -> None:
    material = Material(
        material_id="MAT-000001",
        task_id="TEST",
        source_scenario="pubmed_literature",
        material_type="literature",
        title="Human chorionic gonadotropin immunoassay",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        search_keyword_or_query="human chorionic gonadotropin immunoassay",
        collection_path={"scenario_id": "pubmed_literature"},
        collection_time="2026-07-09T00:00:00+08:00",
        adapter_id="pubmed_literature",
        adapter_version="2.0.0",
        raw_fields={"abstract": "hCG immunoassay evidence."},
        extracted_text_status="completed",
    )
    append_jsonl(task_dir / "data" / "materials.jsonl", material.model_dump(mode="json"))


def test_source_quality_flags_openalex_false_negative_from_long_single_query(tmp_path: Path):
    task_dir = _task_with_hcg_profile(tmp_path)
    _append_pubmed_material(task_dir)
    append_jsonl(
        task_dir / "logs" / "events.jsonl",
        {
            "event": "scenario_query_attempts",
            "scenario_id": "openalex_literature",
            "attempts": [
                {
                    "query_role": "openalex_broad_keywords",
                    "query": (
                        "beta-hCG human chorionic gonadotropin beta subunit quantitative "
                        "fluorescence immunochromatographic assay point-of-care pregnancy "
                        "ectopic serum plasma whole blood lateral flow immunoassay POCT sandwich"
                    ),
                    "status": "no_results",
                    "material_count": 0,
                    "message_zh": "no results",
                }
            ],
        },
    )

    audit = build_source_quality_audit(task_dir)

    assert audit["level"] == "critical"
    assert audit["high_count"] >= 1
    issue_types = {issue["issue_type"] for issue in audit["issues"]}
    assert "single_query_no_results" in issue_types
    assert "missing_core_query" in issue_types
    assert "cross_source_false_negative" in issue_types


def test_source_quality_passes_when_openalex_has_core_attempt(tmp_path: Path):
    task_dir = _task_with_hcg_profile(tmp_path)
    append_jsonl(
        task_dir / "logs" / "events.jsonl",
        {
            "event": "scenario_query_attempts",
            "scenario_id": "openalex_literature",
            "attempts": [
                {
                    "query_role": "openalex_core_keywords",
                    "query": "human chorionic gonadotropin beta hCG immunoassay",
                    "status": "no_results",
                    "material_count": 0,
                    "message_zh": "no results",
                },
                {
                    "query_role": "openalex_broad_keywords",
                    "query": "beta hCG quantitative immunoassay",
                    "status": "no_results",
                    "material_count": 0,
                    "message_zh": "no results",
                },
            ],
        },
    )

    audit = build_source_quality_audit(task_dir)

    issue_types = {issue["issue_type"] for issue in audit["issues"]}
    assert "missing_core_query" not in issue_types
    assert "single_query_no_results" not in issue_types


def test_query_attempts_reads_delivery_browser_events(tmp_path: Path):
    task_dir = _task_with_hcg_profile(tmp_path)
    append_jsonl(
        task_dir / "logs" / "events.jsonl",
        {
            "event": "delivery_browser_workflow_ran",
            "scenario_id": "cmde_regulatory",
            "query_role": "core_cn",
            "attempted_query": "人绒毛膜促性腺激素",
            "status": "no_results",
            "material_count": 0,
            "message_zh": "no results",
        },
    )

    attempts = query_attempts_by_scenario(task_dir)

    assert attempts["cmde_regulatory"][0]["query_role"] == "core_cn"
    assert attempts["cmde_regulatory"][0]["query"] == "人绒毛膜促性腺激素"
