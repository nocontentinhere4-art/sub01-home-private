#!/usr/bin/env python3
"""PERF windows with max_ms > LIMIT in each leg of an ABBA run, and the distance to the nearest toggle (a window covers
the 10 s before its timestamp).  usage: hitches.py NAME LOG [LIMIT_MS]"""
import datetime, json, re, sys
name, LOG = sys.argv[1], sys.argv[2]; lim = float(sys.argv[3]) if len(sys.argv) > 3 else 50
O = "/workspace/sub01-w-sawtooth/legs"
legs = [json.loads(l) for l in open(f"{O}/{name}.legs") if '"leg"' in l]
try: TOG = [float(l.split()[0]) for l in open(f"{O}/{name}.toggles") if " toggle " in l]
except OSError: TOG = []
lo, hi = min(l["t0"] for l in legs), max(l["t1"] for l in legs)
with open(LOG, "rb") as f:
    f.seek(0, 2); f.seek(max(0, f.tell() - 40_000_000))
    for raw in f:
        if b"SUB01_STREAMER_VISUAL_PERF" not in raw: continue
        l = raw.decode("utf-8", "replace"); m = re.match(r"\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})", l)
        g = list(map(int, m.groups())); ts = datetime.datetime(*g[:6], g[6] * 1000, tzinfo=datetime.timezone.utc).timestamp()
        if not lo <= ts <= hi: continue
        mx = float(re.search(r"max_ms=([\d.]+)", l).group(1))
        if mx <= lim: continue
        leg = next((L for L in legs if L["t0"] <= ts <= L["t1"]), None)
        near = [t for t in TOG if ts - 13 <= t <= ts + 1]
        print(f"{m.group(4)}:{m.group(5)}:{m.group(6)} leg {leg['leg'] if leg else '-'} {leg['arm'] if leg else '-'} max_ms {mx:6.1f} "
              f"{'toggle-aligned' if near else 'NOT toggle-aligned'}")
