from pathlib import Path

from .jsonl import append_jsonl, read_json, read_jsonl, write_json


def create_analysis_requests(task_dir: Path) -> dict:
    materials = list(read_jsonl(task_dir / "data" / "materials.jsonl"))
    created = []
    for index, material in enumerate(materials, start=1):
        request = {
            "request_id": f"AR-{index:06d}",
            "target_type": "evidence_card",
            "material_id": material["material_id"],
            "material_type": material.get("material_type", "unknown"),
            "title": material.get("title", ""),
            "source_url": material.get("source_url", ""),
            "extracted_text_path": material.get("extracted_text_path", ""),
            "instructions_zh": (
                "请基于材料完整内容生成结构化证据卡 JSON。"
                "事实必须有摘录、字段或文件来源；不能把推断写成事实。"
            ),
        }
        path = task_dir / "staging" / "analysis_requests" / f"{request['request_id']}.json"
        write_json(path, request)
        created.append(str(path.relative_to(task_dir)))
    report_request = {
        "request_id": "AR-REPORT-000001",
        "target_type": "report_sections",
        "input_files": [
            "data/materials.jsonl",
            "data/evidence_cards.jsonl",
        ],
        "output_dir": "staging/report_sections",
        "instructions_zh": (
            "请作为 IVD 研发立项可行性分析助手，基于已采集材料全文、题录、原始字段和证据卡生成报告章节 JSON。"
            "不要编造未在材料中出现的事实；每个事实和判断必须列出 supporting_evidence_refs。"
            "没有充分证据的章节必须写明证据缺口，不得写成确定结论。"
            "每个 supporting_evidence_ref 必须包含三个字段，全部必填："
            "material_id（引用材料的ID，如 MAT-000001）、"
            "evidence_card_id（证据卡ID，如 EC-000001）、"
            "excerpt（关键摘录文本，从材料原文或证据卡key_excerpts中取，20-100字）。"
            "每个章节输出一个 JSON 文件，所有字段必须填写，不得省略："
            "section_id、section_title、facts、analysis、evidence_gaps、"
            "evidence_strength_summary（必须基于支撑证据的数量和质量给出 strong/moderate/weak/gap 判断）、"
            "confidence_level（高/中/低）、supporting_evidence_refs、needs_human_review。"
        ),
        "required_sections": [
            "临床意义",
            "临床应用定位",
            "目标使用场景",
            "目标人群",
            "诊疗路径",
            "金标准与参照方法",
            "指南与共识",
            "专家和组织意见",
            "市场准入与收费",
            "市场定位",
            "竞争格局",
            "出口与注册",
            "技术可行性",
            "参考物质",
            "安全要求",
            "原材料可获得性",
            "其他发现 / 待归类线索",
        ],
    }
    report_path = task_dir / "staging" / "analysis_requests" / "AR-REPORT-000001.json"
    write_json(report_path, report_request)
    created.append(str(report_path.relative_to(task_dir)))
    return {"created_count": len(created), "requests": created}


def _known_evidence_ids(task_dir: Path) -> set[str]:
    return {
        row["evidence_card_id"]
        for row in read_jsonl(task_dir / "data" / "evidence_cards.jsonl")
        if row.get("evidence_card_id")
    }


def _known_material_ids(task_dir: Path) -> set[str]:
    return {
        row["material_id"]
        for row in read_jsonl(task_dir / "data" / "materials.jsonl")
        if row.get("material_id")
    }


def validate_staged_report_sections(task_dir: Path) -> dict:
    errors = []
    valid = []
    material_ids = _known_material_ids(task_dir)
    evidence_ids = _known_evidence_ids(task_dir)
    for path in sorted((task_dir / "staging" / "report_sections").glob("*.json")):
        section = read_json(path)
        section_id = str(section.get("section_id") or "").strip()
        section_title = str(section.get("section_title") or "").strip()
        analysis = str(section.get("analysis") or "").strip()
        refs = section.get("supporting_evidence_refs") or []
        if not section_id:
            errors.append({"file": path.name, "error": "Missing section_id."})
            continue
        if not section_title:
            errors.append({"file": path.name, "error": "Missing section_title."})
            continue
        if not analysis:
            errors.append({"file": path.name, "error": "Missing analysis."})
            continue
        strength = str(section.get("evidence_strength_summary") or "").strip()
        if strength not in {"strong", "moderate", "weak", "gap"}:
            errors.append(
                {
                    "file": path.name,
                    "error": (
                        "evidence_strength_summary must be one of strong/moderate/weak/gap, "
                        f"got '{strength}'."
                    ),
                }
            )
            continue
        if not isinstance(refs, list):
            errors.append({"file": path.name, "error": "supporting_evidence_refs must be a list."})
            continue
        unsupported_refs = []
        missing_fields = []
        for ref in refs:
            if not isinstance(ref, dict):
                unsupported_refs.append(str(ref))
                continue
            material_id = ref.get("material_id")
            evidence_card_id = ref.get("evidence_card_id")
            excerpt = ref.get("excerpt")
            if not material_id:
                missing_fields.append(f"{ref.get('evidence_card_id','?')}: 缺少 material_id")
            elif material_id not in material_ids:
                unsupported_refs.append(str(material_id))
            if not evidence_card_id:
                missing_fields.append(f"{ref.get('material_id','?')}: 缺少 evidence_card_id")
            elif evidence_card_id not in evidence_ids:
                unsupported_refs.append(str(evidence_card_id))
            if not excerpt:
                missing_fields.append(
                    f"{evidence_card_id or material_id or '?'}: 缺少 excerpt"
                )
        if missing_fields:
            errors.append(
                {
                    "file": path.name,
                    "error": "supporting_evidence_ref 字段不完整: " + "; ".join(missing_fields),
                }
            )
            continue
        if unsupported_refs:
            errors.append(
                {
                    "file": path.name,
                    "error": "Unknown supporting evidence refs: " + ", ".join(unsupported_refs),
                }
            )
            continue
        if not refs and not section.get("evidence_gaps"):
            errors.append(
                {
                    "file": path.name,
                    "error": "Sections without supporting evidence must explain evidence_gaps.",
                }
            )
            continue
        valid.append(path.name)
    return {"ok": not errors, "valid": valid, "errors": errors}


def commit_staged_report_sections(task_dir: Path) -> dict:
    validation = validate_staged_report_sections(task_dir)
    if not validation["ok"]:
        return {"committed_count": 0, "validation": validation}

    target = task_dir / "data" / "report_sections.jsonl"
    existing = {
        row.get("section_id"): row
        for row in read_jsonl(target)
        if row.get("section_id")
    }
    committed = 0
    for name in validation["valid"]:
        section = read_json(task_dir / "staging" / "report_sections" / name)
        section_id = section["section_id"]
        if existing.get(section_id) == section:
            continue
        existing[section_id] = section
        committed += 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")
    for row in existing.values():
        append_jsonl(target, row)
    return {"committed_count": committed, "validation": validation}
