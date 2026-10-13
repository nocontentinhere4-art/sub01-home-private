"""Server-authoritative doors, room lights, presence and one privacy decision."""

import asyncio
import json
import math
from types import SimpleNamespace

import home_interactions as hi
from home_api import device_revisions
from home_world import HomeWorld, NODES
from tests.test_home_api import client

# 03:00 and 12:00 in Tokyo for the page's homeLighting clock.
NIGHT = (3 - 9) * 3600 + 86400 * 100
NOON = (12 - 9) * 3600 + 86400 * 100


def step(home, act, life=None, now=NIGHT, dt=0.05):
    home.update(dt, dt, {"activity": act, **(life or {})}, {}, now=now)


def walk(home, act, life=None, now=NIGHT, limit=4000, each=None):
    for _ in range(limit):
        step(home, act, life, now)
        if each:
            each(home)
        if not home.path and home.activity == act and (
                home.node not in ("desk", "sofa", "bed") or home.seated == 1):
            return
    raise AssertionError("did not arrive")


def test_bathroom_privacy_edges_follow_the_door_and_never_flicker():
    home = HomeWorld({"node": "loft"})
    trace = []
    walk(home, "use_bathroom", each=lambda h: trace.append(
        (h.node, list(h.path), list(h.position), h.view(compact=True))))
    view = home.view()
    assert view["privacy"] and view["doors"]["bathroom"] == {
        "open": False, "locked": True, "mode": "auto"}
    # Privacy switches on once, before the actor crosses the door plane, and
    # never turns off again while he is inside.
    flags = [v["privacy"] for *_, v in trace]
    first = flags.index(True)
    assert all(flags[first:])
    node, path, pos, _ = trace[first]
    assert node == "bath_door" and path[:1] == ["bathroom"] and pos[0] > -0.85
    # The door opens for the step in, then closes and locks behind him.
    opened = [i for i, (*_, v) in enumerate(trace) if v["doors"]["bathroom"]["open"]]
    locked = [i for i, (*_, v) in enumerate(trace) if v["doors"]["bathroom"]["locked"]]
    assert opened and locked and opened[0] < locked[0]
    assert all(trace[i][2][0] <= hi.BATHROOM_CLOSE_X for i in locked)
    # Every in-region frame is private.
    assert all(v["privacy"] for _, _, p, v in trace if hi.in_bathroom(p))

    exit_trace = []
    walk(home, "research", each=lambda h: exit_trace.append(
        (h.node, list(h.path), list(h.position), h.view(compact=True))))
    # He unlocks and opens the door to leave; privacy stays on until he is
    # back at the doorway node outside the bathroom.
    leaving = exit_trace[0][3]
    assert leaving["privacy"] and leaving["doors"]["bathroom"]["open"]
    assert not leaving["doors"]["bathroom"]["locked"]
    off = [v["privacy"] for *_, v in exit_trace].index(False)
    assert exit_trace[off][0] == "bath_door"
    assert not any(v["privacy"] for *_, v in exit_trace[off:])
    assert all(v["privacy"] for _, _, p, v in exit_trace if hi.in_bathroom(p))
    assert home.view()["doors"]["bathroom"] == {"open": False, "locked": False, "mode": "auto"}


def test_privacy_survives_restart_and_stale_door_snapshots():
    home = HomeWorld({"node": "loft"})
    walk(home, "use_bathroom")
    restored = HomeWorld(json.loads(json.dumps(home.to_dict())))
    assert restored.view()["privacy"] and restored.view()["doors"]["bathroom"]["locked"]
    # A forged or stale snapshot cannot leave the door open or locked wrongly.
    state = home.to_dict()
    state["interactions"]["doors"]["bathroom"] = {"open": True, "locked": False}
    forged = HomeWorld(state)
    assert forged.view()["privacy"] and forged.view()["doors"]["bathroom"]["locked"]
    state = HomeWorld({"node": "desk"}).to_dict()
    state["interactions"] = {"doors": {"bathroom": {"open": True, "locked": True}}}
    desk = HomeWorld(state)
    assert not desk.view()["privacy"] and not desk.view()["doors"]["bathroom"]["locked"]
    # Malformed positions never crash and never count as inside.
    assert not hi.in_bathroom([float("nan"), 4.65, 1.3]) and hi.room_of(None) is None


def test_operator_cannot_open_an_occupied_bathroom():
    home = HomeWorld({"node": "loft"})
    walk(home, "use_bathroom")
    home.settings["doors"]["bathroom"] = "open"
    step(home, "use_bathroom")
    assert home.view()["privacy"] and home.view()["doors"]["bathroom"]["open"] is False
    walk(home, "research")
    step(home, "research")
    assert home.view()["doors"]["bathroom"] == {"open": True, "locked": False, "mode": "open"}


def test_devices_and_compact_feed_leak_nothing_during_privacy():
    home = HomeWorld({"node": "loft"})
    walk(home, "use_bathroom")
    compact = home.view(compact=True)
    assert compact["privacy"] and compact["notes"] == [] and compact["memories"] == []
    live = SimpleNamespace(
        home=home, computer=SimpleNamespace(revision="r1"),
        browser=object(), screen_status=lambda d: {"frame_id": "secret-" + d},
        minecraft=SimpleNamespace(frame_tag="tag"))
    assert device_revisions(live, compact["privacy"]) == {"privacy": True}
    assert "secret" not in json.dumps(device_revisions(live, compact["privacy"]))


def test_api_masks_screens_while_private_and_accepts_door_and_light_modes():
    async def run():
        http, live = await client()
        live.screen_status = lambda d: {"device": d, "frame_id": "f-" + d, "url": "https://example.org/" + d}
        live.minecraft = SimpleNamespace(enabled=True, frame=b"x", view=lambda: {
            "enabled": True, "has_frame": True, "observation": {"pos": 1}, "events": ["e"], "last_action": "dig"})
        headers = {"X-Admin-Token": "test"}
        try:
            d = await (await http.get("/api/home")).json()
            assert d["browser_screen"]["frame_id"] == "f-desk" and d["minecraft"]["has_frame"]
            assert set(d["home"]["doors"]) == {"front", "bathroom", "balcony"}
            assert set(d["home"]["lights"]["rooms"]) == set(hi.LIGHT_ROOMS)
            assert d["home"]["presence"] == "home"
            live.home.position = list(NODES["bathroom"])
            live.home.node = "bathroom"
            d = await (await http.get("/api/home")).json()
            assert d["home"]["privacy"]
            text = json.dumps({k: d[k] for k in ("browser_screen", "phone_browser_screen", "minecraft", "computer")})
            assert "f-desk" not in text and "f-phone" not in text and "example.org" not in text
            assert "dig" not in text and d["minecraft"]["has_frame"] is False
            assert d["browser_screen"] == {"device": "desk", "privacy": True}

            patch = {"doors": {"front": "open"}, "lights": {"kitchen": "off", "living": "on"}}
            assert (await http.post("/api/home/settings", json=patch)).status == 403
            r = await http.post("/api/home/settings", json=patch, headers=headers)
            assert r.status == 200
            body = await r.json()
            assert body["doors"] == {"front": "open", "bathroom": "auto", "balcony": "auto"}
            assert body["lights"]["kitchen"] == "off" and body["lights"]["bedroom"] == "auto"
            assert body["lamp"] is True and body["cabinets"] == [False] * 4
            view = live.home.view()
            assert view["doors"]["front"]["open"] and view["door_open"]
            assert view["lights"]["rooms"]["living"]["on"] and not view["lights"]["rooms"]["kitchen"]["on"]
            for bad in ({"doors": {"front": "ajar"}}, {"doors": {"garage": "open"}},
                        {"doors": []}, {"doors": {}}, {"lights": {"living": True}},
                        {"lamp": False, "lights": {"attic": "on"}}):
                r = await http.post("/api/home/settings", json=bad, headers=headers)
                assert r.status == 400, bad
            assert live.home.settings["lamp"] is True  # invalid edit is atomic
            assert live.home.settings["doors"]["front"] == "open"
            # Master lamp keeps working and switches every room off.
            r = await http.post("/api/home/settings", json={"lamp": False}, headers=headers)
            assert r.status == 200
            assert not any(v["on"] for v in live.home.view()["lights"]["rooms"].values())
            restored = HomeWorld(live.home.to_dict())
            assert restored.settings["doors"]["front"] == "open"
            assert restored.settings["lights"]["kitchen"] == "off"
        finally:
            await http.close()
    asyncio.run(run())


def test_front_door_exit_away_and_return_through_the_door():
    home = HomeWorld({"node": "desk", "seated": 1})
    trace = []
    walk(home, "park", life={"place": "door_in"}, each=lambda h: trace.append(
        (list(h.position), h.view(compact=True))))
    assert home.view()["doors"]["front"]["open"]  # closes behind him shortly
    for _ in range(int(hi.CLOSE_DELAY / 0.05) + 2):
        step(home, "park", {"place": "door_out"})
    view = home.view()
    assert view["presence"] == "away" and home.node == "outside"
    assert view["doors"]["front"] == {"open": False, "locked": True, "mode": "auto"}
    # The door was open whenever he crossed its plane.
    crossing = [v for p, v in trace if 3.6 < p[2] < 4.3]
    assert crossing and all(v["doors"]["front"]["open"] for v in crossing)
    assert "leaving" in [v["presence"] for _, v in trace]
    # Lights auto-off once the house is empty for longer than the linger time.
    for _ in range(int(hi.LIGHT_LINGER / 0.5) + 2):
        step(home, "park", {"place": "bench"}, dt=0.5)
    assert not any(v["on"] for v in home.view()["lights"]["rooms"].values())

    # A new indoor activity while life is still on the street keeps him out.
    for _ in range(200):
        step(home, "research", {"place": "street_home"})
    assert home.node == "outside" and not home.path and home.view()["presence"] == "away"
    # Back at the door in the life walk: he returns through the front door.
    back = []
    walk(home, "research", life={"place": "door_out"}, each=lambda h: back.append(
        (list(h.position), h.view(compact=True))))
    assert back[0][1]["presence"] == "returning"
    assert all(v["doors"]["front"]["open"] for p, v in back if 3.6 < p[2] < 4.3)
    assert home.view()["presence"] == "home"
    for _ in range(int(hi.CLOSE_DELAY / 0.05) + 2):
        step(home, "research", {"place": "desk"})
    assert home.view()["doors"]["front"] == {"open": False, "locked": False, "mode": "auto"}


def test_outing_without_life_place_is_unchanged():
    # Legacy callers pass no life place: an indoor activity brings him home.
    home = HomeWorld({"node": "outside"})
    walk(home, "research")
    assert home.node == "desk"


def test_balcony_door_opens_for_passage_and_closes_after():
    home = HomeWorld({"node": "loft"})
    seen = []
    walk(home, "window", each=lambda h: seen.append(
        (h.node, list(h.path), h.view(compact=True)["doors"]["balcony"]["open"])))
    assert all(o for n, p, o in seen if hi.crossing("balcony", n, p))
    walk(home, "research")
    for _ in range(40):
        step(home, "research")
    assert home.view()["doors"]["balcony"]["open"] is False
    home.settings["doors"]["balcony"] = "open"
    step(home, "research")
    assert home.view()["doors"]["balcony"]["open"] is True
    home.settings["doors"]["balcony"] = "closed"
    step(home, "research")
    assert home.view()["doors"]["balcony"]["open"] is False


def test_closed_mode_still_lets_the_actor_through():
    home = HomeWorld({"node": "front"})
    home.settings["doors"]["front"] = "closed"
    seen = []
    walk(home, "park", each=lambda h: seen.append(
        (h.node, list(h.path), h.view()["doors"]["front"]["open"])))
    assert any(o for *_, o in seen)
    assert all(o for n, p, o in seen if hi.crossing("front", n, p))
    assert home.view()["doors"]["front"] == {"open": False, "locked": True, "mode": "closed"}


def test_room_lights_follow_presence_daylight_sleep_and_overrides():
    home = HomeWorld({"node": "kitchen"})
    step(home, "eat", now=NIGHT)
    rooms = home.view()["lights"]["rooms"]
    assert rooms["kitchen"]["on"] and not rooms["bedroom"]["on"]
    assert home.view()["lights"]["dark"] is True
    step(home, "eat", now=NOON)
    assert home.view()["lights"]["dark"] is False
    assert not home.view()["lights"]["rooms"]["kitchen"]["on"]
    # The bathroom light follows occupancy, day or night.
    home = HomeWorld({"node": "loft"})
    walk(home, "use_bathroom", now=NOON)
    assert home.view()["lights"]["rooms"]["bathroom"]["on"]
    # Asleep in bed: bedroom auto light off, an operator "on" still wins.
    home = HomeWorld({"node": "loft"})
    walk(home, "sleep")
    assert not home.view()["lights"]["rooms"]["bedroom"]["on"]
    home.settings["lights"]["bedroom"] = "on"
    step(home, "sleep")
    assert home.view()["lights"]["rooms"]["bedroom"]["on"]
    home.settings["lamp"] = False
    step(home, "sleep")
    assert not home.view()["lights"]["rooms"]["bedroom"]["on"]
    assert home.view()["lights"]["master"] is False
    # Leaving a room keeps its light for the linger time only.
    home = HomeWorld({"node": "kitchen"})
    step(home, "eat")
    walk(home, "research")
    assert home.view()["lights"]["rooms"]["kitchen"]["on"]
    for _ in range(int(hi.LIGHT_LINGER / 0.5) + 2):
        step(home, "research", dt=0.5)
    assert not home.view()["lights"]["rooms"]["kitchen"]["on"]
    assert home.view()["lights"]["rooms"]["living"]["on"]


def test_rooms_and_daylight_match_the_page_zoning():
    assert hi.room_of(NODES["kitchen"]) == "kitchen"
    assert hi.room_of(NODES["desk"]) == "living" and hi.room_of(NODES["sofa"]) == "living"
    assert hi.room_of(NODES["bed"]) == "bedroom" and hi.room_of(NODES["bathroom"]) == "bathroom"
    assert hi.room_of(NODES["outside"]) is None
    assert hi.daylight(NOON) > 0.99 and hi.daylight(NIGHT) == 0
    assert hi.is_dark(None) and hi.is_dark(float("nan"))
    assert math.isclose(hi.daylight((6 - 9) * 3600), 0.5, abs_tol=0.5)


def test_legacy_settings_and_views_remain_compatible():
    home = HomeWorld({"settings": {"lamp": False, "doors": {"front": "bogus"}, "lights": "x"}})
    assert home.settings["lamp"] is False
    assert home.settings["doors"] == {"front": "auto", "bathroom": "auto", "balcony": "auto"}
    assert home.settings["lights"] == {r: "auto" for r in hi.LIGHT_ROOMS}
    view = home.view(compact=True)
    for key in ("door_open", "privacy", "settings", "position", "place"):
        assert key in view
    # Views are copies: mutating them cannot change server state.
    view["settings"]["doors"]["front"] = "open"
    view["settings"]["cabinets"][0] = True
    assert home.settings["doors"]["front"] == "auto" and home.settings["cabinets"][0] is False
