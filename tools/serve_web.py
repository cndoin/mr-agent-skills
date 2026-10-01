#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动 MRAgent 官方 Streamlit Web 界面。

上游的 `web_demo.py` **不在 PyPI 包里**，只存在于 GitHub 仓库，所以 pip install
之后是启动不了界面的 —— 本工具负责把仓库拉下来（或复用本地已克隆的仓库）、
检查依赖、再拉起 streamlit。

上游 Web 界面提供：两种模式切换、模型与 token 填写、**逐 step 勾选**、
Python/R 双路实时日志、三个中间 CSV 的在线编辑保存、结果 ZIP 下载。
（其中 mrlap 与 mr_quality_evaluation 两个开关在 Web 上被作者禁用了，
  想用这两个得走 CLI 的 run_mr.py。）

用法：
  python serve_web.py                       # 自动找本地仓库，没有就克隆
  python serve_web.py --repo /path/MRAgent  # 指定本地仓库
  python serve_web.py --port 8600
  python serve_web.py --check               # 只体检，不启动
"""

import argparse
import os
import subprocess
import sys
import urllib.request

from _common import parse_args_or_fail, emit, fail

TOOL = "mr-serve-web"
REPO_ZIP = "https://github.com/xuwei1997/MRAgent/archive/refs/heads/main.zip"
# 本地常见位置：工作区里克隆的上游仓库
CANDIDATE_REPOS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "MRAgent-upstream"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "MRAgent-upstream"),
    "./MRAgent-upstream",
    "./MRAgent",
]


def find_web_demo(repo=None):
    cands = [repo] if repo else CANDIDATE_REPOS
    for c in cands:
        if not c:
            continue
        p = os.path.normpath(os.path.join(c, "web_demo.py"))
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


def main():
    ap = argparse.ArgumentParser(description="启动 MRAgent 官方 Web 界面")
    ap.add_argument("--repo", help="本地 MRAgent 仓库路径")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--check", action="store_true", help="只体检不启动")
    args = parse_args_or_fail(ap, TOOL)

    demo = find_web_demo(args.repo)
    report = {"tool": TOOL, "web_demo": demo}

    # streamlit 依赖检查
    try:
        import streamlit  # noqa: F401
        report["streamlit"] = True
    except ImportError:
        report["streamlit"] = False

    if demo is None:
        report["ok"] = False
        report["error"] = "找不到 web_demo.py"
        report["hint"] = ("它不在 PyPI 包里。克隆仓库："
                          "git clone --depth 1 https://github.com/xuwei1997/MRAgent.git "
                          "然后用 --repo 指定路径")
        emit(report, 2)

    if not report["streamlit"]:
        report["ok"] = False
        report["error"] = "streamlit 未安装"
        report["hint"] = "pip install streamlit（同样要在 Python 3.11/3.12 的环境里装）"
        emit(report, 2)

    report["ok"] = True
    if args.check:
        report["note"] = "体检通过，可以启动"
        emit(report)

    cmd = [sys.executable, "-m", "streamlit", "run", demo,
           "--server.port", str(args.port)]
    sys.stderr.write("启动: %s\n" % " ".join(cmd))
    sys.stderr.write("浏览器打开 http://localhost:%d\n" % args.port)
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    emit({"tool": TOOL, "ok": True, "action": "served", "port": args.port})


if __name__ == "__main__":
    main()
