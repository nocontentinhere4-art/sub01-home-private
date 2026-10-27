# Agent fixes and focused live check (2026-10-27, Claude)

Continuation of Codex's handoff, which ended with the focused agent check NOT passing. Pod `505jw5ph3dt7ed`; runtime
source `/home/sub01-recovery-stage-20261026/runtime-source`. Each patch was applied by hunk, after a backup in
`/home/sub01-review-20261027/`.

## Result

`owner-agent-focused-20261027-r2/report-20261027T023754.909924Z` reports **PASS: 14 PASS, 1 SKIP (not required), 0 FAIL**
(`focused-report-20261027T0237.md`). It covers:

- C12: chat requests executed through the broker;
- C10a: kill switch, 0.21 s;
- C08: watchdog key release;
- C10b: operator resume, then an executed scroll;
- the audit, caps, freshness and no-lease checks.

The test lease was revoked at the end. STOP is absent and the agent is up, with no lease.

## Root causes and fixes

| Commit | Problem seen live | Fix |
|---|---|---|
| 848e90a | "jump to the bottom of the page" was acknowledged but nothing ran: `request_shape()` returned None because "jump" was not an action verb, so the line was treated as chat | Add `jump (back) to the top/bottom` to `ACTION_VERB`. Ordinary chat such as "jump to conclusions" still triggers no action and no refusal line |
| d686b04 | After a drill, `resume` removed STOP and the watchdog wrote STOP again within 2 s ("heartbeat missing for 2234 s"): its fresh grace only ran when it had tripped itself | Any STOP removal gives a one-shot fresh grace; the watchdog still fails closed afterwards. The watchdog was restarted with its original command line |
| f86e1f7 | "scroll up a little bit" was refused as leaving the desk: `strip_filler` turns it into "scroll up bit" | `SCROLL` accepts "a little/tiny (bit)" and a bare "bit"; "stand up" is still refused |

Kimi reviewed every diff before its commit; the raw Q/A is in `docs/streamer/kimi/agent-c12-20261027/`. The watchdog fix
was first blocked, then approved after the one-shot correction. One review got HTTP 429 and succeeded on the single
retry 10 minutes later.

## Operating notes, learned the hard way

- Run `streamer_agent_checks` with `/home/unreal/venv/bin/python`. The system `python3` breaks the chat ack.
- The checker prints its instructions to its stdout (`run.out`), not to `checks.log`.
- Revoke any earlier test lease (`DELETE /lease`) first: phase 1 requires no active lease.
- The test channel (127.0.0.1) refuses duplicate chat on purpose. Use new probe phrases on every rerun, or C12/C10b fail
  with "got site".
- Resume order:
  1. `streamer_up.py resume`;
  2. wait until port 8836 listens (about 3-50 s);
  3. settle about 8 s;
  4. `POST /lease`.

## Still open (from the handoff plan)

1. Real chat from the public site: a relevant spoken reply, and opening YouTube/Twitter on the Vagon PC. Needs an active
   lease.
2. Simple visual check (webcam and camera 2 frames, Kimi then the owner), voice and head sync, main fps at least 55 stable.
3. The 30-minute acceptance recording and the 1-hour stability run.
4. Promote Codex's runtime-only fixes with a diff review (see the handoff, point 6).
