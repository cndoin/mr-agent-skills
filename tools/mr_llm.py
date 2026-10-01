#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
原子工具：LLM 调用（原生实现，不依赖 mragent）。

对应上游 `mragent.LLM.llm_chat` / `openai_gpt` / `ollama_chat`。
用途是把 MRAgent 内部的 LLM 调用单独暴露出来 —— 验证 key / base_url 通不通、
或做一次生物医学问答，都不必启动整条流水线。

**为什么不用上游实现**：上游 `LLM.py` 依赖 `openai` 与 `ollama` 两个第三方包，
而它们只在 3.11/3.12 的 mragent 环境里才装好。这里用标准库直接发同样的请求，
于是在**没装 mragent 的机器上也能用**。

与上游保持一致的细节：
  * system prompt 固定 "You are a helpful biomedical scientist."
  * OpenAI 分支固定传 `seed=42`（可读性差但可复现性一致）
  * 默认模型 `gpt-4o`（上游 `openai_gpt` 的默认是 `gpt-4-1106-preview`，
    但 `MRAgent` 类实际调用时都会显式传 `gpt-4o`，本工具跟随后者）

用法：
  python mr_llm.py --prompt "Is BMI causally related to back pain?"
  python mr_llm.py --prompt "..." --model gpt-4o --base-url https://api.gpt.ge/v1/
  python mr_llm.py --prompt "..." --model-type ollama --model llama3:8b
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from _common import parse_args_or_fail, emit, fail

TOOL = "mr-llm"
SYSTEM_PROMPT = "You are a helpful biomedical scientist."
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
TIMEOUT = 300


def post_json(url, payload, headers, timeout=TIMEOUT):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def openai_chat(text, key, model, base_url=None):
    """OpenAI 兼容的 /chat/completions。"""
    base = (base_url or DEFAULT_OPENAI_BASE).rstrip("/")
    body = post_json(
        base + "/chat/completions",
        {"model": model, "seed": 42,
         "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": text}]},
        {"Content-Type": "application/json",
         "Authorization": "Bearer %s" % key})
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("响应里没有 choices[0].message.content；"
                         "返回体前 200 字符: %s" % json.dumps(body)[:200])


def ollama_chat(text, model, host=None):
    """Ollama /api/chat。"""
    base = (host or os.environ.get("OLLAMA_HOST") or DEFAULT_OLLAMA_HOST).rstrip("/")
    if not base.startswith("http"):
        base = "http://" + base
    body = post_json(
        base + "/api/chat",
        {"model": model, "stream": False,
         "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": text}]},
        {"Content-Type": "application/json"})
    try:
        return body["message"]["content"]
    except (KeyError, TypeError):
        raise ValueError("响应里没有 message.content；"
                         "返回体前 200 字符: %s" % json.dumps(body)[:200])


def main():
    ap = argparse.ArgumentParser(
        description="LLM 调用（MRAgent 内部接口的原子能力，原生实现，无需 mragent）")
    ap.add_argument("--prompt", required=True, help="提示词")
    ap.add_argument("--model", default="gpt-4o", help="模型名，默认 gpt-4o")
    ap.add_argument("--model-type", default="openai", choices=["openai", "ollama"])
    ap.add_argument("--base-url", default=None,
                    help="OpenAI 兼容平台地址（默认 https://api.openai.com/v1）")
    ap.add_argument("--api-key", help="LLM key；不给则取 MRAGENT_AI_KEY / OPENAI_API_KEY")
    args = parse_args_or_fail(ap, TOOL)

    key = (args.api_key or os.environ.get("MRAGENT_AI_KEY")
           or os.environ.get("OPENAI_API_KEY"))
    if args.model_type == "openai" and not key:
        fail(TOOL, "缺少 LLM key",
             "设置 MRAGENT_AI_KEY 或 OPENAI_API_KEY；用 --model-type ollama 则不需要",
             exit_code=2)

    try:
        if args.model_type == "openai":
            out = openai_chat(args.prompt, key, args.model, args.base_url)
        else:
            out = ollama_chat(args.prompt, args.model, args.base_url)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        fail(TOOL, "LLM 返回 HTTP %s" % exc.code, detail or
             "检查 key 是否有效、base_url 是否正确、模型名是否被该平台支持")
    except urllib.error.URLError as exc:
        fail(TOOL, "无法连接 LLM 服务: %s" % exc.reason,
             "ollama 请确认本地已启动（默认 http://localhost:11434）；"
             "OpenAI 兼容平台请检查 --base-url 与网络")
    except OSError as exc:
        # 传输层直接断掉：连接重置 / 对端强制关闭 / 超时 / DNS 失败。
        # 这些同样是「连不上」，但 OSError 不是 URLError，会漏到下面的兜底分支，
        # 只剩一句原始异常名（既无可执行建议，调用方也无法按连接失败统一处理）。
        # 注意分支顺序：HTTPError ⊂ URLError ⊂ OSError，必须由具体到宽泛。
        fail(TOOL, "无法连接 LLM 服务: %s: %s" % (type(exc).__name__, exc),
             "连接在传输层被中断（连接重置 / 对端关闭 / 超时 / DNS 失败）。"
             "检查 --base-url、网络与代理设置；ollama 请确认本地已启动"
             "（默认 http://localhost:11434）")
    except ValueError as exc:
        fail(TOOL, str(exc), "平台返回的结构不是标准 OpenAI 格式")
    except Exception as exc:
        fail(TOOL, "%s: %s" % (type(exc).__name__, exc))

    emit({"tool": TOOL, "ok": True, "model": args.model,
          "model_type": args.model_type, "base_url": args.base_url,
          "prompt_chars": len(args.prompt),
          "response_chars": len(out or ""), "response": out})


if __name__ == "__main__":
    main()
