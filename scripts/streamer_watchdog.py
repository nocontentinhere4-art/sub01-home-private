#!/usr/bin/env python3
"""SUB-01 streamer watchdog: an independent process that stops the agent when it stops answering or acts too fast.

    python3 scripts/streamer_watchdog.py --streamer-dir /home/unreal/.sub01-private/streamer \\
        --token-file /home/unreal/.sub01-private/operator-token

Standard library only (urllib), so it runs with /usr/bin/python3 next to the agent and survives the agent's venv. Every
`--interval` seconds (5) it reads
  * the agent's heartbeat: GET <agent-url>/state (X-Admin-Token) `t`, else <streamer-dir>/state.json `t` (the agent
    rewrites it every 2 s): the newest of the two;
  * the actions of the last 60 s: `action` rows of <streamer-dir>/events.jsonl (written by the agent BEFORE it sends an
    action) and `act` receipts of the desktop runner's <desktop-data-dir>/events.jsonl (written by the runner after it
    ran one), tailed by offset (rotation and truncation handled); the larger count is used.
It trips when the heartbeat is older than `--heartbeat-timeout` (30 s; before the first heartbeat a `--grace` of 60 s
from its own start), when the agent reports its main loop stuck for `--max-loop-age` (180 s) while not paused, or when
more than `--max-actions-per-minute` (20, the agent's own cap) actions happened in 60 s. A trip:
  1. writes <streamer-dir>/STOP with the reason (the agent pauses within 1 s and never deletes STOP; the supervisor holds
     the agent down while it exists);
  2. releases every held key and mouse button on the remote PC: POST <desktop-url>/pc/session {"active": false,
     "source": "native"} with the token, confirmed only by HTTP 200 with the runner's view `session: false` (or its
     privacy lock, `privacy: true`), tried twice, and retried with an ALERT at every later check until confirmed;
  3. appends a `trip` row to <streamer-dir>/watchdog.jsonl.
It does not trip again while STOP exists (a STOP it could not write is retried, with an ALERT, at every check); once
an operator removes STOP it watches again (a fresh grace for the heartbeat). `wait`/`zoom` rows send no input and are
not counted, as in the agent's own cap. It never removes STOP, never touches the agent's other files, and exits 0 on SIGTERM/SIGINT. `--once` runs
one check and exits 0 (all clear) or 3 (tripped) for tests and cron. Limits: on the same pod it cannot survive the pod
itself; the remote PC's own session (Vagon) is outside its reach.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

PREFIX = "streamer watchdog:"
PRIVATE = "/home/unreal/.sub01-private"


def log(msg):
    print(f"{PREFIX} {msg}", flush=True)


def read_token(path):
    env = os.environ.get("SUB01_ADMIN_TOKEN", "").strip()
    if env:
        return env
    try:
        return Path(path).read_text().strip() if path else ""
    except OSError:
        return ""


def http_json(method, url, token, body=None, timeout=4.0):
    """-> (status, parsed JSON or None). Network errors -> (None, None). The token only travels in the header."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("X-Admin-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(1 << 20)
            status = r.status
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return None, None
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return status, None


def row_time(row):
    """The unix time of an events.jsonl row: the agent's `t` (float) or the runner's ISO `t`."""
    t = row.get("t")
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    if isinstance(t, str):
        try:
            return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


NO_INPUT = ("wait", "zoom")             # as in the agent: kinds that send no input are not in the action cap


def is_input(row):
    a = row.get("action")
    kind = a.get("action") if isinstance(a, dict) else a
    return kind not in NO_INPUT


class Tail:
    """New complete lines of an append-only JSONL file since the last call; a shrunk or replaced file starts over."""

    def __init__(self, path, kind):
        self.path, self.kind = Path(path), kind
        self.offset, self.ino, self.rest = None, None, b""

    def times(self):
        try:
            st = self.path.stat()
        except OSError:
            return []
        if self.offset is None:                               # first look: only the last 256 KB matter for a minute
            self.offset, self.ino = max(0, st.st_size - 256 * 1024), st.st_ino
        if st.st_ino != self.ino or st.st_size < self.offset:
            self.offset, self.ino, self.rest = 0, st.st_ino, b""
        if st.st_size == self.offset:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read(min(st.st_size - self.offset, 8 << 20))
        except OSError:
            return []
        self.offset += len(chunk)
        lines = (self.rest + chunk).split(b"\n")
        self.rest = lines.pop()
        out = []
        for ln in lines:
            if self.kind.encode() not in ln:
                continue
            try:
                row = json.loads(ln)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("kind") == self.kind and is_input(row) and (t := row_time(row)) is not None:
                out.append(t)
        return out


class Watchdog:
    def __init__(self, a, clock=time.time):
        self.a, self.clock = a, clock
        self.dir = Path(a.streamer_dir)
        self.token = read_token(a.token_file)
        self.started = clock()
        self.seen_heartbeat = False
        self.tails = {"agent": Tail(self.dir / "events.jsonl", "action"),
                      "runner": Tail(Path(a.desktop_data_dir or self.dir / "desktop") / "events.jsonl", "act")}
        self.recent = {k: collections.deque() for k in self.tails}
        self.tripped_by = None                                # set while our STOP is in place
        self.release_pending = False                          # the key release not confirmed yet: retried every check
        self.release_status = None
        self.last = {}

    @property
    def stop_file(self):
        return self.dir / "STOP"

    def heartbeat(self):
        """-> (newest heartbeat time or None, loop age or None, paused)."""
        best, loop_age, paused = None, None, False
        status, d = http_json("GET", self.a.agent_url.rstrip("/") + "/state", self.token)
        if status == 200 and isinstance(d, dict):
            if isinstance(d.get("t"), (int, float)):
                best = float(d["t"])
            loop_age = (d.get("heartbeat") or {}).get("loop_age_s")
            paused = bool(d.get("paused"))
        try:
            s = json.loads((self.dir / "state.json").read_text())
            if isinstance(s.get("t"), (int, float)):
                best = max(best or 0.0, float(s["t"]))
                if loop_age is None:
                    hb = s.get("heartbeat") or {}
                    if isinstance(hb.get("loop_t"), (int, float)):
                        loop_age = self.clock() - hb["loop_t"]
                    paused = paused or bool(s.get("paused"))
        except (OSError, ValueError, AttributeError):
            pass
        return best, loop_age, paused

    def actions_last_minute(self, now):
        counts = {}
        for k, tail in self.tails.items():
            q = self.recent[k]
            q.extend(tail.times())
            while q and now - q[0] > 60.0:
                q.popleft()
            counts[k] = sum(1 for t in q if now - t <= 60.0)
        return counts

    def check(self):
        """One look; -> the trip reason or None."""
        now = self.clock()
        if self.tripped_by and not self.stop_file.exists():   # the operator removed STOP: watch again, fresh grace
            log("STOP removed: watching again")
            self.tripped_by, self.seen_heartbeat, self.started, self.release_pending = None, False, now, False
        if self.tripped_by and self.release_pending:          # Kimi: an unconfirmed release keeps being retried
            self.release_pending = not self.release()
            if self.release_pending:
                log("ALERT key release still not confirmed by the runner")
        hb, loop_age, paused = self.heartbeat()
        counts = self.actions_last_minute(now)
        self.last = {"t": now, "heartbeat_age_s": None if hb is None else round(now - hb, 1), "loop_age_s": loop_age,
                     "actions_last_minute": counts, "stop": self.stop_file.exists()}
        if hb is not None and now - hb <= self.a.heartbeat_timeout:
            self.seen_heartbeat = True
        why = None
        if hb is None or now - hb > self.a.heartbeat_timeout:
            if self.seen_heartbeat or now - self.started > self.a.grace:
                why = ("no heartbeat yet" if hb is None and not self.seen_heartbeat else
                       f"heartbeat missing for {now - hb:.0f} s" if hb is not None else "heartbeat unreadable")
        elif isinstance(loop_age, (int, float)) and loop_age > self.a.max_loop_age and not paused:
            why = f"main loop stuck for {loop_age:.0f} s"
        top = max(counts.values()) if counts else 0
        if why is None and top > self.a.max_actions_per_minute:
            why = f"{top} actions in 60 s (cap {self.a.max_actions_per_minute})"
        if why and not self.tripped_by and not self.stop_file.exists():
            self.trip(why)                                    # latched only once STOP is really there (Kimi)
            return why
        return None

    def trip(self, why):
        try:
            self.stop_file.write_text(json.dumps({"by": "streamer_watchdog", "why": why, "t": self.clock()}) + "\n")
            os.chmod(self.stop_file, 0o600)
            stop_ok = self.stop_file.exists()
        except OSError as e:
            stop_ok = False
            log(f"ALERT cannot write STOP ({e}): retrying at every check")
        if stop_ok:                                           # not latched without STOP: the next check tries again
            self.tripped_by = why
        release_ok = self.release()
        self.release_pending = not release_ok
        row = {"t": self.clock(), "kind": "trip", "why": why, "stop_written": stop_ok, "release_status": self.release_status,
               "release_ok": release_ok, "state": self.last}
        try:
            fd = os.open(self.dir / "watchdog.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        except OSError as e:
            log(f"cannot write watchdog.jsonl: {e}")
        log(f"TRIP ({why}): STOP {'written' if stop_ok else 'NOT written'}, key release HTTP {self.release_status} "
            f"({'confirmed' if release_ok else 'NOT confirmed: ALERT, retried at every check'})")

    def release(self):
        """POST /pc/session {"active": false, "source": "native"}, twice at most. Confirmed only by the runner's view as
        it documents it: `session: false` (the keys and buttons were released), or `privacy: true` (its privacy lock
        released them and refuses input); anything else, `{}` included, stays unconfirmed (Kimi)."""
        self.release_status = None
        for _ in range(2):
            status, body = http_json("POST", self.a.desktop_url.rstrip("/") + "/pc/session", self.token,
                                     {"active": False, "source": "native"}, timeout=5.0)
            self.release_status = status
            if status == 200 and isinstance(body, dict) and (body.get("session") is False or body.get("privacy") is True):
                return True
        return False


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="SUB-01 streamer watchdog (heartbeat + action rate -> STOP + key release)")
    p.add_argument("--streamer-dir", default=os.environ.get("STREAMER_DIR") or f"{PRIVATE}/streamer")
    p.add_argument("--token-file", default=f"{PRIVATE}/operator-token", help="operator token (or env SUB01_ADMIN_TOKEN)")
    p.add_argument("--agent-url", default="http://127.0.0.1:8836")
    p.add_argument("--desktop-url", default=os.environ.get("STREAMER_DESKTOP_URL") or "http://127.0.0.1:8832",
                   help="the desktop runner whose /pc/session releases the remote PC's keys")
    p.add_argument("--desktop-data-dir", default=None, help="the runner's --data-dir (its events.jsonl); default <dir>/desktop")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--heartbeat-timeout", type=float, default=30.0)
    p.add_argument("--grace", type=float, default=60.0, help="seconds without any heartbeat after start before tripping")
    p.add_argument("--max-loop-age", type=float, default=180.0, help="the agent's main loop stuck this long (not paused)")
    p.add_argument("--max-actions-per-minute", type=int, default=20)
    p.add_argument("--once", action="store_true", help="one check: exit 0 all clear, 3 tripped")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    wd = Watchdog(a)
    if a.once:
        return 3 if wd.check() else 0
    running = [True]

    def stop(*_):
        running[0] = False
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    log(f"watching {a.streamer_dir} (agent {a.agent_url}, release via {a.desktop_url}/pc/session, heartbeat "
        f"{a.heartbeat_timeout:.0f} s, {a.max_actions_per_minute} actions/min, token {'set' if wd.token else 'MISSING'})")
    while running[0]:
        try:
            wd.check()
        except Exception as e:                                # pragma: no cover - a watchdog never dies of one bad look
            log(f"check failed: {type(e).__name__}: {e}")
        end = time.time() + a.interval
        while running[0] and time.time() < end:
            time.sleep(min(0.5, max(0.0, end - time.time())))
    log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
