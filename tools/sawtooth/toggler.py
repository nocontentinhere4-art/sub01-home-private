#!/usr/bin/env python3
"""Sawtooth mitigation probe: recreate the game's Vulkan swapchain every PERIOD s by alternating r.VSync 1 / 0 through
the live console (gc.py as user unreal). Each toggle costs one ~85 ms frame and resets the present-cost ramp.
Stops after DURATION s (0 = forever) or when STOPFILE exists; always leaves r.VSync 0.
usage: toggler.py PERIOD_S DURATION_S LOGFILE [--double]   (--double: 1 then 0 two seconds apart, stays IMMEDIATE)"""
import os, subprocess, sys, time
period, dur, logf = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
double = "--double" in sys.argv
STOP = "/tmp/sub01-share/w-sawtooth/toggler.stop"
def gc(*cmds):
    r = subprocess.run(["runuser", "-u", "unreal", "--", "python3", "/tmp/sub01-share/gc.py", *cmds], capture_output=True, text=True)
    return r.stdout.strip().replace("\n", " | ")
def log(msg):
    with open(logf, "a") as f: f.write(f"{time.time():.1f} {time.strftime('%H:%M:%S', time.gmtime())} {msg}\n")
end = time.time() + dur if dur > 0 else float("inf"); state = 0
log(f"start period={period} double={double}")
try:
    nxt = time.time() + period
    while time.time() < end and not os.path.exists(STOP):
        time.sleep(max(0.0, min(1.0, nxt - time.time())))
        if time.time() < nxt: continue
        nxt += period
        if double:
            log("toggle 1 " + gc("r.VSync 1")); time.sleep(2); log("toggle 0 " + gc("r.VSync 0"))
        else:
            state ^= 1; log(f"toggle {state} " + gc(f"r.VSync {state}"))
finally:
    log("stop " + gc("r.VSync 0"))
