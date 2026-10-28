# 2026-10-28 live fixes (Claude, with Kimi reviews)

**01:44 UTC: camera rule and slower movement** (agent + motion; Kimi APPROVE)
- **Camera:** the model kept choosing the webcam layout, so the face shot stayed for minutes. The game camera is now
  chosen per tick:
  - `face` while a chat answer is on (`chat_until`) or during a reaction;
  - the `spectator` shot from behind otherwise;
  - each shot is held for at least 4 s.
- **Slower movement** (owner: "si muove troppo velocemente"):
  - gaze τ 0.45 s;
  - talk beats every 2.4-4.2 s, ±2.2° yaw / ±1.0° pitch, nod p 0.2;
  - reading smoothing 1.1 s, wander 0.035 Hz;
  - lean rise/fall 0.9/1.6 s;
  - wrist glide `hand_move_s` 0.9 s (tuning).
- **Chair:** `chair_back_extra_cm` 14, so the backrest stands clear of his back. Face camera `fov_deg` 72 after the seat
  moved 17 cm closer.

**01:49 UTC: "stuck on the search" fixed** (runner; Kimi APPROVE)
- **Symptom:** every search or navigation URL broke. The remote address bar showed `html.duckduckgo.com/html//q=...`:
  the `?` arrived as `/`.
- **Cause:** the Vagon client forwards keys by physical code plus modifier state, and Playwright's `keyboard.type('?')`
  sends Slash without Shift. So searches landed on an empty search page, three "unchanged" outcomes held the agent, and
  he told chat he was stuck.
- **Fix:** `_vagon_type` sends shifted US-layout characters and capitals as explicit `Shift+<Code>` chords.
- **Deploy:** runner restart; Vagon reconnected in about 20 s; `POST /resume` cleared `held`.
- **Live result:** the type outcome was "changed" (8.0) and the next click was "changed" (192).

**01:52 UTC: faster replies on air** (director + agent; Kimi APPROVE)
- **Owner:** "deve essere più reattivo alla chat, è stra lento".
- **Measured delays:**
  - viewer message -> the speech queued: 1-10 s;
  - -> TTS start: about 2 s;
  - -> what viewers see: plus the HLS delay (4 s segments, hls.js keeps about 3 of them) of about 12-16 s.
- **Change:**
  - HLS segments 4 -> 2 s (the GOP is already 2 s), playlist 6 -> 8 entries;
  - chat batch every 4-8 s (was 8-15), minimum gap 2 s.
- **Deploy:**
  - Director restart: back on the FIFO in about 10 s.
  - Agent restart; lease re-armed until 02:53.
  - The live playlist shows 2.0 s segments.
