# Director fifo mode: follow-up pre-commit review (Kimi, 2026-10-24)

Kimi via `tools/ask_kimi.py` on the pod (default model, `--max-tokens 48000 --timeout 1500`, answered 21:15 UTC in
447 s). Attachment: the current versions of every function changed after reviews 1 and 2
(`director-fifo-review1.md`, `director-fifo-review2.md`) and the runbook's switch section.

## Question

Follow-up pre-commit review: your two reviews of the director's fifo mode said "commit: no". Below is what was done
with each finding; attached (delta.txt) are the CURRENT versions of every changed function and the runbook section, not
a diff. Please check that each fix is right and complete, and say whether anything still blocks the commit.

Review 1 (director):
1. "main_failed not wired to a delay": not a defect. The unchanged run loop gives every outcome other than "crash" a
   1 s delay (`delay = backoff_delay(self._failures) if outcome == "crash" else 1.0`); a test asserts the
   `ffmpeg_restart_scheduled` row {"outcome": "main_failed", "delay": 1.0} and `_failures == 0`. A comment says so now.
2. Drain during the spawn hand-off: `_main_handoff` is set before the tap/argv/spawn of a FIFO run and cleared when
   `proc`/`main_on` are installed or on any failure; `drain_tick` skips main.mjpeg while it is set (test: a drain tick
   during an awaited spawn never drains).
3. A check that outlived its run: `main_tick` remembers `launches` before the threaded check and returns "superseded"
   (before storing `main_report`) if a run started meanwhile (test).
4. Grace: `observe()` now runs before the grace return; only the tick (failure/relaunch) is deferred (test: a stale
   check in the grace breaks `fresh_since`).
5. The game as PiP in a one-layout graph (desktop/room, restart mode) now gets the FIFO's `fps` + `tpad` chain; x11
   strings unchanged (test over all five layouts: the FIFO graph minus the FIFO-only pieces equals the x11 graph).
6. Exception safety: tap.open(), the argv build and the spawn are all inside the try; any exception closes the tap (both
   ends, reader joined) and clears the hand-off (test: a failing argv build leaves no open tap).
7. Kept the stop sequence. Suite run under Python 3.12.3 too.

Review 2 (acceptance, runbook, tests):
1. Short placeholder rows: placeholder rows are now collected from ALL in-window segment_fps rows before the partial
   filter and fail however short (tests: a 39 s partial placeholder row next to a healthy FIFO row; a placeholder row
   alone is FAIL, not "no row").
2. Recovery skips every row whose `main_tap_ok` is not true (false, null, missing); none valid -> None (pending until
   restart + 660 s, then unrecovered) (parametrized tests incl. an invalid row followed by a valid/slow one).
3. The weighted gate compares the unrounded rate; the reported value has 3 decimals (tests: exactly 59.5 passes, 59.4967
   fails, mixed durations 600 s @ 59.6 + 60 s @ 59.0 pass weighted 59.545 where a row average 59.3 would fail).
4. Documented: a planned main-view fault gives error_recovered PASS and fps_director FAIL; run the all-green
   acceptance on a clean window.
5. Runbook: the supervisor stop/start restarts every child (gap, new runs, voice model reload); keep the STOP file;
   set webcam_only first if a private page could show (the card is not a privacy cut); check `status`, HLS health and
   the main view afterwards; same for the rollback; the `.bak-before-fifo` backup is never overwritten.
6. Integration tests: every row of every FIFO run is checked (tap_ok true, gaps/repeats/noseq/bad/cut/overflows 0);
   each run's tap (recorded per run) has unique == max_seq - first_seq + 1 (no frame lost between its first and last),
   the rows' sum within one progress block of the tap's total, and all taps' total <= the writer's written. New real
   test: the director's tap reader stops for 8 s (outside the counter's lock): ffmpeg's fifo muxer overflows, the
   recording keeps its pace on the same run (>= 25 fps x 7 s of output during the stall, no relaunch), the window has
   main_tap_ok false with overflows and gaps counted, main_tap_idle then main_tap_flowing.
   While doing this I hardened the parser (see SeqCounter): a part that does not end with EOI is `cut` (a frame the
   game discarded mid-write reaches ffmpeg as a packet without EOI): never unique, its sequence shows as a gap; bytes
   before the part's SOI (a frame whose start the director drained before ffmpeg took over: ffmpeg's parser keeps them
   in the first packet) are tolerated and counted as `trimmed` instead of making the part `noseq` (which would have
   invalidated the whole first window of a run). Rows carry `main_cut`.
7. Runbook "Go / no-go before the switch": a real v24 soak (markers, close/reopen without relaunch, main_fps >= 59.5
   with a valid tap, main_unique ~ game_written, CPU) before enabling, then the spec's step 6 acceptance.

Tests now: 96 existing director tests unchanged, 42 fifo-mode tests (2 with real ffmpeg), 72 acceptance tests (61
existing + 11), all passing; the whole tests/test_streamer_*.py suite passes.

Answer: numbered remaining findings with severity (blocker / should-fix / note) and a concrete fix, then
"commit: yes/no". At most ~600 words.

## Answer

1. **note — malformed zero-length multipart header.** In `SeqCounter.feed`, `Content-Length: 0` matches `m`, but satisfies neither branch: it is neither accepted nor counted as `bad`. Normal ffmpeg JPEG output is unaffected, and this does not bypass the cut/sequence validity checks, so it is not a commit blocker. Tighten it while nearby:
   ```python
   length = int(m.group(1)) if m else None
   if length is not None and 0 < length <= SEQ_MAX_PART:
       self._need = length
   else:
       self.bad += 1
   ```

No other remaining findings at **blocker** or **should-fix** level. The supplied code addresses the earlier findings: the hand-off excludes draining throughout spawn and is cleared on every exit; superseded checks return before storing reports; grace still observes freshness; the FIFO PiP receives the rate/EOF chain; spawn setup is exception-safe; placeholder rows fail before partial filtering; recovery strictly requires `main_tap_ok is True`; and the weighted gate compares the unrounded value. The runbook covers the full-child restart, privacy precaution, verification, rollback, backup preservation, and real-v24 soak.

The integration-test bodies were not included, so their implementation cannot be independently audited here; this approval relies on the reported test runs for those.

**commit: yes**

## What was done

1. Applied: a part header with no, zero or an absurd `Content-length` is counted as `bad` and the parser resynchronises
   (test extended: `Content-length: 0` counts as bad, no frame). Then committed.
