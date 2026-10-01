#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：OpenGWAS 查询（在线 + 离线两种模式）。

对应上游 `mragent.agent_tool.check_keyword_in_opengwas` / `get_gwas_id`，
也就是 MRAgent step4/step5 的能力。

在线模式依赖 mragent + 有效 gwas_token；离线模式只读本地 opengwas.csv
（上游仓库自带，10MB / 5 万行），**不需要装 mragent、不需要联网**，
因此可以先离线确认某个表型到底有没有 GWAS 数据，再决定要不要花 token 跑全流程。

用法：
  # 离线：在本地清单里搜（推荐先跑这个）
  python mr_gwas.py --keyword "body mass index" --mode csv
  python mr_gwas.py --keyword "body mass index" --mode csv --csv /path/opengwas.csv

  # 在线：需要 mragent + MRAGENT_GWAS_TOKEN
  python mr_gwas.py --keyword "body mass index" --mode online

  # 下载上游的 opengwas.csv
  python mr_gwas.py --fetch --csv ./opengwas.csv
"""

import argparse
import os
import sys
import urllib.request

from _common import parse_args_or_fail, emit, fail, read_csv_rows

TOOL = "mr-gwas"
UPSTREAM_CSV_URL = ("https://raw.githubusercontent.com/xuwei1997/MRAgent/"
                    "main/opengwas.csv")
# 本地查找 opengwas.csv 时会依次尝试这些位置。
# 注意：安装到 ~/.workbuddy/skills/mr-agent 后，skill 目录的"上级"是 skills/，
# 不能再依赖工作区里的仓库副本 —— 所以优先查环境变量和 skill 自带副本。
_HERE = os.path.dirname(os.path.abspath(__file__))
# 全局缓存：install.py 会把清单下到这里。放在 $HOME 下而不是 skill 目录里，
# 一是 10 MB 的第三方数据不该进 git 仓库（见 .gitignore / NOTICE），
# 二是多个安装位置（Claude Code / WorkBuddy / CodeBuddy / Codex / DeepSeek Harness）可以共用一份。
GLOBAL_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "mr-agent",
                            "opengwas.csv")
DEFAULT_CSV_PATHS = [
    "./opengwas.csv",
    os.path.join(_HERE, "opengwas.csv"),
    os.path.join(_HERE, "..", "opengwas.csv"),
    GLOBAL_CACHE,
    os.path.join(_HERE, "..", "..", "MRAgent-upstream", "opengwas.csv"),
]


def resolve_csv(explicit=None):
    """找 opengwas.csv。优先级：显式 --csv > 环境变量 > 默认位置列表。"""
    if explicit:
        return explicit if os.path.exists(explicit) else None
    env = os.environ.get("MRAGENT_OPENGWAS_CSV")
    if env and os.path.exists(env):
        return env
    for p in DEFAULT_CSV_PATHS:
        p = os.path.normpath(p)
        if os.path.exists(p):
            return p
    return None


def search_local(csv_path, keyword, limit=50, exact=False):
    """
    在本地 opengwas.csv 里检索。

    上游 MRAgent 的 csv 模式做的是大小写不敏感子串匹配
    （`check_keyword_in_opengwas_csv`），这里保持同样语义，
    另加 `--exact` 供需要精确匹配时用。
    """
    rows = read_csv_rows(csv_path)
    kw = keyword.lower()
    hits = []
    for r in rows:
        trait = (r.get("trait") or "")
        matched = (trait.lower() == kw) if exact else (kw in trait.lower())
        if matched:
            hits.append({
                "id": r.get("id"),
                "trait": trait,
                "population": r.get("population"),
                "sample_size": r.get("sample_size"),
                "year": r.get("year"),
                "author": r.get("author"),
                "nsnp": r.get("nsnp"),
                "category": r.get("category"),
            })
            if len(hits) >= limit:
                break
    return hits, len(rows)


def main():
    ap = argparse.ArgumentParser(description="OpenGWAS 查询（MRAgent step4/5 的原子能力）")
    ap.add_argument("--keyword", help="表型关键词，如 'body mass index'")
    ap.add_argument("--mode", default="csv", choices=["csv", "online"],
                    help="csv=离线读本地清单（默认，不需要 mragent）；online=走 OpenGWAS API")
    ap.add_argument("--csv", help="opengwas.csv 路径；不给则自动查找")
    ap.add_argument("--exact", action="store_true", help="精确匹配 trait，而非子串匹配")
    ap.add_argument("--limit", type=int, default=50, help="返回条数上限")
    ap.add_argument("--fetch", action="store_true", help="下载上游 opengwas.csv 到本地")
    args = parse_args_or_fail(ap, TOOL)

    if args.fetch:
        # 默认下到全局缓存而不是当前目录：下到 CWD 会把 10 MB 的第三方数据
        # 塞回技能目录（那正是 .gitignore 要排除的东西），而且每个安装位置
        # 会各存一份。装到缓存里则多处共用。
        target = args.csv or GLOBAL_CACHE
        try:
            os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
            urllib.request.urlretrieve(UPSTREAM_CSV_URL, target)  # noqa: S310
        except Exception as exc:
            fail(TOOL, "下载失败: %s" % exc,
                 "检查网络，或手动从 %s 下载" % UPSTREAM_CSV_URL)
        emit({"tool": TOOL, "ok": True, "action": "fetch", "path": os.path.abspath(target),
              "size_mb": round(os.path.getsize(target) / 1024 / 1024, 2)})

    if not args.keyword:
        fail(TOOL, "缺少 --keyword（或改用 --fetch 下载清单）", exit_code=2)

    if args.mode == "online":
        from _common import require_mragent
        _mod, funcs, err = require_mragent(TOOL, ["check_keyword_in_opengwas", "get_gwas_id"])
        if err:
            fail(TOOL, err[0], err[1], exit_code=2)
        try:
            has = funcs["check_keyword_in_opengwas"](args.keyword)
            ids = funcs["get_gwas_id"](args.keyword) if has else None
        except Exception as exc:
            fail(TOOL, "在线查询失败: %s: %s" % (type(exc).__name__, exc),
                 "确认 MRAGENT_GWAS_TOKEN 有效且未过期")
        emit({"tool": TOOL, "ok": True, "mode": "online", "keyword": args.keyword,
              "in_opengwas": bool(has), "gwas_id": ids})

    csv_path = resolve_csv(args.csv)
    if not csv_path:
        fail(TOOL, "找不到 opengwas.csv",
             "三种办法: (1) python mr_gwas.py --fetch 下载到当前目录; "
             "(2) 用 --csv 指定路径; "
             "(3) 设置环境变量 MRAGENT_OPENGWAS_CSV 指向它", exit_code=2)

    try:
        hits, total = search_local(csv_path, args.keyword, args.limit, args.exact)
    except Exception as exc:
        fail(TOOL, "读取 %s 失败: %s" % (csv_path, exc))

    emit({
        "tool": TOOL, "ok": len(hits) > 0, "mode": "csv",
        "csv_path": os.path.abspath(csv_path),
        "keyword": args.keyword, "match": "exact" if args.exact else "substring",
        "total_rows": total, "hit_count": len(hits),
        "hits": hits,
        "note": ("未命中。上游用的是子串匹配，换更短的词试试；"
                 "或确认该表型在 OpenGWAS 里是否存在" if not hits else ""),
    })


if __name__ == "__main__":
    main()
