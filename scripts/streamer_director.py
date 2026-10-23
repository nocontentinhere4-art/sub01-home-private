#!/usr/bin/env python3
"""SUB-01 streamer director: records the stream locally with one ffmpeg process.

Inputs of the single ffmpeg process
  0  x11grab of the Unreal game window on :99.0 (`-window_id`, found with xdotool) at --fps (10-120, default 24);
     the game viewport is the frontal webcam shot,
  1  x11grab of the desktop on :102.0 (1920x1080) at --desktop-fps (10-60, default 15, never above --fps),
  2  the voice server's continuous PCM FIFO (s16le, 48 kHz, stereo), or, when
     nobody is writing to the FIFO, `anullsrc` silence (state shows `voice: false`),
  3  only while it is usable: the game's second camera `<streamer-dir>/cam2.mjpeg`, a FIFO of MJPEG 1280x720 at ~30 fps
     (state shows `cam2`). Without it the run has inputs 0-2 only, as before.
  `--test-sources` replaces all of them with lavfi testsrc2/sine (local smoke tests: no X server, FIFO or game).

Voice FIFO. The voice server opens `<streamer-dir>/voice.pcm` O_WRONLY|O_NONBLOCK and only attaches while a
reader exists, so the director itself keeps a read end open on the FIFO for as long as it runs (`VoiceTap`):
that is what lets the server attach, and a process holding the FIFO open for writing is what the director
takes as "voice available". While ffmpeg is not reading the FIFO (silent run, gaps between runs) the tap drains
it, so the server never sees a stalled reader; before a run that reads it the tap discards stale audio.
ffmpeg opens the path blocking, so a launch with voice only happens when a writer is already attached.

cam2 FIFO. Same tap pattern (the director never creates this FIFO: the game does). cam2 is usable when a process holds
it open for writing and `cam2.json` (written by the game: fps, last frame time) reports a frame newer than --cam2-stale s.
ffmpeg stamps its frames with the arrival wallclock (`-use_wallclock_as_timestamps`, like x11grab) and the graph
normalises them to --fps; `tpad` repeats the last frame after an EOF. A cam2 that stops delivering without closing
stalls the whole graph, so a check every --cam2-interval s relaunches ffmpeg without cam2 as soon as its writer is
gone or cam2.json goes stale; a run without cam2 is relaunched with it when the wanted layout is `room`.

Output: libx264 veryfast crf 23 (or NVENC) at --fps (GOP 2 s) + aac 96k, cut into 10 minute segments
`recordings/sub01-YYYYmmdd-HHMMSS-%03d.mp4` (UTC; every ffmpeg launch gets its
own timestamp, so a restart never overwrites a segment). Segments are fragmented
MP4: a crash or SIGKILL loses at most ~2 s and the file stays playable.

Encoder. `--encoder libx264|h264_nvenc|hevc_nvenc`. NVENC runs `-preset p4 -tune ll -rc vbr -cq <crf> -b:v 0 -bf 2`;
it is probed once at start with a 1 s lavfi encode with the same options, and a failed probe falls back to libx264
(event `encoder_fallback`). `/director/state` shows the active `encoder`.

HLS / RTMP. `--hls-dir` (and the optional `--rtmp-url-file` / `--rtmp-url`) send the SAME encode through the tee muxer
to the segments, to `<hls-dir>/live.m3u8` (4 s segments, 6 listed, older ones deleted, media sequence from the epoch
so a relaunch keeps counting up, a discontinuity at the start, no ENDLIST when ffmpeg stops) and to RTMP (flv behind a
dropping fifo). A failing HLS or RTMP branch never stops the recording. The RTMP URL is never logged, printed or put in
state (ffmpeg's own messages are redacted). Nothing here is public: `scripts/streamer_hls_serve.py` serves the HLS
directory on 127.0.0.1 for local tests only.

Layouts: `webcam` (game viewport = frontal webcam full frame, desktop picture-in-picture 480x270 bottom-right;
`character` is the v1 name of the same layout), `desktop` (desktop full frame, webcam PiP), `split` (webcam and
desktop side by side), `room` (cam2 full frame, webcam PiP; without cam2 `webcam` is shown). The wanted layout is the
last line of `<streamer-dir>/layout.jsonl` (written by `POST /director/layout` or by the agent directly; read every
--layout-interval s), or fixed with `--layout`. Every line has `t`, `unix`, `layout`, `previous`, `run`, `offset_s`,
`recording`.

Live switching (`--layout-switch live`, the default): the graph renders every layout of the run and
`streamselect@layout` picks the recorded one. The director changes its `map` through ffmpeg's stdin command channel
(`c` + `streamselect@layout -1 map N`, i.e. avfilter_graph_send_command) and waits for ffmpeg's `Command reply ... ret:0`.
sendcmd is not used for this: it reads its command file once when the graph starts, so a regenerated file could not
drive a running process. No reply within --switch-timeout s, or `--layout-switch restart`: ffmpeg is relaunched with
the new layout (a gap of 1-2 s and a new run prefix); restart mode also renders only the one layout (less CPU).
`build_filter_complex(layout)` is that one-layout graph (`[0:v]` game, `[1:v]` desktop, `[3:v]` cam2).

HTTP on 127.0.0.1 only; every route except /healthz needs the operator
credential in `X-Admin-Token` (from --token-file or SUB01_ADMIN_TOKEN; never logged):

  GET  /healthz           -> {"ok": true, "recording": bool}
  GET  /director/state    -> {recording, since, segments:[{name,bytes,mtime}], ffmpeg_pid,
                              restarts, last_error, layout, live_layout, encoder, cam2, hls, voice, ...}
  POST /director/layout   {"layout": "webcam"|"desktop"|"split"|"room"|"character"}

ffmpeg is restarted on exit with backoff; a watchdog compares the size of the
current run's segments every 30 s and restarts ffmpeg after two checks without
growth; a second check (every 15 s) relaunches ffmpeg when the voice server attached after a
silent start, or came back after a drop (the run's audio input hit EOF; until then `apad` records silence).
The helpers below are pure and importable without ffmpeg.
"""

import argparse
import asyncio
import hmac
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import web

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MIN_TOKEN = 12
MAX_BODY = 1024
DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
DEFAULT_PORT = 8837
MAX_FPS = 120
MAX_DESKTOP_FPS = 60
CAM2_SIZE = "1280x720"
STATS_PERIOD = 5.0          # seconds between ffmpeg -progress blocks
GRAB_QUEUE = "128"          # x11grab packets are raw frames (8 MB at 1080p): ~2 s at 60 fps, at most ~1 GiB per grab

# ---------------------------------------------------------------- layouts

DEFAULT_LAYOUT = "webcam"
PIP_MARGIN = 24
LAYOUTS = {
    "webcam": {"main": "game", "pip": "desktop", "needs_cam2": False,
               "summary": "game viewport (frontal webcam) full frame, desktop picture-in-picture bottom-right"},
    "desktop": {"main": "desktop", "pip": "game", "needs_cam2": False,
                "summary": "desktop full frame, webcam picture-in-picture bottom-right"},
    "split": {"main": None, "pip": None, "needs_cam2": False,
              "summary": "webcam and desktop side by side, each half width"},
    "room": {"main": "cam2", "pip": "game", "needs_cam2": True,
             "summary": "second camera (room) full frame, webcam picture-in-picture bottom-right"},
}
LAYOUT_ALIASES = {"character": "webcam"}           # the v1 name, still sent by the agent
LIVE_ORDER = ("webcam", "desktop", "split", "room")  # input index of each layout at streamselect@layout
SOURCES = {"game": "0:v", "desktop": "1:v", "cam2": "3:v"}
SWITCH_MODES = ("live", "restart")
SWITCH_TARGET = "streamselect@layout"
ENCODERS = ("libx264", "h264_nvenc", "hevc_nvenc")
X264_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")
SEGMENT_RE = re.compile(r"^(sub01-\d{8}-\d{6})-(\d{3})\.mp4$")
HLS_SEGMENT_RE = re.compile(r"^(sub01-\d{8}-\d{6})-\d+\.ts(\.tmp)?$")
HLS_PLAYLIST = "live.m3u8"
HLS_TIME = 4
HLS_LIST_SIZE = 6
REPLY_RE = re.compile(r"Command reply for (?:stream|graph) \d+: ret:<?(-?\d+)>?")
TEE_UNSAFE = re.compile(r"[\s|\[\]:'\"\\]")          # tee muxer syntax: slave separator, option brackets, escapes
RTMP_RE = re.compile(r"rtmps?://[^\s|\[\]'\"\\]+")
TEE_COLON = "\\\\:"                                  # a ':' inside a tee slave option value, escaped for both levels


def validate_layout(value):
    """Return the canonical layout name (`character` -> `webcam`) or raise ValueError (the message lists the names)."""
    if isinstance(value, str):
        value = LAYOUT_ALIASES.get(value, value)
        if value in LAYOUTS:
            return value
    raise ValueError("layout must be one of " + ", ".join(LIVE_ORDER) + " (character = webcam)")


def effective_layout(layout, cam2):
    """What a run can show for a wanted layout: `room` needs cam2, else the webcam layout is shown."""
    layout = validate_layout(layout)
    return DEFAULT_LAYOUT if LAYOUTS[layout]["needs_cam2"] and not cam2 else layout


def live_order(cam2):
    """The layouts a live graph renders, in streamselect input order."""
    return tuple(name for name in LIVE_ORDER if cam2 or not LAYOUTS[name]["needs_cam2"])


def check_tee_path(path, what):
    if TEE_UNSAFE.search(str(path)):
        raise ValueError(f"{what} must not contain whitespace or any of | [ ] : ' \" \\ (tee muxer syntax)")


def validate_rtmp_url(url):
    """The message never repeats the URL: it holds the stream key."""
    if not isinstance(url, str) or not RTMP_RE.fullmatch(url):
        raise ValueError("the RTMP URL must be rtmp:// or rtmps:// without whitespace or any of | [ ] ' \" \\")
    return url


def secret_parts(url):
    """Strings to redact from anything ffmpeg prints: the URL, its path and every path piece of 6+ characters."""
    if not url:
        return ()
    path = url.split("://", 1)[-1].partition("/")[2]
    parts = {url, path} | {piece for piece in re.split(r"[/?&=]", path) if len(piece) >= 6}
    return tuple(sorted((p for p in parts if p), key=len, reverse=True))


def redact(text, secrets):
    for secret in secrets:
        text = text.replace(secret, "<redacted>")
    return text


@dataclass(frozen=True)
class DirectorConfig:
    streamer_dir: Path
    recordings_dir: Path = None
    voice_fifo: Path = None
    ffmpeg: str = "ffmpeg"
    xdotool: str = "xdotool"
    game_display: str = ":99.0"
    desktop_display: str = ":102.0"
    window_prefix: str = "Sub01HomeLab"
    window_id: int = None
    game_pid: int = None
    game_pid_file: Path = None
    width: int = 1920
    height: int = 1080
    pip_width: int = 480
    pip_height: int = 270
    fps: int = 24
    desktop_fps: int = 15
    segment_seconds: int = 600
    crf: int = 23
    preset: str = "veryfast"
    audio_bitrate: str = "96k"
    watchdog_interval: float = 30.0
    voice_interval: float = 15.0
    encoder: str = "libx264"
    layout: str = None                    # fixed layout; None follows layout.jsonl
    layout_switch: str = "live"
    layout_interval: float = 1.0
    switch_timeout: float = 3.0
    cam2_fifo: Path = None
    cam2_json: Path = None
    cam2_stale: float = 3.0
    cam2_interval: float = 1.0
    hls_dir: Path = None
    rtmp_url: str = field(default=None, repr=False)
    test_sources: bool = False
    test_seconds: float = 0
    stats_period: float = STATS_PERIOD

    def __post_init__(self):
        base = Path(self.streamer_dir)
        object.__setattr__(self, "streamer_dir", base)
        object.__setattr__(self, "recordings_dir", Path(self.recordings_dir) if self.recordings_dir else base / "recordings")
        object.__setattr__(self, "voice_fifo", Path(self.voice_fifo) if self.voice_fifo else base / "voice.pcm")
        object.__setattr__(self, "cam2_fifo", Path(self.cam2_fifo) if self.cam2_fifo else base / "cam2.mjpeg")
        object.__setattr__(self, "cam2_json", Path(self.cam2_json) if self.cam2_json else base / "cam2.json")
        if not 10 <= self.desktop_fps <= MAX_DESKTOP_FPS:
            raise ValueError(f"desktop fps must be between 10 and {MAX_DESKTOP_FPS}")
        if not 10 <= self.fps <= MAX_FPS:
            raise ValueError(f"fps must be between 10 and {MAX_FPS}")
        if self.desktop_fps > self.fps:
            raise ValueError(f"desktop fps must not be above fps ({self.fps})")
        if self.segment_seconds < 10:
            raise ValueError("segment length must be at least 10 seconds")
        if not 0 <= self.crf <= 51:
            raise ValueError("crf must be between 0 and 51")
        if self.preset not in X264_PRESETS:
            raise ValueError("unknown x264 preset")
        if self.encoder not in ENCODERS:
            raise ValueError("encoder must be one of " + ", ".join(ENCODERS))
        if min(self.width, self.height, self.pip_width, self.pip_height) < 16:
            raise ValueError("frame sizes are too small")
        if not re.fullmatch(r":\d+(\.\d+)?", self.game_display) or not re.fullmatch(r":\d+(\.\d+)?", self.desktop_display):
            raise ValueError("displays look like :99.0")
        if self.layout is not None:
            object.__setattr__(self, "layout", validate_layout(self.layout))
        if self.layout_switch not in SWITCH_MODES:
            raise ValueError("layout switch must be live or restart")
        if min(self.switch_timeout, self.layout_interval, self.cam2_interval, self.cam2_stale, self.stats_period) <= 0:
            raise ValueError("intervals and timeouts must be positive")
        if self.test_seconds < 0:
            raise ValueError("test seconds must not be negative")
        if self.hls_dir is not None:
            object.__setattr__(self, "hls_dir", Path(self.hls_dir))
            check_tee_path(self.hls_dir, "the HLS directory")
        if self.rtmp_url is not None:
            validate_rtmp_url(self.rtmp_url)
        if self.hls_dir is not None or self.rtmp_url is not None:
            check_tee_path(self.recordings_dir, "the recordings directory (with HLS/RTMP)")


def cam2_scale(cfg):
    """cam2 is MJPEG (full-range yuvj422p, 1280x720): bilinear upscale and an explicit range conversion."""
    if cfg.test_sources:
        return f"scale={cfg.width}:{cfg.height}:flags=bilinear"
    return f"scale={cfg.width}:{cfg.height}:flags=bilinear:in_range=full:out_range=limited"


def _overlay(main, pip, out):
    return f"[{main}][{pip}]overlay=x=W-w-{PIP_MARGIN}:y=H-h-{PIP_MARGIN}:eof_action=pass[{out}]"


def build_filter_complex(layout, cfg):
    """ffmpeg filter graph for ONE layout (restart switching, post passes).
    Inputs: [0:v] game, [1:v] desktop, [3:v] cam2 (room only). Output label [vout]."""
    layout = validate_layout(layout)
    w, h, pw, ph, fps = cfg.width, cfg.height, cfg.pip_width, cfg.pip_height, cfg.fps
    if layout == "split":
        half_w = (w // 2) & ~1
        half_h = (half_w * h // w) & ~1
        return (f"[0:v]fps={fps},scale={half_w}:{half_h}:flags=area,setsar=1[l];"
                f"[1:v]fps={fps},scale={half_w}:{half_h}:flags=area,setsar=1[r];"
                f"[l][r]hstack=inputs=2,pad={w}:{h}:0:(oh-ih)/2:black,format=yuv420p[vout]")
    spec = LAYOUTS[layout]
    main_src, pip_src = SOURCES[spec["main"]], SOURCES[spec["pip"]]
    if spec["main"] == "game":
        main = f"[{main_src}]fps={fps},scale={w}:{h},setsar=1[main];"
    else:                                   # slower sources: scale at their own rate, then repeat frames up to fps
        if spec["main"] == "cam2":
            main = f"[{main_src}]{cam2_scale(cfg)},setsar=1,fps={fps},tpad=stop=-1:stop_mode=clone[main];"
        else:
            main = f"[{main_src}]scale={w}:{h},setsar=1,fps={fps}[main];"
    return (main + f"[{pip_src}]scale={pw}:{ph}:flags=area,setsar=1[pip];"
            f"[main][pip]overlay=x=W-w-{PIP_MARGIN}:y=H-h-{PIP_MARGIN}:eof_action=pass,format=yuv420p[vout]")


def build_live_graph(cfg, cam2, layout):
    """Every layout of the run in one graph; `streamselect@layout` (inputs in live_order(cam2)) picks the recorded one.
    Every streamselect input has the same size, format, rate and SAR, so a `map` command only changes the index and
    one command switches atomically (no frame of a half-switched composite)."""
    w, h, pw, ph, fps = cfg.width, cfg.height, cfg.pip_width, cfg.pip_height, cfg.fps
    half_w = (w // 2) & ~1
    half_h = (half_w * h // w) & ~1
    norm = f"scale={w}:{h},setsar=1,format=yuv420p"
    pip = f"scale={pw}:{ph}:flags=area,setsar=1"
    order = live_order(cam2)
    parts = [f"[0:v]fps={fps},{norm},split=3[gm][gp][gh]",
             f"[1:v]{norm},fps={fps},split=3[dm][dp][dh]",
             f"[gp]{pip},split=2[gpa][gpb]" if cam2 else f"[gp]{pip}[gpa]",
             f"[dp]{pip}[dpip]",
             _overlay("gm", "dpip", "lwebcam"),
             _overlay("dm", "gpa", "ldesktop"),
             f"[gh]scale={half_w}:{half_h}:flags=area,setsar=1[gl];[dh]scale={half_w}:{half_h}:flags=area,setsar=1[dr];"
             f"[gl][dr]hstack=inputs=2,pad={w}:{h}:0:(oh-ih)/2:black,setsar=1[lsplit]"]
    if cam2:
        parts += [f"[3:v]{cam2_scale(cfg)},setsar=1,format=yuv420p,fps={fps},tpad=stop=-1:stop_mode=clone[cm]",
                  _overlay("cm", "gpb", "lroom")]
    labels = "".join(f"[l{name}]" for name in order)
    parts.append(f"{labels}{SWITCH_TARGET}=inputs={len(order)}:map={order.index(effective_layout(layout, cam2))},"
                 f"format=yuv420p[vout]")
    return ";".join(parts)


def video_codec_args(cfg, encoder):
    """Encoder options; -r and -g follow --fps (keyframe every 2 s, so HLS cuts 4 s segments on keyframes)."""
    rate, gop = str(cfg.fps), str(cfg.fps * 2)
    if encoder == "libx264":
        return ["-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
                "-r", rate, "-g", gop]
    return ["-c:v", encoder, "-preset", "p4", "-tune", "ll", "-rc", "vbr", "-cq", str(cfg.crf), "-b:v", "0",
            "-bf", "2", "-g", gop, "-pix_fmt", "yuv420p", "-r", rate]


def output_args(cfg, prefix):
    """The direct segment muxer, or (with HLS/RTMP) the tee muxer over the same encode."""
    fragments = "movflags=+frag_keyframe+empty_moov+default_base_moof"
    pattern = str(Path(cfg.recordings_dir) / f"{prefix}-%03d.mp4")
    if cfg.hls_dir is None and not cfg.rtmp_url:
        return ["-fflags", "+flush_packets",          # a static screen makes tiny fragments: without this they sit in a 32 KB buffer
                "-f", "segment", "-segment_time", str(cfg.segment_seconds), "-reset_timestamps", "1",
                "-segment_format", "mp4", "-segment_format_options", fragments, pattern]
    branches = [f"[f=segment:segment_time={cfg.segment_seconds}:reset_timestamps=1:segment_format=mp4:"
                f"segment_format_options={fragments}:fflags=+flush_packets]{pattern}"]
    if cfg.hls_dir is not None:
        hls = Path(cfg.hls_dir)
        branches.append(f"[f=hls:onfail=ignore:hls_time={HLS_TIME}:hls_list_size={HLS_LIST_SIZE}:"
                        "hls_flags=delete_segments+independent_segments+omit_endlist+discont_start+temp_file+"
                        "program_date_time:"
                        f"hls_start_number_source=epoch:hls_segment_filename={hls / (prefix + '-%d.ts')}]"
                        f"{hls / HLS_PLAYLIST}")
    if cfg.rtmp_url:
        fifo = TEE_COLON.join(("drop_pkts_on_overflow=1", "attempt_recovery=1", "recovery_wait_time=5",
                               "restart_with_keyframe=1"))
        branches.append(f"[f=flv:onfail=ignore:use_fifo=1:fifo_options={fifo}]{cfg.rtmp_url}")
    # global headers: the mp4 fragments and flv need SPS/PPS up front; mpegts repeats them at every IDR itself
    return ["-flags", "+global_header", "-fflags", "+flush_packets", "-f", "tee", "|".join(branches)]


def build_ffmpeg_argv(cfg, *, prefix, window_id=None, voice=True, cam2=False, layout=None, live=False,
                      encoder=None, cam2_fps=None):
    """The one ffmpeg command line. `window_id` None captures the whole of :99.0 instead.

    `live` renders every layout and keeps ffmpeg's stdin command channel open (`-stdin`) for streamselect switches;
    otherwise the graph is the one `layout` and stdin is off (`-nostdin`), as in v1."""
    size = f"{cfg.width}x{cfg.height}"
    layout = effective_layout(layout or DEFAULT_LAYOUT, cam2)
    argv = [cfg.ffmpeg, "-hide_banner", "-stdin" if live else "-nostdin", "-loglevel", "warning",
            # key=value blocks on stdout (frame, fps, out_time_us, dup/drop, speed): the measured output rate
            "-progress", "pipe:1", "-stats_period", f"{cfg.stats_period:g}"]
    if cfg.test_sources:
        voice = True
        argv += ["-re", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={cfg.fps}",
                 "-re", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={cfg.desktop_fps}",
                 "-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    else:
        argv += ["-thread_queue_size", GRAB_QUEUE, "-f", "x11grab", "-framerate", str(cfg.fps), "-draw_mouse", "0"]
        argv += ["-window_id", str(int(window_id))] if window_id else ["-video_size", size]
        argv += ["-i", cfg.game_display,
                 "-thread_queue_size", GRAB_QUEUE, "-f", "x11grab", "-framerate", str(cfg.desktop_fps),
                 "-draw_mouse", "0", "-video_size", size, "-i", cfg.desktop_display]
        if voice:
            argv += ["-thread_queue_size", "4096", "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", str(cfg.voice_fifo)]
        else:
            argv += ["-re", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    if cam2:
        if cfg.test_sources:
            argv += ["-re", "-f", "lavfi", "-i", f"testsrc2=size={CAM2_SIZE}:rate={cfg.fps}"]
        else:
            rate = max(1, min(MAX_FPS, round(cam2_fps or cfg.fps)))     # metadata only: timestamps are the wallclock
            # arrival wallclock as timestamps (x11grab uses the wallclock too); probe small so a launch is quick
            argv += ["-thread_queue_size", "512", "-use_wallclock_as_timestamps", "1", "-probesize", "2000000",
                     "-analyzeduration", "1000000", "-f", "mjpeg", "-framerate", str(rate), "-i", str(cfg.cam2_fifo)]
    graph = build_live_graph(cfg, cam2, layout) if live else build_filter_complex(layout, cfg)
    if voice:
        # apad: if the voice server goes away the FIFO hits EOF; silence keeps the audio track running meanwhile
        graph += ";[2:a]apad[aout]"
    argv += ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]" if voice else "2:a",
             *video_codec_args(cfg, encoder or cfg.encoder), "-max_muxing_queue_size", "1024",
             "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-ar", "48000", "-ac", "2"]
    if cfg.test_seconds:
        argv += ["-t", f"{cfg.test_seconds:g}"]
    return argv + output_args(cfg, prefix)


def probe_encoder(cfg, encoder, run=None, timeout=30):
    """-> (ok, reason). A 1 s lavfi encode with the real encoder options (NVENC needs a GPU, a driver and the
    session limit not reached); libx264 is never probed."""
    if encoder == "libx264":
        return True, "libx264 needs no probe"
    run = run or subprocess.run
    argv = [cfg.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc2=size={cfg.width}x{cfg.height}:rate={cfg.fps}:duration=1",
            *video_codec_args(cfg, encoder), "-f", "null", "-"]
    try:
        done = run(argv, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"probe could not run: {exc.__class__.__name__}: {exc}"[:300]
    if done.returncode == 0:
        return True, f"{encoder} probe passed"
    lines = [line.strip() for line in (done.stderr or "").splitlines() if line.strip()]
    # the encoder's own lines say why (no libcuda, no device, session limit); the generic tail does not
    why = [line for line in lines if re.search(r"nvenc|cuda|device|driver|session", line, re.I)] or lines[-2:]
    return False, f"{encoder} probe exited {done.returncode}: " + " | ".join(why[:2])[:260]


# ------------------------------------------------------------- recordings

def iso(unix):
    return datetime.fromtimestamp(unix, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_prefix(moment):
    return moment.astimezone(timezone.utc).strftime("sub01-%Y%m%d-%H%M%S")


def unique_prefix(directory, moment):
    """A run prefix no existing segment uses, moving forward a second at a time."""
    names = list(os.listdir(directory)) if Path(directory).is_dir() else []
    for _ in range(3600):
        prefix = run_prefix(moment)
        if not any(n.startswith(prefix + "-") for n in names):
            return prefix
        moment += timedelta(seconds=1)
    raise RuntimeError("no free recording prefix")


def list_segments(directory):
    """Segment files of the recordings directory, oldest first: [{name, run, index, bytes, mtime}]."""
    out = []
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return out
    for entry in entries:
        m = SEGMENT_RE.match(entry.name)
        if not m or not entry.is_file():
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        out.append({"name": entry.name, "run": m.group(1), "index": int(m.group(2)),
                    "bytes": st.st_size, "mtime": iso(st.st_mtime)})
    return sorted(out, key=lambda s: (s["run"], s["index"]))


def run_bytes(segments, prefix):
    return sum(s["bytes"] for s in segments if s["run"] == prefix)


def prune_hls(directory, keep_prefix, now, max_age=60.0):
    """Delete HLS segments of earlier runs once older than `max_age` s (a player may still fetch the last ones;
    the running muxer deletes its own). -> number removed."""
    removed = 0
    try:
        entries = list(os.scandir(directory))
    except OSError:
        return 0
    for entry in entries:
        m = HLS_SEGMENT_RE.match(entry.name)
        if not m or m.group(1) == keep_prefix:
            continue
        try:
            if now - entry.stat().st_mtime > max_age:
                os.unlink(entry.path)
                removed += 1
        except OSError:
            continue
    return removed


def hls_state(directory, prefix):
    try:
        names = os.listdir(directory)
    except OSError:
        return {"dir": str(directory), "playlist": False, "segments": 0}
    return {"dir": str(directory), "playlist": HLS_PLAYLIST in names,
            "segments": sum(1 for n in names if prefix and n.startswith(prefix + "-") and n.endswith(".ts"))}


WATCHDOG_GRACE = 60.0
STALL_LIMIT = 2


def watchdog_decision(prev_bytes, cur_bytes, stalled_checks, *, alive, uptime,
                      grace=WATCHDOG_GRACE, limit=STALL_LIMIT):
    """-> (action, stalled_checks). action: down | grace | ok | stalled | restart."""
    if not alive:
        return "down", 0
    if uptime < grace:
        return "grace", 0
    if cur_bytes > prev_bytes:
        return "ok", 0
    stalled_checks += 1
    return ("restart" if stalled_checks >= limit else "stalled"), stalled_checks


def voice_decision(running_with_voice, available, mismatches, *, uptime, gap=False, need=2, min_uptime=30.0):
    """-> (action, mismatches). action: keep | wait | switch.

    A run without voice switches to it once the writer has been there for `need` checks in a row. A run with
    voice keeps going when the writer vanishes (apad records silence), but its audio input has hit EOF for good,
    so once the writer is back (`gap`) the run is relaunched to get the voice again."""
    if running_with_voice:
        if available and gap:
            return ("switch" if uptime >= min_uptime else "wait"), 0
        return "keep", 0
    if not available:
        return "keep", 0
    mismatches += 1
    return ("switch" if mismatches >= need and uptime >= min_uptime else "wait"), mismatches


CAM2_MIN_UPTIME = 30.0      # a run is at least this old before it is relaunched to add cam2 (no relaunch loop)
CAM2_DROP = "cam2 stopped delivering"
REPLY_GRACE = 0.5           # after a non-zero command reply, wait this long for another filtergraph's ret:0


def cam2_decision(running_with_cam2, available, checks, *, uptime, wanted, need=2, min_uptime=CAM2_MIN_UPTIME):
    """-> (action, checks). action: keep | drop | wait | ready | add.

    A run reading cam2 is relaunched without it at once when cam2 stops (a stalled FIFO stalls the whole graph).
    A run without it is relaunched with it only when the wanted layout needs it (`room`), after `need` good checks
    in a row; otherwise cam2 is `ready` for the next launch."""
    if running_with_cam2:
        return ("keep" if available else "drop"), 0
    if not available:
        return "keep", 0
    checks += 1
    if checks < need:
        return "wait", checks
    if not wanted:
        return "ready", checks
    return ("add" if uptime >= min_uptime else "wait"), checks


def _number(value, kind=float):
    try:
        return kind(str(value).strip().rstrip("x"))
    except (TypeError, ValueError):
        return None


class OutputMeter:
    """ffmpeg's `-progress` blocks -> the measured output rate, now and per recording-segment window.

    `fps_measured` is output frames per wall second between two blocks (60 at the 60 fps profile when ffmpeg keeps
    up in real time); ffmpeg's own `fps=` is the average since the run started. A window record closes at the block
    where the output time passed the next multiple of the segment length, and at the end of the run (`partial`). It is
    an approximation of the segment file of that number: the muxer cuts at the first keyframe after segment_time and
    blocks come every stats period, so a record can hold a few seconds of the neighbouring file. dup/drop are ffmpeg's
    -r output counters: frames a source did not deliver are repeated by the graph's fps filters before that, so check
    distinct frames offline with mpdecimate (RUNBOOK)."""

    def __init__(self, segment_seconds, prefix=None, history=None):
        self.segment_seconds, self.prefix = segment_seconds, prefix
        self.history = history if history is not None else deque(maxlen=24)
        self.latest = None
        self._block, self._prev, self._seg, self._last = {}, None, None, None

    def feed(self, line, now):
        """One `key=value` line of the progress output. -> the window records it finished (usually none)."""
        key, sep, value = line.strip().partition("=")
        if not sep:
            return []
        if key != "progress":
            self._block[key] = value
            return []
        block, self._block = self._block, {}
        frame = _number(block.get("frame"), int)
        if frame is None:
            return []
        out_us = _number(block.get("out_time_us"), int)
        out_s = out_us / 1e6 if out_us is not None and out_us >= 0 else None
        dup, drop = _number(block.get("dup_frames"), int) or 0, _number(block.get("drop_frames"), int) or 0
        window = None
        if self._prev is not None and now > self._prev[0]:
            window = (frame - self._prev[1]) / (now - self._prev[0])
        self._prev = (now, frame)
        self.latest = {"frames": frame, "fps_measured": None if window is None else round(window, 2),
                       "fps_ffmpeg": _number(block.get("fps")), "speed": _number(block.get("speed")),
                       "dup_frames": dup, "drop_frames": drop,
                       "out_time_s": None if out_s is None else round(out_s, 2)}
        self._last = (now, frame, out_s, dup, drop)
        index = int(out_s // self.segment_seconds) if out_s is not None else 0
        if self._seg is None:                    # the first block (ffmpeg prints one at start) is the baseline
            self._seg = (index, now, frame, out_s or 0.0, dup, drop)
            return []
        records = []
        if index > self._seg[0]:                 # crossed into the next window (also on the end block)
            records.append(self._close(partial=False))
            self._seg = (index, now, frame, out_s or 0.0, dup, drop)
        if value == "end":
            records += self.finish()
        return records

    def finish(self):
        """The run ended (progress=end, SIGINT, crash): close the open window as partial. -> [] or [record]"""
        if self._seg is None or self._last is None:
            return []
        seg, self._seg = self._seg, None
        if self._last[1] <= seg[2]:              # no frame since the window opened: nothing to report
            return []
        self._seg = seg
        record = self._close(partial=True)
        self._seg = None
        return [record]

    def _close(self, partial):
        index, t0, f0, o0, d0, r0 = self._seg
        now, frame, out_s, dup, drop = self._last
        wall, frames = now - t0, frame - f0
        media = None if out_s is None else out_s - o0
        record = {"segment": f"{self.prefix}-{index:03d}.mp4" if self.prefix else index, "frames": frames,
                  "wall_s": round(wall, 1), "media_s": None if media is None else round(media, 1),
                  "fps": round(frames / wall, 2) if wall > 0 else None,
                  "fps_media": round(frames / media, 2) if media else None,
                  "dup_frames": dup - d0, "drop_frames": drop - r0, "partial": partial}
        self.history.append(record)
        return record


BACKOFF = (2, 4, 8, 16, 32, 60)


def backoff_delay(failures):
    """Seconds to wait after `failures` consecutive short-lived ffmpeg runs."""
    return 1.0 if failures <= 0 else float(BACKOFF[min(failures, len(BACKOFF)) - 1])


# ---------------------------------------------------------------- layout log

def read_last_layout(path, max_bytes=4096):
    """The canonical layout of the last line of layout.jsonl, or None (no file, a half-written or bad line, an
    unknown name: the current layout stays)."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            data = handle.read()
    except OSError:
        return None
    lines = [line for line in data.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        record = json.loads(lines[-1])
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    try:
        return validate_layout(record.get("layout"))
    except ValueError:
        return None


# ------------------------------------------------------------------ voice

def fifo_has_writer(fifo_stat, proc_root="/proc"):
    try:
        pids = [p for p in os.listdir(proc_root) if p.isdigit()]
    except OSError:
        return False
    for pid in pids:
        fd_dir = os.path.join(proc_root, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                st = os.stat(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if (st.st_dev, st.st_ino) != (fifo_stat.st_dev, fifo_stat.st_ino):
                continue
            try:
                with open(os.path.join(proc_root, pid, "fdinfo", fd)) as handle:
                    for line in handle:
                        if line.startswith("flags:") and int(line.split()[1], 8) & os.O_ACCMODE:
                            return True
            except (OSError, ValueError, IndexError):
                continue
    return False


class VoiceTap:
    """A read end on a FIFO (the voice PCM, or cam2's MJPEG), kept open by the director (see the module docstring)."""

    SETTLE = 1.5          # seconds a freshly opened tap waits for a polling writer (the voice server retries every 0.1 s)

    def __init__(self, path, proc_root="/proc", create=True, clock=time.monotonic, sleep=time.sleep, what="voice"):
        self.path, self.proc_root, self.create, self.what = Path(path), proc_root, create, what
        self.fd = self.ident = self.opened_at = None
        self._clock, self._sleep = clock, sleep
        self._lock = threading.RLock()      # the event loop drains while a worker thread probes

    def refresh(self):
        """Open (creating the FIFO if missing) or re-open when the path now names another file. -> (ok, reason)"""
        with self._lock:
            try:
                st = os.stat(self.path)
            except FileNotFoundError:
                self.close()
                if not self.create:
                    return False, f"{self.what} FIFO does not exist"
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    os.mkfifo(self.path, 0o600)
                    st = os.stat(self.path)
                except OSError as exc:
                    return False, f"cannot create the {self.what} FIFO: {exc.strerror}"
            except OSError as exc:
                self.close()
                return False, f"cannot stat the {self.what} FIFO: {exc.strerror}"
            if not stat.S_ISFIFO(st.st_mode):
                self.close()
                return False, f"{self.what} path is not a FIFO"
            if self.fd is not None and self.ident == (st.st_dev, st.st_ino):
                return True, ""
            self.close()
            try:
                self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError as exc:
                return False, f"cannot open the {self.what} FIFO: {exc.strerror}"
            self.ident, self.opened_at = (st.st_dev, st.st_ino), self._clock()
            return True, ""

    def writer_present(self, settle=None):
        """-> (usable, reason). Waits out the settle time after a fresh open so a polling writer can attach."""
        settle = self.SETTLE if settle is None else settle
        while True:
            with self._lock:
                ok, reason = self.refresh()
                if not ok:
                    return False, reason
                found = fifo_has_writer(os.fstat(self.fd), self.proc_root)
                waited = self._clock() - self.opened_at
            if found:
                return True, "writer present"
            if waited >= settle:
                return False, f"no process writes to the {self.what} FIFO"
            self._sleep(0.1)

    def drain(self, limit=1 << 20):
        """Discard whatever is in the pipe (when ffmpeg is not the reader). -> bytes discarded."""
        total = 0
        with self._lock:
            while self.fd is not None and total < limit:
                try:
                    chunk = os.read(self.fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                total += len(chunk)
        return total

    def close(self):
        with self._lock:
            if self.fd is not None:
                try:
                    os.close(self.fd)
                except OSError:
                    pass
            self.fd = self.ident = None


FifoTap = VoiceTap


# ------------------------------------------------------------------- cam2

CAM2_TIME_KEYS = ("last_frame_unix", "last_frame_t", "last_frame", "last_frame_at", "updated_unix", "updated", "t")


def parse_time(value):
    """Unix seconds (or milliseconds) or an ISO-8601 string -> unix seconds; anything else (a monotonic clock) None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            try:
                moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError:
                return None
            return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).timestamp()
    if isinstance(value, (int, float)):
        value = float(value)
        if value > 1e12:
            value /= 1000.0
        return value if value > 1e9 else None
    return None


def cam2_report(path, now):
    """-> (age of the last cam2 frame in s, or None without cam2.json; fps or None). cam2.json fields tried in
    order: a `last_frame_age_s`, a time under one of CAM2_TIME_KEYS, else the file's mtime."""
    try:
        st = os.stat(path)
        raw = Path(path).read_bytes()[:65536]
    except OSError:
        return None, None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        data = None
    data = data if isinstance(data, dict) else {}
    fps = data.get("fps")
    fps = float(fps) if isinstance(fps, (int, float)) and not isinstance(fps, bool) and 1 <= fps <= 240 else None
    age = data.get("last_frame_age_s")
    if isinstance(age, (int, float)) and not isinstance(age, bool) and age >= 0:
        return float(age) + max(0.0, now - st.st_mtime), fps
    last = next((t for t in (parse_time(data.get(k)) for k in CAM2_TIME_KEYS) if t is not None), st.st_mtime)
    return now - last, fps


def cam2_status(cfg, tap, now, writer=True):
    """-> (usable, reason, fps). Usable: cam2.json reports a fresh frame and (with `writer`) a process holds the FIFO
    open for writing. The tap is (re)opened first in every case, so a non-blocking writer can always attach; the /proc
    scan for the writer runs only when the frame is fresh."""
    ok, reason = tap.refresh()
    if not ok:
        return False, reason, None
    age, fps = cam2_report(cfg.cam2_json, now)
    if age is None:
        return False, "no cam2.json next to the cam2 FIFO", fps
    if age > cfg.cam2_stale:
        return False, f"cam2 last frame {age:.1f}s ago", fps
    if writer:
        ok, reason = tap.writer_present(settle=0)
        if not ok:
            return False, reason, fps
    return True, f"cam2 last frame {max(age, 0.0):.1f}s ago" + (", writer present" if writer else ""), fps


# ------------------------------------------------------------ game window

def display_root(display):
    return display.split(".")[0]


def pick_window(candidates, prefix):
    """Among {id, name, width, height}, the biggest window whose name starts with `prefix`."""
    named = [c for c in candidates if str(c.get("name", "")).startswith(prefix)]
    if not named:
        return None
    return max(named, key=lambda c: (c.get("width", 0) * c.get("height", 0), c["id"]))


def parse_geometry(text):
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    try:
        return int(values["WIDTH"]), int(values["HEIGHT"])
    except (KeyError, ValueError):
        return 0, 0


def read_pid(path):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def find_game_window(cfg, run=subprocess.run):
    """-> (window id or None, note). `xdotool search --pid <pid>` (or by name) on :99, name filter on top."""
    if cfg.window_id:
        return int(cfg.window_id), "fixed by --window-id"
    env = dict(os.environ, DISPLAY=display_root(cfg.game_display))
    pid = cfg.game_pid or (read_pid(cfg.game_pid_file) if cfg.game_pid_file else None)

    def xdotool(*args):
        done = run([cfg.xdotool, *args], capture_output=True, text=True, timeout=5, env=env)
        return done.stdout if done.returncode == 0 else ""

    try:
        search = ["search", "--pid", str(pid)] if pid else ["search", "--name", "^" + re.escape(cfg.window_prefix)]
        ids = [int(x) for x in xdotool(*search).split() if x.isdigit()]
        candidates = []
        for wid in ids:
            width, height = parse_geometry(xdotool("getwindowgeometry", "--shell", str(wid)))
            candidates.append({"id": wid, "name": xdotool("getwindowname", str(wid)).strip(),
                               "width": width, "height": height})
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"xdotool unavailable: {exc}"
    chosen = pick_window(candidates, cfg.window_prefix)
    if chosen is None:
        return None, f"no window named {cfg.window_prefix}* on {display_root(cfg.game_display)}"
    return chosen["id"], f"window {chosen['name']!r}"


# ----------------------------------------------------------------- events

def append_jsonl(path, record):
    """One O_APPEND write per line, so the director and the agent can share events.jsonl."""
    data = (json.dumps(record, separators=(",", ":")) + "\n").encode()
    Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


# --------------------------------------------------------------- director

async def spawn_ffmpeg(argv):
    """ffmpeg gets its own session: the supervisor signals the director's whole process group on stop, and a
    second signal (SIGTERM from the group, then our SIGINT) makes ffmpeg exit without writing the last fragment.
    With `-stdin` (live layout switching) its stdin is a pipe the director writes filter commands to."""
    interactive, progress = "-stdin" in argv, "-progress" in argv
    return await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE if interactive else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE if progress else asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        start_new_session=True)


class Director:
    STABLE_SECONDS = 60.0

    def __init__(self, cfg, *, spawn=None, find_window=None, check_voice=None, check_cam2=None, probe=None,
                 clock=time.monotonic, wall=time.time, sleep=asyncio.sleep):
        self.cfg = cfg
        self._spawn = spawn or spawn_ffmpeg
        self._find_window = find_window or (lambda: find_game_window(cfg))
        self.tap = VoiceTap(cfg.voice_fifo)
        self.cam2_tap = FifoTap(cfg.cam2_fifo, create=False, what="cam2")
        self._check_voice = check_voice or self.tap.writer_present
        self._check_cam2 = check_cam2 or (lambda writer=True: cam2_status(cfg, self.cam2_tap, self._wall(), writer))
        self._probe = probe or (lambda encoder: probe_encoder(cfg, encoder))
        self._clock, self._wall, self._sleep = clock, wall, sleep
        self._secrets = secret_parts(cfg.rtmp_url)
        self.proc = None
        self.prefix = None
        self.started_mono = self.started_wall = None
        self.first_started_wall = None
        self.launches = 0
        self.last_error = None
        self.voice, self.voice_reason = None, ""
        self.cam2, self.cam2_reason, self.cam2_fps = None, "", None
        self.cam2_now, self.cam2_checks, self._cam2_ticks, self._cam2_ident = False, 0, 0, None
        self.game_source = self.game_note = None
        self.encoder, self.encoder_note = ((cfg.encoder, "requested") if cfg.encoder == "libx264"
                                           else (None, "not probed yet"))
        self.layout = cfg.layout or DEFAULT_LAYOUT
        self.live_layout, self.live_order = None, ()
        self.meter, self.fps_history = None, deque(maxlen=24)
        self.last_switch = None
        self.watchdog_action = None
        self.stalled_checks = 0
        self.voice_mismatches = 0
        self.voice_gap = False
        self.last_restart_reason = None
        self._failures = 0
        self._last_bytes = 0
        self._tail = deque(maxlen=40)
        self._printed = 0
        self._stopping = False
        self._restart_reason = None
        self._restart = self._stop_event = None
        self._replies = asyncio.Queue()
        self._switch_lock = asyncio.Lock()
        self._layout_sig = None
        self._tasks = set()

    # -- observable state
    @property
    def alive(self):
        return self.proc is not None and self.proc.returncode is None

    @property
    def restarts(self):
        return max(0, self.launches - 1)

    def uptime(self):
        return self._clock() - self.started_mono if self.alive and self.started_mono is not None else 0.0

    def state(self):
        segments = list_segments(self.cfg.recordings_dir)
        cfg = self.cfg
        return {
            "recording": self.alive and self.watchdog_action not in ("stalled", "restart"),
            "since": iso(self.started_wall) if self.alive and self.started_wall else None,
            "first_started": iso(self.first_started_wall) if self.first_started_wall else None,
            "run": self.prefix,
            "segments": [{k: s[k] for k in ("name", "bytes", "mtime")} for s in segments[-100:]],
            "segments_total": len(segments),
            "ffmpeg_pid": self.proc.pid if self.alive else None,
            "restarts": self.restarts,
            "last_error": self.last_error,
            "last_restart_reason": self.last_restart_reason,
            "layout": self.layout,
            "live_layout": self.live_layout if self.alive else None,
            "layout_fixed": cfg.layout is not None,
            "layout_switch": cfg.layout_switch,
            "layouts_available": list(live_order(bool(self.cam2) or self.cam2_now)),
            "last_switch": self.last_switch,
            "encoder": self.encoder,
            "encoder_requested": cfg.encoder,
            "encoder_note": self.encoder_note,
            "fps": cfg.fps,
            "desktop_fps": cfg.desktop_fps,
            "output": self.meter.latest if self.alive and self.meter else None,
            "segments_fps": list(self.fps_history)[-12:],
            "cam2": self.cam2,
            "cam2_reason": self.cam2_reason,
            "cam2_fps": self.cam2_fps,
            "hls": hls_state(cfg.hls_dir, self.prefix) if cfg.hls_dir is not None else None,
            "rtmp": bool(cfg.rtmp_url),
            "test_sources": cfg.test_sources,
            "voice": self.voice,
            "voice_reason": self.voice_reason,
            "game_source": self.game_source,
            "game_note": self.game_note,
            "watchdog": self.watchdog_action,
            "recordings_dir": str(cfg.recordings_dir),
        }

    def event(self, kind, **fields):
        record = {"t": iso(self._wall()), "source": "director", "kind": kind, **fields}
        print(json.dumps(record), flush=True)
        try:
            append_jsonl(self.cfg.streamer_dir / "events.jsonl", record)
        except OSError:
            pass

    # -- layout
    def set_layout(self, layout):
        """Validate, remember and log a layout request (one line of layout.jsonl). With --layout the request is
        logged but the fixed layout stays."""
        requested = layout
        layout = validate_layout(layout)
        previous = self.layout
        if self.cfg.layout is None:
            self.layout = layout
        record = {"t": iso(self._wall()), "unix": round(self._wall(), 3), "layout": layout, "previous": previous,
                  "run": self.prefix if self.alive else None,
                  "offset_s": round(self.uptime(), 2) if self.alive else None, "recording": self.alive}
        if requested != layout:
            record["requested"] = requested
        if self.cfg.layout is not None:
            record["fixed"] = self.cfg.layout
        append_jsonl(self.cfg.streamer_dir / "layout.jsonl", record)
        return record

    def poll_layout_log(self):
        """Follow the last line of layout.jsonl (only re-read when its size or mtime changed). -> layout or None."""
        if self.cfg.layout is not None:
            return None
        path = self.cfg.streamer_dir / "layout.jsonl"
        try:
            st = os.stat(path)
            sig = (st.st_size, st.st_mtime_ns)
        except OSError:
            sig = None
        if sig == self._layout_sig:
            return None
        self._layout_sig = sig
        name = read_last_layout(path) if sig else None
        if name:
            self.layout = name
        return name

    def kick_layout(self):
        """Apply the wanted layout now (after a POST) instead of at the next layout tick."""
        if self._restart is None or self._stopping:
            return
        task = asyncio.ensure_future(self.apply_layout())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def apply_layout(self):
        """Bring the running ffmpeg to the wanted layout: live through streamselect, else by a relaunch.
        -> idle | same | live | restart"""
        async with self._switch_lock:
            if not self.alive or self._restart_reason:
                return "idle"
            proc, wanted = self.proc, self.layout
            if LAYOUTS[wanted]["needs_cam2"] and not self.cam2 and self.cam2_now:
                # right after a relaunch that dropped a stalled cam2, wait (no relaunch loop); cam2_tick adds it later
                if self.last_restart_reason != CAM2_DROP or self.uptime() >= CAM2_MIN_UPTIME:
                    self.request_restart(f"layout {wanted}: relaunch with cam2")
                    return "restart"
            target = effective_layout(wanted, self.cam2)
            if target == self.live_layout:
                return "same"
            if self.cfg.layout_switch != "live" or target not in self.live_order:
                self._note_switch(target, "restart", True, 0)
                self.request_restart(f"layout {target}")
                return "restart"
            started = self._clock()
            ok, detail = await self.send_command(SWITCH_TARGET, "map", str(self.live_order.index(target)))
            ms = round((self._clock() - started) * 1000)
            if self.proc is not proc or self._restart_reason:
                return "stale"                   # relaunched meanwhile: the new run starts with the wanted layout
            if ok:
                previous, self.live_layout = self.live_layout, target
                self._note_switch(target, "live", True, ms)
                self.event("layout_switched", layout=target, previous=previous, how="live", ms=ms, run=self.prefix)
                return "live"
            self._note_switch(target, "restart", False, ms, detail)
            self.event("layout_switch_failed", layout=target, detail=detail, ms=ms, run=self.prefix)
            self.request_restart(f"layout {target} (live switch failed: {detail})")
            return "restart"

    def _note_switch(self, layout, how, ok, ms, detail=None):
        self.last_switch = {"t": iso(self._wall()), "layout": layout, "how": how, "ok": ok, "ms": ms, "detail": detail}

    async def send_command(self, target, command, arg):
        """One filter command through ffmpeg's stdin channel (`c` + `<target> -1 <command> <arg>`). -> (ok, detail)"""
        writer = getattr(self.proc, "stdin", None)
        if writer is None:
            return False, "ffmpeg has no command channel"
        while not self._replies.empty():
            self._replies.get_nowait()
        try:
            writer.write(f"c{target} -1 {command} {arg}\n".encode())   # one write, well under PIPE_BUF
            await writer.drain()
        except (OSError, RuntimeError) as exc:
            return False, f"cannot write to ffmpeg: {exc.__class__.__name__}"
        # ffmpeg answers once per filtergraph; a run without voice has a second (audio) graph that answers ENOSYS
        last, deadline = None, self._clock() + self.cfg.switch_timeout
        try:
            while True:
                left = deadline - self._clock()
                if left <= 0:
                    raise asyncio.TimeoutError
                last = await asyncio.wait_for(self._replies.get(), left)
                if last == 0:
                    return True, "ret 0"
                deadline = min(deadline, self._clock() + REPLY_GRACE)
        except asyncio.TimeoutError:
            return False, "no reply from ffmpeg" if last is None else f"ffmpeg replied ret {last}"

    # -- control
    def request_restart(self, reason):
        self._restart_reason = reason
        if self._restart is not None:
            self._restart.set()

    def stop(self):
        self._stopping = True
        if self._stop_event is not None:
            self._stop_event.set()

    async def watchdog_tick(self):
        cur = run_bytes(list_segments(self.cfg.recordings_dir), self.prefix)
        action, self.stalled_checks = watchdog_decision(
            self._last_bytes, cur, self.stalled_checks, alive=self.alive, uptime=self.uptime())
        self._last_bytes = cur
        self.watchdog_action = action
        if action == "restart":
            self.last_error = f"segment file did not grow for {self.stalled_checks} checks"
            self.event("watchdog_restart", run=self.prefix, bytes=cur)
            self.request_restart("segment growth stalled")
        if self.cfg.hls_dir is not None and self.prefix:
            prune_hls(self.cfg.hls_dir, self.prefix, self._wall())
        return action

    async def voice_tick(self):
        if not self.alive or self.voice is None or self.cfg.test_sources:
            return "idle"
        available, reason = await asyncio.to_thread(self._check_voice)
        if self.voice and not available:
            self.voice_gap = True
        action, self.voice_mismatches = voice_decision(
            self.voice, available, self.voice_mismatches, uptime=self.uptime(), gap=self.voice_gap)
        if action == "switch":
            self.event("voice_changed", voice=available, reason=reason)
            self.request_restart("voice reconnected" if self.voice else "voice came online")
        return action

    async def cam2_tick(self):
        if not self.alive or self.cfg.test_sources or self._restart_reason:
            return "idle"
        # a stalled cam2 freezes the whole graph: while the run reads it, cam2.json freshness is checked every tick
        # (cheap) and the /proc writer scan every 5th
        self._cam2_ticks += 1
        writer = not self.cam2 or self._cam2_ticks % 5 == 0
        available, reason, fps = await asyncio.to_thread(self._check_cam2, writer)
        if self.cam2 and available and self.cam2_tap.ident != self._cam2_ident:
            available, reason = False, "cam2 FIFO was replaced (ffmpeg still reads the old one)"
        self.cam2_now = available
        action, self.cam2_checks = cam2_decision(bool(self.cam2), available, self.cam2_checks, uptime=self.uptime(),
                                                 wanted=LAYOUTS[self.layout]["needs_cam2"])
        if action == "drop":
            self.cam2_reason = reason
            self.event("cam2_changed", cam2=False, reason=reason, run=self.prefix)
            self.request_restart(CAM2_DROP)
        elif action == "add":
            self.cam2_fps = fps
            self.event("cam2_changed", cam2=True, reason=reason, run=self.prefix)
            self.request_restart("cam2 came online")
        return action

    async def layout_tick(self):
        self.poll_layout_log()
        return await self.apply_layout()

    async def drain_tick(self):
        """While ffmpeg is not a FIFO's reader the director is, so its writer never sees a stalled reader."""
        if not (self.alive and self.voice):
            self.tap.drain()
        if not (self.alive and self.cam2):
            self.cam2_tap.drain(limit=4 << 20)                # MJPEG 720p60 is up to ~9 MB/s

    async def _loop(self, interval, tick):
        while not self._stopping:
            if await self._pause(interval):
                return
            try:
                await tick()
            except Exception as exc:  # a watchdog must never die of its own bug
                self.event("watchdog_error", error=repr(exc))

    async def _pause(self, seconds):
        """Sleep; True when shutdown was requested meanwhile."""
        waiter = asyncio.ensure_future(self._stop_event.wait())
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        await asyncio.wait({waiter, sleeper}, return_when=asyncio.FIRST_COMPLETED)
        for task in (waiter, sleeper):
            task.cancel()
        return self._stopping

    async def resolve_encoder(self):
        """Probe the requested NVENC encoder once; libx264 when it fails."""
        if self.encoder is not None:
            return self.encoder
        requested = self.cfg.encoder
        ok, reason = await asyncio.to_thread(self._probe, requested)
        if ok:
            self.encoder, self.encoder_note = requested, reason
        else:
            self.encoder, self.encoder_note = "libx264", reason
            self.event("encoder_fallback", requested=requested, active="libx264", reason=reason)
        return self.encoder

    async def run(self):
        self._restart, self._stop_event = asyncio.Event(), asyncio.Event()
        if self._stopping:
            self._stop_event.set()
        self.cfg.recordings_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.cfg.streamer_dir / "pids").mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.cfg.hls_dir is not None:
            Path(self.cfg.hls_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        await self.reap_stale_ffmpeg()
        await self.resolve_encoder()
        self.poll_layout_log()                       # resume with the last requested layout
        watchers = [asyncio.ensure_future(self._loop(self.cfg.watchdog_interval, self.watchdog_tick)),
                    asyncio.ensure_future(self._loop(self.cfg.voice_interval, self.voice_tick)),
                    asyncio.ensure_future(self._loop(self.cfg.cam2_interval, self.cam2_tick)),
                    asyncio.ensure_future(self._loop(self.cfg.layout_interval, self.layout_tick)),
                    asyncio.ensure_future(self._loop(0.1, self.drain_tick))]
        try:
            while not self._stopping:
                outcome = await self._run_once()
                if self._stopping:
                    break
                delay = backoff_delay(self._failures) if outcome == "crash" else 1.0
                self.event("ffmpeg_restart_scheduled", delay=delay, outcome=outcome)
                if await self._pause(delay):
                    break
        finally:
            for task in watchers + list(self._tasks):
                task.cancel()
            await asyncio.gather(*watchers, *self._tasks, return_exceptions=True)
            self.tap.close()
            self.cam2_tap.close()

    async def _sources(self):
        """-> (window, note, voice, cam2) for the next launch."""
        cfg = self.cfg
        if cfg.test_sources:
            self.game_source, self.game_note = "test", "lavfi testsrc2 test sources"
            self.voice_reason = "lavfi sine test source"
            self.cam2_reason, self.cam2_fps = "lavfi testsrc2 test source", cfg.fps
            return None, self.game_note, True, True
        window, note = await asyncio.to_thread(self._find_window)
        self.game_source = f"window:{window:#x}" if window else "screen"
        self.game_note = note if window else f"window not found, recording the whole of {cfg.game_display}: {note}"
        voice, self.voice_reason = await asyncio.to_thread(self._check_voice)
        if voice:
            self.tap.drain()                                  # no stale audio at the start of the run
        cam2, self.cam2_reason, self.cam2_fps = await asyncio.to_thread(self._check_cam2)
        if cam2:
            self.cam2_tap.drain()                             # start at a fresh frame
        self._cam2_ident = self.cam2_tap.ident if cam2 else None
        return window, note, voice, cam2

    async def _run_once(self):
        cfg = self.cfg
        window, note, voice, available = await self._sources()
        self.cam2_now = available
        live = cfg.layout_switch == "live"
        cam2 = available and (live or LAYOUTS[self.layout]["needs_cam2"])
        target = effective_layout(self.layout, cam2)
        prefix = unique_prefix(cfg.recordings_dir, datetime.fromtimestamp(self._wall(), timezone.utc))
        argv = build_ffmpeg_argv(cfg, prefix=prefix, window_id=window, voice=voice, cam2=cam2, layout=target,
                                 live=live, encoder=self.encoder, cam2_fps=self.cam2_fps)
        self._tail.clear()
        self._printed = 0
        try:
            proc = await self._spawn(argv)
        except (OSError, ValueError) as exc:
            self.last_error = f"cannot start ffmpeg: {exc}"
            self.event("ffmpeg_spawn_failed", error=str(exc))
            self._failures += 1
            return "crash"
        self.launches += 1
        self.proc, self.prefix, self.voice, self.cam2 = proc, prefix, voice, cam2
        self.live_layout, self.live_order = target, (live_order(cam2) if live else (target,))
        self.started_mono, self.started_wall = self._clock(), self._wall()
        self.first_started_wall = self.first_started_wall or self.started_wall
        self._last_bytes, self.stalled_checks, self.voice_mismatches, self.voice_gap = 0, 0, 0, False
        self.cam2_checks = 0
        while not self._replies.empty():
            self._replies.get_nowait()
        self.meter = OutputMeter(cfg.segment_seconds, prefix, self.fps_history)
        self.watchdog_action = "grace"
        self._restart.clear()
        self._restart_reason = None
        self._write_pid(proc.pid)
        self.event("ffmpeg_started", pid=proc.pid, run=prefix, voice=voice, game=self.game_source, note=note,
                   cam2=cam2, layout=target, layout_switch=cfg.layout_switch, encoder=self.encoder, fps=cfg.fps,
                   desktop_fps=cfg.desktop_fps, hls=cfg.hls_dir is not None, rtmp=bool(cfg.rtmp_url))
        drain = asyncio.ensure_future(asyncio.gather(self._drain(proc), self._read_progress(proc, self.meter)))
        waiter = asyncio.ensure_future(proc.wait())
        restarter = asyncio.ensure_future(self._restart.wait())
        stopper = asyncio.ensure_future(self._stop_event.wait())
        await asyncio.wait({waiter, restarter, stopper}, return_when=asyncio.FIRST_COMPLETED)
        requested = None
        if not waiter.done():
            requested = "stop" if self._stopping else (self._restart_reason or "restart requested")
            await self._terminate(proc)
        code = await waiter
        for task in (restarter, stopper):
            task.cancel()
        try:
            await asyncio.wait_for(drain, 5)
        except Exception:
            drain.cancel()
        for record in self.meter.finish():
            self.event("segment_fps", run=prefix, **record)
        stdin = getattr(proc, "stdin", None)
        if stdin is not None:
            try:
                stdin.close()
            except Exception:
                pass
        uptime = self._clock() - self.started_mono
        self.proc = None
        self._remove_pid()
        self.watchdog_action = "down"
        if requested:
            self.event("ffmpeg_stopped", run=prefix, reason=requested, code=code)
            if requested != "stop":
                self.last_restart_reason = requested
                self._failures = 0
            return "stop" if requested == "stop" else "restart"
        tail = " | ".join(list(self._tail)[-3:])
        self.last_error = f"ffmpeg exited with code {code} after {uptime:.0f}s: {tail}"[:600]
        self.event("ffmpeg_exited", run=prefix, code=code, uptime_s=round(uptime, 1), tail=tail[:400])
        self._failures = 1 if uptime >= self.STABLE_SECONDS else self._failures + 1
        return "crash"

    def stderr_line(self, text):
        """One line of ffmpeg's stderr: command replies go to the switcher, the rest (redacted) to log and tail."""
        text = redact(text, self._secrets)
        reply = REPLY_RE.search(text)
        if reply:
            self._replies.put_nowait(int(reply.group(1)))
            return
        if not text or text.startswith("Enter command:") or text in ("<>", "<", ">"):
            return
        self._tail.append(text)
        if self._printed < 200:
            self._printed += 1
            print("ffmpeg:", text, flush=True)

    async def _drain(self, proc):
        stream = getattr(proc, "stderr", None)
        while stream is not None:
            line = await stream.readline()
            if not line:
                return
            self.stderr_line(line.decode("utf-8", "replace").rstrip())

    async def _read_progress(self, proc, meter):
        """ffmpeg's -progress output (stdout); always read, so a full pipe can never block ffmpeg."""
        stream = getattr(proc, "stdout", None)
        while stream is not None:
            line = await stream.readline()
            if not line:
                return
            for record in meter.feed(line.decode("utf-8", "replace"), self._clock()):
                self.event("segment_fps", run=meter.prefix, **record)

    async def _terminate(self, proc, grace=8.0):
        """SIGINT lets ffmpeg write the last fragment and close the segment; SIGKILL if it hangs."""
        if proc.returncode is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), grace)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()

    # -- ffmpeg pid file (lets a new director clean up after a SIGKILLed one)
    @property
    def pid_file(self):
        return self.cfg.streamer_dir / "pids" / "director-ffmpeg.pid"

    def _write_pid(self, pid):
        try:
            self.pid_file.write_text(str(pid))
        except OSError:
            pass

    def _remove_pid(self):
        try:
            self.pid_file.unlink()
        except OSError:
            pass

    async def reap_stale_ffmpeg(self):
        pid = read_pid(self.pid_file)
        if not pid:
            return
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            cmdline = ""
        if ("x11grab" in cmdline or "testsrc2" in cmdline) and str(self.cfg.recordings_dir) in cmdline:
            self.event("stale_ffmpeg", pid=pid)
            for sig in (signal.SIGINT, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                except OSError:
                    break
                for _ in range(10):
                    await self._sleep(0.5)
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        break
                else:
                    continue
                break
        self._remove_pid()


# -------------------------------------------------------------------- http

async def read_json(request):
    if request.content_length is not None and request.content_length > MAX_BODY:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY, actual_size=request.content_length)
    raw = await request.content.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY, actual_size=len(raw))
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Expected object")
    return data


def layout_plan(director, name):
    """-> (live, note): how a request for `name` will reach the recording."""
    cfg = director.cfg
    if cfg.layout is not None:
        return False, f"the layout is fixed by --layout {cfg.layout}; the request is only logged"
    cam2 = bool(director.cam2)
    if effective_layout(name, cam2) != name:
        if director.cam2_now:
            return False, f"{name} needs cam2: ffmpeg is relaunched with it"
        return False, f"{name} needs cam2, which is not available: {DEFAULT_LAYOUT} is shown"
    if cfg.layout_switch == "live":
        return True, "switched live (streamselect)"
    return False, "ffmpeg is relaunched with this layout (--layout-switch restart)"


def create_app(director, token):
    if not isinstance(token, str) or len(token) < MIN_TOKEN:
        raise ValueError("An operator credential of at least 12 characters is required")
    secret = token.encode()
    no_store = {"Cache-Control": "no-store"}

    @web.middleware
    async def guard(request, handler):
        if request.remote not in LOOPBACK:
            raise web.HTTPForbidden(text="Loopback only")
        if request.path != "/healthz" and not hmac.compare_digest(request.headers.get("X-Admin-Token", "").encode(), secret):
            raise web.HTTPForbidden(text="Operator authentication required")
        return await handler(request)

    async def healthz(request):
        return web.json_response({"ok": True, "recording": director.alive}, headers=no_store)

    async def state(request):
        return web.json_response(director.state(), headers=no_store)

    async def layout(request):
        data = await read_json(request)
        try:
            name = validate_layout(data.get("layout"))
        except ValueError as exc:
            raise web.HTTPBadRequest(text=str(exc))
        try:
            record = director.set_layout(data.get("layout"))
        except OSError as exc:
            raise web.HTTPInternalServerError(text=f"cannot write layout.jsonl: {exc.strerror}")
        live, note = layout_plan(director, name)
        director.kick_layout()
        return web.json_response({"ok": True, "layout": name, "live_layout": director.live_layout if director.alive else None,
                                  "live": live, "logged": record, "note": note}, headers=no_store)

    app = web.Application(middlewares=[guard], client_max_size=MAX_BODY)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/director/state", state)
    app.router.add_post("/director/layout", layout)
    return app


def load_token(token_file):
    if token_file:
        return Path(token_file).read_text().strip()
    return os.environ.get("SUB01_ADMIN_TOKEN", "").strip()


async def serve(cfg, host, port, token):
    director = Director(cfg)
    runner = web.AppRunner(create_app(director, token), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    print(f"SUB-01 director on http://{host}:{port} (recordings in {cfg.recordings_dir})", flush=True)
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, name), director.stop)
        except (NotImplementedError, AttributeError):
            pass
    try:
        await director.run()
    finally:
        await runner.cleanup()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--streamer-dir", default=os.environ.get("STREAMER_DIR", DEFAULT_STREAMER_DIR))
    p.add_argument("--token-file", help="file holding the operator credential (else SUB01_ADMIN_TOKEN)")
    p.add_argument("--recordings-dir", help="default <streamer-dir>/recordings")
    p.add_argument("--voice-fifo", help="default <streamer-dir>/voice.pcm")
    p.add_argument("--ffmpeg", default="ffmpeg")
    p.add_argument("--xdotool", default="xdotool")
    p.add_argument("--game-display", default=":99.0")
    p.add_argument("--desktop-display", default=":102.0")
    p.add_argument("--window-prefix", default="Sub01HomeLab", help="game window name starts with this")
    p.add_argument("--window-id", type=lambda v: int(v, 0), help="skip the xdotool lookup (decimal or 0x hex)")
    p.add_argument("--game-pid", type=int, help="search the game window by this pid")
    p.add_argument("--game-pid-file", help="file holding the game pid")
    p.add_argument("--size", default="1920x1080")
    p.add_argument("--pip-size", default="480x270")
    p.add_argument("--fps", type=int, default=24, help=f"game capture and output rate, 10-{MAX_FPS}")
    p.add_argument("--desktop-fps", type=int, default=15, help=f"10-{MAX_DESKTOP_FPS}, at most --fps")
    p.add_argument("--segment-seconds", type=int, default=600)
    p.add_argument("--crf", type=int, default=23, help="x264 crf, or NVENC -cq")
    p.add_argument("--preset", default="veryfast", help="x264 preset (NVENC always uses p4)")
    p.add_argument("--encoder", default="libx264", choices=ENCODERS,
                   help="NVENC is probed once at start; libx264 when the probe fails")
    p.add_argument("--audio-bitrate", default="96k")
    p.add_argument("--layout", help="fix the layout (webcam, desktop, split, room); default: follow layout.jsonl")
    p.add_argument("--layout-switch", default="live", choices=SWITCH_MODES,
                   help="live: streamselect through ffmpeg's stdin; restart: relaunch ffmpeg at every switch")
    p.add_argument("--switch-timeout", type=float, default=3.0, help="seconds to wait for ffmpeg's command reply")
    p.add_argument("--cam2-fifo", help="default <streamer-dir>/cam2.mjpeg")
    p.add_argument("--cam2-json", help="default <streamer-dir>/cam2.json")
    p.add_argument("--cam2-stale", type=float, default=3.0, help="cam2 unusable when its last frame is older")
    p.add_argument("--cam2-interval", type=float, default=1.0, help="seconds between cam2 checks")
    p.add_argument("--layout-interval", type=float, default=1.0, help="seconds between layout.jsonl reads")
    p.add_argument("--hls-dir", help="also write <dir>/live.m3u8 + 4 s segments from the same encode (tee)")
    rtmp = p.add_mutually_exclusive_group()
    rtmp.add_argument("--rtmp-url-file", help="file holding an rtmp(s):// URL: a third tee branch, never logged")
    rtmp.add_argument("--rtmp-url", help="as --rtmp-url-file, but the supervisor logs child command lines: prefer the file")
    p.add_argument("--test-sources", action="store_true", help="lavfi testsrc2/sine instead of X, FIFOs and cam2")
    p.add_argument("--test-seconds", type=float, default=0, help="stop each ffmpeg run after this many seconds")
    p.add_argument("--watchdog-interval", type=float, default=30.0)
    p.add_argument("--voice-interval", type=float, default=15.0)
    p.add_argument("--print-argv", action="store_true", help="resolve the window and voice, print the ffmpeg command, exit")
    args = p.parse_args(argv)
    if args.host not in LOOPBACK:
        p.error("the director binds only to loopback")
    rtmp_url = args.rtmp_url
    if args.rtmp_url_file:
        try:
            rtmp_url = Path(args.rtmp_url_file).read_text().strip()
        except OSError as exc:
            p.error(f"cannot read --rtmp-url-file: {exc.strerror}")
    try:
        width, height = (int(v) for v in args.size.lower().split("x"))
        pip_width, pip_height = (int(v) for v in args.pip_size.lower().split("x"))
        cfg = DirectorConfig(
            streamer_dir=Path(args.streamer_dir), recordings_dir=args.recordings_dir, voice_fifo=args.voice_fifo,
            ffmpeg=args.ffmpeg, xdotool=args.xdotool, game_display=args.game_display,
            desktop_display=args.desktop_display, window_prefix=args.window_prefix, window_id=args.window_id,
            game_pid=args.game_pid, game_pid_file=Path(args.game_pid_file) if args.game_pid_file else None,
            width=width, height=height, pip_width=pip_width, pip_height=pip_height, fps=args.fps,
            desktop_fps=args.desktop_fps, segment_seconds=args.segment_seconds, crf=args.crf, preset=args.preset,
            audio_bitrate=args.audio_bitrate, watchdog_interval=args.watchdog_interval,
            voice_interval=args.voice_interval, encoder=args.encoder, layout=args.layout,
            layout_switch=args.layout_switch, switch_timeout=args.switch_timeout, cam2_fifo=args.cam2_fifo,
            cam2_json=args.cam2_json, cam2_stale=args.cam2_stale, cam2_interval=args.cam2_interval,
            layout_interval=args.layout_interval, hls_dir=args.hls_dir, rtmp_url=rtmp_url or None,
            test_sources=args.test_sources, test_seconds=args.test_seconds)
    except ValueError as exc:
        p.error(str(exc))
    return args, cfg


def main(argv=None):
    args, cfg = parse_args(argv)
    if args.print_argv:
        if cfg.test_sources:
            window, note, voice, reason, cam2, cam2_reason, cam2_fps = (
                None, "test sources", True, "test source", True, "test source", cfg.fps)
        else:
            window, note = find_game_window(cfg)
            tap = VoiceTap(cfg.voice_fifo, create=False)
            voice, reason = tap.writer_present()
            tap.close()
            cam2_tap = FifoTap(cfg.cam2_fifo, create=False, what="cam2")
            cam2, cam2_reason, cam2_fps = cam2_status(cfg, cam2_tap, time.time())
            cam2_tap.close()
        encoder, encoder_note = cfg.encoder, "requested"
        if cfg.encoder != "libx264":
            ok, encoder_note = probe_encoder(cfg, cfg.encoder)
            encoder = cfg.encoder if ok else "libx264"
        layout = effective_layout(cfg.layout or read_last_layout(cfg.streamer_dir / "layout.jsonl") or DEFAULT_LAYOUT, cam2)
        command = build_ffmpeg_argv(cfg, prefix="sub01-YYYYmmdd-HHMMSS", window_id=window, voice=voice, cam2=cam2,
                                    layout=layout, live=cfg.layout_switch == "live", encoder=encoder, cam2_fps=cam2_fps)
        print(f"# window: {window} ({note}); voice: {voice} ({reason}); cam2: {cam2} ({cam2_reason}); "
              f"encoder: {encoder} ({encoder_note}); layout: {layout} ({cfg.layout_switch} switching)")
        print(redact(shlex.join(command), secret_parts(cfg.rtmp_url)))
        return 0
    token = load_token(args.token_file)
    if len(token) < MIN_TOKEN:
        print("set SUB01_ADMIN_TOKEN or --token-file (at least 12 characters)", file=sys.stderr)
        return 2
    cfg.streamer_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        asyncio.run(serve(cfg, args.host, args.port, token))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
