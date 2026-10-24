# SUB-01 handoff (read first; re-injected after every compaction and at session start)

Last update: 2026-10-24 12:15 UTC (structure reviewed by Kimi: `docs/streamer/kimi/handoff-review.md`).
Keep it current: update at every milestone and before ending a turn that changed the plan. Older history:
`docs/HANDOFF.md` (2026-10-02 and earlier, partly stale).

## Main goal
SUB-01 is a simulated 20-year-old streamer in a native Unreal Engine 5 home on a RunPod GPU pod. Goal: the first
complete streaming version, later live on the owner's site subzerone.live (only when he asks). He stays at his desk,
uses the owner's real PC (Vagon Computer, Windows 11, Steam with Detroit: Become Human), browses and plays, speaks
English with his own voice (K07), answers and really executes chat requests, looks real (posture, chair, hands on
keyboard/mouse, head/mouth with the voice), is filmed by two cameras at once (frontal webcam + a camera from behind
showing the house and him at the PC), at 60+ fps, composed and recorded by the director, with logs, recovery and a
kill switch.

Until the owner authorises publication, "streaming version" means a **private pod-only recording / local-HLS
demonstration**. Completion requires: proven keyboard/mouse control of the same Vagon session seen by the monitor, the
agent and the director; safe chat execution and refusal; both cameras composed simultaneously; K07 speech with
head/mouth motion; a final soak showing logs, recovery and the kill switch; the owner's approval of the look.

Owner decisions (2026-10-23 21:45 UTC):
- **60 fps on everything**: game render, both cameras (cam 2 included), the in-game monitor feed, the recording and
  HLS. Proven by measured fps in logs (game PERF line, cam2 status, director per-segment fps), not by caps.
- **Chat source = the chat on his site** (subzerone.live), which sends impulses to SUB-01's brain (site WebSocket
  `/ws` → `live_server.handle_chat` → impulse/brain + streamer chat batches to the agent).
- **All sites and all games are approved.** Still blocked by design (owner's standing rules and a public stream):
  purchases/payments/wallets and adult content. Tell the owner if a request hits these; he can override explicitly.
- **Downloads and installs enabled** (owner, ~21:55 UTC; `--allow-installs`, default on): SUB-01 may download and
  install on the owner's PC (Steam game installs included; purchases still blocked). Chat-driven installs only from
  official stores/vendor sites, never from a file link pasted by a viewer.
- **Credentials block lifted** (owner, ~21:50 UTC: "Può accedere a tutto quello che vuole"): SUB-01's own decisions may
  log in, use logged-in sessions and account pages on the owner's PC (`--allow-credentials`, default on). Kept: chat
  viewers cannot direct credential or account changes (the owner's original chat rule; he may lift it too); typed
  secrets are never spoken, captioned or logged; the director cuts to the webcam layout while a login/account page is
  on screen.
- "Looks real" is accepted by the visual-QA matrix plus his approval.

## Working rules (non-negotiable)
- **Kimi is the partner in every piece of work, with or without agents** (owner, 2026-10-23). Every agent, the
  coordinator included, consults Kimi (`kimi-k3.1-pro`, `tools/ask_kimi.py` on the pod, `--file`, `--image`) BEFORE a
  design decision and has the diff or frames reviewed by Kimi BEFORE EVERY COMMIT; reports carry a "Kimi review"
  section; consultations are saved in `docs/streamer/kimi/`. See `CLAUDE.md`, `docs/streamer/KIMI.md`.
- No public stream, deploy to Railway/`main`, purchases or credential changes without the owner's explicit request.
  "Deploy" here means copying files to the pod only; HLS stays local/private.
- Secrets never in git, logs or chat. On the pod (mode 600, uid 1001): Anthropic key `/home/unreal/.sub01-private/anthropic-key`
  (it was pasted in chat once: rotation advised, not yet done), Kimi key `/home/unreal/.sub01-private/kimi-key`,
  operator token `/home/unreal/.sub01-private/operator-token`. The pod's Jupyter token is supplied by the owner's RunPod
  pod environment and kept only in the session scratchpad `pods.json`; never print it.
- The owner writes Italian; answer in Italian (never Spanish). Commits carry only the attribution trailers.
- Branch `claude/happy-einstein-1x0561` (repo `nocontentinhere4-art/sub01-home-private`, checkout
  `/home/user/sub01-home-private`). Commit and push each verified, Kimi-reviewed deliverable.
- Before any restart or build on the pod: disk preflight (`df -h /`, keep > 3 GB; the backend refuses below 3 GB).
- The agent stays held (STOP file) during cut-overs; it is resumed only after its guard rails pass.

## Plan (ordered; Kimi-reviewed; each step has a done-criterion)
1. **Integrate worker outputs without runtime cut-over** — tests pass, Kimi artefacts and report sections exist,
   commits pushed, rollback baseline recorded (last-known-good commit and game k launcher).
2. **Native game k → l (build v20)** — hands/posture/key light/cam 2 verified on frames, 60 fps measured
   (`SUB01_STREAMER_VISUAL_PERF` p50/p95 frame ms, cam2 achieved fps), game k restorable from its launcher. If 60 does not
   hold, Kimi's order: async readback ring + minimal SceneCapture show flags, TTS concurrency, then UE scalability
   (Lumen/shadows/post), then ffmpeg/browser CPU. The 60 fps in-game monitor feed follows in v21.
3. **Director cut-over (local)** — recording and local HLS show both cameras, the desktop layouts, the NVENC path with
   its fallback, and the agreed fps metric.
4. **Vagon input proven, then ONE canonical desktop source** for the monitor, director and agent (no 8832/8838 split);
   agent still held — benign before/after frames prove keyboard and mouse.
5. **Agent provider and safety controls** (decided with Kimi, `docs/streamer/kimi/cutover.md`): Claude primary, Kimi
   fallback AND Kimi in shadow on every decision (same frame, its proposal logged and compared: latency, JSON validity,
   click-in-target, cost per correct action) for a 30-minute trial before any promotion. Code guard rails before any
   unattended run: deny-by-default action broker, decisions bound to frame id + freshness re-check before dispatch,
   caps (3 actions/decision, 20/min, stop after 3 consecutive failures), 60-minute lease with manual re-arm, frozen or
   black stream = stop, independent watchdog that releases keys, append-only audit (frame hashes, raw JSON, actions).
   Recommend to the owner a dedicated non-admin Windows account on the Vagon PC with no saved passwords/payments.
   Done: allowed/refused actions, logging, fault recovery and STOP halt/resume pass before chat or unattended runs.
6. **Visual polish loop** — QA findings closed, frame reviews saved with Kimi, the owner approves the look.
7. **30-minute acceptance recording** — activity change, executed and refused chat, a recovered error, both cameras,
   voice + head/mouth, Vagon control, measured fps; highlights delivered to the owner.
8. **subzerone.live only on explicit request** — the requested private embed/platform test passes; publication is a
   separate authorisation.

## Last-observed state (2026-10-24 ~12:15 UTC; verify before relying on it)
Pod `3u7g6drf5fiiql` (RTX PRO 4000 24 GB; container CPU quota 10.2 CPUs; root disk ~11 GB free after the offload).
- INCIDENT 2026-10-24 08:25 UTC: the director recorded all night (60 MB/10 min), the root disk hit 100%, the
  supervisor and the backend crashed ("No space left on device"), Jupyter kernels could not start (use the terminal
  channel: scratchpad `podterm.py`). Recovered 10:35-10:55: overnight recordings deleted, backend restarted
  (`resume21.py`; coordinator reserve lowered 3 → 2.5 GB, backup `*.bak-3gb`), services restarted. Director retention
  deployed 11:35 (commit 25d17a8, Kimi-reviewed twice: at most 18 segments, keeps >= 3 GB free, ~160 MB per 10-min
  segment at 60 fps NVENC); the temporary cleanup loop is stopped.
- Storage (owner approved 11:20 UTC): network volume `dvrlt6yk2k` (`/workspace`, EU-RO-1) grown 150 → 200 GB
  (increase-only, +$3.5/month). Idle root-disk folders moved to `/workspace/sub01-root-offload/` with a symlink left in
  place: `/home/unreal/hf-cache` (voice models), `.sub01-private/{community-demo,desk-final-endpoint-candidate4,
  desk7-body-v5,postproduction-20261022}`. `/workspace` (MooseFS) shows everything as root 0777; it cannot chown.
  NEVER grow the container disk: "Edit Pod" resets the pod and wipes everything outside `/workspace`.
- Zen DDC rotated logs (~600 MB of overnight disk-full warnings) deleted.
- Vagon computer seen OFF at 11:10 (idle auto-stop). Since 11:48 the Vagon page asks for the owner's login again
  (`phase login_required`; the session from 2026-10-23 evening expired): the owner must log in at the operator console
  `https://<pod>-8888.proxy.runpod.net/proxy/8838/operator`, then arm a start (`POST /pc/vagon/arm {"minutes":N}`,
  $0.99/h from his balance) before any PC work.
- Native game **m4** (build v21, Kimi fps-workers step B, 2026-10-24 11:56): pid in `streamer/game.pid`, launcher
  `/root/.sub01-windows-recovery/launch-streamer-game-20261024m4.py` = m3 + cores 0-6, `-corelimit=7
  -foregroundworkers=4` (4 foreground + 2 background task workers), log `streamer-game-20261024m4/game.log`;
  `SUB01_PC_ORIGIN` still 8832 (stopped: the in-game monitor shows no fresh picture until the origin switch).
  CPU partition loop: `streamer_cpu_partition.py --game-pid-file streamer/game.pid --game-cpus 0-6 --other-cpus 7-9
  --interval 10` MUST run. Measured on m4: 44-50 fps with cam2 read (render 16-19 ms), 56.7 without cam2 (render 13.3),
  58.3 with cam2 at 30 fps: B gave no gain (rejected by Kimi's gate; `docs/streamer/kimi/fps-workers.md`, next step
  asked in `q-fps-next.txt`). Rollback to m3: kill m4, run the m3 launcher, partition 0-5/6-9, write game.pid.
  Shadows are NOT the bottleneck (runtime A/B: all shadows off saves <1 ms). Live console helper
  `/tmp/sub01-share/gc.py 'r.Foo' 'r.Bar 1'` (as unreal; sequence in ms), A/B script `/tmp/sub01-share/ab2.sh`,
  CSV profiles via `gc.py "csvprofile frames=600"` (Saved/Profiling/CSV), summary `/tmp/sub01-share/csvsum.py`.
  Live tuning via `runuser -u unreal -- python3 /home/unreal/tune.py key=value` (`cam2` 0/1, `cam2_fps`, `cam2_lite`,
  `key_cd` 0.04). Visual bugs: `docs/streamer/VISUAL-QA-20261023.md`. The 8893 viewer is stopped (its x11grab cost
  ~0.45 CPU); its command is in `/tmp/sub01-share/rollback-20261024-1150.txt`.
- Supervisor (pid file `streamer/pids/supervisor.pid`), restarted 11:48 as the ONE desktop source (Kimi step C):
  `streamer_up.py start ... --display :103 --desktop-port 8838 --library-path /usr/local/cuda/lib64` + child args
  (exact command: `/tmp/sub01-share/cutover-c.sh`; every later `status`/`restart` needs `--display :103 --desktop-port
  8838`). Children: desktop = the Vagon runner 8838 (Google Chrome on :103, profile `streamer/desktop-vagon/profile`),
  voice 8835, agent 8836 (HELD by STOP; desktop URL 8838), director 8837 (`--fps 60 --desktop-fps 60 --encoder
  h264_nvenc --hls-dir streamer/hls`, PiP from :103, retention, 60 fps at speed 1.02 measured with and without cam2 in
  the graph). The bundled-Chromium runner 8832 is retired (not deleted). Start the supervisor from a shell pinned to
  7-9 or restart the director once after start: a director launched during the voice model load ran at 0.70x
  (speed guard in `scripts/streamer_director.py`, deployed 12:22, commit dd15704: it relaunched a 0.76x run at 12:32).
- Sources on the pod: Python services `/home/unreal/.sub01-private/latest-source-20261023`; native project
  `/home/unreal/.sub01-private/cinematic-source-v3-final` (`build-worker-vNN.sh`, logs `build-vNN.log`).
- Backend: coordinator `/root/.sub01-windows-recovery/resume21.py` (ports 8830/8831); streamer hold re-armed with
  `POST /api/home/streamer {"operation":"start"}` (X-Admin-Token).
- Watchdog `scripts/streamer_watchdog.py` restarted 11:48 on the agent 8836 and desktop 8838
  (`--desktop-data-dir streamer/desktop-vagon`); the agent needs STOP removed and `POST /lease` (only after plan step 5).
- Sidecars not yet supervised: `scripts/streamer_hls_serve.py` (127.0.0.1:8839, local HLS),
  `scripts/streamer_monitor_feed.py` (:103 → `streamer/monitor.mjpeg`, health 8840, for the in-game monitor feed).
- **RunPod balance guard PAUSED** (13:39 UTC, `kill -STOP 63`): the owner's RunPod account hit an API rate limit
  ("wait 37550 seconds", until ~00:05 UTC 2026-10-25). `/root/.sub01-windows-recovery/guard-v3.py` (pid 63, the OLD
  version: reads `clientBalance` every 300 s and stops the pod at <= $10, ignoring Retry-After) was blind during the
  block anyway. Resume with `kill -CONT 63` after the block (scheduled reminder 00:20 UTC); the Retry-After-aware
  version on disk replaces it only with the owner's OK. All other pods of the account were EXITED (snapshot 10-23).
- **Sawtooth found** (`docs/streamer/kimi/sawtooth.md`): the render thread time climbs ~0.5 ms/min and resets every
  ~7 minutes; this is the "+-5 fps noise". Allocator hypothesis FALSIFIED (game m3b with `-binnedmalloc2`: same ramp,
  GCs every 61 s do not reset it). A full Insights trace (3.5 GB, `/workspace/sub01-traces/m3t.utrace`) was too big
  to analyse (OOM at the 31 GB container limit). Next: two short `cpu`-channel windows via the trace control port
  1985. Game back on plain **m3** since 14:00 (`/tmp/sub01-share/game.log` -> its log).
- Owner progress page with before/now photos: `docs/streamer/STATO-20261024.md` (photos in
  `docs/streamer/photos/`, Kimi's photo review `docs/streamer/kimi/photos-20261024.md`). The owner wants everything on
  GitHub but NOTHING live: Railway deploys from `main`, so the work stays on this branch with an open, unmerged PR.
- Game is back on **m3** (rolled back 12:15 per `docs/streamer/kimi/fps-next.md`; pid in `streamer/game.pid`, cores
  0-5, partition loop default 0-5/6-9). Operational setting: `cam2_fps` 30 (main view 59.7-59.9 fps, cam2 ~27,
  director 60 fps at 1.0x); with cam2 at 60 the game drops to 45-48 fps. Not a pass of the 60/60 gate.
- The bundled runner 8832 runs standalone again (12:22) only because game m3's in-game monitor polls it
  (`SUB01_PC_ORIGIN`); agent/director/watchdog use 8838. Director layout `webcam_only` while the Vagon page shows
  the login (set 12:22; restore `webcam` once the PC is connected).
- Next (Kimi `docs/streamer/kimi/fps-v22.md`; NOTE 14:00: the engine source shows our deferred cam2 capture is
  already built in the main view's SceneRenderBuilder, so `bMainViewFamily` likely changes nothing: re-decide with
  Kimi; the sawtooth comes first): native **v22** = cam2 `bMainViewFamily` A/B-able via tuning, capture
  sequence IDs + timestamps (CaptureScene, readback enqueue, fence completion, encode, FIFO push, FIFO depth/drops),
  swapchain present mode in diagnostics; launch-time A/Bs of `r.Vulkan.DelayAcquireBackBuffer 0` and
  `r.Vulkan.CpuWaitForFence 0` SEPARATELY; an Unreal Insights trace putting RenderThread/RHIThread/acquire/present on
  one timeline. Gate decisions with ABBA/BAAB 60 s legs + an A/A set, judged on per-leg median frame-time deltas
  (<= 2 ms inconclusive). When the owner has logged in and the PC is on: relaunch with
  `SUB01_PC_ORIGIN=http://127.0.0.1:8838`, then stop 8832 for good.
- No workers in flight. Done 2026-10-24: disk-full recovery, director retention (25d17a8), volume 150 → 200 GB +
  offload, Kimi C (one desktop source 8838) and B (m4, rejected), shadow/worker A/B and CSV profiles.

## Where things are
- `docs/streamer/PLAN.md`, `REPORT-20261023.md`, `RUNBOOK.md` (commands: start/stop/kill/resume, test chat via `/ws`,
  rehearsal `scripts/streamer_rehearsal.py`, highlights `scripts/streamer_highlights.py`).
- Code: agent `streamer_agent.py`, motion `scripts/streamer_motion.py`, desktop `scripts/streamer_desktop.py`, voice
  `scripts/voice_server.py`, director `scripts/streamer_director.py`, supervisor `scripts/streamer_up.py`, backend hooks
  `streamer.py`/`live_server.py`, native installers `tools/native_streamer_visual_v2/`, Kimi CLI `tools/ask_kimi.py`.
- Tests: `tests/test_streamer_*.py`, `tests/test_native_streamer_visual_v2.py`, `tests/test_voice_server.py`
  (run with the scratchpad venv: `python -m pytest -q -p no:cacheprovider <files>`).
- Kimi consultations and decisions: `docs/streamer/kimi/` (animation, stream, pc, priorities, posture, DECISIONS*.md).
- Pod bootstrap for a new session: recreate the scratchpad helpers (`podrun.py` runs bash through the Jupyter kernel
  API, `jupput.py` uploads through the contents API; downloads via `/files/tmp/sub01-share/...`), with the Jupyter
  token from the owner's RunPod pod.
