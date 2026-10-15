# Seated base SOURCE packet: chair-lift candidate (SeatedIdle, SitDown, GetUp)

This packet is a proposal. It is not verified and needs a native re-audit before use.

- **Readiness:** `source_ready: false`, `native_ready: false`, `ready: false`. The only failing source check is SitDown's desk clearance (see below), which belongs to the arm step.
- **Nothing installed:** no installer, config, readiness write or importer pin is changed.
- **Chair lift:** accepted in principle by root for source and native review, but not enabled.
- **Originals untouched:** the raw captures (`web/room/mh_mx/*`) and the committed `docs/proposed/seat-pose-fit/*` are unchanged.

## Pinned inputs

- **Main validator:** `origin/main:tools/validate_unreal_seat_contact.py`, sha256 `dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f`. It is imported from the pinned bytes by `tools/recheck_seat_fit_main_rule.py`.
- **Owner model and skin:** `web/room/char_mixamo.glb`, sha256 `7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb`. The patch vertex sets come from `private-audit/seat-fit-source.npz`: the root plantar witness, and seat regions by the native rule.
- **Chair model:** `web/room/chair_owner.glb`, sha256 `d27084af80035c7ab278f90daf77a422fabe738095dad0b015a531f86249e2dc`. It reproduces the measured native shell (`ChairCollider` check).
- **Measured chair report:** `docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json`. Its sha256 is recorded in the report JSON.
- **Body placement:** offset from the audited transform (−3.875, +32.5) cm, the same as the seat-pose-fit actual-chair placement, yaw 180.

## Lifted chair transform (derived proposal, needs native chair review)

| | Translation (cm) | Rotation | Scale |
|---|---|---|---|
| Measured | (200.0199556350708, −186.69002056121826, 60.68757772445679) | (0, 0, 0, 1) | 0.6068757772445679 |
| **Proposed (arm step uses this)** | **(200.0199556350708, −186.69002056121826, 63.1876777245)** | (0, 0, 0, 1) | 0.6068757772445679 |

- The lift is +2.5001 cm Z, rigid, applied to the whole chair model.
- Caster bottoms move from 0.0 to 2.5001 cm, so the caster-to-floor gap goes from −2.5001 to 0.0 cm. The floor top stays at 2.5001 cm and the floor plane is not redefined.
- The cushion top rises by +2.5001 cm (51.4075 → 53.9076 cm).

## Clips (`docs/proposed/seat-pose-anatomical/chair-lift-proposal/`)

| Clip | GLB sha256 | Gated | Fail (main) | Anatomy (gated) | Complete chair | Desk |
|---|---|---|---|---|---|---|
| `SUB01_SeatedIdle.glb` | `da9ad30e691a9028b4ccce9f2438cffe2eae6f27ce386806d17b8dd3199b3ab4` | 126 | 0 | pass | +0.646 cm | clear |
| `SUB01_SitDown_seated.glb` | `ad79b820276014e7e49dcc7ad3d342111095bdbb54305a19ed4c2dc3f19a88ac` | 18 | 0 | pass | +0.526 cm | **fail:** right forearm and hand up to 3.299 cm inside the desk on 16 ungated frames (the captured arm; arm step) |
| `SUB01_GetUp_seated.glb` | `b5836fba3616237896cb59e8b80c593feabb42df942d8bd1a944766acece8e2f` | 17 | 0 | pass | +0.405 cm | clear |

Worst values per patch on the gated frames (min gap / max median / min coverage / min over-surface vertices; bands: seat −2.5..+0.5, sole 0..+1):

| Clip | buttocks | L thigh | R thigh | L sole | R sole |
|---|---|---|---|---|---|
| SeatedIdle | −1.97 / 0.238 / 0.563 / 670 | −2.25 / −0.504 / 0.744 / 1235 | −1.98 / 0.121 / 0.627 / 1580 | 0.05 / 0.228 / 1.0 / 1923 | 0.05 / 0.233 / 1.0 / 2248 |
| SitDown | −1.96 / 0.211 / 0.571 / 670 | −2.22 / −0.513 / 0.747 / 1241 | −1.96 / 0.091 / 0.636 / 1583 | 0.05 / 0.228 / 1.0 | 0.05 / 0.233 / 1.0 |
| GetUp | −1.95 / 0.229 / 0.563 / 670 | −2.22 / −0.504 / 0.744 / 1237 | −1.94 / 0.111 / 0.629 / 1582 | 0.05 / 0.228 / 1.0 | 0.05 / 0.233 / 1.0 |

**Binding constraints** (smallest margins):

- SeatedIdle: L thigh min gap 0.253 cm (f31), then buttocks median 0.262 cm (f49).
- SitDown: L thigh min gap 0.277 cm (f50).
- GetUp: buttocks median 0.271 cm (f9).

**Where the numbers come from:** the per-frame lowest, median, band and over-surface counts for every patch are in each `*.report.json` under `actual_chair.per_frame`. Main's verdict per clip is in `main-rule-chair-lift.json`. The measurement read-back reproduces the stored gaps to within 2e-6 cm.

## SeatedIdle derived edits (constant over the loop; the motion is the capture's)

| Parameter | Value |
|---|---|
| Pelvis posterior tilt (lateral axis, pivot Spine, Spine counter-rotated) | +32.63° |
| Root down / forward | 10.75 cm / 11.76 cm |
| L / R ankle forward | 5.50 / 3.80 cm |
| L / R ankle lateral | 2.36 / 1.13 cm |
| L / R hip swivel | −7.59° / +1.77° |
| Feet | flat, heel down (bind plantar plane, captured heading); toes at the bind local |

| Joint (local rotation vs capture) | Max ° | Mean ° | Frames |
|---|---|---|---|
| Hips | 32.63 | 32.63 | 126 |
| Spine | 32.63 | 32.63 | 126 |
| LeftUpLeg / RightUpLeg | 38.89 / 34.92 | 38.83 / 34.82 | 126 |
| LeftLeg / RightLeg | 16.91 / 24.82 | 16.83 / 24.68 | 126 |
| LeftFoot / RightFoot | 73.71 / 51.47 | 73.62 / 51.43 | 126 |
| LeftToeBase / RightToeBase | 1.55 / 0.74 | 1.45 / 0.63 | 126 |
| The other 55 joints (Spine1 and up, arms, fingers) | 0 | 0 | 0 |

- **Root translation:** at most 19.11 cm. The mean is (0.14, −8.49, +17.09) cm in glTF, which is 10.75 cm down and 11.76 cm forward, plus the pelvis rotation about the Spine pivot.
- **Upper body:** world rotation unchanged (at most 1e-5°). It translates by (0, −10.755, +11.762) cm in glTF.
- **Bone lengths and translations:** bone-length error 0.0 and no non-root translation edits.
- **Anatomical angles** (capture → edited):
  - pelvis tilt 6° → 38.4–39.1° (limit 0–45);
  - lumbar flexion 12° → 44.9° (limit 52);
  - hip flexion: L 73 → 35.4–36.3°, R 68 → 32.1–33.1°;
  - hip abduction 16.2–16.9° (L) and 14.9–15.5° (R) (limit 45);
  - hip rotation −4.8° (L) and −12.1° (R) (limit ±45);
  - knee flexion 94.1–94.4° (L) and 91.5–91.8° (R);
  - **ankle dorsiflexion: L −54 → 19.33–19.49°, R −32 → 19.32–19.50° (limit 20, not exceeded)**;
  - subtalar inversion 1.7–2.0° (L) and 0.0–0.2° (R);
  - MTP 0°.
- **Loop closure:** pose 0.006 cm, velocity 3.21 cm/s (passes).

**SitDown and GetUp** use the existing seam-blend mode into this loop, with windows restricted so that every gated frame is exactly the loop (SitDown frames 23–50, GetUp frames 16–37). As a result, their edits include the swap of the transition's captured upper body and arms for the loop's inside and after the window. The full per-joint table is in `seat-pose-anatomical.report.json`, under `candidates.chair_lift_proposal.clips.*.joint_edits_vs_capture`.

## Seam deltas (written, read-back clips)

| Pair | Position (hips / max joint) | Velocity Δ hips | Velocity Δ max joint | Angular Δ hips / max joint | Loop's own seam (reference) |
|---|---|---|---|---|---|
| SitDown.last → SeatedIdle.first | 0 / 0 cm, 1e-6° | 0.689 cm/s | 5.42 cm/s | 2.82 / 5.96 °/s | 0.69 cm/s, 5.48 cm/s, 2.82 / 5.96 °/s |
| SeatedIdle.last → GetUp.first | 0 / 0 cm, 1e-6° | 0.733 cm/s | 5.54 cm/s | 2.82 / 5.96 °/s | same |

## How the ankle was fixed

The bounded re-solve stopped at 20.01° dorsiflexion. Both `ankle_forward` parameters were then moved +0.4 cm, with the other parameters unchanged. The result was re-run with `--fixed` and re-verified on every frame: dorsiflexion is at most 19.50°, and main's rule still passes with a better seat margin (0.2528 cm, up from 0.2474). The limit was not loosened.

## For the arm step

- Use the GLBs above.
- Use the chair at the proposed transform `(200.0199556350708, -186.69002056121826, 63.1876777245)` cm, rotation identity, scale 0.6068757772445679.
- Place the body at an offset of (−3.875, +32.5) cm from the audited body transform `[203.9, -232.3, -0.6]`, i.e. body_cm `[200.025, -199.8, -0.6]`, yaw 180.
- Floor top: 2.5001 cm.
- Desk: centre Y −302, worktop 84.5 cm.
- Known failure to fix: SitDown's 16 ungated frames, where the right forearm and hand go up to 3.299 cm into the desk structure.

## Geometric diagnosis (`geometry-diagnosis.json`)

- **Measured lengths:** thigh (hip to knee) 36.3 / 35.9 cm, shin (knee to ankle) 39.8 / 40.3 cm, ankle above the sole 7.46 / 7.42 cm. With a flat foot and a vertical shin, the knee joint is therefore at most 2.50 + 7.44 + 39.7 = **49.6 cm** high.
- **Cushion:** the flat top is 50.4 cm (52.9 cm lifted), the maximum 51.4 cm (53.9 cm lifted), and the depth 47.7 cm.
- **Consequence:** the thigh cannot lie level on the cushion with the heels down. It slopes down 16.6–18.4° (measured chair) and 19.7–22.9° (lifted) to knees at about 46–47 cm. The base therefore sits forward, perched: the hip joints are about 8 cm forward of the cushion's front edge, the ischial and buttock skin is on the front of the flat top, and the posterior thighs are on the front waterfall.
- **Result:** main's median and coverage pass with this shape. No footrest is needed (root confirmed). The lift makes the thigh slope about 3° steeper but still passes.
