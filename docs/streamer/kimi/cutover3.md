# Kimi consultation (2026-10-24): next cut-over (director v2, single PC source, 60 fps with two cameras)

1. **Baseline, then director v2.** Save v21/director commands and record the same 120-second route: game FPS/`stat unit`, render-thread ms, per-process CPU on cores 69, and cgroup throttling. Leave 8894 untouched. Preflight 8838: fresh, correct `/pc/frame.png` at ~2 Hz, clean full-screen :103, and agent click/type verified. Start v2 on :102 with **one `h264_nvenc` encode**, HLS mux/tee only. **Keep cam2s reader open and draining even off-air.** Accept 4547 FPS temporarily: this gives seamless layouts and a repeatable dual-view baseline; on-demand hides the cost at 57 FPSstill not 60and adds a 12-second gap.

2. **Gate before publishing/cut-over.** A 120-second local recording must show `h264_nvenc`, not `libx264`; `fps=60`, `speed1.00x`; advancing HLS segments; no FIFO underruns/drops; and `ffprobe` reporting 60/1. Inspect voice sync, PiP and every layout. Investigate any game regression from the 4547 baseline: a 60-FPS encode can merely duplicate 46-FPS frames. On failure, restore director v1 and close cam2s reader; expect approximately 57 FPS.

3. **One source migration; retire later.** Repoint agent8838 and PiP:103, then make a 60-second source recording **before** touching the game. If clean, perform the single ~8-minute relaunch using v21s existing `SUB01_PC_ORIGIN` format, changing only 88328838. Verify the resolved origin and fresh in-game texture, then record three minutes covering input, voice, PiP, cam2 and layouts; soak for ten minutes. Keep 8832 restorable until everything passes, then stopnot deleteits Chromium and Python. Rollback is agent/:102 plus 8832; restoring the old game origin costs another ~8-minute relaunch. No hot switch exists.

4. **CPU/performance checks.** Repeat baseline metrics after every step. Stopping 8832 should free 1.15 CPU-equivalents on cores 69; NVENC savings are unknown until measured. Remove duplicate grabs/encodes. Cap TTS CPU threads at 12 and queue bursts only if speech latency still passes. Do not repin cores tonight.

5. **Rank for genuine dual-camera 60.**  
   1. **Static/baked/cached house shadows**, retaining dynamic shadows for the streamer/moving props: highest potential, medium effort, attacking shadow depths ~79% of 2340 draws.  
   2. **Cam2 shadow-show-flag A/B:** cheap, but revert unless draws/render time actually fall; shadow work may be shared with the main view.  
   3. **720p960540:** cheap, but mostly raster/JPEG savings, likely smaller render-thread gain.  
   4. **30-Hz cam2:** diagnostic/fallback only; repeated frames are not 60 Hz, and current frame times imply only roughly 51 FPS average.

Exact gains require profiling. Final gate: ten minutes at genuine 60 FPS with both cameras, frame-critical times below 16.67 ms, and no output drops or increased quota throttling.
