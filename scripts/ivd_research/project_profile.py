from __future__ import annotations

import re
from typing import Any


COMMON_FORMAL_SCENARIOS = [
    "cmde_regulatory",
    "nmpa_competitor",
    "standards_current",
    "patenthub_patents",
    "yiigle_zhjyyxzz",
    "cma_lab_management",
    "pubmed_literature",
    "pmc_fulltext",
    "openalex_literature",
    "yiigle_fulltext",
]

NEUROLOGY_FORMAL_SCENARIOS = [
    "yiigle_zhsjkzz",
]

AD_FORMAL_SCENARIOS = [
    "wiley_alz",
]

OPTIONAL_SCENARIOS = {
    "local_import",
    "task_intake",
    "life_science_research",
}

NETWORK_SENSITIVE_SCENARIOS = [
    "pubmed_literature",
    "pmc_fulltext",
    "openalex_literature",
]

AD_TERMS = [
    "alzheimer",
    "阿尔茨海默",
    "认知障碍",
    "痴呆",
    "mci",
    "p-tau",
    "ptau",
    "tau217",
    "tau181",
    "aβ",
    "abeta",
    "amyloid",
]

NEUROLOGY_TERMS = [
    *AD_TERMS,
    "神经",
    "cns",
    "neurology",
    "neurodegenerative",
    "neurological",
    "parkinson",
    "帕金森",
    "卒中",
    "stroke",
]

RESPIRATORY_TERMS = [
    "呼吸道",
    "甲型流感",
    "乙型流感",
    "甲流",
    "乙流",
    "influenza",
    "flu a",
    "flu b",
    "respiratory",
]

PROJECT_PROFILE_KEYS = [
    "primary_query",
    "english_keywords",
    "chinese_synonyms",
    "intended_use",
    "sample_type",
    "platform",
    "methodology",
    "competitor_scope",
    "patent_scope",
]

PROJECT_SUBJECT_STOP_TERMS = [
    "项目调研分析综述",
    "调研分析综述",
    "项目调研",
    "可行性调研",
    "体外诊断",
    "检测试剂盒",
    "测定试剂盒",
    "诊断试剂盒",
    "检测试剂",
    "测定试剂",
    "检测项目",
    "检测产品",
    "定量检测",
    "定性检测",
    "半定量检测",
    "定量",
    "定性",
    "半定量",
    "ivd",
    "test kit",
    "diagnostic kit",
    "assay kit",
]


def profile_text(source: Any) -> str:
    """Build a compact text profile from a task state or task dict."""
    if isinstance(source, dict):
        confirmations = source.get("confirmations") or {}
        topic = source.get("topic", "")
    else:
        confirmations = getattr(source, "confirmations", {}) or {}
        topic = getattr(source, "topic", "")
    primary_query = confirmations.get("primary_query", "")
    topic_for_profile = "" if primary_query else topic
    values = [topic_for_profile, *[confirmations.get(key, "") for key in PROJECT_PROFILE_KEYS]]
    return " ".join(str(value or "") for value in values).lower()


def has_confirmed_project_profile(confirmations: dict | None) -> bool:
    confirmations = confirmations or {}
    return any(str(confirmations.get(key, "") or "").strip() for key in PROJECT_PROFILE_KEYS)


def project_subject(source: Any, fallback: str = "目标检测项目") -> str:
    """Derive a display subject from confirmed fields without analyte-specific rules."""
    if isinstance(source, dict):
        confirmations = source.get("confirmations") or source
        topic = str(source.get("topic", "") or "")
    else:
        confirmations = getattr(source, "confirmations", {}) or {}
        topic = str(getattr(source, "topic", "") or "")

    synonyms = str(confirmations.get("chinese_synonyms", "") or "")
    for alias in re.split(r"[；;、，,|\n]+", synonyms):
        clean_alias = " ".join(alias.split()).strip(" /()（）")
        if clean_alias and len(clean_alias) <= 48:
            return clean_alias

    primary = str(confirmations.get("primary_query", "") or topic).strip()
    if not primary:
        return fallback

    marker_match = re.search(
        r"(?i)(?<![a-z0-9])(?:[a-z]+(?:[-_/][a-z0-9]+)+|[a-z]+\d+[a-z0-9-]*)(?![a-z0-9])",
        primary,
    )
    if marker_match:
        return marker_match.group(0)

    subject = re.sub(r"[（(][^）)]*(?:法|平台|检测|assay|method|platform)[^）)]*[）)]", " ", primary, flags=re.I)
    for term in PROJECT_SUBJECT_STOP_TERMS:
        subject = re.sub(re.escape(term), " ", subject, flags=re.I)
    subject = re.sub(r"[；;、，,。:：/|]+", " ", subject)
    subject = " ".join(subject.split()).strip(" -_()（）")
    return subject[:80] or fallback


def is_ad_project(source: Any) -> bool:
    text = profile_text(source)
    return any(term in text for term in AD_TERMS) or bool(re.search(r"\bad\b", text))


def is_neurology_project(source: Any) -> bool:
    text = profile_text(source)
    return any(term in text for term in NEUROLOGY_TERMS) or bool(re.search(r"\bad\b", text))


def project_domain(source: Any) -> str:
    text = profile_text(source)
    if is_ad_project(source):
        return "ad_biomarker"
    if is_neurology_project(source):
        return "neurology"
    if any(term in text for term in RESPIRATORY_TERMS):
        return "respiratory"
    return "generic_ivd"


def formal_scenarios_for(source: Any) -> list[str]:
    scenarios = list(COMMON_FORMAL_SCENARIOS)
    if is_neurology_project(source):
        scenarios.extend(NEUROLOGY_FORMAL_SCENARIOS)
    if is_ad_project(source):
        scenarios.extend(AD_FORMAL_SCENARIOS)
    return scenarios


def is_scenario_applicable(source: Any, scenario_id: str) -> bool:
    if scenario_id in OPTIONAL_SCENARIOS:
        return True
    return scenario_id in formal_scenarios_for(source)


def scenario_exclusion_message(source: Any, scenario_id: str) -> str:
    domain = project_domain(source)
    if scenario_id == "wiley_alz":
        return f"Wiley Alzheimer 文献属于 AD 专用信源；当前项目画像为 {domain}，已排除。"
    if scenario_id == "yiigle_zhsjkzz":
        return f"中华神经科杂志属于神经/认知方向专用中文信源；当前项目画像为 {domain}，已排除。"
    return f"该信源不适用于当前项目画像 {domain}，已排除。"
