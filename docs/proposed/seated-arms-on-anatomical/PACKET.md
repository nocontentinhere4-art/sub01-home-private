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

## Typing: bounded run, partial (`ready: false`)

The run used the base's DeskTyping, SitToType and TypeToSit clips (8bc5c2c / 136195b), the lifted chair and
`--arms-only`. Only the six arm bones may change; the pelvis, spine, legs and fingers are gated to be identical to the
base.

- **Chair roll:** (3.875, −21.279) cm. The base moved the upper body 11.221 cm toward the desk (the Spine2 mean in
  DeskTyping, 3–8 s). The chair is therefore pulled in 11.221 cm less, which keeps the upper-body-to-keyboard
  relation that the contact pipeline was validated on.
- **Where it stopped:** after the DeskTyping stage. It hit the 1320 s bound (elapsed 1985 s; the bound is checked
  between stages). SitToType and TypeToSit were not written, so `seated-typing-ik.proposal.json` holds
  `partial.stage_reached` and the blocker.

DeskTyping, 989 keys, `SUB01_DeskTyping_seated.glb` sha256 `7d1c205c…`:

| Gate | Result |
|---|---|
| Seat (main's strong rule, every frame) | **pass** |
| Lower body and pelvis vs base | **pass**: 0 cm, 0° |
| Fingers vs base | **pass**: 0° |
| Complete chair (floor, desk, body) | **pass**: body margin +0.279 cm |
| Left arm vs desk | **pass**: forearm 0.50 cm (f272) |
| Right arm vs desk | **FAIL**: forearm −0.020 cm (f477) |
| Key contact (left / right) | **FAIL**: right gap up to 8.7 cm (f536), penetration −0.96 cm (f760); left gap up to 0.37 cm |
| `validate_unreal_contact_profile.validate()`, 301 rows | **FAIL**: fingertips hover over 2 mm |
| Ergonomics (soft) | **FAIL**: elbows 96.7–105.6 cm, upper arm 63–88° from vertical, shoulder elevation as captured (−22 to −5°) |

**Blocker.** On this base the contact solve does not converge on the right hand. It runs on the base's own over-key
frames, and its mouse/keyboard switching is part of that. The ergonomic objective found no swivel that brings the
elbows to 0–10 cm above the desk while the bulky sleeves keep clearance. 299 and 350 frames returned to the
clearance-solved pose. The next step is a per-segment contact solve for the right hand: keys versus mouse, with a
mouse contact model. After that, rerun with `--resume` for the transitions.
