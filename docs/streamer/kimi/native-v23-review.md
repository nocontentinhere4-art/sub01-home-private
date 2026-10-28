# Kimi pre-commit review (2026-10-24): native v23, live-tunable look corrections

Question: `q-native-v23-review.txt` (same folder). Model `kimi-k3.1-pro`. Attached: the C++ the installer generated on the v21
sources (unified diff), a 13k-character excerpt of `install_v23.py` (the full installer timed out at 900 s twice) and the v23 test
section. Asked for: math and sign conventions, runtime safety (NaN, pops on live changes, threads), the mouse component scan, the
extra lights with Lumen, merge safety with v22, vacuous tests. The answer came on the fourth attempt (two timeouts, HTTP 429s).

## Answer (verbatim)

**No blocking findings** for the default-off, bit-identical path. The normal-case sign conventions are correct: hip hinge/thigh counter-rotation, clavicle drop and retract, chin tuck, `Roll * Aim`, palm handedness, finger-bend axis, and the law-of-cosines reach calculation. I also see no new proxy/game-thread race: scene components remain on the character tick, while `Evaluate` consumes copied proxy values and touches only proxy/pose state.

The live path and tests do have these findings:

1. **`hand_orient` uses the wrong ease rate — 2/s instead of the specified 1/s.**  
   **File/function:** `Sub01HomeLab.cpp`, `ASub01HomeCharacter::UpdateStreamerVisualV23`, `StreamerVisualV23Shown[7]`.  
   It is a 0..1 weight, but uses:
   ```cpp
   Ease(StreamerVisualV23Shown[7],V2?StreamerVisualV23HandOrient:0.f,2.f);
   ```
   Thus 0→1 takes **0.5 s**, not 1 s. Change the rate to `1.f`. Add a timing test; with `Dt=0.1`, the value should be 0.5 after five ticks and exactly 1 after ten.

2. **The elbow-target slide has a discontinuity when the target is behind the slide direction.**  
   **File/function:** `Sub01HomeHands.cpp`, `StreamerV23Target`.  
   The normal forward-target case is continuous and correct. However, for `Bq = Dot(Ahead,V) < 0`, the selected root does not approach zero as `Cq` approaches zero from below. For example, with `Ahead=+Y`, `V=(0,-10,0)`, `Bq=-10`: the root approaches **20 cm**, so the cap makes the slide jump **0→15 cm** when the guard engages.  
   **Fix:** explicitly handle `Bq<0`: either decline the slide and publish a “guard blocked” condition, or slew-limit the applied slide rather than taking the far root immediately. Also clamp the final slide defensively to `[0,15]`. Add tests for the 15 cm cap and a behind-shoulder target; neither is currently covered.

3. **Several live changes still produce instantaneous visible cuts.**  
   **File/functions:** `UpdateStreamerVisualV23Lights` and the mouse section of `UpdateStreamerVisualV23`.  
   The listed eases do not cover:
   - `key_side_cm` / `key_up_extra_cm`: the recommended `key_side_cm=-55` moves the key **55 cm in one tick**.
   - Fill/rim intensity and placement: lights appear, disappear, or relocate immediately.
   - Mouse adoption/release: the component jumps by the full current `StreamerVisualDeskPropDelta` on adoption and jumps back on release.

   If these are deliberate tuning cuts, document that exception. Otherwise add shown/eased values for light offsets and intensities, and ease the mouse’s adoption offset. The pose and chair eases themselves look continuous.

4. **Mouse adoption is unique, but not sufficiently constrained to a visible, safely movable mouse; mobility is not restored.**  
   **File/functions:** `StreamerVisualV23MouseCandidate`, `AdoptStreamerVisualV23Mouse`, `ScanStreamerVisualV23Mouse`.  
   A hidden or collision-only leaf primitive can pass the bounds test. A simulated physics component can also be adopted, with its transform subsequently fighting physics. On `mouse_scan=0`, position is restored but the component remains **Movable**, permanently changing its rendering/physics classification.  
   **Fix:** for this known RGB mouse, prefer a registered, visible `UStaticMeshComponent` with a mesh; reject simulating physics or handle it explicitly. Save the original mobility and restore it with the original transform on release. If an adopted component disappears, permit a fresh scan rather than leaving the latch set forever.

5. **Neck girth is a dominant-local-axis approximation, not a general scale across the Neck→child axis.**  
   **File/function:** `Sub01HomeHands.cpp`, `ApplyStreamerV23Head`.  
   `Long` is selected from the largest component of `Along`. That is correct when Neck→Head is essentially aligned with a local axis, as in the synthetic test body. With a diagonal offset, scaling the other two local axes also changes length along the actual Neck→Head direction.  
   **Fix:** on the real skeleton, verify and log that the dominant component is sufficiently aligned—otherwise skip this experimental correction or implement a basis-aware solution. Add a diagonal-offset test. The actual asset’s Neck-local offset cannot be determined from the supplied material.

6. **The rim is only “opposite the key” for the recommended values, and Lumen cost/leakage remains unvalidated.**  
   **File/function:** `UpdateStreamerVisualV23Lights`.  
   `rim_side_cm` is used verbatim; it does not track the sign of `StreamerVisualFaceSideCm + key_side_cm`. The recommended `-55/+30` arrangement is opposite only while the total key side remains negative. Either derive the rim sign from the actual key side or document it as an independent manual placement.  
   Cost is bounded to **two additional movable spotlights with no shadow maps**, but exact GPU/Lumen milliseconds cannot be inferred from this diff. Active lights move whenever `LightAim` changes, causing continuing dynamic-light updates; no shadows also permits light leaking, and lighting channel 1 should not be assumed to make the complete direct-plus-indirect Lumen result body-only. Validate on the pod with GPU/Lumen captures. Prefer stable light positions with aim-only tracking if small head movements make the lighting swim.

7. **The production v21→v22→v23 merge is not tested.**  
   **File:** `tests_v23_section.py`, `_stack_to_v21`, `v23_patched`, and `test_v23_text`.  
   Every v23 fixture installs directly onto v21. Therefore the two shared insertion points and the actual post-v22 anchors are not exercised. Moreover, the textual assertions that cam2/key-light functions equal their **v21** versions are not suitable for a fixture whose correct base includes v22.  
   **Fix:** add a v21→v22→v23 fixture, then verify installation, both layers’ tuning/receipt fields, unchanged bridge hashes, and the v22 runtime driver. Compare protected functions against the actual base stack. I see no additional obvious textual collision in the supplied edits.

8. **Several tests bypass the behavior they appear to cover.**
   - The mouse test calls `AdoptStreamerVisualV23Mouse` directly; it never runs `ScanStreamerVisualV23Mouse`, so zero/one/two-candidate adoption and actor/desk-prop exclusion are untested.
   - Proxy correction tests assign proxy fields directly. There is no end-to-end tuning → character ease → anim instance → `PreUpdate` → `Evaluate` → publication test to catch a miswired copy.
   - The immediate/10-second logging sequence, state/clip-time/sequence contents, and final reset behavior are not tested.
   - Missing numeric cases include the elbow cap and degenerate bones, near-180° hand aim/roll, non-axis-aligned neck girth, and restoration of the key transform after `key_side_cm`/`key_up_extra_cm` return to zero.

The chair-extra compensation in the backrest fit has the correct sign, and the logging condition itself appears to implement immediate-on-new-sequence plus 10-second logging correctly.

## What v23 did with each finding

1. Applied. `hand_orient` eases at 1/s (`WEIGHT_RATE`). Character test: 0.5 after five ticks of 0.1 s, exactly 1 after ten.
2. Applied, "decline" variant. When the target lies behind the shoulder along the keyboard axis (`Bq < 0`), `StreamerV23Target`
   leaves it as sent and publishes slide -1 (`v23_slide_*`, the log). The slide is clamped to [0, 15]. Proxy tests: the cap
   (150 deg would need about 25 cm, the slide stops at 15) and a target behind the shoulder (-1, the other hand still slides).
3. Applied; nothing jumps any more except `key_specular`, which is documented.
   - Key offsets glide at 30 cm/s, also on the way back. At 0/0 the v21 key update places the key that same tick; a test checks
     the exact v21 location after a v1 event.
   - Fill and rim intensity glide at 0.02 cd/s. A light rises from 0 at its target position (placed there when it first
     appears); later placement changes glide at 30 cm/s.
   - The mouse glides at 30 cm/s, both on adoption and on release.
4. Applied.
   - **Candidates:** registered, visible, not simulating physics, a static-mesh component with a mesh. The earlier rules still
     hold: a small leaf in the mouse zone, not part of the desk packs.
   - **Adoption and release:** adoption saves the original mobility. `mouse_scan` 0 glides the mouse home, sets it exactly to
     its origin, restores the mobility and releases it.
   - **A vanished component:** if the adopted component's weak pointer goes invalid, it is released and a new scan is allowed.
   - **Tests:** each filter; the real scan over an opt-in stub world with 0, 2 and 1 plausible components; his own actor and a
     desk-prop actor skipped, proved by the candidate count; the glide out and back; the mobility restore; the vanish-and-rescan
     path.
5. Applied. The girth computes the alignment of the Neck->child offset with its long local axis, publishes it
   (`v23_neck_axis_align`, `neckAxisAlign=` in the log) and is skipped below 0.95 (`NECK_AXIS_MIN`). Test: a child offset at
   45 deg gives 0.707 and leaves the Neck and Head untouched. The real skeleton's value shows up in the first live receipt.
6. Documented, not derived. `rim_side_cm` is an independent placement (positive = his right). Lumen cost and leaking are checked
   on the pod during the live session: the rim is optional (session step 9) and stays off if cam2 suffers. The rim follows
   `LightAim` like the key; whether the lighting swims is judged on frames.
7. Applied by pinning v23 to v22 (commit 27670bd).
   - Every v23 fixture is v21 -> v22 -> v23, and the installer refuses without the v22 marker.
   - The protected functions and v22's own block are compared with the real v21+v22 output.
   - The bit-identical default tests compare the v22 build with the v23 build.
   - v22's monitor-feed and cam2-exposure drivers run on the v23 output.
8. Mostly applied.
   - **Scan:** covered as in 4.
   - **Hand-over:** a new test sets the anim instance's v23 fields. `PreUpdate` copies them and clears last frame's
     measurements, then `Evaluate` applies them. The character-side easing into those fields is tested separately.
   - **Not covered, publication:** `NativePostEvaluateAnimation` cannot run under the stub (the stub cannot return the game-thread
     proxy). The publish line is checked as text.
   - **Log state:** at once on a tuning change, every 10 s, one last line when every key is back at its default, then quiet;
     the lights line.
   - **Numeric cases:** the elbow cap, the near-180 deg hand aim (finite pose, same result), the neck girth on a diagonal
     offset, the key restored after its offsets.
   - **Not covered, degenerate bones:** missing bones and zero vectors return early through the existing guards; there is no
     separate test.

## Follow-up: review of the delta (after the fixes above, on v22)

Question: `q-native-v23-review2.txt` (same folder). Attached: the generated C++ before and after the fixes, on the v22 sources
(about 30k characters), and the test-file diff (about 32k characters). The first attempt ran out of its 30k-token budget while
reasoning and gave no answer; the second attempt answered.

### Answer (verbatim)

**No blocking findings on the evidence in the delta.** Three non-blocking notes:

1. **The behind-shoulder guard has a continuity edge.** For `Cq < 0`, as `Bq → 0⁺`, the requested slide approaches `min(15, sqrt(-Cq))`; as `Bq → 0⁻`, the guard declines and the effective target returns to the unslid target. Thus a continuous target crossing `Bq == 0` can jump the IK goal by as much as **15 cm**. The test covers only a fixed behind-shoulder target. This is not blocking if normal hand-target paths cannot make that crossing; otherwise ease the effective slide/target through the transition.

2. **The mobility-save test is partly vacuous.** The adopted mouse starts as `Static == 0`, which is also `StreamerVisualV23MouseMobility`’s initializer. Removing the save in `AdoptStreamerVisualV23Mouse` would therefore still pass the adoption and restoration checks. Start the candidate as `Stationary`, then assert `Movable` while adopted and `Stationary` after release.

3. **The key’s “glide back” behavior is not regression-tested.** The v1-event checks inspect the first tick only for rim/specular and then check the key after 60 ticks. An instantaneous key-offset reset would also pass. After the first v1 tick, assert the expected remaining offsets—normally `27 cm` side and `7 cm` up with the test’s 0.1 s ticks.

Otherwise, the root/clamp math, neck-axis ratio, light/mouse stepping, weak-pointer reset/rescan, and mobility restoration order look correct. The listed UE 5.8 component APIs are being used appropriately on the game thread.

### What v23 did with the three notes

1. Applied. Within `SLIDE_RAMP_CM` (5 cm) ahead of the shoulder line, the slide is multiplied by Bq/5. The applied slide is 0
   at the line and grows continuously up to the capped root. Behind the line the guard still declines (published -1, slide 0).
   Normal keyboard targets sit about 20 cm ahead of the shoulder, so their factor is 1. Proxy test: a target 1 cm ahead with
   `elbow_min_deg` 95 slides exactly 15 x 1/5 = 3 cm.
2. Applied. The test mouse starts Stationary. The test asserts Movable while it is adopted, Stationary as the saved value, and
   Stationary again after the release.
3. Applied. After the first v1 tick, the test asserts the key at 27 cm to the side and 7 cm up (one 3 cm glide step back).

Mutation checks: removing the ramp, the mobility save or the key glide each fails its test. The whole test file passes:
133 tests.

## Final check before the commit

Question: `q-native-v23-review3.txt` (same folder): the three applied notes, with the new slide line inline. Answer (verbatim):

ok
