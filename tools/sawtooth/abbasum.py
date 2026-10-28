#!/usr/bin/env python3
"""Summarise an abba2.py run per leg: medians of the game's 10 s PERF windows (frame ms, fps, render, RHI, GPU),
p95 of the window frame ms, worst max_ms, cam2 fps; the sawtooth seen in the RHI thread's user ms per frame (resets =
drops >= 2 ms) and in render_ms (slope per minute by least squares inside each ramp, start-to-end delta = mean of the
first 60 s after a reset vs the last 60 s before the next); cgroup throttling; GPU clocks/power/utilisation.
usage: abbasum.py NAME [LOG]"""
import csv, datetime, json, os, re, statistics, sys
name = sys.argv[1]; LOG = sys.argv[2] if len(sys.argv) > 2 else "/tmp/sub01-share/game.log"
O = "/workspace/sub01-w-sawtooth/legs"
legs = [json.loads(l) for l in open(f"{O}/{name}.legs") if '"leg"' in l]
t_lo = min(l["t0"] for l in legs) - 120; t_hi = max(l["t1"] for l in legs) + 5
perf, cam = [], []
with open(LOG, "rb") as f:
    f.seek(max(0, os.path.getsize(LOG) - 40_000_000))
    for raw in f:
        if b"SUB01_STREAMER_VISUAL_PERF" not in raw and b"SUB01_STREAMER_VISUAL_CAM2 fps" not in raw: continue
        l = raw.decode("utf-8", "replace")
        m = re.match(r"\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})", l)
        if not m: continue
        g = list(map(int, m.groups()))
        ts = datetime.datetime(*g[:6], g[6] * 1000, tzinfo=datetime.timezone.utc).timestamp()
        if not t_lo <= ts <= t_hi: continue
        kv = dict((k, float(v)) for k, v in re.findall(r"(\w+)=([-\d.]+)", l.split("SUB01_STREAMER_VISUAL_", 1)[1]))
        (perf if "PERF" in l else cam).append((ts, kv))
rhi = []
for l in open(f"{O}/{name}-rhi.jsonl"):
    r = json.loads(l); fps = r["fps_render"][0]
    v = [x for k, x in r["d"].items() if k.startswith("RHIThread")]
    if fps and v:
        hh, mm, ss = map(int, r["utc"].split(":"))
        day = datetime.datetime.fromtimestamp(legs[0]["t0"], datetime.timezone.utc)
        ts = day.replace(hour=hh, minute=mm, second=ss).timestamp()
        rhi.append((ts, v[0][0] / fps, fps))
samp = [json.loads(l) for l in open(f"{O}/{name}.jsonl")]
TOG = []
try: TOG = [float(l.split()[0]) for l in open(f"{O}/{name}.toggles") if " toggle " in l]
except OSError: pass
smi = []
try:
    for row in csv.reader(open(f"{O}/{name}-smi.csv")):
        try:
            ts = datetime.datetime.strptime(row[0].strip(), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=datetime.timezone.utc).timestamp()
            smi.append((ts, float(row[1].split()[0]), float(row[3].split()[0]), float(row[4].split()[0]), float(row[5]), float(row[6].split()[0])))
        except (ValueError, IndexError): pass
except OSError: pass
def pct(xs, q):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else float("nan")
def slope(pts):   # least squares ms per minute
    if len(pts) < 4: return float("nan")
    mx = statistics.mean(p[0] for p in pts); my = statistics.mean(p[1] for p in pts)
    den = sum((p[0] - mx) ** 2 for p in pts)
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / den * 60 if den else float("nan")
print(f"{'leg':>3} {'arm':>3} {'utc':>17} {'n':>3} {'ms50':>6} {'ms95':>6} {'max':>6} {'fps':>5} {'rend':>6} {'rhi':>5} {'gpu':>5} {'cam2':>5} | "
      f"{'resets':>6} {'RHIusr0':>7} {'RHIusr1':>7} {'rd0':>6} {'rd1':>6} {'slope/min':>9} | {'thr':>4} {'gpuMHz':>6} {'W':>5} {'util':>4} | {'h50':>3} {'fps5':>5} {'tog':>3}")
res = []
for L in legs:
    t0, t1 = L["t0"], L["t1"]
    P = [kv for ts, kv in perf if t0 + 10 <= ts <= t1]
    C = [kv for ts, kv in cam if t0 + 10 <= ts <= t1]
    R = [(ts, u) for ts, u, f in rhi if t0 <= ts <= t1]
    resets = [R[i][0] for i in range(1, len(R)) if R[i - 1][1] - R[i][1] >= 2.0]
    edges = [t0] + resets + [t1]
    rd = [(ts, kv["render_ms"]) for ts, kv in perf if t0 + 10 <= ts <= t1]
    slopes, d0, d1, u0, u1 = [], [], [], [], []
    for a, b in zip(edges, edges[1:]):
        seg = [(ts - a, v) for ts, v in rd if a + 15 <= ts <= b - 5]
        if b - a >= 240: slopes.append(slope(seg))
        if a in resets and b in resets:   # a complete ramp
            d0 += [v for ts, v in rd if a + 10 <= ts <= a + 70]; d1 += [v for ts, v in rd if b - 65 <= ts <= b - 5]
            u0 += [u for ts, u in R if a + 5 <= ts <= a + 65]; u1 += [u for ts, u in R if b - 65 <= ts <= b - 5]
    S = [s for s in samp if t0 <= s["t"] <= t1]
    G = [g for g in smi if t0 <= g[0] <= t1]
    r = {"leg": L["leg"], "arm": L["arm"], "n": len(P), "ms50": statistics.median(k["ms"] for k in P) if P else None,
         "ms95": pct([k["ms"] for k in P], .95), "max": max((k["max_ms"] for k in P), default=None),
         "fps": statistics.median(k["fps"] for k in P) if P else None, "render": statistics.median(k["render_ms"] for k in P) if P else None,
         "rhi": statistics.median(k["rhi_ms"] for k in P) if P else None, "gpu": statistics.median(k["gpu_ms"] for k in P) if P else None,
         "cam2": statistics.median(k["fps"] for k in C) if C else None, "resets": len(resets),
         "rhiusr0": statistics.mean(u0) if u0 else None, "rhiusr1": statistics.mean(u1) if u1 else None,
         "rd0": statistics.mean(d0) if d0 else None, "rd1": statistics.mean(d1) if d1 else None,
         "slope": statistics.median(slopes) if slopes else None, "thr": sum(s["cg"]["throttled_periods"] for s in S),
         "mhz": statistics.mean(g[1] for g in G) if G else None, "w": statistics.mean(g[3] for g in G) if G else None,
         "util": statistics.mean(g[5] for g in G) if G else None,
         "hitch50": sum(1 for k in P if k["max_ms"] > 50), "fps_p5": pct([k["fps"] for k in P], .05),
         "toggles": sum(1 for l in TOG if t0 <= l <= t1)}
    res.append(r)
    f = lambda x, w=6, p=2: f"{x:{w}.{p}f}" if isinstance(x, (int, float)) and x == x else " " * (w - 1) + "-"
    print(f"{r['leg']:3d} {r['arm']:>3} {L['utc0']}-{L['utc1'][:5]} {r['n']:3d} {f(r['ms50'])} {f(r['ms95'])} {f(r['max'],6,1)} {f(r['fps'],5,1)} "
          f"{f(r['render'])} {f(r['rhi'],5)} {f(r['gpu'],5)} {f(r['cam2'],5,1)} | {r['resets']:6d} {f(r['rhiusr0'],7)} {f(r['rhiusr1'],7)} "
          f"{f(r['rd0'])} {f(r['rd1'])} {f(r['slope'],9,3)} | {r['thr']:4d} {f(r['mhz'],6,0)} {f(r['w'],5,1)} {f(r['util'],4,0)} | "
          f"{r['hitch50']:3d} {f(r['fps_p5'],5,1)} {r['toggles']:3d}")
A = [r for r in res if r["arm"] == "A" and r["ms50"]]; B = [r for r in res if r["arm"] == "B" and r["ms50"]]
if A and B:
    print(f"A median of leg medians: {statistics.median(r['ms50'] for r in A):.2f} ms   B: {statistics.median(r['ms50'] for r in B):.2f} ms   "
          f"B-A {statistics.median(r['ms50'] for r in B) - statistics.median(r['ms50'] for r in A):+.2f} ms")
json.dump(res, open(f"{O}/{name}.sum.json", "w"), indent=1)
