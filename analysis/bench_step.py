"""CPU of the live loop's pieces, one BLAS thread.

    python analysis/bench_step.py [--seconds 20]
        CPU ms per 50 ms live tick of Brain.step: the step before #19 (dense gather) vs now (sparse ring operator).
        Same pattern as live_server.run_brain: step(5) x 10 per tick + abs/state, slow layer on. The old step is
        tests/test_brain_step.py's reference_step (kept verbatim there for the identity test).
    python analysis/bench_step.py --spiking 25000 100000 [--days 1]
        the spiking child (spiking/live.py) at these sizes: build, CPU per 1 ms step, a 50 ms background pulse, 10
        decisions (learner + twin), one growth step, and the replay of the grown days on a fresh base network.

The BLAS / OpenMP threads are capped by brain_sim and spiking/live.py on import (spiking/threads.py); the setdefault
lines below only make the cap explicit for the reference step.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from brain_sim import Brain  # noqa: E402
from test_brain_step import reference_step  # noqa: E402


def ms_per_tick(step, seconds):
    b = Brain(seed=0)
    for _ in range(20):                       # 1 s warm-up (and builds the sparse operator)
        step(b, 50)
    t = time.process_time()
    ticks = int(seconds / 0.05)
    for _ in range(ticks):
        acc = np.zeros(b.n)
        for _ in range(10):
            acc += np.abs(step(b, 5))
        b.state()
    return (time.process_time() - t) / ticks * 1e3


def rss_mb():
    return round(int(open("/proc/self/statm").read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6, 1)


def spiking_costs(n, days=1):
    """The spiking child's costs at n base neurons (spiking/live.py's LiveBrain, learner + frozen twin, no weights file)."""
    from spiking import live as L
    out = {"n": n}
    t0, c0 = time.perf_counter(), time.process_time()
    b = L.LiveBrain(n, None, twin=True, log=lambda *x: None)
    out.update(build_wall_s=round(time.perf_counter() - t0, 2), build_cpu_s=round(time.process_time() - c0, 2),
               n_syn=int(b.net.n_syn), rss_mb=rss_mb(), calibration=b.calib)
    b.idle(20)                                                  # warm-up
    c0 = time.process_time()
    b.idle(200)
    ms_cpu = (time.process_time() - c0) * 1000 / 200            # CPU ms per 1 ms step
    out.update(cpu_ms_per_step=round(ms_cpu, 3), pulse_cpu_ms=round(ms_cpu * L.IDLE_MS, 1),
               pulse_pct_of_core=round(100 * ms_cpu * L.IDLE_MS / 1000 / L.IDLE_EVERY_S, 2))
    cpu = []
    for i in range(10):                                         # 3 offers, 250 ms timeout (the slow case)
        cpu.append(b.decide(["read about bread", "tokyo parks", "train timetable"], did=f"bench-{i}")["cpu_ms"])
    cpu.sort()
    out.update(decide_cpu_ms_p50=cpu[len(cpu) // 2], decide_cpu_ms_max=cpu[-1])
    grown = []
    for d in range(days):
        c0, w0 = time.process_time(), time.perf_counter()
        r = b.grow_today(f"2026-10-{24 + d:02d}")
        grown.append(round(time.process_time() - c0, 3))
        out.update(grow_wall_s=round(time.perf_counter() - w0, 3), grow_added=r.get("added"))
    out.update(grow_cpu_s_per_day=grown, n_after_growth=int(b.net.n))
    if days:                                                    # the restart: the same ledger on a fresh base network
        fresh = L.LiveNet(b.cfg)
        c0, w0 = time.process_time(), time.perf_counter()
        b.growth.replay(fresh)
        out.update(replay_days=len(b.growth.days), replay_cpu_s=round(time.process_time() - c0, 2),
                   replay_wall_s=round(time.perf_counter() - w0, 2))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--spiking", type=int, nargs="+", help="spiking child sizes (neurons) to measure instead")
    ap.add_argument("--days", type=int, default=1, help="growth steps before the replay (with --spiking)")
    a = ap.parse_args()
    if a.spiking:
        for n in a.spiking:
            print(json.dumps(spiking_costs(n, a.days)), flush=True)
    else:
        old, new = ms_per_tick(reference_step, a.seconds), ms_per_tick(Brain.step, a.seconds)
        print(json.dumps({"before_ms_per_tick": round(old, 2), "after_ms_per_tick": round(new, 2),
                          "speedup": round(old / new, 1), "simulated_s": a.seconds, "tick_s": 0.05}))
