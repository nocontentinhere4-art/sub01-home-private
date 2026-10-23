import itertools
import json
import math
import re
from pathlib import Path

import pytest

from home_world import HomeWorld, NODES, EDGES, route, Pong


def test_routes_stay_out_of_walls_and_furniture():
    source = (Path(__file__).parents[1] / "web/house/home.js").read_text()
    blockers = []
    for m in re.finditer(r"obstacle\(([\d., \-]+)\)", source):
        v = [float(x) for x in m[1].split(",")]
        x, z, w, d = v[:4]
        level = int(v[4]) if len(v) > 4 else 0
        blockers.append(
            (
                x - w / 2 - 0.16,
                x + w / 2 + 0.16,
                z - d / 2 - 0.16,
                z + d / 2 + 0.16,
                level,
            )
        )
    assert len(blockers) > 8
    for a, b in EDGES:
        A, B = NODES[a], NODES[b]
        for i in range(101):
            p = [x + (y - x) * i / 100 for x, y in zip(A, B)]
            x, h, z = p
            level = int(h > 3)
            for x0, x1, z0, z1, l in blockers:
                assert not (l == level and x0 < x < x1 and z0 < z < z1), (
                    a,
                    b,
                    p,
                    (x0, x1, z0, z1),
                )
    for a, b in itertools.product(NODES, repeat=2):
        r = route(a, b)
        assert r[0] == a and r[-1] == b


def arrive(home, act):
    for _ in range(3000):
        home.update(0.05, 0.05, {"activity": act}, {"attention": 1, "somatomotor": 1})
        if not home.path and home.activity == act:
            return
    raise AssertionError("did not arrive")


def test_shared_continuous_walk_privacy_and_persistence():
    home = HomeWorld()
    last = home.position[:]
    for i in range(1800):
        home.update(
            0.05, 0.05, {"activity": "use_bathroom" if i < 450 else "research"}, {}
        )
        assert math.dist(home.position, last) <= 1.25 * 0.05 + 1e-6
        last = home.position[:]
    arrive(home, "use_bathroom")
    assert home.view()["privacy"]
    arrive(home, "research")
    assert not home.view()["privacy"]
    home.add_note("persistent note")
    home.pong.score = [3, 4]
    restored = HomeWorld(json.loads(json.dumps(home.to_dict())))
    assert restored.notes == home.notes and restored.pong.score == [3, 4]


def test_game_only_runs_during_activity_and_responds_to_live_signals():
    p = Pong()
    original = p.view()
    p.update(0.05, {}, False)
    assert p.view()["ball"] == original["ball"]
    p.y = 0.8
    p.update(0.05, {"attention": 2, "somatomotor": 2}, True)
    strong = p.left
    q = Pong()
    q.y = 0.8
    q.update(0.05, {"attention": 0.2, "somatomotor": 0.2}, True)
    assert strong > q.left
    p.input(-1)
    last = p.right
    p.update(0.05, {}, True)
    assert p.right < last
    p.x = 1.1
    p.vx = 0.4
    p.y = 0.1
    p.update(0.05, {}, True)
    assert p.score[0] == 1 and p.reward > 0 and p.matches == 1


def test_life_uses_new_activities_only_when_home_is_enabled():
    from life import Life
    from datetime import datetime
    from zoneinfo import ZoneInfo

    t = datetime(2026, 10, 11, 15, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()
    life = Life()
    assert "play_console" not in life.scores(t, {})
    life.home_enabled = True
    life.home_bladder = 0.9
    assert life.scores(t, {})["use_bathroom"] > 1
    for act in ["use_computer", "play_console", "use_bathroom"]:
        life.place = "window"
        life.x, life.z = 4, 0.9
        life.activity = "window"
        life.path = []
        life.until = t + 10000
        life.home_bladder = 0.6 if act == "use_bathroom" else 0
        life.body.ghrelin = 0.1
        life.chat_waiting = 0
        life.bread = 4
        assert life.apply_vote(act, t)
        life.update(t, 0.05, 0.05, "AWAKE", {})
        assert life.activity == act
        assert life.snapshot()["doing"]


def test_inflight_route_survives_restart():
    home = HomeWorld()
    for _ in range(70):
        home.update(0.05, 0.05, {"activity": "use_bathroom"}, {})
    assert home.path
    saved = HomeWorld(json.loads(json.dumps(home.to_dict())))
    assert (
        saved.path == home.path
        and saved.position == home.position
        and saved.target == home.target
    )
    last = saved.position[:]
    saved.update(0.05, 0.05, {"activity": "use_bathroom"}, {})
    assert math.dist(last, saved.position) < 0.063


def test_compact_feed_excludes_device_logs():
    home = HomeWorld()
    home.add_note("only on the full device API")
    compact = home.view(compact=True)
    assert compact["notes"] == [] and compact["memories"] == []
    assert len(home.view()["notes"]) == 1


def test_camera_gets_up_before_walking_without_a_seat_teleport():
    for activity in ("use_computer", "phone", "play_console"):
        h = HomeWorld()
        arrive(h, activity)
        for _ in range(50):
            h.update(0.05, 0.05, {"activity": activity}, {})
        assert h.seated == 1
        last = h.view()["position"]
        for _ in range(180):
            h.update(0.05, 0.05, {"activity": "use_bathroom"}, {})
            current = h.view()["position"]
            assert math.dist(last, current) <= 1.25 * 0.05 + 0.001
            last = current
        assert h.seated == 0


def test_walk_brakes_before_arrival_and_keeps_routes_continuous():
    h = HomeWorld({"node": "outside"})
    last = h.position[:]
    approach = []
    peak = 0
    for _ in range(3000):
        h.update(.02, .02, {"activity": "research"}, {})
        peak = max(peak, h.speed)
        assert math.dist(last, h.position) <= 1.25 * .02 + 1e-8
        last = h.position[:]
        if h.path == ["desk"] and math.dist(h.position, NODES["desk"]) < .25:
            approach.append(h.speed)
        if not h.path and h.node == "desk":
            break
    assert h.node == "desk" and not h.path
    assert peak > 1.1 and len(approach) > 5
    assert approach[-1] < .25 and approach[-1] < approach[0] / 2


def test_pong_is_beatable_instead_of_an_infinite_perfect_tracker():
    p = Pong()
    for i in range(12000):
        rel = {
            "attention": 0.5 + ((i // 100) % 15) / 10,
            "somatomotor": 0.4 + ((i // 73) % 14) / 10,
        }
        p.update(0.05, rel, True)
    assert p.score[0] > 0 and p.score[1] > 0


def test_ground_routes_do_not_cut_across_the_stair_treads():
    # A diagonal shortcut to the TV previously crossed the first stair tread
    # with a ground-level eye height. Walk around the foot before turning.
    for a, b in EDGES:
        A, B = NODES[a], NODES[b]
        for i in range(101):
            x, y, z = [v + (w-v)*i/100 for v,w in zip(A,B)]
            if abs(y-1.65) < .001:
                assert not (-.2 <= x <= .8 and -1.7 < z < 2.51), (a,b,x,y,z)
    home = HomeWorld({'node':'sofa','seated':1})
    assert home.view()['position'][0] == -1.8
    assert home.view()['position'][2] == .1
    assert home.view()['look'][2] == .1


@pytest.mark.parametrize("seat", ["desk", "sofa", "bed"])
def test_getting_up_from_a_seat_takes_a_human_pace(seat):
    # Seated falls at 0.55 a second of real time: a seat is left in about 1.8 s, never at once and never slowly.
    h = HomeWorld({"node": seat, "seated": 1})
    eye = h.view()["position"]
    started = stepped = None
    for i in range(1, 400):
        h.update(.05, .05, {"activity": "park"}, {})
        if h.path and started is None:
            started = i * .05
        if h.position != list(NODES[seat]):
            stepped = i * .05
            break
        now = h.view()["position"]
        assert math.dist(eye, now) <= 1.25 * .05 + 1e-6, (i, eye, now)
        eye = now
    assert started is not None and stepped is not None
    assert 1.2 <= stepped - started <= 2.5, stepped - started


def test_changing_course_on_a_node_plans_from_that_node_not_back_along_the_last_edge():
    h = HomeWorld({"node": "front", "position": list(NODES["front"]), "target": "outside",
                   "path": ["door", "outside"], "activity": "park"})
    h.update(.05, .05, {"activity": "research"}, {})
    assert h.path == ["aisle", "desk"]


def test_changing_course_while_getting_up_does_not_walk_off_and_back():
    # Still getting up from the desk, he has taken no step: a new target is planned from the seat,
    # not from the next waypoint he never reached (that walked him to the aisle and back).
    h = HomeWorld({"node": "desk", "seated": 1})
    for _ in range(10):
        h.update(.05, .05, {"activity": "park"}, {})
    h.update(.05, .05, {"activity": "research"}, {})
    for _ in range(100):
        h.update(.05, .05, {"activity": "research"}, {})
        assert h.position == list(NODES["desk"])
    assert h.node == "desk" and not h.path and h.seated == 1


@pytest.mark.parametrize("scale", [1, 24, 60])
def test_bathroom_visit_empties_a_full_bladder_in_sim_time_at_any_acceleration(scale):
    # A visit lasts one to two sim minutes. Emptying runs on sim time, as filling does, so 20 sim s
    # empties .9 at 1x, 24x and 60x alike (with a real-time drain a 60x visit left the bladder almost full).
    h = HomeWorld({"node": "bathroom", "bladder": .9})
    for _ in range(int(20 / (.05 * scale))):
        h.update(.05, .05 * scale, {"activity": "use_bathroom"}, {})
    assert h.bladder == 0


@pytest.mark.parametrize("scale", [1, 24, 60])
def test_bladder_fills_over_five_sim_hours_at_any_acceleration(scale):
    h = HomeWorld({"node": "desk", "seated": 1, "bladder": 0})
    for _ in range(int(5 * 3600 / (.5 * scale))):
        h.update(.5, .5 * scale, {"activity": "research"}, {})
    assert h.bladder > .999
