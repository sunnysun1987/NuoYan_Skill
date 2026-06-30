import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

from .jsonl import append_jsonl, read_jsonl
from .status import now_iso


SECTION_LABEL_ZH = {
    "abstract": "摘要",
    "background": "背景",
    "objective": "目的",
    "objectives": "目的",
    "aim": "目的",
    "aims": "目的",
    "importance": "重要性",
    "design": "设计",
    "setting": "研究场景",
    "participants": "研究对象",
    "methods": "方法",
    "method": "方法",
    "results": "结果",
    "findings": "发现",
    "conclusions": "结论",
    "conclusion": "结论",
    "interpretation": "解读",
    "keywords": "关键词",
    "discussion": "讨论",
    "introduction": "引言",
}

PARAMETER_PATTERNS = [
    (r"\bAUC(?:s)?\s*[=:]?\s*(?:of\s*)?([0-9.]+(?:\s*[-–]\s*[0-9.]+)?)", "AUC"),
    (r"\barea under (?:the )?curve\s*[=:]?\s*([0-9.]+)", "AUC"),
    (r"\bsensitivity\s*(?:of|=|:)?\s*([0-9.]+%?)", "灵敏度"),
    (r"\bspecificity\s*(?:of|=|:)?\s*([0-9.]+%?)", "特异性"),
    (r"\baccuracy\s*(?:of|=|:)?\s*([0-9.]+%?)", "准确度"),
    (r"\bcut[- ]?off(?:s)?\s*(?:of|=|:)?\s*([0-9.]+)", "cut-off"),
    (r"\bOR\s*[=:]\s*([0-9.]+)", "OR"),
    (r"\bHR\s*[=:]\s*([0-9.]+)", "HR"),
    (r"\br\s*[=:]\s*(-?[0-9.]+)", "相关系数 r"),
    (r"\bp\s*[<=>]\s*[0-9.]+", "P 值"),
    (r"\b95%\s*CI[,:\s]*([0-9.\-–,\s]+)", "95% CI"),
    (r"\bn\s*[=:]\s*([0-9,]+)", "样本量 n"),
]


def is_mostly_english(text: str) -> bool:
    text = str(text or "")
    if not text.strip():
        return False
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return ascii_letters >= 20 and ascii_letters > cjk * 2


def section_label_zh(label: str) -> str:
    raw = str(label or "Abstract").strip()
    return SECTION_LABEL_ZH.get(raw.lower(), raw)


def extract_parameters(text: str) -> list[dict[str, str]]:
    raw = " ".join(str(text or "").split())
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pattern, label in PARAMETER_PATTERNS:
        for match in re.finditer(pattern, raw, flags=re.IGNORECASE):
            value = match.group(1) if match.groups() else match.group(0)
            value = " ".join(str(value).split()).strip(" ,.;")
            key = (label, value)
            if value and key not in seen:
                seen.add(key)
                rows.append({"label": label, "value": value})
    return rows[:12]


def parameter_lines(text: str) -> list[str]:
    return [f"{item['label']}：{item['value']}" for item in extract_parameters(text)]


def text_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def translation_cache_path(task_dir: Path) -> Path:
    return task_dir / "data" / "translations.jsonl"


def load_translation_cache(task_dir: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    cache: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in read_jsonl(translation_cache_path(task_dir)):
        key = (
            str(row.get("material_id") or ""),
            str(row.get("field") or ""),
            str(row.get("text_hash") or ""),
        )
        cache[key] = row
    return cache


def cached_translation(
    task_dir: Path,
    *,
    material_id: str,
    field: str,
    text: str,
) -> dict[str, Any] | None:
    cache = load_translation_cache(task_dir)
    return cache.get((material_id, field, text_hash(text)))


class TranslationEngine:
    def __init__(
        self,
        *,
        provider: str = "",
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        timeout: float = 90.0,
    ) -> None:
        self.provider = provider or os.environ.get("NUOYAN_TRANSLATION_PROVIDER", "openai")
        self.model = model or os.environ.get("NUOYAN_TRANSLATION_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.environ.get("NUOYAN_TRANSLATION_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("NUOYAN_TRANSLATION_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    def translate_text(self, text: str, *, context: str = "") -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if not is_mostly_english(raw):
            return raw
        if not self.configured:
            raise RuntimeError(
                "未配置完整中文翻译引擎。请设置 NUOYAN_TRANSLATION_API_KEY 或 OPENAI_API_KEY，"
                "并按需设置 NUOYAN_TRANSLATION_MODEL / NUOYAN_TRANSLATION_BASE_URL。"
            )
        return self._translate_openai_compatible(raw, context=context)

    def _translate_openai_compatible(self, text: str, *, context: str = "") -> str:
        system_prompt = (
            "你是医疗与IVD领域的专业中英翻译。请把英文医学材料完整翻译为中文。"
            "要求：1. 不删减信息，不摘要，不改写为总结；2. 保留 Aβ42/40、p-tau217、CSF、PET、AUC、95% CI、P 值、n 等专业符号和数值；"
            "3. 药品、检测平台、队列名称、机构名可保留英文；4. 输出自然、可直接阅读的中文段落；"
            "5. 不添加原文没有的结论。"
        )
        user_prompt = (
            f"上下文：{context or 'IVD立项调研材料'}\n\n"
            "请完整翻译以下文本为中文：\n"
            f"{text}"
        )
        payload = {
            "model": self.model,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"]).strip()


def translation_status(task_dir: Path) -> dict[str, Any]:
    """Report whether the built-in translation command can generate Chinese reading text."""
    engine = TranslationEngine()
    cache_rows = list(read_jsonl(translation_cache_path(task_dir)))
    completed_rows = [
        row for row in cache_rows if row.get("status") == "completed" and row.get("translation_zh")
    ]
    english_sections = 0
    for material in read_jsonl(task_dir / "data" / "materials.jsonl"):
        raw = material.get("raw_fields") or {}
        sections = raw.get("abstract_sections") or []
        if isinstance(sections, list) and sections:
            iterable = [
                {
                    "label": str(section.get("label") or "Abstract"),
                    "text": str(section.get("text") or ""),
                }
                for section in sections
                if isinstance(section, dict)
            ]
        else:
            iterable = [
                {
                    "label": "Abstract",
                    "text": str(raw.get("abstract") or raw.get("summary") or ""),
                }
            ]
        for section in iterable:
            if is_mostly_english(section.get("text", "")):
                english_sections += 1
    configured = engine.configured
    if configured and completed_rows:
        status = "ready_with_cache"
        message = "内置翻译命令已配置，且已有专业中文阅读缓存。"
    elif configured:
        status = "ready_no_cache"
        message = "内置翻译命令已配置，但当前任务尚未生成专业中文阅读缓存。"
    else:
        status = "not_configured"
        message = "内置翻译命令已安装，但尚未配置翻译 API。配置后可生成专业中文阅读缓存。"
    return {
        "status": status,
        "command_available": True,
        "provider": engine.provider,
        "model": engine.model,
        "base_url_configured": bool(engine.base_url),
        "api_key_configured": bool(engine.api_key),
        "configured": configured,
        "cache_path": str(translation_cache_path(task_dir)),
        "cached_translation_count": len(completed_rows),
        "english_section_count": english_sections,
        "message_zh": message,
        "setup_zh": (
            "需要先配置翻译 API 密钥（NUOYAN_TRANSLATION_API_KEY 或 OPENAI_API_KEY）；"
            "可选配置模型和服务地址（NUOYAN_TRANSLATION_MODEL / NUOYAN_TRANSLATION_BASE_URL）。"
            "配置后由 agent 运行诺研内置翻译命令生成缓存，再重新生成报告。"
        ),
    }


def translate_sections(
    sections: list[dict[str, Any]],
    *,
    task_dir: Path | None = None,
    material_id: str = "",
    engine: TranslationEngine | None = None,
) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    engine = engine or TranslationEngine()
    cache = load_translation_cache(task_dir) if task_dir else {}
    for index, section in enumerate(sections or [], start=1):
        if not isinstance(section, dict):
            continue
        label = str(section.get("label") or "Abstract").strip() or "Abstract"
        text = " ".join(str(section.get("text") or "").split())
        if not text:
            continue
        field = f"abstract:{index}:{label}"
        key = (material_id, field, text_hash(text))
        cached = cache.get(key)
        if cached:
            translation_zh = str(cached.get("translation_zh") or "")
            status = str(cached.get("status") or "completed")
            engine_name = str(cached.get("engine") or "")
            error = str(cached.get("error") or "")
        elif is_mostly_english(text):
            translation_zh = ""
            status = "not_configured"
            engine_name = engine.provider
            error = "未生成完整中文翻译：翻译引擎未配置。"
        else:
            translation_zh = ""
            status = "source_is_chinese"
            engine_name = "source"
            error = ""
        translated.append(
            {
                "label": label,
                "label_zh": section_label_zh(label),
                "text": text,
                "translation_zh": translation_zh,
                "translation_status": status,
                "translation_engine": engine_name,
                "translation_error": error,
                "parameters": extract_parameters(text),
            }
        )
    return translated


def translate_materials(
    task_dir: Path,
    *,
    limit: int = 0,
    force: bool = False,
    provider: str = "",
    model: str = "",
    base_url: str = "",
    api_key: str = "",
) -> dict[str, Any]:
    from .reports import _structured_abstract_items

    engine = TranslationEngine(provider=provider, model=model, base_url=base_url, api_key=api_key)
    if not engine.configured:
        return {
            "status": "not_configured",
            "translated_count": 0,
            "message_zh": (
                "未配置完整中文翻译引擎。请设置 NUOYAN_TRANSLATION_API_KEY 或 OPENAI_API_KEY，"
                "并按需设置 NUOYAN_TRANSLATION_MODEL / NUOYAN_TRANSLATION_BASE_URL。"
            ),
        }
    existing = load_translation_cache(task_dir)
    translated_count = 0
    skipped_count = 0
    failed_count = 0
    errors: list[dict[str, str]] = []
    for material in read_jsonl(task_dir / "data" / "materials.jsonl"):
        material_id = str(material.get("material_id") or "")
        title = str(material.get("title") or "")
        raw = material.get("raw_fields") or {}
        for index, section in enumerate(_structured_abstract_items(raw), start=1):
            label = str(section.get("label") or "Abstract")
            text = " ".join(str(section.get("text") or "").split())
            if not text or not is_mostly_english(text):
                continue
            field = f"abstract:{index}:{label}"
            digest = text_hash(text)
            if not force and (material_id, field, digest) in existing:
                skipped_count += 1
                continue
            if limit and translated_count >= limit:
                return {
                    "status": "partial",
                    "translated_count": translated_count,
                    "skipped_count": skipped_count,
                    "failed_count": failed_count,
                    "errors": errors,
                    "message_zh": f"已按 limit={limit} 生成部分完整中文翻译。",
                }
            try:
                translation_zh = engine.translate_text(text, context=f"{title} / {label}")
                append_jsonl(
                    translation_cache_path(task_dir),
                    {
                        "time": now_iso(),
                        "material_id": material_id,
                        "field": field,
                        "label": label,
                        "text_hash": digest,
                        "source_text": text,
                        "translation_zh": translation_zh,
                        "status": "completed",
                        "engine": engine.provider,
                        "model": engine.model,
                    },
                )
                translated_count += 1
            except Exception as exc:
                failed_count += 1
                errors.append(
                    {
                        "material_id": material_id,
                        "field": field,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return {
        "status": "completed" if failed_count == 0 else "completed_with_errors",
        "translated_count": translated_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
        "errors": errors[:20],
        "message_zh": f"完整中文翻译生成完成：新增 {translated_count} 段，跳过 {skipped_count} 段，失败 {failed_count} 段。",
    }
