# Proposed: measured rigid seat placement candidates

`tools/fit_seat_rigid_placement.py` ranks **candidate** placements of the chair (preferred), the body, or the
keyboard+desk against the seated DeskTyping body, scored on the actual exported skin, cushion, support,
collision and reach samples. It is a proposal tool. Every output has `verified: false` and
`requires_server_reaudit: true`, and it never writes or mentions a seat/contact receipt. Any candidate you
choose must be applied on the server and then re-audited with `tools/unreal_audit_seat_contact.py`
(gated by `tools/validate_unreal_seat_contact.py`) and the keyboard contact audit
(`tools/validate_unreal_contact_profile.py`). Nothing counts until those audits pass.

Tests: `tests/test_fit_seat_rigid_placement.py`. The fixture is synthetic but built from root's measured
numbers. `test_actual_repo_data_if_present` runs on `private-audit/` exports when they exist and skips
otherwise; they are not in git.

## Rules it keeps

- **One rigid horizontal transform per unit.** Each unit gets `dx`, `dy` and `yaw` about a stated pivot.
  UE yaw convention: positive yaw turns +X toward +Y. The default bounds are ±40 cm and ±10°.
- **The body never moves vertically.** It is never scaled or stretched, and no bone changes in the
  chair, body or keyboard families. `evaluate()` raises if a body `dz` is passed, and the problem builder
  refuses a body scale other than 1 or any pitch or roll.
- **The chair `dz` is limited to the chair's real height adjustment.** That range comes from the scene
  export, defaults to none (`[0, 0]`) and is reported on every candidate.
- **The thresholds are imported, never redefined or relaxed.**
  - Seat band −2.5..+0.5 cm, with patches of at least 12 vertices and coverage ≥ 0.5
    (`validate_unreal_seat_contact`).
  - Soles are gated as a **support patch** (root, c93a830): nothing below the support (min ≥ 0), the lowest
    plantar point ≤ +1 cm, and at least `MIN_SUPPORT_VERTICES` (12) plantar vertices in 0..+1 cm. There is no
    whole-sole median or coverage gate, because a genuine seated foot plants its toes with the heel raised.
  - Skin counts only where it faces down: normal z ≤ −0.5, as in `AnalyzeCapturedSeatSkin`.
  - Key gap: at most 0.2 cm, with penetration of at most 0.1 cm (`validate_unreal_contact_profile`).
  - The key contact target is fixed at 0.08 cm (`unreal_keyboard_contact_target.py`).
  - Reach has zero tolerance: requested shoulder-to-target distance ≤ arm length.
  - Body vs rigid furniture: zero vertices inside.
- **The height lookup is Sub01SurfaceHeightAt.** It takes the highest triangle under (X, Y) by vertical
  projection, with barycentric tolerance −1e−6 and degenerate triangles skipped. A test compiles the native
  C++ function and compares the two.

## Inputs root exports on the server

All coordinates are world cm at the audited body transform: `[203.9, -232.3, -0.6]`, yaw 180, scale 1.
The 301 frames are DeskTyping at 3–8 s, 60 Hz, `t = 3 + i/60`. Every array is `[frames][vertices][3]`, uses the
same fixed vertex set every frame and lists vertices in the same order.

### (a) Skin: `private-audit/native-seat-fit/skin.json`

```json
{
  "schema": "sub01.seat-fit-skin.v1",
  "clip": "DeskTyping",
  "body": {"location_cm": [203.9, -232.3, -0.6], "yaw_deg": 180, "rotation_pyr": [0, 180, 0], "scale_xyz": [1, 1, 1]},
  "times_s": [3.0, 3.016667, "... 301 values ..."],
  "sole_membership": {
    "rule": "slides material, rest Y <= 0.004 m, bind normal Y < -0.7 (renderer fixed bind-space plantar selection)",
    "expected_vertex_count": 4171
  },
  "patches": {
    "buttocks":              {"positions_cm": [[[x,y,z], ...], ...], "normals": [[[nx,ny,nz], ...], ...]},
    "left_posterior_thigh":  {"positions_cm": ..., "normals": ...},
    "right_posterior_thigh": {"positions_cm": ..., "normals": ...},
    "left_sole":  {"vertex_indices": [i, ...], "positions_cm": ..., "normals": ...},
    "right_sole": {"vertex_indices": [i, ...], "positions_cm": ..., "normals": ...}
  },
  "collision_samples": {"positions_cm": [[[x,y,z], ...], ...], "leg": ["left" | "right" | null, ...]}
}
```

- **Seat patches.** Export every vertex the native audit selects for that region (Hips / LeftUpLeg /
  RightUpLeg weight ≥ 0.30), posed and with skinned normals. Do not subsample, because the ≥ 12 vertex count
  is native.
- **Soles.** Export root's fixed rest-mesh plantar index set: slides material, rest Y ≤ 0.004 m, bind normal
  Y < −0.7. That excludes cuffs and socks (sock minimum Y is 0.023386 m). Root reported 4177 vertices first
  and 4171 in the latest update (all footWeight ≥ 0.95); put the confirmed count in `expected_vertex_count`.
  - Export `vertex_indices` for each foot, with posed positions for exactly those indices, one to one.
  - The solver checks that the indices are unique and do not overlap between feet, and that their total
    equals `expected_vertex_count`.
  - It scores the same indices every frame. It never re-picks the lowest vertices.
  - The facing filter (normal z ≤ −0.5) still applies, as in the native audit. Root's left plantar plane
    normal z is only −0.53, so check `metrics.patches.left_sole.min_over_surface_vertices`.
- **`collision_samples`** (optional but recommended). These are posed skin vertices for collision: torso
  back, knees, shins, foot tops, forearms, and so on.
  - `leg` marks the vertices that belong to each leg chain, so the leg-support family can move them.
  - All patch vertices are also tested for collision automatically.

### (b) Chair: `private-audit/native-chair-surface.json`

This is the existing `tools/unreal_chair_surface_audit.py` report, unchanged. It provides
`chair.sections[].vertices_world_cm`, `cushion_surface.triangle_indices`, `chair.transform.translation_cm`
(the chair pivot) and `rotation_xyzw`. A cushion under 1000 cm² is refused.

### (c, e) Scene: `private-audit/native-seat-fit/scene.json`

```json
{
  "schema": "sub01.seat-fit-scene.v1",
  "floor_support": [
    {"name": "floor", "vertices_world_cm": [...], "triangle_indices": [[0,1,2], ...]},
    {"name": "office_rug", "adjustable": true, "vertices_world_cm": [...], "triangle_indices": [...]}
  ],
  "support_alternatives": [{"name": "remove_rug", "delta_cm": -2.5, "source": "measured rug thickness, <asset>"}],
  "chair_height_adjustment_cm": {"range_cm": [lo <= 0, hi >= 0], "source": "<real chair spec / asset>"},
  "chair_collision":    {"boxes": [BOX, ...], "convex_hulls": [HULL, ...]},
  "keyboard_collision": {"boxes": [...], "convex_hulls": [...]},
  "static_collision":   {"boxes": [...], "convex_hulls": [...]}
}
```

- **`floor_support`** is the actual support triangles under the feet: 2.5 cm near Y = −270. The highest
  surface wins.
  - `adjustable: true` marks a surface a real object could change (a rug or footrest).
  - `support_alternatives` must name a real measured change and its source.
- **Collision** comes in two forms:
  - `BOX = {"name", "center_cm", "half_extents_cm", "yaw_deg", "allowed_penetration_cm"?}`, a vertical-axis box.
  - `HULL = {"name", "vertices_world_cm", "triangle_indices"}`, a closed convex element (UE `FKConvexElem`).
- **Collision groups.**
  - `chair_*` moves with the chair.
  - `keyboard_*` moves with the keyboard as one rigid unit; put the desk here if desk and keyboard move
    together.
  - `static_*` never moves.
- **Leave the cushion foam out of the chair collision.** The cushion is scored by the seat band. Export the
  rigid parts only: base, column, backrest frame, arm pads.
- **Missing collision fails closed.** With no primitives, every candidate fails `collision_not_measured`
  and `inputs_incomplete`.

### (d) Keyboard: `private-audit/native-seat-fit/keyboard.json`

```json
{
  "schema": "sub01.seat-fit-keyboard.v1",
  "keycap_tops": {"vertices_world_cm": [...], "triangle_indices": [...]},
  "keycap_top_spread_cm": 0.077485,
  "key_contact_target_cm": 0.08,
  "arm_length_cm": {"left": 50.85667, "right": 50.85667},
  "keyboard_actor_world": {"location_cm": [x,y,z], "yaw_deg": yaw},
  "frames": [{"time_s": 3.0, "hands": [
     {"side": "left",  "shoulder_cm": [x,y,z], "target_cm": [x,y,z], "key_top_cm": 87.38975858, "corrected_over_key_min_cm": z},
     {"side": "right", "...": "..."}]}, "... 301 frames ..."]
}
```

- `target_cm` is the requested hand target, the one the arm IK reaches for. It moves with the keyboard.
- `shoulder_cm` moves with the body.
- `corrected_over_key_min_cm` is the over-key skin minimum after the server's non-stretch arm IK, the same
  quantity `validate_unreal_contact_profile` gates.
- `key_contact_target_cm` must be exactly 0.08, or the input is refused.

## Run

```
python tools/fit_seat_rigid_placement.py \
  --skin private-audit/native-seat-fit/skin.json --chair private-audit/native-chair-surface.json \
  --scene private-audit/native-seat-fit/scene.json --keyboard private-audit/native-seat-fit/keyboard.json \
  --out private-audit/native-seat-rigid-candidates.json   # optional: --families chair,body,keyboard --top 5
python -m pytest tests/test_fit_seat_rigid_placement.py
```

This is pure Python and NumPy, with no Unreal or Blender. The output is deterministic: the same inputs give
byte-identical JSON. The SHA-256 of each input is recorded in `inputs.digests`.

The search runs in four steps:

1. A deterministic grid: by default 4 cm and 2.5° over ±40 cm and ±10°.
2. Pattern-search refinement of the best seeds, down to 0.25 cm and 0.125°.
3. Ranking. Seat and collision skin are ranked on every 10th frame; reach and key always use every frame.
4. Final scoring. Every reported candidate is rescored on all 301 frames.

## Reading the output (`sub01.seat-rigid-candidates.v1`)

**Candidate.** Each candidate in `families.{chair,body,keyboard}.candidates[]` carries:
- `transforms` per unit: `{dx_cm, dy_cm, dz_cm, yaw_deg, pivot_cm}`, plus the moved actor or component
  transform when the export gives one.
- `body`: `dz_cm` is always 0, `scaled` is false and `per_bone_changes` is false.
- `passing`: true only if `failing_gates` is empty.
- `failing_gates`: each gate that still fails, with:
  - `gate` and `subject`;
  - `worst_amount` with its `unit`, and `worst_time_s`;
  - `failing_frames` out of `of_frames`, and every failing time in `failing_times_s`;
  - details of the worst frame: `requested_cm` / `arm_length_cm` / `horizontal_cm` / `vertical_cm` for
    reach, and `median_gap_cm` / `band_vertices` and similar for the seat and soles.
- `metrics`: per patch, the overlap fraction, worst gaps and minimum band vertices; reach and key contact per
  hand; and the maximum depth per collision primitive.

| gate | meaning |
|---|---|
| `patch_not_over_surface` | fewer than 12 facing vertices over the cushion / support (horizontal miss) |
| `penetration` | min gap below band (seat −2.5, sole 0) |
| `gap`, `coverage` | seat patches only: median above +0.5 cm, < 50 % of the patch in band |
| `sole_lowest_above_band`, `sole_support_vertices` | soles: lowest plantar point above +1 cm, < 12 plantar vertices in 0..+1 cm |
| `reach_exceeds_arm` | requested shoulder-to-target distance > arm length (no stretch) |
| `key_contact_gap`, `key_penetration` | post-IK over-key gap > 0.2 cm or penetration > 0.1 cm (invariant under horizontal placement) |
| `body_collision`, `furniture_overlap` | body vertex inside a rigid part, or two units' parts overlapping (box–box exact SAT, hulls by vertex containment) |
| `hip_joint_discontinuity` | leg-support family only: the UpLeg root is moved off the pelvis socket |
| `collision_not_measured`, `inputs_incomplete` | the export is missing something, so nothing can pass |

**Families.**
- `chair` also reports `chair_dz_needed_for_seat_band_cm`: the chair lift that would put every seat patch's
  minimum and median in band at the best horizontal placement. If `lo > hi`, no single height works and the
  pose must change. A lift outside the stated real range is reported, never applied.
- `body` and `keyboard` also report:
  - `reach_best`: the placement that minimises reach excess alone;
  - `trade_off.path`: five steps from the seat-ranked best to the reach best, each with its failing gates,
    frames over arm and seat overlap.
- `combined_chair_and_keyboard`: the best chair candidate plus the reach-best keyboard/desk, scored together.
  These are two rigid units; the body is untouched.
- `leg_support`: a per-leg rigid translation of the whole leg chain (thigh, calf, foot and toe as one unit, so
  bone lengths are kept), applied on top of the best chair candidate.
  - The translation is vertical by the support-patch rule: the lowest plantar point touches over every frame.
    It can also be horizontal on a bounded grid (`leg_xy_bound_cm`, off by default).
  - Any nonzero translation opens the hip by its length. That is reported as `hip_joint_discontinuity`, with
    `pure_rigid_placement: false` and `requires_pose_solution: true`. The fix needs a real pose solution (a
    pelvis/hip rotation that keeps bone lengths) or a different genuine clip.
  - This candidate never passes.
- `support_surface`: changes the support instead of the body. It reports:
  - per foot, the support-top Z range that would satisfy the gate over all frames;
  - the fixed floor under the foot, and whether a real object could provide that range;
  - each exported `support_alternatives` entry, evaluated exactly.

`irreducible_residuals` lists what no searched placement removes:
- reach in the chair family, since it moves neither the shoulders nor the keyboard;
- reach in every family, when that applies;
- a vertical reach component longer than the arm, which no horizontal move of any size can fix;
- the key gap;
- the seat vertical gap the stated chair range cannot close;
- the sole support, with the leg-support and support-surface options and their costs.

**Choosing a candidate.** Prefer a `chair` candidate. Apply the transform on the server, then re-run the
chair surface audit, `unreal_audit_seat_contact.py` and the keyboard contact audit. Only those audits decide
anything. The solver's `passing` is a prediction from exported samples, and is never a verification.

## What the fixture shows

These results come from root's measured numbers. Fixture assumptions are named in the test.

- **Current placement:** zero cushion overlap for buttocks and both thighs on all 301 frames. The buttocks'
  rear edge is at Y −218.797; the cushion starts at −214.063.
- **Horizontal fix:** the chair must move about 32–40 cm toward −Y. A cushion front edge past −246.152
  covers the buttocks fully. The best chair candidate is about (dx +3.9, dy −36.9) cm, yaw 0. It gives 100 %
  buttock overlap and 62.5 % thigh overlap, with no body or furniture collision.
  - This overlap result depends on the measured bounds only.
- **Seat height:** the lowest buttock skin (z 56.511) is 5.104 cm above the highest cushion point
  (z 51.407). No horizontal placement can close that, so the seat gap still fails.
  - It needs a real chair raise of at least about 4.6 cm (for the median to reach +0.5) or pose work.
    A body lift is forbidden.
  - The exact required lift range depends on the real skin height distribution. The fixture's buttock
    profile is an assumption.
- **Reach:** the right hand is over arm length on 8 frames; worst 51.84344 vs 50.85667 cm (+0.98677) at
  t = 6.8333 s. The reach result depends on root's measured distances; the shoulder and target layout around
  them is a fixture assumption.
  - The chair family cannot change this, so it is reported as irreducible there.
  - In the fixture, moving the keyboard/desk about 1.9 cm toward him clears all 8 frames. Combined with the
    chair move, seat overlap stays at 100 %.
  - Moving the body instead fixes reach only by moving away from the cushion. The body's seat-ranked best
    (+20 cm toward the chair) reaches only 49 % buttock overlap and puts both hands 15–16.5 cm over arm length.
  - On real data this depends on the actual target directions. If a frame's vertical shoulder-to-target
    component alone exceeds the arm, the solver reports it as irreducible by any horizontal placement.
- **Key gap:** 0.3442 cm on the right hand fails the 0.2 cm band. It is unchanged by any horizontal
  placement.
- **Soles vs the 2.5 cm support:** the toes penetrate by 2.661 cm (left) and 2.860 cm (right), using the
  measured minimums −0.161 and −0.360 cm.
  - Leg support needs +2.661 and +2.860 cm (root estimated +2.74 and +2.94 on the real mesh). That opens the
    hips by the same amounts, so a real pose solution is needed.
  - A support change would need a top at Z ≈ −1.16..−0.16 (left) and −1.36..−0.36 (right). That is below the
    fixed floor at 0, so no rug or footrest can do it. Removing the rug still leaves 0.161 and 0.360 cm of
    penetration.

## Unverified

- Everything above is fixture arithmetic on root's numbers plus stated assumptions. Nothing has been run
  on the real export.
- The real cushion's shape and skin height distribution decide the required chair lift.
- The real targets decide whether reach is fixable horizontally.
- The real collision parts decide clearance.
- The sole facing filter at the left foot's tilt (plantar normal z −0.53) is close to the −0.5 cut. Check
  the counts on the real export.
- Hull–hull furniture overlap is vertex containment, not exact.
