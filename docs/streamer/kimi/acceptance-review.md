# Kimi review (2026-10-24): scripts/streamer_acceptance.py before commit

The whole module in one call (86 KB, 35k tokens in) came back empty: kimi-k3.1-pro stops at ~16k completion tokens
and spent them all reasoning. So the module was reviewed in four parts of ~20 KB with a pointed question each (the
questions are at the end), one call at a time; part 1 needed a second attempt for the same reason, part 2 was cut by
the limit in its fifth finding and got a follow-up (2b). Every finding below was applied unless marked otherwise; the
tests cover each one (61 tests at commit). A last check of the fixes (the diff from the reviewed version) found no
blocking issue (end of this file).

## Part 1: helpers, masking, source readers, ffprobe (15 053 tokens, 336 s)

> 1. **Medium — `mask()`**: secrets can still reach persisted evidence. For example, `client_secret=abc` and `refresh_token=abc` are unchanged: `\bsecret` / `\btoken` cannot match after `_`. URL userinfo also survives: `https://u:p@host/x?a=b` becomes `https://u:p@host/x?[query masked]`, retaining `p`. Additionally, the UPPER_SNAKE exemption can preserve any sufficiently long uppercase secret, not just a log tag. **Fix:** recursively redact sensitive dictionary keys, extend raw-line rules to names such as `client_secret`/`refresh_token` and non-Bearer authorization values, and mask URL userinfo before query masking. Restrict the tag exemption to `^SUB01_[A-Z0-9_]+$`. Add these exact regression cases.
>
> 2. **Medium — `read_hls()`**: `EXT-X-PROGRAM-DATE-TIME` is consumed by one segment. A valid playlist containing one PDT followed by several segments gives every subsequent segment `start=None`, making window-end/HLS spot-check dating dependent on optional repeated PDT tags. **Fix:** carry time forward: after dating a segment at `start`, set `next_start = start + extinf` when both are known; use an explicit newer PDT preferentially and invalidate carried time when duration is unknown.
>
> 3. **Medium — `ffprobe_count()`**: probe success and input stability are not established. `done.returncode` is ignored, so parseable partial JSON can be accepted despite ffprobe reporting an error. A successful probe of a still-growing fragmented MP4 is likewise only a snapshot, but its result is indistinguishable from a complete-file measurement. **Fix:** reject nonzero exits before parsing metrics; probe closed recordings where possible, otherwise compare size/mtime before and after and return an explicit `partial/changed` result that cannot support a pass or fail. The existing command is read-only and demux-only, and the 180-second timeout is present.
>
> 4. **Low — `to_unix()`**: numeric `NaN`/infinity, including numeric strings, is accepted; these values can later break sorting or `iso()`. **Fix:** require `math.isfinite()` for both numeric branches and otherwise return `None`.
>
> The specified UE UTC and ISO forms parse correctly, and the voice fallback correctly remains sticky until the next `listening on`.
>
> no blocking finding

Done: (1) mask() now catches any key name holding token/secret/password/api_key/authorization/cookie/credential
(refresh_token, client_secret, X-Admin-Token), Basic and Bearer values and URL userinfo; dict rows are scrubbed by key
at any depth before dumping (`scrub()`); the long-run exemption is limited to `SUB01_*` tags. (2) read_hls() carries
the program date-time forward (start + EXTINF) and drops it at a discontinuity. (3) ffprobe_count() rejects a nonzero
exit. (4) to_unix() rejects NaN and infinity.
Adapted: (3) a segment that grows while it is probed is flagged `growing` and noted in the report, but its count is
still used: a fragmented MP4 snapshot is a consistent packets/duration over the fragments written, and the window's
tail is always the open segment (rejecting it would make every "last 30 minutes" run inconclusive).

## Part 2: Sources, activity, chat (cut off by the output limit in finding 5)

> 1. **high — `eval_chat_executed`:** `ends` includes rows after `until` and is not matched per request. A post-window `chat_request_end(why="done")` can therefore supply a post-window `t1`, after which `bound_outcomes()` and `spoken()` supply post-window results/speech, producing PASS for a request incomplete within the assessed window. **Fix:** select the first end satisfying `req["_t"] <= end["_t"] <= until`; clamp outcome/speech searches to the window, apart from any explicitly documented, bounded grace period.
>
> 2. **high — `eval_activity`:** adjoining spans share a boundary: `a["end"] == b["start"]`, while both `ok` counts use inclusive comparisons. One successful `routine_end` at a browse→game transition can consequently “verify” both spans, allowing PASS without an independently verified browse result. **Fix:** use half-open spans `[start, end)` except for the final span, or use row order for equal timestamps, ensuring one row cannot increment both counters. Add this exact regression case.
>
> 3. **high — `eval_chat_refused`:** `acted` is forcibly empty for every `request_redirect` because of `not reason.startswith("redirect")`. Thus a redirect with an arbitrary bound `req-<seq>` action can still enter `good` and PASS despite the stated “no action bound to it” requirement. Conversely, non-redirect `acted` searches have no upper time bound, so post-window actions can FAIL this window. **Fix:** define redirect semantics explicitly: either exclude redirects from eligible policy refusals or permit only a specifically validated redirect action; otherwise apply the same bound-action check, bounded to the request/window.
>
> 4. **medium — `events_gap` / `absent`:** this does not implement “rows within 15 minutes of both ends.” An ancient first row satisfies the start check, and an arbitrarily late future row satisfies the end check. `absent()` can then return FAIL where coverage is actually unassessable and the result should be MISSING. **Fix:** require actual rows within `fresh` of each endpoint, e.g. `any(abs(t-since) <= fresh)` and `any(abs(t-until) <= fresh)`, retaining the empty/rotation diagnostics.
>
> 5. **medium — `inactive_intervals`:** `held` and `stream_frozen` share one `open_["held"]` slot. If they overlap, either `resume` or `resume_latches` closes both, although the other

Done: (1) chat_executed matches the first chat_request_end of the same seq inside [request, window end] (seq numbers
restart with the agent) and bounds outcomes and speech to the window. (2) Activity spans are half-open [start, end)
except the last: the routine_end that opens the game span no longer verifies the browse span. (3) request_redirect
rows are listed apart ("executed, then undone") and never counted as the refusal; the bound-action search runs from
the refusal to the window end or until the same seq is reused. (4) events_gap() needs rows within 15 minutes of each
window end. (5) held/resume and stream_frozen/resume_latches have separate slots.

## Part 2b: follow-up for the findings after 5 (11 213 tokens, 305 s)

> 6. **High — `eval_chat_executed()`:** an agent restart can still let an old request borrow the new run’s completion, outcomes, and speech. If the original request has no `chat_request_end`, the first same-`seq` end after restart becomes its `end`; `bound_outcomes()` and `spoken()` can then also consume the new request’s rows, producing a false PASS. **Fix:** establish a run/reuse boundary—the agent restart row or the next new same-`seq` chat/request—and cap the end, outcome, and speech searches before it. Report `no chat_request_end` when none exists within that boundary.
>
> 7. **High — `eval_activity()`:** `src.recorded(b["start"])` checks only one instant at the transition. Both spans can otherwise obtain their entire dwell and verification from logs while neither activity is meaningfully recorded, despite the failure text claiming “verified, recorded activity on both sides.” **Fix:** intersect each span’s active time with `src.air()` and require the configured recorded active dwell on both sides, while retaining the recorded-transition check; otherwise classify the pair as soft rather than strong.
>
> 8. **Medium — `eval_chat_refused()` and `eval_chat_executed()`:** recording is checked at the request/refusal timestamp, not when the qualifying speech is delivered. Recording can stop immediately after that row, with the spoken answer arriving later off air, yet refusal still passes through `line and src.recorded(row["_t"])`; executed has the same hole through `src.recorded(req["_t"])`. **Fix:** additionally require `src.recorded(line["_t"])` before a spoken answer can qualify either criterion—ideally checking coverage of the speech interval rather than only its first timestamp.

Done: (6) `seq_limit()`: every search for a request or a refusal stops at the window end, the agent's next start
(supervisor service_started) or the next chat row with the same seq. (7) An activity change needs >= 60 s of active
time while the director records on both sides (`recorded_s` in the spans), besides the recorded transition. (8) The
spoken answer of a request and the spoken refusal must themselves be on air.

## Part 3: errors, on-air replay, two cameras, voice/head/mouth (12 009 tokens, 274 s)

> 1. **High — `eval_errors()` / `output_healthy()`: future evidence can turn a pending recovery into PASS.** The recovery search accepts rows after `src.until`, and the health search has no upper time bound. Use `cutoff = min(src.until, t + deadline)` for both; require recovery rows, director health rows, and recording segments to fall within `(after, cutoff]`. When health is `None`, report `pending` only if the deadline extends beyond the window; once the deadline has elapsed, report `unrecovered`.
>
> 2. **High — `eval_errors()`: incident merging can erase an unresolved fault.** On every merge, `state=f["state"]` overwrites the earlier state. Thus an unrecovered/pending fault followed by a recovered fault of the same kind can produce a recovered incident and overall PASS. Retain member faults and aggregate conservatively: `unrecovered > pending > recovered`; calculate recovery/outage from paired member recoveries rather than carrying an unrelated `rec`.
>
> 3. **High — `on_air()`: CAM2 state is never replayed.** `cam2_changed` is unhandled, so a span starting with `cam2=True` remains true after CAM2 is lost, inflating room time and potentially passing `two_cameras`. After the existing stale-run guard, add:
>    ```python
>    elif k == "cam2_changed":
>        close(t)
>        cur = dict(cur, start=t, cam2=bool(r.get("cam2")))
>    ```
>
> 4. **High — `eval_two_cameras()`: CAM2 evidence can come from outside the assessment window.** Room durations are clipped, but CAM2 selection uses the unclipped `s["start"]`/`s["end"]`. A good line before `src.since` can therefore satisfy `cam2 and not bad`. Build clipped room intervals `(max(start, since), min(end, until))` and select CAM2 lines only inside those intervals.
>
> 5. **High — `eval_mouth_motion()`: post-window and post-speech readiness can produce PASS.** Neither `ready` nor `rejected` has an upper bound, and readiness need not precede any utterance. Require `ready.t <= src.until`, `src.since <= rejected.t <= src.until`, and only PASS for utterances covered by a `MOUTH_READY` already active for that game run.
>
> 6. **Medium — `eval_two_cameras()`: the 30-second stretch is fragmented by irrelevant state changes.** `voice_changed` splits spans while preserving room/CAM2; three contiguous 20-second spans consequently fail despite a continuous 60-second room composition. Merge touching spans with identical `run`, `layout`, and `cam2` before computing `longest`.
>
> 7. **Medium — `eval_voice_k07()`: unknown engines do not prevent PASS.** Known K07 utterances can satisfy the thresholds while additional utterances have unknown engine/fallback status. After retaining the explicit known-non-K07 FAIL, return MISSING when `engine_unknown` is nonzero rather than claiming the complete criterion passed.
>
> 8. **Medium — `eval_head_motion()`: unmeasurable axes are reported as failure.** One integer/missing value excludes an entire axis via `all(isinstance(..., float))`; empty `ranges` then becomes “below threshold.” Collect numeric samples per axis and return MISSING if neither axis has at least two usable samples.

Done: (1) recoveries must fall in (fault, min(window end, fault + deadline)]; a restarted run's health is measured
inside the window only, and an unmeasured one is pending only until its first segment row is due (restart + 660 s),
unrecovered after that. (2) A merged incident takes its worst member's state (unrecovered > pending > recovered).
(3) on_air() replays cam2_changed. (4) CAM2 lines are taken only inside the clipped room intervals. (5) mouth_motion
checks each utterance against the MOUTH_READY of the game run live at that moment (MISSING for an utterance before
it). (6) Touching room spans of one run are merged before the 30 s stretch is measured. (7) voice_k07 is MISSING when
any utterance has an unknown engine. (8) head_motion measures each axis on its own usable samples; MISSING when
neither axis has two.

## Part 4: PC control, fps criteria, report, CLI, RUNBOOK (14 979 tokens, 373 s)

> 1. **Medium — `eval_fps_recordings()`: probe failure is conflated with measured failure and, potentially, recording absence.** An ffprobe timeout or `{"error": "not probed"}` is appended to `bad`, producing **FAIL**, although that path cannot establish either low fps or missing output. If `s["probed"]` is false, the segment is also excluded from `spans`, so an existing but unprobed recording can additionally be reported as “not recording.” This conflicts with the MISSING/cannot-assess rule and the RUNBOOK’s status description.
>    **Fix:** maintain separate `measured_bad` and `unassessable` lists. Determine recording-timeline gaps independently of probe success. Return FAIL for measured low fps or genuine coverage gaps; otherwise return MISSING when probe/assessment errors remain, and PASS only when neither exists. If corrupt containers are intentionally failures, distinguish that error from timeout/not-probed/ffprobe-unavailable. Apply the same distinction to probe errors in `eval_fps_hls()`.
>
> 2. **Low — RUNBOOK: the director-row summary omits the implemented partial-row rule.** “Director rows … >= 59.9” does not explain that complete rows check both `fps` and `fps_media`, while qualifying partial rows ignore wall-clock `fps` and use `fps_media` plus dup/drop.
>    **Fix:** add: “Complete director rows must pass both fps measurements; partial rows with `wall_s >= partial_min_s` are judged on `fps_media` and dup/drop, not wall-clock `fps`; shorter partial rows are not fps evidence.”
>
> Otherwise, the requested logic is consistent: `source_windows()` checks consecutive and window-boundary gaps; the recording edge-pairing correctly detects leading, internal, and trailing gaps for sorted unioned spans; qualifying partial director rows retain dup/drop enforcement; and `evaluate()`/`main()` implement PASS-only-when-all-pass, FAIL precedence, otherwise INCONCLUSIVE, with exit 0 only for PASS.
>
> no blocking finding

Done: (1) a probe error (timeout, not probed, ffprobe missing) makes fps_recordings / fps_hls_spot MISSING, not FAIL;
the recording timeline is built from every segment (an unprobed one by name and mtime) and a gap fails only between
measured edges, a gap next to an unprobed segment is "cannot measure". (2) The RUNBOOK states the partial-row rule and
the probe-error rule.

## Final check of the fixes (the diff from the reviewed version, half 2: 10 681 tokens, 281 s)

> 1. **Medium — `eval_two_cameras` (clipped `room` span construction):** spans wholly outside `[src.since, src.until]` are still appended. For these, `a > b`, producing negative durations that pollute `room_s`/`longest`, can participate in merging, and can make an otherwise valid window fail merely because older room spans exist. After clipping, add `if b <= a: continue` before merging or appending, so only positive in-window intervals contribute.

The whole diff in one call (12k tokens in) came back empty twice (the reasoning used the 16k limit); it was then
checked in two halves with a system prompt stating the token budget. Half 1: "no blocking finding". Half 2, quoted:

> 1. **Medium — `eval_two_cameras` (clipped `room` span construction):** spans wholly outside `[src.since, src.until]` are still appended. For these, `a > b`, producing negative durations that pollute `room_s`/`longest`, can participate in merging, and can make an otherwise valid window fail merely because older room spans exist. After clipping, add `if b <= a: continue` before merging or appending, so only positive in-window intervals contribute.

Done: the clipped room interval is skipped when it is empty. The spans reaching that loop are already only the ones overlapping the window (the list is filtered by clip() > 0 just before), so no negative duration could occur; the guard keeps the loop safe on its own.

## The questions as sent

`q-part1.txt`:

```text
IMPORTANT: think briefly (at most ~4000 tokens of reasoning) and answer in at most ~500 words: numbered findings with severity high/medium/low, the function and the concrete fix; end with "no blocking finding" if none is high. Context: SUB-01 plan step 7, scripts/streamer_acceptance.py reads the pod's streamer logs and recordings for a time window and writes pass/fail/missing per criterion (you agreed the criteria an hour ago: every complete source fps window >= 59.5 with no gap, outputs >= 59.9, director dup/drop 0, MISSING only for 'cannot assess', verdict PASS/FAIL/INCONCLUSIVE). 41 tests pass; a read-only dry run on the pod took 2 s. This is part 1 of 4 of the pre-commit review; the other parts are reviewed separately.

Attached: lines 1-433 (header, thresholds, mask(), to_unix(), read_jsonl(), component(), timed(), the game-log parser, the voice.log replay, list_recordings(), read_hls(), ffprobe_count()). Check only: (a) can mask() leak a token, key or URL secret into a report line, or mangle a log tag? (b) time parsing errors (UE stamps are UTC; ISO with Z, +00:00, +0000, ms) and window edges; (c) the voice.log replay (sticky fallback until the next 'listening on'); (d) ffprobe usage: read-only, no decode, safe on a growing fragmented MP4, timeout.
```

`q-part2.txt`:

```text
IMPORTANT: think briefly (at most ~4000 tokens of reasoning) and answer in at most ~500 words: numbered findings with severity high/medium/low, the function and the concrete fix; end with "no blocking finding" if none is high. Context: SUB-01 plan step 7, scripts/streamer_acceptance.py reads the pod's streamer logs and recordings for a time window and writes pass/fail/missing per criterion (you agreed the criteria an hour ago: every complete source fps window >= 59.5 with no gap, outputs >= 59.9, director dup/drop 0, MISSING only for 'cannot assess', verdict PASS/FAIL/INCONCLUSIVE). 41 tests pass; a read-only dry run on the pod took 2 s. This is part 2 of 4 of the pre-commit review; the other parts are reviewed separately.

Attached: lines 434-813 (the Sources class: probing order, locate(), air()/recorded(), events_gap(); absent(); inactive_intervals(); eval_activity(); spoken(); bound_outcomes(); eval_chat_executed(); eval_chat_refused()). Check only: (a) can a criterion PASS without the evidence it claims, or FAIL on healthy data? (b) the activity spans (carried-in label within 300 s, dwell minus quiet/held/privacy, browse<->game only); (c) request binding (outcomes after an action with decision_id req-<seq> until the next action; routine_start{seq} then routine_end); (d) events_gap (rows within 15 min of both window ends) as the test of 'the log covers the window'.
```

`q-part2b.txt`:

```text
IMPORTANT: think briefly (at most ~4000 tokens of reasoning) and answer in at most ~400 words.
Follow-up to your pre-commit review of part 2 of scripts/streamer_acceptance.py (the Sources class, absent(), inactive_intervals(), eval_activity(), spoken(), bound_outcomes(), eval_chat_executed(), eval_chat_refused()). Your answer was cut off by the output limit in the middle of finding 5. Findings 1-5 are applied in the attached current code: (1) chat_executed matches the first chat_request_end of the same seq inside [request, window end] and bounds outcomes and speech to the window; (2) activity spans are half-open [start, end) except the last, so a routine_end opening the game span verifies only that span; (3) request_redirect rows are listed apart (executed, then undone), never counted as the refusal, and the bound-action search is limited to [refusal, window end] and to before the same seq is reused by a restarted agent; (4) events_gap needs rows within 15 min of each window end; (5) held/resume and stream_frozen/resume_latches have separate slots.
List ONLY further findings (6 and later) with severity high or medium, the function and the fix; if there are none, answer exactly "no further finding".
```

`q-part3.txt`:

```text
IMPORTANT: think briefly (at most ~4000 tokens of reasoning) and answer in at most ~500 words: numbered findings with severity high/medium/low, the function and the concrete fix; end with "no blocking finding" if none is high. Context: SUB-01 plan step 7, scripts/streamer_acceptance.py reads the pod's streamer logs and recordings for a time window and writes pass/fail/missing per criterion (you agreed the criteria an hour ago: every complete source fps window >= 59.5 with no gap, outputs >= 59.9, director dup/drop 0, MISSING only for 'cannot assess', verdict PASS/FAIL/INCONCLUSIVE). 41 tests pass; a read-only dry run on the pod took 2 s. This is part 3 of 4 of the pre-commit review; the other parts are reviewed separately.

Attached: lines 814-1170 (output_healthy(), recovery_rules(), eval_errors() with incident grouping, on_air() replay of the director's runs, eval_two_cameras(), utterances(), eval_voice_k07(), eval_voice_recorded(), eval_head_motion(), eval_mouth_motion()). Check only: (a) fault/recovery pairing and incident grouping bugs, a pending recovery that could be reported as recovered; (b) the on-air replay (stale run rows ignored, stop/exit closes a span, carried state); (c) room >= 60 s with a 30 s stretch and CAM2 lines; (d) the voice/head/mouth split.
```

`q-part4.txt`:

```text
IMPORTANT: think briefly (at most ~4000 tokens of reasoning) and answer in at most ~500 words: numbered findings with severity high/medium/low, the function and the concrete fix; end with "no blocking finding" if none is high. Context: SUB-01 plan step 7, scripts/streamer_acceptance.py reads the pod's streamer logs and recordings for a time window and writes pass/fail/missing per criterion (you agreed the criteria an hour ago: every complete source fps window >= 59.5 with no gap, outputs >= 59.9, director dup/drop 0, MISSING only for 'cannot assess', verdict PASS/FAIL/INCONCLUSIVE). 41 tests pass; a read-only dry run on the pod took 2 s. This is part 4 of 4 of the pre-commit review; the other parts are reviewed separately.

Attached: lines 1171-end (eval_pc_control(), source_windows() and the fps criteria, eval_fps_director(), eval_fps_recordings() coverage/gaps, eval_fps_hls(), evaluate(), render_markdown(), parse_window(), main()) and the RUNBOOK diff. Check only: (a) the gap logic in source_windows() and the recording coverage; (b) a partial director row judged on fps_media and dup/drop; (c) the verdict/exit code; (d) the RUNBOOK text vs the code.
```

`q-delta1.txt`:

```text
IMPORTANT: think briefly (at most ~4000 tokens of reasoning) and answer in at most ~400 words.
Final check before commit of scripts/streamer_acceptance.py. Attached: HALF 1 of 2 of the unified diff (the other half is checked separately) from the version you reviewed
in four parts to the current code. It applies your findings: part 1 (masking of any *token*/*secret* key, Basic/
Bearer, URL userinfo, SUB01_-only tag exemption, recursive key scrub; PDT carried forward in read_hls; nonzero ffprobe
exit rejected and a growing segment flagged but still used; NaN/inf rejected), part 2 (window-bounded request end,
outcomes and speech; half-open activity spans; redirects apart; events_gap rows within 15 min of each end; separate
held/frozen slots), part 2b (seq_limit: the next same-seq chat row or the agent's next service_started bounds every
search; activity needs >= 60 s of recorded active time on both sides; the spoken answer/refusal must be on air),
part 3 (recoveries bounded by min(window end, deadline); health pending only until the first segment row is due;
worst-state incidents; cam2_changed replayed; CAM2 lines inside clipped room intervals; touching room spans merged;
per-utterance MOUTH_READY; unknown engine -> MISSING; per-axis head ranges), part 4 (probe errors -> MISSING, gaps
fail only between measured edges; RUNBOOK). 61 tests pass.
Check ONLY whether a fix is wrong or introduced a new high/medium bug. List such findings with the function and fix,
or answer exactly "no blocking finding".
```
