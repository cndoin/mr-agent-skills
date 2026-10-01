#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：PubMed 文献检索。

对应上游 `mragent.agent_tool.pubmed_crawler` / `get_paper_details` /
`get_paper_details_pmc`，也就是 MRAgent step1 里"扫文献"那一段的能力，
拆出来单独给 AI 调用 —— 只想看看某疾病最近有哪些文献时，不必跑整条流水线。

用法：
  python mr_pubmed.py --keyword "back pain" --num 20
  python mr_pubmed.py --keyword "back pain" --num 20 --sort relevance
  python mr_pubmed.py --details "Some paper title"
  python mr_pubmed.py --details "Some paper title" --pmc
"""

import argparse
import json
import sys

from _common import parse_args_or_fail, emit, fail, require_mragent

TOOL = "mr-pubmed"


def main():
    ap = argparse.ArgumentParser(description="PubMed 检索（MRAgent step1 的原子能力）")
    ap.add_argument("--keyword", help="检索关键词（疾病名 / 暴露名）")
    ap.add_argument("--num", type=int, default=20, help="抓取条数，默认 20")
    ap.add_argument("--sort", default="most recent",
                    choices=["most recent", "relevance", "pub date"],
                    help="排序方式，MRAgent 默认用 most recent")
    ap.add_argument("--details", help="按标题取论文详情（走 PubMed 或 PMC）")
    ap.add_argument("--pmc", action="store_true", help="详情改走 PMC")
    ap.add_argument("--limit", type=int, default=50, help="输出条数上限")
    args = parse_args_or_fail(ap, TOOL)

    if not args.keyword and not args.details:
        fail(TOOL, "必须给 --keyword 或 --details",
             "例: --keyword \"back pain\" --num 20", exit_code=2)

    want = ["get_paper_details_pmc"] if args.pmc else (
        ["get_paper_details"] if args.details else ["pubmed_crawler"])
    _mod, funcs, err = require_mragent(TOOL, want)
    if err:
        fail(TOOL, err[0], err[1], exit_code=2)

    try:
        if args.details:
            fn = funcs["get_paper_details_pmc"] if args.pmc else funcs["get_paper_details"]
            result = fn(args.details)
            emit({"tool": TOOL, "ok": True, "mode": "pmc" if args.pmc else "pubmed",
                  "title": args.details, "result": result})
        else:
            papers = funcs["pubmed_crawler"](args.keyword, args.num, args.sort, json_str=False)
            papers = papers or []
            slim = []
            for p in papers[:args.limit]:
                if isinstance(p, dict):
                    slim.append({
                        "index": p.get("index"),
                        "title": p.get("title"),
                        "abstract": (p.get("abstract") or "")[:400],
                    })
                else:
                    slim.append(p)
            emit({"tool": TOOL, "ok": True, "mode": "crawler",
                  "keyword": args.keyword, "num": args.num, "sort": args.sort,
                  "count": len(papers), "returned": len(slim), "papers": slim})
    except SystemExit:
        raise
    except Exception as exc:
        fail(TOOL, "%s: %s" % (type(exc).__name__, exc),
             "PubMed 需要联网；若超时请减少 --num 或检查网络")


if __name__ == "__main__":
    main()
