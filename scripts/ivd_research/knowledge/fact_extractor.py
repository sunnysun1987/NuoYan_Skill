from __future__ import annotations

import re
from typing import Any

from ivd_research.models import MetricFact


_NUMBER = r"\d+(?:\.\d+)?"
_PERCENT = r"(?:100(?:\.0+)?|(?:\d|[1-9]\d)(?:\.\d+)?)\s*%"
_RATE = rf"(?:{_PERCENT}|1(?:\.0+)?|0(?:\.\d+)?)(?!\d|\.\d)"
_AMOUNT_UNIT = r"(?:pg|ng|ug|µg|μg|mg|g|mIU|IU|U|mmol|nmol|pmol)"
_UNIT = rf"(?:{_AMOUNT_UNIT}/(?:mL|L)|{_AMOUNT_UNIT}\s+(?:mL|L)(?:\s*[−–-]\s*1)?|%)"
_QUANTITATIVE_VALUE = rf"[~≈∼<>≤≥]?\s*{_NUMBER}(?:\s*(?:-|–|to)\s*{_NUMBER})?\s*(?:{_UNIT})?"
_LINK = r"(?:was|were|is|are|of|=|:|：|为|达到)"
_SENSITIVITY_LABEL = r"(?:\b(?:(?:diagnostic|clinical)\s+)?sensitivity\b|(?:诊断|临床)?(?:敏感度|灵敏度))"
_SPECIFICITY_LABEL = r"(?:\b(?:(?:diagnostic|clinical)\s+)?specificity\b|(?:诊断|临床)?特异性)"


PAIRED_RATE_PATTERN = re.compile(
    rf"{_SENSITIVITY_LABEL}\s*(?:and|/|和|及)\s*{_SPECIFICITY_LABEL}"
    rf"\s*(?:{_LINK}|分别为)?\s*({_RATE})\s*(?:and|/|,|，|和)\s*({_RATE})"
    r"(?:\s*,?\s*respectively)?",
    re.I,
)
SHARED_RATE_PATTERN = re.compile(
    rf"({_RATE})\s+{_SENSITIVITY_LABEL}\s*(?:and|/|和|及)\s*{_SPECIFICITY_LABEL}",
    re.I,
)


METRIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "AUC",
        re.compile(rf"\b(?:AUC|area under (?:the )?curve)\b\s*(?:{_LINK}\s*)?({_RATE})", re.I),
    ),
    (
        "sensitivity",
        re.compile(rf"{_SENSITIVITY_LABEL}\s*(?:{_LINK}\s*)?({_RATE})", re.I),
    ),
    (
        "sensitivity",
        re.compile(rf"({_RATE})\s+{_SENSITIVITY_LABEL}", re.I),
    ),
    (
        "specificity",
        re.compile(rf"{_SPECIFICITY_LABEL}\s*(?:{_LINK}\s*)?({_RATE})", re.I),
    ),
    (
        "specificity",
        re.compile(rf"({_RATE})\s+{_SPECIFICITY_LABEL}", re.I),
    ),
    (
        "lod",
        re.compile(
            rf"(?:\blimit of detection\b(?:\s*\(\s*LoD\s*\))?|\bLoD\b|最低检出限)"
            rf"\s*(?:concentration|value)?\s*(?:{_LINK}\s*)?"
            rf"(?:approximately|about|around|约)?\s*({_QUANTITATIVE_VALUE})",
            re.I,
        ),
    ),
    (
        "cutoff",
        re.compile(
            rf"(?:\b(?:cut-?off|threshold)\b|截断值|临界值)"
            rf"\s*(?:concentration|value)?\s*(?:{_LINK}\s*)?"
            rf"(?:approximately|about|around|约)?\s*({_QUANTITATIVE_VALUE})",
            re.I,
        ),
    ),
    ("HR", re.compile(r"\bHR\b\s*(?:=|:|was|of)?\s*(\d+(?:\.\d+)?)")),
    ("OR", re.compile(r"\bOR\b\s*(?:=|:|was|of)?\s*(\d+(?:\.\d+)?)")),
    (
        "CI",
        re.compile(r"\b(?:95%\s*)?CI\b\s*(?:=|:|was|of)?\s*([0-9.]+\s*(?:-|–|,|to)\s*[0-9.]+)", re.I),
    ),
    (
        "sample_size",
        re.compile(
            r"\b(?:n\s*=|sample size\s*(?:was|of|=|:)?|included|enrolled|recruited|comprised|consisted of|样本量\s*(?:为|=|:)?)\s*(\d{2,6})\b",
            re.I,
        ),
    ),
    ("sample_size", re.compile(r"\b(\d{2,6})\s+(?:participants|patients|subjects|cases)\b", re.I)),
    (
        "sample_size",
        re.compile(
            r"\b(?:data (?:from|of)|included|enrolled|recruited|tested|analysed|analyzed|comprised|consisted of)\s+(\d{2,6})\s+samples\b",
            re.I,
        ),
    ),
]


def _window(text: str, start: int, end: int, radius: int = 140) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].split())


def _raw_text(material: dict[str, Any], excerpt: str = "") -> str:
    raw = material.get("raw_fields") or {}
    parts = [
        excerpt,
        raw.get("abstract", ""),
        raw.get("summary", ""),
        raw.get("fulltext_excerpt", ""),
        raw.get("result_summary", ""),
        raw.get("full_visible_text", ""),
    ]
    sections = raw.get("abstract_sections") or []
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, dict):
                parts.append(str(section.get("text") or ""))
    return "\n".join(str(part) for part in parts if part)


def _overlaps_reserved_span(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    return any(start < reserved_end and end > reserved_start for reserved_start, reserved_end in spans)


def _is_non_diagnostic_rate_context(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 32) : start]
    if re.search(
        r"(?:\b(?:analytical|engineering|technical|sensor|instrumental|methodological)"
        r"(?:[-\s]+[a-z][a-z0-9-]*){0,3}|\bhigh[-\s])\s*$",
        prefix,
        re.I,
    ):
        return True
    if re.search(r"(?:分析|工程|技术|传感器|高)(?:[\u4e00-\u9fff]{0,8})?\s*$", prefix):
        return True
    suffix = text[end : end + 24]
    return bool(re.match(r"\s*(?:pH|[kM]?Ω|ohms?\b)", suffix, re.I))


def _append_metric_fact(
    facts: list[MetricFact],
    seen: set[tuple[str, str, str]],
    *,
    metric_type: str,
    value: str,
    text: str,
    start: int,
    end: int,
    material: dict[str, Any],
    evidence_card_id: str,
) -> None:
    normalized_value = " ".join(str(value or "").split())
    evidence = _window(text, start, end)
    key = (metric_type, normalized_value, evidence[:80])
    if not normalized_value or key in seen:
        return
    seen.add(key)
    facts.append(
        MetricFact(
            metric_type=metric_type,
            value=normalized_value,
            excerpt=evidence,
            evidence_card_id=evidence_card_id,
            material_id=str(material.get("material_id") or ""),
            source_location=str(
                material.get("extracted_text_path")
                or material.get("content_snapshot_path")
                or "raw_fields"
            ),
            sample_type=str((material.get("raw_fields") or {}).get("sample_type") or ""),
            platform=str((material.get("raw_fields") or {}).get("platform") or ""),
            reference_standard=str(
                (material.get("raw_fields") or {}).get("reference_standard") or ""
            ),
        )
    )


def extract_metric_facts(
    material: dict[str, Any],
    *,
    evidence_card_id: str = "",
    excerpt: str = "",
) -> list[MetricFact]:
    text = _raw_text(material, excerpt)
    if not text:
        return []
    facts: list[MetricFact] = []
    seen: set[tuple[str, str, str]] = set()
    reserved_spans: list[tuple[int, int]] = []

    for match in PAIRED_RATE_PATTERN.finditer(text):
        if _is_non_diagnostic_rate_context(text, match.start(), match.end()):
            continue
        reserved_spans.append(match.span())
        for metric_type, group_index in [("sensitivity", 1), ("specificity", 2)]:
            _append_metric_fact(
                facts,
                seen,
                metric_type=metric_type,
                value=match.group(group_index),
                text=text,
                start=match.start(),
                end=match.end(),
                material=material,
                evidence_card_id=evidence_card_id,
            )

    for match in SHARED_RATE_PATTERN.finditer(text):
        if _overlaps_reserved_span(match.start(), match.end(), reserved_spans):
            continue
        if _is_non_diagnostic_rate_context(text, match.start(), match.end()):
            continue
        reserved_spans.append(match.span())
        for metric_type in ["sensitivity", "specificity"]:
            _append_metric_fact(
                facts,
                seen,
                metric_type=metric_type,
                value=match.group(1),
                text=text,
                start=match.start(),
                end=match.end(),
                material=material,
                evidence_card_id=evidence_card_id,
            )

    for metric_type, pattern in METRIC_PATTERNS:
        for match in pattern.finditer(text):
            if _overlaps_reserved_span(match.start(), match.end(), reserved_spans):
                continue
            if metric_type in {"sensitivity", "specificity"} and _is_non_diagnostic_rate_context(
                text, match.start(), match.end()
            ):
                continue
            _append_metric_fact(
                facts,
                seen,
                metric_type=metric_type,
                value=match.group(1),
                text=text,
                start=match.start(),
                end=match.end(),
                material=material,
                evidence_card_id=evidence_card_id,
            )
            if len(facts) >= 20:
                return facts
    return facts
