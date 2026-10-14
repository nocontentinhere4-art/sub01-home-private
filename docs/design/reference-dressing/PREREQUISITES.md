# Reference dressing — prerequisites for root (private, source-only)

Status, 2026-10-14. Nothing in this file has been executed in Blender or Unreal, and no image was rendered. There is no GPU-verified result and no claimed visual match. The SimbasJungles reference and the process article were **not viewed**: the required `playwright-isolated` browser was not available to this agent.

## 1. What was and was not inspected

| Item | Result |
|---|---|
| `house.blend` (assembled home) | **Not inspected.** It is not in this checkout or under `out/`. `docs/HOME_COORDINATION.md` places it on the Runpod server at `/workspace/sub01-home-private/assembled/house.blend`, and `tools/assemble_home_blender.py` writes it to `out/home114-assembled/house.blend`. Blender is not installed here. Nothing was downloaded and no paid compute was used. |
| `web/house/assets/lighting/gi-architecture.glb` (103 meshes, bakeId extras) | Parsed with pure Python as a geometry **proxy**. It shares the source lineage of the static house, but its furniture is partly older than the assembled house (see section 3). |
| `web/house/assets/lighting/architecture.glb` (67 meshes) | Bounds only. |
| `cc0-queen-bed/queen-bed.glb`, `haven-sofa/sofa.glb`, `cc0-porta-espresso.json` | Measured: duvet profile, sofa seat, back and arm heights, espresso footprint. |
| Collections, materials and object list of `house.blend` | Unknown until step 4.1 runs. |

### Proxy geometry (runtime metres, x / y up / z; Blender = (x, -z, y))

- Ground slab x -4..4, z -4..4 (top 0.03). Entry slab x 0.75..3.25, z 4..5.8. The wall envelope `house-static-67` spans x -4.09..4.09, y 0..6.15, z -4.09..5.25.
- Loft floor y 3.03 over x -4..-0.2. Loft landing x -0.2..0.8, z -3.85..-1.7. Bathroom tile floor x -3.85..-0.8, z 0.5..2.7.
- Kitchen counter `house-static-10`: x -3.78..-0.62, z -3.88..-3.18, top **0.9225** (confirmed by ray). Utensil crock `house-static-15`. Sink `house-static-70` spans x -3.05..-2.35.
- Furniture by bakeId:
  - `house-sofa-Haven_{linen,seams,felt,legs}`: x -2.26..-1.34, z -1.04..1.24, back 0.92.
  - `house-office-desk-Oak_desk`: x 0.8..3.2, z -3.5..-2.7, top 0.84.
  - `house-office-shelves-*`.
  - `house-upper-cabinet-Cabinet_carcass`: y 1.7..2.4.
  - `house-lower-cabinet-carcass`.
  - `house-coffee-machine-*`.
  - `house-nightstand-side_table_01`.
  - `house-bedside-lamp-*`.
  - Legacy `house-coffee-table-Oak_coffee_table` (top 0.39), `house-bed-frame-Oak_frame`, and `house-bedding-{Duvet,Foot_throw,Pillow_1,Pillow_2}`.
  - TV panel `house-static-66`.
- Doors come from `home_interactions.DOORS`, not from mesh labels: front (2.0, 3.9) on the ground floor, balcony (-2.2, 3.85) on the upper floor, and the bathroom slide along x -0.85 from z 1.35 closed to 2.3 open.
- **Window openings could not be identified** from the proxy. It has no labelled window meshes, so this needs `house.blend`.

## 2. Spec versus repository assets

- **Materials:** every material in `spec.json` uses textures that exist in the repo: `rough_linen`, `quatrefoil_jacquard_fabric` and `home_oak_veneer` (`diff.jpg` and `normal.jpg`). Nothing is missing and nothing needs downloading.
- **Geometry:** all procedural (pillows with piping, draped and folded throws, books, a lathe vase with curve stems, canisters with oak lids). No external asset file is needed.
- **Duplicates the home already has are not added:**
  - all three rugs;
  - curtains;
  - the queen bed's own duvet and pillows;
  - office shelf books;
  - six potted plants;
  - nightstand decor (the lamp fills the nightstand top).

## 3. Clearance and conflict check (planner and proxy)

The authoritative check is `place_on_evaluated_home()`. It uses:
- triangle-level collision with every evaluated mesh;
- downward-ray support on the declared anchor;
- the 0.35 m capsule on every `home_world` walk-graph edge and node;
- door zones;
- the PC monitor, phone and TV prisms and sightlines;
- clearance zones derived from the evaluated bounds of the anchor objects.

It was run here on the proxy, not on `house.blend`.

Clearance zones derived from proxy bounds:

| Zone | Box (runtime m) |
|---|---|
| desk/chair approach | x 1.40..2.60, y 0..1.45, z -2.70..-1.40 |
| keyboard/mouse strip | x 1.45..2.55, y 0.795..1.095, z -3.10..-2.70 |
| sofa seat in use | x -2.263..-1.337, y 0.40..1.617, z -0.20..0.40 |
| bed access side (toward node `bed`) | x -1.521..-0.921 (proxy bed; -1.55.. for the queen bed), y 3..5 |
| kitchen work zone (ray at `LOOKS.kitchen`) | x -2.7..-1.7, y 0.903..1.623, z -3.9..-3.1 |
| upper / lower cabinet door swing | upper y 1.7..2.4, z -3.53..-2.755; lower y 0..0.868, z -3.24..-2.478 |
| bathroom slide | x -0.962..-0.738, y 3.05..5.05, z 0.825..2.825 |

Every conflict found:

1. `sofa_arm_throw_folded` at x -1.95 came within 0.325 m of the `sofa_front_approach-sofa` edge, under the 0.35 m capsule. **Fixed:** centre x is now -1.93 and the length 0.50 m (0.37 m clear).
2. At tilt -14°, `sofa_pillow_linen_left` and `sofa_pillow_linen_right` cut the Haven back cushion: 19 and 18 triangles even after the 2 cm fabric allowance. **Fixed:** tilt is now -10°, and the pillows clear the real sofa triangles.
3. `sofa_arm_throw_folded` at 0.55 m long reached the backrest and seam rise (Haven_linen 20 triangles, Haven_seams 68). **Fixed:** 0.50 m long and moved forward.
4. `bed_foot_blanket_folded` had three problems:
   - The 14 cm side drop entered the duvet's side drape, which reaches |x| 0.84 m (measured in `queen-bed.glb`).
   - Any wider drape would enter the `bed` node capsule, because node x -1.2 means nothing may pass x -1.55.
   - Its spec height of 3.66 was 2 cm inside the duvet, whose top is 3.681.
   **Fixed:** it is now a flat folded band, 1.36 m wide, on the duvet top at 3.68.
5. The proxy still contains the legacy `house-bedding-*`, including a `Foot_throw`. On such a home the blanket is **refused** (`refuse_if_present: ["house-bedding-"]`). `assemble_home_blender.py` deletes `house-bedding-*` and aborts if they are missing, so they should be absent from `house.blend`. This is **unverified** until step 4.1.
6. The proxy coffee table is the legacy oak one (top 0.39). The assembled home uses `house-cc0-coffee-table` (top about 0.455). The default anchor is the cc0 table: if `house.blend` lacks it, the lounge table items are refused (`clearance_unverified`), never guessed.
7. With proxy anchors substituted, all 10 non-bed items get support from real surfaces:
   - sofa items: `house-sofa-Haven_linen`;
   - counter items: `house-static-10` (offset 0.000);
   - coffee-table items: the legacy oak table.
   No collisions, capsule, door, screen or clearance violations remain. The queen-bed duvet surface for the lumbar cushion and the cc0 table top still need the real file.

## 4. Exact steps on the server (additive only)

Use the existing authorized pod only. Blender work runs headless and never renders.

### 4.1 Read-only identification (changes nothing)

```
blender --background /workspace/sub01-home-private/assembled/house.blend \
  --python tools/reference_home_dressing.py -- --list-identifiers --output-dir out/reference-dressing
```

Check `out/reference-dressing/reference-dressing-identifiers.json`:
- `home_version` is 114.
- Every anchor list is non-empty: `sofa`, `coffee_table`, `bed`, `desk`, `upper_cabinet`, `lower_cabinet`.
- There are no `house-bedding-*` identifiers.

If an anchor's real identifiers differ, write `anchors.json`, for example `{"coffee_table": ["<exact bakeId prefix>"]}`, and pass `--anchors anchors.json`. Never point an anchor at a different piece of furniture.

### 4.2 Placement and additive GLB

```
blender --background /workspace/sub01-home-private/assembled/house.blend \
  --python tools/reference_home_dressing.py -- \
  --assets-root web/house/assets --output-dir out/reference-dressing --export-additive-glb
```

- **Before any change**, every existing object is fingerprinted: name, type, parent, world matrix, exact evaluated mesh bytes (modifiers applied) and material node signature.
- After building, and again after export, each must match exactly, or the run raises before writing anything.
- The input `.blend` is never saved. `--save-blend-copy` writes a separate `house-dressed.blend` copy if one is wanted.
- **New objects:** one root empty per item, named `SUB01_RefDress_<room>_<id>`, for example `SUB01_RefDress_lounge_sofa_pillow_linen_left`. Its children are named `<root>_cover`, `_piping`, `_fabric0/1`, `_bookN_cover/_pages`, `_vase`, `_stemN`, `_body` and `_lid`.
  - Collection: `SUB01_ReferenceDressing`.
  - Custom properties: `sub01ReferenceDressing=True`, `dressingSpecId`, `bakeId=house-refdress-<…>`.
  - Materials are `SUB01_RefDress_<material>`, and images are loaded as new datablocks; existing materials and images are never reused or edited.
- **Units and axes:** metres, scale 1, Blender Z up. The glTF export is Y up (`export_yup=True`), which is the same frame as `full-home.glb` and `house.glb`. Root empties are unparented and sit at absolute house coordinates (runtime = Blender (x, z, -y)).
- **Export flags:**
  - `export_format='GLB'`, `use_selection=True` (only `additive_export_objects()`: tagged objects in the dedicated collection);
  - `export_yup=True`, `export_extras=True`;
  - `export_apply=True` (subdivision, displace, solidify and bevel are baked);
  - `export_lights=False`, `export_cameras=False`.
  The selection and active object are restored afterwards.
- **Outputs:** `reference-dressing.glb`, plus `reference-dressing.json` with the built items, resolved positions, support evidence, rejected items with reasons, and the existing-home fingerprint hash.
- **Verify after the run:**
  - `rejected` holds only the expected duplicates.
  - The GLB node list contains the curve parts (`_piping`, `_stemN`). The glTF exporter should convert curves to meshes, but this is not verified here.
  - Base colour tint survives as factor × texture (Multiply mix node). Also unverified.

### 4.3 Unreal import (additive; the home is not reimported)

Do **not** re-run `tools/unreal_import_home.py`, and do not reimport `full-home.glb` or `house.glb`. Reimporting would change the material and contact source hashes that the seat and keyboard audits depend on.

1. Copy `reference-dressing.glb` to `<UE project>/SourceAssets/reference-dressing.glb` and record its sha256 next to `home-inputs.json`. Do not add it to that manifest's `assets[0]`.
2. In the editor, run `level.load_level('/Game/Sub01Home/ActualHome')`, then import with Interchange: `InterchangeManager.import_scene('/Game/Sub01Home/ReferenceDressing', source, params)`, with `is_automated=True`.
   - Assets go **only** under `/Game/Sub01Home/ReferenceDressing`.
   - Never import into `/Game/Sub01Home/ImportedScene`, `/Game/Sub01Home/AuthoringLibrary` or `/Game/Sub01Home/Environment`.
3. Every spawned actor whose label starts with `SUB01_RefDress_` must:
   - keep the glTF node name as its label;
   - move to the World Outliner folder `SUB01_ReferenceDressing`;
   - get the actor tag `SUB01ReferenceDressing`;
   - use Static mobility;
   - have its static-mesh components set to `NoCollision`, so decor never alters pawn movement or the seat and keyboard contact audits.
4. **Placement check against stable existing actors, which are not touched:**
   - Rebuild the import transform the way `tools/unreal_setup_home.py` does: `infer_import_transform` on existing actor pivots, for example the actors labelled from `house-sofa-Haven_linen` and `house-office-desk-Oak_desk`, plus the documented pivot monitor (2, 1.16, -3.276) → UE (200, -327.6, 116) cm.
   - Then require that each `SUB01_RefDress_*` root is within 0.5 cm of `convert_position(position_runtime_m from reference-dressing.json, transform)`.
   - Also require that its offset from its support actor (sofa, desk, bed, coffee table) matches the source offset × 100 cm.
   - If any check fails, delete only the `SUB01_RefDress_*` actors and the `/Game/Sub01Home/ReferenceDressing` folder, and stop.
5. `tools/unreal_setup_home.py` sets **every** static-mesh component to BlockAll unless the actor is tagged `SUB01VisualBackground`. Run the dressing import **after** setup. If setup is ever re-run, re-apply step 3 afterwards, or have that file's owner add a skip for the `SUB01ReferenceDressing` tag. This file does not change it.
6. Save only the level and the new folder: `save_directory('/Game/Sub01Home/ReferenceDressing')` and `save_current_level()`.

### Must not be touched

In Blender:
- every pre-existing object, mesh, material and image in `house.blend` (the fingerprint enforces this; no bevels or deletions);
- the input `.blend` file itself.

In Unreal:
- the ImportedScene actors and assets (233 placed mesh components);
- the restored lights, HDR, sky and `SUB01VisualBackground` actors;
- `SUB01_GroundFloor_FirstPerson_Start`;
- `SUB01_Real_FirstPerson_Render_Camera`;
- the native pawn and GameMode;
- the monitor surface binding, keyboard keycap meshes, and the seating/contact audit sources and their reports;
- `home-inputs.json` `assets[0]`;
- the AuthoringLibrary.

Nothing here authorizes a deploy, a new pod or a new key.
