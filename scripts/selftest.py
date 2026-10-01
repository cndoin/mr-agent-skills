#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""mr-agent 全量自检。

    python scripts/selftest.py            # 全量
    python scripts/selftest.py --quick    # 跳过真实网络探测，离线也能跑完
    python scripts/selftest.py --json     # 结果输出成 JSON，供 CI 消费

设计要点：

1. **全部用 __file__ 定位**，不硬编码任何绝对路径 —— 从工作区跑、从
   ~/.claude/skills、~/.codex/skills 或 ~/.dsh/skills 跑，结果都一样。
2. **解释器用 sys.executable**，不写死路径。注意这不等于要求 3.12：
   本自检验证的是「脚本的契约与降级行为」，完整 MR 需要 3.11/3.12 的
   另一个环境（preflight 会报出来）。
3. **每个用例前清空凭据环境变量**，否则"缺 token 应报错"这类用例会
   因为外部环境里恰好有 token 而假失败 —— 测试必须可重复。
4. 退出码：全绿 0，有失败 1。CI 可直接接。
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL_ROOT, "scripts")
TOOLS = os.path.join(SKILL_ROOT, "tools")
PY = sys.executable

# 会被清理的环境变量：保证"缺凭据"类用例不被宿主环境污染
CRED_VARS = ["MRAGENT_GWAS_TOKEN", "OPENGWAS_JWT", "MRAGENT_AI_KEY",
             "OPENAI_API_KEY"]

RESULTS = []
QUICK = False


def clean_env(extra=None):
    """复制 os.environ 并去掉凭据与 PYTHONPATH。"""
    e = dict(os.environ)
    for k in CRED_VARS:
        e.pop(k, None)
    e.pop("PYTHONPATH", None)  # 防止宿主环境里的假 mragent 影响导入
    if extra:
        e.update(extra)
    return e


def run(args, cwd=None, env=None, timeout=180):
    try:
        p = subprocess.run([PY] + list(args), capture_output=True, text=True,
                           cwd=cwd, env=clean_env(env), timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return "TIMEOUT", "", ""
    except Exception as exc:
        return "EXC", "", "%s: %s" % (type(exc).__name__, exc)


def case(name, args, expect_exit=None, cwd=None, env=None, check=None,
         must_json=True, group=""):
    rc, out, err = run(args, cwd=cwd, env=env)
    ok, detail = True, []
    if expect_exit is not None and rc != expect_exit:
        ok = False
        detail.append("exit=%r 期望=%r" % (rc, expect_exit))
    data = {}
    if must_json:
        try:
            data = json.loads(out)
        except Exception as exc:
            ok = False
            detail.append("stdout 非合法 JSON: %s | 前120=%r" % (str(exc)[:60], out[:120]))
    if ok and check and not check(data):
        ok = False
        detail.append("断言失败")
    RESULTS.append({"case": name, "group": group, "ok": ok, "exit": rc,
                    "detail": "; ".join(detail)})
    print("[%s] %-40s exit=%r %s" % ("PASS" if ok else "FAIL", name, rc,
                                     "-> " + "; ".join(detail) if detail else ""))
    return data


def skip(name, why, group=""):
    RESULTS.append({"case": name, "group": group, "ok": True, "exit": "-",
                    "detail": "SKIP: " + why})
    print("[SKIP] %-40s %s" % (name, why))


def mkrun(base, name, files):
    """造一个形如 output/<run>/ 的结果目录。"""
    d = os.path.join(base, name, "output", "run1")
    os.makedirs(d, exist_ok=True)
    for fn, content in files.items():
        with io.open(os.path.join(d, fn), "wb") as fh:
            fh.write(content if isinstance(content, bytes)
                     else content.encode("utf-8"))
    return d


# ------------------------------------------------------------------ A
def group_a(quick):
    print("=" * 78)
    print("A. preflight.py 边界")
    print("=" * 78)
    PRE = os.path.join(SCRIPTS, "preflight.py")
    case("A1 默认(当前解释器)", [PRE, "--no-network"], 0, group="A")
    case("A2 --python 不存在", [PRE, "--python", os.path.join("no", "such", "python"),
                                "--no-network"], 0, group="A")
    case("A3 --python 指向非可执行文件", [PRE, "--python", __file__, "--no-network"],
         0, group="A")
    case("A4 --python 空字符串", [PRE, "--python", "", "--no-network"], 0, group="A")
    case("A5 带 token 环境变量", [PRE, "--no-network"], 0,
         env={"MRAGENT_GWAS_TOKEN": "fake", "OPENAI_API_KEY": "fake"}, group="A")
    import importlib.util
    spec = importlib.util.spec_from_file_location("mragent_preflight", PRE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Metadata exclusion is checked directly; no installed 3.9.7 interpreter is needed.
    ok = (not module.is_supported_python((3, 9, 7))
          and module.is_supported_python((3, 9, 6))
          and module.is_supported_python((3, 12, 0)))
    RESULTS.append({"case": "A6 上游排除 Python 3.9.7", "group": "A",
                    "ok": ok, "exit": 0, "detail": ""})
    print("[%s] %-40s" % ("PASS" if ok else "FAIL", "A6 上游排除 Python 3.9.7"))
    if quick:
        skip("A7 网络探测(真实)", "--quick 跳过", group="A")
    else:
        case("A7 网络探测(真实)", [PRE], 0, group="A")


# ------------------------------------------------------------------ B
def group_b():
    print()
    print("=" * 78)
    print("B. run_mr.py 边界")
    print("=" * 78)
    RUN = os.path.join(SCRIPTS, "run_mr.py")
    case("B1 dry-run mode=O 不创建目录", [RUN, "--mode", "O", "--outcome", "back pain",
                               "--dry-run"], 0,
         check=lambda d: bool(d.get("workdir")) and not os.path.exists(d.get("workdir", "")), group="B")
    case("B2 dry-run mode=E", [RUN, "--mode", "E", "--exposure", "BMI",
                               "--dry-run"], 0, group="B")
    case("B3 dry-run mode=OE", [RUN, "--mode", "OE", "--exposure", "a",
                                "--outcome", "b", "--dry-run"], 0, group="B")
    case("B4 缺 outcome(mode=O)", [RUN, "--mode", "O", "--dry-run"], 2, group="B")
    case("B5 非法 steps=abc", [RUN, "--mode", "O", "--outcome", "x",
                               "--steps", "abc", "--dry-run"], 2, group="B")
    case("B6 空 steps(应报错)", [RUN, "--mode", "O", "--outcome", "x",
                                 "--steps", "", "--dry-run"], 2, group="B")
    case("B7 越界 steps=99", [RUN, "--mode", "O", "--outcome", "x",
                              "--steps", "99", "--dry-run"], 2, group="B")
    case("B8 负数 steps=-1", [RUN, "--mode", "O", "--outcome", "x",
                              "--steps", "-1", "--dry-run"], 2, group="B")
    case("B8a 重复 steps", [RUN, "--mode", "O", "--outcome", "x",
                            "--steps", "1,1", "--dry-run"], 2, group="B")
    case("B8b 默认关闭 UMLS", [RUN, "--mode", "O", "--outcome", "x",
                               "--dry-run"], 0,
         check=lambda d: d.get("config", {}).get("synonyms") is False, group="B")
    case("B8c 显式开启 UMLS", [RUN, "--mode", "O", "--outcome", "x",
                               "--synonyms", "--dry-run"], 0,
         check=lambda d: d.get("config", {}).get("synonyms") is True, group="B")
    with tempfile.TemporaryDirectory(prefix="mragent-stale-") as root:
        args = [RUN, "--mode", "O", "--outcome", "x", "--tag", "reuse",
                "--workdir", root, "--dry-run"]
        _rc, out, _err = run(args)
        stale = json.loads(out)["workdir"]
        old_csv = os.path.join(stale, "output", "old", "mr_run.csv")
        os.makedirs(os.path.dirname(old_csv), exist_ok=True)
        with open(old_csv, "w", encoding="utf-8") as fh:
            fh.write("stale result")
        args.remove("--dry-run")
        rc, out, _err = run(args, env={"MRAGENT_GWAS_TOKEN": "fake",
                                      "OPENAI_API_KEY": "fake"})
        try:
            data = json.loads(out)
            ok = rc == 2 and data.get("workdir") != stale and data.get("ok") is False
            detail = data.get("workdir", "")
        except Exception as exc:
            ok, detail = False, str(exc)
        RESULTS.append({"case": "B8d 不复用旧结果目录", "group": "B", "ok": ok,
                        "exit": rc, "detail": detail})
        print("[%s] %-40s exit=%r" % ("PASS" if ok else "FAIL",
                                       "B8d 不复用旧结果目录", rc))
    case("B9 未装 mragent 真跑", [RUN, "--mode", "O", "--outcome", "x",
                                  "--steps", "1"], 2,
         env={"MRAGENT_GWAS_TOKEN": "fake", "OPENAI_API_KEY": "fake"}, group="B")
    case("B10 缺 token 真跑", [RUN, "--mode", "O", "--outcome", "x",
                               "--steps", "1"], 2, group="B")

    # auto 模式推断
    for mode, args, label in [
            ("O", ["--outcome", "back pain"], "B16 auto 只给 outcome"),
            ("E", ["--exposure", "BMI"], "B17 auto 只给 exposure"),
            ("OE", ["--exposure", "BMI", "--outcome", "back pain"],
             "B18 auto 两个都给")]:
        case(label, [RUN, "--mode", "auto"] + args + ["--dry-run"], 0,
             check=lambda d, m=mode: d.get("mode") == m, group="B")
    case("B19 auto 都不给", [RUN, "--mode", "auto", "--dry-run"], 2, group="B")

    # 路径穿越：tag / outcome 都可能被塞进目录名
    for tag, label in [("../../evil", "B11 tag 路径穿越"),
                       ("a/b\\c", "B12 tag 含分隔符"),
                       ("  spaced  ", "B13 tag 含空格"),
                       ("中文tag", "B14 tag 中文")]:
        rc, out, _err = run([RUN, "--mode", "O", "--outcome", "x",
                             "--tag", tag, "--dry-run"])
        try:
            wd = json.loads(out).get("workdir", "")
            escaped = (".." in wd.replace("\\", "/").split("/")[-3:]) or \
                      (not os.path.isabs(wd))
            ok = (rc == 0) and (not escaped)
            RESULTS.append({"case": label, "group": "B", "ok": ok, "exit": rc,
                            "detail": "workdir=%s" % wd})
            print("[%s] %-40s workdir=%s" % ("PASS" if ok else "FAIL", label, wd))
        except Exception as exc:
            RESULTS.append({"case": label, "group": "B", "ok": False,
                            "exit": rc, "detail": str(exc)})
            print("[FAIL] %-40s %s" % (label, exc))

    rc, out, _err = run([RUN, "--mode", "O", "--outcome", "..", "..", "etc",
                         "passwd", "--dry-run"])
    try:
        wd = json.loads(out).get("workdir", "")
        ok = ".." not in wd.split("mragent-runs")[-1]
        RESULTS.append({"case": "B15 outcome 路径穿越", "group": "B", "ok": ok,
                        "exit": rc, "detail": wd})
        print("[%s] %-40s workdir=%s" % ("PASS" if ok else "FAIL",
                                         "B15 outcome 路径穿越", wd))
    except Exception as exc:
        RESULTS.append({"case": "B15 outcome 路径穿越", "group": "B",
                        "ok": False, "exit": rc, "detail": str(exc)})
        print("[FAIL] B15 %s" % exc)


# ------------------------------------------------------------------ C
def group_c(base):
    print()
    print("=" * 78)
    print("C. summarize_output.py 边界（畸形输入）")
    print("=" * 78)
    SUM = os.path.join(SCRIPTS, "summarize_output.py")
    for label, d in [
        ("C1 空 CSV(仅表头)",
         mkrun(base, "empty", {"Exposure_and_Outcome.csv":
                               "index,Outcome,Exposure,oeID,MRorNot\n"})),
        ("C2 零字节 CSV", mkrun(base, "zero", {"Exposure_and_Outcome.csv": ""})),
        ("C3 编码异常(latin1)",
         mkrun(base, "latin", {"Exposure_and_Outcome.csv":
                               b"index,Outcome\n1,caf\xe9\n"})),
        ("C4 列缺失", mkrun(base, "nocol",
                            {"Exposure_and_Outcome.csv": "a,b,c\n1,2,3\n"})),
        ("C5 含 None 值",
         mkrun(base, "none", {"Exposure_and_Outcome.csv":
                              "Outcome,Exposure,MRorNot\nNone,None,No\n"})),
        ("C6 完整三件套", mkrun(base, "full", {
            "Exposure_and_Outcome.csv":
                "Outcome,Exposure,oeID,dummy\nback pain,BMI,1,x\n",
            "Outcome_SNP.csv": "OE,sID,opengwas,gwas_id\nBMI,0,True,['ieu-b-40']\n",
            "mr_run.csv": "Exposure,Outcome,oeID\nBMI,back pain,1\n"})),
    ]:
        case(label, [SUM, d], None, group="C")

    deep = mkrun(base, "deep", {"mr_run.csv": "Exposure,Outcome\nA,B\n"})
    cur = deep
    for i in range(12):
        cur = os.path.join(cur, "lvl%d" % i)
        os.makedirs(cur, exist_ok=True)
    with io.open(os.path.join(cur, "x.pdf"), "w") as fh:
        fh.write("%PDF")
    case("C7 深层嵌套 PDF", [SUM, deep], 0, group="C")
    case("C8 目录不存在", [SUM, os.path.join(base, "nope")], 1, group="C")
    case("C9 无参数", [SUM], 2, group="C")
    case("C10 参数是文件不是目录",
         [SUM, os.path.join(base, "full", "output", "run1", "mr_run.csv")], 1,
         group="C")
    # --help 必须走 argparse 的 usage（exit 0），而不是被当成目录路径。
    # 修复前的行为：--help 被当作目录 → 返回 "目录不存在" 的 JSON，exit 1。
    rc, out, err = run([SUM, "--help"], cwd=SCRIPTS)
    ok = rc == 0 and "usage" in (out + err).lower()
    RESULTS.append({"case": "C11 summarize --help", "group": "C", "ok": ok,
                    "exit": rc, "detail": "" if ok else "stdout前80=%r" % out[:80]})
    print("[%s] %-40s exit=%r" % ("PASS" if ok else "FAIL", "C11 summarize --help", rc))


# ------------------------------------------------------------------ D
def group_d(base):
    print()
    print("=" * 78)
    print("D. 工具包：不依赖 mragent，本机可直接实测")
    print("=" * 78)
    run_dir = os.path.join(base, "back_pain_O_test", "output", "back_pain_gpt-4o")
    os.makedirs(os.path.join(run_dir, "BMI_back_pain", "sub"), exist_ok=True)
    io.open(os.path.join(run_dir, "Exposure_and_Outcome.csv"), "w",
            encoding="utf-8").write(
        "index,Outcome,Exposure,oeID,MRorNot,title\n"
        "1,back pain,body mass index,1,No,t1\n"
        "2,back pain,smoking,2,Yes,t2\n"
        "3,back pain,osteoarthritis,3,No,t3\n")
    io.open(os.path.join(run_dir, "Outcome_SNP.csv"), "w", encoding="utf-8").write(
        "OE,sID,opengwas,gwas_id\nback pain,0,True,\"['ieu-a-1']\"\n"
        "BMI,1,True,\"['ieu-b-40']\"\n")
    io.open(os.path.join(run_dir, "mr_run.csv"), "w", encoding="utf-8").write(
        "Exposure,Outcome,oeID\nbody mass index,back pain,1\n")
    io.open(os.path.join(run_dir, "run.log"), "w").write("noise")
    io.open(os.path.join(run_dir, "test.R"), "w").write(
        'Sys.setenv(OPENGWAS_JWT="rawtoken")\n')
    for n in ("pic.scatterplot.pdf", "report.pdf"):
        io.open(os.path.join(run_dir, "BMI_back_pain", "sub", n), "w").write("%PDF")

    d = case("D1 export_results 打包", ["export_results.py", run_dir], 0,
             cwd=TOOLS, check=lambda x: x.get("file_count", 0) >= 5 and x.get("ok"),
             group="D")
    skipped = d.get("skipped") or []
    # 打包必须排除 test.R —— 上游把明文 JWT 写进这个文件，见 SECURITY.md
    ok = "test.R" in skipped
    RESULTS.append({"case": "D1b 打包排除 test.R", "group": "D", "ok": ok,
                    "exit": 0, "detail": "skipped=%s" % skipped})
    print("[%s] %-40s skipped=%s" % ("PASS" if ok else "FAIL",
                                     "D1b 打包排除 test.R", skipped))

    case("D2 export 目录不存在",
         ["export_results.py", os.path.join(base, "nope")], 2, cwd=TOOLS, group="D")
    case("D3 edit_csv --show", ["edit_csv.py", "--dir", run_dir, "--file",
                                "Exposure_and_Outcome.csv", "--show"], 0,
         cwd=TOOLS, check=lambda x: x.get("row_count") == 3, group="D")
    case("D4 edit_csv 改单元格", ["edit_csv.py", "--dir", run_dir, "--file",
                                  "Exposure_and_Outcome.csv", "--row", "1",
                                  "--col", "MRorNot", "--value", "No"], 0,
         cwd=TOOLS, check=lambda x: x.get("action") == "set-cell"
         and x.get("old") == "Yes", group="D")
    case("D5 edit_csv 删行", ["edit_csv.py", "--dir", run_dir, "--file",
                              "Exposure_and_Outcome.csv", "--delete-row", "2"], 0,
         cwd=TOOLS, group="D")
    case("D6 edit_csv 加行", ["edit_csv.py", "--dir", run_dir, "--file",
                              "Exposure_and_Outcome.csv", "--add-row",
                              '{"Outcome":"back pain","Exposure":"vitamin D",'
                              '"oeID":9}'], 0, cwd=TOOLS, group="D")
    case("D7 edit_csv 越界行号", ["edit_csv.py", "--dir", run_dir, "--file",
                                  "mr_run.csv", "--row", "99", "--col", "x",
                                  "--value", "y"], 2, cwd=TOOLS, group="D")
    case("D8 edit_csv 非法文件名", ["edit_csv.py", "--dir", run_dir, "--file",
                                    "evil.csv", "--show"], 2, cwd=TOOLS, group="D")
    case("D9 edit_csv 备份存在", ["edit_csv.py", "--dir", run_dir, "--file",
                                  "mr_run.csv", "--show"], 0, cwd=TOOLS, group="D")

    # 离线 GWAS 需要 opengwas.csv；仓库不分发它，缺失时先尝试下载
    def gwas_ready():
        rc, out, _ = run(["mr_gwas.py", "--keyword", "back pain", "--limit", "1"],
                         cwd=TOOLS)
        try:
            return json.loads(out).get("ok") is True
        except Exception:
            return False
    if not gwas_ready():
        sys.stderr.write("[selftest] 离线清单缺失，尝试下载…\n")
        run(["mr_gwas.py", "--fetch"], cwd=TOOLS, timeout=300)

    if gwas_ready():
        case("D10 mr_gwas 离线检索", ["mr_gwas.py", "--keyword", "back pain",
                                      "--limit", "3"], 0, cwd=TOOLS,
             check=lambda x: x.get("hit_count", 0) > 0, group="D")
        case("D11 mr_gwas 无命中",
             ["mr_gwas.py", "--keyword", "zzz_nonexistent_trait_xyz"], 0,
             cwd=TOOLS, check=lambda x: x.get("ok") is False
             and "未命中" in (x.get("note") or ""), group="D")
        case("D12 mr_gwas 精确匹配", ["mr_gwas.py", "--keyword", "Body mass index",
                                      "--exact", "--limit", "3"], 0, cwd=TOOLS,
             group="D")
    else:
        for n in ("D10 mr_gwas 离线检索", "D11 mr_gwas 无命中",
                  "D12 mr_gwas 精确匹配"):
            skip(n, "opengwas.csv 不可用（网络受限），请先 --fetch", group="D")
    case("D13 mr_gwas 缺 keyword", ["mr_gwas.py"], 2, cwd=TOOLS, group="D")
    case("D14 serve_web --check", ["serve_web.py", "--check"], 2, cwd=TOOLS,
         check=lambda x: x.get("streamlit") is False, group="D")

    # 评测工具（不依赖 mragent）
    bench = os.path.join(base, "bench")
    os.makedirs(bench, exist_ok=True)
    io.open(os.path.join(bench, "acc.csv"), "w", encoding="utf-8").write(
        "MRorNot,MRorNot_gpt4o\nYes,Yes\nNo,No\nYes,Yes\nNo,No\n")
    case("D15 mr_bench 准确率", ["mr_bench.py", "--file",
                                 os.path.join(bench, "acc.csv"), "--gt",
                                 "MRorNot", "--pred", "MRorNot_gpt4o",
                                 "--mode", "accuracy"], 0, cwd=TOOLS,
         check=lambda x: x.get("ok") is True, group="D")


# ------------------------------------------------------------------ E
def group_e():
    print()
    print("=" * 78)
    print("E. 工具包：依赖 mragent 的，验证降级路径（本机无 3.12 环境）")
    print("=" * 78)
    # mr_pubmed 已改为原生 NCBI E-utilities 实现（不再 import mragent），
    # 所以原来的「无 mragent 应 exit 2」不再成立 —— 换成两条离线的确定性断言。
    _src = io.open(os.path.join(TOOLS, "mr_pubmed.py"), encoding="utf-8").read()
    _ok = "require_mragent" not in _src and "eutils.ncbi.nlm.nih.gov" in _src
    RESULTS.append({"case": "E1 mr_pubmed 已脱离 mragent", "group": "E", "ok": _ok,
                    "exit": 0, "detail": "" if _ok else "仍引用 require_mragent 或未用 E-utilities"})
    print("[%s] %-40s %s" % ("PASS" if _ok else "FAIL", "E1 mr_pubmed 已脱离 mragent", ""))
    case("E2 mr_pubmed --num 0 参数校验",
         ["mr_pubmed.py", "--keyword", "x", "--num", "0"], 2, cwd=TOOLS,
         check=lambda x: "正整数" in (x.get("error") or ""), group="E")
    case("E3 mr_synonyms 缺 key", ["mr_synonyms.py", "--term", "BMI"], 2,
         cwd=TOOLS, check=lambda x: "UMLS" in (x.get("error") or ""), group="E")
    case("E4 mr_llm 缺 key", ["mr_llm.py", "--prompt", "hi"], 2, cwd=TOOLS,
         check=lambda x: "key" in (x.get("error") or ""), group="E")
    # 换成离线确定性的用例：指向一个必然拒绝连接的端口。
    # 原来这条是"无 mragent 应 exit 2"，但 mr_llm 已改为原生实现，
    # 带 key 时会真去打 api.openai.com（401，非确定性），不适合做单测。
    case("E5 mr_llm 服务不可达",
         ["mr_llm.py", "--prompt", "hi", "--model-type", "ollama",
          "--model", "llama3", "--base-url", "http://127.0.0.1:1"], 1,
         cwd=TOOLS, check=lambda x: "无法连接" in (x.get("error") or ""), group="E")
    case("E6 mr_eval 缺参数", ["mr_eval.py"], 2, cwd=TOOLS, group="E")
    case("E7 mr_eval --mrornot 缺 exposure",
         ["mr_eval.py", "--mrornot", "--outcome", "x"], 2, cwd=TOOLS, group="E")
    # online 模式不再复刻上游那套已失效的 HTML 爬虫，改为要求 OpenGWAS JWT。
    # 断言：无 JWT 时 exit 2，且提示里要说明上游行为已失效、本工具不复刻。
    case("E8 mr_gwas online 无 JWT",
         ["mr_gwas.py", "--keyword", "BMI", "--mode", "online"], 2, cwd=TOOLS,
         check=lambda x: "JWT" in (x.get("error") or "")
         and "失效" in (x.get("hint") or ""), group="E")
    # 假 JWT 应当被 OpenGWAS 拒绝（HTTP 401）并在本工具里变成结构化错误，
    # 而不是抛出堆栈。这条会真的打一次网络（--quick 时跳过）。
    if not QUICK:
        case("E9 mr_gwas online 假 JWT 被拒",
             ["mr_gwas.py", "--keyword", "BMI", "--mode", "online"], 1, cwd=TOOLS,
             env={"OPENGWAS_JWT": "bogus.jwt.value"},
             check=lambda x: "401" in (x.get("error") or ""), group="E")
    else:
        skip("E9 mr_gwas online 假 JWT 被拒", "--quick 跳过真实网络", group="E")


# ------------------------------------------------------------------ F/G
def group_fg():
    print()
    print("=" * 78)
    print("F. 参数契约：缺 required 参数必须返回结构化 JSON（exit 2）")
    print("=" * 78)
    for name, script, cwd, extra in [
            ("F1 mr_pubmed 无参数", "mr_pubmed.py", TOOLS, []),
            ("F2 mr_gwas 无参数", "mr_gwas.py", TOOLS, []),
            ("F3 mr_synonyms 缺 --term", "mr_synonyms.py", TOOLS, []),
            ("F4 mr_llm 缺 --prompt", "mr_llm.py", TOOLS, []),
            ("F5 mr_eval 无参数", "mr_eval.py", TOOLS, []),
            ("F6 mr_bench 无参数", "mr_bench.py", TOOLS, []),
            ("F7 export_results 缺目录", "export_results.py", TOOLS, []),
            ("F8 edit_csv 缺 --dir/--file", "edit_csv.py", TOOLS, []),
            ("F9 run_mr 缺 --mode", "run_mr.py", SCRIPTS, []),
    ]:
        case(name, [script] + extra, 2, cwd=cwd, group="F",
             check=lambda x: bool(x.get("error")))

    print()
    print("G. --help 不应被当成错误（exit 0）")
    print("-" * 78)
    for name, script, cwd in [("G1 mr_gwas --help", "mr_gwas.py", TOOLS),
                              ("G2 run_mr --help", "run_mr.py", SCRIPTS),
                              ("G3 edit_csv --help", "edit_csv.py", TOOLS),
                              ("G4 mr_bench --help", "mr_bench.py", TOOLS),
                              ("G5 summarize --help", "summarize_output.py", SCRIPTS),
                              ("G6 mr_prompt --help", "mr_prompt.py", TOOLS),
                              ("G7 mr_pubmed --help", "mr_pubmed.py", TOOLS)]:
        rc, out, _ = run([script, "--help"], cwd=cwd)
        ok = rc == 0 and "usage" in out.lower()
        RESULTS.append({"case": name, "group": "G", "ok": ok, "exit": rc,
                        "detail": "" if ok else "stdout前80=%r" % out[:80]})
        print("[%s] %-40s exit=%r" % ("PASS" if ok else "FAIL", name, rc))


# ------------------------------------------------------------------ H
def group_h():
    print()
    print("=" * 78)
    print("H. 开源卫生：不应出现硬编码凭据")
    print("=" * 78)
    import re
    pats = [re.compile(r"sk-[A-Za-z0-9]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
            re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", re.I)]  # API keys/JWT/UUID keys
    bad = []
    for root, dirs, files in os.walk(SKILL_ROOT):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for fn in files:
            if not fn.endswith((".py", ".md")):
                continue
            p = os.path.join(root, fn)
            try:
                txt = io.open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for pat in pats:
                if pat.search(txt):
                    bad.append(os.path.relpath(p, SKILL_ROOT))
    ok = not bad
    RESULTS.append({"case": "H1 无硬编码凭据", "group": "H", "ok": ok,
                    "exit": 0, "detail": ",".join(bad)})
    print("[%s] %-40s %s" % ("PASS" if ok else "FAIL", "H1 无硬编码凭据",
                             "" if ok else bad))

    # 仓库不该带着 10MB 第三方数据
    csv_present = os.path.exists(os.path.join(SKILL_ROOT, "opengwas.csv"))
    RESULTS.append({"case": "H2 opengwas.csv 未入库", "group": "H",
                    "ok": not csv_present, "exit": 0,
                    "detail": "存在于技能目录（应由 install.py 放到全局缓存）"
                              if csv_present else ""})
    print("[%s] %-40s %s" % ("PASS" if not csv_present else "FAIL",
                             "H2 opengwas.csv 未入库",
                             "技能目录内存在副本" if csv_present else "干净"))

    # 安装复制规则必须排除用户下载到技能根目录的第三方清单。
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mragent_install", os.path.join(SKILL_ROOT, "install.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        excluded = "opengwas.csv" in module._ignore(SKILL_ROOT, ["opengwas.csv"])
        RESULTS.append({"case": "H3 安装排除第三方清单", "group": "H",
                        "ok": excluded, "exit": 0, "detail": ""})
        print("[%s] %-40s" % ("PASS" if excluded else "FAIL", "H3 安装排除第三方清单"))
    except Exception as exc:
        RESULTS.append({"case": "H3 安装排除第三方清单", "group": "H",
                        "ok": False, "exit": 0, "detail": str(exc)})
        print("[FAIL] H3 安装排除第三方清单 %s" % exc)

    # Codex / DeepSeek Harness 的安装根目录可配置，且默认路径稳定。
    old = {key: os.environ.get(key) for key in ("CODEX_HOME", "DSH_HOME")}
    try:
        os.environ["CODEX_HOME"] = os.path.join(SKILL_ROOT, ".test-codex-home")
        os.environ["DSH_HOME"] = os.path.join(SKILL_ROOT, ".test-dsh-home")
        tg = module.targets()
        ok = (tg["codex"] == os.path.join(os.environ["CODEX_HOME"], "skills", "mr-agent")
              and tg["deepseek"] == os.path.join(os.environ["DSH_HOME"], "skills", "mr-agent"))
        RESULTS.append({"case": "H4 Codex / DeepSeek 安装根目录可配置", "group": "H",
                        "ok": ok, "exit": 0, "detail": ""})
        print("[%s] %-40s" % ("PASS" if ok else "FAIL", "H4 Codex / DeepSeek 安装根目录可配置"))
    except Exception as exc:
        RESULTS.append({"case": "H4 Codex / DeepSeek 安装根目录可配置", "group": "H",
                        "ok": False, "exit": 0, "detail": str(exc)})
        print("[FAIL] H4 Codex / DeepSeek 安装根目录可配置 %s" % exc)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # 批量安装多个目标时，备份目录名会落在同一秒。
    # 修复前 shutil.move 到已存在目录会静默把源移进去，
    # 降级分支的 copytree 则直接 FileExistsError —— 实测装到第 2 个就崩。
    try:
        import importlib.util as _iu
        _spec = _iu.spec_from_file_location(
            "mragent_install_bak", os.path.join(SKILL_ROOT, "install.py"))
        _mod = _iu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _tmp = tempfile.mkdtemp(prefix="mr-agent-bak-")
        _old_root = _mod.BACKUP_ROOT
        try:
            _mod.BACKUP_ROOT = os.path.join(_tmp, "backups")
            made = []
            for i in range(3):
                _dst = os.path.join(_tmp, "src%d" % i, "mr-agent")
                os.makedirs(_dst, exist_ok=True)
                with io.open(os.path.join(_dst, "SKILL.md"), "w",
                             encoding="utf-8") as fh:
                    fh.write("stub")
                made.append(_mod.backup_existing(_dst))
            ok = (len(set(made)) == 3
                  and all(os.path.isfile(os.path.join(b, "SKILL.md"))
                          for b in made)
                  and not any(os.path.exists(os.path.join(b, "mr-agent"))
                              for b in made))
            detail = "" if ok else "备份路径重复或错位: %r" % (made,)
        finally:
            _mod.BACKUP_ROOT = _old_root
            shutil.rmtree(_tmp, ignore_errors=True)
        RESULTS.append({"case": "H5 备份目录同秒不撞车", "group": "H",
                        "ok": ok, "exit": 0, "detail": detail})
        print("[%s] %-40s %s" % ("PASS" if ok else "FAIL",
                                 "H5 备份目录同秒不撞车", detail))
    except Exception as exc:
        RESULTS.append({"case": "H5 备份目录同秒不撞车", "group": "H",
                        "ok": False, "exit": 0, "detail": str(exc)})
        print("[FAIL] H5 备份目录同秒不撞车 %s" % exc)


# ------------------------------------------------------------------ I
def group_i():
    print()
    print("=" * 78)
    print("I. 上游能力对齐：提示词库 / 不复刻已失效的爬虫")
    print("=" * 78)
    import ast
    import re

    def mrprompt(*args):
        rc, out, _ = run(["mr_prompt.py"] + list(args), cwd=TOOLS)
        try:
            return rc, json.loads(out)
        except Exception:
            return rc, {}

    # I1 数量与分组
    rc, d = mrprompt("--list")
    n_main = len((d.get("groups") or {}).get("main") or [])
    n_abl = len((d.get("groups") or {}).get("step9_ablation") or [])
    ok = rc == 0 and d.get("total") == 22 and n_main == 10 and n_abl == 12
    RESULTS.append({"case": "I1 提示词库 22 个（10 主 + 12 消融）", "group": "I",
                    "ok": ok, "exit": rc,
                    "detail": "main=%s ablation=%s total=%s" % (n_main, n_abl, d.get("total"))})
    print("[%s] %-40s main=%s ablation=%s" % ("PASS" if ok else "FAIL",
          "I1 提示词库 22 个（10 主 + 12 消融）", n_main, n_abl))

    # I2 主模板原文与上游源码逐字一致（需要上游仓库；没有就跳过）
    up = os.path.join(os.path.dirname(SKILL_ROOT), "MRAgent-upstream",
                      "mragent", "template_text.py")
    if os.path.exists(up):
        tree = ast.parse(io.open(up, encoding="utf-8", errors="replace").read())
        upstream = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                    and isinstance(node.value, ast.Constant) \
                    and isinstance(node.value.value, str):
                upstream[node.targets[0].id] = node.value.value
        lib = json.load(io.open(os.path.join(TOOLS, "prompts.json"), encoding="utf-8"))
        diff = [k for k, v in lib["main"].items() if upstream.get(k) != v["text"]]
        ok = not diff and len(lib["main"]) == 10
        RESULTS.append({"case": "I2 主模板与上游逐字一致", "group": "I", "ok": ok,
                        "exit": 0, "detail": ("不一致: %s" % diff) if diff else ""})
        print("[%s] %-40s %s" % ("PASS" if ok else "FAIL",
                                 "I2 主模板与上游逐字一致", diff or "10/10 一致"))
    else:
        skip("I2 主模板与上游逐字一致", "本机没有 MRAgent-upstream 仓库", group="I")

    # I3 渲染
    rc, d = mrprompt("--render", "synonyms_text", "--var", "OE=back pain")
    ok = rc == 0 and d.get("ok") and "back pain" in (d.get("rendered") or "") \
        and d.get("unused_vars") == []
    RESULTS.append({"case": "I3 模板渲染", "group": "I", "ok": bool(ok), "exit": rc,
                    "detail": "" if ok else "rendered=%r" % (d.get("rendered") or "")[:80]})
    print("[%s] %-40s" % ("PASS" if ok else "FAIL", "I3 模板渲染"))

    # I4 缺占位符必须 exit 2 且指明缺哪个
    case("I4 渲染缺占位符", ["mr_prompt.py", "--render", "pubmed_text_obo",
                             "--var", "Outcome=x"], 2, cwd=TOOLS,
         check=lambda x: "缺少占位符" in (x.get("error") or "")
         and "abstract" in (x.get("error") or ""), group="I")

    # I5 名字写错要有近似提示
    case("I5 模板名写错的近似提示",
         ["mr_prompt.py", "--show", "LLM_MR_templat"], 2, cwd=TOOLS,
         check=lambda x: "近似名" in (x.get("hint") or ""), group="I")

    # I6 step9 消融变体的 6 个变体 × 2 个模型都要在
    lib = json.load(io.open(os.path.join(TOOLS, "prompts.json"), encoding="utf-8"))
    variants = {v["variant"] for v in lib["step9_ablation"].values()}
    models = {v["model"] for v in lib["step9_ablation"].values()}
    ok = len(variants) == 6 and models == {"MR", "MR_MOE"}
    RESULTS.append({"case": "I6 消融变体 6 组 × 2 模型", "group": "I", "ok": ok,
                    "exit": 0, "detail": "variants=%s models=%s" % (sorted(variants), sorted(models))})
    print("[%s] %-40s %s" % ("PASS" if ok else "FAIL", "I6 消融变体 6 组 × 2 模型",
                             sorted(variants)))

    # I7 mr_gwas 不得再调用上游那套已失效的 HTML 爬虫
    src = io.open(os.path.join(TOOLS, "mr_gwas.py"), encoding="utf-8").read()
    code = re.sub(r'(?s)""".*?"""', "", src)  # 去掉 docstring，只看代码
    ok = "check_keyword_in_opengwas(" not in code and "gwas.mrcieu.ac.uk/datasets" not in code
    RESULTS.append({"case": "I7 不复刻失效爬虫", "group": "I", "ok": ok, "exit": 0,
                    "detail": "" if ok else "代码里仍调用上游爬虫"})
    print("[%s] %-40s" % ("PASS" if ok else "FAIL", "I7 不复刻失效爬虫"))

    # I8 这三个工具的原子能力本来就是公开 REST，不该被迫依赖整个 mragent
    freed = {}
    for fn in ("mr_pubmed.py", "mr_synonyms.py", "mr_llm.py"):
        body = io.open(os.path.join(TOOLS, fn), encoding="utf-8").read()
        freed[fn] = "require_mragent(" not in body
    ok = all(freed.values())
    RESULTS.append({"case": "I8 三工具已脱离 mragent", "group": "I", "ok": ok,
                    "exit": 0, "detail": str(freed)})
    print("[%s] %-40s %s" % ("PASS" if ok else "FAIL", "I8 三工具已脱离 mragent",
                             "" if ok else freed))

    # I9 mr_llm 的线上请求形状（本地起一个 OpenAI 兼容 mock 服务真发一次）
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = {}

    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            seen["path"] = self.path
            seen["auth"] = self.headers.get("Authorization") or ""
            try:
                seen["body"] = json.loads(self.rfile.read(n).decode("utf-8"))
            except Exception:
                seen["body"] = {}
            out = json.dumps({"choices": [{"message": {"content": "MOCK"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        rc, out, _ = run(["mr_llm.py", "--prompt", "PING", "--model", "gpt-4o",
                          "--base-url", "http://127.0.0.1:%d/v1" % srv.server_address[1],
                          "--api-key", "sk-selftest"], cwd=TOOLS)
        body = seen.get("body") or {}
        msgs = body.get("messages") or []
        ok = (rc == 0 and seen.get("path") == "/v1/chat/completions"
              and seen.get("auth", "").startswith("Bearer sk-selftest")
              and body.get("model") == "gpt-4o" and body.get("seed") == 42
              and len(msgs) == 2
              and msgs[0].get("content") == "You are a helpful biomedical scientist."
              and msgs[1].get("content") == "PING")
        RESULTS.append({"case": "I9 mr_llm 线上请求形状", "group": "I", "ok": ok,
                        "exit": rc,
                        "detail": "" if ok else "path=%s body=%s" % (seen.get("path"), body)})
        print("[%s] %-40s exit=%r" % ("PASS" if ok else "FAIL",
                                      "I9 mr_llm 线上请求形状", rc))
    finally:
        srv.shutdown()

    # I10 文本文件一律 LF —— .gitattributes 声明了 `* text=auto eol=lf`。
    # 这不是洁癖：仓库里的 .py 带 shebang，CRLF 会让 Linux 上执行时
    # 变成 "#!/usr/bin/env python\r"，内核找不到解释器且只报 "not found"。
    exts = (".py", ".md", ".json", ".yml", ".yaml", ".example", ".txt",
            ".cfg", ".toml", ".svg")
    crlf = []
    for root, dirs, files in os.walk(SKILL_ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for fn in files:
            if not fn.endswith(exts):
                continue
            fp = os.path.join(root, fn)
            try:
                if b"\r\n" in io.open(fp, "rb").read():
                    crlf.append(os.path.relpath(fp, SKILL_ROOT))
            except OSError:
                continue
    ok = not crlf
    RESULTS.append({"case": "I10 文本文件行尾为 LF", "group": "I", "ok": ok,
                    "exit": 0, "detail": ",".join(crlf[:6]) if crlf else ""})
    print("[%s] %-40s %s" % ("PASS" if ok else "FAIL", "I10 文本文件行尾为 LF",
                             "" if ok else crlf[:6]))


def main():
    ap = argparse.ArgumentParser(description="mr-agent 全量自检")
    ap.add_argument("--quick", action="store_true", help="跳过真实网络探测")
    ap.add_argument("--json", action="store_true", help="结果输出为 JSON")
    args = ap.parse_args()
    global QUICK
    QUICK = args.quick

    base = tempfile.mkdtemp(prefix="mragentselftest-")
    sys.stderr.write("[selftest] 技能根目录: %s\n" % SKILL_ROOT)
    sys.stderr.write("[selftest] 临时目录  : %s\n" % base)
    try:
        group_a(args.quick)
        group_b()
        group_c(base)
        group_d(base)
        group_e()
        group_fg()
        group_h()
        group_i()
    finally:
        shutil.rmtree(base, ignore_errors=True)

    fails = [r for r in RESULTS if not r["ok"]]
    total = len(RESULTS)
    print()
    print("=" * 78)
    print("总计 %d 用例，失败 %d" % (total, len(fails)))
    for f in fails:
        print("  FAIL %-40s exit=%r %s" % (f["case"], f["exit"], f["detail"]))
    print("=" * 78)

    if args.json:
        json.dump({"total": total, "failed": len(fails),
                   "ok": len(fails) == 0, "cases": RESULTS},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
