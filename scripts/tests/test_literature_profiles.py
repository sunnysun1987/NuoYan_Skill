from types import SimpleNamespace

from ivd_research.query_plan import scenario_query_plans


def test_literature_profile_controls_retrieval_limits():
    state = SimpleNamespace(
        topic="p-tau217 Alzheimer disease",
        confirmations={
            "primary_query": "血浆 p-tau217 阿尔茨海默病",
            "english_keywords": "plasma p-tau217 Alzheimer disease",
            "literature_profile": "quick_scan",
            "literature_retmax": 80,
            "literature_date_range": 5,
        },
    )

    plans = scenario_query_plans(state)
    pubmed_params = plans["pubmed_literature"][0].params
    pmc_params = plans["pmc_fulltext"][0].params

    assert pubmed_params["literature_profile"] == "quick_scan"
    assert pubmed_params["retmax"] == 80
    assert pubmed_params["similar_retmax"] == 3
    assert pmc_params["pdf_download_limit"] == 10


def test_complete_literature_profile_keeps_default_floor_when_retmax_is_stale_low():
    state = SimpleNamespace(
        topic="beta-hCG定量检测试剂盒（荧光免疫层析法）",
        confirmations={
            "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
            "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
            "methodology": "荧光免疫层析法",
            "platform": "荧光免疫层析",
            "literature_profile": "complete_literature",
            "literature_retmax": 50,
            "literature_date_range": 10,
        },
    )

    plans = scenario_query_plans(state)

    assert plans["pubmed_literature"][0].params["retmax"] == 200
    assert plans["pmc_fulltext"][0].params["retmax"] == 200
    assert plans["openalex_literature"][0].params["retmax"] == 200
    assert plans["pubmed_literature"][0].params["continue_after_results"] is True
    assert any(
        plan.params["query_role"] == "pubmed_method_keywords"
        and "fluorescence immunochromatographic assay" in plan.query
        and plan.params["retmax"] == 100
        for plan in plans["pubmed_literature"]
    )
    assert any(
        plan.params["query_role"] == "openalex_method_keywords"
        and "lateral flow immunoassay" in plan.query
        for plan in plans["openalex_literature"]
    )
