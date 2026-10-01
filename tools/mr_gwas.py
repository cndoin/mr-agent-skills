#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：OpenGWAS 查询（离线清单 + 在线 API 两种模式）。

对应上游 `mragent.agent_tool.check_keyword_in_opengwas` / `get_gwas_id`，
也就是 MRAgent step4/step5 的能力。

════════════════════════════════════════════════════════════════════════
为什么在线模式**没有**照搬上游实现
════════════════════════════════════════════════════════════════════════
上游这两个函数是**爬 gwas.mrcieu.ac.uk 的 HTML 表格**：

    url = f"https://gwas.mrcieu.ac.uk/datasets/?trait__icontains={keyword}"
    if "Filtered to 0 records" in soup.text:   # 判断有没有数据
    table = soup.find('table')                 # 再抓表格

2026-10-01 实测该页面已经改版为前端渲染，服务端返回的表格里只有一行
`Failed to load batches data.`，且**无论关键词是什么都不再包含
`Filtered to 0 records`**（连 `zzz_no_such_trait_zzz` 这种乱码词都不含）。
后果：
  * `check_keyword_in_opengwas()` 对**任何**关键词都返回 True —— 永远"存在"；
  * `get_gwas_id()` 返回的是报错行拼出来的垃圾记录，或直接抛异常。

因此本工具**不复刻这个已失效的爬虫**，改用 OpenGWAS 官方鉴权 API：
`GET https://api.opengwas.io/api/gwasinfo`（Bearer JWT），
把清单拉到本地缓存后按 trait 子串过滤。请求用的是你本来就必备的 JWT。

离线模式（`--mode csv`，默认）读上游仓库自带的 opengwas.csv
（10 MB / 5 万行），**不需要 mragent、不需要联网、不需要 token**，
目前是唯一稳定的检索途径。

用法：
  # 离线（推荐先跑这个）
  python mr_gwas.py --keyword "body mass index" --mode csv
  python mr_gwas.py --keyword "body mass index" --mode csv --exact

  # 在线（需 OPENGWAS_JWT 或 MRAGENT_GWAS_TOKEN）
  python mr_gwas.py --keyword "body mass index" --mode online
  python mr_gwas.py --keyword "bmi" --mode online --refresh

  # 下载上游的 opengwas.csv 到全局缓存
  python mr_gwas.py --fetch
"""

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from _common import parse_args_or_fail, emit, fail, read_csv_rows

TOOL = "mr-gwas"
UPSTREAM_CSV_URL = ("https://raw.githubusercontent.com/xuwei1997/MRAgent/"
                    "main/opengwas.csv")
GWASINFO_API = "https://api.opengwas.io/api/gwasinfo"

_HERE = os.path.dirname(os.path.abspath(__file__))
# 全局缓存：install.py 会把清单下到这里。放在 $HOME 下而不是 skill 目录里，
# 一是 10 MB 的第三方数据不该进 git 仓库（见 .gitignore / NOTICE），
# 二是多个安装位置（Claude Code / WorkBuddy / CodeBuddy / Codex / DeepSeek Harness）可以共用一份。
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "mr-agent")
GLOBAL_CACHE = os.path.join(CACHE_DIR, "opengwas.csv")
GWASINFO_CACHE = os.path.join(CACHE_DIR, "gwasinfo.json")

DEFAULT_CSV_PATHS = [
    "./opengwas.csv",
    os.path.join(_HERE, "opengwas.csv"),
    os.path.join(_HERE, "..", "opengwas.csv"),
    GLOBAL_CACHE,
    os.path.join(_HERE, "..", "..", "MRAgent-upstream", "opengwas.csv"),
]

USER_AGENT = "mr-agent/1.1 (OpenGWAS API client)"
TIMEOUT = 120


# ─────────────────────────────── 通用 ───────────────────────────────

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


def get_jwt():
    return (os.environ.get("MRAGENT_GWAS_TOKEN")
            or os.environ.get("OPENGWAS_JWT")
            or None)


def match_trait(trait, keyword, exact=False):
    t = (trait or "").lower()
    kw = keyword.lower()
    return (t == kw) if exact else (kw in t)


def slim(rec):
    return {k: rec.get(k) for k in
            ("id", "trait", "population", "sample_size", "year",
             "author", "nsnp", "category", "sex", "build") if k in rec}


# ───────────────────────────── 离线模式 ─────────────────────────────

def search_local(csv_path, keyword, limit=50, exact=False):
    """
    在本地 opengwas.csv 里检索。

    上游 csv 模式做的是大小写不敏感子串匹配（`check_keyword_in_opengwas_csv`），
    这里保持同样语义，另加 `--exact` 供需要精确匹配时用。
    """
    rows = read_csv_rows(csv_path)
    hits = []
    for r in rows:
        if match_trait(r.get("trait"), keyword, exact):
            hits.append({
                "id": r.get("id"), "trait": r.get("trait"),
                "population": r.get("population"),
                "sample_size": r.get("sample_size"),
                "year": r.get("year"), "author": r.get("author"),
                "nsnp": r.get("nsnp"), "category": r.get("category"),
            })
            if len(hits) >= limit:
                break
    return hits, len(rows)


# ───────────────────────────── 在线模式 ─────────────────────────────

def normalize_gwasinfo(obj):
    """
    把 gwasinfo 响应规整成 list[dict]。

    OpenGWAS 不同版本返回过 list，也返回过 {id: {...}} 的字典，
    所以这里都接受；形状不认识时抛错而不是静默返回空 ——
    "静默返回空"正是上游爬虫坏掉时的表现，不能重蹈。
    """
    if isinstance(obj, list):
        recs = obj
    elif isinstance(obj, dict):
        if isinstance(obj.get("data"), list):
            recs = obj["data"]
        else:
            recs = []
            for k, v in obj.items():
                if isinstance(v, dict):
                    item = dict(v)
                    item.setdefault("id", k)
                    recs.append(item)
    else:
        raise ValueError("无法识别的 gwasinfo 响应类型: %s" % type(obj).__name__)

    out = []
    for r in recs:
        if isinstance(r, dict) and (r.get("id") or r.get("trait")):
            out.append(r)
    if not out and recs:
        raise ValueError("响应里有 %d 条记录但没有一条含 id/trait 字段" % len(recs))
    return out


def fetch_gwasinfo(jwt, refresh=False):
    """取 OpenGWAS 清单；默认用磁盘缓存（清单很大，不必每次重拉）。"""
    if not refresh and os.path.exists(GWASINFO_CACHE):
        try:
            cached = json.load(io.open(GWASINFO_CACHE, encoding="utf-8"))
            recs = normalize_gwasinfo(cached)
            if recs:
                return recs, GWASINFO_CACHE, False
        except Exception:
            pass  # 缓存坏了就走网络

    req = urllib.request.Request(
        GWASINFO_API,
        headers={"Authorization": "Bearer %s" % jwt, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read().decode("utf-8", "replace")
    recs = normalize_gwasinfo(json.loads(body))

    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        io.open(GWASINFO_CACHE, "w", encoding="utf-8", newline="\n").write(
            json.dumps(recs, ensure_ascii=False))
    except OSError:
        pass
    return recs, GWASINFO_CACHE, True


def search_remote(records, keyword, limit=50, exact=False):
    hits = []
    for r in records:
        if match_trait(r.get("trait"), keyword, exact):
            hits.append(slim(r))
            if len(hits) >= limit:
                break
    return hits, len(records)


# ─────────────────────────────── 入口 ───────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="OpenGWAS 查询（MRAgent step4/5 的原子能力）")
    ap.add_argument("--keyword", help="表型关键词，如 'body mass index'")
    ap.add_argument("--mode", default="csv", choices=["csv", "online"],
                    help="csv=离线读本地清单（默认，无需 mragent/联网/token）；"
                         "online=走 OpenGWAS 官方 API（需 JWT）")
    ap.add_argument("--csv", help="opengwas.csv 路径；不给则自动查找")
    ap.add_argument("--exact", action="store_true", help="精确匹配 trait，而非子串匹配")
    ap.add_argument("--limit", type=int, default=50, help="返回条数上限")
    ap.add_argument("--fetch", action="store_true", help="下载上游 opengwas.csv 到全局缓存")
    ap.add_argument("--refresh", action="store_true",
                    help="online 模式忽略本地 gwasinfo 缓存，重新拉取")
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
        emit({"tool": TOOL, "ok": True, "action": "fetch",
              "path": os.path.abspath(target),
              "size_mb": round(os.path.getsize(target) / 1024 / 1024, 2)})

    if not args.keyword:
        fail(TOOL, "缺少 --keyword（或改用 --fetch 下载清单）", exit_code=2)

    # ---------- 在线 ----------
    if args.mode == "online":
        jwt = get_jwt()
        if not jwt:
            fail(TOOL, "online 模式需要 OpenGWAS JWT，但环境里没有",
                 "设置 OPENGWAS_JWT（或 MRAGENT_GWAS_TOKEN）。申请地址 "
                 "https://api.opengwas.io/ 。"
                 "另注：上游 MRAgent 的在线查询是爬 gwas.mrcieu.ac.uk 的 HTML，"
                 "该页面已改版失效（对任何关键词都判定为「有数据」），"
                 "本工具不复刻该行为；没有 JWT 时请改用 --mode csv。",
                 exit_code=2)
        try:
            records, cache_path, fetched = fetch_gwasinfo(jwt, args.refresh)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                fail(TOOL, "OpenGWAS 拒绝了凭据（HTTP %s）" % exc.code,
                     "JWT 无效或已过期，去 https://api.opengwas.io/ 重新申请；"
                     "或改用 --mode csv 走离线清单")
            fail(TOOL, "OpenGWAS API 返回 HTTP %s" % exc.code,
                 "稍后重试；若持续失败可改用 --mode csv")
        except urllib.error.URLError as exc:
            fail(TOOL, "无法连接 OpenGWAS API: %s" % exc.reason,
                 "检查网络/代理；或改用 --mode csv 走离线清单")
        except ValueError as exc:
            fail(TOOL, "OpenGWAS 响应解析失败: %s" % exc,
                 "接口形状可能已变，请反馈该错误信息；或改用 --mode csv")

        hits, total = search_remote(records, args.keyword, args.limit, args.exact)
        emit({
            "tool": TOOL, "ok": len(hits) > 0, "mode": "online",
            "source": GWASINFO_API, "cache": cache_path, "fetched_now": fetched,
            "keyword": args.keyword,
            "match": "exact" if args.exact else "substring",
            "total_rows": total, "hit_count": len(hits), "hits": hits,
            "note": ("" if hits else "该表型在 OpenGWAS 清单里没有匹配项"),
        })

    # ---------- 离线 ----------
    csv_path = resolve_csv(args.csv)
    if not csv_path:
        fail(TOOL, "找不到 opengwas.csv",
             "三种办法: (1) python mr_gwas.py --fetch 下载到全局缓存; "
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
