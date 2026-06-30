from __future__ import annotations

import re
from typing import Any

from ivd_research.models import MetricFact


METRIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AUC", re.compile(r"\b(?:AUC|area under (?:the )?curve)\b[^.;，。]{0,80}?([0-1](?:\.\d+)?)", re.I)),
    ("sensitivity", re.compile(r"\b(?:sensitivity|敏感度|灵敏度)\b[^.;，。]{0,80}?(\d{1,3}(?:\.\d+)?\s*%?|0\.\d+)", re.I)),
    ("specificity", re.compile(r"\b(?:specificity|特异性)\b[^.;，。]{0,80}?(\d{1,3}(?:\.\d+)?\s*%?|0\.\d+)", re.I)),
    ("cutoff", re.compile(r"\b(?:cut-?off|threshold|截断值|临界值)\b[^.;，。]{0,80}?([<>≤≥]?\s*\d+(?:\.\d+)?\s*[A-Za-z/%μµ]*)", re.I)),
    ("HR", re.compile(r"\bHR\b[^.;，。]{0,50}?(\d+(?:\.\d+)?)", re.I)),
    ("OR", re.compile(r"\bOR\b[^.;，。]{0,50}?(\d+(?:\.\d+)?)", re.I)),
    ("CI", re.compile(r"\b(?:95%\s*)?CI\b[^.;，。]{0,60}?([0-9.]+\s*[-–,]\s*[0-9.]+)", re.I)),
    ("sample_size", re.compile(r"\b(?:n\s*=|sample size|participants|patients|subjects|样本量)\b[^.;，。]{0,50}?(\d{2,6})", re.I)),
    ("sample_size", re.compile(r"\b(\d{2,6})\s+(?:participants|patients|subjects|samples|cases)\b", re.I)),
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
    for metric_type, pattern in METRIC_PATTERNS:
        for match in pattern.finditer(text):
            value = str(match.group(1) or "").strip()
            evidence = _window(text, match.start(), match.end())
            key = (metric_type, value, evidence[:80])
            if not value or key in seen:
                continue
            seen.add(key)
            facts.append(
                MetricFact(
                    metric_type=metric_type,
                    value=value,
                    excerpt=evidence,
                    evidence_card_id=evidence_card_id,
                    material_id=str(material.get("material_id") or ""),
                    source_location=str(material.get("extracted_text_path") or material.get("content_snapshot_path") or "raw_fields"),
                    sample_type=str((material.get("raw_fields") or {}).get("sample_type") or ""),
                    platform=str((material.get("raw_fields") or {}).get("platform") or ""),
                    reference_standard=str((material.get("raw_fields") or {}).get("reference_standard") or ""),
                )
            )
            if len(facts) >= 20:
                return facts
    return facts
