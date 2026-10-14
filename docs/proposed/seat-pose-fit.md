# Proposed: seated pose fit (pelvis pitch, leg IK, baked arm IK) on the actual native cushion

This is a **trial**. Every clip, report and GLB is labelled `trial`, `verified: false`,
`requires_server_reaudit: true` and `requires_native_collision_audit: true`, in the GLB `asset.extras.sub01_labels`
and in each report. Nothing here sets or implies a seat or contact receipt or `NativeSeatVerified`. The earlier
failed receipts and reports are untouched. The gates are the validators' own constants, never relaxed:
- `tools/validate_unreal_seat_contact.py`: a seat patch fails below −2.5 cm, needs its lowest point at or below
  +0.5 cm, and needs at least 12 vertices in the band. A sole needs 0..+1 cm and at least 12 vertices.
- `tools/validate_unreal_contact_profile.py`: key gap at most 0.2 cm, penetration at most 0.1 cm. The arm target is
  KeyTop + 0.08 cm.

## Status

Every gate below was measured by **re-reading the written GLB**: the clip is re-sampled and the actual skin is
re-skinned.
- **DeskTyping** is re-sampled at the native audit times, 3..8 s at 60 Hz (301 samples).
- **The other clips** are re-sampled at every written key.

| clip (GLB in `docs/proposed/seat-pose-fit/`) | keys | gates on the written clip | pitch θ | lowering L |
|---|---|---|---|---|
| `SUB01_DeskTyping_seated.glb` (1.07 MB, 60 Hz) | 989 | **all pass**: 301 audit samples, and every key in memory | 22.5° constant | 8.619 cm constant |
| `SUB01_SeatedIdle.glb` (loop) | 126 | **all pass**; loop gate true | 22–24° per frame | 7.14–7.42 cm |
| `SUB01_SitDown_seated.glb` | 68 | **FAIL** (unchanged bytes): buttocks 18/18, right_posterior_thigh 18/18 | 0.0–30.0° applied | 0.00–7.66 cm |
| `SUB01_SitToType_seated.glb` | 37 | **all pass** on the gated frames | 13.8–24.0° applied | 7.28–8.77 cm |
| `SUB01_TypeToSit_seated.glb` | 29 | **all pass** on the gated frames | 12.0–24.0° applied | 7.52–8.78 cm |
| `SUB01_GetUp_seated.glb` | 63 | **all pass** on the 6 gated frames (since the seam need floor, below) | 24.0–30.0° at the seam side | 8.42–9.08 cm |

## Inputs (actual, committed)

- **Cushion.** `docs/proposed/native-chair-measured/20261014-actual-native-chair-surface.json` is root's native
  report: 150 cushion triangles, bounds [173.661, −214.063, 44.357]..[226.132, −166.341, 51.407]. It is the
  default. `--chair FILE` swaps in another report, and `--proxy` uses the old repo GLB proxy, for comparison only.
- **Plantar soles.** `docs/proposed/native-chair-measured/20261014-actual-native-plantar-witness.json.gz` is root's
  fixed witness, reduced by root's selector:
  - bind Z ≤ min + 0.4 cm;
  - bind normal Z < −0.7;
  - foot/toe weight ≥ 0.3.

  That leaves 4171 entries: 1923 left and 2248 right. `export_seat_fit_source.py --witness` identifies each one with
  the nearest posed owner vertex at 3 s. The match error is at most 0.0018 cm at 3, 6 and 8 s.
- **Capture and skin.** The capture is `web/room/mh_mx/room_mx_typing.glb` (DeskTyping), and the owner skin is
  `web/room/char_mixamo.glb`. The seated clips are `room_seated_idle`, `room_mx_sitting`, `room_mx_stand_to_sit`,
  `room_mx_sit_to_stand`, `room_mx_sit_to_type` and `room_mx_type_to_sit`.
- **Body transform.** [203.9, −232.3, −0.6], yaw 180, unchanged. The support (floor) is at z = 2.5 cm.
- **Root's seat-foot analysis** is `20261014-existing-seat-foot-fit-analysis.json`. This fit stays consistent with it:
  - no floor lift and no chair raise. Raising the chair would lift its base;
  - the body is **not** lifted;
  - the feet reach the support through leg IK only. The constant ankle raise is +2.669 / +2.863 cm, root's whole-plantar
    lift of 2.86 cm, applied per leg;
  - the chair moves only in XY.

## Method (`tools/fit_seat_pelvis_pitch.py`)

**(a) Pelvis pitch and lowering.**
- The Hips rotate by θ about the pelvis' own lateral axis (LeftUpLeg→RightUpLeg in Hips-local space).
- The pivot is the **Spine joint**, so the spine base does not swing.
- The Spine is counter-rotated, so Spine, Spine1, Spine2, Neck, Head, shoulders and arms keep their **captured world
  orientation**. Measured change: at most 1.2 × 10⁻⁵ °.
- The whole skeleton then lowers by L.
- Positive θ is a posterior pelvic tilt: the knees rise and the buttocks drop, which brings the thigh slope parallel
  to the cushion.
- Bone lengths are unchanged (0.0 cm).

**Choosing θ, L and the chair offset (DeskTyping).**
- L centres the seat patches' lowest gaps in the band, giving equal margin to −2.5 and +0.5.
- θ is the smallest pitch with at least 0.4 cm of margin and at least 12 band vertices on every key of the whole
  16.47 s loop.
- The chair XY was tried at the earlier candidate (+3.875, −36.875) and at dy −34.5 and −32.5. The smallest pitch
  wins.
- **Lowering alone is infeasible at every chair dy** (θ = 0 rows in the report).
- Coarse margins on 16 keys:

  | θ | dy −36.875 | dy −34.5 | dy −32.5 |
  |---|---|---|---|
  | 0° | −0.77 | −0.45 | −0.17 |
  | 16° | −0.12 | +0.13 | +0.30 |
  | 24° | +0.05 | +0.30 | +0.51 |

- **Chosen:** chair (+3.875, **−32.5**), θ = **22.5°**, L = **8.619 cm**. The dy −32.5 offset is inside root's
  buttock full-cover interval [−52.457, −32.089].
- **New chair actor translation:** [203.895, −219.190, 60.688] cm, rotation and scale unchanged. Root's measured
  translation is [200.020, −186.690, 60.688].

**Per-frame pitch for the other seated clips.**
- Every 3rd key gets the smallest θ (in 2° steps up to 30°) with 0.4 cm of margin.
- The result is interpolated, run through an upper-envelope filter (max over ±0.15 s, then a 0.1 s Gaussian, never
  below a key's own need), and given a per-key band-centred L.
- **Transitions:**
  - the correction is weighted by how seated the hips are (smootherstep on the hips height);
  - θ eases over 0.5 s to the neighbouring clip's seam value;
  - L is then re-solved on the gated frames.

**(b) Legs.**
- Non-stretch two-bone IK (UE `SolveTwoBoneIK` formulation) on UpLeg/Leg/Foot.
- The knee pole is the captured knee, carried with the pelvis.
- The foot keeps its **captured WORLD rotation** (the genuine toe plant; change at most 8 × 10⁻⁶ °).
- The ankle target is the captured ankle + the constant per-leg raise, which puts the lowest witness vertex at
  +0.001 cm.
- The hip-to-ankle distance stays at least 25 cm short of full extension.
- Toes keep their local rotation. No added foot slide: 0.0 cm.

**(c) Arms (DeskTyping), baked into the clip.**
- The correction is the existing keyboard rule (`SolveCapturedKeyboardArmContact` / `Sub01KeyboardContactCorrection`,
  Python counterpart `fit_seat_pose_trial.Trial`): the over-key distal skin minimum goes to KeyTop + 0.08 cm.
- It is solved with two-bone IK, the captured elbow as pole and the captured **wrist world rotation**. Finger locals
  are unchanged (at most 0.00019° from float32 storage).
- **Continuity.** The right hand leaves the keys for the mouse at 2.667, 9.25, 12.583 and 15.683 s.
  - Off the keys, its shift is +L, so it keeps its captured world height on the desk.
  - Within 0.25 s of a key segment, the shift eases (smootherstep) to the segment's value, so the hand never jumps.
  - Off-key frames end at most 1.11 cm below the captured hand height (`off_key_shift_minus_lowering_cm`). Desk and
    mouse contact there needs the native check.
- **Transitions SitToType / TypeToSit:** the seam frame's correction ramps in or out with smootherstep, so the
  approach motion stays genuine.

**(d) Head.** The head socket drops by exactly L: −8.619 cm for DeskTyping, −7.14 to −7.42 for SeatedIdle. The
first-person camera height needs re-checking natively.

## DeskTyping_seated — raw vs corrected

Measured on the 301 native audit samples, read back from the written GLB.

**Seat** (lowest gap in cm, minimum band vertices):

| patch | raw: lowest gap, frames passing | corrected: lowest gap, band min | gate |
|---|---|---|---|
| buttocks | +6.546..+6.825, 0/301 | −0.591..−0.074, 109 | pass 301/301 |
| left posterior thigh | +3.190..+3.390, 0/301 | −1.364..−0.999, 639 | pass 301/301 |
| right posterior thigh | +2.112..+2.410, 0/301 | −1.335..−0.909, 493 | pass 301/301 |

**Soles and keys:**

| patch | raw | corrected | gate |
|---|---|---|---|
| left sole | −2.661..−2.651 (penetration) | +0.0076..+0.0173, 97 vertices | pass 301/301 |
| right sole | −2.860..−2.857 (penetration) | +0.0027..+0.0062, 152 vertices | pass 301/301 |
| left keys (gap) | −9.334..−4.722 (fingers inside the keys) | +0.080..+0.080, ≥ 156 over-key vertices | pass 301/301 |
| right keys (gap) | −7.200..+2.188 | +0.080..+0.080, ≥ 166 over-key vertices | pass 301/301 |

**Arm reach and correction:**

| | left | right |
|---|---|---|
| arm length | 51.431 cm | 50.857 cm |
| worst request (audit window) | 44.50 cm | 46.33 cm |
| worst request (whole clip) | 46.84 cm | 47.14 cm |
| frames over arm length | 0 | 0 |
| bake shift | +13.42..+18.03 cm | +6.51..+15.90 cm |
| audit frames over the native 12 cm cap | **301** | **246** |
| largest per-key shift step | 5.06 cm | 3.42 cm |

- The native correction would refuse every audit frame over its 12 cm cap. The bake does the shift offline, so on the
  written clip the **native correction's request is 0.000 cm on every audit frame** and no frame is refused. The
  runtime correction is not needed.
- The largest per-key shift step (at 60 Hz) is the same per-frame rule the native correction applies: the hand
  rises when a finger presses.

**Other measures:**
- Bone lengths: 0.0 cm. Finger locals: at most 0.00019°. Foot world rotation: at most 8.3 × 10⁻⁶ °.
- Spine/neck/head/shoulder world rotation: at most 1.2 × 10⁻⁵ °. The spine moves exactly −8.619 cm vertically and
  0 horizontally.
- In memory, every one of the 989 keys of the whole loop also passes every gate. Right-hand key contact is gated on
  the 581 keys where that hand is over the keys.

## Stable seated interval and SeatedIdle

The thresholds are stated, not tuned:
- hips speed at most 2 cm/s;
- hips travel at most 1 cm within the window;
- window at least 1 s;
- loop seam from `verify_life_idle_candidate`: pose and hips at most 0.5 cm, velocity at most 5 cm/s.

Results:
- **Captured `room_mx_sitting` (root's `SUB01_Sitting`): no stable window.** Hips travel is 43.5 cm and peak speed
  58.7 cm/s over 4.43 s; it is a sit-down transition. **`SUB01_Sitting` must stay unbound as a seated loop; its
  loop gate is false.**
- **`room_mx_sit_to_type` / `room_mx_type_to_sit`:** shorter than 1 s of stillness (1.2 s and 0.93 s clips), so no
  loop window.
- **`room_seated_idle`** (the repo's captured Mixamo seated idle, baked for our chair by `mx_build.sh`) is stable over
  its whole 0..4.167 s.
  - Hips travel is 0.146 cm and peak speed 0.52 cm/s.
  - Raw seam: pose 0.006 cm, hips 0.006 cm, velocity 3.06 cm/s. It passes, so **no seam blend was needed**.
  - It is delivered as **`SUB01_SeatedIdle`**, a NEW asset, not a re-use of `SUB01_Sitting`.
  - Per-frame θ is 22–24° and L is 7.14–7.42 cm. The first and last keys share θ and L, so the loop stays closed.
  - Seat and soles pass on all 126 keys:

    | patch | lowest gap (cm) | band min |
    |---|---|---|
    | buttocks | +0.037..+0.099 | 16 |
    | left thigh | −1.620..−1.560 | 587 |
    | right thigh | −2.099..−2.037 | 815 |
    | soles | +0.001..+0.005 | ≥ 103 |

  - Loop gate: true.

## Transitions

### SitDown (`SUB01_SitDown_seated.glb`, source `web/room/mh_mx/room_mx_stand_to_sit.glb`)

- Gated frames: hips at the seated height AND settled (hips speed <= 2.0 cm/s), 18 of 68 keys.
- Seam ease: end: θ → 24.0° (SeatedIdle.first); own L at the seam 6.4613 cm vs the neighbour's 7.395 cm (vertical mismatch -0.934 cm)

| patch | raw lowest gap (cm) | corrected lowest gap (cm) | band min | failing gated frames |
|---|---|---|---|---|
| buttocks | +5.928..+6.188 | +0.502..+0.681 | 0 | 18 {'lowest_above_band': 18, 'support_vertices_short': 18} |
| left_posterior_thigh | +1.692..+1.760 | -0.370..-0.288 | 133 | 0  |
| right_posterior_thigh | -1.153..-1.052 | -2.681..-2.502 | 850 | 18 {'penetration': 18} |
| left_sole | -2.900..-1.946 | +0.001..+0.955 | 48 | 0 (penetration on ungated frames: 0) |
| right_sole | -2.905..-0.826 | +0.001..+2.079 | 0 | 0 (penetration on ungated frames: 0) |
- Residual on all 34 keys at the seated hips height (sliding frames, NOT gated): buttocks 34 failing, lowest +0.168..+1.834; left_posterior_thigh 0 failing, lowest -1.336..-0.170; right_posterior_thigh 32 failing, lowest -2.952..+0.461.
- Head height change: [-7.6583, 0.0] cm. Bone length error: 0.0 cm. Foot world rotation change: 6.3e-06°.

### SitToType (`SUB01_SitToType_seated.glb`, source `web/room/mh_mx/room_mx_sit_to_type.glb`)

- Gated frames: all frames (hips stay at the seated height), 37 of 37 keys.
- Seam ease: start: θ → 24.0° (SeatedIdle.last); own L at the seam 8.7664 cm vs the neighbour's 7.395 cm (vertical mismatch +1.371 cm); end: θ → 22.5° (DeskTyping_seated.first); own L at the seam 8.3168 cm vs the neighbour's 8.6192 cm (vertical mismatch -0.302 cm)

| patch | raw lowest gap (cm) | corrected lowest gap (cm) | band min | failing gated frames |
|---|---|---|---|---|
| buttocks | +6.100..+6.794 | -0.455..+0.060 | 60 | 0  |
| left_posterior_thigh | +3.514..+3.864 | -0.774..-0.380 | 304 | 0  |
| right_posterior_thigh | +1.575..+1.972 | -2.061..-1.551 | 1009 | 0  |
| left_sole | -2.670..-2.659 | +0.001..+0.012 | 95 | 0 (penetration on ungated frames: 0) |
| right_sole | -2.863..-2.859 | +0.001..+0.005 | 153 | 0 (penetration on ungated frames: 0) |

- Keys: the left seam gap is 0.08 cm (ramped shift 7.964 cm, under the 12 cm cap). Penetration over 0.1 cm: 0 frames on the left, 0 on the right. The right hand is not over the keys at the seam, in the raw capture either (it is on the mouse), so no contact is required there.
- Head height change: [-8.7664, -7.2778] cm. Bone length error: 0.0 cm. Foot world rotation change: 7.9e-06°.

### TypeToSit (`SUB01_TypeToSit_seated.glb`, source `web/room/mh_mx/room_mx_type_to_sit.glb`)

- Gated frames: all frames (hips stay at the seated height), 29 of 29 keys.
- Seam ease: start: θ → 22.5° (DeskTyping_seated.last); own L at the seam 8.3213 cm vs the neighbour's 8.6192 cm (vertical mismatch -0.298 cm); end: θ → 24.0° (SeatedIdle.first); own L at the seam 8.7783 cm vs the neighbour's 7.395 cm (vertical mismatch +1.383 cm)

| patch | raw lowest gap (cm) | corrected lowest gap (cm) | band min | failing gated frames |
|---|---|---|---|---|
| buttocks | +6.583..+6.754 | -0.445..+0.092 | 40 | 0  |
| left_posterior_thigh | +3.740..+3.867 | -0.813..-0.379 | 304 | 0  |
| right_posterior_thigh | +1.867..+1.930 | -2.092..-1.555 | 998 | 0  |
| left_sole | -2.670..-2.667 | +0.001..+0.003 | 96 | 0 (penetration on ungated frames: 0) |
| right_sole | -2.862..-2.860 | +0.001..+0.004 | 154 | 0 (penetration on ungated frames: 0) |

- Keys: the left seam gap is 0.08 cm (ramped shift 7.7922 cm, under the 12 cm cap). Penetration over 0.1 cm: 0 frames on the left, 0 on the right. The right hand is not over the keys at the seam, in the raw capture either (it is on the mouse), so no contact is required there.
- Head height change: [-8.7783, -7.5205] cm. Bone length error: 0.0 cm. Foot world rotation change: 6.7e-06°.

### GetUp (`SUB01_GetUp_seated.glb`, source `web/room/mh_mx/room_mx_sit_to_stand.glb`)

- Gated frames: hips at the seated height AND settled (hips speed <= 2.0 cm/s), 6 of 63 keys.
- Seam ease: start: θ → 24.0° (SeatedIdle.last); own L at the seam 7.8909 cm vs the neighbour's 7.395 cm (vertical mismatch +0.496 cm)

| patch | raw lowest gap (cm) | corrected lowest gap (cm) | band min | failing gated frames |
|---|---|---|---|---|
| buttocks | +5.741..+5.871 | +0.229..+0.397 | 7 | 1 {'support_vertices_short': 1} |
| left_posterior_thigh | +1.543..+1.617 | -0.906..-0.788 | 335 | 0  |
| right_posterior_thigh | -0.451..-0.369 | -2.397..-2.229 | 858 | 0  |
| left_sole | -2.905..-1.960 | +0.001..+0.947 | 47 | 0 (penetration on ungated frames: 0) |
| right_sole | -2.905..-1.687 | +0.001..+1.219 | 0 | 0 (penetration on ungated frames: 0) |
- Residual on all 36 keys at the seated hips height (sliding frames, NOT gated): buttocks 19 failing, lowest -0.221..+2.713; left_posterior_thigh 5 failing, lowest -2.906..+1.049; right_posterior_thigh 13 failing, lowest -3.110..+1.334.
- Head height change: [-9.0745, 0.0] cm. Bone length error: 0.0 cm. Foot world rotation change: 7.3e-06°.

**SitDown and GetUp, honest compromise.** On SitDown's 18 settled seated keys the spread from the buttocks' lowest
point to the right thigh's lowest point is about 3.18 cm, more than the 3.0 cm band, even at the 30° pitch cap; easing
to SeatedIdle's 24° at the seam makes it slightly worse. The gates are not relaxed:
- buttocks: +0.50..+0.68 cm, above +0.5 by up to 0.18 cm;
- right thigh: −2.50..−2.68 cm, deeper than −2.5 by up to 0.18 cm.

GetUp fails one gated key: buttocks band 7 < 12. Options for root, none applied here:
- a small right-only UpLeg knee-swivel (the optional per-hip pitch);
- a pitch above 30°;
- a captured sit-down whose final pose is closer to SeatedIdle.

The sliding keys at the seated height but still moving are reported as residuals.

## Alignment between clips (seam frames, corrected; raw in brackets)

Hips position delta in UE cm and hips rotation in degrees. `upper_body_shape` is the largest joint difference in the
hips frame: arms on the keyboard vs in the lap. The runtime blend must cover it.

| seam | hips Δ (x, y, z) cm corrected [raw] | hips rotation ° corrected [raw] | upper-body shape cm |
|---|---|---|---|
| SitDown.last → SeatedIdle.first | (-0.14, -3.30, -1.23) [(-0.09, -3.21, -0.04)] | 5.94 [5.94] | 24.6 |
| SeatedIdle.last → SitToType.first | (-0.00, -3.67, -1.09) [(-0.05, -3.77, +0.02)] | 5.96 [5.96] | 25.1 |
| SitToType.last → DeskTyping_seated.first | (-0.28, +0.34, -0.10) [(-0.23, +0.27, +0.05)] | 2.95 [2.95] | 25.3 |
| DeskTyping_seated.last → TypeToSit.first | (+0.50, -0.47, +0.13) [(+0.41, -0.41, -0.01)] | 3.46 [3.46] | 15.8 |
| TypeToSit.last → SeatedIdle.first | (+0.00, +3.67, +1.08) [(+0.05, +3.77, -0.04)] | 5.96 [5.96] | 25.1 |
| SeatedIdle.last → GetUp.first | (+0.19, +3.31, -0.08) [(+0.10, +3.21, +0.16)] | 5.87 [5.87] | 24.9 |
| SitDown.last → SitToType.first | (-0.14, -6.98, -2.32) [(-0.14, -6.98, -0.01)] | 0.02 [0.02] | 6.1 |

How to read this table:
- The pitch is continuous across every seam: corrected rotation deltas equal the raw captured ones (the transitions
  ease θ to the neighbour).
- The remaining hips deltas are the captured clips' own. The 3.2–3.8 cm in y between SitDown/SitToType/GetUp and
  SeatedIdle are different Mixamo captures.
- The corrected vertical deltas come from each clip's own band-centred lowering at the seam, between −1.23 and
  +1.08 cm. The runtime blend (≥ 0.25 s) covers them.
- **The Sitting stable window does not exist**, so it has no row. The StandToSit end → SitToType start delta is
  6.98 cm raw, 7.35 cm corrected.

## Capsule envelope and root trajectory

- **Data available.** The chair report has only the component AABB, with collision QueryAndPhysics and a Custom
  profile. There are no collision primitives. After the XY move, the AABB is [177.319, −247.173, 40.098]..
  [230.167, −193.533, 73.682].
- **Approach point.** This is the standing hips XY at the SitDown start: (203.988, −270.557).
  - The standing capsule (half-height 92, radius 17) there clears the chair AABB by **6.38 cm**. That is conservative,
    by AABB.
  - SitDown carries the hips (+0.14, +33.03, −21.47) cm into the seat. Seated hips XY: (204.13, −237.52).
- **Recommended, no bypass.**
  - The CharacterMovement capsule **stays at the approach point**: standing size, collision on, no move, no teleport,
    no collision disable.
  - The mesh is driven into the seat by the clips' own hips root motion.
  - SeatedIdle, SitToType, DeskTyping and TypeToSit keep the capsule there.
  - GetUp returns the hips to the approach point.
- **Not recommended.** A seated capsule over the seat (radius 17 at the seated hips) overlaps the chair AABB by
  construction. It would need a channel that ignores the chair, which is a bypass.
- **Root audit required:**
  - sweep the standing capsule at the approach point against the actual chair **and desk** collision;
  - check that the swept skin during SitDown/GetUp clears the chair frame, arm pads and desk underside. Only cushion,
    floor and keycap heights are measured here.

## Root: import and re-audit (exact steps; trial, verified false)

1. **Chair.** In the private diagnostic level, move the owned chair actor to translation **[203.895, −219.190,
   60.688]** cm, rotation and scale unchanged. That is root's measured [200.020, −186.690, 60.688] plus (+3.875,
   −32.5, 0). Then re-run `tools/unreal_chair_surface_audit.py` → `private-audit/native-chair-surface.json`. Body
   transform: unchanged [203.9, −232.3, −0.6], yaw 180.
2. **Re-run this fit on that report** if it differs from the committed one:
   ```
   python tools/export_seat_fit_source.py --out private-audit/seat-fit-source.npz
   python tools/fit_seat_pelvis_pitch.py --source private-audit/seat-fit-source.npz \
       --chair private-audit/native-chair-surface.json --chair-dx 0 --chair-dy 0 --out-dir out/seat-pose-fit
   ```
   Use `--chair-dx 0 --chair-dy 0` when the report was taken with the chair already moved. `--chair-dy` fixes the
   offset instead of solving it.
3. **Merge the corrected clips with the owner skin**, using the existing tools:
   ```
   node tools/uncompress_unreal_glb.mjs web/room/char_mixamo.glb out/owner.decoded.glb
   node tools/merge_unreal_skin_clips.mjs out/owner.decoded.glb out/seating-seated.merged.glb \
       docs/proposed/seat-pose-fit/SUB01_DeskTyping_seated.glb docs/proposed/seat-pose-fit/SUB01_SeatedIdle.glb \
       docs/proposed/seat-pose-fit/SUB01_SitDown_seated.glb docs/proposed/seat-pose-fit/SUB01_SitToType_seated.glb \
       docs/proposed/seat-pose-fit/SUB01_TypeToSit_seated.glb docs/proposed/seat-pose-fit/SUB01_GetUp_seated.glb
   ```
   Action names are the basenames, e.g. `SUB01_DeskTyping_seated`.
4. **FBX export** (Blender, server). `tools/export_unreal_seating_fbx.py` accepts exactly the four fixed roles, so root
   extends its `roles` map:
   ```
   {'DeskTypingSeated':'SUB01_DeskTyping_seated','SeatedIdle':'SUB01_SeatedIdle','SitDownSeated':'SUB01_SitDown_seated',
    'SitToTypeSeated':'SUB01_SitToType_seated','TypeToSitSeated':'SUB01_TypeToSit_seated','GetUpSeated':'SUB01_GetUp_seated'}
   ```
   - **Export DeskTypingSeated at 60 fps** (`scene.render.fps = 60`, `bake_anim_step = 1`). It has 60 Hz keys so the
     native 3..8 s @60 Hz audit samples are exact keys.
   - A 30 fps bake of an earlier 30 Hz version left interpolated 60 Hz samples up to 1.3 cm off the 0.08 target.
   - The others stay at 30 fps.
5. **Import** with `tools/unreal_import_seating_fbx.py`, which imports onto the existing owner USkeleton:
   - targets `/Game/Sub01Hands/Seating/SUB01_DeskTypingSeated`, `SUB01_SeatedIdle`, `SUB01_SitDownSeated`,
     `SUB01_SitToTypeSeated`, `SUB01_TypeToSitSeated`, `SUB01_GetUpSeated`;
   - for DeskTypingSeated, set `use_default_sample_rate=False` with a 60 Hz custom sample rate;
   - **do not overwrite** `/Game/Sub01Hands/FBX/SUB01_DeskTyping`, which backs the existing receipts.

   **DeskTyping replacement path:** bind the seated typing slot to `/Game/Sub01Hands/Seating/SUB01_DeskTypingSeated`.
   For the audits below, which load `/Game/Sub01Hands/FBX/SUB01_DeskTyping` directly, either:
   - point their clip constant at the new path in a private diagnostic copy; or
   - temporarily import the corrected clip over a duplicated `SUB01_DeskTyping` in a scratch content folder.
6. **Re-audit (natively, nothing claimed until each passes):**
   - `tools/unreal_audit_seat_contact.py`, gated by `validate_unreal_seat_contact.py`: buttocks, both posterior
     thighs, both soles, 301 samples;
   - `tools/unreal_audit_plantar_witness.py`: the fixed 4171 witness on the support;
   - `tools/unreal_audit_typing_contact.py` and the keyboard contact profile, gated by
     `validate_unreal_contact_profile.py`. The runtime `Sub01KeyboardContactCorrection` request should read ≈ 0 cm on
     every sample;
   - the native collision audit: capsule sweep at the approach point, thigh-under-desk, chair frame and arm pads;
   - the first-person head/camera height: −8.62 cm while typing;
   - SeatedIdle and the transitions on their own clips (seat/sole audits with the clip constant switched).
7. **Keep `SUB01_Sitting` unbound as a loop** (no stable window). Bind SeatedIdle only after its native audits pass.

## Regenerate

Tools:

| file | role |
|---|---|
| `tools/export_seat_fit_source.py` | compact source; `--witness` (default: the committed gz) uses root's fixed 4171 plantar witness |
| `tools/fit_seat_pelvis_pitch.py` | this fit: pitch/lowering solve, leg IK, arm bake, stable window, seam, GLB writer, written-GLB read-back gates |
| `tools/fit_seat_pose_trial.py` | shared kinematics, cushion and keycap geometry; `fit_arms(max_shift_cm=...)` lets the offline bake exceed the native 12 cm cap while still reporting it |

```
python tools/export_seat_fit_source.py --out private-audit/seat-fit-source.npz             # ~25 s; uses root's plantar witness
python tools/fit_seat_pelvis_pitch.py --source private-audit/seat-fit-source.npz \
    --out-dir docs/proposed/seat-pose-fit                                                  # ~10 min, 4 CPUs
python -m pytest tests/test_fit_seat_pelvis_pitch.py tests/test_fit_seat_pose_trial.py
```

`tests/test_fit_seat_pelvis_pitch.py` checks:
- the pitch keeps bone lengths and the spine world orientation;
- positive pitch lifts the knees;
- weighted per-frame pitch;
- the leg IK never stretches and keeps the foot world rotation and toe locals;
- the gates are the validator constants;
- the `--chair` swap changes the cushion and defaults to the actual report;
- the stable-window search finds the still part of a synthetic Sitting clip and rejects drift;
- the seam blend closes the loop continuously;
- quaternion round trip;
- the committed report and GLBs are trial-labelled and under 2 MB.

---

# Earlier trial (a4ed0ce): lowering only, proxy cushion — superseded

Kept for the record. Its conclusion ("one lowering cannot seat buttocks and thighs; a pelvis pitch is needed") is
what the section above implements on the actual cushion.

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

### Trial results, actual 301 frames

The cushion is a **proxy**: chair_fabric triangles from `web/room/chair_owner.glb` at its home.js placement,
selected by the `unreal_chair_surface_audit` rule.
- Proxy bounds: [173.837, −214.162, 42.002]..[226.084, −162.085, 58.702].
- Root's UE bounds: [173.661, −214.063, 44.357]..[226.132, −166.341, 51.407].
- The rise above 51.4 sits behind the buttocks. Under the skin the proxy plateau is 50.3–51.3 cm.
- The chair horizontal candidate is (+3.875, −36.875) cm.
- The support is z = 2.5 cm.

Re-run with `--chair` on root's real cushion report before trusting any seat number.

#### (a) Lowering

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

#### (b) Legs

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

#### (c) Arms

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

#### (d) Head and camera

The captured head socket moves rigidly with the body, **−7.108 cm** on every frame. The capsule and camera
height must be re-checked natively.

#### Collisions

Only cushion, floor and keycap heights are measured. Thigh-under-desk, chair frame and arm pads need the
native collision audit.

### Root's steps (superseded by the steps at the top)

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

## Seam need floor (GetUp fixed, SitDown still failing)

**Why GetUp failed.** Its 6 gated frames (7, 10–14) need 30° of pitch, but the 0.5 s seam ease from SeatedIdle's
24° pulled them to 26.6–30°, so one frame had only 7 buttock band vertices (gate: 12). Change in
`tools/fit_seat_pelvis_pitch.py`: the ease never takes a gated frame below its own pitch need (the rule
`solve_per_frame` already uses). The seam frame keeps the neighbour's exact 24°. Between it and the first gated frame
the pitch rises by smootherstep, 24° → 30° over frames 0–7 (0.23 s). The written GetUp now passes on every gated
frame:
- buttocks +0.209..+0.259 cm, at least 34 band vertices;
- left posterior thigh −0.906..−0.719 cm;
- right posterior thigh −2.259..−2.209 cm;
- both soles pass.

Cost: the vertical lowering mismatch at the SeatedIdle→GetUp seam grows from +0.50 to +1.02 cm. This is not a
validator gate; SitToType already has +1.37 cm. The seam still needs a native look.

DeskTyping, SeatedIdle, SitToType and TypeToSit are byte-identical. Their reports only gain the `floor_rule` seam
fields.

**Why SitDown still fails.** All 18 gated frames (50–67) need more than the 30° pitch grid allows. At 30°:
- buttocks lowest +0.50..+0.68 cm, above the +0.5 cm edge, with 0 band vertices (gate 12);
- right posterior thigh lowest −2.68..−2.50 cm, penetrating below −2.5.

The spread between those two patches (about 3.18 cm) is wider than the 3.0 cm band. An offline probe of the gated
frames (not committed) found:
- 34° passes 8/18;
- 38° passes 18/18 with 0.26 cm margin, under the required 0.4;
- pelvis roll of ±2–6° changes the spread by at most 0.03–0.09 cm. It does not help.

Two further obstacles:
- the last gated frame **is** the SeatedIdle seam frame (24°), so no floor can apply there without a pitch pop. The
  floor is therefore skipped on that side, and the clip is unchanged;
- passing would need either a posterior pelvic tilt above 30° (outside the stated search domain, anatomically
  doubtful) or a different seated end pose than the capture provides.

The importer and the config installer refuse SitDown outright, with no override.
