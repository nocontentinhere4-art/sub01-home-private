"""Motion direction for SUB-01 at his desk: the agent's situation -> motion parameters, every tick, no I/O.

    from scripts.streamer_motion import MotionDirector
    md = MotionDirector(random.Random(7))
    out = md.tick(now, action="scroll", speaking=False, chat_addressed=False, reaction="none", seconds_in_state=42.0)
    out -> {"state", "gaze_yaw_deg", "gaze_pitch_deg", "nod_strength", "intensity", "camera", "motion": {...}}

The first six keys are the native event v2 fields (tools/native_streamer_visual_v2/README.md); `motion` is the proposed
extension (docs/streamer/MOTION-SPEC.md) and is ignored by the current native parser. Pure standard library, no clock,
no files: `now` comes from the caller, every random draw comes from the `rng` given to the constructor, so two directors
with equal seeds and equal inputs produce byte-identical output. Behaviour and numbers follow
docs/streamer/ANIMATION-REFERENCES.md (study, section 4), DIRECTION.md (character, camera rule 10) and the decisions
taken from the Kimi animation consultation (docs/streamer/kimi/DECISIONS-ANIMATION-STREAM.md, 2026-10-23): the quiet
version. Reading is nearly still, speech releases the posture backwards, reactions are single small envelopes, camera
looks are event-driven (chat answer, shared reaction) and never on a timer, the hands keep their desk contacts.

Inputs per tick
  action          read | scroll | click | type | search | navigate | none   (the agent's current desktop action kind;
                  it may be given once on the tick it happens or on every tick while it lasts: both work)
  speaking        bool, his voice is playing now
  chat_addressed  bool, the current speech answers a chat message (set it when the batch is picked, a little before speech)
  reaction        none | surprise | laugh | think   (edge triggered: a kind must return to none before it fires again)
  seconds_in_state  seconds the agent has spent in its current focus/browse state (long focus -> gradual sag)
  screen_target   optional (nx, ny) in 0..1, where on the monitor the action points (streamer_agent.attention_of)
  paused          bool, kill switch or manual pause: neutral body, spectator camera

Outputs
  state           idle | reading | typing | mouse | talking | reacting   (at most one change per `state_min_dwell_s`)
  gaze_yaw_deg    -20..20 (right +)   gaze_pitch_deg  -10..10 (up +)     nod_strength 0..1 (decays over 1 s)
  intensity       0..1                camera          face | monitor | spectator
  motion.lean 0..1 towards the monitor (1 = 9 deg of torso pitch), motion.lean_back 0..1 (1 = 8 deg); the two are
  mutually exclusive (one signed posture channel), motion.head_tilt_deg -12..12 (right ear down +),
  motion.look_at_camera 0..1, motion.look_to_chat 0..1 (chat anchor: `chat_side` * 20 deg, 4 deg down),
  motion.hand_left / hand_right  rest | mouse | keyboard | gesture,  motion.gesture_strength 0..1,
  motion.breathing_rate_hz, motion.fidget (none|desk|...; only `desk` is emitted today), motion.posture label.
"""
from __future__ import annotations

import math

SCHEMA = "sub01.streamer-motion.v1"
STATES = ("idle", "reading", "typing", "mouse", "talking", "reacting")
ACTIONS = ("read", "scroll", "click", "type", "search", "navigate", "none")
REACTIONS = ("none", "surprise", "laugh", "think")
HANDS = ("rest", "mouse", "keyboard", "gesture")
FIDGETS = ("none", "desk", "face", "headphones", "neck", "drink", "stretch", "chair")   # only `desk` ships (Kimi 2.5)
CAMERAS = ("face", "monitor", "spectator")
POINTER = ("scroll", "click", "navigate")

# ---- defaults: one table. Ranges (lo, hi) are drawn uniformly from the rng once per behaviour episode, never per tick.
# Column "why" points at docs/streamer/ANIMATION-REFERENCES.md (A1..A24) and the Kimi decisions (K, DECISIONS-ANIMATION-
# STREAM.md). Posture: `lean` 1.0 = 9 deg forward torso pitch, `lean_back` 1.0 = 8 deg back; `lean_rise_s`/`lean_fall_s`
# are the time a 0.30 posture change takes (the reading lean), not a full-range slew.
DEFAULTS = {
    # timing hygiene
    "state_min_dwell_s": 0.8,            # no state flaps faster than this; clears the 0.6 s native debounce (K, A22)
    "mouse_hold_s": 0.8,                 # a scroll/click/navigate keeps the mouse state this long: persistence, not a freeze (K, A4)
    "read_hold_s": 6.0,                  # a "read" action keeps the reading state this long after the last tick it was given
    "hands_lead_s": 0.5,                 # hands reach the keyboard two ticks before the typing clip starts (K, A3)
    "hands_linger_s": 0.7,               # hands stay on the keyboard this long after the last typed tick (K, A3)
    "keyboard_pause_hold_s": 1.8,        # typing that resumes within this time is the same episode: no new reach, no lead (K)
    "mouse_hand_rest_after_s": 120.0,    # the mouse hand drifts to rest after two minutes without any pointer action (K, A5)
    # head aim: discrete targets and the reading filter (the head stands in for the eyes: no eye rig)
    "click_target_hold_s": (0.7, 1.2),   # a click/search/navigate target holds the head aim this long (K, A4)
    "scroll_target_hold_s": (0.35, 0.7), # a scroll briefly redirects attention, then the reading filter resumes (K, A2)
    "action_gaze_gain": 0.45,            # discrete targets give a visible but partial head turn (K)
    "reading_gaze_gain": 0.18,           # the head follows the lines a little: visible at webcam scale, still no saccades (K 10-27)
    "idle_gaze_gain": 0.28,              # idle attention wanders farther than reading (K 10-27)
    "reading_gaze_max_yaw_deg": 3.0,     # hard bound on screen-following yaw while reading, far below a chat glance (K 10-27)
    "reading_gaze_max_pitch_deg": 2.0,   # no vertical line tracking turning into a reading nod (K 10-27)
    "reading_gaze_smooth_s": 1.1,       # 4 Hz target changes filtered into calm head motion (K 10-27)
    "reading_head_wander_deg": 0.9,      # independent slow head drift: alive, not busy (K 10-27)
    "reading_head_wander_hz": 0.035,     # about an 18 s drift scale, two incommensurate sines, not a visible loop (K 10-27)
    "gaze_tau_s": 0.45,                  # voluntary head aims (lens, chat, click target, think) settle in ~0.22 s (K)
    "camera_pitch_deg": 4.2,             # head-to-lens pitch of the framing recipe: atan(0.07 / 0.95); native computes the real one (K)
    # chat and camera (event-driven: no camera timer, no camera quota; DIRECTION rule 10)
    "chat_glance_every_s": (35.0, 80.0),     # silent reading/idle: a glance at the chat, a little more viewer awareness (K 10-27)
    "chat_glance_min_state_s": 8.0,          # no glance within 8 s of speech, a reaction, typing or a page change (K)
    "chat_glance_s": (0.8, 1.5),             # dwell, excluding the native turn-in/out (K)
    "chat_yaw_deg": 20.0,                    # the chat anchor: 20 deg to his side (K, R15, R16)
    "chat_pitch_deg": -4.0,                  # ... and 4 deg below monitor centre (K)
    "chat_read_first_s": (1.2, 2.2),         # answering chat: one visible read beat at the chat anchor first (K, A11)
    "chat_ack_nod": 0.28,                    # the first look up to the lens carries one small, clear nod (K 10-27)
    "chat_camera_s": (1.4, 2.4),             # ... one initial lens address (K)
    "chat_mid_glance_at_s": (5.5, 8.0),      # a longer answer earns one recheck of the message at this point (K)
    "chat_mid_glance_s": (0.8, 1.2),
    "chat_continue_s": 2.5,                  # a chat edge this soon after the previous answer is the same answer (chunked speech)
    "camera_hold_after_speech_s": 0.35,      # no eye-line exit on the last audio sample (K)
    "wait_glance_at_s": 3.0,                 # waiting for a page longer than this earns one short chat glance (K rule 5)
    "wait_glance_s": (0.8, 1.2),
    "lens_check_every_s": (150.0, 300.0),    # silent idle/reading: a rare brief look at the viewers, eligibility-gated (K 10-27)
    "lens_check_s": (0.6, 1.1),
    # talk beats: phrase-scale head accents while speaking (K 10-27); owner 10-28 "si muove troppo velocemente": slower, smaller, rarer
    "talk_beat_every_s": (2.4, 4.2),         # irregular holds, not per-tick noise
    "talk_beat_yaw_deg": 2.2,                # off-lens accents (Kimi 2.6; owner: livelier)
    "talk_beat_pitch_deg": 1.0,              # (Kimi 1.2)
    "talk_beat_look_cam_scale": 0.55,        # smaller at the lens: he keeps addressing the viewers
    "talk_beat_nod_p": 0.2,                 # most beats carry no nod (Kimi 0.30)
    "talk_beat_nod_strength": (0.14, 0.28),  # about 0.8-1.7 deg before intensity scaling (Kimi 0.12-0.24)
    # nods (native: 0.75 s envelope, strength 1.0 = 6 deg down; rearm at <= 0.02)
    "nod_decay_s": 1.0,
    "speech_start_nod": 0.28,                # a small nod opens a non-chat utterance (K, A13)
    "speech_start_nod_delay_s": 0.12,        # not on the exact state toggle (K)
    "reaction_nod": {"surprise": 0.0, "laugh": 0.3, "think": 0.0},   # surprise has back/check/share, not a nod (K); laugh keeps a small entry cue for the current build
    # posture (one signed channel: + forward lean, - lean back; the agent emits mutually exclusive lean / lean_back)
    "lean_by_state": {"idle": 0.12, "reading": 0.30, "typing": 0.40, "mouse": 0.30, "talking": 0.0, "reacting": 0.30},
    "talk_back_amount": 0.12,                # a dry page comment releases the body about 1 deg back (K, A9 inverted)
    "chat_read_lean": 0.24,                  # reading a viewer's message relaxes the forward lean slightly (K)
    "chat_talk_back_amount": 0.18,           # answering: about 1.4 deg back; engagement is lens aim + nod, not a lunge (K)
    "lean_rise_s": 0.9,                     # a 0.30 posture change towards a pose takes this long (K)
    "lean_fall_s": 1.6,                     # ... and relaxing the same amount takes this long (K)
    "posture_shift_every_s": (240.0, 420.0), # a visible chair shift 9-15 times an hour (K, A7, R4)
    "posture_back_s": (15.0, 35.0),          # how long the leaned-back hold lasts (K)
    "posture_back_amount": 0.28,             # about 2.2 deg back: visible at webcam scale, not lounging (K)
    "weight_shift_every_s": (70.0, 140.0),   # tiny signed weight shifts between the holds (K, R4)
    "weight_shift_amount": 0.05,             # about half a degree; must stay below conscious notice (K)
    "weight_shift_s": 1.8,                   # executed slowly (K)
    "focus_slump_s": 720.0,                  # sag starts after 12 min of one focus (K, A18, R3)
    "focus_slump_ramp_s": 180.0,             # ... and ramps in over 3 min: a drift, not an event (K)
    "slump_back_amount": 0.12,               # small signed backward offset (K)
    "slump_pitch_deg": -1.0,                 # one degree of extra head drop (K)
    "bored_after_s": 75.0,                   # idle this long with nothing happening: bored, not a page load (K rule 9)
    "bored_back_amount": 0.22,
    "bored_rise_s": 1.2,
    "bored_hold_s": (12.0, 20.0),
    "bored_gaze_yaw_deg": 4.0,               # the head drifts a little off the screen, never to the camera (K rule 9)
    "bored_gaze_pitch_deg": 1.0,
    # reactions (native envelopes draw the sub-second shapes; these are the targets and the timeline)
    "surprise_s": 2.6,                       # back, forward check, camera share, recovery (K, A14)
    "surprise_back_amount": 0.40,
    "surprise_back_rise_s": 0.18,
    "surprise_check_at_s": 0.45,
    "surprise_check_lean": 0.45,
    "surprise_camera_at_s": 1.15,
    "surprise_camera_s": 0.75,
    "laugh_s": (2.2, 3.0),                   # a small chuckle: lean back + tilt, camera, recover (K, A15)
    "laugh_back_amount": 0.55,
    "laugh_back_rise_s": 0.25,
    "laugh_tilt_deg": (4.0, 6.0),
    "laugh_pitch_deg": 2.0,
    "laugh_camera_at_s": 0.75,
    "laugh_camera_s": 0.80,
    "think_s": (1.4, 2.4),                   # head tilt, head off the screen; no chin hand without an authored asset (K, A16)
    "think_tilt_deg": (4.0, 7.0),
    "think_gaze_yaw_deg": 7.0,
    "think_gaze_pitch_deg": 2.0,
    "think_chin_p": 0.0,
    "reaction_recover_s": 1.0,               # a reaction pose returns to the prior posture over about a second
    # hands (the free hand is the left; the right keeps mouse/desk contact unless a chat answer frees it)
    "gesture_after_speech_start_s": 0.45,    # hands never fire on the same frame as voice and head (K)
    "gesture_every_chat_s": (8.0, 14.0),     # about one free-hand beat per short answer (K, A8)
    "gesture_every_talk_s": (14.0, 26.0),    # most page comments get zero or one gesture (K, A8)
    "gesture_s": (0.9, 1.4),
    "gesture_strength": (0.25, 0.45),        # the lower part of the 25 deg forearm lift (K)
    "gesture_right_hand_p": 0.15,            # ... and never while a pointer action is in flight (K)
    "fidget_every_s": (120.0, 260.0),        # about 19 fidgets an hour instead of 48 (K, A19)
    "fidget_min_state_s": 25.0,              # a fresh page or state must not instantly produce a fidget (K)
    "fidget_weights": {"desk": 1.0, "face": 0.0, "headphones": 0.0, "neck": 0.0, "drink": 0.0, "stretch": 0.0},
    "fidget_s": {"desk": (1.0, 1.8), "face": (1.2, 2.5), "headphones": (1.0, 2.0), "neck": (1.5, 3.0), "drink": (3.0, 5.0),
                 "stretch": (3.0, 6.0), "chair": (1.5, 3.0)},
    "fidget_strength": 0.2,                  # amplitude of the desk/finger fidget; the wrist keeps contact
    "fidget_quiet_after_chat_s": 3.0,        # the beginning of an answer stays clean (K)
    # breathing (Hz; the native layer currently breathes at a fixed 0.22)
    "breath_rest_hz": 0.20,                  # twelve cycles a minute (K, A23)
    "breath_reading_hz": 0.20,
    "breath_talking_hz": 0.18,               # longer cycles while speaking (R5)
    "breath_surprise_hz": 0.28,
    "breath_laugh_hz": 0.34,                 # mostly in the recovery; the laugh beat itself is a native torso pulse (K)
    "breath_tau_s": 2.0,
    # intensity (native: scales sway and nod)
    "intensity_by_state": {"idle": 0.18, "reading": 0.4, "typing": 0.6, "mouse": 0.5, "talking": 0.68, "reacting": 0.55},   # K 10-27
    "intensity_by_reaction": {"surprise": 0.65, "laugh": 0.8, "think": 0.4},
    "intensity_chat_bonus": 0.1,
}


# "calm" profile (owner 2026-10-28: "si muove troppo veloce, deve essere 10 volte piu lento e naturale"): every voluntary
# move 3-5x slower, accents smaller, glances/nods/gestures/fidgets 2-3x rarer, fewer state flips. Picked by the agent from
# `<streamer-dir>/motion-profile` (one word) or STREAMER_MOTION_PROFILE; "default" = DEFAULTS.
CALM = {
    "state_min_dwell_s": 2.0,
    "reading_gaze_max_yaw_deg": 2.0, "reading_gaze_smooth_s": 4.0,
    "gaze_tau_s": 2.0,
    "chat_glance_every_s": (120.0, 240.0), "chat_glance_s": (2.0, 3.5),
    "lens_check_every_s": (400.0, 800.0), "lens_check_s": (1.5, 2.5),
    "talk_beat_every_s": (8.0, 14.0), "talk_beat_yaw_deg": 1.2, "talk_beat_pitch_deg": 0.6,
    "talk_beat_nod_p": 0.1, "talk_beat_nod_strength": (0.08, 0.16), "speech_start_nod": 0.14, "nod_decay_s": 2.5,
    "lean_rise_s": 4.0, "lean_fall_s": 6.0,
    "posture_shift_every_s": (480.0, 900.0), "weight_shift_every_s": (150.0, 300.0), "weight_shift_s": 6.0,
    "bored_rise_s": 4.0, "surprise_back_rise_s": 0.6, "laugh_back_rise_s": 0.8, "reaction_recover_s": 3.0,
    "gesture_every_chat_s": (16.0, 28.0), "gesture_every_talk_s": (30.0, 60.0), "gesture_s": (2.0, 3.0),
    "fidget_every_s": (300.0, 600.0),
    "intensity_by_state": {"idle": 0.11, "reading": 0.24, "typing": 0.36, "mouse": 0.3, "talking": 0.41, "reacting": 0.33},
}
PROFILES = {"default": {}, "calm": CALM}
assert set(CALM) <= set(DEFAULTS)

def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def gaze_for(nx, ny):
    """Normalised monitor position -> (yaw, pitch) in degrees; same convention as streamer_agent.gaze_for."""
    return (clamp(nx, 0.0, 1.0) - 0.5) * 40.0, (0.5 - clamp(ny, 0.0, 1.0)) * 20.0


class MotionDirector:
    """Keeps the schedules (glances, fidgets, posture shifts, reactions, chat phases) and eases the outputs between ticks."""

    def __init__(self, rng, camera="face", mouse_state="mouse", chat_side=1, defaults=None):
        if camera not in CAMERAS:
            raise ValueError(f"camera must be one of {CAMERAS}")
        if mouse_state not in ("mouse", "reading"):
            raise ValueError("mouse_state must be 'mouse' or 'reading' (the pre-review workaround)")
        self.rng = rng
        self.camera = camera
        self.mouse_state = mouse_state
        self.chat_side = 1 if chat_side >= 0 else -1
        self.d = dict(DEFAULTS)
        if defaults:
            self.d.update(defaults)
        d = self.d
        self.last_t = None
        # debounced state
        self.state, self.state_since = "idle", -1e9
        # action holds
        self.type_since, self.type_episode_t0, self.type_last, self.type_until = None, -1e9, -1e9, -1e9
        self.mouse_until, self.read_until, self.last_pointer, self.last_click = -1e9, -1e9, -1e9, -1e9
        self.target, self.target_until, self.prev_action = None, -1e9, "none"
        self.busy_t, self.settle_t = None, None             # last tick that blocks a chat glance / a fidget
        # edges
        self.reaction_seen, self.chat_prev, self.speak_prev = "none", False, False
        # reactions
        self.react_kind, self.react_t0, self.react_until = "none", -1e9, -1e9
        self.react_tilt, self.react_yaw, self.react_chin = 0.0, 0.0, False
        self.react_amount, self.react_rate = 0.0, 0.0
        # head: chat answer phases, silent glances, the camera hold after a chat answer
        self.chat_phase, self.chat_phase_until, self.chat_t0, self.chat_end_t = "none", -1e9, -1e9, -1e9
        self.chat_speech_t0, self.chat_cam_done, self.chat_mid_done, self.chat_mid_at = None, False, False, 0.0
        self.cam_until = -1e9
        self.next_lens_check = None
        self.beat_next, self.beat_yaw, self.beat_pitch = None, 0.0, 0.0     # talk beats (K 10-27)
        self.beat_yaw_out = self.beat_pitch_out = 0.0
        self.chat_glance_until, self.next_chat_glance, self.wait_glanced = -1e9, None, False
        # nods
        self.nod_t0, self.nod_peak, self.pending_nod = -1e9, 0.0, None
        # hands
        self.gesture_until, self.gesture_hand, self.gesture_amp, self.next_gesture = -1e9, "left", 0.0, 1e18
        # page comments: the 14-26 s between gestures is counted in speaking time across utterances (a comment is ~7 s,
        # so a wall-clock timer restarted at every utterance never fired; live 2026-10-28)
        self.talk_credit, self.talk_need = 0.0, None
        self.fidget_kind, self.fidget_until, self.fidget_hand, self.next_fidget = "none", -1e9, "left", None
        # posture
        self.posture_back_until, self.next_posture_shift = -1e9, None
        self.wshift, self.wshift_target, self.next_weight_shift = 0.0, 0.0, None
        self.bored_until, self.bored_done, self.bored_yaw = -1e9, False, 0.0
        # eased outputs
        self.yaw = self.pitch = 0.0
        self.s = 0.0                                          # signed posture: + forward lean, - lean back
        self.tilt = 0.0
        self.breath = d["breath_rest_hz"]
        self.phase_a, self.phase_b = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)

    # ---- helpers --------------------------------------------------------------------------------------------------
    def u(self, key):
        v = self.d[key]
        return self.rng.uniform(*v) if isinstance(v, tuple) else float(v)

    def talk_beat(self, now, speaking, reacting, paused, look_cam):
        """Phrase-scale head accents while speaking (K 10-27) -> (yaw, pitch) offset held until the next beat; some
        beats carry a small nod, only once the native envelope can re-arm (the decayed nod value <= 0.02)."""
        d = self.d
        if not speaking or reacting or paused:
            self.beat_next, self.beat_yaw, self.beat_pitch = None, 0.0, 0.0
            return 0.0, 0.0
        if self.beat_next is None or now >= self.beat_next:
            first = self.beat_next is None                 # the utterance's first beat: the onset nod is its accent
            scale = d["talk_beat_look_cam_scale"] if look_cam else 1.0
            self.beat_yaw = self.rng.uniform(-d["talk_beat_yaw_deg"], d["talk_beat_yaw_deg"]) * scale
            self.beat_pitch = self.rng.uniform(-d["talk_beat_pitch_deg"], d["talk_beat_pitch_deg"]) * scale
            self.beat_next = now + self.u("talk_beat_every_s")
            current = self.nod_peak * max(0.0, 1.0 - (now - self.nod_t0) / d["nod_decay_s"])
            if not first and self.rng.random() < d["talk_beat_nod_p"] and current <= 0.02:
                self.nod(self.u("talk_beat_nod_strength"), now)
        return self.beat_yaw, self.beat_pitch

    def nod(self, strength, now):
        if strength > 0 and strength >= self.nod_peak * max(0.0, 1 - (now - self.nod_t0) / self.d["nod_decay_s"]):
            self.nod_t0, self.nod_peak = now, clamp(strength, 0.0, 1.0)

    def ease(self, cur, target, dt, tau):
        return cur + (target - cur) * (1 - math.exp(-dt / tau)) if dt > 0 else cur

    def move(self, cur, target, dt, rate):
        """Rate-limited approach: at most `rate` units per second."""
        step = rate * dt
        return cur + clamp(target - cur, -step, step)

    def pick_weighted(self, weights):
        live = {k: w for k, w in weights.items() if w > 0}
        if not live:
            return None
        r, acc = self.rng.random() * sum(live.values()), 0.0
        for key, w in live.items():
            acc += w
            if r <= acc:
                return key
        return next(iter(live))

    def sign(self):
        return 1 if self.rng.random() < 0.5 else -1

    # ---- edges ----------------------------------------------------------------------------------------------------
    def start_reaction(self, kind, now):
        d = self.d
        self.react_kind, self.react_t0 = kind, now
        self.react_amount, self.react_rate = 0.0, 0.0
        if kind == "surprise":
            self.react_until = now + d["surprise_s"]
            self.react_amount = max(d["surprise_back_amount"], d["surprise_check_lean"])
            self.react_rate = d["surprise_back_amount"] / d["surprise_back_rise_s"]
        elif kind == "laugh":
            self.react_until = now + self.u("laugh_s")
            self.react_tilt = self.u("laugh_tilt_deg") * self.sign()
            self.react_amount = d["laugh_back_amount"]
            self.react_rate = d["laugh_back_amount"] / d["laugh_back_rise_s"]
        else:
            self.react_until = now + self.u("think_s")
            self.react_tilt = self.u("think_tilt_deg") * self.sign()
            self.react_yaw = d["think_gaze_yaw_deg"] * self.sign()
            self.react_chin = self.rng.random() < d["think_chin_p"]
        self.nod(d["reaction_nod"][kind], now)
        self.fidget_kind, self.fidget_until = "none", -1e9          # a reaction interrupts a fidget and a gesture
        self.gesture_until = -1e9
        self.bored_until = -1e9

    def start_chat(self, now):
        self.chat_t0 = now
        self.bored_until = -1e9
        if now - self.chat_end_t < self.d["chat_continue_s"]:         # the next chunk of the same answer: no new cycle
            self.chat_phase, self.chat_phase_until = "screen", -1e9
            return
        self.chat_speech_t0, self.chat_cam_done, self.chat_mid_done = None, False, False
        self.chat_mid_at = self.u("chat_mid_glance_at_s")
        self.chat_phase, self.chat_phase_until = "read", now + self.u("chat_read_first_s")

    def end_chat(self, now):
        if self.chat_phase == "camera":                                # finish the eye-line hold, then back to the screen
            self.cam_until = max(self.cam_until, min(self.chat_phase_until, now + self.d["camera_hold_after_speech_s"]))
        self.chat_phase, self.chat_phase_until, self.chat_end_t = "none", -1e9, now

    def start_speech(self, now, chat_addressed):
        d = self.d
        self.bored_until = -1e9
        if chat_addressed:
            if self.chat_speech_t0 is None:
                self.chat_speech_t0 = now
            self.next_gesture = now + max(d["gesture_after_speech_start_s"], 0.4 * self.u("gesture_every_chat_s"))
        else:                                                          # a dry page comment: onset nod, rare gesture
            self.pending_nod = (now + d["speech_start_nod_delay_s"], d["speech_start_nod"])
            if self.talk_need is None:
                self.talk_credit, self.talk_need = 0.0, self.u("gesture_every_talk_s")
            self.next_gesture = now + max(d["gesture_after_speech_start_s"], self.talk_need - self.talk_credit)

    def end_speech(self, now, chat_addressed):
        self.pending_nod = None
        if chat_addressed and self.chat_phase in ("camera", "chat"):
            self.chat_phase_until = min(self.chat_phase_until, now + self.d["camera_hold_after_speech_s"])

    # ---- the tick ---------------------------------------------------------------------------------------------------
    def tick(self, now, action="none", speaking=False, chat_addressed=False, reaction="none", seconds_in_state=0.0,
             screen_target=None, paused=False):
        d = self.d
        action = action if action in ACTIONS else "none"
        reaction = reaction if reaction in REACTIONS else "none"
        speaking, chat_addressed, paused = bool(speaking), bool(chat_addressed), bool(paused)
        chat_addressed = chat_addressed and not paused
        speaking = speaking and not paused
        dt = 0.25 if self.last_t is None else clamp(now - self.last_t, 0.0, 5.0)
        self.last_t = now
        if self.next_fidget is None:                                 # first tick: seed the long schedules
            self.last_pointer = now                                  # he sits down with the mouse hand on the mouse (A2)
            self.next_fidget = now + self.u("fidget_every_s")
            self.next_chat_glance = now + self.u("chat_glance_every_s")
            self.next_lens_check = now + self.u("lens_check_every_s")
            self.next_posture_shift = now + self.u("posture_shift_every_s")
            self.next_weight_shift = now + self.u("weight_shift_every_s")
            self.busy_t = self.settle_t = now
            self.state_since = now - d["state_min_dwell_s"]            # the first tick may still pick its state at once

        # -- edges
        if reaction != "none" and reaction != self.reaction_seen and not paused:
            self.start_reaction(reaction, now)
        self.reaction_seen = reaction
        if chat_addressed and not self.chat_prev:
            self.start_chat(now)
        elif self.chat_prev and not chat_addressed:
            self.end_chat(now)
        self.chat_prev = chat_addressed
        if speaking and not self.speak_prev:
            self.start_speech(now, chat_addressed)
        elif self.speak_prev and not speaking:
            self.end_speech(now, chat_addressed)
        self.speak_prev = speaking
        if speaking and not chat_addressed:
            self.talk_credit += dt

        # -- action holds (A3, A4, A5)
        if action in ("type", "search") and not paused:
            if self.type_since is None or now >= self.type_until:    # the hands had left: a new reach, unless typing
                self.type_since = self.type_episode_t0 if now - self.type_last < d["keyboard_pause_hold_s"] else now
                self.type_episode_t0 = self.type_since               # ... resumes within the pause hold (same episode)
            self.type_last, self.type_until = now, now + d["hands_linger_s"]
        elif self.type_since is not None and now >= self.type_until:
            self.type_since = None
        if action in POINTER and not paused:
            self.mouse_until, self.last_pointer = now + d["mouse_hold_s"], now
            if action != "scroll":                                   # the page changes: he waits for it, the read is over
                self.last_click, self.read_until = now, -1e9
        if action == "read":
            self.read_until = now + d["read_hold_s"]
        if screen_target is not None and not paused:                 # a hold is armed once per new target, not per tick
            tgt = (round(float(screen_target[0]), 3), round(float(screen_target[1]), 3))
            if tgt != self.target or (action not in ("read", "none") and action != self.prev_action):
                self.target = tgt
                self.target_until = now + self.u("scroll_target_hold_s" if action == "scroll" else "click_target_hold_s")
        self.prev_action = action
        hands_on_keys = self.type_since is not None and not paused
        typing_state = hands_on_keys and now - self.type_since >= d["hands_lead_s"]
        reacting = now < self.react_until and not paused
        react_t = now - self.react_t0
        if action != "none" or speaking or chat_addressed or reacting:
            self.bored_until = -1e9                                  # anything happening cancels boredom at once
        if speaking or chat_addressed or reacting or hands_on_keys or action in ("click", "navigate") or paused:
            self.busy_t = now
        if reacting or hands_on_keys or action in ("click", "navigate") or paused:
            self.settle_t = now

        # -- state with debounce (one change per state_min_dwell_s)
        if speaking:
            under = "talking"
        elif typing_state:
            under = "typing"
        elif now < self.mouse_until:
            under = self.mouse_state
        elif action == "read" or now < self.read_until:
            under = "reading"
        else:
            under = "idle"
        want = "idle" if paused else "reacting" if reacting else under
        if want != self.state and now - self.state_since >= d["state_min_dwell_s"]:
            self.state, self.state_since = want, now
            self.wait_glanced = False
            if want != "idle":
                self.bored_done = False
        state = self.state

        # -- head: chat answer phases, silent glances, shared reactions (A10, A11, A12; K rules 3, 5, 6, 7)
        look_cam, look_chat = 0.0, 0.0
        if not paused:
            if chat_addressed:
                ph, until = self.chat_phase, self.chat_phase_until
                if ph == "read" and now >= until:
                    ph = "screen"
                if ph == "screen":
                    if speaking and not self.chat_cam_done:          # the read beat is over and the voice plays: to the lens
                        ph, until, self.chat_cam_done = "camera", now + self.u("chat_camera_s"), True
                        if self.chat_speech_t0 is None:
                            self.chat_speech_t0 = now
                        self.nod(d["chat_ack_nod"], now)
                    elif (speaking and self.chat_cam_done and not self.chat_mid_done and self.chat_speech_t0 is not None
                          and now - self.chat_speech_t0 >= self.chat_mid_at):
                        ph, until, self.chat_mid_done = "chat", now + self.u("chat_mid_glance_s"), True
                elif ph in ("camera", "chat") and now >= until:
                    ph = "screen"
                self.chat_phase, self.chat_phase_until = ph, until
                look_cam = 1.0 if ph == "camera" else 0.0
                look_chat = 1.0 if ph in ("read", "chat") else 0.0
            else:
                # a rare silent look at the viewers while idle or reading (K 10-27): same gates as a chat glance
                if (state in ("idle", "reading") and not speaking and not hands_on_keys and not reacting
                        and now >= self.next_lens_check and now >= self.chat_glance_until and now >= self.cam_until
                        and now - self.busy_t >= d["chat_glance_min_state_s"] and now >= self.mouse_until):
                    self.cam_until = now + self.u("lens_check_s")
                    self.next_lens_check = self.cam_until + self.u("lens_check_every_s")
                if now < self.cam_until:                             # the eye-line hold at the end of a chat answer
                    look_cam = 1.0
                # a silent glance at the chat without stopping; not within 8 s of speech/typing/reaction/page change,
                # not during a scroll, never while typing, reacting or talking
                quiet_head = (not speaking and not hands_on_keys and not reacting and not look_cam
                              and now - self.busy_t >= d["chat_glance_min_state_s"] and now >= self.mouse_until)
                if now >= self.next_chat_glance and now >= self.chat_glance_until:
                    if quiet_head:
                        self.chat_glance_until = now + self.u("chat_glance_s")
                        self.next_chat_glance = self.chat_glance_until + self.u("chat_glance_every_s")
                    else:
                        self.next_chat_glance = now + 5.0
                # waiting for a page after a click: one short glance once the wait exceeds 3 s (K rule 5)
                if (state == "idle" and not self.wait_glanced and not speaking and not reacting and not look_cam
                        and not hands_on_keys and now - self.state_since >= d["wait_glance_at_s"]
                        and self.last_click >= self.state_since - 2.0 and now >= self.chat_glance_until):
                    self.wait_glanced = True
                    self.chat_glance_until = now + self.u("wait_glance_s")
                if now < self.chat_glance_until and not look_cam:
                    look_chat = 1.0
            # reactions shared with the viewers (one short lens look each; no camera for think)
            if reacting and self.react_kind == "surprise" and d["surprise_camera_at_s"] <= react_t < d["surprise_camera_at_s"] + d["surprise_camera_s"]:
                look_cam, look_chat = 1.0, 0.0
            if reacting and self.react_kind == "laugh" and d["laugh_camera_at_s"] <= react_t < d["laugh_camera_at_s"] + d["laugh_camera_s"]:
                look_cam, look_chat = 1.0, 0.0

        # -- nods: only the delayed speech-onset nod is scheduled here; chat ack and reactions fire on their edges
        if paused:
            self.pending_nod = None
        elif self.pending_nod is not None and now >= self.pending_nod[0]:
            self.nod(self.pending_nod[1], now)
            self.pending_nod = None

        # -- posture schedules: chair shift, weight shift, boredom (A7, A17, A18; K rule 9)
        if now >= self.next_posture_shift:
            if reacting or chat_addressed or hands_on_keys or now < self.bored_until or paused:
                self.next_posture_shift = now + 5.0
            else:
                self.posture_back_until = now + self.u("posture_back_s")
                self.next_posture_shift = self.posture_back_until + self.u("posture_shift_every_s")
        leaned_back = now < self.posture_back_until and not chat_addressed and not reacting and not paused
        if now >= self.next_weight_shift:
            self.wshift_target = d["weight_shift_amount"] * (-1 if self.wshift_target > 0 else 1)
            self.next_weight_shift = now + self.u("weight_shift_every_s")
        self.wshift = self.move(self.wshift, 0.0 if paused else self.wshift_target, dt, d["weight_shift_amount"] / d["weight_shift_s"])
        idle_quiet = state == "idle" and not speaking and not chat_addressed and not reacting and not hands_on_keys and not paused
        if (idle_quiet and not self.bored_done and now - self.state_since >= d["bored_after_s"]
                and now - self.last_pointer >= d["bored_after_s"]):
            self.bored_done, self.bored_until = True, now + self.u("bored_hold_s")
            self.bored_yaw = d["bored_gaze_yaw_deg"] * self.sign()
            self.next_fidget = min(self.next_fidget, now + 1.0 + self.rng.random())   # one desk fidget once settled back
        bored = idle_quiet and now < self.bored_until

        # -- hands: base placement (A1..A5)
        if paused:
            left = right = "rest"
        elif hands_on_keys:
            left = right = "keyboard"
        else:
            right = "mouse" if now - self.last_pointer < d["mouse_hand_rest_after_s"] else "rest"
            left = "rest"
        free = None if hands_on_keys or paused else "left"            # the free hand is the left (K)
        # gestures while talking (A8): the free hand, the right only in a chat answer with no pointer action in flight
        if speaking and not hands_on_keys and not reacting and now >= self.next_gesture and now >= self.gesture_until:
            self.gesture_until = now + self.u("gesture_s")
            self.gesture_amp = self.u("gesture_strength")
            take_right = chat_addressed and now >= self.mouse_until and self.rng.random() < d["gesture_right_hand_p"]
            self.gesture_hand = "right" if take_right else "left"
            if chat_addressed:
                self.next_gesture = self.gesture_until + self.u("gesture_every_chat_s")
            else:
                self.talk_credit, self.talk_need = -(self.gesture_until - now), self.u("gesture_every_talk_s")
                self.next_gesture = self.gesture_until + self.talk_need
        gesturing = now < self.gesture_until and not hands_on_keys and not reacting and not paused
        # fidgets with the free hand (A19): desk/finger only; not in the first seconds of an answer, not on a fresh state
        fidget_ok = (free is not None and not reacting and not gesturing and now - self.settle_t >= d["fidget_min_state_s"]
                     and (not chat_addressed or now - self.chat_t0 >= d["fidget_quiet_after_chat_s"]))
        if now >= self.next_fidget and now >= self.fidget_until:
            kind = self.pick_weighted(d["fidget_weights"]) if fidget_ok else None
            if kind is not None:
                self.fidget_kind, self.fidget_hand = kind, free
                self.fidget_until = now + self.rng.uniform(*d["fidget_s"][kind])
                self.next_fidget = self.fidget_until + self.u("fidget_every_s")
            else:
                self.next_fidget = now + 3.0
        fidgeting = now < self.fidget_until and not paused and not hands_on_keys and not reacting
        fidget = self.fidget_kind if fidgeting else "none"
        lifted = fidgeting and fidget not in ("desk", "chair")       # a hand leaves the desk only for the authored kinds
        if gesturing:
            if self.gesture_hand == "left":
                left = "gesture"
            else:
                right = "gesture"
        if lifted:
            if self.fidget_hand == "left":
                left = "gesture"
            else:
                right = "gesture"
        chin = reacting and self.react_kind == "think" and self.react_chin and free is not None
        if chin:
            left = "gesture"
        gesture_strength = 0.0
        if gesturing:
            gesture_strength = self.gesture_amp
        elif fidgeting and fidget == "desk":
            gesture_strength = d["fidget_strength"]
        elif lifted:
            gesture_strength = 0.3
        elif chin:
            gesture_strength = 0.25

        # -- posture target (one signed channel; A6, A7, A9, A14..A18; K rules 1, 5, 7, 8, 9, 10)
        base = d["lean_by_state"][under]
        if speaking:
            s_t = -(d["chat_talk_back_amount"] if chat_addressed else d["talk_back_amount"])
        elif chat_addressed and not self.chat_cam_done:
            s_t = d["chat_read_lean"]                                # reading the message before the answer
        else:
            s_t = base
        tilt_t, react_pose = 0.0, False
        if reacting:
            if self.react_kind == "surprise":
                if react_t < d["surprise_check_at_s"]:
                    s_t, react_pose = -d["surprise_back_amount"], True
                elif react_t < d["surprise_camera_at_s"] + d["surprise_camera_s"]:
                    s_t, react_pose = d["surprise_check_lean"], True
            elif self.react_kind == "laugh":
                if react_t < d["laugh_camera_at_s"] + d["laugh_camera_s"]:
                    s_t, tilt_t, react_pose = -d["laugh_back_amount"], self.react_tilt, True
            else:
                tilt_t = self.react_tilt
        if leaned_back and not speaking:
            s_t = min(s_t, -d["posture_back_amount"])                # the hold replaces the reading lean (K)
        slump_f = 0.0
        if (not reacting and not chat_addressed and not speaking and not leaned_back and not bored
                and state in ("reading", "idle", "mouse")):
            slump_f = clamp((seconds_in_state - d["focus_slump_s"]) / d["focus_slump_ramp_s"], 0.0, 1.0)
            s_t -= d["slump_back_amount"] * slump_f
        if bored:
            s_t = -d["bored_back_amount"]
        if paused:
            s_t, tilt_t = 0.0, 0.0
        # rates: a reaction pose rises at its own rate and recovers over `reaction_recover_s`; posture changes take
        # `lean_rise_s` per 0.30 towards a pose and `lean_fall_s` per 0.30 when relaxing; boredom settles slowly
        if self.react_rate > 0 and (reacting or now < self.react_until + d["reaction_recover_s"]):
            rate = self.react_rate if react_pose else self.react_amount / d["reaction_recover_s"]
        elif s_t != 0.0 and (abs(s_t) > abs(self.s) or (s_t > 0) != (self.s > 0)):
            rate = 0.3 / d["lean_rise_s"]
        else:
            rate = 0.3 / d["lean_fall_s"]
        if bored:
            rate = min(rate, d["bored_back_amount"] / d["bored_rise_s"])
        self.s = self.move(self.s, s_t, dt, rate)
        self.tilt = self.ease(self.tilt, tilt_t, dt, d["gaze_tau_s"])
        posture = ("neutral" if paused else "back" if s_t <= -0.2 else "slump" if slump_f >= 0.5
                   else "forward" if s_t >= 0.4 else "upright")

        # -- head aim target (A1, A2, A10..A16; K rules 1, 2, 9): voluntary aims settle fast, the reading filter slowly
        tau = d["gaze_tau_s"]
        if paused:
            yaw_t, pitch_t = 0.0, 0.0
        elif look_cam:
            yaw_t, pitch_t = 0.0, d["camera_pitch_deg"]
        elif look_chat:
            yaw_t, pitch_t = d["chat_yaw_deg"] * self.chat_side, d["chat_pitch_deg"]
        elif reacting and self.react_kind == "think":
            yaw_t, pitch_t = self.react_yaw, d["think_gaze_pitch_deg"]
        elif reacting and self.react_kind == "laugh" and react_pose:
            yaw_t, pitch_t = 0.0, d["laugh_pitch_deg"]
        elif self.target is not None and now < self.target_until:
            yaw_t, pitch_t = gaze_for(*self.target)
            yaw_t, pitch_t = yaw_t * d["action_gaze_gain"], pitch_t * d["action_gaze_gain"]
        elif bored:
            yaw_t, pitch_t, tau = self.bored_yaw, d["bored_gaze_pitch_deg"], d["reading_gaze_smooth_s"]
        elif state in ("reading", "typing", "mouse"):
            nx = 0.5 + 0.18 * math.sin(now * 2 * math.pi / 3.2 + self.phase_a)
            ny = 0.3 + 0.4 * ((now % 24.0) / 24.0)
            yaw_t, pitch_t = gaze_for(nx, ny)
            yaw_t = clamp(yaw_t * d["reading_gaze_gain"], -d["reading_gaze_max_yaw_deg"], d["reading_gaze_max_yaw_deg"])
            pitch_t = clamp(pitch_t * d["reading_gaze_gain"], -d["reading_gaze_max_pitch_deg"], d["reading_gaze_max_pitch_deg"])
            tau = d["reading_gaze_smooth_s"]
        else:
            w, f = d["reading_head_wander_deg"], d["reading_head_wander_hz"]
            yaw_t = w * 3 * math.sin(2 * math.pi * f * now + self.phase_a) * d["idle_gaze_gain"]
            pitch_t = w * 2 * math.sin(2 * math.pi * f * 0.7 * now + self.phase_b) * d["idle_gaze_gain"]
            tau = d["reading_gaze_smooth_s"]
        if slump_f > 0:
            pitch_t += d["slump_pitch_deg"] * slump_f
        # the return from an excursion (chat, lens, target) is a voluntary move too: fast, then the slow filter takes over
        if abs(yaw_t - self.yaw) > d["reading_gaze_max_yaw_deg"] + 1.0 or abs(pitch_t - self.pitch) > d["reading_gaze_max_pitch_deg"] + 1.0:
            tau = d["gaze_tau_s"]
        self.yaw = self.ease(self.yaw, yaw_t, dt, tau)
        self.pitch = self.ease(self.pitch, pitch_t, dt, tau)
        w, f = d["reading_head_wander_deg"], d["reading_head_wander_hz"]
        if paused:
            wander_y = wander_p = 0.0
        else:                                                        # two incommensurate sines: smooth drift, not a loop
            wander_y = w * (0.7 * math.sin(2 * math.pi * f * now + self.phase_b)
                            + 0.3 * math.sin(2 * math.pi * f * 1.7 * now + self.phase_a)) * (1.4 if speaking else 1.0)
            wander_p = w * 0.6 * (0.7 * math.sin(2 * math.pi * f * 1.3 * now + self.phase_a)
                                  + 0.3 * math.sin(2 * math.pi * f * 0.6 * now + self.phase_b))

        # talk beats, eased like any voluntary aim (K 10-27)
        by, bp = self.talk_beat(now, speaking, reacting, paused, look_cam)
        self.beat_yaw_out = self.ease(self.beat_yaw_out, by, dt, d["gaze_tau_s"])
        self.beat_pitch_out = self.ease(self.beat_pitch_out, bp, dt, d["gaze_tau_s"])

        # -- nod, intensity, breathing
        nod = 0.0 if paused else self.nod_peak * max(0.0, 1 - (now - self.nod_t0) / d["nod_decay_s"])
        if paused:
            inten = 0.0
        elif state == "reacting":
            inten = d["intensity_by_reaction"].get(self.react_kind, 0.5)
        else:
            inten = d["intensity_by_state"][state]
        if chat_addressed and not paused:
            inten += d["intensity_chat_bonus"]
        if reacting and self.react_kind == "laugh":
            breath_t = d["breath_laugh_hz"]
        elif reacting and self.react_kind == "surprise":
            breath_t = d["breath_surprise_hz"]
        elif speaking:
            breath_t = d["breath_talking_hz"]
        elif state == "reading":
            breath_t = d["breath_reading_hz"]
        else:
            breath_t = d["breath_rest_hz"]
        self.breath = self.ease(self.breath, breath_t, dt, 0.4 if reacting else d["breath_tau_s"])

        s_out = 0.0 if paused else self.s + self.wshift
        return {
            "state": state,
            "gaze_yaw_deg": round(clamp(self.yaw + wander_y + self.beat_yaw_out, -20.0, 20.0), 2),
            "gaze_pitch_deg": round(clamp(self.pitch + wander_p + self.beat_pitch_out, -10.0, 10.0), 2),
            "nod_strength": round(clamp(nod, 0.0, 1.0), 3),
            "intensity": round(clamp(inten, 0.0, 1.0), 2),
            "camera": "spectator" if paused else self.camera,
            "motion": {
                "schema": SCHEMA,
                "lean": round(clamp(s_out, 0.0, 1.0), 3),
                "lean_back": round(clamp(-s_out, 0.0, 1.0), 3),
                "head_tilt_deg": round(clamp(self.tilt, -12.0, 12.0), 2),
                "look_at_camera": look_cam,
                "look_to_chat": look_chat,
                "hand_left": left,
                "hand_right": right,
                "gesture_strength": round(clamp(gesture_strength, 0.0, 1.0), 2),
                "breathing_rate_hz": round(self.breath, 3),
                "fidget": fidget,
                "posture": posture,
            },
        }


def event_fields(out):
    """The six v2 event fields of a tick result (for `payload.update(...)` in the agent's Visual.snapshot)."""
    return {k: out[k] for k in ("state", "gaze_yaw_deg", "gaze_pitch_deg", "nod_strength", "intensity", "camera")}
