"""Streamer director, fifo mode (`--game-source fifo`): the offscreen game's main view from `main.mjpeg`, the placeholder
card while it is stale, the MainSource state machine, the seq tap that counts unique main-view frames, and a real ffmpeg
run against a FIFO fed with synthetic JPEGs (start, a writer blip, a stall, the writer gone, the writer back).

The x11 mode stays the default and byte-identical: tests/test_streamer_director.py pins it; here only the switch.
"""
import asyncio
import importlib.util
import json
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("streamer_director_fifo", ROOT / "scripts/streamer_director.py")
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)
sys.path.insert(0, str(ROOT / "tests"))
import streamer_game_writer as gw  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")


def make_cfg(tmp_path, **kw):
    return sd.DirectorConfig(streamer_dir=tmp_path / "streamer", **kw)


def value_after(argv, flag, start=0):
    return argv[argv.index(flag, start) + 1]


def inputs_of(argv):
    out, start = [], 0
    for i, arg in enumerate(argv):
        if arg == "-i":
            out.append((argv[start:i], argv[i + 1]))
            start = i + 2
    return out


def run(coro):
    return asyncio.run(coro)


def events(tmp_path):
    path = tmp_path / "streamer" / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# ------------------------------------------------------------------ flags

def test_game_source_is_explicit_and_x11_stays_the_default(tmp_path):
    args, cfg = sd.parse_args(["--streamer-dir", str(tmp_path)])
    assert cfg.game_source == "x11" and args.game_source == "x11"
    assert (cfg.main_fifo, cfg.main_json) == (tmp_path / "main.mjpeg", tmp_path / "main.json")
    assert (cfg.main_stale, cfg.main_fresh, cfg.main_interval, cfg.main_tap) == (2.0, 3.0, 1.0, True)
    _, cfg = sd.parse_args(["--streamer-dir", str(tmp_path), "--game-source", "fifo", "--main-fifo", "/x/m.mjpeg",
                            "--main-json", "/x/m.json", "--main-stale", "1.5", "--main-fresh", "4", "--main-interval",
                            "0.5", "--no-main-tap"])
    assert (cfg.game_source, cfg.main_fifo, cfg.main_json) == ("fifo", Path("/x/m.mjpeg"), Path("/x/m.json"))
    assert (cfg.main_stale, cfg.main_fresh, cfg.main_interval, cfg.main_tap) == (1.5, 4.0, 0.5, False)
    for bad in (["--game-source", "auto"], ["--game-source", "fifo", "--main-stale", "0"],
                ["--main-fresh", "-1"], ["--main-interval", "nan"]):
        with pytest.raises(SystemExit):
            sd.parse_args(["--streamer-dir", str(tmp_path), *bad])
    with pytest.raises(ValueError):
        make_cfg(tmp_path, game_source="window")


def test_a_missing_fifo_never_switches_the_mode(tmp_path):
    """x11 is never inferred from a missing main.mjpeg, nor fifo from a present one."""
    cfg = make_cfg(tmp_path)
    cfg.streamer_dir.mkdir(parents=True)
    os.mkfifo(cfg.main_fifo)
    director = sd.Director(cfg)
    assert director.main_mode is False and director.state()["main"] is None
    assert director.state()["game_source_mode"] == "x11"
    fifo = sd.Director(make_cfg(tmp_path / "b", game_source="fifo"))
    assert fifo.main_mode is True and fifo.state()["game_source_mode"] == "fifo"


# ------------------------------------------------------------------- argv

def test_fifo_input_follows_the_spec_plus_follow_and_the_tap_output(tmp_path):
    cfg = make_cfg(tmp_path, fps=60, desktop_fps=60, encoder="h264_nvenc", hls_dir=tmp_path / "hls", game_source="fifo")
    argv = sd.build_ffmpeg_argv(cfg, prefix="sub01-20261024-210000", voice=True, cam2=True, layout="room", live=True,
                                encoder="h264_nvenc", cam2_fps=60, main="fifo", tap_fd=7)
    assert argv[:argv.index("-i")][:12] == ["ffmpeg", "-hide_banner", "-stdin", "-loglevel", "warning", "-progress",
                                            "pipe:1", "-stats_period", "5", "-filter_complex_threads", sd.FILTER_THREADS, "-thread_queue_size"]
    (game, gi), (desk, di), (voice, vi), (cam, ci) = inputs_of(argv)
    assert gi == str(tmp_path / "streamer" / "main.mjpeg")
    assert game[game.index("-thread_queue_size"):] == [
        "-thread_queue_size", "512", "-use_wallclock_as_timestamps", "1", "-probesize", "2000000", "-analyzeduration",
        "1000000", "-f", "mjpeg", "-framerate", "60", "-follow", "1"]
    assert di == ":102.0" and value_after(desk, "-f") == "x11grab" and "-window_id" not in argv   # no game window grab
    assert vi.endswith("voice.pcm") and ci.endswith("cam2.mjpeg")
    graph = value_after(argv, "-filter_complex")
    assert graph.startswith("[0:v]" + sd.WALL_PTS + ",fps=60,tpad=stop=-1:stop_mode=clone,scale=1920:1080:in_range=full:out_range=limited,"
                            "setsar=1,format=yuv420p,split=4[gm][gp][gh][lwebcam_only]")
    assert "[lwebcam][ldesktop][lsplit][lroom][lwebcam_only]streamselect@layout=inputs=5:map=3," in graph
    # the recording output first (so -progress reports it), then the tap: input 0 copied as multipart JPEG to fd 7
    tap = argv[argv.index("-map", argv.index("-f", argv.index("-c:a"))):]
    assert tap == ["-map", "0:v", "-c:v", "copy", "-f", "fifo", "-fifo_format", "mpjpeg", "-drop_pkts_on_overflow",
                   "1", "-attempt_recovery", "0", "-queue_size", "60", "pipe:7"]
    assert value_after(argv, "-f", argv.index("-c:a")) == "tee"
    # no tap without a descriptor; a test run limits the tap output too
    assert "mpjpeg" not in sd.build_ffmpeg_argv(cfg, prefix="p", main="fifo")
    limited = sd.build_ffmpeg_argv(make_cfg(tmp_path, test_seconds=3, game_source="fifo"), prefix="p", main="fifo", tap_fd=9)
    assert limited[-17:-11] == ["-map", "0:v", "-c:v", "copy", "-t", "3"] and limited[-1] == "pipe:9"


def test_the_placeholder_is_a_visible_card_through_the_same_graph(tmp_path):
    cfg = make_cfg(tmp_path, fps=60, desktop_fps=60, game_source="fifo")
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", voice=False, cam2=False, layout="webcam", live=True,
                                main="placeholder", tap_fd=7)
    (game, gi), (desk, di), (silence, si) = inputs_of(argv)
    assert game == ["ffmpeg", "-hide_banner", "-stdin", "-loglevel", "warning", "-progress", "pipe:1", "-stats_period",
                    "5", "-filter_complex_threads", sd.FILTER_THREADS, "-re", "-f", "lavfi"] and gi == "smptehdbars=size=1920x1080:rate=60"
    graph = value_after(argv, "-filter_complex")
    assert graph.startswith("[0:v]fps=60,scale=1920:1080,setsar=1,format=yuv420p,split=4")   # no range change, no tpad
    assert "mpjpeg" not in argv and "main.mjpeg" not in " ".join(argv)                         # never a tap, never the FIFO
    assert "anullsrc" in si and di == ":102.0"


def test_x11_argv_does_not_change_with_the_new_parameters(tmp_path):
    for kw in ({}, {"fps": 60, "desktop_fps": 60, "encoder": "h264_nvenc", "hls_dir": tmp_path / "hls"}):
        for live in (True, False):
            for layout in sd.LIVE_ORDER:
                base = dict(prefix="p", window_id=7, voice=True, cam2=True, layout=layout, live=live)
                x11 = sd.build_ffmpeg_argv(make_cfg(tmp_path, **kw), **base)
                assert sd.build_ffmpeg_argv(make_cfg(tmp_path, **kw), **base, main=None, tap_fd=5) == x11
                assert sd.build_ffmpeg_argv(make_cfg(tmp_path, **kw), **base, main="x11") == x11
                assert "tpad=stop=-1:stop_mode=clone,scale=1920:1080:in_range" not in value_after(x11, "-filter_complex")


@pytest.mark.parametrize("layout", ["webcam", "desktop", "split", "room", "webcam_only"])
def test_every_restart_mode_graph_converts_the_fifo_main_view(tmp_path, layout):
    cfg = make_cfg(tmp_path, fps=60, desktop_fps=60, game_source="fifo")
    fifo = sd.build_filter_complex(layout, cfg, main="fifo")
    x11 = sd.build_filter_complex(layout, cfg)
    card = sd.build_filter_complex(layout, cfg, main="placeholder")
    assert card == x11                                                 # the card goes through today's chain
    game = re.findall(r"\[0:v\]([^\[;]*)", fifo)
    assert len(game) == 1 and "in_range=full:out_range=limited" in game[0]
    assert game[0].startswith(sd.WALL_PTS + ",fps=60,tpad=stop=-1:stop_mode=clone,scale=")   # wallclock stamps, rate, tpad
    pip = layout in ("desktop", "room")                                # x11's game PiP has no fps step of its own
    plain = re.sub(r"(\[0:v\][^\[;]*)", lambda m: m.group(1).replace(sd.WALL_PTS + ",", "").replace(",tpad=stop=-1:stop_mode=clone", "")
                   .replace(":in_range=full:out_range=limited", "").replace("[0:v]fps=60,", "[0:v]" if pip else
                                                                            "[0:v]fps=60,"), fifo)
    assert plain == x11                                                # nothing else in the graph changes
    if layout == "webcam_only":
        assert "[1:v]" not in fifo and "[3:v]" not in fifo                # the privacy graph: still no desktop


# --------------------------------------------------------------- main.json

def write_json(path, **fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields))


def test_main_json_freshness(tmp_path):
    path, now = tmp_path / "main.json", time.time()
    assert sd.main_report(path, now) is None and sd.main_freshness(None, 2.0) == (False, "no main.json next to the main FIFO")
    path.write_text("[1, 2]")
    assert sd.main_freshness(sd.main_report(path, now), 2.0) == (False, "main.json is not a JSON object")
    write_json(path, sequence=10, written=9, dropped_queue=1, fps=59.9)
    assert sd.main_freshness(sd.main_report(path, time.time()), 2.0) == (False, "main.json has no last_write_utc")
    write_json(path, written=9, last_write_utc=now - 2.5)
    assert sd.main_freshness(sd.main_report(path, now), 2.0)[1] == "main view last written 2.5s ago"
    write_json(path, written=9, last_write_utc=now - 0.25, sequence=12, dropped_slots=2, frames_discarded_midwrite=1)
    report = sd.main_report(path, now)
    assert sd.main_freshness(report, 2.0) == (True, "main view last written 0.2s ago")
    assert (report["written"], report["sequence"], report["dropped_slots"], report["frames_discarded_midwrite"],
            report["dropped_queue"]) == (9, 12, 2, 1, None)
    os.utime(path, (now - 3, now - 3))                                  # an old file: the game stopped writing it
    assert sd.main_freshness(sd.main_report(path, now), 2.0)[1] == "main.json 3.0s old"
    write_json(path, last_write_utc=datetime_iso(now - 0.5))            # ISO times are read too
    assert sd.main_freshness(sd.main_report(path, now), 2.0)[0] is True
    write_json(path, last_write_utc=(now - 0.5) * 1000, written=True, fps="x")        # milliseconds; junk counters
    report = sd.main_report(path, now)
    assert sd.main_freshness(report, 2.0)[0] is True and report["written"] is None and report["fps"] is None


def datetime_iso(unix):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(unix, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fake_proc(root, pid, fd, target, flags):
    (root / str(pid) / "fd").mkdir(parents=True, exist_ok=True)
    (root / str(pid) / "fdinfo").mkdir(parents=True, exist_ok=True)
    os.symlink(target, root / str(pid) / "fd" / str(fd))
    (root / str(pid) / "fdinfo" / str(fd)).write_text(f"pos:\t0\nflags:\t{flags}\nmnt_id:\t1\n")


def test_main_status_needs_the_fifo_a_writer_and_fresh_json(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    cfg = make_cfg(tmp_path, game_source="fifo")
    tap = sd.FifoTap(cfg.main_fifo, proc_root, create=False, what="main")
    sleeps = []
    status = lambda **kw: sd.main_status(cfg, tap, time.time(), sleep=sleeps.append, **kw)     # noqa: E731
    assert status() == (False, "main FIFO does not exist", None, True) and not cfg.main_fifo.exists()   # never created
    cfg.streamer_dir.mkdir(parents=True)
    cfg.main_fifo.write_bytes(b"")
    assert status()[1:] == ("main path is not a FIFO", None, True)
    cfg.main_fifo.unlink()
    os.mkfifo(cfg.main_fifo)
    assert status()[:2] == (False, "no main.json next to the main FIFO") and tap.fd is not None        # read end open
    write_json(cfg.main_json, written=1, last_write_utc=time.time())
    fresh, reason, report, hard = status()
    assert (fresh, reason, hard) == (False, "no process writes to the main FIFO", False) and report["written"] == 1
    assert sleeps == [sd.MAIN_WRITER_CONFIRM]                          # confirmed by a second scan before it counts
    assert status(writer=False)[0] is True and len(sleeps) == 1        # json only: no scan, no wait
    fake_proc(proc_root, 30, 9, cfg.main_fifo, "0104001")              # the game: O_WRONLY|O_NONBLOCK
    fresh, reason, _, hard = status()
    assert fresh and reason.endswith(", writer present") and not hard and len(sleeps) == 1
    tap.close()


def test_a_writer_back_within_the_confirmation_counts_as_present(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    cfg = make_cfg(tmp_path, game_source="fifo")
    cfg.streamer_dir.mkdir(parents=True)
    os.mkfifo(cfg.main_fifo)
    write_json(cfg.main_json, written=1, last_write_utc=time.time())
    tap = sd.FifoTap(cfg.main_fifo, proc_root, create=False, what="main")
    reopen = lambda seconds: fake_proc(proc_root, 31, 4, cfg.main_fifo, "0104001")      # noqa: E731
    assert sd.main_status(cfg, tap, time.time(), sleep=reopen)[0] is True
    tap.close()


# ------------------------------------------------------------ the seq tap

def jpeg(seq=None, com_first=True, extra_com=None, data=b"\x12\x34" * 50):
    """A synthetic JPEG: SOI, APP0 (JFIF), DQT, optional COM segments, SOS, data, EOI."""
    def seg(marker, payload):
        return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload
    app0 = seg(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00")
    dqt = seg(0xDB, b"\x00" + bytes(range(64)))
    coms = ([seg(0xFE, extra_com)] if extra_com is not None else []) + \
           ([seg(0xFE, b"seq=%d" % seq)] if seq is not None else [])
    head = app0 + (b"".join(coms) + dqt if com_first else dqt + b"".join(coms))
    return b"\xff\xd8" + head + seg(0xDA, b"\x01\x01\x00\x00\x3f\x00") + data + b"\xff\xd9"


def mpjpeg(frames):
    """ffmpeg's mpjpeg muxer output for these packets."""
    out = b"--ffmpeg\r\n"
    for frame in frames:
        out += b"Content-type: image/jpeg\r\nContent-length: %d\r\n\r\n" % len(frame) + frame + b"\r\n--ffmpeg\r\n"
    return out


def test_jpeg_seq_reads_the_com_marker_before_the_scan():
    assert sd.jpeg_seq(jpeg(7)) == 7 and sd.jpeg_seq(jpeg(123456789012, com_first=False)) == 123456789012
    assert sd.jpeg_seq(jpeg(5, extra_com=b"Lavc60.31.102")) == 5             # another comment first
    assert sd.jpeg_seq(jpeg(None)) is None and sd.jpeg_seq(jpeg(None, extra_com=b"seq=")) is None
    assert sd.jpeg_seq(jpeg(None, extra_com=b"seq=12x")) == 12 and sd.jpeg_seq(b"\x89PNG") is None
    assert sd.jpeg_seq(jpeg(9)[:12]) is None                                  # cut before the COM
    scan_first = b"\xff\xd8" + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00" + b"\xff\xfe\x00\x07seq=1"
    assert sd.jpeg_seq(scan_first) is None                                     # a COM after SOS is scan data
    assert sd.jpeg_seq(b"\xff\xd8\xff\xff" + jpeg(4)[2:]) == 4                  # fill byte


@pytest.mark.parametrize("chunk", [1, 7, 777, 1 << 20])
def test_seq_counter_counts_unique_repeated_gaps_and_unmarked_parts(chunk):
    seqs = [0, 1, 2, 2, 5, None, 6, 3, 1000, 10]       # repeat, gap of 2, no marker, out of order, jump, writer reset
    stream = mpjpeg([jpeg(s) for s in seqs])
    counter, t = sd.SeqCounter(), 0.0
    for i in range(0, len(stream), chunk):
        t += 0.001
        counter.feed(stream[i:i + chunk], t)
    snap = counter.snapshot()
    assert (snap["frames"], snap["unique"], snap["repeated"], snap["gaps"], snap["noseq"], snap["bad"]) == (
        10, 7, 2, 2 + 993, 1, 0)
    assert (snap["resets"], snap["first_seq"], snap["last_seq"]) == (1, 0, 10)
    assert counter.take_gap() >= (0.0 if chunk >= len(stream) else 0.001) and counter.take_gap() == 0.0


def test_a_cut_frame_is_not_unique_and_a_drained_start_is_tolerated():
    """A frame the game discarded mid-write reaches ffmpeg as a part without EOI; a part may start with the tail of a
    frame the director drained before ffmpeg took over (ffmpeg's parser keeps those bytes before the SOI)."""
    cut = jpeg(1)[:-40]                                   # no EOI: the game's deadline cut it
    stream = mpjpeg([b"\x55\x66\xff\xd9" + jpeg(0), cut, jpeg(2), jpeg(3)])
    counter = sd.SeqCounter()
    for i in range(0, len(stream), 5):
        counter.feed(stream[i:i + 5], 1.0)
    snap = counter.snapshot()
    assert (snap["frames"], snap["unique"], snap["cut"], snap["trimmed"], snap["gaps"], snap["noseq"]) == (
        4, 3, 1, 1, 1, 0)
    assert (snap["first_seq"], snap["max_seq"]) == (0, 3)


def test_seq_counter_resynchronises_after_a_broken_header():
    counter = sd.SeqCounter()
    good = mpjpeg([jpeg(1)])
    broken = b"Content-type: image/jpeg\r\nContent-length: 999999999999\r\n\r\n"      # beyond SEQ_MAX_PART
    counter.feed(broken + good[len(b"--ffmpeg\r\n"):] + mpjpeg([jpeg(2)]), 1.0)
    snap = counter.snapshot()
    assert snap["bad"] == 1 and snap["unique"] == 2 and snap["frames"] == 2
    counter.feed(b"Content-length: 0\r\n\r\n", 1.5)                              # a zero length is broken too
    assert counter.snapshot()["bad"] == 2 and counter.snapshot()["frames"] == 2
    counter.feed(b"x" * 5000, 2.0)                                               # no header end at all
    assert counter.snapshot()["bad"] >= 1 and len(counter._hdr) <= 2048
    counter.feed(b"\r\n\r\n" + mpjpeg([jpeg(3)]), 3.0)
    assert counter.snapshot()["unique"] == 3


def test_seq_tap_reads_a_real_pipe_until_eof():
    tap = sd.SeqTap()
    fd = tap.open()
    writer = os.dup(fd)                                    # what ffmpeg would inherit
    tap.parent_done()
    assert tap.write_fd is None and tap.eof_at is None
    os.write(writer, mpjpeg([jpeg(s) for s in range(40)]))
    os.close(writer)
    tap.close(timeout=5)
    snap = tap.counter.snapshot()
    assert snap["unique"] == 40 and snap["gaps"] == 0 and tap.eof_at is not None and tap.error is None


def test_a_counting_error_marks_the_tap_invalid_but_keeps_draining_it():
    """Kimi review: a reader that stops would fill ffmpeg's tap pipe, a closed one would end the tap output."""
    tap = sd.SeqTap()

    def broken(chunk, now):
        raise RuntimeError("parser bug")
    tap.counter.feed = broken
    fd = tap.open()
    writer = os.dup(fd)
    tap.parent_done()
    os.write(writer, b"x" * 1000)
    deadline = time.monotonic() + 5
    while tap.error is None and time.monotonic() < deadline:
        time.sleep(0.01)
    os.set_blocking(writer, True)
    os.write(writer, b"y" * (4 << 20))                    # more than any pipe holds: only a reader lets this finish
    os.close(writer)
    tap.close(timeout=5)
    assert tap.error == "RuntimeError: parser bug" and tap.eof_at is not None


# ------------------------------------------------------- the state machine

def test_main_source_first_launch_and_the_switch_back_needs_backoff_and_3s_fresh():
    m = sd.MainSource(fresh_need=3.0)
    m.observe(0.0, False, "main FIFO does not exist")
    assert m.choose(0.0) == "placeholder" and m.failures == 0 and m.retry_in(0.0) == 0   # not a failure: no game yet
    m.launched(0.0, "placeholder")
    for t in (1.0, 2.0, 3.0):
        m.observe(t, True, "fresh")
        assert m.tick(t, "placeholder") == "keep"                           # fresh 0, 1, 2 s: not yet 3
    m.observe(3.5, False, "main.json 2.1s old")                             # a break: the 3 s start again
    m.observe(4.0, True, "fresh")
    assert m.tick(6.9, "placeholder") == "keep" and m.fresh_for(6.9) == pytest.approx(2.9)
    m.observe(7.0, True, "fresh")
    assert m.tick(7.0, "placeholder") == "back" and m.state == "fifo" and m.choose(7.0) == "fifo"


def test_main_source_backoff_2_4_8_16_30_and_the_reset_after_60s():
    m = sd.MainSource(fresh_need=3.0)
    m.observe(0.0, True, "fresh")
    assert m.choose(0.0) == "fifo"
    now, delays = 0.0, []
    for _ in range(7):
        m.launched(now, "fifo")
        now += 5
        m.observe(now, False, "main view last written 2.3s ago")
        assert m.tick(now, "fifo") == "stale" and m.state == "placeholder"
        delays.append(m.retry_in(now))
        m.launched(now, "placeholder")
        m.observe(now, True, "fresh")                                       # fresh again at once ...
        back_at = now + max(delays[-1], 3.0)
        assert m.tick(back_at - 0.01, "placeholder") == "keep"              # ... but backoff and 3 s fresh both hold
        assert m.tick(back_at, "placeholder") == "back" and m.state == "fifo"
        now = back_at
    assert delays == [2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0] and m.failures == 7
    m.launched(now, "fifo")
    m.observe(now, True, "fresh")
    m.observe(now + 59, True, "fresh")
    assert m.tick(now + 59, "fifo") == "keep" and m.failures == 7
    m.observe(now + 60, True, "fresh")
    assert m.tick(now + 60, "fifo") == "keep" and m.failures == 0 and m.retry_at is None


def test_main_source_stale_between_runs_and_a_short_fifo_run_are_failures():
    m = sd.MainSource()
    m.observe(0.0, True, "fresh")
    m.launched(0.0, m.choose(0.0))
    m.observe(10.0, False, "no process writes to the main FIFO")
    assert m.choose(10.0) == "placeholder" and m.failures == 1 and m.retry_in(10.0) == 2.0   # relaunch for another reason
    m2 = sd.MainSource()
    m2.observe(0.0, True, "fresh")
    m2.launched(0.0, m2.choose(0.0))
    assert m2.exited(5.0, "fifo", 5.0, "ffmpeg exited after 5s on the FIFO") is True
    assert m2.state == "placeholder" and m2.reason.startswith("ffmpeg exited") and m2.retry_in(5.0) == 2.0
    m3 = sd.MainSource()
    m3.observe(0.0, True, "fresh")
    m3.launched(0.0, m3.choose(0.0))
    assert m3.exited(100.0, "fifo", 100.0, "x") is False and m3.state == "fifo"           # a long run: ffmpeg's backoff
    assert m3.exited(1.0, "placeholder", 1.0, "x") is False
    assert sd.MainSource().tick(0.0, None) == "keep"                                         # nothing on air


# -------------------------------------------------------------- the meter

def progress(frame, out_s, end=False):
    return [f"frame={frame}", "fps=60.0", f"out_time_us={int(out_s * 1e6)}", "dup_frames=0", "drop_frames=0",
            "speed=1.0x", f"progress={'end' if end else 'continue'}"]


def test_output_meter_rows_carry_unique_main_view_frames_and_game_written():
    counts = {"source": "fifo", "frames": 0, "unique": 0, "repeated": 0, "gaps": 0, "noseq": 0, "bad": 0,
              "overflows": 0, "tap_error": False, "game_written": 100, "game_dropped": 3, "gap_s": 0.0}
    seen = []

    def main():
        seen.append(1)
        return dict(counts)
    meter, records = sd.OutputMeter(10, "sub01-r", main=main), []
    for now, frame in ((0.0, 0), (5.0, 300), (10.5, 630), (15.5, 930)):
        counts.update(frames=frame, unique=frame, repeated=1 if now else 0, game_written=100 + frame,
                      gap_s=0.02 if now < 10 else 0.25)
        for line in progress(frame, now):
            records += meter.feed(line, now)
    assert len(seen) == 4 and meter.latest["main_fps"] == 60.0 and meter.latest["main_max_gap_ms"] == 250
    (row,) = records
    assert row["segment"] == "sub01-r-000.mp4" and row["main_source"] == "fifo"
    assert (row["main_frames"], row["main_unique"], row["main_fps"], row["main_repeated"]) == (630, 630, 60.0, 1)
    assert (row["game_written"], row["game_fps"], row["game_dropped"], row["main_tap_ok"]) == (630, 60.0, 0, True)
    assert row["main_max_gap_ms"] == 250                                   # the window's longest gap, not a sum
    counts.update(noseq=1, game_written=5)                                 # an unmarked part; the game restarted
    end = [r for line in progress(1170, 19.5, end=True) for r in meter.feed(line, 19.5)]
    assert end[0]["main_tap_ok"] is False and end[0]["game_written"] is None and end[0]["partial"] is True
    x11 = sd.OutputMeter(10, "sub01-x")
    rows = [r for now, frame in ((0.0, 0), (10.5, 630)) for line in progress(frame, now) for r in x11.feed(line, now)]
    assert set(rows[0]) == {"segment", "frames", "wall_s", "media_s", "fps", "fps_media", "dup_frames", "drop_frames",
                            "partial"}                                     # x11 rows exactly as before
    assert not any(k.startswith("main") for k in x11.latest)


def test_placeholder_rows_say_so_with_zero_unique_frames():
    meter = sd.OutputMeter(10, "sub01-p", main=lambda: {"source": "placeholder", "game_written": None, "game_dropped": None})
    rows = [r for now, frame in ((0.0, 0), (10.5, 630)) for line in progress(frame, now) for r in meter.feed(line, now)]
    assert rows[0]["main_source"] == "placeholder" and rows[0]["main_fps"] == 0.0 and rows[0]["main_tap_ok"] is None
    broken = sd.OutputMeter(10, "sub01-b", main=lambda: 1 / 0)             # a broken counter never stops the meter
    assert [r for line in progress(0, 0.0) for r in broken.feed(line, 0.0)] == [] and broken.latest["frames"] == 0


# ------------------------------------------------------- the director (fakes)

class FakeStream:
    async def readline(self):
        return b""


class FakeProc:
    """ffmpeg stand-in. Holds a dup of the tap's write end like the real child, writes `parts` into it."""

    def __init__(self, pid, tap_fd=None, exit_after=None, code=1, ignore_sigint=0):
        self.pid, self.returncode, self.signals = pid, None, []
        self.stderr, self.stdout = FakeStream(), FakeStream()
        self._done = asyncio.Event()
        self.tap = os.dup(tap_fd) if tap_fd is not None else None
        self.ignore_sigint = ignore_sigint
        if exit_after is not None:
            asyncio.get_running_loop().call_later(exit_after, self._exit, code)

    def write_parts(self, data):
        os.write(self.tap, data)

    def _exit(self, code):
        if self.returncode is None:
            self.returncode = code
            if self.tap is not None:
                os.close(self.tap)
                self.tap = None
            self._done.set()

    async def wait(self):
        await self._done.wait()
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        if sig == signal.SIGINT and self.signals.count(signal.SIGINT) <= self.ignore_sigint:
            return
        self._exit(255)

    def kill(self):
        self.signals.append(signal.SIGKILL)
        self._exit(-9)


class MainCheck:
    """check_main stand-in: the answer is set by the test; every call is recorded with its `writer` flag."""

    def __init__(self, fresh=True, reason="main view last written 0.1s ago", hard=False):
        self.answer, self.calls = (fresh, reason, {"written": 10, "age_s": 0.2, "last_write_age_s": 0.1}, hard), []

    def set(self, fresh, reason, hard=False, **report):
        self.answer = (fresh, reason, {"written": 10, **report}, hard)

    def __call__(self, writer=True):
        self.calls.append(writer)
        return self.answer


def fifo_director(tmp_path, procs, check=None, clock=None, **kw):
    kw.setdefault("main_interval", 100.0)               # the main tick loop never fires by itself: tests tick by hand
    cfg = make_cfg(tmp_path, game_source="fifo", **kw)
    launched = []

    async def spawn(argv, pass_fds=()):
        proc = procs[len(launched)](pass_fds[0] if pass_fds else None)
        launched.append((argv, proc, pass_fds))
        return proc

    async def quick_sleep(seconds):                     # long intervals (the tick loops) never fire: tests tick by hand
        await asyncio.sleep(0.01 if seconds < 5 else 3600)

    check = check or MainCheck()
    director = sd.Director(cfg, spawn=spawn, check_main=check, check_voice=lambda: (False, "no writer"),
                           check_cam2=lambda writer=True: (False, "no cam2", None), sleep=quick_sleep,
                           **({"clock": clock} if clock else {}))
    return director, launched, check


async def until(predicate, timeout=5.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end, "condition never became true"
        await asyncio.sleep(0.01)


def test_a_fresh_fifo_launches_with_the_tap_and_x11_never_looks(tmp_path):
    async def body():
        director, launched, check = fifo_director(tmp_path, [lambda fd: FakeProc(11, fd)])
        director._find_window = lambda: pytest.fail("fifo mode never looks for a game window")
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        argv, proc, pass_fds = launched[0]
        assert len(pass_fds) == 1 and argv[-1] == f"pipe:{pass_fds[0]}" and str(director.cfg.main_fifo) in argv
        assert director.seq_tap is not None and director.seq_tap.write_fd is None          # the parent's end is closed
        proc.write_parts(mpjpeg([jpeg(s) for s in range(30)]))
        await until(lambda: director.seq_tap.counter.snapshot()["unique"] == 30)
        state = director.state()
        assert state["game_source"] == "fifo:main.mjpeg" and state["main"]["source"] == "fifo"
        assert state["main"]["tap"]["unique"] == 30 and state["main"]["tap"]["eof"] is False
        started = [e for e in events(tmp_path) if e["kind"] == "ffmpeg_started"][0]
        assert started["main"] == "fifo" and started["seq_tap"] is True and started["game"] == "fifo:main.mjpeg"
        assert [(e["main"], e["previous"]) for e in events(tmp_path) if e["kind"] == "main_changed"] == [("fifo", None)]
        director.stop()
        await asyncio.wait_for(task, 5)
        assert director.seq_tap.eof_at is not None                         # the reader thread ended with "ffmpeg"
    run(body())


def test_main_tick_stale_after_the_launch_grace_relaunches_on_the_placeholder_and_back(tmp_path):
    async def body():
        now = [1000.0]
        procs = [lambda fd: FakeProc(1, fd), lambda fd: FakeProc(2, fd), lambda fd: FakeProc(3, fd)]
        director, launched, check = fifo_director(tmp_path, procs, clock=lambda: now[0])
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        check.set(False, "main view last written 2.4s ago")
        now[0] += 1.0
        assert await director.main_tick() == "grace" and director._restart_reason is None   # ffmpeg's own start-up
        now[0] += 2.5
        assert await director.main_tick() == "stale"
        assert director._restart_reason == "main view stale: main view last written 2.4s ago" and director._stop_quick
        await until(lambda: len(launched) == 2 and director.alive)
        assert launched[0][1].signals == [signal.SIGINT]                    # it left at the first SIGINT
        argv, _, pass_fds = launched[1]
        assert "smptehdbars=size=1920x1080:rate=24" in argv and pass_fds == () and director.seq_tap is None
        assert director.state()["main"]["source"] == "placeholder" and director.state()["main"]["retry_in_s"] == 2.0
        assert director._failures == 0                                      # not a crash
        check.set(True, "main view last written 0.1s ago, writer present")
        for _ in range(3):                                                   # fresh, but backoff and 3 s not yet over
            now[0] += 1.0
            assert await director.main_tick() == "keep"
        now[0] += 1.0
        assert await director.main_tick() == "back" and director._restart_reason == "main view back"
        await until(lambda: len(launched) == 3 and director.alive)
        assert str(director.cfg.main_fifo) in launched[2][0] and launched[2][2]
        changes = [(e["main"], e["previous"], e.get("failures")) for e in events(tmp_path) if e["kind"] == "main_changed"]
        assert changes == [("fifo", None, 0), ("placeholder", "fifo", 1), ("fifo", "placeholder", 1)]
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_a_replaced_fifo_or_a_tap_eof_is_stale_at_once_even_in_the_grace(tmp_path):
    async def body():
        director, launched, check = fifo_director(tmp_path, [lambda fd: FakeProc(1, fd), lambda fd: FakeProc(2, fd)])
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        director._main_ident = (1, 2)
        director.main_tap.ident = (1, 3)
        assert await director.main_tick() == "stale" and "replaced" in director._restart_reason
        await until(lambda: len(launched) == 2 and director.alive)
        director.stop()
        await asyncio.wait_for(task, 5)
        d2, launched2, _ = fifo_director(tmp_path / "b", [lambda fd: FakeProc(1, fd), lambda fd: FakeProc(2, fd)])
        task = asyncio.ensure_future(d2.run())
        await until(lambda: d2.alive)
        proc = launched2[0][1]
        os.close(proc.tap)                                                 # input 0 ended: ffmpeg closes the tap
        proc.tap = None
        await until(lambda: d2.seq_tap.eof_at is not None)
        assert await d2.main_tick() == "stale" and "tap EOF" in d2._restart_reason
        d2.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_the_writer_scan_runs_every_5th_tick_on_the_fifo_and_every_tick_on_the_placeholder(tmp_path):
    async def body():
        director, launched, check = fifo_director(tmp_path, [lambda fd: FakeProc(1, fd)])
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        check.calls.clear()
        for _ in range(10):
            await director.main_tick()
        assert check.calls == [False, False, False, False, True] * 2
        director.main_on = "placeholder"
        check.calls.clear()
        await director.main_tick()
        assert check.calls == [True]
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_a_short_fifo_run_that_crashes_goes_to_the_placeholder_without_the_crash_backoff(tmp_path):
    async def body():
        procs = [lambda fd: FakeProc(1, fd, exit_after=0.05, code=1), lambda fd: FakeProc(2, fd)]
        director, launched, check = fifo_director(tmp_path, procs)
        task = asyncio.ensure_future(director.run())
        await until(lambda: len(launched) == 2 and director.alive)
        assert "smptehdbars" in " ".join(launched[1][0]) and director._failures == 0
        kinds = [e["kind"] for e in events(tmp_path)]
        assert kinds.index("ffmpeg_exited") < kinds.index("main_changed", kinds.index("ffmpeg_exited"))
        sched = [e for e in events(tmp_path) if e["kind"] == "ffmpeg_restart_scheduled"]
        assert sched[0]["outcome"] == "main_failed" and sched[0]["delay"] == 1.0
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_stopping_a_fifo_run_sends_a_second_sigint_then_kills(tmp_path):
    async def body():
        director, _, _ = fifo_director(tmp_path, [])
        stubborn = FakeProc(1, ignore_sigint=1)
        await director._terminate(stubborn, grace=0.2, nudge=0.05)
        assert stubborn.signals == [signal.SIGINT, signal.SIGINT] and stubborn.returncode == 255
        blocked = FakeProc(2, ignore_sigint=5)                      # a read blocked on a silent writer
        await director._terminate(blocked, grace=0.2, nudge=0.05)
        assert blocked.signals == [signal.SIGINT, signal.SIGINT, signal.SIGKILL] and blocked.returncode == -9
        plain = FakeProc(3, ignore_sigint=1)                        # x11 runs: as before, SIGINT then SIGKILL
        await director._terminate(plain, grace=0.05)
        assert plain.signals == [signal.SIGINT, signal.SIGKILL]
    run(body())


def test_tap_overflow_and_idle_are_reported_and_drain_only_off_the_fifo(tmp_path):
    async def body():
        now = [500.0]
        director, launched, check = fifo_director(tmp_path, [lambda fd: FakeProc(1, fd)], clock=lambda: now[0])
        drained = []
        director.main_tap.drain = lambda limit=None: drained.append(limit)
        await director.drain_tick()
        assert drained == [sd.MAIN_DRAIN]                              # nothing runs: the director is the reader
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        drained.clear()
        await director.drain_tick()
        assert drained == []                                           # ffmpeg reads main.mjpeg: hands off
        director.stderr_line("[fifo @ 0x55] FIFO queue full")
        assert director.tap_overflows == 1 and director._main_counts()["overflows"] == 1
        now[0] += 10.0                                                 # no frame since the launch, past the grace
        await director.main_tick()
        assert director.tap_idle and director.state()["main"]["tap"]["idle_s"] == 10.0
        launched[0][1].write_parts(mpjpeg([jpeg(1)]))
        await until(lambda: director.seq_tap.counter.snapshot()["frames"] == 1)
        await director.main_tick()
        assert not director.tap_idle
        assert [e["kind"] for e in events(tmp_path) if e["kind"].startswith("main_tap")] == [
            "main_tap_idle", "main_tap_flowing"]
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_no_drain_while_a_fifo_run_is_being_spawned(tmp_path):
    """Kimi review: ffmpeg may read main.mjpeg before the spawn returns; a drain then would split a JPEG."""
    async def body():
        seen = []
        director, launched, check = fifo_director(tmp_path, [])
        director.main_tap.drain = lambda limit=None: seen.append(("drain", director._main_handoff))

        async def slow_spawn(argv, pass_fds=()):
            await director.drain_tick()                     # a drain tick lands while the spawn is in flight
            seen.append(("spawn", director._main_handoff))
            return FakeProc(1, pass_fds[0] if pass_fds else None)
        director._spawn = slow_spawn
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)
        assert ("spawn", True) in seen and not any(kind == "drain" and handoff for kind, handoff in seen)
        assert director._main_handoff is False
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_a_check_that_outlived_its_run_and_the_grace_still_observes(tmp_path):
    async def body():
        now = [100.0]
        director, launched, check = fifo_director(tmp_path, [lambda fd: FakeProc(1, fd)], clock=lambda: now[0])
        task = asyncio.ensure_future(director.run())
        await until(lambda: director.alive)

        def relaunched_meanwhile(writer=True):
            director.launches += 1                           # another run started while the check ran
            return False, "main view last written 2.6s ago", {"written": 1}, False
        director._check_main = relaunched_meanwhile
        assert await director.main_tick() == "superseded" and director._restart_reason is None
        director.launches -= 1
        director._check_main = check
        check.set(False, "main view last written 2.6s ago")
        now[0] += 1.0
        assert await director.main_tick() == "grace"
        assert director.main_source.fresh is False and director.main_source.fresh_since is None   # observed anyway
        check.set(True, "fresh")
        now[0] += 1.0
        assert await director.main_tick() == "keep" and director.main_source.fresh_for(now[0]) == 0.0
        director.stop()
        await asyncio.wait_for(task, 5)
    run(body())


def test_the_tap_is_closed_when_the_command_line_cannot_be_built(tmp_path, monkeypatch):
    async def body():
        director, launched, check = fifo_director(tmp_path, [lambda fd: FakeProc(1, fd)])
        taps = []
        real = sd.SeqTap

        class Recorded(real):
            def __init__(self, *a, **k):
                super().__init__(*a, **k)
                taps.append(self)
        monkeypatch.setattr(sd, "SeqTap", Recorded)

        def broken(*a, **k):
            raise ValueError("bad argv")
        monkeypatch.setattr(sd, "build_ffmpeg_argv", broken)
        assert await director._run_once() == "crash" and launched == []
        assert taps and taps[0].eof_at is not None and taps[0].write_fd is None   # reader ended, both ends closed
        assert director._main_handoff is False and "bad argv" in director.last_error
    run(body())


def test_x11_mode_has_no_main_tick_and_its_rows_are_unchanged(tmp_path):
    async def body():
        cfg = make_cfg(tmp_path)
        director = sd.Director(cfg, check_main=lambda writer=True: pytest.fail("x11 mode never checks main.mjpeg"))
        assert await director.main_tick() == "idle" and director.state()["main"] is None
        drained = []
        director.main_tap.drain = lambda limit=None: drained.append(limit)
        await director.drain_tick()
        assert drained == []
    run(body())


def test_the_reaper_finds_fifo_and_placeholder_recorders(tmp_path):
    cfg = make_cfg(tmp_path, game_source="fifo", test_sources=True)
    root = tmp_path / "proc"
    rec = str(cfg.recordings_dir / "r-%03d.mp4")
    for pid, argv in ((21, ["ffmpeg", "-f", "mjpeg", "-follow", "1", "-i", str(cfg.main_fifo), "-f", "lavfi", "-i",
                            "color=c=red", rec]),
                      (22, ["ffmpeg", "-re", "-f", "lavfi", "-i", "smptehdbars=size=320x180:rate=30", rec]),
                      (23, ["ffmpeg", "-f", "lavfi", "-i", "color=c=red", rec]),                 # neither: not ours
                      (24, ["ffmpeg", "-i", str(cfg.main_fifo), "/elsewhere/x.mp4"])):          # another directory
        (root / str(pid)).mkdir(parents=True)
        (root / str(pid) / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    assert sd.recorder_pids(cfg, root) == [21, 22]


def test_print_argv_in_fifo_mode_looks_without_reading(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sd, "find_game_window", lambda cfg: pytest.fail("no window lookup in fifo mode"))
    monkeypatch.setattr(sd.VoiceTap, "writer_present", lambda self, settle=None: (False, "no writer"))
    monkeypatch.setattr(sd, "main_status", lambda cfg, tap, now, **kw: (True, "main view last written 0.1s ago", {}, False))
    assert sd.main(["--print-argv", "--streamer-dir", str(tmp_path), "--game-source", "fifo"]) == 0
    out = capsys.readouterr().out
    assert "main view: fifo" in out and "-follow 1" in out and "pipe:3" in out and "mpjpeg" in out
    monkeypatch.setattr(sd, "main_status", lambda cfg, tap, now, **kw: (False, "main FIFO does not exist", None, True))
    assert sd.main(["--print-argv", "--streamer-dir", str(tmp_path), "--game-source", "fifo"]) == 0
    out = capsys.readouterr().out
    assert "main view: placeholder (main FIFO does not exist)" in out and "smptehdbars" in out and "mpjpeg" not in out


# ----------------------------------------------- real ffmpeg against a FIFO

def phase_runs(tmp_path):
    started = [e for e in events(tmp_path) if e["kind"] == "ffmpeg_started"]
    return [(e["run"], e["main"]) for e in started]


def mean_luma(path, ffmpeg):
    done = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-vf", "signalstats,metadata=print:key="
                           "lavfi.signalstats.YAVG:file=-", "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    values = [float(v) for v in re.findall(r"YAVG=([\d.]+)", done.stdout)]
    return values


def recorded_taps(monkeypatch):
    """Every SeqTap the director creates, in order (one per FIFO run)."""
    taps, real = [], sd.SeqTap

    class Recorded(real):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            taps.append(self)
    monkeypatch.setattr(sd, "SeqTap", Recorded)
    return taps


@needs_ffmpeg
def test_real_ffmpeg_fifo_start_blip_stall_gone_and_back(tmp_path, monkeypatch):
    """The real Director and ffmpeg in fifo mode (lavfi desktop/voice/cam2, a real main.mjpeg written by GameWriter):
    the game starts after the director (placeholder first), a 0.4 s writer blip passes without a relaunch (-follow), a
    stall and the writer gone keep the placeholder on, the writer back returns to the FIFO. The output keeps running,
    the tap counts every frame written while a FIFO run read (no gap between its first and last sequence), the
    placeholder runs are never black."""
    taps = recorded_taps(monkeypatch)
    frames = gw.make_jpegs(FFMPEG, tmp_path / "jpg")
    _, cfg = sd.parse_args(["--streamer-dir", str(tmp_path / "streamer"), "--test-sources", "--size", "320x180",
                            "--pip-size", "96x54", "--fps", "30", "--desktop-fps", "30", "--preset", "ultrafast",
                            "--game-source", "fifo", "--main-interval", "0.25", "--main-stale", "1.0",
                            "--main-fresh", "1.5", "--layout-switch", "live", "--ffmpeg", FFMPEG])
    cfg = sd.DirectorConfig(**{**cfg.__dict__, "stats_period": 0.5})
    writer = gw.GameWriter(cfg.streamer_dir, frames, fps=30)
    marks = {}

    async def body():
        director = sd.Director(cfg)
        task = asyncio.ensure_future(director.run())
        try:
            await until(lambda: director.alive and director.main_on == "placeholder"
                        and (director.meter.latest or {}).get("frames", 0) >= 15, timeout=30)
            writer.start()
            await until(lambda: director.alive and director.main_on == "fifo"
                        and director.seq_tap.counter.snapshot()["unique"] >= 60, timeout=30)
            fifo_run = director.prefix
            writer.set_mode("gone")                                     # a blip: the game closes and reopens
            await asyncio.sleep(0.4)
            writer.set_mode("run")
            await asyncio.sleep(3.0)
            assert director.prefix == fifo_run and director.main_on == "fifo", "a 0.4 s blip must not relaunch"
            marks["blip_unique"] = director.seq_tap.counter.snapshot()["unique"]
            writer.set_mode("stall")
            await until(lambda: director.alive and director.main_on == "placeholder", timeout=15)
            out_before = (director.meter.latest or {}).get("frames", 0)
            writer.set_mode("gone")
            await asyncio.sleep(2.0)
            assert director.main_on == "placeholder" and director.alive
            assert (director.meter.latest or {}).get("frames", 0) > out_before            # the output keeps running
            writer.set_mode("run")
            await until(lambda: director.alive and director.main_on == "fifo"
                        and director.seq_tap.counter.snapshot()["unique"] >= 45, timeout=30)
            await asyncio.sleep(3.0)
        finally:
            director.stop()
            await asyncio.wait_for(task, 30)
            writer.stop()
        return director

    director = run(body())
    runs = phase_runs(tmp_path)
    assert [m for _, m in runs] == ["placeholder", "fifo", "placeholder", "fifo"], runs
    changes = [(e["main"], e["previous"]) for e in events(tmp_path) if e["kind"] == "main_changed"]
    assert changes == [("placeholder", None), ("fifo", "placeholder"), ("placeholder", "fifo"), ("fifo", "placeholder")]
    stale = [e for e in events(tmp_path) if e["kind"] == "main_changed" and e["main"] == "placeholder" and e["previous"]]
    assert "last written" in stale[0]["reason"] and stale[0]["failures"] == 1
    rows = [e for e in events(tmp_path) if e["kind"] == "segment_fps"]
    fifo_runs = [run_id for run_id, main in runs if main == "fifo"]
    assert len(taps) == len(fifo_runs) == 2
    for (run_id, main) in runs:
        mine = [r for r in rows if r["run"] == run_id]
        assert mine and all(r["main_source"] == main for r in mine)
        if main == "placeholder":
            assert all(r["main_unique"] == 0 and r["main_fps"] == 0.0 and r["main_tap_ok"] is None for r in mine)
            continue
        for r in mine:                                                  # every row of a FIFO run, not only the last
            assert r["main_tap_ok"] is True and r["main_frames"] == r["main_unique"], r
            assert (r["main_gaps"], r["main_repeated"], r["main_noseq"], r["main_bad"], r["main_cut"],
                    r["main_overflows"]) == (0, 0, 0, 0, 0, 0), r
        snap = taps[fifo_runs.index(run_id)].counter.snapshot()
        assert taps[fifo_runs.index(run_id)].error is None
        assert (snap["gaps"], snap["repeated"], snap["noseq"], snap["bad"], snap["cut"]) == (0, 0, 0, 0, 0), snap
        assert snap["unique"] == snap["max_seq"] - snap["first_seq"] + 1 and snap["trimmed"] <= 1, snap
        # the rows close at progress blocks (every 0.5 s here): at most a block's frames after the last one are missing
        assert 0 <= snap["unique"] - sum(r["main_unique"] for r in mine) <= 45, (snap, mine)
    assert sum(t.counter.snapshot()["unique"] for t in taps) <= writer.written
    assert marks["blip_unique"] >= 60 + 2 * 30                                  # frames kept coming through the blip
    # the recordings: every run decodes, the placeholder runs show the bars (never black), the output kept its pace
    files = sorted(cfg.recordings_dir.glob("sub01-*.mp4"))
    assert len(files) == 4
    total = 0
    for path, (run_id, main) in zip(files, runs):
        luma = mean_luma(path, FFMPEG)
        assert len(luma) >= 15, path
        total += len(luma)
        if main == "placeholder":
            assert min(luma) > 50, (path.name, luma[:5])                        # SMPTE bars, not a black frame
    assert all(r["fps_media"] and r["fps_media"] > 25 for r in rows if r["wall_s"] >= 3), rows
    assert writer.written > 300 and director.state()["main"]["failures"] >= 1


@needs_ffmpeg
def test_real_ffmpeg_a_stalled_tap_reader_never_stops_the_recording(tmp_path, monkeypatch):
    """Kimi review: the director's tap reader stops reading for 8 s (outside the counter's lock). ffmpeg's dropping fifo
    muxer overflows ("FIFO queue full"), the recording keeps its pace on the same run, the window's count is marked
    invalid (main_tap_ok false, overflows and gaps counted), and the tap is reported idle, then flowing again."""
    import threading
    stall = threading.Event()

    def stalling_read(self):
        fd = self.read_fd
        try:
            while True:
                if stall.is_set():
                    time.sleep(8.0)
                    stall.clear()
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                self.counter.feed(chunk, self._clock())
        finally:
            self.eof_at = self._clock()
            os.close(fd)
    monkeypatch.setattr(sd.SeqTap, "_read", stalling_read)
    frames = gw.make_jpegs(FFMPEG, tmp_path / "jpg", size="640x360")       # bigger parts: the pipe fills sooner
    _, cfg = sd.parse_args(["--streamer-dir", str(tmp_path / "streamer"), "--test-sources", "--size", "320x180",
                            "--pip-size", "96x54", "--fps", "30", "--desktop-fps", "30", "--preset", "ultrafast",
                            "--game-source", "fifo", "--main-interval", "0.25", "--main-stale", "1.0",
                            "--ffmpeg", FFMPEG])
    cfg = sd.DirectorConfig(**{**cfg.__dict__, "stats_period": 0.5})
    writer = gw.GameWriter(cfg.streamer_dir, frames, fps=30).start()
    seen = {}

    async def body():
        director = sd.Director(cfg)
        task = asyncio.ensure_future(director.run())
        try:
            await until(lambda: director.alive and director.main_on == "fifo" and director.seq_tap
                        and director.seq_tap.counter.snapshot()["unique"] >= 30, timeout=30)
            seen["run"], before = director.prefix, (director.meter.latest or {}).get("frames", 0)
            seen["launches_before"] = director.launches         # the game's first frame may follow the director's start
            stall.set()
            await asyncio.sleep(8.5)
            seen["during"] = (director.meter.latest or {}).get("frames", 0) - before
            await until(lambda: not stall.is_set() and director.tap_overflows >= 1, timeout=10)
            unique = director.seq_tap.counter.snapshot()["unique"]
            await until(lambda: director.seq_tap.counter.snapshot()["unique"] >= unique + 30, timeout=10)
            seen["state"] = director.state()["main"]
            seen["launches"], seen["run_after"] = director.launches, director.prefix
        finally:
            director.stop()
            await asyncio.wait_for(task, 30)
            writer.stop()

    run(body())
    stops = [(e["kind"], e.get("reason"), e.get("main")) for e in events(tmp_path) if e["kind"] in ("ffmpeg_stopped", "ffmpeg_exited", "main_changed", "ffmpeg_started", "watchdog_restart", "speed_restart")]
    assert seen["launches"] == seen["launches_before"] and seen["run_after"] == seen["run"], stops   # no relaunch
    assert seen["during"] >= 25 * 7, seen                                  # the output kept its pace during the stall
    assert seen["state"]["source"] == "fifo" and seen["state"]["tap"]["overflows"] >= 1
    rows = [e for e in events(tmp_path) if e["kind"] == "segment_fps" and e["run"] == seen["run"]]
    assert any(r["main_tap_ok"] is False and r["main_overflows"] >= 1 and r["main_gaps"] > 0 for r in rows), rows
    kinds = [e["kind"] for e in events(tmp_path)]
    assert "main_tap_idle" in kinds and "main_tap_flowing" in kinds and "main_changed" in kinds
    changes = [e["main"] for e in events(tmp_path) if e["kind"] == "main_changed"]
    assert changes[-1] == "fifo" and changes.count("placeholder") <= 1      # the stall never sent it to the card
