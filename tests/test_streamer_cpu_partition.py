"""scripts/streamer_cpu_partition.py: cpu lists, the X server match and the partition plan (pure; no affinity is changed)."""
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location('streamer_cpu_partition', ROOT / 'scripts/streamer_cpu_partition.py')
cp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cp)


def test_parse_cpus():
    assert cp.parse_cpus('0-5') == frozenset(range(6))
    assert cp.parse_cpus('6-9,30') == frozenset({6, 7, 8, 9, 30})
    assert cp.parse_cpus('3') == frozenset({3})
    for bad in ('', '5-2', '0,,1', '-1', 'a'):
        with pytest.raises(ValueError):
            cp.parse_cpus(bad)


def test_xvfb_match_is_exact_on_the_display():
    assert cp.is_xvfb(['/usr/bin/Xvfb', ':99', '-screen', '0', '1920x1080x24'], ':99')
    assert not cp.is_xvfb(['/usr/bin/Xvfb', ':102', '-screen', '0', '1920x1080x24'], ':99')
    assert not cp.is_xvfb(['ffmpeg', '-f', 'x11grab', '-i', ':99'], ':99') and not cp.is_xvfb([], ':99')


def test_plan_pins_game_and_its_x_server_apart_and_skips_threads_already_placed():
    game, others = cp.parse_cpus('0-5'), cp.parse_cpus('6-9')
    every = frozenset(range(48))
    procs = {100: {'cmdline': ['UnrealEditor-Cmd', 'x.uproject'], 'threads': {100: every, 101: game}},
             200: {'cmdline': ['/usr/bin/Xvfb', ':99'], 'threads': {200: every}},
             300: {'cmdline': ['/usr/bin/Xvfb', ':102'], 'threads': {300: every}},
             400: {'cmdline': ['ffmpeg', '-i', ':99'], 'threads': {400: others, 401: every}}}
    changes = cp.plan(procs, {100}, ':99', game, others)
    assert changes == {100: game, 200: game, 300: others, 401: others}


def test_cli_refuses_overlap_and_a_partition_without_the_game(capsys):
    with pytest.raises(SystemExit):
        cp.main(['--game-pid', '1', '--game-cpus', '0-5', '--other-cpus', '5-9', '--once'])
    with pytest.raises(SystemExit):
        cp.main(['--once'])


def test_live_games_fail_closed_on_stale_or_foreign_pids():
    procs = {100: {'cmdline': ['/x/UnrealEditor-Cmd', 'p.uproject', '-game', '-Sub01StreamerVisual'], 'threads': {}},
             200: {'cmdline': ['/x/UnrealEditor-Cmd', 'p.uproject', '-game'], 'threads': {}},
             300: {'cmdline': ['python3', 'viewer.py'], 'threads': {}}}
    assert cp.live_games(procs, {100}) == {100}
    assert cp.live_games(procs, {200, 300, 999}) == set()  # not the streamer game, not a game, gone (a reused or stale game.pid)


def test_partition_with_a_stale_pid_changes_nothing(capsys):
    """A pid that is not the streamer game: the pass refuses and moves no thread (exit 1)."""
    before = os.sched_getaffinity(0)
    assert cp.main(['--once', '--game-pid', str(os.getpid())]) == 1
    out = capsys.readouterr().out
    assert '"changed": 0' in out and 'fail closed' in out and os.sched_getaffinity(0) == before


def test_status_changes_nothing(capsys):
    """--status reads this test process's own threads and reports the plan without touching any affinity."""
    before = os.sched_getaffinity(0)
    assert cp.main(['--status', '--game-pid', str(os.getpid())]) == 0
    assert os.sched_getaffinity(0) == before
    assert '"mode": "status"' in capsys.readouterr().out


def test_interval_mode_fails_fast_when_a_game_thread_cannot_be_pinned(monkeypatch, capsys):
    """--interval stops with exit 1 on the first pass whose game threads could not be pinned (no endless loop)."""
    monkeypatch.setattr(cp, 'one_pass', lambda *a: {'game_failed': 2, 'refused': None})
    monkeypatch.setattr(cp.time, 'sleep', lambda s: (_ for _ in ()).throw(AssertionError('looped')))
    assert cp.main(['--interval', '10', '--game-pid', '1']) == 1
