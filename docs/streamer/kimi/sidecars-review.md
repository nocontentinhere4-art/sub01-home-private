# Kimi code review (2026-10-24 ~16:00 UTC): supervised sidecars and the monitor feed's privacy gate

Question: `q-sidecars-review.txt` (830 s, 21253 prompt + 35625 completion tokens of which 34531
reasoning). Attached: the diff of `scripts/` (streamer_up.py, streamer_monitor_feed.py, streamer_hls_serve.py) and of
`docs/streamer/RUNBOOK.md`, after the design review (`sidecars-design.md`). Answer, verbatim:

**Verdict: hold commit.** One narrow capture race can violate the privacy guarantee; the acknowledgement contract also has a consecutive-cut hole. HLS and the supervisor changes look otherwise sound.

## High

1. **An old capture can emit frames after a close/reopen — `MonitorFeed._run_ffmpeg()`, immediately after `asyncio.wait()`.**  
   The abort decision checks only `self.private_now()`. If the gate closes and reopens before this task resumes—possible with `--resume-after 0`, or a sufficiently stalled loop—`private_now()` is false even though `closed` completed. If `chunk` is also done, its data goes through `reader.feed()` and `sink.offer()`. Those bytes came from the pre-close ffmpeg and can contain frames captured during the cut.

   **Fix:** make capture membership, rather than only current openness, decide whether data is usable. Snapshot the generation before spawning ffmpeg and abort on either generation change or close notification:
   ```python
   capture_gen = self.cut_gen
   ...
   closed_seen = closed is not None and closed.done()
   if self.private_now() or self.cut_gen != capture_gen or closed_seen:
       chunk.cancel()
       outcome = "private"
       break
   ```
   Discard that chunk and terminate the old process; do not merely check the reopened gate. Add a regression test that closes and reopens before the ffmpeg task is scheduled.

## Medium

1. **A new cut does not always require a new acknowledgement — `PrivacyGate.observe()`, `_gate_changed()`, and `showing()`.**  
   `cut_gen` and `neutral_ack` are reset only on an open→private transition. While another reason keeps the gate closed, this sequence is possible: cut A → clean layout line → cut B. `observe()` changes `cut_id` to B, but no `_gate_changed("privacy_on")` occurs. Until the next successful neutral delivery, `showing()` can remain `"neutral"` using A’s generation/acknowledgement. That contradicts “a new cut needs a new ack” and matters to the planned agent check.

   **Fix:** invalidate the acknowledgement and advance a generation whenever `LayoutWatch` starts a new cut, even if the gate never opened. At minimum, `showing()` should also require the acknowledgement’s `privacy_id` to match the current cut, though generation tracking is needed to distinguish cuts without valid IDs.

2. **Watcher failure is silent and is not reflected in health — `run()`’s `self._tasks`.**  
   The tasks are only cancelled/gathered during shutdown; exceptions are otherwise unobserved. One dead poller will normally produce `*_stale` and close the gate within about 2.5 seconds. **That stale-closed posture is privacy-acceptable**, but the feed can then remain degraded indefinitely with `/healthz` returning 200 because a neutral JPEG exists. There is also no recovery if the tick/poller combination is lost.

   **Fix:** add done callbacks or supervise the tasks; on unexpected exit, consume/log the exception, set `last_error`, fail health or stop the process so the supervisor restarts it.

3. **RUNBOOK puts the operator token in argv — “Monitor feed”, “By hand (tests only)”.**  
   `env SUB01_ADMIN_TOKEN=... python ...` contradicts “never put the token on a command line”: it can enter shell history and is briefly visible in `env`’s argv.

   **Fix:** use `--token-file "$T"` in the example; do not replace it with another expanded `env VAR="$(...)"` form.

## Low

1. **`neutral_frames` undercounts partial writes — `_deliver_neutral()`.**  
   A frame completed later through `FifoSink.flush()` gets an acknowledgement but never increments `neutral_frames`. Increment once in the final `if done:` whole-frame path instead of only around `offer()`.

2. **RUNBOOK mismatches:**
   - The command summary lists `showing: ...|"nothing"`; the implementation uses **`"pending"`**.
   - The start-timeout summary’s “others 45–60 s” omits **Xvfb’s 20 s**.
   - Closing does not synchronously stop ffmpeg; it synchronously drops/offs neutral output, then asynchronously terminates ffmpeg. Also, a connecting reader gets neutral on a subsequent delivery/retry, not strictly “at once”. Adjust these claims to avoid implying stronger timing guarantees.

## Checked clean

- Apart from finding High-1, the chunk-processing loop contains no await, so a watcher cannot interleave a close with its offers. `drop_pending()` prevents an unwritten screen tail from being appended after close. Whole frames or prefixes already in the OS pipe can still precede neutral data—the explicitly documented residual FIFO risk.
- No additional stale/error opening path found: opening requires fresh, clean answers from both sources. Initial layout-absent/no-cut is the intentional documented exception.
- **Supervisor/HLS: none.** Existing-service relative stop order and adoption needles are unchanged; valid-token requests are unchanged, and tokenless requests now correctly omit the header. Overall `status` intentionally also depends on the two new services.

## What was applied

- **High-1 (a capture outliving a close/reopen): fixed.** The reviewed diff lacked it; right after sending it I had added
  the cut-generation binding: `_run_ffmpeg` snapshots `cut_gen` before spawning ffmpeg and every decision uses
  `blocked()` (gate closed now, or `cut_gen` changed since launch); Kimi's `closed.done()` check after `asyncio.wait`
  was added as well. Regression test (real lavfi ffmpeg, `--resume-after 0`): close and reopen in the same step while
  capturing -> the capture ends and a new ffmpeg starts (`restarts` 2, `cut_gen` 2).
- **Medium-1 (a new cut while already closed kept the old ack): fixed.** `PrivacyGate.observe` fires `cut_renewed` when a
  layout privacy line starts a new cut (the previous layout reason was not a cut, or another `privacy_id`) while the
  gate was and stays closed; the feed advances `cut_gen`, clears the ack and delivers a neutral frame at once (row
  `cut_renewed`). Test: cut A -> acked with pA; A ends; cut B without an id while the pipe is full -> `pending`, then a
  new ack.
- **Medium-2 (silent watcher death): fixed.** Each watcher task has a done callback: an unexpected end retrieves the
  exception, sets `last_error` and `watcher_failed`, holds the gate closed (`watcher_failed`; neutral frames go on),
  makes `/healthz` answer 503 so the supervisor restarts the feed, and logs a `watcher_failed` row. Test with a runner
  watcher that raises.
- **Medium-3 (token on a RUNBOOK command line): fixed** (`--token-file $T`).
- **Low-1:** `neutral_frames` counts whole neutral frames when they complete (also through `flush`). **Low-2:** RUNBOOK
  says `pending`, lists Xvfb's 20 s, and words the close as "offered" / "told to stop" with the 0.05 s retry and the
  0.5 s delivery to a new reader.

## Follow-up review of the fixes

Question: `q-sidecars-review2.txt` (367 s after one 429 retry, 3040 prompt + 16204 completion
tokens of which 15781 reasoning). Attached: the delta of the monitor feed since the reviewed diff. Answer, verbatim:

**High-1 — fixed.** The monotonic `cut_gen` snapshot closes the close/reopen ABA hole; `closed.done()` covers the completed-waiter case, and the read/discard/write paths now use `blocked()`. The regression test exercises the important case.

**Medium-1 — fixed.** Renewal requires a genuinely new layout cut, clears the old acknowledgement, and repeated/ending lines do not renew it. I accept the pending-neutral-tail design: while private, the pending bytes must be neutral, and the new acknowledgement is created only after the renewal was observed and frame completion. Thus it is a **completion-based** acknowledgement, not proof that every byte postdates renewal. Add a focused pre-existing-tail renewal test. Also soften the stale comment “an old write never acks a new cut,” which is now literally too absolute.

**Medium-2 — fixed for exception and unexpected-return deaths.** The exception is retrieved, failure is latched and logged, the gate is held closed, and `ok()` makes health fail. One residual assumption: `task.cancelled()` is ignored even when `_stopping` is false. That is safe if cancellation is exclusively shutdown-after-`_stopping`; otherwise, non-shutdown cancellation remains a silent-death path and should enter `watcher_failed` too.

**Medium-3 — fixed as reported.** The RUNBOOK is not in this delta, so I cannot independently inspect it. Prefer `--token-file "$T"`; the token file should be operator-only, e.g. mode `0600`.

**Lows — fixed as reported.** `neutral_frames` now counts completed whole frames, including completion through `flush()`, without double-counting partial offers. The other RUNBOOK wording is not verifiable from the attached monitor-only diff.

**New issues:** no new capture/privacy blocker found. Only the cancellation assumption and acknowledgement-wording nit above. I am accepting the reported **162/162** test result, not claiming an independent run.

commit: yes

## What was applied from the follow-up

- A focused test for a renewal over a pending neutral tail: the renewal leaves `showing: pending` and no ack; the ack for
  the new cut comes only when that frame's last byte is in (counted once).
- The comment and the RUNBOOK now call the ack completion based (no longer "an old write never acks a new cut").
- A watcher cancelled while the feed is not stopping is a failure too (`watcher_failed`, error `CancelledError`);
  `run()` sets the stopping flag before it cancels the watchers, so a normal stop logs no failure (tests for both).
- RUNBOOK: `--token-file "$T"` quoted, the token file 0600 uid 1001.
- Kimi's verdict after the fixes: "commit: yes". 164 tests pass in the three suites (44 supervisor, 24 monitor feed,
  96 director).
