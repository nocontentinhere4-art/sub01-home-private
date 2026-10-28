#!/usr/bin/env python3
"""Compare two excl.py JSONs: per thread|timer, exclusive us per frame (A, B, delta), inclusive, calls per frame.
usage: excmp.py A.json B.json [TOP] [THREAD_SUBSTR]"""
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
top = int(sys.argv[3]) if len(sys.argv) > 3 else 40; thf = sys.argv[4] if len(sys.argv) > 4 else ""
print(f"A: {a['frames']} frames {a['span'] / a['frames'] * 1e3:.2f} ms/frame   B: {b['frames']} frames {b['span'] / b['frames'] * 1e3:.2f} ms/frame")
rows = []
for k in set(a["rows"]) | set(b["rows"]):
    if thf and thf not in k.split("|")[0]: continue
    x = a["rows"].get(k, [0, 0, 0]); y = b["rows"].get(k, [0, 0, 0])
    rows.append((y[0] - x[0], k, x, y))
tot = {}
for d, k, x, y in rows:
    th = k.split("|")[0]; t = tot.setdefault(th, [0, 0]); t[0] += x[0]; t[1] += y[0]
print("thread exclusive totals us/frame:", {k: (round(v[0]), round(v[1])) for k, v in tot.items()})
print(f"{'dExcl':>8} {'A excl':>8} {'B excl':>8} {'A incl':>8} {'B incl':>8} {'A n':>6} {'B n':>6}  thread|timer")
for d, k, x, y in sorted(rows, key=lambda r: -abs(r[0]))[:top]:
    print(f"{d:+8.1f} {x[0]:8.1f} {y[0]:8.1f} {x[1]:8.1f} {y[1]:8.1f} {x[2]:6.2f} {y[2]:6.2f}  {k[:100]}")
