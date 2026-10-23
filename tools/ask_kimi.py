#!/usr/bin/env python3
"""Consult Kimi (Moonshot AI, OpenAI-compatible chat completions) for a second opinion on anything in the project.

    python3 tools/ask_kimi.py "question" [--file path ...] [--system text] [--model kimi-k3.1-pro] [--json]
    echo "question" | python3 tools/ask_kimi.py -

The key is read from --key-file (default /home/unreal/.sub01-private/kimi-key, else $KIMI_KEY_FILE) and is never
printed or logged. Attached files are inlined as fenced blocks after the question (text only, each capped at
--file-chars). Standard library only (urllib), so it runs on the pod with /usr/bin/python3.
Models seen with the owner's key on 2026-10-23: kimi-k3.1-pro (default), kimi-k3.1-pro-highspeed, kimi-k3, kimi-k2.6,
kimi-k2.7-code, kimi-k2.7-code-highspeed. Base URL https://api.moonshot.ai/v1 (the .cn endpoint refuses this key).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/v1")
DEFAULT_MODEL = "kimi-k3.1-pro"
DEFAULT_KEY_FILE = os.environ.get("KIMI_KEY_FILE", "/home/unreal/.sub01-private/kimi-key")
SYSTEM = ("You are a senior engineer and animation director consulted on SUB-01, a private project: a simulated "
          "20-year-old streamer living in a native Unreal Engine 5 home on a Linux GPU pod, with a Python aiohttp "
          "backend, a Chromium desktop he browses through a Claude-driven agent, a synthesised voice and a local "
          "recording director. Answer precisely, with concrete numbers and code when useful, and say plainly when "
          "something cannot be known from the material given.")


def read_key(path: str) -> str:
    key = Path(path).read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit(f"empty key file {path}")
    return key


def attach(files, cap: int) -> str:
    parts = []
    for name in files:
        p = Path(name)
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > cap:
            text = text[:cap] + f"\n... [truncated at {cap} characters of {len(text)}]"
        parts.append(f"\n\n--- file: {p.name} ---\n```\n{text}\n```")
    return "".join(parts)


def ask(question: str, *, key: str, model: str, system: str, max_tokens: int, temperature: float, timeout: float):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
            "max_tokens": max_tokens}
    if temperature is not None:                     # kimi-k3.1-pro accepts only the default (1): leave it out unless asked
        body["temperature"] = temperature
    req = urllib.request.Request(f"{BASE}/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"kimi http {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SystemExit(f"kimi unreachable: {type(e).__name__}: {e}") from None
    choice = (data.get("choices") or [{}])[0]
    text = ((choice.get("message") or {}).get("content") or "").strip()
    usage = data.get("usage") or {}
    return {"model": data.get("model", model), "answer": text, "finish_reason": choice.get("finish_reason"),
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question", help="the question, or - to read it from stdin")
    p.add_argument("--file", action="append", default=[], help="text file to inline after the question (repeatable)")
    p.add_argument("--file-chars", type=int, default=60000)
    p.add_argument("--system", default=SYSTEM)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--key-file", default=DEFAULT_KEY_FILE)
    p.add_argument("--max-tokens", type=int, default=4000)
    p.add_argument("--temperature", type=float, default=None, help="omitted by default (kimi-k3.1-pro allows only 1)")
    p.add_argument("--timeout", type=float, default=300.0)
    p.add_argument("--json", action="store_true", help="print the full result as JSON instead of the answer")
    args = p.parse_args(argv)
    question = sys.stdin.read() if args.question == "-" else args.question
    question = question.strip() + attach(args.file, args.file_chars)
    result = ask(question, key=read_key(args.key_file), model=args.model, system=args.system,
                 max_tokens=args.max_tokens, temperature=args.temperature, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print(result["answer"])
        print(f"\n[{result['model']} · {result['prompt_tokens']}+{result['completion_tokens']} tokens · {result['seconds']} s]",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
