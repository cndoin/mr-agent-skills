# Contributing

Thanks for helping improve MR Agent. This repository wraps upstream MRAgent as an agent skill and a set of review tools; statistical methods are provided by MRAgent and its R dependencies.

## Development

Python 3.11 or 3.12 is recommended and covered by CI. The helper tools and quick self-test can be developed without installing the full MRAgent or R stack.

```bash
python scripts/selftest.py --quick
python install.py --list
```

Before opening a pull request:

- Run the quick self-test and report any checks you could not run.
- Do not add API keys, JWTs, private data, or generated run output.
- Do not commit `opengwas.csv`; the installer downloads it into a user cache.
- Verify documented commands against the current code.

## Reliability and Output Contracts

The runner must not report success merely because the upstream process returned exit code zero. Upstream can exit with code zero without producing an MR result; check for `mr_run.csv`. Keep stdout machine-readable JSON for helper scripts, including error paths, and send human-readable diagnostics to stderr. Never print credential values.

## Documentation and Commits

Facts in `references/` should be verified against upstream source or a reproducible run. Mark uncertain behavior as unverified. Use a Conventional Commit subject such as `fix:`, `feat:`, `docs:`, or `test:`. English is the default for new repository-wide documentation; localized guides are welcome.
