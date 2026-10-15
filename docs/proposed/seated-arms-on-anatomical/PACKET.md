# Seated arms on the anatomical chair-lift base (SOURCE packet, `ready: false`)

This is a proposal. It is not verified and needs a native re-audit. Nothing is installed, and no readiness or pin is
written. The captures and the base clips are untouched; every output here is derived.

## Inputs

- **Base:** `docs/proposed/seat-pose-anatomical/chair-lift-proposal/`. Its packet is
  `docs/proposed/seat-pose-anatomical/PACKET.md` at bfe7dc8.
- **Chair transform:** the lifted chair, (200.0199556350708, −186.69002056121826, 63.1876777245) cm. Rotation
  (0, 0, 0, 1) and scale 0.6069 are unchanged.
- **Body placement:** offset from the audited transform (−3.875, +32.5).
- **Shas:** the real LINEA desk geometry, owner model and chair model shas are in `seated-arms.packet.json`.

## Method

`tools/solve_seated_typing_arm_ik.py --base-transitions`:
- For every frame of SitDown and GetUp, any arm skin vertex closer than 0.5 cm to a real LINEA part box has its wrist
  moved out of the part along the shortest way.
- The move is smooth in time and never below a frame's own need.
- The IK is non-stretch, with the elbow pole carried along and the captured hand attitude kept.
- The fingers are carried with the hand.
- The base's settled loop frames are protected and never move.

## Results (read back from the written GLBs)

| Clip | GLB sha256 | Arm vs desk, worst | Body vs complete chair | Main strong rule (gated frames) | Fingers vs base | Gates |
|---|---|---|---|---|---|---|
| SeatedIdle (base, unchanged) | da9ad30e… | ≥ 10 cm | +0.645 cm (f31) | pass | pass | pass |
| SitDown_seated | d242f87d… | +0.60 cm (f19); was −3.30 cm in the base | +0.499 cm (f41) | pass | pass | pass |
| GetUp_seated | 54594b29… | +7.15 cm (f46) | +0.405 cm (f25) | pass | pass | pass |

- **SitDown:** the right wrist moves by up to 6.05 cm over frames 0–44. The left arm is unchanged.
- **GetUp:** no wrist moves were needed. The GLB is re-encoded, but its arms are the base's.
- **Seams:** SitDown.last → SeatedIdle.first and SeatedIdle.last → GetUp.first both have a position Δ of 0. The
  velocity Δ at the hips is 0.69 and 0.73 cm/s; this is the loop's own step.

## Typing: BLOCKED

The base has no anatomical DeskTyping, SitToType or TypeToSit clips, so the ergonomic typing warm start cannot run yet.
The command for it is recorded in `seated-arms.packet.json` under `typing`.
