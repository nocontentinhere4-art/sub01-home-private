# Ergonomic layout refit: independent verification (source only, `ready: false`)

Verifier: `tools/verify_ergonomic_layout_refit.py` (independent of the layout solver). Proposal: `docs/proposed/ergonomic-layout-refit/ergonomic-layout-refit.proposal.json` (sha256 `8ff4cc903362c7d2b514005192061601b177229667f2e05a555197eb317fca00`, status `final_candidate`). Nothing native is verified; `ready` stays false.

## Verdicts

| Check | Result |
|---|---|
| 1_keyboard_supported | **FAIL** |
| 1_mouse_supported | **FAIL** |
| 2_chair_path_and_reversible | **PASS** |
| 3_body_all_clips | **PASS** |
| 4_continuity | **FAIL** |
| 5_ergonomics | **FAIL** |
| 0_desk_variant_items | **FAIL** |

## Layout under test

- Keyboard delta (UE cm): [8.0, 17.0, -0.1] (explicit UE delta (= proposed_three_m difference))
- Mouse delta (UE cm): [0.0, 11.848, -0.1] (explicit UE delta (= proposed_three_m difference))
- Chair start [200.02, -186.69, 63.1877], roll [3.875, -6.279, 0.0], pulled in [203.895, -192.969, 63.1877]
- Clips: SitDown_seated `docs/proposed/seated-arms-on-anatomical/SUB01_SitDown_seated.glb` (d242f87dc9fe…, BASELINE (not in the proposal)), SeatedIdle `docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SeatedIdle.glb` (da9ad30e691a…, BASELINE (not in the proposal)), SitToType_seated `docs/proposed/ergonomic-layout-refit/SUB01_SitToType_seated_refit.glb` (b47ac95e9e5e…, proposal), DeskTyping_seated `docs/proposed/ergonomic-layout-refit/SUB01_DeskTyping_seated_refit.glb` (d5a85367a6e4…, proposal), TypeToSit_seated `docs/proposed/ergonomic-layout-refit/SUB01_TypeToSit_seated_refit.glb` (896a6fc4c375…, proposal), GetUp_seated `docs/proposed/seated-arms-on-anatomical/SUB01_GetUp_seated.glb` (54594b2909fc…, BASELINE (not in the proposal))

## 1. Devices on the worktop

| Device | Bottom − top (cm) | Feet on flat top | Footprint (UE cm) | Margin to slab AABB | Colliding items | Pass |
|---|---|---|---|---|---|---|
| keyboard | 0.0 (original 6.6) | 86/102 | [[189.45, -285.0464], [226.55, -268.9536]] | -0.5464 | none | **FAIL** |
| mouse | 0.0 (original 6.6) | 894/930 | [[229.0, -289.602], [251.0, -268.702]] | -0.798 | none | **FAIL** |

Static envelope: with its feet on the top the keyboard passes the support/item checks up to 15.0 cm toward the body (1 cm steps).

Keyboard clearance to desk items (horizontal gap cm): monitor_frame 43.2036, monitor_stand 40.4536, monitor_root_envelope 40.4536, phone_root_envelope 39.55, clamp_lamp 32.522, grommet_node35 43.5757, mouse 2.45

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
| SitToType_seated | pass | 0.05 cm (f27) | 13.3632 | 6.4552 | 15.0 | **PASS** |
| DeskTyping_seated | pass | 0.05 cm (f660) | 12.6698 | 5.6655 | 15.0 | **PASS** |
| TypeToSit_seated | pass | 0.05 cm (f9) | 13.404 | 5.666 | 15.0 | **PASS** |
| GetUp_seated | pass | 0.001 cm (f52) | 15.0 | 9.4575 | 15.0 | **PASS** |

SitDown_seated: gate = declared support mask (docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_SitDown_seated.report.json main_rule.gated_frame_indices). Cross-check with this verifier's own settled gate (settled: Hips height within the SeatedIdle range +- 0.5 cm, 24 frames): failing [44] {'44': 'left_sole: gap, median 1.114 cm, 44% of the patch in contact'}; frames it adds: [44, 45, 46, 47, 48, 49]

GetUp_seated: gate = declared support mask (docs/proposed/seat-pose-anatomical/chair-lift-proposal/SUB01_GetUp_seated.report.json main_rule.gated_frame_indices). Cross-check with this verifier's own settled gate (settled: Hips height within the SeatedIdle range +- 0.5 cm, 22 frames): failing [21] {'21': 'buttocks: gap, median 0.652 cm, 41% of the patch in contact'}; frames it adds: [17, 18, 19, 20, 21]

Worst frames per segment (cm, frame, desk node):

- SitDown_seated: forearm 6.9915 f26 n44; hand 5.3428 f24 n44; fingers 2.8881 f23 n44
- SeatedIdle: all > 15 cm
- SitToType_seated: thigh 13.3632 f32 n32; knee_shin 13.566 f32 n32; forearm 8.7371 f25 n44; hand 6.4552 f15 n44; fingers 0.6942 f16 n44
- DeskTyping_seated: thigh 12.6698 f128 n32; knee_shin 12.8212 f128 n32; forearm 5.6655 f642 n44; hand 8.2906 f572 n44; fingers 4.5536 f746 n44
- TypeToSit_seated: thigh 13.404 f2 n32; knee_shin 13.6359 f2 n32; forearm 8.7902 f1 n44; hand 5.666 f10 n44; fingers 0.2747 f10 n44
- GetUp_seated: upper_arm 12.9063 f38 n44; forearm 10.3859 f44 n44; hand 9.4575 f48 n44; fingers 9.4238 f48 n44

Fingertip contact (DIAGNOSTIC ONLY; old finger rests, new hands pending):

- DeskTyping_seated left: over keys 989 frames, gap range [2.097, 7.9466]
- DeskTyping_seated right: over keys 607 frames, gap range [2.3058, 10.3131]

## 4. Continuity

| Seam | Pos Δ max (joint) | Hips Δ | Vel Δ max (joint) | Accel ratio vs capture (hips/L/R) | Abrupt |
|---|---|---|---|---|---|
| SitDown_seated.last → SeatedIdle.first | 0.0 (Hips) | 0.0 | 5.4194 (HeadTop_End) | 1.878/1.335/0.827 | no |
| SeatedIdle.last → SeatedIdle.first | 0.0058 (LeftForeArm) | 0.0058 | 5.4788 (HeadTop_End) | 1.881/1.124/0.629 | no |
| SeatedIdle.last → SitToType_seated.first | 0.0 (Hips) | 0.0 | 5.5766 (HeadTop_End) | 1.998/2.271/0.791 | no |
| SitToType_seated.last → DeskTyping_seated.first | 0.2392 (RightFoot) | 0.0287 | 5.3367 (RightHand) | 1.172/1.916/0.209 | no |
| DeskTyping_seated.last → DeskTyping_seated.first | 0.0261 (RightForeArm) | 0.0127 | 4.627 (RightForeArm) | 0.369/0.153/0.003 | no |
| DeskTyping_seated.last → TypeToSit_seated.first | 0.3527 (LeftLeg) | 0.0224 | 12.5971 (HeadTop_End) | 25.711/1.483/0.208 | no |
| TypeToSit_seated.last → SeatedIdle.first | 0.0 (Hips) | 0.0 | 5.4919 (HeadTop_End) | 34.426/3.397/1.133 | no |
| SeatedIdle.last → GetUp_seated.first | 0.0 (Hips) | 0.0 | 5.543 (HeadTop_End) | 1.998/1.508/0.607 | no |

Rule: position jump > 0.5 cm or velocity change > 30.0 cm/s on any body joint (fingers reported separately); accel_over_capture_peak: the one-frame seam acceleration of hips/hands exceeds the smaller capture peak of the two neighbours (chair frame).


Within-clip acceleration (chair frame, judged) vs the capture's own peak:

- SitDown_seated (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.053× of 525.2 cm/s² (1 fr over, peak f34; world+roll 1.053×), LeftHand 0.681× of 2346.9 cm/s² (0 fr over, peak f35; world+roll 0.681×), RightHand 0.599× of 1847.8 cm/s² (0 fr over, peak f18; world+roll 0.599×)
- SeatedIdle (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.144× of 11.0 cm/s² (1 fr over, peak f53; world+roll 1.144×), LeftHand 1.0× of 5.9 cm/s² (1 fr over, peak f53; world+roll 1.0×), RightHand 1.0× of 14.3 cm/s² (0 fr over, peak f40; world+roll 1.0×)
- SitToType_seated (chair roll peak 29.5 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.221× of 36.9 cm/s² (1 fr over, peak f26; world+roll 1.897×), LeftHand 0.376× of 2052.5 cm/s² (0 fr over, peak f10; world+roll 0.371×), RightHand 0.399× of 1536.2 cm/s² (0 fr over, peak f6; world+roll 0.402×)
- DeskTyping_seated (chair roll peak 0.0 cm/s², clip 60.0 fps, capture 30.0 fps): Hips 2.231× of 62.5 cm/s² (22 fr over, peak f934; world+roll 2.231×), LeftHand 0.468× of 150.7 cm/s² (0 fr over, peak f154; world+roll 0.468×), RightHand 2.576× of 1582.1 cm/s² (24 fr over, peak f150; world+roll 2.576×)
- TypeToSit_seated (chair roll peak 48.7 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 28.632× of 0.6 cm/s² (27 fr over, peak f5; world+roll 104.623×), LeftHand 0.733× of 799.8 cm/s² (0 fr over, peak f5; world+roll 0.716×), RightHand 1.059× of 1027.3 cm/s² (1 fr over, peak f5; world+roll 1.047×)
- GetUp_seated (chair roll peak 0.0 cm/s², clip 30.0 fps, capture 30.0 fps): Hips 1.344× of 662.7 cm/s² (1 fr over, peak f42; world+roll 1.344×), LeftHand 1.203× of 1691.0 cm/s² (1 fr over, peak f37; world+roll 1.203×), RightHand 1.188× of 1333.9 cm/s² (2 fr over, peak f36; world+roll 1.188×)

Verdict: **FAIL**

## 5. Ergonomics (DeskTyping, measured independently, total angles)

Targets: {'ergo_elbow_above_desk_cm': [0.0, 12.0], 'ergo_upper_arm_from_vertical_deg': 25.0, 'ergo_shoulder_elevation_vs_idle_deg': 5.0, 'ergo_wrist_flexion_deg': [-20.0, 20.0], 'ergo_wrist_deviation_deg': [-20.0, 10.0], 'ergo_frame_share': 0.95}

| Side | Elbow above top cm (min/med/max) | Upper arm ° | Shoulder elev. vs idle ° | Wrist flex ° | Wrist dev ° |
|---|---|---|---|---|---|
| left | [4.34, 6.34, 8.75] | [29.02, 39.03, 43.5] | [-11.47, -6.15, 1.94] | [-14.65, -5.24, 0.29] | [-12.24, -5.44, -1.58] |
| right | [5.67, 8.61, 22.32] | [31.72, 42.53, 77.41] | [-11.22, -2.56, 5.43] | [-37.15, 0.68, 27.49] | [-17.71, 1.41, 22.71] |

- left: share of frames meeting each target {'elbow_above_desk': 1.0, 'upper_arm': 0.0, 'shoulder_elevation': 1.0, 'wrist_flexion': 1.0, 'wrist_deviation': 1.0}; worst: elbow_highest 8.746  (f0), elbow_lowest 4.3364  (f640), upper_arm_max 43.5041  (f202), shoulder_shrug_max 1.9387  (f116), wrist_flexion_max 0.2888  (f476), wrist_extension_max -14.6521  (f562), wrist_radial_max -1.5758  (f980), wrist_ulnar_max -12.2409  (f610)
- right: share of frames meeting each target {'elbow_above_desk': 0.7058, 'upper_arm': 0.0, 'shoulder_elevation': 0.9757, 'wrist_flexion': 0.6673, 'wrist_deviation': 0.9252}; worst: elbow_highest 22.318  (f750), elbow_lowest 5.669  (f554), upper_arm_max 77.413  (f750), shoulder_shrug_max 5.4339  (f222), wrist_flexion_max 27.4866  (f732), wrist_extension_max -37.1493  (f755), wrist_radial_max 22.713  (f148), wrist_ulnar_max -17.712  (f766)

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

Elapsed 309.0 s. All checks: **FAIL**. `ready: false` (native unverified).
