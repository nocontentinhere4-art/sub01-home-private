"""In-game monitor feed: the privacy gate (owner, 2026-10-23: SUB-01 may log in on his PC; the in-game monitor must
never show a login or account page).

The gate fails closed: the screen reaches monitor.mjpeg only while the last layout.jsonl line is not a privacy line and
the desktop runner's /pc/state says neither `privacy` nor (Vagon workstation) a remote desktop that is not connected.
The FIFO/mpjpeg basics are tested in test_streamer_director.py (section "in-game monitor feed").
"""

import asyncio
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "operator-credential-test"


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module                       # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


mon = load("streamer_monitor_feed_gate", "scripts/streamer_monitor_feed.py")
director = load("streamer_director_for_monitor", "scripts/streamer_director.py")
desktop = load("streamer_desktop_for_monitor", "scripts/streamer_desktop.py")
FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")
NEUTRAL = b"\xff\xd8" + b"neutral-grey" * 20 + b"\xff\xd9"
PID = "p7-c0ffee"


def privacy_line(pid=PID, layout="webcam"):
    return {"t": "2026-10-24T15:00:00Z", "unix": 1.0, "layout": layout, "reason": "privacy", "why": "login page",
            "previous": "room", "source": "streamer_agent", "privacy_id": pid}


def end_line(pid=PID, layout="room"):
    return {"t": "2026-10-24T15:01:00Z", "unix": 2.0, "layout": layout, "reason": "privacy_end", "privacy_id": pid,
            "source": "streamer_agent"}


def append(path, record):
    with open(path, "a") as handle:
        handle.write(json.dumps(record) + "\n")


def run(coro):
    return asyncio.run(coro)


async def until(predicate, timeout=5.0):
    end = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < end, "condition never became true"
        await asyncio.sleep(0.01)


def read_all(fd):
    out = b""
    while True:
        try:
            chunk = os.read(fd, 1 << 20)
        except BlockingIOError:
            return out
        if not chunk:
            return out
        out += chunk


def jpegs(data):
    """Whole JPEGs in a byte stream (a leading piece that does not start at an SOI is left out)."""
    pieces = data.split(b"\xff\xd8")
    return [b"\xff\xd8" + piece for piece in pieces[1:]]


# ------------------------------------------------------------------ layout.jsonl

def test_read_layout_tells_absent_clean_cut_and_unreadable_apart(tmp_path):
    path = tmp_path / "layout.jsonl"
    assert mon.read_layout(path) == ("absent", None)                      # no file: no cut ever started
    path.write_text("")
    assert mon.read_layout(path) == ("absent", None)
    append(path, {"layout": "desktop"})
    assert mon.read_layout(path) == ("clean", None)
    append(path, privacy_line())
    assert mon.read_layout(path) == ("cut", PID)
    append(path, privacy_line(pid="x" * 65, layout="no-such-layout"))     # the layout name does not matter
    assert mon.read_layout(path) == ("cut", None)
    append(path, end_line())
    assert mon.read_layout(path) == ("clean", None)
    with open(path, "a") as handle:                                       # a half-written last line: fail closed
        handle.write('{"layout": "webcam", "reason": "priv')
    assert mon.read_layout(path) == ("unreadable", None)
    with open(path, "a") as handle:                                       # the writer finishes its line
        handle.write('acy", "privacy_id": "p8-1"}\n')
    assert mon.read_layout(path) == ("cut", "p8-1")
    with open(path, "a") as handle:
        handle.write("not json\n")
    assert mon.read_layout(path) == ("unreadable", None)                 # garbage is not the end of a cut
    path.write_text("[1, 2]\n")
    assert mon.read_layout(path) == ("unreadable", None)
    path.write_text(json.dumps({"layout": "webcam"}) + "\n" + "x" * 70000 + "\n" + json.dumps(privacy_line()) + "\n\n")
    assert mon.read_layout(path) == ("cut", PID)                          # only the tail is read, blank lines skipped
    assert mon.read_layout(tmp_path) == ("unreadable", None)              # a directory: cannot be read


def test_a_cut_ends_only_with_a_valid_line_not_with_a_vanished_file(tmp_path):
    path = tmp_path / "layout.jsonl"
    watch = mon.LayoutWatch(path)
    assert watch.check() == (None, None)                                  # no file, no cut seen: clean
    append(path, privacy_line())
    assert watch.check() == ("layout_cut", PID)
    path.unlink()                                                         # deleted during the cut
    assert watch.check() == ("layout_cut_gone", PID)
    path.write_text("")                                                   # recreated empty / truncated
    assert watch.check() == ("layout_cut_gone", PID)
    path.write_text("half a li")
    assert watch.check() == ("layout_unreadable", PID)
    replacement = tmp_path / "new.jsonl"                                  # rotated: a new inode, its last line decides
    replacement.write_text(json.dumps(end_line()) + "\n")
    os.replace(replacement, path)
    assert watch.check() == (None, None) and watch.in_cut is False
    path.unlink()
    assert watch.check() == (None, None)                                  # no cut in force: no file is no cut


def test_layout_reading_agrees_with_the_directors_privacy_cut(tmp_path):
    path = tmp_path / "layout.jsonl"
    records = [privacy_line(), end_line(), {"layout": "webcam", "reason": "privacy"}, {"reason": "PRIVACY"},
               {"layout": "split"}, {"layout": "webcam", "reason": "privacy_end_operator", "privacy_id": PID},
               {"reason": "privacy", "reasserted_by": "director", "privacy_id": PID}, {}]
    for record in records:
        path.write_text(json.dumps(record) + "\n")
        assert (mon.read_layout(path)[0] == "cut") == (director.privacy_cut(record) is not None), record
    assert mon.PRIVACY_REASON == director.PRIVACY_REASON


# ------------------------------------------------------------------ /pc/state

def vagon(kind="workstation", connected=True, phase="connected"):
    return {"privacy": False, "pc_mode": "vagon", "vagon": {"kind": kind, "connected": connected, "phase": phase}}


def test_runner_privacy_mirrors_the_runners_own_lock():
    assert mon.runner_privacy({"privacy": False, "pc_mode": "chromium"}) is None
    assert mon.runner_privacy({"privacy": True, "paused": True}) == "runner_privacy"       # bathroom privacy
    assert mon.runner_privacy(vagon()) is None
    for phase in ("login_required", "dashboard", "starting", "connecting", "ended", "blocked", "opening", "blank"):
        assert mon.runner_privacy(vagon(connected=False, phase=phase)) == "vagon_not_connected", phase
    assert mon.runner_privacy(vagon(connected=True, phase="login_required")) == "vagon_not_connected"
    assert mon.runner_privacy(vagon(connected=False, phase="connected")) == "vagon_not_connected"
    assert mon.runner_privacy(vagon(kind="streams", connected=False, phase="busy")) is None  # public link: no account
    for bad in (None, [], {}, {"privacy": "no"}, {"privacy": False}, {"privacy": False, "pc_mode": "other"},
                {"privacy": False, "pc_mode": "vagon"}, {"privacy": False, "pc_mode": "vagon", "vagon": "x"},
                vagon(connected="yes"), vagon(phase=None), vagon(kind=None), vagon(kind="studio"),
                {"privacy": False, "pc_mode": "vagon", "vagon": {"kind": "workstation"}}):
        assert mon.runner_privacy(bad) == "runner_bad_answer", bad


class StubDesk:
    """Just enough of the runner's Desktop for Runner.view() (as in test_streamer_desktop_vagon.py)."""

    def __init__(self, mode, kind="workstation"):
        self.status, self.restarts, self.error = "ready", 0, ""
        self.feed = desktop.FrameFeed(epoch="abc123")
        self.cfg = SimpleNamespace(pc_mode=mode, vagon_kind=kind, allow_credentials=True, operator_console=False)
        self.vagon = desktop.VagonState("none", kind=kind)

    def display(self):
        return self.feed.display()

    def operator_allowed(self):
        return not self.vagon.connected

    async def release_inputs(self):
        pass


def make_args(tmp_path, *extra, environ=None):
    return mon.parse_args(["--streamer-dir", str(tmp_path), *extra], environ=environ or {})


def test_the_real_runner_state_drives_the_gate_through_http(tmp_path):
    """Contract with scripts/streamer_desktop.py: the real Runner and app answer GET /pc/state with the token."""
    async def body():
        out = {}
        for mode, kind in (("chromium", "workstation"), ("vagon", "workstation"), ("vagon", "streams")):
            desk = StubDesk(mode, kind)
            runner = desktop.Runner(desk, TOKEN, desktop.Events(tmp_path / "e.jsonl"))
            server = TestServer(desktop.create_app(runner), host="127.0.0.1")
            await server.start_server()
            try:
                url = f"http://127.0.0.1:{server.port}"
                feed = mon.MonitorFeed(make_args(tmp_path, "--desktop-url", url), token=TOKEN, neutral=NEUTRAL)
                first = await feed.runner_reason()
                desk.vagon.connected = True
                desk.vagon.set_phase("connected")
                connected = await feed.runner_reason()
                await runner.set_privacy(True, "native")
                bathroom = await feed.runner_reason()
                await runner.set_privacy(False, "native")
                wrong = mon.MonitorFeed(make_args(tmp_path, "--desktop-url", url), token="not-the-operator-token",
                                        neutral=NEUTRAL)
                refused = await wrong.runner_reason()
                for f in (feed, wrong):
                    if f._session is not None:
                        await f._session.close()
                out[(mode, kind)] = (first, connected, bathroom, refused)
            finally:
                await server.close()
        nobody = mon.MonitorFeed(make_args(tmp_path, "--desktop-url", "http://127.0.0.1:9"), token=TOKEN, neutral=NEUTRAL)
        unreachable = await nobody.runner_reason()
        await nobody._session.close()
        no_token = await mon.MonitorFeed(make_args(tmp_path), token=None, neutral=NEUTRAL).runner_reason()
        return out, unreachable, no_token

    out, unreachable, no_token = run(body())
    assert out[("chromium", "workstation")] == (None, None, "runner_privacy", "runner_refused")
    assert out[("vagon", "workstation")] == ("vagon_not_connected", None, "runner_privacy", "runner_refused")
    assert out[("vagon", "streams")] == (None, None, "runner_privacy", "runner_refused")
    assert unreachable == "runner_unreachable" and no_token == "no_token"


def test_the_runner_answer_is_checked_and_the_token_never_follows_a_redirect(tmp_path):
    from aiohttp import web
    seen, current = [], {}

    async def state(request):
        seen.append(request.headers.get("X-Admin-Token"))
        mode = current["mode"]
        if mode == "redirect":
            raise web.HTTPFound("http://127.0.0.1:9/pc/state")
        if mode == "text":
            return web.Response(text="<html>not json</html>")
        if mode == "500":
            return web.Response(status=500)
        return web.json_response({"privacy": False, "pc_mode": "chromium"})

    async def body():
        app = web.Application()
        app.router.add_get("/pc/state", state)
        server = TestServer(app, host="127.0.0.1")
        await server.start_server()
        feed = mon.MonitorFeed(make_args(tmp_path, "--desktop-url", f"http://127.0.0.1:{server.port}/"), token=TOKEN,
                               neutral=NEUTRAL)
        try:
            out = {}
            for mode in ("ok", "redirect", "text", "500"):
                current["mode"] = mode
                out[mode] = await feed.runner_reason()
            return out
        finally:
            await feed._session.close()
            await server.close()

    assert run(body()) == {"ok": None, "redirect": "runner_bad_answer", "text": "runner_bad_answer",
                           "500": "runner_bad_answer"}
    assert seen == [TOKEN] * 4                                            # one request each, none to the redirect target


# ------------------------------------------------------------------ the gate

class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_gate_is_closed_at_start_closes_at_once_and_opens_only_after_a_clean_hold():
    clock, changes = Clock(), []
    gate = mon.PrivacyGate(clock, clock, resume_after=1.0, stale_after=2.5,
                           on_change=lambda kind, reasons, **extra: changes.append((kind, reasons, extra)))
    assert gate.private and gate.reasons_now == ["starting"]
    assert gate.observe("layout", None) is True                          # the runner has not answered yet
    assert gate.reasons_now == ["starting"]
    assert gate.observe("runner", None) is True                          # clean from now: 1 s to go
    clock.t += 0.6
    assert gate.evaluate() is True
    clock.t += 0.4
    assert gate.evaluate() is False and changes == [("privacy_off", [], {"seconds": 1.0})]
    assert gate.observe("layout", "layout_cut", PID) is True              # closes at once
    assert changes[-1] == ("privacy_on", ["layout_cut"], {}) and gate.cut_id == PID and gate.closes == 1
    clock.t += 0.1
    gate.observe("layout", None)
    clock.t += 0.5
    gate.observe("runner", "runner_unreachable")                         # a flap restarts the hold
    clock.t += 0.1
    gate.observe("runner", None)
    clock.t += 0.9
    assert gate.evaluate() is True
    clock.t += 0.1
    assert gate.evaluate() is False and changes[-1][0] == "privacy_off"
    clock.t += 2.6                                                        # no answers: both sources stale
    assert gate.evaluate() is True and gate.reasons_now == ["layout_stale", "runner_stale"]
    public = gate.public()
    assert public["private"] is True and public["reasons"] == ["layout_stale", "runner_stale"]
    assert public["closes"] == 2 and public["since"].endswith("Z") and public["layout_cut_id"] is None
    gate.observe("runner", "vagon_not_connected")
    assert gate.reasons_now == ["layout_stale", "vagon_not_connected"] and gate.public()["last_runner_ok_age_s"] is None


def test_a_hold_keeps_the_gate_closed_whatever_the_sources_say():
    clock = Clock()
    gate = mon.PrivacyGate(clock, clock, resume_after=0.5)
    gate.hold("neutral_unavailable")
    gate.observe("layout", None)
    gate.observe("runner", None)
    clock.t += 5
    gate.observe("layout", None)
    gate.observe("runner", None)
    assert gate.private and gate.reasons_now == ["neutral_unavailable"]
    gate.hold("neutral_unavailable", False)                              # lifted: the clean hold starts now
    clock.t += 0.4
    assert gate.evaluate() is True
    clock.t += 0.1
    assert gate.evaluate() is False


# ------------------------------------------------------------------ the feed while private

def test_while_private_only_neutral_frames_reach_the_fifo_and_nothing_is_captured(tmp_path):
    state = {"privacy": True}

    async def fetch():
        return dict(state)

    args = make_args(tmp_path, "--ffmpeg", str(tmp_path / "no-ffmpeg"), "--neutral-interval", "0.1")
    lines = []

    async def body():
        feed = mon.MonitorFeed(args, fetch_state=fetch, neutral=NEUTRAL, log=lines.append,
                               events_path=tmp_path / "events.jsonl")
        task = asyncio.ensure_future(feed.run())
        await until(lambda: Path(args.fifo).exists())
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        data = b""
        try:
            end = asyncio.get_running_loop().time() + 1.2
            while asyncio.get_running_loop().time() < end:
                data += read_all(reader)
                await asyncio.sleep(0.02)
            health = feed.health()
        finally:
            os.close(reader)
            feed.stop()
            await asyncio.wait_for(task, 10)
        return data, health

    data, health = run(body())
    frames = jpegs(data)
    assert len(frames) >= 5 and set(frames) == {NEUTRAL} and data.startswith(b"\xff\xd8")
    assert health["ok"] is True and health["restarts"] == 0 and health["ffmpeg"] is False and health["screen_frames"] == 0
    assert health["showing"] == "neutral" and health["neutral_frames"] >= 5
    privacy = health["privacy"]
    assert privacy["private"] is True and privacy["reasons"] == ["runner_privacy"]
    assert privacy["neutral_ack"]["gen"] == privacy["cut_gen"] == 1 and privacy["neutral_ack"]["reasons"] == ["runner_privacy"]
    assert TOKEN not in json.dumps(health)


def test_without_a_token_the_screen_is_never_shown(tmp_path, capsys):
    args = make_args(tmp_path, "--ffmpeg", str(tmp_path / "no-ffmpeg"))

    async def body():
        feed = mon.MonitorFeed(args, token=None, neutral=NEUTRAL, log=lambda line: None)
        task = asyncio.ensure_future(feed.run())
        await asyncio.sleep(1.5)
        health = feed.health()
        feed.stop()
        await asyncio.wait_for(task, 10)
        return health

    health = run(body())
    assert health["privacy"]["private"] is True and health["privacy"]["reasons"] == ["no_token"]
    assert health["restarts"] == 0 and health["showing"] == "pending"     # no reader: nothing written, nothing claimed


def test_without_a_neutral_frame_nothing_is_captured_even_when_everything_is_clean(tmp_path):
    """Kimi B3: no screen capture before a neutral frame exists to cover it (the game keeps its last texture)."""
    args = make_args(tmp_path, "--ffmpeg", str(tmp_path / "no-ffmpeg"), "--neutral-interval", "0.1",
                     "--resume-after", "0")

    async def fetch():
        return {"privacy": False, "pc_mode": "chromium"}

    async def body():
        feed = mon.MonitorFeed(args, fetch_state=fetch, log=lambda line: None)
        task = asyncio.ensure_future(feed.run())
        await until(lambda: Path(args.fifo).exists())
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            await asyncio.sleep(0.8)
            data, health = read_all(reader), feed.health()
            http = TestClient(TestServer(mon.create_app(feed)))
            await http.start_server()
            try:
                response = await http.get("/healthz")
                status, body = response.status, await response.json()
            finally:
                await http.close()
        finally:
            os.close(reader)
            feed.stop()
            await asyncio.wait_for(task, 10)
        return data, health, status, body

    data, health, status, body = run(body())
    assert data == b"" and health["restarts"] == 0 and health["ffmpeg"] is False
    assert health["ok"] is False and health["showing"] == "pending" and "neutral frame" in health["last_error"]
    assert health["privacy"]["reasons"] == ["neutral_unavailable"]
    assert status == 503 and body["ok"] is False


def test_healthz_is_200_with_a_neutral_frame(tmp_path):
    async def body():
        feed = mon.MonitorFeed(make_args(tmp_path), token=None, neutral=NEUTRAL)
        http = TestClient(TestServer(mon.create_app(feed)))
        await http.start_server()
        try:
            response = await http.get("/healthz")
            return response.status, response.headers["Cache-Control"], await response.json()
        finally:
            await http.close()

    status, cache, health = run(body())
    assert status == 200 and cache == "no-store" and health["ok"] is True and health["showing"] == "pending"
    assert health["privacy"]["reasons"] == ["starting"] and health["privacy"]["neutral_ack"] is None


def test_the_neutral_ack_needs_a_whole_frame_in_the_fifo_and_names_the_cut(tmp_path):
    big = b"\xff\xd8" + b"g" * 200_000 + b"\xff\xd9"                        # more than the 64 KB pipe
    args = make_args(tmp_path, "--pipe-kb", "64")
    clock = Clock()

    async def body():
        feed = mon.MonitorFeed(args, clock=clock, wall=clock, token=None, neutral=big, log=lambda line: None)
        feed.sink.ensure_fifo()
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        out = {}
        try:
            out["first"], out["partial"] = feed._deliver_neutral(), feed.showing()
            got = read_all(reader)
            while not feed._deliver_neutral():
                got += read_all(reader)
            out["got"], out["done"], out["ack"] = got + read_all(reader), feed.showing(), dict(feed.neutral_ack)
            out["frames_after_first"] = feed.neutral_frames
            feed.gate.observe("layout", None)
            feed.gate.observe("runner", None)
            clock.t += 1.0
            feed.gate.evaluate()
            out["opened"] = feed.showing() == "screen"
            feed.gate.observe("layout", "layout_cut", "p9-new")             # a new cut: closes, neutral at once
            out["gen"], out["ack_at_close"] = feed.cut_gen, feed.neutral_ack
            while not feed._deliver_neutral():
                read_all(reader)
            out["ack_new"] = dict(feed.neutral_ack)
        finally:
            os.close(reader)
            feed.sink.close()
        return out

    out = run(body())
    assert out["first"] is False and out["partial"] == "pending"          # the kernel took only a part: not claimed
    assert out["got"] == big and out["done"] == "neutral" and out["frames_after_first"] == 1   # counted when whole
    assert out["ack"]["gen"] == 1 and out["ack"]["privacy_id"] is None and out["ack"]["reasons"] == ["starting"]
    assert out["opened"] and out["gen"] == 2
    assert out["ack_at_close"] is None                                    # 200 KB never fits at once: not claimed
    assert out["ack_new"]["gen"] == 2 and out["ack_new"]["privacy_id"] == "p9-new"
    assert out["ack_new"]["reasons"] == ["layout_cut"]


def test_a_new_cut_while_already_private_needs_a_new_ack(tmp_path):
    """Kimi review M1: cut A -> clean line -> cut B while the runner keeps the gate closed must not keep A's ack."""
    args = make_args(tmp_path)
    clock, changes = Clock(), []

    async def body():
        feed = mon.MonitorFeed(args, clock=clock, wall=clock, token=None, neutral=NEUTRAL,
                               log=lambda line: changes.append(json.loads(line)["kind"]))
        feed.sink.ensure_fifo()
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        out = []
        try:
            feed.gate.observe("runner", "vagon_not_connected")           # closed for another reason throughout
            assert feed._deliver_neutral()
            out.append((feed.cut_gen, feed.showing(), feed.neutral_ack["privacy_id"]))
            feed.gate.observe("layout", "layout_cut", "pA")               # a cut while closed: renewed and acked
            out.append((feed.cut_gen, feed.showing(), feed.neutral_ack["privacy_id"]))
            feed.gate.observe("layout", "layout_cut", "pA")               # the same line again: nothing new
            feed.gate.observe("layout", None)                             # A ends, the gate stays closed
            out.append((feed.cut_gen, feed.showing(), feed.neutral_ack["privacy_id"]))
            filler = b"\xff\xd8" + b"f" * 300_000 + b"\xff\xd9"          # a full pipe when B starts
            feed.sink.offer(filler)
            feed.gate.observe("layout", "layout_cut", None)               # B, without an id: still a new cut
            out.append((feed.cut_gen, feed.showing(), feed.neutral_ack))
            while not feed._deliver_neutral():
                read_all(reader)
            out.append((feed.cut_gen, feed.showing(), feed.neutral_ack["privacy_id"]))
        finally:
            os.close(reader)
            feed.sink.close()
        return out

    out = run(body())
    assert out[0] == (1, "neutral", None)
    assert out[1] == (2, "neutral", "pA")
    assert out[2] == (2, "neutral", "pA")
    assert out[3] == (3, "pending", None)                                 # the old ack does not cover B
    assert out[4] == (3, "neutral", None)
    assert changes.count("cut_renewed") == 2 and "privacy_on" not in changes


def test_a_renewal_over_a_pending_neutral_tail_is_acked_only_when_that_frame_completes(tmp_path):
    """Kimi follow-up: the ack after a renewal is completion based: a neutral frame half in the pipe when cut A starts
    acks A only once its last byte is in, never at the renewal itself."""
    big = b"\xff\xd8" + b"n" * 200_000 + b"\xff\xd9"
    args = make_args(tmp_path, "--pipe-kb", "64")
    clock = Clock()

    async def body():
        feed = mon.MonitorFeed(args, clock=clock, wall=clock, token=None, neutral=big, log=lambda line: None)
        feed.sink.ensure_fifo()
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            feed.gate.observe("runner", "runner_privacy")
            assert feed._deliver_neutral() is False and feed.sink.pending          # half a neutral frame in the pipe
            feed.gate.observe("layout", "layout_cut", "pA")                       # renewed: the callback tries at once
            at_renewal = (feed.cut_gen, feed.showing(), feed.neutral_ack, bool(feed.sink.pending))
            data = read_all(reader)
            while not feed._deliver_neutral():
                data += read_all(reader)
            data += read_all(reader)
            return at_renewal, (feed.cut_gen, feed.showing(), feed.neutral_ack["privacy_id"], feed.neutral_frames), data
        finally:
            os.close(reader)
            feed.sink.close()

    at_renewal, after, data = run(body())
    assert at_renewal == (2, "pending", None, True)
    assert after == (2, "neutral", "pA", 1) and data == big


def test_a_watcher_cancelled_outside_shutdown_is_a_failure_and_a_stop_is_not(tmp_path):
    args = make_args(tmp_path, "--ffmpeg", str(tmp_path / "no-ffmpeg"))

    async def fetch():
        return {"privacy": True}

    async def body(cancel):
        events = []
        feed = mon.MonitorFeed(args, fetch_state=fetch, neutral=NEUTRAL, log=events.append)
        task = asyncio.ensure_future(feed.run())
        await until(lambda: len(feed._tasks) == 3)
        await asyncio.sleep(0.3)
        if cancel:
            feed._tasks[0].cancel()                                       # the layout watcher, not a shutdown
            await until(lambda: feed.watcher_failed is not None)
        health = feed.health()
        feed.stop()
        await asyncio.wait_for(task, 10)
        return health, [json.loads(line)["kind"] for line in events]

    health, kinds = run(body(cancel=True))
    assert health["ok"] is False and "privacy watcher layout ended: CancelledError" in health["last_error"]
    assert "watcher_failed" in health["privacy"]["reasons"] and kinds.count("watcher_failed") == 1
    health, kinds = run(body(cancel=False))
    assert health["ok"] is True and "watcher_failed" not in kinds                  # a normal stop is not a failure


def test_a_watcher_that_dies_closes_the_gate_and_fails_health(tmp_path):
    """Kimi review M2: a dead watcher is not silent: the gate holds closed, neutral frames go on, /healthz fails."""
    args = make_args(tmp_path, "--ffmpeg", str(tmp_path / "no-ffmpeg"), "--neutral-interval", "0.1", "--resume-after", "0")

    async def fetch():
        return {"privacy": False, "pc_mode": "chromium"}

    async def boom():
        await asyncio.sleep(0.3)
        raise RuntimeError("watcher bug")

    async def body():
        events = []
        feed = mon.MonitorFeed(args, fetch_state=fetch, neutral=NEUTRAL, log=events.append)
        feed._watch_runner = boom
        task = asyncio.ensure_future(feed.run())
        await until(lambda: feed.watcher_failed is not None)
        health = feed.health()
        feed.stop()
        await asyncio.wait_for(task, 10)
        return health, [json.loads(line) for line in events]

    health, events = run(body())
    assert health["ok"] is False and "watcher_failed" in health["privacy"]["reasons"] and health["privacy"]["private"]
    assert "privacy watcher runner ended: RuntimeError" in health["last_error"]
    assert {"kind": "watcher_failed", "watcher": "runner", "error": "RuntimeError"}.items() <= events[-1].items()


def test_a_runner_that_does_not_answer_in_time_is_unreachable(tmp_path):
    async def slow():
        await asyncio.sleep(5)
        return {"privacy": False, "pc_mode": "chromium"}

    async def body():
        feed = mon.MonitorFeed(make_args(tmp_path), fetch_state=slow, neutral=NEUTRAL)
        started = asyncio.get_running_loop().time()
        reason = await feed.runner_reason()
        return reason, asyncio.get_running_loop().time() - started

    reason, seconds = run(body())
    assert reason == "runner_unreachable" and seconds < 2.0


def test_dropping_the_tail_of_a_screen_frame_when_the_gate_closes(tmp_path):
    sink = mon.FifoSink(tmp_path / "f.mjpeg")
    sink.pending = b"tail of a screen frame"
    assert sink.drop_pending() is True and sink.pending == b"" and sink.drop_pending() is False
    assert sink.flush() is False                                          # no reader: nothing can be finished


def test_ffmpeg_never_inherits_the_token_or_a_key():
    env = mon.child_env({"PATH": "/usr/bin", "SUB01_ADMIN_TOKEN": TOKEN, "ANTHROPIC_API_KEY": "k", "GH_TOKEN": "t",
                         "X_SECRET": "s", "DISPLAY": ":103", "HOME": "/home/unreal"})
    assert env == {"PATH": "/usr/bin", "DISPLAY": ":103", "HOME": "/home/unreal"}


# ------------------------------------------------------------------ flags, token

def test_flags_keep_the_gate_on_for_a_real_display_and_the_token_on_loopback(tmp_path):
    args = make_args(tmp_path)
    assert args.desktop_url == "http://127.0.0.1:8838" and args.resume_after == 1.0 and args.neutral_interval == 0.5
    assert args.no_privacy_gate is False
    env = make_args(tmp_path, environ={"STREAMER_DESKTOP_URL": "http://127.0.0.1:8832"})
    assert env.desktop_url == "http://127.0.0.1:8832"
    assert make_args(tmp_path, "--test-source", "--no-privacy-gate").no_privacy_gate is True
    for bad in (["--no-privacy-gate"], ["--desktop-url", "http://10.0.0.5:8838"], ["--desktop-url", "https://127.0.0.1:8838"],
                ["--desktop-url", "http://127.0.0.1:8838/pc?token=x"], ["--desktop-url", "http://127.0.0.1.example:80"],
                ["--resume-after", "-1"], ["--neutral-interval", "0"]):
        with pytest.raises(SystemExit):
            make_args(tmp_path, *bad)
    with pytest.raises(SystemExit):
        make_args(tmp_path, environ={"STREAMER_DESKTOP_URL": "http://192.0.2.1:8838"})
    argv = mon.neutral_argv(make_args(tmp_path, "--size", "320x180", "--quality", "7"))
    assert "color=c=0x484a4e:s=320x180:r=1" in argv and argv[argv.index("-frames:v") + 1] == "1"
    assert argv[argv.index("-q:v") + 1] == "7" and argv[-3:] == ["-f", "mjpeg", "pipe:1"]


def test_token_comes_from_the_file_then_the_environment(tmp_path):
    (tmp_path / "token").write_text(TOKEN + "\n")
    assert mon.read_token(SimpleNamespace(token_file=str(tmp_path / "token")), {}) == TOKEN
    assert mon.read_token(SimpleNamespace(token_file=None), {"SUB01_ADMIN_TOKEN": TOKEN}) == TOKEN
    assert mon.read_token(SimpleNamespace(token_file=None), {"SUB01_ADMIN_TOKEN": "short"}) is None
    assert mon.read_token(SimpleNamespace(token_file=str(tmp_path / "missing")), {"SUB01_ADMIN_TOKEN": TOKEN}) is None


# ------------------------------------------------------------------ real ffmpeg: screen, cut, neutral, screen again

@needs_ffmpeg
def test_smoke_a_privacy_cut_replaces_the_screen_with_the_neutral_frame_and_back(tmp_path):
    state = {"privacy": False, "pc_mode": "chromium"}

    async def fetch():
        return dict(state)

    args = make_args(tmp_path, "--test-source", "--size", "320x180", "--fps", "30", "--ffmpeg", FFMPEG,
                     "--resume-after", "0.3", "--neutral-interval", "0.1")
    layout = tmp_path / "layout.jsonl"
    lines = []

    async def body():
        feed = mon.MonitorFeed(args, fetch_state=fetch, log=lines.append, events_path=tmp_path / "events.jsonl")
        task = asyncio.ensure_future(feed.run())
        await until(lambda: Path(args.fifo).exists() and feed.neutral is not None, timeout=20)
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        got = {}

        async def collect(seconds):
            data, end = b"", asyncio.get_running_loop().time() + seconds
            while asyncio.get_running_loop().time() < end:
                data += read_all(reader)
                await asyncio.sleep(0.02)
            return data

        async def latency(change):
            """Seconds from `change` to the first whole neutral frame read from the FIFO."""
            loop, data = asyncio.get_running_loop(), b""
            start = loop.time()
            change()
            while feed.neutral not in data:
                assert loop.time() - start < 5, "no neutral frame"
                data += read_all(reader)
                await asyncio.sleep(0.005)
            return loop.time() - start

        try:
            await until(lambda: (read_all(reader) or True) and feed.screen_frames >= 10, timeout=20)
            got["open"] = feed.health()
            got["layout_latency"] = await latency(lambda: append(layout, privacy_line()))   # the agent's login line
            await until(lambda: (read_all(reader) or True) and feed.health()["ffmpeg"] is False and feed.private_now())
            read_all(reader)                                             # what was in the pipe before the cut
            screen_before = feed.screen_frames
            got["private_data"] = await collect(1.0)
            got["private"] = feed.health()
            got["screen_during"] = feed.screen_frames - screen_before
            append(layout, end_line())
            await until(lambda: (read_all(reader) or True) and feed.screen_frames > screen_before + 10, timeout=20)
            got["back"] = feed.health()
            got["runner_latency"] = await latency(lambda: state.update(privacy=True))   # the runner's own privacy
            await until(lambda: (read_all(reader) or True) and feed.private_now())
            got["runner"] = feed.health()
        finally:
            os.close(reader)
            feed.stop()
            await asyncio.wait_for(task, 10)
        return feed.neutral, got

    neutral, got = run(body())
    assert mon.is_jpeg(neutral) and got["open"]["showing"] == "screen" and got["open"]["restarts"] == 1
    frames = jpegs(got["private_data"])
    assert len(frames) >= 5 and set(frames) == {neutral}                 # only the neutral frame during the cut
    assert got["screen_during"] == 0 and got["private"]["showing"] == "neutral"
    assert got["private"]["privacy"]["reasons"] == ["layout_cut"] and got["private"]["privacy"]["layout_cut_id"] == PID
    assert got["private"]["privacy"]["neutral_ack"]["privacy_id"] == PID
    # polls every 0.25 s (layout.jsonl) and 0.5 s (/pc/state); the neutral frame goes out in the observing step
    print(f"latency to the first neutral frame: layout line {got['layout_latency']:.3f} s, "
          f"runner privacy {got['runner_latency']:.3f} s")
    assert got["layout_latency"] < 1.0 and got["runner_latency"] < 1.5
    assert got["back"]["restarts"] == 2 and got["back"]["showing"] == "screen"   # a NEW ffmpeg after the cut
    assert got["runner"]["privacy"]["reasons"] == ["runner_privacy"]
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [e["kind"] for e in events] == ["privacy_off", "privacy_on", "privacy_off", "privacy_on"]
    assert events[1]["reasons"] == ["layout_cut"] and events[1]["privacy_id"] == PID
    assert all(e["source"] == "monitor_feed" for e in events) and [json.loads(line) for line in lines] == events
    if shutil.which("ffprobe"):
        probe = asyncio.run(_probe(neutral))
        assert probe == (320, 180)


@needs_ffmpeg
def test_smoke_a_capture_never_outlives_a_close_even_when_the_gate_reopens_at_once(tmp_path):
    """With --resume-after 0 a close and a reopen can both happen while the capture awaits a read: the capture belongs
    to one open period (its cut generation), so it ends and a NEW ffmpeg starts."""
    async def fetch():
        return {"privacy": False, "pc_mode": "chromium"}

    args = make_args(tmp_path, "--test-source", "--size", "320x180", "--fps", "30", "--ffmpeg", FFMPEG,
                     "--resume-after", "0")

    async def body():
        feed = mon.MonitorFeed(args, fetch_state=fetch, log=lambda line: None)
        task = asyncio.ensure_future(feed.run())
        await until(lambda: Path(args.fifo).exists())
        reader = os.open(args.fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            await until(lambda: (read_all(reader) or True) and feed.screen_frames >= 5, timeout=20)
            first_pid = feed.proc.pid
            feed.gate.observe("layout", "layout_cut", PID)               # close ...
            feed.gate.observe("layout", None)                            # ... and reopen in the same step
            reopened = not feed.gate.private
            await until(lambda: (read_all(reader) or True) and feed.restarts == 2 and feed.proc.pid != first_pid,
                        timeout=20)
            await until(lambda: (read_all(reader) or True) and feed.screen_frames >= 10, timeout=20)
            return reopened, feed.health()
        finally:
            os.close(reader)
            feed.stop()
            await asyncio.wait_for(task, 10)

    reopened, health = run(body())
    assert reopened and health["restarts"] == 2 and health["privacy"]["cut_gen"] == 2 and health["showing"] == "screen"


async def _probe(jpeg):
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-f", "mjpeg", "-show_entries", "stream=width,height", "-of", "json", "-",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate(jpeg)
    stream = json.loads(out)["streams"][0]
    return stream["width"], stream["height"]
