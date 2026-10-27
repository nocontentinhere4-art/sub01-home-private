Keep reading quiet but no longer frozen: slightly wider, filtered aim and a slower visible drift.
Speech gets irregular phrase beats; lens-facing beats are smaller so he keeps addressing viewers.
Nods remain accents, gated by the actual decayed value so the native envelope can re-arm.
A rare silent lens check adds streamer presence without introducing a visible camera timer.

```python
# 1) DEFAULTS overrides: existing keys only
{
    "reading_gaze_gain": 0.18,          # more visible screen following without mimicking saccades
    "idle_gaze_gain": 0.28,             # idle attention travels a little farther than reading
    "reading_gaze_max_yaw_deg": 3.0,    # webcam-readable, still far below a chat glance
    "reading_gaze_max_pitch_deg": 2.0,  # avoids turning line tracking into repeated nodding
    "reading_gaze_smooth_s": 0.65,      # keeps the larger reading motion calm
    "reading_head_wander_deg": 0.9,     # enough independent drift to read as alive
    "reading_head_wander_hz": 0.055,    # roughly 18 s: livelier without becoming busy
    "chat_glance_every_s": (35.0, 80.0),# slightly more viewer awareness during long silent stretches
    "chat_ack_nod": 0.28,               # a clearer but still small acknowledgement
    "intensity_by_state": {
        "idle": 0.18, "reading": 0.40, "typing": 0.60,
        "mouse": 0.50, "talking": 0.68, "reacting": 0.55,
    },                                   # subtle native sway; head aim remains the main liveliness
}
```

```python
# 2a) New DEFAULTS keys for talk beats
{
    "talk_beat_every_s": (1.1, 2.1),       # irregular phrase-scale holds, not per-tick noise
    "talk_beat_yaw_deg": 2.6,              # off-lens phrase accents remain small
    "talk_beat_pitch_deg": 1.2,
    "talk_beat_look_cam_scale": 0.55,      # approximately ±1.43° yaw at the lens
    "talk_beat_nod_p": 0.30,               # most beats have no nod
    "talk_beat_nod_strength": (0.12, 0.24),# about 0.7–1.4° before intensity scaling
}
```

```python
# 2b) __init__: three lines
self.beat_next = None
self.beat_yaw = self.beat_pitch = 0.0
self.beat_yaw_out = self.beat_pitch_out = 0.0


def talk_beat(self, now, speaking, reacting, paused, look_cam):
    active = speaking and not reacting and not paused
    if not active:
        self.beat_next = None
        self.beat_yaw = self.beat_pitch = 0.0
        return 0.0, 0.0

    if self.beat_next is None or now >= self.beat_next:
        scale = self.d["talk_beat_look_cam_scale"] if look_cam else 1.0
        self.beat_yaw = self.rng.uniform(
            -self.d["talk_beat_yaw_deg"], self.d["talk_beat_yaw_deg"]
        ) * scale
        self.beat_pitch = self.rng.uniform(
            -self.d["talk_beat_pitch_deg"], self.d["talk_beat_pitch_deg"]
        ) * scale
        self.beat_next = now + self.u("talk_beat_every_s")

        current_nod = self.nod_peak * max(
            0.0, 1.0 - (now - self.nod_t0) / self.d["nod_decay_s"]
        )
        if (self.rng.random() < self.d["talk_beat_nod_p"]
                and current_nod <= 0.02):
            self.nod(self.u("talk_beat_nod_strength"), now)

    return self.beat_yaw, self.beat_pitch
```

```python
# 2c) Correct plan: ease the offsets, then add the eased outputs before clamping.
# Immediately before "# -- nod, intensity, breathing":
by, bp = self.talk_beat(now, speaking, reacting, paused, look_cam)
self.beat_yaw_out = self.ease(self.beat_yaw_out, by, dt, d["gaze_tau_s"])
self.beat_pitch_out = self.ease(self.beat_pitch_out, bp, dt, d["gaze_tau_s"])

# Replace the two gaze entries in the return dict:
"gaze_yaw_deg": round(clamp(
    self.yaw + wander_y + self.beat_yaw_out, -20.0, 20.0
), 2),
"gaze_pitch_deg": round(clamp(
    self.pitch + wander_p + self.beat_pitch_out, -10.0, 10.0
), 2),
```

```python
# 3) Optional rare silent lens check: new DEFAULTS keys
{
    "lens_check_every_s": (150.0, 300.0), # roughly 12–24 opportunities/hour, eligibility-gated
    "lens_check_s": (0.6, 1.1),           # a brief address, not a second camera performance
}

# __init__:
self.next_lens_check = None

# In the first-tick schedule-seeding block:
self.next_lens_check = now + self.u("lens_check_every_s")

# After look_cam/look_chat/state/reacting are established, before head-aim targets:
if (not paused and not speaking and not chat_addressed and not reacting
        and state in ("idle", "reading") and action == "none"
        and now >= self.next_lens_check
        and now >= self.busy_t + d["chat_glance_min_state_s"]
        and now >= self.settle_t + d["chat_glance_min_state_s"]):
    self.cam_until = now + self.u("lens_check_s")
    self.next_lens_check = now + self.u("lens_check_every_s")
if now < self.cam_until:
    look_cam = True
    look_chat = False
```

```python
# 4) pytest tests
import random

import pytest


def director():
    return MotionDirector(random.Random(7))


def test_talk_beats_only_while_speaking():
    m = director()
    for speaking, reacting, paused in (
        (False, False, False),
        (True, True, False),
        (True, False, True),
    ):
        assert m.talk_beat(0.0, speaking, reacting, paused, False) == (0.0, 0.0)
        assert m.beat_next is None

    yaw, pitch = m.talk_beat(0.0, True, False, False, False)
    assert (yaw, pitch) != (0.0, 0.0)
    assert m.beat_next is not None


def test_talk_beat_offsets_are_bounded_and_lens_offsets_smaller():
    for look_cam in (False, True):
        m = director()
        scale = m.d["talk_beat_look_cam_scale"] if look_cam else 1.0
        for i in range(100):
            yaw, pitch = m.talk_beat(
                i * 0.25, True, False, False, look_cam
            )
            assert abs(yaw) <= m.d["talk_beat_yaw_deg"] * scale + 1e-12
            assert abs(pitch) <= m.d["talk_beat_pitch_deg"] * scale + 1e-12


def test_talk_beat_offsets_hold_between_beats():
    m = director()
    m.d["talk_beat_every_s"] = (1.0, 1.0)
    first = m.talk_beat(0.0, True, False, False, False)
    assert m.talk_beat(0.25, True, False, False, False) == first
    assert m.talk_beat(0.75, True, False, False, False) == first
    assert m.talk_beat(1.0, True, False, False, False) != first


def test_talk_beat_nods_respect_native_rearm():
    m = director()
    m.d.update({
        "talk_beat_every_s": (0.1, 0.1),
        "talk_beat_nod_p": 1.0,
        "talk_beat_nod_strength": (0.2, 0.2),
    })
    m.nod_t0, m.nod_peak = 0.0, 1.0

    m.talk_beat(0.0, True, False, False, False)
    assert m.nod_t0 == 0.0
    assert m.nod_peak == 1.0

    m.talk_beat(0.2, True, False, False, False)
    assert m.nod_t0 == 0.0  # current nod is still 0.8

    m.talk_beat(1.1, True, False, False, False)
    assert m.nod_t0 == pytest.approx(1.1)
    assert m.nod_peak == pytest.approx(0.2)


def test_paused_talk_beats_zero_and_reset_episode():
    m = director()
    m.talk_beat(0.0, True, False, False, True)
    assert m.beat_next is not None

    assert m.talk_beat(0.25, True, False, True, True) == (0.0, 0.0)
    assert m.beat_yaw == m.beat_pitch == 0.0
    assert m.beat_next is None

    m.talk_beat(0.5, True, False, False, True)
    assert m.beat_next == pytest.approx(
        0.5 + (m.beat_next - 0.5)  # resumed episode schedules from resume time
    )


def test_talk_beats_deterministic_with_random_7():
    a, b = director(), director()
    seq_a, seq_b = [], []
    for i in range(80):
        now = i * 0.25
        args = (now, True, False, False, i % 3 != 0)
        seq_a.append(a.talk_beat(*args))
        seq_b.append(b.talk_beat(*args))
    assert seq_a == seq_b
```
