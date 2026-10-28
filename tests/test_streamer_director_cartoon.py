"""Streamer director, cartoon mode (`--cartoon-fifo PATH`): one more MJPEG FIFO input and the layout `cartoon`.

Without the flag nothing changes (argv, graph, layout names, state: tests/test_streamer_director.py pins that and the
byte-identity checks here compare against the same builders); with it the input sits after cam2 and before the music
and apps inputs, `cartoon` is the LAST streamselect input, and the layout is selectable live. Fake ffmpeg processes and
a fake /proc tree, plus one real ffmpeg smoke run on lavfi test sources.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_streamer_director as base  # noqa: E402  (its helpers: fake processes, fake ffmpeg stdin, make_director)

sd = base.sd
AUTH, TOKEN = base.AUTH, base.TOKEN
FIFO = "/run/sub01/cartoon.mjpeg"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def cfg_for(tmp_path, cartoon=True, **kw):
    return sd.DirectorConfig(streamer_dir=tmp_path / "streamer", cartoon_fifo=FIFO if cartoon else None, **kw)


def graph_of(argv):
    return base.value_after(argv, "-filter_complex")


def input_paths(argv):
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-i"]


# ------------------------------------------------------------- without the flag: nothing changes

@pytest.mark.parametrize("live", [True, False])
@pytest.mark.parametrize("cam2", [False, True])
@pytest.mark.parametrize("layout", ["webcam", "desktop", "split", "room", "webcam_only"])
def test_without_the_flag_the_argv_and_graph_are_what_they_were(tmp_path, live, cam2, layout):
    plain = cfg_for(tmp_path, cartoon=False)
    flagged = cfg_for(tmp_path, cartoon=True)
    argv = sd.build_ffmpeg_argv(plain, prefix="p", window_id=7, cam2=cam2, layout=layout, live=live)
    assert "cartoon" not in " ".join(argv) and argv.count("-i") == (4 if cam2 else 3)
    # the feature present but this run not reading the FIFO (no writer at launch): the same argv, byte for byte
    assert sd.build_ffmpeg_argv(flagged, prefix="p", window_id=7, cam2=cam2, layout=layout, live=live, cartoon=False) == argv
    assert sd.build_live_graph(plain, cam2, layout) == sd.build_live_graph(plain, cam2, layout, cartoon=False)
    assert sd.build_filter_complex(layout, plain) == sd.build_filter_complex(layout, plain, cam2=cam2)
    assert "cartoon" not in sd.build_live_graph(plain, cam2, layout)


def test_without_the_flag_the_layout_set_is_unchanged_and_cartoon_is_unknown(tmp_path):
    assert "cartoon" not in sd.LAYOUTS and "cartoon" not in sd.LIVE_ORDER
    assert sd.live_order(False) == ("webcam", "desktop", "split", "webcam_only")
    assert sd.live_order(True) == ("webcam", "desktop", "split", "room", "webcam_only")
    assert str(_unknown("cartoon")) == str(_unknown("pip")) == (
        "layout must be one of webcam, desktop, split, room, webcam_only (character = webcam)")
    with pytest.raises(ValueError):
        sd.DirectorConfig(streamer_dir=tmp_path, layout="cartoon")
    log = tmp_path / "layout.jsonl"
    log.write_text(json.dumps({"layout": "cartoon"}) + "\n")
    assert sd.read_last_layout(log) is None                       # an old line naming it changes nothing
    assert sd.parse_args(["--streamer-dir", str(tmp_path)])[1].cartoon_fifo is None


# ------------------------------------------------------------------ with the flag: input and layout

def test_flag_parses_to_the_config(tmp_path):
    args, cfg = sd.parse_args(["--streamer-dir", str(tmp_path), "--cartoon-fifo", str(tmp_path / "c.mjpeg")])
    assert args.cartoon_fifo == str(tmp_path / "c.mjpeg") and cfg.cartoon_fifo == tmp_path / "c.mjpeg"
    assert sd.parse_args(["--streamer-dir", str(tmp_path), "--layout", "cartoon", "--cartoon-fifo", FIFO])[1].layout == "cartoon"
    with pytest.raises(SystemExit):                               # --layout cartoon alone is an unknown layout
        sd.parse_args(["--streamer-dir", str(tmp_path), "--layout", "cartoon"])


def test_cartoon_is_one_more_mjpeg_input_after_cam2_and_before_the_music(tmp_path):
    cfg = cfg_for(tmp_path)
    music = cfg.streamer_dir / "music"
    music.mkdir(parents=True)
    (music / "bgm.mp3").write_bytes(b"x")
    for cam2 in (False, True):
        argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, voice=True, cam2=cam2, layout="webcam", live=True, cartoon=True)
        paths = input_paths(argv)
        index = 4 if cam2 else 3
        assert paths[index] == FIFO and paths[index + 1] == str(music / "bgm.mp3") and sd.cartoon_index(cam2) == index
        if cam2:
            assert paths[3] == str(cfg.cam2_fifo)                 # the established 0..3 never move
        start = argv.index(FIFO) - 1
        opts = argv[start - 12:start]                             # the options of that input, as cam2's
        assert base.value_after(opts, "-f") == "mjpeg" and base.value_after(opts, "-framerate") == "30"
        assert base.value_after(opts, "-use_wallclock_as_timestamps") == "1" and base.value_after(opts, "-thread_queue_size") == sd.CARTOON_QUEUE == "16"
        graph = graph_of(argv)
        assert f"[{index}:v]" in graph and f"[{index + 1}:a]aresample=48000" in graph     # the bgm index moved by one
        assert graph.count("[2:a]apad") == 1                      # the voice/music mix is the one every layout has


def test_live_graph_has_cartoon_as_the_last_streamselect_input(tmp_path):
    cfg = cfg_for(tmp_path, width=1280, height=720, pip_width=320, pip_height=180, fps=30)
    for cam2, count in ((False, 5), (True, 6)):
        order = sd.live_order(cam2, True)
        assert order[-1] == "cartoon" and order[:-1] == sd.live_order(cam2) and len(order) == count
        for layout in ("webcam", "cartoon"):
            graph = sd.build_live_graph(cfg, cam2, layout, cartoon=True)
            labels = "".join(f"[l{n}]" for n in order)
            assert f"{labels}streamselect@layout=inputs={count}:map={order.index(layout)},format=yuv420p[vout]" in graph
            part = [p for p in graph.split(";") if p.endswith("[lcartoon]")][0]
            # full frame: aspect-preserving scale + pad to the output size, full -> limited range, the run's fps, tpad clone
            assert part == (f"[{sd.cartoon_index(cam2)}:v]scale=1280:720:force_original_aspect_ratio=decrease:"
                            "force_divisible_by=2:flags=bilinear:in_range=full:out_range=limited,format=yuv420p,"
                            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,tpad=stop=-1:stop_mode=clone[lcartoon]")
        # the other layouts keep their indices: today's graph is a prefix of the cartoon graph (up to the selector)
        assert sd.build_live_graph(cfg, cam2, "webcam", cartoon=True).startswith(
            sd.build_live_graph(cfg, cam2, "webcam").rsplit(";", 1)[0])


def test_restart_mode_graph_of_the_cartoon_layout_is_the_cartoon_alone(tmp_path):
    cfg = cfg_for(tmp_path, layout_switch="restart")
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, layout="cartoon", live=False, cartoon=True)
    assert "-nostdin" in argv and argv.count("-i") == 4 and input_paths(argv)[3] == FIFO
    assert graph_of(argv).startswith("[3:v]scale=1920:1080:force_original_aspect_ratio=decrease") and "[vout];" in graph_of(argv)
    assert "streamselect" not in graph_of(argv) and "[0:v]" not in graph_of(argv) and "[1:v]" not in graph_of(argv)
    # any other layout in restart mode does not open the FIFO at all
    other = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, layout="webcam", live=False, cartoon=True)
    assert FIFO not in other and other.count("-i") == 3
    assert sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, layout="webcam", live=False) == other


def test_cartoon_without_the_input_shows_the_webcam(tmp_path):
    cfg = cfg_for(tmp_path)
    assert sd.effective_layout("cartoon", False) == "webcam" and sd.effective_layout("cartoon", True, True) == "cartoon"
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, layout="cartoon", live=True)     # no writer at launch
    assert FIFO not in argv and "cartoon" not in graph_of(argv) and "map=0," in graph_of(argv)


def test_test_sources_replace_the_fifo_with_a_lavfi_card(tmp_path):
    cfg = cfg_for(tmp_path, test_sources=True)
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", layout="cartoon", live=True, cartoon=True)
    assert FIFO not in argv and "rgbtestsrc=size=1280x720:rate=30" in argv and argv.count("-i") == 4
    assert "in_range=full" not in graph_of(argv)                  # the lavfi card is not full-range MJPEG


# ----------------------------------------------------------------------------- layout validation

def test_validate_layout_accepts_cartoon_only_with_the_flag():
    assert sd.validate_layout("cartoon", True) == "cartoon" and sd.validate_layout("cartoon", cartoon=True) == "cartoon"
    assert sd.validate_layout("character", True) == "webcam"
    with pytest.raises(ValueError) as err:
        sd.validate_layout("cartoon")
    assert str(err.value) == str(_unknown("pip")) and "cartoon" not in str(err.value)    # exactly as an unknown name
    with pytest.raises(ValueError) as err:
        sd.validate_layout("pip", True)
    assert "webcam, desktop, split, room, webcam_only, cartoon (character = webcam)" in str(err.value)
    for bad in (None, "", "Cartoon", 1, ["cartoon"]):
        with pytest.raises(ValueError):
            sd.validate_layout(bad, True)


def _unknown(name):
    with pytest.raises(ValueError) as err:
        sd.validate_layout(name)
    return err.value


def test_config_and_layout_log_accept_cartoon_only_with_the_flag(tmp_path):
    assert cfg_for(tmp_path, layout="cartoon").layout == "cartoon"
    with pytest.raises(ValueError):
        cfg_for(tmp_path, cartoon=False, layout="cartoon")
    log = tmp_path / "layout.jsonl"
    log.write_text(json.dumps({"layout": "cartoon"}) + "\n")
    assert sd.read_last_layout(log, cartoon=True) == "cartoon" and sd.read_last_layout(log) is None


def test_post_layout_cartoon_is_400_without_the_flag_and_logged_with_it(tmp_path):
    async def body():
        for flag, status in ((False, 400), (True, 200)):
            root = tmp_path / str(flag)
            director, _ = base.make_director(root, [lambda: base.FakeProc(1)], cartoon_fifo=FIFO if flag else None)
            http = TestClient(TestServer(sd.create_app(director, TOKEN)))
            await http.start_server()
            try:
                r = await http.post("/director/layout", json={"layout": "cartoon"}, headers=AUTH)
                text = await r.text()
                assert r.status == status, text
                log = root / "streamer" / "layout.jsonl"
                if flag:
                    reply = json.loads(text)
                    assert reply["layout"] == "cartoon" and director.layout == "cartoon" and json.loads(log.read_text())["layout"] == "cartoon"
                    assert "no writer" in reply["note"] and reply["live"] is False       # nothing is recording / reading
                else:
                    assert "webcam, desktop, split, room, webcam_only (character = webcam)" in text and "cartoon" not in text.split("one of")[1]
                    assert director.layout == "webcam" and not log.exists()
                state = await (await http.get("/director/state", headers=AUTH)).json()
                assert ("cartoon" in state) is flag
            finally:
                await http.close()
    base.run(body())


# ----------------------------------------------------------------------------------- the director

def cartoon_director(tmp_path, ready=True, **kw):
    director, launched = base.make_director(tmp_path, [lambda: base.FakeProc(11), lambda: base.FakeProc(12)],
                                            cartoon_fifo=FIFO, **kw)
    state = {"ready": ready}
    director._check_cartoon = lambda writer=True: (state["ready"], "writer present" if state["ready"] else "no process writes to the cartoon FIFO")
    director._check_cam2 = lambda writer=True: (False, "no cam2", None)
    return director, launched, state


def test_launch_reads_the_cartoon_fifo_only_with_a_writer_attached(tmp_path):
    async def body():
        for ready in (False, True):
            director, launched, _ = cartoon_director(tmp_path / str(ready), ready=ready)
            task = asyncio.ensure_future(director.run())
            await base.until(lambda: director.alive)
            argv = launched[0][0]
            assert (FIFO in argv) is ready and director.cartoon is ready and director.cartoon_now is ready
            assert ("cartoon" in director.live_order) is ready and director.state()["cartoon"] is ready
            assert ("cartoon" in director.state()["layouts_available"]) is ready
            director.stop()
            await asyncio.wait_for(task, 5)
    base.run(body())


def test_live_switch_to_cartoon_sends_the_last_streamselect_map(tmp_path):
    async def body():
        director, proc = _live_director(tmp_path)
        proc.stdin = base.FakeStdin(director)
        director.layout = "cartoon"
        assert await director.apply_layout() == "live"
        assert proc.stdin.lines == [b"cstreamselect@layout -1 map 4\n"] and director.live_layout == "cartoon"
        director.layout = "webcam"
        assert await director.apply_layout() == "live" and proc.stdin.lines[-1] == b"cstreamselect@layout -1 map 0\n"
    base.run(body())


def _live_director(tmp_path, cartoon=True, **kw):
    director, _ = base.make_director(tmp_path, [lambda: None], switch_timeout=0.3, cartoon_fifo=FIFO, **kw)
    proc = base.FakeProc.__new__(base.FakeProc)
    proc.pid, proc.returncode = 5, None
    director.proc, director.prefix, director.cam2, director.cartoon = proc, "sub01-20261023-210000", False, cartoon
    director.live_layout, director.live_order = "webcam", sd.live_order(False, cartoon)
    return director, proc


def test_cartoon_wanted_without_the_input_shows_the_webcam_then_relaunches_with_it(tmp_path):
    async def body():
        director, proc = _live_director(tmp_path, cartoon=False)
        proc.stdin = base.FakeStdin(director)
        director.layout = "cartoon"
        assert await director.apply_layout() == "same" and proc.stdin.lines == []     # nothing to show it with
        director.cartoon_now = True                                                  # a writer attached
        now = [1000.0]
        director._clock, director.started_mono = (lambda: now[0]), 990.0
        director.last_restart_reason = sd.CARTOON_DROP                               # no relaunch loop within 30 s
        assert await director.apply_layout() == "same"
        now[0] = 1021.0
        assert await director.apply_layout() == "restart"
        assert director._restart_reason == "layout cartoon: relaunch with the cartoon input"
    base.run(body())


def test_cartoon_tick_drops_a_gone_writer_at_once_and_adds_it_only_for_the_cartoon_layout(tmp_path):
    async def body():
        now, seen = [1000.0], []
        director, _ = base.make_director(tmp_path, [lambda: None], cartoon_fifo=FIFO)
        avail = [(False, "no process writes to the cartoon FIFO")]
        director._check_cartoon = lambda writer=True: (seen.append(writer), avail[0])[1]
        director._clock = lambda: now[0]
        director.proc, director.cartoon, director.started_mono = base.FakeProc(1), True, 1000.0
        director._cartoon_ident = director.cartoon_tap.ident
        now[0] += 100
        assert await director.cartoon_tick() == "drop" and director._restart_reason == sd.CARTOON_DROP
        director._restart_reason, director.cartoon = None, False
        avail[0] = (True, "writer present")
        assert await director.cartoon_tick() == "wait"
        assert await director.cartoon_tick() == "ready" and director.cartoon_now and director._restart_reason is None
        director.layout = "cartoon"
        assert await director.cartoon_tick() == "add" and director._restart_reason == "cartoon came online"
        kinds = [json.loads(line)["kind"] for line in (tmp_path / "streamer" / "events.jsonl").read_text().splitlines()]
        assert kinds.count("cartoon_changed") == 2
        # without the flag the tick does nothing at all
        plain, _ = base.make_director(tmp_path / "plain", [lambda: None])
        plain.proc = base.FakeProc(2)
        assert await plain.cartoon_tick() == "idle" and plain.cartoon_tap is None
    base.run(body())


def test_cartoon_status_needs_a_fifo_with_a_writer(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    fifo = tmp_path / "cartoon.mjpeg"
    tap = sd.FifoTap(fifo, proc_root, create=False, what="cartoon")
    assert sd.cartoon_status(tap) == (False, "cartoon FIFO does not exist")
    os.mkfifo(fifo)
    assert sd.cartoon_status(tap) == (False, "no process writes to the cartoon FIFO")
    assert sd.cartoon_status(tap, writer=False)[0] is True        # while the run reads it: only the FIFO's identity
    base.fake_proc(proc_root, 30, 9, fifo, "0104001")             # the feeder: O_WRONLY|O_NONBLOCK
    assert sd.cartoon_status(tap) == (True, "writer present")
    tap.close()


# ------------------------------------------------------------------------------- real ffmpeg smoke

@needs_ffmpeg
@pytest.mark.parametrize("layout", ["cartoon", "webcam"])
def test_smoke_live_graph_with_the_cartoon_input_encodes_on_test_sources(tmp_path, layout):
    cfg = cfg_for(tmp_path, test_sources=True, test_seconds=2, width=640, height=360, pip_width=160, pip_height=90,
                  fps=15, desktop_fps=10)
    cfg.recordings_dir.mkdir(parents=True)
    argv = sd.build_ffmpeg_argv(cfg, prefix="sub01-20261023-210000", layout=layout, live=True, cartoon=True)
    done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
    assert done.returncode == 0, done.stderr[-1500:]
    assert (cfg.recordings_dir / "sub01-20261023-210000-000.mp4").stat().st_size > 2_000


def test_cartoon_on_file_turns_the_cartoon_fifo_on_without_a_supervisor_restart(tmp_path):
    base = ["--streamer-dir", str(tmp_path)]
    assert sd.parse_args(base)[1].cartoon_fifo is None                  # off by default
    (tmp_path / sd.CARTOON_ON_FILE).write_text("")
    assert str(sd.parse_args(base)[1].cartoon_fifo) == str(tmp_path / "cartoon.mjpeg")
    explicit = str(tmp_path / "other.mjpeg")
    assert str(sd.parse_args(base + ["--cartoon-fifo", explicit])[1].cartoon_fifo) == explicit   # the flag wins
