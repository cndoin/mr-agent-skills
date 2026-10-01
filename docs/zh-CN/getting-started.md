# 快速开始

本指南先运行文献发现步骤，让你复核候选组合，再继续 MR 分析。

## 环境要求

- 推荐 Python 3.11 或 3.12，CI 覆盖这两个版本。预检接受 Python 3.9–3.12（排除 3.9.7）；3.9/3.10 未纳入 CI，当前拦截 3.13 及以上版本。
- R 4.3.4 及以上，以及 [`../../references/environment.md`](../../references/environment.md) 中列出的 R 包。
- 上游 `mragent` 包和受支持的 LLM 后端。
- 将 OpenGWAS JWT 设置到 `MRAGENT_GWAS_TOKEN` 或 `OPENGWAS_JWT` 环境变量。

技能安装器只复制技能文件，不会替你安装 Python、R 或 MRAgent 依赖。

## 安装技能

```bash
python install.py --target all
```

可用 `--target claude`、`--target workbuddy` 或 `--target codebuddy` 选择目标。`python install.py --list` 只检查技能元数据，不安装。

## 配置环境

创建 Python 3.11 或 3.12 环境，安装 `mragent==0.2.5`，安装并配置所需 R 包，再通过环境变量设置凭据。各平台命令请看 [`../../references/environment.md`](../../references/environment.md)。不要将真实凭据粘贴到命令行、源码或公开 issue。

运行预检，确认环境就绪后再消耗 LLM 或 API 配额：

```bash
python scripts/preflight.py --no-network
```

报告会标出阻塞项，不会输出凭据值。

## 先发现，再复核

先预览模式和参数：

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
```

运行文献发现步骤：

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2
```

检查运行目录中的 `Exposure_and_Outcome.csv`，必要时编辑暴露—结局组合，再运行后续步骤：

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 3,4,5,6,7,8,9
python scripts/summarize_output.py ./mragent-runs/back_pain_O_*/output
python tools/export_results.py ./mragent-runs/back_pain_O_*/output
```

每次真实运行都会创建新的工作目录；`--dry-run` 不会创建目录。运行器会捕获日志，并检查是否生成 `mr_run.csv`，而不是单看进程退出码。

## 选择模式

| 模式 | 必需输入 | 用途 |
| --- | --- | --- |
| `O` | `--outcome` | 为结局发现候选暴露 |
| `E` | `--exposure` | 为暴露发现候选结局 |
| `OE` | `--exposure` 和 `--outcome` | 验证指定的一对 |

## 同义词扩展

UMLS 同义词扩展默认关闭。上游 MRAgent API 内置了 UMLS key，当前运行器无法将它替换为用户自己的 key。显式传入 `--synonyms` 会启用上游行为。独立工具 `tools/mr_synonyms.py` 则要求你提供自己的 `UMLS_API_KEY`。

## 谨慎解读结果

MR 结果受工具变量有效性、研究设计、样本重叠和数据可用性影响。请结合数据集和诊断结果进行专家复核。输出属于研究证据，不是临床建议，也不是因果关系的证明。

## 更多说明

- [`references/api.md`](../../references/api.md) — 构造参数和步骤
- [`references/pitfalls.md`](../../references/pitfalls.md) — 上游已知问题
- [`references/environment.md`](../../references/environment.md) — 环境搭建
- [`SECURITY.md`](../../SECURITY.md) — 凭据和已知风险
