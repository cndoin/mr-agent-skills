---
name: mr-agent
description: "Orchestrate Mendelian randomization (MR) research with MRAgent: discover exposure-outcome candidates in PubMed, select OpenGWAS instruments, run TwoSampleMR, and review reports. Use for MR causal inference, GWAS, MRAgent, OpenGWAS, TwoSampleMR, MRlap, MR-MOE, or STROBE-MR tasks. 适用于孟德尔随机化、MR 因果推断、GWAS、暴露结局发现与结果解读；编排 PubMed、OpenGWAS 和 TwoSampleMR 工作流，不替代专业统计判断。"
license: MIT
compatibility: "CI 已验证 Python 3.11/3.12；预检接受 3.9–3.12（上游排除 3.9.7），但 3.9/3.10 未纳入 CI，3.13+ 当前拦截。完整运行还需 R > 4.3.4、mragent 包与 OpenGWAS JWT。缺依赖时预检会报告阻塞项；未装 mragent 时离线检索 / 打包 / CSV 编辑 / 评测工具仍可运行。"
allowed-tools: "Bash, Read, Write, Edit, Grep, Glob, WebFetch, WebSearch, TodoWrite"
metadata:
  version: "1.2.0"
  author: 寇豆码
  category: bioinformatics
  tags: [mendelian-randomization, causal-inference, gwas, opengwas, twosamplemr, mragent, strobe-mr, epidemiology, bioinformatics]
---

# MRAgent · 孟德尔随机化因果发现

## 路径约定（Codex / DeepSeek Harness / Claude Code / WorkBuddy 通用）

本文件所在目录即**技能根目录**，下文所有相对路径（`scripts/…`、`tools/…`）都以它为基准。

- **Claude Code**：可写成 `${CLAUDE_SKILL_DIR}/scripts/preflight.py`，
  该变量在技能加载时展开为技能目录的绝对路径。
- **Codex、DeepSeek Harness、WorkBuddy / 其他 Agent**：先 `cd` 到技能目录，再照抄相对路径即可。

所有脚本内部都用 `__file__` 定位自身与同级资源，
**从任意 cwd 调用都不会找错依赖**；`python scripts/preflight.py` 与
`python ${CLAUDE_SKILL_DIR}/scripts/preflight.py` 等价。

用 LLM 驱动的 MRAgent（[xuwei1997/MRAgent](https://github.com/xuwei1997/MRAgent)，Apache-2.0，
论文 DOI `10.1093/bib/bbaf140`）自动完成：扫 PubMed 找暴露-结局对 → 选 GWAS →
跑 TwoSampleMR → 出 PDF 报告。本 skill 负责**编排、环境治理、分步执行、结果解读**，
不替代 MRAgent 本身的统计计算。

## Non-negotiable facts（先验证，违反会静默失败）

1. **Python 必须 < 3.13，推荐 3.12。**
   `mragent` 的官方依赖锁了 `numpy>=1.19.5,<2.0` 和 `pandas>=1.4.2,<2.0`。
   这两个版本**没有 cp313 预编译 wheel**，Python 3.13 上会从源码编译，
   需要 gcc + meson，本机没有 → 必然失败（已实测：`metadata-generation-failed`）。
   Python 3.11 / 3.12 有现成 wheel，装得上。**不要试图在 3.13 上硬装。**
2. **R 必须存在，且可执行文件就叫 `R`。**
   MRAgent 用 `os.system('R --slave --no-save --no-restore --no-site-file --no-environ -f test.R --args')`
   调 R。是 `R` 不是 `Rscript`，必须在 `PATH` 里。R 版本 > 4.3.4。
   必需 R 包：`TwoSampleMR`、`ieugwasr`、`dplyr`、`vcfR`、`MRlap`、`jsonlite`。
   其中 `TwoSampleMR` / `ieugwasr` 通常要从 GitHub 装（`remotes::install_github`）。
3. **`gwas_token` 是硬门槛。** OpenGWAS JWT，从 <https://api.opengwas.io/> 申请。
   R 侧靠 `Sys.setenv(OPENGWAS_JWT=...)` 注入。没有它，step5 之后的 GWAS 取数全废。
4. **每个任务必须用独立工作目录。**
   MRAgent 把中间产物写在 **当前工作目录**：`./output/<名称>/` 以及一个临时的 **`test.R`**。
   两个分析并行跑会互相覆盖 `test.R` 和结果目录 —— 这是设计缺陷，不是你可以忽略的细节。
5. **`mode` 只有三种合法值**：`'O'`（疾病当结局，找暴露）、`'E'`（疾病当暴露，找结局）、
   `'OE'`（用户直接给一对暴露-结局做验证）。`OE` 走 `MRAgentOE` 类，不是 `MRAgent`。
6. **LLM 后端二选一**：`model_type='openai'`（需要 `AI_key`，可用 `base_url` 指到兼容平台）
   或 `model_type='ollama'`（本地，不需要 key）。调用时固定 `seed=42`。
7. **step3 会静默退出且退出码为 0。** 当 LLM 判定所有暴露-结局对都已经做过 MR
   （`MRorNot` 全是 `Yes`）时，源码直接 `sys.exit(0)` —— 进程看起来“成功”了，
   但**一个 MR 都没跑**。判成败必须看 `mr_run.csv` 是否存在，**不要用退出码判断**。
8. **技能目录叫 `mr-agent` 而不叫 `mragent`，是故意的。**
   若目录名与 Python 包同名，在该目录的父级下跑 python
   会技能目录当成命名空间包导入，报
   `cannot import name 'MRAgent' from 'mragent' (unknown location)`。
9. **不要用上游的在线 GWAS 检索 —— 它已经失效了。**
   上游 `check_keyword_in_opengwas` / `get_gwas_id` 是爬 `gwas.mrcieu.ac.uk` 的 HTML，
   靠页面里有没有 `"Filtered to 0 records"` 判断命中。2026-10-01 实测该页面已改为
   前端渲染，**对任何关键词都不再包含这个字符串**（连乱码词都不含），
   表格里只剩 `Failed to load batches data.`。
   后果是它对**任何**输入都返回 True（永远"有数据"），不报错、静默往下走，
   把垃圾 `gwas_id` 一路写进 `Outcome_SNP.csv`。
   本技能不复刻该行为：`mr_gwas.py --mode online` 改走官方鉴权 API
   （`api.opengwas.io/api/gwasinfo`，需 JWT）；没有 JWT 就用 `--mode csv` 读离线清单。

10. **同义词扩展默认关闭。** 上游 MRAgent 在 `synonyms=True` 时会调用 UMLS，
    并使用包内硬编码的作者 key；当前 API 不支持注入用户自己的 key。
    独立工具 `tools/mr_synonyms.py` 只接受用户自己的 UMLS key。

11. **本技能不含 SMR / HEIDI，这是故意的。**
    SMR（Summary-data-based MR）是 TwoSampleMR 之外的另一套方法学，
    需要 `.besd` 格式的 QTL 数据 + 自备 LD reference panel + `smr` 命令行工具。
    上游 MRAgent **本身就没有** SMR 功能（`agent_tool.py` 只有 `MRtool` /
    `MRtool_MOE` / `MRtool_MRlap` 三个分析函数），本技能的能力面与之严格对齐。
    被问到 SMR 时如实回答"上游与本技能都不提供"，
    **不要拿 TwoSampleMR 冒充 SMR**。详见 `references/upstream-diff.md` 第九章。

## 运行规则

### 第一步永远是 preflight，不要凭感觉开工

```bash
python scripts/preflight.py --json
```

它会输出结构化 JSON：`python` 版本是否合规、`R` 是否在 PATH、R 包缺哪几个、
`mragent` 是否可导入、`OPENAI_API_KEY` / `MRAGENT_GWAS_TOKEN` / `OPENGWAS_JWT` 是否存在、
OpenGWAS 与 PubMed 是否可达。

**任何一项 `required=true` 且 `ok=false`，就停下来报告，不要带着缺口往下跑。**
把 preflight 的真实输出贴给用户，不要说"环境应该没问题"。

### 先确认三件事再写代码

```
目标模式  : O（找某病的因） | E（找某病的果） | OE（验证一对）
目标实体  : outcome='...' / exposure='...' + outcome='...'
运行范围  : 全量 step 1-10 | 分步（先 1-2 看暴露结局对，人工改 CSV 再往下）
```

不确定就问。疾病名写错，整条链九步全白跑。

### 绝不臆造的东西

| 事实 | 必须来自 |
| --- | --- |
| `gwas_token` | 用户，或环境变量 `MRAGENT_GWAS_TOKEN` / `OPENGWAS_JWT` |
| `AI_key` | 用户，或环境变量 `OPENAI_API_KEY` |
| Python 版本是否可用 | `preflight.py` 实际探测 |
| R 包是否齐全 | `preflight.py` 实际探测 |
| 暴露/结局名 | 用户给的原始表述，**不要自作主张改成 MeSH 术语** |
| MR 结果数字 | `output/` 下 CSV 读出来的，不是 LLM 复述的 |

## 两种模式怎么用

### 知识发现（mode='O' / 'E'）

```python
from mragent import MRAgent
agent = MRAgent(mode='O', outcome='back pain', model='MR', LLM_model='gpt-4o',
                AI_key=key, gwas_token=token, bidirectional=True, synonyms=False,
                introduction=True, num=300)
agent.run(step=[1,2,3,4,5,6,7,8,9,10])
```

`num` 是抓多少篇 PubMed 文章，默认 100。想挖得全就调大，代价是 LLM 调用次数线性上升。

### 因果验证（mode='OE'）

```python
from mragent import MRAgentOE
agent = MRAgentOE(exposure='osteoarthritis', outcome='back pain',
                  model='MR', LLM_model='gpt-4o', AI_key=key, gwas_token=token,
                  bidirectional=True, synonyms=False, introduction=False)
agent.run(step=[1,2,3,4,5,6,7,8,9,10])
```

`MRAgentOE` 只重写了 `step1`（直接把你给的一对写进 `Exposure_and_Outcome.csv`），
其余步骤继承 `MRAgent`。

### 常用开关

| 参数 | 默认 | 作用 / 代价 |
| --- | --- | --- |
| `bidirectional` | False | 双向 MR。**会让运行时间和 LLM 开销翻倍** |
| `synonyms` | False（本技能运行器默认） | 同义词扩展可能使用上游内置 UMLS key；只有接受此限制时才显式开启 |
| `introduction` | True | 生成疾病背景引言 |
| `mr_quality_evaluation` | False | STROBE-MR 质量评估，额外 LLM 调用 |
| `mrlap` | False | 样本重叠校正，**需要先下载 ld + hm3 大文件** |
| `model` | `'MR'` | `'MR_MOE'` 走混合专家框架，**需额外下载 `rf.rdata`** |
| `opengwas_mode` | `'online'` | `'csv'` 走本地 GWAS 清单 |

## 分步执行与人工干预（这是 MRAgent 最有用的设计）

不要一上来就跑全量。推荐节奏：

全程只有三个中间 CSV，名字是**从源码实测**的（README 里写的 `outcome` / `run` 是错的）：

| 文件 | 谁写 | 谁读 |
| --- | --- | --- |
| `Exposure_and_Outcome.csv` | step1（step6/7/8 会回写） | step2/3/6/7/8/9 |
| `Outcome_SNP.csv` | step3（step5 补 `gwas_id`） | step4/5/6/9 |
| `mr_run.csv` | step8 | step9 |

推荐节奏：

1. `run(step=[1,2])` → 看 `Exposure_and_Outcome.csv`，LLM 从文献里抽的暴露-结局对靠不靠谱。
2. 人工增删其中的行 → 再 `run(step=[3,4,5,6,7,8,9,10])`。
3. step5 后检查 `Outcome_SNP.csv` 的 `gwas_id` 选得对不对；step8 后检查 `mr_run.csv`
   里最终进入 MR 的组合。

`run(step=None)` 等于 `[1..10]`，其中 step10 无实现，无害。

## 输出在哪、怎么读

```
./output/
└── <outcome 或 exposure>_<LLM_model>/      # 例如 back_pain_gpt-4o
    ├── Exposure_and_Outcome.csv      # 抽出的暴露-结局对 + MRorNot 判定
    ├── Outcome_SNP.csv               # 同义词扩展 + opengwas 命中 + gwas_id
    ├── mr_run.csv                    # 最终进入 MR 的暴露×结局组合
    ├── <Exposure>_<Outcome>/         # 每个 oeID 一个目录
    │   └── <Exposure>_<Outcome>/     # 每个同义词组合一层
    │       ├── 统计结果 CSV
    │       ├── pic.scatterplot.pdf / pic.forest.pdf
    │       ├── pic.funnel_plot.pdf / pic.leaveoneout.pdf
    │       └── *.pdf 报告（引言 / 结果解读 / 结论）
    └── <Outcome>_<Exposure>/         # bidirectional=True 时多出的反向目录
```

用 `python scripts/summarize_output.py <output目录>` 直接出摘要，别手翻。

## 本机降级路径（诚实边界）

本机（Windows）现状：**Python 3.13 有、R 没有、Docker 没有、WSL 被拦**。
所以本机**跑不了完整 MR**。遇到这种环境，必须明确告诉用户三选一：

1. **装 R + 建 Python 3.12 venv**（本机最重，但能真跑）；
2. **生成可移植脚本**，交给用户的 Linux 服务器 / HPC / Colab 跑；
3. **GitHub Actions** 编排（`setup-r` + `setup-python@3.12`）。

选 2 或 3 时，本 skill 仍然有价值：负责写对参数、写对环境脚本、事后解析 `output/` 和解读报告。
**不要因为跑不了就假装跑过，也不要编造 MR 结果数字。**

## 失败协议

| 症状 | 真实原因 | 处置 |
| --- | --- | --- |
| `metadata-generation-failed` 装 numpy | Python 3.13 撞 `numpy<2` | 换 3.12 venv，别硬编译 |
| `'R' is not recognized` | R 不在 PATH | 装 R 并把 `bin` 加进 PATH |
| `there is no package called 'TwoSampleMR'` | R 包没装 | 走 `references/environment.md` 的装包命令 |
| GWAS 取数全空 / 401 | `gwas_token` 无效或过期 | 重新申请 JWT，确认 `OPENGWAS_JWT` 注入成功 |
| `output/` 里文件张冠李戴 | 两个任务共用 CWD | 每个任务独立工作目录 |
| step1 抽出大量 `null` | LLM 抽不出实体 | 换更强的模型或调大 `num`，别硬往下跑 |

## 工具包（tools/ —— 原子能力，AI 可单独调用）

把 MRAgent 内部的函数拆成一个个独立命令，
**想做单个动作时不必跑整条流水线**。
全部遵循同一契约：standard output 只放 JSON，
缺参数 / 缺依赖都返回结构化错误（exit 2）。

| 工具 | 对应上游 | 典型用法 |
| --- | --- | --- |
| `mr_pubmed.py` | `pubmed_crawler` / `get_paper_details` | `--keyword "back pain" --num 20` |
| `mr_gwas.py` | `check_keyword_in_opengwas` / `get_gwas_id` | `--keyword "body mass index"`（默认离线，不需 mragent） |
| `mr_synonyms.py` | `get_synonyms`（UMLS） | `--term "body mass index"`（需自己的 `UMLS_API_KEY`） |
| `mr_llm.py` | `llm_chat` / `openai_gpt` / `ollama_chat` | `--prompt "..." --model gpt-4o` |
| `mr_eval.py` | `outcome_exposure_MRorNot` / `STROBE_MR` | `--mrornot --outcome X --exposure Y` |
| `mr_bench.py` | `step_2_test` / `step_5_test` | `--file a.csv --gt MRorNot --pred MRorNot_gpt-4o --mode accuracy` |
| `mr_prompt.py` | `template_text.py` + `step_9_test_prompt.py` | `--list` / `--show LLM_MR_template` / `--render ...` |
| `export_results.py` | web 的 ZIP 下载按钮 | `export_results.py <output目录>` |
| `edit_csv.py` | web 的在线表格编辑 | `--dir <run> --file mr_run.csv --show` |
| `serve_web.py` | `web_demo.py` | `serve_web.py --check` |

**只有 `mr_eval.py` 真正需要 mragent**（它要构造 `MRAgent` 实例才能拿到那两个方法）；
`serve_web.py` 需要 streamlit。其余工具都是原生实现，
`mr_pubmed` / `mr_synonyms` / `mr_llm` / `mr_gwas` 的离线模式 / `mr_prompt` /
`export_results` / `edit_csv` / `mr_bench` **在没装 mragent 的机器上也能跑**。

## 参考文件

- `references/api.md` —— 实测得到的 API 速查（真实签名，非 README 转述）
- `references/environment.md` —— Python / R / token 完整搭建与验证命令
- `references/pitfalls.md` —— 从源码里挖出来的坑位清单
- `references/upstream-diff.md` —— **上游仓库 vs PyPI 包 vs 本技能**的逐项能力对照
- `scripts/preflight.py` —— 环境预检，输出 JSON
- `scripts/run_mr.py` —— 统一运行入口（独立工作目录 + 日志捕获 + 静默失败捕获）
- `scripts/summarize_output.py` —— 解析 output 目录出摘要
- `key.py.example` —— 上游 3 个实验脚本 `from key import ...` 用的凭据模板
  （上游仓库里没有 `key.py`，那些脚本 clone 下来必 `ModuleNotFoundError`；
  本技能一律走环境变量，不需要这个文件，它只是给要跑上游原版脚本的人兜底）

想知道"上游某个函数对应本技能哪个入口"，直接查
`references/upstream-diff.md` 第五节的逐项对照表。

## 运行日志在哪

真实运行时，MRAgent 和 R 会往 stdout 狂写输出。
`run_mr.py` 用 `os.dup2` 在文件描述符层重定向，
把它们全部收进 `<工作目录>/run.log`，
**stdout 依然只有一个 JSON**。
想看过程就 tail 那个日志：`tail -f <workdir>/run.log`。

## 安装到不同的 Agent

```bash
# 全部支持的 Agent（Claude Code / WorkBuddy / CodeBuddy / Codex / DeepSeek Harness）
python install.py --target all

# 只装 Claude Code
python install.py --target claude

# 只装 WorkBuddy
python install.py --target workbuddy

# 只装 Codex 或 DeepSeek Harness
python install.py --target codex
python install.py --target deepseek
```

`install.py` 会：复制技能目录 → 校验 frontmatter 合法性 → 下载离线 GWAS 清单到
全局缓存（`~/.cache/mr-agent/opengwas.csv`，10 MB，已排除出 git 仓库）→ 跑一次冒烟。
网络不可用时它不会失败，只提示你事后用 `python tools/mr_gwas.py --fetch` 补下载。

## 自检

```bash
python scripts/selftest.py          # 全量，97 条用例
python scripts/selftest.py --quick  # 跳过真实网络探测
python scripts/selftest.py --json   # 输出 JSON，失败时退出码 1（可直接接 CI）
```

发布或改动后必跑。它会真实调用每个脚本的入口，
断言退出码、JSON 合法性、错误路径契约与路径穿越防护。
