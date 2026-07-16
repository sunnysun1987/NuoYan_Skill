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
    assert plans["pubmed_literature"][0].params["query_role"] == "pubmed_core_keywords"
    assert plans["pmc_fulltext"][0].params["query_role"] == "pmc_core_keywords"
    assert plans["openalex_literature"][0].params["query_role"] == "openalex_core_keywords"
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
    assert plans["cmde_regulatory"][0].params["query_role"] == "core_cn"
    assert any(plan.params["query_role"] == "broad_cn" for plan in plans["cmde_regulatory"])


def test_hcg_query_plan_does_not_enable_alzheimer_specific_source():
    plans = scenario_query_plans(
        _state(
            primary_query="beta-hCG定量检测试剂盒（荧光免疫层析法）",
            english_keywords="human chorionic gonadotropin beta hCG immunoassay pregnancy testing",
            chinese_synonyms="人绒毛膜促性腺激素；β-hCG；hCG",
            sample_type="serum OR urine",
            platform="fluorescence immunochromatography",
            methodology="immunochromatographic assay",
            intended_use="pregnancy-related testing",
        )
    )

    assert "wiley_alz" not in plans
    assert "yiigle_zhsjkzz" not in plans
    assert plans["standards_current"][0].query == "人绒毛膜促性腺激素"
    assert plans["standards_current"][0].params["query_role"] == "core_cn"
    assert "serum" not in plans["openalex_literature"][0].query.lower()
    assert "urine" not in plans["openalex_literature"][0].query.lower()
    assert plans["pubmed_literature"][0].query == "human chorionic gonadotropin beta hCG immunoassay"
    assert plans["pmc_fulltext"][0].query == "human chorionic gonadotropin beta hCG immunoassay"
    assert plans["openalex_literature"][0].query == "human chorionic gonadotropin beta hCG immunoassay"
    assert any(
        plan.params["query_role"] == "openalex_method_keywords"
        and "fluorescence immunochromatographic assay" in plan.query
        for plan in plans["openalex_literature"]
    )
    assert any(
        plan.params["query_role"] == "pubmed_method_keywords"
        and "lateral flow immunoassay" in plan.query
        for plan in plans["pubmed_literature"]
    )
    query_text = "\n".join(
        plan.query
        for scenario_plans in plans.values()
        for plan in scenario_plans
    )
    assert "Alzheimer" not in query_text
    assert "AD " not in query_text


def test_generic_aliases_build_source_safe_query_ladder_without_project_rule():
    plans = scenario_query_plans(
        _state(
            primary_query="降钙素原 PCT 定量检测试剂盒（化学发光法）",
            english_keywords="procalcitonin PCT immunoassay sepsis quantitative test kit serum",
            chinese_synonyms="降钙素原；PCT",
            sample_type="血清/血浆",
            platform="化学发光",
            methodology="免疫分析",
            intended_use="细菌感染和脓毒症风险辅助评估",
        )
    )

    assert plans["standards_current"][0].query == "降钙素原"
    assert plans["openalex_literature"][0].query == "procalcitonin PCT immunoassay sepsis"
    assert "wiley_alz" not in plans
    assert "yiigle_zhsjkzz" not in plans


def test_product_sources_use_layered_queries_instead_of_full_profile_blob():
    plans = scenario_query_plans(
        _state(
            primary_query="降钙素原 PCT 定量检测试剂盒（化学发光法）",
            english_keywords="procalcitonin PCT immunoassay sepsis",
            chinese_synonyms="降钙素原；PCT",
            sample_type="血清、血浆、全血；分别验证稳定性和基质效应",
            platform="化学发光、免疫荧光、POCT",
            methodology="免疫分析为主，覆盖夹心法和竞争法",
            intended_use="细菌感染和脓毒症风险辅助评估",
        )
    )

    for scenario_id in ["nmpa_competitor", "patenthub_patents"]:
        source_plans = plans[scenario_id]
        assert len(source_plans) >= 4
        assert any(plan.params["query_role"] == "core_cn" for plan in source_plans)
        assert any(plan.params["query_role"] == "core_product_cn" for plan in source_plans)
        assert max(len(plan.query) for plan in source_plans) <= 140
        assert all("分别验证稳定性" not in plan.query for plan in source_plans)


def test_ad_query_plan_keeps_alzheimer_specific_source():
    plans = scenario_query_plans(_state())

    assert "wiley_alz" in plans
    assert "yiigle_zhsjkzz" in plans
    assert "Alzheimer disease" in plans["wiley_alz"][0].query
    assert "p-tau217" in plans["wiley_alz"][0].query
