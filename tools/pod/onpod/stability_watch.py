#!/usr/bin/env python3
"""Passive 1-hour stability watch of the live SUB-01 stack: samples, never acts (no restart, no STOP, no provider call).

    python3 stability_watch.py OUT.jsonl [--seconds 3600] [--every 30]

Each sample is one JSON line: supervisor services (status, pid, starts), the game's RSS and the visual receipt's fps,
the newest HLS segment's age, STOP present, the public relay's /status answer, load and free disk. At the end one
`summary` line: restarts per service during the window, game fps min/median, RSS growth, the worst HLS age, STOP seen.
"""
import argparse
import json
import os
import shutil
import statistics
import time
import urllib.request
from pathlib import Path

P = Path("/home/unreal/.sub01-private")
SD = P / "streamer"
HLS = P / "owner-stack-20261026" / "hls"
RECEIPT = P / "streamer-visual-receipt.json"


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def game_rss_mb():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
            if b"Sub01HomeLab" not in cmd or b"Engine/Bin" not in cmd:
                continue
            for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return int(pid), round(int(line.split()[1]) / 1024)
        except OSError:
            continue
    return None, None


def hls_age():
    try:
        newest = max((p.stat().st_mtime for p in HLS.glob("*.ts")), default=None)
    except OSError:
        return None
    return None if newest is None else round(time.time() - newest, 1)


def relay_status():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8841/status", timeout=3) as r:
            return r.status
    except Exception as exc:                                  # an unreachable relay is a sample, not a crash
        return type(exc).__name__


def sample():
    sup = read_json(SD / "supervisor.json") or {}
    services = {n: {"status": s.get("status"), "pid": s.get("pid"), "starts": s.get("starts")}
                for n, s in (sup.get("services") or {}).items()}
    rec = read_json(RECEIPT) or {}
    pid, rss = game_rss_mb()
    du = shutil.disk_usage("/")
    return {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "services": services, "game_pid": pid,
            "game_rss_mb": rss, "fps": rec.get("fps"), "frame_max_ms": rec.get("frame_max_ms"), "hls_age_s": hls_age(),
            "stop": (SD / "STOP").exists(), "relay": relay_status(), "load1": round(os.getloadavg()[0], 2),
            "root_free_gb": round(du.free / 2**30, 1)}


def summary(rows):
    first, last = rows[0], rows[-1]
    restarts = {}
    for name, s in last["services"].items():
        a, b = (first["services"].get(name) or {}).get("starts"), s.get("starts")
        if isinstance(a, int) and isinstance(b, int):
            restarts[name] = b - a
    fps = [r["fps"] for r in rows if isinstance(r.get("fps"), (int, float))]
    rss = [r["game_rss_mb"] for r in rows if r.get("game_rss_mb")]
    ages = [r["hls_age_s"] for r in rows if isinstance(r.get("hls_age_s"), (int, float))]
    return {"summary": True, "samples": len(rows), "from": first["t"], "to": last["t"], "restarts": restarts,
            "game_pid_changed": len({r["game_pid"] for r in rows if r.get("game_pid")}) > 1,
            "fps_min": min(fps) if fps else None, "fps_median": statistics.median(fps) if fps else None,
            "rss_first_mb": rss[0] if rss else None, "rss_last_mb": rss[-1] if rss else None,
            "hls_age_max_s": max(ages) if ages else None, "stop_seen": any(r["stop"] for r in rows),
            "relay_not_200": sum(1 for r in rows if r["relay"] != 200)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=3600.0)
    ap.add_argument("--every", type=float, default=30.0)
    a = ap.parse_args()
    rows, end = [], time.monotonic() + a.seconds
    with open(a.out, "a") as fh:
        while True:
            row = sample()
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if time.monotonic() >= end:
                break
            time.sleep(a.every)
        fh.write(json.dumps(summary(rows)) + "\n")


if __name__ == "__main__":
    main()
