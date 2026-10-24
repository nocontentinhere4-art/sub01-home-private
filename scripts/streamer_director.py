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
  `--test-sources` replaces all of them with lavfi sources (local smoke tests: no X server, FIFO or game): testsrc2
  for the game and cam2, a solid red picture for the desktop (any desktop pixel is recognisable in the output), a sine.

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

Main view source (`--game-source x11|fifo`, explicit, never inferred from a missing file; x11 is the default). x11:
input 0 is the x11grab of the game window above. fifo (the game renders offscreen, docs/streamer/SAWTOOTH-20261024.md
"Structural fix"): input 0 is `<streamer-dir>/main.mjpeg`, a FIFO the game creates and writes whole 1920x1080 JPEGs
into (full range like cam2, each with a `seq=<n>` COM segment), read like cam2 (wallclock timestamps, `tpad` clone after
an EOF, full -> limited range); `main.json` (written by the game once a second) has `written`, `last_write_utc` and the
drop counters. `MainSource` decides every --main-interval s: the FIFO is stale when nobody writes it, main.json is older
than --main-stale s or its `last_write_utc` is; a stale FIFO (or a FIFO run that ffmpeg left within 60 s) relaunches
ffmpeg with input 0 = a lavfi placeholder card (SMPTE bars: visible, never a black grab), and the FIFO is tried again
after a backoff of 2, 4, 8, 16, 30 s once main.json has been fresh for --main-fresh s (events `main_changed`). Only
input 0 differs, so every layout, the privacy cut, retention and the speed guard behave the same in both modes.
Unique main-view frames: a FIFO run has a second ffmpeg output, a stream copy of input 0 as multipart JPEG behind
ffmpeg's dropping `fifo` muxer on a pipe (`SeqTap`); the director reads each part's `seq=` and counts frames, new
sequences, repeats and gaps. ffmpeg stays the FIFO's only reader, and a tap that fails or stalls never stops the
recording. The -progress dup/drop counters cannot see this: the graph's `fps` filters repeat missing source frames
before the encoder. State `main` and the `segment_fps` rows of FIFO runs carry the counts (`main_fps` = new sequences
per wall second) and main.json's `written` per window (`game_fps`).

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
desktop side by side), `room` (cam2 full frame, webcam PiP; without cam2 `webcam` is shown), `webcam_only` (the game
viewport alone: no picture of the desktop anywhere). The wanted layout is the last line of `<streamer-dir>/layout.jsonl`
(written by `POST /director/layout` or by the agent directly; read every --layout-interval s), or fixed with
`--layout`. Every line the director writes has `t`, `unix`, `layout`, `previous`, `run`, `offset_s`, `recording`.

Privacy cut (owner, 2026-10-23: SUB-01 may log in on his PC). While the last line of layout.jsonl has
`"reason": "privacy"` (the agent's line on a login/account page, with its `privacy_id`), the output shows `webcam_only`
whatever else is wanted, a fixed --layout included: every other layout carries the desktop (the PiP, or cam2 in `room`,
which films the in-game monitor). The recording, HLS and RTMP are one encode, so all three are covered. The cut ends
with a later valid line without that reason (the agent's `privacy_end`, which names the layout to restore; an invalid
layout there restores the one requested before the cut). `GET /director/state` has `privacy`, `privacy_id`,
`desktop_hidden` and the restore (`privacy_restore`, `last_privacy`); `desktop_hidden` is true only while the cut is in
force and the running ffmpeg is confirmed on `webcam_only`: ffmpeg answered ret:0 to that map command, or the run was
launched on it (restart mode, a relaunch, a director restart: the log is read before the first launch); false while a
switch is in flight, after an unanswered or failed one, while a relaunch is pending or when nothing runs. The agent types
a credential only when that answer carries its own `privacy_id`. During a cut `POST /director/layout` answers 409 (no
line is written) unless the body has `"end_privacy": true`, which ends the cut (`reason: "privacy_end_operator"`); the
handler reads layout.jsonl first, so the agent's end line followed at once by its POST is accepted; a privacy line that
lands between that read and the POST's own line is appended again on top (and the POST gets 409). A director restarted
during a cut restores the last request before it (or the privacy line's `previous`). A cut never ends on a timer
(`privacy_still_on` every 10 minutes instead), and nothing is acknowledged while an ffmpeg of an earlier director
(found in /proc at start) survived its reap. `desktop_hidden` means safe to type from now on, not that frames composed before the switch
(encoder lookahead, the open HLS segment, RTMP already sent) are gone. Events: `privacy_on`, `privacy_hidden` (ms from
reading the line), `privacy_off`, `privacy_restored`, `privacy_still_on`.

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
                              restarts, last_error, layout, live_layout, encoder, cam2, hls, voice,
                              privacy, privacy_id, desktop_hidden, privacy_restore, last_privacy, ...}
  POST /director/layout   {"layout": "webcam"|"desktop"|"split"|"room"|"webcam_only"|"character", "end_privacy"?: bool}

ffmpeg is restarted on exit with backoff; a watchdog compares the size of the
current run's segments every 30 s and restarts ffmpeg after two checks without
growth; a second check (every 15 s) relaunches ffmpeg when the voice server attached after a
silent start, or came back after a drop (the run's audio input hit EOF; until then `apad` records silence).
The helpers below are pure and importable without ffmpeg.
"""

import argparse
import asyncio
import fcntl
import hmac
import json
import math
import os
import re
import shlex
import shutil
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
GAME_SOURCES = ("x11", "fifo")
PLACEHOLDER = "placeholder"                 # the fifo mode's stand-in for input 0 while the FIFO is stale
PLACEHOLDER_CARD = "smptehdbars"            # lavfi, no font needed (a drawtext without a font would fail every launch)
MAIN_BACKOFF = (2.0, 4.0, 8.0, 16.0, 30.0)  # seconds before the FIFO is tried again after the 1st, 2nd, ... failure
MAIN_STABLE = 60.0          # a FIFO run fresh this long clears the failures; one that ends sooner counts as one
MAIN_DRAIN = 8 << 20        # bytes the director drains per 0.1 s tick while ffmpeg does not read main.mjpeg (1080p60)
MAIN_LAUNCH_GRACE = 3.0     # a FIFO run's first seconds: an old main.json / last write / missing writer is not acted on
MAIN_WRITER_CONFIRM = 0.6   # "no writer" is confirmed by a second /proc scan this much later (a game reopening its fd)
MAIN_STOP_NUDGE = (1.0, 2.0)   # stale FIFO run: second SIGINT after 1 s, SIGKILL after 2 s (normal relaunch: 4 s, 8 s)
TAP_QUEUE = "60"            # packets the tap's fifo muxer holds (~1 s, refcounted) before it drops instead of blocking
SEQ_HEAD = 4096             # bytes of each tapped JPEG kept to find its COM segment (JFIF, DQT, SOF, DHT come first)
SEQ_MAX_PART = 32 << 20     # a tapped part announcing more than this is a broken header, not a frame
SEQ_RESET = 600             # a sequence this far below the highest seen is the writer counting from 0 again
TAP_OVERFLOW = "FIFO queue full"    # ffmpeg's fifo muxer, once per overflow (it then flushes its queue: frames lost)

# ---------------------------------------------------------------- layouts

DEFAULT_LAYOUT = "webcam"
PRIVATE_LAYOUT = "webcam_only"
PRIVACY_REASON = "privacy"
PIP_MARGIN = 24
# `desktop`: the layout shows a picture of the desktop somewhere (room too: cam 2 sees the in-game monitor, which shows it)
LAYOUTS = {
    "webcam": {"main": "game", "pip": "desktop", "needs_cam2": False, "desktop": True,
               "summary": "game viewport (frontal webcam) full frame, desktop picture-in-picture bottom-right"},
    "desktop": {"main": "desktop", "pip": "game", "needs_cam2": False, "desktop": True,
                "summary": "desktop full frame, webcam picture-in-picture bottom-right"},
    "split": {"main": None, "pip": None, "needs_cam2": False, "desktop": True,
              "summary": "webcam and desktop side by side, each half width"},
    "room": {"main": "cam2", "pip": "game", "needs_cam2": True, "desktop": True,
             "summary": "second camera (room) full frame, webcam picture-in-picture bottom-right"},
    "webcam_only": {"main": "game", "pip": None, "needs_cam2": False, "desktop": False,
                    "summary": "game viewport (frontal webcam) full frame, no picture-in-picture: no desktop at all"},
}
LAYOUT_ALIASES = {"character": "webcam"}           # the v1 name, still sent by the agent
LIVE_ORDER = ("webcam", "desktop", "split", "room", "webcam_only")  # input index of each layout at streamselect@layout
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


def privacy_cut(record):
    """The privacy cut a layout.jsonl record asks for, or None: {"id", "why"} when its `reason` is "privacy" (the
    agent's line on a login/account page). The record's `layout` does not matter: a privacy line always means
    PRIVATE_LAYOUT, even with a missing or unknown layout name (fail closed)."""
    if not isinstance(record, dict) or record.get("reason") != PRIVACY_REASON:
        return None
    pid, why = record.get("privacy_id"), record.get("why")
    return {"id": pid if isinstance(pid, str) and 0 < len(pid) <= 64 else None,
            "why": why[:120] if isinstance(why, str) else None}


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
    keep_segments: int = 18                # retention: at most this many recording segments (3 h at 10 min); 0 = no cap
    min_free_gb: float = 3.0               # retention: delete the oldest finished segments while the disk has less free
    game_source: str = "x11"               # x11: x11grab of the game window; fifo: the offscreen game's main.mjpeg
    main_fifo: Path = None
    main_json: Path = None
    main_stale: float = 2.0                # fifo mode: main.json or its last_write_utc older than this = stale
    main_fresh: float = 3.0                # fifo mode: main.json fresh this long before the FIFO is tried again
    main_interval: float = 1.0             # fifo mode: seconds between staleness checks
    main_tap: bool = True                  # fifo mode: count the main view's frames by their seq= markers

    def __post_init__(self):
        base = Path(self.streamer_dir)
        object.__setattr__(self, "streamer_dir", base)
        object.__setattr__(self, "recordings_dir", Path(self.recordings_dir) if self.recordings_dir else base / "recordings")
        object.__setattr__(self, "voice_fifo", Path(self.voice_fifo) if self.voice_fifo else base / "voice.pcm")
        object.__setattr__(self, "cam2_fifo", Path(self.cam2_fifo) if self.cam2_fifo else base / "cam2.mjpeg")
        object.__setattr__(self, "cam2_json", Path(self.cam2_json) if self.cam2_json else base / "cam2.json")
        object.__setattr__(self, "main_fifo", Path(self.main_fifo) if self.main_fifo else base / "main.mjpeg")
        object.__setattr__(self, "main_json", Path(self.main_json) if self.main_json else base / "main.json")
        if self.game_source not in GAME_SOURCES:
            raise ValueError("game source must be x11 or fifo")
        if not all(math.isfinite(v) and v > 0 for v in (self.main_stale, self.main_fresh, self.main_interval)):
            raise ValueError("main view intervals must be positive")
        if not 10 <= self.desktop_fps <= MAX_DESKTOP_FPS:
            raise ValueError(f"desktop fps must be between 10 and {MAX_DESKTOP_FPS}")
        if not 10 <= self.fps <= MAX_FPS:
            raise ValueError(f"fps must be between 10 and {MAX_FPS}")
        if self.desktop_fps > self.fps:
            raise ValueError(f"desktop fps must not be above fps ({self.fps})")
        if self.segment_seconds < 10:
            raise ValueError("segment length must be at least 10 seconds")
        if self.keep_segments < 0 or not math.isfinite(self.min_free_gb) or self.min_free_gb < 0:
            raise ValueError("keep segments and min free GB must be finite and not negative")
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


def game_rate(cfg, main=None):
    """The `fps` step of input 0. The fifo mode's main view (`main` "fifo") also repeats its last frame after an EOF
    (`tpad`, as cam2); the x11 grab and the placeholder card keep today's chain."""
    return f"fps={cfg.fps}" + (",tpad=stop=-1:stop_mode=clone" if main == "fifo" else "")


def game_scale(size, flags=None, main=None):
    """The `scale` step of input 0: the FIFO's JPEGs are full range (yuvj), converted explicitly like cam2's."""
    return (f"scale={size}" + (f":flags={flags}" if flags else "")
            + (":in_range=full:out_range=limited" if main == "fifo" else ""))


def build_filter_complex(layout, cfg, main=None):
    """ffmpeg filter graph for ONE layout (restart switching, post passes).
    Inputs: [0:v] game, [1:v] desktop, [3:v] cam2 (room only). Output label [vout]. `main` "fifo" = input 0 is the
    offscreen game's main.mjpeg (see game_rate / game_scale); anything else = today's chain."""
    layout = validate_layout(layout)
    w, h, pw, ph, fps = cfg.width, cfg.height, cfg.pip_width, cfg.pip_height, cfg.fps
    rate = game_rate(cfg, main)
    if layout == PRIVATE_LAYOUT:              # the game alone: [1:v] (desktop) and [3:v] are not in the graph at all
        return f"[0:v]{rate},{game_scale(f'{w}:{h}', main=main)},setsar=1,format=yuv420p[vout]"
    if layout == "split":
        half_w = (w // 2) & ~1
        half_h = (half_w * h // w) & ~1
        return (f"[0:v]{rate},{game_scale(f'{half_w}:{half_h}', 'area', main)},setsar=1[l];"
                f"[1:v]fps={fps},scale={half_w}:{half_h}:flags=area,setsar=1[r];"
                f"[l][r]hstack=inputs=2,pad={w}:{h}:0:(oh-ih)/2:black,format=yuv420p[vout]")
    spec = LAYOUTS[layout]
    main_src, pip_src = SOURCES[spec["main"]], SOURCES[spec["pip"]]
    if spec["main"] == "game":
        top = f"[{main_src}]{rate},{game_scale(f'{w}:{h}', main=main)},setsar=1[main];"
    else:                                   # slower sources: scale at their own rate, then repeat frames up to fps
        if spec["main"] == "cam2":
            top = f"[{main_src}]{cam2_scale(cfg)},setsar=1,fps={fps},tpad=stop=-1:stop_mode=clone[main];"
        else:
            top = f"[{main_src}]scale={w}:{h},setsar=1,fps={fps}[main];"
    pip = f"scale={pw}:{ph}:flags=area"
    if spec["pip"] == "game":                # the FIFO main view as the PiP: its rate and EOF chain too (Kimi review)
        pip = (f"{rate}," if main == "fifo" else "") + game_scale(f"{pw}:{ph}", "area", main)
    return (top + f"[{pip_src}]{pip},setsar=1[pip];"
            f"[main][pip]overlay=x=W-w-{PIP_MARGIN}:y=H-h-{PIP_MARGIN}:eof_action=pass,format=yuv420p[vout]")


def build_live_graph(cfg, cam2, layout, main=None):
    """Every layout of the run in one graph; `streamselect@layout` (inputs in live_order(cam2)) picks the recorded one.
    Every streamselect input has the same size, format, rate and SAR, so a `map` command only changes the index and
    one command switches atomically (no frame of a half-switched composite)."""
    w, h, pw, ph, fps = cfg.width, cfg.height, cfg.pip_width, cfg.pip_height, cfg.fps
    half_w = (w // 2) & ~1
    half_h = (half_w * h // w) & ~1
    norm = f"scale={w}:{h},setsar=1,format=yuv420p"
    pip = f"scale={pw}:{ph}:flags=area,setsar=1"
    order = live_order(cam2)
    # [lwebcam_only] is the game picture itself: the privacy layout, no PiP (every other layout carries the desktop)
    parts = [f"[0:v]{game_rate(cfg, main)},{game_scale(f'{w}:{h}', main=main)},setsar=1,format=yuv420p,"
             f"split=4[gm][gp][gh][l{PRIVATE_LAYOUT}]",
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


def main_input_args(cfg, main):
    """Input 0 of the fifo mode: the offscreen game's main.mjpeg (read like cam2: arrival wallclock as timestamps,
    a small probe so a launch is quick), or the placeholder card while the FIFO is stale.

    `-follow 1` (the file protocol: a read of 0 bytes is retried instead of ending the input) is the one addition to
    the spec's options (Kimi, docs/streamer/kimi/director-fifo-design.md): the game closes and reopens the FIFO after
    a frame missed its write deadline, and without it the first close is an EOF that ends input 0 for the whole run
    (tpad then repeats one frame until the staleness check relaunches). With it a writer gap is seamless, and a writer
    gone for good stalls the graph until main.json goes stale (as a stalled cam2 does)."""
    if main == "fifo":
        return ["-thread_queue_size", "512", "-use_wallclock_as_timestamps", "1", "-probesize", "2000000",
                "-analyzeduration", "1000000", "-f", "mjpeg", "-framerate", str(cfg.fps), "-follow", "1",
                "-i", str(cfg.main_fifo)]
    return ["-re", "-f", "lavfi", "-i", f"{PLACEHOLDER_CARD}=size={cfg.width}x{cfg.height}:rate={cfg.fps}"]


def tap_output_args(cfg, tap_fd):
    """A second output: input 0 (main.mjpeg) stream-copied as multipart JPEG to the director's pipe `tap_fd`, behind
    ffmpeg's `fifo` muxer, which drops packets instead of blocking when the director does not read (a stalled or
    closed tap ends only this output; the recording goes on). It is not the first video output, so -progress still
    reports the recording."""
    limit = ["-t", f"{cfg.test_seconds:g}"] if cfg.test_seconds else []
    return ["-map", "0:v", "-c:v", "copy", *limit, "-f", "fifo", "-fifo_format", "mpjpeg",
            "-drop_pkts_on_overflow", "1", "-attempt_recovery", "0", "-queue_size", TAP_QUEUE, f"pipe:{int(tap_fd)}"]


def build_ffmpeg_argv(cfg, *, prefix, window_id=None, voice=True, cam2=False, layout=None, live=False,
                      encoder=None, cam2_fps=None, main=None, tap_fd=None):
    """The one ffmpeg command line. `window_id` None captures the whole of :99.0 instead.

    `live` renders every layout and keeps ffmpeg's stdin command channel open (`-stdin`) for streamselect switches;
    otherwise the graph is the one `layout` and stdin is off (`-nostdin`), as in v1. `main` (fifo mode only) is
    "fifo" (input 0 = main.mjpeg; with `tap_fd`, the seq tap output too) or "placeholder" (input 0 = the card); None
    is the x11 mode, exactly as before."""
    size = f"{cfg.width}x{cfg.height}"
    layout = effective_layout(layout or DEFAULT_LAYOUT, cam2)
    main = main if main in ("fifo", PLACEHOLDER) else None
    argv = [cfg.ffmpeg, "-hide_banner", "-stdin" if live else "-nostdin", "-loglevel", "warning",
            # key=value blocks on stdout (frame, fps, out_time_us, dup/drop, speed): the measured output rate
            "-progress", "pipe:1", "-stats_period", f"{cfg.stats_period:g}"]
    if cfg.test_sources:
        voice = True                         # the desktop is solid red: any desktop pixel is recognisable in a test recording
        argv += main_input_args(cfg, main) if main else ["-re", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={cfg.fps}"]
        argv += ["-re", "-f", "lavfi", "-i", f"color=c=red:size={size}:rate={cfg.desktop_fps}",
                 "-re", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    else:
        if main:
            argv += main_input_args(cfg, main)
        else:
            argv += ["-thread_queue_size", GRAB_QUEUE, "-f", "x11grab", "-framerate", str(cfg.fps), "-draw_mouse", "0"]
            argv += ["-window_id", str(int(window_id))] if window_id else ["-video_size", size]
            argv += ["-i", cfg.game_display]
        argv += ["-thread_queue_size", GRAB_QUEUE, "-f", "x11grab", "-framerate", str(cfg.desktop_fps),
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
    graph = build_live_graph(cfg, cam2, layout, main) if live else build_filter_complex(layout, cfg, main)
    if voice:
        # apad: if the voice server goes away the FIFO hits EOF; silence keeps the audio track running meanwhile
        graph += ";[2:a]apad[aout]"
    argv += ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]" if voice else "2:a",
             *video_codec_args(cfg, encoder or cfg.encoder), "-max_muxing_queue_size", "1024",
             "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-ar", "48000", "-ac", "2"]
    if cfg.test_seconds:
        argv += ["-t", f"{cfg.test_seconds:g}"]
    argv += output_args(cfg, prefix)
    if main == "fifo" and tap_fd is not None:
        argv += tap_output_args(cfg, tap_fd)
    return argv


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


def retention_victims(segments, current_prefix, keep, free_bytes, min_free_bytes):
    """Names of recording segments to delete, oldest first. The newest segment of the running ffmpeg (still being
    written) is never chosen. Two rules: at most `keep` segments in total (0 = no cap), and while the disk has less than
    `min_free_bytes` free, the oldest finished segments go one by one until enough would be free (2026-10-24: an
    overnight recording filled the root disk and took every service down)."""
    current = [s for s in segments if s["run"] == current_prefix]
    writing = max(current, key=lambda s: s["index"])["name"] if current else None
    candidates = [s for s in segments if s["name"] != writing]          # oldest first (list_segments order)
    victims = []
    if keep and len(segments) > keep:
        victims = [s["name"] for s in candidates[:len(segments) - keep]]
    freed = sum(s["bytes"] for s in candidates if s["name"] in victims)
    for s in candidates:
        if free_bytes + freed >= min_free_bytes:
            break
        if s["name"] not in victims:
            victims.append(s["name"])
            freed += s["bytes"]
    return victims


def apply_retention(cfg, prefix, events=None):
    """Delete the segments `retention_victims` names; returns the deleted names. Never raises. A segment that cannot be
    deleted is skipped and the selection runs again without it (Kimi review: one undeletable file must not stall the
    reclamation forever)."""
    try:
        free = shutil.disk_usage(cfg.recordings_dir).free
        min_free = int(cfg.min_free_gb * 1024 ** 3)
    except (OSError, ValueError, OverflowError):
        return []
    deleted, failed = [], set()
    try:
        for _ in range(3):                                 # first pass, then retries without the failed files
            segments = [s for s in list_segments(cfg.recordings_dir) if s["name"] not in failed]
            keep = max(1, cfg.keep_segments - len(failed)) if cfg.keep_segments else 0   # a stuck file still counts
            names = retention_victims(segments, prefix, keep, free, min_free)
            if not names:
                break
            stuck = False
            for name in names:
                try:
                    (Path(cfg.recordings_dir) / name).unlink()
                    deleted.append(name)
                except FileNotFoundError:
                    pass
                except OSError:
                    failed.add(name)
                    stuck = True
            free = shutil.disk_usage(cfg.recordings_dir).free
            if not stuck:                                  # everything selected went: the rules are met
                break
    except OSError:
        pass
    if (deleted or failed) and events is not None:
        try:
            events("retention", deleted=deleted, failed=sorted(failed), free_gb=round(free / 1024 ** 3, 2))
        except Exception:                                  # the event log must not take the watchdog down
            pass
    return deleted


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


SLOW_SPEED = 0.95          # output media seconds per wall second below which a check counts as slow
SLOW_LIMIT = 3             # slow checks in a row (3 x 30 s) before ffmpeg is relaunched
SLOW_RESTART_GAP = 600.0   # at most one relaunch for slowness per 10 minutes (no loop on a machine that cannot keep up)


def window_speed(prev, cur):
    """Output media time gained per wall second between two meter clocks `(wall_s, out_time_s)`; None if unknown.
    ffmpeg's own `speed=` is an average since the run started, so a run that fell behind at start (2026-10-24: the
    director launched while the voice model loaded ran at 0.70x for minutes) keeps a misleading figure."""
    if not prev or not cur or prev[1] is None or cur[1] is None or cur[0] <= prev[0]:
        return None
    return (cur[1] - prev[1]) / (cur[0] - prev[0])


def speed_decision(speed, slow_checks, *, uptime, since_restart, grace=WATCHDOG_GRACE, floor=SLOW_SPEED,
                   limit=SLOW_LIMIT, gap=SLOW_RESTART_GAP):
    """-> (action, slow_checks). action: grace | unknown | ok | slow | restart | held (slow, but a relaunch for
    slowness happened less than `gap` s ago). A live graph below real time queues its inputs and its latency grows
    without bound; a relaunch starts it fresh."""
    if uptime < grace:
        return "grace", 0
    if speed is None:
        return "unknown", 0          # a gap breaks the streak (Kimi review: only consecutive slow checks count)
    if speed >= floor:
        return "ok", 0
    slow_checks += 1
    if slow_checks < limit:
        return "slow", slow_checks
    return ("held" if since_restart is not None and since_restart < gap else "restart"), slow_checks


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


PRIVACY_ALERT_S = 600.0     # a privacy cut this long gets a `privacy_still_on` event (again every 10 minutes)
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
    distinct frames offline with mpdecimate (RUNBOOK).

    `main` (fifo mode only; x11 records stay as they were) is read at every block: a callable -> {"source": "fifo" |
    "placeholder", cumulative counts of the run (MAIN_FIELDS: tapped frames, new sequences, repeats, gaps, frames
    without a marker; main.json's written and drops, None when unknown), "gap_s": the longest time between two tapped
    frames since the previous call}. Windows then carry their deltas: `main_fps` = new sequences per wall second (the
    unique main-view frames that reached the director), `game_fps` = main.json written per wall second."""

    def __init__(self, segment_seconds, prefix=None, history=None, main=None):
        self.segment_seconds, self.prefix = segment_seconds, prefix
        self.history = history if history is not None else deque(maxlen=24)
        self.latest = None
        self._block, self._prev, self._seg, self._last = {}, None, None, None
        self.main = main
        self._main_prev = self._main_seg = self._main_last = None
        self._main_gap = 0.0                     # longest gap between tapped frames in the open window

    def _main_block(self, now):
        """Read the main-view counters at a block; -> the fields the live `latest` gets."""
        try:
            counts = dict(self.main())
        except Exception:                        # a broken counter never stops the meter
            return {}
        gap = float(counts.pop("gap_s", 0.0) or 0.0)
        prev, self._main_prev = self._main_prev, (now, counts)
        self._main_last = (now, counts)
        self._main_gap = max(self._main_gap, gap)
        out = {"main_source": counts.get("source"), "main_max_gap_ms": round(gap * 1000)}
        if prev is not None and now > prev[0]:
            out.update(main_window(prev[1], counts, now - prev[0]))
        return out

    def clock(self):
        """(wall clock of the last block, output time in s) or None: the input of `window_speed`."""
        return (self._last[0], self._last[2]) if self._last else None

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
        if self.main is not None:
            self.latest.update(self._main_block(now))
        self._last = (now, frame, out_s, dup, drop)
        index = int(out_s // self.segment_seconds) if out_s is not None else 0
        if self._seg is None:                    # the first block (ffmpeg prints one at start) is the baseline
            self._open_window(index, now, frame, out_s, dup, drop)
            return []
        records = []
        if index > self._seg[0]:                 # crossed into the next window (also on the end block)
            records.append(self._close(partial=False))
            self._open_window(index, now, frame, out_s, dup, drop)
        if value == "end":
            records += self.finish()
        return records

    def _open_window(self, index, now, frame, out_s, dup, drop):
        self._seg = (index, now, frame, out_s or 0.0, dup, drop)
        self._main_seg, self._main_gap = self._main_last, 0.0

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
        if self.main is not None and self._main_last is not None:
            start = self._main_seg[1] if self._main_seg is not None else {}
            record["main_source"] = self._main_last[1].get("source")
            record.update(main_window(start, self._main_last[1], wall))
            record["main_max_gap_ms"] = round(self._main_gap * 1000)
        self.history.append(record)
        return record


MAIN_FIELDS = ("frames", "unique", "repeated", "gaps", "noseq", "bad", "cut", "overflows")


def main_window(start, end, wall):
    """Deltas of the main-view counters between two snapshots over `wall` s: main_frames, main_unique, main_fps (new
    sequences per second), main_repeated, main_gaps, main_noseq, main_bad, main_cut (parts without EOI: discarded by
    the game mid-write, not unique), main_overflows; main_tap_ok (a FIFO window
    whose count can be trusted: no part without a sequence, no broken header, no tap overflow, no tap error; None on
    the placeholder); game_written, game_fps and game_dropped from main.json (None when either snapshot lacks them, or
    when the game's counters went backwards: a restarted game)."""
    out = {}
    for key in MAIN_FIELDS:
        a, b = start.get(key) or 0, end.get(key) or 0
        out[f"main_{key}"] = max(0, b - a)
    out["main_fps"] = round(out["main_unique"] / wall, 2) if wall > 0 else None
    out["main_tap_ok"] = (None if end.get("source") != "fifo" or "unique" not in end else
                          not (out["main_noseq"] or out["main_bad"] or out["main_overflows"] or end.get("tap_error")))
    a, b = start.get("game_written"), end.get("game_written")
    written = b - a if a is not None and b is not None and b >= a else None
    out["game_written"] = written
    out["game_fps"] = round(written / wall, 2) if written is not None and wall > 0 else None
    a, b = start.get("game_dropped"), end.get("game_dropped")
    out["game_dropped"] = b - a if a is not None and b is not None and b >= a else None
    return out


BACKOFF = (2, 4, 8, 16, 32, 60)


def backoff_delay(failures):
    """Seconds to wait after `failures` consecutive short-lived ffmpeg runs."""
    return 1.0 if failures <= 0 else float(BACKOFF[min(failures, len(BACKOFF)) - 1])


# ---------------------------------------------------------------- layout log

LAYOUT_TAIL = 65536          # bytes of layout.jsonl read from the end (a line is ~250 bytes)


def read_tail_records(path, max_bytes=LAYOUT_TAIL):
    """The last lines of layout.jsonl, oldest first: a dict per line, or None for a line that is not a JSON object (a
    half-written last line). A line cut by the read window is left out, never the last one. [] without a file."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            start = max(0, size - max_bytes - 1)        # one byte more: is the window's first line complete?
            handle.seek(start)
            data = handle.read()
    except OSError:
        return []
    if start > 0:
        cut = data.find(b"\n")
        data = data[cut + 1:] if cut >= 0 else b""      # up to the first newline: a piece of a longer line
    out = []
    for line in data.split(b"\n"):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            record = None
        out.append(record if isinstance(record, dict) else None)
    return out


def read_last_record(path, max_bytes=LAYOUT_TAIL):
    """The last line of layout.jsonl as a dict, or None (no file, a half-written or bad line: the current state stays)."""
    records = read_tail_records(path, max_bytes)
    return records[-1] if records else None


def read_last_layout(path, max_bytes=LAYOUT_TAIL):
    """The canonical layout the last line of layout.jsonl asks for (PRIVATE_LAYOUT for a privacy line), or None (no
    file, a half-written or bad line, an unknown name: the current layout stays)."""
    record = read_last_record(path, max_bytes)
    if record is None:
        return None
    if privacy_cut(record) is not None:
        return PRIVATE_LAYOUT
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


# -------------------------------------------- main view (fifo mode, the offscreen game)

MAIN_COUNTERS = ("written", "sequence", "dropped_slots", "dropped_encode", "dropped_queue", "dropped_noreader",
                 "frames_discarded_midwrite")
MAIN_DROPS = MAIN_COUNTERS[2:]


def _count(value):
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


def main_report(path, now):
    """main.json (the game's status of the main-view FIFO, renamed into place once a second) -> {age_s (from the file's
    mtime), last_write_age_s (None without a usable `last_write_utc`), fps, and the counters}, or None without it."""
    try:
        st = os.stat(path)
        raw = Path(path).read_bytes()[:65536]
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        data = None
    data = data if isinstance(data, dict) else {}
    last = parse_time(data.get("last_write_utc"))
    fps = data.get("fps")
    out = {"age_s": round(now - st.st_mtime, 3), "last_write_age_s": None if last is None else round(now - last, 3),
           "fps": float(fps) if isinstance(fps, (int, float)) and not isinstance(fps, bool) else None,
           "valid": bool(data)}
    out.update({key: _count(data.get(key)) for key in MAIN_COUNTERS})
    return out


def main_freshness(report, stale):
    """-> (fresh, reason) from main.json alone: the file and its last written frame both newer than `stale` s."""
    if report is None:
        return False, "no main.json next to the main FIFO"
    if not report["valid"]:
        return False, "main.json is not a JSON object"
    if report["age_s"] > stale:
        return False, f"main.json {report['age_s']:.1f}s old"
    if report["last_write_age_s"] is None:
        return False, "main.json has no last_write_utc"
    if report["last_write_age_s"] > stale:
        return False, f"main view last written {report['last_write_age_s']:.1f}s ago"
    return True, f"main view last written {max(report['last_write_age_s'], 0.0):.1f}s ago"


def main_status(cfg, tap, now, writer=True, confirm=MAIN_WRITER_CONFIRM, sleep=time.sleep):
    """-> (fresh, reason, report, hard). Fresh: main.mjpeg is a FIFO, main.json and its last_write_utc are newer than
    --main-stale s and (with `writer`) a process holds the FIFO open for writing. The director's own read end (`tap`)
    is (re)opened first, so the game's non-blocking writer can always attach. `hard`: the FIFO itself is missing or not
    a FIFO (acted on at once, also in a run's launch grace). A /proc scan that finds no writer is repeated `confirm` s
    later before it counts (the game closes and reopens its fd after a missed write deadline)."""
    ok, reason = tap.refresh()
    report = main_report(cfg.main_json, now)
    if not ok:
        return False, reason, report, True
    ok, reason = main_freshness(report, cfg.main_stale)
    if ok and writer:
        found, why = tap.writer_present(settle=0)
        if not found and confirm:
            sleep(confirm)
            found, why = tap.writer_present(settle=0)
        if not found:
            return False, why, report, False
        reason += ", writer present"
    return ok, reason, report, False


def jpeg_seq(head):
    """The `seq=<n>` of a JPEG's COM segment, from its first bytes (SOI, then marker segments up to SOS), or None."""
    head = bytes(head)
    if head[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(head):
        if head[i] != 0xFF:
            return None
        marker = head[i + 1]
        if marker == 0xFF:                                   # fill byte
            i += 1
            continue
        if marker in (0xDA, 0xD9):                           # start of scan / end of image: no COM before it
            return None
        length = int.from_bytes(head[i + 2:i + 4], "big")
        if length < 2:
            return None
        if marker == 0xFE:
            m = re.match(rb"seq=(\d{1,19})(?!\d)", head[i + 4:i + 2 + length])
            if m:
                return int(m.group(1))
        i += 2 + length
    return None


class SeqCounter:
    """Counts the main view's frames in ffmpeg's multipart-JPEG copy of main.mjpeg (`--ffmpeg` parts with a
    `Content-length` header; ffmpeg's mjpeg parser cuts packets at SOI/EOI). Each part's `seq=` decides: `unique`
    (above every sequence seen), `repeated` (at or below it: the same frame twice, or out of order), `gaps` (sequences
    skipped between two new ones: frames the game counted but this run never got whole), `noseq` (no marker: never
    counted as unique), `bad` (a header without a length). A part that does not end with EOI is `cut` (the game
    discarded it mid-write, or a stream end): never unique, so its sequence shows as a gap. Bytes before the part's SOI
    (a frame whose start the director drained before ffmpeg took over) are tolerated and counted as `trimmed`. Only the
    first SEQ_HEAD bytes and the last two of a part are kept; the rest is skipped by length, so the Python work is per
    chunk read."""

    def __init__(self):
        self.frames = self.unique = self.repeated = self.gaps = self.noseq = self.bad = self.resets = 0
        self.cut = self.trimmed = 0
        self.max_seq = self.first_seq = self.last_seq = None
        self.last_t = None
        self.block_gap = 0.0                      # longest time between two parts since the last take_gap()
        self._hdr, self._head, self._need, self._tail = bytearray(), bytearray(), 0, b""
        self._lock = threading.Lock()

    def feed(self, data, now):
        view, i, n = memoryview(data), 0, len(data)
        with self._lock:
            while i < n:
                if self._need:                                # inside a part's JPEG bytes
                    take = min(self._need, n - i)
                    if len(self._head) < SEQ_HEAD:
                        self._head += view[i:i + min(take, SEQ_HEAD - len(self._head))]
                    self._tail = (self._tail + bytes(view[max(i, i + take - 2):i + take]))[-2:]
                    self._need -= take
                    i += take
                    if not self._need:
                        self._part(now)
                    continue
                before = len(self._hdr)
                self._hdr += view[i:i + 512]
                end = self._hdr.find(b"\r\n\r\n")
                if end < 0:
                    i += len(self._hdr) - before
                    if len(self._hdr) > 2048:                 # no header end: resynchronise on the next one
                        self.bad += 1
                        del self._hdr[:-3]
                    continue
                i += end + 4 - before
                m = re.search(rb"(?i)content-length:\s*(\d{1,12})", self._hdr[:end])
                self._hdr.clear()
                length = int(m.group(1)) if m else None
                if length is not None and 0 < length <= SEQ_MAX_PART:
                    self._need = length
                else:
                    self.bad += 1                             # no, zero or absurd length: resynchronise on the next header

    def _part(self, now):
        start = self._head.find(b"\xff\xd8\xff")
        if start > 0:
            self.trimmed += 1
        seq = jpeg_seq(self._head[start:]) if start >= 0 else None
        complete = self._tail == b"\xff\xd9"
        self._head, self._tail = bytearray(), b""
        self.frames += 1
        if seq is None:
            self.noseq += 1
        elif not complete:
            self.cut += 1                                     # not a whole picture: its sequence stays a gap
        elif self.max_seq is None or seq > self.max_seq:
            if self.max_seq is not None:
                self.gaps += seq - self.max_seq - 1
            else:
                self.first_seq = seq
            self.unique += 1
            self.max_seq = seq
        elif self.max_seq - seq > SEQ_RESET:                  # the writer started counting again (a new game)
            self.resets += 1
            self.unique += 1
            self.max_seq = seq
        else:
            self.repeated += 1
        if seq is not None:
            self.last_seq = seq
        if self.last_t is not None:
            self.block_gap = max(self.block_gap, now - self.last_t)
        self.last_t = now

    def snapshot(self):
        with self._lock:
            return {"frames": self.frames, "unique": self.unique, "repeated": self.repeated, "gaps": self.gaps,
                    "noseq": self.noseq, "bad": self.bad, "cut": self.cut, "trimmed": self.trimmed,
                    "resets": self.resets, "first_seq": self.first_seq, "max_seq": self.max_seq,
                    "last_seq": self.last_seq, "last_t": self.last_t}

    def take_gap(self):
        """The longest time between two parts since the last call (s), then start over."""
        with self._lock:
            gap, self.block_gap = self.block_gap, 0.0
            return gap


class SeqTap:
    """The director's end of ffmpeg's tap output (tap_output_args): a pipe whose write end ffmpeg inherits, read by a
    thread until EOF (ffmpeg exited, or input 0 ended: `eof_at`). Never blocks the event loop."""

    def __init__(self, clock=time.monotonic):
        self.counter, self._clock = SeqCounter(), clock
        self.read_fd = self.write_fd = None
        self.eof_at, self.error = None, None
        self._thread = None

    def open(self):
        """-> the write end for ffmpeg (pass it with pass_fds, then call parent_done())."""
        self.read_fd, self.write_fd = os.pipe()
        try:                                                  # fewer wakeups at ~15 MB/s; best effort
            fcntl.fcntl(self.read_fd, getattr(fcntl, "F_SETPIPE_SZ", 1031), 1 << 20)
        except OSError:
            pass
        self._thread = threading.Thread(target=self._read, name="seq-tap", daemon=True)
        self._thread.start()
        return self.write_fd

    def parent_done(self):
        """Close the director's copy of the write end (ffmpeg holds its own), so the reader sees EOF with ffmpeg."""
        if self.write_fd is not None:
            try:
                os.close(self.write_fd)
            except OSError:
                pass
            self.write_fd = None

    def _read(self):
        """Read until EOF. A counting error marks the count invalid (`error`) but the pipe is still drained: a reader
        that stopped would fill it, and a closed one would end ffmpeg's tap output (read as the input's EOF)."""
        fd = self.read_fd
        try:
            while True:
                chunk = os.read(fd, 1 << 20)
                if not chunk:
                    break
                if self.error is None:
                    try:
                        self.counter.feed(chunk, self._clock())
                    except Exception as exc:  # never takes the director down; the state and the rows show it
                        self.error = f"{exc.__class__.__name__}: {exc}"[:200]
        except OSError as exc:
            self.error = self.error or f"{exc.__class__.__name__}: {exc}"[:200]
        finally:
            self.eof_at = self._clock()
            try:
                os.close(fd)
            except OSError:
                pass

    def close(self, timeout=2.0):
        self.parent_done()
        if self._thread is not None:
            self._thread.join(timeout)


class MainSource:
    """The fifo mode's choice of input 0: `fifo` (main.mjpeg) or the placeholder card. Pure (the caller passes the
    monotonic time and each check's freshness), so a fake clock drives it in tests.

    - fresh = a writer, main.json and its last_write_utc newer than --main-stale; `observe()` it every check.
    - first launch: the FIFO when fresh, else the placeholder (no failure counted).
    - on the FIFO: stale at a check (`tick` -> "stale"), or a FIFO run that ended by itself within MAIN_STABLE s
      (`exited`), is a failure: the placeholder, and no FIFO before `retry_at` = now + MAIN_BACKOFF[failures - 1].
    - on the placeholder: back to the FIFO (`tick` -> "back") once retry_at has passed and the FIFO has been fresh
      for --main-fresh s without a break.
    - a FIFO run on air and fresh without a break for MAIN_STABLE s clears the failures.
    These failures are the main view's own backoff; the director's generic ffmpeg crash backoff is not added to them."""

    def __init__(self, fresh_need=3.0, backoff=MAIN_BACKOFF, stable=MAIN_STABLE):
        self.fresh_need, self.backoff, self.stable = fresh_need, tuple(backoff), stable
        self.state = None                     # wanted: None (first launch), "fifo" or PLACEHOLDER
        self.failures, self.retry_at = 0, None
        self.fresh, self.reason, self.fresh_since = False, "not checked yet", None
        self.fifo_since = None                # launch time of the FIFO run on air

    def observe(self, now, fresh, reason):
        if not fresh:
            self.fresh_since = None
        elif self.fresh_since is None:
            self.fresh_since = now
        self.fresh, self.reason = bool(fresh), reason

    def fresh_for(self, now):
        return 0.0 if self.fresh_since is None else max(0.0, now - self.fresh_since)

    def retry_in(self, now):
        return 0.0 if self.retry_at is None else max(0.0, self.retry_at - now)

    def ready(self, now):
        """The placeholder may give way to the FIFO."""
        return self.fresh and self.fresh_for(now) >= self.fresh_need and self.retry_in(now) <= 0

    def fail(self, now, reason):
        self.failures += 1
        delay = self.backoff[min(self.failures, len(self.backoff)) - 1]
        self.state, self.retry_at, self.reason = PLACEHOLDER, now + delay, reason
        return delay

    def choose(self, now):
        """The source of the next launch (after observe()). A FIFO found stale between runs is a failure."""
        if self.state is None:
            self.state = "fifo" if self.fresh else PLACEHOLDER
        elif self.state == "fifo" and not self.fresh:
            self.fail(now, self.reason)
        elif self.state == PLACEHOLDER and self.ready(now):
            self.state = "fifo"
        return self.state

    def launched(self, now, source):
        self.state = source
        self.fifo_since = now if source == "fifo" else None

    def tick(self, now, on_air):
        """After observe(), for the run on air (`on_air` its source, None when nothing runs). -> "stale" (leave the
        FIFO now), "back" (return to it now) or "keep"."""
        if on_air == "fifo":
            if not self.fresh:
                self.fail(now, self.reason)
                return "stale"
            if (self.failures and self.fifo_since is not None and now - self.fifo_since >= self.stable
                    and self.fresh_for(now) >= self.stable):
                self.failures, self.retry_at = 0, None
            return "keep"
        if on_air == PLACEHOLDER and self.ready(now):
            self.state = "fifo"
            return "back"
        return "keep"

    def exited(self, now, on_air, uptime, reason):
        """A run ended by itself. A FIFO run shorter than `stable` s counts as a failed try."""
        if on_air == "fifo" and uptime < self.stable:
            self.fail(now, reason)
            return True
        return False


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


def recorder_pids(cfg, proc_root="/proc"):
    """Pids of ffmpeg processes recording into this recordings directory (an x11grab, testsrc2 or placeholder-card input,
    or the main FIFO, and the directory on the command line, the program named like --ffmpeg): what a director left
    behind, whatever its pid file says."""
    try:
        pids = [int(p) for p in os.listdir(proc_root) if p.isdigit()]
    except OSError:
        return []
    found, program = [], os.path.basename(cfg.ffmpeg)
    # the segment pattern <dir>/<prefix>-%03d.mp4, alone or after a tee option bracket: never a sibling such as dir-old
    inside = re.compile(r"(?:^|[\]|=])" + re.escape(str(cfg.recordings_dir).rstrip("/")) + "/")
    for pid in pids:
        try:
            argv = Path(proc_root, str(pid), "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        argv = [a.decode("utf-8", "replace") for a in argv if a]
        line = " ".join(argv)
        source = ("x11grab" in line or "testsrc2" in line or PLACEHOLDER_CARD in line or str(cfg.main_fifo) in argv)
        if argv and os.path.basename(argv[0]) in (program, "ffmpeg") and source and any(inside.search(a) for a in argv):
            found.append(pid)
    return sorted(found)


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True                          # exists, owned by someone else
    return True


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

async def spawn_ffmpeg(argv, pass_fds=()):
    """ffmpeg gets its own session: the supervisor signals the director's whole process group on stop, and a
    second signal (SIGTERM from the group, then our SIGINT) makes ffmpeg exit without writing the last fragment.
    With `-stdin` (live layout switching) its stdin is a pipe the director writes filter commands to. `pass_fds`: the
    seq tap's write end (fifo mode)."""
    interactive, progress = "-stdin" in argv, "-progress" in argv
    return await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE if interactive else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE if progress else asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        start_new_session=True, pass_fds=tuple(pass_fds))


class PrivacyHeld(RuntimeError):
    """A layout request while a privacy cut is in force (POST /director/layout answers 409)."""

    def __init__(self, privacy_id):
        super().__init__("a privacy cut is in force: only webcam_only is shown until it ends")
        self.privacy_id = privacy_id


class Director:
    STABLE_SECONDS = 60.0

    def __init__(self, cfg, *, spawn=None, find_window=None, check_voice=None, check_cam2=None, probe=None,
                 check_main=None, clock=time.monotonic, wall=time.time, sleep=asyncio.sleep):
        self.cfg = cfg
        self._spawn = spawn or spawn_ffmpeg
        self._find_window = find_window or (lambda: find_game_window(cfg))
        self.tap = VoiceTap(cfg.voice_fifo)
        self.cam2_tap = FifoTap(cfg.cam2_fifo, create=False, what="cam2")
        self._check_voice = check_voice or self.tap.writer_present
        self._check_cam2 = check_cam2 or (lambda writer=True: cam2_status(cfg, self.cam2_tap, self._wall(), writer))
        # fifo mode: the director's read end on main.mjpeg (the game's non-blocking writer can attach; drained while
        # ffmpeg does not read it), the source state machine, and the seq tap of the FIFO run on air
        self.main_mode = cfg.game_source == "fifo"
        self.main_tap = FifoTap(cfg.main_fifo, create=False, what="main")
        self._check_main = check_main or (lambda writer=True: main_status(cfg, self.main_tap, self._wall(), writer))
        self.main_source = MainSource(cfg.main_fresh)
        self.main_on = None                               # input 0 of the run on air: "fifo" | PLACEHOLDER (fifo mode)
        self.main_report = None                           # the last main.json read
        self.seq_tap = None
        self._main_ident, self._main_ticks = None, 0
        self.tap_overflows = 0                            # ffmpeg's "FIFO queue full" lines in the run on air
        self.tap_idle = False                             # the FIFO run's tap has been silent > --main-stale s
        self._stop_quick = False                          # the next stop is of a stale FIFO run: SIGINT twice, then kill
        self._main_handoff = False                        # a FIFO run is being spawned: no drain of main.mjpeg
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
        self.layout = cfg.layout or DEFAULT_LAYOUT     # the requested layout; PRIVATE_LAYOUT wins while privacy is on
        self.live_layout, self.live_order = None, ()      # live_layout: on air (confirmed by a reply or by the launch)
        self.privacy = None                               # the privacy cut in force (layout.jsonl reason "privacy")
        self.last_privacy = None                          # the last cut that ended, and its restore
        self._switching = None                            # the layout a map command in flight goes to
        self.stale_pids = set()                           # older ffmpegs that survived the reap (never acknowledge then)
        self.proc_root = "/proc"
        self.meter, self.fps_history = None, deque(maxlen=24)
        self.last_switch = None
        self.watchdog_action = None
        self.stalled_checks = 0
        self.slow_checks, self._speed_ref, self.window_speed = 0, None, None   # output speed between watchdog ticks
        self._slow_restart_mono = None                    # the last relaunch for slowness (one per SLOW_RESTART_GAP)
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
        self._log_polled = False                          # the first poll is a (re)start: recover the restore target
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
            "layout": self.wanted(),
            "layout_requested": self.layout,
            "live_layout": self.live_layout if self.alive else None,
            **self.privacy_state(),
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
            "window_speed": self.window_speed,
            "slow_checks": self.slow_checks,
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
            "game_source_mode": cfg.game_source,
            "main": self.main_state() if self.main_mode else None,
            "watchdog": self.watchdog_action,
            "recordings_dir": str(cfg.recordings_dir),
        }

    def main_state(self):
        """fifo mode: the main view's source, why, the backoff, main.json's figures and the seq tap's counts."""
        now, m, rep = self._clock(), self.main_source, self.main_report or {}
        drops = {k: rep.get(k) for k in MAIN_DROPS}
        out = {"source": self.main_on if self.alive else None, "wanted": m.state, "fresh": m.fresh, "reason": m.reason,
               "fresh_for_s": round(m.fresh_for(now), 1), "failures": m.failures,
               "retry_in_s": round(m.retry_in(now), 1), "json_age_s": rep.get("age_s"),
               "last_write_age_s": rep.get("last_write_age_s"), "game_fps": rep.get("fps"),
               "written": rep.get("written"), "sequence": rep.get("sequence"), "dropped": drops,
               "tap": None}
        tap = self.seq_tap if self.alive and self.main_on == "fifo" else None
        if tap is not None:
            snap = tap.counter.snapshot()
            out["tap"] = dict(snap, idle_s=self._tap_idle_s(now), idle=self.tap_idle, eof=tap.eof_at is not None,
                              error=tap.error, overflows=self.tap_overflows)
            out["tap"].pop("last_t")
        latest = self.meter.latest if self.alive and self.meter else None
        out["main_fps"] = (latest or {}).get("main_fps")              # new sequences per second, last stats period
        out["main_tap_ok"] = (latest or {}).get("main_tap_ok")
        return out

    def _tap_idle_s(self, now):
        """Seconds since the FIFO run's tap last saw a frame (since its launch before the first), or None."""
        tap = self.seq_tap if self.alive and self.main_on == "fifo" else None
        if tap is None:
            return None
        last = tap.counter.snapshot()["last_t"]
        return round(now - (last if last is not None else self.started_mono), 2)

    def _main_counts(self):
        """OutputMeter's `main` callable: the cumulative counts of the run on air, main.json's written and drops."""
        rep = self.main_report or {}
        drops = [rep.get(k) for k in MAIN_DROPS if rep.get(k) is not None]
        out = {"source": self.main_on, "game_written": rep.get("written"), "game_dropped": sum(drops) if drops else None}
        if self.seq_tap is not None:
            snap = self.seq_tap.counter.snapshot()
            out.update({k: snap[k] for k in MAIN_FIELDS if k in snap})
            out["overflows"] = self.tap_overflows
            out["tap_error"] = self.seq_tap.error is not None
            out["gap_s"] = self.seq_tap.counter.take_gap()
        return out

    def event(self, kind, **fields):
        record = {"t": iso(self._wall()), "source": "director", "kind": kind, **fields}
        print(json.dumps(record), flush=True)
        try:
            append_jsonl(self.cfg.streamer_dir / "events.jsonl", record)
        except OSError:
            pass

    # -- layout
    def wanted(self):
        """The layout the output must show: PRIVATE_LAYOUT while a privacy cut is in force, else the requested one."""
        return PRIVATE_LAYOUT if self.privacy is not None else self.layout

    def desktop_hidden(self):
        """True only while a privacy cut is in force AND the running ffmpeg is confirmed on a layout without any desktop
        picture: a map command for it answered ret:0, or this run was launched on it. False while a switch is in flight,
        a relaunch is pending (a failed switch may have left the graph anywhere) or nothing runs."""
        return (self.privacy is not None and self.alive and self._switching is None and not self._restart_reason
                and self.live_layout in LAYOUTS and not LAYOUTS[self.live_layout]["desktop"]
                and not any(pid_alive(pid) for pid in self.stale_pids))

    def privacy_state(self):
        p = self.privacy
        return {"privacy": p is not None, "privacy_id": p["id"] if p else None, "privacy_why": p["why"] if p else None,
                "privacy_since": iso(p["since"]) if p else None, "privacy_hidden_at": p["hidden_at"] if p else None,
                "privacy_seconds": round(self._wall() - p["since"], 1) if p else None,
                "desktop_hidden": self.desktop_hidden(), "privacy_restore": self.layout if p else None,
                "last_privacy": dict(self.last_privacy) if self.last_privacy else None}

    def follow_record(self, record):
        """Apply the last line of layout.jsonl. A privacy line (reason "privacy") starts or renews the cut; any other
        valid line ends it, and its layout (if valid; else the one requested before the cut) comes back. With --layout
        only the privacy part is followed: privacy wins over a fixed layout too. -> the layout now wanted when this line
        changed something, else None."""
        cut = privacy_cut(record)
        if cut is not None:
            return PRIVATE_LAYOUT if self._privacy_on(cut) else None
        try:
            layout = validate_layout(record.get("layout"))
        except ValueError:
            layout = None
        changed = False
        if layout is not None and self.cfg.layout is None and layout != self.layout:
            self.layout, changed = layout, True
        if self.privacy is not None:
            self._privacy_off(str(record.get("reason") or "layout line")[:40])
            changed = True
        return self.wanted() if changed or (layout is not None and self.cfg.layout is None) else None

    def _privacy_on(self, cut):
        """A privacy line: the cut starts (or, with another id while one is in force, is renewed: the agent's end line
        was never seen). -> True when something changed."""
        p, now = self.privacy, self._wall()
        if p is not None and p["id"] == cut["id"]:
            return False
        renewed = p is not None
        if p is None:
            self.privacy = p = {"since": now, "seen": self._clock(), "hidden_at": None, "hidden_id": None}
        p.update(id=cut["id"], why=cut["why"], seen=self._clock(), hidden_at=None)   # hidden again only when confirmed
        self.event("privacy_on", privacy_id=cut["id"], why=cut["why"], renewed=renewed, restore=self.layout,
                   live_layout=self.live_layout if self.alive else None, run=self.prefix if self.alive else None)
        self._on_air("already on air")                     # renewed while hidden: the new id is acknowledged at once
        return True

    def _privacy_off(self, how):
        p, self.privacy, now = self.privacy, None, self._wall()
        self.last_privacy = {"id": p["id"], "why": p["why"], "since": iso(p["since"]), "ended": iso(now),
                             "seconds": round(now - p["since"], 1), "hidden_at": p["hidden_at"], "how": how,
                             "restore": self.layout, "restored_at": None, "restored_layout": None}
        self.event("privacy_off", privacy_id=p["id"], seconds=self.last_privacy["seconds"], restore=self.layout, how=how,
                   was_hidden=p["hidden_at"] is not None, run=self.prefix if self.alive else None)

    def _on_air(self, how):
        """The on-air layout may have changed (a confirmed switch, a launch, a new cut): log the moment the desktop is
        hidden for a cut, and the moment the layout after a cut is back on air."""
        p, lp = self.privacy, self.last_privacy
        if p is not None and p["hidden_id"] != p["id"] and self.desktop_hidden():
            p["hidden_id"], p["hidden_at"] = p["id"], p["hidden_at"] or iso(self._wall())
            self.event("privacy_hidden", privacy_id=p["id"], how=how, live_layout=self.live_layout,
                       ms=round((self._clock() - p["seen"]) * 1000), run=self.prefix)
        elif (p is None and lp is not None and lp["restored_at"] is None and self.alive and self._switching is None
              and self.live_layout == effective_layout(self.layout, bool(self.cam2))):
            lp["restored_at"], lp["restored_layout"] = iso(self._wall()), self.live_layout
            self.event("privacy_restored", privacy_id=lp["id"], layout=self.live_layout, how=how, run=self.prefix)

    def set_layout(self, layout, end_privacy=False):
        """Validate, remember and log a layout request (one line of layout.jsonl). With --layout the request is
        logged but the fixed layout stays. While a privacy cut is in force (layout.jsonl is read first, so a privacy
        line written just before counts) the request is refused with PrivacyHeld, unless `end_privacy`: then the line
        (reason "privacy_end_operator") ends the cut."""
        requested = layout
        layout = validate_layout(layout)
        self.poll_layout_log()
        if self.privacy is not None and not end_privacy:
            raise PrivacyHeld(self.privacy["id"])
        previous = self.wanted()
        cut, before = self.privacy, self.layout
        if self.cfg.layout is None:
            self.layout = layout
        record = {"t": iso(self._wall()), "unix": round(self._wall(), 3), "layout": layout, "previous": previous,
                  "run": self.prefix if self.alive else None,
                  "offset_s": round(self.uptime(), 2) if self.alive else None, "recording": self.alive}
        if requested != layout:
            record["requested"] = requested
        if self.cfg.layout is not None:
            record["fixed"] = self.cfg.layout
        if cut is not None:
            record.update(reason="privacy_end_operator", privacy_id=cut["id"])
        path = self.cfg.streamer_dir / "layout.jsonl"
        read_up_to = self._layout_sig[0] if self._layout_sig else 0     # the bytes the poll above really read
        record["nonce"] = os.urandom(6).hex()
        append_jsonl(path, record)
        if cut is not None:
            self._privacy_off("operator")
        landed = self._cut_landed_before(path, read_up_to, record["nonce"])
        if landed is not None and (cut is None or landed.get("privacy_id") != cut["id"]):
            # the agent started a cut between this request's read and its line: put the cut back on top (the last line
            # decides, also for a director restarted later) and refuse the request
            again = {k: v for k, v in landed.items() if k not in ("t", "unix")}
            again.update(t=iso(self._wall()), unix=round(self._wall(), 3), reasserted_by="director",
                         refused_nonce=record["nonce"])          # a restarted director skips the refused request
            self.layout = before
            append_jsonl(path, again)
            self.poll_layout_log()
            self.event("privacy_reasserted", privacy_id=landed.get("privacy_id"), request=layout)
            raise PrivacyHeld(self.privacy["id"] if self.privacy else landed.get("privacy_id"))
        return record

    @staticmethod
    def _cut_landed_before(path, offset, nonce):
        """The privacy record (if any, and not ended after it) appended between `offset` and the line with `nonce`."""
        try:
            with open(path, "rb") as handle:
                handle.seek(offset)
                data = handle.read(LAYOUT_TAIL)
        except OSError:
            return None
        landed = None
        for line in data.split(b"\n"):
            try:
                rec = json.loads(line) if line.strip() else None
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("nonce") == nonce:
                return landed
            landed = rec if privacy_cut(rec) is not None else None
        return None

    def poll_layout_log(self):
        """Follow the last line of layout.jsonl (only re-read when its size or mtime changed). -> the layout now
        wanted when the line changed something, else None. A fixed --layout still follows privacy lines."""
        path = self.cfg.streamer_dir / "layout.jsonl"
        first, self._log_polled = not self._log_polled, True
        try:
            st = os.stat(path)
            sig = (st.st_size, st.st_mtime_ns)
        except OSError:
            sig = None
        if sig == self._layout_sig:
            return None
        self._layout_sig = sig
        records = read_tail_records(path) if sig else []
        record = records[-1] if records else None
        if record is None:
            return None
        if first and privacy_cut(record) is not None and self.cfg.layout is None:
            # a director (re)started during a cut: the layout to restore is the last request before it (or the agent's
            # `previous` on its privacy line), not the default
            refused = {r.get("refused_nonce") for r in records if r is not None and r.get("refused_nonce")}
            requests = [r.get("layout") for r in records[:-1]
                        if r is not None and privacy_cut(r) is None and r.get("nonce") not in refused]
            for name in list(reversed(requests)) + [record.get("previous")]:
                try:
                    self.layout = validate_layout(name)
                    break
                except ValueError:
                    continue
        return self.follow_record(record)

    def kick_layout(self):
        """Apply the wanted layout now (after a POST) instead of at the next layout tick."""
        if self._restart is None or self._stopping:
            return
        task = asyncio.ensure_future(self.apply_layout())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

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
                if effective_layout(self.wanted(), self.cam2) != target:
                    self.kick_layout()           # the wanted layout changed meanwhile (a new cut): at once, not next tick
                return "live"
            if detail.startswith(("no reply", "cannot write")):
                self.live_layout = None          # the command may or may not have reached the graph: on air unknown
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
        clock = self.meter.clock() if self.alive and self.meter is not None else None
        speed, self._speed_ref = window_speed(self._speed_ref, clock), clock
        self.window_speed = None if speed is None else round(speed, 3)
        since = None if self._slow_restart_mono is None else self._clock() - self._slow_restart_mono
        slow, self.slow_checks = speed_decision(speed, self.slow_checks, uptime=self.uptime(), since_restart=since)
        if slow == "restart" and action != "restart":
            self.last_error = f"output below real time ({self.window_speed}x) for {self.slow_checks} checks"
            self.event("speed_restart", run=self.prefix, speed=self.window_speed)
            self._slow_restart_mono = self._clock()
            self.request_restart("output below real time")
        elif slow == "held" and self.slow_checks == SLOW_LIMIT:
            self.event("speed_restart_held", run=self.prefix, speed=self.window_speed)
        if self.cfg.hls_dir is not None and self.prefix:
            prune_hls(self.cfg.hls_dir, self.prefix, self._wall())
        if not self.cfg.test_sources:
            await asyncio.to_thread(apply_retention, self.cfg, self.prefix, self.event)
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
                                                 wanted=LAYOUTS[self.wanted()]["needs_cam2"])
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
        self.stale_pids = {pid for pid in self.stale_pids if pid_alive(pid)}   # gone at last (pids may be reused)
        p = self.privacy
        if p is not None and self._wall() - p["since"] >= p.get("alerted", 0) + PRIVACY_ALERT_S:
            p["alerted"] = p.get("alerted", 0) + PRIVACY_ALERT_S       # a cut is never ended on a timer (fail closed):
            self.event("privacy_still_on", privacy_id=p["id"],         # tell the operator instead, every 10 minutes
                       seconds=round(self._wall() - p["since"]), desktop_hidden=self.desktop_hidden())
        return await self.apply_layout()

    async def main_tick(self):
        """fifo mode, every --main-interval s: is main.mjpeg fresh? A FIFO run that went stale is relaunched on the
        placeholder at once (a stalled FIFO stalls the whole graph); a placeholder run goes back to the FIFO once
        MainSource allows it. While ffmpeg reads the FIFO, main.json is checked every tick and the /proc writer scan
        runs every 5th (as cam2's); on the placeholder both run every tick."""
        if not self.main_mode:
            return "idle"
        self._main_ticks += 1
        writer = not (self.alive and self.main_on == "fifo") or self._main_ticks % 5 == 0
        launch = self.launches
        fresh, reason, report, hard = await asyncio.to_thread(self._check_main, writer)
        if self.launches != launch:
            return "superseded"                  # a new run started during the check: never judge it by this one
        self.main_report = report
        on_air = self.main_on if self.alive and not self._restart_reason else None    # None: a relaunch is pending
        if on_air == "fifo":
            if self.main_tap.ident != self._main_ident:
                fresh, reason, hard = False, "main FIFO was replaced (ffmpeg still reads the old one)", True
            elif self.seq_tap is not None and self.seq_tap.eof_at is not None:
                fresh, reason, hard = False, "ffmpeg's main view input ended (tap EOF)", True
            self._watch_tap()
        now = self._clock()
        self.main_source.observe(now, fresh, reason)    # also in the grace: freshness must be continuous to count
        if on_air == "fifo" and not fresh and not hard and self.uptime() < MAIN_LAUNCH_GRACE:
            return "grace"                       # ffmpeg's own start-up can hold the game's writes for a moment
        action = self.main_source.tick(now, on_air)
        if action == "stale":
            self.event("main_changed", main=PLACEHOLDER, previous="fifo", reason=reason, run=self.prefix,
                       failures=self.main_source.failures, retry_in_s=round(self.main_source.retry_in(now), 1))
            self._stop_quick = True              # a stalled FIFO read may never return: SIGINT twice, then SIGKILL
            self.request_restart(f"main view stale: {reason}")
        elif action == "back":
            self.event("main_changed", main="fifo", previous=PLACEHOLDER, reason=reason, run=self.prefix,
                       failures=self.main_source.failures, fresh_for_s=round(self.main_source.fresh_for(now), 1))
            self.request_restart("main view back")
        return action

    def _watch_tap(self):
        """A FIFO run whose tap has seen no frame for --main-stale s is reported (`main_tap_idle`), and again when frames
        flow (`main_tap_flowing`). Silence alone changes no source: a stalled cam2 or encoder starves the tap too; the
        watchdog and the speed guard handle those, main.json the game."""
        if self.seq_tap is None or not self.cfg.main_tap:
            return
        idle = self._tap_idle_s(self._clock())
        if idle is None:
            return
        if not self.tap_idle and idle > self.cfg.main_stale and self.uptime() >= MAIN_LAUNCH_GRACE:
            self.tap_idle = True
            self.event("main_tap_idle", run=self.prefix, idle_s=idle, overflows=self.tap_overflows)
        elif self.tap_idle and idle <= self.cfg.main_stale:
            self.tap_idle = False
            self.event("main_tap_flowing", run=self.prefix, overflows=self.tap_overflows)

    async def drain_tick(self):
        """While ffmpeg is not a FIFO's reader the director is, so its writer never sees a stalled reader."""
        if not (self.alive and self.voice):
            self.tap.drain()
        if not (self.alive and self.cam2):
            self.cam2_tap.drain(limit=4 << 20)                # MJPEG 720p60 is up to ~9 MB/s
        if self.main_mode and not self._main_handoff and not (self.alive and self.main_on == "fifo"):
            self.main_tap.drain(limit=MAIN_DRAIN)             # MJPEG 1080p60 is ~15 MB/s

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
        self.poll_layout_log()                       # resume with the last requested layout (or the privacy cut)
        watchers = [asyncio.ensure_future(self._loop(self.cfg.watchdog_interval, self.watchdog_tick)),
                    asyncio.ensure_future(self._loop(self.cfg.voice_interval, self.voice_tick)),
                    asyncio.ensure_future(self._loop(self.cfg.cam2_interval, self.cam2_tick)),
                    asyncio.ensure_future(self._loop(self.cfg.layout_interval, self.layout_tick)),
                    asyncio.ensure_future(self._loop(0.1, self.drain_tick))]
        if self.main_mode:
            watchers.append(asyncio.ensure_future(self._loop(self.cfg.main_interval, self.main_tick)))
        try:
            while not self._stopping:
                outcome = await self._run_once()
                if self._stopping:
                    break
                # "main_failed" (a FIFO run ffmpeg left early): the card in 1 s; MainSource's backoff governs the FIFO
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
            self.main_tap.close()

    async def _main_choice(self):
        """fifo mode: the source of input 0 for the next launch (MainSource.choose after a fresh check)."""
        fresh, reason, report, _ = await asyncio.to_thread(self._check_main, True)
        self.main_report = report
        now = self._clock()
        self.main_source.observe(now, fresh, reason)
        before = self.main_source.state
        main = self.main_source.choose(now)
        if before is None or before != main:
            self.event("main_changed", main=main, previous=before, reason=reason, failures=self.main_source.failures,
                       retry_in_s=round(self.main_source.retry_in(now), 1))
        if main == "fifo":
            self.main_tap.drain(limit=MAIN_DRAIN)               # start at a fresh frame
        self._main_ident = self.main_tap.ident if main == "fifo" else None
        self.game_source = "fifo:" + self.cfg.main_fifo.name if main == "fifo" else PLACEHOLDER
        self.game_note = reason if main == "fifo" else f"{PLACEHOLDER_CARD} card: {reason}"
        return main

    async def _sources(self):
        """-> (window, note, voice, cam2, main) for the next launch; `main` is None in the x11 mode."""
        cfg = self.cfg
        main = await self._main_choice() if self.main_mode else None
        if cfg.test_sources:
            if main is None:
                self.game_source, self.game_note = "test", "lavfi testsrc2 test sources"
            self.voice_reason = "lavfi sine test source"
            self.cam2_reason, self.cam2_fps = "lavfi testsrc2 test source", cfg.fps
            return None, self.game_note, True, True, main
        window = None
        if main is None:
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
        return window, (self.game_note if main else note), voice, cam2, main

    async def _run_once(self):
        cfg = self.cfg
        window, note, voice, available, main = await self._sources()
        self.cam2_now = available
        live = cfg.layout_switch == "live"
        cam2 = available and (live or LAYOUTS[self.wanted()]["needs_cam2"])
        target = effective_layout(self.wanted(), cam2)            # a privacy cut: the run starts on webcam_only
        prefix = unique_prefix(cfg.recordings_dir, datetime.fromtimestamp(self._wall(), timezone.utc))
        tap = SeqTap(self._clock) if main == "fifo" and cfg.main_tap else None
        self._tail.clear()
        self._printed = 0
        # from here until main_on is set, ffmpeg may already read main.mjpeg: the director must not drain it (Kimi)
        self._main_handoff = main == "fifo"
        try:
            tap_fd = tap.open() if tap else None
            argv = build_ffmpeg_argv(cfg, prefix=prefix, window_id=window, voice=voice, cam2=cam2, layout=target,
                                     live=live, encoder=self.encoder, cam2_fps=self.cam2_fps, main=main, tap_fd=tap_fd)
            proc = await (self._spawn(argv, pass_fds=(tap_fd,)) if tap else self._spawn(argv))
        except (OSError, ValueError) as exc:
            if tap:
                tap.close()
            self._main_handoff = False
            self.last_error = f"cannot start ffmpeg: {exc}"
            self.event("ffmpeg_spawn_failed", error=str(exc))
            self._failures += 1
            return "crash"
        except BaseException:
            if tap:
                tap.close()
            self._main_handoff = False
            raise
        finally:
            if tap:
                tap.parent_done()                    # ffmpeg holds its own write end: the reader sees EOF with it
        self.launches += 1
        self.proc, self.prefix, self.voice, self.cam2 = proc, prefix, voice, cam2
        self.live_layout, self.live_order = target, (live_order(cam2) if live else (target,))
        self.started_mono, self.started_wall = self._clock(), self._wall()
        self.first_started_wall = self.first_started_wall or self.started_wall
        self._last_bytes, self.stalled_checks, self.voice_mismatches, self.voice_gap = 0, 0, 0, False
        self.cam2_checks, self.slow_checks, self._speed_ref, self.window_speed = 0, 0, None, None
        self.main_on, self.seq_tap, self.tap_overflows, self.tap_idle, self._stop_quick = main, tap, 0, False, False
        self._main_handoff = False                   # alive and main_on now keep the drain away
        if main:
            self.main_source.launched(self.started_mono, main)
        while not self._replies.empty():
            self._replies.get_nowait()
        self.meter = OutputMeter(cfg.segment_seconds, prefix, self.fps_history,
                                 main=self._main_counts if main else None)
        self.watchdog_action = "grace"
        self._restart.clear()
        self._restart_reason = None
        self._write_pid(proc.pid)
        self.event("ffmpeg_started", pid=proc.pid, run=prefix, voice=voice, game=self.game_source, note=note,
                   cam2=cam2, layout=target, layout_switch=cfg.layout_switch, encoder=self.encoder, fps=cfg.fps,
                   desktop_fps=cfg.desktop_fps, hls=cfg.hls_dir is not None, rtmp=bool(cfg.rtmp_url),
                   privacy_id=self.privacy["id"] if self.privacy else None,
                   **({"main": main, "seq_tap": tap is not None} if main else {}))
        self._on_air("launch")                   # a run launched on webcam_only during a cut hides the desktop at once
        if effective_layout(self.wanted(), cam2) != target:
            self.kick_layout()                   # a privacy line arrived while ffmpeg was being started: switch now
        drain = asyncio.ensure_future(asyncio.gather(self._drain(proc), self._read_progress(proc, self.meter)))
        waiter = asyncio.ensure_future(proc.wait())
        restarter = asyncio.ensure_future(self._restart.wait())
        stopper = asyncio.ensure_future(self._stop_event.wait())
        await asyncio.wait({waiter, restarter, stopper}, return_when=asyncio.FIRST_COMPLETED)
        requested = None
        if not waiter.done():
            requested = "stop" if self._stopping else (self._restart_reason or "restart requested")
            if main == "fifo":                   # with -follow 1 a FIFO read loop only ends on a second signal
                nudge, grace = MAIN_STOP_NUDGE if self._stop_quick else (4.0, 8.0)
                await self._terminate(proc, grace=grace, nudge=nudge)
            else:
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
        if tap:
            await asyncio.to_thread(tap.close)               # the reader thread ends at ffmpeg's EOF
        if requested:
            self.event("ffmpeg_stopped", run=prefix, reason=requested, code=code)
            if requested != "stop":
                self.last_restart_reason = requested
                self._failures = 0
            return "stop" if requested == "stop" else "restart"
        tail = " | ".join(list(self._tail)[-3:])
        self.last_error = f"ffmpeg exited with code {code} after {uptime:.0f}s: {tail}"[:600]
        self.event("ffmpeg_exited", run=prefix, code=code, uptime_s=round(uptime, 1), tail=tail[:400])
        if main and self.main_source.exited(self._clock(), main, uptime, f"ffmpeg exited after {uptime:.0f}s on the FIFO"):
            # the main view's own backoff applies (the next launch is the placeholder), not the generic crash one too
            self.event("main_changed", main=PLACEHOLDER, previous="fifo", reason=self.main_source.reason, run=prefix,
                       failures=self.main_source.failures,
                       retry_in_s=round(self.main_source.retry_in(self._clock()), 1))
            return "main_failed"
        self._failures = 1 if uptime >= self.STABLE_SECONDS else self._failures + 1
        return "crash"

    def stderr_line(self, text):
        """One line of ffmpeg's stderr: command replies go to the switcher, the rest (redacted) to log and tail."""
        text = redact(text, self._secrets)
        reply = REPLY_RE.search(text)
        if reply:
            self._replies.put_nowait(int(reply.group(1)))
            return
        if TAP_OVERFLOW in text and self.seq_tap is not None:
            self.tap_overflows += 1              # the tap's fifo muxer dropped its queue: this window's count is invalid
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

    async def _terminate(self, proc, grace=8.0, nudge=None):
        """SIGINT lets ffmpeg write the last fragment and close the segment; SIGKILL if it hangs after `grace` s.
        `nudge` (fifo mode): a second SIGINT after that many seconds. ffmpeg interrupts its input reads only from the
        second signal on, and with `-follow 1` a FIFO whose writer is gone is read again and again until then; a read
        blocked on a writer that holds the FIFO open without writing returns only for the SIGKILL."""
        if proc.returncode is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
        except ProcessLookupError:
            return
        steps = [nudge, grace - nudge] if nudge is not None and 0 < nudge < grace else [grace]
        for index, wait in enumerate(steps):
            try:
                await asyncio.wait_for(proc.wait(), wait)
                return
            except asyncio.TimeoutError:
                if index + 1 < len(steps):
                    try:
                        proc.send_signal(signal.SIGINT)
                    except ProcessLookupError:
                        return
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
        """Before the first launch: stop every ffmpeg that still records into this directory (the pid file's, and any
        other a SIGKILLed director left behind, found in /proc): SIGINT, then SIGKILL, 5 s each. One that survives both
        is remembered and no privacy cut is acknowledged while it lives (it may still write the old layout to HLS); a
        restarted director finds it again in /proc."""
        own = read_pid(self.pid_file)
        pids = set(recorder_pids(self.cfg, self.proc_root))
        if own and own in pids:
            pids.add(own)
        for pid in sorted(pids):
            self.event("stale_ffmpeg", pid=pid)
        for sig in (signal.SIGINT, signal.SIGKILL):
            for pid in list(pids):
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pids.discard(pid)
                except OSError:
                    pass
            for _ in range(10):
                pids = {pid for pid in pids if pid_alive(pid)}
                if not pids:
                    break
                await self._sleep(0.5)
            if not pids:
                break
        for pid in sorted(pids):                 # it survived SIGKILL: it may still write the old layout to HLS
            self.event("stale_ffmpeg_survived", pid=pid)
        self.stale_pids = set(pids)
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
    if director.privacy is not None:
        return False, "a privacy cut is in force: webcam_only stays on air until it ends"
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
        end_privacy = data.get("end_privacy", False)
        if not isinstance(end_privacy, bool):
            raise web.HTTPBadRequest(text="end_privacy must be true or false")
        try:
            record = director.set_layout(data.get("layout"), end_privacy=end_privacy)
        except PrivacyHeld as exc:
            # the agent's privacy line rules until its end line: a plain request would show the desktop again
            director.kick_layout()               # the handler may be the first to have read the privacy line
            return web.json_response({"ok": False, "error": str(exc), "privacy_id": exc.privacy_id,
                                      "layout": PRIVATE_LAYOUT, "hint": "add \"end_privacy\": true to end the cut"},
                                     status=409, headers=no_store)
        except OSError as exc:
            raise web.HTTPInternalServerError(text=f"cannot write layout.jsonl: {exc.strerror}")
        live, note = layout_plan(director, name)
        director.kick_layout()
        return web.json_response({"ok": True, "layout": name, "live_layout": director.live_layout if director.alive else None,
                                  "live": live, "logged": record, "note": note,
                                  "privacy_ended": record.get("reason") == "privacy_end_operator"}, headers=no_store)

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
    p.add_argument("--keep-segments", type=int, default=18, help="keep at most N recording segments (0 = no cap)")
    p.add_argument("--min-free-gb", type=float, default=3.0,
                   help="delete the oldest finished segments while the disk has less free space than this")
    p.add_argument("--crf", type=int, default=23, help="x264 crf, or NVENC -cq")
    p.add_argument("--preset", default="veryfast", help="x264 preset (NVENC always uses p4)")
    p.add_argument("--encoder", default="libx264", choices=ENCODERS,
                   help="NVENC is probed once at start; libx264 when the probe fails")
    p.add_argument("--audio-bitrate", default="96k")
    p.add_argument("--layout", help="fix the layout (webcam, desktop, split, room, webcam_only); default: follow "
                                    "layout.jsonl (a privacy line there still wins over a fixed layout)")
    p.add_argument("--layout-switch", default="live", choices=SWITCH_MODES,
                   help="live: streamselect through ffmpeg's stdin; restart: relaunch ffmpeg at every switch")
    p.add_argument("--switch-timeout", type=float, default=3.0, help="seconds to wait for ffmpeg's command reply")
    p.add_argument("--cam2-fifo", help="default <streamer-dir>/cam2.mjpeg")
    p.add_argument("--cam2-json", help="default <streamer-dir>/cam2.json")
    p.add_argument("--cam2-stale", type=float, default=3.0, help="cam2 unusable when its last frame is older")
    p.add_argument("--cam2-interval", type=float, default=1.0, help="seconds between cam2 checks")
    p.add_argument("--layout-interval", type=float, default=1.0, help="seconds between layout.jsonl reads")
    p.add_argument("--game-source", default="x11", choices=GAME_SOURCES,
                   help="main view: x11 = x11grab of the game window on --game-display (default); fifo = the offscreen "
                        "game's <streamer-dir>/main.mjpeg, with a placeholder card while it is stale. Never inferred")
    p.add_argument("--main-fifo", help="fifo mode: default <streamer-dir>/main.mjpeg (created by the game)")
    p.add_argument("--main-json", help="fifo mode: default <streamer-dir>/main.json (written by the game)")
    p.add_argument("--main-stale", type=float, default=2.0,
                   help="fifo mode: the FIFO is stale when main.json or its last_write_utc is older than this")
    p.add_argument("--main-fresh", type=float, default=3.0,
                   help="fifo mode: main.json fresh this long before the placeholder gives way to the FIFO again")
    p.add_argument("--main-interval", type=float, default=1.0, help="fifo mode: seconds between staleness checks")
    p.add_argument("--no-main-tap", action="store_true",
                   help="fifo mode: no seq tap output (no unique-frame counts; main_fps stays 0)")
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
            desktop_fps=args.desktop_fps, segment_seconds=args.segment_seconds, keep_segments=args.keep_segments,
            min_free_gb=args.min_free_gb, crf=args.crf, preset=args.preset,
            audio_bitrate=args.audio_bitrate, watchdog_interval=args.watchdog_interval,
            voice_interval=args.voice_interval, encoder=args.encoder, layout=args.layout,
            layout_switch=args.layout_switch, switch_timeout=args.switch_timeout, cam2_fifo=args.cam2_fifo,
            cam2_json=args.cam2_json, cam2_stale=args.cam2_stale, cam2_interval=args.cam2_interval,
            layout_interval=args.layout_interval, hls_dir=args.hls_dir, rtmp_url=rtmp_url or None,
            test_sources=args.test_sources, test_seconds=args.test_seconds, game_source=args.game_source,
            main_fifo=args.main_fifo, main_json=args.main_json, main_stale=args.main_stale,
            main_fresh=args.main_fresh, main_interval=args.main_interval, main_tap=not args.no_main_tap)
    except ValueError as exc:
        p.error(str(exc))
    return args, cfg


def main(argv=None):
    args, cfg = parse_args(argv)
    if args.print_argv:
        main, main_note = None, ""
        if cfg.game_source == "fifo":                         # never touches the FIFO's data: a look, no read
            main_tap = FifoTap(cfg.main_fifo, create=False, what="main")
            fresh, why, _, _ = main_status(cfg, main_tap, time.time())
            main_tap.close()
            main = "fifo" if fresh else PLACEHOLDER
            main_note = f"; main view: {main} ({why}{'; seq tap on pipe:3 at run time' if fresh and cfg.main_tap else ''})"
        if cfg.test_sources:
            window, note, voice, reason, cam2, cam2_reason, cam2_fps = (
                None, "test sources", True, "test source", True, "test source", cfg.fps)
        else:
            window, note = find_game_window(cfg) if main is None else (None, "fifo mode: no window lookup")
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
        logged = read_last_record(cfg.streamer_dir / "layout.jsonl")
        private = privacy_cut(logged) is not None
        layout = effective_layout(PRIVATE_LAYOUT if private else
                                  cfg.layout or read_last_layout(cfg.streamer_dir / "layout.jsonl") or DEFAULT_LAYOUT, cam2)
        command = build_ffmpeg_argv(cfg, prefix="sub01-YYYYmmdd-HHMMSS", window_id=window, voice=voice, cam2=cam2,
                                    layout=layout, live=cfg.layout_switch == "live", encoder=encoder, cam2_fps=cam2_fps,
                                    main=main, tap_fd=3 if cfg.main_tap else None)
        print(f"# window: {window} ({note}); voice: {voice} ({reason}); cam2: {cam2} ({cam2_reason}); "
              f"encoder: {encoder} ({encoder_note}); layout: {layout} ({cfg.layout_switch} switching)"
              + ("; privacy cut in force (last layout.jsonl line)" if private else "") + main_note)
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
