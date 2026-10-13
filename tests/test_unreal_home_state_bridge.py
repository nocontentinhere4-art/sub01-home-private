"""Private home-state -> native Unreal bridge: live/stale/unavailable, reconnect,
revisions, long-poll, privacy masking, auth, loopback, coordinates, passthrough."""

import asyncio
import json
import re
import sys
import time
from pathlib import Path

import pytest
from aiohttp import web, WSMsgType
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import unreal_home_state_bridge as bridge  # noqa: E402
from unreal_home_coordinates import convert_position  # noqa: E402
from home_world import HomeWorld, NODES  # noqa: E402

TOKEN = "operator-credential-test"
AUTH = {"X-Admin-Token": TOKEN}


def run(coro):
    asyncio.run(coro)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def walk(world, activity, seconds, dt=0.2):
    for _ in range(int(seconds / dt)):
        world.update(dt, dt, {"activity": activity}, {})


def tick(world, stage="AWAKE"):
    return {"type": "tick", "home": world.view(compact=True), "sleep": {"stage": stage}}


def keys(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from keys(v)
    elif isinstance(value, list):
        for v in value:
            yield from keys(v)


# ---- model ---------------------------------------------------------------

def test_live_stale_unavailable_transitions_never_fabricate():
    clock = Clock()
    model = bridge.HomeStateModel(clock=clock, stale_after=3, unavailable_after=15)
    doc = model.document()
    assert doc["source"]["status"] == "unavailable"
    assert doc["source"]["last_message_age_s"] is None
    assert all(doc[k] is None for k in ("brain", "actor", "destinations", "doors", "lights", "presence", "privacy"))

    world = HomeWorld()
    walk(world, "sleep", 4)
    model.set_connected(True)
    model.apply_tick(tick(world))
    live = model.document()
    assert live["source"]["status"] == "live"
    assert live["brain"] == {"stage": "AWAKE", "activity": "sleep"}
    assert live["destinations"]["final"]["node"] == "bed"
    assert live["actor"]["moving"] is True

    clock.t += 3.5
    stale = model.document()
    assert stale["source"]["status"] == "stale"
    assert stale["source"]["last_message_age_s"] == 3.5
    assert stale["brain"] is None and stale["destinations"] is None    # no route to act on
    assert stale["actor"]["node"] == live["actor"]["node"]             # last known, labelled stale
    assert stale["revision"] > live["revision"]

    clock.t += 12
    gone = model.document()
    assert gone["source"]["status"] == "unavailable"
    assert all(gone[k] is None for k in ("brain", "actor", "destinations", "doors", "lights"))

    # A fresh message while connected is live again; a disconnect is stale at once.
    model.apply_tick(tick(world))
    assert model.document()["source"]["status"] == "live"
    model.set_connected(False)
    assert model.document()["source"]["status"] == "stale"


def test_rest_snapshot_alone_is_not_live():
    clock = Clock()
    model = bridge.HomeStateModel(clock=clock)
    world = HomeWorld()
    model.apply_rest({"home": world.view(), "stage": "AWAKE"})
    doc = model.document()
    assert doc["source"]["status"] == "stale" and doc["brain"] is None
    model.set_connected(True)
    assert model.document()["brain"] == {"stage": "AWAKE", "activity": "research"}


def test_revision_is_monotonic_and_unchanged_when_state_is_unchanged():
    clock = Clock()
    model = bridge.HomeStateModel(clock=clock)
    model.set_connected(True)
    world = HomeWorld()
    model.apply_tick(tick(world))
    first = model.document()["revision"]
    for _ in range(5):
        clock.t += 0.2
        model.apply_tick(tick(world))                 # identical content, newer message
        assert model.document()["revision"] == first
    seen = [first]
    walk(world, "eat", 0.4)
    for _ in range(10):
        walk(world, "eat", 0.2)
        clock.t += 0.2
        model.apply_tick(tick(world))
        seen.append(model.document()["revision"])
    assert seen == sorted(seen) and seen[-1] > first
    model.apply_tick(tick(world, stage="NREM2"))
    assert model.document()["revision"] == seen[-1] + 1


def test_privacy_publishes_only_the_flag_and_house_fields():
    clock = Clock()
    model = bridge.HomeStateModel(clock=clock)
    model.set_connected(True)
    world = HomeWorld()
    walk(world, "use_bathroom", 60)
    view = world.view(compact=True)
    assert view["privacy"] is True and view["place"] == "bathroom"
    model.apply_tick({"type": "tick", "home": view, "sleep": {"stage": "AWAKE"}})
    doc = model.document()
    assert doc["privacy"] is True and doc["source"]["status"] == "live"
    assert doc["brain"] is None and doc["actor"] is None and doc["destinations"] is None
    assert doc["doors"]["bathroom"]["locked"] is True
    assert set(doc["lights"]["rooms"]) == {"living", "kitchen", "bedroom", "bathroom"}
    text = json.dumps(doc)
    # Room/door names are physical house state; activity, stage, route and devices are not published.
    for leak in ("use_bathroom", "AWAKE", "bath_door", "phone", "console", "devices", "floor_cm", "activity"):
        assert leak not in text
    # Devices sent by the backend during privacy never pass through either.
    model.apply_tick({"type": "tick", "home": {**view, "devices": {"privacy": True}}, "sleep": {"stage": "AWAKE"}})
    assert "devices" not in json.dumps(model.document())


def test_no_teleport_or_position_fields_in_any_state():
    clock = Clock()
    model = bridge.HomeStateModel(clock=clock)
    model.set_connected(True)
    world = HomeWorld()
    docs = [model.document()]
    for activity in ("sleep", "watch_tv", "use_bathroom", "park"):
        for _ in range(30):
            walk(world, activity, 1)
            clock.t += 1
            model.apply_tick(tick(world))
            docs.append(model.document())
    clock.t += 5
    docs.append(model.document())
    clock.t += 20
    docs.append(model.document())
    for doc in docs:
        assert not (set(keys(doc)) & bridge.FORBIDDEN_KEYS)
        if doc["destinations"]:
            assert doc["destinations"]["mode"] == "walk"


# ---- coordinates -----------------------------------------------------------

ROUTE_CHECKPOINTS = {   # tools/unreal_native_route.py RouteTargets, reached by the actual native pawn
    "front": (130, 320, 96), "stair_approach": (30, 320, 96), "stair_bottom": (30, 255, 96),
    "stair_top": (30, -170, 396), "landing": (30, -210, 396), "loft": (-50, -210, 396), "bed": (-120, -290, 396)}


def test_default_transform_uses_existing_coordinate_functions_and_matches_native_route():
    transform = bridge.default_transform()
    assert transform["axes"] == (0, 2, 1) and transform["signs"] == (1, 1, 1)
    assert transform["scale_cm_per_meter"] == 100 and transform["max_error_cm"] < 1e-6
    for node, (x, y, capsule_z) in ROUTE_CHECKPOINTS.items():
        point = bridge.waypoint(node, transform)
        assert point["floor_cm"][:2] == [x, y]
        assert point["floor_cm"][2] == capsule_z - 96          # floor under the native capsule centre
        assert point["level"] == ("upper" if capsule_z > 300 else "ground")
        src = NODES[node]
        expected = convert_position((src[0], src[1] - 1.65, src[2]), transform)
        assert point["floor_cm"] == [round(v, 1) for v in expected]
    # PC monitor screen centre recorded in tools/native_pc_bridge/README.md.
    assert [round(v, 3) for v in convert_position((2, 1.16, -3.276), transform)] == [200, -327.6, 116]


def test_transform_file_pairs_dict_and_refusal(tmp_path):
    rotated = {"axes": (2, 0, 1), "signs": (-1, 1, 1), "offset_cm": (50.0, -20.0, 4.0)}
    pairs = [[list(p), list(convert_position(p, rotated))] for p in ((0, 0, 0), (3, 0, 2), (-2, 3, 1))]
    f = tmp_path / "pairs.json"
    f.write_text(json.dumps({"pairs": pairs}))
    found = bridge.load_transform(f)
    assert found["source"] == "file-pairs" and found["axes"] == (2, 0, 1) and found["signs"] == (-1, 1, 1)
    bed = bridge.waypoint("bed", found)["floor_cm"]
    assert bed == [round(v, 1) for v in convert_position((-1.2, 3.0, -2.9), rotated)]
    g = tmp_path / "transform.json"
    g.write_text(json.dumps({**rotated, "scale_cm_per_meter": 100}))
    assert bridge.load_transform(g)["offset_cm"] == (50.0, -20.0, 4.0)
    g.write_text(json.dumps({**rotated, "scale_cm_per_meter": 1}))
    with pytest.raises(ValueError):
        bridge.load_transform(g)
    f.write_text(json.dumps({"pairs": [[[0, 0, 0], [0, 0, 0]], [[1, 0, 1], [100, 100, 0]]]}))
    with pytest.raises(ValueError):
        bridge.load_transform(f)


def test_derived_route_equals_backend_path_including_mid_edge_replans():
    world = HomeWorld()
    checked = 0
    for activity, seconds in (("eat", 0.7), ("research", 3), ("sleep", 3.1), ("eat", 6.3), ("watch_tv", 9.7), ("use_bathroom", 4.1),
                              ("window", 30), ("park", 12.3), ("research", 40)):
        for _ in range(int(seconds / 0.1)):
            world.update(0.1, 0.1, {"activity": activity}, {})
            view = world.view(compact=True)
            if not view["privacy"]:
                assert view["path"] == world.path, "the backend now publishes its own route"
            older = {k: v for k, v in view.items() if k != "path"}  # backends without `path`
            names, source = bridge.remaining_route(older)
            assert source == "derived-route-graph"
            assert names == world.path, (activity, world.node, world.position)
            checked += 1
    assert checked > 900
    # A backend that publishes its path is used as is.
    view = {**world.view(compact=True), "path": ["aisle", "back"]}
    assert bridge.remaining_route(view) == (["aisle", "back"], "backend")


# ---- HTTP: fake backend + bridge -------------------------------------------

class FakeBackend:
    """Same surface as live_server: GET /api/home, /ws?rate=5&lite=1, POST /api/home/settings."""

    def __init__(self):
        self.world = HomeWorld()
        self.sockets = set()
        self.rest_calls = 0
        self.ws_queries = []
        self.settings_posts = []
        self.settings_status = 200
        self.ws_headers = []
        self.rest_status = 200
        app = web.Application()
        app.router.add_get("/api/home", self.state)
        app.router.add_get("/ws", self.ws)
        app.router.add_post("/api/home/settings", self.settings)
        self.server = TestServer(app, host="127.0.0.1")

    async def state(self, request):
        self.rest_calls += 1
        if self.rest_status != 200:
            raise web.HTTPInternalServerError()
        return web.json_response({"home": self.world.view(), "stage": "AWAKE", "life": {}})

    async def ws(self, request):
        self.ws_queries.append(dict(request.query))
        self.ws_headers.append(request.headers.get("X-Admin-Token"))
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "hello"})
        self.sockets.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            self.sockets.discard(ws)
        return ws

    async def settings(self, request):
        if request.headers.get("X-Admin-Token") != TOKEN:
            raise web.HTTPForbidden(text="Operator authentication required")
        if self.settings_status != 200:
            raise web.HTTPForbidden()
        patch = await request.json()
        self.settings_posts.append(patch)
        for key in ("doors", "lights"):
            if key in patch:
                self.world.settings[key] = {**self.world.settings[key], **patch[key]}
        return web.json_response(self.world.settings_view())

    async def push(self, stage="AWAKE"):
        for ws in list(self.sockets):
            await ws.send_json(tick(self.world, stage))

    async def drop(self):
        for ws in list(self.sockets):
            await ws.close()


async def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached")


async def start(backend=None, url=None, stale_after=3.0, unavailable_after=15.0):
    if backend is not None:
        await backend.server.start_server()
        url = str(backend.server.make_url("")).rstrip("/")
    model = bridge.HomeStateModel(stale_after=stale_after, unavailable_after=unavailable_after)
    feed = bridge.BackendFeed(model, url, TOKEN, backoff=(0.05, 0.2))
    http = TestClient(TestServer(bridge.create_app(model, TOKEN, feed, ticker=0.05)))
    await http.start_server()
    return http, model, feed


def test_auth_required_on_every_route_but_healthz():
    async def body():
        http, _, _ = await start(url="http://127.0.0.1:9")
        try:
            assert (await http.get("/healthz")).status == 200
            for headers in ({}, {"X-Admin-Token": "wrong-credential-x"}, {"Authorization": "Bearer nope"}):
                assert (await http.get("/home/state", headers=headers)).status == 403
                assert (await http.get("/home/state?since=1&wait=1", headers=headers)).status == 403
                assert (await http.post("/home/controls", json={"doors": {"front": "open"}},
                                        headers=headers)).status == 403
            assert (await http.get("/home/state", headers=AUTH)).status == 200
            r = await http.get("/home/state", headers={"Authorization": "Bearer " + TOKEN})
            assert r.status == 200 and r.headers["Cache-Control"] == "no-store"
        finally:
            await http.close()
    run(body())


def test_loopback_only_bind_backend_and_credential_refusal(monkeypatch):
    monkeypatch.setenv("SUB01_ADMIN_TOKEN", TOKEN)
    for argv in (["--host", "0.0.0.0"], ["--host", "192.168.1.5"],
                 ["--backend", "http://10.0.0.5:8765"], ["--backend", "http://example.com"],
                 ["--stale-after", "20"]):
        with pytest.raises(SystemExit):
            bridge.parse_args(argv)
    args, token = bridge.parse_args(["--host", "::1", "--backend", "http://localhost:8765"])
    assert token == TOKEN and args.host == "::1"
    monkeypatch.setenv("SUB01_ADMIN_TOKEN", "short")
    with pytest.raises(SystemExit):
        bridge.parse_args([])
    with pytest.raises(ValueError):
        bridge.BackendFeed(bridge.HomeStateModel(), "http://10.1.2.3:8765", TOKEN)
    with pytest.raises(ValueError):
        bridge.create_app(bridge.HomeStateModel(), "short")


def test_feed_goes_live_then_stale_then_reconnects_with_fresh_snapshot():
    async def body():
        backend = FakeBackend()
        http, model, feed = await start(backend, stale_after=0.4, unavailable_after=1.2)
        try:
            await wait_until(lambda: backend.sockets)
            assert backend.rest_calls == 1
            assert backend.ws_queries[0] == {"rate": "5", "lite": "1"}
            assert backend.ws_headers[0] == TOKEN
            walk(backend.world, "sleep", 3)
            await backend.push()
            await wait_until(lambda: model.home and model.home.get("destination") == "bed")
            doc = await (await http.get("/home/state", headers=AUTH)).json()
            assert doc["source"]["status"] == "live" and doc["brain"]["activity"] == "sleep"
            # Silence: stale, then unavailable, even though the socket is open.
            await asyncio.sleep(0.6)
            doc = await (await http.get("/home/state", headers=AUTH)).json()
            assert doc["source"]["status"] == "stale" and doc["brain"] is None
            # Backend drops the socket: the feed reconnects with a fresh REST snapshot.
            await backend.drop()
            await wait_until(lambda: feed.connects >= 2 and backend.sockets)
            assert backend.rest_calls >= 2
            await backend.push()
            await wait_until(lambda: model.status()[0] == "live")
            doc = await (await http.get("/home/state", headers=AUTH)).json()
            assert doc["source"]["status"] == "live"
        finally:
            await http.close()
            await backend.server.close()
    run(body())


def test_failing_rest_snapshot_still_follows_the_websocket_feed():
    # Seen against the real backend: GET /api/home answers 500 when the
    # screens browser is off. The WS `home` view is the same data.
    async def body():
        backend = FakeBackend()
        backend.rest_status = 500
        http, model, feed = await start(backend)
        try:
            await wait_until(lambda: backend.sockets)
            doc = await (await http.get("/home/state", headers=AUTH)).json()
            assert doc["source"]["status"] == "unavailable" and feed.snapshot_failures == 1
            await backend.push()
            await wait_until(lambda: model.status()[0] == "live")
            doc = await (await http.get("/home/state", headers=AUTH)).json()
            assert doc["brain"] == {"stage": "AWAKE", "activity": "research"}
        finally:
            await http.close()
            await backend.server.close()
    run(body())


def test_unreachable_backend_stays_unavailable_and_keeps_retrying():
    async def body():
        http, model, feed = await start(url="http://127.0.0.1:9")
        try:
            await wait_until(lambda: feed.failures >= 3)
            doc = await (await http.get("/home/state", headers=AUTH)).json()
            assert doc["source"]["status"] == "unavailable"
            assert doc["brain"] is None and doc["actor"] is None and doc["privacy"] is None
        finally:
            await http.close()
    run(body())


def test_long_poll_returns_on_change_or_after_wait():
    async def body():
        backend = FakeBackend()
        http, model, feed = await start(backend)
        try:
            await wait_until(lambda: backend.sockets)
            await backend.push()
            await wait_until(lambda: model.status()[0] == "live")
            rev = (await (await http.get("/home/state", headers=AUTH)).json())["revision"]
            began = time.monotonic()
            same = await (await http.get(f"/home/state?since={rev}&wait=0.4", headers=AUTH)).json()
            assert same["revision"] == rev and time.monotonic() - began >= 0.35
            pending = asyncio.ensure_future(http.get(f"/home/state?since={rev}&wait=10", headers=AUTH))
            await asyncio.sleep(0.2)
            assert not pending.done()
            backend.world.settings["lights"]["kitchen"] = "on"
            backend.world.interactions.update(0, backend.world._actor(), backend.world.settings, None)
            began = time.monotonic()
            await backend.push()
            changed = await (await pending).json()
            assert changed["revision"] == rev + 1 and time.monotonic() - began < 2
            assert changed["lights"]["rooms"]["kitchen"] == {"on": True, "mode": "on"}
            assert (await http.get("/home/state?since=x", headers=AUTH)).status == 400
            assert (await http.get("/home/state?since=1&wait=-1", headers=AUTH)).status == 400
        finally:
            await http.close()
            await backend.server.close()
    run(body())


def test_controls_passthrough_validates_and_forwards_door_light_modes():
    async def body():
        backend = FakeBackend()
        http, model, feed = await start(backend)
        try:
            for bad in ({}, {"doors": {"garage": "open"}}, {"doors": {"front": "ajar"}},
                        {"lights": {"kitchen": True}}, {"lamp": False}, {"doors": {}},
                        {"doors": {"front": "open"}, "position": [0, 0, 0]}):
                r = await http.post("/home/controls", json=bad, headers=AUTH)
                assert r.status == 400, bad
            assert (await http.post("/home/controls", data=b"[1]", headers=AUTH)).status == 400
            assert (await http.post("/home/controls", data=b"x" * 5000, headers=AUTH)).status == 413
            assert backend.settings_posts == []
            r = await http.post("/home/controls", json={"doors": {"front": "open"}, "lights": {"bedroom": "off"}},
                                headers=AUTH)
            assert r.status == 200
            out = await r.json()
            assert out["ok"] is True and out["doors"]["front"] == "open" and out["lights"]["bedroom"] == "off"
            assert backend.settings_posts == [{"doors": {"front": "open"}, "lights": {"bedroom": "off"}}]
            backend.settings_status = 403
            r = await http.post("/home/controls", json={"doors": {"front": "auto"}}, headers=AUTH)
            assert r.status == 502 and (await r.json())["backend_status"] == 403
        finally:
            await http.close()
            await backend.server.close()
        # Backend gone: honest 503, not a fake success.
        http, model, feed = await start(url="http://127.0.0.1:9")
        try:
            r = await http.post("/home/controls", json={"doors": {"front": "open"}}, headers=AUTH)
            assert r.status == 503
        finally:
            await http.close()
    run(body())


def test_credential_never_appears_in_documents():
    clock = Clock()
    model = bridge.HomeStateModel(clock=clock)
    model.set_connected(True)
    model.apply_tick(tick(HomeWorld()))
    assert TOKEN not in json.dumps(model.document())
    assert re.fullmatch(r"[0-9a-f]{12}", model.document()["epoch"])


def test_actor_hidden_while_away_owner_decision():
    clock = Clock()
    model = bridge.HomeStateModel(clock=clock, stale_after=3, unavailable_after=15)
    model.set_connected(True)
    world = HomeWorld()
    home = world.view(compact=True)
    model.apply_tick({"type": "tick", "home": {**home, "presence": "home"}, "sleep": {"stage": "AWAKE"}})
    assert model.document()["actor"]["visible"] is True
    model.apply_tick({"type": "tick", "home": {**home, "presence": "away"}, "sleep": {"stage": "AWAKE"}})
    assert model.document()["actor"]["visible"] is False
    model.apply_tick({"type": "tick", "home": {**home, "presence": "returning"}, "sleep": {"stage": "AWAKE"}})
    assert model.document()["actor"]["visible"] is True
