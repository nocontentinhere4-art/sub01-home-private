# Live visual tuning on v23, frame reviews with Kimi (2026-10-24, coordinator)

Frames in `docs/streamer/photos/20261024-tuning/`. Three rounds; questions verbatim, answers verbatim.

## Round 1: question

```
Live visual tuning of SUB-01 (native v23 build, keys set live through the tuning file). Frame review and advice, please.

Image k-elbow.jpg (cam2, the camera behind-left of him), three panels left to right:
1. t0: v23 defaults (v22 cam2 exposure: auto -1 EV; the walls are no longer blown out).
2. t2: elbow keys: hand_back_cm=5, elbow_min_deg=90, elbow_pole_back=0, elbow_pole_out=0.45. Receipt: wrist slide right 5.0 cm,
   elbow_back_left -13.8 cm, elbow_back_right -9.5 cm (negative = elbow AHEAD of the shoulder), torso incline 22 deg,
   head ahead of shoulders 3.3 cm, fingertips below key tops (left -3.4 cm, right -9.1 cm).
3. diagnostic hide_slot=1: hiding material slot 1 (PortableOriginalHoodiePalette_KnitRight) hides the whole hoodie body,
   arms and legs, so the stretched "fan" belongs to that main body section. Slot 7 (a tripo material) changes nothing
   visible. Slots: 0 KnitLeft, 1 KnitRight, 2 skin, 3 nails, 4 hood_lining, 5 hood_patches, 6 feet, 7 tripo, 8 owner_head.
   Also visible in panel 3: his hands type on a keyboard tray at lap height in front of the desk edge (the keyboard
   follows the chair since v21), not on the desk keyboard.

The fan: a sheet of stretched hoodie polygons from his right lower back / hem to the right forearm/elbow. The elbow keys
did not change it. My hypothesis: hem/side vertices of the hoodie are skinned to the right forearm or hand; any pose
where the forearm is far from the hip stretches them. No mesh/weight edit is possible live; only bone poses.

Image k-webcam.jpg (frontal webcam, t0): neck/hood seam, hands overlapping, hunched.

Questions:
a) Is the skinning hypothesis plausible from the frames? What pose change would most likely shrink the fan (hands closer
   to the hip / higher / lower, elbow out or back, upper-arm twist), given these keys: hand_back_cm, hand_height_cm,
   hand_span_cm, elbow_pole_back, elbow_pole_out (-0.5..1.5), elbow_min_deg, shoulder_drop_deg, shoulder_back_deg,
   pelvis_pitch_deg, typing_lean_deg? Give 2-3 concrete settings to try, in order.
b) If no pose fixes it: is it acceptable to frame cam2 so the fan is hidden (camera from the other side, or higher), or
   should the cam2 view avoid his right side altogether? Keys for cam2 placement exist only at build time.
c) Order for the remaining steps (posture, hands, neck seam, chair, key/fill light) given what you see.
```

## Round 1: Kimi (kimi-k3.1-pro)

### a) Fan / skinning

**Plausible, but not proven.** The slot test localizes the fan to the main slot-1 mesh; it does not identify the responsible bone. Also, t2 was not a strong “compact arm” test: the right elbow was still **9.5 cm ahead** of the shoulder.

The most promising direction is **elbow back/in and wrist back toward the hip**, initially slightly downward toward an arms-down pose. At the same frame, keeping torso, pelvis, shoulders and hand span fixed, try:

1. **Elbow-only A/B:**  
   `hand_back_cm=5`, `elbow_min_deg=90`, `elbow_pole_back=1.2`, `elbow_pole_out=0.0`  
   Watch whether `elbow_back_right` moves from `-9.5` toward `0`, and whether the fan follows.

2. **Bring the wrists toward the hips:**  
   `hand_back_cm=20`, `hand_height_cm=-5`, `elbow_min_deg=100`, `elbow_pole_back=1.0`, `elbow_pole_out=0.0`

3. **Bracket the uncertain vertical direction:**  
   Same as 2, but `hand_height_cm=+5`.

Use whichever produces the smaller fan, then back off toward a usable pose. The images cannot establish whether up or down is ultimately better. **Upper-arm twist is a later test**, not the first choice; it may only rotate the sleeve and increase shearing. If none of these produces a clear, repeatable reduction, stop spending time on pose-only fixes.

### b) Hiding it with cam2

**Yes, as a temporary fixed-shot workaround—not as the asset fix.** Try a **higher/tighter version of the current rear-left view**, with the torso occluding the hem-to-elbow sheet, before changing sides. A rear-right view would more likely expose the affected side.

There is no need for a blanket “never show his right side” rule: the requirement is that the fan remain occluded or out of frame **through the whole shot’s motion**, not merely in one still. If that cannot be achieved reliably, use a left/rear or tighter shot until the weights can be repaired. Exact camera coordinates cannot be derived from these images; do the live pose tests before spending the build-time cam2 change.

### c) Remaining order

**Lock chair/keyboard placement → posture → hands → neck seam → key/fill.** Chair cosmetics can wait, but its placement cannot: the tray follows the chair, so hand tuning before that is wasted work.

- **Posture:** reduce the measured **22° incline to roughly 8–12°**, bringing the head back over the shoulders.
- **Hands:** separate the overlapping hands and solve them against the intended desk keyboard. Do not simply raise both by `9.1 cm`: that would put the right fingertips at key height but leave the left **5.7 cm above** it.
- **Neck seam:** address after the final torso/head pose, since posture changes the hood/neck relationship.
- **Lighting:** last; retain the improved v23 wall exposure and use key/fill to recover hoodie/face separation, not to conceal geometry.

## Round 2: question

```
Follow-up on the live visual tuning (your previous answer: elbow back/in and wrists toward the hips; posture to 8-12 deg).
Image k-tune2.jpg, three rows (left cam2 from behind-left, right the frontal webcam crop):
Row 1 t0: v23 defaults, typing (incline 22 deg, head 3.3 cm ahead, stretched hoodie fan on cam2).
Row 2 p2: typing with hand_back_cm=12 hand_height_cm=5 elbow_min_deg=100 elbow_pole_back=1.0 elbow_pole_out=0
          pelvis_pitch_deg=-6 typing_lean_deg=-10 shoulder_drop_deg=3 shoulder_back_deg=2 neck_back_deg=5
          hand_orient=1 hand_yaw_in_deg=12 hand_pitch_deg=10 finger_bend_deg=8 finger_curl_deg=0
          key_side_cm=-55 key_up_extra_cm=10 fill_cd=0.01 fill_side_cm=45 fill_up_cm=0 fill_temp_k=5000.
          Receipt: incline 10.8 deg, head 1.6 cm ahead, fingertips 4.2-4.6 cm below key tops, hand orientation error 0.
Row 3 p3r: same plus posture_lean_deg=-10, state "reading": incline 9.6 deg, head 0.0 cm ahead.
Observations: the cam2 fan is gone in row 3 and mostly gone in row 2 (a faint stretch remains near his right mid-back
while typing); the neck seam is much smaller; face lit by key+fill. The hands sit near the tray but the tips are ~4.5 cm
below the key tops. A small white sphere appears near the desk front-left in row 2 (light gizmo? prop?).
Questions:
a) Do rows 2-3 look better and more natural than row 1? Any regression (stiffness, uncanny posture, lighting)?
b) Keep these values as the new defaults for the session? Which 1-3 changes next (hand height to reach the keys,
   neck_share 0 for the seam, chair_scale/back for the chair overlap, fill/key level, rim)?
c) Anything that would make him look less real that I should check in motion (not visible in stills)?
```

## Round 2: Kimi (kimi-k3.1-pro)

### a) Better, but not finished

Yes. **p2 is the better typing pose; p3r is the better reading pose.** The 10.8°/9.6° inclines are within the intended range, the head is less forward, the hoodie silhouette is substantially cleaner, and the face is easier to read.

Remaining issues:

- p3r is slightly **too symmetrical and posed**; do not make him more upright.
- The hands still are not convincingly using the keyboard. `hand orientation error = 0` confirms target matching, not key contact or natural wrist posture.
- The faint right-mid-back stretch and chair overlap remain.
- Lighting is improved, though slightly flat against the very dark hoodie—not enough to justify another lighting change yet.
- The white sphere is an unwanted artifact unless it is intentional set dressing. Its nature cannot be determined from the still.

### b) Defaults and next changes

**Save these as a provisional session checkpoint:** p2 for typing, with the p3r delta applied only to reading. Keep a rollback; do not call them final while contact and intersections are wrong.

Next, in order:

1. **Fix fingertip height.** Raise the hand targets by the measured **4.5 cm**: try  
   `hand_height_cm: 5 → 9.5`  
   Assuming approximately linear response, that puts the tips roughly **1 mm below to 3 mm above** the key tops. Re-measure rather than assuming; aim for approximately **0–5 mm above in neutral**, with actual finger travel during strikes. Recheck wrist angle and the residual back-cloth stretch afterward.

2. **Fix the chair without changing posture.** Prefer a backrest offset over whole-chair scaling: start by moving it **2 cm away from the torso**, then iterate in **1 cm** steps while checking seat contact and both poses. A reliable scale percentage cannot be derived from these images.

3. **Identify/remove the sphere from capture.** Check the new fill light’s debug/billboard drawing and the scene Outliner. If it is a gizmo, disable its rendering in the capture path without disabling the illumination.

Leave **key/fill unchanged and add no rim yet**. Do not blindly adopt `neck_share=0`: it is not inherently a seam fix and may alter head pitch or stiffen the neck. A/B it only if the seam remains visible in motion.

### c) What to inspect in motion

Capture a typing → reading → typing sequence at 60 fps and inspect slowly:

- **IK continuity:** elbow-pole or minimum-angle clamps engaging, wrist-orientation flips, finger pops, and one-frame target jumps during state blends.
- **Contact:** fingers skating, hovering or penetrating keys; rigid block-like hand motion; implausibly regular typing; keystrokes not matching key travel/clicks.
- **Deformation/collision:** the right-back hoodie fan, neck seam, chair penetration and desk/tray intersections throughout the motion—not just at endpoints.
- **Lifeless motion:** torso, neck and head moving as one rigid piece; frozen gaze; absent or periodic blinks/saccades; perfectly periodic breathing and weight shifts; and, while speaking, delayed lip-sync or insufficient jaw/tongue movement.

## Round 3: question

```
Pre-commit frame review of the live tuning checkpoint (your last advice applied).
Image k-tune3.jpg, three rows (left cam2, right webcam crop): row 1 = t0 (v23 defaults, typing); row 2 = p5 typing;
row 3 = p6r reading. Changes since your last review: hand_height_cm 5 -> 9.5 (fingertips now +0.3/-0.3 cm vs key tops,
were -4.5), chair_back_extra_cm=2 (chair moved 2 cm away from his back), typing_lean_deg -10 -> -4 because the raised
hands brought the typing incline to -2 deg (now 8.3 deg typing, 8.6 deg reading; head 0.5-0.8 cm ahead).
The white sphere left of the speaker is a globe desk lamp (it stays with the fill light off): set dressing, not an artifact.
Full value set (tuning file): hand_back_cm=12 hand_height_cm=9.5 elbow_min_deg=100 elbow_pole_back=1.0 elbow_pole_out=0
pelvis_pitch_deg=-6 typing_lean_deg=-4 posture_lean_deg=-10 shoulder_drop_deg=3 shoulder_back_deg=2 neck_back_deg=5
hand_orient=1 hand_yaw_in_deg=12 hand_pitch_deg=10 finger_bend_deg=8 finger_curl_deg=0 key_side_cm=-55
key_up_extra_cm=10 fill_cd=0.01 fill_side_cm=45 fill_up_cm=0 fill_temp_k=5000 chair_back_extra_cm=2.
I want to commit these values as the documented session checkpoint (docs + before/after frames), keep rollback to the
v23 defaults, and then check motion (typing -> reading -> typing) as you listed.
Answer APPROVE (with any caveat to record) or list what must change first, briefly.
```

## Round 3: Kimi (kimi-k3.1-pro)

**APPROVE — as the documented still-frame checkpoint, not motion sign-off.** No static blocker is apparent in p5/p6r. Commit the exact value set with labeled t0/p5/p6r frames, keep v23 intact as rollback, and identify the globe lamp as set dressing.

**Caveat to record:** fingertip offsets are **+0.3/−0.3 cm**, so one side remains **3 mm below key-top level**—this is contact tolerance, not clearance on both sides. Also record the measured **8.3° typing / 8.6° reading** inclines and head position **0.5–0.8 cm ahead**.

The typing→reading→typing pass must still confirm no visible key or chair penetration, stable IK/elbows, smooth posture/head transitions without popping, and a clean return to the p5 typing pose.
