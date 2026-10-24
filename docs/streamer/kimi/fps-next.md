# Kimi consultation (2026-10-24 ~12:10 UTC): after B failed

Question: `q-fps-next.txt` (model `kimi-k3.1-pro`, 178 s). Answer, verbatim:

1. **Roll back m4 → m3 now**, but as a controlled experiment, not proof that affinity caused the regression. B failed the gate, and m4's cam2-off ceiling is 56.7 fps: no cam2-only optimization can make that configuration pass. Restore the complete m3 affinity/worker configuration while keeping binary and content unchanged.

2. **Rebaseline before native work.** After warm-up, run **3 × 30-second uncapped windows** for cam2 off, requested 30 fps, and full rate, with identical scene/recording state. Record median/p95 frame, render, RHI and GPU times; main fps; requested/achieved cam2 fps; capture age/drops; and per-core game/render/RHI/worker utilization. If m3 does not reproduce its earlier one-view result, that old note is not a usable baseline. The 5.8/10.2 CPU figure rules out quota saturation, not single-thread saturation or a present stall.

3. **If one-view lacks clear headroom above 60 fps, do option 2 before v22.** `EventWait` is a wait site, not 18 ms of game work. Capture an Unreal Insights CPU/GPU/frame trace and instrument Vulkan acquire/present, RHI flush/fences, and task scheduling; `swap_ms≈0` does **not** exonerate the Xvfb path. Then A/B `r.OneFrameThreadLag=0`, each `r.GTSyncType` mode, and `r.FinishCurrentFrame=1` separately—the last as a diagnostic, not an assumed optimization. Use an offscreen/no-present comparison only if the main view still renders.

4. **Then build v22**, with `bMainViewFamily` A/B-able in the same build. Per capture ID, timestamp `CaptureScene()`, readback callback, encode start/end, and FIFO push/pop using one monotonic clock. Report p50/p95 readback latency, queueing, JPEG time, FIFO age, and drops; verify image correctness. Apply the existing fps gate to **achieved** two-camera output, not requested capture rate.

5. **Option 3 is operations-only:** 58.3 main fps with 21 achieved cam2 fps is neither 60 fps nor 30 fresh captures. Use repeated frames to keep running if necessary, but do not call it a pass.

## Done
- 12:15 UTC: rolled back to m3 (`/tmp/sub01-share/rollback-m3.sh`: cores 0-5, -corelimit=6, default workers, partition
  0-5/6-9). Rebaseline follows.
