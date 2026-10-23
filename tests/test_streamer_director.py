"""Streamer director: ffmpeg argv, layouts, segments, watchdog, voice fallback, restart loop, HTTP.

Nothing here launches ffmpeg, xdotool or a real subprocess: processes are fakes, X lookups go through an
injected `run`, and the FIFO probe reads a fake /proc tree.
"""

import asyncio
import importlib.util
import json
import os
import signal
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("streamer_director", ROOT / "scripts/streamer_director.py")
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)
TOKEN = "operator-credential-test"
AUTH = {"X-Admin-Token": TOKEN}


def make_cfg(tmp_path, **kw):
    return sd.DirectorConfig(streamer_dir=tmp_path / "streamer", **kw)


def value_after(argv, flag, start=0):
    return argv[argv.index(flag, start) + 1]


def run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------- argv

def test_argv_builds_the_character_recording(tmp_path):
    cfg = make_cfg(tmp_path)
    argv = sd.build_ffmpeg_argv(cfg, prefix="sub01-20261023-120000", window_id=0x20000C, voice=True)
    assert argv[0] == "ffmpeg" and "-nostdin" in argv
    # input 0: the game window on :99.0 at 24 fps, by window id
    i0 = argv.index("-i")
    assert argv[i0 + 1] == ":99.0"
    first = argv[:i0]
    assert value_after(first, "-f") == "x11grab" and value_after(first, "-framerate") == "24"
    assert value_after(first, "-window_id") == str(0x20000C) and "-video_size" not in first
    # input 1: the desktop on :102.0, 1920x1080, within 10-24 fps
    i1 = argv.index("-i", i0 + 1)
    second = argv[i0 + 2:i1]
    assert argv[i1 + 1] == ":102.0" and value_after(second, "-video_size") == "1920x1080"
    assert 10 <= int(value_after(second, "-framerate")) <= 24
    # input 2: the voice FIFO as raw PCM
    i2 = argv.index("-i", i1 + 1)
    third = argv[i1 + 2:i2]
    assert argv[i2 + 1] == str(tmp_path / "streamer" / "voice.pcm")
    assert (value_after(third, "-f"), value_after(third, "-ar"), value_after(third, "-ac")) == ("s16le", "48000", "2")
    assert argv.count("-i") == 3 and "anullsrc" not in " ".join(argv)
    # composite: desktop picture-in-picture 480x270 bottom-right over the game
    graph = value_after(argv, "-filter_complex")
    assert "[1:v]scale=480:270" in graph and "overlay=x=W-w-" in graph and ":y=H-h-" in graph
    assert value_after(argv, "-map") == "[vout]" and value_after(argv, "-map", argv.index("-map") + 1) == "[aout]"
    assert graph.endswith(";[2:a]apad[aout]")                  # silence after a voice-server EOF, the track keeps running
    # encoding and segmenting
    assert (value_after(argv, "-c:v"), value_after(argv, "-preset"), value_after(argv, "-crf")) == ("libx264", "veryfast", "23")
    assert value_after(argv, "-r") == "24" and (value_after(argv, "-c:a"), value_after(argv, "-b:a")) == ("aac", "96k")
    assert value_after(argv, "-f", argv.index("-c:a")) == "segment"
    assert value_after(argv, "-segment_time") == "600" and value_after(argv, "-reset_timestamps") == "1"
    assert value_after(argv, "-fflags") == "+flush_packets" and argv.index("-fflags") > argv.index("-c:a")
    assert "frag_keyframe" in value_after(argv, "-segment_format_options")
    assert argv[-1] == str(tmp_path / "streamer" / "recordings" / "sub01-20261023-120000-%03d.mp4")


def test_ffmpeg_runs_in_its_own_session_so_a_group_signal_cannot_hit_it_twice(monkeypatch):
    seen = {}

    async def fake_exec(*argv, **kwargs):
        seen["argv"], seen["kwargs"] = argv, kwargs
        return "proc"

    monkeypatch.setattr(sd.asyncio, "create_subprocess_exec", fake_exec)
    assert run(sd.spawn_ffmpeg(["ffmpeg", "-i", "x"])) == "proc"
    assert seen["argv"] == ("ffmpeg", "-i", "x") and seen["kwargs"]["start_new_session"] is True
    assert seen["kwargs"]["stdin"] == sd.asyncio.subprocess.DEVNULL and seen["kwargs"]["stderr"] == sd.asyncio.subprocess.PIPE


def test_argv_falls_back_to_silence_and_to_the_whole_screen(tmp_path):
    cfg = make_cfg(tmp_path)
    argv = sd.build_ffmpeg_argv(cfg, prefix="sub01-x", window_id=None, voice=False)
    assert "anullsrc" in argv[argv.index("-f", argv.index("-re")) + 3] and "s16le" not in argv
    assert str(cfg.voice_fifo) not in argv           # ffmpeg would block opening a FIFO nobody writes to
    assert "-window_id" not in argv and value_after(argv, "-video_size") == "1920x1080"
    assert argv.count("-i") == 3 and value_after(argv, "-map", argv.index("-map") + 1) == "2:a"
    assert "apad" not in value_after(argv, "-filter_complex")


def test_argv_follows_the_configuration(tmp_path):
    cfg = make_cfg(tmp_path, fps=30, desktop_fps=10, segment_seconds=120, crf=28, preset="fast",
                   audio_bitrate="128k", game_display=":98.0", desktop_display=":101.0", ffmpeg="/opt/ffmpeg")
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, voice=True)
    assert argv[0] == "/opt/ffmpeg" and ":98.0" in argv and ":101.0" in argv
    assert value_after(argv, "-segment_time") == "120" and value_after(argv, "-crf") == "28"
    assert value_after(argv, "-b:a") == "128k" and value_after(argv, "-g") == "60"


@pytest.mark.parametrize("kw", [{"desktop_fps": 9}, {"desktop_fps": 25}, {"fps": 5}, {"segment_seconds": 5},
                                {"crf": 60}, {"preset": "turbo"}, {"game_display": "99"}, {"width": 8}])
def test_config_refuses_out_of_range_values(tmp_path, kw):
    with pytest.raises(ValueError):
        make_cfg(tmp_path, **kw)


# --------------------------------------------------------------- layouts

def test_layout_validation_accepts_only_the_three_names():
    assert [sd.validate_layout(n) for n in ("character", "desktop", "split")] == ["character", "desktop", "split"]
    for bad in (None, "", "Character", "pip", 1, ["character"], {"layout": "character"}, True):
        with pytest.raises(ValueError) as err:
            sd.validate_layout(bad)
        assert "character, desktop, split" in str(err.value)
    assert sd.LIVE_LAYOUT == "character" and [k for k, v in sd.LAYOUTS.items() if v["live"]] == ["character"]


def test_filter_graph_for_every_layout(tmp_path):
    cfg = make_cfg(tmp_path)
    character = sd.build_filter_complex("character", cfg)
    desktop = sd.build_filter_complex("desktop", cfg)
    split = sd.build_filter_complex("split", cfg)
    assert character.startswith("[0:v]") and "[1:v]scale=480:270" in character
    assert desktop.startswith("[1:v]") and "[0:v]scale=480:270" in desktop
    assert "hstack" in split and "scale=960:540" in split
    assert all(g.endswith("[vout]") for g in (character, desktop, split))
    with pytest.raises(ValueError):
        sd.build_filter_complex("sideways", cfg)


# -------------------------------------------------------------- segments

def test_list_segments_reads_only_recording_files_in_order(tmp_path):
    d = tmp_path / "rec"
    d.mkdir()
    for name, size in [("sub01-20261023-120000-001.mp4", 30), ("sub01-20261023-120000-000.mp4", 10),
                       ("sub01-20261023-130000-000.mp4", 20), ("notes.txt", 5), ("sub01-bad-000.mp4", 5),
                       ("sub01-20261023-120000-000.mp4.tmp", 5)]:
        (d / name).write_bytes(b"x" * size)
    (d / "sub01-20261023-140000-000.mp4").mkdir()           # a directory is not a segment
    got = sd.list_segments(d)
    assert [s["name"] for s in got] == ["sub01-20261023-120000-000.mp4", "sub01-20261023-120000-001.mp4",
                                        "sub01-20261023-130000-000.mp4"]
    assert [s["bytes"] for s in got] == [10, 30, 20] and got[0]["run"] == "sub01-20261023-120000"
    assert got[1]["index"] == 1 and got[0]["mtime"].endswith("Z")
    assert sd.run_bytes(got, "sub01-20261023-120000") == 40
    assert sd.list_segments(tmp_path / "missing") == []


def test_every_launch_gets_a_prefix_no_segment_uses(tmp_path):
    d = tmp_path / "rec"
    d.mkdir()
    t = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
    assert sd.unique_prefix(d, t) == "sub01-20261023-120000"
    (d / "sub01-20261023-120000-000.mp4").write_bytes(b"x")
    (d / "sub01-20261023-120001-004.mp4").write_bytes(b"x")
    assert sd.unique_prefix(d, t) == "sub01-20261023-120002"
    assert sd.unique_prefix(tmp_path / "none", t) == "sub01-20261023-120000"


# -------------------------------------------------------------- watchdog

def test_watchdog_waits_then_restarts_after_two_checks_without_growth():
    f = sd.watchdog_decision
    assert f(0, 0, 0, alive=False, uptime=500) == ("down", 0)
    assert f(0, 0, 0, alive=True, uptime=20) == ("grace", 0)                  # still starting
    assert f(100, 900, 1, alive=True, uptime=100) == ("ok", 0)                # growth clears the count
    assert f(900, 900, 0, alive=True, uptime=100) == ("stalled", 1)
    assert f(900, 900, 1, alive=True, uptime=130) == ("restart", 2)
    assert f(900, 900, 0, alive=True, uptime=100, limit=1) == ("restart", 1)


def test_voice_decision_is_debounced_and_not_flapping():
    f = sd.voice_decision
    assert f(False, False, 3, uptime=500) == ("keep", 0)
    assert f(False, True, 0, uptime=500) == ("wait", 1)
    assert f(False, True, 1, uptime=500) == ("switch", 2)
    assert f(False, True, 5, uptime=10) == ("wait", 6)                         # just started: no restart loop
    assert f(True, True, 0, uptime=500) == ("keep", 0)
    assert f(True, False, 0, uptime=500) == ("keep", 0)                        # writer gone: apad records silence, no relaunch
    # the writer vanished once and is back, but this run's audio input already hit EOF: relaunch with voice
    assert f(True, True, 0, uptime=500, gap=True) == ("switch", 0)
    assert f(True, True, 0, uptime=10, gap=True) == ("wait", 0)


def test_backoff_grows_and_caps():
    assert [sd.backoff_delay(n) for n in (0, 1, 2, 3, 6, 50)] == [1.0, 2.0, 4.0, 8.0, 60.0, 60.0]


# -------------------------------------------------------------- the FIFO

def fake_proc(root, pid, fd, target, flags):
    (root / str(pid) / "fd").mkdir(parents=True, exist_ok=True)
    (root / str(pid) / "fdinfo").mkdir(parents=True, exist_ok=True)
    os.symlink(target, root / str(pid) / "fd" / str(fd))
    (root / str(pid) / "fdinfo" / str(fd)).write_text(f"pos:\t0\nflags:\t{flags}\nmnt_id:\t1\n")


def test_voice_tap_needs_a_fifo_with_a_writer(tmp_path):
    fifo, proc = tmp_path / "voice.pcm", tmp_path / "proc"
    proc.mkdir()
    absent = sd.VoiceTap(fifo, proc, create=False)
    assert absent.writer_present(settle=0) == (False, "voice FIFO does not exist") and not fifo.exists()
    fifo.write_bytes(b"")
    assert sd.VoiceTap(fifo, proc, create=False).writer_present(settle=0) == (False, "voice path is not a FIFO")
    fifo.unlink()
    tap = sd.VoiceTap(fifo, proc)                                  # creates the FIFO like the voice server would
    assert tap.writer_present(settle=0)[0] is False and fifo.is_fifo() and oct(fifo.stat().st_mode & 0o777) == "0o600"
    fake_proc(proc, 11, 5, fifo, "0100000")                        # a reader (ffmpeg itself) is not a writer
    other = tmp_path / "other"
    other.write_bytes(b"")
    fake_proc(proc, 12, 3, other, "0100001")                       # a writer of some other file
    assert tap.writer_present(settle=0)[0] is False
    fake_proc(proc, 13, 7, fifo, "0100001")                        # O_WRONLY|O_LARGEFILE
    assert tap.writer_present(settle=0) == (True, "writer present")
    tap.close()


def test_voice_tap_counts_a_read_write_holder_and_waits_out_the_settle_time(tmp_path):
    fifo, proc = tmp_path / "voice.pcm", tmp_path / "proc"
    proc.mkdir()
    now = [0.0]
    sleeps = []
    tap = sd.VoiceTap(fifo, proc, clock=lambda: now[0], sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)))
    assert tap.writer_present(settle=0.5) == (False, "no process writes to the voice FIFO")
    assert 0.4 <= sum(sleeps) <= 0.6                              # polled for the settle time, then gave up
    sleeps.clear()
    fake_proc(proc, 20, 4, fifo, "0100002")                       # O_RDWR
    assert tap.writer_present(settle=5)[0] is True and sleeps == []
    tap.close()
    assert sd.VoiceTap(fifo, tmp_path / "no-proc").writer_present(settle=0)[0] is False


def test_voice_tap_works_with_a_writer_that_only_attaches_while_a_reader_exists(tmp_path):
    """The voice server opens O_WRONLY|O_NONBLOCK: ENXIO without a reader. The tap is that reader."""
    fifo = tmp_path / "voice.pcm"
    os.mkfifo(fifo)
    with pytest.raises(OSError) as err:
        os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    assert err.value.errno == 6                                    # ENXIO: nobody to deliver to, so nothing to see
    tap = sd.VoiceTap(fifo)
    assert tap.writer_present(settle=0)[0] is False
    writer = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)            # attaches now that the tap reads
    try:
        assert tap.writer_present(settle=0) == (True, "writer present")      # real /proc: this process holds it
        os.write(writer, b"\0" * 4000)
        assert tap.drain() == 4000 and tap.drain() == 0
    finally:
        os.close(writer)
    assert tap.writer_present(settle=0)[0] is False
    fifo.unlink()                                                  # replaced file: the tap follows the new FIFO
    os.mkfifo(fifo)
    old = tap.ident
    assert tap.writer_present(settle=0)[0] is False and tap.ident != old
    tap.close()
    assert tap.fd is None and tap.drain() == 0


# ------------------------------------------------------------ game window

class XdotoolFake:
    def __init__(self, windows, search_out=None):
        self.windows, self.calls, self.search_out = windows, [], search_out

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw["env"]["DISPLAY"]))
        verb = argv[1]
        out = ""
        if verb == "search":
            out = self.search_out if self.search_out is not None else "\n".join(str(i) for i in self.windows)
        elif verb == "getwindowname":
            out = self.windows[int(argv[2])][0] + "\n"
        elif verb == "getwindowgeometry":
            w, h = self.windows[int(argv[3])][1:]
            out = f"WINDOW={argv[3]}\nX=0\nY=0\nWIDTH={w}\nHEIGHT={h}\nSCREEN=0\n"
        return type("Done", (), {"returncode": 0, "stdout": out})()


def test_game_window_is_the_biggest_one_named_sub01homelab_of_the_pid(tmp_path):
    cfg = make_cfg(tmp_path, game_pid=4321)
    fake = XdotoolFake({101: ("Sub01HomeLab (64-bit)", 1920, 1080), 102: ("Sub01HomeLab splash", 400, 300),
                        103: ("Unreal helper", 2000, 2000)})
    assert sd.find_game_window(cfg, run=fake) == (101, "window 'Sub01HomeLab (64-bit)'")
    assert fake.calls[0] == (["xdotool", "search", "--pid", "4321"], ":99")
    pid_file = tmp_path / "game.pid"
    pid_file.write_text("77\n")
    cfg = make_cfg(tmp_path, game_pid_file=pid_file)
    fake = XdotoolFake({5: ("Sub01HomeLab", 1920, 1080)})
    assert sd.find_game_window(cfg, run=fake)[0] == 5 and fake.calls[0][0][2:] == ["--pid", "77"]


def test_game_window_lookup_by_name_and_failures(tmp_path):
    cfg = make_cfg(tmp_path)
    fake = XdotoolFake({9: ("Sub01HomeLab", 1920, 1080)})
    assert sd.find_game_window(cfg, run=fake)[0] == 9 and fake.calls[0][0][1:3] == ["search", "--name"]
    none_found = XdotoolFake({}, search_out="")
    window, note = sd.find_game_window(cfg, run=none_found)
    assert window is None and "no window named Sub01HomeLab" in note
    assert sd.find_game_window(make_cfg(tmp_path, window_id=0x20000C), run=none_found) == (0x20000C, "fixed by --window-id")

    def missing(argv, **kw):
        raise FileNotFoundError("xdotool")
    window, note = sd.find_game_window(cfg, run=missing)
    assert window is None and "xdotool unavailable" in note


# ----------------------------------------------------------- fake ffmpeg

class FakeStream:
    def __init__(self, lines):
        self.lines = [line.encode() + b"\n" for line in lines]

    async def readline(self):
        return self.lines.pop(0) if self.lines else b""


class FakeProc:
    def __init__(self, pid, exit_after=None, code=0, stderr=()):
        self.pid, self.returncode, self.signals = pid, None, []
        self._done = asyncio.Event()
        self.stderr = FakeStream(stderr)
        if exit_after is not None:
            asyncio.get_running_loop().call_later(exit_after, self._exit, code)

    def _exit(self, code):
        if self.returncode is None:
            self.returncode = code
            self._done.set()

    async def wait(self):
        await self._done.wait()
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self._exit(255 if sig == signal.SIGINT else -sig)

    def kill(self):
        self.signals.append(signal.SIGKILL)
        self._exit(-9)


def make_director(tmp_path, procs, voice=(False, "no writer"), **cfg_kw):
    """A Director whose ffmpeg is fake: `procs` is a list of factories, one per launch."""
    cfg = make_cfg(tmp_path, **cfg_kw)
    launched = []

    async def spawn(argv):
        proc = procs[len(launched)]()
        launched.append((argv, proc))
        return proc

    async def quick_sleep(seconds):
        await asyncio.sleep(0.01 if seconds < 5 else 0.05)

    director = sd.Director(cfg, spawn=spawn, find_window=lambda: (0x20000C, "fixed"),
                           check_voice=lambda: voice, sleep=quick_sleep)
    return director, launched


async def until(predicate, timeout=5.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end, "condition never became true"
        await asyncio.sleep(0.01)


def test_director_restarts_ffmpeg_when_it_exits_and_reports_why(tmp_path):
    async def body():
        director, launched = make_director(tmp_path, [
            lambda: FakeProc(501, exit_after=0.05, code=1, stderr=["Cannot open display :99.0"]),
            lambda: FakeProc(502)])
        task = asyncio.ensure_future(director.run())
        await until(lambda: len(launched) == 2 and director.alive)
        state = director.state()
        assert state["recording"] is True and state["ffmpeg_pid"] == 502 and state["restarts"] == 1
        assert "code 1" in state["last_error"] and "Cannot open display" in state["last_error"]
        assert state["voice"] is False and state["game_source"] == "window:0x20000c" and state["layout"] == "character"
        assert state["since"].endswith("Z") and state["segments"] == []
        first_argv = launched[0][0]
        assert "anullsrc=channel_layout=stereo:sample_rate=48000" in first_argv
        assert value_after(first_argv, "-window_id") == str(0x20000C)
        events = [json.loads(line) for line in (tmp_path / "streamer" / "events.jsonl").read_text().splitlines()]
        assert [e["kind"] for e in events if e["kind"].startswith("ffmpeg_")][:3] == [
            "ffmpeg_started", "ffmpeg_exited", "ffmpeg_restart_scheduled"]
        assert all(e["source"] == "director" for e in events)
        director.stop()
        await asyncio.wait_for(task, 5)
        assert launched[1][1].signals == [signal.SIGINT] and not director.alive      # finalised, not killed
    run(body())


def test_director_without_a_window_records_the_screen_and_uses_the_voice_when_present(tmp_path):
    async def body():
        director, launched = make_director(tmp_path, [lambda: FakeProc(7)], voice=(True, "writer present"))
        director._find_window = lambda: (None, "no window named Sub01HomeLab* on :99")
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        argv = launched[0][0]
        assert "-window_id" not in argv and str(director.cfg.voice_fifo) in argv
        state = director.state()
        assert state["game_source"] == "screen" and "no window named" in state["game_note"] and state["voice"] is True
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_a_hung_ffmpeg_is_killed_when_sigint_is_ignored(tmp_path):
    async def body():
        class Stubborn(FakeProc):
            def send_signal(self, sig):
                self.signals.append(sig)               # ignores SIGINT

        director, launched = make_director(tmp_path, [lambda: Stubborn(9)])
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        proc = launched[0][1]
        terminate = asyncio.ensure_future(director._terminate(proc, grace=0.05))
        await asyncio.wait_for(terminate, 5)
        assert proc.signals == [signal.SIGINT, signal.SIGKILL] and proc.returncode == -9
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_watchdog_tick_restarts_a_recording_that_stopped_growing(tmp_path):
    async def body():
        now = [1000.0]
        director, _ = make_director(tmp_path, [lambda: FakeProc(1)])
        director._clock = lambda: now[0]
        director.proc, director.prefix, director.started_mono = FakeProc(1), "sub01-20261023-120000", 1000.0
        rec = director.cfg.recordings_dir
        rec.mkdir(parents=True)
        segment = rec / "sub01-20261023-120000-000.mp4"
        segment.write_bytes(b"x" * 100)
        now[0] += 30
        assert await director.watchdog_tick() == "grace"
        now[0] += 60
        segment.write_bytes(b"x" * 500)
        assert await director.watchdog_tick() == "ok"
        now[0] += 30
        assert await director.watchdog_tick() == "stalled" and director.state()["recording"] is False
        assert director._restart_reason is None
        now[0] += 30
        assert await director.watchdog_tick() == "restart"
        assert director._restart_reason == "segment growth stalled"
        assert "did not grow" in director.last_error
        segment.write_bytes(b"x" * 900)                     # growth after a restart request clears the count
        assert await director.watchdog_tick() == "ok" and director.stalled_checks == 0
    run(body())


def test_voice_tick_restarts_ffmpeg_once_the_voice_server_connects(tmp_path):
    async def body():
        now = [1000.0]
        available = [(False, "no writer")]
        director, _ = make_director(tmp_path, [lambda: FakeProc(1)])
        director._check_voice = lambda: available[0]
        director._clock = lambda: now[0]
        director.proc, director.voice, director.started_mono = FakeProc(1), False, 1000.0
        now[0] += 100
        assert await director.voice_tick() == "keep"
        available[0] = (True, "writer present")
        assert await director.voice_tick() == "wait" and director._restart_reason is None
        assert await director.voice_tick() == "switch" and director._restart_reason == "voice came online"
    run(body())


def test_voice_tick_relaunches_a_run_whose_voice_writer_vanished_and_came_back(tmp_path):
    async def body():
        now = [1000.0]
        available = [(True, "writer present")]
        director, _ = make_director(tmp_path, [lambda: FakeProc(1)])
        director._check_voice = lambda: available[0]
        director._clock = lambda: now[0]
        director.proc, director.voice, director.started_mono = FakeProc(1), True, 1000.0
        now[0] += 100
        assert await director.voice_tick() == "keep" and director.voice_gap is False
        available[0] = (False, "gone")
        assert await director.voice_tick() == "keep" and director.voice_gap is True and director._restart_reason is None
        assert await director.voice_tick() == "keep"                      # absent for good: silence, no restart loop
        available[0] = (True, "back")                      # ffmpeg read EOF in between: its audio is dead
        assert await director.voice_tick() == "switch" and director._restart_reason == "voice reconnected"
    run(body())


def test_the_director_drains_the_fifo_only_while_ffmpeg_is_not_reading_it(tmp_path):
    async def body():
        director, _ = make_director(tmp_path, [lambda: FakeProc(1)])
        drained = []
        director.tap.drain = lambda: drained.append(1)
        await director.drain_tick()
        assert drained == [1]                                     # nothing running: the director is the reader
        director.proc, director.voice = FakeProc(1), True
        await director.drain_tick()
        assert drained == [1]                                     # ffmpeg reads the voice: hands off
        director.voice = False
        await director.drain_tick()
        assert drained == [1, 1]                                  # a silent run does not read it
    run(body())


async def started(tmp_path):
    director, launched = make_director(tmp_path, [lambda: FakeProc(42)])
    http = TestClient(TestServer(sd.create_app(director, TOKEN)))
    await http.start_server()
    return http, director


def test_every_route_but_health_needs_the_operator_credential(tmp_path):
    async def body():
        http, director = await started(tmp_path)
        try:
            assert (await http.get("/healthz")).status == 200
            for method, path in [("get", "/director/state"), ("post", "/director/layout")]:
                assert (await getattr(http, method)(path)).status == 403
                assert (await getattr(http, method)(path, headers={"X-Admin-Token": "wrong-credential-x"})).status == 403
            assert director.layout == "character" and not (tmp_path / "streamer" / "layout.jsonl").exists()
        finally:
            await http.close()
    run(body())


def test_state_route_has_the_documented_fields(tmp_path):
    async def body():
        http, director = await started(tmp_path)
        try:
            rec = director.cfg.recordings_dir
            rec.mkdir(parents=True)
            (rec / "sub01-20261023-120000-000.mp4").write_bytes(b"x" * 1234)
            state = await (await http.get("/director/state", headers=AUTH)).json()
            for key in ("recording", "since", "segments", "ffmpeg_pid", "restarts", "last_error", "layout"):
                assert key in state
            assert state["recording"] is False and state["ffmpeg_pid"] is None and state["restarts"] == 0
            assert state["segments"] == [{"name": "sub01-20261023-120000-000.mp4", "bytes": 1234,
                                          "mtime": state["segments"][0]["mtime"]}]
            assert (await (await http.get("/healthz")).json()) == {"ok": True, "recording": False}
        finally:
            await http.close()
    run(body())


def test_layout_requests_are_validated_and_logged_to_layout_jsonl(tmp_path):
    async def body():
        http, director = await started(tmp_path)
        log = tmp_path / "streamer" / "layout.jsonl"
        try:
            r = await http.post("/director/layout", json={"layout": "desktop"}, headers=AUTH)
            body_ = await r.json()
            assert r.status == 200 and body_["layout"] == "desktop" and body_["live_layout"] == "character"
            assert body_["live"] is False and body_["logged"]["previous"] == "character"
            await http.post("/director/layout", json={"layout": "split"}, headers=AUTH)
            await http.post("/director/layout", json={"layout": "split"}, headers=AUTH)       # every call is logged
            for bad in ({"layout": "pip"}, {"layout": 3}, {}, {"Layout": "desktop"}):
                assert (await http.post("/director/layout", json=bad, headers=AUTH)).status == 400
            assert (await http.post("/director/layout", data=b"[]", headers=AUTH)).status == 400
            assert (await http.post("/director/layout", data=b"{nope", headers=AUTH)).status == 400
            assert (await http.post("/director/layout", data=b"x" * 2000, headers=AUTH)).status == 413
            lines = [json.loads(line) for line in log.read_text().splitlines()]
            assert [line["layout"] for line in lines] == ["desktop", "split", "split"]
            assert [line["previous"] for line in lines] == ["character", "desktop", "split"]
            assert all({"t", "unix", "layout", "previous", "run", "offset_s", "recording"} <= set(line) for line in lines)
            state = await (await http.get("/director/state", headers=AUTH)).json()
            assert state["layout"] == "split" and state["live_layout"] == "character"
        finally:
            await http.close()
    run(body())


def test_layout_log_records_the_position_in_the_running_recording(tmp_path):
    director, _ = make_director(tmp_path, [lambda: None])
    now = [500.0]
    director._clock = lambda: now[0]
    director.proc, director.prefix, director.started_mono = type("P", (), {"pid": 1, "returncode": None})(), "sub01-r", 480.0
    record = director.set_layout("desktop")
    assert record["run"] == "sub01-r" and record["offset_s"] == 20.0 and record["recording"] is True


def test_the_app_refuses_a_short_credential_and_the_cli_refuses_non_loopback(tmp_path):
    director, _ = make_director(tmp_path, [lambda: None])
    with pytest.raises(ValueError):
        sd.create_app(director, "short")
    with pytest.raises(SystemExit):
        sd.parse_args(["--host", "0.0.0.0", "--streamer-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        sd.parse_args(["--desktop-fps", "30", "--streamer-dir", str(tmp_path)])
    args, cfg = sd.parse_args(["--streamer-dir", str(tmp_path), "--window-id", "0x20000c", "--size", "1280x720"])
    assert args.port == 8837 and cfg.window_id == 0x20000C and (cfg.width, cfg.height) == (1280, 720)
    assert cfg.recordings_dir == tmp_path / "recordings" and cfg.voice_fifo == tmp_path / "voice.pcm"


def test_print_argv_shows_the_command_without_running_it(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sd, "find_game_window", lambda cfg: (0x20000C, "fixed"))
    monkeypatch.setattr(sd.VoiceTap, "writer_present", lambda self, settle=None: (False, "no process writes to the voice FIFO"))
    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch anything"))
    assert sd.main(["--print-argv", "--streamer-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "voice: False" in out and "-window_id 2097164" in out and "anullsrc" in out and "x11grab" in out
