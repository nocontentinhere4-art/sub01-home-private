# Native adapters install runbook: seat, life (+bed), controller

Private; source only. Nothing here was compiled or run in Unreal, and no runtime, Runpod or deploy action
was taken. Root is the sole UE operator; this is the renderer's one-command install plus the inventory of
what each adapter still needs before any readiness gate may turn true.

## What was checked against root's CURRENT main (fb7253a)

- Root main and this branch stage **byte-identical** sources: `tools/stage_unreal_home_runtime.stage()` from
  a detached `origin/main` worktree and from the branch produce the same `Source/` tree (`diff -r`: no
  differences). Root's walk-rate line on main is exactly the adapters' anchor:
  ` Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?float(Sub01FirstPersonMotion::AuthoredWalkRate(Speed)):(PlayingIdle?1.f:0.f)):1.f;`
- All 18 tested install orders (every permutation of seat/life/bed/controller with bed after life, plus
  seat, life, controller alone and the pairs seat+controller, life+controller and controller+seat) apply on
  main's staged sources. Every anchor is unique (count 1) at its turn. The result is additive: every original
  line survives, unchanged and in order. All gate lines and gate bodies (below) stay byte-identical.
- **One fix in an adapter**, in `tools/unreal_seat_transition_runtime.py`. Its hands-proxy edit used to append
  `int32 SeatSerial=…;` to the *same line* as root's ` float Progress=1;`, which edited that line.
  The declarations now go on their own new line, so the C++ means the same. No anchor failed on main.
- No lamps, books, texture or rail file was touched.

## One command

```
python3 tools/install_native_adapters_bundle.py <project>/Source/Sub01HomeLab --dry-run      # prints the diff summary
python3 tools/install_native_adapters_bundle.py <project>/Source/Sub01HomeLab                # applies
        [--only seat,life,bed,controller] [--receipt PATH] [--show-diff]
```

**Fixed order:** seat → life → bed → controller. `bed` is `tools/unreal_bed_root_motion.py`; it extends
the life adapter's bed phases, so it needs `life`. Each hook goes in directly after root's rate line, so in
`Tick` they run in this order:

1. the renderer's rate choice;
2. `UpdateControllerPlay`;
3. `UpdateLifeClips`;
4. `ApplySeatAnimation`.

Each hook does nothing unless its own activity is active, and the activities exclude each other:

- seat: desk `use_computer`;
- life: Idle when the renderer chose Idle, or a sleep command;
- controller: sofa `play_console`.

The movement stops are all inserted after root's privacy and stale-command checks, and before root's
` if(!LiveHomePath.Num()){…SetOperatorFocus(…)` line.

**Dry-run summary on main's staged sources:**

| File | Lines added | Insertions | Lines removed |
|---|---|---|---|
| `Sub01HomeLab.h` | 44 | 2 | 0 |
| `Sub01HomeLab.cpp` | 564 | 6 | 0 |
| `Sub01HomeHands.h` | 19 | 1 | 0 |
| `Sub01HomeHands.cpp` | 14 | 4 | 0 |

It also copies `Sub01SeatTransition.h` and `Sub01LifeClips.h`. It finds 16 gate lines and 17 gate bodies
byte-identical, and leaves 12 other module files untouched.

**The tool refuses (exit 2, nothing written) when:**

- the module or one of its four generated sources is missing;
- an adapter file is missing;
- a selected adapter is already (even partly) installed, or its header already exists in the module;
- `bed` is selected without `life`;
- any anchor count is not 1;
- any original line was edited, moved or removed;
- a gate line or gate body changed;
- a source changed between planning and writing.

**Receipt:** `<project>/private-audit/native-adapters-install-receipt.json`
(`sub01.native-adapters-install-receipt.v1`). It holds:

- the order;
- the branch commit, and whether the adapter files are dirty;
- the sha256 of each adapter `.py` and header, plus the bundle and `validate_unreal_seat_contact.py`;
- the anchors used at each step, with their counts;
- the sha256 of each gate line and gate body;
- the before/after sha256 of the four sources and the sha256 of every other module file;
- `readiness_claimed: false`.

**Root gates kept byte-identical (asserted on every install):**

- **Lines:**
  - walk: the rate line, `Moving` and `PlayingIdle`;
  - gaze smoothing: the three `Sub01FirstPersonMotion::SmoothAngle` lines, including the walk input;
  - live-home privacy: the revoke line, the stale-command stop, and the PC operator-focus line;
  - the Desk interact seat gate;
  - the `TickMinecraftTVInput();` and `UpdateNativePCPrivacy();` calls;
  - the privacy field in `PollLiveHome`;
  - the `Sub01FirstPersonMotionPolicy.h` and `Sub01NativeFixtureEmissionPolicy.h` includes;
  - `TArray<FName> ValidatedHandsPostures;`.
- **Whole bodies:**
  - `Forward`, `Right` and `Interact`;
  - `SetHandsPosture`, the posture whitelist;
  - `UpdateNativePCPrivacy` and `TryNativeHomeDevice`;
  - `PollLiveHome` and `NativeFeedbackSeatReady`;
  - `PublishPrivateNativeCameraPrivacy`, the privacy blackout receipt;
  - `PrepareNativeFixtureEmission` and `ApplyNativeFixtureEmission`;
  - `FSub01MinecraftTVInput`, `FocusMinecraftTV`, `PublishMinecraftTVReceipt`, `SendMinecraftTVInput`,
    `TickMinecraftTVInput` and `ReleaseMinecraftTVInput`.
- **Files:** every non-generated module file (the policies, the PC/device bridges and `Build.cs`) stays
  byte-identical.

The bundle runs from this branch's `tools/`, because it imports `validate_unreal_seat_contact.py` from there.
Main has an older copy of that file, and main lacks the life, bed and controller adapters entirely.

## Prerequisites and gaps

Status as committed in git: **PRESENT** means committed in this branch or root's main (path cited).
**ABSENT** means nothing is committed and no producer has run. **UNKNOWN** means a server-side artefact that
git cannot show, with no receipt committed.

### Seat (`unreal_seat_transition_runtime.py` + `native_seating/Sub01SeatTransition.h`)

| Prerequisite | Exact value | Status |
|---|---|---|
| Owner mesh / USkeleton | `/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner` | UNKNOWN (root's existing import; `unreal-fbx-hands-import.json` not committed) |
| Seat clips (owner USkeleton) | `/Game/Sub01Hands/Seating/SUB01_SitDown`, `SUB01_Sitting`, `SUB01_SitToType`, `SUB01_GetUp`, bound as roles StandToSit, Sitting, SitToType, SitToStand (`SEAT_ROLE_ASSETS`, 5d974da) | UNKNOWN. `unreal_import_seating_fbx.py` is on main (bbdb80b, f5bd04c); no `unreal-seating-import.json` is committed. Note: `native-seat-transition.md` still names them `SUB01_{StandToSit,…,SitToStand}`; the code loads the names above. |
| Typing clip | renderer `HandsClips["DeskTyping"]` = `/Game/Sub01Hands/FBX/SUB01_DeskTyping` | UNKNOWN (root import) |
| Config | `+ValidatedHandsPostures=StandToSit`, `=Sitting`, `=SitToType`, `=SitToStand` in `[/Script/Sub01HomeLab.Sub01HomeCharacter]` | ABSENT |
| Keyboard contact profile | `TypingProfileReady`: 301-sample profile bound to DeskTyping, body at the audited transform (0.05 cm / 0.05°) | UNKNOWN (root's contact-profile runtime is staged; no accepted profile committed) |
| `private-audit/native-chair-surface.json` | broad cushion ≥ 1000 cm² | PRESENT as `docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json` (main 178f52a). It has `errors: []`, 150 cushion triangles and 2345.2 cm². Copy it to `private-audit/` unchanged: its text is the chair revision. |
| `private-audit/native-seat-contact.json` | accepted contact report (`unreal_audit_seat_contact.py`) | ABSENT |
| `private-audit/native-seat-evidence.json` | `python3 tools/unreal_seat_transition_runtime.py <project>` (refuses without an accepted contact report) | ABSENT |
| `SUB01_SeatedIdle`, `SUB01_DeskTypingSeated` (+ `SitDownSeated`, …) | GLBs in `docs/proposed/seat-pose-fit/` (trial, `verified: false`; SeatedIdle `all_gates_pass: true`) | PRESENT as source; import ABSENT. **Gap:** the current seat adapter does **not** bind them. It loops `SUB01_Sitting` and types on `HandsClips["DeskTyping"]`. Binding them needs a later adapter change to `SEAT_ROLE_ASSETS` and the typing slot, after their native audits pass (`seat-pose-fit.md` step 7). |

**Readiness:**

- `NativeSeatVerified` and PC focus are set **only** from the live `ContactVerified`. That needs Typing with
  `TypingProfileReady`, a quantitative skin receipt this tick (`SUB01_SEAT_LIVE_MEASUREMENT`) and an
  unchanged chair revision.
- **No file flips it.** `native-seat-evidence.json` only lets the receipt be checked. Without it, sitting
  still works on the measured cushion, and contact and PC focus stay false.

### Life: Idle and bed (`unreal_life_clips_runtime.py` + `native_life/Sub01LifeClips.h`, then `unreal_bed_root_motion.py`)

| Prerequisite | Exact value | Status |
|---|---|---|
| Idle clip | `/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle`, owner USkeleton, looping | Converted candidate PRESENT: `docs/proposed/standing-idle-retarget/stand_idle_ual_ik.glb` passes `verify_life_idle_candidate.py`; root's 178f52a "Prepare verified owner Idle conversion" adds the export/import tools. Import UNKNOWN: no `unreal-life-import.json` is committed. The committed inventory `docs/proposed/native-life-clips-inventory.json` still lists Idle as missing (`missing_roles: GetUp, Idle, LieDown`); it must be re-run with `--extra Idle=…`. |
| Bed clips | `/Game/Sub01Hands/Life/SUB01_LieDown`, `SUB01_SleepLoop`, `SUB01_GetUp` | PRESENT as source: `docs/proposed/bed-transition/SUB01_*.corrected.in_place.glb`, labelled `derived_library_asset` and "NOT accepted". Import ABSENT. Inventory acceptance needs `--derived ROLE=…` (`bed-transition-pipeline.md` §9). |
| Config | `IdleClipPath=/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle`, `+ValidatedHandsPostures=Idle`; bed roles `+ValidatedHandsPostures=LieDown/SleepLoop/GetUp` only all together (`unreal_bed_root_motion.py config INVENTORY UNREAL_LIFE_IMPORT OUT.ini`) | ABSENT |
| `private-audit/native-life-clips-inventory.json` | `inventory_native_life_clips.py --extra Idle=… --derived …` | ABSENT on the server; the committed copy predates Idle and the bed clips |
| `<project>/unreal-life-import.json` | `unreal_import_life_fbx.py` | UNKNOWN / not committed |
| `private-audit/native-bed-surface.json` | measured mattress (`unreal_bed_surface_audit.py`, branch only) | ABSENT |
| `private-audit/native-life-bed-evidence.json` | accepted placement for this exact bed report (`fit_bed_placement.py`) | ABSENT |
| `private-audit/native-life-root-paths.json` | `unreal_bed_root_motion.py stage-paths docs/proposed/bed-transition/SUB01_bed_mesh_root_paths.json …` (only when every bed role binds the exact clip) | ABSENT (the source paths file is PRESENT) |

**Readiness:**

- **Idle** plays only when the renderer itself bound and chose `HandsClips["Idle"]`, which needs the config
  lines above.
- **Bed:** `SUB01_LIFE_READY … bedMeasured=1 placement=1` needs `native-bed-surface.json` plus
  `native-life-bed-evidence.json`, and all three bed clips bound.
- Without `native-life-root-paths.json`, `SUB01_LIFE_ROOT_MOTION_REFUSED` is logged, and the bed roles
  must not be validated.

### Controller (`unreal_controller_play_runtime.py`)

| Prerequisite | Exact value | Status |
|---|---|---|
| Derived grip clip | `/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip`, owner USkeleton, 152 frames at 30 fps | Source PRESENT: `docs/proposed/controller-play/SUB01_GamingGrip_derived.glb` (`all_frames_pass`, 152/152, `verified: false`, sha `bf31d645…`). Import ABSENT, and **no import tool for `/Game/Sub01Hands/Play` exists** on the branch or on main. **Gap:** root must import it with a row carrying `role: Gaming`, `same_existing_skeleton: true`, `source_fbx_sha256: 84dfc60a…fc7f` and `derived_glb_sha256: bf31d645…`. |
| Raw Gaming capture | `/Game/Sub01Hands/Controller/SUB01_Gaming` (root's grip diagnostic) | Source PRESENT: `docs/proposed/controller-capture/gaming-owner.glb` (main 710f887). Native import UNKNOWN; the adapter does not play this clip. |
| Controller prop | the mesh named by `private-audit/native-controller-asset.json` → `physical_assembly.mesh`, under `/Game/Sub01Home/Devices/Controller/V_8134769e2680/…`. It is **not** `/Game/Sub01Home/Props/SUB01_Controller`. The schema (`sub01.native-controller-asset.v1`) and `source_sha256` (`c034a144…`) match root's main `unreal_import_controller_prop.py`. | Tool PRESENT (main dbae3e1, f2e9582); receipt UNKNOWN / not committed |
| Config | `+ValidatedHandsPostures=Gaming` (`unreal_controller_play_runtime.py config <project> IMPORT.json OUT.ini`; only with accepted evidence) | ABSENT |
| `private-audit/native-sofa-surface.json` | measured sofa seat ≥ 4000 cm², `errors: []` | ABSENT (no audit tool committed; spec in `sofa-controller-play.md` §4.1) |
| `private-audit/native-controller-play-evidence.json` | `… evidence <project> GRIP.json SOFA_CONTACT.json PLACEMENT.json` | ABSENT (needs sofa contact + placement) |
| `private-audit/native-controller-play-runtime-proof.json` | `sub01.native-controller-play-runtime-proof.v1`, ≥ 152/152 native frames passing, penetration ≥ −0.3 cm, native capture sha | ABSENT |

**Readiness:** `ControllerPlayReady()` needs all of these:

- the accepted evidence;
- the runtime proof;
- the clip bound through `ValidatedHandsPostures` on the same skeleton;
- the prop mesh;
- the Hand and Head bones.

**The file that flips it last:** `native-controller-play-runtime-proof.json`. Minecraft input stays on root's
existing TV input path. A correlated Minecraft ACK, the private-input proof, is still root's.

**Readiness stays false after this install.** The bundle writes no evidence, config or proof. Seat contact,
bed placement, sofa contact and controller input remain unproven until the files above exist and the live
native receipts (`SUB01_SEAT_LIVE_MEASUREMENT` with contact, `SUB01_LIFE_READY … placement=1`,
`SUB01_CONTROLLER_PLAY_READY ready=1`) are captured. Keep `HOME_NATIVE_REQUIRED=1` in effect.

## Renderer runbook (exact order)

1. **Furniture first.** Finish root's current lamps, books, texture and rail work and its imports. The
   bundle does not touch them.
2. **Stage from root's main.**
   `python3 tools/stage_unreal_home_runtime.py <project>` from root's current main checkout. Main and this
   branch stage identically today.
3. **Install.**
   - Dry run from this branch's checkout:
     `python3 <branch>/tools/install_native_adapters_bundle.py <project>/Source/Sub01HomeLab --dry-run`.
     Expect the table above: four files, 0 removed, 16 gate lines and 17 gate bodies byte-identical.
   - Then apply: `python3 <branch>/tools/install_native_adapters_bundle.py <project>/Source/Sub01HomeLab`.
   - Keep `private-audit/native-adapters-install-receipt.json`.
4. **Build** with the official `Build.sh` (editor target; the seat's live measurement is `WITH_EDITOR`).
   - Expected first-run logs: `SUB01_SEAT_TRANSITION_READY … contactEvidence=0`, `SUB01_LIFE_READY …`,
     `SUB01_LIFE_ROOT_MOTION_REFUSED` and `SUB01_CONTROLLER_PLAY_READY ready=0 refusal=…`.
   - Every refusal is expected until the proofs exist.
   - Confirm root's walk, gaze, privacy and Minecraft behaviour is unchanged.
5. **Imports and config** (server, root), each with its receipt:
   - seating clips → `unreal-seating-import.json`;
   - Idle (and the bed clips) → inventory, then `unreal-life-import.json`;
   - `SUB01_GamingGrip` → import row;
   - controller prop → `native-controller-asset.json`.
   - Then append only the adapter-generated `ValidatedHandsPostures` fragments.
6. **Audits and proofs to capture, in order:**
   1. `native-chair-surface.json` (committed copy) → `native-seat-contact.json` → `native-seat-evidence.json`,
      then the live typing receipt.
   2. `native-bed-surface.json` → `native-life-bed-evidence.json` → `native-life-root-paths.json`.
   3. `native-sofa-surface.json`, then sofa contact and placement → `native-controller-play-evidence.json` →
      `native-controller-play-runtime-proof.json`.
   4. Native captures of each, compared by eye against the SimbasJungles reference.
7. **Readiness checks.** Claim an activity ready only with `HOME_NATIVE_REQUIRED=1` and the live logs:
   - **seat:** `ContactVerified` and `NativeSeatVerified` with PC focus while typing;
   - **life:** `LifeReady` with `placement=1`;
   - **controller:** `ControllerPlayReady ready=1`, plus a correlated Minecraft input ACK.

   A source test or a passing dry-run is not readiness.

**Rollback:**

1. Re-run step 2: `stage()` overwrites the four generated sources from root's main.
2. Delete `Sub01SeatTransition.h` and `Sub01LifeClips.h` from `Source/Sub01HomeLab`. They hold no UCLASS
   and are unused once the sources are re-staged, but remove them so the next bundle run is not refused.
3. Remove any appended adapter `ValidatedHandsPostures`/`IdleClipPath` lines and the install receipt.
4. Rebuild.

Assets and `private-audit/` evidence files are inert without the adapters.
