"""Workstation kind of the Vagon mode (scripts/streamer_desktop.py --pc-mode vagon, vagon.json kind "workstation": the
owner's Vagon Cloud Computer behind HIS login).

Part 1: pure logic (the navigation lock, the login/dashboard classifier, the button choice, the config file, the operator
input validation, the neutral frame, the Teams API wrapper against a fake HTTP opener) and the HTTP routes against stub
desks: no browser, no network, no Vagon.
Part 2: a real headless Chromium on MOCK pages (tests/fixtures/vagon_mock_login.html, vagon_mock_workstation.html,
vagon_mock_account.html, served by a loopback test server): the login page is detected, the operator console is served
only then and forwards the owner's input (with the token, never without), the login survives a restart in the profile,
Run/Connect/Reconnect are pressed, the model and the monitor get a neutral picture until the desktop is connected, account
pages and external sites are blocked, and the console page works behind a path prefix in a second real browser.
Part 3: the input path on the connected remote desktop (proven live on 2026-10-23): a lone modifier key, keys only after
the stream element took the focus (fail closed), chords held past Vagon's 15 ms AltGr window, clicks/wheel only where the
stream element is under the point (checked before and after the move), VAGON_HIT_JS and the init scripts in a real
headless Chromium (host selection cleared, host defaults cancelled after the player, counters without key values, no
typed text in the diag, data-channel sends counted per label), the RTC summary and the diag schedule.
Nothing here talks to Vagon; the password typed into the mock is a test constant."""

import asyncio
import base64
import glob
import importlib.util
import io
import json
import os
import re
import sys
import time
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parent.parent
if "streamer_desktop" in sys.modules:
    sd = sys.modules["streamer_desktop"]
else:
    spec = importlib.util.spec_from_file_location("streamer_desktop", ROOT / "scripts/streamer_desktop.py")
    sd = importlib.util.module_from_spec(spec)
    sys.modules["streamer_desktop"] = sd
    spec.loader.exec_module(sd)
FIXTURES = ROOT / "tests" / "fixtures"
TOKEN = "operator-credential-test"
AUTH = {"X-Admin-Token": TOKEN}
WS = "https://app.vagon.io/workstation"
MOCK_PASSWORD = "mock-password-1"                    # accepted by the mock login page; a test constant, not a credential
MOCK_SECRET = "mock-secret-value-7c1d"               # the fake API secret; must never appear in logs or events


def run(coro):
    asyncio.run(coro)


def events_of(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def mean_rgb(jpeg_or_png):
    return ImageStat.Stat(Image.open(io.BytesIO(jpeg_or_png)).convert("RGB")).mean


def is_neutral(picture):
    """The grey "PC not connected" picture (re-encoded by build_observation or render_frame, so compared by colour)."""
    expected = mean_rgb(sd.neutral_jpeg(sd.SMALL))
    return all(abs(a - b) < 4 for a, b in zip(mean_rgb(picture), expected))


# --- the navigation lock ----------------------------------------------------------------------------------------------
def test_workstation_url_problem_keeps_the_page_on_its_site_and_off_the_account_pages():
    ok = lambda u: sd.workstation_url_problem(u, WS)
    assert ok(WS) is None and ok("https://app.vagon.io/workstation/connect?x=1") is None and ok("https://app.vagon.io/") is None
    assert ok("https://app.vagon.io/login") is None and ok("https://app.vagon.io/auth/callback?code=x") is None
    assert ok("https://login.vagon.io/signin") is None                                   # a sibling host of the site
    assert ok("https://stream.vagon.io/session/abc") is None and ok("https://vagon.io/") is None
    assert ok("https://app.vagon.io/team/billing") == "account-page" and ok("https://app.vagon.io/settings") == "account-page"
    for path in ("/billing", "/payments", "/invoices", "/subscription", "/plans", "/team", "/members", "/organization",
                 "/account", "/profile", "/api-keys", "/usage", "/files", "/register", "/signup", "/users/1", "/credits"):
        assert ok("https://app.vagon.io" + path) == "account-page", path
    assert ok("https://app.vagon.io/account/login") is None                                # a login flow wins
    assert ok("https://accounts.google.com/o/oauth2") == "external" and ok("https://example.com/") == "external"
    assert ok("https://evil-vagon.io/workstation") == "external" and ok("https://vagon.io.evil.com/") == "external"
    assert ok("http://app.vagon.io/workstation") == "scheme" and ok("https://u:p@app.vagon.io/workstation") == "credentials-in-url"
    assert ok("") == "expected a URL" and ok(None) == "expected a URL" and ok("https://app.vagon.io/a b") == "expected a URL"
    local = "http://127.0.0.1:8080/app/workstation?mocklogin=1"
    assert sd.workstation_url_problem(local, local) == "scheme"                             # tests need allow_private
    assert sd.workstation_url_problem(local, local, allow_private=True) is None
    assert sd.workstation_url_problem("http://127.0.0.1:8080/app/login?next=x", local, True) is None
    assert sd.workstation_url_problem("http://127.0.0.1:8080/app/team/billing", local, True) == "account-page"
    assert sd.workstation_url_problem("http://127.0.0.1:9090/x", local, True) == "external"   # another port: another server
    assert sd.workstation_url_problem("http://127.0.0.2/x", local, True) == "external"


def test_workstation_request_rules_allow_a_login_post_and_site_resources():
    rb = lambda url, main, method="GET": sd.workstation_request_blocked(url, WS, main, method)
    assert rb("https://app.vagon.io/login", True, "POST") is None                             # a login form may submit
    assert rb("https://app.vagon.io/workstation", True, "PUT") == "method"
    assert rb("https://app.vagon.io/team/billing", True) == "account-page"
    assert rb("https://example.com/", True) == "external"
    assert rb("https://login.vagon.io/static/app.js", False) is None                          # site resources
    assert rb("https://fonts.gstatic.com/font.woff2", False) is None                          # a CDN: generic host rules
    assert rb("https://accounts.google.com/gsi/client", False) in ("login", "owner-service")  # never the owner's services
    assert rb("https://www.paypal.com/sdk.js", False) == "banking"
    assert rb("about:blank", True) is None and rb("data:text/plain,x", False) is None


# --- buttons, login page, phases ----------------------------------------------------------------------------------------
def btn(label, x=800, y=500, w=200, h=60):
    return {"label": label, "box": [x, y, w, h]}


def probe(text="", buttons=(), stream=None, url=WS, passwords=0, vw=1920, vh=1080, main=None):
    p = {"url": url, "title": "Vagon", "vw": vw, "vh": vh, "loading": False, "text": text, "buttons": list(buttons),
         "stream": stream, "passwords": passwords}
    p["main"] = main if main is not None else {"url": url, "title": "Vagon", "text": text, "passwords": passwords, "vw": vw, "vh": vh}
    return p


BIG_CANVAS = {"tag": "canvas", "box": [0, 56, 1920, 1024], "playing": True}
SMALL_CANVAS = {"tag": "canvas", "box": [700, 400, 400, 225], "playing": True}
VIDEO = {"tag": "video", "box": [0, 0, 1920, 1080], "playing": True}
STALLED = {"tag": "video", "box": [0, 0, 1920, 1080], "playing": False}


def test_choose_workstation_button_ranks_reconnect_connect_start_and_never_the_dangerous_ones():
    choose = sd.choose_workstation_button
    assert choose([btn("Settings"), btn("Run"), btn("Sign out")]) == (1, "start")
    assert choose([btn("Turn on"), btn("Billing")]) == (0, "start") and choose([btn("Start")]) == (0, "start")
    assert choose([btn("Run"), btn("Connect")]) == (1, "connect") and choose([btn("Open"), btn("Enter")]) == (0, "connect")
    assert choose([btn("Connect"), btn("Reconnect")]) == (1, "reconnect") and choose([btn("Try again")]) == (0, "reconnect")
    assert choose([btn("Go to my computer")]) == (0, "connect")
    for label in ("Stop", "Shut down", "Turn off", "Delete", "Reset", "Restart", "Sign out", "Log out", "Invite", "Settings",
                  "Billing", "Team", "Members", "Profile", "Upgrade", "Buy now", "Subscribe", "Sign in", "Log in", "Download",
                  "Open settings", "Start your free trial plan", "Connect your wallet", "Open in new tab", "Running"):
        assert choose([btn(label)]) == (None, None), label
    assert choose([btn("x" * 70)]) == (None, None) and choose([]) == (None, None) and choose(None) == (None, None)


def test_login_page_reason():
    assert sd.login_page_reason("/login", 0, "") == "path" and sd.login_page_reason("/auth/callback", 0, "") == "path"
    assert sd.login_page_reason("/workstation", 1, "") == "password field"
    assert sd.login_page_reason("/workstation", 0, "Welcome back. Sign in to continue") == "sign-in text"
    assert sd.login_page_reason("/workstation", 0, "Please sign in", [btn("Connect")]) is None   # a control: no login page
    assert sd.login_page_reason("/workstation", 0, "Mock Team Sign out Your computer is on", [btn("Connect")]) is None
    assert sd.login_page_reason("/workstation", 0, "Logged in as owner", []) is None
    assert sd.login_page_reason("", 0, "") is None


def test_classify_workstation_phases():
    c = sd.classify_workstation
    login = c(probe("Sign in", [btn("Sign in"), btn("Continue with Google")], url="https://app.vagon.io/login", passwords=1))
    assert (login["phase"], login["why"], login["button"]) == ("login_required", "path", None)
    assert c(probe("Welcome back", passwords=1))["why"] == "password field"
    assert c(probe("Mock Team Your computer is off", [btn("Run"), btn("Sign out"), btn("Billing")])) == \
        {"phase": "dashboard", "button": 0, "kind": "start", "machine": "off", "why": ""}
    assert c(probe("Your computer is on", [btn("Connect"), btn("Stop")])) == \
        {"phase": "dashboard", "button": 0, "kind": "connect", "machine": "on", "why": ""}
    assert c(probe("Starting your computer...")) == {"phase": "starting", "button": None, "kind": None, "machine": "starting", "why": ""}
    assert c(probe("Your computer is turning on, please wait"))["phase"] == "starting"
    assert c(probe("Connecting..."))["phase"] == "connecting" and c(probe("", [], STALLED))["phase"] == "connecting"
    assert c(probe("", [btn("Stop")], BIG_CANVAS)) == {"phase": "connected", "button": None, "kind": None, "machine": "on", "why": ""}
    assert c(probe("", [], VIDEO))["phase"] == "connected"
    assert c(probe("Usage this month", [], SMALL_CANVAS))["phase"] == "blank"              # a chart is not the desktop
    assert c(probe("Your session has ended.", [btn("Reconnect")])) == {"phase": "ended", "button": 0, "kind": "reconnect", "machine": "unknown", "why": ""}
    assert c(probe("You were disconnected"))["phase"] == "ended" and c(probe("Session ended", [], BIG_CANVAS))["phase"] == "ended"
    assert c(probe("", [btn("Reconnect")], BIG_CANVAS))["phase"] == "ended"
    assert c(probe("Billing", [], url="https://app.vagon.io/team/billing"))["phase"] == "blocked"
    assert c(probe("Checking..."))["phase"] == "blank" and c(None)["phase"] == "blank" and c({})["phase"] == "blank"
    # the stream lives in an iframe: the main frame says where we are, the frame says what is shown
    embed = probe("", [], BIG_CANVAS, url="https://stream.vagon.io/x", main={"url": WS, "text": "Mock Team", "passwords": 0, "vw": 1920, "vh": 1080})
    assert c(embed)["phase"] == "connected"
    embed_login = probe("", [], None, url="https://stream.vagon.io/x", main={"url": "https://app.vagon.io/login", "text": "", "passwords": 0, "vw": 1920, "vh": 1080})
    assert c(embed_login)["phase"] == "login_required"
    seen = {c(p)["phase"] for p in (login, probe("", [], VIDEO), probe("Run", [btn("Run")]), probe("Connecting"), probe("Session ended"), probe(""))}
    assert seen <= set(sd.VAGON_WS_PHASES)
    assert set(c(p)["machine"] for p in (probe("", [btn("Run")]), probe("", [btn("Connect")]), probe("Starting your computer"), probe(""))) <= set(sd.VAGON_MACHINE_STATES)


def test_load_vagon_config_workstation_kind(tmp_path):
    path = tmp_path / "vagon.json"
    path.write_text(json.dumps({"schema": sd.VAGON_SCHEMA, "kind": "workstation"}))
    assert sd.load_vagon_config(path) == {"kind": "workstation", "stream_url": WS, "api_key_file": "", "machine_id": ""}
    path.write_text(json.dumps({"schema": sd.VAGON_SCHEMA, "kind": "workstation", "url": "https://app.vagon.io/workstation?x=1",
                                "api_key_file": "/secret/vagon-api", "machine_id": "mach-1"}))
    assert sd.load_vagon_config(path) == {"kind": "workstation", "stream_url": "https://app.vagon.io/workstation?x=1",
                                          "api_key_file": "/secret/vagon-api", "machine_id": "mach-1"}
    bad = {"stream_url for a workstation": {"schema": sd.VAGON_SCHEMA, "kind": "workstation", "stream_url": WS},
           "url for streams": {"schema": sd.VAGON_SCHEMA, "url": WS},
           "unknown kind": {"schema": sd.VAGON_SCHEMA, "kind": "desktop"},
           "http": {"schema": sd.VAGON_SCHEMA, "kind": "workstation", "url": "http://app.vagon.io/workstation"},
           "account page": {"schema": sd.VAGON_SCHEMA, "kind": "workstation", "url": "https://app.vagon.io/team/billing"},
           "machine id": {"schema": sd.VAGON_SCHEMA, "kind": "workstation", "machine_id": "a b/c"},
           "secret in the file": {"schema": sd.VAGON_SCHEMA, "kind": "workstation", "api_secret": "abc"}}
    for name, data in bad.items():
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError) as info:
            sd.load_vagon_config(path)
        assert "abc" not in str(info.value) and "billing" not in str(info.value), name


def test_validate_operator():
    v = sd.validate_operator
    assert v({"type": "mouse", "x": 0.5, "y": 0.25}) == {"type": "mouse", "x": 0.5, "y": 0.25}
    assert v({"type": "mouse", "x": 0, "y": 1, "buttons": [True, False, False], "wheel": -120}) == \
        {"type": "mouse", "x": 0.0, "y": 1.0, "buttons": [True, False, False], "wheel": -120.0}
    assert v({"type": "key", "key": "Tab"}) == {"type": "key", "key": "Tab", "down": True}
    assert v({"type": "key", "key": "ShiftLeft", "down": False}) == {"type": "key", "key": "ShiftLeft", "down": False}
    assert v({"type": "text", "text": "hello\nworld"}) == {"type": "text", "text": "hello\nworld"}
    for bad in ({"type": "mouse", "x": 1.5, "y": 0}, {"type": "mouse", "x": "0", "y": 0}, {"type": "mouse", "x": 0, "y": 0, "buttons": [True]},
                {"type": "mouse", "x": 0, "y": 0, "wheel": 5000}, {"type": "key", "key": "Control+v"}, {"type": "key", "key": ""},
                {"type": "key", "key": "Tab", "down": 1}, {"type": "text", "text": ""}, {"type": "text", "text": "x" * 2001},
                {"type": "text", "text": "a\x00b"}, {"type": "paste"}, [], None):
        with pytest.raises(ValueError) as info:
            v(bad)
        assert "x" * 50 not in str(info.value)                                             # the text is never echoed


def test_neutral_jpeg_is_a_grey_picture_without_the_page():
    jpeg = sd.neutral_jpeg(sd.SMALL)
    img = Image.open(io.BytesIO(jpeg))
    assert img.size == (1280, 720) and jpeg == sd.neutral_jpeg(sd.SMALL)                  # cached
    mean = ImageStat.Stat(img.convert("RGB")).mean
    assert all(60 < m < 90 for m in mean) and Image.open(io.BytesIO(sd.neutral_jpeg((640, 360)))).size == (640, 360)


def test_vagon_state_public_fields_for_the_workstation():
    v = sd.VagonState("none", "workstation")
    pub = v.public()
    assert pub["kind"] == "workstation" and pub["phase"] == "opening" and pub["logged_in"] is False
    assert pub["machine"] == "unknown" and pub["blocked"] == 0 and pub["reconnects"] == 0 and pub["last_reconnect_utc"] is None
    assert json.dumps(pub)
    streams = sd.VagonState("none").public()
    assert streams["kind"] == "streams" and streams["phase"] == "starting" and "logged_in" not in streams and "machine" not in streams


def test_mod_name_knows_both_sides():
    assert sd.mod_name("ShiftLeft") == "Shift" and sd.mod_name("ControlRight") == "Control" and sd.mod_name("Control") == "Control"
    assert sd.mod_name("MetaLeft") == "Meta" and sd.mod_name("KeyA") is None and sd.mod_name("Left") is None


def ws_desktop(tmp_path, **cfg):
    config = sd.Config(profile=tmp_path / "profile", pc_mode="vagon", vagon_kind="workstation", vagon_url=WS, **cfg)
    return sd.Desktop(config, sd.Events(tmp_path / "events.jsonl"))


def test_operator_console_stays_available_while_not_connected_and_closes_only_when_connected(tmp_path, monkeypatch):
    desk = ws_desktop(tmp_path)
    now = [1000.0]
    monkeypatch.setattr(sd.time, "monotonic", lambda: now[0])
    assert desk.workstation is True and desk.privacy_locked() is True
    assert desk.operator_allowed() is True                                                  # opening: not connected -> served
    for phase in ("login_required", "dashboard", "starting", "connecting", "ended", "blocked", "blank"):
        desk.vagon.set_phase(phase)
        desk.vagon.logged_in = phase != "login_required"
        now[0] += 15 * 60                                                                  # far longer than any old grace
        assert desk.operator_allowed() is True, phase
    desk.vagon.set_phase("connecting")                                                      # the stall of 2026-10-23: 10+ minutes connecting
    now[0] += 11 * 60
    assert desk.operator_allowed() is True and desk.privacy_locked() is True
    desk.vagon.connected, desk.vagon.connected_at = True, now[0]                             # connected: a short grace, then closed
    desk.vagon.set_phase("connected")
    assert desk.operator_allowed() is True and desk.privacy_locked() is False
    now[0] += sd.OPERATOR_CONNECTED_GRACE_S + 1
    assert desk.operator_allowed() is False
    desk.vagon.connected = False                                                            # the session dropped: served again at once
    assert desk.operator_allowed() is True
    flagged = ws_desktop(tmp_path / "b", operator_console=True)
    flagged.vagon.connected = True
    assert flagged.operator_allowed() is True
    streams = sd.Desktop(sd.Config(profile=tmp_path / "c", pc_mode="vagon", vagon_url="https://app.vagon.io/stream/x"), sd.Events(tmp_path / "c.jsonl"))
    assert streams.workstation is False and streams.operator_allowed() is False and streams.privacy_locked() is False
    chromium = sd.Desktop(sd.Config(profile=tmp_path / "d"), sd.Events(tmp_path / "d.jsonl"))
    assert chromium.operator_allowed() is False and chromium.privacy_locked() is False


# --- the optional Teams API, against a fake HTTP opener --------------------------------------------------------------------
class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self):
        self.answer, self.calls = b"{}", []

    def open(self, req, timeout=None):
        self.calls.append(req)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return FakeResponse(self.answer)


def machines(status):
    return json.dumps({"machines": [{"id": "mach-1", "attributes": {"friendly_status": status}}]}).encode()


def test_vagon_api_reads_the_key_file_signs_with_it_and_never_shows_the_secret(tmp_path, monkeypatch, capsys):
    key = tmp_path / "vagon-api"
    key.write_text(f"mock-public-key:{MOCK_SECRET}\n")
    key.chmod(0o644)
    with pytest.raises(ValueError, match="permissive"):
        sd.VagonApi.load(str(key), "mach-1")
    key.chmod(0o600)
    with pytest.raises(ValueError, match="machine_id"):
        sd.VagonApi.load(str(key), "")
    with pytest.raises(ValueError, match="missing"):
        sd.VagonApi.load(str(tmp_path / "nope"), "mach-1")
    (tmp_path / "bad").write_text("just-one-token\n")
    (tmp_path / "bad").chmod(0o600)
    with pytest.raises(ValueError, match="KEY:SECRET"):
        sd.VagonApi.load(str(tmp_path / "bad"), "mach-1")
    for name in ("VAGON_API_KEY", "VAGON_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    fake = FakeOpener()
    monkeypatch.setattr(sd.vagon_pc, "_OPENER", fake)
    api = sd.VagonApi.load(str(key), "mach-1")
    assert api.machine() == "unknown" and api.fresh() is False
    fake.answer = machines("off")
    assert api.refresh() == "off" and api.error == "" and api.fresh() is True
    auth = fake.calls[-1].get_header("Authorization")
    assert auth.startswith("HMAC mock-public-key:") and MOCK_SECRET not in auth and fake.calls[-1].full_url.endswith("/machines")
    assert "VAGON_API_KEY" not in os.environ and "VAGON_API_SECRET" not in os.environ      # the pair stays in memory
    fake.answer = b"{}"
    assert api.start() == "" and api.machine() == "starting" and api.starts == 1
    assert fake.calls[-1].full_url.endswith("/machines/mach-1/start") and fake.calls[-1].get_method() == "POST"
    for status, state in (("turning_on", "starting"), ("ready", "on"), ("stopped", "off"), ("weird", "unknown")):
        fake.answer = machines(status)
        assert api.refresh() == state
    fake.answer = urllib.error.HTTPError("https://api.vagon.io/x", 401, "msg", {}, io.BytesIO(json.dumps({"message": "bad " + MOCK_SECRET}).encode()))
    assert api.refresh() == "unknown" and "HTTP 401" in api.error and MOCK_SECRET not in api.error
    assert MOCK_SECRET not in api.start()
    two = tmp_path / "two-lines"
    two.write_text(f"mock-public-key\n{MOCK_SECRET}\n")
    two.chmod(0o600)
    assert sd.VagonApi.load(str(two), "mach-1")._credentials == ("mock-public-key", MOCK_SECRET)
    assert MOCK_SECRET not in capsys.readouterr().out


class FakeApi:
    """Stands in for VagonApi: a scripted machine state."""

    def __init__(self, state="off"):
        self.state, self.error, self.started_at, self.starts, self.read_at, self.status = state, "", 0.0, 0, 0.0, None
        self.calls = []

    def refresh(self):
        self.calls.append("refresh")
        self.read_at, self.status = time.monotonic(), self.state
        return self.state

    def machine(self):
        return self.state

    def fresh(self, within=None):
        return self.status is not None

    def start(self):
        self.calls.append("start")
        self.started_at, self.starts = time.monotonic(), self.starts + 1
        return self.error


def test_api_start_and_the_status_loop_feed_the_machine_field(tmp_path, monkeypatch, capsys):
    async def body():
        desk = ws_desktop(tmp_path)
        r = await desk.api_start("test")
        assert r["ok"] is False and "not configured" in r["error"]
        desk.api = FakeApi("off")
        r = await desk.api_start("operator request")
        assert r == {"ok": True, "machine": "starting", "started": True, "error": ""} and desk.vagon.machine == "starting"
        assert desk.vagon.machine_source == "api"
        r = await desk.api_start("operator request")                                          # too soon: not again
        assert r["ok"] is False and r["started"] is False and "a moment ago" in r["error"] and desk.api.starts == 1
        desk.api = FakeApi("on")
        r = await desk.api_start("operator request")
        assert r == {"ok": True, "machine": "on", "started": False, "error": ""}
        desk.api.error = "POST /machines/x/start failed with HTTP 403 (this key may not do that)"
        desk.api.state = "off"
        r = await desk.api_start("x")
        assert r["ok"] is False and "HTTP 403" in r["error"]
        monkeypatch.setattr(sd, "VAGON_API_POLL_S", 0.02)
        desk.api = FakeApi("on")
        try:
            await asyncio.wait_for(desk._api_loop(), 0.15)
        except asyncio.TimeoutError:
            pass
        assert desk.vagon.machine == "on" and desk.vagon.machine_source == "api" and desk.api.calls.count("refresh") >= 2
        desk._set_machine("off", "page")                                                      # a fresh API reading wins over the page
        assert desk.vagon.machine == "on"
        kinds = [(e["kind"], e.get("action")) for e in events_of(tmp_path / "events.jsonl")]
        assert ("vagon_api", "start") in kinds
    run(body())


# --- the HTTP routes against stub desks ------------------------------------------------------------------------------------
class StubDesk:
    def __init__(self, mode="vagon", kind="workstation", allowed=False):
        self.status, self.restarts, self.error, self.allowed = "ready", 0, "", allowed
        self.feed, self.cfg = sd.FrameFeed(epoch="abc123"), SimpleNamespace(pc_mode=mode, vagon_kind=kind)
        self.vagon, self.api, self.inputs, self.jpeg = sd.VagonState("none", kind), None, [], None
        self.workstation = mode == "vagon" and kind == "workstation"

    def request_reload(self, why):
        self.vagon.reload_requested = True
        return self.vagon.public()

    def display(self):
        return self.feed.display()

    async def release_inputs(self):
        pass

    def operator_allowed(self):
        return self.allowed

    def operator_frame(self):
        return ("op-7", self.jpeg) if self.jpeg else None

    async def operator_input(self, clean):
        self.inputs.append(clean)
        return True

    async def api_start(self, why):
        return {"ok": True, "machine": "starting", "started": True, "error": ""}

    def take_start(self, why):                                                          # armed in these route tests
        return True


async def client_for(desk, tmp_path):
    runner = sd.Runner(desk, TOKEN, sd.Events(tmp_path / "e.jsonl"))
    http = TestClient(TestServer(sd.create_app(runner)))
    await http.start_server()
    return runner, http


def test_pc_state_carries_the_workstation_fields(tmp_path):
    async def body():
        desk = StubDesk()
        runner, http = await client_for(desk, tmp_path)
        try:
            v = (await (await http.get("/pc/state", headers=AUTH)).json())["vagon"]
            assert v["kind"] == "workstation" and v["phase"] == "opening" and v["logged_in"] is False and v["machine"] == "unknown"
            assert v["blocked"] == 0 and v["operator_console"] is False and v["reconnects"] == 0 and v["last_reconnect_utc"] is None
            desk.vagon.set_phase("login_required")
            desk.vagon.login_why = "path"
            desk.allowed, desk.vagon.machine, desk.vagon.blocked = True, "off", 2
            v = (await (await http.get("/pc/state", headers=AUTH)).json())["vagon"]
            assert v["phase"] == "login_required" and v["operator_console"] is True and v["machine"] == "off" and v["blocked"] == 2
            assert v["login_why"] == "path"
            plain = (await (await http.get("/pc/state", headers=AUTH)).json())
            assert set(plain["vagon"]) >= {"connected", "phase", "reconnects", "last_reconnect_utc", "kind", "logged_in", "machine"}
        finally:
            await http.close()
    run(body())


def test_operator_routes_are_served_only_when_allowed_and_need_the_token(tmp_path):
    async def body():
        desk = StubDesk()
        runner, http = await client_for(desk, tmp_path)
        try:
            r = await http.get("/operator")                                                    # no token needed for the page...
            assert r.status == 404 and "login_required" in await r.text() and "--operator-console" in await r.text()
            assert (await http.get("/operator/frame.jpg", headers=AUTH)).status == 404
            assert (await http.post("/operator/input", json={"type": "key", "key": "Tab"}, headers=AUTH)).status == 404
            desk.allowed = True
            r = await http.get("/operator")
            html = await r.text()
            assert r.status == 200 and r.headers["Content-Type"].startswith("text/html") and "<title>SUB-01 PC operator console" in html
            assert "Content-Security-Policy" in r.headers and r.headers["Cache-Control"] == "no-store"
            assert not re.search(r"""(src|href)=["']https?://""", html) and "<link" not in html     # self-contained: no external asset
            assert not re.search(r"""fetch\(\s*["'`]/""", html) and "'/operator" not in html and '"/pc/' not in html   # relative URLs only
            assert "sessionStorage" in html and "X-Admin-Token" in html and TOKEN not in html
            assert (await http.get("/operator/frame.jpg")).status == 403                      # ...but the frame and the input do
            assert (await http.post("/operator/input", json={"type": "key", "key": "Tab"})).status == 403
            assert (await http.post("/operator/input", json={"type": "key", "key": "Tab"}, headers={"X-Admin-Token": "wrong-token-value"})).status == 403
            assert desk.inputs == []
            r = await http.get("/operator/frame.jpg", headers=AUTH)
            assert r.status == 404 and "No desktop frame" in await r.text()
            desk.jpeg = sd.neutral_jpeg((64, 36))
            r = await http.get("/operator/frame.jpg", headers=AUTH)
            assert r.status == 200 and r.headers["Content-Type"] == "image/jpeg" and await r.read() == desk.jpeg
            assert (await http.get("/operator/frame.jpg", headers={**AUTH, "If-None-Match": r.headers["ETag"]})).status == 304
            r = await http.post("/operator/input", json={"type": "mouse", "x": 0.5, "y": 0.5, "buttons": [True, False, False]}, headers=AUTH)
            assert r.status == 200 and await r.json() == {"ok": True}
            r = await http.post("/operator/input", json={"type": "text", "text": "hello"}, headers=AUTH)
            assert r.status == 200 and desk.inputs[-1] == {"type": "text", "text": "hello"}
            assert (await http.post("/operator/input", json={"type": "mouse", "x": 2, "y": 0}, headers=AUTH)).status == 400
            assert (await http.post("/operator/input", json={"type": "key", "key": "Control+v"}, headers=AUTH)).status == 400
            await http.post("/pc/privacy", json={"active": True}, headers=AUTH)
            assert (await http.get("/operator/frame.jpg", headers=AUTH)).status == 409        # bathroom privacy: nothing shown
            assert (await http.post("/operator/input", json={"type": "text", "text": "x"}, headers=AUTH)).status == 409
            await http.post("/pc/privacy", json={"active": False}, headers=AUTH)
            assert (await http.post("/pc/vagon/start", headers=AUTH)).status == 409            # no API configured
            desk.api = FakeApi()
            r = await http.post("/pc/vagon/start", headers=AUTH)
            assert r.status == 200 and (await r.json())["started"] is True
            assert (await http.post("/pc/vagon/start")).status == 403
            assert (await http.post("/pc/vagon/reload")).status == 403                          # the owner's reload needs the token
            r = await http.post("/pc/vagon/reload", headers=AUTH)
            assert r.status == 200 and (await r.json())["reload_requested"] is True and desk.vagon.reload_requested is True
            text = (tmp_path / "e.jsonl").read_text()
            assert "hello" not in text and '"operator"' in text                                # the console is logged, its input never
        finally:
            await http.close()
    run(body())


def test_main_resolves_the_workstation_kind(tmp_path, monkeypatch, capsys):
    token = tmp_path / "token"
    token.write_text("operator-credential-test\n")
    base = ["--token-file", str(token), "--data-dir", str(tmp_path / "d"), "--streamer-dir", str(tmp_path / "nothing")]
    seen = []

    async def fake_serve(args):
        seen.append(args)
    monkeypatch.setattr(sd, "serve", fake_serve)
    sd.main(base + ["--pc-mode", "vagon", "--vagon-kind", "workstation"])                   # no file needed: the default page
    a = seen[-1]
    assert a.pc_mode == "vagon" and a.vagon_kind == "workstation" and a.vagon_url == WS and a.operator_console is False
    sd.main(base + ["--pc-mode", "vagon", "--vagon-kind", "workstation", "--operator-console", "--vagon-url", "https://app.vagon.io/workstation?x=1"])
    assert seen[-1].operator_console is True and seen[-1].vagon_url == "https://app.vagon.io/workstation?x=1"
    conf = tmp_path / "streamer" / "vagon.json"
    conf.parent.mkdir()
    conf.write_text(json.dumps({"schema": sd.VAGON_SCHEMA, "kind": "workstation", "api_key_file": str(tmp_path / "key"), "machine_id": "mach-1"}))
    sd.main(["--token-file", str(token), "--data-dir", str(tmp_path / "d"), "--pc-mode", "vagon", "--streamer-dir", str(conf.parent)])
    a = seen[-1]
    assert a.vagon_kind == "workstation" and a.vagon_url == WS and a.vagon_api_key_file == str(tmp_path / "key") and a.vagon_machine_id == "mach-1"
    for argv in (["--pc-mode", "vagon", "--vagon-kind", "workstation", "--vagon-url", "https://app.vagon.io/team/billing"],
                 ["--pc-mode", "vagon", "--vagon-kind", "workstation", "--vagon-url", "http://app.vagon.io/workstation"],
                 ["--operator-console"], ["--vagon-kind", "workstation"]):
        with pytest.raises(SystemExit):
            sd.main(base + argv)
    err = capsys.readouterr().err
    assert "billing" not in err                                                               # the page is never echoed
    sd.main(base)
    assert seen[-1].pc_mode == "chromium"


def test_operator_input_reaches_the_page_through_fake_playwright(tmp_path):
    class Keyboard:
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

    class Mouse:
        def __init__(self):
            self.log = []

        async def move(self, x, y, steps=1):
            self.log.append(("move", round(x), round(y)))

        async def down(self, button="left"):
            self.log.append(("down", button))

        async def up(self, button="left"):
            self.log.append(("up", button))

        async def wheel(self, dx, dy):
            self.log.append(("wheel", dx, dy))

    async def body():
        desk = ws_desktop(tmp_path)
        desk.status, desk.page, desk.view = "ready", SimpleNamespace(keyboard=Keyboard(), mouse=Mouse()), (1920, 1080)
        desk._input_lock = asyncio.Lock()
        kb, mouse = desk.page.keyboard.log, desk.page.mouse.log
        assert await desk.operator_input({"type": "mouse", "x": 0.5, "y": 0.5, "buttons": [True, False, False]}) is True
        assert await desk.operator_input({"type": "mouse", "x": 0.5, "y": 0.5, "buttons": [False, False, False]}) is True
        assert mouse == [("move", 960, 540), ("down", "left"), ("move", 960, 540), ("up", "left")] and desk.cursor == [960.0, 540.0]
        mouse.clear()
        assert await desk.operator_input({"type": "mouse", "x": 0.25, "y": 0.5, "wheel": -120}) is True
        assert mouse == [("move", 480, 540), ("wheel", 0, -120.0)]
        assert await desk.operator_input({"type": "text", "text": "owner@example.test\n"}) is True
        assert kb == [("type", "owner@example.test"), ("press", "Enter")]
        kb.clear()
        for key, down in (("ShiftLeft", True), ("Tab", True), ("Tab", False), ("ShiftLeft", False)):
            assert await desk.operator_input({"type": "key", "key": key, "down": down}) is True
        assert kb == [("down", "ShiftLeft"), ("down", "Tab"), ("up", "Tab"), ("up", "ShiftLeft")] and desk.held == set()
        kb.clear()
        assert await desk.operator_input({"type": "key", "key": "ControlLeft", "down": True}) is True
        assert await desk.operator_input({"type": "key", "key": "KeyV", "down": True}) is False      # clipboard combos stay dropped
        assert await desk.operator_input({"type": "key", "key": "KeyV", "down": False}) is True
        assert await desk.operator_input({"type": "key", "key": "KeyA", "down": True}) is True       # Ctrl+A is fine
        assert await desk.operator_input({"type": "key", "key": "ControlLeft", "down": False}) is True
        assert kb == [("down", "ControlLeft"), ("down", "KeyA"), ("up", "ControlLeft")]
        desk.status = "restarting"
        assert await desk.operator_input({"type": "text", "text": "x"}) is False
    run(body())


# --- integration: a real headless Chromium on the mock workstation ------------------------------------------------------------
def chromium_executable():
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


async def until_async(predicate, timeout=30.0, step=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if await predicate():
                return True
        except Exception:
            pass
        await asyncio.sleep(step)
    return False


def mock_site():
    """The mock Vagon site: /app/login, /app/workstation, and account pages the kiosk must never show."""
    def page(name):
        async def handler(request):
            return web.Response(text=(FIXTURES / name).read_text(encoding="utf-8"), content_type="text/html")
        return handler
    app = web.Application()
    app.router.add_get("/app/login", page("vagon_mock_login.html"))
    app.router.add_get("/app/workstation", page("vagon_mock_workstation.html"))
    for path in ("/app/team/billing", "/app/settings", "/app/register", "/app/forgot"):
        app.router.add_get(path, page("vagon_mock_account.html"))
    return app


def external_site():
    async def page(request):
        return web.Response(text="<title>EXTERNAL</title>EXTERNAL-PAGE", content_type="text/html")
    app = web.Application()
    app.router.add_get("/x", page)
    return app


def proxy_app(target_port):
    """A path-prefix reverse proxy like the pod's Jupyter server proxy: /proxy/8832/<path> -> 127.0.0.1:<port>/<path>."""
    async def relay(request):
        url = f"http://127.0.0.1:{target_port}/{request.match_info['tail']}" + (f"?{request.query_string}" if request.query_string else "")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length", "transfer-encoding")}
        async with ClientSession() as session:
            async with session.request(request.method, url, headers=headers, data=await request.read(), allow_redirects=False) as r:
                body = await r.read()
                keep = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "etag", "cache-control", "content-security-policy")}
                return web.Response(status=r.status, body=body, headers=keep)
    app = web.Application()
    app.router.add_route("*", "/proxy/8832/{tail:.*}", relay)
    return app


class Harness:
    """The mock site, a Desktop in the workstation kind on a real headless Chromium, the Runner and its HTTP app."""

    def __init__(self, tmp_path, monkeypatch, logged_in=False, operator_console=False, delay=250, autostart=True):
        monkeypatch.setattr(sd, "VAGON_TICK_S", 0.3)
        monkeypatch.setattr(sd, "VAGON_CLICK_GAP_S", 1.0)
        monkeypatch.setattr(sd, "VAGON_SETTLE_S", 0.3)
        monkeypatch.setattr(sd, "VAGON_NAV_SETTLE_S", 0.3)
        monkeypatch.setattr(sd, "VAGON_RELOAD_BACKOFF", (0.5,))
        monkeypatch.setattr(sd, "OPERATOR_CONNECTED_GRACE_S", 0.0)                        # the console closes as soon as connected
        self.tmp_path, self.logged_in, self.operator_console, self.delay = tmp_path, logged_in, operator_console, delay
        self.autostart = autostart                                        # tests of other features start the mock computer
        self.site = self.external = self.desk = self.runner = self.http = self.events = self.cfg = None

    async def __aenter__(self):
        self.site, self.external = TestServer(mock_site()), TestServer(external_site())
        await self.site.start_server()
        await self.external.start_server()
        query = f"delay={self.delay}" + ("&mocklogin=1" if self.logged_in else "")
        self.url = f"http://127.0.0.1:{self.site.port}/app/workstation?{query}"
        self.cfg = sd.Config(profile=self.tmp_path / "profile", headless=True, kiosk=False, allow_private=True,
                             chromium=CHROMIUM or "", pc_mode="vagon", vagon_kind="workstation", vagon_url=self.url,
                             operator_console=self.operator_console, vagon_autostart=self.autostart)
        self.events = sd.Events(self.tmp_path / "events.jsonl")
        self.runner = sd.Runner(StubDesk(), TOKEN, self.events, allow_private=True)
        self.http = TestClient(TestServer(sd.create_app(self.runner)))
        await self.http.start_server()
        await self.start_desktop()
        return self

    async def start_desktop(self):
        self.desk = sd.Desktop(self.cfg, self.events)
        self.runner.desk, self.desk.on_change = self.desk, self.runner.notify
        self.desk.start()
        ok = await until(lambda: self.desk.status == "ready", 90)
        if not ok:
            await self.__aexit__(None, None, None)
            pytest.skip(f"chromium did not start here: {self.desk.error!r}"[:200])

    async def restart_desktop(self):
        await self.desk.close()
        await self.start_desktop()

    async def __aexit__(self, *exc):
        for step in (self.http and self.http.close(), self.desk and self.desk.close(), self.site and self.site.close(),
                     self.external and self.external.close()):
            if step is not None:
                try:
                    await step
                except Exception:
                    pass

    async def state(self):
        return await (await self.http.get("/pc/state", headers=AUTH)).json()

    async def observe(self):
        r = await self.http.get("/desktop/observe", headers=AUTH)
        assert r.status == 200, await r.text()
        return await r.json()

    async def act(self, **body):
        r = await self.http.post("/desktop/act", json=body, headers=AUTH)
        assert r.status == 200, await r.text()
        return await r.json()

    async def op(self, **body):
        r = await self.http.post("/operator/input", json=body, headers=AUTH)
        assert r.status == 200, await r.text()
        return await r.json()

    async def frac(self, selector):
        """Centre of an element of the kiosk page as fractions of the frame (what the console sends)."""
        box = await self.desk.page.locator(selector).bounding_box()
        w, h = self.desk.view
        return (box["x"] + box["width"] / 2) / w, (box["y"] + box["height"] / 2) / h

    async def mock(self, js):
        return await self.desk.page.evaluate(js)

    async def login_through_the_console(self):
        """What the owner does: click the e-mail field, type, Tab, type the password, Enter."""
        x, y = await self.frac("#email")
        await self.op(type="mouse", x=x, y=y)
        await self.op(type="mouse", x=x, y=y, buttons=[True, False, False])
        await self.op(type="mouse", x=x, y=y, buttons=[False, False, False])
        assert await until_async(lambda: self.mock("document.activeElement && document.activeElement.id === 'email'"), 5)
        await self.op(type="text", text="owner@example.test")
        await self.op(type="key", key="Tab", down=True)
        await self.op(type="key", key="Tab", down=False)
        assert await until_async(lambda: self.mock("document.activeElement.id === 'password'"), 5)
        await self.op(type="text", text=MOCK_PASSWORD)
        assert (await self.mock("window.__typed()")) == {"email": "owner@example.test", "password": MOCK_PASSWORD}
        await self.op(type="key", key="Enter", down=True)
        await self.op(type="key", key="Enter", down=False)


@needs_browser
def test_login_required_console_login_then_run_connect_with_the_privacy_lock(tmp_path, monkeypatch, capsys):
    async def body():
        async with Harness(tmp_path, monkeypatch, autostart=False) as h:
            desk = h.desk
            # 1. the page needs a login: detected, console available, nothing of it reaches the model or the monitor
            assert await until(lambda: desk.vagon.phase == "login_required", 20), (desk.vagon.phase, desk.error)
            assert "/app/login" in desk.page.url and desk.vagon.logged_in is False and desk.operator_allowed() is True
            state = await h.state()
            assert state["vagon"]["kind"] == "workstation" and state["vagon"]["phase"] == "login_required"
            assert state["vagon"]["login_why"] == "path" and state["vagon"]["operator_console"] is True
            assert state["vagon"]["logged_in"] is False and state["vagon"]["machine"] == "unknown"
            obs = await h.observe()
            assert obs["mode"] == "vagon" and obs["remote_ready"] is False and obs["text"] == "" and obs["marks"] == []
            assert obs["title"] == "remote desktop" and obs["url"] == f"http://127.0.0.1:{h.site.port}/…"
            assert is_neutral(base64.b64decode(obs["jpeg_b64"])), "the model saw the login page"
            assert await until(lambda: desk.display()["available"], 10)
            frame = await h.http.get("/pc/frame.png", headers=AUTH)
            assert frame.status == 200 and is_neutral(await frame.read()), "the monitor saw the login page"
            assert await until(lambda: desk.operator_frame() is not None, 10)
            r = await h.http.get("/operator/frame.jpg", headers=AUTH)
            shown = await r.read()
            assert r.status == 200 and not is_neutral(shown) and mean_rgb(shown)[0] > 150     # the owner sees the real (light) login page
            assert (await h.http.get("/operator/frame.jpg")).status == 403
            assert (await h.http.get("/operator")).status == 200
            # the agent cannot act and cannot type into the login form
            res = await h.act(action="type", text="not-a-password")
            assert res["ok"] is False and "not connected (PC login_required)" in res["outcome"]["errors"][0]
            assert (await h.mock("window.__typed()")) == {"email": "", "password": ""}
            res = await h.act(action="click", point=[640, 360])
            assert res["ok"] is False
            # 2. the owner logs in through the console
            await h.login_through_the_console()
            assert await until(lambda: desk.vagon.logged_in and desk.vagon.phase != "login_required", 15), desk.vagon.phase
            # 3. the computer is off: not started until armed (it spends the owner's balance), then one start
            assert await until(lambda: desk.vagon.start_held, 15), (desk.vagon.phase, desk.vagon.machine)
            await asyncio.sleep(2.0)
            assert (await h.mock("window.__pressed")) == [] and desk.vagon.machine == "off"
            assert (await h.state())["vagon"]["start_held"] is True
            r = await h.http.post("/pc/vagon/arm", json={"minutes": 5}, headers=AUTH)
            assert r.status == 200 and (await r.json())["start_armed_s"] > 200
            assert (await h.http.post("/pc/vagon/arm", json={"minutes": 500}, headers=AUTH)).status == 400
            assert (await h.http.post("/pc/vagon/arm", json={"minutes": 5})).status in (401, 403)
            # off -> Run -> starting -> Connect -> connecting -> connected
            assert await until(lambda: desk.vagon.connected, 30), (desk.vagon.phase, desk.vagon.machine)
            assert desk.vagon.starts == 1 and desk.vagon.start_armed_until == 0.0                # one start per arming
            pressed = await h.mock("window.__pressed")
            assert pressed == ["run", "connect"], pressed                                       # never Stop, Sign out, Billing
            state = await h.state()
            assert state["vagon"]["phase"] == "connected" and state["vagon"]["machine"] == "on" and state["vagon"]["logged_in"] is True
            assert state["vagon"]["operator_console"] is False and state["vagon"]["sessions"] == 1
            assert (await h.http.get("/operator")).status == 404                              # the console is gone
            assert (await h.http.post("/operator/input", json={"type": "text", "text": "x"}, headers=AUTH)).status == 404
            obs = await h.observe()
            assert obs["remote_ready"] is True and not is_neutral(base64.b64decode(obs["jpeg_b64"]))
            assert obs["title"] == "remote desktop" and "Mock Team" not in json.dumps(obs)

            async def real_frame():
                r = await h.http.get("/pc/frame.png", headers=AUTH)
                return r.status == 200 and not is_neutral(await r.read())
            assert await until_async(real_frame, 10), "the monitor kept the neutral picture after connecting"
            # the agent drives the remote desktop
            await h.mock("window.__events.length = 0")
            res = await h.act(action="click", point=[640, 360])
            ev = await h.mock("window.__events")
            down = next(e for e in ev if e["kind"] == "mousedown")
            assert res["ok"] is True and (down["x"], down["y"]) == (960, 540)
            await h.mock("window.__events.length = 0")
            res = await h.act(action="type", text="hi", submit=True)
            ev = await h.mock("window.__events")
            assert res["ok"] is True and "".join(e["key"] for e in ev if e["kind"] == "keydown" and len(e["key"]) == 1) == "hi"
            # 4. the session ends: neutral again, Reconnect pressed, counted
            await h.mock("window.__endSession()")
            assert await until(lambda: not desk.vagon.connected, 10)
            obs = await h.observe()
            assert obs["remote_ready"] is False and is_neutral(base64.b64decode(obs["jpeg_b64"]))
            assert await until(lambda: desk.vagon.connected, 20), desk.vagon.phase
            state = await h.state()
            assert state["vagon"]["reconnects"] == 1 and state["vagon"]["sessions"] == 2 and state["vagon"]["last_reconnect_utc"].endswith("+00:00")
            assert (await h.mock("window.__pressed")) == ["run", "connect", "reconnect"]
            # 5. the computer turns off behind our back: held until armed again, then Run is pressed again
            await h.mock("window.__stop()")
            assert await until(lambda: desk.vagon.machine == "off", 10), desk.vagon.machine
            assert await until(lambda: desk.vagon.start_held, 15), desk.vagon.phase
            assert (await h.mock("window.__pressed")) == ["run", "connect", "reconnect"]
            desk.arm_start(5)
            assert await until(lambda: desk.vagon.connected and desk.vagon.sessions == 3, 30), desk.vagon.phase
            assert (await h.mock("window.__pressed")) == ["run", "connect", "reconnect", "run", "connect"]
            events = events_of(h.events.path)
            presses = [(e["label"], e["button"]) for e in events if e["kind"] == "vagon_button"]
            assert presses == [("Run", "start"), ("Connect", "connect"), ("Reconnect", "reconnect"), ("Run", "start"), ("Connect", "connect")]
            kinds = [(e["kind"], e.get("state")) for e in events]
            assert ("vagon", "login_required") in kinds and ("operator", "served") in kinds and ("vagon", "connected") in kinds
            logged = h.events.path.read_text() + capsys.readouterr().out
            assert MOCK_PASSWORD not in logged and "owner@example.test" not in logged and "mocklogin" not in logged and "?delay" not in logged
    run(body())


@needs_browser
def test_navigation_lock_blocks_account_pages_and_external_sites(tmp_path, monkeypatch):
    async def body():
        async with Harness(tmp_path, monkeypatch, logged_in=True) as h:
            desk = h.desk
            assert await until(lambda: desk.vagon.connected, 30), (desk.vagon.phase, desk.error)
            assert desk.vagon.login_seen is None and (await h.http.get("/operator")).status == 404
            base = f"http://127.0.0.1:{h.site.port}"
            on_site = lambda: desk.page.url.startswith(base + "/app/workstation")

            async def settled():
                """Back on the workstation page and connected for a while (a refused navigation first leaves the page,
                then Chromium commits its error page under the attempted URL, then the runner returns)."""
                await asyncio.sleep(1.0)
                return await until(lambda: on_site() and desk.vagon.connected and desk.vagon.phase == "connected"
                                   and time.time() - desk.vagon.since > 1.5, 40)
            # a link to the billing page: refused; the kiosk ends up on its page, connected
            await h.mock("location.href = 'team/billing'")
            assert await until(lambda: desk.vagon.blocked >= 1, 10)
            assert await settled(), (desk.page.url, desk.vagon.phase)
            assert "MOCK-ACCOUNT-PAGE" not in await h.mock("document.body.innerText")
            # an SPA route change to an account page: noticed once committed, the page is brought back
            blocked = desk.vagon.blocked
            await h.mock("history.pushState({}, '', 'settings')")
            assert await until(lambda: desk.vagon.blocked > blocked, 10)
            assert await settled(), (desk.page.url, desk.vagon.phase)
            assert "settings" not in desk.page.url
            # an external site on another port: refused
            blocked = desk.vagon.blocked
            await h.mock(f"location.href = 'http://127.0.0.1:{h.external.port}/x'")
            assert await until(lambda: desk.vagon.blocked > blocked, 10)
            assert await settled(), (desk.page.url, desk.vagon.phase)
            assert "EXTERNAL" not in (await h.mock("document.title"))
            # the model never saw any of it, and the events name hosts, never the paths
            obs = await h.observe()
            assert obs["remote_ready"] is True and "MOCK-ACCOUNT-PAGE" not in json.dumps(obs) and "EXTERNAL" not in json.dumps(obs)
            blocked_events = [e for e in events_of(h.events.path) if e["kind"] == "blocked"]
            reasons = [e.get("reason") for e in blocked_events]
            assert reasons.count("account-page") >= 2 and "external" in reasons
            assert all(e["url"].endswith("/…") for e in blocked_events if e.get("url"))
            assert all("billing" not in e.get("url", "") and "settings" not in e.get("url", "") for e in blocked_events)
            state = await h.state()
            assert state["vagon"]["blocked"] >= 3 and state["vagon"]["phase"] == "connected"
    run(body())


@needs_browser
def test_the_login_survives_a_restart_in_the_persistent_profile(tmp_path, monkeypatch):
    async def body():
        async with Harness(tmp_path, monkeypatch) as h:
            assert await until(lambda: h.desk.vagon.phase == "login_required", 20), h.desk.vagon.phase
            await h.login_through_the_console()
            assert await until(lambda: h.desk.vagon.connected, 30), h.desk.vagon.phase
            assert (h.cfg.profile / "Default").is_dir()                                           # a real Chromium profile on disk
            await h.restart_desktop()
            desk = h.desk
            assert desk.restarts == 0 and desk.cfg.profile == h.cfg.profile
            assert await until(lambda: desk.vagon.connected, 30), (desk.vagon.phase, desk.page.url)
            assert desk.vagon.login_seen is None and desk.vagon.logged_in is True                # no login page this time
            assert "/app/login" not in desk.page.url
            assert (await h.mock("window.__pressed")) == ["connect"]                            # the machine was left on
            kinds = [(e["kind"], e.get("state")) for e in events_of(h.events.path)]
            assert kinds.count(("vagon", "login_required")) == 1
    run(body())


@needs_browser
def test_operator_console_flag_keeps_the_console_while_connected(tmp_path, monkeypatch):
    async def body():
        async with Harness(tmp_path, monkeypatch, logged_in=True, operator_console=True) as h:
            desk = h.desk
            assert await until(lambda: desk.vagon.connected, 30), desk.vagon.phase
            assert (await h.http.get("/operator")).status == 200 and (await h.state())["vagon"]["operator_console"] is True
            await h.mock("window.__events.length = 0")
            await h.op(type="text", text="ok")                                                    # the owner can type on the desktop too
            ev = await h.mock("window.__events")
            assert "".join(e["key"] for e in ev if e["kind"] == "keydown" and len(e["key"]) == 1) == "ok"
            obs = await h.observe()
            assert obs["remote_ready"] is True
    run(body())


@needs_browser
def test_operator_console_page_works_behind_a_path_prefix_in_a_real_browser(tmp_path, monkeypatch):
    async def body():
        from playwright.async_api import async_playwright
        async with Harness(tmp_path, monkeypatch) as h:
            desk = h.desk
            assert await until(lambda: desk.vagon.phase == "login_required", 20), desk.vagon.phase
            proxy = TestServer(proxy_app(h.http.port))
            await proxy.start_server()
            pw = await async_playwright().start()
            browser = await pw.chromium.launch(headless=True, executable_path=CHROMIUM)
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 900})
                console_url = f"http://127.0.0.1:{proxy.port}/proxy/8832/operator"
                r = await page.goto(console_url)
                assert r.status == 200 and await page.title() == "SUB-01 PC operator console"
                assert await until_async(lambda: page.evaluate("document.getElementById('status').textContent.includes('token')"), 5)
                await page.fill("#token", TOKEN)
                await page.click("#save")
                assert await page.evaluate("sessionStorage.getItem('sub01-operator-token')") == TOKEN
                assert await page.evaluate("document.getElementById('token').value") == ""
                assert await until_async(lambda: page.evaluate("document.getElementById('screen').naturalWidth > 0"), 15)
                assert await until_async(lambda: page.evaluate("document.getElementById('phase').textContent.includes('login_required')"), 10)
                assert await page.evaluate("document.getElementById('screen').naturalWidth") == desk.view[0]
                # the owner clicks the e-mail field on the picture and types; the kiosk page receives it
                fx, fy = await h.frac("#email")
                img = await page.locator("#screen").bounding_box()
                await page.mouse.click(img["x"] + fx * img["width"], img["y"] + fy * img["height"])
                assert await until_async(lambda: h.mock("document.activeElement && document.activeElement.id === 'email'"), 5)
                await page.keyboard.type("abc@example.test")
                assert await until_async(lambda: h.mock("document.getElementById('email').value === 'abc@example.test'"), 5)
                await page.keyboard.press("Tab")
                assert await until_async(lambda: h.mock("document.activeElement.id === 'password'"), 5)
                await page.keyboard.type(MOCK_PASSWORD)
                assert await until_async(lambda: h.mock(f"document.getElementById('password').value === '{MOCK_PASSWORD}'"), 5)
                await page.keyboard.press("Enter")
                assert await until(lambda: desk.vagon.logged_in, 15), desk.vagon.phase
                assert await until(lambda: desk.vagon.connected, 30), desk.vagon.phase
                # once connected the console closes itself: the page reports it, the frame route is gone
                assert await until_async(lambda: page.evaluate("document.getElementById('status').textContent.includes('no longer') || document.getElementById('status').textContent.includes('login_required')"), 10)
                assert (await h.http.get("/operator", headers=AUTH)).status == 404
                assert MOCK_PASSWORD not in h.events.path.read_text()
            finally:
                await browser.close()
                await pw.stop()
                await proxy.close()
    run(body())


# ---- money and trial controls are never pressed on the workstation page (Kimi review, 2026-10-23) -------------------
def test_workstation_chooser_never_presses_trial_or_money_controls():
    import scripts.streamer_desktop as sd
    money = [{"label": "Start trial"}, {"label": "Start free trial"}, {"label": "Buy credits"}, {"label": "Add funds"},
             {"label": "Subscribe"}, {"label": "Checkout"}, {"label": "Payment method"}, {"label": "Top up wallet"}]
    assert sd.choose_workstation_button(money) == (None, None)
    index, kind = sd.choose_workstation_button(money + [{"label": "Run"}])
    assert (index, kind) == (len(money), "start")
    index, kind = sd.choose_workstation_button([{"label": "Start trial"}, {"label": "Connect"}, {"label": "Start"}])
    assert (index, kind) == (1, "connect")


# ---- widgets are never connect controls; controls are logged; no blind reload while connecting (2026-10-23 stall) ----------
def test_workstation_chooser_never_presses_chat_support_or_cookie_widgets():
    choose, verdict = sd.choose_workstation_button, sd.control_verdict
    launcher = dict(btn("Open Intercom Messenger", 1800, 1000, 60, 60), widget=True)
    assert choose([launcher]) == (None, None) and choose([btn("Open Intercom Messenger")]) == (None, None)   # by flag or by label
    assert choose([launcher, btn("Connect")]) == (1, "connect")
    assert choose([btn("Connect"), launcher]) == (0, "connect")
    for label in ("Send us a message", "Search for help", "Close", "Home", "Messages", "Help", "Help / Support", "Chat with us",
                  "Open live chat", "Accept all cookies", "Cookie settings", "Give feedback", "Take our survey", "Dismiss"):
        assert choose([btn(label)]) == (None, None), label                                      # the Intercom panel of 2026-10-23
        assert verdict(btn(label)) not in ("reconnect", "connect", "start"), label
    for label in ("Open Intercom Messenger", "Send us a message", "Search for help", "Close", "Help", "Chat with us", "Open live chat",
                  "Accept all cookies", "Give feedback", "Dismiss"):
        assert verdict(btn(label)) == "widget", label
    assert choose([dict(btn("Connect"), widget=True), btn("Connect")]) == (1, "connect")         # a "Connect" inside a widget: not that one
    assert verdict(btn("Connect")) == "connect" and verdict(btn("Run")) == "start" and verdict(btn("Try again")) == "reconnect"
    assert verdict(btn("Sign in")) == "login" and verdict(btn("Buy credits")) == "money" and verdict(btn("Stop")) == "never"
    assert verdict(btn("animation")) == "none" and verdict(btn("")) == "none" and verdict(None) == "none"
    assert set(verdict(btn(l)) for l in ("Connect", "Run", "Try again", "Sign in", "Buy", "Stop", "x", "Chat")) <= set(sd.VAGON_CONTROL_VERDICTS)
    assert sd.choose_vagon_button([btn("Open Intercom Messenger"), btn("Connect")]) == 1              # the streams kind too
    assert sd.choose_vagon_button([dict(btn("Play"), widget=True)]) is None


def test_controls_summary_masks_addresses_and_names_the_frame():
    summary = sd.controls_summary([dict(btn("Open Intercom Messenger"), frame="intercom-messenger-frame"), btn("Connect"),
                                   btn("owner.name@example.test"), btn("x" * 90)])
    assert summary[0] == {"label": "Open Intercom Messenger", "verdict": "widget", "frame": "intercom-messenger-frame"}
    assert summary[1] == {"label": "Connect", "verdict": "connect"}
    assert summary[2]["label"] == "<email>" and "example.test" not in json.dumps(summary)
    assert len(summary[3]["label"]) == 40 and summary[3]["verdict"] == "none"
    assert sd.controls_summary(None) == [] and len(sd.controls_summary([btn("a")] * 50)) == 30


def test_workstation_reload_is_never_blind_while_the_page_may_be_connecting():
    reason = sd.workstation_reload_reason
    # connecting: not before 6 minutes, and then only when the page is dead
    assert reason("connecting", 119, 2, True) is None and reason("connecting", 300, 2, True) is None
    assert reason("connecting", sd.VAGON_WS_STUCK_S["connecting"] - 1, 0, True) is None
    assert reason("connecting", 400, 2, False) is None                                            # alive: requests, WS frames or RTC bytes
    assert reason("connecting", 400, 2, True) == "dead page"
    assert reason("blank", 60, 0, True) is None and reason("blank", 130, 0, False) is None and reason("blank", 130, 0, True) == "dead page"
    # an explicit ended/error text, the owner's request and six fruitless presses: at once
    assert reason("ended", 0, 0, False) == "ended" and reason("connecting", 0, 0, False, requested=True) == "operator request"
    assert reason("dashboard", 0, 6, False) == "six presses without effect"
    # the other phases keep their minimum, no deadness needed (a dashboard that offers nothing, a start that never ends)
    assert reason("dashboard", 100, 0, False) is None and reason("dashboard", 181, 0, False) == "stuck in dashboard"
    assert reason("starting", 599, 0, True) is None and reason("starting", 601, 0, False) == "stuck in starting"
    assert reason("connected", 9999, 0, True) is None and reason("login_required", 9999, 0, True) is None
    assert sd.VAGON_WS_STUCK_S["connecting"] >= 360


def test_page_dead_needs_silence_and_no_stream_element():
    dead = sd.page_dead
    assert dead(1000.0, {"request": 900.0}, False) is True and dead(1000.0, {"request": 950.0}, False) is False
    assert dead(1000.0, {"request": 900.0, "ws": 980.0}, False) is False                            # WebSocket frames keep it alive
    assert dead(1000.0, {"request": 900.0, "rtc": 970.0}, False) is False                           # WebRTC bytes too
    assert dead(1000.0, {"request": 900.0}, True) is False                                          # a video/canvas: never dead
    assert dead(1000.0, {}, False) is True and dead(1000.0, None, False) is True


def test_stream_evidence_needs_frames_or_painting():
    ev = sd.stream_evidence
    video = {"tag": "video", "box": [0, 0, 1920, 1080], "playing": True}
    assert ev(None) is False and ev(dict(video, frames=0)) is False and ev(dict(video, frames=None)) is False
    assert ev(dict(video, frames=12)) is True and ev(dict(video, frames=0), {"frames_decoded": 30}) is True
    assert ev(dict(video, frames=0), {"frames_decoded": 0}, repaint=True) is False                 # a video needs decoded frames, not a repaint
    canvas = {"tag": "canvas", "box": [0, 0, 1920, 1080], "playing": True}
    assert ev(canvas) is False and ev(canvas, repaint=True) is True and ev(canvas, {"frames_decoded": 1}) is True


def test_chromium_args_gpu_autoplay_and_extra_flags():
    base = sd.chromium_args(sd.Config(profile=Path("/p")))
    assert "--disable-gpu" in base and not any(a.startswith("--autoplay-policy") for a in base)
    sw = sd.chromium_args(sd.Config(profile=Path("/p"), gpu="swiftshader", autoplay=True, extra_args=("--foo=1", "not-a-flag")))
    assert "--disable-gpu" not in sw and {"--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"} <= set(sw)
    assert "--autoplay-policy=no-user-gesture-required" in sw and "--foo=1" in sw and "not-a-flag" not in sw and sw[-1] == "--kiosk"
    on = sd.chromium_args(sd.Config(profile=Path("/p"), gpu="on"))
    assert "--disable-gpu" not in on and "--use-angle=swiftshader" not in on


def test_main_parses_the_chromium_flag_options(tmp_path, monkeypatch):
    token = tmp_path / "token"
    token.write_text("operator-credential-test\n")
    seen = []

    async def fake_serve(args):
        seen.append(args)
    monkeypatch.setattr(sd, "serve", fake_serve)
    base = ["--token-file", str(token), "--data-dir", str(tmp_path / "d"), "--streamer-dir", str(tmp_path / "nothing")]
    sd.main(base + ["--pc-mode", "vagon", "--vagon-kind", "workstation", "--gpu", "swiftshader", "--autoplay", "--chromium-arg=--x=1", "--chromium-arg=--y"])   # a flag value needs the = form
    a = seen[-1]
    assert a.gpu == "swiftshader" and a.autoplay is True and a.chromium_arg == ["--x=1", "--y"]
    sd.main(base)
    assert seen[-1].gpu == "off" and seen[-1].autoplay is False and seen[-1].chromium_arg == []
    with pytest.raises(SystemExit):
        sd.main(base + ["--gpu", "maybe"])


class StepMouse:
    def __init__(self):
        self.log = []

    async def move(self, x, y, steps=1):
        self.log.append(("move", round(x), round(y)))

    async def click(self, x, y):
        self.log.append(("click", round(x), round(y)))


class StepPage:
    """What _workstation_step touches of the page: the mouse (presses) and goto (reloads); no frames (the diag then holds
    only what the runner itself saw)."""

    def __init__(self):
        self.mouse, self.goto_calls = StepMouse(), []

    async def goto(self, url, **kw):
        self.goto_calls.append(url)


def test_workstation_step_skips_the_widget_logs_controls_and_never_reloads_a_live_connecting_page(tmp_path, monkeypatch):
    async def body():
        now = [1000.0]
        monkeypatch.setattr(sd.time, "monotonic", lambda: now[0])
        monkeypatch.setattr(sd, "VAGON_CLICK_GAP_S", 0)
        monkeypatch.setattr(sd, "VAGON_RELOAD_BACKOFF", (0.0,))
        desk = ws_desktop(tmp_path)
        desk.status, desk.page, desk.view = "ready", StepPage(), (1920, 1080)
        desk._input_lock = asyncio.Lock()
        v, mouse, page = desk.vagon, desk.page.mouse.log, desk.page
        # 1. the dashboard of 2026-10-23: Intercom's launcher ("Open Intercom Messenger") came first and was pressed; not any more
        dashboard = probe("Your computer is on", [dict(btn("Open Intercom Messenger", 1800, 1000, 60, 60), widget=True),
                                                   btn("Help / Support", 100, 100), btn("Connect")])
        await desk._workstation_step(dashboard, now[0])
        assert v.phase == "dashboard" and v.machine == "on" and v.attempts == 1 and mouse[-1] == ("click", 900, 530)
        events = events_of(tmp_path / "events.jsonl")
        assert [e["label"] for e in events if e["kind"] == "vagon_button"] == ["Connect"]
        controls = [e for e in events if e["kind"] == "vagon_controls"]
        assert len(controls) == 1 and controls[0]["phase"] == "dashboard"
        assert {c["label"]: c["verdict"] for c in controls[0]["controls"]} == {"Open Intercom Messenger": "widget", "Help / Support": "widget", "Connect": "connect"}
        assert desk.operator_allowed() is True                                                  # the console: available all along
        # 2. connecting (the loading cubes): the page keeps making requests -> alive -> no reload for ten minutes
        connecting = probe("Loading", [btn("animation")])
        for _ in range(30):
            now[0] += 20
            desk._activity("request")
            await desk._workstation_step(connecting, now[0])
        assert v.phase == "connecting" and v.connected is False and v.reloads == 0 and page.goto_calls == []
        assert desk.operator_allowed() is True and desk.privacy_locked() is True
        events = events_of(tmp_path / "events.jsonl")
        diags = [e for e in events if e["kind"] == "vagon_diag"]
        assert len(diags) >= 15 and all(d["phase"] == "connecting" for d in diags) and "net" in diags[-1] and "rtc" in diags[-1]
        assert len([e for e in events if e["kind"] == "vagon_controls"]) == 2                   # once per page state, not per tick
        # 3. the page goes dead: a minute without requests, WebSocket frames or WebRTC bytes and no video/canvas -> opened again
        now[0] += 61
        await desk._workstation_step(connecting, now[0])
        assert v.reloads == 1 and page.goto_calls == [WS] and v.last_reload_why.startswith("connecting: dead page")
        assert v.phase == "opening" and v.reload_requested is False
        # 4. a video element without frames is not a connection (the element alone proves nothing)
        now[0] += 5
        stalled = probe("", [], {"tag": "video", "box": [0, 0, 1920, 1080], "playing": True, "frames": 0})
        await desk._workstation_step(stalled, now[0])
        assert v.connected is False and v.phase == "connecting" and desk.operator_allowed() is True
        # 5. frames decoded -> connected; the console closes (after its grace)
        now[0] += 5
        playing = probe("", [], {"tag": "video", "box": [0, 0, 1920, 1080], "playing": True, "frames": 240})
        await desk._workstation_step(playing, now[0])
        assert v.connected is True and v.phase == "connected" and v.sessions == 1 and v.connected_at == now[0]
        now[0] += sd.OPERATOR_CONNECTED_GRACE_S + 1
        assert desk.operator_allowed() is False
        connected_event = next(e for e in events_of(tmp_path / "events.jsonl") if e["kind"] == "vagon" and e.get("state") == "connected")
        assert connected_event["evidence"]["stream"]["frames"] == 240
        # 6. the owner asks for a reload while the session is dropping: honoured at once, with its reason
        desk.request_reload("operator request")
        for _ in range(sd.VAGON_MISSES):
            now[0] += 2
            await desk._workstation_step(connecting, now[0])
        assert v.connected is False and v.reloads == 2 and page.goto_calls == [WS, WS] and "operator request" in v.last_reload_why
        assert desk.operator_allowed() is True
        text = (tmp_path / "events.jsonl").read_text()
        assert "launchFlags" not in text and ("vagon", "reload_requested") in [(e["kind"], e.get("state")) for e in events_of(tmp_path / "events.jsonl")]
    run(body())


# --- the input path on the connected remote desktop (2026-10-23: proven live on the owner's Vagon Computer) -------------
def test_a_lone_modifier_is_a_key_of_its_own():
    """"Meta" alone is the Windows key (Start menu); a lone modifier was refused before."""
    assert sd.parse_key("Meta") == ((), "Meta") and sd.parse_key("Control") == ((), "Control") and sd.parse_key("Shift") == ((), "Shift")
    assert sd.parse_key("Control+Escape") == (("Control",), "Escape") and sd.parse_key("Alt") == ((), "Alt")
    assert sd.validate_action({"action": "key", "key": "Meta"})["key"] == "Meta"
    assert sd.action_policy({"action": "key", "key": "Meta"}) is None
    assert sd.action_policy({"action": "key", "key": "Meta+v"}).startswith("blocked")                # clipboard keys stay refused
    for bad in ("Meta+", "Hyper", "Control+Hyper", "ControlOrMeta", "Meta+Meta", "Win"):
        with pytest.raises(sd.ActionError):
            sd.parse_key(bad)


class OrderPage:
    """A fake page logging, in order, what the vagon act path does: the hit test (VAGON_HIT_JS answered with `hit`, or
    raising it; a list answers call by call, its last item repeating), the move, the focus (VAGON_FOCUS_JS, answering
    `focused`), clicks, wheel steps and keys."""

    def __init__(self):
        self.log, self.hit, self.focused = [], {"ok": True, "tag": "video", "id": "player", "how": "stream"}, True
        page = self

        class Mouse:
            async def move(self, x, y, steps=1):
                page.log.append(("move", round(x), round(y)))

            async def click(self, x, y, **kw):
                page.log.append(("click", round(x), round(y)))

            async def wheel(self, dx, dy):
                page.log.append(("wheel", dx, dy))

        class Keyboard:
            async def press(self, key):
                page.log.append(("press", key))

            async def down(self, key):
                page.log.append(("down", key))

            async def up(self, key):
                page.log.append(("up", key))

            async def type(self, text, delay=0):
                page.log.append(("type", text))

        self.mouse, self.keyboard = Mouse(), Keyboard()

    async def evaluate(self, js, arg=None):
        if js is sd.VAGON_HIT_JS:
            self.log.append(("hit", round(arg[0]), round(arg[1])))
            answer = self.hit
            if isinstance(answer, list):
                answer = answer.pop(0) if len(answer) > 1 else answer[0]
            if isinstance(answer, Exception):
                raise answer
            return answer
        if js is sd.VAGON_FOCUS_JS:
            self.log.append(("focus",))
            return self.focused
        return None


def connected_ws(tmp_path, monkeypatch, page):
    """A workstation Desktop whose remote desktop is connected (session 1, a playing video over the whole page)."""
    monkeypatch.setattr(sd, "VAGON_SETTLE_S", 0)
    monkeypatch.setattr(sd, "VAGON_NAV_SETTLE_S", 0)
    desk = ws_desktop(tmp_path)
    desk.status, desk.page, desk.view = "ready", page, (1920, 1080)
    desk._input_lock = asyncio.Lock()
    desk.vagon.connected, desk.vagon.sessions = True, 1
    live = probe("", [], dict(VIDEO, frames=240))

    async def fake_probe():
        return json.loads(json.dumps(live))
    desk._vagon_probe = fake_probe
    return desk


def test_vagon_keys_focus_the_stream_first_and_fail_closed_without_it(tmp_path, monkeypatch):
    """Measured live: the stream element's DOM focus is all keys need (no click, hover or pointer lock). Every key path
    focuses it first; when it does not take the focus nothing is sent to the host page."""
    async def body():
        page = OrderPage()
        desk = connected_ws(tmp_path, monkeypatch, page)
        r = await desk.do({"action": "key", "key": "Meta"})
        assert r["errors"] == [] and page.log == [("focus",), ("press", "Meta")]       # no click, no move
        page.log.clear()
        await desk.do({"action": "type", "text": "sub01 test", "submit": False})
        assert page.log == [("focus",), ("type", "sub01 test")]
        page.log.clear()
        await desk.do({"action": "key", "key": "Control+Escape"})                     # a chord: the modifier held first
        assert page.log == [("focus",), ("down", "Control"), ("press", "Escape"), ("up", "Control")]
        page.log.clear()
        for action in ({"action": "navigate", "url": "https://example.com/"}, {"action": "back"},
                       {"action": "type", "text": "x", "submit": True}):
            await desk.do(action)
            assert page.log[0] == ("focus",) and page.log[1][0] in ("down", "type") and not any(e[0] in ("click", "move", "hit") for e in page.log), action
            page.log.clear()
        # the stream does not take the focus (stale page, no stream element): fail closed on every key path
        page.focused = False
        for action in ({"action": "key", "key": "Meta"}, {"action": "type", "text": "x", "submit": False},
                       {"action": "navigate", "url": "https://example.com/"}, {"action": "back"}):
            r = await desk.do(action)
            assert r["errors"] == ["the stream did not take the keyboard focus; nothing was sent; observe again"], action
            assert page.log == [("focus",)], action
            page.log.clear()
        assert [e["what"] for e in events_of(tmp_path / "events.jsonl") if e["kind"] == "blocked" and e.get("what") == "keys"] == ["keys"] * 4
        # not connected: nothing is focused or pressed
        page.focused, desk.vagon.connected = True, False
        r = await desk.do({"action": "key", "key": "Meta"})
        assert r["errors"] and page.log == []
    run(body())


def test_vagon_clicks_and_wheel_only_where_the_stream_is_under_the_point(tmp_path, monkeypatch):
    async def body():
        page = OrderPage()
        desk = connected_ws(tmp_path, monkeypatch, page)
        r = await desk.do({"action": "click", "point": [640.0, 360.0]})
        assert r["errors"] == [] and page.log == [("hit", 960, 540), ("move", 960, 540), ("hit", 960, 540), ("click", 960, 540)]
        # anything but an explicit ok: true (no answer, a malformed one) is a refusal
        for answer in (None, "yes", {"tag": "video"}, {"ok": 1}):
            page.log.clear()
            page.hit = answer
            r = await desk.do({"action": "click", "point": [640.0, 360.0]})
            assert r["errors"][0].startswith("blocked") and page.log == [("hit", 960, 540)], answer
        page.log.clear()
        # the Vagon handle ("Click to Open") over the stream: checked, never moved to, never pressed
        page.hit = {"ok": False, "tag": "div", "id": "", "text": "Click to Open", "why": "host control"}
        r = await desk.do({"action": "click", "point": [488.0, 28.0]})
        assert len(r["errors"]) == 1 and r["errors"][0].startswith("blocked: that point is the stream page's own (host control")
        assert page.log == [("hit", 732, 42)]
        r = await desk.do({"action": "scroll", "direction": "down", "amount": 600})
        assert r["errors"][0].startswith("blocked") and not any(e[0] in ("wheel", "move", "click") for e in page.log)
        blocked = [e for e in events_of(tmp_path / "events.jsonl") if e["kind"] == "blocked" and "Click to Open" in e.get("element", "")]
        assert [(e["what"], e["reason"]) for e in blocked] == [("click", "host control"), ("scroll", "host control")]
        # the move itself opens a host menu under the point (a hover toolbar): checked again after the move, not clicked
        page.log.clear()
        page.hit = [{"ok": True, "tag": "video", "id": "player"}, {"ok": False, "tag": "div", "why": "host control"}]
        r = await desk.do({"action": "click", "point": [640.0, 360.0]})
        assert r["errors"][0].startswith("blocked") and page.log == [("hit", 960, 540), ("move", 960, 540), ("hit", 960, 540)]
        # a page that cannot be checked (navigating, frame gone): refused, never clicked blind
        page.log.clear()
        page.hit = RuntimeError("Execution context was destroyed")
        r = await desk.do({"action": "click", "point": [640.0, 360.0]})
        assert "could not be checked" in r["errors"][0] and page.log == [("hit", 960, 540)]
        # the stream under the point again: the wheel turns there, after both checks
        page.hit, desk.cursor = {"ok": True, "tag": "video", "id": "player"}, [960.0, 540.0]
        page.log.clear()
        r = await desk.do({"action": "scroll", "direction": "down", "amount": 600})
        assert r["errors"] == [] and page.log == [("hit", 960, 540), ("move", 960, 540), ("hit", 960, 540), ("wheel", 0, 100.0)] + [("hit", 960, 540), ("wheel", 0, 100.0)] * 5
        # something of the host page appears under the wheel point mid-scroll: the remaining steps are not sent
        page.log.clear()
        page.hit = [{"ok": True}, {"ok": True}, {"ok": True}, {"ok": False, "tag": "div", "why": "host control"}]
        r = await desk.do({"action": "scroll", "direction": "down", "amount": 600})
        assert r["errors"][0].startswith("blocked") and [e[0] for e in page.log].count("wheel") == 2
        page.hit = {"ok": True, "tag": "video", "id": "player"}
        # the wheel rests where the agent last pointed on the stream, else the centre
        desk.cursor = [300.0, 200.0]
        page.log.clear()
        await desk.do({"action": "scroll", "direction": "up", "amount": 60})
        assert page.log[:3] == [("hit", 300, 200), ("move", 300, 200), ("hit", 300, 200)]
    run(body())


HIT_PAGE = """<!doctype html><html><head><style>body{margin:0;background:#000}</style></head><body>
<div id="app" style="position:fixed;inset:0">
  <video id="player" muted style="position:absolute;left:0;top:0;width:1280px;height:640px;background:#123"></video>
  <div id="handle" title="Click to Open" style="position:absolute;left:470px;top:10px;width:36px;height:36px;background:#444;cursor:pointer"></div>
  <button id="power" aria-label="Power" style="position:absolute;left:600px;top:10px;width:60px;height:30px">Power</button>
</div></body></html>"""


@needs_browser
def test_hit_js_in_a_real_browser_tells_the_stream_from_the_host_page():
    from playwright.async_api import async_playwright

    async def body():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=CHROMIUM, headless=True)
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 720})
                await page.set_content(HIT_PAGE)

                async def hit(x, y):
                    return await page.evaluate(sd.VAGON_HIT_JS, [x, y, 320, 180])
                assert (await hit(640, 360))["ok"] is True and (await hit(640, 360))["id"] == "player"
                handle = await hit(488, 28)
                assert handle["ok"] is False and handle["id"] == "handle" and handle["why"] == "a host-page element over the stream"
                assert (await hit(630, 25))["why"] == "host control" and (await hit(630, 25))["text"] == "Power"
                assert (await hit(640, 690))["why"] == "outside the stream"
                # a dim layer over the whole stream (a host backdrop): never pressed through
                await page.evaluate("""() => { const d = document.createElement('div'); d.id = 'dim';
                  d.style.cssText = 'position:absolute;inset:0;background:rgba(0,0,0,0.5)'; document.getElementById('app').appendChild(d); }""")
                dim = await hit(640, 360)
                assert dim["ok"] is False and dim["id"] == "dim" and dim["why"] == "a layer that paints over the stream (dim/backdrop)"
                await page.evaluate("document.getElementById('dim').style.background = 'transparent'")
                assert (await hit(640, 360))["why"] == "a transparent layer over the stream"
                await page.evaluate("document.getElementById('dim').remove(); document.getElementById('player').style.pointerEvents = 'none'")
                assert (await hit(640, 360))["why"].startswith("a container of the stream")
                await page.evaluate("document.getElementById('player').style.pointerEvents = 'auto'; document.getElementById('player').style.display = 'none'")
                assert (await hit(640, 360))["why"] == "no stream element"
            finally:
                await browser.close()
    run(body())


@needs_browser
def test_init_scripts_count_the_input_path_and_hook_a_child_window_peer_connection():
    """INPUT_INIT_JS counts events and the page's listeners (never a key); RTC_INIT_JS also runs in a script-created
    about:blank iframe (a page may make its RTCPeerConnection there), whose record the per-frame diag reads, and wraps the
    outbound data-channel sends in both windows."""
    from playwright.async_api import async_playwright

    async def body():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=CHROMIUM, headless=True)
            try:
                context = await browser.new_context(viewport={"width": 1280, "height": 720})
                await context.add_init_script(sd.RTC_INIT_JS)
                await context.add_init_script(sd.INPUT_INIT_JS)
                page = await context.new_page()
                await page.route("http://sub01.test/", lambda route: route.fulfill(body=HIT_PAGE, content_type="text/html"))
                await page.goto("http://sub01.test/")
                await page.evaluate("""() => { document.addEventListener('keydown', e => { if (e.key === 'Meta') e.preventDefault(); });
                  document.getElementById('player').addEventListener('mousedown', () => {}); }""")
                assert await page.evaluate(sd.VAGON_FOCUS_JS, [320, 180]) is True
                await page.keyboard.press("Meta")
                await page.mouse.click(640, 360)
                hooks = await page.evaluate("window.__sub01Input")
                assert hooks["key"]["down"] == 1 and hooks["key"]["prevented"] == 1 and hooks["key"]["target"] == "video#player"
                # Ctrl+A meant for the remote desktop: the player's document listener gets it, the HOST page selects nothing
                # (its selection tinted the whole video: the "dim"); a host selection made earlier is cleared by the focus
                await page.evaluate("""() => { window.__seen = []; document.addEventListener('keydown', e => window.__seen.push(e.key + (e.ctrlKey ? '+ctrl' : ''))); }""")
                await page.evaluate("""() => { window.__unprevented = 0; document.addEventListener('keydown', e => { if (!e.defaultPrevented) window.__unprevented++; }); }""")
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Tab")
                assert await page.evaluate("[window.__seen, getSelection().type, document.activeElement.id]") == [["Control+ctrl", "a+ctrl", "Tab"], "None", "player"]
                assert await page.evaluate("window.__unprevented") == 3                   # the player sees them untouched
                await page.evaluate("document.getSelection().selectAllChildren(document.body)")
                assert await page.evaluate("getSelection().type") == "Range"
                assert await page.evaluate(sd.VAGON_FOCUS_JS, [320, 180]) is True and await page.evaluate("getSelection().type") != "Range"
                await page.keyboard.press("x")                                             # a plain character: never prevented
                # the runner's cancel runs last (window, bubble): the counter measures only the player's own preventDefault
                assert await page.evaluate("[window.__sub01Input.key.down, window.__sub01Input.key.prevented]") == [5, 1]
                assert hooks["mouse"]["down"] == 1 and hooks["mouse"]["target"] == "video#player"
                assert hooks["listeners"]["document:keydown"] >= 1 and hooks["listeners"]["video#player:mousedown"] == 1
                assert "Meta" not in json.dumps(hooks)                                     # counts, never which key
                made = await page.evaluate("""() => { const f = document.createElement('iframe'); f.name = 'pristine'; document.body.appendChild(f);
                  const pc = new f.contentWindow.RTCPeerConnection(); pc.createDataChannel('control');
                  return {parent: window.__sub01Rtc.created, child: f.contentWindow.__sub01Rtc.created,
                          wrapped: !!f.contentWindow.RTCDataChannel.prototype.send.__sub01 && !!RTCDataChannel.prototype.send.__sub01}; }""")
                assert made == {"parent": 0, "child": 1, "wrapped": True}
                child = next(f for f in page.frames if f.name == "pristine")
                frames = [await page.evaluate(sd.VAGON_DIAG_JS), await child.evaluate(sd.VAGON_DIAG_JS)]
                diag = frames[0]
                assert diag["input"]["cover"] == {"stream": 20} and diag["input"]["active"]["id"] == "player"
                assert diag["input"]["hooks"]["key"]["down"] == 5 and diag["input"]["selection"] != "Range"
                assert diag["rtc"]["dc_out"] == {} and diag["rtc"]["created"] == 0
                # outbound sends are counted per label after the native send (UTF-8 bytes), as own properties only
                # ("__proto__" is a valid channel label); a refused send is not counted. A loopback pair in this page:
                counted = await page.evaluate("""async () => {
                  try { RTCDataChannel.prototype.send.call({label: 'control'}, 'refused'); } catch (e) {}
                  const a = new RTCPeerConnection(), b = new RTCPeerConnection();
                  a.onicecandidate = e => e.candidate && b.addIceCandidate(e.candidate); b.onicecandidate = e => e.candidate && a.addIceCandidate(e.candidate);
                  const chans = ['control', '__proto__'].map(l => a.createDataChannel(l));
                  await a.setLocalDescription(); await b.setRemoteDescription(a.localDescription); await b.setLocalDescription(); await a.setRemoteDescription(b.localDescription);
                  await Promise.all(chans.map(c => new Promise((ok, no) => { if (c.readyState === 'open') ok(); c.onopen = ok; setTimeout(() => no(new Error('open timeout')), 10000); })));
                  chans[0].send('abcd'); chans[0].send('\u00e9\u00e9'); chans[1].send(new Uint8Array(5));
                  const o = window.__sub01Rtc.dc_out;
                  return {own: Object.keys(o), control: o.control, proto: Object.getOwnPropertyDescriptor(o, '__proto__').value, polluted: ({}).n !== undefined}; }""")
                assert counted == {"own": ["control", "__proto__"], "control": {"n": 2, "bytes": 8}, "proto": {"n": 1, "bytes": 5}, "polluted": False}
                # privacy: text typed into a host field (here a contenteditable that has the focus) never reaches the diag
                await page.evaluate("""() => { const d = document.createElement('div'); d.id = 'note'; d.contentEditable = 'true';
                  d.style.cssText = 'position:absolute;left:0;top:660px;width:400px;height:40px'; document.body.appendChild(d); d.focus(); }""")
                await page.keyboard.type("SECRET-owner-typed-7731")
                leaked = json.dumps(await page.evaluate(sd.VAGON_DIAG_JS)) + json.dumps(await page.evaluate(sd.VAGON_HIT_JS, [200, 680, 320, 180]))
                assert "SECRET" not in leaked and "7731" not in leaked
                summary = sd.Desktop._rtc_summary(None, frames)                     # the per-frame diag finds it in the child
                assert summary["created"] == 1 and summary["id"] == 1 and summary["live"] == 0
            finally:
                await browser.close()
    run(body())


def test_rtc_summary_prefers_the_live_connection_over_a_finished_bigger_one():
    """The "empty rtc while connected" of 2026-10-23: the summary picked the previous session's closed connection (most
    bytes) or a snapshot taken before the new one's first stats poll; the live connection now comes first."""
    closed = {"id": 17, "state": {"connection": "closed"}, "tracks": 4, "stats": {"bytes": 45610786, "frames_decoded": 3932, "fps": 31}}
    fresh = {"id": 18, "state": {"connection": "connected"}, "tracks": 4, "stats": None}
    frame = {"host": "app.vagon.io", "rtc": {"created": 18, "pcs": [closed, fresh], "events": [], "dc_out": {"control": {"n": 4, "bytes": 132}}}}
    s = sd.Desktop._rtc_summary(None, [frame])
    assert s["id"] == 18 and s["live"] == 1 and s["bytes"] == 0 and s["dc_out"] == {"control": {"n": 4, "bytes": 132}}
    later = dict(fresh, stats={"bytes": 3516949, "frames_decoded": 261, "fps": 30, "pair": {"local": "srflx", "remote": "relay", "protocol": "udp"}})
    s = sd.Desktop._rtc_summary(None, [{"host": "app.vagon.io", "rtc": {"created": 18, "pcs": [closed, later]}}])
    assert (s["id"], s["frames_decoded"], s["fps"], s["pair"]["remote"], s["pair"]["protocol"]) == (18, 261, 30, "relay", "udp")
    assert sd.Desktop._rtc_summary(None, [{"error": "detached"}]) == {"created": 0, "live": 0}


def test_vagon_diag_route_gives_a_fresh_snapshot_with_the_token_only(tmp_path):
    class DiagDesk(StubDesk):
        vagon_mode = True

        def __init__(self):
            super().__init__()
            self.calls = 0

        async def diag_now(self):
            self.calls += 1
            return {"phase": "connected", "rtc": {"frames_decoded": 3900, "fps": 30}}

    async def body():
        desk = DiagDesk()
        runner, http = await client_for(desk, tmp_path)
        try:
            assert (await http.get("/pc/vagon/diag")).status == 403 and desk.calls == 0
            r = await http.get("/pc/vagon/diag", headers=AUTH)
            assert r.status == 200 and await r.json() == {"ok": True, "diag": {"phase": "connected", "rtc": {"frames_decoded": 3900, "fps": 30}}}
            desk.vagon_mode = False
            assert (await http.get("/pc/vagon/diag", headers=AUTH)).status == 409 and desk.calls == 1
        finally:
            await http.close()
    run(body())


def test_vagon_chords_hold_the_modifier_past_the_altgr_window_and_always_release_it(tmp_path, monkeypatch):
    """Vagon's keyboard layer drops a key that follows a Left-Control keydown within 15 ms (and the Control with it):
    chords go down, wait VAGON_CHORD_HOLD_S, key, up - also on the scancode path, whose batch arrives at once."""
    async def body():
        page = OrderPage()
        desk = connected_ws(tmp_path, monkeypatch, page)
        stamps = []
        down, press = page.keyboard.down, page.keyboard.press

        async def timed_down(key):
            stamps.append(("down", time.monotonic()))
            await down(key)

        async def timed_press(key):
            stamps.append(("press", time.monotonic()))
            await press(key)
        page.keyboard.down, page.keyboard.press = timed_down, timed_press
        await desk._vagon_chord("Control+Shift+a")
        assert page.log == [("down", "Control"), ("down", "Shift"), ("press", "a"), ("up", "Shift"), ("up", "Control")]
        assert stamps[-1][1] - stamps[-2][1] >= sd.VAGON_CHORD_HOLD_S * 0.9 and sd.VAGON_CHORD_HOLD_S >= 0.05
        page.log.clear()
        await desk._vagon_chord("Escape")                                              # a plain key: no hold
        assert page.log == [("press", "Escape")]
        page.log.clear()

        async def failing_press(key):
            raise RuntimeError("target closed")
        page.keyboard.press = failing_press
        with pytest.raises(RuntimeError):
            await desk._vagon_chord("Control+l")
        assert page.log == [("down", "Control"), ("up", "Control")]                    # never left held
        # the scancode path (native monitor): Ctrl+A in one batch is spaced out after the Control
        page.log.clear()
        page.keyboard.down, page.keyboard.press = timed_down, timed_press
        stamps.clear()
        t0 = time.monotonic()
        assert await desk._keys([("down", "Control"), ("down", "KeyA"), ("up", "KeyA"), ("up", "Control")]) is True
        assert [e for e in page.log if e[0] != "focus"] == [("down", "Control"), ("down", "KeyA"), ("up", "KeyA"), ("up", "Control")]
        assert stamps[1][1] - stamps[0][1] >= sd.VAGON_CHORD_HOLD_S * 0.9 and time.monotonic() - t0 < 1.0
    run(body())


def test_diag_requests_share_one_snapshot_and_never_move_the_connected_schedule(tmp_path, monkeypatch):
    async def body():
        now = [1000.0]
        monkeypatch.setattr(sd.time, "monotonic", lambda: now[0])
        desk = ws_desktop(tmp_path)
        desk.status, desk.page, desk.view = "ready", StepPage(), (1920, 1080)
        desk._input_lock = asyncio.Lock()
        calls = []

        async def fake_diag(phase, force=False):          # (the clock is frozen: asyncio.sleep(0) only yields)
            calls.append((phase, now[0]))
            await asyncio.sleep(0)                          # the second request passes the first check meanwhile
            desk.vagon.last_diag, desk.vagon.diag = now[0], {"phase": phase}
            return desk.vagon.diag
        desk._vagon_diag = fake_diag
        # two requests at once: the second one queues behind the first and gets its snapshot
        await asyncio.gather(desk.diag_now(), desk.diag_now())
        assert len(calls) == 1
        # connect: a snapshot now and a follow-up VAGON_DIAG_FOLLOW_S later, even with a manual snapshot in between
        now[0] += 10
        playing = probe("", [], {"tag": "video", "box": [0, 0, 1920, 1080], "playing": True, "frames": 240})
        await desk._workstation_step(playing, now[0])
        assert desk.vagon.connected and calls[-1] == ("connected", now[0])
        connected_at = now[0]
        now[0] += 3
        await desk.diag_now()                                                            # the owner asks for one
        now[0] = connected_at + sd.VAGON_DIAG_FOLLOW_S - 0.5
        await desk._workstation_step(playing, now[0])
        n = len(calls)
        now[0] = connected_at + sd.VAGON_DIAG_FOLLOW_S + 0.5
        await desk._workstation_step(playing, now[0])
        assert len(calls) == n + 1 and calls[-1][0] == "connected"                        # the follow-up came on time
        now[0] += sd.VAGON_DIAG_CONNECTED_S - 1
        await desk._workstation_step(playing, now[0])
        assert len(calls) == n + 1
        now[0] += 2
        await desk._workstation_step(playing, now[0])
        assert len(calls) == n + 2                                                       # then every minute
    run(body())


# ---- starting the owner's computer needs arming (it spends his Vagon balance); Kimi review 2026-10-23 --------------------
def test_take_start_needs_arming_one_start_per_arming_and_expiry(tmp_path, monkeypatch):
    desk = ws_desktop(tmp_path)
    clock = [5000.0]
    monkeypatch.setattr(sd.time, "monotonic", lambda: clock[0])
    assert desk.vagon.autostart is False and desk.take_start("t") is False and desk.vagon.start_held is True
    held = [e for e in events_of(tmp_path / "events.jsonl") if e.get("state") == "start_held"]
    assert len(held) == 1 and desk.take_start("t") is False                                  # logged once per off period
    assert len([e for e in events_of(tmp_path / "events.jsonl") if e.get("state") == "start_held"]) == 1
    assert desk.arm_start(2)["start_armed_s"] == 120.0
    assert desk.take_start("t") is True and desk.vagon.starts == 1 and desk.take_start("t") is False   # one per arming
    desk.arm_start(1)
    clock[0] += 61
    assert desk.take_start("t") is False                                                       # expired
    desk.arm_start(5)
    assert desk.arm_start(0)["start_armed_s"] == 0.0 and desk.take_start("t") is False         # 0 disarms
    desk._set_machine("on", "page")
    assert desk.vagon.start_held is False                                                      # the off period ended
    auto = ws_desktop(tmp_path / "auto", vagon_autostart=True)
    assert auto.vagon.autostart is True and auto.take_start("t") is True and auto.take_start("t") is True


def test_post_pc_vagon_start_and_the_api_fallback_obey_the_arming(tmp_path, monkeypatch):
    async def body():
        desk = ws_desktop(tmp_path)
        desk.api = FakeApi("off")
        desk.api.refresh()
        runner = sd.Runner(desk, TOKEN, sd.Events(tmp_path / "r.jsonl"))
        async with TestClient(TestServer(sd.create_app(runner))) as http:
            r = await http.post("/pc/vagon/start", headers=AUTH)
            assert r.status == 409 and "arm it first" in await r.text() and desk.api.starts == 0
            assert (await http.post("/pc/vagon/arm", json={"minutes": 3}, headers=AUTH)).status == 200
            r = await http.post("/pc/vagon/start", headers=AUTH)
            assert r.status == 200 and desk.api.starts == 1 and desk.vagon.starts == 1
            r = await http.post("/pc/vagon/start", headers=AUTH)
            assert r.status == 409 and desk.api.starts == 1                                    # the arming was used
        # the loop's API fallback (no start button on the page) is held the same way
        desk.vagon.last_api_start = -1e9
        probe = {"url": "https://app.vagon.io/workstation", "title": "x", "text": "", "buttons": [], "passwords": 0}
        monkeypatch.setattr(desk, "_log_controls", lambda *a, **k: None)
        monkeypatch.setattr(desk, "_repainted", lambda: False)

        async def no_diag(*a, **k):
            return None
        monkeypatch.setattr(desk, "_vagon_diag", no_diag)
        monkeypatch.setattr(sd, "classify_workstation",
                            lambda p: {"phase": "dashboard", "button": None, "kind": None, "machine": "off", "why": ""})
        await desk._workstation_step(probe, time.monotonic())
        assert desk.api.starts == 1 and desk.vagon.start_held is True
        desk.arm_start(3)
        desk.api.started_at = 0.0                                                              # past the API's own start gap
        await desk._workstation_step(probe, time.monotonic())
        assert desk.api.starts == 2 and desk.vagon.starts == 2
    run(body())
