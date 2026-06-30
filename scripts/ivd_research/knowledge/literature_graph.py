from __future__ import annotations

from pathlib import Path
from typing import Any

from ivd_research.jsonl import append_jsonl, read_jsonl, write_json
from ivd_research.models import EvidenceRelation, MetricFact
from ivd_research.knowledge.dedup import build_dedup_index
from ivd_research.knowledge.fact_extractor import extract_metric_facts
from ivd_research.knowledge.topic_index import build_topic_index


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        path.unlink()
    for row in rows:
        append_jsonl(path, row)


def build_metric_facts(task_dir: Path) -> list[MetricFact]:
    materials = list(read_jsonl(task_dir / "data" / "materials.jsonl"))
    cards = list(read_jsonl(task_dir / "data" / "evidence_cards.jsonl"))
    material_map = {item.get("material_id"): item for item in materials}
    facts: list[MetricFact] = []
    for card in cards:
        material = material_map.get(card.get("material_id"), {})
        if not material:
            continue
        excerpt_text = " ".join(
            str(excerpt.get("text") or "")
            for excerpt in card.get("key_excerpts") or []
            if isinstance(excerpt, dict)
        )
        extracted = extract_metric_facts(
            material,
            evidence_card_id=str(card.get("evidence_card_id") or ""),
            excerpt=excerpt_text or str(card.get("exact_data") or ""),
        )
        for index, fact in enumerate(extracted, start=1):
            fact.metric_fact_id = f"MF-{len(facts) + index:06d}"
        facts.extend(extracted)
    _write_jsonl(
        task_dir / "knowledge" / "metric_facts.jsonl",
        [fact.model_dump(mode="json") for fact in facts],
    )
    return facts


def build_relations(materials: list[dict[str, Any]], topic_index: dict[str, Any], dedup_index: dict[str, list[str]]) -> list[EvidenceRelation]:
    relations: list[EvidenceRelation] = []
    seen: set[tuple[str, str, str]] = set()
    for key, ids in dedup_index.items():
        for left in ids:
            for right in ids:
                if left >= right:
                    continue
                item = (left, right, "duplicate_candidate")
                if item not in seen:
                    seen.add(item)
                    relations.append(EvidenceRelation(source_id=left, target_id=right, relation_type="duplicate_candidate", weight=0.9, evidence=key))
    for topic_type, values in topic_index.items():
        for topic, ids in values.items():
            if len(ids) < 2:
                continue
            for left in ids:
                for right in ids:
                    if left >= right:
                        continue
                    relation_type = {
                        "marker": "shares_marker",
                        "sample": "shares_sample",
                        "reference": "shares_reference",
                        "platform": "compares_platform",
                    }.get(topic_type, "shares_topic")
                    item = (left, right, relation_type)
                    if item in seen:
                        continue
                    seen.add(item)
                    relations.append(EvidenceRelation(source_id=left, target_id=right, relation_type=relation_type, weight=0.4, evidence=f"{topic_type}:{topic}"))
    return relations


def build_literature_knowledge(task_dir: Path) -> dict[str, Any]:
    task_dir = Path(task_dir)
    materials = list(read_jsonl(task_dir / "data" / "materials.jsonl"))
    cards = list(read_jsonl(task_dir / "data" / "evidence_cards.jsonl"))
    knowledge_dir = task_dir / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    metric_facts = build_metric_facts(task_dir)
    dedup_index = build_dedup_index(materials)
    topic_index = build_topic_index(materials, cards)
    relations = build_relations(materials, topic_index, dedup_index)
    write_json(knowledge_dir / "dedup_index.json", {"duplicate_candidates": dedup_index})
    write_json(knowledge_dir / "topic_index.json", {"topics": topic_index})
    write_json(
        knowledge_dir / "literature_graph.json",
        {
            "nodes": [
                {
                    "id": item.get("material_id"),
                    "title": item.get("title"),
                    "material_type": item.get("material_type"),
                    "source_scenario": item.get("source_scenario"),
                }
                for item in materials
                if item.get("material_id")
            ],
            "relations": [relation.model_dump(mode="json") for relation in relations],
        },
    )
    summary = [
        "# 文献关系与指标事实摘要",
        "",
        f"- 材料节点：{len(materials)}",
        f"- 指标事实：{len(metric_facts)}",
        f"- 候选重复键：{len(dedup_index)}",
        f"- 关系边：{len(relations)}",
    ]
    (knowledge_dir / "relation_summary.md").write_text("\n".join(summary), encoding="utf-8")
    return {
        "metric_fact_count": len(metric_facts),
        "duplicate_key_count": len(dedup_index),
        "relation_count": len(relations),
        "knowledge_dir": str(knowledge_dir),
    }

