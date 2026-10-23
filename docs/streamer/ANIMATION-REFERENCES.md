# SUB-01 at the desk: animation reference study

Status: draft for engineering, 2026-10-23. Private project. Companion to DIRECTION.md (character, rhythm) and
MOTION-SPEC.md (native fields). Implemented as numbers in `scripts/streamer_motion.py` (`DEFAULTS`), checked by
`tests/test_streamer_motion.py`.

Source tags like [K1] point at the list at the end: (F) the page or PDF text was read, (S) only a search summary was
seen. This is a study of behaviour, not of a person: nothing here copies anybody's identity, catchphrases or jokes.

## 1. What could and could not be verified

The owner asked for Kai Cenat and similar streamers as references for what a streamer actually does at the desk. Video
cannot be watched from here, so the study used what exists in text:

- Written accounts of specific clips [K1][K2][K3][K7] and profile pieces [K4][K5][K6][K9]. They describe the big beats
  (bursting into laughter, startling out of the chair, covering the mouth, going still) but never the ordinary desk
  behaviour: nobody writes down how often he looks at the chat monitor or how he holds the mouse while reading. No
  setup tour confirms his monitor layout; most of his gear is out of frame [K8].
- Field research on streamers [R2] and the earlier DIRECTION.md sources, which describe the pattern (glances at chat
  interwoven with the game, silence while focused, reading messages verbatim then reacting) without counts per minute.
- Measured human behaviour at a desk and in conversation, which gives the only hard numbers: head nods in speech [R1],
  posture shifts per hour [R3][R4], breathing while speaking [R5], where to look for perceived eye contact [R6], when
  the head joins an eye movement [R7], face touching per hour [R8], attention over a web page [R9], reading eye movements
  [R10], typing bursts and pauses [R11], gesture rates [R13], and the advice given to streamers about posture and the
  second screen [R14][R15][R16][G1].

So every timing below is a triangulation: a qualitative description of what streamers do, a measured human rate for how
often people do it, and a design choice marked **(design)** where neither exists. Confidence per row: **high** = measured
in a comparable task, **mid** = described qualitatively plus a related measurement, **low** = inference or design.

## 2. What the reference streamers do (qualitative)

| Observation | Evidence | Take for SUB-01 |
|---|---|---|
| The baseline of a reaction streamer is neutral watching; the big beats are rare punctuation. Kai Cenat's style is "reactive, physical, and rooted in genuine emotion", "the loudest streamer on the internet", with facial expressions that "launched thousands of memes" [K4]; the DIRECTION.md sources call it manic escalation [K9]. | K4 (F), K9 (F) | Keep the structure (neutral baseline, discrete beats), invert the volume: understated, proportionate, seated. |
| Laughter is the most frequent big beat: "burst into laughter" then "promptly hid himself under the table" [K1]; "Explodes in Laughter" [K3]. | K1 (F), K3 (F) | A laugh is a lean back with a head tilt and a look to the camera, 1.5-3 s. He never leaves the chair or the frame. |
| Startles move the body: "initially enthralled", then the sound effect "startled him", he "got 'scared' and left his chair" [K2]; "visibly reacted with fear" [K7]; in a horror jump scare he "covers his mouth and stares in disbelief" and in another clip jumps "out of his chair" [K3, search summaries only]. | K2 (F), K7 (S), K3 (S) | Surprise = head back for half a second, then in towards the screen to check, a glance to the camera to share it. No chair leaving, no mouth covering (no face rig, and it is his gesture). |
| Stillness exists and reads as strong: "A still body in a loud room" during a quiet guest moment [K4]. | K4 (F) | Silence and stillness are a state, not a gap (DIRECTION.md rule 1). |
| The grin "lights up the livestream before he even says a word" [K5]: much of the expressiveness is facial. | K5 (F) | The mesh has no face rig: mood has to ride on posture, head, hands and timing. |
| Streamers "interweave attention to the participation of their audience (e.g. glances at the chat stream) with attention to the game"; spotlight streamers "fall silent while playing", "quiet and focused ... especially in moments of tension"; chat is handled by paired "reading" (verbatim, terse, no usernames) and "reaction" practices with a "tight temporality" between a message and its uptake [R2]. | R2 (F) | Chat is glanced at, not stared at; an answer is read-then-react; reading and reacting are visibly two phases. |
| Guides place chat on a second monitor so the streamer can "glance back and forth between monitors without moving your gaze too far away from your webcam" [R16]; a chat display far to the side makes the streamer keep pulling the face away from the camera [R15]. | R16 (S), R15 (S) | The chat anchor is a head turn of about 30 degrees to one side, brief, and the face comes back to the lens. |
| On-camera posture advice: sit upright, head level, monitor at eye level; a "leaning in" pose, slightly forward towards the camera, for presence [R14]. | R14 (S) | Lean in when addressing viewers; upright-to-slightly-forward while reading. |
| Perceived eye contact is strongest when looking about 2 degrees below the lens, with a tolerance of about 5 degrees downward [R6]. | R6 (S) | "Look at camera" aims the head at the lens; the native layer may bias the eyes a hair below it. |
| xQc: chat gets restless when he talks too much over a clip; many viewers keep reaction streams in the background [X1]. | X1 (F, DIRECTION S11) | Long quiet reading is normal; motion during it must stay small so that it does not look like the stream froze. |

## 3. Catalogue of desk behaviours, with timing

Columns: what happens, how long / how often, what triggers it, the evidence behind the number, confidence, and how
SUB-01 does it (the `DEFAULTS` key in `scripts/streamer_motion.py`).

| # | Behaviour | Duration / frequency | Trigger | Evidence | Conf. | SUB-01 (`DEFAULTS`) |
|---|---|---|---|---|---|---|
| A1 | **Reading posture**: head nearly still, eyes sweep the lines, small lean towards the monitor, mouse hand on the mouse, other hand resting. | Holds for the whole FOCUS state (3-12 min); the head follows the text only partly: shifts under 20-25 deg are made by the eyes [R7]; fixations last 225-250 ms and saccades 7-9 letters [R10], far below what a head can show. | New page, long text. | R7 (S), R10 (S), R2 (F) "quiet and focused" | high | `lean_by_state.reading 0.3`, `reading_gaze_gain 0.55`, head wander 0.6 deg; the eyes are not animated (no rig). |
| A2 | **Scroll rhythm**: a short wheel burst, then 10-30 s of reading; most attention stays near the top of a page (57% of viewing time above the fold, 74% in the first two screens [R9]). The mouse hand stays on the mouse between scrolls. | The agent scrolls every 14-28 s while reading (AGENT.md). Mouse hold 2 s per scroll. | Reading. | R9 (S); hand placement **(design)** | mid | `mouse_hold_s 2.0`; the mouse hand stays until 90 s without pointer use (`mouse_hand_rest_after_s`). |
| A3 | **Typing**: both hands move to the keyboard a beat before the first key, type in bursts of 1-4 s, pause, look at the result. Bursts are delimited by pauses of 1 s or more [R11]; a search query is 2-5 words. | Hands lead by 0.3 s, linger 0.6 s after the last character, then return to mouse/rest. | `type`, `search` actions. | R11 (S); lead/linger **(design)** from clip crossfade 0.24 s | mid | `hands_lead_s 0.3`, `hands_linger_s 0.6`; state `typing` only after the hands arrived. |
| A4 | **Click / navigate**: mouse hand active, gaze to the target, a small lean in when the target is small; back to reading after the page settles. | 2 s hold per action; gaze holds the target 5 s. | `click`, `navigate`, `scroll`. | Agent's own `attention_of`; **(design)** | mid | `mouse_hold_s`, `target_hold_s 5.0`; `mouse_state` = `mouse` (sitting loop) or `reading` fallback. |
| A5 | **Mouse hand drifts** when nothing is clicked for a long time: to the desk, the chin, the lap. | After ~90 s without a pointer action; back on the mouse at the next scroll. | Long static read, waiting. | Face touching 23/h [R8]; posture shifts 18-22/h [R4] | mid | `mouse_hand_rest_after_s 90`. |
| A6 | **Idle / waiting**: page loading, deciding what to do: lower lean, more fidgets, a wandering gaze. | Seconds to a minute. | `none` action, no speech. | **(design)** | low | `lean_by_state.idle 0.15`, `idle_gaze_gain 0.3`. |
| A7 | **Posture shift in the chair**: upright to leaned back and back again. | Office workers shift 18-22 times per hour on a pressure mat [R4]; here one visible shift every 150-300 s with a 20-60 s leaned-back hold (the smaller shifts are the fidgets A19). | Timer; never during a reaction or a chat answer. | R4 (S), R3 (F) | high (rate), mid (shape) | `posture_shift_every_s (150, 300)`, `posture_back_s (20, 60)`, `posture_back_amount 0.35`. |
| A8 | **Hand gestures while talking**: the free hand; the mouse hand stays unless he is really addressing someone. | Free-handed narrators gesture 11-22 times per 100 words [R13]; seated with a mouse far fewer: one every 6-14 s while answering chat, every 12-30 s while commenting on the page; 0.8-1.8 s each. | Speech. | R13 (S); seated rates **(design)** | mid | `gesture_every_chat_s`, `gesture_every_talk_s`, `gesture_s`, `gesture_right_hand_p 0.5`. |
| A9 | **Lean in to the webcam when addressing viewers**. | Within 0.6 s of starting the answer; relaxes over 1.4 s after it. | `chat_addressed`. | R14 (S) leaning-in pose; R15 (S) | mid | `lean_chat 0.65`, `lean_chat_reading 0.45`, `lean_rise_s 0.6`, `lean_fall_s 1.4`. |
| A10 | **Glance to the chat and back** without stopping what he does. | Every 30-90 s for 1-3 s while reading or idle and silent; none while typing or reacting. | Timer. | R2 (F) "glances at the chat stream", R16 (S); rate **(design)** | mid | `chat_glance_every_s (30, 90)`, `chat_glance_s (1, 3)`, `chat_yaw_deg 20` + `look_to_chat`. |
| A11 | **Answering a chat message**: read it first (head to the chat side), then turn to the lens and speak, glance back to the chat, repeat. First look up carries a small nod. | Read 1.2-2.5 s; camera 2-4 s; chat 1.5-3 s; about 60% of the answer is to the camera. | `chat_addressed` rising edge. | R2 (F) reading/reaction pairing; R1 (F) nods as agreement; split **(design)** | mid | `chat_read_first_s`, `chat_camera_s`, `chat_screen_s`, `chat_ack_nod 0.3`. |
| A12 | **Eye contact with the camera while talking** to nobody in particular (a comment on the page). | 1-2 s every 20-40 s; the first one 2-10 s after speech starts. | Speech without `chat_addressed`. | R6 (S) where to look; DIRECTION rule 10; rate **(design)** | low | `camera_glance_every_s (20, 40)`, `camera_glance_s (1, 2)`, `speech_first_glance_s (2, 10)`, `camera_pitch_deg 8`. |
| A13 | **Micro head motion while talking**: nods at the end of phrases, a small nod when an utterance starts; nods are "the head motion type which occurred with most frequency", "at the last syllable of the phrases, in strong phrase boundaries", often "accompanied by a small upward motion before the usual down-up motion", the first of a series larger than the rest [R1]. | Phrase-boundary nods every 2.5-5 s, strength 0.12-0.3; speech-start nod 0.4. | Speech. | R1 (F) | high (where), mid (rate) | `talk_nod_every_s (2.5, 5)`, `talk_nod_strength (0.12, 0.3)`, `speech_start_nod 0.4`; the native talking cadence (0.9/0.6 deg) stays. |
| A14 | **Surprise**: head back, then in towards the screen to check, a look to the lens to share it. Phrases of surprise come with "upward (fu, ud) or tilt motions" [R1]. | 2.0 s total; back 0.6 s; camera share from 0.5 s for 1.5 s. | `reaction=surprise` (agent level 2). | R1 (F), K2 (F), K3 (S) | mid | `surprise_s 2.0`, `surprise_back_amount 0.45`, `surprise_camera_at_s 0.5`, nod 0.6. |
| A15 | **Laugh**: lean back, head tilt, breathing fast, a look to the camera, recover. | 1.5-3 s; tilt 5-9 deg; camera from 0.8 s for 1.5 s; breathing 0.5 Hz. | `reaction=laugh` (agent level 3, at most once per 30 min). | K1 (F), K3 (F) | mid | `laugh_s (1.5, 3)`, `laugh_back_amount 0.8`, `laugh_tilt_deg (5, 9)`, `laugh_camera_at_s 0.8`, `breath_laugh_hz 0.5`. |
| A16 | **Think**: head tilt, eyes off the screen (up and to a side), maybe a hand to the chin. Tilts "occurred in almost all dialog acts" and at boundaries where the speaker is thinking [R1]. | 1.5-3 s; tilt 6-10 deg; chin hand 50%. | `reaction=think` (agent level 1). | R1 (F) | mid | `think_s (1.5, 3)`, `think_tilt_deg (6, 10)`, `think_gaze_yaw_deg 8`, `think_chin_p 0.5`. |
| A17 | **Returning upright** after a leaned-back hold: a re-seat, hands back where they were. | End of A7's hold. | Timer. | R3 (F), R4 (S) | mid | Part of A7 (slew back over `lean_fall_s`). |
| A18 | **Slump after long focus**: "all workers appeared to assume slumped sitting postures after 20 minutes of sitting" [R3]; a shift resets it. | After 20 min in one focus state until the next shift. | `seconds_in_state >= 1200`. | R3 (F) | high | `focus_slump_s 1200`, `slump_back_amount 0.15`, pitch -2 deg. |
| A19 | **Fidgets with the free hand**: face/chin, headphones, neck, a drink. People touch their face 23 times per hour [R8]; guides tell streamers to keep drinks within reach [G1]; the headphone adjust is common on stream but unverified in text. | One every 40-110 s (roughly 30-90/h), 1.2-3 s each, a drink 3-5 s; none while typing, reacting, or in the first 2 s of a chat answer. | Timer; the free hand only (the mouse hand stays). | R8 (S), G1 (S); mix **(design)** | mid | `fidget_every_s (40, 110)`, `fidget_weights`, `fidget_s`, `fidget_quiet_after_chat_s 2`. |
| A20 | **Stretch**: both arms up, lean back, head up, then re-seat. Guides advise standing and walking a few minutes every hour or two [G1]; leaving the desk is DIRECTION's BREAK (every 45-75 min). | 3-6 s every 10-20 min, only when silent and not typing. | Timer. | G1 (S); rate **(design)** | low | `stretch_every_s (600, 1200)`, `stretch_s (3, 6)`. |
| A21 | **Going quiet and reading**: no speech, no camera, head still, chat glances only; streamers "fall silent", "quiet and focused" [R2]; talking over content annoys viewers [X1]. | Minutes (FOCUS 3-12 min, cap 20). | Reading. | R2 (F), X1 (F) | high | A1 + A10; `look_at_camera` is 0 the whole time (tested). |
| A22 | **Transitions**: one body state at a time, no flapping; hands lead clips. | At most one state change per 0.5 s (native debounce 0.6 s, crossfade 0.24 s). | Any. | Native README; **(design)** | high | `state_min_dwell_s 0.5`. |
| A23 | **Breathing**: longer cycles while speaking (5.45 s vs 3.68 s listening: 11.0 vs 16.3 per minute), a "sawtooth" of short inhalation and long exhalation [R5]; quiet breathing about 12 per minute. | Rest 0.22 Hz, reading 0.20, talking 0.18, surprise 0.30, laugh 0.50. | State. | R5 (F) | high | `breath_*_hz`; the native layer breathes at a fixed 0.22 today. |
| A24 | **Blinking** (not implementable without a face rig): about 15 per minute relaxed, lower when reading on a screen, incomplete blinks more frequent [R12]. | Noted for a future rig. | Reading. | R12 (S) | mid | None. |

## 4. SUB-01's own direction (what he does and does not do)

Character (DIRECTION.md section 2): curious, ironic, spontaneous, focused, able to be silent. The body says the same.

**He does**
- Read with his whole attention: slight lean in, head still, mouse hand parked on the mouse, the other hand resting or
  slowly fidgeting; one scroll at a time. Stillness is content, not a bug.
- Glance at the chat the way one glances at a clock: a brief head turn every half minute to minute and a half, then back.
- Answer chat in two visible phases: read (head to the chat side), then turn to the lens, lean in a little, small nod,
  speak; glance back to the chat mid-answer. About 60% of an answer is to the camera; the rest is to the message.
- Meet the camera briefly while commenting on a page (1-2 s every 20-40 s), never stare at it.
- React once, proportionately, with the body: a laugh is a lean back and a tilt; surprise is head back then in to check;
  thinking is a tilt and eyes off the screen. Each lasts seconds and ends in the reading posture.
- Shift in the chair every few minutes, sag a little after twenty minutes of one thing, stretch rarely, touch his face,
  adjust the headphones, drink.
- Breathe slower while talking than while listening; nod at the ends of phrases.

**He does not**
- Leave the chair, hide, stand, dance, throw his hands up, cover his mouth or face the camera for a long time: the
  escalating beats of the reference streamers are theirs, and the frame is a desk.
- Perform at the camera when nobody is addressed: no sustained eye contact, no presenter posture.
- Move his head with the text: eyes read, the head drifts.
- Fidget while typing, during a reaction, or in the first seconds of a chat answer.
- Flap between states: hands move first, then the clip; one change per half second at most.
- Mirror a face he does not have: no lip sync, no eyebrows; the mood is in posture, head, hands and timing.

## 5. Open points for a later pass

- Per-streamer desk statistics do not exist in text; if the owner can supply a few clips, a 10-minute tally sheet
  (glances to chat, to camera, scrolls, posture shifts, fidgets, with timestamps) would replace the design rates above.
- The chat anchor direction (which side, how far) is a scene decision; MOTION-SPEC.md proposes +30 deg yaw to his right.
- The mouse state: `mouse` now plays the sitting loop (README), so the module defaults to it; `mouse_state="reading"`
  keeps the rehearsal workaround if the clip review is still open.

## Sources

Streamers (clip and profile descriptions)
- K1 (F) https://meaww.com/kai-cenat-hides-under-the-table-in-reaction-to-kani-rosis-lie-detector-video-during-livestream
- K2 (F) https://meaww.com/kai-cenats-funny-reaction-to-high-nicki-minajs-sound-effect-leaves-internet-in-stitches-he-switched-vibes-so-fast
- K3 (F page, S for the quoted clip summaries) https://www.snapchat.com/topic/kai-cenat-reacts and https://www.snapchat.com/topic/kai-cenat-stream-reaction
- K4 (F) https://9takes.com/personality-analysis/kai-cenat
- K5 (F) https://www.revolt.tv/article/kai-cenat-best-facial-expressions
- K6 (F) https://en.wikipedia.org/wiki/Kai_Cenat
- K7 (S) https://meaww.com/internet-questions-grown-man-kai-cenat-after-seeing-his-dramatic-reaction-to-mice-on-kai-n-speed-show
- K8 (S) https://www.streamscheme.com/kai-cenat-gaming-setup/
- K9 (F, DIRECTION.md S1) https://time.com/collections/time100-creators-2025/7299142/kai-cenat/
- X1 (F, DIRECTION.md S11) https://www.dexerto.com/entertainment/xqc-responds-to-backlash-over-his-reaction-videos-2229977/

Research and guides
- R1 (F, PDF text) Ishi, Ishiguro, Hagita, "Analysis of head motions and speech in spoken dialogue", Interspeech 2007. https://www.isca-archive.org/interspeech_2007/ishi07_interspeech.pdf
- R2 (F, PDF text) Flores-Saviaga et al., "Audience and Streamer Participation at Scale on Twitch", 2020. https://arxiv.org/pdf/2012.00215
- R3 (F, PDF text) Akkarakittichoke, Janwantanakul, "Seat Pressure Distribution Characteristics During 1 Hour Sitting in Office Workers With and Without Chronic Low Back Pain", Safety and Health at Work 8 (2017) 212-219. https://koreascience.or.kr/article/JAKO201718155358886.pdf
- R4 (S) Roynarin et al. 2024 and the Chulalongkorn thesis on postural-shift frequency (18-22 shifts/h; 20-30/h less discomfort than 10/h). https://digital.car.chula.ac.th/chulaetd/73932
- R5 (F, PDF text) Werner, Trouvain, Fuchs, Möbius, "Exploring the presence and absence of inhalation noises when speaking and when listening", ISSP 2020. https://www.coli.uni-saarland.de/~trouvain/docs/Werner_et_al_2021.pdf
- R6 (S) "Don't Look at the Camera: Achieving Perceived Eye Contact", 2024 (about 2 deg below the lens). https://arxiv.org/abs/2404.17104 ; Chen, "Design of a Video Auditorium" (about 5 deg downward tolerance). https://hci.stanford.edu/seminar/abstracts/01-02/020517-chen.html
- R7 (S) Eye-head coordination: head contributes little to gaze shifts under 20-25 deg; eyes dominate 20-50 deg in seated/indoor behaviour. https://arxiv.org/pdf/2406.06300 ; (F, animal data only) https://pmc.ncbi.nlm.nih.gov/articles/PMC1890377
- R8 (S) Kwok, Gralton, McLaws, "Face touching: a frequent habit that has implications for hand hygiene", AJIC 2015 (23 touches/h). https://pubmed.ncbi.nlm.nih.gov/25637115/
- R9 (S) Nielsen Norman Group scrolling and attention (57% of viewing time above the fold, 74% in two screens), as summarised by https://uxmatters.com/mt/archives/2020/11/debunking-the-myth-of-the-fold.php
- R10 (S) Eye movements during reading (fixations 225-250 ms, saccades 7-9 letters, 10-15% regressions). https://sk.sagepub.com/ency/edvol/embed/encyclopedia-of-the-mind/chpt/eye-movements-during-reading
- R11 (S) Typing bursts delimited by pauses >= 1 s. https://digitalcommons.usu.edu/computer_science_stures/23 ; pauses of 15-180 s as planning. https://research.aalto.fi/en/publications/pausing-while-programming-insights-from-keystroke-analysis/
- R12 (S) Blink rate on screens. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8913463/ ; https://jhsmr.org/index.php/jhsmr/article/view/1097
- R13 (S) Graziano, Gullberg: gesture rates per 100 words (Italians about 22, Swedes about 11). https://3quarksdaily.com/?p=251510
- R14 (S) Streaming poses: upright, "leaning in" towards the camera. https://grandavehousing.calpoly.edu/news/best-streaming-poses-how-to (unreachable at fetch time)
- R15 (S) A chat screen far to the side pulls the face from the camera. https://evezone.evetech.co.za/deep-dives/second-screen-for-chat-cheapest-options-in-sa
- R16 (S) Second monitor for chat; glance without leaving the webcam. https://restream.io/blog/how-to-use-webcam/
- G1 (S) Streamer wellbeing guides: breaks every hour or two, drinks within reach, stretch. https://streamlabs.com/content-hub/post/mental-health-for-live-streamers ; https://www.nspcc.org.uk/globalassets/documents/support-us/fundraise-with-us/press-play-for-the-nspcc/streaming-toolkit/wellbeing-guide.pdf
