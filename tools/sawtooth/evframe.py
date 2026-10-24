#!/usr/bin/env python3
"""Print every event of the given threads between T0 and T0+SPAN (s) from an ExportTimingEvents CSV, as an indented
timeline (times in ms relative to T0).
usage: evframe.py EVENTS.csv T0 SPAN THREAD[,THREAD...] [MAXDEPTH] [MIN_US]"""
import csv, sys
src, t0, span = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
ths = set(sys.argv[4].split(","))
md = int(sys.argv[5]) if len(sys.argv) > 5 else 99
mn = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
rows = []
with open(src, newline="") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if len(row) < 5 or row[0] not in ths: continue
        try: s, e, d = float(row[2]), float(row[3]), int(row[4])
        except ValueError: continue
        if e < t0 or s > t0 + span or d > md: continue
        if (e - s) * 1e6 < mn: continue
        rows.append((row[0], s, e, d, row[1].strip('"')))
for th in sorted(ths):
    print(f"== {th}")
    for t, s, e, d, n in sorted(x for x in rows if x[0] == th):
        print(f"{(s - t0) * 1e3:9.3f} {(e - s) * 1e3:8.3f} {'  ' * d}{n}")
