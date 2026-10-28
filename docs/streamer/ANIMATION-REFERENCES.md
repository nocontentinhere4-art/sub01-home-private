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

**Correction after the Kimi review (2026-10-23, docs/streamer/kimi/animation.md; decisions in
kimi/DECISIONS-ANIMATION-STREAM.md; rows marked (K) below).** This is not yet a reference study of desk motion: the
streamer sources establish the large public beats, not ordinary sitting, mouse use, chat glances or typing, and most of
the hard numbers come from other tasks and populations. The first draft also stacked individually plausible behaviours
into a budget of about 128 visible events an hour during silent reading (one every 28 s) before gestures and camera
looks, which would read as busy, timed and head-led. The rates in section 3 are therefore the reduced shipping values,
labelled design, and the result must not be described as reference-matched until actual desk footage has been tallied
(section 5). Two limits stay explicit: with no eyes, jaw or face shapes, "gaze" here means head aim, and a static face in
a tight webcam shot remains a limitation whatever the body does.

## 2. What the reference streamers do (qualitative)

| Observation | Evidence | Take for SUB-01 |
|---|---|---|
| The baseline of a reaction streamer is neutral watching; the big beats are rare punctuation. Kai Cenat's style is "reactive, physical, and rooted in genuine emotion", "the loudest streamer on the internet", with facial expressions that "launched thousands of memes" [K4]; the DIRECTION.md sources call it manic escalation [K9]. | K4 (F), K9 (F) | Keep the structure (neutral baseline, discrete beats), invert the volume: understated, proportionate, seated. |
| Laughter is the most frequent big beat: "burst into laughter" then "promptly hid himself under the table" [K1]; "Explodes in Laughter" [K3]. | K1 (F), K3 (F) | A laugh is a lean back with a head tilt and a look to the camera, 1.5-3 s. He never leaves the chair or the frame. |
| Startles move the body: "initially enthralled", then the sound effect "startled him", he "got 'scared' and left his chair" [K2]; "visibly reacted with fear" [K7]; in a horror jump scare he "covers his mouth and stares in disbelief" and in another clip jumps "out of his chair" [K3, search summaries only]. | K2 (F), K7 (S), K3 (S) | Surprise = head back for half a second, then in towards the screen to check, a glance to the camera to share it. No chair leaving, no mouth covering (no face rig, and it is his gesture). |
| Stillness exists and reads as strong: "A still body in a loud room" during a quiet guest moment [K4]. | K4 (F) | Silence and stillness are a state, not a gap (DIRECTION.md rule 1). |
| The grin "lights up the livestream before he even says a word" [K5]: much of the expressiveness is facial. | K5 (F) | The mesh has no face rig: mood has to ride on posture, head, hands and timing. |
| Streamers "interweave attention to the participation of their audience (e.g. glances at the chat stream) with attention to the game"; spotlight streamers "fall silent while playing", "quiet and focused ... especially in moments of tension"; chat is handled by paired "reading" (verbatim, terse, no usernames) and "reaction" practices with a "tight temporality" between a message and its uptake [R2]. | R2 (F) | Chat is glanced at, not stared at; an answer is read-then-react; reading and reacting are visibly two phases. |
| Guides place chat on a second monitor so the streamer can "glance back and forth between monitors without moving your gaze too far away from your webcam" [R16]; a chat display far to the side makes the streamer keep pulling the face away from the camera [R15]. | R16 (S), R15 (S) | The chat anchor is a head turn of about 20 degrees to one side and 4 degrees down, brief (0.8-1.5 s), and the head comes back to the screen; 30 degrees with a shoulder turn looked like a conversation off-camera (K). |
| On-camera posture advice: sit upright, head level, monitor at eye level; a "leaning in" pose, slightly forward towards the camera, for presence [R14]. | R14 (S) | Inverted for him (K): reading is the forward pose (0.30), speech releases the body slightly back (0.12, chat answer 0.18); engagement comes from the lens aim and one acknowledgement nod, not from a forward lunge per answer. |
| Perceived eye contact is strongest when looking about 2 degrees below the lens, with a tolerance of about 5 degrees downward [R6]. | R6 (S) | The 2-degree rule is about eyes; this rig has none, so "look at camera" aims the head at the lens itself, within 1 degree (K). |
| xQc: chat gets restless when he talks too much over a clip; many viewers keep reaction streams in the background [X1]. | X1 (F, DIRECTION S11) | Long quiet reading is normal; motion during it must stay small so that it does not look like the stream froze. |

## 3. Catalogue of desk behaviours, with timing

Columns: what happens, how long / how often, what triggers it, the evidence behind the number, confidence, and how
SUB-01 does it (the `DEFAULTS` key in `scripts/streamer_motion.py`).

| # | Behaviour | Duration / frequency | Trigger | Evidence | Conf. | SUB-01 (`DEFAULTS`) |
|---|---|---|---|---|---|---|
| A1 | **Reading posture**: head nearly still, eyes sweep the lines, small lean towards the monitor, mouse hand on the mouse, other hand resting. | Holds for the whole FOCUS state (3-12 min); the head follows the text only partly: shifts under 20-25 deg are made by the eyes [R7]; fixations last 225-250 ms and saccades 7-9 letters [R10], far below what a head can show. (K) With no animated eyes the head must not stand in for them: screen-following head motion is capped at +-2 deg yaw / +-1.5 deg pitch, filtered over 0.8 s, with 0.6 deg of slow drift; never at fixation or saccade rates. | New page, long text. | R7 (S), R10 (S), R2 (F) "quiet and focused" | high | `lean_by_state.reading 0.30`, `reading_gaze_gain 0.12`, `reading_gaze_max_yaw_deg 2`, `reading_gaze_max_pitch_deg 1.5`, `reading_gaze_smooth_s 0.8`, `reading_head_wander_deg 0.6`. |
| A2 | **Scroll rhythm**: a short wheel burst, then 10-30 s of reading; most attention stays near the top of a page (57% of viewing time above the fold, 74% in the first two screens [R9]). The mouse hand stays on the mouse between scrolls. | The agent scrolls every 14-28 s while reading (AGENT.md). (K) A scroll is a 0.8 s mouse beat with a 0.35-0.70 s look at the new screen region, then the reading filter resumes; no lean pulse, nod or gesture. The visible wheel motion (2-4 detents over 0.22-0.45 s) is native. | Reading. | R9 (S); hand placement **(design)** | mid | `mouse_hold_s 0.8`, `scroll_target_hold_s (0.35, 0.7)`; the mouse hand stays until 120 s without pointer use (`mouse_hand_rest_after_s`). |
| A3 | **Typing**: both hands move to the keyboard a beat before the first key, type in bursts of 1-4 s, pause, look at the result. Bursts are delimited by pauses of 1 s or more [R11]; a search query is 2-5 words. | (K) Hands lead by 0.50 s (two agent ticks: a 0.3 s lead was eaten by transport, easing and the 0.24 s crossfade), linger 0.70 s after the last key; typing that resumes within 1.8 s is the same episode (no new reach). Native: contact 0.15 s before the first visible strike, bursts of 0.8-1.8 s at 6-9 strikes/s. | `type`, `search` actions. | R11 (S); lead/linger **(design)** | mid | `hands_lead_s 0.5`, `hands_linger_s 0.7`, `keyboard_pause_hold_s 1.8`; state `typing` only after the hands arrived. |
| A4 | **Click / navigate**: mouse hand active, a partial head turn to the target, back to reading after the page settles. | (K) 0.8 s mouse beat; the target holds the head aim 0.7-1.2 s at gain 0.45 (a visible but partial turn), then release; a 5 s hold was a stare at a stale pointer. | `click`, `navigate`. | Agent's own `attention_of`; **(design)** | mid | `mouse_hold_s 0.8`, `click_target_hold_s (0.7, 1.2)`, `action_gaze_gain 0.45`; `mouse_state` = `mouse` (sitting loop) or `reading` fallback. |
| A5 | **Mouse hand drifts** when nothing is clicked for a long time: to the desk. | (K) After 120 s without a pointer action (ordinary scrolling never triggers it); back on the mouse at the next scroll. Only the desk rest exists today: no chin or lap target. | Long static read, waiting. | Posture shifts 18-22/h [R4] | mid | `mouse_hand_rest_after_s 120`. |
| A6 | **Idle / waiting**: a page loading, deciding what to do. (K) Waiting is not boredom: a short idle after a click keeps the click attention 0.8 s, then releases the lean to 0.12 with the head broadly on the screen; after 3 s of waiting one short chat glance; no fidget before 25 s in state. Boredom only after 75 s of nothing: once per idle episode, 0.22 back over 1.2 s, head 4 deg off the screen and 1 deg up, one desk fidget, 12-20 s hold; any read/search/click cancels it and re-engages over 0.55 s. | Seconds to minutes. | `none` action, no speech. | **(design)** | low | `lean_by_state.idle 0.12`, `idle_gaze_gain 0.18`, `wait_glance_at_s 3`, `fidget_min_state_s 25`, `bored_after_s 75`, `bored_back_amount 0.22`, `bored_hold_s (12, 20)`. |
| A7 | **Posture shift in the chair**: upright to leaned back and back again. | Office workers shift 18-22 times per hour on a pressure mat [R4]; (K) pressure-mat shifts are not visible full-body leans: one visible leaned-back hold every 240-420 s lasting 15-35 s at 0.28 (about 2.2 deg), plus near-subliminal weight shifts of 0.05 every 70-140 s executed over 1.8 s. | Timer; never during a reaction, a chat answer or typing. | R4 (S), R3 (F) | high (rate), mid (shape) | `posture_shift_every_s (240, 420)`, `posture_back_s (15, 35)`, `posture_back_amount 0.28`, `weight_shift_every_s (70, 140)`, `weight_shift_amount 0.05`, `weight_shift_s 1.8`. |
| A8 | **Hand gestures while talking**: the free (left) hand; the mouse hand stays. | Free-handed narrators gesture 11-22 times per 100 words [R13]; (K) that does not transfer to a seated mouse user: one 0.9-1.4 s gesture of strength 0.25-0.45 about every 8-14 s while answering chat, every 14-26 s while commenting (most comments get zero or one), never before 0.45 s of speech; the right hand joins 15% of the time in a chat answer and never while a pointer or keyboard contact is required. | Speech. | R13 (S); seated rates **(design)** | mid | `gesture_every_chat_s (8, 14)`, `gesture_every_talk_s (14, 26)`, `gesture_s (0.9, 1.4)`, `gesture_strength (0.25, 0.45)`, `gesture_right_hand_p 0.15`, `gesture_after_speech_start_s 0.45`. |
| A9 | **Pose contrast between reading and talking** (K): reading is the forward pose; speech releases the body slightly back. Addressing a viewer is not a lunge towards the lens. | Reading 0.30 forward; reading the viewer's message 0.24; a dry page comment 0.12 back; a chat answer 0.18 back (about 1.4 deg); a 0.30 change takes 0.55 s towards a pose and 1.1 s relaxing. | `speaking`, `chat_addressed`. | R14 (S) inverted; brief | mid | `lean_by_state`, `talk_back_amount 0.12`, `chat_read_lean 0.24`, `chat_talk_back_amount 0.18`, `lean_rise_s 0.55`, `lean_fall_s 1.1`. |
| A10 | **Glance to the chat and back** without stopping what he does. | (K) Every 45-105 s for 0.8-1.5 s (a clock-like glance) while reading or idle and silent; not within 8 s of speech, typing, a reaction or a page change, not during the scroll beat; the anchor is 20 deg to his side and 4 deg down, turned in over 0.25 s and out over 0.35 s; hands and torso do not move. | Timer. | R2 (F) "glances at the chat stream", R16 (S); rate **(design)** | mid | `chat_glance_every_s (45, 105)`, `chat_glance_s (0.8, 1.5)`, `chat_glance_min_state_s 8`, `chat_yaw_deg 20`, `chat_pitch_deg -4` + `look_to_chat`. |
| A11 | **Answering a chat message**: read it first (head to the chat side), then turn to the lens and speak, then back to the content; a longer answer rechecks the message once. The look up carries a small nod. | (K) Read 1.2-2.2 s; one lens address of 1.4-2.4 s with the acknowledgement nod 0.24 (no generic onset nod); back to the screen; if the answer still runs at 5.5-8 s, one 0.8-1.2 s recheck of the message; at voice end the gaze holds 0.35 s, then the reading posture returns over 1.1 s. No camera percentage quota and no repeating read/camera/screen cycle. | `chat_addressed` rising edge, then `speaking`. | R2 (F) reading/reaction pairing; R1 (F) nods as agreement; shape **(design)** | mid | `chat_read_first_s (1.2, 2.2)`, `chat_camera_s (1.4, 2.4)`, `chat_ack_nod 0.24`, `chat_mid_glance_at_s (5.5, 8)`, `chat_mid_glance_s (0.8, 1.2)`, `camera_hold_after_speech_s 0.35`. |
| A12 | **Camera looks are event-driven** (K): a chat answer, a shared reaction (surprise, laugh), open/close or thanks. A dry page comment keeps the head on the content; quiet reading keeps `look_at_camera` at 0. | No timer: the earlier "1-2 s every 20-40 s while commenting" was presenter behaviour and contradicted DIRECTION rule 10. The lens fallback pitch is 4.2 deg up (from the framing recipe), not 8. | Events only. | DIRECTION rule 10; R6 (S) | mid | `camera_glance_every_s` and `speech_first_glance_s` removed; `camera_pitch_deg 4.2`. |
| A13 | **Micro head motion while talking**: nods are "the head motion type which occurred with most frequency", "at the last syllable of the phrases, in strong phrase boundaries", often "accompanied by a small upward motion before the usual down-up motion", the first of a series larger than the rest [R1]. | (K) `voice_playing` at 4 Hz carries no phrase boundaries, so the agent cannot truthfully place phrase nods and a timer would be metronomic: it sends only a speech-onset nod of 0.28 at +0.12 s (about 1.7 deg) and the chat acknowledgement nod 0.24; the native 0.75 s envelope with a 20% upward pre-motion stays. A later prosody nod can read the voice envelope (`mouth.json`, 25 Hz) natively. | Speech onset. | R1 (F) | high (where), low (rate) | `speech_start_nod 0.28`, `speech_start_nod_delay_s 0.12`; `talk_nod_every_s` removed; the native talking cadence (0.9/0.6 deg) stays. |
| A14 | **Surprise**: head back, then in towards the screen to check, a look to the lens to share it. Phrases of surprise come with "upward (fu, ud) or tilt motions" [R1]. | (K) 2.6 s so the phases do not overlap: back 0.40 reached in 0.18 s, forward check 0.45 from 0.45 s, camera share at 1.15 s for 0.75 s, recovery; no nod. | `reaction=surprise` (agent level 2). | R1 (F), K2 (F), K3 (S) | mid | `surprise_s 2.6`, `surprise_back_amount 0.4`, `surprise_back_rise_s 0.18`, `surprise_check_at_s 0.45`, `surprise_check_lean 0.45`, `surprise_camera_at_s 1.15`, `surprise_camera_s 0.75`. |
| A15 | **Laugh**: a small chuckle with a static face: lean back, head tilt, a look to the camera, recover. | (K) 2.2-3.0 s; back 0.55 in 0.25 s; tilt 4-6 deg, sign randomised; head lifts about 2 deg; camera at 0.75 s for 0.8 s; tilt and camera release first, then the posture. The laugh beat is two decaying native torso pulses at about 3 Hz, not fast sine breathing; breathing rises to 0.34 Hz mainly in the recovery. Hands keep their contacts, the chair never moves. | `reaction=laugh` (agent level 3, at most once per 30 min). | K1 (F), K3 (F) | mid | `laugh_s (2.2, 3)`, `laugh_back_amount 0.55`, `laugh_back_rise_s 0.25`, `laugh_tilt_deg (4, 6)`, `laugh_pitch_deg 2`, `laugh_camera_at_s 0.75`, `laugh_camera_s 0.8`, `breath_laugh_hz 0.34`. |
| A16 | **Think**: head tilt, head off the screen (a little up and to a side). Tilts "occurred in almost all dialog acts" and at boundaries where the speaker is thinking [R1]. | (K) 1.4-2.4 s; tilt 4-7 deg; yaw 7 deg, pitch up 2 deg; no chin hand until an authored, contact-correct asset exists (a procedural hand-to-face contact breaks as soon as the spine moves). | `reaction=think` (agent level 1). | R1 (F) | mid | `think_s (1.4, 2.4)`, `think_tilt_deg (4, 7)`, `think_gaze_yaw_deg 7`, `think_gaze_pitch_deg 2`, `think_chin_p 0`. |
| A17 | **Returning upright** after a leaned-back hold: a re-seat, hands back where they were. | End of A7's hold. | Timer. | R3 (F), R4 (S) | mid | Part of A7 (relaxes at `lean_fall_s`). |
| A18 | **Sag after long focus**: "all workers appeared to assume slumped sitting postures after 20 minutes of sitting" [R3]; a shift resets it. | (K) A 20-minute switch was nearly dead code with FOCUS capped at 20 min, and a switch is a timed event: the sag starts at 12 min and ramps in over 3 min as a 0.12 signed backward offset with 1 deg of head drop. | `seconds_in_state >= 720`. | R3 (F) | high (that it happens), low (when) | `focus_slump_s 720`, `focus_slump_ramp_s 180`, `slump_back_amount 0.12`, `slump_pitch_deg -1`. |
| A19 | **Fidgets with the free hand**. People touch their face 23 times per hour [R8]; guides tell streamers to keep drinks within reach [G1]; the headphone adjust is common on stream but unverified in text. | (K) Face touching is not a licence for procedural face fidgets: fixed chin/ear/nape points are wrong as soon as spine and head move, and a cup needs a prop, grasp and contact-aware path. This week only a small desk/finger fidget ships: one every 120-260 s (about 19/h instead of 48), 1.0-1.8 s, wrist in contact; none while typing, reacting, in the first 3 s of a chat answer or within 25 s of a fresh state. Face, headphones, neck, drink and stretch keep zero weight until each has an authored, contact-checked clip; a native build must fail closed on them. | Timer; the free hand only. | R8 (S), G1 (S); mix **(design)** | mid | `fidget_every_s (120, 260)`, `fidget_s.desk (1.0, 1.8)`, `fidget_weights {desk 1, others 0}`, `fidget_min_state_s 25`, `fidget_quiet_after_chat_s 3`. |
| A20 | **Stretch**: removed (K). An autonomous desk stretch every 10-20 min was unsupported by evidence and too conspicuous; the longer physical relief beat belongs to DIRECTION's BREAK (every 45-75 min). | - | - | G1 (S) | - | `stretch_every_s`, `stretch_s` removed. |
| A21 | **Going quiet and reading**: no speech, no camera, head still, chat glances only; streamers "fall silent", "quiet and focused" [R2]; talking over content annoys viewers [X1]. | Minutes (FOCUS 3-12 min, cap 20). | Reading. | R2 (F), X1 (F) | high | A1 + A10; `look_at_camera` is 0 the whole time (tested). |
| A22 | **Transitions**: one body state at a time, no flapping; hands lead clips. | (K) At most one state change per 0.8 s (clears the 0.6 s native debounce; a 0.5 s agent dwell did not guarantee it); hand preparation is its own channel and is not held back by the body-state debounce. | Any. | Native README; **(design)** | high | `state_min_dwell_s 0.8`. |
| A23 | **Breathing**: longer cycles while speaking (5.45 s vs 3.68 s listening: 11.0 vs 16.3 per minute), a "sawtooth" of short inhalation and long exhalation [R5]; quiet breathing about 12 per minute. | (K) Rest 0.20 Hz, reading 0.20, talking 0.18, surprise 0.28, laugh 0.34 (recovery). The speech shape is native: the first 30% of the cycle inhales, 70% exhales, phase accumulated continuously (never restarted on a rate change). | State. | R5 (F) | high | `breath_*_hz`; the native layer breathes at a fixed 0.22 today. |
| A24 | **Blinking** (not implementable without a face rig): about 15 per minute relaxed, lower when reading on a screen, incomplete blinks more frequent [R12]. | Noted for a future rig. | Reading. | R12 (S) | mid | None. |

## 4. SUB-01's own direction (what he does and does not do)

Character (DIRECTION.md section 2): curious, ironic, spontaneous, focused, able to be silent. The body says the same.

**He does** (revised after the Kimi review, K)
- Read with his whole attention: a slight lean in (0.30), head nearly still (within 2 degrees, drifting slowly), mouse
  hand parked on the mouse, the other hand resting on the desk; one scroll at a time, a short look at the new region,
  then back to the lines. Stillness is content, not a bug.
- Glance at the chat the way one glances at a clock: a brief head turn (0.8-1.5 s) every 45-105 s, never right after
  speaking, typing, reacting or a page change, then back to the screen.
- Answer chat in visible phases: read the message (head to the chat side, 1.2-2.2 s), turn to the lens with one small
  nod and speak to it for 1.4-2.4 s while the body releases slightly back, then back to the content; a longer answer
  rechecks the message once. No camera quota: most of an answer is given to the content.
- Keep the head on the content while commenting on a page; the body releases a degree back and one small nod opens the
  utterance. The camera is met only for a chat answer, a shared reaction, open/close or thanks.
- React once, proportionately, with the body: a laugh is a small lean back, a tilt and a short look to the lens; surprise
  is back, a check forward, a short share; thinking is a tilt and the head a little off the screen. Each lasts 1.4-3 s
  and ends in the previous posture, hands never leaving their contacts.
- Shift in the chair every 4-7 minutes for 15-35 s, drift his weight almost imperceptibly in between, sag a little after
  twelve minutes of one thing, tap or rub the desk with the free hand every few minutes, get bored only after more than
  a minute of nothing.
- Breathe slower while talking than while listening.

**He does not**
- Leave the chair, hide, stand, dance, throw his hands up, cover his mouth or face the camera for a long time: the
  escalating beats of the reference streamers are theirs, and the frame is a desk.
- Perform at the camera when nobody is addressed: no sustained eye contact, no routine camera glance while commenting,
  no presenter posture, no forward lunge for every chat answer.
- Move his head with the text or with the pointer: eyes read, the head drifts.
- Nod to a timer, gesture to a timer, or run a fixed read/camera/chat cycle.
- Touch his face, adjust headphones, drink or stretch until authored, contact-correct clips exist (a procedural arm lift
  is never substituted).
- Fidget while typing, during a reaction, in the first seconds of a chat answer, or on a fresh page.
- Flap between states: hands move first (0.5 s), then the clip; one change per 0.8 s at most.
- Mirror a face he does not have: no lip sync, no eyebrows; the mood is in posture, head, hands and timing.

## 5. Open points for a later pass

- Per-streamer desk statistics do not exist in text; if the owner can supply a few clips, a 10-minute tally sheet
  (glances to chat, to camera, scrolls, posture shifts, fidgets, with timestamps) would replace the design rates above.
  Until then the rates are design values and the result is not reference-matched (K).
- The chat anchor direction (which side) is a scene decision; MOTION-SPEC.md now puts it 20 deg to his right and 4 deg
  down (K), with the gaze cap carrying the whole turn and `look_to_chat` selecting the Spine2/Neck/Head distribution.
- The mouse state: `mouse` now plays the sitting loop (README), so the module defaults to it; the agent still passes
  `mouse_state="reading"` until the sitting-loop build is confirmed on the pod.
- The pre-voice read beat of a chat answer (A11) needs the agent to raise `chat_addressed` when the batch is picked, not
  when the speech is dispatched (today both rise together; the director copes, but the beat then overlaps the voice).
- Phrase nods (A13) return only with a prosody signal: the voice envelope (`mouth.json`) read natively, or chunk timing
  from the voice service; `voice_playing` alone is not enough (K).

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
