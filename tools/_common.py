# -*- coding: utf-8 -*-
"""
mr-agent 工具包共享层。

所有工具的统一契约（与 scripts/ 下的脚本一致）：
  * stdout 只放 JSON，人类提示走 stderr
  * 环境缺失时返回结构化 JSON，而不是抛异常堆栈
  * required 依赖缺失时 exit 2，业务失败 exit 1，成功 exit 0

放在 tools/ 下而不是 scripts/ 下，是为了区分：
  scripts/ = 流程编排（跑完整 MR 流水线）
  tools/   = 原子能力（AI 可单独调用的一个个动作）
"""

import json
import os
import sys


def emit(payload, exit_code=0):
    """把结果以 JSON 写到 stdout 并退出。"""
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.exit(exit_code)


def fail(tool, message, hint=None, exit_code=1):
    """结构化失败。"""
    payload = {"tool": tool, "ok": False, "error": message}
    if hint:
        payload["hint"] = hint
    sys.stderr.write("%s: %s\n" % (tool, message))
    if hint:
        sys.stderr.write("提示: %s\n" % hint)
    emit(payload, exit_code)


def require_mragent(tool, funcs=None):
    """
    导入 mragent 及其函数。

    mragent 只在 Python 3.11/3.12 上装得上（numpy<2 / pandas<2 无 cp313 wheel），
    所以这里必须优雅处理 ImportError，给出可执行的修复建议，而不是堆栈。

    返回 (module_or_None, funcs_dict_or_None, error_or_None)
    """
    try:
        import mragent  # noqa: F401
    except ImportError as exc:
        return None, None, (
            "mragent 未安装或不可导入: %s" % exc,
            "请在 Python 3.11/3.12 的解释器里 pip install mragent；"
            "3.13 装不上（numpy<2/pandas<2 无 cp313 wheel）。"
            "若当前目录存在名为 mragent 的文件夹，Python 会误把它当包导入。",
        )

    got = {}
    if funcs:
        try:
            import mragent.agent_tool as at
            import mragent.LLM as llm
            sources = {"agent_tool": at, "LLM": llm}
            for f in funcs:
                mod = sources.get("agent_tool")
                if hasattr(mod, f):
                    got[f] = getattr(mod, f)
                elif hasattr(llm, f):
                    got[f] = getattr(llm, f)
                else:
                    return None, None, (
                        "mragent 里找不到函数 %s" % f,
                        "版本可能不匹配，确认装的是 mragent==0.2.5",
                    )
        except ImportError as exc:
            return None, None, ("导入 mragent 子模块失败: %s" % exc, None)
    return sys.modules.get("mragent"), got, None


def capture_stdout_to(path):
    """
    返回一个上下文管理器，把 fd 1/2 重定向到文件。

    必须在 fd 层做，才能同时抓到 Python print 和 R 通过 os.system 的原生输出。
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        sys.stdout.flush()
        sys.stderr.flush()
        saved_out = os.dup(1)
        saved_err = os.dup(2)
        fh = open(path, "wb")
        try:
            os.dup2(fh.fileno(), 1)
            os.dup2(fh.fileno(), 2)
            yield fh
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved_out, 1)
            os.dup2(saved_err, 2)
            fh.close()
            os.close(saved_out)
            os.close(saved_err)

    return _ctx()


def parse_args_or_fail(ap, tool):
    """
    解析命令行参数；argparse 校验失败（exit 2）时转成结构化 JSON。

    argparse 默认把 usage 打到 stderr 然后 SystemExit(2)，stdout 什么都没有 ——
    这违反"错误路径也必须返回 JSON"的契约，调用方拿不到可解析的结果。
    --help（exit 0）保持原样输出。
    """
    try:
        return ap.parse_args()
    except SystemExit as exc:
        if exc.code == 2:
            fail(tool, "命令行参数错误",
                 "运行 `python %s --help` 查看完整用法" % tool, exit_code=2)
        raise


def read_csv_rows(path):
    """标准库读 CSV；编码异常退到 latin-1，不因一个坏字节中断。"""
    import csv
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except UnicodeDecodeError:
        with open(path, newline="", encoding="latin-1") as fh:
            return list(csv.DictReader(fh))


def find_first(root, filename):
    for r, _d, files in os.walk(root):
        if filename in files:
            return os.path.join(r, filename)
    return None
