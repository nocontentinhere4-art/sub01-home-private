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
  Owner's console (vagon mode, workstation kind; the page needs no token, the rest does):
    GET  /operator          self-contained page, served only while the Vagon page needs his login (or --operator-console)
    GET  /operator/frame.jpg, POST /operator/input {mouse|key|text}, POST /pc/vagon/start (optional Teams API)
    GET  /pc/vagon/diag     (token) a fresh diagnostic snapshot: WebRTC stats, input counters, what covers the stream

Safety: banking/adult/gambling/trading/login/checkout/payment hosts and paths are refused (also redirects and
sub-frames), no POST navigation, no downloads, file chooser, clipboard or popups, service workers blocked, dialogs
dismissed and reported. A crashed or hung browser is relaunched (`/pc/state.status` is "restarting" meanwhile).
Everything the agent does is appended to <data-dir>/events.jsonl. Playwright is imported only by the Desktop class.

PC modes (`--pc-mode`, docs/streamer/VAGON.md): `chromium` (default, everything above) or `vagon`: the same Chromium
opens the owner's Vagon page (`--vagon-url` or <streamer-dir>/vagon.json) in kiosk mode, presses its
connect/play button, waits for the stream's video/canvas and re-enters after "session ended". The agent primitives are
mapped onto the stream: click/scroll/type/key go to the stream element, navigate/search type the URL into the remote
browser's address bar (Ctrl+L, text, Enter), observe returns the pixels with `mode: "vagon"` and `remote_ready` and no
DOM summary. `/pc/state` carries `pc_mode` and a `vagon` sub-state. The stream URL's query string is never logged.
Input path (measured on the owner's Vagon Computer, 2026-10-23; docs/streamer/VAGON.md A6): keys need only the DOM
focus on the stream element (no click, hover or pointer lock), and fail closed without it; a chord's modifiers are held
VAGON_CHORD_HOLD_S before the key (Vagon drops a key that follows Left-Control within 15 ms); the host page's own default
for modifier chords, Tab, Escape and F-keys is cancelled after the player has seen them, and a host selection (Ctrl+A's
dark tint over the video) is cleared; clicks and the wheel go only where VAGON_HIT_JS finds the stream element itself
under the point, checked before and after the pointer moves, never on the Vagon toolbar handle, its menu or a dialog.

Two Vagon products (`kind` in vagon.json, or `--vagon-kind`): `streams` (a public Vagon Streams link, the default) and
`workstation` (the owner's Vagon Cloud Computer at https://app.vagon.io/workstation, which needs HIS login). In the
workstation kind the runner never has or types credentials: when the page asks for a login it enters the phase
`login_required` and serves an operator console (`GET /operator`, a self-contained page that shows the live desktop and
forwards the owner's mouse and keyboard with the admin token he pastes once) so the owner logs in himself; the login
survives restarts in the persistent profile. The console stays available the whole time the remote desktop is NOT
connected (login_required, dashboard, starting, connecting, ended, blocked) and closes only while it is connected. After
the login it presses Run/Start/Turn on and Connect/Open/Enter (found by text in the main document first, logged as
`vagon_button`; every candidate control and its verdict is logged once per page state as `vagon_controls`); chat, support,
help, cookie and feedback widgets (Intercom and the like, in the page or in their iframes) are never pressed. It waits for
the stream and re-connects after an ended session. The page is never reloaded blindly while it may be connecting: a
`connecting` page is opened again only after 6 minutes AND when it is dead (no request, WebSocket frame or WebRTC byte for
60 s and no video/canvas), on an explicit ended/error text without a way back in, or on the owner's request
(`POST /pc/vagon/reload`). While connecting, a diagnostic snapshot (`vagon_diag` rows every 30 s, the latest in
`/pc/state.vagon.diag`) records the page (title, frames, video/canvas elements, WebGL, WebCodecs, codecs), the WebRTC
peer connections (states, candidate pair types, negotiated codecs, bytes/frames decoded, from an init script), console
errors, failed requests and HTTP errors by host, so a stall can be told apart: ICE/UDP, media/codec, rendering or a dead
page. `connected` is set only on evidence (a video with decoded frames, or a canvas while the page repaints / WebRTC
frames are decoded). A new tab or popup that stays on the Vagon site (the stream window) is adopted as the page instead of
being closed. Privacy lock: until the remote desktop is connected, /desktop/observe and /pc/frame.png return a neutral
"PC not connected" picture, never the account pages, and the host page may navigate only within the workstation/login
pages of app.vagon.io and the stream it opens (billing, team, settings, external sites are blocked and logged). An
optional Teams API key (vagon_pc.py) gives the `machine` field and `POST /pc/vagon/start`.

Chromium flags (documented here and in docs/streamer/VAGON.md): `--gpu off` (default, --disable-gpu) | `swiftshader`
(software WebGL through ANGLE/SwiftShader) | `on` (Chromium decides), `--autoplay` (--autoplay-policy=no-user-gesture-
required) and `--chromium-arg FLAG` (repeatable, verbatim). The flags in use are recorded in the `start` event.
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
import posixpath
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
from urllib.parse import parse_qsl, quote_plus, unquote, urljoin, urlsplit

from aiohttp import web
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageStat

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from computer.input_receipts import native_receipt  # noqa: E402

try:  # stdlib-only guard lists and banner helpers; importing browse.py starts nothing
    import browse as B  # noqa: E402
except Exception:  # the runner also works when only this file is deployed
    B = None

try:  # the optional Vagon Teams API client (stdlib only; nothing is called until a key file is configured)
    import vagon_pc  # noqa: E402
except Exception:
    vagon_pc = None

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
VAGON_KINDS = ("streams", "workstation")
DEFAULT_WORKSTATION_URL = "https://app.vagon.io/workstation"
DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
VAGON_SCHEMA = "sub01.streamer-vagon.v1"
OPERATOR_CONNECTED_GRACE_S = 30.0   # the console stays this long after the desktop connected (a flapping session); never longer
VAGON_API_POLL_S = 60.0       # how often the optional Teams API is asked for the machine's status
VAGON_API_START_GAP_S = 300.0 # at least this long between two API starts of the machine
# Minimum time in a phase before the page may be opened again. `connecting` and `blank` additionally need a DEAD page
# (workstation_reload_reason): a Vagon connection in progress is never interrupted by a blind reload.
VAGON_WS_STUCK_S = {"blank": 120.0, "opening": 60.0, "dashboard": 180.0, "starting": 600.0, "connecting": 360.0}
VAGON_DEAD_S = 60.0           # no request, WebSocket frame or WebRTC byte for this long, and no video/canvas: the page is dead
VAGON_DIAG_EVERY_S = 30.0     # a `vagon_diag` row while the stream is connecting (and once when it connects, ends or reloads)
VAGON_DIAG_CONNECTED_S = 60.0 # ... and while it is connected (frames decoded, candidate pair, focus: the input path's facts)
VAGON_DIAG_FOLLOW_S = 8.0     # ... and this long after the connect (the first one comes before the stats poll has numbers)
VAGON_DIAG_MIN_GAP_S = 2.0    # GET /pc/vagon/diag: at most one fresh snapshot this often
NEUTRAL_TEXT = "PC not connected"
VAGON_TICK_S = 2.0            # how often the stream page is probed for its connect / ended state
VAGON_CLICK_GAP_S = 6.0       # at least this long between two presses of the stream's connect button
VAGON_RELOAD_BACKOFF = (15.0, 30.0, 60.0, 120.0, 300.0)   # seconds before the stream page is opened again
VAGON_BLANK_RELOAD_S = 60.0   # a stream page with neither a button nor a stream for this long is opened again
VAGON_MISSES = 3              # consecutive probes without the stream before "connected" is dropped
VAGON_TYPE_DELAY_MS = 12      # per character: the stream client needs real key events, not inserted text
# The Vagon client forwards each key by its physical code plus the modifier state, and Playwright's keyboard.type() sends
# "?" as the Slash key WITHOUT Shift: the remote PC got "/" for "?", ";" for ":" and lower case for capitals, so every
# search URL (".../html/?q=") broke (owner 10-28: "stuck on the search"). These characters go as explicit Shift chords.
VAGON_SHIFTED = {"?": "Slash", ":": "Semicolon", "!": "Digit1", "@": "Digit2", "#": "Digit3", "$": "Digit4",
                 "%": "Digit5", "^": "Digit6", "&": "Digit7", "*": "Digit8", "(": "Digit9", ")": "Digit0",
                 "_": "Minus", "+": "Equal", "{": "BracketLeft", "}": "BracketRight", "|": "Backslash",
                 '"': "Quote", "<": "Comma", ">": "Period", "~": "Backquote"}


def vagon_key_plan(text):
    """[(chord or None, char)]: a Shift chord for a shifted US-layout character or a capital, else None (typed as is)."""
    out = []
    for ch in text:
        code = VAGON_SHIFTED.get(ch) or (f"Key{ch}" if "A" <= ch <= "Z" else None)
        out.append((f"Shift+{code}" if code else None, ch))
    return out
VAGON_SETTLE_S = 0.8          # pixels need a round trip to the remote machine before they can be compared
# Vagon's keyboard layer (its client bundle, 2026-10-23: keyDownHandler/startPendingCtrl) holds a Left-Control keydown for
# 15 ms to tell it from AltGr and DROPS a key that arrives inside that window, the pending Control with it. Playwright's
# press("Control+a") sends the "a" microseconds after the Control: Ctrl+A, Ctrl+L, Ctrl+Escape never reached Windows
# (measured: 2 keydowns, only the 2 keyups on the control channel). A chord's modifiers are therefore held this long first.
VAGON_CHORD_HOLD_S = 0.1
VAGON_HOVER_S = 0.1           # after the pointer moved onto a click/wheel point, before the second hit test
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
# crypto exchanges and wallets: refused here too, so they stay refused when browse.py is not deployed next to the runner
CRYPTO_HOST = re.compile(r"(^|\.)(coinbase|binance|kraken|bybit|okx|kucoin|bitget|mexc|bitstamp|uniswap|pancakeswap|"
                         r"metamask|walletconnect|dexscreener)\.[a-z.]+$|(^|\.)(crypto\.com|pump\.fun|phantom\.app)$", re.I)
LOGIN_HOST = re.compile(r"^(login|signin|sign-in|sso|auth|oauth|accounts?|idp)\.", re.I)
# the big account providers' login, inbox and account hosts: the `login` class (the agent classifies them the same way)
ACCOUNT_HOST = re.compile(r"(^|\.)(mail\.google\.com|myaccount\.google\.com|accounts\.google\.com|login\.microsoftonline\.com|"
                          r"login\.live\.com|outlook\.live\.com|outlook\.office\.com|appleid\.apple\.com|icloud\.com)$", re.I)
# the owner's infrastructure consoles (he could stop his own pod or rotate a key): never lifted, flag or not
OWNER_HOST = re.compile(r"(^|\.)(claude\.ai|console\.anthropic\.com|runpod\.io|railway\.app)$", re.I)
HOST_RULES = (("adult", ADULT_HOST), ("gambling", GAMBLING_HOST), ("banking", BANK_HOST), ("payment", PAYMENT_HOST),
              ("crypto", CRYPTO_HOST), ("owner-service", OWNER_HOST), ("login", LOGIN_HOST), ("login", ACCOUNT_HOST))
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|sign-?up|signin|signup|servicelogin|userlogin|createaccount|register|"
                        r"my-?account|accounts?|password|oauth2?|sso)(/|\?|$|\.)", re.I)
WIKI_LOGIN = re.compile(r"Special:(UserLogin|CreateAccount)", re.I)
CHECKOUT_PATH = re.compile(r"/(checkout|cart|basket|payments?|pay|billing|purchase|orders?|subscribe|donate|wallet|"
                           r"invoice)(/|\?|$|\.)", re.I)
# --allow-credentials (owner, 2026-10-23; the remote PC only) lifts the `login` host class and the login paths for the
# agent's navigate; changing a password, an e-mail, 2FA or recovery, or deleting an account stays refused (the agent's
# `account_change` class: authentication is not account mutation)
ACCOUNT_CHANGE_PATH = re.compile(
    r"/[^/?#]*(?:change|reset|forgot|forgotten|lost|new|update)[-_]?(?:your[-_]?)?password[^/?#]*(?=[/?#]|$)|"
    r"/password[-_/](?:change|reset|new|update|forgot)(?=[/?#.]|$)|"
    r"/(?:security(?:[-_]?settings)?|recovery|delete[-_]?account|close[-_]?account|deactivate|two[-_]?step|2fa|mfa|"
    r"signinoptions)(?=[/?#.]|$)", re.I)
# MediaWiki's account pages live under /wiki/ (or ?title=) like articles: refused before the article exemption
MEDIAWIKI_ACCOUNT = re.compile(r"Special:(ChangePassword|PasswordReset|ChangeEmail|ChangeCredentials|RemoveCredentials|"
                               r"OATHManage|OATH|BotPasswords|ResetTokens|Preferences|Confirmemail|Invalidateemail)",
                               re.I)
LOGIN_REASONS = ("login", "login-path")      # what --allow-credentials lifts on the remote PC
# The REMOTE PC's browser (vagon mode, the agent's navigate), flag or not: its Chrome profile may already be signed in,
# so these are refused there on top of blocked_url (Kimi review, 2026-10-23: delegation, persistent credentials, data
# export, password vaults, money inside account portals, the owner's Vagon console, adult words in the URL itself)
REMOTE_HOST_RULES = (
    ("owner-service", re.compile(r"(^|\.)vagon\.io$", re.I)),          # his Vagon console (balance, machine)
    ("password-manager", re.compile(r"(^|\.)(passwords\.google\.com|1password\.com|lastpass\.com|bitwarden\.com|"
                                    r"dashlane\.com|keepersecurity\.com|nordpass\.com)$", re.I)),
    ("data-export", re.compile(r"(^|\.)takeout\.google\.com$", re.I)),
)
# account settings portals: their root and sign-in pages only (everything below is account management)
ACCOUNT_PORTAL_HOST = re.compile(r"^(myaccount\.google\.com|account\.google\.com|account\.microsoft\.com|"
                                 r"myaccount\.microsoft\.com|mysignins\.microsoft\.com|account\.live\.com|"
                                 r"appleid\.apple\.com|account\.apple\.com)$", re.I)
PORTAL_SIGNIN = re.compile(r"^/(?:(?:sign-?in|signin|log-?in|login|servicelogin)(?:\.\w{1,5})?/?)?$", re.I)
ACCOUNT_SECURITY_PATH = re.compile(
    r"/(app[-_]?passwords?|passkeys?|security[-_]?keys?|backup[-_]?codes|recovery[-_]?codes|proofs|"
    r"(?:personal[-_])?access[-_]?tokens?|api[-_]?(?:keys?|tokens?)|ssh[-_]?keys?|gpg[-_]?keys?|device[-_]?activity|"
    r"security[-_]?(?:checkup|info)|third[-_]?party(?:[-_]?(?:access|apps?|connections))?|connected[-_]?(?:apps|accounts)|"
    r"authorized[-_]?(?:apps|applications)|takeout|data[-_]?export|export[-_]?(?:your[-_]?)?data|"
    r"download[-_]?(?:your[-_]?)?data|consent|authorize)(?=[/?#.]|$)|"
    r"/o/oauth2(?=[/?#]|$)|/settings/(?:applications|apps|tokens|keys|connections|installations|sessions|emails?|"
    r"security(?:-log)?)(?=[/?#.]|$)", re.I)
SECRET_QUERY = re.compile(r"(^|&)[^=&]*(token|code|key|secret|passw|pwd|otp|auth|session|sig|ticket|magic|nonce)[^=&]*=",
                          re.I)
REMOTE_MONEY_PATH = re.compile(r"/(payments?|payment-?methods?|payments-and-subscriptions|billing|purchases?|wallet|"
                               r"redeem\w*|gift-?cards?|add-?funds|addfunds|top-?up|buy|sell|deposit|withdraw|swap|"
                               r"bridge|stake|checkout|cart|basket|pay)([/?.#-]|$)", re.I)
MONEY_QUERY = re.compile(r"(^|&)(add-?to-?cart|add_to_cart|buy-?now|checkout)=", re.I)
NESTED_URL_DEPTH = 3
TYPED_SCHEME = re.compile(r"^(?:[a-z][a-z0-9+.-]*://|file:|chrome:|chrome-extension:|edge:|about:|javascript:|data:|"
                          r"view-source:|blob:)", re.I)
SLASHLESS_HTTP = re.compile(r"^(https?):/*(?=[^/])", re.I)      # Chromium reads `http:host` and `http:/host` as http://host
TYPED_HOST = re.compile(r"(?:[a-z0-9-]+\.)+[a-z]{2,}|localhost", re.I)


def typed_url(text):
    """The URL a single typed token would open in an address bar, or None: any token with a scheme (`chrome://...`,
    `file:...`: blocked_url refuses those; `http:host` as Chromium reads it), or a host (a name with a TLD, an IP
    literal, localhost, a trailing dot) with an optional port, path, query and fragment. A word, a sentence, an e-mail
    (an `@` before the path) or a password without a dot is not. Limit: a single-label name (`intranet.`, `router/`) is
    not treated as a URL, so passwords such as `Hello123.` or `abc/def` stay typeable."""
    t = str(text or "").strip()
    if not t or any(c.isspace() for c in t):
        return None
    if SLASHLESS_HTTP.match(t) and not re.match(r"^https?://", t, re.I):
        return SLASHLESS_HTTP.sub(lambda m: m.group(1) + "://", t, count=1)
    if TYPED_SCHEME.match(t):
        return t
    if "@" in re.split(r"[/?#]", t, maxsplit=1)[0]:
        return None                                              # user@host: an e-mail, not something to navigate to
    candidate = "https://" + t
    try:
        u = urlsplit(candidate)
        u.port
    except ValueError:
        return None
    host = (u.hostname or "").rstrip(".")
    try:
        ipaddress.ip_address(host.strip("[]"))
        return candidate
    except ValueError:
        return candidate if host and TYPED_HOST.fullmatch(host) else None
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


def blocked_host(host, allow_private=False, allow_login=False):
    """Why a host is refused (adult, gambling, banking, payment, crypto, owner service, login, trading, private), or
    None. `allow_login` (--allow-credentials, the remote PC's address bar only) skips the `login` class and nothing else."""
    h = (host or "").strip("[]").lower().rstrip(".")
    if not h:
        return "no-host"
    if private_host(h):
        return None if allow_private else "private-host"
    plain = (B.HOST_FALSE_HITS.sub("", h) if B else re.sub(r"sussex|essex|middlesex|wessex", "", h))
    for why, rx in HOST_RULES:
        if rx.search(plain) and not (allow_login and why == "login"):
            return why
    if B and (B.trading_host(h) or B.BAD_HOST.search(plain)):
        return "blocked-site"
    return None


def clean_path(raw):
    """The URL path as a browser resolves it: percent-decoded, backslashes as slashes, dot segments removed
    (`/wiki/../checkout` is `/checkout`, not a Wikipedia article)."""
    path = unquote(raw or "") or "/"
    if "\\" not in path and "/." not in path:
        return path
    trailing = path.endswith(("/", "/.", "/.."))
    norm = posixpath.normpath("/" + path.replace("\\", "/").lstrip("/"))
    return norm + "/" if trailing and norm != "/" else norm


def blocked_url(url, allow_private=False, allow_login=False):
    """Why a page URL is refused, or None. Used for navigate/search, links, redirects and the page's final address.
    `allow_login` (only for the agent's navigate on the remote PC with --allow-credentials) lifts the login/SSO/account
    hosts and the login paths; money, adult, gambling, crypto, the owner's consoles, downloads, private hosts and
    account changes (ACCOUNT_CHANGE_PATH) are still refused."""
    try:
        u = urlsplit(str(url or ""))
        port = u.port
    except ValueError:
        return "invalid-url"
    if u.scheme not in ("http", "https"):
        return "scheme"
    if u.username or u.password:
        return "credentials-in-url"
    why = blocked_host(u.hostname, allow_private, allow_login)
    if why:
        return why
    if port not in (None, 80, 443) and not allow_private:
        return "port"
    path = clean_path(u.path)
    if not allow_login and WIKI_LOGIN.search(path + "?" + u.query):
        return "login-path"
    if allow_login and MEDIAWIKI_ACCOUNT.search(path + "?" + unquote(u.query)):
        return "account-change-path"
    article = path.startswith("/wiki/")                  # Wikipedia titles like /wiki/Password are articles, not forms
    if not article and CHECKOUT_PATH.search(path):       # browse.LOGIN_HREF's money words are all in CHECKOUT_PATH
        return "checkout-path"
    if allow_login:
        if not article and ACCOUNT_CHANGE_PATH.search(path):
            return "account-change-path"
    elif not article and (LOGIN_PATH.search(path) or (B and B.LOGIN_HREF.search(path))):
        return "login-path"
    if DOWNLOAD_EXT.search(path):
        return "download"
    return None


def _routes(u):
    """[(path, query)] of the URL and, for a single-page app, of its fragment route (`#/checkout?x=1`, `#!/billing`)."""
    routes = [(clean_path(u.path), unquote(u.query or ""))]
    frag = unquote(u.fragment or "")
    if frag.startswith(("/", "!/")):
        route, _, query = frag.lstrip("!").partition("?")
        routes.append((clean_path(route), query))
    return routes


def _article(path):
    """A wiki article (`/wiki/Payment`, `/wiki/Security`): not a form, whatever its title; Special: pages are not."""
    return path.startswith("/wiki/") and not re.match(r"/wiki/Special:", path, re.I)


def remote_url_problem(url, allow_private=False, allow_login=False, depth=0):
    """Why the agent's navigate may not open `url` in the REMOTE PC's browser (vagon mode), or None: blocked_url (with
    the `login` class lifted by --allow-credentials), then, flag or not, the remote-only rules: the owner's Vagon
    console, password vaults, data export, account portals beyond their sign-in pages, account security and delegation
    (app passwords, tokens, keys, OAuth consent/authorize), MediaWiki account pages, money paths and query actions (also
    in a SPA fragment route and its query), adult words in the URL, a login page over plain http, and every URL embedded
    in a query or the fragment (a `continue=` or `redirect_uri=` target), checked the same way. Wiki articles keep their
    exemption from the path rules. The remote page's final URL after redirects cannot be read back (pixels only): this
    is a check of what is typed, not of where the browser ends up."""
    why = blocked_url(url, allow_private, allow_login)
    if why:
        return why
    u = urlsplit(str(url))
    host = (u.hostname or "").lower().rstrip(".")
    for why, rx in REMOTE_HOST_RULES:
        if rx.search(host):
            return why
    routes = _routes(u)
    for path, query in routes:
        if MEDIAWIKI_ACCOUNT.search(path + "?" + query):
            return "account-change-path"
        if not _article(path):
            if ACCOUNT_CHANGE_PATH.search(path):
                return "account-change-path"
            if ACCOUNT_SECURITY_PATH.search(path):
                return "account-security-path"
            if REMOTE_MONEY_PATH.search(path) or CHECKOUT_PATH.search(path):
                return "checkout-path"
        if MONEY_QUERY.search(query):
            return "checkout-path"
    if ACCOUNT_PORTAL_HOST.match(host) and not all(PORTAL_SIGNIN.match(path) for path, _ in routes):
        return "account-settings"
    frag = unquote(u.fragment or "")
    if ADULT_WORDS.search(" ".join([clean_path(u.path), unquote(u.query or ""), frag])) or (
            B and B.MEDIA_BAD_WORDS.search(unquote(u.query or ""))):
        return "unsafe-text"
    if u.scheme != "https" and not allow_private and login_like(url):
        return "insecure-login"
    if depth < NESTED_URL_DEPTH:
        nested = [frag] + [v for _, query in routes for _, v in parse_qsl(query, keep_blank_values=True)]
        for value in nested:
            value = value.strip()
            if re.match(r"^https?://", value, re.I):
                inner = remote_url_problem(value, allow_private, allow_login, depth + 1)
                if inner:
                    return f"redirect-target ({inner})"
    return None


def login_like(url):
    """A login, account, account-change or account-security page by its host or path, whatever else refuses it."""
    try:
        u = urlsplit(str(url or ""))
        host, path = (u.hostname or "").lower().rstrip("."), clean_path(u.path)
    except ValueError:
        return False
    return bool(LOGIN_HOST.search(host) or ACCOUNT_HOST.search(host) or ACCOUNT_PORTAL_HOST.match(host)
                or LOGIN_PATH.search(path) or (B and B.LOGIN_HREF.search(path)) or WIKI_LOGIN.search(path + "?" + u.query)
                or MEDIAWIKI_ACCOUNT.search(path + "?" + unquote(u.query)) or ACCOUNT_CHANGE_PATH.search(path)
                or ACCOUNT_SECURITY_PATH.search(path))


def sensitive_url(url):
    """The URL may carry a secret: credentials in it, a login/account page (a magic link, a reset code in its path or
    query), or a query parameter named like a token, code, key, password or session."""
    try:
        u = urlsplit(str(url or ""))
        userinfo = bool(u.username or u.password)
    except ValueError:
        return True
    frag = unquote(u.fragment or "")
    return userinfo or login_like(url) or bool(SECRET_QUERY.search(u.query or "") or SECRET_QUERY.search(frag.lstrip("#!/"))
                                               or SECRET_QUERY.search(frag.partition("?")[2]))


def loggable_url(url, remote=False):
    """What a log row shows of a navigate URL: a sensitive one (sensitive_url) as scheme://host/… only; on the remote PC
    every other one without its query and fragment; on the pod's Chromium the URL as it is. Never the userinfo."""
    try:
        u = urlsplit(str(url or ""))
        port = u.port
    except ValueError:
        return ""
    if not u.scheme or not u.hostname:
        return ""
    base = f"{u.scheme}://{u.hostname}" + (f":{port}" if port else "")
    if sensitive_url(url):
        return base + "/…"
    if remote:
        return base + u.path + ("?…" if u.query or u.fragment else "")
    return base + u.path + (f"?{u.query}" if u.query else "") + (f"#{u.fragment}" if u.fragment else "")


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
    """('Control','Shift'), 'a' from "Control+Shift+a"; ActionError when it is not a plain key or combination. A lone
    modifier ("Meta": the Windows key on a remote desktop) is a key of its own."""
    if not isinstance(key, str) or not 1 <= len(key) <= 40:
        raise ActionError("Expected a key name such as Enter or Control+a")
    parts = [key] if key == "+" else key.split("+")
    *mods, last = parts
    lone_modifier = not mods and last in ("Meta", "Control", "Alt", "Shift")
    if any(m not in MODS for m in mods) or not (lone_modifier or last in NAMED_KEYS
                                                 or (len(last) == 1 and last.isprintable() and last != " ")):
        raise ActionError("Unsupported key; use a named key (Enter, ArrowDown, F5, Meta...), one character or Modifier+key")
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


def action_policy(action, marks=None, allow_private=False, allow_login=False, remote=False):
    """Refusal text for an action the desktop will not do (before anything happens), else None. `remote`: the URL is
    typed into the remote PC's browser (vagon mode: remote_url_problem); `allow_login` is that PC's --allow-credentials
    (Runner.remote_logins): it lifts login/account pages for navigate only."""
    kind = action["action"]
    if kind == "navigate":
        why = (remote_url_problem(action["url"], allow_private, allow_login) if remote
               else blocked_url(action["url"], allow_private, allow_login))
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
        url = typed_url(action["text"]) if not why and remote else None
        if url:                                   # a URL typed into the remote address bar gets the navigate rules too
            why = remote_url_problem(url, allow_private, allow_login)
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
# Workstation kind (the owner's Cloud Computer behind his login). Real texts are unknown until the page is seen: heuristics,
# every press is logged as `vagon_button`. Controls that stop, delete, sign out or lead to account pages are never pressed.
VAGON_WS_START_RX = re.compile(r"\b(run|start|turn on|power on|boot( up)?|wake( up)?)\b", re.I)
VAGON_WS_CONNECT_RX = re.compile(r"\b(connect|open|enter|launch|join|resume|go to (my |the )?(computer|desktop|workstation))\b", re.I)
VAGON_WS_NEVER_RX = re.compile(r"\b(stop|shut ?down|turn off|power off|delete|remove|reset|restart|reboot|sign ?out|log ?out|"
                               r"invite|cancel|terminate|destroy|format|wipe|change|edit|rename|settings?|billing|team|members?|"
                               r"profile|account|help|support|docs?|download|install|upgrade|plans?|storage|files?|new tab|"
                               r"trial|buy|purchase|pay(ment)?|subscribe|subscription|checkout|credits?|top ?up|add funds|"
                               r"card|wallet|order)\b", re.I)   # money/trial controls are never pressed (Kimi review, 2026-10-23)
VAGON_WS_STARTING_RX = re.compile(r"(turning|powering|switching|starting|booting|waking) (on|up)|is starting|"
                                  r"starting (your |the )?(computer|machine|workstation|pc)|getting (your |the )?(computer|machine|pc) ready|"
                                  r"preparing|initializ|please wait", re.I)
VAGON_WS_CONNECTING_RX = re.compile(r"connecting|establishing|loading (the )?(stream|desktop|session)|opening (the )?(stream|session)", re.I)
VAGON_LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|signin|auth|oauth2?|sso|verify|verification|two-?factor|2fa|mfa|otp|"
                              r"password|forgot|reset|callback|invite|accept)(/|\?|$|\.)", re.I)   # sign-up is an account page
VAGON_LOGIN_TEXT = re.compile(r"\b(sign in|log in|login|continue with (google|apple|microsoft|github)|forgot (your )?password|"
                              r"don'?t have an account|create (an |your )?account|welcome back|remember me|verification code|"
                              r"two-?factor|authenticator)\b", re.I)
VAGON_ACCOUNT_PATH = re.compile(r"/(billing|payments?|invoices?|subscriptions?|plans?|pricing|checkout|teams?|members?|"
                                r"organizations?|settings?|account|profile|api-?keys?|security|usage|files?|storage|register|"
                                r"sign-?up|delete|admin|users?|credits?|balance|cards?)(/|\?|$|\.)", re.I)
VAGON_WS_PHASES = ("login_required", "dashboard", "starting", "connecting", "connected", "ended", "blocked", "blank",
                   "opening", "restarting")
VAGON_WS_CANVAS_FRACTION = 0.5    # a canvas counts as the remote desktop only when it covers half the viewport (not a chart)
VAGON_MACHINE_STATES = ("unknown", "off", "starting", "on")
# Third-party widgets on the page (chat/support launchers such as Intercom, cookie and feedback banners): never a connect
# control, whatever verb their label starts with ("Open Intercom Messenger"). Applied to labels, to the element's ancestors
# (VAGON_PROBE_JS flags `widget`) and to iframe names/hosts (the probe drops those frames' controls).
VAGON_WS_WIDGET_RX = re.compile(r"intercom|messenger|live ?chat|\bchat\b|support|\bhelp\b|feedback|survey|cookie|consent|"
                                r"notification|announcement|crisp|zendesk|drift|hubspot|freshchat|tawk|olark|"
                                r"send us a message|search for|\bclose\b|dismiss|minimi[sz]e|widget|launcher", re.I)
VAGON_CONTROL_VERDICTS = ("reconnect", "connect", "start", "widget", "login", "money", "never", "none")
EMAIL_RX = re.compile(r"\S+@\S+")
GPU_MODES = ("off", "swiftshader", "on")
GPU_ARGS = {"off": ["--disable-gpu"],
            "swiftshader": ["--use-gl=angle", "--use-angle=swiftshader", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"],
            "on": []}


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
    """<streamer-dir>/vagon.json -> {"kind", "stream_url", "api_key_file", "machine_id"}; ValueError (without the URL)
    when unusable. `kind` is `streams` (default; the link is `stream_url`) or `workstation` (the owner's Cloud Computer
    page is `url`, default https://app.vagon.io/workstation). `stream_url` holds the page URL for either kind."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"cannot read the Vagon config: {error.strerror or error}")
    except ValueError:
        raise ValueError("the Vagon config is not valid JSON")
    if not isinstance(data, dict) or data.get("schema") != VAGON_SCHEMA:
        raise ValueError(f"the Vagon config must be an object with schema {VAGON_SCHEMA}")
    kind = data.get("kind", "streams")
    if kind not in VAGON_KINDS:
        raise ValueError("kind must be one of " + ", ".join(VAGON_KINDS))
    url = data.get("stream_url")
    if kind == "workstation":
        if url is not None:
            raise ValueError("a workstation config names its page as url, not stream_url")
        url = data.get("url", DEFAULT_WORKSTATION_URL)
        why = workstation_url_problem(url, url, allow_private) if isinstance(url, str) else "expected a URL"
        if why:
            raise ValueError(f"url: {why}")
        url = url.strip()
    elif data.get("url") is not None:
        raise ValueError("url is for kind workstation; a stream link is stream_url")
    elif url is not None:
        why = vagon_url_problem(url, allow_private)
        if why:
            raise ValueError(f"stream_url: {why}")
        url = url.strip()
    key_file = data.get("api_key_file")
    if key_file is not None and (not isinstance(key_file, str) or not key_file.strip() or not os.path.isabs(key_file.strip())):
        raise ValueError("api_key_file must be an absolute path")
    machine_id = data.get("machine_id")
    if machine_id is not None and (not isinstance(machine_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", machine_id)):
        raise ValueError("machine_id must be a short identifier (letters, digits, _ . -)")
    unknown = set(data) - {"schema", "kind", "stream_url", "url", "api_key_file", "machine_id"}
    if unknown:
        raise ValueError("unknown keys in the Vagon config: " + ", ".join(sorted(unknown)))
    return {"kind": kind, "stream_url": url or "", "api_key_file": (key_file or "").strip(), "machine_id": machine_id or ""}


def _site_apex(host):
    """'app.vagon.io' -> 'vagon.io'; an IP address or a single label -> itself."""
    h = (host or "").strip("[]").lower().rstrip(".")
    try:
        ipaddress.ip_address(h)
        return h
    except ValueError:
        parts = h.split(".")
        return ".".join(parts[-2:]) if len(parts) >= 2 else h


def same_site(url_parts, base_parts):
    """The URL is on the configured page's host (same port) or on a sibling host of its site (login.vagon.io for
    app.vagon.io)."""
    host, base = (url_parts.hostname or "").lower(), (base_parts.hostname or "").lower()
    if not host or not base:
        return False
    if host == base:
        default = {"https": 443, "http": 80}
        return (url_parts.port or default.get(url_parts.scheme)) == (base_parts.port or default.get(base_parts.scheme))
    apex = _site_apex(base)
    return "." in apex and not apex.replace(".", "").isdigit() and (host == apex or host.endswith("." + apex))


def workstation_url_problem(url, base_url, allow_private=False):
    """Why the host page may not go to `url` in the workstation kind, or None. Allowed: https (http only for tests), no
    credentials, the configured page's site only (`external` otherwise), and on it no account page (billing, team,
    settings, members, api keys, usage, files, sign-up...: `account-page`); login/verification paths are always allowed
    because the owner's login flow needs them."""
    if not isinstance(url, str) or not url.strip() or any(c.isspace() for c in url.strip()):
        return "expected a URL"
    try:
        u, b = urlsplit(url.strip()), urlsplit(str(base_url or "").strip())
        u.port, b.port
    except ValueError:
        return "invalid-url"
    if u.scheme != "https" and not (allow_private and u.scheme == "http"):
        return "scheme"
    if u.username or u.password:
        return "credentials-in-url"
    if not u.hostname:
        return "no-host"
    if not b.hostname or not same_site(u, b):
        return "external"
    path = unquote(u.path)
    if VAGON_LOGIN_PATH.search(path):
        return None
    if VAGON_ACCOUNT_PATH.search(path):
        return "account-page"
    return None


def workstation_request_blocked(url, base_url, main_frame=False, method="GET", allow_private=False):
    """Network verdict in the workstation kind: main-frame navigations must stay on the site and off its account pages
    (POST is allowed: a login form may submit); sub-resources from the site are allowed, others get the generic host
    rules (CDNs and fonts yes, banks and the owner's services no)."""
    if url == "about:blank" or url.startswith(("data:", "blob:")):
        return None
    if main_frame:
        if method.upper() not in ("GET", "HEAD", "POST"):
            return "method"
        return workstation_url_problem(url, base_url, allow_private)
    try:
        if same_site(urlsplit(url), urlsplit(base_url)):
            return None
    except ValueError:
        return "invalid-url"
    return request_blocked(url, False, method, allow_private)


def control_verdict(button):
    """What the runner makes of one control of the workstation page: `reconnect`, `connect` or `start` (pressable, in
    that order of preference), or why it is never pressed: `widget` (a chat/support/cookie/feedback widget by its label or
    its ancestors, e.g. Intercom's "Open Intercom Messenger"), `login`, `money`, `never` (stop, delete, sign out,
    settings, help, trial... VAGON_WS_NEVER_RX) or `none` (no label, too long, or nothing the runner understands)."""
    b = button or {}
    label = " ".join(str(b.get("label") or "").split())
    if b.get("widget") or VAGON_WS_WIDGET_RX.search(label):
        return "widget"
    if not label or len(label) > 60:
        return "none"
    if LOGIN_LABEL.search(label):
        return "login"
    if MONEY_LABEL.search(label):
        return "money"
    if VAGON_WS_NEVER_RX.search(label):
        return "never"
    if VAGON_RECONNECT_RX.search(label):
        return "reconnect"
    if VAGON_WS_CONNECT_RX.search(label):
        return "connect"
    if VAGON_WS_START_RX.search(label):
        return "start"
    return "none"


def choose_workstation_button(buttons):
    """(index, kind) of the control to press on the workstation page: a reconnect/try-again control first, then
    connect/open/enter (the computer is on), then run/start/turn on (it is off). Never a widget, a login or money control,
    never stop/delete/sign out/settings and the like (control_verdict). (None, None) when nothing fits."""
    ranks = {"reconnect": 0, "connect": 1, "start": 2}
    best, best_rank = None, None
    for i, b in enumerate(buttons or []):
        rank = ranks.get(control_verdict(b))
        if rank is not None and (best_rank is None or rank < best_rank):
            best, best_rank = i, rank
    return best, (None if best is None else ("reconnect", "connect", "start")[best_rank])


def controls_summary(buttons, limit=30):
    """The `vagon_controls` log: every candidate control's label (40 chars, e-mail addresses masked) and its verdict,
    plus the frame it came from when it was not the main document. Never a typed value: labels are captions only."""
    out = []
    for b in (buttons or [])[:limit]:
        label = EMAIL_RX.sub("<email>", " ".join(str(b.get("label") or "").split()))[:40]
        item = {"label": label, "verdict": control_verdict(b)}
        if b.get("frame"):
            item["frame"] = str(b["frame"])[:60]
        out.append(item)
    return out


def workstation_reload_reason(phase, stuck_for, attempts, dead, requested=False):
    """Why the workstation page is opened again now, or None (no blind reload). The owner's request (`POST
    /pc/vagon/reload`) and an `ended` page without a way back in reload at once (after the backoff); six presses without
    effect too. Otherwise the phase must have lasted its VAGON_WS_STUCK_S minimum, and `connecting` and `blank` (a page
    that may still be setting the stream up: Vagon can take minutes) reload only when the page is DEAD: no request,
    WebSocket frame or WebRTC byte for VAGON_DEAD_S and no video/canvas element (`dead`, see page_dead)."""
    if requested:
        return "operator request"
    if phase == "ended":
        return "ended"
    if attempts >= 6:
        return "six presses without effect"
    stuck = VAGON_WS_STUCK_S.get(phase)
    if stuck is None or stuck_for < stuck:
        return None
    if phase in ("connecting", "blank"):
        return "dead page" if dead else None
    return f"stuck in {phase}"


def page_dead(now, activity, has_stream):
    """The page is dead: it holds no video/canvas and nothing happened on the network (`activity`: monotonic times of the
    last request, WebSocket frame and WebRTC byte) for VAGON_DEAD_S."""
    if has_stream:
        return False
    last = max([t for t in (activity or {}).values() if t] or [0.0])
    return now - last >= VAGON_DEAD_S


def stream_evidence(stream, rtc=None, repaint=False):
    """`connected` needs evidence that the stream element shows pictures, not just that it exists: a video with decoded
    frames (its playback quality, or the WebRTC inbound stats), or a canvas while the page repainted (the screencast sent
    a new frame) or WebRTC frames were decoded. A video element without data, or a blank canvas, is still `connecting`."""
    if not stream:
        return False
    frames = int(stream.get("frames") or 0)
    decoded = int((rtc or {}).get("frames_decoded") or 0)
    if stream.get("tag") == "video":
        return frames > 0 or decoded > 0
    return decoded > 0 or bool(repaint)


def login_page_reason(path, passwords, text, buttons=None):
    """Why the page is a login page, or None: its path (/login, /signin, /auth, /verify...), a visible password field,
    or sign-in text on a page that offers no computer control (a dashboard with 'Sign out' is not a login page)."""
    if VAGON_LOGIN_PATH.search(unquote(str(path or ""))):
        return "path"
    if passwords:
        return "password field"
    if VAGON_LOGIN_TEXT.search(str(text or "")) and choose_workstation_button(buttons)[0] is None:
        return "sign-in text"
    return None


def _stream_fraction(stream, probe):
    try:
        vw, vh = float(probe.get("vw") or 0), float(probe.get("vh") or 0)
        return stream["box"][2] * stream["box"][3] / (vw * vh) if vw and vh else 0.0
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return 0.0


def classify_workstation(probe):
    """{phase, button, kind, machine, why} from a probe of the workstation page (`main` holds the main frame's url,
    password-field count and text when the stream lives in an iframe). Phases: login_required (the owner must log in),
    blocked (an account page), connected (a playing video or a canvas covering half the viewport, no ended text),
    ended (ended text or a reconnect offer), dashboard (a connect button: machine on; a run/start button: machine off),
    starting (the page says the computer is turning on), connecting, blank."""
    p = probe or {}
    main = p.get("main") or p
    url = str(main.get("url") or p.get("url") or "")
    try:
        path = urlsplit(url).path
    except ValueError:
        path = ""
    text = " ".join(str(p.get("text") or "").split())
    main_text = " ".join(str(main.get("text") or text).split())
    buttons, stream = p.get("buttons") or [], p.get("stream") or None
    idx, kind = choose_workstation_button(buttons)
    out = {"phase": "blank", "button": None, "kind": None, "machine": "unknown", "why": ""}
    why = login_page_reason(path, main.get("passwords", 0), main_text, buttons)
    if why:
        return dict(out, phase="login_required", why=why)
    if VAGON_ACCOUNT_PATH.search(unquote(path)):
        return dict(out, phase="blocked", why="account-page")
    view = main if main.get("vw") else p                  # the stream box is in main-frame pixels (iframe offset applied)
    desktop_sized = bool(stream) and (stream.get("tag") == "video" or _stream_fraction(stream, view) >= VAGON_WS_CANVAS_FRACTION)
    big = desktop_sized and stream.get("playing", True)
    ended = bool(VAGON_ENDED_RX.search(text)) or kind == "reconnect"
    if big and not ended:
        return dict(out, phase="connected", machine="on")
    if ended:
        return dict(out, phase="ended", button=idx, kind=kind)
    if kind == "connect":
        return dict(out, phase="dashboard", button=idx, kind=kind, machine="on")
    if kind == "start":
        return dict(out, phase="dashboard", button=idx, kind=kind, machine="off")
    if VAGON_WS_STARTING_RX.search(text):
        return dict(out, phase="starting", machine="starting")
    if desktop_sized or VAGON_WS_CONNECTING_RX.search(text) or VAGON_BUSY_RX.search(text):
        return dict(out, phase="connecting", machine="on")   # a stalled video, or the page says so; a small canvas is a chart
    return out


_NEUTRAL = {}


def neutral_jpeg(size=SMALL, text=NEUTRAL_TEXT):
    """A grey picture saying "PC not connected": what leaves the runner instead of the owner's account pages."""
    key = (tuple(size), text)
    if key not in _NEUTRAL:
        img = Image.new("RGB", tuple(size), (72, 74, 78))
        draw, font = ImageDraw.Draw(img), _font(max(16, size[1] // 20))
        tw = draw.textlength(text, font=font)
        draw.text(((size[0] - tw) / 2, size[1] / 2 - size[1] / 40), text, fill=(200, 200, 204), font=font)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=70)
        _NEUTRAL[key] = out.getvalue()
    return _NEUTRAL[key]


OPERATOR_KEY_RX = re.compile(r"[A-Za-z][A-Za-z0-9]{0,24}")


def validate_operator(data):
    """The operator console's input: {type: mouse, x, y (fractions 0..1 of the frame), buttons?: [l, m, r], wheel?},
    {type: key, key: a key code such as Tab, Enter, KeyA, ShiftLeft, down: bool} or {type: text, text}. ValueError with a
    message (never echoing the text) when malformed."""
    if not isinstance(data, dict):
        raise ValueError("Expected an input object")
    kind = data.get("type")
    if kind == "mouse":
        x, y = data.get("x"), data.get("y")
        if not _num(x) or not _num(y) or not 0 <= x <= 1 or not 0 <= y <= 1:
            raise ValueError("Expected x and y as fractions 0..1 of the frame")
        clean = {"type": "mouse", "x": float(x), "y": float(y)}
        if "buttons" in data:
            b = data["buttons"]
            if not isinstance(b, list) or len(b) != 3 or any(not isinstance(v, bool) for v in b):
                raise ValueError("Expected three mouse buttons")
            clean["buttons"] = list(b)
        if "wheel" in data:
            if not _num(data["wheel"]) or abs(data["wheel"]) > 2000:
                raise ValueError("Expected a bounded wheel delta")
            clean["wheel"] = float(data["wheel"])
        return clean
    if kind == "key":
        key, down = data.get("key"), data.get("down", True)
        if not isinstance(key, str) or not OPERATOR_KEY_RX.fullmatch(key) or not isinstance(down, bool):
            raise ValueError("Expected a key code (Tab, Enter, KeyA, ShiftLeft...) and down true/false")
        return {"type": "key", "key": key, "down": down}
    if kind == "text":
        text = data.get("text")
        if (not isinstance(text, str) or not 1 <= len(text) <= 2000
                or any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in text)):
            raise ValueError("Expected text of 1-2000 characters (newlines press Enter)")
        return {"type": "text", "text": text}
    raise ValueError("Unknown operator input")


class VagonApi:
    """The optional Teams API (vagon_pc.py) for the workstation kind: the machine's status and a start. The key pair is
    read once from `api_key_file` (mode 0600; one line `KEY:SECRET`, or the key on the first line and the secret on the
    second), kept in memory, never logged; every error text comes from vagon_pc, which scrubs credentials and links."""

    def __init__(self, credentials, machine_id):
        self._credentials, self.machine_id = credentials, machine_id
        self.status, self.read_at, self.error, self.started_at, self.starts = None, 0.0, "", 0.0, 0

    @classmethod
    def load(cls, key_file, machine_id):
        if vagon_pc is None:
            raise ValueError("vagon_pc.py is not importable here")
        if not machine_id:
            raise ValueError("machine_id is missing in the Vagon config")
        state = api_key_file_status(key_file)
        if state != "configured":
            raise ValueError(f"the API key file is {state}" + (" (make it mode 0600)" if state == "permissive" else ""))
        try:
            lines = [l.strip() for l in Path(key_file).read_text(encoding="utf-8").splitlines() if l.strip()]
        except (OSError, UnicodeDecodeError):
            raise ValueError("the API key file cannot be read")
        if len(lines) == 1 and lines[0].count(":") == 1:
            key, secret = lines[0].split(":")
        elif len(lines) == 2:
            key, secret = lines
        else:
            raise ValueError("the API key file must hold KEY:SECRET on one line or the key and the secret on two lines")
        if not key or not secret or any(c.isspace() for c in key + secret):
            raise ValueError("the API key file holds an empty or malformed key pair")
        return cls((key, secret), machine_id)

    def machine(self):
        """'unknown' | 'off' | 'starting' | 'on' from the last status reading."""
        st = self.status
        if st in vagon_pc.READY_STATUSES:
            return "on"
        if st in vagon_pc.STARTING_STATUSES:
            return "starting"
        if st in vagon_pc.OFF_STATUSES:
            return "off"
        return "unknown"

    def fresh(self, within=2 * VAGON_API_POLL_S):
        return self.status is not None and time.monotonic() - self.read_at < within

    def refresh(self):
        """Blocking: one GET /machines. Sets status (or error) and returns the machine state."""
        try:
            self.status, self.error = vagon_pc.status(self.machine_id, credentials=self._credentials), ""
        except Exception as error:
            self.status, self.error = None, clean_error(error)
        self.read_at = time.monotonic()
        return self.machine()

    def start(self):
        """Blocking: POST /machines/{id}/start; the error text (or '') is returned, never raised."""
        try:
            vagon_pc.start_machine(self.machine_id, credentials=self._credentials)
            self.started_at, self.starts, self.error = time.monotonic(), self.starts + 1, ""
            self.status = "turning_on"
            self.read_at = self.started_at
            return ""
        except Exception as error:
            self.error = clean_error(error)
            return self.error


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
        if (not label or LOGIN_LABEL.search(label) or MONEY_LABEL.search(label) or b.get("widget")
                or VAGON_WS_WIDGET_RX.search(label)):
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
    """What the runner knows about the remote session; `public()` is the `vagon` field of /pc/state. The workstation
    kind adds `logged_in`, `machine` (unknown|off|starting|on), `blocked` (navigations refused) and `login_why`."""

    def __init__(self, api_key="none", kind="streams"):
        self.connected, self.phase, self.api_key, self.kind = False, "starting" if kind == "streams" else "opening", api_key, kind
        self.sessions, self.reconnects, self.last_reconnect_utc, self.since = 0, 0, None, time.time()
        self.attempts, self.reloads, self.reload_streak, self.misses = 0, 0, 0, 0
        self.last_click, self.last_reload, self.blank_since, self.last_label = 0.0, 0.0, None, ""
        self.logged_in, self.machine, self.machine_source, self.blocked = False, "unknown", "none", 0
        self.login_seen, self.login_why, self.stuck_since, self.last_api_start = None, "", None, 0.0
        self.connected_at, self.reload_requested, self.last_reload_why = None, False, ""
        self.diag, self.diag_at, self.last_diag, self.last_controls = None, None, 0.0, None
        # Turning the owner's computer on spends his Vagon balance: one start per arming (POST /pc/vagon/arm) unless
        # --vagon-autostart. `start_armed_until` is a monotonic deadline; `start_held` is logged once per off period.
        self.autostart, self.start_armed_until, self.start_held, self.starts = False, 0.0, False, 0

    def start_allowed(self, now):
        return self.autostart or now < self.start_armed_until

    def consume_start(self, now):
        self.starts += 1
        self.start_held = False
        if not self.autostart:
            self.start_armed_until = 0.0                  # one start per arming

    def set_phase(self, phase):
        changed = phase != self.phase
        if changed:
            self.phase, self.since = phase, time.time()
        return changed

    def public(self):
        out = {"connected": self.connected, "phase": self.phase, "reconnects": self.reconnects,
               "last_reconnect_utc": self.last_reconnect_utc, "sessions": self.sessions, "reloads": self.reloads,
               "since_utc": datetime.fromtimestamp(self.since, timezone.utc).isoformat(timespec="seconds"),
               "api_key_file": self.api_key, "kind": self.kind}
        if self.kind == "workstation":
            now = time.monotonic()
            out.update(autostart=self.autostart, start_armed_s=round(max(0.0, self.start_armed_until - now), 1),
                       start_held=self.start_held, starts=self.starts)
            out.update(logged_in=self.logged_in, machine=self.machine, machine_source=self.machine_source,
                       blocked=self.blocked, login_why=self.login_why, reload_requested=self.reload_requested,
                       last_reload_why=self.last_reload_why, diag=self.diag,
                       diag_at_utc=(datetime.fromtimestamp(self.diag_at, timezone.utc).isoformat(timespec="seconds")
                                    if self.diag_at else None))
        return out


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
    base = key
    for suffix in ("Right", "Left"):
        if key.endswith(suffix) and key[:-len(suffix)] in MODS:
            base = key[:-len(suffix)]
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
    pc_mode: str = "chromium"            # "chromium" browses itself; "vagon" shows the owner's Vagon page
    vagon_url: str = ""                  # the stream link or the workstation page (never logged beyond scheme and host)
    vagon_api_key_file: str = ""         # optional; streams: recorded as present/absent only; workstation: the Teams API
    vagon_kind: str = "streams"          # "streams" (public stream link) or "workstation" (the owner's Cloud Computer, his login)
    vagon_machine_id: str = ""           # workstation: the machine's id for the optional API
    operator_console: bool = False       # serve /operator always, not only while the Vagon page needs the owner's login
    gpu: str = "off"                     # "off": --disable-gpu; "swiftshader": software WebGL (ANGLE/SwiftShader); "on": Chromium decides
    autoplay: bool = False               # --autoplay-policy=no-user-gesture-required: a stream video may play without a click
    extra_args: tuple = ()               # --chromium-arg, passed verbatim (documented in the start event)
    vagon_autostart: bool = False        # workstation: press Run/Start (or the API start) on its own; off = only when armed
    allow_credentials: bool = False      # vagon mode: the agent may navigate the REMOTE PC to login/account pages (the
                                         # CLI's --allow-credentials, default on; off here so a bare Config fails closed)


class DesktopUnavailable(RuntimeError):
    """The browser is starting, restarting or unusable right now."""


class ActFailed(RuntimeError):
    """An action could not be carried out (stale mark, covered element, blocked target); the text goes to the agent."""


PULSE_SINK = "sub01_apps"              # the application-audio null sink of scripts/streamer_audio.sh


def pulse_socket(streamer_dir):
    """The application-audio server's socket (<streamer-dir>/run/pulse/native, scripts/streamer_audio.sh) when it accepts
    a connection within 0.5 s, else None: the browser is then launched muted, exactly as before."""
    path = Path(streamer_dir) / "run" / "pulse" / "native"
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            sock.connect(str(path))
    except OSError:
        return None
    return path


def chromium_args(cfg, pulse=None):
    """The browser's flags: the fixed set, the GPU mode (GPU_ARGS), the autoplay policy and the operator's extra flags.
    With `pulse` (an answering application-audio socket) the browser is not muted and media may play without a click."""
    args = ["--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-extensions",
            "--disable-background-networking", "--mute-audio", "--password-store=basic",
            "--disable-dev-shm-usage", "--deny-permission-prompts", "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble", "--disable-infobars", "--noerrdialogs",
            "--disable-features=Translate,AutofillServerCommunication", "--window-position=0,0",
            f"--window-size={cfg.width},{cfg.height}"]
    args += GPU_ARGS.get(getattr(cfg, "gpu", "off") or "off", GPU_ARGS["off"])
    if pulse:
        args.remove("--mute-audio")
    if pulse or getattr(cfg, "autoplay", False):
        args.append("--autoplay-policy=no-user-gesture-required")
    args += [str(a) for a in (getattr(cfg, "extra_args", ()) or ()) if str(a).startswith("--")]
    return args + (["--kiosk"] if cfg.kiosk and not cfg.headless else [])


def chromium_env(display, environ=None, pulse=None):
    """A clean environment for the browser: no operator token, no API keys, only what Chromium needs (with `pulse`, the
    application-audio server and its sink)."""
    environ = os.environ if environ is None else environ
    env = {k: v for k, v in environ.items() if k in SAFE_ENV}
    env["DISPLAY"] = display
    if pulse:
        env["PULSE_SERVER"], env["PULSE_SINK"] = f"unix:{pulse}", PULSE_SINK
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
  const out = {url: location.href, title: document.title || '', vw, vh, loading: document.readyState !== 'complete', text: '', buttons: [], stream: null, passwords: 0};
  const shown = r => r.width >= 1 && r.height >= 1 && r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw;
  const hide = cs => cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity < 0.05;
  for (const el of document.querySelectorAll('input[type=password]')) {
    const r = el.getBoundingClientRect();
    if (shown(r) && !hide(getComputedStyle(el))) out.passwords++;
  }
  let best = null, area = 0;
  for (const el of document.querySelectorAll('video, canvas')) {
    const r = el.getBoundingClientRect();
    if (r.width < minW || r.height < minH || !shown(r) || hide(getComputedStyle(el))) continue;
    if (r.width * r.height > area) {
      area = r.width * r.height;
      const video = el.tagName === 'VIDEO';
      let frames = null;
      if (video) { try { frames = el.getVideoPlaybackQuality().totalVideoFrames; } catch (e) { frames = null; } }
      best = {tag: el.tagName.toLowerCase(), box: [r.left, r.top, r.width, r.height],
        playing: video ? (el.readyState >= 2 && !el.paused && !el.ended && el.videoWidth > 0) : true, frames};
    }
  }
  out.stream = best;
  // chat/support/cookie widgets (Intercom's launcher lives in the main document): their controls are never connect buttons
  const WIDGET = '[id*="intercom" i],[class*="intercom" i],[name*="intercom" i],[id*="launcher" i],[class*="launcher" i],[id*="widget" i],[class*="widget" i],[id*="cookie" i],[class*="cookie" i],[id*="consent" i],[class*="consent" i],[class*="crisp" i],[id*="crisp" i],[class*="zendesk" i],[id*="hubspot" i],[class*="hubspot" i],[class*="drift" i],[id*="drift" i],[class*="chat" i],[id*="chat" i]';
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
    const tag = el.tagName.toLowerCase(), type = (el.getAttribute('type') || '').toLowerCase();
    const caption = tag === 'input' ? (['button', 'submit', 'reset'].includes(type) ? el.value : '') : '';   // never a typed value
    let label = (el.getAttribute('aria-label') || el.innerText || caption || el.title || el.getAttribute('alt') || '').toString().trim();
    if (!label) { const m = /(reconnect|connect|play|start)/i.exec(el.className || ''); label = m ? m[1] : ''; }
    let widget = false;
    try { widget = !!el.closest(WIDGET); } catch (e) { widget = false; }
    out.buttons.push({label: label.replace(/\s+/g, ' ').slice(0, 80), box: [r.left, r.top, r.width, r.height], widget});
  }
  return out;
}"""
# Keyboard focus on the stream element before keys; true only when the stream element itself has the focus (no stream:
# the body is focused, so no host field keeps it, and false is returned). Also: (1) any selection on the HOST page is
# cleared - Ctrl+A that the player forwarded but did not prevent also ran the host page's select-all, which tints the whole
# video dark (the "dim" of 2026-10-23); (2) once per window, a keydown listener registered after every other one (window,
# bubble phase: the player's own document/root listeners have run and seen the event untouched) cancels the HOST page's
# default action for keys aimed at the stream: modifier combinations (select all, find, print, back...), Tab (host
# focus), Escape and F1-F12 (reload...). preventDefault only: plain characters and propagation are left alone.
VAGON_FOCUS_JS = r"""([minW, minH]) => {
  let best = null, area = 0;
  for (const el of document.querySelectorAll('video, canvas')) {
    const r = el.getBoundingClientRect();
    if (r.width >= minW && r.height >= minH && r.width * r.height > area) { area = r.width * r.height; best = el; }
  }
  try { const s = getSelection(); if (s && s.rangeCount && s.type === 'Range') s.removeAllRanges(); } catch (e) {}
  window.__sub01Stream = best;
  if (!window.__sub01HostKeys) {
    window.__sub01HostKeys = true;
    window.addEventListener('keydown', e => {
      if (e.target === window.__sub01Stream && (e.ctrlKey || e.metaKey || e.altKey || /^(Tab|Escape|F\d{1,2})$/.test(e.key))) e.preventDefault();
    });
  }
  const el = best || document.body;
  if (!el) return false;
  if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
  try { el.focus({preventScroll: true}); } catch (e) { return false; }
  return !!best && document.activeElement === best;
}"""
# Init script (every frame, before the page's own code): wraps RTCPeerConnection to record its state transitions, the
# negotiated codecs (payload type and codec name per m= line, never ICE credentials), tracks/data channels, candidate
# errors and a getStats poll (first after 1 s, then every 5 s: selected candidate pair types/protocol, inbound video
# bytes, frames decoded/dropped, fps, packets lost, jitter, decoder, codec), and counts outbound data-channel messages
# per label and WebSocket sends (counts and bytes only: where the input travels). Added with context.add_init_script, it
# runs in every frame, a script-created about:blank iframe included (measured: the iframe keeps its own record, read by
# the per-frame diag); workers have no RTCPeerConnection. At most 8 records: a finished connection is dropped before a
# live one, so the connection that carries the stream is never pushed out by the page's later ones (Vagon makes one per
# (re)connection). Also counts HTMLMediaElement.play() calls and their refusals (autoplay policy). Read back by
# VAGON_DIAG_JS as window.__sub01Rtc.
RTC_INIT_JS = r"""(() => {
  if (window.__sub01Rtc || typeof RTCPeerConnection !== 'function') return;
  const R = window.__sub01Rtc = {pcs: [], events: [], media: {play: 0, rejected: []}, created: 0};
  const t = () => Math.round(performance.now());
  const safeUrl = u => String(u).replace(/:[^:@\/]*@/, ':***@').slice(0, 80);
  const ev = (pc, kind, value) => { R.events.push({t: t(), pc: pc.__id, k: kind, v: String(value).slice(0, 80)}); if (R.events.length > 200) R.events.splice(0, R.events.length - 200); };
  const sdpSummary = sdp => {
    const out = [];
    for (const line of String(sdp || '').split(/\r?\n/)) {
      if (line.startsWith('m=')) { const p = line.split(' '); out.push({media: p[0].slice(2), pts: p.slice(3).join(','), codecs: [], cands: 0}); }
      else if (!out.length) continue;
      else if (line.startsWith('a=rtpmap:')) { const m = /^a=rtpmap:(\d+) ([^/]+)\//.exec(line); if (m) out[out.length - 1].codecs.push(m[1] + ' ' + m[2]); }
      else if (line.startsWith('a=candidate:')) out[out.length - 1].cands++;
      else if (line.startsWith('a=fmtp:') && /profile-level-id=/.test(line)) { const m = /^a=fmtp:(\d+) .*profile-level-id=([0-9a-fA-F]+)/.exec(line); if (m) out[out.length - 1].codecs.push(m[1] + ' pl=' + m[2]); }
    }
    return out.map(m => m.media + ': ' + (m.codecs.join(', ') || m.pts) + (m.cands ? ' (' + m.cands + ' candidates)' : '')).join(' | ').slice(0, 500);
  };
  const keep = rec => {
    R.pcs.push(rec);
    if (R.pcs.length <= 8) return;
    const i = R.pcs.findIndex(p => p !== rec && p.state.connection !== 'connected');
    R.pcs.splice(i >= 0 ? i : 0, 1);
  };
  const watch = (pc, config) => {
    pc.__id = ++R.created;
    const rec = {id: pc.__id, t: t(), policy: (config && config.iceTransportPolicy) || 'all', state: {}, sdp: {}, stats: null, tracks: 0, channels: 0,
      servers: ((config && config.iceServers) || []).map(s => [].concat(s.urls || []).map(safeUrl).join(' ')).slice(0, 6)};
    keep(rec);
    const states = {connectionstatechange: () => pc.connectionState, iceconnectionstatechange: () => pc.iceConnectionState,
      icegatheringstatechange: () => pc.iceGatheringState, signalingstatechange: () => pc.signalingState};
    for (const k of Object.keys(states)) pc.addEventListener(k, () => { const v = states[k](); rec.state[k.replace('statechange', '')] = v; ev(pc, k.replace('statechange', ''), v); });
    pc.addEventListener('track', e => { rec.tracks++; ev(pc, 'track', (e.track && e.track.kind) || '?'); });
    pc.addEventListener('datachannel', () => { rec.channels++; ev(pc, 'datachannel', rec.channels); });
    pc.addEventListener('icecandidateerror', e => ev(pc, 'icecandidateerror', (e.errorCode || '') + ' ' + safeUrl(e.url || '') + ' ' + String(e.errorText || '').slice(0, 40)));
    const create = pc.createDataChannel.bind(pc);
    pc.createDataChannel = (...a) => { rec.channels++; return create(...a); };
    for (const name of ['setLocalDescription', 'setRemoteDescription']) {
      const orig = pc[name].bind(pc), side = name === 'setLocalDescription' ? 'local' : 'remote';
      pc[name] = async (...a) => {
        const r = await orig(...a);
        try { const d = side === 'local' ? pc.localDescription : pc.remoteDescription; if (d && d.sdp) { rec.sdp[side] = sdpSummary(d.sdp); rec.sdp[side + '_type'] = d.type; ev(pc, 'sdp-' + side, d.type); } } catch (e) {}
        return r;
      };
    }
    const poll = async () => {
      if (pc.connectionState === 'closed') { rec.state.connection = 'closed'; return; }
      try {
        const st = await pc.getStats(), byId = {}, s = {t: t()};
        st.forEach(r => { byId[r.id] = r; });
        st.forEach(r => {
          if (r.type === 'inbound-rtp' && (r.kind || r.mediaType) === 'video') {
            const codec = r.codecId && byId[r.codecId];
            Object.assign(s, {bytes: r.bytesReceived, packets: r.packetsReceived, lost: r.packetsLost, jitter: r.jitter, frames_received: r.framesReceived,
              frames_decoded: r.framesDecoded, frames_dropped: r.framesDropped, fps: r.framesPerSecond, w: r.frameWidth, h: r.frameHeight,
              decoder: r.decoderImplementation, hw: r.powerEfficientDecoder, keyframes: r.keyFramesDecoded, pli: r.pliCount, nack: r.nackCount, freeze: r.freezeCount,
              codec: codec ? String(codec.mimeType) + ' ' + String(codec.sdpFmtpLine || '').replace(/.*profile-level-id=([0-9a-fA-F]+).*/, 'pl=$1').slice(0, 40) : undefined});
          } else if (r.type === 'inbound-rtp') { s.audio_bytes = r.bytesReceived; }
          else if (r.type === 'candidate-pair' && (r.nominated || r.state === 'succeeded')) {
            const l = byId[r.localCandidateId] || {}, rm = byId[r.remoteCandidateId] || {};
            s.pair = {state: r.state, nominated: !!r.nominated, local: l.candidateType, remote: rm.candidateType, protocol: l.protocol || rm.protocol, relay: l.relayProtocol, rtt: r.currentRoundTripTime, bytes_in: r.bytesReceived, bytes_out: r.bytesSent};
          } else if (r.type === 'local-candidate') { s.local = s.local || {}; s.local[r.candidateType] = (s.local[r.candidateType] || 0) + 1; }
          else if (r.type === 'remote-candidate') { s.remote = s.remote || {}; s.remote[r.candidateType] = (s.remote[r.candidateType] || 0) + 1; }
          else if (r.type === 'data-channel') { s.dc = s.dc || {}; s.dc[r.state] = (s.dc[r.state] || 0) + 1; s.dc_bytes = (s.dc_bytes || 0) + (r.bytesReceived || 0); }
          else if (r.type === 'transport') { s.dtls = r.dtlsState; s.ice = r.iceState; }
        });
        rec.stats = s;
      } catch (e) { rec.stats_error = String((e && e.message) || e).slice(0, 80); }
      setTimeout(poll, 5000);
    };
    setTimeout(poll, 1000);
  };
  // outbound messages per data channel label and on WebSockets: COUNTS and bytes only (where the input travels)
  R.dc_out = {}; R.ws_out = {n: 0, bytes: 0};
  const utf8 = typeof TextEncoder === 'function' ? new TextEncoder() : null;
  const size = d => { try { return typeof d === 'string' ? (utf8 ? utf8.encode(d).byteLength : d.length) : ((d && (d.byteLength !== undefined ? d.byteLength : d.size)) || 0); } catch (e) { return 0; } };
  const hookSends = win => {   // counted after the native send returned (a refused send is not outbound)
    try {
      const P = win.RTCDataChannel && win.RTCDataChannel.prototype;
      if (P && !P.send.__sub01) {
        const send = P.send, w = function (data) {
          const r = send.apply(this, arguments);
          try {   // own properties only: a label such as "__proto__" or "toString" must not reach Object.prototype
            const k = String(this.label || '?').slice(0, 24);
            let o = Object.prototype.hasOwnProperty.call(R.dc_out, k) ? R.dc_out[k] : null;
            if (!o && Object.keys(R.dc_out).length < 12) Object.defineProperty(R.dc_out, k, {value: o = {n: 0, bytes: 0}, enumerable: true, writable: true, configurable: true});
            if (o) { o.n++; o.bytes += size(data); }
          } catch (e) {}
          return r;
        };
        w.__sub01 = true; P.send = w;
      }
      const W = win.WebSocket && win.WebSocket.prototype;
      if (W && !W.send.__sub01) {
        const send = W.send, w = function (data) { const r = send.apply(this, arguments); R.ws_out.n++; R.ws_out.bytes += size(data); return r; };
        w.__sub01 = true; W.send = w;
      }
    } catch (e) {}
  };
  const install = win => {
    hookSends(win);
    let Native;
    try { Native = win.RTCPeerConnection; if (typeof Native !== 'function' || Native.__sub01) return; } catch (e) { return; }
    function Wrapped(config, ...rest) { const pc = new Native(config, ...rest); watch(pc, config); return pc; }
    Wrapped.__sub01 = true;
    Wrapped.prototype = Native.prototype;
    try { Object.setPrototypeOf(Wrapped, Native); } catch (e) {}
    if (Native.generateCertificate) Wrapped.generateCertificate = Native.generateCertificate.bind(Native);
    win.RTCPeerConnection = Wrapped;
    try { if (win.webkitRTCPeerConnection) win.webkitRTCPeerConnection = Wrapped; } catch (e) {}
  };
  install(window);
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    R.media.play++;
    const p = play.apply(this, arguments);
    if (p && p.catch) p.catch(e => { R.media.rejected.push(String((e && e.name) || e).slice(0, 40)); if (R.media.rejected.length > 10) R.media.rejected.shift(); });
    return p;
  };
})();"""
# Init script (vagon mode, every frame): the input path's facts, as COUNTS only (never a key, a character or a position):
# which targets the page's own code listens on for keyboard/mouse/wheel events (window, document, the video, a layer...),
# how many key/mouse/wheel events reached the window (capture phase) and their last target, how many of them came back to
# the window's bubble phase (the rest were stopped by the player) and how many the page prevented, pointer-lock requests
# and changes, navigator.keyboard.lock() calls. Read back by VAGON_DIAG_JS as window.__sub01Input.
INPUT_INIT_JS = r"""(() => {
  if (window.__sub01Input) return;
  const I = window.__sub01Input = {key: {down: 0, up: 0, bubbled: 0, prevented: 0, target: null}, mouse: {down: 0, up: 0, move: 0, bubbled: 0, prevented: 0, target: null},
    wheel: {n: 0, bubbled: 0, prevented: 0, target: null}, listeners: {}, lock: {requests: 0, changes: 0, errors: 0, held: false, by: null}, kbd_lock: 0};
  const name = t => { try { return t === window ? 'window' : t === document ? 'document' : (t && t.tagName ? t.tagName.toLowerCase() + (t.id ? '#' + String(t.id).slice(0, 24) : '') : '?'); } catch (e) { return '?'; } };
  const WATCH = new Set(['keydown', 'keyup', 'keypress', 'mousedown', 'mouseup', 'mousemove', 'pointerdown', 'pointerup', 'pointermove', 'wheel', 'click', 'contextmenu']);
  const add = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type) {
    try { if (WATCH.has(type)) { const k = name(this) + ':' + type; if (k in I.listeners || Object.keys(I.listeners).length < 40) I.listeners[k] = (I.listeners[k] || 0) + 1; } } catch (e) {}
    return add.apply(this, arguments);
  };
  for (const [type, slot, field] of [['keydown', 'key', 'down'], ['keyup', 'key', 'up'], ['mousedown', 'mouse', 'down'], ['mouseup', 'mouse', 'up'], ['wheel', 'wheel', 'n']]) {
    add.call(window, type, e => { I[slot][field]++; I[slot].target = name(e.target); }, true);
    add.call(window, type, e => { if (field !== 'up') { I[slot].bubbled++; if (e.defaultPrevented) I[slot].prevented++; } }, false);
  }
  add.call(window, 'mousemove', () => { I.mouse.move++; }, {capture: true, passive: true});
  try {
    const rpl = Element.prototype.requestPointerLock;
    if (rpl) Element.prototype.requestPointerLock = function () {
      I.lock.requests++; I.lock.by = name(this);
      try { const p = rpl.apply(this, arguments); if (p && p.catch) p.catch(() => { I.lock.errors++; }); return p; } catch (e) { I.lock.errors++; throw e; }
    };
  } catch (e) {}
  add.call(document, 'pointerlockchange', () => { I.lock.changes++; I.lock.held = !!document.pointerLockElement; }, true);
  add.call(document, 'pointerlockerror', () => { I.lock.errors++; }, true);
  I.fullscreen_changes = 0;
  add.call(document, 'fullscreenchange', () => { I.fullscreen_changes++; }, true);
  try { if (navigator.keyboard && navigator.keyboard.lock) { const kl = navigator.keyboard.lock.bind(navigator.keyboard); navigator.keyboard.lock = (...a) => { I.kbd_lock++; return kl(...a); }; } } catch (e) {}
})();"""
# One frame's diagnostic snapshot (async: WebCodecs support is a promise): where it is, its iframes (hosts), video and
# canvas elements, WebGL (context kind and renderer), WebCodecs/WebGPU, the codecs this browser can receive/decode, the
# WebRTC records of RTC_INIT_JS, user activation. No URL beyond host and path, no page text.
VAGON_DIAG_JS = r"""async () => {
  const out = {host: location.hostname, path: location.pathname.slice(0, 80), title: (document.title || '').slice(0, 80), ready: document.readyState,
    visible: document.visibilityState, focus: document.hasFocus(), vw: innerWidth, vh: innerHeight, iframes: [], videos: [], canvases: []};
  for (const f of document.querySelectorAll('iframe')) {
    let h = ''; try { h = new URL(f.src || 'about:blank', location.href).hostname || (f.src || 'about:blank').slice(0, 30); } catch (e) { h = '?'; }
    const r = f.getBoundingClientRect();
    out.iframes.push({host: h, name: (f.name || f.id || f.className || '').toString().slice(0, 40), w: Math.round(r.width), h: Math.round(r.height)});
    if (out.iframes.length >= 12) break;
  }
  for (const v of document.querySelectorAll('video')) {
    const r = v.getBoundingClientRect(); let q = null; try { q = v.getVideoPlaybackQuality(); } catch (e) {}
    const tracks = v.srcObject && v.srcObject.getTracks ? v.srcObject.getTracks().map(t => t.kind + ':' + t.readyState + (t.muted ? ':muted' : '')).join(' ') : '';
    out.videos.push({w: Math.round(r.width), h: Math.round(r.height), ready: v.readyState, vw: v.videoWidth, vh: v.videoHeight, paused: v.paused, muted: v.muted,
      autoplay: v.autoplay, t: Math.round(v.currentTime * 10) / 10, src_object: !!v.srcObject, src: v.src ? v.src.split(':')[0] : '', tracks,
      frames: q ? q.totalVideoFrames : null, dropped: q ? q.droppedVideoFrames : null, error: v.error ? v.error.code : null, display: getComputedStyle(v).display});
    if (out.videos.length >= 6) break;
  }
  for (const c of document.querySelectorAll('canvas')) {
    const r = c.getBoundingClientRect();
    out.canvases.push({w: Math.round(r.width), h: Math.round(r.height), cw: c.width, ch: c.height, display: getComputedStyle(c).display});
    if (out.canvases.length >= 8) break;
  }
  try {
    const c = document.createElement('canvas'); let gl = null, kind = null;
    for (const n of ['webgl2', 'webgl']) { try { gl = c.getContext(n); } catch (e) {} if (gl) { kind = n; break; } }
    out.webgl = kind;
    if (gl) { const d = gl.getExtension('WEBGL_debug_renderer_info'); out.renderer = String(d ? gl.getParameter(d.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)).slice(0, 100); const lose = gl.getExtension('WEBGL_lose_context'); if (lose) lose.loseContext(); }
  } catch (e) { out.webgl = 'error'; }
  out.webcodecs = 'VideoDecoder' in window; out.webgpu = 'gpu' in navigator; out.codecs = {};
  try { out.codecs.rtc_video = (RTCRtpReceiver.getCapabilities('video').codecs || []).map(c => c.mimeType.replace('video/', '')).filter((v, i, a) => a.indexOf(v) === i && !['rtx', 'red', 'ulpfec', 'flexfec-03'].includes(v)); } catch (e) { out.codecs.rtc_video = 'n/a'; }
  try { out.codecs.mse_h264 = MediaSource.isTypeSupported('video/mp4; codecs="avc1.42E01E"'); out.codecs.mse_vp9 = MediaSource.isTypeSupported('video/webm; codecs="vp09.00.10.08"'); out.codecs.mse_av1 = MediaSource.isTypeSupported('video/mp4; codecs="av01.0.04M.08"'); } catch (e) {}
  if (out.webcodecs) for (const [k, c] of Object.entries({h264: 'avc1.42E01E', vp9: 'vp09.00.10.08', av1: 'av01.0.04M.08'})) { try { out.codecs['vd_' + k] = (await VideoDecoder.isConfigSupported({codec: c, codedWidth: 1920, codedHeight: 1080})).supported; } catch (e) { out.codecs['vd_' + k] = 'error'; } }
  const R = window.__sub01Rtc;
  out.rtc = R ? {created: R.created, pcs: R.pcs.map(p => ({id: p.id, policy: p.policy, servers: p.servers, state: p.state, sdp: p.sdp, tracks: p.tracks, channels: p.channels, stats: p.stats, error: p.stats_error})),
    events: R.events.slice(-30), media: R.media, dc_out: R.dc_out || null, ws_out: R.ws_out || null} : null;
  out.ua = navigator.userAgent.slice(0, 120); out.pointer_lock = 'requestPointerLock' in Element.prototype;
  out.activation = navigator.userActivation ? {active: navigator.userActivation.isActive, been: navigator.userActivation.hasBeenActive} : null;
  // the input path: what has the keyboard focus, what sits over the stream's centre and top edge (overlays, prompts);
  // element summaries carry only the page author's aria-label/title, never innerText (no typed or page text)
  const brief = el => el ? {tag: el.tagName.toLowerCase(), id: (el.id || '').slice(0, 40), cls: (typeof el.className === 'string' ? el.className : '').slice(0, 60),
    text: (el.getAttribute('aria-label') || el.title || '').replace(/\s+/g, ' ').trim().slice(0, 40), tabindex: el.getAttribute('tabindex')} : null;
  out.input = {active: brief(document.activeElement), locked: !!document.pointerLockElement, fullscreen: !!document.fullscreenElement,
    at_centre: brief(document.elementFromPoint(innerWidth / 2, innerHeight / 2)), at_top: brief(document.elementFromPoint(innerWidth / 2, 6)),
    at_bottom: brief(document.elementFromPoint(innerWidth / 2, innerHeight - 24)), hooks: window.__sub01Input || null,
    keyboard_lock: !!(navigator.keyboard && navigator.keyboard.lock), selection: (() => { try { return getSelection().type; } catch (e) { return null; } })()};
  // what covers the largest video at a 5x4 grid of points: the video itself, or which element (with its background) sits on top
  let big = null, area = 0;
  for (const v of document.querySelectorAll('video, canvas')) { const r = v.getBoundingClientRect(); if (r.width * r.height > area) { area = r.width * r.height; big = v; } }
  if (big && area > 0) {
    const r = big.getBoundingClientRect(), cover = {};
    for (let i = 0; i < 5; i++) for (let j = 0; j < 4; j++) {
      const el = document.elementFromPoint(r.left + r.width * (i + 0.5) / 5, r.top + r.height * (j + 0.5) / 4);
      const key = !el ? 'none' : el === big ? 'stream' : (() => { const b = brief(el), cs = getComputedStyle(el); return b.tag + (b.id ? '#' + b.id : '') + (b.cls ? '.' + b.cls.split(/\s+/)[0] : '') + ' bg=' + cs.backgroundColor + ' op=' + cs.opacity; })();
      cover[key] = (cover[key] || 0) + 1;
    }
    out.input.cover = cover;
    out.input.stream_pointer_events = getComputedStyle(big).pointerEvents;
  }
  return out;
}"""
# What a click (or the wheel, or the hover before keys) at (x, y) of the stream page would hit. ok only when the top
# element at the point is the stream element itself (the largest video/canvas; on Vagon `video#player`, which carries the
# player's mouse/wheel/pointer listeners) or inside it. Anything else is the host page's and is never pressed: the
# toolbar handle ("Click to Open") or its menu (Power, Display settings, Files...), a dialog, a dim/backdrop layer, a
# container or a transparent layer of unknown purpose. `why` says which, for the `blocked` event.
VAGON_HIT_JS = r"""([x, y, minW, minH]) => {
  const el = document.elementFromPoint(x, y);
  const brief = e => ({tag: e.tagName.toLowerCase(), id: (e.id || '').slice(0, 40), cls: (typeof e.className === 'string' ? e.className : '').slice(0, 60),
    text: (e.getAttribute('aria-label') || e.title || '').replace(/\s+/g, ' ').trim().slice(0, 40)});
  if (!el) return {ok: false, why: 'nothing at that point'};
  const out = brief(el);
  let stream = null, area = 0;
  for (const c of document.querySelectorAll('video, canvas')) {
    const r = c.getBoundingClientRect();
    if (r.width >= minW && r.height >= minH && r.width * r.height > area) { area = r.width * r.height; stream = c; }
  }
  if (!stream) return Object.assign(out, {ok: false, why: 'no stream element'});
  const r = stream.getBoundingClientRect();
  if (x < r.left || x > r.right || y < r.top || y > r.bottom) return Object.assign(out, {ok: false, why: 'outside the stream'});
  if (el === stream || stream.contains(el)) return Object.assign(out, {ok: true, how: 'stream'});
  const CONTROL = 'button, a[href], input, select, textarea, label, summary, [role=button], [role=link], [role=menu], [role=menuitem], [role=dialog], [role=alertdialog], [role=tooltip], dialog, [aria-modal=true], [contenteditable=""], [contenteditable=true]';
  if (el.closest(CONTROL)) return Object.assign(out, {ok: false, why: 'host control'});
  const clear = (e, pseudo) => {
    const cs = getComputedStyle(e, pseudo || null);
    if (pseudo && (cs.content === 'none' || cs.content === 'normal' || cs.display === 'none')) return true;
    const bg = cs.backgroundColor, m = /^rgba\([^)]*,\s*([\d.]+)\)$/.exec(bg);
    const alpha = bg === 'transparent' ? 0 : m ? Number(m[1]) : 1;    // rgb(...) or an unknown format: it paints
    return alpha === 0 && cs.backgroundImage === 'none' && (!cs.backdropFilter || cs.backdropFilter === 'none') && cs.visibility !== 'hidden';
  };
  if (el.contains(stream)) return Object.assign(out, {ok: false, why: 'a container of the stream (the stream itself is not under the point)'});
  const er = el.getBoundingClientRect();
  const covers = er.left <= r.left + 4 && er.top <= r.top + 4 && er.right >= r.right - 4 && er.bottom >= r.bottom - 4;
  const paints = !(clear(el) && clear(el, '::before') && clear(el, '::after'));
  return Object.assign(out, {ok: false, why: covers ? (paints ? 'a layer that paints over the stream (dim/backdrop)' : 'a transparent layer over the stream')
    : 'a host-page element over the stream'});
}"""


# The operator console (GET /operator): one self-contained page, no external asset, every URL relative to its own
# location so it works behind a path prefix (the pod's Jupyter proxy: .../proxy/8832/operator). The owner pastes the
# admin token once (sessionStorage of this tab, sent as X-Admin-Token); the live desktop is polled at 2 fps from
# operator/frame.jpg; mouse and keyboard go to operator/input. Nothing typed here is logged by the runner.
OPERATOR_UNAVAILABLE = ("The operator console is served only while the Vagon workstation is not connected (phases "
                        "login_required, dashboard, starting, connecting, ended, blocked) or when the runner runs with "
                        "--operator-console.")
OPERATOR_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SUB-01 PC operator console</title>
<style>
  html, body { margin: 0; background: #16181c; color: #e6e6e6; font: 14px/1.4 system-ui, sans-serif; }
  header { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; padding: 8px 12px; background: #23262c; }
  header strong { margin-right: 6px; }
  input[type=password] { width: 260px; background: #111; color: #eee; border: 1px solid #555; padding: 4px 6px; }
  button { background: #3b7ddd; color: #fff; border: 0; padding: 5px 12px; border-radius: 4px; cursor: pointer; }
  button.quiet { background: #444; }
  #phase { font-family: ui-monospace, monospace; color: #9ecbff; }
  #stage { position: relative; margin: 10px auto; max-width: 1600px; }
  #screen { display: block; width: 100%; background: #000; cursor: crosshair; user-select: none; -webkit-user-drag: none; }
  #sink { position: absolute; left: 0; top: 0; width: 1px; height: 1px; opacity: 0.01; resize: none; border: 0; }
  #hint, #status { margin: 6px 12px; color: #aaa; }
  #status.bad { color: #ff9e9e; }
</style>
</head>
<body>
<header>
  <strong>SUB-01 PC &middot; operator console</strong>
  <span>phase: <span id="phase">…</span></span>
  <input id="token" type="password" placeholder="paste the operator token" autocomplete="off" spellcheck="false">
  <button id="save" type="button">Use token</button>
  <button id="forget" type="button" class="quiet">Forget token</button>
  <label><input id="keys" type="checkbox" checked> keyboard goes to the PC</label>
</header>
<p id="hint">The token is the content of /home/unreal/.sub01-private/operator-token on the pod; it stays in this browser tab
(sessionStorage) and is sent as X-Admin-Token. Click the picture, then type: letters, Tab, Enter, Backspace, arrows and
Ctrl+V (paste) go to the kiosk browser on the pod. The runner logs none of it. Log in on the Vagon page you see; the console
closes by itself a few minutes after the login page is gone.</p>
<div id="stage"><img id="screen" alt="the pod's desktop" draggable="false"><textarea id="sink" aria-label="keyboard"></textarea></div>
<p id="status"></p>
<script>
(() => {
  // relative to this page: ".../proxy/8832/operator" -> ".../proxy/8832/"; never an absolute path
  const base = location.pathname.replace(/\/operator\/?$/, '/');
  const STORE = 'sub01-operator-token';
  const $ = id => document.getElementById(id);
  const img = $('screen'), sink = $('sink'), status = $('status'), phase = $('phase');
  let token = '';
  try { token = sessionStorage.getItem(STORE) || ''; } catch (e) {}
  let etag = '', buttons = [false, false, false], lastMove = 0, lastSent = '', frameTimer = 0, stateTimer = 0;
  const headers = extra => Object.assign({'X-Admin-Token': token}, extra || {});
  const say = (text, bad) => { status.textContent = text; status.className = bad ? 'bad' : ''; };
  $('save').addEventListener('click', () => {
    token = $('token').value.trim(); $('token').value = '';
    try { sessionStorage.setItem(STORE, token); } catch (e) {}
    etag = ''; say(token ? 'token stored for this tab' : 'no token'); frame(); state();
  });
  $('forget').addEventListener('click', () => { token = ''; try { sessionStorage.removeItem(STORE); } catch (e) {} say('token forgotten'); });
  async function frame() {
    clearTimeout(frameTimer);
    if (!token) { say('paste the operator token first', true); frameTimer = setTimeout(frame, 1000); return; }
    try {
      const h = headers(); if (etag) h['If-None-Match'] = etag;
      const r = await fetch(base + 'operator/frame.jpg', {headers: h, cache: 'no-store'});
      if (r.status === 304) { /* unchanged */ }
      else if (r.status === 403) say('the token was refused', true);
      else if (r.status === 404) say(await r.text(), true);
      else if (r.status === 409) say('bathroom privacy is active: nothing is shown', true);
      else if (r.ok) {
        etag = r.headers.get('ETag') || '';
        const url = URL.createObjectURL(await r.blob()), old = img.src;
        img.onload = () => { if (old && old.startsWith('blob:')) URL.revokeObjectURL(old); };
        img.src = url;
        if (status.className === 'bad') say('');
      } else say('frame: HTTP ' + r.status, true);
    } catch (e) { say('frame: ' + e.message, true); }
    frameTimer = setTimeout(frame, 500);
  }
  async function state() {
    clearTimeout(stateTimer);
    if (token) {
      try {
        const r = await fetch(base + 'pc/state', {headers: headers(), cache: 'no-store'});
        if (r.ok) {
          const s = await r.json(), v = s.vagon || {};
          phase.textContent = (v.phase || s.status || '?') + (v.kind === 'workstation' ? ' · logged_in=' + v.logged_in + ' · machine=' + v.machine : '')
            + (v.operator_console === false ? ' · console closing' : '');
        }
      } catch (e) {}
    }
    stateTimer = setTimeout(state, 2000);
  }
  const OPERATOR_GONE = 'the console is no longer served (the login page is gone)';
  function send(body) {
    if (!token) return Promise.resolve();
    return fetch(base + 'operator/input', {method: 'POST', headers: headers({'Content-Type': 'application/json'}), body: JSON.stringify(body), cache: 'no-store'})
      .then(r => { if (r.status === 403) say('the token was refused', true); else if (r.status === 404) say(OPERATOR_GONE, true); })
      .catch(() => {});
  }
  const clamp = v => Math.min(1, Math.max(0, v));
  function frac(e) { const r = img.getBoundingClientRect(); return {x: clamp((e.clientX - r.left) / Math.max(1, r.width)), y: clamp((e.clientY - r.top) / Math.max(1, r.height))}; }
  img.addEventListener('mousemove', e => {
    const now = performance.now(); if (now - lastMove < 40) return; lastMove = now;
    const p = frac(e), key = p.x.toFixed(4) + ',' + p.y.toFixed(4); if (key === lastSent) return; lastSent = key;
    send({type: 'mouse', x: p.x, y: p.y});
  });
  img.addEventListener('mousedown', e => {
    e.preventDefault(); sink.focus({preventScroll: true});
    if (e.button >= 0 && e.button <= 2) buttons[e.button] = true;
    const p = frac(e); send({type: 'mouse', x: p.x, y: p.y, buttons: buttons.slice()});
  });
  window.addEventListener('mouseup', e => {
    if (!(e.button >= 0 && e.button <= 2) || !buttons[e.button]) return;
    buttons[e.button] = false;
    const p = frac(e); send({type: 'mouse', x: p.x, y: p.y, buttons: buttons.slice()});
  });
  img.addEventListener('contextmenu', e => e.preventDefault());
  img.addEventListener('wheel', e => { e.preventDefault(); const p = frac(e); send({type: 'mouse', x: p.x, y: p.y, wheel: Math.max(-600, Math.min(600, e.deltaY))}); }, {passive: false});
  const MODS = {ShiftLeft: 1, ShiftRight: 1, ControlLeft: 1, ControlRight: 1, AltLeft: 1, AltRight: 1, MetaLeft: 1, MetaRight: 1};
  const held = new Set();
  const printable = e => e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey;
  const pasteCombo = e => (e.ctrlKey || e.metaKey) && !e.altKey && e.code === 'KeyV';
  const copyCombo = e => (e.ctrlKey || e.metaKey) && (e.code === 'KeyC' || e.code === 'KeyX');
  sink.addEventListener('keydown', e => {
    if (!$('keys').checked) return;
    if (pasteCombo(e)) return;                       // let the browser raise the paste event below
    e.preventDefault();
    if (printable(e)) { send({type: 'text', text: e.key}); return; }   // layout-independent: the character itself
    if (copyCombo(e) || !e.code) return;             // nothing to copy from here
    if (MODS[e.code]) held.add(e.code);
    send({type: 'key', key: e.code, down: true});
  });
  sink.addEventListener('keyup', e => {
    if (!$('keys').checked || pasteCombo(e)) return;
    e.preventDefault();
    if (printable(e) || copyCombo(e) || !e.code) return;
    held.delete(e.code);
    send({type: 'key', key: e.code, down: false});
  });
  sink.addEventListener('paste', e => {
    e.preventDefault();
    const cd = e.clipboardData || window.clipboardData;
    const text = cd && cd.getData ? (cd.getData('text') || '') : '';
    if (text) send({type: 'text', text: text.slice(0, 2000)});
  });
  sink.addEventListener('input', () => { sink.value = ''; });
  window.addEventListener('blur', () => { for (const m of held) send({type: 'key', key: m, down: false}); held.clear(); });
  if (!token) $('token').focus();
  frame(); state();
})();
</script>
</body>
</html>
"""


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
        self.vagon = VagonState(api_key_file_status(cfg.vagon_api_key_file), cfg.vagon_kind)   # /pc/state "vagon" (vagon mode only)
        self.vagon.autostart = bool(getattr(cfg, "vagon_autostart", False))
        self._vagon_task, self._vagon_frame, self._vagon_offset = None, None, (0.0, 0.0)
        self._vagon_next_diag = 0.0                       # connected: when the next periodic diag is due (monotonic)
        self._vagon_lock = asyncio.Lock()                 # the connect loop never presses a button during an action
        self.api, self._api_task, self._api_logged = None, None, None   # workstation: the optional Teams API (VagonApi), set by serve()
        self._operator, self._neutral = (0, None), None   # (sequence, latest raw screencast JPEG) for the owner's console
        self._net, self._counts, self._ws_hosts = {"request": time.monotonic()}, {}, set()   # network activity: page_dead, the diag
        self._console, self._failed, self._http_errors = deque(maxlen=12), {}, {}
        self._rtc_bytes, self._probe_seq, self.browser_version = 0, 0, ""
        self._pages, self._attached = [], set()           # workstation: the dashboard page behind an adopted stream window

    @property
    def vagon_mode(self):
        return self.cfg.pc_mode == "vagon"

    @property
    def workstation(self):
        return self.vagon_mode and self.cfg.vagon_kind == "workstation"

    def operator_allowed(self):
        """The owner's console is served with --operator-console, or in the workstation kind the whole time the remote
        desktop is NOT connected (login_required, dashboard, starting, connecting, ended, blocked, blank...) and for
        OPERATOR_CONNECTED_GRACE_S after it connected (a flapping session). It closes only while the desktop is connected;
        the console closing is never what makes the desktop count as connected (that needs stream_evidence)."""
        if self.cfg.operator_console:
            return True
        if not self.workstation:
            return False
        v = self.vagon
        if not v.connected:
            return True
        return v.connected_at is not None and time.monotonic() - v.connected_at < OPERATOR_CONNECTED_GRACE_S

    def privacy_locked(self):
        """Workstation kind: until the remote desktop is connected nothing but a neutral picture leaves the runner
        through /pc/frame.png and /desktop/observe (the login page and the account pages are the owner's)."""
        return self.workstation and not self.vagon.connected

    def _neutral_pair(self):
        if self._neutral is None:
            jpeg = neutral_jpeg(SMALL)
            self._neutral = (jpeg, render_frame(jpeg, SMALL))
        return self._neutral

    def _lock_feed(self):
        """Publish the neutral frame now (the screencast only sends frames when the page changes)."""
        if self.privacy_locked() and self.feed.publish(*self._neutral_pair()):
            self.on_change()

    def operator_frame(self):
        """(tag, raw JPEG of the latest screencast frame) for the owner's console, or None before the first frame."""
        seq, jpeg = self._operator
        return (f"op-{seq:x}", jpeg) if jpeg else None

    # lifecycle
    def start(self):
        self._wake, self._frame_event, self._input_lock = asyncio.Event(), asyncio.Event(), asyncio.Lock()
        self._task = asyncio.create_task(self._supervise())
        self._publisher_task = asyncio.create_task(self._publisher())
        if self.vagon_mode:
            self._vagon_task = asyncio.create_task(self._vagon_loop())
        if self.workstation and self.api is not None:
            self._api_task = asyncio.create_task(self._api_loop())

    async def close(self):
        self.stopping = True
        if self._wake:
            self._wake.set()
        for task in (self._task, self._publisher_task, self._vagon_task, self._api_task):
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
        pulse = pulse_socket(os.environ.get("STREAMER_DIR") or cfg.profile.parent.parent)   # probed at every launch
        if pulse:
            log(f"browser audio: on, into {PULSE_SINK} ({pulse})")
        options = {"headless": cfg.headless, "args": chromium_args(cfg, pulse), "env": chromium_env(cfg.display, pulse=pulse),
                   "accept_downloads": False, "service_workers": "block", "locale": "en-US", "permissions": [],
                   "ignore_default_args": ["--enable-automation"]}
        options.update({"viewport": {"width": cfg.width, "height": cfg.height}} if cfg.headless else {"no_viewport": True})
        if cfg.chromium:
            options["executable_path"] = cfg.chromium
        if cfg.proxy:
            options["proxy"] = {"server": cfg.proxy}
        self.ctx = await self.pw.chromium.launch_persistent_context(str(cfg.profile), **options)
        await self.ctx.add_init_script(CLIPBOARD_JS)
        if self.vagon_mode:
            await self.ctx.add_init_script(RTC_INIT_JS)       # WebRTC/media diagnostics (window.__sub01Rtc) in every frame
            await self.ctx.add_init_script(INPUT_INIT_JS)     # the input path's counters (window.__sub01Input) in every frame
        await self.ctx.route("**/*", self._route)
        self.page = self.ctx.pages[0] if self.ctx.pages else await self.ctx.new_page()
        for extra in self.ctx.pages[1:]:
            await extra.close()
        try:
            self.browser_version = str(self.ctx.browser.version) if self.ctx.browser else ""
        except Exception:
            self.browser_version = ""
        self._net, self._counts, self._ws_hosts = {"request": time.monotonic()}, {}, set()
        self._console.clear()
        self._failed, self._http_errors, self._rtc_bytes, self._pages, self._attached = {}, {}, 0, [], set()
        self.ctx.on("page", self._on_new_page)
        self.ctx.on("request", lambda r: self._activity("request"))
        self.ctx.on("response", self._on_response)
        self.ctx.on("close", lambda *_: self._request_restart("browser closed"))
        page = self.page
        await self._attach_page(page)
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

    async def _attach_page(self, page):
        """Listeners and the screencast for the page the runner watches: the first page, or an adopted stream window
        (workstation). Listeners are registered once per page; the CDP screencast follows the current page."""
        cfg = self.cfg
        if id(page) not in self._attached:
            self._attached.add(id(page))
            page.on("dialog", self._on_dialog)
            page.on("framenavigated", self._on_navigated)
            page.on("crash", lambda *_: self._request_restart("page crashed") if page is self.page else None)
            page.on("close", lambda *_: self._on_page_closed(page))
            page.on("download", lambda d: self._refused("download", d.url))
            page.on("filechooser", lambda fc: self._refused("file chooser", ""))
            page.on("console", self._on_console)
            page.on("pageerror", lambda e: self._note_console("pageerror", str(e)))
            page.on("requestfailed", self._on_request_failed)
            page.on("websocket", self._on_websocket)
        self.cdp = await self.ctx.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 80, "maxWidth": cfg.width,
                                                     "maxHeight": cfg.height, "everyNthFrame": 1})

    def _on_page_closed(self, page):
        """The watched page closed: in the workstation kind the dashboard page behind an adopted stream window takes
        over (the session may offer Connect again); otherwise the browser is relaunched."""
        if page is not self.page or self._tearing or self.stopping:
            return
        fallback = None
        if self.workstation:
            fallback = next((p for p in reversed(self._pages) if not p.is_closed()), None)
            self._pages = [p for p in self._pages if p is not fallback and not p.is_closed()]
        if fallback is not None:
            asyncio.ensure_future(self._adopt(fallback, "the stream window closed; back to the"))
        else:
            self._request_restart("page closed")

    async def _adopt(self, page, why):
        """Workstation: `page` becomes the page the runner watches, screencasts and drives. The previous page stays open
        behind it (the dashboard tab keeps the session) and is the fallback when the adopted window closes."""
        old = self.page
        if self.cdp is not None:
            for step in (self.cdp.send("Page.stopScreencast"), self.cdp.detach()):
                try:
                    await asyncio.wait_for(step, 3)
                except Exception:
                    pass
        self.page, self.cdp, self._vagon_frame, self._vagon_offset = page, None, None, (0.0, 0.0)
        if old is not None and old is not page and not old.is_closed() and old not in self._pages:
            self._pages.append(old)
        try:
            await self._attach_page(page)
            await page.bring_to_front()
        except Exception as error:
            log(f"vagon: adopting the {why} window failed: {self._scrub(clean_error(error))}")
            self._request_restart("adopted window unusable")
            return
        self.vagon.misses = 0
        log(f"vagon: now watching the {why} window at {redact_url(page.url)}")
        self.events.append("vagon", state="adopted", why=why, host=redact_url(page.url))
        self.on_change()

    async def _adopt_or_close(self, page):
        """Workstation: a new tab or popup that stays on the Vagon site is the stream window and is adopted as the page
        (never closed, the dashboard stays behind it); any other popup is closed as everywhere else."""
        url = page.url
        if url in ("", "about:blank"):
            try:
                await page.wait_for_url(lambda u: u not in ("", "about:blank"), timeout=4000)
            except Exception:
                pass
            url = page.url
        if url and url != "about:blank" and not url.startswith("chrome-error:") and self._main_blocked(url) is None:
            await self._adopt(page, "popup")
            return
        self.popups.append(url or "")
        log("popup closed")
        self.events.append("blocked", what="popup", url=self._url_for_log(url or ""))
        await self._close_quietly(page)

    async def _teardown(self):
        self._tearing = True
        self.feed.clear()
        self._operator = (self._operator[0], None)
        self._pages, self._attached = [], set()
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
        v.stuck_since, v.reload_requested, v.last_reload_why = time.monotonic(), False, str(why)[:120]
        self._net, self._rtc_bytes = {"request": time.monotonic()}, 0
        v.set_phase("opening" if self.workstation else "starting")
        self._lock_feed()
        self.on_change()
        log(f"vagon: opening the {'workstation' if self.workstation else 'stream'} page ({why}) at {redact_url(self.cfg.vagon_url)}")
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
        best, main, dropped = None, None, []
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
                main = {k: info.get(k) for k in ("url", "title", "text", "passwords", "vw", "vh")}
            else:
                try:
                    box = await (await frame.frame_element()).bounding_box()
                except Exception:
                    box = None
                if not box:
                    continue
                offset = (float(box["x"]), float(box["y"]))
                where = self._frame_origin(frame)
                if self.workstation and self._widget_frame(frame):
                    dropped.append(where)                 # a chat/support widget's frame or a third-party frame: no controls
                    info["buttons"] = []
                else:
                    for b in info.get("buttons") or []:
                        b["frame"] = where
            if best is None:
                best = (info, frame, offset)
            pressable = (choose_workstation_button(info.get("buttons"))[0] if self.workstation
                         else choose_vagon_button(info.get("buttons"))) is not None
            if info.get("stream") or pressable:           # the main document comes first: its controls win over any frame's
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
        info["main"] = main or {k: info.get(k) for k in ("url", "title", "text", "passwords", "vw", "vh")}
        info["dropped_frames"] = dropped
        self._vagon_frame, self._vagon_offset = frame, offset
        return info

    def _frame_origin(self, frame):
        """'host' of a sub-frame for the logs (or its name for a blank frame): never a path or a query."""
        url = str(getattr(frame, "url", "") or "")
        try:
            host = urlsplit(url).hostname
        except ValueError:
            host = None
        return host or str(getattr(frame, "name", "") or "")[:30] or "about:blank"

    def _widget_frame(self, frame):
        """A sub-frame whose controls are never pressed: named like a chat/support/cookie widget (Intercom's
        intercom-messenger-frame, launchers) or served by another site than the configured page's."""
        if VAGON_WS_WIDGET_RX.search(str(getattr(frame, "name", "") or "")):
            return True
        url = str(getattr(frame, "url", "") or "")
        if url in ("", "about:blank") or url.startswith(("data:", "blob:")):
            return False
        try:
            return not same_site(urlsplit(url), urlsplit(self.cfg.vagon_url))
        except ValueError:
            return True

    async def _vagon_focus(self):
        """Keyboard focus on the stream element (or the body), so key events reach the stream client. On the workstation's
        own pages (login form, dashboard) the DOM focus is left where the owner put it."""
        if self.workstation and not self.vagon.connected:
            return False
        frame = self._vagon_frame or getattr(self.page, "main_frame", self.page)
        try:
            return bool(await asyncio.wait_for(frame.evaluate(VAGON_FOCUS_JS, list(VAGON_MIN_STREAM)), 5))
        except Exception:
            return False

    async def _vagon_press(self, button, kind=None):
        v, x, y = self.vagon, button["box"][0] + button["box"][2] / 2, button["box"][1] + button["box"][3] / 2
        label = str(button.get("label") or "")[:40]
        v.last_click, v.attempts, v.last_label = time.monotonic(), v.attempts + 1, label
        log(f"vagon: pressing '{label}' ({kind or 'connect'}, attempt {v.attempts})")
        if self.workstation:
            self.events.append("vagon_button", label=label, button=kind, phase=v.phase, attempt=v.attempts)
        else:
            self.events.append("vagon", state="press", label=label, attempt=v.attempts)
        await self.page.mouse.move(x, y, steps=4)
        await self.page.mouse.click(x, y)

    async def _vagon_step(self):
        async with self._vagon_lock:
            await self._vagon_step_locked()

    def _set_machine(self, state, source):
        """The machine's state for /pc/state: the API reading wins while it is fresh, else what the page shows."""
        v = self.vagon
        if source == "page" and self.api is not None and self.api.fresh():
            return
        if state in ("on", "starting"):
            v.start_held = False                          # the off period is over (whoever started it)
        if (state, source) != (v.machine, v.machine_source):
            v.machine, v.machine_source = state, source
            self.on_change()

    def _hold_start(self, why):
        """The computer is off and starting it is not allowed now (not armed): logged once per off period."""
        v = self.vagon
        if not v.start_held:
            v.start_held = True
            log(f"vagon: the computer is off; not starting it until armed (POST /pc/vagon/arm) or --vagon-autostart ({why})")
            self.events.append("vagon", state="start_held", machine="off", why=why)
            self.on_change()

    def take_start(self, why):
        """One synchronous check-and-consume before any start (page button, API fallback, POST /pc/vagon/start).
        True when this start may happen; otherwise the hold is logged."""
        now = time.monotonic()
        if not self.vagon.start_allowed(now):
            self._hold_start(why)
            return False
        self.vagon.consume_start(now)
        self.events.append("vagon", state="start_taken", why=why, autostart=self.vagon.autostart)
        return True

    async def _vagon_return(self, why):
        """Workstation: back to the configured page after a navigation the lock refused. A refused request may leave the
        page where it was (nothing to do) or commit Chromium's error page; a committed account page is replaced."""
        v = self.vagon
        if v.set_phase("blocked"):
            self.on_change()
        await asyncio.sleep(0.3)
        page = self.page
        if page is None:
            return
        url = page.url
        if url and not url.startswith("chrome-error:") and workstation_request_blocked(url, self.cfg.vagon_url, True, "GET", self.cfg.allow_private) is None:
            return                                        # the kiosk page stayed on an allowed page
        try:
            await self.cdp.send("Page.stopLoading")
        except Exception:
            pass
        try:
            await page.goto(self.cfg.vagon_url, wait_until="commit", timeout=NAV_TIMEOUT_MS)
        except Exception as error:
            log(f"vagon: return to the workstation page failed: {self._scrub(clean_error(error))}")

    def _repainted(self):
        """Did the screencast deliver a new frame since the previous probe (the page drew something)?"""
        seq = self._operator[0]
        changed, self._probe_seq = seq != self._probe_seq, seq
        return changed

    def _page_dead(self, now, probe):
        return page_dead(now, self._net, bool((probe or {}).get("stream")))

    def _log_controls(self, phase, probe):
        """`vagon_controls`: every candidate control of this page state with its verdict, once per distinct set."""
        v = self.vagon
        summary = controls_summary(probe.get("buttons"))
        key = (phase, tuple((s["label"], s["verdict"]) for s in summary), tuple(probe.get("dropped_frames") or []))
        if key != v.last_controls:
            v.last_controls = key
            self.events.append("vagon_controls", phase=phase, controls=summary,
                               dropped_frames=list(probe.get("dropped_frames") or [])[:6])

    async def diag_now(self):
        """A fresh diagnostic snapshot on request (GET /pc/vagon/diag): the stats, the input counters and what covers
        the stream right now; at most one every VAGON_DIAG_MIN_GAP_S (else the latest). Never presses anything."""
        if self.status != "ready" or self.page is None:
            raise DesktopUnavailable(self.status)
        v = self.vagon
        if time.monotonic() - v.last_diag < VAGON_DIAG_MIN_GAP_S:
            return v.diag
        async with self._vagon_lock:
            if time.monotonic() - v.last_diag < VAGON_DIAG_MIN_GAP_S:   # a request that queued behind another one
                return v.diag
            return await self._vagon_diag(v.phase if v.connected else f"{v.phase} (request)", force=True)

    def arm_start(self, minutes, why="operator request"):
        """Allow one start of the owner's computer within `minutes` (POST /pc/vagon/arm). 0 disarms."""
        minutes = max(0.0, min(float(minutes), 120.0))
        self.vagon.start_armed_until = time.monotonic() + minutes * 60.0 if minutes else 0.0
        self.events.append("vagon", state="start_armed" if minutes else "start_disarmed", minutes=minutes, why=why)
        return self.vagon.public()

    def request_reload(self, why="operator request"):
        """The owner asks for the workstation page to be opened again (POST /pc/vagon/reload): the loop does it at
        its next tick. The only reload that needs no evidence of a dead page."""
        self.vagon.reload_requested = True
        self.events.append("vagon", state="reload_requested", why=why)
        return self.vagon.public()

    async def _workstation_step(self, probe, now):
        v = self.vagon
        repaint = self._repainted()
        c = classify_workstation(probe)
        self._log_controls(c["phase"], probe)
        if c["phase"] == "connected" and not v.connected:   # evidence first: pictures, not merely a video/canvas element
            diag = await self._vagon_diag("connected?", force=now - v.last_diag >= 5.0)
            if not stream_evidence(probe.get("stream"), (diag or {}).get("rtc"), repaint):
                c = dict(c, phase="connecting", button=None, kind=None, why="stream element without frames yet")
        phase, idx, kind = c["phase"], c["button"], c["kind"]
        if phase == "connected":
            v.misses, v.blank_since, v.reload_streak, v.stuck_since, v.logged_in = 0, None, 0, None, True
            if not v.connected:
                v.connected, v.sessions, v.attempts, v.connected_at = True, v.sessions + 1, 0, now
                if v.sessions > 1:
                    v.reconnects += 1
                    v.last_reconnect_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
                log(f"vagon: remote desktop connected (session {v.sessions}, reconnects {v.reconnects})")
                self.events.append("vagon", state="connected", session=v.sessions, reconnects=v.reconnects,
                                   evidence={"stream": probe.get("stream"), "repaint": repaint, "rtc": (v.diag or {}).get("rtc")})
                self._set_machine("on", "page")
                if v.set_phase("connected"):
                    self.on_change()
                await self._vagon_diag("connected", force=True)   # fresh: the peer connection's stats, not the pre-connection ones
                self._vagon_next_diag = now + VAGON_DIAG_FOLLOW_S  # again once the stats poll has numbers
                return
            self._set_machine("on", "page")
            if v.set_phase("connected"):
                self.on_change()
            if now >= self._vagon_next_diag:
                await self._vagon_diag("connected", force=True)
                self._vagon_next_diag = now + VAGON_DIAG_CONNECTED_S
            return
        if v.connected:
            v.misses += 1
            if v.misses < VAGON_MISSES and phase in ("connecting", "blank"):
                return                                    # a stalled video or a dropped frame: not an ended session yet
            v.connected = False
            self._lock_feed()
            log(f"vagon: remote session {phase}")
            self.events.append("vagon", state="disconnected", phase=phase)
            await self._vagon_diag(phase, force=True)
            self.on_change()                              # the operator console is available again
        if phase == "login_required":
            v.logged_in, v.login_seen, v.attempts = False, now, 0
            if v.set_phase("login_required"):
                v.login_why = c["why"]
                log(f"vagon: the Vagon page needs the owner's login ({c['why']}); the operator console is at /operator")
                self.events.append("vagon", state="login_required", why=c["why"], host=redact_url(probe.get("url")))
                self.on_change()
            return
        if phase == "blocked":
            v.blocked += 1
            log("vagon: the page is an account page; returning to the workstation page")
            self.events.append("blocked", what="page", reason=c["why"], url=redact_url(probe.get("url")))
            await self._vagon_return(c["why"])
            return
        if phase in ("dashboard", "starting", "connecting", "ended"):
            v.logged_in = True
        if c["machine"] != "unknown":
            self._set_machine(c["machine"], "page")
        if v.set_phase(phase):
            v.stuck_since = now
            self.events.append("vagon", state=phase, machine=v.machine, **({"why": c["why"]} if c.get("why") else {}))
            self.on_change()
        if idx is not None and kind == "start" and not v.start_allowed(time.monotonic()):
            self._hold_start("page start button")         # turning the computer on spends the owner's balance
            return
        if idx is not None and v.attempts < 6:
            if now - v.last_click >= VAGON_CLICK_GAP_S:
                if kind == "start" and not self.take_start("page start button"):
                    return
                await self._vagon_press(probe["buttons"][idx], kind)
            return
        if (idx is None and phase in ("dashboard", "blank") and self.api is not None and self.api.fresh()
                and self.api.machine() == "off" and now - v.last_api_start >= VAGON_API_START_GAP_S):
            if self.take_start("API start (no start button on the page)"):
                v.last_api_start = now
                await self.api_start("no start button on the page")
            return
        if phase in ("connecting", "blank", "starting", "ended"):
            await self._vagon_diag(phase)                 # every VAGON_DIAG_EVERY_S: why the stream is not here yet
        stuck_for = now - v.stuck_since if v.stuck_since is not None else 0.0
        reason = workstation_reload_reason(phase, stuck_for, v.attempts, self._page_dead(now, probe), v.reload_requested)
        if reason and now - v.last_reload >= VAGON_RELOAD_BACKOFF[min(v.reload_streak, len(VAGON_RELOAD_BACKOFF) - 1)]:
            v.reloads, v.reload_streak = v.reloads + 1, v.reload_streak + 1
            await self._vagon_diag(phase, force=True)     # the last picture of the page before it is opened again
            await self._vagon_goto(f"{phase}: {reason} (attempts {v.attempts})")

    def _rtc_summary(self, frames):
        """The peer connection that carries the stream: a live one (connection state `connected`) before any finished
        one, then the one that received most; its frame's host, states, negotiated codecs, servers and stats, with the
        headline numbers (bytes, frames decoded, fps, candidate pair) at the top."""
        best, created, events, live = None, 0, [], 0
        for f in frames:
            rtc = f.get("rtc") if isinstance(f, dict) else None
            if not rtc:
                continue
            created += int(rtc.get("created") or 0)
            for pc in rtc.get("pcs") or []:
                stats = pc.get("stats") or {}
                alive = (pc.get("state") or {}).get("connection") == "connected"
                live += alive
                score = (alive, int(stats.get("bytes") or 0), int(pc.get("tracks") or 0), int(pc.get("id") or 0))
                if best is None or score > best[0]:
                    best, events = (score, f.get("host"), pc, rtc), list(rtc.get("events") or [])[-12:]
        if best is None:
            return {"created": created, "live": 0}
        _, host, pc, rtc = best
        stats = pc.get("stats") or {}
        return {"created": created, "live": live, "host": host, "id": pc.get("id"),
                "dc_out": rtc.get("dc_out"), "ws_out": rtc.get("ws_out"),
                "policy": pc.get("policy"), "servers": pc.get("servers"), "state": pc.get("state"), "sdp": pc.get("sdp"),
                "tracks": pc.get("tracks"), "channels": pc.get("channels"), "stats": stats, "error": pc.get("error"),
                "bytes": int(stats.get("bytes") or 0), "frames_decoded": int(stats.get("frames_decoded") or 0),
                "fps": stats.get("fps"), "pair": stats.get("pair"), "events": events}

    async def _vagon_diag(self, phase, force=False):
        """The diagnostic snapshot (module docstring): VAGON_DIAG_JS in the main frame and up to six sub-frames, the
        WebRTC records of RTC_INIT_JS, and what the runner saw on the network (requests, WebSockets, failed requests,
        HTTP errors, console errors). Kept in vagon.diag (/pc/state) and appended as a `vagon_diag` row, at most every
        VAGON_DIAG_EVERY_S unless forced. Returns the diag, or the previous one when it is too early."""
        v, now = self.vagon, time.monotonic()
        if not force and now - v.last_diag < VAGON_DIAG_EVERY_S:
            return v.diag
        v.last_diag = now
        page, frames = self.page, []
        main_frame = getattr(page, "main_frame", None)
        others = [f for f in (getattr(page, "frames", None) or []) if f is not main_frame][:6]
        for frame in ([main_frame] if main_frame is not None else []) + others:
            try:
                info = await asyncio.wait_for(frame.evaluate(VAGON_DIAG_JS), 8)
            except Exception as error:
                frames.append({"error": self._scrub(clean_error(error))[:80]})
                continue
            if isinstance(info, dict):
                frames.append(info)
        main = frames[0] if frames and "error" not in frames[0] else {}
        rtc = self._rtc_summary(frames)
        if rtc.get("bytes", 0) > self._rtc_bytes:
            self._rtc_bytes = rtc["bytes"]
            self._activity("rtc")
        media = next((f["rtc"].get("media") for f in frames if isinstance(f.get("rtc"), dict) and f["rtc"].get("media")), None)
        # the input path of the frame that shows the stream (its cover grid exists), else of the main document
        inputs = next((f.get("input") for f in frames if isinstance(f.get("input"), dict) and f["input"].get("cover")), None)
        diag = {"phase": phase, "host": main.get("host"), "path": main.get("path"), "title": main.get("title"),
                "ready": main.get("ready"), "visible": main.get("visible"), "focus": main.get("focus"),
                "input": inputs or main.get("input"),
                "iframes": main.get("iframes"), "videos": [x for f in frames for x in (f.get("videos") or [])][:8],
                "canvases": [x for f in frames for x in (f.get("canvases") or [])][:8],
                "webgl": main.get("webgl"), "renderer": main.get("renderer"), "webcodecs": main.get("webcodecs"),
                "webgpu": main.get("webgpu"), "codecs": main.get("codecs"), "activation": main.get("activation"),
                "pointer_lock": main.get("pointer_lock"), "media": media, "rtc": rtc,
                "sub_frames": [{"host": f.get("host"), "path": f.get("path"), "videos": len(f.get("videos") or []),
                                "canvases": len(f.get("canvases") or []), "webgl": f.get("webgl"),
                                "rtc": bool((f.get("rtc") or {}).get("created"))} if "error" not in f else f for f in frames[1:]],
                "console": list(self._console)[-6:], "failed": dict(self._failed), "http_errors": dict(self._http_errors),
                "net": {"age_s": {k: round(now - t, 1) for k, t in self._net.items()}, "counts": dict(self._counts),
                        "ws_hosts": sorted(self._ws_hosts)[:10]},
                "browser": {"version": self.browser_version, "executable": self.cfg.chromium or "playwright chromium",
                            "ua": main.get("ua"), "gpu": self.cfg.gpu, "autoplay": self.cfg.autoplay,
                            "extra_args": list(self.cfg.extra_args or ())}}
        v.diag, v.diag_at = diag, time.time()
        self.events.append("vagon_diag", **diag)
        return diag

    # network and console observations (the diag; never a URL beyond its host, never a page text)
    def _activity(self, kind):
        self._net[kind] = time.monotonic()
        self._counts[kind] = self._counts.get(kind, 0) + 1

    def _scrub_text(self, text, limit=160):
        """A console/error text safe to log: URL queries, e-mail addresses and long opaque tokens removed, truncated."""
        text = re.sub(r"\?\S*", "?…", str(text or ""))
        text = EMAIL_RX.sub("<email>", text)
        text = re.sub(r"[A-Za-z0-9_\-]{32,}", "<token>", text)
        return (self._scrub(text) if self.vagon_mode else text)[:limit]

    def _note_console(self, kind, text):
        self._console.append({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"), "kind": kind,
                              "text": self._scrub_text(text)})

    def _on_console(self, msg):
        try:
            if msg.type == "error":
                self._note_console("console", msg.text)
        except Exception:
            pass

    def _on_request_failed(self, request):
        try:
            host = urlsplit(request.url).hostname or request.url.split(":")[0][:20]
            why = str(request.failure or "failed").split(";")[0][:60]
            key = f"{host} {why}"
            if key in self._failed or len(self._failed) < 20:
                self._failed[key] = self._failed.get(key, 0) + 1
        except Exception:
            pass

    def _on_websocket(self, ws):
        try:
            host = urlsplit(ws.url).hostname or "?"
            if len(self._ws_hosts) < 10:
                self._ws_hosts.add(host)
            self._activity("ws_open")
            ws.on("framereceived", lambda f: self._activity("ws"))
            ws.on("framesent", lambda f: self._counts.__setitem__("ws_sent", self._counts.get("ws_sent", 0) + 1))
            ws.on("close", lambda w: self._counts.__setitem__("ws_closed", self._counts.get("ws_closed", 0) + 1))
            ws.on("socketerror", lambda e: self._note_console("websocket", f"{host}: {e}"))
        except Exception:
            pass

    async def _api_loop(self):
        """Workstation with a Teams API key: the machine's status every VAGON_API_POLL_S (blocking HTTP in a thread)."""
        while not self.stopping:
            try:
                state = await asyncio.to_thread(self.api.refresh)
                if self.api.error:
                    if self.api.error != self._api_logged:
                        self._api_logged = self.api.error
                        log(f"vagon API: {self.api.error}")
                        self.events.append("error", where="vagon-api", message=self.api.error)
                else:
                    self._api_logged = None
                    self._set_machine(state, "api")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log(f"vagon API: {clean_error(error)}")
            await asyncio.sleep(VAGON_API_POLL_S)

    async def api_start(self, why):
        """Start the machine through the Teams API (the owner's /pc/vagon/start, or the loop when the page offers no
        start button). {ok, machine, started, error}; never logs a key."""
        if self.api is None:
            return {"ok": False, "machine": self.vagon.machine, "started": False, "error": "the Vagon API is not configured"}
        state = await asyncio.to_thread(self.api.refresh)
        if self.api.error:
            self.events.append("error", where="vagon-api", message=self.api.error)
            return {"ok": False, "machine": state, "started": False, "error": self.api.error}
        if state != "off":
            self._set_machine(state, "api")
            return {"ok": True, "machine": state, "started": False, "error": ""}
        if self.api.started_at and time.monotonic() - self.api.started_at < VAGON_API_START_GAP_S:
            return {"ok": False, "machine": state, "started": False, "error": "the machine was started a moment ago"}
        error = await asyncio.to_thread(self.api.start)
        self.events.append("vagon_api", action="start", why=why, ok=not error, error=error or None)
        log(f"vagon API: start requested ({why}): {'ok' if not error else error}")
        if error:
            return {"ok": False, "machine": state, "started": False, "error": error}
        self._set_machine("starting", "api")
        return {"ok": True, "machine": "starting", "started": True, "error": ""}

    async def _vagon_step_locked(self):
        v, now = self.vagon, time.monotonic()
        probe = await self._vagon_probe()
        if self.workstation:
            return await self._workstation_step(probe, now)
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

    def _remote_ready(self, probe):
        """Is the remote desktop on screen right now (the agent may act and see)? Workstation: the loop's `connected`
        and a fresh probe must agree, so a page that just changed is never shown."""
        if self.workstation:
            return self.vagon.connected and classify_workstation(probe)["phase"] == "connected"
        return classify_vagon(probe)[0] == "ready"

    async def _vagon_snapshot(self, obs):
        probe = await self._vagon_probe()
        ready = self._remote_ready(probe)
        if self.workstation and not ready:                # privacy lock: never the login or account pages
            return {"url": redact_url(self.cfg.vagon_url), "title": "remote desktop", "text": "",
                    "scroll": {"y": 0, "max": 0}, "loading": bool(probe.get("loading")), "width": SMALL[0],
                    "height": SMALL[1], "jpeg": neutral_jpeg(SMALL), "marks": [], "dialogs": self.pop_dialogs() if obs else [],
                    "mode": "vagon", "remote_ready": False}
        try:
            jpeg = await self._guarded(self.page.screenshot(type="jpeg", quality=80), "screenshot")
        except DesktopUnavailable:
            raise
        except Exception as error:
            raise DesktopUnavailable(f"screenshot failed: {self._scrub(clean_error(error))}")
        return {"url": redact_url(probe.get("url")) or redact_url(self.cfg.vagon_url),
                "title": "remote desktop" if self.workstation else " ".join(str(probe.get("title") or "").split())[:160] or "remote desktop",
                "text": "", "scroll": {"y": 0, "max": 0}, "loading": bool(probe.get("loading")), "width": self.view[0],
                "height": self.view[1], "jpeg": jpeg, "marks": [], "dialogs": self.pop_dialogs() if obs else [],
                "mode": "vagon", "remote_ready": ready}

    async def _do_vagon(self, a, errors):
        """The agent primitives on the stream: clicks and wheel at page points over the stream element, keys to
        the focused stream, navigate/search as Ctrl+L + URL + Enter in the remote browser, back as Alt+Left."""
        page, kind = self.page, a["action"]
        if kind == "wait":
            await asyncio.sleep(a["seconds"])
            return
        async with self._vagon_lock:
            probe = await self._vagon_probe()
            if not self._remote_ready(probe):
                phase = classify_workstation(probe)["phase"] if self.workstation else classify_vagon(probe)[0]
                phase = "connecting" if phase == "connected" else phase      # the probe is ahead of the connect loop
                errors.append(f"the remote desktop is not connected ({'PC' if self.workstation else 'stream'} {phase}); wait and observe again")
                return
            if "mark" in a:
                raise ActFailed("there are no marks on the remote desktop; click by point")
            await self._vagon_input(a, probe["stream"]["box"])

    async def _vagon_hit(self, x, y, what="click"):
        """What a click (or the wheel) at page point (x, y) would land on (VAGON_HIT_JS, in the frame that holds the
        stream); ActFailed unless it is the stream element itself (the Vagon toolbar handle, a menu, a dialog, a
        dim/backdrop or any other layer is the host page's), when the stream's iframe (if any) is not on top of the
        parent page at that point, and when it cannot be checked. Anything but an explicit `ok: true` is a refusal."""
        main = getattr(self.page, "main_frame", None)
        frame = self._vagon_frame or main or self.page
        hit = None
        try:
            if main is not None and frame is not main:   # a stream in an iframe: nothing of the parent page may cover it
                owner = await asyncio.wait_for(frame.frame_element(), 5)
                if not await asyncio.wait_for(owner.evaluate("(el, p) => document.elementFromPoint(p[0], p[1]) === el", [x, y]), 5):
                    hit = {"ok": False, "tag": "iframe", "why": "a host-page element over the stream's frame"}
            if hit is None:
                hit = await asyncio.wait_for(frame.evaluate(VAGON_HIT_JS, [x - self._vagon_offset[0], y - self._vagon_offset[1],
                                                                             VAGON_MIN_STREAM[0], VAGON_MIN_STREAM[1]]), 5)
        except Exception as error:
            raise ActFailed(f"the point could not be checked on the stream page ({self._scrub(clean_error(error))[:60]}); observe again")
        if not isinstance(hit, dict) or hit.get("ok") is not True:   # anything but an explicit yes is a no
            hit = hit if isinstance(hit, dict) else {"why": "no answer from the hit test"}
            element = " ".join(s for s in (hit.get("tag"), hit.get("id") and "#" + hit["id"], hit.get("text") and repr(hit["text"])) if s)
            why = str(hit.get("why") or "host-page element")[:60]
            self.events.append("blocked", what=what, reason=why, element=element[:120] or "?")
            raise ActFailed(f"blocked: that point is the stream page's own ({why}: {element[:60]}), not the remote desktop")
        return hit

    def _stream_point(self, box):
        """Where the pointer rests on the stream: the last point the agent used when it is inside the stream box, else
        the centre of the stream."""
        x, y = self.cursor
        if box[0] + 2 <= x <= box[0] + box[2] - 2 and box[1] + 2 <= y <= box[1] + box[3] - 2:
            return x, y
        return box[0] + box[2] / 2, box[1] + box[3] / 2

    async def _vagon_keys_ready(self):
        """Before keys reach the remote desktop: the stream element has the DOM focus (measured 2026-10-23: that alone
        is enough, no click, hover or pointer lock first; a click would land in a remote window). Fails closed: keys that
        cannot be aimed at the stream are never sent to the host page."""
        if not await self._vagon_focus():
            self.events.append("blocked", what="keys", reason="the stream element did not take the keyboard focus")
            raise ActFailed("the stream did not take the keyboard focus; nothing was sent; observe again")

    async def _vagon_point(self, x, y, what):
        """The pointer onto (x, y) of the stream, checked before the move and again VAGON_HOVER_S after it (moving can
        open a host-page hover toolbar or menu under the point): ActFailed when either check says it is not the stream."""
        await self._vagon_hit(x, y, what)
        await self.page.mouse.move(x, y, steps=6)
        self.cursor = [x, y]
        await asyncio.sleep(VAGON_HOVER_S)
        await self._vagon_hit(x, y, what)

    async def _vagon_chord(self, key):
        """One key or chord into the stream like a person presses it: the modifiers down, a hold (VAGON_CHORD_HOLD_S,
        longer than Vagon's 15 ms AltGr window), the key, the modifiers up (always, even after an error)."""
        mods, last = parse_key(key)
        keyboard, held = self.page.keyboard, []
        if not mods:
            await keyboard.press(last)
            return
        try:
            for mod in mods:
                await keyboard.down(mod)
                held.append(mod)
            await asyncio.sleep(VAGON_CHORD_HOLD_S)
            await keyboard.press(last)
            await asyncio.sleep(0.03)
        finally:
            for mod in reversed(held):
                await keyboard.up(mod)

    async def _vagon_type(self, text, delay_ms):
        """Type through the stream client: shifted characters and capitals as explicit Shift chords (VAGON_SHIFTED)."""
        keyboard = self.page.keyboard
        for chord, ch in vagon_key_plan(text):
            if chord:
                await keyboard.press(chord)
            else:
                await keyboard.type(ch)
            if delay_ms:
                await asyncio.sleep(delay_ms / 1000)

    async def _vagon_input(self, a, box):
        page, kind, settle = self.page, a["action"], VAGON_SETTLE_S
        if kind == "click":
            x, y = image_point(a["point"], self.view)
            await self._vagon_point(x, y, "click")
            await page.mouse.click(x, y)
        elif kind == "scroll":
            x, y = self._stream_point(box)
            await self._vagon_point(x, y, "scroll")
            sign, step = (1 if a["direction"] == "down" else -1), a["amount"] / 6
            for i in range(6):
                if i:
                    await self._vagon_hit(x, y, "scroll")  # each step: the page may have put something there meanwhile
                await page.mouse.wheel(0, sign * step)
                await asyncio.sleep(0.05)
        elif kind == "type":
            await self._vagon_keys_ready()
            await self._vagon_type(a["text"], VAGON_TYPE_DELAY_MS)
            if a.get("submit"):
                await page.keyboard.press("Enter")
        elif kind == "key":
            await self._vagon_keys_ready()
            await self._vagon_chord(a["key"])
        elif kind in ("navigate", "search"):
            url = a["url"] if kind == "navigate" else SEARCH_URL + quote_plus(a["query"])
            await self._vagon_keys_ready()
            await self._vagon_chord("Control+l")         # the remote browser's address bar (Chrome, Edge, Firefox)
            await asyncio.sleep(0.3)
            await self._vagon_type(url, 8)
            await asyncio.sleep(0.1)
            await page.keyboard.press("Enter")
            settle = VAGON_NAV_SETTLE_S
        elif kind == "back":
            await self._vagon_keys_ready()
            await self._vagon_chord("Alt+ArrowLeft")     # the host page's own "back" is prevented (VAGON_FOCUS_JS)
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
    def _main_blocked(self, url, method="GET"):
        """Why a main-frame navigation to `url` is refused: the workstation lock (site and account pages) in that kind,
        the general page rules otherwise."""
        if self.workstation:
            return workstation_request_blocked(url, self.cfg.vagon_url, True, method, self.cfg.allow_private)
        return request_blocked(url, True, method, self.cfg.allow_private)

    def _on_response(self, response):
        try:
            if response.status >= 400:
                key = f"{urlsplit(response.url).hostname or '?'} {response.status}"
                if key in self._http_errors or len(self._http_errors) < 20:
                    self._http_errors[key] = self._http_errors.get(key, 0) + 1
            request = response.request
            if (300 <= response.status < 400 and request.is_navigation_request() and request.frame.parent_frame is None
                    and request.frame.page is self.page):
                target = urljoin(response.url, response.headers.get("location", ""))
                why = self._main_blocked(target) if target != response.url else None
                if why:
                    self._kill_navigation(why, target)
        except Exception:
            pass

    def _on_navigated(self, frame):
        try:
            if frame.parent_frame is None and frame.page is self.page and frame.url not in ("about:blank", ""):
                why = None if frame.url.startswith("chrome-error:") else self._main_blocked(frame.url)
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
        if self.workstation:                              # back to the workstation page, not to a blank one
            self.vagon.blocked += 1
            asyncio.ensure_future(self._vagon_return(why))
        else:
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
        if self.workstation:                              # the stream may open in its own window: adopt it, never close it
            asyncio.ensure_future(self._adopt_or_close(page))
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
            if self.workstation:
                why = workstation_request_blocked(req.url, self.cfg.vagon_url, main, req.method, self.cfg.allow_private)
            else:
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
                    if self.workstation:
                        self.vagon.blocked += 1
                        asyncio.ensure_future(self._vagon_return(why))   # an aborted navigation may leave an error page
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
                self._operator = (self._operator[0] + 1, jpeg)   # the owner's console sees the real page
                if self.privacy_locked():                 # the monitor and the model see the neutral picture
                    jpeg, png = self._neutral_pair()
                else:
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
                if self.vagon_mode and mod_name(key) == "Control":   # a batch arrives at once: Vagon's 15 ms AltGr window
                    await asyncio.sleep(VAGON_CHORD_HOLD_S)
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
            if not self.vagon.connected and not self.operator_allowed():
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

    async def operator_input(self, clean):
        """The owner's console: an absolute mouse position (fractions of the frame), a key down/up by its code, or text
        (newlines press Enter). Clipboard combinations are dropped as everywhere; nothing is logged but failures without
        their content. False when not delivered."""
        if self.status != "ready" or self.page is None:
            return False
        kind = clean["type"]
        try:
            async with self._input_lock:
                if kind == "mouse":
                    w, h = self.view
                    x, y = min(w - 1, max(0, clean["x"] * w)), min(h - 1, max(0, clean["y"] * h))
                    self.cursor = [x, y]
                    await self.page.mouse.move(x, y)       # always: the console dedupes, and a press needs the position
                    for i, name in enumerate(("left", "middle", "right")):
                        if "buttons" in clean and clean["buttons"][i] != self.buttons[i]:
                            await (self.page.mouse.down if clean["buttons"][i] else self.page.mouse.up)(button=name)
                            self.buttons[i] = clean["buttons"][i]
                    if clean.get("wheel"):
                        await self.page.mouse.wheel(0, clean["wheel"])
                elif kind == "key":
                    key = clean["key"]
                    if clean["down"]:
                        held_mods = {mod_name(k) for k in self.held} - {None}
                        if not mod_name(key) and clipboard_combo(held_mods, plain_key(key)):
                            self.dropped.add(key)
                            return False
                        await self.page.keyboard.down(key)
                        self.held.add(key)
                    elif key in self.dropped:
                        self.dropped.discard(key)
                    else:
                        await self.page.keyboard.up(key)
                        self.held.discard(key)
                else:
                    for i, part in enumerate(clean["text"].split("\n")):
                        if i:
                            await self.page.keyboard.press("Enter")
                        if part:
                            await self.page.keyboard.type(part, delay=VAGON_TYPE_DELAY_MS if self.vagon.connected else 0)
                return True
        except Exception as error:
            log(f"operator {kind} input not delivered" + (f": {clean_error(error)}" if kind != "text" else ""))
            return False

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

    def remote_logins(self):
        """--allow-credentials applies: vagon mode only (the URL is typed into the REMOTE PC's browser). The pod's own
        Chromium and the Vagon host page's navigation lock never lift the login rules."""
        cfg = getattr(self.desk, "cfg", None)
        return getattr(cfg, "pc_mode", "chromium") == "vagon" and getattr(cfg, "allow_credentials", False) is True

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
            view["vagon"]["operator_console"] = bool(getattr(d, "operator_allowed", lambda: False)())
            view["allow_credentials"] = self.remote_logins()
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

    async def operator_input(self, clean):
        """The owner's console input; None when privacy refuses it. Never logged (it may be a password)."""
        if self.privacy:
            return None
        epoch = self.privacy_epoch
        try:
            ok = await asyncio.wait_for(self.desk.operator_input(clean), 3.0)
        except asyncio.TimeoutError:
            ok = False
        if self.privacy or epoch != self.privacy_epoch:
            await self.desk.release_inputs()
            return None
        self.last_command = "operator"
        return {"ok": bool(ok)}

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
            remote = getattr(getattr(self.desk, "cfg", None), "pc_mode", "chromium") == "vagon"
            refusal = (f"stale frame_id: observe again before using marks (current {self.last_obs['frame_id']})" if stale
                       else action_policy(action, self.last_obs["marks"], self.allow_private, self.remote_logins(), remote))
            # rows: a login URL, and on the remote PC every URL, without its query string (a magic link, a verification or
            # reset code), and never a typed text, in either mode (it may be a credential the agent typed with the
            # owner's --allow-credentials; the agent keeps its own masked audit)
            mask = kind == "type"
            if refusal:
                errors.append(refusal)
                if refusal.startswith("blocked"):
                    log(f"blocked action {kind}: {refusal}")
                    self.events.append("blocked", what="action", action=_loggable(action, remote, mask), reason=refusal)
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
            self.events.append("act", action=_loggable(action, remote, mask), ok=ok, outcome=outcome,
                               frame_id=frame_id if after else None)
            if not ok:
                log(f"action {kind} not ok: {outcome['errors'][0]}")
            return {"ok": ok, "outcome": outcome, "frame_id": frame_id if after is not None else None}


def _loggable(action, remote=False, mask_text=False):
    """An action for events.jsonl: strings cut at 200 characters, the URL as loggable_url shows it, typed text as
    `[typed N chars]` (`mask_text`: on the remote PC, where a password may be typed)."""
    out = {}
    for k, v in action.items():
        if k in ("obs", "mark_info"):
            continue
        if k == "url" and isinstance(v, str):
            v = loggable_url(v, remote)
        elif k == "text" and mask_text and isinstance(v, str):
            v = f"[typed {len(v)} chars]"
        out[k] = v[:200] if isinstance(v, str) else v
    return out


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
        public = request.path == "/healthz" or (request.path == "/operator" and request.method == "GET")
        if not public and not runner.authorized(request):
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

    # the owner's console: the page itself needs no token (it holds none); the frame and the input do
    def operator_gate():
        if not getattr(runner.desk, "operator_allowed", lambda: False)():
            raise web.HTTPNotFound(text=OPERATOR_UNAVAILABLE)

    async def operator_page(request):
        operator_gate()
        runner.events.append("operator", state="served")
        csp = "default-src 'none'; img-src 'self' blob:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'"
        return web.Response(text=OPERATOR_HTML, content_type="text/html", charset="utf-8",
                            headers=dict(no_store, **{"Content-Security-Policy": csp, "X-Frame-Options": "DENY",
                                                      "Referrer-Policy": "no-referrer"}))

    async def operator_frame(request):
        operator_gate()
        refuse_private()
        got = runner.desk.operator_frame()
        if not got:
            raise web.HTTPNotFound(text="No desktop frame yet (browser starting or restarting)")
        tag, jpeg = got
        headers = dict(no_store, ETag=f'"{tag}"')
        if request.headers.get("If-None-Match") == headers["ETag"]:
            return web.Response(status=304, headers=headers)
        return web.Response(body=jpeg, content_type="image/jpeg", headers=headers)

    async def operator_input(request):
        data = await read_json(request)
        operator_gate()
        refuse_private()
        try:
            clean = validate_operator(data)
        except ValueError as error:
            raise web.HTTPBadRequest(text=str(error))
        result = await runner.operator_input(clean)
        if result is None:
            raise web.HTTPConflict(text="Bathroom privacy is active")
        return web.json_response(result, headers=no_store)

    async def vagon_arm(request):
        """Allow one start of the owner's Vagon computer within N minutes ({"minutes": 10}; 0 disarms). Starting it
        spends his balance, so the runner never does it on its own unless --vagon-autostart."""
        if not getattr(runner.desk, "workstation", False):
            raise web.HTTPConflict(text="Only the Vagon workstation kind has a machine to start")
        data = await read_json(request)
        minutes = data.get("minutes", 10) if isinstance(data, dict) else 10
        if not isinstance(minutes, (int, float)) or isinstance(minutes, bool) or not 0 <= minutes <= 120:
            raise web.HTTPBadRequest(text="minutes must be a number between 0 and 120")
        return web.json_response(runner.desk.arm_start(minutes), headers=no_store)

    async def vagon_start(request):
        if getattr(runner.desk, "api", None) is None:
            raise web.HTTPConflict(text="The Vagon API is not configured (api_key_file and machine_id in vagon.json)")
        if not runner.desk.take_start("POST /pc/vagon/start"):              # same contract: arm first (spends his balance)
            raise web.HTTPConflict(text="Starting the computer spends the owner's balance: arm it first (POST /pc/vagon/arm)")
        result = await runner.desk.api_start("operator request")
        return web.json_response(result, status=200 if result["ok"] else 502, headers=no_store)

    async def vagon_reload(request):
        """The owner's request to open the workstation page again (the loop never reloads a connecting page on its own
        unless it is dead)."""
        if not getattr(runner.desk, "workstation", False):
            raise web.HTTPConflict(text="Only the Vagon workstation page can be reloaded on request")
        return web.json_response(runner.desk.request_reload("operator request"), headers=no_store)

    async def vagon_diag(request):
        """A fresh Vagon diagnostic snapshot (WebRTC stats, input counters, what covers the stream); vagon mode only."""
        if not getattr(runner.desk, "vagon_mode", False):
            raise web.HTTPConflict(text="Only the Vagon mode has a stream diagnostic")
        try:
            return web.json_response({"ok": True, "diag": await runner.desk.diag_now()}, headers=no_store)
        except DesktopUnavailable as error:
            return unavailable(error)

    app = web.Application(middlewares=[guard], client_max_size=4096)
    app.router.add_get("/operator", operator_page)
    app.router.add_get("/operator/frame.jpg", operator_frame)
    app.router.add_post("/operator/input", operator_input)
    app.router.add_post("/pc/vagon/arm", vagon_arm)
    app.router.add_post("/pc/vagon/start", vagon_start)
    app.router.add_post("/pc/vagon/reload", vagon_reload)
    app.router.add_get("/pc/vagon/diag", vagon_diag)
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
                 vagon_api_key_file=getattr(args, "vagon_api_key_file", "") or "",
                 vagon_kind=getattr(args, "vagon_kind", None) or "streams",
                 vagon_machine_id=getattr(args, "vagon_machine_id", "") or "",
                 operator_console=bool(getattr(args, "operator_console", False)),
                 gpu=getattr(args, "gpu", None) or "off", autoplay=bool(getattr(args, "autoplay", False)),
                 extra_args=tuple(getattr(args, "chromium_arg", None) or ()),
                 vagon_autostart=bool(getattr(args, "vagon_autostart", False)),
                 allow_credentials=args.pc_mode == "vagon" and getattr(args, "allow_credentials", False) is True)
    desk = Desktop(cfg, events)
    if cfg.pc_mode == "vagon":
        key_status = api_key_file_status(cfg.vagon_api_key_file)
        if key_status == "permissive":
            log("warning: the Vagon API key file is readable by other users; make it mode 0600")
        if cfg.vagon_kind == "workstation":
            api_note = "none"
            if cfg.vagon_api_key_file:
                try:
                    desk.api = VagonApi.load(cfg.vagon_api_key_file, cfg.vagon_machine_id)
                    api_note = "Teams API configured (machine status, /pc/vagon/start)"
                except ValueError as error:
                    api_note = f"not used: {error}"
            log(f"vagon mode (workstation): the owner's Cloud Computer page at {redact_url(cfg.vagon_url)}; API {api_note}; "
                f"operator console {'always' if cfg.operator_console else 'while a login is needed'}")
        else:
            log(f"vagon mode (streams): stream at {redact_url(cfg.vagon_url)}; API key file {key_status} (not used by the runner)")
        log("remote PC logins: " + ("allowed (--allow-credentials): the agent may open login/account pages on the remote PC"
                                    if cfg.allow_credentials else "refused (--no-allow-credentials)"))
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
                  gpu=cfg.gpu, autoplay=cfg.autoplay, chromium_args=list(cfg.extra_args), chromium=cfg.chromium or "playwright",
                  **({"vagon_host": redact_url(cfg.vagon_url), "vagon_kind": cfg.vagon_kind,
                      "operator_console": cfg.operator_console, "allow_credentials": cfg.allow_credentials}
                     if cfg.pc_mode == "vagon" else {}))
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


def env_bool(name, default):
    """1/true/yes/on and 0/false/no/off (any case); anything else, or unset, is the default."""
    value = os.environ.get(name, "").strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    return default


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
                        help="chromium: browse itself (default); vagon: show the owner's Vagon page (streams or workstation)")
    parser.add_argument("--vagon-kind", choices=VAGON_KINDS, help="vagon mode: streams (a public stream link, default) or "
                        "workstation (the owner's Vagon Cloud Computer behind his login); overrides kind in the config file")
    parser.add_argument("--vagon-url", help="vagon mode: the stream link or the workstation page (prefer the config file: a "
                                            "command line is visible to other users); never logged beyond its host")
    parser.add_argument("--vagon-config", help=f"vagon mode: JSON file {{schema: {VAGON_SCHEMA}, kind?, stream_url | url, "
                                               f"api_key_file?, machine_id?}} (default <streamer-dir>/vagon.json)")
    parser.add_argument("--streamer-dir", default=os.environ.get("STREAMER_DIR", DEFAULT_STREAMER_DIR),
                        help="streamer state directory: holds vagon.json (env STREAMER_DIR)")
    parser.add_argument("--vagon-autostart", action="store_true",
                        help="workstation: turn the owner's computer on by itself when it is off (spends his Vagon "
                             "balance); default: only after POST /pc/vagon/arm, one start per arming")
    parser.add_argument("--operator-console", action="store_true",
                        help="vagon mode: serve the owner's console at /operator always, not only while the desktop is not connected")
    parser.add_argument("--gpu", choices=GPU_MODES, default="off",
                        help="Chromium GPU mode: off (--disable-gpu, default), swiftshader (software WebGL through ANGLE), on")
    parser.add_argument("--autoplay", action="store_true", help="Chromium --autoplay-policy=no-user-gesture-required")
    parser.add_argument("--allow-credentials", action=argparse.BooleanOptionalAction,
                        default=env_bool("STREAMER_ALLOW_CREDENTIALS", True),
                        help="vagon mode (owner, 2026-10-23): the agent may open login, SSO and account pages on the REMOTE "
                             "PC (money, adult, gambling, crypto, account changes and the owner's consoles stay refused; "
                             "the Vagon host page's own lock is unchanged); default on (env STREAMER_ALLOW_CREDENTIALS)")
    parser.add_argument("--chromium-arg", action="append", default=[], metavar="--FLAG[=VALUE]",
                        help="extra Chromium flag, verbatim, written as --chromium-arg=--flag=value (repeatable; recorded in the start event)")
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK:
        parser.error("the streamer desktop binds only to loopback")
    flag_url, args.vagon_url, args.vagon_api_key_file, args.vagon_machine_id = (args.vagon_url or "").strip(), "", "", ""
    if args.pc_mode == "vagon":
        config_path = Path(args.vagon_config).expanduser() if args.vagon_config else Path(args.streamer_dir).expanduser() / "vagon.json"
        conf = {"kind": "", "stream_url": "", "api_key_file": "", "machine_id": ""}
        if args.vagon_config or config_path.is_file():
            try:
                conf = load_vagon_config(config_path, args.allow_private)
            except ValueError as error:
                parser.error(f"{config_path}: {error}")
        kind = args.vagon_kind or conf["kind"] or "streams"
        url = flag_url or (conf["stream_url"] if not args.vagon_kind or args.vagon_kind == conf["kind"] else "")
        if kind == "workstation":
            url = url or DEFAULT_WORKSTATION_URL
            why = workstation_url_problem(url, url, args.allow_private)
        else:
            if not url:
                parser.error(f"vagon mode needs the owner's stream link: --vagon-url or stream_url in {config_path}")
            why = vagon_url_problem(url, args.allow_private)
        if why:
            parser.error(f"vagon page refused: {why}")    # the link itself is never echoed
        args.vagon_kind, args.vagon_url = kind, url
        args.vagon_api_key_file, args.vagon_machine_id = conf["api_key_file"], conf["machine_id"]
        if args.start_url != "about:blank":
            log("--start-url is ignored in vagon mode")
    elif flag_url or args.vagon_config or args.vagon_kind or args.operator_console:
        parser.error("--vagon-url, --vagon-config, --vagon-kind and --operator-console need --pc-mode vagon")
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
