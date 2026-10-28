# Kimi consultation (2026-10-23): animation

Model kimi-k3.1-pro, asked through tools/ask_kimi.py with the project documents attached; the brief is in `docs/streamer/kimi/q-animation.txt`. The answer is advice to weigh, not project policy; decisions taken from it are recorded in DECISIONS-ANIMATION-STREAM.md.

# Ship direction

Ship the quiet version: **reading is nearly still; speech releases the posture; reactions are single, small envelopes; the hands keep believable contact with the desk.** Do not implement the study literally. Its main failure is that it stacks many individually plausible behaviours into a performance that will look busy, timed, and head-led.

Two limits need to be explicit:

- I have only the supplied documents. I have not seen the two clips, the mesh, the actual `DEFAULTS`, the Unreal animation graph, or the desk/prop transforms. Exact clip phase indices, IK target XYZ coordinates, and a guarantee that the result looks “real” cannot be derived from this material.
- With no animated eyes, jaw, or face shapes, there is no true reading gaze, blink, eye contact, or facial laugh. `gaze` below means **head aim**. A restrained upper-body performance is achievable; a static face in a tight webcam shot will remain a limitation.

All rates below are shipping design values, not newly discovered streamer statistics.

---

# 1. Critique of the study and native spec

## 1.1 The behavioural study

| Problem | Correction to ship |
|---|---|
| **It is not yet a reference study of desk motion.** The streamer sources establish large public beats, not ordinary sitting, mouse use, chat glances, or typing. Most of the useful numbers come from different tasks and populations. | Keep the qualitative structure—neutral watching punctuated by rare beats—but label the desk rates as design. Do not describe the result as reference-matched until actual desk footage has been tallied. |
| **The behaviour budget is too high.** Using the midpoint rates, silent reading gets approximately 60 chat glances/hour, 16 visible posture shifts/hour, 48 fidgets/hour, and 4.5 stretches/hour: about **128 visible events/hour, one every 28 s**, before gestures and camera looks. | Remove autonomous stretching. Ship chat glances every **45–105 s**, visible posture changes every **240–420 s**, and free-hand desk fidgets every **120–260 s**. The tiny weight shifts are separate and must remain almost subliminal. |
| **A1 turns reading into head motion.** A `reading_gaze_gain` of 0.55 is especially wrong when there are no animated eyes. Head-following text or every screen target will produce a slow reading bob rather than reading. | Use gain **0.12**, clamp reading head motion to **±2° yaw / ±1.5° pitch**, smooth it over **0.8 s**, and keep independent head drift at only **0.6°**. Discrete clicks may use gain **0.45**. Never generate head motion at fixation or saccade rates. |
| **The mouse and click holds are freezes, not behaviour.** A 2 s mouse hold per scroll and a 5 s target hold will make him stare at stale pointers. | The hand remains on the mouse independently of action holds. Use a **0.35–0.70 s** scroll-target hold and **0.7–1.2 s** click/result hold. The visible scroll itself lasts **0.22–0.45 s**. |
| **The 0.3 s typing lead is not robust at 4 Hz.** One tick is 0.25 s; transport, easing, and a 0.24 s crossfade consume the lead. It also cannot guarantee contact before the first visible keystroke. | Agent lead becomes **0.50 s**, two ticks. Native hand travel takes **0.35 s**, with contact established about **0.15 s before typing motion starts**. Keep the hands on the keyboard for **0.70 s** after typing and through pauses shorter than **1.8 s**. |
| **Pressure-mat shifts are not visible full-body leans.** A7 transfers an 18–22/hour measurement into a visible posture performance. Likewise, R3 does not justify a discrete “slump at exactly 20 minutes.” | Use a visible leaned-back hold every **240–420 s**, lasting **15–35 s**, at only `lean_back=0.28`. Add tiny **0.05 normalized** weight shifts every **70–140 s**. Start long-focus sag gradually at **720 s**, ramping over **180 s**, rather than switching at 1200 s. A 1200 s threshold is nearly dead code when FOCUS is capped at 20 minutes. |
| **The gesture evidence does not transfer directly.** Free-handed narration gestures per 100 words do not describe a seated person using a mouse. Procedural forearm lifts at the proposed frequency will look like a talking puppet. | Use the free hand only, normally the left. Gesture for **0.9–1.4 s**, strength **0.25–0.45**, at most about every **8–14 s during chat** and **14–26 s during other speech**. The right hand participates only 15% of the time and never while a pointer or keyboard contact is required. |
| **A9 conflicts with the brief’s talking posture.** Automatically driving `lean=0.65` for every chat answer produces a repeated forward presenter lunge. | Ship the brief’s pose contrast: reading at `lean=0.30`, generic speech at `lean_back=0.12`, and chat speech at `lean_back=0.18`. These are only **1.0–1.4° backward**; engagement comes from the lens aim and acknowledgement nod, not a large forward movement. |
| **The 30° chat anchor is too far for a frequent glance.** The proposed 15% `Spine2` contribution also gives roughly 4.5° of shoulder turn, making a short glance look like a conversation with someone off-camera. | Put the chat anchor at **20° to his right and 4° down**. A full glance uses `Spine2` **5%**, `Neck` **30%**, `Head` **65%**: approximately **1° / 6° / 13°**. Use a **0.8–1.5 s dwell**, not a generic 1–3 s stare. |
| **The answer phases and 60% camera quota are mechanical.** Fixed read/camera/chat cycles will repeat visibly. | One read phase, one initial lens address, then screen or message as appropriate. Initial camera hold **1.4–2.4 s**. If the answer is still running at **5.5–8.0 s**, make one **0.8–1.2 s** chat glance. Short answers skip it. No camera-percentage quota. |
| **Scheduled camera looks contradict DIRECTION rule 10.** A look every 20–40 s during generic speech is presenter behaviour. | Remove `camera_glance_every_s` and `speech_first_glance_s`. Camera looks are event-driven: chat address, qualifying reaction, open/close or thanks. A dry page comment stays on the screen. Quiet reading keeps `look_at_camera=0`. |
| **R1 does not justify a phrase-nod timer.** More importantly, `voice_playing` at 4 Hz contains no phrase boundaries. The system cannot truthfully claim phrase-synchronous nods. | Ship only a speech-onset nod and a chat acknowledgement nod. Disable periodic `talk_nod_every_s`. Native nod: **0.75 s**, 20% upward pre-motion, with `nod_strength=1.0` mapped to **6° downward**. Onset strength **0.28**, chat acknowledgement **0.24**. |
| **Surprise does not fit its own 2 s timeline.** The back, forward check, and camera share overlap; the additional 0.6 nod is unmotivated. | Use **2.6 s**: back over **0.18 s**, forward check beginning at **0.45 s**, camera share at **1.15 s for 0.75 s**, then recovery. No surprise nod. |
| **The proposed laugh is a rocking lean plus fast sine breathing.** With a static face, `lean_back=0.8`, a 9° tilt, and 0.5 Hz breathing will look performed or uncomfortable. | Ship a small chuckle: `lean_back=0.55`, tilt **4–6°**, total **2.2–3.0 s**, camera at **0.75 s for 0.8 s**. Two decaying native upper-torso pulses at about **3 Hz**, only **0.7°** initially, supply the laugh beat. Do not use a continuous 0.5 Hz breathing pump. |
| **Think promises an eye movement and a chin contact that cannot currently be delivered.** | Use head yaw **7°**, pitch up **2°**, tilt **4–7°**, for **1.4–2.4 s**. Set `think_chin_p=0`; no procedural hand-to-face contact. |
| **Face touching is not a licence for procedural face fidgets.** Fixed chin/ear/nape points become wrong as soon as the spine and head move. A cup additionally needs a prop, grasp, and contact-aware path. | This week, `face`, `headphones`, `neck`, `drink`, and `stretch` have zero agent weight. Never replace them with a generic forearm gesture. Add only a small desk/finger fidget now. |
| **Stretching every 10–20 minutes is both unsupported and too conspicuous.** | Remove the autonomous desk stretch. BREAK already owns the longer physical relief beat. |
| **The agent/native dwell values disagree.** A 0.5 s agent dwell does not guarantee passage through a 0.6 s native debounce. | Agent minimum dwell becomes **0.8 s**. Hand preparation is a separate channel and is not held back by body-state debounce. |

## 1.2 The native motion spec

1. **The counter-pitch explanation is mathematically inconsistent.**  
   At full forward lean, 9° torso pitch minus 5.5° counter-pitch leaves **3.5°** on the head. That is not “face level.” At full back lean it leaves **4.8°**. This is acceptable as a natural intermediate pose, but the final head-aim stage must remove the residual when a screen, chat, or lens target is active.

2. **Do not animate these offsets in unnamed Mixamo local axes.**  
   Bone-local X is not a portable character pitch axis. Construct rotations around **character/component-space axes**, distribute them over the chain, and convert back to local transforms. Use quaternions, not independently interpolated Euler angles.

3. **Forward and backward lean need one signed posture channel.**  
   The two different spine distributions cannot simply be “subtracted” as rotations. Use:
   ```text
   s = clamp(lean - lean_back, -1, +1)
   torso_angle = 9° * s   when s >= 0
   torso_angle = 8° * s   when s < 0
   ```
   The agent should nevertheless emit mutually exclusive forward/back poses. Reaction and posture-back poses replace the base reading lean rather than accidentally adding to it.

4. **One 0.25–0.4 s smoother for everything is wrong.**  
   Ship posture smoothing around **0.45 s**, voluntary head aim **0.22 s**, reading head filtering **0.8 s**, and reaction onset **0.08–0.12 s**. Sub-second reaction and hand shapes must be native envelopes; the 4 Hz agent cannot draw them reliably.

5. **The lens fallback is not geometrically reliable.**  
   `gaze_yaw=0, gaze_pitch=8` is not generally a lens aim. With the camera recipe below, the neutral head-to-lens pitch is approximately **4.2° up**, not 8°. Compute it from the fixed webcam-lens transform.

6. **The “2° below the lens” rule belongs to eyes, not this head rig.**  
   For this build, aim the head at the lens itself. Do not introduce a 2° head offset and call it eye contact. Tighten the steady-state acceptance error from 3° to **1°**.

7. **The hand enum currently promises combinations that two full-body clips cannot represent.**  
   The supported set must be explicit:
   - sitting loop: left rest, right mouse;
   - sitting loop plus IK: either or both hands at rest;
   - typing loop: both hands keyboard;
   - sitting loop plus an arm mask: one hand gesture, the other retaining its desk contact;
   - no typing-plus-gesture combination;
   - no left-mouse mode for this right-handed character.

8. **A wrist IK pull is not a complete hand solution.**  
   The “12 cm toward the body” rest rule and 25 cm correction allowance are too crude. Rest targets must be calibrated against the actual desk and props. Use two-bone IK with a wrist rotation and elbow pole, then fingers. A normal correction should be under **30 mm**; fail calibration rather than stretching when the required correction exceeds **60 mm**.

9. **The 24-phase matcher cannot solve hand contact.**  
   It can choose a compatible spine/head phase. It cannot make a crossfade from mouse to keyboard into a believable reach. During that transition the arms need their own timed paths and contact pins.

10. **Unsupported fidgets must fail closed.**  
    A valid-but-unimplemented `fidget:"face"` must leave the hand at rest and log the unsupported request. It must not invoke the generic gesture layer.

11. **The nod edge rule needs rearming.**  
    A repeated nod of the same strength must work. Rearm when `nod_strength <= 0.02`; trigger on the next rise through the threshold. The agent holds the value long enough to survive a tick, and native starts exactly one 0.75 s envelope.

12. **The proposed breathing shaping is incorrect.**  
    Raising `sin` to a power on the inhale half does not create a short inhale and long exhale, and fractional powers of negative values are a numerical hazard. Accumulate phase continuously:
    ```text
    phase = fract(phase + breathing_rate_hz * dt)
    ```
    For speech, use the first **30%** of the cycle for a smooth inhale and the remaining **70%** for exhale, with a 0.6 s crossfade between wave shapes. Do not restart phase on rate or state changes.

13. **The pelvis acceptance is too loose.**  
    The existing 8 cm audit may be useful for whole-clip drift, but it is not an acceptable tolerance for these additive layers. With procedural layers toggled on and off at the same clip phase, the additional hips difference must be **≤0.5 mm and ≤0.2°**.

14. **Receipts need values and one-shot identifiers, not only field names.**  
    Debug captures need applied torso angle, head target and error, hand-contact state, IK offset in millimetres, clip phase, and the last accepted action/reaction identifier. `motion_fields_applied:["lean"]` alone cannot diagnose a pop or a missed click.

15. **The time estimates are optimistic.**  
    A 4–6 h hand item can deliver a simple wrist offset, not convincing desk contacts, transitions, and finger motion. Five contact-aware fidget clips in 1–2 days is not a credible cleanup/import/review estimate without an unusually mature asset pipeline.

---

# 2. Motion-director `DEFAULTS` to ship

The actual Python file was not supplied, so this covers **every key named in the documents plus the replacements below**; unnamed existing keys cannot be audited.

Conventions:

- Ranges are uniform random draws **once per behaviour episode**, never re-rolled on each 4 Hz tick.
- `lean=1` means 9° total forward torso pitch; `lean_back=1` means 8° backward.
- Nod strengths assume the native calibration of 6° at strength 1.
- `chat_glance_s` and similar dwell values exclude the native turn-in/turn-out time.

## 2.1 State, gaze and hand timing

| Key | Ship value | One-line reason |
|---|---:|---|
| `state_min_dwell_s` | **0.80** | Clears the 0.6 s native debounce and avoids losing legitimate transitions. |
| `hands_lead_s` | **0.50** | Two agent ticks provide enough time for a 0.35 s reach and contact settle. |
| `hands_linger_s` | **0.70** | Prevents an immediate hand departure when the last character or action arrives. |
| `keyboard_pause_hold_s` | **1.8** | Short planning pauses must not cause sitting/typing clip flapping. |
| `mouse_hold_s` | **0.80** | Gives a discrete mouse action visual persistence without freezing the hand for 2 s. |
| `mouse_hand_rest_after_s` | **120** | Two minutes without pointer use earns a rest; ordinary scrolling never triggers it. |
| `mouse_state` | **`"mouse"`** | Uses the native sitting-loop mapping rather than preserving the rehearsal workaround. |
| `click_target_hold_s` | **(0.7, 1.2)** | Holds long enough to acquire the result without a 5 s stare. |
| `scroll_target_hold_s` | **(0.35, 0.70)** | A scroll briefly redirects attention and then releases it. |
| `action_gaze_gain` | **0.45** | Discrete click/search targets may produce a visible but partial head turn. |
| `reading_gaze_gain` | **0.12** | Prevents the head from acting as a substitute for reading eye movements. |
| `idle_gaze_gain` | **0.18** | Idle attention may wander slightly more than reading without becoming animated. |
| `reading_head_wander_deg` | **0.60** | Enough motion to avoid a frozen head, small enough to preserve stillness. |
| `reading_head_wander_hz` | **0.04** | Approximately a 25 s drift scale; use smooth noise, not an obvious sine loop. |
| `reading_gaze_max_yaw_deg` | **2.0** | Hard bound on text/screen-following yaw during reading. |
| `reading_gaze_max_pitch_deg` | **1.5** | Prevents vertical line tracking from becoming a reading nod. |
| `reading_gaze_smooth_s` | **0.80** | Filters 4 Hz target changes into slow, low-amplitude head movement. |

## 2.2 Posture

| Key | Ship value | One-line reason |
|---|---:|---|
| `lean_by_state.reading` | **0.30** | A 2.7° forward torso angle reads as engaged without a permanent hunch. |
| `lean_by_state.typing` | **0.40** | A 3.6° lean gives search/type a little more intent than reading. |
| `lean_by_state.idle` | **0.12** | Waiting releases most, but not all, of the reading posture. |
| `lean_by_state.talking` | **0.0** | Speech uses the small explicit backward posture below instead of forward presenter posture. |
| `talk_back_amount` | **0.12** | Approximately 1° back distinguishes a dry page comment from reading. |
| `chat_read_lean` | **0.24** | Reading a viewer message relaxes the forward lean slightly before the answer. |
| `chat_talk_back_amount` | **0.18** | Approximately 1.4° back supports the brief’s reading-forward/talking-back contrast. |
| `lean_rise_s` | **0.55** | Fast enough to show intention, slow enough not to look like a snap. |
| `lean_fall_s` | **1.10** | Returning to neutral should be less noticeable than the initial engagement. |
| `posture_shift_every_s` | **(240, 420)** | Produces a visible chair-posture change roughly 9–15 times/hour, not every pressure-mat shift. |
| `posture_back_s` | **(15, 35)** | Long enough to be a genuine hold, short enough not to become a second default pose. |
| `posture_back_amount` | **0.28** | About 2.2° back is visible at webcam scale without looking like lounging. |
| `weight_shift_every_s` | **(70, 140)** | Supplies very small postural variation between the larger holds. |
| `weight_shift_amount` | **0.05** | Only about half a degree of signed posture change; it must not read as a behaviour beat. |
| `weight_shift_s` | **1.8** | Slow execution keeps the weight shift below conscious notice. |
| `focus_slump_s` | **720** | Starts only in unusually long FOCUS states and avoids the nearly dead 20-minute threshold. |
| `focus_slump_ramp_s` | **180** | Makes sag a gradual drift rather than a timed animation event. |
| `slump_back_amount` | **0.12** | A small signed backward offset reduces engagement without caricaturing fatigue. |
| `slump_pitch_deg` | **-1.0** | One degree of additional head drop is sufficient at this framing. |

## 2.3 Chat, camera, speech and gestures

| Key | Ship value | One-line reason |
|---|---:|---|
| `chat_glance_every_s` | **(45, 105)** | Roughly one glance per 75 s on average, with irregular spacing. |
| `chat_glance_min_state_s` | **8.0** | Prevents a glance immediately after every page/state entry. |
| `chat_glance_s` | **(0.8, 1.5)** | A clock-like dwell rather than a prolonged turn away from the lens. |
| `chat_yaw_deg` | **20** | Matches a nearby chat display and avoids the proposed 30° pull away from camera. |
| `chat_pitch_deg` | **-4** | Places the anchor slightly below monitor centre. |
| `chat_read_first_s` | **(1.2, 2.2)** | A visible short-message read beat; it is not a claim about reading long messages. |
| `chat_ack_nod` | **0.24** | About 1.4° of downward motion acknowledges the message without bobbing. |
| `chat_camera_s` | **(1.4, 2.4)** | Long enough to feel addressed, short enough to avoid presenter staring. |
| `chat_mid_glance_at_s` | **(5.5, 8.0)** | Only longer answers earn one return to the message. |
| `chat_mid_glance_s` | **(0.8, 1.2)** | Rechecks the text without restarting the whole answer cycle. |
| `camera_glance_s` | **(0.7, 1.2)** | Default dwell for event-driven non-chat camera looks. |
| `camera_hold_after_speech_s` | **0.35** | Prevents an abrupt eye-line exit on the final audio sample. |
| `speech_start_nod` | **0.28** | About 1.7° gives non-chat speech a small physical onset. |
| `speech_start_nod_delay_s` | **0.12** | Avoids moving exactly on the state toggle and reads as the start of the utterance. |
| `gesture_after_speech_start_s` | **0.45** | Hands do not fire on the same frame as the voice and head. |
| `gesture_every_chat_s` | **(8, 14)** | Allows roughly one free-hand beat in a normal short answer. |
| `gesture_every_talk_s` | **(14, 26)** | Most 10–40 s comments receive zero or one gesture, not a stream of gestures. |
| `gesture_s` | **(0.9, 1.4)** | Enough time for lift, brief hold and an unhurried return. |
| `gesture_strength` | **(0.25, 0.45)** | Uses only the lower part of the procedural 25° forearm-lift range. |
| `gesture_right_hand_p` | **0.15** | The right hand normally keeps its mouse/desk role. |

There is deliberately **no periodic talking-nod timer**. `speech_start_nod` is suppressed for chat answers, which use `chat_ack_nod` instead.

## 2.4 Reactions

| Key | Ship value | One-line reason |
|---|---:|---|
| `surprise_s` | **2.6** | Fits back, forward check, camera share and recovery without overlap. |
| `surprise_back_amount` | **0.40** | About 3.2° back is clear but keeps him seated and proportionate. |
| `surprise_back_rise_s` | **0.18** | Requires a native fast envelope rather than the normal posture smoother. |
| `surprise_check_at_s` | **0.45** | The forward check follows the initial withdrawal instead of blending with it. |
| `surprise_check_lean` | **0.45** | About 4° forward gives curiosity after the startle. |
| `surprise_camera_at_s` | **1.15** | Shares the reaction only after he has checked the screen. |
| `surprise_camera_s` | **0.75** | A brief share, not a second reaction performed for the lens. |
| `laugh_s` | **(2.2, 3.0)** | Supports a small chuckle and recovery with a static face. |
| `laugh_back_amount` | **0.55** | About 4.4° back reads clearly without the proposed large rock. |
| `laugh_tilt_deg` | **(4, 6)** | Enough asymmetry to distinguish laugh from surprise; sign is randomized. |
| `laugh_camera_at_s` | **0.75** | The body beat happens before the lens is acknowledged. |
| `laugh_camera_s` | **0.80** | Short enough to return naturally to the content. |
| `think_s` | **(1.4, 2.4)** | A concise thought beat that does not become a recurring pose. |
| `think_tilt_deg` | **(4, 7)** | A smaller, randomized tilt avoids an exaggerated “thinking” emoji pose. |
| `think_gaze_yaw_deg` | **7** | Moves the head off the screen without pretending to animate eyes. |
| `think_gaze_pitch_deg` | **2** | A slight upward head aim supplies the off-screen thought direction. |
| `think_chin_p` | **0.0** | Disabled until an authored, contact-correct chin-hand asset exists. |
| `reaction_cooldown_s` | **30** | Preserves the one-proportionate-reaction rule. |
| `level3_cooldown_s` | **1800** | Enforces the maximum one level-3 beat per 30 minutes. |

## 2.5 Fidgets and breathing

| Key | Ship value | One-line reason |
|---|---:|---|
| `fidget_every_s` | **(120, 260)** | Reduces the original roughly 48 fidgets/hour to about 19/hour on average. |
| `fidget_min_state_s` | **25** | A short page load or fresh state must not instantly produce a fidget. |
| `fidget_s` | **(1.0, 1.8)** | Fits the supported desk/finger fidget without pretending to be a drink or face touch. |
| `fidget_weights` | **`{desk:1.0, face:0, headphones:0, neck:0, drink:0, stretch:0}`** | Only the contact-safe procedural behaviour ships this week. |
| `fidget_quiet_after_chat_s` | **3.0** | Keeps the beginning of an answer clean and intentional. |
| `breath_rest_hz` | **0.20** | Twelve cycles/minute is a neutral quiet-breathing default. |
| `breath_reading_hz` | **0.20** | Reading remains calm and does not acquire a separate conspicuous rhythm. |
| `breath_talking_hz` | **0.18** | A 5.56 s cycle is close to the longer speech-cycle evidence. |
| `breath_surprise_hz` | **0.28** | A brief rate increase supports the startle without running indefinitely. |
| `breath_laugh_hz` | **0.34** | Used mainly in recovery; the laugh beat itself is not fast sine breathing. |
| `breath_speech_inhale_fraction` | **0.30** | Gives speech a short inhale and longer exhale while preserving phase continuity. |

## 2.6 Keys removed or replaced

| Removed key | Replacement / reason |
|---|---|
| `lean_chat`, `lean_chat_reading` | Replaced by `chat_read_lean` and `chat_talk_back_amount`; removes the repeated forward presenter lunge. |
| `target_hold_s` | Split into `click_target_hold_s` and `scroll_target_hold_s`. |
| `chat_screen_s` | Removed with the fixed read/camera/screen cycle; the single mid-answer glance is event-length dependent. |
| `camera_glance_every_s` | Removed; camera address is event-driven, not a background timer. |
| `speech_first_glance_s` | Removed; generic page comments do not automatically perform to the lens. |
| `camera_pitch_deg` | Removed; lens pitch is computed from the actual fixed camera and head transforms. |
| `talk_nod_every_s`, `talk_nod_strength` | Removed until real phrase/prosody timing exists. |
| Surprise nod strength | Removed; surprise has a back/check/share structure, not an unexplained nod. |
| `stretch_every_s`, `stretch_s` | Removed; no autonomous desk stretch ships. |

## 2.7 Small extension additions required for clean native triggering

Keep the v2 compatibility approach, but add:

- **`motion.action_seq: uint32`** — increments for each new discrete `click` or `scroll`. Native triggers once per new value. Without it, two identical scrolls in a row are indistinguishable from one action held over several ticks.
- **`motion.reaction: "none"|"think"|"surprise"|"laugh"`** — persists during the reaction. Native starts one envelope on entry. Inferring laugh versus think from combinations of lean and tilt would be fragile.
- **`fidget:"desk"`** — the only procedural fidget added now.
- Do not add prosody fields this week. If true phrase nods are wanted later, supply phrase/chunk timing or an audio-derived envelope; `voice_playing` alone is insufficient.

---

# 3. Ranked native implementation

Hours below include a basic on-pod debug pass and assume an engineer already familiar with the animation instance, the existing phase matcher, and UE IK. They are estimates; clip quality and retarget/skeleton surprises can change them substantially.

| Rank | Native work and viewer-visible result | Bones | Driving signal from agent | Hours | Acceptance: frame/log must show |
|---|---|---|---|---:|---|
| **1** | **Motion kernel, signed posture and head counter-pitch.** Viewer sees reading, talking and relaxation as different body states rather than different head offsets. | `Hips` untouched; `Spine`, `Spine1`, `Spine2`; `Neck`, `Head` for counter-pitch. | `motion.lean`, `motion.lean_back`; `state` only for fallback. | **6–8** | Full lean gives **9±0.2°** total torso pitch; full back gives **8±0.2°**. Additional hips delta is **≤0.5 mm / 0.2°**. Malicious simultaneous lean values do not pop. With a head target active, residual target error is removed by the later head pass. |
| **2** | **Final head-target stack: filtered screen aim, chat, lens and tilt.** Viewer sees a brief chat acknowledgement and genuine lens address, but no reading bob. | `Spine2` only for chat, `Neck`, `Head`. | `gaze_yaw_deg`, `gaze_pitch_deg`, `look_at_camera`, `look_to_chat`, `head_tilt_deg`, current action. | **8–10** | Lens aim error **≤1° after 0.8 s**. Chat gives **20±1°** total head yaw, **−4±1°** pitch and approximately **1°** `Spine2` yaw. A synthetic ±10° reading sweep produces no more than **2°** head yaw and **4°/s** reading-head speed. |
| **3** | **Desk/mouse/rest contact calibration on the sitting loop.** Viewer stops seeing floating wrists, a palm through the desk, or a hand glued to an imaginary mouse. | `Left/RightArm`, `ForeArm`, `Hand`; finger roots for the rest pose. Shoulders remain stable. | `hand_left`, `hand_right`, `state`; `action_seq` for click/scroll contact activity. | **10–14** | After settling, wrist target error p95 **≤5 mm** and maximum **≤10 mm** over a 60 s loop; normal corrective offset p95 **<30 mm**, hard cap **60 mm**. No visible palm/desk or finger/prop penetration at the actual webcam angle. |
| **4** | **Two-clip reach and return choreography.** Viewer sees hands lead the body, arc above the desk and settle before typing; no crossfade drag through the keyboard. | Same arm chains; `Spine`, `Spine1`, `Spine2`, `Head` used by the body phase-match cost. | `hand_left/right="keyboard"` at **−0.50 s**, then `state="typing"` with action `type` or `search`; reverse hand fields on exit. | **14–18** | Logged hand preparation precedes typing by **≥0.45 s**; `hands_ready=keyboard` precedes the first native strike by **≥0.10 s**. No transition-frame wrist discontinuity over **10 mm**, no desk penetration, and no more than one body-state transition per dwell interval. |
| **5** | **Native finger and mouse micro-motion.** Viewer sees uneven typing bursts, small releases and actual click/scroll shapes rather than a vibrating loop. | Available Mixamo finger chains, `Hand`, small residual on `ForeArm`. Exact finger names must be verified on the live skeleton. | `state="typing"` gates typing; new `action_seq` with `click` or `scroll` gates mouse beats. The agent does not send individual finger motion at 4 Hz. | **8–12** | Typing strikes occur only while typing: **6–9 strikes/s** inside **0.8–1.8 s** visual bursts. Strike down **45–65 ms**, release **70–110 ms**. Click is about **60 ms down / 90 ms up**. No synchronized all-finger motion and no strikes after state exit beyond completion of the current ≤80 ms strike. |
| **6** | **Phase-continuous breathing and robust one-shot nods.** Viewer gets quiet life signs without a breathing reset or metronomic head bob. | `Spine1`, `Spine2`; `Neck`, `Head` for nod. | `breathing_rate_hz`, `state="talking"`, `nod_strength`. | **4–6** | Rate changes produce no phase discontinuity; talking uses a 30/70 inhale/exhale split. Two identical nod strengths separated by a zero/rearm period create exactly two **0.75 s** pulses. Reading without speech produces no nod pulses. |
| **7** | **Native think/surprise/laugh envelopes.** Viewer can distinguish the three reactions with the face static. | Spine chain, `Neck`, `Head`; hands remain pinned to their current contacts. | New `motion.reaction`, `state="reacting"`, `intensity`; continuous lean/tilt/camera fields remain the fallback. | **6–8** | Surprise reaches 90% of its back pose in **0.18±0.03 s**, checks at **0.45 s**, shares at **1.15 s**, ends at **2.6±0.1 s**. Laugh and think match their shipped durations. Hips stay fixed and no reaction spawns a hand-to-face action. |
| **8** | **Small free-hand gesture and desk fidget layer.** Viewer gets occasional conversational hand life and a safe idle outlet. | Gesture-side `Arm`, `ForeArm`, `Hand`, fingers; no spine or hips movement required. | `hand_left/right="gesture"`, `gesture_strength`, `fidget="desk"`; suppressed by typing and reaction state. | **8–10** | Gesture lasts **0.9–1.4 s**, respects **25° forearm / 8° upper-arm** maxima at strength 1, and returns within **5 mm / 3°** of its start pose. The other hand’s contact error does not change. No gesture is accepted during typing. |
| **9** | **Record and import the third clip described below, then use its contact/reach segments.** Viewer sees authored asymmetry and weight in the hardest hand transitions. | Full skeleton recorded; primarily arm/finger layers used native, with minimal baked spine/head motion. | Same preparation, typing and return signals as ranks 4–5. | **24–32** | Start/end contact poses match within **5 mm and 3°**; clip markers select the intended segment; hands contact the real-sized props; the full 12 s take is never played as a repeating behavioural loop. |
| **10** | **Authored face/headphone/neck/drink clips, later.** Viewer gets the larger realism step that procedural arm lifts cannot safely provide. | Arm chains plus relevant spine/head layers; cup interaction also needs a prop/grasp setup. | `fidget` kind with one-shot entry/exit; agent weights remain zero until each asset passes. | **40–60** | Each clip has contact-checked begin/hold/end poses, no mesh penetration, no prop teleport, and a phase/contact-safe return. Until then, unsupported requests log and leave the hand at rest. |

**Do not start rank 10 this week.** The procedural body plus a proper desk/mouse/typing vertical slice is already a substantial sprint. The complete hand stack is roughly **32–44 hours** on its own.

## 3.1 Required evaluation order

Use this order every frame:

1. Evaluate the base clip and any phase-matched body crossfade.
2. Apply breathing and signed spine posture in component space.
3. Apply head tilt and the final screen/chat/lens head aim.
4. Apply the gesture or authored arm mask.
5. Solve hand IK and contact constraints against the post-posture body.
6. Apply or blend the finger layer.
7. Record debug metrics.

Future face/headphone fidgets must compute their targets **after step 3**, not from fixed points in the unanimated character space.

For head-target conflicts, the native priority is **reaction/lens > chat > screen**. The agent should avoid overlaps; native logs a suppressed lower-priority target rather than aiming between two targets.

## 3.2 Convincing keyboard and mouse hands with only the two clips

### Calibrate contacts, not generic “hand offsets”

Create calibrated character/prop sockets for:

- left and right keyboard wrist aims and palm orientations;
- left desk-rest wrist aim;
- right desk-rest wrist aim;
- mouse wrist/palm aim;
- elbow pole positions for keyboard, desk and mouse.

Their actual XYZ values cannot be supplied without the scene. Do not infer them from a 12 cm rule.

Two-bone IK controls the wrist; it does not place the elbow arbitrarily and it does not solve the fingers. After reaching the target, align the wrist orientation to the calibrated palm pose. If a required correction exceeds **60 mm**, the clip/prop calibration is wrong and must be fixed rather than hidden with a longer arm reach.

### Sitting → typing timeline

At `t=-0.50 s`:

1. Freeze new gestures and fidgets.
2. Capture both current wrist transforms.
3. Begin quintic/minimum-jerk wrist paths to the keyboard contact transforms.
4. Use a **30–50 mm arc height** where needed so the hands clear the desk rather than slide through it.
5. Left may lead right by **60–90 ms**; this small asymmetry is desirable.

At `t=-0.28 s`:

- Start the **0.28 s** body crossfade toward the typing loop.
- Keep the arms under the reach/contact system so the body crossfade cannot drag the wrists.

At `t=-0.15 s`:

- Both keyboard contacts are established.
- Pre-shape the fingers and assert `hands_ready=keyboard`.

At `t=0`:

- Start the typing-body state and native strike scheduler.
- Blend in any useful authored typing arm/finger motion over about **0.12 s**, while keeping the contact pins active.

### What the 24-phase matcher should actually match

At the body transition, evaluate the target clip at the existing 24 phases and choose the candidate with the lowest body cost, for example:

```text
C(p) =
    (angle_error(Spine2_current, Spine2(p)) / 6°)²
  + (angle_error(Head_current,   Head(p))     / 5°)²
  + 0.25 * (Spine2_rate_error(p) / (25°/s))²
```

Do **not** include a large wrist-cost term and expect the matcher to solve the reach: the arms are explicitly overridden during this transition. Do not re-phase continuously after the transition; that creates time-warp shimmer.

### Typing → reading/mouse

1. Stop scheduling new strikes immediately; allow the current strike to finish within **80 ms**.
2. Keep both hands on the keyboard for **0.70 s**.
3. If typing resumes within **1.8 s**, never leave the keyboard pose.
4. Otherwise, return the right hand to mouse over about **0.30 s** and the left to desk rest over about **0.36 s**, again with a shallow arc.
5. Phase-match the sitting body during the same broad window.
6. Restore the clip’s arm influence only after contact has settled.

### Native typing and mouse detail

These are native visual parameters, not 4 Hz agent updates:

- Typing visual bursts: **0.8–1.8 s**.
- Burst strike rate: **6–9/s**, irregular rather than perfectly periodic.
- Short intra-action pauses: **0.25–0.8 s**; these are visual micro-bursts within the agent’s longer typing state, not a replacement for its linguistic typing model.
- Fingertip approach travel: approximately **8–14 mm** before a strike.
- Per-strike joint contribution: roughly **4–8°** at the knuckle and **8–14°** at the next finger joint, scaled by finger and current clip pose.
- Wrist motion during a strike: no more than about **1.5°**.
- Resting finger drift: independent **0.5–1.5°** offsets over **1.5–4 s**, never frame-random noise.
- Mouse click: index-finger flexion around **8°**, approximately **60 ms down / 90 ms up**, without an arm punch.
- Scroll: **2–4 detents over 0.22–0.45 s**, approximately **8–12°** of the selected finger motion, with the palm staying on the mouse.
- Pointer movement: when required, only **10–35 mm over 0.18–0.45 s**; do not move the mouse continuously while reading.

If the typing clip already contains strong finger animation, add only a residual and clamp the **combined** angle. Do not stack procedural strikes on top of baked strikes at full amplitude.

Without real key events, this is plausible generic typing, not truthful per-key contact. The supplied action signal cannot provide exact finger-to-key correspondence.

## 3.3 The third clip to record

Record **one 12-second desk contact-and-transition take**, not another generic idle loop and not a laugh. Reach and settle are the present asset gap.

Use the actual chair, desk height, keyboard and mouse dimensions. Keep hips seated and bake essentially no lean, nod, gaze, laughter or breathing; those belong to procedural layers.

| Time | Required content |
|---|---|
| **0.0–2.0 s** | Match the reading contact pose: right hand on mouse, left hand at desk rest, shoulders asymmetric but quiet. |
| **2.0–2.9 s** | Both hands travel to keyboard; left leads by 60–90 ms; shallow wrist arcs, no desk sliding. |
| **2.9–3.4 s** | Settle onto home keys with a clear, held contact pose. |
| **3.4–5.2 s** | One natural typing burst. |
| **5.2–5.8 s** | Stop with hands remaining on the keys; a small planning pause, not a return to idle. |
| **5.8–6.6 s** | A second, shorter typing burst. |
| **6.6–7.3 s** | Hands remain still on the keyboard. |
| **7.3–8.2 s** | Right hand returns to the mouse and settles. |
| **8.0–8.9 s** | Left hand returns to desk rest, slightly overlapping the right-hand return. |
| **8.9–12.0 s** | Small settle, then a clean held end pose matching the start. |

Add segment markers at the reach, keyboard-contact, pause and return points. The take is source material for segments; playing all 12 s repeatedly would be as artificial as another loop.

---

# 4. Webcam framing recipe

Use a **fixed camera**. No head tracking, auto-framing, pose-dependent zoom, or camera movement between reading and talking. The same fixed lens transform is the `look_at_camera` target, avoiding a feedback loop.

The numbers assume ordinary adult head proportions and the posture ranges above; the actual mesh still needs the frame acceptance check.

| Setting | Ship value |
|---|---|
| Camera distance | **0.95 m horizontally from the neutral eye/face plane**; straight-line eye distance is about 0.954 m. |
| Lens height | **70 mm above the neutral eye line**. |
| Optical-axis pitch | **10° downward**. This is the camera’s framing pitch, not the head-to-lens angle. |
| Sensor/frame | **16:9**. |
| Vertical FOV | **40°**, maintained as vertical FOV in Unreal. |
| Resulting horizontal FOV | Approximately **65.8°** at 16:9; diagonal approximately **73.2°**. |
| Equivalent lens feel | Approximately **28 mm full-frame equivalent**; wide enough for the room, not an extreme close webcam distortion. |
| Horizontal head placement | Nose/head centre at **50% of frame width**. |
| Neutral vertical placement | Top of head around **20% from the top**, eyes around **36%**, chin around **53%**, shoulder line around **67%**. |
| Bottom of frame | Upper chest, below the shoulder line; resting desk hands need not be visible. |
| Focus/framing behaviour | Fixed focus and framing; the roughly ±9 cm head travel from extreme posture must remain sharp and uncropped. |

At neutral, the physical direction from the head to the lens is approximately:

```text
atan(0.07 / 0.95) = 4.2° upward
```

That is why a fixed `gaze_pitch_deg=8` is not the right fallback.

### Frame acceptance with both poses

Test the actual rendered mesh at:

- neutral;
- `lean=1.0`;
- `lean_back=1.0`;
- each of those with the maximum shipped reaction tilt.

The frame must show:

- neutral top-of-head within **18–22%** from the top;
- neutral eyes within **34–38%**;
- neutral chin within **51–55%**;
- at every extreme, top of head no higher than **14% from the top** and chin no lower than **60%**;
- head height remains approximately **29–38% of frame height**;
- both shoulders remain visible during the 20° chat glance;
- no automatic reframing between the reading-forward and talking-back poses.

This gives enough headroom for the forward lean to grow slightly in perspective and enough lower-frame room for the backward pose and upper chest.

---

# 5. Ten behaviours implementable this week

These are rules, not a repertoire to run on a loop. Content reactions still require the agent’s reaction signal; spontaneity must not be manufactured by scheduling laughter or surprise.

Waiting below uses the module’s existing idle/`none` action. A short idle after a click is treated as waiting; boredom is not inferred until the much longer threshold.

| # | Situation and trigger | Rule with timings |
|---|---|---|
| **1** | **Settle into a long article** — `action=read` continuously for **0.75 s**, no voice, chat address or reaction. | Keep the sitting loop, right hand mouse and left hand rest. Ease to `lean=0.30` over **0.55 s**. Breathing becomes **0.20 Hz**. Head follows only the filtered coarse screen region, capped at **±2°/±1.5°**, with **0.6°** slow drift. `look_at_camera` remains zero for the entire read. |
| **2** | **Scroll and resume reading** — new `action_seq` whose action is `scroll`. | Keep the palm on the mouse. Native produces **2–4 wheel detents over 0.22–0.45 s**. Hold the new screen target for **0.35–0.70 s**, then return to the reading filter. No lean pulse, nod, gesture or whole-hand lift. The next agent scroll remains on its own 14–28 s content cadence. |
| **3** | **Glance at chat without breaking a silent read** — silent read/idle, at least **8 s** in state, no typing/reaction/chat answer, and the randomized **45–105 s** timer expires. | Turn to the 20°/−4° chat anchor over about **0.25 s**, dwell **0.8–1.5 s**, return over about **0.35 s**. Total visible excursion is roughly **1.4–2.1 s**. Hands and torso do not change. Do not glance during the scroll action itself. |
| **4** | **Search with the hands arriving first** — the agent has committed to `type` or `search`. | At **−0.50 s**, emit both hands `keyboard` while the body remains in its current state. Native completes the reach by **−0.15 s**. At zero, begin typing at `lean=0.40`. Use uneven **0.8–1.8 s** visual bursts. After typing ends, keep hands on keys **0.70 s**; if typing resumes within **1.8 s**, do not leave. Otherwise right returns to mouse and left to rest, then reading gaze resumes. |
| **5** | **Wait for a page without instantly fidgeting** — a click has occurred and the action subsequently becomes idle/`none`. | For the first **0.8 s**, retain the mouse contact and click/result attention. If still waiting, release lean toward **0.12** over about **0.6 s** and keep the head broadly on the screen. If waiting exceeds **3 s**, permit one **0.8–1.2 s** chat glance. No fidget before **25 s** in state. On `read`, restore reading posture over **0.55 s** and cancel any remaining wait beat. |
| **6** | **Read a viewer’s message before answering** — rising `chat_addressed`, voice not yet playing. | Keep the hands where they are. Move to `chat_read_lean=0.24`, turn to chat over **0.25 s**, and hold the read beat for **1.2–2.2 s** while the agent schedules the voice. No camera look, gesture or fidget. This is one visible read phase, not the start of a repeating read/camera cycle. |
| **7** | **Answer the viewer** — voice starts while `chat_addressed` remains true. | Suppress the generic speech-onset nod. At **+0.12 s**, start the single `chat_ack_nod=0.24`. Blend the head to the lens over about **0.28 s** and move from reading posture to `lean_back=0.18` over about **0.8 s**. Hold the initial lens address **1.4–2.4 s**, then return to screen/message. If speech is still active at the randomized **5.5–8.0 s** mark, make one **0.8–1.2 s** chat recheck. At voice end, hold the current gaze **0.35 s**, then return to screen and reading posture over **1.1 s**. |
| **8** | **Laugh once, with a static face** — `reaction=laugh`, outside typing; gestures and fidgets are suppressed. | Native starts a small chuckle envelope: base lean clears, `lean_back` rises toward **0.55** in about **0.25 s**, head tilt becomes a randomized **4–6°**, and the head lifts about **2°**. Add two decaying **0.7°-initial** torso pulses at roughly **3 Hz** during the first **0.75 s**. At **0.75 s**, look to the lens for **0.8 s**. Release tilt and camera first, then recover to the prior posture; total **2.2–3.0 s**. Hands stay in contact and the chair never moves. |
| **9** | **Be bored without confusing it with a two-second page load** — idle/`none` for at least **75 s**, no voice, chat address, reaction or pointer action. | Once per idle episode, ease to `lean_back=0.22` over **1.2 s**. Let the head drift only about **4°** away from the screen and **1°** upward; do not look at the camera. After at least **1 s** in that posture, permit one **1.0–1.8 s** desk/finger fidget. Hold the released posture **12–20 s** or until a new action. Any `read`, `search` or `click` immediately cancels the boredom rule and re-engages over **0.55 s**. |
| **10** | **Make a dry page comment without becoming a presenter** — `voice_playing` is true, `chat_addressed` is false, and the current content action is read/scroll/idle. | Keep the head on the content; no routine camera glance. After **0.12 s**, play the single `speech_start_nod=0.28`. Release the body toward `lean_back=0.12` over about **0.8 s**. A free-hand gesture occurs only if its irregular **14–26 s** speech timer fires, never before **0.45 s** of speech. When the voice ends, return to the exact prior reading posture over **1.1 s**; do not append a reaction or camera look merely because speech ended. |

---

# Final pod acceptance

Before calling the motion pass finished, record a scripted 10-minute session through the actual webcam shot, not only a skeletal debug view. It must contain a long read, repeated scrolls, a search, a short wait, a chat answer longer than 8 s, one think, one surprise and one laugh.

The recording and logs together must show:

1. No camera look during quiet reading.
2. No head motion following individual reading lines or pointer fixations.
3. No state/clip flapping and no hand contact acquired after visible typing begins.
4. No desk, keyboard, mouse or face penetration.
5. No procedural face, headphone, neck, drink or stretch substitution.
6. No repeated fixed-period nod, gesture or chat/camera cycle.
7. One reaction per event, followed by a return to the previous posture.
8. Additional procedural hips movement within **0.5 mm / 0.2°**.
9. Both maximum forward and maximum backward poses inside the webcam acceptance bounds.
10. A viewer can distinguish **reading, waiting, answering, thinking, surprise and a small laugh** without relying on facial animation.

What cannot yet be signed off is the quality of the underlying clips and their hand poses. If the sitting clip already contains broken wrist orientation or the typing clip has hands passing through keys, procedural layering will not rescue it; the third contact/transition take becomes necessary rather than merely desirable.