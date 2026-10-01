# 上游仓库 vs PyPI 包 vs 本技能：完整比对

比对时间 2026-10-01，上游 `github.com/xuwei1997/MRAgent` main 分支，
PyPI `mragent==0.2.5`。

## 一、比对方法

1. `git clone --depth 1` 上游仓库到本地
2. `pip download mragent==0.2.5` 取 wheel
3. 对 `mragent/` 下 6 个 .py 做逐字节比对

**结论：核心库完全一致。**

```
__init__.py            raw:CRLF  crlf:LF  lf-normalized:IDENTICAL
LLM.py                 raw:CRLF  crlf:LF  lf-normalized:IDENTICAL
agent_tool.py          raw:CRLF  crlf:LF  lf-normalized:IDENTICAL
agent_workflow.py      raw:CRLF  crlf:LF  lf-normalized:IDENTICAL
agent_workflow_OE.py   raw:CRLF  crlf:LF  lf-normalized:IDENTICAL
template_text.py       raw:CRLF  crlf:LF  lf-normalized:IDENTICAL
```

字节不同只有一个原因：本机 `core.autocrlf=true`，克隆时把 LF 转成了 CRLF。
**归一化行尾后逐字节相同**，所以本技能里记录的 API 签名、step 语义、
坑位清单对上游源码同样成立，不存在"pip 版和 GitHub 版行为不同"的问题。

## 二、上游仓库多出来的东西（wheel 里没有）

| 文件 | 是什么 | 本技能的处理 |
| --- | --- | --- |
| `opengwas.csv` | 10.3 MB / 50044 行的离线 GWAS 清单 | `mr_gwas.py --mode csv` 直接用，`--fetch` 可下载 |
| `web_demo.py` | 487 行 Streamlit 界面 | `serve_web.py` 负责拉起 |
| `agent_workflow_demo.py` | 知识发现 demo | 参数已并入 `run_mr.py`（含 `mr_quality_evaluation_key_item`） |
| `agent_workflow_OE_demo.py` | 因果验证 demo | `run_mr.py --mode OE` |
| `step_1_test_out.py` | step1 抽取结果输出 + 多模型对比 | `mr_pubmed.py` + `mr_bench.py` |
| `step_2_test.py` | step2 MRorNot 判定**准确率** | `mr_bench.py --mode accuracy` |
| `step_2_test_STROBE_MR.py` | STROBE-MR 评估 | `mr_eval.py --strobe` |
| `step_5_test.py` | step5 GWAS 选择的**查准/查全/F1** | `mr_bench.py --mode prf` |
| `step_9_test_out.py` / `step_9_test_prompt.py` | step9 结果解释 | `summarize_output.py` |
| `step_1/9_test_SimCSE.py` | SimCSE 语义相似度（论文实验） | **未纳入** —— 依赖 SimCSE 模型，属论文复现环境，非生产能力 |
| `pyproject.toml` / `images/` / `.idea/` | 构建配置与图片 | 无关 |

## 三、能力对照表

### 编排层（scripts/）

| 上游能力 | 上游入口 | 本技能 | 状态 |
| --- | --- | --- | --- |
| 知识发现（找因） | `MRAgent(mode='O')` | `run_mr.py --mode O` | 已覆盖 |
| 知识发现（找果） | `MRAgent(mode='E')` | `run_mr.py --mode E` | 已覆盖 |
| 因果验证 | `MRAgentOE` | `run_mr.py --mode OE` | 已覆盖 |
| **模式自动推断** | web_demo `O if outcome else E` | `run_mr.py --mode auto` | 已覆盖（新增） |
| 分步执行 | `run(step=[...])` | `run_mr.py --steps` | 已覆盖 |
| 双向 MR | `bidirectional=True` | `--bidirectional` | 已覆盖 |
| 同义词开关 | `synonyms` | 默认关闭；`--synonyms` 显式开启 | 已覆盖（上游内置 UMLS key） |
| 引言开关 | `introduction` | `--no-introduction` | 已覆盖 |
| MR_MOE 混合专家 | `model='MR_MOE'` | `--model MR_MOE` | 已覆盖 |
| MRlap 校正 | `mrlap=True` | `--mrlap` | 已覆盖 |
| STROBE-MR 评估 | `mr_quality_evaluation` | `--mr-quality-evaluation` | 已覆盖 |
| **STROBE-MR 关键条目** | `mr_quality_evaluation_key_item` | `--mr-quality-evaluation-key-item` | 已覆盖（新增） |
| OpenAI 兼容平台 | `base_url` | `--base-url` | 已覆盖 |
| 本地 Ollama | `model_type='ollama'` | `--model-type ollama` | 已覆盖 |
| 离线 GWAS 模式 | `opengwas_mode='csv'` | 见 `mr_gwas.py` | 已覆盖 |
| 环境体检 | **上游没有** | `preflight.py` | 本技能独有 |
| 结果摘要 | **上游没有** | `summarize_output.py` | 本技能独有 |
| 运行日志捕获 | 仅 web 有 | `run_mr.py` 的 `run.log` | 已覆盖（上游 CLI 没有） |

### 原子能力层（tools/）

| 上游函数 | 上游位置 | 本技能入口 | 状态 |
| --- | --- | --- | --- |
| `pubmed_crawler` | agent_tool.py:30 | `mr_pubmed.py --keyword` | 已覆盖 |
| `get_paper_details` | agent_tool.py:92 | `mr_pubmed.py --details` | 已覆盖 |
| `get_paper_details_pmc` | agent_tool.py:221 | `mr_pubmed.py --details --pmc` | 已覆盖 |
| `check_keyword_in_opengwas` | agent_tool.py:168 | `mr_gwas.py --mode online` | 已覆盖 |
| `get_gwas_id` | agent_tool.py:195 | `mr_gwas.py --mode online` | 已覆盖 |
| `get_synonyms` | agent_tool.py:675 | `mr_synonyms.py` | 已覆盖 |
| `MRtool` / `MRtool_MOE` / `MRtool_MRlap` | agent_tool.py:261/386/487 | 经 `run_mr.py` step9 触发 | 已覆盖（R 侧，不单独暴露） |
| `llm_chat` / `openai_gpt` / `ollama_chat` | LLM.py | `mr_llm.py` | 已覆盖 |
| `MRAgent.outcome_exposure_MRorNot` | agent_workflow.py:152 | `mr_eval.py --mrornot` | 已覆盖 |
| `MRAgent.STROBE_MR` | agent_workflow.py:208 | `mr_eval.py --strobe` | 已覆盖 |
| `MRAgent.step5_get_gwas_id` | agent_workflow.py:398 | `mr_gwas.py` | 已覆盖 |
| 中间 CSV 在线编辑 | web_demo data_editor | `edit_csv.py` | 已覆盖 |
| 结果 ZIP 下载 | web_demo:263 | `export_results.py` | 已覆盖 |
| Web 界面 | web_demo.py | `serve_web.py` | 已覆盖 |
| 准确率 / PRF 评测 | step_2/5_test.py | `mr_bench.py` | 已覆盖 |

**未纳入**：`step_*_test_SimCSE.py`（SimCSE 语义相似度）。它依赖
`SimCSE` 预训练模型与论文实验数据集，属于论文复现环境，不是日常生产能力；
如确需，可单独按上游脚本跑。

## 四、本技能比上游多出来的（上游没有的能力）

这些都是为了让 AI 能安全、可解析地调用而补的：

1. **`preflight.py`** —— 上游完全没有环境体检，装不上就一路报错到底
2. **`summarize_output.py`** —— 上游只能自己翻 CSV
3. **stdout 只放 JSON 的契约** —— 上游 CLI 直接 print，无法被程序解析；
   本技能用 `os.dup2` 做 fd 级重定向，把 Python print 和 R 原生输出一起收进 `run.log`
4. **静默失败捕获** —— 上游 step3 `sys.exit(0)` 让人误以为成功；
   本技能用 `mr_run.csv` 是否存在判成败
5. **独立工作目录** —— 上游 `test.R` / `./output` 写 CWD，并发互踩
6. **结果完整性校验** —— 打包时提示"没有 PDF = 还没跑到 step9"

## 五、上游 Web 与 CLI 的差异（值得知道）

`web_demo.py` 里 `mrlap` 和 `mr_quality_evaluation` 两个开关是
`disabled=True` 的 —— **作者只在 Web 上禁用了**，CLI/脚本里可以用
（上游 `agent_workflow_demo.py` 就把两个都开了）。所以想用这两个功能，
必须走本技能的 `run_mr.py`，不要指望 Web 界面。
