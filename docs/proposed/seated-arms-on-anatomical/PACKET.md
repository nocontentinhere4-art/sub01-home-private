# Seated arms on the anatomical chair-lift base (SOURCE packet, `ready: false`)

> **Readiness labels (corrected):** the final segmented-rerun typing proposal has `source_ready: true` (every aggregate source gate passes) and `native_ready: false`; `ready` = source_ready AND native_ready = **false**. The CLI exits 0 only on source_ready. Nothing native is claimed.

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

## Typing: segmented rerun, complete but failing (`ready: false`)

This replaces the partial run above. Solver commits: 0d1dfc3, 593a370, 2ea922f, 85c5e6f and 1ca44a2. The run used the
same base clips, the lifted chair, `--arms-only` and roll (3.875, −21.279) cm. DeskTyping was solved in 10 chunks of
100 frames, with 12 frames of overlap and a checkpoint per chunk (`DeskTyping_seated.chunks/`). Run 1 stopped at 8 of
10 chunks on the 1320 s bound. Run 2 (`--resume`) solved the last 2 chunks, then SitToType, TypeToSit, the seams and the
roll gates, in 891.5 s.

**Right-hand segmentation.** Each frame is classed as keyboard (K), mouse (M) or transit (T): 422 K, 349 M and 218 T.
K and M are taken from the fit's on-key mask and the palm's distance to the mouse.

- **Keyboard frames:** IK to the keycaps under the key gates.
- **Mouse frames:** IK to main's `desk-hands/contact` mouse rule at the real `web/room/mouse.glb` placement
  (home.js `furnished("mouse", 2.4, 0.846, -2.91, 0.22)`). The palm point is 2.2 cm behind and 1.2 cm right of the
  shell top, giving target (241.2, −286.577, 90.041).
- **Transit frames:** desk clearance only, with quintic C1 blends at the segment boundaries.

The left hand is on the keys on all 989 frames.

| Clip (sha256) | Seat, main rule | Lower body / fingers vs base | Complete chair | Keys L / R | Mouse | Arms vs desk L / R |
|---|---|---|---|---|---|---|
| DeskTyping `9a8253ec…` | pass | 0 cm, 0° / 0° | pass (+0.279 cm) | pass (gap 0.065–0.146) / **FAIL**: 127 K frames gap > 0.2, worst 5.35 cm f158 | pass: XY 0.0008 cm, skin over shell 0.071–0.090 cm | pass (forearm +0.54 f555) / **FAIL**: fingers −1.52 f555 (T), forearm −0.088 f477 |
| SitToType `adb7547e…` | pass | 0 / 0 | pass (+0.567) | pass / pass | – | **FAIL**: L fingers −1.52 f7, hand −1.01 f6; R similar f6–7 |
| TypeToSit `ed0911cc…` | pass | 0 / 0 | pass (+0.554) | **FAIL**: L penetration −0.59 f0 / pass | – | **FAIL**: L fingers −0.57 f23 |

- **`validate_unreal_contact_profile.validate()`** on DeskTyping refuses with "Fingertips hover above the keycaps
  (gap over 2 mm)". These are the right-hand K frames next to segment switches.
- **Roll gates pass:** the complete chair clears the desk (20 cm) and the floor (+0.0001 cm), floor contact is
  unchanged, and the roll is exactly reversible.
- **Seams:**
  - Position Δ is 0 at SitDown→Idle, Idle→SitToType, TypeToSit→Idle and Idle→GetUp. It is 0.24 cm at
    SitToType→DeskTyping.
  - The DeskTyping loop (last→first) is **2.71 cm / 9.99°** on the right arm. DeskTyping→TypeToSit is **2.55 cm**.
    These come from the right hand's segment state differing at the clip ends. **Not continuous.**

**Ergonomics: soft targets, unreachable, with numbers.** The targets are elbows 0–10 cm above the 84.5 cm top and
the upper arm within 20° of vertical. Both arms miss them on all 989 frames.

- **Reached:**
  - Left: elbow 97.2–101.0 cm, upper arm 65.5–77.4°.
  - Right: elbow 94.6–106.6 cm, upper arm 59.6–90.0°.
  - Shoulder elevation: L −26.7 to −9.0° (captured −22.4 to −9.0°), R −21.8 to −5.2°.
- **Why they cannot be reached:**
  - **Reach.** The shoulder is 44.1–50.2 cm (L) and 37.4–49.3 cm (R) horizontally from the wrist on the keys or the
    mouse. The segments are only l1 28.1 + l2 23.3 cm long, which puts a floor of asin(max(0, d_h − l2)/l1) =
    **47.7–72.9° (L) and 31.0–70.6° (R)** on the upper arm. That is above 20° on every frame.
  - **Sleeves.** The sleeve is 10.7 cm thick at the elbow, so clearing the slab needs the elbow at ≥ 95.2 cm. That
    is above the 94.5 cm the target allows.
  - **Girdle.** The girdle allows depression 0–10° and pro/retraction ±15° (Kapandji). The per-chunk ergonomic budget
    (60 s) stopped the search before a girdle candidate was kept, so the girdle stays at 0°/0°. Even at full
    retraction, a 15° girdle moves the shoulder by about 4 cm, and the reach floor stays above 20°.
- **Fix:** the base posture or the chair-to-desk distance has to change. The chair would need to roll in about
  15–20 cm, or the keyboard come toward the body. That is a base/root decision.

**Remaining blockers:**

1. Right-hand K frames hover next to segment switches (127 frames).
2. Transit f555 fingers and f477 forearm.
3. SitToType f6–7 hands into the desk (the arm pass does not yet run on its early transit frames).
4. TypeToSit seam-frame key penetration.
5. The DeskTyping loop and exit seams on the right arm.

## Typing: hard gates fixed (every source gate passes; native unverified)

This replaces the two typing sections above. The solver commits are 48742c3, 1b0feac, d500d55, 1b500fa, 10c7da8,
cb9f770 and 5b24f9e. The setup is unchanged:

- same base, lifted chair, `--arms-only`;
- roll (3.875, −21.279) cm, keyboard unchanged; the chair/keyboard ergonomic decision stays with root.

DeskTyping resumes from the 10 committed chunk checkpoints, which serve as the warm start. A whole-clip **finish** stage
follows, checkpointed in `SUB01_DeskTyping_seated.finish-checkpoint.npz` (1019 s). The measurement and the transitions
ran in the next bounded run (573 s).

**What changed:**

1. **Segmentation.** A transit run with a KEYBOARD segment on both sides becomes KEYBOARD. The rule is cited from
   docs/qa/contact.md for seated "type": fingertips on the keycaps, 0 to +2 mm, through the whole clip.
   - Right hand: 574 key, 349 mouse and 66 transit frames.
   - Transit is left only between the keyboard and the mouse, and the C1 blends live there.
   - Every KEYBOARD frame is gated as on the keys.
   - A keyboard frame whose fit path leaves the keycaps has its finger target pulled back into the key field.
2. **Contact polish.** Keyboard frames still outside the gate take a vertical correction from a 0.05 cm grid.
   - Where the lowest fingertip switches keys, the grid is tried again after a 0.25–1.0 cm horizontal hand move.
   - Frames polished: 214, 215, 240, 295, 304, 405, 406, 407 (all fixed). Single-frame horizontal moves were needed at
     214, 215, 295 (0.25 cm) and 405–407 (0.25, 0.5, 1.0 cm).
3. **Clearance where the right arm is fully extended.** The swivel cannot help there.
   - Added palmar wrist flexion toward neutral (six arm bones only) on 241 frames, up to 40° before the soft ±15° limit.
     The resulting wrist flexion stays between −15° and 13.7°.
   - A reach step (finger target up to 14 cm toward the body) and a clavicle fallback exist, but this run used neither.
   - The contact profile now reports a changed clavicle truthfully: it lists it, and the validator refuses.
4. **Loop closure.**
   - The last 0.5 s of IK inputs and parameters is C1-blended to frame 0.
   - The finish checkpoint restores those inputs.
5. **Transitions.**
   - The SitDown/GetUp desk pass (38fb963) now runs on SitToType and TypeToSit, on every frame and every arm vertex. It
     never pushes an arm down through a desk part.
   - Seam-frame corrections taper to exactly zero over 0.2 s (quintic).
   - TypeToSit's frame 0 therefore keeps DeskTyping's written last arm pose.

| Clip (sha256) | Keys L / R | Arms vs desk L / R (min cm) | Mouse | Seat (main) / base invariance / fingers / chair |
|---|---|---|---|---|
| DeskTyping `26b3a8e3…` | pass (gap ≤ 0.160) / pass (key-frame penetration ≤ 0.014) | +0.507 / +0.508 | pass: XY 0.0002 cm, skin 0.072–0.090 cm | pass / 0 cm / 0° / +0.279 cm |
| SitToType `a141cae8…` | pass / pass | +0.508 / +0.565 | – | pass / 0 / 0° / +0.567 |
| TypeToSit `7e3fbadf…` | pass (frame-0 gap 0.13; worst penetration ≤ 0.011) / pass | +0.578 / +0.500 | – | pass / 0 / 0° / +0.554 |

- **`validate_unreal_contact_profile.validate()`** on the 301-row window **passes**. The maximum corrected key gap is
  0.080 cm (left) and 0.134 cm (right); penetration is 0. No clavicle changes inside the window.
- **Roll gates pass:** complete chair vs desk and floor, floor contact unchanged, exactly reversible.
- **Not gated:** 18 right-hand transit frames hover over the keys while approaching or leaving them (158–159, 753–756,
  935–946).

**Seams** (position Δ max joint / arm joint, rotation Δ, arm velocity Δ):

| Seam | Position Δ max / arm (cm) | Rotation Δ | Arm velocity Δ (cm/s) |
|---|---|---|---|
| SitDown → Idle | 0 / 0 | 0 | 2.9 |
| Idle → SitToType | 0 / 0 | 0 | 5.7 |
| SitToType → DeskTyping | 0.239 (RightFoot, base) / 0.032 | 0.41° | 10.2 |
| DeskTyping loop | 0.019 / 0.019 | 0.05° | 4.6 |
| DeskTyping → TypeToSit | 0.353 (LeftLeg, the base's own seam) / 0.049 | 1.45° | 17.4 |
| TypeToSit → Idle | 0 / 0 | 0 | 7.2 |
| Idle → GetUp | 0 / 0 | 0 | 2.9 |

**Ergonomics (soft targets) are still missed on every DeskTyping frame.** The reason is the reach geometry in the
section above; the chair/keyboard distance is root's decision.

| | Elbow height (cm) | Upper arm from vertical | Shoulder elevation |
|---|---|---|---|
| Left | 97.2–101.0 | 65.8–77.3° | −26.7 to −9.0° |
| Right | 95.4–108.4 | 61.3–94.3° | −21.8 to −5.2° |

**Bounding:**
- DeskTyping uses chunks with checkpoints, plus a checkpointed whole-clip finish stage.
- The finish is one stage. It took 1019 s in this run; an earlier variant took 1876 s, over the 1320 s bound, because
  the bound is checked between stages.

**For root to confirm:**
1. Desk centre Y: −302 in the script vs −310 in the record.
2. The +2.5001 cm chair lift.
3. Keyboard foot contact.
4. A native swept collision audit.
5. The left clavicle depression from the ergonomic objective, on 51 DeskTyping frames outside the 3–8 s window, against a
   six-arm-bone native correction.
6. The chair-to-keyboard distance (ergonomics).
