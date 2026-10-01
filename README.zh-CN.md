<div align="center">

# MR Agent

### 从论文到可检验的假设

面向孟德尔随机化研究的开源智能体技能。

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [Español](README.es.md) · [Français](README.fr.md)

![MR Agent 项目视觉](assets/mr-agent-cover.svg)

</div>

快速入口：[简体中文使用指南](docs/zh-CN/getting-started.md) · [所有语言的指南](docs/README.md)

把 [xuwei1997/MRAgent](https://github.com/xuwei1997/MRAgent)（Apache-2.0，
论文 [DOI 10.1093/bib/bbaf140](https://doi.org/10.1093/bib/bbaf140)）
包装成可被 Agent 直接调度的能力：自动扫 PubMed 找暴露-结局对 → 选 GWAS →
跑 TwoSampleMR → 出图出报告。

## 安装

支持 **Claude Code、WorkBuddy、CodeBuddy、OpenAI Codex 和 DeepSeek Harness**，一个命令安装到对应的原生技能目录：

```bash
python install.py --target all       # 全部
python install.py --target claude    # 只装 ~/.claude/skills/mr-agent
python install.py --target workbuddy # 只装 ~/.workbuddy/skills/mr-agent
python install.py --target codex     # 只装 Codex（默认 ~/.codex/skills/mr-agent）
python install.py --target deepseek  # 只装 DeepSeek Harness（默认 ~/.dsh/skills/mr-agent）
python install.py --list             # 只看装到哪，不装
```

Codex 支持用 `CODEX_HOME` 自定义根目录，DeepSeek Harness 支持用 `DSH_HOME` 自定义根目录；未设置时使用上述默认路径。

它会：复制技能目录 → 校验 `SKILL.md` 的公共技能元数据 → 下载离线 GWAS 清单到全局缓存 → 跑冒烟。

也可以手工拷贝，效果一样 —— 这个技能没有构建步骤，也没有必须安装的位置。

## 它做什么

| 模式 | 入口类 | 用途 |
| --- | --- | --- |
| `O` | `MRAgent` | 给定疾病当**结局**，自动找潜在暴露（找"因"） |
| `E` | `MRAgent` | 给定疾病当**暴露**，自动找潜在结局（找"果"） |
| `OE` | `MRAgentOE` | 给定一对暴露-结局，直接做因果验证 |

## 它不做什么

- **不做统计计算本身** —— MR 由 R 的 TwoSampleMR 完成，本技能只负责编排与治理。
- **不保证环境一定能跑** —— 需要 Python 3.11/3.12 + R（>4.3.4）+ OpenGWAS JWT。
  缺任何一项，`preflight.py` 会明确报阻塞，不会假装能跑。
- **不编造结果数字** —— 所有结论必须来自 `output/` 下的 CSV 与 PDF。

## 可选：让 MRAgent 内部调用 DeepSeek

运行本技能的 Agent（Codex 或 DeepSeek Harness）和 MRAgent 分析期间调用的 LLM 是两项独立配置。MRAgent 支持 OpenAI 兼容接口：在系统环境变量中设置 `MRAGENT_AI_KEY`，然后把模型和接口地址传给运行器：

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --llm-model deepseek-flash --base-url https://api.deepseek.com
```

请查看 [DeepSeek API 文档](https://api-docs.deepseek.com/guides/agent_integrations/opencode)确认当前模型名和接口兼容性。不要把真实 key 写进命令、源码或 issue。

## 目录结构

```
mr-agent/
├── SKILL.md                      # 主入口：硬约束、操作规则、失败协议
├── README.md                     # 本文件
├── install.py                    # 装到 Claude Code / WorkBuddy / CodeBuddy / Codex / DeepSeek Harness
├── LICENSE / NOTICE              # MIT；NOTICE 记录上游与数据来源
├── CONTRIBUTING.md / SECURITY.md # 贡献约束；凭据处理规则
├── CHANGELOG.md / Makefile
├── .editorconfig                # 配 .gitattributes 一起锁 LF
└── .github/workflows/ci.yml     # 3 OS × py3.11/3.12，刻意不装 mragent
├── references/
│   ├── api.md                    # 源码实测的 API 速查（签名 / step / 文件名）
│   ├── environment.md            # Python / R / token 完整搭建与验证
│   ├── pitfalls.md               # 19 个坑位，按严重程度分级
│   ├── smr.md                    # SMR / HEIDI：数据格式、双引擎、官方校准实测
│   └── upstream-diff.md          # 上游仓库 vs PyPI 包 vs 本技能的能力对照
├── scripts/                      # 流程编排
│   ├── preflight.py              # 环境预检 → 结构化 JSON
│   ├── run_mr.py                 # 统一运行入口（独立目录 + 日志捕获 + 静默失败捕获）
│   ├── summarize_output.py       # 解析 output/ → 结构化摘要
│   └── selftest.py               # 118 条自检用例
└── tools/                        # 原子能力（AI 可单独调用）
    ├── _common.py                # 共享层：JSON 契约、mragent 导入、fd 重定向
    ├── mr_pubmed.py              # PubMed 检索 / 论文详情
    ├── mr_gwas.py                # OpenGWAS 在线查询 + 离线清单检索 + 清单下载
    ├── mr_synonyms.py            # UMLS 同义词扩展
    ├── mr_llm.py                 # LLM 调用（openai / ollama）
    ├── mr_eval.py                # 是否做过 MR 判定 / STROBE-MR 质量评估
    ├── mr_bench.py               # 准确率 / 查准率 / 查全率 / F1 评测
    ├── mr_smr.py                 # SMR + HEIDI（官方引擎 / 零依赖原生引擎双路径）
    ├── export_results.py         # 结果目录打 ZIP
    ├── edit_csv.py               # 读写三个中间 CSV（人工干预的程序化入口）
    └── serve_web.py              # 拉起上游 Streamlit Web 界面
```

其中 `mr_gwas.py`（离线模式）、`export_results.py`、`edit_csv.py`、`mr_bench.py`
**不依赖 mragent**，没装环境也能跑；其余需要 Python 3.11/3.12 + mragent。
`mr_smr.py --engine native` 也是纯标准库（零依赖）；`--engine official` 需要
官方 `smr` 二进制，用 `fetch-binary` 自动下载或设 `SMR_BIN`。

### 超出上游的部分：SMR / HEIDI

上游 MRAgent 只有 TwoSampleMR（IVW / Egger / weighted median / mode），
**回答不了"哪个基因介导了这个信号"**。本技能额外内建了 SMR（Summary-data-based MR，
Zhu et al. 2016 *Nat Genet*）：用 cis-xQTL 作工具变量，检验分子表型是否介导
SNP→性状的效应，核心产出是 SMR 检验与 HEIDI 检验（区分连锁不平衡 vs 共享因果变异）。

这是**主动扩展而不是复刻上游**，因此与"对齐上游"的部分分开表述。
两条路径：`--engine official` 驱动官方 `smr` 命令行（功能最全，48 个 flag 已映射，
另有 `official` 子命令做无遗漏透传）；`--engine native` 是零依赖实现，
SMR 检验与官方**逐位一致**，HEIDI 的 `p_HEIDI` 小数位有已知差异（已显式标注）。
详见 [`references/smr.md`](references/smr.md)。

### 离线 GWAS 清单

`opengwas.csv`（10.3 MB / 50044 行）是上游仓库里的 GWAS 目录索引。
**它不随本仓库分发** —— 10 MB 的第三方数据不该进 git（见 `NOTICE`）。
`install.py` 会把它下载到全局缓存：

```
~/.cache/mr-agent/opengwas.csv      # 多个安装位置共用一份
```

装完就能离线检索，不需要联网、也不需要 mragent：

```bash
python tools/mr_gwas.py --keyword "body mass index" --mode csv
```

手工补下载 / 更新：`python tools/mr_gwas.py --fetch`。
也可用环境变量 `MRAGENT_OPENGWAS_CSV` 指向你自己的副本。


## 快速开始

```bash
# 1. 体检
python scripts/preflight.py --python <你的 3.12 解释器>

# 2. 先跑前两步，看 LLM 抽出来的暴露-结局对靠不靠谱
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2

# 3. 人工过一遍 Exposure_and_Outcome.csv，再跑剩下的
python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9,10

# 可选：打开 UMLS 同义词扩展；上游包会使用其内置 key，默认关闭
# python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9,10 --synonyms

# 4. 出摘要
python scripts/summarize_output.py ./mragent-runs/back_pain_O_*/output

# 5. 打包交付
python tools/export_results.py ./mragent-runs/back_pain_O_*/output
```

## 不跑全流程，只想做单个动作

```bash
# 先离线确认某表型到底有没有 GWAS 数据（不需要 mragent、不需要联网）
python tools/mr_gwas.py --keyword "body mass index" --mode csv

# 看看某疾病最近文献（step1 的原子能力）
python tools/mr_pubmed.py --keyword "back pain" --num 20

# 人工改中间产物再继续跑
python tools/edit_csv.py --dir <run目录> --file mr_run.csv --show
python tools/edit_csv.py --dir <run目录> --file mr_run.csv --row 0 --col MRorNot --value No
```

## 自检

```bash
python scripts/selftest.py            # 118 条用例
python scripts/selftest.py --quick    # 跳过真实网络探测
python scripts/selftest.py --json     # 输出 JSON，供 CI 消费（失败时退出码 1）
```

覆盖：参数契约（错误路径也必须返回 JSON）、路径穿越防护、畸形 CSV、
编码异常、深层嵌套、凭据脱敏、打包排除 `test.R`、开源卫生（无硬编码密钥）。

**全部脚本用 `__file__` 定位资源**，安装到其他目录后也会从脚本自身位置
查找同级文件。

CI（`.github/workflows/ci.yml`）跑的就是这套自检。**它刻意不装 mragent** ——
E 组用例断言的正是"没有 mragent 时的降级路径"，装上反而会失败。
网络拿不到 `opengwas.csv` 时相关用例会 `[SKIP]` 而非假绿。

## 环境变量

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `MRAGENT_GWAS_TOKEN` / `OPENGWAS_JWT` | 是 | OpenGWAS JWT，<https://api.opengwas.io/> 申请 |
| `MRAGENT_AI_KEY` / `OPENAI_API_KEY` | 视后端 | `model_type='ollama'` 时不需要 |
| `UMLS_API_KEY` | 独立同义词工具 | 完整流水线默认关闭；显式 `--synonyms` 会使用上游包内置 key |

## 三个脚本的设计约定

统一约定：**stdout 只放结构化 JSON，人类提示走 stderr**；
空状态与错误路径也必须返回 JSON，不靠异常堆栈表达结果。

- `preflight.py`：`ready: true/false` + `blocking` 列表，缺什么一目了然。
- `run_mr.py`：强制 `chdir` 到独立工作目录（避免 `test.R` / `./output` 被并发覆盖）；
  捕获 `SystemExit` 并用 `mr_run.csv` 判定成败（**不看退出码**）。
- `summarize_output.py`：不依赖 pandas，纯标准库，任何解释器都能跑。

## 兼容的 Agent

| Agent | 安装位置 | 状态 |
| --- | --- | --- |
| Claude Code | `~/.claude/skills/mr-agent` | 已验证：frontmatter 合法、自检全绿 |
| WorkBuddy | `~/.workbuddy/skills/mr-agent` | 已验证：同上 |
| CodeBuddy | `~/.codebuddy/skills/mr-agent` | 同格式，未实机验证 |
| OpenAI Codex | `$CODEX_HOME/skills/mr-agent`（默认 `~/.codex/skills/mr-agent`） | 安装路径与元数据已自检；需在 Codex 中确认加载 |
| DeepSeek Harness | `$DSH_HOME/skills/mr-agent`（默认 `~/.dsh/skills/mr-agent`） | 安装路径与元数据已自检；需在 Harness 中确认加载 |

`SKILL.md` 使用各端共有的 `name` 和 `description` 作为发现元数据，并保留
`license` / `compatibility` / `allowed-tools` / `metadata` 扩展信息。
安装器检查公共字段，避免某个 Agent 的专属 frontmatter 规则阻止其他端加载。
正文里的路径是相对技能根目录的，Claude Code 可写成
`${CLAUDE_SKILL_DIR}/scripts/preflight.py`，其他 Agent `cd` 进去照抄即可。

## 许可

本技能自身代码 **MIT**，见 `LICENSE`。

它依赖但**不包含**上游代码：运行时 `import` 的 `mragent` 是 Apache-2.0，
调用的 R 包（TwoSampleMR / ieugwasr / MRlap 等）各有其 GPL 许可，
数据来源（OpenGWAS / PubMed / UMLS）各有使用条款。完整归属见 **`NOTICE`**。

使用请引用原论文：*Briefings in Bioinformatics*, 2025, doi:10.1093/bib/bbaf140。
