from pathlib import Path
import tomllib

from ivd_research.constants import WORKFLOW_VERSION


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "install-windows.ps1"
PACKAGED_INSTALLER = REPO_ROOT / "packaging" / "windows" / "install-windows.ps1"
ASSET_BUILDER = REPO_ROOT / "packaging" / "windows" / "build-assets.ps1"
OFFLINE_LAUNCHER = REPO_ROOT / "packaging" / "windows" / "install-offline.cmd"
OFFLINE_README = REPO_ROOT / "packaging" / "windows" / "README_FIRST.md"
VALIDATION_PROMPT = REPO_ROOT / "docs" / "windows-installation-validation-prompt.md"


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
    assert "CC BY 4.0" in script
    assert "Jörg Tiedemann" in script
    assert "Santhosh Thottingal" in script
    assert "OPUS-MT" in script


def test_windows_asset_builder_supports_python_executable_and_bundles_build_tools():
    script = ASSET_BUILDER.read_text(encoding="utf-8")

    assert "function Invoke-BuildPython" in script
    assert "Get-Command $PythonExe" in script
    assert 'eq "py.exe"' in script
    assert '"setuptools>=68"' in script
    assert '"wheel"' in script
    assert '"pip"' in script
    assert "& $PythonExe -3.13" not in script


def test_offline_install_bootstraps_build_tools_before_editable_install():
    script = PACKAGED_INSTALLER.read_text(encoding="utf-8")

    build_tool_install = script.index('"setuptools>=68", "wheel"')
    editable_install = script.index('"--editable"')
    assert build_tool_install < editable_install


def test_release_bundle_has_double_click_launcher_and_user_instructions():
    launcher = OFFLINE_LAUNCHER.read_text(encoding="utf-8")
    guide = OFFLINE_README.read_text(encoding="utf-8")

    assert "install-windows.ps1" in launcher
    assert "nuoyan-windows-standard-assets-2.3.0.zip" in launcher
    assert "ExecutionPolicy Bypass" in launcher
    assert "双击" in guide
    assert "INSTALL_NUOYAN.cmd" in guide
    assert "standard_ready=true" in guide


def test_windows_validation_prompt_targets_the_github_release_bundle():
    prompt = VALIDATION_PROMPT.read_text(encoding="utf-8")

    assert "nuoyan-windows-offline-installer-2.3.0.zip" in prompt
    assert "INSTALL_NUOYAN.cmd" in prompt
    assert "nuoyan-skill-v2 源码目录" in prompt
    assert "nuoyan-skill-v2-2.3.0 源码目录" not in prompt


def test_windows_runtime_is_documented_for_agent_not_business_user():
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "windows-standard-environment.md").read_text(
        encoding="utf-8"
    )

    assert ".venv\\Scripts\\nuoyan.exe" in skill
    assert "业务同事" in guide and "不需要输入命令" in guide
    assert "doctor --profile standard --network --strict" in guide


def test_windows_users_are_directed_to_the_github_offline_installer():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "windows-standard-environment.md").read_text(
        encoding="utf-8"
    )

    release_url = "https://github.com/sunnysun1987/NuoYan_Skill/releases/latest"
    assert release_url in readme
    assert release_url in guide
    assert "nuoyan-windows-offline-installer-2.3.0.zip" in readme
    assert "nuoyan-windows-offline-installer-2.3.0.zip" in guide
    assert "INSTALL_NUOYAN.cmd" in readme
    assert "INSTALL_NUOYAN.cmd" in guide
    assert "终端用户不需要从 GitHub 下载" not in guide


def test_windows_environment_release_has_distinct_version():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    guide = (REPO_ROOT / "docs" / "windows-standard-environment.md").read_text(
        encoding="utf-8"
    )

    assert project["project"]["version"] == "2.3.0"
    assert "v2.3.0" in WORKFLOW_VERSION
    assert "V2.3.0" in readme
    assert "本地离线资产" in skill
    assert "指标事实" in skill and "中英文" in skill
    assert "标准离线资产包" in guide
    assert "Java/Node" in guide and "可选" in guide
    assert "windows-assets" in guide
