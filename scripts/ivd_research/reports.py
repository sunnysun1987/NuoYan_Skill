from pathlib import Path
import re
from typing import Any
from datetime import date

from jinja2 import Template

from .jsonl import append_jsonl, read_json, read_jsonl
from .quality import build_collection_alerts
from .status import now_iso
from .translation import extract_parameters


REPORT_SECTIONS = [
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
]

SOURCE_DISPLAY_LIMIT = 100
CURRENT_REPORT_DATE = date.today()
STATUS_LABELS = {
    "completed": "completed / 已完成",
    "collection_failed": "collection_failed / 采集失败",
    "needs_login": "needs_login / 需要登录",
    "permission_required": "permission_required / 权限受限",
    "needs_manual_review": "needs_manual_review / 需人工复核",
    "not_started": "not_started / 未启动",
    "no_results": "no_results / 未发现结果",
    "deferred": "deferred / 暂缓",
    "draft": "draft / 草稿",
}


def report_display_title(topic: str) -> str:
    title = str(topic or "").strip() or "项目"
    suffix_replacements = [
        ("立项可行性全量验证调研", "调研分析综述"),
        ("立项可行性调研", "调研分析综述"),
        ("可行性全量验证调研", "调研分析综述"),
        ("可行性调研", "调研分析综述"),
        ("立项调研", "调研分析综述"),
        ("调研", "调研分析综述"),
    ]
    for suffix, replacement in suffix_replacements:
        if title.endswith(suffix):
            return f"{title[:-len(suffix)]}{replacement}"
    if title.endswith("综述"):
        return title
    return f"{title}调研分析综述"


def asset_root() -> Path:
    return Path(__file__).resolve().parents[2] / "assets"


def local_path(material: dict) -> str:
    if material.get("download_files"):
        return material["download_files"][0].get("relative_path", "")
    return material.get("collection_path", {}).get("stored_file", "")


def _first_raw(raw: dict, *keys: str) -> str:
    for key in keys:
        value = raw.get(key, "")
        if isinstance(value, list):
            value = "；".join(str(item) for item in value if str(item).strip())
        value = str(value or "").strip()
        if value:
            return value
    return ""


def _extract_identifier_from_text(text: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}[：:]\s*([A-Za-z0-9./_\-]+)", str(text or ""))
    return match.group(1).strip() if match else ""


def _clean_identifier(value: str, kind: str) -> str:
    value = str(value or "").strip().strip("；;,.")
    if not value or value.upper() in {"PMID", "PMCID", "DOI", "NONE", "NULL"}:
        return ""
    if kind == "pmid":
        match = re.search(r"\d{6,10}", value)
        return match.group(0) if match else ""
    if kind == "pmcid":
        match = re.search(r"PMC\d+", value, re.IGNORECASE)
        return match.group(0).upper() if match else ""
    if kind == "doi":
        match = re.search(r"10\.\S+", value)
        return match.group(0).strip("；;,.") if match else ""
    return value


def _date_sort_value(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.search(r"(\d{4})(?:[-/ ]([A-Za-z]{3,9}|\d{1,2}))?(?:[-/ ](\d{1,2}))?", raw)
    if not match:
        return raw
    year = int(match.group(1))
    month_text = match.group(2) or "1"
    month_names = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = month_names.get(month_text[:3].lower(), None) if month_text.isalpha() else int(month_text)
    day = int(match.group(3) or 1)
    return f"{year:04d}-{month:02d}-{day:02d}"


def _display_publication_date(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = _date_sort_value(raw)
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", normalized)
    if not match:
        return raw
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    is_month_only = bool(re.fullmatch(r"\d{4}[-/]\d{1,2}", raw))
    is_future = date(year, month, day) > CURRENT_REPORT_DATE
    if is_future:
        if is_month_only:
            return f"{year:04d}-{month:02d}（待核验，来源返回未来刊期）"
        return f"{year:04d}-{month:02d}-{day:02d}（待核验，来源返回未来日期）"
    if is_month_only:
        return f"{year:04d}-{month:02d}"
    return raw


def _clean_summary_text(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    lines = []
    skip_prefixes = (
        "来源：",
        "PMID：",
        "PMCID：",
        "DOI：",
        "期刊：",
        "发表日期：",
        "检索口径：",
        "OpenAlex ID：",
        "原始接口文件：",
        "业务相关性：",
        "历史任务路径：",
        "历史材料ID：",
        "历史来源场景：",
        "原始来源URL：",
        "复用边界：",
    )
    capture = False
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in {"摘要：", "摘要/结构化摘要：", "全文片段："}:
            capture = True
            continue
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        if capture or len(line) > 18:
            lines.append(line)
    result = " ".join(lines).strip() or cleaned
    return result[:900]


def _structured_abstract_items(raw: dict[str, Any]) -> list[dict[str, str]]:
    sections = raw.get("abstract_sections") or []
    items: list[dict[str, str]] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            label = str(section.get("label") or "").strip() or "Abstract"
            text = " ".join(str(section.get("text") or "").split())
            if text:
                items.append({"label": label, "text": text})
    if not items:
        abstract = " ".join(str(raw.get("abstract") or raw.get("summary") or "").split())
        if abstract:
            items.append({"label": "Abstract", "text": abstract})
    return items


def _structured_abstract_text(raw: dict[str, Any], *, max_chars: int = 1800) -> str:
    lines = [f"{item['label']}: {item['text']}" for item in _structured_abstract_items(raw)]
    keywords = raw.get("keywords") or []
    if isinstance(keywords, list):
        keyword_text = "；".join(str(item).strip() for item in keywords if str(item).strip())
    else:
        keyword_text = str(keywords or "").strip()
    if keyword_text:
        lines.append(f"Keywords: {keyword_text}")
    text = "\n".join(lines).strip()
    return text[:max_chars]


def _source_record_limit(materials: list[dict]) -> list[dict]:
    grouped: dict[str, int] = {}
    limited = []
    for item in materials:
        source = str(item.get("source_scenario") or "")
        grouped[source] = grouped.get(source, 0) + 1
        if grouped[source] <= SOURCE_DISPLAY_LIMIT:
            limited.append(item)
    return limited


def evidence_by_material(evidence_cards: list[dict]) -> dict[str, list[dict]]:
    grouped = {}
    for card in evidence_cards:
        grouped.setdefault(card.get("material_id", ""), []).append(card)
    return grouped


def normalize_materials(
    materials: list[dict],
    evidence_cards: list[dict] | None = None,
    *,
    task_dir: Path | None = None,
) -> list[dict]:
    from .constants import EVIDENCE_STRENGTH_LABELS, MATERIAL_TYPE_LABELS
    from .scenarios.registry import all_scenarios

    _scenario_labels = {s.scenario_id: s.label_zh for s in all_scenarios()}
    evidence = evidence_by_material(evidence_cards or [])
    normalized = []
    for material in materials:
        row = dict(material)
        row["raw_fields"] = row.get("raw_fields") or {}
        material_cards = evidence.get(material.get("material_id", ""), [])
        row["local_path"] = local_path(material)
        raw = row["raw_fields"]
        text_blob = " ".join(
            str(value or "")
            for value in [
                row.get("title", ""),
                raw.get("summary", ""),
                raw.get("abstract", ""),
                raw.get("identifier", ""),
            ]
        )
        row["pmid"] = _clean_identifier(
            _first_raw(raw, "pmid", "PMID") or _extract_identifier_from_text(text_blob, "PMID"),
            "pmid",
        )
        row["pmcid"] = _clean_identifier(
            _first_raw(raw, "pmcid", "PMCID") or _extract_identifier_from_text(text_blob, "PMCID"),
            "pmcid",
        )
        row["doi"] = _clean_identifier(
            _first_raw(raw, "doi", "DOI") or _extract_identifier_from_text(text_blob, "DOI"),
            "doi",
        )
        row["publication_date"] = _first_raw(raw, "publication_date", "publication_year") or row.get("publication_date", "")
        row["publication_date_display"] = _display_publication_date(row["publication_date"])
        row["publication_sort_date"] = _date_sort_value(row["publication_date"])
        row["display_year"] = str(row.get("publication_date") or "")[:4]
        row["journal"] = _first_raw(raw, "journal", "source", "source_display_name")
        row["has_download"] = bool(row.get("download_files")) or row.get("download_status") in {"downloaded", "linked_snapshot"}
        if row.get("download_files"):
            row["download_status_zh"] = "已下载原文/PDF，见追溯目录 02_下载原文与网页快照_downloads"
        elif row.get("extracted_text_path"):
            row["download_status_zh"] = "已保存文本/快照，见追溯目录 03_全文抽取文本_extracted_text"
        else:
            row["download_status_zh"] = "未下载，仅保留题录/摘要/链接"
        row["display_url"] = (
            row.get("source_url")
            or _first_raw(raw, "pubmed_url", "pmc_url", "pdf_url", "url", "landing_page_url", "oa_url")
            or (f"https://doi.org/{row['doi']}" if row.get("doi") else "")
        )
        # Chinese display labels
        row["material_type_zh"] = MATERIAL_TYPE_LABELS.get(
            row.get("material_type", ""), row.get("material_type", "")
        )
        row["source_scenario_zh"] = _scenario_labels.get(
            row.get("source_scenario", ""), row.get("source_scenario", "")
        )
        row["taxonomy_tags"] = sorted(
            {
                tag
                for card in material_cards
                for tag in (card.get("taxonomy_tags") or [])
            }
        )
        row["evidence_strengths"] = sorted(
            {card.get("evidence_strength", "needs_review") for card in material_cards}
        )
        row["include_in_report"] = any(card.get("include_in_report") for card in material_cards)
        row["evidence_summaries"] = [
            card.get("summary", "") for card in material_cards if card.get("summary")
        ]
        row["abstract_sections_display"] = _structured_abstract_items(raw)
        row["abstract_sections_translated"] = []
        row["structured_abstract"] = _structured_abstract_text(raw)
        row["structured_summary"] = (
            row["structured_abstract"]
            or _clean_summary_text(
                _first_raw(raw, "abstract", "summary", "content")
                or " ".join(row.get("evidence_summaries") or [])
            )
        )
        display_text = row["structured_summary"] or _first_raw(raw, "scope", "basic_info_text", "full_visible_text")
        row["summary_translation_zh"] = ""
        row["summary_translation_status"] = "not_configured" if display_text else "not_needed"
        row["parameter_items"] = extract_parameters(display_text)
        row["status_text"] = " ".join(
            str(value or "")
            for value in [
                material.get("download_status", ""),
                material.get("extracted_text_status", ""),
                material.get("failure_type", ""),
                material.get("failure_reason", ""),
            ]
        ).strip()
        normalized.append(row)
    return normalized


def clean_report_text(text: str) -> str:
    cleaned = str(text or "")
    cleaned = cleaned.replace(" 专利标题（英）：", "；英文标题：")
    return cleaned


def clean_evidence_summary(text: str) -> str:
    cleaned = clean_report_text(text)
    cleaned = cleaned.replace("自动草稿证据卡：", "")
    cleaned = re.sub(r"PMID[：:]\s*[A-Za-z0-9./_\-]+[；;]?", "", cleaned)
    cleaned = re.sub(r"PMCID[：:]\s*[A-Za-z0-9./_\-]+[；;]?", "", cleaned)
    cleaned = re.sub(r"DOI[：:]\s*[A-Za-z0-9./_\-()]+[；;]?", "", cleaned)
    cleaned = re.sub(r"期刊[：:]\s*[^。；;]+[；;]?", "", cleaned)
    cleaned = re.sub(r"出版日期[：:]\s*[^。；;]+[；;]?", "", cleaned)
    cleaned = re.sub(r"发表日期[：:]\s*[^。；;]+[；;]?", "", cleaned)
    cleaned = re.sub(r"检索口径[：:]\s*[^。]+", "", cleaned)
    cleaned = cleaned.replace("该卡基于已采集材料生成，需研发人员复核后使用。", "")
    cleaned = cleaned.strip(" ；;。")
    return cleaned or "已采集材料线索，需复核后形成可引用结论。"


def is_section_fact(text: str) -> bool:
    value = str(text or "").strip()
    return value.startswith(
        (
            "Abstract[",
            "Keywords",
            "中文译文",
            "摘录中文译文",
            "参数",
            "摘录参数",
            "摘录线索",
        )
    )


def display_key_facts(items: list[str], summary: str) -> list[str]:
    facts: list[str] = []
    seen = set()
    low_value = {
        "已采集材料线索，需复核后形成可引用结论。",
        "已采集材料线索，需复核后形成可引用结论",
        "全文状态：completed",
        "全文状态: completed",
    }
    for item in items:
        if is_section_fact(item):
            continue
        fact = clean_evidence_summary(item)
        if not fact or fact in low_value:
            continue
        if fact == summary:
            continue
        if fact in seen:
            continue
        seen.add(fact)
        facts.append(fact)
    return facts[:6]


def normalize_evidence_cards(evidence_cards: list[dict]) -> list[dict]:
    from .constants import EVIDENCE_STRENGTH_LABELS, MATERIAL_TYPE_LABELS

    normalized = []
    for card in evidence_cards:
        row = dict(card)
        row["title"] = clean_display_title(row.get("title", ""))
        row["summary"] = clean_evidence_summary(row.get("summary", ""))
        row["key_excerpts"] = [
            {**excerpt, "text": clean_evidence_summary(excerpt.get("text", ""))}
            for excerpt in row.get("key_excerpts", [])
        ]
        row["key_facts"] = [
            clean_evidence_summary(item)
            for item in row.get("key_facts", [])
            if clean_evidence_summary(item)
        ]
        row["display_facts"] = display_key_facts(row["key_facts"], row["summary"])
        parameter_facts = [
            fact
            for fact in row["key_facts"]
            if fact.startswith("参数") or fact.startswith("摘录参数")
        ]
        row["translation_facts"] = []
        row["parameter_facts"] = parameter_facts[:10]
        # Map internal keys to Chinese display labels
        row["material_type_zh"] = MATERIAL_TYPE_LABELS.get(
            row.get("material_type", ""), row.get("material_type", "")
        )
        row["evidence_strength_zh"] = EVIDENCE_STRENGTH_LABELS.get(
            row.get("evidence_strength", ""), row.get("evidence_strength", "")
        )
        normalized.append(row)
    return normalized


def cards_by_section(
    evidence_cards: list[dict],
    *,
    include_only: bool = True,
) -> dict[str, list[dict]]:
    grouped = {section: [] for section in REPORT_SECTIONS}
    fallback = "其他发现 / 待归类线索"
    for card in evidence_cards:
        if include_only and not card.get("include_in_report"):
            continue
        tags = card.get("taxonomy_tags") or []
        target = next((tag for tag in tags if tag in grouped), fallback)
        grouped[target].append(card)
    return grouped


def report_sections_by_title(report_sections: list[dict]) -> dict[str, dict]:
    grouped = {}
    for section in report_sections:
        title = str(section.get("section_title") or "").strip()
        if title:
            grouped[title] = section
    return grouped


def normalize_report_sections(report_sections: list[dict]) -> list[dict]:
    normalized = []
    for section in report_sections:
        row = dict(section)
        row["facts"] = [clean_report_text(item) for item in row.get("facts", [])]
        row["analysis"] = clean_report_text(row.get("analysis", ""))
        row["evidence_gaps"] = [
            clean_report_text(item) for item in row.get("evidence_gaps", [])
        ]
        row["supporting_evidence_refs"] = row.get("supporting_evidence_refs", [])
        normalized.append(row)
    return normalized


def normalize_scenario_statuses(scenario_statuses: list[dict]) -> list[dict]:
    from .scenarios.registry import all_scenarios

    _label_map = {s.scenario_id: s.label_zh for s in all_scenarios()}
    normalized = []
    for scenario in scenario_statuses:
        row = dict(scenario)
        scenario_id = row.get("scenario_id", "")
        row["label_zh"] = _label_map.get(scenario_id, scenario_id)
        row["status_display"] = STATUS_LABELS.get(row.get("status", ""), f"{row.get('status', '')} / 待确认")
        if row.get("status") in {"needs_login", "permission_required"}:
            if scenario_id == "patenthub_patents":
                row["next_action"] = (
                    "需要用户登录 PatentHub：agent 先执行 open-browser-session "
                    "--scenario patenthub_patents --background 打开持久化浏览器；"
                    "用户完成登录/验证后通知 agent 继续，再重新运行 PatentHub 采集。"
                )
            else:
                row["next_action"] = (
                    f"open-browser-session --scenario {scenario_id} --headless false，"
                    "然后在可见浏览器中完成登录或真人验证。"
                )
        else:
            row["next_action"] = ""
        normalized.append(row)
    return normalized


def _by_type(materials: list[dict], material_type: str) -> list[dict]:
    return [item for item in materials if item.get("material_type") == material_type]


def _titles(materials: list[dict], limit: int = 5) -> list[str]:
    return [clean_display_title(item.get("title", "")) for item in materials[:limit] if item.get("title")]


def clean_display_title(title: str) -> str:
    return str(title or "").split(" 专利标题（英）：", 1)[0].strip()


def _raw(material: dict, key: str) -> str:
    value = (material.get("raw_fields") or {}).get(key, "")
    return "；".join(str(item) for item in value) if isinstance(value, list) else str(value or "")


def _competitor_lines(competitors: list[dict]) -> list[str]:
    lines = []
    for item in competitors[:8]:
        raw = item.get("raw_fields") or {}
        parts = [
            item.get("title", ""),
            raw.get("registration_certificate_number", ""),
            raw.get("registrant", ""),
            raw.get("methodology", ""),
            raw.get("approval_date", ""),
        ]
        line = " / ".join(str(part) for part in parts if part)
        if line:
            lines.append(line)
    return lines


def build_feasibility_analysis(
    materials: list[dict],
    evidence_cards: list[dict],
    scenario_statuses: list[dict],
) -> dict[str, Any]:
    competitors = _by_type(materials, "competitor")
    literature = _by_type(materials, "literature")
    patents = _by_type(materials, "patent")
    standards = _by_type(materials, "standard")
    regulatory = _by_type(materials, "regulatory")
    extracted_count = sum(1 for item in materials if item.get("extracted_text_path"))
    downloaded_count = sum(1 for item in materials if item.get("download_files"))
    blocked = [
        item
        for item in scenario_statuses
        if item.get("status") in {"needs_login", "permission_required", "collection_failed", "no_results"}
    ]

    judgement_parts = []
    if competitors:
        judgement_parts.append(
            f"已检索到 {len(competitors)} 条 NMPA 竞品/同类注册材料，说明该方向存在明确注册参照。"
        )
    if literature:
        judgement_parts.append(
            f"已采集 {len(literature)} 条中文期刊/CMA 文献材料，可支撑临床背景、检测价值和应用定位的初步论证。"
        )
    if standards or regulatory:
        judgement_parts.append(
            f"已采集 {len(standards)} 条现行标准和 {len(regulatory)} 条监管/指导原则材料，可作为注册路径和性能评价要求的参照。"
        )
    if patents:
        judgement_parts.append(
            f"已采集 {len(patents)} 条 PatentHub 专利材料，但需要人工复核其与目标 IVD 产品的直接相关性。"
        )
    if not judgement_parts:
        judgement_parts.append("当前材料不足以形成可执行立项判断，应先补齐核心来源。")

    clinical = []
    for item in literature[:5]:
        abstract = _raw(item, "abstract") or _raw(item, "summary")
        clinical.append(
            {
                "title": clean_display_title(item.get("title", "")),
                "point": abstract[:260] if abstract else "该文献已采集题录/正文线索，需在证据卡复核阶段确认可引用结论。",
            }
        )

    technology = []
    for item in competitors[:5]:
        raw = item.get("raw_fields") or {}
        technology.append(
            {
                "title": clean_display_title(item.get("title", "")),
                "point": "；".join(
                    str(value)
                    for value in [
                        raw.get("methodology", ""),
                        raw.get("scope", ""),
                        raw.get("sample_type", ""),
                    ]
                    if value
                )
                or "注册详情已采集，可用于对照方法学、样本类型和预期用途。",
            }
        )

    ip_points = []
    for item in patents[:5]:
        raw = item.get("raw_fields") or {}
        title = item.get("title", "")
        abstract = raw.get("abstract") or raw.get("basic_info_text", "")
        relevance = "需人工复核"
        if any(token in f"{title} {abstract}" for token in ["疫苗", "猪", "兽用"]):
            relevance = "可能不是目标人用 IVD 方向的直接专利，应作为排除/风险线索记录"
        ip_points.append(
            {
                "title": clean_display_title(title),
                "identifier": raw.get("publication_number", ""),
                "relevance": relevance,
                "point": str(abstract)[:260],
            }
        )

    gaps = []
    if not competitors:
        gaps.append("缺少 NMPA 竞品注册材料，无法判断国内注册参照和竞争格局。")
    if not literature:
        gaps.append("缺少临床文献材料，临床意义、目标人群和诊疗路径只能保留为待证实。")
    if not standards:
        gaps.append("缺少现行标准材料，性能评价、样本处理和安全要求仍需补充。")
    if not patents:
        gaps.append("缺少专利材料，知识产权风险和可绕开空间无法判断。")
    if blocked:
        gaps.append("存在未完成或受限场景：" + "；".join(f"{item.get('scenario_id')}={item.get('status')}" for item in blocked))
    if any(item.get("download_status") == "permission_required" for item in patents):
        gaps.append("PatentHub 部分 PDF/全文下载受权限限制，当前仅基于页面可见信息形成初步判断。")
    if not gaps:
        gaps.append("当前材料已覆盖主要 MVP 来源，但所有自动证据卡仍需研发人员复核后才能作为正式报告结论。")

    return {
        "overall_judgement": " ".join(judgement_parts),
        "source_basis": {
            "materials": len(materials),
            "evidence_cards": len(evidence_cards),
            "extracted_text": extracted_count,
            "downloaded_originals": downloaded_count,
        },
        "competitor_lines": _competitor_lines(competitors),
        "clinical_points": clinical,
        "technology_points": technology,
        "standard_titles": _titles(standards),
        "regulatory_titles": _titles(regulatory),
        "ip_points": ip_points,
        "evidence_gaps": gaps,
        "next_actions": [
            "优先复核 NMPA 竞品的预期用途、方法学、样本类型和注册证有效期。",
            "复核文献证据卡，把摘要线索归入临床意义、目标人群、诊疗路径和技术可行性。",
            "对 PatentHub 结果做相关性筛选，排除动物疫苗等非目标 IVD 方向材料。",
        ],
    }


def build_business_decision(
    *,
    materials: list[dict],
    literature_materials: list[dict],
    regulatory_materials: list[dict],
    competitor_materials: list[dict],
    standard_materials: list[dict],
    patent_materials: list[dict],
    scenario_map: dict[str, dict],
) -> dict[str, Any]:
    """Build business-facing decision text, not development diagnostics."""
    literature_count = len(literature_materials)
    literature_signals = build_literature_signal_summary(literature_materials)
    marker = literature_signals["marker"]
    missing_domains = []
    if not regulatory_materials:
        missing_domains.append("法规/指导原则")
    if not competitor_materials:
        missing_domains.append("NMPA 竞品注册")
    if not standard_materials:
        missing_domains.append("现行标准")
    if not patent_materials:
        missing_domains.append("专利")

    if literature_count and missing_domains:
        conclusion = (
            "当前已形成文献证据基础，可支持继续推进立项调研，但尚不能形成完整立项建议。"
            "主要原因是注册路径、同类产品、标准和专利风险证据尚未补齐。"
        )
    elif literature_count:
        conclusion = (
            f"当前证据支持 AD 血液 {marker} 方向继续进入立项复核。"
            "建议按“辅助诊断/风险评估/转诊分层”定位推进，先完成注册证字段、专利全文和性能方案复核后再进入正式立项会。"
        )
    else:
        conclusion = (
            "当前尚未形成可用于立项判断的证据基础，应先完成核心来源采集。"
        )

    basis = [
        (
            f"已采集文献材料 {literature_count} 条，覆盖 PubMed、PMC、OpenAlex、中国指南和国际对标资料，可支撑临床价值、目标人群和检测场景复核。"
            f"其中含摘要 {literature_signals['with_abstract']} 条、结构化 Abstract {literature_signals['with_structured']} 条、可解析文本 {literature_signals['extracted']} 份。"
        ),
        f"{marker} 与 AD 病理、认知下降风险和血液标志物临床应用相关，文献链条可支撑研发继续做方法学和临床性能论证。",
    ]
    if competitor_materials:
        basis.append(
            f"已导入 {len(competitor_materials)} 条竞品/同类注册线索，可用于识别同类标志物、化学发光/免疫检测平台、样本类型和注册参照。"
        )
    if regulatory_materials:
        basis.append(
            f"已导入 {len(regulatory_materials)} 条法规/注册路径材料，可用于确认 IVD 注册管理、分类规则和预期用途边界。"
        )
    if standard_materials:
        basis.append(
            f"已导入 {len(standard_materials)} 条标准/性能控制材料，可用于设计 LoD/LoQ、精密度、线性、干扰、参考区间和样本稳定性验证。"
        )
    if patent_materials:
        basis.append(
            f"已形成 {len(patent_materials)} 条专利检索策略和风险提示，后续需由专利人员完成全文和权利要求复核。"
        )
    if missing_domains:
        basis.append("尚缺：" + "、".join(missing_domains) + "。这些缺口会影响注册可行性、竞品定位、性能验证边界和知识产权风险判断。")
    if scenario_map.get("pmc_fulltext", {}).get("status") == "completed":
        basis.append("PMC 已补入开放全文材料，但 PDF 是否可下载仍需逐条核验。")

    cannot_conclude = []
    if not competitor_materials:
        cannot_conclude.append("不能判断国内是否已有同类注册产品、主流方法学、样本类型和预期用途表述。")
    if not regulatory_materials:
        cannot_conclude.append("不能判断该方向的注册路径、临床评价和性能评价要求。")
    if not standard_materials:
        cannot_conclude.append("不能判断适用标准、性能验证项目和安全/质量体系约束。")
    if not patent_materials:
        cannot_conclude.append("不能判断知识产权风险、自由实施空间和技术绕开方向。")
    if not cannot_conclude:
        cannot_conclude.extend(
            [
                "不能直接认定 NMPA 官方数据库字段已经完整核验；注册证编号、注册人、有效期、适用样本和说明书仍需人工复核。",
                f"不能直接形成自由实施结论；{marker} 抗体表位、校准品、算法、试剂盒组合和平台绑定专利需要专利全文审阅。",
                "不能直接确定最终性能指标；参考区间、cut-off、灰区比例、临床灵敏度/特异性和不同平台一致性需要研发与医学共同确认。",
                "自动证据卡仍未人工复核，不能直接作为最终立项会结论。",
            ]
        )

    return {
        "conclusion": conclusion,
        "basis": basis,
        "cannot_conclude": cannot_conclude,
        "recommendation": (
            "建议进入立项复核阶段：注册人员核验国内同类注册证字段，研发人员输出化学发光免疫法性能验证方案，医学人员确认适用人群与临床解释边界，专利人员完成 FTO 初筛。四项完成后再形成正式立项结论。"
        ),
    }


def build_search_profile(task: dict) -> list[dict[str, str]]:
    confirmations = task.get("confirmations") or {}
    date_range = confirmations.get("literature_date_range") or {}
    if isinstance(date_range, dict):
        date_text = " 至 ".join(
            part
            for part in [
                str(date_range.get("start") or date_range.get("from") or ""),
                str(date_range.get("end") or date_range.get("to") or ""),
            ]
            if part
        )
    else:
        date_text = str(date_range or "")
    rows = [
        ("标题/课题", task.get("topic", "")),
        ("核心检索词", confirmations.get("primary_query", "")),
        ("英文检索词", confirmations.get("english_keywords", "")),
        ("样本类型", confirmations.get("sample_type", "")),
        ("平台", confirmations.get("platform", "")),
        ("方法学/检测原理", confirmations.get("methodology", "")),
        ("预期用途", confirmations.get("intended_use", "")),
        ("目标地区", confirmations.get("target_region", "")),
        ("竞品范围", confirmations.get("competitor_scope", "")),
        ("专利范围", confirmations.get("patent_scope", "")),
        ("文献时间范围", date_text or f"近 {confirmations.get('literature_years', 5)} 年"),
        ("单渠道展示上限", f"每个检索渠道最多展示 {SOURCE_DISPLAY_LIMIT} 条"),
    ]
    return [{"label": label, "value": str(value or "-")} for label, value in rows]


def _material_title_join(materials: list[dict], limit: int = 3) -> str:
    titles = [item.get("title", "") for item in materials[:limit] if item.get("title")]
    if len(materials) > limit:
        titles.append(f"另 {len(materials) - limit} 条")
    return "；".join(titles) if titles else "暂无材料"


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _count_topic(materials: list[dict], terms: list[str]) -> int:
    count = 0
    for item in materials:
        raw = item.get("raw_fields") or {}
        text = " ".join(
            str(value or "")
            for value in [
                item.get("title", ""),
                raw.get("abstract", ""),
                raw.get("full_visible_text", ""),
                raw.get("keywords", ""),
                raw.get("mesh_terms", ""),
            ]
        )
        if _contains_any(text, terms):
            count += 1
    return count


def _sample_titles(materials: list[dict], terms: list[str], limit: int = 4) -> str:
    titles = []
    for item in materials:
        raw = item.get("raw_fields") or {}
        text = f"{item.get('title', '')} {raw.get('abstract', '')} {raw.get('keywords', '')}"
        if _contains_any(text, terms):
            title = clean_display_title(item.get("title", ""))
            if title and title not in titles:
                titles.append(title)
        if len(titles) >= limit:
            break
    return "；".join(titles) if titles else "暂无直接题名线索"


def _target_marker(materials: list[dict], confirmations: dict | None = None) -> str:
    profile_text = ""
    if confirmations:
        profile_text = " ".join(
            str(confirmations.get(key, "") or "")
            for key in [
                "primary_query",
                "english_keywords",
                "chinese_synonyms",
                "methodology",
                "platform",
                "competitor_scope",
                "patent_scope",
            ]
        ).lower()
    if any(term in profile_text for term in ["aβ42/40", "abeta42/40", "amyloid beta 42/40", "aβ40", "aβ42"]):
        return "Aβ42/40"
    if "p-tau217" in profile_text or "ptau217" in profile_text or "tau217" in profile_text:
        return "p-Tau217"
    if "p-tau181" in profile_text or "ptau181" in profile_text or "tau181" in profile_text:
        return "p-Tau181"
    text = " ".join(item.get("title", "") for item in materials[:200]).lower()
    if any(term in text for term in ["aβ42/40", "abeta42/40", "amyloid beta 42/40"]):
        return "Aβ42/40"
    if "217" in text:
        return "p-Tau217"
    if "181" in text:
        return "p-Tau181"
    if "aβ" in text or "abeta" in text or "amyloid beta" in text:
        return "Aβ"
    return "目标标志物"


def build_literature_signal_summary(
    literature_materials: list[dict],
    confirmations: dict | None = None,
) -> dict[str, Any]:
    total = len(literature_materials)
    pubmed = sum(1 for item in literature_materials if item.get("source_scenario") == "pubmed_literature")
    pmc = sum(1 for item in literature_materials if item.get("source_scenario") == "pmc_fulltext")
    extracted = sum(1 for item in literature_materials if item.get("extracted_text_path"))
    with_abstract = sum(1 for item in literature_materials if (item.get("raw_fields") or {}).get("abstract"))
    with_structured = sum(1 for item in literature_materials if (item.get("raw_fields") or {}).get("abstract_sections"))
    marker = _target_marker(literature_materials, confirmations)
    topics = {
        "blood": _count_topic(literature_materials, ["blood", "plasma", "serum", "血浆", "血清", "血液"]),
        "csf": _count_topic(literature_materials, ["CSF", "cerebrospinal fluid", "脑脊液"]),
        "mci": _count_topic(literature_materials, ["MCI", "mild cognitive impairment", "轻度认知"]),
        "diagnosis": _count_topic(literature_materials, ["diagnosis", "diagnostic", "诊断", "differential"]),
        "screening": _count_topic(literature_materials, ["screening", "primary care", "triage", "筛查", "转诊"]),
        "risk": _count_topic(literature_materials, ["risk", "prediction", "predict", "prognosis", "progression", "风险", "预测", "进展"]),
        "amyloid_reference": _count_topic(literature_materials, ["amyloid PET", "Aβ", "Abeta", "amyloid pathology", "淀粉样"]),
        "tau_reference": _count_topic(literature_materials, ["tau PET", "tau pathology", "神经原纤维", "tau pathology"]),
        "csf_reference": _count_topic(literature_materials, ["CSF biomarker", "cerebrospinal fluid biomarker", "脑脊液标志物"]),
        "auc": _count_topic(literature_materials, ["AUC", "area under", "sensitivity", "specificity", "灵敏度", "特异性"]),
        "immunoassay": _count_topic(literature_materials, ["immunoassay", "ELISA", "Simoa", "chemiluminescence", "ECL", "免疫", "化学发光"]),
    }
    return {
        "marker": marker,
        "total": total,
        "pubmed": pubmed,
        "pmc": pmc,
        "extracted": extracted,
        "with_abstract": with_abstract,
        "with_structured": with_structured,
        "topics": topics,
        "examples": {
            "blood": _sample_titles(literature_materials, ["blood", "plasma", "serum"], 4),
            "diagnosis": _sample_titles(literature_materials, ["diagnosis", "diagnostic"], 4),
            "risk": _sample_titles(literature_materials, ["risk", "prediction", "progression"], 4),
            "reference": _sample_titles(literature_materials, ["amyloid PET", "tau PET", "CSF", "pathology"], 4),
            "technology": _sample_titles(literature_materials, ["immunoassay", "ELISA", "Simoa", "chemiluminescence", "ECL"], 4),
        },
    }


def _signal_sentence(signals: dict[str, Any]) -> str:
    topics = signals.get("topics", {})
    return (
        f"文献证据共 {signals.get('total', 0)} 条，其中 PubMed {signals.get('pubmed', 0)} 条、PMC/开放全文 {signals.get('pmc', 0)} 条；"
        f"已解析文本 {signals.get('extracted', 0)} 份，含摘要 {signals.get('with_abstract', 0)} 条，含结构化 Abstract {signals.get('with_structured', 0)} 条。"
        f"血液/血浆/血清相关 {topics.get('blood', 0)} 条，CSF 相关 {topics.get('csf', 0)} 条，MCI/早期认知障碍相关 {topics.get('mci', 0)} 条，"
        f"诊断/鉴别诊断相关 {topics.get('diagnosis', 0)} 条，筛查/分诊相关 {topics.get('screening', 0)} 条，风险预测/进展相关 {topics.get('risk', 0)} 条。"
    )


def build_project_analysis_sections(
    *,
    literature_materials: list[dict],
    regulatory_materials: list[dict],
    competitor_materials: list[dict],
    standard_materials: list[dict],
    patent_materials: list[dict],
    materials: list[dict],
    confirmations: dict | None = None,
) -> list[dict[str, Any]]:
    signals = build_literature_signal_summary(literature_materials, confirmations)
    marker = signals["marker"]
    topics = signals["topics"]
    examples = signals["examples"]
    signal_text = _signal_sentence(signals)
    literature_titles = _material_title_join(literature_materials)
    competitor_titles = _material_title_join(competitor_materials)
    regulatory_titles = _material_title_join(regulatory_materials)
    standard_titles = _material_title_join(standard_materials)
    patent_titles = _material_title_join(patent_materials)
    return [
        {
            "id": "analysis-1",
            "title": "临床意义",
            "analysis": (
                f"{signal_text} 综合题名、摘要和全文线索看，{marker} 不是单纯研究性概念，证据集中在 AD 病理识别、MCI/早期人群分层、"
                "血液标志物替代或前置 PET/CSF 检查、以及临床试验/专科诊疗路径中的辅助判断。"
            ),
            "evidence": f"{examples['blood']}；{examples['diagnosis']}",
            "gap": "需要按人群、疾病阶段、参照方法和检测平台进一步提取 AUC、灵敏度、特异性、cut-off 和灰区比例。",
        },
        {
            "id": "analysis-2",
            "title": "临床应用定位",
            "analysis": (
                f"诊断/鉴别诊断相关文献 {topics.get('diagnosis', 0)} 条，筛查/分诊相关 {topics.get('screening', 0)} 条，风险预测/进展相关 {topics.get('risk', 0)} 条。"
                f"因此 {marker} 更适合作为 AD 辅助诊断、Aβ/Tau 病理阳性预测、认知下降风险分层和临床研究入组辅助，不宜单独声明为确诊工具。"
            ),
            "evidence": f"诊断线索：{examples['diagnosis']}；风险线索：{examples['risk']}",
            "gap": "需要医学人员确认说明书适用人群、排除条件、阴阳性解释和联合检查建议。",
        },
        {
            "id": "analysis-3",
            "title": "目标使用场景",
            "analysis": (
                f"文献中血液样本相关 {topics.get('blood', 0)} 条、MCI/早期认知障碍相关 {topics.get('mci', 0)} 条，提示首要场景应放在记忆门诊、神经内科、老年医学科、"
                "认知障碍专病门诊和临床研究队列，而不是泛人群无症状筛查。"
            ),
            "evidence": examples["blood"],
            "gap": "需要补充真实临床路径、检测频次、报告解释和复测策略。",
        },
        {
            "id": "analysis-4",
            "title": "目标人群",
            "analysis": (
                f"现有文献更集中于疑似 AD、MCI、主观认知下降、AD 连续谱及专科就诊人群。血液相关线索 {topics.get('blood', 0)} 条，"
                f"CSF 相关线索 {topics.get('csf', 0)} 条，说明血液 {marker} 可作为低创入口，但 CSF/PET 仍是重要参照。"
            ),
            "evidence": literature_titles,
            "gap": "需要按血浆、血清、全血分别形成样本适用性和干扰因素评估。",
        },
        {
            "id": "analysis-5",
            "title": "诊疗路径",
            "analysis": (
                f"文献中 amyloid PET/Aβ 病理参照相关 {topics.get('amyloid_reference', 0)} 条，tau PET/Tau 病理参照相关 {topics.get('tau_reference', 0)} 条，"
                f"CSF 参照相关 {topics.get('csf_reference', 0)} 条。{marker} 的合理位置是 PET/CSF 前的前置分层和转诊辅助，阳性/阴性解释应结合临床量表、影像和病史。"
            ),
            "evidence": examples["reference"],
            "gap": "需要确认与量表、影像、CSF、Aβ/tau 组合检测的推荐顺序。",
        },
        {
            "id": "analysis-6",
            "title": "金标准与参照方法",
            "analysis": (
                f"当前证据显示，{marker} 的评价参照不应只使用临床诊断标签。研发方案应优先定义 amyloid PET/Aβ 病理、tau PET/Tau 病理、CSF Aβ42/40 与 p-tau 等参照方法，"
                "并区分病理阳性预测、临床诊断辅助和疾病进展预测三类终点。"
            ),
            "evidence": literature_titles,
            "gap": "需要定义临床试验/性能评价中采用的参照标准和一致性评价指标。",
        },
        {
            "id": "analysis-7",
            "title": "指南与共识",
            "analysis": (
                f"文献池中指南、共识、临床实践建议和血液标志物框架性文献应优先用于确定 {marker} 的临床解释边界。"
                "自动检索结果显示该方向已有较多国际讨论，但中文指南/全文来源若未命中，不能直接替代本土注册和临床使用语境。"
            ),
            "evidence": literature_titles,
            "gap": "需要补齐中文期刊原文、指南推荐等级和引用证据级别。",
        },
        {
            "id": "analysis-8",
            "title": "专家和组织意见",
            "analysis": (
                "现阶段专家和组织意见主要间接来自指南、共识、协会实践建议和高被引综述。"
                f"这些材料可用于界定 {marker} 的适用场景、报告解释边界和与 PET/CSF 的关系，但不能替代企业内部 KOL 访谈和本地临床路径确认。"
            ),
            "evidence": literature_titles,
            "gap": "需要补充临床专家、注册人员和研发负责人的确认意见。",
        },
        {
            "id": "analysis-9",
            "title": "市场准入与收费",
            "analysis": (
                f"文献证据可以证明 {marker} 的临床需求和技术关注度，但不能直接证明市场准入可行性。"
                "收费编码、医保支付、医院检验项目立项、套餐组合和患者自费接受度需要另行采集真实市场材料。"
            ),
            "evidence": "暂无直接材料",
            "gap": "需要补充收费项目、地区准入、采购渠道和竞品价格信息。",
        },
        {
            "id": "analysis-10",
            "title": "市场定位",
            "analysis": (
                f"从文献主题看，{marker} 更适合作为 AD 血液标志物组合或单项高价值标志物进入专科辅助诊断、病理阳性预测和研究入组场景。"
                "商业定位上应强调低创、可及、可前置分层，而不是替代 PET/CSF 或单项确诊。"
            ),
            "evidence": competitor_titles,
            "gap": "需要补充目标医院层级、科室入口、检测套餐组合和商业化路径。",
        },
        {
            "id": "analysis-11",
            "title": "竞争格局",
            "analysis": (
                f"已导入 {len(competitor_materials)} 条竞品/同类注册线索。若 NMPA 采集未完成，当前竞争格局只能从文献、公开产品和相邻标志物推断，"
                f"重点关注 {marker}、其他 p-tau 标志物、Aβ42/40、NfL 等组合方案以及化学发光/免疫检测平台差异。"
            ),
            "evidence": competitor_titles,
            "gap": "NMPA 官方数据库字段、注册证状态、说明书和有效期需要人工核验。",
        },
        {
            "id": "analysis-12",
            "title": "出口与注册",
            "analysis": (
                f"已导入 {len(regulatory_materials)} 条法规/注册材料。对 {marker} 这类 AD 血液标志物项目，注册论证不能只看文献有效性，"
                "还要把预期用途、样本类型、临床评价路径、同品种比对可能性和性能验证要求拆开确认。"
            ),
            "evidence": regulatory_titles,
            "gap": "需要确认分类编码、临床评价路径、同品种比对可能性和注册申报资料清单。",
        },
        {
            "id": "analysis-13",
            "title": "技术可行性",
            "analysis": (
                f"免疫检测/ELISA/Simoa/化学发光/ECL 等平台相关文献 {topics.get('immunoassay', 0)} 条，AUC/灵敏度/特异性等性能评价相关 {topics.get('auc', 0)} 条。"
                f"{marker} 在血液中丰度低、前分析变量敏感，对抗体特异性、校准体系、批间一致性、基质效应和样本稳定性要求较高；技术可行性应从研究平台向可注册 IVD 平台做桥接验证。"
            ),
            "evidence": "；".join([examples["technology"], competitor_titles]),
            "gap": "需要研发输出 LoD/LoQ、线性、精密度、hook、交叉反应、干扰和稳定性验证方案。",
        },
        {
            "id": "analysis-14",
            "title": "参考物质",
            "analysis": (
                f"{marker} 的立项风险不只在临床价值，还在可溯源校准体系、质控品和平台一致性。"
                "若无明确参考物质/校准品证据，后续性能转化可能出现批间一致性、不同平台可比性和 cut-off 固化困难。"
            ),
            "evidence": standard_titles,
            "gap": "需要确认抗原/抗体、校准品、质控品、溯源体系和批间一致性方案。",
        },
        {
            "id": "analysis-15",
            "title": "安全要求",
            "analysis": (
                f"{marker} 检测的安全风险主要来自假阳性、假阴性、灰区结果和过度解释。"
                "对于认知障碍和 AD 风险场景，报告必须强调辅助判断属性，避免患者或医生将单项结果理解为确诊或排除诊断。"
            ),
            "evidence": regulatory_titles,
            "gap": "需要形成风险分析、适用限制、警示语和结果解释模板。",
        },
        {
            "id": "analysis-16",
            "title": "原材料可获得性",
            "analysis": (
                f"{marker} 方法学转化依赖高特异性抗体、稳定抗原/校准品、质控材料和低背景检测体系。"
                "如果无法确认抗体表位、交叉反应、供应稳定性和校准体系，临床文献再充分也不能直接转化为可注册产品。"
            ),
            "evidence": patent_titles,
            "gap": "需要补充关键抗体、抗原、磁珠/发光底物、校准品和质控品供应风险。",
        },
        {
            "id": "analysis-17",
            "title": "其他发现 / 待归类线索",
            "analysis": "当前最大剩余缺口集中在 NMPA 字段核验、专利全文/FTO、中文期刊全文、PMC PDF 下载和业务专家复核。",
            "evidence": f"当前材料总数 {len(materials)} 条",
            "gap": "应将缺口转为 Excel 补证任务，逐项关闭后再形成正式立项结论。",
        },
    ]


def build_business_action_rows(
    *,
    regulatory_materials: list[dict],
    competitor_materials: list[dict],
    standard_materials: list[dict],
    patent_materials: list[dict],
    literature_materials: list[dict],
    scenario_map: dict[str, dict],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not competitor_materials:
        marker = _target_marker(literature_materials)
        rows.append(
            {
                "priority": "P0",
                "owner": "注册 / 产品",
                "action": f"补查 NMPA 同类产品，确认是否已有 AD 血液 {marker} 或相近 AD 标志物 IVD 注册路径/产品。",
                "acceptance": "形成同类产品清单，至少包含注册证编号、注册人、方法学、样本类型、预期用途和有效期。",
            }
        )
    if not regulatory_materials:
        rows.append(
            {
                "priority": "P0",
                "owner": "注册",
                "action": "补查 CMDE/NMPA 指导原则、审评报告和临床评价相关文件。",
                "acceptance": "明确注册分类、性能评价、临床评价和申报资料要求；无法命中专门文件时给出可类比文件。",
            }
        )
    if not standard_materials:
        rows.append(
            {
                "priority": "P0",
                "owner": "研发 / 质量",
                "action": "补查现行国家、行业和团体标准，确认性能验证、样本处理和安全要求。",
                "acceptance": "形成适用标准清单，标注标准状态、标准号、适用条款和与本项目的关系。",
            }
        )
    if not patent_materials:
        rows.append(
            {
                "priority": "P1",
                "owner": "研发 / 知识产权",
                "action": f"补查 {marker}、血液检测、免疫检测平台和 AD 辅助诊断相关专利。",
                "acceptance": "形成高相关专利清单，并标注可能阻碍、可绕开点和需法务复核项。",
            }
        )
    if literature_materials:
        rows.append(
            {
                "priority": "P1",
                "owner": "医学 / 研发",
                "action": "复核已采集文献，筛出真正支持目标血液标志物 IVD 立项的核心证据。",
                "acceptance": "每条纳入证据明确对应临床意义、目标人群、诊疗路径、性能指标或技术可行性。",
            }
        )
    if scenario_map.get("pmc_fulltext", {}).get("status") == "completed":
        rows.append(
            {
                "priority": "P2",
                "owner": "医学 / 项目助理",
                "action": "核验 PMC 全文和开放 PDF 链接，补充不可下载全文的替代来源或人工下载记录。",
                "acceptance": "核心文献至少保留 PMID/PMCID/DOI、页面链接、摘要或正文摘录和全文获取状态。",
            }
        )
    return rows


def build_evidence_gap_rows(
    *,
    literature_materials: list[dict],
    regulatory_materials: list[dict],
    competitor_materials: list[dict],
    standard_materials: list[dict],
    patent_materials: list[dict],
    scenario_map: dict[str, dict],
) -> list[dict[str, str]]:
    """Business-facing evidence gaps and supplement tasks."""
    rows: list[dict[str, str]] = [
        {
            "gap": "NMPA 官方注册字段仍需逐项核验",
            "current_basis": f"已形成 {len(competitor_materials)} 条竞品/同类注册线索。",
            "missing_evidence": "注册证编号、注册人、有效期、产品组成、样本类型、方法学、预期用途、说明书链接。",
            "impact": "影响中国注册参照、同品种比对、竞品定位和说明书边界。",
            "owner": "注册 / 产品",
            "acceptance": "形成可点击来源链接和字段完整的竞品注册清单。",
        },
        {
            "gap": "核心文献的性能指标尚未结构化提取",
            "current_basis": f"已采集 {len(literature_materials)} 条文献材料。",
            "missing_evidence": "AUC、灵敏度、特异性、cut-off、样本量、疾病分期、参照方法、平台/方法学。",
            "impact": "影响是否值得立项、性能目标设定和临床试验方案设计。",
            "owner": "医学 / 研发",
            "acceptance": "核心文献逐条形成指标摘要，并映射到项目分析 17 个章节。",
        },
        {
            "gap": "样本类型证据需要按血浆、血清、全血拆分",
            "current_basis": "当前检索画像包含血浆 / 血清 / 全血，但材料中的样本类型尚未统一归类。",
            "missing_evidence": "各样本类型的稳定性、抗凝剂、冻融、基质效应、干扰和平台适配证据。",
            "impact": "影响产品样本声明、采血管选择和分析性能验证。",
            "owner": "研发 / 医学",
            "acceptance": "形成样本类型对比表，并明确首版产品建议样本。",
        },
        {
            "gap": "专利全文和 FTO 判断不足",
            "current_basis": f"已形成 {len(patent_materials)} 条专利检索/风险线索。",
            "missing_evidence": "高相关专利全文、权利要求、法律状态、地域、到期日、抗体表位和平台绑定风险。",
            "impact": "影响自由实施、研发路线选择和上市风险。",
            "owner": "知识产权 / 研发",
            "acceptance": "输出高相关专利清单和 FTO 初筛意见。",
        },
        {
            "gap": "参考物质、校准品和关键原材料证据不足",
            "current_basis": f"已形成 {len(standard_materials)} 条标准/性能控制材料。",
            "missing_evidence": "抗原/抗体来源、校准品、质控品、溯源体系、批间一致性和供应风险。",
            "impact": "影响研发可行性、成本、供应稳定性和注册资料完整性。",
            "owner": "研发 / 供应链 / 质量",
            "acceptance": "形成关键原材料清单、候选供应商和验证计划。",
        },
        {
            "gap": "市场准入、收费和商业化路径尚未形成证据",
            "current_basis": "当前材料以文献、注册、法规和专利为主。",
            "missing_evidence": "收费项目、医院科室入口、检测套餐、竞品价格、渠道和目标医院层级。",
            "impact": "影响立项商业价值和首版产品定位。",
            "owner": "市场 / 产品",
            "acceptance": "形成市场定位和准入路径简表。",
        },
    ]
    if scenario_map.get("pmc_fulltext", {}).get("status") == "completed":
        rows.append(
            {
                "gap": "PMC 开放全文已采集，但 PDF 下载状态需逐篇确认",
                "current_basis": scenario_map.get("pmc_fulltext", {}).get("last_message", ""),
                "missing_evidence": "核心文献 PDF、本地快照、正文表格和可引用摘录。",
                "impact": "影响证据复核效率和后续审计追溯。",
                "owner": "项目助理 / 医学",
                "acceptance": "核心 PMC 文献保留原文链接、PMCID、PDF/全文状态和摘录位置。",
            }
        )
    return rows


def build_report(task_dir: Path, report_type: str) -> dict:
    task = read_json(task_dir / "task.json")
    css = (asset_root() / "styles" / "report.css").read_text(encoding="utf-8")
    reviewed_path = task_dir / "data" / "reviewed_evidence_cards.jsonl"
    reviewed_cards = list(read_jsonl(reviewed_path))
    review_source = "reviewed" if reviewed_cards else "draft"
    evidence_cards = normalize_evidence_cards(
        reviewed_cards or list(read_jsonl(task_dir / "data" / "evidence_cards.jsonl"))
    )
    report_sections = normalize_report_sections(
        list(read_jsonl(task_dir / "data" / "report_sections.jsonl"))
    )
    materials = normalize_materials(
        list(read_jsonl(task_dir / "data" / "materials.jsonl")),
        evidence_cards,
        task_dir=task_dir,
    )
    scenario_statuses = normalize_scenario_statuses(
        list((task.get("scenario_statuses") or {}).values())
    )
    collection_alerts = build_collection_alerts(
        materials=materials,
        evidence_cards=evidence_cards,
        scenario_statuses=scenario_statuses,
    )
    generated_at = now_iso()

    if report_type == "materials":
        template_path = asset_root() / "templates" / "materials-report.html"
        output = task_dir / "reports" / "materials-index_v001.html"
        latest = task_dir / "reports" / "latest-materials-index.html"
        html = Template(template_path.read_text(encoding="utf-8")).render(
            task_id=task["task_id"],
            topic=task["topic"],
            materials=materials,
            evidence_cards=evidence_cards,
            review_source=review_source,
            scenario_statuses=scenario_statuses,
            collection_alerts=collection_alerts,
            failed_count=sum(1 for item in materials if item.get("failure_type")),
            generated_at=generated_at,
            css=css,
        )
    elif report_type == "feasibility":
        template_path = asset_root() / "templates" / "feasibility-report.html"
        output = task_dir / "reports" / "feasibility-report_v001.html"
        latest = task_dir / "reports" / "latest-feasibility-report.html"
        html = Template(template_path.read_text(encoding="utf-8")).render(
            task_id=task["task_id"],
            topic=task["topic"],
            materials=materials,
            evidence_cards=evidence_cards,
            review_source=review_source,
            scenario_statuses=scenario_statuses,
            collection_alerts=collection_alerts,
            included_count=sum(1 for card in evidence_cards if card.get("include_in_report")),
            analysis_source="ai_report_sections" if report_sections else "rule_draft",
            report_sections_count=len(report_sections),
            report_sections_by_title=report_sections_by_title(report_sections),
            cards_by_section=cards_by_section(
                evidence_cards,
                include_only=review_source == "reviewed",
            ),
            analysis=build_feasibility_analysis(materials, evidence_cards, scenario_statuses),
            sections=REPORT_SECTIONS,
            generated_at=generated_at,
            css=css,
        )
    else:
        raise ValueError(f"Unsupported report type: {report_type}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    latest.write_text(html, encoding="utf-8")
    append_jsonl(
        task_dir / "data" / "report_versions.jsonl",
        {"time": generated_at, "type": report_type, "path": str(output.relative_to(task_dir))},
    )
    return {"report_path": str(output), "latest_path": str(latest)}


def _scenario_level(status: str, count: int) -> str:
    if count > 0 or status == "completed":
        return "success"
    if status in {"collection_failed", "needs_login", "permission_required"}:
        return "danger"
    return "warn"


def _scenario_status_text(status: str, count: int) -> str:
    if count > 0:
        return "completed / 已采集"
    if status == "completed":
        return "completed / 已完成"
    if status == "collection_failed":
        return "collection_failed / 采集失败"
    if status in {"needs_login", "permission_required"}:
        return f"{status} / 受限"
    if status == "no_results":
        return "no_results / 未发现结果"
    if status == "not_started":
        return "not_started / 未启动"
    return STATUS_LABELS.get(status, status or "unknown / 待确认")


def build_standard_report(task_dir: Path, output: Path | None = None) -> dict:
    """Render the business-facing tabbed delivery report."""
    task = read_json(task_dir / "task.json")
    css = (asset_root() / "styles" / "report.css").read_text(encoding="utf-8")
    reviewed_path = task_dir / "data" / "reviewed_evidence_cards.jsonl"
    reviewed_cards = list(read_jsonl(reviewed_path))
    review_source = "reviewed" if reviewed_cards else "draft"
    evidence_cards = normalize_evidence_cards(
        reviewed_cards or list(read_jsonl(task_dir / "data" / "evidence_cards.jsonl"))
    )
    materials = normalize_materials(
        list(read_jsonl(task_dir / "data" / "materials.jsonl")),
        evidence_cards,
        task_dir=task_dir,
    )
    materials_by_id = {item.get("material_id"): item for item in materials}
    scenario_statuses = normalize_scenario_statuses(
        list((task.get("scenario_statuses") or {}).values())
    )
    scenario_map = {item.get("scenario_id"): item for item in scenario_statuses}
    collection_alerts = build_collection_alerts(
        materials=materials,
        evidence_cards=evidence_cards,
        scenario_statuses=scenario_statuses,
    )
    analysis = build_feasibility_analysis(materials, evidence_cards, scenario_statuses)

    literature_materials = _by_type(materials, "literature")
    pubmed_materials = [
        item for item in literature_materials if item.get("source_scenario") == "pubmed_literature"
    ]
    pmc_materials = [
        item for item in literature_materials if item.get("source_scenario") == "pmc_fulltext"
    ]
    openalex_materials = [
        item for item in literature_materials if item.get("source_scenario") == "openalex_literature"
    ]
    other_literature_materials = [
        item
        for item in literature_materials
        if item.get("source_scenario") not in {
            "pubmed_literature",
            "pmc_fulltext",
            "openalex_literature",
        }
    ]
    regulatory_materials = _by_type(materials, "regulatory")
    competitor_materials = _by_type(materials, "competitor")
    standard_materials = _by_type(materials, "standard")
    patent_materials = _by_type(materials, "patent")

    evidence_map = [
        {
            "name": "PubMed 文献",
            "count": len(pubmed_materials),
            "status": _scenario_status_text(
                scenario_map.get("pubmed_literature", {}).get("status", ""),
                len(pubmed_materials),
            ),
            "level": _scenario_level(
                scenario_map.get("pubmed_literature", {}).get("status", ""),
                len(pubmed_materials),
            ),
            "use": "支撑国际文献证据、临床价值、目标人群和检测路径判断。",
        },
        {
            "name": "PMC 全文",
            "count": len(pmc_materials),
            "status": _scenario_status_text(
                scenario_map.get("pmc_fulltext", {}).get("status", ""),
                len(pmc_materials),
            ),
            "level": _scenario_level(
                scenario_map.get("pmc_fulltext", {}).get("status", ""),
                len(pmc_materials),
            ),
            "use": "支撑可追溯全文、PDF 下载、关键表格和原文结论复核。",
        },
        {
            "name": "OpenAlex 文献",
            "count": len(openalex_materials),
            "status": _scenario_status_text(
                scenario_map.get("openalex_literature", {}).get("status", ""),
                len(openalex_materials),
            ),
            "level": _scenario_level(
                scenario_map.get("openalex_literature", {}).get("status", ""),
                len(openalex_materials),
            ),
            "use": "支撑跨库文献发现、DOI/PMID 补齐、开放获取全文和 PDF 链接识别。",
        },
        {
            "name": "中文文献",
            "count": len(other_literature_materials),
            "status": _scenario_status_text("", len(other_literature_materials)),
            "level": _scenario_level("", len(other_literature_materials)),
            "use": "补充国内临床应用、实验室管理、指南解读和转化场景。",
        },
        {
            "name": "法规 / 指导原则",
            "count": len(regulatory_materials),
            "status": _scenario_status_text(
                scenario_map.get("cmde_regulatory", {}).get("status", ""),
                len(regulatory_materials),
            ),
            "level": _scenario_level(
                scenario_map.get("cmde_regulatory", {}).get("status", ""),
                len(regulatory_materials),
            ),
            "use": "确认注册路径、性能评价、临床评价和申报资料要求。",
        },
        {
            "name": "NMPA 竞品",
            "count": len(competitor_materials),
            "status": _scenario_status_text(
                scenario_map.get("nmpa_competitor", {}).get("status", ""),
                len(competitor_materials),
            ),
            "level": _scenario_level(
                scenario_map.get("nmpa_competitor", {}).get("status", ""),
                len(competitor_materials),
            ),
            "use": "确认同类产品、方法学、样本类型、预期用途和注册参照。",
        },
        {
            "name": "现行标准",
            "count": len(standard_materials),
            "status": _scenario_status_text(
                scenario_map.get("standards_current", {}).get("status", ""),
                len(standard_materials),
            ),
            "level": _scenario_level(
                scenario_map.get("standards_current", {}).get("status", ""),
                len(standard_materials),
            ),
            "use": "确认性能验证、安全要求、样本处理和质量体系约束。",
        },
        {
            "name": "专利",
            "count": len(patent_materials),
            "status": _scenario_status_text(
                scenario_map.get("patenthub_patents", {}).get("status", ""),
                len(patent_materials),
            ),
            "level": _scenario_level(
                scenario_map.get("patenthub_patents", {}).get("status", ""),
                len(patent_materials),
            ),
            "use": "识别知识产权风险、可绕开空间和研发自由实施风险。",
        },
    ]

    failed_scenarios = [
        item
        for item in scenario_statuses
        if item.get("status") in {"collection_failed", "needs_login", "permission_required"}
    ]
    business_decision = build_business_decision(
        materials=materials,
        literature_materials=literature_materials,
        regulatory_materials=regulatory_materials,
        competitor_materials=competitor_materials,
        standard_materials=standard_materials,
        patent_materials=patent_materials,
        scenario_map=scenario_map,
    )
    action_rows = build_business_action_rows(
        regulatory_materials=regulatory_materials,
        competitor_materials=competitor_materials,
        standard_materials=standard_materials,
        patent_materials=patent_materials,
        literature_materials=literature_materials,
        scenario_map=scenario_map,
    )
    gap_rows = build_evidence_gap_rows(
        literature_materials=literature_materials,
        regulatory_materials=regulatory_materials,
        competitor_materials=competitor_materials,
        standard_materials=standard_materials,
        patent_materials=patent_materials,
        scenario_map=scenario_map,
    )
    project_analysis_sections = build_project_analysis_sections(
        literature_materials=literature_materials,
        regulatory_materials=regulatory_materials,
        competitor_materials=competitor_materials,
        standard_materials=standard_materials,
        patent_materials=patent_materials,
        materials=materials,
        confirmations=task.get("confirmations") or {},
    )
    registration_materials = (
        regulatory_materials + competitor_materials + standard_materials + patent_materials
    )

    template_path = asset_root() / "templates" / "standard-delivery-report.html"
    report_output = output or task_dir / "reports" / "standard-delivery-report.html"
    html = Template(template_path.read_text(encoding="utf-8")).render(
        task_id=task["task_id"],
        topic=task["topic"],
        report_title=report_display_title(task["topic"]),
        materials=materials,
        materials_by_id=materials_by_id,
        evidence_cards=evidence_cards[:SOURCE_DISPLAY_LIMIT],
        review_source=review_source,
        scenario_statuses=scenario_statuses,
        scenario_map=scenario_map,
        collection_alerts=collection_alerts,
        analysis=analysis,
        business_decision=business_decision,
        evidence_map=evidence_map,
        failed_scenarios=failed_scenarios,
        search_profile=build_search_profile(task),
        project_analysis_sections=project_analysis_sections,
        literature_materials=_source_record_limit(literature_materials),
        pubmed_materials=pubmed_materials,
        pmc_materials=pmc_materials,
        openalex_materials=openalex_materials,
        other_literature_materials=other_literature_materials,
        regulatory_materials=regulatory_materials,
        competitor_materials=competitor_materials,
        standard_materials=standard_materials,
        patent_materials=patent_materials,
        registration_materials=_source_record_limit(registration_materials),
        gap_rows=gap_rows,
        action_rows=action_rows,
        generated_at=now_iso(),
        css=css,
    )

    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(html, encoding="utf-8")
    append_jsonl(
        task_dir / "data" / "report_versions.jsonl",
        {
            "time": now_iso(),
            "type": "standard_delivery",
            "path": str(report_output.relative_to(task_dir)),
        },
    )
    return {"report_path": str(report_output)}
