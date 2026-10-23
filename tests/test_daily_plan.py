"""daily_plan.hint: plain and midnight-crossing windows, weights, null activities, the activities filter, bad files.

    python -m pytest tests/test_daily_plan.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import daily_plan  # noqa: E402


def window(activity, start, end, weight=1.0):
    return {"id": f"{activity}-{start}", "activity": activity, "earliest_start": start,
            "latest_start": end, "weight": weight}


def use_template(monkeypatch, tmp_path, daily):
    path = tmp_path / "day_template.json"
    path.write_text(json.dumps({"shared": {"daily": daily}}), encoding="utf-8")
    monkeypatch.setattr(daily_plan, "_DEFAULT_PATH", path)


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


def test_null_activity_is_ignored(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window(None, "07:00", "09:00", weight=1.0),
                                         window("eat", "07:00", "09:00", weight=0.2)])
    assert daily_plan.hint(8.0) == "eat"


def test_only_null_activities_give_none(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window(None, "07:00", "09:00")])
    assert daily_plan.hint(8.0) is None


def test_highest_weight_wins_and_ties_go_to_earlier_entry(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [
        window("phone", "09:00", "12:00", weight=0.15),
        window("research", "09:00", "12:00", weight=0.20),
        window("chat", "09:00", "12:00", weight=0.20),
    ])
    assert daily_plan.hint(10.0) == "research"


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


def test_bad_hour_returns_none(monkeypatch, tmp_path):
    use_template(monkeypatch, tmp_path, [window("eat", "07:00", "09:00")])
    assert daily_plan.hint(float("nan")) is None
    assert daily_plan.hint(None) is None


def test_repository_template_sleeps_after_midnight():
    assert daily_plan.hint(0.5) == "sleep"
