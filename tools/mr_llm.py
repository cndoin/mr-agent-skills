#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：直接调 MRAgent 用的那套 LLM 接口。

对应上游 `mragent.LLM.llm_chat` / `openai_gpt` / `ollama_chat`。
用途是把 MRAgent 内部的 LLM 调用单独暴露出来 —— 比如想验证某个 key / base_url
通不通，或想拿它做一次生物医学问答，而不必启动整条流水线。

注意：MRAgent 调用时固定 `seed=42`，system prompt 固定为
"You are a helpful biomedical scientist."。本工具保持同样行为。

用法：
  python mr_llm.py --prompt "Is BMI causally related to back pain?"
  python mr_llm.py --prompt "..." --model gpt-4o --base-url https://api.gpt.ge/v1/
  python mr_llm.py --prompt "..." --model-type ollama --model llama3:8b
"""

import argparse
import os
import sys

from _common import parse_args_or_fail, emit, fail, require_mragent

TOOL = "mr-llm"


def main():
    ap = argparse.ArgumentParser(description="LLM 调用（MRAgent 内部接口的原子能力）")
    ap.add_argument("--prompt", required=True, help="提示词")
    ap.add_argument("--model", default="gpt-4o", help="模型名，默认 gpt-4o")
    ap.add_argument("--model-type", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--base-url", default=None, help="OpenAI 兼容平台地址")
    ap.add_argument("--api-key", help="LLM key；不给则取 MRAGENT_AI_KEY / OPENAI_API_KEY")
    args = parse_args_or_fail(ap, TOOL)

    key = args.api_key or os.environ.get("MRAGENT_AI_KEY") or os.environ.get("OPENAI_API_KEY")
    if args.model_type == "openai" and not key:
        fail(TOOL, "缺少 LLM key",
             "设置 MRAGENT_AI_KEY 或 OPENAI_API_KEY；用 --model-type ollama 则不需要",
             exit_code=2)

    _mod, funcs, err = require_mragent(TOOL, ["llm_chat"])
    if err:
        fail(TOOL, err[0], err[1], exit_code=2)

    try:
        out = funcs["llm_chat"](args.prompt, args.model, key, args.base_url, args.model_type)
    except Exception as exc:
        fail(TOOL, "LLM 调用失败: %s: %s" % (type(exc).__name__, exc),
             "检查 key 是否有效、base_url 是否可达、模型名是否被该平台支持")

    emit({"tool": TOOL, "ok": True, "model": args.model,
          "model_type": args.model_type, "base_url": args.base_url,
          "prompt_chars": len(args.prompt), "response": out})


if __name__ == "__main__":
    main()
