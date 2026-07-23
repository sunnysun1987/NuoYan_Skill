from __future__ import annotations

import re
from typing import Any

from .project_profile import has_confirmed_project_profile, project_subject


GENERIC_PROJECT_TERMS = {
    "analysis",
    "assay",
    "biomarker",
    "beta",
    "blood",
    "clinical",
    "detection",
    "diagnosis",
    "diagnostic",
    "disease",
    "human",
    "immunoassay",
    "ivd",
    "kit",
    "method",
    "plasma",
    "quantitative",
    "serum",
    "test",
    "testing",
    "urine",
}


def assess_material_relevance(
    material: dict[str, Any],
    confirmations: dict[str, Any] | None,
) -> dict[str, Any]:
    if not has_confirmed_project_profile(confirmations):
        return {
            "relevant": True,
            "reason": "legacy_task_without_confirmed_profile",
            "matched_aliases": [],
            "matched_context_terms": [],
        }

    aliases = project_aliases(confirmations or {})
    context_terms = project_context_terms(confirmations or {})
    if not aliases and len(context_terms) < 2:
        return {
            "relevant": True,
            "reason": "insufficient_relevance_profile",
            "matched_aliases": [],
            "matched_context_terms": [],
        }
    text = material_relevance_text(material)
    primary_text = material_primary_relevance_text(material)
    matched_aliases = [alias for alias in aliases if _contains_term(text, alias)]
    matched_primary_aliases = [
        alias for alias in aliases if _contains_term(primary_text, alias)
    ]
    matched_context = [term for term in context_terms if _contains_term(text, term)]
    relevant = bool(
        matched_primary_aliases
        or (matched_aliases and matched_context)
        or len(matched_context) >= 2
    )
    reason = (
        "project_alias_match"
        if matched_primary_aliases
        else "project_context_match"
        if relevant
        else "no_project_signal_in_material"
    )
    return {
        "relevant": relevant,
        "reason": reason,
        "matched_aliases": matched_aliases[:8],
        "matched_context_terms": matched_context[:8],
    }


def project_aliases(confirmations: dict[str, Any]) -> list[str]:
    aliases = _split_aliases(str(confirmations.get("chinese_synonyms") or ""))
    subject = project_subject(confirmations, fallback="")
    if subject:
        aliases.append(subject)
    aliases.extend(_specific_ascii_terms(str(confirmations.get("english_keywords") or "")))
    return _dedupe(alias for alias in aliases if _is_specific(alias))


def project_context_terms(confirmations: dict[str, Any]) -> list[str]:
    values = [
        str(confirmations.get("english_keywords") or ""),
        str(confirmations.get("intended_use") or ""),
    ]
    terms: list[str] = []
    for value in values:
        terms.extend(_specific_ascii_terms(value))
        terms.extend(
            chunk
            for chunk in re.findall(r"[\u4e00-\u9fff]{4,}", value)
            if chunk not in {"体外诊断", "辅助诊断", "定量检测", "定性检测"}
        )
    return _dedupe(terms)


def material_relevance_text(material: dict[str, Any]) -> str:
    raw = material.get("raw_fields") or {}
    values = [
        material.get("title"),
        material.get("structured_summary"),
        raw.get("title"),
        raw.get("product_name"),
        raw.get("abstract"),
        raw.get("summary"),
        raw.get("keywords"),
        raw.get("scope"),
        raw.get("full_visible_text"),
        raw.get("basic_info_text"),
    ]
    return " ".join(_flatten(value) for value in values if value)


def material_primary_relevance_text(material: dict[str, Any]) -> str:
    raw = material.get("raw_fields") or {}
    values = [
        material.get("title"),
        raw.get("title"),
        raw.get("product_name"),
        raw.get("keywords"),
        raw.get("scope"),
    ]
    return " ".join(_flatten(value) for value in values if value)


def _split_aliases(value: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r"[；;、，,|\n]+", value)
        if item.strip()
    ]


def _specific_ascii_terms(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{1,}", value)
        if token.lower() not in GENERIC_PROJECT_TERMS
        and (len(token) >= 4 or token.isupper() or any(char.isupper() for char in token[1:]))
    ]


def _is_specific(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(normalized and normalized not in GENERIC_PROJECT_TERMS)


def _contains_term(text: str, term: str) -> bool:
    normalized_text = _normalize(text)
    normalized_term = _normalize(term)
    if not normalized_term:
        return False
    if re.fullmatch(r"[a-z0-9 ]+", normalized_term):
        return bool(
            re.search(
                rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])",
                normalized_text,
            )
        )
    return normalized_term in normalized_text


def _normalize(value: str) -> str:
    text = str(value or "").lower().replace("β", " beta ")
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return " ".join(text.split())


def _flatten(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    return str(value or "")


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        key = _normalize(item)
        if item and key and key not in seen:
            seen.add(key)
            result.append(item)
    return result
