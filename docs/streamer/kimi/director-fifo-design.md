# Director fifo mode: design consultation (Kimi, 2026-10-24)

Kimi via `tools/ask_kimi.py` on the pod (default model, `--max-tokens 48000 --timeout 900`, answered 20:01 UTC in
582 s; a first try with 24000 tokens ended while reasoning). Attachments: the spec section "Structural fix" of
`docs/streamer/SAWTOOTH-20261024.md` and an excerpt of `scripts/streamer_director.py` (the cam2 FIFO handling, the
graphs and argv, OutputMeter, the tick loops). What was adopted is listed at the end.

## Question

You are reviewing a design for SUB-01's stream director (Python asyncio service that runs ONE ffmpeg 6.1.1 process
composing a game's main view, a second camera "cam2" (MJPEG FIFO from the game), a desktop x11grab and voice PCM into
60 fps NVENC MP4 segments + local HLS). Attached: the spec section ("Structural fix", steps 4-6) and an excerpt of the
current director code (cam2 FIFO handling, the -progress meter, the live graph).

Why: today the director grabs the game window on Xvfb :99 with x11grab. The X11 present path costs growing CPU (a
sawtooth) and holds the game to ~49 fps. A parallel worker builds the game side: the game renders offscreen and writes its
main view as baseline 1920x1080 JPEGs (full-range YCbCr, q~85, JFIF + one COM segment `seq=<n>`) into the FIFO
`streamer/main.mjpeg` (game creates it; one writer, O_NONBLOCK + poll, whole frames, a cut frame is discarded and counted),
plus `streamer/main.json` once per second (atomic rename): sequence, fps, written, dropped_slots, dropped_encode,
dropped_queue, dropped_noreader, frames_discarded_midwrite, pipe_size, last_write_utc (unix seconds float, like cam2.json's
*_utc fields). My job: the director side. The coordinator's requirements:
- `--game-source fifo|x11`, explicit, never inferred; x11 = exactly today's behaviour and the default for now.
- fifo input 0: `-thread_queue_size 512 -use_wallclock_as_timestamps 1 -probesize 2000000 -analyzeduration 1000000 -f
  mjpeg -framerate 60 -i main.mjpeg`, scaled like cam2 (full -> limited range), tpad clone after EOF.
- staleness check every 1 s like cam2's: stale = no writer, main.json older than 2 s, or last_write_utc older than 2 s.
  Stale -> kill the ffmpeg run and relaunch on a visible placeholder card (lavfi), never a silent black grab. Retry the
  FIFO with backoff 2, 4, 8 s up to 30 s; switch back once main.json has been fresh for 3 s. Events for each transition.
- Measure "unique main-view frames per second reaching the director" cheaply (gate: >= 59.5), expose it in the director
  state and the per-segment rows for the acceptance tool. Suggested inputs: ffmpeg -progress dup/drop, main.json
  `written`, optionally a light tap reading the seq= markers.
- Layouts (webcam, room, split, desktop, webcam_only), privacy cut, retention and speed guard identical in both modes.

Facts I measured locally (ffmpeg 6.1.1, same version as the pod):
F1. The -progress dup_frames/drop_frames count only the OUTPUT vsync (-r). The graph already makes every source CFR
    with `fps=60` filters (each source is fps-filtered before overlay/streamselect), so a source that delivers 50 fps is
    padded inside the graph and dup stays 0 (the pod's real rows: fps 60.0, dup 0, drop 0 while the game ran at 49).
    So -progress dup/drop cannot measure unique main-view frames.
F2. `-stats_mux_pre` does NOT write anything for a stream-copy output in 6.1.1 (tested: no file created). `ni`/`{ti}`
    directives are unavailable for filter_complex outputs.
F3. The mjpeg decoder does not export COM content (only logs it at INFO with -debug pict_info; the director runs
    -loglevel warning and keeps a 40-line error tail).
F4. A second ffmpeg OUTPUT that stream-copies input 0 works: `-map 0:v -c:v copy -f fifo -fifo_format mpjpeg
    -drop_pkts_on_overflow 1 -attempt_recovery 0 -queue_size 60 pipe:3` (fd 3 = the write end of a pipe the director
    passes with pass_fds). The director reads multipart parts ("Content-length: N"), looks only at the first bytes of
    each JPEG for the COM `seq=`, skips the rest by length. Test: 8 s at 60 fps -> 480 parts, 480 unique seqs
    (seq=0..479), no extra ffmpeg CPU measurable (4.13 vs 4.24 s), Python reader 0.16 s CPU for 41 MB (my naive parser;
    a skip-by-length parser does O(chunks) Python work). ffmpeg remains the FIFO's only reader.
F5. Fault isolation of that tap: reader closes its end -> "Broken pipe ... Error muxing a packet" on out#1, the main
    output keeps running to its end (exit code 224 at the end). Reader stalls (never reads) -> fifo muxer logs "FIFO
    queue full" and drops; the main output keeps 60 fps; but at shutdown ffmpeg waits to flush the tap (hung until the
    reader resumed). The director SIGKILLs after an 8 s grace anyway, and its reader thread reads until EOF.
F6. EOF on a writer close. Emulating the game's contract (non-blocking writer, 500 ms per-frame deadline, then close and
    reopen), a writer that closes for 0.5 s and reopens: WITHOUT `-follow 1` ffmpeg reads EOF at once (the tap saw 150
    frames then EOF; the later frames never reach ffmpeg; input 0 is finished for that run, tpad clones the last frame
    and the game's next writes fill the pipe until its deadline: last_write_utc goes stale, the director relaunches on
    the placeholder, then backoff + 3 s fresh: ~6-8 s without a live main view for a 0.5 s writer gap). WITH the file
    protocol's `-follow 1` input option (read() == 0 -> EAGAIN, retried every 1 ms) the reopen is seamless (329 of 330
    frames through the tap), but when the writer is gone for good the input never ends: the whole graph stalls (all
    layouts freeze, as a stalled cam2 does) until the staleness tick relaunches on the placeholder (<= ~3 s).
    Risk without follow: every ffmpeg launch on the FIFO stops reading it for ~1-2 s while the later inputs open and
    probe (cam2 probes ~0.6-1 s), longer than the game's 500 ms deadline, so a close (and an EOF) right at start-up is
    likely. Note: the tap also tells the director at once when input 0 hit EOF (its pipe closes) while ffmpeg runs.

My proposed design (please criticise; I will implement what we agree):

D1 Flags: `--game-source x11|fifo` (default x11), `--main-fifo` (default <streamer-dir>/main.mjpeg), `--main-json`
   (default main.json), `--main-stale 2.0`, `--main-fresh 3.0`, `--main-interval 1.0`. x11 mode builds exactly today's
   argv (the existing tests pin it). In fifo mode the game window lookup (xdotool) is skipped; `--game-display` unused.

D2 State machine (pure class, injectable clock, unit-tested), states `fifo` and `placeholder`:
   - fresh(now) = FIFO exists and is a FIFO, a process holds it open for writing (/proc scan as for cam2), main.json
     mtime age <= 2 s, last_write_utc age <= 2 s. While ffmpeg reads the FIFO: json checks every tick, /proc writer scan
     every 5th tick (as cam2); also stale if the FIFO was replaced (new inode) since the launch.
   - Start: first launch on fifo if fresh now, else on the placeholder (event main_source{to: placeholder, reason}).
   - fifo -> placeholder: stale at a tick, or the fifo run crashed (ffmpeg exited by itself) within 60 s ->
     failures += 1, retry_at = now + min(30, 2 * 2**(failures-1)) (2, 4, 8, 16, 30, 30 ...), event, relaunch.
   - placeholder -> fifo: now >= retry_at AND fresh continuously for >= 3 s -> event, relaunch on fifo.
   - failures reset to 0 after the fifo run has stayed fresh for 60 s.
   - Other relaunches (layout restart mode, voice, cam2, watchdog, speed guard) keep the current source; a relaunch
     that finds the source stale goes to the placeholder through the same transition.
   - The director holds its own read end on main.mjpeg (like cam2) so the game can open O_NONBLOCK, and drains it while
     ffmpeg does not read it (up to 8 MB per 0.1 s tick).
D3 Placeholder: input 0 = `-re -f lavfi -i smptehdbars=size=1920x1080:rate=<fps>` (no font dependency: drawtext needs
   fontconfig and a missing font would make every placeholder launch fail). Same graph as fifo/x11 (only input 0
   differs), so every layout, the privacy cut (webcam_only = the card alone, no desktop) and room work unchanged.
D4 Metric: the mpjpeg copy tap of F4, always on in fifo mode. Director counters (cumulative per run): parts, unique
   (seq > max seen), repeated (seq <= max seen), gaps (sum of seq jumps - 1), noseq, max inter-arrival gap (ms),
   last_seq, last part time. Every -progress block (5 s) snapshots them; OutputMeter windows (the segment_fps rows) get
   deltas: main_source, main_frames, main_unique, main_fps (= unique / wall_s), main_repeated, main_gaps, main_noseq,
   main_max_gap_ms, and from main.json snapshots game_written (delta), game_fps (delta/wall), game_dropped (sum of
   the dropped_* + discarded deltas). State `main` = {mode, source, reason, failures, retry_in_s, fresh_for_s, json
   age, last_write age, writer, tap: last 5 s unique fps etc.}. Rows of x11 runs stay byte-identical (no main_* keys).
   Placeholder runs: main_source "placeholder", main_fps 0.
D5 Acceptance tool (scripts/streamer_acceptance.py has 16 criteria; tests pin the list): fold the main view into
   existing criteria rather than add a 17th (a 17th would be MISSING in x11 mode and make every x11 verdict
   inconclusive): fps_director fails a row with main_source placeholder or main_fps < 59.5; two_cameras counts `room`
   only while the run's main source is not the placeholder (the webcam PiP would be the card); error_recovered treats a
   `main_source -> placeholder` event as a fault recovered by an ffmpeg_started with main_source fifo (deadline 300 s:
   a game restart takes 1-2 min) followed by healthy output; output health also needs main_fps >= 59.5 when present.

Questions:
Q1. Is the mpjpeg copy tap (F4) the right cheap measure, or would you rather the director relay the FIFO itself
    (Python reads main.mjpeg, counts seqs, writes whole frames to a pipe ffmpeg reads), or only main.json `written`
    deltas? Any failure mode of the copy tap I missed (memory, ordering, startup, the tap EOF while the main output
    continues on tpad, the shutdown hang of F5)?
Q2. The state machine: is my reading of "backoff 2, 4, 8 s up to 30 s" and "fresh for 3 s" right? Should a fifo run
    that the director sees deliver no tap frame for > 2 s (while main.json still says fresh) also count as stale? I
    lean to NOT switching on it (a cam2 or encoder stall can starve the tap too; the watchdog and speed guard cover
    those) but to log it and expose it.
Q3. Placeholder: smptehdbars without text OK? Or a dark card with a moving element so a frozen output is visible?
Q4. Acceptance integration D5: agree, or prefer a separate criterion?
Q5. Anything else for parity (privacy, retention, speed guard, the /proc reaper of stale ffmpegs: it matches "x11grab"
    in the argv, which a fifo-mode argv still has for the desktop input)?
Q6. F6: use `-follow 1` on the main FIFO input (a deviation from the spec's input options, which I would report), or
    keep the spec's options and add a rule "tap EOF while main.json is fresh -> relaunch straight on the FIFO", or
    something else (a launch grace for the last_write_utc check, the director holding a write end so ffmpeg never sees
    EOF, reordering inputs so the FIFO is opened last)? Which gives the shortest outages with the least risk?
Answer in English, numbered, concise (at most ~900 words), with concrete changes. Do not restate the question.

## Answer

1. **Use the copy tap.** A Python relay adds another 12–24 MB/s copy/framing path and owns difficult resynchronisation and backpressure cases; `main.json.written` alone cannot see frames drained before launch or lost before ffmpeg accepts them. The tap measures frames accepted from input 0, not necessarily composited, so output-health checks remain necessary. Enable it only for runs actually reading `main.mjpeg`, not placeholder runs. Append it as a separately scoped output. Important: `pass_fds` does **not** rename an arbitrary descriptor to 3; use `pipe:{actual_wfd}` with `pass_fds=(actual_wfd,)`, or explicitly arrange descriptor 3. Close the parent’s write end after spawn. Start the reader immediately, bound MIME-header/part sizes, parse JPEG segments for COM rather than scanning arbitrary bytes, and discard payloads by length. Keep draining through termination until ffmpeg is killed; otherwise F5’s shutdown hang remains. The tap queue is roughly 24 MB at 60 × 400 KB, plus overhead. Treat tap overflow or inability to obtain sequence numbers as an invalid measurement, not healthy zero fps.

2. **The backoff interpretation is correct:** `min(30, 2 * 2**(failures-1))`, giving 2, 4, 8, 16, 30…. Require **both** `now >= retry_at` and continuously fresh for at least 3.0 s; reset `fresh_since` on every failed predicate, and perform a final writer/inode check before switching. Keep these failures separate from generic ffmpeg `_failures`, and do not apply both backoffs to one relaunch. Reset only after 60 s of continuously fresh FIFO operation. I agree that tap silence alone should not change source: expose `tap_idle_s`, emit threshold/recovery events, and leave stalls to the watchdog/speed guard. **Tap EOF while ffmpeg remains alive is different:** request a relaunch through the normal source-selection/backoff path, because otherwise that run can remain on tpad indefinitely.

3. **SMPTE bars are acceptable**, without `drawtext`; a dark card is less distinguishable from failure. A small lavfi-generated moving element is useful for operators but must not become a health detector. Keep `-re`. Also implement the missing source normalisation everywhere: full-to-limited conversion and `tpad=stop=-1:stop_mode=clone` must cover live, restart, split and the early `webcam_only` graph path. Do not blindly apply MJPEG full-range conversion to the lavfi card; produce equivalent normalised source pads instead.

4. **Keep 16 criteria, with explicit sub-reasons.** In x11 mode, retain exactly the old verdict logic. For healthy FIFO legs, an unexpected placeholder row fails; evaluate the 59.5 gate using full windows and the leg’s weighted `sum(main_unique)/sum(wall_s)`, not tiny run-boundary partial rows. Expected placeholder intervals during fault-injection tests belong to `error_recovered`, not the steady-state fps verdict. An invalid tap makes that measurement inconclusive. The `two_cameras` amendment is right. For recovery, require `placeholder -> ffmpeg_started(main_source=fifo)` within 300 s, followed by two consecutive healthy progress windows, including output health and `main_fps >= 59.5`.

5. **Preserve parity by branching early enough that x11 argv and graph construction are untouched.** Route source relaunches through the existing privacy, segment-finalisation, retention, HLS and watchdog paths. Placeholder output still grows at real time, so those guards deliberately do not establish main-view health. Today’s reaper still matches the desktop `x11grab`, including placeholder launches, but extend its ownership predicate to the recording prefix/main FIFO rather than relying on that indefinitely. Make FIFO draining an explicit ownership state: never drain between ffmpeg spawn and confirmation that its FIFO descriptor is closed. The proposed 8 MB/0.1 s provides 80 MB/s capacity, ample versus approximately 24 MB/s input. Finally, handle sequence/JSON counter resets without negative deltas; `main_max_gap_ms` must be a window maximum, not a counter delta.

6. **Ship `-follow 1` on input 0 and report the deviation.** It is the tested option that makes a 0.5 s close/reopen nearly seamless. Add a bounded **3 s launch grace** for source-staleness kills—FIFO replacement and process failure remain immediately actionable—because start-up pipe filling can otherwise make `last_write_utc` stale just before recovery. Also debounce a `/proc` “no writer” observation for approximately 0.6 s or confirm it twice; otherwise a transient close can still trigger the placeholder despite `follow`. JSON/`last_write_utc` continue to bound genuine disappearance. Do not use immediate EOF/fresh relaunch as the primary mechanism: it sacrifices healthy runs and can loop during start-up. Reordering inputs or grace alone does not fix mid-run EOF. If the argv deviation is rejected, use a director-held keep-alive write descriptor instead, never together with `follow`: open it after the read end, never write through it, and exclude your own PID/fd from writer detection. With either approach, permanent writer loss can freeze the graph until the roughly 3 s stale detection, plus relaunch latency.

## What was adopted

- Q1 the copy tap: adopted as answered (only on FIFO runs, `pipe:<actual fd>` with `pass_fds`, the parent's write end
  closed after spawn, the reader started before spawn, bounded header and part size, the COM read from the JPEG's
  segments, payloads skipped by length). The reader drains until EOF even after a counting error. Tap overflow (ffmpeg's
  "FIFO queue full"), unmarked frames, broken headers or a tap error mark the window's count invalid (`main_tap_ok`
  false), never a healthy zero.
- Q2 the state machine: as answered (2, 4, 8, 16, 30 s; both the backoff and 3 s of continuous freshness; reset after
  60 s of continuously fresh FIFO operation; main-view failures separate from the generic crash backoff). Tap silence is
  reported (`main_tap_idle` / `main_tap_flowing`), never a source change; a tap EOF while ffmpeg runs relaunches through
  the normal backoff path.
- Q3 SMPTE HD bars without text, `-re`, through the same graph, no range conversion. Range conversion and `tpad` were
  already applied to every graph path of input 0 (the excerpt sent was the pre-change code).
- Q4 kept 16 criteria; x11 rows judged as before; weighted FIFO gate; invalid count = missing evidence; `two_cameras`
  amendment; `main_changed` -> fifo restart recovery with a 300 s deadline. Deliberate difference: a placeholder row
  always fails `fps_director` (the 30-minute recording must show the main view at 60); events.jsonl has only 10-minute
  rows, so the recovered run's first row (not two 5 s progress windows) decides its health.
- Q5 reaper ownership extended to the main FIFO path and the card; drain only while no ffmpeg reads main.mjpeg.
- Q6 `-follow 1` shipped (the one deviation from the spec's input options, reported to the coordinator), 3 s launch
  grace for soft staleness, "no writer" confirmed by a second scan 0.6 s later. Found afterwards and handled: with
  `-follow 1` one SIGINT does not stop ffmpeg when the writer is gone (its I/O interrupt needs a second signal), and a
  read blocked on a silent writer needs SIGKILL; a stale FIFO run is stopped with SIGINT, SIGINT after 1 s, SIGKILL
  after 2 s.
