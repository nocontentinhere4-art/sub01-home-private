#!/usr/bin/env python3
"""SUB-01 live stream, "cartoon mode" frame feeder.

What this service is
--------------------
A small standalone daemon that keeps a named pipe (FIFO) permanently fed with a
1280x720, 30 fps MJPEG stream (concatenated JPEG files) so that a reader (the
ffmpeg process of the stream director) never stalls:

    <streamer-dir>/cartoon.mjpeg        the FIFO (created 0600 if missing)
    <streamer-dir>/cartoon/poster.jpg   idle still (override with --poster)
    <streamer-dir>/cartoon/clips/       the only place clips may be played from

* IDLE: the poster frame is repeated at 30 fps.  If the poster is missing or
  unreadable a dark frame with the text "CARTOON MODE" is used.  The poster is
  re-read whenever its mtime changes (checked at most once a second).
* PLAYING: a clip (mp4) is decoded by an ffmpeg child to raw 1280x720 RGB at
  30 fps (aspect kept: scale + pad with black), an optional caption is burnt
  into a semi-transparent bar at the bottom with Pillow, every frame is encoded
  as JPEG and written to the FIFO in real time.  Afterwards we go back to idle.

Writing to a FIFO without ever blocking the event loop
------------------------------------------------------
The FIFO is opened O_WRONLY|O_NONBLOCK.  That open fails with ENXIO as long as
no reader has the FIFO open, so we retry once per second and meanwhile DROP the
frames (counted in "dropped") instead of buffering them.  Once open, writes are
non-blocking too: a pipe holds 64 KiB by default (we ask for 1 MiB with
F_SETPIPE_SZ), a JPEG frame is often larger, so a write may be partial.  The
unwritten tail of that frame is kept in a ONE-frame "pending" slot and flushed
on the next tick; while the slot is occupied further frames are dropped.  So
memory is bounded by a single frame and the byte stream always stays aligned on
frame boundaries (a reader never sees a torn frame in the middle of the stream).
When the reader goes away the write fails with EPIPE; the fd is closed, the
pending tail discarded and the open-retry loop starts again.  Reader attached /
detached transitions are logged.

Playback timing: one 30 fps tick loop (monotonic deadlines, resync if more than
250 ms behind) is the ONLY writer of the FIFO.  The decoder task runs ahead by at
most 8 encoded frames (bounded queue = back-pressure on ffmpeg); if it ever
lags the previous frame is repeated, so the output rate stays constant.  The
clip timer is counted in ticks, i.e. it is wall-clock time, with or without a
reader attached.

HTTP API (127.0.0.1 only, default port 8842)
--------------------------------------------
Every route except GET /healthz needs the header X-Admin-Token equal to the
content of --token-file (whitespace-trimmed; compared with hmac.compare_digest;
the token is never logged).  A missing / wrong token gives 401.

  GET  /healthz                 -> {"ok": true}
  POST /play {"id","path","caption"}
        id       str, 1..64 chars, only printable characters
        path     regular file inside <streamer-dir>/cartoon/clips/ (symlinks
                 are resolved first; relative paths are taken relative to
                 clips/), at most 64 MB; anything else is 400.
        caption  optional; sanitized to printable characters, whitespace
                 collapsed, at most 80 characters.
        Plays the clip once and returns, as soon as the first frame is
        decoded, {"ok": true, "id", "seconds", "caption"}; "seconds" is the
        planned play time = min(clip duration from ffprobe, 12 s), null if the
        duration is unknown.  At most 12 s are played.  409 while another clip
        is playing, 422 if the clip cannot be decoded.
  POST /stop                    -> {"ok": true, "stopped": id or null}
  GET  /state                   -> {"playing": id or null, "started": epoch
        seconds of the current clip or null, "seconds": planned seconds of the
        current clip or null, "frames_written": complete frames accepted by
        the FIFO since start (idle + clips), "clip_frames": frames shown of the
        current clip, "reader": bool (FIFO currently open for writing),
        "dropped": frames dropped since start}

Logging: one JSON object per line on stdout ("event": start, play, done, stop,
error, reader_attached, reader_detached, shutdown).

Shutdown: SIGTERM / SIGINT stop the tick loop, kill the ffmpeg child and exit.
If this process dies hard, the child's stdout pipe breaks and ffmpeg exits by
itself.

CLI
---
  python3 scripts/cartoon_feed.py --streamer-dir DIR --token-file FILE
          [--port 8842] [--poster FILE] [--ffmpeg ffmpeg] [--ffprobe ffprobe]

Requires Python 3.12, aiohttp, Pillow and the ffmpeg binary.
"""
from __future__ import annotations

import argparse
import asyncio
import errno
import fcntl
import functools
import hmac
import io
import json
import os
import shutil
import signal
import stat
import sys
import time
from typing import Any, Callable

from aiohttp import web
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- constants --
W, H = 1280, 720                      # output frame size
FPS = 30
FRAME_BYTES = W * H * 3               # one raw rgb24 frame from ffmpeg
JPEG_QUALITY = 85
MAX_CLIP_SECONDS = 12.0
MAX_CLIP_BYTES = 64 * 1024 * 1024
MAX_CAPTION = 80
MAX_ID = 64
QUEUE_FRAMES = 8                      # decoder read-ahead (encoded JPEGs)
REOPEN_SECONDS = 1.0                  # FIFO open retry period without reader
F_SETPIPE_SZ = 1031                   # linux fcntl, not exported by fcntl module
PIPE_SIZE = 1 << 20
FIRST_FRAME_TIMEOUT = 8.0             # /play waits this long for a decoded frame
MAX_BODY = 64 * 1024

_REPEAT = object()                    # "decoder has no new frame, repeat last"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z"


def log_json(event: str, **fields: Any) -> None:
    """One JSON line on stdout.  Never pass the admin token here."""
    print(json.dumps({"ts": now_iso(), "event": event, **fields}, ensure_ascii=False), flush=True)


# -------------------------------------------------------------- text helpers --
def sanitize_text(value: Any, limit: int) -> str:
    """Printable characters only; every run of whitespace (incl. control chars
    such as newlines, tabs, NUL, ESC) becomes a single space; trimmed; cut to
    `limit` characters."""
    if not isinstance(value, str):
        return ""
    out: list[str] = []
    for ch in value:
        if ch.isprintable() and ch not in "  ":
            out.append(ch)
        else:
            out.append(" ")          # control / unprintable -> separator
    return " ".join("".join(out).split())[:limit]


def sanitize_caption(value: Any) -> str:
    return sanitize_text(value, MAX_CAPTION)


_FONT_FILES = (
    "DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "LiberationSans-Bold.ttf",
    "LiberationSans-Regular.ttf", "NotoSans-Bold.ttf", "Arial.ttf",
)


@functools.lru_cache(maxsize=16)
def get_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in _FONT_FILES:
        try:
            return ImageFont.truetype(name, size)   # Pillow searches system font dirs
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)    # Pillow >= 10.1, scalable
    except TypeError:                               # very old Pillow: bitmap font
        return ImageFont.load_default()


def text_width(font, text: str) -> float:
    return font.getlength(text)


def wrap_lines(font, text: str, max_w: float) -> list[str]:
    """Greedy word wrap; words wider than a line are hard-split by characters."""
    lines: list[str] = []
    cur = ""
    for word in text.split(" "):
        while text_width(font, word) > max_w and len(word) > 1:      # hard split
            k = len(word)
            while k > 1 and text_width(font, word[:k]) > max_w:
                k -= 1
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:k])
            word = word[k:]
        trial = word if not cur else cur + " " + word
        if text_width(font, trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def build_caption_strip(caption: str) -> tuple[Image.Image, int] | None:
    """Pre-render the caption bar once per clip.

    Returns (RGBA strip of width W, y of its top edge in the frame) or None for
    an empty caption.  Single line at 40..28 px if it fits, else two lines at
    28 px (second line ellipsised)."""
    caption = sanitize_caption(caption)
    if not caption:
        return None
    max_w = W - 96
    font, lines = None, None
    for size in (40, 36, 32, 28):
        f = get_font(size)
        if text_width(f, caption) <= max_w:
            font, lines = f, [caption]
            break
    if font is None:
        font = get_font(28)
        lines = wrap_lines(font, caption, max_w)
        if len(lines) > 2:
            lines = lines[:2]
            while lines[1] and text_width(font, lines[1] + "...") > max_w:
                lines[1] = lines[1][:-1]
            lines[1] += "..."
    line_h = int(font.size * 1.25) if hasattr(font, "size") else 36
    pad = 14
    bar_h = line_h * len(lines) + 2 * pad
    strip = Image.new("RGBA", (W, bar_h), (0, 0, 0, 165))           # semi-transparent bar
    draw = ImageDraw.Draw(strip)
    for i, line in enumerate(lines):
        draw.text((W / 2, pad + i * line_h), line, font=font, fill=(255, 255, 255, 255),
                  anchor="ma", stroke_width=2, stroke_fill=(0, 0, 0, 255))
    return strip, H - bar_h


# -------------------------------------------------------------- image helpers --
def to_jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def fit_to_frame(img: Image.Image) -> Image.Image:
    """Scale keeping aspect ratio and pad with black to W x H."""
    img = img.convert("RGB")
    scale = min(W / img.width, H / img.height)
    nw, nh = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    canvas.paste(img, ((W - nw) // 2, (H - nh) // 2))
    return canvas


def dark_frame_jpeg() -> bytes:
    img = Image.new("RGB", (W, H), (14, 14, 22))
    ImageDraw.Draw(img).text((W / 2, H / 2), "CARTOON MODE", font=get_font(72),
                             fill=(200, 200, 215), anchor="mm")
    return to_jpeg(img)


def load_poster_jpeg(path: str) -> bytes | None:
    try:
        with Image.open(path) as im:
            im.load()
            return to_jpeg(fit_to_frame(im))
    except Exception:           # missing, unreadable, not an image ...
        return None


def render_clip_frame(raw: bytes, strip: tuple[Image.Image, int] | None) -> bytes:
    """raw rgb24 W*H*3 -> caption bar composited (bottom strip only) -> JPEG."""
    img = Image.frombytes("RGB", (W, H), raw)
    if strip is not None:
        bar, y0 = strip
        region = img.crop((0, y0, W, H)).convert("RGBA")
        region.alpha_composite(bar)
        img.paste(region.convert("RGB"), (0, y0))
    return to_jpeg(img)


# ------------------------------------------------------------- FIFO plumbing --
def ensure_fifo(path: str) -> None:
    """Create the FIFO (0600) if missing; refuse to use a non-FIFO."""
    try:
        st = os.stat(path)
    except FileNotFoundError:
        os.mkfifo(path, 0o600)
        os.chmod(path, 0o600)           # umask-independent
        return
    if not stat.S_ISFIFO(st.st_mode):
        raise RuntimeError(f"{path} exists and is not a FIFO")


class FifoWriter:
    """Never-blocking, frame-aligned, bounded-memory writer for the MJPEG FIFO.

    write_frame() is called from the event loop once per tick and returns True
    when the complete frame was handed to the pipe, False when it was dropped
    or is still partly pending (see the module docstring)."""

    def __init__(self, path: str, log: Callable[..., None] = log_json,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self.log = log
        self.clock = clock
        self.fd: int | None = None
        self.pending = memoryview(b"")        # unwritten tail of at most ONE frame
        self.next_open = 0.0                  # earliest time of the next open attempt
        self.frames_written = 0
        self.dropped = 0

    @property
    def reader(self) -> bool:
        return self.fd is not None

    def _try_open(self) -> None:
        now = self.clock()
        if now < self.next_open:
            return
        self.next_open = now + REOPEN_SECONDS
        try:
            ensure_fifo(self.path)            # recreate if someone removed it
            fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as e:
            if e.errno != errno.ENXIO:        # ENXIO = no reader yet: perfectly normal
                self.log("error", where="fifo_open", error=str(e))
            return
        except RuntimeError as e:
            self.log("error", where="fifo_open", error=str(e))
            return
        try:                                  # bigger pipe -> fewer partial writes (best effort)
            fcntl.fcntl(fd, F_SETPIPE_SZ, PIPE_SIZE)
        except OSError:
            pass
        self.fd = fd
        self.log("reader_attached")

    def _detach(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
            self.log("reader_detached")
        self.pending = memoryview(b"")
        self.next_open = self.clock() + REOPEN_SECONDS

    def _push(self, data: memoryview) -> memoryview | None:
        """Write what fits.  Returns the unwritten rest, or None on EPIPE/error."""
        assert self.fd is not None
        try:
            n = os.write(self.fd, data)
        except BlockingIOError:
            return data
        except OSError as e:                  # EPIPE: reader gone; anything else: also reopen
            if e.errno != errno.EPIPE:
                self.log("error", where="fifo_write", error=str(e))
            return None
        return data[n:]

    def write_frame(self, frame: bytes) -> bool:
        if self.fd is None:
            self._try_open()
            if self.fd is None:
                self.dropped += 1
                return False
        if len(self.pending):                 # finish the previous frame first
            rest = self._push(self.pending)
            if rest is None:
                self._detach()
                self.dropped += 1
                return False
            self.pending = rest
            if len(rest):                     # reader is slow: drop the new frame
                self.dropped += 1
                return False
            self.frames_written += 1
        rest = self._push(memoryview(frame))
        if rest is None:
            self._detach()
            self.dropped += 1
            return False
        if len(rest):
            self.pending = rest               # remember the tail, count it when complete
            return False
        self.frames_written += 1
        return True

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


# --------------------------------------------------------------- clip logic --
class ClipError(Exception):
    """Rejected /play request (HTTP 400)."""


def resolve_clip(clips_dir: str, raw_path: Any, max_bytes: int) -> tuple[str, int]:
    """Validate `raw_path`; returns (resolved real path, size)."""
    if not isinstance(raw_path, str) or not raw_path or len(raw_path) > 4096 or "\0" in raw_path:
        raise ClipError("path must be a non-empty string")
    clips_real = os.path.realpath(clips_dir)
    candidate = raw_path if os.path.isabs(raw_path) else os.path.join(clips_real, raw_path)
    real = os.path.realpath(candidate)             # resolves symlinks and ..
    if os.path.commonpath([clips_real, real]) != clips_real or real == clips_real:
        raise ClipError("path must be a regular file inside the clips directory")
    try:
        st = os.stat(real)
    except OSError:
        raise ClipError("path must be a regular file inside the clips directory") from None
    if not stat.S_ISREG(st.st_mode):
        raise ClipError("path must be a regular file inside the clips directory")
    if st.st_size <= 0 or st.st_size > max_bytes:
        raise ClipError(f"clip must be 1 byte .. {max_bytes} bytes")
    return real, st.st_size


class Clip:
    def __init__(self, clip_id: str, caption: str, max_seconds: float) -> None:
        self.id = clip_id
        self.caption = caption
        self.strip = build_caption_strip(caption)
        self.started = time.time()
        self.seconds: float | None = None            # planned play time
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_FRAMES)
        self.first: asyncio.Future = asyncio.get_running_loop().create_future()
        self.ready = False                           # first frame is queued
        self.last: bytes | None = None               # last frame shown (for repeats)
        self.ticks = 0                               # frames shown = wall-clock progress
        self.max_ticks = max(1, round(max_seconds * FPS))
        self.error: str | None = None
        self.stop_reason: str | None = None
        self.task: asyncio.Task | None = None


class CartoonFeed:
    def __init__(self, streamer_dir: str, poster: str | None = None, ffmpeg: str = "ffmpeg",
                 ffprobe: str = "ffprobe", max_seconds: float = MAX_CLIP_SECONDS,
                 max_bytes: int = MAX_CLIP_BYTES, log: Callable[..., None] = log_json) -> None:
        self.dir = os.path.abspath(streamer_dir)
        self.fifo_path = os.path.join(self.dir, "cartoon.mjpeg")
        self.clips_dir = os.path.join(self.dir, "cartoon", "clips")
        self.poster_path = poster or os.path.join(self.dir, "cartoon", "poster.jpg")
        self.ffmpeg, self.ffprobe = ffmpeg, ffprobe
        self.max_seconds, self.max_bytes = max_seconds, max_bytes
        self.log = log
        self.writer = FifoWriter(self.fifo_path, log=log)
        self.clip: Clip | None = None
        self._tick_task: asyncio.Task | None = None
        self._poster_key: tuple | None = None
        self._poster_jpeg: bytes = dark_frame_jpeg()
        self._poster_checked = 0.0

    # ----- lifecycle -----
    async def start(self) -> None:
        os.makedirs(self.clips_dir, exist_ok=True)
        ensure_fifo(self.fifo_path)
        self._tick_task = asyncio.create_task(self._tick_loop())

    async def close(self) -> None:
        if self._tick_task:
            self._tick_task.cancel()
            await asyncio.gather(self._tick_task, return_exceptions=True)
            self._tick_task = None
        clip = self.clip
        if clip:
            self._finish(clip, "shutdown")
            if clip.task:
                await asyncio.gather(clip.task, return_exceptions=True)
        self.writer.close()

    # ----- idle frame -----
    def idle_jpeg(self) -> bytes:
        """Poster (re-read when its mtime changes) or the dark fallback frame."""
        t = time.monotonic()
        if t - self._poster_checked >= 1.0:
            self._poster_checked = t
            try:
                st = os.stat(self.poster_path)
                key: tuple | None = (st.st_mtime_ns, st.st_size)
            except OSError:
                key = None
            if key != self._poster_key:
                self._poster_key = key
                self._poster_jpeg = (key and load_poster_jpeg(self.poster_path)) or dark_frame_jpeg()
        return self._poster_jpeg

    # ----- one tick: choose the frame to emit -----
    def next_frame(self) -> bytes:
        clip = self.clip
        if clip is None or not clip.ready:
            return self.idle_jpeg()
        try:
            item = clip.queue.get_nowait()
        except asyncio.QueueEmpty:
            item = _REPEAT                       # decoder lagging: repeat last frame
        if item is None:                         # decoder finished
            self._finish(clip, "error" if clip.error else "ended")
            return self.idle_jpeg()
        if item is not _REPEAT:
            clip.last = item
        clip.ticks += 1
        frame = clip.last or self.idle_jpeg()
        if clip.ticks >= clip.max_ticks:
            self._finish(clip, "max_seconds")
        return frame

    async def _tick_loop(self) -> None:
        loop = asyncio.get_running_loop()
        period = 1.0 / FPS
        next_t = loop.time()
        while True:
            try:
                self.writer.write_frame(self.next_frame())
            except Exception as e:               # never let the feed die
                self.log("error", where="tick", error=repr(e))
            next_t += period
            delay = next_t - loop.time()
            if delay < -0.25:                    # fell far behind: resync, don't burst
                next_t = loop.time()
                delay = 0
            await asyncio.sleep(max(0.0, delay))

    # ----- clip lifecycle -----
    def _finish(self, clip: Clip, reason: str) -> None:
        if self.clip is not clip:
            return
        self.clip = None
        clip.stop_reason = clip.stop_reason or reason
        if clip.task and not clip.task.done():
            clip.task.cancel()                   # decoder's finally kills ffmpeg
        fields = dict(id=clip.id, reason=reason, frames=clip.ticks,
                      seconds_played=round(clip.ticks / FPS, 2))
        if clip.error:
            fields["error"] = clip.error
        self.log("done", **fields)

    async def stop(self) -> str | None:
        clip = self.clip
        if clip is None:
            return None
        self._finish(clip, "stopped")
        if clip.task:
            await asyncio.gather(clip.task, return_exceptions=True)
        return clip.id

    async def _probe_seconds(self, path: str) -> float | None:
        exe = shutil.which(self.ffprobe)
        if not exe:
            return None
        try:
            p = await asyncio.create_subprocess_exec(
                exe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL)
            try:
                out, _ = await asyncio.wait_for(p.communicate(), 5)
            except asyncio.TimeoutError:
                p.kill()
                await p.wait()
                return None
            return float(out.decode().strip().splitlines()[0])
        except (OSError, ValueError, IndexError):
            return None

    async def play(self, clip_id: str, path: str, caption: str) -> Clip:
        """Start a clip.  Raises ClipError (400), BusyError (409), DecodeError (422)."""
        real, _size = resolve_clip(self.clips_dir, path, self.max_bytes)
        if self.clip is not None:
            raise BusyError(self.clip.id)
        clip = Clip(clip_id, sanitize_caption(caption), self.max_seconds)
        self.clip = clip                          # reserve synchronously (before any await)
        try:
            dur = await self._probe_seconds(real)
            clip.seconds = round(min(dur, self.max_seconds), 2) if dur is not None else None
            clip.task = asyncio.create_task(self._decode(clip, real))
            try:
                ok = await asyncio.wait_for(asyncio.shield(clip.first), FIRST_FRAME_TIMEOUT)
            except asyncio.TimeoutError:
                clip.error = clip.error or "timeout waiting for the first frame"
                ok = False
            if not ok:
                raise DecodeError(clip.error or clip.stop_reason or "no frames decoded")
        except BaseException:
            if self.clip is clip:
                self._finish(clip, "error" if clip.error else "aborted")
            raise
        self.log("play", id=clip.id, path=real, caption=clip.caption, seconds=clip.seconds)
        return clip

    async def _decode(self, clip: Clip, path: str) -> None:
        """ffmpeg -> raw rgb frames -> JPEG (thread) -> bounded queue."""
        proc = None
        stderr_tail = bytearray()

        async def drain(stream: asyncio.StreamReader) -> None:   # keep ffmpeg from blocking on stderr
            while chunk := await stream.read(4096):
                stderr_tail.extend(chunk)
                del stderr_tail[:-1500]

        drain_task = None
        try:
            vf = (f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease,"
                  f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,format=rgb24")
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg, "-nostdin", "-v", "error", "-protocol_whitelist", "file",
                "-i", path, "-t", f"{self.max_seconds:g}", "-an", "-sn", "-vf", vf,
                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, limit=4 * FRAME_BYTES)
            drain_task = asyncio.create_task(drain(proc.stderr))
            loop = asyncio.get_running_loop()
            while True:
                try:
                    raw = await proc.stdout.readexactly(FRAME_BYTES)
                except asyncio.IncompleteReadError:
                    break                          # EOF (a trailing partial frame is dropped)
                jpeg = await loop.run_in_executor(None, render_clip_frame, raw, clip.strip)
                await clip.queue.put(jpeg)
                if not clip.ready:
                    clip.ready = True
                    if not clip.first.done():
                        clip.first.set_result(True)
            rc = await proc.wait()
            if drain_task:
                await asyncio.gather(drain_task, return_exceptions=True)
            if rc != 0 or not clip.ready:
                tail = stderr_tail.decode("utf-8", "replace").strip().replace("\n", " | ")[-300:]
                clip.error = f"ffmpeg exit {rc}: {tail}" if tail else f"ffmpeg exit {rc}, no frames"
                self.log("error", where="decode", id=clip.id, error=clip.error)
            await clip.queue.put(None)             # sentinel: tick loop finishes the clip
        except asyncio.CancelledError:
            raise
        except Exception as e:
            clip.error = repr(e)
            self.log("error", where="decode", id=clip.id, error=clip.error)
            try:
                clip.queue.put_nowait(None)
            except asyncio.QueueFull:
                pass
        finally:
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
            if drain_task and not drain_task.done():
                drain_task.cancel()
            if not clip.first.done():
                clip.first.set_result(False)

    def state(self) -> dict[str, Any]:
        c = self.clip
        return {
            "playing": c.id if c else None,
            "started": round(c.started, 3) if c else None,
            "seconds": c.seconds if c else None,
            "frames_written": self.writer.frames_written,
            "clip_frames": c.ticks if c else 0,
            "reader": self.writer.reader,
            "dropped": self.writer.dropped,
        }


class BusyError(Exception):
    def __init__(self, playing: str) -> None:
        super().__init__("busy")
        self.playing = playing


class DecodeError(Exception):
    pass


# ----------------------------------------------------------------- HTTP app --
def make_app(feed: CartoonFeed, token: str) -> web.Application:
    token_bytes = token.encode("utf-8")
    if not token_bytes:
        raise ValueError("empty admin token")

    @web.middleware
    async def auth(request: web.Request, handler):
        if request.method == "GET" and request.path == "/healthz":
            return await handler(request)
        supplied = request.headers.get("X-Admin-Token", "").encode("utf-8")
        if not hmac.compare_digest(supplied, token_bytes):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        return await handler(request)

    async def healthz(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def play(request: web.Request) -> web.Response:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return web.json_response({"ok": False, "error": "body must be a JSON object"}, status=400)
        clip_id = sanitize_text(body.get("id"), MAX_ID)
        if not clip_id:
            return web.json_response({"ok": False, "error": "id must be a non-empty string"}, status=400)
        caption = body.get("caption", "")
        if caption is not None and not isinstance(caption, str):
            return web.json_response({"ok": False, "error": "caption must be a string"}, status=400)
        try:
            clip = await feed.play(clip_id, body.get("path"), caption or "")
        except ClipError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        except BusyError as e:
            return web.json_response({"ok": False, "error": "busy", "playing": e.playing}, status=409)
        except DecodeError as e:
            return web.json_response({"ok": False, "error": f"decode failed: {e}"}, status=422)
        return web.json_response({"ok": True, "id": clip.id, "seconds": clip.seconds,
                                  "caption": clip.caption})

    async def stop(_request: web.Request) -> web.Response:
        stopped = await feed.stop()
        return web.json_response({"ok": True, "stopped": stopped})

    async def state(_request: web.Request) -> web.Response:
        return web.json_response(feed.state())

    async def on_startup(_app: web.Application) -> None:
        await feed.start()

    async def on_cleanup(_app: web.Application) -> None:
        await feed.close()

    app = web.Application(middlewares=[auth], client_max_size=MAX_BODY)
    app.add_routes([web.get("/healthz", healthz), web.post("/play", play),
                    web.post("/stop", stop), web.get("/state", state)])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


# --------------------------------------------------------------------- main --
def read_token(path: str) -> str:
    st = os.stat(path)
    if st.st_mode & 0o077:
        log_json("warning", message="token file is accessible by group/others", path=path)
    with open(path, encoding="utf-8") as f:
        token = f.read().strip()
    if not token:
        raise SystemExit("token file is empty")
    return token


async def amain(args: argparse.Namespace) -> None:
    token = read_token(args.token_file)
    feed = CartoonFeed(args.streamer_dir, poster=args.poster, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
    app = make_app(feed, token)
    runner = web.AppRunner(app, access_log=None)     # no access log: keep headers out of logs
    await runner.setup()                             # runs on_startup -> feed.start()
    site = web.TCPSite(runner, "127.0.0.1", args.port)
    await site.start()
    log_json("start", port=args.port, fifo=feed.fifo_path, clips=feed.clips_dir,
             poster=feed.poster_path, fps=FPS, size=f"{W}x{H}")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    log_json("shutdown")
    await runner.cleanup()                           # on_cleanup -> feed.close() kills ffmpeg


def main() -> None:
    ap = argparse.ArgumentParser(description="SUB-01 cartoon mode MJPEG FIFO feeder (see module docstring)")
    ap.add_argument("--streamer-dir", required=True, help="directory holding cartoon.mjpeg and cartoon/")
    ap.add_argument("--token-file", required=True, help="file whose content is the X-Admin-Token secret")
    ap.add_argument("--port", type=int, default=8842, help="HTTP port on 127.0.0.1 (default 8842)")
    ap.add_argument("--poster", default=None, help="idle still (default <streamer-dir>/cartoon/poster.jpg)")
    ap.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg binary")
    ap.add_argument("--ffprobe", default="ffprobe", help="ffprobe binary (clip duration; optional)")
    args = ap.parse_args()
    try:
        asyncio.run(amain(args))
    except Exception as e:
        log_json("error", where="main", error=repr(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
