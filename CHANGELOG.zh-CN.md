# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)，
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [未发布]

### 新增

- 安装器支持 OpenAI Codex 与 DeepSeek Harness，并可通过 `CODEX_HOME` / `DSH_HOME` 自定义技能根目录。
- 精简中英双语技能描述，提升不同 Agent 技能目录的兼容性。
- 更新英文、中文、日文、西班牙文、法文的安装指南。

### 修复

- 拒绝 `run_mr.py` 中无效或重复的 step 编号，dry-run 不再创建运行目录，
  每次真实运行独占新目录，避免复用旧 `mr_run.csv` 造成假成功。
- 安装器复制时排除 `opengwas.csv`；直接下载到当前目录时正确处理目标路径。
- 移除独立同义词工具里误复制的上游 UMLS key，改为必须提供用户自己的 key。
- 完整流程默认关闭 UMLS 同义词扩展，并在用户显式开启时提示上游 key 限制。
- 扩展自检的凭据扫描并增加对应回归用例。
- 预检遵守上游明确排除 Python 3.9.7 的版本约束。

### 文档

- 明确记录 **SMR / HEIDI 不在能力范围内**：上游 MRAgent 本身没有该功能，
  本技能与之严格对齐，避免被误认为遗漏。见 `references/upstream-diff.md` 第九章与 `SKILL.md` 第 11 条。

## [1.1.0] — 2026-10-01

**目标：能同时被 Claude Code 与 WorkBuddy 加载，并满足开源发布要求。**

### 新增

- **`install.py`** —— 一键装到 `~/.claude/skills`、`~/.workbuddy/skills`、
  `~/.codebuddy/skills`。装完自动校验 frontmatter、下载离线清单、跑冒烟。
  零第三方依赖，任何 Python 3.8+ 都能跑安装。
- **`scripts/selftest.py`** —— 把此前散落在临时目录的三份测试合并进仓库，
  74 条用例一条命令跑完，支持 `--quick` / `--json`。CI 可直接接退出码。
- **`tools/mr_bench.py`** —— 复现上游 `step_2_test` / `step_5_test` 的
  准确率与 PRF 评测。
- `--mode auto` 智能模式推断（上游 Web demo 有而 CLI 没有的能力）。
- `--mr-quality-evaluation-key-item` 参数（上游 demo 用到，此前遗漏）。

### 修复

- **stdout 被污染（严重）**：MRAgent 与 R 会往 stdout 狂写输出（实测 90+ 行），
  导致调用方 JSON 解析失败。改用 `os.dup2` 做**文件描述符级**重定向 ——
  只重定向 `sys.stdout` 抓不到 R 的输出，因为 R 走的是 fd 层。
- **`--tag` 路径穿越**：`../../evil` 现在被消毒成 `_______evil`。
- **argparse 缺参不返回 JSON**：8 个工具 + `run_mr.py` 统一走
  `parse_args_or_fail()`，错误路径也返回结构化 JSON（exit 2）。
- **`SKILL.md` 里的参数被写成全角破折号**（`——keyword`），复制出去根本执行不了。
  共 19 处，已全部修正。

### 安全

- **工作目录凭据脱敏**：上游 MRAgent 会把明文 JWT 写进 CWD 的 `test.R`
  （`Sys.setenv(OPENGWAS_JWT="<JWT>")`）。`run_mr.py` 现在在任务收尾时把
  `run.log` 与 `test.R` 里的真实凭据替换成 `***REDACTED***`，
  并在返回 JSON 的 `redacted` 字段列出被改写的文件。已实测验证。
- `export_results.py` 打包时排除 `test.R` / `*.log`，新增用例 `D1b` 守住这条。
- 不再在文档中引用上游硬编码的 UMLS key 片段。

### 开源合规

- `LICENSE`（MIT）、`NOTICE`（上游 MRAgent / OpenGWAS / R 包归属）、
  `CONTRIBUTING.md`、`SECURITY.md`、`.gitignore`、`.gitattributes`。
- **`opengwas.csv`（10.3 MB 第三方数据）不再随仓库分发**。改由 `install.py`
  下载到 `~/.cache/mr-agent/`，多个安装位置共用一份。仓库因此干净，
  也不再涉及再分发上游数据文件的问题。

### 变更

- 技能目录名保持 `mr-agent`（不能叫 `mragent`）—— 与 Python 包同名会让
  该目录下的 `import mragent` 解析到技能目录本身。
- **`.github/workflows/ci.yml`**：3 OS × Python 3.11/3.12 矩阵。
  **刻意不装 mragent** —— 自检验证的是脚本契约与降级行为，装上反而会让
  E 组用例失败。`permissions: contents: read` 最小权限，`fail-fast: false`。
- **`.editorconfig`**：配 `.gitattributes` 一起锁 LF；`Makefile` 用 tab、
  Markdown 保留行尾硬换行。
- `install.py --list` 现在会校验 frontmatter 并以退出码表达结果 ——
  只列路径不校验的话，它在 CI 里就是个"永不失败的检查"。
- 覆盖已有安装时自动备份到 `~/.cache/mr-agent/backups/`。
  **备份不能放在 `skills/` 同级**：`mr-agent.bak-<ts>/` 里也有 SKILL.md，
  会被 Agent 当成第二个同名技能一起加载。只保留最近 3 份。

### 修复（第二轮追加）

- **`LICENSE` 恢复纯 MIT**。初版在 MIT 正文后附了一段第三方许可说明 ——
  "MIT + 附加条款"在 OSI 意义上就不再是 MIT 了。第三方归属全部移到 `NOTICE`。
- `mr_gwas.py --fetch` 默认下载到全局缓存而非当前目录。下到 CWD 会把
  10 MB 第三方数据塞回技能目录，正是 `.gitignore` 要排除的东西。
- `SKILL.md` 里用例数写着 64，实际 74 —— 文档数字漂移，已核对齐。
- `README.md` 关于"技能目录里已内置 opengwas.csv"的描述已失效，改为说明
  全局缓存机制。

## [1.0.0] — 2026-10-01

首个版本。基于 PyPI `mragent==0.2.5` 源码实测（而非 README 转述）构建：

- `SKILL.md`：8 条硬约束、两种模式、分步干预节奏、失败协议表。
- `references/`：`api.md` / `environment.md` / `pitfalls.md` / `upstream-diff.md`。
- `scripts/`：`preflight.py` / `run_mr.py` / `summarize_output.py`。
- `tools/`：`mr_pubmed` / `mr_gwas` / `mr_synonyms` / `mr_llm` / `mr_eval` /
  `export_results` / `edit_csv` / `serve_web` + 共享契约层 `_common.py`。

关键事实修正（README 是错的，源码为准）：中间产物是 `Outcome_SNP.csv` 与
`mr_run.csv`；step3 在全部已做过 MR 时 `sys.exit(0)`（退出码 0 但一个 MR 没跑）；
调 R 用的是 `R` 而不是 `Rscript`。
