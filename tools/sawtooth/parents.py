#!/usr/bin/env python3
"""For one thread and one timer of a full-hierarchy ExportTimingEvents CSV: total time per frame grouped by the
parent chain (up to 4 ancestors).  usage: parents.py EVENTS.csv THREAD TIMER [NFRAMES]"""
import csv, sys, collections
src, th, timer = sys.argv[1], sys.argv[2], sys.argv[3]
nf = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
ev = []
with open(src, newline="") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if len(row) < 5 or row[0] != th: continue
        try: s, e, d = float(row[2]), float(row[3]), int(row[4])
        except ValueError: continue
        if e < 1e17: ev.append((s, d, e, row[1].strip('"')))
ev.sort()
agg = collections.defaultdict(lambda: [0.0, 0]); stack = []
for s, d, e, n in ev:
    while stack and stack[-1][1] <= s: stack.pop()
    if n == timer:
        key = " < ".join(x[0] for x in reversed(stack[-4:]))
        agg[key][0] += e - s; agg[key][1] += 1
    stack.append((n, e))
for k, (t, c) in sorted(agg.items(), key=lambda x: -x[1][0])[:15]:
    print(f"{t / nf * 1e6:9.1f} us/frame  {c / nf:6.2f}/frame  {t / c * 1e6:8.1f} us/call   {k[:160]}")
