from pathlib import Path
import json
import sys
import types

from typer.testing import CliRunner

from ivd_research.cli import app
from ivd_research.confirmations import update_confirmations
from ivd_research.models import FailureType
from ivd_research.scenarios.base import ScenarioResult
from ivd_research.scenarios.cmde_regulatory import collect as collect_cmde
from ivd_research.scenarios.local_import_adapter import collect as collect_local_import
from ivd_research.scenarios.nmpa_competitor import collect as collect_nmpa
from ivd_research.source_adapters.life_science_research_bridge import (
    import_life_science_findings,
)
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


def _hcg_confirmations() -> dict:
    return {
        "task_info": True,
        "keyword_pool": True,
        "collection_scope": True,
        "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
        "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
        "sample_type": "血清/尿液",
        "platform": "荧光免疫层析",
        "methodology": "荧光免疫层析法",
        "intended_use": "妊娠相关检测",
        "target_region": "中国",
        "competitor_scope": "NMPA hCG 同类产品",
        "patent_scope": "中国",
    }


def _import_minimum_life_science(task_id: str, task_dir: Path) -> None:
    databases = [
        "UniProt",
        "NCBI Gene",
        "Human Protein Atlas",
        "ClinicalTrials.gov",
        "Reactome",
    ]
    lanes = ["target_protein", "expression", "clinical", "pathway_network"]
    findings = [
        {
            "source_database": databases[index % len(databases)],
            "evidence_lane": lanes[index % len(lanes)],
            "entity": f"hCG-{index}",
            "query": "beta hCG quantitative immunoassay",
            "title": f"beta-hCG external evidence {index}",
            "result_summary": "beta-hCG is a pregnancy-related glycoprotein biomarker.",
            "source_url": f"https://example.org/life-science/hcg/{index}",
            "identifier": f"LSR-HCG-{index}",
        }
        for index in range(12)
    ]
    import_life_science_findings(task_id, task_dir, findings, query="beta hCG")


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
    assert calls[0] == "core_cn"
    assert "broad_cn" in calls
    assert "short_cn" in calls
    assert "已按" in result.stdout
    assert "个检索层级重试" in result.stdout


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


def test_life_science_plan_command_marks_required_plugin_action(tmp_path: Path):
    state = init_task("AD p-tau181 血液标志物 IVD 调研", tmp_path)
    task_dir = Path(state.task_dir)
    update_confirmations(task_dir, FULL_CONFIRMATIONS)

    result = CliRunner().invoke(
        app,
        [
            "life-science-plan",
            "--task-id",
            state.task_id,
            "--output-root",
            str(tmp_path),
            "--json",
        ],
    )

    task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    scenario = task["scenario_statuses"]["life_science_research"]
    plan_path = task_dir / "staging" / "life_science_research" / "external_plugin_query_plan.json"

    assert result.exit_code == 0
    assert plan_path.exists()
    assert scenario["status"] == "needs_manual_review"
    assert "life-science-research 插件" in scenario["last_message"]
    assert '"minimum_coverage"' in result.stdout


def test_delivery_pipeline_does_not_collect_ad_source_for_hcg(monkeypatch, tmp_path: Path):
    state = init_task("beta-hCG 非 AD 信源装配测试", tmp_path)
    task_dir = Path(state.task_dir)
    update_confirmations(task_dir, _hcg_confirmations())
    _import_minimum_life_science(state.task_id, task_dir)
    calls = []

    def fake_collect(task_id, task_dir, params):
        calls.append(params)
        return ScenarioResult(
            status=FailureType.COLLECTION_FAILED.value,
            failure_type=FailureType.COLLECTION_FAILED,
            message_zh="不应调用 AD 专用信源",
        )

    monkeypatch.setattr("ivd_research.cli.DELIVERY_BROWSER_SCENARIOS", [])
    monkeypatch.setattr("ivd_research.cli.DELIVERY_HTTP_SCENARIOS", ["wiley_alz"])
    monkeypatch.setattr("ivd_research.cli.SCENARIO_COLLECTORS", {"wiley_alz": fake_collect})

    result = CliRunner().invoke(
        app,
        [
            "run-delivery-pipeline",
            "--task-id",
            state.task_id,
            "--output-root",
            str(tmp_path),
            "--skip-network-preflight",
            "--json",
        ],
    )

    task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    scenario = task["scenario_statuses"]["wiley_alz"]

    assert result.exit_code == 0
    assert calls == []
    assert scenario["status"] == "deferred"
    assert "AD 专用信源" in scenario["last_message"]


def test_delivery_pipeline_blocks_hcg_until_life_science_import(monkeypatch, tmp_path: Path):
    state = init_task("beta-hCG LSR-first gate 测试", tmp_path)
    task_dir = Path(state.task_dir)
    update_confirmations(task_dir, _hcg_confirmations())
    calls = []

    def fake_collect(task_id, task_dir, params):
        calls.append(params)
        return ScenarioResult(status="completed", message_zh="不应先采集")

    monkeypatch.setattr("ivd_research.cli.DELIVERY_BROWSER_SCENARIOS", [])
    monkeypatch.setattr("ivd_research.cli.DELIVERY_HTTP_SCENARIOS", ["pubmed_literature"])
    monkeypatch.setattr("ivd_research.cli.SCENARIO_COLLECTORS", {"pubmed_literature": fake_collect})

    result = CliRunner().invoke(
        app,
        [
            "run-delivery-pipeline",
            "--task-id",
            state.task_id,
            "--output-root",
            str(tmp_path),
            "--skip-network-preflight",
            "--json",
        ],
    )

    payload = json.loads(result.stdout)
    task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    scenario = task["scenario_statuses"]["life_science_research"]

    assert result.exit_code == 2
    assert payload["status"] == "needs_life_science_research"
    assert calls == []
    assert scenario["status"] == "needs_manual_review"
    assert (task_dir / "staging" / "life_science_research" / "external_plugin_query_plan.json").exists()
