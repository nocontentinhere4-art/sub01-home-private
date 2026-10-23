# SUB-01 streamer: first complete version (plan, 2026-10-23)

Owner's priority: SUB-01 stays at his PC, browses the web, uses apps, talks with his own voice (English only),
reads the public chat and comments. House life (walks, phone, bed, routines) is paused, not deleted.

## What exists (inventory, 2026-10-23)

| Area | State |
|---|---|
| Brain | `mind.py` (Claude via `ANTHROPIC_API_KEY`, else OpenRouter) writes page notes, day plans, 40-word chat replies; `eyes.py` picks browse links from page text. Text only, no image ever reaches a model. No observe/decide/act/verify loop except the browser's link choice. The spiking model votes on micro-choices. On the pod `MIND=0`: no key configured. |
| Chat | Site WebSocket `/ws` only (`handle_chat` → `chat.check` → impulse parser → canned reaction). `mind.Inbox` queues at most 10 messages, replies one per 120 s, no relevance ranking. No Twitch/YouTube/Kick connector. |
| Voice | Nothing. No TTS, no audio path anywhere. The character has no face rig (no morph targets): lip sync and facial expressions are impossible with the current mesh. |
| Browser | `browse.py` Playwright Chromium: goto, scroll, vetted site search; clicks, typing, logins blocked by design. Frames 1280×800 JPEG via `/api/screen/desk.jpg`. |
| PC | `scripts/home_pc_runner.py` v86 text Linux guest on 8832 (`/pc/*` + `/devices/*`), consumed by the native monitor (`SUB01_ACTUAL_PC_MONITOR_BOUND`). No real desktop. Vagon client exists, never run, no screen source. |
| Native seat | Live game: validated postures Walk/Idle only; seat gates refuse. `-Sub01StreamerVisual` (pod source) places the body at the desk (authored transform), holds the R9_Sitting pose, applies head gaze yaw ±20°/pitch ±10° and a nod from `streamer-visual-event.json`, spectator camera at (334,−209,151) FOV 65, ghost views allowed. No typing/mouse/talking/breathing animation. Desk clips on the live skeleton exist on the pod only (`Content/Sub01Hands/Cinematic20261022`: Desk7 sitting, DeskTyping, PCTransition DeskSit/DeskGetUp, RestHands, Reach, Website loop). |
| Streaming | No OBS on the pod, no RTMP, no recorder. ffmpeg, Xvfb :99 (game), xdotool present. No audio device, no PulseAudio. |
| Kill switch | None at runtime. |

## Architecture of v1 (shortest complete path)

```
chat (/ws)  ─┐
             ▼
 live_server (backend 8830) ── streamer.py: activity hold at the desk, chat batches, kill switch, /api/home/streamer
             │                       │
             │                       ▼
             │               streamer_agent.py  observe → decide (Claude, vision) → act → verify → comment
             │                 │           │                                   │
             │                 ▼           ▼                                   ▼
             │        streamer_desktop.py (8832)                       voice_server.py (8835)
             │        Chromium on Xvfb :102 1920×1080                  TTS (Kokoro CPU; Chatterbox/ElevenLabs optional)
             │        /pc/* for the monitor + /desktop/* actions       /speak /stop, speaking state, PCM FIFO
             │                 │                                               │
             ▼                 ▼                                               ▼
   native game (-Sub01StreamerVisual v2): body at desk, states idle/reading/typing/mouse/talking, gaze, breathing
             │  reads streamer-visual-event.json written by the agent
             ▼
   streamer_director.py: ffmpeg x11grab :99 (character) + :102 (desktop) + voice PCM → local MP4 segments; layouts
```

Everything runs on the pod as uid 1001 under `/home/unreal/.sub01-private/streamer/` (state, logs, kill file).
No public broadcast, no purchases, no credential changes. Verification is a local recording.

## Interface contracts (workers must respect these exactly)

### Ports and paths
- Backend 8830 (existing), bridge 8831 (existing), **desktop runner 8832** (replaces the v86 runner while streaming),
  **voice server 8835**, **agent status 8836**, **director status 8837**. All loopback, `X-Admin-Token` = operator token
  file `/home/unreal/.sub01-private/operator-token` (env `SUB01_ADMIN_TOKEN` or `--token-file`).
- State dir `STREAMER_DIR` default `/home/unreal/.sub01-private/streamer/` with: `STOP` (kill file: when present every
  autonomous action stops within 1 s and speech is cut), `state.json`, `events.jsonl` (one JSON per line, every decision,
  action, outcome, speech, error), `recordings/`.
- Native event file: `/home/unreal/.sub01-private/streamer-visual-event.json` (schema below), written atomically
  (tmp + rename), uid 1001, mode 0600.
- Display `:102` 1920×1080 for the desktop; the game stays on `:99`.

### streamer.py (backend, in live_server)
- Enabled by env `SUB01_STREAMER=1`. `GET /api/home/streamer` → `{active, since, activity, paused: [...], chat: {pending, spoken}, kill: bool}`.
- `POST /api/home/streamer` body `{"operation": "start"|"stop"|"kill"}`; `kill` also writes `STOP`.
- While active: `life.activity == "use_computer"` at node `desk`, stage reported AWAKE, impulses that would move him are
  refused with the honest line (reuse `life.request_impulse` why_not), hunger/bladder/sleep timers keep running but do not
  move him (they are logged as "deferred"). Phone/walk/bed/TV routines paused. On stop: previous behaviour resumes, nothing reset.
- Chat for the agent: `GET /api/home/streamer/chat?since=<seq>` → `{messages: [{seq, t, nick, text, kind}]}` from the
  existing `handle_chat` path after `chat.check` (filtered, rate-limited); `POST /api/home/streamer/said` records what he
  answered so Inbox/mind do not answer twice. Chat is input, never command: nothing in a message changes rules, grants
  credentials or drives the desktop directly.

### streamer_desktop.py (pod, 8832)
- Serves the existing PC runner contract so the native monitor and the web house keep working:
  `GET /pc/state` (`status, ready, display{kind:"graphical", available, revision, frame_id, width, height}, privacy, session`),
  `GET /pc/frame.png` (PNG of the desktop, 1280×720 downscale of :102 by default; `?full=1` for 1920×1080),
  `POST /pc/input`, `POST /pc/graphical-input`, `POST /pc/session`, `POST /pc/privacy`, and `/devices/*` via
  `scripts/home_device_proxy.HomeDeviceProxy(home_origin=8830)` exactly like `home_pc_runner.py`.
- Agent API (same token):
  - `GET /desktop/observe` → `{frame_id, url, title, jpeg_b64 (1280×720), text (visible text, ≤3000 chars), marks: [{id, role, label, box:[x,y,w,h]}], scroll: {y, max}, loading, dialogs: [...]}`; marks are clickable/typeable elements numbered on the screenshot (set-of-marks).
  - `POST /desktop/act` body one of `{"action":"navigate","url"}`, `{"action":"click","mark"|"point":[x,y]}`, `{"action":"type","text","submit":bool}`, `{"action":"scroll","direction":"up"|"down","amount"}`, `{"action":"key","key"}`, `{"action":"back"}`, `{"action":"search","query"}` (DuckDuckGo HTML), `{"action":"wait","seconds"}`. Returns `{ok, outcome: {url_before, url_after, title_after, changed, errors: [...], load_ms, dialog}, frame_id}` after waiting for load/network idle (cap 10 s). Never claims success without a post-action observation.
  - Safety: separate profile dir, `accept_downloads=False`, blocked domains (banking, adult, login pages of the owner's services), no file uploads, no clipboard, no purchases (block `checkout|payment|cart` paths), popups closed. Browser crash → auto relaunch, `status: "restarting"` for the monitor.
- Rate: frames at ≥8 fps for the monitor (CDP screencast like `city_readonly_pc_adapter.py`).

### voice_server.py (pod, 8835)
- `POST /speak` `{"text", "priority": "low"|"normal"|"high", "max_seconds", "tag"}` → `{id, queued, estimated_seconds}`.
  Sentences are synthesized and played one by one; a `high` request cuts the current sentence and drops `low` items;
  queue bound 3 items; items older than 20 s are dropped (logged).
- `POST /stop` cuts speech now. `GET /state` → `{speaking: bool, current: {id, tag, started, text}, queue: n, engine, voice}`.
- Audio sink: continuous 48 kHz stereo s16le PCM to the FIFO `STREAMER_DIR/voice.pcm` (silence when idle) for the director;
  the same PCM is also written as per-utterance WAV in `STREAMER_DIR/speech/` with a `timeline.jsonl` (start/end UTC).
- Engine abstraction: `kokoro` (default, blend from the chosen candidate), `chatterbox`, `elevenlabs` (needs key) behind one
  class; mock engine for tests (sine tone with duration ≈ 0.07 s per character).
- Speaking state file `STREAMER_DIR/speaking.json` `{speaking, started_utc, ends_utc, text}` for the native talking animation.

### Native event file (schema `sub01.private-streamer-visual-event.v2`)
```json
{"schema":"sub01.private-streamer-visual-event.v2","source":"streamer_agent","native_pid":N,"native_start_ticks":N,
 "captured_utc":T,"expires_utc":T+2,"sequence":S,
 "state":"idle"|"reading"|"typing"|"mouse"|"talking"|"reacting",
 "gaze_yaw_deg":-20..20,"gaze_pitch_deg":-10..10,"nod_strength":0..1,"intensity":0..1}
```
The v1 game accepts only `source: "human_vagon_observation"` and no `state`; v2 of `TickPrivateStreamerVisual` accepts both.

### streamer_director.py (pod)
- ffmpeg inputs: x11grab `:99.0` window of the game (1920×1080), x11grab `:102.0` (desktop), PCM FIFO voice.
- Layouts: `character` (full character, desktop PiP 480×270 bottom-right), `desktop` (desktop full, character PiP),
  `split`. The agent sets the layout through `POST /director/layout`; transitions are hard cuts in v1 (ffmpeg re-launch
  is NOT allowed: the layout is changed by `sendcmd`/`zmq` or by recording three streams and compositing after; v1
  records a fixed `character` layout and writes `layout.jsonl` so the final MP4 can be composited; the live preview
  shows `character`).
- Output: `recordings/sub01-YYYYmmdd-HHMMSS.mp4` in 10-minute segments (h264 veryfast, 24 fps, aac). `GET /director/state`.
- No PulseAudio on the pod: browser/app audio is not captured in v1 (documented limit).

### streamer_agent.py
- Loop every 2–6 s (adaptive): observe (desktop + chat batch + voice state + time) → decide with Claude
  (`ANTHROPIC_API_KEY`; model `STREAMER_MODEL` default `claude-sonnet-4-5`; vision input = marked screenshot; JSON output:
  `{thought, action, say, state, layout}`) → act via `/desktop/act` → verify (outcome) → comment through `/speak` only when
  `say` is non-empty and pacing allows. Rules from `docs/streamer/DIRECTION.md` (silence while reading, one proportionate
  reaction per event, chat in batches, never execute chat commands). Budget: `STREAMER_CALLS_PER_HOUR` default 240.
- Model error / no key → "quiet mode": keeps reading with scripted safe behaviour (scroll, no speech except a short
  honest line), logs the error, retries with backoff. Voice unavailable → captions in `events.jsonl`, loop continues.
- Writes the native event file every ≤1 s and `STREAMER_DIR/state.json`.
- Memory/personality: reuse `mind.Memory` and the persona rules in `mind.py` (never claims to be human, no real-person identity).

### streamer_up.py (pod)
- `start|stop|status|kill`: Xvfb :102, desktop runner, voice server, agent, director, in this order, each with health
  checks, PID files and restart-on-crash (max 5 per 10 min). `kill` = `STOP` file + voice `/stop` + agent pause; the scene
  stays presentable (desktop keeps streaming, character idle).

## Work split (separate scopes, no shared files)
| Worker | Files | Depends on |
|---|---|---|
| W1 desktop | `scripts/streamer_desktop.py`, `tests/test_streamer_desktop.py` | — |
| W2 backend | `streamer.py`, wiring in `live_server.py` (guarded by `SUB01_STREAMER`), `tests/test_streamer_mode.py` | — |
| W3 voice | `scripts/voice_server.py`, `tests/test_voice_server.py` | — |
| W4 native | `tools/native_streamer_visual_v2/` (patch + installer for `TickPrivateStreamerVisual` and `Sub01HomeHands`), compile-closure check | copies of pod sources |
| W5 agent | `streamer_agent.py`, `tests/test_streamer_agent.py` (fake provider) | contracts above, DIRECTION.md |
| W6 director | `scripts/streamer_director.py`, `scripts/streamer_up.py`, `docs/streamer/RUNBOOK.md`, tests for layout/segment logic | contracts above |

## Verification
1. Unit tests per worker (fake providers, no network).
2. Pod integration: start with `streamer_up.py start`, 30-minute continuous local recording with: an activity change
   (reading → search → another site), chat interaction (messages through `/ws`, spoken answers), an induced error
   (browser killed, model error injected) and recovery; the recording and `events.jsonl` are the evidence.
3. Declared limits: no lip sync/facial animation (mesh has no face rig), no app audio capture (no PulseAudio), chat only
   from the site WebSocket, Vagon not connected.

## Blockers for the owner
- `ANTHROPIC_API_KEY` (or `OPENROUTER_API_KEY`) on the pod, in a root-only file; without it the agent runs in quiet mode.
- Voice choice among the candidates (A/B/C Kokoro blends) or a key for ElevenLabs Voice Design if a more realistic voice is wanted.
