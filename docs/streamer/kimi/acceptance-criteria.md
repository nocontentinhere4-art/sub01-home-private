# Kimi consultation (2026-10-24): acceptance criteria and thresholds (plan step 7)

Question: at the end of this file (the sources and their real formats, today's values, the proposed criteria C1-C8
and nine questions). Model kimi-k3.1-pro; the first call spent its 16 000 tokens reasoning and gave no answer, the
second (40 000 tokens, ~6 min) answered. Kimi's answer, verbatim:

> 1. **No: median/p05 can conceal exactly the sawtooth you need to detect.** With 180 PERF samples, several very bad windows can sit below the 5th percentile while the criterion passes; 90% coverage also permits three minutes unobserved. Use **every complete window ≥59.5 fps**, with median/p05 retained only as diagnostics, and **100% expected-sample coverage** over the applicable on-air/active interval, excluding only incomplete boundary windows. A logging gap is inconclusive, not a passing interval. Even this proves “every logged 10/30-second average met tolerance,” not instantaneous, stall-free 60 fps. The sawtooth must be fixed or explicitly waived.
>
> 2. **Use 59.9 for director, recording-container and HLS output pace; retain source thresholds separately.** For non-partial director segments require **dup_frames = drop_frames = 0**: 0.5% permits about 180 frames in a 36,000-frame segment. Count only video packets and use the video/media timeline rather than format duration when audio makes it differ. `r_frame_rate=60/1` is metadata, not measurement. Yes, source metrics are indispensable: the fps filter can turn 40 delivered fps into a perfectly paced 60 fps recording by repeating frames. Neither 59.5 nor 59.9 proves unique source frames.
>
> 3. **The four labels are reasonable, but the dwell test needs tightening.** Require at least **60 seconds elapsed on-air in each state**, not 60 seconds composed of sparse agent actions, with successful activity evidence in each. Carry the initial activity state in from before the window. Treat `video` as an inferred label unless playback is evidenced; merely opening a video host is weak evidence. A host change within `browse` should remain only a topic change. Also exclude held/quiet/privacy intervals from dwell.
>
> 4. **Excluding operational refusals is reasonable for a explicitly named `policy_refusal` criterion, but it is stricter than the owner’s generic “one refused”; confirm that interpretation.** Do not require every refusal to be voiced when lines are rate-limited. Require the **one acceptance refusal** to have audible or visible on-air delivery—speech/caption linked within 60 seconds, or equivalent recorded evidence—and report its delivery mode. A purely internal refusal log does not prove content in the recording. A later safe alternative action should not invalidate a refusal; only execution of the refused request should.
>
> 5. **Keep 120/300/120/60/300 seconds as initial test SLOs; their operational suitability cannot be derived from the supplied data.** Report actual recovery time and outage duration. **Yes: any unrecovered incident fails**, even after another recovered; group repeated symptoms into incidents rather than averaging them away. A pending deadline should block overall PASS until observation is extended, not disappear into a pass. Make recovery fault-specific: `layout_switch_failed` needs a successful layout switch, and unintended cam2 loss needs cam2 restored/healthy. For recording faults, `ffmpeg_started` alone is insufficient—require subsequent healthy output. Do not classify operator STOP holds, intentional privacy cuts, or intentional cam2-off as faults.
>
> 6. **Require both ≥60 seconds cumulative and one continuous ≥30-second stretch.** Cumulative time alone can pass through repeated brief flashes. All qualifying time must be recorded `room`, with run `cam2=true`, `on=1`, `reader=1`, and delivered fps >0; highlight the continuous stretch.
>
> 7. **Passing the literal owner requirement on wiring evidence alone would not be honest.** Split C6 into `voice_k07`, `voice_recorded`, `head_motion`, and `mouth_motion`. `MOUTH_READY` plus `talking` proves readiness/state, not visible movement. Use recorded visual inspection or actual POSE variation overlapping speech for head motion. With the stated head-only rig and no jaw/morph targets, literal mouth motion/lip movement is **not met** unless the owner explicitly redefines it as mouth-driven head emphasis. K07 itself can pass only when the ordered voice-log replay starts from a known engine/fallback state.
>
> 8. **Agree: today it is MISSING.** The best no-new-process measurement is in the existing native UE HTTP polling path: count received frames and frames actually applied/presented, then emit, for example, `fps_in`, `fps_applied`, sequence/age and window duration every 10 seconds. Sidecar health alone does not prove in-game presentation, and a live sample cannot reconstruct 30 minutes. Director/HLS fps and pixel changes are not substitutes, especially for static desktop content.
>
> 9. **Use MISSING strictly for “cannot assess,” not “required event did not occur.”** Complete logs showing no fault, speech, refusal or PC actions mean the required content is absent: FAIL. Absent/rotated-away logs, unknown clock correlation or unavailable monitor metrics are MISSING. Overall should be PASS only when all pass; any FAIL gives FAIL, otherwise any MISSING gives INCONCLUSIVE. Read both event files, carry state across the window boundary, record coverage/parse gaps and clock skew, and verify that content evidence overlaps the recording. Highlights need actual media-timeline offsets, not merely filename assumptions. Finally, HLS’s ~24-second history supports only `fps_hls_spot`; it cannot prove a 30-minute HLS criterion.
>
> **Concrete edits before coding**
> - **C2:** accept `why=done`; do not treat `steps` as success unless documented otherwise. The shown action rows lack `seq`, so request-specific action correlation must be established or marked unproven.
> - **C4/C7:** correct the MISSING/FAIL cases above; make pending faults block overall PASS.
> - **C5:** add the continuous 30-second requirement.
> - **C6:** split voice/head/mouth and mark literal mouth motion unmet on this rig.
> - **C8:** source `min≥59.5`, expected coverage 100%; output pace `≥59.9`, zero director dup/drop; recording coverage 100%; split HLS spot from full-window compliance.
>
> Today’s quoted values cannot pass overall: PERF 48.8 and CAM2 delivered 40 fail, while director output at approximately 60.005 fps with zero dup/drop proves only output pace.

## What was adopted in `scripts/streamer_acceptance.py`

1. **Sources: every complete window, no gap.** PERF, CAM2 and monitor lines pass only when every window is >= 59.5 fps
   (median/p05 kept as diagnostics). A gap (consecutive lines, or the window ends, more than 1.5 periods apart) makes
   the criterion MISSING ("unmeasured time is not a pass"); a window below 59.5 makes it FAIL whatever the gaps.
2. **Outputs: 59.9.** Director rows, recording packets / video-stream duration and HLS packets / EXTINF need >= 59.9;
   non-partial director rows need dup = drop = 0. `r_frame_rate` is reported, never judged. Any speed_restart in the
   window fails `fps_director`. The report states that output pace does not prove distinct source frames.
   Adapted: a partial director row (the run ended: restart, stop) is judged on `fps_media` and dup/drop, because its
   `fps` divides by wall time that includes ffmpeg's start and stop (today's real partial row: 59.3 wall, 60.04 media).
   Recording coverage: the whole window, gaps between segments up to 2 s tolerated (segment starts are estimated as
   mtime minus the probed duration).
3. **Activity:** dwell is elapsed time in a state, carried in from before the window, minus quiet, held/frozen and
   privacy intervals, with at least one verified outcome on each side and the change on air. Only browse <-> game
   counts; a change to/from `video` (a host, not proven playback) and site changes inside browsing are listed as weak.
4. **Refusals:** operational refusals (pc_offline, hands_off, no_model, games_off) are listed apart and do not count
   (the acceptance shows the chat policy, as the rehearsal schedules: admin, leave_desk); the owner can say otherwise.
   The counted refusal must be **spoken** (a `speech` row; a `caption` row means the voice failed and is shown as
   "caption only (not on air)") within 60 s, recorded, and never executed (no action bound to `req-<seq>`); a later
   unrelated action does not invalidate it.
5. **Errors:** deadlines kept (director 120 s, cam2 300 s, supervisor 300 s, agent 300 s, runner 60 s, Vagon 300 s,
   watchdog 900 s); outage times reported; faults of one kind within 60 s are one incident; any unrecovered incident
   fails; a pending one makes the criterion MISSING, which blocks an overall PASS. Recoveries are fault-specific:
   `layout_switch_failed` needs that layout on air (a switch or a relaunch on it); a recording fault needs a restart
   AND the new run's output measured at >= 59.9 with no dup/drop (its segment row or its probed segment), else
   pending; a cam2 loss needs cam2 healthy again (a game CAM2 line on=1 with frames, or the director re-adding it).
   Not faults: a cam2 drop while the game's CAM2 line says on=0 (switched off on purpose), requested restarts,
   privacy cuts. Kept as a fault: a watchdog trip (automatic, not an operator STOP).
6. **Two cameras:** >= 60 s of `room` with cam2 in all AND one stretch >= 30 s, with every CAM2 line in that time
   on=1, reader=1, fps > 0; the stretch is a highlight.
7. **Voice split** into `voice_k07` (replay of voice.log from a known `listening on` line; an utterance before one is
   "engine unknown"), `voice_recorded`, `head_motion` (POSE head pitch/yaw range >= 1 degree over the samples taken
   during speech, plus a talking state; with the note that 10 s POSE sampling shows the head moved while he spoke, not
   that the voice drove it) and `mouth_motion`, which FAILS on the current head_only rig ("not met") until a jaw/morph
   rig exists or the owner redefines it.
8. **Monitor feed:** MISSING today, with the recommendation for native v22: a `SUB01_STREAMER_VISUAL_MONITOR` line
   every 10 s with `fps_in`, `fps_applied`, sequence/age and `window_s` from the native polling path; the check
   already reads that shape (`fps_applied` first). The sidecar's live health is not accepted (no history, no proof of
   presentation); the `--monitor-samples` option of the first draft was dropped.
9. **Semantics:** MISSING only for "cannot assess" (a log absent or not covering the window: events.jsonl must have
   rows within 15 minutes of both window ends; a gap; no measuring source; a pending recovery; HLS rotated away);
   complete logs without the required content FAIL. Verdict PASS / FAIL / INCONCLUSIVE. Both event files are read,
   state is carried across the window start, bad lines are counted per source, content criteria require the moment
   to be on air, highlights use the probed media timeline (marked "approx." otherwise). HLS is `fps_hls_spot`.
- C2 accepts only `why=done` (not `steps`); the result must be bound to the request: the outcomes after an action
  with `decision_id req-<seq>` or the routine_end of a game routine started with that seq. A model-picked `look`
  request has no binding in the logs and is reported as unproven.

## The question sent to Kimi

```text
(Please keep your reasoning short and answer in at most ~1000 words: a numbered answer per question, then a short
list of concrete changes to the criteria.)

SUB-01 (a simulated streamer in a native UE 5.8 house on a GPU pod; a director composes two cameras and a PC desktop,
records 60 fps NVENC 10-minute MP4 segments and a local HLS) needs a 30-minute ACCEPTANCE RECORDING (plan step 7).
I am writing scripts/streamer_acceptance.py: given a time window (default the last 30 minutes) it reads the real logs and
recordings, and writes a Markdown report plus a JSON with pass/fail per criterion, each with evidence lines, timestamps
and highlight timestamps (segment file + offset). Please review the criteria definitions and thresholds below, BEFORE I
code them. Be concrete: say which numbers to change and why.

Required content of the recording (owner): a change of activity; a chat request carried out and one refused; an error
that was recovered; both cameras composed simultaneously; K07 voice with head (and mouth) motion; control of the PC
(keyboard and mouse on the owner's Vagon cloud desktop); measured fps. Owner rule: "60 fps on everything" (game render,
cam2, the in-game monitor feed, the director's per-segment output, HLS), PROVEN BY MEASURED FPS IN LOGS, NOT BY CAPS.

## Sources (real formats seen on the pod today)
- events.jsonl (shared, append-only; rotates to events.1.jsonl at 20 MB). Rows are told apart by shape:
  agent rows have numeric `t` (unix) + `utc`; director rows `source: director` with ISO `t`; supervisor `source: streamer_up`.
  Agent kinds: decision{state, action, provider}, action{action, source: model|chat|routine|quiet, decision_id},
  outcome{action, verdict: changed|unchanged|moved|done|pending|error, url, title, pixel_diff}, chat{seq, cls: ok|request|
  human|inject|finance}, chat_window{offered, local, answered}, chat_request{seq, decision: executed|queued|dropped|refused,
  reason}, chat_request_end{seq, request, steps, why: done|steps|time|quiet|failed|refused|redirected, commented},
  speech|caption{text, tag, seqs}, error{where}, quiet{mode}, quiet_end, held, resume, stream_frozen, resume_latches,
  provider_switch, action_timeout, inject, routine_start{name: launch_game|stop_game}, routine_end{why: started|
  steam_open|stopped|...}, pc{phase, remote_ready}, pc_blocked, layout.
  Director kinds: ffmpeg_started{run, layout, cam2, voice, encoder, fps, hls}, ffmpeg_stopped, ffmpeg_exited,
  layout_switched{layout, previous}, layout_switch_failed, cam2_changed{cam2}, speed_restart{speed}, speed_restart_held,
  watchdog_restart, segment_fps{segment, frames, wall_s, media_s, fps, fps_media, dup_frames, drop_frames, partial}.
  Supervisor kinds: service_started/up/unhealthy/crashed/failed/stopped, kill/resume.
- Layouts: webcam (game viewport = frontal webcam, desktop PiP), desktop, split, room (cam2 full frame + webcam PiP:
  the ONLY layout composing both cameras), webcam_only (privacy cut).
- Game log (UE, UTC stamps): `SUB01_STREAMER_VISUAL_PERF fps=48.8 ms=20.50 max_ms=25.6 gpu_ms=10.70 frames=488
  window_s=10 ...` every 10 s; `SUB01_STREAMER_VISUAL_CAM2 fps=40.0 capture_fps=50.3 target_fps=60 frames=... reader=1
  ... on=1 window_s=30` every 30 s (fps = frames written to the FIFO the director reads); `SUB01_STREAMER_VISUAL_STATE
  reading -> talking`; `SUB01_STREAMER_VISUAL_MOUTH_READY rig=head_only (no jaw bone, no morph targets: emphasis, not
  lip sync) file=.../mouth.json pollHz=30 headPitchDeg=2 jawPitchDeg=12`; `..._MOUTH_FILE_REJECTED` on a bad file;
  `SUB01_STREAMER_VISUAL_POSE ... headPitch= headYaw=` every 10 s. NO line logs the in-game monitor feed fps.
- Voice: speech/timeline.jsonl {id, tag, text, start_utc, end_utc, cut, error?}; logs/voice.log has no timestamps but
  is ordered: "listening on ... engine=chatterbox voice=sub01-voice-reference-k07.wav fallback=kokoro:am_puck",
  "<primary> unavailable (...); falling back to kokoro" (sticky until restart), "spoken id=<UTC stamp>-NNNN ...".
  mouth.json (open 0..1 at 25 Hz while speaking) is a live snapshot only, no history.
- Desktop runner (Vagon mode) desktop-vagon/events.jsonl: act{action: key|type|click|scroll..., ok, outcome{changed,
  errors}}, vagon{state: connected|disconnected|login_required|...}, browser{state}, relaunch.
- Monitor feed sidecar (:103 -> monitor.mjpeg FIFO): fps only on a live HTTP health endpoint, no log history; not
  running today (the game currently polls the old runner over HTTP for the monitor picture).
- Recordings: recordings/sub01-YYYYmmdd-HHMMSS-NNN.mp4 (fragmented MP4, 10 min, 60/1). HLS: hls/live.m3u8 with
  EXT-X-PROGRAM-DATE-TIME, 4 s .ts segments, list size 6 (only ~24-28 s of history kept).
- rehearsal.jsonl: induced faults {kind: inject, event: kill_browser|provider_error, t}.
- watchdog.jsonl: {kind: trip, why, stop_written}.

Today's real values (agent held by STOP, Vagon PC off/login_required, no chat): PERF fps 48.8; CAM2 fps 40 (capture
50); director segment_fps 60.0 (36021 frames / 600.3 s, dup 0, drop 0); layout webcam_only since 14:06; no speech.

## Proposed criteria (status: pass | fail | missing = "missing evidence"; overall pass only if all pass)
C1 activity_change. Activity label per agent action: game (between routine_end{launch_game, started|steam_open} and
   routine_end{stop_game, stopped}), video (URL host youtube/youtu.be/twitch/vimeo/dailymotion), browse (other web
   actions), desktop (Vagon actions outside a game). PASS: >= 1 transition between two DIFFERENT labels with >= 60 s of
   agent activity on each side. A host change inside `browse` is reported as a weak "topic change", not a pass.
   FAIL: agent active, single label. MISSING: no decision/action rows in the window.
C2 chat_executed. PASS: >= 1 chat_request{executed} in the window for a desktop request (open/search/look/scroll/
   launch_game; not face/hush), whose chat_request_end has why in {done, steps}, with >= 1 action row source chat|routine
   for that request whose outcome verdict is changed|moved|done, and a voiced line (speech row whose seqs contain the
   seq). FAIL: executed requests but all ended failed/refused/redirected/time or with no successful action.
C3 chat_refused. PASS: >= 1 POLICY refusal (chat_request{refused} with a reason other than the operational ones
   pc_offline|hands_off|no_model|games_off; or a chat row cls human|inject|finance answered by a local line) with the
   refusal voiced (speech/caption, seqs contain the seq, within 60 s) and NO action row for that seq. Operational
   refusals are listed but do not count. FAIL: a refused request got an action, or only operational refusals.
C4 error_recovered. Faults and their recovery deadlines: director ffmpeg_exited|watchdog_restart|speed_restart|
   cam2_changed{false}|layout_switch_failed -> ffmpeg_started within 120 s; supervisor service_crashed|unhealthy|
   failed -> service_up same service within 300 s; agent error|quiet{error}|held|stream_frozen|action_timeout ->
   quiet_end|resume|resume_latches|a later valid decision within 120 s; runner relaunch -> browser ready within 60 s;
   vagon disconnected -> connected within 300 s. Rehearsal injects are labelled "induced". PASS: >= 1 recovered fault
   and no unrecovered fault (a fault whose deadline runs past the window end is "pending", not a fail). FAIL: a fault
   not recovered in time. MISSING: no fault in the window.
C5 two_cameras. On-air layout timeline from director rows (state carried in from before the window). PASS: >= 60 s
   cumulative in layout `room` with the run's cam2 = true AND game CAM2 lines in that time with on=1 reader=1 fps>0.
   FAIL: the director recorded, never composed both. MISSING: no director run.
C6 voice_k07_head_mouth. PASS: >= 3 utterances and >= 20 s speech in the window (timeline.jsonl, no error), every one
   spoken while the voice.log replay says engine chatterbox + the k07 prompt and no fallback; the recording carried
   voice (ffmpeg_started voice=true for the runs on air); the game log has MOUTH_READY for the game run live in the
   window (rig named), no MOUTH_FILE_REJECTED in the window, and a STATE "-> talking" line overlapping >= 1 utterance.
   rig=head_only is reported as a WARNING (head emphasis, no lip sync), not a fail. FAIL: any utterance on the fallback.
C7 pc_control. PASS: runner act rows in the window with ok and outcome.changed, >= 1 keyboard (key|type) and >= 1
   mouse (click|scroll|move|drag), each while the last vagon state row was `connected`; agent outcome rows (verdict
   changed, pixel_diff) shown when present. MISSING: no act rows. FAIL: act rows but not connected or nothing changed.
C8 fps, one sub-criterion each:
   fps_game: PERF windows covering >= 90% of the window; median >= 59.5, p05 >= 58.0.
   fps_cam2: CAM2 `fps` (delivered) with on=1 reader=1, covering >= 90%; median >= 59.5, p05 >= 58.0; capture_fps shown.
   fps_monitor_feed: no source logs it -> MISSING today; accepted sources: a game log line SUB01_STREAMER_VISUAL_MONITOR*
     with fps= (to be added in native v22), or an optional JSONL of the sidecar's health samples (fps_in).
   fps_director: segment_fps rows overlapping the window (non-partial; partial ones only if >= 60 s): fps >= 59.5 and
     fps_media >= 59.5, dup+drop <= 0.5% of frames; any speed_restart in the window fails it.
   fps_recordings: ffprobe -count_packets (no decode) on each segment overlapping the window: nb_read_packets /
     format duration >= 59.5, r_frame_rate 60/1, segments covering >= 90% of the window.
   fps_hls: ffprobe -count_packets on the .ts segments overlapping the window: packets / EXTINF >= 59.5 for every one.
     HLS keeps ~24 s, so this is a spot check at the window end; MISSING if none overlap (run within ~20 s of the end).

## Questions
1. Is "median >= 59.5, p05 >= 58.0, coverage >= 90%" an honest "60 fps measured" for the 10-s PERF and 30-s CAM2
   windows, given a known render-thread sawtooth (+-5 fps, reset every ~7 min)? Or should every window be >= 59?
2. Container counts (packets/duration, segment_fps): 59.5 or tighter (59.9)? Note packets prove the output pace only,
   the graph's fps filter repeats frames a source did not deliver; is that a reason to require the source metrics too?
3. Is the activity-change definition right (labels, 60 s dwell, host change = weak)?
4. Refusals: exclude operational reasons? Require the refusal to be voiced (refusal lines are rate-limited)?
5. Error recovery: deadlines OK? Should one unrecovered fault fail the criterion even if another recovered?
6. Two cameras: is 60 s cumulative in `room` enough, or require one continuous stretch (e.g. >= 30 s)?
7. Voice/head/mouth: with a head_only rig, is passing on wiring evidence (MOUTH_READY + talking state + K07 utterances)
   honest, or must the report mark the mouth part as "not met"?
8. Monitor feed: MISSING with a recommendation (v22 log line) - agree? Anything better that needs no new process?
9. pass/fail/missing semantics, and anything else a reviewer would expect in such a report.
```
