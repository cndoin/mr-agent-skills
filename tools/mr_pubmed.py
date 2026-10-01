#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：PubMed 文献检索（原生实现，不依赖 mragent）。

对应上游 `mragent.agent_tool.pubmed_crawler` / `get_paper_details` /
`get_paper_details_pmc` —— MRAgent step1「扫文献」那一段的能力。

**为什么不沿用上游实现**：上游这些函数靠 `Bio.Entrez`（biopython），
并且把作者邮箱硬编码在源码里（`670525744@qq.com` / `xuwei_chn@foxmail.com`）。
本工具改用标准库直接请求 NCBI E-utilities —— 公开 REST 接口，不需要任何凭据，
于是在**没装 mragent 的机器上也能跑**，也不会把别人的邮箱当成你的。

与上游的差异（有意为之，可用 --first-abstract-only / --strict-shape 还原）：
  * 上游只取 `AbstractText[0]`，结构化摘要（Background/Methods/Results…）会被截断成第一段。
    本工具默认拼接全部段落并保留 Label 前缀。
  * 上游把 `'most recent'` 直接传给 Entrez，而这不是合法的 sort 取值（Entrez 会忽略）。
    本工具把它映射成合法的 `pub_date`。

用法：
  python mr_pubmed.py --keyword "back pain" --num 20
  python mr_pubmed.py --keyword "back pain" --sort relevance --limit 5
  python mr_pubmed.py --details "Body mass index and back pain: a Mendelian randomization study"
  python mr_pubmed.py --details "Mendelian randomization" --pmc
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from _common import parse_args_or_fail, emit, fail

TOOL = "mr-pubmed"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_BIOC = ("https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/"
            "pmcoa.cgi/BioC_json/{pmc_id}/unicode")

# 上游 `--sort` 的三个字面量 → Entrez 真正接受的取值。
# 上游直接把 'most recent' 传给 Entrez，这不是合法值，会被静默忽略。
SORT_MAP = {
    "most recent": "pub_date",
    "pub date": "pub_date",
    "relevance": "relevance",
}

USER_AGENT = "mr-agent/1.1 (https://github.com/xuwei1997/MRAgent fork; MR skill)"


def _strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def _text(node):
    """取节点全部文本（处理 <i> 之类的内联标签），并规整空白。"""
    if node is None:
        return None
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip() or None


def _params(extra):
    p = {"tool": "mr-agent"}
    email = os.environ.get("NCBI_EMAIL")
    if email:
        p["email"] = email
    p.update(extra)
    return p


def _get(url, params=None, timeout=45):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def esearch(term, retmax, sort):
    raw = _get(EUTILS + "/esearch.fcgi",
               _params({"db": "pubmed", "term": term, "retmax": str(retmax),
                        "retmode": "json", "sort": sort}))
    data = json.loads(raw.decode("utf-8", "replace"))
    return data.get("esearchresult", {}).get("idlist", []) or []


def efetch_xml(ids):
    return _get(EUTILS + "/efetch.fcgi",
                _params({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}))


def parse_articles(xml_bytes, first_abstract_only=False):
    """把 PubMed XML 解析成结构化列表（字段对齐上游 get_paper_details）。"""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("PubMed 返回的 XML 无法解析: %s" % exc)

    out = []
    for i, art in enumerate(root.iter(), 0):
        if _strip_ns(art.tag) != "PubmedArticle":
            continue
        rec = {"index": None, "title": None, "abstract": None, "pmid": None,
               "doi": None, "journal": None, "author": None, "year": None}
        for node in art.iter():
            t = _strip_ns(node.tag)
            if t == "PMID" and rec["pmid"] is None:
                rec["pmid"] = _text(node)
            elif t == "ArticleTitle" and rec["title"] is None:
                rec["title"] = _text(node)
            elif t == "AbstractText":
                label = node.attrib.get("Label")
                piece = _text(node)
                if piece:
                    piece = "%s: %s" % (label, piece) if label else piece
                    rec["abstract"] = piece if rec["abstract"] is None \
                        else rec["abstract"] + " " + piece
            elif t == "ELocationID" and node.attrib.get("EIdType") == "doi" \
                    and rec["doi"] is None:
                rec["doi"] = _text(node)
            elif t == "Title" and rec["journal"] is None:
                rec["journal"] = _text(node)
            elif t == "LastName" and rec["author"] is None:
                rec["author"] = _text(node)
            elif t == "Year" and rec["year"] is None:
                rec["year"] = _text(node)
        if first_abstract_only and rec["abstract"]:
            # 还原上游行为：只留第一段
            rec["abstract"] = rec["abstract"].split(". ")[0]
        out.append(rec)

    for i, rec in enumerate(out, 1):
        rec["index"] = i
    return out


def pubmed_crawler(keyword, num, sort, first_abstract_only=False):
    ids = esearch(keyword, num, sort)
    if not ids:
        return []
    return parse_articles(efetch_xml(ids), first_abstract_only)


def get_paper_details(title, sort="relevance", first_abstract_only=False):
    """按标题检索单篇，返回上游同形状的 [title, PMID, DOI, Journal, Author, Year, abstract]。"""
    ids = esearch(title, 1, sort)
    if not ids:
        return None
    arts = parse_articles(efetch_xml(ids), first_abstract_only)
    if not arts:
        return None
    a = arts[0]
    return [a["title"], a["pmid"], a["doi"], a["journal"],
            a["author"], a["year"], a["abstract"]]


def get_paper_details_pmc(title):
    """走 PMC BioC_json 取全文（与上游同一端点）。返回 (pmc_id, 正文文本)。"""
    ids = esearch(title, 1, "relevance")
    if not ids:
        return None, None
    last_err = None
    for pmid in ids:
        try:
            raw = _get(PMC_BIOC.format(pmc_id=pmid))
            text = raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last_err = "PMC 返回 HTTP %s" % exc.code
            continue
        if "No record can be found for the input" in text:
            last_err = "PMC 无该文献全文（PMID %s）" % pmid
            continue
        try:
            data = json.loads(text)
        except ValueError:
            last_err = "PMC 返回非 JSON"
            continue
        # 递归收集 passage 文本
        chunks = []

        def walk(node):
            if isinstance(node, dict):
                if "text" in node and isinstance(node["text"], str):
                    chunks.append(node["text"])
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(data)
        body = "\n".join(c.strip() for c in chunks if c.strip())
        if body:
            return pmid, body
        last_err = "PMC 返回内容里没有正文（PMID %s）" % pmid
    return None, last_err


def main():
    ap = argparse.ArgumentParser(
        description="PubMed 检索（MRAgent step1 的原子能力，原生实现，无需 mragent）")
    ap.add_argument("--keyword", help="检索关键词（疾病名 / 暴露名）")
    ap.add_argument("--num", type=int, default=20, help="抓取条数，默认 20")
    ap.add_argument("--sort", default="most recent",
                    choices=["most recent", "relevance", "pub date"],
                    help="排序；MRAgent 传的是 'most recent'（会被映射成合法的 pub_date）")
    ap.add_argument("--details", help="按标题取论文详情（走 PubMed 或 PMC）")
    ap.add_argument("--pmc", action="store_true", help="详情改走 PMC 全文")
    ap.add_argument("--limit", type=int, default=50, help="输出条数上限")
    ap.add_argument("--first-abstract-only", action="store_true",
                    help="还原上游行为：结构化摘要只留第一段")
    ap.add_argument("--strict-shape", action="store_true",
                    help="完全还原上游输出形状：只留第一段摘要，"
                         "且无结果时返回 [{'index':0,'title':'No paper found',"
                         "'abstract':'No paper found'}]")
    ap.add_argument("--email", help="NCBI 建议提供的联系邮箱（也可用环境变量 NCBI_EMAIL）")
    args = parse_args_or_fail(ap, TOOL)

    if not args.keyword and not args.details:
        fail(TOOL, "必须给 --keyword 或 --details",
             "例: --keyword \"back pain\" --num 20", exit_code=2)
    if args.num <= 0:
        fail(TOOL, "--num 必须为正整数，收到 %r" % args.num, exit_code=2)
    if args.strict_shape:
        args.first_abstract_only = True
    if args.email:
        os.environ["NCBI_EMAIL"] = args.email
    elif not os.environ.get("NCBI_EMAIL"):
        sys.stderr.write(
            "提示: 未设置联系邮箱。NCBI 建议提供（环境变量 NCBI_EMAIL），"
            "否则高峰期可能被限流。\n")

    entrez_sort = SORT_MAP[args.sort]

    try:
        if args.pmc or args.details:
            if args.pmc:
                pmid, body = get_paper_details_pmc(args.details)
                if not body:
                    fail(TOOL, "取 PMC 全文失败: %s" % pmid,
                         "该文献可能没有开放全文；可去掉 --pmc 走 PubMed 摘要")
                emit({"tool": TOOL, "ok": True, "mode": "pmc", "query": args.details,
                      "pmid": pmid, "chars": len(body), "text": body})
            detail = get_paper_details(args.details, entrez_sort,
                                       args.first_abstract_only)
            if detail is None:
                fail(TOOL, "PubMed 未找到匹配文献: %s" % args.details,
                     "标题若有拼写差异会检索不到，可先用 --keyword 搜出准确标题",
                     exit_code=1)
            emit({"tool": TOOL, "ok": True, "mode": "pubmed", "query": args.details,
                  "shape": "[title, PMID, DOI, Journal, Author, Year, abstract]",
                  "result": detail})
        else:
            papers = pubmed_crawler(args.keyword, args.num, entrez_sort,
                                    args.first_abstract_only)
            if not papers and args.strict_shape:
                # 上游无结果时返回的是这个哨兵对象，而不是空列表
                papers = [{"index": 0, "title": "No paper found",
                           "abstract": "No paper found"}]
            slim = [{"index": p["index"], "title": p["title"],
                     "abstract": (p["abstract"] or "")[:400]} for p in papers[:args.limit]]
            emit({"tool": TOOL, "ok": True, "mode": "crawler",
                  "keyword": args.keyword, "num": args.num,
                  "sort": args.sort, "entrez_sort": entrez_sort,
                  "count": len(papers), "returned": len(slim), "papers": slim})
    except urllib.error.HTTPError as exc:
        fail(TOOL, "NCBI 返回 HTTP %s" % exc.code,
             "稍后重试；频繁请求会被限流（可用 NCBI_EMAIL 声明身份）")
    except urllib.error.URLError as exc:
        fail(TOOL, "无法连接 NCBI: %s" % exc.reason,
             "PubMed 需要联网；检查网络或代理后重试")
    except ValueError as exc:
        fail(TOOL, str(exc), "NCBI 偶发返回截断内容，重试即可")
    except Exception as exc:
        fail(TOOL, "%s: %s" % (type(exc).__name__, exc))


if __name__ == "__main__":
    main()
