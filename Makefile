# mr-agent —— 常用命令入口
#
# 刻意不依赖任何构建系统，只用 make 做命令索引；没有 make 时照抄命令行即可。
# Python 解释器可用 PY 覆盖：make test PY=python3.12

PY ?= python

.DEFAULT_GOAL := help
.PHONY: help test test-quick install install-claude install-wb smoke clean

help:  ## 显示本帮助
	@echo "mr-agent —— 可用目标："
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- 测试
test:  ## 全量自检（110 条用例，含真实网络探测）
	$(PY) scripts/selftest.py

test-quick:  ## 快速自检（跳过网络探测，离线也能跑完）
	$(PY) scripts/selftest.py --quick

preflight:  ## 环境预检（本机能不能真跑 MR，看这个）
	$(PY) scripts/preflight.py

# ---------------------------------------------------------------- 安装
install:  ## 装到所有 Agent（Claude Code / WorkBuddy / CodeBuddy / Codex / DeepSeek Harness）
	$(PY) install.py --target all

install-claude:  ## 只装 Claude Code
	$(PY) install.py --target claude

install-wb:  ## 只装 WorkBuddy
	$(PY) install.py --target workbuddy

install-list:  ## 只看会被装到哪，不装
	$(PY) install.py --list

# ---------------------------------------------------------------- 数据
fetch-data:  ## 下载离线 GWAS 清单到 ~/.cache/mr-agent/ （仓库不分发它）
	cd tools && $(PY) mr_gwas.py --fetch

# ---------------------------------------------------------------- 冒烟
smoke:  ## 装完后冒烟：预检 + 离线检索
	$(PY) install.py --target all --no-fetch

# ---------------------------------------------------------------- 清理
clean:  ## 删掉编译缓存与运行产物
	$(PY) -c "import pathlib,shutil;[shutil.rmtree(p,ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PY) -c "import pathlib;[p.unlink() for p in pathlib.Path('.').rglob('*.log') if p.name=='run.log']"
