"""Direct HTTP access to the NMPA medical-device registration search API.

This bypasses the SPA page entirely by calling the backend API endpoints
directly.  The API was reverse-engineered from the browser-collect diagnostic
payloads saved during earlier runs.

API endpoints
-------------
- Search:  POST https://www.nmpa.gov.cn/datasearch/data/nmpadata/search
- Detail:  POST https://www.nmpa.gov.cn/datasearch/data/nmpadata/queryDetail

Item IDs (stable across sessions)
---------------------------------
- 境内医疗器械（注册）: ff80808183cad7500183cb66fe690285
- 进口医疗器械（注册）: ff808081830b103501838d4871b53543
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from ivd_research.models import FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso

NMPA_SEARCH_URL = "https://www.nmpa.gov.cn/datasearch/data/nmpadata/search"
NMPA_DETAIL_URL = "https://www.nmpa.gov.cn/datasearch/data/nmpadata/queryDetail"
NMPA_HOME_URL = "https://www.nmpa.gov.cn/datasearch/home-index.html"

REGISTRATION_TYPES: dict[str, str] = {
    "境内医疗器械（注册）": "ff80808183cad7500183cb66fe690285",
    "进口医疗器械（注册）": "ff808081830b103501838d4871b53543",
}

# Mapping of API detail field keys to human-readable labels
NMPA_DETAIL_FIELDS: dict[str, tuple[str, str]] = {
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

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

KNOWN_METHODOLOGIES = [
    "荧光PCR法",
    "PCR法",
    "PCR-荧光探针法",
    "胶体金法",
    "酶联免疫法",
    "化学发光免疫分析法",
    "化学发光法",
    "免疫层析法",
    "免疫荧光法",
    "乳胶法",
    "磁微粒化学发光法",
    "间接免疫荧光法",
    "流式荧光发光法",
    "实时荧光PCR法",
    "荧光定量PCR法",
    "PCR-反向点杂交法",
    "环介导等温扩增法",
    "重组酶介导链替换核酸扩增法",
]


def _detect_methodology(text: str) -> str:
    """Extract methodology from product name or scope text."""
    for method in KNOWN_METHODOLOGIES:
        if method in text:
            return method
    # Heuristic: look for （...法） pattern
    import re
    match = re.search(r"[（(]([^)）]*法)[）)]", text)
    if match:
        return match.group(1)
    return ""


def _normalize(text: str) -> str:
    return " ".join(str(text).split())


def _build_raw_fields(detail: dict[str, str]) -> dict[str, Any]:
    """Build the raw_fields dict expected by build_nmpa_api_material."""
    fields: dict[str, Any] = {}
    for key, (norm_key, label_zh) in NMPA_DETAIL_FIELDS.items():
        value = _normalize(detail.get(key, ""))
        fields[norm_key] = value
    full_visible = "；".join(
        f"{label_zh}: {fields[norm_key]}"
        for key, (norm_key, label_zh) in NMPA_DETAIL_FIELDS.items()
        if fields[norm_key]
    )
    fields["full_visible_text"] = full_visible
    fields["methodology"] = _detect_methodology(
        " ".join([
            fields.get("product_name", ""),
            fields.get("scope", ""),
            fields.get("structure_and_composition", ""),
        ])
    )
    return fields


def fetch_nmpa_search(
    query: str,
    item_id: str,
    page_num: int = 1,
    page_size: int = 20,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Call the NMPA search API directly via HTTP POST.

    Returns the decoded JSON response from the search endpoint.
    """
    _client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    payload = {
        "itemId": item_id,
        "searchValue": query,
        "pageNum": page_num,
        "pageSize": min(page_size, 20),
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nmpa.gov.cn/datasearch/home-index.html",
    }
    response = None
    try:
        response = _client.post(NMPA_SEARCH_URL, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        return {"error": str(exc), "code": getattr(response, "status_code", 0) if response is not None else 0}
    return body


def fetch_nmpa_detail(
    item_id: str,
    nmpa_record_id: str,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Call the NMPA detail API directly via HTTP POST."""
    _client = client or httpx.Client(timeout=30.0, follow_redirects=True)
    payload = {
        "itemId": item_id,
        "nmpaRecordId": nmpa_record_id,
    }
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json;charset=UTF-8",
        "Accept": "application/json, */*",
        "Referer": "https://www.nmpa.gov.cn/datasearch/home-index.html",
    }
    try:
        response = _client.post(NMPA_DETAIL_URL, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        return {"error": str(exc), "code": getattr(response, "status_code", 0)}
    return body


def collect_nmpa_http(
    *,
    task_id: str,
    task_dir: Path,
    query: str,
    material_id_prefix: str,
    methodology: str = "",
    registration_types: list[str] | None = None,
    page_limit: int = 5,
    page_size: int = 20,
) -> ScenarioResult:
    """Collect NMPA competitor registration data via direct HTTP API calls.

    This does NOT require Playwright — it calls the NMPA backend API directly,
    the same endpoints the SPA page would call via pajax.hasTokenGet().
    """
    wanted_types = registration_types or list(REGISTRATION_TYPES.keys())
    materials: list[Material] = []
    collection_errors: list[dict[str, Any]] = []
    material_index = 0
    total_found = 0

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for reg_type in wanted_types:
            item_id = REGISTRATION_TYPES.get(reg_type)
            if not item_id:
                collection_errors.append({
                    "registration_type": reg_type,
                    "status": "unsupported",
                    "reason": f"Unknown registration type: {reg_type}",
                })
                continue

            # First, get page 1 to determine total count
            search_result = fetch_nmpa_search(query, item_id, page_num=1, page_size=page_size, client=client)
            if search_result.get("error"):
                collection_errors.append({
                    "registration_type": reg_type,
                    "status": FailureType.COLLECTION_FAILED.value,
                    "reason": search_result["error"],
                })
                continue

            if search_result.get("code") != 200:
                collection_errors.append({
                    "registration_type": reg_type,
                    "status": FailureType.COLLECTION_FAILED.value,
                    "reason": f"API returned code {search_result.get('code')}",
                })
                continue

            data = search_result.get("data") or {}
            total = int(data.get("total", 0))
            total_found += total

            if total == 0:
                continue

            pages_needed = min(page_limit, -(-total // page_size))  # ceil division
            all_list_items = list(data.get("list", []))

            # Fetch remaining pages
            for page_num in range(2, pages_needed + 1):
                time.sleep(0.3)  # polite delay
                page_result = fetch_nmpa_search(query, item_id, page_num=page_num, page_size=page_size, client=client)
                if page_result.get("error"):
                    collection_errors.append({
                        "registration_type": reg_type,
                        "page": page_num,
                        "status": FailureType.COLLECTION_FAILED.value,
                        "reason": page_result["error"],
                    })
                    continue
                page_data = page_result.get("data") or {}
                all_list_items.extend(page_data.get("list", []))

            # Fetch details for each result
            for row in all_list_items:
                nmpa_record_id = row.get("f3", "")
                if not nmpa_record_id:
                    continue

                # Apply methodology filter
                product_name = row.get("f2", "")
                if methodology and methodology not in product_name:
                    continue

                material_index += 1
                material_id = material_id_prefix if material_index == 1 else f"{material_id_prefix}-{material_index:03d}"

                time.sleep(0.2)  # polite delay
                detail_result = fetch_nmpa_detail(item_id, nmpa_record_id, client=client)
                if detail_result.get("error"):
                    collection_errors.append({
                        "registration_type": reg_type,
                        "record_id": nmpa_record_id,
                        "status": FailureType.COLLECTION_FAILED.value,
                        "reason": detail_result["error"],
                    })
                    continue

                detail_data = (
                    detail_result.get("data", {}).get("detail") or {}
                )
                if not detail_data:
                    collection_errors.append({
                        "registration_type": reg_type,
                        "record_id": nmpa_record_id,
                        "status": FailureType.NO_VALID_MATERIALS.value,
                        "reason": "Empty detail response",
                    })
                    continue

                raw_fields = _build_raw_fields(detail_data)
                raw_fields["registration_type"] = reg_type
                raw_fields["list_row"] = row

                full_visible = raw_fields.get("full_visible_text", "")
                product_name = raw_fields.get("product_name") or row.get("f2", "NMPA 注册详情")

                text_dir = task_dir / "extracted_text" / "competitors"
                text_dir.mkdir(parents=True, exist_ok=True)
                text_path = text_dir / f"{material_id}_nmpa.txt"
                text_path.write_text(full_visible, encoding="utf-8", errors="ignore")

                materials.append(
                    Material(
                        material_id=material_id,
                        task_id=task_id,
                        source_scenario="nmpa_competitor",
                        material_type="competitor",
                        title=product_name,
                        source_url="https://www.nmpa.gov.cn/datasearch/home-index.html#category=ylqx",
                        search_keyword_or_query=query,
                        collection_path={
                            "scenario_id": "nmpa_competitor",
                            "search_url": NMPA_SEARCH_URL,
                            "registration_type": reg_type,
                            "item_id": item_id,
                            "nmpa_record_id": nmpa_record_id,
                            "collected_via": "nmpa_http_api",
                        },
                        collection_time=now_iso(),
                        adapter_id="nmpa_http_api",
                        adapter_version="2.0.0",
                        raw_fields=raw_fields,
                        download_status="not_applicable",
                        extracted_text_status="completed",
                        extracted_text_path=str(text_path.relative_to(task_dir)),
                        content_snapshot_path=str(text_path.relative_to(task_dir)),
                    )
                )

    if not materials:
        status = FailureType.COLLECTION_FAILED.value if collection_errors else FailureType.NO_RESULTS.value
        return ScenarioResult(
            status=status,
            failure_type=FailureType.COLLECTION_FAILED if collection_errors else FailureType.NO_RESULTS,
            message_zh=(
                f"NMPA HTTP API 未采集到符合条件的竞品详情。"
                f"{f' 错误数 {len(collection_errors)}。' if collection_errors else ''}"
                f"{f' 列表共 {total_found} 条，已按方法学 {methodology} 过滤。' if methodology else ''}"
            ),
            collection_errors=collection_errors,
        )

    msg = (
        f"NMPA HTTP API 已采集 {len(materials)} 条竞品详情"
        f"（共检索到 {total_found} 条记录"
    )
    if methodology:
        msg += f"，已按方法学 {methodology} 过滤"
    msg += "）。"
    return ScenarioResult(
        status="completed",
        materials=materials,
        message_zh=msg,
        collection_errors=collection_errors,
    )
