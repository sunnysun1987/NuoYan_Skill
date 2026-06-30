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

