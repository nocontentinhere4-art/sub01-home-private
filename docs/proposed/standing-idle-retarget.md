# Standing idle for the native owner: retarget pipeline, measured residuals, acquisition plan

**Status (14 October 2026): no clip passes. No genuine standing idle exists on the owner skeleton in
this repository, and nothing was downloaded or acquired.** The retarget pipeline below is real and
was run here on every standing idle the repository holds. Each output fails at least one measured
gate, so none of them is committed and none should be bound. The measured reports are committed
in `docs/proposed/standing-idle-retarget/`.

The web was **not** checked. This session has no `playwright-isolated` browser tool, so every licence
fact below is quoted from files in the repository. Where the repository says nothing, the fact is
marked unverified.

## What was added (new files only)

| file | role |
|---|---|
| `tools/retarget_life_clip.py` | The pipeline. It drives the existing `tools/retarget_first_person.mjs`, unchanged, with Node. |
| `tools/verify_life_idle_candidate.py` | The gate. It measures a candidate against the owner and exits 0 only if every invariant passes. It never edits a clip. |
| `tools/life_gltf.py` | glTF reading (GLB, or `.gltf` with `.bin` or `data:` buffers), forward kinematics, and a GLB writer. It has **no meshopt decoder**: compressed files are decoded first by the existing `tools/uncompress_unreal_glb.mjs`, which uses the vendored official decoder. |
| `tests/test_verify_life_idle_candidate.py`, `tests/test_retarget_life_clip.py`, `tests/life_clip_synth.py` | Tests on synthetic owner-like GLBs, plus real-file tests that skip when the files are absent. |
| `docs/proposed/standing-idle-retarget/*.json` | The measured reports of the real runs. |

`tools/native_life_skeleton_parity.py` (3a1bae2) is reused unchanged for the 66-vs-65 rule.

## Sources in the repository, ranked by genuineness

| rank | source | provenance (quoted from the repository) | standing idle? | measured result |
|---|---|---|---|---|
| — | `web/room/mh_mx/room_mx_standing_clap.glb` | A genuine Mixamo capture, baked on the owner skeleton. `web/room/mh_mx/README.md`: "Mixamo captures, baked for our chair by `room_build/kimodo/mx_build.sh`". | **No.** It is a clap. | Already on the owner skeleton, with rest deviation 0. It still fails `standing` (leg extension 0.72), `root_in_place` (hips 30.1 cm), `feet_joints`, `soles` (slide 11.3 / 8.1 cm) and `loop`. Excluded. |
| 1 | `web/room/boy_moves.glb#stand_idle` | The Quaternius Universal Animation Library `Idle_Loop`. `web/room/CREDITS.md` quotes the archive's `License.txt`: "CC0 1.0 Universal (CC0 1.0) Public Domain Dedication". The site-wide QAL v1.0 "forbids redistributing them as a standalone asset or pack". `room_build/boy_post.mjs` already retargeted it onto the 24-bone first rig, with the feet pinned by IK there. How it was authored or captured is not documented. | Yes, a breathing idle (2.5 s). | Best measured result. See below. |
| 2 | `web/room/char_v5.glb#idle` | The idle that came with the Tripo v5 placeholder rig. CREDITS: `char_v5.glb` is "AI-generated with Tripo (tripo3d.ai, paid API)", under "Tripo's terms of service". The idle's capture method is undocumented. The inventory class is `unknown`. | Partly. The idle steps around. | Its bone lengths are almost the owner's. The source itself fails: feet slide 12.0 / 19.4 cm and the hips travel 25.3 cm. |
| 3 | `web/room/boy_m_idle.glb` | AI-generated. CREDITS: "clips generated with NVIDIA ARDY", under the NVIDIA Open Model License. | Yes, at 20 fps. | Fails `timing` (20 fps), `loop` and `soles`. |
| 4 | `web/room/boy_idle.glb` | AI-generated: "Meshy, via Higgsfield; generated content under those services' terms". | — | **Refused** by `retarget_first_person.mjs`: "Animated scale changes are rejected". |
| — | Mixamo `Sleeping_Idle` and `Laying_Sleeping` on v5 (`web/room/mh_v5/`) | Genuine Mixamo captures (`room_build/kimodo/mixamo_clips.json`). | No, they are lying. | Not standing idles. |
| — | Epic Game Animation Sample | **Not in the repository.** `tools/stage_first_person_assets.py` records `'game_animation_sample_found': False`. | — | — |

## How the retarget works (`tools/retarget_life_clip.py`)

### 1. Decode

A meshopt-compressed source goes through `node tools/uncompress_unreal_glb.mjs` into the work
directory.

### 2. Prepare

This step is bookkeeping only. The motion is unchanged, and the report proves it with
`prepared_vs_original_max_joint_cm`, which is 0.00027 cm for v5 and 0 for UAL.

- The source's skeleton nodes and the one chosen animation are renamed to `mixamorig:` names
  through an explicit table. The presets are `v5`, `ual_boy` and `mixamo`, which also covers
  `mixamorig1:` and similar prefixes. `--mapping MAP.json` supplies any other table.
- Unmapped intermediates keep their motion: twist bones, v5's `Pelvis`, metacarpals, and a
  synthetic pelvis in the tests.
- An owner joint that the source lacks becomes a **static leaf with no keys**. That joint holds the
  owner's rest relative to its parent. Examples are finger endpoints, `HeadTop_End`, `Toe_End`, and
  every finger on the fingerless UAL rig.
- **Rest re-basing.** The `.mjs` delta assumes both rests are the same pose. v5 and UAL are A-pose
  and the owner is a T-pose, so without re-basing the arms would point outward.
  - Each mapped source joint's rest rotation is swung by the shortest arc until its bone points
    where the owner's does after the `.mjs` alignment C. The hands also use the index–pinky axis.
  - Tracks are absolute local rotations, so the animated pose is unchanged. An untracked re-based
    node gets a constant track that holds its original rest.
  - Hips, Spine and Spine1 are **not** re-based, because they place Spine2, which defines C.
    Iterating on them does not converge: each pass tilts the frame further. That leaves a reported
    residual of about 3.2° at Spine and Spine1.

### 3. Retarget

The retarget is `node tools/retarget_first_person.mjs PREPARED.glb web/room/char_mixamo.glb RAW.glb --clip NAME`:

```
Q_target_world(t) = C · Q_src_world(t) · Q_src_rest_world⁻¹ · C⁻¹ · Q_target_rest_world
target local      = Q_target_parent_world(t)⁻¹ · Q_target_world(t)
```

- The owner's local translations are kept, so bone lengths are exact.
- The hips get the source's world delta scaled by the measured leg-height ratio.
- The `.mjs` writes its own audit, which includes the no-motion rest recovery and the bone-length
  checks.

### 4. In place

- The hips translation keeps its measured sway.
- The constant horizontal offset of the first frame is removed, so he starts where the owner's rest
  stands. For v5 that offset is 20.15 cm.
- The linear horizontal drift from the first frame to the last is removed. It is about 0 for all
  three runs.
- Vertical motion is untouched, and every removed amount is reported.

### 5. Loop window

`--trim auto` runs an exhaustive search over the measured frames, using numpy, for the longest
window of at least 2 s that passes three groups of checks:

| group | requirement |
|---|---|
| loop | pose ≤ 0.5 cm, hips ≤ 0.5 cm, velocity ≤ 5 cm/s |
| feet | slide ≤ 2 cm, rise ≤ 2 cm |
| hips | travel ≤ 5 cm |

The search also reports the best loop window, and the best loop among windows where the feet stay
planted. Nothing is ever crossfaded, blended or posed.

### 6. Residuals

`verify_life_idle_candidate.py` checks the output and writes `OUTPUT.report.json`.

## Invariants (`tools/verify_life_idle_candidate.py`)

| invariant | rule |
|---|---|
| `skeleton` | The 65 owner joints with the owner's parents. The Mixamo prefix may differ. At most one structural root, which must be constant at 0, 3 and 8 s (`native_life_skeleton_parity.structural_root_parity`), so 66 nodes against 65 joints is never rejected on the count. With `--mapping`, every owner joint must be named explicitly, or set to null. |
| `rest_offsets` | Per-bone rest offset (in the parent frame) and length within 0.05 cm of the owner's. The maximum per bone is reported. With `--mapping`, the bone-length ratios are reported instead. |
| `bone_length_constancy` | Every frame, every bone within 0.05 cm of its own rest and of the owner's. |
| `root_in_place` | Hips horizontal travel ≤ 5 cm, net ≤ 0.5 cm, structural root constant. |
| `loop` | Start against end: hips-relative pose ≤ 0.5 cm, hips world ≤ 0.5 cm, seam velocity ≤ 5 cm/s. |
| `feet_joints` | Labelled as **joint** positions. Height std ≤ 0.5 cm and range ≤ 2 cm, slide ≤ 2 cm, no sinking more than 0.5 cm below the owner's rest joint height. |
| `soles` | The owner's **fixed plantar vertex set**: material `feet`, rest Y ≤ 0.004 m, bind normal Y < −0.7. On the real owner this is **4177 vertices**, with Y bounds 0 to 0.0039926 m, so the socks are excluded. They are skinned every frame. Per foot: penetration below y = 0 ≤ 0.5 cm, lowest-vertex lift ≤ 2 cm, centroid slide ≤ 2 cm. |
| `standing` | Torso tilt ≤ 30°, leg extension ≥ 0.85. |
| `timing` | Uniform 30 ± 0.5 fps, 1 to 60 s. |
| `symmetry` | Every Left joint stays left of its Right twin, in the hips frame, on every frame. |

Only bone-for-bone mode can return `accepted_for_binding: true`, and only when everything passes.

## Measured residuals of the real runs

The full numbers are in `docs/proposed/standing-idle-retarget/`.

| | UAL `stand_idle` (rank 1) | v5 `idle` | ARDY `m_idle` |
|---|---|---|---|
| duration / fps / frames | 2.5 s / 30 / 76 | 15.33 s / 30 / 461 | 3.35 s / **20** / 68 |
| `.mjs` bone-length error | 5e-16 m | 4e-16 m | 4e-16 m |
| `.mjs` no-motion rest recovery | 0 | 3e-8 | 0 |
| leg-height scale (owner / source) | 1.0331 | 1.0203 | 1.0236 |
| rest offsets vs owner | 0.0 cm | 0.0 cm | 0.0 cm |
| bone-length deviation vs owner | 0.0 cm | 0.0 cm | 0.0 cm |
| rest-axis residual Spine / Spine1 (unrebased) | 3.29° | 3.15° | 3.27° |
| hips horizontal travel / net | 0.78 / 0.0 cm | **25.8** / 0.0 cm | 0.89 / 0.0 cm |
| loop pose / hips / seam velocity | 0.0 cm / 0.0 cm / **16.8 cm/s** | 0.057 / 0.0004 cm / **15.3 cm/s** | **1.09** cm / 0.004 cm / **9.7 cm/s** |
| feet joints slide (max) | 0.44 cm | **19.9 cm** | 0.45 cm |
| soles lowest vertex, left | **+3.58 to +3.65 cm** (floats) | **−3.56 to +0.71 cm** | **−1.70 to −1.61 cm** |
| soles lowest vertex, right | **−2.22 to −2.16 cm** (sinks) | **−2.70 to +1.59 cm** | **−1.63 to −1.50 cm** |
| soles centroid slide L / R | 0.18 / 0.33 cm | **14.4 / 19.8 cm** | 0.42 / 0.43 cm |
| standing (tilt, extension) | 6.4°, 1.06 | 7.7°, 1.05 | 0.8°, 1.07 |
| symmetry | pass | pass | pass |
| loop windows passing everything | none | none | none |
| failed | `feet_joints`, `loop`, `soles` | `feet_joints`, `loop`, `root_in_place`, `soles` | `loop`, `soles`, `timing` |

### Where each residual comes from

**The seam-velocity kinks are in the sources, not added by the retarget.** Verifying the sources
themselves in `--mapping` mode gives seam velocities of 12.4 cm/s for UAL and 14.9 cm/s for v5.
Their first and last poses match, but the motion reverses at the seam, mostly in the hands.

**The UAL foot offsets come from the retarget.** Directions are transferred exactly: on the test's
other rig the error is under 0.01°, and on UAL's leg chain it is 0.000°. But the owner's shin-to-thigh
proportion differs from the first rig's: the owner has 36.3 / 39.8 cm, the first rig 35.1 / 35.4 cm.
The UAL stance is staggered and bent, so the left sole ends 3.6 cm above the floor and the right one
2.2 cm below it.

That gap can only be closed by foot IK, which this pipeline refuses to apply. A different source is
needed.

### Window search

The search finds no window of at least 2 s that passes the loop, feet and hips checks in any
source. The best UAL loop window is the whole clip, 0 to 2.47 s, with normalised cost 1.34. The
best v5 loop among windows where the feet stay planted is 0.2 to 3.4 s, with pose 1.99 cm and cost
3.99.

**Verdict: none of the repository's clips can be bound as the owner's Idle.** The freeze remains
until a better source arrives. The adapter's fail-closed refusal (`SUB01_LIFE_IDLE_REFUSED`) is the
correct behaviour today.

## Licence facts, as the repository records them

### Mixamo

- `docs/design/mixamo/README.md`: "used under Mixamo's terms. They are royalty-free, including
  commercial use, but the raw animation files may not be redistributed on their own." Also: "The
  raw FBX files stay in scratch and are never committed by this pipeline."
- `web/room/mh_mx/README.md`: "Mixamo's terms allow the animations in an app but not the raw files
  redistributed: the FBX stay out of the repository".
- `docs/research/game_look.md` cites Adobe General Terms § 3.6: "cannot distribute the Content Files
  on a stand-alone basis, outside of the End Use". Free access is terminable "in its sole
  discretion" (§ 3.7). Its verdict for the public web room was **DO NOT USE**.
- `tools/stage_first_person_assets.py` describes `Walking.fbx` and the others as "Existing
  user-downloaded Mixamo source; private import only, never standalone redistribution". Its
  `license_policy` is "Mixamo raw FBX is private source input only".

### How `Walking.fbx` was obtained

`stage_first_person_assets.py` reads `~/Downloads/<Name>.fbx` (its default `--downloads`): the
owner's own download. It stages it to `SourceAssets/Walking.fbx` in a private bundle.

It also warns: "Raw Walking hips Y209.1508 and spine pre-rotation … differ from Texting/Gaming
hipsY104.2749". So Walking was downloaded on a different Mixamo character or scale.

### The owner skeleton

`char_mixamo.glb` is "v5 auto-rigged onto the standard 65-bone skeleton by
`room_build/rig/autorig.sh`, offline" (CREDITS). It was **not** rigged by Mixamo's auto-rigger.

**A Mixamo "Without Skin" download therefore carries Mixamo's own character offsets, not the
owner's.** It fails the strict `rest_offsets` gate and must go through `retarget_life_clip.py
--preset mixamo`, which keeps the owner's offsets.

### Other sources

- **Quaternius UAL:** CC0, per the archive `License.txt` recorded in CREDITS. The QAL v1.0
  forbids standalone or pack redistribution.
- **Tripo (`char_v5.glb`):** "Tripo's terms of service". The idle's origin is undocumented.
- **ARDY:** the NVIDIA Open Model License. The clip is AI-generated.
- **Meshy / Higgsfield (`boy_idle.glb`):** "generated content under those services' terms".

### Epic Game Animation Sample — unverified

The repository holds no Game Animation Sample and no licence text for it. The only Epic or Fab text
is in `docs/research/game_look.md`:

- the Fab EULA, for Quixel / Fab content: "restrict end users from extracting or otherwise using
  Content outside of the Project";
- MetaHuman under "UE EULA § 6(e)".

Whether the Game Animation Sample's motions may be exported to FBX or GLB and retargeted onto a
non-Epic skeleton is **unverified**. Read the actual terms before using it.

## Acquisition candidates

None of these has been done.

### (A) An official Mixamo standing idle (recommended)

Examples are "Breathing Idle" and "Idle".

1. **Owner**, with their own Mixamo or Adobe account:
   - choose the idle;
   - check **In Place** if offered;
   - download **FBX Binary, Without Skin, 30 fps**.

   No credentials are shared with anyone.
2. **Owner or root:** copy it to the server, outside Git, for example `/srv/private/life/Breathing_Idle.fbx`.
   - Never commit it: Mixamo terms forbid redistributing the raw file.
   - Never copy it into `web/`.
3. **Root** converts it with the existing converter (no renames):
   `node room_build/kimodo/mixamo_glb.mjs /srv/private/life/Breathing_Idle.fbx /srv/private/life/Breathing_Idle.src.glb`
4. **Root** retargets onto the owner. The offsets differ from the owner's, as for `Walking.fbx`
   above. The `mixamo` preset handles `mixamorig1:` as well:
   `python3 tools/retarget_life_clip.py /srv/private/life/Breathing_Idle.src.glb /srv/private/life/Idle.glb --preset mixamo --provenance "Mixamo Breathing Idle, owner download <date>"`
5. Continue at **Common steps** below.

### (B) Epic Game Animation Sample idle (UE5 Manny/Quinn skeleton)

The licence is unverified (see above).

1. **Owner** obtains the Game Animation Sample with their own Epic account and accepts its terms.
2. **Root**, on the server (never on the owner's Mac):
   - opens it in the server's Unreal;
   - exports one standing idle AnimSequence on the Manny skeleton to FBX;
   - converts the FBX to GLB with Blender's glTF exporter;
   - keeps both files under `/srv/private/life/`, outside Git.
3. **Root** writes an explicit mapping JSON: owner joint → Manny bone, or `null`. For example:
   - `Hips`→`pelvis`, `Spine`→`spine_01`, `Spine1`→`spine_03`, `Spine2`→`spine_05`;
   - `Neck`→`neck_01`, `Head`→`head`;
   - `LeftShoulder`→`clavicle_l`, `LeftArm`→`upperarm_l`, `LeftForeArm`→`lowerarm_l`, `LeftHand`→`hand_l`;
   - `LeftHandIndex1..3`→`index_01_l..index_03_l`, and so on for the other fingers;
   - `LeftUpLeg`→`thigh_l`, `LeftLeg`→`calf_l`, `LeftFoot`→`foot_l`, `LeftToeBase`→`ball_l`;
   - `*4`, `HeadTop_End` and `Toe_End` → `null`.

   Skipped spine bones are carried by the world-delta method. Twist bones stay unmapped
   intermediates.
4. **Root** retargets with the mapping:
   `python3 tools/retarget_life_clip.py /srv/private/life/GASP_Idle.glb /srv/private/life/Idle.glb --mapping /srv/private/life/manny_to_owner.json --provenance "Epic GASP <asset name>"`
5. Continue at **Common steps** below.

## Common steps, into 67af5f8's adapter

All of these run as root, on the server. Every step must succeed before the next.

1. **Verify.** This is the gate; exit 0 is required:
   `python3 tools/verify_life_idle_candidate.py /srv/private/life/Idle.glb --out /srv/private/life/Idle.verify.json`
2. **Inventory.** The `Idle` row must read `"verdict": "Candidate"`. `--extra` is the operator's
   explicit declaration about that file. For a retarget, the `--provenance` text in the report says
   what it is.
   `python3 tools/inventory_native_life_clips.py --extra Idle=/srv/private/life/Idle.glb --out <project>/private-audit/native-life-clips-inventory.json`
3. **FBX conversion** (Blender, on the server):
   ```
   node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb /tmp/owner.glb
   node tools/merge_unreal_skin_clips.mjs /tmp/owner.glb /tmp/life.glb /srv/private/life/Idle.glb
   blender -b --python tools/export_unreal_life_fbx.py -- /tmp/life.glb <project>/SourceAssets/LifeFBX \
       <project>/private-audit/native-life-clips-inventory.json Idle=/srv/private/life/Idle.glb
   ```
   The `Idle=` path must be the same string given to `--extra`.
4. **Import** onto the existing owner USkeleton. The 66-vs-65 structural-root parity is checked
   there.
   `UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_life_fbx.py" -unattended`
5. **Config fragment.** Exit 3 means nothing is proven and nothing is written.
   `python3 tools/unreal_life_clips_runtime.py config <project>/private-audit/native-life-clips-inventory.json <project>/unreal-life-import.json /tmp/life-fragment.ini`
6. **Install.** Run `stage_unreal_home_runtime.stage(project)`, then the seat adapter if used, then:
   `python3 tools/unreal_life_clips_runtime.py install <project>/Source/Sub01HomeLab`
7. **Build and run** with the official Build.sh. Expect `SUB01_LIFE_READY idleBound=1 …`, and
   `SUB01_LIFE_IDLE_OK` while he stands still.

### What root must check visually (native capture; nothing is claimed here)

- Arms hang naturally after A-pose to T-pose re-basing. Check palm and forearm twist: twist is only
  aligned at the hands, by the index–pinky axis.
- Fingers. A fingerless source leaves the owner's straight rest fingers rigid on the hand.
- Soles on the native floor, both feet, the whole loop. The UAL run would show one foot 3.6 cm high
  and the other 2.2 cm sunk.
- The loop seam. A hand "tick" appears where the seam velocity exceeds 5 cm/s.
- Spine lean: the 3.2° Spine / Spine1 residual.
- The Walk ↔ Idle crossfade (0.24 s).
- The first-person view from the head camera.

## Commands used here

These ran on CPU, read-only on the repository, with outputs in a scratch directory:

```
python3 tools/retarget_life_clip.py web/room/boy_moves.glb OUT/stand_idle_ual.glb --preset ual_boy --animation stand_idle
python3 tools/retarget_life_clip.py web/room/char_v5.glb   OUT/idle_v5.glb        --preset v5 --animation idle
python3 tools/retarget_life_clip.py web/room/boy_m_idle.glb OUT/m_idle_ardy.glb   --preset ual_boy
python3 tools/retarget_life_clip.py web/room/boy_idle.glb  OUT/boy_idle_ai.glb    --preset ual_boy   # refused by the .mjs
python3 tools/verify_life_idle_candidate.py web/room/mh_mx/room_mx_standing_clap.glb --out OUT/standing_clap.verify.json
```

The output GLBs, 0.1 to 0.5 MB each, are **not committed**, because every one of them fails the
gate. They regenerate in seconds, deterministically, from the commands above.
