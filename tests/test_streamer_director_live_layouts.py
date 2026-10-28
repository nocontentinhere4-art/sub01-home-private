"""Streamer director, `--live-layouts` (owner 10-28: all six layouts at 1080p60 fell behind real time on the shared pod)
and the delay guard (LAG_LIMIT). Without the flag every graph is what it was (the other test files pin it)."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_streamer_director as base  # noqa: E402
import test_streamer_director_cartoon as cart  # noqa: E402

sd = base.sd
POD = ("webcam_only", "desktop")


def cfg_for(tmp_path, live_layouts=POD, cartoon=True, **kw):
    return cart.cfg_for(tmp_path, cartoon=cartoon, live_layouts=live_layouts, **kw)


def streamselect_inputs(graph):
    return graph.split("streamselect@layout=inputs=")[1].split(":")[0]


def test_config_and_cli_parse_the_live_layouts(tmp_path):
    assert cfg_for(tmp_path, live_layouts=" desktop,webcam_only,desktop ").live_layouts == ("desktop", "webcam_only")
    assert cfg_for(tmp_path, live_layouts=None).live_layouts is None
    with pytest.raises(ValueError):
        cfg_for(tmp_path, live_layouts="desktop,pc")
    args, cfg = sd.parse_args(["--streamer-dir", str(tmp_path), "--live-layouts", "webcam_only,desktop"])
    assert cfg.live_layouts == POD
    assert sd.parse_args(["--streamer-dir", str(tmp_path)])[1].live_layouts is None


def test_live_order_keeps_the_privacy_layout_the_launch_layout_and_the_cartoon():
    assert sd.live_order(True, True, POD, "desktop") == ("desktop", "webcam_only", "cartoon")
    assert sd.live_order(True, False, ("desktop",), "desktop") == ("desktop", "webcam_only")   # privacy stays live
    assert sd.live_order(True, True, POD, "room") == ("desktop", "room", "webcam_only", "cartoon")
    assert sd.live_order(False, False, POD, "room") == ("desktop", "webcam_only")             # room needs cam2
    assert sd.live_order(True, True) == sd.live_order(True, True, None, "desktop")             # no flag: all of them
    assert sd.live_order(True, False, ("webcam_only",), "room") == ("desktop", "room", "webcam_only")  # desktop read


def test_pruned_graph_renders_only_the_live_layouts(tmp_path):
    cfg = cfg_for(tmp_path)
    graph = sd.build_live_graph(cfg, False, "desktop", cartoon=True)
    assert streamselect_inputs(graph) == "3" and "map=0," in graph
    assert "[lwebcam]" not in graph and "[lsplit]" not in graph and "hstack" not in graph and "[lroom]" not in graph
    assert ",split=2[gp][lwebcam_only]" in graph and "[gp]scale=480:270:flags=area,setsar=1[gpa]" in graph
    assert f"fps={cfg.fps}[dm]" in graph and "[dp]" not in graph and "[dh]" not in graph
    assert "[ldesktop]" in graph and "[lcartoon]" in graph
    assert sd.build_live_graph(cfg, False, "webcam_only", cartoon=True).count("map=1,") == 1


def test_cam2_is_read_only_when_room_is_rendered(tmp_path):
    cfg = cfg_for(tmp_path)
    assert not sd.renders_cam2(cfg, "desktop") and sd.renders_cam2(cfg, "room")
    assert sd.renders_cam2(cfg_for(tmp_path, live_layouts=None), "desktop")
    room = sd.build_live_graph(cfg, True, "room", cartoon=False)                    # launched for room: it has it
    assert "[lroom]" in room and "split=2[gpa][gpb]" in room and streamselect_inputs(room) == "3"
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, cam2=True, layout="desktop", live=True)
    assert not any(a.endswith("cam2.mjpeg") for a in argv) and "[lroom]" not in base.value_after(argv, "-filter_complex")
    argv = sd.build_ffmpeg_argv(cfg, prefix="p", window_id=7, cam2=True, layout="room", live=True)
    assert any(a.endswith("cam2.mjpeg") for a in argv)


def test_a_layout_outside_the_live_set_relaunches_and_a_live_one_switches(tmp_path):
    async def body():
        director, proc = cart._live_director(tmp_path, live_layouts=POD)
        proc.stdin = base.FakeStdin(director)
        director.live_layout = "desktop"
        director.live_order = sd.live_order(False, True, POD, "desktop")
        director.layout = "webcam_only"
        assert await director.apply_layout() == "live" and proc.stdin.lines == [b"cstreamselect@layout -1 map 1\n"]
        director.layout = "webcam"
        assert await director.apply_layout() == "restart" and director._restart_reason == "layout webcam"
        assert sd.layout_plan(director, "webcam")[0] is False and sd.layout_plan(director, "desktop")[0] is True
    base.run(body())


def test_lag_growth_and_decision():
    assert sd.lag_growth(None, (10.0, 5.0)) is None and sd.lag_growth((10.0, None), (20.0, 5.0)) is None
    assert sd.lag_growth((100.0, 50.0), (160.0, 109.5)) == pytest.approx(0.5)
    assert sd.lag_decision(None, since_restart=None) == "ok"
    assert sd.lag_decision(9.9, since_restart=None) == "ok"
    assert sd.lag_decision(10.5, since_restart=None) == "restart"
    assert sd.lag_decision(10.5, since_restart=120.0) == "held"
    assert sd.lag_decision(10.5, since_restart=700.0) == "restart"


def test_watchdog_tick_relaunches_a_run_that_drifts_behind_real_time(tmp_path):
    async def body():
        now = [1000.0]
        director, _ = base.make_director(tmp_path, [lambda: base.FakeProc(1)])
        director._clock = lambda: now[0]
        director.proc, director.prefix, director.started_mono = base.FakeProc(1), "sub01-20261023-120000", 1000.0
        director.meter = sd.OutputMeter(600)
        rec = director.cfg.recordings_dir
        rec.mkdir(parents=True)
        segment = rec / "sub01-20261023-120000-000.mp4"
        out = [5.0]                                                # 5 s behind at start: not counted

        async def tick(media_gain):
            now[0] += 30
            out[0] += media_gain
            segment.write_bytes(b"x" * int(1000 + now[0]))
            director.meter._last = (now[0], 0, out[0], 0, 0)
            return await director.watchdog_tick()

        await tick(30)                                             # grace: no reference yet
        await tick(25)
        assert director.lag_s == 0.0 and director._restart_reason is None
        for _ in range(3):
            await tick(29.0)                                       # 0.967x: above SLOW_SPEED, 1 s per tick
        assert director.slow_checks == 0 and director.lag_s == 3.0 and director._restart_reason is None
        for _ in range(8):
            await tick(29.0)
        assert director._restart_reason == "output fell behind the wall clock" and director.state()["lag_s"] == 11.0
        director._restart_reason = None
        await tick(29.0)                                           # the same run still behind: held, no loop
        assert director._restart_reason is None
    base.run(body())


@cart.needs_ffmpeg
@pytest.mark.parametrize("layout,cam2", [("desktop", False), ("webcam_only", False), ("room", True), ("desktop", True)])
def test_smoke_pruned_live_graph_encodes_on_test_sources(tmp_path, layout, cam2):
    cfg = cfg_for(tmp_path, test_sources=True, test_seconds=2, width=640, height=360, pip_width=160, pip_height=90,
                  fps=15, desktop_fps=10)
    cfg.recordings_dir.mkdir(parents=True)
    argv = sd.build_ffmpeg_argv(cfg, prefix="sub01-20261023-210000", layout=layout, live=True, cartoon=True, cam2=cam2)
    done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
    assert done.returncode == 0, done.stderr[-1500:]
    assert (cfg.recordings_dir / "sub01-20261023-210000-000.mp4").stat().st_size > 2_000
