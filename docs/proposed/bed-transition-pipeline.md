# Bed transitions: lie down, sleep loop, get up (proposal; private)

**Status (14 October 2026): corrected clips ready for root's import, NOT accepted.** The lie-down and get-up are
labelled `derived_library_asset` (not refused, not called mocap) and corrected under labels. The sleep chain is
continuous at 15 cm/s peak joint speed. The native mattress is still unmeasured, and no placement or runtime is
verified.

Nothing here ran on the server, in Unreal or in Blender. No result was viewed in the engine. No runtime receipt
exists, and nothing here claims a visual match or an accepted bed.

## 0. What changed since b7b099b (owner direction)

| b7b099b (raw stage) | now |
|---|---|
| LieDown/GetUp `ProvenanceUnverified`, refused | labelled **`derived_library_asset`**: preview/mh-motion clips retargeted via `mh_retarget.mjs`; capture method undocumented. The verbatim quotes and hashes stay in every report. |
| GetUp: 79 cm seated slide, 184 cm/s, 762 cm/s² | slide held; 63 cm/s, 370 cm/s² (§2) |
| LieDown starts mid-walk at 66 cm/s | trimmed to the last planted standing frame and eased in from rest (§3) |
| soles 3.3 / 4.8 cm (GetUp end), 4.3–12.2 cm (LieDown start) | 0.001–0.08 cm, at least 213 plantar vertices per foot, no penetration (§4) |
| Sova blend 204 / 231 cm/s, gaps 58 / 82 cm | settle 15.1 cm/s, gap into the get-up 0 cm (§5) |
| two different bed placements | one shared rigid placement (§6) |
| movement off in bed, no root path | mesh root-motion install step (§7) |

## 1. Files

| file | role |
|---|---|
| `tools/bed_transition_corrections.py` | **New.** Slide hold, walk-in trim and ease-in, floor reference, leg IK, sleep loop and settle, alternatives, labelled GLBs, reports. |
| `tools/unreal_bed_root_motion.py` | **New.** The native movement proposal: an install step after `unreal_life_clips_runtime.py`, path staging, and a config with visible labels. |
| `tests/test_bed_transition_corrections.py` | **New.** 19 tests: synthetic, staged-source anchors, the inventory label, and real data. |
| `tools/bed_transition_pipeline.py` | b7b099b raw stage. Its provenance now carries `label`. A `derived_library_asset` verdict must lead with the label and may not claim capture. |
| `tools/inventory_native_life_clips.py` | **Additive** `--derived ROLE=PATH`. See §8. |
| `tools/unreal_bed_surface_audit.py`, `tools/fit_bed_placement.py` | Additive. The audit also measures the duvet top and its material slot; the fitter gains `--support duvet`. |
| `docs/proposed/bed-transition/SUB01_{LieDown,SleepLoop,GetUp}.corrected.{in_place,travel_in_hips}.glb` | **The corrected clips** (0.09–0.52 MB each). PRIVATE. Each one carries `asset.extras.sub01_provenance` and `sub01_labels`. |
| `docs/proposed/bed-transition/SUB01_{Role}.corrected.report.json` | One report per clip, raw vs corrected. |
| `docs/proposed/bed-transition/SUB01_bed_mesh_root_paths.json` | The per-frame mesh root path of all three clips, in one frame. |
| `docs/proposed/bed-transition/SUB01_{LieDown,GetUp}.{in_place,travel_in_hips}.glb`, `SUB01_*.report.json` | The raw stage, kept for comparison (superseded). |

| corrected clip (in_place, to import) | frames / s | sha256 |
|---|---|---|
| `SUB01_LieDown.corrected.in_place.glb` | 462 / 15.37 | `5aa10162601b160cbf75f4d1ef3ce259fab3f1fd1600490787be4a51332a613a` |
| `SUB01_SleepLoop.corrected.in_place.glb` | 59 / 1.93 (loops) | `f6dafbff7a2e04dd5d72c2c0155dfd40f7a9cf8d2bd46aded6ab819eaca498cc` |
| `SUB01_GetUp.corrected.in_place.glb` | 367 / 12.20 | `256142f9c84c0813d64b0a57aff8cf092c6fe20831600cc48cc0e3be8896a76e` |

The run is deterministic: `python3 tools/bed_transition_corrections.py docs/proposed/bed-transition --work /tmp/bed-c`.

**Labels:**
- **LieDown:** `retargeted`, `walk_in_trimmed`, `ease_in_retime`, `leg_ik_floor_contact`, `sleep_settle_blend`,
  `lie_down_truncated`.
- **SleepLoop:** `retargeted`, `seated_slide_removed`, `lying_segment_of_get_up_source`, `sleep_loop_seam_blend`.
- **GetUp:** `retargeted`, `seated_slide_removed`, `head_trimmed_to_loop_start`, `cropped_before_walk`,
  `leg_ik_floor_contact`.

## 2. Get-up: the seated slide (removed)

**Window, measured:** 4.80 to 6.23 s (frames 144 to 187).
- Peak 183.9 cm/s at 5.40 s, at sitting height (torso ≤ 45° from vertical, not standing).
- Both feet are up to 41 cm off the floor during the run.

**Why it is an artefact, not a scoot:**
- The lie-down sits on the bed edge and lies down **30.8 cm** further in.
- The raw get-up lies **105.2 cm** from its own seat.
- After the hold it is **30.9 cm**, matching the lie-down.

**Method:**
- The hips' horizontal position is held through the window: the captured displacement inside it is subtracted,
  smoothed with a Gaussian of σ = 4 frames.
- Rotations and the vertical path are untouched.
- The frames after the window keep their captured path, offset by the removed 76.8 cm.
- The travel is removed, not redistributed: no step of the feet carries it, and the native walk does the leaving.
- Hips travel inside the window: 90.3 cm raw, 24.1 cm corrected (sitting-up sway).

**Root path to the standing crop** (component frame):

| | raw | corrected |
|---|---|---|
| path / net | 183.7 / 110.0 cm | 118.3 / 39.2 cm |
| max speed | **183.9 cm/s** at 5.40 s | **63.2 cm/s** at 4.20 s (sitting up, before the window) |
| max acceleration | **761.8 cm/s²** at 5.17 s | **369.8 cm/s²** |
| largest one-frame step | **6.16 cm** | **2.12 cm** |
| discontinuity (> 10 cm/frame) | none | none |

## 3. Lie-down: walk-in hand-off (stand-still start)

The adapter walks to the approach (`WalkToBed`, which stops within 12 cm) and then turns in place, so the clip
starts from a **stand-still**. The source starts at 20.5 cm/s and reaches 70 cm/s at 0.4 s, mid-walk.

**Trim:** to the last standing frame with both feet planted, before he sits.
- Rules: the verifier's standing rule (torso ≤ 30°, leg extension ≥ 0.85 × rest); both foot joints ≤ 20 cm/s and
  within 3 cm of their standing minimum.
- Result: **frame 44 (1.47 s)**, hips 45.7 cm/s.

**Ease-in:**
- The first 0.5 s of playback is time-warped, u = t²/2R. Only captured poses are used (slerp between neighbours).
- The clip now starts at **1.6 cm/s** (central difference; 0 by construction).

**Residual against the native clips** (hips-relative pose at the start frame, best frame of each):

| reference | max joint | RMS | worst |
|---|---|---|---|
| native Walk `web/house/assets/first-person/walking.glb` (best frame 1) | 37.9 cm | 23.9 cm | fingers |
| Idle candidate `stand_idle_ual_ik.glb` (best frame 9) | 51.4 cm | 24.2 cm | fingers |

The renderer's own crossfade covers this pose residual. There is no speed residual (both are at rest).

**Root path, raw → corrected:**
- path: 192.1 → 126.6 cm
- max speed: **70.1 → 40.3 cm/s**
- max acceleration: **225.3 → 199.0 cm/s²**
- largest step: **2.34 → 1.34 cm**

## 4. Foot contact (standing phases)

**Floor reference:** the source floor sits off y = 0. One constant vertical hips shift per clip puts the lower foot
of the planted standing run on y = 0:
- LieDown: −1.98 cm.
- SleepLoop and GetUp: −5.67 cm (one placement).
- The lying body therefore drops 3.7 cm inside the 2.5 s settle.

**Leg IK:**
- Tool: `leg_ik_life_clip.correct`, imported unchanged. It is an analytic two-bone IK with the captured knee plane,
  the captured world foot orientation and a bounded vertical root support.
- Scope: only the run of frames where both feet are planted. The boundary correction fades out over 8 frames.
- Contact is measured with root's plantar rule (`verify_life_idle_candidate.sole_selection`).

| | lowest plantar vertex, left / right | plantar vertices in 0..+1 cm (min) | verdict |
|---|---|---|---|
| GetUp end, raw (last 0.2 s) | 3.28–3.41 / 4.84–5.37 cm | 0 / 0 | fail |
| GetUp end, corrected (14 frames) | 0.001 / 0.001–0.078 cm | 213 / 247 | **pass** |
| LieDown start, raw (first 0.2 s) | 4.29–12.23 / 1.20–1.31 cm | 0 / 0 | fail |
| LieDown start, corrected (7 frames) | 0.001 / 0.001 cm | 263 / 252 | **pass** |

**IK side effects:**
- Root support: 2.35 cm (GetUp) and 2.02 cm (LieDown), against a bound of 3 cm.
- Knee plane change: 3.5° and 1.0°.
- Foot world orientation change: 0°.
- No penetration on any frame.

## 5. Sleep continuity: the options measured, the choice

**Method, the same for every option:** a settle in which the lie-down is held at a captured, still lying frame (it
is truncated there) and the loop advances, with a smootherstep (C2) weight. The peak is the max joint speed
(hips-relative, the b7b099b measure), with the world speed in brackets.

| option | gap | 1.5 s | 2.0 s | 2.5 s | window for ≤ 40 cm/s |
|---|---|---|---|---|---|
| **(chosen)** loop from the get-up source's own captured lying-still head | 19.3 cm | 24.3 (15.8) | 18.5 (12.0) | **15.1 (9.5)** | already |
| Mixamo Laying_Sleeping (v5, via mh_retarget + bed_fit) | 45 / 44 cm | 64 / 64 | 48 / 49 | 38.0 / 40.4 | 2.5 s |
| Sova sleep_back (b7b099b's choice) | 86 / 84 cm | 148 / 145 | 111 / 109 | 89 / 87 | 5.6 s |
| Sova sleep_side | 78 / 82 cm | 125 / 131 | 94 / 98 | 75 / 79 | 4.9 s; also a side ↔ back flip |

**(a) Broader search.**
- Every Sova loop, the Mixamo lying loops and the get-up's own lying frames were tried.
- The lie-down may be truncated at any still lying frame; the get-up may start later than its first frame.
- The Sova loops have the right arm over the head, while every lie-down and get-up lying frame has it at the side.
  That is ~85 cm at the fingertips, which no 1.5–2.5 s window brings under 40 cm/s.
- The Mixamo loop only reaches 38–40 cm/s at 2.5 s. Its v5 file also carries the documented "lift and raised fists"
  of the retarget/bed-fit chain (`docs/design/mixamo/README.md`).

**(b) Long captured-pose interpolation:** this is the settle above, at 1.5 / 2.0 / 2.5 s.

**(c) Sova intermediate poses:** no Sova clip passes through an arms-at-side pose. `sleep_roll_to_back` rolls
side → back with the arm moving up. So no captured Sova settle exists for these clips.

**Chosen: `SleepLoop` = the get-up source's own captured lying-still head.**
- Frames 12–70, all moving < 10 cm/s, with the seated slide removed.
- Closed with `leg_ik_life_clip.seam_blend` over 12 frames (0.4 s); the captured gap before the blend is 0.78 cm.
- Label: `lying_segment_of_get_up_source`. It is a captured lying-still segment; no breathing is documented for it.
- Settle (end of LieDown): 2.5 s, from lie-down frame 386 (eased timeline) into loop phase 41 → 0, pose gap 19.3 cm.

**Peak joint speed** (hips-relative):

| | peak |
|---|---|
| settle | **15.1 cm/s** (world 9.5) |
| loop's own speed | max 8.1, median 1.5 cm/s |
| lie-down → loop seam | 2.1 cm/s |
| loop → get-up seam | 2.1 cm/s |
| raw b7b099b Sova blends | 204 and 231 cm/s |

**Seams:**
- LieDown end = loop start: pose 0 cm, hips 0 cm, velocity mismatch 1.7 cm/s.
- Loop end = GetUp start: pose 0 cm, hips 0 cm, velocity mismatch 1.7 cm/s.
- The get-up side needs no blend: the get-up starts at frame 12 of its source, which is the loop's start pose.

**Trade-off, stated plainly:**
- The chosen loop is a 1.93 s still-lying segment, supine with arms at the side. It is not a Sova sleeping pose.
- The Sova loops remain usable only with a captured arm settle, or a 5–6 s settle the owner did not ask for.

## 6. Placement (the bed is NOT measured)

The loop and the get-up are the same captured frames, so **one rigid placement** now serves the LieDown's last
frame and the GetUp's first frame. The b7b099b clips needed two different yaws (−58.7° and 167.7°).

**Synthetic dry run** (`fit-dry-run-synthetic/*-corrected-*.json`, a flat 152 × 203 cm top at 60 cm; it is NOT the
native bed):
- With `--lateral-offset-cm 50` both proposals pass with the same transform: yaw −56.66°.
- LieDown start hips: 27.6 cm outside the edge.
- GetUp end hips: 5.1 cm outside the edge.
- Centred (offset 0), both floor frames land over the mattress: he lies ~30 cm in from the edge, as captured.

**Consequence for the capsule:**
- The capsule radius is 16 (`InitCapsuleSize(16, 91)`), and the coordinator states 17 / 92.
- The capsule cannot stand where the body's hips end. So the mesh root motion's return stops at the bed's
  collision.
- A residual of at most 20 cm is absorbed by the first native steps (§7). The placement audit must measure it.

### Root's measurement run (server, exact)

```
UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_bed_surface_audit.py" -unattended
#   expect: SUB01_BED_SURFACE_AUDIT <project>/private-audit/native-bed-surface.json
python3 tools/unreal_life_clips_runtime.py check-bed <project>
#   expect: "BedPlacementMissing" (was "BedUnmeasured")
for off in 30 40 50 60; do
  python3 tools/fit_bed_placement.py <project>/private-audit/native-bed-surface.json \
    docs/proposed/bed-transition/SUB01_LieDown.corrected.travel_in_hips.glb --lateral-offset-cm $off \
    --approach-side <left|right> --work /tmp/bed-fit --out <project>/private-audit/bed-fit-lie-$off.json
  python3 tools/fit_bed_placement.py <project>/private-audit/native-bed-surface.json \
    docs/proposed/bed-transition/SUB01_GetUp.corrected.travel_in_hips.glb --frame 0 --floor-frame last \
    --lateral-offset-cm $off --approach-side <left|right> --work /tmp/bed-fit --out <project>/private-audit/bed-fit-up-$off.json
done
```

**Pick the offset where:**
- both runs report `proposal_ok: true` and the same `transform`;
- the GetUp's `approach.distance_from_edge_cm` is the largest, at ≥ 16 + 4 cm if possible;
- below that, the return ends short by (20 − distance) cm and is absorbed (§7);
- the gap is never > 20 cm (that would block).

Also read the live `FirstPersonBody` relative transform (capsule offset, `HandsMeshRotation`). The fitter's
`component_to_actor` is unknown here.

### Duvet handling (recommendation)

The bed's duvet (`blue_fabric`, 0.51–0.70 m in the asset) is a rigid mesh over the mattress, so a sleeping body
intersects it.

**Recommended: hide the duvet during the bed phases** (LyingDown, Asleep and GettingUp) by setting the bed
component's duvet material slot to a masked, invisible material. Restore it after.
- The audit now records the slot index (`duvet_sections[].material_slot`).
- The support is then the measured cream mattress top, as the fitter assumes by default.
- It is a reversible material state, not a geometry edit. It is not implemented in an adapter yet; it needs the
  bed component reference from the audit.

**Alternative, if the duvet must stay visible:** he lies ON the duvet. The audit now measures the duvet's upward top
(`duvet_sections[].top_surface`: band 12 cm, |n_z| ≥ 0.8). Run the fitter with `--support duvet`, so the back patch
is fitted to the duvet top instead of the mattress.

Never deform or swap the duvet without a measurement. The web room built its duvet over his skin, which is not
available natively.

## 7. Native movement: mesh root motion, capsule at the bedside (`tools/unreal_bed_root_motion.py`)

This is a new install step, applied **after** `unreal_life_clips_runtime.py install`. Its four anchors are the
life adapter's own installed text, and each must be unique:
- fields before `FSub01LifeMachine LifeMachine;`;
- `LoadLifeRootPath();` before `SUB01_LIFE_READY`;
- `UpdateLifeRootMotion(Instance);` after the movement lock and before the head camera;
- two one-line changes:
  - `LifeMovementLocked()` also holds while the capsule returns;
  - the life LIVE_GATE does not zero the capsule's velocity during the return.

Tests check the anchors on freshly staged main sources (`stage_unreal_home_runtime.stage`), and coexistence with the
seat adapter in three orders.

**Behaviour:**
- **LyingDown:** the capsule stays where TurnInPlace left it, which is the approach point. The body mesh's relative
  location is `HandsBaseOffset + root path(t)`, with t the time the hands proxy actually evaluated
  (`LifeEvaluatedTime`).
- **Asleep:**
  - The body is world-anchored.
  - The invisible capsule (the camera is on the head bone) walks by `AddMovementInput` on the floor to the GetUp's
    measured end point (27.1 cm from the approach for these clips), at ≤ 70 cm/s. CharacterMovement collides as
    usual.
  - The mesh offset is recomputed every tick, so the body does not move.
- **GettingUp:** the mesh offset follows the GetUp path. At its last frame the body stands over the capsule (offset
  ≤ 2 cm), and the mesh returns to the renderer's own offset.
- **Bed collision:** if the bed stops the capsule ≤ 20 cm short, the residual offset decays linearly with the
  distance the capsule then walks natively, over 60 cm. That is ≤ 0.33 cm of foot slide per cm walked, logged as
  `SUB01_LIFE_ROOT_RETURN_SHORT`.
- **Blocked:** if the capsule stops more than 20 cm short, movement stays locked and `SUB01_LIFE_ROOT_RETURN_BLOCKED`
  is logged. The body never snaps.
- **Yaw:** actor yaw is held (`bUseControllerRotationYaw` off) while the path is active.

**Never:** `SetActorLocation`, teleport, an actor transform, or bone writes.

**Refusals:**
- Without `<project>/private-audit/native-life-root-paths.json` or with a mismatching one (schema, or sample count
  vs the imported clip's play length): `SUB01_LIFE_ROOT_MOTION_REFUSED`, and the 67af5f8 behaviour is unchanged.
  Do not validate the bed roles then: in-place clips would lie down on the spot.
- If the body is not on the capsule: also refused.

**Assumption to check in the engine:** the renderer's `HandsMeshRotation` makes the owner's rest facing equal the
actor's +X. The component-frame path relies on it. Check it on the first run: the logged `SUB01_LIFE_ROOT_BEGIN`
origin must match the capsule at the bedside, and the body must not walk sideways.

## 8. Provenance label (inventory)

**`inventory_native_life_clips.py --derived ROLE=PATH`** (additive and commented; the default output is
byte-identical):
- The row's provenance is `derived_library_asset`.
- It becomes a `Candidate` **only** if the GLB carries `asset.extras.sub01_provenance.label ==
  "derived_library_asset"`. Otherwise the verdict is `ProvenanceLabelMissing`.
- The row keeps `provenance_label`, and the verdict reason starts with `derived_library_asset (label visible; not a
  capture)`.
- It is deliberately not in `accepted_provenance`.

**`unreal_bed_root_motion.py config`** writes life's config fragment plus one comment per bound derived clip:
`; SUB01 provenance <Role>=derived_library_asset (...): preview/mh-motion clips retargeted via mh_retarget.mjs;
capture method undocumented`.

### Provenance (verbatim-checked quotes; hashes)

| file | sha256 |
|---|---|
| `web/room/mh_v5/room_bed_lie.glb` | `61e881220a646f37f6b52d09f05919188c159ddf89f658d274f2a4501f871e94` |
| `web/room/mh_v5/room_bed_wake.glb` | `aa5935e33f377204549b25a31747c3ad168707747ac703e451fed30557c96f49` |
| `web/room/char_mixamo.glb` (owner) | `7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb` |

**Quoted:**
- CREDITS.md: `mh_v5/*.glb` is "preview/mh-motion's clips, retargeted".
- mh_v5/README.md: "room-mh's clips through G14's `mh_retarget.mjs` cc57630, default options".
- mh_retarget.mjs: "zero-phase smoothing ... then two-bone IK".
- docs/design/room-v5/README.md calls them "16 mocap clips" and "placeholders". That is quoted as written; this
  pipeline does **not** call them mocap.

**Undocumented:** the capture method, performer and original file of the preview/mh-motion clips.

Every corrected report carries `documented_quotes` (each checked verbatim) and the source hashes.

## 9. Root import steps (server; exact; none run here)

`<repo>` is this private checkout on the server; `<project>` is the UE project.

```
# 0. measure + place (§6). Placement evidence is still required before the bed can play.

# 1. inventory with the three labelled derived clips (paths exactly as written here; export matches them)
python3 tools/inventory_native_life_clips.py \
  --derived LieDown=docs/proposed/bed-transition/SUB01_LieDown.corrected.in_place.glb \
  --derived SleepLoop=docs/proposed/bed-transition/SUB01_SleepLoop.corrected.in_place.glb \
  --derived GetUp=docs/proposed/bed-transition/SUB01_GetUp.corrected.in_place.glb \
  [--extra Idle=<root's Idle source>] \
  --out <project>/private-audit/native-life-clips-inventory.json
#   expect 3 rows provenance=derived_library_asset, verdict=Candidate,
#   verdict_reason "derived_library_asset (label visible; not a capture): ..."

# 2. FBX (export_unreal_life_fbx): owner skin + the three in-place clips in ONE merged source
node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb /tmp/owner.glb
node tools/merge_unreal_skin_clips.mjs /tmp/owner.glb /tmp/life-bed.glb \
  docs/proposed/bed-transition/SUB01_LieDown.corrected.in_place.glb \
  docs/proposed/bed-transition/SUB01_SleepLoop.corrected.in_place.glb \
  docs/proposed/bed-transition/SUB01_GetUp.corrected.in_place.glb
blender -b --python tools/export_unreal_life_fbx.py -- /tmp/life-bed.glb <project>/SourceAssets/LifeFBX \
  <project>/private-audit/native-life-clips-inventory.json \
  LieDown=docs/proposed/bed-transition/SUB01_LieDown.corrected.in_place.glb \
  SleepLoop=docs/proposed/bed-transition/SUB01_SleepLoop.corrected.in_place.glb \
  GetUp=docs/proposed/bed-transition/SUB01_GetUp.corrected.in_place.glb
#   life-fbx-audit.json and unreal-life-import.json are REWRITTEN per run: if Idle is a GLB clip, add it to the
#   same merge and the same export (Idle=<clip>), or the Idle row disappears from the import report.

# 3. import (unreal_import_life_fbx roles LieDown/SleepLoop/GetUp)
UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_life_fbx.py" -unattended
#   expect SUB01_LIFE_SKELETON_PARITY ... and SUB01_LIFE_IMPORTED role=LieDown|SleepLoop|GetUp
#   durations 15.3667 / 1.9333 / 12.2 s

# 4. config fragment (life gate + visible labels) and the root path file
python3 tools/unreal_bed_root_motion.py config <project>/private-audit/native-life-clips-inventory.json \
  <project>/unreal-life-import.json /tmp/life-fragment.ini
#   = unreal_life_clips_runtime config + "; SUB01 provenance <Role>=derived_library_asset ..." lines;
#   bed roles appear only all together. Append the fragment to the [Sub01HomeCharacter] config.
python3 tools/unreal_bed_root_motion.py stage-paths docs/proposed/bed-transition/SUB01_bed_mesh_root_paths.json \
  <project>/private-audit/native-life-clips-inventory.json <project>/unreal-life-import.json <project>
#   writes <project>/private-audit/native-life-root-paths.json only if every bed role binds the exact clip

# 5. install (staged sources; order: stage -> seat (if used) -> life -> bed root motion)
python3 tools/stage_unreal_home_runtime.py <project>
python3 -c "import sys;sys.path.insert(0,'tools');import unreal_seat_transition_runtime as s;s.install_module('<project>/Source/Sub01HomeLab')"  # if the seat is used
python3 tools/unreal_life_clips_runtime.py install <project>/Source/Sub01HomeLab
python3 tools/unreal_bed_root_motion.py install <project>/Source/Sub01HomeLab
#   build with the official Build.sh; expect SUB01_LIFE_ROOT_MOTION_READY then SUB01_LIFE_READY ... bedMeasured=1 placement=1
#   (placement=1 needs native-life-bed-evidence.json from a server placement audit that does not exist yet)
```

**Still open, in order:**
1. The mattress measurement.
2. The duvet decision.
3. The placement audit: play the imported clips at the approach, skin them against this exact bed report, sweep
   the capsule return, then write `native-life-bed-evidence.json`.
4. The first engine run, checking the mesh-axis assumption.

Nothing here is accepted. Nothing is deployed.

## Licence

- **PRIVATE.** Never deploy, never publish, never main.
- The corrected clips derive from the mh_v5 clips ("as their sources"). They contain no Sova frames.
- The measured Sova and Mixamo alternatives were not written to this directory.
