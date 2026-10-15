# Anatomical seated base, judged by main's strong seat rule (checkpoint, `ready: false`)

This is a proposal. It is not verified and needs a native re-audit before use. It changes no importer pin or verdict field. The source captures and the committed `docs/proposed/seat-pose-fit` GLBs are untouched. The arms are not edited; they come in a separate later step.

- **Solver:** `tools/solve_seat_pose_anatomical.py`, tests in `tests/test_solve_seat_pose_anatomical.py`.
- **Objective:** the four per-patch conditions of main's `validate()`, as signed margins:
  - minimum gap at or above the band's lower edge;
  - median at or below the band's upper edge;
  - coverage of at least 0.5;
  - at least 12 vertices over the surface.

  There is no local-support (`MIN_SUPPORT_VERTICES`) term.
- **Verdict:** `tools/recheck_seat_fit_main_rule.py`'s own `measure_clip` and `recheck` on the written GLBs. That uses main's validator bytes (sha256 `dd95f1b1…`) and the fitter's actual-chair read-back. The read-back reproduces the stored per-frame gaps to within 2e-6 cm.

## Result on the measured chair (transform unchanged)

| Clip | Gated frames | Fail | Worst buttocks median | Worst buttocks coverage | Worst min gap (seat) | Worst sole median | Binding constraint |
|---|---|---|---|---|---|---|---|
| SeatedIdle | 126 | 0 | +0.253 cm (f49) | 0.568 (f47) | −2.251 cm, L thigh (f31) | 0.233 cm | buttocks median (0.247 cm margin), then L thigh min gap (0.249 cm) |
| SitDown_seated | 18 | 0 | see JSON | see JSON | see JSON | see JSON | buttocks median (0.275 cm margin) |
| GetUp_seated | 15 | 0 | see JSON | see JSON | see JSON | see JSON | buttocks median (0.255 cm margin) |

Per-frame data for every patch is in each `SUB01_*.report.json` under `actual_chair.per_frame.patches`: lowest, median, in-band and over-surface counts. Main's verdict and the worst frame per metric are in `main-rule-measured-chair.json`. On every frame, both soles are flat with the heel down: minimum gap 0.05 cm, median at most 0.233 cm, coverage 1.0.

## SeatedIdle edits (one constant set over the loop, so the capture's motion is kept)

- **Pelvis:** posterior tilt +33.2° about the pelvis lateral axis, pivot at the Spine. Absolute tilt goes from 6° to 39–40°, inside the 0–45° seated range. The Spine is counter-rotated, so lumbar flexion goes from 12° to 45.5°, inside the 52° limit (Pearcy 1984).
- **Root:** 12.82 cm down and 10.75 cm forward.
- **Upper body** (Spine1 and up, arms, head): world rotation unchanged (at most 1e-5°). It is translated by (0, −12.82, +10.75) cm in glTF.
- **Hips:** flexion goes from 73° to 38° (left) and from 68° to 37° (right). Abduction stays within 4–10°, rotation within −9 to −2°.
- **Knees:** flexion 98° (left) and 92° (right), from 80° and 72°.
- **Ankles:** dorsiflexion +19.6 to 19.8° (left) and +14.8° (right), from −54° and −32° plantarflexion (the toe plant). The left ankle is near the 20° limit. Subtalar inversion is 2.5° (left) and 6.9° (right).
- **MTPs:** returned to the bind pose (0°).
- **Per-joint local rotation changes** (maximum): Hips 33.2°, Spine 33.2°, L/R UpLeg 35.0/30.8°, L/R Leg 17.9/27.4°, L/R Foot 74.0/48.4°, L/R ToeBase 1.5/0.7°. The other 55 joints are unchanged. No non-root translation changes, and the bone-length error is 0.
- **Loop closure:** pose 0.006 cm, velocity 3.16 cm/s (passes).
- **Clearance:** the whole body against the complete chair has a minimum margin of +0.51 cm, with no penetration. Desk clearance is clear.

## Transitions (the existing seam-blend mode into the new loop)

The seam window was restricted so that every gated settled frame is already exactly the loop:

- SitDown: window 23–50.
- GetUp: window 14–41.

At the seam, the position delta is 0 and the velocity delta is 0.69/0.74 cm/s at the hips (the loop's own seam is 0.69). Clearance against the complete chair is +0.49 and +0.37 cm.

Two issues remain on ungated frames:

- **Desk clearance in SitDown:** the right forearm and hand dip up to 3.29 cm into the desk structure on 16 frames. These are the captured arms; the old fit has the same values (3.297 cm), and they will be addressed in the arm step.
- **Joint ranges on ungated stand/sit frames:** the capture itself leaves the seated ranges there (for example, anterior pelvic tilt while rising). See `anatomical_angles` in the reports.

## Chair-lift proposal (+2.5001 cm): see PACKET.md

This is the corrected source packet for the arm step:

- Ankle dorsiflexion is at most 19.50°, within the 20° limit.
- Main's strong rule passes on every gated frame of SeatedIdle (126), SitDown (18) and GetUp (17).
- The lifted chair transform and the geometric diagnosis are in `PACKET.md` and `geometry-diagnosis.json`.
- The readiness fields are `source_ready` (derived from every required clip's main rule, anatomical limits, complete-chair and desk checks; false while SitDown's desk clearance fails), `native_ready: false` and `ready: false`.
