import hashlib
import re
import zipfile
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from ivd_research.models import DownloadFile, FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso

from .registry import get_scenario
from .site_collect import (
    detect_restriction,
    http_error_result,
    page_text,
    save_snapshot,
    save_text,
    USER_AGENT,
)


SCENARIO_ID = "cmde_regulatory"
MATERIAL_TYPE = "regulatory"
SUBJECT_ZH = "CMDE 指导原则、征求意见和审评资料"
SEARCH_URL_TEMPLATE = "https://www.cmde.org.cn/search/?keywords={query}"
IVD_GUIDANCE_BASE = (
    "https://www.cmde.org.cn/flfg/zdyz/zdyzjs/cplb/cplbtwzdsj/"
)
IVD_GUIDANCE_PAGES = [
    f"{IVD_GUIDANCE_BASE}index.html",
    *[f"{IVD_GUIDANCE_BASE}index_{index}.html" for index in range(1, 9)],
]
VALIDATION_RULES = [
    "优先匹配用户关键词；无精确匹配时仅采集体外诊断试剂同类指导原则并标注为同类参考",
    "详情页必须来自 cmde.org.cn 公开栏目",
    "有 doc/docx 附件时下载原文并尽量抽取全文",
    "collection_failed",
    "no_results",
]
ANALOG_TERMS = (
    "肺炎",
    "支原体",
    "核酸检测试剂",
    "抗原检测试剂",
    "抗体检测试剂",
    "检测试剂",
    "病原体",
    "呼吸道",
)
CMDE_RESULT_PREFIXES = ("【审评报告】", "【指导原则文本库】", "【征求意见】")
WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def adapter():
    return get_scenario(SCENARIO_ID)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _fetch(url: str) -> tuple[bytes, str, int, str]:
    with httpx.Client(timeout=45.0, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
    return response.content, response.headers.get("content-type", ""), response.status_code, str(response.url)


def _fetch_html(url: str) -> tuple[str, str, int]:
    content, _content_type, status_code, final_url = _fetch(url)
    return content.decode("utf-8", errors="ignore"), final_url, status_code


def _looks_like_security_script_page(html: str) -> bool:
    text = _clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
    return not text and ("$_ts" in html or "_$_v()" in html)


def _keyword_tokens(query: str) -> list[str]:
    tokens = [item for item in re.split(r"[\s;；,，/]+", query.strip()) if item]
    return tokens or [query.strip()] if query.strip() else []


def _page_url(index: int) -> str:
    if index == 0:
        return f"{IVD_GUIDANCE_BASE}index.html"
    return f"{IVD_GUIDANCE_BASE}index_{index}.html"


def _entry_date(text: str) -> str:
    match = re.search(r"\((\d{4}-\d{2}-\d{2})\)\s*$", text)
    return match.group(1) if match else ""


def parse_cmde_list_html(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        title = _clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "").strip()
        if not title or not href or not href.endswith(".html"):
            continue
        url = urljoin(base_url, href)
        if "/flfg/zdyz/" not in url:
            continue
        container = anchor.find_parent("li") or anchor.parent
        visible_text = _clean_text(container.get_text(" ", strip=True)) if container else title
        if "注册审查指导原则" not in visible_text and "技术审查指导原则" not in visible_text:
            continue
        if url in seen:
            continue
        seen.add(url)
        entries.append(
            {
                "title": title,
                "detail_url": url,
                "publication_date": _entry_date(visible_text),
                "visible_text": visible_text,
            }
        )
    return entries


def parse_cmde_search_html(html: str, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    entries = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        title = _clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "").strip()
        if not title or not href:
            continue
        if not any(prefix in title for prefix in CMDE_RESULT_PREFIXES):
            continue
        url = urljoin(base_url, href)
        if "cmde.org.cn" not in url and not url.startswith("http"):
            continue
        container = anchor.find_parent("li") or anchor.find_parent("div") or anchor.parent
        visible_text = _clean_text(container.get_text(" ", strip=True)) if container else title
        if url in seen:
            continue
        seen.add(url)
        document_category = ""
        for prefix in CMDE_RESULT_PREFIXES:
            if prefix in title:
                document_category = prefix.strip("【】")
                break
        entries.append(
            {
                "title": title,
                "detail_url": url,
                "publication_date": _entry_date(visible_text),
                "visible_text": visible_text,
                "document_category": document_category,
            }
        )
    return entries


def cmde_next_search_page_url(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        text = _clean_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "").strip()
        if "下一页" not in f"{text} {href}" and "next" not in f"{text} {href}".lower():
            continue
        if href and not href.lower().startswith(("javascript:", "#")):
            return urljoin(base_url, href)
    return ""


def _match_entry(entry: dict[str, str], query: str) -> str:
    haystack = f"{entry.get('title', '')} {entry.get('visible_text', '')}".lower()
    tokens = [token.lower() for token in _keyword_tokens(query)]
    if tokens and all(token in haystack for token in tokens):
        return "exact_query_match"
    return ""


def _docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile):
        return ""
    root = ElementTree.fromstring(xml)
    paragraphs = []
    for paragraph in root.findall(".//w:p", WORD_NS):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", WORD_NS)]
        line = _clean_text("".join(texts))
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_cmde_detail_html(html: str, detail_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = _clean_text((soup.find("h1") or soup.find("title")).get_text(" ", strip=True))
    text = page_text(html)
    date_match = re.search(r"发布时间[:：]\s*(\d{4}-\d{2}-\d{2})", text)
    attachment_url = ""
    attachment_title = ""
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if re.search(r"\.(?:docx?|pdf)(?:$|\?)", href, re.IGNORECASE):
            attachment_url = urljoin(detail_url, href)
            attachment_title = _clean_text(anchor.get_text(" ", strip=True)) or Path(href).name
            break
    return {
        "title": title,
        "publication_date": date_match.group(1) if date_match else "",
        "visible_text": text,
        "attachment_url": attachment_url,
        "attachment_title": attachment_title,
    }


def _readable_detail_html(detail: dict[str, Any], attachment_text: str) -> str:
    title = detail.get("title") or "CMDE regulatory material"
    rows = "\n".join(
        f"<dt>{escape(label)}</dt><dd>{escape(str(value))}</dd>"
        for label, value in (
            ("发布日期", detail.get("publication_date", "")),
            ("附件", detail.get("attachment_title", "")),
            ("附件地址", detail.get("attachment_url", "")),
        )
        if value
    )
    body = attachment_text or detail.get("visible_text", "")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; line-height: 1.7; margin: 32px; color: #1f2933; }}
    main {{ max-width: 920px; margin: 0 auto; }}
    h1 {{ font-size: 26px; line-height: 1.35; margin-bottom: 18px; }}
    dl {{ display: grid; grid-template-columns: 120px 1fr; gap: 8px 16px; margin-bottom: 24px; }}
    dt {{ font-weight: 700; color: #52606d; }}
    dd {{ margin: 0; word-break: break-all; }}
    pre {{ white-space: pre-wrap; font-family: inherit; background: #f6f8fa; padding: 18px; border-radius: 6px; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <dl>{rows}</dl>
    <pre>{escape(body)}</pre>
  </main>
</body>
</html>
"""


def _download_attachment(
    task_dir: Path,
    *,
    material_id: str,
    attachment_url: str,
) -> tuple[str, list[DownloadFile], str]:
    if not attachment_url:
        return "not_attempted", [], ""
    try:
        content, _content_type, status_code, final_url = _fetch(attachment_url)
    except Exception:
        return "download_failed", [], ""
    if status_code >= 400:
        return "download_failed", [], ""
    suffix = Path(final_url.split("?", 1)[0]).suffix or ".bin"
    target_dir = task_dir / "downloads" / MATERIAL_TYPE
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{material_id}_{SCENARIO_ID}_attachment{suffix}"
    target.write_bytes(content)
    extracted_text = _docx_text(content) if suffix.lower() == ".docx" else ""
    return "downloaded", [
        DownloadFile(
            original_filename=Path(final_url.split("?", 1)[0]).name,
            stored_filename=target.name,
            relative_path=str(target.relative_to(task_dir)),
            source_url=final_url,
            sha256=_sha256(content),
            status="downloaded",
        )
    ], extracted_text


def _build_material(
    *,
    task_id: str,
    material_id: str,
    query: str,
    match_strategy: str,
    list_url: str,
    list_snapshot: str,
    detail_url: str,
    detail_snapshot: str,
    text_path: str,
    entry: dict[str, str],
    detail: dict[str, Any],
    download_status: str,
    download_files: list[DownloadFile],
) -> Material:
    publication_date = detail.get("publication_date") or entry.get("publication_date", "")
    return Material(
        material_id=material_id,
        task_id=task_id,
        source_scenario=SCENARIO_ID,
        material_type=MATERIAL_TYPE,
        title=detail.get("title") or entry["title"],
        source_url=detail_url,
        search_keyword_or_query=query,
        collection_path={
            "scenario_id": SCENARIO_ID,
            "list_url": list_url,
            "detail_url": detail_url,
            "list_snapshot": list_snapshot,
            "detail_snapshot": detail_snapshot,
        },
        collection_time=now_iso(),
        adapter_id=SCENARIO_ID,
        adapter_version="0.5.0",
        raw_fields={
            "source_site": "CMDE",
            "document_category": entry.get("document_category") or "CMDE regulatory material",
            "publication_date": publication_date,
            "match_strategy": match_strategy,
            "attachment_title": detail.get("attachment_title", ""),
            "attachment_url": detail.get("attachment_url", ""),
            "validation_rules": VALIDATION_RULES,
        },
        download_status=download_status,
        download_files=download_files,
        extracted_text_status="completed" if text_path else "not_attempted",
        extracted_text_path=text_path,
        content_snapshot_path=detail_snapshot,
    )


def collect(task_id, task_dir, params):
    query = str(params.get("query", "")).strip()
    material_id = params.get("material_id", "MAT-000000")
    page_limit = int(params.get("page_limit", 3))
    result_limit = int(params.get("result_limit", 5))
    task_dir = Path(task_dir)
    if not query:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=f"{SUBJECT_ZH} 缺少检索关键词，请先确认关键词池。",
        )

    search_url = SEARCH_URL_TEMPLATE.format(query=quote(query))
    collection_errors = []
    try:
        search_html, final_search_url, search_status = _fetch_html(search_url)
    except Exception as exc:
        search_html, final_search_url, search_status = "", search_url, 0
        collection_errors.append({"url": search_url, "status": "collection_failed", "reason": str(exc)})
    if search_html:
        restriction = detect_restriction(search_html, final_search_url, search_status)
        if restriction:
            collection_errors.append(
                {
                    "url": final_search_url,
                    "status": restriction.value,
                    "reason": "CMDE 全文检索页受限，已继续采集公开栏目页",
                }
            )

    matched: list[tuple[dict[str, str], str, str]] = []
    exact_seen = False
    list_snapshots: dict[str, str] = {}
    if search_html and not detect_restriction(search_html, final_search_url, search_status):
        search_snapshot = save_snapshot(
            task_dir,
            MATERIAL_TYPE,
            f"{material_id}_{SCENARIO_ID}_search.html",
            search_html,
        )
        list_snapshots[final_search_url] = search_snapshot
        for entry in parse_cmde_search_html(search_html, final_search_url):
            matched.append((entry, "cmde_search_result", final_search_url))
        next_search_url = cmde_next_search_page_url(search_html, final_search_url)
        for page_index in range(2, max(1, page_limit) + 1):
            if not next_search_url:
                break
            try:
                page_html, page_url, page_status = _fetch_html(next_search_url)
            except Exception as exc:
                collection_errors.append({"url": next_search_url, "status": "collection_failed", "reason": str(exc)})
                break
            if detect_restriction(page_html, page_url, page_status):
                break
            page_snapshot = save_snapshot(
                task_dir,
                MATERIAL_TYPE,
                f"{material_id}_{SCENARIO_ID}_search_p{page_index}.html",
                page_html,
            )
            list_snapshots[page_url] = page_snapshot
            for entry in parse_cmde_search_html(page_html, page_url):
                matched.append((entry, "cmde_search_result", page_url))
            next_search_url = cmde_next_search_page_url(page_html, page_url)
    for page_index in range(min(page_limit, len(IVD_GUIDANCE_PAGES))):
        if matched:
            break
        list_url = _page_url(page_index)
        try:
            list_html, final_list_url, status_code = _fetch_html(list_url)
        except Exception as exc:
            collection_errors.append({"url": list_url, "status": "collection_failed", "reason": str(exc)})
            continue
        http_error = http_error_result(SUBJECT_ZH, status_code, final_list_url)
        if http_error:
            collection_errors.append({"url": list_url, "status": http_error.status, "reason": http_error.message_zh})
            continue
        snapshot = save_snapshot(
            task_dir,
            MATERIAL_TYPE,
            f"{material_id}_{SCENARIO_ID}_list_{page_index + 1}.html",
            list_html,
        )
        list_snapshots[final_list_url] = snapshot
        if _looks_like_security_script_page(list_html):
            collection_errors.append(
                {
                    "url": final_list_url,
                    "status": FailureType.PERMISSION_REQUIRED.value,
                    "reason": "CMDE 公开栏目页返回安全脚本空正文，无法解析栏目列表。",
                }
            )
            continue
        for entry in parse_cmde_list_html(list_html, final_list_url):
            strategy = _match_entry(entry, query)
            if not strategy:
                continue
            if strategy == "exact_query_match":
                exact_seen = True
            elif exact_seen:
                continue
            matched.append((entry, strategy, final_list_url))
        if exact_seen and len(matched) >= result_limit:
            break

    if exact_seen:
        matched = [item for item in matched if item[1] == "exact_query_match"]
    matched = matched[:result_limit]
    if not matched:
        if collection_errors and any(
            item.get("status") == FailureType.PERMISSION_REQUIRED.value
            for item in collection_errors
        ):
            return ScenarioResult(
                status=FailureType.PERMISSION_REQUIRED.value,
                failure_type=FailureType.PERMISSION_REQUIRED,
                message_zh=(
                    f"{SUBJECT_ZH} 返回安全脚本或受限页面，未能取得可解析的 CMDE 检索/栏目结果。"
                    "请使用浏览器 workflow 观察页面，或通过公开链接/人工导入补证。"
                ),
                collection_errors=collection_errors,
            )
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{SUBJECT_ZH} 未在 CMDE 体外诊断试剂指导原则栏目中找到与“{query}”相关的公开材料。",
            collection_errors=collection_errors,
        )

    materials: list[Material] = []
    for index, (entry, strategy, list_url) in enumerate(matched, start=1):
        current_material_id = material_id if len(matched) == 1 else f"{material_id}-{index:03d}"
        try:
            detail_html, final_detail_url, detail_status = _fetch_html(entry["detail_url"])
        except Exception as exc:
            collection_errors.append({"url": entry["detail_url"], "status": "collection_failed", "reason": str(exc)})
            continue
        http_error = http_error_result(SUBJECT_ZH, detail_status, final_detail_url)
        if http_error:
            collection_errors.append({"url": entry["detail_url"], "status": http_error.status, "reason": http_error.message_zh})
            continue
        detail = parse_cmde_detail_html(detail_html, final_detail_url)
        download_status, download_files, attachment_text = _download_attachment(
            task_dir,
            material_id=current_material_id,
            attachment_url=detail.get("attachment_url", ""),
        )
        readable_html = _readable_detail_html(detail, attachment_text)
        detail_snapshot = save_snapshot(
            task_dir,
            MATERIAL_TYPE,
            f"{current_material_id}_{SCENARIO_ID}_detail.html",
            readable_html,
        )
        text_path = save_text(
            task_dir,
            MATERIAL_TYPE,
            f"{current_material_id}_{SCENARIO_ID}.txt",
            attachment_text or detail.get("visible_text", ""),
        )
        materials.append(
            _build_material(
                task_id=task_id,
                material_id=current_material_id,
                query=query,
                match_strategy=strategy,
                list_url=list_url,
                list_snapshot=list_snapshots.get(list_url, ""),
                detail_url=final_detail_url,
                detail_snapshot=detail_snapshot,
                text_path=text_path,
                entry=entry,
                detail=detail,
                download_status=download_status,
                download_files=download_files,
            )
        )

    if not materials:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{SUBJECT_ZH} 找到候选条目，但详情页或附件采集失败。",
            collection_errors=collection_errors,
        )

    analog_count = sum(1 for material in materials if material.raw_fields.get("match_strategy") == "ivd_analog_reference")
    message = f"{SUBJECT_ZH} 已采集 {len(materials)} 条公开材料。"
    if analog_count:
        message += f" 其中 {analog_count} 条为体外诊断同类参考，非“{query}”精确匹配。"
    return ScenarioResult(
        status="completed",
        materials=materials,
        message_zh=message,
        collection_errors=collection_errors,
    )
