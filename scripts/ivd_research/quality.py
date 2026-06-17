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


def build_collection_alerts(
    *,
    materials: list[dict[str, Any]],
    evidence_cards: list[dict[str, Any]],
    scenario_statuses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize collection quality risks for business-facing outputs."""
    failed = [
        scenario
        for scenario in scenario_statuses
        if scenario.get("status") in CRITICAL_STATUSES
    ]
    fallback_missing = [
        scenario
        for scenario in scenario_statuses
        if scenario_needs_fallback(scenario) and not has_fallback_record(scenario)
    ]
    no_results = [
        scenario for scenario in scenario_statuses if scenario.get("status") == "no_results"
    ]
    not_started = [
        scenario
        for scenario in scenario_statuses
        if scenario.get("status") == "not_started"
        and scenario.get("scenario_id") not in OPTIONAL_NOT_STARTED_SCENARIOS
    ]
    completed = [
        scenario for scenario in scenario_statuses if scenario.get("status") == "completed"
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
        warning_messages.append(f"{label} 未命中结果：{message}")
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
        "no_results_count": len(no_results),
        "not_started_count": len(not_started),
        "critical_messages": critical_messages,
        "warning_messages": warning_messages,
        "failed_scenarios": failed,
        "fallback_missing_scenarios": fallback_missing,
        "no_results_scenarios": no_results,
        "not_started_scenarios": not_started,
    }
