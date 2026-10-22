"""Client for the Vagon Teams API. The persona's PC is a Vagon Windows computer.

Documented capabilities: create, start, stop, auto-stop, performance change (stopped machines only), reset (irreversible,
deliberately not exposed here), a Vagon-hosted connection link, and run-script (PowerShell on Windows, answer window of
about 5 s). Not documented: keyboard or mouse input from outside the Vagon client, a screen image or raw stream, direct
RDP or VNC, internet access from the machine, admin rights. Those are open questions for Vagon, see docs/design/vagon-pc.

Auth: `Authorization: HMAC {key}:{signature}:{nonce}:{timestamp}`. The signature is the hex HMAC-SHA256, keyed with the
API secret, of key + method + path + timestamp + nonce + body, with no separators, no host and no query string. The
timestamp is in milliseconds and must be less than 60 s old. Credentials come only from VAGON_API_KEY and
VAGON_API_SECRET; nothing is written to disk or printed.

Not verified until run with real credentials on a pod: the signature (the field order is from the vendor docs), the
status values, and whether run-script reaches the interactive desktop.
"""
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "https://api.vagon.io"
PREFIX = "/organization-management/v1"
AUTO_STOP_STEPS = (0, 900, 3600, 10800, 21600)   # seconds of idle time the vendor accepts; 0 disables auto-stop
WEB_LINK = re.compile(r"https?://[\x21-\x7e]+")  # http(s) only, no spaces or control characters


class VagonError(RuntimeError):
    pass


def _credentials():
    key, secret = os.environ.get("VAGON_API_KEY", ""), os.environ.get("VAGON_API_SECRET", "")
    if not key or not secret:
        raise VagonError("set VAGON_API_KEY and VAGON_API_SECRET in the environment")
    return key, secret


def signed_header(method, path, body, key, secret, timestamp_ms=None, nonce=None):
    """The Authorization value for one request. `path` has no host and no query string; `body` is the exact text that
    is sent, or '' for GET."""
    ts = str(int(time.time() * 1000) if timestamp_ms is None else timestamp_ms)
    nonce = uuid.uuid4().hex if nonce is None else nonce
    payload = f"{key}{method}{path}{ts}{nonce}{body}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"HMAC {key}:{sig}:{nonce}:{ts}"


def call(method, path, body=None, query=None, timeout=20):
    """One signed request, returning the decoded JSON. Any HTTP error raises VagonError; a 429 is never retried here."""
    key, secret = _credentials()
    raw = "" if body is None else json.dumps(body, separators=(",", ":"))
    url = BASE + PREFIX + path + (("?" + urllib.parse.urlencode(query)) if query else "")
    headers = {"Authorization": signed_header(method, PREFIX + path, raw, key, secret),
               "Content-Type": "application/json"}
    req = urllib.request.Request(url, method=method, data=raw.encode() if raw else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode()
    except urllib.error.HTTPError as e:
        raise VagonError(f"{method} {path} failed with HTTP {e.code}") from e
    return json.loads(text) if text.strip() else {}


def list_machines(q=None):
    return call("GET", "/machines", query={"q": q} if q else None).get("machines", [])


def find_machine(machine_id):
    for m in list_machines():
        if m.get("id") == machine_id:
            return m
    raise VagonError(f"machine {machine_id} not found")


def status(machine_id):
    """friendly_status from the list: off, creating, turning_on, ready, turning_off, ..."""
    return find_machine(machine_id).get("attributes", {}).get("friendly_status")


def create_machine(plan_id, region, os_name="Windows"):
    """Creates one machine on a Team plan. The plan id comes from the Team Console: no list endpoint is documented."""
    return call("POST", "/machines", {"plan_id": plan_id, "quantity": 1, "region": region, "os": os_name})


def start_machine(machine_id):
    return call("POST", f"/machines/{machine_id}/start")


def stop_machine(machine_id, graceful=True):
    return call("POST", f"/machines/{machine_id}/stop", {"gracefully": graceful})


def set_auto_stop(machine_id, seconds):
    if seconds not in AUTO_STOP_STEPS:
        raise VagonError(f"auto-stop must be one of {AUTO_STOP_STEPS}")
    return call("PATCH", f"/machines/{machine_id}", {"auto_stop_threshold": seconds})


def wait_ready(machine_id, poll_s=15.0, max_wait_s=300.0):
    """Polls until the machine is ready. The vendor documents no rate limit, so the poll is slow by design."""
    deadline = time.time() + max_wait_s
    while True:
        st = status(machine_id)
        if st == "ready":
            return
        if time.time() > deadline:
            raise VagonError(f"machine {machine_id} still {st} after {max_wait_s:.0f} s")
        time.sleep(poll_s)


def connection_link(machine_id, minutes=30):
    """A Vagon-hosted session link. The docs do not say it works outside the Vagon app."""
    return call("POST", f"/machines/{machine_id}/access", {"expires_in": int(minutes)})


def run_script(machine_id, script):
    """Runs a PowerShell script through the machine's agent and returns its text output."""
    return call("POST", f"/machines/{machine_id}/run-script", {"script_body": script}).get("result", "")


def open_url(machine_id, url):
    """Opens an http(s) link in the machine's default browser. The link is checked, and quoted for PowerShell, so the
    text of a chat message can never become a command: single quotes are doubled and nothing else is interpreted."""
    if len(url) > 2000 or not WEB_LINK.fullmatch(url):
        raise VagonError("only plain http or https links without spaces can be opened")
    quoted = "'" + url.replace("'", "''") + "'"
    return run_script(machine_id, f"Start-Process {quoted}")
