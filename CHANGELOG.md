# Changelog

This project follows [Semantic Versioning](https://semver.org/) and the [Keep a Changelog](https://keepachangelog.com/) format.

## 1.3.2 — 2026-10-02

### Added

- Self-check group L (3 cases): **documented commands are now tested like code**.
  L1 commands must reference existing scripts; L2 every flag used in the docs must be
  accepted by the corresponding tool; L3 is a coverage guard that fails when too few
  commands are checked -- this prevents a vacuous test that can never fail.
  Case count 118 -> 122 (incl. J16).

### Fixed

- **`python scripts/preflight.py --json` in `SKILL.md` was an invalid command.**
  `preflight.py` has no `--json` flag; it always prints JSON. The bad example had been
  in the docs for a long time because examples were never executed. It is now pinned by
  L2; the remaining 74 documented commands all pass.

## 1.3.1 — 2026-10-01

### Added

- Add self-check cases J14 / J15 to pin down "the download request must carry a browser UA": J14 asserts the header offline, and J15 issues a real 1-byte range request to confirm the server actually accepts it -- an offline assertion alone cannot prove the server honours the header.
- Add self-check group K (6 cases) guarding multi-language documentation consistency: every README must mention SMR, every getting-started guide must carry the SMR / HEIDI section, every `smr.md` link must resolve to a real file, and the case count declared in the docs must equal the number actually executed. The trigger was concrete: the SMR section had been synced into English and Simplified Chinese only, while the Japanese, Spanish, and French overviews silently fell behind with no case able to detect it.

### Fixed

- **Fix `fetch-binary` being unable to download the official binary**: the download site's WAF rejects urllib's default UA (`Python-urllib/3.x`) with `HTTP 403 Forbidden`, while a browser UA returns `200` immediately. `download_binary()` previously called bare `urlopen(url)`, so `fetch-binary` could never succeed. Requests now go through `download_request()`, which sets the UA explicitly. Measured on the same URL in the same shell: default UA 403, browser UA 200 / 2171140 bytes.
- Split list items that had been glued onto the previous line in the getting-started guides.
- Correct the relative path of the `references/smr.md` link in `docs/zh-CN/getting-started.md`, which was missing `../../` and pointed at a location that does not exist.
- Correct the `fetch-binary --out ./smr-bin` example in all five getting-started guides: `fetch-binary` accepts no arguments (it always extracts into the global cache), so that command is rejected by argparse.

- Correct the relative path of the `references/smr.md` link in `docs/zh-CN/getting-started.md`, which was missing `../../` and pointed at a location that does not exist.

### Documentation

- Complete the SMR / HEIDI sections in the Japanese, Spanish, and French READMEs, which previously covered the workflow only.
- Add an SMR / HEIDI walkthrough (fetch the binary, preflight, both engines) to all five getting-started guides and index `references/smr.md` in `docs/README.md`.
- Sync the self-check case count (110 -> 118) and the skill version (1.3.0 -> 1.3.1).

## 1.3.0 — 2026-10-01

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

