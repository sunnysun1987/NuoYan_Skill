from types import SimpleNamespace

from ivd_research.query_plan import scenario_query_plans
from ivd_research.scenarios.pubmed_pmc import MAX_RETMAX, _safe_int


def _state(**confirmations):
    defaults = {
        "primary_query": "AD p-Tau217 血液标志物 IVD",
        "english_keywords": "Alzheimer disease p-tau217 plasma blood biomarker",
        "sample_type": "plasma OR serum",
        "platform": "chemiluminescence OR ELISA OR Simoa",
        "methodology": "immunoassay",
        "intended_use": "diagnosis OR screening OR risk stratification",
        "literature_date_range": {"start": "2021-06-17", "end": "2026-06-17"},
        "literature_retmax": "all",
        "patent_scope": "全球",
    }
    defaults.update(confirmations)
    return SimpleNamespace(topic=defaults["primary_query"], confirmations=defaults)


def test_literature_retmax_all_flows_to_pubmed_and_pmc():
    plans = scenario_query_plans(_state())

    assert plans["pubmed_literature"][0].params["retmax"] == "all"
    assert plans["pmc_fulltext"][0].params["retmax"] == "all"
    assert plans["openalex_literature"][0].params["retmax"] == "all"
    query = plans["pubmed_literature"][0].query
    assert "血浆" not in query
    assert "阿尔茨海默病辅助诊断" not in query
    openalex_query = plans["openalex_literature"][0].query
    assert " OR " not in openalex_query
    assert " AND " not in openalex_query
    assert "(" not in openalex_query
    assert len(openalex_query) <= 220


def test_pubmed_safe_int_all_uses_high_batch_cap():
    assert _safe_int("all", 20) == MAX_RETMAX
    assert _safe_int("全部", 20) == MAX_RETMAX


def test_from_to_date_range_and_short_browser_retry_plans():
    plans = scenario_query_plans(
        _state(literature_date_range={"from": "2021-06-17", "to": "2026-06-17"})
    )

    assert plans["pubmed_literature"][0].params["date_range"] == {
        "from": "2021-06-17",
        "to": "2026-06-17",
    }
    assert len(plans["cmde_regulatory"]) >= 2
    assert plans["cmde_regulatory"][1].params["query_role"] == "short_cn"


def test_hcg_query_plan_does_not_enable_alzheimer_specific_source():
    plans = scenario_query_plans(
        _state(
            primary_query="beta-hCG定量检测试剂盒（荧光免疫层析法）",
            english_keywords="beta hCG quantitative test kit fluorescence immunochromatography",
            sample_type="serum OR urine",
            platform="fluorescence immunochromatography",
            methodology="immunochromatographic assay",
            intended_use="pregnancy-related testing",
        )
    )

    assert "wiley_alz" not in plans
    query_text = "\n".join(
        plan.query
        for scenario_plans in plans.values()
        for plan in scenario_plans
    )
    assert "Alzheimer" not in query_text
    assert "AD " not in query_text


def test_ad_query_plan_keeps_alzheimer_specific_source():
    plans = scenario_query_plans(_state())

    assert "wiley_alz" in plans
    assert "Alzheimer disease" in plans["wiley_alz"][0].query
    assert "p-tau217" in plans["wiley_alz"][0].query
