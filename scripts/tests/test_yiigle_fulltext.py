import json

from ivd_research.scenarios import yiigle_fulltext
from ivd_research.scenarios.yiigle_fulltext import parse_yiigle_api_result


def test_parse_yiigle_api_result_builds_traceable_materials(tmp_path):
    payload = {
        "code": 200,
        "data": {
            "result": {
                "searchTotal": 938,
                "infos": [
                    {
                        "artId": 1627708,
                        "artTitle": "血清人绒毛膜促性腺激素水平与异位妊娠结局",
                        "artAbstract": "结果显示血清 beta-hCG 日变化率具有预测价值。",
                        "artDoi": "10.3760/example",
                        "journalCn": "中华实验外科杂志",
                        "artPubYear": 2025,
                        "artPubDate": "2025-11-08T06:59:18.000+00:00",
                        "authorNames": ["张三", "李四"],
                        "artificialKeywords": ["异位妊娠", "人绒毛膜促性腺激素"],
                        "docType": "原创论文",
                        "artUrl": "https://rs.yiigle.com/cmaid/1627708",
                    },
                    {
                        "artId": 1,
                        "artTitle": "时间范围外文献",
                        "artPubYear": 2010,
                    },
                ],
            }
        },
    }

    result = parse_yiigle_api_result(
        payload,
        task_id="TASK-TEST",
        task_dir=tmp_path,
        material_id="MAT-000001",
        query="篇关摘=(人绒毛膜促性腺激素)",
        keyword="人绒毛膜促性腺激素",
        raw_text=json.dumps(payload, ensure_ascii=False),
        date_range={"start": "2016-01-01", "end": "2026-12-31"},
    )

    assert result.status == "completed"
    assert len(result.materials) == 1
    material = result.materials[0]
    assert material.title.startswith("血清人绒毛膜促性腺激素")
    assert material.source_url == "https://rs.yiigle.com/cmaid/1627708"
    assert material.raw_fields["search_total"] == 938
    assert material.raw_fields["abstract"].startswith("结果显示")
    assert material.extracted_text_path
    assert (tmp_path / material.extracted_text_path).exists()
    assert material.content_snapshot_path
    assert (tmp_path / material.content_snapshot_path).exists()


def test_yiigle_search_paginates_until_date_range_limit(monkeypatch):
    calls = []

    def fake_page(keyword, *, page, page_size):
        calls.append((keyword, page, page_size))
        rows = {
            1: [
                {"artId": 1, "artTitle": "旧文献1", "artPubYear": 2010},
                {"artId": 2, "artTitle": "旧文献2", "artPubYear": 2011},
            ],
            2: [
                {"artId": 3, "artTitle": "beta-hCG 新文献1", "artPubYear": 2024},
                {"artId": 4, "artTitle": "beta-hCG 新文献2", "artPubYear": 2025},
            ],
        }[page]
        return {
            "code": 200,
            "data": {"result": {"searchTotal": 100, "infos": rows}},
        }

    monkeypatch.setattr(yiigle_fulltext, "_request_yiigle_page", fake_page)

    payload, raw_text = yiigle_fulltext.yiigle_api_search(
        "beta-hCG",
        retmax=2,
        date_range={"start": "2016-01-01", "end": "2026-12-31"},
    )

    result = payload["data"]["result"]
    assert [call[1] for call in calls] == [1, 2]
    assert result["retrieval"]["records_scanned"] == 4
    assert result["retrieval"]["date_range_matches_scanned"] == 2
    assert result["retrieval"]["date_range_total"] is None
    assert len(json.loads(raw_text)["data"]["result"]["infos"]) == 4


def test_yiigle_retmax_uses_profile_depth_instead_of_fifty_item_cap():
    assert yiigle_fulltext._safe_int(200, 20) == 200


def test_yiigle_pagination_uses_actual_response_page_size(monkeypatch):
    calls = []

    def fake_page(keyword, *, page, page_size):
        calls.append((page, page_size))
        start = (page - 1) * 10
        rows = [
            {
                "artId": start + index,
                "artTitle": f"文献 {start + index}",
                "artPubYear": 2025,
            }
            for index in range(1, 11)
        ]
        return {
            "code": 200,
            "data": {"result": {"searchTotal": 30, "infos": rows}},
        }

    monkeypatch.setattr(yiigle_fulltext, "_request_yiigle_page", fake_page)

    payload, _ = yiigle_fulltext.yiigle_api_search("hCG", retmax=25)

    retrieval = payload["data"]["result"]["retrieval"]
    assert [page for page, _ in calls] == [1, 2, 3]
    assert retrieval["records_scanned"] == 30
    assert retrieval["effective_page_size"] == 10


def test_yiigle_date_filter_does_not_treat_unknown_year_as_in_range(tmp_path):
    payload = {
        "code": 200,
        "data": {
            "result": {
                "searchTotal": 3,
                "infos": [
                    {"artId": 1, "artTitle": "年份未知"},
                    {
                        "artId": 2,
                        "artTitle": "日期字段可确认",
                        "artPubDate": "2025-05-01T00:00:00.000+00:00",
                    },
                    {"artId": 3, "artTitle": "范围外", "artPubYear": 2010},
                ],
            }
        },
    }

    result = parse_yiigle_api_result(
        payload,
        task_id="TASK-TEST",
        task_dir=tmp_path,
        material_id="MAT-000001",
        query="hCG",
        keyword="hCG",
        raw_text=json.dumps(payload, ensure_ascii=False),
        date_range={"start": "2020-01-01", "end": "2026-12-31"},
        retmax=10,
    )

    assert [material.title for material in result.materials] == ["日期字段可确认"]
