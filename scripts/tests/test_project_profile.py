from types import SimpleNamespace

from ivd_research.project_profile import formal_scenarios_for, project_domain, project_subject


def _state(**confirmations):
    topic = confirmations.get("primary_query", "")
    return SimpleNamespace(topic=topic, confirmations=confirmations)


def test_non_neurology_ivd_formal_scenarios_exclude_ad_specific_sources():
    state = _state(
        primary_query="beta-hCG定量检测试剂盒（荧光免疫层析法）",
        english_keywords="beta hCG quantitative test kit fluorescence immunochromatography",
        sample_type="serum OR urine",
        methodology="fluorescence immunochromatography",
        intended_use="pregnancy-related testing",
    )

    scenarios = formal_scenarios_for(state)

    assert project_domain(state) == "generic_ivd"
    assert "pubmed_literature" in scenarios
    assert "openalex_literature" in scenarios
    assert "wiley_alz" not in scenarios
    assert "yiigle_zhsjkzz" not in scenarios


def test_respiratory_formal_scenarios_exclude_ad_specific_sources():
    state = _state(
        primary_query="甲型乙型流感核酸检测试剂盒",
        english_keywords="influenza A influenza B PCR test kit",
        sample_type="鼻咽拭子",
        methodology="qPCR",
        intended_use="呼吸道感染辅助诊断",
    )

    scenarios = formal_scenarios_for(state)

    assert project_domain(state) == "respiratory"
    assert "wiley_alz" not in scenarios
    assert "yiigle_zhsjkzz" not in scenarios


def test_ad_formal_scenarios_include_ad_specific_sources():
    state = _state(
        primary_query="血浆 p-tau217 阿尔茨海默病 体外诊断",
        english_keywords="plasma p-tau217 Alzheimer disease biomarker",
        sample_type="血浆",
        methodology="immunoassay",
        intended_use="AD 辅助诊断",
    )

    scenarios = formal_scenarios_for(state)

    assert project_domain(state) == "ad_biomarker"
    assert "yiigle_zhsjkzz" in scenarios
    assert "wiley_alz" in scenarios


def test_confirmed_primary_query_overrides_stale_initial_topic():
    state = SimpleNamespace(
        topic="AD p-tau217 历史任务标题",
        confirmations={
            "primary_query": "beta-hCG定量检测试剂盒（荧光免疫层析法）",
            "english_keywords": "beta hCG quantitative test kit fluorescence immunochromatography",
            "sample_type": "血清/尿液",
            "methodology": "荧光免疫层析法",
            "intended_use": "妊娠相关检测",
        },
    )

    scenarios = formal_scenarios_for(state)

    assert project_domain(state) == "generic_ivd"
    assert "wiley_alz" not in scenarios
    assert "yiigle_zhsjkzz" not in scenarios


def test_generic_multiplex_immunoassay_is_not_misclassified_as_respiratory():
    state = _state(
        primary_query="降钙素原 PCT 定量检测试剂盒",
        english_keywords="procalcitonin multiplex immunoassay sepsis",
        chinese_synonyms="降钙素原；PCT",
        sample_type="血清/血浆",
        methodology="多重免疫分析",
        intended_use="细菌感染和脓毒症风险辅助评估",
    )

    assert project_domain(state) == "generic_ivd"
    assert project_subject(state) == "降钙素原"
