"""Vagon mode of the streamer desktop runner (scripts/streamer_desktop.py --pc-mode vagon).

Part 1: the pure logic (stream link redaction, the config file, connect/ended classification, the mapping of the agent
primitives onto the stream, the /pc/state fields) against fake Playwright objects: no browser, no network.
Part 2: an integration test against a MOCK stream page (tests/fixtures/vagon_mock_stream.html: a Connect button, a
canvas that records the mouse and keyboard events it receives, a "Session ended" state) in a real headless Chromium,
when Playwright and a Chromium build are available; otherwise those tests are skipped with the reason.
Nothing here talks to Vagon."""

import asyncio
import base64
import copy
import glob
import importlib.util
import io
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("streamer_desktop", ROOT / "scripts/streamer_desktop.py")
sd = importlib.util.module_from_spec(spec)
sys.modules["streamer_desktop"] = sd
spec.loader.exec_module(sd)
FIXTURES = ROOT / "tests" / "fixtures"
TOKEN = "operator-credential-test"
AUTH = {"X-Admin-Token": TOKEN}
SECRET = "SECRET-QUERY-TOKEN-9f3a"
STREAM = "https://app.vagon.io/stream/abc123?launchFlags=-token%20" + SECRET


def run(coro):
    asyncio.run(coro)


def events_of(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


# --- stream link, config file ---------------------------------------------------------------------------------------
def test_redact_url_keeps_the_host_and_never_the_path_query_or_fragment():
    assert sd.redact_url(STREAM) == "https://app.vagon.io/…"
    assert sd.redact_url("https://app.vagon.io/") == "https://app.vagon.io/"
    assert sd.redact_url("http://127.0.0.1:8080/fx/page.html?token=x#frag") == "http://127.0.0.1:8080/…"
    assert sd.redact_url("https://app.vagon.io/?token=x") == "https://app.vagon.io/…"
    assert sd.redact_url("not a url") == "" and sd.redact_url("") == "" and sd.redact_url(None) == ""
    for value in (STREAM, "http://127.0.0.1:8080/fx/page.html?token=x#frag"):
        assert SECRET not in sd.redact_url(value) and "token" not in sd.redact_url(value)


def test_vagon_url_problem():
    assert sd.vagon_url_problem(STREAM) is None
    assert sd.vagon_url_problem("https://app.vagon.io/stream/abc") is None
    assert sd.vagon_url_problem("http://app.vagon.io/stream/abc") == "the stream link must be https"
    assert sd.vagon_url_problem("https://user:pw@app.vagon.io/stream/abc") == "credentials-in-url"
    assert sd.vagon_url_problem("https://app.vagon.io/") == "the stream link has no path"
    assert sd.vagon_url_problem("https://www.paypal.com/stream/x") == "banking"
    assert sd.vagon_url_problem("https://login.vagon.io/stream/x") == "login"
    assert sd.vagon_url_problem("https://127.0.0.1/fx/mock.html?t=1") == "private-host"
    assert sd.vagon_url_problem("http://127.0.0.1:9/fx/mock.html?t=1") == "the stream link must be https"
    assert sd.vagon_url_problem("http://127.0.0.1:9/fx/mock.html?t=1", allow_private=True) is None
    assert sd.vagon_url_problem("https://app.vagon.io/stream/a b") == "expected a stream URL"
    assert sd.vagon_url_problem("") == "expected a stream URL" and sd.vagon_url_problem(None) == "expected a stream URL"


def test_load_vagon_config(tmp_path):
    good = tmp_path / "vagon.json"
    good.write_text(json.dumps({"schema": sd.VAGON_SCHEMA, "stream_url": STREAM, "api_key_file": "/secret/vagon-key"}))
    assert sd.load_vagon_config(good) == {"kind": "streams", "stream_url": STREAM, "api_key_file": "/secret/vagon-key", "machine_id": ""}
    minimal = tmp_path / "min.json"
    minimal.write_text(json.dumps({"schema": sd.VAGON_SCHEMA}))
    assert sd.load_vagon_config(minimal) == {"kind": "streams", "stream_url": "", "api_key_file": "", "machine_id": ""}
    bad = {"wrong schema": {"schema": "other", "stream_url": STREAM},
           "http link": {"schema": sd.VAGON_SCHEMA, "stream_url": "http://app.vagon.io/stream/x"},
           "credentials": {"schema": sd.VAGON_SCHEMA, "stream_url": "https://u:p@app.vagon.io/stream/x"},
           "relative key": {"schema": sd.VAGON_SCHEMA, "api_key_file": "vagon-key"},
           "unknown key": {"schema": sd.VAGON_SCHEMA, "api_secret": "abc"},
           "a list": [1, 2]}
    for name, data in bad.items():
        path = tmp_path / (name.replace(" ", "_") + ".json")
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError) as info:
            sd.load_vagon_config(path)
        assert "app.vagon.io" not in str(info.value) and "abc" not in str(info.value), name     # no link, no key in errors
    (tmp_path / "broken.json").write_text("{oops")
    with pytest.raises(ValueError, match="not valid JSON"):
        sd.load_vagon_config(tmp_path / "broken.json")
    with pytest.raises(ValueError, match="cannot read"):
        sd.load_vagon_config(tmp_path / "missing.json")
    local = tmp_path / "local.json"
    local.write_text(json.dumps({"schema": sd.VAGON_SCHEMA, "stream_url": "http://127.0.0.1:9/fx/m.html?t=1"}))
    with pytest.raises(ValueError):
        sd.load_vagon_config(local)
    assert sd.load_vagon_config(local, allow_private=True)["stream_url"] == "http://127.0.0.1:9/fx/m.html?t=1"


def test_api_key_file_status_never_reads_the_file(tmp_path):
    assert sd.api_key_file_status("") == "none"
    assert sd.api_key_file_status(str(tmp_path / "nope")) == "missing"
    key = tmp_path / "key"
    key.write_text("vagon-public:vagon-secret")
    key.chmod(0o644)
    assert sd.api_key_file_status(str(key)) == "permissive"
    key.chmod(0o600)
    assert sd.api_key_file_status(str(key)) == "configured"


# --- the connection page: which button, which phase ------------------------------------------------------------------
def btn(label, x=800, y=500, w=200, h=60):
    return {"label": label, "box": [x, y, w, h]}


def probe(text="", buttons=(), stream=None, url=STREAM, title="Vagon Streams"):
    return {"url": url, "title": title, "vw": 1920, "vh": 1080, "loading": False, "text": text,
            "buttons": list(buttons), "stream": stream}


VIDEO = {"tag": "video", "box": [0, 0, 1920, 1080], "playing": True}
STALLED = {"tag": "video", "box": [0, 0, 1920, 1080], "playing": False}
CANVAS = {"tag": "canvas", "box": [0, 0, 1920, 1080], "playing": True}


def test_choose_vagon_button_prefers_reconnect_then_connect_and_skips_other_controls():
    assert sd.choose_vagon_button([btn("Settings"), btn("Connect"), btn("Mute")]) == 1
    assert sd.choose_vagon_button([btn("Connect"), btn("Try again")]) == 1
    assert sd.choose_vagon_button([btn("Play"), btn("Reconnect")]) == 1
    assert sd.choose_vagon_button([btn("Start streaming")]) == 0 and sd.choose_vagon_button([btn("Launch")]) == 0
    assert sd.choose_vagon_button([btn("Full screen"), btn("Dark mode"), btn("Settings")]) is None
    assert sd.choose_vagon_button([btn("Sign in to connect"), btn("Log in")]) is None          # never a login control
    assert sd.choose_vagon_button([btn("Buy now"), btn("Subscribe")]) is None                   # never a money control
    assert sd.choose_vagon_button([btn(""), btn("   ")]) is None and sd.choose_vagon_button([]) is None
    assert sd.choose_vagon_button(None) is None


def test_classify_vagon_phases():
    assert sd.classify_vagon(probe("", [btn("Settings")], VIDEO)) == ("ready", None)
    assert sd.classify_vagon(probe("", [], CANVAS)) == ("ready", None)
    assert sd.classify_vagon(probe("Ready to connect", [btn("Settings"), btn("Connect")])) == ("waiting", 1)
    assert sd.classify_vagon(probe("Connecting…")) == ("busy", None)
    assert sd.classify_vagon(probe("Preparing your session, please wait")) == ("busy", None)
    assert sd.classify_vagon(probe("", [], STALLED)) == ("busy", None)                           # a video that stopped
    assert sd.classify_vagon(probe("Your session has ended.", [btn("Reconnect")])) == ("ended", 0)
    assert sd.classify_vagon(probe("Session ended")) == ("ended", None)
    assert sd.classify_vagon(probe("You were disconnected", [btn("Settings")])) == ("ended", None)
    assert sd.classify_vagon(probe("The Stream is expired")) == ("ended", None)
    assert sd.classify_vagon(probe("Insufficient capacity, try again later", [btn("Try again")])) == ("ended", 0)
    assert sd.classify_vagon(probe("", [btn("Reconnect")], VIDEO)) == ("ended", 0)              # a reconnect offer wins
    assert sd.classify_vagon(probe("Session ended", [btn("Connect")], VIDEO)) == ("ended", 0)
    assert sd.classify_vagon(probe("")) == ("blank", None)
    assert sd.classify_vagon(None) == ("blank", None)
    phases = {sd.classify_vagon(p)[0] for p in (probe("", [], VIDEO), probe("x", [btn("Connect")]), probe("Connecting"),
                                                 probe("Session ended"), probe(""))}
    assert phases <= set(sd.VAGON_PHASES)


def test_image_point_maps_the_observation_image_onto_the_viewport():
    assert sd.image_point([640, 360], (1920, 1080)) == (960.0, 540.0)
    assert sd.image_point([0, 0], (1920, 1080)) == (0.0, 0.0)
    assert sd.image_point([1279.9, 719.9], (1919, 1079)) == (1918.0, 1078.0)                   # clamped to the page
    assert sd.image_point([320, 180], (1280, 720)) == (320.0, 180.0)


def test_vagon_state_public_fields():
    v = sd.VagonState("configured")
    pub = v.public()
    assert pub["connected"] is False and pub["phase"] == "starting" and pub["reconnects"] == 0
    assert pub["last_reconnect_utc"] is None and pub["sessions"] == 0 and pub["reloads"] == 0
    assert pub["api_key_file"] == "configured" and pub["since_utc"].endswith("+00:00")
    assert v.set_phase("waiting") is True and v.set_phase("waiting") is False and v.phase == "waiting"
    assert json.dumps(pub)                                                                     # JSON-serialisable


def test_observation_carries_mode_and_remote_ready_only_in_vagon_mode():
    out = io.BytesIO()
    Image.new("RGB", (1920, 1080), (40, 40, 40)).save(out, "JPEG")
    base = {"url": "https://app.vagon.io/…", "title": "Vagon Streams", "text": "", "scroll": {"y": 0, "max": 0},
            "jpeg": out.getvalue(), "width": 1920, "height": 1080, "marks": [], "loading": False, "dialogs": []}
    obs = sd.build_observation({**base, "mode": "vagon", "remote_ready": True}, "ab-1")
    assert obs["mode"] == "vagon" and obs["remote_ready"] is True and obs["marks"] == [] and obs["text"] == ""
    assert Image.open(io.BytesIO(base64.b64decode(obs["jpeg_b64"]))).size == (1280, 720)
    plain = sd.build_observation(base, "ab-2")
    assert "mode" not in plain and "remote_ready" not in plain                                 # chromium: unchanged


# --- /pc/state --------------------------------------------------------------------------------------------------------
class StubDesk:
    def __init__(self, mode):
        self.status, self.restarts, self.error = "ready", 0, ""
        self.feed, self.cfg, self.vagon = sd.FrameFeed(epoch="abc123"), SimpleNamespace(pc_mode=mode), sd.VagonState("none")

    def display(self):
        return self.feed.display()

    async def release_inputs(self):
        pass


def test_pc_state_reports_pc_mode_and_the_vagon_substate(tmp_path):
    async def body():
        for mode in ("chromium", "vagon"):
            desk = StubDesk(mode)
            runner = sd.Runner(desk, TOKEN, sd.Events(tmp_path / "e.jsonl"))
            http = TestClient(TestServer(sd.create_app(runner)))
            await http.start_server()
            try:
                state = await (await http.get("/pc/state", headers=AUTH)).json()
                assert state["pc_mode"] == mode and state["status"] == "ready"
                if mode == "vagon":
                    assert state["vagon"]["connected"] is False and state["vagon"]["reconnects"] == 0
                    assert state["vagon"]["last_reconnect_utc"] is None and state["vagon"]["phase"] == "starting"
                    desk.vagon.connected, desk.vagon.reconnects, desk.vagon.last_reconnect_utc = True, 2, "2026-10-23T10:00:00+00:00"
                    state = await (await http.get("/pc/state", headers=AUTH)).json()
                    assert state["vagon"]["connected"] is True and state["vagon"]["reconnects"] == 2
                    assert state["vagon"]["last_reconnect_utc"] == "2026-10-23T10:00:00+00:00"
                else:
                    assert "vagon" not in state
                await http.post("/pc/privacy", json={"active": True}, headers=AUTH)
                masked = await (await http.get("/pc/state", headers=AUTH)).json()
                assert masked["privacy"] is True and "vagon" not in masked and "pc_mode" not in masked   # masked view unchanged
            finally:
                await http.close()
    run(body())


# --- the primitives on the stream, against fake Playwright objects --------------------------------------------------------
class FakeKeyboard:
    def __init__(self):
        self.log = []

    async def down(self, key):
        self.log.append(("down", key))

    async def up(self, key):
        self.log.append(("up", key))

    async def press(self, key):
        self.log.append(("press", key))

    async def type(self, text, delay=0):
        self.log.append(("type", text))

    async def insert_text(self, text):
        self.log.append(("insert", text))


class FakeMouse:
    def __init__(self):
        self.log = []

    async def move(self, x, y, steps=1):
        self.log.append(("move", round(x), round(y)))

    async def click(self, x, y, **kw):
        self.log.append(("click", round(x), round(y)))

    async def down(self, button="left"):
        self.log.append(("down", button))

    async def up(self, button="left"):
        self.log.append(("up", button))

    async def wheel(self, dx, dy):
        self.log.append(("wheel", dx, dy))


class FakePage:
    def __init__(self):
        self.keyboard, self.mouse, self.focused, self.goto_calls = FakeKeyboard(), FakeMouse(), 0, []

    async def evaluate(self, js, arg=None):
        if js is sd.VAGON_FOCUS_JS:
            self.focused += 1
            return True
        if js is sd.VAGON_HIT_JS:                       # the stream is under every point (the hit test fails closed)
            return {"ok": True, "tag": "canvas"}
        return None

    async def goto(self, url, **kw):
        self.goto_calls.append(url)


def vagon_desktop(tmp_path, monkeypatch, probes):
    """A Desktop in vagon mode whose stream probe answers from `probes` (the last one repeats)."""
    monkeypatch.setattr(sd, "VAGON_SETTLE_S", 0)
    monkeypatch.setattr(sd, "VAGON_NAV_SETTLE_S", 0)
    desk = sd.Desktop(sd.Config(profile=tmp_path / "profile", pc_mode="vagon", vagon_url=STREAM), sd.Events(tmp_path / "events.jsonl"))
    desk.status, desk.page, desk.view = "ready", FakePage(), (1920, 1080)
    desk._input_lock = asyncio.Lock()
    queue = [copy.deepcopy(p) for p in probes]

    async def fake_probe():
        return copy.deepcopy(queue.pop(0) if len(queue) > 1 else queue[0])
    desk._vagon_probe = fake_probe
    return desk


def test_primitives_are_mapped_onto_the_stream(tmp_path, monkeypatch):
    async def body():
        desk = vagon_desktop(tmp_path, monkeypatch, [probe("", [btn("Settings")], VIDEO)])
        kb, mouse = desk.page.keyboard.log, desk.page.mouse.log
        r = await desk.do({"action": "click", "point": [640.0, 360.0]})
        assert r["errors"] == [] and mouse == [("move", 960, 540), ("click", 960, 540)] and desk.cursor == [960.0, 540.0]
        mouse.clear()
        r = await desk.do({"action": "navigate", "url": "https://example.com/a?b=1"})
        assert r["errors"] == [] and kb == [("down", "Control"), ("press", "l"), ("up", "Control"), ("type", "https://example.com/a?b=1"), ("press", "Enter")]
        assert desk.page.focused == 1 and desk.page.goto_calls == []            # the remote browser navigates, not ours
        kb.clear()
        await desk.do({"action": "search", "query": "cats dogs"})
        assert kb == [("down", "Control"), ("press", "l"), ("up", "Control"), ("type", sd.SEARCH_URL + "cats+dogs"), ("press", "Enter")]
        kb.clear()
        await desk.do({"action": "back"})
        assert kb == [("down", "Alt"), ("press", "ArrowLeft"), ("up", "Alt")]
        kb.clear()
        await desk.do({"action": "type", "text": "hello", "submit": True})
        assert kb == [("type", "hello"), ("press", "Enter")]
        kb.clear()
        await desk.do({"action": "type", "text": "no submit", "submit": False})
        assert kb == [("type", "no submit")]
        kb.clear()
        await desk.do({"action": "key", "key": "Control+a"})
        assert kb == [("down", "Control"), ("press", "a"), ("up", "Control")]    # held: Vagon drops a too-fast chord
        await desk.do({"action": "scroll", "direction": "down", "amount": 600})
        assert mouse[0] == ("move", 960, 540) and mouse[1:] == [("wheel", 0, 100.0)] * 6
        mouse.clear()
        await desk.do({"action": "scroll", "direction": "up", "amount": 300})
        assert mouse[1:] == [("wheel", 0, -50.0)] * 6
        r = await desk.do({"action": "click", "mark": 3, "obs": "x-1"})
        assert r["errors"] == ["there are no marks on the remote desktop; click by point"]
        r = await desk.do({"action": "wait", "seconds": 0})
        assert r["errors"] == []
    run(body())


def test_primitives_are_refused_while_the_remote_desktop_is_not_connected(tmp_path, monkeypatch):
    async def body():
        desk = vagon_desktop(tmp_path, monkeypatch, [probe("Connecting…")])
        for action in ({"action": "click", "point": [1.0, 1.0]}, {"action": "type", "text": "x", "submit": False},
                       {"action": "navigate", "url": "https://example.com/"}, {"action": "key", "key": "Enter"},
                       {"action": "scroll", "direction": "down", "amount": 100}, {"action": "back"}):
            r = await desk.do(action)
            assert r["errors"] == ["the remote desktop is not connected (stream busy); wait and observe again"], action
        assert desk.page.keyboard.log == [] and desk.page.mouse.log == []
        r = await desk.do({"action": "wait", "seconds": 0})
        assert r["errors"] == []
    run(body())


def test_vagon_snapshot_has_pixels_mode_and_no_dom_summary(tmp_path, monkeypatch):
    async def body():
        desk = vagon_desktop(tmp_path, monkeypatch, [probe("", [], VIDEO)])
        out = io.BytesIO()
        Image.new("RGB", (1920, 1080), (9, 9, 9)).save(out, "JPEG")

        async def shot(**kw):
            return out.getvalue()
        desk.page.screenshot = shot
        snap = await desk.snapshot("obs-1")
        assert snap["mode"] == "vagon" and snap["remote_ready"] is True and snap["marks"] == [] and snap["text"] == ""
        assert snap["url"] == "https://app.vagon.io/…" and SECRET not in json.dumps({k: v for k, v in snap.items() if k != "jpeg"})
        assert snap["title"] == "Vagon Streams" and snap["scroll"] == {"y": 0, "max": 0} and snap["jpeg"] == out.getvalue()
        obs = sd.build_observation(snap, "obs-1")
        assert obs["mode"] == "vagon" and obs["remote_ready"] is True
        desk2 = vagon_desktop(tmp_path, monkeypatch, [probe("Connecting", title="")])
        desk2.page.screenshot = shot
        snap = await desk2.snapshot(None)
        assert snap["remote_ready"] is False and snap["title"] == "remote desktop"
    run(body())


def test_native_keys_and_pc_input_reach_the_stream(tmp_path, monkeypatch):
    async def body():
        desk = vagon_desktop(tmp_path, monkeypatch, [probe("", [], VIDEO)])
        desk.vagon.connected = True
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x2A, 0x1E, 0x9E, 0xAA]}) is True
        assert desk.page.keyboard.log == [("down", "Shift"), ("down", "KeyA"), ("up", "KeyA"), ("up", "Shift")]
        assert desk.page.focused == 1
        desk.page.keyboard.log.clear()
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x1D, 0x2F, 0xAF, 0x9D]})      # Ctrl+V stays refused
        assert desk.page.keyboard.log == [("down", "Control"), ("up", "Control")]
        desk.page.keyboard.log.clear()
        assert await desk.type_text("hello\nworld\n") is True
        assert desk.page.keyboard.log == [("type", "hello"), ("press", "Enter"), ("type", "world"), ("press", "Enter")]
        desk.vagon.connected = False
        assert await desk.type_text("x") is False
    run(body())


def test_connect_loop_presses_connect_notices_the_end_and_re_enters(tmp_path, monkeypatch):
    async def body():
        monkeypatch.setattr(sd, "VAGON_CLICK_GAP_S", 0)
        monkeypatch.setattr(sd, "VAGON_RELOAD_BACKOFF", (0.0,))
        sequence = [probe("Ready to connect", [btn("Settings"), btn("Connect", 860, 510)]),
                    probe("Connecting…"),
                    probe("", [btn("Mute")], VIDEO),
                    probe("", [], STALLED),                                   # one bad probe: still connected
                    probe("", [], VIDEO),
                    probe("Your session has ended.", [btn("Reconnect", 860, 510)]),
                    probe("Connecting…"),
                    probe("", [], VIDEO),
                    probe("Session ended"),                                   # no button at all: the page is opened again
                    probe("Ready to connect", [btn("Connect", 860, 510)])]
        desk = vagon_desktop(tmp_path, monkeypatch, sequence)
        v, mouse, page = desk.vagon, desk.page.mouse.log, desk.page
        await desk._vagon_step()                                              # 1: waiting -> press Connect
        assert v.phase == "waiting" and mouse == [("move", 960, 540), ("click", 960, 540)] and v.attempts == 1
        await desk._vagon_step()                                              # 2: busy
        assert v.phase == "busy" and not v.connected
        await desk._vagon_step()                                              # 3: ready
        assert v.connected and v.phase == "ready" and v.sessions == 1 and v.reconnects == 0 and v.attempts == 0
        await desk._vagon_step()                                              # 4: a stalled video is tolerated
        assert v.connected and v.misses == 1
        await desk._vagon_step()                                              # 5: ready again
        assert v.connected and v.misses == 0
        mouse.clear()
        await desk._vagon_step()                                              # 6: ended, Reconnect offered -> pressed
        assert not v.connected and v.phase == "ended" and mouse == [("move", 960, 540), ("click", 960, 540)]
        await desk._vagon_step()                                              # 7: busy
        await desk._vagon_step()                                              # 8: ready: a reconnect
        assert v.connected and v.reconnects == 1 and v.sessions == 2 and v.last_reconnect_utc.endswith("+00:00")
        await desk._vagon_step()                                              # 9: ended without a button: opened again
        assert not v.connected and v.reloads == 1 and page.goto_calls == [STREAM] and v.phase == "starting"
        mouse.clear()
        await desk._vagon_step()                                              # 10: the fresh page offers Connect
        assert mouse == [("move", 960, 540), ("click", 960, 540)] and v.phase == "waiting"
        kinds = [(e["kind"], e.get("state")) for e in events_of(tmp_path / "events.jsonl")]
        assert ("vagon", "press") in kinds and ("vagon", "connected") in kinds and ("vagon", "disconnected") in kinds
        assert ("vagon", "open") in kinds
        text = (tmp_path / "events.jsonl").read_text()
        assert SECRET not in text and "launchFlags" not in text                   # the link is logged as host only
        assert desk.vagon.public()["reconnects"] == 1
    run(body())


def test_connect_loop_stops_pressing_after_six_attempts_and_reopens_the_page(tmp_path, monkeypatch):
    async def body():
        monkeypatch.setattr(sd, "VAGON_CLICK_GAP_S", 0)
        monkeypatch.setattr(sd, "VAGON_RELOAD_BACKOFF", (0.0,))
        desk = vagon_desktop(tmp_path, monkeypatch, [probe("Ready", [btn("Connect")])])
        for _ in range(6):
            await desk._vagon_step()
        assert desk.vagon.attempts == 6 and len(desk.page.mouse.log) == 12 and desk.page.goto_calls == []
        await desk._vagon_step()
        assert desk.page.goto_calls == [STREAM] and desk.vagon.attempts == 0 and desk.vagon.reloads == 1
    run(body())


def test_error_texts_are_scrubbed_of_the_link(tmp_path):
    desk = sd.Desktop(sd.Config(profile=tmp_path / "p", pc_mode="vagon", vagon_url=STREAM), sd.Events(tmp_path / "e.jsonl"))
    scrubbed = desk._scrub(f"Page.goto: net::ERR_CONNECTION_REFUSED at {STREAM}")
    assert SECRET not in scrubbed and "launchFlags" not in scrubbed and "app.vagon.io" in scrubbed
    assert SECRET not in desk._scrub("query was launchFlags=-token%20" + SECRET)
    plain = sd.Desktop(sd.Config(profile=tmp_path / "p2"), sd.Events(tmp_path / "e2.jsonl"))
    assert plain._url_for_log("https://example.com/a?b=1") == "https://example.com/a?b=1"
    assert desk._url_for_log(STREAM) == "https://app.vagon.io/…"


def test_main_resolves_the_vagon_settings_without_echoing_the_link(tmp_path, monkeypatch, capsys):
    token = tmp_path / "token"
    token.write_text("operator-credential-test\n")
    base = ["--token-file", str(token), "--data-dir", str(tmp_path / "d")]
    seen = []

    async def fake_serve(args):
        seen.append(args)
    monkeypatch.setattr(sd, "serve", fake_serve)
    for argv in (["--pc-mode", "vagon"],                                              # no link anywhere
                 ["--pc-mode", "vagon", "--vagon-url", "https://u:pw@app.vagon.io/stream/x"],
                 ["--pc-mode", "vagon", "--vagon-url", "http://app.vagon.io/stream/x"],
                 ["--vagon-url", STREAM],                                             # needs --pc-mode vagon
                 ["--pc-mode", "rdp"]):
        with pytest.raises(SystemExit):
            sd.main(base + argv + ["--streamer-dir", str(tmp_path / "nothing")])
        err = capsys.readouterr().err
        assert SECRET not in err and "u:pw" not in err
    assert seen == []
    sd.main(base)                                                                     # the default is unchanged
    assert seen[-1].pc_mode == "chromium" and seen[-1].vagon_url == ""
    conf = tmp_path / "streamer" / "vagon.json"
    conf.parent.mkdir()
    conf.write_text(json.dumps({"schema": sd.VAGON_SCHEMA, "stream_url": STREAM, "api_key_file": str(tmp_path / "key")}))
    sd.main(base + ["--pc-mode", "vagon", "--streamer-dir", str(conf.parent)])
    assert seen[-1].pc_mode == "vagon" and seen[-1].vagon_url == STREAM and seen[-1].vagon_api_key_file == str(tmp_path / "key")
    sd.main(base + ["--pc-mode", "vagon", "--vagon-config", str(conf), "--vagon-url", "https://app.vagon.io/stream/other"])
    assert seen[-1].vagon_url == "https://app.vagon.io/stream/other"                 # the flag wins over the file
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "x", "stream_url": STREAM}))
    with pytest.raises(SystemExit):
        sd.main(base + ["--pc-mode", "vagon", "--vagon-config", str(bad)])
    assert SECRET not in capsys.readouterr().err


def test_chromium_mode_is_the_default_and_keeps_its_dom_paths(tmp_path):
    cfg = sd.Config(profile=tmp_path / "p")
    assert cfg.pc_mode == "chromium" and cfg.vagon_url == "" and cfg.vagon_api_key_file == ""
    desk = sd.Desktop(cfg, sd.Events(tmp_path / "e.jsonl"))
    assert desk.vagon_mode is False and desk._vagon_task is None
    assert "--kiosk" in sd.chromium_args(sd.Config(profile=tmp_path / "p", pc_mode="vagon"))   # kiosk: the stream fills the screen


# --- integration: a real headless Chromium on the mock stream page ----------------------------------------------------------
def chromium_executable():
    """A Chromium that Playwright can drive, or None (then the browser tests are skipped). Playwright's own build when
    it is installed, else a build under PLAYWRIGHT_BROWSERS_PATH (/opt/pw-browsers here), else BROWSE_CHROMIUM."""
    if importlib.util.find_spec("playwright") is None:
        return None
    env = os.environ.get("BROWSE_CHROMIUM")
    if env and Path(env).exists():
        return env
    roots = [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), str(Path.home() / ".cache" / "ms-playwright")]
    for root in [r for r in roots if r]:
        found = sorted(glob.glob(os.path.join(root, "chromium-*", "chrome-linux*", "chrome")), reverse=True)
        if found:
            return found[0]
    return None


CHROMIUM = chromium_executable()
needs_browser = pytest.mark.skipif(CHROMIUM is None, reason="playwright with a Chromium build is not available (no "
                                                           "`playwright install` is run here)")


async def until(predicate, timeout=30.0, step=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(step)
    return predicate()


class Harness:
    """The fixture server, a Desktop in vagon mode on a real headless Chromium, the Runner and its HTTP app."""

    def __init__(self, tmp_path, page_name, query):
        self.tmp_path, self.page_name, self.query = tmp_path, page_name, query
        self.server = self.desk = self.runner = self.http = self.events = None

    async def __aenter__(self):
        app = web.Application()
        app.router.add_static("/fx", str(FIXTURES), show_index=False)
        self.server = TestServer(app)
        await self.server.start_server()
        self.url = f"http://127.0.0.1:{self.server.port}/fx/{self.page_name}?{self.query}"
        cfg = sd.Config(profile=self.tmp_path / "profile", headless=True, kiosk=False, allow_private=True,
                        chromium=CHROMIUM or "", pc_mode="vagon", vagon_url=self.url)
        self.events = sd.Events(self.tmp_path / "events.jsonl")
        self.desk = sd.Desktop(cfg, self.events)
        self.runner = sd.Runner(self.desk, TOKEN, self.events, allow_private=True)
        self.desk.on_change = self.runner.notify
        self.http = TestClient(TestServer(sd.create_app(self.runner)))
        await self.http.start_server()
        self.desk.start()
        ok = await until(lambda: self.desk.status == "ready", 90)
        if not ok:
            await self.__aexit__(None, None, None)
            pytest.skip(f"chromium did not start here: {self.desk.error!r}"[:200])
        return self

    async def __aexit__(self, *exc):
        for step in (self.http and self.http.close(), self.desk and self.desk.close(), self.server and self.server.close()):
            if step is not None:
                try:
                    await step
                except Exception:
                    pass

    @property
    def frame(self):
        return self.desk._vagon_frame or self.desk.page.main_frame

    async def mock_events(self, clear=False):
        got = await self.frame.evaluate("window.__events")
        if clear:
            await self.frame.evaluate("window.__events.length = 0")
        return got

    async def act(self, **body):
        r = await self.http.post("/desktop/act", json=body, headers=AUTH)
        assert r.status == 200, await r.text()
        return await r.json()

    async def state(self):
        return await (await self.http.get("/pc/state", headers=AUTH)).json()


def keydowns(events):
    return [(e["key"], bool(e["ctrl"]), bool(e["alt"])) for e in events if e["kind"] == "keydown"]


def typed(events):
    return "".join(e["key"] for e in events if e["kind"] == "keydown" and len(e["key"]) == 1 and not e["ctrl"])


@needs_browser
def test_vagon_mode_connects_drives_the_stream_and_reconnects(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sd, "VAGON_TICK_S", 0.3)
    monkeypatch.setattr(sd, "VAGON_CLICK_GAP_S", 1.0)
    monkeypatch.setattr(sd, "VAGON_SETTLE_S", 0.3)
    monkeypatch.setattr(sd, "VAGON_NAV_SETTLE_S", 0.3)

    async def body():
        async with Harness(tmp_path, "vagon_mock_stream.html", f"token={SECRET}&delay=300") as h:
            desk = h.desk
            assert await until(lambda: desk.vagon.connected, 30), (desk.vagon.phase, desk.error)
            assert await h.frame.evaluate("window.__state") == "connected"
            assert await h.frame.evaluate("window.__connects") == 1                 # one press of Connect, not many
            state = await h.state()
            assert state["pc_mode"] == "vagon" and state["vagon"]["connected"] is True
            assert state["vagon"]["reconnects"] == 0 and state["vagon"]["last_reconnect_utc"] is None
            assert state["vagon"]["phase"] == "ready" and state["display"]["available"] is True
            obs = await (await h.http.get("/desktop/observe", headers=AUTH)).json()
            assert obs["mode"] == "vagon" and obs["remote_ready"] is True and obs["marks"] == [] and obs["text"] == ""
            assert obs["url"] == f"http://127.0.0.1:{h.server.port}/…" and SECRET not in json.dumps(obs)
            assert Image.open(io.BytesIO(base64.b64decode(obs["jpeg_b64"]))).size == (1280, 720)
            # click by point: the stream element gets a real press at the page point 960,540
            await h.mock_events(clear=True)
            res = await h.act(action="click", point=[640, 360])
            assert res["ok"] is True and res["outcome"]["changed"] is True and res["outcome"]["errors"] == []
            ev = await h.mock_events(clear=True)
            down = next(e for e in ev if e["kind"] == "mousedown")
            assert (down["x"], down["y"], down["button"]) == (960, 540, 0) and any(e["kind"] == "mouseup" for e in ev)
            # type + submit: real key events on the focused stream
            res = await h.act(action="type", text="hi there", submit=True)
            ev = await h.mock_events(clear=True)
            assert res["ok"] is True and typed(ev) == "hi there" and keydowns(ev)[-1] == ("Enter", False, False)
            # key combination
            await h.act(action="key", key="Control+a")
            assert ("a", True, False) in keydowns(await h.mock_events(clear=True))
            # scroll: wheel events over the stream
            res = await h.act(action="scroll", direction="down", amount=600)
            wheels = [e["dy"] for e in await h.mock_events(clear=True) if e["kind"] == "wheel"]
            assert res["ok"] is True and len(wheels) == 6 and all(d > 0 for d in wheels)
            await h.act(action="scroll", direction="up", amount=300)
            assert all(e["dy"] < 0 for e in await h.mock_events(clear=True) if e["kind"] == "wheel")
            # navigate: Ctrl+L, the URL, Enter into the remote browser; our own page never moves
            res = await h.act(action="navigate", url="https://example.com/a?b=1")
            ev = await h.mock_events(clear=True)
            assert res["ok"] is True and keydowns(ev)[:2] == [("Control", True, False), ("l", True, False)]
            assert keydowns(ev)[-1] == ("Enter", False, False)
            assert typed(ev) == "https://example.com/a?b=1" and h.url.split("?")[0] in desk.page.url
            # search: the DuckDuckGo HTML URL typed the same way
            res = await h.act(action="search", query="cats dogs")
            ev = await h.mock_events(clear=True)
            assert res["ok"] is True and typed(ev) == sd.SEARCH_URL + "cats+dogs"
            # back: Alt+Left for the remote browser
            await h.act(action="back")
            assert ("ArrowLeft", False, True) in keydowns(await h.mock_events(clear=True))
            # policy and marks still hold
            res = await h.act(action="navigate", url="https://www.paypal.com/")
            assert res["ok"] is False and res["outcome"]["errors"] == ["blocked: banking"]
            res = await h.act(action="click", mark=1)
            assert res["ok"] is False and "not in the last observation" in res["outcome"]["errors"][0]
            res = await h.act(action="key", key="Control+v")
            assert res["ok"] is False and res["outcome"]["errors"] == ["blocked: clipboard keys are disabled"]
            assert await h.mock_events(clear=True) == []
            # native monitor input and /pc/input reach the stream
            r = await h.http.post("/pc/graphical-input", json={"type": "vga-keyboard", "scancodes": [0x2A, 0x1E, 0x9E, 0xAA]}, headers=AUTH)
            assert (await r.json()) == {"ok": True}
            assert ("A", False, False) in keydowns(await h.mock_events(clear=True))
            moves = await h.frame.evaluate("window.__moves")
            r = await h.http.post("/pc/graphical-input", json={"type": "vga-mouse", "dx": 10, "dy": 5, "wheel": 0, "buttons": [True, False, False]}, headers=AUTH)
            assert (await r.json()) == {"ok": True}
            await h.http.post("/pc/graphical-input", json={"type": "vga-mouse", "dx": 0, "dy": 0, "wheel": 0, "buttons": [False, False, False]}, headers=AUTH)
            ev = await h.mock_events(clear=True)
            assert await h.frame.evaluate("window.__moves") > moves and [e["kind"] for e in ev if e["kind"].startswith("mouse")] == ["mousedown", "mouseup"]
            r = await h.http.post("/pc/input", json={"input": "ok"}, headers=AUTH)
            assert (await r.json())["ok"] is True
            ev = await h.mock_events(clear=True)
            assert typed(ev) == "ok" and keydowns(ev)[-1][0] == "Enter"
            # the session ends: noticed, actions refused honestly, the Reconnect button pressed, counted
            await h.frame.evaluate("window.__endSession()")
            assert await until(lambda: not desk.vagon.connected, 10)
            assert desk.vagon.phase == "ended"
            if not desk.vagon.connected:
                res = await h.act(action="type", text="x")
                if not res["ok"]:
                    assert "not connected" in res["outcome"]["errors"][0]
            assert await until(lambda: desk.vagon.connected, 20), desk.vagon.phase
            state = await h.state()
            assert state["vagon"]["reconnects"] == 1 and state["vagon"]["last_reconnect_utc"].endswith("+00:00")
            assert state["vagon"]["sessions"] == 2 and await h.frame.evaluate("window.__connects") == 2
            obs = await (await h.http.get("/desktop/observe", headers=AUTH)).json()
            assert obs["remote_ready"] is True
            kinds = [(e["kind"], e.get("state")) for e in events_of(h.events.path)]
            assert kinds.count(("vagon", "connected")) == 2 and ("vagon", "disconnected") in kinds and ("vagon", "press") in kinds
            logged = h.events.path.read_text() + capsys.readouterr().out
            assert SECRET not in logged and "token=" not in logged and "?delay" not in logged
    run(body())


@needs_browser
def test_vagon_mode_reopens_an_ended_page_that_offers_no_way_back(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "VAGON_TICK_S", 0.3)
    monkeypatch.setattr(sd, "VAGON_CLICK_GAP_S", 1.0)
    monkeypatch.setattr(sd, "VAGON_RELOAD_BACKOFF", (0.5,))

    async def body():
        async with Harness(tmp_path, "vagon_mock_stream.html", f"token={SECRET}&delay=100&noreconnect=1") as h:
            desk = h.desk
            assert await until(lambda: desk.vagon.connected, 30), desk.vagon.phase
            await h.frame.evaluate("window.__endSession()")
            assert await until(lambda: desk.vagon.reloads >= 1, 15), (desk.vagon.phase, desk.vagon.reloads)
            assert await until(lambda: desk.vagon.connected and desk.vagon.sessions == 2, 30), desk.vagon.phase
            state = await h.state()
            assert state["vagon"]["reloads"] == 1 and state["vagon"]["reconnects"] == 1
            assert await h.frame.evaluate("window.__connects") == 1                 # a fresh page: its own first connect
            opened = [e for e in events_of(h.events.path) if e["kind"] == "vagon" and e.get("state") == "open"]
            assert len(opened) == 2 and all(e["host"] == f"http://127.0.0.1:{h.server.port}/…" for e in opened)
    run(body())


@needs_browser
def test_vagon_mode_finds_the_stream_inside_the_dashboard_iframe_embed(tmp_path, monkeypatch):
    monkeypatch.setattr(sd, "VAGON_TICK_S", 0.3)
    monkeypatch.setattr(sd, "VAGON_CLICK_GAP_S", 1.0)
    monkeypatch.setattr(sd, "VAGON_SETTLE_S", 0.3)

    async def body():
        async with Harness(tmp_path, "vagon_mock_embed.html", f"token={SECRET}&delay=200") as h:
            desk = h.desk
            assert await until(lambda: desk.vagon.connected, 30), desk.vagon.phase
            assert desk._vagon_frame is not None and desk._vagon_frame is not desk.page.main_frame
            assert desk._vagon_offset == (0.0, 40.0)                                  # the embed's top bar
            await h.mock_events(clear=True)
            res = await h.act(action="click", point=[640, 360])
            ev = await h.mock_events(clear=True)
            down = next(e for e in ev if e["kind"] == "mousedown")
            assert res["ok"] is True and (down["x"], down["y"]) == (960, 500)         # frame coordinates: 540 - 40
            # a dialog of the PARENT page over the stream's iframe: the frame's own hit test cannot see it; refused
            await desk.page.evaluate("""() => { const d = document.createElement('div'); d.id = 'parent-dialog';
              d.style.cssText = 'position:fixed;left:800px;top:400px;width:300px;height:200px;background:#fff;z-index:9';
              document.body.appendChild(d); }""")
            res = await h.act(action="click", point=[640, 360])
            assert res["ok"] is False and "over the stream's frame" in res["outcome"]["errors"][0]
            assert not [e for e in await h.mock_events(clear=True) if e["kind"] in ("mousedown", "click")]
            await desk.page.evaluate("document.getElementById('parent-dialog').remove()")
            await h.act(action="type", text="abc")
            assert typed(await h.mock_events(clear=True)) == "abc"
            obs = await (await h.http.get("/desktop/observe", headers=AUTH)).json()
            assert obs["mode"] == "vagon" and obs["remote_ready"] is True
            assert obs["title"] == "Mock stream"                                       # the frame that streams, not the shell
            assert obs["url"] == f"http://127.0.0.1:{h.server.port}/…" and SECRET not in json.dumps(obs)
    run(body())
