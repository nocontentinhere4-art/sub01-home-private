#!/usr/bin/env python3
"""SUB-01 streamer CPU partition: the game and its X server on dedicated physical cores, everything else on the rest.

Why (measured 2026-10-23 on pod 3u7g6drf5fiiql, docs/streamer/kimi/native-v21-perf.md): the container's cgroup allows
10.2 CPUs (cpu.max 1020000/100000) while 48 logical CPUs are visible (24 cores x 2 SMT, siblings N and N+24). Unpinned,
the container burns its quota early in every 100 ms period and is throttled in 100% of the periods: the game ran at 15 fps
with the GPU at 11 ms. Everything of uid 1001 pinned to cores 0-9 (one SMT thread per core, <= 10 CPUs so the quota is
never hit): 23 fps; the game + Xvfb :99 on 0-5 and the rest on 6-9: 40-42 fps (cam2 on), 53 fps with cam2 off. Kimi:
keep the siblings of the game's cores (24-29) idle, pin at launch where possible, keep watching cpu.stat.

Run it as the game's user (uid 1001): the container's root has no CAP_SYS_NICE, so only the owner can change a
process's affinity, and only processes of THIS uid are moved (other users' processes keep their CPUs: this is not core
exclusivity, only a partition of uid 1001's own load). Every thread of every process of this uid is pinned: the game
process (--game-pid or --game-pid-file) and the X server of --xvfb-display to --game-cpus, everything else to
--other-cpus, the game's own child processes (shader compile workers) included; a thread already on its set is left alone.
Fail closed (Kimi's review): a pass changes NOTHING unless a game pid is given, alive and an UnrealEditor-Cmd streamer
game (a stale or missing game.pid would otherwise push the game onto the others' cores).
--interval N re-applies every N s (new processes; children inherit their parent's set anyway); --once applies once;
--restore gives every thread of this uid the cgroup's effective cpuset again (stop a running --interval loop FIRST, or it
re-partitions); --status prints the plan and the cgroup throttling only. One JSON line per pass on stdout; threads that
exited meanwhile count as `gone`, a refused pin as `failed` (exit 1 when a game thread could not be pinned).

    sudo -u unreal python3 scripts/streamer_cpu_partition.py --game-pid-file /home/unreal/.sub01-private/streamer/game.pid --interval 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_GAME_CPUS, DEFAULT_OTHER_CPUS, DEFAULT_DISPLAY = '0-5', '6-9', ':99'
CGROUP_STAT = Path('/sys/fs/cgroup/cpu.stat')
CGROUP_CPUSET = Path('/sys/fs/cgroup/cpuset.cpus.effective')
GAME_BINARY = 'UnrealEditor-Cmd'
GAME_FLAG = '-Sub01StreamerVisual'


def parse_cpus(spec: str) -> frozenset:
    """'0-5,8' -> {0,1,2,3,4,5,8}; raises ValueError on an empty or malformed list."""
    out = set()
    for part in spec.split(','):
        part = part.strip()
        if not part:
            raise ValueError(f'empty item in cpu list {spec!r}')
        low, _, high = part.partition('-')
        a, b = int(low), int(high or low)
        if a < 0 or b < a:
            raise ValueError(f'bad cpu range {part!r}')
        out.update(range(a, b + 1))
    return frozenset(out)


def is_xvfb(cmdline: list, display: str) -> bool:
    """The X server process of `display` (Xvfb with the display as an argument)."""
    return bool(cmdline) and os.path.basename(cmdline[0]) == 'Xvfb' and display in cmdline[1:]


def is_game(cmdline: list) -> bool:
    """The streamer game: UnrealEditor-Cmd started with -Sub01StreamerVisual."""
    return bool(cmdline) and os.path.basename(cmdline[0]) == GAME_BINARY and GAME_FLAG in cmdline[1:]


def live_games(processes: dict, game_pids: set) -> set:
    """The given pids that are alive, ours and really the streamer game (fail closed on a stale or reused pid)."""
    return {pid for pid in game_pids if pid in processes and is_game(processes[pid].get('cmdline') or [])}


def plan(processes: dict, game_pids: set, display: str, game_cpus: frozenset, other_cpus: frozenset) -> dict:
    """processes: {pid: {'cmdline': [...], 'threads': {tid: frozenset(current cpus)}}} -> {tid: wanted cpus} for the threads to change."""
    changes = {}
    for pid, proc in processes.items():
        wanted = game_cpus if pid in game_pids or is_xvfb(proc.get('cmdline') or [], display) else other_cpus
        for tid, current in proc.get('threads', {}).items():
            if frozenset(current) != wanted:
                changes[tid] = wanted
    return changes


def read_pid(args) -> set:
    pids = set()
    if args.game_pid:
        pids.add(int(args.game_pid))
    if args.game_pid_file:
        try:
            pids.add(int(Path(args.game_pid_file).read_text().split()[0]))
        except (OSError, ValueError, IndexError):
            pass
    return pids


def own_processes(uid: int) -> dict:
    out = {}
    for entry in os.listdir('/proc'):
        if not entry.isdigit():
            continue
        base = Path('/proc') / entry
        try:
            if base.stat().st_uid != uid:
                continue
            cmdline = [a.decode(errors='replace') for a in (base / 'cmdline').read_bytes().split(b'\0') if a]
            threads = {}
            for tid in os.listdir(base / 'task'):
                try:
                    threads[int(tid)] = frozenset(os.sched_getaffinity(int(tid)))
                except OSError:
                    pass
            out[int(entry)] = {'cmdline': cmdline, 'threads': threads}
        except OSError:
            continue
    return out


def throttling() -> dict:
    try:
        stat = dict(line.split() for line in CGROUP_STAT.read_text().splitlines())
        return {'nr_periods': int(stat['nr_periods']), 'nr_throttled': int(stat['nr_throttled']), 'throttled_usec': int(stat['throttled_usec'])}
    except (OSError, ValueError, KeyError):
        return {}


def effective_cpus() -> frozenset:
    try:
        return parse_cpus(CGROUP_CPUSET.read_text().strip())
    except (OSError, ValueError):
        return frozenset(range(os.cpu_count() or 1))


def apply(changes: dict, critical: set = frozenset()) -> tuple:
    """-> (changed, gone, failed, critical_failed); a thread that exited meanwhile (ESRCH) is not a failure."""
    done = gone = failed = critical_failed = 0
    for tid, cpus in changes.items():
        try:
            os.sched_setaffinity(tid, cpus)
            done += 1
        except ProcessLookupError:
            gone += 1
        except OSError:
            failed += 1
            critical_failed += tid in critical
    return done, gone, failed, critical_failed


def one_pass(args, game_cpus, other_cpus) -> dict:
    uid = os.getuid()
    procs = own_processes(uid)
    asked = read_pid(args)
    games = live_games(procs, asked)
    refused = None
    if args.restore:
        everything = effective_cpus()
        changes = {tid: everything for proc in procs.values() for tid, cur in proc['threads'].items() if cur != everything}
    elif not games:
        changes, refused = {}, f'no live streamer game among {sorted(asked)}: nothing changed (fail closed)'
    else:
        changes = plan(procs, games, args.xvfb_display, game_cpus, other_cpus)
    critical = {tid for pid in games for tid in procs[pid]['threads']}
    done, gone, failed, critical_failed = (0, 0, 0, 0) if args.status or refused else apply(changes, critical)
    xvfb = [pid for pid, p in procs.items() if is_xvfb(p['cmdline'], args.xvfb_display)]
    return {'utc': round(time.time(), 3), 'uid': uid, 'mode': 'restore' if args.restore else 'status' if args.status else 'partition',
            'game_pids': sorted(games), 'asked_pids': sorted(asked), 'xvfb_pids': xvfb, 'game_cpus': sorted(game_cpus), 'other_cpus': sorted(other_cpus),
            'processes': len(procs), 'threads': sum(len(p['threads']) for p in procs.values()), 'to_change': len(changes),
            'changed': done, 'gone': gone, 'failed': failed, 'game_failed': critical_failed, 'refused': refused, 'cgroup': throttling()}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--game-pid', type=int)
    p.add_argument('--game-pid-file')
    p.add_argument('--game-cpus', default=DEFAULT_GAME_CPUS)
    p.add_argument('--other-cpus', default=DEFAULT_OTHER_CPUS)
    p.add_argument('--xvfb-display', default=DEFAULT_DISPLAY)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true')
    mode.add_argument('--interval', type=float, default=0)
    mode.add_argument('--restore', action='store_true')
    mode.add_argument('--status', action='store_true')
    args = p.parse_args(argv)
    game_cpus, other_cpus = parse_cpus(args.game_cpus), parse_cpus(args.other_cpus)
    if game_cpus & other_cpus:
        p.error('--game-cpus and --other-cpus overlap')
    if not (args.restore or args.status or args.game_pid or args.game_pid_file):
        p.error('--game-pid or --game-pid-file is required to partition')
    while True:
        result = one_pass(args, game_cpus, other_cpus)
        print(json.dumps(result), flush=True)
        if result['game_failed']:
            return 1   # a game thread could not be pinned: fail fast in --interval mode too (Kimi's final review)
        if not args.interval or args.restore or args.status or args.once:
            return 1 if result['game_failed'] or (result['refused'] and not args.status) else 0
        time.sleep(max(1.0, args.interval))


if __name__ == '__main__':
    sys.exit(main())
