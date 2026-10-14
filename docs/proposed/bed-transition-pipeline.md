# Bed transition pipeline: lie down, sleep loop, get up (proposal; private)

**Status (14 October 2026): the pipeline runs end to end here, on CPU, from repository files. Its verdict is
REFUSED for binding.** The corrected lie-down and get-up are real retargets with exact owner bone offsets, but:

- their origin before `preview/mh-motion` is undocumented (provenance stays unverified);
- no Sova sleep loop meets either of them within a plausible blend (the best gaps are 58 cm and 82 cm);
- the native mattress has not been measured.

Nothing was run on the server, in Unreal or in Blender. No result was viewed in the engine, and nothing here
claims a visual match or an accepted bed.

## Files (all new; no existing file is edited)

| file | role |
|---|---|
| `tools/bed_transition_pipeline.py` | The pipeline: provenance, retarget, crop, root path, sleep-loop search, blend, gaps, reports. |
| `tools/unreal_bed_surface_audit.py` | **Server only.** A UE editor audit of the actual mattress top, the twin of `unreal_chair_surface_audit.py`. Not run. |
| `tools/fit_bed_placement.py` | A pure-Python placement fitter. It proposes the body transform from the lying frame's skinned back patch and the mattress triangles. It never accepts. |
| `tests/test_bed_transition_pipeline.py` | 17 tests: synthetic, plus one real-data run (skipped if the files or Node are absent). |
| `docs/proposed/bed-transition/*.report.json`, `*.root_path.json` | The measured reports of the run below. |
| `docs/proposed/bed-transition/SUB01_{LieDown,GetUp}.{travel_in_hips,in_place}.glb` | The corrected clips (0.43 to 0.57 MB each). PRIVATE. |
| `docs/proposed/bed-transition/fit-dry-run-synthetic/` | The fitter run on a **synthetic** flat mattress. It shows how the fitter behaves; it is not the native bed. |

The pipeline imports these files read-only and does not edit them:
- `retarget_life_clip.py` (`mapping_for`, `prepare_source`, `topo`, `MJS`);
- `verify_life_idle_candidate.py`;
- `life_gltf.py`;
- `validate_unreal_seat_contact.py` (`SEAT_BAND_CM`, `SOLE_BAND_CM`, `MIN_PATCH_VERTICES`, `MIN_SUPPORT_VERTICES`);
- `unreal_life_clips_runtime.py` (`MIN_MATTRESS_AREA_CM2`, `mattress_triangles`, `life_id`).

`retarget_first_person.mjs` runs unchanged under Node.

## 1. Provenance (quoted; every quote is checked verbatim by the run)

### Sources used, with their hashes

| file | sha256 |
|---|---|
| `web/room/mh_v5/room_bed_lie.glb` (v5 rig, 80 nodes) | `61e881220a646f37f6b52d09f05919188c159ddf89f658d274f2a4501f871e94` |
| `web/room/mh_v5/room_bed_wake.glb` (v5 rig, 80 nodes) | `aa5935e33f377204549b25a31747c3ad168707747ac703e451fed30557c96f49` |
| `web/room/desk_states/bed/sleep_back.glb` (chosen loop) | `aa399a4283ce2f64b0fd504ddb41fbc7c717b1659ae2311cc77d2c09743103b4` |
| `web/room/desk_states/bed/sleep_side.glb` | `0f868e63962f8481e3ca99d10095e900091b6a610b2058ab9d831db10b373b3b` |
| `web/room/desk_states/bed/sleep_back_idle.glb` | `99b6904165f818b8318a89e63a5f19a83bc76cfedf4ad020df0caf8659bc5552` |
| `web/room/char_mixamo.glb` (owner) | `7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb` |
| `web/room/mh_mx/room_bed_lie.glb` (drifted copy, measured only) | `f22e3fb1a991c25dd0d128059e97e52e49819e2393db78dbc9c690a80af8d3e2` |
| `web/room/mh_mx/room_bed_wake.glb` (drifted copy, measured only) | `b85449b4ea450ab232886c25152aefb3dc4a87162bc2908b6f1141331da6b3d5` |

The READMEs, scripts and tools are hashed in `bed-transition-pipeline.report.json` under `hashes`.

### What is documented

- **CREDITS.md:** `mh_v5/*.glb` is "preview/mh-motion's clips, retargeted", under a licence "as their sources".
- **mh_v5/README.md:** `room_bed_lie` and `room_bed_wake` are "room-mh's clips through G14's `mh_retarget.mjs`
  cc57630, default options".
- **mh_retarget.mjs:** it applies "zero-phase smoothing (Gaussian, sigma 1 frame limbs / 1.7 spine-neck-head),
  then two-bone IK" on the wrists and ankles. **So the v5 "originals" are already smoothed and IK-adjusted.**
- **docs/design/room-v5/README.md:** the set is called "16 mocap clips" in the release note, and the contract says
  "**The ones here now are placeholders**".
- **mh_mx/README.md:** the mh_mx copies are "v5's room clips carried over by `room_build/kimodo/mx_convert.mjs` (no
  Mixamo capture of these yet)".

### What is not documented

- How the `preview/mh-motion` clip was made: motion capture, keyframed or generated. No README, licence or
  generation script for it is in this repository.
- Its performer, capture system and original file. There is no original file hash.
- Git history: the repository starts at the snapshot `852bd77` (2026-10-12). Every clip arrives in `449b417`, so git
  adds nothing.
- A Mixamo lie-down or get-up. `room_build/kimodo/mixamo_clips.json` has none.
  - The genuine Mixamo captures on v5 (`room_sleeping_idle`, `room_laying_sleeping`, `room_laying_nodding`) are
    lying loops or a rare event, not transitions.
  - They are also not the sources of `room_bed_lie` / `room_bed_wake`.

**Verdict: ProvenanceUnverified.** The repository documents a chain back to a v5-rig placeholder, and nothing
before it. This is not upgraded to "genuine capture". The reports refuse a provenance block that lacks any of
these: the source hash, the documented chain, the undocumented list, the verdict, or the verbatim quotes.

### Sova sleep loops

- desk_states/README.md: "SovaSims animations used with the author's permission (confirmed by the owner, 2026-10-08)".
- The licence is pending: the clips "never go to main".
- Their capture method is undocumented.
- They are used here **privately only**.

## 2. Retarget from the v5 originals onto the owner's exact offsets

`retarget_v5()` in `bed_transition_pipeline.py` is a thin wrapper:
1. `retarget_life_clip.mapping_for('v5')` and `prepare_source()`: rename to the owner's joints and re-base the rest.
2. Then `node tools/retarget_first_person.mjs PREPARED OWNER RAW --clip NAME`, unchanged.

| | LieDown | GetUp |
|---|---|---|
| frames / fps | 510 / 30 (16.967 s) | 464 / 30 (15.433 s), cropped to 379 |
| prepared vs original source, max joint | 0.0 cm | 0.0 cm |
| `.mjs` bone-length error (sampled) | 5e-16 m | 5e-16 m |
| `.mjs` no-motion rest recovery | 3e-8 | 3e-8 |
| leg-height scale (owner / source) | 1.0203 | 1.0203 |
| rest-axis residual, Hips / Spine / Spine1 (not re-based) | 5.96° / 3.15° / 3.15° | same |
| **owner bone-length deviation, every frame** | **0.0 cm** | **0.0 cm** |
| non-hips translation tracks written | 0 | 0 |
| the mh_mx copy's non-hips translation drift | **7.08 cm** (Spine), 12 tracks, length change up to 2.98 cm | **5.03 cm** (Spine), length change up to 1.57 cm |
| world joint difference, this retarget vs the mh_mx copy | max 23.8 cm, median 11.6 cm | max 20.7 cm, median 10.9 cm |

The owner's local translations are kept exactly; only captured rotations and the hips' captured delta are used.

Fingers: the source's `finger*-1..3` rotations are used. The owner's `*4` finger tips, `HeadTop_End` and `Toe_End`
hold the owner's rest. No finger pose is invented.

## 3. Root travel: captured, smooth, cropped before the walk

The hips' horizontal path is kept as captured. Two variants are written:

- **`travel_in_hips`**: the path stays in the hips track. This is what the 67af5f8 adapter would play with movement
  disabled.
- **`in_place`**: the horizontal path is removed (vertical kept). `SUB01_<role>.root_path.json` gives the path per
  frame, for the native side to drive as smooth movement.
  - Fields: `forward_cm`, `right_cm` and `hips_up_cm` in the component frame (X forward, Y right, Z up, cm, relative
    to frame 0), plus speed and a support class (floor / transitional / bed).

The owner skeleton has no animated root bone (its structural root is constant, `native_life_skeleton_parity`), so
UE root motion from a root bone is not available without changing the skeleton.

### Get-up crop (measured)

**Rule:**
- standing = torso tilt ≤ 30° and leg extension ≥ 0.95 × the owner's rest extension (1.079), held ≥ 0.3 s;
- walk = hips horizontal speed > 20 cm/s, with its 0.5 s mean also > 20 cm/s;
- crop = the first settled frame (≤ 10 cm/s) between the standing onset and the walk.

| | value |
|---|---|
| standing onset | 12.20 s (frame 366) |
| **crop** | **12.60 s (frame 378)**, hips speed 9.8 cm/s |
| walk onset | 13.13 s (frame 394) |
| discarded tail (the walk away) | 91.9 cm path, 79.9 cm net, max 63.2 cm/s |
| uncropped clip | 275.7 cm path, **188.3 cm net**, so the 1.9 m is no longer carried into the bed transition |

### Remaining root travel

| | LieDown (16.97 s) | GetUp (cropped, 12.6 s) |
|---|---|---|
| path / net | 192.1 cm / 126.2 cm (forward 124.2, right 22.5) | 183.7 cm / 110.0 cm (forward 108.7, right −17.0) |
| max speed | 70.1 cm/s at 0.40 s (walking in) | **183.9 cm/s at 5.40 s** |
| max acceleration | 225 cm/s² | **762 cm/s²** at 5.17 s |
| max one-frame step | 2.34 cm (no discontinuity; threshold 10 cm) | 6.16 cm (no discontinuity) |
| on the floor / off it | 67.2 / 124.9 cm | 10.3 / 173.4 cm |

**Two findings that are reported, not fixed:**

1. **LieDown starts mid-walk**, at 66 cm/s, with the left foot in the air. The start's soles fail the plantar band
   (left 4.3 to 12.2 cm up, sliding 37 cm). It needs a walk-in hand-off at matching speed, not a standing start.
2. **GetUp contains an implausible seated slide.** From 4.97 to 5.73 s the hips travel about 79 cm at sitting
   height, peaking at 184 cm/s and 762 cm/s².
   - It is smooth frame to frame, so it is not a teleport.
   - It is still not a physical scoot. It comes from the mh_v5 source (the same in the uncropped clip).
   - A genuine get-up capture is needed to replace it.

### Get-up end checks (the verifier's own rules, last 0.2 s)

| check | result |
|---|---|
| standing (tilt 9.2°, extension 1.055) | pass |
| foot joints still (slide ≤ 0.34 cm) | pass |
| soles: no penetration, no slide | pass |
| **plantar contact** (`SOLE_BAND_CM` 0 to +1 cm) | **FAIL.** Left sole lowest 3.28 to 3.41 cm above the floor, right 4.84 to 5.37 cm. No single vertical shift fits both (interval −3.28 … −4.37 is empty): the captured legs disagree. Not fixed (no IK). |

## 4. Sova sleep loops: exhaustive search, blend, gaps

The search is a joint search over three things:
- lie-down lying frames (torso > 60°);
- the loop phase p;
- get-up lying frames.

The lie-down blends into loop phase p, the loop is re-phased to start at (p + N) mod L, and the get-up blends out of
that same phase.

**Cost:** max(hips-relative max joint distance / 10 cm, velocity mismatch / 50 cm/s, gravity attitude / 30°).
These are stated criteria, not tuned. A posture-class change (supine / side / oblique) is a refusal on its own.

**Placement:** each clip gets one rigid placement. Yaw comes from 2D Kabsch over all 65 joints, and the hips are put
on the hips at the blend start. It is never a per-frame correction.

**Blend:** N = **24 frames (0.8 s)**, the bed layer's existing crossfade. It slerps captured local rotations and lerps
the hips, with a smoothstep weight.

| loop (posture) | lie → loop: pose / velocity / attitude | loop → get-up: pose / velocity / attitude | verdict |
|---|---|---|---|
| **sleep_back** (supine), chosen | **58.5 cm** / 167 cm/s / 6.8° | **81.7 cm** / 73 cm/s / 8.8° | refused: pose and velocity |
| sleep_side (side) | 59.4 cm / 121 cm/s / **100.3°** | 81.4 cm / 13 cm/s / **100.8°** | refused, plus a side ↔ back flip |
| sleep_back_idle (oblique) | 123.4 cm / 97 cm/s / 74.2° | 134.4 cm / 76 cm/s / 83.1° | refused, plus a posture flip |

### Before the blend (sleep_back)

- **Direct cuts, unplaced:**
  - lie end → loop start: pose 86.8 cm, hips 151.0 cm apart;
  - loop end → get-up start: pose 84.3 cm, hips 29.5 cm apart.
- **Best match, placed** (hips coincide):
  - lie-down frame 334 (11.13 s) to loop phase 184: pose 58.5 cm (RMS 45.6 cm), attitude 6.8°. The loop is placed
    with yaw 135.4° and a vertical shift of −7.7 cm.
  - loop phase 9 to get-up frame 106 (3.53 s): pose 81.7 cm (RMS 49.5 cm), attitude 8.8°.
- **Discarded captured frames:** the lie-down's last 5.03 s and the get-up's first 3.53 s.

### After the blend

- The seams are exact by construction: pose 0, hips 0.
- The cost moves into the blend window. Peak joint speed is 204 cm/s (lie blend) and 231 cm/s (wake blend), against
  1.8 cm/s inside the loop itself.

**Verdict:** a 58 to 82 cm pose gap is not a plausible blend; the joints would sweep through the body. It is not
hidden.

**What is needed (either one):**
- a captured settle from the lie-down's end pose into the loop's pose (same supine class; the gap is the limb and
  torso configuration), **and** a captured transition from the loop's pose into the get-up's lying start; or
- a lie-down and get-up captured from and to the loop's own pose, or a sleep loop captured in the mh_v5 lie-down's
  end pose.

The composed (blended) clips are written to the scratch work directory only. They are **not committed**.

## 5. Bed geometry: requirements (the native mattress is NOT measured)

### Measurement root must make

Run `tools/unreal_bed_surface_audit.py` on the server. It writes `<project>/private-audit/native-bed-surface.json` in
the shape `unreal_life_clips_runtime.validate_bed()` reads: `bed.sections[].vertices_world_cm` and
`mattress_surface.triangle_indices`.

| requirement | detail |
|---|---|
| component | exactly one `StaticMeshComponent` tagged `SUB01Device:Bed` (`unreal_setup_home.py`), with one mattress-material section |
| material | default regex `cream[ _]?upholstery`. These are file facts from `queen-bed.glb`: cream 0.38 to 0.60 m (mattress), linen pillows at the −Z end, blue_fabric duvet 0.51 to 0.70 m. Override with `SUB01_BED_AUDIT_CONFIG` if the imported names differ. |
| triangles | upward faces (\|n_z\| ≥ 0.9) within 4 cm of the highest top point, in world cm, from the official `ProceduralMeshLibrary.get_section_from_static_mesh` |
| area | **≥ 15,000 cm²** (`MIN_MATTRESS_AREA_CM2`). The asset's mattress is about 152 × 203 cm, roughly 30,900 cm² before import. |
| head end | the direction toward the pillows' centroid along the long axis; ambiguous (< 10 cm) means refusal |
| collision | the component must collide (the audit records the profile and pawn response) |
| ambiguity | more than one tagged component or section means refusal; there is no name-only acceptance |

### Placement and contact audit (a server step; it does not exist yet as an engine tool)

`tools/fit_bed_placement.py` computes the proposal on CPU from the measured report:

- **Support patch:** a fixed bind-space selection, never a per-pose minimum. It is posterior-facing skin (bind normal ·
  −forward > 0.7), dominated by Hips / Spine / Spine1 / Spine2 (`torso_back`). Side-lying frames use the lateral
  selection.
  - Gated with the seat rule's constants: the lowest vertex within `SEAT_BAND_CM` (−2.5 … +0.5 cm), at least 12
    vertices in the band, at least 12 over the mattress, and no patch vertex hanging off the mattress.
  - Non-penetration: no skin vertex over the mattress deeper than −2.5 cm.
  - The legs (knees may be up) and the head (it rests on the pillow, which is unmeasured) are reported, not gated.
- **Transform:**
  - yaw: the body's hips→head axis onto the mattress long axis, toward the head end;
  - position: the head top 25 cm inside the head edge, and the back patch centred across;
  - vertical: inside the allowed range, the most support.
- **Approach side:** the LieDown's first frame (or the GetUp's last frame, `--floor-frame last`) must land beside the
  bed: left, right, foot end or head end, never over the mattress.
- **Output:** `accepted: false` and `native_bed_verified: false`, always.

**A real acceptance still needs the engine:**
1. play the imported LieDown / SleepLoop / GetUp at the proposed approach;
2. skin them every frame with the imported owner mesh;
3. measure the back patch against the triangles of this exact `native-bed-surface.json`;
4. only then write `native-life-bed-evidence.json` (`bed_revision` = `life_id(report text)`, `approach_cm`,
   `yaw_deg`, `accepted`).

That tool does not exist yet. The mesh component's relative transform to the actor (capsule offset, mesh yaw) is not
known here and must be read from the live character.

### Synthetic dry run (NOT the native bed)

The fitter was run on a flat 152 × 203 cm top at 60 cm (`fit-dry-run-synthetic/`):

- **LieDown last frame:** a proposal exists.
  - yaw −58.7°, back patch 4569 vertices in the band at the band's −2.5 cm edge;
  - 164 vertices off the mattress, the foot 0.4 cm past the end;
  - the walk-in start lands 18 cm right of the edge.
- **GetUp first frame:** a different yaw (167.7°). The standing end lands past the foot end.

These two placements are not one bed placement, because the clips do not share a bed: the lie-down ends on one
spot, the get-up starts on another.

## 6. Commands

Here (CPU), from the repository root:

```
python3 tools/bed_transition_pipeline.py docs/proposed/bed-transition --work /tmp/bed-work --write-glb
python3 tools/fit_bed_placement.py docs/proposed/bed-transition/fit-dry-run-synthetic/SYNTHETIC-bed-surface.json \
    docs/proposed/bed-transition/SUB01_LieDown.travel_in_hips.glb --work /tmp/bed-work \
    --out docs/proposed/bed-transition/fit-dry-run-synthetic/LieDown-last-frame.json
python3 tools/fit_bed_placement.py docs/proposed/bed-transition/fit-dry-run-synthetic/SYNTHETIC-bed-surface.json \
    docs/proposed/bed-transition/SUB01_GetUp.travel_in_hips.glb --frame 0 --floor-frame last --work /tmp/bed-work \
    --out docs/proposed/bed-transition/fit-dry-run-synthetic/GetUp-first-frame.json
python3 -m pytest -q tests/test_bed_transition_pipeline.py
```

The run is deterministic. The GLB hashes are in `bed-transition-pipeline.report.json` under `corrected_outputs`.

## 7. Server steps (root; per 67af5f8; none run here; currently BLOCKED at step 3)

1. **Measure the bed:**
   `UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_bed_surface_audit.py" -unattended`
   - Expect `SUB01_BED_SURFACE_AUDIT`.
   - Then `python3 tools/unreal_life_clips_runtime.py check-bed <project>` must move from `BedUnmeasured` to
     `BedPlacementMissing`.
2. **Propose a placement:**
   `python3 tools/fit_bed_placement.py <project>/private-audit/native-bed-surface.json docs/proposed/bed-transition/SUB01_LieDown.travel_in_hips.glb --approach-side <left|right> --out <project>/private-audit/bed-placement-proposal.json`
   - Repeat for GetUp with `--frame 0 --floor-frame last`.
   - The two must agree on one bed placement. Today they cannot (§4).
3. **Inventory.** **Blocked:** the corrected LieDown/GetUp are `ProvenanceUnverified`, and `--extra` is the
   operator's declaration of a genuine capture. Do not pass them as `--extra` unless the owner explicitly accepts
   the `preview/mh-motion` provenance. The SleepLoop (`sleep_back.glb`) is an inventory Candidate already. With
   accepted transitions:
   `python3 tools/inventory_native_life_clips.py --extra LieDown=<clip> --extra GetUp=<clip> --out <project>/private-audit/native-life-clips-inventory.json`
4. **FBX:**
   ```
   node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb /tmp/owner.glb
   node tools/merge_unreal_skin_clips.mjs /tmp/owner.glb /tmp/life.glb <LieDown.glb> <SleepLoop.glb> <GetUp.glb>
   blender -b --python tools/export_unreal_life_fbx.py -- /tmp/life.glb <project>/SourceAssets/LifeFBX \
       <project>/private-audit/native-life-clips-inventory.json LieDown=<clip> SleepLoop=<clip> GetUp=<clip>
   ```
5. **Import:**
   `UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_life_fbx.py" -unattended`
   - Expect `SUB01_LIFE_IMPORTED role=LieDown|SleepLoop|GetUp`.
6. **Config fragment:**
   `python3 tools/unreal_life_clips_runtime.py config <inventory> <project>/unreal-life-import.json /tmp/life-fragment.ini`
   - Bed roles are emitted only all together.
7. **Placement evidence:** the server skin audit (§5), then `native-life-bed-evidence.json`.
8. **Install:** `stage_unreal_home_runtime.stage(project)`, then the seat adapter if used, then
   `python3 tools/unreal_life_clips_runtime.py install <project>/Source/Sub01HomeLab`.
   - Build with the official Build.sh.
   - Expect `SUB01_LIFE_READY ... bedMeasured=1 ... placement=1`.

## Open requirements (in order)

1. **Clips.** A captured lie-down and get-up that meet one sleep loop within ≤ 10 cm hips-relative, the same posture
   class and ≤ 30° attitude. They must have documented provenance: for example owner-downloaded Mixamo captures,
   retargeted with `retarget_life_clip.py --preset mixamo` or this pipeline's wrapper.
2. **Get-up.** The 79 cm seated slide (184 cm/s) and the floating soles (3.3 and 4.8 cm) need a different source.
   They are not fixed here.
3. **Native movement.**
   - In-place mode needs the adapter to drive the root path while lying, but the 67af5f8 adapter disables movement
     during bed phases.
   - The standing capsule cannot walk onto the mattress (the bed blocks the pawn).
   - So either keep `travel_in_hips` (the body ends offset from the capsule, see 67af5f8's open item), or a
     non-walking movement mode that ignores the bed for the capsule. Never a teleport.
4. **Duvet.** The bed's duvet is a rigid mesh over the mattress. A sleeping body under it intersects it unless it is
   hidden, swapped or deformed.
5. **Measurement and evidence.** The mattress measurement, the component-to-actor transform, the pillow top for the
   head, and the engine skin audit.

## Licence

- **PRIVATE.** Never deploy, never publish, never main.
- The Sova frames are under the author's preview permission (confirmed by the owner 2026-10-08), and their licence is
  still pending. The composed clips that contain them stay uncommitted.
- The committed LieDown/GetUp GLBs derive from mh_v5 clips "as their sources", whose origin is undocumented.
- They are in this private repository only, as the run's measured output, under the same terms as `web/room/mh_v5/`.
