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

## 15:27-15:34 UTC: "fomo" removed from the chat filter, backend restarted as r7b

- **Kimi:** APPROVE (it had been overloaded overnight, `engine_overloaded_error`).
- **Runtime-source patched** (backup in `/home/sub01-review-20261027/fomo-backup.tgz`).
- **Backend downtime 15:27:15-15:34:05.**
  - The first relaunch (r7) was refused with "Production agent STOP must remain held".
  - Rule for later restarts: **hold STOP (`streamer_up.py kill`) BEFORE launching the coordinator**, then `resume` once
    `/healthz` 8830/8831 answers.
- **Now running:**
  - coordinator `/root/sub01-owner-backend-resume-r7.py`, with its memory count read from the stopped state, not the
    hard-coded 356;
  - argv in `/home/sub01-review-20261027/coord-r7b.argv`;
  - state `owner-state-oct15-20261027-r7b`, **382 memories preserved**;
  - snapshot source `…-r6`, untouched.
- **Agent resumed**, lease of 60 min armed at 15:34:18.
- **Chat test** "fomo family, have you heard of it?" returned `received`.

## 16:08 UTC: soft background music in the live mix

- **Director change** (written by Kimi; two defects fixed, then Kimi APPROVE): when
  `<streamer-dir>/music/bgm.mp3` exists, it is the last FFmpeg input, looped. The mix is `volume=0.08`,
  `sidechaincompress` keyed by the voice, then `amix` with the unchanged voice. Without the file the argv is identical.
- **Track:** `tools/pod/onpod/make-bgm.sh` generates an original 180 s lo-fi pad at -10 LUFS. It is installed at
  `/home/unreal/.sub01-private/streamer/music/bgm.mp3`, owned by root, mode 600; **chown it to unreal** if the director
  ever runs as unreal.
- **Restart:** only the director was restarted (16:08:14); the supervisor respawned it.
- **Check:** the first live HLS segment afterwards had a mean of -33.7 dB (it was silent before).
- **To replace the music:** drop another file at that path and restart the director.
- **Still to do:** desktop (Vagon PC) audio. It needs the PulseAudio monitor of the desktop runner's Chrome as an extra
  input.

## 16:29 UTC: the desktop's (Vagon PC) audio in the live mix

**Setup**
- PulseAudio was installed on the pod with apt (pulseaudio and pulseaudio-utils).
- `scripts/streamer_audio.sh up` runs as unreal with `STREAMER_DIR` set. It provides:
  - the socket `<streamer-dir>/run/pulse/native`, with `auth-anonymous` (the 0700 directory is the access control);
  - the null sink `sub01_apps`.
- The tone test passed (-21 dB).

**Desktop runner**
- At every browser launch it probes that socket. When the socket answers, Chrome runs without `--mute-audio`, with
  autoplay allowed, and with `PULSE_SERVER` and `PULSE_SINK` set. Otherwise nothing changes.
- Restarted with `streamer_up.py restart desktop`: Vagon reconnected in 19 s on its own, and Chrome shows up as a sink
  input.

**Director**
- When the socket answers, the director adds `-f pulse -server unix:<socket> -i sub01_apps.monitor` as the last input.
- Mix chain:
  1. `volume@apps` at 0.6;
  2. summed with the music;
  3. ducked under the voice;
  4. `alimiter`.
- On the privacy layout (`webcam_only`) the desktop audio is muted before the picture switches, and unmuted after every
  successful live switch to another layout.
- If the mute gets no reply, the director relaunches ffmpeg, which starts at `volume@apps=0`.
- Restarted with `restart director` at 16:28. The ffmpeg argv has both the apps input and the music. The HLS audio was
  -32.7 dB mean.

**Review and tests**
- Code written by Kimi; I spliced it in (one probe per launch, plus an idempotent unmute). Kimi APPROVEd the final diff.
- Tests: 399 pass. The one failure is `test_logged_in_feeds.py::test_api_browsing_lists_accounts`, which already failed
  before this change: the `chess` module is missing locally.

**After a pod restart:** run `streamer_audio.sh up` again. Without the server, both the desktop and the director fall
back to the old behaviour (muted Chrome, no apps input).

## 17:18 UTC: livelier animation, and the 1-hour stability watch

**Why only six fields**
- The owner asked for more natural, cooler animation ("più naturali e fighe").
- The current native build reads only six fields from the motion director: `state`, the head aim (yaw and pitch),
  `nod_strength`, `intensity` and `camera`.
- Everything under `motion` (lean, tilt, gestures, fidgets, breathing rate) is ignored until a native rebuild, so all of
  the new liveliness goes through those six fields.

**Design** (Kimi, with my changes; Kimi APPROVEd the final diff)
- **Talk beats:** while he speaks, a small head-aim accent every 1.1-2.1 s, up to ±3.2° yaw and ±1.5° pitch. The accents
  are smaller (×0.55) while he looks into the lens.
- **Nods during speech:** about a third of the beats carry a nod of 0.14-0.28, only once the native envelope can re-arm.
  The first beat of an utterance never nods.
- **Reading and idle:** a wider aim filter (gain 0.18 / 0.28, at most 3°/2°) and a slower visible drift (0.9° at 0.055 Hz).
- **Viewer awareness:** chat glances every 35-80 s. A rare silent lens check (every 150-300 s, lasting 0.6-1.1 s) uses
  the same gates as a chat glance.
- **Intensity raised:** idle 0.18, reading 0.4, talking 0.68.

**Tests:** the quiet-version tests were updated to the new rules. All 37 motion tests pass. The 6 failures in
`test_streamer_agent.py` predate this change: they fail the same way with it stashed, because this container has no
provider keys.

**Deploy**
- Patched in runtime-source.
- `streamer_up.py restart agent` at 17:18, then the lease was re-armed for 60 min (until 18:18).
- STOP stayed absent throughout.

**Stability watch**
- `tools/pod/onpod/stability_watch.py` is passive: it samples every 30 s for 3600 s and never acts. It started at
  17:19 on the pod.
- Output: `/home/sub01-review-20261027/stability-20261027T1730.jsonl`; the last line is the summary.
- First sample: all services up, game RSS 8044 MB, receipt 51.8 fps (under load right after the agent restart), HLS age
  4.4 s, relay 200.

**RunPod:** one balance read at 17:14:34 UTC: $48.94. It was $51.36 at 15:18, so the spend is about $1.24/h.

## 17:27 UTC: game fps back to about 59 (CPU partition)

**Problem**
- After the restarts of the day, the game ran at 48-57 fps, below the owner's 55.
- It was render-thread bound: `perf_render_ms` 15-20 against a GPU time of 7.4 ms (34% GPU).
- On pod 505 (Ryzen 9 9950X, 32 logical CPUs, cgroup 13.6 CPUs, no throttling) nothing was pinned.

**What was tried** (Kimi's order: `cam2_lite` first, then the partition)
1. `cam2_lite=1` alone gave 49-59 fps: not enough.
2. `streamer_cpu_partition.py --once` as unreal, with game and Xvfb :99 on `0-7` (CCD0, siblings idle) and all other
   uid-1001 threads on `8-15,24-31`, gave 58-60 fps and a render time of 10-13 ms.
3. `cam2_lite` back to 0 (cam2 at full quality) with the partition alone gave 57.4-59.9 fps, `nr_throttled` flat.
   This is the setup kept.

The tuning backup is `/home/sub01-review-20261027/face-tuning.bak-20261027T1726.json`; its content is identical to the
current file except the sequence.

**The partition is one pass, not persistent.** Children inherit their parent's set, so supervisor restarts stay on
`8-15,24-31`. A NEW game process would start on the others' set, so re-run the same command after any game restart:

```
runuser -u unreal -- python3 $SRC/scripts/streamer_cpu_partition.py --game-pid-file $SD/game.pid --game-cpus 0-7 --other-cpus 8-15,24-31 --xvfb-display :99 --once
```

Undo with `--restore`.

## 18:19 UTC: 1-hour stability watch passed

**Window:** 17:19-18:19 UTC, 121 samples.

**Whole window**
- No service restarted: xvfb, desktop, voice, agent, director, monitor and hls all 0.
- The game pid did not change.
- STOP was never seen, and the relay always answered 200.
- The maximum HLS age was 4.8 s.

**After the CPU partition (17:28 onwards, 103 samples)**
- Game fps: median 59.2, minimum 56.2, p10 57.5; no sample below 55.
- Worst frame: 68 ms.
- Game RSS: 8068 to 8190 MB, about +122 MB/h, to keep watching on a long run.

**Lease:** it expired at 18:18:39 as designed. The agent announced "My time at the controls is up" and released its
inputs. Re-arming is manual and waits for the owner.

## 21:30 UTC: a more interactive SUB-01 (owner, twice: "più interattivo")

**Evidence before the change**
- With the PC working, he watched one YouTube live stream for an hour. Every decision said "Nothing new on screen; stay
  quiet". He spoke 2 lines in 3 hours.
- The persona had been written reserved: "happy to say nothing for minutes", "an empty say is often the best answer",
  "no question designed to make chat respond", "do not answer every remark".
- The code pacing matched that: a reading remark every 2.5-4.5 min, and a 20 s gap between lines.

**Change** (Kimi wrote the persona replacements and the numbers; Kimi APPROVEd the final diff)
- **Persona:** he thinks aloud and talks regularly, and answers every viewer message quickly (by nick when it is clean).
  He may ask chat what to look up next, and he moves to new content after a few minutes.
- **Unchanged:** honesty, safety, untrusted content, the chat_request rules, no assistant-speak and no engagement bait.
- **Pacing:**
  - speech gap 8 s;
  - a reading remark every 35-70 s, other remarks every 12-25 s;
  - chat batches every 8-15 s, or at once for 1 waiting message (minimum gap 4 s);
  - direct questions after 0.75 s;
  - up to 4 chat replies, say up to 30 words;
  - focus cap 4 min, stale page 3 min;
  - decisions every 8-11 s (reading) or 7-10 s, with a call cap of 450/h (about $0.005 a call, so about $2.3/h at most).
- **Layout:** a model-chosen layout stays at least 45 s. Webcam may come after 8 s for a chat answer or a reaction.
  Before, it flipped between room and desktop every ~30 s.

**Tests:** 10 tests that encoded the old cadence now use the new constants. The 6 failures that remain are the
pre-existing ones (no API keys locally).

**Live** (agent restart at 21:30, lease re-armed until 22:30)
- In the first 2.5 minutes he greeted and said he would leave the abbey stream, opened a different video, and commented
  on it twice, about one remark a minute.
- The layout stayed on desktop.

## 21:46-21:51 UTC: native v25 live (the body follows the agent)

**Build**
- Staging copy `<private>/v25-build` (Content symlinked), `install_v25.py` (9 anchors), UBT on CCD1 at nice 10.
- `BUILD EXIT 0` in about 3 min, with no warnings or errors from the v25 lines.

**Swap and restart** (21:46:52-21:49:15)
1. The v24 binaries and source were backed up to `/home/sub01-review-20261027/{binaries,source}-v24-backup-20261027T214652`.
2. The game (pid 7405) was stopped with TERM.
3. The v25 `Binaries/Linux` and `Source/Sub01HomeLab` were copied into the live project.
4. The game was relaunched with the same argv and environment as before (read from the old process as its own user; the
   token is the old process's own, equal to operator-token), with `taskset -c 0-7`.
5. New pid 18983, written to both game.pid files.

**State after the restart**
- `SUB01_STREAMER_VISUAL_V2_READY clips=3/3` and `MAIN_TAP_GONOGO verdict=GO`.
- The HLS was fresh again, and STOP stayed absent.
- The stream showed the placeholder for about 2.5 min while the game loaded.

**Live checks**
- `SUB01_STREAMER_VISUAL_V25 motion=1`.
- Lean follows the state: reading +2.3 to +3.2°, talking -1.4°.
- The breathing rate follows speech: 0.18 Hz talking, 0.20 Hz otherwise.
- Agent nods are honoured: 5 in the first minute.
- Game fps after warm-up: 57.5-59.8, render 9.5-12.8 ms.
- Head roll and gestures read 0 in that minute. They appear with think/laugh reactions and with talking gestures.

**Roll back to v24:** stop the game, copy `binaries-v24-backup-20261027T214652/Linux/.` back into
`project/Sub01HomeLab/Binaries/Linux/`, and relaunch the same way.

## 00:38-00:53 UTC (10-28): framing, and the "view from behind" back

**Hands**
- The owner reported buggy, crossed hands.
- On the fixed `webcam_only` stream the face camera (fov 95) showed them cut off and distorted at the bottom edge. The
  receipt showed fingertips 0.5-0.8 cm into the keys and the elbow guard sliding both wrists the full 15 cm.
- Kimi: reframe, do not touch the IK live.
- Face camera: `fov_deg` 95 -> 60, and `aim_drop_cm` -2 -> -16 after the owner asked three times to raise it. The hands
  are now out of the face shot.
- Tuning backup: `face-tuning.bak-20261028T0040.json`.

**Layout switching**
- The stack was launched on 10-26 with `--layout webcam_only`, a privacy stop-gap while Vagon showed its login. The
  director has ignored every layout request since.
- I added a director flag file `<streamer-dir>/layout-follow` that ignores a launch-time `--layout` (Kimi APPROVE).
  `room` then turned out to be the flat cam2 composite with a PiP, which is not what the owner meant. The flag file is
  removed again.
- During that director restart, viewers saw a few seconds of colour bars (the placeholder card).

**The view the owner wants**
- It is the native `spectator` camera: the cinematic shot from behind him at the PC, in the full main view.
- It was on air before only when the agent was paused, because the agent always asked for `face`.

**Camera directing**
- Change in `streamer_agent.py` (Kimi APPROVE): the director stays fixed on `webcam_only`, and the agent's layout choice
  picks the game camera instead of POSTing a director layout:
  - webcam -> `face`;
  - room, desktop, split -> `spectator`.
- The native camera switch blends over 1 s; the 45 s / 8 s dwell still applies.
- `STREAMER_CAMERA_DIRECTING=0` restores the old path.
- Deployed at 00:52 (agent restart, lease re-armed until 01:52).
- First result: camera `spectator`, and the frame matches the owner's reference.
- 01:05 UTC: owner "avvicinalo alla tastiera di più": `seat_back_cm` 36 -> 26 (tuning, live; backup `face-tuning.bak-20261028T0058.json`).
  The wrist slide of the elbow guard dropped from 15 to 10-11 cm; the hands sit on the keyboard in the spectator shot.
  58.9 fps.
