"""NMPA Edge CDP collector — two-phase approach.

Phase A: collect ALL list pages (list only, no details).
Phase B: fetch detail for each row (separately, with retry).

The JS evaluate only fetches ONE page at a time. Python controls the
pagination loop — no silent failures, every page has a diagnostic record.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ivd_research.models import FailureType, Material
from ivd_research.scenarios.base import ScenarioResult, now_iso

CATEGORIES = [
    {
        "key": "domestic_register",
        "label": "境内医疗器械（注册）",
        "itemId": "ff80808183cad7500183cb66fe690285",
    },
    {
        "key": "import_register",
        "label": "进口医疗器械（注册）",
        "itemId": "ff808081830b103501838d4871b53543",
    },
]

# Methodology patterns (long-match-first to avoid false positives)
METHOD_PATTERNS: list[tuple[str, str]] = [
    ("磁微粒化学发光法", r"磁微粒.*化学发光"),
    ("化学发光免疫分析法", r"化学发光(?:免疫)?(?:分析)?法?"),
    ("时间分辨荧光免疫分析法", r"时间分辨荧光(?:免疫)?(?:分析)?法?"),
    ("干式免疫荧光法", r"干式免疫荧光法?"),
    ("荧光免疫层析法", r"荧光免疫层析法?"),
    ("免疫荧光法", r"免疫荧光法?"),
    ("胶体金法", r"胶体金法?"),
    ("乳胶法", r"乳胶(?:免疫)?(?:比浊)?法?"),
    ("酶联免疫法", r"酶联免疫(?:吸附)?法?|elisa",),
    ("实时荧光PCR法", r"实时荧光pcr|荧光定量pcr|real[- ]?timepcr"),
    ("荧光PCR法", r"荧光pcr|pcr-?荧光探针"),
    ("PCR法", r"\bpcr\b"),
    ("恒温扩增法", r"恒温扩增|lamp|raa|rpa"),
    ("核酸测序法", r"测序|高通量测序|ngs"),
    ("微阵列芯片法", r"芯片法|微阵列"),
    ("免疫层析法", r"免疫层析法?"),
    ("培养法", r"培养法|分离培养"),
]

FETCH_ONE_PAGE_JS = """
async (params) => {
    const { itemId, query, pageNum, pageSize } = params;
    // pajax.hasTokenGet returns a Promise in the NMPA SPA
    if (typeof pajax !== 'undefined' && pajax.hasTokenGet && typeof api !== 'undefined' && api.queryList) {
        try {
            const data = await pajax.hasTokenGet(api.queryList, {
                itemId, searchValue: query, pageNum, pageSize
            });
            const listData = ((((data || {}).data || {}).data || {}));
            return {
                ok: true, transport: 'pajax',
                total: listData.total || 0,
                rows: listData.list || [],
                pageNum, pageSize,
            };
        } catch(e) {
            return {ok: false, errorType: 'pajax_error', errorMessage: e.message || String(e)};
        }
    }
    // Fallback to fetch
    try {
        const r = await fetch(api.queryList, {
            method: 'POST',
            headers: {'Content-Type': 'application/json;charset=UTF-8'},
            body: JSON.stringify({itemId, searchValue: query, pageNum, pageSize}),
            credentials: 'include',
        });
        if (!r.ok) return {ok: false, errorType: 'http_' + r.status};
        const j = await r.json();
        const listData = (j.data || {});
        return {ok: true, transport: 'fetch', total: listData.total || 0, rows: listData.list || [], pageNum, pageSize};
    } catch(e) {
        return {ok: false, errorType: 'fetch_error', errorMessage: e.message || String(e)};
    }
};
"""

FETCH_ONE_DETAIL_JS = """
async (params) => {
    const { itemId, detailId } = params;
    if (typeof pajax !== 'undefined' && pajax.hasTokenGet && typeof api !== 'undefined' && api.queryDetail) {
        try {
            const data = await pajax.hasTokenGet(api.queryDetail, { itemId, id: detailId });
            const detail = ((((data || {}).data || {}).data || {}).detail || {});
            return {ok: true, detail};
        } catch(e) {
            return {ok: false, errorType: 'detail_error', errorMessage: e.message || String(e)};
        }
    }
    try {
        const r = await fetch(api.queryDetail, {
            method: 'POST',
            headers: {'Content-Type': 'application/json;charset=UTF-8'},
            body: JSON.stringify({itemId, id: detailId}),
            credentials: 'include',
        });
        if (!r.ok) return {ok: false, errorType: 'detail_http_' + r.status};
        const j = await r.json();
        return {ok: true, detail: (((j || {}).data || {}).detail || {})};
    } catch(e) {
        return {ok: false, errorType: 'detail_fetch_error', errorMessage: e.message || String(e)};
    }
};
"""


def _normalize(text: str) -> str:
    return " ".join(str(text).split())


def _extract_methodology(detail: dict[str, str]) -> dict[str, Any]:
    import re

    search_fields = [
        ("product_name", detail.get("f4", "")),
        ("model_spec", detail.get("f6", "")),
        ("composition", detail.get("f7", "")),
        ("intended_use", detail.get("f8", "")),
        ("remark", detail.get("f12", "")),
    ]
    candidates: list[dict[str, str]] = []
    for field_name, value in search_fields:
        text = _normalize(value)
        if not text:
            continue
        for method, pattern in METHOD_PATTERNS:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                candidates.append({
                    "methodology": method,
                    "source_field": field_name,
                    "match_text": m.group(0),
                })
    if not candidates:
        return {"methodology": None, "confidence": "none", "candidates": []}
    first = candidates[0]
    return {
        "methodology": first["methodology"],
        "source_field": first["source_field"],
        "match_text": first["match_text"],
        "confidence": "high" if first["source_field"] == "product_name" else "medium",
        "candidates": candidates,
    }


def collect_nmpa_headless(
    *,
    task_dir: Path,
    task_id: str,
    query: str,
    material_id_prefix: str,
    methodology: str = "",
    page_limit: int = 0,
) -> ScenarioResult:
    """Two-phase NMPA collection via Edge CDP."""
    try:
        from ivd_research.browser_collect import launch_edge_cdp_context, find_edge_executable
        _ = find_edge_executable()
    except Exception:
        return ScenarioResult(
            status=FailureType.NEEDS_MANUAL_REVIEW.value,
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh="NMPA 采集需要 Microsoft Edge。未找到 Edge。",
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ScenarioResult(
            status=FailureType.NEEDS_MANUAL_REVIEW.value,
            failure_type=FailureType.NEEDS_MANUAL_REVIEW,
            message_zh="请安装 Playwright：pip install playwright && playwright install chromium",
        )

    import hashlib
    from ivd_research.browser_session import _terminate_background_session

    digest = hashlib.sha1(str(Path(task_dir).resolve()).encode()).hexdigest()[:12]
    profile_dir = Path.home() / ".ivd_research_edge_profiles" / f"nmpa_{digest}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    _terminate_background_session(profile_dir)

    raw_dir = task_dir / "downloads" / "nmpa_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    text_dir = task_dir / "extracted_text" / "competitors"
    text_dir.mkdir(parents=True, exist_ok=True)

    attempt_log: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []  # {category_key, row, detail}
    materials: list[Material] = []
    import subprocess

    edge_proc: subprocess.Popen | None = None
    try:
        with sync_playwright() as pw:
            browser, context, page, edge_proc, _, _ = launch_edge_cdp_context(
                pw, profile_dir=profile_dir, headless=False, allow_headed_fallback=False,
            )
            try:
                page.goto(
                    "https://www.nmpa.gov.cn/datasearch/home-index.html#category=ylqx",
                    wait_until="domcontentloaded", timeout=30000,
                )
                page.wait_for_timeout(3000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(5000)

                # Wait for pajax / api objects to be ready
                for _ in range(20):
                    ready = page.evaluate(
                        "() => !!(typeof pajax !== 'undefined' && pajax.hasTokenGet"
                        " && typeof api !== 'undefined' && api.queryList && api.queryDetail)"
                    )
                    if ready:
                        break
                    page.wait_for_timeout(1000)

                # ---- PHASE A: collect all list pages for each category ----
                for cat in CATEGORIES:
                    cat_log = {
                        "key": cat["key"], "label": cat["label"],
                        "itemId": cat["itemId"], "attempted": True,
                        "pages_fetched": 0, "total": 0, "rows_collected": 0,
                        "errors": [],
                    }

                    # Fetch first page
                    page_result = page.evaluate(FETCH_ONE_PAGE_JS, {
                        "itemId": cat["itemId"], "query": query,
                        "pageNum": 1, "pageSize": 10,
                    })
                    # Save raw diagnostic
                    (raw_dir / f"{cat['key']}_page_1.json").write_text(
                        json.dumps(page_result, ensure_ascii=False, indent=2), encoding="utf-8")

                    if not page_result.get("ok"):
                        cat_log["errors"].append({"page": 1, "error": page_result})
                        attempt_log.append(cat_log)
                        continue

                    total = page_result.get("total", 0)
                    rows = page_result.get("rows", [])
                    cat_log["total"] = total
                    cat_log["rows_collected"] = len(rows)
                    cat_log["pages_fetched"] = 1

                    for row in rows:
                        if row.get("f3"):
                            all_rows.append({"category_key": cat["key"], "row": row})

                    # Fetch remaining pages
                    per_page = len(rows) or 10
                    total_pages = -(-total // per_page)  # ceil division
                    max_pages = total_pages if page_limit <= 0 else min(total_pages, -(-page_limit // per_page))

                    for p in range(2, max_pages + 1):
                        time.sleep(0.5)
                        page_result = page.evaluate(FETCH_ONE_PAGE_JS, {
                            "itemId": cat["itemId"], "query": query,
                            "pageNum": p, "pageSize": per_page,
                        })
                        (raw_dir / f"{cat['key']}_page_{p}.json").write_text(
                            json.dumps(page_result, ensure_ascii=False, indent=2), encoding="utf-8")

                        if not page_result.get("ok"):
                            cat_log["errors"].append({"page": p, "error": page_result})
                            continue

                        p_rows = page_result.get("rows", [])
                        cat_log["rows_collected"] += len(p_rows)
                        cat_log["pages_fetched"] += 1
                        for row in p_rows:
                            if row.get("f3"):
                                all_rows.append({"category_key": cat["key"], "row": row})

                    attempt_log.append(cat_log)

                # ---- PHASE B: fetch details (sequential, one retry, then list-only fallback) ----
                #
                # DESIGN NOTE — NMPA detail API rate limiting
                # ==============================================
                # The `pajax.hasTokenGet(api.queryDetail, ...)` call is designed for
                # human users clicking one detail button at a time.  When we call it
                # programmatically for 192 rows, the NMPA server starts rejecting
                # requests after ~40–70 successful calls (returns empty or errors).
                #
                # Current strategy (3 tiers):
                #   1. Sequential pass      → typically ~40 materials with full f0-f18
                #   2. One retry pass       → typically recovers ~30 more (~20% hit rate)
                #   3. List-only fallback   → remaining rows saved with f0/f1/f2
                #                              (registration №, registrant, product name)
                #
                # Total: ~70 full-detail + ~122 list-only = 192 materials.
                # Runtime: ~200 seconds for 肺炎支原体 (184 domestic + 8 import).
                #
                # --- IF FULL DETAIL COLLECTION IS REQUIRED IN THE FUTURE ---
                #
                # Add multiple retry rounds WITH page refresh between rounds:
                #
                #   for round in range(max_rounds):
                #       page.goto(NMPA_HOME, ...)        # refresh → new pajax token
                #       wait_for_pajax(page)
                #       for entry in still_failed:
                #           result = page.evaluate(FETCH_ONE_DETAIL_JS, ...)
                #           if result.ok: recover
                #       if recovery_rate < 5%: break     # diminishing returns
                #
                # Estimated: 8–10 rounds, 600–800 seconds to get all 192 full details.
                # Each round's recovery rate decreases (30 → 20 → 15 → 10 → ...).
                #
                # The per-round page.goto() must use the same hash-route URL
                # (home-index.html#category=ylqx), then wait for pajax re-init.
                # Do NOT call page.goto() between individual detail requests —
                # that was tested and made collection worse (pajax context loss).
                # ================================================================
                detail_index = 0
                failed_details: list[dict[str, Any]] = []

                for entry in all_rows:
                    row = entry["row"]
                    detail_id = row.get("f3", "")
                    if not detail_id:
                        continue

                    cat = next((c for c in CATEGORIES if c["key"] == entry["category_key"]), CATEGORIES[0])
                    detail_result = page.evaluate(FETCH_ONE_DETAIL_JS, {
                        "itemId": cat["itemId"], "detailId": detail_id,
                    })
                    time.sleep(0.15)

                    if not detail_result.get("ok"):
                        failed_details.append(entry)
                        continue

                    detail = detail_result.get("detail", {})
                    if not detail:
                        failed_details.append(entry)
                        continue

                    # Apply methodology filter
                    product_name = detail.get("f4", "") or row.get("f2", "")
                    meth = _extract_methodology(detail)
                    if methodology and methodology not in product_name:
                        continue

                    detail_index += 1
                    material_id = (
                        material_id_prefix
                        if detail_index == 1
                        else f"{material_id_prefix}-{detail_index:03d}"
                    )

                    full_text = "；".join(
                        f"{k}: {_normalize(detail.get(k, ''))}"
                        for k in sorted(detail.keys()) if detail.get(k)
                    )
                    tp = text_dir / f"{material_id}_nmpa.txt"
                    tp.write_text(full_text, encoding="utf-8", errors="ignore")

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
                                "category": cat["label"],
                                "collected_via": "nmpa_two_phase",
                            },
                            collection_time=now_iso(),
                            adapter_id="nmpa_two_phase",
                            adapter_version="5.0.0",
                            raw_fields={
                                "registration_certificate_number": detail.get("f0", ""),
                                "registrant": detail.get("f1", ""),
                                "product_name": product_name,
                                "methodology": meth.get("methodology"),
                                "methodology_source": meth.get("source_field"),
                                "methodology_confidence": meth.get("confidence"),
                                "scope": detail.get("f8", ""),
                                "approval_date": detail.get("f14", ""),
                                "full_visible_text": full_text,
                                "category": cat["label"],
                            },
                            download_status="not_applicable",
                            extracted_text_status="completed",
                            extracted_text_path=str(tp.relative_to(task_dir)),
                            content_snapshot_path=str(tp.relative_to(task_dir)),
                        )
                    )

                # ---- Retry failed details (one pass, longer delay) ----
                if failed_details:
                    time.sleep(3.0)
                    retry_ok = 0
                    for entry in failed_details:
                        row = entry["row"]
                        detail_id = row.get("f3", "")
                        if not detail_id:
                            continue
                        cat = next(
                            (c for c in CATEGORIES if c["key"] == entry["category_key"]),
                            CATEGORIES[0],
                        )
                        detail_result = page.evaluate(FETCH_ONE_DETAIL_JS, {
                            "itemId": cat["itemId"], "detailId": detail_id,
                        })
                        time.sleep(0.1)
                        if not detail_result.get("ok"):
                            continue
                        detail = detail_result.get("detail", {})
                        if not detail:
                            continue
                        retry_ok += 1
                        entry["_retried_ok"] = True
                        product_name = detail.get("f4", "") or row.get("f2", "")
                        meth = _extract_methodology(detail)
                        if methodology and methodology not in product_name:
                            continue
                        detail_index += 1
                        material_id = (
                            material_id_prefix
                            if detail_index == 1
                            else f"{material_id_prefix}-{detail_index:03d}"
                        )
                        full_text = "；".join(
                            f"{k}: {_normalize(detail.get(k, ''))}"
                            for k in sorted(detail.keys()) if detail.get(k)
                        )
                        tp = text_dir / f"{material_id}_nmpa.txt"
                        tp.write_text(full_text, encoding="utf-8", errors="ignore")
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
                                    "category": cat["label"],
                                    "collected_via": "nmpa_retry",
                                },
                                collection_time=now_iso(),
                                adapter_id="nmpa_two_phase",
                                adapter_version="5.0.0",
                                raw_fields={
                                    "registration_certificate_number": detail.get("f0", ""),
                                    "registrant": detail.get("f1", ""),
                                    "product_name": product_name,
                                    "methodology": meth.get("methodology"),
                                    "methodology_source": meth.get("source_field"),
                                    "methodology_confidence": meth.get("confidence"),
                                    "scope": detail.get("f8", ""),
                                    "approval_date": detail.get("f14", ""),
                                    "full_visible_text": full_text,
                                    "category": cat["label"],
                                },
                                download_status="not_applicable",
                                extracted_text_status="completed",
                                extracted_text_path=str(tp.relative_to(task_dir)),
                                content_snapshot_path=str(tp.relative_to(task_dir)),
                            )
                        )
                    attempt_log.append({
                        "stage": "detail_retry",
                        "failed_before": len(failed_details),
                        "recovered": retry_ok,
                        "still_failed": len(failed_details) - retry_ok,
                    })

                    # ---- Create list-only materials for remaining failed items ----
                    # These use list-page fields (f0/f1/f2) without full detail,
                    # still valuable for competitor landscape analysis.
                    list_only = 0
                    for entry in failed_details:
                        # Skip items already recovered in retry
                        if entry.get("_retried_ok"):
                            continue
                        row = entry["row"]
                        product_name = row.get("f2", "")
                        if not product_name:
                            continue
                        if methodology and methodology not in product_name:
                            continue
                        detail_index += 1
                        material_id = (
                            material_id_prefix
                            if detail_index == 1
                            else f"{material_id_prefix}-{detail_index:03d}"
                        )
                        cat = next(
                            (c for c in CATEGORIES if c["key"] == entry["category_key"]),
                            CATEGORIES[0],
                        )
                        brief = "；".join(
                            f"{label}: {row.get(k,'')}"
                            for k, label in [
                                ("f0", "注册证编号"),
                                ("f1", "注册人"),
                                ("f2", "产品名称"),
                            ]
                            if row.get(k)
                        )
                        tp = text_dir / f"{material_id}_nmpa_list.txt"
                        tp.write_text(brief, encoding="utf-8", errors="ignore")
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
                                    "category": cat["label"],
                                    "collected_via": "nmpa_list_only",
                                },
                                collection_time=now_iso(),
                                adapter_id="nmpa_two_phase",
                                adapter_version="5.0.0",
                                raw_fields={
                                    "registration_certificate_number": row.get("f0", ""),
                                    "registrant": row.get("f1", ""),
                                    "product_name": product_name,
                                    "methodology": _extract_methodology(
                                        {"f4": product_name}
                                    ).get("methodology"),
                                    "methodology_confidence": "list_only",
                                    "list_only": True,
                                    "category": cat["label"],
                                    "full_visible_text": brief,
                                },
                                download_status="not_applicable",
                                extracted_text_status="completed",
                                extracted_text_path=str(tp.relative_to(task_dir)),
                                content_snapshot_path=str(tp.relative_to(task_dir)),
                            )
                        )
                        list_only += 1
                    attempt_log.append({
                        "stage": "list_only_fallback",
                        "list_only_created": list_only,
                    })

            finally:
                context.close()
                if browser is not None:
                    browser.close()
    finally:
        if edge_proc is not None and edge_proc.poll() is None:
            try:
                edge_proc.terminate()
            except Exception:
                pass

    # Save attempt log
    (raw_dir / "_attempt_log.json").write_text(
        json.dumps(attempt_log, ensure_ascii=False, indent=2), encoding="utf-8")

    if not materials:
        return ScenarioResult(
            status=FailureType.NO_RESULTS.value,
            failure_type=FailureType.NO_RESULTS,
            message_zh=(
                "NMPA 采集完成（" + "；".join(a["label"] + ": " + str(a["rows_collected"]) + "条" for a in attempt_log) + "）"
                f"但未采集到符合条件的新材料。"
                f"（搜索词：{query}，方法学：{methodology or '未指定'}）"
            ),
        )

    by_cat = {}
    for m in materials:
        cat_label = (m.collection_path or {}).get("category", "unknown")
        by_cat[cat_label] = by_cat.get(cat_label, 0) + 1
    cat_summary = "、".join(f"{k}: {v}条" for k, v in by_cat.items())
    return ScenarioResult(
        status="completed",
        materials=materials,
        message_zh=f"NMPA 已采集 {cat_summary}（共 {len(materials)} 条）。",
    )
