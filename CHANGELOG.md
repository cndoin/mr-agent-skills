# Changelog

This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/) format.

## Unreleased

### Added

- Add `tools/mr_smr.py`, a dual-engine SMR / HEIDI toolkit. It drives the official `smr` binary (MIT, Yang lab) with all 48 commonly used flags mapped to their official names plus a lossless `official` pass-through, and it ships a dependency-free native engine whose SMR test matches the official implementation to about six significant digits.
- Add `references/smr.md` covering input formats, both engines, measured calibration against the official binary, the full flag mapping table, and the known pitfalls.
- Add `tests/gen_smr_fixture.py`, a deterministic, dependency-free generator for the SMR test dataset, plus self-check group J (13 cases) guarding flag forwarding, failure detection and numeric calibration (97 -> 110).
- Add native installer destinations for OpenAI Codex and DeepSeek Harness, including `CODEX_HOME` and `DSH_HOME` overrides.
- Shorten the bilingual skill description for broader compatibility with agent skill catalogs.
- Document the five supported agents across English, Chinese, Japanese, Spanish, and French getting-started guides.

### Fixed

- Reject invalid or repeated step numbers; keep dry runs from creating run directories; allocate a fresh directory for each real run.
- Exclude `opengwas.csv` from installer copies and correctly handle relative download paths.
- Remove the copied upstream UMLS key from the standalone synonym tool and require the user's own key.
- Disable UMLS synonym expansion by default in the full workflow and warn when it is explicitly enabled.
- Expand credential scanning and regression coverage.
- Enforce the upstream Python version exclusion for 3.9.7 in preflight.
- Keep installer backup directory names unique when several targets are installed within the same second, which previously aborted the run with `FileExistsError`; add self-check case H5 (96 -> 97).
- Detect official `smr` failures that still return exit code 0 (the error is written only to the log) and verify the BESD files were actually produced.
- Run `make-besd` from the `.flist` directory, because the official binary resolves relative ESD paths against the current working directory; without this, any call from another directory produced a silent false success.
- Broaden the E5 connectivity assertion to accept the reason in either `error` or `hint`, so the case no longer fails on machines that route localhost through a proxy.

### Documentation

- Add English as the primary README and provide localized overviews and getting-started guides in Simplified Chinese, Japanese, Spanish, and French.
- Provide an English security policy and contributing guide.
- Record that SMR / HEIDI is a deliberate capability extension beyond upstream. Upstream MRAgent genuinely has no SMR support (evidence retained in `references/upstream-diff.md` chapter 9), so this is documented as an added feature rather than parity work.
- Sync the self-check case count (97 -> 110) and the skill version (1.2.0 -> 1.3.0) across the docs.

## 1.0.0 — 2026-10-01

Initial release of the skill wrapper and helper toolkit. See the [Simplified Chinese changelog](CHANGELOG.zh-CN.md) for the detailed implementation history and source-level findings.

## [1.2.0] - 2026-10-01

### Added
- `tools/mr_prompt.py`：上游提示词库，含 `template_text.py` 的 10 个主模板与
  `step_9_test_prompt.py` 的 12 个 step9 消融变体（6 变体 x 2 模型）。
  支持 `--list` / `--show` / `--render` / `--diff-mragent`；提示词已 vendor 到
  `tools/prompts.json`，自检 I2 用 AST 断言与上游源码逐字一致（10/10）。
- `key.py.example`：上游 3 个实验脚本 `from key import ...` 依赖的凭据模板。
  上游仓库没有 `key.py`，也没有 `.gitignore` 去排除它，所以那些脚本 clone
  下来必然 `ModuleNotFoundError: No module named 'key'`。
- 自检新增分组 I（上游能力对齐）与用例 I10（文本文件行尾必须 LF），
  用例数 81 -> 96。

### Changed
- `tools/mr_pubmed.py` 改为**原生 NCBI E-utilities 实现**，不再依赖 mragent。
  新增 `--first-abstract-only` / `--strict-shape` 还原上游输出形状，
  新增 `--email` / `NCBI_EMAIL`，不再冒用上游硬编码的作者邮箱。
- `tools/mr_gwas.py` 的 online 模式不再复刻上游已失效的 HTML 爬虫，改走
  OpenGWAS 官方鉴权 API（`api.opengwas.io/api/gwasinfo`），新增 `--refresh`。
- `tools/mr_synonyms.py`、`tools/mr_llm.py` 改为原生实现，不再依赖 mragent。
- `scripts/summarize_output.py` 改用 argparse，新增 `--limit` / `--strict`。
- `.gitignore` 增加 `key.py`（保留 `key.py.example`）。
- 全仓库 14 个文本文件由 CRLF 归一为 LF。

### Fixed
- `summarize_output.py --help` 原来被当成目录路径，返回"目录不存在"的 JSON
  且 exit 1；现与其他入口一致：输 usage、exit 0。
- `mr_pubmed.py` 把上游传给 Entrez 的 `'most recent'` 映射为合法的 `pub_date`
  —— 上游那个取值 Entrez 根本不认，会被静默忽略。
- 比对文档里引用的上游泄露凭据做打码处理（自检 H1 发现）。

