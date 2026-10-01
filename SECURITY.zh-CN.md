# 安全策略

本项目会接触三类凭据：OpenGWAS JWT（`gwas_token`）、LLM API key、UMLS API key。
它们值钱且一旦泄漏难以回收，所以凭据处理是本项目的第一优先级。

## 一、报告漏洞

**不要开公开 issue。** 请走私密渠道：

| 渠道 | 入口 |
|---|---|
| GitHub 私密咨询 | 仓库页 → Security → *Report a vulnerability*（首选） |
| 邮件 | 见仓库主页 profile 的联系方式 |

报告请包含：受影响版本（`metadata.version`，见 `SKILL.md` frontmatter）、
复现步骤、**实际影响**（尤其是：能否导致凭据外泄 / 路径穿越 / 结果被伪造为成功）。

## 二、凭据规则（硬性）

| 规则 | 原因 |
|---|---|
| 优先通过环境变量传入 | 支持 `--api-key` 的单项工具也接受命令行 key，但命令行可能被 shell history 和 `ps` 记录 |
| 支持的变量名：`MRAGENT_GWAS_TOKEN` / `OPENGWAS_JWT` / `MRAGENT_AI_KEY` / `OPENAI_API_KEY` | 见 `scripts/run_mr.py` |
| 不要把凭据写进 `SKILL.md`、测试用例、issue、日志 | 它们都会进 git |
| 不要把 `output/` 或工作目录整包发出去 | 见下一节——`test.R` 里可能有明文 JWT |

## 三、已知落盘风险与我们的处理

**上游 MRAgent 会把明文 JWT 写进当前工作目录的 `test.R`**：

```r
Sys.setenv(OPENGWAS_JWT="<你的明文 JWT>")   # agent_tool.py: MRtool / MRtool_MOE
```

这不是我们的代码，但工作目录是我们创建的，所以我们在自己这一侧做了收尾：

1. **`scripts/run_mr.py` 任务结束时自动脱敏**。`_redact_workdir()` 会把
   `run.log` 与 `test.R` 里出现的真实 token / key 替换成 `***REDACTED***`，
   并在返回的 JSON 里用 `redacted` 字段列出被改写的文件名。
   （已实测：`test.R` 写入明文 → 任务结束 → 文件中只剩 `***REDACTED***`。）
2. **`tools/export_results.py` 打包时排除 `test.R`**，以及 `*.log` / `*.bak` / `*.tmp`。
   所以下载结果 ZIP 不会带走 `test.R`。
3. **`scripts/run_mr.py` 的 stdout 输出对凭据脱敏**，字段值显示为 `***set***`，
   只表明"已设置"，不含内容。进程输出全部重定向进 `run.log`，不污染 stdout。

### 仍然存在的边界（我们改不了上游）

- 如果 MRAgent 进程被 `kill -9`，`finally` 不执行，脱敏就跑不到。
  这种情况下请手动删除工作目录下的 `test.R`。
- `_redact_workdir()` 只处理 `run.log` 与 `test.R` 两个已知落盘点，
  不递归扫 `output/`（里面可能有上百 MB 图表，为脱敏全读一遍不划算）。
  若上游未来把凭据写进别的文件，这里需要同步补。
- `--no-exclude` 会关掉打包时的排除规则。**加上它就可能把 `test.R` 打进 ZIP，
  除非你确认已脱敏。**

## 四、UMLS key

上游 MRAgent 在完整流程中硬编码了 UMLS API key，且目前没有参数允许调用方替换。
本项目不复制这把 key；`run_mr.py` 默认关闭同义词扩展。
若显式传入 `--synonyms`，上游包仍会使用自己的内置 key。请先确认你接受这一行为；
更稳妥的选择是保持默认关闭。独立工具 `tools/mr_synonyms.py` 只接受用户自己的
`UMLS_API_KEY` / `--api-key`，不会回退到上游 key。

## 五、其他

- **`--tag` 做过消毒**：`../../evil` 会被改写成 `_______evil`，防止路径穿越。
  新增任何拼接路径的参数时，必须走同样的消毒。
- 本项目不收集、不上传任何数据；所有网络访问只到 PubMed /
  OpenGWAS / UMLS / 用户自配的 LLM 端点。
