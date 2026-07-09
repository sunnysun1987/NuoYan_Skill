from __future__ import annotations

from typing import Any


CRITICAL_STATUSES = {
    "collection_failed",
    "permission_required",
    "needs_login",
    "download_failed",
    "parse_failed",
}

OPTIONAL_NOT_STARTED_SCENARIOS = {
    "local_import",
    "task_intake",
}

SCENARIO_FALLBACK_MATERIAL_TYPES = {
    "cmde_regulatory": {"regulatory"},
    "nmpa_competitor": {"competitor"},
    "standards_current": {"standard"},
    "patenthub_patents": {"patent"},
    "pubmed_literature": {"literature"},
    "pmc_fulltext": {"literature"},
    "openalex_literature": {"literature"},
    "yiigle_fulltext": {"literature"},
    "yiigle_zhjyyxzz": {"literature"},
    "yiigle_zhsjkzz": {"literature"},
    "cma_lab_management": {"literature"},
    "wanfang_literature": {"literature"},
    "chinese_journal": {"literature"},
}

CHINESE_LITERATURE_SCENARIOS = {
    "yiigle_fulltext",
    "yiigle_zhjyyxzz",
    "yiigle_zhsjkzz",
    "cma_lab_management",
    "wanfang_literature",
    "chinese_journal",
}

CHINESE_LITERATURE_FALLBACK_SOURCES = {
    "web_search_public_fallback",
    "local_import",
    "import_local",
}

FALLBACK_REQUIRED_STATUSES = {
    "collection_failed",
    "permission_required",
    "needs_login",
    "download_failed",
    "parse_failed",
}


def scenario_needs_fallback(scenario: dict[str, Any]) -> bool:
    return scenario.get("status") in FALLBACK_REQUIRED_STATUSES


def has_fallback_record(scenario: dict[str, Any]) -> bool:
    """Detect whether a failed scenario records a fallback or next action.

    This intentionally accepts structured fields when future collectors add
    them, and also recognizes explicit wording in last_message so current
    adapters can participate without a schema migration.
    """
    raw_fields = scenario.get("raw_fields") or {}
    text = " ".join(
        str(value or "")
        for value in [
            scenario.get("last_message", ""),
            scenario.get("next_action", ""),
            raw_fields.get("fallback_action", ""),
            raw_fields.get("fallback_status", ""),
            raw_fields.get("next_action", ""),
        ]
    )
    keywords = [
        "fallback",
        "兜底",
        "重试",
        "改写检索式",
        "缩短检索式",
        "import-finding",
        "import_local",
        "浏览器",
        "browser",
        "site-profile",
        "record-site-observation",
        "用户提供",
        "人工补证",
        "补证",
    ]
    return any(keyword in text for keyword in keywords)


def material_coverage_type(material: dict[str, Any]) -> str:
    """Return the business coverage lane represented by a material.

    Imported or plugin-derived records may be stored as literature even when the
    source lane is really patent or regulatory.  Coverage detection therefore
    looks at explicit material_type first, then source metadata and titles.
    """
    material_type = str(material.get("material_type") or "").strip()
    if material_type in {"regulatory", "competitor", "standard", "patent"}:
        return material_type

    raw_fields = material.get("raw_fields") or {}
    haystack = " ".join(
        str(value or "")
        for value in [
            material.get("title", ""),
            material.get("source_url", ""),
            material.get("source_scenario", ""),
            material.get("evidence_lane", ""),
            raw_fields.get("evidence_lane", ""),
            raw_fields.get("source_database", ""),
            raw_fields.get("import_source", ""),
            raw_fields.get("identifier", ""),
            raw_fields.get("summary", ""),
        ]
    ).lower()
    if any(signal in haystack for signal in ["google patents", "patents.google", "patent_landscape", "专利"]):
        return "patent"
    if any(signal in haystack for signal in ["nmpa", "注册证", "医疗器械批准证明", "械注准"]):
        return "competitor"
    if any(signal in haystack for signal in ["yy/t", "gb/t", "标准", "std.samr", "行业标准"]):
        return "standard"
    if any(signal in haystack for signal in ["cmde", "指导原则", "审评报告", "注册审查"]):
        return "regulatory"
    if material_type == "literature":
        return "literature"
    return material_type or "unknown"


def fallback_materials_for_scenario(
    materials: list[dict[str, Any]],
    scenario_id: str,
) -> list[dict[str, Any]]:
    required_types = SCENARIO_FALLBACK_MATERIAL_TYPES.get(scenario_id, set())
    if not required_types:
        return []

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for material in materials:
        if material.get("source_scenario") == scenario_id:
            continue
        if material.get("failure_type"):
            continue
        coverage_type = material_coverage_type(material)
        if coverage_type not in required_types:
            continue
        if scenario_id in CHINESE_LITERATURE_SCENARIOS:
            source_scenario = str(material.get("source_scenario") or "")
            if source_scenario not in CHINESE_LITERATURE_FALLBACK_SOURCES:
                continue
        if not (material.get("title") or material.get("source_url") or material.get("extracted_text_path")):
            continue
        key = str(material.get("material_id") or material.get("source_url") or material.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        matches.append(material)
    return matches


def fallback_coverage_by_scenario(
    *,
    materials: list[dict[str, Any]],
    scenario_statuses: list[dict[str, Any]],
    required_scenario_ids: list[str] | set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    required_ids = set(required_scenario_ids or [])
    coverage: dict[str, list[dict[str, Any]]] = {}
    for scenario in scenario_statuses:
        scenario_id = str(scenario.get("scenario_id") or "")
        if required_ids and scenario_id not in required_ids:
            continue
        if scenario.get("status") not in CRITICAL_STATUSES | {"no_results", "not_started"}:
            continue
        fallback_materials = fallback_materials_for_scenario(materials, scenario_id)
        if fallback_materials:
            coverage[scenario_id] = fallback_materials
    return coverage


def build_collection_alerts(
    *,
    materials: list[dict[str, Any]],
    evidence_cards: list[dict[str, Any]],
    scenario_statuses: list[dict[str, Any]],
    required_scenario_ids: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Summarize collection quality risks for business-facing outputs."""
    required_ids = set(required_scenario_ids or [])
    fallback_coverage = fallback_coverage_by_scenario(
        materials=materials,
        scenario_statuses=scenario_statuses,
        required_scenario_ids=required_ids,
    )
    failed = [
        scenario
        for scenario in scenario_statuses
        if scenario.get("status") in CRITICAL_STATUSES
        and (not required_ids or scenario.get("scenario_id") in required_ids)
    ]
    fallback_missing = [
        scenario
        for scenario in scenario_statuses
        if scenario_needs_fallback(scenario) and not has_fallback_record(scenario)
        and (not required_ids or scenario.get("scenario_id") in required_ids)
    ]
    no_results = [
        scenario
        for scenario in scenario_statuses
        if scenario.get("status") == "no_results"
        and (not required_ids or scenario.get("scenario_id") in required_ids)
    ]
    not_started = [
        scenario
        for scenario in scenario_statuses
        if scenario.get("status") == "not_started"
        and scenario.get("scenario_id") not in OPTIONAL_NOT_STARTED_SCENARIOS
        and (not required_ids or scenario.get("scenario_id") in required_ids)
    ]
    completed = [
        scenario
        for scenario in scenario_statuses
        if scenario.get("status") == "completed"
        and (not required_ids or scenario.get("scenario_id") in required_ids)
    ]

    critical_messages: list[str] = []
    if not materials:
        critical_messages.append(
            "本次任务未登记任何材料。该状态不能解释为“未检索到证据”，应优先检查采集链路、网络、权限或检索式。"
        )
    if not evidence_cards:
        critical_messages.append(
            "本次任务未生成任何证据卡，报告不能支撑立项判断。"
        )
    for scenario in failed:
        label = scenario.get("label_zh") or scenario.get("scenario_id")
        status = scenario.get("status")
        message = scenario.get("last_message") or "未记录失败原因。"
        critical_messages.append(f"{label} 状态为 {status}：{message}")
    for scenario in fallback_missing:
        label = scenario.get("label_zh") or scenario.get("scenario_id")
        critical_messages.append(
            f"{label} 失败后缺少兜底动作记录。必须记录重试、公开来源导入、浏览器观察或人工补证任务。"
        )

    warning_messages: list[str] = []
    for scenario in no_results:
        label = scenario.get("label_zh") or scenario.get("scenario_id")
        message = scenario.get("last_message") or "该场景返回 no_results，但缺少检索说明。"
        fallback_materials = fallback_coverage.get(str(scenario.get("scenario_id") or ""), [])
        if fallback_materials:
            warning_messages.append(
                f"{label} 原通道未命中：{message}；系统已匹配 {len(fallback_materials)} 条同类型公开兜底材料，仍需人工复核官方字段或来源完整性。"
            )
        else:
            warning_messages.append(f"{label} 未命中结果：{message}")
    for scenario in failed:
        fallback_materials = fallback_coverage.get(str(scenario.get("scenario_id") or ""), [])
        if fallback_materials:
            label = scenario.get("label_zh") or scenario.get("scenario_id")
            warning_messages.append(
                f"{label} 官方/原始通道未闭环，但已匹配 {len(fallback_materials)} 条同类型公开兜底材料；正式立项前仍需关闭原通道核验。"
            )
    if not_started:
        warning_messages.append(
            "仍有未启动采集场景："
            + "；".join(
                str(scenario.get("label_zh") or scenario.get("scenario_id"))
                for scenario in not_started
            )
        )

    if critical_messages:
        level = "critical"
        if materials and evidence_cards:
            headline = "采集异常：已形成部分证据，但仍存在关键来源失败"
        else:
            headline = "采集异常：当前报告没有形成可用证据基础"
    elif warning_messages:
        level = "warning"
        headline = "采集不完整：当前报告存在待补证来源"
    else:
        level = "ok"
        headline = "采集状态正常"

    return {
        "level": level,
        "headline": headline,
        "material_count": len(materials),
        "evidence_card_count": len(evidence_cards),
        "completed_count": len(completed),
        "failed_count": len(failed),
        "fallback_missing_count": len(fallback_missing),
        "fallback_covered_count": len(fallback_coverage),
        "fallback_coverage": fallback_coverage,
        "no_results_count": len(no_results),
        "not_started_count": len(not_started),
        "critical_messages": critical_messages,
        "warning_messages": warning_messages,
        "failed_scenarios": failed,
        "fallback_missing_scenarios": fallback_missing,
        "no_results_scenarios": no_results,
        "not_started_scenarios": not_started,
    }
