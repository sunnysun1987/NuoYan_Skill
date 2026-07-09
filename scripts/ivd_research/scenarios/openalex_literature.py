import json
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from ivd_research.models import DownloadFile, FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso


OPENALEX_WORKS_URL = "https://api.openalex.org/works"
USER_AGENT = "NuoYan-Skill/2.0 (IVD feasibility evidence collection; contact local user)"
DEFAULT_RETMAX = 20


def collect(task_id, task_dir, params):
    query = str(params.get("query", "")).strip()
    material_id = str(params.get("material_id", "MAT-000000"))
    task_dir = Path(task_dir)
    retmax = _safe_int(params.get("retmax"), DEFAULT_RETMAX)
    if not query:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh="OpenAlex 检索缺少关键词，请先确认英文关键词或项目关键词池。",
        )

    try:
        payload, raw_text, url = openalex_search(
            query,
            retmax=retmax,
            date_range=params.get("date_range"),
        )
    except Exception as exc:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"OpenAlex 检索失败：{exc}",
        )

    works = payload.get("results") or []
    raw_path = _save_raw_text(
        task_dir,
        f"{material_id}_openalex_search.json",
        raw_text,
    )
    if not works:
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"OpenAlex 未查询到与“{query}”匹配的公开结果。",
        )

    materials: list[Material] = []
    for index, work in enumerate(works[:retmax], start=1):
        current_material_id = material_id if len(works[:retmax]) == 1 else f"{material_id}-{index:03d}"
        text_path = _save_literature_text(
            task_dir,
            f"{current_material_id}_openalex_{_work_id_suffix(work)}.txt",
            format_openalex_text(work, query),
        )
        pdf_url = _best_pdf_url(work)
        download_files: list[DownloadFile] = []
        download_status = "not_available"
        if pdf_url:
            download_status = "available_not_downloaded"
            download_files = [
                DownloadFile(
                    original_filename=f"{current_material_id}_openalex_source.pdf",
                    stored_filename="",
                    relative_path="",
                    source_url=pdf_url,
                    status="available_not_downloaded",
                )
            ]
        material = Material(
            material_id=current_material_id,
            task_id=task_id,
            source_scenario="openalex_literature",
            material_type="literature",
            title=work.get("display_name") or work.get("title") or f"OpenAlex 文献 {index}",
            source_url=_best_landing_url(work),
            search_keyword_or_query=query,
            collection_path={
                "scenario_id": "openalex_literature",
                "query": query,
                "openalex_search_raw": raw_path,
                "openalex_api_url": url,
                "list_index": index,
                "retmax": retmax,
            },
            collection_time=now_iso(),
            adapter_id="openalex_literature",
            adapter_version="2.0.0",
            raw_fields={
                "source_database": "OpenAlex",
                "query": query,
                "openalex_id": work.get("id", ""),
                "doi": _strip_doi(work.get("doi", "")),
                "pmid": _strip_pubmed_url((work.get("ids") or {}).get("pmid", "")),
                "pmcid": _strip_pmc_url((work.get("ids") or {}).get("pmcid", "")),
                "journal": _source_name(work),
                "publication_year": work.get("publication_year", ""),
                "publication_date": work.get("publication_date", ""),
                "type": work.get("type", ""),
                "cited_by_count": work.get("cited_by_count", 0),
                "is_oa": (work.get("open_access") or {}).get("is_oa", False),
                "oa_status": (work.get("open_access") or {}).get("oa_status", ""),
                "pdf_url": pdf_url,
                "landing_page_url": _best_landing_url(work),
                "abstract": _abstract_from_inverted_index(work.get("abstract_inverted_index")),
                "concepts": [
                    concept.get("display_name", "")
                    for concept in (work.get("concepts") or [])[:12]
                    if concept.get("display_name")
                ],
                "authorships": _author_names(work),
                "search_count": (payload.get("meta") or {}).get("count", ""),
            },
            download_status=download_status,
            download_files=download_files,
            extracted_text_status="completed" if text_path else "not_attempted",
            extracted_text_path=text_path,
            content_snapshot_path=raw_path,
            possible_duplicate_keys=_duplicate_keys(work),
        )
        materials.append(material)

    return ScenarioResult(
        status="completed",
        materials=materials,
        message_zh=f"OpenAlex 检索完成，解析文献 {len(materials)} 条。",
    )


def openalex_search(query: str, *, retmax: int, date_range: Any = None) -> tuple[dict[str, Any], str, str]:
    params = {
        "search": query,
        "per-page": str(retmax),
    }
    date_filter = _date_filter(date_range)
    if date_filter:
        params["filter"] = date_filter
    url = f"{OPENALEX_WORKS_URL}?{urlencode(params)}"
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.json(), response.text, url
    except Exception:
        raw_text = _curl_get(url)
        return json.loads(raw_text), raw_text, url


def _curl_get(url: str) -> str:
    completed = subprocess.run(
        ["curl", "-fsSL", "--max-time", "35", "-A", USER_AGENT, url],
        check=False,
        capture_output=True,
        text=True,
        timeout=40,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "").strip() or f"curl exit {completed.returncode}")
    return completed.stdout


def _save_raw_text(task_dir: Path, filename: str, content: str) -> str:
    raw_dir = task_dir / "downloads" / "literature" / "openalex"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(task_dir))


def _save_literature_text(task_dir: Path, filename: str, content: str) -> str:
    text_dir = task_dir / "extracted_text" / "literature"
    text_dir.mkdir(parents=True, exist_ok=True)
    path = text_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path.relative_to(task_dir))


def format_openalex_text(work: dict[str, Any], query: str) -> str:
    raw_abstract = _abstract_from_inverted_index(work.get("abstract_inverted_index"))
    lines = [
        "来源：OpenAlex",
        f"检索式：{query}",
        f"OpenAlex ID：{work.get('id', '')}",
        f"标题：{work.get('display_name') or work.get('title') or ''}",
        f"作者：{'；'.join(_author_names(work))}",
        f"期刊/来源：{_source_name(work)}",
        f"发表日期：{work.get('publication_date', '')}",
        f"发表年份：{work.get('publication_year', '')}",
        f"DOI：{_strip_doi(work.get('doi', ''))}",
        f"PMID：{_strip_pubmed_url((work.get('ids') or {}).get('pmid', ''))}",
        f"PMCID：{_strip_pmc_url((work.get('ids') or {}).get('pmcid', ''))}",
        f"开放获取状态：{(work.get('open_access') or {}).get('oa_status', '')}",
        f"PDF链接：{_best_pdf_url(work)}",
        f"落地页：{_best_landing_url(work)}",
        f"被引次数：{work.get('cited_by_count', 0)}",
        f"主题概念：{'；'.join(concept.get('display_name', '') for concept in (work.get('concepts') or [])[:12] if concept.get('display_name'))}",
        "",
        "摘要：",
        raw_abstract or "OpenAlex 未返回摘要。需通过 DOI、PubMed、PMC 或出版社页面补充全文。",
    ]
    return "\n".join(lines)


def _abstract_from_inverted_index(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in index.items():
        if not isinstance(indexes, list):
            continue
        for position in indexes:
            if isinstance(position, int):
                positions.append((position, word))
    return " ".join(word for _, word in sorted(positions))


def _source_name(work: dict[str, Any]) -> str:
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    if source.get("display_name"):
        return source["display_name"]
    host = work.get("host_venue") or {}
    return host.get("display_name", "")


def _best_pdf_url(work: dict[str, Any]) -> str:
    for container in [
        work.get("best_oa_location") or {},
        work.get("primary_location") or {},
    ]:
        if container.get("pdf_url"):
            return container["pdf_url"]
    content_urls = work.get("content_urls") or {}
    return content_urls.get("pdf", "")


def _best_landing_url(work: dict[str, Any]) -> str:
    for container in [
        work.get("primary_location") or {},
        work.get("best_oa_location") or {},
    ]:
        if container.get("landing_page_url"):
            return container["landing_page_url"]
    return work.get("doi") or work.get("id", "")


def _author_names(work: dict[str, Any]) -> list[str]:
    names = []
    for item in work.get("authorships") or []:
        author = item.get("author") or {}
        if author.get("display_name"):
            names.append(author["display_name"])
    return names[:12]


def _strip_doi(value: str) -> str:
    return str(value or "").replace("https://doi.org/", "").strip()


def _strip_pubmed_url(value: str) -> str:
    return str(value or "").rstrip("/").split("/")[-1] if value else ""


def _strip_pmc_url(value: str) -> str:
    raw = str(value or "").rstrip("/").split("/")[-1] if value else ""
    return raw if raw.upper().startswith("PMC") else raw


def _work_id_suffix(work: dict[str, Any]) -> str:
    return str(work.get("id", "")).rstrip("/").split("/")[-1] or "work"


def _duplicate_keys(work: dict[str, Any]) -> list[str]:
    keys = []
    for value in [
        work.get("id", ""),
        _strip_doi(work.get("doi", "")),
        _strip_pubmed_url((work.get("ids") or {}).get("pmid", "")),
        _strip_pmc_url((work.get("ids") or {}).get("pmcid", "")),
    ]:
        if value:
            keys.append(str(value).lower())
    return keys


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _date_filter(date_range: Any) -> str:
    if not date_range:
        return ""
    start = ""
    end = ""
    if isinstance(date_range, dict):
        start = str(date_range.get("start") or date_range.get("from") or "").strip()
        end = str(date_range.get("end") or date_range.get("to") or "").strip()
    elif isinstance(date_range, str) and "TO" in date_range:
        left, right = date_range.split("TO", 1)
        start = left.strip(" []")
        end = right.strip(" []")
    if not start or not end:
        return ""
    return f"from_publication_date:{start},to_publication_date:{end}"
