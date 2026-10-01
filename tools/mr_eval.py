#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：LLM 判定类能力（是否做过 MR / STROBE-MR 质量评估）。

对应上游 `MRAgent.outcome_exposure_MRorNot`（step2 的核心）与
`MRAgent.STROBE_MR`（STROBE-MR 质量评估）。

这两个都是 MRAgent 的**实例方法**，无法脱离实例直接调用，所以本工具会
在独立临时目录里构造一个最小实例再调方法 —— 构造过程会建 output 目录并
打印日志，因此和 run_mr.py 一样做 fd 级重定向，保证 stdout 只有 JSON。

用法：
  # 判断某对暴露-结局既往是否已做过 MR
  python mr_eval.py --mrornot --outcome "back pain" --exposure "body mass index"

  # 按 STROBE-MR 清单评估一篇文献的质量
  python mr_eval.py --strobe --title "Body mass index and back pain: a Mendelian randomization study"
"""

import argparse
import os
import sys
import tempfile

from _common import parse_args_or_fail, emit, fail, require_mragent, capture_stdout_to

TOOL = "mr-eval"


def build_agent(AgentCls, args, key):
    """构造一个最小可用的 MRAgent 实例（只为拿到那两个方法）。"""
    kwargs = dict(mode="O", outcome=args.outcome or "tmp", AI_key=key,
                  LLM_model=args.model, model_type=args.model_type,
                  base_url=args.base_url, gwas_token=os.environ.get("MRAGENT_GWAS_TOKEN"))
    return AgentCls(**kwargs)


def main():
    ap = argparse.ArgumentParser(description="LLM 判定：MRorNot / STROBE-MR")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mrornot", action="store_true", help="判断某对是否做过 MR")
    g.add_argument("--strobe", action="store_true", help="STROBE-MR 质量评估")
    ap.add_argument("--outcome", help="结局（--mrornot 必填）")
    ap.add_argument("--exposure", help="暴露（--mrornot 必填）")
    ap.add_argument("--title", help="文献标题（--strobe 必填）")
    ap.add_argument("--model", default="gpt-4o")
    ap.add_argument("--model-type", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", help="不给则取 MRAGENT_AI_KEY / OPENAI_API_KEY")
    ap.add_argument("--keep-log", action="store_true", help="保留本次构造过程的日志")
    args = parse_args_or_fail(ap, TOOL)

    if args.mrornot and not (args.outcome and args.exposure):
        fail(TOOL, "--mrornot 需要同时给 --outcome 和 --exposure", exit_code=2)
    if args.strobe and not args.title:
        fail(TOOL, "--strobe 需要 --title", exit_code=2)

    key = args.api_key or os.environ.get("MRAGENT_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if args.model_type == "openai" and not key:
        fail(TOOL, "缺少 LLM key",
             "设置 MRAGENT_AI_KEY 或 OPENAI_API_KEY", exit_code=2)

    _mod, _f, err = require_mragent(TOOL)
    if err:
        fail(TOOL, err[0], err[1], exit_code=2)

    from mragent import MRAgent

    workdir = tempfile.mkdtemp(prefix="mr_eval_")
    log_path = os.path.join(workdir, "eval.log")
    cwd = os.getcwd()
    os.chdir(workdir)
    payload = {"tool": TOOL, "model": args.model, "workdir": workdir}
    try:
        with capture_stdout_to(log_path):
            agent = build_agent(MRAgent, args, key)
            if args.mrornot:
                verdict = agent.outcome_exposure_MRorNot(args.outcome, args.exposure)
                payload.update(mode="mrornot", outcome=args.outcome,
                               exposure=args.exposure, result=verdict)
            else:
                verdict = agent.STROBE_MR(args.title)
                payload.update(mode="strobe", title=args.title, result=verdict)
    except SystemExit:
        fail(TOOL, "MRAgent 内部触发了 sys.exit（多半是前置步骤条件不满足）")
    except Exception as exc:
        fail(TOOL, "%s: %s" % (type(exc).__name__, exc),
             "确认 key 有效；STROBE-MR 评估需要较长的 LLM 输出，弱模型可能截断")
    finally:
        os.chdir(cwd)

    payload["ok"] = True
    if not args.keep_log:
        try:
            os.remove(log_path)
        except OSError:
            pass
        payload.pop("workdir", None)
    else:
        payload["log_path"] = log_path
    emit(payload)


if __name__ == "__main__":
    main()
