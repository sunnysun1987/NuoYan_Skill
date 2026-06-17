from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .jsonl import append_jsonl, read_json, read_jsonl
from .models import EvidenceCard
from .translation import parameter_lines


SECTION_BY_MATERIAL_TYPE = {
    "regulatory": "出口与注册",
    "competitor": "竞争格局",
    "standard": "指南与共识",
    "patent": "技术可行性",
    "literature": "临床意义",
    "local_import": "其他发现 / 待归类线索",
}


def material_ids(task_dir: Path) -> set[str]:
    return {
        row["material_id"]
        for row in read_jsonl(task_dir / "data" / "materials.jsonl")
        if "material_id" in row
    }


def committed_evidence_ids(task_dir: Path) -> set[str]:
    return {
        row["evidence_card_id"]
        for row in read_jsonl(task_dir / "data" / "evidence_cards.jsonl")
        if "evidence_card_id" in row
    }


def next_evidence_card_id(task_dir: Path) -> str:
    existing = committed_evidence_ids(task_dir)
    staged = {
        path.stem
        for path in (task_dir / "staging" / "evidence_cards").glob("EC-*.json")
    }
    return f"EC-{len(existing | staged) + 1:06d}"


def _read_extracted_excerpt(task_dir: Path, material: dict[str, Any]) -> tuple[str, str]:
    relative = material.get("extracted_text_path") or ""
    if not relative:
        return "", ""
    path = task_dir / relative
    if not path.exists():
        return "", relative
    text = path.read_text(encoding="utf-8", errors="ignore")
    excerpt = " ".join(text.split())
    return excerpt[:800], relative


def _raw_field_excerpt(material: dict[str, Any]) -> tuple[str, str]:
    raw = material.get("raw_fields") or {}
    for key in ["abstract", "summary", "full_visible_text", "detail_text", "citation"]:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:800], f"raw_fields.{key}"
    compact = {
        key: value
        for key, value in raw.items()
        if value not in ("", None, [], {})
    }
    if compact:
        return str(compact)[:800], "raw_fields"
    return "", ""


def _identifier(material: dict[str, Any]) -> str:
    raw = material.get("raw_fields") or {}
    for key in [
        "pmid",
        "pmcid",
        "doi",
        "registration_certificate_number",
        "standard_no",
        "standard_number",
        "publication_number",
        "patent_number",
    ]:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _source_type(material: dict[str, Any]) -> str:
    return material.get("source_scenario") or material.get("material_type") or "unknown"


def _taxonomy_tag(material: dict[str, Any]) -> str:
    return SECTION_BY_MATERIAL_TYPE.get(
        material.get("material_type", ""),
        SECTION_BY_MATERIAL_TYPE.get(material.get("source_scenario", ""), "其他发现 / 待归类线索"),
    )


def _field_text(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value in ("", None, [], {}):
            continue
        if isinstance(value, list):
            return "；".join(str(item).strip() for item in value if str(item).strip())
        return " ".join(str(value).split())
    return ""


def _structured_abstract_lines(raw: dict[str, Any]) -> list[str]:
    sections = raw.get("abstract_sections") or []
    lines: list[str] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            label = str(section.get("label") or "").strip() or "Abstract"
            text = " ".join(str(section.get("text") or "").split())
            if text:
                lines.append(f"Abstract[{label}]：{text}")
    elif isinstance(sections, dict):
        for label, value in sections.items():
            text = " ".join(str(value or "").split())
            if text:
                lines.append(f"Abstract[{label or 'Abstract'}]：{text}")
    if not lines:
        abstract = " ".join(str(raw.get("abstract") or raw.get("summary") or "").split())
        if abstract:
            lines.append(f"Abstract：{abstract}")
    keywords = raw.get("keywords") or []
    if isinstance(keywords, list):
        keyword_text = "；".join(str(item).strip() for item in keywords if str(item).strip())
    else:
        keyword_text = str(keywords or "").strip()
    if keyword_text:
        lines.append(f"Keywords：{keyword_text}")
    return lines


def _append_fact(facts: list[str], label: str, value: str) -> None:
    if value:
        facts.append(f"{label}：{value}")


def _draft_review_facts(
    material: dict[str, Any],
    excerpt: str,
    *,
    task_dir: Path | None = None,
) -> list[str]:
    raw = material.get("raw_fields") or {}
    facts: list[str] = []
    material_type = material.get("material_type", "unknown")

    if material_type == "standard":
        _append_fact(facts, "标准号", _field_text(raw, "standard_no", "standard_number"))
        _append_fact(facts, "标准状态", _field_text(raw, "status", "current_zh"))
        _append_fact(facts, "发布日期", _field_text(raw, "publish_date", "publication_date"))
        _append_fact(facts, "实施日期", _field_text(raw, "implementation_date"))
    elif material_type == "competitor":
        _append_fact(facts, "注册证编号", _field_text(raw, "registration_certificate_number"))
        _append_fact(facts, "注册人", _field_text(raw, "registrant"))
        _append_fact(facts, "方法学", _field_text(raw, "methodology"))
        _append_fact(facts, "适用范围", _field_text(raw, "scope"))
    elif material_type == "literature":
        _append_fact(facts, "PMID", _field_text(raw, "pmid"))
        _append_fact(facts, "PMCID", _field_text(raw, "pmcid"))
        _append_fact(facts, "DOI", _field_text(raw, "doi"))
        _append_fact(facts, "期刊", _field_text(raw, "journal", "journal_iso"))
        _append_fact(facts, "出版日期", _field_text(raw, "publication_date", "publish_date"))
        _append_fact(facts, "全文状态", _field_text(raw, "fulltext_status", "xml_status"))
        _append_fact(facts, "PDF状态", _field_text(raw, "pdf_status"))
        facts.extend(_structured_abstract_lines(raw))
    elif material_type == "patent":
        _append_fact(facts, "公开号", _field_text(raw, "publication_number", "patent_number"))
        _append_fact(facts, "基本信息", _field_text(raw, "basic_info_text"))
        _append_fact(facts, "PDF限制", _field_text(raw, "pdf_restriction_zh", "pdf_status"))

    if excerpt:
        facts.append(f"摘录线索：{excerpt[:240]}")
        for line in parameter_lines(excerpt):
            facts.append(f"摘录参数：{line}")
    return facts


def _publication_or_issue_date(material: dict[str, Any]) -> str:
    raw = material.get("raw_fields") or {}
    return _field_text(raw, "publication_date", "publish_date", "approval_date")


def build_draft_evidence_card(
    task_dir: Path,
    material: dict[str, Any],
    evidence_card_id: str,
) -> EvidenceCard:
    excerpt, source_path = _read_extracted_excerpt(task_dir, material)
    location = "extracted_text:1" if excerpt else ""
    if not excerpt:
        excerpt, location = _raw_field_excerpt(material)
        source_path = material.get("content_snapshot_path", "")
    if not excerpt:
        excerpt = material.get("source_url") or material.get("title", "")
        location = "source_url" if material.get("source_url") else "title"

    title = material.get("title") or material.get("material_id", "")
    material_type = material.get("material_type", "unknown")
    source_location = source_path or location or "material_record"
    review_facts = _draft_review_facts(material, excerpt, task_dir=task_dir)
    summary_detail = "；".join(review_facts[:4])
    summary = f"自动草稿证据卡：{title}"
    if summary_detail:
        summary = f"{summary}。{summary_detail}"
    summary = f"{summary}。该卡基于已采集材料生成，需研发人员复核后使用。"
    taxonomy_tag = _taxonomy_tag(material)
    exact_data = "\n".join([*review_facts, f"原文摘录：{excerpt}"] if excerpt else review_facts)

    return EvidenceCard(
        evidence_card_id=evidence_card_id,
        material_id=material["material_id"],
        material_type=material_type,
        title=title,
        source_type=_source_type(material),
        source_quality="自动草稿，未人工复核",
        publication_or_issue_date=_publication_or_issue_date(material),
        identifier=_identifier(material),
        summary=summary,
        tr1_file=material.get("extracted_text_path") or material.get("content_snapshot_path", ""),
        primary_tag=taxonomy_tag,
        secondary_tag="待人工归类",
        evidence_conclusion=summary,
        exact_data=exact_data or excerpt,
        source_location=source_location,
        original_excerpt_or_table_marker=location or "material_record",
        chinese_evidence_explanation="系统根据材料摘录生成低可信度草稿，必须人工复核。",
        key_facts=review_facts or [summary],
        key_excerpts=[
            {
                "text": excerpt,
                "location": location or "material_record",
                "source_path": source_path,
            }
        ],
        taxonomy_tags=[taxonomy_tag],
        evidence_strength="needs_review",
        confidence_level="待复核",
        include_in_report=False,
        report_usage="初稿线索，仅供复核",
        facts=review_facts or [summary],
        limitations=["自动生成，未人工复核；只能作为报告初稿线索。"],
        needs_review=True,
        review_reasons=["自动生成草稿，需人工确认相关性、标签和结论。"],
    )


def generate_draft_evidence_cards(task_dir: Path) -> dict:
    materials = list(read_jsonl(task_dir / "data" / "materials.jsonl"))
    existing_material_ids = {
        row.get("material_id")
        for row in read_jsonl(task_dir / "data" / "evidence_cards.jsonl")
    }
    generated = []
    for material in materials:
        if material.get("material_id") in existing_material_ids:
            continue
        card_id = next_evidence_card_id(task_dir)
        card = build_draft_evidence_card(task_dir, material, card_id)
        path = task_dir / "staging" / "evidence_cards" / f"{card.evidence_card_id}.json"
        from .jsonl import write_json

        write_json(path, card.model_dump(mode="json"))
        generated.append(str(path.relative_to(task_dir)))
        existing_material_ids.add(material.get("material_id"))

    commit = commit_staged_evidence(task_dir)
    return {
        "generated_count": len(generated),
        "generated": generated,
        "committed_count": commit["committed_count"],
        "validation": commit["validation"],
    }


def has_fact_source_support(card: EvidenceCard) -> bool:
    supported_by_excerpt = any(
        excerpt.text.strip() and excerpt.location.strip() != "location_unknown"
        for excerpt in card.key_excerpts
    )
    supported_by_source_fields = (
        bool(card.exact_data.strip())
        or bool(card.source_location.strip())
        or bool(card.original_excerpt_or_table_marker.strip())
    )
    return supported_by_excerpt or supported_by_source_fields


def validate_staged_evidence(task_dir: Path) -> dict:
    errors = []
    valid = []
    known_material_ids = material_ids(task_dir)
    for path in sorted((task_dir / "staging" / "evidence_cards").glob("*.json")):
        try:
            card = EvidenceCard.model_validate(read_json(path))
            if card.material_id not in known_material_ids:
                errors.append(
                    {
                        "file": path.name,
                        "error": f"Unknown material_id: {card.material_id}",
                    }
                )
            elif card.include_in_report and not card.key_excerpts:
                errors.append(
                    {
                        "file": path.name,
                        "error": "纳入报告的证据卡必须包含关键摘录。",
                    }
                )
            elif (
                card.include_in_report
                and (card.facts or card.key_facts)
                and not has_fact_source_support(card)
            ):
                errors.append(
                    {
                        "file": path.name,
                        "error": "Included facts require source support from key_excerpts or exact_data/source_location/original_excerpt_or_table_marker.",
                    }
                )
            else:
                valid.append(path.name)
        except ValidationError as exc:
            errors.append({"file": path.name, "error": str(exc)})
    return {"ok": not errors, "valid": valid, "errors": errors}


def commit_staged_evidence(task_dir: Path) -> dict:
    validation = validate_staged_evidence(task_dir)
    if not validation["ok"]:
        return {"committed_count": 0, "validation": validation}

    count = 0
    existing_ids = committed_evidence_ids(task_dir)
    for name in validation["valid"]:
        path = task_dir / "staging" / "evidence_cards" / name
        card = EvidenceCard.model_validate(read_json(path))
        if card.evidence_card_id in existing_ids:
            continue
        append_jsonl(
            task_dir / "data" / "evidence_cards.jsonl",
            card.model_dump(mode="json"),
        )
        export_evidence_card_files(task_dir, card.model_dump(mode="json"))
        existing_ids.add(card.evidence_card_id)
        count += 1
    return {"committed_count": count, "validation": validation}


def export_evidence_card_files(task_dir: Path, card: dict[str, Any]) -> None:
    card_id = card.get("evidence_card_id") or "EC-UNKNOWN"
    json_path = task_dir / "evidence_cards" / "json" / f"{card_id}.json"
    markdown_path = task_dir / "evidence_cards" / "markdown" / f"{card_id}.md"
    from .jsonl import write_json

    write_json(json_path, card)
    excerpts = card.get("key_excerpts") or []
    excerpt_lines = []
    for excerpt in excerpts:
        excerpt_lines.append(
            f"- {excerpt.get('text', '')}\n  - 位置：{excerpt.get('location', '')}\n  - 文件：{excerpt.get('source_path', '')}"
        )
    abstract_lines = [
        fact
        for fact in (card.get("key_facts") or card.get("facts") or [])
        if str(fact).startswith("Abstract")
        or str(fact).startswith("Keywords")
    ]
    parameter_lines_ = [
        fact
        for fact in (card.get("key_facts") or card.get("facts") or [])
        if str(fact).startswith("参数")
        or str(fact).startswith("摘录参数")
    ]
    section_prefixes = (
        "Abstract",
        "Keywords",
        "中文译文",
        "摘录中文译文",
        "参数",
        "摘录参数",
        "摘录线索",
    )
    general_fact_lines = [
        fact
        for fact in (card.get("key_facts") or card.get("facts") or [])
        if not str(fact).startswith(section_prefixes)
    ]
    markdown = "\n".join(
        [
            f"# {card.get('title', card_id)}",
            "",
            f"- 证据卡ID：{card_id}",
            f"- 材料ID：{card.get('material_id', '')}",
            f"- 材料类型：{card.get('material_type', '')}",
            f"- 证据强度：{card.get('evidence_strength', '')}",
            f"- 是否纳入报告：{'是' if card.get('include_in_report') else '否'}",
            f"- 标签：{'；'.join(card.get('taxonomy_tags') or [])}",
            "",
            "## 摘要",
            str(card.get("summary", "")),
            "",
            "## 结论",
            str(card.get("evidence_conclusion", "")),
            "",
            "## 关键事实",
            "\n".join(f"- {fact}" for fact in general_fact_lines) if general_fact_lines else "暂无独立关键事实。",
            "",
            "## 结构化 Abstract",
            "\n".join(f"- {line}" for line in abstract_lines) if abstract_lines else "未解析到结构化 Abstract。",
            "",
            "## 参数要点",
            "\n".join(f"- {line}" for line in parameter_lines_) if parameter_lines_ else "未识别到明确参数。",
            "",
            "## 关键摘录",
            "\n".join(excerpt_lines) if excerpt_lines else "暂无关键摘录。",
            "",
            "## 局限与复核原因",
            "\n".join(f"- {item}" for item in (card.get("limitations") or card.get("review_reasons") or [])),
            "",
        ]
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
