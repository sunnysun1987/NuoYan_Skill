from pathlib import Path

from ivd_research.jsonl import append_jsonl
from ivd_research.translation import (
    TranslationEngine,
    setup_translation_engine,
    text_hash,
    translate_sections,
    translation_status,
)


TRANSLATION_ENV_KEYS = [
    "NUOYAN_TRANSLATION_PROVIDER",
    "NUOYAN_TRANSLATION_API_KEY",
    "OPENAI_API_KEY",
    "NUOYAN_TRANSLATION_BASE_URL",
    "NUOYAN_TRANSLATION_MODEL",
    "NUOYAN_LIBRETRANSLATE_URL",
    "NUOYAN_LIBRETRANSLATE_API_KEY",
]


def test_translate_sections_requires_real_engine_when_not_cached(tmp_path: Path, monkeypatch):
    for key in TRANSLATION_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    engine = TranslationEngine(provider="argos")
    rows = translate_sections(
        [{"label": "Results", "text": "The assay showed AUC 0.92 for Alzheimer disease pathology."}],
        task_dir=tmp_path,
        material_id="MAT-000001",
        engine=engine,
    )

    assert rows[0]["translation_zh"] == ""
    assert rows[0]["translation_status"] == "engine_not_ready"
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


def test_translation_status_reports_builtin_command_and_missing_engine(tmp_path: Path, monkeypatch):
    for key in TRANSLATION_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NUOYAN_TRANSLATION_PROVIDER", "argos")
    append_jsonl(
        tmp_path / "data" / "materials.jsonl",
        {
            "material_id": "MAT-000001",
            "raw_fields": {
                "abstract_sections": [
                    {
                        "label": "Background",
                        "text": "Influenza A and influenza B infections require rapid diagnostic testing in clinical settings.",
                    }
                ]
            },
        },
    )

    status = translation_status(tmp_path)

    assert status["command_available"] is True
    assert status["configured"] is False
    assert status["status"] == "not_configured"
    assert status["active_provider"] == ""
    assert status["english_section_count"] == 1


def test_translation_status_accepts_libretranslate_intranet_route(tmp_path: Path, monkeypatch):
    for key in TRANSLATION_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NUOYAN_TRANSLATION_PROVIDER", "libretranslate")
    monkeypatch.setenv("NUOYAN_LIBRETRANSLATE_URL", "http://translate.intranet.local")

    status = translation_status(tmp_path)

    assert status["configured"] is True
    assert status["active_provider"] == "libretranslate"
    assert status["libretranslate_configured"] is True


def test_setup_translation_engine_can_skip_model_download():
    result = setup_translation_engine(provider="argos", install_model=False)

    assert result["provider"] == "argos"
    assert result["status"] in {"ready", "package_installed_model_missing", "not_installed"}
    assert "next_step_zh" in result
