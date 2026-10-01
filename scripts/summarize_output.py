#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
解析 MRAgent 的 output/ 目录，产出结构化摘要。

不依赖 pandas —— 用标准库 csv 读，避免在 3.11/3.12 venv 之外的解释器中因
numpy/pandas 版本锁而无法运行。

用法：
  python summarize_output.py <output根目录或某个run目录>
  python summarize_output.py ./mragent-runs/back_pain_O_xxx/output

判成败的关键：mr_run.csv 是否存在。存在才说明真的跑了 MR。
"""

import csv
import json
import os
import sys

EXPOSURE_OUTCOME_CSV = "Exposure_and_Outcome.csv"
OUTCOME_SNP_CSV = "Outcome_SNP.csv"
MR_RUN_CSV = "mr_run.csv"


def read_csv_rows(path):
    """读 CSV 成 dict 列表；编码失败时退到 latin-1，绝不因此中断。"""
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except UnicodeDecodeError:
        with open(path, newline="", encoding="latin-1") as fh:
            return list(csv.DictReader(fh))
    except Exception as exc:
        return [{"__error__": "%s" % exc}]


def find_first(root, filename):
    for r, _d, files in os.walk(root):
        if filename in files:
            return os.path.join(r, filename)
    return None


def collect_pdfs(root):
    """按分析子目录聚合 PDF 产物。"""
    buckets = {}
    for r, _d, files in os.walk(root):
        pdfs = sorted(f for f in files if f.lower().endswith(".pdf"))
        if pdfs:
            rel = os.path.relpath(r, root).replace("\\", "/")
            buckets[rel] = pdfs
    return buckets


def summarize(root):
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return {"tool": "mragent-summarize", "ok": False,
                "error": "目录不存在: %s" % root}

    eo_path = find_first(root, EXPOSURE_OUTCOME_CSV)
    snp_path = find_first(root, OUTCOME_SNP_CSV)
    run_path = find_first(root, MR_RUN_CSV)

    report = {
        "tool": "mragent-summarize",
        "root": root,
        "ok": run_path is not None,
        "artifacts": {
            "exposure_and_outcome": eo_path,
            "outcome_snp": snp_path,
            "mr_run": run_path,
        },
    }

    if eo_path:
        rows = read_csv_rows(eo_path)
        mr_or_not = {}
        for row in rows:
            key = str(row.get("MRorNot", "<空>"))
            mr_or_not[key] = mr_or_not.get(key, 0) + 1
        pairs = []
        for row in rows:
            e, o = row.get("Exposure"), row.get("Outcome")
            if e and o and e != "None" and o != "None":
                pairs.append({"exposure": e, "outcome": o,
                              "MRorNot": row.get("MRorNot")})
        report["exposure_outcome"] = {
            "row_count": len(rows),
            "non_null_pairs": len(pairs),
            "MRorNot_distribution": mr_or_not,
            "pairs": pairs[:50],
        }

    if snp_path:
        rows = read_csv_rows(snp_path)
        hit = sum(1 for r in rows if str(r.get("opengwas", "")).upper() == "TRUE")
        with_gwas = sum(1 for r in rows if r.get("gwas_id") not in (None, "", "nan"))
        report["outcome_snp"] = {
            "row_count": len(rows),
            "opengwas_hit": hit,
            "with_gwas_id": with_gwas,
        }

    if run_path:
        rows = read_csv_rows(run_path)
        combos = []
        for row in rows:
            e, o = row.get("Exposure"), row.get("Outcome")
            if e and o:
                combos.append("%s -> %s" % (e, o))
        report["mr_run"] = {
            "row_count": len(rows),
            "combos": sorted(set(combos))[:100],
        }
    else:
        report["warning"] = ("未找到 mr_run.csv —— 说明流程没走到 step8。"
                             "若进程退出码为 0，极可能是 step3 判定所有对都已做过 MR 后 sys.exit(0)")

    report["pdfs"] = collect_pdfs(root)
    report["pdf_total"] = sum(len(v) for v in report["pdfs"].values())
    return report


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("用法: python summarize_output.py <output目录>\n")
        json.dump({"tool": "mragent-summarize", "ok": False,
                   "error": "缺少目录参数"}, sys.stdout, ensure_ascii=False, indent=2)
        return 2
    report = summarize(sys.argv[1])
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
