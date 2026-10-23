# SUB-01 handoff (read first; re-injected after every compaction and at session start)

Last update: 2026-10-23 21:40 UTC (structure reviewed by Kimi: `docs/streamer/kimi/handoff-review.md`).
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

## Last-observed state (2026-10-23 ~21:35 UTC; verify before relying on it)
Pod `3u7g6drf5fiiql` (RTX PRO 4000 24 GB, root disk ~3 GB free).
- Native game k (build v19, t.MaxFPS 24): launcher `/root/.sub01-windows-recovery/launch-streamer-game-20261023k.py`;
  verify with `pgrep -u unreal -f UnrealEditor-Cmd` and `/home/unreal/.sub01-private/streamer-visual-receipt.json`.
  Main viewer port 8893 (`curl -s 127.0.0.1:8893/frame.jpg`). Live tuning file
  `/home/unreal/.sub01-private/streamer-visual-face-tuning.json` via `runuser -u unreal -- python3 /home/unreal/tune.py key=value`
  (QA-kept 22:1x UTC: up 20, forward 2, side -6, aim_drop -2, fov 95, seat_back 36, posture_lean 0, posture_head 14
  — posture_head 14 is a temporary yaw compensation for the wrong-axis bug; reset to ~0 after the native axis fix).
  Visual bugs ranked in `docs/streamer/VISUAL-QA-20261023.md`. State/camera hold: `/home/unreal/camera-check.py <camera> <state> <seconds>`.
- Sources on the pod: Python services `/home/unreal/.sub01-private/latest-source-20261023`; native project
  `/home/unreal/.sub01-private/cinematic-source-v3-final` (`build-worker-vNN.sh`, logs `build-vNN.log`).
- Backend: coordinator `/root/.sub01-windows-recovery/resume20.py` (ports 8830/8831); streamer hold re-armed with
  `POST /api/home/streamer {"operation":"start"}` (X-Admin-Token).
- Supervisor `scripts/streamer_up.py` (start/status/kill/resume/restart/stop; see `docs/streamer/RUNBOOK.md`):
  desktop 8832 (bundled Chromium, :102; feeds the in-game monitor + director PiP), voice 8835 (Chatterbox K07,
  `streamer/mouth.json`), agent 8836 (Claude primary, Kimi fallback), director 8837 (24 fps libx264, recordings in
  `/home/unreal/.sub01-private/streamer/recordings`, verified rehearsal segments copied to `/workspace/sub01-streamer-recordings`).
- Vagon runner 8838 (:103, Google Chrome 156 `/opt/google/chrome/chrome`, owner's authenticated profile
  `streamer/desktop-vagon/profile`, backups `profile.bak-*`, last 2 kept): connected, real Windows frames at 30 fps
  (H.264 1080p, relay over UDP), keyboard and mouse PROVEN (typing/clearing YouTube search, Start menu, scroll; commit
  45c6830). Starting the computer needs arming (`POST /pc/vagon/arm {"minutes":N}`, one start per arming; commit
  7fc8bcc): it spends the owner's balance ($0.99/h; balance seen 8.88 USD) and the computer stops itself after his
  idle setting (~15 min). The main runner 8832 still runs the bundled Chromium (its source file is updated; it picks
  the new code up when restarted). Owner login console: `https://<pod>-8888.proxy.runpod.net/proxy/8838/operator`.
- Director v2 (commit 9b3da99) is STAGED in the pod source but the running director is still the old 24 fps one:
  restart it after game l with `--child-arg "director=--game-pid-file $P/game.pid" --child-arg "director=--fps 60
  --desktop-fps 60 --encoder h264_nvenc --hls-dir /home/unreal/.sub01-private/streamer/hls"` and watch
  `/director/state` `output.fps_measured`. New sidecars (not yet in the supervisor): `scripts/streamer_hls_serve.py`
  (127.0.0.1:8839), `scripts/streamer_monitor_feed.py` (:103 → `streamer/monitor.mjpeg`, health 8840; for the v21
  monitor feed). Layouts: webcam, desktop, split, room (cam 2).
- Build v20 compiled (stream pass + cam 2); the native worker is adding the QA fixes (wrong posture axis, loop-seam
  head snap, chair through his back, webcam re-aim, seat yaw, key light) before launch of game l at 60 fps.
- Workers in flight: native (v20 QA fixes, then v21 monitor feed); agent safety (Kimi
  shadow mode, guard rails, credentials/installs flags, webcam/room layouts, privacy cut). Done today: visual QA
  (`docs/streamer/VISUAL-QA-20261023.md`), director v2, Vagon input proof, arming gate.

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
