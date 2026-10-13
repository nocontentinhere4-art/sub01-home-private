"""Real end-to-end check: actual live_server.py + /ws + home-state bridge on loopback.

Skipped only when the server cannot start in time (reason shown); any failed
check fails the test. The tool kills its children in every case and this test
verifies none is left running.
"""

import asyncio
import json
import os

import pytest

import home_interactions as hi
from tools.home_e2e_check import (STARTED, CheckFailed, StartTimeout, analyse_bathroom_walk, analyse_outing,
                                  ordered, run_check, seed_outing, seed_walk_to_bathroom, sim_epoch)

TIMEOUT = min(90.0, float(os.environ.get("SUB01_E2E_TIMEOUT", "90")))
WALK_TIMEOUT = min(120.0, float(os.environ.get("SUB01_E2E_WALK_TIMEOUT", "120")))


def test_home_stack_end_to_end():
    try:
        report = asyncio.run(run_check(TIMEOUT))
    except StartTimeout as error:
        pytest.skip(f"home backend could not start within {TIMEOUT:.0f} s: {str(error)[-400:]}")
    except CheckFailed as error:
        pytest.fail(str(error))
    finally:
        left = [p.pid for p in STARTED if p.poll() is None]
        assert not left, f"end-to-end child processes left running: {left}"
    assert STARTED, "the check started real child processes"
    names = {c["check"] for c in report["checks"]}
    assert report["ok"] and all(c["ok"] for c in report["checks"])
    for required in ("ws_home_fields", "settings_403_without_token", "settings_400_bad_mode",
                     "ws_reflects_settings", "api_home_200_without_browse", "bridge_live",
                     "bridge_controls_passthrough", "bridge_stale_after_backend_stop",
                     "privacy_ws_position", "privacy_ws_devices", "privacy_api_unauthenticated_pose",
                     "privacy_bridge_only_flag_and_house"):
        assert required in names, required


# ---------------------------------------------------------------- real walking phases

def rec(t, place, privacy=False, position=(1.3, 1.65, -0.75), **extra):
    r = {"t": t, "privacy": privacy, "position": list(position), "entry_position": list(position), "place": place,
         "activity": "use_bathroom", "walking": True, "path": ["x"], "presence": "home",
         "devices": {"computer": 1}, "front": "closed", "bathroom": "closed"}
    r.update(extra)
    return r


def private(t, bathroom="locked"):
    return rec(t, "bathroom", True, hi.PRIVATE_ACTOR["position"], walking=False, path=[],
               devices={"privacy": True}, bathroom=bathroom)


def good_walk():
    return [rec(0, "desk"), rec(1, "stair_top", position=(0.3, 4.65, -1.7)),
            rec(2, "bath_aisle", position=(-0.5, 4.65, 1.2)), private(3, "open"), private(4), private(5),
            rec(6, "bath_door", position=(-0.5, 4.65, 1.35), activity="park", bathroom="open")]


def failed(checks):
    return {name for name, ok, _ in checks if not ok}


def test_walk_analysis_accepts_real_shape_and_rejects_leaks():
    checks, summary = analyse_bathroom_walk(good_walk())
    assert not failed(checks)
    assert summary["privacy_on_t"] == 3 and summary["privacy_off_t"] == 6
    leak = good_walk()
    leak.insert(3, rec(2.5, "bath_door", position=(-1.4, 4.65, 1.35)))   # a public pose inside the bathroom
    assert "walk_never_publishes_inside_bathroom" in failed(analyse_bathroom_walk(leak)[0])
    assert "walk_privacy_turns_off" in failed(analyse_bathroom_walk(good_walk()[:-1])[0])
    unmasked = good_walk()
    unmasked[4]["devices"] = {"computer": 1}
    assert "walk_private_devices_masked" in failed(analyse_bathroom_walk(unmasked)[0])
    never_locked = [dict(r, bathroom="open") for r in good_walk()]
    assert "walk_bathroom_locked_while_private" in failed(analyse_bathroom_walk(never_locked)[0])


def test_outing_analysis():
    def r(t, presence, front, z=3.2, place="front"):
        return rec(t, place, position=(2, 1.65, z), presence=presence, front=front)
    good = [r(0, "home", "closed"), r(1, "home", "open"), r(2, "leaving", "open", 5), r(3, "away", "open", 7.25),
            r(4, "away", "locked", 7.25), r(5, "returning", "open", 6), r(6, "home", "open", 3.5)]
    assert not failed(analyse_outing(good)[0])
    never_locked = [dict(x, front="closed") if x["presence"] == "away" else x for x in good]
    assert "outing_front_locked_away" in failed(analyse_outing(never_locked)[0])
    assert "outing_presence_sequence" in failed(analyse_outing(good[:5])[0])
    assert ordered(["home", "leaving", "away"], ["home", "away"]) and not ordered(["away", "home"], ["home", "away"])


def test_walk_seeds_are_start_state_only(tmp_path):
    seed_walk_to_bathroom(tmp_path, stay_s=10)
    home, life = (json.loads((tmp_path / f).read_text()) for f in ("home.json", "life.json"))
    assert home == {"navigation_version": 2, "node": "desk", "seated": 1}
    assert life["activity"] == "use_bathroom" and abs(life["until"] - (sim_epoch() + 10)) < 5
    seed_outing(tmp_path, bench_s=5)
    assert json.loads((tmp_path / "life.json").read_text()) == {"place": "desk", "activity": "park", "until": 0.0,
                                                                  "dur": 5}


def test_home_stack_real_walking_phases():
    try:
        report = asyncio.run(run_check(WALK_TIMEOUT, privacy=False, house=False, walking=True))
    except StartTimeout as error:
        pytest.skip(f"home backend could not start within {WALK_TIMEOUT:.0f} s: {str(error)[-400:]}")
    except CheckFailed as error:
        pytest.fail(str(error))
    finally:
        left = [p.pid for p in STARTED if p.poll() is None]
        assert not left, f"end-to-end child processes left running: {left}"
    names = {c["check"] for c in report["checks"]}
    assert report["ok"] and all(c["ok"] for c in report["checks"])
    for required in ("walk_route_followed", "walk_privacy_at_doorway", "walk_private_standin",
                     "walk_bathroom_locked_while_private", "walk_privacy_turns_off",
                     "walk_never_publishes_inside_bathroom", "outing_presence_sequence",
                     "outing_front_locked_away", "outing_front_opens_returning", "outing_back_inside"):
        assert required in names, required
    assert report["timings"]["total"] <= 120
