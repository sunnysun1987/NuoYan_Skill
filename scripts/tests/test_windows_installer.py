from pathlib import Path
import tomllib

from ivd_research.constants import WORKFLOW_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "install-windows.ps1"
PACKAGED_INSTALLER = REPO_ROOT / "packaging" / "windows" / "install-windows.ps1"
ASSET_BUILDER = REPO_ROOT / "packaging" / "windows" / "build-assets.ps1"


def test_windows_installer_uses_isolated_complete_runtime():
    wrapper = INSTALLER.read_text(encoding="utf-8")
    script = PACKAGED_INSTALLER.read_text(encoding="utf-8")

    assert "packaging\\windows\\install-windows.ps1" in wrapper
    assert ".codex\\skills\\nuoyan-skill-v2" in script
    assert ".venv\\Scripts\\python.exe" in script
    assert "[browser,pdf,translation]" in script
    assert "PLAYWRIGHT_BROWSERS_PATH" in script
    assert "--model-path" in script
    assert "--profile standard --network --strict --json" in script
    assert "pip install --user" not in script


def test_windows_installer_checks_prerequisites_and_supports_verify_only():
    script = PACKAGED_INSTALLER.read_text(encoding="utf-8")

    assert "Resolve-NuoyanAsset" in script
    assert "AssetBundle" in script
    assert "AssetRoot" in script
    assert "SourcesConfig" in script
    assert "[switch]$VerifyOnly" in script
    assert "Life Science Research" in script


def test_windows_installer_prefers_local_then_mirror_then_public_and_records_state():
    script = PACKAGED_INSTALLER.read_text(encoding="utf-8")

    local_index = script.index('"local"')
    mirror_index = script.index('"mirror"')
    public_index = script.index('"public"')
    assert local_index < mirror_index < public_index
    assert "install-state.json" in script
    assert "manifest_version" in script
    assert "sha256" in script
    assert "source_type" in script
    assert "allow_public_fallback" in script
    assert "PSObject.Properties" in script
    assert 'source_type = "public_package_index"' in script


def test_verify_only_is_read_only_and_extra_runtimes_are_optional():
    script = PACKAGED_INSTALLER.read_text(encoding="utf-8")
    standard_manifest = (
        REPO_ROOT / "packaging" / "windows" / "manifest.standard.json"
    ).read_text(encoding="utf-8")

    assert "if ($VerifyOnly)" in script
    assert "VerifyOnly does not download or modify files" in script
    assert "java-runtime" not in standard_manifest
    assert "node-runtime" not in standard_manifest


def test_windows_asset_builder_writes_release_hashes_and_refuses_placeholders():
    script = ASSET_BUILDER.read_text(encoding="utf-8")

    assert "Get-FileHash" in script
    assert "Compress-Archive" in script
    assert "THIRD_PARTY_LICENSES.txt" in script
    assert "release_ready" in script
    assert "placeholder" in script.lower()


def test_windows_runtime_is_documented_for_agent_not_business_user():
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "windows-standard-environment.md").read_text(
        encoding="utf-8"
    )

    assert ".venv\\Scripts\\nuoyan.exe" in skill
    assert "业务同事不执行命令行" in guide
    assert "doctor --profile standard --network --strict" in guide


def test_windows_environment_release_has_distinct_version():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == "2.2.2"
    assert "v2.2.2" in WORKFLOW_VERSION
    assert "V2.2.2" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")
