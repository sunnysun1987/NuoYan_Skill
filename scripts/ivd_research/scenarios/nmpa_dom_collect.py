"""NMPA competitor collection via Playwright DOM interaction.

Instead of waiting for the SPA's pajax JavaScript API objects to be ready
(which fails in headless / CDP scenarios), this module simulates human
interaction with the NMPA search form:
  1. Navigate to the search page
  2. Click the category tab ("境内医疗器械（注册）" or "进口医疗器械（注册）")
  3. Type the query in the search box
  4. Click the search button
  5. Wait for results to appear
  6. Click detail buttons and extract registration data
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from ivd_research.models import FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso
from ivd_research.scenarios.nmpa_competitor import _detect_methodology


NMPA_SEARCH_PAGE = (
    "https://www.nmpa.gov.cn/datasearch/home-index.html#category=ylqx"
)

REGISTRATION_TYPES = [
    "境内医疗器械（注册）",
    "进口医疗器械（注册）",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CERT_RE = re.compile(r"国械注[准进许][0-9A-Za-z]+")


def _normalize(text: str) -> str:
    return " ".join(str(text).split())


def _wait_stable(page: Any, timeout_ms: int = 8000) -> None:
    """Wait for the page to reach a stable state after navigation."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=max(3000, timeout_ms // 3))
    except Exception:
        pass


def _dismiss_popups(page: Any) -> list[str]:
    """Dismiss known NMPA popups / intro guides."""
    dismissed: list[str] = []
    # Try common close buttons
    for selector in [
        ".introjs-skipbutton",
        ".introjs-donebutton",
        "[aria-label='Close']",
        ".el-message-box__close",
        ".layui-layer-close",
        "button:has-text('关闭')",
        "button:has-text('确定')",
        "a:has-text('×')",
    ]:
        try:
            loc = page.locator(selector)
            if loc.count():
                loc.first.click(timeout=2000)
                dismissed.append(selector)
                time.sleep(0.3)
        except Exception:
            continue
    return dismissed


def _click_category_tab(page: Any, tab_text: str) -> bool:
    """Click a category tab button matching the given text."""
    for selector in [
        f"button:has-text('{tab_text}')",
        f"a:has-text('{tab_text}')",
        f"span:has-text('{tab_text}')",
        f"[title*='{tab_text}']",
    ]:
        try:
            loc = page.locator(selector)
            if loc.count():
                loc.first.click(timeout=3000)
                time.sleep(0.5)
                return True
        except Exception:
            continue
    return False


def _find_search_input(page: Any) -> Any | None:
    """Find the main search input box on the NMPA page."""
    for selector in [
        "input[type='text']",
        "input[name='searchValue']",
        "input[placeholder*='搜索']",
        "input[placeholder*='请输入']",
        ".el-input__inner",
    ]:
        try:
            loc = page.locator(selector)
            if loc.count():
                return loc.first
        except Exception:
            continue
    return None


def _find_search_button(page: Any) -> Any | None:
    """Find the search submit button."""
    for selector in [
        "button:has-text('搜索')",
        "button:has-text('查询')",
        "input[type='submit']",
        "button.el-button--primary",
        ".search-btn",
    ]:
        try:
            loc = page.locator(selector)
            if loc.count():
                return loc.first
        except Exception:
            continue
    return None


def collect_nmpa_dom(
    *,
    task_dir: Path,
    task_id: str,
    page: Any,
    context: Any,
    query: str,
    methodology: str = "",
    page_limit: int = 5,
    start_index: int = 1,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Collect NMPA registration data by interacting with the search form via DOM.

    This does NOT use pajax / JavaScript API objects — it clicks buttons and
    fills input fields like a human user.
    """
    paths: dict[str, Path] = {}
    base = task_dir / "downloads" / "browser_workflow" / "nmpa_competitor"
    for sub in ("snapshots", "detail_snapshots", "downloads", "api_raw"):
        p = base / sub
        p.mkdir(parents=True, exist_ok=True)
        paths[sub] = p

    collection_errors: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    detail_snapshot_paths: list[str] = []
    material_index = start_index - 1

    for reg_type in REGISTRATION_TYPES:
        try:
            # --- Navigate to the search page ---
            page.goto(NMPA_SEARCH_PAGE, wait_until="domcontentloaded", timeout=30000)
            _wait_stable(page)
            _dismiss_popups(page)

            # --- Click the category tab ---
            if not _click_category_tab(page, reg_type):
                collection_errors.append({
                    "registration_type": reg_type,
                    "status": FailureType.COLLECTION_FAILED.value,
                    "reason": f"Could not find category tab: {reg_type}",
                })
                continue
            time.sleep(0.5)

            # --- Type query in search box ---
            search_input = _find_search_input(page)
            if not search_input:
                collection_errors.append({
                    "registration_type": reg_type,
                    "status": FailureType.COLLECTION_FAILED.value,
                    "reason": "Could not find search input",
                })
                continue
            search_input.fill("")
            search_input.type(query, delay=50)
            time.sleep(0.3)

            # --- Click search button ---
            search_button = _find_search_button(page)
            if search_button:
                search_button.click(timeout=5000)
            else:
                # Try pressing Enter
                search_input.press("Enter")
            _wait_stable(page)
            _dismiss_popups(page)
            time.sleep(1.0)

            # --- Save search result snapshot ---
            snapshot_path = paths["snapshots"] / f"nmpa_{reg_type[:4]}_search.html"
            snapshot_path.write_text(page.content(), encoding="utf-8", errors="ignore")

            # --- Parse results: try multiple strategies ---
            results = _parse_results_from_page(page)

            if not results:
                # Try API approach as fallback
                try:
                    results = _try_api_fallback(page, query, reg_type, page_limit)
                except Exception:
                    pass

            if not results:
                collection_errors.append({
                    "registration_type": reg_type,
                    "status": FailureType.NO_RESULTS.value,
                    "reason": "No results found on page or via API fallback",
                })
                continue

            # --- Collect details for each result ---
            limited = results[:page_limit]
            for row in limited:
                if methodology and methodology not in row.get("product_name", ""):
                    continue
                material_index += 1
                material_id = f"MAT-{material_index:06d}"

                cert_no = row.get("cert_no", "")
                product_name = row.get("product_name", "")
                registrant = row.get("registrant", "")

                # Try to click detail button
                detail_data = _click_detail(page, row, context)
                if not detail_data:
                    detail_data = row  # Fall back to list view data

                full_text = _format_detail_text(detail_data)

                # Save extracted text
                text_dir = task_dir / "extracted_text" / "competitors"
                text_dir.mkdir(parents=True, exist_ok=True)
                text_path = text_dir / f"{material_id}_nmpa_dom.txt"
                text_path.write_text(full_text, encoding="utf-8", errors="ignore")
                rel_text = str(text_path.relative_to(task_dir))

                detail_snapshot_path = paths["detail_snapshots"] / f"{material_id}.html"
                detail_snapshot_path.write_text(
                    f"<pre>{full_text}</pre>", encoding="utf-8", errors="ignore"
                )
                detail_rel = str(detail_snapshot_path.relative_to(task_dir))
                detail_snapshot_paths.append(detail_rel)

                materials.append({
                    "material_id": material_id,
                    "task_id": task_id,
                    "source_scenario": "nmpa_competitor",
                    "material_type": "competitor",
                    "title": product_name,
                    "source_url": NMPA_SEARCH_PAGE,
                    "search_keyword_or_query": query,
                    "collection_path": {
                        "scenario_id": "nmpa_competitor",
                        "registration_type": reg_type,
                        "collected_via": "nmpa_dom",
                    },
                    "collection_time": now_iso(),
                    "adapter_id": "nmpa_dom",
                    "adapter_version": "3.0.0",
                    "raw_fields": {
                        "registration_certificate_number": cert_no,
                        "registrant": registrant,
                        "product_name": product_name,
                        "methodology": _detect_methodology(
                            f"{product_name} {detail_data.get('scope', '')}"
                        ),
                        "scope": detail_data.get("scope", ""),
                        "approval_date": detail_data.get("approval_date", ""),
                        "full_visible_text": full_text,
                        "registration_type": reg_type,
                    },
                    "download_status": "not_applicable",
                    "extracted_text_status": "completed",
                    "extracted_text_path": rel_text,
                    "content_snapshot_path": rel_text,
                })
        except Exception as exc:
            collection_errors.append({
                "registration_type": reg_type,
                "status": FailureType.COLLECTION_FAILED.value,
                "reason": str(exc),
            })

    return materials, detail_snapshot_paths, collection_errors


def _parse_results_from_page(page: Any) -> list[dict[str, str]]:
    """Parse search result rows from the current page using DOM selectors."""
    results: list[dict[str, str]] = []
    try:
        # Try table rows first
        rows = page.locator("table tbody tr, .el-table__body tr, .list-table tr, .result-table tr")
        if rows.count() == 0:
            rows = page.locator("tr:has(td)")

        for i in range(rows.count()):
            try:
                row = rows.nth(i)
                text = row.inner_text()
                cert_match = CERT_RE.search(text)
                if not cert_match:
                    continue

                cells = row.locator("td")
                cell_texts = []
                for j in range(min(cells.count(), 5)):
                    cell_texts.append(_normalize(cells.nth(j).inner_text()))

                results.append({
                    "cert_no": cert_match.group(0),
                    "product_name": cell_texts[3] if len(cell_texts) > 3 else "",
                    "registrant": cell_texts[2] if len(cell_texts) > 2 else "",
                    "row_text": _normalize(text)[:500],
                })
            except Exception:
                continue
    except Exception:
        pass

    # If table parsing failed, try extracting from page text
    if not results:
        try:
            text = page.inner_text("body")
            for match in CERT_RE.finditer(text):
                cert = match.group(0)
                # Get surrounding text
                start = max(0, match.start() - 200)
                end = min(len(text), match.end() + 300)
                ctx = text[start:end]
                results.append({
                    "cert_no": cert,
                    "product_name": "",
                    "registrant": "",
                    "row_text": _normalize(ctx),
                })
        except Exception:
            pass

    return results


def _try_api_fallback(page: Any, query: str, reg_type: str, page_limit: int) -> list[dict[str, str]]:
    """Try the pajax API as a fallback when DOM parsing fails."""
    results: list[dict[str, str]] = []
    item_ids = {
        "境内医疗器械（注册）": "ff80808183cad7500183cb66fe690285",
        "进口医疗器械（注册）": "ff808081830b103501838d4871b53543",
    }
    item_id = item_ids.get(reg_type)
    if not item_id:
        return results

    js = """
    async ({itemId, query, pageSize}) => {
        try {
            const r = await pajax.hasTokenGet(api.queryList, {
                itemId, searchValue: query, pageNum: 1, pageSize
            });
            const list = ((((r || {}).data || {}).data || {}).list || []);
            return list.map(row => ({
                cert_no: row.f0 || '',
                product_name: row.f2 || '',
                registrant: row.f1 || '',
                record_id: row.f3 || ''
            }));
        } catch(e) { return []; }
    }
    """
    try:
        result = page.evaluate(js, {"itemId": item_id, "query": query, "pageSize": page_limit})
        results = list(result or [])
    except Exception:
        pass
    return results


def _click_detail(page: Any, row: dict[str, str], context: Any) -> dict[str, str] | None:
    """Click the detail button for a result row and extract detail data."""
    try:
        # Try clicking a detail link/button
        clicked = False
        for selector in [
            "a:has-text('详情')",
            "button:has-text('详情')",
            "a.detail",
            ".detail-btn",
        ]:
            try:
                loc = page.locator(selector)
                if loc.count():
                    # Open in new page
                    with context.expect_page(timeout=5000) as new_page_info:
                        loc.first.click(timeout=3000)
                    new_page = new_page_info.value
                    new_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    text = new_page.inner_text("body")
                    new_page.close()
                    clicked = True
                    return _parse_detail_text(text)
            except Exception:
                continue

        if not clicked:
            # Try API fallback for detail
            return None
    except Exception:
        return None
    return None


def _parse_detail_text(text: str) -> dict[str, str]:
    """Parse NMPA detail page text into structured fields."""
    fields: dict[str, str] = {}
    labels = {
        "注册证编号": "cert_no",
        "注册人名称": "registrant",
        "产品名称": "product_name",
        "管理类别": "management_category",
        "规格型号": "specification",
        "结构及组成": "structure",
        "适用范围": "scope",
        "预期用途": "scope",
        "批准日期": "approval_date",
        "有效期至": "expiry_date",
    }
    for label, key in labels.items():
        match = re.search(rf"{label}[：:]\s*(.+?)(?:\s*(?:；|$|\n))", text)
        if match:
            fields[key] = _normalize(match.group(1))
    fields["full_text"] = _normalize(text)[:5000]
    return fields


def _format_detail_text(data: dict[str, str]) -> str:
    """Format detail data as readable text."""
    lines = []
    for label, key in [
        ("注册证编号", "cert_no"),
        ("注册人名称", "registrant"),
        ("产品名称", "product_name"),
        ("适用范围", "scope"),
        ("批准日期", "approval_date"),
        ("有效期至", "expiry_date"),
        ("管理类别", "management_category"),
        ("规格型号", "specification"),
    ]:
        val = data.get(key, "")
        if val:
            lines.append(f"{label}：{val}")
    return "\n".join(lines) if lines else data.get("full_text", "")
