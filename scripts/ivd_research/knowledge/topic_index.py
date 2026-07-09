from __future__ import annotations

import re
from typing import Any


TOPIC_PATTERNS = {
    "marker": re.compile(
        r"\b(p-?tau ?217|p-?tau ?181|Aβ ?42/?40|Aβ ?40/?42|NfL|GFAP|amyloid|tau|"
        r"beta[- ]?hCG|β[- ]?hCG|hCG|human chorionic gonadotropin|cTnI|troponin|PCT|CRP|"
        r"influenza ?A|influenza ?B|RSV|SARS[- ]?CoV[- ]?2)\b|"
        r"(绒毛膜促性腺激素|肌钙蛋白|降钙素原|甲型流感|乙型流感|呼吸道合胞病毒)",
        re.I,
    ),
    "sample": re.compile(r"\b(plasma|serum|CSF|blood|urine|swab|saliva|血浆|血清|脑脊液|全血|尿液|拭子|唾液)\b", re.I),
    "reference": re.compile(r"\b(amyloid PET|tau PET|CSF|pathology|clinical diagnosis|culture|PCR|sequencing|病理|临床诊断|培养|测序)\b", re.I),
    "platform": re.compile(r"\b(chemiluminescence|CLIA|ELISA|immunoassay|immunochromatography|POCT|PCR|qPCR|NGS|mass spectrometry|化学发光|酶联免疫|免疫分析|免疫层析|荧光免疫层析|质谱|核酸检测)\b", re.I),
}


def extract_topics(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for topic_type, pattern in TOPIC_PATTERNS.items():
        values = sorted({match.group(0) for match in pattern.finditer(text or "")})
        if values:
            result[topic_type] = values
    return result


def build_topic_index(materials: list[dict[str, Any]], evidence_cards: list[dict[str, Any]]) -> dict[str, Any]:
    by_material = {card.get("material_id"): card for card in evidence_cards}
    topics: dict[str, dict[str, list[str]]] = {}
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
        extracted = extract_topics(text)
        for topic_type, values in extracted.items():
            for value in values:
                bucket = topics.setdefault(topic_type, {}).setdefault(value.lower(), [])
                if material_id and material_id not in bucket:
                    bucket.append(material_id)
    return topics
