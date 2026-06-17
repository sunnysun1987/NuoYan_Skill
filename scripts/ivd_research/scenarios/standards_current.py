import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from ivd_research.models import FailureType, Material
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


SCENARIO_ID = "standards_current"
MATERIAL_TYPE = "standard"
SUBJECT_ZH = "现行标准查询"
SEARCH_URL_TEMPLATE = "https://std.samr.gov.cn/search/std?q={query}"
STD_PAGE_URL_TEMPLATE = "https://std.samr.gov.cn/search/stdPage?q={query}&tid="
NO_RESULT_MARKERS = ("没有查询到数据", "暂无数据", "无查询结果", "未查询到")
VALIDATION_RULES = [
    "标准状态为现行，且列表包含标准号和标准名称",
    "collection_failed",
    "no_results",
]

HEADER_ALIASES = {
    "standard_no": ("标准号", "标准编号", "标准代号", "编号"),
    "standard_name": ("标准名称", "中文名称", "名称", "标准中文名称"),
    "status": ("状态", "标准状态"),
    "standard_type": ("标准类型", "类型", "标准类别"),
    "ics": ("ICS", "ICS号", "ICS分类号", "国际标准分类号"),
    "ccs": ("CCS", "CCS号", "中国标准分类号"),
    "responsible_unit": ("归口单位", "主管部门", "归口部门", "技术归口"),
    "region": ("地区", "所属地区", "区域/地方", "国家地区"),
    "trade": ("所属行业", "行业"),
    "publish_date": ("发布日期", "发布于", "发布时间"),
    "implementation_date": ("实施日期", "实施于", "实施时间"),
}

STANDARD_NO_RE = re.compile(
    r"\b(?:GB/T|GB|YY/T|YY|SN/T|SB/T|DB\d+/T|DB\d+)\s*[\w.]+(?:\s*-\s*\d{4})?\b",
    re.IGNORECASE,
)
DATE_PAIR_RE = re.compile(r"发布于\s*(\d{4}-\d{2}-\d{2})\s*实施于\s*(\d{4}-\d{2}-\d{2})")
ICS_CCS_RE = re.compile(
    r"国际标准分类号（ICS）\s*([0-9.]+)\s+中国标准分类号（CCS）\s*([A-Z0-9]+)"
)


def adapter():
    return get_scenario(SCENARIO_ID)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _field_for_header(header: str) -> str | None:
    normalized = _clean_text(header).replace(" ", "").upper()
    for field, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias.replace(" ", "").upper() == normalized:
                return field
    return None


def _table_rows(soup: BeautifulSoup) -> list[dict[str, str]]:
    rows = []
    for table in soup.find_all("table"):
        headers: list[str] = []
        for tr in table.find_all("tr"):
            header_cells = [
                _clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all("th")
            ]
            data_cells = [
                _clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all("td")
            ]
            if header_cells:
                headers = header_cells
                continue
            if not headers or not data_cells:
                continue
            mapped = {}
            for header, value in dict(zip(headers, data_cells)).items():
                field = _field_for_header(header)
                if field and value:
                    mapped[field] = value
            if mapped.get("standard_no") and mapped.get("standard_name"):
                rows.append(mapped)
    return rows


def _text_after_label(text: str, label: str) -> str:
    marker = f"{label} "
    if marker not in text:
        return ""
    value = text.split(marker, 1)[1]
    for next_label in ("英文标题", "归口单位", "所属行业", "所属地区", "发布于", "实施于"):
        next_marker = f" {next_label} "
        if next_marker in value:
            value = value.split(next_marker, 1)[0]
    return _clean_text(value)


def _standard_row_from_card(card: Tag) -> dict[str, str] | None:
    text = _clean_text(card.get_text(" ", strip=True))
    match = STANDARD_NO_RE.search(text)
    if not match:
        return None
    standard_no = _clean_text(match.group(0).replace(" - ", "-"))
    tail = _clean_text(text[match.end() :])
    status = "现行" if " 现行 " in f" {tail} " else ("废止" if " 废止 " in f" {tail} " else "")
    standard_name = tail
    if status:
        standard_name = tail.split(status, 1)[0]
    standard_name = _clean_text(standard_name)

    standard_type = ""
    logo = card.select_one(".s-logo")
    if logo:
        standard_type = _clean_text(logo.get_text("", strip=True))

    row = {
        "standard_no": standard_no,
        "standard_name": standard_name,
        "status": status,
        "standard_type": standard_type,
        "ics": "",
        "ccs": "",
        "responsible_unit": _text_after_label(text, "归口单位"),
        "region": _text_after_label(text, "所属地区"),
        "trade": _text_after_label(text, "所属行业"),
        "publish_date": "",
        "implementation_date": "",
    }

    ics_match = ICS_CCS_RE.search(text)
    if ics_match:
        row["ics"] = ics_match.group(1)
        row["ccs"] = ics_match.group(2)

    date_match = DATE_PAIR_RE.search(text)
    if date_match:
        row["publish_date"] = date_match.group(1)
        row["implementation_date"] = date_match.group(2)
    return row if row["standard_no"] and row["standard_name"] else None


def _card_rows(soup: BeautifulSoup) -> list[dict[str, str]]:
    rows = []
    cards = soup.select(".post")
    if not cards:
        cards = soup.select(".panel")
    if not cards:
        cards = soup.select(".media")
    for card in cards:
        if not isinstance(card, Tag):
            continue
        row = _standard_row_from_card(card)
        if row and row not in rows:
            rows.append(row)
    return rows


def _rows_from_html(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = _table_rows(soup)
    if rows:
        return rows
    return _card_rows(soup)


def _fetch_standards_html(url: str) -> tuple[str, str, int]:
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            with httpx.Client(timeout=45.0, follow_redirects=True) as client:
                response = client.get(url, headers={"User-Agent": USER_AGENT})
            return response.text, str(response.url), response.status_code
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError("standards request failed")


def _is_current_standard_status(status: str) -> bool:
    normalized = _clean_text(status).lower()
    return normalized in {"现行", "current"} or normalized == "鐜拌"


def _standard_source_url(html: str, base_url: str, standard_no: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        text = _clean_text(anchor.get_text(" ", strip=True))
        if standard_no and standard_no in text:
            return urljoin(base_url, anchor["href"])
    return base_url


def parse_standards_current_html(
    html: str,
    *,
    task_id: str,
    material_id_prefix: str,
    query: str,
    source_url: str,
    snapshot_path: str = "",
    text_path: str = "",
    validation_rules: list[str] | None = None,
) -> ScenarioResult:
    text = page_text(html)
    if any(marker in text for marker in NO_RESULT_MARKERS):
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{SUBJECT_ZH} 未查询到与“{query}”匹配的公开结果。",
        )

    rows = _rows_from_html(html)
    if not rows:
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{SUBJECT_ZH} 未在页面中解析到标准号和标准名称。",
        )

    current_rows = [row for row in rows if _is_current_standard_status(row.get("status", ""))]
    if not current_rows:
        return ScenarioResult(
            status="no_results",
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"{SUBJECT_ZH} 未解析到现行标准材料。",
        )

    materials = []
    rules = validation_rules or VALIDATION_RULES
    for index, row in enumerate(current_rows, start=1):
        current_material_id = (
            material_id_prefix if index == 1 else f"{material_id_prefix}-{index:03d}"
        )
        standard_no = row.get("standard_no", "")
        standard_name = row.get("standard_name", "")
        status = row.get("status", "")
        raw_fields: dict[str, Any] = {
            "standard_no": standard_no,
            "standard_name": standard_name,
            "status": status,
            "standard_type": row.get("standard_type", ""),
            "ics": row.get("ics", ""),
            "ccs": row.get("ccs", ""),
            "responsible_unit": row.get("responsible_unit", ""),
            "region": row.get("region", ""),
            "trade": row.get("trade", ""),
            "publish_date": row.get("publish_date", ""),
            "implementation_date": row.get("implementation_date", ""),
            "validation_rules": rules,
            "current": True,
            "current_zh": status,
        }

        materials.append(
            Material(
                material_id=current_material_id,
                task_id=task_id,
                source_scenario=SCENARIO_ID,
                material_type=MATERIAL_TYPE,
                title=f"{standard_no} {standard_name}".strip(),
                source_url=_standard_source_url(html, source_url, standard_no),
                search_keyword_or_query=query,
                collection_path={
                    "scenario_id": SCENARIO_ID,
                    "search_url": source_url,
                    "snapshot": snapshot_path,
                },
                collection_time=now_iso(),
                adapter_id=SCENARIO_ID,
                adapter_version="0.5.0",
                raw_fields=raw_fields,
                download_status="snapshot_saved" if snapshot_path else "not_attempted",
                extracted_text_status="completed" if text_path else "not_attempted",
                extracted_text_path=text_path,
                content_snapshot_path=snapshot_path,
            )
        )

    return ScenarioResult(
        status="completed",
        materials=materials,
        message_zh=f"{SUBJECT_ZH} 已解析 {len(materials)} 条标准材料。",
    )


def collect(task_id, task_dir, params):
    failure_modes = ("collection_failed", "no_results")
    validation_rules = [VALIDATION_RULES[0], *failure_modes]
    query = str(params.get("query", "")).strip()
    material_id = params.get("material_id", "MAT-000000")
    task_dir = Path(task_dir)
    if not query:
        return ScenarioResult(
            status="needs_manual_review",
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=f"{SUBJECT_ZH} 缺少检索关键词，请先确认关键词池。",
        )

    fixture_html = params.get("html")
    if fixture_html is None and params.get("html_fixture_path"):
        fixture_html = Path(params["html_fixture_path"]).read_text(
            encoding="utf-8", errors="ignore"
        )

    if fixture_html is not None:
        return parse_standards_current_html(
            str(fixture_html),
            task_id=task_id,
            material_id_prefix=material_id,
            query=query,
            source_url=str(
                params.get("source_url", STD_PAGE_URL_TEMPLATE.format(query=quote(query)))
            ),
            validation_rules=validation_rules,
        )

    search_url = STD_PAGE_URL_TEMPLATE.format(query=quote(query))
    try:
        html, final_url, status_code = _fetch_standards_html(search_url)
    except Exception as exc:
        return ScenarioResult(
            status="collection_failed",
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh=f"{SUBJECT_ZH} 搜索页访问失败：{exc}",
        )

    restriction = detect_restriction(html, final_url, status_code)
    if restriction:
        return ScenarioResult(
            status=restriction.value,
            failure_type=restriction,
            message_zh=f"{SUBJECT_ZH} 搜索页返回受限或空白内容（{restriction.value}）。",
        )
    http_error = http_error_result(SUBJECT_ZH, status_code, final_url)
    if http_error:
        return http_error

    snapshot = save_snapshot(
        task_dir, MATERIAL_TYPE, f"{material_id}_{SCENARIO_ID}_search.html", html
    )
    text_path = save_text(
        task_dir, MATERIAL_TYPE, f"{material_id}_{SCENARIO_ID}.txt", page_text(html)
    )
    return parse_standards_current_html(
        html,
        task_id=task_id,
        material_id_prefix=material_id,
        query=query,
        source_url=final_url,
        snapshot_path=snapshot,
        text_path=text_path,
        validation_rules=validation_rules,
    )
