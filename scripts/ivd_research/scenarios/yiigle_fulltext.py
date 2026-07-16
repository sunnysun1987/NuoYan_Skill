import json
import html
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

from ivd_research.models import FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso

from .registry import get_scenario
from .site_collect import USER_AGENT, collect_yiigle_journal, save_text


SCENARIO_ID = "yiigle_fulltext"
SUBJECT_ZH = "中华医学期刊全文数据库"
API_URL = "https://www.yiigle.com/apiVue/search/searchList"
DETAIL_URL_TEMPLATE = "https://rs.yiigle.com/cmaid/{art_id}"
DEFAULT_RETMAX = 20


def adapter():
    return get_scenario(SCENARIO_ID)


def collect(task_id, task_dir, params):
    """Collect cross-journal Yiigle metadata through its public search API."""
    query = str(params.get("query", "") or "").strip()
    keyword = str(params.get("base_keyword", "") or query).strip()
    material_id = str(params.get("material_id", "MAT-000000"))
    task_dir = Path(task_dir)
    if not keyword:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=f"{SUBJECT_ZH} 缺少检索关键词，请先确认关键词池。",
        )

    retmax = _safe_int(params.get("retmax"), DEFAULT_RETMAX)
    try:
        payload, raw_text = yiigle_api_search(keyword, retmax=retmax)
        result = parse_yiigle_api_result(
            payload,
            task_id=task_id,
            task_dir=task_dir,
            material_id=material_id,
            query=query,
            keyword=keyword,
            raw_text=raw_text,
            date_range=params.get("literature_date_range"),
        )
        if result.status != "collection_failed":
            return result
    except Exception:
        pass

    return collect_yiigle_journal(
        task_id=task_id,
        task_dir=task_dir,
        params=params,
        scenario_id=SCENARIO_ID,
        journal_url="https://www.yiigle.com/",
        subject_zh=SUBJECT_ZH,
        search_url_template="https://www.yiigle.com/searchMobile?ind=3&q={query}",
    )


def yiigle_api_search(keyword: str, *, retmax: int = DEFAULT_RETMAX) -> tuple[dict[str, Any], str]:
    body = {
        "type": "",
        "sortField": "",
        "page": 1,
        "searchType": "pt",
        "pageSize": retmax,
        "queryString": keyword,
        "query": "",
        "searchText": keyword,
        "searchLog": keyword,
        "isAggregations": "N",
        "logintoken": None,
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.yiigle.com",
        "Referer": "https://www.yiigle.com/Paper/Search",
    }
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.post(API_URL, json=body, headers=headers)
        response.raise_for_status()
        return response.json(), response.text
    except Exception:
        completed = subprocess.run(
            [
                "curl",
                "-fsSL",
                "--max-time",
                "35",
                "-A",
                USER_AGENT,
                "-H",
                "Content-Type: application/json;charset=UTF-8",
                "-H",
                "Origin: https://www.yiigle.com",
                "-H",
                "Referer: https://www.yiigle.com/Paper/Search",
                "--data",
                json.dumps(body, ensure_ascii=False),
                API_URL,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=40,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or "").strip() or f"curl exit {completed.returncode}")
        return json.loads(completed.stdout), completed.stdout


def parse_yiigle_api_result(
    payload: dict[str, Any],
    *,
    task_id: str,
    task_dir: Path,
    material_id: str,
    query: str,
    keyword: str,
    raw_text: str,
    date_range: Any = None,
) -> ScenarioResult:
    if payload.get("code") != 200:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{SUBJECT_ZH} 官方检索接口返回异常状态：{payload.get('code')}。",
        )
    result = (payload.get("data") or {}).get("result") or {}
    rows = result.get("infos") or []
    if not isinstance(rows, list):
        rows = []
    rows = [row for row in rows if isinstance(row, dict) and _within_date_range(row, date_range)]
    search_total = int(result.get("searchTotal") or 0)
    if not rows:
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{SUBJECT_ZH} 官方检索接口未返回与“{keyword}”匹配且在确认时间范围内的文献。",
        )

    raw_dir = task_dir / "downloads" / "literature" / SCENARIO_ID
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{material_id}_{SCENARIO_ID}_search_api.json"
    raw_path.write_text(raw_text, encoding="utf-8")
    raw_relative = str(raw_path.relative_to(task_dir))

    materials: list[Material] = []
    for index, row in enumerate(rows, start=1):
        current_id = material_id if len(rows) == 1 else f"{material_id}-{index:03d}"
        art_id = str(row.get("artId") or "")
        source_url = str(row.get("artUrl") or row.get("artMobileUrl") or "")
        if not source_url and art_id:
            source_url = DETAIL_URL_TEMPLATE.format(art_id=art_id)
        title = _plain_text(
            row.get("artTitle") or row.get("artDropTitle") or f"中华医学期刊文献 {index}"
        )
        abstract = _plain_text(row.get("artAbstract") or "", preserve_lines=True)
        text_path = save_text(
            task_dir,
            "literature",
            f"{current_id}_{SCENARIO_ID}.txt",
            _format_text(row, title=title, abstract=abstract, source_url=source_url),
        )
        doi = str(row.get("artDoi") or "").strip()
        duplicate_keys = [f"doi:{doi.lower()}"] if doi else []
        if art_id:
            duplicate_keys.append(f"yiigle:{art_id}")
        materials.append(
            Material(
                material_id=current_id,
                task_id=task_id,
                source_scenario=SCENARIO_ID,
                material_type="literature",
                title=title,
                source_url=source_url or "https://www.yiigle.com/",
                search_keyword_or_query=query or keyword,
                collection_path={
                    "scenario_id": SCENARIO_ID,
                    "api_url": API_URL,
                    "query": keyword,
                    "search_snapshot": raw_relative,
                    "list_index": index,
                },
                collection_time=now_iso(),
                adapter_id=SCENARIO_ID,
                adapter_version="0.5.0",
                raw_fields={
                    "source_database": SUBJECT_ZH,
                    "art_id": art_id,
                    "doi": doi,
                    "journal": row.get("journalCn") or row.get("journalEn") or "",
                    "publication_date": row.get("artPubDate") or "",
                    "publication_year": row.get("artPubYear") or "",
                    "authors": row.get("authorNames") or [],
                    "keywords": row.get("keywords") or row.get("artificialKeywords") or [],
                    "abstract": abstract,
                    "document_type": row.get("docType") or "",
                    "volume": row.get("vol") or "",
                    "issue": row.get("issue") or "",
                    "start_page": row.get("startPage") or "",
                    "end_page": row.get("endPage") or "",
                    "search_total": search_total,
                    "fulltext_status": "metadata_and_abstract",
                    "pdf_status": "not_checked",
                },
                download_status="not_attempted",
                extracted_text_status="completed",
                extracted_text_path=text_path,
                content_snapshot_path=raw_relative,
                possible_duplicate_keys=duplicate_keys,
            )
        )

    return ScenarioResult(
        status="completed",
        materials=materials,
        message_zh=(
            f"{SUBJECT_ZH} 官方检索接口命中 {search_total} 条，"
            f"当前批次解析并保存 {len(materials)} 条题录与摘要。"
        ),
    )


def _within_date_range(row: dict[str, Any], date_range: Any) -> bool:
    if not isinstance(date_range, dict):
        return True
    start = str(date_range.get("start") or date_range.get("from") or "")[:4]
    end = str(date_range.get("end") or date_range.get("to") or "")[:4]
    year = str(row.get("artPubYear") or "")[:4]
    if not year.isdigit():
        return True
    return (not start or year >= start) and (not end or year <= end)


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, 50))


def _plain_text(value: Any, *, preserve_lines: bool = False) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    if preserve_lines:
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return " ".join(text.split())


def _format_text(row: dict[str, Any], *, title: str, abstract: str, source_url: str) -> str:
    authors = "；".join(str(item) for item in row.get("authorNames") or [])
    keywords = "；".join(
        str(item) for item in (row.get("keywords") or row.get("artificialKeywords") or [])
    )
    return "\n".join(
        [
            f"题名：{title}",
            f"期刊：{row.get('journalCn') or row.get('journalEn') or ''}",
            f"作者：{authors}",
            f"发表时间：{row.get('artPubDate') or row.get('artPubYear') or ''}",
            f"DOI：{row.get('artDoi') or ''}",
            f"关键词：{keywords}",
            f"来源：{source_url}",
            "",
            "Abstract：",
            abstract,
        ]
    )
