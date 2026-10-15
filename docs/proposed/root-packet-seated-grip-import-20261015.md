# Root dependency packet: seated clips and Gaming grip, export/import (2026-10-15)

Source only. Nothing here has been run in Blender or Unreal. Branch `claude/friendly-wozniak-dsxmyz`, packet written at `38de0fb`.
Integrate by path, no bulk merge. For the files marked "differs" below, main has not changed them since the merge base `1bbb25d`, so the branch version is strictly newer and can be copied over as is.

## What is importable

| role | asset | GLB sha256 | actual-chair verdict |
|---|---|---|---|
| SeatedIdle | /Game/Sub01Hands/Seating/SUB01_SeatedIdle | 57ba5e1be7a392b3889c8a875f993d39a808fee87f12a4e25d6f70a62b47a156 | pass |
| SitDownSeated | /Game/Sub01Hands/Seating/SUB01_SitDownSeated | a0b362324af7861e414730fed9175b6c72b88de5a525bce14ef113abdea25104 | pass (68/68 frames, seam into SeatedIdle continuous) |
| GetUpSeated | /Game/Sub01Hands/Seating/SUB01_GetUpSeated | 89f6b246e39992b97121d91d65ca537efa8d9516b95aa1a7e8b8bd0d124cdac7 | pass (63/63 frames, seam from SeatedIdle continuous) |
| DeskTypingSeated / SitToTypeSeated / TypeToSitSeated | (never imported) | 97fd8489… / ed46fd3e… / d25496c6… | fail on the actual chair; refused by the importer |
| Gaming grip | /Game/Sub01Hands/Play/SUB01_GamingGrip | bf31d64518d85f6eefd8150009a758ddddc95ca6afd63d5d83bdf29a2dcdaaf9 | derived grip, 152/152 source frames |

Typing stays on the renderer's `/Game/Sub01Hands/FBX/SUB01_DeskTyping`. The seated importer never writes under `/Game/Sub01Hands/FBX`.

## Files to take

**Entry points**
- `tools/export_unreal_seated_fit_fbx.py` (absent on main)
- `tools/unreal_import_seated_fit_fbx.py` (absent on main): staged import, never replaces an existing asset, `save_asset` result checked (2415e50), actual-chair pins (0ea80c2)
- `tools/export_unreal_gaming_grip_fbx.py` (absent on main)
- `tools/unreal_import_gaming_grip.py` (absent on main): staging fix 8cc8fd7, save-failure fix 2415e50
- `tools/install_default_game_ini.py` (absent on main)

**Committed fit data**
- the whole `docs/proposed/seat-pose-fit/` folder: GLBs, per-clip reports, `seat-pose-fit.report.json` (sha 881ecf13…), `chair-reposition-proposal.json`
- `docs/proposed/controller-play/SUB01_GamingGrip_derived.glb` and its report

**Python import closure** (computed from the entry points)
- `tools/unreal_seat_transition_runtime.py`: differs; branch is newer
- `tools/inventory_native_life_clips.py`: differs; branch is newer
- `tools/validate_unreal_seat_contact.py`: differs; branch is newer
- `tools/unreal_controller_play_runtime.py`, `tools/fit_controller_grip.py`, `tools/export_seat_fit_source.py`, `tools/life_gltf.py`, `tools/unreal_life_clips_runtime.py` (needed by the ini installer): absent on main
- `tools/native_life_skeleton_parity.py`, `tools/stage_first_person_assets.py`, `tools/validate_unreal_contact_profile.py`, `tools/uncompress_unreal_glb.mjs`, `tools/merge_unreal_skin_clips.mjs`: same as main

**Tests:** `tests/test_seated_fit_import.py`, `tests/test_unreal_import_gaming_grip.py`, `tests/test_install_default_game_ini.py`.

**Adapter side (later).** `tools/native_seating/Sub01SeatTransition.h`, `tools/unreal_seat_transition_runtime.py` and `tools/install_native_adapters_bundle.py` are about to receive the committed-verdict slot-binding guard. Take the adapter files from that follow-up commit. The export and import steps below do not depend on it.

## Server order (root)

```
# 0. check the source checkout first
python3 -m pytest -q tests/test_seated_fit_import.py tests/test_unreal_import_gaming_grip.py tests/test_install_default_game_ini.py

# 1. seated clips: all six roles are exported; the importer accepts only the 3 passing ones
node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb OWNER.glb
node tools/merge_unreal_skin_clips.mjs OWNER.glb SEATED.glb docs/proposed/seat-pose-fit/SUB01_DeskTyping_seated.glb \
  docs/proposed/seat-pose-fit/SUB01_SeatedIdle.glb docs/proposed/seat-pose-fit/SUB01_SitDown_seated.glb \
  docs/proposed/seat-pose-fit/SUB01_SitToType_seated.glb docs/proposed/seat-pose-fit/SUB01_TypeToSit_seated.glb \
  docs/proposed/seat-pose-fit/SUB01_GetUp_seated.glb
blender -b --python tools/export_unreal_seated_fit_fbx.py -- SEATED.glb <P>/SourceAssets/SeatedFitFBX
UnrealEditor-Cmd <P>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_seated_fit_fbx.py" -unattended
#    -> <P>/private-audit/unreal-seated-fit-import.json; log SUB01_SEATED_FIT_IMPORTED accepted=SeatedIdle,SitDownSeated,GetUpSeated

# 2. Gaming grip
node tools/merge_unreal_skin_clips.mjs OWNER.glb GRIP.glb docs/proposed/controller-play/SUB01_GamingGrip_derived.glb
blender -b --python tools/export_unreal_gaming_grip_fbx.py -- GRIP.glb <P>/SourceAssets/ControllerFBX \
  docs/proposed/controller-play/SUB01_GamingGrip_derived.glb
UnrealEditor-Cmd <P>/Sub01HomeLab.uproject -ExecutePythonScript="<repo>/tools/unreal_import_gaming_grip.py" -unattended
#    -> <P>/unreal-gaming-grip-import.json; log SUB01_GAMING_GRIP_IMPORTED (or _PRESERVED on a matching rerun)

# 3. config: check first, then apply
python3 tools/install_default_game_ini.py <P> --only seat,seated-fit,idle --dry-run
python3 tools/install_default_game_ini.py <P> --only seat,seated-fit,idle      # rollback: --restore
```

## What the importers guarantee (tested against a fake `unreal` module only)

- **Existing assets are never replaced or deleted.** An existing final asset is kept only when the existing receipt matches its source, skeleton and length. Otherwise the importer refuses and changes nothing.
- **Imports are staged.** Each run imports into its own staging path with `replace_existing=False`, verifies there, then renames onto final paths that did not exist before.
- **Failures clean up only this run's work.** A failed rename or failed `save_asset` deletes only this run's staging assets and its own renamed-in final paths. The previous receipt stays byte-identical.
- **The receipt is written last**, atomically, after every save succeeds. Readiness flags stay false.
- **Failed typing fits have no override.** Nothing can import, bind or write config for them.

## Still needs native proof

- The Unreal Python API behaviour: `rename_asset`, `list_assets`, `save_asset` return values, and the 60 Hz custom sample rate (not used by the 3 passing roles).
- How the SitDown → SeatedIdle → GetUp seams look on the real skin, and the foot stance drift (up to 9.6 cm, within the capture's own foot speed).
- Grip and sofa contact proof (`native-controller-play-runtime-proof.json`) and live controller input.
