#!/usr/bin/env python3
"""SUB-01 in-game monitor feed: an X display captured at 60 fps into an MJPEG FIFO that the game reads.

  ffmpeg -f x11grab -framerate 60 -draw_mouse 0 -i :103 -vf scale=1280:720 -pix_fmt yuvj420p -c:v mjpeg -q:v 5
         -f mpjpeg pipe:1

The script pumps whole JPEG frames from ffmpeg into `<streamer-dir>/monitor.mjpeg` (a FIFO it creates, mode 0600; the
FIFO carries plain concatenated JPEGs, like cam2.mjpeg):
- it never blocks: the FIFO is opened O_WRONLY|O_NONBLOCK (no reader: ENXIO, tried again every 0.5 s); a frame that
  does not fit in the pipe is dropped whole, and a frame the kernel took only in part is finished before the next one,
  so a connected reader sees whole JPEGs. Not across a reconnect or a crash: a reader that opens while the previous
  one left part of a frame in the pipe, or a feed that dies mid-frame, gives one truncated JPEG, so the game must
  resync on SOI (FF D8) like any MJPEG reader and read without blocking (the feed pauses without a reader, during
  backoff and after a crash). A vanished reader is noticed by poll() (POLLERR) even while nothing is written.
  The pipe is --pipe-kb large (about two frames: little latency);
- ffmpeg runs only while a reader exists (stopped after --idle-stop s without one, unless --always) and is restarted
  with backoff (1, 2, 4 ... 30 s) when it exits;
- ffmpeg writes mpjpeg (multipart with Content-length) on its stdout, so frames are cut by length, not by scanning
  JPEG markers;
- GET http://127.0.0.1:8840/healthz -> {ok, ffmpeg, reader, frames_in, frames_written, frames_dropped, fps_in,
  restarts, last_error, display, showing, screen_frames, neutral_frames, discarded_private, privacy{...}} (no secrets;
  loopback only); HTTP 503 with ok false while there is no neutral frame (see below).

Privacy gate (owner, 2026-10-23: SUB-01 may log in on his PC; the in-game monitor must never show a login or account
page; design reviewed with Kimi, docs/streamer/kimi/sidecars-design.md). The screen reaches the FIFO only while the
gate is open, and the gate fails closed:
- PRIVATE while the last line of <streamer-dir>/layout.jsonl is a privacy line (`"reason": "privacy"`, the agent's
  line on a login/account page; the director's rule) until a later valid line without it (a file that disappears or
  is emptied during a cut keeps the cut; with no cut seen, no file is no cut), while the file or its last line cannot
  be read or parsed; while the desktop runner's GET /pc/state (--desktop-url, token from SUB01_ADMIN_TOKEN or
  --token-file) says `privacy: true`, or, in the Vagon workstation kind, until `vagon.connected` is true AND the phase
  is `connected` (the Vagon host page's login, dashboard and account pages; stricter than the runner's own lock, which
  looks at `connected` only); while /pc/state cannot be read (no token, refused, unreachable, malformed, a redirect) or
  an answer is older than STALE_AFTER s; at start until both have answered; and while no neutral frame exists.
- Closing is immediate, in the same step as the observation: the tail of a partly written screen frame is dropped,
  the neutral grey frame (the runner's "PC not connected" grey, rendered with ffmpeg at the feed's size before any
  capture may start) is offered to the reader, no frame of the running capture is written any more and ffmpeg is told
  to stop; then the neutral frame every --neutral-interval s (sooner after a full pipe). `showing` is "neutral" only
  once a WHOLE neutral frame went into the FIFO for this cut (`privacy.neutral_ack` names the cut generation and the
  layout cut id), else "pending"; a new cut while already closed is a new generation (`cut_renewed`). Opening needs
  every check clean and fresh for --resume-after s; then a NEW ffmpeg is launched (a capture belongs to one open
  period), so nothing captured during the cut can come out of an old pipe. A privacy watcher that ends on its own
  closes the gate for good (`watcher_failed`) and fails /healthz, so the supervisor restarts the feed.
- `privacy_on`/`cut_renewed`/`privacy_off`/`watcher_failed` rows go to stdout (the supervisor's logs/monitor.log) and
  to <streamer-dir>/events.jsonl.
- ffmpeg gets our environment without the operator token or any key.
- Not covered: frames captured between a private page appearing and its privacy line (the agent sees the page first),
  what is already in the FIFO when the gate closes (up to the pipe size, --pipe-kb), the Vagon dashboard until the
  runner flips `vagon.connected` to false, and a feed that dies: the game keeps its last texture unless it has its own
  no-frame deadline.
`--test-source` captures lavfi testsrc2 instead of X (local tests); only there may `--no-privacy-gate` switch the gate
off. Supervised by scripts/streamer_up.py as the `monitor` service (RUNBOOK.md "Monitor feed").
"""

import argparse
import asyncio
import errno
import fcntl
import json
import os
import re
import select
import signal
import stat
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout, web

DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
DEFAULT_PORT = 8840                 # 8838 is the Vagon runner
DEFAULT_DESKTOP_URL = "http://127.0.0.1:8838"
LOOPBACK = ("127.0.0.1", "::1", "localhost")
LOCAL_URL = re.compile(r"http://(127\.0\.0\.1|localhost|\[::1\]):\d{1,5}")    # the token never leaves the machine
BACKOFF = (1, 2, 4, 8, 16, 30)
F_SETPIPE_SZ = getattr(fcntl, "F_SETPIPE_SZ", 1031)
PART = re.compile(rb"Content-length:\s*(\d+)\r\n\r\n", re.I)
MIN_TOKEN = 12
PRIVACY_REASON = "privacy"          # scripts/streamer_director.py privacy_cut(): the agent's line on a private page
LAYOUT_TAIL = 65536
NEUTRAL_COLOR = "0x484a4e"          # (72, 74, 78): the desktop runner's "PC not connected" grey
LAYOUT_INTERVAL = 0.25              # seconds between layout.jsonl reads
RUNNER_INTERVAL = 0.5               # seconds between GET /pc/state
RUNNER_TIMEOUT = 1.0
STALE_AFTER = 2.5                   # an answer older than this closes the gate (a hung poll, a blocked loop)
NEUTRAL_RETRY = 30.0                # seconds between attempts to render the neutral frame after a failure


def now_iso(unix=None):
    return datetime.fromtimestamp(time.time() if unix is None else unix, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_argv(args):
    source = (["-re", "-f", "lavfi", "-i", f"testsrc2=size={args.size}:rate={args.fps}"] if args.test_source else
              ["-thread_queue_size", "64", "-f", "x11grab", "-framerate", str(args.fps), "-draw_mouse", "0",
               "-i", args.display])
    width, height = args.size.split("x")
    return [args.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning", *source,
            "-vf", f"scale={width}:{height}", "-pix_fmt", "yuvj420p", "-c:v", "mjpeg", "-q:v", str(args.quality),
            "-f", "mpjpeg", "pipe:1"]


def neutral_argv(args):
    """One JPEG of the neutral grey at the feed's size and quality."""
    return [args.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-f", "lavfi",
            "-i", f"color=c={NEUTRAL_COLOR}:s={args.size}:r=1", "-frames:v", "1", "-pix_fmt", "yuvj420p",
            "-c:v", "mjpeg", "-q:v", str(args.quality), "-f", "mjpeg", "pipe:1"]


def is_jpeg(data):
    return isinstance(data, (bytes, bytearray)) and len(data) > 4 and data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9"


# ------------------------------------------------------------------ privacy signals

def read_layout(path, max_bytes=LAYOUT_TAIL):
    """The last line of layout.jsonl -> (state, privacy_id or None). Own reader: the director's read_tail_records() turns
    every OSError into "no lines", and here "no file" and "cannot read" must differ.

    "absent": no file, or no line in it (empty, truncated). "clean": a JSON object without `"reason": "privacy"`. "cut":
    the agent's privacy line (the director's privacy_cut rule: the line's layout does not matter). "unreadable": the
    file cannot be read (EACCES, EIO, a directory...) or its last line is not a JSON object (half-written, garbage)."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - max_bytes))
            data = handle.read()
    except FileNotFoundError:
        return "absent", None
    except OSError:
        return "unreadable", None
    lines = [line for line in data.split(b"\n") if line.strip()]
    if not lines:
        return "absent", None
    try:
        record = json.loads(lines[-1])
    except (ValueError, UnicodeDecodeError, RecursionError):
        record = None
    if not isinstance(record, dict):
        return "unreadable", None
    if record.get("reason") == PRIVACY_REASON:
        cut = record.get("privacy_id")
        return "cut", cut if isinstance(cut, str) and 0 < len(cut) <= 64 else None
    return "clean", None


class LayoutWatch:
    """layout.jsonl -> the gate's layout reason (None = clean) and the cut's privacy_id.

    A cut starts with a privacy line and ends ONLY with a later valid line without that reason. A file that disappears,
    is emptied or truncated during a cut keeps it (`layout_cut_gone`); without a cut seen, no file is no cut. An
    unreadable file or last line is private (`layout_unreadable`) and changes nothing else. A replaced file (new inode)
    is simply read: its last line decides, as for the director."""

    def __init__(self, path):
        self.path, self.in_cut, self.cut_id = Path(path), False, None

    def check(self):
        state, cut = read_layout(self.path)
        if state == "cut":
            self.in_cut, self.cut_id = True, cut
            return "layout_cut", cut
        if state == "clean":
            self.in_cut, self.cut_id = False, None
            return None, None
        if state == "unreadable":
            return "layout_unreadable", self.cut_id
        return ("layout_cut_gone", self.cut_id) if self.in_cut else (None, None)


def runner_privacy(view):
    """What the desktop runner's GET /pc/state means for the monitor -> reason or None (the screen may be shown).

    "runner_privacy": the runner's privacy flag (sources native/home). "vagon_not_connected": the Vagon workstation kind
    while the remote desktop is not connected (the host page shows the owner's login, dashboard or account pages). This
    is STRICTER than the runner's own privacy_locked() (`not vagon.connected`): the phase must say `connected` too.
    Anything not understood is "runner_bad_answer" (fail closed): an unknown pc_mode, a vagon mode without the `vagon`
    object, an unknown `kind`, a workstation without a boolean `connected` and a string `phase`. Only the public Vagon
    Streams kind and the pod's own Chromium have no account page of the owner's to hide."""
    if not isinstance(view, dict) or not isinstance(view.get("privacy"), bool):
        return "runner_bad_answer"
    if view["privacy"]:
        return "runner_privacy"
    mode = view.get("pc_mode")
    if mode == "chromium":
        return None
    if mode != "vagon" or not isinstance(view.get("vagon"), dict):
        return "runner_bad_answer"
    vagon = view["vagon"]
    kind = vagon.get("kind")
    if kind == "streams":
        return None
    if kind != "workstation" or not isinstance(vagon.get("connected"), bool) or not isinstance(vagon.get("phase"), str):
        return "runner_bad_answer"
    if vagon["connected"] and vagon["phase"] == "connected":
        return None
    return "vagon_not_connected"


class PrivacyGate:
    """Fail-closed gate over two polled sources ("layout", "runner"), each reporting a reason (private) or None (clean),
    plus holds set by the feed itself (`neutral_unavailable`: no screen without a neutral frame to cover it).

    Closed (private) at start until both answered clean; closes at once on any reason, hold, or answer older than
    `stale_after` (monotonic clock); opens only after every check has been clean for `resume_after` s without a break."""

    SOURCES = ("layout", "runner")

    def __init__(self, clock=time.monotonic, wall=time.time, resume_after=1.0, stale_after=STALE_AFTER, on_change=None):
        self._clock, self._wall = clock, wall
        self.resume_after, self.stale_after, self.on_change = resume_after, stale_after, on_change
        self.reason = {name: "starting" for name in self.SOURCES}
        self.answered = {name: None for name in self.SOURCES}
        self.holds = set()
        self.private, self.since_wall, self.clean_since = True, wall(), None
        self.cut_id, self.closes, self.reasons_now = None, 0, ["starting"]

    def observe(self, source, reason, cut_id=None):
        """A new layout cut (a privacy line after a non-cut state, or another privacy_id) while the gate is already
        closed fires `cut_renewed`, so the feed needs a new neutral acknowledgement for it (Kimi review)."""
        new_cut = source == "layout" and reason == "layout_cut" and (
            self.reason["layout"] != "layout_cut" or cut_id != self.cut_id)
        was_private = self.private
        self.reason[source], self.answered[source] = reason, self._clock()
        if source == "layout":
            self.cut_id = cut_id
        private = self.evaluate()
        if new_cut and was_private and private:
            self._changed("cut_renewed", self.reasons_now)
        return private

    def hold(self, reason, active=True):
        (self.holds.add if active else self.holds.discard)(reason)
        return self.evaluate()

    def current_reasons(self, now):
        reasons = {r for r in self.reason.values() if r} | self.holds
        for source, at in self.answered.items():
            if at is not None and now - at > self.stale_after:
                reasons.add(f"{source}_stale")
        return sorted(reasons)

    def evaluate(self):
        now = self._clock()
        self.reasons_now = reasons = self.current_reasons(now)
        if reasons:
            self.clean_since = None
            if not self.private:
                self.private, self.since_wall, self.closes = True, self._wall(), self.closes + 1
                self._changed("privacy_on", reasons)
        else:
            if self.clean_since is None:
                self.clean_since = now
            if self.private and now - self.clean_since >= self.resume_after:
                seconds = round(self._wall() - self.since_wall, 1)
                self.private, self.since_wall = False, self._wall()
                self._changed("privacy_off", [], seconds=seconds)
        return self.private

    def _changed(self, kind, reasons, **extra):
        if self.on_change:
            self.on_change(kind, reasons, **extra)

    def public(self):
        now = self._clock()
        return {"private": self.private, "reasons": list(self.reasons_now), "since": now_iso(self.since_wall),
                "layout_cut_id": self.cut_id, "closes": self.closes,
                "last_runner_ok_age_s": (round(now - self.answered["runner"], 1)
                                         if self.answered["runner"] is not None and self.reason["runner"] is None else None)}


def child_env(environ=None):
    """ffmpeg's environment: ours without the operator token or any key (ffmpeg calls no API)."""
    environ = os.environ if environ is None else environ
    return {k: v for k, v in environ.items()
            if k != "SUB01_ADMIN_TOKEN" and not k.endswith(("_API_KEY", "_TOKEN", "_SECRET"))}


class RunnerRefused(Exception):
    """GET /pc/state answered 401/403: a wrong or missing operator token."""


def read_token(args, environ=None):
    """The operator token for GET /pc/state: --token-file, else SUB01_ADMIN_TOKEN. None when missing or too short.
    Never printed or logged."""
    environ = os.environ if environ is None else environ
    try:
        text = Path(args.token_file).read_text().strip() if args.token_file else environ.get("SUB01_ADMIN_TOKEN", "").strip()
    except OSError:
        return None
    return text if len(text) >= MIN_TOKEN else None


# ------------------------------------------------------------------ FIFO

class PartReader:
    """Cuts ffmpeg's mpjpeg stream ("Content-length: N\\r\\n\\r\\n" + N bytes per part) into JPEG frames."""

    def __init__(self, limit=8 << 20):
        self.buf, self.limit = bytearray(), limit

    def feed(self, data):
        self.buf += data
        frames = []
        while True:
            m = PART.search(self.buf)
            if not m:
                if len(self.buf) > self.limit:            # no header in 8 MB: garbage, keep only a possible header start
                    del self.buf[:-64]
                return frames
            start = m.end()
            size = int(m.group(1))
            if len(self.buf) < start + size:
                return frames
            frames.append(bytes(self.buf[start:start + size]))
            del self.buf[:start + size]


class FifoSink:
    """Whole frames into a FIFO without ever blocking the capture."""

    def __init__(self, path, pipe_bytes=256 << 10, clock=time.monotonic, retry=0.5):
        self.path, self.pipe_bytes, self._clock, self.retry = Path(path), pipe_bytes, clock, retry
        self.fd, self.pending, self._tried = None, b"", -1e9
        self.written = self.dropped = 0

    def ensure_fifo(self):
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.mkfifo(self.path, 0o600)
            return
        if not stat.S_ISFIFO(st.st_mode):
            raise ValueError(f"{self.path} exists and is not a FIFO")

    def try_open(self, force=False):
        """-> True when a reader is there (the open succeeds); retried at most every `retry` s."""
        if self.fd is not None:
            return True
        now = self._clock()
        if not force and now - self._tried < self.retry:
            return False
        self._tried = now
        try:
            self.fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno not in (errno.ENXIO, errno.ENOENT):
                raise
            return False
        try:
            fcntl.fcntl(self.fd, F_SETPIPE_SZ, self.pipe_bytes)
        except OSError:
            pass                                          # above /proc/sys/fs/pipe-max-size: keep the default
        return True

    def reader_alive(self):
        """poll() reports POLLERR on a pipe's write end once no reader is left: notice it without writing."""
        if self.fd is None:
            return False
        poller = select.poll()
        poller.register(self.fd, select.POLLOUT)
        if any(events & (select.POLLERR | select.POLLHUP) for _, events in poller.poll(0)):
            self.close()
            return False
        return True

    def offer(self, frame):
        """Write one frame or drop it whole. -> True when written (maybe with a tail still pending)."""
        if not self.try_open() or (self.pending and not self._write_pending()):
            self.dropped += 1
            return False
        try:
            n = os.write(self.fd, frame)
        except BlockingIOError:
            self.dropped += 1
            return False
        except OSError:                                   # EPIPE: the reader went away
            self.close()
            self.dropped += 1
            return False
        self.pending = frame[n:]
        self.written += 1
        return True

    def drop_pending(self):
        """Forget the unwritten tail of a frame (the privacy gate closed): the reader resyncs on the next SOI."""
        dropped, self.pending = bool(self.pending), b""
        return dropped

    def flush(self):
        """Finish a pending tail if the pipe takes it. -> True when nothing is pending (a reader must be connected)."""
        if self.fd is None:
            return False
        return not self.pending or self._write_pending()

    def _write_pending(self):
        try:
            n = os.write(self.fd, self.pending)
        except BlockingIOError:
            return False
        except OSError:
            self.close()
            return False
        self.pending = self.pending[n:]
        return not self.pending

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd, self.pending = None, b""                 # a new reader never gets the tail of an old frame


# ------------------------------------------------------------------ the feed

class MonitorFeed:
    """`fetch_state`: async () -> the runner's /pc/state dict (raises when it cannot be read); default an aiohttp GET.
    `neutral`: the neutral JPEG (default rendered with ffmpeg at start; until it exists the gate holds closed and
    health is not ok: no screen capture without a picture to cover it). No gate only with --test-source."""

    def __init__(self, args, clock=time.monotonic, sleep=asyncio.sleep, wall=time.time, fetch_state=None, neutral=None,
                 token=None, events_path=None, log=None):
        self.args, self._clock, self._sleep, self._wall = args, clock, sleep, wall
        self.sink = FifoSink(Path(args.fifo), args.pipe_kb << 10, clock)
        self.proc, self.restarts, self.frames_in, self.last_error = None, 0, 0, None
        self._times = deque(maxlen=600)
        self._tail = deque(maxlen=20)
        self._stopping = asyncio.Event()
        self._gate_closed, self._gate_open = asyncio.Event(), asyncio.Event()
        self.gated = not getattr(args, "no_privacy_gate", False)
        self.gate = PrivacyGate(clock, wall, args.resume_after, on_change=self._gate_changed) if self.gated else None
        self.layout = LayoutWatch(Path(args.streamer_dir) / "layout.jsonl")
        self.token, self._fetch, self._session = token, fetch_state, None
        self.neutral, self._neutral_tried = (neutral if is_jpeg(neutral) else None), -1e9
        self.screen_frames = self.neutral_frames = self.discarded = 0
        # cut generation: 1 for the closed gate at start, +1 at every close and every renewed cut; the ack names the
        # generation (and the layout cut id seen) for which a WHOLE neutral frame was completed in the FIFO after the
        # cut was observed (completion based: a neutral tail pending at a renewal may have begun before it)
        self.cut_gen, self.neutral_ack, self._next_neutral = 1, None, 0.0
        self.watcher_failed = None
        self.events_path = events_path
        self._log = log or (lambda line: print(line, flush=True))
        self._tasks = []
        if self.gated:
            self._gate_closed.set()
            if self.neutral is None:
                self.gate.hold("neutral_unavailable")
        else:
            self._gate_open.set()

    # -- reporting
    def showing(self):
        """screen: the gate lets the screen through. neutral: private, and a whole neutral frame went into the FIFO for
        this cut. pending: private, no whole neutral frame written yet for this cut (no reader, a full pipe, no neutral
        frame at all): the game may still hold an older picture."""
        if not self.gated or not self.gate.private:
            return "screen"
        return "neutral" if self.neutral_ack and self.neutral_ack["gen"] == self.cut_gen else "pending"

    def ok(self):
        return not (self.gated and (self.neutral is None or self.watcher_failed))

    def health(self):
        now = self._clock()
        recent = [t for t in self._times if now - t <= 5.0]
        privacy = {"private": False, "gate": "off (test source)"}
        if self.gated:
            privacy = dict(self.gate.public(), cut_gen=self.cut_gen,
                           neutral_ack=dict(self.neutral_ack) if self.neutral_ack else None)
        return {"ok": self.ok(), "ffmpeg": self.proc is not None and self.proc.returncode is None,
                "reader": self.sink.reader_alive(), "frames_in": self.frames_in, "frames_written": self.sink.written,
                "frames_dropped": self.sink.dropped, "fps_in": round(len(recent) / 5.0, 1), "restarts": self.restarts,
                "last_error": self.last_error, "display": "lavfi" if self.args.test_source else self.args.display,
                "fifo": str(self.args.fifo), "showing": self.showing(), "screen_frames": self.screen_frames,
                "neutral_frames": self.neutral_frames, "discarded_private": self.discarded, "privacy": privacy}

    def event(self, kind, **fields):
        record = {"t": now_iso(self._wall()), "source": "monitor_feed", "kind": kind, **fields}
        line = json.dumps(record, separators=(",", ":"))
        self._log(line)
        if self.events_path:
            try:
                fd = os.open(self.events_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.write(fd, (line + "\n").encode())
                finally:
                    os.close(fd)
            except OSError:
                pass

    def _gate_changed(self, kind, reasons, **extra):
        """Runs synchronously inside the observation that changed the gate (no await in between): on closing, the
        screen frame's unwritten tail is dropped and the neutral frame goes out in the same step, before ffmpeg is
        even told to stop."""
        if kind == "privacy_on":
            self._gate_open.clear()
            self._gate_closed.set()
            self.cut_gen, self.neutral_ack, self._next_neutral = self.cut_gen + 1, None, 0.0
            self.sink.drop_pending()
            self._deliver_neutral()
        elif kind == "cut_renewed":                       # already closed: only a new ack is needed (a neutral tail
            self.cut_gen, self.neutral_ack, self._next_neutral = self.cut_gen + 1, None, 0.0   # may be pending: kept)
            self._deliver_neutral()
        else:
            self._gate_closed.clear()
            self._gate_open.set()
        self.event(kind, reasons=reasons, privacy_id=self.gate.cut_id, **extra)

    def _deliver_neutral(self):
        """Write (or finish) a neutral frame. -> True once a WHOLE neutral frame is in the FIFO; then the ack names this
        cut. Best effort: no reader or a full pipe means it is retried, never claimed."""
        now = self._clock()
        if self.neutral is None or not (self.sink.reader_alive() or self.sink.try_open()):
            self._next_neutral = now + 0.5
            return False
        if self.sink.pending:                             # only a neutral tail can be pending while private; its last
            done = self.sink.flush()                      # byte lands now, so the reader cannot have it any earlier
        else:
            done = self.sink.offer(self.neutral) and not self.sink.pending
        if done:
            self.neutral_frames += 1                      # whole neutral frames in the FIFO
            self.neutral_ack = {"gen": self.cut_gen, "privacy_id": self.gate.cut_id, "t": now_iso(self._wall()),
                                "reasons": list(self.gate.reasons_now)}
            self._next_neutral = now + self.args.neutral_interval
        else:
            self._next_neutral = now + 0.05                # a full pipe: try again soon
        return done

    def private_now(self):
        return self.gated and self.gate.private

    def stop(self):
        self._stopping.set()

    async def _pause(self, seconds, wake=None):
        """Sleep up to `seconds`, or until stopping (-> True) or `wake` is set."""
        waits = [asyncio.ensure_future(self._stopping.wait())]
        if wake is not None:
            waits.append(asyncio.ensure_future(wake.wait()))
        try:
            await asyncio.wait(waits, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in waits:
                task.cancel()
        return self._stopping.is_set()

    # -- privacy watchers
    async def _watch_layout(self):
        while not self._stopping.is_set():
            try:
                reason, cut = self.layout.check()
            except Exception:                             # never a dead watcher: anything unexpected is private
                reason, cut = "layout_unreadable", self.layout.cut_id
            self.gate.observe("layout", reason, cut)
            if await self._pause(LAYOUT_INTERVAL):
                return

    async def runner_reason(self):
        """One GET /pc/state -> the runner's privacy reason, or None when the screen may be shown."""
        if self.token is None and self._fetch is None:
            return "no_token"
        try:
            return runner_privacy(await asyncio.wait_for(self._fetch_state(), RUNNER_TIMEOUT))
        except RunnerRefused:
            return "runner_refused"
        except (asyncio.TimeoutError, ClientError, OSError):
            return "runner_unreachable"
        except Exception:                                 # bad JSON, an unexpected shape or error: private
            return "runner_bad_answer"

    async def _watch_runner(self):
        while not self._stopping.is_set():
            self.gate.observe("runner", await self.runner_reason())
            if await self._pause(RUNNER_INTERVAL):
                return

    async def _fetch_state(self):
        if self._fetch is not None:
            return await self._fetch()
        if self._session is None:
            self._session = ClientSession(timeout=ClientTimeout(total=RUNNER_TIMEOUT))
        url = self.args.desktop_url.rstrip("/") + "/pc/state"
        async with self._session.get(url, headers={"X-Admin-Token": self.token}, allow_redirects=False) as resp:
            if resp.status in (401, 403):
                raise RunnerRefused(f"http {resp.status}")
            if resp.status != 200:
                raise ValueError(f"http {resp.status}")
            try:
                return await resp.json(content_type=None)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("not JSON") from exc

    async def _tick_gate(self):
        """Re-evaluate every LAYOUT_INTERVAL: an answer that stops coming closes the gate (stale)."""
        while not self._stopping.is_set():
            self.gate.evaluate()
            if await self._pause(LAYOUT_INTERVAL):
                return

    async def _render_neutral(self):
        self._neutral_tried = self._clock()
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(*neutral_argv(self.args), stdin=asyncio.subprocess.DEVNULL,
                                                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                        env=child_env())
            out, err = await asyncio.wait_for(proc.communicate(), 20)
        except (OSError, asyncio.TimeoutError) as exc:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            self.last_error = f"cannot render the neutral frame: {type(exc).__name__}"
            return None
        if proc.returncode != 0 or not is_jpeg(out):
            self.last_error = "cannot render the neutral frame: " + err.decode("utf-8", "replace").strip()[-200:]
            return None
        return out

    async def _ensure_neutral(self):
        """Render the neutral frame; only then may the gate open (the hold `neutral_unavailable` is lifted)."""
        self.neutral = await self._render_neutral()
        if self.neutral is not None:
            self.gate.hold("neutral_unavailable", False)

    # -- main loop
    def _watcher_done(self, name):
        """A privacy watcher that ends on its own (it should only end when the feed stops) closes the gate for good
        (hold `watcher_failed`: neutral frames go on) and makes /healthz fail, so the supervisor restarts the feed."""
        def done(task):
            if self._stopping.is_set():                   # shutdown: run() sets it before cancelling the watchers
                return
            exc = None if task.cancelled() else task.exception()
            why = "CancelledError" if task.cancelled() else type(exc).__name__ if exc else "returned"
            self.watcher_failed = name
            self.last_error = f"privacy watcher {name} ended: {why}"
            self.gate.hold("watcher_failed")
            self.event("watcher_failed", watcher=name, error=None if why == "returned" else why)
        return done

    async def run(self):
        self.sink.ensure_fifo()
        if self.gated:
            self._tasks = []
            for name, watcher in (("layout", self._watch_layout), ("runner", self._watch_runner),
                                  ("tick", self._tick_gate)):
                task = asyncio.ensure_future(watcher())
                task.add_done_callback(self._watcher_done(name))
                self._tasks.append(task)
            if self.neutral is None:
                await self._ensure_neutral()
        failures = 0
        try:
            while not self._stopping.is_set():
                if self.private_now():
                    await self._private_phase()
                    continue
                if not self.args.always and not (self.sink.reader_alive() or self.sink.try_open(force=True)):
                    if await self._pause(0.5, self._gate_closed if self.gated else None):
                        break
                    continue
                started = self._clock()
                outcome = await self._run_ffmpeg()
                if outcome in ("idle", "private") or self._stopping.is_set():
                    failures = 0
                    continue
                failures = 0 if self._clock() - started >= 60 else failures + 1
                if await self._pause(BACKOFF[min(failures, len(BACKOFF)) - 1] if failures else 1.0,
                                     self._gate_closed if self.gated else None):
                    break
        finally:
            self._stopping.set()                          # before the cancel: an expected end, not watcher_failed
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            if self._session is not None:
                await self._session.close()
            self.sink.close()

    async def _private_phase(self):
        """While the gate is closed: no capture; the neutral frame to a reader (the close already sent one, see
        _gate_changed) every --neutral-interval s, retried soon after a full pipe, at once for a new reader."""
        while self.private_now() and not self._stopping.is_set():
            if self.neutral is None:
                if self._clock() - self._neutral_tried >= NEUTRAL_RETRY:
                    await self._ensure_neutral()
            elif self._clock() >= self._next_neutral:
                self._deliver_neutral()
            wait = self._next_neutral - self._clock() if self.neutral is not None else 0.5
            if await self._pause(max(0.02, wait), self._gate_open):
                return

    async def _run_ffmpeg(self):
        gen = self.cut_gen                                # this capture belongs to one open period of the gate

        def blocked():                                    # closed now, or closed (and maybe reopened) since launch
            return self.private_now() or self.cut_gen != gen

        try:
            self.proc = await asyncio.create_subprocess_exec(
                *build_argv(self.args), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, env=child_env())
        except OSError as exc:
            self.last_error = f"cannot start ffmpeg: {exc}"
            return "crash"
        self.restarts += 1
        errors = asyncio.ensure_future(self._stderr(self.proc))
        reader, outcome, last_reader = PartReader(), "exit", self._clock()
        stopper = asyncio.ensure_future(self._stopping.wait())
        closed = asyncio.ensure_future(self._gate_closed.wait()) if self.gated else None
        try:
            while True:
                chunk = asyncio.ensure_future(self.proc.stdout.read(65536))
                await asyncio.wait({chunk, stopper} | ({closed} if closed else set()),
                                   return_when=asyncio.FIRST_COMPLETED)
                if blocked() or (closed is not None and closed.done()):   # the gate closed since launch: done
                    chunk.cancel()
                    outcome = "private"
                    break
                if not chunk.done():
                    chunk.cancel()
                    outcome = "stop"
                    break
                data = chunk.result()
                if not data:
                    break
                for frame in reader.feed(data):
                    self.frames_in += 1
                    self._times.append(self._clock())
                    if blocked():
                        self.discarded += 1
                        continue
                    if self.sink.offer(frame):
                        self.screen_frames += 1
                if blocked():
                    outcome = "private"
                    break
                if self.sink.fd is not None:
                    last_reader = self._clock()
                elif not self.args.always and self._clock() - last_reader > self.args.idle_stop:
                    outcome = "idle"
                    break
        finally:
            stopper.cancel()
            if closed:
                closed.cancel()
            await self._terminate(self.proc)
            await asyncio.gather(errors, return_exceptions=True)
        if outcome == "exit":
            self.last_error = f"ffmpeg exited with code {self.proc.returncode}: " + " | ".join(list(self._tail)[-2:])
            print(self.last_error[:400], flush=True)
        return outcome

    async def _stderr(self, proc):
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                self._tail.append(text)

    @staticmethod
    async def _terminate(proc, grace=3.0):
        if proc.returncode is None:
            try:
                proc.send_signal(signal.SIGINT)
                await asyncio.wait_for(proc.wait(), grace)
            except ProcessLookupError:
                pass
            except asyncio.TimeoutError:
                proc.kill()
        await proc.wait()


def create_app(feed):
    async def healthz(request):                   # 503 without a neutral frame: the supervisor sees a broken feed
        health = feed.health()
        return web.json_response(health, status=200 if health["ok"] else 503, headers={"Cache-Control": "no-store"})

    app = web.Application()
    app.router.add_get("/healthz", healthz)
    return app


async def serve(args):
    token = read_token(args)
    feed = MonitorFeed(args, token=token, events_path=Path(args.streamer_dir) / "events.jsonl")
    runner = web.AppRunner(create_app(feed), access_log=None)
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        loop.add_signal_handler(getattr(signal, name), feed.stop)
    gate = (f"privacy gate on ({args.streamer_dir}/layout.jsonl + {args.desktop_url}/pc/state)" if feed.gated
            else "privacy gate OFF (test source)")
    print(f"SUB-01 monitor feed: {args.display if not args.test_source else 'lavfi'} -> {args.fifo} "
          f"({args.size} {args.fps} fps), {gate}, health on http://{args.host}:{args.port}/healthz", flush=True)
    if feed.gated and token is None:
        print("WARNING no operator token (SUB01_ADMIN_TOKEN or --token-file): /pc/state cannot be read, so the gate "
              "stays closed and the in-game monitor shows only the neutral picture", flush=True)
    try:
        await feed.run()
    finally:
        await runner.cleanup()


def parse_args(argv=None, environ=None):
    environ = os.environ if environ is None else environ
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--streamer-dir", default=environ.get("STREAMER_DIR", DEFAULT_STREAMER_DIR))
    p.add_argument("--fifo", help="default <streamer-dir>/monitor.mjpeg")
    p.add_argument("--display", default=":103", help="X display to capture")
    p.add_argument("--fps", type=int, default=60)
    p.add_argument("--size", default="1280x720")
    p.add_argument("--quality", type=int, default=5, help="mjpeg -q:v (2 best .. 31 worst)")
    p.add_argument("--pipe-kb", type=int, default=256, help="FIFO buffer size (latency vs dropped frames)")
    p.add_argument("--idle-stop", type=float, default=10.0, help="stop ffmpeg after this long without a reader")
    p.add_argument("--always", action="store_true", help="capture even without a reader")
    p.add_argument("--ffmpeg", default="ffmpeg")
    p.add_argument("--host", default="127.0.0.1", choices=LOOPBACK)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--test-source", action="store_true", help="lavfi testsrc2 instead of x11grab")
    p.add_argument("--desktop-url", default=environ.get("STREAMER_DESKTOP_URL", DEFAULT_DESKTOP_URL),
                   help="the desktop runner whose GET /pc/state gates the screen (loopback http only)")
    p.add_argument("--token-file", help="operator token file (else SUB01_ADMIN_TOKEN); never printed")
    p.add_argument("--resume-after", type=float, default=1.0,
                   help="seconds every privacy check must be clean before the screen comes back")
    p.add_argument("--neutral-interval", type=float, default=0.5, help="seconds between neutral frames while private")
    p.add_argument("--no-privacy-gate", action="store_true", help="only with --test-source (local tests)")
    args = p.parse_args(argv)
    args.fifo = args.fifo or str(Path(args.streamer_dir) / "monitor.mjpeg")
    if not re.fullmatch(r":\d+(\.\d+)?", args.display):
        p.error("--display looks like :103")
    if not re.fullmatch(r"\d{2,4}x\d{2,4}", args.size) or not 1 <= args.fps <= 120 or not 2 <= args.quality <= 31:
        p.error("--size WxH, --fps 1-120, --quality 2-31")
    if not 64 <= args.pipe_kb <= 1024:
        p.error("--pipe-kb must be between 64 and 1024")
    if not LOCAL_URL.fullmatch(args.desktop_url.rstrip("/")):
        p.error("--desktop-url must be http://127.0.0.1:PORT (or localhost, [::1]): the token never leaves the machine")
    if not 0.0 <= args.resume_after <= 60.0 or not 0.1 <= args.neutral_interval <= 10.0:
        p.error("--resume-after 0-60, --neutral-interval 0.1-10")
    if args.no_privacy_gate and not args.test_source:
        p.error("--no-privacy-gate is accepted only with --test-source: a real display is always gated")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
