# SUB-01 streamer: runbook (pod, v1)

One supervisor (`scripts/streamer_up.py`) runs five children as uid 1001 `unreal`, in this order: Xvfb :102,
desktop runner, voice server, agent, director. The director records the stream to local MP4 files and, on request,
writes a local HLS playlist from the same encode ("Recording: 60 fps, NVENC, layouts, HLS" below).
There is no public broadcast: nothing is published or streamed out without the owner's request. Design:
`docs/streamer/PLAN.md`; persona rules: `DIRECTION.md`.

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
The agent gets `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `MOONSHOT_API_KEY`, `STREAMER_MODEL`,
`STREAMER_CALLS_PER_HOUR`, `STREAMER_PROVIDER`, `STREAMER_FALLBACK_PROVIDER`, `STREAMER_KIMI_MODEL` from the
supervisor's own environment (set them on the command that starts the supervisor, never on a command line);
no other child receives them. The operator token goes to the children in `SUB01_ADMIN_TOKEN` only.
Providers (AGENT.md "Providers", KIMI.md): Claude is the primary and Kimi the fallback as soon as
`/home/unreal/.sub01-private/kimi-key` (0600, uid 1001) exists; explicit `--child-arg "agent=--fallback-provider kimi"`,
Kimi first `--child-arg "agent=--provider kimi --fallback-provider anthropic"`; `status`/`GET :8836/state` shows
`provider.active`, `provider_switch` rows are in `events.jsonl`.

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
| HLS (only with `--hls-dir`) | `hls/live.m3u8` + `hls/sub01-...-<epoch seq>.ts` (4 s), local test server 127.0.0.1:8839 |
| voice PCM FIFO, speech WAVs | `voice.pcm`, `speech/` |
| second camera (written by the game) | `cam2.mjpeg` (FIFO, MJPEG 1280x720 at 60), `cam2.json` (fps, last frame) |
| in-game monitor feed (read by the game) | `monitor.mjpeg` (FIFO), `scripts/streamer_monitor_feed.py` health 127.0.0.1:8840 (8838 is the Vagon runner) |

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
- **Not 60 fps / choppy.** Director state `output` (`fps_measured`, `speed` below 1.0 means ffmpeg falls behind) and
  `encoder` (`libx264` after an `encoder_fallback` row: read `encoder_note`, e.g. no libcuda, NVENC session limit).
  Relieve it with `--layout-switch restart` (one composite) or drop cam2; check sources with the mpdecimate command in
  "Recording: 60 fps" below.
- **No recording / not growing.** Director state: `recording`, `last_error`, `game_source`. `screen` means no
  window named `Sub01HomeLab*` was found with xdotool on :99 and the whole display is recorded (set `--child-arg
  director='--game-pid N'` or `--window-id`). The watchdog restarts ffmpeg after two checks (30 s apart) without
  growth. Also `df -h`, and `logs/director.log` for ffmpeg warnings.
- **A service is `failed`.** Read its `last_error`, fix the cause, `restart <name>`.

## Stream day (single operator; from Kimi's skeleton, `kimi/DECISIONS.md` B19)

Still local only: there is no public output in v1 and none is started without the owner's request. Everything below
uses the commands of REPORT-20261023.md as they are. Fill the header before starting:
`Date/UTC ____  Operator ____  Build/tag ____  Planned duration ____  Vagon today: YES/NO  Local Chromium fallback ready: YES/NO`.

### A. Go / no-go, T-60 to T-20

- [ ] Exact candidate deployed (`$S` points at it); no unreviewed camera, agent or audio patch since the last rehearsal.
- [ ] No credential in chat, screenshots, logs, command lines or recordings; the API key pasted in chat has been rotated
      and the old one revoked. `ls -l /home/unreal/.sub01-private/{operator-token,anthropic-key,kimi-key}` all `0600`
      uid 1001; `streamer/desktop/profile` and `streamer/vagon.json` not group/other readable; token >= 32 characters.
- [ ] Keys reach only the agent: `tr '\0' '\n' </proc/$(cat $P/pids/agent.pid)/environ | grep -c API_KEY` (after start).
- [ ] Disk: recordings on the volume, not the root disk (about 3.7 GB free there): `--child-arg director='--recordings-dir
      /workspace/<...>/recordings'`; free space >= 2 x (bytes of the last run / its seconds x 9000) from `ls -l recordings/`.
- [ ] Model and voice providers healthy, call budget covers 3 h (`STREAMER_CALLS_PER_HOUR` 240, observed 51 per 30 min).
- [ ] GPU: Unreal + Chatterbox leave headroom (`nvidia-smi`), no CUDA OOM in `logs/voice.log`.
- [ ] If Vagon: the owner's one-time login is done (VAGON.md A2), the machine's session/idle allowance covers the day, he
      has armed exactly one machine start, the remote Windows is prepared (dedicated browser profile, notifications off,
      Steam logged in, en-US layout, desktop shortcut `SUB-01 Detroit`, save policy approved), `/pc/state.vagon.phase` is
      `connected` and the `remote_ready` neutral picture was seen before it.
- [ ] A 2-hour local rehearsal passed with this candidate; no open severity-1/2 defect. Otherwise: another rehearsal.

### B. Start (as root on the pod)

```
S=/home/unreal/.sub01-private/latest-source-20261023
P=/home/unreal/.sub01-private/streamer
T=/home/unreal/.sub01-private/operator-token
curl -s -X POST -H "X-Admin-Token: $(cat $T)" -H 'Content-Type: application/json' \
     --data '{"operation":"start"}' http://127.0.0.1:8830/api/home/streamer
runuser -u unreal -- /home/unreal/venv/bin/python $S/scripts/streamer_up.py start --source $S --streamer-dir $P \
     --token-file $T --child-env "director=XAUTHORITY=/home/unreal/.sub01-private/native-xauthority" \
     --child-arg "director=--game-pid-file $P/game.pid" \
     --child-arg "director=--fps 60 --desktop-fps 60 --encoder h264_nvenc --hls-dir $P/hls"
runuser -u unreal -- /home/unreal/venv/bin/python $S/scripts/streamer_up.py status --source $S --streamer-dir $P --token-file $T
```

- [ ] The native game runs with `-Sub01StreamerVisual`; `$P/game.pid` is its pid; `status` shows every service `up`, no
      restart loop; `GET /api/home/streamer` says `active: true`, `activity: use_computer`, routines paused.
- [ ] Director: `curl -s -H "X-Admin-Token: $(cat $T)" localhost:8837/director/state` shows `recording: true`, `voice:
      true`, `game_source` a window (not `screen`), `encoder: h264_nvenc` (else read `encoder_note`), `output.fps_measured`
      about 60 and `output.speed` about 1.0; the newest segment grows.
- [ ] Application audio (when enabled, section below): `pactl list short sinks` has `sub01_apps`, a Chromium sink-input
      appears when a page plays sound.
- [ ] Picture: no body displacement, face and hands in frame, desktop text readable in the PiP; the agent is not in quiet
      mode unless intended (`curl -s -H "X-Admin-Token: $(cat $T)" localhost:8836/state`).
- [ ] **Kill drill** before anything else: `streamer_up.py kill` -> actions and speech stop within 1 s, scene stays up ->
      `streamer_up.py resume` -> one harmless action and one spoken line succeed. Vagon: no reconnect or machine start
      happened while killed.
- [ ] Watch and listen to the first completed segment (or 30 s of a test recording) with headphones: voice level, no
      silence where speech was, layout as expected.

### C. During

- Every 5 minutes and at every 10-minute segment roll: `status`; agent last decision age and outcome (`:8836/state`);
  provider active and errors (`provider_switch`, `quiet` rows in `events.jsonl`); voice queue and synthesis time
  (`:8835/state`); chat pending/answered (`/api/home/streamer`); desktop/Vagon phase and `reconnects`; director PID,
  segment growth, `df -h` of the recordings volume; GPU memory.
- The operator watches the local output continuously with `kill` one command away; no manual clicking on `:102` while
  the agent is active (the owner's input goes through the operator console only during a Vagon login).
- Log every incident as UTC time, symptom, action, time to recovery.

### D. Incidents (first action is always the safe one)

| Symptom | Do |
|---|---|
| Unsafe speech, private content on screen, a secret visible | `streamer_up.py kill` at once; then `curl -s -X POST -H "X-Admin-Token: $(cat $T)" localhost:8835/stop`; note the UTC; resume only after the page/state is clean and checked by the operator. The recording may contain it: treat it as sensitive, do not share it. |
| Browser dead / frozen | automatic (relaunch in ~2 s). If no useful action within 60 s: "When something fails" above; kill rather than let it click blindly |
| Model errors, agent silent | quiet mode is by design; Kimi fallback engages by itself. Both down for 5 min: let him read (quiet mode scrolls) or end the session |
| Voice stuck or repeating | `curl -s -X POST -H "X-Admin-Token: $(cat $T)" localhost:8835/stop`; then `restart voice`; never restart the director for a voice problem |
| Application audio clipping or wrong | `streamer_audio.sh down` mutes applications (voice continues); fix later |
| Vagon disconnected / `ended` / `login_required` | no input while not ready (built in); neutral picture; at most the armed reconnects, then it waits for the owner. Never type credentials for him; he uses the console himself. Say nothing about accounts aloud |
| Director not recording / disk full | `director/state`, `df -h`; the watchdog relaunches ffmpeg; a full disk means stop, move recordings to the volume, restart |
| Unreal crash, CUDA OOM, uncontrolled behaviour | `kill`, then `stop`; no live rebuild |

### E. Stop and after

```
runuser -u unreal -- /home/unreal/venv/bin/python $S/scripts/streamer_up.py stop   --source $S --streamer-dir $P --token-file $T
curl -s -X POST -H "X-Admin-Token: $(cat $T)" -H 'Content-Type: application/json' --data '{"operation":"stop"}' http://127.0.0.1:8830/api/home/streamer
```

- [ ] Short outro first, then no new chat requests; `stop` lets ffmpeg close the last segment (check it plays).
- [ ] Vagon: the owner ends the machine himself from his own browser (the runner never presses Stop) and confirms it is
      off; the runner cannot know whether machine time stopped.
- [ ] Keep `recordings/`, `events.jsonl`, `speech/timeline.jsonl`, `layout.jsonl`, `supervisor.json`, the incident list.
- [ ] Record: duration, actions, chat answered, speech errors, restarts, provider switches, Vagon reconnects.
- [ ] If a credential appeared anywhere: revoke and rotate it first, then treat recordings and chat history as sensitive.

## Application audio (planned; `scripts/streamer_audio.sh`)

The pod has no audio device and no PulseAudio today; browser and game sound are not recorded (voice only). The chain
decided in `kimi/DECISIONS.md` B10-B11: one per-user PulseAudio (or pipewire-pulse, whichever the pod has) with a null
sink `sub01_apps`, the desktop Chromium playing into it, the director recording `sub01_apps.monitor` as a fourth
ffmpeg input, voice kept on its own FIFO (never into the sink: it would be recorded twice), applications about -9 dB
and ducked under speech, a limiter at -1 dBFS, about -16 LUFS on the finished segment.

```
S=/home/unreal/.sub01-private/latest-source-20261023
runuser -u unreal -- $S/scripts/streamer_audio.sh check        # what the pod has; installs nothing
runuser -u unreal -- $S/scripts/streamer_audio.sh up           # server if needed + the sink, once; prints the env
runuser -u unreal -- $S/scripts/streamer_audio.sh test         # tone into the sink, 6 s recorded from the monitor, verdict
runuser -u unreal -- $S/scripts/streamer_audio.sh ffmpeg-args  # the director's input and filter lines (W6)
```

To verify on the pod before anyone relies on it (no pod access from here): a server binary exists (apt may be
unavailable; a user-space install is the owner's call, the root disk has ~3.7 GB free); `ffmpeg -devices` lists `pulse`
(else `parec` into a FIFO, documented in the script); `amix` knows `normalize`; the Playwright Chromium finds
`libpulse.so.0`; the desktop runner is started with the printed env and **without `--mute-audio`** (hard-coded today:
W1 adds `--audio`); `pactl list short sink-inputs` shows Chromium while a page plays; for Vagon, that the Cloud Computer
sends audio to the web client at all (unknown until the first session: if not, no pod-side sink can recover it).
Sync: record a page that flashes and beeps on one click, measure the offset in the segment, correct a constant
offset with `adelay` on the early path; accept 50 ms locally, 80 ms through Vagon, drift under 20 ms over two hours.
Until W6 merges the input, the recording stays voice-only and `director/state` does not mention application audio.

## Recording: 60 fps, NVENC, layouts, HLS (director v2)

Director flags (`--child-arg "director=..."`; defaults keep the v1 recording: 24 fps, libx264, no HLS):

| Flag | Meaning |
|---|---|
| `--fps 10-120` (24) | game capture, every `fps=` filter, `-r`, and GOP `-g` = 2 x fps (a keyframe every 2 s) |
| `--desktop-fps 10-60` (15) | desktop capture; never above `--fps` (the graph repeats its frames up to `--fps`) |
| `--encoder libx264\|h264_nvenc\|hevc_nvenc` | NVENC: `-preset p4 -tune ll -rc vbr -cq <crf> -b:v 0 -bf 2 -g 2*fps -pix_fmt yuv420p`; probed once at start (1 s lavfi encode at the real size/rate, same options); a failed probe records with libx264 and logs `encoder_fallback` |
| `--layout webcam\|desktop\|split\|room` | fix the layout; default: follow the last line of `layout.jsonl` |
| `--layout-switch live\|restart` (live) | live: switch inside the running ffmpeg; restart: relaunch ffmpeg at every switch (less CPU) |
| `--hls-dir DIR` | also `DIR/live.m3u8` + 4 s segments from the same encode (tee muxer; off by default) |
| `--rtmp-url-file FILE` / `--rtmp-url URL` | optional third tee branch (flv, behind a dropping fifo; off by default). The director never logs, prints or puts the URL in state (ffmpeg's messages are redacted); use the file, because the supervisor logs child command lines. ffmpeg itself can only take it on its command line, so local users can see it with `ps` while it runs |
| `--cam2-fifo`, `--cam2-json`, `--cam2-stale 3`, `--cam2-interval 1` | second camera paths (default `<streamer-dir>/cam2.mjpeg`, `cam2.json`), freshness limit, check period |
| `--layout-interval 1`, `--switch-timeout 3` | how often `layout.jsonl` is read; how long a live switch waits for ffmpeg's reply |
| `--test-sources`, `--test-seconds N` | lavfi testsrc2/sine instead of X, FIFOs and cam2 (local smoke tests) |

Pod profile (owner, 2026-10-23: 60 fps on everything): `--child-arg "director=--fps 60 --desktop-fps 60 --encoder
h264_nvenc --hls-dir /home/unreal/.sub01-private/streamer/hls"` (start command in B above). Check the exact ffmpeg
command without starting anything: `runuser -u unreal -- /home/unreal/venv/bin/python $S/scripts/streamer_director.py
--streamer-dir $P --fps 60 --desktop-fps 60 --encoder h264_nvenc --hls-dir $P/hls --print-argv` (also runs the probe).

**Layouts.** `webcam` = the game viewport (the frontal webcam shot) full frame + desktop 480x270 bottom-right
(`character` is accepted as its v1 name); `desktop` = desktop full + webcam PiP; `split` = webcam | desktop side by
side; `room` = cam2 full + webcam PiP (needs cam2, otherwise `webcam` is shown). `POST /director/layout {"layout": ...}`
appends a line to `layout.jsonl`; the agent may also append `{"layout": ...}` lines itself. The director reads the last
line every second (a half-written or unknown line is ignored) and switches.

**How a switch works.** In live mode the graph renders every layout of the run at once (all sources normalised to
1920x1080 yuv420p at `--fps`) and `streamselect@layout` picks the recorded one. ffmpeg runs with `-stdin` and the
director writes its interactive filter command `c` + `streamselect@layout -1 map N` to ffmpeg's stdin, then waits for
`Command reply ... ret:0` (ffmpeg 6.1 says "for stream 0", 7.x "for graph 0"): one command, so no half-switched frame;
measured 76-86 ms locally. No reply in `--switch-timeout` (3 s) means the fallback: ffmpeg is relaunched with the new
layout (a 1-2 s gap and a new run prefix). sendcmd cannot do this: it reads its command file once at graph start.
Cost of rendering all four: about 0.5 core more than one layout at 1080p60 (measured on the 4-core test box with
lavfi sources); `--layout-switch restart` avoids it. `events.jsonl`: `layout_switched` / `layout_switch_failed`;
state: `layout` (wanted), `live_layout` (shown), `last_switch`.

**cam2.** Used when `cam2.mjpeg` is a FIFO with a writer and `cam2.json` reports a frame newer than 3 s
(`last_frame_unix`, `last_frame`, ISO or ms accepted; `last_frame_age_s`; else the file's mtime). ffmpeg reads it with
`-use_wallclock_as_timestamps 1 -f mjpeg`; the director keeps a read end open and drains it while ffmpeg does not
read it (a non-blocking writer can attach, a blocking one never stalls). Honest limit: a cam2 that keeps the FIFO open
but stops writing freezes the whole recording, so while ffmpeg reads it the director checks `cam2.json` every second
and relaunches ffmpeg without cam2 once the last frame is 3 s old (gap: about 4-6 s). Without cam2 a `room` request
shows `webcam`; when cam2 comes back the run is relaunched with it only if `room` is wanted (not within 30 s of a
relaunch that dropped it). A cam2 FIFO the game replaces (new inode) also means a relaunch. In restart mode cam2 is
attached only to `room` runs. Missing cam2 = v1 inputs.

**HLS.** Same encode as the recording (tee): `hls_time 4`, list size 6, old segments deleted, `omit_endlist` (a
relaunch does not end the stream for players), `discont_start`, media sequence from the epoch (keeps counting up across
relaunches), `program_date_time`, temp files renamed when complete. A failing HLS or RTMP branch (`onfail=ignore`) never
stops the recording. Local check only: `python3 $S/scripts/streamer_hls_serve.py $P/hls` (127.0.0.1:8839, playlist
no-cache, nothing else served) and `ffprobe http://127.0.0.1:8839/live.m3u8`. Never expose it without the owner's
request; anything on the pod (the agent's Chromium included) can read it while it runs. Browsers need H.264 for HLS;
`hevc_nvenc` is for local files.

**Proving 60.** ffmpeg runs with `-progress pipe:1 -stats_period 5`. State `output` = `fps_measured` (output frames per
wall second over the last 5 s; 60 when ffmpeg keeps up), `fps_ffmpeg` (average since the run started), `speed` (1.0 =
real time), `dup_frames`/`drop_frames`. Each 10-minute segment (and each run's last, `partial`) gets a `segment_fps`
row in `events.jsonl` and in state `segments_fps`: frames, wall_s, media_s, fps (frames/wall), fps_media. A row is
a window of output time numbered like the segment files, not the file itself: the muxer cuts at the first keyframe
after 600 s and progress comes every 5 s, so a row can include a few seconds of the neighbouring file. That proves
the output pace, not that every source delivered 60 distinct frames: the graph's `fps` filters repeat frames a source
did not deliver, and dup/drop do not count those. Check a finished segment offline:
`ffprobe -v error -select_streams v -count_packets -show_entries stream=nb_read_packets,r_frame_rate -of csv=p=0 SEG`
(a full 600 s segment: 36000 packets, 60/1) and the distinct frames of one minute of the webcam layout (the character
always moves; a static desktop legitimately repeats):
`ffmpeg -hide_banner -nostats -i SEG -t 60 -an -vf mpdecimate=max=0,showinfo -f null - 2>&1 | grep -c 'showinfo.*n:'`
(about 3600; a 30 fps source upsampled to 60 gives about 1800). Seen locally: 60.8 fps without cam2 at 1080p60 with
libx264 ultrafast on 4 cores, 36.8 fps (speed 0.4) with cam2 decoding as well; the pod's NVENC and 16 vCPU are
expected to hold 60, and these numbers are how to check it.

## Monitor feed (in-game monitor texture; `scripts/streamer_monitor_feed.py`)

Captures an X display (default `:103`) at 60 fps, scales to 1280x720 and writes MJPEG (q 5, yuvj420p) into
`<streamer-dir>/monitor.mjpeg`, a FIFO the game reads. It never blocks: no reader means frames are dropped and ffmpeg is
stopped after 10 s (restarted when a reader opens the FIFO); a frame that does not fit is dropped whole, a partly
written one is finished first, so a connected reader gets whole JPEGs; ffmpeg is restarted with backoff when it exits.
Across a reader reconnect or a feed crash one JPEG can be truncated: the game must resync on SOI (FF D8) and read
without blocking (the feed pauses without a reader, during backoff and after a crash).
`:103` is the Vagon runner's display: the feed is raw, so a login or account page there reaches the in-game monitor
unless the game's privacy lock covers the monitor texture (it does for the neutral picture; check before a stream).

```
runuser -u unreal -- setsid nohup /home/unreal/venv/bin/python $S/scripts/streamer_monitor_feed.py \
     --streamer-dir $P --display :103 > $P/logs/monitor.log 2>&1 < /dev/null &
curl -s localhost:8840/healthz     # ffmpeg, reader, frames_in/written/dropped, fps_in, restarts, last_error
```

Not yet a `streamer_up.py` child (adding one changes `ORDER`, which the supervisor's tests pin). To add it: `ORDER` +
`"monitor"` after `"director"`; `SCRIPTS["monitor"] = "scripts/streamer_monitor_feed.py"`, `DEFAULT_PORTS["monitor"] =
8840`, `PORT_FLAG["monitor"] = "--port"`, `HEALTH_PATH["monitor"] = "/healthz"`, `START_TIMEOUT["monitor"] = 20.0`,
`DEFAULT_PYTHON["monitor"] = "/home/unreal/venv/bin/python"`; in `build_specs` give it `--streamer-dir` like the
director (the display through `--child-arg "monitor=--display :103"`); and update the tests that list the services.

## Known limits

- No application or browser audio yet: no audio device or PulseAudio on the pod. Only the voice PCM is recorded
  ("Application audio" above is the planned chain; `scripts/streamer_audio.sh check` on the pod says what is missing).
- The privacy lock's neutral picture covers the model and the monitor texture, not this recording: the director grabs
  display `:102` itself, so during a Vagon login the kiosk's login page is in the local MP4 (fix: W1/W6, DECISIONS A2).
  Until then, start the director after `phase: connected`, or treat that recording as private.
- Layout changes are hard cuts (live through streamselect, or a relaunch as fallback); no OBS; RTMP and HLS exist but
  are off by default and nothing public is started without the owner's request.
- A cam2 FIFO that stays open without frames freezes the recording until the director notices (about 4-6 s) and
  relaunches without cam2. `fps_measured` proves the output pace, not distinct source frames (offline check above).
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
VNC or browser source on the desktop frame), cropped and placed 480x270 bottom-right; that is scene `Webcam` (v1
`Character`). Scenes `Desktop` (desktop full, game small), `Split` and `Room` (cam2 full, game small) are the other
layouts. Audio: the voice PCM (`-f s16le -ar 48000 -ac 2`) piped from the pod into a virtual audio device and captured
as an audio input; add the Mac's own browser audio if wanted. Scene switching on `layout.jsonl`-style requests through
obs-websocket gives the same live cuts the pod recorder now makes with streamselect.
