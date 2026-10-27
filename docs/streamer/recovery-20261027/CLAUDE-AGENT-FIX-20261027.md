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

## Real chat from the public site: PASS (02:42-02:44 UTC)

Both messages went through the public relay (`POST /chat`, Origin subzerone.live), with a 15-minute lease armed and
revoked afterwards. Both returned `received`.

- **"hey, what are you reading right now?"** He answered on topic, in the `say [direct]` log line: "A Scientific
  American piece on how octopus arms may talk to each other..."
- **"can you open youtube please?"** He said "I'll open it", and YouTube opened on the Vagon PC: "YouTube's open. The
  home feed is mostly big-budget challenge videos...". Screenshot: `chat-test-youtube-20261027T0243.jpg`.

The log shows that he spoke. Audio playback on the stream was not measured here; the 30-minute recording covers it.

## Still open (from the handoff plan)

1. Simple visual check (webcam and camera 2 frames, Kimi then the owner), voice and head sync, main fps at least 55 stable.
2. The 30-minute acceptance recording and the 1-hour stability run.
3. Promote Codex's runtime-only fixes with a diff review (see the handoff, point 6).

## Later on 2026-10-27

**Faster replies (deployed).** Commit f8c1eae: a direct question went from about 14 s to about 9.4 s, measured from
the site to the start of the voice. Kimi approved.

**Lease.** A 60-minute lease was armed at 02:49:24 UTC and expires around 03:49 UTC. After that SUB-01 again answers
"my hands are off the desk" to requests. That is by design (manual re-arm); the owner decides whether it becomes
automatic.

## NEXT: owner requests not yet implemented (02:50-03:00 UTC)

1. **"Fai sì che qualsiasi link sia apribile ... può fare tutto come una persona reale."**
   - Agent side, `streamer_agent.py` `request_url_problem()`: refuse a viewer link only for the classes in a new
     `VIEWER_LINK_BLOCKED` tuple instead of every `BLOCKED_HOST` / `BLOCKED_PATH` class.
   - The owner lifts `money`, `gambling`, `torrent`, `login`, `file` and `account_change` for viewers.
   - Recommendation to put to the owner: keep `adult` blocked, because the PC screen is public on subzerone.live.
   - Update the policy tests that encode the old rule:
     - `test_parse_request_refused_classes_with_their_reason` (paypal, cart);
     - `test_a_viewer_site_redirecting_to_a_login_page_is_undone_and_said`;
     - `test_logins_are_his_own_to_use_by_flag_while_chat_keeps_every_block`.
   - Kimi reviews the diff. Patch the runtime source `/home/sub01-recovery-stage-20261026/runtime-source`, then
     restart the agent with `streamer_up.py kill` and `resume`; port 8836 is up in about 3-50 s. Re-arm the lease.
2. **Chat filter: "fomo family open it" was rejected** ("no trading or get-rich talk").
   - Cause: `lexicon.py` `HYPE` contains `fomo(?: app)?`, from the owner's rule of 2026-10-09; `browse.py` `MONEY_HYPE`
     contains `fomo app`. The owner now says "rimuovi sto filtro".
   - Remove `fomo`, and with `links_open` do not judge the URL text itself with `HYPE` (`chat.check`). Keep insults,
     personal data and so on.
   - The chat filter runs in the BACKEND (run copy
     `/home/unreal/.sub01-private/owner-backend-runtime-20261027-r6/source`). The coordinator ends all its services
     if one child stops, so a restart means Codex's full r7 procedure (`restart_backend_r6.py` on his Mac):
     - new `--state-snapshot` from the stopped r6 state;
     - new run and state directories;
     - the expected memory count read from the stopped state.

     Do it while watching, not overnight.
   - Workaround that already works: "open fomofamily.com" passes the filter and opens the site.
3. **Desktop audio and soft chill background music on the stream** ("c'è troppo silenzio").
   - Today the director's audio is the K07 voice only.
   - Needed:
     - capture the Vagon Chrome tab audio on `:103` (PulseAudio monitor of the desktop runner's Chrome) as a second
       audio input of the director's FFmpeg;
     - mix in a quiet royalty-free lo-fi loop, ducked under the voice;
     - check the levels in a short recording before going live.
