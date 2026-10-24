# Director fifo mode: pre-commit review, part 1 (the director) (Kimi, 2026-10-24)

Kimi via `tools/ask_kimi.py` on the pod (default model, `--max-tokens 48000`; the first try hit the 900 s read timeout,
the second answered 20:52 UTC in 829 s). Attachments: the diff of `scripts/streamer_director.py` in two parts (split at
a hunk boundary). Part 2 (acceptance tool, runbook, tests): `director-fifo-review2.md`.

## Question

Pre-commit code review, part 1 of 2: the director's fifo mode (`scripts/streamer_director.py`), implemented after your
design answer (not attached; summary of what was adopted from it below). Review
the attached diff (two files, the director diff split at a hunk boundary) for correctness bugs, races, resource leaks,
x11-mode regressions and contract violations. Python 3.13 asyncio service; ffmpeg 6.1.1.

Adopted from your design answer:
- `--game-source x11|fifo` (default x11, never inferred); fifo input 0 = the spec's options + `-follow 1`; the copy tap
  (`-map 0:v -c:v copy -f fifo -fifo_format mpjpeg -drop_pkts_on_overflow 1 -attempt_recovery 0 -queue_size 60
  pipe:<actual fd>` with pass_fds=(fd,), the parent's write end closed right after spawn, a reader thread started before
  spawn that parses the multipart header and the JPEG segments for the COM `seq=`, skipping payloads by length, bounded
  header (2048) and part size (32 MB)); tap only on FIFO runs.
- MainSource state machine (backoff 2, 4, 8, 16, 30; back only when retry_at passed AND fresh >= 3 s continuously;
  failures cleared after 60 s of continuously fresh FIFO; its failures separate from the generic crash backoff: a FIFO run
  that ffmpeg leaves within 60 s returns "main_failed" with a 1 s relaunch delay, the generic `_failures` untouched).
- 3 s launch grace for soft staleness (old json / old last write / no writer); FIFO missing, FIFO replaced (inode) and
  tap EOF are acted on at once. "No writer" is confirmed by a second /proc scan 0.6 s later.
- Tap silence only reported (`main_tap_idle` / `main_tap_flowing`), never a source change. Tap overflow (ffmpeg's "FIFO
  queue full" on stderr), frames without a marker, broken headers or a tap error make the window's count invalid
  (`main_tap_ok` false), not a healthy zero.
- SMPTE HD bars placeholder through the same graph, `-re`, no range conversion, no tap.
- Reaper ownership extended to the main FIFO path and the card.
- Counter resets never give negative deltas; `main_max_gap_ms` is a window maximum.

Found while implementing (please check the handling):
- With `-follow 1` ffmpeg does not leave on ONE SIGINT when the FIFO's writer is gone (its interrupt callback only
  fires from the second signal on; the read loop retries forever), and a read blocked on a writer that holds the FIFO
  open without writing ends only on SIGKILL (measured: the first exits 1.0 s after a second SIGINT, the second needs
  SIGKILL). So a FIFO run is stopped with SIGINT, a second SIGINT after 1 s and SIGKILL after 2 s when the main view is
  stale (`_stop_quick`), and SIGINT / 4 s / SIGINT / 8 s / SIGKILL for other relaunches; x11 runs as before (SIGINT, 8 s,
  SIGKILL).
- A counting exception in the tap reader marks the count invalid but keeps draining the pipe until EOF (a stopped reader
  would fill it; a closed one would end the tap output, which the director reads as the input's EOF).

Local evidence: 96 existing director tests unchanged and passing; 37 new tests (fake clock state machine, argv in both
modes, json/status, parser in 1/7/777-byte chunks, real pipes, Director with fake ffmpeg processes that hold the tap's
write end) and one real-ffmpeg test: the director starts on the card (no game), the writer starts (switch to the FIFO
after 1.5 s fresh), a 0.4 s writer close/reopen passes without a relaunch, a stall (writer open, silent) goes to the card
(SIGKILL after 2 s), the writer gone keeps the card while the output keeps its pace, the writer back returns to the FIFO;
every FIFO row has main_tap_ok true, main_unique == main_frames, no repeats; every recording decodes; the card is never
black. Stable 4/4 runs.

Questions:
R1. Bugs or races? In particular: the order in `_run_once` (tap.open before spawn, parent_done in finally, tap.close
    after the process ends), `main_tick` reading `on_air` after the await, the grace path returning before observe(),
    `_main_choice` events, and the drain ownership (drain only while no ffmpeg reads main.mjpeg).
R2. Anything in the x11 path that is not byte-identical (argv, graph, rows, events, state keys added: `game_source_mode`
    and `main` = None)?
R3. Is the stop sequence for FIFO runs right, or should a stale stop go straight to SIGKILL?
R4. Anything that would break on the pod (uid 1001, the game's FIFO mode 0600 owned by the same uid, pipe-max-size
    1 MiB, Python 3.12 there)?
Answer: numbered findings, each with severity (blocker / should-fix / note) and a concrete fix; then "commit: yes/no".
At most ~900 words.

## Answer

1. **blocker — the `main_failed` outcome is not wired to the promised delay.** `_run_once()` introduces `return "main_failed"`, but the diff contains no corresponding change to the loop consuming `outcome`. That loop is not included, so its exact resulting behaviour cannot be determined; the 1 s contract is not implemented by anything shown here. Add an explicit branch before generic crash backoff:
   ```python
   if outcome == "main_failed":
       await self._sleep(1.0)
       continue
   ```
   Leave `_failures` untouched. Without this, an early FIFO exit gets either an immediate iteration or an unrelated/generic delay.

2. **should-fix — drain ownership does not cover the spawn hand-off.** While `_run_once()` awaits `_spawn()`, `drain_tick()` still sees neither `alive` nor `main_on == "fifo"`. If the spawn await yields after the child has opened `main.mjpeg`, the director and ffmpeg can briefly read the same FIFO, potentially splitting a JPEG between readers. Track an explicit `_main_reader_starting` state, set it before spawning a FIFO run, suppress draining throughout that hand-off, and clear it on failure or after `proc`/`main_on` are installed. The normal running/shutdown ownership conditions are otherwise correct.

3. **should-fix — `main_tick()` can apply an old check to a new run.** Reading `on_air` after the await avoids deliberately stopping an already-superseded run, but it does not associate the result with the run that initiated the check. A restart during `_check_main()` can install a new `proc`, `seq_tap`, and `_main_ident`; the old result is then stored in `main_report` and evaluated against that new run. Capture `self.launches` (or a dedicated generation) before the await and discard the result if it changes; only then assign `main_report`. Keep the post-await `_restart_reason` check.

4. **should-fix — launch grace skips the freshness observation.** The early `"grace"` return leaves `fresh=True` and `fresh_since` advancing even though this check found the source stale. Status is consequently misleading, and a stale/recovered interval during grace can incorrectly count toward “continuously fresh”. Call `observe(now, fresh, reason)` before the grace return, but defer `tick()`—and therefore failure/relaunch—until grace expires. Hard failures should continue bypassing grace.

5. **should-fix — one non-live FIFO graph omits the FIFO rate/EOF chain.** In `build_filter_complex()`, when the game is the PiP and another source is main, input 0 receives `game_scale()` but not `game_rate()`. Thus `fps,tpad=...clone` is present in live mode and game-main layouts, but absent in this layout. Prefix that PiP chain with `game_rate()` when `main == "fifo"`—or normalise input 0 once—while retaining the existing x11 string.

6. **should-fix — tap setup is not exception-safe.** `tap.open()` and `build_ffmpeg_argv()` both occur before the `try` protecting spawn. An argv-construction exception leaks the pipe descriptors and leaves the reader thread blocked. Protect construction as well as spawn, calling `parent_done()` and closing/joining the tap on every pre-spawn exit. The normal successful ordering—reader before spawn, parent write end closed immediately afterwards, reader joined after process exit—is correct.

7. **note — x11, stopping, and pod checks.** For `main=None`, I find no x11 argv, filter-graph, segment-row, or event change; `_terminate(..., nudge=None)` is equivalent to the old sequence, and the two status additions are as specified. Reaper matching is intentionally broader, including under an x11 configuration. `_main_choice` also avoids duplicating the tick-driven “back” event.

   Keep the FIFO stop sequence: stale SIGINT/second-SIGINT-at-1-s/SIGKILL-at-2-s handles both measured cases; unconditional SIGKILL would unnecessarily sacrifice clean finalisation. No code-level pod blocker is apparent: mode `0600` with shared uid works, the 1 MiB pipe request is best-effort, and the constructs used support Python 3.12. Actual 3.12 test results were not supplied, so run the suite there.

**commit: no**

## What was done

1. Not a defect, rejected with evidence: the run loop (unchanged, outside the diff) already gives every outcome other
   than "crash" a 1 s delay (`delay = backoff_delay(self._failures) if outcome == "crash" else 1.0`), and
   `test_a_short_fifo_run_that_crashes_goes_to_the_placeholder_without_the_crash_backoff` asserts the
   `ffmpeg_restart_scheduled` row `{"outcome": "main_failed", "delay": 1.0}` and `_failures == 0`. A comment now says so
   at that line.
2. Fixed: `_main_handoff` is set before a FIFO run's tap/argv/spawn and cleared once `proc` and `main_on` are installed
   (or on any failure); `drain_tick` never drains main.mjpeg while it is set
   (`test_no_drain_while_a_fifo_run_is_being_spawned`).
3. Fixed: `main_tick` remembers `launches` before its check and discards the result ("superseded") if a run started
   meanwhile, before storing `main_report` (`test_a_check_that_outlived_its_run_and_the_grace_still_observes`).
4. Fixed: the grace path observes the freshness first (so `fresh_since` breaks), and only defers the tick (same test).
5. Fixed: in a one-layout graph where the game is the PiP (`desktop`, `room` in restart mode), the FIFO main view gets
   its `fps` + `tpad` chain too; the x11 string is unchanged (`test_every_restart_mode_graph_converts_the_fifo_main_view`).
6. Fixed: the tap is opened and the argv built inside the spawn's `try`; any exception closes the tap (both ends, the
   reader joined) and clears the hand-off (`test_the_tap_is_closed_when_the_command_line_cannot_be_built`).
7. Kept the stop sequence. The suite was also run under Python 3.12.3 (the pod's director interpreter): 202 passed
   (director, fifo mode, acceptance).
