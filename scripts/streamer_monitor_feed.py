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
  restarts, last_error, display} (no secrets; loopback only).
`--test-source` captures lavfi testsrc2 instead of X (local tests). Not yet a streamer_up.py child: see RUNBOOK.md
"Monitor feed" for the command and for how to add it as a sixth service.
"""

import argparse
import asyncio
import errno
import fcntl
import os
import re
import select
import signal
import stat
import sys
import time
from collections import deque
from pathlib import Path

from aiohttp import web

DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
DEFAULT_PORT = 8840                 # 8838 is the Vagon runner
LOOPBACK = ("127.0.0.1", "::1", "localhost")
BACKOFF = (1, 2, 4, 8, 16, 30)
F_SETPIPE_SZ = getattr(fcntl, "F_SETPIPE_SZ", 1031)
PART = re.compile(rb"Content-length:\s*(\d+)\r\n\r\n", re.I)


def build_argv(args):
    source = (["-re", "-f", "lavfi", "-i", f"testsrc2=size={args.size}:rate={args.fps}"] if args.test_source else
              ["-thread_queue_size", "64", "-f", "x11grab", "-framerate", str(args.fps), "-draw_mouse", "0",
               "-i", args.display])
    width, height = args.size.split("x")
    return [args.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning", *source,
            "-vf", f"scale={width}:{height}", "-pix_fmt", "yuvj420p", "-c:v", "mjpeg", "-q:v", str(args.quality),
            "-f", "mpjpeg", "pipe:1"]


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


class MonitorFeed:
    def __init__(self, args, clock=time.monotonic, sleep=asyncio.sleep):
        self.args, self._clock, self._sleep = args, clock, sleep
        self.sink = FifoSink(Path(args.fifo), args.pipe_kb << 10, clock)
        self.proc, self.restarts, self.frames_in, self.last_error = None, 0, 0, None
        self._times = deque(maxlen=600)
        self._tail = deque(maxlen=20)
        self._stopping = asyncio.Event()

    def health(self):
        now = self._clock()
        recent = [t for t in self._times if now - t <= 5.0]
        return {"ok": True, "ffmpeg": self.proc is not None and self.proc.returncode is None,
                "reader": self.sink.reader_alive(), "frames_in": self.frames_in, "frames_written": self.sink.written,
                "frames_dropped": self.sink.dropped, "fps_in": round(len(recent) / 5.0, 1), "restarts": self.restarts,
                "last_error": self.last_error, "display": "lavfi" if self.args.test_source else self.args.display,
                "fifo": str(self.args.fifo)}

    def stop(self):
        self._stopping.set()

    async def _pause(self, seconds):
        try:
            await asyncio.wait_for(self._stopping.wait(), seconds)
        except asyncio.TimeoutError:
            pass
        return self._stopping.is_set()

    async def run(self):
        self.sink.ensure_fifo()
        failures = 0
        while not self._stopping.is_set():
            if not self.args.always and not (self.sink.reader_alive() or self.sink.try_open(force=True)):
                if await self._pause(0.5):
                    break
                continue
            started = self._clock()
            outcome = await self._run_ffmpeg()
            if outcome == "idle" or self._stopping.is_set():
                failures = 0
                continue
            failures = 0 if self._clock() - started >= 60 else failures + 1
            if await self._pause(BACKOFF[min(failures, len(BACKOFF)) - 1] if failures else 1.0):
                break
        self.sink.close()

    async def _run_ffmpeg(self):
        try:
            self.proc = await asyncio.create_subprocess_exec(
                *build_argv(self.args), stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
        except OSError as exc:
            self.last_error = f"cannot start ffmpeg: {exc}"
            return "crash"
        self.restarts += 1
        errors = asyncio.ensure_future(self._stderr(self.proc))
        reader, outcome, last_reader = PartReader(), "exit", self._clock()
        stopper = asyncio.ensure_future(self._stopping.wait())
        try:
            while True:
                chunk = asyncio.ensure_future(self.proc.stdout.read(65536))
                await asyncio.wait({chunk, stopper}, return_when=asyncio.FIRST_COMPLETED)
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
                    self.sink.offer(frame)
                if self.sink.fd is not None:
                    last_reader = self._clock()
                elif not self.args.always and self._clock() - last_reader > self.args.idle_stop:
                    outcome = "idle"
                    break
        finally:
            stopper.cancel()
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


async def serve(args):
    feed = MonitorFeed(args)
    app = web.Application()
    app.router.add_get("/healthz", lambda request: web.json_response(feed.health(), headers={"Cache-Control": "no-store"}))
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM"):
        loop.add_signal_handler(getattr(signal, name), feed.stop)
    print(f"SUB-01 monitor feed: {args.display if not args.test_source else 'lavfi'} -> {args.fifo} "
          f"({args.size} {args.fps} fps), health on http://{args.host}:{args.port}/healthz", flush=True)
    try:
        await feed.run()
    finally:
        await runner.cleanup()


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--streamer-dir", default=os.environ.get("STREAMER_DIR", DEFAULT_STREAMER_DIR))
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
    args = p.parse_args(argv)
    args.fifo = args.fifo or str(Path(args.streamer_dir) / "monitor.mjpeg")
    if not re.fullmatch(r":\d+(\.\d+)?", args.display):
        p.error("--display looks like :103")
    if not re.fullmatch(r"\d{2,4}x\d{2,4}", args.size) or not 1 <= args.fps <= 120 or not 2 <= args.quality <= 31:
        p.error("--size WxH, --fps 1-120, --quality 2-31")
    if not 64 <= args.pipe_kb <= 1024:
        p.error("--pipe-kb must be between 64 and 1024")
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
