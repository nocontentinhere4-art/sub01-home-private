# Decisions on the Kimi consultations of 2026-10-23 (`pc.md`, `priorities.md`)

Advice weighed against the owner's rules (no purchases; no public stream without his request; no credentials in git or
chat; no copying a real streamer's identity) and the project's facts (REPORT-20261023.md is the current state; the
PLAN.md inventory table is the morning's). Decision: **adopt** as written, **adapt** (changed, says how), **reject** (says
which rule or fact), **done** (already true today). Effort: S < 4 h, M 4-16 h, L > 16 h. Workers as in PLAN.md "Work split".

Facts the advice did not have (they drive several rows below):
- F1 The director records display `:102` by `x11grab`, not `/pc/frame.png`: the privacy lock's neutral picture protects
  the model and the monitor texture, **not the recording**; while the owner logs in, the kiosk's login page is recorded.
- F2 Root disk: about 3.7 GB free; `recordings/` defaults under `/home/unreal`. The 150 GB volume is at `/workspace`.
- F3 Program is 1920x1080 at **24 fps** (verified); `-g 48` already gives 2 s keyframes. `--mute-audio` is hard-coded in
  `chromium_args` (`scripts/streamer_desktop.py:1252`). No PulseAudio on the pod; apt may be unavailable.
- F4 Streams prices and SDK (VAGON.md part B) say nothing about the owner's Cloud Computer; its plan cost is unknown.
- F5 `mouth.json` (voice RMS envelope, 25 Hz, 20/80 ms smoothing) exists, and the native mouth layer already drives a
  `Jaw` bone at 12 deg x open when the skeleton has one. The mesh has 65 Mixamo bones, no jaw, no morph targets.

## A. `pc.md` (remote Vagon Cloud Computer), ranked

| # | Recommendation | Decision | Reason | Lands | Effort |
|---|---|---|---|---|---|
| 1 | Owner-armed sessions: one machine start per arm, no auto start after `ended`/`off`, 3 reconnects (15/30/60 s), then `owner_required` | adopt | today `ended`/`off` are re-pressed with backoff (VAGON.md A1): a possible machine-start loop on his plan | W1 `streamer_desktop.py` (arm file / `POST /pc/vagon/arm`), VAGON.md A1 | M |
| 2 | Program video gated by the same privacy state as the observation (neutral picture, muted audio, buffers dropped) | adopt | F1: the recording is not covered today | W1 (neutral X window over `:102` while not connected) or W6 (director swaps `[1:v]` on `/pc/state`); RUNBOOK preflight | M |
| 3 | Kill latch independent of the agent loop: no new input, no reconnect, no machine start, owner rearm | adapt | `STOP` already stops agent + voice in 1 s; the desktop runner does not honour it (keeps reconnecting, accepts `/desktop/act`) | W1: refuse actions and reconnects while `STOP` exists; RUNBOOK kill drill | S |
| 4 | Three flags `transport_connected` / `remote_ready` / `program_safe`; a big canvas alone sets none | adapt | `connected` + `remote_ready` exist; `program_safe` = the director safety flag (B2) | W1, W6 | M |
| 5 | Never `--operator-console` in production; console input revoked on phase change; 15 min idle / 30 min absolute | adapt | console is 404 once connected and 10 min after the login page (second factors); add the 30 min cap, close live sessions on phase change | W1 | S |
| 6 | Exact allowlist of hosts and paths observed in qualification instead of `*.vagon.io` + path denylist | adapt | tighten after the first real session (A3 unknowns) | W1, VAGON.md A3 | S |
| 7 | Exact, state-dependent button labels; never `Start trial`, `Upgrade and run`, `Connect & Buy`, `Restart` | adopt | real defect: `VAGON_WS_NEVER_RX` (`streamer_desktop.py:578`) has no `trial|buy|purchase|pay|subscribe`, so `Start trial` matches the start pattern today (no purchases) | W1 `VAGON_WS_NEVER_RX` + M4 corpus test | S |
| 8 | One input gateway: release held keys on blur/disconnect/kill, no blind retry of launch, dialogs, `Enter`, saves | adapt | runner serialises actions; the agent's "retry twice then replace" must be off for non-idempotent remote actions | W1 release-all, W5 vagon action policy | M |
| 9 | Coordinate mapping from source size + CSS rect (`object-fit: contain`), recalc on resize; 100/100 mock + 20/20 live | adapt | mapping exists for the stream element; letterbox math and the calibration test are missing | W1 + M6 test | M |
| 10 | Keyboard check string typed into a test field and OCR'd before any `navigate`; ~25 chars/s ASCII; owner sets en-US | adopt | a wrong layout types garbage into his address bar | W1 `navigate` guard, RUNBOOK first session, owner prep | S |
| 11 | Screenshot-only perception: 1280x720 overview + native crops, OCR for URLs/labels, verification table, dialog policy (stop on credentials/UAC/Steam Guard/payment/save; one `Escape`; exact `Reject all`) | adapt | W5's planned vagon adaptation; Tesseract only if present on the pod (apt), else model-vision crops | W5 `streamer_agent.py` | L |
| 12 | Detroit through the owner's shortcut `SUB-01 Detroit`, a privately approved save manifest, story difficulty, no QTE reliance, consequences stand | adopt | no save overwrite or improvisation on his machine; the LLM loop cannot do QTEs | W5 session manifest, RUNBOOK owner prep | M |
| 13 | "Never" list on the owner's machine (Vagon admin, Windows tools, Steam store/friends, downloads, clipboard, owner profile) | adopt | web part is already in the URL guards; the remote desktop part can only live in the agent's mode policy | W5 (vagon mode allowed actions), AGENT.md | M |
| 14 | Audio: stream audio track if exposed, else PulseAudio null sink monitor; remove `--mute-audio`; mute with the privacy state | adopt | the only path on a pod without a device (F3) | `scripts/streamer_audio.sh` (here), W1 `--audio` flag, W6 mix | M |
| 15 | Mock tests M1-M9 and the first 30 minutes with the owner, go/no-go list | adopt | M1-M5 extend `tests/test_streamer_desktop_workstation.py`; M8/M9 need the pod | W1 tests, RUNBOOK "First Vagon session" | L |
| 16 | Verify `Ctrl+L`/`Alt+D`/`Alt+Left` reach the remote client, else disable `navigate` | adopt | kiosk Chromium may eat them | first session, W1 | S |
| 17 | Mix targets: duck 8-10 dB, limiter -1 dBTP, about -16 LUFS, A/V within 40 ms, mute within 100 ms | adopt | starting points, measured on the finished segment | RUNBOOK audio section, W6 | S |
| 18 | Clean X capture of the kiosk at native size for PiP; monitor is ambience; PiP composed outside Unreal post | done | director grabs `:102` natively and composites in ffmpeg; monitor = CDP screencast | - | - |
| 19 | Profile 0700, config 0600, token only in a header, no URL/DOM/typed input in logs, VNC only over SSH | done + check | already documented; add a permission check and `ulimit -c 0` to the preflight | RUNBOOK, W6 supervisor env | S |
| 20 | Ask Vagon whether an automated operator of his own computer is acceptable | done | VAGON.md B7; the owner asks | owner | - |
| 21 | Program at 1080p30, later a 1080p60 preset | reject | F3: 24 fps is verified and `priorities.md` itself fixes 24; 60 buys nothing for a desktop and costs CPU under Unreal | - | - |
| 22 | Teams API wrapper not deployed for the first integration | adopt | one less credential and control path; optional already | VAGON.md A2 (keep `api_key_file` absent) | - |

## B. `priorities.md` (next work items), ranked

| # | Recommendation | Decision | Reason | Lands | Effort |
|---|---|---|---|---|---|
| 1 | Known-good candidate: restart backend, redeploy agent, 8-line chat rehearsal, tag build, **rotate the API key pasted in chat**, scan artefacts for it | adopt | REPORT lists both; the key is an owner rule | owner + pod; PLAN "Next" 1 | S |
| 2 | Safety enforced in the broker, `POST /director/safety {on}` = safe view + app mute without restarting ffmpeg; 30 hostile cases | adopt | the broker guards exist for the web; the director has no live switch yet | W6 (zmq/sendcmd), W5 cases | L |
| 3 | Status view + 2-hour local soak (7200 s continuous, no restart, no memory growth, 2 GB GPU headroom) | adopt | 30 min proves orchestration, not endurance | `streamer_up.py status --json` fields, `streamer_rehearsal.py --minutes 120` | M |
| 4 | Disk free >= max(30 GB, 2 x 2.5 h projection) | adapt | F2: impossible on the root disk; recordings go to the volume (`--child-arg director='--recordings-dir /workspace/...'`) and the rule applies there | RUNBOOK preflight | S |
| 5 | Vagon feasibility spike >= 60 min: audio on, US keyboard, 3 h allowance, full desktop vs one app, cost | adapt | = A15 first session + soak; drop "Stream Link" and the `$4.50-8.46` figures (F4) | RUNBOOK, owner | M |
| 6 | Finish the Vagon pixel agent (`mode`/`remote_ready` through `normalize()`, point-only, pause while not ready, pixel verify, bounded reconnect) | adopt | PLAN already names it the next worker's job | W5 | L |
| 7 | First game: preinstall The Battle for Wesnoth (free, turn-based) | reject as requirement | the owner's machine runs Detroit by his choice, and installing software on it is his call (A13); offered to him as an optional calmer first game | VAGON.md A2 note | - |
| 8 | Separate body and camera ownership; keep `AuthoredReach` off | done | seat fix (builds v15/v16): `bUseControllerRotationYaw=false`, mesh offset, face camera verified; `mouse` plays the sitting loop. Remaining: a 20-min recording with no displacement | W4 verification | S |
| 9 | Desk performance: weighted idle variants, typing only on real input, talking from PCM, monitor at 8 fps | adapt | talking (`speaking.json`/`mouth.json`) and typing-on-`type` are done; variants need `RestHands` as a second idle; 8 fps monitor is low value (the PiP is the readable view) | W4 | M |
| 10 | Application audio chain: per-user PulseAudio, null sink `sub01_apps`, voice stays on its FIFO, ducking, limiter, sync calibration | adopt | correct for a device-less pod; nothing installed here, `check` reports what the pod lacks | `scripts/streamer_audio.sh`, RUNBOOK | M |
| 11 | `apt-get install pulseaudio`, root `install -d /run/user/1001` | adapt | apt may be unavailable, no root step: runtime dir under `$STREAMER_DIR/run`; if no server binary exists, a user-space install (conda-forge `pulseaudio`, ~50 MB) is the owner's call | script | S |
| 12 | Voice/chat scheduling + captions from the approved text in the programme | adapt | fairness, dedupe, caps, sentence-by-sentence synthesis exist (AGENT.md, VOICE.md); new: director captions from `speaking.json`, p95 say-to-playback < 8 s measured | W6 drawtext, W5 metric | M |
| 13 | Two-hour rundown (5/25/40/20/25/5 min), stored facts, fallback topics, no duplicate action across provider failover | adopt | browsing alone is not a programme; failover idempotency is unverified | W5 | M |
| 14 | Lip sync v1: new jaw bone, mouth bag, Rhubarb cues, 0-8 deg (12 max) | adapt | F5: the driver exists; only the bone is missing. Envelope first, Rhubarb only once visemes exist | LIPSYNC-OPTIONS.md, Blender + W4 | L |
| 15 | MetaHuman head for a later v2 if close-ups are mandatory; 2D texture mouth rejected | adopt | matches our reading; a new head changes his identity, so it is a v2 question for the owner | LIPSYNC-OPTIONS.md | - |
| 16 | Director as live programme: `desktop` the normal view, live cuts in one process, local recording independent of any publisher | adopt (cuts) / defer (publisher) | PLAN already names zmq/sendcmd; no public output exists or is built without the owner's request | W6 | L |
| 17 | Twitch publisher + IRC chat bot as the one platform | reject (defer) | owner rule: no public stream without his request, and he named no destination; no account or token is created by us | - | - |
| 18 | Two-hour dress rehearsal with scheduled failures (00:20 browser, 00:40 model, 01:00 Vagon, 01:20 voice), full 1x review | adopt | the last check that unit tests cannot replace; publisher failure dropped (none) | `streamer_rehearsal.py` schedule, RUNBOOK | M |
| 19 | Freeze the release; single-operator runbook; go/no-go; another rehearsal instead of "trying it live" | adopt | folded into RUNBOOK "Stream day" | RUNBOOK | S |
| 20 | Keep 1080p24, K07, 10-min segments, ffmpeg director; no OBS; no resolution/fps increase before the soak | done | all true today | - | - |
| 21 | Never read raw chat/web text aloud; clean streaming-only accounts; operator watches the preview with kill at hand | done / adopt | `ACK_LINES`, chat text never typed; accounts are the owner's preparation | RUNBOOK | - |
| 22 | Public bitrate 6 Mbit/s, upload >= 2x, 2 s keyframes | defer | no public output in v1 (`-g 48` already) | with 17 | - |

Written from these decisions: `RUNBOOK.md` "Stream day", `scripts/streamer_audio.sh` + RUNBOOK "Application audio",
`LIPSYNC-OPTIONS.md`, `PLAN.md` "Next". Code changes stay with their workers (W1, W4, W5, W6) as listed.
