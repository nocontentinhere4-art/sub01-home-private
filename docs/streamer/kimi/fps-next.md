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
- 12:22 UTC: the bundled runner 8832 restarted standalone (game m3 polls `SUB01_PC_ORIGIN` 8832: 14 connection errors
  per second, ~26 MB/hour of log, while it was down); agent, director and watchdog stay on 8838.
- Rebaseline on m3, uncapped (`t.MaxFPS 0`), 3 x 30 s windows (script `/tmp/sub01-share/ab2.sh`, per-thread CPU from
  /proc):

| case | fps | frame ms | render | RHI | GPU | cam2 fps | max frame ms |
|---|---|---|---|---|---|---|---|
| cam2 60 requested | 48.2 | 20.8 | 17.6 | 4.0 | 10.6 | 43.4 | 1381 |
| cam2 off | 59.2 | 16.9 | 13.1 | 2.6 | 7.0 | 0 | 347 |
| cam2 30 requested | 61.1 | 16.4 | 13.6 | 3.2 | 8.5 | 28.8 | 35.8 |

  No thread saturated (render thread 50-70% of a core, RHI 60-71%); frame ~= render + RHI in every case.
- Sync A/B (30 s, cam2 full, uncapped; baselines of the same config varied 44.1-51.3 fps): `r.GTSyncType 1` 50.4
  (cam2 50.5), `2` 49.4, `r.OneFrameThreadLag 0` 26, `r.FinishCurrentFrame 1` 47.2, `r.Vulkan.CpuWaitForFence 0` 53.8
  (baseline just before: 44.1); `r.Vulkan.DelayAcquireBackBuffer` is read only at RHI init. Next: `q-fps-v22.txt`.
