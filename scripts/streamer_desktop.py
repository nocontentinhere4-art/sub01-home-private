#!/usr/bin/env python3
"""SUB-01 streamer desktop: a real headed Chromium on its own X display, served on loopback.

One Playwright Chromium (dedicated persistent profile inside --data-dir, never the owner's), shown on an X display
(default :102, 1920x1080). It serves two things on one port, every route except /healthz needs `X-Admin-Token`:

  PC runner contract (same as scripts/home_pc_runner.py, so the native 3D monitor and the web house keep working):
    GET  /pc/state[?since=REV&wait=S]   status, ready, display{kind:"graphical",...}, privacy, session, restarts
    GET  /pc/frame.png[?revision=ID&full=1]   PNG of the desktop (1280x720; full=1: 1920x1080), from CDP screencast
    POST /pc/input, /pc/graphical-input, /pc/session, /pc/privacy      (PS/2 scancodes and relative mouse -> the page)
    GET  /devices/state, /devices/{device}/frame.jpg, POST /devices/{device}/action   (--home-origin proxy)
  Agent API (docs/streamer/PLAN.md):
    GET  /desktop/observe   screenshot 1280x720 with numbered marks, visible text, marks, scroll, dialogs
    POST /desktop/act       navigate | click | type | scroll | key | back | search | wait -> {ok, outcome, frame_id}

Safety: banking/adult/gambling/trading/login/checkout/payment hosts and paths are refused (also redirects and
sub-frames), no POST navigation, no downloads, file chooser, clipboard or popups, service workers blocked, dialogs
dismissed and reported. A crashed or hung browser is relaunched (`/pc/state.status` is "restarting" meanwhile).
Everything the agent does is appended to <data-dir>/events.jsonl. Playwright is imported only by the Desktop class.

PC modes (`--pc-mode`, docs/streamer/VAGON.md): `chromium` (default, everything above) or `vagon`: the same Chromium
opens the owner's Vagon Streams page (`--vagon-url` or <streamer-dir>/vagon.json) in kiosk mode, presses its
connect/play button, waits for the stream's video/canvas and re-enters after "session ended". The agent primitives are
mapped onto the stream: click/scroll/type/key go to the stream element, navigate/search type the URL into the remote
browser's address bar (Ctrl+L, text, Enter), observe returns the pixels with `mode: "vagon"` and `remote_ready` and no
DOM summary. `/pc/state` carries `pc_mode` and a `vagon` sub-state. The stream URL's query string is never logged.
"""

import argparse
import asyncio
import base64
import hashlib
import hmac
import io
import ipaddress
import json
import math
import os
import re
import secrets
import signal
import socket
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote, urljoin, urlsplit

from aiohttp import web
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from computer.input_receipts import native_receipt  # noqa: E402

try:  # stdlib-only guard lists and banner helpers; importing browse.py starts nothing
    import browse as B  # noqa: E402
except Exception:  # the runner also works when only this file is deployed
    B = None

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MIN_TOKEN = 12
MAX_WAIT = 25
SCREEN = (1920, 1080)
SMALL = (1280, 720)
MAX_FPS = 10
IDLE_CAP_S = 10.0
NAV_TIMEOUT_MS = 15000
ACT_TIMEOUT_S = 45.0
TEXT_MAX = 3000
MAX_MARKS = 60
IMAGE_CHANGE = 1.5            # mean grey-level change (0..255) of 64x36 thumbnails that counts as a visible change
SEARCH_URL = "https://html.duckduckgo.com/html/?q="
MOUSE_GAIN = 2.0              # native relative mouse units -> page pixels
SAFE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TMPDIR", "USER", "LD_LIBRARY_PATH", "PLAYWRIGHT_BROWSERS_PATH",
            "FONTCONFIG_PATH", "XAUTHORITY", "XDG_RUNTIME_DIR")
FOREIGN_PROFILES = ("google-chrome", "/chromium", "application support/google", "appdata/local/google", "bravesoftware",
                    "microsoft edge", "/firefox", "/.mozilla")
PC_MODES = ("chromium", "vagon")
DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
VAGON_SCHEMA = "sub01.streamer-vagon.v1"
VAGON_TICK_S = 2.0            # how often the stream page is probed for its connect / ended state
VAGON_CLICK_GAP_S = 6.0       # at least this long between two presses of the stream's connect button
VAGON_RELOAD_BACKOFF = (15.0, 30.0, 60.0, 120.0, 300.0)   # seconds before the stream page is opened again
VAGON_BLANK_RELOAD_S = 60.0   # a stream page with neither a button nor a stream for this long is opened again
VAGON_MISSES = 3              # consecutive probes without the stream before "connected" is dropped
VAGON_TYPE_DELAY_MS = 12      # per character: the stream client needs real key events, not inserted text
VAGON_SETTLE_S = 0.8          # pixels need a round trip to the remote machine before they can be compared
VAGON_NAV_SETTLE_S = 2.5
VAGON_MIN_STREAM = (320, 180)


def log(message):
    print(f"streamer desktop: {message}", flush=True)


# --- policy: what the desktop never opens, types or clicks --------------------------------------------------------
ADULT_HOST = re.compile(r"porn|xxx|xvideo|xhamster|redtube|youporn|onlyfans|fansly|hentai|chaturbate|stripchat|"
                        r"livejasmin|camgirl|escort|nsfw|erotic|fetish|(^|[.-])(sex|nude|nudes|naked|adult)([.-]|$)", re.I)
GAMBLING_HOST = re.compile(r"casino|poker|betting|bet365|sportsbet|gambl|(^|[.-])(slots?|lottery)([.-]|$)", re.I)
BANK_HOST = re.compile(r"(^|[.-])(\w*bank\w*|paypal\w*|venmo|revolut|n26|monzo|klarna|payoneer|westernunion|moneygram|"
                       r"skrill|neteller|alipay|paytm|wellsfargo|hsbc|barclays|santander|unicredit|intesasanpaolo|"
                       r"postepay|mediolanum|fineco|sparkasse|commerzbank|mastercard)([.-]|$)|"
                       r"(^|\.)(wise|chase|stripe|capitalone|americanexpress|amex|citi|ing|schwab|fidelity|vanguard|"
                       r"zellepay)\.(com|co\.uk|it|de|nl|fr|es)$|(^|\.)cash\.app$", re.I)
PAYMENT_HOST = re.compile(r"^(pay|payments?|checkout|billing|wallet)\.", re.I)
LOGIN_HOST = re.compile(r"^(login|signin|sign-in|sso|auth|oauth|accounts?|idp)\.", re.I)
OWNER_HOST = re.compile(r"(^|\.)(claude\.ai|console\.anthropic\.com|mail\.google\.com|myaccount\.google\.com|"
                        r"accounts\.google\.com|login\.microsoftonline\.com|login\.live\.com|outlook\.live\.com|"
                        r"outlook\.office\.com|appleid\.apple\.com|icloud\.com|runpod\.io|railway\.app)$", re.I)
HOST_RULES = (("adult", ADULT_HOST), ("gambling", GAMBLING_HOST), ("banking", BANK_HOST), ("payment", PAYMENT_HOST),
              ("login", LOGIN_HOST), ("owner-service", OWNER_HOST))
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|sign-?up|signin|signup|servicelogin|userlogin|createaccount|register|"
                        r"my-?account|accounts?|password|oauth2?|sso)(/|\?|$|\.)", re.I)
WIKI_LOGIN = re.compile(r"Special:(UserLogin|CreateAccount)", re.I)
CHECKOUT_PATH = re.compile(r"/(checkout|cart|basket|payments?|pay|billing|purchase|orders?|subscribe|donate|wallet|"
                           r"invoice)(/|\?|$|\.)", re.I)
DOWNLOAD_EXT = re.compile(r"\.(pdf|zip|rar|7z|exe|dmg|apk|msi|iso|tar|gz|tgz|bz2|xz|deb|rpm|docx?|xlsx?|pptx?|mp3|mp4|"
                          r"mov|avi|mkv|torrent)$", re.I)
ADULT_WORDS = re.compile(r"\b(porn\w*|xxx|nsfw|hentai|onlyfans|nudes?|naked|escort\w*|camgirl\w*)\b", re.I)
CARD_LIKE = re.compile(r"(?:\d[ -]?){13,19}")
MONEY_LABEL = re.compile(r"\b(buy( now)?|purchase|add to (cart|basket|bag)|checkout|place (an )?order|pay( now)?|donate|"
                         r"subscribe|upgrade|top ?up|deposit|withdraw|connect (your )?wallet|swap|stake|mint|claim)\b", re.I)
MONEY_PATH = re.compile(r"/(buy|sell|deposit|withdraw|stake|bridge|wallet|swap)(/|\?|$|-)", re.I)
LOGIN_LABEL = re.compile(r"^\W*(log ?in|sign ?(in|up)|register|create (an )?account|my account|cart|basket|"
                         r"continue with (google|apple|facebook))\b", re.I)
WALL_TEXT = re.compile(r"verify you are (a )?human|unusual traffic|captcha|checking your browser|are you a robot|"
                       r"access denied|just a moment", re.I)
LOGIN_TEXT = re.compile(r"(log|sign) ?in to (continue|view|see|read|watch)|please (log|sign) in|sign up to (continue|read|"
                        r"see)|you must be (logged|signed) in|create (a free |an )?account to", re.I)
AC_BAD = re.compile(r"cc-|password|username|email|tel|address|postal|one-time|bday", re.I)
NAME_BAD = re.compile(r"(^|[^a-z])(pass(word|wd)?|cvv|cvc|iban|ssn|otp|routing|e-?mail|username|address|postal|phone|tel)"
                      r"([^a-z]|$)|card|credit|ccnum", re.I)
NO_TYPE = {"password", "email", "tel", "number", "date", "datetime-local", "month", "time", "week", "file"}
MODS = {"Control", "Shift", "Alt", "Meta", "ControlOrMeta"}
NAMED_KEYS = {"Enter", "Tab", "Escape", "Backspace", "Delete", "Space", "ArrowUp", "ArrowDown", "ArrowLeft",
              "ArrowRight", "Home", "End", "PageUp", "PageDown", "Insert"} | {f"F{i}" for i in range(1, 13)}


def private_host(host):
    h = (host or "").strip("[]").rstrip(".").lower()
    if h in ("localhost", "metadata", "metadata.google.internal") or h.endswith(
            (".local", ".internal", ".localhost", ".lan", ".home", ".corp")):
        return True
    try:
        return not ipaddress.ip_address(h).is_global
    except ValueError:
        return "." not in h                      # single-label and numeric-obfuscated names never leave the LAN


def blocked_host(host, allow_private=False):
    """Why a host is refused (adult, gambling, banking, payment, login, owner service, trading, private), or None."""
    h = (host or "").strip("[]").lower().rstrip(".")
    if not h:
        return "no-host"
    if private_host(h):
        return None if allow_private else "private-host"
    plain = (B.HOST_FALSE_HITS.sub("", h) if B else re.sub(r"sussex|essex|middlesex|wessex", "", h))
    for why, rx in HOST_RULES:
        if rx.search(plain):
            return why
    if B and (B.trading_host(h) or B.BAD_HOST.search(plain)):
        return "blocked-site"
    return None


def blocked_url(url, allow_private=False):
    """Why a page URL is refused, or None. Used for navigate/search, links, redirects and the page's final address."""
    try:
        u = urlsplit(str(url or ""))
        port = u.port
    except ValueError:
        return "invalid-url"
    if u.scheme not in ("http", "https"):
        return "scheme"
    if u.username or u.password:
        return "credentials-in-url"
    why = blocked_host(u.hostname, allow_private)
    if why:
        return why
    if port not in (None, 80, 443) and not allow_private:
        return "port"
    path = unquote(u.path)
    if WIKI_LOGIN.search(path + "?" + u.query):
        return "login-path"
    article = path.startswith("/wiki/")                  # Wikipedia titles like /wiki/Password are articles, not forms
    if not article and CHECKOUT_PATH.search(path):
        return "checkout-path"
    if not article and (LOGIN_PATH.search(path) or (B and B.LOGIN_HREF.search(path))):
        return "login-path"
    if DOWNLOAD_EXT.search(path):
        return "download"
    return None


def request_blocked(url, main_frame=False, method="GET", allow_private=False):
    """Network-level verdict for one request. Main-frame navigations get the full URL rules and must be GET/HEAD;
    everything else (sub-frames, scripts, images) only the host rules, so a page cannot embed a login or bank frame."""
    if url == "about:blank" or url.startswith(("data:", "blob:")):
        return None
    if main_frame:
        return "post-navigation" if method.upper() not in ("GET", "HEAD") else blocked_url(url, allow_private)
    try:
        u = urlsplit(url)
        port = u.port
    except ValueError:
        return "invalid-url"
    if u.scheme not in ("http", "https"):
        return "scheme"
    why = blocked_host(u.hostname, allow_private)
    return why or ("port" if port not in (None, 80, 443) and not allow_private else None)


def text_blocked(text):
    """Typed or searched text that must not be sent: adult/harm words, card-like numbers."""
    t = str(text or "")
    if ADULT_WORDS.search(t) or (B and B.MEDIA_BAD_WORDS.search(t)):
        return "unsafe-text"
    return "card-number" if CARD_LIKE.search(t) else None


def mark_blocked(mark, allow_private=False):
    """Why clicking this link/button is refused: a blocked link, a money control, a login control."""
    href, label = str(mark.get("href") or ""), str(mark.get("label") or "")
    if href:
        why = blocked_url(href, allow_private)
        if why:
            return f"link target ({why})"
    if MONEY_LABEL.search(label) or (href and MONEY_PATH.search(urlsplit(href).path)):
        return "money control"
    if LOGIN_LABEL.search(label):
        return "login or account control"
    return None


def field_blocked(info):
    """Why typing into the focused element is refused (password, e-mail, card, address fields), or None."""
    if not info:
        return None
    type_, ac, name = str(info.get("type") or ""), str(info.get("ac") or ""), str(info.get("name") or "")
    if type_ in NO_TYPE and info.get("tag") == "input":
        return f"{type_} field"
    if AC_BAD.search(ac) or NAME_BAD.search(name):
        return "sensitive field"
    return None


def parse_key(key):
    """('Control','Shift'), 'a' from "Control+Shift+a"; ActionError when it is not a plain key or combination."""
    if not isinstance(key, str) or not 1 <= len(key) <= 40:
        raise ActionError("Expected a key name such as Enter or Control+a")
    parts = [key] if key == "+" else key.split("+")
    *mods, last = parts
    if any(m not in MODS for m in mods) or not (last in NAMED_KEYS or (len(last) == 1 and last.isprintable() and last != " ")):
        raise ActionError("Unsupported key; use a named key (Enter, ArrowDown, F5...), one character or Modifier+key")
    return tuple(mods), last


def clipboard_combo(mods, key):
    mods = set(mods)
    base = {"Control", "Meta", "ControlOrMeta"} & mods
    return bool((base and key.lower() in ("c", "v", "x", "insert")) or ("Shift" in mods and key in ("Insert", "Delete")))


# --- action validation, outcome, marks (pure) ---------------------------------------------------------------------
class ActionError(ValueError):
    """A malformed request (HTTP 400). Policy refusals are not errors of this kind: they come back as ok=false."""


ACTIONS = ("navigate", "click", "type", "scroll", "key", "back", "search", "wait")


def _num(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _plain(value, limit):
    return isinstance(value, str) and 1 <= len(value) <= limit and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def normalize_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(c.isspace() or ord(c) < 32 for c in value.strip()):
        raise ActionError("Expected an http(s) URL without spaces")
    v = value.strip()
    if "://" not in v and re.match(r"^[\w-]+(\.[\w-]+)+(:\d+)?([/?#]|$)", v):
        v = "https://" + v
    if not re.match(r"^https?://", v, re.I):
        raise ActionError("Expected an http(s) URL")
    return v


def validate_action(body):
    """Normalise a /desktop/act body; ActionError when it is malformed."""
    if not isinstance(body, dict):
        raise ActionError("Expected an action object")
    kind = body.get("action")
    if kind not in ACTIONS:
        raise ActionError("Unknown action; expected one of " + ", ".join(ACTIONS))
    out = {"action": kind}
    if body.get("frame_id") is not None:
        if not _plain(body["frame_id"], 64):
            raise ActionError("Invalid frame_id")
        out["frame_id"] = body["frame_id"]
    mark = body.get("mark")
    if mark is not None and (isinstance(mark, bool) or not isinstance(mark, int) or not 1 <= mark <= 999):
        raise ActionError("mark must be a mark id from the last observation")
    if kind == "navigate":
        out["url"] = normalize_url(body.get("url"))
    elif kind == "search":
        query = body.get("query")
        if not isinstance(query, str) or not _plain(" ".join(query.split()), 200):
            raise ActionError("Expected a search query of at most 200 characters")
        out["query"] = " ".join(query.split())
    elif kind == "click":
        point = body.get("point")
        if (mark is None) == (point is None):
            raise ActionError("Give exactly one of mark or point")
        if mark is not None:
            out["mark"] = mark
        else:
            if (not isinstance(point, list) or len(point) != 2 or not all(_num(v) for v in point)
                    or not 0 <= point[0] < SMALL[0] or not 0 <= point[1] < SMALL[1]):
                raise ActionError("point must be [x, y] inside the 1280x720 observation image")
            out["point"] = [float(point[0]), float(point[1])]
    elif kind == "type":
        if not _plain(body.get("text"), 500):
            raise ActionError("Expected text of 1-500 characters without control characters")
        submit = body.get("submit", False)
        if not isinstance(submit, bool):
            raise ActionError("submit must be a boolean")
        out.update(text=body["text"], submit=submit)
        if mark is not None:
            out["mark"] = mark
    elif kind == "scroll":
        direction, amount = body.get("direction", "down"), body.get("amount", 600)
        if direction not in ("up", "down") or not _num(amount) or not 1 <= amount <= 5000:
            raise ActionError("Expected direction up|down and an amount of 1-5000 pixels")
        out.update(direction=direction, amount=int(amount))
    elif kind == "key":
        parse_key(body.get("key"))
        out["key"] = body["key"]
    elif kind == "wait":
        seconds = body.get("seconds", 1)
        if not _num(seconds) or not 0 <= seconds <= IDLE_CAP_S:
            raise ActionError("Expected seconds between 0 and 10")
        out["seconds"] = float(seconds)
    return out


def action_policy(action, marks=None, allow_private=False):
    """Refusal text for an action the desktop will not do (before anything happens), else None."""
    kind = action["action"]
    if kind == "navigate":
        why = blocked_url(action["url"], allow_private)
        return f"blocked: {why}" if why else None
    if kind == "search":
        why = text_blocked(action["query"])
        return f"blocked: {why}" if why else None
    if kind == "key":
        mods, last = parse_key(action["key"])
        return "blocked: clipboard keys are disabled" if clipboard_combo(mods, last) else None
    if kind in ("click", "type") and "mark" in action:
        mark = (marks or {}).get(action["mark"])
        if mark is None:
            return f"mark {action['mark']} is not in the last observation; call /desktop/observe first"
        why = mark_blocked(mark, allow_private)
        if why:
            return f"blocked: {why}"
    if kind == "type":
        why = text_blocked(action["text"])
        return f"blocked: {why}" if why else None
    return None


def page_verdict(url, title, text, allow_private=False):
    """('blocked'|'wall'|'error', reason) for the page that is now on screen, or None. 'blocked' pages are replaced
    by a blank page; walls (bot check, sign-in) and load errors are reported to the agent."""
    url, title, text = url or "", title or "", text or ""
    if url.startswith("chrome-error:"):
        return "error", "page failed to load"
    if url and url != "about:blank":
        why = blocked_url(url, allow_private)
        if why:
            return "blocked", why
    if B:
        if B.is_finance(url, title, text):
            return "blocked", "trading"
        if not B.text_ok(title, text):
            return "blocked", "unsafe-content"
        if B.challenge_title(title, url) or (len(text) < B.WALL_MAX_CHARS and B.BODY_WALL.search(text)):
            return "wall", "bot check or error page"
        if len(text) < B.LOGIN_WALL_MAX_CHARS and B.LOGIN_WALL.search(text):
            return "wall", "sign-in wall"
    elif len(text) < 2000 and WALL_TEXT.search(text):
        return "wall", "bot check or error page"
    elif len(text) < 3000 and LOGIN_TEXT.search(text):
        return "wall", "sign-in wall"
    return None


def _thumb(jpeg):
    img = Image.open(io.BytesIO(jpeg))
    img.draft("L", (128, 72))                            # JPEG decodes at 1/8 size: cheap
    return img.convert("L").resize((64, 36))


def image_delta(a_jpeg, b_jpeg):
    """Mean grey-level difference (0..255) of 64x36 thumbnails; 0 when either picture is missing."""
    if not a_jpeg or not b_jpeg:
        return 0.0
    try:
        a, b = (_thumb(x) for x in (a_jpeg, b_jpeg))
        return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
    except Exception:
        return 0.0


def compute_outcome(before, after, errors, load_ms, dialog=None):
    """Outcome of an action from two real observations. `after` None means nothing could be observed: never a success."""
    errors = [str(e)[:200] for e in errors][:8]
    b, a = before or {}, after
    if a is None:
        errors = (errors + ["no post-action observation: the browser is unavailable"])[:8]
        return {"url_before": b.get("url", ""), "url_after": "", "title_after": "", "changed": False,
                "errors": errors, "load_ms": int(load_ms), "dialog": dialog}
    changed = (a.get("url") != b.get("url") or a.get("title") != b.get("title") or a.get("text") != b.get("text")
               or (a.get("scroll") or {}).get("y") != (b.get("scroll") or {}).get("y")
               or image_delta(b.get("jpeg"), a.get("jpeg")) > IMAGE_CHANGE)
    return {"url_before": b.get("url", ""), "url_after": a.get("url", ""), "title_after": a.get("title", ""),
            "changed": bool(changed), "errors": errors, "load_ms": int(load_ms), "dialog": dialog}


def _iou(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / float(a[2] * a[3] + b[2] * b[3] - w * h)


def build_marks(raw, vw, vh, limit=MAX_MARKS):
    """Number the clickable/typeable elements found in the page (page pixels): clipped to the viewport, no near
    duplicates (a link wrapping a button), reading order (rows, then left to right), ids 1..N."""
    items = []
    for r in raw or []:
        try:
            x, y, w, h = (float(v) for v in r["box"])
        except (KeyError, TypeError, ValueError):
            continue
        x0, y0, x1, y1 = max(0.0, x), max(0.0, y), min(float(vw), x + w), min(float(vh), y + h)
        if x1 - x0 < 6 or y1 - y0 < 6:
            continue
        items.append({"idx": r.get("idx", len(items)), "role": str(r.get("role") or "clickable")[:20],
                      "label": " ".join(str(r.get("label") or "").split())[:60],
                      "box": [round(x0), round(y0), round(x1 - x0), round(y1 - y0)],
                      "href": str(r.get("href") or "")[:300], "typeable": bool(r.get("typeable"))})
    items.sort(key=lambda m: ((m["box"][1] + m["box"][3] / 2) // 24, m["box"][0]))
    out = []
    for m in items:
        if any(_iou(m["box"], o["box"]) > 0.85 for o in out):
            continue
        out.append(m)
        if len(out) >= limit:
            break
    for i, m in enumerate(out, 1):
        m["id"] = i
    return out


def to_image_space(marks, sx, sy, size=SMALL):
    """The public marks {id, role, label, box} in observation-image pixels (1280x720)."""
    out = []
    for m in marks:
        x, y, w, h = m["box"]
        x0, y0 = min(size[0] - 1, max(0, round(x * sx))), min(size[1] - 1, max(0, round(y * sy)))
        x1, y1 = min(size[0], max(x0 + 1, round((x + w) * sx))), min(size[1], max(y0 + 1, round((y + h) * sy)))
        pub = {"id": m["id"], "role": m["role"], "label": m["label"], "box": [x0, y0, x1 - x0, y1 - y0]}
        if m.get("href"):
            pub["href"] = m["href"][:200]
        out.append(pub)
    return out


MARK_COLORS = [(230, 57, 70), (29, 120, 220), (36, 160, 80), (240, 140, 0), (150, 70, 200), (0, 160, 160)]


def _font(size=14):
    try:
        return ImageFont.load_default(size)
    except TypeError:                                    # Pillow < 10.1
        return ImageFont.load_default()


def draw_marks(img, marks):
    """Draw each mark's rectangle and its number on `img` (RGB, observation size), in place."""
    draw, font = ImageDraw.Draw(img), _font()
    for m in marks:
        x, y, w, h = m["box"]
        color = MARK_COLORS[m["id"] % len(MARK_COLORS)]
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=color, width=2)
        label = str(m["id"])
        tw = int(draw.textlength(label, font=font)) + 6
        cy = y - 16 if y >= 16 else y
        draw.rectangle([x, cy, x + tw, cy + 15], fill=color)
        draw.text((x + 3, cy), label, fill=(255, 255, 255), font=font)
    return img


def trim_text(text, limit=TEXT_MAX):
    return " ".join(str(text or "").split())[:limit]


def build_observation(snap, frame_id, size=SMALL, quality=78):
    """The /desktop/observe body from a raw snapshot: downscaled screenshot with the marks drawn on it."""
    img = Image.open(io.BytesIO(snap["jpeg"])).convert("RGB")
    sx, sy = size[0] / float(snap.get("width") or img.size[0]), size[1] / float(snap.get("height") or img.size[1])
    img = img.resize(size, getattr(Image, "Resampling", Image).BILINEAR)
    marks = to_image_space(snap.get("marks") or [], sx, sy, size)
    draw_marks(img, marks)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality)
    obs = {"frame_id": frame_id, "url": snap.get("url", ""), "title": snap.get("title", ""),
           "jpeg_b64": base64.b64encode(out.getvalue()).decode("ascii"), "width": size[0], "height": size[1],
           "text": trim_text(snap.get("text")), "marks": marks, "scroll": snap.get("scroll") or {"y": 0, "max": 0},
           "loading": bool(snap.get("loading")), "dialogs": list(snap.get("dialogs") or [])}
    if snap.get("mode"):                                 # vagon: pixels of a remote machine, no DOM to summarise
        obs["mode"] = snap["mode"]
        obs["remote_ready"] = bool(snap.get("remote_ready"))
    return obs


# --- Vagon Streams: the stream page's connect / ended states and the config file (pure) ----------------------------
# The connection page's DOM is not documented (docs/streamer/VAGON.md), so buttons are found by their visible text.
VAGON_RECONNECT_RX = re.compile(r"\b(reconnect|try again|retry|connect again|restart session|new session)\b", re.I)
VAGON_CONNECT_RX = re.compile(r"\b(connect|start( stream(ing)?)?|play|launch|continue|enter|join|open stream|resume)\b", re.I)
VAGON_ENDED_RX = re.compile(r"session (has )?(ended|expired|terminated|timed out|is over)|session end(ed)?\b|"
                            r"(stream|session|link) is (expired|not available|paused|inactive)|disconnected|"
                            r"connection (lost|failed|closed)|you (have been|were) disconnected|time is up|"
                            r"(idle|inactivity) (limit|time ?out)|something went wrong|failed to connect|"
                            r"no (available )?(capacity|machine)|insufficient capacity|stream (is )?(unavailable|offline)", re.I)
VAGON_BUSY_RX = re.compile(r"connecting|initializ|preparing|loading|starting|installing|please wait|setting up|"
                           r"waiting for|assigning|booting|queue", re.I)
VAGON_PHASES = ("starting", "waiting", "busy", "ready", "ended", "blank", "restarting")


def redact_url(url):
    """What may be logged or shown of a stream link: scheme and host, the path replaced by an ellipsis; never the
    query string (tokens, launch flags, visitor e-mail) or the fragment. Empty for an unusable value."""
    try:
        u = urlsplit(str(url or ""))
    except ValueError:
        return ""
    if not u.scheme or not u.hostname:
        return ""
    host = u.hostname + (f":{u.port}" if u.port else "")
    return f"{u.scheme}://{host}/" + ("…" if u.path.strip("/") or u.query else "")


def vagon_url_problem(url, allow_private=False):
    """Why a stream link cannot be used, or None: the page rules apply (https only, no credentials in the URL, no
    private host unless tests allow it, no login/checkout path), plus the link must not be a bare origin."""
    if not isinstance(url, str) or not url.strip() or any(c.isspace() for c in url.strip()):
        return "expected a stream URL"
    u = urlsplit(url.strip())
    if u.scheme != "https" and not (allow_private and u.scheme == "http"):
        return "the stream link must be https"
    why = blocked_url(url.strip(), allow_private)
    if why:
        return why
    if not u.path.strip("/") and not u.query:
        return "the stream link has no path"
    return None


def load_vagon_config(path, allow_private=False):
    """<streamer-dir>/vagon.json -> {"stream_url", "api_key_file"}; ValueError (without the URL) when unusable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"cannot read the Vagon config: {error.strerror or error}")
    except ValueError:
        raise ValueError("the Vagon config is not valid JSON")
    if not isinstance(data, dict) or data.get("schema") != VAGON_SCHEMA:
        raise ValueError(f"the Vagon config must be an object with schema {VAGON_SCHEMA}")
    url = data.get("stream_url")
    if url is not None:
        why = vagon_url_problem(url, allow_private)
        if why:
            raise ValueError(f"stream_url: {why}")
        url = url.strip()
    key_file = data.get("api_key_file")
    if key_file is not None and (not isinstance(key_file, str) or not key_file.strip() or not os.path.isabs(key_file.strip())):
        raise ValueError("api_key_file must be an absolute path")
    unknown = set(data) - {"schema", "stream_url", "api_key_file"}
    if unknown:
        raise ValueError("unknown keys in the Vagon config: " + ", ".join(sorted(unknown)))
    return {"stream_url": url or "", "api_key_file": (key_file or "").strip()}


def api_key_file_status(path):
    """'none' | 'configured' | 'missing' | 'permissive' for the optional API key file; its content is never read."""
    if not path:
        return "none"
    try:
        st = os.stat(path)
    except OSError:
        return "missing"
    return "permissive" if st.st_mode & 0o077 else "configured"


def choose_vagon_button(buttons):
    """Index of the button to press on the stream page: a reconnect/try-again control first, then connect/start/play.
    Buttons whose text names something else (settings, mute, full screen, sign in...) are never pressed."""
    best, best_rank = None, None
    for i, b in enumerate(buttons or []):
        label = " ".join(str(b.get("label") or "").split())
        if not label or LOGIN_LABEL.search(label) or MONEY_LABEL.search(label):
            continue
        rank = 0 if VAGON_RECONNECT_RX.search(label) else 1 if VAGON_CONNECT_RX.search(label) else None
        if rank is not None and (best_rank is None or rank < best_rank):
            best, best_rank = i, rank
    return best


def classify_vagon(probe):
    """(phase, button index or None) from a probe of the stream page: ready (a video that plays or a canvas of a
    useful size), ended (the page says so, or offers a reconnect), waiting (a connect button), busy (the page says
    it is connecting), blank (nothing usable yet)."""
    p = probe or {}
    stream, text = p.get("stream") or None, " ".join(str(p.get("text") or "").split())
    button = choose_vagon_button(p.get("buttons"))
    reconnect = button is not None and VAGON_RECONNECT_RX.search(str(p["buttons"][button].get("label") or ""))
    if stream and stream.get("playing", True) and not reconnect and not (VAGON_ENDED_RX.search(text) and button is not None):
        return "ready", None
    if VAGON_ENDED_RX.search(text) or reconnect:
        return "ended", button
    if button is not None:
        return "waiting", button
    if stream or VAGON_BUSY_RX.search(text):
        return "busy", None
    return "blank", None


def image_point(point, view, size=SMALL):
    """A point of the 1280x720 observation image -> page pixels, clamped to the viewport."""
    x = min(view[0] - 1, max(0, point[0] * view[0] / size[0]))
    y = min(view[1] - 1, max(0, point[1] * view[1] / size[1]))
    return x, y


class VagonState:
    """What the runner knows about the remote session; `public()` is the `vagon` field of /pc/state."""

    def __init__(self, api_key="none"):
        self.connected, self.phase, self.api_key = False, "starting", api_key
        self.sessions, self.reconnects, self.last_reconnect_utc, self.since = 0, 0, None, time.time()
        self.attempts, self.reloads, self.reload_streak, self.misses = 0, 0, 0, 0
        self.last_click, self.last_reload, self.blank_since, self.last_label = 0.0, 0.0, None, ""

    def set_phase(self, phase):
        changed = phase != self.phase
        if changed:
            self.phase, self.since = phase, time.time()
        return changed

    def public(self):
        return {"connected": self.connected, "phase": self.phase, "reconnects": self.reconnects,
                "last_reconnect_utc": self.last_reconnect_utc, "sessions": self.sessions, "reloads": self.reloads,
                "since_utc": datetime.fromtimestamp(self.since, timezone.utc).isoformat(timespec="seconds"),
                "api_key_file": self.api_key}


# --- PS/2 scancodes and relative mouse from the native monitor -> page input --------------------------------------
# Playwright key *codes* (KeyA, Digit1, Minus...): with Shift held they type A and !, plain "a" would not
SCAN = {0x01: "Escape", 0x0C: "Minus", 0x0D: "Equal", 0x0E: "Backspace", 0x0F: "Tab", 0x1A: "BracketLeft",
        0x1B: "BracketRight", 0x1C: "Enter", 0x1D: "Control", 0x27: "Semicolon", 0x28: "Quote", 0x29: "Backquote",
        0x2A: "Shift", 0x2B: "Backslash", 0x33: "Comma", 0x34: "Period", 0x35: "Slash", 0x36: "ShiftRight",
        0x38: "Alt", 0x39: "Space", 0x3A: "CapsLock", 0x57: "F11", 0x58: "F12"}
SCAN.update({0x02 + i: f"Digit{c}" for i, c in enumerate("1234567890")})
SCAN.update({0x10 + i: f"Key{c}" for i, c in enumerate("QWERTYUIOP")})
SCAN.update({0x1E + i: f"Key{c}" for i, c in enumerate("ASDFGHJKL")})
SCAN.update({0x2C + i: f"Key{c}" for i, c in enumerate("ZXCVBNM")})
SCAN.update({0x3B + i: f"F{i + 1}" for i in range(10)})
EXT_SCAN = {0x1C: "Enter", 0x1D: "ControlRight", 0x35: "Slash", 0x38: "AltRight", 0x47: "Home", 0x48: "ArrowUp",
            0x49: "PageUp", 0x4B: "ArrowLeft", 0x4D: "ArrowRight", 0x4F: "End", 0x50: "ArrowDown", 0x51: "PageDown",
            0x52: "Insert", 0x53: "Delete", 0x5B: "Meta", 0x5C: "MetaRight"}


def decode_scancodes(codes):
    """Set-1 make/break bytes -> [("down"|"up", playwright_key)]; unknown codes and Pause sequences are dropped."""
    out, ext, it = [], False, iter(codes)
    for c in it:
        if c == 0xE0:
            ext = True
            continue
        if c == 0xE1:                                    # Pause/Break: E1 + two bytes
            next(it, None), next(it, None)
            continue
        key = (EXT_SCAN if ext else SCAN).get(c & 0x7F)
        ext = False
        if key:
            out.append(("up" if c & 0x80 else "down", key))
    return out


def plain_key(key):
    """'KeyC' -> 'c' (what clipboard_combo and the key policy compare); other names unchanged."""
    return key[3].lower() if len(key) == 4 and key.startswith("Key") else key


def mod_name(key):
    base = key[:-5] if key.endswith("Right") and key[:-5] in MODS else key
    return base if base in ("Control", "Shift", "Alt", "Meta") else None


def validate_graphical(data):
    """Same JSON as home_pc_runner /pc/graphical-input; ValueError with a message when it is not valid."""
    kind = data.get("type")
    if kind == "vga-keyboard":
        codes = data.get("scancodes")
        if (not isinstance(codes, list) or not 1 <= len(codes) <= 16
                or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 255 for v in codes)):
            raise ValueError("Expected bounded PS/2 scancodes")
        clean = {"type": kind, "scancodes": codes}
    elif kind == "vga-mouse":
        buttons = data.get("buttons")
        if not isinstance(buttons, list) or len(buttons) != 3 or any(not isinstance(v, bool) for v in buttons):
            raise ValueError("Expected three mouse buttons")
        if any(not _num(data.get(k)) or abs(data[k]) > 100 for k in ("dx", "dy", "wheel")):
            raise ValueError("Expected bounded relative mouse movement")
        clean = {k: data[k] for k in ("type", "dx", "dy", "wheel", "buttons")}
    else:
        raise ValueError("Unknown graphical input")
    if "native_receipt" in data:
        clean["native_receipt"] = native_receipt(data["native_receipt"])
    return clean


# --- screencast frames ---------------------------------------------------------------------------------------------
class Throttle:
    """At most `fps` publishes per second. `wait()` is the delay before the next one; `allow()` checks and marks."""

    def __init__(self, fps=MAX_FPS, clock=time.monotonic):
        self.gap, self.clock, self.last = 1.0 / fps, clock, None

    def wait(self):
        return 0.0 if self.last is None else max(0.0, self.last + self.gap - self.clock())

    def mark(self):
        self.last = self.clock()

    def allow(self):
        if self.wait() > 0:
            return False
        self.mark()
        return True


def render_frame(jpeg, size=SMALL):
    """PNG bytes of a screencast JPEG, resized to `size` (fast PNG settings: this runs ten times a second)."""
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    if img.size != tuple(size):
        img = img.resize(size, getattr(Image, "Resampling", Image).BILINEAR)
    out = io.BytesIO()
    img.save(out, "PNG", compress_level=1)
    return out.getvalue()


class FrameFeed:
    """The latest published desktop frame: stable ids (hex + '-', as the web house requires), monotonic revision."""

    def __init__(self, small=SMALL, full=SCREEN, epoch=None):
        self.small, self.full, self.epoch = small, full, epoch or secrets.token_hex(3)
        self.revision, self.frame_id, self.png, self.raw, self._digest, self._full = 0, "", None, None, None, None

    def publish(self, jpeg, png):
        digest = hashlib.blake2b(jpeg, digest_size=8).digest()
        if digest == self._digest and self.png is not None:
            return False                                 # identical picture: same id, no revision bump
        self._digest, self.png, self.raw, self._full = digest, png, jpeg, None
        self.revision += 1
        self.frame_id = f"{self.epoch}-{self.revision:x}"
        return True

    def clear(self):
        self.png = self.raw = self._digest = self._full = None
        self.frame_id = ""

    def display(self):
        return {"kind": "graphical", "available": self.png is not None, "revision": self.revision,
                "frame_id": self.frame_id, "width": self.small[0], "height": self.small[1],
                "full_width": self.full[0], "full_height": self.full[1]}

    def full_png(self):
        """(frame_id, 1920x1080 PNG) of the current frame, or None; cached per frame. Blocking: run in a thread."""
        raw, frame_id = self.raw, self.frame_id
        if raw is None:
            return None
        if self._full is None or self._full[0] != frame_id:
            self._full = (frame_id, render_frame(raw, self.full))
        return self._full


# --- events, token, processes ---------------------------------------------------------------------------------------
class Events:
    """Append-only JSON lines: every action and outcome, block, relaunch and error."""

    def __init__(self, path, limit=20 * 1024 * 1024):
        self.path, self.limit, self.count = Path(path), limit, 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, kind, **fields):
        record = {"t": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "kind": kind, **fields}
        try:
            self.count += 1
            if self.count % 100 == 0 and self.path.exists() and self.path.stat().st_size > self.limit:
                self.path.replace(self.path.with_suffix(".jsonl.1"))
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as error:
            log(f"cannot write events: {error}")


def load_token(token_file):
    if token_file:
        return Path(token_file).read_text().strip()
    return os.environ.get("SUB01_ADMIN_TOKEN", "").strip()


def kill_profile_processes(profile, sig=signal.SIGKILL):
    """Kill the Chromium that uses this profile and everything below it (a hung browser keeps the profile lock;
    stopped children would outlive a killed parent). Returns the pids signalled."""
    needle, table = f"--user-data-dir={profile}".encode(), {}
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.name.isdigit() and int(entry.name) != os.getpid():
            try:
                table[int(entry.name)] = (int((entry / "stat").read_text().rsplit(")", 1)[1].split()[1]),
                                          (entry / "cmdline").read_bytes().split(b"\0"))
            except (OSError, ValueError, IndexError):
                continue
    victims = {pid for pid, (_, argv) in table.items() if needle in argv}
    stack = list(victims)
    while stack:
        parent = stack.pop()
        for pid, (ppid, _) in table.items():
            if ppid == parent and pid not in victims:
                victims.add(pid)
                stack.append(pid)
    for pid in victims:
        try:
            os.kill(pid, sig)
        except OSError:
            pass
    return sorted(victims)


def clean_error(error):
    text = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    return re.sub(r"^[\w.]+: ", "", text)[:200]


# --- the browser ------------------------------------------------------------------------------------------------------
@dataclass
class Config:
    profile: Path
    display: str = ":102"
    width: int = SCREEN[0]
    height: int = SCREEN[1]
    headless: bool = False
    kiosk: bool = True
    allow_private: bool = False          # tests only: lets the page reach loopback servers
    proxy: str = ""
    chromium: str = ""
    start_url: str = "about:blank"
    pc_mode: str = "chromium"            # "chromium" browses itself; "vagon" shows the owner's Vagon Streams page
    vagon_url: str = ""                  # the stream link (never logged beyond scheme and host)
    vagon_api_key_file: str = ""         # optional, recorded as present/absent only; the runner makes no API call


class DesktopUnavailable(RuntimeError):
    """The browser is starting, restarting or unusable right now."""


class ActFailed(RuntimeError):
    """An action could not be carried out (stale mark, covered element, blocked target); the text goes to the agent."""


def chromium_args(cfg):
    args = ["--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
            "--disable-background-networking", "--mute-audio", "--password-store=basic", "--disable-gpu",
            "--disable-dev-shm-usage", "--deny-permission-prompts", "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble", "--disable-infobars", "--noerrdialogs",
            "--disable-features=Translate,AutofillServerCommunication", "--window-position=0,0",
            f"--window-size={cfg.width},{cfg.height}"]
    return args + (["--kiosk"] if cfg.kiosk and not cfg.headless else [])


def chromium_env(display, environ=None):
    """A clean environment for the browser: no operator token, no API keys, only what Chromium needs."""
    environ = os.environ if environ is None else environ
    env = {k: v for k, v in environ.items() if k in SAFE_ENV}
    env["DISPLAY"] = display
    return env


SNAP_JS = r"""(withMarks) => {
  const vw = innerWidth, vh = innerHeight, de = document.documentElement;
  const out = {url: location.href, title: document.title || '', vw, vh, text: '', raw: [],
    scroll: {y: Math.round(scrollY), max: Math.max(0, Math.round(Math.max(de.scrollHeight, document.body ? document.body.scrollHeight : 0) - vh))},
    loading: document.readyState !== 'complete'};
  const shown = r => r.width >= 1 && r.height >= 1 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
  const hide = cs => cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.05;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'TEXTAREA', 'SELECT', 'OPTION']);
  const parts = []; let size = 0, seen = 0;
  const walker = document.createTreeWalker(document.body || de, NodeFilter.SHOW_TEXT), range = document.createRange();
  while (walker.nextNode() && seen < 8000 && size < 4000) {
    seen++;
    const node = walker.currentNode, s = node.nodeValue, p = node.parentElement;
    if (!s || !s.trim() || !p || SKIP.has(p.tagName)) continue;
    range.selectNodeContents(node);
    if (!shown(range.getBoundingClientRect()) || hide(getComputedStyle(p))) continue;
    const t = s.replace(/\s+/g, ' ').trim(); parts.push(t); size += t.length + 1;
  }
  out.text = parts.join(' ');
  if (withMarks) {
    const SEL = 'a[href],button,input,textarea,select,summary,[role=button],[role=link],[role=textbox],[role=searchbox],[role=combobox],[role=checkbox],[role=tab],[role=menuitem],[role=option],[contenteditable=""],[contenteditable=true],[onclick],[tabindex]';
    const NOTYPE = ['checkbox', 'radio', 'submit', 'button', 'image', 'reset', 'range', 'color', 'date', 'datetime-local', 'month', 'time', 'week'];
    const els = [];
    for (const el of document.querySelectorAll(SEL)) {
      if (out.raw.length >= 150) break;
      const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
      if (tag === 'input' && ['hidden', 'password', 'file'].includes(type)) continue;
      if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
      const r = el.getBoundingClientRect();
      if (r.width < 6 || r.height < 6 || !shown(r)) continue;
      if (r.width * r.height > 0.5 * vw * vh && !['a', 'button', 'input', 'textarea', 'select'].includes(tag)) continue;
      const cs = getComputedStyle(el);
      if (hide(cs) || cs.pointerEvents === 'none') continue;
      const cx = Math.min(vw - 1, Math.max(0, r.left + r.width / 2)), cy = Math.min(vh - 1, Math.max(0, r.top + r.height / 2));
      const top = document.elementFromPoint(cx, cy);
      if (!top || !(top === el || el.contains(top) || top.contains(el))) continue;
      const typeable = tag === 'textarea' || el.isContentEditable || (tag === 'input' && !NOTYPE.includes(type));
      let role = el.getAttribute('role') || '';
      if (!role) role = tag === 'a' ? 'link' : tag === 'select' ? 'select' : typeable ? (type === 'search' ? 'searchbox' : 'textbox')
        : (tag === 'input' && (type === 'checkbox' || type === 'radio')) ? type : (tag === 'button' || tag === 'summary' || tag === 'input') ? 'button' : 'clickable';
      const label = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.innerText || el.value || el.title
        || el.getAttribute('alt') || (el.querySelector('img[alt]') || {}).alt || el.getAttribute('name') || '').toString();
      out.raw.push({idx: els.length, role, label: label.slice(0, 120), box: [r.left, r.top, r.width, r.height], href: tag === 'a' ? (el.href || '') : '', typeable});
      els.push(el);
    }
    document.__sub01Els = els;
  }
  return out;
}"""
TAG_JS = r"""({pairs, obs}) => {
  for (const e of document.querySelectorAll('[data-sub01-mark]')) { e.removeAttribute('data-sub01-mark'); e.removeAttribute('data-sub01-obs'); }
  const els = document.__sub01Els || [];
  for (const [idx, id] of pairs) { const e = els[idx]; if (e && e.isConnected) { e.setAttribute('data-sub01-mark', String(id)); e.setAttribute('data-sub01-obs', obs); } }
  return true;
}"""
FOCUS_JS = r"""() => {
  const e = document.activeElement; if (!e || e === document.body || e === document.documentElement) return null;
  const tag = e.tagName.toLowerCase(), type = (e.getAttribute('type') || '').toLowerCase();
  const editable = tag === 'textarea' || e.isContentEditable || (tag === 'input' && !['checkbox', 'radio', 'submit', 'button', 'image', 'reset', 'range', 'color', 'file', 'hidden'].includes(type));
  const value = type === 'password' ? '' : (tag === 'input' || tag === 'textarea') ? e.value : (e.isContentEditable ? e.innerText : '');
  return {tag, type, editable, ac: (e.getAttribute('autocomplete') || '').toLowerCase(), name: ((e.getAttribute('name') || '') + ' ' + (e.id || '')).toLowerCase().slice(0, 80), value: (value || '').slice(-600)};
}"""
POINT_JS = r"""([x, y]) => {
  const e = document.elementFromPoint(x, y); if (!e) return null;
  const c = e.closest('a[href],button,[role=button],[role=link],input,summary') || e;
  return {label: (c.getAttribute('aria-label') || c.innerText || c.value || c.title || '').slice(0, 120), href: c.tagName === 'A' ? (c.href || '') : ''};
}"""
CLIPBOARD_JS = r"""(() => { const deny = () => Promise.reject(new DOMException('Clipboard access is disabled', 'NotAllowedError'));
  try { Object.defineProperty(navigator, 'clipboard', {configurable: true, get: () => ({readText: deny, writeText: deny, read: deny, write: deny})}); } catch (e) {} })();"""
# Vagon: the stream page (or one of its frames) -> its visible text, its buttons and the stream element (video/canvas)
VAGON_PROBE_JS = r"""([minW, minH]) => {
  const vw = innerWidth, vh = innerHeight;
  const out = {url: location.href, title: document.title || '', vw, vh, loading: document.readyState !== 'complete', text: '', buttons: [], stream: null};
  const shown = r => r.width >= 1 && r.height >= 1 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
  const hide = cs => cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.05;
  let best = null, area = 0;
  for (const el of document.querySelectorAll('video, canvas')) {
    const r = el.getBoundingClientRect();
    if (r.width < minW || r.height < minH || !shown(r) || hide(getComputedStyle(el))) continue;
    if (r.width * r.height > area) {
      area = r.width * r.height;
      const video = el.tagName === 'VIDEO';
      best = {tag: el.tagName.toLowerCase(), box: [r.left, r.top, r.width, r.height],
        playing: video ? (el.readyState >= 2 && !el.paused && !el.ended && el.videoWidth > 0) : true};
    }
  }
  out.stream = best;
  const parts = [];
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  let seen = 0, size = 0;
  while (walker.nextNode() && seen < 2000 && size < 1200) {
    seen++;
    const node = walker.currentNode, s = node.nodeValue, p = node.parentElement;
    if (!s || !s.trim() || !p || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(p.tagName)) continue;
    const r = p.getBoundingClientRect();
    if (!shown(r) || hide(getComputedStyle(p))) continue;
    const t = s.replace(/\s+/g, ' ').trim(); parts.push(t); size += t.length + 1;
  }
  out.text = parts.join(' ').slice(0, 1200);
  const SEL = 'button, [role=button], a[href], input[type=button], input[type=submit], [onclick], [class*="play" i], [class*="connect" i], [class*="start" i], [class*="reconnect" i]';
  for (const el of document.querySelectorAll(SEL)) {
    if (out.buttons.length >= 30) break;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 12 || r.height < 12 || r.width * r.height > 0.6 * vw * vh || !shown(r)) continue;
    const cs = getComputedStyle(el);
    if (hide(cs) || cs.pointerEvents === 'none') continue;
    const cx = Math.min(vw - 1, Math.max(0, r.left + r.width / 2)), cy = Math.min(vh - 1, Math.max(0, r.top + r.height / 2));
    const top = document.elementFromPoint(cx, cy);
    if (!top || !(top === el || el.contains(top) || top.contains(el))) continue;
    let label = (el.getAttribute('aria-label') || el.innerText || el.value || el.title || el.getAttribute('alt') || '').toString().trim();
    if (!label) { const m = /(reconnect|connect|play|start)/i.exec(el.className || ''); label = m ? m[1] : ''; }
    out.buttons.push({label: label.replace(/\s+/g, ' ').slice(0, 80), box: [r.left, r.top, r.width, r.height]});
  }
  return out;
}"""
VAGON_FOCUS_JS = r"""([minW, minH]) => {
  let best = null, area = 0;
  for (const el of document.querySelectorAll('video, canvas')) {
    const r = el.getBoundingClientRect();
    if (r.width >= minW && r.height >= minH && r.width * r.height > area) { area = r.width * r.height; best = el; }
  }
  const el = best || document.body;
  if (!el) return false;
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
  try { el.focus({preventScroll: true}); } catch (e) { return false; }
  return document.activeElement === el;
}"""


class Resolver:
    """DNS check for the network guard: a host is public only if every address it resolves to is global."""

    def __init__(self):
        self.cache = {}

    async def public(self, host):
        h, now = (host or "").strip("[]").lower(), time.time()
        hit = self.cache.get(h)
        if hit and hit[1] > now:
            return hit[0]
        try:
            ok = ipaddress.ip_address(h).is_global
        except ValueError:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(h, None, type=socket.SOCK_STREAM)
                ok = bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)
            except (OSError, ValueError):
                ok = False
        if len(self.cache) > 5000:
            self.cache.clear()
        self.cache[h] = (ok, now + 300)
        return ok


class Desktop:
    """The Playwright side: one persistent headed Chromium with a supervisor that relaunches it when it crashes or hangs."""

    RELAUNCH_DELAY = 1.0                                 # seconds before the first relaunch; doubles up to 30
    GUARD_S = 20.0                                       # a page read or screenshot slower than this means a hung browser
    LAUNCH_S = 90.0                                      # a launch that takes longer than this is retried

    def __init__(self, cfg, events):
        self.cfg, self.events = cfg, events
        self.status, self.error, self.restarts = "starting", "", 0
        self.on_change = lambda: None
        self.feed, self.throttle, self.resolver = FrameFeed((SMALL[0], SMALL[1]), (cfg.width, cfg.height)), Throttle(), Resolver()
        self.pw = self.ctx = self.page = self.cdp = None
        self.dialogs, self.act_dialog = deque(maxlen=10), None
        self.blocked_nav, self.popups, self.refused, self.blocked_count = [], [], [], 0
        self.view = (cfg.width, cfg.height)               # the page's real viewport (kiosk gives 1919x1079 on a 1920x1080 screen)
        self.held, self.dropped, self.buttons, self.cursor = set(), set(), [False] * 3, [cfg.width // 2, cfg.height // 2]
        self.stopping, self._tearing, self._why, self._latest = False, False, None, None
        self._wake = self._frame_event = self._input_lock = self._task = self._publisher_task = None
        self.vagon = VagonState(api_key_file_status(cfg.vagon_api_key_file))   # /pc/state "vagon" (vagon mode only)
        self._vagon_task, self._vagon_frame, self._vagon_offset = None, None, (0.0, 0.0)
        self._vagon_lock = asyncio.Lock()                 # the connect loop never presses a button during an action

    @property
    def vagon_mode(self):
        return self.cfg.pc_mode == "vagon"

    # lifecycle
    def start(self):
        self._wake, self._frame_event, self._input_lock = asyncio.Event(), asyncio.Event(), asyncio.Lock()
        self._task = asyncio.create_task(self._supervise())
        self._publisher_task = asyncio.create_task(self._publisher())
        if self.vagon_mode:
            self._vagon_task = asyncio.create_task(self._vagon_loop())

    async def close(self):
        self.stopping = True
        if self._wake:
            self._wake.set()
        for task in (self._task, self._publisher_task, self._vagon_task):
            if task:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        await self._teardown()

    def _set_status(self, status):
        if status != self.status:
            self.status = status
            self.on_change()

    def _request_restart(self, why):
        if self._why is None and not self._tearing and not self.stopping:
            self._why = why
            log(f"browser needs a relaunch: {why}")
            if self._wake:
                self._wake.set()

    async def _supervise(self):
        delay = self.RELAUNCH_DELAY
        while not self.stopping:
            try:
                await asyncio.wait_for(self._launch(), self.LAUNCH_S)
                delay = self.RELAUNCH_DELAY
                self.error = ""
                self._set_status("ready")
                log(f"browser ready on {self.cfg.display} ({self.cfg.width}x{self.cfg.height}, restarts {self.restarts})")
                self.events.append("browser", state="ready", restarts=self.restarts)
                await self._watch()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._why = self._why or f"launch failed: {clean_error(error)}"
                self.error = clean_error(error)
                log(f"error: {self.error}")
                self.events.append("error", where="browser", message=self.error)
            if self.stopping:
                break
            self._set_status("restarting")
            await self._teardown()
            self.restarts += 1
            log(f"relaunch #{self.restarts} in {delay:.0f}s ({self._why})")
            self.events.append("relaunch", number=self.restarts, why=self._why, delay=delay)
            await asyncio.sleep(delay)
            delay = min(30.0, delay * 2)

    async def _watch(self):
        misses = 0
        while not self.stopping and self._why is None:
            try:
                await asyncio.wait_for(self._wake.wait(), 5)
            except asyncio.TimeoutError:
                pass
            if self._why or self.stopping:
                break
            try:
                await asyncio.wait_for(self.page.evaluate("1"), 8)
                misses = 0
            except Exception as error:
                misses += 1
                if misses >= 2:
                    self._why = f"browser hang ({clean_error(error)})"

    async def _launch(self):
        from playwright.async_api import async_playwright  # lazy: the pure helpers and the tests never need it
        cfg = self.cfg
        cfg.profile.mkdir(parents=True, exist_ok=True)
        kill_profile_processes(cfg.profile)
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            try:
                (cfg.profile / name).unlink()
            except OSError:
                pass
        self._why, self._tearing = None, False
        self._wake.clear()
        self.feed.clear()
        self.pw = await async_playwright().start()
        # Headed: the real window is the viewport (an emulated viewport would undo --kiosk). Headless: emulate the size.
        options = {"headless": cfg.headless, "args": chromium_args(cfg), "env": chromium_env(cfg.display),
                   "accept_downloads": False, "service_workers": "block", "locale": "en-US", "permissions": [],
                   "ignore_default_args": ["--enable-automation"]}
        options.update({"viewport": {"width": cfg.width, "height": cfg.height}} if cfg.headless else {"no_viewport": True})
        if cfg.chromium:
            options["executable_path"] = cfg.chromium
        if cfg.proxy:
            options["proxy"] = {"server": cfg.proxy}
        self.ctx = await self.pw.chromium.launch_persistent_context(str(cfg.profile), **options)
        await self.ctx.add_init_script(CLIPBOARD_JS)
        await self.ctx.route("**/*", self._route)
        self.page = self.ctx.pages[0] if self.ctx.pages else await self.ctx.new_page()
        for extra in self.ctx.pages[1:]:
            await extra.close()
        self.ctx.on("page", self._on_new_page)
        self.ctx.on("response", self._on_response)
        self.ctx.on("close", lambda *_: self._request_restart("browser closed"))
        page = self.page
        page.on("dialog", self._on_dialog)
        page.on("framenavigated", self._on_navigated)
        page.on("crash", lambda *_: self._request_restart("page crashed"))
        page.on("close", lambda *_: self._request_restart("page closed") if page is self.page else None)
        page.on("download", lambda d: self._refused("download", d.url))
        page.on("filechooser", lambda fc: self._refused("file chooser", ""))
        self.cdp = await self.ctx.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 80, "maxWidth": cfg.width,
                                                     "maxHeight": cfg.height, "everyNthFrame": 1})
        try:
            self.view = tuple(await page.evaluate("[innerWidth, innerHeight]"))
        except Exception:
            self.view = (cfg.width, cfg.height)
        self.cursor = [self.view[0] // 2, self.view[1] // 2]
        if abs(self.view[0] - cfg.width) > 8 or abs(self.view[1] - cfg.height) > 8:
            log(f"warning: the page viewport is {self.view[0]}x{self.view[1]}, not {cfg.width}x{cfg.height} "
                f"(no kiosk? check the X display size): the stream shows the page only, scaled")
        if self.vagon_mode:
            await self._vagon_goto("launch")
        elif cfg.start_url and cfg.start_url != "about:blank" and not blocked_url(cfg.start_url, cfg.allow_private):
            try:
                await page.goto(cfg.start_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            except Exception as error:
                log(f"start page not loaded: {clean_error(error)}")

    async def _teardown(self):
        self._tearing = True
        self.feed.clear()
        if self.vagon_mode:
            self.vagon.connected, self._vagon_frame = False, None
            self.vagon.set_phase("restarting")
        self.on_change()
        for step in (self.ctx and self.ctx.close(), self.pw and self.pw.stop()):
            if step is not None:
                try:
                    await asyncio.wait_for(step, 6)
                except (Exception, asyncio.CancelledError):
                    pass
        self.ctx = self.page = self.cdp = self.pw = None
        kill_profile_processes(self.cfg.profile)
        self.held.clear()
        self.buttons = [False] * 3

    # Vagon Streams: open the stream page, press its connect button, notice "session ended", re-enter
    def _scrub(self, text):
        """An error text that may quote the stream link (Playwright puts the URL in its messages) -> safe to log."""
        text, url = str(text), self.cfg.vagon_url
        if url:
            text = text.replace(url, redact_url(url))
            query = urlsplit(url).query
            if query:
                text = text.replace(query, "…")
        return text[:200]

    def _url_for_log(self, url):
        return redact_url(url) if self.vagon_mode else str(url)[:200]

    async def _vagon_goto(self, why):
        """Open the stream page (at launch, and again after an ended session that offers no way back in)."""
        v = self.vagon
        v.connected, v.attempts, v.misses, v.blank_since = False, 0, 0, None
        v.last_reload, self._vagon_frame, self._vagon_offset = time.monotonic(), None, (0.0, 0.0)
        v.set_phase("starting")
        self.on_change()
        log(f"vagon: opening the stream page ({why}) at {redact_url(self.cfg.vagon_url)}")
        self.events.append("vagon", state="open", why=why, host=redact_url(self.cfg.vagon_url))
        try:
            await self.page.goto(self.cfg.vagon_url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception as error:
            message = self._scrub(clean_error(error))
            log(f"vagon: stream page not loaded: {message}")
            self.events.append("error", where="vagon", message=message)

    async def _vagon_loop(self):
        while not self.stopping:
            await asyncio.sleep(VAGON_TICK_S)
            if self.status != "ready" or self.page is None or self._tearing:
                continue
            try:
                await self._vagon_step()
            except asyncio.CancelledError:
                raise
            except DesktopUnavailable as error:           # the supervisor is relaunching the browser
                log(f"vagon: probe skipped: {self._scrub(error)}")
            except Exception as error:
                log(f"vagon: probe failed: {self._scrub(clean_error(error))}")

    async def _vagon_probe(self):
        """The stream page now: visible text, buttons and the stream element, from the main frame or the frame that
        holds the stream (the dashboard's iframe embed). Boxes are in page pixels; `self.view` is the page viewport."""
        page = self.page
        frames = [page.main_frame] + [f for f in page.frames if f is not page.main_frame][:5]
        best = None
        for frame in frames:
            try:
                info = await self._guarded(frame.evaluate(VAGON_PROBE_JS, list(VAGON_MIN_STREAM)), "stream probe")
            except DesktopUnavailable:
                raise
            except Exception:
                continue                                  # a frame that navigated away or detached meanwhile
            offset = (0.0, 0.0)
            if frame is page.main_frame:
                self.view = (int(info["vw"]), int(info["vh"]))
            else:
                try:
                    box = await (await frame.frame_element()).bounding_box()
                except Exception:
                    box = None
                if not box:
                    continue
                offset = (float(box["x"]), float(box["y"]))
            if best is None:
                best = (info, frame, offset)
            if info.get("stream") or choose_vagon_button(info.get("buttons")) is not None:
                best = (info, frame, offset)
                break
        if best is None:
            raise DesktopUnavailable("the stream page cannot be read")
        info, frame, offset = best
        if offset != (0.0, 0.0):
            for b in info.get("buttons") or []:
                b["box"][0], b["box"][1] = b["box"][0] + offset[0], b["box"][1] + offset[1]
            if info.get("stream"):
                info["stream"]["box"][0] += offset[0]
                info["stream"]["box"][1] += offset[1]
        self._vagon_frame, self._vagon_offset = frame, offset
        return info

    async def _vagon_focus(self):
        """Keyboard focus on the stream element (or the body), so key events reach the stream client."""
        frame = self._vagon_frame or getattr(self.page, "main_frame", self.page)
        try:
            return bool(await asyncio.wait_for(frame.evaluate(VAGON_FOCUS_JS, list(VAGON_MIN_STREAM)), 5))
        except Exception:
            return False

    async def _vagon_press(self, button):
        v, x, y = self.vagon, button["box"][0] + button["box"][2] / 2, button["box"][1] + button["box"][3] / 2
        label = str(button.get("label") or "")[:40]
        v.last_click, v.attempts, v.last_label = time.monotonic(), v.attempts + 1, label
        log(f"vagon: pressing '{label}' (attempt {v.attempts})")
        self.events.append("vagon", state="press", label=label, attempt=v.attempts)
        await self.page.mouse.move(x, y, steps=4)
        await self.page.mouse.click(x, y)

    async def _vagon_step(self):
        async with self._vagon_lock:
            await self._vagon_step_locked()

    async def _vagon_step_locked(self):
        v, now = self.vagon, time.monotonic()
        probe = await self._vagon_probe()
        phase, idx = classify_vagon(probe)
        if phase == "ready":
            v.misses, v.blank_since, v.reload_streak = 0, None, 0
            if not v.connected:
                v.connected, v.sessions, v.attempts = True, v.sessions + 1, 0
                if v.sessions > 1:
                    v.reconnects += 1
                    v.last_reconnect_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                log(f"vagon: remote desktop connected (session {v.sessions}, reconnects {v.reconnects})")
                self.events.append("vagon", state="connected", session=v.sessions, reconnects=v.reconnects)
            if v.set_phase("ready"):
                self.on_change()
            return
        if v.connected:
            v.misses += 1
            if v.misses < VAGON_MISSES and phase in ("busy", "blank"):
                return                                    # a stalled video or a dropped frame: not an ended session yet
            v.connected = False
            log(f"vagon: remote session {phase}: {probe.get('text', '')[:80]!r}")
            self.events.append("vagon", state="disconnected", phase=phase, text=str(probe.get("text") or "")[:120])
        if v.set_phase(phase):
            self.on_change()
        if idx is not None and v.attempts < 6:
            if now - v.last_click >= VAGON_CLICK_GAP_S:
                await self._vagon_press(probe["buttons"][idx])
            return
        if phase == "blank":
            v.blank_since = v.blank_since or now
        reload_due = (phase == "ended" or v.attempts >= 6
                      or (phase == "blank" and now - v.blank_since >= VAGON_BLANK_RELOAD_S))
        if reload_due and now - v.last_reload >= VAGON_RELOAD_BACKOFF[min(v.reload_streak, len(VAGON_RELOAD_BACKOFF) - 1)]:
            v.reloads, v.reload_streak = v.reloads + 1, v.reload_streak + 1
            await self._vagon_goto(f"{phase}, attempts {v.attempts}")

    async def _vagon_snapshot(self, obs):
        probe = await self._vagon_probe()
        try:
            jpeg = await self._guarded(self.page.screenshot(type="jpeg", quality=80), "screenshot")
        except DesktopUnavailable:
            raise
        except Exception as error:
            raise DesktopUnavailable(f"screenshot failed: {self._scrub(clean_error(error))}")
        phase, _ = classify_vagon(probe)
        return {"url": redact_url(probe.get("url")) or redact_url(self.cfg.vagon_url),
                "title": " ".join(str(probe.get("title") or "").split())[:160] or "remote desktop", "text": "",
                "scroll": {"y": 0, "max": 0}, "loading": bool(probe.get("loading")), "width": self.view[0],
                "height": self.view[1], "jpeg": jpeg, "marks": [], "dialogs": self.pop_dialogs() if obs else [],
                "mode": "vagon", "remote_ready": phase == "ready"}

    async def _do_vagon(self, a, errors):
        """The agent primitives on the stream: clicks and wheel at page points over the stream element, keys to
        the focused stream, navigate/search as Ctrl+L + URL + Enter in the remote browser, back as Alt+Left."""
        page, kind = self.page, a["action"]
        if kind == "wait":
            await asyncio.sleep(a["seconds"])
            return
        async with self._vagon_lock:
            probe = await self._vagon_probe()
            phase, _ = classify_vagon(probe)
            if phase != "ready":
                errors.append(f"the remote desktop is not connected (stream {phase}); wait and observe again")
                return
            if "mark" in a:
                raise ActFailed("there are no marks on the remote desktop; click by point")
            await self._vagon_input(a, probe["stream"]["box"])

    async def _vagon_input(self, a, box):
        page, kind, settle = self.page, a["action"], VAGON_SETTLE_S
        if kind == "click":
            x, y = image_point(a["point"], self.view)
            await page.mouse.move(x, y, steps=6)
            await page.mouse.click(x, y)
            self.cursor = [x, y]
        elif kind == "scroll":
            await page.mouse.move(box[0] + box[2] / 2, box[1] + box[3] / 2)
            sign, step = (1 if a["direction"] == "down" else -1), a["amount"] / 6
            for _ in range(6):
                await page.mouse.wheel(0, sign * step)
                await asyncio.sleep(0.05)
        elif kind == "type":
            await self._vagon_focus()
            await page.keyboard.type(a["text"], delay=VAGON_TYPE_DELAY_MS)
            if a.get("submit"):
                await page.keyboard.press("Enter")
        elif kind == "key":
            await self._vagon_focus()
            await page.keyboard.press(a["key"])
        elif kind in ("navigate", "search"):
            url = a["url"] if kind == "navigate" else SEARCH_URL + quote_plus(a["query"])
            await self._vagon_focus()
            await page.keyboard.press("Control+l")        # the remote browser's address bar (Chrome, Edge, Firefox)
            await asyncio.sleep(0.3)
            await page.keyboard.type(url, delay=8)
            await asyncio.sleep(0.1)
            await page.keyboard.press("Enter")
            settle = VAGON_NAV_SETTLE_S
        elif kind == "back":
            await self._vagon_focus()
            await page.keyboard.press("Alt+ArrowLeft")
            settle = VAGON_NAV_SETTLE_S
        await asyncio.sleep(settle)

    # events from the page
    def _refused(self, what, url):
        self.refused.append(what)
        log(f"{what} refused")
        self.events.append("blocked", what=what, url=self._url_for_log(url))

    async def _on_dialog(self, dialog):
        record = {"type": dialog.type, "message": (dialog.message or "")[:200], "action": "dismissed",
                  "t": round(time.time(), 1)}
        try:
            if dialog.type == "beforeunload":            # leaving the page is what was asked; staying would hang navigation
                await dialog.accept()
                record["action"] = "accepted (leave page)"
            else:
                await dialog.dismiss()
        except Exception:
            record["action"] = "failed"
        self.dialogs.append(record)
        self.act_dialog = record
        log(f"dialog {record['type']} {record['action']}")
        self.events.append("dialog", **record)

    # Playwright's route sees only the first request of a redirect chain, so redirects are checked here: a 3xx
    # whose target is refused stops the load before the target answers; the committed URL is checked again.
    def _on_response(self, response):
        try:
            request = response.request
            if (300 <= response.status < 400 and request.is_navigation_request() and request.frame.parent_frame is None
                    and request.frame.page is self.page):
                target = urljoin(response.url, response.headers.get("location", ""))
                why = request_blocked(target, True, "GET", self.cfg.allow_private) if target != response.url else None
                if why:
                    self._kill_navigation(why, target)
        except Exception:
            pass

    def _on_navigated(self, frame):
        try:
            if frame.parent_frame is None and frame.page is self.page and frame.url not in ("about:blank", ""):
                why = None if frame.url.startswith("chrome-error:") else blocked_url(frame.url, self.cfg.allow_private)
                if why:
                    self._kill_navigation(why, frame.url)
        except Exception:
            pass

    def _kill_navigation(self, why, url):
        host = urlsplit(url).hostname or ""
        self.blocked_count += 1
        self.blocked_nav.append((why, host))
        log(f"blocked redirect/navigation to {host} ({why})")
        self.events.append("blocked", what="redirect", reason=why, url=self._url_for_log(url))
        asyncio.ensure_future(self._blank())

    async def _blank(self):
        try:
            await self.cdp.send("Page.stopLoading")
            await self.page.goto("about:blank", wait_until="commit", timeout=5000)
        except Exception:
            pass

    def _on_new_page(self, page):
        if page is self.page:
            return
        self.popups.append(page.url or "")
        log("popup closed")
        self.events.append("blocked", what="popup", url=self._url_for_log(page.url or ""))
        asyncio.ensure_future(self._close_quietly(page))

    @staticmethod
    async def _close_quietly(page):
        try:
            await page.close()
        except Exception:
            pass

    async def _route(self, route):
        try:
            req = route.request
            try:
                main = req.is_navigation_request() and req.frame.parent_frame is None
            except Exception:
                main = False
            why = request_blocked(req.url, main, req.method, self.cfg.allow_private)
            if why is None and not self.cfg.allow_private and not self.cfg.proxy and not req.url.startswith(("data:", "blob:", "about:")):
                if not await self.resolver.public(urlsplit(req.url).hostname or ""):
                    why = "unresolved-or-private"
            if why:
                self.blocked_count += 1
                if main:
                    self.blocked_nav.append((why, urlsplit(req.url).hostname or ""))
                    log(f"blocked navigation to {urlsplit(req.url).hostname} ({why})")
                    self.events.append("blocked", what="navigation", reason=why, url=self._url_for_log(req.url))
                return await route.abort("blockedbyclient")
            await route.continue_()
        except Exception:
            pass                                          # route already handled or the page is gone

    # screencast: acknowledge at once, publish at most MAX_FPS, newest frame wins
    def _on_frame(self, params):
        asyncio.ensure_future(self._ack(params.get("sessionId")))
        self._latest = params.get("data")
        self._frame_event.set()

    async def _ack(self, session_id):
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:
            pass

    async def _publisher(self):
        while True:
            await self._frame_event.wait()
            self._frame_event.clear()
            delay = self.throttle.wait()
            if delay > 0:
                await asyncio.sleep(delay)
            data, self._latest = self._latest, None
            if not data or self._tearing:
                continue
            self.throttle.mark()                          # the gap counts from the start of the render: 10 fps, not 1/(0.1+render)
            try:
                jpeg = base64.b64decode(data)
                png = await asyncio.to_thread(render_frame, jpeg, SMALL)
            except Exception as error:
                log(f"frame skipped: {clean_error(error)}")
                continue
            if self.feed.publish(jpeg, png):
                self.on_change()

    # reads
    def display(self):
        d = self.feed.display()
        d["available"] = d["available"] and self.status == "ready"
        return d

    async def frame(self, full=False):
        if self.status != "ready" or self.feed.png is None:
            return None
        if full:
            return await asyncio.to_thread(self.feed.full_png)
        return self.feed.frame_id, self.feed.png

    def _ready(self):
        if self.status != "ready" or self.page is None:
            raise DesktopUnavailable(self.status)

    def pop_dialogs(self):
        out = list(self.dialogs)
        self.dialogs.clear()
        return out

    async def _guarded(self, coro, what):
        try:
            return await asyncio.wait_for(coro, self.GUARD_S)
        except asyncio.TimeoutError:
            self._request_restart(f"{what} timed out")
            raise DesktopUnavailable(f"{what} timed out")

    async def snapshot(self, obs=None):
        """Raw observation of the page now. With `obs` the clickable elements are numbered and tagged in the DOM.
        Vagon mode: the pixels of the stream page, `mode` and `remote_ready`, no text and no marks."""
        self._ready()
        if self.vagon_mode:
            return await self._vagon_snapshot(obs)
        info = None
        for attempt in (1, 2):
            try:
                info = await self._guarded(self.page.evaluate(SNAP_JS, bool(obs)), "page read")
                break
            except DesktopUnavailable:
                raise
            except Exception as error:                    # navigation destroyed the context: once more
                if attempt == 2:
                    raise DesktopUnavailable(f"page read failed: {clean_error(error)}")
                await asyncio.sleep(0.4)
        try:
            jpeg = await self._guarded(self.page.screenshot(type="jpeg", quality=80), "screenshot")
        except DesktopUnavailable:
            raise
        except Exception as error:
            raise DesktopUnavailable(f"screenshot failed: {clean_error(error)}")
        marks = build_marks(info.get("raw"), info["vw"], info["vh"]) if obs else []
        if marks:
            try:
                await self._guarded(self.page.evaluate(TAG_JS, {"pairs": [[m["idx"], m["id"]] for m in marks], "obs": obs}), "tagging")
            except DesktopUnavailable:
                raise
            except Exception:
                marks = []
        self.view = (info["vw"], info["vh"])
        return {"url": info["url"], "title": info["title"], "text": info["text"], "scroll": info["scroll"],
                "loading": info["loading"], "width": info["vw"], "height": info["vh"], "jpeg": jpeg, "marks": marks,
                "dialogs": self.pop_dialogs() if obs else []}

    async def focus_info(self):
        try:
            return await asyncio.wait_for(self.page.evaluate(FOCUS_JS), 5)
        except Exception:
            return None

    # agent actions
    async def do(self, action):
        """Perform one validated, policy-checked action; wait for load / network idle (cap 10 s). Never raises:
        problems come back in `errors`. Returns {errors, dialog, load_ms}."""
        self._ready()
        t0, errors = time.monotonic(), []
        self.blocked_nav, self.popups, self.refused, self.act_dialog = [], [], [], None
        try:
            await asyncio.wait_for(self._do(action, errors), ACT_TIMEOUT_S)
        except asyncio.TimeoutError:
            errors.append(f"action timed out after {ACT_TIMEOUT_S:.0f}s; the browser is being relaunched")
            self._request_restart("action timed out")
        except ActFailed as error:
            errors.append(str(error))
            if str(error).startswith("blocked"):
                self.events.append("blocked", what="click", reason=str(error))
        except DesktopUnavailable as error:
            errors.append(f"browser unavailable: {error}")
        except Exception as error:
            errors.append(clean_error(error))
        for why, host in dict.fromkeys(self.blocked_nav):
            errors.append(f"blocked navigation to {host or 'unknown host'} ({why})")
        if self.popups:
            errors.append("a popup was opened and closed by policy; navigate to its link instead")
        for what in dict.fromkeys(self.refused):
            errors.append(f"a {what} was refused by policy")
        return {"errors": errors, "dialog": self.act_dialog, "load_ms": int((time.monotonic() - t0) * 1000)}

    async def _do(self, a, errors):
        page, kind = self.page, a["action"]
        if self.vagon_mode:
            return await self._do_vagon(a, errors)
        if kind in ("navigate", "search"):
            url = a["url"] if kind == "navigate" else SEARCH_URL + quote_plus(a["query"])
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                if response is not None and response.status >= 400:
                    errors.append(f"the page answered HTTP {response.status}")
            except Exception as error:
                if not self.blocked_nav:
                    errors.append("navigation failed: " + clean_error(error))
        elif kind == "back":
            if await page.go_back(wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS) is None:
                errors.append("there is no earlier page to go back to")
        elif kind == "wait":
            await asyncio.sleep(a["seconds"])
        elif kind == "scroll":
            await page.mouse.move(self.view[0] / 2, self.view[1] / 2)
            sign, step = (1 if a["direction"] == "down" else -1), a["amount"] / 6
            for _ in range(6):
                await page.mouse.wheel(0, sign * step)
                await asyncio.sleep(0.05)
        elif kind == "key":
            await page.keyboard.press(a["key"])
        elif kind in ("click", "type"):
            if "mark" in a or "point" in a:
                x, y = await self._target(a)
                await page.mouse.move(x, y, steps=6)
                await page.mouse.click(x, y)
                await asyncio.sleep(0.2)
            if kind == "type":
                await self._type(a, errors)
        if not errors:
            await self._settle()
            if kind in ("navigate", "search", "back", "click") and not self.blocked_nav:
                await self._dismiss_banners()

    async def _target(self, a):
        """Page pixel to click: the tagged element of the last observation (re-measured now) or the given image point."""
        page = self.page
        if "mark" in a:
            el = await page.query_selector(f'[data-sub01-mark="{int(a["mark"])}"][data-sub01-obs="{a["obs"]}"]')
            if el is None:
                raise ActFailed(f"mark {a['mark']} is no longer on the page; observe again")
            await el.scroll_into_view_if_needed(timeout=2000)
            box = await el.bounding_box()
            if not box or box["width"] < 1 or box["height"] < 1:
                raise ActFailed(f"mark {a['mark']} is not visible; observe again")
            x = min(self.view[0] - 1, max(0, box["x"] + box["width"] / 2))
            y = min(self.view[1] - 1, max(0, box["y"] + box["height"] / 2))
            if not await el.evaluate("(e, p) => { const t = document.elementFromPoint(p[0], p[1]); return !!t && (t === e || e.contains(t) || t.contains(e)); }", [x, y]):
                raise ActFailed(f"mark {a['mark']} is covered by another element; observe again")
            return x, y
        x, y = a["point"][0] * self.view[0] / SMALL[0], a["point"][1] * self.view[1] / SMALL[1]
        info = await page.evaluate(POINT_JS, [x, y])
        why = mark_blocked(info or {}, self.cfg.allow_private)
        if why:
            raise ActFailed(f"blocked: {why}")
        return x, y

    async def _type(self, a, errors):
        page = self.page
        info = await self.focus_info()
        if not info or not info.get("editable"):
            errors.append("no editable element is focused; click a text field first (or pass its mark)")
            return
        why = field_blocked(info)
        if why:
            raise ActFailed(f"blocked: typing into a {why}")
        text = a["text"]
        await page.keyboard.type(text, delay=max(4, min(60, 6000 // max(1, len(text)))))
        tail = text[-20:]
        after = await self.focus_info()
        if not after or tail not in str(after.get("value") or ""):
            errors.append("the typed text was not found in the focused field")
        elif a.get("submit"):
            await page.keyboard.press("Enter")

    async def _settle(self):
        t0 = time.monotonic()
        try:
            await self.page.wait_for_load_state("load", timeout=IDLE_CAP_S * 1000)
            left = IDLE_CAP_S - (time.monotonic() - t0)
            if left > 0.3:
                await self.page.wait_for_load_state("networkidle", timeout=left * 1000)
        except Exception:
            pass                                          # long-polling pages never go idle: observe what is there
        await asyncio.sleep(0.3)

    async def _dismiss_banners(self):
        """Cookie banners and modals: the reject / close button, never accept (browse.choose_dismiss)."""
        if not B:
            return
        try:
            buttons = await asyncio.wait_for(self.page.evaluate(B.BUTTONS_JS), 3)
            i = B.choose_dismiss(buttons)
            if i is not None:
                await self.page.locator(f'[data-sub01-btn="{int(i)}"]').first.click(timeout=2000)
                self.events.append("banner", index=i, label=str(next((b.get("label") for b in buttons if b["i"] == i), ""))[:60])
                await asyncio.sleep(0.4)
        except Exception:
            pass

    # input forwarded from the native monitor and /pc/input
    async def forward(self, clean):
        """PS/2 scancodes or relative mouse -> real key / mouse events in the page. False when not delivered."""
        if self.status != "ready" or self.page is None:
            return False
        try:
            async with self._input_lock:
                if clean["type"] == "vga-keyboard":
                    return await self._keys(decode_scancodes(clean["scancodes"]))
                return await self._mouse(clean)
        except Exception as error:
            log(f"input not delivered: {clean_error(error)}")
            return False

    async def _keys(self, events):
        if self.vagon_mode:                               # no DOM fields to protect: the keys go to the stream
            await self._vagon_focus()
        else:
            info = await self.focus_info()
            why = field_blocked(info)
            if why:
                self.events.append("blocked", what="keyboard", reason=why)
                return False
        for op, key in events:
            if op == "down":
                held_mods = {mod_name(k) for k in self.held} - {None}
                if not mod_name(key) and clipboard_combo(held_mods, plain_key(key)):
                    self.dropped.add(key)                # its release is dropped too
                    self.events.append("blocked", what="keyboard", reason="clipboard")
                    continue
                await self.page.keyboard.down(key)
                self.held.add(key)
            elif key in self.dropped:
                self.dropped.discard(key)
            else:
                await self.page.keyboard.up(key)
                self.held.discard(key)
        return True

    async def _mouse(self, c):
        w, h = self.view
        self.cursor[0] = min(w - 1, max(0, self.cursor[0] + c["dx"] * MOUSE_GAIN))
        self.cursor[1] = min(h - 1, max(0, self.cursor[1] + c["dy"] * MOUSE_GAIN))
        if c["dx"] or c["dy"]:
            await self.page.mouse.move(self.cursor[0], self.cursor[1])
        for i, name in enumerate(("left", "middle", "right")):
            if c["buttons"][i] != self.buttons[i]:
                await (self.page.mouse.down if c["buttons"][i] else self.page.mouse.up)(button=name)
                self.buttons[i] = c["buttons"][i]
        if c["wheel"]:
            await self.page.mouse.wheel(0, c["wheel"] * 40)
        return True

    async def type_text(self, text):
        """/pc/input: text into the focused field ("\\n" presses Enter); False when nothing safe is focused."""
        if self.status != "ready" or self.page is None:
            return False
        if self.vagon_mode:
            if not self.vagon.connected:
                return False
            await self._vagon_focus()
        else:
            info = await self.focus_info()
            if not info or not info.get("editable") or field_blocked(info):
                return False
        for i, part in enumerate(text.split("\n")):
            if i:
                await self.page.keyboard.press("Enter")
            part = "".join(c for c in part if c >= " " and c != "\x7f")
            if part and self.vagon_mode:
                await self.page.keyboard.type(part, delay=VAGON_TYPE_DELAY_MS)   # real key events for the stream
            elif part:
                await self.page.keyboard.insert_text(part)
        return True

    async def release_inputs(self):
        keys, buttons = list(self.held), [i for i, b in enumerate(self.buttons) if b]
        self.held.clear()
        self.dropped.clear()
        self.buttons = [False] * 3
        if self.status != "ready" or self.page is None:
            return
        for key in keys:
            try:
                await self.page.keyboard.up(key)
            except Exception:
                pass
        for i in buttons:
            try:
                await self.page.mouse.up(button=("left", "middle", "right")[i])
            except Exception:
                pass


# --- the runner: auth, privacy, session, agent API ---------------------------------------------------------------
class Runner:
    def __init__(self, desk, token, events, clock=time.monotonic, allow_private=False):
        if not isinstance(token, str) or len(token) < MIN_TOKEN:
            raise ValueError("An operator credential of at least 12 characters is required")
        self.desk, self.events, self.clock, self.allow_private = desk, events, clock, allow_private
        self._token = token.encode()
        self.privacy, self.privacy_epoch = False, 0
        self.privacy_sources = {"native": False, "home": False}
        self.session_sources = {"native": 0.0, "home": 0.0}
        self.home_devices = None
        self.changed = asyncio.Event()
        self.lock = asyncio.Lock()
        self.epoch, self.obs_count, self.commands, self.last_command = secrets.token_hex(3), 0, 0, None
        self.last_obs = {"frame_id": None, "marks": {}}

    @property
    def session_until(self):
        return max(self.session_sources.values())

    def authorized(self, request):
        return hmac.compare_digest(request.headers.get("X-Admin-Token", "").encode(), self._token)

    def notify(self):
        self.changed.set()
        self.changed = asyncio.Event()

    def view(self):
        d = self.desk
        if self.privacy:
            return {"status": d.status, "ready": d.status == "ready", "paused": True, "output": "",
                    "last_command": None, "revision": None, "privacy": True}
        display, mode = d.display(), getattr(getattr(d, "cfg", None), "pc_mode", "chromium")
        view = {"status": d.status, "ready": d.status == "ready", "paused": False, "output": "",
                "last_command": self.last_command, "commands": self.commands, "revision": display["revision"],
                "display": display, "error": d.error, "restarts": d.restarts, "privacy": False,
                "session": self.clock() < self.session_until, "pc_mode": mode}
        if mode == "vagon":
            view["vagon"] = d.vagon.public()
        return view

    async def set_privacy(self, active, source="native"):
        if source not in self.privacy_sources:
            raise ValueError("Unknown privacy source")
        self.privacy_sources[source] = bool(active)
        active = any(self.privacy_sources.values())
        if active != self.privacy:
            self.privacy = active
            self.privacy_epoch += 1
            if active:
                self.session_sources = dict.fromkeys(self.session_sources, 0.0)
                await self.desk.release_inputs()
            self.notify()

    async def set_session(self, active, source="native"):
        if source not in self.session_sources:
            raise ValueError("Unknown session source")
        if not active and source == "native":
            await self.desk.release_inputs()
        self.session_sources[source] = self.clock() + 60 if active and not self.privacy else 0.0
        self.notify()

    async def wait_for_change(self, since, wait):
        deadline, epoch = self.clock() + wait, self.privacy_epoch
        status = self.desk.status
        while True:
            revision = self.desk.display()["revision"]
            if self.privacy_epoch != epoch or (not self.privacy and (revision != since or self.desk.status != status)):
                return
            remaining = deadline - self.clock()
            if remaining <= 0:
                return
            try:
                await asyncio.wait_for(self.changed.wait(), min(remaining, 0.25))
            except asyncio.TimeoutError:
                pass

    async def graphical_input(self, clean):
        """Returns the response or None when privacy refuses it (also when it began meanwhile)."""
        if self.privacy:
            return None
        epoch = self.privacy_epoch
        receipt = clean.get("native_receipt")
        payload = {k: v for k, v in clean.items() if k != "native_receipt"}
        queued, started = time.monotonic(), time.time() * 1000
        try:
            ok = await asyncio.wait_for(self.desk.forward(payload), 1.4)
        except asyncio.TimeoutError:
            ok = False
        if self.privacy or epoch != self.privacy_epoch:
            await self.desk.release_inputs()
            return None
        if receipt is None or not ok:
            return {"ok": bool(ok)}
        level = "GuestKeyboardInjected" if payload["type"] == "vga-keyboard" else "GuestMouseInjected"
        return {"ok": True, "native_receipt": receipt, "ack_level": level, "queued_at": queued,
                "ack_received_at": time.monotonic(), "worker_started_ms": started, "worker_finished_ms": time.time() * 1000}

    async def type_input(self, text):
        if self.privacy:
            return None
        epoch = self.privacy_epoch
        if text_blocked(text):
            self.events.append("blocked", what="pc/input", reason=text_blocked(text))
            return {"ok": False, "revision": self.desk.display()["revision"]}
        ok = await self.desk.type_text(text)
        if self.privacy or epoch != self.privacy_epoch:
            return None
        self.last_command = "input"
        return {"ok": bool(ok), "revision": self.desk.display()["revision"]}

    def next_frame_id(self):
        self.obs_count += 1
        return f"{self.epoch}-{self.obs_count:x}"

    async def observe(self):
        async with self.lock:
            frame_id = self.next_frame_id()
            snap = await self.desk.snapshot(frame_id)
            self.last_obs = {"frame_id": frame_id, "marks": {m["id"]: m for m in snap["marks"]}}
            return await asyncio.to_thread(build_observation, snap, frame_id)

    async def act(self, body):
        """Do one action and report what really happened, from a new observation after it."""
        action = validate_action(body)                   # ActionError -> 400
        async with self.lock:
            kind = action["action"]
            stale = action.get("frame_id") and action["frame_id"] != self.last_obs["frame_id"] and ("mark" in action)
            self.commands += 1
            self.last_command = kind
            errors, result = [], {"errors": [], "dialog": None, "load_ms": 0}
            before = await self.desk.snapshot(None)
            refusal = (f"stale frame_id: observe again before using marks (current {self.last_obs['frame_id']})" if stale
                       else action_policy(action, self.last_obs["marks"], self.allow_private))
            if refusal:
                errors.append(refusal)
                if refusal.startswith("blocked"):
                    log(f"blocked action {kind}: {refusal}")
                    self.events.append("blocked", what="action", action=_loggable(action), reason=refusal)
            else:
                run = dict(action, obs=self.last_obs["frame_id"])
                if "mark" in action:
                    run["mark_info"] = self.last_obs["marks"][action["mark"]]
                result = await self.desk.do(run)
                errors += result["errors"]
            frame_id, after = self.next_frame_id(), None       # id of the post-action state; marks come from /desktop/observe
            try:
                after = await self.desk.snapshot(None)
                verdict = page_verdict(after["url"], after["title"], after["text"], self.allow_private)
                if verdict and verdict[0] == "blocked":
                    errors.append(f"blocked page ({verdict[1]}): replaced by a blank page")
                    log(f"blocked page {verdict[1]}")
                    self.events.append("blocked", what="page", reason=verdict[1], url=after["url"][:200])
                    await self.desk.do({"action": "navigate", "url": "about:blank"})
                    after = await self.desk.snapshot(None)
                elif verdict:
                    errors.append(f"{verdict[0]}: {verdict[1]}")
            except DesktopUnavailable as error:
                log(f"no post-action observation: {error}")
            outcome = compute_outcome(before, after, errors, result["load_ms"], result["dialog"])
            if kind == "scroll" and after is not None and not outcome["errors"] and not outcome["changed"]:
                outcome["errors"].append(f"nothing moved when scrolling {action['direction']} (already at the "
                                         f"{'end' if action['direction'] == 'down' else 'top'} of the page?)")
            ok = not outcome["errors"]
            self.events.append("act", action=_loggable(action), ok=ok, outcome=outcome, frame_id=frame_id if after else None)
            if not ok:
                log(f"action {kind} not ok: {outcome['errors'][0]}")
            return {"ok": ok, "outcome": outcome, "frame_id": frame_id if after is not None else None}


def _loggable(action):
    return {k: (v[:200] if isinstance(v, str) else v) for k, v in action.items() if k not in ("obs", "mark_info")}


async def read_json(request):
    if request.content_length is not None and request.content_length > 4096:
        raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=request.content_length)
    raw = await request.content.read(4097)
    if len(raw) > 4096:
        raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=len(raw))
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Expected object")
    return data


def create_app(runner):
    no_store = {"Cache-Control": "no-store"}

    @web.middleware
    async def guard(request, handler):
        if request.path != "/healthz" and not runner.authorized(request):
            raise web.HTTPForbidden(text="Operator authentication required")
        return await handler(request)

    def refuse_private():
        if runner.privacy:
            raise web.HTTPConflict(text="Bathroom privacy is active")

    def unavailable(error):
        return web.json_response({"ok": False, "error": f"browser unavailable ({error})", "status": runner.desk.status},
                                 status=503, headers=no_store)

    async def healthz(request):
        return web.json_response({"ok": True, "status": runner.desk.status, "restarts": runner.desk.restarts}, headers=no_store)

    async def state(request):
        since = request.query.get("since")
        if since is not None:
            try:
                since, wait = int(since), min(MAX_WAIT, max(0.0, float(request.query.get("wait", MAX_WAIT))))
            except ValueError:
                raise web.HTTPBadRequest(text="Invalid since/wait")
            await runner.wait_for_change(since, wait)
        return web.json_response(runner.view(), headers=no_store)

    async def frame(request):
        refuse_private()
        epoch, full = runner.privacy_epoch, request.query.get("full") in ("1", "true")
        got = await runner.desk.frame(full)
        refuse_private()                                  # privacy may have begun while the frame was prepared
        if runner.privacy_epoch != epoch:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        if not got:
            raise web.HTTPNotFound(text="Desktop frame is not available (browser starting or restarting)")
        frame_id, pixels = got
        requested = request.query.get("revision")
        if requested is not None and requested != frame_id:
            raise web.HTTPConflict(text="Desktop frame revision changed")
        tag = '"vga-' + frame_id + ('-full"' if full else '"')
        headers = dict(no_store, ETag=tag)
        if request.headers.get("If-None-Match") == tag:
            return web.Response(status=304, headers=headers)
        return web.Response(body=pixels, content_type="image/png", headers=headers)

    async def command(request):
        data = await read_json(request)
        text, raw = data.get("input"), data.get("raw", False)
        if not isinstance(text, str) or not isinstance(raw, bool) or len(text) > 2000:
            raise web.HTTPBadRequest(text="Input must be text of at most 2000 characters")
        refuse_private()
        result = await runner.type_input(text if raw else text + "\n")
        if result is None:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        return web.json_response(result, headers=no_store)

    async def graphical_input(request):
        data = await read_json(request)
        refuse_private()
        try:
            clean = validate_graphical(data)
        except ValueError as error:
            raise web.HTTPBadRequest(text=str(error))
        if not runner.desk.display()["available"]:
            raise web.HTTPConflict(text="Desktop is unavailable (browser starting or restarting)")
        result = await runner.graphical_input(clean)
        if result is None:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        return web.json_response(result, headers=no_store)

    def flag(data):
        if not isinstance(data.get("active"), bool):
            raise web.HTTPBadRequest(text="Expected active boolean")
        return data["active"]

    async def session(request):
        data = await read_json(request)
        active, source = flag(data), data.get("source", "native")
        if not isinstance(source, str) or source not in runner.session_sources:
            raise web.HTTPBadRequest(text="Unknown session source")
        if active and runner.privacy:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        await runner.set_session(active, source)
        return web.json_response(runner.view(), headers=no_store)

    async def privacy(request):
        data = await read_json(request)
        source = data.get("source", "native")
        if source not in ("native", "home"):
            raise web.HTTPBadRequest(text="Unknown privacy source")
        await runner.set_privacy(flag(data), source)
        return web.json_response(runner.view(), headers=no_store)

    async def device_route(request):
        refuse_private()
        if runner.home_devices is None:
            raise web.HTTPServiceUnavailable(text="Actual full-home device backend is not connected")
        operation = "state" if request.path == "/devices/state" else "frame" if request.method == "GET" else "action"
        return await getattr(runner.home_devices, operation)(request)

    async def observe(request):
        refuse_private()
        try:
            return web.json_response(await runner.observe(), headers=no_store)
        except DesktopUnavailable as error:
            return unavailable(error)

    async def act(request):
        data = await read_json(request)
        refuse_private()
        try:
            return web.json_response(await runner.act(data), headers=no_store)
        except ActionError as error:
            raise web.HTTPBadRequest(text=str(error))
        except DesktopUnavailable as error:
            return unavailable(error)

    app = web.Application(middlewares=[guard], client_max_size=4096)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/pc/state", state)
    app.router.add_get("/pc/frame.png", frame)
    app.router.add_post("/pc/input", command)
    app.router.add_post("/pc/graphical-input", graphical_input)
    app.router.add_post("/pc/session", session)
    app.router.add_post("/pc/privacy", privacy)
    app.router.add_get("/devices/state", device_route)
    app.router.add_get("/devices/{device}/frame.jpg", device_route)
    app.router.add_post("/devices/{device}/action", device_route)
    app.router.add_get("/desktop/observe", observe)
    app.router.add_post("/desktop/act", act)
    return app


async def serve(args):
    token, data = load_token(args.token_file), Path(args.data_dir)
    events = Events(data / "events.jsonl")
    cfg = Config(profile=data / "profile", display=args.display, width=args.size[0], height=args.size[1],
                 headless=args.headless, kiosk=not args.no_kiosk, allow_private=args.allow_private,
                 proxy=args.proxy or "", chromium=args.chromium or "", start_url=args.start_url,
                 pc_mode=args.pc_mode, vagon_url=getattr(args, "vagon_url", "") or "",
                 vagon_api_key_file=getattr(args, "vagon_api_key_file", "") or "")
    desk = Desktop(cfg, events)
    if cfg.pc_mode == "vagon":
        key_status = api_key_file_status(cfg.vagon_api_key_file)
        log(f"vagon mode: stream at {redact_url(cfg.vagon_url)}; API key file {key_status} (not used by the runner)")
        if key_status == "permissive":
            log("warning: the Vagon API key file is readable by other users; make it mode 0600")
    runner = Runner(desk, token, events, allow_private=args.allow_private)
    desk.on_change = runner.notify
    if args.home_origin:
        from scripts.home_device_proxy import HomeDeviceProxy
        runner.home_devices = HomeDeviceProxy(args.home_origin, token, runner)
    site_runner = web.AppRunner(create_app(runner), access_log=None)   # request lines are not logged
    await site_runner.setup()
    await web.TCPSite(site_runner, args.host, args.port).start()
    desk.start()
    log(f"start on http://{args.host}:{args.port} display={args.display} {cfg.width}x{cfg.height} mode={cfg.pc_mode} "
        f"profile={cfg.profile} events={events.path} home={'yes' if args.home_origin else 'no'}")
    events.append("start", host=args.host, port=args.port, display=args.display, size=[cfg.width, cfg.height],
                  profile=str(cfg.profile), headless=cfg.headless, pid=os.getpid(), pc_mode=cfg.pc_mode,
                  **({"vagon_host": redact_url(cfg.vagon_url)} if cfg.pc_mode == "vagon" else {}))
    stop = asyncio.Event()
    for name in ("SIGINT", "SIGTERM"):
        try:
            asyncio.get_running_loop().add_signal_handler(getattr(signal, name), stop.set)
        except (NotImplementedError, AttributeError):
            pass
    try:
        await stop.wait()
    finally:
        log("stopping")
        events.append("stop")
        await site_runner.cleanup()
        await desk.close()
        if runner.home_devices:
            await runner.home_devices.close()


def parse_size(value):
    m = re.fullmatch(r"(\d{3,4})x(\d{3,4})", value)
    if not m:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT such as 1920x1080")
    return int(m.group(1)), int(m.group(2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8832)
    parser.add_argument("--data-dir", required=True, help="private runtime directory (outside Git): profile/ and events.jsonl")
    parser.add_argument("--display", default=":102", help="X display for the headed browser")
    parser.add_argument("--size", type=parse_size, default=SCREEN, help="viewport and screen size (default 1920x1080)")
    parser.add_argument("--token-file", help="file holding the operator credential (or SUB01_ADMIN_TOKEN)")
    parser.add_argument("--home-origin", help="home backend loopback origin for the /devices/* proxy")
    parser.add_argument("--start-url", default="about:blank")
    parser.add_argument("--proxy", help="upstream proxy for the browser (DNS is then left to the proxy)")
    parser.add_argument("--chromium", help="Chromium executable (default: Playwright's)")
    parser.add_argument("--headless", action="store_true", help="no X display (tests and CI)")
    parser.add_argument("--no-kiosk", action="store_true", help="show the browser window frame instead of the page only")
    parser.add_argument("--allow-private", action="store_true", help="TESTS ONLY: allow loopback/LAN pages and ports")
    parser.add_argument("--pc-mode", choices=PC_MODES, default="chromium",
                        help="chromium: browse itself (default); vagon: show the owner's Vagon Streams page")
    parser.add_argument("--vagon-url", help="vagon mode: the stream link (prefer stream_url in the config file: a "
                                            "command line is visible to other users); never logged beyond its host")
    parser.add_argument("--vagon-config", help=f"vagon mode: JSON file {{schema: {VAGON_SCHEMA}, stream_url, "
                                               f"api_key_file?}} (default <streamer-dir>/vagon.json)")
    parser.add_argument("--streamer-dir", default=os.environ.get("STREAMER_DIR", DEFAULT_STREAMER_DIR),
                        help="streamer state directory: holds vagon.json (env STREAMER_DIR)")
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK:
        parser.error("the streamer desktop binds only to loopback")
    flag_url, args.vagon_url, args.vagon_api_key_file = (args.vagon_url or "").strip(), "", ""
    if args.pc_mode == "vagon":
        config_path = Path(args.vagon_config).expanduser() if args.vagon_config else Path(args.streamer_dir).expanduser() / "vagon.json"
        conf = {"stream_url": "", "api_key_file": ""}
        if args.vagon_config or config_path.is_file():
            try:
                conf = load_vagon_config(config_path, args.allow_private)
            except ValueError as error:
                parser.error(f"{config_path}: {error}")
        url = flag_url or conf["stream_url"]
        if not url:
            parser.error(f"vagon mode needs the owner's stream link: --vagon-url or stream_url in {config_path}")
        why = vagon_url_problem(url, args.allow_private)
        if why:
            parser.error(f"stream link refused: {why}")   # the link itself is never echoed
        args.vagon_url, args.vagon_api_key_file = url, conf["api_key_file"]
        if args.start_url != "about:blank":
            log("--start-url is ignored in vagon mode")
    elif flag_url or args.vagon_config:
        parser.error("--vagon-url and --vagon-config need --pc-mode vagon")
    if len(load_token(args.token_file)) < MIN_TOKEN:
        parser.error("set SUB01_ADMIN_TOKEN or --token-file (at least 12 characters)")
    data = Path(args.data_dir).expanduser().resolve()
    if data == ROOT or ROOT in data.parents:
        parser.error("keep runtime data outside the repository")
    if any(p in str(data).lower() for p in FOREIGN_PROFILES):
        parser.error("--data-dir looks like another browser's profile folder; use a dedicated directory")
    if args.home_origin:
        from scripts.home_device_proxy import loopback_origin
        try:
            loopback_origin(args.home_origin)
        except ValueError as error:
            parser.error(str(error))
    args.data_dir = str(data)
    data.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
