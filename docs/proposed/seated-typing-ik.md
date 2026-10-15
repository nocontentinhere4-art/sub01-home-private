# Proposed: seated typing whole-arm IK on the actual chair and the real LINEA140 desk

**Status: `ready: false`. Not native-verified. Not a receipt.**

The committed clips sit on the old seat base in `docs/proposed/seat-pose-fit/`. That base fails main's strong seat
rule on every frame. The rule is in origin/main `tools/validate_unreal_seat_contact.py` `validate()` at 9792a35: the
median gap must be at most the band's high edge, and at least 0.5 of the band must be covered. The failure is in
main's rule, not in this branch's `MIN_SUPPORT_VERTICES` rule. Measured on the DeskTyping base:

| region | band vertices | over-surface vertices |
|---|---|---|
| buttocks | 62–163 | ≥ 923 |
| left thigh | 272–836 | ≥ 1824 |

The measured chair's castors sit at 0.0 cm, which is 2.5 cm below the 2.5 cm floor support plane. The arm step is
written to warm-start from the corrected base in `docs/proposed/seat-pose-anatomical/` with that base's chair
transform. It has not been run on that base yet, because the base does not exist yet.

Tool: `tools/solve_seated_typing_arm_ik.py`. Outputs: `docs/proposed/seated-typing-ik/`. Tests:
`tests/test_solve_seated_typing_arm_ik.py`.

## Real geometry

**Desk**
- Source: root's LINEA140 source GLB, sha256 `99bdf3fd…`.
- Placement: root's own, from `prepare_real_linea140_placement.place_bytes`. Translation is (2.1, .025, −3.02) m and the
  scale is .82/.755.
- UE mapping: `real_linea_edge_clamp`, UE = 100·(2.1+Sx, −3.02+Sz, .025+Sy).
- Output: per-node AABBs in `real-linea140-geometry.json`.

| item | value |
|---|---|
| tabletop (node 44) | top 84.5, bottom 81.459 (3.041 cm thick), X 133.97..286.03, Y −337.30..−266.70 |
| centre | (210, −302) |
| front edge | Y −266.70 (+Y is the front) |
| overall size | 152.05 × 70.60 × 82.36 cm (the 84.86 cm maximum is the grommet rim) |
| knee bay | X 143.69..237.21, below the 78.09 cm front apron (matches root's record) |
| desk feet | on 2.5 cm |

Root's `real-linea140-guarded-placement` JSON gives the centre as Y −310. Root's executable script gives Y −302.
**Root must confirm which is correct.**

**Keyboard**
- It did not move. The home.js `furnished("keyboard", 2, .846, -2.94, .371)` matches the home source nodes 184–187 in
  root's record: X 181.45..218.55, Y −302.05..−285.95.
- The key top is at 87.39 cm.
- Its bottom is 84.6 cm against an 84.5 cm desk top. Root's device-foot check is still pending.

**Chair**
- The initial transform is root's measured one, [200.020, −186.690, 60.688].
- The complete chair is the owner source `web/room/chair_owner.glb`, sha256 `d27084af…`. It has arm pads (top at
  67.0 cm), a base, castors and a gas lift.
- The source is placed by the measured transform.
- Root's measured LOD0 shell lies on the source surface within 0.416 cm (tolerance 0.5 cm).

## Chair roll activity

- The chair rolls from its measured transform by (+3.875, −32.5, 0) cm to [203.895, −219.190, 60.688].
- The path is a quintic smootherstep, so velocity and acceleration are zero at both ends.
- Pull-in plays over SitToType: peak 51.0 cm/s and 130 cm/s². Push-back plays over TypeToSit: peak 65.5 cm/s and
  214 cm/s².
- The body rolls rigidly with the chair, so the seat geometry relative to the chair is unchanged and the feet scoot.
- Exact reversibility passes: the final transform is identical to the initial one and the path is retraced (deviation
  8.5e-14 cm).
- A scan of extra pull-in (0, −2.5, −5, −7.5 cm) chose 0.

Clearances along the 101-sample path and on every clip frame:

| check | result |
|---|---|
| complete chair vs desk | ≥ 20 cm everywhere |
| body vs complete chair | worst +0.48 cm, legs against the upholstery; fabric may compress to −2.5 cm |
| floor | −2.5 cm, constant along the path, so the floor gate is **false** |

## Gates per clip

| gate | DeskTyping (989 keys) | SitToType (37) | TypeToSit (29) |
|---|---|---|---|
| seat, main's strong rule | **FAIL** (all 5 regions) | **FAIL** | **FAIL** |
| seat, branch band/MIN_SUPPORT rule (solver frame and at the rolled chair) | pass | pass | pass |
| keys (≤ 0.2 cm gap, ≤ 0.1 cm penetration) | pass | pass (contact at the seam) | pass |
| `validate_unreal_contact_profile.validate()`, 301 rows at 3–8 s | **pass**: max gap 0.140 / 0.099 cm, penetration 0.043 cm | – | – |
| arm skin vs real desk, > 0 every frame | pass: forearm 0.52 cm (f424), fingers 0.50 cm (f887) | pass: fingers 0.55 cm | pass: fingers 0.67 cm |
| legs and torso vs desk | pass: legs 9.6 cm | pass | pass |
| fingers equal the capture on all frames (≤ 0.1°) | pass, 0.0002° | pass | pass |
| complete chair vs desk | pass | pass | pass |
| complete chair vs floor | **FAIL**, −2.5 cm | **FAIL** | **FAIL** |
| body vs complete chair | pass, 0.58 cm | pass, 0.50 cm | pass, 0.48 cm |

Soft targets (never gates):
- **Wrist.** The ranges are flexion/extension ±15° and deviation from −20° (ulnar) to +10° (radial). DeskTyping stays
  inside them on every frame, but it sits at the 15° extension limit. The transitions leave the range while the hands
  come off or go back to the lap (up to −50° extension).
- **Ergonomics: FAILED on the committed run.** The run had no ergonomic objective. The elbows are 97–116 cm high and
  the upper arm is 61–104° from vertical, so the arms are winged up. The swivel needed to keep the owner's bulky
  sleeves clear of an 84.5 cm desk from this low seat is 80–105°.
- **The fix is in the code but has not run yet.** The arm step now has an ergonomic objective: elbow 0–10 cm above the
  desk top (ANSI/HFES 100-2007) and upper arm within 20° of vertical (RULA score 1). Among the swivels that still clear
  the desk, it picks the one with the lowest cost. The reports now give elbow height, upper-arm angle and shoulder
  elevation per frame.

## Seams (world, read back)

| seam | max joint position Δ | max velocity Δ |
|---|---|---|
| SeatedIdle → SitToType | 3.44 cm (finger curls kept, hips 0) | 13.2 cm/s |
| SitToType → DeskTyping | 0.009 cm | 10.0 cm/s |
| DeskTyping → TypeToSit | 0.37 cm | 27.5 cm/s |
| TypeToSit → SeatedIdle | 3.44 cm | 14.5 cm/s |
| DeskTyping loop | 2.51 cm | 14.3 cm/s |

SitDown and GetUp are unchanged.

## Bounded run

- The full solve had a 1320 s cap.
- The DeskTyping stage finished and was committed as a checkpoint.
- The transitions ran with `--resume`, which checks the sha256 of the committed DeskTyping GLB.
- The CLI exits with code 3 whenever `ready` is false. The report is still written.

## Next step: warm start on the corrected base

```
python tools/solve_seated_typing_arm_ik.py \
    --base-dir docs/proposed/seat-pose-anatomical \
    --base-chair-offset DX,DY \
    --chair-translation X,Y,Z \
    [--keycaps keyboard-keycaps-world.json] \
    --max-seconds 1320
```

- `--base-chair-offset`: the base's solver-frame chair offset.
- `--chair-translation`: for example the proposed +2.5 cm lift.
- The keyboard IK targets, the chair and cushion, and every clearance are recomputed for the chair transform you give.

## Root must confirm

1. The desk centre: the code's Y −302 or the record's Y −310.
2. The floor under the chair: the castors are at 0.0 cm and the support plane is at 2.5 cm. The proposed lift is +2.5 cm.
3. The keyboard foot contact: its bottom is at 84.6 cm on an 84.5 cm desk.
4. The native chair base and castor actors, and a native swept check of the roll.
5. The corrected seat base and its chair offset for the warm start.
