from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .jsonl import read_jsonl
from .project_profile import formal_scenarios_for
from .quality import fallback_coverage_by_scenario


QUERY_SENSITIVE_SCENARIOS = {
    "cmde_regulatory",
    "standards_current",
    "pubmed_literature",
    "pmc_fulltext",
    "openalex_literature",
    "yiigle_fulltext",
    "yiigle_zhjyyxzz",
    "yiigle_zhsjkzz",
    "cma_lab_management",
    "wanfang_literature",
    "chinese_journal",
}

CORE_QUERY_ROLES = {
    "core_cn",
    "core_product_cn",
    "openalex_core_keywords",
    "pubmed_core_keywords",
    "pmc_core_keywords",
    "yiigle_fulltext_core_expression",
    "short_cn",
}

NO_RESULT_COMPARABLE_SOURCES = {
    "yiigle_fulltext": {
        "yiigle_zhjyyxzz",
        "cma_lab_management",
        "yiigle_zhsjkzz",
    },
}

LONG_QUERY_CHAR_THRESHOLD = 140
LONG_QUERY_TOKEN_THRESHOLD = 16


def build_source_quality_audit(
    task_dir: Path,
    *,
    task: dict[str, Any] | None = None,
    materials: list[dict[str, Any]] | None = None,
    scenario_statuses: list[dict[str, Any]] | None = None,
    required_scenario_ids: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    task_dir = Path(task_dir)
    if task is None:
        task = _read_json(task_dir / "task.json")
    if materials is None:
        materials = list(read_jsonl(task_dir / "data" / "materials.jsonl"))
    if scenario_statuses is None:
        scenario_statuses = list((task.get("scenario_statuses") or {}).values())
    required_ids = set(required_scenario_ids or formal_scenarios_for(task))
    statuses = {
        str(scenario.get("scenario_id") or ""): scenario
        for scenario in scenario_statuses
    }
    attempts_by_scenario = query_attempts_by_scenario(task_dir)
    fallback_coverage = fallback_coverage_by_scenario(
        materials=materials,
        scenario_statuses=scenario_statuses,
        required_scenario_ids=required_ids,
    )

    issues: list[dict[str, Any]] = []
    for scenario_id in sorted(required_ids):
        scenario = statuses.get(scenario_id)
        if not scenario:
            continue
        if scenario.get("status") != "no_results":
            continue
        if scenario_id not in QUERY_SENSITIVE_SCENARIOS:
            continue
        attempts = attempts_by_scenario.get(scenario_id, [])
        query_texts = _attempt_queries(attempts) or _queries_from_message(
            str(scenario.get("last_message") or "")
        )
        core_attempts = [
            attempt
            for attempt in attempts
            if str(attempt.get("query_role") or "") in CORE_QUERY_ROLES
        ]
        fallback_count = len(fallback_coverage.get(scenario_id, []))

        if not attempts:
            issues.append(
                _issue(
                    scenario,
                    severity="medium",
                    issue_type="missing_query_attempt_trace",
                    finding="该来源为 no_results，但未找到可追溯的多层检索尝试记录。",
                    evidence="场景状态缺少 query attempts 日志，无法证明已排除检索式过窄。",
                    recommendation="重新运行该来源，保留核心词、产品提示、宽业务词和原始检索式的尝试记录。",
                )
            )
        elif len({attempt.get("query") for attempt in attempts if attempt.get("query")}) <= 1:
            issues.append(
                _issue(
                    scenario,
                    severity="high",
                    issue_type="single_query_no_results",
                    finding="该来源只记录到一个检索层级即判定 no_results。",
                    evidence=_attempt_summary(attempts),
                    recommendation="至少执行核心词、宽业务词和原始检索式三个层级后，再保留 no_results 结论。",
                )
            )
        if attempts and not core_attempts:
            issues.append(
                _issue(
                    scenario,
                    severity="high",
                    issue_type="missing_core_query",
                    finding="该来源未记录核心词检索层级，存在假阴性风险。",
                    evidence=_attempt_summary(attempts),
                    recommendation="优先补跑核心词检索，再决定是否保留缺口。",
                )
            )
        if any(_is_long_query(query) for query in query_texts) and not core_attempts:
            issues.append(
                _issue(
                    scenario,
                    severity="high" if not fallback_count else "medium",
                    issue_type="overconstrained_query",
                    finding="该来源 no_results 可能由检索词过长或限定条件过多造成。",
                    evidence="；".join(query_texts[:2]),
                    recommendation="缩短为检测项目/靶标核心词，再按产品提示和方法学逐层扩展。",
                )
            )

    openalex = statuses.get("openalex_literature")
    if openalex and openalex.get("status") == "no_results":
        comparable_count = _material_count_for_sources(
            materials,
            {
                "pubmed_literature",
                "pmc_fulltext",
                "life_science_research",
            },
        )
        if comparable_count:
            attempts = attempts_by_scenario.get("openalex_literature", [])
            core_attempts = [
                attempt
                for attempt in attempts
                if str(attempt.get("query_role") or "") in CORE_QUERY_ROLES
            ]
            issues.append(
                _issue(
                    openalex,
                    severity="medium" if core_attempts else "high",
                    issue_type="cross_source_false_negative",
                    finding="OpenAlex 为 no_results，但 PubMed/PMC/LSR 已有相关文献或科学数据库材料，疑似检索策略假阴性。",
                    evidence=(
                        f"可比来源已有 {comparable_count} 条材料；"
                        + (_attempt_summary(attempts) if attempts else str(openalex.get("last_message") or ""))
                    ),
                    recommendation=(
                        "复核 OpenAlex 核心英文检索词和宽检索词；如未执行核心词层级，先补跑后再重建报告。"
                    ),
                )
            )

    for scenario_id, comparable_sources in NO_RESULT_COMPARABLE_SOURCES.items():
        scenario = statuses.get(scenario_id)
        if not scenario or scenario.get("status") != "no_results":
            continue
        comparable_count = _material_count_for_sources(materials, comparable_sources)
        if not comparable_count:
            continue
        attempts = attempts_by_scenario.get(scenario_id, [])
        core_attempts = [
            attempt
            for attempt in attempts
            if str(attempt.get("query_role") or "") in CORE_QUERY_ROLES
        ]
        issues.append(
            _issue(
                scenario,
                severity="medium" if core_attempts else "high",
                issue_type="cross_source_channel_mismatch",
                finding="该聚合来源为 no_results，但同体系的专门中文期刊来源已采集到相关材料。",
                evidence=(
                    f"可比中文来源已有 {comparable_count} 条材料；"
                    + (_attempt_summary(attempts) if attempts else str(scenario.get("last_message") or ""))
                ),
                recommendation=(
                    "复核聚合搜索页的结果链接结构、筛选条件和详情页解析规则；"
                    "在适配器闭环前保留该来源缺口，不能用专门期刊材料自动关闭。"
                ),
            )
        )

    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    if high_count:
        level = "critical"
        headline = f"采集质量审计发现 {high_count} 项高风险疑似假阴性。"
    elif medium_count:
        level = "warning"
        headline = f"采集质量审计发现 {medium_count} 项需要复核的检索追溯问题。"
    else:
        level = "ok"
        headline = "采集质量审计未发现高风险检索策略问题。"
    return {
        "level": level,
        "headline": headline,
        "issue_count": len(issues),
        "high_count": high_count,
        "medium_count": medium_count,
        "ready": high_count == 0,
        "issues": issues,
    }


def query_attempts_by_scenario(task_dir: Path) -> dict[str, list[dict[str, Any]]]:
    attempts: dict[str, list[dict[str, Any]]] = {}
    for event in read_jsonl(Path(task_dir) / "logs" / "events.jsonl"):
        scenario_id = str(event.get("scenario_id") or "")
        if not scenario_id:
            continue
        if event.get("event") == "scenario_query_attempts":
            rows = event.get("attempts") or []
            if isinstance(rows, list):
                attempts.setdefault(scenario_id, []).extend(
                    row for row in rows if isinstance(row, dict)
                )
        elif event.get("event") == "delivery_browser_workflow_ran" and event.get("attempted_query"):
            attempts.setdefault(scenario_id, []).append(
                {
                    "query_role": event.get("query_role", ""),
                    "query": event.get("attempted_query", ""),
                    "status": event.get("status", ""),
                    "material_count": event.get("material_count", 0),
                    "message_zh": event.get("message_zh", ""),
                }
            )
    return attempts


def _issue(
    scenario: dict[str, Any],
    *,
    severity: str,
    issue_type: str,
    finding: str,
    evidence: str,
    recommendation: str,
) -> dict[str, Any]:
    scenario_id = str(scenario.get("scenario_id") or "")
    return {
        "severity": severity,
        "status_level": "danger" if severity == "high" else "warn",
        "issue_type": issue_type,
        "scenario_id": scenario_id,
        "source": scenario.get("label_zh") or scenario_id,
        "finding": finding,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _attempt_queries(attempts: list[dict[str, Any]]) -> list[str]:
    queries: list[str] = []
    for attempt in attempts:
        query = " ".join(str(attempt.get("query") or "").split()).strip()
        if query and query not in queries:
            queries.append(query)
    return queries


def _queries_from_message(message: str) -> list[str]:
    matches = re.findall(r"“([^”]+)”", str(message or ""))
    return [" ".join(match.split()).strip() for match in matches if match.strip()]


def _is_long_query(query: str) -> bool:
    clean = " ".join(str(query or "").split())
    if len(clean) >= LONG_QUERY_CHAR_THRESHOLD:
        return True
    tokens = re.findall(r"[A-Za-z0-9α-ωΑ-ΩβΒτΤ\-]+|[\u4e00-\u9fff]+", clean)
    return len(tokens) >= LONG_QUERY_TOKEN_THRESHOLD


def _attempt_summary(attempts: list[dict[str, Any]], limit: int = 4) -> str:
    parts = []
    for attempt in attempts[:limit]:
        role = attempt.get("query_role") or "unknown"
        status = attempt.get("status") or "unknown"
        query = " ".join(str(attempt.get("query") or "").split())
        if len(query) > 120:
            query = query[:119].rstrip() + "..."
        parts.append(f"{role}/{status}: {query}")
    return "；".join(parts)


def _material_count_for_sources(
    materials: list[dict[str, Any]],
    source_scenarios: set[str],
) -> int:
    return sum(
        1
        for material in materials
        if material.get("source_scenario") in source_scenarios
        and material.get("material_type") == "literature"
        and not material.get("failure_type")
    )


def _read_json(path: Path) -> dict[str, Any]:
    import json

    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
