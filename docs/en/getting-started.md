# Getting started

This guide runs a literature-discovery workflow first, lets you review its candidate pairs, and then continues the MR analysis.

## Requirements

- Python 3.11 or 3.12 is recommended and covered by CI. Preflight accepts Python 3.9–3.12 except 3.9.7; Python 3.9/3.10 are not in CI and 3.13+ is currently blocked.
- R 4.3.4 or later and the packages listed in [`../../references/en/environment.md`](../../references/en/environment.md).
- The upstream `mragent` package and a supported LLM backend.
- An OpenGWAS JWT in `MRAGENT_GWAS_TOKEN` or `OPENGWAS_JWT`.

The skill installer only copies the skill files; it does not install Python, R, or MRAgent dependencies.

## Install the skill

```bash
python install.py --target all
```

Select `--target claude`, `workbuddy`, `codebuddy`, `codex`, or `deepseek`. Codex installs to `$CODEX_HOME/skills/mr-agent` (default `~/.codex/skills/mr-agent`); DeepSeek Harness installs to `$DSH_HOME/skills/mr-agent` (default `~/.dsh/skills/mr-agent`). Use `python install.py --list` to validate metadata and print destinations without installing.

## Prepare your environment

Create a Python 3.11 or 3.12 environment, install `mragent==0.2.5`, install and configure R packages, and set credentials as environment variables. Follow [`../../references/en/environment.md`](../../references/en/environment.md) for platform-specific commands. Do not paste real credentials into shell commands, source files, or issue reports.

Run preflight before spending LLM or API quota:

```bash
python scripts/preflight.py --no-network
```

The report marks blocking requirements and never prints credential values.

## Run discovery, then review

Preview the selected mode and parameters:

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
```

Run the literature steps:

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
```

Inspect `Exposure_and_Outcome.csv` in the reported run directory. Edit the pairs if needed, then run the later steps:

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9
python scripts/summarize_output.py ./mragent-runs/back_pain_O_*/output
python tools/export_results.py ./mragent-runs/back_pain_O_*/output
```

Each actual invocation creates a new work directory. `--dry-run` does not create one. The runner captures logs and checks for `mr_run.csv` rather than assuming a zero process exit code means MR completed.

## Choose a mode

| Mode | Required input | Goal |
| --- | --- | --- |
| `O` | `--outcome` | Discover candidate exposures for an outcome |
| `E` | `--exposure` | Discover candidate outcomes for an exposure |
| `OE` | `--exposure` and `--outcome` | Validate one specified pair |

## SMR / HEIDI (optional)

`tools/mr_smr.py` runs SMR (Zhu et al. 2016 *Nat Genet*) and the HEIDI test on summary data, answering the question TwoSampleMR cannot: **which gene mediates this signal?**

```bash
# 1. Prepare the official smr binary (downloaded and verified into the global cache; or point SMR_BIN at one you already have)
python tools/mr_smr.py fetch-binary
# 2. Check the environment and your inputs
python tools/mr_smr.py preflight
# 3. Analyze: native has no dependencies, official drives the upstream binary
python tools/mr_smr.py analyze --engine native \
  --besd ./data/gene.besd --gwas ./data/trait.ma --out ./out/smr
python tools/mr_smr.py analyze --engine official \
  --besd ./data/gene.besd --gwas ./data/trait.ma --out ./out/smr
```

`--engine native` is a pure standard-library implementation whose SMR test matches the official binary **digit for digit**; the HEIDI `p_HEIDI` has a known difference in the decimals (the direction agrees, and both the output and the docs say so). Use the `official` sub-command to pass any upstream flag through verbatim — no official capability is left out. Data formats, the 48 mapped flags, and the measured calibration are in [`references/smr.md`](../../references/smr.md). This path needs no R, no `mragent`, and no OpenGWAS token — only Python and your cis-xQTL / GWAS summary data.

## Synonym expansion

UMLS expansion is off by default. The upstream MRAgent API embeds an UMLS key and does not currently expose a way for this runner to replace it. Explicit `--synonyms` enables that upstream behavior. The standalone `tools/mr_synonyms.py` instead requires your own `UMLS_API_KEY`.

## Interpret results carefully

MR results depend on instrument validity, study design, sample overlap, and data availability. Review the source datasets and diagnostics with an expert. The generated report is research evidence, not clinical advice or proof of causality.

## More documentation

- [`references/api.md`](../../references/api.md) — constructor and step details
- [`references/pitfalls.md`](../../references/pitfalls.md) — upstream failure modes
- [`references/en/environment.md`](../../references/en/environment.md) — full setup notes
- [`references/smr.md`](../../references/smr.md) — SMR / HEIDI: data formats and the two engines

- [`SECURITY.md`](../../SECURITY.md) — credential handling and known risks
