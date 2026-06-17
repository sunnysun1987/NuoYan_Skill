import hashlib
import json
import re
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin
from xml.etree import ElementTree

import httpx
from bs4 import BeautifulSoup

from ivd_research.models import DownloadFile, FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso


USER_AGENT = (
    "Mozilla/5.0 NuoYan-Skill/1.0 "
    "(compatible; research evidence collection)"
)


def normalized_tokens(query: str) -> list[str]:
    return [token.strip().lower() for token in query.replace("；", " ").replace(";", " ").split() if token.strip()]


def fetch_html(url: str) -> tuple[str, str, int]:
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
    return response.text, str(response.url), response.status_code


def post_html(url: str, data: dict[str, str]) -> tuple[str, str, int]:
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.post(url, data=data, headers={"User-Agent": USER_AGENT})
    return response.text, str(response.url), response.status_code


def fetch_binary(url: str) -> tuple[bytes, str, int]:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
    return response.content, response.headers.get("content-type", ""), response.status_code


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_pdf_response(content: bytes, content_type: str, status_code: int) -> bool:
    if status_code != 200:
        return False
    head = content[:1024].lstrip()
    return head.startswith(b"%PDF") or "application/pdf" in content_type.lower()


def download_public_pdf(
    task_dir: Path,
    *,
    url: str,
    stored_filename: str,
    material_type: str = "literature",
) -> tuple[str, list[DownloadFile]]:
    if not url:
        return "not_attempted", []
    try:
        content, content_type, status_code = fetch_binary(url)
    except Exception:
        return "download_failed", []
    if not _is_pdf_response(content, content_type, status_code):
        return "download_failed", []
    download_dir = task_dir / "downloads" / material_type
    download_dir.mkdir(parents=True, exist_ok=True)
    target = download_dir / stored_filename
    target.write_bytes(content)
    return "downloaded", [
        DownloadFile(
            original_filename=Path(url.split("?", 1)[0]).name or stored_filename,
            stored_filename=stored_filename,
            relative_path=str(target.relative_to(task_dir)),
            source_url=url,
            sha256=_sha256_bytes(content),
            status="downloaded",
        )
    ]


def page_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def save_snapshot(task_dir: Path, material_type: str, filename: str, html: str) -> str:
    snapshot_dir = task_dir / "downloads" / material_type
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / filename
    snapshot_path.write_text(html, encoding="utf-8", errors="ignore")
    return str(snapshot_path.relative_to(task_dir))


def save_text(task_dir: Path, material_type: str, filename: str, text: str) -> str:
    text_dir = task_dir / "extracted_text" / material_type
    text_dir.mkdir(parents=True, exist_ok=True)
    text_path = text_dir / filename
    text_path.write_text(text, encoding="utf-8", errors="ignore")
    return str(text_path.relative_to(task_dir))


def restriction_result(subject_zh: str, reason_zh: str, failure_type: FailureType) -> ScenarioResult:
    return ScenarioResult(
        status=failure_type.value,
        failure_type=failure_type,
        message_zh=f"{subject_zh} 未生成材料：{reason_zh}",
    )


def http_error_result(subject_zh: str, status_code: int, final_url: str) -> ScenarioResult | None:
    if status_code < 400:
        return None
    return ScenarioResult(
        status="collection_failed",
        failure_type=FailureType.COLLECTION_FAILED,
        message_zh=f"{subject_zh} 访问失败，HTTP 状态码 {status_code}，URL：{final_url}",
    )


def detect_restriction(html: str, final_url: str = "", status_code: int | None = None) -> FailureType | None:
    text = page_text(html).lower()
    html_lower = html.lower()
    if status_code == 401:
        return FailureType.NEEDS_LOGIN
    if status_code == 403:
        return FailureType.PERMISSION_REQUIRED
    if status_code == 202 or "$_ts" in html or "人机" in text or "安全验证" in text:
        return FailureType.PERMISSION_REQUIRED
    if "cf-challenge" in html_lower or "cloudflare" in text or "cf-turnstile-response" in html_lower:
        return FailureType.PERMISSION_REQUIRED
    if "reason=blocked" in final_url or ("用户登录" in text and "密码" in text):
        return FailureType.NEEDS_LOGIN
    if not page_text(html):
        return FailureType.COLLECTION_FAILED
    return None


def first_matching_link(html: str, base_url: str, tokens: list[str], href_contains: str = "") -> dict[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True)
        href = urljoin(base_url, anchor["href"])
        candidate = f"{text} {href}".lower()
        if href_contains and href_contains not in href:
            continue
        if not tokens or any(token in candidate for token in tokens):
            return {"text": text, "url": href}
    return None


YIIGLE_NO_RESULT_MARKERS = ("没有找到", "暂无数据", "无搜索结果", "未检索到", "no results")
YIIGLE_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
YIIGLE_NAV_LINK_TEXTS = {
    "上一篇",
    "下一篇",
    "摘要",
    "全文",
    "PDF",
    "PDF下载",
    "Previous",
    "Next",
    "Abstract",
}


def _clean_yiigle_text(value: str) -> str:
    text = " ".join(value.split())
    return re.sub(r"^(?:null|none)\s+", "", text, flags=re.IGNORECASE)


def _yiigle_meta_values(soup: BeautifulSoup) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for tag in soup.find_all("meta"):
        key = (tag.get("name") or tag.get("property") or "").strip().lower()
        content = _clean_yiigle_text(tag.get("content", ""))
        if key and content:
            values.setdefault(key, []).append(content)
    return values


def _first_yiigle_meta(meta: dict[str, list[str]], *names: str) -> str:
    for name in names:
        values = meta.get(name.lower(), [])
        if values:
            return values[0]
    return ""


def _all_yiigle_meta(meta: dict[str, list[str]], *names: str) -> list[str]:
    values: list[str] = []
    for name in names:
        values.extend(meta.get(name.lower(), []))
    return values


def _split_yiigle_values(values: list[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        for item in re.split(r"[;；,，、]\s*", value):
            cleaned = _clean_yiigle_text(item)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                items.append(cleaned)
    return items


def _yiigle_section_text(soup: BeautifulSoup, headings: tuple[str, ...]) -> str:
    for heading in soup.find_all(["h1", "h2", "h3", "h4", "strong", "b"]):
        heading_text = heading.get_text(" ", strip=True)
        if not any(marker.lower() in heading_text.lower() for marker in headings):
            continue
        parent = heading.find_parent(["section", "div", "article"]) or heading.parent
        if parent:
            text = parent.get_text(" ", strip=True)
            return _clean_yiigle_text(text.replace(heading_text, "", 1))
    return ""


def _is_yiigle_no_results(html: str) -> bool:
    text = page_text(html).lower()
    return any(marker.lower() in text for marker in YIIGLE_NO_RESULT_MARKERS)


def _yiigle_pdf_url(soup: BeautifulSoup, detail_url: str) -> str:
    # Strategy 1: Look for <a> tags with pdf/download hrefs (static pages)
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        text = anchor.get_text(" ", strip=True)
        href_lower = href.lower()
        if not href or href_lower.startswith(("javascript:", "#")):
            continue
        candidate = f"{href} {text}".lower()
        if ".pdf" in href_lower or ("download" in href_lower and "pdf" in candidate):
            return urljoin(detail_url, href)

    # Strategy 2: Extract from embedded xmlData (Nuxt.js SPA pages)
    # xmlData contains <self-uri content-type="pdf" xlink:href="..."/> but the
    # string may be JSON-escaped (< for <, / for /, \" for ")
    for script_tag in soup.find_all("script"):
        text = script_tag.string or ""
        if "self-uri" not in text:
            continue
        # Try matching the JSON-escaped form first (\\u003Cself-uri...)
        pdf_match = re.search(
            r'(?:\\u003C|<)\s*self-uri\s[^>]*content-type\s*=\s*(?:\\"|["\'])\s*pdf\s*(?:\\"|["\'])'
            r'[^>]*(?:\\"|["\'])\s*xlink[:_]href\s*=\s*(?:\\"|["\'])\s*([^\s"\'\\>]+)',
            text,
            re.IGNORECASE,
        )
        if pdf_match:
            pdf_path = pdf_match.group(1).replace("\\u002F", "/").replace("\\/", "/")
            return urljoin(detail_url, pdf_path)

    # Strategy 3: Look for PDF download buttons in Vue/Nuxt components
    pdf_button = soup.select_one(
        '[title="PDF下载"], [title*="PDF"], [aria-label*="PDF"], '
        '[class*="icon-PDF"], a[href*=".pdf"]'
    )
    if pdf_button:
        href = pdf_button.get("href", "")
        if href and not href.startswith(("javascript:", "#")):
            return urljoin(detail_url, href)

    return ""


def _yiigle_next_page_url(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    current_page = 1
    current_match = re.search(r"search_(\d+)\.jspx", base_url)
    if current_match:
        current_page = int(current_match.group(1))
    numeric_candidates: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        text = _clean_yiigle_text(anchor.get_text(" ", strip=True))
        href = anchor.get("href", "").strip()
        candidate = f"{text} {href}".lower()
        if "下一页" not in candidate and "next" not in candidate:
            page_match = re.search(r"search_(\d+)\.jspx", href)
            if page_match:
                page_number = int(page_match.group(1))
                if page_number > current_page:
                    numeric_candidates.append((page_number, href))
            continue
        if href.startswith("javascript:pageClickEvent("):
            match = re.search(r"pageClickEvent\(['\"]([^'\"]+)['\"]\)", href)
            if match:
                return urljoin(base_url, match.group(1))
        if href and not href.lower().startswith(("javascript:", "#")):
            return urljoin(base_url, href)
    if numeric_candidates:
        _page_number, href = sorted(numeric_candidates)[0]
        match = re.search(r"pageClickEvent\(['\"]([^'\"]+)['\"]\)", href)
        return urljoin(base_url, match.group(1) if match else href)
    return ""


def _yiigle_xml_data(html: str) -> str:
    match = re.search(r'xmlData:"((?:\\.|[^"\\])*)"', html)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return ""


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_node_text(node: ElementTree.Element) -> str:
    return _clean_yiigle_text("".join(node.itertext()))


def _yiigle_xml_sections(html: str) -> dict[str, str]:
    xml_text = _yiigle_xml_data(html)
    if not xml_text:
        return {"full_text": "", "references": "", "pdf_url": ""}
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except ElementTree.ParseError:
        return {"full_text": "", "references": "", "pdf_url": ""}

    body_lines: list[str] = []
    references: list[str] = []
    pdf_url = ""
    in_body = False
    in_back = False
    for node in root.iter():
        name = _xml_local_name(node.tag)
        if name == "body":
            in_body = True
            in_back = False
            continue
        if name == "back":
            in_body = False
            in_back = True
            continue
        if name == "self-uri":
            content_type = node.get("content-type", "")
            href = node.get("{http://www.w3.org/1999/xlink}href", "")
            if content_type == "pdf" and href:
                pdf_url = href
            continue
        text = _xml_node_text(node)
        if not text:
            continue
        if in_body and name in {"title", "p"}:
            body_lines.append(text)
        elif in_back and name == "mixed-citation":
            references.append(text)
    return {
        "full_text": "\n".join(dict.fromkeys(body_lines)),
        "references": "\n".join(dict.fromkeys(references)),
        "pdf_url": pdf_url,
    }


def _yiigle_article_key(detail_url: str) -> str:
    cmaid_match = re.search(r"/cmaid/(\d+)", detail_url, re.IGNORECASE)
    if cmaid_match:
        return cmaid_match.group(1)
    abstract_match = re.search(r"/abstract/abstract(\d+)", detail_url, re.IGNORECASE)
    if abstract_match:
        return abstract_match.group(1)
    return detail_url.lower()


def _is_yiigle_navigation_link(title: str, visible_text: str) -> bool:
    cleaned_title = _clean_yiigle_text(title)
    if cleaned_title in YIIGLE_NAV_LINK_TEXTS:
        return True
    if len(cleaned_title) <= 4 and cleaned_title.lower() in {
        item.lower() for item in YIIGLE_NAV_LINK_TEXTS
    }:
        return True
    return False


def _yiigle_access_fields(text: str, pdf_url: str) -> dict[str, str]:
    text_lower = text.lower()
    restricted = any(
        marker in text_lower
        for marker in (
            "试读结束",
            "继续阅读请登录",
            "请登录",
            "登录后",
            "购买全文",
            "付费",
            "权限",
            "订阅",
            "trial",
            "login",
            "purchase",
        )
    )
    free = any(
        marker in text_lower
        for marker in (
            "免费",
            "开放获取",
            "开放全文",
            "全文开放",
            "全文免费",
            "open access",
            "free full text",
        )
    )

    if restricted:
        full_text_access = "trial_login_or_paid_required"
        pdf_status = "permission_required" if pdf_url else "not_found"
        download_status = "permission_required" if pdf_url else "not_attempted"
    elif free:
        full_text_access = "free_html"
        pdf_status = "download_candidate" if pdf_url else "not_found"
        download_status = "download_candidate" if pdf_url else "not_attempted"
    else:
        full_text_access = "public_html_text"
        pdf_status = "not_downloaded_access_unclear" if pdf_url else "not_found"
        download_status = "not_attempted"

    return {
        "full_text_access": full_text_access,
        "pdf_status": pdf_status,
        "download_status": download_status,
    }


def parse_yiigle_result_list(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue
        if re.search(r"\(\d+\)\s*$", title):
            continue
        detail_url = urljoin(base_url, anchor["href"]).split("#", 1)[0]
        detail_url_lower = detail_url.lower()
        if (
            "rs.yiigle.com/cmaid/" not in detail_url_lower
            and "/cn/abstract/abstract" not in detail_url_lower
        ):
            continue
        container = anchor.find_parent(["div", "li", "tr", "article"]) or anchor.parent
        visible_text = container.get_text(" ", strip=True) if container else title
        if _is_yiigle_navigation_link(title, visible_text):
            continue
        article_key = _yiigle_article_key(detail_url)
        if article_key in seen:
            continue
        seen.add(article_key)
        entries.append(
            {
                "title": _clean_yiigle_text(title),
                "detail_url": detail_url,
                "list_index": len(entries) + 1,
                "visible_text": _clean_yiigle_text(visible_text),
            }
        )
    return entries


def parse_yiigle_detail(html: str, detail_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    meta = _yiigle_meta_values(soup)
    text = page_text(html)
    title_node = soup.find("h1") or soup.find("title")
    title = (
        _first_yiigle_meta(meta, "citation_title", "eprints.title", "dc.title")
        or (title_node.get_text(" ", strip=True) if title_node else "")
        or "Yiigle 文献详情"
    )
    authors = _split_yiigle_values(
        _all_yiigle_meta(
            meta,
            "citation_author",
            "eprints.creators_name",
            "dc.creator",
            "author",
        )
    )
    if not authors:
        author_match = re.search(r"作者[:：]\s*([^。；;\n]+)", text)
        if author_match:
            authors = _split_yiigle_values([author_match.group(1)])

    doi = _first_yiigle_meta(meta, "citation_doi", "eprints.doi", "dc.identifier")
    if not doi:
        doi_match = YIIGLE_DOI_RE.search(text)
        doi = doi_match.group(0) if doi_match else ""

    abstract = (
        _first_yiigle_meta(meta, "citation_abstract", "eprints.abstract")
        or _yiigle_section_text(soup, ("摘要", "abstract"))
        or _first_yiigle_meta(meta, "description")
    )
    keywords = (
        _first_yiigle_meta(
            meta, "citation_keywords", "eprints.keywords", "dc.subject", "keywords"
        )
        or _yiigle_section_text(soup, ("关键词", "key words", "keywords"))
    )
    pdf_url = _yiigle_pdf_url(soup, detail_url)
    xml_sections = _yiigle_xml_sections(html)
    if not pdf_url and xml_sections.get("pdf_url"):
        pdf_url = urljoin(detail_url, xml_sections["pdf_url"])
    access_fields = _yiigle_access_fields(text, pdf_url)
    if xml_sections["full_text"]:
        access_fields["full_text_access"] = "embedded_structured_text_available"

    return {
        "title": _clean_yiigle_text(title),
        "detail_url": detail_url,
        "authors": authors,
        "publication_date": _first_yiigle_meta(
            meta, "citation_publication_date", "eprints.date", "dc.date"
        ),
        "doi": doi,
        "abstract": _clean_yiigle_text(abstract),
        "keywords": _clean_yiigle_text(keywords),
        "journal": _first_yiigle_meta(
            meta,
            "citation_journal_title",
            "eprints.publication",
            "jour-name",
            "journal-title",
        ),
        "full_text_access": access_fields["full_text_access"],
        "pdf_status": access_fields["pdf_status"],
        "pdf_url": pdf_url,
        "download_status": access_fields["download_status"],
        "full_text": xml_sections["full_text"],
        "references": xml_sections["references"],
        "full_text_length": len(xml_sections["full_text"]),
    }


def _yiigle_readable_detail_text(entry: dict[str, Any], detail: dict[str, Any]) -> str:
    lines: list[str] = []

    def add(label: str, value: Any) -> None:
        if value:
            lines.append(f"{label}: {value}")

    add("Title", detail.get("title") or entry.get("title", ""))
    authors = detail.get("authors") or []
    if authors:
        add("Authors", "; ".join(authors))
    add("Journal", detail.get("journal", ""))
    add("Publication date", detail.get("publication_date", ""))
    add("DOI", detail.get("doi", ""))
    add("Keywords", detail.get("keywords", ""))
    add("Abstract", detail.get("abstract", ""))
    add("Source URL", detail.get("detail_url") or entry.get("detail_url", ""))
    add("PDF URL", detail.get("pdf_url", ""))
    add("Full text access", detail.get("full_text_access", ""))
    add("Full text", detail.get("full_text", ""))
    add("References", detail.get("references", ""))
    return "\n".join(lines) + "\n"


def _yiigle_readable_detail_html(entry: dict[str, Any], detail: dict[str, Any]) -> str:
    title = str(detail.get("title") or entry.get("title") or "Yiigle literature detail")
    authors = detail.get("authors") or []
    fields = [
        ("Authors", "; ".join(authors)),
        ("Journal", detail.get("journal", "")),
        ("Publication date", detail.get("publication_date", "")),
        ("DOI", detail.get("doi", "")),
        ("Keywords", detail.get("keywords", "")),
        ("Source URL", detail.get("detail_url") or entry.get("detail_url", "")),
        ("PDF URL", detail.get("pdf_url", "")),
        ("Full text access", detail.get("full_text_access", "")),
    ]
    rows = "\n".join(
        f"<dt>{escape(label)}</dt><dd>{escape(str(value))}</dd>"
        for label, value in fields
        if value
    )
    abstract = str(detail.get("abstract") or "")
    abstract_html = (
        f"<section><h2>Abstract</h2><p>{escape(abstract)}</p></section>"
        if abstract
        else ""
    )
    full_text = str(detail.get("full_text") or "")
    full_text_html = (
        f"<section><h2>Full Text Extracted From Page Data</h2><pre>{escape(full_text)}</pre></section>"
        if full_text
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.65; margin: 32px; color: #1f2933; }}
    main {{ max-width: 880px; margin: 0 auto; }}
    h1 {{ font-size: 28px; line-height: 1.35; margin-bottom: 20px; }}
    dl {{ display: grid; grid-template-columns: 160px 1fr; gap: 8px 18px; }}
    dt {{ font-weight: 700; color: #52606d; }}
    dd {{ margin: 0; }}
    section {{ margin-top: 24px; }}
    pre {{ white-space: pre-wrap; font-family: inherit; background: #f6f8fa; padding: 16px; border-radius: 6px; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <dl>
{rows}
    </dl>
    {abstract_html}
    {full_text_html}
  </main>
</body>
</html>
"""


def build_yiigle_material(
    *,
    task_id: str,
    material_id: str,
    query: str,
    scenario_id: str,
    search_url: str,
    search_snapshot: str,
    detail_snapshot: str,
    text_path: str,
    raw_detail_snapshot: str = "",
    download_status: str | None = None,
    download_files: list[DownloadFile] | None = None,
    entry: dict[str, Any],
    detail: dict[str, Any],
) -> Material:
    collection_path = {
        "scenario_id": scenario_id,
        "search_url": search_url,
        "detail_url": detail.get("detail_url") or entry["detail_url"],
        "search_snapshot": search_snapshot,
        "detail_snapshot": detail_snapshot,
        "list_index": entry.get("list_index"),
    }
    if raw_detail_snapshot:
        collection_path["raw_detail_snapshot"] = raw_detail_snapshot

    return Material(
        material_id=material_id,
        task_id=task_id,
        source_scenario=scenario_id,
        material_type="literature",
        title=detail.get("title") or entry["title"],
        source_url=detail.get("detail_url") or entry["detail_url"],
        search_keyword_or_query=query,
        collection_path=collection_path,
        collection_time=now_iso(),
        adapter_id=scenario_id,
        adapter_version="0.4.0",
        raw_fields={
            "journal": detail.get("journal", ""),
            "publication_date": detail.get("publication_date", ""),
            "doi": detail.get("doi", ""),
            "authors": detail.get("authors", []),
            "keywords": detail.get("keywords", ""),
            "abstract": detail.get("abstract", ""),
            "full_text_access": detail.get("full_text_access", ""),
            "pdf_status": detail.get("pdf_status", ""),
            "pdf_url": detail.get("pdf_url", ""),
            "full_text_length": detail.get("full_text_length", 0),
            "list_visible_text": entry.get("visible_text", ""),
        },
        download_status=download_status or detail.get("download_status", "not_attempted"),
        download_files=download_files or [],
        extracted_text_status="completed" if text_path else "not_attempted",
        extracted_text_path=text_path,
        content_snapshot_path=detail_snapshot,
    )


def _yiigle_detail_matches_query(entry: dict[str, Any], detail: dict[str, Any], query: str) -> bool:
    tokens = normalized_tokens(query)
    if not tokens:
        return True
    haystack = " ".join(
        [
            entry.get("title", ""),
            entry.get("visible_text", ""),
            detail.get("title", ""),
            detail.get("abstract", ""),
            detail.get("keywords", ""),
            detail.get("doi", ""),
        ]
    ).lower()
    return all(token in haystack for token in tokens)


def collect_yiigle_journal(
    *,
    task_id: str,
    task_dir: Path,
    params: dict[str, Any],
    scenario_id: str,
    journal_url: str,
    subject_zh: str,
    search_url_template: str = "",
) -> ScenarioResult:
    query = str(params.get("query", "")).strip()
    material_id = params.get("material_id", "MAT-000000")
    if not query:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=f"{subject_zh} 缺少检索关键词，请先确认关键词池。",
        )

    if search_url_template:
        search_url = search_url_template.format(query=quote(query))
    else:
        search_url = f"{journal_url.rstrip('/')}/search.jspx?q={quote(query)}"
    try:
        search_html, final_search_url, search_status = fetch_html(search_url)
    except Exception as exc:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{subject_zh} 搜索页访问失败：{exc}",
        )

    if _is_yiigle_no_results(search_html):
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{subject_zh} 未查询到与“{query}”匹配的文献结果。",
        )
    restriction = detect_restriction(search_html, final_search_url, search_status)
    if restriction:
        return restriction_result(
            subject_zh,
            f"搜索页返回受限或空白内容（{restriction.value}）。",
            restriction,
        )
    http_error = http_error_result(subject_zh, search_status, final_search_url)
    if http_error:
        return http_error

    search_snapshot = save_snapshot(
        task_dir,
        "literature",
        f"{material_id}_{scenario_id}_search.html",
        search_html,
    )
    entries = parse_yiigle_result_list(search_html, final_search_url)
    pagination_errors: list[dict[str, Any]] = []
    page_limit = int(params.get("page_limit", 5))
    seen_entry_keys = {_yiigle_article_key(entry["detail_url"]) for entry in entries}
    next_url = _yiigle_next_page_url(search_html, final_search_url)
    for page_number in range(2, max(1, page_limit) + 1):
        if not next_url:
            break
        try:
            page_html, page_url, page_status = fetch_html(next_url)
        except Exception as exc:
            pagination_errors.append(
                {
                    "url": next_url,
                    "status": "collection_failed",
                    "reason": str(exc),
                }
            )
            break
        restriction = detect_restriction(page_html, page_url, page_status)
        if restriction:
            break
        http_error = http_error_result(subject_zh, page_status, page_url)
        if http_error:
            break
        save_snapshot(
            task_dir,
            "literature",
            f"{material_id}_{scenario_id}_search_p{page_number}.html",
            page_html,
        )
        for entry in parse_yiigle_result_list(page_html, page_url):
            key = _yiigle_article_key(entry["detail_url"])
            if key in seen_entry_keys:
                continue
            seen_entry_keys.add(key)
            entries.append(entry)
        next_url = _yiigle_next_page_url(page_html, page_url)
    if not entries:
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{subject_zh} 未在搜索页发现与“{query}”匹配的文献详情链接。",
        )

    materials: list[Material] = []
    collection_errors: list[dict[str, Any]] = pagination_errors
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
        http_error = http_error_result(subject_zh, detail_status, final_detail_url)
        if http_error:
            collection_errors.append(
                {
                    "detail_url": entry["detail_url"],
                    "status": http_error.status,
                    "reason": http_error.message_zh,
                }
            )
            continue

        raw_detail_snapshot = save_snapshot(
            task_dir,
            "literature",
            f"{current_material_id}_{scenario_id}_raw_detail.html",
            detail_html,
        )
        detail = parse_yiigle_detail(detail_html, final_detail_url)
        detail_snapshot = save_snapshot(
            task_dir,
            "literature",
            f"{current_material_id}_{scenario_id}_detail.html",
            _yiigle_readable_detail_html(entry, detail),
        )
        text_path = save_text(
            task_dir,
            "literature",
            f"{current_material_id}_{scenario_id}.txt",
            _yiigle_readable_detail_text(entry, detail),
        )
        download_status = detail.get("download_status", "not_attempted")
        download_files: list[DownloadFile] = []
        if detail.get("pdf_status") == "download_candidate" and detail.get("pdf_url"):
            download_status, download_files = download_public_pdf(
                task_dir,
                url=detail["pdf_url"],
                stored_filename=f"{current_material_id}_{scenario_id}.pdf",
                material_type="literature",
            )
        materials.append(
            build_yiigle_material(
                task_id=task_id,
                material_id=current_material_id,
                query=query,
                scenario_id=scenario_id,
                search_url=final_search_url,
                search_snapshot=search_snapshot,
                detail_snapshot=detail_snapshot,
                text_path=text_path,
                raw_detail_snapshot=raw_detail_snapshot,
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
            message_zh=f"{subject_zh} did not yield valid literature materials.",
            collection_errors=collection_errors,
        )

    return ScenarioResult(
        status="completed",
        materials=materials,
        collection_errors=collection_errors,
        message_zh=f"{subject_zh} 已通过真实搜索页和详情页采集 {len(materials)} 条候选文献。",
    )


def collect_search_snapshot(
    *,
    task_id: str,
    task_dir: Path,
    params: dict[str, Any],
    scenario_id: str,
    material_type: str,
    subject_zh: str,
    search_url_template: str,
    no_result_markers: list[str],
    validation_rules: list[str],
) -> ScenarioResult:
    query = str(params.get("query", "")).strip()
    material_id = params.get("material_id", "MAT-000000")
    if not query:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=f"{subject_zh} 缺少检索关键词，请先确认关键词池。",
        )
    search_url = search_url_template.format(query=quote(query))
    try:
        html, final_url, status_code = fetch_html(search_url)
    except Exception as exc:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{subject_zh} 搜索页访问失败：{exc}",
        )
    restriction = detect_restriction(html, final_url, status_code)
    if restriction:
        return restriction_result(subject_zh, f"搜索页返回受限或空白内容（{restriction.value}）。", restriction)
    http_error = http_error_result(subject_zh, status_code, final_url)
    if http_error:
        return http_error

    text = page_text(html)
    if any(marker in text for marker in no_result_markers):
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{subject_zh} 未查询到与“{query}”匹配的公开结果。",
        )
    tokens = normalized_tokens(query)
    if tokens and not any(token in text.lower() for token in tokens):
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{subject_zh} 搜索页未出现与“{query}”直接匹配的内容。",
        )

    snapshot = save_snapshot(task_dir, material_type, f"{material_id}_{scenario_id}_search.html", html)
    save_text(task_dir, material_type, f"{material_id}_{scenario_id}.txt", text)
    return ScenarioResult(
        status="needs_manual_review",
        failure_type=FailureType.NEEDS_MANUAL_REVIEW,
        message_zh=(
            f"{subject_zh} 仅到达搜索结果页，已保存诊断快照 {snapshot}；"
            "尚未进入详情页或下载原文，因此未生成正式材料。"
        ),
    )


def collect_site(
    *,
    task_id: str,
    task_dir: Path,
    params: dict[str, Any],
    scenario_id: str,
    material_type: str,
    subject_zh: str,
    entry_url: str,
    validation_rules: list[str],
) -> ScenarioResult:
    query = str(params.get("query", "")).strip()
    material_id = params.get("material_id", "MAT-000000")
    if not query:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=f"{subject_zh} 缺少检索关键词，请先确认关键词池。",
        )

    snapshot_dir = task_dir / "downloads" / material_type
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{material_id}_{scenario_id}.html"

    try:
        html, final_url, status_code = fetch_html(entry_url)
    except Exception as exc:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{subject_zh} 访问失败，已记录为采集失败：{exc}",
        )

    restriction = detect_restriction(html, final_url, status_code)
    if restriction:
        return restriction_result(subject_zh, f"入口页返回受限或空白内容（{restriction.value}）。", restriction)
    http_error = http_error_result(subject_zh, status_code, final_url)
    if http_error:
        return http_error

    snapshot_path.write_text(html, encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    page_text = soup.get_text(" ", strip=True).lower()
    tokens = normalized_tokens(query)
    matched_query = any(token in page_text for token in tokens) if tokens else False
    links = []
    for anchor in soup.find_all("a"):
        text = anchor.get_text(" ", strip=True)
        href = anchor.get("href")
        if not text or not href:
            continue
        lower_text = text.lower()
        if not tokens or any(token in lower_text for token in tokens):
            links.append({"text": text, "url": urljoin(entry_url, href)})
        if len(links) >= 5:
            break

    if not matched_query and not links:
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{subject_zh} 已访问入口页，但未发现与“{query}”直接匹配的公开条目。",
        )

    return ScenarioResult(
        status="needs_manual_review",
        failure_type=FailureType.NEEDS_MANUAL_REVIEW,
        message_zh=(
            f"{subject_zh} 仅到达入口页，已保存诊断快照 {snapshot_path.relative_to(task_dir)}；"
            "尚未完成站内搜索、详情页解析或附件下载，因此未生成正式材料。"
        ),
    )
