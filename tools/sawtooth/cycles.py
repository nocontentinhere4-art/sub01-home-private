#!/usr/bin/env python3
"""Sawtooth cycles from the game log: detect resets (render_ms drop >= 1.5 ms between consecutive PERF lines, from
>= 16.5 ms) and print, per cycle, its wall duration, the number of frames rendered in it (sum of the PERF 'frames='
counts), the mean fps, and render_ms at start and end.  A reset tied to a fixed number of frames (or of X11 requests
per frame) shows a constant frame count while the duration varies with fps.
usage: cycles.py LOG [MIN_DROP_MS] [MIN_FROM_MS]"""
import re, sys, datetime
TS = re.compile(rb"^\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]")
drop = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
frm = float(sys.argv[3]) if len(sys.argv) > 3 else 16.5
perf = []
with open(sys.argv[1], "rb") as f:
    for raw in f:
        if b"SUB01_STREAMER_VISUAL_PERF" not in raw: continue
        m = TS.match(raw)
        if not m: continue
        y, mo, d, h, mi, s, ms = (int(x) for x in m.groups())
        t = datetime.datetime(y, mo, d, h, mi, s, ms * 1000)
        g = dict(re.findall(rb"(\w+)=([\d.]+)", raw))
        perf.append((t, float(g[b"render_ms"]), float(g[b"fps"]), int(float(g[b"frames"])), float(g.get(b"window_s", 10))))
cuts = [i for i in range(1, len(perf)) if perf[i - 1][1] - perf[i][1] >= drop and perf[i - 1][1] >= frm]
# merge resets split across two adjacent windows
merged = []
for i in cuts:
    if merged and i - merged[-1] <= 2: merged[-1] = i; continue
    merged.append(i)
print(f"{'cycle start':19s} {'dur s':>6} {'frames':>7} {'fps':>5} {'r0':>6} {'r1':>6}")
for a, b in zip(merged, merged[1:]):
    seg = perf[a:b]
    if (seg[-1][0] - seg[0][0]).total_seconds() > 1200 or any((y[0] - x[0]).total_seconds() > 30 for x, y in zip(seg, seg[1:])):
        continue
    dur = (perf[b][0] - perf[a][0]).total_seconds()
    fr = sum(x[3] for x in seg)
    print(f"{seg[0][0]:%m-%d %H:%M:%S}    {dur:6.0f} {fr:7d} {fr / dur:5.1f} {seg[0][1]:6.2f} {seg[-1][1]:6.2f}")
