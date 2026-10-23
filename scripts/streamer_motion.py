"""Motion direction for SUB-01 at his desk: the agent's situation -> motion parameters, every tick, no I/O.

    from scripts.streamer_motion import MotionDirector
    md = MotionDirector(random.Random(7))
    out = md.tick(now, action="scroll", speaking=False, chat_addressed=False, reaction="none", seconds_in_state=42.0)
    out -> {"state", "gaze_yaw_deg", "gaze_pitch_deg", "nod_strength", "intensity", "camera", "motion": {...}}

The first six keys are the native event v2 fields (tools/native_streamer_visual_v2/README.md); `motion` is the proposed
extension (docs/streamer/MOTION-SPEC.md) and is ignored by the current native parser. Pure standard library, no clock,
no files: `now` comes from the caller, every random draw comes from the `rng` given to the constructor, so two directors
with equal seeds and equal inputs produce byte-identical output. Behaviour and numbers follow
docs/streamer/ANIMATION-REFERENCES.md (study, section 4) and DIRECTION.md (character, camera rule 10).

Inputs per tick
  action          read | scroll | click | type | search | navigate | none   (the agent's current desktop action kind;
                  it may be given once on the tick it happens or on every tick while it lasts: both work)
  speaking        bool, his voice is playing now
  chat_addressed  bool, the current speech answers a chat message (set it when the batch is picked, a little before speech)
  reaction        none | surprise | laugh | think   (edge triggered: a kind must return to none before it fires again)
  seconds_in_state  seconds the agent has spent in its current focus/browse state (long focus -> slump)
  screen_target   optional (nx, ny) in 0..1, where on the monitor the action points (streamer_agent.attention_of)
  paused          bool, kill switch or manual pause: neutral body, spectator camera

Outputs
  state           idle | reading | typing | mouse | talking | reacting   (at most one change per `state_min_dwell_s`)
  gaze_yaw_deg    -20..20 (right +)   gaze_pitch_deg  -10..10 (up +)     nod_strength 0..1 (decays over 1 s)
  intensity       0..1                camera          face | monitor | spectator
  motion.lean 0..1 towards the camera/monitor, motion.lean_back 0..1, motion.head_tilt_deg -12..12 (right ear down +),
  motion.look_at_camera 0..1, motion.look_to_chat 0..1 (chat anchor: `chat_side` * ~30 deg beyond the gaze cap),
  motion.hand_left / hand_right  rest | mouse | keyboard | gesture,  motion.gesture_strength 0..1,
  motion.breathing_rate_hz, motion.fidget (none|face|headphones|neck|drink|stretch|chair), motion.posture label.
"""
from __future__ import annotations

import math

SCHEMA = "sub01.streamer-motion.v1"
STATES = ("idle", "reading", "typing", "mouse", "talking", "reacting")
ACTIONS = ("read", "scroll", "click", "type", "search", "navigate", "none")
REACTIONS = ("none", "surprise", "laugh", "think")
HANDS = ("rest", "mouse", "keyboard", "gesture")
FIDGETS = ("none", "face", "headphones", "neck", "drink", "stretch", "chair")
CAMERAS = ("face", "monitor", "spectator")

# ---- defaults: one table. Ranges (lo, hi) are drawn uniformly from the rng each time they are used. --------------------
# Column "why" points at docs/streamer/ANIMATION-REFERENCES.md (A1..A22 = catalogued behaviours, R = reference numbers).
DEFAULTS = {
    # timing hygiene
    "state_min_dwell_s": 0.5,            # no state flaps faster than this (native debounce is 0.6 s; the 0.24 s crossfade)
    "mouse_hold_s": 2.0,                 # a scroll/click/navigate keeps the mouse state this long (A4)
    "read_hold_s": 6.0,                  # a "read" action keeps the reading state this long after the last tick it was given
    "hands_lead_s": 0.3,                 # hands reach the keyboard this long before the typing clip starts (A3)
    "hands_linger_s": 0.6,               # hands stay on the keyboard this long after the last typed character (A3)
    "mouse_hand_rest_after_s": 90.0,     # the mouse hand drifts to rest after this long without any pointer action (A2, A5)
    # eyes and head
    "camera_glance_every_s": (20.0, 40.0),   # while talking to nobody in particular: a look at the lens (A12)
    "camera_glance_s": (1.0, 2.0),
    "speech_first_glance_s": (2.0, 10.0),    # the first glance after speech starts comes sooner (A12)
    "chat_read_first_s": (1.2, 2.5),         # answering chat: read the message first, head to the chat anchor (A10, A11)
    "chat_camera_s": (2.0, 4.0),             # ... then speak to the lens (A11)
    "chat_screen_s": (1.5, 3.0),             # ... glance back to the chat, repeat: about 60% of the answer is to the camera
    "chat_glance_every_s": (30.0, 90.0),     # silent reading/idle: a glance at the chat without stopping (A10)
    "chat_glance_s": (1.0, 3.0),
    "camera_pitch_deg": 8.0,                 # the webcam sits above the monitor: looking at it raises the head (R: 2 deg below lens)
    "chat_yaw_deg": 20.0,                    # gaze cap towards the chat side; `look_to_chat` carries the rest of the head turn
    "gaze_tau_s": 0.35,                      # exponential ease of the gaze (eye+head gaze shifts settle in ~0.3 s)
    "reading_gaze_gain": 0.55,               # the head follows the lines only partly: eyes do most of a <20 deg shift (R)
    "idle_gaze_gain": 0.3,
    "target_hold_s": 5.0,                    # an action's screen point holds the gaze this long
    # nods
    "nod_decay_s": 1.0,
    "speech_start_nod": 0.4,                 # a small nod opens an utterance (A13)
    "talk_nod_every_s": (2.5, 5.0),          # phrase-boundary nods while talking (R: Ishi 2007) (A13)
    "talk_nod_strength": (0.12, 0.3),
    "chat_ack_nod": 0.3,                     # the first look up to the camera in a chat answer carries a nod (A11)
    "reaction_nod": {"surprise": 0.6, "laugh": 0.8, "think": 0.3},
    # posture (lean towards camera/monitor, lean back)
    "lean_by_state": {"idle": 0.15, "reading": 0.3, "typing": 0.25, "mouse": 0.25, "talking": 0.35, "reacting": 0.3},
    "lean_chat": 0.65,                       # addressing chat: in towards the lens (A9)
    "lean_chat_reading": 0.45,               # ... while reading the message
    "lean_rise_s": 0.6,                      # full-range lean-in time
    "lean_fall_s": 1.4,                      # full-range return time
    "posture_shift_every_s": (150.0, 300.0), # a chair shift, upright <-> back (R: 18-22 shifts/h incl. small ones) (A17)
    "posture_back_s": (20.0, 60.0),          # how long the leaned-back posture holds
    "posture_back_amount": 0.35,
    "focus_slump_s": 1200.0,                 # after 20 min of one focus the posture sags (R: slump after ~20 min) (A18)
    "slump_back_amount": 0.15,
    # reactions
    "surprise_s": 2.0,                       # head back, then in towards the screen to check (A14)
    "surprise_back_amount": 0.45,
    "surprise_camera_at_s": 0.5,             # the look to the lens that shares the reaction (A14, A12)
    "laugh_s": (1.5, 3.0),                   # lean back + tilt, then recover (A15)
    "laugh_back_amount": 0.8,
    "laugh_tilt_deg": (5.0, 9.0),
    "laugh_camera_at_s": 0.8,
    "share_camera_s": 1.5,
    "think_s": (1.5, 3.0),                   # head tilt, eyes off the screen, maybe a hand to the chin (A16)
    "think_tilt_deg": (6.0, 10.0),
    "think_gaze_yaw_deg": 8.0,
    "think_gaze_pitch_deg": 6.0,
    "think_chin_p": 0.5,
    # hands
    "gesture_every_chat_s": (6.0, 14.0),     # gestures while answering chat (A8)
    "gesture_every_talk_s": (12.0, 30.0),    # fewer when commenting on the page: the mouse hand stays (A8)
    "gesture_s": (0.8, 1.8),
    "gesture_strength": (0.35, 0.7),
    "gesture_right_hand_p": 0.5,             # chance the mouse hand leaves the mouse for a chat gesture
    "fidget_every_s": (40.0, 110.0),         # free-hand fidgets: face/chin, headphones, neck, drink (R: ~23 face touches/h) (A19)
    "fidget_weights": {"face": 0.35, "headphones": 0.2, "neck": 0.15, "drink": 0.15, "chair": 0.15},
    "fidget_s": {"face": (1.2, 2.5), "headphones": (1.0, 2.0), "neck": (1.5, 3.0), "drink": (3.0, 5.0), "chair": (1.5, 3.0)},
    "fidget_quiet_after_chat_s": 2.0,        # no fidget in the first seconds of a chat answer
    "stretch_every_s": (600.0, 1200.0),      # both arms up, lean back, rare and only when quiet (A20)
    "stretch_s": (3.0, 6.0),
    # breathing (Hz; the native layer currently breathes at a fixed 0.22)
    "breath_rest_hz": 0.22,
    "breath_reading_hz": 0.2,
    "breath_talking_hz": 0.18,               # longer cycles while speaking (R: 5.45 s speaking vs 3.68 s listening)
    "breath_surprise_hz": 0.3,
    "breath_laugh_hz": 0.5,
    "breath_tau_s": 2.0,
    # intensity (native: scales sway and nod)
    "intensity_by_state": {"idle": 0.1, "reading": 0.3, "typing": 0.55, "mouse": 0.45, "talking": 0.6, "reacting": 0.5},
    "intensity_by_reaction": {"surprise": 0.65, "laugh": 0.8, "think": 0.4},
    "intensity_chat_bonus": 0.1,
    # micro motion (deterministic wander on top of the native sway)
    "wander_deg": 0.6,
    "wander_hz": 0.07,
}


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def gaze_for(nx, ny):
    """Normalised monitor position -> (yaw, pitch) in degrees; same convention as streamer_agent.gaze_for."""
    return (clamp(nx, 0.0, 1.0) - 0.5) * 40.0, (0.5 - clamp(ny, 0.0, 1.0)) * 20.0


class MotionDirector:
    """Keeps the schedules (glances, nods, fidgets, posture shifts, reactions) and eases the outputs between ticks."""

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
        self.last_t = None
        # debounced state
        self.state, self.state_since = "idle", -1e9
        # action holds
        self.type_since, self.type_until = None, -1e9
        self.mouse_until, self.read_until, self.last_pointer = -1e9, -1e9, -1e9
        self.target, self.target_until = None, -1e9
        # edges
        self.reaction_seen, self.chat_prev, self.speak_prev = "none", False, False
        # reactions
        self.react_kind, self.react_t0, self.react_until = "none", -1e9, -1e9
        self.react_tilt, self.react_yaw, self.react_chin = 0.0, 0.0, False
        # eyes
        self.cam_until, self.next_cam_glance = -1e9, 0.0
        self.chat_phase, self.chat_phase_until, self.chat_t0, self.chat_acked = "none", -1e9, -1e9, False
        self.chat_glance_until, self.next_chat_glance = -1e9, None
        # nods
        self.nod_t0, self.nod_peak, self.next_talk_nod = -1e9, 0.0, 0.0
        # hands
        self.gesture_until, self.gesture_hand, self.gesture_amp, self.next_gesture = -1e9, "left", 0.0, 0.0
        self.fidget_kind, self.fidget_until, self.fidget_hand, self.next_fidget = "none", -1e9, "left", None
        self.stretch_until, self.next_stretch = -1e9, None
        # posture
        self.posture_back_until, self.next_posture_shift = -1e9, None
        # eased outputs
        self.yaw = self.pitch = 0.0
        self.lean = self.lean_back = self.tilt = 0.0
        self.breath = self.d["breath_rest_hz"]
        self.phase_a, self.phase_b = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)

    # ---- helpers --------------------------------------------------------------------------------------------------
    def u(self, key):
        v = self.d[key]
        return self.rng.uniform(*v) if isinstance(v, tuple) else float(v)

    def nod(self, strength, now):
        if strength > 0 and strength >= self.nod_peak * max(0.0, 1 - (now - self.nod_t0) / self.d["nod_decay_s"]):
            self.nod_t0, self.nod_peak = now, clamp(strength, 0.0, 1.0)

    def ease(self, cur, target, dt, tau):
        return cur + (target - cur) * (1 - math.exp(-dt / tau)) if dt > 0 else cur

    def slew(self, cur, target, dt, rise_s, fall_s):
        step = dt / (rise_s if target > cur else fall_s)
        return cur + clamp(target - cur, -step, step)

    def pick_weighted(self, weights):
        r, acc = self.rng.random() * sum(weights.values()), 0.0
        for key, w in weights.items():
            acc += w
            if r <= acc:
                return key
        return next(iter(weights))

    # ---- edges ----------------------------------------------------------------------------------------------------
    def start_reaction(self, kind, now):
        d = self.d
        self.react_kind, self.react_t0 = kind, now
        if kind == "surprise":
            self.react_until = now + d["surprise_s"]
        elif kind == "laugh":
            self.react_until = now + self.u("laugh_s")
            self.react_tilt = self.u("laugh_tilt_deg") * (1 if self.rng.random() < 0.5 else -1)
        else:
            self.react_until = now + self.u("think_s")
            self.react_tilt = self.u("think_tilt_deg") * (1 if self.rng.random() < 0.5 else -1)
            self.react_yaw = d["think_gaze_yaw_deg"] * (1 if self.rng.random() < 0.5 else -1)
            self.react_chin = self.rng.random() < d["think_chin_p"]
        self.nod(d["reaction_nod"][kind], now)
        self.fidget_kind, self.fidget_until = "none", -1e9          # a reaction interrupts a fidget

    def start_chat(self, now):
        self.chat_t0, self.chat_acked = now, False
        self.chat_phase, self.chat_phase_until = "read", now + self.u("chat_read_first_s")
        self.cam_until = -1e9
        self.next_gesture = now + self.u("gesture_every_chat_s") * 0.5

    def end_chat(self, now):
        self.chat_phase, self.chat_phase_until = "none", -1e9
        self.next_cam_glance = now + self.u("camera_glance_every_s")

    def start_speech(self, now, chat_addressed):
        self.nod(self.d["speech_start_nod"], now)
        self.next_talk_nod = now + self.u("talk_nod_every_s")
        if not chat_addressed:
            self.next_cam_glance = now + self.u("speech_first_glance_s")
            self.next_gesture = now + self.u("gesture_every_talk_s")

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
            self.next_stretch = now + self.u("stretch_every_s")
            self.next_posture_shift = now + self.u("posture_shift_every_s")

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
        self.speak_prev = speaking

        # -- action holds (A3, A4, A5)
        if action in ("type", "search") and not paused:
            if self.type_since is None:
                self.type_since = now
            self.type_until = now + d["hands_linger_s"]
        elif self.type_since is not None and now >= self.type_until:
            self.type_since = None
        if action in ("scroll", "click", "navigate") and not paused:
            self.mouse_until, self.last_pointer = now + d["mouse_hold_s"], now
        if action == "read":
            self.read_until = now + d["read_hold_s"]
        if screen_target is not None:
            self.target, self.target_until = (float(screen_target[0]), float(screen_target[1])), now + d["target_hold_s"]
        hands_on_keys = self.type_since is not None and not paused
        typing_state = hands_on_keys and now - self.type_since >= d["hands_lead_s"]
        reacting = now < self.react_until and not paused
        react_t = now - self.react_t0

        # -- state with debounce (one change per state_min_dwell_s)
        if paused:
            want = "idle"
        elif reacting:
            want = "reacting"
        elif speaking:
            want = "talking"
        elif typing_state:
            want = "typing"
        elif now < self.mouse_until:
            want = self.mouse_state
        elif action == "read" or now < self.read_until:
            want = "reading"
        else:
            want = "idle"
        if want != self.state and now - self.state_since >= d["state_min_dwell_s"]:
            self.state, self.state_since = want, now
        state = self.state

        # -- eyes: camera and chat (A10, A11, A12)
        look_cam, look_chat = 0.0, 0.0
        if not paused:
            if chat_addressed:
                if now >= self.chat_phase_until:
                    if self.chat_phase in ("read", "screen"):
                        self.chat_phase, self.chat_phase_until = "camera", now + self.u("chat_camera_s")
                        if not self.chat_acked:
                            self.chat_acked = True
                            self.nod(d["chat_ack_nod"], now)
                    else:
                        self.chat_phase, self.chat_phase_until = "screen", now + self.u("chat_screen_s")
                look_cam = 1.0 if self.chat_phase == "camera" else 0.0
                look_chat = 1.0 if self.chat_phase in ("read", "screen") else 0.0
            else:
                if speaking and now >= self.next_cam_glance and now >= self.cam_until:
                    self.cam_until = now + self.u("camera_glance_s")
                    self.next_cam_glance = self.cam_until + self.u("camera_glance_every_s")
                if now < self.cam_until:
                    look_cam = 1.0
                # a silent glance at the chat without stopping; none while typing, reacting or talking to the lens
                if now >= self.next_chat_glance and now >= self.chat_glance_until:
                    if hands_on_keys or reacting or look_cam:
                        self.next_chat_glance = now + 5.0
                    else:
                        self.chat_glance_until = now + self.u("chat_glance_s")
                        self.next_chat_glance = self.chat_glance_until + self.u("chat_glance_every_s")
                if now < self.chat_glance_until and not look_cam:
                    look_chat = 1.0
            # reactions shared with the viewers
            if reacting and self.react_kind == "surprise" and d["surprise_camera_at_s"] <= react_t < d["surprise_camera_at_s"] + d["share_camera_s"]:
                look_cam, look_chat = 1.0, 0.0
            if reacting and self.react_kind == "laugh" and d["laugh_camera_at_s"] <= react_t < d["laugh_camera_at_s"] + d["share_camera_s"]:
                look_cam, look_chat = 1.0, 0.0

        # -- nods while talking (A13)
        if speaking and now >= self.next_talk_nod:
            self.nod(self.u("talk_nod_strength"), now)
            self.next_talk_nod = now + self.u("talk_nod_every_s")

        # -- stretch, posture shift (A17, A18, A20)
        quiet = not speaking and not reacting and not hands_on_keys and not chat_addressed and not paused
        if quiet and state in ("idle", "reading") and now >= self.next_stretch and now >= self.stretch_until:
            self.stretch_until = now + self.u("stretch_s")
            self.next_stretch = self.stretch_until + self.u("stretch_every_s")
            self.fidget_kind, self.fidget_until = "none", -1e9
            self.posture_back_until = now                            # a stretch is the posture shift of its period
            self.next_posture_shift = self.stretch_until + self.u("posture_shift_every_s")
        stretching = now < self.stretch_until and not paused
        if now >= self.next_posture_shift and not reacting and not chat_addressed:
            self.posture_back_until = now + self.u("posture_back_s")
            self.next_posture_shift = self.posture_back_until + self.u("posture_shift_every_s")
        leaned_back = now < self.posture_back_until and not chat_addressed and not paused

        # -- hands: base placement (A1..A5)
        if paused:
            left = right = "rest"
        elif stretching:
            left = right = "gesture"
        elif hands_on_keys:
            left = right = "keyboard"
        else:
            right = "mouse" if now - self.last_pointer < d["mouse_hand_rest_after_s"] else "rest"
            left = "rest"
        free = None if hands_on_keys or stretching or paused else ("left" if right == "mouse" else "right")
        # gestures while talking (A8)
        if speaking and not hands_on_keys and not stretching and now >= self.next_gesture and now >= self.gesture_until:
            self.gesture_until = now + self.u("gesture_s")
            self.gesture_amp = self.u("gesture_strength") * (1.0 if chat_addressed else 0.7)
            take_right = chat_addressed and self.rng.random() < d["gesture_right_hand_p"]
            self.gesture_hand = "right" if (take_right or right != "mouse") else "left"
            self.next_gesture = self.gesture_until + self.u("gesture_every_chat_s" if chat_addressed else "gesture_every_talk_s")
        gesturing = now < self.gesture_until and not hands_on_keys and not stretching and not paused
        # fidgets with the free hand (A19)
        fidget_ok = (free is not None and not reacting and not gesturing and (not chat_addressed or now - self.chat_t0 >= d["fidget_quiet_after_chat_s"]))
        if now >= self.next_fidget and now >= self.fidget_until:
            if fidget_ok:
                self.fidget_kind = self.pick_weighted(d["fidget_weights"])
                self.fidget_until = now + self.rng.uniform(*d["fidget_s"][self.fidget_kind])
                self.fidget_hand = free
                self.next_fidget = self.fidget_until + self.u("fidget_every_s")
            else:
                self.next_fidget = now + 3.0
        fidgeting = now < self.fidget_until and not paused and not hands_on_keys and not stretching
        fidget = self.fidget_kind if fidgeting else ("stretch" if stretching else "none")
        if gesturing:
            if self.gesture_hand == "left":
                left = "gesture"
            else:
                right = "gesture"
        if fidgeting and fidget != "chair":
            if self.fidget_hand == "left":
                left = "gesture"
            else:
                right = "gesture"
        if reacting and self.react_kind == "think" and self.react_chin and free is not None:
            if free == "left":
                left = "gesture"
            else:
                right = "gesture"
        gesture_strength = 0.0
        if gesturing:
            gesture_strength = self.gesture_amp
        elif fidgeting and fidget != "chair":
            gesture_strength = 0.3
        elif stretching:
            gesture_strength = 0.6
        elif reacting and self.react_kind == "think" and self.react_chin:
            gesture_strength = 0.25

        # -- posture targets (A6, A7, A9, A14..A18)
        lean_t = d["lean_by_state"][state]
        back_t, tilt_t = 0.0, 0.0
        if chat_addressed:
            lean_t = max(lean_t, d["lean_chat_reading"] if self.chat_phase == "read" else d["lean_chat"])
        if reacting:
            if self.react_kind == "surprise":
                if react_t < 0.6:
                    back_t = d["surprise_back_amount"]
                else:
                    lean_t = max(lean_t, 0.5)
            elif self.react_kind == "laugh":
                back_t, tilt_t, lean_t = d["laugh_back_amount"], self.react_tilt, 0.0
            else:
                tilt_t, lean_t = self.react_tilt, 0.1
        if leaned_back and not reacting:
            back_t, lean_t = max(back_t, d["posture_back_amount"]), lean_t * 0.5
        slump = (not reacting and not chat_addressed and state in ("reading", "idle") and seconds_in_state >= d["focus_slump_s"]
                 and not leaned_back)
        if slump:
            back_t, lean_t = max(back_t, d["slump_back_amount"]), lean_t * 0.5
        if stretching:
            back_t, lean_t = max(back_t, 0.5), 0.0
        if paused:
            lean_t = back_t = tilt_t = 0.0
        self.lean = self.slew(self.lean, lean_t, dt, d["lean_rise_s"], d["lean_fall_s"])
        self.lean_back = self.slew(self.lean_back, back_t, dt, d["lean_rise_s"], d["lean_fall_s"])
        self.tilt = self.ease(self.tilt, tilt_t, dt, 0.4)
        posture = ("neutral" if paused else "stretch" if stretching else "back" if back_t >= 0.3 else "slump" if slump
                   else "forward" if lean_t >= 0.45 else "upright")

        # -- gaze target (A1, A2, A10..A16)
        if paused:
            yaw_t, pitch_t = 0.0, 0.0
        elif look_cam:
            yaw_t, pitch_t = 0.0, d["camera_pitch_deg"]
        elif look_chat:
            yaw_t, pitch_t = d["chat_yaw_deg"] * self.chat_side, -2.0
        elif reacting and self.react_kind == "think":
            yaw_t, pitch_t = self.react_yaw, d["think_gaze_pitch_deg"]
        elif reacting and self.react_kind == "laugh":
            yaw_t, pitch_t = 0.0, 4.0
        elif stretching:
            yaw_t, pitch_t = 0.0, 6.0
        elif self.target is not None and now < self.target_until:
            yaw_t, pitch_t = gaze_for(*self.target)
        elif state in ("reading", "typing", "mouse"):
            nx = 0.5 + 0.18 * math.sin(now * 2 * math.pi / 3.2 + self.phase_a)
            ny = 0.3 + 0.4 * ((now % 24.0) / 24.0)
            yaw_t, pitch_t = gaze_for(nx, ny)
            yaw_t, pitch_t = yaw_t * d["reading_gaze_gain"], pitch_t * d["reading_gaze_gain"]
        else:
            yaw_t, pitch_t = (d["wander_deg"] * 3 * math.sin(2 * math.pi * d["wander_hz"] * now + self.phase_a) * d["idle_gaze_gain"],
                              d["wander_deg"] * 2 * math.sin(2 * math.pi * d["wander_hz"] * 0.7 * now + self.phase_b) * d["idle_gaze_gain"])
        if slump:
            pitch_t -= 2.0
        tau = d["gaze_tau_s"] * (0.7 if (look_cam or look_chat) else 1.0)
        self.yaw = self.ease(self.yaw, yaw_t, dt, tau)
        self.pitch = self.ease(self.pitch, pitch_t, dt, tau)
        wander_y = 0.0 if paused else d["wander_deg"] * math.sin(2 * math.pi * d["wander_hz"] * now + self.phase_b) * (1.4 if speaking else 1.0)
        wander_p = 0.0 if paused else d["wander_deg"] * 0.6 * math.sin(2 * math.pi * d["wander_hz"] * 1.3 * now + self.phase_a)

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

        return {
            "state": state,
            "gaze_yaw_deg": round(clamp(self.yaw + wander_y, -20.0, 20.0), 2),
            "gaze_pitch_deg": round(clamp(self.pitch + wander_p, -10.0, 10.0), 2),
            "nod_strength": round(clamp(nod, 0.0, 1.0), 3),
            "intensity": round(clamp(inten, 0.0, 1.0), 2),
            "camera": "spectator" if paused else self.camera,
            "motion": {
                "schema": SCHEMA,
                "lean": round(clamp(self.lean, 0.0, 1.0), 3),
                "lean_back": round(clamp(self.lean_back, 0.0, 1.0), 3),
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
