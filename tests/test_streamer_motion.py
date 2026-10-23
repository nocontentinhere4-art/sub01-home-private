"""scripts/streamer_motion.py: behaviour over simulated minutes (frequencies inside the documented ranges, no state
flapping faster than 0.5 s, eye contact mostly while talking, hands consistent with the action, determinism).

    python -m pytest tests/test_streamer_motion.py -q
Pure module: no clock, no files, no network.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import streamer_motion as SM  # noqa: E402

HZ = 4
DT = 1.0 / HZ


def simulate(seconds, inputs, seed=11, md=None, t0=1000.0):
    """inputs(t) -> kwargs for tick; returns [(t, out)] at 4 Hz."""
    md = md or SM.MotionDirector(random.Random(seed))
    rows = []
    n = int(seconds * HZ)
    for i in range(n):
        t = t0 + i * DT
        rows.append((t, md.tick(t, **inputs(t))))
    return rows


def onsets(rows, pred):
    """Count rising edges of pred(out) and the lengths (s) of the runs."""
    count, runs, run = 0, [], 0
    prev = False
    for _, out in rows:
        cur = bool(pred(out))
        if cur and not prev:
            count += 1
        if cur:
            run += 1
        elif run:
            runs.append(run * DT)
            run = 0
        prev = cur
    if run:
        runs.append(run * DT)
    return count, runs


def fraction(rows, pred):
    return sum(1 for _, o in rows if pred(o)) / max(1, len(rows))


READING = lambda t: {"action": "scroll" if int(t) % 20 == 0 and t % 1 < DT else "read"}      # a scroll every 20 s
TALKING = lambda t: {"action": "read", "speaking": True}
CHAT = lambda t: {"action": "none", "speaking": True, "chat_addressed": True}
IDLE = lambda t: {"action": "none"}


# ---- shape, ranges, determinism -------------------------------------------------------------------------------------
def test_output_shape_and_ranges():
    rng = random.Random(3)
    rows = simulate(600, lambda t: {"action": rng.choice(SM.ACTIONS), "speaking": rng.random() < 0.3,
                                    "chat_addressed": rng.random() < 0.1,
                                    "reaction": rng.choice(SM.REACTIONS) if rng.random() < 0.02 else "none",
                                    "seconds_in_state": t % 1500}, seed=5)
    for _, o in rows:
        assert set(o) == {"state", "gaze_yaw_deg", "gaze_pitch_deg", "nod_strength", "intensity", "camera", "motion"}
        assert o["state"] in SM.STATES
        assert -20 <= o["gaze_yaw_deg"] <= 20 and -10 <= o["gaze_pitch_deg"] <= 10
        assert 0 <= o["nod_strength"] <= 1 and 0 <= o["intensity"] <= 1
        assert o["camera"] == "face"
        m = o["motion"]
        assert m["schema"] == SM.SCHEMA
        assert 0 <= m["lean"] <= 1 and 0 <= m["lean_back"] <= 1 and -12 <= m["head_tilt_deg"] <= 12
        assert m["look_at_camera"] in (0.0, 1.0) and m["look_to_chat"] in (0.0, 1.0)
        assert not (m["look_at_camera"] and m["look_to_chat"])
        assert m["hand_left"] in SM.HANDS and m["hand_right"] in SM.HANDS
        assert 0 <= m["gesture_strength"] <= 1 and 0.1 <= m["breathing_rate_hz"] <= 0.6
        assert m["fidget"] in SM.FIDGETS
        assert set(SM.event_fields(o)) == {"state", "gaze_yaw_deg", "gaze_pitch_deg", "nod_strength", "intensity", "camera"}


def test_deterministic_given_the_random_source():
    def inputs(t):
        r = random.Random(int(t * 10))
        return {"action": r.choice(SM.ACTIONS), "speaking": r.random() < 0.4, "chat_addressed": r.random() < 0.15,
                "reaction": r.choice(SM.REACTIONS) if r.random() < 0.03 else "none"}
    a = simulate(900, inputs, seed=42)
    b = simulate(900, inputs, seed=42)
    c = simulate(900, inputs, seed=43)
    assert [o for _, o in a] == [o for _, o in b]
    assert [o for _, o in a] != [o for _, o in c]


def test_constructor_validates():
    with pytest.raises(ValueError):
        SM.MotionDirector(random.Random(1), camera="webcam")
    with pytest.raises(ValueError):
        SM.MotionDirector(random.Random(1), mouse_state="reach")
    md = SM.MotionDirector(random.Random(1), mouse_state="reading", camera="spectator", chat_side=-1)
    o = md.tick(0.0, action="click")
    assert o["state"] == "reading" and o["camera"] == "spectator"
    md.tick(5.0, action="read")
    for k in range(40):                                   # the chat anchor is on the left for chat_side=-1
        o = md.tick(6 + k * 0.25, action="read")
        if o["motion"]["look_to_chat"]:
            assert o["gaze_yaw_deg"] < 0
            break


# ---- states ----------------------------------------------------------------------------------------------------------
def test_no_state_flapping_faster_than_half_a_second():
    r = random.Random(9)
    def jittery(t):                                       # inputs that change on nearly every tick
        return {"action": r.choice(SM.ACTIONS), "speaking": r.random() < 0.5,
                "reaction": r.choice(SM.REACTIONS) if r.random() < 0.3 else "none", "chat_addressed": r.random() < 0.3}
    rows = simulate(600, jittery, seed=1)
    changes = [t for (t, o), (_, p) in zip(rows[1:], rows[:-1]) if o["state"] != p["state"]]
    assert changes, "states never changed"
    gaps = [b - a for a, b in zip(changes, changes[1:])]
    assert min(gaps) >= SM.DEFAULTS["state_min_dwell_s"] - 1e-9


def test_state_follows_the_situation():
    md = SM.MotionDirector(random.Random(2))
    assert md.tick(0.0, action="none")["state"] == "idle"
    assert md.tick(1.0, action="read")["state"] == "reading"
    assert md.tick(2.0, action="scroll")["state"] == "mouse"
    assert md.tick(3.0, action="read")["state"] == "mouse"           # the mouse hold outlasts the single scroll tick
    assert md.tick(5.0, action="read")["state"] == "reading"
    assert md.tick(6.0, action="read", speaking=True)["state"] == "talking"
    o = md.tick(7.0, action="read", reaction="laugh")
    assert o["state"] == "reacting"
    assert md.tick(12.0, action="read", reaction="laugh")["state"] == "reading"   # the same reaction does not retrigger
    assert md.tick(13.0, action="read", reaction="none")["state"] == "reading"
    assert md.tick(14.0, action="read", reaction="laugh")["state"] == "reacting"  # ... after none it fires again


def test_paused_is_neutral():
    md = SM.MotionDirector(random.Random(2))
    for k in range(40):
        md.tick(k * 0.25, action="type", speaking=True, chat_addressed=True)
    o = md.tick(10.0, action="type", speaking=True, chat_addressed=True, reaction="laugh", paused=True)
    for k in range(20):
        o = md.tick(10.25 + k * 0.25, action="type", speaking=True, paused=True)
    assert o["state"] == "idle" and o["intensity"] == 0 and o["camera"] == "spectator"
    assert o["motion"]["hand_left"] == "rest" and o["motion"]["hand_right"] == "rest"
    assert o["motion"]["look_at_camera"] == 0 and o["motion"]["fidget"] == "none" and o["nod_strength"] == 0


# ---- eyes --------------------------------------------------------------------------------------------------------------
def test_camera_glances_while_talking_every_20_to_40_s_for_1_to_2_s():
    rows = simulate(20 * 60, TALKING, seed=21)
    n, runs = onsets(rows, lambda o: o["motion"]["look_at_camera"] > 0.5)
    per_min = n / 20
    assert 1.2 <= per_min <= 3.4, per_min                 # 60/40 .. 60/20 per minute, with jitter
    assert runs and min(runs) >= 1.0 - DT and max(runs) <= 2.0 + DT
    # the gaze actually rises towards the lens above the monitor while looking at it
    up = [o["gaze_pitch_deg"] for _, o in rows if o["motion"]["look_at_camera"] > 0.5]
    assert sum(up) / len(up) > 3.0


def test_eye_contact_mostly_while_talking():
    talking = simulate(10 * 60, TALKING, seed=4)
    chatting = simulate(10 * 60, CHAT, seed=4)
    reading = simulate(10 * 60, READING, seed=4)
    idle = simulate(10 * 60, IDLE, seed=4)
    cam = lambda o: o["motion"]["look_at_camera"] > 0.5
    assert fraction(chatting, cam) >= 0.45                # answering chat: most of the time to the lens
    assert 0.03 <= fraction(talking, cam) <= 0.12         # a glance now and then while commenting
    assert fraction(reading, cam) == 0 and fraction(idle, cam) == 0   # never while silent (reactions aside)


def test_chat_answer_reads_the_message_first_then_turns_to_the_camera():
    md = SM.MotionDirector(random.Random(8))
    for k in range(20):
        md.tick(k * 0.25, action="read")
    rows = [(5 + k * 0.25, md.tick(5 + k * 0.25, action="none", speaking=True, chat_addressed=True)) for k in range(80)]
    first = rows[0][1]["motion"]
    assert first["look_to_chat"] == 1.0 and first["look_at_camera"] == 0.0
    t_cam = next(t for t, o in rows if o["motion"]["look_at_camera"] > 0.5)
    assert 1.0 <= t_cam - 5 <= 2.75                       # chat_read_first_s (1.2, 2.5) plus one tick
    assert any(o["motion"]["look_to_chat"] for t, o in rows if t > t_cam)   # glances back to the chat while answering
    # leaning in towards the lens once he answers
    assert max(o["motion"]["lean"] for t, o in rows if t <= t_cam + 1.5) >= 0.5
    # and the lean relaxes after the answer
    after = [md.tick(25 + k * 0.25, action="read") for k in range(24)]
    assert after[-1]["motion"]["lean"] < 0.4


def test_chat_glances_while_reading_every_30_to_90_s():
    rows = simulate(30 * 60, READING, seed=12)
    n, runs = onsets(rows, lambda o: o["motion"]["look_to_chat"] > 0.5)
    assert 14 <= n <= 72, n                               # 1800/90 .. 1800/30 with jitter
    assert runs and min(runs) >= 1.0 - DT and max(runs) <= 3.0 + DT
    turned = [o["gaze_yaw_deg"] for _, o in rows if o["motion"]["look_to_chat"] > 0.5]
    assert sum(turned) / len(turned) > 8.0                # the head turns to the chat side (right by default)


def test_no_chat_glance_while_typing():
    rows = simulate(10 * 60, lambda t: {"action": "type"}, seed=3)
    assert all(o["motion"]["look_to_chat"] == 0 for _, o in rows)
    assert all(o["motion"]["look_at_camera"] == 0 for _, o in rows)


# ---- hands --------------------------------------------------------------------------------------------------------------
def test_hands_reach_the_keyboard_before_typing_starts_and_linger_after():
    md = SM.MotionDirector(random.Random(5))
    for k in range(40):
        md.tick(k * 0.1, action="read")
    o = md.tick(4.0, action="type")
    assert o["motion"]["hand_left"] == "keyboard" and o["motion"]["hand_right"] == "keyboard"
    assert o["state"] != "typing"                         # the clip follows the hands, not the other way round
    o2 = md.tick(4.2, action="type")
    assert o2["state"] != "typing"
    o3 = md.tick(4.5, action="type")
    assert o3["state"] == "typing"                        # hands_lead_s 0.3 passed (and the 0.5 s dwell)
    # the action ended: hands linger 0.6 s, then back to the mouse
    o4 = md.tick(5.0, action="none")
    assert o4["motion"]["hand_right"] == "keyboard"
    o5 = md.tick(5.7, action="none")
    assert o5["motion"]["hand_right"] == "mouse" and o5["motion"]["hand_left"] == "rest"


def test_hands_consistent_with_the_action_over_minutes():
    typing = simulate(5 * 60, lambda t: {"action": "type"}, seed=6)
    assert all(o["motion"]["hand_left"] == "keyboard" and o["motion"]["hand_right"] == "keyboard" for _, o in typing[4:])
    assert all(o["motion"]["fidget"] == "none" for _, o in typing)
    pointing = simulate(5 * 60, lambda t: {"action": "scroll" if int(t * 4) % 8 == 0 else "click"}, seed=6)
    assert all(o["motion"]["hand_right"] in ("mouse", "gesture") for _, o in pointing)
    assert fraction(pointing, lambda o: o["motion"]["hand_right"] == "mouse") >= 0.9
    assert all(o["motion"]["hand_left"] != "keyboard" for _, o in pointing)
    reading = simulate(10 * 60, READING, seed=6)
    assert fraction(reading, lambda o: o["motion"]["hand_right"] == "mouse") >= 0.85   # the mouse hand stays while reading
    assert all(o["motion"]["hand_left"] in ("rest", "gesture") for _, o in reading)
    assert fraction(reading, lambda o: o["motion"]["hand_left"] == "gesture") <= 0.15


def test_mouse_hand_drifts_to_rest_after_a_long_still_read():
    rows = simulate(4 * 60, lambda t: {"action": "read"}, seed=7)   # no pointer action at all
    early = [o for t, o in rows if t - rows[0][0] < 60]
    late = [o for t, o in rows if t - rows[0][0] > 150]
    assert fraction([(0, o) for o in early], lambda o: o["motion"]["hand_right"] == "mouse") >= 0.85
    assert fraction([(0, o) for o in late], lambda o: o["motion"]["hand_right"] == "mouse") == 0


def test_fidgets_every_40_to_110_s_with_the_free_hand():
    rows = simulate(30 * 60, IDLE, seed=13)
    n, runs = onsets(rows, lambda o: o["motion"]["fidget"] not in ("none", "stretch"))
    assert 12 <= n <= 54, n                               # 1800/110 .. 1800/40 with jitter and skips
    assert runs and min(runs) >= 1.0 - DT and max(runs) <= 5.0 + DT
    kinds = {o["motion"]["fidget"] for _, o in rows} - {"none"}
    assert {"face", "headphones", "drink"} & kinds
    for _, o in rows:
        m = o["motion"]
        if m["fidget"] in ("face", "headphones", "neck", "drink"):
            assert "gesture" in (m["hand_left"], m["hand_right"]) and m["gesture_strength"] > 0


def test_stretch_is_rare_and_quiet_only():
    rows = simulate(60 * 60, IDLE, seed=14)
    n, runs = onsets(rows, lambda o: o["motion"]["fidget"] == "stretch")
    assert 2 <= n <= 7, n                                 # every 600-1200 s
    assert runs and min(runs) >= 3.0 - DT and max(runs) <= 6.0 + DT
    for _, o in rows:
        if o["motion"]["fidget"] == "stretch":
            assert o["motion"]["hand_left"] == "gesture" and o["motion"]["hand_right"] == "gesture"
    talking = simulate(60 * 60, TALKING, seed=14)
    assert all(o["motion"]["fidget"] != "stretch" for _, o in talking)


def test_gestures_while_answering_chat_more_than_while_commenting():
    chat = simulate(10 * 60, CHAT, seed=15)
    talk = simulate(10 * 60, TALKING, seed=15)
    g = lambda o: o["motion"]["gesture_strength"] >= 0.35
    n_chat, _ = onsets(chat, g)
    n_talk, _ = onsets(talk, g)
    assert 30 <= n_chat <= 110, n_chat                    # every 6-14 s plus the gesture itself
    assert 15 <= n_talk <= 55, n_talk                     # every 12-30 s
    assert n_chat > n_talk
    assert any(o["motion"]["hand_right"] == "gesture" for _, o in chat)    # the mouse hand may leave the mouse for chat
    assert all(o["motion"]["hand_right"] != "gesture" or o["motion"]["gesture_strength"] > 0 for _, o in talk)


# ---- reactions and posture -------------------------------------------------------------------------------------------
def react_rows(kind, seed=16):
    md = SM.MotionDirector(random.Random(seed))
    for k in range(40):
        md.tick(k * 0.25, action="read")
    rows = []
    for k in range(60):
        t = 10 + k * 0.25
        rows.append((t - 10, md.tick(t, action="read", reaction=kind if t - 10 < 4 else "none")))
    return rows


def test_laugh_leans_back_tilts_shares_with_the_camera_then_recovers():
    rows = react_rows("laugh")
    assert rows[0][1]["state"] == "reacting" and rows[0][1]["nod_strength"] >= 0.7
    peak_t = max(rows, key=lambda r: r[1]["motion"]["lean_back"])
    assert peak_t[1]["motion"]["lean_back"] >= 0.5 and peak_t[0] <= 2.0
    assert max(abs(o["motion"]["head_tilt_deg"]) for _, o in rows) >= 4.0
    assert any(o["motion"]["look_at_camera"] for t, o in rows if 0.75 <= t <= 2.5)
    assert rows[-1][1]["motion"]["lean_back"] < 0.15 and abs(rows[-1][1]["motion"]["head_tilt_deg"]) < 1.0
    assert rows[-1][1]["state"] == "reading"
    assert max(o["motion"]["breathing_rate_hz"] for _, o in rows) > 0.3


def test_surprise_head_back_then_in_to_the_screen():
    rows = react_rows("surprise")
    early = [o["motion"]["lean_back"] for t, o in rows if t <= 0.6]
    assert max(early) >= 0.2
    later = [o["motion"]["lean"] for t, o in rows if 1.2 <= t <= 2.0]
    assert max(later) >= 0.4
    assert any(o["motion"]["look_at_camera"] for t, o in rows if 0.5 <= t <= 2.0)
    assert all(o["intensity"] >= 0.6 for t, o in rows if t < 1.5)


def test_think_tilts_the_head_and_looks_off_screen():
    rows = react_rows("think", seed=17)
    assert max(abs(o["motion"]["head_tilt_deg"]) for _, o in rows) >= 5.0
    off = [abs(o["gaze_yaw_deg"]) for t, o in rows if 0.75 <= t <= 1.5]
    assert max(off) >= 4.0
    assert all(o["motion"]["look_at_camera"] == 0 for _, o in rows)


def test_lean_and_lean_back_move_smoothly():
    r = random.Random(18)
    rows = simulate(300, lambda t: {"action": r.choice(SM.ACTIONS), "speaking": r.random() < 0.5,
                                    "chat_addressed": r.random() < 0.3,
                                    "reaction": r.choice(SM.REACTIONS) if r.random() < 0.05 else "none"}, seed=18)
    step = DT / SM.DEFAULTS["lean_rise_s"] + 2e-3                   # the slew limit plus the 3-decimal rounding
    for (_, a), (_, b) in zip(rows, rows[1:]):
        assert abs(b["motion"]["lean"] - a["motion"]["lean"]) <= step
        assert abs(b["motion"]["lean_back"] - a["motion"]["lean_back"]) <= step
        assert abs(b["gaze_yaw_deg"] - a["gaze_yaw_deg"]) <= 26.0   # eased: under two thirds of the range per tick


def test_posture_shifts_every_150_to_300_s_and_long_focus_slumps():
    rows = simulate(60 * 60, lambda t: {"action": "read", "seconds_in_state": 60.0}, seed=19)
    n, runs = onsets(rows, lambda o: o["motion"]["posture"] == "back")
    assert 7 <= n <= 25, n                                # 3600/300 .. 3600/150 with the 20-60 s holds; stretches take a slot
    assert runs and min(runs) >= 20 - DT and max(runs) <= 60 + DT
    fresh = simulate(120, lambda t: {"action": "read", "seconds_in_state": 60.0}, seed=20)
    stale = simulate(120, lambda t: {"action": "read", "seconds_in_state": 1500.0}, seed=20)
    assert stale[-1][1]["motion"]["lean_back"] > fresh[-1][1]["motion"]["lean_back"]
    assert any(o["motion"]["posture"] == "slump" for _, o in stale)
    assert all(o["motion"]["posture"] != "slump" for _, o in fresh)


def test_nods_while_talking_at_phrase_rate_and_on_speech_start():
    md = SM.MotionDirector(random.Random(22))
    for k in range(8):
        md.tick(k * 0.25, action="read")
    first = md.tick(2.0, action="read", speaking=True)
    assert first["nod_strength"] >= 0.35
    rows = [(2 + k * 0.25, md.tick(2 + k * 0.25, action="read", speaking=True)) for k in range(1, 5 * 60 * HZ)]
    n, _ = onsets(rows, lambda o: o["nod_strength"] >= 0.1)
    assert 45 <= n <= 150, n                              # every 2.5-5 s over five minutes
    silent = simulate(5 * 60, READING, seed=22)
    n_silent, _ = onsets(silent, lambda o: o["nod_strength"] >= 0.1)
    assert n_silent == 0


def test_breathing_slower_while_talking_than_at_rest():
    rest = simulate(120, IDLE, seed=23)[-1][1]["motion"]["breathing_rate_hz"]
    talk = simulate(120, TALKING, seed=23)[-1][1]["motion"]["breathing_rate_hz"]
    read = simulate(120, lambda t: {"action": "read"}, seed=23)[-1][1]["motion"]["breathing_rate_hz"]
    assert talk < read <= rest
    assert abs(rest - SM.DEFAULTS["breath_rest_hz"]) < 0.01


def test_intensity_by_state_and_chat_bonus():
    md = SM.MotionDirector(random.Random(24))
    assert md.tick(0.0, action="none")["intensity"] == pytest.approx(0.1)
    assert md.tick(1.0, action="read")["intensity"] == pytest.approx(0.3)
    assert md.tick(2.0, action="read", speaking=True)["intensity"] == pytest.approx(0.6)
    assert md.tick(3.0, action="read", speaking=True, chat_addressed=True)["intensity"] == pytest.approx(0.7)
    assert md.tick(4.0, action="read", reaction="laugh")["intensity"] == pytest.approx(0.8)


def test_screen_target_steers_the_gaze():
    md = SM.MotionDirector(random.Random(25))
    for k in range(8):
        md.tick(k * 0.25, action="read")
    rows = [md.tick(2 + k * 0.25, action="click", screen_target=(0.95, 0.9)) for k in range(12)]
    assert rows[-1]["gaze_yaw_deg"] > 10 and rows[-1]["gaze_pitch_deg"] < -4
    rows = [md.tick(5 + k * 0.25, action="click", screen_target=(0.05, 0.1)) for k in range(12)]
    assert rows[-1]["gaze_yaw_deg"] < -10 and rows[-1]["gaze_pitch_deg"] > 4
