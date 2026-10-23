#!/usr/bin/env python3
"""SUB-01 streamer director: records the stream locally with one ffmpeg process.

Inputs of the single ffmpeg process
  0  x11grab of the Unreal game window on :99.0 (`-window_id`, found with xdotool),
  1  x11grab of the desktop on :102.0 (1920x1080),
  2  the voice server's continuous PCM FIFO (s16le, 48 kHz, stereo), or, when
     nobody is writing to the FIFO, `anullsrc` silence (state shows `voice: false`).

Voice FIFO. The voice server opens `<streamer-dir>/voice.pcm` O_WRONLY|O_NONBLOCK and only attaches while a
reader exists, so the director itself keeps a read end open on the FIFO for as long as it runs (`VoiceTap`):
that is what lets the server attach, and a process holding the FIFO open for writing is what the director
takes as "voice available". While ffmpeg is not reading the FIFO (silent run, gaps between runs) the tap drains
it, so the server never sees a stalled reader; before a run that reads it the tap discards stale audio.
ffmpeg opens the path blocking, so a launch with voice only happens when a writer is already attached.

Output: h264 veryfast crf 23 at 24 fps + aac 96k, cut into 10 minute segments
`recordings/sub01-YYYYmmdd-HHMMSS-%03d.mp4` (UTC; every ffmpeg launch gets its
own timestamp, so a restart never overwrites a segment). Segments are fragmented
MP4: a crash or SIGKILL loses at most ~2 s and the file stays playable.

Layouts. The live composite is FIXED to `character` in v1 (game full frame,
desktop picture-in-picture 480x270 bottom-right). `POST /director/layout` only
validates the name, remembers it and appends one line to `<streamer-dir>/layout.jsonl`
(`t`, `unix`, `layout`, `previous`, `run`, `offset_s`, `recording`). A later post
pass can read that file to re-cut the stream. Honest limit: the recording holds
only the composite, so a post pass can re-frame or cut it but cannot bring back
the full-size desktop under the `desktop` layout; that needs the raw sources.
`build_filter_complex(layout)` already builds the graph for all three layouts
(`[0:v]` game, `[1:v]` desktop) for such a pass.

HTTP on 127.0.0.1 only; every route except /healthz needs the operator
credential in `X-Admin-Token` (from --token-file or SUB01_ADMIN_TOKEN; never logged):

  GET  /healthz           -> {"ok": true, "recording": bool}
  GET  /director/state    -> {recording, since, segments:[{name,bytes,mtime}], ffmpeg_pid,
                              restarts, last_error, layout, live_layout, voice, ...}
  POST /director/layout   {"layout": "character"|"desktop"|"split"}

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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import web

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MIN_TOKEN = 12
MAX_BODY = 1024
DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
DEFAULT_PORT = 8837

# ---------------------------------------------------------------- layouts

LIVE_LAYOUT = "character"
DEFAULT_LAYOUT = LIVE_LAYOUT
PIP_MARGIN = 24
# `live` says whether the running ffmpeg can show it. Only `character` is live in v1.
LAYOUTS = {
    "character": {"live": True, "main": "game", "pip": "desktop",
                  "summary": "game full frame, desktop picture-in-picture bottom-right"},
    "desktop": {"live": False, "main": "desktop", "pip": "game",
                "summary": "desktop full frame, game picture-in-picture bottom-right"},
    "split": {"live": False, "main": None, "pip": None,
              "summary": "game and desktop side by side, each half width"},
}
X264_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")
SEGMENT_RE = re.compile(r"^(sub01-\d{8}-\d{6})-(\d{3})\.mp4$")


def validate_layout(value):
    """Return the layout name or raise ValueError (the message lists the valid names)."""
    if not isinstance(value, str) or value not in LAYOUTS:
        raise ValueError("layout must be one of " + ", ".join(sorted(LAYOUTS)))
    return value


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

    def __post_init__(self):
        base = Path(self.streamer_dir)
        object.__setattr__(self, "streamer_dir", base)
        object.__setattr__(self, "recordings_dir", Path(self.recordings_dir) if self.recordings_dir else base / "recordings")
        object.__setattr__(self, "voice_fifo", Path(self.voice_fifo) if self.voice_fifo else base / "voice.pcm")
        if not 10 <= self.desktop_fps <= 24:
            raise ValueError("desktop fps must be between 10 and 24")
        if not 10 <= self.fps <= 30:
            raise ValueError("fps must be between 10 and 30")
        if self.segment_seconds < 10:
            raise ValueError("segment length must be at least 10 seconds")
        if not 0 <= self.crf <= 51:
            raise ValueError("crf must be between 0 and 51")
        if self.preset not in X264_PRESETS:
            raise ValueError("unknown x264 preset")
        if min(self.width, self.height, self.pip_width, self.pip_height) < 16:
            raise ValueError("frame sizes are too small")
        if not re.fullmatch(r":\d+(\.\d+)?", self.game_display) or not re.fullmatch(r":\d+(\.\d+)?", self.desktop_display):
            raise ValueError("displays look like :99.0")


def build_filter_complex(layout, cfg):
    """ffmpeg filter graph for a layout. Inputs: [0:v] game, [1:v] desktop. Output label [vout]."""
    validate_layout(layout)
    w, h, pw, ph, fps = cfg.width, cfg.height, cfg.pip_width, cfg.pip_height, cfg.fps
    if layout == "split":
        half_w = (w // 2) & ~1
        half_h = (half_w * h // w) & ~1
        return (f"[0:v]fps={fps},scale={half_w}:{half_h},setsar=1[l];"
                f"[1:v]fps={fps},scale={half_w}:{half_h},setsar=1[r];"
                f"[l][r]hstack=inputs=2,pad={w}:{h}:0:(oh-ih)/2:black,format=yuv420p[vout]")
    main_src, pip_src = ("0:v", "1:v") if layout == "character" else ("1:v", "0:v")
    return (f"[{main_src}]fps={fps},scale={w}:{h},setsar=1[main];"
            f"[{pip_src}]scale={pw}:{ph}:flags=area,setsar=1[pip];"
            f"[main][pip]overlay=x=W-w-{PIP_MARGIN}:y=H-h-{PIP_MARGIN}:eof_action=pass,format=yuv420p[vout]")


def build_ffmpeg_argv(cfg, *, prefix, window_id=None, voice=True):
    """The one ffmpeg command line. `window_id` None captures the whole of :99.0 instead."""
    size = f"{cfg.width}x{cfg.height}"
    argv = [cfg.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning",
            "-thread_queue_size", "512", "-f", "x11grab", "-framerate", str(cfg.fps), "-draw_mouse", "0"]
    argv += ["-window_id", str(int(window_id))] if window_id else ["-video_size", size]
    argv += ["-i", cfg.game_display,
             "-thread_queue_size", "512", "-f", "x11grab", "-framerate", str(cfg.desktop_fps),
             "-draw_mouse", "0", "-video_size", size, "-i", cfg.desktop_display]
    if voice:
        argv += ["-thread_queue_size", "4096", "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", str(cfg.voice_fifo)]
    else:
        argv += ["-re", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    graph = build_filter_complex(LIVE_LAYOUT, cfg)
    if voice:
        # apad: if the voice server goes away the FIFO hits EOF; silence keeps the audio track running meanwhile
        graph += ";[2:a]apad[aout]"
    argv += ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]" if voice else "2:a",
             "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-pix_fmt", "yuv420p",
             "-r", str(cfg.fps), "-g", str(cfg.fps * 2), "-max_muxing_queue_size", "1024",
             "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-ar", "48000", "-ac", "2",
             "-fflags", "+flush_packets",          # a static screen makes tiny fragments: without this they sit in a 32 KB buffer
             "-f", "segment", "-segment_time", str(cfg.segment_seconds), "-reset_timestamps", "1",
             "-segment_format", "mp4",
             "-segment_format_options", "movflags=+frag_keyframe+empty_moov+default_base_moof",
             str(Path(cfg.recordings_dir) / f"{prefix}-%03d.mp4")]
    return argv


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


BACKOFF = (2, 4, 8, 16, 32, 60)


def backoff_delay(failures):
    """Seconds to wait after `failures` consecutive short-lived ffmpeg runs."""
    return 1.0 if failures <= 0 else float(BACKOFF[min(failures, len(BACKOFF)) - 1])


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
    """A read end on the voice FIFO, kept open by the director (see the module docstring)."""

    SETTLE = 1.5          # seconds a freshly opened tap waits for a polling writer (the voice server retries every 0.1 s)

    def __init__(self, path, proc_root="/proc", create=True, clock=time.monotonic, sleep=time.sleep):
        self.path, self.proc_root, self.create = Path(path), proc_root, create
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
                    return False, "voice FIFO does not exist"
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    os.mkfifo(self.path, 0o600)
                    st = os.stat(self.path)
                except OSError as exc:
                    return False, f"cannot create the voice FIFO: {exc.strerror}"
            except OSError as exc:
                self.close()
                return False, f"cannot stat the voice FIFO: {exc.strerror}"
            if not stat.S_ISFIFO(st.st_mode):
                self.close()
                return False, "voice path is not a FIFO"
            if self.fd is not None and self.ident == (st.st_dev, st.st_ino):
                return True, ""
            self.close()
            try:
                self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError as exc:
                return False, f"cannot open the voice FIFO: {exc.strerror}"
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
                return False, "no process writes to the voice FIFO"
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
    second signal (SIGTERM from the group, then our SIGINT) makes ffmpeg exit without writing the last fragment."""
    return await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        start_new_session=True)


class Director:
    STABLE_SECONDS = 60.0

    def __init__(self, cfg, *, spawn=None, find_window=None, check_voice=None,
                 clock=time.monotonic, wall=time.time, sleep=asyncio.sleep):
        self.cfg = cfg
        self._spawn = spawn or spawn_ffmpeg
        self._find_window = find_window or (lambda: find_game_window(cfg))
        self.tap = VoiceTap(cfg.voice_fifo)
        self._check_voice = check_voice or self.tap.writer_present
        self._clock, self._wall, self._sleep = clock, wall, sleep
        self.proc = None
        self.prefix = None
        self.started_mono = self.started_wall = None
        self.first_started_wall = None
        self.launches = 0
        self.last_error = None
        self.voice, self.voice_reason = None, ""
        self.game_source = self.game_note = None
        self.layout = DEFAULT_LAYOUT
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
            "live_layout": LIVE_LAYOUT,
            "voice": self.voice,
            "voice_reason": self.voice_reason,
            "game_source": self.game_source,
            "game_note": self.game_note,
            "watchdog": self.watchdog_action,
            "recordings_dir": str(self.cfg.recordings_dir),
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
        layout = validate_layout(layout)
        previous, self.layout = self.layout, layout
        record = {"t": iso(self._wall()), "unix": round(self._wall(), 3), "layout": layout, "previous": previous,
                  "run": self.prefix if self.alive else None,
                  "offset_s": round(self.uptime(), 2) if self.alive else None, "recording": self.alive}
        append_jsonl(self.cfg.streamer_dir / "layout.jsonl", record)
        return record

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
        return action

    async def voice_tick(self):
        if not self.alive or self.voice is None:
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

    async def drain_tick(self):
        """While ffmpeg is not the FIFO's reader the director is, so the voice server never sees a stalled reader."""
        if not (self.alive and self.voice):
            self.tap.drain()

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

    async def run(self):
        self._restart, self._stop_event = asyncio.Event(), asyncio.Event()
        if self._stopping:
            self._stop_event.set()
        self.cfg.recordings_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.cfg.streamer_dir / "pids").mkdir(parents=True, exist_ok=True, mode=0o700)
        await self.reap_stale_ffmpeg()
        watchers = [asyncio.ensure_future(self._loop(self.cfg.watchdog_interval, self.watchdog_tick)),
                    asyncio.ensure_future(self._loop(self.cfg.voice_interval, self.voice_tick)),
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
            for task in watchers:
                task.cancel()
            await asyncio.gather(*watchers, return_exceptions=True)
            self.tap.close()

    async def _run_once(self):
        cfg = self.cfg
        window, note = await asyncio.to_thread(self._find_window)
        self.game_source = f"window:{window:#x}" if window else "screen"
        self.game_note = note if window else f"window not found, recording the whole of {cfg.game_display}: {note}"
        voice, self.voice_reason = await asyncio.to_thread(self._check_voice)
        if voice:
            self.tap.drain()                                  # no stale audio at the start of the run
        prefix = unique_prefix(cfg.recordings_dir, datetime.fromtimestamp(self._wall(), timezone.utc))
        argv = build_ffmpeg_argv(cfg, prefix=prefix, window_id=window, voice=voice)
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
        self.proc, self.prefix, self.voice = proc, prefix, voice
        self.started_mono, self.started_wall = self._clock(), self._wall()
        self.first_started_wall = self.first_started_wall or self.started_wall
        self._last_bytes, self.stalled_checks, self.voice_mismatches, self.voice_gap = 0, 0, 0, False
        self.watchdog_action = "grace"
        self._restart.clear()
        self._restart_reason = None
        self._write_pid(proc.pid)
        self.event("ffmpeg_started", pid=proc.pid, run=prefix, voice=voice, game=self.game_source, note=note)
        drain = asyncio.ensure_future(self._drain(proc))
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

    async def _drain(self, proc):
        stream = getattr(proc, "stderr", None)
        while stream is not None:
            line = await stream.readline()
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                self._tail.append(text)
                if self._printed < 200:
                    self._printed += 1
                    print("ffmpeg:", text, flush=True)

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
        if "x11grab" in cmdline and str(self.cfg.recordings_dir) in cmdline:
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
            record = director.set_layout(name)
        except OSError as exc:
            raise web.HTTPInternalServerError(text=f"cannot write layout.jsonl: {exc.strerror}")
        return web.json_response({"ok": True, "layout": name, "live_layout": LIVE_LAYOUT,
                                  "live": LAYOUTS[name]["live"], "logged": record,
                                  "note": "v1 records the fixed character composite; the request is logged in layout.jsonl"},
                                 headers=no_store)

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
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--desktop-fps", type=int, default=15, help="10-24")
    p.add_argument("--segment-seconds", type=int, default=600)
    p.add_argument("--crf", type=int, default=23)
    p.add_argument("--preset", default="veryfast")
    p.add_argument("--audio-bitrate", default="96k")
    p.add_argument("--watchdog-interval", type=float, default=30.0)
    p.add_argument("--voice-interval", type=float, default=15.0)
    p.add_argument("--print-argv", action="store_true", help="resolve the window and voice, print the ffmpeg command, exit")
    args = p.parse_args(argv)
    if args.host not in LOOPBACK:
        p.error("the director binds only to loopback")
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
            voice_interval=args.voice_interval)
    except ValueError as exc:
        p.error(str(exc))
    return args, cfg


def main(argv=None):
    args, cfg = parse_args(argv)
    if args.print_argv:
        window, note = find_game_window(cfg)
        tap = VoiceTap(cfg.voice_fifo, create=False)
        voice, reason = tap.writer_present()
        tap.close()
        command = build_ffmpeg_argv(cfg, prefix="sub01-YYYYmmdd-HHMMSS", window_id=window, voice=voice)
        print(f"# window: {window} ({note}); voice: {voice} ({reason})")
        print(shlex.join(command))
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
