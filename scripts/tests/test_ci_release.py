from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_ci_enforces_release_and_runtime_health_gates():
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert '      - "v*"' in workflow
    assert "run: nuoyan doctor --strict --json" in workflow
    assert "run: python -m compileall -q scripts" in workflow
    assert "run: git diff --check" in workflow


def test_release_workflow_builds_and_publishes_windows_downloads():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "contents: write" in workflow
    assert "windows-latest" in workflow
    assert "codex/v2.3.0-release" in workflow
    assert 'python-version: "3.13"' in workflow
    assert "name: Run tests" in workflow
    assert "name: Run Ruff" in workflow
    assert "name: Compile Python sources" in workflow
    assert "name: Check patch formatting" in workflow
    assert "setuptools>=68" in workflow
    assert "wheel" in workflow
    assert "pytest-results.xml" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "::error title=Windows pytest failed::" in workflow
    assert "build-assets.ps1" in workflow
    assert "nuoyan-windows-offline-installer-$Version.zip" in workflow
    assert "WINDOWS_VALIDATION_PROMPT.md" in workflow
    assert "SHA256SUMS.txt" in workflow
    assert "gh release upload" in workflow
    assert "--clobber" in workflow
    assert "if: github.ref_type == 'tag'" in workflow


def test_release_workflow_rejects_a_tag_that_does_not_match_package_version():
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "GITHUB_REF_NAME" in workflow
    assert '"v$Version"' in workflow
    assert "does not match package version" in workflow
