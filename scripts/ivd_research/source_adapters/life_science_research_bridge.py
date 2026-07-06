from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ivd_research.jsonl import append_jsonl
from ivd_research.models import Material, SourceRun
from ivd_research.status import count_lines, now_iso, record_materials


LANE_TO_MATERIAL_TYPE = {
    "literature": "literature",
    "target": "literature",
    "protein": "literature",
    "pathway": "literature",
    "network": "literature",
    "disease": "literature",
    "clinical": "literature",
    "genetics": "literature",
}

DEFAULT_LIFE_SCIENCE_MINIMUMS = {
    "materials": 12,
    "databases": 5,
    "lanes": 4,
}


def safe_filename_part(value: str, max_length: int = 60) -> str:
    safe = re.sub(r"[\\/:*?\"<>|]+", "-", str(value or "").strip())
    safe = re.sub(r"\s+", "-", safe).strip(".-")
    return safe[:max_length] or "life-science-research"


def build_life_science_research_plan(task: dict[str, Any]) -> dict[str, Any]:
    confirmations = task.get("confirmations") or {}
    topic = str(task.get("topic") or "").strip()
    primary_query = str(confirmations.get("primary_query") or topic).strip()
    english_query = str(confirmations.get("english_keywords") or primary_query).strip()
    sample_type = str(confirmations.get("sample_type") or "").strip()
    intended_use = str(confirmations.get("intended_use") or "").strip()
    clinical_query = " ".join(
        item for item in [english_query, sample_type, intended_use, "clinical trial"] if item
    )
    return {
        "plugin_name": "life-science-research",
        "router_skill": "life-science-research:research-router-skill",
        "minimum_coverage": DEFAULT_LIFE_SCIENCE_MINIMUMS,
        "import_command": (
            "nuoyan import-life-science-findings --task-id <task_id> "
            "--findings-json-file external_findings.json --query "
            f"\"{english_query}\" --json"
        ),
        "evidence_lanes": [
            {
                "lane": "target_protein",
                "databases": ["UniProt", "Open Targets", "NCBI Gene", "Human Protein Atlas"],
                "query": english_query,
                "purpose": "确认靶标/蛋白基础信息、疾病关联和组织表达。",
            },
            {
                "lane": "pathway_network",
                "databases": ["STRING", "Reactome", "QuickGO"],
                "query": english_query,
                "purpose": "补充通路、互作网络和功能注释证据。",
            },
            {
                "lane": "clinical",
                "databases": ["ClinicalTrials.gov"],
                "query": clinical_query,
                "purpose": "检索临床试验、队列研究和血液/样本相关临床线索。",
            },
            {
                "lane": "genetics_ontology",
                "databases": ["GWAS Catalog", "EFO/OLS"],
                "query": english_query,
                "purpose": "补充遗传关联、疾病本体和公共科学数据库定义。",
            },
        ],
    }


def normalize_external_finding(finding: dict[str, Any]) -> dict[str, Any]:
    source_database = str(
        finding.get("source_database")
        or finding.get("database")
        or finding.get("source")
        or "life_science_research"
    ).strip()
    evidence_lane = str(finding.get("evidence_lane") or finding.get("lane") or "literature").strip()
    entity = str(finding.get("entity") or finding.get("target") or finding.get("biomarker") or "").strip()
    title = str(finding.get("title") or finding.get("result_title") or "").strip()
    summary = str(
        finding.get("result_summary")
        or finding.get("summary")
        or finding.get("content")
        or finding.get("abstract")
        or ""
    ).strip()
    source_url = str(finding.get("source_url") or finding.get("url") or "").strip()
    query = str(finding.get("query") or "").strip()
    identifier = str(
        finding.get("identifier")
        or finding.get("pmid")
        or finding.get("doi")
        or finding.get("nct_id")
        or finding.get("uniprot_id")
        or ""
    ).strip()
    if not title:
        stem = " / ".join(part for part in [source_database, entity, identifier] if part)
        title = stem or "life-science-research 外部科学数据库证据"
    if not summary:
        summary = title
    return {
        **finding,
        "source_database": source_database,
        "evidence_lane": evidence_lane,
        "entity": entity,
        "title": title,
        "result_summary": summary,
        "source_url": source_url,
        "query": query,
        "identifier": identifier,
    }


def import_life_science_findings(
    task_id: str,
    task_dir: Path,
    findings: list[dict[str, Any]],
    *,
    query: str = "",
    skill_name: str = "life-science-research:research-router-skill",
    plugin_name: str = "life-science-research",
) -> dict[str, Any]:
    task_dir = Path(task_dir)
    normalized_findings = [normalize_external_finding(item) for item in findings]
    run_digest = hashlib.sha1(
        "|".join(
            f"{item['source_database']}:{item['query']}:{item['title']}"
            for item in normalized_findings
        ).encode("utf-8")
    ).hexdigest()[:10]
    source_run_id = f"LSR-{run_digest}"
    next_index = count_lines(task_dir / "data" / "materials.jsonl") + 1
    materials: list[Material] = []
    for offset, finding in enumerate(normalized_findings):
        material_id = f"MAT-{next_index + offset:06d}"
        evidence_lane = finding["evidence_lane"]
        material_type = LANE_TO_MATERIAL_TYPE.get(evidence_lane, "literature")
        text_dir = task_dir / "extracted_text" / "life_science_research"
        text_dir.mkdir(parents=True, exist_ok=True)
        source_database_filename = safe_filename_part(finding["source_database"])
        text_path = text_dir / f"{material_id}_{source_database_filename}.txt"
        text_path.write_text(finding["result_summary"], encoding="utf-8")
        relative_text = str(text_path.relative_to(task_dir))
        raw_fields = {
            **finding,
            "source_site_id": "life_science_research",
            "source_name": "Codex life-science-research 插件",
            "plugin_name": plugin_name,
            "skill_name": skill_name,
            "source_run_id": source_run_id,
            "evidence_lane": evidence_lane,
        }
        material = Material(
            material_id=material_id,
            task_id=task_id,
            source_scenario="life_science_research",
            material_type=material_type,
            title=finding["title"],
            source_url=finding["source_url"],
            search_keyword_or_query=finding["query"] or query,
            collection_path={
                "scenario_id": "life_science_research",
                "source_run_id": source_run_id,
                "source_database": finding["source_database"],
                "evidence_lane": evidence_lane,
            },
            collection_time=now_iso(),
            adapter_id="life_science_research_bridge",
            adapter_version="2.1.0",
            raw_fields=raw_fields,
            download_status="not_applicable",
            extracted_text_status="completed",
            extracted_text_path=relative_text,
            content_snapshot_path=relative_text,
            possible_duplicate_keys=[
                key
                for key in [
                    finding.get("identifier", ""),
                    finding.get("source_url", ""),
                    f"{finding['source_database']}:{finding['entity']}",
                ]
                if key
            ],
            source_site_id="life_science_research",
            source_name="Codex life-science-research 插件",
            evidence_lane=evidence_lane,
            source_run_id=source_run_id,
        )
        materials.append(material)
    record_materials(task_dir, materials)
    source_run = SourceRun(
        source_run_id=source_run_id,
        task_id=task_id,
        evidence_lane="life_science",
        source_database=";".join(sorted({item["source_database"] for item in normalized_findings})),
        query=query or ";".join(sorted({item["query"] for item in normalized_findings if item["query"]})),
        plugin_name=plugin_name,
        skill_name=skill_name,
        status="completed" if materials else "no_results",
        imported_material_ids=[item.material_id for item in materials],
        collection_time=now_iso(),
    )
    append_jsonl(task_dir / "data" / "source_runs.jsonl", source_run.model_dump(mode="json"))
    try:
        from ivd_research.status import load_task, save_task

        state = load_task(task_dir)
        scenario = state.scenario_statuses.get("life_science_research")
        if scenario is not None:
            scenario.status = source_run.status
            scenario.material_count += len(materials)
            if not materials:
                scenario.failure_count += 1
            database_count = len({item["source_database"] for item in normalized_findings})
            lane_count = len({item["evidence_lane"] for item in normalized_findings})
            scenario.last_message = (
                f"通过 life-science-research 插件桥接导入 {len(materials)} 条材料，"
                f"覆盖 {database_count} 个数据库、{lane_count} 个证据通道。"
            )
            save_task(state)
    except Exception:
        pass
    return {
        "source_run_id": source_run_id,
        "imported_count": len(materials),
        "material_ids": [item.material_id for item in materials],
    }
