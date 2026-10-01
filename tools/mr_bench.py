#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
评测工具：算 MRAgent 各步 LLM 抽取结果的准确率 / 查准率 / 查全率 / F1。

对应上游论文复现用的 `step_2_test.py`（算 MRorNot 判定准确率）和
`step_5_test.py`（算 gwas_id 选择的 precision/recall/F1）。
这两个脚本在原仓库里是写死数据文件的实验代码，这里做成通用 CLI ——
只要给一对"地面真值列 / 模型预测列"就能算。

注意：上游还有 `step_1_test_SimCSE.py` / `step_9_test_SimCSE.py`，
它们依赖 SimCSE 模型算语义相似度，属论文实验环境，依赖较重，未纳入本工具包。

用法：
  # 准确率：两列是标称值（如 Yes/No）
  python mr_bench.py --file MR40.csv --gt MRorNot --pred MRorNot_gpt-4o --mode accuracy

  # 查准/查全/F1：两列是 list 字符串（如 "['ieu-a-1','ieu-b-40']"）
  python mr_bench.py --file gwas_test.csv --gt gwas_id_hum --pred gwas_id_gpt-4o --mode prf

  # 多模型对比：一次算多列
  python mr_bench.py --file MR40.csv --gt MRorNot --pred MRorNot_gpt-4o,MRorNot_llama3 --mode accuracy
"""

import argparse
import os
import re

from _common import emit, fail, parse_args_or_fail, read_csv_rows

TOOL = "mr-bench"


def parse_list(value):
    """把 "['a','b']" 或 "[a, b]" 解析成 list。上游用的是正则法，这里保持一致。"""
    if value is None:
        return []
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return []
    s = re.sub(r"[\[\]]", "", s)
    return [x.strip().strip("'\"") for x in s.split(",") if x.strip()]


def accuracy(rows, gt_col, pred_col):
    total = hit = 0
    skipped = 0
    for r in rows:
        g, p = r.get(gt_col), r.get(pred_col)
        if g is None or p is None or str(p).lower() in ("nan", "none", ""):
            skipped += 1
            continue
        total += 1
        if str(g).strip() == str(p).strip():
            hit += 1
    return {"correct": hit, "compared": total, "skipped": skipped,
            "accuracy": (hit / total) if total else None}


def prf(rows, gt_col, pred_col):
    ps, rs, f1s = [], [], []
    for r in rows:
        g, p = parse_list(r.get(gt_col)), parse_list(r.get(pred_col))
        if not g and not p:
            continue
        inter = set(g) & set(p)
        precision = (len(inter) / len(p)) if p else 0.0
        recall = (len(inter) / len(g)) if g else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        ps.append(precision)
        rs.append(recall)
        f1s.append(f1)
    def avg(xs):
        return (sum(xs) / len(xs)) if xs else None
    return {"rows": len(ps),
            "precision_avg": avg(ps), "recall_avg": avg(rs), "f1_avg": avg(f1s)}


def main():
    ap = argparse.ArgumentParser(description="评测 MRAgent 各步抽取质量")
    ap.add_argument("--file", required=True, help="CSV 文件")
    ap.add_argument("--gt", required=True, help="地面真值列名")
    ap.add_argument("--pred", required=True, help="预测列名（多列用逗号分隔可批量对比）")
    ap.add_argument("--mode", default="accuracy", choices=["accuracy", "prf"])
    args = parse_args_or_fail(ap, TOOL)

    if not os.path.exists(args.file):
        fail(TOOL, "文件不存在: %s" % args.file, exit_code=2)

    try:
        rows = read_csv_rows(args.file)
    except Exception as exc:
        fail(TOOL, "读取失败: %s" % exc)

    if not rows:
        fail(TOOL, "CSV 没有数据行", exit_code=2)

    cols = list(rows[0].keys())
    if args.gt not in cols:
        fail(TOOL, "真值列 %s 不存在" % args.gt, "现有列: %s" % ", ".join(cols), exit_code=2)

    pred_cols = [c.strip() for c in args.pred.split(",") if c.strip()]
    missing = [c for c in pred_cols if c not in cols]
    if missing:
        fail(TOOL, "预测列不存在: %s" % ", ".join(missing),
             "现有列: %s" % ", ".join(cols), exit_code=2)

    fn = accuracy if args.mode == "accuracy" else prf
    per_col = {}
    for c in pred_cols:
        try:
            per_col[c] = fn(rows, args.gt, c)
        except Exception as exc:
            per_col[c] = {"error": "%s: %s" % (type(exc).__name__, exc)}

    emit({"tool": TOOL, "ok": True, "file": os.path.abspath(args.file),
          "mode": args.mode, "gt_col": args.gt, "row_count": len(rows),
          "results": per_col})


if __name__ == "__main__":
    main()
