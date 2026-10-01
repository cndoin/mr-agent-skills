#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：MRAgent 提示词库。

上游把全部提示词硬编码在 `mragent/template_text.py`（10 个）与
`step_9_test_prompt.py`（12 个 step9 消融变体）里，用户只能改源码。
本工具把它们做成可列举、可查看、可渲染、可与装机版比对漂移的命令，
**不依赖 mragent**（提示词已 vendor 到 tools/prompts.json）。

用法：
  python mr_prompt.py --list
  python mr_prompt.py --list --group main
  python mr_prompt.py --show LLM_MR_template
  python mr_prompt.py --render pubmed_text_obo --var Outcome="back pain" \
      --var title="..." --var abstract="..."
  python mr_prompt.py --diff-mragent          # 装了 mragent 时比对是否漂移
"""

import argparse
import io
import json
import os
import sys

from _common import parse_args_or_fail, emit, fail

TOOL = "mr-prompt"
HERE = os.path.dirname(os.path.abspath(__file__))
LIB_PATH = os.path.join(HERE, "prompts.json")

# 上游 step9 里两个「官方主模板」其实与最丰富的消融变体同源，这里显式标注
EQUIVALENT = {
    "LLM_MR_template": "LLM_MR_template_one_shot_and_knowledge",
    "LLM_MR_MOE_template": "LLM_MR_MOE_template_one_shot_and_knowledge",
}


def load_lib():
    if not os.path.exists(LIB_PATH):
        fail(TOOL, "提示词库缺失: %s" % LIB_PATH,
             "该文件应从仓库一并分发；或运行 tools/gen_prompts.py 重新生成")
    try:
        return json.load(io.open(LIB_PATH, encoding="utf-8"))
    except Exception as exc:
        fail(TOOL, "提示词库解析失败: %s" % exc, LIB_PATH)


def find(lib, name):
    """在 main / step9_ablation 两处查找模板。"""
    if name in lib.get("main", {}):
        return "main", lib["main"][name]
    if name in lib.get("step9_ablation", {}):
        return "step9_ablation", lib["step9_ablation"][name]
    return None, None


def fuzzy(lib, name):
    """给近似名做提示。"""
    pool = list(lib.get("main", {})) + list(lib.get("step9_ablation", {}))
    low = name.lower()
    return [p for p in pool if low in p.lower()][:8]


def main():
    ap = argparse.ArgumentParser(
        description="MRAgent 提示词库（上游 10 主模板 + 12 step9 消融变体）")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="列出全部模板")
    g.add_argument("--show", metavar="NAME", help="打印某个模板的完整原文")
    g.add_argument("--render", metavar="NAME", help="渲染模板（需提供占位符变量）")
    g.add_argument("--diff-mragent", action="store_true",
                   help="与已安装 mragent 包里的提示词逐字比对（漂移检测）")
    ap.add_argument("--group", choices=["main", "step9_ablation"],
                    help="配合 --list 只看某一组")
    ap.add_argument("--var", action="append", default=[], metavar="K=V",
                    help="渲染变量，可重复。例: --var Outcome=\"back pain\"")
    ap.add_argument("--vars-file", metavar="JSON",
                    help="从 JSON 文件读渲染变量（object，键为占位符名）")
    ap.add_argument("--out", metavar="FILE", help="把渲染结果写到文件而不是 stdout")
    args = parse_args_or_fail(ap, TOOL)

    lib = load_lib()

    # ---------- --list ----------
    if args.list:
        groups = [args.group] if args.group else ["main", "step9_ablation"]
        payload = {"tool": TOOL, "ok": True, "library": LIB_PATH,
                   "source": lib.get("_meta", {}).get("source_repo"),
                   "total": len(lib.get("main", {})) + len(lib.get("step9_ablation", {})),
                   "groups": {}}
        for grp in groups:
            items = lib.get(grp, {})
            payload["groups"][grp] = [
                {"name": n,
                 "step": v.get("step") or v.get("model"),
                 "purpose": v.get("purpose") or v.get("variant_label"),
                 "chars": v.get("chars"),
                 "placeholders": v.get("placeholders")}
                for n, v in items.items()
            ]
        emit(payload)

    # ---------- --show ----------
    if args.show:
        grp, tpl = find(lib, args.show)
        if tpl is None:
            fail(TOOL, "找不到模板 %s" % args.show,
                 "近似名: %s" % (", ".join(fuzzy(lib, args.show)) or "无"),
                 exit_code=2)
        emit({"tool": TOOL, "ok": True, "group": grp, "name": args.show,
              "step": tpl.get("step") or tpl.get("model"),
              "purpose": tpl.get("purpose") or tpl.get("variant_label"),
              "placeholders": tpl["placeholders"], "chars": tpl["chars"],
              "text": tpl["text"]})

    # ---------- --render ----------
    if args.render:
        grp, tpl = find(lib, args.render)
        if tpl is None:
            fail(TOOL, "找不到模板 %s" % args.render,
                 "近似名: %s" % (", ".join(fuzzy(lib, args.render)) or "无"),
                 exit_code=2)

        variables = {}
        if args.vars_file:
            if not os.path.exists(args.vars_file):
                fail(TOOL, "变量文件不存在: %s" % args.vars_file, exit_code=2)
            try:
                obj = json.load(io.open(args.vars_file, encoding="utf-8"))
            except Exception as exc:
                fail(TOOL, "变量文件解析失败: %s" % exc, exit_code=2)
            if not isinstance(obj, dict):
                fail(TOOL, "变量文件必须是 JSON object", exit_code=2)
            variables.update({str(k): str(v) for k, v in obj.items()})
        for kv in args.var:
            if "=" not in kv:
                fail(TOOL, "--var 需要 K=V 形式，收到 %r" % kv, exit_code=2)
            k, v = kv.split("=", 1)
            variables[k.strip()] = v

        need = set(tpl["placeholders"])
        given = set(variables)
        missing = sorted(need - given)
        extra = sorted(given - need)
        if missing:
            fail(TOOL, "缺少占位符: %s" % ", ".join(missing),
                 "用 --var %s=... 补齐；模板 %s" % (missing[0], args.render),
                 exit_code=2)

        rendered = tpl["text"].format(**{k: variables[k] for k in need})
        if args.out:
            io.open(args.out, "w", encoding="utf-8", newline="\n").write(rendered)
            emit({"tool": TOOL, "ok": True, "group": grp, "name": args.render,
                  "out": os.path.abspath(args.out), "chars": len(rendered),
                  "unused_vars": extra})
        emit({"tool": TOOL, "ok": True, "group": grp, "name": args.render,
              "chars": len(rendered), "unused_vars": extra, "rendered": rendered})

    # ---------- --diff-mragent ----------
    if args.diff_mragent:
        try:
            import mragent.template_text as tt
        except ImportError as exc:
            fail(TOOL, "mragent 未安装，无法比对: %s" % exc,
                 "装到 Python 3.11/3.12 环境后再跑；或不装也能用 vendor 版提示词",
                 exit_code=2)
        rows, drift = [], []
        for name, item in lib["main"].items():
            installed = getattr(tt, name, None)
            if installed is None:
                rows.append({"name": name, "status": "装机版缺失"})
                drift.append(name)
            elif installed == item["text"]:
                rows.append({"name": name, "status": "一致"})
            else:
                rows.append({"name": name, "status": "不一致",
                             "vendor_chars": item["chars"], "installed_chars": len(installed)})
                drift.append(name)
        emit({"tool": TOOL, "ok": not drift, "compared": len(rows),
              "drift": drift, "rows": rows})

    fail(TOOL, "没有可执行的动作", exit_code=2)


if __name__ == "__main__":
    main()
