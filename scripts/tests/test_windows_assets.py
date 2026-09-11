import hashlib
import json
from pathlib import Path

from ivd_research.windows_assets import (
    load_asset_manifest,
    validate_asset_manifest,
    verify_asset_file,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
STANDARD_MANIFEST = REPO_ROOT / "packaging" / "windows" / "manifest.standard.json"
EXTRA_MANIFEST = REPO_ROOT / "packaging" / "windows" / "manifest.extra.json"


def test_standard_manifest_declares_current_required_runtime_assets():
    manifest = load_asset_manifest(STANDARD_MANIFEST)
    assets = {asset["id"]: asset for asset in manifest["assets"]}

    assert manifest["profile"] == "standard"
    assert {"python-wheelhouse", "playwright-chromium", "argos-en-zh-model"} <= set(assets)
    assert all(assets[asset_id]["required"] for asset_id in assets)
    assert "java-runtime" not in assets
    assert "node-runtime" not in assets
    assert validate_asset_manifest(manifest) == []


def test_extra_manifest_keeps_java_and_node_optional():
    manifest = load_asset_manifest(EXTRA_MANIFEST)
    assets = {asset["id"]: asset for asset in manifest["assets"]}

    assert manifest["profile"] == "extra"
    assert {"java-runtime", "node-runtime"} <= set(assets)
    assert all(not asset["required"] for asset in assets.values())
    assert validate_asset_manifest(manifest) == []


def test_manifest_rejects_unsafe_paths_hashes_and_missing_license():
    payload = {
        "schema_version": 1,
        "manifest_version": "2.3.0-test",
        "profile": "standard",
        "release_ready": True,
        "assets": [
            {
                "id": "bad",
                "version": "1",
                "relative_path": "../outside.zip",
                "size": 10,
                "sha256": "not-a-hash",
                "license": "",
                "required": True,
                "sources": [],
            }
        ],
    }

    errors = validate_asset_manifest(payload)

    assert any("relative_path" in error for error in errors)
    assert any("sha256" in error for error in errors)
    assert any("license" in error for error in errors)
    assert any("sources" in error for error in errors)


def test_template_manifest_allows_unbuilt_assets_but_not_release_validation():
    payload = {
        "schema_version": 1,
        "manifest_version": "2.3.0-template",
        "profile": "standard",
        "release_ready": False,
        "assets": [
            {
                "id": "wheelhouse",
                "version": "locked-by-build",
                "relative_path": "python/wheelhouse.zip",
                "size": 0,
                "sha256": "0" * 64,
                "license": "See THIRD_PARTY_LICENSES.txt in built bundle",
                "required": True,
                "sources": [{"type": "build", "url": "pip-download"}],
            }
        ],
    }

    assert validate_asset_manifest(payload) == []
    payload["release_ready"] = True
    errors = validate_asset_manifest(payload)
    assert any("release_ready" in error for error in errors)


def test_verify_asset_file_checks_size_and_sha256(tmp_path: Path):
    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"nuoyan-offline-asset")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()

    valid = verify_asset_file(asset, expected_size=asset.stat().st_size, expected_sha256=digest)
    invalid = verify_asset_file(asset, expected_size=1, expected_sha256="f" * 64)

    assert valid["ok"] is True
    assert valid["actual"]["sha256"] == digest
    assert invalid["ok"] is False
    assert {error["field"] for error in invalid["errors"]} == {"size", "sha256"}


def test_manifest_files_are_valid_json():
    for path in [STANDARD_MANIFEST, EXTRA_MANIFEST]:
        json.loads(path.read_text(encoding="utf-8"))
