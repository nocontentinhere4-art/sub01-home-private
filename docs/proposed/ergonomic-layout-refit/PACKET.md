# Ergonomic layout refit: SOURCE proposal (`final_candidate`, `source_ready: false`)

**Readiness:** `source_ready: false`, `native_ready: false`, `ready: false`. Six arm gates fail; they are listed below.
This is a proposal. Nothing in the runtime moves, and nothing is installed or pinned. Root integrates it, or not.

**Hand model:** the hand contact is to be redone on root's frozen 65-bone owner,
`docs/proposed/canonical-anatomical-hand-cuffs-source-packet-20261015.json` (sha256 `d1da823e…`, origin/main). No work
was done on the old finger rests. PC, phone and contact are **not** claimed ready.

## The one configuration (old → new)

| Item | Original | Proposed | Delta |
|---|---|---|---|
| Keyboard (home.js) | `furnished("keyboard", 2, 0.846, -2.94, 0.371, 0, …)` | `furnished("keyboard", 2.0000, 0.846, -2.7900, 0.371, 0, …)` | +15.0 cm toward the body (UE +Y, three.js +z); rotation and scale unchanged |
| Mouse + pad (home.js) | `furnished("mouse", 2.4, 0.846, -2.91, 0.22, 0, "/room/mouse.glb")` | `furnished("mouse", 2.4000, 0.846, -2.7915, 0.22, 0, …)` | +11.848 cm toward the body (the pad front stops 2.0 cm inside the edge) |
| Chair typing roll | (3.875, −21.279) cm → chair (203.895, −207.969, 63.1877) | (3.875, **−12.279**) cm → chair (203.895, **−198.969**, 63.1877) | 9.0 cm **less** pull-in than before; the initial transform (measured + 2.5001 lift) is unchanged |
| Body | rolls rigidly with the chair | same; solver→world shift (0, 20.221, 0) cm | seat-relative pose = the anatomical base, unchanged |

- **Keyboard:** case 37.10 × 16.09 × 2.79 cm at X 181.45–218.55, Y −287.046 to −270.954, bottom 84.6 cm. That is a
  0.1 cm float over the 84.5 cm top, which is root's pending foot check; the refit changes X/Y only.
  - Worktop margins: front 4.355 cm for the bottom-support vertices (4.252 cm for the full case), left 47.5, right 67.5,
    rear 50.3 cm. All 44 bottom vertices are on the flat top (the eased edge is under 1 cm).
  - Key field: Y −286.297 to −272.917.
- **Mouse pad:** X 229–251, Y −289.602 to −268.702. Front margin 2.0 cm, rear 47.7 cm. The plan gap to the keyboard
  case is 10.45 cm. Main's palm target moves to (241.2, −274.729, 90.041).
- **Clear of** the grommets, the monitor stand and panel, the lamp and the plant. Everything else on the top is behind
  the devices.
- **Chair:** the complete chair (`chair_owner.glb`, every vertex) is ≥ 20 cm from every desk part along the whole roll
  path. The floor gap is constant at 0.0001 cm, and the roll is exactly reversible.
  - Arm pads: top 69.52 cm, 8.57 cm under the front apron, 51.2 cm from the desk.
- **Body vs desk:**
  - torso ≥ 25.5 cm (gate ≥ 5);
  - legs ≥ 12.6 cm (the knee by the drawer carcass, node 32);
  - main's strong seat rule passes at the new roll, re-measured literally (99 frames).
- **No footrest:** none is needed. The feet are unchanged; root confirmed the base needs none.

**Reversibility:** the original values are in `original` (proposal JSON) and in the table above. Restoring the three
transforms restores the layout exactly. The roll's push-back is the exact time reverse.

## Measured geometry (why the soft targets cannot all hold)

| | Left | Right |
|---|---|---|
| Shoulder (Arm joint) height | 104.5–109.1 cm | 105.0–109.5 cm |
| Shoulder above the 84.5 cm desk top | 20.0–24.6 cm | 20.5–25.0 cm |
| Upper arm / forearm | 28.09 / 23.35 cm | 27.74 / 23.12 cm |
| Sleeve radius, forearm (bind, p90) | 10.3–11.4 cm over the proximal 60 %, 5.5–6.7 cm near the wrist | similar |

- **Upper arm with the elbow at the desk top:** with the elbow exactly at the desk top, the upper arm is already
  **25.8–44.6° from vertical** on every frame (`upper_arm_deg_if_elbow_at_desk_top`). The soft targets "elbow 0–10 cm
  above the desk" and "upper arm ≤ 20°" therefore exclude each other for this rig at this desk.
- **What would meet both:** about +10 cm of seat height (shoulder ≈ 117 cm) plus a 10 cm footrest. That puts the cushion
  at about 64 cm, beyond a standard gas lift, so it is not proposed.
- **Sleeve over the edge:** with a bulky sleeve, the forearm may cross the worktop edge only high (the old 95+ cm
  elbows). The refit therefore brings the keyboard forward so that the wrists sit at or in front of the edge.

## Arm solve (palm/wrist-target mode; every DeskTyping key, 989 frames)

**Method:** `tools/ergonomic_layout_refit.py`, with a non-stretch two-bone IK.

- **The target is a hand frame built without fingers.** The hand frame is placed by the middle MCP: 5.5 cm toward the
  body from D (left) or K (right), 3.5 cm over the key tops. The hand is level and the palm faces down. On the mouse,
  main's palm target is used with the hand pitched 15°.
  - It is blended over the source-ready solve's keyboard/mouse/transit segmentation.
  - The palm motion from the same solve (26b3a8e3) is added, horizontal component only.
  - The hand frame may yaw ≤ 20° and pitch ±10° about the palm point.
- **Swivel:** per frame, the lowest-cost clear swivel. The swivel is then smoothed periodically, and frames that fail
  are pinned.
- **Only Arm, ForeArm and Hand change.** The girdle is as captured: the shoulder elevation equals the capture's on every
  frame.
- **Solution files:** `arm-solution.npz` (arm worlds, swivel, palm targets, hand yaw and pitch) and `per-frame.json`.
  The GLB `SUB01_DeskTyping_seated_refit.glb` (sha256 `b79421b6…`) reads back to within 4e-6 cm.

| | Left (989 keyboard frames) | Right: keyboard (574) | Right: mouse (349) | Right: transit (66) |
|---|---|---|---|---|
| Elbow above the desk top (median) | −4.5 to 13.1 (−0.8) | −3.3 to 18.9 (16.1) | −1.1 to 9.2 (2.8) | −1.8 to 19.9 (10.6) |
| Upper arm from vertical (median) | 17.3–72.0° (29.8°) | 21.7–83.2° (74.6°) | 32.4–66.0° (46.3°) | 32.9–85.6° (64.4°) |
| Wrist flexion, RAW (median) | −12.9 to 15.2° (6.4°); 984/989 in ±15° | −43.4 to 21.2° (−34.9°) | 14.8–20.0° (15.0°) | −42.1 to 18.5° |
| Wrist deviation, RAW (median) | −47.6 to −1.9° (−7.9°); 672/989 in the zone | −66.4 to −9.7° (−63.0°) | −6.7 to 17.4° (−6.2°) | −59.6 to 41.8° |

**Before (same method, original layout):** the elbows were 10.8–17.4 cm above the desk and the upper arm 61–80° from
vertical.

**Clearances, every frame, full arm skin:**
- **Arm vs desk:**
  - upper arm, forearm and hand > 0 on every frame (forearm min 0.417 cm L, 0.285 cm R);
  - 148 L and 140 R frames are under the 0.5 cm design target, but the > 0 gate passes.
- **Other parts:**
  - keyboard case > 0 (min 0.902 L, 0.051 R);
  - complete chair ≥ 3 cm;
  - thighs clear.
- **Own torso (convex-section test):** penetrated on 5 L and 14 R frames, worst −0.043 cm L and −1.178 cm R.
- **Old fingers vs desk:** −1.52 cm. This is reported only, never gated.

## Gates

| Group | Result |
|---|---|
| Devices (support, margins, gaps, items) | pass |
| Body and chair (legs, torso ≥ 5 cm, complete chair along the roll, floor, reversible roll) | pass |
| Seat (main's strong rule at the new roll) | pass |
| Arm vs desk, chair and keyboard case; non-stretch reach; swivel resolved | pass (L and R) |
| **Arm vs own torso** | **FAIL** (L 5 frames, −0.04 cm; R 14 frames, −1.18 cm) |
| **Wrist flexion, raw, in ±15° on every frame** | **FAIL** (L 5 frames, max 15.24°; R keyboard frames down to −43°) |
| **Elbow path continuous (≤ 2 cm per 60 Hz key)** | **FAIL**: swivel jumps up to 26 cm L and 30 cm R where pinned frames break the smoothing (447 L and 273 R pinned) |

The ergonomic soft targets are reported, not gated: elbow band L 26/989 and R 385/989 frames; upper arm ≤ 20° L 12 and
R 0 frames.

## Diagnostic only: the old finger rests

These are known wrong, carried rigidly and never optimised. On the moved keyboard, the over-key gap is −4.41 to 1.51 cm
(L) and −4.23 to 2.76 cm (R). Only 88 L and 11 R keyboard frames fall in the old key gate. **Root redoes the contact on
the frozen new hands.**

**Palm-target envelope for the new hands** (every 10th frame, palm target moved ±1.5 cm Z or ±1 cm Y): every arm
solution resolves except left z −1.5 cm (79 of 99 frames unresolved). A lower palm needs a re-solve.

## Limits, stated plainly

1. **The left arm is close to natural; the right arm on the keys is not.** On the keys the right elbow sits high (median
   +16 cm), with the upper arm at 75° and ulnar deviation of about 63°. It comes in from the side because a lower elbow
   either enters the torso section or puts the sleeve into the worktop edge.
2. **The search grid was coarse:** keyboard +15/+17, chair 0/+3/+6/+9, mouse dx 0/−8, on every 40th frame. The score
   still improved at the grid's edge (+9 cm push-back), so a wider push-back may do better. A bounded refinement may
   follow in a separate commit.
3. **The swivel continuity fails.** A continuous swivel (a path solve rather than per-frame candidates plus pinning) is
   the next step.
4. **The arm-vs-torso test is a conservative convex plan section** of the torso-core skin (≥ 90 % spine weight). Small
   negatives may be concavity fill.
5. **Not done here:** SitToType and TypeToSit (the different roll length and the transitions into this DeskTyping), the
   native collision audit and the new-hand contact.
