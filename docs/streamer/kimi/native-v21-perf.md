# Native v21: 60 fps diagnosis and plan (Kimi consultation, 2026-10-24 ~00:06 UTC)

Model `kimi-k3.1-pro`, 455 s, 26737 completion tokens. Question: `q-native-v21-perf.txt` (measurements
taken live on game l, build v20). A first run hit the 30000-token reasoning cap without an answer; this is the second run
(64000 tokens, questions limited to 6 lines each).

## Kimi's answer (verbatim)

**1. Diagnosis:** Throttling/placement are established contributors; synchronous X11 present is plausible but unproven, and SMT’s independent contribution is not isolated. Per-thread CPU is not critical-path wall time: sleeping waits are invisible, spinning waits look like CPU, and Render→RHI→GPU/present can serialize. Also check swapchain acquire/back-pressure, cam2’s second scene render, readback ring-slot reuse, and JPEG/FIFO waits. Use `swap_ms` plus wall-time markers around acquire/present, capture/readback and writer; RHI CPU≈GPU alone proves nothing.

**2. Partition:** Start with game+Xvfb on `0–5`, others on `6–9`; do not move to `0–6/7–9`. Keep `24–29` idle so nothing shares the game’s SMT siblings. Add `30–33` to “others” only as a later A/B: it may improve throughput, but affinity can then no longer guarantee usage below quota. `-corelimit=6` is reasonable; going lower risks too few UE workers/stalls, not incorrect affinity. Pin every thread at launch where possible and keep monitoring `cpu.stat`; a 10-second rescan is not a hard guarantee.

**3. Feed/offscreen:** Choose raw BGRA; reject 60-fps in-game MJPEG and retain JPEG for the 5-fps snapshot. Use the FIFO for the first ffmpeg-compatible implementation; adopt a timestamped, fixed-slot SPSC shared-memory ring only when its reader is justified by timing/drop requirements or measured copy/back-pressure cost. Offscreen remains a smoke-test item: confirm exact 5.8.3 dummy SDL emits the delegate at 1920×1080 with `-ForceRes -ResX=1920 -ResY=1080`. Query format/stride; accept B8G8R8A8 or explicitly convert/tone-map A2B10G10R10/HDR. Only enqueue in the callback—never wait/`Lock`; manual copies require transfer-src support and correct CopySrc/present transitions.

**4. Order:** Build v21 with P2, P3, switchable minimal cam2 show flags, and the additional wall-time/format probes; compile P4 default-off only if isolated and useful for avoiding another build. Relaunch **windowed** with P1, not offscreen. A/B no reader, real reader, cam2 off, and x11grab paused, then use live cvar tests; keep the old game until viewer/director/recording validation passes. If acquire/present dominates, stage offscreen plus the main feed as a coordinated three-component change; otherwise fix cam2/readback. Do not deploy `-RenderOffScreen` while the viewer rejects it.

## Decision taken
- v21 = P2 (PERF thread/swap times, live whitelisted console channel, shorter perf window) + P3 (cam2 renders only for a
  reader) + switchable lite cam2 capture flags + the visual fixes; NO main-view feed (P4) in this build and no
  `-RenderOffScreen`: the 8893 viewer rejects offscreen games on purpose, and Kimi asks for proof that present dominates first.
- Game m relaunched WINDOWED with P1: the game started on physical cores 0-5 (launcher affinity, `-corelimit=6`), Xvfb :99
  pinned with it, everything else of uid 1001 on 6-9, SMT siblings 24-29 left idle; `cpu.stat` monitored.
- A/B on m: no reader / real reader / cam2 off / x11grab paused, then live cvars through the console channel.
