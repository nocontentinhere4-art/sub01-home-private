# Native v21: Kimi's final review (game m3, 2026-10-24 ~01:25 UTC)

Model `kimi-k3.1-pro`, 466 s. Question: `q-native-v21-final.txt`; attached: the C++ delta from the reviewed build to the
final one, the final `scripts/streamer_cpu_partition.py`, and the final frame sheet (scratchpad `v21-work/kimi/native-v21-final-frames.jpg`,
not committed: webcam and cam2 in reading/typing/talking on game m3).

## Kimi's answer (verbatim)

## 1) Remaining delta blocker

**No live game/rendering blocker is evident in the supplied C++ delta.** The console grammar is substantially tighter, unhandled commands now count as refused, and the mobility/chair changes are consistent with the reported m3 result.

There is **one concrete partitioner contract bug**: in the documented `--interval` mode, a game-thread `EPERM` is logged but never causes exit 1—the function containing the exit-code check is never reached.

```python
print(json.dumps(result), flush=True)
if result['game_failed']:
    return 1
```

Add that immediately after printing. It does not invalidate the successful m3 measurements, but fix it before sign-off if supervisors rely on the stated fail-fast behaviour.

The shown fd-adoption order is sound **provided the probe only publishes when `!Reader && HandoffFd < 0`**. The probe and close paths are not included, so fd-leak/stale-reader correctness cannot be fully certified here; soak reader reconnects and check stable fd count plus clean frame boundaries.

## 2) Frame verdict and visual-QA order

**Substantially improved, but cam2 is still visually unacceptable.** The old gross chair/keyboard displacement is not apparent, and the webcam is usable. Cam2 has severely clipped walls/desk/chair and an illegible, nearly white monitor.

In order:

1. **Fix cam2 exposure/tone mapping, then prove the monitor path.** Lock exposure for repeatable QA. Display a known grey ramp, colour bars and text in Chromium: if room detail returns but the screen remains blank, debug the browser-to-monitor capture/material rather than lighting.
2. **Verify contacts with dedicated QA views, not these broadcast angles.** Use a side view of pelvis/backrest and close views of both hands/keys throughout complete motion cycles. The webcam crops the keyboard and cam2 occludes finger contact, so these stills do not independently certify the reported fit.
3. **Make the performances distinct.** Typing reads most clearly; reading and talking are too similar. Correct gaze/eye-line and talking head/mouth performance, then inspect state transitions, floating/penetration and exposure pumping in full-rate video. Lip-sync, typing cadence and temporal artefacts cannot be judged from this sheet; each cell is only 640×360.

Only after those should the loop spend time on framing and material/lighting polish.

## 3) Performance ceiling and the route to 60/60

**45–47 fps is an honest ceiling for v21 as currently implemented—not a fundamental ceiling for the hardware or two-camera architecture.**

- 45–47 fps means **21.3–22.2 ms/frame**; 60 fps requires **16.67 ms**.
- The render thread alone is already **17–18 ms**.
- GPU at **7–10.5 ms** and 0% throttling leaves little reason to start with more partitioning or lower resolution.

The highest-value next step is **eliminating repeated static shadow-depth submission**, particularly for the second view: **1,850/2,340 draw calls, about 79%, are shadow depth**. Bake/cache the static house’s shadows and reuse them across both view families, keeping per-frame dynamic shadows for the streamer and newly movable props.

As a cheap diagnostic first, run once with cam2 dynamic shadows disabled—not as the final look. You want at least roughly **5–6 ms** saved; a practical render-thread target is around **11–12 ms**, followed by end-to-end p95 frame-time and cam2-delivery measurements. That experiment will quickly validate or reject the shadow hypothesis. **60/60 is plausible, but not proven**, and cam2’s current 41–46 fps delivery must be rechecked after rendering is fixed.

## Response
1. Partitioner: fixed - `--interval` now exits 1 on the first pass whose game threads could not be pinned (test added). The probe
   publishes only when `!Reader && HandoffFd < 0` (it returns early otherwise), as Kimi requires; a reconnect soak with an fd
   count is for the director cut-over.
2. Frames: cam2 exposure (bright walls and a near-white monitor) and dedicated contact QA views are the next visual-QA items;
   reading vs talking performance too. Not in this build.
3. Performance: 45-47 fps with both views is the honest v21 ceiling; next step is the shadow-depth cost (79% of draw calls).
   Diagnostic already measured tonight on game m (both views, `r.ShadowQuality 0` through the console channel): 53 fps
   with a cam2 reader, render thread 13.1 ms (from ~17.4): shadows are ~4 ms of the two-view render thread, not 5-6.
