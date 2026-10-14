# Real lamps: proposal and root commands (private, server only)

Status: proposal. Nothing here has been run yet. Root or the renderer is the only
Blender/Unreal executor, and every run stays on the same private pod before the fixed
stop at 18:18:23 UTC. Nothing is deployed and the live site is not touched.

## What changes

| Role | Real asset (CC0, modeled Poly Haven model) | Replaces (hidden, never destroyed) | Excised exact components |
|---|---|---|---|
| DeskLamp | `desk_lamp_arm_01` (the existing red one, moved from the right of the desk to the left) | node 126 `Mesh_106`, the white glow disc (`web/house/home.js:1113`); the red instance nodes on the right (`home.js:625`, matched by materials `desk_lamp_arm_01*`) | white stem `beam([1.1,.85,-3.15],[1.1,1.3,-3.15], .014)` (`home.js:1114`), which sits in the shared rail-metal batch node 163 / Material 8 |
| LowerPendant | `modern_ceiling_lamp_01` | node 127 `house-static-64` glow disc (`home.js:1152`); body/cable (`home.js:1150-1151`) if standalone | body/cable if batched |
| UpperPendant | `modern_ceiling_lamp_01` | node 129 `house-static-65` glow disc; body/cable if standalone | body/cable if batched |
| BedLamp | `industrial_pipe_lamp` (reviewed copy at `/workspace/sub01-home-private/reviewed-furniture/industrial_pipe_lamp`; native size 18.3 × 36.4 × 26.2 cm) | the old procedural bedside lamp (`tools/build_home_bedside_lamp.py`, `home.js:1117-1131`): nodes 195 `Brass_base`, 196 `Brass_socket`, 197 `Brass_stem`, 198 `Bulb`, 199 `Linen_shade` | none |

Wording: `desk_lamp_arm_01`, `modern_ceiling_lamp_01` and `industrial_pipe_lamp` are
modeled Poly Haven assets. The desk_lamp source is not documented as scanned or
photographed, so it is not described that way here.

Rules:
- Emitter nodes 126, 127, 129, 198 and 199 are **hidden**, never excised or
  destroyed, so the native fixture guards (`tools/unreal_native_fixture_emission.py`)
  still find their exact actors.
- Node 66 (KitchenWork) and every screen, monitor, TV, phone, keyboard or PC
  identity are refused as hide targets.
- A shared batch is never hidden as a whole. The builder selects lamp parts inside
  a batch by **exact welded connected components** that fit the home.js cylinder
  (endpoints and radius, ±1.5 mm). It refuses when there is no match or when
  there is more than one candidate set. It writes those triangle IDs to
  `lamp-excision-triangles.json`. `combined-remainder-spec.json` holds the union with
  root's rail excision (the 45 rail components in nodes 162/163) as **one**
  remainder edit per node and primitive. Any triangle claimed by both sides is a
  hard refusal.
- Real size only: uniform scale 1.0. The pendant cable is shortened or lengthened
  along its axis only (thin rod band; the cross-section does not change), so the
  canopy touches the measured ceiling underside and the bulb sits at the light.

## Coordinates

DeskLamp light `SUB01_AuthoredLight_DeskLamp`: source `[1.1, 1.35, -3.15]`
(`tools/unreal_home_lights.py:17`, `web/house/home.js:1132-1133`)
→ Blender `(1.1, 3.15, 1.35)` → UE contract `(110, -315, 135)` cm. Unreal re-verifies
the actual offset and axes from the hidden originals' pivots with
`unreal_home_coordinates.infer_import_transform`, and refuses on any mismatch.

Expected placements (the server measures the real values):
- DeskLamp: yaw 180° (shade over the desk, arm toward the wall). The bulb is at
  x 1.1, z -3.15, and the flange and grommet pin rest on the desk top (y ≈ 0.845).
  At real size the bulb is at y ≈ 1.54, so the light at 1.35 is about 19 cm below
  it, outside the shade. **Proposal** (not applied): move the DeskLamp light to the
  reported `bulb_source_m`.
- Pendants: the canopy sits flush on the BVH-measured ceiling underside, and the
  bulb is at the light (`LowerPendant (-2, 2.43, .5)`, `UpperPendant (2, 4.98, -.2)`).
  On a low ceiling the cable is clamped to 3 cm and the report shows the bulb
  offset. Pendant globe components get `cast_shadow = False` so the globe does not
  trap the light.
- BedLamp: the pipe lamp stands on the nightstand top (`side_table_01`, y ≈ 3.5).
  Its footprint is centred on the old lamp axis (x, z) = (-3.55, -3.1), with all
  footprint corners plus a 1 cm margin on one flat top. The real bulb offset from
  the BedLamp light is reported as a proposal; the light is not moved.

## Root commands (server)

```bash
cd /workspace/sub01-home-private
BL=/workspace/sub01-tools/blender-4.5.3-linux-x64/blender
SRC=out/lighting-v23/unreal-home-lab/Sub01HomeLab/SourceAssets/full-home.glb   # exact GLB Unreal imported
sha256sum "$SRC"   # must be 9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b
CEIL=$(ls out/furniture-refresh/*/modern_ceiling_lamp_01*.gltf out/furniture-refresh/modern_ceiling_lamp_01*/*.gltf 2>/dev/null | head -1)
# 1) dry run: identification, supports, collisions, manifests (no GLB export)
$BL --background --factory-startup --python tools/build_real_lamps.py -- \
  --source-glb "$SRC" --ceiling-lamp "$CEIL" \
  --desk-lamp web/house/assets/desk_lamp_arm_01/desk_lamp_arm_01.gltf \
  --bedside-lamp /workspace/sub01-home-private/reviewed-furniture/industrial_pipe_lamp \
  --rail-excision <root rail builder triangle-ID manifest.json> \
  --output-dir out/real-lamps --dry-run
# 2) real build: same command without --dry-run
```

Base .blend: none (`--factory-startup`). The builder imports the exact `full-home.glb`
that Unreal imported, so GLB node indices, Blender objects and the actors
`full-home_node_<N>` describe the same geometry. The assembled `house.blend` from
`tools/assemble_home_blender.py` swaps furniture and so differs from Unreal. If a
base .blend is passed, every hide target must map to exactly one object by
evaluated world bounds; otherwise the builder refuses.

Outputs in `out/real-lamps/`: `real-lamps.glb` (world-placed, additive),
`SUB01_RealLamp_<role>.glb` (local frame, for UE), `placement-report.json`,
`original-hide-manifest.json`, `lamp-excision-triangles.json`,
`combined-remainder-spec.json` and `provenance.json` (Poly Haven URLs, CC0, sha256
of every file). Pre-existing objects are fingerprinted, and any change is a refusal.

Unreal (sole editor owner, ActualHome already loaded):

```python
import sys; sys.path.insert(0, '/workspace/sub01-home-private/tools')
import unreal_import_real_lamps as r
r.run('/workspace/sub01-home-private/out/real-lamps', dry_run=True)   # verify everything, change nothing
r.run('/workspace/sub01-home-private/out/real-lamps')                 # import, spawn SUB01_RealLamp_<role>, hide originals
```

Root's single remainder surgery consumes `combined-remainder-spec.json` for nodes
162 and 163. This import does not excise anything.

## Visual checks (native capture, before claiming anything)

1. Desk from the chair: one red arm lamp on the LEFT, standing on the desk top
   (no gap, not through the monitor or keyboard). The right side has no lamp, and
   there is no white disc or stem.
2. Lounge and loft from below: each glass globe hangs from a canopy flush with the
   ceiling, with no floating and no rod through the ceiling. The old white
   cylinder and black cable are gone.
3. Bedside: the pipe lamp stands on the nightstand, and the linen shade lamp is gone.
4. With lamps off, the new lamps do not glow (all emissive inputs zeroed). Screens
   are unchanged.

## Rollback

`r.run(out_dir, restore=True)` restores the exact previous hidden state recorded in
`unreal-real-lamps-state.json` and removes only the `SUB01_RealLamp_*` actors. The
imported assets under `/Game/Sub01Home/RealLamps/` stay unreferenced and can be
deleted manually. To roll back the excision, rerun root's surgery with only the rail
manifest.

## Emission slots for the emission-toggle agent

All imported materials are owned copies named `SUB01_RealLamp_<role>_<source material>`
with emission at zero:
- DeskLamp: `SUB01_RealLamp_DeskLamp_desk_lamp_arm_01` (body),
  `SUB01_RealLamp_DeskLamp_desk_lamp_arm_01_light` (bulb; source emissiveFactor
  1, .984, .649).
- Pendants: `SUB01_RealLamp_<Lower|Upper>Pendant_modern_ceiling_globe` (bulb; source
  emissive .623, .542, .475), `..._modern_ceiling_lamp_01_glass`, `..._modern_ceiling_lamp_01`.
- BedLamp: `SUB01_RealLamp_BedLamp_<pipe lamp bulb material>` (the exact name is in
  `placement-report.json` → `roles.BedLamp.emission_slots`).

In UE the parameters are the Interchange glTF MIC parameters whose names contain
`Emissive` (`EmissiveFactor`, `EmissiveStrength`). The emission-toggle agent owns any
non-zero value.
