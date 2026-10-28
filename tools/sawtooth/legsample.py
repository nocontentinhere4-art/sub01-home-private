#!/usr/bin/env python3
"""Light per-leg sampler (one JSON line every INTERVAL s for DURATION s) for the sawtooth work.
Per sample: the game's last PERF line (fps, render/gpu/rhi ms), cgroup cpu.stat deltas (usage, nr_throttled,
throttled_usec), and for the game's main threads plus extra pids (Xvfb :99, the director's ffmpeg): CPU ms/s,
run-queue wait ms/s (schedstat), voluntary/involuntary context switches/s; also the game's RSS and thread count.
usage: legsample.py OUT.jsonl DURATION_S [INTERVAL_S] [EXTRA_PID ...]"""
import json, os, re, sys, time
LOG = "/tmp/sub01-share/game.log"
out, dur = sys.argv[1], float(sys.argv[2])
iv = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
extra = [p for p in sys.argv[4:]]
pid = open("/home/unreal/.sub01-private/streamer/game.pid").read().strip()
HZ = os.sysconf("SC_CLK_TCK")
WANT = re.compile(r"^(UnrealEditor-Cm|RenderThread|RHIThread|Foregro|Backgro-rker|RTHeartBeat|\[vk|cuda)")
def task_stats(p, t):
    base = f"/proc/{p}/task/{t}"
    s = open(base + "/stat").read(); name = s[s.index("(") + 1:s.rindex(")")]; f = s[s.rindex(")") + 2:].split()
    run, wait, slices = (int(x) for x in open(base + "/schedstat").read().split())
    st = open(base + "/status").read()
    v = int(re.search(r"voluntary_ctxt_switches:\s+(\d+)", st).group(1))
    nv = int(re.search(r"nonvoluntary_ctxt_switches:\s+(\d+)", st).group(1))
    return name, ((int(f[11]) + int(f[12])) * 1000.0 / HZ, run / 1e6, wait / 1e6, v, nv)
def snap():
    d = {}
    for t in os.listdir(f"/proc/{pid}/task"):
        try:
            name, v = task_stats(pid, t)
            if WANT.match(name): d[f"{name.strip()}#{t}"] = v
        except (OSError, ValueError, AttributeError): pass
    for p in extra:
        try:
            tot = None
            for t in os.listdir(f"/proc/{p}/task"):
                name, v = task_stats(p, t)
                tot = v if tot is None else tuple(a + b for a, b in zip(tot, v))
            d[f"pid{p}"] = tot
        except (OSError, ValueError, AttributeError): pass
    return d
def cg():
    return {k: int(v) for k, v in (l.split() for l in open("/sys/fs/cgroup/cpu.stat"))}
def perf():
    with open(LOG, "rb") as f:
        f.seek(max(0, os.path.getsize(LOG) - 60000)); t = f.read().decode("utf-8", "replace")
    m = re.findall(r"\[([\d.:-]+)\]\[[\s\d]+\]LogTemp: Display: SUB01_STREAMER_VISUAL_PERF (.*)", t)
    if not m: return {}
    ts, rest = m[-1]
    d = {"ts": ts}
    for k, v in re.findall(r"(\w+)=([\d.]+)", rest): d[k] = float(v)
    return d
def mem():
    st = open(f"/proc/{pid}/status").read()
    return int(re.search(r"VmRSS:\s+(\d+)", st).group(1)) // 1024, int(re.search(r"Threads:\s+(\d+)", st).group(1))
a, ca, ta = snap(), cg(), time.time(); end = ta + dur
with open(out, "a") as fo:
    while time.time() < end:
        time.sleep(iv)
        b, cb, tb = snap(), cg(), time.time(); dt = tb - ta
        th = {}
        for k in b:
            if k in a and b[k] and a[k]:
                x, y = a[k], b[k]
                th[k] = [round((y[0] - x[0]) / dt, 1), round((y[1] - x[1]) / dt, 1), round((y[2] - x[2]) / dt, 1),
                         round((y[3] - x[3]) / dt, 1), round((y[4] - x[4]) / dt, 1)]
        rss, nth = mem()
        rec = {"t": round(tb, 1), "utc": time.strftime("%H:%M:%S", time.gmtime(tb)), "perf": perf(), "rss_mb": rss, "threads": nth,
               "cg": {"cpus": round((cb["usage_usec"] - ca["usage_usec"]) / 1e6 / dt, 2),
                      "throttled_periods": cb["nr_throttled"] - ca["nr_throttled"],
                      "periods": cb["nr_periods"] - ca["nr_periods"],
                      "throttled_ms": round((cb["throttled_usec"] - ca["throttled_usec"]) / 1e3, 1)},
               "th": th}   # per thread: cpu ms/s, run ms/s (schedstat), runqueue-wait ms/s, vol cs/s, invol cs/s
        fo.write(json.dumps(rec) + "\n"); fo.flush()
        a, ca, ta = b, cb, tb
