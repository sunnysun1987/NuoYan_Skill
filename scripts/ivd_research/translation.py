import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
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

PROVIDER_LABEL_ZH = {
    "argos": "Argos Translate 离线翻译",
    "libretranslate": "LibreTranslate 企业内网翻译服务",
    "openai": "OpenAI-compatible 云端翻译网关",
}


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


def subprocess_env_with_certifi() -> dict[str, str]:
    env = dict(os.environ)
    try:
        import certifi

        cert_path = certifi.where()
        env.setdefault("SSL_CERT_FILE", cert_path)
        env.setdefault("REQUESTS_CA_BUNDLE", cert_path)
    except Exception:
        pass
    return env


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


def setup_translation_engine(
    *,
    provider: str = "argos",
    install_model: bool = True,
    timeout: int = 180,
) -> dict[str, Any]:
    provider = str(provider or "argos").lower()
    if provider != "argos":
        return {
            "status": "unsupported_provider",
            "provider": provider,
            "message_zh": "当前自动安装仅支持 Argos Translate 离线翻译依赖。LibreTranslate 建议由企业管理员部署为内网服务。",
        }
    commands: list[list[str]] = []
    if importlib.util.find_spec("argostranslate") is None:
        commands.append([sys.executable, "-m", "pip", "install", "argostranslate"])
    executed: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
            env=subprocess_env_with_certifi(),
        )
        executed.append(
            {
                "command": " ".join(command),
                "returncode": completed.returncode,
                "stdout_tail": completed.stdout[-1000:],
                "stderr_tail": completed.stderr[-1000:],
            }
        )
        if completed.returncode != 0:
            return {
                "status": "install_failed",
                "provider": "argos",
                "commands": executed,
                "message_zh": "Argos Translate Python 依赖安装失败。可由 IT 管理员在企业标准环境中预装后再分发诺研_skill。",
            }
    engine = TranslationEngine(provider="argos")
    if install_model and engine.argos_installed() and not engine.argos_ready():
        for command in [
            ["argospm", "update"],
            ["argospm", "install", "translate-en_zh"],
        ]:
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=subprocess_env_with_certifi(),
                )
                executed.append(
                    {
                        "command": " ".join(command),
                        "returncode": completed.returncode,
                        "stdout_tail": completed.stdout[-1000:],
                        "stderr_tail": completed.stderr[-1000:],
                    }
                )
                if completed.returncode != 0:
                    break
            except (OSError, subprocess.SubprocessError) as exc:
                executed.append(
                    {
                        "command": " ".join(command),
                        "returncode": -1,
                        "stdout_tail": "",
                        "stderr_tail": f"{type(exc).__name__}: {exc}",
                    }
                )
                break
        engine = TranslationEngine(provider="argos")
    if engine.argos_ready():
        status = "ready"
        message = "Argos Translate 已安装，且 en→zh 离线翻译模型可用。"
    elif engine.argos_installed():
        status = "package_installed_model_missing"
        message = (
            "Argos Translate Python 包已安装，但尚未导入 en→zh 离线翻译模型。"
            "请从 Argos Translate 模型库下载 English→Chinese 模型并用 argospm install 导入，"
            "或由 IT 管理员预装模型后统一分发。"
        )
    else:
        status = "not_installed"
        message = "Argos Translate 尚未安装。"
    return {
        "status": status,
        "provider": "argos",
        "commands": executed,
        "argos_installed": engine.argos_installed(),
        "argos_model_ready": engine.argos_ready(),
        "message_zh": message,
        "next_step_zh": (
            "如本机模型下载受证书、代理或内网限制影响，请由 IT 管理员下载 English→Chinese .argosmodel 后运行 argospm install 导入。"
            "模型安装完成后运行 translation-status 确认 argos_model_ready=true，再运行 translate-materials 生成 data/translations.jsonl。"
        ),
    }


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
        self.provider = provider or os.environ.get("NUOYAN_TRANSLATION_PROVIDER", "auto")
        self.model = model or os.environ.get("NUOYAN_TRANSLATION_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.environ.get("NUOYAN_TRANSLATION_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("NUOYAN_TRANSLATION_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.libretranslate_url = (
            base_url
            or os.environ.get("NUOYAN_LIBRETRANSLATE_URL")
            or (
                os.environ.get("NUOYAN_TRANSLATION_BASE_URL", "")
                if (provider or os.environ.get("NUOYAN_TRANSLATION_PROVIDER", "")).lower() == "libretranslate"
                else ""
            )
        ).rstrip("/")
        self.libretranslate_api_key = (
            api_key
            or os.environ.get("NUOYAN_LIBRETRANSLATE_API_KEY")
            or os.environ.get("NUOYAN_TRANSLATION_API_KEY", "")
        )
        self.argos_from = os.environ.get("NUOYAN_ARGOS_FROM", "en")
        self.argos_to = os.environ.get("NUOYAN_ARGOS_TO", "zh")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.active_provider())

    def active_provider(self) -> str:
        provider = str(self.provider or "auto").lower()
        if provider == "auto":
            if self.argos_ready():
                return "argos"
            if self.libretranslate_ready():
                return "libretranslate"
            if self.openai_ready():
                return "openai"
            return ""
        if provider == "argos":
            return "argos" if self.argos_ready() else ""
        if provider == "libretranslate":
            return "libretranslate" if self.libretranslate_ready() else ""
        if provider in {"openai", "openai-compatible", "openai_compatible"}:
            return "openai" if self.openai_ready() else ""
        return ""

    def openai_ready(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    def libretranslate_ready(self) -> bool:
        return bool(self.libretranslate_url)

    def argos_installed(self) -> bool:
        return (
            importlib.util.find_spec("argostranslate") is not None
            and importlib.util.find_spec("argostranslate.translate") is not None
        )

    def argos_ready(self) -> bool:
        if not self.argos_installed():
            return False
        try:
            import argostranslate.translate

            for source_language in argostranslate.translate.get_installed_languages():
                if getattr(source_language, "code", "") != self.argos_from:
                    continue
                for target_language in argostranslate.translate.get_installed_languages():
                    if getattr(target_language, "code", "") == self.argos_to:
                        source_language.get_translation(target_language)
                        return True
        except Exception:
            return False
        return False

    def translate_text(self, text: str, *, context: str = "") -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if not is_mostly_english(raw):
            return raw
        active_provider = self.active_provider()
        if not active_provider:
            raise RuntimeError(
                "未配置可用的专业中文翻译引擎。推荐安装 Argos Translate 离线翻译包；"
                "或配置企业内网 LibreTranslate 服务；也可由管理员统一配置 OpenAI-compatible API。"
            )
        if active_provider == "argos":
            return self._translate_argos(raw)
        if active_provider == "libretranslate":
            return self._translate_libretranslate(raw)
        return self._translate_openai_compatible(raw, context=context)

    def _translate_argos(self, text: str) -> str:
        import argostranslate.translate

        return str(
            argostranslate.translate.translate(
                text,
                self.argos_from,
                self.argos_to,
            )
        ).strip()

    def _translate_libretranslate(self, text: str) -> str:
        payload: dict[str, Any] = {
            "q": text,
            "source": self.argos_from,
            "target": self.argos_to,
            "format": "text",
        }
        if self.libretranslate_api_key:
            payload["api_key"] = self.libretranslate_api_key
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.libretranslate_url}/translate", json=payload)
            response.raise_for_status()
        data = response.json()
        return str(data.get("translatedText") or "").strip()

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
    active_provider = engine.active_provider()
    configured = bool(active_provider)
    if configured and completed_rows:
        status = "ready_with_cache"
        message = "内置翻译命令已配置，且已有专业中文阅读缓存。"
    elif configured:
        status = "ready_no_cache"
        message = "内置翻译命令已配置，但当前任务尚未生成专业中文阅读缓存。"
    else:
        status = "not_configured"
        message = "内置翻译命令已安装，但尚未配置可用翻译引擎。推荐先安装 Argos Translate 离线翻译包，或接入企业内网 LibreTranslate 服务。"
    return {
        "status": status,
        "command_available": True,
        "provider": engine.provider,
        "active_provider": active_provider,
        "model": engine.model,
        "argos_installed": engine.argos_installed(),
        "argos_model_ready": engine.argos_ready(),
        "libretranslate_configured": engine.libretranslate_ready(),
        "openai_configured": engine.openai_ready(),
        "base_url_configured": bool(engine.base_url),
        "api_key_configured": bool(engine.api_key),
        "configured": configured,
        "cache_path": str(translation_cache_path(task_dir)),
        "cached_translation_count": len(completed_rows),
        "english_section_count": english_sections,
        "message_zh": message,
        "setup_zh": (
            "推荐方案：安装 argostranslate 并导入 en→zh 离线模型后直接运行 translate-materials。"
            "企业方案：由管理员部署 LibreTranslate，并设置 NUOYAN_LIBRETRANSLATE_URL。"
            "云端兜底：由管理员统一配置 NUOYAN_TRANSLATION_API_KEY / NUOYAN_TRANSLATION_BASE_URL，研发人员不需要个人账号。"
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
            status = "engine_not_ready"
            engine_name = engine.active_provider() or engine.provider
            error = "未生成完整中文翻译：当前环境尚未配置可用翻译引擎。"
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
                "未配置可用的专业中文翻译引擎。推荐安装 Argos Translate 离线翻译包；"
                "或接入企业内网 LibreTranslate 服务；也可由管理员统一配置 OpenAI-compatible API。"
            ),
            "setup_zh": translation_status(task_dir)["setup_zh"],
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
        title_text = " ".join(title.split())
        if title_text and is_mostly_english(title_text):
            digest = text_hash(title_text)
            field = "title"
            if not force and (material_id, field, digest) in existing:
                skipped_count += 1
            elif not limit or translated_count < limit:
                try:
                    translation_zh = engine.translate_text(title_text, context=f"{title_text} / Title")
                    append_jsonl(
                        translation_cache_path(task_dir),
                        {
                            "time": now_iso(),
                            "material_id": material_id,
                            "field": field,
                            "label": "Title",
                            "text_hash": digest,
                            "source_text": title_text,
                            "translation_zh": translation_zh,
                            "status": "completed",
                            "engine": engine.active_provider() or engine.provider,
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
            elif limit and translated_count >= limit:
                return {
                    "status": "partial",
                    "translated_count": translated_count,
                    "skipped_count": skipped_count,
                    "failed_count": failed_count,
                    "errors": errors,
                    "message_zh": f"已按 limit={limit} 生成部分完整中文翻译。",
                }
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
                        "engine": engine.active_provider() or engine.provider,
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
