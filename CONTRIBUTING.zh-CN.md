# 贡献指南

感谢你想改进它。先读完这一页，再动手 —— 这里有两条约束是拿血泪换来的。

## 项目定位

一个把 MRAgent 包装成 **Agent Skill + 工具包** 的项目：
`scripts/` 管流程编排，`tools/` 管原子动作，`references/` 存事实。
它不重新实现任何统计算法 —— TwoSampleMR 怎么算，由上游的 R 包决定。

## 两条硬约束

### 1. 不许静默失败

「失败被上报为成功」是本项目最不能接受的一类缺陷。已经真实发生过：

- **step3 的 `sys.exit(0)`**：上游在"所有暴露-结局对都已做过 MR"时直接退出，
  退出码是 0，但**一个 MR 都没跑**。所以判成败必须看 `mr_run.csv` 是否存在，
  **永远不要用退出码判断**。
- **stdout 被污染**：MRAgent 与 R 会往 stdout 狂写输出（实测污染 90+ 行），
  导致调用方 JSON 解析失败。已用 `os.dup2` 在**文件描述符层**重定向进 `run.log`。
  注意：只重定向 `sys.stdout` 抓不到 R 的输出，因为 R 走的是 fd 层。

新增脚本时，遇到可选能力不可用，必须在返回值里留下**可观测的错误字段**，
而不是返回一个看起来正常的成功。

### 2. 契约：stdout 只放 JSON

所有脚本：

- 正常路径与**错误路径**都输出合法 JSON（缺参数、缺依赖也一样，退出码 2）；
- 人类可读提示走 stderr；
- 凭据字段脱敏为 `***set***`，绝不回显原文；
- 缺参数不能用 argparse 默认的 usage 报错（那不是 JSON）——
  统一用 `_common.parse_args_or_fail()`。

`scripts/selftest.py` 会逐条断言这些契约。改完必须全绿。

## 环境要求

- **推荐 Python 3.11 或 3.12**（CI 覆盖版本）。预检接受 3.9–3.12，但上游排除
  3.9.7；3.9/3.10 未纳入 CI。Python 3.13+ 当前被预检拦截，原因是上游
  `numpy<2` / `pandas<2` 组合在本项目已测环境没有可用 wheel。
- 完整跑 MR 还需要 **R > 4.3.4** 与 6 个 R 包。
  只改工具层的话不需要 —— 离线检索 / 打包 / CSV 编辑 / 评测四类工具
  **不依赖 mragent**，在本机（无 R、无 Docker）就能开发与验证。

## 开发流程

```bash
python scripts/selftest.py          # 全量自检（118 条）
python scripts/selftest.py --quick  # 只跑不依赖 mragent 的用例
python install.py --target all      # 装到 Claude Code + WorkBuddy 并冒烟
```

提交前请确认：

1. `selftest.py` 全绿；
2. 没有把 `token` / `key` / 真实 GWAS ID 硬编码进去；
3. `opengwas.csv`（10 MB）**不要**提交 —— 它在 `.gitignore` 里；
4. 文档里写的命令**真的跑过**。上一版 `SKILL.md` 里 `——keyword` 被写成了
   全角破折号，复制出去根本执行不了，这类错误只有实跑才能发现。

## 改 `references/` 时的要求

`references/api.md` 里的签名是**从源码实测**的，不是 README 转述 ——
README 里 `outcome` / `run` 两个文件名就是错的，真实名字是
`Outcome_SNP.csv` / `mr_run.csv`。

**任何写进 `references/` 的事实，都要能从源码或一次真实执行里复现。**
不确定的就标注"未验证"，不要猜。

## 提交信息

- subject 用 Conventional Commits 前缀（`fix:` / `feat:` / `perf:` / `docs:` / `test:`）
- body 写中文，讲清三件事：**改了什么 / 为什么改（原来错在哪）/ 影响范围**
