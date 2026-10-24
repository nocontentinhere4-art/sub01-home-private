#!/usr/bin/env python3
"""While THREAD is inside TIMER (e.g. the render thread's WaitForTasks under ProcessVisibilityTasks), which timers do the
other threads run?  Sums each other thread's EXCLUSIVE time per timer clipped to those intervals, per interval.
usage: during.py EVENTS.csv THREAD TIMER [MIN_MS] [TOP]"""
import csv, sys, collections
src, th, timer = sys.argv[1], sys.argv[2], sys.argv[3]
mn = float(sys.argv[4]) / 1e3 if len(sys.argv) > 4 else 0.0005
top = int(sys.argv[5]) if len(sys.argv) > 5 else 30
ev = collections.defaultdict(list)
with open(src, newline="") as f:
    r = csv.reader(f); next(r)
    for row in r:
        if len(row) < 5 or row[0] == "Rendering Frames": continue
        try: s, e, d = float(row[2]), float(row[3]), int(row[4])
        except ValueError: continue
        if e < 1e17: ev[row[0]].append((s, d, e, row[1].strip('"')))
iv = sorted((s, e) for s, d, e, n in ev[th] if n == timer and e - s >= mn)
print(f"{len(iv)} intervals, mean {sum(e - s for s, e in iv) / len(iv) * 1e3:.3f} ms")
# exclusive segments for each other thread: walk the hierarchy and emit (start, end, name) leaf-exclusive pieces
def segments(lst):
    lst.sort(); out = []; stack = []   # stack of [name, end, cursor]
    def close_until(t):
        while stack and stack[-1][1] <= t:
            n, e, cur = stack.pop()
            if e > cur: out.append((cur, e, n))
            if stack: stack[-1][2] = e
    for s, d, e, n in lst:
        close_until(s)
        if stack and s > stack[-1][2]: out.append((stack[-1][2], s, stack[-1][0]))
        if stack: stack[-1][2] = s
        stack.append([n, e, s])
    close_until(1e18)
    return out
agg = collections.defaultdict(float); busy = collections.defaultdict(float)
import bisect
starts = [s for s, e in iv]
for other, lst in ev.items():
    if other == th: continue
    for s, e, n in segments(lst):
        i = bisect.bisect_right(starts, e) - 1
        while i >= 0 and iv[i][1] > s:
            a, b = max(s, iv[i][0]), min(e, iv[i][1])
            if b > a:
                agg[(other, n)] += b - a
                if n not in ("TaskWorkerIsLookingForWork", "WaitForTasks", "WaitForRHIThreadTasks"): busy[other] += b - a
            i -= 1
k = len(iv)
print("busy ms per interval:", {t: round(v / k * 1e3, 2) for t, v in sorted(busy.items())})
for (t, n), v in sorted(agg.items(), key=lambda x: -x[1])[:top]:
    print(f"{v / k * 1e3:8.3f} ms/interval  {t:28s} {n[:90]}")
