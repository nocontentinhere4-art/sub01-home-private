# Phone grip: full-mesh solver and pickup/put-down proposal (private, unaccepted)

This is a proposal only. Nothing here is verified, bound or accepted:
- every report says `verified: false`, `requires_native_reaudit: true` and `visual_accepted: false`;
- nothing ran in Unreal or Blender;
- no Runpod action was taken.

Root imports the candidate, renders it natively and judges the actual image.

## Inputs (exact bytes)

| Input | Path | sha256 |
|---|---|---|
| Owner skin | `web/room/char_mixamo.glb` (equal to `web/house/assets/first-person/owner.glb`) | `7609eccb…57adbb` |
| Texting capture | `docs/proposed/phone-capture/texting.glb` (byte-identical to `web/house/assets/first-person/texting.glb`) | `8a6dfc04…ae75` |
| Phone | the original five-part assembly from `tools/unreal_phone_grip_diagnostic.py` `PARTS` | — |

- **Owner skin:** all 249,148 vertices of all 5 skinned primitives.
- **Texting capture:** the audit's `targetSHA256` is the owner above. The clip is 18.53 s and is sampled at 30 fps (556 frames, including exactly 4.000 s).
- **Phone:** the case is 7.5 × 15 × 1.5 cm. The screen is 6.7 × 13.7 cm at +0.8 cm from the body centre. The speaker, the volume key (−x) and the power key (+x) are included.
- **Mirrored phone frame:** x runs across (power key at +x), y runs along the length (speaker/top at +y), and z is the screen normal.

## Coordinate conventions

- **Units:** glTF owner model space, right-handed, in cm (the joints are cm under the 0.01 root).
- **UE values:** produced by the FBX handedness mirror `diag(1,-1,1)`, so `R_ue = M R M` and `t_ue = M t`.
- **Evidence for the mirror:** your native head-local eye `(.118852, -13.382491, 12.634526)` with Y negated lands 1.27 cm from the actual `owner_head` surface, in front of the face. The three other sign choices land inside the hood or body.
- **Parity check before import:** each report's `native_parity` gives the wrist position and rotation in the head frame, in the UE basis. Compare them against the `SUB01_PHONE_CAPTURED_WRIST/HEAD` log lines (0.5 cm / 1°) before importing.

## Tools

| File | Role |
|---|---|
| `tools/phone_grip_hand_export.mjs` | Skins every owner vertex with the exact clip (vendored three r180, meshopt; fingers, bones and clip untouched). It keeps the vertices within 30 cm of the right wrist on any frame, which is a reach bound, not a name filter. The output goes to the git-ignored cache `out/phone-grip/`. |
| `tools/fit_phone_grip.py` | The solver and residuals (see below). `--owner --clip [--phone measured.json] [--wrist-correction] [--evaluate-ue "X=.. Y=.. Z=..\|P=.. Y=.. R=.."]` |
| `tools/phone_grip_transition.py` | The pickup / lift / use / lower / release plan (see below). |
| `tools/unreal_phone_wrist_correction.py` | An opt-in native installer for the bounded RightHand correction (see below). |

### Solver

**Free variables.** There are two:
- one rigid phone transform in the RightHand joint frame;
- optionally, one constant RightHand local post-rotation `C`, at most 35°.

Finger local rotations, bone lengths and the clip are never changed.

**Geometry measured against the actual skin.** Joint names only label the report.
- Signed distance from every vertex to every part box. The vertices are split by dominant influence:
  - **rigid hand:** RightHand and fingers;
  - **forearm;**
  - **body.**
- Separating-axis triangle/box overlaps per part. This counts both case overlaps and screen crossings, with the screen at zero thickness.
- Eye rays from a 5×9 screen grid to the actual eye, tested against the actual triangles.
- Gravity support: the centre of mass inside the hull of the skin under the case, or a friction pinch with at least 3 skin contacts on each of two opposite case faces.
- Screen facing: the angle between the screen and the eye, and whether the speaker end is upright against the head's up axis.

**Arm IK.** Bounded (≤10 cm) and orientation-preserving: a RightArm/RightForeArm two-bone translation of the wrist. It is used only to clear body skin. Hand–phone residuals are invariant to it by construction.

**Search.** Geometric seeds (screen toward the eye, the palm side, and the thumb/finger-pad pinch), then CEM on the 4 s pose, then CEM on every 25th frame. It runs on 4 processes. Residuals are then computed on all 556 frames.

## Measured findings (4 s hold, actual skin)

**The captured hand is a closed hold.** The right index is near-straight (tip–wrist 13.2 cm). Middle, ring and pinky are curled (≈10 cm), and their distal pads sit 0–0.1 cm above the palm skin. There is therefore **no 1.5 cm cavity between the palm and the curled fingers**: the case cannot lie in the palm without moving fingers, which is not allowed.

**The thumb pad and the middle distal pad are ≈2.0 cm apart at 4 s.** The case thickness fits between them. During thumbing the gap varies (1.1 cm at 2 s, 0.6 cm at 12 s), so a rigid pinch has unavoidable small per-frame residuals.

**Mount-only rank 0** (screen toward the eye, no wrist correction):
- 0 screen crossings on all 556 frames;
- maximum hand penetration 0.027 cm;
- at most 19 case-triangle overlaps in the worst frame (226 in total);
- body cleared with at most 0.75 cm of IK.

But it rests the case on the thumb base only, with the screen 52° off the eye and 48° off upright. It is not a convincing grip.

**Mount plus a 17.8° wrist correction:** at 4 s the screen is 18.8° off the eye and 24.5° off upright, fully visible, with 0 penetration and 0 overlaps. But the contacts are the index and thumb tips on the back face only, so the case balances and is not a held grip.

Root's current mount, for comparison: 208 screen-triangle crossings and 1641 conservative case overlaps.

**The captured thumb taps.** The skin gap from the Thumb3 pad to the Middle3 pad cycles from ≥1.6 cm (open windows, each about 0.5 s) down to 0.62 cm. The open windows are 2.73–3.23, 3.43–4.07, 4.97–5.47, 6.40–7.03, 7.93–8.40, 8.73–9.33, 10.23–10.73, 10.93–11.53, 12.43–12.93, 13.73–14.37 and 15.27–15.73 s. The median over the 2–16 s hold is 1.44 cm. The series is in the report under `captured_thumb_middle_gap`.

A rigid 1.5 cm thumb/middle pinch is therefore exact only inside those windows, which include 4 s. In between, the captured thumb closes through the case plane. The first and last ≈1.5 s of the clip are the arm raising and lowering with open fingers (index tip–wrist 15.7 cm). Those frames belong to the pickup/put-down transition, not the hold.

## Final candidates (`phone-grip-texting.fit.json`)

The report holds both candidates, with all 556 frame rows, `thumb_screen_track` and `native_parity`.

| | **A: pinch at 4 s** (use for today's frozen 4 s review) | **B: full-clip clean** (use for live playback) |
|---|---|---|
| `phoneGripCandidate` (UE wrist-local) | `X=0.49562 Y=-12.94453 Z=10.12485\|P=-49.01338 Y=-48.31926 R=66.01844` | `X=0.67529 Y=-12.69298 Z=7.90880\|P=-59.66519 Y=64.88939 R=-19.60990` |
| `-Sub01PhoneWristCorrection` (UE RightHand local post-multiply, xyzw) | `0.13363071 -0.09262843 -0.10364932 0.98123373` (22.2°) | `0.19018425 -0.07935026 -0.12091590 0.97103699` (27.6°) |
| 4 s hand penetration / case overlaps / screen crossings | 0 / 0 / 0 | 0 / 0 / 0 |
| 4 s contacts | thumb pad on the case, middle distal pad on the back (33 vertices); friction pinch on opposite faces | index and middle distal pads only (10 vertices); not a supported grip |
| 4 s screen vs eye / upright / visible | 35.1° / 26.8° / 100 % | 26.0° / 19.9° / 100 % |
| All 556 frames: max hand penetration | 0.75 cm (346 frames: the thumb closing between the open windows) | 0.031 cm (3 frames) |
| All 556 frames: case overlaps / screen crossings | 43062 / 4564 (≤200 / ≤35 per frame) | 29 / 0 (≤12 per frame) |
| Body clearance IK | ≤6.5 cm on 37 frames | ≤2.75 cm on 10 frames |
| Thumb over the glass | no; the pad holds the bottom power-side corner of the case | no |

Orthographic diagnostic plots of the actual skinned points at 4 s, in the corrected hand frame: `A-pinch-4s-orthographic.png` and `B-fullclip-4s-orthographic.png`. Red marks skin within 0.3 cm of the case, and green is the direction to the actual eye. These are measurement plots, not renders and not visual acceptance.

**Assessment, without overclaiming.**
- **A** is the only candidate where the actual skin really holds the phone, and only while the captured thumb is open, which includes 4 s.
- **B** never intersects across the clip, but it rests the case on two fingertips, so it is not a held grip.
- No rigid mount of the 1.5 cm case can be both held and intersection-free on all frames with the captured fingers. The middle, ring and pinky are closed on the palm, and the thumb taps down to 0.62 cm from the middle pad.
- A fully physical live grip therefore needs either a capture whose fingers cradle a phone, or per-frame thumb collision that stops the thumb at the glass. The second is a finger change, which is out of scope under the no-edit rule.

## Applying it natively (root)

1. Check `native_parity` against the captured wrist/head log.
2. **Mount only:** pass `phoneGripCandidate` (UE wrist-local cm and an FRotator) through the existing protected native control, or `-Sub01PhoneMountCm=... -Sub01PhoneMountEuler=...`.
3. **With the correction:** in the staging script, after the contact-profile install and before `install_phone_grip_diagnostic`:
   ```python
   import unreal_home_hands_runtime, unreal_phone_grip_diagnostic
   from unreal_phone_wrist_correction import apply_to_modules
   apply_to_modules(unreal_home_hands_runtime, unreal_phone_grip_diagnostic)
   ```
   Then launch with `-Sub01PhoneWristCorrection="X=.. Y=.. Z=.. W=.."`, using `ue_right_hand_local_post_multiply_xyzw` from the report.
   - The review then runs the same captured Phone clip through `USub01HomeHandsInstance`, frozen at the review time. Its proxy `Evaluate` multiplies only the RightHand local rotation.
   - Both freeze guards (eye camera, candidate) route through `PhoneGripPoseFrozen`.
   - The correction is refused if it is not finite, not unit, or more than 35°.
   - The walk cleanup clears it.
4. **Per-frame arm IK** (only frames listed with a nonzero `ik_wrist_delta_cm_ue_wrist_local`): the effector is `W.Location + W.Rotation.RotateVector(delta)` with `W.Rotation` kept, on RightArm/RightForeArm, with the captured elbow as the pole. It is not wired natively yet. The rows give the delta per frame. Re-skin and re-audit natively.

## Pickup / use / put-down (`tools/phone_grip_transition.py`)

The phone is a world object until the hand actually reaches it, a rigid wrist child while held, and a world object again after release. It never teleports.

| Phase | What happens |
|---|---|
| REACH | The phone stays at rest. The wrist IK target is `rest · inverse(attach)`, approached from above the desk. |
| GRASP | Attach only on a frame where the measured skin-to-case gap is inside the 0.3 cm band. `attach = inverse(wrist_on_that_frame) · rest`, so the phone does not move at the attach instant. |
| LIFT | The wrist-local offset slerps (smoothstep) from `attach` to the solved `mount` while the wrist rises. The case bottom must stay above the measured desk top on every frame. Phone steps over 3 cm per frame are refused. |
| USE | Held at `mount` on the captured Texting clip, with the live browser screen unchanged. |
| LOWER | The reverse blend `mount` → `place = inverse(wrist_release) · rest`. |
| RELEASE | Detach when the case bottom reaches the desk band. The world transform is exactly the release-frame pose. |

`plan()` returns the pose per frame, the phases and its refusals. It needs actual wrist frames (native log or skin export), so root has to supply a real reach/lift capture or IK output. No synthetic motion counts as acceptance.

## Limitations

- **No native or visual verification.** The candidate is pending root's actual image.
- **Rigid hand–phone relation over a moving thumb.** The thumb moves while texting, so a rigid mount cannot be contact-perfect on every frame. The per-frame residuals are the evidence.
- **IK skin effects not modelled.** Forearm skin re-deformation under arm IK is not re-skinned here. Hand-vs-body skin after an IK move is not re-tested.
- **Scene geometry not tested.** Desk and chair are not included.
