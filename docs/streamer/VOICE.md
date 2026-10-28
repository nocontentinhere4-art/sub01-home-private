# Voice server (`scripts/voice_server.py`, port 8835)

Text in over HTTP, speech out as PCM: no audio device. A writer thread feeds `<streamer-dir>/voice.pcm` (FIFO,
48 kHz stereo s16le, real-time pace, silence when idle; no reader attached is fine, ffmpeg can come and go).
Each utterance also lands in `speech/<id>.wav` (as played) and `speech/timeline.jsonl`
`{id, tag, text, start_utc, end_utc, cut}`; `speaking.json` `{speaking, started_utc, ends_utc, text, id}` is replaced
atomically on every change. All `*_utc` are Unix seconds (float). WAVs older than `--keep-hours` (24) are deleted.

`mouth.json` (`sub01.streamer-mouth.v1` `{schema, utc, open, energy, speaking, id}`, mode 0600) is replaced atomically at
25 Hz while speaking: `open` 0..1 is the RMS of the 20 ms block being written to the FIFO right now, normalised to the
utterance (95th percentile block RMS of each sentence pushed so far, floor 2 % full scale), closed below 8 % of that
level, smoothed with a 20 ms attack and an 80 ms release; `energy` is the same level with a 150 ms time constant. Zero
when idle and at once when speech ends or is cut (`/stop`, the STOP file, a `high` item). Computed on the clock thread
(one RMS per block), written by its own thread: playback never waits on the disk. `/state` shows `mouth: {open, energy}`.
The native home reads the file (`tools/native_streamer_visual_v2/install_mouth.py`).

## Run on the pod
Both engines live in one environment, `/home/unreal/voice-rt-venv` (CUDA torch, Kokoro, Chatterbox, aiohttp, numpy).
```
HF_HOME=/home/unreal/hf-cache /home/unreal/voice-rt-venv/bin/python scripts/voice_server.py \
  --token-file /home/unreal/.sub01-private/operator-token --streamer-dir /home/unreal/.sub01-private/streamer
```
With no voice flags this is the owner's choice (K07): Chatterbox on CUDA, reference WAV
`<streamer-dir>/voice/sub01-voice-reference-k07.wav` (else `assets/voice/` in the repo), `--exaggeration 0.45
--cfg-weight 0.5`, English only, falling back to Kokoro `am_puck` (CPU) if Chatterbox cannot import or CUDA fails.
The fallback is logged once and shown in `/state` (`engine`, `fallback`). Kokoro needs `espeak-ng` for rare words.
- `--voice-config <voice.json>`: `sub01.streamer-voice.v1` with `engine, voice_prompt, exaggeration, cfg_weight,
  fallback` (`"kokoro"`, `"kokoro:am_puck"`, `{"engine":"kokoro","voice":"am_puck","speed":1.0}` or `"none"`); a relative
  prompt is relative to the file. Pod file: `/home/unreal/.sub01-private/streamer/voice/voice.json`. Flags override it.
- Kokoro alone: `--engine kokoro --voice "am_michael:0.55,am_puck:0.45" --speed 1.0 [--threads 4]` (weighted blend of
  stock voices, always CPU). `--voice` also sets the Kokoro fallback voice when the engine is Chatterbox.
- ElevenLabs (optional): `ELEVENLABS_API_KEY=... --engine elevenlabs --voice <voice id>` (pcm_24000); never logged.
- Tests/dev: `--engine mock` (sine tone, 0.07 s per character). `--offline` stops any HuggingFace access.

## API (loopback, `X-Admin-Token`; `/healthz` is open)
- `POST /speak {"text", "priority": "low|normal|high", "max_seconds", "tag"}` -> `{id, queued, estimated_seconds,
  speech_seconds, starts_in_seconds, position, queue, truncated}`. `estimated_seconds` runs until the speech ends and
  includes the rendering lead-in of a slow engine; `speech_seconds` is the speech alone. 429 `{queued:false}` when
  the queue is full, 503 while `<streamer-dir>/STOP` exists, 400 for bad input (text <= 2000 characters).
- `POST /stop` -> `{ok, stopped, dropped}`. `GET /state` -> `{speaking, current: {id, tag, started, text} | null,
  queue, engine, voice, ready, waiting, fallback, killed, fifo, last_error, stats}`. `GET /healthz`.

## Interruption policy
- Sentences are split before synthesis and rendered one ahead of playback. Chatterbox renders about as slowly as
  it speaks, so a long first sentence is broken at a comma (about 90 characters) to start sooner.
- At most 3 items wait, ordered high > normal > low, then by arrival. A full queue rejects the newcomer unless it
  outranks a waiting item, which is then evicted (oldest of the lowest rank).
- `high` cuts the current utterance at the next 20 ms block (10 ms fade, `cut: true` in the timeline) and drops
  every waiting `low` item; an older `high` is cut too. `/stop` cuts and empties the queue.
- An item waiting more than 20 s is dropped and logged (`voice: dropped ...`).
- `max_seconds` keeps whole sentences whose estimated length fits, then re-checks real durations; the first sentence is
  always spoken. The STOP kill file cuts speech within about 0.2 s and refuses new items until it is removed.
- A synthesis error drops the utterance (or its remaining sentences), is logged and counted; the server keeps running.

## Limits
One utterance at a time; no mixing with other audio; English only. No lip sync: the body mesh has no jaw bone or morph
targets, so `mouth.json` only drives a head emphasis in the native home (a jaw rotation once a face rig exists). The Kokoro
fallback sounds different from Chatterbox. `/state.current.started` is null while the first sentence still renders.
`estimated_seconds` uses 0.07 s per character (Chatterbox about 0.9 s rendering per second of speech, Kokoro 0.3:
assumptions). If the FIFO reader stalls for more than 1 s, audio is dropped (the WAV still has it).
