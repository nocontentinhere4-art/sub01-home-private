"""v25watch.py OUT_DIR [SECONDS]: poll the visual receipt every 0.2 s; count samples with a v25 gesture (left/right > 0.05)
or a head roll (|roll| > 1 deg) and, at the first few of each, grab the live HLS frame ~3 s later (the HLS lags) for review.
Read-only. Prints a JSON summary at the end (event and grab times and the segment used, so the lag can be checked)."""
import glob, json, os, subprocess, sys, time
OUT = sys.argv[1]; SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 600
R = "/home/unreal/.sub01-private/streamer-visual-receipt.json"
H = "/home/unreal/.sub01-private/owner-stack-20261026/hls"
os.makedirs(OUT, exist_ok=True)
n = {"samples": 0, "gesture": 0, "roll": 0, "talking": 0}
grabs, pending, last_grab = [], [], 0.0


def grab(p):
    segs = sorted(glob.glob(H + "/*.ts"), key=os.path.getmtime)
    row = {"event_t": round(p[0] - 3, 1), "grab_t": round(time.time(), 1), "kind": p[1], "gesture": p[2], "roll": p[3],
           "camera": p[4], "segment": None, "file": None, "ok": False}
    if len(segs) >= 2:
        row["segment"] = os.path.basename(segs[-2])                # the newest complete segment
        name = f"{OUT}/v25-{len(grabs) + 1}-{p[1]}.jpg"
        if os.path.exists(name):
            os.remove(name)
        rc = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", segs[-2], "-frames:v", "1", "-update", "1", name]).returncode
        row["file"], row["ok"] = name, rc == 0 and os.path.exists(name)
    grabs.append(row)


end = time.time() + SECONDS
while time.time() < end:
    now = time.time()
    for p in [p for p in pending if p[0] <= now]:
        pending.remove(p)
        grab(p)
    try:
        r = json.load(open(R))
    except (OSError, ValueError):
        time.sleep(0.2); continue
    n["samples"] += 1
    n["talking"] += r.get("state") == "talking"
    g = max(float(r.get("v25_gesture_left") or 0), float(r.get("v25_gesture_right") or 0))
    roll = abs(float(r.get("v25_head_roll_deg") or 0))
    kinds = [k for k, hit in (("gesture", g > 0.05), ("roll", roll > 1)) if hit]
    for k in kinds:
        n[k] += 1
    if kinds and now - last_grab > 5 and len(grabs) + len(pending) < 8:
        pending.append((now + 3, "-".join(kinds), round(g, 2), round(roll, 1), r.get("camera")))
        last_grab = now
    time.sleep(0.2)
for p in pending:                                                  # the window ended: flush, never drop silently
    time.sleep(max(0.0, p[0] - time.time()))
    grab(p)
print(json.dumps({"counts": n, "grabs": grabs}))
