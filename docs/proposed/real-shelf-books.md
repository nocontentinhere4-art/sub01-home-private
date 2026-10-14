# Real shelf books: replace the office shelf's cube books (root runbook)

Private, server-only, additive. Nothing here has run in Blender or Unreal yet. No visual result is claimed.

## What gets replaced
- The cube books come from `web/house/home.js:361-368` (`books()`). They are RoundedBox meshes with width .035-.055, height .16-.28, depth exactly .14, centres at `x + i*.054`, and one `mat()` each, so `batchArchitecture` (home.js:2766-2806) cannot merge them: it needs at least 3 meshes that share a material.
- `home.js:856-860` places them only on boards with `y > 1.6`. In IEEE doubles that gives 2.05 and 2.5 (the third value is 1.5999999999999999), so there are **2 rows of 15 = 30 books**, with bottoms at runtime y 2.07 and 2.52, z -3.71.
- `home.js:2819-2833` names each one `house-static-<N>` (both the node name and the bakeId). N depends on scene order, so the builder matches that name pattern **and** the exact geometric signature, and refuses unless it finds exactly 30 objects, one per (row, index) slot.
- The loft books at `home.js:938` are not touched.
- The shelf is `tools/build_home_office_shelves.py`, loaded by home.js:861-876 as `house-office-shelves-*`. Its board tops are at .2675 + i*.45; the books stand on the boards at 2.0675 and 2.5175. The builder measures these heights from the evaluated triangles.

## Material-batched books (owner rule: never hide a shared batch)
**Selection.** Cube books are selected per **exact connected component**, never per node:
- every evaluated node in the shelf region is split into components, with vertices welded by position because the three.js boxes duplicate them per face;
- a component counts as a book only if its bounds match the home.js book box and it sits on a shelf board.

**Per-node outcome:**

| Node contents | What the builder writes |
|---|---|
| Exactly one book component | Listed under `originals` in `original-hide-manifest.json`, and hidden in UE. |
| Several books, or books with other geometry (e.g. a lamp stem or rail metal sharing the material) | Never hidden. Listed under `excisions`. |

**Each `excisions` entry contains:**
- `node`, `ident`, `canonical`;
- `triangle_order`: the Blender evaluated `loop_triangles` of that glTF node;
- `excise.components[]` (component id, row/index, `triangle_ids`, bounds);
- `excise.triangle_ids` and `excise.triangles_runtime_m`: world positions, so the set can be matched in any tool;
- `remainder`: `triangle_count`, `components`, bounds, and `positions_sha256` of the kept triangles.

**Unreal step with excisions.** The UE script refuses while `excisions` is non-empty. After root applies the excision, run it with `--excision-applied`; it then leaves those nodes untouched and hides only the separate ones.

**Refusals.** Any count or slot mismatch is refused, including a book welded to other geometry, which then fails the box test. The refusal lists matches and near misses.

**Excision format.** Root's rail/stairs excision builder (nodes 162/163) is not in any pushed branch (`origin/main` and both `claude/*` branches searched). This format is self-describing: map it onto the rail builder's format if that differs.

### Guard against root's rail/stem union
Root's union is recorded in `evidence/native/exact-lamp-stem-rail-union.json`: node 163 / primitive 0, with stem triangles 1800..1839 removed and rail remainder 1640..1799 of 1840. The rail batches are nodes 162/163.

- **What is reserved.** The builder always reserves glTF nodes 162 and 163, plus every node index or name it finds in that evidence file (or in the file given by `--reserved-evidence`).
- **Naming the reserved nodes.** It names them from `--source-glb <native full-home.glb>`.
- **When it refuses:**
  - if any hidden or excised book node is a reserved node;
  - if a batched book excision exists while reserved indices cannot be named.
- **What it records.** The check is written under `reserved_surgery_guard` in the report.
- **Triangle numbering.** Book `triangle_ids` follow Blender `loop_triangles` order. They are not glTF primitive indices; the world positions are included so the two can be matched.

## Base: which and why
Use `/workspace/sub01-home-private/out/native-reference-base/house.blend`, the native base from `tools/prepare_native_dressing_base.py`.
- It is the plain import of the same `full-home.glb` that Unreal shows, so node names and pivots match the UE actors.
- The same base already ran successfully for reference dressing (`docs/design/reference-dressing/PREREQUISITES.md`).
- The assembled home114 base would not match the UE map.

## Commands (server; root or the renderer only)
```
cd /workspace/sub01-home-private && git fetch origin && git checkout claude/friendly-wozniak-dsxmyz
B=/workspace/sub01-tools/blender-4.5.3-linux-x64/blender
BASE=/workspace/sub01-home-private/out/native-reference-base/house.blend
ASSET=$(ls out/furniture-refresh/set-dressing/**/book_encyclopedia_set_01*.{blend,gltf} 2>/dev/null | head -1)   # confirm the path by hand
SRC=$(python3 -c "import json;print(json.load(open('${BASE%.blend}.json'))['source_sha256'])")
# 1. read-only and fast (evaluates only objects near the shelf; no asset needed): candidates, boards, shelf, reserved-node guard
"$B" --background --factory-startup "$BASE" --python tools/build_real_shelf_books.py -- \
  --list-originals --allow-unassembled --source-sha256 9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b \
  --source-glb <UE project>/SourceAssets/full-home.glb --output-dir out/real-books
# 2. dry run: measure, lay out, check, report; no GLB
"$B" --background --factory-startup "$BASE" --python tools/build_real_shelf_books.py -- \
  --dry-run --allow-unassembled --source-sha256 "$SRC" --source-glb <UE project>/SourceAssets/full-home.glb --books-asset "$ASSET" --output-dir out/real-books
# 3. build plus additive GLB
"$B" --background --factory-startup "$BASE" --python tools/build_real_shelf_books.py -- \
  --allow-unassembled --source-sha256 "$SRC" --books-asset "$ASSET" --output-dir out/real-books
```

**Checks after step 1** (`out/real-books/real-shelf-books-identifiers.json`):
- exactly 30 `originals` (book components);
- `originals_batched_nodes`, previewed in `original-hide-manifest.preview.json`;
- `boards` includes z of about 2.0675 and 2.5175;
- `shelf_objects` is not empty.

If the step refuses, the JSON lists the matched names and near misses.

**Optional flags:**
- `--spine-axis` (default `-Y`): the direction the spines face in the asset file. Check it on the Poly Haven preview.
- `--front-axis` (default `-Y`): the room side of the shelf in Blender.
- `--seed`.
- `--uniform-scale`: only use it if the asset is not in metres. Book dimensions outside 0.12-0.45 m height are refused.

**Outputs in `out/real-books/`:**
- `real-shelf-books.json`, containing:
  - `provenance`: the asset, the Poly Haven URL, CC0 and the file sha256;
  - `asset_books`: the measured real dimensions;
  - `built[]`: for each book, the source mesh, dimensions, Blender matrix, runtime pivot, support and contact checks;
  - `rejected[]`;
  - `existing_objects_verified_unchanged`;
  - `additive_glb`: sha256 and texture roles.
- `real-shelf-books.glb`: only `SUB01_RealBook_*` nodes and materials.
- `original-hide-manifest.json`: the separate originals, the `excisions` for batched nodes, plus the shelf and reference pivots used for the UE check.

**Guarantees:**
- **Fingerprint.** Every pre-existing object is fingerprinted before and after the build and after the export. Any change aborts, and the base is never saved.
- **Layout.** A seeded layout on the two boards, over the cube books' span plus 10 cm:
  - upright rows;
  - leaning books, rotated about the bottom edge so the top corner rests on the upright neighbour. Each has 2 checked contacts.
  - small horizontal stacks, longest book at the bottom.
- **Spines** face the room.
- **Rejection.** A book is rejected if it:
  - collides with an evaluated triangle (shelf, cleats, wall);
  - overlaps another book (oriented-box test);
  - leaves the board;
  - exceeds the clearance;
  - fails the downward support rays.
- **Scale.** Rigid only; never non-uniform.
- **Materials.** The scanned textures are kept and copied under the `SUB01_RealBook_` prefix: albedo sRGB, normal and roughness Non-Color, and emission strength 0 (any emissive image refuses).

## Unreal import (editor, native game stopped)
```
UnrealEditor-Cmd <Sub01Home.uproject> -ExecutePythonScript="/workspace/sub01-home-private/tools/unreal_import_real_shelf_books.py --root /workspace/sub01-home-private/out/real-books" -unattended
```
**Import and placement:**
- Imports into `/Game/Sub01Home/RealBooks/V_<sha12>`.
- Infers the import transform from the 30 originals and the desk/sofa/coffee-table pivots, then refuses unless the shelf actor is within 0.5 cm of the Blender base.
- Each book actor must land within 0.5 cm of its exported pivot with uniform scale. Otherwise the import is rolled back.

**Actor setup:**
- Book actors are relabelled `SUB01_RealBook_NN`, tagged `SUB01RealShelfBooks`, put in folder `SUB01_RealShelfBooks`, set Static, with NoCollision.
- The 30 originals get `set_actor_hidden_in_game(True)` and component visibility off. They are not destroyed, and their collision is unchanged.

**Texture check:**
- Albedo must be sRGB with TC_Default.
- Normal must be non-sRGB with TC_Normalmap.
- Roughness/ORM must be non-sRGB.
- Owned textures are corrected, then re-checked; a failure refuses.

**Safety:**
- All pre-existing actors are fingerprinted (transform, mesh, materials, collision). Any difference rolls back the import.
- A re-run with the same GLB is a no-op. A different GLB is refused until `--restore`.
- The receipt is written to `<project>/real-shelf-books-import.json`.

## Visual verification (required before any claim)
- A native close-up of the office shelf from about 1.2 m in front, at eye height 1.65, looking at runtime (1.6, 2.3, -3.72), with the same capture path used for the other native shots.
- Confirm:
  - real book textures;
  - no cube books visible;
  - no floating or intersecting books;
  - the spines face the room;
  - the leaning books touch their neighbours.
- Compare against the SimbasJungles reference.

## Rollback
- Run the same UE command with `--restore`. It deletes only the `SUB01_RealBook_*`/tagged actors and `/Game/Sub01Home/RealBooks`, and unhides the originals to their recorded states.
- Blender never modifies the base. Delete `out/real-books/` if needed.
