# Sofa controller play: trial grip and seating (verified: false)

**Status: TRIAL, verified false.** Nothing here accepts a keyboard contact, a controller contact or a sofa contact. The native adapter is not staged, compiled or running. Minecraft input still uses the existing plumbing (`games/minecraft/native_input.cjs`), which only proves the input path. It is not two-handed controller play.

Files:
- `tools/fit_controller_grip.py`: the solver (pure Python and numpy).
- `tools/unreal_controller_play_runtime.py`: the native adapter fragment, its evidence gates and its install.
- `tests/test_fit_controller_grip.py`: the tests.
- `docs/proposed/controller-play/controller-grip-gaming.summary.json`: the real run, per frame.

## 1. Inventory

### Captured seated controller clip

**Mixamo "Gaming".** This is the owner's own official Mixamo download, `Gaming.fbx`.

Provenance:
- FBX sha256 `84dfc60ab9e13b9c896e89def81478a5e47f45b80cc3d8902c5b8a0ae8d8fc7f`, 649,024 bytes (declared by root).
- Manifest role `downloaded_gaming` (`tools/stage_first_person_assets.py`).
- The raw FBX is private and is never in Git.

`docs/design/mixamo/README.md` says: "Gaming (5.0 s): **seated**, a controller held in both hands over the lap, head down. The performer sits low (hips 0.58 m before scaling)." The capture sheet is `docs/design/mixamo/phone_gaming_postures.jpg`.

The clip used here is DERIVED: `docs/proposed/controller-capture/gaming-owner.glb`.
- Root made it with the official Blender export plus an aligned-world rest-delta retarget onto the unchanged owner skeleton.
- Audit `gaming-owner.glb.audit.json`:
  - source raw GLB `e4838742…0426`;
  - target owner `9d8646d2…95ea`;
  - output `f8b00ce5…6c09`, which equals the committed file;
  - bone-length error 5e-16;
  - `proceduralMotionAdded: false`;
  - 24 moving source finger channels.

What the solver measured on this clip:

| | Value |
|---|---|
| Skeleton | Owner Mixamo 65 joints. Bone lengths equal the owner skin's bind (char_mixamo.glb `7609ecc…`), for example forearm 23.1210 vs 23.1210 cm. |
| Frames | 152 captured key times, 5.0333 s |
| Seated | Yes. Thighs are at least 88.2° from vertical in every frame. Hips are 44.7–45.2 cm over the feet and about 50.5 cm over the floor. |
| FK parity with root, t = 4 s (glTF cm) | Hips (2.3456, 50.5276, 11.0024), Head (2.6834, 105.621, 16.4187), LeftHand (20.1514, 88.0128, 50.2592), RightHand (-8.7231, 85.4654, 51.5078). The max error is 1.5e-4 cm. |
| Wrist joints apart | 28.11–29.39 cm |
| Contact geometry apart (skinned palm patch / distal thumb / distal index centroids) | Palms 23.79–25.10 cm (closest palm vertices 19.39–20.88 cm). Thumbs 12.05–13.78 cm. Index fingers 16.52–18.19 cm. |
| Controller | 15.38 cm wide. Its grip axes are about 9.7 cm apart, its stick caps 5.0 cm, its face-button centre to left stick 6.6 cm, and its triggers 9.0 cm. |
| Left Hand in the right Hand frame | Drift 2.04 cm max (p95 1.49 cm) and 0.93° max |
| Captured local rotation amplitude, deg from frame 0 | Thumb2: L 13.6, R 12.6. Index2: L 11.2, R 11.4. Index3: L 7.3, R 10.6. Thumb1/Thumb3 are 0–0.9. |

Earlier estimates are not used:
- The earlier "13.47–14.17 cm wrist spacing" was a scaled source gap, and root withdrew it.
- No proxy or synthetic stand-in is used for the real numbers.
- A fallback exercise on `web/house/assets/first-person/texting.glb` (standing, one-hand phone) only proved the pipeline. It is not reported as a result.

### Controller mesh

`web/room/controller.glb`, sha256 `c034a144…17e4`.
- Licence: CC0. It was modelled in code for this project by `room_build/build_desk_tech.mjs` (`web/room/CREDITS.md`).
- It was decoded with the existing `tools/uncompress_unreal_glb.mjs` and the vendored MeshoptDecoder (KHR_mesh_quantization node transform applied).
- The `controller_contact` mesh is a baked alpha-blend contact shadow. It is excluded from all grip and collision geometry, both by mesh name and by an alpha/contact material check.

Body geometry:
- 7,297 vertices and 13,848 triangles.
- Bounds x ±7.690 cm, y 0..5.586 cm, z ±5.182 cm, so 15.38 × 5.59 × 10.36 cm.
- 724 boundary edges (the open lathe caps and the D-pad) and 0 non-manifold edges. "Inside" therefore uses the generalized winding number |w| > 0.5.

Measured features (controller frame: x across, y up, z toward the player):
- Stick caps: L (-3.299, 5.586, -1.865) cm, R (1.701, 5.586, 0.435) cm. They agree with the authoring constants to 0.0015 mm after a measured shift of (0, -0.014, -0.66) cm.
- The face-button, trigger and grip regions are the authoring constants moved by that shift. Their distances to the actual surface: face-button centre 4.7 mm, triggers 2.2 mm.

### Sofa

`web/house/assets/haven-sofa/sofa.glb` (CC0, Innerscene, sha256 `92b7db30…398d`), at the runtime origin (-1.8, 0, 0.1) m and yaw -90°. The mapping is UE = 100 × (web x, web z, web y).

Authored seat cushions:
- Two edge-connected upward linen patches, each 5,808 cm² projected.
- Top 50.30 cm.
- UE X -221.2..-154.0, Y -79.8..8.6 and 11.4..99.8.
- Footprint X -226.25..-133.75, Y -103.75..123.75.

**There is no native measured sofa surface.** These numbers are source geometry, not a measurement.

## 2. Solver results (raw residuals, all 152 frames)

The contact rules:
- Palm local support patch: nothing deeper than -0.3 cm, the lowest point within +0.3 cm, and at least 12 palm vertices within -0.3..+0.3 cm.
- Full-hand collision: every vertex of each hand (L 3,915 and R 4,094 vertices), checked with exact point-triangle distance plus the winding number.
- Finger motion is the captured motion. Nothing is posed.

The palm patches are asymmetric: L 147 and R 377 vertices, because of the owner skin's weights.

| | Fixed offset on RightHand | Per-frame rigid | Bounded two-arm IK proposal |
|---|---|---|---|
| Frames with a full two-hand grip | **0/152** | **0/152** | **0/152** |
| L palm lowest gap | +3.0 cm (no contact) | +3.0 cm | -0.347..-0.346 cm (8 in band) |
| R palm lowest gap | +0.156..+0.174 cm, 4 in band | +0.10..+0.24 cm, 2 in band | -0.321..-0.301 cm (51 in band) |
| L hand deepest / penetrating vertices | -0.60 cm / 9 frames, ≤23 vertices | -0.17 cm / 0 | -0.72 cm / 152 frames, ≤89 vertices |
| R hand deepest / penetrating vertices | -1.09 cm / 152 frames, ≤137 vertices | -0.97 cm / 152, ≤137 | -1.08 cm / 152, ≤135 |
| L thumb to left stick | 5.73–7.37 cm | 5.89–7.32 cm | 0.77–1.33 cm |
| R thumb to face buttons / right stick | 1.06–1.38 / 2.96–3.80 cm | 0.98–1.47 / 2.98–3.81 cm | 3.04–3.55 / 2.30–2.66 cm |
| L / R index to trigger | 7.06–8.96 / 2.74–3.70 cm | 7.18–8.76 / 2.80–3.70 cm | 3.38–4.37 / 0.94–1.24 cm |

How the captured thumbs move relative to the controller:
- In the bounded proposal, the thumb path extent is L 1.09 cm and R 1.04 cm.
- The per-axis range is ≤ 0.64 cm.
- That is about a stick cap's travel, but the thumbs never sit on the caps: the left thumb is ≥ 0.77 cm away and the right ≥ 2.3 cm.
- The index fingers move ≤ 0.88 cm.

Hand drift:
- The two hands are nearly rigid relative to each other: drift 2.04 cm and 0.93°.
- So a fixed rigid controller is not defeated by drift. It is defeated by spacing: the captured palms are 24–25 cm apart, and the grips are about 9.7 cm apart.
- The left-only IK that removes the drift needs ≤ 2.04 cm of wrist movement, ≤ 4.5° of elbow change and 0 residual. It does not fix the spacing.

The bounded two-arm IK is a proposal and is never applied:
- Each hand keeps its own grip of the controller.
- Per frame, the controller sits at the rigid midpoint of the two hands, and each wrist moves rigidly to its grip.
- Both arms are re-solved with analytic two-bone IK.
- The hand and fingers move rigidly, so the captured finger locals are exact.

Bound: ≤ 10 cm and ≤ 25° per wrist. Measured:

| | Left | Right |
|---|---|---|
| Wrist displacement | 4.65–5.86 cm | 6.82–8.08 cm |
| Wrist rotation | 24.5–24.9° | 24.5–24.9° (at the edge of the bound) |
| Elbow change, max | 16.4° | 9.9° |
| IK position residual | 0 | 0 |
| Frames within bound | 152/152 | 152/152 |

After the proposal, contact is still not accepted:
- The palms sit 0.0–0.05 cm deeper than the -0.3 cm compression band.
- The captured finger curls enter the grips by up to 0.72 cm (L) and 1.08 cm (R).

**Conclusion:** the captured curl is tighter than this controller's grips. A grip needs one of three things:
- a controller whose grip cross-section matches the capture;
- a bounded per-frame offset search with the penetration weight raised;
- a review that accepts finger skin compression of about 1 cm. Root decides; it is not claimed here.

`validate_grip()` refuses this report: `GripFailed: full two-hand grip in 0/152 frames`.

## 2b. Option 1: penetration-aware joint search (round 2, all 152 frames)

**Controller used:** the original `web/room/controller.glb`, sha256 `c034a144…17e4`. Root's normalized derivative (`8134769e…0034`, geometry preserved) is not committed in this checkout (searched `docs/proposed/controller*` and `out/`). `controller_source()` prefers it by hash when present, and every report records which file was used. Root's `tools/unreal_import_controller_prop.py` also imports the original sha.

**Time mapping.** The GLB keys start at 1/30 s, so native AnimSequence t = glTF t − 1/30 s, and native 4 s = glTF 4.033333 s. Root's posted values match my FK at glTF **4.000000** s (native 3.966667 s) within 1.5e-4 cm. At glTF **4.033333** s (native 4.0 s) my FK gives:

| Joint | Position (cm) | Difference from the posted values |
|---|---|---|
| Hips | (2.3547, 50.5451, 11.0361) | 0.034 cm |
| Head | (2.5921, 105.5454, 16.8054) | 0.39 cm |
| LeftHand | (20.2004, 88.1431, 50.7127) | 0.45 cm |
| RightHand | (-8.6597, 84.8908, 51.9462) | 0.57 cm |

So the posted values are at glTF 4.0, which is native 3.9667 s. Reports now carry both `gltf_t` and `native_t`, and the adapter's evidence states the mapping.

**Search.** For each of the 152 frames:
- each hand's rigid grip of the controller is searched (6-DoF per hand);
- the controller sits at the rigid midpoint of the two hands;
- both wrists move under the bounded two-arm two-bone IK (≤ 10 cm, ≤ 25°), with a joint 12-DoF refinement when the bound binds;
- the hand and fingers move as one rigid unit, so every captured finger local rotation, including the 24 moving channels, is exact.

The cost puts penetration first (2 mm surrogate SDF, optimiser margin 0.1 cm), then the palm band, then the thumb and index pull. Reports use exact winding-number metrics on every hand vertex.

Provisional gates: thumb distal centroid within 2.0 cm of the stick or face-button cap centre; index distal centroid within 3.0 cm of the trigger.

| | contact-first (`--aim contact`) | all constraints (`--aim all`) |
|---|---|---|
| Frames passing everything | **0/152** | **0/152** |
| Frames with palm patch + no penetration (both hands, within the IK bound) | **129/152** (frames 23–151) | 61/152 |
| Frames meeting the thumb + index gates | 0 | 0 |
| Left thumb to left stick | 0.79–2.67 cm (≤ 2 cm in 151 frames) | 0.79–2.00 cm (151) |
| Right thumb to face buttons or right stick | 2.72–3.87 cm (never ≤ 2) | 2.36–3.41 cm (never) |
| Left index to trigger | 3.31–5.21 cm (never ≤ 3) | 3.30–5.10 cm (never) |
| Right index to trigger | 2.27–3.88 cm (2 frames ≤ 3) | 1.95–3.43 cm (56 frames) |
| Wrist IK, left / right | ≤ 5.16 cm / ≤ 8.73 cm, ≤ 24.8° | ≤ 5.62 / ≤ 8.08 cm, ≤ 24.8° |
| Elbow change, left / right | ≤ 16.6° / ≤ 6.3° | ≤ 18.7° / ≤ 6.3° |
| Frames within the IK bound | 152 | 152 |
| Searched grip variation across frames (right / left) | 3.0 cm, 30.6° / 1.8 cm, 16.9° | 2.9 cm, 30.6° / 1.8 cm, 17.2° |

Findings:
- **Contact is reachable for most frames.** With the bounded IK, 129/152 frames hold both palms on the grips without finger penetration. Frames 0–22 still need up to 0.62 cm of finger-skin compression.
- **Thumbs and index fingers are not.** The captured right thumb never comes within 2.36 cm of a cap, and the captured left index never within 3.3 cm of its trigger, while contact holds. This is the captured finger pose against this controller's layout, not a solver residual.
- **The grip is not one socket offset.** It varies by up to 3 cm and 31° across frames. Native play would need either a per-frame controller track baked with the IK into a derived clip, or a fixed offset at the cost of these residuals.

**Option 3, finger-skin compression needed** (deepest hand vertex inside the controller, per frame; `compression_needed_cm` in the summaries):

| | Left hand | Right hand | Worst of both hands |
|---|---|---|---|
| contact-first | 0.23–0.62 cm (median 0.27) | 0.22–0.28 cm | ≤ 0.30 in 129 frames, ≤ 0.50 in 131, ≤ 0.62 in all 152 |
| all constraints | ≤ 0.63 cm | ≤ 0.37 cm | ≤ 0.63 cm |

**Option 2, pad width needed** if the captured hand spacing is kept with no IK: the right hand holds its searched grip and the left palm misses the controller surface by 4.72–7.56 cm (median 5.68). That is a total pad of up to 7.56 cm, or about 3.78 cm per side if symmetric, and a contact width of up to 22.94 cm against the controller's 15.38 cm. The `--aim all` numbers are 4.96–7.50 cm.

`validate_grip()` refuses both search reports. The gate also requires one socket offset (≤ 0.3 cm, ≤ 1°) and an IK-baked derived clip (`clip.ik_baked`), and neither exists.

Commands:

```
python tools/fit_controller_grip.py search --clip docs/proposed/controller-capture/gaming-owner.glb --aim contact|all \
    --source-fbx-sha256 84dfc60ab9e13b9c896e89def81478a5e47f45b80cc3d8902c5b8a0ae8d8fc7f --out OUT.json
```

Per-frame summaries: `docs/proposed/controller-play/controller-search-{contact,all}.summary.json`.

## 2c. Derived grip clip `SUB01_GamingGrip` (label `derived_from_capture`), iteration 1: PARTIAL

`tools/derive_controller_grip_clip.py` derives a grip clip from the real capture `gaming-owner.glb` (sha `f8b00ce5…`) against the actual 15.38 cm controller. The original `c034a144…` was used because the normalized file is not in this checkout. The controller is not oversized.

How it is derived:
- **One fixed controller offset** in the right Hand socket, and one left grip.
- **Bounded two-arm two-bone IK** per frame (≤ 10 cm, ≤ 25°). It changes the Arm and ForeArm rotations, and the Hand local so the hand reaches its grip.
- **Fingers:** the captured locals stay as the base. A constant curl delta (joints 1–3) and a spread delta (joint 1), each ≤ 15°, is added per finger. Because the delta is constant, it is smooth, and the captured frame-to-frame variation is unchanged.
- **Unchanged:** translations, clavicles, spine, neck and head.

Outputs: `docs/proposed/controller-play/SUB01_GamingGrip_derived.glb` (280 KB) and `…derived.report.json` (per frame: contact, penetration, thumb/index distances, IK displacement, finger deltas and seam).

| Iteration 1 | Value |
|---|---|
| **Frames passing every gate** | **21/152** (`all_frames_pass: false`, `status: partial`) |
| Frames with contact (both palm patches in -0.3..+0.3 cm with ≥ 12 vertices, no vertex deeper than -0.3 cm, IK within bound) | 144/152 |
| Frames with thumbs ≤ 2.0 cm and index ≤ 3.0 cm | 22/152 |
| Left thumb / right thumb to cap | 1.29–1.93 cm / 1.97–2.20 cm (gate 2.0) |
| Left index / right index to trigger | 2.69–3.22 cm / 2.74–2.86 cm (gate 3.0) |
| Deepest hand vertex | L -0.316 cm (3 frames), R -0.371 cm (5 frames). The band is -0.3 cm, with no compression allowance. |
| Fixed offset | Holds: 6e-14 cm, 2.4e-6° |
| IK | ≤ 4.35 cm left, ≤ 8.52 cm right, ≤ 15.3° |
| Largest finger delta | 14.7° (left index curl); right thumb spread -11.5° |
| Bone-length error | 2e-14 cm |
| Upper-body change | 0 |
| Loop seam on edited joints | 0.433° (captured 0.433°) |

Failing frames are listed in the report. They fail mostly because the right thumb sits 0–0.2 cm beyond the 2.0 cm gate and the left index 0–0.22 cm beyond the 3.0 cm gate, with 8 frames slightly penetrating. Iteration 2 will add smooth per-frame delta keys.

Re-run:

```
python tools/derive_controller_grip_clip.py --sample 16 --rounds 4 --iters 400
```

### Root import steps for the derived clip

1. **Export to FBX.** Use the official Blender export at the clip's own **30 fps**, keeping all 152 keys. Native t = glTF t − 1/30 s.
2. **Import** to `/Game/Sub01Hands/Play/SUB01_GamingGrip` onto the existing owner USkeleton. The import row must carry `role: Gaming`, `same_existing_skeleton: true`, `source_fbx_sha256: 84dfc60a…` and `derived_glb_sha256` = the report's `output_glb_sha256`.
3. **Evidence.** `evidence` takes the derived report. It refuses unless `all_frames_pass`, the fixed offset holds, deltas are ≤ 15° and the label is `derived_from_capture`. Raw-capture fits and searches are refused.
4. **Runtime proof (root).** Write `private-audit/native-controller-play-runtime-proof.json`:

   ```
   {"schema": "sub01.native-controller-play-runtime-proof.v1", "accepted": true,
    "clip_object_path": "/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip",
    "evidence_revision": "<FNV of the evidence text>", "frames_measured": >=152, "frames_passing": ==frames_measured,
    "max_penetration_cm": >= -0.3, "native_capture": {"path": ..., "sha256": ...}}
   ```

   It comes from a native per-frame skin-vs-controller contact measurement of the socket-attached prop, plus a native capture. Without it, `ControllerPlayReady()` stays false.

## 3. Seated on the sofa

- **Contact rule:** the rule of `validate_unreal_seat_contact.py`, applied per region (buttocks, both posterior thighs, both soles) over the whole 5.03 s clip at ≥ 30 Hz:
  - seat band -2.5..+0.5 cm, sole band 0..+1 cm;
  - at least 12 vertices per patch over the surface and at least 12 in the band;
  - no penetration.
- **Capsule:** the standing capsule (radius 17, half-height 92) never moves while playing. It stays at the measured approach in front of the sofa. Only the body component is offset by the measured `body_offset_cm` and yaw, which is the root-motion approach. At the home_world sofa node (-255, 10) cm the source footprint leaves **11.75 cm** horizontal clearance. The evidence builder recomputes this from the measured footprint and refuses ≤ 0.
- **Camera:** it rides the captured Head socket while playing (SnapToTarget, absolute rotation) and is restored to (0, 0, 74) afterwards. The head moves 11.9 / 0.6 / 6.5 cm (x/y/z) over the clip.

## 4. Root steps (exact)

1. **Native sofa audit.** Write `private-audit/native-sofa-surface.json` with a read-only editor audit modelled on `tools/unreal_chair_surface_audit.py`:
   - Find the ONE imported HAVEN sofa component (`haven-sofa/sofa.glb`, linen material).
   - Use `ProceduralMeshLibrary.get_section_from_static_mesh` and `StaticMeshEditorSubsystem.get_lod_material_slot`.
   - Store the world-cm vertices and the upward (normal z > 0.65) edge-connected seat triangles as `sofa.sections[].vertices_world_cm` + `seat_surface.triangle_indices`, with `errors: []`.
   - Confirm that the component blocks the pawn.
   - The seat area must be ≥ 4,000 cm². The authored expectation is two cushions of about 5,808 cm² at a top of 50.3 cm.
2. **Controller import.** Root's `tools/unreal_import_controller_prop.py` imports the original (sha `c034a144…`) under `/Game/Sub01Home/Devices/Controller/V_c034a1444711` and writes `private-audit/native-controller-asset.json` (`sub01.native-controller-asset.v1`), with the baked shadow excluded. The adapter loads `physical_assembly.mesh` from that receipt, and refuses a missing receipt, a different source sha or a path containing "contact". The axis contract (UE = 100 × (x, z, y)) must be confirmed from the receipt's `original_source_transform`.
3. **Clip import.** Import `gaming-owner.glb` onto the existing owner USkeleton as `/Game/Sub01Hands/Play/SUB01_Gaming`. The import row must carry `role: Gaming`, `same_existing_skeleton: true` and `source_fbx_sha256: 84dfc60a…fc7f`.
4. **Sofa contact.** Play SUB01_Gaming at the chosen body offset on the measured seat. Dump the per-region gaps in the `unreal_audit_seat_contact.py` format, with ≥ 152 samples over 5.03 s, to `SOFA_CONTACT.json`. Measure the placement (`approach_cm`, `yaw_deg`, `body_offset_cm`, `body_yaw_deg`, `sofa_footprint_cm`) into `PLACEMENT.json`.
5. **Grip.** Run `python tools/fit_controller_grip.py fit --clip docs/proposed/controller-capture/gaming-owner.glb --source-fbx-sha256 84dfc60a… --out GRIP.json`. The evidence step refuses anything short of 152/152 grip frames.
6. **Evidence.** Run `python tools/unreal_controller_play_runtime.py evidence <project> GRIP.json SOFA_CONTACT.json PLACEMENT.json`. It is computed from the gates and refuses each failure.
7. **Config.** Run `python tools/unreal_controller_play_runtime.py config <project> IMPORT.json OUT.ini`. It writes `+ValidatedHandsPostures=Gaming` only with accepted evidence for this exact sofa report.
8. **Install.** Run `python tools/unreal_controller_play_runtime.py install <project>/Source/Sub01HomeLab`. It is additive, uses unique anchors, refuses missing anchors and refuses a reinstall. It coexists with the seat and life adapters in any order.

## 5. Native adapter behaviour

- **Plays only when all of these hold:**
  - live home is fresh, public and unblocked;
  - activity is `play_console` and node is `sofa`, with no route;
  - the capsule is within 12 cm and 5° of the measured approach;
  - `ControllerPlayReady()`, which means: evidence accepted (sofa revision, grip and seat gates, capsule clearance > 0), clip bound through `ValidatedHandsPostures` on the same skeleton, and controller mesh loaded.
- **Posture gate:** `SetHandsPosture(TEXT("Walk"))` must succeed first; it is never bypassed or widened. The clip then replaces the renderer's choice, like the seat and life adapters do.
- **Controller visibility:** visible only while playing, and has no collision. It is placed every tick at the RightHand socket (socket rotation, imported bone scale excluded) plus the solved offset.
- **What it never touches:** it does not set the actor location, add movement input or send Minecraft input. The existing TV input path is untouched.
- **Readiness logging:** readiness is logged as `SUB01_CONTROLLER_PLAY_READY ready=0|1 refusal=…`.

## What remains

- **Grip:** a grip that passes 152/152 frames. Option 1 holds palm contact in 129/152 frames, but the thumbs and index fingers never meet their gates. Root decides between:
  - option 3: accept about 0.62 cm of finger-skin compression, and relax or redefine the thumb and index gates;
  - option 2: a controller with grips about 22.9 cm across;
  - a different capture.
  Native play also needs the IK and the per-frame controller track baked into a derived clip.
- **Sofa:** the native sofa audit, the seated contact run and the body offset, all measured on the server.
- **Import:** the controller import and its axis receipt.
- **Visual review:** a first-person review against the SimbasJungles reference.
- **Minecraft:** a correlated Minecraft ACK from root's device side.

Nothing above is verified.
