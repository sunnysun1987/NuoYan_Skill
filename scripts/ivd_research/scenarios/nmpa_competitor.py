import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ivd_research.models import FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso

from .registry import get_scenario
from .site_collect import collect_site


REGISTRATION_CERT_RE = re.compile(r"国械注[准进许][0-9A-Za-z]+")


def adapter():
    return get_scenario("nmpa_competitor")


def collect(task_id, task_dir, params):
    query = str(params.get("query", "")).strip()
    methodology = str(params.get("methodology", "")).strip()
    material_id = params.get("material_id", "MAT-000000")
    if not query:
        failure_modes = ("collection_failed", "no_results")
        return collect_site(
            task_id=task_id,
            task_dir=task_dir,
            params=params,
            scenario_id="nmpa_competitor",
            material_type="competitor",
            subject_zh="NMPA 竞品注册信息",
            entry_url="https://www.nmpa.gov.cn/datasearch/home-index.html#category=ylqx",
            validation_rules=["结果包含注册证编号、注册人、产品名称和详情", *failure_modes],
        )

    # Strategy 1: clean HTTP API (fast, no browser)
    try:
        from .nmpa_api import collect_nmpa_http
    except Exception:
        collect_nmpa_http = None

    if collect_nmpa_http is not None:
        result = collect_nmpa_http(
            task_id=task_id,
            task_dir=Path(task_dir),
            query=query,
            material_id_prefix=material_id,
            methodology=methodology,
        )
        if result.status == "completed":
            return result
        # HTTP API failed (typical: WAF 412) → fall through

    # Strategy 2: Edge CDP two-phase collection (list → details)
    # Uses the new nmpa_browser_api module with proper pagination,
    # category-level separation, and pajax Promise wrapping.
    try:
        from .nmpa_browser_api import collect_nmpa_headless

        edge_result = collect_nmpa_headless(
            task_dir=Path(task_dir),
            task_id=task_id,
            query=query,
            material_id_prefix=material_id,
            methodology=methodology,
            page_limit=int(params.get("page_limit", 0) or 0),
        )
        if edge_result.status == "completed" or "未找到 Edge" not in edge_result.message_zh:
            return edge_result
    except ImportError:
        pass
    except Exception:
        pass

    # Strategy 3: Playwright DOM fallback when Edge is unavailable.
    try:
        from playwright.sync_api import sync_playwright
        from .nmpa_dom_collect import collect_nmpa_dom

        start_index = _material_start_index(str(material_id))
        page_limit = int(params.get("page_limit", 0) or 0) or 5
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(locale="zh-CN")
            page = context.new_page()
            try:
                material_dicts, _, errors = collect_nmpa_dom(
                    task_dir=Path(task_dir),
                    task_id=task_id,
                    page=page,
                    context=context,
                    query=query,
                    methodology=methodology,
                    page_limit=page_limit,
                    start_index=start_index,
                )
            finally:
                context.close()
                browser.close()
        materials = [Material.model_validate(item) for item in material_dicts]
        if materials:
            return ScenarioResult(
                status="completed",
                materials=materials,
                message_zh=f"NMPA Playwright DOM 兜底采集完成，解析竞品/注册材料 {len(materials)} 条。",
                collection_errors=errors,
            )
        return ScenarioResult(
            status=FailureType.NO_RESULTS.value,
            failure_type=FailureType.NO_RESULTS,
            message_zh=(
                f"NMPA 已在 Edge 缺失时改用 Playwright DOM 兜底检索，但未查询到与“{query}”匹配的注册材料。"
                "建议缩小到产品核心名、检测项目或方法学后重试。"
            ),
            collection_errors=errors,
        )
    except Exception as exc:
        return ScenarioResult(
            status=FailureType.NEEDS_MANUAL_REVIEW.value,
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh=(
                "NMPA Edge 不可用，Playwright DOM 兜底也未完成。"
                f"建议安装 Microsoft Edge 或使用更窄检索词后人工复核。错误：{type(exc).__name__}: {exc}"
            ),
        )

    # Strategy 4: no Playwright / no Edge available
    return ScenarioResult(
        status=FailureType.NEEDS_MANUAL_REVIEW.value,
        failure_type=FailureType.NEEDS_MANUAL_REVIEW,
        message_zh=(
            "NMPA 竞品信息采集需要 Playwright + Edge 浏览器。"
            "请安装：pip install playwright && playwright install chromium"
        ),
    )


def _material_start_index(material_id: str) -> int:
    match = re.search(r"MAT-(\d+)", str(material_id or ""))
    return int(match.group(1)) if match else 1


def parse_nmpa_result_list(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        headers = _table_headers(row)
        row_data = {
            _normalize_space(header): _normalize_space(cell.get_text(" ", strip=True))
            for header, cell in zip(headers, cells)
            if _normalize_space(header)
        }
        visible_text = _normalize_space(row.get_text(" ", strip=True))
        certificate = _first_by_labels(row_data, ["注册证编号", "注册证号", "注册证"])
        if not certificate:
            certificate = _first_registration_certificate(visible_text)
        anchor = row.find("a", href=True)
        detail_url = urljoin(base_url, anchor["href"]) if anchor else ""
        product_name = (
            _first_by_labels(row_data, ["产品名称", "产品名", "名称"])
            or (_normalize_space(anchor.get_text(" ", strip=True)) if anchor else "")
            or (cells[1].get_text(" ", strip=True) if len(cells) > 1 else "")
        )
        registrant = _first_by_labels(row_data, ["注册人名称", "注册人", "申请人"]) or (
            cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
        )
        registration_type = _first_by_labels(row_data, ["注册类型", "数据类型", "类别"]) or (
            cells[3].get_text(" ", strip=True) if len(cells) > 3 else ""
        )
        unique_key = detail_url or certificate
        if not unique_key or unique_key in seen:
            continue
        seen.add(unique_key)
        entries.append(
            {
                "list_index": len(entries) + 1,
                "registration_certificate_number": _normalize_space(certificate),
                "product_name": _normalize_space(product_name),
                "registrant": _normalize_space(registrant),
                "registration_type": _normalize_space(registration_type),
                "detail_url": detail_url,
                "visible_text": visible_text,
            }
        )
    return entries


def parse_nmpa_detail(html: str, detail_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    fields = _detail_fields(soup)
    full_visible_text = _normalize_space(soup.get_text(" ", strip=True))
    title_node = soup.find("h1") or soup.find("title")
    title = _normalize_space(title_node.get_text(" ", strip=True)) if title_node else ""
    return {
        "detail_url": detail_url,
        "title": title,
        "registration_certificate_number": _field_or_regex(
            fields,
            ["注册证编号", "注册证号", "注册证"],
            full_visible_text,
        ),
        "registrant": _first_by_labels(fields, ["注册人名称", "注册人", "申请人"]),
        "product_name": _first_by_labels(fields, ["产品名称", "产品名", "名称"]) or title,
        "methodology": _first_by_labels(fields, ["检测原理", "方法学", "检验方法"]),
        "scope": _first_by_labels(fields, ["适用范围", "预期用途"]),
        "approval_date": _first_by_labels(fields, ["批准日期", "发证日期", "批准时间"]),
        "full_visible_text": full_visible_text,
    }


def build_nmpa_material(
    *,
    task_id: str,
    material_id: str,
    query: str,
    search_url: str,
    search_snapshot: str,
    detail_snapshot: str,
    entry: dict[str, Any],
    detail: dict[str, Any],
) -> Material:
    registration_certificate_number = (
        detail.get("registration_certificate_number")
        or entry.get("registration_certificate_number", "")
    )
    product_name = detail.get("product_name") or entry.get("product_name") or "NMPA 注册详情"
    registrant = detail.get("registrant") or entry.get("registrant", "")
    return Material(
        material_id=material_id,
        task_id=task_id,
        source_scenario="nmpa_competitor",
        material_type="competitor",
        title=product_name,
        source_url=entry.get("detail_url") or detail.get("detail_url", ""),
        search_keyword_or_query=query,
        collection_path={
            "scenario_id": "nmpa_competitor",
            "search_url": search_url,
            "detail_url": entry.get("detail_url") or detail.get("detail_url", ""),
            "search_snapshot": search_snapshot,
            "detail_snapshot": detail_snapshot,
            "list_index": entry.get("list_index"),
        },
        collection_time=now_iso(),
        adapter_id="nmpa_competitor",
        adapter_version="0.2.0",
        raw_fields={
            "registration_certificate_number": registration_certificate_number,
            "registrant": registrant,
            "product_name": product_name,
            "methodology": detail.get("methodology", ""),
            "scope": detail.get("scope", ""),
            "approval_date": detail.get("approval_date", ""),
            "registration_type": entry.get("registration_type", ""),
            "list_visible_text": entry.get("visible_text", ""),
            "full_visible_text": detail.get("full_visible_text", ""),
        },
        download_status="not_attempted",
        extracted_text_status="completed" if detail.get("full_visible_text") else "not_attempted",
        content_snapshot_path=detail_snapshot,
    )


NMPA_DETAIL_FIELD_LABELS = {
    "f0": ("registration_certificate_number", "注册证编号"),
    "f1": ("registrant", "注册人名称"),
    "f2": ("registrant_address", "注册人住所"),
    "f3": ("production_address", "生产地址"),
    "f4": ("product_name", "产品名称"),
    "f5": ("management_category", "管理类别"),
    "f6": ("specification", "规格型号"),
    "f7": ("structure_and_composition", "结构及组成"),
    "f8": ("scope", "适用范围/预期用途"),
    "f9": ("storage_condition", "储存条件"),
    "f10": ("attachments", "附件"),
    "f11": ("change_record", "变更情况"),
    "f12": ("remarks", "备注"),
    "f13": ("approval_department", "审批部门"),
    "f14": ("approval_date", "批准日期"),
    "f15": ("issue_date", "发证日期"),
    "f16": ("expiry_date", "有效期至"),
    "f17": ("agent", "代理人/变更记录"),
    "f18": ("nmpa_record_id", "NMPA记录ID"),
}


def normalize_nmpa_api_detail(detail: dict[str, Any]) -> dict[str, Any]:
    fields = {
        normalized_key: detail.get(raw_key) or ""
        for raw_key, (normalized_key, _label_zh) in NMPA_DETAIL_FIELD_LABELS.items()
    }
    full_visible_text = "；".join(
        f"{label_zh}: {fields[normalized_key]}"
        for _raw_key, (normalized_key, label_zh) in NMPA_DETAIL_FIELD_LABELS.items()
        if fields[normalized_key]
    )
    fields["methodology"] = _detect_methodology(
        " ".join(
            [
                fields.get("product_name", ""),
                fields.get("scope", ""),
                fields.get("structure_and_composition", ""),
            ]
        )
    )
    fields["full_visible_text"] = full_visible_text
    return fields


def build_nmpa_api_material(
    *,
    task_id: str,
    material_id: str,
    query: str,
    search_url: str,
    search_snapshot: str,
    detail_snapshot: str,
    registration_type: str,
    item_id: str,
    row: dict[str, Any],
    detail: dict[str, Any],
) -> Material:
    normalized = normalize_nmpa_api_detail(detail)
    product_name = normalized.get("product_name") or row.get("f2") or "NMPA 注册详情"
    registration_certificate_number = (
        normalized.get("registration_certificate_number") or row.get("f0") or ""
    )
    registrant = normalized.get("registrant") or row.get("f1") or ""
    return Material(
        material_id=material_id,
        task_id=task_id,
        source_scenario="nmpa_competitor",
        material_type="competitor",
        title=product_name,
        source_url=search_url,
        search_keyword_or_query=query,
        collection_path={
            "scenario_id": "nmpa_competitor",
            "search_url": search_url,
            "search_snapshot": search_snapshot,
            "detail_snapshot": detail_snapshot,
            "registration_type": registration_type,
            "item_id": item_id,
            "nmpa_record_id": row.get("f3") or normalized.get("nmpa_record_id", ""),
        },
        collection_time=now_iso(),
        adapter_id="nmpa_competitor",
        adapter_version="0.3.0",
        raw_fields={
            **normalized,
            "registration_certificate_number": registration_certificate_number,
            "registrant": registrant,
            "product_name": product_name,
            "registration_type": registration_type,
            "list_row": row,
        },
        download_status="not_applicable",
        extracted_text_status="completed" if normalized.get("full_visible_text") else "not_attempted",
        content_snapshot_path=detail_snapshot,
    )


def methodology_matches(detail: dict[str, Any], methodology: str) -> bool:
    expected = _normalize_space(methodology)
    if not expected:
        return True
    haystack = _normalize_space(
        " ".join(
            str(value or "")
            for value in [
                detail.get("methodology", ""),
                detail.get("product_name", ""),
                detail.get("title", ""),
                detail.get("full_visible_text", ""),
            ]
        )
    ).lower()
    return expected.lower() in haystack


def _detect_methodology(text: str) -> str:
    normalized = _normalize_space(text)
    known_methods = [
        "荧光PCR法",
        "PCR法",
        "胶体金法",
        "酶联免疫法",
        "化学发光免疫分析法",
        "免疫层析法",
    ]
    for method in known_methods:
        if method in normalized:
            return method
    return ""


def _normalize_space(text: str) -> str:
    return " ".join(str(text).split())


def _table_headers(row: Any) -> list[str]:
    table = row.find_parent("table")
    if not table:
        return []
    header_row = table.find("tr")
    if not header_row:
        return []
    return [cell.get_text(" ", strip=True) for cell in header_row.find_all(["th", "td"])]


def _first_by_labels(fields: dict[str, str], labels: list[str]) -> str:
    for label in labels:
        for key, value in fields.items():
            if label in key and value:
                return value
    return ""


def _first_registration_certificate(text: str) -> str:
    match = REGISTRATION_CERT_RE.search(text)
    return match.group(0) if match else ""


def _field_or_regex(fields: dict[str, str], labels: list[str], text: str) -> str:
    return _first_by_labels(fields, labels) or _first_registration_certificate(text)


def _detail_fields(soup: BeautifulSoup) -> dict[str, str]:
    fields: dict[str, str] = {}
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            fields[_normalize_space(dt.get_text(" ", strip=True))] = _normalize_space(
                dd.get_text(" ", strip=True)
            )
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = _normalize_space(cells[0].get_text(" ", strip=True))
            value = _normalize_space(cells[1].get_text(" ", strip=True))
            if key and value:
                fields.setdefault(key, value)
    return fields
