# Decisions on the Kimi consultations of 2026-10-23 (`animation.md`, `stream.md`)

Advice weighed against the owner's rules (original character, no copying a real streamer, chat never changes rules or
credentials, no public stream without his request) and the project's facts. Decision: **adopt** as written, **adapt**
(changed, says how), **reject** (says which rule or fact), **done** (already true today), **defer**. Effort: S < 4 h,
M 4-16 h, L > 16 h. Workers as in PLAN.md (W4 Unreal, W5 agent, W6 director). "done" in the Lands column = applied in
this pass (`scripts/streamer_motion.py`, its tests, MOTION-SPEC.md, ANIMATION-REFERENCES.md, PROMPT-ADDITIONS.md,
CHAT-DECISIONS.md).

Facts the advice did not have:
- F1 The agent sets `chat_until` when a chat answer is dispatched: `chat_addressed` and `speaking` rise on the same tick,
  so the pre-voice read beat exists only if W5 raises `chat_until` when the batch is picked (one line).
- F2 The current native build reads only the six v2 fields (state, gaze, nod, intensity, camera); `motion` is ignored,
  so until W4's work lands a reaction's entry nod is its only visible cue.
- F3 One agent action is one typing block (model cycle >= 2.5 s): typing never resumes within 1.8 s at the agent level.
- F4 `mouth.json` (voice RMS envelope, 25 Hz) already exists: an audio-derived talking envelope is available natively.
- F5 Vagon mode has a Steam launch routine on the owner's own PC (`launch_game`, `--pc-allow-games`, no purchases).
- F6 Code today: say <= 25 words, chat reply <= 40; one spoken refusal per 15 s; 5 waiting requests, 120 s active,
  180 s stale drop; quiet mode scrolls 250 px every 20-35 s; direct question after 10 s; chat batch every 90-180 s.
- F7 The `motion` output schema (`sub01.streamer-motion.v1`) is frozen for this pass: no new keys.

## A. `animation.md`, ranked

| # | Recommendation | Decision | Reason | Lands | Effort |
|---|---|---|---|---|---|
| 1 | Ship the quiet version: cut the ~128 visible events/h to chat glances every 45-105 s, posture holds every 240-420 s, fidgets every 120-260 s; no autonomous stretch | adopt | the first draft stacked plausible behaviours into a busy performance; its desk rates were design, not reference | done (DEFAULTS, tests) | S |
| 2 | Reading head: gain 0.12, +-2 deg yaw / +-1.5 deg pitch, 0.8 s filter, 0.6 deg drift at 0.04 Hz; clicks gain 0.45 | adopt | no eye rig: head motion at fixation rate is a reading bob | done (`reading_gaze_*`, `action_gaze_gain`) | S |
| 3 | Mouse hold 0.8 s; click target 0.7-1.2 s; scroll target 0.35-0.70 s; hold armed once per new target | adopt | 2 s / 5 s holds were stares at stale pointers | done | S |
| 4 | Hands lead 0.50 s, linger 0.70 s, keyboard pause hold 1.8 s | adapt | F3: the pause hold lands as "a resume within 1.8 s is the same episode: no new reach, no lead"; intra-action micro-bursts are native | done | S |
| 5 | Visible hold 15-35 s at 0.28 every 240-420 s; weight shifts 0.05 every 70-140 s over 1.8 s; sag from 720 s ramping over 180 s (0.12, pitch -1) | adopt | pressure-mat shifts are not visible leans; 1200 s was dead code at the 20-min FOCUS cap | done | S |
| 6 | Gestures: left hand, 0.9-1.4 s, strength 0.25-0.45, every 8-14 s (chat) / 14-26 s (talk), first >= 0.45 s after the voice; right hand 15%, never with a pointer in flight | adopt | a seated mouse user is not a free-handed narrator | done | S |
| 7 | Pose contrast: reading 0.30 forward, dry comment 0.12 back, chat answer 0.18 back, message read 0.24; remove `lean_chat` 0.65 | adopt | the brief's reading-forward / talking-back; a 0.65 lunge per answer is a presenter | done (signed channel) | S |
| 8 | Chat anchor 20 deg / -4 deg; Spine2 5% / Neck 30% / Head 65%; dwell 0.8-1.5 s | adopt | 30 deg + 15% shoulders is a conversation off-camera | done + MOTION-SPEC | S |
| 9 | Chat answer: one read beat 1.2-2.2 s, one lens address 1.4-2.4 s with ack nod 0.24, one recheck at 5.5-8 s, 0.35 s hold at voice end; no camera quota, no read/camera/screen cycle | adopt | fixed cycles repeat visibly | done; F1 note for W5 (`chat_until` at batch pick-up) | S |
| 10 | Remove `camera_glance_every_s`, `speech_first_glance_s`: camera looks only for chat, shared reactions, open/close/thanks | adopt | DIRECTION rule 10; a look every 20-40 s is presenter behaviour | done; open/close/thanks = W5 raises `chat_addressed` for those lines | S |
| 11 | Remove periodic talking nods; keep speech-onset 0.28 at +0.12 s and chat ack 0.24; no prosody fields this week | adopt | `voice_playing` has no phrase boundaries; F4: a later native prosody nod can read `mouth.json` | done; W4 later | S |
| 12 | Surprise 2.6 s: back 0.40 in 0.18 s, check 0.45 from 0.45 s, camera 1.15 s for 0.75 s, no nod | adopt | the 2 s version overlapped its own phases | done | S |
| 13 | Laugh: chuckle 2.2-3.0 s, back 0.55, tilt 4-6 deg, camera 0.75 s for 0.8 s, two native 3 Hz torso pulses, no 0.5 Hz breathing pump | adapt | F2: a 0.3 entry nod stays so the current build shows something; breathing 0.34 in recovery | done | S |
| 14 | Think 1.4-2.4 s, yaw 7, pitch up 2, tilt 4-7, `think_chin_p` 0 | adopt | no contact-correct hand asset | done | S |
| 15 | Fidgets: `desk` only; face/headphones/neck/drink/stretch weight 0; unsupported kinds fail closed natively; min 25 s in state, 3 s quiet after a chat edge | adopt | fixed chin/ear points break as soon as the spine moves | done; spec (W4) | S |
| 16 | Breathing 0.20/0.20/0.18/0.28/0.34 Hz; phase accumulation, 30/70 inhale/exhale for speech, no `sin` power shaping | adopt | the agent sends the rate; the wave shape is native | done (rates); spec | S |
| 17 | `state_min_dwell_s` 0.8; the hand channel is not debounced | adopt | 0.5 s did not clear the 0.6 s native debounce | done | S |
| 18 | One signed posture channel `s = lean - lean_back`; the agent emits mutually exclusive poses; reaction/back poses replace the base lean | adopt | two spine distributions cannot be subtracted as rotations | done + spec | S |
| 19 | Smoothers: posture ~0.45 s, voluntary head aim 0.22 s, reading 0.8 s, reaction onset 0.08-0.12 s | adopt | one 0.25-0.4 s smoother for everything was wrong | done (0.22 / 0.8 + rate limits); spec (W4) | S |
| 20 | Lens pitch computed from the camera transform (about 4.2 deg up), aim at the lens itself, acceptance 1 deg | adapt | the v2 gaze field still needs a number for the current build: `camera_pitch_deg` 4.2 from the recipe | done + spec | S |
| 21 | Component-space axes, quaternions, counter-pitch residual removed by the final head pass | adopt | bone-local X is not a portable pitch axis | spec (W4) | M |
| 22 | Explicit supported hand set; no typing+gesture; no left-mouse | adopt | two clips cannot represent more | spec | - |
| 23 | Calibrated contact sockets, two-bone IK + wrist + elbow pole + fingers; correction < 30 mm, fail > 60 mm; no 12 cm rule | adopt | a wrist pull is not a hand solution | spec (W4 rank 3) | M |
| 24 | The 24-phase matcher picks the body phase only; arms get timed paths and contact pins during the reach | adopt | a crossfade cannot be a reach | spec (W4 rank 4) | M |
| 25 | Hips delta <= 0.5 mm / 0.2 deg for additive layers | adopt | 8 cm is a whole-clip audit, not a layer tolerance | spec acceptance | - |
| 26 | Receipts carry values and one-shot ids (torso angle, head error, IK mm, phase, last accepted action/reaction) | adopt | field names alone cannot diagnose a pop | spec acceptance (W4) | S |
| 27 | Nod rearm at <= 0.02, one 0.75 s envelope per rise | adopt | repeated equal strengths must work | spec; the agent's 1 s decay already crosses it | - |
| 28 | `motion.action_seq`, `motion.reaction` | defer | F7; needs `sub01.streamer-motion.v2` and the native parser together; the director detects new targets internally meanwhile | W4+W5 next schema bump | S |
| 29 | `mouse_state` "mouse" | done (module default) | the agent still passes "reading" until the sitting-loop build is confirmed on the pod | W5 flag | - |
| 30 | Ranked native list 1-10 with hours; do not start rank 10 (authored face/drink clips) this week | adopt | replaces MOTION-SPEC section 3; the old 2-4 h estimates were optimistic | spec (W4) | L |
| 31 | Third clip: a 12 s desk contact-and-transition take with markers, never played as a loop | adopt | reach and settle are the asset gap | spec 3.3; owner/W4 | L |
| 32 | Webcam recipe: fixed camera, 0.95 m, lens 70 mm above the eye line, -10 deg, 40 deg vertical FOV, 16:9, head 20/36/53/67%; frame acceptance at both pose extremes | adopt | both poses stay in frame, no reframing feedback loop | spec 4 (W4) | S |
| 33 | Ten situational rules | adopt | all ten land in the director where the inputs allow (rule 6's pre-voice read needs F1) | done | S |
| 34 | Final 10-minute pod acceptance through the real webcam shot | adopt | the skeletal view hides the frame | spec acceptance | - |
| 35 | Label the desk rates as design; tally real desk footage before calling anything reference-matched | adopt | honest provenance | REFERENCES sections 1, 3, 5 | - |
| 36 | A static face in a tight shot remains a limitation | done | known (no face rig; LIPSYNC-OPTIONS.md) | - | - |

## B. `stream.md`, ranked

| # | Recommendation | Decision | Reason | Lands | Effort |
|---|---|---|---|---|---|
| 1 | Bounded detours: never more than 2 consecutive viewer-chosen destinations without 90 s self-led activity | adopt | the owner wants SUB-01 to lead; today a viewer can chain the session | W5 `Requests`; CHAT-DECISIONS | M |
| 2 | Active request 4 actions / 90 s; 2 waiting; every accepted request terminal within 360 s or a spoken failure; no silent stale expiry | adapt | steps 4 already; F6: 120 -> 90 s, 5 -> 2 waiting, the 180 s stale drop becomes a spoken "I took too long" | W5 | S |
| 3 | Stable viewer id (keyed hash) as the fairness key | adapt | the site chat exposes nicks today; the id needs the backend first | backend + W5 | M |
| 4 | <= 2 speeches per request, usually 1; a scroll/back done within 3 s needs no spoken ack; acknowledge the normalised intent, never raw text | adopt | `ACK_LINES` are generic ("On it") today | W5 | S |
| 5 | Do not execute when the 6-word cut or an ambiguous referent changes the meaning: one short clarification | adapt | keep the cleaner; add the clarification line and expose the query to the ack | W5 | S |
| 6 | Refusals: one spoken per 60 s, same class same viewer silent for 10 min, 3 refusals in 5 min -> that viewer ignored 10 min | adopt | abuse must not be a reliable way to make him speak (F6: 15 s today) | W5 | S |
| 7 | A level-1 observation may be spoken; level is never inflated for permission | adopt | the "level >= 2 while reading" rule teaches exaggeration | W5 pacing; PROMPT-ADDITIONS | S |
| 8 | Speech occupancy 10-20% of a mixed 30-min window, a measurement band, not 20-35% | adopt | long speech exposes the static face and rewards filler | DIRECTION.md section 3 (coordinator) | - |
| 9 | Stop quiet-mode scrolling; hold the last verified page, honest status line | adopt | a browser scrolling with no decision process looks possessed | W5 `QUIET_SCROLL_S` | S |
| 10 | Director-owned caption/slate path; until it exists a voice outage pauses the session | adopt | `events.jsonl` captions reach nobody | W6 + RUNBOOK | M |
| 11 | One interruption rule: direct questions after 12-30 s (target 60 s), fast lane once per viewer per 90 s; windows every 180-300 s (90-120 s with >= 4 clean), <= 45 s / 30 s of speech, <= 2 individual answers | adapt | F6: 10 s / 90-180 s / 3 messages today; keep "never cut a verification or a sentence" | W5; CHAT-DECISIONS pacing | M |
| 12 | Group acknowledgement names the shared content | adopt | "lots of great messages" is a vending machine | PROMPT-ADDITIONS | - |
| 13 | Sizes: react 1-8 words, comment 8-20, ack 3-12, answer 12-28 (max 30), open 35, close 45 | adapt | the validator's hard caps stay 25/40 (F6); the prompt carries the usual sizes and the 30 as his habit | PROMPT-ADDITIONS | - |
| 14 | The must-stay-silent list (no fresh observation, < 3 s after a page, timer-only, narration, < 4 s clean air, voice down, BREAK/STOP, empty chat) | adopt | matches DIRECTION rule 1 and the pacing gates | PROMPT-ADDITIONS; W5 (clean air 4 s) | S |
| 15 | Empty chat: skip CHAT, no "anyone there", <= 1 self remark per 5 min, change activity after 10 min | done | DIRECTION section 6 | - | - |
| 16 | System-prompt additions | adapt | rewritten in the existing prompt's voice ("he"), duplicates of existing rules cut, identity lines left to code (`mind.py` answers them) | PROMPT-ADDITIONS (W5 pastes) | S |
| 17 | Two-hour session with two 3-min desk breaks, pacing marks, intentional transition lines | adapt | DIRECTION keeps BREAK 2-5 min every 45-75 min and the room camera; Kimi's "finish the active request, no intake, no backlog on return" and the lines are taken; "he never leaves the desk" is the backend's life logic, not a rule for the agent | CHAT-DECISIONS; W5 rundown (DECISIONS.md B13) | M |
| 18 | Page/browser failure: 2 attempts, one line after 8 s, abandon with a plain line, back to the thread in 30 s | adopt | `LOOP_BREAK_AFTER` 2 exists; the lines and the 30 s return are new | W5 | S |
| 19 | Slow model: silence to 25 s, one line, no "thinking" filler; quiet mode cancels not-started requests at 60 s, declared pause at 3 min | adopt | honest, bounded | W5 | S |
| 20 | Voice outage: retry once if playback never started, stop talk animation, no new requests after 10 s, slate at 90 s, discard the backlog on recovery | adopt | with 10: until the slate exists, operator pause | W5 + W6 | M |
| 21 | STOP as viewers see it: full-frame "PAUSED BY OPERATOR" slate within 2 s, requests `cancelled_operator`, re-observe before resuming | adopt | STOP is not a privacy shutter (DECISIONS.md B2 safety slate) | W6 + W5 | M |
| 22 | Twenty request decisions | adapt | 17 adopted as written; #8 Steam executes through the Vagon launch routine when `pc` mode is on (F5), refused on the pod; #10 face: the frontal webcam is the character already, so a `layout: character` cut plus the line; identity/impression lines stay code's | CHAT-DECISIONS | S |
| 23 | "Stop talking": a 60 s quiet interval, once per 10 min | adopt | one viewer gets a pause, not control | W5 | S |
| 24 | Never claim to hear tab audio | adopt | `--mute-audio` is hard-coded today; revisit when the audio chain (DECISIONS.md A14) lands | PROMPT-ADDITIONS | - |
| 25 | Metrics: full causal trace per request, playback-interval occupancy, 30-min windows with denominators, N/A when no chat | adopt | counters today prove execution, not pacing | CHAT-DECISIONS; W5 speech/request records | M |
| 26 | Per-30-minute targets | adopt | the acceptance sheet | CHAT-DECISIONS | - |
| 27 | Two-hour soak with 6 viewer ids, every refusal class, each failure once, three non-operator reviewers | adopt | internal counters do not prove he feels like a person | RUNBOOK (coordinator), `streamer_rehearsal.py` | M |
| 28 | The rehearsal does not prove the new request policy; redeploy and rehearse first | done | DECISIONS.md B1 | - | - |
| 29 | No USD target from the supplied material | done | PRICES for Kimi are assumed (AGENT.md) | - | - |
| 30 | Imitating a real streamer is refused without a lecture | adopt | owner rule, with Kimi's line | CHAT-DECISIONS | - |
