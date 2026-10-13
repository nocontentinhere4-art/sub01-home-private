"""Private home-state -> native Unreal bridge (loopback only).

Reads the real, running home backend (live_server.py) and republishes the
house state that a native Unreal client needs as one small, versioned JSON
document with a monotonic revision:

    backend  GET /api/home            full state on start and every reconnect
             WS  /ws?rate=5&lite=1    `tick` messages carrying `home` (+ sleep stage)
    bridge   GET /home/state[?since=REV&wait=S]   (X-Admin-Token)
             POST /home/controls {"doors":{..},"lights":{..}} -> POST /api/home/settings
             GET /healthz

Rules this module keeps:
- It never invents brain state. `brain` appears only while the backend feed is
  live; a quiet feed is reported as "stale", then "unavailable".
- It never emits a position command. The actor is described by the graph node
  he last reached, the node he is heading to and the remaining route
  waypoints (converted to Unreal centimetres with the existing
  tools/unreal_home_coordinates.py). The native pawn must walk there with
  CharacterMovement; there is no field it could teleport to.
- During bathroom privacy only the flag and non-identifying house fields
  (doors, lights, presence) are published: no activity, stage, route or node.
- Loopback bind only, operator credential (>= 12 chars) compared with hmac,
  never printed, access log off. The backend URL must be loopback as well.

Library use: HomeStateModel (pure state -> document), BackendFeed (WS + REST
consumer with reconnect backoff), create_app (aiohttp app). CLI: main().
"""

import argparse
import asyncio
import hmac
import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import home_interactions as hi  # noqa: E402  (validation + floor constants only)
from home_world import EDGES, NODES, route  # noqa: E402  (read-only graph)
from unreal_home_coordinates import convert_position, infer_import_transform  # noqa: E402

SCHEMA = "sub01.home-state.v1"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MIN_TOKEN = 12
MAX_WAIT = 25.0
MAX_BODY = 4096
STALE_AFTER = 3.0        # seconds without a backend home message -> "stale"
UNAVAILABLE_AFTER = 15.0  # ... -> "unavailable" (nothing but the status is published)
EYE_HEIGHT_M = 1.65      # home_world.NODES are walking-eye points; waypoints are published on the floor
# Fields the bridge must never publish (they would let a client teleport the pawn).
FORBIDDEN_KEYS = frozenset({"position", "entry_position", "look", "location", "teleport",
                            "set_position", "transform"})

# Documented source -> Unreal pivot pairs (metres -> centimetres). They come
# from evidence already recorded in this repository:
#  - the PC monitor screen centre, tools/native_pc_bridge/README.md:
#    source (2, 1.16, -3.276) -> UE (200, -327.6, 116);
#  - the native route checkpoints in tools/unreal_native_route.py that the
#    actual CharacterMovement test reached (stair_bottom, bed), taken at floor
#    level (capsule centre 96 cm minus its 96 cm half height; ground floor 0 m,
#    upper floor 3 m as in home_interactions.UPPER_FLOOR).
# infer_import_transform() must find exactly one 100 cm/m solution for them.
# A transform written by the actual UE coordinate audit can replace these
# with --transform-file (see docs/unreal-home-state-bridge.md).
DEFAULT_PIVOTS = (
    ((2.0, 1.16, -3.276), (200.0, -327.6, 116.0)),
    ((0.3, 0.0, 2.55), (30.0, 255.0, 0.0)),
    ((-1.2, 3.0, -2.9), (-120.0, -290.0, 300.0)),
)


def default_transform():
    found = infer_import_transform(list(DEFAULT_PIVOTS))
    return {**found, "source": "documented-pivots"}


def load_transform(path):
    """A JSON file with either {"pairs": [[src_m, ue_cm], ...]} (re-verified
    here) or the dict that infer_import_transform returned (axes, signs,
    offset_cm, scale_cm_per_meter == 100), e.g. written by the UE setup."""
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "pairs" in data:
        found = infer_import_transform([(tuple(a), tuple(b)) for a, b in data["pairs"]])
        return {**found, "source": "file-pairs"}
    if not (isinstance(data, dict) and data.get("scale_cm_per_meter") == 100
            and sorted(data.get("axes", [])) == [0, 1, 2]
            and len(data.get("signs", [])) == 3 and all(s in (-1, 1) for s in data["signs"])
            and len(data.get("offset_cm", [])) == 3
            and all(isinstance(v, (int, float)) and math.isfinite(v) for v in data["offset_cm"])):
        raise ValueError("transform file is not a verified 100 cm/m import transform")
    return {"axes": tuple(data["axes"]), "signs": tuple(data["signs"]),
            "offset_cm": tuple(float(v) for v in data["offset_cm"]),
            "scale_cm_per_meter": 100, "source": "file-transform"}


def waypoint(node, transform):
    """A graph node as a floor-level Unreal waypoint (cm). Not a pose command."""
    x, y, z = NODES[node]
    floor = y - EYE_HEIGHT_M
    ue = convert_position((x, floor, z), transform)
    return {"node": node,
            "level": "upper" if y > hi.UPPER_FLOOR else "ground",
            "floor_cm": [round(v, 1) for v in ue]}


_NEIGHBOURS = {}
for _a, _b in EDGES:
    _NEIGHBOURS.setdefault(_a, []).append(_b)
    _NEIGHBOURS.setdefault(_b, []).append(_a)


def _segment_distance(p, a, b):
    """Distance from p to segment a->b when p lies strictly past a, else None."""
    ab = [q - r for q, r in zip(b, a)]
    ap = [q - r for q, r in zip(p, a)]
    length2 = sum(v * v for v in ab)
    if length2 < 1e-9:
        return None
    t = sum(u * v for u, v in zip(ap, ab)) / length2
    if t <= 0 or t > 1 + 1e-6 or math.dist(p, a) < 1e-4:
        return None
    closest = [r + t * v for r, v in zip(a, ab)]
    return math.dist(closest, p)


# The view rounds positions to 0.1 mm; edges leaving a node can be almost
# collinear (kitchen_gate -> kitchen / sofa_rear_approach), so keep this tight.
SEGMENT_TOLERANCE_M = 1e-3


def remaining_route(home):
    """Remaining node names to walk, and where they came from.

    Uses home["path"] when the backend publishes it. The current
    HomeWorld.view() does not, so otherwise the route is re-derived from the
    same deterministic graph search (home_world.route) the backend uses: from
    the node the actor is currently walking towards (the edge his walking
    position lies on), else from the node he last reached."""
    path = home.get("path")
    if isinstance(path, list) and all(n in NODES for n in path):
        return list(path), "backend"
    place, target = home.get("place"), home.get("destination")
    if place not in NODES or target not in NODES:
        return [], "derived-route-graph"
    try:
        planned = route(place, target)[1:] if place != target else []
    except ValueError:
        return [], "derived-route-graph"
    walking_at = home.get("entry_position")
    candidates = []
    if isinstance(walking_at, list) and hi.finite_position(walking_at):
        for n in _NEIGHBOURS.get(place, []):
            d = _segment_distance(walking_at, NODES[place], NODES[n])
            if d is not None and d <= SEGMENT_TOLERANCE_M:
                candidates.append((d, n))
    # Usual case: walking the planned first edge. Otherwise the actor is on
    # an edge he was already walking when the target changed (HomeWorld
    # finishes it, then replans from its end node).
    if not candidates or (planned and planned[0] in [n for _, n in candidates]):
        return planned, "derived-route-graph"
    nxt = min(candidates)[1]
    return [nxt] + route(nxt, target)[1:], "derived-route-graph"


class HomeStateModel:
    """Latest real backend state -> versioned document. No I/O."""

    def __init__(self, transform=None, clock=time.monotonic,
                 stale_after=STALE_AFTER, unavailable_after=UNAVAILABLE_AFTER,
                 backend_host="127.0.0.1"):
        self.transform = transform or default_transform()
        self.clock = clock
        self.stale_after, self.unavailable_after = stale_after, unavailable_after
        self.backend_host = backend_host
        self.epoch = uuid.uuid4().hex[:12]   # changes when the bridge restarts
        self.connected = False
        self.home = None
        self.stage = None
        self.received_at = None
        self.revision = 0
        self._key = None
        self._doc = None
        self._changed = asyncio.Event()
        self.refresh()

    # ---- inputs from the backend -----------------------------------------
    def apply_rest(self, data):
        """GET /api/home body: {"home": view(), "stage": ..., ...}."""
        if isinstance(data, dict) and isinstance(data.get("home"), dict):
            self.home = data["home"]
            stage = data.get("stage")
            self.stage = stage if isinstance(stage, str) else None
            self.received_at = self.clock()
        return self.refresh()

    def apply_tick(self, msg):
        """A WebSocket `tick` that carries `home` (compact view)."""
        if not (isinstance(msg, dict) and msg.get("type") == "tick" and isinstance(msg.get("home"), dict)):
            return False
        self.home = msg["home"]
        sleep = msg.get("sleep")
        self.stage = sleep.get("stage") if isinstance(sleep, dict) and isinstance(sleep.get("stage"), str) else None
        self.received_at = self.clock()
        return self.refresh()

    def set_connected(self, connected):
        self.connected = bool(connected)
        return self.refresh()

    # ---- document --------------------------------------------------------
    def status(self):
        if self.home is None or self.received_at is None:
            return "unavailable", None
        age = max(0.0, self.clock() - self.received_at)
        if self.connected and age <= self.stale_after:
            return "live", age
        if age <= self.unavailable_after:
            return "stale", age
        return "unavailable", age

    def _body(self, status):
        home = self.home or {}
        doc = {"schema": SCHEMA, "epoch": self.epoch,
               "source": {"status": status, "backend_url_host": self.backend_host},
               "privacy": None, "brain": None, "actor": None,
               "destinations": None, "doors": None, "lights": None, "presence": None,
               "coordinates": {"units": "cm", "frame": "unreal-world",
                               "waypoint_height": "floor",
                               "transform_source": self.transform.get("source", "unknown")}}
        if status == "unavailable":
            return doc   # nothing about the house is known well enough to publish
        privacy = bool(home.get("privacy"))
        doc["privacy"] = privacy
        doc["presence"] = home.get("presence") if home.get("presence") in hi.PRESENCE else None
        doors = home.get("doors")
        if isinstance(doors, dict):
            doc["doors"] = {n: {k: doors[n].get(k) for k in ("open", "locked", "mode")}
                            for n in hi.DOOR_NAMES if isinstance(doors.get(n), dict)}
        lights = home.get("lights")
        if isinstance(lights, dict) and isinstance(lights.get("rooms"), dict):
            doc["lights"] = {"master": lights.get("master"), "dark": lights.get("dark"),
                             "rooms": {r: {k: lights["rooms"][r].get(k) for k in ("on", "mode")}
                                       for r in hi.LIGHT_ROOMS if isinstance(lights["rooms"].get(r), dict)}}
        if privacy:
            return doc   # flag + doors/lights/presence only
        names, path_source = remaining_route(home)
        place, target = home.get("place"), home.get("destination")
        seated = home.get("seated")
        doc["actor"] = {
            "node": place if place in NODES else None,
            "target": target if target in NODES else None,
            "path": [waypoint(n, self.transform) for n in names],
            "path_source": path_source,
            "seated": round(float(seated), 3) if isinstance(seated, (int, float)) and math.isfinite(seated) else None,
            "moving": bool(home.get("walking")),
            # Owner decision 2026-10-13: hide his body while he is out of the house.
            "visible": home.get("presence") != "away",
            "route_sequence": home.get("sequence") if isinstance(home.get("sequence"), int) else None,
        }
        if status == "live":
            activity = home.get("activity")
            doc["brain"] = {"stage": self.stage, "activity": activity if isinstance(activity, str) else None}
            doc["destinations"] = {
                "mode": "walk",
                "next": doc["actor"]["path"][0] if names else None,
                "final": waypoint(target, self.transform) if target in NODES else None,
            }
        return doc

    def refresh(self):
        """Recompute; bump the revision only when the published content changed."""
        status, age = self.status()
        body = self._body(status)
        key = json.dumps(body, sort_keys=True, separators=(",", ":"))
        changed = key != self._key
        if changed:
            self._key = key
            self.revision += 1
            self._doc = body
            self._changed.set()
            self._changed = asyncio.Event()
        return changed

    def document(self):
        self.refresh()
        status, age = self.status()
        doc = json.loads(json.dumps(self._doc))
        doc["revision"] = self.revision
        doc["source"]["last_message_age_s"] = None if age is None else round(age, 2)
        return doc

    async def wait_for_change(self, since, wait):
        deadline = self.clock() + max(0.0, min(MAX_WAIT, wait))
        while self.revision == since:
            remaining = deadline - self.clock()
            if remaining <= 0:
                break
            event = self._changed
            try:
                # Wake at least every 0.5 s so status ageing is noticed.
                await asyncio.wait_for(event.wait(), timeout=min(remaining, 0.5))
            except asyncio.TimeoutError:
                self.refresh()
        return self.document()


def check_loopback_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.hostname not in LOOPBACK:
        raise ValueError("the backend must be a loopback http(s) URL")
    return parts


class BackendFeed:
    """Consumes the real backend: REST snapshot, then the lite WebSocket feed."""

    def __init__(self, model, backend_url, token, backoff=(0.5, 10.0), sleep=asyncio.sleep):
        check_loopback_url(backend_url)
        self.model = model
        self.base = backend_url.rstrip("/")
        self._token = token
        self.backoff = backoff
        self.sleep = sleep
        self.connects = 0
        self.failures = 0
        self.snapshot_failures = 0

    def headers(self):
        return {"X-Admin-Token": self._token}

    async def snapshot(self, session):
        async with session.get(self.base + "/api/home", headers=self.headers()) as resp:
            if resp.status != 200:
                raise aiohttp.ClientResponseError(resp.request_info, (), status=resp.status)
            self.model.apply_rest(await resp.json())

    async def run_once(self, session):
        try:
            await self.snapshot(session)
        except (aiohttp.ClientResponseError, aiohttp.ContentTypeError, ValueError):
            # The backend answered but the snapshot failed (e.g. GET /api/home
            # returns 500 when the screens browser is off). The WS feed carries
            # the same `home` view, so continue; only a refused connection aborts.
            self.snapshot_failures += 1
        ws_url = self.base.replace("http", "ws", 1) + "/ws?rate=5&lite=1"
        async with session.ws_connect(ws_url, headers=self.headers(), heartbeat=20,
                                      max_msg_size=4 * 1024 * 1024) as ws:
            self.connects += 1
            self.failures = 0
            self.model.set_connected(True)
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                self.model.apply_tick(data)

    async def run(self, session=None, stop=None):
        own = session is None
        session = session or aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=5))
        try:
            while not (stop and stop.is_set()):
                try:
                    await self.run_once(session)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass   # never log the URL headers / credential; status carries the outcome
                self.model.set_connected(False)
                self.failures += 1
                delay = min(self.backoff[1], self.backoff[0] * 2 ** (self.failures - 1))
                await self.sleep(delay)
        finally:
            self.model.set_connected(False)
            if own:
                await session.close()

    async def post_settings(self, session, patch):
        async with session.post(self.base + "/api/home/settings", json=patch,
                                headers=self.headers()) as resp:
            text = await resp.text()
            return resp.status, text

    async def post_native_state(self, session, report):
        async with session.post(self.base + '/api/home/native_state', json=report,
                                headers=self.headers(), allow_redirects=False) as resp:
            return resp.status, await resp.text()


async def read_json(request):
    if request.content_length is not None and request.content_length > MAX_BODY:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY, actual_size=request.content_length)
    raw = await request.content.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY, actual_size=len(raw))
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Expected object")
    return data


def validate_controls(data):
    """Only door / light-room operator modes, validated exactly like home_api."""
    if not data or set(data) - {"doors", "lights"}:
        raise ValueError("Use {\"doors\": {...}} and/or {\"lights\": {...}} only")
    patch = {}
    if "doors" in data:
        patch["doors"] = hi.validate_modes(data["doors"], hi.DOOR_NAMES, hi.DOOR_MODES, "door")
    if "lights" in data:
        patch["lights"] = hi.validate_modes(data["lights"], hi.LIGHT_ROOMS, hi.LIGHT_MODES, "light room")
    return patch


SESSION = web.AppKey("session", aiohttp.ClientSession)


def create_app(model, token, feed=None, session_factory=None, ticker=0.5):
    if not isinstance(token, str) or len(token) < MIN_TOKEN:
        raise ValueError("operator credential must be at least 12 characters")
    secret = token.encode()

    def authorized(request):
        got = request.headers.get("X-Admin-Token") or request.headers.get("Authorization", "").removeprefix("Bearer ")
        return hmac.compare_digest(got.strip().encode(), secret)

    @web.middleware
    async def guard(request, handler):
        if request.path != "/healthz" and not authorized(request):
            return web.Response(status=403, text="Operator authentication required",
                                headers={"Cache-Control": "no-store"})
        resp = await handler(request)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    async def healthz(request):
        return web.json_response({"ok": True})

    async def state(request):
        since = request.query.get("since")
        if since is None:
            return web.json_response(model.document())
        try:
            since_rev = int(since)
            wait = float(request.query.get("wait", "20"))
        except ValueError:
            raise web.HTTPBadRequest(text="since must be an integer and wait a number")
        if not math.isfinite(wait) or wait < 0:
            raise web.HTTPBadRequest(text="wait must be a non-negative number")
        return web.json_response(await model.wait_for_change(since_rev, wait))

    async def controls(request):
        data = await read_json(request)
        try:
            patch = validate_controls(data)
        except ValueError as error:
            raise web.HTTPBadRequest(text=str(error))
        if feed is None:
            raise web.HTTPServiceUnavailable(text="No backend configured")
        session = request.app[SESSION]
        try:
            status, text = await feed.post_settings(session, patch)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise web.HTTPServiceUnavailable(text="Home backend unavailable")
        if status != 200:
            # The backend decides (e.g. 403 bad credential, 400 invalid, 404 home disabled).
            return web.json_response({"ok": False, "backend_status": status}, status=502)
        try:
            settings = json.loads(text)
        except ValueError:
            settings = {}
        return web.json_response({"ok": True,
                                  "doors": settings.get("doors"), "lights": settings.get("lights"),
                                  "note": "Operator modes accepted by the backend; the published state follows its next tick."})

    async def native_state(request):
        # Check the actual peer, never forwarded address headers.
        import ipaddress
        try:
            local = ipaddress.ip_address(request.remote or '').is_loopback
        except ValueError:
            local = False
        if not local:
            raise web.HTTPForbidden(text='Native feedback requires loopback')
        data = await read_json(request)
        doc = model.document()
        actor, brain = doc.get('actor') or {}, doc.get('brain') or {}
        if (doc['source']['status'] != 'live' or doc.get('privacy') is not False
                or data.get('epoch') != model.epoch
                or type(data.get('sequence')) is not int
                or data['sequence'] != actor.get('route_sequence')
                or data.get('activity') != brain.get('activity')):
            raise web.HTTPConflict(text='Native feedback does not match live command')
        if feed is None:
            raise web.HTTPServiceUnavailable(text='No backend configured')
        try:
            status, text = await feed.post_native_state(request.app[SESSION], data)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            raise web.HTTPServiceUnavailable(text='Home backend unavailable')
        if status != 200:
            error = {400: web.HTTPBadRequest, 403: web.HTTPForbidden,
                     409: web.HTTPConflict, 503: web.HTTPServiceUnavailable}.get(status, web.HTTPBadGateway)
            raise error(text='Native feedback refused by backend')
        return web.json_response({'ok': True, 'fresh_for_s': 3})

    async def lifecycle(app):
        app[SESSION] = (session_factory or (lambda: aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10))))()
        tasks = []
        if feed is not None:
            tasks.append(asyncio.create_task(feed.run(session=app[SESSION])))

        async def tick():
            while True:
                await asyncio.sleep(ticker)
                model.refresh()   # status ageing moves the revision and wakes long-polls
        tasks.append(asyncio.create_task(tick()))
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await app[SESSION].close()

    app = web.Application(middlewares=[guard], client_max_size=MAX_BODY)
    app.cleanup_ctx.append(lifecycle)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/home/state", state)
    app.router.add_post("/home/controls", controls)
    app.router.add_post('/home/native_state', native_state)
    return app


def load_token(token_file):
    if token_file:
        return Path(token_file).read_text().strip()
    return os.environ.get("SUB01_ADMIN_TOKEN", "").strip()


async def serve(args, token):
    backend_host = check_loopback_url(args.backend).hostname
    transform = load_transform(args.transform_file) if args.transform_file else default_transform()
    model = HomeStateModel(transform, stale_after=args.stale_after,
                           unavailable_after=args.unavailable_after, backend_host=backend_host)
    feed = BackendFeed(model, args.backend, token)
    app = create_app(model, token, feed)
    runner = web.AppRunner(app, access_log=None)   # request lines (and headers) are never logged
    await runner.setup()
    await web.TCPSite(runner, args.host, args.port).start()
    print(f"home-state bridge on http://{args.host}:{args.port} (backend {backend_host}, "
          f"transform {transform['source']})", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    import signal
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await stop.wait()
    await runner.cleanup()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8811)
    parser.add_argument("--backend", default="http://127.0.0.1:8765",
                        help="loopback URL of the running home backend (live_server.py)")
    parser.add_argument("--token-file", help="file holding the existing operator credential")
    parser.add_argument("--transform-file", help="verified UE import transform or pivot pairs (JSON)")
    parser.add_argument("--stale-after", type=float, default=STALE_AFTER)
    parser.add_argument("--unavailable-after", type=float, default=UNAVAILABLE_AFTER)
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK:
        parser.error("the home-state bridge binds only to loopback")
    try:
        check_loopback_url(args.backend)
    except ValueError as error:
        parser.error(str(error))
    if not 0 < args.stale_after < args.unavailable_after:
        parser.error("need 0 < --stale-after < --unavailable-after")
    token = load_token(args.token_file)
    if len(token) < MIN_TOKEN:
        parser.error("set SUB01_ADMIN_TOKEN or --token-file (at least 12 characters)")
    return args, token


def main(argv=None):
    args, token = parse_args(argv)
    asyncio.run(serve(args, token))


if __name__ == "__main__":
    main()
