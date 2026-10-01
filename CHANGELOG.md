# Changelog

This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/) format.

## Unreleased

### Fixed

- Reject invalid or repeated step numbers; keep dry runs from creating run directories; allocate a fresh directory for each real run.
- Exclude `opengwas.csv` from installer copies and correctly handle relative download paths.
- Remove the copied upstream UMLS key from the standalone synonym tool and require the user's own key.
- Disable UMLS synonym expansion by default in the full workflow and warn when it is explicitly enabled.
- Expand credential scanning and regression coverage.
- Enforce the upstream Python version exclusion for 3.9.7 in preflight.

### Documentation

- Add English as the primary README and provide localized overviews and getting-started guides in Simplified Chinese, Japanese, Spanish, and French.
- Provide an English security policy and contributing guide.

## 1.0.0 — 2026-10-01

Initial release of the skill wrapper and helper toolkit. See the [Simplified Chinese changelog](CHANGELOG.zh-CN.md) for the detailed implementation history and source-level findings.
