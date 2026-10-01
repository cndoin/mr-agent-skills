#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成一个最小的、确定性的 SMR 测试数据集（纯标准库）。

    python tests/gen_smr_fixture.py <输出目录>

为什么是「生成」而不是「提交固定文件」：产物里有 PLINK 的二进制 .bed，
提交进仓库会被 core.autocrlf 之类的东西反复折腾。生成器只用标准库、
固定随机种子，因此每次产出**逐字节相同**，既干净又可重放。

产出（刻意覆盖官方 SMR 的三种文本格式，逐字对照 SMR.pdf "Make a BESD file"）：

    ref.bed / ref.bim / ref.fam   PLINK 1 二进制基因型（500 个体 × 20 SNP）
    eqtl_1.esd                    Chr SNP Bp A1 A2 Freq Beta se p  （9 列，带表头）
    eqtl.flist                    Chr ProbeID GeneticDistance ProbeBp Gene
                                  Orientation PathOfEsd            （7 列，带表头）
    gwas.ma                       SNP A1 A2 freq b se p n          （8 列，GCTA-COJO）

数据构造方式：8 条单倍型按均匀频率抽样，前 10 个 SNP 共享一个 LD 块，
再让表达量由 top SNP 驱动、性状由表达量驱动。这样 SMR 的
「SNP -> 表达 -> 性状」因果链是**已知**的，期望 b_SMR ≈ 0.50/0.60。
"""
import io
import math
import os
import random
import sys
import tempfile

N_IND = 500
N_SNP = 20
N_HAP = 8
BLOCK = 10          # 前 10 个 SNP 构成一个 LD 块
CHR = 1
BASE_BP = 1000000
PROBE_BP = 1005000
A1, A2 = "A", "G"
PROBE_ID = "ENSG00000123456"
GENE = "TESTGENE"
ORI = "+"
SEED = 20261001

# 因果结构：expr <- 0.60 * g(top)，trait <- 0.50 * expr
B_EXPR = 0.60
B_TRAIT = 0.50


def regress(x, y):
    """单变量线性回归的 beta / se，闭式解。"""
    n = len(x)
    mx = sum(x) / n
    my = sum(y) / n
    sxx = sxy = 0.0
    for i in range(n):
        dx = x[i] - mx
        sxx += dx * dx
        sxy += dx * (y[i] - my)
    b = sxy / sxx
    a = my - b * mx
    ssr = 0.0
    for i in range(n):
        r = y[i] - (a + b * x[i])
        ssr += r * r
    return b, math.sqrt((ssr / (n - 2)) / sxx)


def two_sided_p(z):
    """2 * (1 - Phi(|z|))，用 erfc 精确算，避免自己写正态积分。"""
    return math.erfc(abs(z) / math.sqrt(2.0))


def build(out_dir):
    random.seed(SEED)
    os.makedirs(out_dir, exist_ok=True)
    snps = ["rs%04d" % (1000 + i) for i in range(N_SNP)]

    def wr(name, text):
        with io.open(os.path.join(out_dir, name), "w", encoding="utf-8",
                     newline="\n") as fh:
            fh.write(text)

    # ---- 基因型：单倍型抽样，LD 结构自然产生 ----
    cum, acc = [], 0.0
    for _ in range(N_HAP):
        acc += 1.0 / N_HAP
        cum.append(acc)
    hap = [[random.randint(0, 1) for _ in range(N_SNP)] for _ in range(N_HAP)]
    for s in range(BLOCK):
        for h in range(N_HAP):
            base = 1 if h < N_HAP // 2 else 0
            hap[h][s] = base if random.random() > 0.15 else 1 - base

    def draw_hap():
        u = random.random()
        for i, c in enumerate(cum):
            if u <= c:
                return i
        return N_HAP - 1

    G = [[0] * N_IND for _ in range(N_SNP)]
    for i in range(N_IND):
        h1, h2 = draw_hap(), draw_hap()
        for s in range(N_SNP):
            G[s][i] = hap[h1][s] + hap[h2][s]

    freqs = []
    for s in range(N_SNP):
        f1 = sum(G[s]) / (2.0 * N_IND)
        if f1 > 0.5:                      # 让 A1 是次等位
            G[s] = [2 - v for v in G[s]]
            f1 = 1.0 - f1
        freqs.append(f1)

    # ---- 表型：已知因果链 ----
    top = 0
    m_top = sum(G[top]) / N_IND
    gt = [v - m_top for v in G[top]]
    expr = [B_EXPR * gt[i] + random.gauss(0.0, 1.0) for i in range(N_IND)]
    trait = [B_TRAIT * expr[i] + random.gauss(0.0, 0.8) for i in range(N_IND)]

    esd_lines, gwas_lines = [], []
    for s in range(N_SNP):
        m = sum(G[s]) / N_IND
        gc = [v - m for v in G[s]]
        b_e, se_e = regress(gc, expr)
        b_g, se_g = regress(gc, trait)
        bp = BASE_BP + s * 500
        esd_lines.append("\t".join([
            str(CHR), snps[s], str(bp), A1, A2, "%.6f" % freqs[s],
            "%.8f" % b_e, "%.8f" % se_e, "%.6e" % two_sided_p(b_e / se_e)]))
        gwas_lines.append("\t".join([
            snps[s], A1, A2, "%.6f" % freqs[s], "%.8f" % b_g, "%.8f" % se_g,
            "%.6e" % two_sided_p(b_g / se_g), str(N_IND)]))

    # ---- 写 PLINK bed（PLINK 1，SNP-major，00=A1 纯合，10=杂合，11=A2 纯合）----
    per_snp = (N_IND + 3) // 4
    buf = bytearray([0x6C, 0x1B, 0x01])
    for s in range(N_SNP):
        row = bytearray(per_snp)
        for i in range(N_IND):
            v = G[s][i]
            code = 0b00 if v == 2 else (0b10 if v == 1 else 0b11)
            row[i // 4] |= code << ((i % 4) * 2)
        buf += row
    with io.open(os.path.join(out_dir, "ref.bed"), "wb") as fh:
        fh.write(bytes(buf))

    wr("ref.bim", "".join("%d\t%s\t0\t%d\t%s\t%s\n"
                          % (CHR, snps[s], BASE_BP + s * 500, A1, A2)
                          for s in range(N_SNP)))
    wr("ref.fam", "".join("FAM1\tIND%04d\t0\t0\t0\t-9\n" % (i + 1)
                          for i in range(N_IND)))
    wr("eqtl_1.esd", "Chr\tSNP\tBp\tA1\tA2\tFreq\tBeta\tse\tp\n"
       + "\n".join(esd_lines) + "\n")
    wr("eqtl.flist",
       "Chr\tProbeID\tGeneticDistance\tProbeBp\tGene\tOrientation\tPathOfEsd\n"
       + "\t".join([str(CHR), PROBE_ID, "0", str(PROBE_BP), GENE, ORI,
                    "eqtl_1.esd"]) + "\n")
    wr("gwas.ma", "SNP\tA1\tA2\tfreq\tb\tse\tp\tn\n"
       + "\n".join(gwas_lines) + "\n")

    b_top, se_top = regress(gt, expr)
    b_gw, se_gw = regress(gt, trait)
    return {
        "top_snp": snps[top],
        "top_z_eqtl": b_top / se_top,
        "top_z_gwas": b_gw / se_gw,
        "expected_b_smr_rough": b_gw / b_top,
    }


def main():
    # 默认输出到临时目录：产物里有 PLINK 二进制 .bed，不该落进技能目录
    # （install.py 会整目录复制，进仓库更不合适）。
    out_dir = (sys.argv[1] if len(sys.argv) > 1
               else os.path.join(tempfile.gettempdir(), "mr-agent-smr-fixture"))
    info = build(out_dir)
    print("fixture 已生成到 %s" % out_dir)
    for f in sorted(os.listdir(out_dir)):
        print("  %-12s %8d bytes" % (f, os.path.getsize(os.path.join(out_dir, f))))
    print("top SNP = %s  b_SMR(粗糙手算) = %.4f"
          % (info["top_snp"], info["expected_b_smr_rough"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
