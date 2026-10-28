# Kimi design review (2026-10-24): native v23, live-tunable look corrections

Question: `q-native-v23-design.txt` (same folder), with two frames attached: `docs/streamer/photos/20261024/now-webcam.jpg` and
`now-cam2.jpg`. Model `kimi-k3.1-pro`. The first call ran out of its 16k-token budget while reasoning (no answer); the second
call (40k tokens) answered after HTTP 429 retries.

Context sent with the question (measured on game m3, build v21): elbow interior angle L 73-80 / R 64 deg (recipe 85-100), wrist
targets reached exactly, finger flexion MCP/PIP L 16/28 R 16-20/13-24, no mouse actor near the mat, lean -6 measured, chair fit
on the backrest part (gap 0.9 cm) while the chair's big frame part still crosses the oversized hoodie in cam2, one soft key light
of 0.04 cd on the webcam axis.

## Answer (verbatim)

Overall, the levers and the proxy ordering are sound. I would make three conceptual changes: use **hand placement as the primary reach fix and `elbow_min_deg` only as a guard**, treat **`neck_girth` and `mouse_scan` as experiments rather than expected fixes**, and make the **chair fit account for the shell, not just the backrest**.

The frames support these hypotheses, but they cannot prove the skinning causes. These changes can improve pose, contact and lighting; they do not by themselves guarantee photorealistic skin, hair or cloth.

## 1. Are these the right levers?

### Neck/hood seam

`neck_share` is the right first lever. Start with:

- `neck_share = 0`
- `neck_girth = 1`
- `neck_back_deg` determined by posture, not by the seam

With share zero, head-channel motion no longer twists the neck skin away from a hood ring that is mostly torso-weighted. If large yaw then looks rigid, try `0.10–0.15`, not an immediate return to `0.4`.

`neck_back_deg` may improve the head-over-shoulders silhouette, but it is **not fundamentally a seam fix** and can open or close the gap depending on the hood weights.

`neck_girth` is only a blunt corrective. It is not vertex-selective: partially weighted vertices will change, hood vertices may change too if they share Neck influence, and rotated non-uniform bone scale can produce skinning/normal artefacts. It can help if the neck is uniformly too thin inside an otherwise correctly fitted ring; it will not reliably fix a jagged lining edge or an asymmetric wedge.

Before using girth, run three diagnostics:

1. Hide slots 4 and 5 separately. If the jagged edge changes, investigate lining/patch intersection or z-fighting first.
2. Temporarily remove head pitch/yaw and compare `neck_share = 0` versus `0.4`.
3. If the gap remains with no head motion, treat it as an asset-fit problem. The durable fix is hood-ring/neck weights and geometry, possibly with a proper inner collar.

If a uniform radial gap remains, try `neck_girth = 1.05`, then at most `1.08–1.10` in this session.

### Other defects

- **Elbow fan:** pole, reach and posture are the right pose-side levers. If it survives a nearly open elbow and a down/out pole, it is probably weights/deformation, not IK.
- **Posture:** A is appropriate, especially before IK. Preserve thigh orientation in a common reference frame, rather than assuming equal opposite local UpLeg rotations are exact.
- **Hands:** position-based orientation is a substantial improvement over guessed Mixamo local axes. Position and orientation must be fixed before judging finger contact.
- **Lighting:** key direction and fill ratio are the important levers; rim is optional separation.
- **Chair:** include node_247 in the clearance calculation. A fit based only on node_249 and a sacrum proxy cannot establish hoodie clearance.

If trimming the live key count, I would defer `neck_girth`, `chair_side_cm` and possibly `key_specular`. I would instead add **measurements**, not controls: per-hand fingertip/key-plane distances, elbow position relative to the torso, selected mouse component, and per-chair-part clearance.

## 2. Elbow fan: likely cause and first values

For a fan extending into the **upper arm/shoulder**, I would suspect the back pole plus the underlying skin weights first. The right elbow at `64°` is certainly too tight and likely aggravates the elbow portion, but flexion alone does not explain an upper-arm fan.

The pole is a clean diagnostic because it changes arm orientation without changing the shoulder-to-wrist distance, hence essentially without changing elbow interior angle.

### Isolation tests

1. **Pole test:** leave `elbow_min_deg = 0`, `hand_back_cm = 13`; set:
   - `elbow_pole_back = 0`
   - `elbow_pole_out = 0.45`

   If the fan moves or diminishes substantially, upper-arm placement is implicated.

2. **Reach test:** restore the old pole and change only:
   - `hand_back_cm = 5`

   This moves the wrists 8 cm forward. If the fan primarily follows elbow opening, reach/flexion is the larger contributor.

### First combined values

```text
hand_back_cm       = 5
hand_height_cm     = 4.5     // unchanged initially
elbow_min_deg      = 90
elbow_pole_back    = 0
elbow_pole_out     = 0.45
```

Keep `hand_span_cm = 20` initially. Do not start with a minimum of `100–110°`; that is more likely to make the slide fight keyboard placement.

The slide routine must report when it cannot satisfy both the angle and the keyboard target. After this feature, zero error to the **original** wrist target is no longer necessarily desirable; log requested target, effective target, slide and residual separately. If the fan remains at roughly `90–95°` with pole back zero, I would stop searching for a magic pole value and inspect/re-weight the hoodie around the deltoid, elbow and forearm. The lack of twist bones limits how much deformation quality the IK can recover.

## 3. Hands: orientation, fingers and mouse

### Typing orientation

The proposed orientation is a good first approximation for relaxed typing:

```text
hand_orient       = 1.0       // full-weight diagnostic
hand_yaw_in_deg   = 12
hand_pitch_deg    = 10
```

Use full weight first so the result is unambiguous; blend back to approximately `0.8` only if the wrist looks forced.

One important change: construct the target in the **keyboard/desk frame**, not in a leaned torso frame. Fingers should follow keyboard forward, pitch relative to the key plane, and the knuckle line should be parallel to that plane. Otherwise posture corrections can reintroduce a hand-angle error.

Use quaternion blending and mirror the inward-yaw sign per hand. Also unit-test the palm-side cross-product convention against a known palm-down pose; its sign depends on the direction of the across-hand vector and the frame handedness.

Leave `hand_height_cm = 4.5` for the first orientation test. Afterwards adjust height in approximately `0.25 cm` steps using fingertip-to-key-plane measurements. Do not require every fingertip to touch throughout a typing clip, but detect persistent hovering and keycap penetration. If the hands still overlap after orientation and position are correct, try `hand_span_cm = 24`; confirm in a non-webcam QA view before changing it solely because of camera projection.

### Finger bend

The `1.0 / 1.2 / 0.6` MCP/PIP/DIP split is reasonable. The important unspecified point is whether it is **additive** or an **absolute replacement** for the clip pose.

- If additive to the measured clip pose, start with `finger_bend_deg = 8`, keeping `finger_curl_deg = 0`. That puts the left hand approximately at MCP `24°`, PIP `38°`, and the right around MCP `24–28°`, PIP `23–34°`: shaped, but not yet a claw.
- If it replaces the clip flexion, start around `18–20°` instead.

Do not initially combine it with the existing guessed-axis curl.

### Mouse

From the supplied scan, it cannot be assumed that `mouse_scan` will find the mouse. If its triangles are merged into the desk mesh, component bounds cannot recover it; that requires separating the mouse asset or supplying an explicit replacement/reference.

For the scan:

- Require exactly one plausible candidate; otherwise no-op.
- Log its full component path, bounds and transform.
- Move it by the **same recorded keyboard-pack pull-back transform**, not by the current estimated hand error.
- Test `mouse_scan = 1` with `hand_on_mouse = 0` first. Enable the hand target only after the visible mouse and target coincide.

Use a short target/orientation transition, approximately `0.25 s`, and whitelist states where holding the mouse makes sense. “Every state except typing” is too broad without knowing the complete state set. Also, `hand_on_mouse` alone does not create a convincing grip; it will eventually need a mouse-specific wrist height, orientation and finger/thumb pose.

## 4. Posture split and starting values

A natural first correction is approximately **18° of actual extension**, split between pelvis and distributed spine extension, with only small clavicle and neck changes:

```text
pelvis_pitch_deg   = -10
typing_lean        = effective -14   // 8° more extension than today's effective -6
shoulder_drop_deg  = 3
shoulder_back_deg  = 2
neck_back_deg      = 5
```

Use the existing lean calibration to obtain that measured result; do not apply the `1.42` gain a second time. Leave `typing_head = 15` for the first posture comparison so gaze changes do not confound it. Afterwards, `10°` may look more natural if he remains excessively down-looking.

The shoulders should provide relaxation, not most of the correction. I would initially keep drop below about `4°`, retraction below `3°`, and neck back below `6–8°`.

There is a numerical acceptance issue: a `15–20°` correction applied to a measured `20–29°` incline produces roughly `0–14°`; it cannot guarantee `<=5°`. At the `29°` peak, at least `24°` of correction is required. If the first preset remains high, try `pelvis_pitch_deg = -12` and effective `typing_lean = -16`, then adjust in 2° measured steps. If achieving the peak requirement requires a rigid or arched pose, correct or replace the base clip rather than hiding the problem with more chin tuck.

Judge the final pelvis-to-head measurement, not the sum of commanded angles, and watch thigh/seat contact after the hip hinge.

## 5. Face lighting

Lock the v22 camera exposure before comparing these settings. Exact photometric results cannot be derived from `0.04 cd` alone; distance, spot distribution, material and exposure all matter.

Assuming positive side means **his right**, I would start with:

```text
key_side_cm       = -55       // his left
key_up_extra_cm   = 10        // about 35 cm above monitor centre in total
key_specular      = 1
key intensity     = 0.04 cd   // unchanged

fill_cd           = 0.010     // 25% of key cd
fill_side_cm      = 45        // his right
fill_up_cm        = 0
fill_temp_k       = 5000

// Add only after judging key/fill:
rim_cd            = 0.006     // 15% of key cd
rim_back_cm       = 60
rim_side_cm       = 30        // opposite the key
rim_up_cm         = 40
rim_temp_k        = 6500
```

Geometrically, this is aiming for:

- **Key:** near the monitor/webcam plane, roughly `50–60 cm` to his left and `35–45 cm` above eye level. If monitor centre is not near eye level, use the head-relative requirement rather than blindly retaining `key_up_extra_cm = 10`.
- **Fill:** near the frontal camera side, `35–45 cm` to his right and around eye level to `10 cm` above it.
- **Rim:** `50–60 cm` behind, about `30 cm` sideways and `40 cm` above the head, aimed at hair/shoulders rather than the lens.

The cd ratios are only starting ratios. At the head, a fill contribution around `20–30%` of key is a reasonable soft, still-dimensional webcam look. Keep specular at `1` unless highlights actually clip; reducing specular does not cure flat lighting.

A channel-1 rim is reasonable, but it is **not webcam-only**. Cam2 will see its effect on his back and hoodie, and cam2 is already the exposure-sensitive view. Start with rim off, add `0.006`, and be willing to leave it off. It should provide separation, not fix facial modelling.

## 6. Chair: which correction first?

For the reported flank/lower-back shell intersection:

1. `chair_side_cm = 0`
2. Try **lateral widening first**: `chair_scale = 1.08`
3. If lower-back/depth penetration remains, add `chair_back_extra_cm = 2`, then `4`

If node_247’s 38 cm half-extent is its half-width, `1.08` adds about **3 cm clearance per side**. If lateral clipping remains, try `1.12`; I would not jump directly toward `1.3`.

At `back_extra = 2` and `4`, the measured backrest gap becomes approximately `2.9` and `4.9 cm`, respectively.

Two implementation details matter:

- Make `chair_scale` **lateral-only**, about the common seat pivot. Scaling depth as well changes the fit and can create a second problem.
- Define the back-offset sign explicitly. Clearance requires moving the chair **away from his back**. I would define positive `chair_back_extra_cm` as opposite his facing; under a literal positive-along-facing convention, the trial offsets would need to be negative.

`chair_side_cm` is only useful for a measured asymmetric intersection; otherwise it merely moves penetration to the other flank.

The better long-term fit is to evaluate nodes 247, 248 and 249 against posed lower-back/flank hoodie clearance proxies and take the maximum required correction. Keep `chair_back_extra_cm` as an artistic trim after that fit. Tune the chair after posture, because sitting up changes the hoodie/chair overlap.

## 7. Defaults and instrumentation

I agree with **all visual defaults remaining “today”** in the build. Do not enable even an apparently obvious correction by default before the A/B session. At defaults, skip the code path entirely rather than merely applying identity transforms; in particular, do not create lights, scan/move components or introduce new transform-evaluation rounding.

Once a preset is approved, ship it as the live tuning preset, while retaining the off/identity code defaults for rollback.

The log should include:

- build, tuning-file hash/revision, state and clip time/phase;
- raw and effective values;
- left/right elbow before/after, slide, clamp/failure reason and wrist error;
- left/right hand-orientation error and fingertip contact measurements;
- measured pelvis-to-head incline;
- selected mouse component or “no unique candidate”;
- chair offsets/scale and clearance per part;
- effective light positions and intensities.

Log immediately when a tuning revision is applied as well as every 10 seconds. Clip phase is important: otherwise normal loop variation, such as `73–80°`, can be mistaken for a tuning effect.

Suggested session order: **fixed baseline → pole/reach isolation → posture → final hand placement/orientation → neck seam → chair → key/fill → rim → mouse**.

## 8. Mouth possibilities later

Nothing needs to be built now. Later options, in descending order of likely quality:

1. **Author viseme and expression morph targets** and re-import the head. Drive them from phoneme/viseme timestamps generated alongside the synthesized speech, rather than audio amplitude alone.
2. **Add a jaw bone and a small lip/corner rig**, with re-skinning; or move to a fuller facial rig/head asset if facial performance becomes a priority.
3. **Procedural mouth-region vertex deformation** or a separate lower-face/mouth rig. This can work for limited motion but is easy to make uncanny.
4. **Material/texture visemes or a separate stylized mouth element**. Useful for a stylized character, not a convincing realism solution.

Any genuinely opening mouth also needs suitable inner-mouth, teeth and tongue geometry. The existing head-emphasis layer can remain as speech-related body language, but it is not a substitute for lip sync.

## What v23 adopted

- **Defaults stay "today"** and every code path is skipped at its default (no light created, no component scanned or moved,
  no extra transform rounding). Tests compare the proxy pose and the character side with the v21 build bit for bit.
- **Reach first, `elbow_min_deg` as a guard.** The slide is published with the wrist residual to the slid target and the elbow's
  distance behind the shoulder (`v23_slide_*`, `v23_residual_*`, `v23_elbow_back_*`), and is capped (`SLIDE_MAX_CM`).
- **Hand orientation in the keyboard frame** (the character sends the keyboard's forward axis in component space; the body frame is
  only the fallback). This matters: his body faces ~17 deg off the monitor axis (`facingDot=0.957`). The palm-side convention is
  pinned by a test on a hand built palm-down.
- **Finger bend is additive** on the clip's flexion; start at 8 deg with `finger_curl_deg` 0.
- **Mouse:** a component is adopted only when it is the UNIQUE plausible candidate (else nothing, logged as "no unique candidate");
  its full path, bounds and transform are logged; it moves by the recorded keyboard pull-back. `hand_on_mouse` is whitelisted to
  `idle` and `reading` (the agent's `mouse` state keeps its own path) and needs a found mouse.
- **Chair:** new `chair_scale` (lateral-only, about the seated pelvis: positions and the actor scale on the local axis closest to his
  side); positive `chair_back_extra_cm` = away from his back. `chair_side_cm` kept for a measured asymmetric overlap only.
- **Thigh orientation** is preserved in component space (each thigh turned back by the inverse hinge about its own pivot), checked
  to 1e-9 in the tests.
- **Rim** default side moved opposite the key (`rim_side_cm` 30); `neck_girth` range narrowed to 0.9..1.2 (try 1.05, at most 1.10).
- **Instrumentation:** fingertip height above the key plane (mean/min per hand), Hips->Head incline, head ahead of the shoulders,
  clip time, tuning sequence, light positions (`SUB01_STREAMER_VISUAL_V23_LIGHTS` on change); the log fires at once on a tuning
  change and every 10 s.
- The live starting values and the session order are Kimi's (installer `RECOMMENDED`, README "v23").

## Not adopted (with the reason)

- **Per-chair-part hoodie clearance** against posed torso proxies: the level's chair parts are coarse boxes (node_247's bounds
  enclose the whole frame), so a bounds clearance would not measure the hoodie; the live keys plus cam2 frames decide instead.
- **A separate "key plane" frame for the hand pitch:** the keyboard is level in this level, so the horizontal plane is the key plane.
