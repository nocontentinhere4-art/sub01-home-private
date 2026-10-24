# Kimi consultation (2026-10-24 16:44-16:49 UTC): periodic swapchain recreation as the interim mitigation

Kimi via `tools/ask_kimi.py` (default model), 32000-token budget, answered in 304 s.

## Question (verbatim)

```text
Follow-up on the SUB-01 render-time sawtooth (UE 5.8.3, Vulkan, NVIDIA 595.91.07, game window presented to Xvfb :99,
IMMEDIATE, 3 images; your previous answer: test r.NumBufferedOcclusionQueries 2 first, offscreen+FIFO as the structural
fix). New results, then a design decision. Max ~400 words, numbered.

Results (10 s PERF windows of the game; Insights 4 s full-hierarchy exports for the traced cases):
1. r.NumBufferedOcclusionQueries 2: the visibility fence wait disappears (ProcessVisibilityTasks 7.25 -> 1.52 ms/frame
   incl.) but frame time is unchanged (49 fps at the same ramp phase): the render thread now idles 4.3 ms/frame waiting
   for game-thread work, and the game thread waits 18.4 ms/frame in Sync_RenderingThread (r.GTSyncType 0 = RT N-1 and
   RHI-thread N-2 fences). Adding r.GTSyncType -1 brings the occlusion-fence wait back (3.9 ms/frame on the N-2 fence),
   frame time again unchanged. Conclusion: the RHI thread's present (~9.6 ms/frame, growing) is on the critical path
   whatever the buffering; these cvars only move the wait. Both reverted.
2. r.VSync 1 (16:31:21) and r.VSync 0 (16:35:03): each causes one 80-91 ms frame (FlushRHIThread + WaitForCompletion +
   FVulkanViewport swapchain destroy/create; UE logs "Creating new VK swapchain" only the first time) and RESETS THE
   RAMP. The 16:35:03 toggle was mid-ramp (3.7 min after the previous reset, frame 20.1 ms -> 18.4 ms, fps 49.7 -> 54.3).
   The next reset did NOT come on the old schedule (~16:38:40) but ~21.5k frames after the recreation (16:42:21-31),
   i.e. the cycle clock is per swapchain: ~21.66k presents after (re)creation the cost drops by itself. FIFO (VSync 1)
   behaved like IMMEDIATE on Xvfb (no 60 Hz cap, same ramp slope ~0.5 ms/min).
3. Baseline 16-min leg (cam2_fps 60): frame p50 20.16 ms (49.7 fps), p95 22.19, RHI user 8.8 -> 12.0 ms/frame per ramp,
   render 15.35 -> 18.60, slope 0.54 ms/min; GPU 2377-2396 MHz, 90-99 W, util 57% at ramp start and 48% at ramp end
   (GPU starved, not slower), no throttle reasons; no other GPU work (chrome, K07 python, NVENC ffmpeg idle).

Design decision (runtime mitigation now, structural fix for the coordinator later):
 a) Periodic swapchain recreation by alternating r.VSync 1 / 0 every T seconds through the live console from a small
    pod-side loop (one recreation per T; FIFO and IMMEDIATE alternate, both behave the same here). Expected: ramp
    amplitude 3.3 ms x (T*50 fps / 21.66k) -> T = 60 s: max +0.45 ms, mean +0.23 ms (now mean +1.65 ms), at the price of
    one ~85 ms frame per T (a visible ~5-frame freeze in the stream). Alternative: double toggle (1 then 0, 2 s apart) to
    stay in IMMEDIATE, two hitches per T.
 b) ABBA (A = no toggles, B = toggles every 60 s), legs 15 min + 60 s settle, same passive sampling, cam2_fps 60, judged on
    leg median frame time, p95, 1% low fps (hitches counted), ramp slope/amplitude and the number of >50 ms frames.
 c) For the coordinator (native): recreate the swapchain from code at a quiet moment, or better avoid the Xvfb present
    entirely (-RenderOffScreen + back-buffer readback to a FIFO via OnBackBufferReadyToPresent, like cam2; the present's
    base cost ~8.6 ms user + 2.5 ms sys per frame on the RHI thread would go away, not just the ramp).
Questions: is (a) acceptable as an interim mitigation for a private stream (hitch vs sawtooth), which T, single or
double toggle? Is (b) the right gate (what delta counts as a pass)? Anything risky about recreating an Xvfb swapchain
every minute for hours (leaks, X resources, NVIDIA driver)? What should I monitor for that?
```

## Answer (verbatim)

1. **Intermit mitigation/T:** Yes, as an easily disabled private-stream stopgap—but it is not visually free. At 60 s, you recover about **1.42 ms/frame** of mean ramp debt in exchange for one scheduled **~85 ms freeze/minute**. There is no objective optimum without a hitch budget. Use **60 s for the diagnostic ABBA**. For continuous streaming, I would start at **120 s**, then confirm it: predicted maximum/mean residual ramp is **~0.91/0.46 ms**, versus **0.46/0.23 ms** at 60 s. Thus 60 s buys only ~0.23 ms/frame while doubling the freezes. Use the **single alternating toggle**; the double toggle has no measured benefit and adds another hitch/reset.

2. **Gate:** ABBA is sound. Average the two B-leg metrics and two A-leg metrics, cancelling linear drift; keep hitches in the headline metrics. A reasonable preregistered pass is:
   - Median **≥1.0 ms better** (~5%), and improvement exceeds A-leg variability.
   - p95 no worse by more than **0.25 ms**.
   - No leg-scale upward trend; reset amplitude **≤0.6 ms**.
   - 1%-low FPS no more than **5% worse**.
   - Only approximately **15 additional >50 ms frames per 15-minute B leg**, each toggle-aligned and **<120 ms**, with no unscheduled stalls.  
   Otherwise, the mechanism works but the streaming configuration does not. Repeat if the A legs disagree materially.

3. **Risk/soak:** Two recreations establish nothing about leak safety. This repeatedly stresses UE viewport teardown, RHI flushes, and NVIDIA/X11 WSI; UE, driver, or X-server growth might appear only after hundreds of cycles. At 60 s, that is **60 recreations/hour, 1440/day**. Soak at least **8 hours/480 recreations** before trusting it, and **24 hours** for intended all-day operation. Retain an instant kill switch.

4. **Monitor:** Game and Xvfb RSS/PSS; `nvidia-smi` total/per-process GPU memory; game FD/thread counts; X resources via `xrestop` if supported; recreation latency; post-reset present cost and ramp amplitude. Fail on monotonic post-warm-up growth, growing hitches, `OUT_OF_*_MEMORY`, `DEVICE_LOST`, `BadAlloc`, or unscheduled stalls. Recreation only caps the ramp; offscreen/readback remains the structural candidate because it can also remove the **~11.1 ms/frame RHI present cost**, subject to measuring readback overhead.

## What was adopted

- ABBA `recr60` started 16:49:30 UTC: A = `r.VSync 0` with no toggles, B = `toggler.py 60` (single alternating r.VSync
  toggle every 60 s), legs 15 min + 60 s settle, same samplers in every leg, cam2_fps 60. Judged on Kimi's gate above
  (window medians, p95, low-fps windows, >50 ms windows, ramp amplitude).
- The toggler is NOT left running after the test: an 8-24 h soak with the monitors above is required first, and the
  recommended operating period is 120 s.
