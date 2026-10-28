# Kimi consultation (2026-10-23): priorities

Model kimi-k3.1-pro, asked through tools/ask_kimi.py with the project documents attached; the brief is in `docs/streamer/kimi/q-priorities.txt`. The answer is advice to weigh, not project policy; decisions taken from it are recorded in DECISIONS.md.

# Technical direction

Treat **REPORT-20261023.md as the current state**; the “Voice: Nothing / Kill switch: None” inventory in PLAN.md is historical. The verified base is worth keeping: do not rewrite it around OBS, do not change TTS voices, and do not increase resolution or frame rate before the endurance work.

The 30-minute rehearsal proves orchestration and two recovery paths. It does **not** prove two-hour reliability, interesting two-hour behaviour, Vagon/Steam control, application audio, chat throughput, or facial believability. Thirteen utterances and five injected chat messages are a small sample.

My fixed decisions for the first complete version are:

- Keep **1920×1080, 24 fps, H.264/AAC, 10-minute local segments** and the ffmpeg director.
- Keep **Chatterbox K07**. Fix pacing and intelligibility rather than evaluating more voices.
- Make the **desktop/game the readable main view**; the Unreal monitor remains set dressing.
- Use **one slow, pausable, mouse/turn-based game**, not an FPS or action game. The 2–6-second agent loop is unsuitable for real-time gameplay.
- Put Vagon behind a short feasibility gate, with the current Chromium desktop retained as a working fallback.
- Ship **subtle jaw/viseme animation** for the first version. Do not put a MetaHuman transplant on the critical path.
- Build exactly **one public-platform integration**, not Twitch, YouTube and Kick together.
- Pass a two-hour local dress rehearsal before any public endurance stream. The first public technical stream should still be only 30 minutes.

The hours below include implementation and verification, but not owner waiting time, Vagon account approval, Steam installation time, or a custom likeness/hair art pass.

---

# 1. The next 15 work items, in order

## 1. Promote the current fixes to a clean, known-good candidate

- **Goal:** Restart the backend, redeploy the agent with the new chat policy, rerun the required eight-chat-line rehearsal, tag the exact source/native build/configuration, and rotate the API key pasted in chat. Check recordings, events and public chat history for that key before sharing anything further.
- **Why viewers care:** Safe requests must actually happen; viewers should not hear the obsolete canned room reaction or see safe requests ignored. A leaked key can also abruptly kill the service or become a public incident.
- **Hours:** **6**
- **Risk:** **Low**, except for an incomplete restart leaving old code running.
- **Verify:** From freshly restarted processes:
  - Safe open/search/scroll/back/read requests are executed and acknowledged by voice.
  - Non-actionable chat produces no obsolete “Not doing that one…” reaction.
  - Token theft, rules changes and unsafe requests receive one short refusal.
  - `/said` prevents double answers.
  - The old API key is revoked, the replacement is root-only, and no key appears in logs, screenshots or recordings.
  - Record build identifiers, native build v10/v12 or successor, K07 voice assets and prompt/configuration hashes.

## 2. Add a public-stream safety envelope and an emergency programme cut

- **Goal:** Enforce safety in the desktop/action broker, not merely in the model prompt. For the first streams, use allowlisted applications and domains; prohibit terminal/file manager, email, owner accounts, payments, downloads/uploads, Steam store/community/chat, credential entry and arbitrary chat-supplied URLs. Add a director control such as `POST /director/safety {"on":true|false}` which immediately selects a safe character/slate view and mutes application audio without restarting ffmpeg.
- **Why viewers care:** This prevents the stream from becoming a live demonstration of prompt injection, accidental account exposure, random purchasing or inappropriate browsing.
- **Hours:** **16**
- **Risk:** **High.** Vagon turns a browser sandbox into a general remote-input problem.
- **Verify:**
  - Run at least 30 hostile chat and webpage cases, including indirect prompt injection on an otherwise allowed page.
  - Zero forbidden actions reach `/desktop/act`.
  - Existing kill still stops autonomous action and speech within **1 second**.
  - Safety view plus application mute engages within **500 ms** in the local preview.
  - STOP also prevents queued speech from restarting.
  - Steam/Vagon uses a clean streaming-only profile with no private friends, messages, real name or stored payment view.
  - The operator understands that killing output does **not** retract words or frames already delivered to viewers.

## 3. Add one operational status view and run a two-hour baseline soak

- **Goal:** Instrument the existing local-Chromium version before adding more complexity. Expose decision age, last action outcome, model provider/errors, browser restarts, voice queue/synthesis time, speaking state, chat backlog, director PID/segment/bytes, audio underruns, disk free, process RSS, GPU memory and Vagon state when applicable.
- **Why viewers care:** Most embarrassing streams do not fail dramatically; they slowly become frozen, silent, repetitive or hours behind on chat.
- **Hours:** **10**, including the run and initial review.
- **Risk:** **Medium.**
- **Verify:** A fresh-boot, 120-minute local run produces:
  - At least **7,200 seconds ±2 seconds** of continuous programme, excluding deliberate pre-roll.
  - No director restart, no segment gap over one second and no persistent frozen video.
  - No unbounded voice/chat queue and no monotonic memory growth after warm-up.
  - No CUDA OOM while Unreal, Chatterbox and encoding are concurrently active; retain roughly **2 GB GPU headroom** during a synthesis/render stress test.
  - Successful recovery from another browser kill and primary-model failure.
  - Disk requirement calculated from actual segment sizes:  
    `recorded_bytes / recorded_seconds × 9,000 seconds × 2` for a 2.5-hour session with safety margin.
  - At the observed 51 decisions per 30 minutes, the default 240 calls/hour ceiling is sufficient; actual provider usage is nevertheless logged.

## 4. Time-box a Vagon/Steam feasibility spike

- **Goal:** Prove the unknowns before committing to full integration. The owner supplies the account, Stream Link, budget and terms confirmation. Configure 1080p or scale-to-screen, Mouse Control, US keyboard, a session/idle allowance of at least three hours, and **audio on**—the current “audio off” setting cannot provide game sound.
- **Why viewers care:** A cloud-PC failure on stream otherwise means a blank desktop, repeated connect clicks or a game with no sound.
- **Hours:** **8 engineering hours**, plus owner setup.
- **Risk:** **High.**
- **Verify in one session lasting at least 60 minutes:**
  - Whether a visitor sees a full desktop or only one application window.
  - Whether Steam and the chosen game can actually launch.
  - Whether remote application audio reaches the kiosk Chromium session.
  - Point input, scrolling and US-keyboard text at 1280×720 observation and 1920×1080 remote resolution.
  - One forced disconnect/reconnect and one ended-session re-entry.
  - Pod egress to Vagon and measured action-to-visible-result latency.
  - No Stream Link path/query in logs.
  - Actual session cost. At the documented rates, three machine-hours cost **$4.50–$8.46**, plus **$0.67/day storage and $0.67/day maintenance**, with plan fees still unknown.

**Gate:** The 28-hour integration estimate below applies only if full required input, application access and audio are demonstrated. If Vagon exposes only a browser application or no visitor audio, Steam/audio feasibility cannot be inferred from the supplied material.

## 5. Complete the Vagon pixel agent and one real game path

- **Goal:** Preserve `mode` and `remote_ready` through the agent’s `normalize()`, support point-only actions without marks, pause all input while disconnected, and verify outcomes by pixel/screen changes rather than claiming success after sending input. Add explicit coordinate scaling and bounded reconnect behaviour. Preinstall and use **The Battle for Wesnoth**, offline single-player, as the first test game: free, turn-based and mouse-driven.
- **Why viewers care:** He performs observable, real actions instead of clicking blindly or commentating on a game he is not controlling.
- **Hours:** **28**
- **Risk:** **High.**
- **Verify:**
  - At least **47/50 fixed web/UI actions** and **29/30 simple game inputs** land correctly.
  - Observation-to-remote coordinates use  
    `remote_x = observed_x × remote_width / observed_width`, and equivalently for Y.
  - No input is sent while `remote_ready` is false.
  - Three induced reconnects produce no click storm; useful control resumes within **60 seconds** or the system enters local fallback.
  - Thirty minutes of actual game progress, not merely reaching the main menu.
  - Steam overlay, notifications, friends and store are disabled or inaccessible.
  - Local Chromium becomes a safe, presentable fallback within **30 seconds** of declaring Vagon unavailable.

## 6. Fix the desk-pin/camera defect and lock the shots

- **Goal:** Make body ownership and camera ownership separate: the desk pin alone writes the body transform; selecting or guarding a camera must never move the actor. Correct the frontal webcam camera and retain the spectator camera as a diagnostic view. Keep `AuthoredReach` disabled until its clip is separately approved.
- **Why viewers care:** A body jumping out of frame is more damaging than modest animation. Stable framing also makes subsequent facial work judgeable.
- **Hours:** **12**
- **Risk:** **Medium.**
- **Verify:**
  - Body actor transform is identical before and after every camera/layout change.
  - Face, hands and torso remain inside their intended frames through idle, reading, typing, talking and reacting.
  - A 20-minute recording contains no camera-induced body displacement, sudden FOV change or desk intersection.
  - The default activity composition keeps the actual `:102` desktop readable; the in-game monitor is never relied on for reading.
  - The mouse/reach state cannot re-enable the reviewed-and-rejected body movement.

## 7. Finish the desk performance and monitor presentation

- **Goal:** Build a restrained performance system from the existing clips: several weighted seated/reading variations, typing only during actual text input, breathing without visible periodic reset, gaze changes with dwell time, one proportionate reaction per event, and talking state driven by actual PCM playback rather than queued text. Retain the verified **0.24-second** cross-fades. Update the native monitor from changed desktop frames at an **8 fps cap**, not 2 fps; static pages should not cause needless copies.
- **Why viewers care:** The current single seated loop will become conspicuous over two hours, and typing/nodding at the wrong time makes him appear to be a puppet playing an unrelated animation.
- **Hours:** **24**
- **Risk:** **Medium.**
- **Verify:**
  - State and action agree for 100 sampled actions; he never types while only reading.
  - Talking ends within **80 ms** of actual voice PCM ending.
  - No pose pop, root slide, hand clipping or repeated identical reaction loop in a 30-minute full-speed review.
  - The monitor reaches 8 updates/second on changing content without violating the GPU/frame-time budget.
  - Mouse clicks retain the safe reading pose until a separate reach clip passes review.

## 8. Add application audio, ducking, loudness control and measured sync

- **Goal:** Implement the PulseAudio/ffmpeg chain in section 4. Capture local Chromium and Vagon-kiosk audio, mix it with the existing direct voice PCM, duck applications under speech and preserve audio across every layout and segment.
- **Why viewers care:** Silent games and silent web video feel broken even when the character voice works. Uncontrolled game audio can also make the voice unusable.
- **Hours:** **14**
- **Risk:** **Medium.**
- **Verify:**
  - Test tone, browser sound, game sound and voice all appear in a completed recording.
  - No echo or double-captured voice.
  - No audio underruns and no muted audio stream in any segment.
  - Local A/V offset is within **50 ms**, Vagon offset within **80 ms**, and drift over two hours is under **20 ms** after calibration.
  - Output peaks stay at or below approximately **−1 dBFS**; speech remains clearly above ducked application sound.
  - Pulling the public network connection does not stop local audio/video recording.

## 9. Fix voice/chat scheduling and put captions in the programme

- **Goal:** Separate urgent, chat and low-priority commentary scheduling. Keep accepted chat requests from starving behind unsolicited commentary, deduplicate answers, cap spoken lines at roughly two sentences/18 seconds, and synthesize sentence-by-sentence. Put captions generated from the exact approved spoken text into the programme; if TTS fails, show those captions publicly rather than only writing them to `events.jsonl`.
- **Why viewers care:** A response arriving 40 seconds late, repeated commentary or speech over speech quickly destroys the illusion of attention.
- **Hours:** **18**
- **Risk:** **Medium.**
- **Verify:**
  - With an empty voice queue, p95 time from finalized `say` text to playback is under **8 seconds**, including the observed 2.8–5-second synthesis.
  - Under a test of 20 messages in five minutes, every safe message is answered, visibly queued or explicitly deferred; no viewer starves through two queue rounds.
  - Actionable requests are acknowledged promptly and either execute within **90 seconds** or have a visible queued state.
  - No exact duplicate answer, no answer after STOP, and no low-priority line older than its TTL is unexpectedly spoken.
  - Caption start/end agree with `speech/timeline.jsonl` within **80 ms**.
  - Voice failure leaves captions and safe desktop behaviour running.

## 10. Give the agent an actual two-hour rundown and provider-failure behaviour

- **Goal:** Replace endless opportunistic scrolling with a flexible rundown: **5-minute introduction, 25-minute web topic, 40-minute game block, 20-minute viewer-request/web block, 25-minute game block, 5-minute wrap-up**. Store topic notes and already-stated facts, prepare two safe fallback topics, and make Claude-primary/Kimi-fallback use the same action schema and safety policy. If both fail, use quiet safe behaviour without duplicating timed-out actions.
- **Why viewers care:** Real browsing alone is not a programme. Viewers need a discernible activity, continuity and an ending.
- **Hours:** **18**
- **Risk:** **Medium.**
- **Verify:**
  - Three consecutive content blocks work in a 45-minute test without manual steering.
  - No exact repeated non-refusal utterance and no contradictory recap of earlier activity.
  - There is no silent stretch over **90 seconds** unless meaningful visible gameplay/action and application audio are carrying the scene.
  - Primary-model timeout cannot cause the same action to run again through the fallback.
  - Projected calls remain within **480 for two hours**, with provider budget available for a three-hour stream day.
  - Persona constraints, including never claiming to be human, survive provider failover.

## 11. Implement first-version lip sync with a new jaw bone and utterance cues

- **Goal:** Add one carefully weighted jaw bone to the existing head, build only the mouth interior required to avoid a hollow opening, and drive subtle opening from cues generated after TTS synthesis. Do not use raw application audio or unsmoothed amplitude chatter. See section 3.
- **Why viewers care:** A completely closed mouth during an obvious voice line is immediately noticeable in the owner’s desired webcam shot.
- **Hours:** **30**, including a four-hour geometry prototype.
- **Risk:** **High**, because head topology is unknown.
- **Verify:**
  - Twenty varied English lines, including the existing octopus material, plosives and long vowels.
  - Mouth remains closed during silence and for at least the final audio release; no response to browser/game voices.
  - Jaw/audio offset stays within **80 ms** at playback.
  - No stretched eyes, neck seam, mouth interior hole or exaggerated ventriloquist movement at the actual delivery shot size.
  - Desk clips and the existing Walk/Idle animations still work after skeleton reimport.
  - If the four-hour geometry prototype cannot open the mouth without destroying the face, stop this approach rather than shipping a deformed head. The report does not provide enough topology information to predict that outcome.

## 12. Turn the director into a real live programme, isolated from publishing failures

- **Goal:** Composite all layouts continuously in one director process. Make `desktop` the normal web/game view with a modest character facecam; reserve `character` for introduction, outro and safety, and use `split` only where both remain legible. Keep hard cuts—they are normal television grammar—but cut deliberately at sentence/action boundaries. `layout.jsonl` becomes diagnostic, not a required post-production plan. Keep local recording independent of the network publisher.
- **Why viewers care:** The current character view with a 480×270 desktop PiP is not a readable two-hour browsing stream, and post-compositing does not help live viewers.
- **Hours:** **20**
- **Risk:** **Medium-high.**
- **Verify:**
  - Twenty layout changes in 60 minutes cause zero ffmpeg restarts, audio gaps or timestamp discontinuities.
  - Web text and game UI are legible at the delivered 1920×1080 view.
  - Safety view and captions work in every layout.
  - A 60-second publishing-network failure leaves the local master continuous; the publisher reconnects independently.
  - The public test encode uses a two-second keyframe interval and a measured sustainable bitrate—start around **6 Mbit/s video plus AAC**, rather than increasing frame rate or resolution.
  - A human watches the programme output, not just the three individual sources.

## 13. Connect one public destination and its native chat

- **Goal:** For a concrete plan, use **Twitch** as the reference launch integration: one publisher configuration and one read-only chat connector over Twitch IRC/TLS. Use a dedicated bot account/token, pass sanitized messages through the existing `chat.check` and agent policy, deduplicate by message ID, handle PING/reconnect, and never give the model the OAuth token or stream key. Do not build YouTube or Kick connectors now.
- **Why viewers care:** Native-platform viewers otherwise cannot participate in the supposedly interactive stream.
- **Hours:** **16**
- **Risk:** **Medium.**
- **Verify:**
  - Fifty test messages, including spam, links, token requests and duplicate deliveries, produce no duplicates or forbidden action.
  - Connector reconnect does not replay an entire backlog as new requests.
  - Token and stream key never enter screenshots, events or process-list arguments.
  - Chat ingestion survives a 60-second network interruption without stalling the agent.
  - Slow mode/operator moderation and link handling are configured before public promotion.

**Uncertainty:** No launch platform is specified in the attachments. Twitch is my planning choice, not a known owner decision. If the owner has already selected another destination, item 13 is the item to re-plan; the other fourteen remain valid.

## 14. Run the full two-hour dress rehearsal with scheduled failures

- **Goal:** Fresh boot, exact release configuration, real Vagon/game path, real application audio, native chat path where possible, and a full two-hour recording. Inject failures rather than hoping they happen.
- **Why viewers care:** This is the last practical way to find interactions that unit tests and highlights conceal.
- **Hours:** **16**, including a full-speed review.
- **Risk:** **High until passed.**
- **Verify:**
  - At 00:20, kill Chromium; useful activity resumes within 30 seconds.
  - At 00:40, fail the primary model; no duplicate action or unsafe fallback occurs.
  - At 01:00, interrupt Vagon; reconnect or local fallback follows the verified path.
  - At 01:20, cut/restart voice; captions and scene remain coherent.
  - At 01:35, interrupt publishing; local recording remains continuous.
  - Finish with 120 minutes of usable programme, no unresolved severity-1/2 defect, no camera displacement, acceptable lip/audio sync and complete segments.
  - Review the **entire recording at 1×**, including silence, not just `streamer_highlights.py`.

## 15. Freeze the release and make the single-operator day reversible

- **Goal:** Freeze source, native build, prompts, model routing, K07 assets, animation assets and director configuration. Produce the runbook below, a safe starting page/game state, a local-desktop fallback and explicit go/no-go criteria. No feature work after the dress rehearsal without rerunning affected tests.
- **Why viewers care:** The operator should never improvise credentials, camera settings or service restarts in public.
- **Hours:** **8**
- **Risk:** **Low.**
- **Verify:**
  - One operator performs start, preflight, kill/safety drill, resume and stop using only the document.
  - Provider and Vagon budgets cover three hours; Vagon remaining session time covers the whole stream day.
  - Local recording and public output can be stopped independently.
  - Vagon can be ended manually to stop cost.
  - Any failed mandatory gate results in another local rehearsal, not “trying it live.”

**Total:** approximately **244 hours**. Dropping Vagon from the first release would save only about 36 hours and would not remove the need for the endurance, audio, safety and presentation work.

---

# 2. The three biggest public-stream embarrassment risks

## Risk 1: He does or reveals something unsafe, and the operator cannot undo it

The untrusted inputs are not just chat. Webpage text, search results, Steam UI and Vagon screens all influence a model with real input capability. The current Vagon implementation is particularly sensitive because address-bar and keyboard input can bypass assumptions made for a marked-web-element browser. The already-exposed API key demonstrates that secret hygiene is not theoretical.

**Mitigation:**

- Complete items 1 and 2 before public promotion.
- Use clean, streaming-only accounts and a restricted Vagon desktop.
- Enforce capabilities at the action broker; never rely on “the model will refuse.”
- Do not read raw chat/web text aloud verbatim.
- Keep one operator watching local preview continuously, with kill and safety-view/mute controls.
- Rotate exposed credentials and redact them from any artefacts before distribution.
- Treat the first public session as a 30-minute technical stream, not the two-hour endurance launch.

**Residual risk:** A kill switch stops future output; it cannot erase speech or frames already transmitted. No broadcast delay is documented, so do not claim that one exists.

## Risk 2: The stream visibly stalls or loses control during the two-hour/Vagon path

Only one induced browser crash and one model error were exercised. That is useful fault-path coverage, not a reliability statistic. Vagon still has the known agent mismatch—marks expected, `mode`/`remote_ready` discarded—and unknown desktop/audio/session behaviour. Two hours also introduces disk, VRAM, TTS queue, reconnect and content repetition problems absent from a 30-minute run.

**Mitigation:**

- Do the Vagon spike before full integration.
- Use only a slow, pauseable game.
- Never send remote input while the session is not ready.
- Keep the verified local Chromium desktop as an immediate content fallback.
- Add bounded queues, decision IDs/idempotency and useful status metrics.
- Pass the two-hour rehearsal with repeated failures and a publisher outage.
- End or fall back cleanly after 60 seconds of unrecoverable cloud state; do not let the model keep clicking.

## Risk 3: It technically works but looks and sounds fake or unpleasant

A static mouth, rigid eyes, one seated loop, a 2 fps monitor and a bad webcam frame will be obvious in a frontal shot. Conversely, an exaggerated jaw on unsuitable geometry can look worse than no lip sync. Voice-only recordings, loud game audio and late chat answers create a separate “broken stream” impression.

**Mitigation:**

- Fix camera/body ownership before facial work.
- Use the desktop as the main activity view; do not ask the small Unreal monitor to carry content.
- Keep the first jaw motion subtle and judge it at actual facecam size.
- Add application audio, ducking, limiter and measured sync.
- Use visible captions and real queue fairness.
- Watch the full rehearsal at normal speed. Metrics cannot assess uncanny motion, boring browsing or whether a joke/reaction lands.

---

# 3. Lip sync on a Mixamo body with no face bones

## Common timing design

Whichever facial asset is used, do not make Unreal guess speech from the final mixed programme audio.

1. Chatterbox finishes an utterance WAV.
2. Run **Rhubarb Lip Sync** on that WAV to generate timed mouth cues. It is free/open source and suitable for English. This is per-utterance processing, not a magical real-time facial solve.
3. Give Unreal the utterance ID and cue file before playback.
4. Schedule PCM playback and cue playback against the same `t0`; the native animation samples the cue timeline from actual audio progress.
5. If Rhubarb cannot meet a measured **one-second processing budget** on the pod, use a smoothed voice-WAV envelope for the jaw fallback.
6. Never drive his mouth from browser/game audio.

The existing 2.8–5-second synthesis delay remains. Cue generation adds to it and therefore belongs in the item-9 latency measurements.

## Option A: Replace the head with a free rigged head

- **Work:** Generate an adult head, match scale/proportions and skin tone, cut/attach at the neck, preserve the Mixamo body skeleton and animation, add facial bones or morphs, author at least 6–8 viseme shapes plus blink, and build a small live curve driver.
- **Hours:** **45–80** for a competent technical animator, including a basic driver.
- **Visual quality:** **3/5**, potentially 4/5 with art time. Real mouth deformation and blinking are possible, but likeness change, neck seam, hair mismatch and skin shading are substantial risks.
- **Free downloads:**  
  - **Blender**  
  - **MPFB2** and the MakeHuman base/assets, checking the licence of each bundled asset pack  
  - Blender’s included **Rigify** where useful  
  - **Rhubarb Lip Sync**
- **Main failure mode:** A technically functional head that no longer looks like the established character.
- **Verdict:** Better long-term than a jaw-only head, but not the shortest safe path.

## Option B: MetaHuman head retarget/attachment to the Mixamo body

- **Work:** Fit a MetaHuman head to the body, remove/hide the original head without leaving neck geometry conflicts, transfer head/neck motion from the Mixamo body, match skin/hair at the seam, and drive facial curves live. Add procedural blink and small brow/eye motion; merely attaching the head does not supply a performance.
- **Hours:** **70–110**, including viseme driving and basic facial life.
- **Visual quality:** **4–5/5** if the fit and performance are good; potentially worse than the current character if the seam or proportions are wrong. This is the only listed route I would expect to withstand a sustained realistic close-up.
- **Free downloads:**  
  - Epic’s **MetaHuman tools** appropriate to the installed UE version  
  - A free preset/custom MetaHuman head  
  - MetaHuman sample/control-rig assets supplied by Epic  
  - **Rhubarb Lip Sync** for utterance timing
- **Do not require:** MetaHuman Animator, an iPhone, a paid capture rig or a marketplace animation pack for this basic live viseme path.
- **Uncertainties:** The UE version is not given, so the exact Creator/plugin/Bridge download path cannot be specified. Epic account and current licence/EULA terms must be checked.
- **Verdict:** **Use this for visual v2 if close-up realism is mandatory.** Do not put it on the first-public-stream critical path.

## Option C: A 2D mouth overlay in the head texture/material

- **Work:** Export the UV layout, paint 6–8 mouth textures, isolate the head material and select/blend textures from the utterance cues.
- **Hours:** **12–20** if the mouth already has unique, usable UVs.
- **Visual quality:** **1–2/5**. Acceptable for a small or deliberately stylized face; not credible for the stated realistic frontal webcam.
- **Free downloads:** Blender for UV inspection, **Krita or GIMP**, Rhubarb.
- **Main failure modes:** No real mouth opening, lighting/shading mismatch, and mirrored/overlapping UVs causing the mouth image to appear elsewhere. Re-UV work adds time.
- **Verdict:** **Do not use it on this realistic character.** It is a fallback for a tiny face icon, not the owner’s reference shot.

## Option D: Add an audio-driven jaw bone — selected for v1

- **Work:** In Blender, add a jaw bone parented to the actual head bone while preserving the existing skeleton and animation compatibility. Weight only suitable lower-lip/jaw/chin vertices. Add a simple dark mouth bag and minimal interior geometry if opening reveals a hollow head. Drive approximately **0–8° normally, 12° maximum**, with smoothed attack/release and Rhubarb-timed openness. No sideways jaw motion.
- **Hours:** **24–36**; budget **30** in the work plan.
- **Visual quality:** **2–3/5**. Considerably better than a static closed mouth at medium/small facecam size, but still closer to a ventriloquist than full human speech.
- **Free downloads:** Blender and Rhubarb only; no replacement character asset is required.
- **Main failure mode:** The existing mesh may lack sufficient lip loops or mouth geometry. That cannot be determined from the report.
- **Verdict:** **Ship this first, conservatively.** It solves the conspicuous “voice with a sealed mouth” problem without changing identity.

Lip sync alone will not create a realistic face. Without blinks, cheek movement and brow/eye behaviour, an extreme close-up will still expose the rig. Shot size must remain part of the first-version solution.

---

# 4. Application-audio chain on the headless Linux pod

## Decision and signal flow

Use **one per-user PulseAudio daemon with a null sink**. Do not add PipeWire, ALSA loopback or OBS for this release. Do not run PulseAudio as root.

```text
Local Chromium ──────────────────────────────┐
                                             ├─ PulseAudio playback
Vagon game/browser audio                     │        │
  → Vagon session                            │        ▼
  → kiosk Chromium on :102 ──────────────────┘   null sink: sub01_apps
                                                        │
                                                        ▼
                                              sub01_apps.monitor
                                                        │
                                                        ├──────────────┐
                                                                       ▼
Voice server → continuous 48 kHz stereo s16le voice.pcm → duck/mix/limit
                                                                       │
:99 / :102 x11grab → existing video compositor                         │
                                             └───────────────┬─────────┘
                                                             ▼
                                               H.264/AAC local segments
                                               + independent publisher
```

Important decisions:

- Capture **`sub01_apps.monitor`**, not the sink itself.
- Keep voice on the existing direct PCM FIFO. Do **not** play voice into `sub01_apps`, or it will be captured twice.
- Do not use a PulseAudio loopback module; a null-sink monitor is sufficient.
- The Vagon session must have audio enabled. If Vagon supplies video without visitor audio, this chain cannot recover game sound; cloud-side capture or a different Vagon configuration would then be required.
- Start PulseAudio before Chromium/Vagon kiosk so they inherit the correct environment.

## Minimal PulseAudio setup

Package names below are for Debian/Ubuntu; the pod distribution is not stated.

```bash
apt-get install -y pulseaudio pulseaudio-utils
# ffmpeg must show a PulseAudio device:
ffmpeg -hide_banner -devices 2>/dev/null | grep -i pulse
```

Create the runtime directory on every boot, and a readable config owned by uid 1001:

```bash
install -d -o unreal -g unreal -m 700 /run/user/1001

P=/home/unreal/.sub01-private/streamer

cat >"$P/pulse.pa" <<'EOF'
.fail
# Unix socket only; do not load a network/TCP audio protocol.
load-module module-native-protocol-unix

load-module module-null-sink \
  sink_name=sub01_apps \
  rate=48000 \
  channels=2 \
  format=s16le \
  channel_map=front-left,front-right \
  sink_properties=device.description=SUB01_Apps

set-default-sink sub01_apps
EOF

chown unreal:unreal "$P/pulse.pa"
```

Have `streamer_up.py` supervise this as uid 1001, before the desktop runner:

```bash
runuser -u unreal -- env \
  HOME=/home/unreal \
  XDG_RUNTIME_DIR=/run/user/1001 \
  pulseaudio -n -F "$P/pulse.pa" \
    --daemonize=no \
    --exit-idle-time=-1
```

For all `pactl`, Chromium and ffmpeg processes, use:

```bash
HOME=/home/unreal
XDG_RUNTIME_DIR=/run/user/1001
PULSE_SERVER=unix:/run/user/1001/pulse/native
export HOME XDG_RUNTIME_DIR PULSE_SERVER
```

Checks:

```bash
pactl info
pactl list short sinks
# Expected: sub01_apps

pactl list short sources
# Expected: sub01_apps.monitor
```

Launch the desktop/Vagon kiosk with that environment. Do not pass `--mute-audio`; remove it if a launcher default supplies it. Browser autoplay may still require a real click, so test with a local page that starts audio from a click. `--autoplay-policy=no-user-gesture-required` can be used for the controlled test page, but should not be treated as a substitute for checking actual browser routing.

While sound is playing:

```bash
pactl list short sink-inputs
```

If there is no sink input, ffmpeg cannot capture application sound regardless of how healthy the null sink looks.

## Standalone capture test

Start this recording first:

```bash
ffmpeg -y -hide_banner \
  -f pulse -i sub01_apps.monitor \
  -t 8 -c:a pcm_s16le /tmp/sub01-apps-test.wav
```

In another shell with the same environment, play a five-second tone into the null sink:

```bash
ffmpeg -v error -f lavfi \
  -i "sine=frequency=1000:sample_rate=48000:duration=5" \
  -f s16le -ac 2 -ar 48000 - |
pacat --raw --device=sub01_apps \
  --format=s16le --rate=48000 --channels=2
```

The WAV must contain the tone. Repeat with an actual browser sound and then the Vagon game. A test tone alone proves only the audio plumbing.

## Integration into the existing director

Keep the existing x11grab inputs and voice FIFO. Add the PulseAudio monitor as another input. For example, if video inputs are 0/1, application audio is input 2 and voice is input 3:

```bash
# Input 2: application monitor
-thread_queue_size 1024 \
-f pulse -i sub01_apps.monitor

# Input 3: existing continuous voice PCM
-thread_queue_size 4096 \
-f s16le -ar 48000 -ac 2 \
-i /home/unreal/.sub01-private/streamer/voice.pcm
```

Merge this audio section into the current `-filter_complex`, preserving the existing video output label:

```text
[2:a]aresample=48000:async=1:first_pts=0,volume=0.35[app];

[3:a]aresample=48000:async=1:first_pts=0,
     asplit=2[voice][duckkey];

[app][duckkey]
  sidechaincompress=
    threshold=0.03:ratio=6:attack=15:release=300
  [ducked];

[ducked][voice]
  amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,
  alimiter=limit=0.891
  [aout]
```

Then map `[aout]` and encode:

```bash
-map "[aout]" -c:a aac -b:a 192k -ar 48000
```

These gain/compressor values are starting points, not a substitute for listening. `volume=0.35` is roughly −9 dB on application audio before ducking. The limiter value 0.891 is approximately −1 dBFS sample peak.

Check the installed ffmpeg filter options:

```bash
ffmpeg -h filter=amix
ffmpeg -h filter=sidechaincompress
```

On an old ffmpeg without `amix`’s `normalize` option, upgrade or account for its automatic input attenuation; otherwise the mix will be quieter than expected.

Measure completed output rather than judging only the voice’s old −3 dBFS peak:

```bash
ffmpeg -hide_banner -i completed-segment.mp4 \
  -map 0:a -af ebur128=peak=true -f null -
```

Use a fixed, measured gain structure for live output. Target approximately **−16 LUFS integrated programme loudness**, speech clearly intelligible over applications, and no clipped peaks. Do not insert a constantly readjusting loudness effect immediately before launch.

## Sync and latency

Latency and sync are different: the chain can be 100 ms late and still produce a perfectly synchronized recording.

Expected planning ranges, **not measurements from this pod**:

| Path/component | Expected additional latency |
|---|---:|
| Null-sink playback to monitor capture | Typically about **10–40 ms** |
| ffmpeg buffering, resampling/mix and AAC | About **30–100 ms** |
| Total local application-audio path | Plan for **50–150 ms** |
| Direct voice PCM transport | Roughly one/few audio buffers; negligible beside TTS |
| Chatterbox synthesis | Existing measured **2.8–5 s per line**, unchanged |
| One video frame at 24 fps | **41.7 ms** |
| Vagon remote action/audio/video transport | **Unknown until measured** |

For Vagon, the local chain adds its 50–150 ms **after the kiosk browser plays the already-delivered remote audio**. It does not reveal the cloud-side delay. Do not quote a Vagon action-to-photon number until item 4 measures it.

Calibration procedure:

1. Use a local HTML test that, from one user gesture, flashes a high-contrast rectangle and emits a short 1 kHz beep.
2. Record it through the complete director, not a standalone audio command.
3. Measure the constant offset, then delay the earlier path by that amount; use `adelay=NN|NN` when application audio is the path needing delay.
4. Keep `aresample=async=1` for small clock corrections, but do not mistake it for correction of a fixed offset.
5. Repeat at the end of a two-hour capture and after a Vagon reconnect.

Accept **≤50 ms local skew**, **≤80 ms Vagon skew**, and **<20 ms drift over two hours**. Lip animation should remain within approximately **80 ms** of actual voice playback.

---

# 5. One-page stream-day runbook skeleton

Bracketed publisher commands are placeholders to be filled by items 12–13; they are not represented as commands that exist today.

```text
SUB-01 STREAM DAY
Date/UTC: ______  Operator: ______  Build/tag: ______
Planned public duration: ______  Destination/channel: ______
Local fallback ready: YES / NO     Vagon required today: YES / NO

A. GO / NO-GO — T-60 TO T-20
[ ] Exact release candidate deployed; no unreviewed camera/agent/audio patch.
[ ] No exposed credential in chat, screenshots, logs, command line or recordings.
[ ] Clean desktop/Steam profile; safe start page and offline game loaded.
[ ] Model and voice providers healthy; budgets cover 3 hours.
[ ] If Vagon is required: remaining session/idle allowance covers the whole day;
    remote audio, mouse, keyboard and game verified in preflight.
[ ] Disk free >= max(30 GB, 2× measured 2.5-hour projection).
[ ] Public upload >= 2× planned output bitrate; local recording does not depend on it.
[ ] GPU synthesis+render test leaves headroom; no CUDA OOM or thermal fault.
[ ] Full 2-hour dress rehearsal passed; no open severity-1/2 defect.
[ ] Operator has watched/listened to the actual programme output with headphones.

B. START — LOCAL ONLY, NOTHING PUBLIC YET
    S=/home/unreal/.sub01-private/latest-source-20261023
    P=/home/unreal/.sub01-private/streamer
    T=/home/unreal/.sub01-private/operator-token

[ ] Native game is running with -Sub01StreamerVisual; $P/game.pid is valid.
[ ] Start backend desk hold using the REPORT curl command:
    POST 127.0.0.1:8830/api/home/streamer {"operation":"start"}
[ ] Start services using the complete REPORT streamer_up.py start command,
    including director XAUTHORITY and --game-pid-file arguments.
[ ] Run streamer_up.py status. All workers healthy; no restart loop.
[ ] GET /api/home/streamer:
    active=true, activity=use_computer at desk, expected routines paused.
[ ] pactl: sub01_apps and sub01_apps.monitor exist; expected app sink-input exists.
[ ] Camera/body check: no body jump; face/hands safe; desktop text readable.
[ ] Browser/model recovery and Vagon state healthy; agent is not in quiet mode
    unless deliberately declared.
[ ] Kill drill: kill -> actions/speech stop <=1 s -> scene remains presentable ->
    safety view/mute works -> resume -> one harmless action succeeds.
[ ] Record a separate 20–30 s preflight containing voice, browser/game audio,
    captions, a layout change and a sync flash/beep. Watch and listen to it.
[ ] Latest completed recording segment is playable; recording bytes are growing.
[ ] Public chat moderation is ready.

    IF ANY MANDATORY CHECK FAILS: DO NOT PUBLISH.

C. PUBLISH AND DURING
[ ] Start local programme recording before publishing.
[ ] [PUBLISHER START]; verify viewers receive picture AND both audio classes.
[ ] Announce a short, safe opening; do not troubleshoot accounts in public.
[ ] Every 5 minutes and at each 10-minute segment roll, check:
    - agent last decision/action age and outcome;
    - model provider/errors and remaining budget;
    - voice speaking/queue/synthesis time; chat pending/answered;
    - browser/Vagon readiness and reconnect count;
    - director PID, current segment growth, disk free;
    - application/voice levels, sync and captions;
    - GPU memory and any restart counter.
[ ] Operator watches local preview continuously and moderates public chat.
[ ] No manual desktop clicking while the agent is active.
[ ] Log every incident as UTC time + symptom + action + recovery time.

D. INCIDENTS — FIRST ACTION IS ALWAYS THE SAFE ONE
Unsafe speech/screen/secret:
    1. streamer_up.py kill immediately.
    2. Director safety ON: safe view + application mute.
    3. [PUBLISHER STOP] if anything unsafe may still be leaving the pod.
    4. Record UTC. Resume only after a clean page/state and explicit operator check.

Browser crash:
    Allow automatic recovery. If useful control is not back in 60 s,
    hold safety/local fallback; do not allow repeated blind clicks.

Primary model failure:
    Allow verified Kimi fallback or quiet safe mode. If both are unhealthy for
    5 minutes, use the prepared safe fallback content or end the segment.

Voice stuck/repeating:
    POST 127.0.0.1:8835/stop with the admin token.
    If behaviour continues, kill autonomy. Captions may continue.
    Never restart the whole director merely to fix TTS.

Application audio bad/clipping:
    Mute application audio; continue voice/captions only if intelligible.
    If all programme audio is gone, end the public stream.

Vagon disconnect:
    Agent sends no input while not ready. Reconnect once through the verified path;
    after 60 s use local fallback. Do not expose the Stream Link.

Publisher/network failure:
    Keep local recorder running. Restore publisher independently.
    If public loss exceeds 60 s, end cleanly rather than repeatedly reconnecting live.

Recorder failure, Unreal crash, CUDA OOM, or uncontrolled behaviour:
    Safety ON, stop publishing, kill autonomy. Do not improvise a live rebuild.

E. NORMAL STOP AND POST
[ ] Deliver short outro; stop accepting new chat requests.
[ ] [PUBLISHER STOP] first; confirm the public endpoint is offline.
[ ] Run the complete REPORT streamer_up.py stop command.
[ ] POST backend /api/home/streamer {"operation":"stop"}.
[ ] End the Vagon session in the owner console/API when available; confirm cost stopped.
[ ] Confirm the final MP4 segment closes and all expected segments have audio/video.
[ ] Preserve recordings/, events.jsonl, speech/timeline.jsonl, layout.jsonl,
    status/metrics and the incident list.
[ ] Record actual duration, actions, chat service, speech errors, restarts,
    Vagon cost and any sync drift.
[ ] If a credential appeared publicly: stop distribution, revoke/rotate it,
    and treat the recording/chat history as sensitive before editing or sharing.
```

**Release rule:** until item 14 passes with the exact candidate, the correct next output is another local rehearsal—not a public stream.