"""Real end-to-end CPU check of the private home stack (no fakes, loopback only).

Starts the actual live_server.py (HOME_ENABLED=1, MIND=0, CLIPS=0, no browse
service, no spiking, no paid keys) on 127.0.0.1 with a random free port and a
temporary data directory outside the repository, then talks to it over real
HTTP and the real /ws feed, and starts tools/unreal_home_state_bridge.py
against it.

Two backend runs:
  1. "house": a fresh data dir. Verifies doors/lights/presence/path in the WS
     `home` messages, /api/home without a browse service, operator settings
     round-trip (403 without token, 400 on a bad mode), the WS feed and the
     bridge reflecting the change, bridge controls passthrough, and the bridge
     going stale after the backend is stopped.
  2. "privacy": a documented test-only start state written into the temp data
     dir before start (home.json: the actor at the bathroom node; life.json:
     activity use_bathroom with a far-future end). Verifies privacy end to end:
     WS stand-in pose, devices {"privacy": true}, unauthenticated /api/home
     masking, and the bridge publishing only the privacy fields.

    python tools/home_e2e_check.py [--timeout 90] [--keep]

Exit code 0 on success, 1 on a failed check, 2 when the server could not start
in time. The JSON report on stdout lists every check with its timing.
"""

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import home_interactions as hi  # noqa: E402

TOKEN = "e2e-local-operator-token"   # test-only credential for this temporary server
BRIDGE_STALE = 1.0
STARTED = []   # every child Popen, so callers can verify none is left running
BRIDGE_UNAVAILABLE = 6.0


class StartTimeout(RuntimeError):
    """The server (or bridge) did not become healthy before the deadline."""


class CheckFailed(AssertionError):
    pass


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_env():
    env = {k: v for k, v in os.environ.items()
           if k not in ("BROWSE", "BROWSE_SERVICE_URL", "BROWSE_SERVICE_TOKEN", "SITE_PASSWORD", "SITE_GATE",
                        "MINT", "PORT", "HOST")}
    env.update(HOME_ENABLED="1", HOME_ENTRYPOINT="1", MIND="0", CLIPS="0",
               SUB01_SPIKING_LIVE="0", SUB01_MINECRAFT="0", SUB01_DAY_LIVE="0",
               ANTHROPIC_API_KEY="", REPLICATE_API_TOKEN="", OPENROUTER_API_KEY="", OPENAI_API_KEY="",
               SUB01_POD_SECRET="", RUNPOD_API_KEY="", SUB01_ADMIN_TOKEN=TOKEN,
               PYTHONUNBUFFERED="1")
    return env


class Child:
    """A child process in its own session; always killed (group) on close."""

    def __init__(self, name, argv, env, log_dir):
        self.name = name
        self.log_path = Path(log_dir) / f"{name}.log"
        self.log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
        STARTED.append(self.proc)

    def alive(self):
        return self.proc.poll() is None

    def stop(self, grace=5.0):
        if self.proc.poll() is None:
            for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 5.0)):
                try:
                    os.killpg(self.proc.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    self.proc.wait(wait)
                    break
                except subprocess.TimeoutExpired:
                    continue
        self.log.close()

    def tail(self, n=30):
        try:
            return "\n".join(self.log_path.read_text(errors="replace").splitlines()[-n:])
        except OSError:
            return ""


class Report:
    def __init__(self):
        self.t0 = time.monotonic()
        self.checks = []
        self.timings = {}

    def ok(self, name, condition, detail=None):
        entry = {"check": name, "ok": bool(condition), "t": round(time.monotonic() - self.t0, 2)}
        if detail is not None:
            entry["detail"] = detail
        self.checks.append(entry)
        if not condition:
            raise CheckFailed(f"{name}: {detail}")

    def mark(self, name):
        self.timings[name] = round(time.monotonic() - self.t0, 2)


async def wait_healthy(session, url, child, deadline):
    while time.monotonic() < deadline:
        if not child.alive():
            raise StartTimeout(f"{child.name} exited early:\n{child.tail()}")
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as r:
                if r.status == 200:
                    return
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass
        await asyncio.sleep(0.25)
    raise StartTimeout(f"{child.name} not healthy at {url} before the deadline:\n{child.tail()}")


async def home_messages(session, base, count, until=None, timeout=15.0):
    """Collect real /ws `tick` messages carrying `home`."""
    out = []
    end = time.monotonic() + timeout
    async with session.ws_connect(base.replace("http", "ws") + "/ws?rate=5&lite=1", max_msg_size=0) as ws:
        while time.monotonic() < end and len(out) < count:
            try:
                msg = await ws.receive(timeout=max(0.1, end - time.monotonic()))
            except asyncio.TimeoutError:
                break
            if msg.type != aiohttp.WSMsgType.TEXT:
                if msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    break
                continue
            data = json.loads(msg.data)
            if data.get("type") == "tick" and isinstance(data.get("home"), dict):
                out.append(data["home"])
                if until and until(data["home"]):
                    return out
    return out


async def bridge_doc(session, base, **query):
    async with session.get(base + "/home/state", params=query, headers={"X-Admin-Token": TOKEN}) as r:
        return r.status, await r.json()


async def wait_bridge(session, base, predicate, timeout):
    end = time.monotonic() + timeout
    doc = None
    while time.monotonic() < end:
        status, doc = await bridge_doc(session, base)
        if status == 200 and predicate(doc):
            return doc
        await asyncio.sleep(0.2)
    return doc


def start_backend(data_dir, log_dir, name):
    port = free_port()
    argv = [sys.executable, str(ROOT / "live_server.py"), "--host", "127.0.0.1", "--port", str(port),
            # Clock ignores --start at exactly x1, so run a hair faster to pin a
            # deterministic awake afternoon (15:00 Tokyo) whatever the real time.
            "--data-dir", str(data_dir), "--start", "15:00", "--time-scale", "1.001"]
    return Child(name, argv, server_env(), log_dir), f"http://127.0.0.1:{port}"


def start_bridge(backend, log_dir, name):
    port = free_port()
    argv = [sys.executable, str(ROOT / "tools/unreal_home_state_bridge.py"), "--port", str(port),
            "--backend", backend, "--stale-after", str(BRIDGE_STALE),
            "--unavailable-after", str(BRIDGE_UNAVAILABLE)]
    env = server_env()
    return Child(name, argv, env, log_dir), f"http://127.0.0.1:{port}"


def seed_privacy(data_dir):
    """Documented test-only start state: he is in the bathroom, staying there."""
    (data_dir / "home.json").write_text(json.dumps({"navigation_version": 2, "node": "bathroom"}))
    (data_dir / "life.json").write_text(json.dumps({"place": "window", "activity": "use_bathroom",
                                                    "until": 1e13}))


async def house_run(rep, session, tmp, deadline):
    data = tmp / "house-data"
    data.mkdir()
    backend, base = start_backend(data, tmp, "backend-house")
    bridge = None
    try:
        await wait_healthy(session, base + "/healthz", backend, deadline)
        rep.mark("house_backend_healthy")
        async with session.get(base + "/api/home") as r:
            rep.ok("api_home_200_without_browse", r.status == 200, r.status)
            full = await r.json()
        rep.ok("api_home_no_screens_without_browse",
               full.get("browser_screen") is None and full.get("phone_browser_screen") is None,
               [full.get("browser_screen"), full.get("phone_browser_screen")])
        homes = await home_messages(session, base, 5)
        rep.ok("ws_home_messages", len(homes) >= 3, len(homes))
        h = homes[-1]
        rep.ok("ws_home_fields", all(k in h for k in ("doors", "lights", "presence", "path", "privacy")),
               sorted(h))
        rep.ok("ws_doors_shape", set(h["doors"]) == set(hi.DOOR_NAMES) and all(
            d["state"] in hi.DOOR_STATES and d["mode"] in hi.DOOR_MODES for d in h["doors"].values()), h["doors"])
        rep.ok("ws_lights_shape", set(h["lights"]["rooms"]) == set(hi.LIGHT_ROOMS), h["lights"])
        rep.ok("ws_presence_and_path", h["presence"] in hi.PRESENCE and isinstance(h["path"], list),
               [h["presence"], h["path"]])
        rep.ok("ws_not_private", h["privacy"] is False and "computer" in h["devices"], h.get("devices"))

        patch = {"doors": {"balcony": "open"}, "lights": {"kitchen": "on", "bedroom": "off"}}
        async with session.post(base + "/api/home/settings", json=patch) as r:
            rep.ok("settings_403_without_token", r.status == 403, r.status)
        bad = {"doors": {"balcony": "ajar"}}
        async with session.post(base + "/api/home/settings", json=bad, headers={"X-Admin-Token": TOKEN}) as r:
            rep.ok("settings_400_bad_mode", r.status == 400, r.status)
        async with session.post(base + "/api/home/settings", json=patch, headers={"X-Admin-Token": TOKEN}) as r:
            body = await r.json() if r.status == 200 else await r.text()
            rep.ok("settings_round_trip", r.status == 200 and body["doors"]["balcony"] == "open"
                   and body["lights"]["kitchen"] == "on" and body["lights"]["bedroom"] == "off", body)
        changed = await home_messages(session, base, 50, until=lambda m: (
            m["doors"]["balcony"]["mode"] == "open" and m["doors"]["balcony"]["open"]
            and m["lights"]["rooms"]["kitchen"]["on"] and not m["lights"]["rooms"]["bedroom"]["on"]))
        rep.ok("ws_reflects_settings", bool(changed) and changed[-1]["doors"]["balcony"]["open"] is True
               and changed[-1]["lights"]["rooms"]["kitchen"]["on"] is True,
               changed[-1]["doors"]["balcony"] if changed else None)
        rep.mark("house_settings_verified")

        bridge, bbase = start_bridge(base, tmp, "bridge-house")
        await wait_healthy(session, bbase + "/healthz", bridge, deadline)
        async with session.get(bbase + "/home/state") as r:
            rep.ok("bridge_403_without_token", r.status == 403, r.status)
        doc = await wait_bridge(session, bbase, lambda d: d["source"]["status"] == "live", 10)
        rep.ok("bridge_live", doc["source"]["status"] == "live", doc["source"])
        rep.ok("bridge_house_fields", doc["doors"]["balcony"]["mode"] == "open"
               and doc["lights"]["rooms"]["kitchen"]["on"] is True and doc["privacy"] is False
               and doc["actor"] is not None, {k: doc[k] for k in ("doors", "privacy")})
        rep.ok("bridge_no_position_fields", not any(k in json.dumps(doc) for k in
                                                     ('"position"', '"entry_position"', '"look"')))
        async with session.post(bbase + "/home/controls", json={"doors": {"front": "open"}},
                                headers={"X-Admin-Token": TOKEN}) as r:
            body = await r.json()
            rep.ok("bridge_controls_passthrough", r.status == 200 and body["doors"]["front"] == "open", body)
        async with session.post(bbase + "/home/controls", json={"doors": {"front": "ajar"}},
                                headers={"X-Admin-Token": TOKEN}) as r:
            rep.ok("bridge_controls_400", r.status == 400, r.status)
        doc = await wait_bridge(session, bbase, lambda d: (d.get("doors") or {}).get("front", {}).get("open") is True, 10)
        rep.ok("bridge_reflects_control", doc["doors"]["front"] == {"open": True, "locked": False, "mode": "open"},
               doc["doors"]["front"])
        async with session.get(base + "/api/home") as r:
            rep.ok("backend_reflects_control", (await r.json())["home"]["settings"]["doors"]["front"] == "open")
        rep.mark("house_bridge_verified")

        stopped = time.monotonic()
        backend.stop()
        rep.timings["backend_graceful_stop_s"] = round(time.monotonic() - stopped, 2)
        doc = await wait_bridge(session, bbase, lambda d: d["source"]["status"] != "live", 10)
        rep.ok("bridge_stale_after_backend_stop", doc["source"]["status"] == "stale"
               and doc["brain"] is None and doc["destinations"] is None, doc["source"])
        rep.timings["bridge_not_live_after_stop_request_s"] = round(time.monotonic() - stopped, 2)
        doc = await wait_bridge(session, bbase, lambda d: d["source"]["status"] == "unavailable",
                                BRIDGE_UNAVAILABLE + 5)
        rep.ok("bridge_unavailable_later", doc["source"]["status"] == "unavailable"
               and doc["doors"] is None and doc["actor"] is None, doc["source"])
        rep.mark("house_done")
    finally:
        if bridge:
            bridge.stop()
        backend.stop()


async def privacy_run(rep, session, tmp, deadline):
    data = tmp / "privacy-data"
    data.mkdir()
    seed_privacy(data)
    backend, base = start_backend(data, tmp, "backend-privacy")
    bridge = None
    try:
        await wait_healthy(session, base + "/healthz", backend, deadline)
        rep.mark("privacy_backend_healthy")
        homes = await home_messages(session, base, 5)
        rep.ok("privacy_ws_messages", len(homes) >= 3, len(homes))
        rep.ok("privacy_ws_flag", all(m["privacy"] is True for m in homes), [m["privacy"] for m in homes])
        for key, value in hi.PRIVATE_ACTOR.items():
            rep.ok(f"privacy_ws_{key}", all(m[key] == value for m in homes), homes[-1][key])
        rep.ok("privacy_ws_devices", all(m["devices"] == {"privacy": True} for m in homes), homes[-1]["devices"])
        rep.ok("privacy_ws_phone_app", homes[-1]["phone"]["app"] == "home", homes[-1]["phone"])
        rep.ok("privacy_bathroom_locked", homes[-1]["doors"]["bathroom"]["state"] == "locked",
               homes[-1]["doors"]["bathroom"])
        async with session.get(base + "/api/home") as r:
            full = await r.json()
        rep.ok("privacy_api_unauthenticated_pose", full["home"]["position"] == hi.PRIVATE_ACTOR["position"]
               and full["home"]["privacy"] is True, full["home"]["position"])
        rep.ok("privacy_api_computer_masked", full["computer"].get("privacy") is True
               and full["computer"].get("output") == "", {k: full["computer"].get(k) for k in ("privacy", "output")})
        async with session.post(base + "/api/home/computer", json={"input": "ls"},
                                headers={"X-Admin-Token": TOKEN}) as r:
            rep.ok("privacy_api_refuses_input", r.status == 409, r.status)
        async with session.post(base + "/api/home/settings", json={"doors": {"bathroom": "open"}},
                                headers={"X-Admin-Token": TOKEN}) as r:
            rep.ok("privacy_operator_open_saved", r.status == 200, r.status)
        homes = await home_messages(session, base, 3)
        rep.ok("privacy_bathroom_stays_locked", homes and homes[-1]["doors"]["bathroom"]["state"] == "locked"
               and homes[-1]["doors"]["bathroom"]["mode"] == "open", homes[-1]["doors"]["bathroom"] if homes else None)
        rep.mark("privacy_backend_verified")

        bridge, bbase = start_bridge(base, tmp, "bridge-privacy")
        await wait_healthy(session, bbase + "/healthz", bridge, deadline)
        doc = await wait_bridge(session, bbase, lambda d: d["source"]["status"] == "live", 10)
        rep.ok("privacy_bridge_live", doc["source"]["status"] == "live", doc["source"])
        rep.ok("privacy_bridge_only_flag_and_house", doc["privacy"] is True and doc["actor"] is None
               and doc["brain"] is None and doc["destinations"] is None
               and doc["doors"]["bathroom"]["locked"] is True, {k: doc[k] for k in ("privacy", "actor", "brain")})
        text = json.dumps(doc)
        rep.ok("privacy_bridge_no_leaks", not any(w in text for w in ("use_bathroom", "bath_door", "devices",
                                                                      "activity", "phone")))
        rep.mark("privacy_done")
    finally:
        if bridge:
            bridge.stop()
        backend.stop()


async def run_check(timeout=90.0, keep=False, privacy=True):
    """Whole check bounded by `timeout` seconds; children are always killed."""
    try:
        return await asyncio.wait_for(_run_check(timeout, keep, privacy), timeout)
    except asyncio.TimeoutError:
        raise CheckFailed(f"the end-to-end check exceeded {timeout} s")


async def _run_check(timeout, keep, privacy):
    rep = Report()
    tmp = Path(tempfile.mkdtemp(prefix="sub01-home-e2e-"))
    if ROOT in tmp.resolve().parents:
        raise RuntimeError("temporary data dir must be outside the repository")
    deadline = time.monotonic() + timeout
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            await house_run(rep, session, tmp, deadline)
            if privacy:
                await privacy_run(rep, session, tmp, deadline)
        rep.mark("total")
        return {"ok": True, "checks": rep.checks, "timings": rep.timings}
    finally:
        if keep:
            print(f"kept logs and data in {tmp}", file=sys.stderr)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--keep", action="store_true", help="keep the temp data dir and child logs")
    parser.add_argument("--no-privacy", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(run_check(args.timeout, args.keep, not args.no_privacy))
    except StartTimeout as error:
        print(json.dumps({"ok": False, "start_timeout": str(error)[-2000:]}))
        return 2
    except CheckFailed as error:
        print(json.dumps({"ok": False, "failed": str(error)[-2000:]}))
        return 1
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
