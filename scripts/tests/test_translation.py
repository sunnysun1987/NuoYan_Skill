from pathlib import Path

from ivd_research.jsonl import append_jsonl
from ivd_research.translation import text_hash, translate_sections


def test_translate_sections_requires_real_engine_when_not_cached(tmp_path: Path):
    rows = translate_sections(
        [{"label": "Results", "text": "The assay showed AUC 0.92 for Alzheimer disease pathology."}],
        task_dir=tmp_path,
        material_id="MAT-000001",
    )

    assert rows[0]["translation_zh"] == ""
    assert rows[0]["translation_status"] == "not_configured"
    assert "未生成完整中文翻译" in rows[0]["translation_error"]


def test_translate_sections_uses_cached_complete_translation(tmp_path: Path):
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."
    append_jsonl(
        tmp_path / "data" / "translations.jsonl",
        {
            "material_id": "MAT-000001",
            "field": "abstract:1:Results",
            "text_hash": text_hash(text),
            "translation_zh": "第一句。第二句。第三句。第四句。",
            "status": "completed",
            "engine": "test",
        },
    )

    rows = translate_sections(
        [{"label": "Results", "text": text}],
        task_dir=tmp_path,
        material_id="MAT-000001",
    )

    assert rows[0]["translation_zh"] == "第一句。第二句。第三句。第四句。"
    assert rows[0]["translation_status"] == "completed"


def test_translate_sections_skips_chinese_source_text(tmp_path: Path):
    rows = translate_sections(
        [{"label": "摘要", "text": "这是一段中文摘要，已经可以直接阅读，不需要再生成中文阅读版。"}],
        task_dir=tmp_path,
        material_id="MAT-000002",
    )

    assert rows[0]["translation_zh"] == ""
    assert rows[0]["translation_status"] == "source_is_chinese"
