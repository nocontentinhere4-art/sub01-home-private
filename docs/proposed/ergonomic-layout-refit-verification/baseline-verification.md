# Ergonomic layout refit: independent verification (source only, `ready: false`)

Verifier: `tools/verify_ergonomic_layout_refit.py` (independent of the layout solver). Proposal: `None` (sha256 `None`, status `baseline`). Nothing native is verified; `ready` stays false.

## Verdicts

| Check | Result |
|---|---|
| 1_keyboard_supported | **FAIL** |
| 1_mouse_supported | **FAIL** |
| 2_chair_path_and_reversible | **PASS** |
| 3_body_all_clips | **PASS** |
| 4_continuity | **FAIL** |
| 5_ergonomics | **FAIL** |

## Layout under test

- Keyboard delta (UE cm): [0.0, 0.0, 0.0] (home.js)
- Mouse delta (UE cm): [0.0, 0.0, 0.0] (home.js)
- Chair start [200.02, -186.69, 63.1877], roll [3.875, -21.279, 0.0], pulled in [203.895, -207.969, 63.1877]
- Clips: SitDown_seated `docs/proposed/seated-arms-on-anatomical/SUB01_SitDown_seated.glb` (d242f87dc9fe…, baseline), SeatedIdle `docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SeatedIdle.glb` (da9ad30e691a…, baseline), SitToType_seated `docs/proposed/seated-arms-on-anatomical/SUB01_SitToType_seated.glb` (a141cae85439…, baseline), DeskTyping_seated `docs/proposed/seated-arms-on-anatomical/SUB01_DeskTyping_seated.glb` (26b3a8e32425…, baseline), TypeToSit_seated `docs/proposed/seated-arms-on-anatomical/SUB01_TypeToSit_seated.glb` (7e3fbadf363a…, baseline), GetUp_seated `docs/proposed/seated-arms-on-anatomical/SUB01_GetUp_seated.glb` (54594b2909fc…, baseline)

## 1. Devices on the worktop

| Device | Bottom − top (cm) | Feet on flat top | Footprint (UE cm) | Margin to slab AABB | Colliding items | Pass |
|---|---|---|---|---|---|---|
| keyboard | 0.1 (original 0.1) | 102/102 | [[181.45, -302.0464], [218.55, -285.9536]] | 19.2516 | none | **FAIL** |
| mouse | 0.1 (original 0.1) | 930/930 | [[229.0, -301.45], [251.0, -280.55]] | 13.848 | none | **FAIL** |

Keyboard clearance to desk items (horizontal gap cm): monitor_frame 26.2036, monitor_stand 23.4536, monitor_root_envelope 23.4536, phone_root_envelope 47.55, clamp_lamp 15.522, grommet_node35 28.9, mouse 10.45

Monitor provenance: web/house/home.js @ d03e673 (sha256 881340cfc23db38a9747b94bd23a873e7c6e30ca25cc739935eaea7ddcc228a1); docs/proposed/monitor-support-fix-20261015.json @ 9e720c6 (sha256 7ed7b57f87add30de4b90f288cbd7248d946f8fc169b1d2100b9076396e1a326): +2.5000 cm (stand bottom 82 -> top 84.5), screen centre z 118.5.

## 2. Chair (complete source chair, every triangle sampled at 1 cm)

- Native shell on source surface: max 0.4162 cm (tol 0.5)
- Worst desk clearance along the roll: 20.0 cm at offset [0.0, 0.0, 0.0] (None vs None)
- Floor gap range: [0.0001, 0.0001] cm; reversibility: **PASS** (push-back retraces pull-in within None cm)
- Verdict: **PASS**

## 3. Body, every frame

| Clip | Seat (main rule) | Soles lowest − floor | Legs vs desk min | Arms vs desk min (no fingers) | Torso | Pass |
|---|---|---|---|---|---|---|
| SitDown_seated | pass | 0.001 cm (f17) | 15.0 | 0.6048 | 15.0 | **PASS** |
| SeatedIdle | pass | 0.05 cm (f64) | 15.0 | 15.0 | 15.0 | **PASS** |
| SitToType_seated | pass | 0.05 cm (f27) | 12.5125 | 0.6295 | 15.0 | **PASS** |
| DeskTyping_seated | pass | 0.05 cm (f660) | 11.7374 | 0.5073 | 15.0 | **PASS** |
| TypeToSit_seated | pass | 0.05 cm (f9) | 12.4752 | 0.5085 | 15.0 | **PASS** |
| GetUp_seated | pass | 0.001 cm (f52) | 15.0 | 7.1537 | 11.9423 | **PASS** |

SitDown_seated: gate = declared support mask (docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SitDown_seated.report.json main_rule.gated_frame_indices). Cross-check with this verifier's own settled gate (settled: Hips height within the SeatedIdle range +- 0.5 cm, 24 frames): failing [44] {'44': 'left_sole: gap, median 1.114 cm, 44% of the patch in contact'}; frames it adds: [44, 45, 46, 47, 48, 49]

GetUp_seated: gate = declared support mask (docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_GetUp_seated.report.json main_rule.gated_frame_indices). Cross-check with this verifier's own settled gate (settled: Hips height within the SeatedIdle range +- 0.5 cm, 22 frames): failing [21] {'21': 'buttocks: gap, median 0.652 cm, 41% of the patch in contact'}; frames it adds: [17, 18, 19, 20, 21]

Worst frames per segment (cm, frame, desk node):

- SitDown_seated: upper_arm 14.8699 f30 n44; forearm 1.05 f26 n44; hand 0.6048 f19 n44; fingers 0.8671 f20 n44
- SeatedIdle: all > 15 cm
- SitToType_seated: thigh 12.5125 f30 n32; knee_shin 14.9422 f31 n32; upper_arm 5.1268 f31 n44; forearm 0.6295 f36 n44; hand 3.4821 f27 n44; fingers 0.5078 f5 n44
- DeskTyping_seated: thigh 11.7374 f134 n32; knee_shin 14.5258 f130 n32; upper_arm 1.6027 f925 n44; forearm 0.5073 f963 n44; hand 2.712 f408 n44; fingers 0.7054 f408 n44
- TypeToSit_seated: thigh 12.4752 f8 n32; knee_shin 14.862 f7 n32; upper_arm 4.7511 f6 n44; forearm 0.5085 f1 n44; hand 3.3361 f19 n44; fingers 0.596 f23 n44
- GetUp_seated: shoulder 13.4254 f34 n44; upper_arm 9.9338 f39 n44; forearm 7.1537 f46 n44; hand 7.2473 f48 n44; fingers 8.5393 f50 n44

Fingertip contact (DIAGNOSTIC ONLY; old finger rests, new hands pending):

- DeskTyping_seated left: over keys 989 frames, gap range [0.0251, 0.1595]
- DeskTyping_seated right: over keys 592 frames, gap range [0.0143, 1.7304]

## 4. Continuity

| Seam | Pos Δ max (joint) | Hips Δ | Vel Δ max (joint) | Accel ratio vs capture (hips/L/R) | Abrupt |
|---|---|---|---|---|---|
| SitDown_seated.last → SeatedIdle.first | 0.0 (Hips) | 0.0 | 5.4194 (HeadTop_End) | 1.878/1.335/0.827 | no |
| SeatedIdle.last → SeatedIdle.first | 0.0058 (LeftForeArm) | 0.0058 | 5.4788 (HeadTop_End) | 1.881/1.124/0.629 | no |
| SeatedIdle.last → SitToType_seated.first | 0.0 (Hips) | 0.0 | 5.6644 (LeftHand) | 1.998/28.411/9.751 | no |
| SitToType_seated.last → DeskTyping_seated.first | 0.2392 (RightFoot) | 0.0287 | 10.1868 (RightForeArm) | 1.172/2.163/0.385 | no |
| DeskTyping_seated.last → DeskTyping_seated.first | 0.0188 (RightForeArm) | 0.0127 | 4.5915 (LeftArm) | 0.369/1.171/0.031 | no |
| DeskTyping_seated.last → TypeToSit_seated.first | 0.3527 (LeftLeg) | 0.0224 | 17.3574 (LeftForeArm) | 25.711/1.922/0.164 | no |
| TypeToSit_seated.last → SeatedIdle.first | 0.0 (Hips) | 0.0 | 7.2424 (LeftHand) | 34.426/36.261/7.46 | no |
| SeatedIdle.last → GetUp_seated.first | 0.0 (Hips) | 0.0 | 5.543 (HeadTop_End) | 1.998/1.508/0.607 | no |

Rule: position jump > 0.5 cm or velocity change > 30.0 cm/s on any body joint (fingers reported separately); accel_over_capture_peak: the one-frame seam acceleration of hips/hands exceeds the smaller capture peak of the two neighbours (chair frame).


Within-clip acceleration (chair frame, judged) vs the capture's own peak:

- SitDown_seated (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.053× of 525.2 cm/s² (1 fr over, peak f34; world+roll 1.053×), LeftHand 0.681× of 2346.9 cm/s² (0 fr over, peak f35; world+roll 0.681×), RightHand 0.599× of 1847.8 cm/s² (0 fr over, peak f18; world+roll 0.599×)
- SeatedIdle (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.144× of 11.0 cm/s² (1 fr over, peak f53; world+roll 1.144×), LeftHand 1.0× of 5.9 cm/s² (1 fr over, peak f53; world+roll 1.0×), RightHand 1.0× of 14.3 cm/s² (0 fr over, peak f40; world+roll 1.0×)
- SitToType_seated (chair roll peak 86.3 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.221× of 36.9 cm/s² (1 fr over, peak f26; world+roll 3.384×), LeftHand 4.534× of 2052.5 cm/s² (13 fr over, peak f24; world+roll 4.541×), RightHand 3.005× of 1536.2 cm/s² (11 fr over, peak f8; world+roll 3.024×)
- DeskTyping_seated (chair roll peak 0.0 cm/s², clip 60.0 fps, capture 30.0 fps): Hips 2.231× of 62.5 cm/s² (22 fr over, peak f934; world+roll 2.231×), LeftHand 49.188× of 150.7 cm/s² (67 fr over, peak f926; world+roll 49.188×), RightHand 8.419× of 1582.1 cm/s² (76 fr over, peak f394; world+roll 8.419×)
- TypeToSit_seated (chair roll peak 142.8 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 28.632× of 0.6 cm/s² (27 fr over, peak f5; world+roll 264.778×), LeftHand 4.332× of 799.8 cm/s² (16 fr over, peak f22; world+roll 4.282×), RightHand 3.851× of 1027.3 cm/s² (15 fr over, peak f5; world+roll 3.983×)
- GetUp_seated (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.344× of 662.7 cm/s² (1 fr over, peak f42; world+roll 1.344×), LeftHand 1.203× of 1691.0 cm/s² (1 fr over, peak f37; world+roll 1.203×), RightHand 1.188× of 1333.9 cm/s² (2 fr over, peak f36; world+roll 1.188×)

Verdict: **FAIL**

## 5. Ergonomics (DeskTyping, measured independently, total angles)

Targets: {'ergo_elbow_above_desk_cm': [0.0, 12.0], 'ergo_upper_arm_from_vertical_deg': 25.0, 'ergo_shoulder_elevation_vs_idle_deg': 5.0, 'ergo_wrist_flexion_deg': [-20.0, 20.0], 'ergo_wrist_deviation_deg': [-20.0, 10.0], 'ergo_frame_share': 0.95}

| Side | Elbow above top cm (min/med/max) | Upper arm ° | Shoulder elev. vs idle ° | Wrist flex ° | Wrist dev ° |
|---|---|---|---|---|---|
| left | [12.7, 14.36, 16.5] | [65.82, 75.2, 77.27] | [-15.76, -6.21, 1.94] | [-12.08, -1.66, 2.67] | [8.08, 17.23, 18.54] |
| right | [10.85, 14.47, 23.94] | [61.27, 71.84, 94.3] | [-11.22, -2.56, 5.43] | [-15.65, -0.37, 22.25] | [-5.66, 18.8, 26.8] |

- left: share of frames meeting each target {'elbow_above_desk': 0.0, 'upper_arm': 0.0, 'shoulder_elevation': 1.0, 'wrist_flexion': 1.0, 'wrist_deviation': 0.095}; worst: elbow_highest 16.4979  (f0), elbow_lowest 12.6967  (f925), upper_arm_max 77.2712  (f911), shoulder_shrug_max 1.9387  (f116), wrist_flexion_max 2.6654  (f963), wrist_extension_max -12.078  (f610), wrist_radial_max 18.5375  (f969), wrist_ulnar_max 8.0847  (f610)
- right: share of frames meeting each target {'elbow_above_desk': 0.0586, 'upper_arm': 0.0, 'shoulder_elevation': 0.9757, 'wrist_flexion': 0.9909, 'wrist_deviation': 0.3134}; worst: elbow_highest 23.9365  (f558), elbow_lowest 10.8511  (f4), upper_arm_max 94.2993  (f558), shoulder_shrug_max 5.4339  (f222), wrist_flexion_max 22.2478  (f422), wrist_extension_max -15.6522  (f586), wrist_radial_max 26.7951  (f762), wrist_ulnar_max -5.6626  (f58)

Verdict: **FAIL**

## Geometry used (origin/main bytes)

- ref `origin/main` @ `6aba6d4`
- LINEA140 `web/house/assets/real-linea140/originalsource.glb` sha256 `99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d`; placement `tools/prepare_real_linea140_placement.py` sha256 `a857a14fe7a77b742634eb7b37836b9a535a6a713c9d52afd133c04f00fbff76` @ b17952c: scale 1.086093, translation [2.1, 0.025, -3.02] m; top 84.5 cm, floor 2.5 cm
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

Elapsed 266.1 s. All checks: **FAIL**. `ready: false` (native unverified).
