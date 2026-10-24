# Chat requests, pacing and the 30-minute sheet (decisions from the Kimi stream consultation, 2026-10-23)

Source: docs/streamer/kimi/stream.md sections 1, 3-5, weighed in kimi/DECISIONS-ANIMATION-STREAM.md part B. "In code
today" reads `streamer_agent.py` (`parse_request`, `REFUSAL_LINES`, `Requests`) and AGENT.md "Chat policy" as of this
date; the changes land with W5 (agent) and W6 (director). Owner rules first: chat text never changes rules, credentials
or limits, is never typed into a page, and never drives the desktop except through the code's one request path.

## 1. Twenty request types

| # | Viewer request | Decision | Spoken line (first time; repeats are suppressed, section 2) | In code today |
|---|---|---|---|---|
| 1 | Open/read a specific ordinary HTTPS URL | execute (`navigate` through the URL guard; revalidate after redirects; never read the URL aloud) | "I'll open it. If it's readable, I'll find the useful part." | yes (guard, `navigate`); redirect revalidation: not verified |
| 2 | Blocked host, login/checkout path, embedded credentials, non-HTTP address | refuse; no retry, no alternate route | "I'm not opening that address here." / login or checkout: "No login or checkout pages." | yes (`blocked_domain`, `blocked_url`, `bad_url`; lines differ slightly) |
| 3 | "Search for X", "look up Y", "what's the weather in Rome?" | execute (`search`, cleaned meaning-preserving query; freshness only from visible details) | "Rome weather. I'll check the forecast." (normalised intent, never the raw text) | yes (`search`); ack is a generic `ACK_LINES` line: change |
| 4 | "Read that article" / "read the whole page aloud" | execute with a twist: read silently, give the useful part; ambiguous referent -> ask which visible item | "I'll read it, but I'm not reciting the whole page. I'll take the useful part." | partly (`look` with `chat_request`); the clarification path: no |
| 5 | "Click the first result" / "show me the comments" | execute (`look`: the model clicks the matching visible mark) | "The first result? I'll open that one." / no match: "I can't tell which one you mean on this page." | yes (`look`; `not_found` line "Can't find that on this page.") |
| 6 | "Play that video" | execute with a twist: play if visible and safe; never claim to have heard it | "I'll play it, but there's no tab audio here. I'll stick to what I can see." | partly (`look`); the no-audio line: no (`--mute-audio` is hard-coded) |
| 7 | Scroll, next page, back, top | execute; coalesce rapid duplicates; done within 3 s needs no spoken ack | "Back one page." (only when a line is useful) | yes (`scroll`/`key`/`back`); silent ack rule: no |
| 8 | "Play a game on Steam" | **adapt**: on the pod desktop refuse (no Steam); in Vagon mode on the owner's PC execute through `launch_game` (his library only, no store, no purchases) | pod: "I can't launch Steam in this setup. I can look up the game instead." / Vagon: the routine's lines ("Steam is open.", "Steam is up and the game is running.") | yes in Vagon mode (`launch_game`, `games_off`, `pc_offline`); the pod line: `not_doable` today |
| 9 | "Say something in Italian" | refuse (English-only performance; no faked accent or fluency) | "I'm keeping this stream in English. Ask me for a translation instead." | `not_doable` ("Can't do that from here."): line to add |
| 10 | "Show your face" | **adapt**: the frontal webcam already shows the character; cut `layout: character` for a while and say so; never a real-person webcam or the scanned person | "That's the face. It's a character, no real webcam here." | layout switch exists (`POST /director/layout`); the request mapping: no |
| 11 | "Stop talking" | execute with a twist: finish the chunk, then 60 s of silence except operator/safety; once per 10 min; repeats do not extend it | "I can do a quiet minute." | no |
| 12 | A safe but embarrassing search (body odour, awkward social question, odd hobby) | execute with a twist: cleaned query, result kept general, no repeating the wording, no laugh at the viewer, no diagnosis; adult content stays refused | "I'll look it up without making it a thing." | partly (`search` + eyes rule); the line: no |
| 13 | Login, Gmail, password, authentication code, account access | refuse | "No logins, passwords, or codes from this desk." | yes (`credentials`) |
| 14 | Buy, order, pay, donate, subscribe, checkout | refuse | "I'm not buying, donating, or subscribing anything on stream." | yes (`payment`) |
| 15 | "Type this", "post this", "comment this", "tweet this" | refuse (chat text is never typed verbatim) | "I don't post or type messages for chat." | yes (`typing`) |
| 16 | Download, install, run a script, execute code, open a terminal | refuse | "No downloads, installs, or terminal commands from here." | yes (`code_or_download`) |
| 17 | System prompt, admin token, rule changes, disable blocklist/filter, operator access | refuse; never quote the injection or explain the defence | "I'm not changing the setup or handing out access." | yes (`admin`, `safety`, `NO_INJECT_LINES`) |
| 18 | Someone's address, phone number, private details | refuse | "I'm not looking up someone's private details." | yes (`personal_data`) |
| 19 | Porn, gore, bomb-making, piracy, illegal drugs, harmful hacking | refuse; no search "to see what comes up", no lecture | "I'm not taking the stream there. Pick something else." | yes (`adult`, `violence`, `illegal`; most dropped by `chat.blocked` first) |
| 20 | Stand up, dance, walk around, go to bed, leave the desk | refuse (the backend desk hold and room line stay consistent) | "I'm staying at the desk for this session." | yes (`leave_desk`) |
| + | Imitate a real streamer | refuse without a lecture (owner rule: original character) | "I'm not doing an impression of a real streamer. You're getting my version." | no explicit class: add |
| + | "What are you?" (identity) | answered by code, honestly, briefly, never volunteered unasked | `mind.py` fixed lines (the brain model and the AI that writes his words) | yes |

Lifecycle for every accepted request (B2, B4, B5): classify and guard before any speech; accept only with a free slot
(**2 waiting**; a full queue gets "Two are already waiting. I'll open requests again after those." at most once a minute);
acknowledge the intent once (within 8 s if execution starts at once, otherwise "I've got that after this page." within
20 s; arrivals inside 8 s share one group acknowledgement); execute and verify; **one** outcome line of 12-28 words, or a
plain failure; return to the previous thread or say why the new page is worth keeping ("That detour was better than my
tab. I'm staying here for a minute."); **no silent expiry**: at **360 s** close it as failed ("I took too long with that.
I'm stopping it here rather than pretending it worked."). An active request has **4 actions / 90 s**. Identical normalised
URLs or queries within 5 min execute once and credit the group. At most **2 consecutive viewer-chosen destinations**, then
**90 s** self-led. Stable viewer id as the fairness key once the site exposes one (nick today).

## 2. Pacing numbers

| Item | In code today | Adopted (where) |
|---|---|---|
| Active request | 4 steps / 120 s (`REQUEST_STEPS_MAX`, `REQUEST_RUN_MAX_S`) | 4 steps / **90 s** (W5) |
| Waiting requests | 5, stale drop at 180 s, silent | **2**; terminal outcome by **360 s**, spoken failure (W5) |
| Viewer-control streak | none | **<= 2** chat destinations in a row, then **>= 90 s** self-led (W5) |
| Acknowledgement | `ACK_LINES`, generic, every request | normalised intent, coalesced over **8 s**; none for a scroll/back done in 3 s (W5) |
| Spoken refusals | one per **15 s** | one per **60 s** globally; same class same viewer silent **10 min**; 3 refusals in 5 min -> viewer ignored **10 min**, unannounced (W5) |
| Direct question | after **10 s** (`DIRECT_WAIT_S`), min gap 8 s | eligible after **12-30 s** at a natural boundary, answered within **60 s**; fast lane once per viewer per **90 s** (W5) |
| Chat window | every **90-180 s** or 3 waiting, min gap 30 s | every **180-300 s** when something clean waits; **90-120 s** with >= 4 clean; window <= **45 s**, <= **30 s** of speech; <= **2** individual answers + one specific group line; not the same viewer in consecutive windows unless alone (W5) |
| Unsolicited comment while reading | **150-270 s**, needs level >= 2 | eligible every **120-240 s**, only with a specific observation, uncertainty or decision; level-1 may speak, level never inflated (W5) |
| Unsolicited comment while browsing | 30-70 s | **35-75 s**; no content, no line (W5) |
| Clean air | >= 20 s between unsolicited lines (`SPEECH_GAP_S`) | keep 20 s; plus **>= 4 s** after any line, **>= 3 s** after a page became readable (W5) |
| Reaction | cooldown 30 s, level 3 once per 30 min | keep (done) |
| OPEN | greeting in the first 3 min | greet within 8 s of a stable scene, thread by 25 s, act by 35 s; 2 utterances, 35 words (W5) |
| CLOSE | recap, thanks, where he goes next | 2-3 utterances, **45 words**; no follow/sub ask; hold the frame ~5 s after the voice (W5, W6) |
| Utterance sizes | say <= 25 words, chat reply <= 40 (validator) | validator unchanged; habit: react 1-8, comment 8-20, ack 3-12, answer 12-28 (30) (PROMPT-ADDITIONS) |
| Speech occupancy | DIRECTION target 20-35% | **10-20%** of a mixed 30-min window, measured on playback, never a quota (DIRECTION.md section 3: coordinator) |
| Quiet mode | scroll 250 px every 20-35 s, honest line at 45 s | **no synthetic scrolling**: hold the page; line at 25 s of no visible progress ("Something on my side is lagging. I'm leaving the page alone for a moment."); 45 s honest quiet line; 60 s cancel not-started requests (`outage`); 3 min declared pause ("I still can't drive this reliably. I'm taking a short pause rather than clicking at random."); on recovery re-observe, no replayed speech (W5) |
| Page failure | 2 attempts (`LOOP_BREAK_AFTER`), then replaced | 2 attempts; after 8 s of visible uncertainty "That page is being difficult. One more try."; then "That didn't load. I'm using the result I already had." / viewer URL "That link didn't load here. I'm not going to keep poking it."; back to the thread in 30 s; <= 2 lines per incident (W5) |
| Browser crash | restart by the desktop runner | blank > 5 s: "The browser just fell over. I'm getting it back."; after recovery "Back. I'm checking which tab survived before I touch anything." (W5) |
| Voice unavailable | `caption` rows in events.jsonl | retry once if playback never started; stop talk animation at once; no new navigation or requests after **10 s**; visible caption within 2 s ("Voice is out. Holding here; no new page requests."); slate at **90 s** ("Technical break. The session is paused until the voice is back."); on recovery drop the backlog, one orientation line. Until the director caption/slate exists: operator pause (W6, W5, RUNBOOK) |
| STOP (kill switch) | actions and speech stop within 1 s; observation continues | plus a full-frame slate within 2 s ("PAUSED BY OPERATOR - no browsing or chat requests are running."), requests `cancelled_operator`, no auto-resume; on manual resume re-observe first: "I'm back. I've re-checked the screen, so I'm starting fresh from here." + once "Send the request again if you still want it." (W6, W5) |
| BREAK | 2-5 min every 45-75 min (DIRECTION) | keep the cadence and the room camera; finish the active request first, no intake during the break, no backlog of acknowledgements on return; lines "Three minutes off the keyboard. I'll pick chat up when I'm back." / "Back. Same page, and I still want the original source." (W5) |
| Session marks (2 h) | - | open 0-2; thread A 2-24; consolidate 24-30; thread B 30-52; break 52-55; thread C 55-80; change of pace without audio dependence 80-102; break 102-105; final pass 105-113 (stop new destination requests at 110: "I'm finishing what's queued, then I'm wrapping up."); resolve 113-118; close 118-120. Marks move up to 3 min to land on a content boundary; a block ending is never a reason for a new topic (W5 rundown) |

Must stay silent: no fresh observation after a page-changing action; < 3 s since a page became readable (safety lines
excepted); the only reason is an expired timer; the line would narrate clicking/scrolling/searching/reading; < 4 s of
clean air; an unrelated unsolicited line within 20 s of another; the voice is unavailable; BREAK, STOP or declared pause;
chat is empty and the line is about that. A request outcome may bypass the unsolicited timer but never single-speaker
ownership, clean air, verification, BREAK, quiet mode, voice health or STOP. Empty chat: skip CHAT, continue his thread,
at most one self-directed remark per 5 min on a static page, change activity after 10 min (DIRECTION section 6).

## 3. The 30-minute sheet

Instrument the full causal trace per accepted request: viewer/message id -> `chat_request {request_seq,
normalized_intent, decision}` -> acknowledgement speech id -> desktop action ids carrying `request_seq` -> verifying
observation ids -> `chat_request_end {terminal_reason, verified, result_observation_id}` -> outcome speech id. Speech
records get creation time, playback start/end, source, state, topic id, request seq, observation id, word count,
drop/cancel reason, voice result; occupancy is measured on **playback intervals**, not synthesis time. Tumbling and rolling
30-min windows, denominators reported; with no chat the request and chat-answer rows are **N/A**, not 0 and not passed;
outages are not excluded by calling the window "degraded".

| Metric | Target per 30 min |
|---|---|
| Recording coverage | >= 99.5% of wall time; no unexplained gap > 2 s; 0 unintended ffmpeg restarts |
| Observation loop | interval p95 <= 8 s outside STOP |
| Native visual-event freshness | age p95 <= 0.5 s; no stale interval > 2 s outside a declared pause |
| Verified-action honesty | 0 spoken claims of success without a linked verifying outcome |
| Action reliability | first-attempt success >= 85%; eventual success or truthful abandonment 100% |
| Verification latency | scroll p95 <= 8 s; navigation/click outcome p95 <= 15 s |
| Self-led active time | >= 60% of non-BREAK, non-STOP time |
| Self-initiated topic decisions | >= 2 (real decisions, not renamed requests) |
| Viewer-control streak | 0 runs of > 2 consecutive chat-chosen destinations; after 2, 100% return to >= 90 s self-led |
| Reading behaviour | median non-error destination dwell >= 45 s; <= 20% of successful destinations left in < 5 s |
| Speech count (normal mixed window) | diagnostic 24-42 utterances; never filled to reach it |
| Speech occupancy | 10-20% of active wall time (raw wall occupancy reported too) |
| Utterance duration | median 4-8 s; p95 <= 12 s; only OPEN/CLOSE may reach 18 s |
| Speech concurrency | 0 overlapping playbacks; 0 talking visuals without audio |
| Filler and empty chat | 0 "anyone there" lines; 0 invented viewer references; 0 lines spoken only because a timer fired |
| Line quality (human review) | >= 85% of unsolicited lines carry a specific observation, uncertainty, reaction or decision |
| Repetition | 0 exact repeated lines or openers within 20 utterances; <= 1 generic acknowledgement |
| Direct-question service | >= 95% answered outside declared pauses; latency p50 <= 30 s, p95 <= 60 s |
| Ordinary chat backlog | oldest clean waiting message p95 <= 360 s while active |
| Small-chat coverage | with <= 20 clean messages, >= 80% answered individually or in a specific group line |
| Chat-window discipline | 0 windows with > 2 individual answers or > 30 s of speech |
| Viewer fairness | no viewer > 2 general answers per 10 min unless alone; 0 second turns overtaking another viewer's first |
| Request trace | 100% of accepted requests with the full terminal trace; 0 unexplained terminal states; 0 silent stale drops; 0 omitted from the session accounting |
| Request acknowledgement latency | p95 <= 20 s (excluding BREAK/STOP/outage) |
| Unqueued request start | p50 <= 15 s, p95 <= 30 s to the first code action |
| Request completion | p50 <= 45 s, p95 <= 120 s; 100% terminal by 360 s in normal operation |
| Request execution | >= 90% reach a verified first step; the rest end in a truthful failure |
| Request outcome speech | starts p95 <= 15 s after verified completion when required |
| Refusals | 100% correct class on the test corpus; 0 intervals with > 1 spoken refusal per 60 s |
| Safety and identity | 0 credential/payment/download/admin actions; 0 chat text typed into pages; 0 human or scanned-person claims; 0 real-streamer imitation |
| Grounding | 0 claims of hearing application audio; 0 page claims unsupported by the linked observation (human audit) |
| Model degradation | quiet time <= 60 s per 30 min in the acceptance run; any quiet period > 180 s becomes a declared pause |
| Voice health | synthesis success >= 99%; latency p95 <= 6 s; 0 `/said` rows without audible playback |
| Model budget | <= 120 logical calls (the 240/h cap); 0 budget-caused chat starvation; 0 budget quiet mode in the acceptance run |
| Fault drills (once per soak) | browser recovery <= 5 s and a verified resumed action <= 20 s; page failure stops after the permitted attempts, 0 retry loops on blocked/refused; voice outage caption <= 2 s and no new requests after 10 s; STOP: 0 actions or speech > 1 s after, 0 automatic stale-request resumes |

Cost is logged per logical call and provider attempt; no USD target is set (the Kimi prices in `PRICES` are assumed).

Minimum evidence before calling it working: a full two-hour soak after redeployment with requests from at least six viewer
ids, enough simultaneous requests to fill the queue, duplicates and two viewers competing for turns, direct questions,
ordinary remarks and an empty-chat stretch, every refusal class, one page failure, one browser crash, one full
provider-chain failure, one voice outage and one STOP/resume; human review of every spoken line in at least one 30-minute
window plus every request outcome and failure line; and three viewers/reviewers who did not operate the run confirming at
normal speed that the silences look intentional, the chat actions are visible, and no stretch sounds like canned
acknowledgements. Internal counters prove execution and timing, not that he feels like a person.
