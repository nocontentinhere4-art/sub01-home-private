import json
import math

from home_world import HomeWorld, NODES, route


def test_sofa_stands_in_front_and_rises_toward_tv_without_back_crossing():
    home = HomeWorld({"node": "sofa", "seated": 1})
    assert home.view()["position"] == [-1.8, 1.3655, .1]
    last = home.view()["position"]
    for _ in range(38):
        home.update(.05, .05, {"activity": "research"}, {})
        eye = home.view()["position"]
        assert eye[0] <= last[0], "Get up toward the front/TV, never across backrest"
        assert eye[1] >= last[1]
        assert math.dist(eye, last) <= .05 * 1.25 + .001
        last = eye
    assert home.seated == 0
    assert home.position[0] == -2.55


def test_sofa_route_uses_clear_front_and_rear_ends():
    assert route("lounge_gate", "sofa") == ["lounge_gate", "sofa_front_approach", "sofa"]
    assert route("kitchen_gate", "sofa") == ["kitchen_gate", "sofa_rear_approach", "sofa"]
    # HAVEN's real footprint x[-2.2625,-1.3375], z[-1.0375,1.2375],
    # plus body radius.16. The table ends x=-2.86. These are physical gaps.
    for start in ["lounge_gate", "kitchen_gate"]:
        nodes = route(start, "sofa")
        for a, b in zip(nodes, nodes[1:]):
            for i in range(101):
                x, _, z = [v+(w-v)*i/100 for v,w in zip(NODES[a], NODES[b])]
                assert not (-2.4225 < x < -1.1775 and -1.1975 < z < 1.3975)
                if -.75 < z < .95:
                    assert x > -2.70, "Body clears coffee table front edge"


def test_legacy_seated_pose_preserved_and_unsafe_moving_sofa_path_replanned():
    seated = HomeWorld({"node": "sofa", "seated": 1, "position": [-.45, 1.65, .1]})
    assert seated.view()["position"] == [-1.8, 1.3655, .1]
    legacy = HomeWorld({"node": "kitchen_gate", "position": [-1.4, 1.65, -.9],
                        "target": "sofa", "path": ["sofa"], "activity": "play_console"})
    assert legacy.position == list(NODES["kitchen_gate"])
    assert legacy.path == ["sofa_rear_approach", "sofa"]
    for _ in range(100):
        legacy.update(.05, .05, {"activity": "play_console"}, {})
    restored = HomeWorld(json.loads(json.dumps(legacy.to_dict())))
    assert restored.position == legacy.position
    assert restored.path == legacy.path
    assert restored.seated == legacy.seated
    assert restored.to_dict()["navigation_version"] == 2


def test_legacy_partial_departure_replans_but_unrelated_motion_is_unchanged():
    leaving = HomeWorld({"node": "sofa", "seated": .5, "position": [-.45, 1.65, .1],
                         "path": ["kitchen_gate", "kitchen"], "target": "kitchen", "activity": "eat"})
    assert leaving.seated == .5
    assert leaving.position == list(NODES["sofa"])
    assert leaving.path == ["sofa_rear_approach", "kitchen_gate", "kitchen"]
    assert leaving.view()["position"][0] == -2.175
    saved = {"node": "aisle", "position": [1.3, 1.65, -1.1],
             "path": ["back", "kitchen_gate", "kitchen"], "target": "kitchen", "activity": "eat"}
    unrelated = HomeWorld(saved)
    assert unrelated.position == saved["position"]
    assert unrelated.path == saved["path"]


def test_current_inflight_sofa_arrival_and_departure_roundtrip_without_repositioning():
    for node, activity, seated in [("kitchen_gate", "play_console", 0), ("sofa", "research", .5)]:
        home = HomeWorld({"node": node, "seated": seated})
        for _ in range(7):
            home.update(.05, .05, {"activity": activity}, {})
        saved = json.loads(json.dumps(home.to_dict()))
        restored = HomeWorld(saved)
        assert restored.position == home.position
        assert restored.path == home.path
        assert restored.view()["position"] == home.view()["position"]
