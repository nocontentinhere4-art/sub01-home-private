# Native adapters import plan against root main 2c61c93

Private; source only. Nothing here was compiled, imported or run in Unreal. No runtime, Runpod, budget or deploy
action was taken. Root is the sole UE operator; every step below is the renderer's/root's to run on the server,
**after root's office/furniture bundle**. Machine-readable copy: `native-adapters-import-plan-2c61c93.json`.
This plan supersedes the prerequisite tables in `native-adapters-install-runbook.md` (written against fb7253a).

## 1. Main compatibility of the d8d03c4 bundle (re-verified)

Method: `git worktree add <scratch> origin/main` (2c61c93); in a temp project holding only `Sub01HomeLab.uproject` (`{}`)
and `Config/`, run main's `tools/stage_unreal_home_runtime.stage()`; stage the branch the same way; run
`tools/install_native_adapters_bundle.py <tmp>/Source/Sub01HomeLab --dry-run` from the branch; worktree removed after.

| Check | Result on 2c61c93 |
|---|---|
| main vs branch staged `Source/` + `Config/` | byte-identical (`diff -rq`: no output) |
| bundle `--dry-run`, order seat → life → bed → controller | exit 0; `.h` +44 (2 insertions), `.cpp` +564 (6), `Hands.h` +19 (1), `Hands.cpp` +14 (4), 0 lines removed |
| anchors | all unique at their turn |
| gates | 16 gate lines and 17 gate bodies byte-identical; 12 other module files untouched |
| subsets `seat`, `life`, `life,bed`, `controller`, `seat,controller`, `life,bed,controller` | all exit 0 |
| real apply to a copy, then re-run | apply exit 0 with receipt; re-run REFUSED ("Sub01SeatTransition.h already exists") |
| tests (bundle, seat transition, life clips, controller grip fit) | 114 passed |

Root's 22 commits since fb7253a touch lamps, books, desk, shelves, editor guard and one controller verifier
(`ae012c5`, server-side only); none touches the staged generator or any anchor. **No adapter or bundle fix needed.**

Note: the bundle must run from this branch's `tools/` (main's `unreal_seat_transition_runtime.py`,
`validate_unreal_seat_contact.py`, `Sub01SeatTransition.h` and `inventory_native_life_clips.py` are older; main has
no life/bed/controller adapters). Run every importer below from the branch checkout too (the life importer imports
`inventory_native_life_clips.py` from its own directory, and only the branch copy accepts `--derived`).

## 2. Owner USkeleton (all adapters)

| Asset | Exact path | Status | Evidence |
|---|---|---|---|
| Owner mesh | `/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner` | **EXISTS** | main 178f52a `docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json` `body.mesh` (in-engine probe: 249148 vertices, 66 bones, `geometry_identity_verified: true`) |
| Owner USkeleton | `/Game/Sub01Hands/FBX/SUB01_OriginalOwner_Skeleton.SUB01_OriginalOwner_Skeleton` | **EXISTS** | same file `body.skeleton`; `identity_basis`: "Actual existing owner and DeskTyping USkeleton equality; historic import receipt absent after migration" |
| DeskTyping | `/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping` | **EXISTS** | the same in-engine equality; loaded by root's `unreal_audit_seat_contact.py`, `run_unreal_contact_*` |
| `unreal-fbx-hands-import.json` | `<project>/unreal-fbx-hands-import.json` | **ABSENT** (migration) | same `identity_basis`; every importer falls back to owner + DeskTyping equality |

## 3. Per-adapter assets

Status words: **EXISTS** = in-engine evidence committed; **MISSING** = no import receipt, tool run or commit message
on main or the branch says it was imported (git log origin/main -60 and a full `git log --grep` search found no
`Idle`, `Seating`, `GamingGrip` or `Life` import; `unreal-life-import`, `unreal-seating-import` and `SUB01_Idle`/
`SUB01_GamingGrip` occur only in the importer sources). Check MISSING assets on the server before importing; if one
exists, keep it only if its receipt is present and re-run the importer otherwise (both importers replace in place).

### Seat (`unreal_seat_transition_runtime.py`, `native_seating/Sub01SeatTransition.h`)

| Role | Required asset | Status | Source | Create with |
|---|---|---|---|---|
| StandToSit | `/Game/Sub01Hands/Seating/SUB01_SitDown.SUB01_SitDown` | MISSING | `web/room/mh_mx/room_mx_stand_to_sit.glb` | seating chain (S1–S3) |
| Sitting | `/Game/Sub01Hands/Seating/SUB01_Sitting.SUB01_Sitting` | MISSING | `web/room/mh_mx/room_mx_sitting.glb` | seating chain |
| SitToType | `/Game/Sub01Hands/Seating/SUB01_SitToType.SUB01_SitToType` | MISSING | `web/room/mh_mx/room_mx_sit_to_type.glb` | seating chain |
| SitToStand | `/Game/Sub01Hands/Seating/SUB01_GetUp.SUB01_GetUp` | MISSING | `web/room/mh_mx/room_mx_sit_to_stand.glb` | seating chain |
| DeskTyping | `/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping` (via renderer `HandsClips`) | EXISTS | — | — |

Seating chain (branch checkout `<B>`, project `<P>`):

```
S1 node <B>/tools/uncompress_unreal_glb.mjs <B>/web/room/char_mixamo.glb /tmp/owner.glb
S2 node <B>/tools/merge_unreal_skin_clips.mjs /tmp/owner.glb /tmp/seating-merged.glb \
     <B>/web/room/mh_mx/room_mx_stand_to_sit.glb <B>/web/room/mh_mx/room_mx_sit_to_stand.glb \
     <B>/web/room/mh_mx/room_mx_sitting.glb <B>/web/room/mh_mx/room_mx_sit_to_type.glb
   blender -b --python <B>/tools/export_unreal_seating_fbx.py -- /tmp/seating-merged.glb <P>/SourceAssets/SeatingFBX
S3 UnrealEditor-Cmd <P>/Sub01HomeLab.uproject -ExecutePythonScript="<B>/tools/unreal_import_seating_fbx.py" -unattended
   -> <P>/unreal-seating-import.json (owner, skeleton, 4 rows same_existing_skeleton: true, runtime_ready: false)
```

Config (no generator exists; append by hand only when `unreal-seating-import.json` has all four rows on
`SUB01_OriginalOwner_Skeleton` with `same_existing_skeleton: true`), `Config/DefaultGame.ini`:

```
[/Script/Sub01HomeLab.Sub01HomeCharacter]
+ValidatedHandsPostures=StandToSit
+ValidatedHandsPostures=Sitting
+ValidatedHandsPostures=SitToType
+ValidatedHandsPostures=SitToStand
```

Evidence/proofs: `private-audit/native-chair-surface.json` (copy main's
`docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json` byte-identical, or re-run
`unreal_chair_surface_audit.py`) → `private-audit/native-seat-contact.json` (`unreal_audit_seat_contact.py`, main) →
`private-audit/native-seat-evidence.json` (`python3 <B>/tools/unreal_seat_transition_runtime.py <P>`; refuses without
an accepted contact report) → typing contact profile `<P>/unreal-skinned-contact-audit.json`
(`unreal_audit_skinned_contact.py`, main; status UNKNOWN) → live `SUB01_SEAT_LIVE_MEASUREMENT` while typing.

Readiness: `NativeSeatVerified` / PC focus stay **false** until the live `ContactVerified` receipt. No file flips them.

### Life: Idle (`unreal_life_clips_runtime.py`, `native_life/Sub01LifeClips.h`)

| Role | Required asset | Status | Source | Create with |
|---|---|---|---|---|
| Idle | `/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle` (looping) | MISSING | `docs/proposed/standing-idle-retarget/stand_idle_ual_ik.glb` | life chain (L1–L4) |

Inventory dry-run done here (source only, not committed): branch `inventory_native_life_clips.py --extra
Idle=…stand_idle_ual_ik.glb --derived LieDown/SleepLoop/GetUp=…corrected.in_place.glb` returns
`missing_roles: []` and verdict **Candidate** for all four ("standing, stationary, loops"; the bed ones keep the
visible `derived_library_asset` label).

```
L1 python3 <B>/tools/inventory_native_life_clips.py \
     --extra Idle=docs/proposed/standing-idle-retarget/stand_idle_ual_ik.glb \
     [--derived LieDown=docs/proposed/bed-transition/SUB01_LieDown.corrected.in_place.glb \
      --derived SleepLoop=docs/proposed/bed-transition/SUB01_SleepLoop.corrected.in_place.glb \
      --derived GetUp=docs/proposed/bed-transition/SUB01_GetUp.corrected.in_place.glb] \
     --out <P>/private-audit/native-life-clips-inventory.json          (run in <B>)
L2 node <B>/tools/merge_unreal_skin_clips.mjs /tmp/owner.glb /tmp/life-merged.glb \
     <B>/docs/proposed/standing-idle-retarget/stand_idle_ual_ik.glb [+ the three bed GLBs]
L3 blender -b --python <B>/tools/export_unreal_life_fbx.py -- /tmp/life-merged.glb <P>/SourceAssets/LifeFBX \
     <P>/private-audit/native-life-clips-inventory.json Idle=docs/proposed/standing-idle-retarget/stand_idle_ual_ik.glb \
     [LieDown=… SleepLoop=… GetUp=…]
L4 UnrealEditor-Cmd <P>/Sub01HomeLab.uproject -ExecutePythonScript="<B>/tools/unreal_import_life_fbx.py" -unattended
   -> <P>/unreal-life-import.json (parity-checked rows, runtime_ready: false)
L5 python3 <B>/tools/unreal_life_clips_runtime.py config <P>/private-audit/native-life-clips-inventory.json \
     <P>/unreal-life-import.json /tmp/life.ini      (append /tmp/life.ini to Config/DefaultGame.ini)
```

Expected config: `IdleClipPath=/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle` and `+ValidatedHandsPostures=Idle`
(the tool refuses a role whose import row does not match the inventory sha). Readiness: Idle plays only when the
renderer itself binds and chooses `HandsClips["Idle"]` (root d2a7dc7 plays a bound Idle at rate 1); confirm with a
native capture.

### Life: bed (`unreal_bed_root_motion.py`, needs life)

| Role | Required asset | Status | Source |
|---|---|---|---|
| LieDown | `/Game/Sub01Hands/Life/SUB01_LieDown.SUB01_LieDown` | MISSING | `docs/proposed/bed-transition/SUB01_LieDown.corrected.in_place.glb` |
| SleepLoop | `/Game/Sub01Hands/Life/SUB01_SleepLoop.SUB01_SleepLoop` | MISSING | `docs/proposed/bed-transition/SUB01_SleepLoop.corrected.in_place.glb` |
| GetUp | `/Game/Sub01Hands/Life/SUB01_GetUp.SUB01_GetUp` | MISSING | `docs/proposed/bed-transition/SUB01_GetUp.corrected.in_place.glb` |

Created by the bracketed parts of L1–L4. Config: use the bed tool instead of L5 when importing bed roles —
`python3 <B>/tools/unreal_bed_root_motion.py config <inventory> <P>/unreal-life-import.json /tmp/life.ini`
(bed `+ValidatedHandsPostures=LieDown/SleepLoop/GetUp` only all together). Proofs:
`private-audit/native-bed-surface.json` (`unreal_bed_surface_audit.py`, branch) → `fit_bed_placement.py` proposal
(never accepted) → `private-audit/native-life-bed-evidence.json` (**no producer exists**: needs a server placement
audit) → `private-audit/native-life-root-paths.json` (`unreal_bed_root_motion.py stage-paths
docs/proposed/bed-transition/SUB01_bed_mesh_root_paths.json <inventory> <P>/unreal-life-import.json <P>`).
Readiness: `SUB01_LIFE_READY … bedMeasured=1 placement=1` stays false until then; without root paths the native
side logs `SUB01_LIFE_ROOT_MOTION_REFUSED` and the bed roles must not be validated. **Recommended:** import Idle
alone first; defer the bed roles until the bed evidence producer exists.

### Controller (`unreal_controller_play_runtime.py`)

| Item | Required | Status | Evidence / source |
|---|---|---|---|
| Grip clip | `/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip`, owner USkeleton, 152 keys, native 5.0333 s | MISSING | source `docs/proposed/controller-play/SUB01_GamingGrip_derived.glb` (sha `bf31d645…`, 152/152 frames, `verified: false`) |
| Raw capture | `/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming` | EXISTS (not played by the adapter) | root diagnostics: `run_unreal_native_window_recording.py`, `unreal_controller_grip_diagnostic.py` (dbae3e1), `native-controller-intents.md` |
| Prop mesh | `physical_assembly.mesh` from `<P>/private-audit/native-controller-asset.json`, under `/Game/Sub01Home/Devices/Controller/V_8134769e2680/` | UNKNOWN (receipt not committed) | `unreal_import_controller_prop.py` (main dbae3e1) |

**New in this commit** (no importer existed):

- `tools/export_unreal_gaming_grip_fbx.py` — Blender, modelled on `export_unreal_life_fbx.py`; refuses unless the
  clip is byte-identical to the committed derived GLB and has 152 keys; writes `GamingGrip.fbx` and
  `gaming-grip-fbx-audit.json` (`sub01.gaming-grip-fbx-audit.v1`). Not run in Blender here.
- `tools/unreal_import_gaming_grip.py` — UE, modelled on `unreal_import_life_fbx.py`: existing owner only (receipt
  or owner + DeskTyping equality), structure parity then per-clip structural-root parity via
  `native_life_skeleton_parity.py`, exact object path, duration within 2/30 s; on any mismatch it deletes the
  imported asset and raises without a receipt. Receipt `<P>/unreal-gaming-grip-import.json` carries the row the
  adapter's `config` requires (`role: Gaming`, `same_existing_skeleton: true`, `source_fbx_sha256 84dfc60a…`,
  `derived_glb_sha256 bf31d645…`), with `controller_grip_verified/sofa_contact_verified/runtime_ready: false`.
  Fake-unreal tests: `tests/test_unreal_import_gaming_grip.py` (15), including that the receipt passes
  `config_fragment` with accepted evidence and is refused without it.

```
C0 (optional, root ae012c5) python3 tools/verify_written_controller_grip_all_frames.py --helpers … \
     --derived docs/proposed/controller-play/SUB01_GamingGrip_derived.glb \
     --report docs/proposed/controller-play/SUB01_GamingGrip_derived.report.json \
     --source docs/proposed/controller-capture/gaming-owner.glb --owner … --controller web/room/controller.glb --cache … --output …
C1 node <B>/tools/merge_unreal_skin_clips.mjs /tmp/owner.glb /tmp/grip-merged.glb \
     <B>/docs/proposed/controller-play/SUB01_GamingGrip_derived.glb
C2 blender -b --python <B>/tools/export_unreal_gaming_grip_fbx.py -- /tmp/grip-merged.glb \
     <P>/SourceAssets/ControllerFBX <B>/docs/proposed/controller-play/SUB01_GamingGrip_derived.glb
C3 UnrealEditor-Cmd <P>/Sub01HomeLab.uproject -ExecutePythonScript="<B>/tools/unreal_import_gaming_grip.py" -unattended
   -> <P>/unreal-gaming-grip-import.json
C4 (prop, if its receipt is absent) root's unreal_import_controller_prop.py -> <P>/private-audit/native-controller-asset.json
C5 python3 <B>/tools/unreal_controller_play_runtime.py config <P> <P>/unreal-gaming-grip-import.json /tmp/controller.ini
   -> `+ValidatedHandsPostures=Gaming` ONLY with accepted evidence; refuses now (evidence missing). Do not hand-write it.
```

Proofs: `private-audit/native-sofa-surface.json` (**no audit tool exists**; spec `sofa-controller-play.md` §4.1) →
sofa contact report + placement (**no producer**) → `private-audit/native-controller-play-evidence.json`
(`unreal_controller_play_runtime.py evidence <P> GRIP_REPORT.json SOFA_CONTACT.json PLACEMENT.json`) →
`private-audit/native-controller-play-runtime-proof.json` (`sub01.native-controller-play-runtime-proof.v1`,
**no producer**). Readiness: `ControllerPlayReady()` / `SUB01_CONTROLLER_PLAY_READY ready=1` stays false; plus a
correlated Minecraft input ACK on root's TV input path.

## 4. Ordered renderer steps (after root's office bundle)

1. **Office bundle done** (root): lamps/books/desk/shelves imports saved; editor quiescent.
2. **Stage**: `python3 <main>/tools/stage_unreal_home_runtime.py <P>` from main 2c61c93 (or later, re-verify).
3. **Bundle**: `python3 <B>/tools/install_native_adapters_bundle.py <P>/Source/Sub01HomeLab --dry-run` → expect the
   §1 table; then apply without `--dry-run`; keep `<P>/private-audit/native-adapters-install-receipt.json`.
4. **Build** (official `Build.sh`, editor target). Expect `SUB01_SEAT_ROLE_MISSING` ×4,
   `SUB01_SEAT_TRANSITION_READY … contactEvidence=0`, `SUB01_LIFE_READY …`, `SUB01_LIFE_ROOT_MOTION_REFUSED`,
   `SUB01_CONTROLLER_PLAY_READY ready=0 refusal=…`. Confirm walk/gaze/privacy/Minecraft unchanged.
5. **Imports** (editor, one at a time, each receipt kept): S1–S3 seating; L1–L4 Idle (bed roles deferred);
   C1–C3 grip; C4 prop if needed.
6. **Config** (`Config/DefaultGame.ini`, under `[/Script/Sub01HomeLab.Sub01HomeCharacter]`): the four seat lines;
   the L5 output. No Gaming or bed lines yet (their tools refuse).
7. **Rebuild/restart** native; expect seat roles and Idle bound (no `SUB01_SEAT_ROLE_MISSING`).
8. **Proofs** in order: seat chain (§3 seat) → bed chain (when producers exist) → sofa/controller chain.
   Native captures of each, compared by eye with the SimbasJungles reference.
9. **Readiness** only from live logs with `HOME_NATIVE_REQUIRED=1`: seat `ContactVerified` + PC focus while
   typing; life `placement=1`; controller `ready=1` + correlated Minecraft ACK. Nothing here sets a flag true.

## 5. Rollback

1. Remove the appended `ValidatedHandsPostures` / `IdleClipPath` lines from `Config/DefaultGame.ini`.
2. Re-stage from main (step 2); delete `Source/Sub01HomeLab/Sub01SeatTransition.h` and `Sub01LifeClips.h`; delete
   the install receipt; rebuild.
3. Imported assets are inert without config and adapters. To remove them: `EditorAssetLibrary.delete_directory`
   on `/Game/Sub01Hands/Seating`, `/Game/Sub01Hands/Play`, and the `SUB01_Idle`/bed assets in `/Game/Sub01Hands/Life`,
   plus their receipts and `SourceAssets/{SeatingFBX,LifeFBX,ControllerFBX}`. Never touch `/Game/Sub01Hands/FBX`.

## 6. Gaps (honest)

- No seat config generator: the four seat lines are hand-appended after checking the receipt.
- Typing contact profile (`unreal-skinned-contact-audit.json`) and `native-seat-contact.json`: not committed; UNKNOWN.
- Bed: no producer for `native-life-bed-evidence.json` (server placement audit).
- Sofa: no `native-sofa-surface.json` audit tool, no sofa contact/placement producer, no runtime-proof producer.
- `export_unreal_gaming_grip_fbx.py` was not run in Blender and `unreal_import_gaming_grip.py` not in UE (fake tests only).
- The seat adapter does not bind the seated-idle/typing-seated GLBs in `docs/proposed/seat-pose-fit/`.
- Controller prop receipt not committed; its presence on the server is UNKNOWN.
- Every readiness flag stays false; no capture, seat, contact or input proof exists.
