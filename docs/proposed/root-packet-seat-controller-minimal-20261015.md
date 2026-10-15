# Root packet: minimal seat + controller install on origin/main (2026-10-15)

Private, source only. Nothing deployed; no target, provider or pod touched. Proven in clean worktrees of origin/main
**57d41bb** (full suite), **380baa8** (root's named main; became fetchable at ~04:30 UTC) and **d9827e5** (main at
04:35 UTC; 380baa8 is its ancestor). On all three the main inputs are byte-identical (seat runtime 534903e1...,
validator dd95f1b1..., contract aa9a3f9e...), the brace patch applies, closure `--only seat,controller` PASSES with
g++ and clang++, and the 17 packet tests pass. Main's motion, PC runtime, grip importer and validator are used as is.

## Why

Main's `tools/stage_unreal_home_runtime.py` stages the renderer but never installs
`tools/unreal_seat_transition_runtime.py`, so `NativeSeatVerified` (and PC focus) can never become true. This packet
adds one small installer that stages exactly like main and applies **main's own seat adapter**, then the controller
adapter, with every readiness flag false by default.

## Files

| path | status on main | sha256 |
|---|---|---|
| tools/install_seat_controller_adapters.py | NEW | 1bc4f783ddb1d30adcedbf01d3c2b8a7694c656e6348538240d30ddfbeff1b7b |
| tools/controller_play_minimal.py | NEW | 688644f13dd63abaffa124f8a7cbf77ee9e41306b9ed1ac842f1bc26894e7422 |
| tools/unreal_controller_play_runtime.py | NEW (branch file verbatim, incl. eye camera aa18430) | 1190282a31e53141b68c4f5efdf562139b91c1d9a13dfc9a4a174b20febb33b0 |
| tools/check_native_adapters_compile_closure.py | NEW (022c399 + `--only seat,controller`, lazy bundle/grip imports, same-line extension hunks) | d66b9a82a33cf13803e7533d7dddc5cf6b7b72afb31f2e02aa781cf34dccc413 |
| tools/native_adapters_ue_shim.py | NEW (022c399, unchanged) | ec715687b2b0b515781029c06eee70484dcced9a7210bd24174e5f427a918f0e |
| tests/test_seat_controller_minimal.py | NEW | d848b7fda39e9d1fe6f1b56ac9f97674d17bff6e4da8d98db5fd10e473f814e9 |
| tools/unreal_seat_transition_runtime.py | **MODIFIED, 1 line deleted** (root-owned; patch below, root applies) | main 534903e15553dc2308b8ba4fb78165c9fb3973e87d0ff668ba3bdb99b1e91661 -> patched 76661fc8034fff5289f37d74264b89ecffe092a88c1b0c65443c6efe8c8d35b4 |

Used from main unchanged: `tools/validate_unreal_seat_contact.py` (dd95f1b1...a18f, the strong median + 50% coverage
rule), `tools/controller_clip_contract.py` (aa9a3f9e...628b, the four pins), `tools/native_seating/Sub01SeatTransition.h`
(764e53fd...3784), `tools/stage_unreal_home_runtime.py` (23c525ce...7d61) and everything it stages (motion, PC runtime,
hands). Not used: the branch seat validator, `fit_controller_grip.py`, `export_seat_fit_source.py`, `life_gltf.py`,
`install_native_adapters_bundle.py`, the grip analyzer, the branch seat runtime.

### The one unavoidable main change

`docs/proposed/root-packet-seat-controller-minimal-20261015.seat-brace.patch` deletes one line. Main's generated
`LoadSeatTransition` closes one brace early after the cushion block, so the contact-evidence block lands at file scope
and the installed module cannot compile (closure check on unpatched main: brace net -1, g++/clang "expected
unqualified-id", 5 failures). Same defect the branch fixed in fe7bf0a. The installer refuses (exit 2, nothing
written) until the patch is applied.

```diff
     UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_CUSHION area=%.2fcm2 bounds=%s"),Area,*Cushion.ToString());
    }
   }
-  }
  }
  // Contact evidence: only an accepted, quantitative report (build_evidence()).
```

## Gates (nothing loosened)

- Seat: main's adapter verbatim except the brace; `NativeSeatVerified=false` in the header, set only from
  `SeatOut.ContactVerified` (live pose-matched receipt over native evidence).
- Controller: `ControllerPlayReady()` = evidence && native runtime proof && clip && controller mesh && hand/head bones;
  all start false. The clip binds only if `ValidatedHandsPostures` contains `Gaming`; the installer writes no Config
  (test compares Config bytes before/after) and `config` writes `+ValidatedHandsPostures=Gaming` only with accepted
  evidence for THIS sofa report and the exact derived-clip import row.
- Sofa contact (controller-owned, `tools/controller_play_minimal.py`): per region per sample over the whole clip at
  >= 30 Hz, main's rule unchanged (over-surface >= 12, min gap >= band low, **median <= band high, coverage >= 50%**,
  soles included) AND a support patch of >= 12 band vertices. The 12 is main's `MIN_PATCH_VERTICES` reused, not a new
  constant: a contact patch must be at least the smallest patch main accepts over a surface, so a few grazing vertices
  of a large patch never count as support. It is an extra per-patch requirement, never whole-seat validation, and the
  seat validator is not edited. A randomized test checks the gate never accepts what main's `validate()` refuses.
- Grip: only the derived clip report (`validate_derived`); raw fits/searches refused; no `fit_controller_grip` import.
- The runtime file's own `evidence` CLI needs the branch validator's `MIN_SUPPORT_VERTICES`; on main it fails closed
  (AttributeError, nothing written). Use `tools/controller_play_minimal.py evidence` instead.

## Commands (clean origin/main worktree)

```
git worktree add --detach /tmp/wt origin/main && cd /tmp/wt
# copy ONLY the 6 NEW files above and the .seat-brace.patch from the branch, then:
git apply root-packet-seat-controller-minimal-20261015.seat-brace.patch   # root's one-line fix
python3 tools/install_seat_controller_adapters.py --stage <project>        # or <project>/Source/Sub01HomeLab if staged
python3 tools/check_native_adapters_compile_closure.py --only seat,controller
python3 tools/controller_play_minimal.py status <project>
python3 -m pytest -q tests/test_seat_controller_minimal.py
```

## Results on 57d41bb

- Unpatched seat runtime: installer `REFUSED: seat adapter closes LoadSeatTransition early ...`, exit 2.
- Patched: installer exit 0, `installed: [seat, controller]`, `validated_gaming_posture_in_config: []`; second run
  `REFUSED: seat adapter is already installed`, exit 2.
- Closure `--only seat,controller`: 14 anchors all unique; added lines Sub01HomeLab.cpp 362, .h 25, Sub01HomeHands.cpp 7,
  .h 10, Sub01SeatTransition.h 286; g++ and clang++ (`-std=c++20 -fsyntax-only -Wall -Werror -Wshadow`, stub UE shim)
  OK for engine_free_headers, character (WITH_EDITOR=1), hands (WITH_EDITOR=0/1); **closure: PASS**. Not compiled:
  root function bodies hosting inserted lines (inserted lines compiled as probes), real engine signatures, UHT, linking.
- `status`: evidence false, runtime_proof false, ready false. `config` with no evidence: written false, exit 3.
- `tests/test_seat_controller_minimal.py`: 17 passed (main worktree).
- Main's whole suite (`python3 -m pytest -q tests --continue-on-collection-errors`), pristine 57d41bb vs 57d41bb +
  packet + brace patch: baseline 22 failed / 2327 passed / 49 skipped / 57 errors; packet 22 failed / **2344** passed /
  49 skipped / 57 errors. The +17 are the packet tests; the FAILED/ERROR sets are identical (pre-existing, e.g. missing
  `aiohttp` in this sandbox), so nothing else changes.
- Claude branch: test_seat_controller_minimal (skips without main's contract), compile-closure, fit_controller_grip,
  controller eye camera and support-contact tests: 70 passed, 1 skipped.
- The patch file's own sha256: 197b7787388687b8c1cea11e2aa9d898a34d4d1eb8ce3aa345ae611523986c11.
