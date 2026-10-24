# Kimi consultation (2026-10-24 16:08-16:20 UTC): the sawtooth mechanism and the fix plan

Kimi via `tools/ask_kimi.py` (default model). The first try spent its whole 16000-token budget reasoning and returned no answer; the second
try (32000 tokens) answered in 303 s.

## Question (verbatim)

```text
SUB-01 render-time sawtooth (UE 5.8.3 editor build run as UnrealEditor-Cmd -game, Linux, Vulkan SM6, NVIDIA RTX PRO 4000,
driver 595.91.07; the game window is presented to Xvfb :99 (1920x1080, no DRI3, VK_PRESENT_MODE_IMMEDIATE_KHR, 3 images);
the director's ffmpeg x11grabs that window at 60 fps). The game is pinned to cores 0-5 (-corelimit=6: 2 foreground + 3
background workers). Symptom: render_ms climbs ~0.5 ms/min and drops back every ~7 min (fps ~55 -> ~45). Earlier ruled out:
GC, allocator, PC-frame textures, host load, the TV video loop. Please review the mechanism and decide the fix plan.
Max ~450 words, numbered.

New evidence (two 40-52 s Unreal Insights windows, A = ramp start, B = ramp end, events exported with thread names;
plus /proc sampling every 5-15 s over a full ramp):
1. The earlier "per-call growth" table was mis-attributed: ExportTimerStatistics always includes the GPU queues, and the
   4.4 -> 6.8 ms "EndDrawingViewport" and "RenderGraphExecute exclusive" rows were GPU breadcrumb timers whose spans include
   GPU idle. On the CPU render thread EndDrawingViewport is 8 us.
2. Per frame (A 52.1 fps / B 45.1 fps; frame p50 19.1 / 22.1 ms): RHI thread VulkanQueuePresent 8.2 -> 10.8 ms (+2.6).
   Render thread: +3.1 ms per frame, of which +1.8 ms is WaitForTasks under ProcessVisibilityTasks ->
   FSceneRenderer::WaitOcclusionTests -> FRHICommandListExecutor::WaitOnRHIThreadFence (2.9 -> 4.75 ms per frame), and
   the rest a broad 5-15% slowdown of many scopes. While the render thread waits there, the workers are mostly idle and
   the RHI thread is inside VulkanQueuePresent (1.0 ms of the 3.0 ms wait in A, 2.7 of 4.76 ms in B). Workers' and game
   thread's own work is flat (the game thread waits on the render thread).
3. GPU: the scene passes per frame are flat (~7.8 ms main SceneRender, ~6.4 ms group, gpu_ms 10.7 flat); nvidia-smi:
   2385 MHz, P1, 93 W of 145 W, no throttle reasons, 46% util. In a frame the GPU finishes ~3-4 ms after the RHI thread
   enters present, and present returns 5.6 ms (A) / 6.5-6.8 ms (B) after that, so most of present is not GPU wait.
4. /proc per-thread, normalised per frame across one ramp: RHI thread USER time 8.6 ms/frame right after a reset ->
   12.2 ms/frame at the end of the ramp; RHI system time flat 2.5 ms; minor faults ~0; voluntary switches flat 51/frame;
   render thread user ~12.5-13.5 ms flat-ish; Xvfb :99 CPU ~210 ms/s, flat per frame. cgroup: zero throttling during
   the ramp (6.4 of 10.2 CPUs used).
5. The reset is tied to a FRAME COUNT, not wall time: 14 consecutive cycles had 21,662 +- 230 frames (PERF 10 s windows)
   while their duration varied 390-450 s with fps (e.g. 400 s at 54.9 fps = 21,967 frames; 440 s at 49.5 fps = 21,810).
   65536 / 21,662 = 3.03. Hypothesis: the NVIDIA X11 WSI on Xvfb (libxcb/libxcb-present/shm/sync/xfixes mapped) sends
   ~3 X requests per present, and a user-space structure it scans per present grows until the 16-bit X11 request
   sequence number wraps (65536 requests), e.g. unclaimed replies/events or pending presents compared modulo 2^16.
   No swapchain recreation is logged during the run (one "Creating new VK swapchain" at start).

Proposed plan:
 a) Runtime fix candidate: r.NumBufferedOcclusionQueries 2 (ECVF_RenderThreadSafe, default 1, max 4). With 2,
    WaitOcclusionTests keeps one fence in flight, so the render thread should stop waiting for the RHI thread's present;
    the RHI thread (now ~63% of a core at 50 fps, 11-15 ms CPU per frame) would then limit only if it exceeds the frame
    budget. Cost: occlusion results one frame older (possible popping). ABBA (A = 1, B = 2), legs ~15 min = 2 ramps each,
    judged on per-leg median frame time, p95, ramp slope (render_ms vs frames since reset) and start-to-end delta; same
    passive sampling in every leg; cam2_fps 60.
 b) Proof of the X11 mechanism without native code: t.MaxFPS 30 for one leg (cycle should stretch to ~720 s if it is
    per-frame/per-request; stay 440 s if wall-time).
 c) Structural fix (native/launch, for the coordinator): stop presenting the main view through the Xvfb X11 path (the
    present costs 8-12 ms of RHI CPU per frame even at its best): -RenderOffScreen plus a main-view FIFO like cam2 for the
    director, or a GPU-backed X server (Xorg + nvidia_drv, headless) for :99; or a native workaround that forces a sequence
    wrap periodically (XNoOp burst on the game's Display).
Questions: is the mechanism argument sound, and what would falsify it cheaply? Is (a) safe to flip at runtime on UE 5.8
(occlusion history sized for 4 frames), and are there other render-thread -> RHI-thread sync points I should A/B
instead or as well (r.RHICmd*, r.GTSyncType, r.OneFrameThreadLag were inconclusive earlier)? Order of (a), (b), (c)?
```

## Answer (verbatim)

1. **Mechanism: strong localisation, but only circumstantial causality.** Flat GPU work plus growing RHI **user** time, with flat syscalls/faults/switches, is consistent with a user-space scan inside present—not GPU back-pressure. The arithmetic also fits: three requests/frame leave only 550 other requests before 65,536 at 21,662 frames. It does not yet distinguish NVIDIA WSI from libxcb/UE, or exclude another per-present counter.

2. **Cheap falsification.** Sample only the RHI TID with `perf record -g` early/late; extra samples should land in present/WSI/X11. If feasible, run one `xtrace`/`x11trace` cycle and use its protocol data, not its timings: reset must coincide with wrapping on the **WSI connection**, and cycle length must match measured requests/frame. A sawtooth surviving a verified no-main-view-present `-RenderOffScreen` run falsifies the X11-present explanation. `t.MaxFPS 30` predicting ~21.7k frames/~722 s merely reconfirms frame dependence; a driver frame counter predicts that too. The strongest causal test is a verified early wrap using XNoOps on that same WSI connection: immediate reset supports it; no reset falsifies the simple model. Requests from another X client do not count.

3. **(a) is worth testing, but only hides the latency.** Yes—given your 5.8.3 source check that the CVar is consumed per frame and all four slots exist, runtime 1↔2 is reasonable; `ECVF_RenderThreadSafe` alone would not establish that. Flip at leg boundaries and discard transition frames. Present’s CPU ramp remains. At the worst sampled point, 12.2+2.5=14.7 ms RHI CPU/frame is ~88% of a core at 60 fps, before scheduling gaps, so RHI can still cap fps. Check popping/disappearing geometry on cuts and fast motion.

4. **Other A/Bs:** do not shotgun `r.RHICmd*`, `r.GTSyncType`, or `r.OneFrameThreadLag`; they do not target this fence. Optionally test 4 as a dose check, and an occlusion-queries-off leg solely to bound the benefit of removing that wait. A no-RHI-thread launch leg is diagnostic only: it should relocate present cost.

5. **Order:** run a short (a) A/B now for mitigation; prototype (c) offscreen+FIFO immediately/in parallel—it is both the preferred fix and cleanest ablation—then complete ABBA as needed. Prefer GPU-backed Xorg second; wrap-forcing only as a diagnostic/last resort. Treat (b) as optional, not a proof gate.

## What was adopted

- (a) `r.NumBufferedOcclusionQueries 2` is tested first as the runtime mitigation: a short check, then the full ABBA with
  15-minute legs; the setting is flipped at leg boundaries and the 60 s after each flip are discarded; frames are
  checked for popping.
- `r.RHICmd*`, `r.GTSyncType` and `r.OneFrameThreadLag` are not re-tested (they do not target this fence).
- (c) offscreen rendering plus a main-view FIFO is written up for the coordinator as the structural fix (native code and
  a director change, both outside this agent's remit). `perf` and `xtrace` are not installed on the pod and
  `perf_event_paranoid` is 4, so the causal X11 test stays a recommendation.
