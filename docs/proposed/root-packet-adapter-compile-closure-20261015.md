# Root packet: full adapter-bundle compile closure (2026-10-15)

Branch `claude/friendly-wozniak-dsxmyz` at `022c399`. Checked against `origin/main` at `57d41bb`. This is source only: no readiness is claimed and no proof flag is set.

**Root's priority is the minimal seat + controller installer for current main.** That packet is in progress as `docs/proposed/root-packet-seat-controller-minimal-20261015.md` (it will use main's strong seat validator, unchanged). This document covers the full bundle (seat, life, bed, controller, plus the grip analyzer).

## Bounded validation

```
python3 tools/check_native_adapters_compile_closure.py --staging-ref origin/main --json closure.json   # about 6 s
```

| run | staging inputs | seat validator | result |
|---|---|---|---|
| A | origin/main 57d41bb | branch | PASS (exit 0); JSON sha256 2ff05be33dceeabaeb89fe2971ec01d2bbd972aa313da76f3cf229b3a672448a |
| B | branch HEAD | branch | PASS (exit 0) |
| C | origin/main 57d41bb | **main's strong rule, unchanged** | PASS (exit 0) |

- **Static checks:** 30 anchors are all unique. Includes resolve, braces balance, nothing is defined twice (including unity-build statics), every method is declared and defined once, every `Sub01*` name is defined, and no inserted line redeclares a host local.
- **Compiled** with g++ 13 and clang++ 18, `-std=c++20 -fsyntax-only -Wall -Werror -Wshadow` against a stub UE shim (`TCHAR=char16_t`, format-checked UE_LOG/Printf):
  - the engine-free headers (`Sub01SeatTransition.h`, `Sub01LifeClips.h`, …);
  - the whole installed character class;
  - all 21 adapter-added functions;
  - the 5 lines inserted into root functions, as probes;
  - `Sub01HomeHands.h`/`FSub01HandsProxy` with `WITH_EDITOR` set to 0 and to 1.
- **Not compiled:** root's own function bodies (only the inserted lines are), real engine signatures (checked only against stubs), UHT and linking. `FQuat` in the grip analyzer's UFUNCTION is noted only, because UHT was not run.
- **Real errors this check found and fixed** (`fe7bf0a`): a stray `}` that closed `LoadSeatTransition` early, and a local `TypingClipPath` shadowing the field. Both came from branch commit abb00cd, which is not in main.

## Contact-criterion caveat (explicit, not hidden)

The branch `tools/validate_unreal_seat_contact.py` replaces main's seat-patch rule (median ≤ +0.5 cm and ≥ 50 % band coverage) with a local-support rule (lowest point within the band and ≥ 12 band vertices) **for all patches**. That is a weaker whole-seat criterion. **Do not take the branch validator.**

- Run C shows the bundle still installs and compiles with main's validator. The seat adapter only calls `validate`, `regions_by_sample` and `cushion_triangles`, all of which exist on main.
- The controller adapter references `MIN_SUPPORT_VERTICES`, which is not on main. The minimal packet moves that sole-support constant into a controller-owned module with a physical justification.
- The committed seated fits (SeatedIdle/SitDown/GetUp "pass", `7ac1a9b`) were judged with the branch rule. A recheck under main's strong rule is running and will be published as `docs/proposed/seat-pose-fit/main-strong-rule-recheck.json`. Until then, treat those passes as **unverified under main's criterion**.

## Files

The import closure of `check_native_adapters_compile_closure.py`, `install_native_adapters_bundle.py` and `unreal_controller_grip_contact_native.py`, compared with `origin/main`.

**Absent on main (new files)**
- `check_native_adapters_compile_closure.py`, `native_adapters_ue_shim.py`, `install_native_adapters_bundle.py`
- `unreal_controller_play_runtime.py`, `unreal_controller_grip_contact_native.py`, `unreal_life_clips_runtime.py`, `unreal_bed_root_motion.py`
- `unreal_import_seated_fit_fbx.py`, `fit_controller_grip.py`, `export_seat_fit_source.py`, `life_gltf.py`
- `native_life/Sub01LifeClips.h`

**Differ from main, and only the branch changed them since the merge base `1bbb25d`**
- `inventory_native_life_clips.py`
- `native_seating/Sub01SeatTransition.h`
- `validate_unreal_seat_contact.py`: **keep main's** (see above)

**Differ from main, and main also changed them since the merge base. Keep main's for these.**
- `unreal_first_person_motion.py`: main bb4beac/fb81cc5. Run A stages from main's version and passes.
- `unreal_pc_runtime.py`: main 9e720c6. Run A passes with main's version.
- `unreal_import_gaming_grip.py`: main 62348da, root's reviewed contract-based version.
- `unreal_seat_transition_runtime.py`: main 70930c8 is only the walk-rate anchor fix. The branch has the same fix (prefix-resolved `SEAT_RATE_ANCHOR`) plus all seat work, so the **branch version supersedes it**.

**Same as main:** every other staged runtime (`stage_unreal_home_runtime.py`, `unreal_home_hands_runtime.py` after root's 1012fe3, `unreal_skin_contact_native.py`, and the rest).

## Root's next real compile

1. Take the minimal seat + controller packet when it lands, with main's validator kept.
2. Stage from main, run the installer, then run `check_native_adapters_compile_closure.py --staging-ref origin/main` (exit 0 is required).
3. Build in the sibling build project. Any engine-signature mismatch shows up only there.
4. Readiness stays false until the native evidence and live receipts exist (`NativeSeatVerified`, `ControllerPlayReady`, the sofa, grip and Game proofs).
