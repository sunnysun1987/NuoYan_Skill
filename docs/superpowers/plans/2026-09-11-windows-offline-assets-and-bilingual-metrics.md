# Windows Offline Assets and Bilingual Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 发布可离线、可回退、可校验的 Windows 标准环境安装机制，并让指标事实从数据层到 HTML、Excel 和 Markdown 证据卡统一提供中英双语速读信息。

**Architecture:** 使用 JSON manifest 描述可分发资产，PowerShell 安装器按本地、内网、公网顺序解析并校验资产，不在 Git 中提交大型二进制文件。指标事实通过稳定词典和已有翻译缓存生成双语字段，英文原文始终保留，翻译缺失时只标记状态、不伪造译文。

**Tech Stack:** PowerShell 5.1+、Python 3.11、Pydantic、Jinja2、openpyxl、pytest、Playwright、Argos Translate。

## Global Constraints

- 默认标准资产只包含当前真实需要的 Python wheels、Playwright Chromium、Argos Translate 和 English→Chinese 模型。
- Java/Node 仅作为可选扩展资产，不进入当前 `standard_ready` 门禁。
- 资产解析优先级固定为本地离线资产、IT 内网镜像、官方公网源；所有来源失败后停止并给出明确缺口。
- `-VerifyOnly` 不联网、不写文件、不安装组件。
- 英文原文始终保留；翻译引擎不可用时不得生成伪译文。
- 不提交大型运行时二进制、下载缓存、任务运行数据或用户已有未跟踪文件。
- 每个独立修改运行目标测试、Ruff、compileall 和 `git diff --check` 后单独中文提交。

---

### Task 1: Windows 资产 manifest 与校验器

**Files:**
- Create: `packaging/windows/manifest.standard.json`
- Create: `packaging/windows/manifest.extra.json`
- Create: `packaging/windows/sources.example.json`
- Create: `scripts/ivd_research/windows_assets.py`
- Modify: `scripts/ivd_research/cli.py`
- Test: `scripts/tests/test_windows_assets.py`

**Interfaces:**
- Produces: `load_asset_manifest(path: Path) -> dict[str, Any]`
- Produces: `validate_asset_manifest(payload: dict[str, Any]) -> list[str]`
- Produces: `verify_asset_file(path: Path, expected_size: int, expected_sha256: str) -> dict[str, Any]`
- Produces CLI: `nuoyan windows-assets --manifest <path> [--asset-root <path>] --json`

- [ ] **Step 1: Write failing manifest tests**

Test that the standard manifest declares Python wheels, Chromium and Argos en→zh model; the extra manifest declares optional Java/Node; every asset has `id`, `version`, `relative_path`, `size`, `sha256`, `license`, `required`, and ordered sources; unsafe paths and malformed hashes are rejected.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest -q scripts/tests/test_windows_assets.py`

Expected: collection/import failure because `ivd_research.windows_assets` and manifests do not exist.

- [ ] **Step 3: Implement manifest validation and file verification**

Use `Path.resolve()` containment checks, exact byte size, streaming SHA-256, and structured results containing `ok`, `asset_id`, `path`, `expected`, `actual`, and `errors`. Keep URLs as data; this module does not download or execute assets.

- [ ] **Step 4: Add read-only CLI inspection**

Expose manifest validation and optional local file verification through `windows-assets`. Exit nonzero only when `--strict` is supplied and validation fails.

- [ ] **Step 5: Verify GREEN**

Run: `python3 -m pytest -q scripts/tests/test_windows_assets.py scripts/tests/test_ci_release.py`

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add packaging/windows scripts/ivd_research/windows_assets.py scripts/ivd_research/cli.py scripts/tests/test_windows_assets.py
git commit -m "新增 Windows 离线资产清单与校验"
```

### Task 2: Windows 安装器本地优先与回退机制

**Files:**
- Create: `packaging/windows/install-windows.ps1`
- Create: `packaging/windows/build-assets.ps1`
- Modify: `install-windows.ps1`
- Modify: `scripts/ivd_research/translation.py`
- Modify: `scripts/ivd_research/doctor.py`
- Test: `scripts/tests/test_windows_installer.py`
- Test: `scripts/tests/test_translation.py`
- Test: `scripts/tests/test_doctor.py`

**Interfaces:**
- Installer parameters: `-AssetBundle`, `-AssetRoot`, `-SourcesConfig`, `-VerifyOnly`.
- Install state: `%USERPROFILE%\.codex\skills\nuoyan-skill-v2\.nuoyan\install-state.json`.
- Translation setup: `setup_translation_engine(..., model_path: Path | None = None)` imports a verified local `.argosmodel` before any network attempt.

- [ ] **Step 1: Extend installer and translation tests first**

Assert local asset lookup precedes mirror/public sources, `-VerifyOnly` blocks download and writes, local Argos model import uses its explicit path, install state records source/hash/version, optional Java/Node are not standard prerequisites, and legacy root script delegates to the packaged installer.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest -q scripts/tests/test_windows_installer.py scripts/tests/test_translation.py scripts/tests/test_doctor.py`

Expected: failures for missing parameters, local model import, install state, and packaged installer.

- [ ] **Step 3: Implement deterministic asset resolution**

PowerShell functions must return structured asset records and use this order: adjacent extracted cache/ZIP, configured mirror, public source. Validate size/hash before installation. Do not silently continue after checksum mismatch.

- [ ] **Step 4: Implement offline component installation**

Install Python packages using the local wheelhouse with `--no-index --find-links` when available, set `PLAYWRIGHT_BROWSERS_PATH` to the managed browser directory, import the verified Argos model path, and use online installation only for missing assets. Preserve current standard directory and isolated `.venv` rules.

- [ ] **Step 5: Persist and inspect install state**

Write state atomically after successful non-verify installation. Extend doctor output with manifest version, installed asset sources and checksum failures while retaining separate runtime, Chromium and Argos readiness checks.

- [ ] **Step 6: Add build script**

`build-assets.ps1` downloads/builds only declared assets into a staging directory, computes real sizes and SHA-256 values, writes a release manifest, and creates standard/extra ZIPs. It must refuse placeholder hashes in release mode.

- [ ] **Step 7: Verify GREEN**

Run: `python3 -m pytest -q scripts/tests/test_windows_installer.py scripts/tests/test_translation.py scripts/tests/test_doctor.py`

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add install-windows.ps1 packaging/windows scripts/ivd_research/translation.py scripts/ivd_research/doctor.py scripts/tests/test_windows_installer.py scripts/tests/test_translation.py scripts/tests/test_doctor.py
git commit -m "完善 Windows 离线安装与来源回退"
```

### Task 3: 指标事实双语数据、HTML、Excel 与证据卡

**Files:**
- Modify: `scripts/ivd_research/models.py`
- Modify: `scripts/ivd_research/knowledge/fact_extractor.py`
- Modify: `scripts/ivd_research/translation.py`
- Modify: `scripts/ivd_research/reports.py`
- Modify: `scripts/ivd_research/review_excel.py`
- Modify: `assets/templates/evidence-card.md`
- Modify: `assets/templates/standard-delivery-report.html`
- Modify: `scripts/ivd_research/assets/templates/evidence-card.md`
- Modify: `scripts/ivd_research/assets/templates/standard-delivery-report.html`
- Test: `scripts/tests/test_metric_fact_extractor.py`
- Test: `scripts/tests/test_reports_analysis.py`
- Test: `scripts/tests/test_package_verification.py`
- Test: `scripts/tests/test_translation.py`

**Interfaces:**
- `MetricFact` adds `metric_type_en`, `metric_type_zh`, `metric_explanation_zh`, `value_explanation_zh`, `excerpt_zh`, and `translation_status` with backward-compatible defaults.
- `enrich_metric_fact_translation(task_dir: Path, fact: dict[str, Any], cache: dict | None = None, capability: dict | None = None) -> dict[str, Any]` returns display/export fields without network calls.

- [ ] **Step 1: Write failing bilingual contract tests**

Cover stable mappings for AUC, sensitivity, specificity, LoD, cutoff, HR, OR, CI and sample size; unknown metrics preserve English; cached excerpt translation produces `completed`; missing engine produces `engine_not_ready`; HTML search contains both languages; Excel and Markdown expose the same fields.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest -q scripts/tests/test_metric_fact_extractor.py scripts/tests/test_reports_analysis.py scripts/tests/test_package_verification.py scripts/tests/test_translation.py`

Expected: failures for missing model fields, enrichment function and rendered bilingual columns.

- [ ] **Step 3: Add stable bilingual metric vocabulary**

Centralize canonical English label, Chinese label and Chinese explanation in the metric extraction/translation layer. Populate new fields when facts are created and preserve compatible parsing of existing JSONL rows.

- [ ] **Step 4: Enrich excerpts from cache only**

Use the existing `translations.jsonl` cache keyed by material, field and text hash. Add metric excerpt cache fields to `translate-materials`; report/export functions may only read the cache and capability status.

- [ ] **Step 5: Update HTML, Excel and Markdown**

HTML shows Chinese label plus English label, Chinese explanation, translated excerpt when available, expandable English original and a compact status label. Excel adds explicit bilingual columns. Evidence cards use the same order and always retain original excerpt.

- [ ] **Step 6: Keep template copies identical**

Apply equivalent template changes under both `assets/templates/` and `scripts/ivd_research/assets/templates/`; the existing package parity test must pass byte-for-byte.

- [ ] **Step 7: Verify GREEN**

Run: `python3 -m pytest -q scripts/tests/test_metric_fact_extractor.py scripts/tests/test_reports_analysis.py scripts/tests/test_package_verification.py scripts/tests/test_translation.py scripts/tests/test_packaging.py`

Expected: all selected tests pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/ivd_research assets/templates scripts/tests
git commit -m "增加指标事实中英双语速读"
```

### Task 4: Skill 说明、版本、项目状态与发布验证

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `docs/windows-standard-environment.md`
- Modify: `references/report-rules.md`
- Modify: `references/cli-contract.md`
- Modify: `docs/development-release-checklist.md`
- Modify: `pyproject.toml`
- Modify: `scripts/ivd_research/constants.py`
- Modify: `scripts/tests/test_windows_installer.py`
- Create: `audit/v2.3.0-release-validation.md`
- Modify: `PROJECT_STATUS.md`

**Interfaces:**
- Release version: `2.3.0`.
- Workflow version: `诺研_skill-code-v2.3.0-2026-09-11`.

- [ ] **Step 1: Write failing documentation/version assertions**

Update tests to require `2.3.0`, C-strategy installation language, explicit standard/extra asset boundaries, and bilingual metric delivery requirements before modifying documentation.

- [ ] **Step 2: Verify RED**

Run: `python3 -m pytest -q scripts/tests/test_windows_installer.py scripts/tests/test_ci_release.py`

Expected: failures because version and documentation still describe V2.2.2 online-first installation.

- [ ] **Step 3: Update Skill and operator documentation**

Document that agents use the packaged offline-first installer, run strict doctor before research, never ask business users to install translators manually, and generate bilingual metric facts before delivery. Keep conditional details in existing references instead of expanding the main Skill unnecessarily.

- [ ] **Step 4: Update versions and release record**

Set package/workflow versions to 2.3.0, add a release validation document with actual commands and results, and update `PROJECT_STATUS.md` with completed, verified and Windows-manual-acceptance boundaries.

- [ ] **Step 5: Run complete local verification**

Run:

```bash
python3 -m pytest -q
ruff check scripts/
python3 -m compileall -q scripts
git diff --check
```

Expected: zero test failures, Ruff success, compileall exit 0, diff check exit 0.

- [ ] **Step 6: Run artifact-level smoke verification**

Build the wheel, validate both manifests, render a representative report fixture through the existing report tests, and run local doctor without claiming Windows 10/11 acceptance from macOS.

- [ ] **Step 7: Commit**

```bash
git add SKILL.md README.md docs references pyproject.toml scripts/ivd_research/constants.py scripts/tests/test_windows_installer.py audit PROJECT_STATUS.md
git commit -m "发布诺研 Skill 2.3.0"
```

## Completion Boundary

Local completion requires all deterministic tests and packaging checks to pass, all planned commits to exist, and the worktree to contain only the user's pre-existing untracked files. Windows offline installation remains a separate manual acceptance item until tested on clean Windows 10/11 hosts with the generated asset ZIPs.
