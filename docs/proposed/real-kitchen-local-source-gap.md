# Real kitchen cabinet / sink / tap: gap in locally available sources

**Outcome: no genuine, externally authored kitchen cabinet, sink or tap model exists among the sources available locally in this checkout (2026-10-14).** No import packet or Blender import script is produced, because there is nothing genuine to import. This record is scoped strictly to *files already on disk*. It does **not** claim that no suitable source exists anywhere.

No web research was done for this record. Under the owner's rule, web or browser research may use only the configured isolated Playwright MCP, and that MCP is not available in this session. No curl, wget, WebFetch or WebSearch call was made. The evidence below comes only from files in the checkout and their metadata.

## Correction to `real-kitchen-cabinet-sink-search.md`

That earlier record is titled "no genuine source found", and its outcome line reads "(b) no genuine acquirable source". Its actual scope was much narrower than that wording:

- **CC0 only.** CC-BY and royalty-free models were excluded, but the owner accepts properly licensed non-CC0 models.
- **Partial search.** It searched a handful of sites by API on one day.
- **Incomplete sources.** It did not check CGTrader or TurboSquid. Smithsonian was not reached because of a rate limit. Sketchfab downloads needed a login, so no files were inspected.

Its conclusion therefore means only **"no free CC0 match was found in that limited search."** It does not mean that no genuine source exists. A clearly marked scope note has been added at the top of that file. The rest of that file is unchanged.

## 1. Local 3D asset inventory

**Scope of the inventory**

- **What was searched:** every `*.glb`, `*.gltf`, `*.fbx`, `*.obj` and `*.blend` file, plus `*.usd*`, `*.dae`, `*.stl`, `*.ply` and `*.zip`. The search excluded `node_modules`, `.git` and `.claude/worktrees`, which are copies of the same tree.
- **Where it looked:** the checkout itself, local `out/`, and a filesystem-wide `find` outside the repository (`/tmp` and the scratchpad).
- **Downloads folders:** none exist.
- **What the outside search found:** only decoded copies of the character, chair and controller files. No kitchen files.
- **How files were read:** glTF/GLB JSON chunks were parsed with `python3 -I`, giving node and mesh names, accessor bounds, triangle counts and material and image counts. `.blend` object names were read with `strings` (`OB…` IDs). The single FBX was name-scanned.

### Kitchen-related hits (names matching kitchen|cabinet|sink|faucet|tap|counter|drawer|cupboard|basin)

| Path | sha256 | Origin / licence (quoted from local files) | Structure measured from file | Verdict |
|---|---|---|---|---|
| `web/house/assets/kitchen-cabinet-original/cabinet.glb` | `f7796dd06a4e13b87f46fccd2b10cb9cf5c5fbd89b69f447da9597ea27793bc3` | `cabinet.json`: "Original Blender construction: four independent fronts, real thin carcass, reveals and understated lower brass pulls." Built by our own `tools/build_home_upper_cabinet.py`. | 9 nodes / 9 meshes, 2 materials, 0 images, about 1,728 triangles. Carcass bounds x ±1.55, y ±.35, depth .36. Doors 1–4 are separate nodes with the origin at the left (−x) edge, at translations x −1.548 / −.773 / .002 / .777, z .165. Leaf local bounds x 0..0.771, y ±.33, z ±.009. Each brass pull is parented to its door. | **Rejected.** This is the existing *upper* cabinet and was authored by us. Root's provenance inventory already marks it `replacement_required`. It is not a genuine external source, and it is not a base unit or a sink. |
| `web/house/assets/kitchen-cabinet-original/cabinet.blend` | `4cc26a1ab62c7ed4874079ff29d5532d00829741db8f8770c19669089645a3ae` | Same build script. | Objects: Cabinet carcass, Cabinet door 1–4, Cabinet brass pull 1–4. | Rejected for the same reason (the source of the row above). |
| `web/house/assets/lighting/gi-architecture.glb` | `ca4ee39b59a60cd6d2c4226c90daf4b38ba88840d34c47b8f0e906e107d0754a` | Our baked GI receiver export. | 103 nodes, 0 materials, about 219k triangles. Nodes `house-lower-cabinet-carcass` and `house-upper-cabinet-Cabinet_carcass` are bake receivers of the procedural and Blender carcasses. | **Rejected.** This is a lighting bake of our own geometry, with no doors and no materials. |
| `web/house/assets/lighting/architecture.glb` | `a1383f264067f82233eceb962c22346ce966875f203505ddbbe162d254af618c` | Our static architecture export. | 67 anonymous `house-static-N` nodes, 0 materials. | Rejected because it is our own procedural geometry. |
| `web/house/assets/cc0-porta-espresso/source.glb` | `b51e1c8d4e17b3e569270126113ec266c52c5faa49a8383f01c2981c8bcbf8e6` | `LICENSE.txt`: "Porta Espresso by Innerscene. CC0-1.0." `provenance.json`: "Compact ivory enamel / bronze / steel espresso machine…" | 46 nodes / 45 meshes, 6 materials, 7 images, about 15.3k triangles. The hits are "Removable drip basin …" and the material "Warm ivory satin cabinet enamel". | **Rejected.** This is a genuine CC0 external model, but it is an espresso machine that is already in use. "Basin" means its drip tray, not a sink. |
| `web/house/assets/cc0-porta-espresso/porta-espresso.glb` | `20bf877c4f750da4e7bbff89ae2dddc0c71b647d9ac7d469293bf071bf10d3b4` | Prepared derivative of the row above. | 6 nodes. | Rejected for the same reason. |
| `web/room/room_clean.glb` | `cdd33006719f9c867e5dd3a43ef744054218259204e7d93c651373759ecaeb47` | `web/room/CREDITS.md`: "built in Blender 4.2 from simple modelled parts plus a few scanned props … Everything in the file is CC0, or original work". The fridge and door are "built from code in `room_build/build_room.py`". | 19 nodes. The only hit is `hangers` (door hooks). The fridge is fused into `room_static`. | **Rejected.** This is the old bedroom, and it has no kitchen units, sink or tap. |

### All other local 3D files (checked, not kitchen-related)

| Group | Files | Why rejected |
|---|---|---|
| Our original Blender furniture | `bed/`, `bedside-lamp/`, `coffee-machine/`, `coffee-table-original/`, `office-desk-original/`, `office-shelves-original/`, `sofa-original/`, `bedding/` (`.glb` and `.blend`) | Authored by us. Object names are bed, lamp, espresso, table, desk, shelves and sofa parts. None is a kitchen unit. |
| Poly Haven CC0 models (`web/house/assets/*` and `lite/*`) | `desk_lamp_arm_01`, `modern_arm_chair_01`, `modern_coffee_table_01`, `potted_plant_01`, `side_table_01`, `sofa_03`, `throw_pillows_01` | Genuine CC0, but none is kitchen furniture. |
| Other external CC0 | `cc0-queen-bed/`, `haven-sofa/` (with `LICENSE.txt` and `provenance.json`) | A bed and a sofa. |
| Bedroom props | `web/room/props_tripo.glb` (T_ramen, T_mug, T_headphones, T_sneakers), `props_tripo2.glb` (T2_lamp), `props_picked.glb` (notebook, pen_pencil, earbuds, key_bowl, keys, hamper), `food.glb`, `bottle.glb`, `mouse*.glb`, `monitor.glb`, `controller.glb`, `hand_phone.glb`, `sneakers_door.glb`, `room.glb` (a single `Mesh_0`) | Small props and the old room. There are no cabinets, sinks or taps. |
| Characters and animation | `web/room/char_*.glb`, `boy*.glb`, `mh_mx/*`, `mh_v5/*`, `desk_states/*`, `web/house/assets/first-person/*`, `docs/proposed/{bed-transition,seat-pose-fit,controller-*,phone-capture,standing-idle-retarget}/*`, `room_build/charfix/ref_feet.glb`, `out/seat-fit-cache/*` | Skinned characters and animation clips (66–87 joints, often 0 meshes). |
| FBX | `docs/design/chair-tripo/chair_owner_raw.fbx` (`3b6fa857…`) | The raw source of the owner chair. |
| OBJ / USD / DAE / STL / PLY / ZIP | none found | — |

**Result:** the checkout contains no externally authored kitchen base unit, wall unit, sink bowl or tap. The only kitchen cabinetry is ours: the procedural lower run and the Blender upper unit.

## 2. Actual kitchen slots a replacement must fit

All coordinates are browser metres; +y is up and the kitchen wall is at −z. UE cm = (x, z, y) × 100, and UE yaw = −source yaw.

| Slot | Geometry | Cite |
|---|---|---|
| Counter slab | Shape ±1.58 × ±.35 at (−2.2, .8675, −3.53): x −3.78..−0.62, z −3.88..−3.18, underside .8675, depth .055, so the top is at **.9225** | `web/house/home.js:663-674` |
| Sink opening (hole in the slab) | Local x −.82..−.18, y −.26..+.17. After the −90° X rotation this is world x −3.02..−2.38, z −3.70..−3.27 | `home.js:666-669` |
| Sink bowl (procedural) | Floor .64 × .43 at (−2.7, .754, −3.485). Walls at x −3.015 / −2.385 and z −3.6925 / −3.2775. Rim at y .93. Drain at (−2.7, .766/.770, −3.485) | `home.js:722-729` |
| Tap (procedural) | Tube from (−2.7, .93, −3.79) up to y 1.24 and out to the spout end (−2.7, 1.16, −3.53). Base cylinder at y .935. Lever beam (−2.65, .95)→(−2.61, 1.04) at z −3.79 | `home.js:730-739` |
| Under-cabinet strip | 3.1 × .035 × .43 at (−2.2, 1.68, −3.69), so its bottom is at about 1.6625 | `home.js:712-721` |
| Lower run carcass | x −3.725..−0.675 (3.05 m), z −3.86..−3.1975, y 0..0.8675. Sides at x −3.716 / −.684. Partitions at x −2.95 / −2.25 / −1.55. Fillers: .10 on the left, .20 on the right | `web/house/lower_kitchen_cabinet.mjs:31-48` |
| Lower doors | 4 leaves .65 × .76 × .035, centres x −3.3 / −2.6 / −1.9 / −1.2. Pivot `Lower_cabinet_hinge_i` at (c − .325, .44, −3.192); leaf child at local (.325, 0, −.023). **Hinged on the left (−x) edge**, open angle −0.49π | `lower_kitchen_cabinet.mjs:2-6, 52-70` |
| Upper run | Our Blender unit at (−2.2, 2.05, −3.71) with a 3.1 × .7 × .36 fallback box | `home.js:675-705`; `tools/build_home_upper_cabinet.py:40-79` |

## 3. What the runtime door bindings actually require

The owner asked not to insist on four doors unless the bindings truly need four. The source shows the following.

**Lower run**

- **The doors are built procedurally, not loaded.** `createLowerKitchenCabinet` builds its own leaves from `LOWER_CABINET.centers` (`lower_kitchen_cabinet.mjs:3, 53-70`). It does **not** look up meshes by name. A replacement leaf mesh could be parented to each `Lower_cabinet_hinge_i` pivot in place of the RoundedBox leaf, without any change to the bindings.
- **Count.** The *persisted state* is what truly needs 4:
  - `setTargets` throws unless it receives exactly 4 booleans (`lower_kitchen_cabinet.mjs:74`).
  - The API rejects any `lowerCabinets` value that is not 4 booleans (`home_api.py:282-287`).
  - The world loader resets any other shape to `[False]*4` (`home_world.py:243-248`).
  - `home.js` defaults to four `false` values (`home.js:654, 2647`).
  - The API test checks this (`tests/test_home_api.py:111-113`).

  Changing the door count therefore means a coordinated change to `LOWER_CABINET.centers`, the `setTargets` length, `home_api.py`, `home_world.py`, the `home.js` defaults and the tests. A migration of saved 4-length state is also needed, because `home_world.py` would otherwise silently reset it.
- **Geometry assumptions in the collision and sweep model** (`lowerDoorBlocks`, `lower_kitchen_cabinet.mjs:7-13`):
  - There is one shared `width` of .65, so all doors are the same width. Unequal modules need a per-door width.
  - The leaf occupies local x 0..width, so it is **left-hinged**. A right-hinged door needs a mirrored x range and a +0.49π angle.
  - Local z runs from −.0405 to .022.
  - The vertical span is `hingeY ± halfHeight` (.44 ± .38).
- **Bake.** Only `Lower_cabinet_carcass` (bakeId `house-lower-cabinet-carcass`) is static-baked. Leaves and pulls are `excludeStaticBake` (`lower_kitchen_cabinet.mjs:49-62`). A new carcass needs a GI rebake.

**Upper run**

- **Name lookup.** `attachUpperCabinetDoors` *does* key on node names. For i = 1..4 it looks for `Cabinet_door_i` or `Cabinet door i`, and throws if one is missing (`cabinet_doors.mjs:34-36`).
- **Hinge from origin.** It takes the hinge from each panel's **origin**, shifted +.014 in z (`cabinet_doors.mjs:37-43`). A replacement door node therefore needs its origin on the hinge edge.
- **Collision model.** It assumes width .771, thickness .044, half-height .33, and a leaf extending to local +x, i.e. left-hinged (`cabinet_doors.mjs:3-7, 18-19`).
- **Count.** Persisted `cabinets` must be exactly 4 booleans (`cabinet_doors.mjs:70-71`; `home_api.py:282-287`; `home_world.py:243-248`).

**Native Unreal:** the native cabinet interaction code is not in Git; it is root-owned. Root's screenshots `docs/screens/home/private-{lower,upper}-cabinet-native-interaction.jpg` show both banks in use natively. It is unverified here whether the native side keys on these names or on the 4-boolean state. Root must confirm this before any change to the door count.

## 4. Search plan for when the isolated Playwright MCP is configured

Web research is **blocked** until the isolated Playwright MCP is available. When it is, use only that MCP. Do not use the personal Chrome session, curl or WebFetch. Run the searches below and record, for every hit, the URL, author, the exact licence text, whether a login or terms acceptance is required, and the file format.

The following are not allowed without a separate owner decision:

- paid purchases or subscriptions;
- creating an account;
- accepting legal terms (EULA or general model licence click-through).

Any source that requires one of these is recorded as a *lead*, not acquired.

**Licence acceptance**

| Licence | Status |
|---|---|
| CC0 | Acceptable. |
| CC-BY 3.0/4.0 | Acceptable; record attribution exactly. |
| Royalty-free, permitting private use and modification | Acceptable. |
| CC-BY-NC, -ND and "editorial" | Rejected, because modification and use must be allowed. |

| Source | Queries / filters | Notes |
|---|---|---|
| Poly Haven (`polyhaven.com/models`, CC0) | Categories furniture and props; tags kitchen, cabinet, sink, faucet, tap, cupboard, drawer | Re-verify the earlier negative CC0 result. Downloads need no login. |
| Sketchfab | Search with the "Downloadable" feature filter and the licence filters "CC Attribution" and "CC0" (read the filter ids from the page; none are hard-coded here). Queries: "kitchen base cabinet", "kitchen cabinet doors", "modular kitchen", "kitchen sink", "undermount sink", "inset stainless sink", "kitchen faucet", "kitchen mixer tap", "IKEA METOD" | Check the model page for "Downloadable", the licence badge, and whether doors are separate objects (model inspector / object list). Download requires a login, so record leads only unless the owner approves. |
| BlenderKit free tier | `blenderkit.com/asset-gallery?query=kitchen cabinet` with "free" (and sink, faucet, mixer tap). Licence is per asset (royalty-free or CC0) | Account required, so leads only. The earlier paid CC0 tap leads (Kitchen Monobloc Mixer by Strawberry) stay recorded as paid. |
| CGTrader free | `cgtrader.com/free-3d-models?keywords=kitchen cabinet` (and sink, faucet), licence "Royalty Free" | Login and EULA, so leads only. |
| TurboSquid free | `turbosquid.com/Search/3D-Models/free/kitchen-cabinet` (and sink, faucet) | Login and EULA, so leads only. |
| Manufacturer CAD/BIM | IKEA (METOD/ENHET product 3D, if downloadable); BIMobject and the manufacturer pages for sinks and taps (Franke, Blanco, Grohe, Hansgrohe), with door hardware from Blum and Hettich for hinge geometry | Read each portal's own licence. Many permit use in project design but forbid redistribution, so a GLB derived from them must stay private and unpublished. |
| Smithsonian Open Access (CC0) | Retry the earlier rate-limited query ("kitchen", "sink") | Low likelihood. |
| Excluded | Kenney and Quaternius | Stylised low-poly; excluded for realism. |

**Acceptance tests for any hit:**

1. Real-world metric scale.
2. Lower doors, upper doors and drawer fronts are **separate meshes** whose hinge edges can be found from per-door bounds.
3. The run fills 3.05 m by **uniform scale only, or by repeating a genuine module**. For example, five 0.6 m modules plus a 0.05 m filler. No stretching.
4. A sink base with a bowl that fits the existing opening, x −3.02..−2.38 and z −3.70..−3.27, or the slab opening is changed to fit the sink's measured cut-out.
5. Tap height stays under the strip at about 1.66.

Only a hit that passes all five should get a `real-kitchen-replacement-packet` and a Blender import candidate. The pattern for that builder is `tools/build_real_lamps.py`: an additive GLB, a hide manifest, and a fingerprint abort.

## 5. What happens now

The following stay exactly as they are:

- the procedural lower run (`lower_kitchen_cabinet.mjs`);
- the Blender upper cabinet (`home.js:675-705`);
- the procedural sink and tap (`home.js:722-739`).

Nothing is hidden and no runtime files are changed.
