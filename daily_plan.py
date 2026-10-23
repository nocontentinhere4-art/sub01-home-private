"""SUB-01's day plan: the activity the day template most likely has at a simulated hour.

hint(hour) is for life.py to consult. It reads docs/design/daily-life/day_template.json and nothing else: stdlib
only, no network, and nothing here starts an activity.
"""
import json
import math
import re
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent / "docs" / "design" / "daily-life" / "day_template.json"
_CLOCK = re.compile(r"([0-9]{1,2}):([0-9]{2})")
_CACHE = {}     # resolved path -> entries; filled only after a successful read


def load(path=None) -> list:
    """The template's entries in file order, as dicts with id, activity, start, end and weight.

    start and end are simulated hours (end may pass 24.0). Entries with a null activity are included, with
    activity None. A missing or invalid file gives []. The default file is read once and then cached.
    """
    return [dict(entry) for entry in _entries(path)]


def hint(hour: float, activities=None) -> str | None:
    """The activity most likely at a simulated hour (0 <= hour < 24), or None.

    An entry takes part when its window contains the hour, either as it is or 24 hours later, so windows
    written past 24:00 work. Null activities and weight 0 are ignored. If activities (a set of names) is given,
    only those names take part. The highest weight wins; ties go to the earlier entry in the file. Hours outside
    0 to 24 wrap around the clock. Never raises.
    """
    try:
        clock = float(hour) % 24.0
        if not math.isfinite(clock):
            return None
        if isinstance(activities, str):
            activities = {activities}
        allowed = None if activities is None else set(activities)
        best = None
        for entry in _entries():
            name = entry["activity"]
            if name is None or entry["weight"] <= 0:
                continue
            if allowed is not None and name not in allowed:
                continue
            if not any(entry["start"] <= clock + shift <= entry["end"] for shift in (0.0, 24.0)):
                continue
            if best is None or entry["weight"] > best["weight"]:
                best = entry
        return None if best is None else best["activity"]
    except Exception:
        return None


def _entries(path=None) -> list:
    key = str(_DEFAULT_PATH if path is None else path)
    entries = _CACHE.get(key)
    if entries is None:
        entries = _read(key)
        if entries is None:
            return []
        _CACHE[key] = entries
    return entries


def _read(path: str):
    """The entries of the template at path, or None if the file is missing, unreadable or not a valid template."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        entries = []
        _collect(data, 1.0, entries)
    except Exception:
        return None
    return entries


def _collect(node, factor: float, out: list) -> None:
    """Append the entries under node in file order. An entry is an object with an "activity" key. An object
    without one that has a weight (a meal option) multiplies the weights of the entries inside it: a step's
    weight of 1.0 applies only once its option is picked."""
    if isinstance(node, list):
        for item in node:
            _collect(item, factor, out)
    elif isinstance(node, dict):
        if "activity" in node:
            out.append(_entry(node, factor))
            return
        if "weight" in node:
            factor *= _weight(node["weight"])
        for value in node.values():
            _collect(value, factor, out)


def _entry(node: dict, factor: float) -> dict:
    activity = node["activity"]
    if activity is not None and (not isinstance(activity, str) or not activity):
        raise ValueError(f"bad activity {activity!r}")
    start = _clock(node["earliest_start"])
    end = _clock(node["latest_start"])
    if end < start:     # a window written across midnight without 24:00 notation, e.g. 23:00 to 01:00
        end += 24.0
    weight = factor * _weight(node["weight"])
    return {"id": node.get("id"), "activity": activity, "start": start, "end": end, "weight": weight}


def _clock(text) -> float:
    """Parse "HH:MM" into simulated hours. 24:00 and later are allowed, as in the template."""
    match = _CLOCK.fullmatch(text) if isinstance(text, str) else None
    if match is None or int(match.group(1)) > 47 or int(match.group(2)) > 59:
        raise ValueError(f"bad time {text!r}")
    return int(match.group(1)) + int(match.group(2)) / 60.0


def _weight(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"bad weight {value!r}")
    return float(value)
