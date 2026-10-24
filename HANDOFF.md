# SUB-01 handoff (read first; re-injected after every compaction and at session start)

Last update: 2026-10-24 21:50 UTC (structure reviewed by Kimi: `docs/streamer/kimi/handoff-review.md`).
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
- **Mouth and hoodie set aside** (owner, 2026-10-24 ~21:40 UTC: "Per la bocca lasciamo perdere per ora e la stessa cosa
  vale anche per la felpa"): no jaw/mouth rig and no hoodie re-weighting for now. The acceptance tool waives
  `mouth_motion` (`OWNER_WAIVERS`, still evaluated and shown; `--no-waivers` judges it); head motion with the voice
  stays required.
- **Codex may take over** (owner, 2026-10-24 ~21:45 UTC): when the Claude session runs out of usage, Codex continues
  from the exact same point with the same rules and mechanics (`AGENTS.md`, this file, `tools/pod/README.md`).

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
   Status 2026-10-24: every control mapped, fixed where partial and unit-tested (`docs/streamer/AGENT-CHECKS.md`,
   Kimi-reviewed); the live part is `scripts/streamer_agent_checks.py` (needs the owner's login + armed PC, the
   operator's resume and lease). Live blocker: the backend must run with the Vagon link bridge variables unset.
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
- **Sawtooth mechanism found** (2026-10-24 15:40-18:35, `docs/streamer/SAWTOOTH-20261024.md`, Kimi
  `docs/streamer/kimi/sawtooth2-*.md`): the CPU cost of `vkQueuePresentKHR` on the RHI thread (NVIDIA X11 present on
  Xvfb :99) grows ~3.3 ms/frame over a swapchain's life and resets after ~21.7k presents or when the swapchain is
  recreated (an `r.VSync` flip does it, one ~80 ms frame). GPU flat; occlusion/GTSync cvars only move the wait.
  Offscreen ablation (m3 + `-RenderOffScreen`, cam2 60): 59.9 fps capped, 77.5 observed uncapped, no sawtooth. v22
  baseline (plain m3 launcher, cam2 60): 20.29 ms p50, same sawtooth. Next (native, not built; spec in the doc):
  offscreen + main-view FIFO to the director. Interim, experimental: `scripts/streamer_swapchain_refresh.py` (ABBA:
  +4.3 fps, one ~80 ms frame per flip; NOT running, soak 8-24 h first).
- Owner progress page with before/now photos: `docs/streamer/STATUS-20261024.md` (photos in
  `docs/streamer/photos/`, Kimi's photo review `docs/streamer/kimi/photos-20261024.md`). The owner wants everything on
  GitHub but NOTHING live: Railway deploys from `main`, so the work stays on this branch with the open DRAFT PR
  https://github.com/nocontentinhere4-art/sub01-home-private/pull/4 (never merge without the owner's explicit go).
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
- Done 2026-10-24: disk-full recovery, director retention (25d17a8), volume 150 → 200 GB + offload, Kimi C (one
  desktop source 8838) and B (m4, rejected), shadow/worker A/B and CSV profiles.
- **Sawtooth ROOT CAUSE (sawtooth worker, 17:30)**: the CPU cost of `vkQueuePresentKHR` on the RHI thread (NVIDIA X11
  present on Xvfb :99) grows ~3.3 ms/frame over a swapchain's life (RHI user time 8.8 → 12.0 ms/frame; GPU flat and
  less busy at the ramp end, clocks/power flat, no throttling). It resets after ~21.7k presents (14 cycles, 21,662 ± 230
  frames) or when the swapchain is recreated. The present gates the render thread through the occlusion fence
  (WaitOcclusionTests 2.9 → 4.75 ms/frame) and the game thread through the RHI frame fence. (The coordinator's 15:35
  A/B table was mis-attributed: ExportTimerStatistics always includes the GPU queues.) `r.NumBufferedOcclusionQueries 2`
  and `r.GTSyncType -1` only move the wait. Stopgap: an `r.VSync` flip every 60-120 s recreates the swapchain (~85 ms
  hitch): ABBA median 20.45 → 18.47 ms with `cam2_fps` 60, slope 0.36 → 0.01 ms/min; Kimi wants an 8-24 h soak before
  using it. It does not reach 60: the base present cost (~9 ms user + 2.5 sys per frame) stays. Structural fix (next
  native build): render the main view offscreen and hand it to the director like cam2 (no X11 present); ablation
  `-RenderOffScreen` (launcher m3o) measures the ceiling first. Interim (18:05): m3o on v21 with `cam2_fps` 60 holds the
  60 cap: 59.8-59.9 fps, render 13.4 ms, RHI 4.3, GPU 10.3-10.5, cam2 capture 59.8 / written 51.5-52.5 fps (was 40).
  Final ABBA of the VSync flip: -1.79 ms median, +4.3 fps, flip hitches 74-86 ms.

## Workers in flight (owner asked for multi-agent work, 2026-10-24 ~15:40 UTC)
Each works in its own git worktree, consults Kimi and gets a Kimi review before committing; the coordinator merges,
builds on the pod, deploys and pushes. Split reviewed by Kimi: `docs/streamer/kimi/multiagent.md`.
| Worker | Scope | Pod rights |
|---|---|---|
| native v22 | DONE, merged 27670bd (119 tests, Kimi lifted its hold); engine APIs checked against the 5.8.3 source by the coordinator; include guard narrowed to the read-back (coordinator + Kimi). Pod dry run plans cleanly; build script `/tmp/sub01-share/deploy/v22/build-v22.sh` (refuses under MEASURING, backs up `source-backup-before-v22` and `binaries-v21-linux`). Sequence: sawtooth m3o ablation on v21 → build v22 + sidecars deploy → relaunch m3 (= v22) → smoke test + v22 baseline | read-only |
| sidecars | DONE, merged 8634ff9 (164 tests, Kimi "commit: yes"). DEPLOYED 18:33 UTC with the agent-checks code (`/tmp/sub01-share/deploy/sidecars/deploy-sidecars.sh`): supervisor pid 2010496 with `--hls-dir`, children desktop/voice/director/monitor/hls up, agent held, watchdog restarted (new code), backups `*.bak-before-window`. Follow-ups: agent waits for the feed's neutral confirmation before typing a credential; game blanks the texture when the feed goes stale | read-only |
| sawtooth | DONE, merged (findings `docs/streamer/SAWTOOTH-20261024.md`, tools `tools/sawtooth/`, stopgap `scripts/streamer_swapchain_refresh.py` NOT running: Kimi wants an 8-24 h soak, 120 s period). Native hand-off spec for v24 in the same doc. v22 baseline 20.29 ms (49.3 fps), same as v21 | runtime handed back to the coordinator 19:10 |
| visual v23 | DONE, merged (133 native tests; Kimi: 8 issues + 3 notes fixed, then "ok"). 31 live keys via `tune.py`, defaults bit-identical to v22; tuning order in the installer's `RECOMMENDED` and the README. Builds after the v22 baseline leg | read-only |
| agent checks | DONE, merged c59403b (819 streamer tests pass; Kimi: 5 blockers fixed, then "may proceed"). Found a second chat→PC path (backend Vagon link bridge) outside broker/lease/STOP: fixed in code, live blocker until the backend runs with the bridge variables unset (review before restarting the backend). Agent/desktop/watchdog files deployed 18:33. The running backend (`runtime-minecraft-resume21/source`, old code) has no VAGON_* variables and no .env, so its bridge is disabled (`vagon_bridge.enabled()` needs them) | read-only; STOP stays |
| acceptance | DONE, merged (61 tests; Kimi: criteria agreed first, 21 review findings fixed, final check clean). 16 criteria, PASS/FAIL/INCONCLUSIVE with masked evidence + highlight times (RUNBOOK "Acceptance check"). Dry run 18:03-18:33: 3 pass (director, recordings, HLS spot), 12 fail (agent held, `webcam_only`, PC not logged in, game 50.25 fps, cam2 44.35, mouth by design), monitor feed missing evidence until v22 runs (v22's `SUB01_STREAMER_VISUAL_MONITOR_FEED fps=` line is the shape the tool reads) | read-only |
Nobody but the coordinator restarts the supervisor, director, voice, agent, watchdog or backend.
**Measurement lease** (Kimi): while `/tmp/sub01-share/MEASURING` exists (end time + purpose inside), nobody builds,
deploys, restarts, scans logs or runs heavy jobs on the pod; only tiny reads and Kimi calls. Builds, deploys and
restarts go into `docs/streamer/POD-CHANGES.md` with UTC times.
State 19:25: all six workers DONE and merged. Game on **v23** binaries (plain m3 launcher, relaunched 19:13 by
`/tmp/sub01-share/relaunch-m3-now.sh`; binaries saved `binaries-v2{1,2,3}-linux`, sources `source-v2{2,3}`), v23 keys at
their defaults, `cam2_fps` 30, coordinator owns the runtime. Frames for tuning: `/tmp/sub01-share/frames.sh TAG [STATE]`
(webcam via x11grab, room/cam2 from the local HLS; restores `webcam_only`). v23 live tuning checkpoint p5 approved by Kimi for
still frames (`docs/streamer/VISUAL-TUNING-20261024.md`; values in `docs/streamer/tuning/`): incline 22 → 8.3 deg, cam2
hoodie fan gone while reading, fingertips at key height. Motion check signed off by Kimi (scope recorded in the tuning doc).
Director fifo mode DONE (c7e42ed, 944 streamer tests; Kimi "commit: yes"; adds `-follow 1` to the FIFO input, a
`smptehdbars` placeholder, a `seq=` tap measuring unique main-view fps). Deployed 21:22 UTC in **x11 mode** (default,
unchanged behaviour; backups `*.bak-before-fifo`); switch/rollback in RUNBOOK "Main view from the offscreen game".
Native v24 worker (offscreen main-view tap) still running; then build, offscreen launch, go/no-go, ABBA, soak.
Earlier plan: merge each worker; keep a v22-only build for A/B and rollback; an integrated v22 + sidecars
privacy/stream smoke test; then v23 (offline now, pinned to the v22 commit) builds only after the sawtooth
measurements end; relaunch, measure, live visual tuning with frames.

## Takeover: exact resume point (2026-10-24 21:50 UTC; for Codex or a new Claude session)
Read `AGENTS.md` (rules), then this file, then `tools/pod/README.md` (pod access: create `pods.json` outside the repo
with the Jupyter password the owner gives you). Verify the state below on the pod before acting
(`podterm.py ... 'tail -20 /tmp/sub01-share/pod-changes.log; cat /tmp/sub01-share/MEASURING'`).
**Baseline pinned (21:55 UTC):** the takeover baseline is the commit SHA recorded in `docs/streamer/TAKEOVER-BASELINE.txt`
(written right after this section was pushed); resume against that SHA, not against the moving branch tip. Pod workdirs: Python
services `/home/unreal/.sub01-private/latest-source-20261023` (deployed files identical to the branch: sha256 prefixes
agent 82449c080ddd, director d7ff873b40ac, acceptance 89af651914f1, up ebe5cedf96e8, monitor_feed a1035e51c084,
hls_serve 2b1aedac7f2d, desktop 02dde27fb5fd, watchdog bec28f8958b7); native project
`/home/unreal/.sub01-private/cinematic-source-v3-final` (running `.so` = `binaries-v23-linux`, sha256 830da2d11dcb);
streamer data `/home/unreal/.sub01-private/streamer`; shared scratch `/tmp/sub01-share` (wiped if the pod restarts;
durable copies under `/workspace`). Secrets: `pods.json` is provided by the owner through an approved secret channel
(never pasted in chat) or pre-provisioned on the machine.
**Live state:**
- Game: plain m3 launcher on the **v23** binaries (pid in `streamer/game.pid`, relaunched 19:13 UTC; CPU partition
  loop 0-5/6-9 running), windowed on Xvfb `:99` (so the sawtooth is still there, ~49-51 fps). Tuning file =
  checkpoint p5 (`docs/streamer/tuning/streamer-visual-tuning-20261024-p5.json`), `cam2_fps` 30. Binaries/sources
  saved on the pod: `cinematic-source-v3-final/binaries-v2{1,2,3}-linux`, `source-v2{2,3}`, `source-backup-before-v2{2,3}`.
- Supervisor (started 18:33 by `tools/pod/onpod/deploy-sidecars.sh`, `--display :103 --desktop-port 8838 --hls-dir`):
  desktop 8838 (Vagon page at `login_required`), voice 8835, agent 8836 HELD by STOP (since 10:40), director 8837
  (fifo-capable code, **x11 mode**, layout `webcam_only`), monitor 8840 (grey/neutral: Vagon not connected), hls 8839.
  Watchdog runs the new code. Runner 8832 standalone (the game's `SUB01_PC_ORIGIN`).
- **RunPod balance guard PAUSED** (pid 63, `kill -STOP 63`, account API rate limit until ~00:05 UTC 2026-10-25):
  expected `ps -o pid,stat,lstart,cmd -p 63` = state `Ts`, started `Wed Oct 21 19:05:18 2026`, command
  `python3 /root/.sub01-windows-recovery/guard-v3.py`. After 00:20 UTC 2026-10-25: verify it is still that process
  (if the pid is gone or different, the pod restarted: do NOT start another guard without the owner; report it), then
  `kill -CONT 63`, check its log/next poll for errors, log the change, tell the owner. (A reminder
  was scheduled into the Claude session; a new agent must do it itself.)
- No measurement lease. Draft PR #4 open, never merge without the owner's go.
**In flight at handover:** the native v24 worker (offscreen main-view tap, `install_v24.py`; spec = "Structural fix"
in `docs/streamer/SAWTOOTH-20261024.md`). If its commits are not on the branch: its code is DONE but only partly Kimi-reviewed (7 of 11 pieces; fixed: SOS
bounds, FNV basis, a reorder-buffer stall, the write deadline) and is preserved as a patch on the pod,
`/workspace/sub01-w-v24/v24-wip-2149.patch` (copy of `/tmp/sub01-share/w-v24/v24-wip-2149.patch`; applies with
`git apply` on commit 11ee6f9; 5 files: `install_v24.py`, `main_fifo_probe.py`, README, tests). Finish the Kimi
review (status/log, header/cam2 edits, m5 launcher, probe, follow-up), then commit. Launcher already on the pod:
`/root/.sub01-windows-recovery/launch-streamer-game-20261024m5.py`. Engine APIs verified (OnBackBufferReadyToPresent:
render thread, (SWindow&, ISlateViewportProvider&); offscreen viewport texture PF_A2B10G10R10). cam2's 52-53 of 60
fps loss = whole-frame drops on a full pipe (reader back-pressure, ~7/s), not the capture. The director side is DONE
and deployed in x11 mode (RUNBOOK "Main view from the offscreen game").
The v24 worker runs inside the Claude session (a local git worktree; it has not modified the pod's native sources
or binaries: only the m5 launcher file and the patch). If that session is gone, the worker is gone too: inspect
`/tmp/sub01-share/w-v24/` and the patch before redoing anything; only the coordinator builds, so builds never overlap.
**Rollback (exact; P=/home/unreal/.sub01-private/cinematic-source-v3-final; durable script copies in
`/workspace/sub01-tools/`, also in `tools/pod/onpod/`; `/tmp/sub01-share` is wiped by a pod restart):**
- Game to the known-good v23: `cp -a $P/binaries-v23-linux/. $P/Sub01HomeLab/Binaries/Linux/` (always first: a v24
  build replaces `Binaries/Linux`, and the m3 launcher loads whatever is there), then
  `bash /workspace/sub01-tools/relaunch-m3-now.sh` (copy it to `/tmp/sub01-share/` first if that dir is gone). For
  v22/v21 use `binaries-v22-linux` / `binaries-v21-linux` the same way. v24's tap only runs offscreen (launcher m5).
- Director to x11: `bash /workspace/sub01-tools/deploy-sidecars.sh` as is (it reinstalls the 18:33 scripts from
  `/tmp/sub01-share/deploy/sidecars/`; if that dir is gone, copy `/workspace/sub01-tools/sidecars/*` there first, then
  install the branch's current `scripts/` files instead if newer), then `POST /director/layout {"layout":"webcam_only"}`
  with the operator token while the Vagon page may show a login.
- Tuning to checkpoint p5: `runuser -u unreal -- python3 /home/unreal/tune.py $(python3 -c "import json;
  d=json.load(open('/workspace/sub01-tuning/streamer-visual-tuning-20261024-p5.json')); print(' '.join(f'{k}={v}' for
  k,v in d.items() if k!='schema'))")` (same values as `docs/streamer/tuning/`; it includes `cam2_fps=30`).
- Health checks after any of these: supervisor `status` (all children up, agent held), new
  `SUB01_STREAMER_VISUAL_PERF` lines in the game log, `GET /director/state` (recording, `window_speed` ~1.0), local HLS
  playlist updating, `pod-changes.log` line written.
- Measurement lease: the sawtooth tools do NOT create it. Before an ABBA leg or the soak: `echo "<end UTC> <purpose>" >
  /tmp/sub01-share/MEASURING`; remove it when the leg ends.
**Next steps, in order:**
1. 00:20 UTC: resume the RunPod guard (above).
2. v24: Kimi review -> apply on the pod (pattern `tools/pod/onpod/build-v23.sh`, backups, refuse under MEASURING) ->
   launcher m5 (= m3o + v24; never edit m3/m3o) -> go/no-go (tap fires once per frame offscreen, non-black, format and
   pitch handled) -> switch the director to `--game-source fifo` (RUNBOOK) -> `cam2_fps` 60 -> ABBA 4 x 15 min
   (`tools/sawtooth/`) -> >= 8 h soak -> gates in the spec (>= 59.5 unique main-view fps at the director, <= 0.5%
   drops, no sawtooth). Rollback: m3 launcher windowed + director x11.
3. When the owner has logged in at the operator console and OKs a PC start: arm, relaunch the game with
   `SUB01_PC_ORIGIN=http://127.0.0.1:8838` (feed then live on the in-game monitor), stop 8832 for good, run
   `scripts/streamer_agent_checks.py` (`--audit-only`, then the live flags with the operator steps it prints), the
   30-minute Kimi-shadow trial (`scripts/streamer_shadow_report.py`).
4. 30-minute acceptance recording -> `scripts/streamer_acceptance.py` (mouth waived) -> highlights -> owner approval.
5. Open with the owner: Kimi's 3 wording suggestions for the public page `docs/streamer/STATUS-20261024.md`;
   whether to watch PR #4.

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

## Codex access verification — 2026-10-24 22:12 UTC
- Separate takeover checkout verified clean at a0332c9549b99bc7d9eccfba7113b0978ca87410. Immutable baseline unchanged.
- Authenticated existing JupyterLab session reached through the authorized personal browser; no credentials copied or printed. Local pods.json has not yet been provisioned.
- Tiny read at 22:11:46 UTC: no MEASURING lease; root has 7.4 GB available; PID 63 is Ts, started Wed Oct 21 19:05:18 2026, exact expected guard-v3.py command. It remains paused because 00:20 UTC has not arrived.
- Existing v24 worker is progressing: shared directory had review7 and m5-fix artefacts timestamped 22:10 UTC; durable v24-wip-2149.patch and v24-wip-on-92bea07-2203.patch exist. Do not duplicate or interrupt its review.
- Runtime ownership handed to Codex at approximately 22:16 UTC: Claude explicitly confirmed no more builds, deploys, restarts, tuning, console cvars, MEASURING or STOP changes, and no branch commits. Claude cancelled its 00:20 UTC guard reminder. Its v24 worker continues review only and will deliver final patch, verbatim consultations and MANIFEST.txt under /workspace/sub01-w-v24/.
- Offline reproductions confirm podterm shell status false-positive (false -> END 0) and podrun generated-code false-positive (exit 7 -> local exit 0). No fix or commit yet: consult the on-pod partner first.
- No runtime changes, builds, restarts, API balance polling, Vagon starts or commits performed by Codex.

### Codex continuation — 2026-10-24 22:19 UTC
- Private local access provisioned outside git in ~/.sub01/pods.json (directory 700, file 600), downloaded through authenticated Jupyter UI without showing the value; pod transfer file removed. Local terminal helper connection succeeds with certificate verification enabled.
- Helper design consultation running on the pod: /tmp/sub01-share/codex-helpers/{question.txt,answer.json,consult.err}. Save question/answer verbatim under docs/streamer/kimi/ before committing repairs.
- Baseline v24 artefact names corrected from Claude's live response: v24-wip-on-92bae07-2203.patch (base 92bae07), sha256 prefix 64352b3cb21440bd; launcher m5 prefix 4d9bd83099609f73. Earlier note spelling 92bea07 was a transcription error. No final MANIFEST.txt yet.

### Helper repair checkpoint — 2026-10-24 22:30 UTC
- Partner's initial broad consultation exhausted its reasoning budget without an answer (saved verbatim); the focused follow-up explicitly approved the limited status/TLS repair with no blockers.
- Local fixes preserve the shell status before printf, delimit multiline commands correctly, require kernel completion and an exit marker, map signal exits, and use verified default CA trust when the Linux bundle is absent. No commit until the exact diff review finishes.
- Live Jupyter probes: both terminal and kernel helpers returned exactly 0 and 7 for the corresponding harmless commands, with expected stdout. No application runtime mutation.
- Read-only live health: director recording=true, webcam_only, window_speed=1.0; Vagon phase dashboard (does not authorize or prove PC start). Native PID 2015338 remains the 19:13 v23 process; latest 10 s PERF samples at 22:25 UTC = 58.4, 57.1, 56.0 fps, below acceptance.

### Helper deliverable verified — 2026-10-24 22:39 UTC
- Exact diff review found a fragmented-status blocker (42 could be read as 4). Detection and parsing now share a newline-terminated marker regex; the targeted regression passes. Follow-up review explicitly returned COMMIT YES.
- Final verification: 26 regression tests pass; live terminal and kernel probes preserve 0, 7 and 42. Source and consultation artefacts are ready to commit/push on the private branch. No game or sidecar runtime changes.
- Eight deployed service source hashes exactly match the takeover prefixes. v24 worker review still active, no final MANIFEST.txt at last check.
- For the future v24 build script, do not copy build-v23.sh's final status behaviour: it prints BUILD_EXIT but does not explicitly exit with RC. Require the real build exit and independently verify the produced binary.
