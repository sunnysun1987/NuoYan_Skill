# Nuoyan_skill_V2.0

Nuoyan_skill_V2.0 is a Codex skill for IVD product feasibility research. It helps an agent confirm search scope, collect regulatory, competitor, standards, patent and literature evidence, generate evidence cards, build an HTML feasibility report, and export an Excel evidence review table.

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

The final verification command reports whether the package is ready for business review:

```bash
nuoyan verify-package --task-id <task_id> --json
```

Key fields include `search_profile_ready`, `scenario_coverage_ready`, `fallback_ready`, `network_ready`, `final_review_ready` and `business_ready`.

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

The installed local skill name may be `Nuoyan_skill_V2.0` for backward compatibility with existing Codex installations. For a public repository or newly packaged skill, prefer the hyphen-case name `nuoyan-skill-v2`, which matches Codex skill validation rules for portable distribution.
