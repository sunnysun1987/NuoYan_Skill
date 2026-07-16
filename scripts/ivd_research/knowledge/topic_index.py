from __future__ import annotations

import re
from typing import Any

from ivd_research.project_profile import has_confirmed_project_profile, project_subject


TOPIC_PATTERNS = {
    "sample": re.compile(r"\b(plasma|serum|CSF|blood|urine|swab|saliva|血浆|血清|脑脊液|全血|尿液|拭子|唾液)\b", re.I),
    "reference": re.compile(r"\b(amyloid PET|tau PET|CSF|pathology|clinical diagnosis|culture|PCR|sequencing|病理|临床诊断|培养|测序)\b", re.I),
    "platform": re.compile(r"\b(chemiluminescence|CLIA|ELISA|immunoassay|immunochromatography|POCT|PCR|qPCR|NGS|mass spectrometry|化学发光|酶联免疫|免疫分析|免疫层析|荧光免疫层析|质谱|核酸检测)\b", re.I),
}


def _marker_aliases(confirmations: dict | None) -> list[str]:
    if not has_confirmed_project_profile(confirmations):
        return []
    aliases = [project_subject({"confirmations": confirmations or {}})]
    synonyms = str((confirmations or {}).get("chinese_synonyms", "") or "")
    aliases.extend(
        item.strip()
        for item in re.split(r"[；;、，,|\n]+", synonyms)
        if item.strip()
    )
    return list(dict.fromkeys(alias for alias in aliases if alias and alias != "目标检测项目"))


def extract_topics(text: str, *, marker_aliases: list[str] | None = None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for topic_type, pattern in TOPIC_PATTERNS.items():
        values = sorted({match.group(0) for match in pattern.finditer(text or "")})
        if values:
            result[topic_type] = values
    marker_values = [
        alias
        for alias in marker_aliases or []
        if re.search(re.escape(alias), text or "", flags=re.I)
    ]
    if marker_values:
        result["marker"] = marker_values
    return result


def build_topic_index(
    materials: list[dict[str, Any]],
    evidence_cards: list[dict[str, Any]],
    *,
    confirmations: dict | None = None,
) -> dict[str, Any]:
    by_material = {card.get("material_id"): card for card in evidence_cards}
    topics: dict[str, dict[str, list[str]]] = {}
    marker_aliases = _marker_aliases(confirmations)
    for material in materials:
        material_id = material.get("material_id")
        raw = material.get("raw_fields") or {}
        card = by_material.get(material_id, {})
        text = " ".join(
            str(value or "")
            for value in [
                material.get("title", ""),
                raw.get("abstract", ""),
                raw.get("summary", ""),
                card.get("summary", ""),
                card.get("evidence_conclusion", ""),
            ]
        )
        extracted = extract_topics(text, marker_aliases=marker_aliases)
        for topic_type, values in extracted.items():
            for value in values:
                bucket = topics.setdefault(topic_type, {}).setdefault(value.lower(), [])
                if material_id and material_id not in bucket:
                    bucket.append(material_id)
    return topics
