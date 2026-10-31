#!/usr/bin/env python3
"""The voices pod (owner 10-31: "per me va bene gpu per le voci"): k2-fsa OmniVoice, the engine of the owner's Voice
Studio, on a small GPU, cloning SUB-01's and Kimchi's voices from the reference WAVs the owner made there. The live
server's voice_server.py (`--engine remote`) calls it through the RunPod HTTPS proxy.

  POST /tts {"text", "voice"}   X-Admin-Token required -> audio/L16 bytes (PCM16 mono 24 kHz), header X-Sample-Rate
  GET  /healthz                 {"ok", "ready", "voices", "device"}

Voices: <voices-dir>/<name>-ref.wav (3-10 s, from the owner's samples) and, optional, <name>-ref.txt (its transcript;
without it the transcript is made once at start with Whisper and saved next to the WAV). One synthesis at a time.
The token is read from --token-file and compared in constant time; texts are logged by length only."""
import argparse
import asyncio
import hmac
import sys
import threading
import time
from pathlib import Path

import numpy as np
from aiohttp import web

RATE = 24000
MAX_CHARS = 400


def log(message):
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tts gpu:", message, file=sys.stderr, flush=True)


class Voices:
    def __init__(self, voices_dir, device="cuda", steps=None):
        self.dir, self.device, self.steps = Path(voices_dir), device, steps
        self.refs = {}
        self.model = None
        self.lock = threading.Lock()

    def load(self):
        import torch
        from omnivoice import OmniVoice
        started = time.monotonic()
        dtype = torch.float16 if self.device.startswith("cuda") else torch.float32
        self.model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map=self.device, dtype=dtype)
        for wav in sorted(self.dir.glob("*-ref.wav")):
            name = wav.name[: -len("-ref.wav")]
            txt = wav.with_suffix(".txt")
            if not txt.exists():
                txt.write_text(self.transcribe(wav))
            self.refs[name] = (str(wav), txt.read_text().strip())
            log(f"voice {name}: {len(self.refs[name][1])} chars of reference transcript")
        log(f"loaded in {time.monotonic() - started:.1f}s on {self.device}: {', '.join(self.refs) or 'no voices'}")
        for name in self.refs:                      # the first call of each voice is the slow one
            self.synth("Ready.", name)

    @staticmethod
    def transcribe(wav):
        from transformers import pipeline
        asr = pipeline("automatic-speech-recognition", model="openai/whisper-small", device=0)
        return asr(str(wav))["text"].strip()

    def synth(self, text, voice):
        ref, ref_text = self.refs[voice]
        kwargs = {"text": text, "ref_audio": ref, "ref_text": ref_text}
        if self.steps:
            kwargs["num_step"] = self.steps
        with self.lock:
            out = self.model.generate(**kwargs)
        audio = out[0] if isinstance(out, (list, tuple)) else out
        audio = np.asarray(audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio, dtype=np.float32)
        return (np.clip(audio.reshape(-1), -1, 1) * 32767).astype("<i2").tobytes()


def create_app(voices, token):
    state = {"ready": False}

    async def tts(request):
        if not hmac.compare_digest(request.headers.get("X-Admin-Token", ""), token):
            raise web.HTTPForbidden()
        if not state["ready"]:
            return web.json_response({"why": "loading"}, status=503)
        try:
            d = await request.json()
        except ValueError:
            raise web.HTTPBadRequest()
        text, voice = " ".join(str(d.get("text") or "").split())[:MAX_CHARS], str(d.get("voice") or "")
        if not text or voice not in voices.refs:
            return web.json_response({"why": "text and a known voice", "voices": list(voices.refs)}, status=400)
        t0 = time.monotonic()
        pcm = await asyncio.get_running_loop().run_in_executor(None, voices.synth, text, voice)
        dt = time.monotonic() - t0
        log(f"{voice}: {len(text)} chars -> {len(pcm) / 2 / RATE:.2f}s audio in {dt:.2f}s")
        return web.Response(body=pcm, content_type="audio/L16", headers={"X-Sample-Rate": str(RATE)})

    async def healthz(request):
        return web.json_response({"ok": True, "ready": state["ready"], "voices": list(voices.refs), "device": voices.device})

    async def on_start(app):
        def load():
            voices.load()
            state["ready"] = True
        threading.Thread(target=load, daemon=True).start()

    app = web.Application()
    app.router.add_post("/tts", tts)
    app.router.add_get("/healthz", healthz)
    app.on_startup.append(on_start)
    return app


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--host", default="0.0.0.0", help="the RunPod proxy reaches the pod's port from outside")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--voices-dir", required=True)
    p.add_argument("--token-file", required=True)
    p.add_argument("--device", default="cuda")
    p.add_argument("--steps", type=int, help="diffusion steps (fewer is faster)")
    a = p.parse_args()
    token = Path(a.token_file).read_text().strip()
    if len(token) < 24:
        raise SystemExit("token too short")
    web.run_app(create_app(Voices(a.voices_dir, a.device, a.steps), token), host=a.host, port=a.port, print=None)


if __name__ == "__main__":
    main()
