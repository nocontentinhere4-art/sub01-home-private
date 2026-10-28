#!/usr/bin/env python3
"""Ramp metrics per ABBA leg from the game's PERF windows: resets (render_ms drop >= 1.0 ms between consecutive windows,
or a toggle), and for each complete ramp the slope (ms/min, least squares, first 15 s after a reset skipped) and the
amplitude (mean render_ms of the last 30 s before the next reset minus the first 30 s after this one).
usage: ramps.py NAME LOG"""
import datetime, json, re, statistics, sys
name, LOG = sys.argv[1], sys.argv[2]
O = "/workspace/sub01-w-sawtooth/legs"
legs = [json.loads(l) for l in open(f"{O}/{name}.legs") if '"leg"' in l]
try: TOG = [float(l.split()[0]) for l in open(f"{O}/{name}.toggles") if " toggle " in l]
except OSError: TOG = []
lo, hi = min(l["t0"] for l in legs) - 120, max(l["t1"] for l in legs) + 5
P = []
with open(LOG, "rb") as f:
    f.seek(0, 2); f.seek(max(0, f.tell() - 40_000_000))
    for raw in f:
        if b"SUB01_STREAMER_VISUAL_PERF" not in raw: continue
        l = raw.decode("utf-8", "replace"); m = re.match(r"\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})", l)
        if not m: continue
        g = list(map(int, m.groups())); ts = datetime.datetime(*g[:6], g[6] * 1000, tzinfo=datetime.timezone.utc).timestamp()
        if lo <= ts <= hi:
            kv = dict(re.findall(r"(\w+)=([\d.]+)", l.split("PERF", 1)[1])); P.append((ts, float(kv["render_ms"]), float(kv["ms"])))
def slope(pts):
    if len(pts) < 4: return None
    mx = statistics.mean(p[0] for p in pts); my = statistics.mean(p[1] for p in pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / den * 60 if den else None
for L in legs:
    t0, t1 = L["t0"], L["t1"]
    W = [p for p in P if t0 - 60 <= p[0] <= t1]
    cuts = [W[i][0] for i in range(1, len(W)) if W[i - 1][1] - W[i][1] >= 1.0]
    cuts += [t for t in TOG if t0 - 60 <= t <= t1]
    cuts = sorted(cuts); merged = []
    for c in cuts:
        if merged and c - merged[-1] < 25: merged[-1] = max(merged[-1], c); continue
        merged.append(c)
    sl, amp = [], []
    for a, b in zip(merged, merged[1:]):
        seg = [(ts - a, r) for ts, r, _ in W if a + 15 <= ts <= b - 2]
        s = slope(seg)
        if s is not None: sl.append(s)
        first = [r for ts, r, _ in W if a + 2 <= ts <= a + 32]; last = [r for ts, r, _ in W if b - 32 <= ts <= b - 2]
        if first and last: amp.append(statistics.mean(last) - statistics.mean(first))
    inleg = [c for c in merged if t0 <= c <= t1]
    print(f"leg {L['leg']} {L['arm']} {L['utc0']}-{L['utc1']}: resets/toggles {len(inleg)}, ramps {len(amp)}, "
          f"slope median {statistics.median(sl) if sl else float('nan'):.3f} ms/min, amplitude median "
          f"{statistics.median(amp) if amp else float('nan'):.2f} ms (max {max(amp) if amp else float('nan'):.2f})")
