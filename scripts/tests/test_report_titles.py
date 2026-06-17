from ivd_research.reports import report_display_title


def test_report_display_title_replaces_narrow_feasibility_suffix():
    assert (
        report_display_title("AD项目Aβ40-Aβ42检测立项可行性调研")
        == "AD项目Aβ40-Aβ42检测调研分析综述"
    )


def test_report_display_title_appends_analysis_review_for_plain_topic():
    assert report_display_title("AD项目p-Tau217检测") == "AD项目p-Tau217检测调研分析综述"


def test_report_display_title_keeps_existing_review_title():
    assert report_display_title("AD项目调研分析综述") == "AD项目调研分析综述"
