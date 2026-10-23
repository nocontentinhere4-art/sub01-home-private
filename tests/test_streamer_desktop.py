"""Streamer desktop runner: the pure helpers and the HTTP app against a fake browser (no Playwright, no network)."""

import asyncio
import base64
import importlib.util
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("streamer_desktop", ROOT / "scripts/streamer_desktop.py")
sd = importlib.util.module_from_spec(spec)
sys.modules["streamer_desktop"] = sd
spec.loader.exec_module(sd)
TOKEN = "operator-credential-test"
AUTH = {"X-Admin-Token": TOKEN}
PNG = b"\x89PNG\r\n\x1a\n"


def jpeg(color=(255, 255, 255), size=(1920, 1080)):
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, "JPEG", quality=80)
    return out.getvalue()


def run(coro):
    asyncio.run(coro)


def test_playwright_is_not_needed_to_import_the_module():
    code = ("import importlib.util, sys; spec = importlib.util.spec_from_file_location('m', sys.argv[1]);"
            " m = importlib.util.module_from_spec(spec); sys.modules['m'] = m; spec.loader.exec_module(m);"
            " assert 'playwright' not in sys.modules; print('ok')")
    done = subprocess.run([sys.executable, "-c", code, str(ROOT / "scripts/streamer_desktop.py")], capture_output=True, text=True)
    assert done.returncode == 0 and done.stdout.strip() == "ok", done.stderr


# --- policy ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url,why", [
    ("https://example.com/", None), ("https://html.duckduckgo.com/html/?q=cats", None),
    ("https://en.wikipedia.org/wiki/Password", None), ("https://en.wikipedia.org/wiki/Sussex", None),
    ("https://www.bbc.co.uk/news/world", None), ("https://booking.com/", None),
    ("https://www.paypal.com/signin", "banking"), ("https://online.mybank.com/", "banking"),
    ("https://www.pornhub.com/", "adult"), ("https://www.bet365.com/", "gambling"),
    ("https://accounts.google.com/x", "login"), ("https://claude.ai/chats", "owner-service"),
    ("https://pay.example.com/", "payment"), ("https://github.com/login", "login-path"),
    ("https://shop.example.com/checkout", "checkout-path"), ("https://shop.example.com/cart/", "checkout-path"),
    ("https://en.wikipedia.org/wiki/Special:UserLogin", "login-path"),
    ("https://www.google.com/accounts", "login-path"), ("https://example.com/report.pdf", "download"), ("file:///etc/passwd", "scheme"), ("javascript:alert(1)", "scheme"),
    ("http://127.0.0.1:8830/api/home", "private-host"), ("http://169.254.169.254/latest", "private-host"),
    ("http://localhost/", "private-host"), ("http://2130706433/", "private-host"), ("https://example.com:8443/", "port"),
    ("https://user:pw@example.com/", "credentials-in-url"), ("https://www.tradingview.com/", "blocked-site"),
])
def test_blocked_url(url, why):
    assert sd.blocked_url(url) == why


def test_blocked_url_core_rules_hold_without_the_browse_module(monkeypatch):
    monkeypatch.setattr(sd, "B", None)
    assert sd.blocked_url("https://example.com/") is None
    for url in ("https://www.paypal.com/", "https://www.pornhub.com/", "https://github.com/login",
                "https://shop.example.com/checkout", "http://10.0.0.5/", "https://accounts.google.com/"):
        assert sd.blocked_url(url), url


def test_allow_private_is_only_for_tests():
    assert sd.blocked_url("http://127.0.0.1:9999/page", allow_private=True) is None
    assert sd.blocked_url("http://127.0.0.1:9999/login", allow_private=True) == "login-path"


def test_request_blocked_distinguishes_navigation_from_subresources():
    assert sd.request_blocked("https://example.com/", True, "GET") is None
    assert sd.request_blocked("https://example.com/search", True, "POST") == "post-navigation"
    assert sd.request_blocked("https://cdn.example.com/app.js") is None
    assert sd.request_blocked("https://accounts.google.com/gsi/client") == "login"      # no sign-in frames
    assert sd.request_blocked("https://example.com/cart/pixel.gif") is None             # path rules: pages only
    assert sd.request_blocked("http://192.168.1.1/") == "private-host"
    assert sd.request_blocked("data:text/plain,hi") is None and sd.request_blocked("about:blank", True) is None
    assert sd.request_blocked("ftp://example.com/") == "scheme"


def test_text_mark_and_field_policy():
    assert sd.text_blocked("best ramen in tokyo") is None
    assert sd.text_blocked("free porn") == "unsafe-text"
    assert sd.text_blocked("4111 1111 1111 1111") == "card-number"
    assert sd.mark_blocked({"label": "Read more", "href": "https://example.com/a"}) is None
    assert sd.mark_blocked({"label": "Buy now", "href": ""}) == "money control"
    assert sd.mark_blocked({"label": "Log in"}) == "login or account control"
    assert sd.mark_blocked({"label": "Next", "href": "https://www.paypal.com/"}).startswith("link target")
    assert sd.field_blocked({"tag": "input", "type": "password"}) == "password field"
    assert sd.field_blocked({"tag": "input", "type": "text", "name": "user_email x"}) == "sensitive field"
    assert sd.field_blocked({"tag": "input", "type": "search", "name": "q search"}) is None
    assert sd.field_blocked({"tag": "textarea", "type": "", "ac": "off", "name": "hotel"}) is None
    assert sd.field_blocked(None) is None


def test_keys_and_clipboard():
    assert sd.parse_key("Control+Shift+a") == (("Control", "Shift"), "a")
    assert sd.parse_key("+") == ((), "+") and sd.parse_key("F5") == ((), "F5")
    for bad in ("", "Hyper+a", "Foo", "a+b", "x" * 41, 7):
        with pytest.raises(sd.ActionError):
            sd.parse_key(bad)
    assert sd.clipboard_combo({"Control"}, "v") and sd.clipboard_combo({"Meta"}, "C") and sd.clipboard_combo({"Shift"}, "Insert")
    assert not sd.clipboard_combo({"Control"}, "a") and not sd.clipboard_combo(set(), "v")


def test_validate_action():
    assert sd.validate_action({"action": "navigate", "url": "example.com/a"})["url"] == "https://example.com/a"
    assert sd.validate_action({"action": "search", "query": " cats \n dogs "})["query"] == "cats dogs"
    assert sd.validate_action({"action": "click", "mark": 3}) == {"action": "click", "mark": 3}
    assert sd.validate_action({"action": "click", "point": [10, 20]})["point"] == [10.0, 20.0]
    assert sd.validate_action({"action": "type", "text": "hi", "submit": True}) == {"action": "type", "text": "hi", "submit": True}
    assert sd.validate_action({"action": "scroll"}) == {"action": "scroll", "direction": "down", "amount": 600}
    assert sd.validate_action({"action": "wait", "seconds": 2})["seconds"] == 2.0
    assert sd.validate_action({"action": "key", "key": "Enter"})["key"] == "Enter"
    assert sd.validate_action({"action": "back"}) == {"action": "back"}
    bad = [None, [], {}, {"action": "format"}, {"action": "navigate"}, {"action": "navigate", "url": "javascript:alert(1)"},
           {"action": "navigate", "url": "https://a b.com"}, {"action": "navigate", "url": "file:///etc/passwd"},
           {"action": "click"}, {"action": "click", "mark": 1, "point": [1, 1]}, {"action": "click", "mark": True},
           {"action": "click", "mark": 0}, {"action": "click", "point": [1280, 5]}, {"action": "click", "point": [float("nan"), 1]},
           {"action": "type", "text": ""}, {"action": "type", "text": "a\nb"}, {"action": "type", "text": "x" * 501},
           {"action": "type", "text": "a", "submit": "yes"}, {"action": "scroll", "direction": "left"},
           {"action": "scroll", "amount": 0}, {"action": "key", "key": "Hyper+x"}, {"action": "wait", "seconds": 11},
           {"action": "search", "query": ""}, {"action": "search", "query": "q" * 201}]
    for body in bad:
        with pytest.raises(sd.ActionError):
            sd.validate_action(body)


def test_action_policy():
    marks = {1: {"id": 1, "label": "Read more", "href": "https://example.com/a"}, 2: {"id": 2, "label": "Sign in"}}
    pol = lambda body: sd.action_policy(sd.validate_action(body), marks)  # noqa: E731
    assert pol({"action": "navigate", "url": "https://example.com"}) is None
    assert pol({"action": "navigate", "url": "https://www.paypal.com"}) == "blocked: banking"
    assert pol({"action": "search", "query": "porn"}) == "blocked: unsafe-text"
    assert pol({"action": "click", "mark": 1}) is None
    assert pol({"action": "click", "mark": 2}) == "blocked: login or account control"
    assert "not in the last observation" in pol({"action": "click", "mark": 9})
    assert pol({"action": "click", "point": [5, 5]}) is None
    assert pol({"action": "key", "key": "Control+v"}) == "blocked: clipboard keys are disabled"
    assert pol({"action": "type", "text": "4111 1111 1111 1111"}) == "blocked: card-number"
    assert pol({"action": "scroll"}) is None


def test_page_verdict():
    assert sd.page_verdict("https://example.com/", "Example", "Hello world") is None
    assert sd.page_verdict("https://www.paypal.com/", "PayPal", "x") == ("blocked", "banking")
    assert sd.page_verdict("chrome-error://chromewebdata/", "", "")[0] == "error"
    assert sd.page_verdict("https://example.com/", "Just a moment...", "Checking your browser")[0] == "wall"
    assert sd.page_verdict("https://example.com/", "Welcome", "Please sign in to continue to the site")[0] == "wall"
    assert sd.page_verdict("about:blank", "", "") is None


# --- outcome, marks, observation ---------------------------------------------------------------------------------------
def snap(url="https://a.test/", title="A", text="hello", y=0, color=(255, 255, 255)):
    return {"url": url, "title": title, "text": text, "scroll": {"y": y, "max": 900}, "jpeg": jpeg(color)}


def test_compute_outcome_reports_what_changed():
    same = sd.compute_outcome(snap(), snap(), [], 40)
    assert same["changed"] is False and same["errors"] == [] and same["load_ms"] == 40 and same["dialog"] is None
    assert sd.compute_outcome(snap(), snap(url="https://b.test/", title="B"), [], 5)["changed"] is True
    assert sd.compute_outcome(snap(), snap(y=300), [], 5)["changed"] is True
    assert sd.compute_outcome(snap(), snap(color=(0, 0, 0)), [], 5)["changed"] is True       # pixels only
    assert sd.compute_outcome(snap(), snap(color=(254, 255, 255)), [], 5)["changed"] is False  # noise
    out = sd.compute_outcome(snap(), snap(url="https://b.test/", title="B"), ["boom"], 1, {"type": "alert"})
    assert out["url_before"] == "https://a.test/" and out["url_after"] == "https://b.test/" and out["title_after"] == "B"
    assert out["errors"] == ["boom"] and out["dialog"] == {"type": "alert"}


def test_compute_outcome_without_an_observation_is_never_a_success():
    out = sd.compute_outcome(snap(), None, [], 9)
    assert out["changed"] is False and out["url_after"] == "" and "no post-action observation" in out["errors"][0]


def test_build_marks_orders_dedupes_clips_and_caps():
    raw = [{"idx": 0, "role": "link", "label": "  Second\n row ", "box": [300, 100, 80, 20], "href": "https://x.test/"},
           {"idx": 1, "role": "button", "label": "First", "box": [10, 98, 80, 24]},
           {"idx": 2, "role": "button", "label": "dup of first", "box": [11, 99, 80, 24]},
           {"idx": 3, "role": "link", "label": "tiny", "box": [0, 0, 3, 3]},
           {"idx": 4, "role": "link", "label": "offscreen", "box": [2000, 10, 50, 50]},
           {"idx": 5, "role": "textbox", "label": "Edge", "box": [1900, 1060, 100, 100], "typeable": True},
           {"idx": 6, "box": "bad"}, {"idx": 7, "role": "link", "label": "Top", "box": [500, 5, 60, 20]}]
    marks = sd.build_marks(raw, 1920, 1080)
    assert [m["label"] for m in marks] == ["Top", "First", "Second row", "Edge"]
    assert [m["id"] for m in marks] == [1, 2, 3, 4]
    assert marks[3]["box"] == [1900, 1060, 20, 20] and marks[3]["typeable"] is True
    many = [{"idx": i, "role": "link", "label": str(i), "box": [(i % 20) * 90, (i // 20) * 40, 80, 30]} for i in range(200)]
    assert len(sd.build_marks(many, 1920, 1080)) == sd.MAX_MARKS


def test_marks_are_drawn_on_the_observation_image():
    raw = [{"idx": 0, "role": "button", "label": "Go", "box": [600, 300, 300, 150]}]
    s = {**snap(text="word " * 2000), "width": 1920, "height": 1080, "marks": sd.build_marks(raw, 1920, 1080),
         "loading": True, "dialogs": [{"type": "alert"}]}
    obs = sd.build_observation(s, "ab12-1")
    img = Image.open(io.BytesIO(base64.b64decode(obs["jpeg_b64"])))
    assert img.format == "JPEG" and img.size == (1280, 720) == (obs["width"], obs["height"])
    assert obs["marks"] == [{"id": 1, "role": "button", "label": "Go", "box": [400, 200, 200, 100]}]
    assert len(obs["text"]) == sd.TEXT_MAX and obs["frame_id"] == "ab12-1" and obs["loading"] is True
    assert obs["dialogs"] == [{"type": "alert"}] and obs["scroll"] == {"y": 0, "max": 900}
    px = img.convert("RGB")
    edge, want = px.getpixel((401, 250)), sd.MARK_COLORS[1]                          # the mark's colour on a white page
    assert all(abs(a - b) < 40 for a, b in zip(edge, want)), (edge, want)
    assert min(px.getpixel((500, 250))) > 240 and min(px.getpixel((900, 600))) > 240   # inside and outside: untouched
    blank = sd.build_observation({**s, "marks": []}, "ab12-2")
    assert blank["marks"] == []
    assert blank["jpeg_b64"] != obs["jpeg_b64"]


def test_to_image_space_keeps_boxes_inside_the_image():
    marks = [{"id": 1, "role": "link", "label": "x", "box": [1915, 1075, 5, 5], "href": "https://x.test/" + "a" * 300}]
    pub = sd.to_image_space(marks, 1280 / 1920, 720 / 1080)[0]
    x, y, w, h = pub["box"]
    assert x + w <= 1280 and y + h <= 720 and w >= 1 and h >= 1 and len(pub["href"]) == 200


# --- input decoding ------------------------------------------------------------------------------------------------------
def test_decode_scancodes():
    shift_a = [0x2A, 0x1E, 0x9E, 0xAA]                    # key codes, so Shift types "A" (a plain "a" key would not)
    assert sd.decode_scancodes(shift_a) == [("down", "Shift"), ("down", "KeyA"), ("up", "KeyA"), ("up", "Shift")]
    assert sd.decode_scancodes([0xE0, 0x48, 0xE0, 0xC8]) == [("down", "ArrowUp"), ("up", "ArrowUp")]
    assert sd.decode_scancodes([0xE1, 0x1D, 0x45, 0x1C]) == [("down", "Enter")]       # Pause sequence dropped
    assert sd.decode_scancodes([0x00, 0x7F, 0xFF]) == []
    assert sd.decode_scancodes([0x39, 0xB9, 0x02, 0x1C]) == [("down", "Space"), ("up", "Space"), ("down", "Digit1"), ("down", "Enter")]
    assert sd.mod_name("ShiftRight") == "Shift" and sd.mod_name("Control") == "Control" and sd.mod_name("KeyA") is None
    assert sd.plain_key("KeyC") == "c" and sd.plain_key("Insert") == "Insert" and sd.plain_key("Key") == "Key"
    assert sd.decode_scancodes([0x35, 0x0C]) == [("down", "Slash"), ("down", "Minus")]


def test_validate_graphical_matches_the_pc_runner_contract():
    ok = sd.validate_graphical({"type": "vga-keyboard", "scancodes": [30, 158]})
    assert ok == {"type": "vga-keyboard", "scancodes": [30, 158]}
    mouse = sd.validate_graphical({"type": "vga-mouse", "dx": 5, "dy": -2.5, "wheel": 0, "buttons": [True, False, False],
                                   "native_receipt": {"input_id": 4, "generation": 9}, "junk": 1})
    assert mouse["native_receipt"] == {"input_id": 4, "generation": 9} and "junk" not in mouse
    for bad in ({"type": "x"}, {"type": "vga-keyboard"}, {"type": "vga-keyboard", "scancodes": []},
                {"type": "vga-keyboard", "scancodes": [256]}, {"type": "vga-keyboard", "scancodes": [True]},
                {"type": "vga-keyboard", "scancodes": list(range(17))},
                {"type": "vga-mouse", "dx": 0, "dy": 0, "wheel": 0, "buttons": [True, False]},
                {"type": "vga-mouse", "dx": 101, "dy": 0, "wheel": 0, "buttons": [False] * 3},
                {"type": "vga-mouse", "dx": float("inf"), "dy": 0, "wheel": 0, "buttons": [False] * 3},
                {"type": "vga-mouse", "dx": 0, "dy": 0, "wheel": 0, "buttons": [False] * 3, "native_receipt": {"input_id": 0}}):
        with pytest.raises(ValueError):
            sd.validate_graphical(bad)


# --- frames ------------------------------------------------------------------------------------------------------------------
def test_throttle_never_exceeds_ten_fps():
    now = [0.0]
    t = sd.Throttle(10, clock=lambda: now[0])
    published = 0
    for _ in range(120):                                  # a 60 fps screencast for two seconds
        if t.allow():
            published += 1
        now[0] += 1 / 60
    assert 18 <= published <= 21
    now[0] = 100.0
    t = sd.Throttle(10, clock=lambda: now[0])
    assert t.wait() == 0.0 and t.allow() and not t.allow() and abs(t.wait() - 0.1) < 1e-9
    now[0] += 0.05
    assert abs(t.wait() - 0.05) < 1e-9
    now[0] += 0.06
    assert t.wait() == 0.0


def test_frame_feed_ids_dedupe_and_full_size():
    feed = sd.FrameFeed(epoch="ab12cd")
    assert feed.display()["available"] is False and feed.full_png() is None
    a, b = jpeg((10, 10, 10)), jpeg((200, 10, 10))
    assert feed.publish(a, sd.render_frame(a)) is True and feed.revision == 1
    assert feed.publish(a, sd.render_frame(a)) is False and feed.revision == 1            # same picture: same id
    assert feed.publish(b, sd.render_frame(b)) is True and feed.revision == 2
    assert re.fullmatch(r"[0-9a-f-]+", feed.frame_id) and feed.frame_id == "ab12cd-2"     # alphabet the web house accepts
    d = feed.display()
    assert d == {"kind": "graphical", "available": True, "revision": 2, "frame_id": "ab12cd-2", "width": 1280,
                 "height": 720, "full_width": 1920, "full_height": 1080}
    assert Image.open(io.BytesIO(feed.png)).size == (1280, 720)
    frame_id, full = feed.full_png()
    assert frame_id == "ab12cd-2" and full.startswith(PNG) and Image.open(io.BytesIO(full)).size == (1920, 1080)
    feed.clear()
    assert feed.display()["available"] is False and feed.revision == 2
    assert feed.publish(b, sd.render_frame(b)) and feed.frame_id == "ab12cd-3"           # ids never repeat


def test_chromium_launch_settings_keep_secrets_out():
    env = sd.chromium_env(":102", {"PATH": "/bin", "LD_LIBRARY_PATH": "/libs", "SUB01_ADMIN_TOKEN": "x" * 20,
                                   "ANTHROPIC_API_KEY": "k", "DISPLAY": ":99", "HOME": "/home/u"})
    assert env == {"PATH": "/bin", "LD_LIBRARY_PATH": "/libs", "HOME": "/home/u", "DISPLAY": ":102"}
    cfg = sd.Config(profile=Path("/p"), width=1920, height=1080)
    args = sd.chromium_args(cfg)
    assert "--kiosk" in args and "--window-size=1920,1080" in args and "--deny-permission-prompts" in args
    assert "--kiosk" not in sd.chromium_args(sd.Config(profile=Path("/p"), kiosk=False))
    assert "--kiosk" not in sd.chromium_args(sd.Config(profile=Path("/p"), headless=True))


def test_events_are_json_lines_and_rotate(tmp_path):
    ev = sd.Events(tmp_path / "d" / "events.jsonl", limit=300)
    ev.append("act", action={"action": "back"}, ok=True)
    ev.append("blocked", reason="banking", odd=Path("/x"))
    lines = [json.loads(line) for line in (tmp_path / "d" / "events.jsonl").read_text().splitlines()]
    assert [x["kind"] for x in lines] == ["act", "blocked"] and lines[0]["ok"] is True and lines[1]["odd"] == "/x"
    assert lines[0]["t"].endswith("+00:00")
    assert oct((tmp_path / "d" / "events.jsonl").stat().st_mode & 0o777) == "0o600"
    for i in range(120):
        ev.append("fill", i=i, pad="x" * 50)
    assert (tmp_path / "d" / "events.jsonl.1").exists()


@pytest.mark.skipif(not Path("/proc/self/cmdline").exists(), reason="needs /proc")
def test_kill_profile_processes_takes_the_children_and_spares_other_profiles(tmp_path):
    mine, other = tmp_path / "profile", tmp_path / "other"
    parent = ("import subprocess, sys, time; c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
              " print(c.pid, flush=True); time.sleep(60)")
    a = subprocess.Popen([sys.executable, "-c", parent, f"--user-data-dir={mine}"], stdout=subprocess.PIPE, text=True)
    b = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"--user-data-dir={other}"])
    child = int(a.stdout.readline())
    try:
        killed = sd.kill_profile_processes(mine)
        assert a.pid in killed and child in killed and b.pid not in killed
        assert a.wait(5) == -9 and b.poll() is None
        assert sd.kill_profile_processes(tmp_path / "nothing") == []
    finally:
        for proc in (a, b):
            proc.kill()
            proc.wait()


def test_main_refuses_unsafe_settings(tmp_path, monkeypatch, capsys):
    token = tmp_path / "token"
    token.write_text("operator-credential-test\n")
    base = ["--token-file", str(token)]
    for argv in (["--data-dir", str(tmp_path / "d"), "--host", "0.0.0.0"],
                 ["--data-dir", str(ROOT / "runtime")],
                 ["--data-dir", str(tmp_path / ".config" / "google-chrome" / "Default")],
                 ["--data-dir", str(tmp_path / "d"), "--home-origin", "http://example.com:80"],
                 ["--data-dir", str(tmp_path / "d"), "--size", "big"]):
        with pytest.raises(SystemExit):
            sd.main(base + argv)
    short = tmp_path / "short"
    short.write_text("abc")
    with pytest.raises(SystemExit):
        sd.main(["--token-file", str(short), "--data-dir", str(tmp_path / "d")])


# --- the HTTP app with a fake browser ------------------------------------------------------------------------------------
class FakeDesktop:
    """Same surface as Desktop (status, restarts, display, frame, snapshot, do, forward, type_text, release_inputs)."""

    def __init__(self):
        self.status, self.restarts, self.error, self.on_change = "ready", 0, "", lambda: None
        self.feed = sd.FrameFeed(epoch="abc123")
        self.page = {"url": "about:blank", "title": "", "text": "", "y": 0, "color": (255, 255, 255), "loading": False,
                     "raw": [{"idx": 0, "role": "link", "label": "More", "box": [100, 100, 120, 30],
                              "href": "https://example.com/more"},
                             {"idx": 1, "role": "button", "label": "Sign in", "box": [400, 100, 120, 30]},
                             {"idx": 2, "role": "searchbox", "label": "Search", "box": [100, 200, 400, 40], "typeable": True}]}
        self.calls, self.forwarded, self.typed, self.released = [], [], [], 0
        self.dialog, self.fail_do_status, self.snapshot_fails_after = None, None, None
        self.publish((10, 20, 30))

    def publish(self, color):
        data = jpeg(color)
        if self.feed.publish(data, sd.render_frame(data)):
            self.on_change()

    def display(self):
        d = self.feed.display()
        d["available"] = d["available"] and self.status == "ready"
        return d

    async def frame(self, full=False):
        if self.status != "ready" or self.feed.png is None:
            return None
        return await asyncio.to_thread(self.feed.full_png) if full else (self.feed.frame_id, self.feed.png)

    async def snapshot(self, obs=None):
        if self.status != "ready" or self.snapshot_fails_after == 0:
            raise sd.DesktopUnavailable(self.status)
        if self.snapshot_fails_after is not None:
            self.snapshot_fails_after -= 1
        p = self.page
        return {"url": p["url"], "title": p["title"], "text": p["text"], "scroll": {"y": p["y"], "max": 900},
                "loading": p["loading"], "width": 1920, "height": 1080, "jpeg": jpeg(p["color"]),
                "marks": sd.build_marks(p["raw"], 1920, 1080) if obs else [], "dialogs": []}

    async def do(self, action):
        self.calls.append(action)
        p, kind, errors = self.page, action["action"], []
        if kind == "navigate":
            p.update(url=action["url"], title="Page", text="Hello from " + action["url"], color=(240, 240, 255), y=0)
        elif kind == "search":
            p.update(url=sd.SEARCH_URL + action["query"], title="Results", text="results", color=(230, 255, 230))
        elif kind == "scroll":
            p["y"] = min(900, p["y"] + action["amount"]) if action["direction"] == "down" else max(0, p["y"] - action["amount"])
        elif kind == "click" and "mark_info" in action and action["mark_info"].get("href"):
            p.update(url=action["mark_info"]["href"], title="More", text="more text", color=(255, 240, 240))
        if self.fail_do_status:
            errors.append(self.fail_do_status)
        return {"errors": errors, "dialog": self.dialog, "load_ms": 12}

    async def forward(self, clean):
        self.forwarded.append(clean)
        return True

    async def type_text(self, text):
        self.typed.append(text)
        return True

    async def release_inputs(self):
        self.released += 1


async def started(tmp_path, clock=None):
    desk = FakeDesktop()
    events = sd.Events(tmp_path / "events.jsonl")
    runner = sd.Runner(desk, TOKEN, events, **({"clock": clock} if clock else {}))
    desk.on_change = runner.notify
    http = TestClient(TestServer(sd.create_app(runner)))
    await http.start_server()
    return http, runner, desk


def events_of(tmp_path):
    path = tmp_path / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_runner_needs_a_real_credential(tmp_path):
    with pytest.raises(ValueError):
        sd.Runner(FakeDesktop(), "short", sd.Events(tmp_path / "e.jsonl"))


def test_every_route_but_health_requires_the_operator_credential(tmp_path):
    async def body():
        http, _, _ = await started(tmp_path)
        try:
            assert (await http.get("/healthz")).status == 200
            for method, path in [("get", "/pc/state"), ("get", "/pc/frame.png"), ("post", "/pc/input"),
                                 ("post", "/pc/graphical-input"), ("post", "/pc/session"), ("post", "/pc/privacy"),
                                 ("get", "/devices/state"), ("get", "/devices/phone/frame.jpg"),
                                 ("post", "/devices/phone/action"), ("get", "/desktop/observe"), ("post", "/desktop/act")]:
                assert (await getattr(http, method)(path, json={})).status == 403, path
                assert (await getattr(http, method)(path, json={}, headers={"X-Admin-Token": "wrong-credential"})).status == 403
        finally:
            await http.close()
    run(body())


def test_pc_state_contract_for_the_native_monitor_and_the_house(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            state = await (await http.get("/pc/state", headers=AUTH)).json()
            assert state["status"] == "ready" and state["ready"] is True and state["privacy"] is False
            assert state["session"] is False and state["restarts"] == 0
            d = state["display"]
            assert d["kind"] == "graphical" and d["available"] is True and d["frame_id"] == "abc123-1"
            assert isinstance(d["revision"], int) and (d["width"], d["height"]) == (1280, 720)
            assert re.fullmatch(r"[0-9a-f-]+", d["frame_id"])
            await http.post("/pc/session", json={"active": True}, headers=AUTH)
            assert (await (await http.get("/pc/state", headers=AUTH)).json())["session"] is True
            desk.status, desk.restarts = "restarting", 2
            state = await (await http.get("/pc/state", headers=AUTH)).json()
            assert state["status"] == "restarting" and state["ready"] is False and state["restarts"] == 2
            assert state["display"]["available"] is False
        finally:
            await http.close()
    run(body())


def test_frame_png_revisions_etag_full_size_and_restarting(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            r = await http.get("/pc/frame.png", headers=AUTH)
            pixels = await r.read()
            assert r.status == 200 and r.content_type == "image/png" and pixels.startswith(PNG)
            assert Image.open(io.BytesIO(pixels)).size == (1280, 720) and r.headers["ETag"] == '"vga-abc123-1"'
            assert (await http.get("/pc/frame.png", headers={**AUTH, "If-None-Match": '"vga-abc123-1"'})).status == 304
            assert (await http.get("/pc/frame.png?revision=abc123-1", headers=AUTH)).status == 200
            assert (await http.get("/pc/frame.png?revision=abc123-0", headers=AUTH)).status == 409
            full = await http.get("/pc/frame.png?full=1&revision=abc123-1", headers=AUTH)
            assert Image.open(io.BytesIO(await full.read())).size == (1920, 1080) and full.headers["ETag"].endswith('-full"')
            desk.publish((200, 0, 0))
            assert (await http.get("/pc/frame.png?revision=abc123-1", headers=AUTH)).status == 409
            assert (await http.get("/pc/frame.png?revision=abc123-2", headers=AUTH)).status == 200
            desk.status = "restarting"
            assert (await http.get("/pc/frame.png", headers=AUTH)).status == 404
        finally:
            await http.close()
    run(body())


def test_state_long_poll_wakes_on_a_new_frame_and_on_privacy(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            since = (await (await http.get("/pc/state", headers=AUTH)).json())["revision"]
            waiting = asyncio.create_task(http.get(f"/pc/state?since={since}&wait=5", headers=AUTH))
            await asyncio.sleep(0.1)
            assert not waiting.done()
            desk.publish((1, 2, 3))
            r = await asyncio.wait_for(waiting, 2)
            assert (await r.json())["revision"] == since + 1
            waiting = asyncio.create_task(http.get(f"/pc/state?since={since + 1}&wait=5", headers=AUTH))
            await asyncio.sleep(0.1)
            await http.post("/pc/privacy", json={"active": True}, headers=AUTH)
            assert (await (await asyncio.wait_for(waiting, 2)).json())["privacy"] is True
            assert (await http.get("/pc/state?since=x", headers=AUTH)).status == 400
            t0 = asyncio.get_running_loop().time()
            await http.get(f"/pc/state?since={since + 1}&wait=0.3", headers=AUTH)
            assert asyncio.get_running_loop().time() - t0 < 2
        finally:
            await http.close()
    run(body())


def test_privacy_masks_state_and_refuses_pixels_input_and_the_agent(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            view = await (await http.post("/pc/privacy", json={"active": True}, headers=AUTH)).json()
            assert view == {"status": "ready", "ready": True, "paused": True, "output": "", "last_command": None,
                            "revision": None, "privacy": True}
            assert desk.released == 1
            assert (await http.get("/pc/frame.png", headers=AUTH)).status == 409
            for method, path, payload in [("post", "/pc/input", {"input": "x"}), ("post", "/pc/session", {"active": True}),
                                          ("post", "/pc/graphical-input", {"type": "vga-keyboard", "scancodes": [30]}),
                                          ("get", "/desktop/observe", None), ("get", "/devices/state", None),
                                          ("post", "/desktop/act", {"action": "back"})]:
                r = await getattr(http, method)(path, headers=AUTH, **({"json": payload} if payload is not None else {}))
                assert r.status == 409, path
            assert desk.typed == [] and desk.forwarded == [] and desk.calls == []
            await http.post("/pc/privacy", json={"active": True, "source": "home"}, headers=AUTH)
            await http.post("/pc/privacy", json={"active": False}, headers=AUTH)       # the home source still holds it
            assert (await (await http.get("/pc/state", headers=AUTH)).json())["privacy"] is True
            await http.post("/pc/privacy", json={"active": False, "source": "home"}, headers=AUTH)
            assert (await (await http.get("/pc/state", headers=AUTH)).json())["privacy"] is False
            assert (await http.post("/pc/privacy", json={"active": 1}, headers=AUTH)).status == 400
            assert (await http.post("/pc/privacy", json={"active": True, "source": "x"}, headers=AUTH)).status == 400
        finally:
            await http.close()
    run(body())


def test_session_expires_and_native_release_frees_held_input(tmp_path):
    async def body():
        now = [1000.0]
        http, runner, desk = await started(tmp_path, clock=lambda: now[0])
        try:
            await http.post("/pc/session", json={"active": True, "source": "native"}, headers=AUTH)
            assert (await (await http.get("/pc/state", headers=AUTH)).json())["session"] is True
            now[0] += 61
            assert (await (await http.get("/pc/state", headers=AUTH)).json())["session"] is False
            await http.post("/pc/session", json={"active": True}, headers=AUTH)
            await http.post("/pc/session", json={"active": False}, headers=AUTH)
            assert desk.released == 1
            assert (await http.post("/pc/session", json={"active": True, "source": "x"}, headers=AUTH)).status == 400
            assert (await http.post("/pc/session", json={"active": "yes"}, headers=AUTH)).status == 400
        finally:
            await http.close()
    run(body())


def test_graphical_input_is_validated_forwarded_and_receipted(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            key = {"type": "vga-keyboard", "scancodes": [42, 30, 158, 170]}
            r = await http.post("/pc/graphical-input", json=key, headers=AUTH)
            assert r.status == 200 and await r.json() == {"ok": True}
            mouse = {"type": "vga-mouse", "dx": 12, "dy": -3, "wheel": 0, "buttons": [True, False, False]}
            assert (await http.post("/pc/graphical-input", json=mouse, headers=AUTH)).status == 200
            assert [f["type"] for f in desk.forwarded] == ["vga-keyboard", "vga-mouse"]
            r = await http.post("/pc/graphical-input", json={**key, "native_receipt": {"input_id": 7, "generation": 3}}, headers=AUTH)
            body_ = await r.json()
            assert body_["ok"] is True and body_["native_receipt"] == {"input_id": 7, "generation": 3}
            assert body_["ack_level"] == "GuestKeyboardInjected" and "native_receipt" not in desk.forwarded[-1]
            assert 0 <= body_["ack_received_at"] - body_["queued_at"] <= 3.5
            assert 0 <= body_["worker_finished_ms"] - body_["worker_started_ms"] <= 1500
            r = await http.post("/pc/graphical-input", json={**mouse, "native_receipt": {"input_id": 8, "generation": 3}}, headers=AUTH)
            assert (await r.json())["ack_level"] == "GuestMouseInjected"
            for bad in ({"type": "x"}, {"type": "vga-keyboard", "scancodes": [999]}, {**key, "native_receipt": {"input_id": 0, "generation": 1}}):
                assert (await http.post("/pc/graphical-input", json=bad, headers=AUTH)).status == 400
            desk.status = "restarting"
            assert (await http.post("/pc/graphical-input", json=key, headers=AUTH)).status == 409
            assert len(desk.forwarded) == 4
        finally:
            await http.close()
    run(body())


def test_a_slow_page_is_reported_as_not_delivered(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)

        async def never(clean):
            await asyncio.sleep(30)
        desk.forward = never
        try:
            runner_call = sd.asyncio.wait_for
            r = await asyncio.wait_for(http.post("/pc/graphical-input", json={"type": "vga-keyboard", "scancodes": [30]}, headers=AUTH), 5)
            assert r.status == 200 and await r.json() == {"ok": False}
            del runner_call
        finally:
            await http.close()
    run(body())


def test_pc_input_types_text_and_enter(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            r = await http.post("/pc/input", json={"input": "hello"}, headers=AUTH)
            assert (await r.json())["ok"] is True and desk.typed == ["hello\n"]
            await http.post("/pc/input", json={"input": "raw", "raw": True}, headers=AUTH)
            assert desk.typed[-1] == "raw"
            blocked = await (await http.post("/pc/input", json={"input": "4111 1111 1111 1111"}, headers=AUTH)).json()
            assert blocked["ok"] is False and len(desk.typed) == 2
            for bad in ({"input": 5}, {"input": "x" * 2001}, {"input": "a", "raw": "no"}, {}):
                assert (await http.post("/pc/input", json=bad, headers=AUTH)).status == 400
            assert (await http.post("/pc/input", data=b"x" * 5000, headers=AUTH)).status == 413
            assert (await http.post("/pc/input", data=b"{oops", headers=AUTH)).status == 400
        finally:
            await http.close()
    run(body())


def test_observe_returns_the_marked_screenshot(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        desk.page.update(url="https://example.com/", title="Example", text="Example Domain " * 400, y=120)
        try:
            r = await http.get("/desktop/observe", headers=AUTH)
            obs = await r.json()
            assert r.status == 200 and obs["url"] == "https://example.com/" and obs["title"] == "Example"
            assert re.fullmatch(r"[0-9a-f]+-[0-9a-f]+", obs["frame_id"])
            img = Image.open(io.BytesIO(base64.b64decode(obs["jpeg_b64"])))
            assert img.format == "JPEG" and img.size == (1280, 720)
            assert len(obs["text"]) <= 3000 and obs["scroll"] == {"y": 120, "max": 900}
            assert obs["loading"] is False and obs["dialogs"] == []
            assert [(m["id"], m["role"], m["label"]) for m in obs["marks"]] == [(1, "link", "More"), (2, "button", "Sign in"), (3, "searchbox", "Search")]
            assert obs["marks"][0]["box"] == [67, 67, 80, 20]
            second = await (await http.get("/desktop/observe", headers=AUTH)).json()
            assert second["frame_id"] != obs["frame_id"]
            desk.status = "restarting"
            r = await http.get("/desktop/observe", headers=AUTH)
            assert r.status == 503 and (await r.json())["ok"] is False
        finally:
            await http.close()
    run(body())


def test_act_navigate_reports_a_real_outcome_and_logs_it(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            r = await http.post("/desktop/act", json={"action": "navigate", "url": "https://example.com/a"}, headers=AUTH)
            res = await r.json()
            assert r.status == 200 and res["ok"] is True and re.fullmatch(r"[0-9a-f]+-[0-9a-f]+", res["frame_id"])
            o = res["outcome"]
            assert o == {"url_before": "about:blank", "url_after": "https://example.com/a", "title_after": "Page",
                         "changed": True, "errors": [], "load_ms": 12, "dialog": None}
            assert desk.calls[0]["url"] == "https://example.com/a"
            res = await (await http.post("/desktop/act", json={"action": "wait", "seconds": 0}, headers=AUTH)).json()
            assert res["ok"] is True and res["outcome"]["changed"] is False       # nothing happened: said so
            log = events_of(tmp_path)
            assert [e["kind"] for e in log] == ["act", "act"] and log[0]["action"]["url"] == "https://example.com/a"
            assert log[0]["ok"] is True and log[0]["outcome"]["changed"] is True and log[1]["outcome"]["changed"] is False
        finally:
            await http.close()
    run(body())


def test_act_refuses_blocked_targets_without_touching_the_browser(tmp_path, capsys):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            for payload, reason in [({"action": "navigate", "url": "https://www.paypal.com/"}, "blocked: banking"),
                                    ({"action": "navigate", "url": "https://github.com/login"}, "blocked: login-path"),
                                    ({"action": "search", "query": "free porn"}, "blocked: unsafe-text"),
                                    ({"action": "key", "key": "Control+v"}, "blocked: clipboard keys are disabled"),
                                    ({"action": "type", "text": "5500 0000 0000 0004"}, "blocked: card-number")]:
                res = await (await http.post("/desktop/act", json=payload, headers=AUTH)).json()
                assert res["ok"] is False and res["outcome"]["errors"] == [reason], payload
                assert res["outcome"]["changed"] is False and res["outcome"]["url_after"] == "about:blank"
            assert desk.calls == []
            blocked = [e for e in events_of(tmp_path) if e["kind"] == "blocked"]
            assert len(blocked) == 5 and blocked[0]["reason"] == "blocked: banking"
            assert "streamer desktop: blocked action navigate" in capsys.readouterr().out
        finally:
            await http.close()
    run(body())


def test_act_rejects_malformed_bodies(tmp_path):
    async def body():
        http, _, desk = await started(tmp_path)
        try:
            for payload in ({"action": "hover"}, {"action": "navigate", "url": "javascript:alert(1)"},
                            {"action": "click"}, {"action": "type", "text": ""}, []):
                r = await http.post("/desktop/act", json=payload, headers=AUTH)
                assert r.status == 400, payload
            assert (await http.post("/desktop/act", data=b"x" * 5000, headers=AUTH)).status == 413
            assert desk.calls == []
        finally:
            await http.close()
    run(body())


def test_click_uses_the_marks_of_the_last_observation(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            r = await http.post("/desktop/act", json={"action": "click", "mark": 1}, headers=AUTH)
            assert "call /desktop/observe first" in (await r.json())["outcome"]["errors"][0]
            obs = await (await http.get("/desktop/observe", headers=AUTH)).json()
            stale = await (await http.post("/desktop/act", json={"action": "click", "mark": 1, "frame_id": "zz-1"}, headers=AUTH)).json()
            assert stale["ok"] is False and "stale frame_id" in stale["outcome"]["errors"][0]
            res = await (await http.post("/desktop/act", json={"action": "click", "mark": 1, "frame_id": obs["frame_id"]}, headers=AUTH)).json()
            assert res["ok"] is True and res["outcome"]["url_after"] == "https://example.com/more" and res["outcome"]["changed"] is True
            call = desk.calls[-1]
            assert call["mark"] == 1 and call["obs"] == obs["frame_id"] and call["mark_info"]["href"] == "https://example.com/more"
            obs2 = await (await http.get("/desktop/observe", headers=AUTH)).json()
            login = await (await http.post("/desktop/act", json={"action": "click", "mark": 2}, headers=AUTH)).json()
            assert login["ok"] is False and login["outcome"]["errors"] == ["blocked: login or account control"]
            assert len(desk.calls) == 1 and obs2["frame_id"]
            point = await (await http.post("/desktop/act", json={"action": "click", "point": [640, 360]}, headers=AUTH)).json()
            assert point["ok"] is True and desk.calls[-1]["point"] == [640.0, 360.0]
        finally:
            await http.close()
    run(body())


def test_scroll_that_moves_nothing_is_not_a_success(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            res = await (await http.post("/desktop/act", json={"action": "scroll", "direction": "up"}, headers=AUTH)).json()
            assert res["ok"] is False and res["outcome"]["changed"] is False and "nothing moved" in res["outcome"]["errors"][0]
            res = await (await http.post("/desktop/act", json={"action": "scroll", "amount": 300}, headers=AUTH)).json()
            assert res["ok"] is True and res["outcome"]["changed"] is True
        finally:
            await http.close()
    run(body())


def test_act_reports_dialogs_browser_errors_and_walls(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            desk.dialog = {"type": "alert", "message": "Hi", "action": "dismissed", "t": 1.0}
            res = await (await http.post("/desktop/act", json={"action": "navigate", "url": "https://example.com/"}, headers=AUTH)).json()
            assert res["ok"] is True and res["outcome"]["dialog"]["message"] == "Hi"
            desk.dialog, desk.fail_do_status = None, "navigation failed: net::ERR_NAME_NOT_RESOLVED"
            res = await (await http.post("/desktop/act", json={"action": "navigate", "url": "https://nope.invalid/"}, headers=AUTH)).json()
            assert res["ok"] is False and res["outcome"]["errors"] == ["navigation failed: net::ERR_NAME_NOT_RESOLVED"]
            desk.fail_do_status = None
            desk.page.update(url="https://example.com/x", title="Just a moment...", text="Checking your browser")
            res = await (await http.post("/desktop/act", json={"action": "wait", "seconds": 0}, headers=AUTH)).json()
            assert res["ok"] is False and res["outcome"]["errors"][0].startswith("wall:")
        finally:
            await http.close()
    run(body())


def test_a_page_that_lands_on_a_blocked_site_is_replaced_by_a_blank_page(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        orig = desk.do

        async def redirecting(action):
            out = await orig(action)
            if action.get("url") == "https://example.com/redirect":
                desk.page.update(url="https://www.paypal.com/login", title="PayPal", text="Log in")
            if action.get("url") == "about:blank":
                desk.page.update(url="about:blank", title="", text="")
            return out
        desk.do = redirecting
        try:
            res = await (await http.post("/desktop/act", json={"action": "navigate", "url": "https://example.com/redirect"}, headers=AUTH)).json()
            assert res["ok"] is False and res["outcome"]["url_after"] == "about:blank"
            assert res["outcome"]["errors"] == ["blocked page (banking): replaced by a blank page"]
            assert [c.get("url") for c in desk.calls] == ["https://example.com/redirect", "about:blank"]
            assert any(e["kind"] == "blocked" and e["what"] == "page" for e in events_of(tmp_path))
        finally:
            await http.close()
    run(body())


def test_a_restarting_browser_is_never_reported_as_success(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            desk.snapshot_fails_after = 1                    # the "before" snapshot works, the one after the action does not
            res = await (await http.post("/desktop/act", json={"action": "navigate", "url": "https://example.com/"}, headers=AUTH)).json()
            assert res["ok"] is False and res["frame_id"] is None and res["outcome"]["changed"] is False
            assert "no post-action observation" in res["outcome"]["errors"][0]
            desk.snapshot_fails_after = None
            desk.status = "restarting"
            r = await http.post("/desktop/act", json={"action": "navigate", "url": "https://example.com/"}, headers=AUTH)
            assert r.status == 503 and (await r.json())["ok"] is False and (await r.json())["status"] == "restarting"
        finally:
            await http.close()
    run(body())


def test_actions_are_serialised(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        running, peak = [0], [0]
        orig = desk.do

        async def slow(action):
            running[0] += 1
            peak[0] = max(peak[0], running[0])
            await asyncio.sleep(0.05)
            running[0] -= 1
            return await orig(action)
        desk.do = slow
        try:
            await asyncio.gather(*(http.post("/desktop/act", json={"action": "scroll", "amount": 10}, headers=AUTH) for _ in range(4)))
            assert peak[0] == 1 and len(desk.calls) == 4
        finally:
            await http.close()
    run(body())


def test_devices_proxy_needs_a_home_origin_and_follows_privacy(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        backend_calls = []

        async def home(request):
            backend_calls.append((request.path, request.headers.get("X-Admin-Token")))
            return web.json_response({"home": {"privacy": False}, "phone_screen": None})
        backend = TestServer(web.Application())
        backend.app.router.add_get("/api/home", home)
        await backend.start_server()
        try:
            assert (await http.get("/devices/state", headers=AUTH)).status == 503
            from scripts.home_device_proxy import HomeDeviceProxy
            runner.home_devices = HomeDeviceProxy(f"http://127.0.0.1:{backend.port}", TOKEN, runner)
            r = await http.get("/devices/state", headers=AUTH)
            assert r.status == 200 and (await r.json())["home"] == {"privacy": False}
            assert backend_calls and backend_calls[0] == ("/api/home", TOKEN)
            assert (await http.get("/devices/phone/frame.jpg", headers=AUTH)).status == 404       # no phone frame: honest
            assert (await http.post("/devices/phone/action", json={"action": "bogus"}, headers=AUTH)).status == 400
            await http.post("/pc/privacy", json={"active": True}, headers=AUTH)
            assert (await http.get("/devices/state", headers=AUTH)).status == 409
        finally:
            await runner.home_devices.close()
            await http.close()
            await backend.close()
    run(body())


# --- the browser-side logic against fake Playwright objects (no browser) -----------------------------------------------
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

    async def down(self, button="left"):
        self.log.append(("down", button))

    async def up(self, button="left"):
        self.log.append(("up", button))

    async def wheel(self, dx, dy):
        self.log.append(("wheel", dx, dy))


class FakePage:
    def __init__(self, focus=None):
        self.keyboard, self.mouse, self.focus = FakeKeyboard(), FakeMouse(), focus

    async def evaluate(self, js, arg=None):
        return self.focus


def make_desktop(tmp_path, focus=None, **cfg):
    desk = sd.Desktop(sd.Config(profile=tmp_path / "profile", **cfg), sd.Events(tmp_path / "events.jsonl"))
    desk.status, desk.page = "ready", FakePage(focus)
    desk._input_lock = asyncio.Lock()
    return desk


def test_native_keyboard_reaches_the_page_with_shift_and_without_clipboard(tmp_path):
    async def body():
        desk = make_desktop(tmp_path)
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x2A, 0x1E, 0x9E, 0xAA]})
        assert desk.page.keyboard.log == [("down", "Shift"), ("down", "KeyA"), ("up", "KeyA"), ("up", "Shift")]
        assert desk.held == set()
        desk.page.keyboard.log.clear()
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x1D, 0x2F, 0xAF, 0x9D]})      # Ctrl+V
        assert desk.page.keyboard.log == [("down", "Control"), ("up", "Control")]
        assert [e["reason"] for e in events_of(tmp_path)] == ["clipboard"]
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x1E]})                         # a key held down
        assert desk.held == {"KeyA"}
        await desk.release_inputs()
        assert desk.page.keyboard.log[-1] == ("up", "KeyA") and desk.held == set()
    run(body())


def test_native_keyboard_never_types_into_sensitive_fields_or_a_dead_browser(tmp_path):
    async def body():
        desk = make_desktop(tmp_path, focus={"tag": "input", "type": "password", "editable": True})
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x1E, 0x9E]}) is False
        assert desk.page.keyboard.log == [] and events_of(tmp_path)[0]["reason"] == "password field"
        desk = make_desktop(tmp_path, focus={"tag": "input", "type": "search", "editable": True, "name": "q"})
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x1E, 0x9E]}) is True
        desk.status = "restarting"
        assert await desk.forward({"type": "vga-keyboard", "scancodes": [0x1E]}) is False
    run(body())


def test_native_mouse_moves_clicks_and_scrolls_the_page(tmp_path):
    async def body():
        desk = make_desktop(tmp_path)
        desk.view = (1920, 1080)
        desk.cursor = [960, 540]
        await desk.forward({"type": "vga-mouse", "dx": 10, "dy": -5, "wheel": 0, "buttons": [False] * 3})
        await desk.forward({"type": "vga-mouse", "dx": 0, "dy": 0, "wheel": 0, "buttons": [True, False, False]})
        await desk.forward({"type": "vga-mouse", "dx": 0, "dy": 0, "wheel": 0, "buttons": [True, False, False]})   # still held
        await desk.forward({"type": "vga-mouse", "dx": 0, "dy": 0, "wheel": 2, "buttons": [False, False, True]})
        assert desk.page.mouse.log == [("move", 960 + 20, 540 - 10), ("down", "left"), ("up", "left"),
                                       ("down", "right"), ("wheel", 0, 80)]
        for _ in range(30):
            await desk.forward({"type": "vga-mouse", "dx": 100, "dy": 100, "wheel": 0, "buttons": [False, False, True]})
        assert desk.cursor == [1919, 1079]                  # clamped to the page
        await desk.release_inputs()
        assert desk.page.mouse.log[-1] == ("up", "right") and desk.buttons == [False] * 3
    run(body())


def test_pc_input_types_only_into_a_safe_editable_field(tmp_path):
    async def body():
        text = {"tag": "textarea", "type": "", "editable": True, "name": "msg"}
        desk = make_desktop(tmp_path, focus=text)
        assert await desk.type_text("hello\nworld\x03\n") is True
        assert desk.page.keyboard.log == [("insert", "hello"), ("press", "Enter"), ("insert", "world"), ("press", "Enter")]
        assert await make_desktop(tmp_path, focus=None).type_text("x") is False
        assert await make_desktop(tmp_path, focus={"tag": "input", "type": "email", "editable": True}).type_text("x") is False
        assert await make_desktop(tmp_path, focus={"tag": "button", "editable": False}).type_text("x") is False
    run(body())


class FakeRoute:
    def __init__(self, url, nav=False, method="GET", top=True):
        frame = type("F", (), {"parent_frame": None if top else object()})()
        self.request = type("R", (), {"url": url, "method": method, "frame": frame, "is_navigation_request": lambda s: nav})()
        self.done = None

    async def abort(self, code="failed"):
        self.done = ("abort", code)

    async def continue_(self):
        self.done = ("continue",)


def test_network_guard_blocks_pages_posts_and_private_addresses(tmp_path):
    async def body():
        desk = make_desktop(tmp_path)

        async def resolves(host):
            return host != "rebind.example.net"
        desk.resolver.public = resolves
        cases = [(FakeRoute("https://www.paypal.com/", nav=True), ("abort", "blockedbyclient")),
                 (FakeRoute("https://example.com/form", nav=True, method="POST"), ("abort", "blockedbyclient")),
                 (FakeRoute("https://example.com/", nav=True), ("continue",)),
                 (FakeRoute("https://cdn.example.com/a.js"), ("continue",)),
                 (FakeRoute("https://accounts.google.com/gsi/client"), ("abort", "blockedbyclient")),
                 (FakeRoute("https://example.com/frame", nav=True, top=False), ("continue",)),
                 (FakeRoute("https://rebind.example.net/x"), ("abort", "blockedbyclient")),
                 (FakeRoute("http://169.254.169.254/latest/meta-data"), ("abort", "blockedbyclient")),
                 (FakeRoute("data:text/plain,hi"), ("continue",))]
        for route, expected in cases:
            await desk._route(route)
            assert route.done == expected, route.request.url
        assert [w for w, _ in desk.blocked_nav] == ["banking", "post-navigation"] and desk.blocked_count == 5
        assert any(e["kind"] == "blocked" and e["what"] == "navigation" for e in events_of(tmp_path))
    run(body())


def test_redirects_are_checked_even_though_routes_only_see_the_first_request(tmp_path):
    async def body():
        desk = make_desktop(tmp_path)
        killed = []
        desk._blank = lambda: killed.append(1) or asyncio.sleep(0)

        def response(status, location, url="https://example.com/start", nav=True, top=True):
            frame = type("F", (), {"parent_frame": None if top else object(), "page": desk.page})()
            req = type("R", (), {"frame": frame, "is_navigation_request": lambda s: nav})()
            return type("Resp", (), {"status": status, "url": url, "headers": {"location": location}, "request": req})()
        desk._on_response(response(302, "https://example.com/next"))
        desk._on_response(response(200, "https://www.paypal.com/"))
        desk._on_response(response(302, "https://www.paypal.com/", top=False))
        desk._on_response(response(302, "https://www.paypal.com/", nav=False))
        assert killed == [] and desk.blocked_nav == []
        desk._on_response(response(302, "/account/login"))                                  # relative Location
        desk._on_response(response(301, "https://www.paypal.com/"))
        await asyncio.sleep(0)
        assert [w for w, _ in desk.blocked_nav] == ["login-path", "banking"] and len(killed) == 2
        frame = type("F", (), {"parent_frame": None, "page": desk.page, "url": "https://accounts.google.com/x"})()
        desk._on_navigated(frame)                                                           # a JS redirect that committed
        frame.url = "about:blank"
        desk._on_navigated(frame)
        frame.url = "https://example.com/ok"
        desk._on_navigated(frame)
        assert len(killed) == 3
    run(body())


def test_dialogs_and_popups_are_handled_and_reported(tmp_path):
    async def body():
        desk = make_desktop(tmp_path)

        class Dialog:
            def __init__(self, type_, message):
                self.type, self.message, self.did = type_, message, None

            async def dismiss(self):
                self.did = "dismiss"

            async def accept(self):
                self.did = "accept"
        alert, leave = Dialog("alert", "hi"), Dialog("beforeunload", "")
        await desk._on_dialog(alert)
        await desk._on_dialog(leave)
        assert (alert.did, leave.did) == ("dismiss", "accept")
        assert [d["action"] for d in desk.dialogs] == ["dismissed", "accepted (leave page)"]
        assert desk.act_dialog["type"] == "beforeunload"
        assert [d["type"] for d in desk.pop_dialogs()] == ["alert", "beforeunload"] and desk.pop_dialogs() == []
        closed = []

        class Popup:
            url = "https://example.com/pop"

            async def close(self):
                closed.append(1)
        desk._on_new_page(desk.page)                        # the main page itself is not a popup
        desk._on_new_page(Popup())
        await asyncio.sleep(0)
        assert closed == [1] and desk.popups == ["https://example.com/pop"]
        desk._refused("download", "https://example.com/x.bin")
        assert desk.refused == ["download"]
    run(body())


class FakeCDP:
    def __init__(self):
        self.sent = []

    async def send(self, method, params=None):
        self.sent.append((method, params))


def test_screencast_acks_every_frame_at_once_and_publishes_at_most_ten_per_second(tmp_path):
    async def body():
        desk = make_desktop(tmp_path)
        desk.cdp, desk._frame_event, notified = FakeCDP(), asyncio.Event(), []
        desk.on_change = lambda: notified.append(1)
        publisher = asyncio.create_task(desk._publisher())
        last = None
        for i in range(60):                                 # a 100 fps screencast for 0.6 s
            last = jpeg((i * 4 % 256, 30, 90), size=(640, 360))
            desk._on_frame({"sessionId": f"s{i}", "data": base64.b64encode(last).decode()})
            await asyncio.sleep(0.01)
        for _ in range(100):                                # the newest picture must land, however loaded the machine is
            await asyncio.sleep(0.05)
            if desk.feed.raw == last:
                break
        publisher.cancel()
        acks = [p["sessionId"] for m, p in desk.cdp.sent if m == "Page.screencastFrameAck"]
        assert acks == [f"s{i}" for i in range(60)]         # every frame, in order, none dropped
        assert 2 <= desk.feed.revision <= 12 and len(notified) == desk.feed.revision    # ~10 fps, not 100
        assert desk.feed.raw == last                        # the newest picture wins
        assert Image.open(io.BytesIO(desk.feed.png)).size == (1280, 720)
    run(body())


def test_supervisor_relaunches_after_failures_and_counts_restarts(tmp_path, capsys):
    async def body():
        desk = make_desktop(tmp_path)
        desk.RELAUNCH_DELAY, seen, launches = 0.01, [], []
        desk._wake = asyncio.Event()

        async def launch():
            launches.append(1)
            if len(launches) <= 2:
                raise RuntimeError("Missing X server or $DISPLAY")
            desk._why = None

        async def watch():
            if len(launches) == 3:
                desk._why = "page crashed"                   # first working browser crashes at once
            else:
                await asyncio.sleep(0.2)

        async def teardown():
            seen.append(desk.status)
        desk._launch, desk._watch, desk._teardown = launch, watch, teardown
        task = asyncio.create_task(desk._supervise())
        for _ in range(100):
            await asyncio.sleep(0.02)
            if len(launches) >= 4 and desk.status == "ready":
                break
        desk.stopping = True
        task.cancel()
        assert len(launches) == 4 and desk.restarts == 3 and desk.status == "ready"
        assert seen == ["restarting"] * 3 and desk.error == ""
        kinds = [e["kind"] for e in events_of(tmp_path)]
        assert kinds.count("error") == 2 and kinds.count("relaunch") == 3 and kinds.count("browser") == 2
        out = capsys.readouterr().out
        assert "streamer desktop: error: Missing X server" in out and "streamer desktop: relaunch #3" in out
    run(body())


def test_a_hanging_page_read_asks_for_a_relaunch_and_fails_honestly(tmp_path):
    async def body():
        desk = make_desktop(tmp_path)
        desk._wake, desk.GUARD_S = asyncio.Event(), 0.05

        async def stuck(js, arg=None):
            await asyncio.sleep(60)
        desk.page.evaluate = stuck
        with pytest.raises(sd.DesktopUnavailable, match="page read timed out"):
            await desk.snapshot("obs-1")
        assert desk._why == "page read timed out" and desk._wake.is_set()
        result = await desk.do({"action": "navigate", "url": "https://example.com/"})     # never raises, never "ok"
        assert result["errors"] and result["load_ms"] >= 0
    run(body())


def test_healthz_reports_status_without_credentials(tmp_path):
    async def body():
        http, runner, desk = await started(tmp_path)
        try:
            desk.status, desk.restarts = "restarting", 3
            assert await (await http.get("/healthz")).json() == {"ok": True, "status": "restarting", "restarts": 3}
        finally:
            await http.close()
    run(body())
