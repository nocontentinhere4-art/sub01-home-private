# Native motion spec for SUB-01 at the desk (`motion` extension of the v2 event)

Status: proposal for the Unreal worker, 2026-10-23, revised the same day after the Kimi animation review
(docs/streamer/kimi/animation.md; decisions in kimi/DECISIONS-ANIMATION-STREAM.md). Private project. Items marked **(K)**
come from that review. Source of the numbers: ANIMATION-REFERENCES.md (behaviours A1-A24) and `scripts/streamer_motion.py`
(`DEFAULTS`). The agent already produces every field below each tick; nothing here changes the v2 contract that the pod
build accepts today.

## 1. Compatibility

- The v2 event keeps its six required/optional fields (`state`, `gaze_yaw_deg`, `gaze_pitch_deg`, `nod_strength`,
  `intensity`, `camera`). The agent adds one object, `motion`, next to them. `ParseStreamerVisualV2` reads named fields
  only (`TryGet...`), so the current build ignores `motion` and nothing breaks before the native work lands.
- A build that implements this spec reads `motion` when present and falls back to today's behaviour when it is absent
  or malformed (each field independently: a bad `lean` must not drop the whole event). Its receipt reports what it
  applied with values, not only names (section 5).
- Freshness, uid, pid, sequence and expiry rules are unchanged; a stale event means idle, spectator, `motion` all neutral.
- Schema `sub01.streamer-motion.v1` is frozen for this round. Two additions wait for a `v2` bump together with the parser
  **(K)**: `action_seq` (uint32, increments per new click/scroll, so two identical scrolls are two beats) and `reaction`
  (`none|think|surprise|laugh`, so native starts one envelope on entry instead of inferring the kind from lean and tilt).

```json
{"schema":"sub01.private-streamer-visual-event.v2","source":"streamer_agent", "...":"(envelope as today)",
 "state":"talking","gaze_yaw_deg":0,"gaze_pitch_deg":4.2,"nod_strength":0.24,"intensity":0.7,"camera":"face",
 "motion":{"schema":"sub01.streamer-motion.v1","lean":0.0,"lean_back":0.18,"head_tilt_deg":0.0,
           "look_at_camera":1.0,"look_to_chat":0.0,"hand_left":"rest","hand_right":"mouse",
           "gesture_strength":0.0,"breathing_rate_hz":0.18,"fidget":"none","posture":"upright"}}
```

## 2. Fields, bone-level meaning, implementation path

Bone names are those the v2 proxy already resolves (exact name, else the bone whose name ends with it): `Hips`,
`Spine1`, `Spine2`, `Head`, `LeftHand`, `RightHand`; the spec adds `Spine` (or the lowest spine bone), `Neck`,
`LeftForeArm`/`RightForeArm`, `LeftArm`/`RightArm` and the finger roots, resolved the same way. Finger chain names must
be verified on the live skeleton **(K)**.

Construction rules **(K)**: build every offset as a rotation about **character/component-space axes**, distribute it over
the chain and convert back to local transforms; use quaternions, never independently interpolated Euler angles (bone-
local X is not a portable pitch axis). The agent sends at 4 Hz; the game owns the interpolation with **different
smoothers per layer**: posture about **0.45 s**, voluntary head aim **0.22 s**, the reading head filter **0.8 s**,
reaction onsets **0.08-0.12 s** (native envelopes; the 4 Hz agent cannot draw sub-second shapes).

| Field | Range | Bone-level meaning | Path | Clamp |
|---|---|---|---|---|
| `lean`, `lean_back` | 0..1 each, mutually exclusive | **One signed posture channel (K)**: `s = clamp(lean - lean_back, -1, 1)`; torso pitch `9 deg * s` forward (`Spine` 40%, `Spine1` 35%, `Spine2` 25%) or `8 deg * s` back (`Spine` 50%, `Spine1` 35%, `Spine2` 15%). `Neck`/`Head` counter-pitch about 60% forward / 40% back as an intermediate pose; the residual (3.5 deg at full lean, 4.8 at full back) is **removed by the final head pass** whenever a screen, chat or lens target is active **(K)**. The pelvis does not move (pin guard history). | Procedural, additive, on top of any clip, step 2 of the evaluation order. | 9 / 8 deg total |
| `head_tilt_deg` | -12..12 | Roll of the head about its forward axis, right ear down positive: `Neck` 35%, `Head` 65%. Laugh 4-6 deg, think 4-7 deg **(K)**. | Procedural, same path as the head sway offset. | 12 deg |
| `look_at_camera` | 0..1 | Head aim at the `face` camera (the lens above the monitor). **Aim at the lens itself**: the "2 deg below the lens" rule belongs to eyes, not this head rig **(K)**. Compute the direction from the fixed lens transform; with the framing recipe (section 4) the neutral head-to-lens pitch is about **4.2 deg up**, which is what the agent's `gaze_pitch_deg` carries as the fallback for builds without this field. Blend 0.28 s in, 0.5 s out. Steady-state error **<= 1 deg** after 0.8 s. | Procedural aim from the camera transform, `Neck` 30% / `Head` 70%, step 3. | head 35 deg yaw, 20 deg pitch from the clip pose |
| `look_to_chat` | 0..1 | Head turn to the chat anchor: **20 deg to his right and 4 deg below monitor centre (K)** at monitor distance (where the chat display sits). The agent's gaze fields already carry 20 / -4; the flag selects the distribution `Spine2` **5%** / `Neck` **30%** / `Head` **65%** (about 1 / 6 / 13 deg), so a glance moves the shoulders a degree, not a conversation off-camera. Turn in about 0.25 s, out about 0.35 s. | Procedural aim, step 3. | head 35 deg yaw |
| `hand_left`, `hand_right` | `rest` `mouse` `keyboard` `gesture` | Where each hand is. **Supported set with two full-body clips (K)**: sitting loop = left rest + right mouse; sitting loop + IK = either or both hands at rest; typing loop = both hands keyboard; sitting loop + arm mask = one hand gesture, the other keeping its desk contact. **Not supported**: typing + gesture, left-hand mouse (he is right-handed). The agent moves the hands **0.50 s** before `state` becomes `typing` (two ticks), so the hand placement must not wait for the clip switch; hand preparation is its own channel, not held by the state debounce. | Clip choice today; per-hand contact targets (section 3.2) next. | IK correction < 30 mm normal, fail at 60 mm **(K)** |
| `gesture_strength` | 0..1 | Amplitude of the free-hand gesture layer on the gesture-side `Arm`/`ForeArm`/`Hand`/fingers: forearm lift 0-25 deg, upper-arm abduction 0-8 deg at strength 1, wrist open, back within the agent's window (0.9-1.4 s). The agent sends **0.25-0.45**. For `fidget: desk` the same value sizes the finger motion while the wrist keeps contact. | Procedural two-pose additive first, authored gesture clips later. | 25 deg / 8 deg |
| `fidget` | `none` `desk` (`face` `headphones` `neck` `drink` `stretch` `chair` reserved) | **Only `desk` is emitted today (K)**: a small finger/desk fidget of the free hand, 1.0-1.8 s, wrist in contact, no spine or hips motion. The other kinds have zero agent weight until an authored, contact-checked clip exists for each; a valid-but-unimplemented kind must **fail closed**: hand stays at rest, the request is logged, the generic gesture layer is never substituted **(K)**. Future face/headphone targets are computed after step 3, never from fixed points in unanimated character space. | Procedural (desk); authored clips later (rank 10). | one at a time |
| `breathing_rate_hz` | 0.1..0.6 | Frequency of the existing breathing on `Spine1`/`Spine2` (today fixed at 0.22). **Accumulate phase continuously** `phase = fract(phase + rate * dt)`; never restart on a rate or state change **(K)**. Amplitude 0.6 deg; 0.9 deg above 0.4 Hz. While `state` is `talking` use the first **30%** of the cycle for a smooth inhale and **70%** for the exhale, crossfading wave shapes over 0.6 s; do not raise `sin` to a power (wrong shape, negative-base hazard) **(K)**. | Procedural, one parameter on the existing layer. | 0.1-0.6 Hz |
| `posture` | label | `upright` `forward` `back` `slump` `neutral`: a readable summary for logs and the receipt; nothing to animate. | Receipt only. | - |

Notes
- `nod_strength` is read on every event, not only on entry into `reacting`: a pulse starts when the value **rises through
  the threshold after a rearm at <= 0.02** **(K)**; one 0.75 s envelope per rise, strength 1.0 = 6 deg down, 20% upward
  pre-motion. The agent holds a value for a tick and lets it decay over 1 s, so two equal nods separated by a zero give two
  pulses. There is **no periodic talking nod**: the agent sends a speech-onset nod (0.28) and a chat acknowledgement nod
  (0.24) only. A future prosody nod can read `mouth.json` (the voice envelope, 25 Hz) natively; `voice_playing` has no
  phrase boundaries **(K)**.
- The reading sweep stays agent-side and is already filtered (gain 0.12, +-2 / +-1.5 deg, 0.8 s): a synthetic +-10 deg
  reading sweep must produce no more than 2 deg of head yaw and 4 deg/s of head speed **(K)**.
- Head-target priority **reaction/lens > chat > screen**; native logs a suppressed lower-priority target instead of aiming
  between two **(K)**.
- The `mouse` state plays the sitting loop (no reach clip). `hand_right: mouse` is therefore the default of that loop.

## 3. Native implementation, ranked (K)

Hours include a basic on-pod debug pass for an engineer who knows the animation instance, the 24-phase matcher and UE IK;
they are estimates. Do **not** start rank 10 this week: ranks 1-8 plus a proper desk/mouse/typing slice are already a
sprint, and the complete hand stack (3-5, 9) is 32-44 h on its own.

| Rank | Native work, viewer-visible result | Bones | Driving signal | Hours | Acceptance (frame / log must show) |
|---|---|---|---|---:|---|
| 1 | **Motion kernel, signed posture, head counter-pitch.** Reading, talking and relaxing read as body states, not head offsets. | `Spine`, `Spine1`, `Spine2`, `Neck`, `Head`; `Hips` untouched | `lean`, `lean_back`; `state` only as fallback | 6-8 | full lean 9 +- 0.2 deg torso pitch, full back 8 +- 0.2; extra hips delta <= 0.5 mm / 0.2 deg; simultaneous lean values do not pop; the later head pass removes the residual when a target is active |
| 2 | **Final head-target stack**: filtered screen aim, chat, lens, tilt. A brief chat acknowledgement and a real lens address, no reading bob. | `Spine2` (chat only), `Neck`, `Head` | `gaze_yaw_deg`, `gaze_pitch_deg`, `look_at_camera`, `look_to_chat`, `head_tilt_deg` | 8-10 | lens error <= 1 deg after 0.8 s; chat = 20 +- 1 deg head yaw, -4 +- 1 pitch, about 1 deg `Spine2`; a +-10 deg synthetic reading sweep gives <= 2 deg head yaw and <= 4 deg/s |
| 3 | **Desk/mouse/rest contact calibration on the sitting loop.** No floating wrists, palm through the desk, hand glued to an imaginary mouse. | arm chains, finger roots; shoulders stable | `hand_left`, `hand_right`, `state` | 10-14 | wrist target error p95 <= 5 mm, max <= 10 mm over a 60 s loop; corrective offset p95 < 30 mm, cap 60 mm; no penetration at the webcam angle |
| 4 | **Two-clip reach and return choreography** (section 3.2). Hands lead the body, arc over the desk, settle before typing. | arm chains; `Spine*`, `Head` in the phase-match cost | hands `keyboard` at -0.50 s, then `state: typing`; reversed on exit | 14-18 | hand preparation precedes typing by >= 0.45 s; `hands_ready=keyboard` >= 0.10 s before the first strike; no wrist discontinuity > 10 mm; one body transition per dwell |
| 5 | **Native finger and mouse micro-motion.** Uneven typing bursts, real click and scroll shapes. | finger chains, `Hand`, small `ForeArm` residual | `state: typing`; click/scroll beats (new target / `action_seq` later) | 8-12 | strikes 6-9/s inside 0.8-1.8 s bursts, only while typing; strike down 45-65 ms, release 70-110 ms; click 60/90 ms; no synchronised all-finger motion |
| 6 | **Phase-continuous breathing, robust one-shot nods.** Quiet life signs without a breathing reset or a metronome. | `Spine1`, `Spine2`; `Neck`, `Head` | `breathing_rate_hz`, `state`, `nod_strength` | 4-6 | no phase discontinuity on rate changes; 30/70 split while talking; two equal nods with a rearm between give exactly two 0.75 s pulses; reading gives none |
| 7 | **Think / surprise / laugh envelopes.** Three distinguishable reactions with a static face. | spine chain, `Neck`, `Head`; hands pinned | `state: reacting` + lean/tilt/camera fields (`reaction` after the v2 bump) | 6-8 | surprise reaches 90% of its back pose in 0.18 +- 0.03 s, checks at 0.45 s, shares at 1.15 s, ends at 2.6 +- 0.1; laugh 2.2-3.0 s with two decaying 0.7 deg torso pulses at ~3 Hz; no hand-to-face |
| 8 | **Free-hand gesture and desk fidget layer.** Occasional conversational hand life, a safe idle outlet. | gesture-side arm chain and fingers | `hand_*: gesture`, `gesture_strength`, `fidget: desk` | 8-10 | gesture 0.9-1.4 s within 25 deg / 8 deg maxima, returns within 5 mm / 3 deg; the other hand's contact error unchanged; none accepted during typing or a reaction |
| 9 | **Record and import the third clip** (section 3.3), use its contact/reach segments. | full skeleton recorded; arm/finger layers used | the rank 4-5 signals | 24-32 | start/end contact poses match within 5 mm / 3 deg; markers select segments; the 12 s take never plays as a loop |
| 10 | **Authored face/headphone/neck/drink clips**, later. | arm chains, spine/head layers; cup prop and grasp | `fidget` kinds, one-shot entry/exit | 40-60 | contact-checked begin/hold/end, no penetration or prop teleport; until then the kinds fail closed |

### 3.1 Evaluation order, every frame (K)

1. Base clip and any phase-matched body crossfade. 2. Breathing and signed spine posture in component space.
3. Head tilt and the final screen/chat/lens head aim. 4. Gesture or authored arm mask. 5. Hand IK and contact constraints
against the post-posture body. 6. Finger layer. 7. Debug metrics (section 5).

### 3.2 Convincing keyboard and mouse hands with the two clips (K)

**Calibrate contacts, not generic offsets.** Character/prop sockets for: left and right keyboard wrist aims and palm
orientations; left desk-rest wrist aim; right desk-rest wrist aim; mouse wrist/palm aim; elbow pole positions for
keyboard, desk and mouse. Their XYZ comes from the scene, never from a "12 cm towards the body" rule. Two-bone IK places
the wrist, then the wrist orientation is aligned to the calibrated palm pose, then the fingers; a required correction
over **60 mm** means the clip/prop calibration is wrong and must be fixed, not hidden by a longer reach.

**Sitting -> typing.** At `t = -0.50 s` (the agent's hands `keyboard`): freeze new gestures and fidgets, capture both wrist
transforms, start quintic/minimum-jerk wrist paths to the keyboard contacts with a **30-50 mm arc** so the hands clear the
desk; the left may lead the right by **60-90 ms**. At `-0.28 s`: start the **0.28 s** body crossfade to the typing loop,
arms kept under the reach/contact system so the crossfade cannot drag the wrists. At `-0.15 s`: contacts established,
fingers pre-shaped, `hands_ready=keyboard`. At `0`: typing body state and the native strike scheduler; blend any useful
authored typing arm/finger motion in over about 0.12 s with the pins active.

**What the 24-phase matcher matches.** At the body transition, evaluate the target clip at the 24 phases and take the
lowest body cost, for example `C(p) = (angle_error(Spine2) / 6 deg)^2 + (angle_error(Head) / 5 deg)^2 + 0.25 *
(Spine2_rate_error / (25 deg/s))^2`. No large wrist term: the arms are overridden during the transition. Do not re-phase
continuously afterwards (time-warp shimmer).

**Typing -> reading/mouse.** Stop scheduling strikes at once, let the current one finish within 80 ms; keep both hands on
the keys **0.70 s**; if typing resumes within **1.8 s** never leave the keyboard pose; otherwise the right hand returns to
the mouse over about **0.30 s** and the left to desk rest over about **0.36 s** with shallow arcs; phase-match the sitting
body in the same window; restore the clip's arm influence only after contact has settled.

**Native typing and mouse detail** (visual parameters, not 4 Hz agent updates): bursts 0.8-1.8 s at 6-9 strikes/s,
irregular; intra-action pauses 0.25-0.8 s; fingertip approach 8-14 mm; per strike 4-8 deg at the knuckle, 8-14 deg at the
next joint, wrist <= 1.5 deg; resting finger drift 0.5-1.5 deg over 1.5-4 s (never frame noise); click = index flexion
about 8 deg, 60 ms down / 90 ms up, no arm punch; scroll = 2-4 detents over 0.22-0.45 s, 8-12 deg of the finger, palm on
the mouse; pointer travel only when required, 10-35 mm over 0.18-0.45 s, never continuous while reading. If the typing
clip already has strong finger motion, add a residual and clamp the **combined** angle. Without real key events this is
plausible generic typing, not per-key truth.

### 3.3 The third clip to record (K)

One **12 s desk contact-and-transition take** on the real chair, desk height, keyboard and mouse; hips seated; bake no
lean, nod, gaze, laugh or breathing (those are procedural). 0.0-2.0 s the reading contact pose (right on mouse, left at
rest, shoulders asymmetric but quiet); 2.0-2.9 both hands to the keyboard, left leading 60-90 ms, shallow arcs; 2.9-3.4
settle on home keys, held; 3.4-5.2 one natural burst; 5.2-5.8 stop with hands on the keys (a planning pause); 5.8-6.6 a
second shorter burst; 6.6-7.3 still on the keys; 7.3-8.2 right hand back to the mouse; 8.0-8.9 left back to rest,
overlapping; 8.9-12.0 settle, clean end pose matching the start. Segment markers at reach, contact, pause and return. It
is source material for segments, never a loop. Not another idle loop, not a laugh: reach and settle are the asset gap.

## 4. Webcam framing recipe (K)

A **fixed camera**: no head tracking, auto-framing, pose-dependent zoom or movement between reading and talking. The same
fixed lens transform is the `look_at_camera` target (no feedback loop). Numbers assume adult head proportions and the
posture ranges above; the actual mesh still needs the frame acceptance below.

| Setting | Value |
|---|---|
| Camera distance | 0.95 m horizontally from the neutral eye/face plane (eye distance about 0.954 m) |
| Lens height | 70 mm above the neutral eye line |
| Optical-axis pitch | 10 deg downward (framing pitch, not the head-to-lens angle) |
| Frame, FOV | 16:9; vertical FOV 40 deg (kept as vertical in Unreal) -> horizontal about 65.8 deg, diagonal about 73.2 deg, about a 28 mm full-frame feel |
| Head placement | nose/head centre at 50% of the width; top of head about 20% from the top, eyes 36%, chin 53%, shoulder line 67%; bottom of frame on the upper chest (resting desk hands need not be visible) |
| Head to lens at neutral | `atan(0.07 / 0.95) = 4.2 deg` upward: the `camera_pitch_deg` fallback; not 8 |
| Focus | fixed; the +-9 cm head travel of the extreme poses stays sharp and uncropped |

**Frame acceptance** with the rendered mesh at neutral, `lean 1.0`, `lean_back 1.0`, each with the maximum reaction tilt:
neutral top of head within 18-22%, eyes 34-38%, chin 51-55%; at every extreme the top of head no higher than 14% and the
chin no lower than 60%; head height 29-38% of frame height; both shoulders visible during the 20 deg chat glance; no
reframing between the reading-forward and talking-back poses.

## 5. Acceptance (what to check on the pod)

1. Receipt shows every `motion` field applied **with values** **(K)**: applied torso angle, head target and residual error,
   hand-contact state per hand, IK offset in mm, clip phase, last accepted action/reaction id; a malformed field is listed
   in `motion_fields_rejected` and the rest still applies.
2. Hips: the whole-clip drift audit (8 cm / 25 deg) stays, and in addition toggling the procedural layers at the same clip
   phase changes the hips by **<= 0.5 mm and <= 0.2 deg** **(K)**.
3. Face camera: `look_at_camera` 1.0 puts the head aim within **1 deg** of the lens after 0.8 s (`face_camera_aim_error_deg`),
   blend 0.28 s in / 0.5 s out.
4. Chat glance: `look_to_chat` 1.0 turns the head **20 +- 1 deg** to his right, **-4 +- 1 deg** pitch, about 1 deg of
   `Spine2`; back within 0.35 s.
5. State changes stay debounced (0.6 s native, 0.8 s agent) and the hands switch **0.50 s** before `typing` starts
   (compare event and receipt timestamps in `events.jsonl` vs `streamer-visual-receipt.json`); contact before the first
   visible strike by >= 0.10 s.
6. A scripted **10-minute recording through the actual webcam shot** (not the skeletal view) **(K)** with a long read,
   repeated scrolls, a search, a short wait, a chat answer longer than 8 s, one think, one surprise, one laugh, reviewed
   against ANIMATION-REFERENCES.md section 4: no camera look during quiet reading; no head motion following lines or
   pointer fixations; no state/clip flapping and no hand contact acquired after visible typing begins; no desk, keyboard,
   mouse or face penetration; no procedural face/headphone/neck/drink/stretch substitution; no fixed-period nod, gesture
   or chat/camera cycle; one reaction per event followed by a return to the previous posture; both extreme poses inside
   the frame acceptance; a viewer can tell reading, waiting, answering, thinking, surprise and a small laugh apart without
   facial animation.

What cannot be signed off from documents is the quality of the two clips' hand poses: if the sitting clip has broken
wrist orientation or the typing clip passes through the keys, procedural layering will not rescue it and the third take
(3.3) becomes necessary rather than desirable **(K)**.

## 6. Agent side (for reference)

`scripts/streamer_motion.py` is pure (no clock, no files; the rng is injected) and produces the six v2 fields plus
`motion` from: the current action kind, speaking, chat_addressed, reaction kind, seconds in the current state, an
optional screen target and the pause flag. All rates and holds are the one `DEFAULTS` table at the top of the file;
`tests/test_streamer_motion.py` holds them inside the documented ranges over simulated minutes. Director-side rules
shipped with this revision **(K rules 1-10)**: settle into a read (0.30 forward over 0.55 s, filtered head, no camera);
scroll (0.8 s mouse hold, 0.35-0.70 s target, no lean pulse); silent chat glance (45-105 s, 0.8-1.5 s, none within 8 s of
speech/typing/reaction/page change, none during the scroll); search (hands at -0.50 s, lean 0.40, 0.70 s linger, 1.8 s
pause hold); wait for a page (lean to 0.12, one chat glance after 3 s, no fidget before 25 s); read the message (0.24
forward, chat anchor 1.2-2.2 s); answer (ack nod 0.24, lens 1.4-2.4 s, 0.18 back, one recheck at 5.5-8 s, 0.35 s hold at
voice end); laugh (0.55 back, 4-6 deg tilt, lens at 0.75 s for 0.8 s, hands pinned); bored (after 75 s idle: 0.22 back,
head 4 deg off the screen, one desk fidget, 12-20 s hold, any action cancels); dry comment (no camera, onset nod 0.28,
0.12 back, back to the exact reading posture over 1.1 s).
