# Derived phone grip clip: native visual-review packet (private, NOT ready)

- **Label:** `derived_from_capture`. This is not the original capture, and original-capture invariance does not apply.
- **Status flags:** `ready: false`, `verified: false`, `visual_accepted: false`. Native import, contact, visual acceptance and activity binding all remain false.
- **Baseline:** `docs/proposed/phone-capture/texting.glb` (sha `8a6dfc04…ae75`) is unchanged.
- **Scope:** source only. No Unreal, Blender, provider or Runpod action was taken.

`packet.json` is the review packet. It holds the hashes, the contract, the mount, the taps, an audit summary, the open items and the server-only native review steps. It is checked by `python tools/phone_grip_packet.py check`, which confirms:
- exactly the 15 edited right-hand/thumb rotation channels differ from the capture;
- every other channel, the 557 key times, the nodes and the rest TRS are byte-identical;
- all channels target the owner's 65 skin joints.

| File | Content |
|---|---|
| `SUB01_PhoneGrip_derived.glb` | sha `81c1d4e10c0a71f46cb4aac36eafd605f92f2fa9397f8d444cc10775445823b2` (solve a2) |
| `SUB01_PhoneGrip_derived.report.json` | params, per-joint deltas/speeds, anatomy, mount, per-frame thumb stop, taps, active set, lineage |
| `SUB01_PhoneGrip_derived.audit.json` | independent three.js full-mesh audit, all 556 frames |
| `active-set.json` | audit-generated extrema kept in every solve (frames 63…504) |
| `orthographic-4s.png`, `orthographic-10s.png` | measurement plots of the actual skinned points in the RightHand frame. Red = skin within 0.3 cm of the case; black = deeper than 0.15 cm. These are not renders. |

Reproduce:
```
python tools/derive_phone_grip_clip.py --params docs/proposed/phone-grip-derived/SUB01_PhoneGrip_derived.report.json --out-dir <dir>   # byte-identical GLB
python tools/audit_phone_grip_clip.py --clip <dir>/SUB01_PhoneGrip_derived.glb --report <dir>/SUB01_PhoneGrip_derived.report.json --out <audit>
```

## Derived edits

All edits are rotations, so bone lengths are unchanged (max error 1.9e-14 cm). The left arm and hand, spine, head and all other joints are bit-identical to the capture.

| Joint(s) | Value |
|---|---|
| Finger cradle MCP (index / middle / ring / pinky; limit −5..85°) | 12.1 / 18.5 / 24.1 / 32.5° |
| Finger cradle PIP (limit 0..105°) | 41.0 / 43.9 / 45.7 / 47.2° |
| Finger cradle DIP (limit 0..75°) | 31.0 / 31.2 / 31.3 / 32.0° |
| Finger abduction (limit ±15°) | 13.9 / 7.8 / 10.6 / 1.8° |
| RightHand correction, baked into the clip (no runtime wrist installer) | 8.4° |
| Thumb CMC offset | 19.4° |
| Thumb MCP offset | 13.3° |
| Per-frame MCP glass stop | ≤1.6° |

The cradle is constant over the clip. The captured thumb texting motion is kept.

**Taps.** A tap counts only when the per-frame stop is engaged AND the thumb pad skin is within 0.02 cm of the glass rectangle. A stop on the case rim would be `rim_contact`, not a tap.
- a2 has 27 taps and 0 rim contacts.
- The independent audit sees 28 pad–glass contact events.
- uv ≈ (0.74–0.97, 0.38–0.54), the right-centre of the glass, each 1–4 frames long.

**Mount** (original five-part phone, derived RightHand frame): `phoneGripCandidate X=0.75422 Y=-9.68499 Z=4.71232|P=-22.42641 Y=59.35637 R=4.24461`.

## Independent audit, all 556 frames

| Group | Max depth | Frames beyond 0.15 cm compression (all / hold) |
|---|---|---|
| Fingers + palm (incl. thenar) | 0.198 cm | 77 / 68 |
| Thumb | 0.0 | 0 / 0 |
| Forearm | 0 | 0 / 0 |
| Body | 0 | 0 / 0 |

- **Keys and speaker:** 0 overlaps.
- **Support:** gravity support holds on all 556 frames.
- **Screen in the hold:** 22.7–33.1° to the eye, 11.0–36.2° from upright, 91–96 % visible.

## Lineage

| Solve | What changed | Fingers/palm max | Thumb max | Taps |
|---|---|---|---|---|
| v6 | pinned objective | 0.32 | 0.39 | (rim stops) |
| v8 | all-hand compression on 21 hold frames | 0.21 | 0.175 | (mostly rim stops) |
| a1 | +8 audit extrema | 0.19 | 0.077 | 2 genuine |
| **a2** | +6 audit extrema; pad-on-glass dips; thumb side ≥0.1 cm off the rim | 0.198 | **0.0** | **27 genuine** |

## Open (why `ready` is false)

1. **Palm/thenar compression.** The skin reaches 0.198 cm on 77 frames against the 0.15 cm band. The next step is another active-set round from this audit, with the decision resting on the audit.
2. **Little palm support.** This is a finger-pads-behind plus thumb-in-front hold, not a full palm cradle.
3. **Native proof outstanding.** Root's actual native first-person hand and live-screen pixels decide whether the geometry changes further.

## Native visual review (server only, root)

See `packet.json` → `native_review_steps_server_only`:
- `tools/export_unreal_phone_grip_fbx.py` mirrors the GamingGrip exporter. It refuses unless the GLB matches the packet sha, 557 keys and 65 joints.
- The derived clip must not replace the original `SUB01_Phone` asset.
- The phone is mounted with the existing private grip diagnostic and `phoneGripCandidate`, without `-Sub01PhoneWristCorrection`.
