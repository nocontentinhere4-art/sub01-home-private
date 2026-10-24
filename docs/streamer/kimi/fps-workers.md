# Kimi consultation (2026-10-24 ~11:45 UTC): 60 fps with two cameras: shadows or task workers?

Question: `q-fps-workers.txt` (model `kimi-k3.1-pro`, 243 s). Data gathered on the live game m3 (build v21) before asking.

## Measurements (game m3, main view + cam2 1280x720 with a reader, t.MaxFPS 60)
Runtime A/B through the private live console (`streamer-visual-console.json`; 12 s settle + three 10 s PERF windows;
noise about +-2 fps between identical baselines):

| variant | fps | frame ms | render ms | GPU ms |
|---|---|---|---|---|
| baseline (sg.ShadowQuality 3, VSM on) | 51.7 | 19.4 | 16.2 | 10.7 |
| sg.ShadowQuality 2 | 52.0 | 19.2 | 15.9 | 10.6 |
| VSM resolution bias directional 0 / local 1 | 50.6 | 19.8 | 16.5 | 10.5 |
| r.Shadow.RadiusThreshold 0.03 | 49.5 | 20.2 | 16.9 | 10.6 |
| VSM off + 3 CSM cascades | 39.5 | 25.3 | 21.4 | 15.0 |
| all shadows off (sg.ShadowQuality 0) | 52.2 | 19.2 | 15.3 | 8.8 |
| cam2 lite (tuning `cam2_lite` 1) | 51.1 | 19.6 | 16.3 | 10.5 |

The project runs Vulkan SM6 with virtual shadow maps (`r.Shadow.Virtual.Enable 1`, cache on), Lumen GI and reflections,
TSR. Shadows cost under 1 ms of render thread: the shadow-depth hypothesis from `native-v21-final.md` does not hold.

CSV profile (`csvprofile frames=600`): RenderThreadTime 18.1 ms; exclusive EventWait **4.54**, RenderOther 4.49,
FetchVisibilityForPrimitives 1.96, RDG 1.79, RDG_CollectResources 1.48, RenderShadows 1.49, ShadowInitDynamic 1.30.
The engine (UE 5.8.3) had 5 task workers under `-corelimit=6`: **2 foreground** + 3 background
(`TaskGraph.cpp`: `GNumForegroundWorkers = max(ceil(N/21), 2)`, `-foregroundworkers=N` overrides). Every
parallel-rendering cvar was already on.

## Kimi's answer (verbatim)

1. **Order: C → B; skip A as a standalone relaunch.** C is free and is B's precondition, although disjoint CPU affinity, no throttling, and game CPU at 355%/600% make direct contention unlikely. Retire 8832 and the 8893 grab, measure briefly, then—unless unexpectedly fixed—use one private-stream relaunch for B. With `-corelimit=7`, N should be 6, so `-foregroundworkers=4` gives **4 foreground + 2 background workers**. Verify that and the affinity in the log. The named remaining load is approximately 163% on cores 7–9, leaving reasonable headroom; also watch director/ffmpeg for dropped frames.

2. **Use identical measurements:** warmed-up route, main view plus the 1280×720 cam2 reader, recording active; three 120-second windows, render-thread CSV, then a 20-minute hitch soak for the accepted configuration. For C, a result within the **±2 fps noise** and less than roughly **1 ms render-thread improvement** means "no useful effect"; proceed to B. Call either configuration successful only with **sustained 59–60 fps**, average `RenderThreadTime` **≤15.5 ms**, and `RenderThreadTime_CriticalPath` **<16.0 ms**, without recurring reader/recording stalls. Reject B as a 60-fps solution if it remains below 58 fps or critical path stays ≥16.67 ms. `EventWait` should fall materially from **4.54 ms** if worker queuing was the problem, but it is diagnostic—not an independent rejection gate.

3. **A's single background worker is a queueing risk, not certain breakage.** Dedicated IO/async-loading/RHI threads remain, but work actually assigned to background task-graph workers can serialize: streaming activity, background PSO/shader work, and possibly cam2 JPEG encoding. That can produce hitches despite good average FPS. Which queue the JPEG encoder uses cannot be determined from the supplied material; inspect or instrument it. B mitigates this risk but does not eliminate it.

4. **If B fails, do not try more shadow/core permutations.** Instrument cam2 readback → JPEG encode → reader delivery with timestamps and queue depth. The reader remains the strongest lead because removing it alone restores 60 fps.

5. **Do not activate the 8832→8838 origin switch in this relaunch.** With Vagon off, 8838 cannot be validated end-to-end, and coupling it complicates rollback. Stage its configuration if useful; switch and test separately when the PC is up.

## What was done
- C (11:48 UTC): the supervisor's desktop child is now the Vagon runner (8838, Google Chrome on :103; director PiP
  from :103, agent and watchdog on 8838); the bundled-Chromium runner 8832 and the 8893 viewer grab are stopped.
  Game fps unchanged (51.9, render 16.0): no useful effect, as predicted.
- B (11:56 UTC): game **m4** = m3 + cores 0-6, `-corelimit=7 -foregroundworkers=4` (log: 4 foreground + 2 background
  workers), the partition loop on `--game-cpus 0-6 --other-cpus 7-9`; `SUB01_PC_ORIGIN` unchanged (8832).
  The cam2 JPEG encoder runs on `AnyBackgroundThreadNormalTask` (install_cam2.py), i.e. the background workers.
