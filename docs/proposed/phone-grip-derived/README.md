# Derived phone grip clip: checkpoint candidate (private, NOT ready)

The current checkpoint is solve v8. It replaced v6 (`df613902…`), which was worse on every audited count.

- **Label:** `derived_from_capture`. This is not the original capture, and original-capture invariance does not apply.
- **Status flags:** `verified: false`, `visual_accepted: false`. Every native gate is false.
- **Baseline:** `docs/proposed/phone-capture/texting.glb` (sha `8a6dfc04…ae75`) stays unchanged.
- **Scope:** source only. No Unreal, Blender, provider or Runpod action was taken.

| File | sha256 / note |
|---|---|
| `SUB01_PhoneGrip_derived.glb` | `231728793cd328eb92b69e47af13af364b4fd2dcb70cbbb3280576237075582e`: the Texting clip with only the edited rotation outputs replaced (557 keys, 30 fps, same input) |
| `SUB01_PhoneGrip_derived.report.json` | params, per-joint deltas/speeds, anatomy, mount, per-frame thumb stop, tap events |
| `SUB01_PhoneGrip_derived.audit.json` | independent full-mesh audit, three.js skinning, all 556 frames |
| `orthographic-4s.png`, `orthographic-10s.png` | measurement plots of the actual skinned points in the RightHand frame. Red = skin within 0.3 cm of the case; black = deeper than 0.15 cm. These are not renders. |

Reproduce:
```
python tools/derive_phone_grip_clip.py --params docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.report.json --out-dir <dir>   # byte-identical GLB
python tools/audit_phone_grip_clip.py --clip <dir>/SUB01_PhoneGrip_derived.glb --report <dir>/SUB01_PhoneGrip_derived.report.json --out <audit>
```

## What is derived

All edits are rotations, so bone lengths are unchanged (max error 1.9e-14 cm). Every other joint, including the whole left arm and hand, spine and head, is bit-identical to the capture.

| Joint(s) | Edit | Value |
|---|---|---|
| Right index/middle/ring/pinky | One constant cradle: rest × flex about local +X × abduction about local +Z (joint 1). Hard limits: MCP −5..85°, PIP 0..105°, DIP 0..75°, abduction ±15°. | MCP 9.9 / 19.4 / 24.7 / 32.7°, PIP 41.8 / 46.0 / 47.0 / 50.1°, DIP 31.4 / 32.4 / 32.9 / 34.1°, abduction 14.4 / 5.7 / 9.7 / 5.8° |
| RightHand | Captured × one constant correction, baked into the clip, so no native wrist installer is needed | 6.61° |
| RightHandThumb1 (CMC) | Captured × constant offset (≤45°) | 23.8° |
| RightHandThumb2 (MCP) | Captured × constant offset (≤30°), then a per-frame glass stop: MCP first, then CMC, on 75 frames; it reaches its 35° bound on at least one frame | 9.35° |

- **Tap events:** taps come only from the stop, never from a timer. The captured thumb would pass the glass, and the stop holds its skin on the glass inside the screen. The report lists 27 taps; the audit, using an independent ≤0.02 cm contact test, sees 28 glass contacts, mostly near uv (0.76–0.95, 0.48–0.61), toward the right of the glass.
- **Phone mount** (original five-part assembly, derived RightHand frame), UE `phoneGripCandidate`: `X=0.63516 Y=-8.88427 Z=4.47354|P=-19.28669 Y=65.29789 R=0.04263` (from the report).

## Independent audit, all 556 frames (hold window 2–16 s in brackets)

| Group | Max depth | Frames beyond 0.15 cm compression | Case / glass triangle overlaps |
|---|---|---|---|
| Fingers + palm (incl. thenar palm skin) | 0.21 cm | 111 (108) | 869 / 0 |
| Thumb (CMC/MCP/IP skin) | 0.175 cm | 1 (1) | 2371 / 1043 (the glass count includes stopped tap contact at the glass plane) |
| Forearm | 0 | 0 | 0 / 0 |
| Body | 0 | 0 | 0 / 0 |

- **Keys:** speaker, volume and power have 0 overlaps by any skin.
- **Support:** gravity support holds on all 556 frames (hull and/or friction pinch).
- **Screen angles in the hold:** 22.8–33.4° to the eye, 16.1–41.7° from upright, 91–96 % visible.
- **Left hand:** stays beyond the 30 cm export reach of the phone.

## Why it is not ready

1. **Palm/thenar skin still exceeds the 0.15 cm compression band** (max 0.21 cm) on 111 frames the solve did not sample. The captured thumb motion drags thumb-weighted palm skin. Next step: active-set constraint generation.
   - `--active-set out/phone-grip/active-set.json --add-worst-from-audit <audit>` appends the worst separated violating frames to a persisted set.
   - Those frames stay in every following solve, which warm-starts from this candidate.
   - The decision rests on the next independent audit, not the solver cost.
2. **The palm carries little.** There are about 12 palm contact vertices at 4 s, so the hold is mostly finger-pads-behind plus thumb-in-front, not yet a full palm cradle.
3. **Native checks still needed.** Native import, contact, visual acceptance and activity binding all remain false and require root's actual native proof.
