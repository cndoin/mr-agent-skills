#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读写 MRAgent 的三个中间 CSV —— 也就是"人工干预"这一步的程序化入口。

上游 web_demo.py 用 `st.data_editor` 让你在网页上改这三个表再保存；
本工具把同样的能力做成 CLI + JSON，这样 AI 也能直接改，不必人手点。

三个可编辑的表（名字是源码实测的，README 里写的是错的）：
  Exposure_and_Outcome.csv   暴露-结局对 + MRorNot 判定
  Outcome_SNP.csv            同义词 / opengwas 命中 / gwas_id
  mr_run.csv                 最终进入 MR 的组合

每一步修改都会先写一份 .bak 备份（只保留一份，覆盖式）。

用法：
  # 查看
  python edit_csv.py --dir <run目录> --file Exposure_and_Outcome.csv --show

  # 改某个单元格（第 0 行的 MRorNot 改成 No）
  python edit_csv.py --dir ... --file mr_run.csv --row 0 --col MRorNot --value No

  # 删第 3 行
  python edit_csv.py --dir ... --file Exposure_and_Outcome.csv --delete-row 3

  # 追加一行
  python edit_csv.py --dir ... --file Exposure_and_Outcome.csv \
      --add-row '{"Outcome":"back pain","Exposure":"smoking","oeID":9}'

  # 从 JSON 整体覆盖
  python edit_csv.py --dir ... --file mr_run.csv --replace rows.json
"""

import argparse
import csv
import json
import os
import sys

from _common import parse_args_or_fail, emit, fail, read_csv_rows

TOOL = "mr-edit-csv"
VALID_FILES = ("Exposure_and_Outcome.csv", "Outcome_SNP.csv", "mr_run.csv")


def resolve(dirpath, filename):
    if filename not in VALID_FILES:
        return None, ("不允许编辑 %s" % filename,
                      "只允许: %s" % ", ".join(VALID_FILES))
    # 允许传 run 目录或 output 下的具体目录，向上/向下找一层
    for cand in (os.path.join(dirpath, filename),
                 os.path.join(dirpath, "output", filename)):
        if os.path.exists(cand):
            return cand, None
    for root, _d, files in os.walk(dirpath):
        if filename in files:
            return os.path.join(root, filename), None
    return None, ("在 %s 下找不到 %s" % (dirpath, filename),
                  "先跑 run_mr.py 至少到 step1 才有这个文件")


def write_rows(path, fieldnames, rows):
    bak = path + ".bak"
    try:
        if os.path.exists(path):
            with open(path, "rb") as src, open(bak, "wb") as dst:
                dst.write(src.read())
    except OSError as exc:
        sys.stderr.write("警告: 备份失败 %s\n" % exc)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser(description="编辑 MRAgent 中间 CSV")
    ap.add_argument("--dir", required=True, help="run 目录（含 output/）")
    ap.add_argument("--file", required=True, help="要编辑的文件名")
    ap.add_argument("--show", action="store_true", help="只查看，不修改")
    ap.add_argument("--row", type=int, help="行号（从 0 开始）")
    ap.add_argument("--col", help="列名")
    ap.add_argument("--value", help="新值")
    ap.add_argument("--delete-row", type=int, help="删除指定行号")
    ap.add_argument("--add-row", help="追加一行，JSON 对象字符串")
    ap.add_argument("--replace", help="用 JSON 文件整体覆盖（list of object）")
    ap.add_argument("--limit", type=int, default=100, help="--show 显示行数上限")
    args = parse_args_or_fail(ap, TOOL)

    path, err = resolve(args.dir, args.file)
    if err:
        fail(TOOL, err[0], err[1], exit_code=2)

    rows = read_csv_rows(path)
    with open(path, newline="", encoding="utf-8") as fh:
        fieldnames = list(csv.DictReader(fh).fieldnames or [])

    if args.show or not (args.col or args.delete_row is not None
                         or args.add_row or args.replace):
        emit({"tool": TOOL, "ok": True, "action": "show", "path": path,
              "columns": fieldnames, "row_count": len(rows),
              "rows": rows[:args.limit]})

    action = None
    if args.replace:
        try:
            new_rows = json.load(open(args.replace, encoding="utf-8"))
        except Exception as exc:
            fail(TOOL, "读取 %s 失败: %s" % (args.replace, exc), exit_code=2)
        if not isinstance(new_rows, list):
            fail(TOOL, "JSON 顶层必须是数组", exit_code=2)
        cols = list(fieldnames)
        for r in new_rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        write_rows(path, cols, new_rows)
        action = "replace"

    elif args.add_row:
        try:
            obj = json.loads(args.add_row)
        except Exception as exc:
            fail(TOOL, "--add-row 不是合法 JSON: %s" % exc, exit_code=2)
        if not isinstance(obj, dict):
            fail(TOOL, "--add-row 必须是 JSON 对象", exit_code=2)
        rows.append(obj)
        cols = list(fieldnames) + [k for k in obj if k not in fieldnames]
        write_rows(path, cols, rows)
        action = "add-row"

    elif args.delete_row is not None:
        idx = args.delete_row
        if idx < 0 or idx >= len(rows):
            fail(TOOL, "行号 %d 越界（共 %d 行）" % (idx, len(rows)), exit_code=2)
        removed = rows.pop(idx)
        write_rows(path, fieldnames, rows)
        action = "delete-row"
        emit({"tool": TOOL, "ok": True, "action": action, "path": path,
              "removed": removed, "row_count": len(rows),
              "hint": "改完继续跑后续 step 即可生效"})

    elif args.col:
        if args.row is None or args.value is None:
            fail(TOOL, "--col 需要同时给 --row 和 --value", exit_code=2)
        idx = args.row
        if idx < 0 or idx >= len(rows):
            fail(TOOL, "行号 %d 越界（共 %d 行）" % (idx, len(rows)), exit_code=2)
        if args.col not in fieldnames:
            fail(TOOL, "列 %s 不存在" % args.col,
                 "现有列: %s" % ", ".join(fieldnames), exit_code=2)
        old = rows[idx].get(args.col)
        rows[idx][args.col] = args.value
        write_rows(path, fieldnames, rows)
        action = "set-cell"
        emit({"tool": TOOL, "ok": True, "action": action, "path": path,
              "row": idx, "col": args.col, "old": old, "new": args.value,
              "hint": "改完继续跑后续 step 即可生效"})

    if action in ("replace", "add-row"):
        emit({"tool": TOOL, "ok": True, "action": action, "path": path,
              "row_count": len(rows),
              "hint": "改完继续跑后续 step 即可生效"})


if __name__ == "__main__":
    main()
