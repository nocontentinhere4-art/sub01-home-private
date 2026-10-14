# Reference dressing: self-contained runbook for root

Updated 2026-10-14. Work stays private and on the existing authorized pod: no deploy, no new pod, no new key, no render. Nothing here has run in Blender or Unreal yet, and no GPU or visual result is claimed. The SimbasJungles reference and its process article were **not viewed**, because the required `playwright-isolated` browser was unavailable to the author.

## 1. Inputs

| Input | Value / source |
|---|---|
| Blender | `/workspace/sub01-tools/blender-4.5.3-linux-x64/blender` (official 4.5.3 LTS, SHA-verified by root) |
| Base | `/workspace/sub01-home-private/out/native-reference-base/house.blend`, written by `tools/prepare_native_dressing_base.py` (commit `5473bcb`, `origin/main`) |
| Base facts reported by root | SHA-256 `9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b`, 34,589,540 bytes, 233 mesh objects, 758,827 vertices |
| Base sidecar | `house.json` next to the base. Schema `sub01.native-dressing-base.v1`, with `source_sha256` (the native GLB hash), `mesh_objects` and `vertices`. |
| Base scene record | `scene['sub01NativeSourceSha256']` = the native source GLB SHA-256 |
| Module | `tools/reference_home_dressing.py` (Blender stdlib only; imports nothing from the server stack) |
| Item spec | `docs/design/reference-dressing/spec.json` |
| Walk graph | `home_world.py` `NODES` and `EDGES` (walking-eye points in metres; floor = eye − 1.65), plus `LOOKS['kitchen']` for the kitchen work zone. Parsed with `ast`, never imported. |
| Doors | `home_interactions.py` `DOORS` (front, balcony), plus `tools/build_home_bath_door.py` constants for the bathroom slide (closed z 1.35 → open z 2.3) |
| Device screens | PC monitor UE (200, −327.6, 116) cm, extent (34, 0, 20), i.e. runtime (2, 1.16, −3.276) (pivot from `tools/unreal_home_state_bridge.py`). Phone plane (2.7, 0.866, −2.92), 0.067 × 0.137, facing up. TV plane (−3.747, 1.65, −0.05), 1.66 × 0.95, facing +x. |
| Textures | `web/house/assets/{rough_linen,quatrefoil_jacquard_fabric,home_oak_veneer}/{diff,normal}.jpg`, tracked in git. `web/house/assets/manifest.json` and `home114-assembled/house.blend` are **not** used. |

The value `9556495…` is ambiguous: it is either the base file's hash or the source GLB's hash. The commands in section 3 resolve it. The run refuses on any mismatch, so a wrong guess cannot slip through.

### How the base names things (from `prepare_native_dressing_base.py`)

- It runs a plain `bpy.ops.import_scene.gltf` of the native GLB after factory settings.
- No renaming, re-parenting or re-collecting happens: objects keep the glTF node names, in the importer's default scene collection.
- glTF node extras become custom properties. The identity used is `obj.get('bakeId', obj.name)`, the same convention as `tools/assemble_home_blender.py`.
- The native GLB is the V4 browser export. `assemble_home_blender.py` `OLD_PREFIXES` shows it still carries the legacy `house-bed-frame-`, `house-bedding-`, `house-coffee-table-` and `house-coffee-machine-` objects.

Anchor prefixes (`DEFAULT_ANCHORS`). Each is cited in `ANCHOR_SOURCES`, and a test checks that the prefix appears in its source file:

| Anchor | Prefixes | Source |
|---|---|---|
| sofa | `house-sofa-` | `web/house/home.js` |
| coffee_table | `house-cc0-coffee-table-`, `house-coffee-table-` | home.js / assemble OLD_PREFIXES |
| bed | `house-cc0-queen-bed-`, `house-bed-frame-`, `house-bedding-` | home.js / assemble OLD_PREFIXES |
| desk | `house-office-desk-` | home.js |
| upper_cabinet | `house-upper-cabinet-` | home.js |
| lower_cabinet | `house-lower-cabinet-carcass` | `web/house/lower_kitchen_cabinet.mjs` |
| kitchen_surface | downward ray at `LOOKS['kitchen']` (−2.2, ·, −3.5) | home_world.py |

If `--list-identifiers` shows different real identifiers, write `anchors.json` (`{"anchor": ["exact prefix", ...]}`) and add `--anchors anchors.json`. Never map an anchor onto a different piece of furniture.

## 2. What the run guarantees (enforced in code, covered by tests)

1. **Baseline.** Without `--allow-unassembled`, only the assembled home (`homeVersion` 114) is accepted, so this native base is refused. With the flag, the base must have `sub01NativeSourceSha256` equal to `--source-sha256` (or to the sidecar's `source_sha256` when the flag is omitted). The sidecar's schema, `source_sha256`, `mesh_objects` and `vertices` must match the opened scene. `--base-sha256` / `--base-bytes`, when given, must match the opened `.blend` file. The whole house is never rebuilt or reimported.
2. **Preservation.** Before any change, every existing object is fingerprinted: name, type, parent, exact world matrix, exact evaluated mesh bytes (modifiers applied), and material node signatures. The check repeats after placement and after export. Any difference raises before anything is written. The input `.blend` is never saved over. The report records the source SHA and the 233 mesh objects.
3. **Support and bounds.**
   - Placement uses only depsgraph-evaluated triangles of this base. Each item gets triangle-level collision against every existing object (with a small soft-fabric allowance).
   - Resting items need a downward-ray hit on the declared anchor under every sample point. A missing support means the item is **unplaced** (`unsupported:`), and rigid items with partial support are also refused.
   - Wall or hanging items must declare `mount` and `attach`, and the attach ray must hit the declared surface. No current item is wall-mounted or hanging.
   - Clearance zones come from the evaluated anchor bounds:
     - desk/chair approach and keyboard/mouse strip, from the desk;
     - the sofa seat in use, from the sofa;
     - the bed access side toward node `bed`;
     - the kitchen work zone, from the ray at `LOOKS.kitchen`;
     - cabinet door swings, from the carcass bounds.
   - These are combined with the 0.35 m capsules on every walk-graph edge and node, the door zones, and the monitor, phone and TV prisms and sightlines.
   - If an anchor is missing, that room's items are refused and listed under `refused_rooms`.
4. **Export.** Only the `SUB01_ReferenceDressing` collection is exported: it is set as the active layer collection, and the export uses `use_active_collection=True`, `use_active_collection_with_nested=True` and `use_selection=True` with only tagged objects selected. The written GLB is then parsed. Any node outside the new collection, any material without the `SUB01_RefDress_` prefix, or a missing item root deletes the file and raises. The selection and active collection are restored afterwards.
5. **Textures.** Missing texture files are reported per material and per item (`path`, `item`, `material`). Nothing is silently substituted, and nothing is labelled as scanned (`sub01Scanned=False` on every new material).

## 3. Commands (run from the repo checkout on the pod)

```
cd /workspace/sub01-home-private
git fetch origin && git checkout claude/friendly-wozniak-dsxmyz   # or the integrated commit
B=/workspace/sub01-tools/blender-4.5.3-linux-x64/blender
BASE=/workspace/sub01-home-private/out/native-reference-base/house.blend
sha256sum "$BASE"; stat -c %s "$BASE"            # expect 9556495f…481b and 34589540 if that hash is the base's
SRC=$(python3 -c "import json;print(json.load(open('${BASE%.blend}.json'))['source_sha256'])")
```

- If `sha256sum` printed `9556495…`, add `--base-sha256 9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b --base-bytes 34589540` to both commands below.
- If instead `$SRC` equals `9556495…`, it is the source hash. Pass it as `--source-sha256` and omit the base flags.

**Step 1: read-only identification.** This changes nothing and saves nothing.

```
"$B" --background --factory-startup "$BASE" --python tools/reference_home_dressing.py -- \
  --list-identifiers --allow-unassembled --source-sha256 "$SRC" --output-dir out/reference-dressing
```

Check `out/reference-dressing/reference-dressing-identifiers.json`:
- `base.basis == "native-dressing-base"`, with no `refused` key;
- `mesh_objects == 233` and `vertices == 758827`;
- every list under `anchors` is non-empty;
- the identifiers are the bakeIds expected above.

**Step 2: placement plus the additive GLB.**

```
"$B" --background --factory-startup "$BASE" --python tools/reference_home_dressing.py -- \
  --allow-unassembled --source-sha256 "$SRC" \
  --assets-root web/house/assets --texture-fallback flat \
  --output-dir out/reference-dressing --export-additive-glb
```

**Outputs:**
- `out/reference-dressing/reference-dressing.json`, containing:
  - `base` and `source_sha256`;
  - `built[]`, with resolved positions, support evidence, `fallback_untextured` and `missing_textures`;
  - `rejected[]` with reasons, and `refused_rooms`;
  - `anchors_matched` and `textures`;
  - `existing_objects_verified_unchanged` and `existing_mesh_objects` (233);
  - the `additive_glb` path and sha256, with `verified_additive_only: true`.
- `out/reference-dressing/reference-dressing.glb`, containing only the `SUB01_RefDress_*` objects.
- Add `--save-blend-copy` only if a separate `house-dressed.blend` copy is wanted. The base is never overwritten.

**Expected results.** These were predicted from the repo's `gi-architecture.glb` proxy (same V4 lineage) using the same code path, so they are not a Blender result:
- 10 items placed:
  - three sofa pillows and the arm throw, on `house-sofa-Haven_linen`;
  - the book stack and vase, on `house-coffee-table-Oak_coffee_table` (top 0.39);
  - three canisters, on the counter (top 0.9225);
  - the lumbar cushion, on `house-bedding-Duvet`.
- `bed_foot_blanket_folded` **refused** as `duplicate:existing:house-bedding-Foot_throw`, because the native home already has a foot throw.
- The `skipped_existing` duplicates are listed: rugs, curtains, duvet, shelf books, plants and nightstand.

**Expected refusals:**
- Base refusals: a missing flag, a SHA, size or count mismatch, or a missing sidecar SHA. These raise before any change.
- `clearance_unverified:<anchor>` for a room whose anchor is missing.
- `unsupported:` when there is no real support surface.
- `collides:`, `walk_graph:`, `door:`, `screen_*:` and `clear:` clearance failures.
- A fingerprint change raises without writing.

## 4. Texture fallback choices

The `--texture-fallback` flag selects one of three behaviours:

| Choice | Flag | Behaviour |
|---|---|---|
| **A (default)** | `flat` | The item is built with the spec's authored base colour and roughness only. Its material is named `…_UNTEXTURED_FALLBACK` with `fallback_untextured=True`, and the report marks the item `fallback_untextured: true` and lists the missing paths. It is clearly not scanned or textured. |
| B | `skip` | Items using a material with missing files are not built (`texture_missing:<material>:<path>`). |
| C | `wait` | The run stops before any change and lists every missing file. |

The three texture folders are tracked in git, so A should not be triggered on a full checkout. If it is, the report says so per item.

## 5. Unreal additive import (the home is not reimported)

Do **not** re-run `tools/unreal_import_home.py` and do not reimport `full-home.glb`. That would change the material and contact hashes that the seat and keyboard audits depend on.

1. Copy `reference-dressing.glb` to `<UE project>/SourceAssets/reference-dressing.glb` and record its sha256 next to `home-inputs.json`. Do not add it to `assets[0]`.
2. In the editor, run `level.load_level('/Game/Sub01Home/ActualHome')`, then `InterchangeManager.import_scene('/Game/Sub01Home/ReferenceDressing', source, params)` with `is_automated=True`.
   - Assets go **only** under `/Game/Sub01Home/ReferenceDressing`.
   - Never import into `ImportedScene`, `AuthoringLibrary` or `Environment`.
3. Each new actor (label starts with `SUB01_RefDress_`) must:
   - keep its glTF node name as its label;
   - move to the Outliner folder `SUB01_ReferenceDressing`;
   - get the actor tag `SUB01ReferenceDressing`;
   - use Static mobility;
   - have its static-mesh components set to `NoCollision`, so decor never alters pawn movement or the seat and keyboard contact audits.
4. **Placement check against stable existing actors, which stay untouched:**
   - Rebuild the import transform the way `tools/unreal_setup_home.py` does: `infer_import_transform` over existing actor pivots, e.g. the actors labelled from `house-sofa-Haven_linen`, `house-office-desk-Oak_desk` and `house-coffee-table-Oak_coffee_table`, plus the documented monitor pivot (2, 1.16, −3.276) → (200, −327.6, 116) cm.
   - Each `SUB01_RefDress_*` root must be within 0.5 cm of `convert_position(built[].position_runtime_m, transform)`.
   - Its offset from its support actor must equal the runtime offset × 100 cm.
   - On failure, delete only the `SUB01_RefDress_*` actors and the `/Game/Sub01Home/ReferenceDressing` folder, and stop.
5. `tools/unreal_setup_home.py` sets every static-mesh component to BlockAll unless the actor is tagged `SUB01VisualBackground`. Import the dressing **after** setup. If setup is re-run, re-apply step 3, or have that file's owner skip the `SUB01ReferenceDressing` tag.
6. Save only the new folder and the level: `save_directory('/Game/Sub01Home/ReferenceDressing')` and `save_current_level()`.

### Must not be touched

In Blender:
- the 233 base mesh objects, their meshes, materials and images (the fingerprint enforces this);
- the base `.blend` and its sidecar.

In Unreal:
- the ImportedScene actors and assets (233 mesh components);
- lights, HDR, sky and `SUB01VisualBackground` actors;
- `SUB01_GroundFloor_FirstPerson_Start`;
- `SUB01_Real_FirstPerson_Render_Camera`;
- the native pawn and GameMode;
- the monitor surface binding and keyboard keycap meshes;
- the seating/contact audit sources and their reports;
- `home-inputs.json` `assets[0]`;
- the AuthoringLibrary.

## 6. Verified versus unverified

**Verified here:**
- 37 pure-Python tests pass. They use duck-typed fakes for `bpy` objects; Blender is not installed in this environment. They cover:
  - base SHA, count and size refusals;
  - refusal without `--allow-unassembled`;
  - a missing support makes an item unplaced;
  - a missing anchor refuses its room;
  - the fingerprint detects matrix, mesh and material changes;
  - only tagged objects in the collection are exported, and a leaking GLB is rejected;
  - the texture fallback is reported and never called scanned.
- The proxy run against `gi-architecture.glb`.

**Unverified:**
- the real base's identifiers and evaluated surfaces;
- glTF 4.5.3 exporter behaviour (curve parts, Multiply-tint export, collection flags);
- Unreal actor layout after Interchange import;
- window openings;
- any visual result.
