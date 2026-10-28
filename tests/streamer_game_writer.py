"""Test helper: the offscreen game's side of the main-view contract (docs/streamer/SAWTOOTH-20261024.md, "Structural
fix" step 3), for the director's fifo-mode tests. Not imported by any service.

GameWriter creates `main.mjpeg` (a FIFO, mode 0600) unless it exists, opens it O_WRONLY|O_NONBLOCK (retrying while
ENXIO: no reader), writes whole baseline JPEGs that carry a `seq=<n>` COM segment under poll() with a per-frame deadline
(a frame that cannot be written in time is discarded and counted, the fd closed and opened again, its tail never resumed),
and renames `main.json` into place several times a second (sequence, fps, written, the drop counters, last_write_utc).
Modes: "run" (write at `fps`), "stall" (keep the FIFO open, write nothing; main.json keeps coming with an old
last_write_utc), "gone" (close the FIFO, stop main.json: a game that exited).
"""
import errno
import json
import os
import select
import struct
import subprocess
import threading
import time
from pathlib import Path


def strip_com(jpeg):
    """A JPEG without its COM segments (ffmpeg writes its own `Lavc...` comment)."""
    out, i = bytearray(jpeg[:2]), 2
    while i + 4 <= len(jpeg):
        marker = jpeg[i + 1]
        if marker == 0xDA:
            out += jpeg[i:]
            break
        length = struct.unpack(">H", jpeg[i + 2:i + 4])[0]
        if marker != 0xFE:
            out += jpeg[i:i + 2 + length]
        i += 2 + length
    return bytes(out)


def with_seq(jpeg, seq):
    """The JPEG with one COM segment `seq=<n>` right after its APP0 (JFIF) segment."""
    com = b"seq=%d" % seq
    cut = 4 + struct.unpack(">H", jpeg[4:6])[0]
    return jpeg[:cut] + b"\xff\xfe" + struct.pack(">H", len(com) + 2) + com + jpeg[cut:]


def make_jpegs(ffmpeg, directory, size="320x180", count=30):
    """`count` distinct test-pattern JPEGs (full-range yuvj420p, like the game's), without COM segments."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc2=size={size}:rate=30", "-frames:v", str(count), "-q:v", "5",
                    str(directory / "f%03d.jpg")], check=True, timeout=60)
    return [strip_com((directory / f"f{i:03d}.jpg").read_bytes()) for i in range(1, count + 1)]


class GameWriter:
    def __init__(self, streamer_dir, frames, fps=30, deadline=0.5, json_period=0.25):
        self.dir = Path(streamer_dir)
        self.fifo, self.status = self.dir / "main.mjpeg", self.dir / "main.json"
        self.frames, self.fps, self.deadline, self.json_period = frames, fps, deadline, json_period
        self.mode, self.fd = "run", None
        self.seq = self.written = self.discarded = self.noreader = self.opens = 0
        self.last_write = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="game-writer", daemon=True)
        self._lock = threading.Lock()

    def start(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        if not self.fifo.exists():
            os.mkfifo(self.fifo, 0o600)
        self._thread.start()
        return self

    def set_mode(self, mode):
        assert mode in ("run", "stall", "gone")
        with self._lock:
            self.mode = mode

    def stop(self):
        self._stop.set()
        self._thread.join(5)
        self._close()

    def _close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def _open(self):
        try:
            self.fd = os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
            self.opens += 1
        except OSError as exc:
            if exc.errno != errno.ENXIO:
                raise
            self.fd = None

    def _write_frame(self):
        data = memoryview(with_seq(self.frames[self.seq % len(self.frames)], self.seq))
        end = time.monotonic() + self.deadline
        while data:
            left = end - time.monotonic()
            if left <= 0 or not select.select([], [self.fd], [], left)[1]:
                self.discarded += 1                      # cut or never started: the whole frame is dropped
                self._close()
                return False
            try:
                data = data[os.write(self.fd, data):]
            except BlockingIOError:
                continue
            except OSError:                              # EPIPE: the reader went away
                self.discarded += 1
                self._close()
                return False
        self.written += 1
        self.last_write = time.time()
        return True

    def _json(self):
        tmp = self.status.with_name("main.json.tmp")
        tmp.write_text(json.dumps({"schema": "sub01.streamer-main-status.test", "sequence": self.seq, "fps": self.fps,
                                   "written": self.written, "dropped_slots": 0, "dropped_encode": 0,
                                   "dropped_queue": 0, "dropped_noreader": self.noreader,
                                   "frames_discarded_midwrite": self.discarded, "pipe_size": 65536,
                                   "last_write_utc": self.last_write}))
        os.replace(tmp, self.status)

    def _loop(self):
        start, tick, next_json = time.monotonic(), 0, 0.0
        while not self._stop.is_set():
            with self._lock:
                mode = self.mode
            now = time.monotonic()
            if mode == "gone":
                self._close()
            else:
                if mode == "run":
                    if self.fd is None:
                        self._open()
                    if self.fd is None:
                        self.noreader += 1
                    else:
                        self._write_frame()
                    self.seq += 1
                if now >= next_json:
                    self._json()
                    next_json = now + self.json_period
            tick += 1
            delay = start + tick / self.fps - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                start, tick = time.monotonic(), 0
