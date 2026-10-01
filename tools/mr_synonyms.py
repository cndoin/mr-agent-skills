#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：UMLS 同义词扩展。

对应上游 `mragent.agent_tool.get_synonyms`，也就是 MRAgent step3 里
"把 body mass index 扩展成 BMI / obesity 等说法" 的能力 —— 扩展得越好，
step5 在 OpenGWAS 里命中 GWAS 的概率越高。

关于 API key（重要）：
本工具只接受用户自己的 UMLS key，不复用上游包里硬编码的 key。
完整流水线的上游 `MRAgent` 暂不支持注入自定义 UMLS key，因此运行器默认关闭
同义词扩展；用户显式开启时会使用上游包内置 key，存在限流、失效和授权边界。

用法：
  python mr_synonyms.py --term "body mass index"  # 需先设置 UMLS_API_KEY
"""

import argparse
import os
import sys

from _common import parse_args_or_fail, emit, fail, require_mragent

TOOL = "mr-synonyms"


def main():
    ap = argparse.ArgumentParser(description="UMLS 同义词扩展（MRAgent step3 的原子能力）")
    ap.add_argument("--term", required=True, help="要扩展的术语")
    ap.add_argument("--api-key", help="UMLS API key；不给则取环境变量 UMLS_API_KEY")
    args = parse_args_or_fail(ap, TOOL)

    key = args.api_key or os.environ.get("UMLS_API_KEY")
    key_source = "user" if args.api_key else ("env" if os.environ.get("UMLS_API_KEY") else None)

    if not key:
        fail(TOOL, "缺少 UMLS API key",
             "到 https://uts.nlm.nih.gov/uts/ 申请后设置 UMLS_API_KEY 或使用 --api-key",
             exit_code=2)

    _mod, funcs, err = require_mragent(TOOL, ["get_synonyms"])
    if err:
        fail(TOOL, err[0], err[1], exit_code=2)

    try:
        result = funcs["get_synonyms"](args.term, key)
    except Exception as exc:
        fail(TOOL, "同义词扩展失败: %s: %s" % (type(exc).__name__, exc),
             "若卡住或返回空，多半是 UMLS key 被限流/失效；"
             "可改用 mr_gwas.py 的离线清单直接确认表型名")

    items = result if isinstance(result, list) else [result]
    emit({"tool": TOOL, "ok": True, "term": args.term,
          "key_source": key_source, "count": len(items), "synonyms": items})


if __name__ == "__main__":
    main()
