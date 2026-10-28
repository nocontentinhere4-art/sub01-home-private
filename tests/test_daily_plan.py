"""daily_plan.hint: windows (plain, midnight-crossing, sleep spans), weights, null activities, the activities filter,
bad files and entries, the cache, speed, and the repository template's day against life.py's hour rules.

    python -m pytest tests/test_daily_plan.py -q
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import daily_plan  # noqa: E402
import life  # noqa: E402

TEMPLATE = Path(__file__).resolve().parents[1] / "docs" / "design" / "daily-life" / "day_template.json"

# The typical weekday at home, as docs/design/daily-life/README.md lists it: (start, activity). Each runs to the next.
DAY = [("00:00", "listen_music"), ("00:30", "sleep"), ("08:00", "phone"), ("09:00", "eat"),
       ("10:00", "buy_bread"), ("11:00", "research"), ("12:00", "eat"), ("12:30", "research"),
       ("16:30", "park"), ("17:30", "buy_bread"), ("18:15", "phone"), ("18:30", "play_console"),
       ("19:00", "eat"), ("21:00", "play_console"), ("22:30", "phone"), ("23:30", "listen_music")]


def window(activity, start, end, weight=1.0):
    return {"id": f"{activity}-{start}", "activity": activity, "earliest_start": start,
            "latest_start": end, "weight": weight}


def sleep_entry(start="00:30", wake="08:00", weight=1.0):
    return {"id": "sleep_test", "activity": "sleep", "earliest_start": "23:45", "latest_start": "25:00",
            "target_start": start, "wake": {"earliest": "07:30", "target": wake, "latest": "09:00"},
            "duration_min": [0, 0], "weight": weight}


def use_template(monkeypatch, tmp_path, daily):
    path = tmp_path / "day_template.json"
    path.write_text(json.dumps({"shared": {"daily": daily}}), encoding="utf-8")
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)
    return path


def clock_hours(text):
    hours, minutes = text.split(":")
    return int(hours) + int(minutes) / 60


def all_entries(node, out):
    """Every object with an "activity" key in the whole template, wherever it sits."""
    if isinstance(node, list):
        for item in node:
            all_entries(item, out)
    elif isinstance(node, dict):
        if "activity" in node:
            out.append(node)
        for value in node.values():
            all_entries(value, out)
    return out


def test_plain_window_inside_and_outside(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window("eat", "07:30", "10:00")])
    assert daily_plan.hint(7.5) == "eat"
    assert daily_plan.hint(10.0) == "eat"
    assert daily_plan.hint(7.25) is None
    assert daily_plan.hint(10.25) is None


def test_window_crossing_midnight(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window("sleep", "23:30", "25:00")])
    assert daily_plan.hint(23.5) == "sleep"
    assert daily_plan.hint(0.5) == "sleep"      # 00:30 is 24:30 on the template clock
    assert daily_plan.hint(1.0) == "sleep"      # 01:00 is 25:00, the end of the window
    assert daily_plan.hint(1.5) is None
    assert daily_plan.hint(12.0) is None


def test_window_written_with_clock_times_across_midnight(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window("listen_music", "22:00", "01:00")])
    assert daily_plan.hint(22.5) == "listen_music"
    assert daily_plan.hint(0.5) == "listen_music"
    assert daily_plan.hint(2.0) is None


def test_sleep_entry_spans_the_night_from_target_bedtime_to_wake(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [sleep_entry(), window("listen_music", "22:00", "25:00", weight=0.12)])
    assert daily_plan.hint(23.0) == "listen_music"   # still awake before the target bedtime
    assert daily_plan.hint(0.5) == "sleep"           # the target bedtime, 00:30
    assert daily_plan.hint(5.0) == "sleep"
    assert daily_plan.hint(8.0) == "sleep"           # the target wake ends the span
    assert daily_plan.hint(8.25) is None


def test_null_activity_is_ignored(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window(None, "07:00", "09:00", weight=1.0),
                                         window("eat", "07:00", "09:00", weight=0.2)])
    assert daily_plan.hint(8.0) == "eat"


def test_only_null_activities_give_none(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window(None, "07:00", "09:00")])
    assert daily_plan.hint(8.0) is None


def test_largest_total_wins_and_ties_go_to_the_earlier_activity(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [
        window("phone", "09:00", "12:00", weight=0.15),
        window("research", "09:00", "12:00", weight=0.20),
        window("chat", "09:00", "12:00", weight=0.20),
    ])
    assert daily_plan.hint(10.0) == "research"


def test_alternatives_of_one_activity_add_up(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [
        window("research", "09:00", "12:00", weight=0.15),
        window("phone", "09:00", "12:00", weight=0.20),
        window("research", "09:00", "12:00", weight=0.10),
    ])
    assert daily_plan.hint(10.0) == "research"      # 0.25 in all, against 0.20 for phone
    assert daily_plan.hint(10.0, activities={"phone"}) == "phone"


def test_meal_option_weight_applies_to_its_steps(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [{"group": "breakfast", "options": [
        {"id": "bf_bakery", "weight": 0.10, "steps": [window("buy_bread", "07:00", "09:30")]},
        {"id": "bf_stock", "weight": 0.40, "steps": [window("eat", "07:30", "10:00")]},
    ]}])
    assert daily_plan.hint(7.25) == "buy_bread"
    assert daily_plan.hint(8.0) == "eat"


def test_activities_filter_keeps_only_listed_names(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [
        window("phone", "09:00", "12:00", weight=0.15),
        window("research", "09:00", "12:00", weight=0.20),
    ])
    assert daily_plan.hint(10.0) == "research"
    assert daily_plan.hint(10.0, activities={"phone"}) == "phone"
    assert daily_plan.hint(10.0, activities="phone") == "phone"
    assert daily_plan.hint(10.0, activities={"sleep"}) is None
    assert daily_plan.hint(10.0, activities=set()) is None


def test_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", tmp_path / "absent.json")
    assert daily_plan.hint(8.0) is None
    assert daily_plan.load() == []


def test_invalid_file_returns_none(monkeypatch, tmp_path):
    path = tmp_path / "day_template.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)
    assert daily_plan.hint(8.0) is None
    assert daily_plan.load() == []


def test_a_file_without_shared_is_invalid(monkeypatch, tmp_path):
    path = tmp_path / "day_template.json"
    path.write_text(json.dumps({"day_types": {}}), encoding="utf-8")
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)
    assert daily_plan.load() == []
    assert daily_plan.hint(8.0) is None


@pytest.mark.parametrize("bad", [
    window("eat", "25:99", "09:00"),                       # minutes past 59
    window("eat", "07:00", "09:00", weight=-1.0),          # a negative weight
    window("eat", "07:00", "09:00", weight=True),          # a bool is not a weight
    window("", "07:00", "09:00"),                          # an empty activity name
    {"id": "no_window", "activity": "eat", "weight": 1.0},  # no window at all
])
def test_one_bad_entry_makes_the_whole_file_invalid(monkeypatch, tmp_path, bad):
    use_template(monkeypatch, tmp_path, [window("phone", "07:00", "09:00"), bad])
    assert daily_plan.load() == []
    assert daily_plan.hint(8.0) is None


@pytest.mark.parametrize("hour", [float("nan"), float("inf"), float("-inf"), None, "x", [], object(), 1 + 2j])
def test_bad_hour_never_raises(monkeypatch, tmp_path, hour):
    use_template(monkeypatch, tmp_path, [window("eat", "07:00", "09:00")])
    assert daily_plan.hint(hour) is None


@pytest.mark.parametrize("activities", [5, object()])
def test_bad_activities_never_raise(monkeypatch, tmp_path, activities):
    use_template(monkeypatch, tmp_path, [window("eat", "07:00", "09:00")])
    assert daily_plan.hint(8.0, activities=activities) is None


def test_day_types_are_not_read_by_hint(monkeypatch, tmp_path):
    path = tmp_path / "day_template.json"
    path.write_text(json.dumps({
        "shared": {"daily": [window("eat", "07:00", "09:00", weight=0.2)]},
        "day_types": {"class_day": {"entries": [window("research", "07:00", "09:00", weight=0.9)]}},
    }), encoding="utf-8")
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)
    assert daily_plan.hint(8.0) == "eat"
    assert [entry["activity"] for entry in daily_plan.load()] == ["eat"]


def test_the_template_is_read_once_until_clear_cache(monkeypatch, tmp_path):
    path = use_template(monkeypatch, tmp_path, [window("eat", "07:00", "09:00")])
    assert daily_plan.hint(8.0) == "eat"
    path.write_text(json.dumps({"shared": {"daily": [window("phone", "07:00", "09:00")]}}), encoding="utf-8")
    assert daily_plan.hint(8.0) == "eat"            # the cached reading, not the new file
    daily_plan.clear_cache()
    assert daily_plan.hint(8.0) == "phone"


def test_a_failed_read_is_cached_too(monkeypatch, tmp_path):
    path = tmp_path / "later.json"
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)
    assert daily_plan.hint(8.0) is None
    path.write_text(json.dumps({"shared": {"daily": [window("eat", "07:00", "09:00")]}}), encoding="utf-8")
    assert daily_plan.hint(8.0) is None             # not read again
    daily_plan.clear_cache()
    assert daily_plan.hint(8.0) == "eat"


def test_load_returns_copies(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window("eat", "07:00", "09:00")])
    daily_plan.load()[0]["activity"] = "phone"
    assert daily_plan.hint(8.0) == "eat"


def test_ten_thousand_calls_take_under_a_second():
    daily_plan.hint(8.0)                            # the first call reads the template
    started = time.perf_counter()
    for i in range(10_000):
        daily_plan.hint((i % 2400) / 100)
    assert time.perf_counter() - started < 1.0


def test_every_half_hour_of_the_repository_template_is_a_life_activity():
    for step in range(48):
        for hour in (step / 2, step / 2 + 0.25):
            assert daily_plan.hint(hour) in life.ACTIVITIES, hour


def test_repository_template_day_sequence_minute_by_minute():
    starts = [clock_hours(start) for start, _ in DAY]
    for minute in range(24 * 60):
        hour = minute / 60 + 1 / 120                     # the middle of the minute, clear of every window edge
        index = max(i for i, begin in enumerate(starts) if begin <= hour)
        assert daily_plan.hint(hour) == DAY[index][1], f"{minute // 60:02d}:{minute % 60:02d}"


def test_repository_template_respects_life_hour_rules():
    bakery_walk = life.WALK_S["home-bakery"] / 3600      # hours from home to the bakery counter
    park_walk = life.WALK_S["home-park"] / 3600
    for step in range(96):
        hour = step / 4 + 0.125                          # off the quarter hours, away from the window edges
        name = daily_plan.hint(hour)
        open_bakery = 7 <= hour + bakery_walk < 20       # life.py: buy_bread while open, buy_konbini while closed
        if name == "buy_bread":
            assert open_bakery, hour
        if name == "buy_konbini":
            assert not open_bakery, hour
        if name == "park":
            assert 8 <= hour and hour + park_walk < life.PARK_CLOSES, hour     # the weekday opening
        if name == "order_food":
            assert 10 <= hour < 23.5, hour               # life.py kitchen_open
        if name in ("research", "play_console", "use_computer", "window"):
            assert hour >= life.NIGHT_END, hour          # the desk is off from 00:00 to 06:00


def test_repository_template_entry_counts_and_names():
    entries = all_entries(json.loads(TEMPLATE.read_text(encoding="utf-8")), [])
    assert len(entries) == 46
    nulls = [entry for entry in entries if entry["activity"] is None]
    assert len(nulls) == 17
    assert all(str(entry.get("proposal", "")).startswith("P") for entry in nulls)
    assert {entry["activity"] for entry in entries if entry["activity"] is not None} <= set(life.ACTIVITIES)


def test_load_gives_the_shared_part_of_the_repository_template():
    entries = daily_plan.load()
    assert len(entries) == 37
    assert sum(entry["activity"] is None for entry in entries) == 9
