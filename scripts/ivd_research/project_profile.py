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
    "multiplex",
]

HCG_TERMS = [
    "beta-hcg",
    "β-hcg",
    "β hcg",
    "hcg",
    "human chorionic gonadotropin",
    "绒毛膜促性腺激素",
    "妊娠",
    "pregnancy",
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
    values = [
        topic_for_profile,
        primary_query,
        confirmations.get("english_keywords", ""),
        confirmations.get("chinese_synonyms", ""),
        confirmations.get("intended_use", ""),
        confirmations.get("sample_type", ""),
        confirmations.get("platform", ""),
        confirmations.get("methodology", ""),
        confirmations.get("competitor_scope", ""),
        confirmations.get("patent_scope", ""),
    ]
    return " ".join(str(value or "") for value in values).lower()


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
    if any(term in text for term in HCG_TERMS):
        return "hcg"
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
