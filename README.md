# 诺研_skill_IVD研发项目调研

`诺研_skill` is a Codex skill for IVD R&D project research. It helps an agent confirm search scope, collect regulatory, competitor, standards, patent, literature and external scientific database evidence, generate enhanced evidence cards, build an HTML research analysis report, export an Excel evidence review table, and preserve local knowledge assets.

Skill name policy: the skill name is fixed as `诺研_skill`. Future changes should iterate code or capability versions only; do not put version numbers in the skill name or primary title.

## Install

Clone this repository into a Codex skills directory, then restart Codex so the skill can be discovered.

```bash
mkdir -p ~/.codex/skills
git clone git@github.com:sunnysun1987/nuoyan-skill-v2.git ~/.codex/skills/nuoyan-skill-v2
```

For local CLI use, install the Python package in editable mode:

```bash
cd ~/.codex/skills/nuoyan-skill-v2
python3 -m pip install -e ".[dev]"
```

Optional capabilities:

```bash
python3 -m pip install -e ".[browser,pdf,ocr,dev]"
```

## Quick Check

Run a dependency and output-path check:

```bash
nuoyan doctor --json
```

Before formal public-source collection, run the network preflight:

```bash
nuoyan doctor --network --json
```

The network preflight separates Python DNS, Python HTTPS and system curl status for PubMed/NCBI and OpenAlex. DNS or proxy failures must be treated as collection failures, not as evidence absence.

## Network And Proxy

Enterprise networks, VPNs, proxies, DNS filtering and sandboxed agent runtimes can block PubMed/NCBI, PMC or OpenAlex. If `doctor --network` reports `gaierror`, `Could not resolve host`, `No DNS configuration available` or timeout errors, configure the host environment before rerunning collection.

Common proxy setup:

```bash
export HTTPS_PROXY=http://proxy.example.com:8080
export HTTP_PROXY=http://proxy.example.com:8080
export NO_PROXY=localhost,127.0.0.1
```

Recommended allowlist:

- `eutils.ncbi.nlm.nih.gov`
- `pubmed.ncbi.nlm.nih.gov`
- `pmc.ncbi.nlm.nih.gov`
- `api.openalex.org`
- `www.nmpa.gov.cn`
- `www.cmde.org.cn`
- `std.samr.gov.cn`

If public APIs remain blocked, use the skill's fallback path: record the true failure, collect from legal public pages or user-provided files, import findings with `import-finding`, and keep unresolved items in the Excel review and supplement task table.

## Workflow Contract

The first step is always search-scope confirmation. A formal research run must confirm product type, target analyte, disease or intended use, sample type, platform or methodology, target region, competitor scope, literature range, patent scope and report depth before collection.

Formal collection should cover the evidence map:

- regulatory and review guidance
- NMPA competitor registrations
- current standards
- patents
- Chinese literature
- PubMed, PMC and OpenAlex literature
- fallback or manually imported evidence when a source is restricted
- life-science-research plugin evidence when the topic involves biomarkers, proteins, genes, pathways, clinical studies, genetic evidence or public scientific databases

V2.1 adds a standard source-site baseline and lightweight local knowledge assets:

- `nuoyan source-sites --json` exports built-in source configuration.
- `nuoyan import-life-science-findings --task-id <task_id> --findings-json-file external_findings.json --json` imports plugin findings into the material pipeline.
- `nuoyan import-literature-table --task-id <task_id> --path literature.xlsx --json` imports local CSV/XLSX literature lists.
- `nuoyan build-knowledge --task-id <task_id> --json` generates metric facts, topic index, dedup index and a literature graph.

Professional Chinese reading support is built into this repository as CLI code, not as a separate Codex skill:

- `nuoyan translation-status --task-id <task_id> --json` checks whether the built-in translation command exists, whether an API key is configured, and how many cached translations are available.
- `nuoyan translate-materials --task-id <task_id> --json` generates cached Chinese translations for English abstract sections using an OpenAI-compatible translation API.
- Required configuration: set `NUOYAN_TRANSLATION_API_KEY` or `OPENAI_API_KEY`. Optional configuration: `NUOYAN_TRANSLATION_MODEL` and `NUOYAN_TRANSLATION_BASE_URL`.
- HTML reports read `data/translations.jsonl`; if no cache exists, they show the translation capability status instead of inventing a partial translation.

The final verification command reports whether the package is ready for business review:

```bash
nuoyan verify-package --task-id <task_id> --json
```

Key fields include `search_profile_ready`, `scenario_coverage_ready`, `fallback_ready`, `network_ready`, `v21_assets_ready`, `final_review_ready` and `business_ready`.

`business_ready=true` requires more than generated files. The package must have confirmed search scope, complete source coverage or documented fallback, V2.1 source-site and knowledge assets, reviewed evidence cards, and a valid standard delivery folder.

## Tests

Run deterministic tests without depending on live public networks:

```bash
python3 -m pytest
```

Live network checks should remain explicit and separate from normal CI:

```bash
nuoyan doctor --network --json
```

## Release Note

The formal skill name is `诺研_skill`; the formal display title is `诺研_skill_IVD研发项目调研`. The repository name can remain `nuoyan-skill-v2` for GitHub continuity, but user-facing skill naming should not include code version numbers.
