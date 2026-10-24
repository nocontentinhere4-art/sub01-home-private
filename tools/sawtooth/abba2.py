#!/usr/bin/env python3
"""Long-leg ABBA for a runtime setting against the render-time sawtooth (legs cover >= 2 ramps).
Holds the MEASURING lease for the whole run, runs the GPU telemetry and the per-thread samplers throughout, applies
arm A or B, waits WARM s, measures LEG s, and logs leg boundaries. An arm spec is a ';'-list of live-console commands
(gc.py, as user unreal) and/or 'toggler:PERIOD[:double]' (periodic swapchain recreation, toggler.py, for that arm only).
Analysis is separate (abbasum.py) from the game log and the samplers.
usage: abba2.py NAME 'A spec' 'B spec' [--order ABBA] [--leg 900] [--warm 60]"""
import argparse, datetime, json, os, subprocess, time
p = argparse.ArgumentParser(); p.add_argument("name"); p.add_argument("a"); p.add_argument("b")
p.add_argument("--order", default="ABBA"); p.add_argument("--leg", type=float, default=900); p.add_argument("--warm", type=float, default=60)
args = p.parse_args()
O = "/workspace/sub01-w-sawtooth/legs"; os.makedirs(O, exist_ok=True)
W = "/tmp/sub01-share/w-sawtooth"; STOP = f"{W}/toggler.stop"
total = len(args.order) * (args.leg + args.warm) + 30
utc = lambda t=None: datetime.datetime.fromtimestamp(t or time.time(), datetime.timezone.utc).strftime("%H:%M:%S")
end = time.time() + total
with open("/tmp/sub01-share/MEASURING", "w") as f:
    f.write(f"{utc(end)} UTC sawtooth: ABBA {args.name} (A='{args.a}' B='{args.b}', {args.order}, legs {args.leg:.0f}+{args.warm:.0f} s)\n")
xvfb = subprocess.run(["pgrep", "-f", "Xvfb :99 "], capture_output=True, text=True).stdout.split()[:1]
ff = subprocess.run(["pgrep", "-f", "x11grab.*:99.0"], capture_output=True, text=True).stdout.split()[:1]
procs = [subprocess.Popen(["bash", f"{W}/gpusample.sh", f"{O}/{args.name}", str(int(total))]),
         subprocess.Popen(["taskset", "-c", "7", "nice", "-n", "5", "python3", f"{W}/legsample.py", f"{O}/{args.name}.jsonl", str(int(total)), "5", *xvfb, *ff]),
         subprocess.Popen(["taskset", "-c", "7", "nice", "-n", "5", "python3", f"{W}/rhisample.py", f"{O}/{args.name}-rhi.jsonl", str(int(total)), "5", *xvfb, *ff])]
log = open(f"{O}/{args.name}.legs", "a", buffering=1)
toggler = None
def stop_toggler():
    global toggler
    if toggler is not None:
        open(STOP, "w").close()
        try: toggler.wait(timeout=30)
        except subprocess.TimeoutExpired: toggler.kill()
        toggler = None
    try: os.unlink(STOP)
    except OSError: pass
def apply(spec):
    global toggler
    stop_toggler()
    items = [c.strip() for c in spec.split(";") if c.strip()]
    cmds = [c for c in items if not c.startswith("toggler:")]
    out = ""
    if cmds:
        r = subprocess.run(["runuser", "-u", "unreal", "--", "python3", "/tmp/sub01-share/gc.py", *cmds], capture_output=True, text=True)
        out = r.stdout.strip().replace("\n", " | ")
    for t in (c for c in items if c.startswith("toggler:")):
        parts = t.split(":"); extra = ["--double"] if len(parts) > 2 and parts[2] == "double" else []
        toggler = subprocess.Popen(["taskset", "-c", "8", "python3", f"{W}/toggler.py", parts[1], "0", f"{O}/{args.name}.toggles", *extra])
        out += f" toggler {parts[1]} s{' double' if extra else ''}"
    return out
try:
    for i, arm in enumerate(args.order):
        rec = apply(args.a if arm == "A" else args.b)
        t_apply = time.time(); time.sleep(args.warm); t0 = time.time(); time.sleep(args.leg); t1 = time.time()
        log.write(json.dumps({"leg": i, "arm": arm, "applied": t_apply, "t0": t0, "t1": t1, "utc0": utc(t0), "utc1": utc(t1), "receipt": rec}) + "\n")
finally:
    log.write(json.dumps({"restore": apply(args.a), "utc": utc()}) + "\n")
    stop_toggler()
    for pr in procs:
        try: pr.terminate()
        except OSError: pass
    try: os.unlink("/tmp/sub01-share/MEASURING")
    except OSError: pass
