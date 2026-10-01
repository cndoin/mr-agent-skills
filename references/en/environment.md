# Environment Setup

MR Agent coordinates Python and R. A complete Mendelian randomization run requires both runtimes and external credentials; the helper tools can be used independently.

## Python

Use Python 3.11 or 3.12 (the CI-tested versions). The preflight accepts Python 3.9–3.12 except 3.9.7; Python 3.13 and later are currently blocked by the upstream dependency constraints.

### Windows

```powershell
py -3.12 -m venv C:\venvs\mragent
C:\venvs\mragent\Scripts\python.exe -m pip install --upgrade pip
C:\venvs\mragent\Scripts\python.exe -m pip install mragent==0.2.5
```

### macOS / Linux

```bash
python3.12 -m venv ~/venvs/mragent
source ~/venvs/mragent/bin/activate
python -m pip install --upgrade pip
python -m pip install mragent==0.2.5
```

Check the installed package:

```bash
python -c "from mragent import MRAgent, MRAgentOE; print('mragent OK')"
python -c "import numpy, pandas; print(numpy.__version__, pandas.__version__)"
```

## R

Install R 4.3.4 or later and make sure the executable is named `R` and is on `PATH`. Upstream invokes `R --slave ... -f test.R`.

Install the required packages:

```r
install.packages("TwoSampleMR", repos = c("https://mrcieu.r-universe.dev", "https://cloud.r-project.org"))
install.packages(c("ieugwasr", "dplyr", "vcfR", "jsonlite"))
```

`MRlap` is optional and is needed only when the `mrlap` option is enabled. Consult the [full Chinese environment guide](../environment.md) for its extra data files and platform notes.

Verify package availability:

```bash
R --slave -e 'for (p in c("TwoSampleMR","ieugwasr","dplyr","vcfR","jsonlite")) cat(p, requireNamespace(p, quietly=TRUE), "\n")'
```

## Credentials

Create an OpenGWAS JWT at [api.opengwas.io](https://api.opengwas.io/) and provide it as `MRAGENT_GWAS_TOKEN` (or `OPENGWAS_JWT`). Configure the LLM credential required by your selected backend, such as `MRAGENT_AI_KEY` or `OPENAI_API_KEY`.

Use your operating system's environment-variable settings or a local, untracked environment file. Do not put credentials in source code, shell history, screenshots, or public issues. Run `python scripts/preflight.py --no-network` to check local prerequisites without making network requests.

## Scope

This setup guide does not install MR Agent itself or configure an LLM backend. The root README has installation and runner examples. A full run also needs valid credentials and network access to the selected services.
