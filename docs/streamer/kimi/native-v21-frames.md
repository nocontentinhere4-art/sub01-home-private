# Native v21: Kimi's frame review (2026-10-24 ~00:54 UTC)

Model `kimi-k3.1-pro`, 207 s. Question: `q-native-v21-frames.txt`; image: scratchpad `v21-work/kimi/native-v21-frames-sheet.jpg` (not committed) (2x2: v20 webcam
with the key light off / v21 webcam reading with key_cd 0.15 / v20 cam2 empty / v21 cam2 typing with him rendered).

## Kimi's answer (verbatim)

1. **Borderline acceptable for a test stream, not final sign-off.** The AFTER face is readable—neither muddy nor obviously featureless—but the forehead/cheeks/neck look pale and somewhat flat. Go **down** to **`key_cd = 0.125`**, not up; avoid 0.5 cd. The downscaled sheet cannot prove pixel-level clipping, so confirm on the original frame with a histogram/waveform.

2. **Cam2 defects, most important first:**
   1. **Chair/backrest interpenetration.** The white backrest slashing through the hoodie is the first thing the eye catches. The v21b approach is right: identify the thin tall central part regardless of pelvis-relative ordering, then move the chair rearward only as needed, up to 0.40 m. Validate that the backrest is behind the torso, the pelvis remains supported by the seat, and hand/keyboard alignment has not regressed.
   2. **Stretched fan at the right elbow.** Treat this as a pose-dependent deformation problem until inspected. At the exact typing pose, check the hoodie’s upper-arm/forearm/twist-bone weights, unweighted vertices, bone scale and elbow IK over-rotation; normalize/smooth the weights and add an elbow corrective if weight cleanup alone does not remove the fan.
   3. **Hunched, weakly readable typing pose.** His head and torso are thrust far forward, and the keyboard contact does not read cleanly. After the chair fit, reduce spine/neck forward pitch and re-solve both hands onto the keyboard. If the hands remain hidden, move cam2 slightly more side-on rather than distorting the pose to satisfy the camera.

3. **Webcam:** framing is serviceable—the whole head and chin are visible and the eye line works—though roughly 20% headroom makes it a little loose. The main owner-reject risk is the **craned neck/forward-lunging pose**, not a facial artefact. Also inspect the dark viewer-right torso/arm slit at full resolution; at this scale I cannot tell whether it is background or a mesh opening. No gross face/hair artefact is visible here, but the owner’s subjective taste cannot be inferred from the material.

## Response
1. Key light: down, as Kimi says. Measured on game m (skin median in a 110 px box on the face, 1920x1080, none clipped):
   0.04 cd -> 152, 0.06 -> 183, 0.08 -> 199, 0.15 -> 203; the task's target is ~140, so the tuning file carries `key_cd` 0.04.
2. cam2 chair interpenetration and the elbow fan: root cause found on game m2 - the level's keyboard pack and chair parts are
   Static-mobility actors, every SetActorLocation of the pull-back failed (605 "has to be 'Movable'" warnings), so since the
   pull-back he moved 36 cm back alone: the chair stayed (backrest 22 cm into his back) and the keyboard stayed 36 cm ahead (the
   hands IK stretched his arms to it). The final v21 makes each accepted prop Movable before moving it; verified on game m3: 0 mobility warnings, chair fit gap 0.8 cm
   (target 1) on the backrest `full-home_node_249`, his hands on the keyboard in the webcam. The elbow fan remains (skinning).
3. Hunched pose / craned neck: for the visual-QA loop after this build (typing_lean_deg / posture_lean_deg live keys).
