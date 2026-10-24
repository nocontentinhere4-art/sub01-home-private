#!/usr/bin/env python3
"""Every INTERVAL s: per game thread whose name matches (RHIThread, RenderThread, main thread) and for extra pids:
user ms/s, system ms/s, minor faults/s, major faults/s, voluntary and involuntary context switches/s; the game's
last PERF fps; the whole game process's minor faults/s.  One JSON line per sample.
usage: rhisample.py OUT.jsonl DURATION_S [INTERVAL_S] [EXTRA_PID ...]"""
import json, os, re, sys, time
LOG = "/tmp/sub01-share/game.log"
out, dur = sys.argv[1], float(sys.argv[2]); iv = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
extra = sys.argv[4:]
pid = open("/home/unreal/.sub01-private/streamer/game.pid").read().strip(); HZ = os.sysconf("SC_CLK_TCK")
def rd(base):
    s = open(base + "/stat").read(); name = s[s.index("(") + 1:s.rindex(")")]; f = s[s.rindex(")") + 2:].split()
    st = open(base + "/status").read()
    v = int(re.search(r"\nvoluntary_ctxt_switches:\s+(\d+)", st).group(1)); nv = int(re.search(r"nonvoluntary_ctxt_switches:\s+(\d+)", st).group(1))
    return name, [int(f[11]) * 1000 / HZ, int(f[12]) * 1000 / HZ, int(f[7]), int(f[9]), v, nv]
def snap():
    d = {}
    for t in os.listdir(f"/proc/{pid}/task"):
        try:
            n, v = rd(f"/proc/{pid}/task/{t}")
            if n.startswith(("RHIThread", "RenderThread", "UnrealEditor", "[vk", "Foregro", "Backgro-rker", "cuda")): d[n.strip() + "#" + t] = v
        except (OSError, AttributeError): pass
    try: d["process"] = rd(f"/proc/{pid}")[1]
    except OSError: pass
    for p in extra:
        try: d["pid" + p] = rd(f"/proc/{p}")[1]
        except OSError: pass
    return d
def fps():
    with open(LOG, "rb") as f:
        f.seek(max(0, os.path.getsize(LOG) - 30000)); t = f.read().decode("utf-8", "replace")
    m = re.findall(r"SUB01_STREAMER_VISUAL_PERF fps=([\d.]+).*?render_ms=([\d.]+)", t)
    return [float(x) for x in m[-1]] if m else [0, 0]
a, ta = snap(), time.time(); end = ta + dur
with open(out, "a") as fo:
    while time.time() < end:
        time.sleep(iv); b, tb = snap(), time.time(); dt = tb - ta
        rec = {"utc": time.strftime("%H:%M:%S", time.gmtime(tb)), "fps_render": fps(),
               "d": {k: [round((y - x) / dt, 1) for x, y in zip(a[k], b[k])] for k in b if k in a}}
        fo.write(json.dumps(rec) + "\n"); fo.flush(); a, ta = b, tb
