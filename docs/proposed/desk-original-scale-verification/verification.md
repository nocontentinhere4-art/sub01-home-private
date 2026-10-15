# Ergonomic layout refit: independent verification (source only, `ready: false`)

Verifier: `tools/verify_ergonomic_layout_refit.py` (independent of the layout solver). Proposal: `docs/proposed/desk-original-scale/ergonomic-layout-refit.proposal.json` (sha256 `1567f1bfbaf84ac026ec78bc0672551e6194707df2961c1a2ccf9b95867fb6da`, status `final_candidate`). Nothing native is verified; `ready` stays false.

## Verdicts

| Check | Result |
|---|---|
| 1_keyboard_supported | **PASS** |
| 1_mouse_supported | **PASS** |
| 2_chair_path_and_reversible | **PASS** |
| 3_body_all_clips | **PASS** |
| 4_continuity | **FAIL** |
| 5_ergonomics | **FAIL** |
| 0_desk_variant_items | **FAIL** |

## Layout under test

- Keyboard delta (UE cm): [8.0, 14.202, -6.6] (explicit UE delta (= proposed_three_m difference))
- Mouse delta (UE cm): [0.0, 9.05, -6.6] (explicit UE delta (= proposed_three_m difference))
- Chair start [200.02, -186.69, 63.1877], roll [3.875, -13.577, 0.0], pulled in [203.895, -200.267, 63.1877]
- Clips: SitDown_seated `docs/proposed/seated-arms-on-anatomical/SUB01_SitDown_seated.glb` (d242f87dc9fe…, BASELINE (not in the proposal)), SeatedIdle `docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SeatedIdle.glb` (da9ad30e691a…, BASELINE (not in the proposal)), SitToType_seated `docs/proposed/desk-original-scale/chair-roll-7p702/SUB01_SitToType_seated_refit.glb` (628f3725c41b…, proposal), DeskTyping_seated `docs/proposed/desk-original-scale/chair-roll-7p702/SUB01_DeskTyping_seated_refit.glb` (38fb1ef82c22…, proposal), TypeToSit_seated `docs/proposed/desk-original-scale/chair-roll-7p702/SUB01_TypeToSit_seated_refit.glb` (4bb4b220cb90…, proposal), GetUp_seated `docs/proposed/seated-arms-on-anatomical/SUB01_GetUp_seated.glb` (54594b2909fc…, BASELINE (not in the proposal))

## 1. Devices on the worktop

| Device | Bottom − top (cm) | Feet on flat top | Footprint (UE cm) | Margin to slab AABB | Colliding items | Pass |
|---|---|---|---|---|---|---|
| keyboard | 0.0 (original 6.6) | 102/102 | [[189.45, -287.8444], [226.55, -271.7516]] | 2.2516 | none | **PASS** |
| mouse | 0.0 (original 6.6) | 930/930 | [[229.0, -292.4], [251.0, -271.5]] | 2.0 | none | **PASS** |

Static envelope: with its feet on the top the keyboard passes the support/item checks up to 15.0 cm toward the body (1 cm steps).

Keyboard clearance to desk items (horizontal gap cm): monitor_frame 38.4056, monitor_stand 35.6556, monitor_root_envelope 37.6556, phone_root_envelope 39.55, clamp_lamp 27.83, grommet_node35 41.2656, mouse 2.45

Monitor provenance: web/house/home.js @ d03e673 (sha256 881340cfc23db38a9747b94bd23a873e7c6e30ca25cc739935eaea7ddcc228a1); docs/proposed/monitor-support-fix-20261015.json @ 9e720c6 (sha256 7ed7b57f87add30de4b90f288cbd7248d946f8fc169b1d2100b9076396e1a326): +2.5000 cm (stand bottom 82 -> top 84.5), screen centre z 118.5.

## 2. Chair (complete source chair, every triangle sampled at 1 cm)

- Native shell on source surface: max 0.4162 cm (tol 0.5)
- Worst desk clearance along the roll: 20.0 cm at offset [0.0, 0.0, 0.0] (None vs None)
- Floor gap range: [0.0001, 0.0001] cm; reversibility: **PASS** (push-back retraces pull-in within None cm)
- Verdict: **PASS**

## 3. Body, every frame

| Clip | Seat (main rule) | Soles lowest − floor | Legs vs desk min | Arms vs desk min (no fingers) | Torso | Pass |
|---|---|---|---|---|---|---|
| SitDown_seated | pass | 0.001 cm (f17) | 15.0 | 5.3428 | 15.0 | **PASS** |
| SeatedIdle | pass | 0.05 cm (f64) | 15.0 | 15.0 | 15.0 | **PASS** |
| SitToType_seated | pass | 0.05 cm (f27) | 10.2321 | 2.1279 | 15.0 | **PASS** |
| DeskTyping_seated | pass | 0.05 cm (f660) | 9.4065 | 0.2197 | 15.0 | **PASS** |
| TypeToSit_seated | pass | 0.05 cm (f9) | 10.2844 | 0.6 | 15.0 | **PASS** |
| GetUp_seated | pass | 0.001 cm (f52) | 15.0 | 9.4575 | 15.0 | **PASS** |

SitDown_seated: gate = declared support mask (docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SitDown_seated.report.json main_rule.gated_frame_indices). Cross-check with this verifier's own settled gate (settled: Hips height within the SeatedIdle range +- 0.5 cm, 24 frames): failing [44] {'44': 'left_sole: gap, median 1.114 cm, 44% of the patch in contact'}; frames it adds: [44, 45, 46, 47, 48, 49]

GetUp_seated: gate = declared support mask (docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_GetUp_seated.report.json main_rule.gated_frame_indices). Cross-check with this verifier's own settled gate (settled: Hips height within the SeatedIdle range +- 0.5 cm, 22 frames): failing [21] {'21': 'buttocks: gap, median 0.652 cm, 41% of the patch in contact'}; frames it adds: [17, 18, 19, 20, 21]

Worst frames per segment (cm, frame, desk node):

- SitDown_seated: forearm 6.9915 f26 n44; hand 5.3428 f24 n44; fingers 2.8881 f23 n44
- SeatedIdle: all > 15 cm
- SitToType_seated: thigh 10.2321 f32 n32; knee_shin 11.3834 f33 n32; forearm 3.2232 f36 n44; hand 2.1279 f26 n44; fingers -1.398 f16 n44
- DeskTyping_seated: thigh 9.4065 f130 n32; knee_shin 10.5945 f129 n32; upper_arm 13.818 f800 n44; forearm 0.2197 f944 n44; hand 1.8119 f608 n44; fingers -1.4 f472 n44
- TypeToSit_seated: thigh 10.2844 f2 n32; knee_shin 11.3634 f1 n32; forearm 2.9852 f1 n44; hand 0.6 f11 n44; fingers -1.3998 f8 n44
- GetUp_seated: upper_arm 12.9063 f38 n44; forearm 10.3859 f44 n44; hand 9.4575 f48 n44; fingers 9.4238 f48 n44

Fingertip contact (DIAGNOSTIC ONLY; old finger rests, new hands pending):

- DeskTyping_seated left: over keys 989 frames, gap range [-4.5304, 0.7599]
- DeskTyping_seated right: over keys 607 frames, gap range [-3.8269, 3.244]

## 4. Continuity

| Seam | Pos Δ max (joint) | Hips Δ | Vel Δ max (joint) | Accel ratio vs capture (hips/L/R) | Abrupt |
|---|---|---|---|---|---|
| SitDown_seated.last → SeatedIdle.first | 0.0 (Hips) | 0.0 | 5.4194 (HeadTop_End) | 1.878/1.335/0.827 | no |
| SeatedIdle.last → SeatedIdle.first | 0.0058 (LeftForeArm) | 0.0058 | 5.4788 (HeadTop_End) | 1.881/1.124/0.629 | no |
| SeatedIdle.last → SitToType_seated.first | 0.0 (Hips) | 0.0 | 5.6181 (HeadTop_End) | 1.998/2.173/0.742 | no |
| SitToType_seated.last → DeskTyping_seated.first | 0.2392 (RightFoot) | 0.0287 | 5.2485 (RightHand) | 1.172/1.922/0.207 | no |
| DeskTyping_seated.last → DeskTyping_seated.first | 0.0261 (RightForeArm) | 0.0127 | 4.5915 (LeftArm) | 0.369/0.154/0.003 | no |
| DeskTyping_seated.last → TypeToSit_seated.first | 0.3527 (LeftLeg) | 0.0224 | 12.5073 (HeadTop_End) | 25.711/1.467/0.212 | no |
| TypeToSit_seated.last → SeatedIdle.first | 0.0 (Hips) | 0.0 | 5.581 (HeadTop_End) | 34.426/3.085/0.96 | no |
| SeatedIdle.last → GetUp_seated.first | 0.0 (Hips) | 0.0 | 5.543 (HeadTop_End) | 1.998/1.508/0.607 | no |

Rule: position jump > 0.5 cm or velocity change > 30.0 cm/s on any body joint (fingers reported separately); accel_over_capture_peak: the one-frame seam acceleration of hips/hands exceeds the smaller capture peak of the two neighbours (chair frame).


Within-clip acceleration (chair frame, judged) vs the capture's own peak:

- SitDown_seated (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.053× of 525.2 cm/s² (1 fr over, peak f34; world+roll 1.053×), LeftHand 0.681× of 2346.9 cm/s² (0 fr over, peak f35; world+roll 0.681×), RightHand 0.599× of 1847.8 cm/s² (0 fr over, peak f18; world+roll 0.599×)
- SeatedIdle (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.144× of 11.0 cm/s² (1 fr over, peak f53; world+roll 1.144×), LeftHand 1.0× of 5.9 cm/s² (1 fr over, peak f53; world+roll 1.0×), RightHand 1.0× of 14.3 cm/s² (0 fr over, peak f40; world+roll 1.0×)
- SitToType_seated (chair roll peak 56.4 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.221× of 36.9 cm/s² (1 fr over, peak f26; world+roll 2.618×), LeftHand 0.362× of 2052.5 cm/s² (0 fr over, peak f10; world+roll 0.355×), RightHand 0.385× of 1536.2 cm/s² (0 fr over, peak f6; world+roll 0.396×)
- DeskTyping_seated (chair roll peak 0.0 cm/s², clip 60.0 fps, capture 30.0 fps): Hips 2.231× of 62.5 cm/s² (22 fr over, peak f934; world+roll 2.231×), LeftHand 0.467× of 150.7 cm/s² (0 fr over, peak f154; world+roll 0.467×), RightHand 2.579× of 1582.1 cm/s² (24 fr over, peak f150; world+roll 2.579×)
- TypeToSit_seated (chair roll peak 93.2 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 28.632× of 0.6 cm/s² (27 fr over, peak f5; world+roll 181.083×), LeftHand 0.479× of 799.8 cm/s² (0 fr over, peak f5; world+roll 0.512×), RightHand 0.774× of 1027.3 cm/s² (0 fr over, peak f5; world+roll 0.77×)
- GetUp_seated (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.344× of 662.7 cm/s² (1 fr over, peak f42; world+roll 1.344×), LeftHand 1.203× of 1691.0 cm/s² (1 fr over, peak f37; world+roll 1.203×), RightHand 1.188× of 1333.9 cm/s² (2 fr over, peak f36; world+roll 1.188×)

Verdict: **FAIL**

## 5. Ergonomics (DeskTyping, measured independently, total angles)

Targets: {'ergo_elbow_above_desk_cm': [0.0, 12.0], 'ergo_upper_arm_from_vertical_deg': 25.0, 'ergo_shoulder_elevation_vs_idle_deg': 5.0, 'ergo_wrist_flexion_deg': [-20.0, 20.0], 'ergo_wrist_deviation_deg': [-20.0, 10.0], 'ergo_frame_share': 0.95}

| Side | Elbow above top cm (min/med/max) | Upper arm ° | Shoulder elev. vs idle ° | Wrist flex ° | Wrist dev ° |
|---|---|---|---|---|---|
| left | [1.82, 3.94, 7.45] | [16.88, 30.55, 36.34] | [-11.47, -6.15, 1.94] | [-21.3, -13.52, -9.43] | [-4.15, -2.8, -0.43] |
| right | [3.14, 6.68, 13.48] | [19.73, 34.63, 51.52] | [-11.22, -2.56, 5.43] | [-33.88, -8.43, 23.85] | [-12.53, 1.51, 21.2] |

- left: share of frames meeting each target {'elbow_above_desk': 1.0, 'upper_arm': 0.1628, 'shoulder_elevation': 1.0, 'wrist_flexion': 0.9889, 'wrist_deviation': 1.0}; worst: elbow_highest 7.4522  (f0), elbow_lowest 1.8214  (f656), upper_arm_max 36.3381  (f188), shoulder_shrug_max 1.9387  (f116), wrist_flexion_max -9.4295  (f760), wrist_extension_max -21.3032  (f188), wrist_radial_max -0.4336  (f966), wrist_ulnar_max -4.15  (f163)
- right: share of frames meeting each target {'elbow_above_desk': 0.9899, 'upper_arm': 0.0081, 'shoulder_elevation': 0.9757, 'wrist_flexion': 0.9221, 'wrist_deviation': 0.7048}; worst: elbow_highest 13.4793  (f943), elbow_lowest 3.1413  (f624), upper_arm_max 51.5179  (f943), shoulder_shrug_max 5.4339  (f222), wrist_flexion_max 23.8474  (f749), wrist_extension_max -33.8827  (f797), wrist_radial_max 21.201  (f744), wrist_ulnar_max -12.5297  (f160)

Verdict: **FAIL**

## Geometry used (origin/main bytes)

- ref `origin/main` @ `7cf5eec`
- LINEA140 `web/house/assets/real-linea140/originalsource.glb` sha256 `99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d`; placement `tools/prepare_real_linea140_placement.py` sha256 `a857a14fe7a77b742634eb7b37836b9a535a6a713c9d52afd133c04f00fbff76` @ b17952c: scale 1.0, translation [2.1, 0.025, -3.02] m; top 78.0 cm, floor 2.5 cm
- placement: `tools/prepare_real_linea140_placement.py` sha256 `a857a14fe7a77b742634eb7b37836b9a535a6a713c9d52afd133c04f00fbff76` @ b17952c
- home_js: `web/house/home.js` sha256 `881340cfc23db38a9747b94bd23a873e7c6e30ca25cc739935eaea7ddcc228a1` @ d03e673
- monitor_fix: `docs/proposed/monitor-support-fix-20261015.json` sha256 `7ed7b57f87add30de4b90f288cbd7248d946f8fc169b1d2100b9076396e1a326` @ 9e720c6
- lamp_mount: `docs/proposed/real-linea-grommet-lamp-mount-20261014.json` sha256 `e0a0aca1aee1f277548a9394ad1f76c00f281634879a502cd1bde176e49a350f` @ abe17df
- linea_record: `docs/proposed/real-linea140-guarded-placement-20261014.json` sha256 `c0425e20051b024812c75218deed43c719a3c621f8a624a736f577eb88d60b99` @ bb24ae5
- pinned `web/house/assets/real-linea140/originalsource.glb` sha256 `99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d`
- pinned `web/room/chair_owner.glb` sha256 `d27084af80035c7ab278f90daf77a422fabe738095dad0b015a531f86249e2dc`
- pinned `web/house/assets/keyboard/keyboard.glb` sha256 `86989af770a2caa655680bdb7f0a9bbc13c417795ab8c9c734d66fcc44b89fdf`
- pinned `web/room/mouse.glb` sha256 `ad9ee242415eb5de55781f8bf7befb70dcbe9dba03d1ccb587a58b5e6cd1fcec`
- pinned `tools/validate_unreal_seat_contact.py` sha256 `dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f`
- chair report `docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json` sha256 `84b976f967511cb06ea526c7ed21ea143d7a1ab8438133213035301243e7a8e8`
- seat-fit source npz sha256 `8a14f32ac1aea622f9a8b20fbe284d694d7d873ed16bb940792ba481dca1e9a4`; owner skin (fit_seat_pelvis_pitch.owner_skin, every 2th vertex: 124576 vertices), segments by dominant joint; desk parts as conservative node AABBs

Elapsed 175.8 s. All checks: **FAIL**. `ready: false` (native unverified).
