# MRAgent API 速查（源码实测版）

本文件的内容**来自解包 `mragent==0.2.5` 后的源码**，不是 README 转述。
凡与 README 冲突之处，以本文件为准（README 有几处已经过时/写错）。

## 包结构（wheel 内实际只有 5 个 Python 文件，没有任何 .R 文件）

```
mragent/
├── __init__.py            # 仅两行：from .agent_workflow import MRAgent; from .agent_workflow_OE import MRAgentOE
├── agent_workflow.py      # 1037 行，MRAgent 类与 step1~step10
├── agent_workflow_OE.py   # 19 行，MRAgentOE 只重写 step1
├── agent_tool.py          # 709 行，PubMed 抓取 / UMLS / OpenGWAS / 内联 R 脚本
├── LLM.py                 # 41 行，openai 与 ollama 两个后端
└── template_text.py       # 218 行，提示词模板
```

**注意：R 代码不在包里**。它是 `agent_tool.py` 里用 Python 字符串拼出来的，
运行时写到 CWD 的 `test.R`，再 `os.system('R ... -f test.R')` 执行。

## 构造签名（逐字抄自 `agent_workflow.py:24`）

```python
class MRAgent:
    def __init__(self, mode='O', exposure=None, outcome=None, AI_key=None, model='MR',
                 num=100, bidirectional=False, synonyms=True, introduction=True,
                 LLM_model='gpt-4o', model_type='openai', base_url=None,
                 gwas_token=None, opengwas_mode='online',
                 mr_quality_evaluation=False, mr_quality_evaluation_key_item=None,
                 mrlap=False):
```

```python
class MRAgentOE(MRAgent):
    def __init__(self, mode='OE', *args, **kwargs):
        super().__init__(mode, **kwargs)
```

### 参数语义

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `mode` | `'O'` | `'O'` 疾病当结局找暴露；`'E'` 疾病当暴露找结局（源码里 `outcome = exposure`）；`'OE'` 走 `MRAgentOE` |
| `exposure` / `outcome` | None | `E` 模式只填 `exposure`；`O` 只填 `outcome`；`OE` 两个都填 |
| `AI_key` | None | `model_type='openai'` 时必填 |
| `model` | `'MR'` | `'MR_MOE'` 走混合专家框架，**需额外下载 `rf.rdata`** |
| `num` | 100 | PubMed 抓取文章数，LLM 调用量随它线性上升 |
| `bidirectional` | False | 双向 MR，step9 会多跑反向目录，**时间与开销翻倍** |
| `synonyms` | True | step3 调 UMLS 做同义词扩展（见下方"硬编码 key"） |
| `introduction` | True | step9 生成疾病背景引言 |
| `LLM_model` | `'gpt-4o'` | 同时用作输出目录名的一部分 |
| `model_type` | `'openai'` | `'openai'` 或 `'ollama'`，其他值抛 `ValueError` |
| `base_url` | None | OpenAI 兼容平台的地址 |
| `gwas_token` | None | OpenGWAS JWT，**硬门槛** |
| `opengwas_mode` | `'online'` | `'csv'` 时需 CWD 下有 `opengwas.csv` |
| `mr_quality_evaluation` | False | STROBE-MR 评估，额外 LLM 调用 |
| `mrlap` | False | MRlap 校正，需 ld + hm3 大文件 |

`run(step=None)`：`None` 等于 `[1,2,3,4,5,6,7,8,9,10]`，**step10 无实现**（传了也无害）。

## 输出目录怎么命名

```python
mode == 'OE' -> ./output/<exposure>_<outcome>_<LLM_model>
mode == 'O'  -> ./output/<outcome>_<LLM_model>
mode == 'E'  -> ./output/<exposure>_<LLM_model>
```

是**相对路径**，相对当前工作目录。构造时就 `os.makedirs` 建好。

## 三个中间 CSV（README 写错了，以下是源码实测）

| 文件 | 写入 step | 读取 step | 内容 |
| --- | --- | --- | --- |
| `Exposure_and_Outcome.csv` | step1；step6/7/8 回写 | step2/3/6/7/8/9 | `index, Outcome, Exposure, title, oeID, MRorNot...` |
| `Outcome_SNP.csv` | step3；step5 补 `gwas_id` | step4/5/6/9 | `OE, sID, opengwas, gwas_id` |
| `mr_run.csv` | step8 | step9 | 最终进入 MR 的暴露×结局组合，含 `oeID` |

README 说的 `exposure_and_outcome` / `outcome` / `run` **都不存在**，别去找。

## step 职责

| step | 做什么 | 关键风险 |
| --- | --- | --- |
| 1 | 抓 PubMed（`most recent`，`num` 篇）→ LLM 抽暴露-结局对 | 抽不出实体时大量 `null` |
| 2 | 检索既往 MR 研究 + STROBE-MR 质量评估 → 写 `MRorNot` | 依赖 LLM 判断"是否做过 MR" |
| 3 | 剔除 `MRorNot=='Yes'`，同义词扩展（UMLS） | **全为 Yes 时 `sys.exit(0)` 静默退出** |
| 4 | 判断每个 OE 在 OpenGWAS 里有没有数据 | 写 `opengwas` 布尔列 |
| 5 | 为每个 OE 取 `gwas_id` 列表 | 无有效 token 时这里全空 |
| 6 | 笛卡尔积组合暴露×结局 | 组合数会爆炸 |
| 7 | 人群/种族等过滤 | — |
| 8 | 生成 `mr_run.csv` | **这一步的产物才是"真的要跑 MR"的证据** |
| 9 | 逐组合跑 TwoSampleMR + 出图出报告 | 耗时主体；`bidirectional` 时翻倍 |
| 10 | 无实现 | — |

## R 是怎么被调用的

```python
with open('test.R', 'w', encoding='utf-8') as f:      # 写进当前工作目录
    f.write(r_script_run)
os.system('R --slave --no-save --no-restore --no-site-file --no-environ -f test.R --args')
```

R 脚本里：`Sys.setenv(OPENGWAS_JWT="<token>")`，然后
`library(TwoSampleMR)`、`library(ieugwasr)`、`library(dplyr)`。
出图：`pic.scatterplot.pdf`、`pic.forest.pdf`、`pic.funnel_plot.pdf`、`pic.leaveoneout.pdf`。

## LLM 后端

```python
def llm_chat(text, model_name, AI_key=None, base_url=None, model_type='openai'):
    if model_type == 'openai':
        return openai_gpt(text, AI_key, model_name, base_url)   # seed=42 固定
    elif model_type == 'ollama':
        return ollama_chat(text, model_name)                    # 需要 pip install ollama
    else:
        raise ValueError("Unsupported model type. Please use 'openai' or 'ollama'.")
```

system prompt 固定为 `"You are a helpful biomedical scientist."`。

## 官方依赖（来自 wheel METADATA）

```
Requires-Python: >=3.9
biopython >=1.82,<2.0      bs4 >=0.0.1,<0.0.2
numpy >=1.19.5,<2.0.0      ollama >=0.1.8,<0.2.0
openai >=1.6.1,<2.0.0      pandas >=1.4.2,<2.0.0
pypdf2 >=3.0.1,<4.0.0      reportlab >=4.0.9,<5.0.0
requests >=2.27.1,<3.0.0
```

`numpy<2` + `pandas<2` 是**致命组合**：Python 3.13 上二者都没有预编译 wheel，
必须源码编译（需 gcc + meson），本机做不到 → 只能用 3.11/3.12。
