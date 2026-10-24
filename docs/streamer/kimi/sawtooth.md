# Kimi consultation (2026-10-24 ~13:30 UTC): the render-thread sawtooth and the allocator

Question: `q-sawtooth.txt` (model `kimi-k3.1-pro`, 211 s), after these findings on game m3:
- the "+-5 fps noise" is a **sawtooth**: the render thread time rises ~0.5 ms per minute (15.3 -> 18.9 ms with cam2 on,
  9.4 -> 13 ms overnight without cam2) and drops back at every garbage collection (CSVEvent "GC", period ~7 minutes);
  at a drop only `Exclusive/RenderThread/EventWait` moves (4.9 -> 2.6 ms); GPU, instance count and draw calls are flat;
  per-thread CPU and host load are flat;
- stopping the in-game monitor's frame source (the PC bridge creates a new UTexture2D per frame) did NOT stop the rise;
- the process runs Mimalloc (editor default) and the engine calls `FMemory::Trim()` (mi_collect) after a GC;
- `r.Vulkan.CpuWaitForFence` is read-only at runtime, so its earlier A/B legs were A/A (no conclusion on it).

## Kimi's answer (verbatim)

1. **Run Binned2 next; change nothing else.** Keep the current GC cadence and fence settings, reproduce scene/camera/warm-up, and verify the startup log actually reports Binned2. Capture GC/Trim timestamps, RenderThreadTime, EventWait, RenderOther, FPS and RSS for **≥3 GC intervals (~25 minutes)**. If it appears fixed, repeat Mimalloc immediately; ideally use A/B/A rather than relying solely on the historical baseline.

2. **Accept only a differential pattern:** Mimalloc reproduces approximately **+0.5 ms/min** and the **~3 ms GC-aligned reset**; Binned2 has fitted slope **|slope| <0.1 ms/min**, no GC-aligned step **>0.5 ms**, no EventWait ramp, and FPS between GCs within **~1 FPS** of its own post-warm-up mean. That supports, but does not prove, Mimalloc causation. The same ramp/reset under Binned2 strongly falsifies the proposed Mimalloc-specific mechanism. Intermediate results are inconclusive.

3. **For causal confirmation,** add a temporary game-thread exec hook calling only `FMemory::Trim()` at a Mimalloc peak, without GC. A repeatable immediate fall toward **15.3/2.6 ms** for RenderThreadTime/EventWait, followed by the same ramp, directly implicates Trim. No fall means Trim alone is not the reset mechanism. Use 30-second GC only afterward as diagnostic/mitigation, verifying actual GC events; expected sawtooth amplitude is **~0.25 ms**, but recurring hitches make it a poor fix.

4. **Editor risk:** allocator switches may be ignored or poorly tested in editor builds and change whole-process RSS/virtual-memory use, performance and stability. Soak save/load/shutdown before adoption; instability is a compatibility result, not evidence about the sawtooth. Do not shotgun Binned3/Ansi as diagnostics. Test `CpuWaitForFence=0` separately later. Also, flat CPU% is not flat work/frame when FPS changes: `CPU ms/frame = 1000 × (Δcpu/Δwall) / FPS`.

## Done
- 13:32 UTC: game **m3b** = m3 + `-binnedmalloc2` (log: "Memory allocator used: Binned2"), launcher
  `/root/.sub01-windows-recovery/launch-streamer-game-20261024m3b.py`, everything else unchanged (cam2 60, t.MaxFPS 60).
  CSV profile of 100000 frames from 13:40 UTC for the GC cycles.
- Result (13:36-13:48 UTC, m3b with Binned2): the ramp is unchanged (render 14.9 -> 18.2 ms in 6 minutes, ~0.55 ms/min);
  with Binned2 the engine runs a GC every ~61 s and those GCs do NOT reset it; the reset came ~7 minutes after the
  streamer started (13:43:50), as before. By Kimi's gate this falsifies the Mimalloc-specific mechanism. The reset is
  tied to something with a ~7-minute period, not to GC as such (the bedroom TV video loops every 10.6 min; the house has
  no running clock; the PC-frame textures are not it).
- 13:48-14:00 UTC: game m3t (Mimalloc + `-trace=default,task -tracefile`): 3.5 GB in 12 minutes (~460 MB/min after
  warm-up), moved to `/workspace/sub01-traces/m3t.utrace`. Headless Unreal Insights (`-NoUI -AutoQuit
  -ExecOnAnalysisCompleteCmd="TimingInsights.Export..."`) was OOM-killed analysing it (container limit 31 GB). Next: a
  small trace, the `cpu` channel switched on only for two ~40 s windows (start and end of a ramp) through the trace
  control port 1985 (`ToggleChannels cpu 1|0`), then `TimingInsights.ExportTimerStatistics -threads=... -startTime=
  -endTime=` per window.
- 14:00 UTC: back on plain m3 (Mimalloc, no trace).
