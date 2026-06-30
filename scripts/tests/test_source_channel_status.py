from pathlib import Path
import sys
import types

import pytest
from typer.testing import CliRunner

from ivd_research.cli import app
from ivd_research.confirmations import update_confirmations
from ivd_research.models import FailureType
from ivd_research.scenarios.base import ScenarioResult
from ivd_research.scenarios.cmde_regulatory import collect as collect_cmde
from ivd_research.scenarios.local_import_adapter import collect as collect_local_import
from ivd_research.scenarios.nmpa_competitor import collect as collect_nmpa
from ivd_research.status import init_task


FULL_CONFIRMATIONS = {
    "task_info": True,
    "keyword_pool": True,
    "collection_scope": True,
    "primary_query": "血浆 p-tau217 阿尔茨海默病 体外诊断",
    "english_keywords": "plasma p-tau217 Alzheimer disease IVD",
    "sample_type": "血浆",
    "platform": "化学发光",
    "methodology": "免疫分析",
    "intended_use": "阿尔茨海默病辅助诊断",
    "target_region": "中国",
    "competitor_scope": "NMPA 已注册同类产品",
    "patent_scope": "全球",
}


def test_run_scenario_retries_query_plans(monkeypatch, tmp_path: Path):
    state = init_task("p-tau217 信源重试测试", tmp_path)
    task_dir = Path(state.task_dir)
    update_confirmations(task_dir, FULL_CONFIRMATIONS)
    calls = []

    def fake_collect(task_id, task_dir, params):
        calls.append(params["query_role"])
        return ScenarioResult(
            status=FailureType.NO_RESULTS.value,
            failure_type=FailureType.NO_RESULTS,
            message_zh=f"no result for {params['query_role']}",
        )

    monkeypatch.setattr(
        "ivd_research.cli.SCENARIO_COLLECTORS",
        {"cma_lab_management": fake_collect},
    )

    result = CliRunner().invoke(
        app,
        [
            "run-scenario",
            "--task-id",
            state.task_id,
            "--scenario",
            "cma_lab_management",
            "--output-root",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert calls == ["broad_cn", "short_cn", "method_specific_cn"]
    assert "已按 3 个检索层级重试" in result.stdout


def test_nmpa_dom_structure_failures_are_collection_failed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "ivd_research.scenarios.nmpa_competitor.collect_nmpa_http",
        lambda **kwargs: ScenarioResult(
            status=FailureType.COLLECTION_FAILED.value,
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh="HTTP 412",
            collection_errors=[{"status": FailureType.COLLECTION_FAILED.value}],
        ),
        raising=False,
    )

    class FakeContext:
        def new_page(self):
            return object()

        def close(self):
            return None

    class FakeBrowser:
        def new_context(self, **kwargs):
            return FakeContext()

        def close(self):
            return None

    class FakeChromium:
        def launch(self, **kwargs):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_sync_api = types.SimpleNamespace(sync_playwright=lambda: FakePlaywright())
    fake_playwright = types.SimpleNamespace(sync_api=fake_sync_api)
    monkeypatch.setitem(sys.modules, "playwright", fake_playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)
    monkeypatch.setattr(
        "ivd_research.scenarios.nmpa_dom_collect.collect_nmpa_dom",
        lambda **kwargs: (
            [],
            [],
            [
                {
                    "registration_type": "境内医疗器械（注册）",
                    "status": FailureType.COLLECTION_FAILED.value,
                    "reason": "Could not find category tab",
                }
            ],
        ),
    )

    result = collect_nmpa(
        task_id="TASK",
        task_dir=tmp_path,
        params={"query": "葡萄糖", "material_id": "MAT-000001"},
    )

    assert result.status == FailureType.COLLECTION_FAILED.value
    assert "渠道适配失败" in result.message_zh


def test_cmde_security_script_page_is_permission_required(monkeypatch, tmp_path: Path):
    security_html = """<!doctype html><html><head><script>$_ts={};</script></head><body></body></html><script>_$_v();</script>"""

    monkeypatch.setattr(
        "ivd_research.scenarios.cmde_regulatory._fetch_html",
        lambda url: (security_html, url, 200),
    )

    result = collect_cmde(
        task_id="TASK",
        task_dir=tmp_path,
        params={"query": "核酸检测试剂", "material_id": "MAT-000001", "page_limit": 1},
    )

    assert result.status == FailureType.PERMISSION_REQUIRED.value
    assert "安全脚本" in result.message_zh


def test_local_import_run_scenario_points_to_import_local(tmp_path: Path):
    result = collect_local_import(
        task_id="TASK",
        task_dir=tmp_path,
        params={"query": "", "material_id": "MAT-000001"},
    )

    assert result.status == FailureType.NEEDS_MANUAL_REVIEW.value
    assert "import-local" in result.message_zh
