from pathlib import Path
import subprocess
import sys
from typing import Any

from .jsonl import append_jsonl
from .browser_workflows import browser_workflow, page_probe_result, search_url_for_workflow
from .site_profiles import site_profile
from .status import now_iso


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return True


def browser_state_dir(task_dir: Path, scenario_id: str, profile_scope: str = "task") -> Path:
    if profile_scope == "user":
        return Path.home() / ".ivd_research_browser_state" / scenario_id
    if profile_scope != "task":
        raise ValueError(f"Unsupported browser profile scope: {profile_scope}")
    return task_dir / "browser_state" / scenario_id


def prepare_browser_session(task_dir: Path, scenario_id: str, profile_scope: str = "task") -> dict[str, Any]:
    profile = site_profile(scenario_id)
    state_dir = browser_state_dir(task_dir, scenario_id, profile_scope)
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "scenario_id": scenario_id,
        "entry_url": profile["entry_url"],
        "state_dir": str(state_dir),
        "profile_scope": profile_scope,
        "state_dir_exists": state_dir.is_dir(),
        "playwright_available": playwright_available(),
        "message_zh": (
            "已准备 Playwright 持久化浏览器会话目录。"
            "如需登录或真人验证，请由用户在可见浏览器中手动完成，agent 只能读取合法可见内容。"
        ),
    }
    append_jsonl(
        task_dir / "logs" / "events.jsonl",
        {
            "time": now_iso(),
            "event": "browser_session_prepared",
            "scenario_id": scenario_id,
            "message_zh": payload["message_zh"],
            "state_dir": str(state_dir),
        },
    )
    return payload


def _terminate_background_session(state_dir: Path) -> list[int]:
    """Terminate any background browser process holding a lock on state_dir.

    Returns list of PIDs that were terminated.
    """
    terminated: list[int] = []

    # Strategy 1: use psutil if available (cross-platform, reliable)
    try:
        import psutil as _psutil_module  # type: ignore[import-untyped]

        for proc in _psutil_module.process_iter(["pid", "cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            cmd_str = " ".join(cmdline)
            if "launch_persistent_context" not in cmd_str:
                continue
            if str(state_dir) not in cmd_str:
                continue
            try:
                proc.terminate()
                proc.wait(timeout=5)
                terminated.append(proc.info["pid"])
            except Exception:
                try:
                    proc.kill()
                    terminated.append(proc.info["pid"])
                except Exception:
                    pass
        return terminated
    except ImportError:
        pass

    # Strategy 2: fall back to wmic + taskkill (Windows)
    import subprocess as _sp

    target = str(state_dir).replace("\\", "\\\\")
    try:
        result = _sp.run(
            ["wmic", "process", "where", f"commandline like '%{target}%'", "get", "processid"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            pid_str = line.strip()
            if pid_str.isdigit():
                try:
                    _sp.run(["taskkill", "/PID", pid_str, "/F"],
                            capture_output=True, timeout=5)
                    terminated.append(int(pid_str))
                except Exception:
                    pass
    except Exception:
        pass
    return terminated


def open_browser_session(
    task_dir: Path,
    scenario_id: str,
    url: str | None = None,
    headless: bool = False,
    background: bool = False,
    profile_scope: str = "task",
) -> dict[str, Any]:
    profile = site_profile(scenario_id)
    target_url = url or profile["entry_url"]
    state_dir = browser_state_dir(task_dir, scenario_id, profile_scope)
    state_dir.mkdir(parents=True, exist_ok=True)

    if background:
        script = (
            "from pathlib import Path\n"
            "from playwright.sync_api import sync_playwright\n"
            "import sys, time\n"
            "state_dir = Path(sys.argv[1])\n"
            "target_url = sys.argv[2]\n"
            "with sync_playwright() as p:\n"
            "    context = p.chromium.launch_persistent_context(user_data_dir=str(state_dir), headless=False, accept_downloads=True)\n"
            "    page = context.pages[0] if context.pages else context.new_page()\n"
            "    page.goto(target_url, wait_until='domcontentloaded', timeout=30000)\n"
            "    while True:\n"
            "        if not context.pages:\n"
            "            break\n"
            "        time.sleep(1)\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(state_dir), target_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP") else 0,
        )
        append_jsonl(
            task_dir / "logs" / "events.jsonl",
            {
                "time": now_iso(),
                "event": "browser_session_opened_background",
                "scenario_id": scenario_id,
                "url": target_url,
                "pid": process.pid,
                "state_dir": str(state_dir),
            },
        )
        return {
            "status": "opened_background",
            "scenario_id": scenario_id,
            "state_dir": str(state_dir),
            "profile_scope": profile_scope,
            "state_dir_exists": state_dir.is_dir(),
            "pid": process.pid,
            "message_zh": "已在后台打开 Playwright 持久化浏览器会话；请在浏览器中完成登录/验证后再运行采集。",
        }

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "status": "dependency_missing",
            "scenario_id": scenario_id,
            "state_dir": str(state_dir),
            "profile_scope": profile_scope,
            "state_dir_exists": state_dir.is_dir(),
            "message_zh": f"缺少 Playwright，无法打开持久化浏览器会话：{exc}",
        }

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(state_dir),
                headless=headless,
                accept_downloads=True,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            append_jsonl(
                task_dir / "logs" / "events.jsonl",
                {
                    "time": now_iso(),
                    "event": "browser_session_opened",
                    "scenario_id": scenario_id,
                    "url": target_url,
                    "message_zh": "已打开 Playwright 持久化浏览器会话。",
                },
            )
            input("请在浏览器中完成登录/验证或页面观察。完成后关闭浏览器，或回到这里按 Enter 继续...")
            context.close()
    except Exception as exc:
        append_jsonl(
            task_dir / "logs" / "debug.jsonl",
            {
                "time": now_iso(),
                "event": "browser_session_open_failed",
                "scenario_id": scenario_id,
                "error": str(exc),
            },
        )
        return {
            "status": "open_failed",
            "scenario_id": scenario_id,
            "state_dir": str(state_dir),
            "profile_scope": profile_scope,
            "state_dir_exists": state_dir.is_dir(),
            "message_zh": f"Playwright 持久化浏览器会话打开失败：{exc}",
        }

    return {
        "status": "closed",
        "scenario_id": scenario_id,
        "state_dir": str(state_dir),
        "profile_scope": profile_scope,
        "state_dir_exists": state_dir.is_dir(),
        "message_zh": "Playwright 持久化浏览器会话已关闭，登录态/验证状态会保留在会话目录中。",
    }


def probe_browser_workflow(
    task_dir: Path,
    scenario_id: str,
    query: str,
    headless: bool = True,
    profile_scope: str = "task",
) -> dict[str, Any]:
    workflow = browser_workflow(scenario_id)
    target_url = search_url_for_workflow(workflow, query)
    state_dir = browser_state_dir(task_dir, scenario_id, profile_scope)
    state_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = task_dir / "downloads" / "browser_probe"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return {
            "status": "dependency_missing",
            "scenario_id": scenario_id,
            "target_url": target_url,
            "state_dir": str(state_dir),
            "profile_scope": profile_scope,
            "state_dir_exists": state_dir.is_dir(),
            "message_zh": f"缺少 Playwright，无法执行浏览器探测：{exc}",
        }

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(state_dir),
                headless=headless,
                accept_downloads=True,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            title = page.title()
            text = page.locator("body").inner_text(timeout=5000) if page.locator("body").count() else ""
            html = page.content()
            final_url = page.url
            snapshot_path = snapshot_dir / f"{scenario_id}_probe.html"
            snapshot_path.write_text(html, encoding="utf-8", errors="ignore")
            context.close()
    except Exception as exc:
        append_jsonl(
            task_dir / "logs" / "debug.jsonl",
            {
                "time": now_iso(),
                "event": "browser_workflow_probe_failed",
                "scenario_id": scenario_id,
                "target_url": target_url,
                "error": str(exc),
            },
        )
        return {
            "status": "collection_failed",
            "scenario_id": scenario_id,
            "target_url": target_url,
            "state_dir": str(state_dir),
            "profile_scope": profile_scope,
            "state_dir_exists": state_dir.is_dir(),
            "message_zh": f"Playwright 浏览器探测失败：{exc}",
        }

    result = page_probe_result(
        scenario_id=scenario_id,
        query=query,
        final_url=final_url,
        title=title,
        text=text,
    )
    result.update(
        {
            "state_dir": str(state_dir),
            "profile_scope": profile_scope,
            "state_dir_exists": state_dir.is_dir(),
            "snapshot_path": str(snapshot_path.relative_to(task_dir)),
            "message_zh": result["reason_zh"],
        }
    )
    append_jsonl(
        task_dir / "logs" / "events.jsonl",
        {
            "time": now_iso(),
            "event": "browser_workflow_probed",
            "scenario_id": scenario_id,
            "status": result["status"],
            "target_url": target_url,
            "final_url": final_url,
            "snapshot_path": result["snapshot_path"],
            "message_zh": result["message_zh"],
        },
    )
    return result
