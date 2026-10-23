# SUB-01 voice options

Status: comparison, 2026-10-23; no decision made. USD; prices change. (S) = seen only in a search summary.

**Assumptions.** English adult male voice, original identity (not cloned from a real person), monetised public stream, 5-25 word sentences, cancellable speech. Cost load: 15 min of speech per hour, 6 h a day (about 900 characters per minute), roughly 2.43M characters a month (my assumption). API cost at that load: ElevenLabs Flash $97, Azure Neural HD $53, Google Chirp 3 HD $43, OpenAI tts-1 $36; local engines have no API fee but need compute.

## ElevenLabs [E1-E7]

- **Quality:** top expressiveness; v4/v3 accept audio tags.
- **Latency:** Flash v2.5 about 75 ms, excluding network.
- **Cost:** API $40/1M characters (Flash/Turbo), $80 (v3, Multilingual v2). Plans: Free 10k credits, Starter $6/month, Creator $22, Pro $99; the two pricing pages disagree on included volumes.
- **Rights:** paid plans include a commercial licence. Free: no commercial use; "elevenlabs.io" or "11.ai" required in the title. Policy bans cloning a living person without consent and removing watermarks, and restricts training other models on output.
- **Design:** Voice Design: 20-1000 character prompt, 3 previews, save one; charged once for the preview text.
- **Cancel:** WebSocket multi-context: `close_context` ends a turn (5 contexts per connection). Docs don't say buffered audio is dropped; stop playback locally too.

## Kokoro-82M [K1-K3]

- **Quality:** good for 82M parameters; best male voices graded C+ (am_michael, am_puck, am_fenrir); only speed is documented as a control; weak under 10-20 tokens.
- **Latency:** third-party wrapper, self-reported: about 300 ms on an RTX 4060 Ti, under 1 s on an M3 Pro CPU, about 3.5 s on an older i7.
- **Cost:** no fee.
- **Rights:** Apache-2.0 code and weights; card: permissive audio, including synthetic audio from closed commercial TTS.
- **Design:** blendable, e.g. `am_michael(2)+am_puck(1)`: a new voice, not a clone.
- **Cancel:** stop iterating chunks.

## Orpheus TTS [O1-O4]

- **Quality:** expressive; eight tags (`<laugh>`, `<sigh>`, `<gasp>`...); voices leo, dan, zac (male by name).
- **Latency:** vendor: about 200 ms streaming, about 100 ms with input streaming. Needs about 83 tokens/s for real time (S); CPU is roughly 37-41x slower than real time (S).
- **Cost:** no fee, but a GPU shared with Unreal; no official VRAM figure.
- **Rights:** Apache-2.0 on the card; built on Llama-3.2-3B, so check Llama terms. Access requires accepting a no-impersonation policy.
- **Design:** fixed voices; cloning exists (avoid); an own voice means fine-tuning on licensed recordings (about 300 examples per speaker advised).
- **Cancel:** stop the token stream.

## Chatterbox (Resemble AI) [C1-C2]

- **Quality:** controls `exaggeration`, `cfg_weight`; Turbo and Nano accept `[laugh]`, `[cough]`, `[chuckle]`.
- **Latency:** Chatterbox-Flash first packet 103-119 ms (GPU not named); Nano about 3x real time on 8 CPU cores.
- **Cost:** no fee.
- **Rights:** MIT; every output is watermarked (PerTh).
- **Design:** Turbo needs a reference clip, so identity is whatever you supply: use a licensed or consenting speaker; check terms before using another TTS's output as reference.
- **Cancel:** Flash streams natively; others per chunk.

## Piper [P1-P3]

- **Quality:** fast VITS voices, flatter, no tags.
- **Latency:** chunked output on CPU; no benchmark read.
- **Cost:** no fee.
- **Rights:** engine GPL-3.0; docs: personal use and research only; per-voice licences; en_US-ryan-high's dataset is CC BY-NC-SA 4.0, unusable here. Read each MODEL_CARD.
- **Design:** none.
- **Cancel:** stop iterating chunks.

## OpenAI [A1-A4]

- **Warning:** tts-1, tts-1-hd and gpt-4o-mini-tts shut down on 2027-01-06; the Realtime API is the stated replacement.
- **Quality:** natural; `instructions` steer tone; 13 voices (marin, cedar recommended).
- **Latency:** unpublished; pcm or wav streams fastest.
- **Cost:** gpt-4o-mini-tts $0.60/1M text tokens plus $12/1M audio tokens; tts-1 $15/1M characters; gpt-realtime-2.1-mini $20/1M audio-out tokens; GPT-Live $0.05/min.
- **Rights:** disclose the AI voice; keep provenance markers; no impersonation.
- **Design:** prompt-to-voice: free, adults only, GPT-Live only. Recording-based voices need consent and sales approval.
- **Cancel:** Realtime `response.cancel`, `conversation.item.truncate`.

## Azure Speech [Z1-Z4]

- **Quality:** HD (DragonHD, Omni) is natural, with style tags like `[excited]`; male en-US: Andrew, Andrew2, Brian, Davis.
- **Latency:** docs: under 300 ms (HD and standard).
- **Cost:** Neural $15/1M characters, Neural HD $22, custom $24 plus $52/h training and about $4/h hosting; free tier 0.5M characters a month.
- **Rights:** commercial terms not checked. Custom and personal voice: limited access, disclosure rules.
- **Design:** prebuilt personas; custom needs consenting voice talent.
- **Cancel:** WebSocket v2 text streaming; cancel semantics undocumented on pages read.

## Google Cloud TTS [G1-G3]

- **Quality:** Chirp 3 HD, 16 male voices (Charon, Puck, Fenrir...); no SSML when streaming.
- **Latency:** unpublished.
- **Cost:** Chirp 3 HD $30/1M characters (1M free monthly), Neural2 $16, Instant custom $60.
- **Rights:** terms not checked.
- **Design:** prebuilt; Instant custom is allow-listed cloning of a consenting speaker.
- **Cancel:** streaming synthesis; close the stream (untested).

## Sources

- E1 https://elevenlabs.io/pricing
- E2 https://elevenlabs.io/pricing/api
- E3 https://elevenlabs.io/docs/overview/models
- E4 https://elevenlabs.io/docs/eleven-creative/voices/voice-design
- E5 https://elevenlabs.io/docs/cookbooks/multi-context-web-socket
- E6 https://elevenlabs.io/docs/help-center/legal/can-i-publish-the-content-i-generate-on-the-platform
- E7 https://elevenlabs.io/use-policy
- K1 https://huggingface.co/hexgrad/Kokoro-82M
- K2 https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
- K3 https://github.com/remsky/Kokoro-FastAPI
- O1 https://github.com/canopyai/Orpheus-TTS
- O2 https://huggingface.co/canopylabs/orpheus-tts-0.1-finetune-prod
- O3 (S) https://www.baseten.co/library/orpheus-tts/
- O4 (S) https://huggingface.co/OpenVoiceOS/phoonnx-orpheus
- C1 https://github.com/resemble-ai/chatterbox
- C2 https://huggingface.co/ResembleAI/chatterbox-flash
- P1 https://github.com/OHF-Voice/piper1-gpl
- P2 https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ryan/high/MODEL_CARD
- P3 https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md
- A1 https://developers.openai.com/api/docs/guides/text-to-speech
- A2 https://developers.openai.com/api/docs/pricing
- A3 https://developers.openai.com/api/docs/guides/custom-voices
- A4 https://developers.openai.com/api/docs/guides/realtime-conversations
- Z1 https://learn.microsoft.com/en-us/azure/ai-services/speech-service/high-definition-voices
- Z2 https://prices.azure.com/api/retail/prices (East US)
- Z3 https://azure.microsoft.com/en-us/pricing/details/speech/
- Z4 https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-lower-speech-synthesis-latency
- G1 https://cloud.google.com/text-to-speech/pricing
- G2 https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
- G3 https://docs.cloud.google.com/text-to-speech/docs/chirp3-instant-custom-voice

## Recommendation matrix (no choice made)

| Goal | Candidates | Caveat |
|---|---|---|
| Best quality | ElevenLabs; then Azure HD, Google Chirp 3 HD, Orpheus | cost; vendor terms |
| Best free/local | Kokoro; Chatterbox (licensed reference); Orpheus (GPU) | Kokoro male voices C+; Piper needs licence check |
| Best latency | ElevenLabs Flash; Chatterbox-Flash (vendor figures); Azure | measure on the real pod |
| Original identity, no cloning | ElevenLabs Voice Design; Kokoro blending | OpenAI: GPT-Live only |
| Cleanest cancel | ElevenLabs multi-context; OpenAI Realtime | test that buffered audio stops |
