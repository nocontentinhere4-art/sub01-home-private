#!/usr/bin/env python3
"""Owner 10-31 "solo roast continuo da parte di sub-01": SUB-01 roasts his guest non-stop for a bounded time.

Every few seconds, when the voice is idle, one new roast line is written by Claude Haiku from the guest's known
on-air facts and his latest line, then spoken by SUB-01 (POST /speak, tag "direct"). Playful only: no race,
nationality, sexuality, body or family. Stops after --minutes or when <streamer-dir>/roast-off exists."""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

MODEL = "claude-haiku-5-5"
FACTS = [
    "started as a Fortnite kid", "his whole fame is one TRUMP memecoin trade of about forty million",
    "pinned X post is a photo next to his Urus in a field, and he said he got lost for an hour on that drive",
    "54.5K followers on pump.fun and follows zero people", "a 13 million dollar pump.fun portfolio",
    "told SUB-01 to wait before launching BOOKI", "has not made a single trade on this stream",
    "keeps saying 'bro' and 'chat'", "did a day-in-the-life video on Orangie's channel",
    "his X bio is just @pumpfun and his location says 'project kimchi'", "dressed for Halloween as himself",
]
SYSTEM = ("You write ONE spoken roast line for SUB-01, an AI streamer, aimed at his guest Kimchi, a memecoin trader, "
          "live on stream. Savage but playful, like two friends on a stream: punchlines about his trading, his flexes, "
          "his car, his Fortnite past, his larp energy, his advice, his outfit, his fans. Never about race, "
          "nationality, sexuality, body, family or anything hateful; no slurs. Swearing is fine (fuck, shit). "
          "15 to 35 words, one or two sentences, no emojis, no stage directions, no quotes, never start with 'Ha'. "
          "Never give financial advice or promise gains.")


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "roast:", msg, file=sys.stderr, flush=True)


def http(method, url, body=None, token=None, timeout=8):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"X-Admin-Token": token} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def last_lines(timeline, n=8):
    try:
        rows = [json.loads(line) for line in Path(timeline).read_text().splitlines()[-n:]]
    except (OSError, ValueError):
        return []
    return [("Kimchi" if str(r.get("tag", "")).startswith("guest:") else "SUB-01", r.get("text", "")) for r in rows]


def clean(line):
    line = re.sub(r"[*_\"“”]", "", line).strip()
    line = re.sub(r"^(ha+[,!. ]+)+", "", line, flags=re.I).strip()
    return line[:400]


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--streamer-dir", required=True)
    p.add_argument("--token-file", required=True)
    p.add_argument("--key-file", required=True)
    p.add_argument("--voice-url", default="http://127.0.0.1:8835")
    p.add_argument("--minutes", type=float, default=30)
    p.add_argument("--gap", type=float, default=4.0, help="silence before the next roast")
    a = p.parse_args()
    import anthropic
    token = Path(a.token_file).read_text().strip()
    client = anthropic.Anthropic(api_key=Path(a.key_file).read_text().strip(), timeout=25.0, max_retries=1)
    sdir = Path(a.streamer_dir)
    end, said, quiet_since = time.monotonic() + a.minutes * 60, [], None
    log(f"on for {a.minutes:.0f} min")
    while time.monotonic() < end and not (sdir / "roast-off").exists():
        try:
            st = http("GET", a.voice_url + "/state", token=token)
            if st.get("speaking") or st.get("queue"):
                quiet_since = None
                time.sleep(0.5)
                continue
            quiet_since = quiet_since or time.monotonic()
            if time.monotonic() - quiet_since < a.gap:
                time.sleep(0.5)
                continue
            convo = "\n".join(f"{w}: {t}" for w, t in last_lines(sdir / "speech" / "timeline.jsonl"))
            user = (f"Facts about Kimchi you can use: {'; '.join(FACTS)}.\n\nLast lines on stream:\n{convo}\n\n"
                    f"Roasts SUB-01 already said (do not repeat their jokes or openings):\n" + "\n".join(said[-10:]) +
                    "\n\nIf Kimchi just said something, hit back at that first. Write the next roast line.")
            msg = client.messages.create(model=MODEL, max_tokens=300, system=SYSTEM, thinking={"type": "disabled"},
                                         messages=[{"role": "user", "content": user}])
            line = clean("".join(getattr(b, "text", "") for b in msg.content))
            if not line:
                continue
            http("POST", a.voice_url + "/speak", {"text": line, "priority": "high", "tag": "direct"}, token=token)
            said.append(line)
            quiet_since = None
            log(f"line ({len(line)} chars)")
            time.sleep(1.5)
        except Exception as exc:                      # keep going; one bad call never ends the bit
            log(f"step failed: {type(exc).__name__}: {exc}")
            time.sleep(3)
    log("off")


if __name__ == "__main__":
    main()
