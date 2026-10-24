"""scripts/streamer_swapchain_refresh.py: the console request file and the flip schedule (no game, fake clock)."""
import importlib.util
import io
import json
import os
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location('streamer_swapchain_refresh', ROOT / 'scripts/streamer_swapchain_refresh.py')
sr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sr)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Recorder:
    def __init__(self, clock, on_send=None):
        self.clock, self.sent, self.on_send = clock, [], on_send

    def send(self, cmd):
        self.sent.append((self.clock.t, cmd))
        if self.on_send:
            self.on_send(self)
        return len(self.sent)


def test_console_request_is_private_valid_and_sequence_grows(tmp_path):
    path = str(tmp_path / 'console.json')
    console = sr.Console(path, clock=lambda: 5.0)          # a frozen clock must still give growing sequences
    a = console.send('r.VSync 1')
    b = console.send('r.VSync 0')
    assert b == a + 1
    doc = json.loads(Path(path).read_text())
    assert doc == {'schema': sr.SCHEMA, 'sequence': b, 'commands': ['r.VSync 0']}
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert sorted(os.listdir(tmp_path)) == ['console.json']        # no temporary file left behind


def test_short_writes_are_completed_and_a_failing_writer_leaves_no_partial_file(tmp_path):
    path = str(tmp_path / 'console.json')

    def dribble(fd, data):                                   # the kernel may accept a few bytes at a time
        for i in range(0, len(data), 7):
            sr._write_all(fd, data[i:i + 7])

    sr.Console(path, write=dribble).send('r.VSync 1')
    assert json.loads(Path(path).read_text())['commands'] == ['r.VSync 1']

    def broken(fd, data):
        os.write(fd, data[:5])
        raise OSError('disk full')

    with pytest.raises(OSError):
        sr.Console(path, write=broken).send('r.VSync 0')
    assert json.loads(Path(path).read_text())['commands'] == ['r.VSync 1']   # the old request is intact
    assert sorted(os.listdir(tmp_path)) == ['console.json']


def test_flips_alternate_on_schedule_and_always_end_on_vsync_0(tmp_path):
    clock = FakeClock()
    rec, out = Recorder(clock), io.StringIO()
    flips = sr.run(rec, 60.0, duration=250.0, stop_file=str(tmp_path / 'stop'), clock=clock, sleep=clock.sleep, out=out)
    assert flips == 4
    assert [c for _, c in rec.sent] == ['r.VSync 1', 'r.VSync 0', 'r.VSync 1', 'r.VSync 0', 'r.VSync 0']
    assert [t - 1000.0 for t, _ in rec.sent[:4]] == pytest.approx([60, 120, 180, 240], abs=1.0)
    events = [json.loads(l)['event'] for l in out.getvalue().splitlines()]
    assert events[0] == 'start' and events[-1] == 'stop' and events.count('flip') == 4


def test_a_clock_jump_gives_one_flip_then_a_full_period(tmp_path):
    clock, jumped = FakeClock(), []
    rec = Recorder(clock)

    def sleep(s):                                            # suspended for five hours right after the first flip
        clock.sleep(s)
        if len(rec.sent) == 1 and not jumped:
            jumped.append(1)
            clock.t += 5 * 3600.0

    sr.run(rec, 60.0, duration=5 * 3600.0 + 150.0, stop_file=str(tmp_path / 'stop'), clock=clock, sleep=sleep,
           out=io.StringIO())
    times = [t - 1000.0 for t, c in rec.sent[:-1]]
    assert times[0] == pytest.approx(60, abs=1.0)
    assert times[1] == pytest.approx(5 * 3600.0 + 61, abs=1.5)     # one flip at wake-up, no burst of 300 flips
    assert times[2] - times[1] == pytest.approx(60, abs=1.5)        # then a full period
    assert len(times) == 3 and rec.sent[-1][1] == 'r.VSync 0'


def test_stop_file_and_stop_callback_end_the_loop_and_restore(tmp_path):
    clock = FakeClock()
    rec = Recorder(clock, lambda r: (tmp_path / 'stop').write_text('') if len(r.sent) == 1 else None)
    assert sr.run(rec, 30.0, stop_file=str(tmp_path / 'stop'), clock=clock, sleep=clock.sleep, out=io.StringIO()) == 1
    assert [c for _, c in rec.sent] == ['r.VSync 1', 'r.VSync 0']
    calls = iter([False, False, True])
    rec2 = Recorder(clock)
    assert sr.run(rec2, 30.0, stop_file=str(tmp_path / 'nope'), clock=clock, sleep=clock.sleep, out=io.StringIO(),
                  stop=lambda: next(calls, True)) == 0
    assert [c for _, c in rec2.sent] == ['r.VSync 0']


def test_restore_is_retried_and_a_persistent_failure_is_raised(tmp_path):
    clock, attempts = FakeClock(), []

    class Flaky:
        def send(self, cmd):
            attempts.append(cmd)
            if len(attempts) < 3:
                raise OSError('busy')
            return len(attempts)

    out = io.StringIO()
    assert sr.run(Flaky(), 30.0, stop_file=str(tmp_path / 'nope'), clock=clock, sleep=clock.sleep, out=out,
                  stop=lambda: True) == 0
    assert attempts == ['r.VSync 0'] * 3
    assert [json.loads(l)['event'] for l in out.getvalue().splitlines()].count('restore_failed') == 2

    class Dead:
        def send(self, cmd):
            raise OSError('gone')

    with pytest.raises(OSError):
        sr.run(Dead(), 30.0, stop_file=str(tmp_path / 'nope'), clock=clock, sleep=clock.sleep, out=io.StringIO(),
               stop=lambda: True)


@pytest.mark.parametrize('period,duration', [(5.0, 0.0), (float('nan'), 0.0), (float('inf'), 0.0), (60.0, float('nan')),
                                             (60.0, -1.0)])
def test_bad_periods_and_durations_are_refused(tmp_path, period, duration):
    with pytest.raises(ValueError):
        sr.run(sr.Console(str(tmp_path / 'c.json')), period, duration, stop_file=str(tmp_path / 'stop'), out=io.StringIO())
    assert not (tmp_path / 'c.json').exists()
