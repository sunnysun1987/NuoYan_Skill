from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .jsonl import read_json, read_jsonl, write_jsonl
from .models import EvidenceCard
from .translation import parameter_lines
from .knowledge.fact_extractor import extract_metric_facts
from .source_adapters.source_sites import get_source_site


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
        "openalex_id",
        "registration_certificate_number",
        "standard_no",
        "standard_number",
        "publication_number",
        "patent_number",
        "identifier",
        "nct_id",
        "uniprot_id",
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


def _source_site_id(material: dict[str, Any]) -> str:
    raw = material.get("raw_fields") or {}
    return (
        material.get("source_site_id")
        or raw.get("source_site_id")
        or material.get("source_scenario")
        or ""
    )


def _source_name(material: dict[str, Any]) -> str:
    raw = material.get("raw_fields") or {}
    source_site_id = _source_site_id(material)
    source_site = get_source_site(source_site_id) if source_site_id else None
    return (
        material.get("source_name")
        or raw.get("source_name")
        or (source_site.display_name if source_site else "")
        or material.get("source_scenario")
        or ""
    )


def _one_sentence_conclusion(title: str, facts: list[str]) -> str:
    for fact in facts:
        if fact.startswith("Abstract"):
            return f"{title} 提供文献摘要证据，需结合样本、平台和参照方法复核可用于的研发判断。"
    return f"{title} 已形成自动证据草稿，需人工确认相关性和报告用途。"


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
    metric_facts = extract_metric_facts(
        material,
        evidence_card_id=evidence_card_id,
        excerpt=excerpt,
    )
    for fact in metric_facts:
        review_facts.append(f"参数事实[{fact.metric_type}]：{fact.value}；原文：{fact.excerpt[:180]}")
    summary_detail = "；".join(review_facts[:4])
    summary = f"自动草稿证据卡：{title}"
    if summary_detail:
        summary = f"{summary}。{summary_detail}"
    summary = f"{summary}。该卡基于已采集材料生成，需研发人员复核后使用。"
    taxonomy_tag = _taxonomy_tag(material)
    exact_data = "\n".join([*review_facts, f"原文摘录：{excerpt}"] if excerpt else review_facts)
    raw = material.get("raw_fields") or {}
    source_site_id = _source_site_id(material)
    source_name = _source_name(material)
    fulltext_status = _field_text(raw, "fulltext_status", "xml_status") or material.get("extracted_text_status", "")
    permission_status = "受限" if material.get("failure_type") in {"permission_required", "needs_login"} else ""
    one_sentence = _one_sentence_conclusion(title, review_facts)

    return EvidenceCard(
        evidence_card_id=evidence_card_id,
        material_id=material["material_id"],
        material_type=material_type,
        title=title,
        source_type=_source_type(material),
        source_quality="自动草稿，未人工复核",
        source_site_id=source_site_id,
        source_name=source_name,
        source_input_trace={
            "source_site_id": source_site_id,
            "source_name": source_name,
            "source_url": material.get("source_url", ""),
            "search_keyword_or_query": material.get("search_keyword_or_query", ""),
            "collection_time": material.get("collection_time", ""),
        },
        publication_or_issue_date=_publication_or_issue_date(material),
        identifier=_identifier(material),
        summary=summary,
        tr1_file=material.get("extracted_text_path") or material.get("content_snapshot_path", ""),
        primary_tag=taxonomy_tag,
        secondary_tag="待人工归类",
        evidence_conclusion=summary,
        one_sentence_conclusion=one_sentence,
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
        metric_facts=[fact.model_dump(mode="json") for fact in metric_facts],
        disease=_field_text(raw, "disease", "condition"),
        biomarker_or_target=_field_text(raw, "biomarker", "target", "entity"),
        sample_type=_field_text(raw, "sample_type"),
        intended_use=_field_text(raw, "intended_use"),
        population=_field_text(raw, "population", "participants", "patients"),
        platform=_field_text(raw, "platform"),
        reference_standard=_field_text(raw, "reference_standard", "comparator"),
        research_stage="自动草稿",
        priority_level="B" if metric_facts or _identifier(material) else "C",
        card_status="draft_needs_review",
        fulltext_status=str(fulltext_status or ""),
        permission_status=permission_status,
        gap_tasks=[
            item
            for item in [
                "补充全文或 PDF" if fulltext_status in {"metadata_only", "parse_failed", "not_attempted"} else "",
                "复核权限受限来源" if permission_status else "",
                "人工确认指标事实" if metric_facts else "",
            ]
            if item
        ],
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

    commit = commit_staged_evidence(
        task_dir,
        staged_names={Path(path).name for path in generated},
    )
    return {
        "generated_count": len(generated),
        "generated": generated,
        "committed_count": commit["committed_count"],
        "added_count": commit["added_count"],
        "replaced_count": commit["replaced_count"],
        "deduplicated_count": commit["deduplicated_count"],
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


def validate_staged_evidence(
    task_dir: Path,
    *,
    staged_names: set[str] | None = None,
) -> dict:
    errors = []
    valid = []
    known_material_ids = material_ids(task_dir)
    existing_material_ids_by_card_id: dict[str, set[str]] = {}
    for row in read_jsonl(task_dir / "data" / "evidence_cards.jsonl"):
        card_id = str(row.get("evidence_card_id") or "")
        if not card_id:
            continue
        existing_material_ids_by_card_id.setdefault(card_id, set()).add(
            str(row.get("material_id") or "")
        )
    for card_id, linked_material_ids in existing_material_ids_by_card_id.items():
        if len(linked_material_ids) > 1:
            errors.append(
                {
                    "file": "data/evidence_cards.jsonl",
                    "error": (
                        f"Evidence card {card_id} is linked to different material_ids: "
                        f"{', '.join(sorted(linked_material_ids))}."
                    ),
                }
            )
    existing_material_by_card_id = {
        card_id: next(iter(linked_material_ids))
        for card_id, linked_material_ids in existing_material_ids_by_card_id.items()
        if len(linked_material_ids) == 1
    }
    staged_card_files: dict[str, str] = {}
    paths = sorted((task_dir / "staging" / "evidence_cards").glob("*.json"))
    if staged_names is not None:
        paths = [path for path in paths if path.name in staged_names]
    for path in paths:
        try:
            card = EvidenceCard.model_validate(read_json(path))
            card_errors = []
            if path.stem != card.evidence_card_id:
                card_errors.append(
                    f"Filename {path.name} must match evidence_card_id {card.evidence_card_id}.json"
                )
            previous_file = staged_card_files.get(card.evidence_card_id)
            if previous_file:
                card_errors.append(
                    f"Duplicate staged evidence_card_id {card.evidence_card_id}: "
                    f"{previous_file}, {path.name}"
                )
            else:
                staged_card_files[card.evidence_card_id] = path.name
            if card.material_id not in known_material_ids:
                card_errors.append(f"Unknown material_id: {card.material_id}")
            existing_material_id = existing_material_by_card_id.get(card.evidence_card_id)
            if existing_material_id and existing_material_id != card.material_id:
                card_errors.append(
                    f"Evidence card {card.evidence_card_id} cannot replace material_id "
                    f"{existing_material_id} with {card.material_id}."
                )
            if card.include_in_report and not card.key_excerpts:
                card_errors.append("纳入报告的证据卡必须包含关键摘录。")
            if (
                card.include_in_report
                and (card.facts or card.key_facts)
                and not has_fact_source_support(card)
            ):
                card_errors.append(
                    "Included facts require source support from key_excerpts or "
                    "exact_data/source_location/original_excerpt_or_table_marker."
                )
            if card_errors:
                errors.extend(
                    {"file": path.name, "error": message}
                    for message in card_errors
                )
            else:
                valid.append(path.name)
        except ValidationError as exc:
            errors.append({"file": path.name, "error": str(exc)})
    return {"ok": not errors, "valid": valid, "errors": errors}


def commit_staged_evidence(
    task_dir: Path,
    *,
    staged_names: set[str] | None = None,
) -> dict:
    validation = validate_staged_evidence(task_dir, staged_names=staged_names)
    if not validation["ok"]:
        return {
            "committed_count": 0,
            "added_count": 0,
            "replaced_count": 0,
            "deduplicated_count": 0,
            "validation": validation,
        }

    evidence_path = task_dir / "data" / "evidence_cards.jsonl"
    rows: list[dict[str, Any]] = []
    row_indexes: dict[str, int] = {}
    deduplicated_cards: dict[str, dict[str, Any]] = {}
    deduplicated_count = 0
    for row in read_jsonl(evidence_path):
        card_id = str(row.get("evidence_card_id") or "")
        if card_id and card_id in row_indexes:
            rows[row_indexes[card_id]] = row
            deduplicated_cards[card_id] = row
            deduplicated_count += 1
            continue
        if card_id:
            row_indexes[card_id] = len(rows)
        rows.append(row)
    committed_cards: list[dict[str, Any]] = []
    added_count = 0
    replaced_count = 0
    for name in validation["valid"]:
        path = task_dir / "staging" / "evidence_cards" / name
        card = EvidenceCard.model_validate(read_json(path))
        payload = card.model_dump(mode="json")
        if card.evidence_card_id in row_indexes:
            rows[row_indexes[card.evidence_card_id]] = payload
            replaced_count += 1
        else:
            row_indexes[card.evidence_card_id] = len(rows)
            rows.append(payload)
            added_count += 1
        committed_cards.append(payload)

    if committed_cards or deduplicated_count:
        write_jsonl(evidence_path, rows)
        export_cards = dict(deduplicated_cards)
        export_cards.update(
            {
                str(card.get("evidence_card_id") or ""): card
                for card in committed_cards
            }
        )
        for card in export_cards.values():
            export_evidence_card_files(task_dir, card)

    return {
        "committed_count": len(committed_cards),
        "added_count": added_count,
        "replaced_count": replaced_count,
        "deduplicated_count": deduplicated_count,
        "validation": validation,
    }


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
        or str(fact).startswith("参数事实")
    ]
    metric_lines = [
        f"{fact.get('metric_type', '')}：{fact.get('value', '')}；{fact.get('excerpt', '')[:220]}"
        for fact in card.get("metric_facts", [])
        if isinstance(fact, dict)
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
            f"- 信源：{card.get('source_name', '') or card.get('source_site_id', '')}",
            f"- 来源链接：{(card.get('source_input_trace') or {}).get('source_url', '')}",
            f"- 研发优先级：{card.get('priority_level', '')}",
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
            "\n".join(f"- {line}" for line in (metric_lines + parameter_lines_)) if (metric_lines or parameter_lines_) else "未识别到明确参数。",
            "",
            "## 研发定位",
            "\n".join(
                f"- {label}：{value}"
                for label, value in [
                    ("疾病/适应症", card.get("disease", "")),
                    ("标志物/靶标", card.get("biomarker_or_target", "")),
                    ("样本类型", card.get("sample_type", "")),
                    ("预期用途", card.get("intended_use", "")),
                    ("平台/方法学", card.get("platform", "")),
                    ("参照方法", card.get("reference_standard", "")),
                ]
                if value
            )
            or "待人工补充。",
            "",
            "## 关键摘录",
            "\n".join(excerpt_lines) if excerpt_lines else "暂无关键摘录。",
            "",
            "## 局限与复核原因",
            "\n".join(f"- {item}" for item in (card.get("limitations") or card.get("review_reasons") or [])),
            "",
            "## 补证任务",
            "\n".join(f"- {item}" for item in (card.get("gap_tasks") or [])) or "暂无自动补证任务。",
            "",
        ]
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
