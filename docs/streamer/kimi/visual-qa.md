# Kimi consultation (2026-10-23): visual QA bug ranking and the kept face-camera tuning (with frames)

Model kimi-k3.1-pro (250 s, 15471 completion units) with eight frames attached: the original face idle (`m-face-idle.jpg`), the FOV 100 kept-setting face idle/reading/typing/talking (`mx-face-*.jpg`), spectator reading, monitor typing and the free-camera side view (`ghost-side-left-eye.png`), all under `/tmp/sub01-share/qa/` on the pod; brief in `q-visual-qa.txt`. Advice to weigh: the QA folded it into `docs/streamer/VISUAL-QA-20261023.md` (section 4) and disagrees on two points there (the reacting "drop" is the loop seam, and FOV 95 is kept rather than 90-92 after measuring both).

## 1. Visual bugs, ranked by likely viewer impact

Temporal defects below are based on your receipts; still frames alone cannot establish their frequency.

1. **Hoodie chest and collar — broken-looking torso in nearly every face view.** The white chair is visible through a large chest opening, with ragged edges and a damaged-looking collar. **Likely cause:** asset/mesh—missing or back-facing polygons, bad skinning, or a material mask—not simply chair intersection. **Fix:** inspect the neutral-pose mesh in the DCC/Persona, repair faces/normals/weights/material, and reimport. Do not hide it with lighting or framing.

2. **Chair/body relationship — backrest and frame penetrate or protrude through him** in spectator/side views; idle also remains approximately 25° hinged forward. **Likely cause:** chair/seat placement plus the authored seated clips. It is not corrected by `seat_back`, and the present `posture_lean` knob is irrelevant anatomically. **Fix:** realign chair/seat and character root, then correct the clip and add properly mapped spine flexion. Preserve intentional seat contact.

3. **Head/face during typing — sustained crown-only framing, no usable facial performance.** **Likely cause:** excessive neck/head flexion in the typing clip, compounded by broken gaze pitch. **Fix:** reauthor the clip or add an anatomically correct additive neck/head correction and monitor gaze. Tilting the webcam is the wrong remedy.

4. **Procedural motion/reacting — nod is a shake, “pitch” twists/yaws, and reacting has a one-frame drop.** **Likely cause:** native bone-axis mapping plus an unblended state entry. **Fix:** quaternion-based anatomical controls, correct per-bone spaces, and a **150–250 ms** entry blend. Disable broken pitch-driven cadence/nod until repaired.

5. **Right hand/mouse state — he pantomimes mouse use from the keyboard.** **Likely cause:** state/clip and missing hand IK or incorrect prop placement. **Fix:** dedicated mouse pose with hand IK; adjust the mouse/keyboard transforms if necessary.

6. **Face lighting — dark face and crushed black hair/hoodie against bright walls and screen.** **Likely cause:** lighting/exposure balance. **Fix:** broad camera-side key/fill, initially approximately **+1 EV on the cheeks**, then reduce excessive background contribution if needed.

7. **Face camera — excessive headroom and selection-dependent reframing.** **Likely cause:** wide FOV and re-solving aim from a noisy one-second head mean. **Fix:** framing adjustment plus a stored calibration; do not re-aim merely because a camera was selected.

I agree with the controlled axis diagnosis and the landmark arithmetic, and withdraw my 72 cm distance assumption. My disagreements are classification and shipping bar: the chest hole is separate from chair penetration, and the kept framing is a reasonable stop-gap, not final.

## 2. Face-camera judgement

**Head ~30%, eyes ~41%, top margin ~22% is watchable**, with a good eye line and acceptable size for a wide desk/just-chatting shot. However, 22% is visibly generous headroom and FOV 100 reads wider than a typical monitor-webcam look.

Priority should be:

1. Complete hair, unobstructed face, and stable framing.
2. Eyes approximately **35–42%** down.
3. Natural head size.
4. Fixed top-margin and old head-size targets last.

Retire the incompatible **8–12% margin** and **24–27% hair-to-chin head** combination. Also consistently call the QA measurement “head,” not “face.”

I would test **FOV 92, then 90**, without moving the camera. Approximate projection from the current landmarks gives **35–37% head, 39–40% eyes, and 17–18% top margin**. Keep **seat 36, side −6, up 20, forward 2**, and initially retain aim and head yaw; trim aim only **1–2°** after measurement. The face-to-lens distance is approximately **51–57 cm**, so there is no reason to spend seat travel chasing the old distance. Calibrate aim once over a complete loop and store it.

## 3. Yaw stop-gap and native axis repair

Keeping **`posture_head +14` as yaw** is acceptable temporarily: rename it, document it, clamp it to the shot’s requirement, and blend activation. It must not be treated as evidence that head pitch works.

Forward spine bend and nod must rotate about the **ear-to-ear/shoulder-to-shoulder anatomical axis**, not an assumed Euler channel. On the usual UE Mixamo orientation consistent with your finding, this is commonly **bone-local X—UE `Roll`**—while local Y is the long/twist axis. FBX import orientation is authoritative, so verify rather than blindly swapping channels.

For each bone, with reference rotation \(Q\) mapping local to component space and component-space right vector \(R\), compute:

`a_local = normalize(inverse(Q) * R)`

Apply an additive bone-space quaternion about `a_local`: distribute lean over the spine chain; apply nod at neck/head; determine sign by which direction lowers the nose. Verify at a fixed animation time: **+5° nod** must produce **5 ± 0.5° downward facial pitch, <1° yaw change, and <1° long-axis twist**. A commanded **+10° total lean** must change pelvis-to-head inclination by **10 ± 1°**, with pelvis movement **<1 mm** and lateral head drift **<5 mm**.

## 4. Next-build acceptance checks

1. **Mesh/contact:** two complete loops of every state in face, spectator, and side views: **zero visible chest holes, backface failures, or chair-through-body frames**.
2. **Camera/performance:** sample **40 s/state at 5 Hz**. In at least **95%** of idle/reading/talking samples: head **32–38%**, eyes **37–42%**, complete hair, and no monitor bezel. Typing must show eyes and mouth in **≥95%** of samples. Twenty same-state camera reselections must change aim by **<0.2°** and eye line by **<1% of frame height**.
3. **Motion/function:** pass the numerical axis tests above; reacting blends over **150–250 ms** with no adjacent-frame head displacement **>10 mm**; right palm remains within **20 mm** of the mouse for **≥95%** of mouse-state frames.
