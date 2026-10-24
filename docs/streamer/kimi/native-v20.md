# Kimi consultation (2026-10-23): native build v20 (stream pass, cam2, pose fix)

Model kimi-k3.1-pro via `tools/ask_kimi.py` on the pod; questions in `q-native-v20.txt`, each with the generated C++ of the
layer attached (`install_stream_pass.py`, `install_cam2.py`, `install_pose_fix.py`). Advice to weigh: what was applied and
what was rejected (with the reason) is listed after each answer. Build v20 compiled with every applied change.

## 1. Design: hands IK (368 s)

1. **should fix — core solve: no issue; degeneracy handling is not robust.** The law of cosines, reach clamp, `D1`/`D2` composition, and conversion back to parent-relative rotations are correct. With unit/rigid bone transforms, `alpha == 1`, and a reachable target, the wrist reaches `T` and bone lengths are preserved. An unreachable target intentionally stops at the clamped distance.  
   The flip risk is real when the clip bend projection disappears, the pole becomes parallel to `Axis`, the two mixed bend directions nearly oppose each other, or `FindBetweenNormals` approaches 180°. The fallback axes and `1e-3` thresholds can produce discontinuities. Use the projected pole as the primary plane; when degenerate, reuse and reproject the previous frame’s valid bend direction, with hysteresis, before falling back to the clip/fixed axis. Fade or constrain near-shoulder targets and avoid linearly mixing nearly opposite bend vectors. This construction adds no explicit forearm roll, but does not guarantee anatomically stable twist or palm orientation.  
   **Local-rotation slerp is acceptable for the 0.3 s IK-weight fade.** It preserves hierarchy and lengths; it is not a linear wrist-position blend. Do not independently lerp component-space bone positions. If a controlled fade path is required, interpolate the effector target and re-solve.

2. **nit — traversal and cost are fine; define LOD behaviour explicitly.** `Out = Out * Source[parent]` correctly produces child-local × … × root in Unreal’s transform convention. A few hundred transform multiplications on the animation worker are not a credible 60 fps problem; caching parent chains is optional optimisation.  
   A missing arm bone or parent safely skips that arm, and missing fingers are skipped, but LOD can therefore make IK pop off. Require the arm chain and parents at every rendered LOD, or deliberately fade to an authored pose. Reset finger diagnostics on every early exit, and invalidate the resolver on skeleton identity changes, not merely equal bone count. Also make a valid post-solve hand transform (`Done`) a precondition for elbow/finger logging; it is currently readable after a failed hand-transform evaluation.  
   **Pole weight 0.5 and the supplied down/back/out vectors: no mathematical issue.** It is a heuristic bend-plane blend, not a guarantee of elbow placement. Pole weight does **not** control the 85–100° interior angle; that comes from shoulder–target distance and bone lengths. Correct seating/targets using the reach and elbow measurements.

3. **should fix — offsets are plausible, but the glide can pop.** For an 18–19 cm wrist-to-fingertip hand, 13 cm behind keyboard centre is a plausible curled-finger/home-row starting offset; 7 cm behind mouse centre plausibly places the wrist near the mouse’s rear for palm contact. A 20 cm span and 4.5 cm wrist height are also reasonable starting values. They are not skeleton-independent proof of contact: keyboard bounds centre is not necessarily home row, and wrist-only IK with unchanged hand-local rotation cannot guarantee fingertip or palm placement. Use calibrated home-row/mouse contact transforms or sockets, derive the wrist offset from the actual hand geometry, and verify hand component orientation and contact positions within wrist limits.  
   `W.InverseTransformPosition` and inverse-rotation of the poles correctly account for the seat offset. Left-hand planting and small-drift tracking are fine.  
   **Glide flaw:** `HandWorld` excludes the arc, while `Sent` includes it. Restarting mid-arc sets `MoveFrom = HandWorld`, instantly removing the old arc height—up to a 4 cm vertical pop. Store the last sent world position, including arc, and restart from that.

4. **nit — additive curl is valid; the measurements are limited.** Right-multiplying the local rotation is a valid additive local curl for this fixed skeleton, provided each bone’s axis and sign are visually validated. The PIP measurement is a sensible unsigned **flexion-from-straight** proxy: zero means collinear segments, not a zero-degree interior joint angle. The MCP measurement is cruder because hand→finger1 is wrist→knuckle, including palm geometry and finger splay. Both also include the authored clip pose and cannot distinguish flexion from sideways bending or hyperextension. Calibrate per finger against the reference/pre-curl pose, log additive delta separately from total flexion, and use a signed angle about the validated flexion axis if these numbers gate acceptance.

cam2: no capture/FIFO implementation was supplied, so its game-thread, JPEG, and nonblocking-drop behaviour cannot be assessed.

**Applied**: the bend falls back to the previous frame's bend (reprojected) when the clip's plane degenerates, and a mix of
nearly opposite clip/pole directions takes the pole instead of flipping through zero (`StreamerV2SolveTwoBone(..., LastBend)`);
the arm resolver is keyed on the skeleton (not only the bone count); finger diagnostics reset every evaluation; elbow and
finger measurements only after a valid solved hand; the glide restarts from the last SHOWN wrist position (arc included).
**Kept**: local-rotation slerp for the 0.3 s IK fade (Kimi: acceptable); the forearm carried by the upper-arm turn then bent
at the elbow. **Not done (noted)**: calibrated contact sockets for keys/mouse (no such data on the level; the knobs
`hand_back_cm`, `mouse_back_cm` and the measured reach cover it until frames are checked).

## 2. Design: cam2 readback path and frame cost (520 s)

5. **Should fix — ordering/readback logic itself is OK; resource lifetime is not.**
   - With the current immediate `CaptureScene()`, its rendering commands precede your readback command, so capture-then-copy is correctly ordered. Simply substituting `CaptureSceneDeferred()` breaks that guarantee; the copy must run after the deferred capture, or on the following tick.
   - `IsReady()/Lock()/Unlock()` on the render thread are correct. `IsReady()` only polls. `Lock()` still maps through the immediate RHI command list: with a threaded RHI it can cause synchronous render↔RHI submission/map overhead, although it should not wait for an unfinished GPU copy after a successful fence poll. Measure it; do not move `Lock()` to a worker thread.
   - Reuse after a ready, unlocked copy is the intended `FRHIGPUTextureReadback` pattern: `EnqueueCopy()` rearms the copy/fence. Your `Pending` protection and stale-slot handling are fine. The row copy is also correct: pitch is in pixels, hence `Pitch * 4` for BGRA8.
   - **No issue** with `Self` captures or readback reuse during JPEG encoding: the encoder owns an independent `Pixels` copy. Conversely, `Self` does not protect the raw `FTextureRenderTargetResource*`; see teardown below.

6. **Blocker for a hard “never stall/always 60 fps” promise; actual performance cannot be known from the excerpt.**
   - Immediate `CaptureScene()` is the flush-capable, higher-game-thread-cost path. For the stated requirement, use deferred capture and a one-frame pipeline: enqueue readback of the previous deferred capture before requesting the next one. Do not merely swap the function in the present code.
   - 720p is **44.4%** of 1080p’s pixels, but the capture is not “44.4% of main-view cost”: visibility, geometry, shadow and some Lumen/view-state work are resolution-independent or cache-dependent. At equal settings it can approach another substantial scene render. Readback itself is **3.686 MB/frame, 221 MB/s at 60 fps**, modest for this machine.
   - An RTX 4090 makes 60+60 plausible for a modest interior, not guaranteed. Budget total GPU/render work below **16.67 ms**, preferably around **14 ms**, and verify with `stat unit`, `stat gpu` and `profilegpu`.
   - Cheapest close-looking baseline: keep `SCS_FinalColorLDR`, matched exposure/post-processing, 720p at 100% capture scale, persistent history for TSR, and motion blur off. Next remove capture DOF and nonessential volumetric/RT effects. An optional 80% internal scale reduces pixel work by 36%, but softens output. Disabling Lumen or dynamic shadows is cheaper but materially changes lighting; first reduce capture-specific quality, shadow distance/resolution where supported.

7. **Should fix — normal writes are nonblocking, but there are real edge cases.**
   - **No issue** with nonblocking `open`, ENXIO retry, querying actual pipe capacity, or finishing `Rest` before another frame. Partial writes larger than `PIPE_BUF` are expected; `Rest` preserves stream order for one writer.
   - `FIONREAD` is not a reservation of whole-frame writable space, even where accepted on this descriptor. Treat it only as a heuristic; `write`/`EAGAIN` remains authoritative. If it succeeds and `Size > PipeBytes`, your room test drops forever. Either explicitly reject/reduce such frames, or start them only on an empty pipe and stream via `Rest`.
   - `Written` and `LastWrittenMs` currently advance on a partial write. Move them to completion of the final byte. Retry `EINTR` rather than treating it as reader loss.
   - Pool-thread identity is not itself a problem; the mask is thread-local and saved/restored correctly. However, do not restore an unblocked mask with a SIGPIPE still pending: a short positive write racing reader disappearance is the dangerous case. Drain pending SIGPIPE before every restore, or preferably use a dedicated writer thread with SIGPIPE permanently blocked. Absolute all-or-nothing delivery across reader disconnect is impossible for frames larger than `PIPE_BUF`.

8. **Should fix; no unconditional API-signature blocker is visible.**
   - Ensure both UObject members are `UPROPERTY` or otherwise strongly rooted. At teardown, stop submissions, finish the encoder, clear the readback ring in a render-thread shutdown command, and release the render target/resource only after queued users are gone. Currently the last `Self` reference can also release the ring from an arbitrary pool thread.
   - `SaveStringToFile()` plus `rename()` is synchronous filesystem I/O on the game thread every second. Move status serialization/write/rename to a worker using an atomic counter snapshot.
   - The listed `Lock`, `FImageView`, `CompressImage`, `SCS_FinalColorLDR`, `SetMotionBlur` and non-reflected `std::atomic` usages are **no issue**. Required dependencies include `RHI`, `RenderCore`, `ImageWrapper`, `ImageCore` and `Json`, with headers such as `RHIGPUReadback.h`, `RHICommandList.h`, `RenderingThread.h`, `ImageWrapper.h`, `ImageCore.h` and `Async/Async.h`, plus the normal Linux/POSIX headers. A stub build cannot certify the exact installed 5.8.3 headers.

**Applied**: `CaptureSceneDeferred()` by default (`cam2_deferred` 1) with a one-capture pipeline: each tick's readback
command is enqueued BEFORE the next deferred request and reads the previous capture (no mid-tick `SendAllEndOfFrameUpdates`,
same pose as the main view); depth of field off in the capture; a frame larger than the pipe starts only on an empty pipe and
streams through the rest; frames count as written with their last byte; EINTR retried; a pending SIGPIPE is consumed before
every mask restore. Confirmed in the 5.8.3 source: `RHIMapStagingSurface_RenderThread` flushes only when the fence is not yet
signalled (we lock only after `IsReady()`), and `EnqueueCopy` clears the fence for slot reuse.
**Rejected**: (a) the render-target resource pointer captured by the render command: commands run in order and the target's
release is enqueued after ours on destruction, so it cannot be freed first; (b) moving `cam2.json` writing off the game thread:
~1 KB once per second, the same pattern as the existing 4 Hz receipt; (c) a dedicated writer thread: one task in flight with
the mask restored after each write gives the same guarantee. The GPU cost is measured, not assumed: `SUB01_STREAMER_VISUAL_PERF
gpu_ms` with `cam2` 1 vs 0 and the `SUB01_STREAMER_VISUAL_CAM2` 30 s line.

## 3. Design: pose fix for the visual QA (472 s)

### A — pose offsets
- **ok:** `local' = parent⁻¹ * Delta * parent * local` is correct for a component-space rotation about the bone’s unchanged pivot, assuming no non-uniform bone scale and that component transforms are rebuilt from the mutated locals. Your signs are also correct: `+angle` about anatomical Right tips Up toward `Right × Up = Forward`; negative pitch raises the nose; positive Up-yaw turns right. Splitting yaw/pitch 0.4 Neck / 0.6 Head is anatomically fine.
- **should fix:** Thigh **origins**, not thigh directions, remain a good lateral axis in a symmetric seated pose. Asymmetric stepping, crossed legs, or hip separation crossing the 5 cm fallback can nevertheless rotate or snap that axis. Prefer a Hips-rotation axis calibrated in the reference pose against the reference thigh line; flatten it and retain the last valid axis on bad frames. Shoulders are worse because gestures and breathing move them.
- **ok / nit:** The gain cannot run away: its target is clamped to `[0.5,3]`, updates are convex, and breathing occurs after measurement. It can chatter when `Achieved≈0` or when clip geometry changes rapidly. Add an achievement deadband, for example `0.25°`, and optionally slow/slew-limit adaptation. No inherent oscillation is evident.

### B — loop seam
- **ok:** At rate 1, without hitches or interruption, the two-player construction is continuous at both ends; non-looping Previous is preferable to allowing it to wrap.
- **should fix:** A state change during a seam discards the currently visible blended pose: outgoing Previous becomes only `Current`, then `Progress` resets. That can reproduce the pop. Queue non-urgent changes until the seam finishes, or snapshot the blended outgoing pose/use another layer. Clear all seam state on every state switch, including reversals. Also, because seams are rejected while `Progress<1`, a natural wrap during a state-change fade remains unprotected.
- **should fix:** Fade time and animation time diverge when `Rate≠1` or `DeltaSeconds>0.1`. Previous can clamp at the end and freeze while Current continues. Trigger using sequence fade `min(wallFade*Rate, Length*0.25)`, run the blend for `sequenceFade/Rate`, and derive alpha from that same clock rather than the independently clamped `DeltaSeconds`.
- **ok / should fix:** `0.5 s` is a reasonable initial fade for a 5.5 s loop, but 7–9 cm correction still means 14–18 cm/s of visible drift. Prefer authoring a matching loop or choosing a seam minimizing pose **and velocity** error. Phase matching and seat-offset evaluation are not shown; restarting at zero is only safe if zero is the established phase, and seat/root offsets must use the identical blend alpha.

### C — face aim
- **ok:** Tracking while any camera is active and retaining one aim across switches fixes the repeated four-second settling behaviour.
- **should fix:** A tuning change does not reset `FaceSelectedAt`. If face is already selected, its wall-clock timeout is already expired, so re-aim happens immediately from one fresh sample. Moreover, `FromMean = HeadCount>0` can label one stale/intermittent sample as a mean. Reset the selection timer on tuning changes and use the mean only when `MeanSeconds>=2`; otherwise use the explicit fallback.
- **nit:** Use `K = 1-exp(-Dt/5)` for a exact variable-step exponential mean.

### D — seat and chair
- **blocker if `BodyRelative` is non-identity:** The body and chair pivots are not equivalent. `Seat*BodyRelative` rotates around `Pivot` in the outer relative space, whereas the chair uses `AuthoredBodyTransform*Pivot`. Transform the pelvis pivot through `BodyRelative` before constructing the outer yaw, or conjugate the component-space yaw by `BodyRelative`. Current order also rotates `PullLocal` but not `ClipOffset`; define both in one space and derive `ChairDelta` from exactly that result. The chair’s world rotation formula itself is correct.
- **should fix:** The AABB support formula is correct for a world AABB, but that box can substantially overestimate a rotated/reclined backrest’s front surface. The 20 cm lateral test does not guarantee armrest exclusion. Explicitly identify the backrest, then project its local OBB vertices or evaluate its front plane near sacrum height.
- **ok / should fix:** The fit move sign is correct and static geometry should converge in one pass. The 25 cm clamp bounds error, but instantaneous passes can visibly move the chair by up to 25 cm during streaming. Fit before going live/cache the result, or ease tuning corrections over roughly 0.3–0.5 s.
- **ok / calibration required:** Eleven centimetres behind a Mixamo Hips origin is plausible—roughly the expected 8–12 cm order—but cannot be validated from bone names. Measure R9’s pelvis/sacral surface and clothing; Hips is not intrinsically the sacrum.

### E — build/runtime
- **blocker:** As pasted, namespace-scope `StreamerV2Right(...) const` is invalid C++; non-member functions cannot have a trailing `const`. Remove it or make the function a member.
- **should fix:** Reference-skeleton indices are not universally mesh/compact-pose indices. Map them through `FBoneContainer` before `Pose[C]`; do not merely construct `FMeshPoseBoneIndex(Bone)`. Also make mutable globals per proxy/instance for safe multiple instances/worker-thread evaluation. No further UE-5.8-specific failure is provable from this excerpt.

**Applied**: his lateral axis is the thigh line calibrated ONCE into the Hips frame and carried by the Hips rotation (moving
legs no longer turn it), the last valid axis is kept on a bad frame; the lean gain adapts only on a measurable achievement
(>= 0.25 deg); a state change waits for a running loop seam (<= `loop_fade_s`) instead of dropping the blended pose; the face
camera restarts its selection timer on a tuning change and uses the head mean only after >= 2 s of samples, with the exact
exponential weight `1-exp(-dt/tau)`; the chair fit traces the backrest's real surface at sacrum height
(`LineTraceComponent` per chair part, from in front of him backwards; the bounds stay as the fallback) and the chair glides
to its fitted place at 60 cm/s.
**Rejected**: (a) "blocker if BodyRelative is non-identity": the body's authored relative transform here is a translation
(the actor takes the body's yaw-only rotation at the start) and any yaw-only rigid transform maps the vertical through the
pelvis to the vertical through its world image, so the body yaw (about the pelvis, component space) and the chair yaw (about
the pelvis's world point) are the same rotation; the pull-back is applied after the yaw by design, the clip offset before it;
(b) "namespace-scope `StreamerV2Right(...) const` is invalid": it is a member of the proxy struct (the excerpt cut the struct
head; the engine build compiled it); (c) mapping reference-skeleton indices through the bone container: these come from the
mesh's reference skeleton (`FBoneContainer::GetReferenceSkeleton()`), the same `MakeCompactPoseIndex(FMeshPoseBoneIndex(..))`
path the shipped v2 code uses. **Open (needs frames)**: a seam during a 0.24 s state-change fade stays unblended (rare); the
sacrum offset (11 cm behind Hips) and the trace height are calibration values to check on a side frame.

## 4. Code review of the final diff (5 parts, sent in parallel)

### Part 1: install_stream_pass.py (656 s)

**Blocker:** none found in this layer.

### Should fix

1. **Interrupted hand glides can pop vertically by up to `hand_arc_cm`.**  
   **Location:** `UpdateStreamerVisualHands`, target assignments:
   ```cpp
   Have ? Sent[S] : StreamerVisualHandWorld[S]
   ```
   During a glide, `Sent` includes the arc but `HandWorld` does not. If `Have` becomes false—IK disabled, keyboard lost, or schema changed—alpha remains nonzero while the published target immediately loses the arc, causing as much as a 4 cm snap.  
   **Fix:** publish the last displayed target while fading:
   ```cpp
   Have ? Sent[S] : StreamerVisualHandSent[S]
   ```
   Add a test that disables IK at `MoveP == 0.5` and asserts the target remains unchanged while alpha decays.

2. **The perf receipt is not reliably real-time fps/frame time.**  
   **Location:** `UpdateStreamerVisualPerf`. Game-world `Dt` may be smoothed, clamped, paused, or time-dilated; consequently `1000 / mean(Dt)` can conceal hitches or report non-wall-clock fps. GPU time is also the latest RHI sample appended once per game tick, so samples can be repeated or skipped when game/render rates differ.  
   **Fix:** derive window `fps` and mean `frame_ms` from successive `Now` wall-clock values:
   ```cpp
   fps = Frames / (Now - WindowStart);
   frame_ms = 1000.0 * (Now - WindowStart) / Frames;
   ```
   Measure `max_ms` from consecutive wall-clock ticks too. Either collect GPU samples per render frame or label the current value as a sampled estimate; report unavailable GPU timing explicitly rather than apparently valid zero.

### Nit

3. **The key light is registered before being made dark.**  
   **Location:** `KEY_LIGHT_CREATE`. Between `RegisterComponent()` and the first `UpdateStreamerVisualKeyLight`, it has engine-default intensity/visibility and an interim transform. Usually same-tick updates prevent a visible flash, but initialization should not depend on that ordering.  
   **Fix:** set intensity zero and visibility false before registration; preferably `SetupAttachment(GetRootComponent())`, configure, then register. The first update applies the tuned state.

4. **Exact `Head` lookup can unnecessarily defeat head aiming on prefixed Mixamo skeletons.**  
   **Location:** `UpdateStreamerVisualKeyLight`, `GetBoneIndex(TEXT("Head"))`. Unlike the arm resolver, this has no suffix fallback.  
   **Fix:** resolve/cache `Head` using the same exact-then-suffix strategy. Add a `mixamorig:Head`-style test. This is only a fallback-aim issue, not a crash.

### No issue found

- The two-bone law-of-cosines solve, transform/quaternion composition order, bone-length preservation, pole projection, and elbow/finger angle signs are correct.
- The worker-side solve touches only proxy/pose data; no new actor or RHI access occurs there.
- Mouse/chair array additions are bounds-guarded, and the chair-only delta gate correctly avoids the old early-return problem.
- Forced-LOD numbering (`1` = LOD0) and hide-slot change/restore flow look correct.
- Anchor uniqueness checks, dry-run behaviour, second-run refusal, and in-memory all-or-nothing planning look correct.

Before runtime sign-off, the C++ stub still needs supplementing with an on-engine smoke test for actual section hide/show, forced LOD, light registration/aim, and Vulkan GPU timing.

**Applied**: the IK fade-out keeps the last SHOWN target (`StreamerVisualHandSent`, arc included); perf from the wall clock between ticks (fps = frames / window, frame_ms = window / frames, max_ms = the longest gap), GPU time averaged over the non-zero RHI samples and -1 when none (`gpu_samples` in the log), counters reset on a fresh window (a bug the new exact test then caught); the key light is dark and hidden before `RegisterComponent`. **Rejected**: exact `Head` lookup (this skeleton's bone is literally `Head`: the seat fix's FACE_RIG log lists Neck/Head/HeadTop_End and `head_world` is filled in every receipt).

### Part 2: install_cam2.py (536 s)

## Blocker

1. **`CaptureSceneDeferred()` is called on the game thread.**  
   **Location:** `ASub01HomeCharacter::UpdateStreamerVisualCam2`, final statement of the capture block:
   ```cpp
   if(Deferred) StreamerVisualCam2->CaptureSceneDeferred();
   ```
   This runs from the character tick. In UE, `CaptureSceneDeferred()` is the render-thread entry point; the game-thread API is `CaptureScene()`, which schedules the deferred capture. The current default path therefore violates UE thread affinity and can race scene/render-target state or fail at runtime despite compiling.

   **Fix:** For a safe immediate commit, use `CaptureScene()` followed by the readback render command, copying that capture and removing the previous-capture state. To retain main-view/deferred rendering, invoke `CaptureSceneDeferred()` from the appropriate render-thread capture hook/command, preserving the required order: poll/copy the previous target before rendering the new capture.

   **Test gap:** The stub must model this contract—e.g. record/assert thread affinity in `CaptureSceneDeferred()`. A syntax-only stub currently approves the invalid call. Also add one real Vulkan capture test; stub frame ordering cannot validate actual scene-capture execution.

## Should fix

2. **Disabling cam2 does not prevent pre-pause readbacks from being emitted after resume.**  
   **Location:** `UpdateStreamerVisualCam2`:
   ```cpp
   if(!On) StreamerVisualCam2HasPrevious=false; // a stale target is never copied after a pause
   ```
   This only suppresses copying the render target on the first resumed capture. `Pending[]` entries remain in `FSub01StreamerCam2::Readback`. On resume, `Pump()` first polls that ring and can encode the newest pre-pause copy—even when its current `Texture` argument is null. Thus an old image can be written and counted as a new post-resume frame.

   **Fix:** Add a capture generation/epoch, incremented on disable/resume, and stamp slots and encode work; discard older generations instead of encoding them. Alternatively, enqueue render-thread invalidation that marks outstanding slots stale and frees each only when its fence is ready. Do **not** simply clear `Pending` for unfinished GPU copies and reuse those slots.

   **Test:** Pause with an outstanding readback, change the stub image contents, resume, and assert that no pre-pause pixels reach `EncodeAndWrite`.

## Nit

3. **All FIFO open failures are reported as “no reader”.**  
   **Location:** `FSub01StreamerCam2::WriteFrame`, failed `::open`.
   `ENXIO` means no reader, but `EACCES`, `EMFILE`, `ENFILE`, etc. receive the same counter and leave `cam2_reason` empty, causing misleading status and indefinite retries.

   **Fix:** Handle `ENXIO` separately; rate-limited-log/store `errno` for other failures, and disable cam2 for permanent path/permission errors.

## No issue found

- The readback row copy is correct: `FRHIGPUTextureReadback::Lock` reports pitch in pixels, so `Source + Y * Pitch * 4` is intentional.
- Ring polling never waits on a fence; encoder exclusion, counter atomics, `Self` lifetime, and movement of `Pixels` into the single encode task are sound for steady-state operation.
- FIFO `Rest` ordering, EAGAIN/EINTR handling, whole-frame dropping, and blocked/drained SIGPIPE handling preserve frame order; no interleaving defect found.
- Look-at yaw/pitch signs, `FRotator(Pitch, Yaw, 0)`, timer arithmetic, and installer anchor/refusal planning look correct.

**Rejected (blocker claim)**: `CaptureSceneDeferred()` is a game-thread call in UE 5.8.3 (`SceneCaptureComponent.cpp`: it adds the component to `SceneCapturesToUpdateMap` under a lock; the capture renders with the next main view; the header says "Render the scene to the texture the next time the main view is rendered"). **Applied**: a capture epoch (bumped when `cam2` goes 0) stamped on every readback slot; copies from before a pause are dropped (`dropped_stale`), never encoded after it; FIFO open errors other than ENXIO are kept in `open_errno` (status) instead of counting as "no reader" (not disabled: a permission fix should be picked up without a restart).

### Part 3: install_pose_fix.py (308 s)

## Blocker

None proven from this part alone. The successful engine build removes compile/API concerns, but the runtime behaviours below remain open.

## Should fix

1. **Chair tracing can select the seat, legs, or another ineligible part as the “backrest”.**  
   **Location:** `FitStreamerVisualChair`, the `FindComponentByClass<UPrimitiveComponent>()` block.  
   The trace runs before the behind/above eligibility checks. Any resulting hit sets `ByTrace`, overrides the bounds result, and even bypasses the `!Parts` no-backrest path. A closer seat/armrest hit can therefore drive the chair to the wrong position. Tracing only the first primitive may also trace a collision root rather than the visible backrest.  
   **Fix:** determine backrest eligibility first; trace only eligible backrest primitives, preferably all relevant visible primitives. Allow `ByTrace` only for those hits. Add a test with an ineligible part producing a closer hit than the real backrest.

2. **The face-camera head tracker does not support the prefixed Mixamo names supported by the proxy.**  
   **Location:** `ApplyStreamerVisualFaceCamera`, `GetBoneIndex(TEXT("Head"))`.  
   `ResolveStreamerV2Pose` explicitly falls back to suffix matching, but the camera requires an exact `Head` name. On a skeleton containing only e.g. `mixamorig:Head`, no samples are collected and the camera permanently uses the two-second fallback aim.  
   **Fix:** publish/reuse the proxy’s resolved Head reference-skeleton index, or perform equivalent suffix resolution on the mesh and use `GetBoneTransform(index)`. Test with no exact `Head` bone.

3. **The loop seam freezes Previous instead of playing through the loop’s end.**  
   **Location:** `StreamerV2LoopSeam`, `Previous.SetPlayRate(0)`.  
   This holds the pose captured at fade entry for the whole fade, contrary to the stated end-to-start crossfade; motion can visibly stall before blending into the restart.  
   **Fix:** advance Previous at `Rate`, clamping/holding only once it reaches the sequence end. Also make the timing convention consistent for non-unit rates: currently `Length-Fade` uses sequence seconds while `Progress` fades over wall-clock seconds. Either support and test rates such as 0.5 and 2, or explicitly restrict desk loops to rate 1.

4. **A tuning re-aim causes a camera cut when the face camera is already visible.**  
   **Location:** `ApplyStreamerVisualFaceCamera`, `if(StreamerVisualTuningChanged)` followed by the aim/alpha blocks.  
   `FaceAimed` is cleared, but `FaceAlpha` remains 1. The old aim is rendered while the new mean is collected, then the new location/rotation is applied immediately at `Ease == 1`.  
   **Fix:** retain the old aim as a blend source and ease old→new over one second when the new aim becomes ready. Add a regression test beginning with `FaceAlpha == 1`.

## Nit

- **Frame-rate-dependent gain adaptation:** `ApplyStreamerV2Body` applies a fixed `0.2` correction per animation evaluation. Convergence differs substantially between 30 and 120 Hz. Pass evaluation delta time into the body pass and use an exponential/time-based coefficient.
- On measurement failure with `Measure == true`, `StreamerV2LeanMeasured` can retain a stale value; clear it whenever the post-lean Head transform cannot be obtained.

## No issue found

- The shown `parentRotation⁻¹ * Delta * parentRotation * local` rotation preserves the bone pivot and produces the intended component-space pre-rotation, assuming ordinary unit bone scale.
- The lean inclination sign, nose-up head pitch sign, right-positive yaw, camera side-vector calculation, and chair gap/move signs are internally consistent.
- No new render-thread interaction or demonstrable cross-thread race is introduced in the shown code; scene queries remain on the character side and pose mutation remains in proxy evaluation.
- The installer’s exactly-once anchors, refusal-before-write, marker/balance checks, dry-run behaviour, and post-write verification are coherent in this part.

The stub tests cannot establish the real Mixamo `+10° → 10±1°` acceptance, actual animation-player seam behaviour, or collision-derived chair fit; those still require in-game validation.

**Applied**: chair-fit eligibility (behind, above, not an armrest) before the trace, only eligible parts' hits count; a tuning re-aim while the webcam is on screen eases from the old aim over 1 s (no cut); the lean gain adapts with a time constant (0.08 s) from the proxy's delta time instead of a fixed per-evaluation step; a failed post-lean measurement clears the value. **Rejected**: exact `Head` (as part 1); "the seam freezes Previous": Previous is advanced every frame by the existing captured-layer clock (`AdvanceCapturedLayerTime` with `PreviousCapturedRate`), exactly as in a state-change crossfade; desk loops play at rate 1.

### Part 4: tests (stub and drivers, first half) (369 s)

**Blocker:** none demonstrated by this chunk. It contains mainly the stub and drivers; actual game/render/anim-thread safety cannot be established from it.

### Should fix

1. **The hand-IK integration can be completely broken while every test passes.**  
   **Location:** `STREAMPASS_DRIVER`, `STREAMPASS_MATH_DRIVER`.  
   The character driver checks targets and flags, while the math driver tests only `StreamerV2SolveTwoBone`. Neither runs `EvaluateStreamerV2Hands` nor inspects `Output.Pose`; measured angles are manually assigned, and `NativePostEvaluateAnimation()` is explicitly empty. Thus wrong bone indices, parent/local rotation composition, component-space conversion, alpha application, or finger rotations would still pass.  
   **Fix:** add a three-bone pose evaluation test: alpha 0 must leave the pose unchanged; alpha 1 must preserve both bone lengths and place the wrist on the component-space target; verify elbow direction, unchanged hand-local transform, malformed hierarchies, and actual finger-joint rotations. Exercise the game-thread-to-proxy copy rather than assigning proxy measurements manually.

2. **The cam2 stub removes every threading/lifetime boundary it is meant to test.**  
   **Location:** `StubRender::FDispatch::operator()`, `AsyncTask`, and `FRHIGPUTextureReadback`.  
   Render commands and “background” JPEG work execute immediately on the calling thread, while the readback staging buffer appears synchronously. Consequently, tests cannot expose a game-thread RHI call, locking before readiness, unsynchronized ring-slot reuse, a task capturing a dead `this`, or shutdown with an encode/readback outstanding. Whether the production code has these defects is unknowable here.  
   **Fix:** queue render commands until an explicit render pump; make readiness depend on that pump; assert `Lock` only after readiness and pair every lock/unlock. Run encoding on a controllable worker, then test completion out of order, backpressure, FIFO destruction, and character teardown with work outstanding.

3. **The image oracle cannot detect stride, dimensions, orientation, or most pixel corruption.**  
   **Location:** `FRHIGPUTextureReadback::EnqueueCopy` and `IImageWrapperModule::CompressImage`.  
   Every staging byte has the same value, and the fake encoder examines only `Image.Colors[0].B`. Wrong row addressing, padded-pitch handling, height, or vertical flipping therefore produces the same observed result.  
   **Fix:** fill pixels with an `(x,y)`-dependent pattern, use a pitch greater than 1280, and have the fake encoder validate/hash every pixel plus `SizeX/SizeY`. Include explicit top/bottom-row checks.

### Nit

4. **The perf test accepts a completely unimplemented perf calculation.**  
   **Location:** `STREAMPASS_DRIVER`, `CHECK(..., 20)`.  
   If both frame time and FPS remain zero, `Near(FrameMs,0)` makes the assertion pass. Despite the comment, neither `max_ms` nor window reset is checked.  
   **Fix:** use controlled ticks and nonzero configurable GPU cycles; assert exact FPS/frame/max values, publication timing, and reset on a second window. Also, material hiding is only exercised with `hide_slot == -1`; `ShowMaterialSection` records nothing, so add a valid-slot test if that path matters.

### No issue found

The installer tests properly cover dry-run equivalence, exactly-once anchors, all-or-nothing writes, CRLF preservation, dependencies, and second-run refusal. The visible quaternion multiplication/rotation and transform formulas are consistent for the tested unit-scale cases. The two-bone math tests have good length, reach-clamping, pole, degeneracy, and bend-continuity coverage, and the hand-glide driver correctly checks small drift and mid-arc restart from the displayed position.

**Applied**: the proxy now runs on a bone chain in the tests (`test_v20_proxy_runs_on_a_bone_chain`: a Mixamo-like skeleton with local +Y bones and arbitrary twists; lean +10 converges to 10.000 deg with gain 1.46 and the pelvis fixed, sideways head drift < 5 mm, lean -16 sits him up, nose-down 5 deg nod within 0.5 deg with < 1 deg yaw/twist, yaw +20 to his right, the mouth emphasis, hand IK with alpha 0/1, lengths kept, hand local untouched, finger curl x1/x1.2); render commands and async tasks are QUEUED in the stub and flushed after each game tick; the readback stub fills an (x,y) pattern with padded rows and the fake encoder checks every pixel and the size (`StubPixelErrors == 0`); `Lock` only after `IsReady` and paired with `Unlock` (`BadLocks == 0`); the perf test asserts exact fps/frame/max/GPU values and the window reset.

### Part 5: tests (second half) and README (560 s)

**Blocker:** none demonstrated by this part. It is principally tests/documentation; a product C++ defect should not be inferred where the implementation is absent.

### Should fix

1. **Reader loss during a partially written frame is untested** — `CAM2_DRIVER`, reader-leaves section (`close(R); Ticks(C, 6, ...)`), and the oversized-frame checks `150–152`.  
   The reader-close test occurs with small frames and no pending `Rest`. If an oversized frame has been partially written and the reader then disappears, carrying `Rest` into a subsequent reader would send that reader the tail of an old JPEG before any new frame.  
   **Fix/test:** explicitly discard the incomplete frame on the EPIPE/reader-close path (`Rest.Reset()` or equivalent), do not increment `Written`, and add a driver case that closes mid-frame, reopens, and verifies the new stream begins with `FF D8` and contains only complete newer frames. If the implementation already resets `Rest`, this test will prove it.

2. **The actual pose proxy behaviour is not exercised** — `test_posefix_logic_runs`, `POSEFIX_DRIVER`, and `POSEFIX_MATH_DRIVER`.  
   The character driver checks field plumbing, seat/chair behaviour, and camera aiming; the math driver checks isolated quaternion formulas. Neither runs the real proxy evaluation through a pose. Consequently, incorrect bone indices, gain adaptation, weight application, or loop-seam state handling could pass every shown test—including the stated `+10° → 10±1°` acceptance criterion.  
   **Fix:** add a deterministic bone-chain fixture, run the real evaluation for enough frames to settle, and measure Hips→Head inclination from the resulting pose. Also assert head yaw/pitch on the output bones and evaluate across a loop boundary, checking transform continuity rather than merely checking seam-related strings.

3. **`WholeFrames` does not verify its stated ordering invariant, and the pitch test does not verify pixels** — `CAM2_DRIVER::WholeFrames` and the `StubPitch = 1344` section.  
   ```cpp
   uint8(F[2] - Last) == 0
   ```
   rejects only equality; reversed sequence numbers are accepted. The JPEG checks otherwise cover framing markers, not whether padded source rows were copied correctly.  
   **Fix:** have the stub embed a wider capture serial and require strictly increasing serials. Independently feed row/column-dependent BGRA pixels and assert, at the compressor boundary, that row 1 and subsequent rows contain the expected pixels when pitch differs from width.

### Nit

4. **The FIFO documentation overstates the guarantee** — README, Cam2 “Writer (background)” bullet.  
   “The reader never sees a split JPEG” is false at `read()` granularity; the oversized-frame test deliberately completes a frame through multiple writes. What the design can guarantee is an ordered, non-interleaved MJPEG byte stream while a reader remains connected.  
   **Fix:** use that wording. If atomic whole-frame visibility is genuinely required, this FIFO protocol does not provide it.

5. **The documented command order violates the pose-fix prerequisite** — README installation command block.  
   `install_pose_fix.py --dry-run` appears before `install_mouth.py`, although pose fix refuses sources lacking the mouth layer.  
   **Fix:** move the mouth installation before pose fix in the executable sequence.

### No issue found

The shown quaternion conjugation `P⁻¹ Δ P L`, lean/nose/yaw sign checks, and chair-gap movement sign are internally consistent. The deferred-readback-before-next-capture ordering assertion is correct. Installer dry-run, refusal, no-write, and hash-preservation coverage is good. UE render-thread/resource teardown remains unverified by the stub, but this excerpt does not establish a lifetime defect.

**Applied**: a reader that leaves mid-frame (a partial oversized frame in `Rest`) is tested: the next reader's stream starts with `FF D8` and holds only whole newer frames; frame order is checked by a strictly increasing encode counter AND capture serial; the README's FIFO wording now promises an ordered, non-interleaved stream of whole frames while a reader stays connected; the install order in the README puts the mouth layer before the pose fix.

After these changes: 93 tests pass (stub compile with g++ and clang++, -Wall -Werror -Wshadow) and build v20 was rebuilt from the backup with the four layers.
