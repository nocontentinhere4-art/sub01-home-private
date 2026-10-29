#!/usr/bin/env python3
"""The Simli avatars' voices (owner 10-29, avatars phase 1): Chatterbox on the GPU with synthetic reference voices
(stock voices rendered once with Higgsfield TTS, never a real person's), returned as the raw PCM the Simli SDK takes:
16-bit little-endian, 16 kHz, mono. Loopback only, run in the voice venv (it has chatterbox):

  POST /tts {"text", "voice"}  -> audio/L16 bytes at 16 kHz (one synthesis at a time; 400 on a bad text or voice)
  GET  /healthz                -> {"ok", "voices"}

One model is loaded; each voice's conditionals are prepared once at start and swapped in per request. SUB-01's own
voice server is untouched; this only shares the GPU."""
import argparse
import asyncio
from pathlib import Path

import numpy as np
from aiohttp import web

MAX_CHARS = 320
OUT_RATE = 16000


def to_pcm16k(samples, rate):
    """mono samples at `rate` (float in [-1, 1], or int16) -> PCM16 bytes at 16 kHz (polyphase resampling)."""
    raw = np.asarray(samples)
    x = raw.astype(np.float32).reshape(-1)
    if np.issubdtype(raw.dtype, np.integer):               # int16 scale only for integer input; floats are clipped
        x = x / 32768.0
    if rate != OUT_RATE:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(OUT_RATE, int(rate))
        x = resample_poly(x, OUT_RATE // g, int(rate) // g)
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


class Voices:
    """One Chatterbox model, a prepared conditioning per voice name."""

    def __init__(self, prompts, exaggeration=0.5, cfg_weight=0.5, device="cuda"):
        for name, path in prompts.items():
            if not Path(path).is_file():
                raise ValueError(f"voice {name}: {path} is not a file")
        self.prompts, self.exaggeration, self.cfg_weight, self.device = dict(prompts), exaggeration, cfg_weight, device
        self.model, self.conds = None, {}

    def load(self):
        from chatterbox.tts import ChatterboxTTS
        self.model = ChatterboxTTS.from_pretrained(device=self.device)
        for name, path in self.prompts.items():
            self.model.prepare_conditionals(str(path), exaggeration=self.exaggeration)
            self.conds[name] = self.model.conds
        self.synthesize("Ready.", next(iter(self.prompts)))

    def synthesize(self, text, voice):
        self.model.conds = self.conds[voice]
        wav = self.model.generate(text, exaggeration=self.exaggeration, cfg_weight=self.cfg_weight)
        array = wav.detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav)
        return np.asarray(array, dtype=np.float32).reshape(-1), int(getattr(self.model, "sr", 24000))


def create_app(voices):
    lock = asyncio.Lock()
    names = lambda: sorted(voices.prompts)

    async def healthz(request):
        return web.json_response({"ok": True, "voices": names()})

    async def tts(request):
        try:
            body = await request.json()
        except ValueError:
            body = None
        body = body if isinstance(body, dict) else {}
        text = " ".join(str(body.get("text") or "").split())
        voice = str(body.get("voice") or "")
        if not text or len(text) > MAX_CHARS or voice not in voices.prompts:
            return web.json_response({"ok": False, "error": f"text 1..{MAX_CHARS} characters, voice one of {names()}"},
                                     status=400)
        async with lock:                                   # one synthesis at a time on the shared GPU
            samples, rate = await asyncio.to_thread(voices.synthesize, text, voice)
        if samples.size == 0:
            return web.json_response({"ok": False, "error": "no audio"}, status=502)
        return web.Response(body=to_pcm16k(samples, rate), content_type="audio/L16",
                            headers={"X-Sample-Rate": str(OUT_RATE)})

    app = web.Application(client_max_size=64 * 1024)
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/tts", tts)
    return app


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--voice", action="append", required=True, metavar="NAME=WAV", help="a synthetic reference voice")
    p.add_argument("--port", type=int, default=8844)
    a = p.parse_args()
    voices = Voices(dict(v.split("=", 1) for v in a.voice))
    voices.load()
    web.run_app(create_app(voices), host="127.0.0.1", port=a.port, access_log=None)


if __name__ == "__main__":
    main()
