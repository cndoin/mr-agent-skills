<div align="center">

# MR Agent

### From papers to testable hypotheses

An open-source agent skill for Mendelian randomization research.

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md)

![MR Agent — From papers to testable hypotheses](assets/mr-agent-cover.svg)

</div>

MR Agent wraps [MRAgent](https://github.com/xuwei1997/MRAgent) in a reviewable workflow: discover exposure–outcome candidates in PubMed, look up GWAS datasets, run TwoSampleMR through R, and inspect the resulting files and reports.

This project adds environment preflight, isolated run directories, structured command output, result summaries, and small tools for reviewing intermediate CSV files. The statistical methods remain in MRAgent and its R dependencies.

## What it does

| Mode | Use |
| --- | --- |
| `O` | Start with an outcome and find candidate exposures |
| `E` | Start with an exposure and find candidate outcomes |
| `OE` | Validate a specified exposure–outcome pair |

The recommended workflow pauses after literature discovery so you can review the candidate pairs before launching later steps.

![Literature, GWAS selection, MR analysis, and result review](assets/causal-workflow.svg)

## Requirements

- Python 3.11 or 3.12 is recommended and covered by CI. The preflight accepts Python 3.9–3.12 except 3.9.7; Python 3.9/3.10 are not in CI, and 3.13+ is currently blocked.
- R 4.3.4 or later, plus the R packages listed in [`references/en/environment.md`](references/en/environment.md).
- The upstream `mragent` package, an LLM backend, and an OpenGWAS JWT for a complete MR run.
- Windows, macOS, and Linux are supported for the helper tools; a full MR run also depends on the upstream R setup.

## Install the skill

The installer copies the skill into Claude Code, WorkBuddy, or CodeBuddy skill directories. It does not install Python, R, or MRAgent dependencies.

```bash
python install.py --target all
python install.py --list
```

For a manual installation, copy this repository into your agent's skill directory. See the localized [getting started guides](docs/README.md), starting with [English](docs/en/getting-started.md).

## Quick start

Set `MRAGENT_GWAS_TOKEN` (or `OPENGWAS_JWT`) and the LLM key required by your backend in the environment. Then check the environment and preview the parameters:

```bash
python scripts/preflight.py --no-network
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
```

Run discovery, inspect `Exposure_and_Outcome.csv`, and then continue:

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
# Review the generated candidate pairs before continuing.
python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9
python scripts/summarize_output.py ./mragent-runs/back_pain_O_*/output
```

Each actual run receives a fresh directory under `mragent-runs/`. A dry run only prints the planned configuration and does not create one.

## Included tools

- `scripts/preflight.py` — check Python, R, package, credential presence, and optional network availability.
- `scripts/run_mr.py` — launch MRAgent in an isolated directory and return structured JSON.
- `scripts/summarize_output.py` — summarize generated CSV and PDF outputs.
- `tools/mr_gwas.py` — search the OpenGWAS catalogue online or from a locally cached index.
- `tools/edit_csv.py` — review and edit intermediate analysis tables.
- `tools/export_results.py` — package result files while excluding logs and `test.R` by default.
- Additional helpers cover PubMed, synonyms, LLM calls, evaluation, benchmarking, and the upstream web demo.

## Safety and limitations

- MR estimates depend on instrument quality, study design, sample overlap, and data availability. This workflow does not prove causality or replace expert review, and it is not clinical advice.
- The runner checks for `mr_run.csv` instead of trusting the upstream process exit code, which can be zero even when no MR ran.
- Credentials should be supplied through environment variables. The upstream package writes the OpenGWAS JWT into a temporary `test.R`; the runner attempts to redact it and the ZIP exporter excludes that file.
- UMLS synonym expansion is **off by default**. Explicitly passing `--synonyms` makes upstream MRAgent use its embedded UMLS key; the upstream API currently does not accept a replacement key. The standalone synonym tool requires your own UMLS key.
- This repository does not include GWAS summary statistics or the 10 MB catalogue CSV. The catalogue is downloaded to a user cache when requested.

## Verify locally

```bash
python scripts/selftest.py --quick
python install.py --list
```

The self-test covers helper-script contracts and offline behavior. It does not run a full MR analysis or validate live OpenGWAS, PubMed, R, or LLM services.

## Languages

The project overview and getting-started guide are available in English, Simplified Chinese, Japanese, Spanish, and French. The detailed implementation references are being translated; an English environment guide is available at [`references/en/environment.md`](references/en/environment.md). The executable [`SKILL.md`](SKILL.md) remains in Chinese; it contains the instructions the agent follows.

## Citation and license

If you use MRAgent in research, cite the paper: Xu et al., *Briefings in Bioinformatics* (2025), [doi:10.1093/bib/bbaf140](https://doi.org/10.1093/bib/bbaf140). This skill is MIT licensed; upstream MRAgent is Apache-2.0. See [`NOTICE`](NOTICE) for third-party attribution and data notes.
