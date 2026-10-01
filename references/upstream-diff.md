# 上游 MRAgent vs 本技能：完整比对

比对时间 **2026-10-01**（第二轮复核）。
对象：`github.com/xuwei1997/MRAgent` main 分支 + PyPI `mragent==0.2.5`。
本技能版本：**1.2.0**，自检 **97 条用例全绿**。

---

## 一、比对方法（可复现）

1. `git clone --depth 1 https://github.com/xuwei1997/MRAgent.git`
2. `pip download mragent==0.2.5 --no-deps` 取 wheel
3. 对 `mragent/` 下 6 个 `.py` 做**逐字节**比对（含行尾归一化）
4. 用 `ast` 解析上游源码，提取全部顶层函数/方法与提示词常量
5. 对每个上游端点发真实 HTTP 请求，核实其**当前是否还能用**
6. 本技能侧逐个入口实跑，断言退出码 + stdout JSON 合法性

## 二、核心库：归一化行尾后**逐字节一致**

```
__init__.py            raw:CRLF  wheel:LF  lf-normalized:IDENTICAL
LLM.py                 raw:CRLF  wheel:LF  lf-normalized:IDENTICAL
agent_tool.py          raw:CRLF  wheel:LF  lf-normalized:IDENTICAL
agent_workflow.py      raw:CRLF  wheel:LF  lf-normalized:IDENTICAL
agent_workflow_OE.py   raw:CRLF  wheel:LF  lf-normalized:IDENTICAL
template_text.py       raw:CRLF  wheel:LF  lf-normalized:IDENTICAL
```

字节差异**只**来自本机 `core.autocrlf=true` 在克隆时把 LF 转成 CRLF。
结论：GitHub 版与 pip 版行为相同，不存在"两个版本"。

---

## 三、上游文件清单 → 覆盖度（逐文件）

上游共 30 个文件（不含 `.git`）。逐项处理如下：

| 上游文件 | 是什么 | 本技能 |
| --- | --- | --- |
| `mragent/agent_workflow.py` | 主类 `MRAgent`，1037 行 / 30 个方法 | 经 `scripts/run_mr.py` 编排调用 |
| `mragent/agent_workflow_OE.py` | `MRAgentOE`，19 行，只重写 step1 | `run_mr.py --mode OE` |
| `mragent/agent_tool.py` | 709 行，爬虫 / GWAS / R 调用 / UMLS | 拆成 `mr_pubmed` / `mr_gwas` / `mr_synonyms` 等 |
| `mragent/LLM.py` | 41 行，openai / ollama 封装 | `tools/mr_llm.py`（原生重写） |
| `mragent/template_text.py` | 218 行，**10 个提示词模板** | `tools/mr_prompt.py` + `tools/prompts.json` |
| `mragent/__init__.py` | 导出 `MRAgent` / `MRAgentOE` | 未改动调用方式 |
| `opengwas.csv` | 10.3 MB / 50044 行离线清单 | `mr_gwas.py --mode csv`；由 `install.py` 下到全局缓存 |
| `web_demo.py` | 487 行 Streamlit 界面 | `tools/serve_web.py` |
| `agent_workflow_demo.py` | 知识发现 demo | 参数并入 `run_mr.py` |
| `agent_workflow_OE_demo.py` | 因果验证 demo | `run_mr.py --mode OE` |
| `step_1_test_out.py` | step1 抽取 + 多模型对比 | `mr_pubmed.py` + `mr_bench.py` |
| `step_2_test.py` | step2 MRorNot **准确率** | `mr_bench.py --mode accuracy` |
| `step_2_test_STROBE_MR.py` | STROBE-MR 评估准确率 | `mr_eval.py --strobe` + `mr_bench.py` |
| `step_5_test.py` | step5 GWAS 选择**查准/查全/F1** | `mr_bench.py --mode prf` |
| `step_9_test_out.py` | step9 结果解释 | `summarize_output.py` |
| `step_9_test_prompt.py` | **415 行 / 12 个提示词消融变体** | ✅ 本轮新增：`mr_prompt.py` |
| `step_1_test_SimCSE.py` | SimCSE 语义相似度 | ⚠️ 未纳入（见第八节） |
| `step_9_test_SimCSE.py` | SimCSE 语义相似度 | ⚠️ 未纳入（见第八节） |
| `key.py` | **上游没有这个文件**，但 3 个脚本 import 它 | 本技能补 `key.py.example` |
| `pyproject.toml` | 依赖与元数据 | 依赖版本已核实，写进 `references/environment.md` |
| `LICENSE` | Apache-2.0 | 本技能 MIT + `NOTICE` 归属声明 |
| `images/`、`.idea/` | 论文配图 / IDE 配置 | 无关（`.idea/` 本不该入库） |
| `.gitignore` | **上游没有** | 本技能有，且覆盖运行产物与凭据 |

---

## 四、编排层能力对照（`MRAgent` 类 30 个方法）

| 上游方法 | 本技能入口 | 状态 |
| --- | --- | --- |
| `__init__`（全部超参） | `run_mr.py` 的 CLI 参数 | ✅ |
| `define_path` | `run_mr.py` 独立工作目录 | ✅ 且修掉了并发互踩 |
| `step1` 扫 PubMed 抽暴露-结局对 | `run_mr.py --steps 1` + `mr_pubmed.py` | ✅ |
| `outcome_exposure_MRorNot` | `mr_eval.py --mrornot` | ✅ |
| `STROBE_MR` | `mr_eval.py --strobe` | ✅ |
| `step2` | `run_mr.py --steps 2` | ✅ |
| `step3` 同义词 + GWAS 命中 | `run_mr.py --steps 3` + `mr_synonyms` + `mr_gwas` | ✅ |
| `opengwas_df` / `opengwas_list` / `check_keyword_in_opengwas_csv` | `mr_gwas.py --mode csv` | ✅ |
| `step4` | `run_mr.py --steps 4` | ✅ |
| `get_gwas_id_csv` / `step5_get_gwas_id` / `step5` | `mr_gwas.py` + `run_mr.py --steps 5` | ✅ |
| `step6` / `step7` / `step8` | `run_mr.py --steps 6,7,8` | ✅ |
| `LLM_MR_result` / `LLM_MR_result_PDF` | `run_mr.py --steps 9` | ✅ |
| `mrlap_result_text` | `--mrlap` | ✅ |
| `LLM_Introduction` / `LLM_Introduction_PDF` | `--no-introduction` 反向开关 | ✅ |
| `LLM_conclusion` | `run_mr.py --steps 9` | ✅ |
| `step9_mrlap` / `step9_run_mr_LLM` / `step9_gwas_poppulation` / `step9` | `run_mr.py --steps 9` | ✅ |
| `run(step=[...])` | `run_mr.py --steps` | ✅ |
| `MRAgentOE.step1` | `run_mr.py --mode OE` | ✅ |
| — | `run_mr.py --mode auto`（自动推断） | 本技能新增，对齐上游 web 行为 |

全部超参映射：`bidirectional` / `synonyms` / `introduction` / `mr_quality_evaluation` /
`mr_quality_evaluation_key_item` / `mrlap` / `model='MR'\|'MR_MOE'` /
`opengwas_mode` / `num` / `base_url` / `model_type` / `LLM_model` —— 逐个都有对应开关。

---

## 五、原子能力层对照（`agent_tool.py` + `LLM.py`）

| 上游函数 | 行号 | 本技能入口 | 依赖 | 状态 |
| --- | --- | --- | --- | --- |
| `pubmed_crawler` | 30 | `mr_pubmed.py --keyword` | **无** | ✅ 原生重写 |
| `get_paper_details` | 92 | `mr_pubmed.py --details` | **无** | ✅ 原生重写 |
| `get_paper_details_pmc` | 221 | `mr_pubmed.py --details --pmc` | **无** | ✅ 原生重写 |
| `check_keyword_in_opengwas` | 168 | `mr_gwas.py --mode online` | JWT | ⚠️ 上游已失效，见第七节 |
| `get_gwas_id` | 195 | `mr_gwas.py --mode online` | JWT | ⚠️ 上游已失效，见第七节 |
| `get_synonyms` | 675 | `mr_synonyms.py` | 自己的 UMLS key | ✅ 原生重写 |
| `MRtool` | 261 | `run_mr.py` step9 触发 | R | ✅ |
| `MRtool_MOE` | 386 | `--model MR_MOE` | R | ✅ |
| `MRtool_MRlap` | 487 | `--mrlap` | R + 大文件 | ✅ |
| `openai_gpt` / `ollama_chat` / `llm_chat` | LLM.py | `mr_llm.py` | **无** | ✅ 原生重写 |
| `timer` 装饰器 | 16 | — | — | 仅计时，无功能价值 |

**本轮变化**：`mr_pubmed` / `mr_synonyms` / `mr_llm` 三个工具从"包装 mragent"改为
**原生实现**。理由：这三个能力本就是公开 REST 接口（NCBI E-utilities / UMLS / OpenAI），
被迫依赖整个 mragent 会让它们在没装 mragent 的机器上完全不可用。
现在本机（无 mragent、无 R）能直接跑的工具有
`preflight` / `run_mr --dry-run` / `summarize_output` / `mr_pubmed` / `mr_gwas` /
`mr_synonyms` / `mr_llm` / `mr_bench` / `mr_prompt` / `export_results` / `edit_csv`。

---

## 六、提示词库（本轮新增能力）

上游把提示词硬编码在源码里，用户只能改源码。本技能把它们全部拆出来做成可调用工具：

| 组 | 数量 | 内容 |
| --- | --- | --- |
| `main` | **10** | `template_text.py` 的全部主模板 |
| `step9_ablation` | **12** | `step_9_test_prompt.py` 的 6 个变体 × 2 个模型 |

主模板清单：

| 模板 | step | 用途 | 占位符 |
| --- | --- | --- | --- |
| `MRorNot_text` | step2 | 判定某对是否已做过 MR | Exposure / Outcome / pubmed_out |
| `pubmed_text` | step1 | 批量喂文献抽暴露-结局对 | Outcome / num / pubmed_out |
| `pubmed_text_obo` | step1 | **逐篇**喂文献（step1 实际用这个） | Outcome / title / abstract |
| `synonyms_text` | step3 | 生成医学同义词 | OE |
| `gwas_id_text` | step5 | 挑最合适的 GWAS ID | keyword / json_list |
| `LLM_MR_template` | step9 | 解读 MR 结果（MR 模式） | 7 个 |
| `LLM_MR_MOE_template` | step9 | 解读 MR 结果（MR_MOE） | 7 个 |
| `LLM_conclusion_template` | step9 | 生成结论段 | Exposure / Outcome / MRresult |
| `LLM_Introduction_template` | step9 | 生成疾病引言 | 5 个 |
| `LLM_template_MR_effect_evaluation` | step2 | STROBE-MR 质量评估（8109 字符，最长） | paper_details |

step9 消融变体（6 组 × 2 模型）：

| 变体 | 含义 |
| --- | --- |
| `zero_shot` | 完全无知识，直接让它读表 |
| `few_knowledge` | 告诉它 IVW p<0.05 与 OR 方向的含义 |
| `one_shot` | 给一份参考范例 |
| `one_shot_and_knowledge` | 范例 + 知识 |
| `zero_shot_CoT` | 零样本思维链 |
| `zero_shot_CoT_and_knowledge` | 思维链 + 知识 |

**一个实测发现**：`LLM_MR_template`（2438 字符）与
`LLM_MR_template_one_shot_and_knowledge`（2438 字符）**内容完全相同** ——
即上游正式使用的那条 step9 提示词，本身就是消融实验里"最丰富"的那一档。

一致性由自检 `I2` 保证：**10/10 与上游源码逐字比对一致**。

---

## 七、⚠️ 上游当前已失效的功能（本轮最重要的发现）

### 7.1 在线 GWAS 查询已经不能用

上游 `check_keyword_in_opengwas`（agent_tool.py:168）与 `get_gwas_id`（:195）
的做法是**爬 `gwas.mrcieu.ac.uk` 的 HTML 表格**：

```python
url = f"https://gwas.mrcieu.ac.uk/datasets/?trait__icontains={keyword}"
if "Filtered to 0 records" in soup.text:   # ← 用这个字符串判断"有没有数据"
    return False
table = soup.find('table')                 # ← 再抓表格
```

2026-10-01 实测该页面已改成前端渲染，服务端返回的表格里只剩一行
`Failed to load batches data.`。关键证据：

| 探测 | 结果 |
| --- | --- |
| 关键词 `body mass index` | 页面**不含** `Filtered to 0 records` |
| 关键词 `zzz_no_such_trait_zzz`（乱码） | 页面**同样不含**该字符串 |
| 表格行 | 只有 1 行：`Failed to load batches data.` |
| `<td>` 总数 | 5（没有数据集行） |

后果：
- `check_keyword_in_opengwas()` 对**任何**关键词都返回 `True` —— 永远说"有数据"；
- `get_gwas_id()` 返回由报错行拼出的垃圾记录，或 `table` 为 `None` 时直接 `AttributeError`；
- 更糟的是它**不报错**，step5 会把垃圾 `gwas_id` 一路写进 `Outcome_SNP.csv`。

**本技能的处理**：不复刻这个已失效的爬虫（自检 `I7` 断言代码里不出现该调用），
改为走 OpenGWAS 官方鉴权 API `GET https://api.opengwas.io/api/gwasinfo`（Bearer JWT）。
实测该端点无 token / 假 token 均返回 **HTTP 401**，证明鉴权是唯一门禁、
请求本身构造正确（自检 `E8`/`E9` 覆盖这两条路径）。

**没有 JWT 怎么办**：用 `--mode csv` 走离线清单 —— 这正是目前**唯一稳定**的检索途径。

### 7.2 上游 3 个脚本 clone 下来直接跑必然报错

```
step_2_test_STROBE_MR.py :  from key import AI_key
step_9_test_out.py       :  from key import mr_key
step_9_test_prompt.py    :  from key import AI_key, mr_key
```

而仓库里**没有 `key.py`**，也没有 `.gitignore` 去排除它：

```
$ ls key.py        → 不存在
$ ls .gitignore    → 不存在
$ ls .idea/        → 有（且已被提交）
```

即：`ModuleNotFoundError: No module named 'key'`。
本技能补了 `key.py.example`（模板，无真实凭据），并把 `key.py` 加进 `.gitignore`。

### 7.3 硬编码的第三方凭据与个人信息

上游源码里直接写着别人的东西，公开发布前作者显然没清理：

| 内容 | 位置 |
| --- | --- |
| `670****44@qq.com` | `agent_tool.py` —— `pubmed_crawler` 里的 NCBI 联系邮箱 |
| `xuwei_***@foxmail.com` | `agent_tool.py` ×2（`get_paper_details` / PMC）+ `pyproject.toml` 作者邮箱 |
| `d6382a8b-****-****-****-************` | `agent_workflow.py:302` —— **UMLS API key**，硬编码 |
| `https://api.gpt.ge/v1/` | 三个 demo / 测试脚本里的第三方中转 base_url |

对使用者的实际影响：

1. **别人的邮箱被当成你的**去请求 NCBI，你的限流额度可能被别人用掉，反之亦然。
   本技能的 `mr_pubmed.py` 改用 `NCBI_EMAIL` 环境变量，没设就只提示、不冒用。
2. **UMLS key 是作者的**。用它跑同义词扩展，等于蹭别人的配额；
   那个 key 哪天被吊销，你的流程会突然在某一步开始静默返回空同义词列表。
   本技能的 `mr_synonyms.py` **只接受你自己的 key**。
3. `api.gpt.ge` 是第三方中转，不是 OpenAI 官方。demo 里把它设成默认
   `base_url` 意味着**默认把 prompt 发给一个非官方中转**。
   本技能默认走官方 `https://api.openai.com/v1`，要用中转必须显式 `--base-url`。

---

## 八、本技能比上游多出来的（上游完全没有的能力）

| 能力 | 为什么需要 |
| --- | --- |
| `preflight.py` 环境体检 | 上游装不上就一路报错到底；这里先探测再决定怎么跑 |
| `summarize_output.py` | 上游只能自己翻 CSV |
| **stdout 只放 JSON 的契约** | 上游 CLI 直接 print，程序无法解析 |
| **fd 级日志重定向** | 只重定向 `sys.stdout` 抓不到 R 的原生输出，必须 `os.dup2` |
| **静默失败捕获** | 上游 step3 判定"都做过 MR"后 `sys.exit(0)`，进程显示成功但一个 MR 没跑 |
| **独立工作目录** | 上游把 `test.R` 和 `./output` 写进 CWD，两个任务并行会互踩 |
| **工作目录脱敏** | 上游把明文 JWT 写进 `test.R`（`Sys.setenv(OPENGWAS_JWT=...)`），
而工作目录是要打包分享的；本技能收尾时替换成 `***REDACTED***` |
| **参数契约**（exit 2 + 结构化 JSON） | 上游脚本缺参数时抛 Usage 到 stderr，调用方拿不到可解析结果 |
| **`mr_prompt.py` 提示词库** | 上游提示词只能改源码 |
| **`key.py.example`** | 上游那 3 个脚本缺这个文件根本跑不起来 |

---

## 九、未纳入项（明确声明，不装作覆盖了）

| 项 | 原因 |
| --- | --- |
| `step_1_test_SimCSE.py` / `step_9_test_SimCSE.py` | 依赖 `SimCSE` 预训练模型（`princeton-nlp/unsup-simcse-*`，下载约 1.3 GB）+ 论文实验标注数据。属于**论文复现环境**而非生产能力。如确需，按上游脚本单独跑即可。 |
| 生成真实 MR 结果数字 | 本机无 R / 无 Docker / WSL 被拦。预检会如实报阻塞，**不编造任何统计结果**。 |
| **SMR（Summary-data-based MR）/ HEIDI** | **上游 MRAgent 本身就没有这个功能**，不是本技能的遗漏。见下方说明。 |

### 关于 SMR：不在 MRAgent 的能力范围内

**上游 MRAgent 没有 SMR 分析功能，本技能因此也没有** —— 这是能力面对齐，不是遗漏。

SMR（Summary-data-based Mendelian Randomization，Zhu et al. 2016, *Nature Genetics*）
是 Yang lab（西湖大学）的另一套方法，与 MRAgent 用的 TwoSampleMR **不是同一条技术路线**：

| 维度 | MRAgent（TwoSampleMR） | SMR |
| --- | --- | --- |
| 数据输入 | OpenGWAS 上任意暴露 / 结局的 GWAS summary data | 同一套 LD panel 下的 **GWAS summary + 分子 QTL** summary |
| 分子 QTL | 不需要 | 必须，格式为 `.besd` + `.esi`（Binary eQTL Summary Data） |
| LD 参考面板 | 由 OpenGWAS API 侧做 `ld_clump` | **必须自备** `.ld` / `.bim` / `.fam`（1000G 或 UKB） |
| 核心检验 | IVW / MR-Egger / weighted median / simple & weighted mode，外加多效性与异质性检验 | **SMR 检验**（`b_SMR`）+ **HEIDI 检验**（区分连锁不平衡 vs 水平多效性） |
| 实现 | R 包 `TwoSampleMR` | 独立命令行 **`smr`**（C++），或 R 包 `smr` |
| 主要用途 | 表型 → 表型 的因果推断 | **基因 / 分子表型 → 复杂疾病** 的因果基因定位 |

逐处核对过的依据：

- 上游 `mragent/agent_tool.py` 只有三个分析函数：
  `MRtool`（标准 TwoSampleMR，第 261 行）、`MRtool_MOE`（第 386 行）、
  `MRtool_MRlap`（第 487 行）—— **没有任何 SMR 相关代码**。
- 提示词库 `template_text.py` 与 `step_9_test_prompt.py` **没有 SMR 模板**，
  只有 `LLM_MR_template` / `LLM_MR_MOE_template` / `mrlap_result_text` 等。
- 上游 `README.md` / `pyproject.toml` 也未声明 SMR 依赖。
- 全仓库搜 `SMR`，仅命中 `opengwas.csv` 里的 `eQTLGen` 等**数据集名称**，
  以及 `STROBE_MR`（MR 报告规范，与 SMR 无关）。

**若确需 SMR**，那是**新增能力**而非"补齐遗漏"，需要：装 `smr` 命令行工具 +
下载 1000G LD reference + 取得 `.besd` 格式的 QTL 数据（如 eQTLGen / GTEx 转换版）。
可作为独立工具（例如 `tools/mr_smr.py`）另行扩展，与本技能"复刻上游"的定位分开。

---

## 十、验证证据

| 验证 | 结果 |
| --- | --- |
| 自检用例 | **97 条，全绿** —— 工作区与 5 个安装位（Claude Code / WorkBuddy / CodeBuddy / Codex / DeepSeek Harness）各跑一遍 |
| 主模板与上游逐字一致 | **10/10 一致**（自检 I2，AST 解析比对） |
| `mr_llm` 线上请求形状 | 本地起 OpenAI 兼容 mock 服务真发请求：路径 / Bearer / `seed=42` / system prompt 全部与上游一致（自检 I9） |
| `mr_synonyms` 真实 UMLS | 假 key → 真实返回 **HTTP 401**，被转成结构化错误 |
| `mr_gwas` online 真实 API | 无 token → exit 2 + 说明；假 token → 真实 **HTTP 401** |
| `mr_pubmed` 真实 NCBI | esearch + efetch 真实联通，解析出标题与摘要 |
| 离线 GWAS | 50044 行清单检索命中，中文/特殊字符不炸 |

本机实测能跑通的入口：**11 个**（见第五节末）；
因缺凭据/依赖而返回结构化阻塞的入口：`mr_eval`（需 mragent）、
`serve_web`（需 streamlit）、以及需要各自 key 的在线路径。
**没有任何入口是"因为技能本身写错而跑不了"的。**
