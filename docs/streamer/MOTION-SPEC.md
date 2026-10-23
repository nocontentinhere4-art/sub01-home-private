# Native motion wish-list for SUB-01 at the desk (`motion` extension of the v2 event)

Status: proposal for the Unreal worker, 2026-10-23. Private project. Source of the numbers: ANIMATION-REFERENCES.md
(behaviours A1-A24) and `scripts/streamer_motion.py` (`DEFAULTS`). The agent already produces every field below each
tick; nothing here changes the v2 contract that the pod build accepts today.

## 1. Compatibility

- The v2 event keeps its six required/optional fields (`state`, `gaze_yaw_deg`, `gaze_pitch_deg`, `nod_strength`,
  `intensity`, `camera`). The agent adds one object, `motion`, next to them. `ParseStreamerVisualV2` reads named fields
  only (`TryGet...`), so the current build ignores `motion` and nothing breaks before the native work lands.
- A build that implements this spec reads `motion` when present and falls back to today's behaviour when it is absent
  or malformed (each field independently: a bad `lean` must not drop the whole event). It reports what it applied in
  the receipt (`motion_fields_applied`, a list) so the agent log and the receipt can be compared.
- Freshness, uid, pid, sequence and expiry rules are unchanged; a stale event means idle, spectator, `motion` all neutral.

```json
{"schema":"sub01.private-streamer-visual-event.v2","source":"streamer_agent", "...":"(envelope as today)",
 "state":"talking","gaze_yaw_deg":0,"gaze_pitch_deg":8,"nod_strength":0.3,"intensity":0.7,"camera":"face",
 "motion":{"schema":"sub01.streamer-motion.v1","lean":0.65,"lean_back":0.0,"head_tilt_deg":0.0,
           "look_at_camera":1.0,"look_to_chat":0.0,"hand_left":"gesture","hand_right":"mouse",
           "gesture_strength":0.5,"breathing_rate_hz":0.18,"fidget":"none","posture":"forward"}}
```

## 2. Fields, bone-level meaning, implementation path

Bone names are those the v2 proxy already resolves (exact name, else the bone whose name ends with it): `Hips`,
`Spine1`, `Spine2`, `Head`, `LeftHand`, `RightHand`; the spec adds `Spine` (or the lowest spine bone), `Neck`,
`LeftForeArm`/`RightForeArm`, `LeftArm`/`RightArm` resolved the same way. All offsets are additive local rotations
applied after the clip is evaluated and before the existing head offset, in the same convention as the breathing on
`Spine1`/`Spine2`. Every value is eased on the native side as the gaze is today; the agent sends 4 Hz, the game runs
at frame rate, so the game owns the interpolation (recommended: critically damped or exponential, 0.25-0.4 s).

| Field | Range | Bone-level meaning | Path | Clamp |
|---|---|---|---|---|
| `lean` | 0..1 | Forward pitch of the torso towards the monitor/lens: split `Spine` 40%, `Spine1` 35%, `Spine2` 25%, with `Neck`/`Head` counter-pitching about 60% of the total so the face stays level and keeps looking at the screen (a lean of 1.0 = 9 deg of torso pitch, 5.5 deg of counter-pitch). The pelvis does not move (the pin guard history: nothing may displace the seat). | Procedural, additive, on top of any clip. | 9 deg total |
| `lean_back` | 0..1 | Backward pitch of the same chain into the chair back: `Spine` 50%, `Spine1` 35%, `Spine2` 15%, head counter-pitch 40% (1.0 = 8 deg). When both `lean` and `lean_back` are non-zero the difference is applied (they are never both high in practice). | Procedural, additive. | 8 deg |
| `head_tilt_deg` | -12..12 | Roll of the head about its forward axis, right ear down positive: `Neck` 35%, `Head` 65%. Used by laugh (5-9 deg) and think (6-10 deg). | Procedural, same path as the head sway offset. | 12 deg |
| `look_at_camera` | 0..1 | Weight of a head aim at the `face` camera position (the lens above the monitor: the existing face camera location, aimed back at `Head`), replacing the gaze yaw/pitch target with the lens direction. Aim 2 deg below the lens for perceived eye contact (R6). Blend 0.3 s in, 0.5 s out. The gaze fields in the same event already point there (yaw 0, pitch +8) so a build without this field still looks roughly right. | Procedural: an aim offset computed from the camera transform, applied to `Neck` 30% / `Head` 70%. | the existing +-20/+-10 cap does not apply to this aim; cap the head itself at 35 deg yaw, 20 deg pitch from the clip pose |
| `look_to_chat` | 0..1 | Weight of a head turn to the chat anchor: a point 30 deg to his right of the monitor centre and 5 deg below it, at monitor distance (where a second screen or a phone would sit). This is the part of the turn that the +-20 deg gaze cap cannot carry. Blend 0.3 s in, 0.4 s out. | Procedural aim, `Spine2` 15% / `Neck` 30% / `Head` 55%, so a real turn also moves the shoulders a little. | head 35 deg yaw |
| `hand_left`, `hand_right` | `rest` `mouse` `keyboard` `gesture` | Where each hand is. `keyboard` for both = the typing loop as today; `mouse` right + `rest` left = the sitting loop as today (`SupportedWebsite` has the hands on desk/mouse). `rest` for a hand that is on the mouse in the clip = a per-hand IK pull of the wrist to a desk rest target 12 cm towards the body, fingers relaxed (or a second loop phase). `gesture` = the hand leaves the desk: an additive arm layer (see below) scaled by `gesture_strength`, or a short clip chosen by `fidget`. Per-hand blends 0.3 s. The agent moves the hands 0.3 s before the state changes to `typing`, so the hand placement must not wait for the clip switch. | Clip choice today (two loops), per-hand IK targets for `rest`/`mouse` later, additive layer or short clips for `gesture`. | IK reach 25 cm from the clip pose |
| `gesture_strength` | 0..1 | Amplitude of the free-hand gesture layer: forearm lift (0-25 deg at `LeftForeArm`/`RightForeArm`), small upper-arm abduction (0-8 deg), wrist open, returning to the desk within the agent's gesture window (0.8-1.8 s). While `fidget` names a target (face, headphones, neck, drink) the same hand goes to that target instead. | Procedural first (a two-pose additive), authored gesture clips later. | 25 deg |
| `fidget` | `none` `face` `headphones` `neck` `drink` `stretch` `chair` | Target of the free hand (`face`: chin/cheek, `headphones`: ear cup, `neck`: back of the neck, `drink`: a cup to the right of the keyboard and back, 3-5 s) or a whole-body beat (`stretch`: both arms up and back, 3-6 s; `chair`: a re-seat, handled by `lean_back`). Hand reach targets are fixed points in the character's space (chin, ear, nape, cup) so they need no scene query. | Short authored clips (one per kind, 1.5-5 s, on the live skeleton, same import as the Desk7 clips) blended on the arm chain; until they exist, the procedural gesture layer with the strength given. | one at a time |
| `breathing_rate_hz` | 0.1..0.6 | Frequency of the existing breathing sine on `Spine1`/`Spine2` (today fixed at 0.22). Phase-continuous when the rate changes (accumulate phase, do not restart). Amplitude 0.6 deg as today, 0.9 deg above 0.4 Hz (laugh). Speech breathing is a sawtooth (short in, long out): shape the wave as `sin` raised to 0.6 power on the inhale half when `state` is `talking`. | Procedural, one parameter on the existing layer. | 0.1-0.6 Hz |
| `posture` | label | `upright` `forward` `back` `slump` `stretch` `neutral`: a readable summary for logs and the receipt; nothing to animate. | Receipt only. | - |

Notes
- `intensity` keeps its meaning (scales sway and nod). `nod_strength` is read on entry into `reacting` today; this spec
  asks for it to be read on every event (a small nod while `talking` every 2.5-5 s is the phrase-boundary nod, A13): a
  nod pulse starts when `nod_strength` rises above its previous value by more than 0.1, with the given amplitude, the
  existing 0.75 s shape, and a small upward pre-motion of 20% (R1).
- The reading sweep stays agent-side (gaze yaw/pitch); the head follows it with the existing sway path.
- The `mouse` state plays the sitting loop (no reach clip). `hand_right: mouse` is therefore the default of that loop.

## 3. Priorities: realism per hour of native work

| Rank | Item | Why | Work | Assets |
|---|---|---|---|---|
| 1 | `lean` / `lean_back` on the spine chain with head counter-pitch | Posture is the biggest tell at the webcam framing: leaning in for chat, back for a laugh, sagging after 20 min. Two additive rotations, same path as breathing. | 2-4 h | none |
| 2 | `look_at_camera` aim at the face camera | Eye contact at the right moments is what makes the viewer feel addressed; the gaze cap cannot reach the lens. One aim offset from a known transform. | 2-3 h | none |
| 3 | `breathing_rate_hz` + nod on every event | Cheapest life signs: slower breathing while talking, phrase nods. Parameters on existing layers. | 1-2 h | none |
| 4 | `look_to_chat` aim | The glance to the side and back is the signature desk behaviour of a streamer (A10/A11); without it he never acknowledges the chat with his body. | 1-2 h after item 2 | none |
| 5 | `head_tilt_deg` | Laugh and think read as different reactions only with a tilt. One roll offset. | 1 h | none |
| 6 | Hands: per-hand `rest`/`mouse` IK pull on the sitting loop | Lets the mouse hand leave and return without a new clip; removes the "glued hands" look in long reads. | 4-6 h | none (IK on the existing loop) |
| 7 | Gesture layer (`gesture_strength`) | Talking with a free hand; procedural two-pose additive on the forearm. | 3-4 h | none |
| 8 | Fidget clips (`fidget`) | Face, headphones, neck, drink, stretch: five short clips on the live skeleton. The largest realism step after posture, but it needs authoring/import like the Desk7 clips. | 1-2 days incl. import review | 5 clips |
| 9 | Hand-matched phase for the fidget/gesture return | Avoid the hands popping when a clip ends; reuse the 24-phase matcher. | 2 h | none |

Everything above the fidget clips is procedural on the current clips and needs no new assets. Items 1-5 are a day of
work and cover leaning, eye contact, breathing, nods, the chat glance and the tilt: that is most of what the study found.

## 4. Acceptance (what to check on the pod)

1. Receipt shows `motion_fields_applied` with every field the event carried; a malformed field is listed in
   `motion_fields_rejected` and the rest still applies.
2. Pelvis stays within the existing drift audit (8 cm / 25 deg) with `lean` 1.0 and `lean_back` 1.0 held for 10 s each.
3. Face camera: `look_at_camera` 1.0 puts the head aim within 3 deg of the lens (2 deg below) in the receipt
   (`face_camera_aim_error_deg`), and the hold/decay times are 0.3/0.5 s.
4. Chat glance: `look_to_chat` 1.0 turns the head about 30 deg to his right, shoulders about 4 deg; back within 0.4 s.
5. State changes stay debounced (0.6 s) and the hands switch 0.3 s before `typing` starts (compare event and receipt
   timestamps in `events.jsonl` vs `streamer-visual-receipt.json`).
6. A 10-minute recording with the agent's rhythm (reading, a chat answer, one laugh, one surprise, one think) reviewed
   against ANIMATION-REFERENCES.md section 4: he reads still, glances at chat, answers to the lens, reacts once and
   returns, never leaves the chair.

## 5. Agent side (for reference)

`scripts/streamer_motion.py` is pure (no clock, no files; the rng is injected) and produces the six v2 fields plus
`motion` from: the current action kind, speaking, chat_addressed, reaction kind, seconds in the current state, an
optional screen target and the pause flag. All rates and holds are the one `DEFAULTS` table at the top of the file;
`tests/test_streamer_motion.py` holds them inside the documented ranges over simulated minutes.
