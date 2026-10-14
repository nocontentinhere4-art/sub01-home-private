# Native life clips: standing idle and bed (proposal, source only)

## The problem

In the native Unreal home, the owner's full body stops on a walk frame whenever he stands still.

The renderer's generated runtime (`tools/unreal_home_hands_runtime.py`, staged into
`Sub01HomeLab.cpp`) already has two pieces for this:
- an `IdleClipPath`;
- a `Bind(TEXT("Idle"), IdleClipPath)`.

Its `Tick` picks `HandsClips["Idle"]` while the Walk posture is not moving. Two things stop that
from working:
- `tools/unreal_hands_bindings.py` never writes an Idle clip, so Idle is never bound.
- The renderer sets the rate to 0 for a stationary Walk posture, even when it picks Idle. A bound
  idle would freeze too.

There is no native bed or sleep clip at all.

## Files (all new; no existing file is edited)

| file | role |
|---|---|
| `tools/inventory_native_life_clips.py` | Read-only, pure Python inventory. It reads GLB JSON and binary accessors, and binary FBX through the existing `stage_first_person_assets.inspect_fbx`. |
| `docs/proposed/native-life-clips-inventory.json` | Its output for the repository's files. It is deterministic; a test checks it equals a fresh run. |
| `tools/native_life/Sub01LifeClips.h` | The engine-free state machine. Tests compile it with `-std=c++17 -Wall -Werror`. |
| `tools/unreal_life_clips_runtime.py` | The binding gate (config fragment), the bed gate, the C++ adapter and `install_module()`. |
| `tools/unreal_import_life_fbx.py` | The UE Python import onto the existing owner USkeleton. Server only. |
| `tools/export_unreal_life_fbx.py` | The Blender GLB to animation-only FBX converter for GLB sources. Server only. |
| `tests/test_native_life_clips.py` | 43 tests. |

## Clip inventory (measured from the files)

**The owner skeleton:** `web/room/char_mixamo.glb`, the skin `SUB01_OriginalOwner` was imported
from. It has 65 `mixamorig:` joints under a 0.01-scale `mixamo` node.

**What counts as "same skeleton":**
- the same 65 names and parents;
- every rest TRS within 1e-4;
- the same armature node.

**Units:** posture numbers are glTF metres above each clip's own floor.

| role | file | skeleton | length | posture | loops | verdict |
|---|---|---|---|---|---|---|
| Idle | `boy_idle.glb`, `boy_m_idle.glb`, `boy_moves.glb#stand_idle`, `char_v5.glb#idle` | other rigs (26/25/26 nodes; v5) | 4.0 / 3.35 / 2.5 / 15.33 s | – | – | **SkeletonMismatch.** They are AI-generated (Meshy, NVIDIA ARDY), a UAL library clip on the old rig, or the v5 rig. |
| LieDown | `mh_mx/room_bed_lie.glb` | owner, 65 | 16.967 s @ 30 Hz | standing (hips 0.919 m) to lying supine (hips 0.690 m, torso 98° from vertical) | no | **ProvenanceUnverified** |
| GetUp | `mh_mx/room_bed_wake.glb` | owner, 65 | 15.433 s @ 30 Hz | lying supine (hips 0.720 m) to standing (hips 0.917 m); hips travel 192.6 cm | no | **ProvenanceUnverified** |
| (sleep end) | `mh_mx/room_bedtime.glb` | owner, 65 | 29.2 s | desk stretch, walk, bed, lying; the web page holds its last frame | no | **ProvenanceUnverified** |
| SleepLoop | `desk_states/bed/sleep_side.glb` | owner, 65, rest error 0 | 6.633 s @ 30 Hz | lying on side, hips 0.852 m, torso 78° | yes (0.014 cm, 0.027°) | Candidate |
| SleepLoop | `desk_states/bed/sleep_back.glb` | owner, 65 | 6.633 s | lying supine, hips 0.875 m | yes (0.036 cm) | Candidate |
| SleepLoop | `desk_states/bed/sleep_back_idle.glb` | owner, 65 | 6.0 s | lying supine, hips 0.873 m | yes (0.066 cm, 0.11°) | Candidate |
| SleepLoop | `desk_states/bed/sleep_roll_to_back.glb` | owner, 65 | 14.333 s | side to back | no | NotLooping (a one-shot roll) |
| SleepLoop | `mh_v5/room_sleeping_idle.glb`, `room_laying_sleeping.glb` | v5 rig (80 nodes) | 17.6 / 1.7 s | – | – | **SkeletonMismatch.** These are genuine Mixamo captures, but only on the v5 rig. |

### Provenance

- **mh_mx bed transitions:** these are v5 clips carried onto the owner skeleton by
  `room_build/kimodo/mx_convert.mjs` (`web/room/mh_mx/README.md`).
  - `docs/design/room-v5/README.md` calls the v5 set "mocap clips". It also calls them
    "placeholders", and their source branch (`preview/mh-motion`) is not documented here.
  - They are not bone-for-bone: they carry translation tracks on every bone, up to **6.9 cm**
    from the owner's rest bone offsets.
  - They are therefore not accepted as genuine captures.
- **Sova bed clips (G23):** used with the author's permission
  (`web/room/desk_states/README.md`).
  - Their capture method is not documented, and their licence is preview-only.
  - They were fitted to the web room's bed, not the native house bed.

### Chain gaps

These are pose-shape gaps: joints in the hips' own frame, end pose against start pose. A
0.24 s crossfade cannot hide them.
- `room_bed_lie` end to `sleep_back_idle` start: 144.9 cm, with the hips 18 cm higher.
- `room_bed_lie` end to `room_bed_wake` start: 35.8 cm.

The source clips do not share one bed.

### Scan of every other owner-skeleton clip under `web/`

The only clip that is standing, stationary (≤ 5 cm of hips travel) and looping is
`house/assets/first-person/texting.glb`. It is the Phone activity, and it is never an idle
substitute. Seated clips are recognised by leg extension (hips-to-foot height against the
owner's thigh and shin length).

### What exists and what does not

- **No genuine standing idle exists on the owner skeleton in this repository.**
- **No genuine lie-down or get-up with documented provenance exists on the owner skeleton.**
- **No measured native bed surface exists.**
- **The repository has no FBX for idle or bed.** Mixamo FBX are kept out of Git by licence.

Nothing was synthesized, retargeted or hand-posed to fill these gaps.

## What the adapter does

### Standing

- Moving → the renderer's Walk, untouched.
- Still, with a bound Idle (the renderer's own `HandsClips["Idle"]`, so its `Bind` gate decides
  path, skeleton and `ValidatedHandsPostures`) → the adapter plays Idle looping at rate 1, so it
  breathes instead of freezing.
  - This happens only when the renderer itself chose Idle that tick
    (`Instance->TargetSequence == Idle`).
  - A seat clip chosen by the seat adapter is never overridden.
- Still, without Idle → the adapter refuses with an explicit reason:
  - `ClipMissing` / `SkeletonMismatch` / `NotValidated`, or `PostureGate`;
  - logged once as `SUB01_LIFE_IDLE_REFUSED <reason>`.

  It leaves the renderer's choice alone, so **the freeze remains until a genuine idle is
  imported**. It never holds a hand-picked frame.

### Bed

This path runs only when all of these hold:
- the activity is `sleep` at the `bed` node, with an empty path, fresh, not private, not blocked;
- the renderer's posture gate holds;
- all three of LieDown, SleepLoop and GetUp are loaded from `/Game/Sub01Hands/Life/SUB01_<Role>`,
  on the owner USkeleton, and listed in `ValidatedHandsPostures`;
- `private-audit/native-bed-surface.json` holds a mattress top of at least 15,000 cm²;
- `private-audit/native-life-bed-evidence.json` is accepted for that exact report text (its
  FNV-1a revision).

Otherwise the phase is `Refused` with one of:
`ClipMissing`, `SkeletonMismatch`, `NotValidated`, `BedUnmeasured`, `BedPlacementMissing`,
`Private`, `Blocked`, `PostureGate`, `ApproachTimeout` or `ClipUnavailable`. Each refusal is
logged as `SUB01_LIFE_PHASE 5 ... refusal=<reason>`.

### Bed sequence

1. **Aligning:** CharacterMovement input toward the measured approach (< 12 cm), then a bounded
   turn in place (103°/s, 3° tolerance) while still. It times out at 30 s.
2. **LyingDown:** the LieDown clip, non-looping, started once per serial. Playback counts only from
   what the proxy evaluated (sequence, serial, time). Movement is **disabled**
   (`DisableMovement`), and the live loop's path walking is gated by `LifeMovementLocked()`.
   - A LieDown that never starts within 1 s refuses and restores standing; the body never left the
     capsule.
   - A wake command during LieDown lets it finish, then gets up.
3. **Asleep:** SleepLoop, looping. A stale feed or privacy never wakes or moves him. Only a fresh,
   different command does.
4. **GettingUp:** the GetUp clip, non-looping, with movement still off. A GetUp that never starts
   keeps movement off (fail closed). When it has played, movement is set back to `MOVE_Walking`.
5. **In bed** (phases 2 to 4): the eye follows the captured Head bone, as the seat does. The full
   body stays on the capsule root (Walk attachment). It is never attached to the camera.

### What the added code never does

No added code sets the actor location, rotation or transform, teleports, sweeps the capsule
(`MoveUpdatedComponent`), touches bones or IK, adds procedural motion, edits `HandsClips` or
`ValidatedHandsPostures`, or calls `SetHandsPosture`. The tests enforce this by string checks on
the added code.

## Server steps (root; nothing here was run)

### Prerequisites

- An owner-approved genuine capture for each missing role, on the Mixamo skeleton:
  - **Idle:** for example a Mixamo standing breathing idle, downloaded "Without Skin" like the
    existing `Walking.fbx`, kept out of Git.
  - **Bed:** a lie-down and a get-up, plus a sleep loop that matches them (the Sova loops do not
    match the mh_mx transitions; see the chain gaps above).
- For the bed only:
  - a native mattress-top measurement, `private-audit/native-bed-surface.json`, in the chair
    report's shape with a `mattress_surface`;
  - a placement audit that plays the imported clips at a candidate approach and measures the skin
    against that mattress, then writes `native-life-bed-evidence.json`.

  **Neither tool exists yet.**

### Steps

1. **Inventory** (any Python, on the server's repository checkout):
   ```
   python3 tools/inventory_native_life_clips.py --extra Idle=/srv/private/Idle.fbx \
       --out <project>/private-audit/native-life-clips-inventory.json
   ```
   The `Idle` row must read `"verdict": "Candidate"`. `--extra` is the operator's explicit
   declaration that the file is a genuine capture; it is still measured and gated.
2. **Stage the FBX source.**
   - For an operator FBX (copied unchanged; its sha256 must be the inventoried one):
     ```
     python3 tools/unreal_life_clips_runtime.py audit-fbx <project>/private-audit/native-life-clips-inventory.json \
         <project>/SourceAssets/LifeFBX Idle=/srv/private/Idle.fbx
     ```
   - For accepted repository GLBs:
     ```
     node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb /tmp/owner.glb
     node tools/merge_unreal_skin_clips.mjs /tmp/owner.glb /tmp/life.glb <clip.glb> ...
     blender -b --python tools/export_unreal_life_fbx.py -- /tmp/life.glb <project>/SourceAssets/LifeFBX \
         <project>/private-audit/native-life-clips-inventory.json SleepLoop=web/room/desk_states/bed/sleep_back_idle.glb ...
     ```
3. **Import** (editor; the owner import report `unreal-fbx-hands-import.json` must already exist):
   ```
   UnrealEditor-Cmd <project>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_life_fbx.py" -unattended
   ```
   - Expected log, per role: `SUB01_LIFE_IMPORTED role=Idle path=/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle duration=…`
   - Output: `<project>/unreal-life-import.json`.
4. **Config fragment** (separate from `unreal_hands_bindings.py`, which stays the renderer's):
   ```
   python3 tools/unreal_life_clips_runtime.py config <project>/private-audit/native-life-clips-inventory.json \
       <project>/unreal-life-import.json /tmp/life-fragment.ini
   ```
   Exit code 3 with a refusal per role means nothing was proven, and nothing is written. With a
   proven idle the fragment is:
   ```
   [/Script/Sub01HomeLab.Sub01HomeCharacter]
   IdleClipPath=/Game/Sub01Hands/Life/SUB01_Idle.SUB01_Idle
   +ValidatedHandsPostures=Idle
   ```
   Put these lines in the same `[/Script/Sub01HomeLab.Sub01HomeCharacter]` section the renderer's
   bindings were written to (the class is `Config=Game`, so `Config/DefaultGame.ini`). Bed roles
   (`+ValidatedHandsPostures=LieDown|SleepLoop|GetUp`) are emitted only all together.
5. **Install order** (staged sources only; all anchors must be unique, otherwise the whole install
   refuses):
   1. `stage_unreal_home_runtime.stage(project)`;
   2. the seat adapter, if used: `unreal_seat_transition_runtime.install_module(...)`;
   3. `python3 tools/unreal_life_clips_runtime.py install <project>/Source/Sub01HomeLab`.

   The life install also works before the seat's; both orders are tested.
   - With seat first, `UpdateLifeClips` runs before `ApplySeatAnimation` in `Tick`, so a seat clip
     wins.
   - In the other order, Idle still never overrides a seat clip, because of the `TargetSequence`
     check.
6. **Build and run** with the official Build.sh, then check these log lines:
   - `SUB01_LIFE_READY idleBound=1 loaded=… sameSkeleton=… validated=… bedMeasured=0 … placement=0`
   - while standing still: `SUB01_LIFE_IDLE_OK`, or `SUB01_LIFE_IDLE_REFUSED <reason>`;
   - for a sleep command without a bed: `SUB01_LIFE_PHASE 5 clip=… refusal=BedUnmeasured movement=1`,
     or `ClipMissing` until the bed clips exist.

   Optional: `python3 tools/unreal_life_clips_runtime.py check-bed <project>` gives the same bed
   verdict offline.

## Verified, and not verified

**Verified here (CPU, no engine):**
- the inventory numbers above, from the actual files;
- the header's scenarios, compiled with clang++/g++ `-std=c++17 -Wall -Werror`:
  - idle when still, walk when moving, no rate-0 idle;
  - every refusal;
  - movement off throughout lying, asleep and getting up;
  - stale and privacy never wake him;
  - fail-closed starts;
- the Python and C++ FNV parity;
- the gates;
- an additive-only install on sources staged by `stage()`, alone and with the seat adapter in
  both orders.

**Not verified:**
- **Build and runtime:** the adapter has not been compiled against Unreal, and has not been run.
  No log line, render or capture exists. No visual result is claimed.
- **Idle import:** whether a downloaded idle imports onto `SUB01_OriginalOwner` without a rest
  mismatch. The importer checks the skeleton and duration only.
- **Crossfade:** the visual blend Walk ↔ Idle (the renderer's 0.24 s crossfade).
- **Body offset after GetUp:** at the end of GetUp the body stands where the clip's hips ended,
  not over the capsule. mh_mx `room_bed_wake` moves the hips 192.6 cm; `room_bed_lie` moves them
  125.3 cm. The renderer's next clip then pulls the body back over 0.24 s. A placement audit has
  to choose clips whose travel cancels, because moving the capsule to compensate would be a
  teleport.
- **Bed contact:** no lying height or contact against the native mattress is verified.
- **Bed tools:** the bed surface and placement tools do not exist.
