# SMR（Summary-data-based Mendelian Randomization）使用与实现说明

本文档覆盖 `tools/mr_smr.py`。SMR 是 TwoSampleMR 之外的另一套因果推断方法学，
**不是上游 MRAgent 的功能** —— 本技能主动扩展，上游差分依据见
`upstream-diff.md` 第九章。

## 1. 方法学一句话

TwoSampleMR 问的是「表型 A 是否因果影响表型 B」，工具变量是**全基因组独立 SNP**。
SMR 问的是「**某个基因/分子表型的表达量** 是否介导了 SNP 对复杂性状的效应」，
工具变量是**一个 cis-xQTL 区域内多个 LD 连锁的 SNP**，数据形式是 summary statistics
（不需要个体数据）。参考 Zhu et al. 2016, *Nature Genetics* 48:481–487。

- **SMR 检验**：`b_SMR = b_zy / b_zx`（`zy` = SNP→性状，`zx` = SNP→分子表型），
  检验统计量 `T_SMR = (z_zx² · z_zy²) / (z_zx² + z_zy²)`，df = 1 卡方。
  SE 用 delta method。
- **HEIDI 检验**：用区域内的**多个** SNP 各算一个 `b_xy`，检验它们是否来自同一个
  因果变异。`p_HEIDI` 不显著 ⇒ 不能拒绝「单一共享因果变异」（即 SMR 结论可信）；
  `p_HEIDI` 显著 ⇒ 更可能是 LD 连锁造成的假象。

## 2. 输入数据格式

SMR 不接受 OpenGWAS 的 `id`，需要自备三类文件。

### 2.1 参考基因型（LD 面板）

PLINK 1 二进制三件套 `ref.bed` / `ref.bim` / `ref.fam`（1000G 或 UKB）。
SMR 用它们估 LD 与做等位基因频率一致性检查。

### 2.2 GWAS summary（`.ma`，GCTA-COJO 格式）

8 列，**表头会被忽略**：

```
SNP  A1  A2  freq  b  se  p  n
```

### 2.3 分子 QTL summary（二选一）

**(a) `.esd` 文本**（9 列，**带表头**）—— 每个 probe 一个文件：

```
Chr  SNP  Bp  A1  A2  Freq  Beta  se  p
```

**(b) `.flist` 清单**（7 列，带表头）—— 指向上面那些 `.esd`：

```
Chr  ProbeID  GeneticDistance  ProbeBp  Gene  Orientation  PathOfEsd
```

> ⚠️ **官方按 CWD 解析 `PathOfEsd` 里的相对路径**，也按 CWD 写 `--out`。
> 从别的工作目录调用时，官方会报
> `Error: can not open the file [xxx.esd] to read.`，
> **但仍然返回 exit code 0**（假成功）。
> `mr_smr.py` 的做法是：在 `.flist` 所在目录执行，并绝对化输出路径；
> 同时从日志里提取 `Error:` 行纳入成功判定 —— 双保险。

**(c) `.besd` 二进制**（官方 BESD）：`<prefix>.besd` + `.esi`（SNP 信息）+ `.epi`（probe 信息）。
体积极小（只存 b 和 se，p 由 b/se 反算），是官方推荐的正式存储方式。
用 `make-besd` 从 (a)/(b) 生成，用 `dump-besd` 反解回文本。

## 3. 两条执行路径

### `--engine official` —— 官方 `smr` 二进制（功能最全）

Yang lab（西湖大学）的命令行工具，`smr` 二进制**自报 MIT License**
（源码仓库 `JianYang-Lab/SMR` 标 GPL-2.0；本技能只分发/调用官方预编译二进制，
不 vendor 源码）。

```bash
python tools/mr_smr.py fetch-binary      # 按平台自动下载到 ~/.cache/mr-agent/tools/smr
# 或手动下载后： export SMR_BIN=/path/to/smr
#
# 注意：fetch-binary 不接受任何参数，固定解压到上面的全局缓存。
# 要指定已有二进制只能用 SMR_BIN，没有 --out。
python tools/mr_smr.py analyze --engine official \
    --bfile ref --gwas gwas.ma --beqtl eqtl --out result
```

平台差异（官方现状，不是本技能的遗漏）：Windows 只发到 **1.3.1**，
Linux / macOS 已到 **1.4.3**。

下载请求会显式携带浏览器 UA：官方下载站的 WAF 对 urllib 的默认 UA
直接回 `HTTP 403`（详见 §8 第 7 条）。这是本技能实测出来并修掉的缺陷 ——
原先 `download_binary()` 用裸 `urlopen()`，导致 `fetch-binary` 必然失败。

### `--engine native` —— 纯标准库实现（零外部依赖）

```bash
python tools/mr_smr.py analyze --engine native \
    --bfile ref --gwas gwas.ma --flist eqtl.flist --out result
```

- **SMR 检验与官方逐位一致**（自检 J10 对官方金标准断言，
  见下方 §5 的实测数字）。
- **HEIDI 为独立实现**：`nsnp_HEIDI`（入选 SNP 数）与官方一致，
  但 `p_HEIDI` 小数位有差异 —— 官方未公开其 HEIDI 的精确方差构造，
  本技能穷举了 24+ 种组合仍无法精确反推（最接近的构造差 0.13）。
  **需要与已发表数字严格对齐时，用 `--engine official`。**
  自检只对 `nsnp_HEIDI` 做精确断言，不对 `p_HEIDI` 做精确断言 —— 不假装一致。

## 4. 子命令

| 子命令 | 作用 | 是否需要官方二进制 |
| --- | --- | --- |
| `preflight` | 探测官方二进制与输入文件 | 否 |
| `fetch-binary` | 按平台下载官方 `smr` 到全局缓存 | 否 |
| `make-besd` | 文本（`.flist` / `.esd` / Matrix eQTL / FastQTL / PLINK / GEMMA / BOLT-LMM）→ BESD | **是** |
| `ld` | 从 PLINK bfile 纯标准库算 LD（r / r²） | 否 |
| `dump-besd` | BESD → 文本；`--to-esd` 再拆成 `.esd` + `.flist` 供 native 引擎消费 | **是** |
| `analyze` | 跑 SMR (+HEIDI)，`--engine auto\|official\|native` | 看引擎 |
| `official` | **把参数原样透传给官方 `smr`** —— 官方功能全覆盖的兜底入口 | **是** |

### `dump-besd` 的 `--query` 语义（易错点）

官方 `--query` 是「按 eQTL **p 值阈值**导出子集」，**不是「取前 N 条」**。
默认 `5.0e-8`；取 `--query 1` 才是全量导出。
早期实现写成 `default=5`，官方直接报
`Error: --query should be within the range from 0 to 1.`。
本工具默认 `1.0`（全量），自检 J8 对此有回归保护。

## 5. 实测校准（官方 vs native）

数据集：`tests/gen_smr_fixture.py` 确定性生成（种子 `20261001`，
500 个体 × 20 SNP，前 10 个 SNP 共享 LD 块，已知因果链
「SNP → 表达（0.60）→ 性状（0.50）」）。金标准由官方 smr 1.3.1 产出。

| 量 | 官方 1.3.1 | native | 一致？ |
| --- | --- | --- | --- |
| `topSNP` | `rs1008` | `rs1000` | 数值等价（两者完全共线，r²=1.0，b/se 完全相同；平局取谁不同） |
| `b_SMR` | `0.56559` | `0.5655897295` | ✅ 约 6 位有效数字 |
| `se_SMR` | `0.130691` | `0.1306912898` | ✅ 约 6 位有效数字 |
| `p_SMR` | `1.506901e-05` | `1.50690025e-05` | ✅ |
| `nsnp_HEIDI` | `6` | `6` | ✅ 精确一致 |
| `p_HEIDI` | `0.8045132` | `0.916231` | ❌ **已知差异**，见 §3 |

`b/se/p` 的微小差异来自 `.esd` 文本只写 8 位小数，而 BESD 内部精度更高 ——
native 读文本，官方读 BESD。若两边都读同一份文本，差异会进一步缩小。

复现：

```bash
python tests/gen_smr_fixture.py /tmp/fix
python tools/mr_smr.py make-besd --flist /tmp/fix/eqtl.flist --out /tmp/fix/eqtl
python tools/mr_smr.py analyze --engine official --bfile /tmp/fix/ref \
    --gwas /tmp/fix/gwas.ma --beqtl /tmp/fix/eqtl --out /tmp/fix/off
python tools/mr_smr.py analyze --engine native --bfile /tmp/fix/ref \
    --gwas /tmp/fix/gwas.ma --flist /tmp/fix/eqtl.flist --out /tmp/fix/nat
```

## 6. 参数映射（`analyze`）

本工具对部分 flag 用了更短的名字；其余同名。**未在下表列出的官方 flag，
用 `--raw "..."` 或 `official` 子命令原样透传**，因此官方功能不会被包装层截断。
自检 J5/J6/J7 保证这张表与解析器不会漂移。

| 本技能 flag | 官方 flag |
| --- | --- |
| `--peqtl-smr` | `--peqtl-smr` |
| `--peqtl-heidi` | `--peqtl-heidi` |
| `--cis-wind` | `--cis-wind` |
| `--smr-wind` | `--smr-wind` |
| `--ld-upper` | `--ld-upper-limit` |
| `--ld-lower` | `--ld-lower-limit` |
| `--heidi-min-m` | `--heidi-min-m` |
| `--heidi-max-m` | `--heidi-max-m` |
| `--heidi-mtd` | `--heidi-mtd` |
| `--phet` | `--phet` |
| `--peqtl-trans` | `--peqtl-trans` |
| `--trans-wind` | `--trans-wind` |
| `--set-list` | `--set-list` |
| `--set-wind` | `--set-wind` |
| `--extract-exposure-probe` | `--extract-exposure-probe` |
| `--extract-outcome-probe` | `--extract-outcome-probe` |
| `--exclude-exposure-probe` | `--exclude-exposure-probe` |
| `--exclude-outcome-probe` | `--exclude-outcome-probe` |
| `--extract-single-exposure-probe` | `--extract-single-exposure-probe` |
| `--extract-single-outcome-probe` | `--extract-single-outcome-probe` |
| `--extract-snp` | `--extract-snp` |
| `--exclude-snp` | `--exclude-snp` |
| `--extract-probe` | `--extract-probe` |
| `--exclude-probe` | `--exclude-probe` |
| `--extract-snp-probe` | `--extract-snp-probe` |
| `--extract-target-snp-probe` | `--extract-target-snp-probe` |
| `--genes` | `--genes` |
| `--target-snp` | `--target-snp` |
| `--smr-file` | `--smr-file` |
| `--maf` | `--maf` |
| `--diff-freq` | `--diff-freq` |
| `--diff-freq-prop` | `--diff-freq-prop` |
| `--nmecs` | `--nmecs` |
| `--psmr` | `--psmr` |
| `--gene-list` | `--gene-list` |
| `--probe-wind` | `--probe-wind` |
| `--heidi-off` | `--heidi-off` |
| `--trans` | `--trans` |
| `--smr-multi` | `--smr-multi` |
| `--ld-multi-snp` | `--ld-multi-snp` |
| `--mecs` | `--mecs` |
| `--pmecs` | `--pmecs` |
| `--mmecs` | `--mmecs` |
| `--meta` | `--meta` |
| `--plot` | `--plot` |
| `--disable-freq-ck` | `--disable-freq-ck` |
| `--describe-cis` | `--descriptive-cis` |
| `--describe-trans` | `--descriptive-trans` |

共 48 条。此外 `analyze` 自带 `--bfile` / `--gwas` / `--beqtl`（**给两次即
双分子性状 / omics / two-sample SMR**）/ `--out` / `--thread-num`，以及
`--esd` / `--flist`（native 专用）与 `--raw`（万能透传）。

## 7. 官方默认参数

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--peqtl-smr` | `5e-8` | 入选 SMR 的 cis-eQTL 显著性阈值 |
| `--peqtl-heidi` | `1.57e-3` | 参与 HEIDI 的 SNP 的 eQTL 阈值（比 SMR 宽松，为的是拿到足够多 SNP） |
| `--ld-upper-limit` | `0.9` | HEIDI 修剪时 LD r² 上限 |
| `--ld-lower-limit` | `0.05` | HEIDI 修剪时 LD r² 下限 |
| `--heidi-min-m` | `3` | HEIDI 最少需要几个 SNP |
| `--heidi-max-m` | `20` | HEIDI 最多用几个 SNP |
| `--cis-wind` | `2000` | cis 窗口（Kb，双侧） |
| `--heidi-mtd` | `1` | HEIDI 方法：0 = 原始，1 = 改进版 |

## 8. 常见坑

1. **官方 exit 0 不等于成功。** 官方把错误写在日志里（`Error: ...`），
   returncode 仍是 0。判成败必须同时看日志与产物是否真的生成。
2. **`.flist` 的相对路径按 CWD 解析。** 换工作目录就全线失败（见 §2.3）。
3. **`--query` 是 p 值阈值不是条数。** 见 §4。
4. **`--make-besd` 默认是稀疏格式。** 只存 cis ±2Mb、trans ±1Mb、
   以及 p < 1e-5 的 SNP；要全量得加 `--make-besd-dense`（文件会非常大）。
5. **`.ma` 文件表头会被忽略**，靠列位置解析；列顺序错了不会报错，
   只会算出荒谬的数。
6. **等位基因方向。** eQTL、GWAS、LD panel 三方的 A1 必须对齐；
   官方有频率一致性检查（`--disable-freq-ck` 可关，但不建议）。
7. **下载官方二进制必须带浏览器 UA。** 官方下载站的 WAF 直接拒绝 urllib 的
   默认 UA（`Python-urllib/3.x`）并返回 `HTTP 403 Forbidden`；同一个 URL、
   同一个 shell，只把 UA 换成浏览器 UA 就立刻 `200`（实测 2171140 字节）。
   `download_request()` 已内置 UA，自检 J14 离线断言请求头、J15 发 1 字节
   Range 请求确认服务端真的放行。**这类 403 极易被误判成“网络不通”或“代理问题”，
   于是去找网络而不是改请求头。** 自己写脚本拉这个包时注意同样的坑。
