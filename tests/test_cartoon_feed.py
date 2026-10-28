"""Tests for scripts/cartoon_feed.py (no pytest-asyncio needed: each test drives
its own event loop with asyncio.run).  Clip tests need the ffmpeg binary and are
skipped without it."""
import asyncio
import contextlib
import errno
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cartoon_feed.py"
spec = importlib.util.spec_from_file_location("cartoon_feed", SCRIPT)
cf = importlib.util.module_from_spec(spec)
sys.modules["cartoon_feed"] = cf
spec.loader.exec_module(cf)

TOKEN = "s3cret-test-token"
AUTH = {"X-Admin-Token": TOKEN}
HAVE_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg not installed")


@pytest.fixture(scope="session")
def test_mp4(tmp_path_factory):
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg not installed")
    p = tmp_path_factory.mktemp("mp4") / "test.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30",
                    "-t", "2", "-pix_fmt", "yuv420p", "-y", str(p)], check=True)
    return p


@contextlib.asynccontextmanager
async def running(tmp_path, **kw):
    """Feed + app + test client; yields (feed, client, log_events)."""
    events = []
    feed = cf.CartoonFeed(str(tmp_path), log=lambda ev, **f: events.append({"event": ev, **f}), **kw)
    client = TestClient(TestServer(cf.make_app(feed, TOKEN)))
    async with client:
        yield feed, client, events


def run(coro):
    return asyncio.run(coro)


def put_clip(tmp_path, mp4, name="a.mp4"):
    clips = tmp_path / "cartoon" / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    dst = clips / name
    shutil.copyfile(mp4, dst)
    return dst


def assert_frame(jpeg: bytes):
    im = Image.open(io.BytesIO(jpeg))
    assert im.format == "JPEG" and im.size == (1280, 720)
    return im


# ------------------------------------------------------------------ helpers --
def test_sanitize_caption():
    s = cf.sanitize_caption("  hi\x00 there\n\tfriend\x1b[31m!  ")
    assert s == "hi there friend [31m!"
    assert cf.sanitize_caption("x" * 500) == "x" * 80
    assert cf.sanitize_caption(None) == "" and cf.sanitize_caption(123) == ""
    assert all(c.isprintable() for c in cf.sanitize_caption("a\x07b\r\nc\x7fd"))


def test_idle_frames_dark_and_poster(tmp_path):
    async def go():
        async with running(tmp_path) as (feed, _c, _e):
            im = assert_frame(feed.idle_jpeg())          # no poster -> dark frame
            assert im.convert("RGB").getpixel((5, 5))[0] < 40
    run(go())
    poster = tmp_path / "cartoon" / "poster.jpg"
    Image.new("RGB", (640, 360), (250, 0, 0)).save(poster)  # 16:9, different size

    async def go2():
        async with running(tmp_path) as (feed, _c, _e):
            im = assert_frame(feed.idle_jpeg()).convert("RGB")
            r, g, b = im.getpixel((640, 360))
            assert r > 200 and g < 60 and b < 60
    run(go2())


def test_caption_bar_burnt_into_bottom():
    white = bytes([255]) * cf.FRAME_BYTES
    strip = cf.build_caption_strip("Hello cartoon")
    assert strip is not None and cf.build_caption_strip("") is None
    im = assert_frame(cf.render_clip_frame(white, strip)).convert("RGB")
    assert im.getpixel((5, 5))[0] > 240                  # top untouched
    assert im.getpixel((5, 715))[0] < 140                # semi-transparent dark bar
    long = cf.build_caption_strip("word " * 16)           # 80 chars -> may wrap, must fit
    assert long is not None and long[0].height <= 140 and long[1] + long[0].height == 720


# ---------------------------------------------------------------------- HTTP --
def test_auth_required(tmp_path):
    async def go():
        async with running(tmp_path) as (_f, c, _e):
            assert (await c.get("/healthz")).status == 200            # open
            for method, path in (("get", "/state"), ("post", "/play"), ("post", "/stop")):
                assert (await getattr(c, method)(path)).status == 401
                r = await getattr(c, method)(path, headers={"X-Admin-Token": "wrong"})
                assert r.status == 401
            assert (await c.get("/state", headers=AUTH)).status == 200
    run(go())


def test_play_path_validation(tmp_path):
    clips = tmp_path / "cartoon" / "clips"
    clips.mkdir(parents=True)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x" * 100)
    (clips / "link.mp4").symlink_to(outside)
    (clips / "sub").mkdir()
    (clips / "big.mp4").write_bytes(b"x" * 2000)

    async def go():
        async with running(tmp_path, max_bytes=1000) as (feed, c, _e):
            async def play(path):
                r = await c.post("/play", json={"id": "t", "path": path, "caption": ""}, headers=AUTH)
                return r.status
            assert await play(str(outside)) == 400                     # outside clips/
            assert await play(str(clips / ".." / "outside.mp4")) == 400  # traversal
            assert await play(str(clips / "link.mp4")) == 400          # symlink escaping clips/
            assert await play(str(clips / "sub")) == 400               # directory
            assert await play(str(clips / "missing.mp4")) == 400
            assert await play(str(clips)) == 400
            assert await play(str(clips / "big.mp4")) == 400           # over size limit
            assert await play("") == 400 and await play(None) == 400
            r = await c.post("/play", data=b"not json", headers=AUTH)
            assert r.status == 400
            r = await c.post("/play", json={"path": str(clips / "big.mp4")}, headers=AUTH)
            assert r.status == 400                                     # id missing
            assert feed.clip is None
    run(go())


@needs_ffmpeg
def test_play_409_state_stop_and_done(tmp_path, test_mp4):
    clip = put_clip(tmp_path, test_mp4)

    async def go():
        async with running(tmp_path) as (feed, c, events):
            r = await c.post("/play", headers=AUTH, json={
                "id": "one", "path": str(clip), "caption": "Hi\x00 there\n" + "x" * 200})
            assert r.status == 200, await r.text()
            body = await r.json()
            assert body["ok"] and body["id"] == "one"
            assert body["caption"].startswith("Hi there xxx") and len(body["caption"]) == 80
            assert body["seconds"] is None or 1.5 < body["seconds"] <= 2.1

            r = await c.post("/play", headers=AUTH, json={"id": "two", "path": str(clip)})
            assert r.status == 409                                    # busy

            st = await (await c.get("/state", headers=AUTH)).json()
            assert st["playing"] == "one" and st["started"] and st["reader"] is False
            assert st["dropped"] > 0                                  # no reader: dropped, not blocked

            await asyncio.sleep(0.5)
            r = await c.post("/stop", headers=AUTH)
            assert (await r.json()) == {"ok": True, "stopped": "one"}
            st = await (await c.get("/state", headers=AUTH)).json()
            assert st["playing"] is None
            assert [e["event"] for e in events if e["event"] in ("play", "done")] == ["play", "done"]
            assert next(e for e in events if e["event"] == "done")["reason"] == "stopped"
            assert (await (await c.post("/stop", headers=AUTH)).json())["stopped"] is None

            # a second clip plays to its natural end and returns to idle
            r = await c.post("/play", headers=AUTH, json={"id": "three", "path": "a.mp4"})  # relative
            assert r.status == 200
            deadline = time.monotonic() + 6
            while feed.clip is not None and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            assert feed.clip is None
            done = [e for e in events if e["event"] == "done"][-1]
            assert done["reason"] == "ended" and 50 <= done["frames"] <= 62
    run(go())


@needs_ffmpeg
def test_max_seconds_cuts_clip(tmp_path, test_mp4):
    clip = put_clip(tmp_path, test_mp4)

    async def go():
        async with running(tmp_path, max_seconds=0.5) as (feed, c, events):
            r = await c.post("/play", headers=AUTH, json={"id": "cut", "path": str(clip)})
            assert r.status == 200
            for _ in range(60):
                if feed.clip is None:
                    break
                await asyncio.sleep(0.1)
            done = [e for e in events if e["event"] == "done"][-1]
            assert done["reason"] in ("max_seconds", "ended") and done["frames"] <= 16
    run(go())


@needs_ffmpeg
def test_undecodable_clip_is_422(tmp_path):
    clips = tmp_path / "cartoon" / "clips"
    clips.mkdir(parents=True)
    (clips / "junk.mp4").write_bytes(b"this is not a video" * 10)

    async def go():
        async with running(tmp_path) as (feed, c, _e):
            r = await c.post("/play", headers=AUTH, json={"id": "j", "path": "junk.mp4"})
            assert r.status == 422
            assert feed.clip is None                                  # slot released
    run(go())


# ---------------------------------------------------------------------- FIFO --
def make_fifo(tmp_path):
    p = str(tmp_path / "t.mjpeg")
    cf.ensure_fifo(p)
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
    return p


def test_fifo_writer_drops_without_reader(tmp_path):
    p = make_fifo(tmp_path)
    logs = []
    w = cf.FifoWriter(p, log=lambda ev, **f: logs.append(ev))
    frame = b"\xff\xd8\xff" + b"0" * 200_000
    t0 = time.monotonic()
    results = [w.write_frame(frame) for _ in range(300)]
    assert time.monotonic() - t0 < 1.0                               # never blocks
    assert not any(results) and w.dropped == 300 and w.frames_written == 0 and not w.reader
    assert logs == []                                                # ENXIO is silent


def test_fifo_writer_reader_attach_slow_reader_and_detach(tmp_path):
    p = make_fifo(tmp_path)
    logs = []
    now = [100.0]
    w = cf.FifoWriter(p, log=lambda ev, **f: logs.append(ev), clock=lambda: now[0])
    frame = b"\xff\xd8\xff" + b"1" * 100_000
    assert w.write_frame(frame) is False                             # nobody reading yet
    rfd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
    assert w.write_frame(frame) is False                             # open retried only once per second
    now[0] += 1.1
    assert w.write_frame(frame) is True and w.reader                 # attached, 100 KB fits in 1 MiB pipe
    assert logs == ["reader_attached"]
    # reader never reads: the pipe fills, frames get dropped, memory stays bounded
    t0 = time.monotonic()
    for _ in range(100):
        w.write_frame(frame)
    assert time.monotonic() - t0 < 1.0
    assert w.dropped > 0 and len(w.pending) <= len(frame)
    # reader drains: pending tail is flushed first so the byte stream stays frame-aligned
    data = b""
    while True:
        try:
            chunk = os.read(rfd, 1 << 20)
        except BlockingIOError:
            break
        if not chunk:
            break
        data += chunk
    w.write_frame(frame)
    w.write_frame(frame)
    while True:
        try:
            chunk = os.read(rfd, 1 << 20)
        except BlockingIOError:
            break
        data += chunk
    assert data.count(b"\xff\xd8\xff") == w.frames_written          # only complete frames, aligned
    assert len(data) >= w.frames_written * len(frame) and data.startswith(b"\xff\xd8\xff")
    # reader goes away -> EPIPE -> detached, then reattach works
    os.close(rfd)
    w.write_frame(frame)
    assert not w.reader and logs[-1] == "reader_detached"
    rfd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
    now[0] += 1.1
    assert w.write_frame(frame) is True and w.reader
    assert logs[-2:] == ["reader_detached", "reader_attached"]
    os.close(rfd)
    w.close()


def test_feed_writes_valid_frames_to_fifo(tmp_path):
    async def go():
        async with running(tmp_path) as (feed, c, _e):
            rfd = os.open(feed.fifo_path, os.O_RDONLY | os.O_NONBLOCK)
            data = b""
            deadline = time.monotonic() + 5
            while data.count(b"\xff\xd8\xff") < 4 and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                try:
                    data += os.read(rfd, 1 << 22)
                except BlockingIOError:
                    pass
            st = await (await c.get("/state", headers=AUTH)).json()
            os.close(rfd)
            assert st["reader"] is True and st["frames_written"] >= 3
            first = data.split(b"\xff\xd8\xff")[1]
            assert_frame(b"\xff\xd8\xff" + first)                    # complete 1280x720 JPEG
    run(go())
