# Director fifo mode: pre-commit review, part 2 (acceptance, runbook, tests) (Kimi, 2026-10-24)

Kimi via `tools/ask_kimi.py` on the pod (default model, `--max-tokens 48000 --timeout 1500`, answered 20:59 UTC in
413 s). Attachments: the diff of `scripts/streamer_acceptance.py`, `docs/streamer/RUNBOOK.md` and
`tests/test_streamer_acceptance.py`, and the new `tests/test_streamer_director_fifo.py`.

## Question

Pre-commit code review, part 2 of 2: the acceptance tool and the operator runbook for the director's fifo mode
(part 1 was the director itself). Attached: the diff of `scripts/streamer_acceptance.py`, `docs/streamer/RUNBOOK.md`
and `tests/test_streamer_acceptance.py`, and the new test file `tests/test_streamer_director_fifo.py`.

What the acceptance change does (your design answer Q4, adopted): 16 criteria kept; x11-mode rows (no `main_source`)
judged exactly as before. fps_director: a segment_fps row with `main_source` "placeholder" fails; the FIFO rows (full
rows and partial rows >= 60 s, the existing filter) need sum(main_unique)/sum(wall_s) >= 59.5 over the rows whose
`main_tap_ok` is true; rows with an invalid count make it MISSING (inconclusive) unless something else already fails.
two_cameras: `room` time does not count while the run's main view is the placeholder (from `ffmpeg_started.main`).
error_recovered: `main_changed` to the placeholder (also the first one at a director start without a game) is a fault,
deadline 300 s, recovered by an `ffmpeg_started` with main "fifo" followed by a segment row of that run with fps_media
>= 59.9, dup/drop 0 and main_fps >= 59.5 (rows with an invalid count are skipped; none yet -> pending until 600 + 60 s
after the restart, as for other director restarts). Note one deliberate difference from your answer: a placeholder row
always fails fps_director (the 30-minute acceptance recording must show the main view at 60; a planned fault injection
on the main view is then judged by error_recovered AND fails fps, as a killed game already fails fps_game). The
"two consecutive healthy progress windows" you asked for are not in events.jsonl (only 10-minute rows are logged), so
the first row of the recovered run decides.

RUNBOOK: the mode, staleness and placeholder, the unique-frame metric and its limits, the switch (deploy code with
x11 still default, then restart the supervisor with one more `--child-arg "director=--game-source fifo"`, then relaunch
the game offscreen: the card covers the game's restart, never a black :99 grab), the checks, the rollback.

Questions:
S1. Logic errors in the acceptance changes (row selection, weighting, the recovery predicate and health, on_air main)?
S2. Is the deliberate difference (placeholder rows always fail fps_director) acceptable, or should it be weighted /
    excused when an injected fault explains it?
S3. Is the switch/rollback order in the RUNBOOK safe (privacy cut, recording continuity, the supervisor restarting
    every child)? Anything missing for the coordinator?
S4. Test gaps in tests/test_streamer_director_fifo.py worth closing before the commit?
Answer: numbered findings with severity (blocker / should-fix / note) and a concrete fix; then "commit: yes/no".
At most ~800 words.

## Answer

1. **blocker — short placeholder rows can escape `fps_director`.** `main_view_rows()` receives the already-filtered `rows`: full rows and partial rows ≥60 s. A 39 s placeholder run therefore produces a partial row that is never checked, despite “a placeholder row always fails”. Keep that filter for the FIFO weighted metric, but collect placeholder rows from **all in-window `segment_fps` rows before the partial-row filter** and fail on any of them. Add a regression with a 39 s partial placeholder row and otherwise healthy output.

2. **blocker — recovery does not skip every invalid tap count.** In `output_healthy()`:
   ```python
   r.get("main_tap_ok") is False
   ```
   skips only explicit `false`. A missing/`None` value—notably no tap—can either cause immediate `unrecovered`, or recovery from an untrusted `main_fps`. Use:
   ```python
   if r.get("main_source") == "fifo" and r.get("main_tap_ok") is not True:
       continue
   ```
   Test `None`, missing, and `False`; an invalid first row followed by a valid row; and no valid row remaining pending until `ffmpeg_started + 660 s`.

3. **should-fix — rounding can move a failing weighted rate across the gate.** `weighted` is rounded to two decimals before comparison, so an actual 59.496 fps can pass as 59.50. Calculate `raw_weighted`, compare that against `TH["source_min_fps"]`, and round only the reported metric/message. Add exact-boundary and just-below-boundary tests, plus mixed-duration rows so weighted averaging is genuinely distinguished from a row average.

4. **note — `on_air` and the deliberate policy are sound.** Taking `main` from `ffmpeg_started` is correct: `main_changed` precedes the relaunch and must not alter the on-air span early. Always failing placeholder rows is also acceptable; do not weight or excuse them. A planned injection should produce `error_recovered=PASS` **and** `fps_director=FAIL`. Document that expected combined result, and use a clean 30-minute window for the all-green acceptance run so a healthy recovery does not trigger an unnecessary rollback.

5. **should-fix — the source-switch order is safe, but the coordinator procedure is incomplete.** FIFO director → offscreen game, and windowed game → x11 director, correctly avoid a black `:99` grab. However, the placeholder is not a stream-wide privacy cut, and recording is not continuous: the deploy restart, full supervisor restart, and each source relaunch create gaps/new runs. Explicitly state that supervisor stop/start restarts **every supervised child**; invoke the existing privacy/BRB procedure before that stop, hold it until all children and the game are healthy, and run the normal post-deploy checks for every child. Verify recording and HLS/viewer recovery; continuity across the whole-supervisor restart cannot be established from this diff. Apply the same protocol to rollback. Also make `.bak-before-fifo` creation non-overwriting so rerunning deployment cannot destroy the known-good backup.

6. **should-fix — strengthen the integration test’s central claim.** `test_real_ffmpeg_fifo_start_blip_stall_gone_and_back` says the tap counts every written frame, but `by_run` retains only the last row per run and the count assertions are merely lower bounds. Group and check **all** rows; require zero gaps/noseq/bad/overflows on every healthy FIFO row and compare per-run unique counts with writer/game counters, documenting any boundary allowance. A real tap-overflow/backpressure test would also be valuable: injecting the stderr line proves only the counter, not that ffmpeg’s recording output survives.

7. **note — rollout evidence remains outstanding.** The 320×180, 30 fps synthetic-JPEG test is useful smoke coverage, but not proof of v24 behaviour or 1920×1080/60 NVENC operation. Make a real-v24 soak, including seq markers and FIFO close/reopen behaviour, a go/no-go gate before enabling fifo mode on the pod.

commit: no

## What was done

1. Fixed: placeholder rows are collected from all in-window `segment_fps` rows before the partial-row filter and fail
   however short (`test_a_short_placeholder_row_fails_too`: a 39 s row next to a healthy FIFO row, and alone).
2. Fixed: the main-view recovery skips every row whose `main_tap_ok` is not true (false, null, missing); none valid ->
   pending until restart + 660 s, then unrecovered (`test_the_main_view_recovery_skips_rows_without_a_valid_count`
   for the three cases with a valid and a slow row after it, `test_a_main_view_recovery_without_a_valid_row_is_pending_until_660_s`).
3. Fixed: the weighted gate compares the unrounded rate, reported with 3 decimals
   (`test_the_weighted_main_view_gate_is_unrounded_and_weighted_by_wall_time`: exactly 59.5, 59.4967, and mixed
   durations where a row average would disagree).
4. Documented in the acceptance docstring and the runbook (a planned main-view fault: error_recovered PASS and
   fps_director FAIL; the all-green run on a clean window).
5. Runbook: every child restarts with the supervisor (gap, new runs, voice model reload), STOP file kept, `webcam_only`
   first if a private page could show (the card is not a privacy cut), `status` / HLS health / main-view checks after,
   the same for the rollback, and a backup that a second deploy never overwrites.
6. Integration tests strengthened: all rows of every FIFO run checked; each run's tap (recorded per run) has
   `unique == max_seq - first_seq + 1` (no frame lost between its first and last), the rows' sum within one progress
   block of it, all taps' total <= the writer's written. New real-ffmpeg test of a stalled tap reader (8 s): ffmpeg's
   fifo muxer overflows, the recording keeps its pace on the same run, the window is marked invalid (overflows and gaps
   counted), `main_tap_idle` then `main_tap_flowing`. While doing this the parser was hardened: a part without EOI is
   `cut` (a frame the game discarded mid-write; never unique, its sequence a gap) and bytes before a part's SOI (a
   frame start drained by the director before ffmpeg took over) are `trimmed` instead of `noseq`.
7. Runbook "Go / no-go before the switch": a real v24 soak first, then the spec's step 6 acceptance.
