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
| 2026-10-24 16:21:08 | sawtooth | live cvar r.NumBufferedOcclusionQueries 1 -> 2 (quick check, then ABBA; restored to 1 at the end) | gc.py 'r.NumBufferedOcclusionQueries 1' |
| 2026-10-24 16:22:20 | sawtooth | trace window occ2-mid (15 s, cpu/frame/bookmark/task via port 1985) | none needed (channels off + Stop at the end) |
| 2026-10-24 16:26:55 | sawtooth | live cvars r.GTSyncType -1 r.NumBufferedOcclusionQueries 2 (exploratory; restored to r.NumBufferedOcclusionQueries 1 / r.GTSyncType 0 at the end) | gc.py 'r.NumBufferedOcclusionQueries 1' 'r.GTSyncType 0' |
| 2026-10-24 16:28:26 | sawtooth | trace window occ2-gts-1 (12 s, cpu/frame/bookmark/task via port 1985) | none needed (channels off + Stop at the end) |
| 2026-10-24 16:31:21 | sawtooth | live cvars r.NumBufferedOcclusionQueries 1 r.GTSyncType 0 r.VSync 1 (exploratory; restored to r.NumBufferedOcclusionQueries 1 / r.GTSyncType 0 at the end) | gc.py 'r.NumBufferedOcclusionQueries 1' 'r.GTSyncType 0' |
| 2026-10-24 16:35:06 | sawtooth | restored live cvars r.VSync 0, r.NumBufferedOcclusionQueries 1, r.GTSyncType 0 (baseline) | n/a |
| 2026-10-24 16:49:30 | sawtooth | ABBA recr60 started: B legs alternate r.VSync 1/0 every 60 s (swapchain recreation, ~85 ms hitch each); A legs r.VSync 0 | touch /tmp/sub01-share/w-sawtooth/toggler.stop; gc.py 'r.VSync 0' |
| 2026-10-24 17:53:58 | sawtooth | relaunch game on m3o = m3 + -RenderOffScreen (v21 binaries; no game window, the director grabs a black :99 meanwhile) | relaunch.sh launch-streamer-game-20261023m3.py streamer-game-20261023m3 |
| 2026-10-24 18:19:59 | sawtooth | relaunch game back on plain m3 (v21 binaries) after the offscreen ablation | n/a (baseline) |
| 2026-10-24 18:33:15 | coordinator | sidecars (8634ff9) + agent-checks code (c59403b) deployed, supervisor restarted with --hls-dir, watchdog restarted | *.bak-before-window + /tmp/sub01-share/cutover-c.sh |
| 2026-10-24 18:35:55 | coordinator | build v22 started (backup: source-backup-before-v22, binaries-v21-linux) | restore both dirs |
| 2026-10-24 18:38:41 | coordinator | build v22 finished BUILD_EXIT=0 | binaries-v21-linux |
| 2026-10-24 18:41:53 | coordinator | v22 built OK (164 s); binaries-v22-linux + source-v22 saved; next launch loads v22 | copy binaries-v21-linux back into Sub01HomeLab/Binaries/Linux |
| 2026-10-24 18:44:38 | sawtooth | relaunch game on plain m3 launcher, now loading the v22 build (new baseline) | restore the v21 binaries backup, then relaunch m3 |
| 2026-10-24 19:09:02 | sawtooth | tune.py cam2_fps 60 -> 30 (operational setting at the end of the sawtooth work) | runuser -u unreal -- python3 /home/unreal/tune.py cam2_fps=60 |
| 2026-10-24 19:10:13 | coordinator | build v23 started (backup: source-backup-before-v23, binaries-v22-linux) | restore both dirs |
| 2026-10-24 19:12:50 | coordinator | build v23 finished BUILD_EXIT=0 | binaries-v22-linux |
| 2026-10-24 19:13:04 | coordinator | v23 built OK (155 s); binaries-v23-linux + source-v23 saved; coordinator owns the runtime again | binaries-v22-linux |
| 2026-10-24 19:13:34 | coordinator | relaunch plain m3 (pid 2015338) on the binaries in place | binaries-v2x-linux + this script |
| 2026-10-24 19:23:02 | coordinator | tune.py elbow_pole_back=0 elbow_pole_out=0.45 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:24:09 | coordinator | tune.py hand_back_cm=5 elbow_min_deg=90 elbow_pole_back=0 elbow_pole_out=0.45 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:25:18 | coordinator | tune.py hide_slot=7 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:26:00 | coordinator | tune.py hide_slot=1 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:27:37 | coordinator | tune.py elbow_pole_out=1.2 elbow_pole_back=0 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:28:19 | coordinator | tune.py elbow_pole_out=0.3 elbow_pole_back=1.2 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:36:03 | coordinator | tune.py hand_back_cm=20 hand_height_cm=-5 elbow_min_deg=100 elbow_pole_back=1.0 elbow_pole_out=0 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:36:46 | coordinator | tune.py hand_height_cm=5 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:37:51 | coordinator | tune.py hand_back_cm=12 pelvis_pitch_deg=-10 typing_lean_deg=-14 shoulder_drop_deg=3 shoulder_back_deg=2 neck_back_deg=5 hand_orient=1 hand_yaw_in_deg=12 hand_pitch_deg=10 finger_bend_deg=8 finger_curl_deg=0 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:38:51 | coordinator | tune.py pelvis_pitch_deg=-6 typing_lean_deg=-10 key_side_cm=-55 key_up_extra_cm=10 fill_cd=0.01 fill_side_cm=45 fill_up_cm=0 fill_temp_k=5000 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:40:37 | coordinator | tune.py posture_lean_deg=-10 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:45:39 | coordinator | tune.py hand_height_cm=9.5 chair_back_extra_cm=2 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:46:45 | coordinator | tune.py typing_lean_deg=-4 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 19:47:44 | coordinator | tune.py fill_cd=0 | previous values in /tmp/sub01-share/tune/tune-log.txt |
| 2026-10-24 ~19:48 | coordinator | tune.py fill_cd=0.01 (fill light back on after the globe-lamp check) | tune.py fill_cd=0 |
| 2026-10-24 21:22:46 | coordinator | director fifo-capable code deployed (x11 mode, default), director restarted | *.bak-before-fifo |

(From 2026-10-24 ~15:40 the rows above are folded in from `/tmp/sub01-share/pod-changes.log` on the pod.)
