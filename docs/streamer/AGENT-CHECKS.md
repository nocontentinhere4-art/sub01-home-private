# Plan step 5: the agent's safety controls, checked (2026-10-24)

HANDOFF.md plan step 5 requires these controls before any chat-driven or unattended run. This page maps each one to the
code that implements it, the tests that prove it and its status, lists what was missing and how it was fixed (every fix
designed and reviewed with Kimi: `kimi/agent-checks-design.md`, `kimi/agent-checks-design2.md`,
`kimi/agent-checks-review.md`), and says how to run the live checks once the owner has logged in to the PC and armed it.

**Status meaning.** PASS = implemented and proven by unit tests (no network, fakes, real code paths). The guard-rail
agent has **never run live**: the pod's source equals this branch, but the agent has been held down by the STOP file
since 2026-10-23 23:12 UTC (its audit rows on the pod are from the earlier version, without decision ids or frame
hashes). Live evidence comes from `scripts/streamer_agent_checks.py` (below), which must pass with no required SKIP
before step 5 is done.

## The controls

| # | Control | Code (`file:function`) | Tests (`tests/...::test`) | Status |
|---|---|---|---|---|
| 1 | Claude primary, Kimi fallback | `streamer_agent.py`: `make_provider`, `resolve_fallback`, `Agent.decide`, `Agent.switch_provider`, `Agent.maybe_return_to_primary` | `test_streamer_agent.py::test_primary_error_switches_to_the_fallback_at_once_and_the_primary_returns_after_the_window`, `::test_both_providers_failing_is_quiet_mode_and_either_one_recovering_leaves_it`, `::test_provider_flags_env_and_the_default_fallback_resolution`, `::test_agent_builds_the_chain_from_the_key_files` | PASS |
| 2 | Kimi in shadow on every decision, same frame; compared on latency, JSON validity, click-in-target, cost per correct action | `streamer_agent.py`: `Agent.fire_shadow`, `shadow_call`, `shadow_log`, `shadow_skip`, `cancel_shadows`, `reconcile_shadow`, `think` (primary tokens and cost in `_bind`), `decision_row`; `scripts/streamer_shadow_report.py`: `report`, `side_stats` | `test_streamer_agent.py::test_shadow_gets_the_same_request_concurrently_never_blocks_and_is_logged_next_to_the_primary`, `::test_shadow_is_skipped_not_queued_and_ends_at_its_own_timeout`, `::test_review_on_the_pc_the_shadow_waits_for_an_explicit_not_private_and_never_sees_a_private_frame`, `::test_checks_every_decision_gets_one_shadow_row_or_one_skip_row_across_a_stop_and_a_hard_kill`, `::test_checks_the_primary_cost_is_joined_to_its_decision_and_to_its_shadow_row`, `::test_checks_a_short_write_a_wide_mode_and_a_rotation_before_a_restart`; `test_streamer_shadow_report.py` (4 tests, two runs with the same decision ids among them) | PASS after fix (was PARTIAL) |
| 3 | Deny-by-default action broker | `streamer_agent.py`: `Agent.act`, `payload_problem`, `broker_check`, `final_check`, `refused_outcome` | `test_streamer_agent.py::test_checks_the_broker_refuses_a_bad_payload_from_every_source_before_anything_is_sent` (16 payloads x 4 sources), `::test_checks_the_broker_keeps_the_chromium_vocabulary_and_the_alt_f4_of_the_stop_game_routine_only`, `::test_review_a_timed_out_login_submission_holds_and_a_lease_lapsing_mid_check_stops_the_dispatch` | PASS after fix (was PARTIAL) |
| 4 | Each decision bound to its frame id; freshness re-check before dispatch | `streamer_agent.py`: `Agent.frame_ref`, `build_request`, `think`, `act`, `freshness`, `final_check` (age at dispatch), `dispatch` (`action` row: ids, hashes, `age_s`, `frame_age_s`) | `test_streamer_agent.py::test_a_stale_decision_frame_is_refused_before_dispatch_and_a_fresh_one_goes_through`, `::test_pc_dispatch_refuses_a_changed_click_target_a_black_frame_and_a_disconnected_pc`, `::test_audit_rows_bind_decisions_to_frames_with_raw_json_and_a_typed_password_never_leaves_the_runner`, `::test_checks_an_input_whose_verified_frame_is_older_than_fresh_s_at_dispatch_is_refused` | PASS (dispatch-time age added) |
| 5 | Caps: 3 actions/decision, 20/min, stop after 3 consecutive failures | `streamer_agent.py`: `broker_check`, `final_check`, `note_dispatch`, `actions_last_minute`, `note_result`, `hold`; `scripts/streamer_watchdog.py`: `Watchdog.actions_last_minute` (independent count) | `test_streamer_agent.py::test_caps_per_decision_and_per_minute_are_enforced_in_the_broker`, `::test_three_failures_in_a_row_hold_the_agent_until_resume_and_a_probation`, `::test_watchdog_trips_when_actions_exceed_the_cap_counting_agent_rows_and_runner_receipts` | PASS |
| 6 | 60-minute lease, manual re-arm | `streamer_agent.py`: `arm_lease`, `check_lease`, `lease_active`, `hands_off_reason`, `make_app` (`POST/DELETE /lease`), `enter_pause` (a STOP revokes it) | `test_streamer_agent.py::test_a_lease_is_required_for_desktop_actions_and_lapses_after_its_minutes`, `::test_checks_a_stop_ends_the_routine_and_the_request_revokes_the_lease_and_only_a_new_lease_acts` | PASS |
| 7 | A frozen or black stream means stop | `streamer_agent.py`: `check_stream`, `latch_frozen`, `freshness` (black frame), `check_probation`, `resume_latches` | `test_streamer_agent.py::test_pc_frozen_or_black_stream_stops_acting_releases_keys_and_needs_resume` | PASS (remote PC; the agent acts only there) |
| 8 | Independent watchdog that releases held keys | `scripts/streamer_watchdog.py`: `Watchdog.check`, `trip`, `on_stop`, `release`, `write_state` | `test_streamer_agent.py::test_watchdog_trips_on_a_missing_heartbeat_releases_keys_and_never_trips_twice`, `::test_review_the_watchdog_retries_a_stop_it_could_not_write_ignores_waits_and_follows_rotation`, `::test_review2_the_watchdog_confirms_a_release_only_by_the_runners_view_and_keeps_retrying`, `::test_checks_the_watchdog_releases_keys_on_every_stop_it_did_not_write_and_keeps_a_heartbeat`, `::test_checks_the_watchdog_keeps_retrying_its_own_trips_release_after_stop_is_removed` | PASS after fix (was PARTIAL); live: last release unconfirmed (see "Pod state") |
| 9 | Append-only audit (frame hashes, raw JSON, actions) | `streamer_agent.py`: `Agent.log` (`run` id, 0600, short write = failure), `rotate_events`, `audit_failed`, `recover_audit`, `decision_row`, `raw_for_log`, `scrub`, `dispatch` (no input without its `action` row) | `test_streamer_agent.py::test_audit_rows_bind_decisions_to_frames_with_raw_json_and_a_typed_password_never_leaves_the_runner`, `::test_review3_a_credential_in_any_json_escaping_of_the_raw_answer_never_reaches_the_audit`, `::test_checks_rotation_never_overwrites_an_older_audit_and_loses_no_row`, `::test_checks_an_audit_that_cannot_be_written_stops_the_hands_until_a_synced_recovery`, `::test_checks_no_input_is_sent_when_only_its_own_action_row_cannot_be_written`, `::test_checks_a_short_write_a_wide_mode_and_a_rotation_before_a_restart` | PASS after fix (was PARTIAL) |
| 10 | Kill switch: STOP halts actions and voice within a second; resume works | `streamer_agent.py`: `stop_watch`, `check_stop`, `enter_pause`, `leave_pause`, `guard`, `speak_next`; `scripts/voice_server.py` (STOP cuts and refuses speech); `scripts/streamer_up.py`: `do_kill`, `cmd_resume`, the agent held down while STOP exists | `test_streamer_agent.py::test_stop_file_stops_acting_and_speaking_but_keeps_observing`, `::test_stop_during_a_model_call_cancels_it`, `::test_kill_switch_works_within_one_second_in_the_running_agent`, `::test_status_server_endpoints_and_pause_resume`, `::test_checks_a_stop_ends_the_routine_and_the_request_revokes_the_lease_and_only_a_new_lease_acts`; `test_streamer_up.py::test_kill_writes_stop_cuts_speech_and_takes_only_the_agent_down`, `::test_a_stop_file_keeps_the_agent_down_and_everything_else_up`; `test_voice_server.py::test_kill_file_cuts_speech_and_refuses_new` | PASS after fix (was PARTIAL) |
| 11a | Payments and age-restricted content blocked | `streamer_agent.py`: `blocked_classes`, `model_url_problem`, `clean_action`, `clean_pc_action`, `pc_type_problem`, `parse_request` (`R_PAY`, `R_ADULT`), `ChatGate.classify`, `payload_problem`; `chat.py`: `check`/`blocked`; `scripts/streamer_desktop.py`: `action_policy`, `page_verdict` | `test_streamer_agent.py::test_logins_are_his_own_to_use_by_flag_while_chat_keeps_every_block`, `::test_pc_guard_rails_refuse_each_class_in_code`, `::test_pc_chat_policy_purchases_refused_games_by_flag_and_chromium_untouched`, `::test_parse_request_refused_classes_with_their_reason`, `::test_checks_the_broker_refuses_a_bad_payload_from_every_source_before_anything_is_sent` | PASS |
| 11b | Chat viewers cannot direct credential or account changes | `streamer_agent.py`: `parse_request` (`R_CREDS`, `R_ACCOUNT`, `account_change`), `Agent.route_request`, `Agent.start_request`, `ChatGate.classify` (`CREDS`), `request_url_problem` | `test_streamer_agent.py::test_logins_are_his_own_to_use_by_flag_while_chat_keeps_every_block`, `::test_checks_a_viewer_never_directs_an_account_change_and_the_over_block_is_deliberate`, `::test_checks_an_account_change_from_chat_gets_the_fixed_line_and_never_reaches_the_model_or_the_pc`, `::test_checks_the_account_predicate_runs_again_when_a_request_is_routed_and_when_it_is_started` | PASS after fix (was PARTIAL) |
| 11c | Typed secrets never spoken, captioned or logged | `streamer_agent.py`: `register_secret`, `add_secret`, `enqueue` (secret filter; captions use the same queue), `scrub`/`scrub_text`, `raw_for_log`/`mask_decoded`, `public_action`, `refused_outcome` (every refused `type` masked); `scripts/streamer_desktop.py`: `Runner.act`/`_loggable` (every typed text masked, both modes) | `test_streamer_agent.py::test_audit_rows_bind_decisions_to_frames_with_raw_json_and_a_typed_password_never_leaves_the_runner`, `::test_review_a_credential_is_masked_from_the_moment_it_is_proposed_and_rows_keep_their_structure`, `::test_review2_a_short_credential_is_never_typed_and_every_registered_one_is_masked_even_escaped`, `::test_on_a_private_screen_any_typed_text_is_masked_from_the_decision_row_on`; `test_streamer_desktop_vagon.py::test_remote_typing_is_never_logged_and_state_reports_the_flag`, `::test_typed_text_is_never_in_the_runners_log_in_either_mode` | PASS after fix (was PARTIAL in chromium mode) |
| 11d | Installs only from official stores and vendor sites, never a viewer's link | `streamer_agent.py`: `install_request`, `source_ok`, `official_entries`, `Agent.model_url_problem`/`install_url_problem`, `clean_pc_action` (`chat_install`); `vagon_bridge.py`: `streamer_block` (G5 below) | `test_streamer_agent.py::test_installs_are_his_own_to_choose_from_official_sources_by_flag`, `::test_a_viewer_install_request_goes_to_the_official_page_and_his_navigation_stays_there`, `::test_review_a_viewer_install_types_no_command_and_its_landing_page_must_stay_official`, `::test_review2_curated_github_sources_are_release_paths_only` | PASS |
| 11e | Spam and secret requests filtered | `chat.py`: `check` (1 message/10 s per viewer, 30/10 s global, dedupe, blocklist); `streamer_agent.py`: `ChatGate.classify` (`spam_reason`, duplicates 180 s, more than 4 per 30 s per nick, `CREDS`/`INJECT`), `Agent.refusal_line` | `test_streamer_agent.py::test_chat_gate_spam_duplicates_and_classes`, `::test_refusals_come_from_code_and_the_model_never_opens_a_host_from_chat`, `::test_refusals_alone_need_no_model_call` | PASS |
| 12 | (found) The backend's Vagon link bridge: a second chat-to-PC path outside the agent | `live_server.py`: `Live.handle_chat`; `vagon_bridge.py`: `streamer_block`, `submit_link`, `_open`; `streamer.py`: `link_bridge_state` | `test_streamer_mode.py::test_streamer_mode_never_sends_a_viewer_link_to_the_pc_bridge_and_the_agent_still_gets_it`, `::test_a_link_queued_before_the_streamer_mode_or_a_stop_is_dropped_before_any_vagon_call` | FIXED in code; **live blocker** until the backend runs with the bridge disabled |

The live-check runner itself: `tests/test_streamer_agent_checks.py` (30 tests: refusal without flags, every precondition,
a correct agent passes, broken agents fail, the drill, aborts including Ctrl+C and an error after the lease, an agent
that stops answering is no proof, receipts matched one to one, high-water marks across rotations, audit-only, the
probes against the real chat policy, GET only and never removing STOP). The fake runner logs its receipts through the
real `streamer_desktop.validate_action`/`_loggable`, so receipts differ from the agent's rows as they do live.

## What was missing and what changed (minimal fixes, each designed and reviewed with Kimi)

- **F1 broker (control 3).** The payload was validated only upstream. `payload_problem` is now the broker's first rule,
  at `act()` entry and again in `final_check`: only a dispatchable kind of the current desktop, the agent's URL rules
  on a navigation (money, age-restricted, account changes, the owner's consoles never), the mode's key rules (Alt+F4
  only for the `stop_game` routine at its `stop_confirm` stage), no card number, IBAN or (PC) purchase in typed text.
  A refused `type` is always masked in its row.
- **F2 account changes (11b).** "open steam settings and change the account name" was executed as `launch_game`, "log
  out of steam" reached the model. `R_ACCOUNT` / `LOGOUT_REQ` / `account_change` refuse them as `credentials` at parse,
  route and start. Accepted over-blocking (Kimi): "search for how to log out of gmail", "did you update your profile?".
- **F3 watchdog (8).** It released keys only on its own trips. It now releases them on every STOP it did not write
  (also one already there at its start), once per STOP (identity: device, inode, mtime, size), confirmed and retried
  like a trip (`stop_seen` rows), and writes its heartbeat `watchdog.state.json` at every check.
- **F4 / G2 audit (9).** Rotation replaced `events.1.jsonl` (history lost). It is now an exclusive hard link to a unique
  name (`events.<UTC microseconds>Z-<pid>[-n].jsonl`), the live file recreated exclusively (0600) and the directory
  synced. The live file is created 0600, and an older one the agent owns is narrowed to 0600 at the next append (a
  rotated file is a hard link of it, so it shares that mode; a file another user owns is left as it is). Rows carry
  the process `run` id (decision ids restart per run). A failed or short append latches `audit_degraded` (hands off);
  `POST /resume` clears it only after a synced `audit_recovered` row, else 503. `dispatch` sends nothing when its own
  `action` row could not be written (refused, the latch set).
- **F5 / G1 kill switch (10, 6).** A STOP now ends the routine and the request in flight (`why: paused`), revokes the
  lease in memory before any audit I/O, and leaving the pause starts the probation (two fresh, usable, non-private looks
  2 s apart). After a STOP only a new lease acts.
- **F6 / G4 shadow (2).** The primary's tokens and cost are in its `decision` row and the `shadow_decision` row; every
  decision gets exactly one `shadow_decision` or `shadow_skipped` row (skips, STOP/shutdown cancellations, and at start
  the decisions a hard kill left unaccounted, read from the last 2 MB of the live file and, when it is shorter, the
  newest rotated file); `scripts/streamer_shadow_report.py` scores the trial by (run, decision id) (latency, JSON
  validity, click-in-target and correctness from human labels, a labelled click without a readable point a miss, cost
  per correct action: null without labels).
  An input whose verified frame is older than `fresh_s` at dispatch is refused (`stale_refused`).
- **F7 typed text (11c).** The desktop runner logged typed text in chromium mode; it now masks every typed text.
- **G5 link bridge (12).** `live_server.handle_chat` sent a viewer's link to `vagon_bridge.submit_link` (the Vagon API
  opens it on the PC and may start the billed machine), outside the broker, lease and STOP. In streamer mode (active or
  not) and while STOP exists no viewer link reaches the bridge: checked at the call site, at submission and in the
  worker right before any Vagon API call. `GET /api/home/streamer` reports `link_bridge {enabled, blocked}`.

## Live checks: `scripts/streamer_agent_checks.py`

For later: the owner has logged in at the operator console and armed one start himself; the operator has deployed this
branch's files (agent, watchdog, desktop runner, backend modules), restarted the backend **with the Vagon bridge
variables unset**, restarted the watchdog, removed STOP (`streamer_up.py resume`) and has **not** armed a lease yet.
As the service user on the pod:

```
S=/home/unreal/.sub01-private/latest-source-20261023
runuser -u unreal -- /home/unreal/venv/bin/python $S/scripts/streamer_agent_checks.py --audit-only
runuser -u unreal -- /home/unreal/venv/bin/python $S/scripts/streamer_agent_checks.py \
    --owner-logged-in --pc-armed --send-chat --stop-drill
```

- Without `--audit-only` or all three acknowledgements it refuses and does nothing (exit 2). It never removes STOP,
  never POSTs (no lease, no resume), never sends input to the PC; when something is missing it prints the operator's
  exact command (resume, lease, revoke, watchdog start, the owner's PC steps) and exits 2.
- Preconditions (GET and file reads): no STOP; agent healthy, no lease yet, not held/frozen/audit; no privacy screen;
  no typed credential known; `--no-allow-credentials` on the agent (Kimi; `--credentials-on-ok` overrides only that);
  the PC connected (agent and runner views); the watchdog's heartbeat fresh (<= 20 s), on the same runner, its last
  release confirmed; the backend's link bridge reported disabled.
- Phase 1 (no lease): inert refusal probes through the site's WebSocket, as viewers (purchase, login, account change,
  install from a file name, keys, spam, a crypto push; only reserved `.example` targets): each refused by code, and
  nothing dispatched during the whole phase (+5 s), by time and by the files' high-water marks (C11a/b/d/e, C14).
  The high-water marks follow every file by inode across both rotations (the agent's hard link, the runner's rename)
  and a writer still appending to a rotated file; evidence a removed or replaced file cut short is a FAIL.
- It prints the lease command and waits for the operator. Phase 2 (leased): "scroll down" and "page down" each executed
  as exactly one broker action matched by exactly one runner receipt of the same payload (C12). The runner logs what it
  received after validation (`frame_id` added, defaults filled, typed text masked), so rows and receipts are compared
  by payload signature (`payload_sig`), never as whole dicts.
- The audit since the start: frame binding and dispatch-time ages (C04), caps (C05b), shadow accounting (C02b), the
  fields, and the secrets a script can test for (the operator token, API-key-shaped strings, unmasked typed text) in
  the agent's and the runner's rows (C09; an arbitrary secret cannot be proven absent), every runner receipt matched to
  its own agent dispatch, one to one, by payload and time (C13).
- `--stop-drill`: writes STOP, requires the agent paused or down and the voice `killed` and silent within 1 s, no action
  after it (C10a), the watchdog's `stop_seen` release confirmed and the runner's own view released (C08); prints the
  resume and lease commands and waits; one benign request after the operator's resume (C10b). STOP stays on any
  timeout or abort.
- Any abnormal end once the lease was asked for (an abort, Ctrl+C, an error) writes STOP and must prove within 5 s that
  the lease ended (P02): the agent's state paused without a lease, or its own `lease_revoked`/STOP `pause` row. An
  agent that no longer answers is no proof (FAIL, with the status command to check). Ctrl+C exits 130.
- Before every probe and after every wait it re-checks (privacy, credentials, STOP, watchdog) and aborts (P01).
- Report: `<streamer-dir>/agent-checks/report-<UTC to the microsecond>.json` and `.md` (0600, created exclusively).
  Exit 0 only when every required check passed; a required SKIP is incomplete (exit 1). The drill is required unless
  `--smoke`.

Shadow trial (the 30-minute comparison before any promotion): `scripts/streamer_shadow_report.py --streamer-dir ...
--since-min 30 [--labels labels.jsonl] [--json]`; decisions are keyed by (run, decision id); labels are written by a
person from the logged frames (`{"run", "decision_id", "who": "primary"|"shadow", "correct", "target_box"}`; a label
without `run` is used only when one run of the window has that id, otherwise reported as ambiguous).

## Pod state observed (read-only, 2026-10-24 15:45-16:05 UTC)

- `/tmp/sub01-share/MEASURING` absent during the reads. Source `latest-source-20261023` identical to this branch's
  parent commit (sha256 of the six files). Root disk 8.5 GB free.
- STOP present since 10:40 UTC, written by the watchdog: "heartbeat missing for 41261 s" (the agent had been down since
  23:12). The trip's key release went to the retired runner 8832 (HTTP none, not confirmed, ALERTs until that watchdog
  stopped). The watchdog running since 11:48 watches 8838; it is the earlier code (no `stop_seen`, no heartbeat file).
- Agent 8836: down (held by the supervisor while STOP exists). Runners 8838 and 8832 and the director answer
  `/healthz`. The agent's audit rows on the pod predate the guard-rail version.
- The backend's environment could not be read (permission denied), so the Vagon bridge's state is unknown; its launcher
  sets none of the bridge variables.

## Limits (declared)

- Latches (held, frozen, audit) live in memory: `kill` + `resume` restarts the agent without them, but a restarted
  agent has no lease, so the operator's explicit re-arm is still needed.
- A watchdog on the same pod cannot survive the pod; pixels cannot verify UAC or installer identity (earlier reviews).
- The chat refusals are code patterns, not a security boundary (Kimi): the first chat run stays supervised, with
  credentials off and inert probes.
- Frame times are the agent's receive times; the runner gives no capture timestamp.
- Outside streamer mode the bridge keeps its behaviour, including starting the machine for a viewer's link (Kimi:
  viewer-originated jobs should never start machines): an owner decision, reported.

## Kimi review

- Design (`kimi/agent-checks-design.md`): status table confirmed with corrections (8 is a live FAIL until the release is
  confirmed; 10 PARTIAL until F5); F1-F7 kept with changes (all applied: payload check at entry and in `final_check`,
  Alt+F4 tied to the routine, unique exclusive rotation names, `audit_degraded`, STOP identity with size and startup
  STOP, canary tests in both modes, zero-or-null cost metrics); the runner: inert probes, no dispatch in a refused
  window, 100 % shadow accounting, dispatch-time ages, receipts cross-matched, required SKIP is a failure.
- Follow-up (`kimi/agent-checks-design2.md`): G1 kept (lease revoked before audit I/O; non-private probation looks);
  G2 changed (exclusive recreation, directory fsync, synced `audit_recovered`, 503); G3 changed (phase 1 global zero
  with high-water marks, exactly one action and receipt per benign probe, revalidation before every probe and after the
  wait, abort revokes the test lease, drill required unless smoke); G4 changed (no STOP exclusion, cancellation and
  startup reconciliation skips, XOR, no duplicates or orphans, `fresh_s` enforced at dispatch); G5 changed (blocked in
  streamer mode at every call site and before every Vagon call; queued jobs rechecked). Not applied: a cross-process
  lock for `events.jsonl` (the director and the supervisor append without one; every writer appends, only the agent
  rotates); viewer-originated machine starts outside streamer mode (reported above).
- Pre-commit review of the whole diff (`kimi/agent-checks-review.md`): "do not commit as-is", five blockers, all fixed
  with regression tests: (1) `dispatch` ignored a failed `action` append and a short write counted as success: no
  input without its row now, short write = failure; (2) the watchdog's own trip lost its pending release when STOP was
  removed: kept and retried; (3) the runner's abort accepted an agent that stopped answering as proof and only handled
  `Aborted`: P02 needs positive proof, and every abnormal end after the lease was asked for writes STOP; (4) the scorer
  joined decisions by id alone across restarts: keyed by (run, decision id), labels carry `run`, ambiguous legacy
  labels left out and reported; (5) C13 compared counts: receipts matched one to one by payload and time. Should-fix,
  all applied: high-water marks across rotations (or FAIL), 0600 for an older audit the agent owns, reconciliation
  into the newest rotated file, an unscorable labelled click is a miss. Nits applied: C09 named for what it tests,
  report names to the microsecond, created exclusively. Found while fixing (5): the runner's receipts carry `frame_id`
  and normalised fields, so C12's whole-dict comparison would have failed every live run; both checks now compare
  payload signatures, and the fake runner logs through the real runner's code.
- Follow-up review of the fix diff (same file): B1-B5 all RESOLVED, no new blocking safety hole; one report-only count
  (C13's "dispatches without a receipt" could be hidden by a matched pre-window dispatch) fixed with a test. Verdict:
  the commit may proceed. This is still not the live step-5 certification: the live run and the disabled-bridge
  deployment remain.
