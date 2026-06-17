import hashlib
import shutil
from pathlib import Path

from .extractors.pdf import extract_pdf_text
from .extractors.text import extract_docx_text, extract_text_file
from .models import FailureType, Material
from .status import count_lines, now_iso, record_materials


SUPPORTED = {".pdf", ".txt", ".md", ".html", ".htm", ".doc", ".docx"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_material_type(path: Path) -> tuple[str, str, str]:
    name = path.name
    if any(term in name for term in ["标准", "GB", "YY", "DB"]):
        return "standard", "文件名包含标准相关词", "medium"
    if any(term in name for term in ["专利", "权利要求", "说明书"]):
        return "patent", "文件名包含专利相关词", "medium"
    if any(term in name for term in ["审评", "指导原则", "征求意见"]):
        return "regulatory", "文件名包含监管资料相关词", "medium"
    return "literature", "文件名未命中特定规则，默认按文献材料待确认", "low"


def iter_supported_files(source: Path) -> list[Path]:
    if not source.exists():
        raise FileNotFoundError(f"Local import path does not exist: {source}")
    if source.is_file():
        return [source] if source.suffix.lower() in SUPPORTED else []
    return [
        path
        for path in source.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED
    ]


def extract_for_file(file_path: Path) -> tuple[str, str, FailureType | None]:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        text, status = extract_pdf_text(file_path)
    elif suffix in {".txt", ".md", ".html", ".htm"}:
        text, status = extract_text_file(file_path), "parsed"
    elif suffix == ".docx":
        text, status = extract_docx_text(file_path)
    elif suffix == ".doc":
        text, status = "", "needs_manual_review"
    else:
        text, status = "", "unsupported"

    failure_type = None
    if status.startswith("parse_failed"):
        failure_type = FailureType.PARSE_FAILED
    elif status in {"needs_ocr", "needs_pdf_dependency", "needs_manual_review"}:
        failure_type = FailureType.NEEDS_MANUAL_REVIEW
    return text, status, failure_type


def import_local(task_id: str, task_dir: Path, source: Path) -> dict:
    files = iter_supported_files(source)
    materials: list[Material] = []
    next_index = count_lines(task_dir / "data" / "materials.jsonl") + 1
    for offset, file_path in enumerate(files):
        material_type, reason, confidence = infer_material_type(file_path)
        material_id = f"MAT-{next_index + offset:06d}"
        stored_name = f"{material_id}{file_path.suffix.lower()}"
        target = task_dir / "downloads" / "local_import" / stored_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)

        text, status, failure_type = extract_for_file(file_path)
        extracted_path = task_dir / "extracted_text" / "local_import" / f"{material_id}.txt"
        extracted_relative = ""
        if text:
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_text(text, encoding="utf-8")
            extracted_relative = str(extracted_path.relative_to(task_dir))

        material = Material(
            material_id=material_id,
            task_id=task_id,
            source_scenario="local_import",
            material_type=material_type,
            title=file_path.name,
            collection_time=now_iso(),
            adapter_id="local_import",
            adapter_version="0.1.0",
            raw_fields={
                "initial_type_reason_zh": reason,
                "initial_type_confidence": confidence,
                "user_confirmation_required": True,
                "original_suffix": file_path.suffix.lower(),
            },
            download_status="imported",
            extracted_text_status=status,
            extracted_text_path=extracted_relative,
            failure_type=failure_type,
            failure_reason=status if failure_type else "",
            collection_path={
                "source_file": str(file_path),
                "stored_file": str(target.relative_to(task_dir)),
            },
            possible_duplicate_keys=[sha256_file(file_path)],
        )
        materials.append(material)

    record_materials(task_dir, materials)
    return {
        "imported_count": len(materials),
        "materials": [material.model_dump(mode="json") for material in materials],
    }
