# Plan step 5: pre-commit review of the safety-control diff

Pre-commit review of the whole plan-step-5 diff (code, runner, scorer, tests, control table), 2026-10-24. Attached files: r1-code.diff, r2-streamer_agent_checks.py, r3-streamer_shadow_report.py, r4-tests.diff, r5/r6 runner and scorer tests, r7-AGENT-CHECKS.md. What was applied from the answer is recorded at the end of this file and in AGENT-CHECKS.md.

## Question

```
Pre-commit review of the plan-step-5 diff (SUB-01 streamer agent safety controls). You designed it with me in two consultations (F1-F7 KEEP with changes; G1-G5). Attached:
  r1-code.diff: streamer_agent.py, scripts/streamer_watchdog.py, scripts/streamer_desktop.py, live_server.py, vagon_bridge.py, streamer.py;
  r2-streamer_agent_checks.py: the new live-check runner (whole file);
  r3-streamer_shadow_report.py: the new shadow trial scorer (whole file);
  r4-tests.diff: the new tests in test_streamer_agent.py, test_streamer_mode.py, test_streamer_desktop_vagon.py;
  r5/r6: the runner's and the scorer's tests (whole files);
  r7-AGENT-CHECKS.md: the control table and the claims.
Test results: all tests/test_streamer_*.py pass (779 before the last two small fixes; the full count is re-run before the commit); the other suites importing live_server/vagon_bridge pass except one failure that also fails on the untouched base commit (an audience-vote timing test) and one needing a Playwright browser that is not installed here.

What I applied from your answers, in short:
- F1: payload_problem at act() entry (before break_loop) and again in final_check; Alt+F4 only when source is "routine" AND self.pc.routine is stop_game at stage stop_confirm; every refused `type` row masked.
- F2: R_ACCOUNT, LOGOUT_REQ/LOGOUT_ANY, account_change(text) checked in parse_request, route_request and start_request (refused "credentials").
- F3: watchdog on_stop() for every STOP it did not write (also one present at its start), identity (dev, ino, mtime_ns, size), stop_seen rows, retry until confirmed (also after STOP is removed), watchdog.state.json heartbeat at every check.
- F4/G2: rotation by exclusive os.link to events.<UTC microseconds>Z-<pid>[-n].jsonl, unlink, exclusive recreation 0600, directory fsync; every row 0600 with the process `run` id; OSError -> audit_degraded latch (hands off "audit"); POST /resume -> recover_audit writes a synced audit_recovered row or answers 503. Not done: a cross-process lock (the director and supervisor append to the same file without one; only the agent rotates).
- F5/G1: enter_pause revokes the lease in memory before any audit I/O, cancels the step, ends routine/request (why paused), cancels shadows with skip rows; leave_pause starts the probation; probation looks must be non-private.
- F6/G4: primary tokens/cost in _bind, decision row and shadow row; shadow_skipped rows for every skip, STOP/shutdown cancellation ("cancelled"/"shutdown") and startup reconciliation ("lost_at_shutdown" with decision_run); final_check refuses an input whose verified frame is older than fresh_s at dispatch; action rows carry age_s and frame_age_s; the scorer gives null (not zero) without labels.
- F7: the desktop runner masks every typed text in both modes; canary test in both modes, refused text included.
- G3 runner: two phases (phase 1 without a lease, zero agent actions and runner receipts by time AND by byte high-water marks, +5 s; phase 2 exactly one own action of a whitelisted key kind and exactly one payload-identical receipt per benign probe); revalidation before every probe and after the lease wait (fail closed); abort after the lease writes STOP and confirms the lease ended (P02) instead of POSTing (the runner never POSTs); drill required unless --smoke; required SKIP = exit 1; the link bridge must be reported disabled (GET /api/home/streamer link_bridge.enabled false).
- G5: live_server never calls vagon_submit_link while streamer mode is attached (active or not); vagon_bridge.streamer_block() refuses at submit_link and again in _open before any Vagon call (and after the wait for ready); GET /api/home/streamer reports link_bridge {enabled, blocked}. Not done: forbidding viewer-originated machine starts outside streamer mode (reported to the owner as a recommendation; the bridge cannot act at all in streamer mode).

Please review for correctness bugs, safety holes, and claims in AGENT-CHECKS.md that the code or tests do not support. Answer with: BLOCKERS (must fix before commit), SHOULD-FIX, NITS, each with file:function and a concrete fix; then say whether the commit may proceed once the blockers are fixed. At most 900 words.
```

## Answer (verbatim)

## BLOCKERS

- **`streamer_agent.py:Agent.dispatch` / `Agent.log` — an audit failure can still be followed by PC input.** `dispatch()` ignores the new Boolean result of `self.log("action", ...)`; if that append fails, `audit_degraded` is latched but `services.act(send)` is still called. Require the action row to be written before dispatch and return a refused outcome without calling `services.act` otherwise. Also check `os.write()`’s return value: a short write currently counts as success. Add a fault-injection test where only the dispatch-time append fails, and assert `world.acts == []`.

- **`scripts/streamer_watchdog.py:Watchdog.check` — STOP removal cancels an unconfirmed release for the watchdog’s own trip.** The first branch resets `release_pending=False` when `tripped_by` is set and STOP disappears. This bypasses the new retry-after-STOP-removal logic and can leave a key held. Preserve `release_pending` across that reset and retry independently of STOP presence. Test an own-trip release failure followed by STOP removal, through eventual confirmation.

- **`scripts/streamer_agent_checks.py:Run.emergency_stop` / `main` — lease termination is not fail-closed.** `status is None` is accepted as P02 PASS, although a GET timeout does not prove either process death or lease revocation. Require explicit paused/no-active-lease state, or independent proof that the process is down. Additionally, only `Aborted` is handled: `KeyboardInterrupt` or an unexpected `OSError` after leasing can exit without writing STOP. Cover every post-lease exit path with best-effort STOP/P02 handling and a nonzero exit.

- **`scripts/streamer_shadow_report.py:report` / `read_labels` — decision IDs are joined without `run`.** IDs restart at `d1`; a report spanning a restart collapses shadow rows, misjoins primary/shadow metrics, and makes labels ambiguous. Key decisions, shadows, skips, raws, and label lookups by `(run, decision_id)`, using `decision_run` where present. Add a run field to labels, with an explicit legacy/ambiguous-row policy, and test two runs containing the same ID.

- **`scripts/streamer_agent_checks.py:Run.audit_checks` (C13) — receipt counts do not prove receipt provenance.** One foreign receipt plus one legitimately missing receipt leaves counts equal and passes C13. Match every receipt to a distinct dispatch, preferably by propagating `action_id` into runner receipts; otherwise use conservative payload/time matching. Until then, C13’s “every runner receipt is an agent dispatch” claim is unsupported.

## SHOULD-FIX

- **`scripts/streamer_agent_checks.py:Audit.between` — byte evidence is incomplete across rotation.** After an inode change it reads only the current live file from offset zero, missing bytes in rotated files. Follow the inode/rotation chain, or fail C14 explicitly when rotation prevents complete high-water-mark evidence.

- **`streamer_agent.py:Agent.log` — 0600 is not ensured for an existing audit.** `os.open(..., 0600)` does not change an older file’s permissions. `fchmod` the opened live file, and address pre-existing rotated files, before claiming every row is 0600.

- **`streamer_agent.py:Agent.reconcile_shadow` — reconciliation examines only the last 2 MB of the live file.** Extend it to the relevant rotated history or qualify the “every decision/exactly one terminal row” claim in `AGENT-CHECKS.md`; the current test covers only one live-file tail row.

- **`scripts/streamer_shadow_report.py:side_stats` — unscorable labelled clicks disappear from the denominator.** A labelled click with no extractable point should be a conservative miss or an explicitly reported unscorable category, not silently excluded from `click_in_target_rate`.

## NITS

- **`Run.audit_checks` / `AGENT-CHECKS.md`:C09** checks the token, one key-like pattern, and masked `type` rows. Rename “no secret anywhere” to those precise checks; arbitrary secrets cannot be proven absent.
- **`Run.write_report`** uses second-resolution names with truncating opens. Use microseconds and exclusive creation to avoid overwriting simultaneous reports.

**Verdict:** do not commit as-is. The code commit may proceed once the blockers have fixes and regression tests and the full applicable suite is rerun. That still would not constitute live step-5 certification; the required live run and disabled-bridge deployment remain outstanding.

## Follow-up: the fixes reviewed (2026-10-24)

The diff from the reviewed version to the fixed one (`r8-fixes.diff`: agent, watchdog, runner, scorer and their tests) was sent with this question. Two earlier tries ran out of the output budget while reasoning (24000 tokens); this answer came with a larger budget.

### Question

```
Follow-up to your pre-commit review of the plan-step-5 diff (SUB-01 streamer agent safety controls). You said: do not commit as-is; five blockers; the commit may proceed once they are fixed with regression tests and the suite is re-run. Attached: fixes.diff, the diff from the version you reviewed to the current one (agent, watchdog, runner, scorer and their tests). All 788 tests in tests/test_streamer_*.py pass (779 before, 9 new).

What I did, per item:
B1 streamer_agent.py:Agent.dispatch/log: the `action` row is written right after note_dispatch (so it counts against the caps) and the secret registration, BEFORE any other side effect; if log() returns False, dispatch returns refused_outcome(("action_refused", "hands off: audit ...")) without calling services.act (log() latched audit_degraded). log() treats os.write() != len(data) as OSError("short write"). Test: only the dispatch-time append fails -> world.acts == [], verdict action_refused, counters["actions"] == 0, hands off "audit"; a short write latches.
B2 streamer_watchdog.py:Watchdog.check: removing STOP after the watchdog's own trip no longer resets release_pending; the existing elif branch retries it until confirmed. Test: own trip with an unconfirmed release, STOP removed, still retried, then confirmed.
B3 streamer_agent_checks.py:Run.emergency_stop/main: P02 PASS needs positive proof within 5 s: GET /state paused with no active lease, or the agent's own audit row since the STOP (`lease_revoked` why STOP, or a `pause` row whose why starts with "STOP"; enter_pause revokes the lease in memory before both rows). No answer is no proof (FAIL with the status command). main catches BaseException (Aborted, KeyboardInterrupt, OSError, bugs): P01 FAIL, and when a lease may be active (it was seen, OR wait_for_lease has printed the lease command: `lease_asked`), emergency_stop; the report is written; exit 130 for Ctrl+C, else 1. Writing STOP failing with OSError -> P02 FAIL with the kill command. A normal end after a lease prints the revoke command (the runner never POSTs).
B4 streamer_shadow_report.py: every join keyed by (decision_run or run, decision_id); labels may carry `run`; a label without run is used only when exactly one run in the window has that id, else counted as ambiguous (or unknown) and left out, reported in `labels_left_out`; `runs` reported. Test: two runs with the same ids, ambiguous/unknown labels, a reconciled skip from a later run.
B5 C13: each runner `act` receipt must match a distinct agent `action` row (greedy, receipts in time order) with the same payload signature and d.t - 1 s <= receipt.t <= d.t + 30 s; dispatches are read from 30 s before the window. payload_sig(action): kind plus the kind's fields as both logs carry them: scroll (direction, int amount, defaults down/600), key (key), click (mark, point as floats), type (mark, length from "[typed N chars]" or the text, submit default False), navigate (URL without query/fragment, lowercased, https:// added when missing), search (whitespace-normalised), wait (seconds). Test: one foreign receipt plus one undelivered dispatch -> FAIL.
Found while fixing: the real runner logs validate_action() output (frame_id added, amount int, submit default) so C12's whole-dict comparison would have failed every live run; C12 now also uses payload_sig, and the test fake logs receipts through the real streamer_desktop.validate_action/_loggable.
SHOULD-FIX: Audit.mark is now {inode: (name, size)} over the live and rotated files; between() reads every file of the second mark from the first mark's size of the same inode (0 if new), checks the inode on open, and returns (rows, complete); complete is False when a file of the first mark is gone or a name holds another inode; C14 FAILs on incomplete evidence. Test: agent hard-link rotation, a stale writer appending to the rotated file, runner rename rotation, then a removed file. Agent.log fchmods the live file to 0600 when its mode is wider and the agent's euid owns it (another owner's file is left alone, documented). reconcile_shadow reads on into the newest rotated file when the live file is shorter than the 2 MB tail. side_stats: a labelled click with no readable point is a miss, counted as clicks_unscorable.
NITS: C09 renamed to what it tests (operator token, API-key-shaped strings, unmasked typed text); reports named to the microsecond and created with O_EXCL (a "-n" suffix when taken).

Please check only: is each blocker resolved; did the fixes introduce a bug or a safety hole (for example in the dispatch reordering, the BaseException handling, the 30 s receipt window or payload_sig's normalisation); may the commit proceed. Answer with RESOLVED/NOT RESOLVED per item, NEW PROBLEMS (file:function, concrete fix) if any, and a one-line verdict. At most 500 words.
Budget: two earlier tries of this question ran out of the output budget while reasoning (24000 tokens); please keep the reasoning focused on the items above.
```

### Answer

**B1 — RESOLVED.** Dispatch is counted, secrets are registered, and the `action` row is appended before `services.act`. Append failure returns `action_refused` without desktop input; short writes latch the degraded-audit state. The regression covers the important side-effect ordering.

**B2 — RESOLVED.** Removing STOP no longer clears an unconfirmed `release_pending`; the existing retry path continues until release is confirmed.

**B3 — RESOLVED.** P02 now requires positive paused/no-lease state or a qualifying revocation/pause row; an unreachable agent and STOP-write failure both fail closed with operator commands. The `BaseException` path covers Ctrl+C and unexpected errors, performs the conditional emergency stop, writes the report, and returns the specified statuses.

**B4 — RESOLVED.** Decisions, shadows, skips, raws, and labels are resolved by `(run, decision_id)`, including `decision_run` reconciliation. Legacy labels are accepted only when unambiguous; exclusions and runs are reported. Missing click points are scored as specified.

**B5 — RESOLVED.** C13 implements distinct, greedy, time-ordered receipt matching with the stated 30-second look-back and payload signatures. C12 uses the same normalisation, avoiding the live-runner whole-dict mismatch.

**NEW PROBLEMS**
- **Non-blocking, report-only:** `scripts/streamer_agent_checks.py:Run.audit_checks` — “dispatches without a receipt” is wrong when look-back dispatches are matched. `used` may include pre-window rows, so `len(actions) - min(len(actions), len(used))` can report zero while a current-window dispatch is undelivered. Track matched current-window dispatches separately and compute the count from those; add a test combining one matched pre-window dispatch with one current undelivered dispatch. This does **not** affect foreign-receipt detection or C13’s PASS/FAIL result.

**Verdict: Commit may proceed on the supplied diff and reported green 788-test run; no new blocking safety hole found.**

## Applied

From the pre-commit review, all items (details in AGENT-CHECKS.md, "Kimi review"):

- B1 `Agent.dispatch` / `Agent.log`: the `action` row is written before any other side effect and before
  `services.act`; a failed append refuses the action (`action_refused`, hands off `audit`); a short write is a failed
  write. Tests: `test_checks_no_input_is_sent_when_only_its_own_action_row_cannot_be_written`,
  `test_checks_a_short_write_a_wide_mode_and_a_rotation_before_a_restart`.
- B2 `Watchdog.check`: removing STOP keeps an unconfirmed release pending; retried until confirmed. Test:
  `test_checks_the_watchdog_keeps_retrying_its_own_trips_release_after_stop_is_removed`.
- B3 `Run.emergency_stop` / `main`: P02 needs positive proof (paused without a lease, or the agent's own
  `lease_revoked`/STOP `pause` row); every abnormal end once the lease was asked for writes STOP; Ctrl+C exits 130.
  Tests: `test_an_agent_that_stops_answering_is_no_proof_that_the_lease_ended`,
  `test_ctrl_c_or_an_error_once_the_lease_was_asked_for_writes_stop_and_proves_the_lease_ended`.
- B4 `streamer_shadow_report.py`: keyed by (run, decision id); labels carry `run`; ambiguous legacy labels left out
  and reported. Test: `test_two_runs_with_the_same_decision_ids_are_kept_apart_and_legacy_labels_are_never_guessed`.
- B5 C13: receipts matched one to one to dispatches by payload signature and time; C12 uses the same signature (the
  runner's receipts carry `frame_id` and normalised fields). Test:
  `test_receipts_are_matched_one_to_one_to_dispatches_by_payload_not_by_counts`.
- Should-fix: high-water marks by inode across rotations, incomplete evidence fails C14
  (`test_high_water_marks_follow_both_rotations_and_a_stale_writer_and_flag_a_lost_file`); 0600 for an older audit
  the agent owns; reconciliation into the newest rotated file; an unscorable labelled click is a miss.
- Nits: C09 named for what it tests; report names to the microsecond, created exclusively.

From the follow-up: the "dispatches without a receipt" count now counts only this window's own unmatched dispatches
(a pre-window dispatch matched by a receipt inside the window no longer hides one); test added to
`test_receipts_are_matched_one_to_one_to_dispatches_by_payload_not_by_counts`. Verdict: the commit may proceed.
