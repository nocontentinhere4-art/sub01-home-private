# Proposed home.js integration (not applied)

`home-js-integration.patch` is one reviewable patch for Codex that wires the
already-merged helper modules into `web/house/home.js`. It is **not applied**:
`home.js` is Codex-owned and may carry local body-hook work. Apply it on top
of that work with `git apply docs/proposed/home-js-integration.patch` (or
`git apply -3` if `home.js` has local changes nearby).

The patch is generated, never hand-edited. Regenerate and verify it with:

```
python tools/build_home_js_integration_patch.py           # rewrite the patch from tools/home_js_integration_edits.py
python tools/build_home_js_integration_patch.py --check   # is the committed patch current?
python tools/build_home_js_integration_patch.py --verify  # temp-copy verification, see below
```

The generator copies `home.js` to a temporary directory, applies each hunk with
an anchor that must occur exactly once, and writes `git diff --no-index` with
repo-relative paths. If an anchor stops matching, it fails and names the hunk.
`tests/test_proposed_home_patch.py` checks that the patch still applies, the
patched file passes `node --check`, and the committed patch matches the
generator. It skips with a reason if `home.js` has moved on.

## Design rule

Several node checks run isolated `home.js` blocks (`canWalk`, `lighting()`,
`acceptHome`) inside their own fixture scopes. These blocks therefore get **no
new free identifiers**:
- the door rules are wrapped under the collider names `canWalk` already calls;
- `lighting()` calls a hoisted `applyRoomLights()` hook, guarded by `typeof`;
- each new home state reaches the lights and the panel through the frame loop,
  not through `acceptHome`.

## Hunks, in order

Original line numbers refer to the unpatched `home.js` at `cc51313`.

| Hunk | Original lines | What | Source |
|---|---|---|---|
| H1 | 14 | Stop importing `balconyAllows`; H2b provides a wrapped one | `1dbcf2c` |
| H2 | 44–45 | Stop importing `frontDoorAllows`/`bathroomAllows`. Add imports: `house_interactions`, `house_controls_panel`, `furnishing_detail`, `bath_fixture_materials`, `replaced_primitives` | `0eb0514`, `1dbcf2c`, `55e620f`, `a14e876`, furnishing/bath modules |
| H2b | 52 (after the last import) | `visitorDoor()` plus wrappers `balconyAllows`/`frontDoorAllows`/`bathroomAllows`. A closed or locked door blocks entry from the house, never traps the visitor, and falls back to the exact old collider for older servers. `canWalk` stays byte-identical | `1dbcf2c`/`a81430f` (checkpoint #5) |
| H3 | 578 | `applyHavenSeamDetail`: sofa seams use the linen weave normal/roughness. The rug stays off | furnishing_detail (#6) |
| H4 | 890–894 | `applyQueenBedOak`: queen bed wood uses the shared oak maps at 1.83 m/tile, keeping the same mean roughness and colour | furnishing_detail (#6) |
| H5 | after 954 | Bath swap block (#15), details below | `5d985c5`, `579b15a`, `a14e876`, bath_fixture_materials |
| H6 | 988–991 | Delete the balcony placeholder chair: two cream boxes and four leg beams that sit inside the real `modern_arm_chair_01`. `obstacle(-1.2, 4.55, …)` on line 992 stays, because it is the real chair's collider | asset audit (#11) |
| H7 | before 1186 | `houseLightState`, `lastLightRooms`, and `applyRoomLights()`: per-room levels from `fixtureLevel`/`roomLit` (`lamp` stays the master switch; older servers use `lamp` only). Includes the bath light and any `switchedRoom` material | `0eb0514` (#2, #15) |
| H8 | 1223 | `lighting()` re-applies the room levels after its master pass | `0eb0514` (#2) |
| H9 | after 1242 | `toggleDoor(name)` plus E-interactions on the front door group, the bathroom leaf and the balcony leaf. They toggle the operator mode `open` ↔ `auto` through the existing authenticated `mutate('settings')` | `1dbcf2c` (#5) |
| H10 | after 1393 | Mount the operator controls panel as a collapsed `<details>` labelled "House" in the footer. Opening it re-checks the operator key | `55e620f` (#12) |
| H11 | 1563–1564 | Frame loop. On each new home state: update the panel and re-apply room lights when the rooms change. Door targets come from `doorTargets` (the visitor opens a door only from the dead-end side or the doorway); older servers use proximity | `1dbcf2c`, `0eb0514`, `55e620f` |
| H12 | 1567 | Front door target = `doorWant.front` | `1dbcf2c` |
| H13 | 1582 | Bathroom door target = `doorWant.bathroom`. The `doorOpen` name is kept, so the literal checked by tests is unchanged | `1dbcf2c` |
| H14 | 2729 | Add `bathFixturesReady`, `bathLightReady` and `bathDoorReady` to the asset barrier, so they are hidden before startup cleanup and baking | #15 |

### H5: the bath swap block (#15)

- `BATH_FALLBACK_CALLS` (in `replaced_primitives.mjs`) lists the procedural vanity and toilet.
  - This list is checked against `tools/build_home_bath_fixtures.py` `replaces_home_js` and against the `home.js` literals.
  - At load time, those meshes are found synchronously by position and size.
  - They are marked `replaceable` so `batchArchitecture` does not merge them.
- They are hidden only after the matching GLB **and** sidecar have loaded, and only if `sidecar.replaces_home_js` equals the list.
- The ceiling light is a `PointLight` taken from the sidecar `light` spec, plus the opal diffuser as a switched material for the bathroom room.
- The oak door GLB is parented to the existing `bathDoor` slab. The slab material is made invisible; the slab keeps sliding and colliding.
- Any missing asset or mismatch leaves today's primitives. The GLBs are built on Runpod and are not in Git.

## Verification (done in a temp copy, never the working tree)

`--verify`:
1. Runs `git apply --check` against the repository.
2. Copies the repository files into a temp directory (assets symlinked; a `node_modules/three` shim from `web/house/vendor`).
3. Runs every `tests/js` check that reads `home.js` (plus the helper-module checks) on the unpatched copy.
4. Applies the patch and runs `node --check web/house/home.js`.
5. Runs the same checks again.
6. Runs the Python tests that read `home.js` before and after.

Result at `cc51313`:
- The patch applies.
- `node --check` passes.
- **22 of 26 node checks pass, both before and after; no regressions.**
- The 4 checks that fail identically before and after are pre-existing source-extraction fixtures, unrelated to this patch:
  - `baked_receiver_lighting_check`: `gltfLoader` not defined;
  - `home_input_cleanup_check`: `createFirstPersonBody` not defined;
  - `home_screen_light_check`: `firstPersonBody` not defined;
  - `loft_art_clearance_check`: missing `frame(-2.2, 4.65, -3.88…)` literal.

## Required follow-ups when this is applied

- `tests/test_home_asset_audit.py::test_balcony_boxes_measured_against_actual_chair` measures the chair boxes that H6 deletes, so it fails after H6 by design. Retire that test, or change it to assert that the placeholder is gone, in the same commit.
- Baked contact lighting: H5 (vanity/toilet primitives taken out of batches) and H6 (chair boxes removed) change the merged `house-static-*` batch geometry for the darkwood, white, cream, brass and wood materials.
  - The existing exact-vertex bake matcher will reject the stale bakes for those batches (`shape-not-found`), and they render unbaked until the next Runpod bake.
  - Nothing else changes.
- The bath GLBs/sidecars (`web/house/assets/bath-{fixtures,light,door}-original/`) must be deployed for H5 to have any visible effect.
- Nothing here has been checked in a browser: door toggles, panel layout and lighting levels are unverified visually.

## Left out

Nothing was left out. Every requested hunk applies cleanly.
