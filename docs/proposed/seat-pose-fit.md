# Proposed: seated pose fit — trial on the actual 301 DeskTyping frames

This is a **trial only**. Every output is labelled `trial`, `verified: false`, `requires_server_reaudit: true`
and `requires_native_collision_audit: true`. Nothing here sets or implies a seat or contact receipt. The
earlier failed receipts and reports are not touched.

## Tools

| file | what |
|---|---|
| `tools/export_seat_fit_source.py` | compact actual source: fixed patch vertex sets, bind data, captured joint world matrices; on-demand skinning |
| `tools/fit_seat_pose_trial.py` | trial pose fit: lower the body, two-link leg IK, the existing keyboard arm correction, all gates per frame |
| `tests/test_fit_seat_pose_trial.py` | parity on the repo GLBs, IK non-stretch, lowering solved from data, toe plant kept, per-frame reach, size bounds |

```
python tools/export_seat_fit_source.py --out private-audit/seat-fit-source.npz        # ~25 s, 2.7 MB
python tools/fit_seat_pose_trial.py --source private-audit/seat-fit-source.npz \
    [--chair private-audit/native-chair-surface.json] --out private-audit/native-seat-pose-trial.json   # ~10 min
python -m pytest tests/test_fit_seat_pose_trial.py
```

## Source and parity

**Inputs.**
- The owner skin is `web/room/char_mixamo.glb`, meshopt-decoded by the existing
  `tools/uncompress_unreal_glb.mjs` with the vendored decoder.
- The capture is `web/room/mh_mx/room_mx_typing.glb`, the `SourceAssets/room_mx_typing.glb` that UE imported as
  `SUB01_DeskTyping`. `web/house/assets/first-person/typing.glb` gives identical soles.
- Frames are t = 3 + i/60 s, sampled LINEAR from the clip's own node reference pose.
- UE component space is 100·(x, z, y) cm, then the audited body transform [203.9, −232.3, −0.6], yaw 180.

**Compact store.**
- Fixed index sets chosen once in bind space:

  | set | vertices |
  |---|---|
  | buttocks | 8057 |
  | left / right posterior thigh | 18751 / 19499 |
  | plantar (root's rule: `feet`, rest Y ≤ 0.004 m, bind normal Y < −0.7) | 4177 (1925 left + 2252 right; UE welds to 4171) |
  | distal finger skin | 961 / 959 |

- For those vertices only: bind positions, normals and weights.
- 65 × 301 joint world matrices.
- Total 2.7 MB, instead of about 70 M posed vertices.

**Parity with root's UE numbers at 3 s** (lowest / median / highest plantar gap, cm). The maximum error is
**5 × 10⁻⁶ cm**.

| sole | source | root UE |
|---|---|---|
| left | −0.161045 / 10.39739 / 24.268176 | −0.161045 / 10.39739 / 24.26818 |
| right | −0.360147 / 7.526767 / 14.819675 | −0.360148 / 7.52677 / 14.81967 |

The horizontal mapping and the arm chain also match root:
- **Buttocks:** the facing-down bounds match root's to the stated digits: min [185.272, −246.152, 56.511],
  max x/y [223.788, −218.797]. The max z is 83.023 here vs root's 83.081.
- **Keycap top:** reconstructed from `web/house/assets/keyboard/keyboard.glb` at its home.js placement,
  87.389759 cm vs root's 87.38975858.
- **Right-arm reach before any change:** worst request 51.84301 cm vs root's 51.84344, at t = 6.8333 s.
  - Arm length is 50.85702 vs root's 50.85667.
  - The post-correction right-hand gap maximum is 0.34406 cm vs root's 0.3442.

## Trial results, actual 301 frames

The cushion is a **proxy**: chair_fabric triangles from `web/room/chair_owner.glb` at its home.js placement,
selected by the `unreal_chair_surface_audit` rule.
- Proxy bounds: [173.837, −214.162, 42.002]..[226.084, −162.085, 58.702].
- Root's UE bounds: [173.661, −214.063, 44.357]..[226.132, −166.341, 51.407].
- The rise above 51.4 sits behind the buttocks. Under the skin the proxy plateau is 50.3–51.3 cm.
- The chair horizontal candidate is (+3.875, −36.875) cm.
- The support is z = 2.5 cm.

Re-run with `--chair` on root's real cushion report before trusting any seat number.

### (a) Lowering

**Not feasible as a single value on this cushion.**

The rule puts the highest per-frame lowest seat gap at 0, touching on the worst frame. That gives
**L = 7.108 cm**: mesh component z −7.708. The proxy cushion under the buttocks is about 1 cm lower than root's
51.407 top, so this is more than root's 5.1 cm estimate.

Results at that lowering:

| patch | lowest gap (cm), worst frames | band vertices min | gate |
|---|---|---|---|
| buttocks | 0.000 … −0.401 | 56 | **pass** all 301 |
| left posterior thigh | −2.725 … −2.904 | 1217 | **fail** (penetration) all 301 |
| right posterior thigh | −3.570 … −3.866 | 990 | **fail** (penetration) all 301 |

The band-feasible interval of L is **empty**:
- 6.573 cm puts the buttocks' lowest point at +0.5, but the right thigh is then at −3.47.
- 5.263 cm puts the right thigh's deepest point at −2.5, but the buttocks are then at +1.71.

**Why:** the captured thighs slope down toward the knees. With the body lowered, they reach the cushion front
edge 3.5–4.6 cm below the buttocks' contact level, and that holds even after the leg fit raises the knees. One
body lowering cannot seat both. The next pose step must be a bone-length-keeping **pelvis/hip pitch, or
thigh-only lift**, applied on top of the lowering, or a different genuine sitting clip. A chair raise is not
the answer (a raised chair floats on its wheels), and neither is relaxing the −2.5 cm edge.

### (b) Legs

These pass, including the support patch on both feet over all 301 frames.
- **Foot raise:** constant per leg in world, +2.661 (left) and +2.860 cm (right). That is **+9.769 and
  +9.968 cm relative to the lowered body**, against the expected "roughly +8".
- **Plantar result:** lowest 0.000 to 0.010 cm on every frame, with at least 99 left / 153 right plantar
  vertices in 0..+1 cm.
- **Two-link IK:** non-stretch and reached on all frames (the hip-to-ankle distance is at least 22 cm short of
  full extension). The knee pole is the captured knee.
- **Bone lengths:** maximum error **0.0 cm**.
- **Foot world orientation** (the genuine toe plant): maximum change **3 × 10⁻⁶ °**.
- **Foot slide:** the plantar centroid moves the same as captured (0.165 / 0.193 cm maximum), with zero added
  slide.

### (c) Arms

Reach requested is the shoulder-to-target distance vs arm length, per frame, all 301. The 0.08 cm target is
unchanged.

**Before:** the right hand is over the 50.857 cm arm on **11 frames**, by up to 0.986 cm at 6.8333 s:

| time (s) | over arm (cm) |
|---|---|
| 3.2 | 0.458 |
| 6.5167 | 0.323 |
| 6.5333 | 0.732 |
| 6.55 | 0.609 |
| 6.5667 | 0.538 |
| 6.5833 | 0.298 |
| 6.6 | 0.057 |
| 6.7833 | 0.173 |
| 6.8 | 0.548 |
| 6.8167 | 0.712 |
| 6.8333 | 0.986 |

Root counted 8. The worst value agrees to 0.0004 cm, so the difference is likely the counting criterion. The
left hand is never over (worst 48.622 of 51.431).

**After lowering:** no frame on either side is over arm length.
- The right worst is 47.226 cm, a margin of at least 3.631 cm.
- The left worst is 45.129 cm.
- At 6.8333 s, the right request drops from 51.843 to 47.226 cm.

**Over-correction.** The right hand used to need lowering by 2.108 cm to reach KeyTop + 0.08. After a 7.1 cm
body lowering it needs **raising by 5.000 cm**. The lowering more than removes the right wrist's required
lowering.

**The native arm correction then refuses most frames.**
- `Sub01KeyboardContactCorrection` refuses any |shift| > 12 cm, and that cap is not relaxed here.
- The captured left fingers already sit 4.7–7.5 cm into the keycaps. Add the 7.1 cm lowering and the needed
  lift exceeds 12 cm on **299 left frames**. The right side exceeds it on **156 frames**.
- On those frames the existing correction does nothing, and the trial shows over-limit penetration on 299 left
  and 156 right frames.
- **Key contact therefore fails after lowering** unless the hand pose comes from a capture whose fingers are
  not already deep in the keys, or a smaller lowering is found by the pelvis/thigh step above.

### (d) Head and camera

The captured head socket moves rigidly with the body, **−7.108 cm** on every frame. The capsule and camera
height must be re-checked natively.

### Collisions

Only cushion, floor and keycap heights are measured. Thigh-under-desk, chair frame and arm pads need the
native collision audit.

## Root's steps to apply and re-audit natively

1. **Export the source and keep the receipts.** Run `export_seat_fit_source.py` on the server. Keep every
   existing failed receipt and report unchanged.
2. **Re-run the trial on the actual cushion.** Use `--chair private-audit/native-chair-surface.json`, with the
   chair moved by the candidate (+3.875, −36.875) cm in the scene. Confirm L, the empty or non-empty interval,
   and the thigh penetration on the real cushion triangles.
3. **Only if a feasible pose exists** (after adding the pelvis/thigh step, or with another clip), apply it in a
   private diagnostic build only:
   - body z −0.6 − L;
   - per-leg IK targets (captured ankle + raise, captured foot rotation, captured knee pole);
   - the existing `SolveCapturedKeyboardArmContact` unchanged.
4. **Re-audit.**
   - `unreal_chair_surface_audit.py` → `unreal_audit_seat_contact.py` (gated by
     `validate_unreal_seat_contact.py`, every patch a local support patch);
   - the keyboard contact audit and `validate_unreal_contact_profile.py`;
   - the native collision audit.
   Nothing is claimed until those pass.
