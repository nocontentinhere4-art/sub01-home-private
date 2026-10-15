# Derived phone grip clip: checkpoint candidate (private, NOT ready)

- **Label:** `derived_from_capture`. This is not the original capture, and original-capture invariance does not apply.
- **Status flags:** `verified: false`, `visual_accepted: false`. Every native gate is false.
- **Baseline:** `docs/proposed/phone-capture/texting.glb` (sha `8a6dfc04…ae75`) stays unchanged.
- **Scope:** source only. No Unreal, Blender, provider or Runpod action was taken.

| File | sha256 / note |
|---|---|
| `SUB01_PhoneGrip_derived.glb` | `df613902840c5d7a537792316838f5d11cf2978dc080e46f7540206357d37c31`: the Texting clip with only the edited rotation outputs replaced (557 keys, 30 fps, same input) |
| `SUB01_PhoneGrip_derived.report.json` | params, per-joint deltas/speeds, anatomy, mount, per-frame thumb stop, tap events |
| `SUB01_PhoneGrip_derived.audit.json` | independent full-mesh audit, three.js skinning, all 556 frames |
| `orthographic-4s.png`, `orthographic-10s.png` | measurement plots of the actual skinned points in the RightHand frame. Red = skin within 0.3 cm of the case; black = deeper than 0.15 cm. These are not renders. |

Reproduce:
```
python tools/derive_phone_grip_clip.py --params docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.report.json --out-dir <dir>   # byte-identical GLB
python tools/audit_phone_grip_clip.py --clip <dir>/SUB01_PhoneGrip_derived.glb --report <dir>/SUB01_PhoneGrip_derived.report.json --out <audit>
```

## What is derived

All edits are rotations, so bone lengths are unchanged (max error 1.8e-14 cm). Every other joint, including the whole left arm and hand, spine and head, is bit-identical to the capture.

| Joint(s) | Edit | Value |
|---|---|---|
| Right index/middle/ring/pinky | One constant cradle: rest × flex about local +X × abduction about local +Z (joint 1). Hard limits: MCP −5..85°, PIP 0..105°, DIP 0..75°, abduction ±15°. | MCP 9.6 / 19.2 / 23.5 / 33.2°, PIP 42.5 / 48.9 / 48.4 / 48.1°, DIP 32.1 / 33.4 / 34.0 / 34.2°, abduction 14.8 / 4.6 / 7.1 / 3.1° |
| RightHand | Captured × one constant correction, baked into the clip, so no native wrist installer is needed | 5.75° |
| RightHandThumb1 (CMC) | Captured × constant offset (≤45°) | 27.6° |
| RightHandThumb2 (MCP) | Captured × constant offset (≤30°), then a per-frame glass stop of at most 6.7° (MCP only, on 39 frames) | 9.3° |

- **Tap events:** taps come only from the stop, never from a timer. The captured thumb would pass the glass, and the stop holds its skin on the glass inside the screen. The report lists 14 taps; the audit, using an independent ≤0.02 cm contact test, sees 7 glass contacts, all near uv (0.83, 0.49).
- **Phone mount** (original five-part assembly, derived RightHand frame), UE `phoneGripCandidate`: `X=0.76195 Y=-8.64162 Z=4.40882|P=-16.31516 Y=67.88692 R=-2.96622` (from the report).

## Independent audit, all 556 frames (hold window 2–16 s in brackets)

| Group | Max depth | Frames beyond 0.15 cm compression | Case / glass triangle overlaps |
|---|---|---|---|
| Fingers + palm (incl. thenar palm skin) | 0.32 cm | 208 (194) | 2648 / 0 |
| Thumb (CMC/MCP/IP skin) | 0.39 cm | 164 (85) | 5824 / 390 |
| Forearm | 0 | 0 | 0 / 0 |
| Body | 0.20 cm (one end frame) | 1 (0) | 20 / 8 (2 frames, outside the hold) |

- **Keys:** speaker, volume and power have 0 overlaps by any skin.
- **Support:** gravity support holds on all 556 frames (hull and/or friction pinch).
- **Screen angles in the hold:** 21.7–32.5° to the eye, 16.5–42.5° from upright, 91–95 % visible.
- **Left hand:** stays beyond the 30 cm export reach of the phone.

## Why it is not ready

1. **Thenar/palm and thumb skin exceed the compression band on frames the solve did not sample.** The captured thumb motion drags thumb-weighted palm skin. Next step: active-set constraint generation.
   - `--active-set out/phone-grip/active-set.json --add-worst-from-audit <audit>` appends the worst separated violating frames to a persisted set.
   - Those frames stay in every following solve, which warm-starts from this candidate.
   - The decision rests on the next independent audit, not the solver cost.
2. **The palm carries little.** There are about 14 palm contact vertices at 4 s, so the hold is mostly finger-pads-behind plus thumb-in-front, not yet a full palm cradle.
3. **Native checks still needed.** Native import, contact, visual acceptance and activity binding all remain false and require root's actual native proof.
