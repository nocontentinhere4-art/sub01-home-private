#!/usr/bin/env python3
"""EXPERIMENTAL interim mitigation for the render-time sawtooth (docs/streamer/SAWTOOTH-20261024.md).

The game's main view is presented through the NVIDIA Vulkan X11 path on Xvfb :99. The CPU cost of vkQueuePresentKHR on
the RHI thread grows with every present (+~3.3 ms per frame over ~21.7k presents) and drops back only when the swapchain
is recreated or after ~21.7k presents. Every PERIOD seconds this flips r.VSync through the game's private live console
(`streamer-visual-console.json`, uid 1001, mode 0600); each flip makes UE recreate the swapchain, which costs one
~80 ms frame and resets the ramp. FIFO (r.VSync 1) and IMMEDIATE (r.VSync 0) behave the same on Xvfb.

Not a structural fix (the base present cost stays) and not soaked: run it only after an 8-24 h soak, as uid 1001, one
instance at a time (a lock file enforces it), with the stop file as the kill switch. It is the only writer of the
console file while it runs: other tools (gc.py) racing with it can lose a request. On a normal exit (stop file,
SIGTERM/SIGINT, --duration) it writes r.VSync 0 (retried); a SIGKILL or a failing disk cannot, so whoever stops it
uncleanly must send `r.VSync 0` themselves.

usage (as uid 1001): streamer_swapchain_refresh.py [--period 120] [--duration 0] [--console PATH] [--stop-file PATH]
"""
import argparse
import fcntl
import json
import math
import os
import signal
import sys
import tempfile
import time

CONSOLE = "/home/unreal/.sub01-private/streamer-visual-console.json"
STOP_FILE = "/home/unreal/.sub01-private/streamer/swapchain-refresh.stop"
SCHEMA = "sub01.private-streamer-visual-console.v1"
GAME_UID = 1001
MIN_PERIOD_S = 30.0


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        if n <= 0:
            raise OSError("short write")
        view = view[n:]


class Console:
    """Writes live-console requests; the game runs each request once per growing sequence (ms since the epoch, kept
    strictly increasing inside this process)."""

    def __init__(self, path, clock=time.time, write=_write_all):
        self.path, self.clock, self.write, self.last = path, clock, write, 0

    def send(self, *commands):
        seq = max(int(self.clock() * 1000), self.last + 1)
        self.last = seq
        data = json.dumps({"schema": SCHEMA, "sequence": seq, "commands": list(commands)}).encode()
        fd, tmp = tempfile.mkstemp(prefix=".refresh-", suffix=".tmp", dir=os.path.dirname(self.path) or ".")
        try:
            os.fchmod(fd, 0o600)
            self.write(fd, data)
            os.fsync(fd)
        except BaseException:
            os.close(fd)
            os.unlink(tmp)
            raise
        os.close(fd)
        os.replace(tmp, self.path)
        return seq


def _finite(name, value, minimum):
    if not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be a finite number >= {minimum:g}")


def run(console, period, duration=0.0, stop_file=STOP_FILE, clock=time.monotonic, sleep=time.sleep, out=sys.stdout,
        stop=lambda: False, restore_attempts=3):
    """Alternate r.VSync 1/0 every `period` s until the stop file exists, `stop()` is true or `duration` (>0) elapsed.
    A clock jump (suspend) gives one flip, then a full period. Returns the number of flips; ends by writing r.VSync 0
    (retried `restore_attempts` times; the last error is raised if every attempt fails)."""
    _finite("period", period, MIN_PERIOD_S)
    _finite("duration", duration, 0.0)
    start = clock()
    due, state, flips = start + period, 0, 0

    def note(**fields):
        out.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields}) + "\n")
        out.flush()

    note(event="start", period_s=period, duration_s=duration)
    try:
        while not stop() and not os.path.exists(stop_file) and not (duration > 0 and clock() - start >= duration):
            now = clock()
            if now < due:
                sleep(min(1.0, due - now))
                continue
            state ^= 1
            seq = console.send(f"r.VSync {state}")
            flips += 1
            note(event="flip", vsync=state, sequence=seq, flips=flips)
            due += period
            if due <= clock():          # we fell behind (suspend, clock jump): no burst, a full period from now
                due = clock() + period
    finally:
        for attempt in range(1, restore_attempts + 1):
            try:
                seq = console.send("r.VSync 0")
                note(event="stop", vsync=0, sequence=seq, flips=flips)
                break
            except OSError as exc:
                note(event="restore_failed", attempt=attempt, error=str(exc))
                if attempt == restore_attempts:
                    raise
                sleep(1.0)
    return flips


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--period", type=float, default=120.0, help="seconds between swapchain recreations (>= 30)")
    p.add_argument("--duration", type=float, default=0.0, help="stop after this many seconds (0 = until stopped)")
    p.add_argument("--console", default=CONSOLE)
    p.add_argument("--stop-file", default=STOP_FILE)
    p.add_argument("--lock-file", default=None, help="default: <console>.refresh.lock")
    args = p.parse_args(argv)
    if os.geteuid() != GAME_UID:
        p.error(f"run as uid {GAME_UID} (the game's user): the console file is private to it")
    _finite("period", args.period, MIN_PERIOD_S)
    _finite("duration", args.duration, 0.0)
    lock = open(args.lock_file or args.console + ".refresh.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        p.error("another streamer_swapchain_refresh is running")
    stopping = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.append(1))
    run(Console(args.console), args.period, args.duration, args.stop_file, stop=lambda: bool(stopping))
    return 0


if __name__ == "__main__":
    sys.exit(main())
