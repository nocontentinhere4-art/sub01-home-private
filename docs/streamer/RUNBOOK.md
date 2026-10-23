# SUB-01 streamer: runbook (pod, v1)

One supervisor (`scripts/streamer_up.py`) runs five children as uid 1001 `unreal`, in this order: Xvfb :102,
desktop runner, voice server, agent, director. The director records the stream to local MP4 files.
There is no public broadcast in v1. Design: `docs/streamer/PLAN.md`; persona rules: `DIRECTION.md`.

## Commands

```
S=/home/unreal/.sub01-private/latest-source-20261023
UP="runuser -u unreal -- python3 $S/scripts/streamer_up.py"      # as root; as unreal drop the runuser part
$UP start --source $S              # detached; returns when services settle or after 60 s, prints status
$UP start --source $S --dry-run    # exact command line and environment of every child, launches nothing
$UP status [--json]                # supervisor, STOP file, per-service state, restarts used (n/5), director summary
$UP kill                           # kill switch (below)
$UP resume                         # remove STOP; the supervisor starts the agent again
$UP restart voice                  # one service; resets its restart budget (names: xvfb desktop voice agent director)
$UP stop                           # SIGTERM in reverse order (director first), SIGKILL a child after 15 s
```

`start` refuses to run as root (`--allow-root` overrides). Every path, port and interpreter is a flag
(`start --help`); extra child flags: `--child-arg desktop='--flag value'`, `--child-env voice=KEY=VALUE`.
The agent gets `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `STREAMER_MODEL`, `STREAMER_CALLS_PER_HOUR` from the
supervisor's own environment (set them on the command that starts the supervisor, never on a command line);
no other child receives them. The operator token goes to the children in `SUB01_ADMIN_TOKEN` only.

`kill`: writes `STOP`, calls voice `/stop`, takes the agent down and keeps it down (`held`). The desktop runner,
voice server, director and Xvfb keep running, so the stream shows the desktop and the idle character. It works
without a readable token (only the voice call needs it). Undo with `resume`.

## Ports, paths

| What | Where |
|---|---|
| backend 8830, bridge 8831 | existing, not supervised |
| desktop runner 8832, voice 8835, agent 8836, director 8837 | 127.0.0.1, header `X-Admin-Token` = `/home/unreal/.sub01-private/operator-token` |
| state dir | `/home/unreal/.sub01-private/streamer/` |
| `STOP`, `state.json`, `events.jsonl` (all components, one JSON per line), `layout.jsonl`, `supervisor.json` | state dir |
| logs | `logs/<name>.log` (xvfb desktop voice agent director supervisor); `pids/<name>.pid` |
| recordings | `recordings/sub01-YYYYmmdd-HHMMSS-NNN.mp4` (UTC, 10-minute segments, fragmented MP4) |
| voice PCM FIFO, speech WAVs | `voice.pcm`, `speech/` |

Each ffmpeg launch has its own timestamp prefix, so a restart never overwrites a segment. Segments are fragmented:
a crash costs about 2 s and the file stays playable. Director state: `curl -s -H "X-Admin-Token: $(cat
/home/unreal/.sub01-private/operator-token)" localhost:8837/director/state`.

## Restart policy

A child that exits is restarted after 1, 2, 4, 8, 16 s; at most 5 restarts per 10 minutes. The sixth failure leaves
it `failed` (listed by `status`, `service_failed` in `events.jsonl`); the others keep running. A child whose health
URL fails for 2 minutes after being up is restarted; one not healthy after its start timeout (voice 240 s,
desktop 90 s, others 20-60 s) counts as a crash. If Xvfb :102 restarts, the desktop runner is restarted too. A
supervisor that was killed leaves its children running; the next `start` adopts them. An Xvfb :102 that already
exists is used, never stopped.

## When something fails

First `status`, then `tail -50 logs/<name>.log`, then `grep '"service_' events.jsonl | tail`.

- **Browser dead / desktop frozen.** The runner relaunches Chromium itself (`/pc/state` says `restarting`). If the
  `desktop` service is `backoff` or `failed`, read `logs/desktop.log`: usual causes are Xvfb :102 missing (`status`
  shows `xvfb`), the `LD_LIBRARY_PATH` libraries, a port 8832 still held by the old v86 runner ("already in use" in
  `last_error`). Fix, `restart desktop`. The agent keeps running and logs desktop errors.
- **No voice.** `curl -H "X-Admin-Token: $T" localhost:8835/state` (speaking, engine, queue). The voice server
  attaches to `voice.pcm` only while a reader exists, so the director keeps a read end open and drains it while
  ffmpeg is not reading. Director state `voice: false` means no process had the FIFO open for writing when ffmpeg
  started: the recording has silence, and the director relaunches ffmpeg by itself 30-90 s after the server attaches
  (also after the server restarted mid-run, because ffmpeg's audio input hit EOF; until then the track records
  silence; each relaunch is a gap of a few seconds). Check `logs/voice.log` (the model load from
  `/home/unreal/hf-cache` takes a minute; `start` does not wait for it), then `restart voice`. Without voice the
  agent writes captions into `events.jsonl` and continues.
- **Model errors / agent silent.** No key means quiet mode by design. Check the agent saw it:
  `tr '\0' '\n' </proc/$(cat pids/agent.pid)/environ | grep -c API_KEY`. Errors and the hourly call budget are in
  `events.jsonl`; the agent retries with backoff and stays `up`, so `status` will not flag it.
- **Chat offline.** Chat arrives only through the site WebSocket and the backend (`SUB01_STREAMER=1`,
  `GET /api/home/streamer`, `.../chat`). The backend is not supervised here: if 8830 is down the agent keeps reading
  without chat. Check `kill` is not set (`STOP` present means `status` prints the kill banner).
- **No recording / not growing.** Director state: `recording`, `last_error`, `game_source`. `screen` means no
  window named `Sub01HomeLab*` was found with xdotool on :99 and the whole display is recorded (set `--child-arg
  director='--game-pid N'` or `--window-id`). The watchdog restarts ffmpeg after two checks (30 s apart) without
  growth. Also `df -h`, and `logs/director.log` for ffmpeg warnings.
- **A service is `failed`.** Read its `last_error`, fix the cause, `restart <name>`.

## Layouts

`POST /director/layout {"layout": "character"|"desktop"|"split"}` is validated and appended to `layout.jsonl`
(time, layout, previous, run prefix, seconds into the running recording). The live composite stays `character`
(game full frame, desktop 480x270 bottom-right). A post pass can use the log to re-cut the recording, but it holds
only the composite: the full-size desktop is not recoverable from it.

## Known limits

- No application or browser audio: no audio device or PulseAudio on the pod. Only the voice PCM is recorded.
- Layout changes are hard cuts and are not applied live in v1; no OBS, no RTMP, no public stream; local files only.
- Audio and video come from separate clocks (two X grabs and a PCM FIFO): small drift is possible.
- No lip sync or facial animation (the mesh has no face rig). Chat comes only from the site WebSocket.
- The child command lines follow the flags of `streamer_desktop.py`, `voice_server.py` and `streamer_agent.py`
  as of 2026-10-23 (voice with `/home/unreal/voice-rt-venv`, `--voice-config` only if `voice/voice.json` exists);
  re-check with `start --dry-run` after those scripts change.
- ffmpeg runs in its own session so `stop` lets it close the last segment; a director that is SIGKILLed leaves it
  recording until the next director start reaps it.
- Not verified against the real game window on the pod (no game here); only against X test windows and the real
  voice server with its mock engine.

## The same scene in OBS on a Mac

Source 1: window capture of the game (1920x1080), full frame. Source 2: the desktop on :102 (screen share,
VNC or browser source on the desktop frame), cropped and placed 480x270 bottom-right; that is scene `Character`.
Scenes `Desktop` (desktop full, game small) and `Split` are the other two layouts. Audio: the voice PCM
(`-f s16le -ar 48000 -ac 2`) piped from the pod into a virtual audio device and captured as an audio input; add
the Mac's own browser audio if wanted. Scene switching on `layout.jsonl`-style requests through obs-websocket gives
live cuts, which the pod recorder cannot do.
