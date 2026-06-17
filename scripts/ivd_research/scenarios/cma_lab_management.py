import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .registry import get_scenario
from ivd_research.models import FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso

from .site_collect import (
    detect_restriction,
    download_public_pdf,
    fetch_html,
    page_text,
    post_html,
    save_snapshot,
    save_text,
)


SCENARIO_ID = "cma_lab_management"
MATERIAL_TYPE = "literature"
SUBJECT_ZH = "中华临床实验室管理电子杂志文献"
SEARCH_URL = "https://zhlcsysgldzzz.cma-cmc.com.cn/CN/searchresult"
NO_RESULT_MARKERS = ("没有找到", "没有找到相关文献", "暂无数据", "无检索结果", "未查询到", "No results")
VALIDATION_RULES = [
    "文献详情包含 DOI、标题、作者和摘要选项卡",
    "collection_failed",
    "no_results",
]
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s<>'\"，。；;]+", re.IGNORECASE)
DATE_RE = re.compile(r"(?:19|20)\d{2}(?:[-年]\d{1,2}(?:[-月]\d{1,2}日?)?)?")


def adapter():
    return get_scenario(SCENARIO_ID)


def build_search_sql(query: str) -> str:
    query = query.strip()
    return (
        f"(((((({query}[Title]) OR {query}[Abstract]) OR {query}[Keyword]) OR "
        f"{query}[Author]) OR {query}[AuthorCompany]) OR {query}[DOI]) AND 33[Journal])"
    )


def parse_cma_result_list(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, anchor in enumerate(soup.find_all("a", href=True), start=1):
        title = _clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "")
        if not title or not href or not _looks_like_article_link(href):
            continue

        detail_url = urljoin(base_url, href).split("#", 1)[0]
        article_key = _cma_article_key(detail_url)
        if article_key in seen:
            continue
        seen.add(article_key)

        container = anchor.find_parent(["article", "li", "tr", "div"]) or anchor.parent
        visible_text = _clean_text(container.get_text(" ", strip=True) if container else title)
        entries.append(
            {
                "title": title,
                "detail_url": detail_url,
                "list_index": index,
                "doi": _first_doi(visible_text),
                "authors": _authors_from_text(visible_text),
                "journal": _journal_from_text(visible_text),
                "publication_date": _first_date(visible_text),
                "visible_text": visible_text,
            }
        )

    return entries


def parse_cma_detail(html: str, detail_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    meta = _meta_values(soup)
    body_text = _clean_text(soup.get_text(" ", strip=True))

    title_zh = _first_meta(meta, "citation_title", "dc.title", "eprints.title")
    if not title_zh:
        title_node = soup.find("h1") or soup.find("title")
        title_zh = _clean_text(title_node.get_text(" ", strip=True)) if title_node else ""

    title_en = _english_title(soup, title_zh)
    authors = meta.get("citation_author") or meta.get("eprints.creators_name") or _authors_from_text(body_text)
    journal = _first_meta(meta, "citation_journal_title", "eprints.publication", "jour-name") or _journal_from_text(body_text)
    publication_date = _first_meta(meta, "citation_publication_date", "eprints.date") or _first_date(body_text)
    doi = _first_meta(meta, "citation_doi", "eprints.doi", "dc.identifier") or _first_doi(body_text)
    citation = _citation_text(soup, body_text)
    abstract = _abstract_text(soup) or _first_meta(meta, "citation_abstract", "eprints.abstract")
    pdf_status, pdf_url, pdf_restriction_zh = _pdf_status(soup, detail_url, body_text)

    return {
        "detail_url": detail_url,
        "doi": doi,
        "title_zh": title_zh,
        "title_en": title_en,
        "authors": authors,
        "journal": journal,
        "publication_date": publication_date,
        "citation": citation,
        "abstract": abstract,
        "pdf_status": pdf_status,
        "pdf_url": pdf_url,
        "pdf_restriction_zh": pdf_restriction_zh,
        "full_visible_text": body_text,
    }


def build_cma_material(
    *,
    task_id: str,
    material_id: str,
    query: str,
    search_url: str,
    search_sql: str,
    search_snapshot: str,
    detail_snapshot: str,
    text_path: str,
    download_status: str | None = None,
    download_files: list | None = None,
    entry: dict[str, Any],
    detail: dict[str, Any],
) -> Material:
    raw_fields = {
        "doi": detail.get("doi") or entry.get("doi", ""),
        "title_zh": detail.get("title_zh", ""),
        "title_en": detail.get("title_en", ""),
        "authors": detail.get("authors") or entry.get("authors", []),
        "journal": detail.get("journal") or entry.get("journal", ""),
        "publication_date": detail.get("publication_date") or entry.get("publication_date", ""),
        "citation": detail.get("citation", ""),
        "abstract": detail.get("abstract", ""),
        "pdf_status": detail.get("pdf_status", "not_found"),
        "pdf_url": detail.get("pdf_url", ""),
        "pdf_restriction_zh": detail.get("pdf_restriction_zh", ""),
        "list_visible_text": entry.get("visible_text", ""),
        "validation_rules": VALIDATION_RULES,
    }
    return Material(
        material_id=material_id,
        task_id=task_id,
        source_scenario=SCENARIO_ID,
        material_type=MATERIAL_TYPE,
        title=detail.get("title_zh") or entry["title"],
        source_url=entry["detail_url"],
        search_keyword_or_query=query,
        collection_path={
            "scenario_id": SCENARIO_ID,
            "search_url": search_url,
            "detail_url": entry["detail_url"],
            "search_sql": search_sql,
            "search_snapshot": search_snapshot,
            "detail_snapshot": detail_snapshot,
            "list_index": entry.get("list_index"),
        },
        collection_time=now_iso(),
        adapter_id=SCENARIO_ID,
        adapter_version="0.4.0",
        raw_fields=raw_fields,
        download_status=download_status or _download_status_for_pdf(raw_fields["pdf_status"]),
        download_files=download_files or [],
        extracted_text_status="completed" if text_path else "not_attempted",
        extracted_text_path=text_path,
        content_snapshot_path=detail_snapshot,
    )


def collect(task_id, task_dir, params):
    query = str(params.get("query", "")).strip()
    material_id = params.get("material_id", "MAT-000000")
    task_dir = Path(task_dir)
    if not query:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh="中华临床实验室管理电子杂志文献缺少检索关键词，请先确认关键词池。",
        )

    search_sql = build_search_sql(query)
    try:
        html, final_url, status_code = post_html(SEARCH_URL, {"searchSQL": search_sql})
    except Exception as exc:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{SUBJECT_ZH}检索失败：{exc}",
        )

    text = page_text(html)
    if _is_no_results_text(text):
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{SUBJECT_ZH}未查询到与“{query}”匹配的公开结果。",
        )

    restriction = detect_restriction(html, final_url, status_code)
    if restriction:
        return ScenarioResult(
            status=restriction.value,
            failure_type=restriction,
            message_zh=f"{SUBJECT_ZH}检索页返回受限或空白内容（{restriction.value}）。",
        )
    if status_code >= 400:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{SUBJECT_ZH}检索失败，HTTP 状态码 {status_code}，URL：{final_url}",
        )

    entries = parse_cma_result_list(html, final_url)
    if not entries:
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{SUBJECT_ZH}未在检索页解析到与“{query}”匹配的文献详情链接。",
        )

    search_snapshot = save_snapshot(
        task_dir,
        MATERIAL_TYPE,
        f"{material_id}_{SCENARIO_ID}_search.html",
        html,
    )

    materials = []
    collection_errors: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        current_material_id = material_id if len(entries) == 1 else f"{material_id}-{index:03d}"
        try:
            detail_html, final_detail_url, detail_status = fetch_html(entry["detail_url"])
        except Exception as exc:
            collection_errors.append(
                {
                    "detail_url": entry["detail_url"],
                    "status": "collection_failed",
                    "reason": str(exc),
                }
            )
            continue

        restriction = detect_restriction(detail_html, final_detail_url, detail_status)
        if restriction:
            collection_errors.append(
                {
                    "detail_url": entry["detail_url"],
                    "status": restriction.value,
                    "reason": "restricted detail page",
                }
            )
            continue
        if detail_status >= 400:
            collection_errors.append(
                {
                    "detail_url": entry["detail_url"],
                    "status": "collection_failed",
                    "reason": f"{SUBJECT_ZH}详情页访问失败，HTTP 状态码 {detail_status}，URL：{final_detail_url}",
                }
            )
            continue

        detail_snapshot = save_snapshot(
            task_dir,
            MATERIAL_TYPE,
            f"{current_material_id}_{SCENARIO_ID}_detail.html",
            detail_html,
        )
        detail = parse_cma_detail(detail_html, final_detail_url)
        if not _is_valid_article_detail(detail):
            continue
        detail_text = _article_text_for_storage(detail)
        text_path = save_text(
            task_dir,
            MATERIAL_TYPE,
            f"{current_material_id}_{SCENARIO_ID}.txt",
            detail_text,
        )
        download_status = _download_status_for_pdf(detail.get("pdf_status", "not_found"))
        download_files = []
        if detail.get("pdf_status") == "available_public_link" and detail.get("pdf_url"):
            download_status, download_files = download_public_pdf(
                task_dir,
                url=detail["pdf_url"],
                stored_filename=f"{current_material_id}_{SCENARIO_ID}.pdf",
                material_type=MATERIAL_TYPE,
            )
        materials.append(
            build_cma_material(
                task_id=task_id,
                material_id=current_material_id,
                query=query,
                search_url=final_url,
                search_sql=search_sql,
                search_snapshot=search_snapshot,
                detail_snapshot=detail_snapshot,
                text_path=text_path,
                download_status=download_status,
                download_files=download_files,
                entry=entry,
                detail=detail,
            )
        )

    if not materials:
        return ScenarioResult(
            status="collection_failed" if collection_errors else "no_valid_materials",
            failure_type=FailureType.COLLECTION_FAILED
            if collection_errors
            else FailureType.NO_VALID_MATERIALS,
            message_zh=f"{SUBJECT_ZH} no valid article detail metadata was extracted.",
            collection_errors=collection_errors,
        )

    return ScenarioResult(
        status="completed",
        materials=materials,
        collection_errors=collection_errors,
        message_zh=f"{SUBJECT_ZH}已完成真实检索页和详情页采集，共 {len(materials)} 篇。",
    )


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _looks_like_article_link(href: str) -> bool:
    href_lower = href.lower()
    if any(token in href_lower for token in ("download", "pdf", "file.do", "current.shtml", "showtenyear")):
        return False
    return (
        "/cn/10." in href_lower
        or "/cn/abstract/abstract" in href_lower
        or "/cn/" in href_lower and "cma.j" in href_lower
    )


def _cma_article_key(detail_url: str) -> str:
    return detail_url.split("#", 1)[0].lower()


def _is_valid_article_detail(detail: dict[str, Any]) -> bool:
    if not detail.get("title_zh"):
        return False
    return bool(
        detail.get("doi")
        or detail.get("journal")
        or detail.get("abstract")
        or detail.get("citation")
        or detail.get("authors")
    )


def _download_status_for_pdf(pdf_status: str) -> str:
    if pdf_status == "available_public_link":
        return "download_candidate"
    if pdf_status == "permission_required":
        return "permission_required"
    return "not_attempted"


def _first_doi(text: str) -> str:
    match = DOI_RE.search(text)
    return match.group(0).rstrip(".") if match else ""


def _first_date(text: str) -> str:
    match = DATE_RE.search(text)
    return match.group(0) if match else ""


def _authors_from_text(text: str) -> list[str]:
    match = re.search(r"(?:作者|Authors?)[:：]\s*(.+?)(?=\s*(?:DOI|中华临床实验室管理电子杂志|摘要|$))", text, re.IGNORECASE)
    if not match:
        return []
    return _split_people(match.group(1))


def _split_people(value: str) -> list[str]:
    cleaned = _clean_text(value).strip(" ，,;；")
    if not cleaned:
        return []
    parts = re.split(r"[，、;；]|\s*,\s*", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _journal_from_text(text: str) -> str:
    journal = "中华临床实验室管理电子杂志"
    return journal if journal in text else ""


def _meta_values(soup: BeautifulSoup) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for tag in soup.find_all("meta"):
        key = tag.get("name") or tag.get("property")
        content = tag.get("content", "").strip()
        if not key or not content:
            continue
        values.setdefault(key.lower(), []).append(_clean_text(content))
    return values


def _first_meta(meta: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = meta.get(key.lower())
        if values:
            return values[0]
    return ""


def _english_title(soup: BeautifulSoup, title_zh: str) -> str:
    for node in soup.find_all(["h1", "h2", "h3", "p", "div"]):
        text = _clean_text(node.get_text(" ", strip=True))
        if not text or text == title_zh:
            continue
        if re.search(r"[A-Za-z]{3,}", text) and not re.search(r"[\u4e00-\u9fff]", text):
            return text
    return ""


def _citation_text(soup: BeautifulSoup, body_text: str) -> str:
    for selector in (".citation", ".ref", ".source", ".meta"):
        node = soup.select_one(selector)
        if node:
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    journal = _journal_from_text(body_text)
    if not journal:
        return ""
    start = body_text.find(journal)
    end = body_text.find(" DOI", start)
    if end == -1:
        end = len(body_text)
    return _clean_text(body_text[start:end])


def _abstract_text(soup: BeautifulSoup) -> str:
    for selector in ("#abstract", ".abstract", ".article-abstract"):
        node = soup.select_one(selector)
        if node:
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                return text

    for heading in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
        if "摘要" not in heading.get_text(" ", strip=True):
            continue
        parent = heading.find_parent(["section", "div", "article"])
        if parent:
            text = _clean_text(parent.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _pdf_status(soup: BeautifulSoup, detail_url: str, body_text: str) -> tuple[str, str, str]:
    meta_pdf_url = _first_meta(_meta_values(soup), "citation_pdf_url", "eprints.document_url")
    if meta_pdf_url and (
        ".pdf" in meta_pdf_url.lower()
        or "downloadarticlefile" in meta_pdf_url.lower()
    ):
        return "available_public_link", urljoin(detail_url, meta_pdf_url), ""
    restricted_tokens = ("登录", "登陆", "权限", "付费", "购买", "VIP", "试读", "不存在", "暂无PDF")
    for anchor in soup.find_all("a", href=True):
        label = _clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "")
        candidate = f"{label} {href}"
        if "pdf" not in candidate.lower():
            continue
        if href.strip().lower().startswith(("javascript:", "#")):
            return "permission_required", "", "PDF 下载不是明确的公开文件链接，未尝试下载。"
        if any(token in candidate for token in restricted_tokens):
            return "permission_required", "", "PDF 下载需要登录、权限或付费，未尝试下载。"
        return "available_public_link", urljoin(detail_url, href), ""

    if any(token in body_text for token in restricted_tokens):
        return "permission_required", "", "PDF 下载需要登录、权限或付费，未尝试下载。"
    return "not_found", "", ""


def _is_no_results_text(text: str) -> bool:
    return any(marker.lower() in text.lower() for marker in NO_RESULT_MARKERS)


def _article_text_for_storage(detail: dict[str, Any]) -> str:
    parts = [
        ("标题", detail.get("title_zh", "")),
        ("英文标题", detail.get("title_en", "")),
        ("作者", "；".join(detail.get("authors") or [])),
        ("期刊", detail.get("journal", "")),
        ("发表日期", detail.get("publication_date", "")),
        ("DOI", detail.get("doi", "")),
        ("引文", detail.get("citation", "")),
        ("摘要", detail.get("abstract", "")),
    ]
    lines = [f"{label}：{value}" for label, value in parts if value]
    if not lines:
        visible = str(detail.get("full_visible_text") or "")
        return _remove_page_noise(visible)
    return "\n".join(lines)


def _remove_page_noise(text: str) -> str:
    noise_tokens = [
        "Modal",
        "关闭",
        "提交更改",
        "首页",
        "当前目录",
        "过刊浏览",
        "下载引用文件",
        "文献管理软件",
        "AI",
    ]
    lines = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(token in stripped for token in noise_tokens):
            continue
        lines.append(stripped)
    return "\n".join(lines)
