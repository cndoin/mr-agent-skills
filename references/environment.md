# 环境搭建

MRAgent 是 **Python 编排 + R 计算** 的双栈结构，两边都得齐。
按下面的顺序做，每步都有验证命令 —— 没验证就别往下走。

## 1. Python：必须是 3.11 或 3.12

**为什么不是 3.13**：`mragent` 锁 `numpy>=1.19.5,<2.0` 和 `pandas>=1.4.2,<2.0`，
这两个版本没有 cp313 预编译 wheel，3.13 上要源码编译（需 gcc + meson），
本机做不到，实测报 `metadata-generation-failed`。

### Windows

```bash
# 建 venv（用 3.12 的解释器；若只有 3.13，先装一个 3.12）
py -3.12 -m venv C:\venvs\mragent
C:\venvs\mragent\Scripts\python.exe -m pip install -U pip
C:\venvs\mragent\Scripts\python.exe -m pip install mragent
```

### Linux / macOS

```bash
python3.12 -m venv ~/venvs/mragent
source ~/venvs/mragent/bin/activate
pip install -U pip
pip install mragent
```

### 验证

```bash
python -c "from mragent import MRAgent, MRAgentOE; print('mragent OK')"
python -c "import numpy, pandas; print(numpy.__version__, pandas.__version__)"
# 期望：numpy 1.x，pandas 1.x。若是 2.x 说明装错了解释器。
```

## 2. R：版本 > 4.3.4，且命令名必须叫 `R`

源码调用的是 `R --slave ... -f test.R`，**不是 `Rscript`**。装完必须确认 `R` 在 PATH 里。

```bash
which R          # Linux/macOS
where R          # Windows
R --version
```

Windows 装完 R 后若 `where R` 找不到，把 `C:\Program Files\R\R-4.x.x\bin` 加进 PATH。

## 3. R 包

### TwoSampleMR（MR 主计算，不在 CRAN）

Windows / macOS 走 MRC IEU 的 r-universe（**推荐，不用编译**）：

```r
install.packages("TwoSampleMR",
                 repos = c("https://mrcieu.r-universe.dev", "https://cloud.r-project.org"))
```

Linux 或要从源码装：

```r
install.packages("remotes")
remotes::install_github("MRCIEU/TwoSampleMR")
```

### 其余包

```r
install.packages(c("ieugwasr", "dplyr", "vcfR", "jsonlite"))
```

### MRlap（仅 `mrlap=True` 时需要，可选）

```r
install.packages("remotes")
remotes::install_github("n-mounier/MRlap")
```

MRlap 还需要两个外部数据文件，从 <https://utexas.box.com/s/vkd36n197m8klbaio3yzoxsee6sxo11v> 下：
`eur_w_ld_chr/`（LD score 目录）和 `w_hm3.noMHC.snplist`（HapMap3 列表）。
注意 `ld` 参数指向**目录**，`hm3` 指向**文件**，别搞反。

### 一次性验证

```bash
R --slave -e 'for (p in c("TwoSampleMR","ieugwasr","dplyr","vcfR","MRlap","jsonlite")) cat(p, requireNamespace(p, quietly=TRUE), "\n")'
```

期望全 `TRUE`（`MRlap` 可以 `FALSE`，只要不用 `mrlap=True`）。

## 4. OpenGWAS token（硬门槛）

1. 打开 <https://api.opengwas.io/> 注册并申请 JWT。
2. 设进环境变量，**不要写进命令行**（会进 shell history）：

```bash
# Linux/macOS
export MRAGENT_GWAS_TOKEN="<你的 JWT>"

# Windows PowerShell
$env:MRAGENT_GWAS_TOKEN = "<你的 JWT>"
```

JWT 有有效期，过期后 step5 之后取数全空或 401。

## 5. LLM 后端

| 方式 | 需要 | 配置 |
| --- | --- | --- |
| OpenAI | `AI_key` | `export MRAGENT_AI_KEY="sk-..."` |
| OpenAI 兼容平台 | `AI_key` + `base_url` | `--base-url https://...` |
| 本地 Ollama | 无 key | `curl -fsSL https://ollama.com/install.sh \| sh` + `pip install ollama`，然后 `--model-type ollama --llm-model <本地模型名>` |

## 6. 跑一次体检

```bash
python scripts/preflight.py --python C:\venvs\mragent\Scripts\python.exe
```

`ready: true` 才开工；有 `blocking` 项就先补环境。

## 三条落地路径（按本机条件选）

### A. 本机直跑（Windows）

需要：装 R（+ 上述 R 包）+ 建 3.12 venv。
**本机当前状态：无 R、无 Docker、WSL 被拦** → 走这条路先得装 R。

### B. 远程 Linux 服务器 / HPC / Colab

用 `--dry-run` 生成配置，把脚本和命令搬过去跑：

```bash
python scripts/run_mr.py --mode O --outcome "back pain" --steps 1,2 --dry-run
```

R 在 Linux 上装 TwoSampleMR 需要编译工具链（`build-essential`、`libcurl4-openssl-dev`、
`libxml2-dev` 等），预留时间。

### C. Docker / GitHub Actions（最省事）

MRC IEU 提供预装镜像：

```bash
docker run -it mrcieu/twosamplemr R
```

GitHub Actions 可用 `r-lib/actions/setup-r` + `actions/setup-python@v5`（python-version: '3.12'）。
适合把 MR 分析做成可复现的流水线。

### D. 只想要个界面

官方 HuggingFace Demo：<https://huggingface.co/spaces/xuwei1997/MRAgent>
（2025-07 更新后支持自填兼容 OpenAI 接口的模型）。不想装环境就用它。
