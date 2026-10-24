#!/usr/bin/env python3
"""Exclusive and inclusive time per frame for every (thread, timer) of a full-hierarchy ExportTimingEvents CSV.
Frames = number of 'Rendering Frames' events that end inside the span (or the span / FRAME_MS when absent).
Writes a JSON {key: [excl_us_per_frame, incl_us_per_frame, count_per_frame]} for excmp.py.
usage: excl.py EVENTS.csv OUT.json"""
import csv, json, sys, collections
src, out = sys.argv[1], sys.argv[2]
ev = collections.defaultdict(list); frames = []
with open(src, newline="") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if len(row) < 5: continue
        try: s, e, d = float(row[2]), float(row[3]), int(row[4])
        except ValueError: continue
        if not e < 1e17: continue
        if row[0] == "Rendering Frames": frames.append((s, e)); continue
        ev[row[0]].append((s, e, d, row[1].strip('"')))
excl = collections.defaultdict(float); incl = collections.defaultdict(float); cnt = collections.Counter()
t0 = min(x[0] for v in ev.values() for x in v); t1 = max(x[1] for v in ev.values() for x in v)
for th, lst in ev.items():
    lst.sort(key=lambda x: (x[0], x[2]))
    stack = []   # (end, key, child_time)
    def pop_until(t):
        while stack and stack[-1][0] <= t:
            end, key, s0, child = stack.pop()
            dur = end - s0
            excl[key] += dur - child; incl[key] += dur; cnt[key] += 1
            if stack: stack[-1][3] += dur
    for s, e, d, n in lst:
        pop_until(s)
        stack.append([e, (th, n), s, 0.0])
    pop_until(1e18)
nf = len([1 for s, e in frames if t0 <= e <= t1]) or 1
print(f"span {t0:.3f}..{t1:.3f} = {t1 - t0:.3f} s, frames {nf}, ms/frame {(t1 - t0) / nf * 1e3:.2f}")
json.dump({"frames": nf, "span": t1 - t0, "rows": {f"{k[0]}|{k[1]}": [excl[k] / nf * 1e6, incl[k] / nf * 1e6, cnt[k] / nf] for k in incl}},
          open(out, "w"))
