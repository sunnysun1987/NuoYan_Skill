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
    return SimpleNamespace(topic="AD p-Tau217", confirmations=defaults)


def test_literature_retmax_all_flows_to_pubmed_and_pmc():
    plans = scenario_query_plans(_state())

    assert plans["pubmed_literature"][0].params["retmax"] == "all"
    assert plans["pmc_fulltext"][0].params["retmax"] == "all"
    assert plans["openalex_literature"][0].params["retmax"] == "all"
    query = plans["pubmed_literature"][0].query
    assert "血浆" not in query
    assert "阿尔茨海默病辅助诊断" not in query


def test_pubmed_safe_int_all_uses_high_batch_cap():
    assert _safe_int("all", 20) == MAX_RETMAX
    assert _safe_int("全部", 20) == MAX_RETMAX
