#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MRAgent 统一运行入口。

做三件 MRAgent 自己不做、但缺了就会出事的事：
  1. **强制独立工作目录**：MRAgent 把 ./output/ 和临时 test.R 写在 CWD，
     并发任务会互相覆盖。本脚本 chdir 进独立目录再跑。
  2. **堵住 step3 的静默失败**：源码在"所有对都做过 MR"时 sys.exit(0)，
     退出码 0 但一个 MR 都没跑。这里捕获 SystemExit 并检查 mr_run.csv。
  3. **环境变量取 token**：不把密钥写进命令行（会进 shell history）。

用法：
  # 知识发现：找"背痛"的因
  python run_mr.py --mode O --outcome "back pain" --steps 1,2

  # 因果验证：骨关节炎 -> 背痛
  python run_mr.py --mode OE --exposure osteoarthritis --outcome "back pain"

  # 只下发配置，不真跑（用于生成可移植脚本 / 检查参数）
  python run_mr.py --mode O --outcome "back pain" --dry-run

前置：MRAGENT_GWAS_TOKEN（或 OPENGWAS_JWT）必须设置。
"""

import argparse
import json
import io
import os
import sys
import traceback
from datetime import datetime

# MRAgent 写死的中间产物文件名（源码实测，README 里的 outcome/run 是错的）
EXPOSURE_OUTCOME_CSV = "Exposure_and_Outcome.csv"
OUTCOME_SNP_CSV = "Outcome_SNP.csv"
MR_RUN_CSV = "mr_run.csv"

VALID_MODES = ("O", "E", "OE", "auto")


def arg_error(message):
    """参数错误：走 stderr 提示 + stdout 结构化 JSON，然后 exit 2。"""
    sys.stderr.write("参数错误: %s\n" % message)
    json.dump({"tool": "mragent-run", "ok": False, "error": message},
              sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.exit(2)


def build_workdir(base, mode, exposure, outcome, tag=None):
    """计算每个任务的独立目录，杜绝 test.R / output 互踩。"""
    parts = [p for p in (exposure, outcome) if p]
    slug = "_".join(parts) if parts else "unnamed"
    slug = "".join(c if (c.isalnum() or c in "-_") else "_" for c in slug)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # tag 来自用户输入，必须整体消毒：否则 "../../x" 会路径穿越，
    # 空格与分隔符会造出畸形目录名。
    raw = "%s_%s_%s" % (slug, mode, tag or stamp)
    name = "".join(c if (c.isalnum() or c in "-_") else "_" for c in raw).strip("_")
    if not name:
        name = "run_%s" % stamp
    path = os.path.abspath(os.path.join(base, name))
    return path


def reserve_workdir(path):
    """独占创建新工作目录，避免复用旧 CSV 造成陈旧结果被当成新成功。"""
    candidate = path
    suffix = 2
    while True:
        try:
            os.makedirs(candidate)
            return candidate
        except FileExistsError:
            candidate = "%s_%d" % (path, suffix)
            suffix += 1


def collect_config(args, require_secrets=True):
    """组装传给 MRAgent / MRAgentOE 的构造参数。"""
    token = os.environ.get("MRAGENT_GWAS_TOKEN") or os.environ.get("OPENGWAS_JWT")
    ai_key = os.environ.get("MRAGENT_AI_KEY") or os.environ.get("OPENAI_API_KEY")

    if require_secrets:
        if not token:
            return None, "缺少 gwas_token：请设置 MRAGENT_GWAS_TOKEN 或 OPENGWAS_JWT"
        if args.model_type == "openai" and not ai_key:
            return None, "model_type=openai 需要 LLM key：设置 MRAGENT_AI_KEY 或 OPENAI_API_KEY"
    else:
        token = token or "<SET_MRAGENT_GWAS_TOKEN>"
        ai_key = ai_key or "<SET_MRAGENT_AI_KEY>"

    cfg = {
        "mode": args.mode,
        "exposure": args.exposure,
        "outcome": args.outcome,
        "model": args.model,
        "num": args.num,
        "bidirectional": args.bidirectional,
        "synonyms": args.synonyms,
        "introduction": not args.no_introduction,
        "LLM_model": args.llm_model,
        "model_type": args.model_type,
        "base_url": args.base_url,
        "gwas_token": "***set***",
        "opengwas_mode": args.opengwas_mode,
        "mr_quality_evaluation": args.mr_quality_evaluation,
        "mr_quality_evaluation_key_item": (
            [x.strip() for x in args.mr_quality_evaluation_key_item.split(",") if x.strip()]
            if args.mr_quality_evaluation_key_item else None),
        "mrlap": args.mrlap,
    }
    return {"cfg": cfg, "token": token, "ai_key": ai_key}, None


def main():
    ap = argparse.ArgumentParser(description="MRAgent runner")
    ap.add_argument("--mode", choices=VALID_MODES, required=True,
                    help="O=疾病当结局找暴露; E=疾病当暴露找结局; OE=验证给定一对; "
                         "auto=按给了什么自动推断（对齐上游 web_demo 的行为）")
    ap.add_argument("--outcome", help="结局（O/OE 模式必填）")
    ap.add_argument("--exposure", help="暴露（E/OE 模式必填）")
    ap.add_argument("--steps", default="1,2,3,4,5,6,7,8,9,10",
                    help="要执行的 step 列表，逗号分隔，默认全量")
    ap.add_argument("--workdir", default="./mragent-runs", help="独立工作目录的父目录")
    ap.add_argument("--model", default="MR", choices=["MR", "MR_MOE"])
    ap.add_argument("--llm-model", default="gpt-4o")
    ap.add_argument("--model-type", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--base-url", default=None, help="OpenAI 兼容平台的 base_url")
    ap.add_argument("--num", type=int, default=100, help="PubMed 抓取文章数")
    ap.add_argument("--opengwas-mode", default="online", choices=["online", "csv"])
    ap.add_argument("--bidirectional", action="store_true", help="双向 MR（开销翻倍）")
    synonyms = ap.add_mutually_exclusive_group()
    synonyms.add_argument("--synonyms", dest="synonyms", action="store_true",
                          help="启用上游 UMLS 同义词扩展（上游使用其内置 key）")
    synonyms.add_argument("--no-synonyms", dest="synonyms", action="store_false",
                          help="关闭 UMLS 同义词扩展（默认）")
    ap.set_defaults(synonyms=False)
    ap.add_argument("--no-introduction", action="store_true", help="关闭疾病引言生成")
    ap.add_argument("--mr-quality-evaluation", action="store_true", help="STROBE-MR 质量评估")
    ap.add_argument("--mr-quality-evaluation-key-item", default=None,
                    help="STROBE-MR 关键条目，逗号分隔，如 4b,4e,6e,10d（上游 demo 用的就是这组）")
    ap.add_argument("--mrlap", action="store_true", help="MRlap 样本重叠校正（需 ld/hm3 大文件）")
    ap.add_argument("--tag", default=None, help="工作目录后缀，便于区分多次运行")
    ap.add_argument("--dry-run", action="store_true", help="只输出配置，不执行")
    try:
        args = ap.parse_args()
    except SystemExit as exc:
        # argparse 校验失败默认只把 usage 打到 stderr、stdout 为空，
        # 这里转成结构化 JSON，保证调用方永远拿到可解析的结果。
        if exc.code == 2:
            sys.stderr.write("命令行参数错误，用 --help 查看用法\n")
            json.dump({"tool": "mragent-run", "ok": False,
                       "error": "命令行参数错误"},
                      sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            sys.exit(2)
        raise

    # auto：对齐上游 web_demo 的推断逻辑（Knowledge Discovery 下 outcome 优先），
    # 两个都给则视为因果验证 OE。
    if args.mode == "auto":
        if args.exposure and args.outcome:
            args.mode = "OE"
        elif args.outcome:
            args.mode = "O"
        elif args.exposure:
            args.mode = "E"
        else:
            arg_error("mode=auto 需要至少给 --exposure 或 --outcome")

    # 参数一致性校验：E 模式把 exposure 当主角，OE 模式两个都要
    if args.mode == "O" and not args.outcome:
        arg_error("mode=O 需要 --outcome")
    if args.mode == "E" and not args.exposure:
        arg_error("mode=E 需要 --exposure（源码会把 exposure 赋给 outcome）")
    if args.mode == "OE" and not (args.exposure and args.outcome):
        arg_error("mode=OE 需要同时给 --exposure 和 --outcome")

    try:
        steps = [int(s) for s in args.steps.split(",") if s.strip()]
    except ValueError:
        arg_error("--steps 必须是逗号分隔的整数，例如 1,2,3")
    if not steps:
        arg_error("--steps 不能为空，至少要给一个 step（例如 1,2）")
    invalid_steps = sorted(set(steps) - set(range(1, 11)))
    if invalid_steps:
        arg_error("--steps 只能使用 1 到 10，非法值: %s" % ", ".join(map(str, invalid_steps)))
    if len(steps) != len(set(steps)):
        arg_error("--steps 不允许重复编号")

    built, err = collect_config(args, require_secrets=not args.dry_run)
    if err:
        sys.stderr.write("配置错误: %s\n" % err)
        json.dump({"tool": "mragent-run", "ok": False, "error": err},
                  sys.stdout, ensure_ascii=False, indent=2)
        return 2

    workdir = build_workdir(args.workdir, args.mode, args.exposure, args.outcome, args.tag)
    payload = {
        "tool": "mragent-run",
        "mode": args.mode,
        "steps": steps,
        "workdir": workdir,
        "config": built["cfg"],
    }

    if args.dry_run:
        payload["ok"] = True
        payload["note"] = "dry-run：未执行，以下为将要下发的配置"
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.synonyms:
        sys.stderr.write(
            "警告: 上游 MRAgent 将使用其包内置的 UMLS key；"
            "目前无法通过本运行器替换成你自己的 key。\n")
    try:
        workdir = reserve_workdir(workdir)
    except OSError as exc:
        payload.update(ok=False, error="创建工作目录失败: %s: %s" % (type(exc).__name__, exc))
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 2
    payload["workdir"] = workdir

    # 关键：切进独立工作目录，避免 ./output 与 test.R 被并发任务覆盖
    os.chdir(workdir)
    payload["cwd"] = os.getcwd()

    try:
        if args.mode == "OE":
            from mragent import MRAgentOE as AgentCls
        else:
            from mragent import MRAgent as AgentCls
    except ImportError as exc:
        payload.update(ok=False, error="mragent 未安装或不可导入: %s" % exc)
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        return 2

    kwargs = dict(built["cfg"])
    kwargs["AI_key"] = built["ai_key"]
    kwargs["gwas_token"] = built["token"]
    kwargs.pop("exposure", None)
    kwargs.pop("outcome", None)
    if args.mode == "OE":
        kwargs["exposure"] = args.exposure
        kwargs["outcome"] = args.outcome
    elif args.mode == "O":
        kwargs["outcome"] = args.outcome
    else:
        kwargs["exposure"] = args.exposure

    # MRAgent 与 R 都会往 fd 1/2 狂写输出。若不做重定向，这些 print 会混进 stdout
    # 破坏"stdout 只放 JSON"的契约（实测污染出上百行，调用方 JSON 解析直接失败）。
    # 用 os.dup2 在文件描述符层重定向，能同时抓到 Python print 和 R 的原生输出
    # （后者不走 Python 的 sys.stdout，只重定向 sys.stdout 是抓不到的）。
    log_path = os.path.join(workdir, "run.log")
    payload["log_path"] = log_path
    silent_exit = False
    sys.stdout.flush()
    sys.stderr.flush()
    saved_out_fd = os.dup(1)
    saved_err_fd = os.dup(2)
    log_fh = open(log_path, "wb")
    try:
        os.dup2(log_fh.fileno(), 1)
        os.dup2(log_fh.fileno(), 2)
        try:
            agent = AgentCls(**kwargs)
            agent.run(step=steps)
        except SystemExit as exc:
            # step3 在"全部已做过 MR"时 sys.exit(0)：退出码 0，但一个 MR 都没跑
            silent_exit = True
            payload["system_exit_code"] = exc.code
        except Exception as exc:
            payload.update(ok=False, error="%s: %s" % (type(exc).__name__, exc),
                           traceback=traceback.format_exc().splitlines()[-6:])
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_out_fd, 1)
        os.dup2(saved_err_fd, 2)
        log_fh.close()
        os.close(saved_out_fd)
        os.close(saved_err_fd)
        # 上游把明文 JWT 写进了 test.R，R 报错也可能回显到 run.log；
        # 工作目录会被打包分享，收尾必须脱敏。失败不影响主流程结果。
        try:
            payload["redacted"] = _redact_workdir(
                workdir, [built.get("token"), built.get("ai_key")])
        except Exception as exc:
            payload["redact_error"] = "%s: %s" % (type(exc).__name__, exc)

    if payload.get("ok") is False:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 1

    # 用产物判断成败，不用退出码
    out_root = os.path.join(workdir, "output")
    run_csv = None
    for root, _dirs, files in os.walk(out_root):
        if MR_RUN_CSV in files:
            run_csv = os.path.join(root, MR_RUN_CSV)
            break

    payload["artifacts"] = {
        "output_root": out_root,
        "exposure_and_outcome": os.path.exists(
            _first_match(out_root, EXPOSURE_OUTCOME_CSV)),
        "outcome_snp": os.path.exists(_first_match(out_root, OUTCOME_SNP_CSV)),
        "mr_run_csv": run_csv,
    }
    payload["ok"] = run_csv is not None
    if silent_exit and not run_csv:
        payload["warning"] = ("进程以 SystemExit 结束且未产生 mr_run.csv —— "
                              "极可能是 step3 判定所有暴露-结局对都已做过 MR 后 sys.exit(0)，"
                              "本次一个 MR 都没跑")
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload["ok"] else 1



REDACTED = "***REDACTED***"


def _redact_workdir(workdir, secrets):
    """任务收尾时抹掉工作目录里落盘的明文凭据。

    原因是上游的行为，不是我们的：MRAgent 会把 gwas_token 原样写进 CWD 的
    test.R（Sys.setenv(OPENGWAS_JWT="<明文 JWT>")），R 报错时也可能把命令回显
    到 run.log。工作目录是会被打包分享的，所以必须清理。

    只处理 run.log 与 test.R 两个已知落盘点，不递归扫全目录 —— 避免为了
    脱敏把整个 output/ 树读一遍（里面可能有上百 MB 的图与结果）。
    """
    secrets = [x for x in secrets
               if x and len(x) >= 8 and not x.startswith("<SET_")]
    if not secrets:
        return []
    touched = []
    for name in ("run.log", "test.R"):
        p = os.path.join(workdir, name)
        if not os.path.isfile(p):
            continue
        try:
            raw = io.open(p, "rb").read()
        except OSError:
            continue
        new = raw
        for sec in secrets:
            new = new.replace(sec.encode("utf-8"), REDACTED.encode("utf-8"))
        if new != raw:
            with io.open(p, "wb") as fh:
                fh.write(new)
            touched.append(name)
    return touched

def _first_match(root, filename):
    for r, _d, files in os.walk(root):
        if filename in files:
            return os.path.join(r, filename)
    return ""


if __name__ == "__main__":
    sys.exit(main())
