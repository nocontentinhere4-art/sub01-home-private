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

def test_layout_validation_accepts_the_five_layouts_and_the_v1_name():
    # v2: `character` (v1) is the webcam layout; `room` is new (cam2); `webcam_only` is the privacy layout (no PiP)
    assert [sd.validate_layout(n) for n in ("character", "webcam", "desktop", "split", "room", "webcam_only")] == [
        "webcam", "webcam", "desktop", "split", "room", "webcam_only"]
    for bad in (None, "", "Character", "pip", 1, ["character"], {"layout": "character"}, True):
        with pytest.raises(ValueError) as err:
            sd.validate_layout(bad)
        assert "webcam, desktop, split, room, webcam_only (character = webcam)" in str(err.value)
    assert sd.DEFAULT_LAYOUT == "webcam" and sd.LIVE_ORDER == ("webcam", "desktop", "split", "room", "webcam_only")
    assert [n for n, spec in sd.LAYOUTS.items() if not spec["desktop"]] == ["webcam_only"]   # room sees the monitor


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


def test_window_speed_and_speed_decision():
    assert sd.window_speed((100.0, 10.0), (130.0, 31.0)) == 0.7
    assert sd.window_speed(None, (130.0, 31.0)) is None and sd.window_speed((130.0, 1.0), (130.0, 2.0)) is None
    assert sd.window_speed((100.0, None), (130.0, 31.0)) is None
    f = sd.speed_decision
    assert f(0.5, 2, uptime=20, since_restart=None) == ("grace", 0)
    assert f(None, 2, uptime=500, since_restart=None) == ("unknown", 0)
    checks, actions = 0, []
    for speed in (0.7, None, 0.7, None, 0.7):                           # never 3 slow checks in a row: no relaunch
        action, checks = f(speed, checks, uptime=500, since_restart=None)
        actions.append(action)
    assert actions == ["slow", "unknown", "slow", "unknown", "slow"] and checks == 1
    assert f(1.01, 2, uptime=500, since_restart=None) == ("ok", 0)
    assert f(0.7, 0, uptime=500, since_restart=None) == ("slow", 1)
    assert f(0.7, 2, uptime=500, since_restart=None) == ("restart", 3)
    assert f(0.7, 2, uptime=500, since_restart=120.0) == ("held", 3)          # one relaunch for slowness per 10 min
    assert f(0.7, 2, uptime=500, since_restart=700.0) == ("restart", 3)


def test_watchdog_tick_relaunches_a_run_below_real_time(tmp_path):
    async def body():
        now = [1000.0]
        director, _ = make_director(tmp_path, [lambda: FakeProc(1)])
        director._clock = lambda: now[0]
        director.proc, director.prefix, director.started_mono = FakeProc(1), "sub01-20261023-120000", 1000.0
        director.meter = sd.OutputMeter(600)
        rec = director.cfg.recordings_dir
        rec.mkdir(parents=True)
        segment = rec / "sub01-20261023-120000-000.mp4"
        out = [0.0]

        async def tick(media_gain):
            now[0] += 30
            out[0] += media_gain
            segment.write_bytes(b"x" * int(1000 + now[0]))        # growing: the stall rule stays quiet
            director.meter._last = (now[0], 0, out[0], 0, 0)
            return await director.watchdog_tick()

        await tick(30)                                             # grace
        await tick(30)
        assert director.window_speed == 1.0 and director.slow_checks == 0
        await tick(21)
        await tick(21)
        assert director.slow_checks == 2 and director._restart_reason is None
        await tick(21)
        assert director._restart_reason == "output below real time" and "0.7x" in director.last_error
        assert director.state()["window_speed"] == 0.7
        director._restart_reason = None
        for _ in range(3):                                         # still slow right after: held, no relaunch loop
            await tick(21)
        assert director._restart_reason is None and director.slow_checks == 6
    run(body())


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
        assert state["voice"] is False and state["game_source"] == "window:0x20000c" and state["layout"] == "webcam"
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
            assert director.layout == "webcam" and not (tmp_path / "streamer" / "layout.jsonl").exists()
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
            assert r.status == 200 and body_["layout"] == "desktop" and body_["live_layout"] is None    # not recording
            assert body_["live"] is True and body_["logged"]["previous"] == "webcam"
            await http.post("/director/layout", json={"layout": "split"}, headers=AUTH)
            await http.post("/director/layout", json={"layout": "split"}, headers=AUTH)       # every call is logged
            for bad in ({"layout": "pip"}, {"layout": 3}, {}, {"Layout": "desktop"}):
                assert (await http.post("/director/layout", json=bad, headers=AUTH)).status == 400
            assert (await http.post("/director/layout", data=b"[]", headers=AUTH)).status == 400
            assert (await http.post("/director/layout", data=b"{nope", headers=AUTH)).status == 400
            assert (await http.post("/director/layout", data=b"x" * 2000, headers=AUTH)).status == 413
            lines = [json.loads(line) for line in log.read_text().splitlines()]
            assert [line["layout"] for line in lines] == ["desktop", "split", "split"]
            assert [line["previous"] for line in lines] == ["webcam", "desktop", "split"]
            assert all({"t", "unix", "layout", "previous", "run", "offset_s", "recording"} <= set(line) for line in lines)
            state = await (await http.get("/director/state", headers=AUTH)).json()
            assert state["layout"] == "split" and state["live_layout"] is None
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


# =====================================================================================================================
# v2 (director worker, 2026-10-23): 60 fps, NVENC with probe fallback, cam2 + layouts webcam/room/desktop/split,
# live switching through ffmpeg's stdin command channel, HLS/RTMP through the tee muxer, the output fps meter,
# the loopback HLS server, and two real ffmpeg smoke tests on lavfi test sources (skipped without ffmpeg).
# =====================================================================================================================

import re
import shutil
import subprocess
import time

hls_spec = importlib.util.spec_from_file_location("streamer_hls_serve", ROOT / "scripts/streamer_hls_serve.py")
hls_serve = importlib.util.module_from_spec(hls_spec)
hls_spec.loader.exec_module(hls_serve)
FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")
RTMP = "rtmp://203.0.113.7/live/sk_live_0123456789abcdef"     # documentation address, fake stream key


def inputs_of(argv):
    """[(options before -i, value of -i)] for every input of an ffmpeg argv."""
    out, start = [], 0
    for i, arg in enumerate(argv):
        if arg == "-i":
            out.append((argv[start:i], argv[i + 1]))
            start = i + 2
    return out


def test_v2_argv_60fps_nvenc_cam2_and_hls_tee(tmp_path):
    hls = tmp_path / "hls"
    cfg = make_cfg(tmp_path, fps=60, desktop_fps=60, encoder="h264_nvenc", hls_dir=hls)
    argv = sd.build_ffmpeg_argv(cfg, prefix="sub01-20261023-210000", window_id=0x20000C, voice=True, cam2=True,
                                layout="room", live=True, encoder="h264_nvenc", cam2_fps=60)
    assert "-stdin" in argv and "-nostdin" not in argv                      # the live switch channel
    assert value_after(argv, "-progress") == "pipe:1" and value_after(argv, "-stats_period") == "5"
    (game, gi), (desk, di), (voice, vi), (cam, ci) = inputs_of(argv)
    assert gi == ":99.0" and value_after(game, "-framerate") == "60" and value_after(game, "-window_id") == str(0x20000C)
    assert di == ":102.0" and value_after(desk, "-framerate") == "60"
    assert vi == str(tmp_path / "streamer" / "voice.pcm")
    assert ci == str(tmp_path / "streamer" / "cam2.mjpeg") and value_after(cam, "-f") == "mjpeg"
    assert value_after(cam, "-use_wallclock_as_timestamps") == "1" and value_after(cam, "-framerate") == "60"
    graph = value_after(argv, "-filter_complex")
    assert set(re.findall(r"\bfps=(\d+)", graph)) == {"60"}                # nothing resampled below 60
    assert "[3:v]" in graph and "tpad=stop=-1:stop_mode=clone" in graph     # a cam2 EOF repeats its last frame
    assert "[lwebcam][ldesktop][lsplit][lroom][lwebcam_only]streamselect@layout=inputs=5:map=3," in graph and graph.endswith(
        ";[2:a]apad[aout]")
    assert graph.count("overlay=") == 3 and "hstack=inputs=2" in graph
    # NVENC, consistent rate and GOP
    assert (value_after(argv, "-c:v"), value_after(argv, "-preset"), value_after(argv, "-tune")) == ("h264_nvenc", "p4", "ll")
    assert (value_after(argv, "-rc"), value_after(argv, "-cq"), value_after(argv, "-b:v"), value_after(argv, "-bf")) == (
        "vbr", "23", "0", "2")
    assert (value_after(argv, "-r"), value_after(argv, "-g"), value_after(argv, "-pix_fmt")) == ("60", "120", "yuv420p")
    assert "-crf" not in argv
    # one encode, two outputs through tee
    assert value_after(argv, "-f", argv.index("-c:a")) == "tee" and value_after(argv, "-flags") == "+global_header"
    rec_branch, hls_branch = argv[-1].split("|")
    assert rec_branch.startswith("[f=segment:segment_time=600:reset_timestamps=1:segment_format=mp4:")
    assert "frag_keyframe" in rec_branch and "fflags=+flush_packets" in rec_branch
    assert rec_branch.endswith("]" + str(tmp_path / "streamer" / "recordings" / "sub01-20261023-210000-%03d.mp4"))
    assert hls_branch.startswith("[f=hls:onfail=ignore:hls_time=4:hls_list_size=6:hls_flags=delete_segments+")
    assert "omit_endlist" in hls_branch and "hls_start_number_source=epoch" in hls_branch
    assert f"hls_segment_filename={hls}/sub01-20261023-210000-%d.ts]{hls}/live.m3u8" in hls_branch
    # the third branch: RTMP behind a dropping fifo; ':' inside fifo_options escaped for both tee levels
    rtmp_cfg = make_cfg(tmp_path, fps=60, desktop_fps=60, rtmp_url=RTMP)
    branches = sd.build_ffmpeg_argv(rtmp_cfg, prefix="p", live=True)[-1].split("|")
    assert len(branches) == 2 and branches[1].startswith("[f=flv:onfail=ignore:use_fifo=1:fifo_options=drop_pkts_on_overflow=1\\\\:")
    assert branches[1].endswith("]" + RTMP) and RTMP not in repr(rtmp_cfg)


def test_v2_live_graph_without_cam2_and_the_restart_mode_graph(tmp_path):
    cfg = make_cfg(tmp_path, fps=30, desktop_fps=30)
    for layout, index in (("webcam", 0), ("character", 0), ("desktop", 1), ("split", 2), ("room", 0), ("webcam_only", 3)):
        argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, cam2=False, layout=layout, live=True)
        graph = value_after(argv, "-filter_complex")
        assert f"[lwebcam][ldesktop][lsplit][lwebcam_only]streamselect@layout=inputs=4:map={index}," in graph   # room -> webcam
        assert "[3:v]" not in graph and argv.count("-i") == 3 and "mjpeg" not in argv
    # restart mode: one layout per launch, stdin closed as in v1
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, cam2=True, layout="room", live=False)
    graph = value_after(argv, "-filter_complex")
    assert "-nostdin" in argv and "streamselect" not in graph and argv.count("-i") == 4
    assert graph.startswith("[3:v]scale=1920:1080:flags=bilinear:in_range=full:out_range=limited,setsar=1,fps=30,tpad=")
    assert "[0:v]scale=480:270" in graph
    assert sd.build_filter_complex("webcam", cfg) == sd.build_filter_complex("character", cfg)
    assert sd.effective_layout("room", False) == "webcam" and sd.effective_layout("room", True) == "room"
    assert sd.live_order(False) == ("webcam", "desktop", "split", "webcam_only")
    assert sd.live_order(True) == ("webcam", "desktop", "split", "room", "webcam_only")


@pytest.mark.parametrize("kw", [{"fps": 121}, {"fps": 9}, {"fps": 60, "desktop_fps": 61}, {"fps": 24, "desktop_fps": 30},
                                {"encoder": "nvenc"}, {"layout": "bogus"}, {"layout_switch": "hot"},
                                {"rtmp_url": "http://203.0.113.7/live/key"}, {"rtmp_url": "rtmp://h/app/a key"},
                                {"rtmp_url": "rtmp://h/a|b"}, {"hls_dir": "/tmp/a|b"}, {"hls_dir": "/tmp/a:b"},
                                {"hls_dir": "/tmp/a b"}, {"switch_timeout": 0}, {"test_seconds": -1}])
def test_v2_config_refuses_bad_values(tmp_path, kw):
    with pytest.raises(ValueError) as err:
        make_cfg(tmp_path, **kw)
    assert "key" not in str(err.value) and "203.0.113.7" not in str(err.value)      # never echoes the URL


def test_v2_config_and_cli_accept_the_pod_profile(tmp_path):
    cfg = make_cfg(tmp_path, fps=120, desktop_fps=60, layout="character", encoder="hevc_nvenc")
    assert (cfg.fps, cfg.desktop_fps, cfg.layout, cfg.encoder) == (120, 60, "webcam", "hevc_nvenc")
    args, cfg = sd.parse_args(["--streamer-dir", str(tmp_path), "--fps", "60", "--desktop-fps", "60", "--encoder",
                               "h264_nvenc", "--hls-dir", str(tmp_path / "hls")])
    assert (cfg.fps, cfg.desktop_fps, cfg.encoder, cfg.hls_dir, cfg.layout, cfg.layout_switch) == (
        60, 60, "h264_nvenc", tmp_path / "hls", None, "live")
    _, cfg = sd.parse_args(["--streamer-dir", str(tmp_path), "--cam2-interval", "0.5", "--layout-interval", "2"])
    assert (cfg.cam2_interval, cfg.layout_interval) == (0.5, 2.0)
    url_file = tmp_path / "rtmp-url"
    url_file.write_text(RTMP + "\n")
    _, cfg = sd.parse_args(["--streamer-dir", str(tmp_path), "--rtmp-url-file", str(url_file)])
    assert cfg.rtmp_url == RTMP
    for bad in (["--encoder", "vaapi"], ["--fps", "121"], ["--desktop-fps", "61", "--fps", "60"],
                ["--rtmp-url", RTMP, "--rtmp-url-file", str(url_file)], ["--layout-switch", "hot"]):
        with pytest.raises(SystemExit):
            sd.parse_args(["--streamer-dir", str(tmp_path), *bad])


# ------------------------------------------------------------------ encoder

class FakeRun:
    def __init__(self, code=0, stderr="", raises=None):
        self.code, self.stderr, self.raises, self.calls = code, stderr, raises, []

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        if self.raises:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.code, "", self.stderr)


def test_v2_encoder_probe_and_fallback_with_a_mocked_subprocess(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path, fps=60, desktop_fps=60, encoder="h264_nvenc")
    fake = FakeRun(code=1, stderr="[h264_nvenc @ 0x1] Cannot load libcuda.so.1\nError while opening encoder\n")
    monkeypatch.setattr(sd.subprocess, "run", fake)
    ok, reason = sd.probe_encoder(cfg, "h264_nvenc")
    assert ok is False and "libcuda" in reason and len(fake.calls) == 1
    probe = fake.calls[0]
    assert "testsrc2=size=1920x1080:rate=60:duration=1" in probe and probe[-3:] == ["-f", "null", "-"]
    assert value_after(probe, "-c:v") == "h264_nvenc" and value_after(probe, "-tune") == "ll"
    assert sd.probe_encoder(cfg, "libx264") == (True, "libx264 needs no probe") and len(fake.calls) == 1
    assert sd.probe_encoder(cfg, "hevc_nvenc", run=FakeRun(raises=FileNotFoundError("ffmpeg")))[0] is False
    assert sd.probe_encoder(cfg, "hevc_nvenc", run=FakeRun(code=0)) == (True, "hevc_nvenc probe passed")

    async def body():                     # the director probes once, falls back, and says so in state and events
        director, launched = make_director(tmp_path, [lambda: FakeProc(1, exit_after=0.05, code=1), lambda: FakeProc(2)],
                                           fps=60, desktop_fps=60, encoder="h264_nvenc")
        task = asyncio.ensure_future(director.run())
        await until(lambda: len(launched) == 2 and director.alive)
        state = director.state()
        assert (state["encoder"], state["encoder_requested"]) == ("libx264", "h264_nvenc") and "libcuda" in state["encoder_note"]
        assert all(value_after(argv, "-c:v") == "libx264" and value_after(argv, "-g") == "120" for argv, _ in launched)
        assert len(fake.calls) == 2                                          # once per director, not per launch
        events = [json.loads(line) for line in (tmp_path / "streamer" / "events.jsonl").read_text().splitlines()]
        fallback = [e for e in events if e["kind"] == "encoder_fallback"]
        assert len(fallback) == 1 and fallback[0]["requested"] == "h264_nvenc" and fallback[0]["active"] == "libx264"
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())
    passing = sd.Director(make_cfg(tmp_path, encoder="hevc_nvenc"), probe=lambda enc: (True, f"{enc} probe passed"))
    assert run(passing.resolve_encoder()) == "hevc_nvenc" and passing.state()["encoder"] == "hevc_nvenc"


# ------------------------------------------------------------------ layouts

def test_v2_layout_follows_the_last_line_of_layout_jsonl(tmp_path):
    log = tmp_path / "layout.jsonl"
    assert sd.read_last_layout(log) is None
    log.write_text('{"layout": "desktop"}\n{"layout": "character", "source": "agent"}\n\n')
    assert sd.read_last_layout(log) == "webcam"
    with open(log, "a") as handle:
        handle.write('{"layout": "room"}\n{"layout": "spl')                   # half-written last line: keep the current one
    assert sd.read_last_layout(log) is None
    log.write_text('{"layout": "room"}\n{"layout": "sideways"}\n')
    assert sd.read_last_layout(log) is None
    log.write_text('{"layout": "split"}\n')
    assert sd.read_last_layout(log) == "split"
    director, _ = make_director(tmp_path, [lambda: None])
    streamer_log = tmp_path / "streamer" / "layout.jsonl"
    streamer_log.parent.mkdir(parents=True)
    streamer_log.write_text('{"layout": "room"}\n')
    assert director.poll_layout_log() == "room" and director.layout == "room"
    assert director.poll_layout_log() is None                               # unchanged file: not re-read
    fixed, _ = make_director(tmp_path, [lambda: None], layout="desktop")
    assert fixed.poll_layout_log() is None and fixed.layout == "desktop"
    record = fixed.set_layout("split")                                      # logged, but the fixed layout stays
    assert record["fixed"] == "desktop" and fixed.layout == "desktop"
    assert director.set_layout("character")["requested"] == "character" and director.layout == "webcam"


class FakeStdin:
    """ffmpeg's stdin: records the command lines and answers like ffmpeg 6.1 (or 7.x) on stderr."""

    def __init__(self, director, ret=0, style="stream"):
        self.director, self.ret, self.style, self.lines = director, ret, style, []

    def write(self, data):
        self.lines.append(data)
        if self.ret is not None:
            reply = (f"Command reply for stream 0: ret:{self.ret} res:" if self.style == "stream"
                     else f"Command reply for graph 0: ret:<{self.ret}> res:")
            loop = asyncio.get_running_loop()
            loop.call_soon(self.director.stderr_line, "")
            loop.call_soon(self.director.stderr_line, "Enter command: <target>|all <time>|-1 <command>[ <argument>]")
            loop.call_soon(self.director.stderr_line, reply)

    async def drain(self):
        return None

    def close(self):
        pass


def live_director(tmp_path, cam2=True, **kw):
    director, _ = make_director(tmp_path, [lambda: None], switch_timeout=0.3, **kw)
    proc = FakeProc.__new__(FakeProc)
    proc.pid, proc.returncode = 5, None
    director.proc, director.prefix, director.cam2 = proc, "sub01-20261023-210000", cam2
    director.live_layout, director.live_order = "webcam", sd.live_order(cam2)
    return director, proc


def test_v2_live_switch_writes_one_streamselect_command_and_waits_for_the_reply(tmp_path):
    async def body():
        director, proc = live_director(tmp_path)
        proc.stdin = FakeStdin(director)
        assert await director.apply_layout() == "same" and proc.stdin.lines == []
        director.layout = "split"
        assert await director.apply_layout() == "live"
        assert proc.stdin.lines == [b"cstreamselect@layout -1 map 2\n"] and director.live_layout == "split"
        director.layout = "room"
        proc.stdin.style = "graph"                                           # ffmpeg 7.x wording
        assert await director.apply_layout() == "live" and proc.stdin.lines[-1] == b"cstreamselect@layout -1 map 3\n"
        assert director.state()["last_switch"]["how"] == "live" and director._restart_reason is None
        assert not any("Enter command" in line for line in director._tail)   # prompts stay out of the error tail
        events = [json.loads(line) for line in (tmp_path / "streamer" / "events.jsonl").read_text().splitlines()]
        assert [(e["layout"], e["previous"]) for e in events if e["kind"] == "layout_switched"] == [
            ("split", "webcam"), ("room", "split")]
        # no reply (or an error reply) -> relaunch with the new layout
        proc.stdin = FakeStdin(director, ret=None)
        director.layout = "desktop"
        assert await director.apply_layout() == "restart"
        assert director._restart_reason.startswith("layout desktop (live switch failed: no reply")
        director._restart_reason = None
        proc.stdin = FakeStdin(director, ret=-22)
        assert await director.apply_layout() == "restart" and "ret -22" in director._restart_reason
    run(body())


def test_v2_a_switch_that_outlives_its_ffmpeg_changes_nothing(tmp_path):
    """Kimi review: a relaunch while a switch waits for its reply must not let the old switch touch the new run."""
    async def body():
        director, proc = live_director(tmp_path)

        class Relaunching(FakeStdin):
            def write(self, data):
                super().write(data)
                new = FakeProc.__new__(FakeProc)
                new.pid, new.returncode = 6, None
                asyncio.get_running_loop().call_soon(setattr, director, "proc", new)   # the run was replaced
        proc.stdin = Relaunching(director)
        director.layout = "desktop"
        assert await director.apply_layout() == "stale"
        assert director.live_layout == "webcam" and director._restart_reason is None and director.last_switch is None
    run(body())


def test_v2_room_needs_cam2_and_the_restart_mode_relaunches(tmp_path):
    async def body():
        director, proc = live_director(tmp_path, cam2=False)
        proc.stdin = FakeStdin(director)
        director.layout = "room"
        assert await director.apply_layout() == "same"                       # no cam2: webcam is what room can show
        director.cam2_now = True                                             # cam2 came up: relaunch with it...
        now = [1000.0]
        director._clock, director.started_mono = (lambda: now[0]), 990.0
        director.last_restart_reason = sd.CAM2_DROP                          # ...but not 30 s after dropping it
        assert await director.apply_layout() == "same"
        now[0] = 1021.0
        assert await director.apply_layout() == "restart" and director._restart_reason == "layout room: relaunch with cam2"
        restart, proc2 = live_director(tmp_path, layout_switch="restart")
        restart.live_order = ("webcam",)
        restart.layout = "desktop"
        assert await restart.apply_layout() == "restart" and restart._restart_reason == "layout desktop"
        assert not hasattr(proc2, "stdin")
    run(body())


# --------------------------------------------------------------------- cam2

def test_v2_cam2_is_usable_only_with_a_writer_and_a_fresh_cam2_json(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    cfg = make_cfg(tmp_path)
    tap = sd.FifoTap(cfg.cam2_fifo, proc_root, create=False, what="cam2")
    now = time.time()
    assert sd.cam2_status(cfg, tap, now) == (False, "cam2 FIFO does not exist", None)
    cfg.streamer_dir.mkdir(parents=True)
    cfg.cam2_fifo.write_bytes(b"")
    assert sd.cam2_status(cfg, tap, now)[1] == "cam2 path is not a FIFO"
    cfg.cam2_fifo.unlink()
    os.mkfifo(cfg.cam2_fifo)
    assert sd.cam2_status(cfg, tap, now)[1] == "no cam2.json next to the cam2 FIFO" and tap.fd is not None   # tap open
    cfg.cam2_json.write_text(json.dumps({"fps": 60, "last_frame_unix": now - 0.4}))
    assert sd.cam2_status(cfg, tap, now)[1] == "no process writes to the cam2 FIFO"
    assert sd.cam2_status(cfg, tap, now, writer=False)[0] is True          # freshness only (while the run reads it)
    fake_proc(proc_root, 30, 9, cfg.cam2_fifo, "0104001")                  # the game: O_WRONLY|O_NONBLOCK
    ok, reason, fps = sd.cam2_status(cfg, tap, now)
    assert ok and fps == 60.0 and reason == "cam2 last frame 0.4s ago, writer present"
    cfg.cam2_json.write_text(json.dumps({"fps": 60, "last_frame": iso_z(now - 9)}))
    assert sd.cam2_status(cfg, tap, now)[:2] == (False, "cam2 last frame 9.0s ago")
    cfg.cam2_json.write_text(json.dumps({"last_frame_ms": 1, "last_frame_unix": (now - 2) * 1000}))   # milliseconds
    assert sd.cam2_status(cfg, tap, now)[0] is True
    tap.close()
    assert sd.parse_time(True) is None and sd.parse_time(12345.0) is None and sd.parse_time("nope") is None


def iso_z(unix):
    return datetime.fromtimestamp(unix, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def test_v2_cam2_decision_drops_at_once_and_adds_only_for_room():
    f = sd.cam2_decision
    assert f(True, True, 3, uptime=5, wanted=False) == ("keep", 0)
    assert f(True, False, 0, uptime=5, wanted=True) == ("drop", 0)          # a stalled cam2 freezes the graph: at once
    assert f(False, False, 1, uptime=500, wanted=True) == ("keep", 0)
    assert f(False, True, 0, uptime=500, wanted=True) == ("wait", 1)
    assert f(False, True, 1, uptime=500, wanted=True) == ("add", 2)
    assert f(False, True, 1, uptime=10, wanted=True) == ("wait", 2)         # just launched: no relaunch loop
    assert f(False, True, 1, uptime=500, wanted=False) == ("ready", 2)      # webcam/desktop/split do not need it


def test_v2_cam2_tick_relaunches_without_a_stalled_cam2_and_with_it_for_room(tmp_path):
    async def body():
        now = [1000.0]
        available = [(False, "cam2 last frame 7.0s ago", 60.0)]
        writers = []
        director, _ = make_director(tmp_path, [lambda: None])
        director._check_cam2 = lambda writer=True: (writers.append(writer), available[0])[1]
        director._clock = lambda: now[0]
        director.proc, director.cam2, director.started_mono = FakeProc(1), True, 1000.0
        now[0] += 100
        assert await director.cam2_tick() == "drop" and director._restart_reason == "cam2 stopped delivering"
        director._restart_reason, director.cam2 = None, False
        available[0] = (True, "cam2 writer present, last frame 0.1s ago", 60.0)
        assert await director.cam2_tick() == "wait"
        assert await director.cam2_tick() == "ready" and director._restart_reason is None and director.cam2_now
        director.layout = "room"
        assert await director.cam2_tick() == "add" and director._restart_reason == "cam2 came online"
        director._restart_reason, director.cam2 = None, True                # reading cam2, the game replaces the FIFO
        director._cam2_ident, director.cam2_tap.ident = (1, 2), (1, 3)
        assert await director.cam2_tick() == "drop" and "replaced" in director.cam2_reason
        kinds = [json.loads(line)["kind"] for line in (tmp_path / "streamer" / "events.jsonl").read_text().splitlines()]
        assert kinds.count("cam2_changed") == 3
        assert writers == [False, True, True, True, True]    # reading cam2: freshness only, but every 5th tick is full
    run(body())


def test_v2_restart_mode_attaches_cam2_only_to_room_runs(tmp_path):
    async def body():
        launched = []
        for layout in ("webcam", "room"):
            director, runs = make_director(tmp_path / layout, [lambda: FakeProc(3)], layout_switch="restart", layout=layout)
            director._check_cam2 = lambda writer=True: (True, "fresh", 60.0)
            task = asyncio.ensure_future(director.run())
            await until(lambda: director.alive)
            launched.append((runs[0][0], director.cam2, director.cam2_now))
            director.stop()
            await asyncio.wait_for(task, 5)
        (webcam_argv, webcam_cam2, now_ready), (room_argv, room_cam2, _) = launched
        assert webcam_argv.count("-i") == 3 and webcam_cam2 is False and now_ready is True     # ready for a room switch
        assert room_argv.count("-i") == 4 and room_cam2 is True and "mjpeg" in room_argv
    run(body())


def test_v2_the_director_drains_cam2_only_while_ffmpeg_is_not_reading_it(tmp_path):
    async def body():
        director, _ = make_director(tmp_path, [lambda: None])
        drained = []
        director.cam2_tap.drain = lambda limit=None: drained.append(limit)
        await director.drain_tick()
        director.proc, director.cam2 = FakeProc(1), True
        await director.drain_tick()
        assert drained == [4 << 20]                                # one drain (4 MB cap), none while ffmpeg reads
    run(body())


# ------------------------------------------------------------- output fps

def progress_block(frame, out_s, fps=60.0, dup=0, drop=0, end=False):
    return [f"frame={frame}", f"fps={fps:.2f}", "stream_0_0_q=23.0", f"out_time_us={int(out_s * 1e6)}",
            f"out_time=00:00:{out_s:09.6f}", f"dup_frames={dup}", f"drop_frames={drop}", "speed=1.00x",
            f"progress={'end' if end else 'continue'}"]


def test_v2_output_meter_measures_fps_now_and_per_segment():
    meter = sd.OutputMeter(10, "sub01-r")
    records = []
    for now, frame, out_s, dup in ((0.0, 0, 0.0, 0), (5.0, 300, 5.0, 0), (10.5, 630, 10.5, 2), (15.5, 930, 15.5, 2)):
        for line in progress_block(frame, out_s, dup=dup):
            records += meter.feed(line, now)
    assert meter.latest["fps_measured"] == 60.0 and meter.latest["frames"] == 930 and meter.latest["speed"] == 1.0
    assert records == [{"segment": "sub01-r-000.mp4", "frames": 630, "wall_s": 10.5, "media_s": 10.5, "fps": 60.0,
                        "fps_media": 60.0, "dup_frames": 2, "drop_frames": 0, "partial": False}]
    end = [r for line in progress_block(1170, 19.5, dup=2, end=True) for r in meter.feed(line, 19.5)]
    assert [(r["segment"], r["frames"], r["partial"]) for r in end] == [("sub01-r-001.mp4", 540, True)]
    assert meter.finish() == [] and len(meter.history) == 2
    # an end block past a boundary closes the full window; no empty partial after it
    crossing = sd.OutputMeter(10, "sub01-c")
    for now, frame, out_s in ((0.0, 0, 0.0), (5.0, 300, 5.0)):
        for line in progress_block(frame, out_s):
            crossing.feed(line, now)
    end = [r for line in progress_block(620, 10.3, end=True) for r in crossing.feed(line, 10.3)]
    assert [(r["segment"], r["frames"], r["partial"]) for r in end] == [("sub01-c-000.mp4", 620, False)]
    # a run that ends at its first block reports nothing (no zero-frame record)
    short = sd.OutputMeter(10, "sub01-s")
    assert [r for line in progress_block(0, 0.0, end=True) for r in short.feed(line, 0.0)] == [] and short.finish() == []
    killed = sd.OutputMeter(600, "sub01-k")
    for now, frame in ((0.0, 0), (2.0, 118)):
        for line in progress_block(frame, now):
            killed.feed(line, now)
    assert killed.finish()[0]["fps"] == 59.0 and killed.feed("garbage", 3.0) == []
    for line in ("frame=N/A", "progress=continue"):                          # a block without a frame count is ignored
        assert killed.feed(line, 4.0) == []


# -------------------------------------------------------------- secrets, HLS

def test_v2_the_rtmp_url_never_reaches_logs_state_or_print_argv(tmp_path, monkeypatch, capsys):
    url_file = tmp_path / "rtmp-url"
    url_file.write_text(RTMP)
    monkeypatch.setattr(sd, "find_game_window", lambda cfg: (0x20000C, "fixed"))
    monkeypatch.setattr(sd.VoiceTap, "writer_present", lambda self, settle=None: (False, "no writer"))
    assert sd.main(["--print-argv", "--streamer-dir", str(tmp_path), "--rtmp-url-file", str(url_file)]) == 0
    out = capsys.readouterr().out
    assert "sk_live_0123456789abcdef" not in out and "203.0.113.7" not in out and "]<redacted>" in out
    director, _ = make_director(tmp_path, [lambda: None], rtmp_url=RTMP)
    director.stderr_line(f"[fifo @ 0x5] Error opening {RTMP}: Connection refused")
    director.stderr_line("[rtmp @ 0x6] Server error: stream sk_live_0123456789abcdef refused")
    state = json.dumps(director.state())
    assert all("sk_live" not in line and "203.0.113.7" not in line for line in director._tail)
    assert "sk_live" not in state and director.state()["rtmp"] is True


def test_v2_old_hls_segments_are_pruned_and_state_counts_the_current_run(tmp_path):
    hls = tmp_path / "hls"
    hls.mkdir()
    now = time.time()
    names = {"sub01-20261023-200000-1792790000.ts": now - 300, "sub01-20261023-200000-1792790001.ts.tmp": now - 300,
             "sub01-20261023-205900-1792790100.ts": now - 10, "sub01-20261023-210000-1792790200.ts": now - 300,
             "live.m3u8": now - 300, "notes.ts": now - 300}
    for name, mtime in names.items():
        (hls / name).write_bytes(b"x")
        os.utime(hls / name, (mtime, mtime))
    assert sd.prune_hls(hls, "sub01-20261023-210000", now) == 2
    assert sorted(os.listdir(hls)) == ["live.m3u8", "notes.ts", "sub01-20261023-205900-1792790100.ts",
                                       "sub01-20261023-210000-1792790200.ts"]
    assert sd.hls_state(hls, "sub01-20261023-210000") == {"dir": str(hls), "playlist": True, "segments": 1}
    assert sd.hls_state(tmp_path / "none", "x")["playlist"] is False


def test_v2_hls_server_serves_only_playlist_and_segments_with_no_cache_playlist(tmp_path):
    async def body():
        hls = tmp_path / "hls"
        hls.mkdir()
        (hls / "live.m3u8").write_text("#EXTM3U\n#EXTINF:4.0,\nsub01-x-1.ts\n")
        (hls / "sub01-x-1.ts").write_bytes(b"\x47" * 188)
        (hls / "notes.txt").write_text("private")
        (tmp_path / "secret.ts").write_bytes(b"no")
        os.symlink(tmp_path / "secret.ts", hls / "link.ts")
        http = TestClient(TestServer(hls_serve.create_app(hls)))
        await http.start_server()
        try:
            r = await http.get("/live.m3u8")
            assert r.status == 200 and r.headers["Content-Type"] == "application/vnd.apple.mpegurl"
            assert "no-cache" in r.headers["Cache-Control"] and (await r.text()).startswith("#EXTM3U")
            r = await http.get("/sub01-x-1.ts")
            assert r.status == 200 and r.headers["Content-Type"] == "video/mp2t" and len(await r.read()) == 188
            for path in ("/notes.txt", "/missing.ts", "/link.ts", "/..%2Fsecret.ts", "/", "/.hidden.ts"):
                assert (await http.get(path)).status == 404, path
        finally:
            await http.close()
    run(body())
    with pytest.raises(SystemExit):
        hls_serve.main([str(tmp_path), "--host", "0.0.0.0"])


# ------------------------------------------------------- real ffmpeg smoke

def small_profile(tmp_path, *extra):
    return ["--streamer-dir", str(tmp_path / "streamer"), "--test-sources", "--size", "320x180", "--pip-size", "96x54",
            "--fps", "30", "--desktop-fps", "30", "--preset", "ultrafast", "--hls-dir", str(tmp_path / "hls"), *extra]


@needs_ffmpeg
def test_v2_smoke_five_seconds_of_test_sources_make_an_mp4_and_an_hls_playlist(tmp_path):
    _, cfg = sd.parse_args(small_profile(tmp_path, "--test-seconds", "5"))
    cfg.recordings_dir.mkdir(parents=True)
    cfg.hls_dir.mkdir()
    argv = sd.build_ffmpeg_argv(cfg, prefix="sub01-20261023-210000", cam2=True, layout="room", live=True)
    assert argv.count("-i") == 4 and "testsrc2=size=1280x720:rate=30" in argv and "x11grab" not in argv
    done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
    assert done.returncode == 0, done.stderr[-1500:]
    meter = sd.OutputMeter(cfg.segment_seconds, "sub01-20261023-210000")
    records = [r for line in done.stdout.splitlines() for r in meter.feed(line, 0.0)]
    assert records and records[-1]["frames"] >= 140 and records[-1]["partial"] is True     # 5 s at 30 fps
    mp4 = cfg.recordings_dir / "sub01-20261023-210000-000.mp4"
    assert mp4.stat().st_size > 10_000
    playlist = (cfg.hls_dir / "live.m3u8").read_text()
    assert "#EXTINF:" in playlist and "#EXT-X-DISCONTINUITY" in playlist and "#EXT-X-ENDLIST" not in playlist
    segments = sorted(cfg.hls_dir.glob("sub01-20261023-210000-*.ts"))
    assert segments and all(seg.name in playlist for seg in segments)
    if shutil.which("ffprobe"):
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height,r_frame_rate:"
                                "format=duration", "-of", "json", str(mp4)], capture_output=True, text=True, timeout=30)
        info = json.loads(probe.stdout)
        video = [s for s in info["streams"] if s["codec_name"] == "h264"][0]
        assert (video["width"], video["height"], video["r_frame_rate"]) == (320, 180, "30/1")
        assert {s["codec_name"] for s in info["streams"]} == {"h264", "aac"} and 4.5 <= float(info["format"]["duration"]) <= 5.6


def top_band_ymax(path, ffmpeg):
    """Brightest luma of the top 40 rows of every frame (split pads the top with black, testsrc2 is bright there)."""
    done = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vf",
                           "crop=iw:40:0:0,signalstats,metadata=print:key=lavfi.signalstats.YMAX:file=-",
                           "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    return [float(v) for v in re.findall(r"YMAX=([\d.]+)", done.stdout)]


@needs_ffmpeg
def test_v2_smoke_the_real_director_switches_layout_live_and_probes_nvenc(tmp_path):
    """The real Director, real ffmpeg (lavfi sources): NVENC is probed (no GPU here: fallback to libx264), the agent
    appends a layout line, the running ffmpeg switches to split without a relaunch, the meter reports fps."""
    _, cfg = sd.parse_args(small_profile(tmp_path, "--encoder", "h264_nvenc"))
    cfg = sd.DirectorConfig(**{**cfg.__dict__, "stats_period": 0.5})

    async def body():
        director = sd.Director(cfg)
        task = asyncio.ensure_future(director.run())
        try:
            await until(lambda: director.alive and director.meter and (director.meter.latest or {}).get("frames", 0) >= 45,
                        timeout=40)
            assert director.state()["live_layout"] == "webcam" and director.launches == 1
            sd.append_jsonl(cfg.streamer_dir / "layout.jsonl", {"layout": "split", "source": "agent"})   # as the agent
            await until(lambda: director.state()["live_layout"] == "split", timeout=10)
            await asyncio.sleep(1.5)
            state = director.state()
            assert state["last_switch"]["how"] == "live" and director.launches == 1     # switched without a relaunch
            assert state["output"]["fps_measured"] and state["output"]["fps_measured"] > 20
        finally:
            director.stop()
            await asyncio.wait_for(task, 20)
        return director

    director = run(body())
    events = [json.loads(line) for line in (cfg.streamer_dir / "events.jsonl").read_text().splitlines()]
    kinds = [e["kind"] for e in events]
    assert "layout_switched" in kinds and "ffmpeg_exited" not in kinds and kinds.count("ffmpeg_started") == 1
    if director.encoder == "libx264":                     # no usable NVENC here: the probe failed and said so
        assert "encoder_fallback" in kinds
    seg = [e for e in events if e["kind"] == "segment_fps"]
    assert seg and seg[-1]["partial"] is True and seg[-1]["frames"] > 45 and director.state()["segments_fps"]
    assert "#EXTINF:" in (cfg.hls_dir / "live.m3u8").read_text()
    recording = sorted(cfg.recordings_dir.glob("sub01-*-000.mp4"))
    assert len(recording) == 1
    ymax = top_band_ymax(recording[0], FFMPEG)
    assert len(ymax) > 60 and max(ymax[:15]) > 100 and max(ymax[-10:]) < 40   # webcam first, black split bar at the end


# ------------------------------------------------- in-game monitor feed (scripts/streamer_monitor_feed.py)

mon_spec = importlib.util.spec_from_file_location("streamer_monitor_feed", ROOT / "scripts/streamer_monitor_feed.py")
mon = importlib.util.module_from_spec(mon_spec)
mon_spec.loader.exec_module(mon)


def test_v2_monitor_feed_argv_and_flags(tmp_path):
    args = mon.parse_args(["--streamer-dir", str(tmp_path)])
    argv = mon.build_argv(args)
    assert args.fifo == str(tmp_path / "monitor.mjpeg") and (args.display, args.fps, args.port) == (":103", 60, 8840)
    assert value_after(argv, "-f") == "x11grab" and value_after(argv, "-framerate") == "60" and value_after(argv, "-i") == ":103"
    assert value_after(argv, "-vf") == "scale=1280:720" and value_after(argv, "-c:v") == "mjpeg" and value_after(argv, "-q:v") == "5"
    assert argv[-3:] == ["-f", "mpjpeg", "pipe:1"] and "-nostdin" in argv
    args = mon.parse_args(["--streamer-dir", str(tmp_path), "--display", ":104", "--test-source", "--fps", "30"])
    assert "testsrc2=size=1280x720:rate=30" in mon.build_argv(args) and "x11grab" not in mon.build_argv(args)
    for bad in (["--display", "104"], ["--fps", "0"], ["--size", "big"], ["--host", "0.0.0.0"], ["--pipe-kb", "8"]):
        with pytest.raises(SystemExit):
            mon.parse_args(["--streamer-dir", str(tmp_path), *bad])


def test_v2_monitor_feed_cuts_mpjpeg_parts_by_length():
    frames = [b"\xff\xd8" + bytes([i]) * (1000 * (i + 1)) + b"\xff\xd9" for i in range(3)]
    stream = b"--ffmpeg\r\n" + b"".join(b"Content-type: image/jpeg\r\nContent-length: %d\r\n\r\n%s\r\n--ffmpeg\r\n" % (len(f), f)
                                         for f in frames)
    reader, got = mon.PartReader(), []
    for i in range(0, len(stream), 777):                                  # arbitrary pipe chunks
        got += reader.feed(stream[i:i + 777])
    assert got == frames and len(reader.buf) < 40


def test_v2_monitor_feed_writes_whole_frames_and_never_blocks(tmp_path):
    fifo = tmp_path / "monitor.mjpeg"
    now = [0.0]
    sink = mon.FifoSink(fifo, pipe_bytes=65536, clock=lambda: now[0])
    sink.ensure_fifo()
    assert stat_is_fifo(fifo) and oct(fifo.stat().st_mode & 0o777) == "0o600"
    assert sink.offer(b"x" * 10) is False and sink.dropped == 1 and sink.fd is None      # no reader: dropped, no block
    reader = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        assert sink.offer(b"y" * 10) is False                            # open retried only every 0.5 s
        now[0] += 1
        a, b, c = b"A" * 100_000, b"B" * 100_000, b"C" * 50_000
        assert sink.offer(a) is True and sink.pending                    # the kernel took a part: the tail is pending
        assert sink.offer(b) is False and sink.dropped == 3              # B dropped whole while A is unfinished
        data = read_all(reader)
        assert sink.offer(c) is True
        data += read_all(reader)
        while sink.pending:                                              # C's tail goes out with the next offer
            sink.offer(b"")
            data += read_all(reader)
        assert data == a + c                                             # whole frames, B never started
        sink.pending = b"tail"
    finally:
        os.close(reader)
    assert sink.reader_alive() is False and sink.fd is None and sink.pending == b""   # POLLERR: noticed without a write
    assert sink.offer(b"z" * 10) is False and sink.fd is None
    with pytest.raises(ValueError):
        (tmp_path / "plain").write_bytes(b"")
        mon.FifoSink(tmp_path / "plain").ensure_fifo()


def stat_is_fifo(path):
    import stat as stat_
    return stat_.S_ISFIFO(os.stat(path).st_mode)


def read_all(fd):
    out = b""
    while True:
        try:
            chunk = os.read(fd, 1 << 20)
        except BlockingIOError:
            return out
        if not chunk:
            return out
        out += chunk


@needs_ffmpeg
def test_v2_smoke_monitor_feed_delivers_decodable_jpegs_and_stops_without_a_reader(tmp_path):
    args = mon.parse_args(["--streamer-dir", str(tmp_path), "--test-source", "--size", "320x180", "--fps", "30",
                           "--idle-stop", "0.5", "--ffmpeg", FFMPEG])

    async def body():
        feed = mon.MonitorFeed(args)
        task = asyncio.ensure_future(feed.run())
        await until(lambda: Path(args.fifo).exists())
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        data = b""
        try:
            end = asyncio.get_running_loop().time() + 2.5
            while asyncio.get_running_loop().time() < end:
                data += read_all(reader)
                await asyncio.sleep(0.02)
            assert feed.health()["ffmpeg"] and feed.health()["reader"]
        finally:
            os.close(reader)
        await until(lambda: not feed.health()["ffmpeg"], timeout=10)    # no reader: capture stops
        health = feed.health()
        feed.stop()
        await asyncio.wait_for(task, 10)
        return data, health

    data, health = run(body())
    assert health["frames_written"] >= 20 and health["restarts"] == 1 and health["reader"] is False
    got = tmp_path / "got.mjpeg"
    got.write_bytes(data)
    if shutil.which("ffprobe"):
        probe = subprocess.run(["ffprobe", "-v", "error", "-f", "mjpeg", "-count_frames", "-show_entries",
                                "stream=nb_read_frames,width,height", "-of", "json", str(got)],
                               capture_output=True, text=True, timeout=30)
        stream = json.loads(probe.stdout)["streams"][0]
        assert (stream["width"], stream["height"]) == (320, 180)
        assert int(stream["nb_read_frames"]) >= health["frames_written"] - 1     # every written frame decodes


# =====================================================================================================================
# privacy cut (owner, 2026-10-23: logins on his PC). The agent appends {"layout": "webcam", "reason": "privacy",
# "privacy_id": ...} to layout.jsonl on a login/account page and types a credential only when GET /director/state says
# {"privacy": true, "privacy_id": <same>, "desktop_hidden": true}. The director then shows webcam_only (the game, no PiP:
# no desktop picture at all; room is out too, cam 2 sees the in-game monitor) until a later line without that reason.
# =====================================================================================================================

import sys
from types import SimpleNamespace

PID = "p1-a1b2c3"


def privacy_line(pid=PID, layout="webcam", **extra):
    return {"t": "2026-10-23T22:00:00Z", "unix": 1.0, "layout": layout, "reason": "privacy", "why": "login page",
            "previous": "room", "source": "streamer_agent", "privacy_id": pid, **extra}


def end_line(layout="room", pid=PID):
    return {"t": "2026-10-23T22:01:00Z", "unix": 2.0, "layout": layout, "reason": "privacy_end", "privacy_id": pid,
            "source": "streamer_agent"}


def log_line(director, record):
    sd.append_jsonl(director.cfg.streamer_dir / "layout.jsonl", record)


def kinds_of(tmp_path):
    path = tmp_path / "streamer" / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_privacy_graphs_have_no_desktop_picture(tmp_path):
    cfg = make_cfg(tmp_path, fps=60, desktop_fps=60)
    graph = sd.build_filter_complex("webcam_only", cfg)
    assert graph == "[0:v]fps=60,scale=1920:1080,setsar=1,format=yuv420p[vout]"            # the game alone
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, cam2=False, layout="webcam_only", live=False)
    assert "-nostdin" in argv and argv.count("-i") == 3 and "mjpeg" not in argv             # restart mode: no cam2 input
    assert "[1:v]" not in value_after(argv, "-filter_complex") and "[3:v]" not in value_after(argv, "-filter_complex")
    live = value_after(sd.build_ffmpeg_argv(cfg, prefix="p", cam2=True, layout="webcam_only", live=True), "-filter_complex")
    assert "[0:v]fps=60,scale=1920:1080,setsar=1,format=yuv420p,split=4[gm][gp][gh][lwebcam_only]" in live
    assert live.count("[lwebcam_only]") == 2 and "streamselect@layout=inputs=5:map=4," in live   # straight from the game
    assert sd.effective_layout("webcam_only", False) == "webcam_only" and sd.LAYOUTS["webcam_only"]["needs_cam2"] is False


def test_privacy_lines_are_read_fail_closed(tmp_path):
    assert sd.privacy_cut(privacy_line()) == {"id": PID, "why": "login page"}
    assert sd.privacy_cut(privacy_line(pid=7)) == {"id": None, "why": "login page"}         # a bad id never matches the agent's
    assert sd.privacy_cut(privacy_line(pid="x" * 65))["id"] is None
    for other in (end_line(), {"layout": "webcam"}, {"reason": "Privacy"}, None, [], "privacy"):
        assert sd.privacy_cut(other) is None
    log = tmp_path / "layout.jsonl"
    for layout in ("webcam", "bogus", None, "desktop"):                                     # the layout field does not matter
        log.write_text(json.dumps({"layout": "split"}) + "\n" + json.dumps(privacy_line(layout=layout)) + "\n")
        assert sd.read_last_layout(log) == "webcam_only" and sd.read_last_record(log)["privacy_id"] == PID
    with open(log, "a") as handle:
        handle.write('{"layout": "room", "reason": "privacy_e')                              # half-written: keep the state
    assert sd.read_last_record(log) is None and sd.read_last_layout(log) is None
    log.write_text(json.dumps(end_line()) + "\n")
    assert sd.read_last_layout(log) == "room"


def test_privacy_switches_live_to_webcam_only_and_acknowledges_only_after_ret_0(tmp_path):
    async def body():
        director, proc = live_director(tmp_path, cam2=True)
        seen = []

        class Watching(FakeStdin):
            def write(self, data):
                seen.append((data, director.desktop_hidden(), director.state()["desktop_hidden"]))
                super().write(data)
        proc.stdin = Watching(director)
        assert director.poll_layout_log() is None                                           # running, no log yet
        log_line(director, privacy_line())
        assert director.poll_layout_log() == "webcam_only"
        state = director.state()
        assert (state["privacy"], state["privacy_id"], state["desktop_hidden"]) == (True, PID, False)  # webcam has a PiP
        assert state["layout"] == "webcam_only" and state["privacy_restore"] == "webcam" and state["live_layout"] == "webcam"
        assert await director.apply_layout() == "live"
        assert seen == [(b"cstreamselect@layout -1 map 4\n", False, False)]                 # not acknowledged in flight
        state = director.state()
        assert (state["privacy"], state["privacy_id"], state["desktop_hidden"]) == (True, PID, True)
        assert state["live_layout"] == "webcam_only" and state["privacy_hidden_at"]
        # the agent asks again and again: same answer, no new command
        assert await director.apply_layout() == "same" and len(seen) == 1 and director.desktop_hidden()
        # the end line: the layout it names comes back (room: cam 2 is in this run), then the restore is reported
        log_line(director, end_line("room"))
        assert director.poll_layout_log() == "room"
        state = director.state()
        assert (state["privacy"], state["privacy_id"], state["desktop_hidden"]) == (False, None, False)
        assert state["last_privacy"]["id"] == PID and state["last_privacy"]["restore"] == "room"
        assert state["last_privacy"]["restored_at"] is None
        assert await director.apply_layout() == "live" and seen[-1][0] == b"cstreamselect@layout -1 map 3\n"
        last = director.state()["last_privacy"]
        assert last["restored_layout"] == "room" and last["restored_at"] and last["hidden_at"] and last["how"] == "privacy_end"
        events = kinds_of(tmp_path)
        assert [e["kind"] for e in events if e["kind"].startswith("privacy")] == [
            "privacy_on", "privacy_hidden", "privacy_off", "privacy_restored"]
        hidden = [e for e in events if e["kind"] == "privacy_hidden"][0]
        assert hidden["privacy_id"] == PID and hidden["how"] == "live switch" and hidden["ms"] >= 0
    run(body())


def test_privacy_is_never_acknowledged_after_a_failed_or_unanswered_switch(tmp_path):
    async def body():
        director, proc = live_director(tmp_path, cam2=False)
        proc.stdin = FakeStdin(director, ret=None)                                          # no reply at all
        log_line(director, privacy_line())
        director.poll_layout_log()
        assert await director.apply_layout() == "restart"
        assert director._restart_reason.startswith("layout webcam_only (live switch failed: no reply")
        assert director.live_layout is None and director.desktop_hidden() is False         # on air: unknown
        director2, proc2 = live_director(tmp_path / "b", cam2=False)
        proc2.stdin = FakeStdin(director2, ret=-22)                                         # an error reply: not switched
        log_line(director2, privacy_line())
        director2.poll_layout_log()
        assert await director2.apply_layout() == "restart" and director2.live_layout == "webcam"
        assert director2.desktop_hidden() is False
        director2._restart_reason = None
        director2.live_layout = "webcam_only"                                               # say a relaunch confirmed it
        assert director2.desktop_hidden() is True
        director2.proc.returncode = 1                                                       # ffmpeg gone: nothing is confirmed
        assert director2.desktop_hidden() is False
    run(body())


def test_a_new_cut_during_a_switch_away_from_webcam_only_waits_for_its_own_switch(tmp_path):
    """The agent ends one cut and starts the next before the director sees the end line take effect."""
    async def body():
        director, proc = live_director(tmp_path, cam2=False)
        proc.stdin = FakeStdin(director)
        log_line(director, privacy_line("p1-aaaaaa"))
        director.poll_layout_log()
        assert await director.apply_layout() == "live" and director.desktop_hidden()
        log_line(director, end_line("desktop", "p1-aaaaaa"))
        director.poll_layout_log()
        during = []

        class NewCutMidSwitch(FakeStdin):
            def write(self, data):
                log_line(director, privacy_line("p2-bbbbbb"))                              # written while the map is in flight
                director.poll_layout_log()
                during.append((director.state()["privacy_id"], director.desktop_hidden()))
                super().write(data)
        proc.stdin = NewCutMidSwitch(director)
        assert await director.apply_layout() == "live" and director.live_layout == "desktop"
        assert during == [("p2-bbbbbb", False)] and director.desktop_hidden() is False      # desktop on air: no ack
        proc.stdin = FakeStdin(director)
        assert await director.apply_layout() == "live" and director.live_layout == "webcam_only"
        assert director.desktop_hidden() and director.state()["privacy_id"] == "p2-bbbbbb"
        # a renewed cut (another id, no end line in between) while webcam_only is on air: acknowledged at once
        log_line(director, privacy_line("p3-cccccc"))
        director.poll_layout_log()
        assert director.state()["privacy_id"] == "p3-cccccc" and director.desktop_hidden()
        renewed = [e for e in kinds_of(tmp_path) if e["kind"] in ("privacy_on", "privacy_hidden")]
        assert [(e["kind"], e["privacy_id"]) for e in renewed][-2:] == [("privacy_on", "p3-cccccc"), ("privacy_hidden", "p3-cccccc")]
        assert renewed[-2]["renewed"] is True
    run(body())


def test_privacy_is_not_acknowledged_while_an_older_ffmpeg_survives_and_a_long_cut_is_reported(tmp_path):
    async def body():
        director, proc = live_director(tmp_path, cam2=False)
        proc.stdin = FakeStdin(director)
        now = [5000.0]
        director._wall = lambda: now[0]
        log_line(director, privacy_line())
        await director.layout_tick()
        assert director.desktop_hidden() is True
        director.stale_pids = {os.getpid()}                 # an ffmpeg of a SIGKILLed director that survived the reap
        assert director.desktop_hidden() is False and director.state()["desktop_hidden"] is False
        director.stale_pids = {2 ** 22 + 12345}             # gone: acknowledged again, and forgotten at the next tick
        assert director.desktop_hidden() is True
        await director.layout_tick()
        assert director.stale_pids == set()
        assert not [e for e in kinds_of(tmp_path) if e["kind"] == "privacy_still_on"]
        now[0] += 601
        await director.layout_tick()
        await director.layout_tick()                        # once per 10 minutes, not per tick
        now[0] += 600
        await director.layout_tick()
        alerts = [e for e in kinds_of(tmp_path) if e["kind"] == "privacy_still_on"]
        assert [a["seconds"] for a in alerts] == [601, 1201] and all(a["privacy_id"] == PID for a in alerts)
        assert director.privacy is not None and director.state()["privacy_seconds"] == 1201.0   # never ended on a timer
        assert sd.pid_alive(os.getpid()) and not sd.pid_alive(2 ** 22 + 12345)
    run(body())


def test_the_reaper_finds_every_recorder_of_this_directory_in_proc(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path)
    root = tmp_path / "proc"
    for pid, argv in ((11, ["ffmpeg", "-f", "x11grab", "-i", ":99", str(cfg.recordings_dir / "a-%03d.mp4")]),
                      (12, ["/usr/bin/ffmpeg", "-f", "lavfi", "-i", "testsrc2", str(cfg.recordings_dir / "b.mp4")]),
                      (13, ["ffmpeg", "-f", "x11grab", "-i", ":99", "/elsewhere/c.mp4"]),          # another directory
                      (14, ["bash", "-c", "ffmpeg -f x11grab " + str(cfg.recordings_dir)]),        # not ffmpeg itself
                      (16, ["ffmpeg", "-f", "x11grab", "-i", ":99", str(cfg.recordings_dir) + "-old/d-%03d.mp4"]),  # a sibling
                      (17, ["ffmpeg", "-f", "x11grab", "-i", ":99", "-f", "tee",
                            "[f=segment:segment_time=600]" + str(cfg.recordings_dir / "e-%03d.mp4") + "|[f=hls]/h/l.m3u8"]),
                      (15, ["python3", "streamer_director.py"])):
        (root / str(pid)).mkdir(parents=True)
        (root / str(pid) / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    assert sd.recorder_pids(cfg, root) == [11, 12, 17]

    async def body():
        director, _ = make_director(tmp_path, [lambda: None])
        director.proc_root = root
        sent, alive = [], {11: True, 12: True}
        monkeypatch.setattr(sd, "recorder_pids", lambda cfg, proc_root: [11, 12])
        monkeypatch.setattr(sd.os, "kill", lambda pid, sig: sent.append((pid, sig)) if sig else None)
        monkeypatch.setattr(sd, "pid_alive", lambda pid: alive.get(pid, False) and not (pid == 11 and len(sent) >= 2))
        await director.reap_stale_ffmpeg()                  # 11 stops on SIGINT, 12 survives even SIGKILL
        assert sent[:2] == [(11, signal.SIGINT), (12, signal.SIGINT)] and (12, signal.SIGKILL) in sent
        assert (11, signal.SIGKILL) not in sent and director.stale_pids == {12}
        kinds = [(e["kind"], e["pid"]) for e in kinds_of(tmp_path) if e["kind"].startswith("stale_ffmpeg")]
        assert kinds == [("stale_ffmpeg", 11), ("stale_ffmpeg", 12), ("stale_ffmpeg_survived", 12)]
    run(body())


def test_a_restarted_director_restores_the_layout_requested_before_the_cut(tmp_path):
    director, _ = make_director(tmp_path, [lambda: None])
    (tmp_path / "streamer").mkdir(parents=True)
    for record in ({"layout": "split"}, {"layout": "desktop"}, privacy_line(layout="webcam")):
        log_line(director, record)
    assert director.poll_layout_log() == "webcam_only" and director.state()["privacy_restore"] == "desktop"
    log_line(director, {"reason": "privacy_end", "privacy_id": PID})             # an end line without a layout
    director.poll_layout_log()
    assert director.layout == "desktop" and director.state()["last_privacy"]["restore"] == "desktop"
    lone, _ = make_director(tmp_path / "b", [lambda: None])                      # only the privacy line: its `previous`
    (tmp_path / "b" / "streamer").mkdir(parents=True)
    log_line(lone, privacy_line())
    lone.poll_layout_log()
    assert lone.state()["privacy_restore"] == "room"
    big, _ = make_director(tmp_path / "c", [lambda: None])                       # a long log: the last line still counts
    (tmp_path / "c" / "streamer").mkdir(parents=True)
    with open(tmp_path / "c" / "streamer" / "layout.jsonl", "w") as handle:
        for i in range(2000):
            handle.write(json.dumps({"layout": "split", "pad": "x" * 60, "i": i}) + "\n")
        handle.write(json.dumps(privacy_line()) + "\n")
    assert big.poll_layout_log() == "webcam_only" and big.state()["privacy_restore"] == "split"
    log = tmp_path / "d.jsonl"
    log.write_text("x" * (sd.LAYOUT_TAIL - 10) + "\n" + json.dumps(privacy_line()) + "\n")   # the window starts mid-line
    assert sd.read_last_record(log)["privacy_id"] == PID and sd.read_tail_records(log)[0]["privacy_id"] == PID


def test_a_post_that_races_the_agents_privacy_line_puts_the_cut_back_on_top(tmp_path, monkeypatch):
    async def body():
        http, director = await started(tmp_path)
        log = tmp_path / "streamer" / "layout.jsonl"
        log.parent.mkdir(parents=True)
        real_append = sd.append_jsonl
        raced = []

        def racing_append(path, record):                    # the agent appends right between the POST's read and write
            if record.get("nonce") and not raced:
                raced.append(1)
                real_append(path, privacy_line("p9-racing"))
            real_append(path, record)
        monkeypatch.setattr(sd, "append_jsonl", racing_append)
        try:
            r = await http.post("/director/layout", json={"layout": "desktop"}, headers=AUTH)
            assert r.status == 409 and (await r.json())["privacy_id"] == "p9-racing"
            lines = [json.loads(line) for line in log.read_text().splitlines()]
            assert [(x.get("reason"), x.get("privacy_id")) for x in lines][-1] == ("privacy", "p9-racing")
            assert lines[-1]["reasserted_by"] == "director" and lines[-2]["layout"] == "desktop"
            state = await (await http.get("/director/state", headers=AUTH)).json()
            assert state["privacy"] is True and state["privacy_id"] == "p9-racing"
            assert state["privacy_restore"] == "webcam" and lines[-1]["refused_nonce"] == lines[-2]["nonce"]   # refused
            assert sd.read_last_layout(log) == "webcam_only"                     # a restarted director sees the cut too
            restarted, _ = make_director(tmp_path, [lambda: None])
            assert restarted.poll_layout_log() == "webcam_only" and restarted.state()["privacy_restore"] != "desktop"
        finally:
            await http.close()
    run(body())


def test_privacy_wins_over_a_fixed_layout_in_restart_mode_and_relaunches_without_the_desktop(tmp_path):
    async def body():
        director, launched = make_director(tmp_path, [lambda: FakeProc(1), lambda: FakeProc(2), lambda: FakeProc(3)],
                                           layout="desktop", layout_switch="restart", layout_interval=0.05)
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        assert value_after(launched[0][0], "-filter_complex").startswith("[1:v]")         # the fixed desktop layout
        log_line(director, privacy_line())
        await until(lambda: len(launched) == 2 and director.alive)
        graph = value_after(launched[1][0], "-filter_complex")
        assert graph.startswith("[0:v]fps=24,scale=1920:1080,setsar=1,format=yuv420p[vout]") and "[1:v]" not in graph
        state = director.state()
        assert state["desktop_hidden"] is True and state["layout"] == "webcam_only" and state["layout_requested"] == "desktop"
        assert launched[0][1].signals == [signal.SIGINT]                                    # the desktop run was finalised
        log_line(director, end_line("split"))                                               # the fixed layout comes back
        await until(lambda: len(launched) == 3 and director.alive)
        assert value_after(launched[2][0], "-filter_complex").startswith("[1:v]")
        state = director.state()
        assert state["privacy"] is False and state["last_privacy"]["restored_layout"] == "desktop"
        director.stop()
        await asyncio.wait_for(task, 5)
        started = [e for e in kinds_of(tmp_path) if e["kind"] == "ffmpeg_started"]
        assert [e["layout"] for e in started] == ["desktop", "webcam_only", "desktop"] and started[1]["privacy_id"] == PID
    run(body())


def test_a_restarted_director_resumes_the_privacy_cut_from_the_first_launch(tmp_path):
    async def body():
        director, launched = make_director(tmp_path, [lambda: FakeProc(1)])
        (tmp_path / "streamer").mkdir(parents=True)
        log_line(director, {"layout": "desktop"})
        log_line(director, privacy_line())
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        graph = value_after(launched[0][0], "-filter_complex")
        assert "[lwebcam][ldesktop][lsplit][lwebcam_only]streamselect@layout=inputs=4:map=3," in graph
        state = director.state()
        assert (state["privacy"], state["privacy_id"], state["desktop_hidden"], state["live_layout"]) == (
            True, PID, True, "webcam_only")
        hidden = [e for e in kinds_of(tmp_path) if e["kind"] == "privacy_hidden"]
        assert len(hidden) == 1 and hidden[0]["how"] == "launch"
        director.stop()
        await asyncio.wait_for(task, 5)
        assert director.desktop_hidden() is False                                           # nothing runs: nothing confirmed
    run(body())


def test_layout_posts_during_a_privacy_cut_get_409_unless_they_end_it(tmp_path):
    async def body():
        http, director = await started(tmp_path)
        log = tmp_path / "streamer" / "layout.jsonl"
        try:
            log.parent.mkdir(parents=True)
            log_line(director, privacy_line())                                              # not polled yet: the POST reads it
            r = await http.post("/director/layout", json={"layout": "desktop"}, headers=AUTH)
            answer = await r.json()
            assert r.status == 409 and answer["privacy_id"] == PID and answer["layout"] == "webcam_only"
            assert len(log.read_text().splitlines()) == 1                                   # nothing logged: the cut stays
            state = await (await http.get("/director/state", headers=AUTH)).json()
            for key in ("privacy", "privacy_id", "privacy_why", "privacy_since", "desktop_hidden", "privacy_restore",
                        "last_privacy", "layout_requested"):
                assert key in state
            assert state["privacy"] is True and state["desktop_hidden"] is False and state["layout"] == "webcam_only"
            assert (await http.post("/director/layout", json={"layout": "desktop", "end_privacy": "yes"},
                                    headers=AUTH)).status == 400
            r = await http.post("/director/layout", json={"layout": "desktop", "end_privacy": True}, headers=AUTH)
            answer = await r.json()
            assert r.status == 200 and answer["privacy_ended"] is True
            assert answer["logged"]["reason"] == "privacy_end_operator" and answer["logged"]["privacy_id"] == PID
            state = await (await http.get("/director/state", headers=AUTH)).json()
            assert state["privacy"] is False and state["layout"] == "desktop" and state["last_privacy"]["how"] == "operator"
            # the agent's own sequence: its privacy_end line, then at once its POST of the previous layout: accepted
            log_line(director, privacy_line("p2-dddddd"))
            r = await http.post("/director/layout", json={"layout": "split"}, headers=AUTH)
            assert r.status == 409
            log_line(director, end_line("webcam", "p2-dddddd"))
            r = await http.post("/director/layout", json={"layout": "webcam"}, headers=AUTH)
            assert r.status == 200 and (await r.json())["privacy_ended"] is False
            state = await (await http.get("/director/state", headers=AUTH)).json()
            assert state["privacy"] is False and state["last_privacy"]["id"] == "p2-dddddd" and state["layout"] == "webcam"
        finally:
            await http.close()
    run(body())


def test_print_argv_shows_the_privacy_layout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sd, "find_game_window", lambda cfg: (0x20000C, "fixed"))
    monkeypatch.setattr(sd.VoiceTap, "writer_present", lambda self, settle=None: (False, "no writer"))
    sd.append_jsonl(tmp_path / "layout.jsonl", privacy_line())
    assert sd.main(["--print-argv", "--streamer-dir", str(tmp_path), "--layout", "desktop"]) == 0
    out = capsys.readouterr().out
    assert "layout: webcam_only" in out and "privacy cut in force" in out and "map=3" in out


# ------------------------------------------------- privacy, real ffmpeg (lavfi sources; the desktop is solid red)

AGENT_SPEC = importlib.util.spec_from_file_location("streamer_agent_for_director_tests", ROOT / "streamer_agent.py")


def pip_chroma(path, ffmpeg, cfg):
    """Mean Cr of the PiP corner of every frame: ~240 where the red test desktop shows, ~150 or less for the game."""
    x, y = cfg.width - cfg.pip_width - sd.PIP_MARGIN, cfg.height - cfg.pip_height - sd.PIP_MARGIN
    done = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vf",
                           f"crop={cfg.pip_width}:{cfg.pip_height}:{x}:{y},signalstats,"
                           "metadata=print:key=lavfi.signalstats.VAVG:file=-", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=60)
    return [float(v) for v in re.findall(r"VAVG=([\d.]+)", done.stdout)]


def runs_of(flags):
    out = []
    for flag in flags:
        if out and out[-1][0] == flag:
            out[-1][1] += 1
        else:
            out.append([flag, 1])
    return out


@needs_ffmpeg
def test_privacy_smoke_the_agents_line_hides_every_desktop_pixel_until_its_end_line(tmp_path):
    """Real Director + real ffmpeg + the agent's own write_layout_line / privacy_acked code over HTTP: the ack comes
    only once the output is webcam_only; the decoded recording shows the red desktop PiP, then none at all, then the PiP
    again after the end line, with one transition each way."""
    SA = importlib.util.module_from_spec(AGENT_SPEC)
    sys_path = list(sys.path)
    sys.path.insert(0, str(ROOT))
    try:
        AGENT_SPEC.loader.exec_module(SA)
    finally:
        sys.path[:] = sys_path
    _, cfg = sd.parse_args(small_profile(tmp_path, "--layout-interval", "0.2"))
    cfg = sd.DirectorConfig(**{**cfg.__dict__, "stats_period": 0.5})

    async def body():
        director = sd.Director(cfg)
        http = TestClient(TestServer(sd.create_app(director, TOKEN)))
        await http.start_server()

        async def director_state():
            return await (await http.get("/director/state", headers=AUTH)).json()
        agent = SimpleNamespace(dir=cfg.streamer_dir, clock=time.time, error=lambda *a: None, privacy=None,
                                cfg=SimpleNamespace(require_privacy_ack=True),
                                services=SimpleNamespace(director_state=director_state))
        task = asyncio.ensure_future(director.run())
        try:
            await until(lambda: director.alive and (director.meter.latest or {}).get("frames", 0) >= 30, timeout=40)
            pid = "p1-5m0k3d"
            agent.privacy = {"id": pid, "acked": False,
                             "line_ok": SA.Agent.write_layout_line(agent, "webcam", "privacy", why="login page",
                                                                  previous="webcam", privacy_id=pid)}
            assert await SA.Agent.privacy_acked(agent) is False                       # the agent's first ask: too early
            acked_at = time.monotonic()
            while not await SA.Agent.privacy_acked(agent):
                assert time.monotonic() - acked_at < 10, director.state()
                await asyncio.sleep(0.05)
            assert agent.privacy["acked"] is True and director.state()["live_layout"] == "webcam_only"
            await asyncio.sleep(2.5)                                                    # "typing" on a hidden desktop
            assert await SA.Agent.privacy_acked(agent) is True                          # asked afresh: still hidden
            SA.Agent.write_layout_line(agent, "webcam", "privacy_end", privacy_id=pid)  # privacy_clear_look's two steps
            agent.privacy = None
            r = await http.post("/director/layout", json={"layout": "webcam"}, headers=AUTH)
            assert r.status == 200
            await until(lambda: (director.state()["last_privacy"] or {}).get("restored_at"), timeout=10)
            assert await SA.Agent.privacy_acked(agent) is False                         # no cut, no ack
            await asyncio.sleep(2.0)
            assert director.launches == 1                                               # all of it live, no relaunch
        finally:
            director.stop()
            await asyncio.wait_for(task, 20)
            await http.close()
    run(body())
    recording = sorted(cfg.recordings_dir.glob("sub01-*-000.mp4"))
    assert len(recording) == 1
    flags = [v > 200 for v in pip_chroma(recording[0], FFMPEG, cfg)]                     # True: the desktop is visible
    runs = runs_of(flags)
    assert [flag for flag, _ in runs] == [True, False, True], runs                      # PiP, none at all, PiP again
    assert runs[1][1] >= 60 and runs[0][1] >= 20 and runs[2][1] >= 30, runs            # >= 2 s hidden at 30 fps
    kinds = [json.loads(line)["kind"] for line in (cfg.streamer_dir / "events.jsonl").read_text().splitlines()]
    assert [k for k in kinds if k.startswith("privacy")] == ["privacy_on", "privacy_hidden", "privacy_off", "privacy_restored"]


@needs_ffmpeg
def test_privacy_smoke_the_restart_mode_graph_runs_without_any_desktop_pixel(tmp_path):
    _, cfg = sd.parse_args(small_profile(tmp_path, "--test-seconds", "2", "--layout-switch", "restart"))
    cfg.recordings_dir.mkdir(parents=True)
    cfg.hls_dir.mkdir()
    for layout, red in (("webcam", True), ("webcam_only", False)):
        argv = sd.build_ffmpeg_argv(cfg, prefix=f"sub01-20261023-2200{0 if red else 1}0", cam2=False, layout=layout, live=False)
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
        assert done.returncode == 0, done.stderr[-1500:]
        chroma = pip_chroma(next(cfg.recordings_dir.glob(f"sub01-20261023-2200{0 if red else 1}0-000.mp4")), FFMPEG, cfg)
        assert len(chroma) >= 50 and all((v > 200) is red for v in chroma), (layout, chroma[:5])


# ---- retention: the recordings never fill the disk again (2026-10-24 incident) -----------------------------------------
def _seg(run, index, size):
    return {"name": f"{run}-{index:03d}.mp4", "run": run, "index": index, "bytes": size, "mtime": ""}


def test_retention_keeps_the_newest_segments_and_never_the_one_being_written():
    import scripts.streamer_director as sd
    segs = [_seg("sub01-20261023-100000", i, 60) for i in range(5)] + [_seg("sub01-20261024-010000", i, 60) for i in range(3)]
    gb = 1024 ** 3
    # count cap: 8 segments, keep 4 -> the 4 oldest go
    assert sd.retention_victims(segs, "sub01-20261024-010000", 4, 50 * gb, 2 * gb) == [s["name"] for s in segs[:4]]
    # no cap and plenty of space -> nothing
    assert sd.retention_victims(segs, "sub01-20261024-010000", 0, 50 * gb, 2 * gb) == []
    # low disk: oldest finished segments go until enough would be free; the segment being written survives even if needed
    victims = sd.retention_victims(segs, "sub01-20261024-010000", 0, 0, 10 ** 12)
    assert "sub01-20261024-010000-002.mp4" not in victims and len(victims) == 7
    victims = sd.retention_victims(segs, "sub01-20261024-010000", 0, 2 * gb - 100, 2 * gb)
    assert victims == [segs[0]["name"], segs[1]["name"]]                     # 60 + 60 bytes cover the 100 missing
    # a single segment (the one being written) is never deleted
    assert sd.retention_victims([_seg("r", 0, 10)], "r", 1, 0, 2 * gb) == []


def test_apply_retention_deletes_files_and_reports(tmp_path, monkeypatch):
    import scripts.streamer_director as sd
    rec = tmp_path / "recordings"
    rec.mkdir()
    names = [f"sub01-20261024-010000-{i:03d}.mp4" for i in range(6)]
    for n in names:
        (rec / n).write_bytes(b"x" * 10)
    cfg = sd.DirectorConfig(streamer_dir=tmp_path, recordings_dir=rec, keep_segments=3, min_free_gb=0)
    seen = []
    deleted = sd.apply_retention(cfg, "sub01-20261024-010000", lambda kind, **f: seen.append((kind, f)))
    assert deleted == names[:3] and sorted(p.name for p in rec.iterdir()) == names[3:]
    assert seen and seen[0][0] == "retention" and seen[0][1]["deleted"] == names[:3]
    import pytest as _pytest
    with _pytest.raises(ValueError):
        sd.DirectorConfig(streamer_dir=tmp_path, keep_segments=-1)


def test_apply_retention_skips_an_undeletable_segment_and_rejects_non_finite_limits(tmp_path, monkeypatch):
    import scripts.streamer_director as sd
    rec = tmp_path / "recordings"
    rec.mkdir()
    names = [f"sub01-20261024-010000-{i:03d}.mp4" for i in range(5)]
    for n in names:
        (rec / n).write_bytes(b"x" * 10)
    cfg = sd.DirectorConfig(streamer_dir=tmp_path, recordings_dir=rec, keep_segments=3, min_free_gb=0)
    real_unlink = sd.Path.unlink

    def unlink(self, *a, **k):
        if self.name == names[0]:
            raise PermissionError("busy")
        return real_unlink(self, *a, **k)
    monkeypatch.setattr(sd.Path, "unlink", unlink)
    seen = []
    deleted = sd.apply_retention(cfg, "sub01-20261024-010000", lambda kind, **f: seen.append(f))
    assert names[0] not in deleted and names[1] in deleted and names[2] in deleted          # the stuck one is skipped
    assert seen and seen[-1]["failed"] == [names[0]]
    import pytest as _pytest
    for bad in (float("nan"), float("inf")):
        with _pytest.raises(ValueError):
            sd.DirectorConfig(streamer_dir=tmp_path, min_free_gb=bad)
