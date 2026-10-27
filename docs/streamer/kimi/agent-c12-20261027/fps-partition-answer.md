Plan: try `cam2_lite=1` first, then test CPU partitioning only if it doesn’t deliver ≥55 stable fps.
`cam2_lite` directly reduces the render-thread bottleneck and is cheaper/safer to roll back live; compare two 10 s windows in the same scene.
If still short, restore visual settings if needed and run your proposed `--once` split unchanged: CCD0’s 8 physical cores are ample for ~350% game load, with idle SMT siblings protecting latency.
CCD1 with SMT also has enough capacity for the other workloads; do not add CCD0 siblings or cross-CCD game affinity initially.
Revert partitioning immediately if fps/1% lows or `perf_render_ms` worsen, `perf_game_wait_ms`/RHI rise, `nr_throttled` increases, or capture/WebRTC/audio shows drops.
Keep whichever change reaches ≥55 stable across both windows; prefer partitioning alone if it suffices, otherwise combine them.
