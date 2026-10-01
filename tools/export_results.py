#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
把 MRAgent 的结果目录打成 ZIP。

对应上游 `web_demo.py:create_download_button` 的下载能力 —— 上游只在
Streamlit 界面里提供，这里做成 CLI，方便 AI 跑完后直接产出可交付的压缩包。

用法：
  python export_results.py <output目录> [--out result.zip]
  python export_results.py ./mragent-runs/back_pain_O_xxx/output
"""

import argparse
import os
import sys
import zipfile
from datetime import datetime

from _common import parse_args_or_fail, emit, fail

TOOL = "mr-export"
# 这些是临时/日志类文件，不进交付包
EXCLUDE_SUFFIX = (".log", ".bak", ".tmp")
EXCLUDE_NAMES = {"test.R"}


def main():
    ap = argparse.ArgumentParser(description="打包 MRAgent 结果目录为 ZIP")
    ap.add_argument("directory", help="output 目录（或其上层 run 目录）")
    ap.add_argument("--out", help="输出 zip 路径；默认 <directory>/../MRAgent_results_<时间戳>.zip")
    ap.add_argument("--no-exclude", action="store_true", help="连日志/临时文件也打进去")
    args = parse_args_or_fail(ap, TOOL)

    d = os.path.abspath(args.directory)
    if not os.path.isdir(d):
        fail(TOOL, "目录不存在: %s" % d, exit_code=2)

    out = args.out
    if not out:
        parent = os.path.dirname(d)
        out = os.path.join(parent, "MRAgent_results_%s.zip" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    packed, skipped, total_bytes = [], [], 0
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    if os.path.abspath(os.path.join(root, fn)) == out:
                        continue  # 别把自己打进去
                    if not args.no_exclude and (
                            fn in EXCLUDE_NAMES or fn.endswith(EXCLUDE_SUFFIX)):
                        skipped.append(fn)
                        continue
                    fp = os.path.join(root, fn)
                    rel = os.path.relpath(fp, os.path.dirname(d))
                    zf.write(fp, rel)
                    packed.append(rel.replace("\\", "/"))
                    total_bytes += os.path.getsize(fp)
    except Exception as exc:
        fail(TOOL, "打包失败: %s: %s" % (type(exc).__name__, exc))

    by_ext = {}
    for p in packed:
        ext = os.path.splitext(p)[1].lower() or "(无扩展名)"
        by_ext[ext] = by_ext.get(ext, 0) + 1

    emit({
        "tool": TOOL, "ok": True,
        "source": d, "zip": out,
        "zip_size_mb": round(os.path.getsize(out) / 1024 / 1024, 3),
        "file_count": len(packed),
        "raw_bytes": total_bytes,
        "by_ext": by_ext,
        "skipped": sorted(set(skipped)),
        "files": packed[:200],
        "note": ("里面没有 PDF —— 说明还没跑到 step9，当前只是中间产物"
                 if not any(p.lower().endswith(".pdf") for p in packed) else ""),
    })


if __name__ == "__main__":
    main()
