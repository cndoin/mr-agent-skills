#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：UMLS 同义词扩展（原生实现，不依赖 mragent）。

对应上游 `mragent.agent_tool.get_synonyms`，也就是 MRAgent step3 里
"把 body mass index 扩展成 BMI / obesity 等说法"的能力 ——
扩展得越好，step5 在 OpenGWAS 里命中 GWAS 的概率越高。

**为什么不用上游实现**：上游 `get_synonyms` 只是两次 UMLS REST 调用
（`requests` + 两次 GET），却挂在 `agent_tool.py` 里，于是被迫依赖整个 mragent。
这里用标准库直接发同样的两个请求，**没装 mragent 也能用**。

关于 API key（重要）：
本工具只接受用户自己的 UMLS key，不复用上游包里硬编码的 key。
完整流水线的上游 `MRAgent` 暂不支持注入自定义 UMLS key，因此运行器默认关闭
同义词扩展；用户显式开启时会使用上游包内置 key，存在限流、失效和授权边界。

用法：
  python mr_synonyms.py --term "body mass index"   # 需先设置 UMLS_API_KEY
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from _common import parse_args_or_fail, emit, fail

TOOL = "mr-synonyms"
UMLS_BASE = "https://uts-ws.nlm.nih.gov/rest"
TIMEOUT = 60


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mr-agent/1.1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def get_synonyms(term, api_key, page_size=25):
    """与上游同语义：先按字符串找 CUI，再取该 CUI 下 ENG 原子的名称，小写去重。"""
    search = "%s/search/current?%s" % (UMLS_BASE, urllib.parse.urlencode(
        {"apiKey": api_key, "string": term, "pageNumber": 1, "pageSize": 1}))
    data = _get_json(search)
    results = (data.get("result") or {}).get("results") or []
    if not results:
        return [], None
    cui = results[0].get("ui")

    atoms = "%s/content/current/CUI/%s/atoms?%s" % (
        UMLS_BASE, cui, urllib.parse.urlencode(
            {"apiKey": api_key, "ttys": "", "language": "ENG",
             "pageSize": page_size}))
    data2 = _get_json(atoms)
    rows = data2.get("result") or []
    names = [r.get("name") for r in rows if isinstance(r, dict) and r.get("name")]
    return sorted({n.lower() for n in names}), cui


def main():
    ap = argparse.ArgumentParser(
        description="UMLS 同义词扩展（MRAgent step3 的原子能力，原生实现，无需 mragent）")
    ap.add_argument("--term", required=True, help="要扩展的术语")
    ap.add_argument("--api-key", help="UMLS API key；不给则取环境变量 UMLS_API_KEY")
    ap.add_argument("--page-size", type=int, default=25,
                    help="原子（atom）返回上限，默认 25，与上游一致")
    args = parse_args_or_fail(ap, TOOL)

    key = args.api_key or os.environ.get("UMLS_API_KEY")
    key_source = "user" if args.api_key else (
        "env" if os.environ.get("UMLS_API_KEY") else None)

    if not key:
        fail(TOOL, "缺少 UMLS API key",
             "到 https://uts.nlm.nih.gov/uts/ 申请后设置 UMLS_API_KEY 或使用 --api-key",
             exit_code=2)

    try:
        synonyms, cui = get_synonyms(args.term, key, args.page_size)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            fail(TOOL, "UMLS 拒绝了凭据（HTTP %s）" % exc.code,
                 "key 无效或已过期，去 https://uts.nlm.nih.gov/uts/ 重新申请")
        fail(TOOL, "UMLS 返回 HTTP %s" % exc.code, "稍后重试；UMLS 有速率限制")
    except urllib.error.URLError as exc:
        fail(TOOL, "无法连接 UMLS: %s" % exc.reason, "检查网络或代理")
    except ValueError as exc:
        fail(TOOL, "UMLS 响应解析失败: %s" % exc,
             "接口形状可能已变，请反馈该错误信息")
    except Exception as exc:
        fail(TOOL, "同义词扩展失败: %s: %s" % (type(exc).__name__, exc),
             "若卡住或返回空，多半是 UMLS key 被限流/失效；"
             "可改用 mr_gwas.py 的离线清单直接确认表型名")

    emit({"tool": TOOL, "ok": True, "term": args.term, "cui": cui,
          "key_source": key_source, "count": len(synonyms), "synonyms": synonyms,
          "note": "" if synonyms else
          "UMLS 里没找到该字符串对应的 CUI，或该 CUI 下没有 ENG 原子"})


if __name__ == "__main__":
    main()
