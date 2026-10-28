"""Hourly agent lease renewal (owner's explicit OK, 2026-10-28 02:07 UTC: "Rinnovo automatico").

Every --every seconds it reads the agent's /state; when the lease has less than --below seconds left it re-arms it with
POST /lease {"minutes": 60}. It never renews while a guard rail is up: the STOP file, held, frozen, audit_degraded or
probation. Those keep needing a human (/resume), and a lease that runs out while one is up stays out. A renewal that
fails is logged and not retried until the next check. Stop it by killing the process or creating --off-file.
Run as unreal: setsid nohup python3 lease_renew.py > /dev/null 2>&1 < /dev/null &"""
import argparse, json, os, time, urllib.request
from datetime import datetime, timezone

p = argparse.ArgumentParser()
p.add_argument("--agent", default="http://127.0.0.1:8836")
p.add_argument("--token-file", default="/home/unreal/.sub01-private/operator-token")
p.add_argument("--stop-file", default="/home/unreal/.sub01-private/streamer/STOP")
p.add_argument("--off-file", default="/home/unreal/.sub01-private/lease-renew.off")
p.add_argument("--log", default="/home/unreal/.sub01-private/streamer/logs/lease-renew.log")
p.add_argument("--every", type=float, default=300)
p.add_argument("--below", type=float, default=900)
p.add_argument("--minutes", type=int, default=60)
a = p.parse_args()


def log(**kw):
    kw = {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **kw}
    with open(a.log, "a") as f:
        f.write(json.dumps(kw) + "\n")


def call(path, body=None):
    token = open(a.token_file).read().strip()
    req = urllib.request.Request(a.agent + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Admin-Token": token, "Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def check():
    if os.path.exists(a.off_file):
        return log(event="skip", why="off_file")
    if os.path.exists(a.stop_file):
        return log(event="skip", why="STOP")
    st = call("/state")
    if st.get("stop_file") or st.get("paused"):
        return log(event="skip", why="agent STOP/paused")
    g = st.get("guards") or {}
    up = [k for k in ("held", "frozen", "audit_degraded", "probation") if g.get(k)]
    if up:
        return log(event="skip", why="guard", guards=up)
    left = (st.get("lease") or {}).get("remaining_s") or 0
    if (st.get("lease") or {}).get("active") and left > a.below:
        return
    r = call("/lease", {"minutes": a.minutes})
    log(event="renewed", left_before_s=left, ok=r.get("ok"), expires=(r.get("lease") or {}).get("expires_utc"))


log(event="start", every=a.every, below=a.below, minutes=a.minutes, pid=os.getpid())
while True:
    try:
        check()
    except Exception as e:                       # agent restarting or unreachable: try again at the next check only
        log(event="error", error=str(e)[:160])
    time.sleep(a.every)
