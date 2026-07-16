import json

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
