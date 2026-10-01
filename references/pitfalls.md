# 坑位清单（全部来自源码，非推测）

读 `mragent==0.2.5` 源码时发现的问题，按"会让你白跑多久"排序。

## P0 · 跑了但等于没跑

### 1. step3 静默 `sys.exit(0)`

`agent_workflow.py:274-276`：

```python
if df.empty:
    print('There is no MR studies')
    sys.exit(0)
```

当 step2 把所有暴露-结局对都判成 `MRorNot='Yes'`（既往已做过 MR）时，
step3 直接退出，**退出码 0**，看起来像成功，但一个 MR 都没跑。

**判成败只看 `mr_run.csv` 是否存在**，不要用退出码。`scripts/run_mr.py` 已经
捕获 `SystemExit` 并给出 warning，`scripts/summarize_output.py` 也会把
"缺 mr_run.csv" 标成 `ok: false`。

### 2. `gwas_token` 无效 → step5 之后全空

R 侧靠 `Sys.setenv(OPENGWAS_JWT=...)` 注入。token 缺失/过期时不会在 Python 侧抛错，
而是 R 里静默返回空，最终 `gwas_id` 一列全是 `nan`，step9 拿不到组合。

**检查点**：step5 后看 `Outcome_SNP.csv` 的 `with_gwas_id` 计数（summarize 脚本会报）。

### 3. Python 3.13 装不上

`numpy<2` + `pandas<2` 无 cp313 wheel → 源码编译 → 本机无 gcc → `metadata-generation-failed`。
**用 3.11/3.12 venv**。这是最容易在第一步就浪费半小时的坑。

## P1 · 结果张冠李戴

### 4. 中间产物写在当前工作目录

```python
with open('test.R', 'w', encoding='utf-8') as f:   # 相对路径，写 CWD
    ...
os.system('R --slave ... -f test.R --args')
```

`./output/` 和 `test.R` 都相对 CWD。**两个分析并发跑会互相覆盖**。
`scripts/run_mr.py` 强制每个任务一个独立目录并 `chdir` 进去 —— 别绕过它直接调 `MRAgent`。

### 5. README 的文件名是错的

README 说输出目录下有 `exposure_and_outcome`、`outcome`、`run` 三个表。
源码里实际是 **`Exposure_and_Outcome.csv` / `Outcome_SNP.csv` / `mr_run.csv`**。
按 README 去找会一无所获。

### 6. 输出目录名带模型名

```python
mode=='O'  -> ./output/<outcome>_<LLM_model>
mode=='OE' -> ./output/<exposure>_<outcome>_<LLM_model>
```

换模型会换目录，别以为结果丢了。

## P2 · 脆弱与外部依赖

### 7. UMLS API key 硬编码在包里

`agent_workflow.py:302`：

```python
python_list = get_synonyms(OE, "<上游包内置 key>")
```

上游 `MRAgent` 类的 `synonyms=True` 默认值会调用这个硬编码 key；本技能运行器
显式将其默认设为 `False`。该 key 可能被限流或失效。

**处置**：保持本技能默认关闭。完整流程显式使用 `--synonyms` 才会让上游包调用
其内置 key；独立 `mr_synonyms.py` 工具则要求你提供自己的 UMLS key。

### 8. `opengwas_mode='csv'` 要求 CWD 下有 `opengwas.csv`

`agent_workflow.py:321` 硬编码 `opengwas_path = 'opengwas.csv'`。
切到 csv 模式前先确认文件在位，否则 `FileNotFoundError`。

### 9. step9 用 `eval()` 解析 gwas_id

```python
Outcome_id_list = eval(Outcome_id)   # 把 "[...]" 字符串转 list
```

数据来自 R 输出，风险可控，但只要格式稍变就炸，且异常信息很难懂。
看到 `SyntaxError` / `NameError` 出现在 step9，先怀疑这里。

### 10. `global snp_path` 跨方法共享状态

`step9` 里 `global snp_path` 被多个方法读写。分步运行时若顺序/上下文不同，
可能读到上一次的残留值。**分步执行务必按 1→2→…→9 的顺序**。

### 11. LLM 输出靠正则抠 JSON

```python
if '[' in gpt_out and ']' in gpt_out:
    gpt_out = gpt_out.split('[')[1].split(']')[0]
```

模型一旦不按格式输出（比如先说两句话再给 JSON），抽取就退化成
`[{"Outcome": null, "Exposure": null}]`。表现为 `Exposure_and_Outcome.csv` 里大量空行。
**处置**：换更强模型，或调大 `num` 让有效样本变多。

## P3 · 成本与规模

### 12. `bidirectional=True` 让 step9 翻倍

每个组合多跑一遍反向 MR，目录也多一套 `<Outcome>_<Exposure>/`。时间和 LLM 开销 ×2。

### 13. 笛卡尔积爆炸

step6 对暴露×结局做笛卡尔积，step9 再对 `gwas_id` 列表做笛卡尔积。
`synonyms=True` 会同义词膨胀，`num` 调大会让实体数上升 —— **三层相乘**。
先用 `--steps 1,2` 看规模，再决定要不要全量跑。

### 14. step10 是空实现

`run(step=None)` 默认带 `[1..10]`，但 step10 没有任何实现，传了不报错也不做事。

## 顺带一提

上游 `synonyms` 默认 `True` 且依赖外部 UMLS；本技能运行器覆盖为关闭。
`introduction` 默认 `True` 且额外消耗 LLM 调用。想省钱省时间时加
`--no-introduction`。

## 补记（第二轮比对上游仓库后发现）

### 15. `opengwas.csv` 里的非 ASCII 被写成了 `<U+XXXX>` 字面文本

上游仓库自带的离线清单里，作者名长这样：`Fern<U+00E1>ndez-Rhodes L` ——
不是编码问题，是**源文件里就是这个字面字符串**（已核对原始字节确认）。

影响：用含重音符号的词去匹配 `trait` 列会匹配不上。
**处置**：离线检索时尽量用 ASCII 写法；命中异常时改用 `mr_gwas.py --mode csv`
配更短的关键词，或走在线模式。

### 16. `web_demo.py` 不在 PyPI 包里

`pip install mragent` 之后**没有** Web 界面 —— 它只存在于 GitHub 仓库。
想用界面必须先有仓库副本，见 `mr_gwas.py --fetch` 的同源思路，或直接
`git clone` 后用 `tools/serve_web.py` 拉起。

另外：`mrlap` 与 `mr_quality_evaluation` 两个开关在 Web 界面里是
`disabled=True`（作者禁用了），**只有 CLI 能用**。

### 17. 上游 CLI 会把输出直接吐到 stdout

上游的 `agent_workflow_demo.py` 直接 `agent.run()`，海量 print 混在 stdout 里，
程序无法解析。Web 版靠 `CaptureOutput` + patch `os.system` 绕开。
本技能的 `run_mr.py` 用 `os.dup2` 在 fd 层重定向解决，见 SKILL.md 末尾。

### 18. 评测脚本写死了数据文件

`step_2_test.py` 读 `MR40.csv`、`step_5_test.py` 读 `gwas_test.csv`，
文件名与模型列名都硬编码。本技能的 `mr_bench.py` 把这些改成参数化的
`--file / --gt / --pred`，可一次对比多个模型列。

### 19. 克隆上游仓库会踩 CRLF

本机 `core.autocrlf=true`，`git clone` 后 `mragent/` 下的 .py 会变成 CRLF，
与 wheel 里的 LF 逐字节不同（但归一化后内容一致，见 `upstream-diff.md`）。
别因为这个误判"GitHub 版和 pip 版不一样"。
