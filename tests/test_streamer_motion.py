"""scripts/streamer_motion.py: behaviour over simulated minutes (frequencies inside the documented ranges, no state
flapping faster than the dwell, camera looks only for chat answers and shared reactions, a nearly still reading head,
hands consistent with the action, determinism). Ranges: DEFAULTS and docs/streamer/kimi/DECISIONS-ANIMATION-STREAM.md.

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
D = SM.DEFAULTS


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
CAM = lambda o: o["motion"]["look_at_camera"] > 0.5
CHAT_LOOK = lambda o: o["motion"]["look_to_chat"] > 0.5


def answers(period=40.0, length=8.0):
    """Realistic chat answers: `length` s of speech to a viewer every `period` s, reading in between."""
    def inputs(t):
        if (t - 1000.0) % period < length:
            return {"action": "none", "speaking": True, "chat_addressed": True}
        return {"action": "read"}
    return inputs


# ---- shape, ranges, determinism -------------------------------------------------------------------------------------
def test_output_shape_and_ranges():
    rng = random.Random(3)
    rows = simulate(600, lambda t: {"action": rng.choice(SM.ACTIONS), "speaking": rng.random() < 0.3,
                                    "chat_addressed": rng.random() < 0.1,
                                    "reaction": rng.choice(SM.REACTIONS) if rng.random() < 0.02 else "none",
                                    "seconds_in_state": t % 1500,
                                    "screen_target": (rng.random(), rng.random()) if rng.random() < 0.2 else None}, seed=5)
    for _, o in rows:
        assert set(o) == {"state", "gaze_yaw_deg", "gaze_pitch_deg", "nod_strength", "intensity", "camera", "motion"}
        assert o["state"] in SM.STATES
        assert -20 <= o["gaze_yaw_deg"] <= 20 and -10 <= o["gaze_pitch_deg"] <= 10
        assert 0 <= o["nod_strength"] <= 1 and 0 <= o["intensity"] <= 1
        assert o["camera"] == "face"
        m = o["motion"]
        assert set(m) == {"schema", "lean", "lean_back", "head_tilt_deg", "look_at_camera", "look_to_chat", "hand_left",
                          "hand_right", "gesture_strength", "breathing_rate_hz", "fidget", "posture"}
        assert m["schema"] == SM.SCHEMA
        assert 0 <= m["lean"] <= 1 and 0 <= m["lean_back"] <= 1 and -12 <= m["head_tilt_deg"] <= 12
        assert not (m["lean"] > 0 and m["lean_back"] > 0)             # one signed posture channel
        assert m["look_at_camera"] in (0.0, 1.0) and m["look_to_chat"] in (0.0, 1.0)
        assert not (m["look_at_camera"] and m["look_to_chat"])
        assert m["hand_left"] in SM.HANDS and m["hand_right"] in SM.HANDS
        assert 0 <= m["gesture_strength"] <= 1 and 0.1 <= m["breathing_rate_hz"] <= 0.6
        assert m["fidget"] in SM.FIDGETS
        assert m["posture"] in ("neutral", "upright", "forward", "back", "slump")
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
    rows = simulate(200, lambda t: {"action": "read"}, md=md, t0=1.0)
    turned = [o["gaze_yaw_deg"] for _, o in rows if CHAT_LOOK(o)]
    assert turned and max(turned) < 0                                 # the chat anchor is on the left for chat_side=-1


# ---- states ----------------------------------------------------------------------------------------------------------
def test_no_state_flapping_faster_than_the_dwell():
    r = random.Random(9)
    def jittery(t):                                       # inputs that change on nearly every tick
        return {"action": r.choice(SM.ACTIONS), "speaking": r.random() < 0.5,
                "reaction": r.choice(SM.REACTIONS) if r.random() < 0.3 else "none", "chat_addressed": r.random() < 0.3}
    rows = simulate(600, jittery, seed=1)
    changes = [t for (t, o), (_, p) in zip(rows[1:], rows[:-1]) if o["state"] != p["state"]]
    assert changes, "states never changed"
    gaps = [b - a for a, b in zip(changes, changes[1:])]
    assert min(gaps) >= D["state_min_dwell_s"] - 1e-9
    assert D["state_min_dwell_s"] >= 0.6                  # clears the native debounce


def test_state_follows_the_situation():
    md = SM.MotionDirector(random.Random(2))
    assert md.tick(0.0, action="none")["state"] == "idle"
    assert md.tick(1.0, action="read")["state"] == "reading"
    assert md.tick(2.0, action="scroll")["state"] == "mouse"
    assert md.tick(2.5, action="read")["state"] == "mouse"           # the 0.8 s mouse hold outlasts the single scroll tick
    assert md.tick(3.0, action="read")["state"] == "reading"         # ... and is over by now: no 2 s freeze
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
    assert o["motion"]["lean"] == 0 and o["motion"]["lean_back"] == 0 and o["motion"]["posture"] == "neutral"


# ---- head: camera and chat -------------------------------------------------------------------------------------------
def test_camera_looks_are_event_driven_never_on_a_timer():
    talking = simulate(20 * 60, TALKING, seed=21)                     # twenty minutes of page comments
    assert fraction(talking, CAM) == 0                                # a dry page comment stays on the content
    assert fraction(simulate(10 * 60, READING, seed=4), CAM) == 0
    assert fraction(simulate(10 * 60, IDLE, seed=4), CAM) == 0
    assert fraction(simulate(10 * 60, lambda t: {"action": "type"}, seed=4), CAM) == 0


def test_chat_answer_reads_the_message_then_addresses_the_lens_once_then_rechecks():
    rows = simulate(10 * 40, answers(40.0, 10.0), seed=4)             # ten answers of 10 s
    cams = [(t, o) for t, o in rows if CAM(o)]
    n, runs = onsets(rows, CAM)
    assert n == 10, n                                                 # exactly one lens address per answer
    assert min(runs) >= D["chat_camera_s"][0] - DT and max(runs) <= D["chat_camera_s"][1] + 2 * DT
    for k in range(10):
        t0 = 1000.0 + k * 40.0
        first_cam = next(t for t, o in cams if t >= t0)
        assert D["chat_read_first_s"][0] - DT <= first_cam - t0 <= D["chat_read_first_s"][1] + DT
        first = next(o for t, o in rows if t >= t0)
        assert first["motion"]["look_to_chat"] == 1.0 and first["motion"]["look_at_camera"] == 0.0
        # a longer answer gets one recheck of the message at 5.5-8 s after speech start
        rechecks = [t for t, o in rows if t0 + 3 <= t < t0 + 10 and CHAT_LOOK(o)]
        assert rechecks and D["chat_mid_glance_at_s"][0] - DT <= rechecks[0] - t0 <= D["chat_mid_glance_at_s"][1] + DT
        assert rechecks[-1] - rechecks[0] <= D["chat_mid_glance_s"][1] + DT
    up = [o["gaze_pitch_deg"] for _, o in cams]
    assert sum(up) / len(up) > 2.5                                    # the head rises towards the lens above the monitor
    assert fraction(rows, CAM) < 0.12                                 # no camera quota: most of the answer is to the content


def test_chat_answer_posture_is_reading_forward_then_talking_back():
    md = SM.MotionDirector(random.Random(8))
    for k in range(40):
        md.tick(k * 0.25, action="read")
    before = md.tick(10.0, action="read")["motion"]
    assert before["lean"] >= 0.29 and before["lean_back"] == 0        # reading: 0.30 forward
    rows = [(10.25 + k * 0.25, md.tick(10.25 + k * 0.25, action="none", speaking=True, chat_addressed=True)) for k in range(32)]
    t_cam = next(t for t, o in rows if CAM(o))
    assert any(o["motion"]["look_to_chat"] for t, o in rows if t < t_cam)   # read beat first
    assert all(o["motion"]["lean"] <= 0.31 for _, o in rows)          # never a forward presenter lunge
    assert max(o["motion"]["lean_back"] for t, o in rows if t <= t_cam + 1.5) >= D["chat_talk_back_amount"] - 0.01
    assert all(o["nod_strength"] <= D["chat_ack_nod"] + 1e-6 for _, o in rows)
    assert max(o["nod_strength"] for _, o in rows) >= D["chat_ack_nod"] - 1e-6   # one acknowledgement nod
    after = [md.tick(18.25 + k * 0.25, action="read") for k in range(16)]
    assert after[-1]["motion"]["lean_back"] == 0 and after[-1]["motion"]["lean"] >= 0.25   # back to the reading posture


def test_chat_answer_with_the_voice_arriving_late_reads_then_waits_then_addresses_the_lens():
    md = SM.MotionDirector(random.Random(9))
    for k in range(40):
        md.tick(k * 0.25, action="read")
    pre = [(10 + k * 0.25, md.tick(10 + k * 0.25, action="read", chat_addressed=True)) for k in range(16)]   # 4 s before the voice
    assert pre[0][1]["motion"]["look_to_chat"] == 1.0
    assert all(not CAM(o) for _, o in pre)                            # no lens address without a voice
    assert pre[-1][1]["motion"]["lean"] == pytest.approx(D["chat_read_lean"], abs=0.02)
    talk = [(14 + k * 0.25, md.tick(14 + k * 0.25, action="read", speaking=True, chat_addressed=True)) for k in range(16)]
    assert CAM(talk[0][1]) or CAM(talk[1][1])                         # the voice starts: straight to the lens
    hold = [t for t, o in talk if CAM(o)]
    assert D["chat_camera_s"][0] - DT <= hold[-1] - hold[0] + DT <= D["chat_camera_s"][1] + DT


def test_chunked_speech_within_one_answer_does_not_repeat_the_read_camera_cycle():
    def inputs(t):
        k = t - 1000.0
        if 0 <= k < 5 or 5.5 <= k < 10:                                # two chunks, a 0.5 s gap between them
            return {"action": "none", "speaking": True, "chat_addressed": True}
        return {"action": "read"}
    rows = simulate(30, inputs, seed=3)
    n, _ = onsets(rows, CAM)
    assert n == 1


def test_chat_glances_while_reading_every_45_to_105_s():
    rows = simulate(30 * 60, READING, seed=12)
    n, runs = onsets(rows, CHAT_LOOK)
    assert 12 <= n <= 42, n                               # 1800/105 .. 1800/45 with jitter and deferrals
    assert runs and min(runs) >= D["chat_glance_s"][0] - DT and max(runs) <= D["chat_glance_s"][1] + DT
    turned = [o["gaze_yaw_deg"] for _, o in rows if CHAT_LOOK(o)]
    assert sum(turned) / len(turned) > 12.0               # the head turns to the chat side (right by default), 20 deg anchor
    # never within 8 s of a page change, never during the scroll hold
    for (t, o), (_, p) in zip(rows[1:], rows[:-1]):
        if CHAT_LOOK(o) and not CHAT_LOOK(p):
            assert (t - 1000.0) % 20.0 >= D["mouse_hold_s"]


def test_no_chat_glance_while_typing_or_talking():
    rows = simulate(10 * 60, lambda t: {"action": "type"}, seed=3)
    assert all(o["motion"]["look_to_chat"] == 0 for _, o in rows)
    assert all(o["motion"]["look_at_camera"] == 0 for _, o in rows)
    rows = simulate(10 * 60, TALKING, seed=3)
    assert all(o["motion"]["look_to_chat"] == 0 for _, o in rows)


def test_waiting_for_a_page_earns_one_short_glance_after_three_seconds():
    md = SM.MotionDirector(random.Random(31))
    for k in range(40):
        md.tick(k * 0.25, action="read")
    md.tick(10.0, action="click", screen_target=(0.5, 0.5))
    rows = [(10.25 + k * 0.25, md.tick(10.25 + k * 0.25, action="none")) for k in range(48)]   # 12 s of waiting
    glances = [t for t, o in rows if CHAT_LOOK(o)]
    assert glances and glances[0] - 10.0 >= D["wait_glance_at_s"] and glances[0] - 10.0 <= D["wait_glance_at_s"] + 2.5
    n, runs = onsets(rows, CHAT_LOOK)
    assert n == 1 and D["wait_glance_s"][0] - DT <= runs[0] <= D["wait_glance_s"][1] + DT
    assert all(not CAM(o) for _, o in rows)
    assert rows[-1][1]["motion"]["lean"] == pytest.approx(D["lean_by_state"]["idle"], abs=0.02)   # the lean released


# ---- head: reading stillness and targets ------------------------------------------------------------------------------
def test_reading_head_is_nearly_still():
    rows = simulate(10 * 60, lambda t: {"action": "read"}, seed=27)
    last_glance = -1e9
    quiet = []
    for t, o in rows:                                     # outside the chat glances and their 0.75 s fast return
        if CHAT_LOOK(o):
            last_glance = t
        elif t - last_glance > 0.75:
            quiet.append((t, o))
    yaw_cap = D["reading_gaze_max_yaw_deg"] + D["reading_head_wander_deg"] + 0.1
    pitch_cap = D["reading_gaze_max_pitch_deg"] + D["reading_head_wander_deg"] * 0.6 + 0.1
    assert all(abs(o["gaze_yaw_deg"]) <= yaw_cap and abs(o["gaze_pitch_deg"]) <= pitch_cap for _, o in quiet)
    speeds = [abs(b["gaze_yaw_deg"] - a["gaze_yaw_deg"]) / DT for (ta, a), (tb, b) in zip(quiet, quiet[1:]) if tb - ta < DT + 1e-6]
    assert speeds and max(speeds) <= 4.0                   # no reading bob: under 4 deg/s


def test_screen_target_gives_a_partial_head_turn_then_releases():
    md = SM.MotionDirector(random.Random(25))
    for k in range(8):
        md.tick(k * 0.25, action="read")
    rows = [(2 + k * 0.25, md.tick(2 + k * 0.25, action="click", screen_target=(0.95, 0.9))) for k in range(16)]
    early = [o for t, o in rows if t - 2 <= 1.0]
    assert max(o["gaze_yaw_deg"] for o in early) >= 5.0 and min(o["gaze_pitch_deg"] for o in early) <= -2.5
    assert max(o["gaze_yaw_deg"] for _, o in rows) <= 18 * D["action_gaze_gain"] + 1.0    # partial, gain 0.45
    assert abs(rows[-1][1]["gaze_yaw_deg"]) < 4.0                     # the 0.7-1.2 s hold is over: back to the reading filter
    rows = [md.tick(6 + k * 0.25, action="click", screen_target=(0.05, 0.1)) for k in range(5)]
    assert min(o["gaze_yaw_deg"] for o in rows) <= -5.0 and max(o["gaze_pitch_deg"] for o in rows) >= 2.5


def test_scroll_target_holds_shorter_than_a_click_target():
    def hold_of(action):
        md = SM.MotionDirector(random.Random(26))
        for k in range(8):
            md.tick(k * 0.25, action="read")
        rows = [(2 + k * 0.25, md.tick(2 + k * 0.25, action=action, screen_target=(0.95, 0.5))) for k in range(16)]
        return sum(1 for _, o in rows if o["gaze_yaw_deg"] > 4.0) * DT
    assert hold_of("scroll") < hold_of("click")


# ---- hands --------------------------------------------------------------------------------------------------------------
def test_hands_reach_the_keyboard_before_typing_starts_and_linger_after():
    md = SM.MotionDirector(random.Random(5))
    for k in range(40):
        md.tick(k * 0.1, action="read")
    o = md.tick(4.0, action="type")
    assert o["motion"]["hand_left"] == "keyboard" and o["motion"]["hand_right"] == "keyboard"
    assert o["state"] != "typing"                         # the clip follows the hands, not the other way round
    assert md.tick(4.25, action="type")["state"] != "typing"
    assert md.tick(4.4, action="type")["state"] != "typing"
    o3 = md.tick(4.5, action="type")
    assert o3["state"] == "typing"                        # hands_lead_s 0.5 passed (and the 0.8 s dwell)
    # the action ended: hands linger 0.7 s, then back to the mouse
    o4 = md.tick(5.0, action="none")
    assert o4["motion"]["hand_right"] == "keyboard"
    o5 = md.tick(5.3, action="none")
    assert o5["motion"]["hand_right"] == "mouse" and o5["motion"]["hand_left"] == "rest"


def test_typing_that_resumes_within_the_pause_hold_skips_the_reach():
    md = SM.MotionDirector(random.Random(5))
    for k in range(12):
        md.tick(k * 0.25, action="type")                  # typing since 0.0, state typing since 0.5
    assert md.tick(3.0, action="type")["state"] == "typing"
    o = md.tick(3.75, action="none")                      # 0.75 s pause: hands left (linger 0.7), sitting loop
    assert o["motion"]["hand_right"] == "mouse" and o["state"] == "idle"
    o = md.tick(4.6, action="type")                       # resumes 1.6 s after the last key: the same episode
    assert o["motion"]["hand_left"] == "keyboard" and o["state"] == "typing"   # no new 0.5 s lead: typing at once
    for k in range(8):
        md.tick(4.75 + k * 0.25, action="type")
    for k in range(8):
        md.tick(6.75 + k * 0.25, action="none")
    o = md.tick(8.6, action="type")                       # 2.1 s pause: a new reach with its lead
    assert o["motion"]["hand_left"] == "keyboard" and o["state"] != "typing"
    assert md.tick(9.0, action="type")["state"] != "typing"
    assert md.tick(9.25, action="type")["state"] == "typing"


def test_hands_consistent_with_the_action_over_minutes():
    typing = simulate(5 * 60, lambda t: {"action": "type"}, seed=6)
    assert all(o["motion"]["hand_left"] == "keyboard" and o["motion"]["hand_right"] == "keyboard" for _, o in typing[4:])
    assert all(o["motion"]["fidget"] == "none" for _, o in typing)
    pointing = simulate(5 * 60, lambda t: {"action": "scroll" if int(t * 4) % 8 == 0 else "click"}, seed=6)
    assert all(o["motion"]["hand_right"] == "mouse" for _, o in pointing)
    assert all(o["motion"]["hand_left"] != "keyboard" for _, o in pointing)
    reading = simulate(10 * 60, READING, seed=6)
    assert fraction(reading, lambda o: o["motion"]["hand_right"] == "mouse") >= 0.85   # the mouse hand stays while reading
    assert all(o["motion"]["hand_left"] == "rest" for _, o in reading)                # the free hand keeps its desk contact


def test_mouse_hand_drifts_to_rest_after_two_minutes_without_pointer_use():
    rows = simulate(4 * 60, lambda t: {"action": "read"}, seed=7)   # no pointer action at all
    early = [o for t, o in rows if t - rows[0][0] < 100]
    late = [o for t, o in rows if t - rows[0][0] > 125]
    assert all(o["motion"]["hand_right"] == "mouse" for o in early)
    assert all(o["motion"]["hand_right"] == "rest" for o in late)


def test_fidgets_are_desk_only_every_120_to_260_s_and_keep_the_contact():
    rows = simulate(30 * 60, IDLE, seed=13)
    n, runs = onsets(rows, lambda o: o["motion"]["fidget"] != "none")
    assert 5 <= n <= 17, n                                # 1800/260 .. 1800/120 with jitter, plus the one bored fidget
    assert runs and min(runs) >= D["fidget_s"]["desk"][0] - DT and max(runs) <= D["fidget_s"]["desk"][1] + DT
    assert {o["motion"]["fidget"] for _, o in rows} == {"none", "desk"}
    for _, o in rows:
        m = o["motion"]
        if m["fidget"] == "desk":
            assert m["hand_left"] == "rest" and m["hand_right"] in ("mouse", "rest") and m["gesture_strength"] > 0
    first = next(t for t, o in rows if o["motion"]["fidget"] != "none")
    assert first - rows[0][0] >= D["fidget_min_state_s"]
    talking = simulate(60 * 60, TALKING, seed=14)
    assert all(o["motion"]["fidget"] in ("none", "desk") for _, o in talking)


def test_no_autonomous_stretch_or_face_fidget():
    r = random.Random(28)
    rows = simulate(60 * 60, lambda t: {"action": r.choice(["read", "none", "none", "scroll"]), "speaking": r.random() < 0.2}, seed=28)
    assert all(o["motion"]["fidget"] in ("none", "desk") for _, o in rows)
    assert all(o["motion"]["posture"] != "stretch" for _, o in rows)


def test_gestures_while_answering_chat_more_than_while_commenting_and_small():
    chat = simulate(10 * 60, CHAT, seed=15)
    talk = simulate(10 * 60, TALKING, seed=15)
    g = lambda o: o["motion"]["gesture_strength"] > 0 and o["motion"]["fidget"] == "none"
    n_chat, runs_chat = onsets(chat, g)
    n_talk, runs_talk = onsets(talk, g)
    assert 30 <= n_chat <= 75, n_chat                     # every 8-14 s plus the gesture itself
    assert 15 <= n_talk <= 45, n_talk                     # every 14-26 s
    assert n_chat > n_talk
    for runs in (runs_chat, runs_talk):
        assert min(runs) >= D["gesture_s"][0] - DT and max(runs) <= D["gesture_s"][1] + DT
    amps = [o["motion"]["gesture_strength"] for _, o in chat + talk if g(o)]
    assert D["gesture_strength"][0] <= min(amps) and max(amps) <= D["gesture_strength"][1]
    assert any(o["motion"]["hand_right"] == "gesture" for _, o in chat)    # the mouse hand may leave the mouse for chat
    assert fraction(chat, lambda o: o["motion"]["hand_right"] == "gesture") < 0.03   # ... rarely (15%)
    assert all(o["motion"]["hand_right"] != "gesture" for _, o in talk)    # never for a page comment
    # the first gesture of a comment never fires with the voice
    md = SM.MotionDirector(random.Random(16))
    for k in range(8):
        md.tick(k * 0.25, action="read")
    first = [md.tick(2 + k * 0.25, action="read", speaking=True) for k in range(2)]
    assert all(o["motion"]["gesture_strength"] == 0 for o in first)


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


def test_laugh_is_a_small_chuckle_shared_once_then_recovered():
    rows = react_rows("laugh")
    assert rows[0][1]["state"] == "reacting" and rows[0][1]["nod_strength"] >= 0.25
    peak_t, peak = max(rows, key=lambda r: r[1]["motion"]["lean_back"])
    assert D["laugh_back_amount"] - 0.02 <= peak["motion"]["lean_back"] <= D["laugh_back_amount"] and peak_t <= 0.5
    tilt = max(abs(o["motion"]["head_tilt_deg"]) for _, o in rows)
    assert 3.5 <= tilt <= D["laugh_tilt_deg"][1]
    cam = [t for t, o in rows if CAM(o)]
    assert cam and D["laugh_camera_at_s"] - DT <= cam[0] <= D["laugh_camera_at_s"] + DT
    assert cam[-1] - cam[0] + DT <= D["laugh_camera_s"] + DT
    assert all(o["motion"]["hand_left"] == "rest" and o["motion"]["hand_right"] == "mouse" for _, o in rows)   # hands keep contact
    done = next(t for t, o in rows if t > 1.5 and o["motion"]["lean_back"] == 0 and abs(o["motion"]["head_tilt_deg"]) < 0.5)
    assert done <= D["laugh_s"][1] + 0.5                              # recovered within the laugh window
    assert rows[-1][1]["state"] == "reading" and rows[-1][1]["motion"]["lean"] >= 0.25
    assert max(o["motion"]["breathing_rate_hz"] for _, o in rows) > 0.3


def test_surprise_back_then_check_then_share_then_recover():
    rows = react_rows("surprise")
    early = [o["motion"]["lean_back"] for t, o in rows if t < D["surprise_check_at_s"]]
    assert max(early) >= D["surprise_back_amount"] - 0.02 and max(early) <= D["surprise_back_amount"]
    check = [o["motion"]["lean"] for t, o in rows if D["surprise_camera_at_s"] <= t <= 1.9]
    assert min(check) >= D["surprise_check_lean"] - 0.02
    cam = [t for t, o in rows if CAM(o)]
    assert cam and D["surprise_camera_at_s"] - DT <= cam[0] <= D["surprise_camera_at_s"] + DT
    assert cam[-1] - cam[0] + DT <= D["surprise_camera_s"] + DT
    assert all(o["intensity"] >= 0.6 for t, o in rows if t < 1.5)
    assert all(o["nod_strength"] == 0 for t, o in rows if t < 2.6)   # no surprise nod
    assert next(o["state"] for t, o in rows if t >= D["surprise_s"] + DT) == "reading"
    assert rows[-1][1]["motion"]["lean"] == pytest.approx(0.3, abs=0.06) and rows[-1][1]["motion"]["lean_back"] == 0


def test_think_tilts_the_head_and_looks_off_screen_without_a_chin_hand():
    rows = react_rows("think", seed=17)
    tilt = max(abs(o["motion"]["head_tilt_deg"]) for _, o in rows)
    assert 3.5 <= tilt <= D["think_tilt_deg"][1]
    off = [abs(o["gaze_yaw_deg"]) for t, o in rows if 0.75 <= t <= 1.4]
    assert max(off) >= 4.0
    assert all(o["motion"]["look_at_camera"] == 0 for _, o in rows)
    assert all(o["motion"]["hand_left"] == "rest" and o["motion"]["gesture_strength"] == 0 for _, o in rows)
    reacting = [t for t, o in rows if o["state"] == "reacting"]
    assert D["think_s"][0] - DT <= reacting[-1] - reacting[0] + DT <= D["think_s"][1] + 2 * DT


def test_lean_and_lean_back_move_smoothly():
    r = random.Random(18)
    rows = simulate(300, lambda t: {"action": r.choice(SM.ACTIONS), "speaking": r.random() < 0.5,
                                    "chat_addressed": r.random() < 0.3}, seed=18)
    step = 0.3 / D["lean_rise_s"] * DT + D["weight_shift_amount"] / D["weight_shift_s"] * DT + 2e-3
    for (_, a), (_, b) in zip(rows, rows[1:]):            # no reactions: the posture rate per 0.30
        assert abs(b["motion"]["lean"] - a["motion"]["lean"]) <= step
        assert abs(b["motion"]["lean_back"] - a["motion"]["lean_back"]) <= step
        assert abs(b["gaze_yaw_deg"] - a["gaze_yaw_deg"]) <= 26.0   # eased: under two thirds of the range per tick
    r = random.Random(19)
    rows = simulate(300, lambda t: {"action": r.choice(SM.ACTIONS), "speaking": r.random() < 0.5,
                                    "reaction": r.choice(SM.REACTIONS) if r.random() < 0.05 else "none"}, seed=19)
    fast = max(D["surprise_back_amount"] / D["surprise_back_rise_s"], D["laugh_back_amount"] / D["laugh_back_rise_s"]) * DT + 0.02
    for (_, a), (_, b) in zip(rows, rows[1:]):            # reactions: their own onset rate, still continuous
        assert abs(b["motion"]["lean"] + b["motion"]["lean_back"] - a["motion"]["lean"] - a["motion"]["lean_back"]) <= fast + 0.5


def test_posture_shifts_every_240_to_420_s_and_long_focus_sags_gradually():
    rows = simulate(60 * 60, lambda t: {"action": "read", "seconds_in_state": 60.0}, seed=19)
    n, runs = onsets(rows, lambda o: o["motion"]["posture"] == "back")
    assert 6 <= n <= 16, n                                # 3600/420 .. 3600/240 with the 15-35 s holds
    assert runs and min(runs) >= D["posture_back_s"][0] - DT and max(runs) <= D["posture_back_s"][1] + DT
    backs = [o["motion"]["lean_back"] for _, o in rows if o["motion"]["posture"] == "back"]
    assert max(backs) <= D["posture_back_amount"] + D["weight_shift_amount"] + 1e-3
    fresh = simulate(120, lambda t: {"action": "read", "seconds_in_state": 60.0}, seed=20)
    half = simulate(120, lambda t: {"action": "read", "seconds_in_state": 810.0}, seed=20)     # half way up the ramp
    stale = simulate(120, lambda t: {"action": "read", "seconds_in_state": 1500.0}, seed=20)
    lean = lambda rows: rows[-1][1]["motion"]["lean"]
    assert lean(stale) < lean(half) < lean(fresh)
    assert lean(fresh) - lean(stale) == pytest.approx(D["slump_back_amount"], abs=0.06)
    assert any(o["motion"]["posture"] == "slump" for _, o in stale)
    assert all(o["motion"]["posture"] != "slump" for _, o in fresh)
    assert stale[-1][1]["gaze_pitch_deg"] < fresh[-1][1]["gaze_pitch_deg"]      # the head drops a degree


def test_weight_shifts_are_subliminal():
    rows = simulate(20 * 60, lambda t: {"action": "read", "seconds_in_state": 60.0}, seed=29)
    upright, since_back = [], -1e9
    for t, o in rows:                                     # settled reading: not within 3 s of a chair shift or the start
        if o["motion"]["posture"] != "upright":
            since_back = t
        elif t - since_back > 3.0 and t - rows[0][0] > 3.0:
            upright.append(o["motion"]["lean"])
    assert max(upright) - min(upright) <= 2 * D["weight_shift_amount"] + 0.02
    assert max(upright) - min(upright) >= D["weight_shift_amount"]     # ... but present


def test_boredom_after_75_s_idle_releases_the_posture_once_and_any_action_cancels_it():
    rows = simulate(130, IDLE, seed=30)
    bored = [(t, o) for t, o in rows if o["motion"]["lean_back"] >= D["bored_back_amount"] - 0.03]
    assert bored and bored[0][0] - 1000.0 >= D["bored_after_s"] and bored[0][0] - 1000.0 <= D["bored_after_s"] + 3.0
    hold = bored[-1][0] - bored[0][0]
    assert D["bored_hold_s"][0] - 2.0 <= hold <= D["bored_hold_s"][1] + 1.0
    assert all(not CAM(o) for _, o in rows)
    assert any(o["motion"]["fidget"] == "desk" for t, o in bored)      # one desk fidget once settled
    drift = [abs(o["gaze_yaw_deg"]) for t, o in bored if not CHAT_LOOK(o)
             and not any(CHAT_LOOK(p) for u, p in rows if t - 0.75 <= u < t)]
    assert drift and max(drift) <= D["bored_gaze_yaw_deg"] + 1.0      # a few degrees off the screen, a chat glance aside
    # a long idle gets the beat once (chair shifts switched off to isolate it)
    still = SM.MotionDirector(random.Random(30), defaults={"posture_shift_every_s": (1e6, 1e6)})
    long = simulate(10 * 60, IDLE, md=still)
    n, _ = onsets(long, lambda o: o["motion"]["lean_back"] >= D["bored_back_amount"] - 0.03)
    assert n == 1
    # a read cancels it at once and re-engages
    md = SM.MotionDirector(random.Random(30))
    rows = simulate(80, IDLE, md=md)
    assert rows[-1][1]["motion"]["lean_back"] > 0.1
    back = [md.tick(1080 + k * 0.25, action="read") for k in range(8)]
    assert back[-1]["motion"]["lean_back"] == 0 and back[-1]["motion"]["lean"] >= 0.25


def test_speech_onset_nod_only_no_periodic_talking_nods():
    md = SM.MotionDirector(random.Random(22))
    for k in range(8):
        md.tick(k * 0.25, action="read")
    rows = [(2 + k * 0.25, md.tick(2 + k * 0.25, action="read", speaking=True)) for k in range(5 * 60 * HZ)]
    assert rows[0][1]["nod_strength"] == 0                            # not on the exact toggle: 0.12 s later
    assert rows[1][1]["nod_strength"] == pytest.approx(D["speech_start_nod"], abs=1e-6)
    n, _ = onsets(rows, lambda o: o["nod_strength"] >= 0.05)
    assert n == 1                                                     # five minutes of speech: one onset nod, nothing periodic
    silent = simulate(5 * 60, READING, seed=22)
    n_silent, _ = onsets(silent, lambda o: o["nod_strength"] >= 0.05)
    assert n_silent == 0
    # a repeated nod of the same strength works once the previous one has decayed (rearm)
    md = SM.MotionDirector(random.Random(22))
    a = [md.tick(k * 0.25, action="read", speaking=0.5 <= k * 0.25 < 2.0 or 4.0 <= k * 0.25 < 6.0) for k in range(32)]
    n, _ = onsets([(0, o) for o in a], lambda o: o["nod_strength"] >= 0.05)
    assert n == 2


def test_breathing_slower_while_talking_than_at_rest():
    rest = simulate(120, IDLE, seed=23)[-1][1]["motion"]["breathing_rate_hz"]
    talk = simulate(120, TALKING, seed=23)[-1][1]["motion"]["breathing_rate_hz"]
    read = simulate(120, lambda t: {"action": "read"}, seed=23)[-1][1]["motion"]["breathing_rate_hz"]
    assert talk < read <= rest
    assert abs(rest - D["breath_rest_hz"]) < 0.01


def test_intensity_by_state_and_chat_bonus():
    md = SM.MotionDirector(random.Random(24))
    assert md.tick(0.0, action="none")["intensity"] == pytest.approx(0.1)
    assert md.tick(1.0, action="read")["intensity"] == pytest.approx(0.3)
    assert md.tick(2.0, action="read", speaking=True)["intensity"] == pytest.approx(0.6)
    assert md.tick(3.0, action="read", speaking=True, chat_addressed=True)["intensity"] == pytest.approx(0.7)
    assert md.tick(4.0, action="read", reaction="laugh")["intensity"] == pytest.approx(0.8)


def test_talking_releases_the_posture_back_and_returns_to_reading():
    md = SM.MotionDirector(random.Random(32))
    for k in range(40):
        md.tick(k * 0.25, action="read")
    talk = [md.tick(10 + k * 0.25, action="read", speaking=True) for k in range(24)]
    assert talk[-1]["motion"]["lean"] == 0 and talk[-1]["motion"]["lean_back"] == pytest.approx(D["talk_back_amount"], abs=0.06)
    assert all(not CAM(o) for o in talk)
    after = [md.tick(16 + k * 0.25, action="read") for k in range(12)]
    assert after[-1]["motion"]["lean_back"] == 0 and after[-1]["motion"]["lean"] >= 0.25
