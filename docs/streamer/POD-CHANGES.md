# Pod change log (builds, deploys, restarts, runtime changes)

Pod `3u7g6drf5fiiql`. One line per change, UTC. Measurements are only comparable between two lines of this log.
Started 2026-10-24 on Kimi's advice (`docs/streamer/kimi/multiagent.md`); earlier entries are reconstructed from
`HANDOFF.md`.

| UTC | Who | Change | Rollback |
|---|---|---|---|
| 2026-10-24 10:35-10:55 | coordinator | disk-full recovery: overnight recordings deleted, backend restarted (`resume21.py`) | - |
| 2026-10-24 11:20 | coordinator | network volume 150 → 200 GB, idle root folders offloaded to `/workspace/sub01-root-offload/` | symlinks in place |
| 2026-10-24 11:35 | coordinator | director retention deployed (25d17a8) | previous `scripts/streamer_director.py` |
| 2026-10-24 11:48 | coordinator | supervisor restarted as the one desktop source 8838 (`/tmp/sub01-share/cutover-c.sh`); watchdog on 8836/8838 | `/tmp/sub01-share/rollback-20261024-1150.txt` |
| 2026-10-24 11:56 | coordinator | game m4 (cores 0-6, `-corelimit=7 -foregroundworkers=4`) | m3 launcher |
| 2026-10-24 12:15 | coordinator | game back on m3 (m4 rejected) | - |
| 2026-10-24 12:22 | coordinator | director speed guard deployed (dd15704); runner 8832 standalone again for the in-game monitor; director layout `webcam_only` | - |
| 2026-10-24 13:39 | coordinator | RunPod balance guard paused (`kill -STOP 63`) during the account's API rate limit | `kill -CONT 63` (due ~00:20 UTC) |
| 2026-10-24 ~13:00-14:00 | coordinator | game m3b (`-binnedmalloc2`) and m3t (trace) test runs | m3 launcher |
| 2026-10-24 14:00 | coordinator | game m3 relaunched (pid 1993395) | - |
| 2026-10-24 ~15:00 | coordinator | `tune.py cam2_fps=60` for the sawtooth tests (operational value 30) | `tune.py cam2_fps=30` |
| 2026-10-24 15:20, 15:24 | coordinator | trace windows A and B via port 1985 | - |
| 2026-10-24 ~15:40 | coordinator | sawtooth worker takes ownership of the game runtime (see `HANDOFF.md`, workers in flight) | - |
