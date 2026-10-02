# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)，
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## 1.3.2 — 2026-10-02

### 新增

- 自检新增 **L 组 3 条用例**：**把文档里的命令也当代码测**。
  L1 命令引用的脚本必须存在；L2 命令用到的 flag 必须被对应工具接受；
  L3 是覆盖面守卫 —— 校验条数低于阈值即判失败，防止提取器失效导致用例「空过」
  （一条永远不会失败的测试等于没有测试）。用例数 118 → 122（含 J16）。

### 修复

- **`SKILL.md` 里的 `python scripts/preflight.py --json` 是无效命令**。
  `preflight.py` 根本没有 `--json`，它默认就输出 JSON。这条错误示例存在了很久，
  根因是**文档示例从未被执行过** —— 现在由 L2 钉住，其余 74 条文档命令经校验均合法。

## 1.3.1 — 2026-10-01

### 新增

- 自检新增 **J14 / J15 两条用例**，把「下载请求必须带浏览器 UA」钉死：J14 离线断言请求头，J15 真发一个 1 字节 Range 请求确认服务端真的放行 —— 只用离线断言证明不了服务端认这个头。
- 自检新增 **K 组 6 条用例**，守卫多语言文档一致性：五份 README 都必须提及 SMR、
  五份 getting-started 都必须有 SMR / HEIDI 章节、所有 `smr.md` 链接都必须解析得到
  真实文件，且文档里声明的用例数必须等于实际执行的用例数。加这一组的原因很具体 ——
  SMR 段落曾经只同步了英文和简体中文，日 / 西 / 法三份概览静默掉队，
  而当时没有任何用例看得出来。

### 修复

- **修复 `fetch-binary` 无法下载官方二进制**：官方下载站的 WAF 会拒绝 urllib 的默认
  UA（`Python-urllib/3.x`）并返回 `HTTP 403 Forbidden`，换浏览器 UA 立刻 `200`。
  原先 `download_binary()` 用裸 `urlopen(url)`，因此 `fetch-binary` 必然失败。
  现在统一走 `download_request()` 显式携带 UA。实测同一 URL 同一 shell：
  默认 UA 403，浏览器 UA 200 / 2171140 字节。
- 修正 getting-started 指南里被粘连到上一行的列表条目。
- 修正 `docs/zh-CN/getting-started.md` 中 `references/smr.md` 的相对路径，
  原先少了 `../../`，指向一个不存在的位置。
- 修正五份 getting-started 指南中 `fetch-binary --out ./smr-bin` 的错误示例 ——
  `fetch-binary` 不接受任何参数（固定解压到全局缓存），该命令会被 argparse 拒绝。

- 修正 `docs/zh-CN/getting-started.md` 中 `references/smr.md` 的相对路径，
  原先少了 `../../`，指向一个不存在的位置。

### 文档

- 补齐日文、西班牙文、法文 README 的 SMR / HEIDI 段落 —— 此前这三份只覆盖工作流本身。
- 五份 getting-started 指南全部新增 SMR / HEIDI 操作步骤（取二进制、preflight、双引擎），
  并在 `docs/README.md` 索引中登记 `references/smr.md`。
- 同步自检用例数（110 → 118）与技能版本号（1.3.0 → 1.3.1）。

## 1.3.0 — 2026-10-01

### 新增

- 新增 `tools/mr_smr.py`：**双引擎 SMR / HEIDI 工具**。`--engine official` 驱动官方 `smr` 二进制
  （Yang lab，MIT），显式映射 **48 个**官方 flag 并提供 `official` 子命令做无遗漏原样透传；
  `--engine native` 为纯标准库实现，SMR 检验与官方**逐位一致**（约 6 位有效数字）。
- 新增 `references/smr.md`：输入格式、双引擎、对官方二进制的实测校准、完整参数映射表与常见坑。
- 新增 `tests/gen_smr_fixture.py`：零依赖、确定性的 SMR 测试数据集生成器；自检新增 J 组 13 条用例，
  守卫参数转发、假成功防护与数值校准（97 → 110）。
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
- 修复批量安装时同一秒内多个目标的备份目录重名、导致安装中途以 `FileExistsError` 中断的问题；自检新增 H5 回归用例（96 → 97）。
- 修复官方 `smr` **出错仍返回 exit 0**（错误只写日志）被上报成成功的问题：改为从日志提取 `Error:` 行，并校验 BESD 三件套确实生成。
- 修复 `make-besd` 未在 `.flist` 所在目录执行的问题：官方按 CWD 解析相对 ESD 路径，从别的工作目录调用会全线报
  `can not open the file [...] to read.` 却仍 exit 0，属于静默假成功。
- 放宽 E5 连通性断言：连接失败原因出现在 `error` 或 `hint` 均可，不再因宿主设置 `http_proxy` 而假失败。

### 文档

- 重新定位 **SMR / HEIDI**：上游 MRAgent 确实没有该功能（核对依据完整保留在
  `references/upstream-diff.md` 第九章），但本技能现在**主动内建**，因此文档从
  "不在能力范围内"改写为"新增能力"，避免把新增能力说成复刻上游。
  见 `SKILL.md` 第 11 条与 `references/smr.md`。
- 同步自检用例数（97 → 110）与技能版本号（1.2.0 → 1.3.0）。

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
