# Kimi consultation (2026-10-24 ~12:40 UTC): A/B protocol and the v22 scope

Question: `q-fps-v22.txt` (model `kimi-k3.1-pro`, 269 s). Answer, verbatim:

1. **Decision gate.** Use a fixed replay/scene and identical process settings. After **15 s warm-up**, run **60 s legs** in balanced interleaving: `ABBA`, then `BAAB`—eight legs, four per arm; restart for launch-only CVars. Include an A/A set to measure drift. Compare paired **per-leg median frame-time deltas**, not FPS; also report render/RHI/GPU, p99/max, cam2 rate and drops. Require consistent direction in all four pairs and an effect outside A/A noise. Until calibrated, treat **≤2 ms as inconclusive** and gather more pairs. Thus only `OneFrameThreadLag=0` is decided—reject it. `CpuWaitForFence=0` is promising, not proven.

2. **v22 scope.** Keep `bMainViewFamily`, tested at 60 Hz cam2 with output/cadence correctness checks, and keep the capture timestamps. Add capture/frame sequence IDs, FIFO depth/drops, and split **readback enqueue** from **fence wait/completion**. Retain cam2-off and 30 Hz as controls; their present difference is noise. Test `DelayAcquireBackBuffer=0` and `CpuWaitForFence=0` **separately at launch**, logging effective values; no combined run or default change yet. Add selected swapchain present mode to diagnostics: `t.MaxFPS=0` does not make FIFO presentation uncapped. Drop the promised PERF acquire/present/fence breakdown: game-module public APIs cannot wrap those internal RHI calls, and no suitable public counters are established here. Use existing Insights/RHI events if available; otherwise make an RHI patch or external Vulkan instrumentation a separate task. Drop further GTSyncType/FinishCurrentFrame sweeps.

3. **Main lead.** Not the additive pattern alone: it also occurs with cam2 off, and additive counters do not prove disjoint, non-overlapping work. First verify what the counters include, then put RenderThread and RHIThread on one timeline and distinguish real CPU work from sleep/spin waits. Attribute **acquire-fence, acquire and present time**, while verifying present mode; that directly tests the `CpuWaitForFence` hint. Correlate any RenderThread stall with cam2 readback/fence completion before trying more global sync switches.

## Operational setting until v22 passes (not a pass of the 60/60 gate)
12:40 UTC: `cam2_fps` 30 in the tuning file (Kimi: "use repeated frames to keep running if necessary, but do not call it
a pass"). Measured: main view 59.7-59.9 fps (t.MaxFPS 60), max frame 20-22 ms, render 10.8-12 ms; cam2 27 fps
achieved; director 60 fps at 1.0x with cam2 in the graph. With cam2 at 60 the game ran 45-48 fps and cam2 reached only
27-43 fps (the director drained the FIFO too slowly: `dropped_no_reader_or_full` ~550 per log window).
