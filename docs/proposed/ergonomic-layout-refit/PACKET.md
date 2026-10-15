# Ergonomic layout refit: SOURCE proposal (`final_candidate`, `source_ready: false`)

**Readiness:** `source_ready: false`, `native_ready: false`, `ready: false`. Three right-arm gates fail, by small
margins; they are listed below. This is a proposal: nothing in the runtime moves, and nothing is installed or pinned.
This revision (refinement, 4fca1fd) replaces the first `final_candidate` (1cd44c4). The before/after table is at the end.

**Hand model:** the hand contact is to be redone on root's frozen 65-bone owner,
`docs/proposed/canonical-anatomical-hand-cuffs-source-packet-20261015.json` (sha256 `d1da823e…`, origin/main). That
owner has the same 25 body joints and wrist tracks, with new finger rests, hand geometry and cuffs. No work was done on
the old finger rests. PC, phone and contact are **not** claimed ready.

## The one configuration (old → new)

| Item | Original | Proposed | Delta (UE cm) |
|---|---|---|---|
| Keyboard | `furnished("keyboard", 2, 0.846, -2.94, 0.371, 0, …)` | `furnished("keyboard", 2.0800, 0.8450, -2.7700, 0.371, 0, …)` | (+8, +17, −0.1) |
| Mouse + pad | `furnished("mouse", 2.4, 0.846, -2.91, 0.22, 0, "/room/mouse.glb")` | `furnished("mouse", 2.4000, 0.8450, -2.7915, 0.22, 0, …)` | (0, +11.848, −0.1) |
| Chair typing roll | (3.875, −21.279) → chair (203.895, −207.969, 63.1877) | (3.875, **−6.279**) → chair (203.895, **−192.969**, 63.1877) | 15 cm **less** pull-in |
| Body | rolls rigidly with the chair | same; solver→world shift (0, 26.221, 0) | seat-relative pose unchanged |

Rotation and scale are unchanged for every item. The chair's initial transform (measured + 2.5001 lift) is unchanged.

- **Z −0.1 cm:** the home.js 0.846 m floated 0.1 cm over the 84.5 cm LINEA top. The case bottom and the pad now rest
  on the top (bottom above the top: 0.0 cm). Root confirms this natively.
- **Keyboard:** case 37.10 × 16.09 × 2.79 cm at X 189.45–226.55, Y −285.046 to −268.954, Z 84.5–87.29.
  - Margins: front 2.25 cm (support vertices 2.36), rear 52.3, left 55.5, right 59.5. All 44 bottom vertices are on the
    flat top.
  - +8 cm in X puts the home row (F/J centre) about 1.7 cm right of the body midline, where it was 6.3 cm left of it.
    This is what fixes the right arm.
- **Mouse pad:** X 229–251, Y −289.602 to −268.702. Front margin 2.0 cm. The plan gap to the keyboard case is 2.45 cm
  (minimum 1.0). Main's palm target moves to (241.2, −274.729, 89.941).
- **Clear of** the grommets, the monitor, the lamp and the plant (all behind the devices).
- **Chair:** the complete chair is ≥ 20 cm from every desk part along the whole roll. The floor gap is constant, the roll
  is exactly reversible, and the arm pads are 57 cm from the desk.
- **Body vs desk:**
  - torso ≥ 30 cm (gate ≥ 5);
  - legs ≥ 14.9 cm;
  - the chair stays in front of the knee bay;
  - main's strong seat rule passes at the new roll (99 frames, literal re-measure).
- **No footrest** is needed; the feet are unchanged.
- **No keyboard yaw:** it was not tried. The verifier supports rigid translation only, and the +X move removed the need.

**Reversibility:** the original values are in `original` (proposal JSON). Restoring the three transforms restores the
layout exactly. The roll's push-back is the exact time reverse.

## Arm solve (palm/wrist-target mode, 989 DeskTyping keys)

**Method:** `tools/ergonomic_layout_refit.py`.

- **Hand frame without fingers:** the middle MCP is 5.5 cm toward the body from D (left) or K (right), 3.5 cm over the
  key tops. The hand is level with the palm down. On the mouse, main's palm target is used with the hand pitched 15°.
- **Adaptation:** about the palm point, the hand frame turns its neutral (bind forearm) axis toward the forearm, by at
  most 20° of yaw and ±10° of pitch. This is smoothed in time with σ 0.15 s, and the palm motion with σ 0.067 s.
- **Swivel:** a CONTINUOUS path by dynamic programming over every frame.
  - Candidates run from −120° to 120° in 5° steps.
  - Each node must clear the desk (≥ 0.5 cm), the chair, the keyboard case, and the own torso and thighs (convex section,
    ≥ 1 cm solver margin).
  - The transition penalty is steep above an elbow step of 2 cm per key.
- **Only Arm, ForeArm and Hand change.** The shoulder elevation is the captured one on every frame.
- **Outputs:**
  - `arm-solution.npz`: arm worlds, swivel, palm targets and hand yaw/pitch;
  - `per-frame.json`;
  - `SUB01_DeskTyping_seated_refit.glb` (sha256 `f4f132f1…`).

| Raw angles, no added corrections | Left, keys (989) | Right, keys (574) | Right, mouse (349) | Right, transit (66) |
|---|---|---|---|---|
| Elbow above the 84.5 top: range (median) | −2.2 to 2.3 (−0.2) cm | −0.7 to 12.6 (0.4) cm | −0.1 to 9.7 (2.3) cm | −0.5 to 14.5 (9.5) cm |
| Upper arm from vertical: range (median) | 29.0–43.5° (39.0°) | 27.8–67.2° (34.8°) | 38.8–61.7° (45.8°) | 36.1–74.3° (60.5°) |
| Wrist flexion: range (median), frames in ±15° | 0.3–10.2° (4.3°), 989/989 | −17.1 to 11.0° (0.8°), 560/574 | −3.0 to 16.4° (11.5°), 266/349 | −22.9 to 11.3°, 56/66 |
| Wrist deviation: range (median) | −19.8 to −4.9° (−9.8°), all in the zone | −47.7 to 3.9° (−18.5°), 341/574 | −0.5 to 13.1° (3.6°) | −39.2 to 15.4° |
| Elbow max step per key | 1.51 cm | 2.06 cm (the DP measured 1.999) | | |

**Clearances, every frame, full arm skin:**
- **Arm vs desk, non-finger:** > 0 on every frame (forearm min 0.293 L, 0.234 R).
- **Other parts:** keyboard case ≥ 1.03 L / 0.59 R; complete chair ≥ 3; thighs clear.
- **Own torso:** L ≥ 0.96 cm; **R −0.145 cm on 5 frames**.
- **Old fingers vs desk:** −1.52 cm. This is reported only, never gated.

**Envelope for the new hands** (palm target ±1.5 cm Z or ±1 cm Y, every 10th frame): all resolve except left z −1.5
(24 frames unresolved) and right z −1.5 (1 frame).

## Transitions for the new layout (new GLBs, in the proposal's `proposed.clips`)

- **What they are:** the base transition body (unchanged), with the chair on the new roll: a quintic pull-in over
  SitToType and the exact push-back over TypeToSit, using `chair_translation_per_frame_cm`.
- **Arms:** the six arm bones' local rotations are slerped with the same s, from the base arms (the SeatedIdle seam) to
  the refit DeskTyping's first / last frame. Then the existing transition desk pass runs on the non-finger arm skin, with
  the wrists out of the parts, never pushed down, and tapering to zero at both seams.

| Clip | sha256 | Seam to DeskTyping (arm joints) | Arm vs desk (non-finger), body, chair, case | Wrist moved by the desk pass (L / R) |
|---|---|---|---|---|
| SitToType | `0a62bdbb…` | 0.032 cm | pass on every frame (desk min 1.885 L / 0.856 R) | 0 / 1.69 cm |
| TypeToSit | `21807715…` | 0.038 cm | pass on every frame (1.071 / 0.800) | 3.68 / 11.33 cm |

The old 22 cm seams came from pairing the baseline transitions with the new layout; with these clips they are 0.03–0.04 cm.

## Gates

**Pass:**
- devices, including the Z rest;
- body and chair;
- seat (main's strong rule);
- both arms vs desk, chair and keyboard case;
- non-stretch reach on every frame (max 0.996 R);
- swivel resolved;
- left own body;
- left raw wrist flexion within ±15° on every frame;
- left elbow path continuous;
- both transitions clear.

**FAIL:**
1. `right_arm_clear_of_own_body`: 5 frames at −0.145 cm. The solver used a 1 cm margin on stride-3 skin; the full skin
   finds this.
2. `right_wrist_flexion_raw_within_soft_zone`: 14 keyboard, 83 mouse and 10 transit frames outside ±15° (worst −22.9°
   transit, 16.4° mouse, −17.1° keys).
3. `right_elbow_path_continuous`: max 2.06 cm per key, against the 2.0 bound.

**Soft targets (reported, unchanged):**
- Upper arm ≤ 20° holds on 0 frames. It is geometrically incompatible with the elbow band at this desk: with the elbow
  at the top, the upper arm is already 25.8–44.6° from vertical, because the shoulder sits only 20–25 cm above the
  84.5 cm top and the upper arm is 28 cm long.
- Elbow band: L 206/989 frames, R keys 330/574.

## Diagnostic only: old finger rests (known wrong, never optimised)

Over-key gap −4.40 to 1.44 cm (L), −3.68 to 4.42 cm (R). Only 23 L and 13 R frames fall in the old key gate. Root
redoes the contact on the frozen new hands.

## Right-arm diagnosis (why 1cd44c4 was worse)

- **Keyboard X:** the 75% keyboard's home row sat 6.3 cm left of the body midline. The right hand (K at x 200) had to
  come 20 cm inward from the shoulder (x 220). The forearm then crossed the key rows at 45–65°: deviation −63°, the
  elbow raised, the upper arm at 75°.
- **Mouse/key alternation:** the right hand alternates between the mouse and the keys. Per-frame swivel picks with
  pinning jumped 30 cm.
- **Hand axis:** the right hand's wrist→MCP line sits about 15° off its neutral forearm axis at bind. The adaptation
  used it, so it pitched the hand the wrong way.
- **What fixed it:** keyboard +8 cm in X, a 15 cm push-back (room for the elbows between the belly and the edge),
  adaptation about the neutral axis, and the DP path.

## Before → after

| | 1cd44c4 | This revision |
|---|---|---|
| Right keys: elbow / upper arm / flexion / deviation (medians) | +16.1 cm / 74.6° / −34.9° / −63° | +0.4 cm / 34.8° / 0.8° / −18.5° |
| Left keys: elbow / upper arm / flexion (medians) | −0.8 cm / 29.8° / 6.4° | −0.2 cm / 39.0° / 4.3° (989/989 in ±15°) |
| Elbow max step per key, L / R | 26.3 / 29.9 cm | 1.51 / 2.06 cm |
| Torso intersections, L / R | 5 / 14 frames (−0.04 / −1.18 cm) | 0 / 5 frames (— / −0.145 cm) |
| Transition seams | 22.3 cm (baseline clips) | 0.03–0.04 cm |
| Device float | 0.1 cm | 0.0 cm |

## Limits

- **Search:** a coarse grid on every 40th frame. Keyboard +15/+17 in Y and 0/+4/+8 in X; chair 0 to +18 in steps of 3
  (+15 kept, because +18 made the mouse unreachable at full frame rate); mouse X 0/−8.
- **Not done:** the arm-vs-own-body test is a conservative convex plan section; the native collision audit; the
  new-hand contact; SitToType/TypeToSit hand contact.
