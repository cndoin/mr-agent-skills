#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SMR（Summary-data-based Mendelian Randomization）分析与数据工具。

SMR 是 TwoSampleMR 之外的另一套方法学：用 cis-xQTL（eQTL/pQTL/mQTL）作为工具变量，
检验"基因/分子表型的效应是否介导了 SNP 对复杂性状的效应"。
核心产出是 SMR 检验（b_SMR / se / p）与 HEIDI 检验（区分共享因果变异 vs 连锁不平衡）。

官方实现是 Yang lab（西湖大学）的 `smr` 命令行工具（Zhu et al. 2016 Nat Genet）。
本工具提供两条路径：

  --engine official  调用官方 smr 二进制。功能最全（SMR/HEIDI、trans 区域、
                     multi-SNP SMR、MeCS、BESD 制作、locus plot、query 等），
                     数值与已发表结果逐位一致。需要先 `fetch-binary`。
  --engine native    纯标准库实现，零外部依赖。SMR 检验与官方逐位一致（已实测校准）；
                     HEIDI 为独立实现，结论一致但小数位可能与官方不同。

契约（与其他工具一致）：stdout 只放 JSON，人类提示走 stderr；
参数错误 exit 2，业务失败 exit 1，成功 exit 0。

用法速览：
  python mr_smr.py preflight                          # 探测官方二进制与输入
  python mr_smr.py fetch-binary                       # 下载官方 smr（按平台）
  python mr_smr.py analyze --engine official \\
      --bfile ref --gwas gwas.ma --beqtl eqtl --out result
  python mr_smr.py analyze --engine native \\
      --bfile ref --gwas gwas.ma --esd eqtl_1.esd --out result
  python mr_smr.py make-besd --flist my.flist --out mybesd
  python mr_smr.py ld --bfile ref --snp rs1008        # PLINK bfile -> LD
  python mr_smr.py dump-besd --besd eqtl --out eqtl --to-esd
  python mr_smr.py official -- --beqtl-summary eqtl --query 1e-6 --out q

`official` 子命令把参数原样透传给官方 smr，因此官方任何功能都不会被本包装层截断；
`analyze --engine official` 则是把常用 flag 翻译后的便利入口。
"""

import argparse
import io
import json
import math
import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import emit, fail, parse_args_or_fail  # noqa: E402

TOOL = "mr_smr"
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.environ.get("MRAGENT_CACHE") or os.path.join(
    os.path.expanduser("~"), ".cache", "mr-agent")
BIN_DIR = os.path.join(CACHE_DIR, "tools", "smr")

# 官方下载页：https://yanglab.westlake.edu.cn/software/smr/#Download
# Windows 目前只发到 1.3.1，Linux/macOS 已到 1.4.3 —— 这是官方现状，不是遗漏。
SMR_RELEASES = {
    ("nt", "x86_64"): ("smr-1.3.1-win-x86_64.zip",
                       "https://yanglab.westlake.edu.cn/software/smr/download/smr-1.3.1-win-x86_64.zip"),
    ("posix", "x86_64", "linux"): ("smr-1.4.3-linux-x86_64.zip",
                                   "https://yanglab.westlake.edu.cn/software/smr/download/smr-1.4.3-linux-x86_64.zip"),
    ("posix", "arm64", "darwin"): ("smr-1.4.3-macOS-arm64.zip",
                                   "https://yanglab.westlake.edu.cn/software/smr/download/smr-1.4.3-macOS-arm64.zip"),
}

# 官方默认参数（SMR.pdf "Other parameters" 一节，逐条核对）
DEFAULTS = dict(peqtl_smr=5e-8, peqtl_heidi=1.57e-3, ld_upper=0.9,
                ld_lower=0.05, heidi_min_m=3, heidi_max_m=20, cis_wind=2000)


def fmt_num(v):
    """把阈值格式化成官方能吃的写法：1.0 -> 1，5e-08 -> 5e-08。"""
    return "%g" % v


# 官方 --query 输出的 15 列（SMR query 输出格式，带表头）
QUERY_COLS = ["SNP", "Chr", "BP", "A1", "A2", "Freq", "Probe", "Probe_Chr",
              "Probe_bp", "Gene", "Orientation", "b", "SE", "p"]

# 官方可选参数（带值）：SMR/HEIDI、trans、multi-SNP、omics、选择、QC、进阶
OFFICIAL_OPT_FLAGS = [
    ("--peqtl-smr", "peqtl_smr"), ("--peqtl-heidi", "peqtl_heidi"),
    ("--cis-wind", "cis_wind"), ("--smr-wind", "smr_wind"),
    ("--ld-upper-limit", "ld_upper"), ("--ld-lower-limit", "ld_lower"),
    ("--heidi-min-m", "heidi_min_m"), ("--heidi-max-m", "heidi_max_m"),
    ("--heidi-mtd", "heidi_mtd"), ("--phet", "phet"),
    ("--peqtl-trans", "peqtl_trans"), ("--trans-wind", "trans_wind"),
    ("--set-list", "set_list"), ("--set-wind", "set_wind"),
    ("--extract-exposure-probe", "extract_exposure_probe"),
    ("--extract-outcome-probe", "extract_outcome_probe"),
    ("--exclude-exposure-probe", "exclude_exposure_probe"),
    ("--exclude-outcome-probe", "exclude_outcome_probe"),
    ("--extract-single-exposure-probe", "extract_single_exposure_probe"),
    ("--extract-single-outcome-probe", "extract_single_outcome_probe"),
    ("--extract-snp", "extract_snp"), ("--exclude-snp", "exclude_snp"),
    ("--extract-probe", "extract_probe"), ("--exclude-probe", "exclude_probe"),
    ("--extract-snp-probe", "extract_snp_probe"),
    ("--extract-target-snp-probe", "extract_target_snp_probe"),
    ("--genes", "genes"), ("--target-snp", "target_snp"),
    ("--smr-file", "smr_file"), ("--maf", "maf"),
    ("--diff-freq", "diff_freq"), ("--diff-freq-prop", "diff_freq_prop"),
    ("--nmecs", "nmecs"), ("--psmr", "psmr"),
    ("--gene-list", "gene_list"), ("--probe-wind", "probe_wind"),
]

# 官方布尔开关
OFFICIAL_BOOL_FLAGS = [
    ("--heidi-off", "heidi_off"), ("--trans", "trans"),
    ("--smr-multi", "smr_multi"), ("--ld-multi-snp", "ld_multi_snp"),
    ("--mecs", "mecs"), ("--pmecs", "pmecs"), ("--mmecs", "mmecs"),
    ("--meta", "meta"), ("--plot", "plot"),
    ("--disable-freq-ck", "disable_freq_ck"),
    ("--descriptive-cis", "descriptive_cis"),
    ("--descriptive-trans", "descriptive_trans"),
]


def append_official_flags(args, a):
    """把 Namespace 里已赋值的官方参数按序追加到 args。"""
    for flag, attr in OFFICIAL_OPT_FLAGS:
        v = getattr(a, attr, None)
        if v is None or v == "":
            continue
        args += [flag, fmt_num(v) if isinstance(v, float) else str(v)]
    for flag, attr in OFFICIAL_BOOL_FLAGS:
        if getattr(a, attr, False):
            args.append(flag)
    return args


def collect_outputs(out_prefix, skip=None):
    """扫出以 out_prefix 为前缀的兄弟产物文件。"""
    d = os.path.dirname(os.path.abspath(out_prefix)) or "."
    stem = os.path.basename(out_prefix)
    got = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.startswith(stem) and f != stem and f != skip:
                got.append(os.path.join(d, f))
    return got


# ====================================================================== 公共
def _exe_names():
    if os.name == "nt":
        return ["smr.exe", "smr-1.3.1-win.exe", "smr-1.0.3-win.exe"]
    return ["smr", "smr_v1.3.1_linux_x86_64_static", "smr_linux"]


def find_smr(explicit=None):
    """按优先级定位官方二进制：显式参数 > SMR_BIN > PATH > 全局缓存。"""
    names = _exe_names()
    cands = []
    if explicit:
        cands.append(explicit)
    if os.environ.get("SMR_BIN"):
        cands.append(os.environ["SMR_BIN"])
    for d in (os.environ.get("PATH") or "").split(os.pathsep):
        for n in names:
            cands.append(os.path.join(d, n))
    for root, _dirs, files in os.walk(BIN_DIR) if os.path.isdir(BIN_DIR) else []:
        for f in files:
            if f in names or (f.startswith("smr") and f.endswith(".exe")):
                cands.append(os.path.join(root, f))

    seen = set()
    for c in cands:
        if not c:
            continue
        c = os.path.abspath(c)
        if c in seen:
            continue
        seen.add(c)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def platform_key():
    import platform
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    if os.name == "nt":
        return ("nt", arch)
    return ("posix", arch, sys.platform)


# 官方下载站在 WAF 后面，会直接拒绝 urllib 的默认 UA（Python-urllib/3.x）并返回
# 403 Forbidden；换浏览器 UA 立刻变 200。这不是代理或网络问题 —— 实测同一个 URL
# 在同一个 shell 里只改 UA：默认 UA 403，浏览器 UA 200 / 2171140 字节。
# 所以下载请求必须显式带 UA，否则 fetch-binary 永远失败。
DOWNLOAD_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def download_request(url, extra=None):
    """构造带浏览器 UA 的下载请求。

    单独抽成函数是为了让自检能在不离线联网的前提下断言请求头 ——
    这个缺陷当初就是"只有真联网才会暴露"才漏掉的。
    """
    import urllib.request
    headers = {"User-Agent": DOWNLOAD_UA}
    if extra:
        headers.update(extra)
    return urllib.request.Request(url, headers=headers)


def download_binary(timeout=300):
    """下载并解压官方 smr 到全局缓存。返回 (path, error)。"""
    import urllib.request
    key = platform_key()
    rel = SMR_RELEASES.get(key)
    if not rel:
        rel = SMR_RELEASES.get((key[0], key[1]))
    if not rel:
        return None, ("当前平台没有官方预编译包: %r。"
                      "请到 https://yanglab.westlake.edu.cn/software/smr/#Download "
                      "手动下载后放到 PATH，或用 SMR_BIN 指定。" % (key,))
    name, url = rel
    os.makedirs(BIN_DIR, exist_ok=True)
    zpath = os.path.join(BIN_DIR, name)
    sys.stderr.write("[%s] 下载 %s\n" % (TOOL, url))
    try:
        with urllib.request.urlopen(download_request(url),
                                    timeout=timeout) as resp, \
                io.open(zpath, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    except Exception as exc:
        return None, "下载失败: %s: %s（可手动下载后放到 PATH，或用 SMR_BIN 指定；HTTP 403 通常是 UA 被拒）" % (type(exc).__name__, exc)
    try:
        with zipfile.ZipFile(zpath) as z:
            z.extractall(BIN_DIR)
    except Exception as exc:
        return None, "解压失败: %s: %s" % (type(exc).__name__, exc)
    try:
        os.remove(zpath)
    except OSError:
        pass
    path = find_smr()
    if path and os.name != "nt":
        try:
            os.chmod(path, 0o755)
        except OSError:
            pass
    return path, None if path else "解压完成但没找到可执行文件"


# ============================================================== 文本格式读取
def read_ma(path):
    """GCTA-COJO 格式的 GWAS summary。

    列固定为 SNP A1 A2 freq b se p n（表头会被忽略，与官方一致）。
    """
    out = {}
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            f = ln.split()
            if len(f) < 7:
                continue
            try:
                float(f[4]), float(f[5])
            except ValueError:
                continue                      # 表头行
            out[f[0]] = dict(a1=f[1], a2=f[2], freq=f[3],
                             b=float(f[4]), se=float(f[5]), p=float(f[6]))
    return out


def read_esd(path):
    """ESD 格式（SMR 官方 "Make a BESD file" 第 1 种输入）。

    Chr SNP Bp A1 A2 Freq Beta se p
    """
    out = {}
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            f = ln.split()
            if len(f) < 9:
                continue
            try:
                int(f[2])
                float(f[5])
            except ValueError:
                continue
            out[f[1]] = dict(chr=f[0], bp=int(f[2]), a1=f[3], a2=f[4],
                             freq=float(f[5]), b=float(f[6]),
                             se=float(f[7]), p=float(f[8]))
    return out


def read_flist(path):
    """flist：Chr ProbeID GeneticDistance ProbeBp Gene Orientation PathOfEsd"""
    rows = []
    base = os.path.dirname(os.path.abspath(path))
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            f = ln.split()
            if len(f) < 7 or f[0] == "Chr":
                continue
            esd = f[6]
            if not os.path.isabs(esd):
                cand = os.path.join(base, esd)
                esd = cand if os.path.exists(cand) else esd
            rows.append(dict(chr=f[0], probe=f[1], probe_bp=f[3],
                             gene=f[4], ori=f[5], esd=esd))
    return rows


def read_query_table(path):
    """解析官方 --query 输出（15 列，带表头）。"""
    rows, head = [], None
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            f = ln.rstrip("\n").split("\t")
            if head is None:
                head = f
                continue
            if len(f) != len(head):
                continue
            rows.append(dict(zip(head, f)))
    return rows


def write_esd_from_query(recs, prefix):
    """把 query 表按 probe 拆成每 probe 一个 .esd + 一个 .flist（均带表头）。

    这样官方 BESD 可以直接喂给 native 引擎，无需逆向官方私有二进制格式。
    """
    groups = {}
    for r in recs:
        groups.setdefault(r["Probe"], []).append(r)
    base = os.path.dirname(os.path.abspath(prefix)) or "."
    stem = os.path.basename(prefix)
    made = []
    flist = ["Chr\tProbeID\tGeneticDistance\tProbeBp\tGene\tOrientation\tPathOfEsd"]
    for i, (probe, rs) in enumerate(sorted(groups.items()), 1):
        rs.sort(key=lambda r: int(float(r["BP"])))
        p0 = rs[0]
        name = "%s_%d.esd" % (stem, i)
        path = os.path.join(base, name)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("Chr\tSNP\tBp\tA1\tA2\tFreq\tBeta\tse\tp\n")
            for r in rs:
                fh.write("\t".join([r["Chr"], r["SNP"], r["BP"], r["A1"], r["A2"],
                                    r["Freq"], r["b"], r["SE"], r["p"]]) + "\n")
        flist.append("\t".join([
            p0.get("Probe_Chr") or "NA", probe, "0", p0.get("Probe_bp") or "NA",
            p0.get("Gene") or "NA", p0.get("Orientation") or "NA", name]))
        made.append(dict(probe=probe, esd=path, n_snp=len(rs)))
    with io.open(prefix + ".flist", "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(flist) + "\n")
    return made


# ============================================================== PLINK bfile
class Plink(object):
    """只读 PLINK 1 二进制（.bed/.bim/.fam），够用来算 LD。"""

    def __init__(self, prefix):
        bim, fam, bed = prefix + ".bim", prefix + ".fam", prefix + ".bed"
        for p in (bim, fam, bed):
            if not os.path.exists(p):
                raise IOError("缺少 PLINK 文件: %s" % p)
        self.snps = []
        with io.open(bim, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                f = ln.split()
                if len(f) >= 6:
                    self.snps.append(dict(chr=f[0], snp=f[1], bp=int(f[3]),
                                          a1=f[4], a2=f[5]))
        self.index = {s["snp"]: i for i, s in enumerate(self.snps)}
        with io.open(fam, encoding="utf-8", errors="replace") as fh:
            self.n = sum(1 for ln in fh if ln.strip())
        self.raw = io.open(bed, "rb").read()
        if self.raw[:3] != b"\x6c\x1b\x01":
            raise IOError("%s 不是 PLINK 1 bed（魔法数不匹配）" % bed)
        self.per = (self.n + 3) // 4

    def dosage(self, snp):
        """返回 A1 拷贝数列表；缺失为 None。

        bed 编码（PLINK 1，SNP-major）：
          00 = 纯合第一个等位(.bim 第 5 列 A1)  01 = 缺失
          10 = 杂合                            11 = 纯合第二个等位(A2)
        """
        i = self.index.get(snp)
        if i is None:
            return None
        row = self.raw[3 + i * self.per:3 + (i + 1) * self.per]
        out = []
        for k in range(self.n):
            code = (row[k >> 2] >> ((k & 3) * 2)) & 0b11
            out.append({0: 2.0, 1: None, 2: 1.0, 3: 0.0}[code])
        return out


def _r(x, y):
    pr = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    m = len(pr)
    if m < 3:
        return None
    mx = sum(p[0] for p in pr) / m
    my = sum(p[1] for p in pr) / m
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pr)
    sxx = sum((p[0] - mx) ** 2 for p in pr)
    syy = sum((p[1] - my) ** 2 for p in pr)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


# ================================================================= 统计分布
def _gser(a, x):
    ap, s = a, 1.0 / a
    d = s
    for _ in range(3000):
        ap += 1
        d *= x / ap
        s += d
        if abs(d) < abs(s) * 1e-16:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a, x):
    tiny = 1e-300
    b = x + 1 - a
    c, d = 1 / tiny, 1 / b
    h = d
    for i in range(1, 3000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        de = d * c
        h *= de
        if abs(de - 1) < 1e-16:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(x, k):
    """卡方分布上尾概率 P(X > x)，无需 scipy。"""
    if x <= 0:
        return 1.0
    a, xx = k / 2.0, x / 2.0
    return (1.0 - _gser(a, xx)) if xx < a + 1 else _gcf(a, xx)


def z_p(z):
    """双侧正态 p 值。"""
    return math.erfc(abs(z) / math.sqrt(2.0))


# ================================================================ 原生引擎
class NativeEngine(object):
    """零依赖的 SMR + HEIDI 实现。

    SMR 检验与官方逐位一致（实测 b/se/p 三项全等）。HEIDI 采用
    「相对 target SNP 的偏差 Σ d²/Var(d)，含 LD 协方差校正」这一标准形式，
    与官方结论一致，但官方未公开其 HEIDI 精确实现，小数位可能有差异；
    需要与已发表数字严格对齐时请用 --engine official。
    """

    def __init__(self, gwas, bfile=None, ld_cache=None):
        self.gwas = gwas
        self.plink = Plink(bfile) if bfile else None
        self._geno = {}
        self._r = ld_cache if ld_cache is not None else {}

    def geno(self, snp):
        if snp not in self._geno:
            self._geno[snp] = self.plink.dosage(snp) if self.plink else None
        return self._geno[snp]

    def ld(self, s1, s2):
        if s1 == s2:
            return 1.0
        key = (s1, s2) if s1 < s2 else (s2, s1)
        if key not in self._r:
            a, b = self.geno(s1), self.geno(s2)
            self._r[key] = _r(a, b) if (a and b) else None
        return self._r[key]

    @staticmethod
    def bxy(g, e):
        return g["b"] / e["b"]

    @staticmethod
    def vxy(g, e):
        b = g["b"] / e["b"]
        return g["se"] ** 2 / e["b"] ** 2 + b ** 2 * e["se"] ** 2 / e["b"] ** 2

    def covxy(self, s1, s2, e):
        r = self.ld(s1, s2)
        if r is None:
            return 0.0
        g1, g2 = self.gwas[s1], self.gwas[s2]
        e1, e2 = e[s1], e[s2]
        return (r * g1["se"] * g2["se"] / (e1["b"] * e2["b"])
                + (g1["b"] / e1["b"]) * (g2["b"] / e2["b"])
                * r * e1["se"] * e2["se"] / (e1["b"] * e2["b"]))

    def _pick_heidi_snps(self, e, top, opts):
        """官方 HEIDI 选 SNP：cis 窗口 -> p_eQTL 阈值 -> LD 修剪。

        两种修剪规则都对得上官方实测：
          mtd=0：只与 top 比（去 r²>上限 与 r²<下限）  -> nsnp=7（本例）
          mtd=1：在 mtd=0 结果上再做逐步修剪（去 r²>上限）-> nsnp=6（本例）
        """
        probp = float(e[top]["bp"]) if "bp" in e[top] else None
        cand = [s for s in e
                if e[s].get("p", 1.0) < opts["peqtl_heidi"]
                and (probp is None or "bp" not in e[s]
                     or abs(e[s]["bp"] - probp) <= opts["cis_wind"] * 1000)]
        cand.sort(key=lambda s: e[s]["p"])
        out = []
        for s in cand:
            if s == top:
                out.append(s)
                continue
            r = self.ld(s, top)
            if r is None:
                continue
            r2 = r * r
            if opts["ld_lower"] < r2 < opts["ld_upper"]:
                out.append(s)
        if opts["heidi_mtd"] == 1:
            pruned = []
            for s in out:                       # 逐步修剪：与已保留的任意一个太像就去掉
                if all((self.ld(s, k) is None
                        or (self.ld(s, k) ** 2) <= opts["ld_upper"])
                       for k in pruned):
                    pruned.append(s)
            out = pruned
        return out[:opts["heidi_max_m"]]

    def smr(self, probe, e, opts):
        """对一个 probe 跑 SMR (+HEIDI)。返回官方 .smr 同构的 dict。"""
        common = [s for s in e if s in self.gwas]
        if not common:
            return None
        top = min(common, key=lambda s: e[s]["p"])
        g_t, e_t = self.gwas[top], e[top]
        if e_t["p"] > opts["peqtl_smr"]:
            return None                          # 没达到 top eQTL 显著阈值
        b = self.bxy(g_t, e_t)
        v = self.vxy(g_t, e_t)
        se = math.sqrt(v) if v > 0 else float("nan")
        z = b / se if se > 0 else float("nan")
        row = dict(
            probeID=probe["probe"], ProbeChr=probe.get("chr", e_t.get("chr", "NA")),
            Gene=probe.get("gene", "NA"), Probe_bp=probe.get("probe_bp", "NA"),
            topSNP=top, topSNP_chr=e_t.get("chr", "NA"), topSNP_bp=e_t.get("bp", "NA"),
            A1=g_t["a1"], A2=g_t["a2"], Freq=g_t["freq"],
            b_GWAS=g_t["b"], se_GWAS=g_t["se"], p_GWAS=g_t["p"],
            b_eQTL=e_t["b"], se_eQTL=e_t["se"], p_eQTL=e_t["p"],
            b_SMR=b, se_SMR=se, p_SMR=chi2_sf(z * z, 1), p_HEIDI="NA", nsnp_HEIDI=0)

        if opts["heidi_off"]:
            return row
        snps = self._pick_heidi_snps(e, top, opts)
        row["nsnp_HEIDI"] = len(snps)
        if len(snps) < opts["heidi_min_m"]:
            return row                           # 官方：SNP 太少则不跑 HEIDI，留 NA

        bt = self.bxy(g_t, e_t)
        others = [s for s in snps if s != top]
        d, vd = [], []
        for s in others:
            d.append(self.bxy(self.gwas[s], e[s]) - bt)
            vd.append(self.vxy(self.gwas[s], e[s]) + v
                      - 2 * self.covxy(s, top, e))
        num = 0.0
        for i in range(len(d)):
            if vd[i] > 0:
                num += d[i] * d[i] / vd[i]
        row["p_HEIDI"] = chi2_sf(num, max(1, len(d)))
        row["_heidi_Q"] = num
        return row


# ============================================================== 官方引擎
def run_official(binpath, args, cwd=None, timeout=1800):
    """跑官方二进制并把全部输出收进日志（stdout 必须保持纯 JSON）。"""
    exe = binpath
    if os.name == "nt" and exe.lower().endswith(".exe"):
        pass
    p = subprocess.run([exe] + args, cwd=cwd, capture_output=True,
                       text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


# 官方二进制的错误往往**不影响 returncode**（实测 `can not open the file
# [...] to read.` 之后仍然 exit 0），只写在日志里。不显式检查就会把失败当成功。
_ERROR_PREFIXES = ("Error:", "ERROR:", "error:")


def official_error(log):
    """从官方日志里揪出错误行；没有则返回 None。"""
    for ln in (log or "").splitlines():
        t = ln.strip()
        if t.startswith(_ERROR_PREFIXES):
            return t
    return None


def parse_smr_table(path):
    """解析官方 .smr 结果表（tab 分隔，带表头）。"""
    rows = []
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        head = None
        for ln in fh:
            f = ln.rstrip("\n").split("\t")
            if head is None:
                head = f
                continue
            if len(f) != len(head):
                continue
            rows.append(dict(zip(head, f)))
    return rows


# ==================================================================== 命令
def cmd_preflight(a):
    info = dict(tool=TOOL, ok=True, official=dict(), native=dict(), inputs=dict())
    b = find_smr(a.smr_bin)
    info["official"] = dict(found=bool(b), path=b, cache_dir=BIN_DIR,
                            platform=list(platform_key()))
    if b:
        try:
            rc, out, err = run_official(b, ["--help"], timeout=120)
            ver = [l for l in (out + err).splitlines() if "Version" in l]
            info["official"]["version"] = ver[0].split()[-1] if ver else "unknown"
        except Exception as exc:
            info["official"]["version"] = "probe failed: %s" % exc
    for k, p in (("gwas", a.gwas), ("esd", a.esd), ("flist", a.flist),
                 ("beqtl", a.beqtl), ("bfile", a.bfile)):
        if p:
            info["inputs"][k] = os.path.exists(p if k != "bfile" else p + ".bed")
    info["native"] = dict(ready=True, note="标准库实现，无外部依赖")
    if not b:
        info["ok"] = False
        info["hint"] = ("未找到官方 smr 二进制。运行 `python %s fetch-binary` 自动下载，"
                        "或手动下载后设 SMR_BIN 指向它。" % os.path.basename(__file__))
    emit(info)


def cmd_fetch_binary(a):
    path, err = download_binary()
    if err and not path:
        fail(TOOL, err, "也可手动下载：https://yanglab.westlake.edu.cn/software/smr/#Download",
             exit_code=1)
    emit(dict(tool=TOOL, ok=True, path=path, cache_dir=BIN_DIR,
              hint="已就绪，可以直接 --engine official 使用"))


def cmd_make_besd(a):
    b = find_smr(a.smr_bin)
    if not b:
        fail(TOOL, "make-besd 需要官方 smr 二进制",
             "运行 `python %s fetch-binary` 下载（BESD 是官方私有二进制格式）"
             % os.path.basename(__file__), exit_code=2)
    if not a.flist and not a.eqtl_summary:
        fail(TOOL, "make-besd 需要 --flist 或 --eqtl-summary",
             "flist 格式：Chr ProbeID GeneticDistance ProbeBp Gene Orientation PathOfEsd",
             exit_code=2)
    # 官方按 CWD 解析 .flist 里的相对 ESD 路径，也按 CWD 写 --out。
    # 因此统一在输入文件所在目录执行，并把 --out 绝对化；
    # 否则换个工作目录调用就会全线 "can not open the file"，而官方仍 exit 0。
    src = a.flist or a.eqtl_summary
    run_cwd = None
    if src and os.path.exists(src):
        run_cwd = os.path.dirname(os.path.abspath(src)) or None
    out = os.path.abspath(a.out) if a.out else None

    args = []
    if a.flist:
        args += ["--eqtl-flist", os.path.abspath(a.flist)]
    else:
        args += ["--eqtl-summary", os.path.abspath(a.eqtl_summary)]
        for flag, on in (("--matrix-eqtl-format", a.matrix_eqtl_format),
                         ("--fastqtl-nominal-format", a.fastqtl_nominal_format),
                         ("--plink-qassoc-format", a.plink_qassoc_format),
                         ("--gemma-format", a.gemma_format),
                         ("--bolt-assoc-format", a.bolt_assoc_format)):
            if on:
                args.append(flag)
    args.append("--make-besd-dense" if a.dense else "--make-besd")
    if a.geno_uni:
        args.append("--geno-uni")
    if out:
        args += ["--out", out]
    for k in ("cis_wind", "trans_wind", "peqtl_trans", "peqtl_other"):
        v = getattr(a, k, None)
        if v is not None:
            args += ["--" + k.replace("_", "-"), str(v)]
    rc, so, se = run_official(b, args, cwd=run_cwd)
    log = so + se
    errline = official_error(log)
    # BESD 三件套是 make-besd 的最小成功凭证：.besd 存数据、.esi 存 SNP、.epi 存 probe。
    expected = [out + e for e in (".besd", ".esi", ".epi")] if out else []
    prods = [dict(path=p, bytes=os.path.getsize(p))
             for p in expected if os.path.exists(p)]
    missing = [p for p in expected if not os.path.exists(p)]
    ok = rc == 0 and not errline and not missing
    payload = dict(tool=TOOL, ok=ok, exit=rc, cmd=[b] + args,
                   products=prods, missing=missing, log=log[-4000:])
    if errline:
        payload["official_error"] = errline
    emit(payload, 0 if ok else 1)


def cmd_ld(a):
    try:
        pl = Plink(a.bfile)
    except (IOError, OSError) as exc:
        fail(TOOL, "读取 PLINK 数据失败: %s" % exc, exit_code=2)
    if a.snp:
        if a.snp not in pl.index:
            fail(TOOL, "bfile 里没有 SNP: %s" % a.snp, exit_code=2)
        g0 = pl.dosage(a.snp)
        rows = []
        for s in pl.snps:
            r = _r(g0, pl.dosage(s["snp"]))
            if r is not None:
                rows.append((s["snp"], r, r * r))
        rows.sort(key=lambda x: -abs(x[1]))
        if a.out:
            with io.open(a.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("SNP\tr\tr2\n")
                for n, r, r2 in rows:
                    fh.write("%s\t%.8f\t%.8f\n" % (n, r, r2))
        emit(dict(tool=TOOL, ok=True, ref_snp=a.snp, n=len(rows),
                  n_individuals=pl.n, out=a.out,
                  ld=[dict(snp=n, r=r, r2=r2) for n, r, r2 in rows[:a.top]]))
    else:
        snps = [s["snp"] for s in pl.snps]
        mat = [[_r(pl.dosage(x), pl.dosage(y)) for y in snps] for x in snps]
        if a.out:
            with io.open(a.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("SNP\t" + "\t".join(snps) + "\n")
                for i, x in enumerate(snps):
                    fh.write(x + "\t" + "\t".join(
                        "NA" if v is None else "%.6f" % v for v in mat[i]) + "\n")
        emit(dict(tool=TOOL, ok=True, n_snp=len(snps), n_individuals=pl.n,
                  out=a.out, snps=snps))


def cmd_dump_besd(a):
    """把官方 .besd 导出成文本，可选拆成 ESD + flist 供 native 引擎消费。

    官方 --query 的语义是「按 eQTL p 值阈值导出子集」，默认 5.0e-8；
    取 --query 1 即全量导出。导入的是 SMR query 输出格式（15 列）：
      SNP Chr BP A1 A2 Freq Probe Probe_Chr Probe_bp Gene Orientation b SE p
    加 --to-esd 时按 Probe 拆分，写出 <out>_N.esd 与 <out>.flist。
    """
    b = find_smr(a.smr_bin)
    if not b:
        fail(TOOL, "dump-besd 需要官方 smr 二进制",
             "运行 `python %s fetch-binary` 下载（BESD 是官方私有二进制格式）"
             % os.path.basename(__file__),
             exit_code=2)
    if not os.path.exists(a.besd + ".besd") and not os.path.exists(a.besd):
        fail(TOOL, "找不到 BESD: %s" % a.besd,
             "需要 <prefix>.besd / .esi / .epi 三件套，--besd 传前缀而非文件名",
             exit_code=2)
    out_abs = os.path.abspath(a.out)
    args = ["--beqtl-summary", os.path.abspath(a.besd),
            "--query", fmt_num(a.query), "--out", out_abs]
    for flag, attr in (("--snp", "snp"), ("--probe", "probe"),
                       ("--snp-chr", "snp_chr"), ("--probe-chr", "probe_chr"),
                       ("--extract-snp", "extract_snp"),
                       ("--extract-probe", "extract_probe"),
                       ("--genes", "genes")):
        v = getattr(a, attr, None)
        if v:
            args += [flag, v]
    rc, so, se = run_official(b, args)
    qfile = out_abs + ".txt"
    errline = official_error(so + se)
    payload = dict(tool=TOOL, ok=False, exit=rc, cmd=[b] + args,
                   query_file=qfile, log=(so + se)[-2000:])
    if errline:
        payload["official_error"] = errline
    if rc != 0 or errline or not os.path.exists(qfile):
        emit(payload, 1)
        return
    payload["ok"] = True
    recs = read_query_table(qfile)
    payload["n_records"] = len(recs)
    payload["n_probes"] = len(set(r["Probe"] for r in recs))
    if a.to_esd and recs:
        made = write_esd_from_query(recs, out_abs)
        payload["esd_files"] = made[:50]
        payload["n_esd"] = len(made)
        payload["flist"] = out_abs + ".flist"
    emit(payload, 0)


def cmd_analyze(a):
    engine = a.engine
    if engine == "auto":
        engine = "official" if find_smr(a.smr_bin) else "native"
    if engine == "official":
        return analyze_official(a)
    return analyze_native(a)


def analyze_official(a):
    """官方引擎：把本技能暴露的 flag 全量翻译成官方 flag。

    未在本工具显式列出的官方 flag，一律用 --raw（或用 `official` 子命令）
    原样透传，因此官方功能不会被本包装层截断。
    """
    beqtl = a.beqtl if isinstance(a.beqtl, list) else ([a.beqtl] if a.beqtl else [])
    if not a.bfile or not a.gwas or not beqtl:
        fail(TOOL, "official 引擎需要 --bfile / --gwas / --beqtl",
             "双分子性状（omics/two-sample）SMR 传两次 --beqtl；另加 --out 指定输出前缀",
             exit_code=2)
    b = find_smr(a.smr_bin)
    if not b:
        fail(TOOL, "未找到官方 smr 二进制",
             "运行 `python %s fetch-binary` 下载，或加 --engine native 走零依赖实现"
             % os.path.basename(__file__), exit_code=2)
    out = a.out or "smr_result"
    args = ["--bfile", a.bfile, "--gwas-summary", a.gwas]
    for x in beqtl:
        args += ["--beqtl-summary", x]
    args += ["--out", out, "--thread-num", str(a.thread_num)]
    append_official_flags(args, a)
    if a.raw:
        args += a.raw.split()
    rc, so, se = run_official(b, args)
    log = so + se
    errline = official_error(log)
    res_path = out + ".smr"
    rows = parse_smr_table(res_path) if os.path.exists(res_path) else []
    ok = rc == 0 and bool(rows) and not errline
    payload = dict(tool=TOOL, ok=ok, engine="official",
                   exit=rc, cmd=[b] + args, result_file=res_path,
                   n_results=len(rows), results=rows,
                   log=log[-4000:] if not ok else "")
    if errline:
        payload["official_error"] = errline
    outs = collect_outputs(out, skip=os.path.basename(res_path))
    if outs:
        payload["outputs"] = outs
    emit(payload, 0 if ok else 1)


def cmd_official(a):
    """原样透传任意官方 flag —— 官方功能一个不缺的兜底入口。

    用法：python mr_smr.py official -- --bfile ref --gwas-summary g.ma \
              --beqtl-summary eqtl --out r --smr-multi --set-list s.list
    """
    b = find_smr(None)
    if not b:
        fail(TOOL, "未找到官方 smr 二进制",
             "运行 `python %s fetch-binary` 下载，或用 SMR_BIN 指定路径"
             % os.path.basename(__file__), exit_code=2)
    args = [x for x in list(a.args) if x != "--"]
    if not args:
        fail(TOOL, "official 需要透传参数",
             "例：official -- --beqtl-summary eqtl --query 1e-6 --out q",
             exit_code=2)
    rc, so, se = run_official(b, args)
    log = so + se
    errline = official_error(log)
    ok = rc == 0 and not errline
    outputs = []
    if "--out" in args:
        outputs = collect_outputs(args[args.index("--out") + 1])
    payload = dict(tool=TOOL, ok=ok, exit=rc, engine="official-raw",
                   cmd=[b] + args, outputs=outputs, log=log[-6000:])
    if errline:
        payload["official_error"] = errline
    emit(payload, 0 if ok else 1)


def analyze_native(a):
    if not a.gwas:
        fail(TOOL, "native 引擎需要 --gwas（GCTA-COJO 格式 .ma）", exit_code=2)
    if not a.esd and not a.flist:
        fail(TOOL, "native 引擎需要 --esd（单个 ESD 文本）或 --flist",
             "若手里是官方 .besd，先用 `dump-besd` 或官方 `--recode` 导出文本",
             exit_code=2)
    if not os.path.exists(a.gwas):
        fail(TOOL, "找不到 GWAS 文件: %s" % a.gwas, exit_code=2)
    gwas = read_ma(a.gwas)
    if not gwas:
        fail(TOOL, "GWAS 文件解析后为空，检查是否为 GCTA-COJO 格式（SNP A1 A2 freq b se p n）",
             exit_code=1)

    probes = []
    if a.flist:
        for r in read_flist(a.flist):
            probes.append(r)
    else:
        probes.append(dict(chr="NA", probe=os.path.basename(a.esd),
                           probe_bp="NA", gene="NA", ori="NA", esd=a.esd))

    opts = dict(peqtl_smr=a.peqtl_smr if a.peqtl_smr is not None else DEFAULTS["peqtl_smr"],
                peqtl_heidi=a.peqtl_heidi if a.peqtl_heidi is not None else DEFAULTS["peqtl_heidi"],
                ld_upper=a.ld_upper if a.ld_upper is not None else DEFAULTS["ld_upper"],
                ld_lower=a.ld_lower if a.ld_lower is not None else DEFAULTS["ld_lower"],
                heidi_min_m=a.heidi_min_m if a.heidi_min_m is not None else DEFAULTS["heidi_min_m"],
                heidi_max_m=a.heidi_max_m if a.heidi_max_m is not None else DEFAULTS["heidi_max_m"],
                cis_wind=a.cis_wind if a.cis_wind is not None else DEFAULTS["cis_wind"],
                heidi_mtd=1 if a.heidi_mtd is None else a.heidi_mtd,
                heidi_off=bool(a.heidi_off))

    if a.bfile and not os.path.exists(a.bfile + ".bed"):
        fail(TOOL, "找不到 PLINK 数据: %s.bed" % a.bfile,
             "LD 估计需要参考基因型；或先跑 `ld` 子命令导出 LD 表", exit_code=2)
    try:
        eng = NativeEngine(gwas, bfile=a.bfile)
    except (IOError, OSError) as exc:
        fail(TOOL, "读取 PLINK 数据失败: %s" % exc, exit_code=2)

    results, skipped = [], []
    for p in probes:
        if not os.path.exists(p["esd"]):
            skipped.append(dict(probe=p["probe"], reason="找不到 ESD: %s" % p["esd"]))
            continue
        e = read_esd(p["esd"])
        if not e:
            skipped.append(dict(probe=p["probe"], reason="ESD 解析为空"))
            continue
        row = eng.smr(p, e, opts)
        if row is None:
            skipped.append(dict(probe=p["probe"],
                                reason="没有 SNP 同时出现在 GWAS 与 ESD，或未过 --peqtl-smr"))
        else:
            results.append(row)

    payload = dict(tool=TOOL, ok=bool(results), engine="native",
                   n_results=len(results), results=results,
                   skipped=skipped[:50],
                   heidi_note=("HEIDI 为本技能的独立实现，与官方结论一致；"
                               "官方未公开其 HEIDI 精确公式，小数位可能有差异。"
                               "需要与已发表数字严格对齐时用 --engine official。"),
                   params=opts)
    if a.out:
        tsv = a.out + ".smr"
        cols = ["probeID", "ProbeChr", "Gene", "Probe_bp", "topSNP", "topSNP_chr",
                "topSNP_bp", "A1", "A2", "Freq", "b_GWAS", "se_GWAS", "p_GWAS",
                "b_eQTL", "se_eQTL", "p_eQTL", "b_SMR", "se_SMR", "p_SMR",
                "p_HEIDI", "nsnp_HEIDI"]
        with io.open(tsv, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\t".join(cols) + "\n")
            for r in results:
                fh.write("\t".join(str(r.get(c, "NA")) for c in cols) + "\n")
        payload["result_file"] = tsv
    emit(payload, 0 if results else 1)


# ====================================================================== CLI
def build_parser():
    ap = argparse.ArgumentParser(
        prog="mr_smr.py",
        description="SMR（Summary-data-based MR）分析与数据工具")
    sub = ap.add_subparsers(dest="cmd")

    def common_inputs(p):
        p.add_argument("--smr-bin", help="官方 smr 可执行文件路径（也可用 SMR_BIN 环境变量）")

    p = sub.add_parser("preflight", help="探测官方二进制与输入文件")
    common_inputs(p)
    for f in ("--gwas", "--esd", "--flist", "--beqtl", "--bfile"):
        p.add_argument(f)
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("fetch-binary", help="下载官方 smr 二进制到全局缓存")
    p.set_defaults(func=cmd_fetch_binary)

    p = sub.add_parser("make-besd", help="文本 eQTL -> BESD（需官方二进制）")
    common_inputs(p)
    p.add_argument("--flist")
    p.add_argument("--eqtl-summary")
    p.add_argument("--matrix-eqtl-format", action="store_true")
    p.add_argument("--fastqtl-nominal-format", action="store_true")
    p.add_argument("--plink-qassoc-format", action="store_true")
    p.add_argument("--gemma-format", action="store_true")
    p.add_argument("--bolt-assoc-format", action="store_true")
    p.add_argument("--dense", action="store_true", help="密集 BESD（体积巨大）")
    p.add_argument("--geno-uni", action="store_true", help="所有 ESD 的 SNP 集合相同，加速")
    p.add_argument("--cis-wind", type=int)
    p.add_argument("--trans-wind", type=int)
    p.add_argument("--peqtl-trans", type=float)
    p.add_argument("--peqtl-other", type=float)
    p.add_argument("--out")
    p.set_defaults(func=cmd_make_besd)

    p = sub.add_parser("ld", help="从 PLINK bfile 计算 LD（纯标准库）")
    p.add_argument("--bfile", required=True)
    p.add_argument("--snp", help="给定时输出该 SNP 对其他所有 SNP 的 r/r2")
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--out")
    p.set_defaults(func=cmd_ld)

    p = sub.add_parser("dump-besd", help="把官方 .besd 导出成文本（经官方 --query）")
    common_inputs(p)
    p.add_argument("--besd", required=True, help="BESD 前缀（不是文件名）")
    p.add_argument("--query", type=float, default=1.0,
                   help="eQTL p 值阈值，导出 p<=该值的记录（默认 1=全量导出）")
    p.add_argument("--to-esd", dest="to_esd", action="store_true",
                   help="再按 probe 拆成 .esd + .flist，供 native 引擎直接消费")
    p.add_argument("--snp")
    p.add_argument("--probe")
    p.add_argument("--snp-chr", dest="snp_chr")
    p.add_argument("--probe-chr", dest="probe_chr")
    p.add_argument("--extract-snp", dest="extract_snp")
    p.add_argument("--extract-probe", dest="extract_probe")
    p.add_argument("--genes")
    p.add_argument("--out", required=True, help="输出前缀（官方写成 <out>.txt）")
    p.set_defaults(func=cmd_dump_besd)

    p = sub.add_parser("official",
                       help="原样透传任意官方 flag（官方功能全覆盖的兜底入口）")
    p.add_argument("args", nargs=argparse.REMAINDER,
                   help="官方参数原样，建议紧跟 -- ：official -- --beqtl-summary e --out r")
    p.set_defaults(func=cmd_official)

    p = sub.add_parser("analyze",
                       help="跑 SMR (+HEIDI)：official=官方全功能，native=零依赖")
    common_inputs(p)
    p.add_argument("--engine", default="auto", choices=["auto", "official", "native"])
    p.add_argument("--bfile", help="PLINK 参考基因型（LD 估计）")
    p.add_argument("--gwas", help="GCTA-COJO 格式 GWAS summary")
    p.add_argument("--beqtl", action="append", default=[],
                   help="BESD 前缀（official）；给两次即双分子性状/omics SMR")
    p.add_argument("--esd", help="ESD 文本（native 引擎）")
    p.add_argument("--flist", help="flist（native 引擎，可含多个 probe）")
    p.add_argument("--out", help="输出前缀")
    p.add_argument("--thread-num", type=int, default=1)
    # --- SMR / HEIDI 核心 ---
    p.add_argument("--peqtl-smr", type=float, help="cis-eQTL 入选阈值（默认 5e-8）")
    p.add_argument("--peqtl-heidi", type=float, help="HEIDI 选 SNP 阈值（默认 1.57e-3）")
    p.add_argument("--cis-wind", type=int, help="cis 窗口 Kb（默认 2000）")
    p.add_argument("--smr-wind", dest="smr_wind", type=int,
                   help="--extract-snp-probe 用的窗口 Kb")
    p.add_argument("--ld-upper", dest="ld_upper", type=float,
                   help="HEIDI 修剪 LD r2 上限（默认 0.9）")
    p.add_argument("--ld-lower", dest="ld_lower", type=float,
                   help="HEIDI 修剪 LD r2 下限（默认 0.05）")
    p.add_argument("--ld-multi-snp", dest="ld_multi_snp", action="store_true",
                   help="multi-SNP SMR 的 LD 用 SNP 两两估计")
    p.add_argument("--heidi-min-m", dest="heidi_min_m", type=int,
                   help="HEIDI 最少 SNP 数（默认 3）")
    p.add_argument("--heidi-max-m", dest="heidi_max_m", type=int,
                   help="HEIDI 最多 SNP 数（默认 20）")
    p.add_argument("--heidi-mtd", dest="heidi_mtd", type=int, choices=[0, 1],
                   help="HEIDI 方法：0=原始 1=新法（默认 1）")
    p.add_argument("--heidi-off", dest="heidi_off", action="store_true",
                   help="关闭 HEIDI 检验")
    p.add_argument("--phet", type=float, help="异质性检验 p 值阈值")
    # --- trans 区域 ---
    p.add_argument("--trans", action="store_true", help="trans 区域 SMR")
    p.add_argument("--peqtl-trans", dest="peqtl_trans", type=float,
                   help="trans-eQTL 阈值（默认 5e-8）")
    p.add_argument("--trans-wind", dest="trans_wind", type=int,
                   help="trans 窗口 Kb（默认 1000）")
    # --- multi-SNP / set-based ---
    p.add_argument("--smr-multi", dest="smr_multi", action="store_true",
                   help="multi-SNP SMR（set-based 检验）")
    p.add_argument("--set-list", dest="set_list", help="SNP set 列表文件")
    p.add_argument("--set-wind", dest="set_wind", type=int, help="set 窗口 Kb")
    # --- 双分子性状（omics / two-sample SMR）---
    p.add_argument("--extract-exposure-probe", dest="extract_exposure_probe")
    p.add_argument("--extract-outcome-probe", dest="extract_outcome_probe")
    p.add_argument("--exclude-exposure-probe", dest="exclude_exposure_probe")
    p.add_argument("--exclude-outcome-probe", dest="exclude_outcome_probe")
    p.add_argument("--extract-single-exposure-probe",
                   dest="extract_single_exposure_probe")
    p.add_argument("--extract-single-outcome-probe",
                   dest="extract_single_outcome_probe")
    # --- 选择 / 抽取 ---
    p.add_argument("--extract-snp", dest="extract_snp")
    p.add_argument("--exclude-snp", dest="exclude_snp")
    p.add_argument("--extract-probe", dest="extract_probe")
    p.add_argument("--exclude-probe", dest="exclude_probe")
    p.add_argument("--extract-snp-probe", dest="extract_snp_probe")
    p.add_argument("--extract-target-snp-probe", dest="extract_target_snp_probe")
    p.add_argument("--genes", help="基因列表（抽取对应 probe）")
    p.add_argument("--target-snp", dest="target_snp", help="强制指定 target SNP")
    p.add_argument("--smr-file", dest="smr_file", help="复用已有 .smr 结果表")
    # --- QC ---
    p.add_argument("--maf", type=float, help="MAF 过滤阈值")
    p.add_argument("--disable-freq-ck", dest="disable_freq_ck", action="store_true",
                   help="关闭等位基因频率一致性检查")
    p.add_argument("--diff-freq", dest="diff_freq", type=float, help="允许的频率差")
    p.add_argument("--diff-freq-prop", dest="diff_freq_prop", type=float,
                   help="允许的频率差比例")
    # --- 进阶功能 ---
    p.add_argument("--mecs", action="store_true", help="MeCS 分析")
    p.add_argument("--pmecs", action="store_true", help="pMeCS")
    p.add_argument("--mmecs", action="store_true", help="mMeCS")
    p.add_argument("--nmecs", type=int, help="nMeCS 的 SNP 数")
    p.add_argument("--meta", action="store_true", help="SMR 结果 meta 分析")
    p.add_argument("--psmr", type=float, help="PSMR p 值阈值")
    p.add_argument("--plot", action="store_true", help="输出 SMR locus plot 数据")
    p.add_argument("--gene-list", dest="gene_list", help="--plot 用的基因区间列表")
    p.add_argument("--probe-wind", dest="probe_wind", type=int)
    p.add_argument("--describe-cis", dest="descriptive_cis", action="store_true",
                   help="打印 cis-eQTL 描述统计")
    p.add_argument("--describe-trans", dest="descriptive_trans", action="store_true",
                   help="打印 trans-eQTL 描述统计")
    p.add_argument("--raw",
                   help="附加参数原样透传给官方二进制（未列出的 flag 走这里）。"
                        "值以 - 开头时建议写 --raw=\"--flag\"，或直接用 official 子命令")
    p.set_defaults(func=cmd_analyze)

    return ap


def _normalize_argv(argv):
    """让 `--raw --some-flag` 这种写法也能用。

    argparse 的 _parse_optional 会把「以 - 开头且不含空格」的 token 当成选项，
    于是 `--raw --heidi-off` 直接报 usage 错，而 help 里又引导用户这么写。
    把紧跟在 --raw 后面、以 - 开头的值改写成 `--raw=<值>` 即可绕开
    （含空格的值 argparse 本来就当值处理，无需改写）。
    """
    out, i = [], 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--raw" and i + 1 < len(argv) and argv[i + 1].startswith("-"):
            out.append("--raw=" + argv[i + 1])
            i += 2
            continue
        out.append(tok)
        i += 1
    return out


def main():
    # `--raw --flag` 里的值会被 argparse 误判成选项，先规范化再解析
    sys.argv[1:] = _normalize_argv(sys.argv[1:])
    ap = build_parser()
    a = parse_args_or_fail(ap, TOOL)
    if not getattr(a, "func", None):
        ap.print_help(sys.stderr)
        fail(TOOL, "缺少子命令",
             "可选：preflight / fetch-binary / make-besd / ld / dump-besd / "
             "analyze / official",
             exit_code=2)
    a.func(a)


if __name__ == "__main__":
    main()
