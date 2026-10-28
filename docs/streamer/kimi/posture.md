# Kimi consultation (2026-10-23): posture, chair, hands, webcam (with frames)

Model kimi-k3.1-pro with three frames attached (webcam reading, webcam talking, side view); brief in `q-posture.txt`. Advice to weigh; the tuning values are being tested live by the visual QA worker and the hands/chair recipe goes to the native worker.

These are starting calibration values; exact bone angles and pixel-to-centimetre conversions cannot be recovered from three uncalibrated renders. World-space measurements override the knob values.

## 1. What is wrong

- **Image 1:** He is looming into the lens, shoulders forward and neck craned; this is not relaxed sitting. The face is roughly **half the frame height**, not a quarter, the hair is cropped, and the head sits right of centre. Almost no chair, desk, shoulders or useful room context is visible. At 61 cm, the close perspective also overemphasises the face.
- **Image 2:** It is effectively the same bad shot with a mouth shape. Talking has not changed the posture or framing, and the head/gaze still does not feel settled naturally on the lens. No hand performance can be judged because the arms are outside the frame.
- **Image 3:** The **−10° lean has not produced an upright world-space torso**. He reads as perched and reaching toward the desk, not supported by the chair. Lumbar/backrest contact is not demonstrated; the chair and body do not read as one seated contact chain. The visible arm is reaching rather than resting with a relaxed 90° elbow. Only one hand is visible, so two-hand keyboard contact is unproven; the mouse has no credible hand/scroll pose. The cropped head also prevents checking eye-to-monitor alignment.

## 2. Initial targets

Assuming the current animation stack and a roughly 27-inch, 16:9 monitor:

| Control | Target |
|---|---:|
| `seat_back_cm` | **30**; tune 28–32 |
| `posture_lean_deg` | **−16° total**, initially −8° Spine1 / −8° Spine2 |
| `posture_head_deg` | **+2°**, with procedural sway limited to about ±2° |
| Webcam up / forward / side | **+20 / +2 / 0 cm** from monitor centre |
| Aim | **12° downward** from horizontal |
| FOV | **95° horizontal** at 16:9; approximately **63° vertical** |
| Expected head-to-camera distance | **About 72 cm**, acceptable working range **68–76 cm** |

“Forward” means toward the room; the lens remains in front of the glass. For another monitor size, set webcam up to approximately **monitor half-height + 2–3 cm**.

Do **not** reduce seat pull-back merely to fix the arms—that tightens the webcam again. Move/re-dock the keyboard and mouse and solve the arms. Finish with the trunk approximately vertical to **5° reclined**, shoulders down, and ears over shoulders rather than ahead of them.

At 72 cm, 95° horizontal FOV gives about **88 cm of vertical coverage**, making a 22 cm face approximately 25% of frame height. Trim FOV between **90–100°** to hold the face at **24–27%**. Wider than 100° adds context but visibly bends walls/chair edges and stretches a face placed off-centre.

## 3. Hands and the third clip

Use the **typing loop** as the desk-work base; reserve the reading loop for reading.

- Apply breathing/posture first, then world-space hand IK, using two-bone arm IK with elbow poles pointing down/back and slightly outward.
- Parent targets to the actual props. For typing, place wrist targets over the two home-row hand positions, approximately **18–22 cm apart**. Target **85–100° elbows**, forearms horizontal to 10° downward, and wrist joints **4–5 cm above the desk**, with neutral wrists and less than 10° extension.
- Use a typing hand pose: approximately **20–35° proximal** and **25–40° middle-joint finger curl**, then adjust fingertips to within **1 cm** of key contact. Do not merely lay flat palms across the keyboard.
- For scrolling, keep the left hand planted and blend the right wrist to the mouse over **0.25 seconds**, using a **4 cm-high arc** rather than dragging it through the desk. The mouse should move with the keyboard during seat adjustments. Use a palm-on-mouse pose, thumb on its side, index/middle fingers on the buttons, and a **12–18° finger pulse** for each wheel scroll.

If recording a third clip, make it **24 seconds**, with identical start/end poses: **0–4 s** supported neutral idle; **4–10 s** two-handed typing; **10–12 s** right hand to mouse; **12–17 s** three scrolls plus one click; **17–19 s** return to home row; **19–24 s** quiet talking/idle. Pelvis and back remain planted, and the left hand does not follow the right.

## 4. Chair and verification

Slide the pelvis back: sacrum **0–2 cm from the lumbar/backrest surface**, pelvis over the rear half of the seat, with **4–6 cm clearance behind the knees**. Lumbar contact is mandatory; upper-back contact can be light. Avoid both a visible gap and hoodie/backrest interpenetration.

Set key tops **0–2 cm below seated elbow height**; armrests may support the forearms but must not lift the shoulders. For a 73 cm desk and average proportions, **45–47 cm seat-pan height** is only a starting check—foot and knee fit take priority.

Verify in an uncropped orthographic side view with a 10 cm debug ruler. If `s` is pixels/cm, require backrest gap **≤2s px**, penetration **<1s px**, and fingertip/key error **≤1s px**. Also measure the **85–100° elbow**, **60–80 cm eye-to-screen distance**, and monitor top within **±3 cm of eye height**. The current perspective crop cannot prove these.

## 5. Three proof frames

1. **Front webcam:** complete hair with **8–12% top margin**, face **24–27% of frame height**, eyes roughly **35–42% down**, centred face, relaxed shoulders, chair back and room visible on both sides.
2. **Side:** full body/chair/desk, showing pelvis depth, backrest contact, seat clearance, elbow angle, wrist height, screen distance and eye/monitor alignment.
3. **Over-the-shoulder:** keyboard centred, left hand contacting home row, right hand correctly wrapping the mouse during scrolling, no finger/desk penetration, and no torso displacement caused by the reach.