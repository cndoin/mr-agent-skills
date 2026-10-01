#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 mr-agent 技能装到各个 Agent 的技能目录。

用法：
    python install.py --target all          # 全部（默认）
    python install.py --target claude       # 只装 Claude Code
    python install.py --target workbuddy    # 只装 WorkBuddy
    python install.py --target codebuddy    # 只装 CodeBuddy
    python install.py --target codex        # 只装 OpenAI Codex
    python install.py --target deepseek     # 只装 DeepSeek Harness
    python install.py --list                # 只看会被装到哪，不装

契约与其他脚本一致：stdout 只有一个 JSON，提示走 stderr。
零第三方依赖 —— 只用标准库，所以任何 Python 3.8+ 都能跑安装。

为什么需要这个脚本：
    不同 Agent 的技能目录不同（~/.claude/skills、~/.codex/skills …），
    而且 opengwas.csv（10 MB）不该进 git 仓库（见 .gitignore / NOTICE），
    得由安装阶段下载到全局缓存 —— 两者手工做都容易漏。
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_NAME = "mr-agent"

# 第三方数据：仓库不分发，装的时候下到 $HOME 下的缓存里
CSV_URL = ("https://raw.githubusercontent.com/xuwei1997/MRAgent/"
           "main/opengwas.csv")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "mr-agent")
CACHE_CSV = os.path.join(CACHE_DIR, "opengwas.csv")
# 备份必须放在 skills/ 之外：同级的 mr-agent.bak-<ts> 目录里也有 SKILL.md，
# 会被 Agent 当成第二个同名技能一起加载（真踩过）。
BACKUP_ROOT = os.path.join(CACHE_DIR, "backups")

# 复制时要排除的东西：版本控制、缓存、运行产物、以及那个 10 MB 的第三方数据
EXCLUDE = {".git", "__pycache__", "output", "mragent-runs", "opengwas.csv",
           ".pytest_cache", ".mypy_cache"}


def targets():
    """各 Agent 的技能目录。目录不存在不代表 Agent 没装 —— 所以都列出。"""
    home = os.path.expanduser("~")
    codex_home = os.path.expanduser(os.environ.get("CODEX_HOME") or os.path.join(home, ".codex"))
    dsh_home = os.path.expanduser(os.environ.get("DSH_HOME") or os.path.join(home, ".dsh"))
    return {
        "claude": os.path.join(home, ".claude", "skills", SKILL_NAME),
        "workbuddy": os.path.join(home, ".workbuddy", "skills", SKILL_NAME),
        "codebuddy": os.path.join(home, ".codebuddy", "skills", SKILL_NAME),
        "codex": os.path.join(codex_home, "skills", SKILL_NAME),
        "deepseek": os.path.join(dsh_home, "skills", SKILL_NAME),
    }


# ---------------------------------------------------------------- frontmatter
def parse_frontmatter(path):
    """极简 YAML 子集解析：只处理本项目实际用到的 `key: value` 与一层嵌套。

    刻意不引入 PyYAML —— 安装脚本要能在任何裸 Python 上跑。
    """
    text = io.open(path, encoding="utf-8").read()
    if not text.startswith("---"):
        return None, "文件没有以 --- 开头，不是合法 frontmatter"
    end = text.find("\n---", 3)
    if end < 0:
        return None, "frontmatter 没有找到结束的 ---"
    body = text[3:end]
    data, cur = {}, None
    for line in body.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0 and ":" in line:
            k, _, v = line.partition(":")
            v = v.strip()
            if v == "":
                cur = k.strip()
                data[cur] = {}
            else:
                cur = None
                data[k.strip()] = v.strip('"').strip("'")
        elif indent > 0 and cur and ":" in line:
            k, _, v = line.partition(":")
            data[cur][k.strip()] = v.strip().strip('"').strip("'")
    return data, None


def validate_frontmatter(path):
    """校验可移植技能 frontmatter 的共同要求。"""
    problems = []
    data, err = parse_frontmatter(path)
    if err:
        return ["frontmatter 解析失败: %s" % err]

    if not data.get("name"):
        problems.append("缺少 name")
    else:
        name = data["name"]
        # Codex、Claude Code、DeepSeek Harness 均使用小写 kebab-case 技能名。
        ok_chars = all(c.isalnum() or c == "-" for c in name)
        if not ok_chars or name != name.lower():
            problems.append("name 必须是小写字母/数字/连字符: %r" % name)
        if len(name) > 64:
            problems.append("name 超过 64 字符")

    desc = data.get("description", "")
    if not desc:
        problems.append("缺少 description（这是触发技能的唯一依据，不能空）")
    elif len(desc) < 60:
        problems.append("description 太短（%d 字符），触发词覆盖不足" % len(desc))

    if not data.get("license"):
        problems.append("缺少 license 字段（开源发布必需）")
    return problems


# ---------------------------------------------------------------- 复制
def _ignore(directory, names):
    return [n for n in names if n in EXCLUDE]


def backup_existing(dst):
    """覆盖前把已有安装改名备份。

    直接 rmtree 掉用户已有的安装是不可接受的 —— 万一他手动改过 SKILL.md，
    一次安装就没了。备份成 .bak-<时间戳>，并只保留最近 3 份，避免无限堆积。
    """
    if not os.path.exists(dst):
        return None
    os.makedirs(BACKUP_ROOT, exist_ok=True)
    base = os.path.basename(dst)
    bak = os.path.join(BACKUP_ROOT, "%s.bak-%s"
                       % (base, time.strftime("%Y%m%d-%H%M%S")))
    try:
        shutil.move(dst, bak)
    except Exception:
        # 跨盘/跨设备时 move 会失败，降级成复制后删除
        shutil.copytree(dst, bak, ignore=_ignore)
        shutil.rmtree(dst, ignore_errors=True)
    # 只留最近 3 份
    olds = sorted([p for p in os.listdir(BACKUP_ROOT)
                   if p.startswith(base + ".bak-")], reverse=True)
    for p in olds[3:]:
        shutil.rmtree(os.path.join(BACKUP_ROOT, p), ignore_errors=True)
    return bak


def install_one(dst, src, dry_run=False, no_backup=False):
    if dry_run:
        return {"path": dst, "action": "would-copy", "exists": os.path.exists(dst)}
    bak = None if no_backup else backup_existing(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(src, dst, ignore=_ignore)
    # 复制完再校验一次，确保装进去的是能加载的版本
    problems = validate_frontmatter(os.path.join(dst, "SKILL.md"))
    return {"path": dst, "action": "installed", "backup": bak,
            "frontmatter_problems": problems}


# ---------------------------------------------------------------- 数据
def fetch_csv(timeout=180):
    """下载离线 GWAS 清单到全局缓存。网络不可用时返回 None，不算失败。"""
    if os.path.exists(CACHE_CSV) and os.path.getsize(CACHE_CSV) > 1024 * 1024:
        return {"status": "cached", "path": CACHE_CSV,
                "size_mb": round(os.path.getsize(CACHE_CSV) / 1048576, 2)}
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with urllib.request.urlopen(CSV_URL, timeout=timeout) as resp:
            raw = resp.read()
        if len(raw) < 1024 * 1024:
            return {"status": "failed", "reason": "下载内容过小，疑似不是完整清单"}
        with io.open(CACHE_CSV, "wb") as fh:
            fh.write(raw)
        return {"status": "downloaded", "path": CACHE_CSV,
                "size_mb": round(len(raw) / 1048576, 2)}
    except Exception as exc:
        return {"status": "failed", "reason": "%s: %s" % (type(exc).__name__, exc),
                "hint": "稍后手动执行 python tools/mr_gwas.py --fetch"}


# ---------------------------------------------------------------- 冒烟
def smoke(dst):
    """装完跑两条真实命令：预检 + 离线检索。不需要 R，本机就能验。"""
    py = sys.executable
    steps = []
    p = os.path.join(dst, "scripts", "preflight.py")
    try:
        r = subprocess.run([py, p, "--no-network"], capture_output=True,
                           text=True, timeout=180, cwd=dst)
        ok = False
        try:
            ok = json.loads(r.stdout).get("ready") is not None
        except Exception:
            pass
        steps.append({"step": "preflight", "ok": ok, "exit": r.returncode})
    except Exception as exc:
        steps.append({"step": "preflight", "ok": False,
                      "error": "%s: %s" % (type(exc).__name__, exc)})

    g = os.path.join(dst, "tools", "mr_gwas.py")
    try:
        r = subprocess.run([py, g, "--keyword", "body mass index", "--limit", "3",
                            "--mode", "csv"], capture_output=True, text=True,
                           timeout=180, cwd=os.path.dirname(g))
        ok = False
        note = ""
        try:
            d = json.loads(r.stdout)
            ok = d.get("ok") is True and d.get("hit_count", 0) > 0
            note = "命中 %s 条" % d.get("hit_count")
        except Exception as exc:
            note = "输出非 JSON: %s" % str(exc)[:60]
        steps.append({"step": "gwas_offline", "ok": ok, "note": note})
    except Exception as exc:
        steps.append({"step": "gwas_offline", "ok": False,
                      "error": "%s: %s" % (type(exc).__name__, exc)})
    return steps


def main():
    ap = argparse.ArgumentParser(description="安装 mr-agent 技能到各 Agent 目录")
    ap.add_argument("--target", default="all",
                    help="安装目标，可用逗号分隔（如 codex,deepseek），默认 all")
    ap.add_argument("--list", action="store_true", help="只列目标路径，不安装")
    ap.add_argument("--dry-run", action="store_true", help="演练，不写盘")
    ap.add_argument("--no-fetch", action="store_true", help="不下载离线 GWAS 清单")
    ap.add_argument("--no-smoke", action="store_true", help="装完不跑冒烟")
    ap.add_argument("--no-backup", action="store_true",
                    help="覆盖已有安装时不备份（默认会备份成 .bak-<时间戳>）")
    args = ap.parse_args()

    tg = targets()
    # 支持逗号分隔多目标：--target claude,workbuddy
    # （用 choices 限制成单选会让人以为只能一次装一个，实测我自己就写错了）
    names = [x.strip() for x in args.target.split(",") if x.strip()]
    if names == ["all"]:
        chosen = tg
    else:
        unknown = [n for n in names if n not in tg]
        if unknown:
            sys.stderr.write("[install] !! 未知目标: %s（可选: %s）\n"
                             % (", ".join(unknown), ", ".join(sorted(tg))))
            json.dump({"tool": "mragent-install", "ok": False,
                       "error": "未知安装目标: %s" % ", ".join(unknown),
                       "available": sorted(tg)},
                      sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            return 2
        chosen = {n: tg[n] for n in names}

    if args.list:
        # 只列路径而不校验，会让 CI 里出现"永远通过"的检查 —— 那等于没检查。
        problems = validate_frontmatter(os.path.join(HERE, "SKILL.md"))
        json.dump({"targets": chosen, "cache_csv": CACHE_CSV,
                   "frontmatter_problems": problems,
                   "ok": not problems},
                  sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0 if not problems else 1

    sys.stderr.write("[install] 源目录: %s\n" % HERE)
    fm = validate_frontmatter(os.path.join(HERE, "SKILL.md"))
    if fm:
        sys.stderr.write("[install] !! frontmatter 有问题: %s\n" % "; ".join(fm))

    out = {"tool": "mragent-install", "source": HERE,
           "frontmatter_problems": fm, "installed": [], "csv": None,
           "smoke": []}

    for name, dst in chosen.items():
        sys.stderr.write("[install] -> %s : %s\n" % (name, dst))
        rec = install_one(dst, HERE, dry_run=args.dry_run,
                          no_backup=args.no_backup)
        rec["target"] = name
        out["installed"].append(rec)

    if not args.no_fetch and not args.dry_run:
        sys.stderr.write("[install] 下载离线 GWAS 清单…\n")
        out["csv"] = fetch_csv()

    if not args.no_smoke and not args.dry_run:
        for rec in out["installed"]:
            if rec.get("action") == "installed":
                sys.stderr.write("[install] 冒烟: %s\n" % rec["target"])
                rec["smoke"] = smoke(rec["path"])

    bad = [r for r in out["installed"] if r.get("frontmatter_problems")]
    out["ok"] = not fm and not bad
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
