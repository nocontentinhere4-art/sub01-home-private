"""Life's chat impulse, sleep-on-the-way, day-hint, walk-time, label and save rules, as life.py is on this branch
(aee7deb, 35e4b81, 6df9b5d).

PIN tests state what the code does now: a decision to revisit, not a claim that it is right. BUG and design-gap tests
are strict xfails: they state the intended behaviour and fail today, so the suite stays green; when a fix lands they
XPASS, which fails the run and says the marker has to go.

    python -m pytest tests/test_life_rules.py -q
No network, no AI calls, no server: life.py alone, with its own clock and its own body."""
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import daily_plan  # noqa: E402
import life as L  # noqa: E402
from impulse import Impulse, parse  # noqa: E402
from twin.body import Body  # noqa: E402

TZ = ZoneInfo("Asia/Tokyo")
MON = 5                                                   # 2026-10-05 is a Monday
HOME_FROM_BENCH = ["park_gate", "street_park", "street_home", "door_out", "door_in", "bed"]
HOME_FROM_COUNTER = ["bakery_in", "bakery_door", "street_bakery", "street_home", "door_out", "door_in", "bed"]
HUNGRY = {"since_meal_h": 6.0, "ghrelin": 0.9, "glucose": 78.0}     # above EAT_AT (as in test_needs_first.py)


def at(h, m=0, day=MON):
    return datetime(2026, 10, day, h, m, tzinfo=TZ).timestamp()


def fed():
    """Not hungry. An external body: update() does not step it, so its hunger stays where the test put it."""
    return Body({"since_meal_h": 0.5, "ghrelin": 0.1, "glucose": 110.0})


def idle(place="desk", activity="research", seed=0, body=None, **state):
    """Awake and settled: at `place`, doing `activity`, with no end in sight (until 1e18, so nothing transitions)."""
    s = {"place": place, "activity": activity, "until": 1e18, **state}
    return L.Life(s, rng=random.Random(seed), body=body or fed())


def asleep(seed=0):
    return L.Life({"place": "bed", "activity": "sleep", "until": 0.0}, rng=random.Random(seed), body=fed())


def tick(lf, t, stage="AWAKE", dt=1.0):
    lf.update(t, dt, dt, stage, {}, 0.0, 0.0)
    return t + dt


def run_until(lf, t, done, stage="AWAKE", limit=3600):
    """Tick until done(lf); returns the time reached."""
    for _ in range(limit):
        if done(lf):
            return t
        t = tick(lf, t, stage)
    raise AssertionError(f"not done after {limit} s: {lf.activity} at {lf.place}, path {lf.path}")


def arrive(lf, t, stage="AWAKE", limit=3600):
    return run_until(lf, t, lambda x: not x.path, stage, limit)


def ticks_to_arrive(lf, t, stage="AWAKE", limit=3600):
    """How many 1 s ticks the walk he is on takes from here (time scale 1)."""
    for n in range(limit):
        if not lf.path:
            return n
        t = tick(lf, t, stage)
    raise AssertionError(f"still walking after {limit} s: {lf.place}, path {lf.path}")


def at_bench(seed=0):
    """He has walked from the desk to the park bench and sits there: the park visit is under way."""
    lf, t = idle(seed=seed), at(14)
    lf.start("park", t, "walk to the park")
    t = arrive(lf, t)
    assert (lf.place, lf.activity, lf.path) == ("bench", "park", [])
    return lf, t


def mid_leg_walk():
    """The walk to the park, 120 s in: he is on the long street leg, between two waypoints."""
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    for _ in range(120):
        t = tick(lf, t)
    return lf, t


def roundtrip(lf):
    """to_dict() through JSON, as the state file holds it, then a new Life."""
    return L.Life(json.loads(json.dumps(lf.to_dict())), rng=random.Random(0))


def window_request(why="asked in chat: window"):
    return Impulse("activity", "window", None, "Okay, I will look out the window.", why)


# --- sleep starts only in bed -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("place, activity", [("desk", "research"), ("window", "window"), ("table", "eat"),
                                             ("door_in", "get_delivery")])
def test_a_sleep_stage_indoors_walks_him_to_bed_first(place, activity):
    lf, t = idle(place, activity), at(23)
    t = tick(lf, t, "NREM")
    assert lf.activity == "sleep" and lf.say == "goes to bed" and lf.path[-1] == "bed"
    arrive(lf, t, "NREM")
    assert lf.place == "bed" and lf.activity == "sleep"


def test_a_sleep_stage_in_bed_starts_sleep_without_a_walk():
    lf, t = idle("bed", "phone"), at(23)
    tick(lf, t, "NREM")
    assert lf.activity == "sleep" and lf.path == [] and lf.say == "falls asleep" and lf.label() == "sleeping"


def test_a_sleep_stage_at_the_bench_walks_him_home_and_he_sleeps_only_once_he_is_in_bed():
    lf, t = at_bench()
    t = tick(lf, t, "NREM")                       # the stage begins: the walk home is set, and no sleep yet
    assert lf.activity == "sleep" and lf.say == "goes to bed"
    assert lf.path == HOME_FROM_BENCH and lf.trip == "home-park"
    assert lf.label() == "walking to bed" and lf.snapshot()["pose"] == "walking"
    routes = set()
    for _ in range(1000):
        if lf.place == "bed":
            break
        assert lf.path and lf.activity == "sleep"  # on the way: still the sleep walk, not asleep
        before = (lf.x, lf.z)
        t = tick(lf, t, "NREM")
        assert (lf.x, lf.z) != before              # he moves every tick on the way
        if lf.geo:
            routes.add(lf.geo["route"])
    assert lf.place == "bed" and not lf.path and (lf.x, lf.z) == L.PLACES["bed"]
    assert routes == {"home-park"}                # the outdoor part is the real park route
    assert lf.geo is None                         # indoors: no map position
    for _ in range(600):                          # asleep in bed: nothing moves and nothing is decided
        t = tick(lf, t, "NREM")
    assert (lf.activity, lf.place, lf.path) == ("sleep", "bed", [])
    assert lf.label() == "sleeping" and lf.snapshot()["pose"] == "lying"
    t = tick(lf, t, "AWAKE")                      # the brain wakes him: he gets up at once
    assert lf.activity != "sleep" and lf.log[-1]["what"] == "wakes up"


def test_a_sleep_stage_at_the_counter_buys_the_bread_then_walks_home_on_the_bakery_route():
    lf, t = idle(), at(11)
    lf.start("buy_bread", t, "no bread left: walks to the bakery")
    t = arrive(lf, t)
    assert lf.place == "counter" and lf.bread == 0
    t = tick(lf, t, "NREM")
    assert lf.bread == L.BREAD_PER_TRIP           # the purchase is finished before he leaves
    assert lf.activity == "sleep" and lf.path == HOME_FROM_COUNTER and lf.trip == "home-bakery"
    routes = set()
    for _ in range(1000):
        if lf.place == "bed":
            break
        assert lf.path and lf.activity == "sleep"
        t = tick(lf, t, "NREM")
        if lf.geo:
            routes.add(lf.geo["route"])
    assert lf.place == "bed" and not lf.path and lf.activity == "sleep"
    assert routes == {"home-bakery"}


def test_a_wake_mid_walk_is_acted_on_only_at_bed_as_it_is_now():                # PIN, see the xfail below
    lf, t = at_bench()
    t = tick(lf, t, "NREM")
    for _ in range(60):                           # a minute into the walk
        t = tick(lf, t, "NREM")
    t = tick(lf, t, "AWAKE")                      # awake, on the street
    assert lf.activity == "sleep" and lf.path     # he does not turn back: the walk to bed goes on
    t = arrive(lf, t)
    assert lf.place == "bed" and lf.activity == "sleep"
    t = tick(lf, t, "AWAKE")
    assert lf.activity != "sleep" and lf.log[-1]["what"] == "wakes up"


@pytest.mark.xfail(strict=True, reason="design gap: a wake mid-walk is only handled at bed (life.py:700-726 return "
                                       "before the wake check at :737), so an awake man finishes the walk home first")
def test_a_wake_mid_walk_turns_him_back_at_the_next_node():
    lf, t = at_bench()
    t = tick(lf, t, "NREM")
    for _ in range(60):
        t = tick(lf, t, "NREM")
    t = tick(lf, t, "AWAKE")
    node = lf.path[0]
    run_until(lf, t, lambda x: x.place == node, limit=600)
    assert lf.activity != "sleep"


# --- chat impulses: carried out, waited for, replaced, dropped -----------------------------------------------
def test_a_chat_request_is_carried_out_on_the_next_tick_when_he_is_awake_and_settled():
    lf, t = idle(), at(14)
    imp = parse("look through the window")
    lf.request_impulse(imp, t)
    assert lf.impulse == ("window", imp.why, t)
    t0 = t
    tick(lf, t0)
    assert lf.activity == "window" and lf.path == ["window"] and lf.impulse is None
    assert lf.say == imp.why and lf.log[-1] == {"t": t0, "what": imp.why}


def test_a_chat_request_made_mid_walk_waits_and_runs_on_arrival():
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    for _ in range(30):
        t = tick(lf, t)
    lf.request_impulse(window_request(), t)
    for _ in range(3600):
        if not lf.path:
            break
        assert lf.activity == "park" and lf.impulse is not None      # still walking: the request waits
        t = tick(lf, t)
    assert lf.place == "bench" and lf.activity == "park"             # arrived: the next tick carries it out
    tick(lf, t)
    assert lf.activity == "window" and lf.path[-1] == "window" and lf.impulse is None
    assert lf.say == "asked in chat: window"


def test_the_latest_accepted_request_wins():
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    lf.request_impulse(Impulse("activity", "window", None, "r", "asked in chat: window"), t)
    lf.request_impulse(Impulse("activity", "research", None, "r", "asked in chat: research"), t)
    assert lf.impulse[0] == "research"
    t = arrive(lf, t)
    tick(lf, t)
    assert lf.activity == "research" and lf.say == "asked in chat: research"


def test_a_sleep_or_unusable_request_neither_replaces_nor_cancels_a_pending_one():
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    lf.request_impulse(window_request(), t)
    for junk in (Impulse("activity", "sleep", None, "r", "asked in chat: sleep"),
                 Impulse("activity", "not_an_activity", None, "r", "x"),
                 Impulse("open_url", None, "https://example.com", "r", "x"),
                 Impulse("reply_only", None, None, "r", "x"), None, "window"):
        lf.request_impulse(junk, t)
        assert lf.impulse[0] == "window"
    t = arrive(lf, t)
    tick(lf, t)
    assert lf.activity == "window"


def test_a_sleep_request_is_never_carried_out_awake_or_asleep():
    lf, t = idle(), at(23)
    lf.request_impulse(parse("time for a nap"), t)
    lf.request_impulse(parse("go to bed"), t)
    assert lf.impulse is None
    tick(lf, t)
    assert lf.activity == "research" and lf.path == []
    la = asleep()
    la.request_impulse(parse("time for a nap"), t)
    assert la.impulse is None


def test_a_request_that_is_not_an_activity_is_refused_and_an_empty_why_falls_back_to_the_log_text():
    lf, t = idle(), at(14)
    for junk in (None, object(), Impulse("reply_only", None, None, "r", "x"),
                 Impulse("open_url", None, "https://e.x", "r", "x"), Impulse("activity", None, None, "r", "x"),
                 Impulse("activity", "nope", None, "r", "x")):
        lf.request_impulse(junk, t)
        assert lf.impulse is None
    lf.request_impulse(Impulse("activity", "window", None, "r", None), t)
    assert lf.impulse == ("window", "", t)
    tick(lf, t)
    assert lf.activity == "window" and lf.log[-1]["what"] == "looks out of the window"


def test_a_request_for_what_he_is_already_doing_in_place_is_dropped_not_restarted():
    lf, t = idle("window", "window"), at(14)
    before = (lf.until, list(lf.started), list(lf.log))
    lf.request_impulse(window_request(), t)
    tick(lf, t)
    assert lf.impulse is None and lf.activity == "window" and lf.say == ""
    assert (lf.until, lf.started, lf.log) == before


def test_a_request_for_the_walk_he_is_already_on_is_refused_not_restarted():
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    t = tick(lf, t)
    assert lf.request_impulse(Impulse("activity", "park", None, "r", "asked in chat: park"), t) == L.ALREADY_LINE
    t = arrive(lf, t)
    started, until = len(lf.started), lf.until
    tick(lf, t)
    assert lf.activity == "park" and lf.impulse is None
    assert len(lf.started) == started and lf.until == until


def test_a_request_made_while_he_sleeps_waits_and_is_dropped_at_waking_once_over_an_hour_old_PIN():
    la, t = asleep(), at(23)
    t = tick(la, t, "NREM", dt=60.0)                                   # asleep: update() keeps the stage
    assert la.request_impulse(window_request(), t) == L.ASLEEP_LINE   # the honest line; the request waits
    for _ in range(480):                          # eight hours of sleep, a minute a tick
        t = tick(la, t, "NREM", dt=60.0)
    assert la.activity == "sleep" and la.place == "bed" and la.impulse[0] == "window"   # kept while he sleeps
    tick(la, t, "AWAKE", dt=60.0)                 # at waking it is past IMPULSE_TTL: dropped, and the log says why
    assert la.impulse is None and la.say == "wakes up"
    assert la.log[-2]["what"] == "asked in chat: window; not any more: that was more than an hour ago"


def test_a_fresh_request_made_while_he_sleeps_is_carried_out_at_waking_PIN():
    la, t = asleep(), at(23)
    t = tick(la, t, "NREM", dt=60.0)
    assert la.request_impulse(window_request(), t) == L.ASLEEP_LINE
    for _ in range(30):                           # half an hour asleep: still within IMPULSE_TTL
        t = tick(la, t, "NREM", dt=60.0)
    tick(la, t, "AWAKE", dt=60.0)
    assert la.activity == "window" and la.impulse is None and la.say == "wakes up; asked in chat: window"


def test_a_chat_request_is_taken_before_the_needs_PIN():
    control = idle(body=Body(HUNGRY))
    control.bread = 4
    tick(control, at(13))
    assert control.activity in L.FOOD_ACTS                          # with no request, the need comes first
    lf = idle(body=Body(HUNGRY))
    lf.bread = 4
    assert lf.hunger > L.EAT_AT
    lf.request_impulse(window_request(), at(13))
    tick(lf, at(13))
    assert lf.activity == "window"                                  # update() takes the request before the needs


# --- requests the code refuses now (B1-B5, fixed in F1) and the x/z save bug (B6, still open: xfail) ---------------
def test_a_bakery_request_at_night_does_not_sell_him_bread():
    lf, t = idle(), at(23)
    lf.request_impulse(parse("go to the bakery"), t)
    t = tick(lf, t)
    run_until(lf, t, lambda x: x.activity != "buy_bread")
    assert lf.bread == 0


def test_a_park_request_after_closing_time_does_not_send_him_out():
    lf, t = idle(), at(23)
    imp = Impulse("activity", "park", None, "The park sounds nice. Heading out.", "asked in chat: park")
    lf.request_impulse(imp, t)
    tick(lf, t)
    assert not lf.path


def test_an_eat_request_with_nothing_to_eat_does_not_start_a_meal():
    lf, t = idle("window", "window"), at(12)
    imp = Impulse("activity", "eat", None, "Good idea. Bread at the table, then.", "asked in chat: eat")
    lf.request_impulse(imp, t)
    tick(lf, t)
    assert lf.activity != "eat"


def test_a_video_request_with_nothing_to_show_is_not_carried_out():
    lf, t = idle(), at(14)
    lf.can_watch = False
    lf.request_impulse(parse("show me a youtube clip"), t)
    tick(lf, t)
    assert lf.activity != "watch_video"


def test_an_order_request_while_a_delivery_is_on_its_way_is_not_carried_out():
    lf, t = idle("bed", "phone"), at(19)
    lf.delivery = {"ordered": t - 600, "leaves": t - 300, "arrives": t + 900, "dish": "ramen"}
    lf.request_impulse(Impulse("activity", "order_food", None, "r", "asked in chat: order_food"), t)
    tick(lf, t)
    assert lf.activity != "order_food"


def test_the_mid_leg_setup_really_is_mid_leg():                              # the precondition of the xfail below
    lf, _ = mid_leg_walk()
    assert lf.path and (lf.x, lf.z) != L.PLACES[lf.place]


@pytest.mark.xfail(strict=True, reason="BUG life.py:287 (__init__) and :889 (to_dict): x and z are not saved, so a "
                                       "restart mid-leg puts him back at the last waypoint (a park leg is ~770 m)")
def test_a_save_taken_mid_leg_keeps_where_he_is():
    lf, _ = mid_leg_walk()
    back = roundtrip(lf)
    assert (back.x, back.z) == pytest.approx((lf.x, lf.z))


# --- the walk: speed, real routes, and the time it takes ----------------------------------------------------
def test_walk_speed_and_the_outdoor_speedup_are_the_design_numbers():
    assert L.WALK_SPEED == 1.3 and L.OUTDOOR_SPEEDUP == 3


def test_walk_s_is_the_real_route_length_at_the_outdoor_pace():
    for name, (lo, hi) in {"home-park": (1000, 1500), "home-bakery": (300, 600)}.items():
        meters = L.TOKYO["routes"][name]["meters"]
        assert lo <= meters <= hi, (name, meters)
        assert L.WALK_S[name] == pytest.approx(meters / L.WALK_SPEED / L.OUTDOOR_SPEEDUP)
    assert 4 * 60 <= L.WALK_S["home-park"] <= 7 * 60          # about five minutes each way
    assert 60 <= L.WALK_S["home-bakery"] <= 3 * 60            # about two minutes


def test_the_park_walk_from_the_desk_takes_walk_s_plus_the_indoor_steps():
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    expect = lf.walk_s()
    assert L.WALK_S["home-park"] <= expect <= L.WALK_S["home-park"] + 30
    assert abs(ticks_to_arrive(lf, t) - expect) <= 10


def test_the_walk_home_from_the_bench_takes_walk_s_plus_the_indoor_steps():
    lf, t = at_bench()
    t = tick(lf, t, "NREM")
    expect = lf.walk_s()
    assert L.WALK_S["home-park"] <= expect <= L.WALK_S["home-park"] + 30
    n = ticks_to_arrive(lf, t, "NREM")
    assert abs(n - expect) <= 10 and 300 <= n <= 360          # about five and a half minutes


def test_the_walk_from_the_counter_to_bed_takes_the_bakery_walk_s_plus_the_indoor_steps():
    lf, t = idle(), at(11)
    lf.start("buy_bread", t, "no bread left: walks to the bakery")
    t = arrive(lf, t)
    t = tick(lf, t, "NREM")
    expect = lf.walk_s()
    assert L.WALK_S["home-bakery"] <= expect <= L.WALK_S["home-bakery"] + 30
    n = ticks_to_arrive(lf, t, "NREM")
    assert abs(n - expect) <= 10 and 100 <= n <= 160


# --- the day hint: the template's step for the hour -----------------------------------------------------------
def test_day_hint_adds_the_plan_bonus_only_to_the_step_it_names():
    lf, t = idle(), at(14)
    base = lf.scores(t, {}, 0.0, 0.0)
    lf.day_hint = "window"
    hinted = lf.scores(t, {}, 0.0, 0.0)
    assert hinted["window"] == pytest.approx(base["window"] + L.PLAN_BONUS)
    assert {k: v for k, v in hinted.items() if k != "window"} == {k: v for k, v in base.items() if k != "window"}
    lf.plan_hint = "phone"                        # the mind's step wins: the template's is not added on top
    both = lf.scores(t, {}, 0.0, 0.0)
    assert both["phone"] == pytest.approx(base["phone"] + L.PLAN_BONUS)
    assert both["window"] == pytest.approx(base["window"])


def test_a_day_hint_that_cannot_happen_now_tilts_nothing():
    lf, t = idle(), at(21)                        # the park is shut, the sleep step is no choice, no food, not hungry
    base = lf.scores(t, {}, 0.0, 0.0)
    for hint in ("park", "sleep", "order_food", "eat"):
        lf.day_hint = hint
        assert lf.scores(t, {}, 0.0, 0.0) == base, hint


def test_day_hint_is_read_from_the_template_on_each_awake_idle_update(monkeypatch, tmp_path):
    path = tmp_path / "day_template.json"
    path.write_text(json.dumps({"shared": {"daily": [
        {"id": "w", "activity": "window", "earliest_start": "07:00", "latest_start": "09:00", "weight": 1.0},
        {"id": "r", "activity": "research", "earliest_start": "09:00", "latest_start": "12:00", "weight": 1.0}]}}),
        encoding="utf-8")
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)
    lf = idle()
    for hour, want in ((8, "window"), (10, "research"), (13, None)):
        tick(lf, at(hour))
        assert lf.day_hint == want, hour


def test_day_hint_is_kept_through_a_walk_and_refreshed_after_it_PIN(monkeypatch, tmp_path):
    path = tmp_path / "day_template.json"
    path.write_text(json.dumps({"shared": {"daily": [
        {"id": "w", "activity": "window", "earliest_start": "07:00", "latest_start": "09:00", "weight": 1.0},
        {"id": "r", "activity": "research", "earliest_start": "09:00", "latest_start": "12:00", "weight": 1.0}]}}),
        encoding="utf-8")
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)
    lf = idle()
    tick(lf, at(8))
    assert lf.day_hint == "window"
    lf.start("park", at(8), "walk to the park")
    tick(lf, at(10))                              # a walking tick returns before the hint is read (life.py:646)
    assert lf.path and lf.day_hint == "window"
    arrive(lf, at(10))
    tick(lf, at(10))
    assert lf.day_hint == "research"


def test_the_template_sleep_step_tilts_nothing_at_night():
    lf = idle("bed", "phone")
    tick(lf, at(0, 30))
    assert lf.day_hint == "sleep"                 # the repository's template: sleep is not a choice
    with_hint = lf.scores(at(0, 30), {}, 0.0, 0.0)
    lf.day_hint = None
    assert lf.scores(at(0, 30), {}, 0.0, 0.0) == with_hint


def test_day_hint_tilts_the_choice_only_when_the_plan_has_no_step():
    def window_share(hint, plan=None, n=400):
        lf = idle(seed=11)
        lf.day_hint, lf.plan_hint = hint, plan
        picks = [lf.choose(at(14), "AWAKE", {}, 0.0, 0.0) for _ in range(n)]
        return picks.count("window") / n

    assert window_share("window") > 0.6
    assert window_share(None) < 0.4
    assert window_share("window", plan="phone") < 0.4      # the plan's step is there, so the hint is not used


# --- labels ----------------------------------------------------------------------------------------------------------
def test_every_activity_has_a_label_and_the_snapshot_shows_it():
    for act, (place, _, _) in L.ACTIVITIES.items():
        lf = L.Life({"place": place, "activity": act, "until": 1e18}, rng=random.Random(0), body=fed())
        assert lf.label() == L.LABEL[act] == lf.snapshot()["doing"], act


def test_the_sleep_labels_say_walking_to_bed_on_the_way_and_sleeping_in_bed():
    assert asleep().label() == "sleeping"
    lf, t = idle(), at(23)
    lf.start("sleep", t, "goes to bed")
    assert lf.label() == "walking to bed" and lf.snapshot()["doing"] == "walking to bed"
    arrive(lf, t, "NREM")
    assert lf.label() == "sleeping"


def test_the_eating_and_ordering_labels_name_the_dish():
    assert L.Life({"place": "table", "activity": "eat", "eating": "ramen"}, rng=random.Random(0)).label() \
        == "eating ramen from the delivery"
    assert L.Life({"place": "table", "activity": "eat", "eating": "konbini_bento"}, rng=random.Random(0)).label() \
        == "eating a bento from the konbini"
    assert L.Life({"place": "bed", "activity": "order_food", "order_dish": "sushi"}, rng=random.Random(0)).label() \
        == "ordering sushi on the phone"
    assert L.Life({"place": "bed", "activity": "order_food"}, rng=random.Random(0)).label() \
        == L.LABEL["order_food"]


def test_while_walking_to_any_other_place_the_label_already_names_the_activity_PIN():
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    assert lf.path and lf.label() == L.LABEL["park"] and lf.snapshot()["pose"] == "walking"


# --- save and restore ----------------------------------------------------------------------------------------
def test_a_save_taken_mid_walk_resumes_the_same_walk():
    lf, t = mid_leg_walk()
    assert lf.path and lf.activity == "park"
    back = roundtrip(lf)
    assert (back.activity, back.place, back.path, back.trip) == (lf.activity, lf.place, lf.path, lf.trip)
    assert (back.until, back.dur) == (lf.until, lf.dur)
    assert back.label() == lf.label() == L.LABEL["park"]


def test_a_sleep_walk_saved_on_the_way_resumes_as_a_sleep_walk():
    lf, t = at_bench()
    t = tick(lf, t, "NREM")
    for _ in range(40):
        t = tick(lf, t, "NREM")
    back = roundtrip(lf)
    assert back.activity == "sleep" and back.place == lf.place and back.path == lf.path
    assert back.trip == "home-park" and back.label() == "walking to bed"


def test_a_pending_request_is_saved_and_still_carried_out_after_a_restart_PIN():
    lf, t = idle(), at(14)
    lf.start("park", t, "walk to the park")
    lf.request_impulse(window_request(), t)
    assert lf.to_dict()["impulse"] == ["window", "asked in chat: window", t]    # saved, as a list in the JSON state
    back = roundtrip(lf)
    assert back.impulse == ("window", "asked in chat: window", t)
    t = arrive(back, t)                                                          # the walk resumes on the way
    tick(back, t)
    assert back.activity == "window" and back.impulse is None
