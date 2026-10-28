Probe Pulse with a 0.5 s AF_UNIX connect; absence of the socket leaves both launch paths unchanged.
Apps are always the final input, with music and apps summed before voice-keyed ducking.
The apps limiter is installed only in apps graphs, and its gain is fixed to zero for private launches.
Privacy mutes before entering the cut, restarts on mute failure, and merely logs unmute failures.
Set `self.apps_audio` when constructing the launch argv; replace the shown director audio tail, whose unavailable prefix remains unchanged.

```python
# streamer_desktop.py
import socket
from pathlib import Path


def pulse_socket(streamer_dir):
    """Return the PulseAudio native socket only when it accepts a connection promptly."""
    path = Path(streamer_dir) / "run" / "pulse" / "native"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            sock.connect(str(path))
    except OSError:
        return None
    return path


def chromium_args(cfg):
    """The browser's flags: the fixed set, the GPU mode (GPU_ARGS), the autoplay policy and the operator's extra flags."""
    args = ["--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
            "--disable-background-networking", "--mute-audio", "--password-store=basic",
            "--disable-dev-shm-usage", "--deny-permission-prompts", "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble", "--disable-infobars", "--noerrdialogs",
            "--disable-features=Translate,AutofillServerCommunication", "--window-position=0,0",
            f"--window-size={cfg.width},{cfg.height}"]
    args += GPU_ARGS.get(getattr(cfg, "gpu", "off") or "off", GPU_ARGS["off"])
    streamer_dir = os.environ.get("STREAMER_DIR") or Path(cfg.data_dir).parent
    pulse = pulse_socket(streamer_dir)
    if pulse:
        args.remove("--mute-audio")
    if pulse or getattr(cfg, "autoplay", False):
        args.append("--autoplay-policy=no-user-gesture-required")
    args += [str(a) for a in (getattr(cfg, "extra_args", ()) or ()) if str(a).startswith("--")]
    return args + (["--kiosk"] if cfg.kiosk and not cfg.headless else [])


def chromium_env(display, environ=None, streamer_dir=None):
    """A clean environment for the browser: no operator token, no API keys, only what Chromium needs."""
    environ = os.environ if environ is None else environ
    env = {k: v for k, v in environ.items() if k in SAFE_ENV}
    env["DISPLAY"] = display
    if streamer_dir is None:
        streamer_dir = environ.get("STREAMER_DIR")
    if streamer_dir:
        pulse = pulse_socket(streamer_dir)
        if pulse:
            env["PULSE_SERVER"] = f"unix:{pulse}"
            env["PULSE_SINK"] = "sub01_apps"
    return env
```

```python
# Browser._launch: replace its options assignment (cfg = self.cfg)
        streamer_dir = os.environ.get("STREAMER_DIR") or Path(cfg.data_dir).parent
        options = {"headless": cfg.headless, "args": chromium_args(cfg),
                   "env": chromium_env(cfg.display, streamer_dir=streamer_dir),
```

```python
# streamer_director.py
import socket
from pathlib import Path

APPS_GAIN = 0.6


def pulse_socket(streamer_dir):
    """Return the PulseAudio native socket only when it accepts a connection promptly."""
    path = Path(streamer_dir) / "run" / "pulse" / "native"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            sock.connect(str(path))
    except OSError:
        return None
    return path
```

```python
# build_ffmpeg_argv: complete replacement for the tail beginning at `music = ...`
    music = cfg.streamer_dir / "music" / "bgm.mp3"
    music = music if music.exists() else None
    music_index = argv.count("-i")       # the next input's index (cam2 and live inputs counted, not assumed)
    if music:                           # last music input: the established 0..N indices never move
        argv += ["-stream_loop", "-1", "-i", str(music)]
    apps = None if cfg.test_sources else pulse_socket(cfg.streamer_dir)
    apps_index = argv.count("-i")
    if apps:
        argv += ["-thread_queue_size", "1024", "-f", "pulse", "-server", f"unix:{apps}",
                 "-i", "sub01_apps.monitor"]
    graph = build_live_graph(cfg, cam2, layout, main) if live else build_filter_complex(layout, cfg, main)
    if music or apps:
        # apad also covers a vanished voice writer; normalize=0 leaves the voice's level untouched
        graph += ";[2:a]apad,asplit=2[voice][key]"
        if music:
            graph += (f";[{music_index}:a]aresample=48000,"
                      "aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.08[bgm]")
        if apps:
            apps_gain = 0 if effective_layout(layout, cam2) == PRIVATE_LAYOUT else APPS_GAIN
            graph += (f";[{apps_index}:a]aresample=48000:async=1:first_pts=0,"
                      "aformat=sample_fmts=fltp:channel_layouts=stereo,"
                      f"volume@apps={apps_gain}[apps]")
        if music and apps:
            graph += (";[bgm][apps]amix=inputs=2:duration=first:dropout_transition=0:"
                      "normalize=0[bed]")
            bed = "bed"
        else:
            bed = "bgm" if music else "apps"
        mixed = "mix" if apps else "aout"
        graph += (f";[{bed}][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=500[ducked];"
                  f"[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[{mixed}]")
        if apps:
            graph += ";[mix]alimiter=limit=0.891[aout]"
    elif voice:
        # apad: if the voice server goes away the FIFO hits EOF; silence keeps the audio track running meanwhile
        graph += ";[2:a]apad[aout]"
    argv += ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]" if voice or music or apps else "2:a",
             *video_codec_args(cfg, encoder or cfg.encoder), "-max_muxing_queue_size", "1024",
             "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-ar", "48000", "-ac", "2"]
```

```python
# streamer_director.py
    async def apply_layout(self):
        """Bring the running ffmpeg to the wanted layout: live through streamselect, else by a relaunch.
        -> idle | same | live | restart | stale"""
        async with self._switch_lock:
            if not self.alive or self._restart_reason:
                return "idle"
            proc, wanted = self.proc, self.wanted()
            if LAYOUTS[wanted]["needs_cam2"] and not self.cam2 and self.cam2_now:
                # right after a relaunch that dropped a stalled cam2, wait (no relaunch loop); cam2_tick adds it later
                if self.last_restart_reason != CAM2_DROP or self.uptime() >= CAM2_MIN_UPTIME:
                    self.request_restart(f"layout {wanted}: relaunch with cam2")
                    return "restart"
            target = effective_layout(wanted, self.cam2)
            if target == self.live_layout:
                self._on_air("same")
                return "same"
            if self.cfg.layout_switch != "live" or target not in self.live_order:
                self._note_switch(target, "restart", True, 0)
                self.request_restart(f"layout {target}")
                return "restart"
            if getattr(self, "apps_audio", False) and target == PRIVATE_LAYOUT:
                muted, mute_detail = await self.send_command("volume@apps", "volume", "0")
                if not muted:
                    self.event("apps_mute_failed", detail=mute_detail, run=self.prefix)
                    self.request_restart("privacy: apps mute failed")
                    return "restart"
            started = self._clock()
            self._switching = target                     # desktop_hidden is false until the reply settles it
            try:
                ok, detail = await self.send_command(SWITCH_TARGET, "map", str(self.live_order.index(target)))
            finally:
                self._switching = None
            ms = round((self._clock() - started) * 1000)
            if self.proc is not proc or self._restart_reason:
                return "stale"                   # relaunched meanwhile: the new run starts with the wanted layout
            if ok:
                previous, self.live_layout = self.live_layout, target
                self._note_switch(target, "live", True, ms)
                self.event("layout_switched", layout=target, previous=previous, how="live", ms=ms, run=self.prefix)
                self._on_air("live switch")
                if (getattr(self, "apps_audio", False) and previous == PRIVATE_LAYOUT
                        and target != PRIVATE_LAYOUT):
                    unmuted, unmute_detail = await self.send_command(
                        "volume@apps", "volume", str(APPS_GAIN))
                    if not unmuted:
                        self.event("apps_unmute_failed", detail=unmute_detail, run=self.prefix)
                if effective_layout(self.wanted(), self.cam2) != target:
                    self.kick_layout()           # the wanted layout changed meanwhile (a new cut): at once, not next tick
                return "live"
            if detail.startswith(("no reply", "cannot write")):
                self.live_layout = None          # the command may or may not have reached the graph: on air unknown
            self._note_switch(target, "restart", False, ms, detail)
            self.event("layout_switch_failed", layout=target, detail=detail, ms=ms, run=self.prefix)
            self.request_restart(f"layout {target} (live switch failed: {detail})")
            return "restart"
```

```python
# tests/test_streamer_desktop.py
import socket
from types import SimpleNamespace

import scripts.streamer_desktop as desktop


def desktop_cfg(tmp_path, autoplay=False):
    return SimpleNamespace(data_dir=tmp_path / "data", width=1280, height=720,
                           gpu="off", autoplay=autoplay, extra_args=(),
                           kiosk=False, headless=True)


def listening_pulse(tmp_path):
    socket_path = tmp_path / "run" / "pulse" / "native"
    socket_path.parent.mkdir(parents=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen()
    return server


def test_chromium_args_and_env_are_unchanged_without_pulse(tmp_path, monkeypatch):
    monkeypatch.setenv("STREAMER_DIR", str(tmp_path))
    cfg = desktop_cfg(tmp_path)
    args = desktop.chromium_args(cfg)
    env = desktop.chromium_env(":99", environ={"PATH": "/bin"}, streamer_dir=tmp_path)
    assert "--mute-audio" in args
    assert "--autoplay-policy=no-user-gesture-required" not in args
    assert env == {"PATH": "/bin", "DISPLAY": ":99"}


def test_chromium_uses_pulse_and_adds_autoplay_only_once(tmp_path, monkeypatch):
    server = listening_pulse(tmp_path)
    try:
        monkeypatch.setenv("STREAMER_DIR", str(tmp_path))
        cfg = desktop_cfg(tmp_path, autoplay=True)
        args = desktop.chromium_args(cfg)
        env = desktop.chromium_env(":99", environ={"PATH": "/bin"}, streamer_dir=tmp_path)
        assert "--mute-audio" not in args
        assert args.count("--autoplay-policy=no-user-gesture-required") == 1
        assert env["PULSE_SERVER"] == f"unix:{tmp_path / 'run' / 'pulse' / 'native'}"
        assert env["PULSE_SINK"] == "sub01_apps"
    finally:
        server.close()
```

```python
# tests/test_streamer_director.py
import socket
from types import SimpleNamespace

import pytest

import scripts.streamer_director as sd


@pytest.fixture
def director_cfg(tmp_path, monkeypatch):
    cfg = SimpleNamespace(streamer_dir=tmp_path, ffmpeg="ffmpeg", width=1280, height=720,
                          pip_width=320, pip_height=180, fps=30, desktop_fps=5, stats_period=1,
                          test_sources=False, test_seconds=None, encoder="libx264",
                          audio_bitrate="128k", game_display=":99.0", desktop_display=":99.0",
                          voice_fifo=tmp_path / "voice.raw")
    monkeypatch.setattr(sd, "effective_layout", lambda layout, cam2: layout)
    monkeypatch.setattr(sd, "build_filter_complex", lambda *args: "VIDEO")
    monkeypatch.setattr(sd, "video_codec_args", lambda *args: [])
    monkeypatch.setattr(sd, "output_args", lambda *args: ["out.mkv"])
    return cfg


@pytest.fixture
def pulse_server(director_cfg):
    path = director_cfg.streamer_dir / "run" / "pulse" / "native"
    path.parent.mkdir(parents=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen()
    yield server
    server.close()


def graph_of(argv):
    return argv[argv.index("-filter_complex") + 1]


def test_no_pulse_socket_leaves_argv_identical(director_cfg, monkeypatch):
    without_socket = sd.build_ffmpeg_argv(director_cfg, prefix="out")
    monkeypatch.setattr(sd, "pulse_socket", lambda streamer_dir: None)
    assert sd.build_ffmpeg_argv(director_cfg, prefix="out") == without_socket
    assert graph_of(without_socket) == "VIDEO;[2:a]apad[aout]"


def test_apps_only_graph(director_cfg, pulse_server):
    argv = sd.build_ffmpeg_argv(director_cfg, prefix="out")
    pulse_input = argv.index("sub01_apps.monitor")
    assert argv[pulse_input - 6:pulse_input + 1] == [
        "-thread_queue_size", "1024", "-f", "pulse",
        "-server", f"unix:{director_cfg.streamer_dir / 'run' / 'pulse' / 'native'}",
        "-i", "sub01_apps.monitor",
    ]
    graph = graph_of(argv)
    assert "[3:a]aresample=48000:async=1:first_pts=0" in graph
    assert "volume@apps=0.6[apps]" in graph
    assert "[apps][key]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=500[ducked]" in graph
    assert graph.endswith("[mix]alimiter=limit=0.891[aout]")
    assert argv[argv.index("-map", argv.index("-filter_complex") + 3) + 1] == "[aout]"


def test_music_and_apps_are_summed_then_ducked(director_cfg, pulse_server):
    bgm = director_cfg.streamer_dir / "music" / "bgm.mp3"
    bgm.parent.mkdir()
    bgm.write_bytes(b"test")
    argv = sd.build_ffmpeg_argv(director_cfg, prefix="out")
    assert argv[argv.index("sub01_apps.monitor") - 1] == "-i"
    assert argv.index(str(bgm)) < argv.index("sub01_apps.monitor")
    graph = graph_of(argv)
    assert "[3:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.08[bgm]" in graph
    assert "[4:a]aresample=48000:async=1:first_pts=0" in graph
    assert "[bgm][apps]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[bed]" in graph
    assert "[bed][key]sidechaincompress=" in graph
    assert graph.endswith("[mix]alimiter=limit=0.891[aout]")


def test_private_layout_builds_apps_gain_zero(director_cfg, pulse_server):
    argv = sd.build_ffmpeg_argv(director_cfg, prefix="out", layout=sd.PRIVATE_LAYOUT)
    assert "volume@apps=0[apps]" in graph_of(argv)
```
