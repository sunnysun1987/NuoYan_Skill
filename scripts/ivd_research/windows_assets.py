from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
REQUIRED_ASSET_FIELDS = {
    "id",
    "version",
    "relative_path",
    "size",
    "sha256",
    "license",
    "required",
    "sources",
}


def load_asset_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(str(value or "").replace("\\", "/"))
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_asset_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    for field in ("manifest_version", "profile"):
        if not str(payload.get(field) or "").strip():
            errors.append(f"{field} is required")
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        return errors + ["assets must be a non-empty list"]

    release_ready = payload.get("release_ready") is True
    asset_ids: set[str] = set()
    for index, asset in enumerate(assets):
        prefix = f"assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = REQUIRED_ASSET_FIELDS - set(asset)
        for field in sorted(missing):
            errors.append(f"{prefix}.{field} is required")
        asset_id = str(asset.get("id") or "").strip()
        if not asset_id:
            errors.append(f"{prefix}.id is required")
        elif asset_id in asset_ids:
            errors.append(f"{prefix}.id must be unique: {asset_id}")
        asset_ids.add(asset_id)
        if not str(asset.get("version") or "").strip():
            errors.append(f"{prefix}.version is required")
        if not _safe_relative_path(str(asset.get("relative_path") or "")):
            errors.append(f"{prefix}.relative_path must stay inside the asset root")
        size = asset.get("size")
        if not isinstance(size, int) or size < 0:
            errors.append(f"{prefix}.size must be a non-negative integer")
        digest = str(asset.get("sha256") or "")
        if not SHA256_PATTERN.fullmatch(digest):
            errors.append(f"{prefix}.sha256 must be 64 hexadecimal characters")
        if not str(asset.get("license") or "").strip():
            errors.append(f"{prefix}.license is required")
        if not isinstance(asset.get("required"), bool):
            errors.append(f"{prefix}.required must be boolean")
        sources = asset.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{prefix}.sources must be a non-empty ordered list")
        else:
            for source_index, source in enumerate(sources):
                source_prefix = f"{prefix}.sources[{source_index}]"
                if not isinstance(source, dict):
                    errors.append(f"{source_prefix} must be an object")
                    continue
                if not str(source.get("type") or "").strip():
                    errors.append(f"{source_prefix}.type is required")
                if not str(source.get("url") or source.get("path") or "").strip():
                    errors.append(f"{source_prefix} requires url or path")
        if release_ready and (size == 0 or digest == "0" * 64):
            errors.append(
                f"{prefix} cannot be release_ready with an unbuilt size or sha256"
            )
    return errors


def verify_asset_file(
    path: Path,
    *,
    expected_size: int,
    expected_sha256: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "path": str(path),
        "expected": {"size": expected_size, "sha256": expected_sha256.lower()},
        "actual": {"size": None, "sha256": ""},
        "errors": [],
    }
    if not path.is_file():
        result["errors"].append({"field": "path", "message": "asset file not found"})
        return result

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_size = path.stat().st_size
    actual_sha256 = digest.hexdigest()
    result["actual"] = {"size": actual_size, "sha256": actual_sha256}
    if actual_size != expected_size:
        result["errors"].append(
            {"field": "size", "message": f"expected {expected_size}, got {actual_size}"}
        )
    if actual_sha256 != expected_sha256.lower():
        result["errors"].append(
            {"field": "sha256", "message": "asset checksum does not match manifest"}
        )
    result["ok"] = not result["errors"]
    return result


def inspect_asset_manifest(
    manifest_path: Path,
    *,
    asset_root: Path | None = None,
) -> dict[str, Any]:
    payload = load_asset_manifest(manifest_path)
    errors = validate_asset_manifest(payload)
    verification: list[dict[str, Any]] = []
    if asset_root is not None and not errors:
        root = asset_root.resolve()
        for asset in payload["assets"]:
            relative_path = Path(str(asset["relative_path"]))
            candidate = (root / relative_path).resolve()
            if root not in candidate.parents and candidate != root:
                verification.append(
                    {
                        "ok": False,
                        "asset_id": asset["id"],
                        "path": str(candidate),
                        "errors": [
                            {"field": "path", "message": "asset path escapes asset root"}
                        ],
                    }
                )
                continue
            checked = verify_asset_file(
                candidate,
                expected_size=asset["size"],
                expected_sha256=asset["sha256"],
            )
            checked["asset_id"] = asset["id"]
            verification.append(checked)
    return {
        "ok": not errors and all(item.get("ok") for item in verification),
        "manifest": str(manifest_path),
        "manifest_version": payload.get("manifest_version", ""),
        "profile": payload.get("profile", ""),
        "release_ready": payload.get("release_ready") is True,
        "errors": errors,
        "assets": verification,
    }
