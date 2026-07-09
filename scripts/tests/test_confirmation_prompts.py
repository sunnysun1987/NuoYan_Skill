from ivd_research.cli import CONFIRMATION_QUESTIONS


def test_confirmation_prompts_are_not_ad_specific_defaults():
    joined = "\n".join(CONFIRMATION_QUESTIONS.values())

    for forbidden in ["AD", "阿尔茨海默", "p-tau", "Abeta", "NfL"]:
        assert forbidden not in joined
    assert "妊娠" not in joined
    assert "目标检测项目" in joined or "检测项目" in joined
