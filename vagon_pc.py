"""Client for the Vagon Teams API. The persona's PC is a Vagon Windows computer.

Documented capabilities: create, start, stop, auto-stop, performance change (stopped machines only), reset (irreversible,
deliberately not exposed here), a Vagon-hosted connection link, and run-script (PowerShell on Windows, answer window of
about 5 s). Not documented: keyboard or mouse input from outside the Vagon client, a screen image or raw stream, direct
RDP or VNC, internet access from the machine, admin rights. Those are open questions for Vagon, see docs/design/vagon-pc.

Auth: `Authorization: HMAC {key}:{signature}:{nonce}:{timestamp}`. The signature is the hex HMAC-SHA256, keyed with the
API secret, of key + method + path + timestamp + nonce + body, with no separators, no host and no query string. The
timestamp is in milliseconds and must be less than 60 s old. Credentials come only from VAGON_API_KEY and
VAGON_API_SECRET; nothing is written to disk or printed.

Not verified against the live API (see docs/design/vagon-pc): whether the signed path includes the API prefix (this code
signs it with the prefix), the JSON field names, the status strings, and whether run-script reaches the interactive
desktop.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "https://api.vagon.io"
PREFIX = "/organization-management/v1"
TIMEOUT_S = 20.0                                 # per request: a slower answer is an error, not a wait
MAX_RESPONSE_BYTES = 2_000_000
MAX_LINK = 2000
AUTO_STOP_STEPS = (0, 900, 3600, 10800, 21600)   # seconds of idle time the vendor accepts; 0 disables auto-stop
WEB_LINK = re.compile(r"https?://[\x21-\x7e]+")  # http(s) only, no spaces or control characters
LINK_PORTS = (None, 80, 443)                     # the ports a chat link may name: no probing of other services
# A public DNS name, without the final dot: labels of letters, digits and hyphens, and a last label of letters or
# punycode. No IP literal matches (10.0.0.5, 0x7f000001, 2130706433, 127.1 and [::1] all fail the last label).
_PUBLIC_NAME = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})")
LOCAL_SUFFIXES = (".local", ".localhost", ".localdomain", ".internal", ".lan", ".home", ".intranet", ".corp", ".arpa")
# Wildcard DNS services answer for a name that spells an address (169.254.169.254.nip.io) or for any name below them.
WILDCARD_ZONES = ("nip.io", "sslip.io", "xip.io", "localtest.me", "lvh.me", "vcap.me", "traefik.me")
_SPELLED_IP = re.compile(r"(?<!\d)\d{1,3}(?:[.-]\d{1,3}){3}(?!\d)")
WAIT_POLL_S = 15.0
WAIT_MAX_S = 300.0

# friendly_status values from GET /machines. The README quotes the vendor's list as off, creating, turning_on, ready,
# turning_off and more. 'running' and 'on' are candidates only, kept until a real machine shows which value it reports.
# A value outside these tuples is still returned to the caller, and it is logged once.
READY_STATUSES = ("ready", "running", "on")
STARTING_STATUSES = ("creating", "turning_on")
OFF_STATUSES = ("off", "stopped")
KNOWN_STATUSES = READY_STATUSES + STARTING_STATUSES + OFF_STATUSES + ("turning_off",)

log = logging.getLogger("vagon_pc")
_logged = set()                                  # each odd reading is logged once; capped so it cannot grow forever


class VagonError(RuntimeError):
    pass


def safe_token(value, limit=40):
    """A vendor string made safe for one log line: letters, digits and _ . - only, cut short."""
    if value is None:
        return "none"
    return re.sub(r"[^A-Za-z0-9_.-]", "?", str(value))[:limit] or "none"


def _log_once(key, msg, *args):
    if key not in _logged and len(_logged) < 100:
        _logged.add(key)
        log.warning(msg, *args)


def _credentials():
    key, secret = os.environ.get("VAGON_API_KEY", ""), os.environ.get("VAGON_API_SECRET", "")
    if not key or not secret:
        raise VagonError("set VAGON_API_KEY and VAGON_API_SECRET in the environment")
    return key, secret


def _now_ms():
    return int(time.time() * 1000)


def _new_nonce():
    return uuid.uuid4().hex


def _payload(key, method, path, ts, nonce, body):
    """The exact text that is signed, with no separators. The field order is the one in the design brief and has not
    yet been checked against a live call (see docs/design/vagon-pc)."""
    return f"{key}{method}{path}{ts}{nonce}{body}"


def signed_header(method, path, body, key, secret, timestamp_ms=None, nonce=None):
    """The Authorization value for one request. `path` is the signed path: the API prefix included, no host, no query
    string. `body` is the exact text that is sent, or '' when there is none."""
    ts = str(_now_ms() if timestamp_ms is None else int(timestamp_ms))
    nonce = _new_nonce() if nonce is None else nonce
    payload = _payload(key, method, path, ts, nonce, body).encode()
    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f"HMAC {key}:{sig}:{nonce}:{ts}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an error here: the signed header must never be sent on to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _scrub(text, key, secret):
    """Removes the credentials, signatures and links from a message that may carry them."""
    for value in (key, secret):
        if value:
            text = text.replace(value, "<redacted>")
    return re.sub(r"HMAC \S+|https?://\S+", "<redacted>", text)


def _vendor_message(e, key, secret):
    """The short text of a JSON error body, when there is one. The body is never shown whole."""
    try:
        obj = json.loads(e.read(4096).decode("utf-8", "replace"))
    except Exception:
        return ""
    if isinstance(obj, dict):
        for field in ("message", "error", "detail"):
            if isinstance(obj.get(field), str):
                return _scrub(obj[field], key, secret)[:120]
    return ""


_HINTS = {401: "the key, the secret or the clock is wrong; a request is valid for 60 s",
          403: "this key may not do that", 404: "not found", 429: "rate limited; not retried"}


def _hint(code):
    if code in _HINTS:
        return _HINTS[code]
    if 300 <= code < 400:
        return "redirects are not followed"
    return "the vendor's server failed; not retried" if code >= 500 else ""


def _http_message(where, e, key, secret):
    hint = _hint(e.code)
    msg = f"{where} failed with HTTP {e.code}" + (f" ({hint})" if hint else "")
    vendor = _vendor_message(e, key, secret)
    return msg + (f"; the vendor says: {vendor}" if vendor else "")


def call(method, path, body=None, query=None, timeout=TIMEOUT_S):
    """One signed request; returns the decoded JSON ({} for an empty answer). Every failure raises VagonError, and its
    text holds no credential, signature or link. Nothing is retried: a 429 is raised at once."""
    key, secret = _credentials()
    raw = "" if body is None else json.dumps(body, separators=(",", ":"))
    url = BASE + PREFIX + path + (("?" + urllib.parse.urlencode(query)) if query else "")
    headers = {"Authorization": signed_header(method, PREFIX + path, raw, key, secret),
               "Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, method=method, data=raw.encode() if raw else None, headers=headers)
    where = f"{method} {path}"
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            data = r.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise VagonError(_http_message(where, e, key, secret)) from None
    except urllib.error.URLError as e:
        raise VagonError(f"{where} could not reach the API: {_scrub(str(e.reason), key, secret)}") from None
    except (TimeoutError, socket.timeout):
        raise VagonError(f"{where} timed out after {timeout:g} s") from None
    except OSError as e:
        raise VagonError(f"{where} failed: {type(e).__name__}") from None
    if len(data) > MAX_RESPONSE_BYTES:
        raise VagonError(f"{where} answered with more than {MAX_RESPONSE_BYTES} bytes")
    text = data.decode("utf-8", "replace").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        raise VagonError(f"{where} answered with something that is not JSON") from None


def _machine_path(machine_id, suffix=""):
    """The path of one machine. The id is quoted, so it cannot add a path segment or a query."""
    return "/machines/" + urllib.parse.quote(str(machine_id), safe="") + suffix


def list_machines(q=None):
    """GET /machines: the team's machines as a list of dicts. The answer is {'machines': [...]} or a bare list."""
    data = call("GET", "/machines", query={"q": q} if q else None)
    if isinstance(data, dict):
        if "machines" not in data:
            raise VagonError("GET /machines answered without a 'machines' list")
        data = data["machines"]
    if not isinstance(data, list):
        raise VagonError("GET /machines answered without a list of machines")
    return [m for m in data if isinstance(m, dict)]


def find_machine(machine_id):
    for m in list_machines():
        if m.get("id") == machine_id:
            return m
    raise VagonError(f"machine {safe_token(machine_id)} is not listed by GET /machines")


def status_of(machine):
    """friendly_status of one machine from the list. A value outside KNOWN_STATUSES is returned as it is and logged
    once. A list without that field gives None, and the log names the attributes the answer does carry, once."""
    attributes = machine.get("attributes") if isinstance(machine, dict) else None
    value = attributes.get("friendly_status") if isinstance(attributes, dict) else None
    if isinstance(value, str):
        if value not in KNOWN_STATUSES:
            _log_once(("status", value), "vagon status %s is not in KNOWN_STATUSES", safe_token(value))
        return value
    names = sorted(attributes) if isinstance(attributes, dict) else []
    _log_once(("missing",), "vagon machine has no attributes.friendly_status; attribute names: %s",
              ", ".join(safe_token(n) for n in names[:20]) or "none")
    return None


def status(machine_id):
    """The machine's status string. There is no single-machine GET, so it is read from the list. None when absent."""
    return status_of(find_machine(machine_id))


def create_machine(plan_id, region, os_name="Windows"):
    """Creates one machine on a Team plan. The plan id comes from the Team Console: no list endpoint is documented.
    The bridge never calls this; it is for one manual create."""
    return call("POST", "/machines", {"plan_id": plan_id, "quantity": 1, "region": region, "os": os_name})


def start_machine(machine_id):
    return call("POST", _machine_path(machine_id, "/start"))


def stop_machine(machine_id, graceful=True):
    return call("POST", _machine_path(machine_id, "/stop"), {"gracefully": bool(graceful)})


def set_auto_stop(machine_id, seconds):
    if seconds not in AUTO_STOP_STEPS:
        raise VagonError(f"auto-stop must be one of {AUTO_STOP_STEPS}")
    return call("PATCH", _machine_path(machine_id), {"auto_stop_threshold": seconds})


def wait_ready(machine_id, poll_s=WAIT_POLL_S, max_wait_s=WAIT_MAX_S, clock=time.monotonic, sleep=time.sleep):
    """Polls the status until it is one of READY_STATUSES. Bounded: after max_wait_s it raises VagonError, and the last
    sleep ends at the deadline. An unknown value is polled like any other value that is not ready."""
    deadline = clock() + max_wait_s
    while True:
        st = status(machine_id)
        if st in READY_STATUSES:
            return
        left = deadline - clock()
        if left <= 0:
            raise VagonError(f"machine still not ready after {max_wait_s:.0f} s (last status: {safe_token(st)})")
        sleep(min(poll_s, left))


def connection_link(machine_id, minutes=30):
    """A Vagon-hosted session link. The docs do not say it works outside the Vagon app."""
    return call("POST", _machine_path(machine_id, "/access"), {"expires_in": int(minutes)})


def run_script(machine_id, script):
    """Runs a PowerShell script through the machine's agent; returns its text output (the vendor answers in ~5 s)."""
    answer = call("POST", _machine_path(machine_id, "/run-script"), {"script_body": script})
    return str(answer.get("result", "")) if isinstance(answer, dict) else ""


def is_plain_link(url):
    """The one gate for a link: an http or https string of at most MAX_LINK printable ASCII characters, no space, whose
    host is a public DNS name (SUB01-S03). Refused: userinfo (user:pw@host); a port other than 80 or 443; any IP literal
    (dotted, decimal, hex, octal or IPv6); a single-label name such as localhost; a local or internal name such as
    printer.local or metadata.google.internal; a wildcard-DNS name that spells an address (169.254.169.254.nip.io); a
    backslash, a percent sign or any character other than letters, digits, dots and hyphens. The name is not
    resolved, so a public name whose DNS points at a private address is not caught here."""
    if not isinstance(url, str) or len(url) > MAX_LINK or WEB_LINK.fullmatch(url) is None:
        return False
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port                          # ValueError for a port that is not a number in range
    except ValueError:
        return False
    name = parts.hostname or ""                    # lower case, brackets removed, userinfo removed
    if name.endswith("."):
        name = name[:-1]
    if "@" in parts.netloc or port not in LINK_PORTS or len(name) > 253:
        return False
    if _PUBLIC_NAME.fullmatch(name) is None or name.endswith(LOCAL_SUFFIXES):
        return False
    if any(name == zone or name.endswith("." + zone) for zone in WILDCARD_ZONES):
        return False
    return _SPELLED_IP.search(name) is None


# The link is never written into the script as text. Its bytes travel as one base64 literal, and base64 has no quote,
# dollar sign, backtick, separator or newline, so no shell or PowerShell can read anything from the link.
OPEN_SCRIPT = ("Start-Process -FilePath ([System.Text.Encoding]::ASCII.GetString("
               "[System.Convert]::FromBase64String('{encoded}')))")


def open_url(machine_id, url):
    """Opens one link in the machine's default browser. Only a link that passes is_plain_link is sent."""
    if not is_plain_link(url):
        raise VagonError("only public http or https links without spaces can be opened")
    encoded = base64.b64encode(url.encode("ascii")).decode("ascii")
    return run_script(machine_id, OPEN_SCRIPT.format(encoded=encoded))
