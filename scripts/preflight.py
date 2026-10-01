#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MRAgent preflight —— 环境预检，输出结构化 JSON。

约定：
  * stdout 只放 JSON，人类可读提示一律走 stderr
  * 空状态 / 错误路径也必须给出结构化 JSON，绝不靠异常堆栈表达结果
  * required=true 且 ok=false 的项 = 硬阻塞，调用方必须停下报告

用法：
  python preflight.py                     # 探测当前解释器
  python preflight.py --python /path/py   # 探测指定解释器（推荐指向 3.12 venv）
  python preflight.py --no-network        # 跳过网络探测（离线环境）
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request

# MRAgent 0.2.5 硬约束：官方依赖锁 numpy<2 / pandas<2，二者无 cp313 wheel。
# 3.13 上必须源码编译（本机无 gcc）→ 必然失败。故上限写死 3.12。
PYTHON_MAX_OK = (3, 12)
PYTHON_MIN_OK = (3, 9)

REQUIRED_R_PACKAGES = [
    "TwoSampleMR",   # MR 主计算
    "ieugwasr",      # OpenGWAS 接口
    "dplyr",         # R 脚本内数据处理
    "vcfR",
    "MRlap",         # mrlap=True 时才真正需要
    "jsonlite",
]
# MRlap 只在 mrlap=True 时必需，其余缺一个就跑不动
OPTIONAL_R_PACKAGES = {"MRlap"}

TOKEN_ENV_VARS = ["MRAGENT_GWAS_TOKEN", "OPENGWAS_JWT"]
LLM_ENV_VARS = ["OPENAI_API_KEY", "MRAGENT_AI_KEY"]

NETWORK_TARGETS = {
    "opengwas": "https://api.opengwas.io/api/status",
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi",
}


def is_supported_python(version):
    """Check upstream's declared range, including its explicit 3.9.7 exclusion."""
    return (PYTHON_MIN_OK <= version[:2] <= PYTHON_MAX_OK
            and version[:3] != (3, 9, 7))


def _result(name, ok, detail, required=True, hint=None):
    item = {"name": name, "ok": bool(ok), "required": bool(required), "detail": detail}
    if hint:
        item["hint"] = hint
    return item


def probe_python(target):
    """探测 Python 版本是否落在 MRAgent 可安装区间内。"""
    code = (
        "import sys,json;"
        "print(json.dumps({'version':sys.version.split()[0],"
        "'major':sys.version_info[0],'minor':sys.version_info[1],"
        "'micro':sys.version_info[2]}))"
    )
    try:
        out = subprocess.run([target, "-c", code], capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return _result("python", False, "解释器不可用: %s" % (out.stderr.strip()[:200] or "unknown"),
                           hint="确认 --python 指向一个真实存在的解释器")
        info = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception as exc:  # 超时 / 找不到文件 / JSON 解析失败
        return _result("python", False, "探测失败: %s" % exc, hint="确认 --python 路径正确")

    ver = (info["major"], info["minor"], info["micro"])
    ok = is_supported_python(ver)
    detail = "%s (Python %s)" % (target, info["version"])
    if not ok:
        if ver == (3, 9, 7):
            return _result("python", False, detail,
                           hint="上游 mragent 明确排除 Python 3.9.7，请使用其他受支持版本")
        return _result(
            "python", False, detail,
            hint="MRAgent 锁 numpy<2 / pandas<2，二者无 cp313 预编译 wheel。"
                 "Python >=3.13 需源码编译（本机无 gcc）必然失败，请改用 3.11/3.12 venv",
        )
    return _result("python", True, detail)


def probe_mragent(target):
    """探测 mragent 是否已安装且可导入。"""
    code = (
        "import json;"
        "from mragent import MRAgent, MRAgentOE;"
        "import inspect,sys;"
        "sig=inspect.signature(MRAgent.__init__);"
        "print(json.dumps({'importable':True,'params':list(sig.parameters)}))"
    )
    try:
        out = subprocess.run([target, "-c", code], capture_output=True, text=True, timeout=120)
    except Exception as exc:
        return _result("mragent", False, "探测失败: %s" % exc)

    if out.returncode != 0:
        err = out.stderr.strip().splitlines()
        tail = err[-1] if err else "unknown"
        return _result("mragent", False, "import 失败: %s" % tail[:300],
                       hint="pip install mragent（必须在 3.11/3.12 的解释器里装）")
    try:
        info = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        return _result("mragent", True, "import 成功（版本信息解析失败）")
    return _result("mragent", True, "import 成功，%d 个构造参数" % len(info.get("params", [])))


def probe_r():
    """R 必须可执行且命令名就叫 R —— 源码用 os.system('R -f test.R') 调用。"""
    path = shutil.which("R")
    if not path:
        return _result("r_runtime", False, "PATH 中找不到 R 可执行文件",
                       hint="安装 R >4.3.4 并把 bin 目录加入 PATH（源码调用的是 R，不是 Rscript）")

    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60)
        version = (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception as exc:
        return _result("r_runtime", False, "R 存在但无法执行: %s" % exc)
    return _result("r_runtime", True, "%s -> %s" % (version, path))


def probe_r_packages():
    """逐个探测 R 包。缺 MRlap 不阻塞（只有 mrlap=True 时才需要）。"""
    path = shutil.which("R")
    if not path:
        return [_result("r_packages", False, "R 不存在，跳过包探测")]

    expr = ";".join(
        'cat("%s", requireNamespace("%s", quietly=TRUE), "\\n")' % (p, p)
        for p in REQUIRED_R_PACKAGES
    )
    cmd = [path, "--slave", "--no-save", "--no-restore", "--no-site-file",
           "--no-environ", "-e", expr]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as exc:
        return [_result("r_packages", False, "探测失败: %s" % exc)]

    present = {}
    for line in (out.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            present[parts[0]] = parts[1].upper() == "TRUE"

    results = []
    missing_required, missing_optional = [], []
    for pkg in REQUIRED_R_PACKAGES:
        ok = present.get(pkg, False)
        if not ok:
            (missing_optional if pkg in OPTIONAL_R_PACKAGES else missing_required).append(pkg)
        results.append(_result(
            "r_pkg:%s" % pkg, ok,
            "已安装" if ok else "缺失",
            required=(pkg not in OPTIONAL_R_PACKAGES),
        ))

    if missing_required:
        results.append(_result(
            "r_packages", False, "缺失必需包: %s" % ", ".join(missing_required),
            hint="见 references/environment.md 的装包命令（TwoSampleMR/ieugwasr 通常需 install_github）",
        ))
    elif missing_optional:
        results.append(_result(
            "r_packages", True, "仅缺可选包: %s（mrlap=True 时才需要）" % ", ".join(missing_optional),
            required=False,
        ))
    else:
        results.append(_result("r_packages", True, "全部 %d 个 R 包齐备" % len(REQUIRED_R_PACKAGES)))
    return results


def probe_tokens():
    """gwas_token 是硬门槛；LLM key 与后端有关，缺了只警告（可用 ollama 本地模型）。"""
    results = []
    token_vals = [v for v in TOKEN_ENV_VARS if os.environ.get(v)]
    if token_vals:
        results.append(_result("gwas_token", True, "环境变量已设置: %s" % ", ".join(token_vals)))
    else:
        results.append(_result(
            "gwas_token", False, "未找到 %s" % " / ".join(TOKEN_ENV_VARS),
            hint="到 https://api.opengwas.io/ 申请 JWT 后设置 MRAGENT_GWAS_TOKEN",
        ))

    llm_vals = [v for v in LLM_ENV_VARS if os.environ.get(v)]
    if llm_vals:
        results.append(_result("llm_key", True, "已设置: %s" % ", ".join(llm_vals), required=False))
    else:
        results.append(_result(
            "llm_key", False,
            "未找到 %s（若走 ollama 本地模型则不需要）" % " / ".join(LLM_ENV_VARS),
            required=False,
        ))
    return results


def probe_network(timeout=8):
    results = []
    for name, url in NETWORK_TARGETS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mragent-preflight/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                results.append(_result("net:%s" % name, True, "HTTP %s" % resp.status, required=False))
        except Exception as exc:
            results.append(_result("net:%s" % name, False, "%s" % exc, required=False,
                                   hint="离线或需代理；OpenGWAS 不可达则 step5 之后必然取不到数"))
    return results


def main():
    ap = argparse.ArgumentParser(description="MRAgent environment preflight")
    ap.add_argument("--python", default=sys.executable, help="待探测的 Python 解释器")
    ap.add_argument("--no-network", action="store_true", help="跳过网络探测")
    args = ap.parse_args()

    checks = []
    checks.append(probe_python(args.python))
    checks.append(probe_mragent(args.python))
    checks.append(probe_r())
    checks.extend(probe_r_packages())
    checks.extend(probe_tokens())
    if not args.no_network:
        checks.extend(probe_network())

    blocking = [c for c in checks if c.get("required") and not c.get("ok")]
    report = {
        "tool": "mragent-preflight",
        "target_python": args.python,
        "checks": checks,
        "blocking": [c["name"] for c in blocking],
        "ready": len(blocking) == 0,
    }
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

    if blocking:
        sys.stderr.write("阻塞项: %s\n" % ", ".join(c["name"] for c in blocking))
    return 0


if __name__ == "__main__":
    sys.exit(main())
