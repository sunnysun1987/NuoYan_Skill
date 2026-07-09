import json
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from .browser_session import browser_state_dir, _terminate_background_session
from .browser_workflows import (
    browser_workflow,
    page_probe_result,
    search_url_for_workflow,
)
from .jsonl import append_jsonl, read_jsonl
from .models import FailureType
from .scenarios.cmde_regulatory import (
    _build_material as build_cmde_material,
    _download_attachment as download_cmde_attachment,
    _readable_detail_html as readable_cmde_detail_html,
    cmde_next_search_page_url,
    parse_cmde_detail_html,
    parse_cmde_search_html,
)
from .scenarios.nmpa_competitor import (
    build_nmpa_api_material,
    build_nmpa_material,
    methodology_matches,
    parse_nmpa_detail,
    parse_nmpa_result_list,
)
from .scenarios.patenthub_patents import (
    build_patenthub_material,
    parse_patenthub_detail,
    parse_patenthub_result_list,
)
from .status import now_iso

try:
    from playwright.sync_api import sync_playwright
except Exception as exc:  # pragma: no cover - depends on optional browser extra.
    sync_playwright = None
    PLAYWRIGHT_IMPORT_ERROR = exc
else:  # pragma: no cover - import availability is environment-specific.
    PLAYWRIGHT_IMPORT_ERROR = None


SUCCESS_STATUSES = {"completed", "search_results"}

POPUP_DISMISS_CONFIG: dict[str, dict[str, Any]] = {
    "patenthub_patents": {
        "description_zh": "关注微信公众号弹窗，只允许点击普通关闭或稍后关注控件。",
        "selectors": [
            "button:has-text('稍后关注')",
            "button:has-text('稍后再说')",
            "[aria-label='Close']",
            ".el-dialog__headerbtn",
            ".ant-modal-close",
        ],
    }
}


def browser_workflow_paths(task_dir: Path, scenario_id: str) -> dict[str, Path]:
    base_dir = task_dir / "downloads" / "browser_workflow" / scenario_id
    paths = {
        "base_dir": base_dir,
        "snapshot_dir": base_dir / "snapshots",
        "detail_snapshot_dir": base_dir / "detail_snapshots",
        "download_dir": base_dir / "downloads",
        "scout_dir": base_dir / "scout",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def edge_cdp_profile_dir(task_dir: Path, scenario_id: str, profile_scope: str = "task") -> Path:
    if profile_scope == "user":
        return Path.home() / ".ivd_research_edge_profiles" / scenario_id
    if profile_scope != "task":
        raise ValueError(f"Unsupported browser profile scope: {profile_scope}")
    return task_dir / "browser_state" / "edge_profiles" / scenario_id


def relative_to_task(task_dir: Path, path: Path) -> str:
    task_root = task_dir.resolve()
    target = path.resolve(strict=False)
    if not target.is_relative_to(task_root):
        raise ValueError(f"Browser workflow path must stay inside task directory: {path}")
    return target.relative_to(task_root).as_posix()


def next_material_index(task_dir: Path) -> int:
    highest = 0
    for row in read_jsonl(task_dir / "data" / "materials.jsonl"):
        material_id = str(row.get("material_id", ""))
        if not material_id.startswith("MAT-"):
            continue
        try:
            highest = max(highest, int(material_id[4:10]))
        except ValueError:
            continue
    return highest + 1


def popup_dismiss_config(scenario_id: str) -> dict[str, Any]:
    return POPUP_DISMISS_CONFIG.get(
        scenario_id,
        {"description_zh": "该场景未配置可安全自动关闭的弹窗。", "selectors": []},
    )


def close_blocking_popups(page: Any, scenario_id: str) -> list[str]:
    dismissed: list[str] = []
    for selector in popup_dismiss_config(scenario_id)["selectors"]:
        try:
            locator = page.locator(selector)
            if locator.count():
                locator.first.click(timeout=1000)
                dismissed.append(selector)
        except Exception:
            continue
    return dismissed


def normalize_browser_collection_status(status: str) -> str:
    if status in {
        FailureType.NEEDS_LOGIN.value,
        FailureType.PERMISSION_REQUIRED.value,
        FailureType.COLLECTION_FAILED.value,
        "search_results",
        "completed",
    }:
        return status
    if status == "page_ready":
        return FailureType.NEEDS_MANUAL_REVIEW.value
    return FailureType.COLLECTION_FAILED.value


def blocked_reason_for(status: str, reason_zh: str) -> str:
    if status in {
        FailureType.NEEDS_LOGIN.value,
        FailureType.PERMISSION_REQUIRED.value,
        FailureType.COLLECTION_FAILED.value,
    }:
        return reason_zh
    return ""


def safe_page_snapshot(page: Any) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            title = page.title()
            body = page.locator("body")
            text = body.inner_text(timeout=5000) if body.count() else ""
            html = page.content()
            final_url = page.url
            return {
                "title": title,
                "text": text,
                "html": html,
                "final_url": final_url,
            }
        except Exception as exc:
            last_error = exc
            try:
                page.wait_for_load_state("domcontentloaded", timeout=2000)
            except Exception:
                pass
    raise last_error or RuntimeError("Unable to capture browser page snapshot")


def find_edge_executable() -> str:
    edge = shutil.which("msedge") or shutil.which("msedge.exe")
    if edge:
        return edge
    for candidate in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if Path(candidate).exists():
            return candidate
    raise RuntimeError("Microsoft Edge executable was not found")


def edge_cdp_launch_args(
    port: int,
    profile_dir: Path,
    headless: bool = True,
    minimized: bool = False,
) -> list[str]:
    args = [
        find_edge_executable(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeFirstRunExperience,msEdgeShoppingAssistant,msHubApps,EdgeSigninInterceptionEnabled,msImplicitSignin,msSync",
        "--disable-sync",
        "--disable-default-apps",
        "--window-size=1280,900",
        "about:blank",
    ]
    if headless:
        args.insert(-1, "--headless=new")
        args.insert(-1, "--disable-gpu")
    elif minimized:
        args.insert(-1, "--start-minimized")
        args.insert(-1, "--window-position=-32000,-32000")
    return args


def launch_edge_cdp_context(
    playwright: Any,
    profile_dir: Path,
    *,
    headless: bool,
    allow_headed_fallback: bool = True,
) -> tuple[Any, Any, Any, subprocess.Popen, bool, str]:
    attempts = [headless]
    if headless and allow_headed_fallback:
        attempts.append(False)
    last_error = ""
    profile_dir.mkdir(parents=True, exist_ok=True)
    for attempt_headless in attempts:
        port = free_local_port()
        edge_process = subprocess.Popen(
            edge_cdp_launch_args(
                port,
                profile_dir,
                headless=attempt_headless,
                minimized=not attempt_headless,
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version",
                    timeout=1,
                ).read()
                browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                page = context.pages[0] if context.pages else context.new_page()
                fallback_reason = (
                    ""
                    if attempt_headless == headless
                    else "Edge headless CDP failed to stay alive; fell back to minimized headed Edge."
                )
                return browser, context, page, edge_process, attempt_headless, fallback_reason
            except Exception as exc:
                last_error = str(exc)
                if edge_process.poll() is not None:
                    break
                time.sleep(0.25)
        if edge_process.poll() is None:
            edge_process.terminate()
    raise RuntimeError(last_error or "Unable to start Microsoft Edge CDP session")


def scout_dom_candidates(page: Any) -> dict[str, list[dict[str, Any]]]:
    return page.evaluate(
        """
        () => {
          const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
          const attrs = (el) => ({
            tag: el.tagName.toLowerCase(),
            type: el.getAttribute('type') || '',
            id: el.id || '',
            name: el.getAttribute('name') || '',
            class: el.getAttribute('class') || '',
            placeholder: el.getAttribute('placeholder') || '',
            aria_label: el.getAttribute('aria-label') || '',
            title: el.getAttribute('title') || '',
            text: clean(el.innerText || el.textContent || '').slice(0, 160),
          });
          const css = (el) => {
            if (el.id) return `#${CSS.escape(el.id)}`;
            const name = el.getAttribute('name');
            if (name) return `${el.tagName.toLowerCase()}[name="${name.replace(/"/g, '\\\\"')}"]`;
            const cls = (el.getAttribute('class') || '').trim().split(/\\s+/).filter(Boolean).slice(0, 2);
            return cls.length ? `${el.tagName.toLowerCase()}.${cls.map(CSS.escape).join('.')}` : el.tagName.toLowerCase();
          };
          const take = (selector, limit) => Array.from(document.querySelectorAll(selector)).slice(0, limit)
            .map((el) => ({ selector: css(el), ...attrs(el) }));
          const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 80)
            .map((el) => ({ selector: css(el), href: el.href, ...attrs(el) }));
          return {
            inputs: take('input, textarea, [contenteditable="true"]', 40),
            buttons: take('button, input[type="button"], input[type="submit"], [role="button"]', 60),
            selects: take('select', 30),
            links,
            tables: take('table', 20),
          };
        }
        """
    )


def scout_browser_workflow(
    task_dir: Path,
    scenario_id: str,
    query: str,
    headless: bool = True,
    page_limit: int = 1,
    launch_mode: str = "playwright",
    profile_scope: str = "task",
) -> dict[str, Any]:
    workflow = browser_workflow(scenario_id)
    target_url = search_url_for_workflow(workflow, query)
    paths = browser_workflow_paths(task_dir, scenario_id)
    state_dir = browser_state_dir(task_dir, scenario_id, profile_scope)
    state_dir.mkdir(parents=True, exist_ok=True)

    if sync_playwright is None:
        return dependency_missing_result(
            task_dir,
            scenario_id,
            query,
            target_url,
            PLAYWRIGHT_IMPORT_ERROR or RuntimeError("Playwright is unavailable"),
        )

    network_candidates: list[dict[str, Any]] = []
    edge_process: subprocess.Popen | None = None
    actual_headless = headless
    fallback_reason = ""
    try:
        with sync_playwright() as p:
            if launch_mode == "edge-cdp":
                (
                    browser,
                    context,
                    page,
                    edge_process,
                    actual_headless,
                    fallback_reason,
                ) = launch_edge_cdp_context(
                    p,
                    edge_cdp_profile_dir(task_dir, scenario_id, profile_scope),
                    headless=headless,
                )
            elif launch_mode == "playwright":
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(state_dir),
                    headless=headless,
                    accept_downloads=True,
                    downloads_path=str(paths["download_dir"]),
                )
                page = context.pages[0] if context.pages else context.new_page()
                browser = None
            else:
                raise ValueError(f"Unsupported browser launch mode: {launch_mode}")

            def record_response(response: Any) -> None:
                if len(network_candidates) >= 80:
                    return
                try:
                    request = response.request
                    content_type = response.headers.get("content-type", "")
                    if request.resource_type in {"xhr", "fetch", "document"} or "json" in content_type:
                        network_candidates.append(
                            {
                                "url": response.url,
                                "status": response.status,
                                "resource_type": request.resource_type,
                                "method": request.method,
                                "content_type": content_type,
                            }
                        )
                except Exception:
                    return

            page.on("response", record_response)
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            if launch_mode == "edge-cdp":
                page.wait_for_timeout(8000)
            closed_popups = close_blocking_popups(page, scenario_id)
            snapshot = safe_page_snapshot(page)
            dom_candidates = scout_dom_candidates(page)
            if browser is not None:
                browser.close()
            else:
                context.close()
    except Exception as exc:
        return collection_failed_result(
            task_dir,
            scenario_id,
            query,
            target_url,
            state_dir,
            exc,
        )
    finally:
        if edge_process is not None and edge_process.poll() is None:
            edge_process.terminate()

    html_path = paths["scout_dir"] / "scout.html"
    json_path = paths["scout_dir"] / "scout.json"
    html_path.write_text(snapshot["html"], encoding="utf-8", errors="ignore")
    candidate_counts = {key: len(value) for key, value in dom_candidates.items()}
    empty_dynamic_page = not snapshot["text"].strip() and not any(candidate_counts.values())
    status = FailureType.COLLECTION_FAILED.value if empty_dynamic_page else "completed"
    message_zh = (
        "页面为空白或未暴露 DOM 候选，可能被安全脚本、动态入口参数或站点防护阻塞；"
        "已保存 HTML 和 network response 供开发者排查。"
        if empty_dynamic_page
        else "已完成页面侦察，保存了 DOM 候选元素和 network response 候选。"
    )
    payload = {
        "status": status,
        "scenario_id": scenario_id,
        "query": query,
        "target_url": target_url,
        "final_url": snapshot["final_url"],
        "title": snapshot["title"],
        "text_length": len(snapshot["text"]),
        "text_preview": snapshot["text"][:1000],
        "closed_popups": closed_popups,
        "headless": headless,
        "actual_headless": actual_headless,
        "launch_mode": launch_mode,
        "profile_scope": profile_scope,
        "fallback_reason": fallback_reason,
        "dom_candidates": dom_candidates,
        "candidate_counts": candidate_counts,
        "network_candidates": network_candidates,
        "snapshot_paths": [
            relative_to_task(task_dir, html_path),
            relative_to_task(task_dir, json_path),
        ],
        "message_zh": message_zh,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    append_jsonl(
        task_dir / "logs" / "debug.jsonl",
        {
            "time": now_iso(),
            "event": "browser_workflow_scouted",
            "scenario_id": scenario_id,
            "target_url": target_url,
            "final_url": snapshot["final_url"],
            "candidate_counts": payload["candidate_counts"],
            "network_candidate_count": len(network_candidates),
        },
    )
    return payload


def collect_patenthub_visible_results(
    *,
    task_dir: Path,
    task_id: str,
    context: Any,
    search_html: str,
    search_url: str,
    query: str,
    search_snapshot: str,
    page_limit: int,
    start_index: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    paths = browser_workflow_paths(task_dir, "patenthub_patents")
    entries = parse_patenthub_result_list(search_html, search_url)[:page_limit]
    materials: list[dict[str, Any]] = []
    detail_snapshots: list[str] = []
    for index, entry in enumerate(entries, start=start_index):
        material_id = f"MAT-{index:06d}"
        page = context.new_page()
        try:
            page.goto(entry["detail_url"], wait_until="domcontentloaded", timeout=30000)
            detail_html = page.content()
            detail_snapshot_path = paths["detail_snapshot_dir"] / f"{material_id}.html"
            detail_snapshot_path.write_text(detail_html, encoding="utf-8", errors="ignore")
            detail_snapshot = relative_to_task(task_dir, detail_snapshot_path)
            detail_snapshots.append(detail_snapshot)
            detail = parse_patenthub_detail(detail_html, entry["detail_url"])
            text_path = paths["base_dir"] / "extracted_text" / f"{material_id}.txt"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            fallback_text = ""
            try:
                body = page.locator("body")
                fallback_text = body.inner_text(timeout=5000) if body.count() else ""
            except Exception:
                fallback_text = ""
            text_path.write_text(
                detail.get("extracted_text") or fallback_text,
                encoding="utf-8",
                errors="ignore",
            )
            material = build_patenthub_material(
                task_id=task_id,
                material_id=material_id,
                query=query,
                search_url=search_url,
                search_snapshot=search_snapshot,
                detail_snapshot=detail_snapshot,
                entry=entry,
                detail=detail,
                extracted_text_path=relative_to_task(task_dir, text_path),
            )
            materials.append(material.model_dump(mode="json"))
        finally:
            try:
                page.close()
            except Exception:
                pass
    return materials, detail_snapshots


def collect_nmpa_visible_results(
    *,
    task_dir: Path,
    task_id: str,
    context: Any,
    search_html: str,
    search_url: str,
    query: str,
    search_snapshot: str,
    page_limit: int,
    start_index: int,
    methodology: str = "",
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    paths = browser_workflow_paths(task_dir, "nmpa_competitor")
    entries = parse_nmpa_result_list(search_html, search_url)[:page_limit]
    materials: list[dict[str, Any]] = []
    detail_snapshots: list[str] = []
    collection_errors: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=start_index):
        if not entry.get("detail_url"):
            continue
        material_id = f"MAT-{index:06d}"
        page = context.new_page()
        page.goto(entry["detail_url"], wait_until="domcontentloaded", timeout=30000)
        detail_html = page.content()
        detail_snapshot_path = paths["detail_snapshot_dir"] / f"{material_id}.html"
        detail_snapshot_path.write_text(detail_html, encoding="utf-8", errors="ignore")
        detail_snapshot = relative_to_task(task_dir, detail_snapshot_path)
        detail_snapshots.append(detail_snapshot)
        detail = parse_nmpa_detail(detail_html, entry["detail_url"])
        if not methodology_matches(detail, methodology):
            collection_errors.append(
                {
                    "detail_url": entry["detail_url"],
                    "status": "filtered_by_methodology",
                    "reason": f"methodology_not_matched:{methodology}",
                    "product_name": detail.get("product_name") or entry.get("product_name", ""),
                    "detected_methodology": detail.get("methodology", ""),
                }
            )
            continue
        material = build_nmpa_material(
            task_id=task_id,
            material_id=material_id,
            query=query,
            search_url=search_url,
            search_snapshot=search_snapshot,
            detail_snapshot=detail_snapshot,
            entry=entry,
            detail=detail,
        )
        materials.append(material.model_dump(mode="json"))
    return materials, detail_snapshots, collection_errors


def free_local_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def collect_nmpa_api_results(
    *,
    task_dir: Path,
    task_id: str,
    page: Any,
    query: str,
    search_url: str,
    search_snapshot: str,
    page_limit: int,
    start_index: int,
    methodology: str = "",
    registration_types: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], dict[str, Any]]:
    paths = browser_workflow_paths(task_dir, "nmpa_competitor")
    raw_dir = paths["base_dir"] / "api_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    wanted_registration_types = registration_types or [
        "境内医疗器械（注册）",
        "进口医疗器械（注册）",
    ]
    config_groups: list[dict[str, Any]] = []
    config_error = ""
    try:
        request = urllib.request.Request(
            "https://www.nmpa.gov.cn/datasearch/config/NMPA_DATA.json",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            config_payload = json.loads(response.read().decode("utf-8"))
            config_groups = (
                config_payload.get("data", [])
                if isinstance(config_payload, dict)
                else config_payload
            )
    except Exception as exc:
        config_error = str(exc)
        config_groups = []
    # Use native browser fetch() instead of pajax to avoid dependency on
    # the SPA's JavaScript globals (window.pajax / window.api may not be
    # loaded in headless or slow-connection scenarios).
    # The browser context already holds WAF-cleared cookies, so fetch()
    # can call the NMPA backend API directly.
    api_payload = page.evaluate(
        """
        async ({ query, pageLimit, registrationTypes, configGroups, configError }) => {
          const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
          const NMPA_DATA_URL = 'https://www.nmpa.gov.cn/datasearch/config/NMPA_DATA.json';
          const SEARCH_URL = 'https://www.nmpa.gov.cn/datasearch/data/nmpadata/search';
          const DETAIL_URL = 'https://www.nmpa.gov.cn/datasearch/data/nmpadata/queryDetail';
          // Prefer pajax.hasTokenGet when available (includes CSRF token).
          // Fall back to native fetch() for headless/slow-page scenarios.
          const apiPost = async (url, body) => {
            if (typeof pajax !== 'undefined' && pajax.hasTokenGet) {
              return pajax.hasTokenGet(url, body);
            }
            const response = await fetch(url, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json;charset=UTF-8' },
              body: JSON.stringify(body),
              credentials: 'include',
            });
            if (!response.ok) {
              return { code: response.status, data: null, message: 'HTTP ' + response.status };
            }
            return response.json();
          };
          // Wait for pajax to be ready (headed mode loads the full SPA).
          for (let attempt = 0; attempt < 20; attempt++) {
            if (typeof pajax !== 'undefined' && pajax.hasTokenGet) break;
            await sleep(1000);
          }
          let groups = configGroups || [];
          for (let attempt = 0; attempt < 8; attempt += 1) {
            if (groups.length) break;
            try {
              const configResponse = await fetch(NMPA_DATA_URL, { cache: 'no-store', credentials: 'include' });
              const configJson = await configResponse.json();
              groups = configJson.data || [];
            } catch(e) {}
            if (groups.length) break;
            await sleep(1500);
          }
          const medicalDevices = groups.find((group) => group.paraCode === 'item_3')
            || groups.find((group) => (group.paraName || '').includes('医疗器械'));
          if (!medicalDevices) {
            return {
              status: 'collection_failed',
              message: '未找到医疗器械数据分类',
              groups: groups.map((group) => ({
                paraCode: group.paraCode || '',
                paraName: group.paraName || '',
                itemCount: (group.itemList || []).length,
              })),
              configError,
              results: []
            };
          }
          const selectedItems = (medicalDevices.itemList || []).filter((item) =>
            registrationTypes.includes(item.itemName)
          );
          const results = [];
          for (const item of selectedItems) {
            const firstPage = await apiPost(SEARCH_URL, {
              itemId: item.itemId,
              searchValue: query,
              pageNum: 1,
              pageSize: 200,
            });
            const firstBody = firstPage && firstPage.data;
            const firstData = (firstBody && firstBody.data) || firstBody || {};
            const total = firstData.total || 0;
            const allRows = [...(firstData.list || [])];
            // Fetch remaining pages. pageLimit=0 means unlimited.
            const actualPerPage = (firstData.list || []).length || 10;
            const totalPages = Math.ceil(total / actualPerPage);
            const maxPages = pageLimit > 0 ? Math.ceil(pageLimit / actualPerPage) : totalPages;
            const pagesToFetch = Math.min(totalPages, maxPages);
            for (let p = 2; p <= pagesToFetch; p++) {
              const pageResp = await apiPost(SEARCH_URL, {
                itemId: item.itemId,
                searchValue: query,
                pageNum: p,
                pageSize: actualPerPage,
              });
              const pageBody = pageResp && pageResp.data;
              const pageData = (pageBody && pageBody.data) || pageBody || {};
              allRows.push(...(pageData.list || []));
            }
            const rows = allRows.slice(0, pageLimit);
            // Fetch detail for each row
            const details = [];
            for (const row of rows) {
              if (!row.f3) continue;
              try {
                const detailResponse = await apiPost(DETAIL_URL, {
                  itemId: item.itemId,
                  id: row.f3,
                });
                const detailBody = detailResponse && detailResponse.data;
                const detailData = (detailBody && detailBody.data) || detailBody || {};
                details.push({
                  row,
                  response: detailData,
                  detail: detailData.detail || detailData,
                });
              } catch (error) {
                details.push({ row, error: String(error && (error.message || error)) });
              }
            }
            results.push({
              itemId: item.itemId,
              itemName: item.itemName,
              listResponse: firstData,
              details,
            });
          }
          return {
            status: selectedItems.length ? 'completed' : 'no_results',
            queryListUrl: SEARCH_URL,
            queryDetailUrl: DETAIL_URL,
            registrationTypes,
            results,
          };
        }
        """,
        {
            "query": query,
            "pageLimit": page_limit,
            "registrationTypes": wanted_registration_types,
            "configGroups": config_groups,
            "configError": config_error,
        },
    )
    api_payload_path = raw_dir / "nmpa_api_payload.json"
    api_payload_path.write_text(
        json.dumps(api_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    materials: list[dict[str, Any]] = []
    detail_snapshot_paths: list[str] = []
    collection_errors: list[dict[str, Any]] = []
    material_index = start_index
    for result in api_payload.get("results", []):
        list_path = raw_dir / f"{result.get('itemId', 'unknown')}_list.json"
        list_path.write_text(
            json.dumps(result.get("listResponse", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for detail_result in result.get("details", []):
            row = detail_result.get("row", {})
            detail = detail_result.get("detail", {})
            if not detail:
                collection_errors.append(
                    {
                        "status": "detail_collection_failed",
                        "registration_type": result.get("itemName", ""),
                        "row": row,
                        "reason": detail_result.get("error", "empty_detail"),
                    }
                )
                continue
            if not methodology_matches(
                {
                    "methodology": "",
                    "product_name": detail.get("f4", ""),
                    "title": detail.get("f4", ""),
                    "full_visible_text": " ".join(str(value or "") for value in detail.values()),
                },
                methodology,
            ):
                collection_errors.append(
                    {
                        "status": "filtered_by_methodology",
                        "registration_type": result.get("itemName", ""),
                        "product_name": row.get("f2") or detail.get("f4", ""),
                        "detected_methodology": "",
                        "reason": f"methodology_not_matched:{methodology}",
                    }
                )
                continue
            material_id = f"MAT-{material_index:06d}"
            detail_path = raw_dir / f"{material_id}_detail.json"
            detail_path.write_text(
                json.dumps(detail_result.get("response", {}), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            detail_snapshot = relative_to_task(task_dir, detail_path)
            detail_snapshot_paths.append(detail_snapshot)
            material = build_nmpa_api_material(
                task_id=task_id,
                material_id=material_id,
                query=query,
                search_url=search_url,
                search_snapshot=search_snapshot,
                detail_snapshot=detail_snapshot,
                registration_type=result.get("itemName", ""),
                item_id=result.get("itemId", ""),
                row=row,
                detail=detail,
            )
            materials.append(material.model_dump(mode="json"))
            material_index += 1
    return materials, detail_snapshot_paths, collection_errors, api_payload


def _cmde_object_data_url(html: str) -> str:
    """Extract the data URL from a CMDE <object type=text/html> embed tag."""
    import re
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for obj in soup.find_all("object"):
        if obj.get("type", "") == "text/html" and obj.get("data"):
            data_url = obj["data"].strip()
            if data_url and "hxsearchAction.do" in data_url:
                return data_url
    # Fallback: regex match in raw HTML for edge cases
    match = re.search(
        r'<object[^>]+type\s*=\s*"text/html"[^>]+data\s*=\s*"([^"]+)"',
        html,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def collect_cmde_browser_results(
    *,
    task_dir: Path,
    task_id: str,
    context: Any,
    page: Any,
    query: str,
    page_limit: int,
    start_index: int,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    paths = browser_workflow_paths(task_dir, "cmde_regulatory")
    matched: list[tuple[dict[str, str], str, str, str]] = []
    collection_errors: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for page_index in range(max(1, page_limit)):
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        list_html = page.content()
        # CMDE may embed search results in an <object data="..."> tag
        object_data_url = _cmde_object_data_url(list_html)
        if object_data_url:
            new_page = context.new_page()
            try:
                new_page.goto(object_data_url, wait_until="domcontentloaded", timeout=30000)
                try:
                    new_page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
                list_html = new_page.content()
            except Exception:
                pass
            finally:
                new_page.close()
        list_snapshot_path = paths["snapshot_dir"] / f"cmde_search_{page_index + 1}.html"
        list_snapshot_path.write_text(list_html, encoding="utf-8", errors="ignore")
        list_snapshot = relative_to_task(task_dir, list_snapshot_path)
        for entry in parse_cmde_search_html(list_html, page.url):
            detail_url = entry.get("detail_url", "")
            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)
            matched.append((entry, "cmde_search_result", page.url, list_snapshot))
        next_url = cmde_next_search_page_url(list_html, page.url)
        if not next_url:
            break
        page.goto(next_url, wait_until="domcontentloaded", timeout=30000)
    matched = matched[:page_limit]

    materials: list[dict[str, Any]] = []
    detail_snapshot_paths: list[str] = []
    for offset, (entry, strategy, list_url, list_snapshot) in enumerate(matched):
        material_id = f"MAT-{start_index + offset:06d}"
        detail_page = context.new_page()
        try:
            detail_page.goto(entry["detail_url"], wait_until="domcontentloaded", timeout=30000)
            try:
                detail_page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            detail_html = detail_page.content()
            detail = parse_cmde_detail_html(detail_html, detail_page.url)
            download_status, download_files, attachment_text = download_cmde_attachment(
                task_dir,
                material_id=material_id,
                attachment_url=detail.get("attachment_url", ""),
            )
            detail_snapshot_path = paths["detail_snapshot_dir"] / f"{material_id}.html"
            detail_snapshot_path.write_text(
                readable_cmde_detail_html(detail, attachment_text),
                encoding="utf-8",
                errors="ignore",
            )
            detail_snapshot = relative_to_task(task_dir, detail_snapshot_path)
            detail_snapshot_paths.append(detail_snapshot)
            text_path = paths["base_dir"] / "extracted_text" / f"{material_id}.txt"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(
                attachment_text or detail.get("visible_text", ""),
                encoding="utf-8",
                errors="ignore",
            )
            material = build_cmde_material(
                task_id=task_id,
                material_id=material_id,
                query=query,
                match_strategy=strategy,
                list_url=list_url,
                list_snapshot=list_snapshot,
                detail_url=detail_page.url,
                detail_snapshot=detail_snapshot,
                text_path=relative_to_task(task_dir, text_path),
                entry=entry,
                detail=detail,
                download_status=download_status,
                download_files=download_files,
            )
            materials.append(material.model_dump(mode="json"))
        except Exception as exc:
            collection_errors.append(
                {
                    "detail_url": entry.get("detail_url", ""),
                    "status": "collection_failed",
                    "reason": str(exc),
                }
            )
        finally:
            detail_page.close()
    return materials, detail_snapshot_paths, collection_errors


def dependency_missing_result(
    task_dir: Path,
    scenario_id: str,
    query: str,
    target_url: str,
    exc: Exception,
) -> dict[str, Any]:
    state_dir = browser_state_dir(task_dir, scenario_id)
    message_zh = f"缺少 Playwright，无法执行浏览器 workflow：{exc}"
    append_jsonl(
        task_dir / "logs" / "debug.jsonl",
        {
            "time": now_iso(),
            "event": "browser_workflow_dependency_missing",
            "scenario_id": scenario_id,
            "target_url": target_url,
            "error": str(exc),
        },
    )
    return {
        "status": FailureType.COLLECTION_FAILED.value,
        "scenario_id": scenario_id,
        "query": query,
        "target_url": target_url,
        "final_url": "",
        "title": "",
        "text_length": 0,
        "state_dir": str(state_dir),
        "state_dir_exists": state_dir.is_dir(),
        "snapshot_paths": [],
        "detail_snapshot_paths": [],
        "downloaded_files": [],
        "materials": [],
        "blocked_reason": message_zh,
        "pagination": {"page_limit": 0, "pages_visited": 0, "has_more": None},
        "closed_popups": [],
        "message_zh": message_zh,
    }


def collection_failed_result(
    task_dir: Path,
    scenario_id: str,
    query: str,
    target_url: str,
    state_dir: Path,
    exc: Exception,
) -> dict[str, Any]:
    message_zh = f"Playwright 浏览器 workflow 执行失败：{exc}"
    append_jsonl(
        task_dir / "logs" / "debug.jsonl",
        {
            "time": now_iso(),
            "event": "browser_workflow_failed",
            "scenario_id": scenario_id,
            "target_url": target_url,
            "error": str(exc),
        },
    )
    return {
        "status": FailureType.COLLECTION_FAILED.value,
        "scenario_id": scenario_id,
        "query": query,
        "target_url": target_url,
        "final_url": "",
        "title": "",
        "text_length": 0,
        "state_dir": str(state_dir),
        "state_dir_exists": state_dir.is_dir(),
        "snapshot_paths": [],
        "detail_snapshot_paths": [],
        "downloaded_files": [],
        "materials": [],
        "blocked_reason": message_zh,
        "pagination": {"page_limit": 0, "pages_visited": 0, "has_more": None},
        "closed_popups": [],
        "message_zh": message_zh,
    }


def run_browser_workflow(
    task_dir: Path,
    scenario_id: str,
    query: str,
    task_id: str = "",
    headless: bool = True,
    page_limit: int = 1,
    methodology: str = "",
    launch_mode: str = "playwright",
    profile_scope: str = "task",
) -> dict[str, Any]:
    workflow = browser_workflow(scenario_id)
    target_url = search_url_for_workflow(workflow, query)
    paths = browser_workflow_paths(task_dir, scenario_id)
    state_dir = browser_state_dir(task_dir, scenario_id, profile_scope)
    state_dir.mkdir(parents=True, exist_ok=True)

    # Release any background browser session holding a lock on this state_dir
    _terminate_background_session(state_dir)

    if sync_playwright is None:
        return dependency_missing_result(
            task_dir,
            scenario_id,
            query,
            target_url,
            PLAYWRIGHT_IMPORT_ERROR or RuntimeError("Playwright is unavailable"),
        )

    edge_process: subprocess.Popen | None = None
    api_payload: dict[str, Any] = {}
    used_nmpa_api = False
    used_cmde_browser = False
    actual_headless = headless
    fallback_reason = ""
    try:
        with sync_playwright() as p:
            if launch_mode == "edge-cdp":
                (
                    browser,
                    context,
                    page,
                    edge_process,
                    actual_headless,
                    fallback_reason,
                ) = launch_edge_cdp_context(
                    p,
                    edge_cdp_profile_dir(task_dir, scenario_id, profile_scope),
                    headless=headless,
                )
            elif launch_mode == "playwright":
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(state_dir),
                    headless=headless,
                    accept_downloads=True,
                    downloads_path=str(paths["download_dir"]),
                )
                page = context.pages[0] if context.pages else context.new_page()
                browser = None
            else:
                raise ValueError(f"Unsupported browser launch mode: {launch_mode}")

            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            if launch_mode == "edge-cdp":
                page.wait_for_timeout(8000)
            closed_popups = close_blocking_popups(page, scenario_id)
            snapshot = safe_page_snapshot(page)
            title = snapshot["title"]
            text = snapshot["text"]
            html = snapshot["html"]
            final_url = snapshot["final_url"]
            snapshot_path = paths["snapshot_dir"] / "search.html"
            snapshot_path.write_text(html, encoding="utf-8", errors="ignore")
            search_snapshot_relative = relative_to_task(task_dir, snapshot_path)
            materials: list[dict[str, Any]] = []
            detail_snapshot_paths: list[str] = []
            collection_errors: list[dict[str, Any]] = []
            material_start_index = next_material_index(task_dir)
            if scenario_id == "nmpa_competitor" and launch_mode == "edge-cdp":
                (
                    materials,
                    detail_snapshot_paths,
                    collection_errors,
                    api_payload,
                ) = collect_nmpa_api_results(
                    task_dir=task_dir,
                    task_id=task_id,
                    page=page,
                    query=query,
                    search_url=final_url,
                    search_snapshot=search_snapshot_relative,
                    page_limit=page_limit,
                    start_index=material_start_index,
                    methodology=methodology,
                )
                used_nmpa_api = True
            if scenario_id == "cmde_regulatory":
                (
                    materials,
                    detail_snapshot_paths,
                    collection_errors,
                ) = collect_cmde_browser_results(
                    task_dir=task_dir,
                    task_id=task_id,
                    context=context,
                    page=page,
                    query=query,
                    page_limit=page_limit,
                    start_index=material_start_index,
                )
                used_cmde_browser = True
            if browser is not None:
                browser.close()
            else:
                context.close()
    except Exception as exc:
        return collection_failed_result(
            task_dir,
            scenario_id,
            query,
            target_url,
            state_dir,
            exc,
        )
    finally:
        if edge_process is not None and edge_process.poll() is None:
            edge_process.terminate()

    probe = page_probe_result(
        scenario_id=scenario_id,
        query=query,
        final_url=final_url,
        title=title,
        text=text,
    )
    status = normalize_browser_collection_status(probe["status"])
    reason_zh = probe["reason_zh"]
    snapshot_paths = [search_snapshot_relative]
    material_start_index = next_material_index(task_dir)
    if used_nmpa_api:
        api_failed = api_payload.get("status") in {
            FailureType.PERMISSION_REQUIRED.value,
            FailureType.COLLECTION_FAILED.value,
        }
        if api_failed:
            collection_errors.append(
                {
                    "stage": "nmpa_api",
                    "status": api_payload.get("status"),
                    "reason": api_payload.get("message", "NMPA page API was not ready."),
                }
            )
            append_jsonl(
                task_dir / "logs" / "debug.jsonl",
                {
                    "time": now_iso(),
                    "event": "nmpa_api_failed_fallback_to_dom",
                    "api_status": api_payload.get("status"),
                    "api_message": api_payload.get("message", ""),
                },
            )
            used_nmpa_api = False
            materials = []
        else:
            status = "completed" if materials else FailureType.NO_RESULTS.value
            reason_zh = ""
            total = sum(
                int((((result.get("listResponse") or {}).get("data") or {}).get("total") or 0))
                for result in api_payload.get("results", [])
            )
            if not reason_zh:
                reason_zh = (
                    f"NMPA 医疗器械注册 API 已采集 {len(materials)} 条详情；列表共返回 {total} 条匹配记录。"
                    if materials
                    else "NMPA 医疗器械注册 API 未采集到符合条件的详情。"
                )
    if used_cmde_browser:
        status = "completed" if materials else FailureType.NO_RESULTS.value
        reason_zh = (
            f"CMDE 搜索结果页已采集 {len(materials)} 条公开材料。"
            if materials
            else "CMDE 搜索结果页未采集到【审评报告】、【指导原则文本库】或【征求意见】匹配材料。"
        )
    if scenario_id == "patenthub_patents" and status == "search_results":
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(state_dir),
                    headless=headless,
                    accept_downloads=True,
                    downloads_path=str(paths["download_dir"]),
                )
                materials, detail_snapshot_paths = collect_patenthub_visible_results(
                    task_dir=task_dir,
                    task_id=task_id,
                    context=context,
                    search_html=html,
                    search_url=final_url,
                    query=query,
                    search_snapshot=search_snapshot_relative,
                    page_limit=page_limit,
                    start_index=material_start_index,
                )
                context.close()
            if materials:
                status = "completed"
                reason_zh = f"专利汇已采集 {len(materials)} 条可见专利基本信息。"
        except Exception as exc:
            append_jsonl(
                task_dir / "logs" / "debug.jsonl",
                {
                    "time": now_iso(),
                    "event": "patenthub_detail_collection_failed",
                    "scenario_id": scenario_id,
                    "error": str(exc),
                },
            )
    if not used_nmpa_api and scenario_id == "nmpa_competitor" and status in {
        "completed",
        FailureType.NEEDS_MANUAL_REVIEW.value,
        "search_results",
    }:
        nmpa_entries = parse_nmpa_result_list(html, final_url)
        if not nmpa_entries:
            status = FailureType.NO_RESULTS.value
            reason_zh = "NMPA browser workflow did not find visible registration result rows."
        else:
            status = "completed"
            reason_zh = f"NMPA 医疗器械注册结果页发现 {len(nmpa_entries)} 条可见结果。"
    if not used_nmpa_api and scenario_id == "nmpa_competitor" and status == "completed":
        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(state_dir),
                    headless=headless,
                    accept_downloads=True,
                    downloads_path=str(paths["download_dir"]),
                )
                (
                    materials,
                    detail_snapshot_paths,
                    nmpa_collection_errors,
                ) = collect_nmpa_visible_results(
                    task_dir=task_dir,
                    task_id=task_id,
                    context=context,
                    search_html=html,
                    search_url=final_url,
                    query=query,
                    search_snapshot=search_snapshot_relative,
                    page_limit=page_limit,
                    start_index=material_start_index,
                    methodology=methodology,
                )
                collection_errors.extend(nmpa_collection_errors)
                context.close()
            if materials:
                status = "completed"
                reason_zh = f"NMPA 医疗器械注册信息已采集 {len(materials)} 条可见详情。"
        except Exception as exc:
            append_jsonl(
                task_dir / "logs" / "debug.jsonl",
                {
                    "time": now_iso(),
                    "event": "nmpa_detail_collection_failed",
                    "scenario_id": scenario_id,
                    "error": str(exc),
                },
            )
    append_jsonl(
        task_dir / "logs" / "debug.jsonl",
        {
            "time": now_iso(),
            "event": "browser_workflow_snapshot_saved",
            "scenario_id": scenario_id,
            "status": status,
            "target_url": target_url,
            "final_url": final_url,
            "snapshot_paths": snapshot_paths,
            "detail_snapshot_paths": detail_snapshot_paths,
            "text_length": len(text),
            "closed_popups": closed_popups,
            "headless": headless,
            "actual_headless": actual_headless,
            "fallback_reason": fallback_reason,
        },
    )
    return {
        "status": status,
        "scenario_id": scenario_id,
        "query": query,
        "target_url": target_url,
        "final_url": final_url,
        "title": title,
        "text_length": len(text),
        "headless": headless,
        "actual_headless": actual_headless,
        "launch_mode": launch_mode,
        "profile_scope": profile_scope,
        "fallback_reason": fallback_reason,
        "state_dir": str(state_dir),
        "state_dir_exists": state_dir.is_dir(),
        "snapshot_paths": snapshot_paths,
        "detail_snapshot_paths": detail_snapshot_paths,
        "downloaded_files": [],
        "materials": materials,
        "collection_errors": collection_errors,
        "blocked_reason": blocked_reason_for(status, reason_zh),
        "pagination": {
            "page_limit": page_limit,
            "pages_visited": 1,
            "has_more": None,
        },
        "closed_popups": closed_popups,
        "message_zh": reason_zh,
    }
