# SUB-01 voice: the owner's choice (2026-10-23)

Chosen: **K07**. Engine Chatterbox (Resemble AI, MIT), English, GPU on the pod.

| Field | Value |
|---|---|
| Reference prompt | `assets/voice/sub01-voice-reference-k07.wav` (pod copy: `/home/unreal/.sub01-private/streamer/voice/sub01-voice-reference-k07.wav`) |
| Origin of the reference | Kokoro-82M stock voice `am_puck`, synthetic, rendered 2026-10-23. No real person's voice is involved. |
| Parameters | `exaggeration 0.45`, `cfg_weight 0.5` |
| Fallback | Kokoro `am_puck` (CPU) when Chatterbox or CUDA is unavailable |
| Pod config | `/home/unreal/.sub01-private/streamer/voice/voice.json` (`sub01.streamer-voice.v1`) |

Measured on the pod (RTX PRO 4000): 2.8–5.1 s synthesis for lines of 3–6 s; identity stable across four different
lines (`voice-samples/k07/`). Chatterbox output carries Resemble's inaudible Perth watermark.

Alternatives kept on file: 15 Kokoro voices and blends, 15 other Chatterbox candidates (G–J, K01–K10, L01–L02), and
ElevenLabs Voice Design if the owner ever provides an account (commercial use needs a paid tier).
