# Stride, cadence and the first-person body (2026-10-23)

The owner's order: the animations must look real. Walking at 1.2 m/s, the step cadence coupled to the speed, foot
contact within 1 cm, no foot slide, no popping, natural transitions, the body visible and plausible in first person.
Commit 5e45c84 had set `WALK_V = 1.2` and played the walk clip at `speed / REF_SPEED`. This note records what that
left (the clip's fixed step at any pace), the gait model that replaces it, the measured clips, and the evidence.

## The gait model (`web/room/gait.js`)

A walking adult lengthens the step and quickens the cadence together, each about with the square root of the speed:
the "walk ratio" (step length over cadence) stays near constant across speeds (Grieve & Gear 1966; Sekiya & Nagasaki
1998, 0.0058–0.0065 m per step/min). `WALK_RATIO = 0.32 m·s` gives a young adult's gait:

| speed (m/s) | cadence (steps/s) | step (m) |
|---|---|---|
| 0.3 | 0.97 | 0.31 |
| 0.6 | 1.37 | 0.44 |
| 0.9 | 1.68 | 0.54 |
| **1.2** | **1.94** | **0.62** |

A walk clip has one step: its planted foot moves back under the hips at its reference foot speed `REF_SPEED` for
`duration / steps` seconds, so `clipStep = REF_SPEED · duration / 2`. Playing it faster or slower changes only the
cadence. The rule in `room.html drive()`, every frame of a walk step at speed `v`:

- **stride share** `s = clamp(step(v) / clipStep, 0.3, 1)`: below the speed whose step is the clip's, the walk blends
  toward the standing pose by `s` (the swing shrinks with `s`; measured on `room_walk`, the planted foot's speed is
  linear in the share, exponent 1.03). The MakeHuman layer (`boy_mh.js pivot()`, the live character) blends from
  `step.stride`; the first rig blends in `room.html strideBlend()`.
- **rate** `timeScale = v / (share · REF_SPEED)`, where `share` is the walk's share of what the mixer blends now
  (`walkShare()`: the stand under it, or the pose it is still fading in from). The foot moving back at
  `share · REF_SPEED · rate` under hips moving forward at `v` stays still on the floor, whatever the blend does.
- The stride is not stretched beyond the clip's: an additive extrapolation (`walk − stand` on top of the walk) was
  measured on `room_walk` at +6 % of stride for a 1.3 cm sole dip at k = 0.3; not worth a bounce. Above the clip's own
  speed the cadence rises instead: `v / clipStep`.

Measured clips (`room_build/kimodo_g12/walk_metrics.py`, H13; the plants and stances re-measured here with the
vendored three.js, `tests/js/gait_check.mjs`):

| clip | plays for | REF_SPEED (m/s) | loop (s) | step (m) | share = 1 from | cadence at 1.2 m/s |
|---|---|---|---|---|---|---|
| `room/mh_mx/room_walk` (Mixamo rig) | the live default (`?char=mixamo`) | 0.714 (v5: 0.675) | 1.267 | 0.452 | 0.64 m/s | 2.65 steps/s |
| `room/boy_m_walk` (ARDY) | `?char=old` | 0.628 (manifest `refFootSpeed`, else `stride` 0.65) | 1.884 | 0.592 | 1.09 m/s | 2.03 steps/s |
| `room/boy_moves` walk (UAL) | `?char=old&motion=ual` | 0.803 (was 0.86 in the code) | 1.333 | 0.535 | 0.89 m/s | 2.24 steps/s |
| `house/assets/first-person/walking` | the house, first person | 1.4 | 1.033 | 0.723 | always (no stand to blend to) | 1.66 steps/s |

So at cruise the ARDY walk is exactly the owner's numbers (0.59 m at 2.0 steps/s). **The live character's `room_walk`
is a short-stepped clip** (0.45 m): at 1.2 m/s it must take 2.65 steps a second, a hurried walk. Nothing in the page
can lengthen its step; a walk captured at ~1.2 m/s for the Mixamo character (baked like the other `room_mx_*` clips)
is the fix, outside this change. In the room's 3.5 m, cruise lasts about a second of any path: most of the walking is
the acceleration, the corners (0.48 m/s) and the stop, which are what the model changes.

### Slide (`tests/js/gait_check.mjs`, the planted foot's travel over a flat-footed stance, no foot IK)

| | the clip's own skate at REF_SPEED | 0.15 m/s | 0.3 m/s | 0.6 m/s | 1.2 m/s |
|---|---|---|---|---|---|
| `room_walk`, this model | 3.6 cm | 3.6 cm | 3.1 cm | 3.4 cm | 3.5 cm |
| `room_walk`, before (full stride at `v / REF`, floor 0.2; the layer's short strides) | | 46.5 cm | 8.2 cm | 3.5 cm | 3.5 cm |
| ARDY walk, this model | 1.8 cm | rolls | rolls | rolls | 1.5 cm |
| ARDY walk, before | | – | 2.9 cm | 1.6 cm | 1.5 cm |

The model adds nothing to a clip's own skate at any pace; what is left is the clip's (H13: every shipped clip skates
2.6–5.4 cm a stance without IK, and `room_walk` has a 5 cm foot pop at its loop seam, frame 38 → 0). The owner's
centimetre needs cleaner loops: that is clip work (`room_build`), not the page's. On the first rig the motion layer's
contact lock (`boy_motion.js feet()`) plants the foot it finds within **1 cm** of the floor (`CONTACT = 0.01`, was 2 cm)
and holds it within 12 cm; the MakeHuman layer has no foot lock, so the live character shows the clip's skate.

A sweep of `REF_SPEED` against the flat-stance slide at 1.2 m/s (`ref_sweep`, this session): `room_walk` 0.65 → 3.7 cm,
0.684 → 3.1, 0.714 → 3.5; ARDY 0.628 → 1.5, 0.65 → 0.7; UAL 0.78 → 1.7, 0.803 → 1.9, 0.86 → 3.2. The differences are
within each clip's own asymmetry (left and right feet differ by 5 %); H13's numbers are used as measured.

## Pops

- **Walk start.** The walk fades in from the stand over 0.4 s; the rate follows the fade's share, so the first steps
  are short and slow and the feet do not skate while the blend fills (`walkShare()`).
- **Turn on the spot → walk** (`halfSteps(false)`): the walk went to weight 1 at once while the stand faded out
  (weights summing to 1.5: the walk's share jumped 0.5 → 0.67). Now the walk fades in from its share while the stand
  fades out; the two sum to 1 throughout. `halfSteps(true)` also re-enables a stand that an earlier fade-out had
  disabled (three.js disables a faded-out action; `play()` alone left it at weight 0, so the first rig turned with full
  strides).
- **Walk → pose** (`startPose`): the stand blended under the walk (short strides as he slowed) was stopped, which set
  the walk's share to 1 in one frame (a 15 cm pop at the feet, the case `boy_mh.js transition()` already bridged with
  `sigma0`). The first rig now keeps that share under the outgoing pose and lets it go over 0.3 s (`posePose`).
- **Walking on, not turning** (`boy_mh.js pivot()`): with shorter strides on his way the layer's "turn about the feet"
  hips offset would have engaged at every corner and snapped back at full stride; it is now for the turn on the spot
  only, and the turn's origin follows his heading while he walks.
- **The get-up hand-over** (`boy_mh.js flow()`, line ~1714: the walk's time set from the clip's phase at rate 1) is dead
  code: `FLOW` is never set (`env.flow()` has no caller since the Mixamo stand-up took over), so it was left as it is.

## The stretch and the chair

`room.html doVariant("stretch")` (the first rig's idle variant, and the act after a long sit) sends the hands 0.54 m
over the shoulders and 0.16 m forward. `overChair()` now lifts any hand or elbow target that falls inside the desk
chair's footprint (`BLOCK[2]`) to 8 cm over its backrest (`CHAIR_TOP = 1.26` over the pivot, where `handOn()` rests the
hand), so the arms rise over the chair rather than through its back. The MakeHuman layer plays no procedural stretch
(its seated stretch is `room_bedtime`'s, part of the unused `flow()`), so nothing changes there.

## First person (`web/house/first_person_body.mjs`)

Before: the body was hidden during any walk (gated "awaiting camera and anatomy review"); when shown it would have
been the arms alone, placed with the group 1.42 m under the camera — 0.3 m too high for a model whose eyes are 1.61 m
up (Head joint 1.453, HeadTop_End 1.725; `EYE_ON_HEAD = 0.58`).

Now, while he is on his feet and the viewer follows him:
- **the body but the head** is drawn (`bodyTriangleIndices`: every triangle without a vertex a quarter weighted to
  Head/Neck/Eye bones; the hood meshes, whose lining faces inward around the camera, are left out), as a second
  skinned mesh per skin bound to the same skeleton (no bone, weight or bind-matrix change; the arms-only meshes stay
  for the seated captures);
- it **stands on the floor** under the camera (`floorAt` from `home.js`), its eyes at the camera by a uniform scale of
  the group (0.9–1.15; the server's eye height is 1.65 m) and its eye point — 12 cm ahead of the Head joint, the face —
  under the camera (`EYE_FORWARD`). Aligning the Head joint itself put the camera inside the skull and the collar: the
  first renders were black slivers (the near plane through the hoodie);
- the **walk's rate** follows the server's `speed` through the same model (`walkRate`: `clipRate(speed, 1, 1.4)`, the
  capture's step kept since there is no standing capture to shorten it toward): 1.66 steps/s at 1.2 m/s, slower steps
  as he arrives;
- **standing still** shows the capture's first frame held (a staggered stance; from the eye a body standing on the
  floor). It never shows under a seated camera (`standingOnly`: seated or at the desk → hidden), so a standing body
  cannot rise into the lowered camera; typing and the phone stay gated as before.

Reviewed headless from the eye (`tools/fp_review.html`, `tools/shots.py`; SwiftShader, 480×360):
`fp_walk_down_t03/06/09.png` (looking 63° down at three phases: the chest, the swinging hands, the legs and the shoes
on the tiles), `fp_walk_steep_t06.png` (80° down), `fp_walk_half_t06.png` (34° down: nothing of the body in view, as
the chest sits behind the eyes until ~60°), `fp_walk_level_t06.png` (level), `fp_idle_down.png` (standing).

## Evidence

- `gait_0.4ms.png`, `gait_0.8ms.png`, `gait_1.2ms.png` (`tools/gait_review.html`): the live character from the side,
  a frame every 0.35 / 0.25 / 0.2 s, top row before (full stride at `v / REF`), bottom row the model. At 0.4 m/s the
  strides are shorter and quicker below; at 1.2 m/s both rows are the same (share 1).
- `fp_*.png`: the first-person views above.
- `tests/js/gait_check.mjs` (new): the model's numbers and the slide table above, on the shipped clips.
- `tests/js/home_first_person_body_check.mjs`: the body less the head, the eye line, the cadence from the speed, the
  feet on the floor, the gates.
- `tests/test_boy_motion.py`, `tests/test_boy_mh.py`: the wiring (the import, `drive()`, `pivot()`, the 1 cm lock).

Not verified here: the full room page in a browser (its three.js comes from a CDN; this session had no network), so
the walk start/stop and the pose hand-overs were checked by reading and by the clip-level simulation, not on screen;
the house page itself (no server); real frame rate (SwiftShader).

## Outside these files

- `life.py WALK_SPEED = 1.3` and `home_world.py`'s 1.25 m/s desired speed: the model walks at 1.3 / 1.25 m/s while the
  room's character walks its own paths at 1.2 m/s. For one pace everywhere both should be 1.2.
- A walk capture at ~1.2 m/s with a 0.6 m step for the Mixamo character (`room_build/kimodo`, baked like
  `room_mx_*`), and clean loop seams for `room_walk` (the 5 cm pop at frame 38 → 0 and its 3.6 cm skate): the owner's
  centimetre is not reachable with the clip as shipped.
- `web/room/boy_m_manifest.json`: `refFootSpeed` / `cycleTime` / `strideLength` for `clips.walk` (H13's spec); the
  page reads `refFootSpeed` first and falls back to `stride`. `web/room/boy_moves_walk.json` (written by
  `room_build/boy_post.mjs`) is read when present; until then the code uses the measured 0.803.
- A relaxed standing capture for the first-person idle, and the arm captures' own reviews (typing, the phone).
