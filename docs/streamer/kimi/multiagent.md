# Multi-agent split and measurement ownership (2026-10-24 ~15:45 UTC)

Question: `q-multiagent.txt` (same folder). Kimi's answer (kimi-k3.1-pro, 311 s):

### a) Split and sequencing

The split is mostly right, with one hard change:

- **Let v23 prepare code/assets offline now**, pinned to a specific v22 commit, but defer installer finalization, building, deployment and especially live tuning until **v22 is merged and sawtooth has finished its measurements**. As written, v23’s live tuning conflicts with sawtooth’s exclusive runtime ownership. Different files do not prevent changes to GPU load, lighting or the visual baseline.
- Keep 1 and 2 repo-only and 5 offline. Agent 6 can develop offline, but its “read-only” log dry run still consumes CPU/I/O and must be scheduled outside measurement windows.
- The coordinator should maintain one timestamped **build/deploy/restart/change log**, retain a v22-only artifact for A/B and rollback, and run an integrated v22+sidecar privacy/stream smoke test before v23.
- Sawtooth should leave cam2/exposure keys unchanged unless a specific hypothesis requires them. “Finish on the baseline launcher” should also mean restoring cvars/configuration and verifying a final baseline run.

### b) Measurement ownership

**No—game-runtime ownership is necessary but insufficient.** Use a coordinator-held, whole-pod measurement lease:

- No UE/sidecar builds, deployments, service restarts, v23 tuning, Chromium/PC workload changes or acceptance log scans during captures.
- Remove the heavy-CPU exception for sawtooth during measurements. Trace analysis can also perturb subsequent legs through CPU load and heating; run it afterward, or with the game idle and the load/thermal baseline re-established.
- Hold scene, cameras, resolution, recording/HLS/MJPEG state and trace settings constant. Log per-process load, cgroup throttling, GPU clocks/temperature/power/VRAM and every exceptional event.
- Compare matched ramp phases, not arbitrary 40-second averages. For ABBA, each leg should cover at least two nominal cycles—about **14 minutes per leg, 56 minutes minimum for ABBA**—with identical tracing. Compare ramp slope, start-to-end delta and frame-time percentiles, not just leg averages.

### c) Sawtooth mechanisms to check first

The mechanism **cannot be named from the two CPU windows alone**. Do not add the scope deltas blindly: `EndDrawingViewport` and `WaitForTasks` may expose the same back-pressure. RDG’s increase is potentially **0.39 ms × 6 = 2.34 ms/frame** if those calls are critical-path and non-overlapping; DirectLighting + Radiosity + WorldTick contribute only **0.160 ms** combined.

Check in this order:

1. **Real GPU slowdown versus presentation/back-pressure accounting.**  
   Confirm that wall-frame time/FPS actually ramps. Capture matched GPU timestamps and lightweight clock/power/temperature telemetry.
   - If GPU pass times rise while clocks fall, prioritise thermal/power policy or external GPU contention; a fixed-clock run is a diagnostic, not automatically the fix.
   - If GPU pass times and clocks stay flat while acquire/present waits grow, investigate the Vulkan present path: separate acquire, present, submission and fence waits; inspect present mode, swapchain image count/queue depth, frame limiter/vsync, compositor/Chromium/capture activity and swapchain recreations. `EndDrawingViewport` is then probably the wait sink, not the root cause.
   - If GPU times rise at stable clocks with unchanged pass counts, investigate growing GPU work, memory pressure or queue/resource behaviour.

2. **RDG/RHI overhead or resource growth.**  
   Because RDG exclusive time grows while other pass scopes are flat, measure per-frame pass/barrier/allocation counts, command-buffer submission/fence waits, descriptor/pool usage, VRAM and process RSS. Look specifically for a counter that grows throughout a ramp and drops at reset.

3. **The approximately 420-second reset.**  
   In parallel, cheaply correlate it with UE GC/purge/cache trims, swapchain recreation, director/camera changes, watchdog or service restarts, browser/recorder activity, and log/segment rotation. Also check CPU clocks/cgroup throttling. A matching event plus a targeted intervention is much stronger evidence than another A/B average.

Do not start with lighting or exposure tuning; those small scope increases are currently secondary symptoms at best.

## Coordinator decisions
- Adopted: a whole-pod **measurement lease**. The sawtooth worker writes `/tmp/sub01-share/MEASURING` (end time and
  purpose) while it captures; nobody runs builds, deploys, restarts, scans or heavy jobs while it exists, and the
  sawtooth worker itself runs trace analysis only outside its capture windows.
- Adopted: v23 is prepared offline now, pinned to the v22 commit once v22 is merged; its build and live tuning wait
  until v22 is merged and the sawtooth measurements are finished.
- Adopted: ABBA legs of about 14 minutes (two ramps) with identical tracing, judged on ramp slope, start-to-end delta
  and percentiles; GPU clocks/power/temperature/VRAM and cgroup throttling logged alongside.
- Adopted: the sawtooth check order (GPU slowdown vs present back-pressure, then RDG/RHI resource growth, then
  correlating the ~420 s reset with events).
- Adopted: a coordinator change log of builds, deploys and restarts; a v22-only artifact kept for A/B and rollback;
  an integrated v22 + sidecars privacy/stream smoke test before v23.

## Pre-commit review of the handoff diff (kimi-k3.1-pro, 150 s)

APPROVE
