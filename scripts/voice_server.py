#!/usr/bin/env python3
"""SUB-01 voice server: queued text-to-speech delivered as raw PCM, no audio device needed.

Text arrives over HTTP, is split into sentences, synthesized one sentence ahead of
playback by a TTS engine (default: Chatterbox on the GPU with the owner's reference voice and a
Kokoro am_puck fallback; also Kokoro on CPU, optional ElevenLabs, a sine-tone mock for tests)
and played into:

  <streamer-dir>/voice.pcm          FIFO, continuous 48 kHz stereo s16le at real-time pace,
                                    silence when idle (ffmpeg reads it; no reader is fine)
  <streamer-dir>/speech/<id>.wav    every utterance as it was played (48 kHz stereo s16le)
  <streamer-dir>/speech/timeline.jsonl
                                    {id, tag, text, start_utc, end_utc, cut} per utterance
  <streamer-dir>/speaking.json      {speaking, started_utc, ends_utc, text, id}, replaced
                                    atomically on every change (the native talking animation)

All *_utc values are Unix seconds (float, UTC), like the other native files.

HTTP on loopback only; every route except /healthz needs the operator credential in
`X-Admin-Token` (from --token-file or SUB01_ADMIN_TOKEN; never logged):

  POST /speak {"text", "priority": "low|normal|high", "max_seconds", "tag"}
        -> {id, queued, estimated_seconds, speech_seconds, starts_in_seconds, position, queue, truncated}
        estimated_seconds = until the speech ends (slow engines: rendering lead-in included);
        speech_seconds = the speech alone. 429 when the queue is full, 503 while STOP exists.
  POST /stop  -> {ok, stopped, dropped}      cut the current utterance, drop the queue
  GET  /state -> {speaking, current: {id, tag, started, text} | null, queue, engine, voice, ...}
  GET  /healthz -> {ok, engine, ready}

Voice settings come from flags or --voice-config (a sub01.streamer-voice.v1 JSON); flags win.

Policy: at most 3 items wait; `high` cuts the current utterance at the next sample block
(20 ms, with a 10 ms fade) and drops queued `low` items; an item older than 20 s is dropped
and logged; `max_seconds` keeps whole sentences only (at least the first one).
"""

import argparse
import asyncio
import collections
import concurrent.futures
import errno
import fcntl
import hmac
import json
import math
import os
import re
import signal
import stat
import sys
import threading
import time
import types
import wave
from pathlib import Path

import numpy as np
from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
MIN_TOKEN = 12
DEFAULT_PORT = 8835
DEFAULT_STREAMER_DIR = "/home/unreal/.sub01-private/streamer"
DEFAULT_VOICE = "am_puck"                # Kokoro voice: the standalone voice and the fallback
DEFAULT_ENGINE = "chatterbox"
DEFAULT_PROMPT = "sub01-voice-reference-k07.wav"  # synthetic reference rendered from Kokoro am_puck
DEFAULT_EXAGGERATION = 0.45
DEFAULT_CFG_WEIGHT = 0.5
VOICE_CONFIG_SCHEMA = "sub01.streamer-voice.v1"
ENGINES = ("chatterbox", "kokoro", "elevenlabs", "mock")

OUT_RATE = 48000
OUT_CHANNELS = 2
FRAME_BYTES = 2 * OUT_CHANNELS            # s16le stereo
BLOCK_FRAMES = 960                        # 20 ms: the granularity of pacing and of cuts
BLOCK_SECONDS = BLOCK_FRAMES / OUT_RATE
FADE_FRAMES = 480                         # 10 ms ramp when an utterance is cut
LOOKAHEAD = 0.25                          # next sentence is pushed when this much audio is left
FIFO_RETRY = 0.1                          # seconds between attempts to open the FIFO
FIFO_PENDING_MAX = OUT_RATE * FRAME_BYTES  # a reader that stalls for 1 s loses audio

QUEUE_BOUND = 3
MAX_AGE = 20.0
MAX_TEXT = 2000
MAX_TAG = 64
SECONDS_PER_CHAR = 0.07
SYNTH_TIMEOUT = 60.0
PRIORITIES = {"low": 0, "normal": 1, "high": 2}


def log(message):
    print("voice: " + message, flush=True)


def short(text, limit=70):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------- text

_ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "mt", "e.g", "i.e", "approx", "fig"}
_INITIALISM = re.compile(r"^(?:[A-Za-z]\.)*[A-Za-z]$")
_CLOSERS = "\"')]}”’»"
_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


def clean_text(text):
    """Control characters out, runs of blanks collapsed, newlines kept as line breaks."""
    text = _CONTROL.sub(" ", str(text).replace("\r\n", "\n").replace("\r", "\n"))
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _ends_sentence(word, following):
    core = word.rstrip(_CLOSERS)
    if not core or core[-1] not in ".!?…":
        return False
    if core[-1] in "!?…":
        return True
    if core.endswith(".."):  # ellipsis: a sentence end only when a new sentence follows
        return following is None or not following[0].islower()
    stem = core[:-1]
    if stem.lower() in _ABBREVIATIONS:
        return False
    if _INITIALISM.match(stem) and (len(stem) == 1 and stem.isupper() or "." in stem):
        return False  # "J." in "J. Smith", "U.S."
    return following is None or not following[0].islower()


def _wrap_long(sentence, max_chars):
    """Break an over-long sentence at clause punctuation, then at spaces."""
    if len(sentence) <= max_chars:
        return [sentence]
    chunks, current = [], ""
    for clause in re.split(r"(?<=[,;:])\s+", sentence):
        while len(clause) > max_chars:
            cut = clause.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(clause[:cut].strip())
            clause = clause[cut:].strip()
        if not clause:
            continue
        if current and len(current) + 1 + len(clause) > max_chars:
            chunks.append(current)
            current = clause
        else:
            current = (current + " " + clause).strip()
    if current:
        chunks.append(current)
    return chunks


def split_sentences(text, max_chars=240, min_chars=12):
    """Sentences for one-at-a-time synthesis.

    Newlines always end a sentence; abbreviations ("Dr.", "e.g."), initials and decimals do not.
    Fragments shorter than min_chars join the next sentence (Kokoro is weak on tiny inputs);
    sentences longer than max_chars are broken at clauses.
    """
    sentences = []
    for line in clean_text(text).split("\n"):
        words = line.split()
        current = []
        for index, word in enumerate(words):
            current.append(word)
            following = words[index + 1] if index + 1 < len(words) else None
            if _ends_sentence(word, following):
                sentences.append(" ".join(current))
                current = []
        if current:
            sentences.append(" ".join(current))
    merged, carry = [], ""
    for sentence in sentences:
        if carry:
            sentence = carry + " " + sentence
            carry = ""
        if len(sentence) < min_chars:
            carry = sentence
        else:
            merged.append(sentence)
    if carry:
        if merged:
            merged[-1] += " " + carry
        else:
            merged.append(carry)
    return [piece for sentence in merged for piece in _wrap_long(sentence, max_chars)]


def truncate_sentences(sentences, max_seconds, seconds_per_char=SECONDS_PER_CHAR):
    """Keep whole sentences while their estimated duration fits max_seconds.

    Returns (kept, truncated). The first sentence is always kept: a cap never produces silence.
    """
    if not max_seconds or not sentences:
        return list(sentences), False
    kept, total = [], 0.0
    for sentence in sentences:
        seconds = len(sentence) * seconds_per_char
        if kept and total + seconds > max_seconds + 1e-9:
            return kept, True
        kept.append(sentence)
        total += seconds
    return kept, False


def shorten_first(sentences, max_chars):
    """Break the first sentence at a clause so a slow engine renders a short chunk first.

    Returns (chunks, head): head is how many chunks came from the first sentence (they are
    never separated by max_seconds, which only cuts between sentences).
    """
    if not sentences or not max_chars or len(sentences[0]) <= max_chars:
        return list(sentences), 1
    first = sentences[0]
    cut = max((m.end() for m in re.finditer(r"[,;:]\s+", first[: max_chars + 1])), default=0)
    if cut < 20 or cut >= len(first) - 8:  # no usable clause break: keep the sentence whole
        return list(sentences), 1
    return [first[:cut].strip(), first[cut:].strip()] + list(sentences[1:]), 2


def estimate_seconds(sentences, seconds_per_char=SECONDS_PER_CHAR, synth_rtf=0.0):
    """Seconds from the start of processing to the end of speech.

    Mirrors the playback pipeline: the first chunk must render before anything plays, and a
    chunk starts rendering when the previous one has been pushed, so a slow engine (synth_rtf
    near 1) shows up as a lead-in plus a stall whenever rendering outruns playback.
    """
    if not sentences:
        return 0.0
    speech = [len(s) * seconds_per_char for s in sentences]
    push = speech[0] * synth_rtf
    end = push + speech[0]
    for index in range(1, len(speech)):
        push = max(push + speech[index] * synth_rtf, end - LOOKAHEAD)
        end = max(end, push) + speech[index]
    return end


# ---------------------------------------------------------------- audio helpers

def to_int16(samples):
    array = np.asarray(samples)
    if array.ndim > 1:
        array = array.mean(axis=1)
    array = array.reshape(-1)
    if array.dtype.kind == "f":
        return np.rint(np.clip(array, -1.0, 1.0) * 32767.0).astype(np.int16)
    if array.dtype != np.int16:
        return np.clip(array, -32768, 32767).astype(np.int16)
    return array


def to_stereo_48k(samples, rate):
    """Mono samples at `rate` -> 48 kHz stereo s16le bytes (numpy linear interpolation)."""
    mono = to_int16(samples)
    if mono.size == 0:
        return b""
    if rate != OUT_RATE:
        count = max(1, int(round(mono.size * OUT_RATE / rate)))
        positions = np.arange(count, dtype=np.float64) * (rate / OUT_RATE)
        resampled = np.interp(positions, np.arange(mono.size, dtype=np.float64), mono.astype(np.float64))
        mono = np.clip(np.rint(resampled), -32768, 32767).astype(np.int16)
    return np.repeat(mono, OUT_CHANNELS).tobytes()


def fade_out(pcm):
    """Ramp a short stereo s16le buffer linearly down to silence."""
    frames = len(pcm) // FRAME_BYTES
    if frames == 0:
        return bytes(pcm)
    data = np.frombuffer(bytes(pcm[: frames * FRAME_BYTES]), dtype=np.int16).reshape(-1, OUT_CHANNELS)
    ramp = np.linspace(1.0, 0.0, frames, endpoint=False)[:, None]
    return np.rint(data * ramp).astype(np.int16).tobytes()


def silence(seconds):
    return bytes(max(0, int(round(seconds * OUT_RATE))) * FRAME_BYTES)


# ---------------------------------------------------------------- engines

class EngineError(Exception):
    pass


class Engine:
    """synthesize(text) -> (int16 mono samples, sample_rate). Called from one worker thread."""

    name = "engine"
    voice = ""
    # Estimates only; real durations come from the audio.
    seconds_per_char = SECONDS_PER_CHAR  # seconds of speech per character
    synth_rtf = 0.0                      # seconds of rendering per second of speech
    first_chunk_chars = None             # if set, the first sentence is broken at a clause above this length

    def synthesize(self, text):
        raise NotImplementedError

    def warmup(self):
        """Load models ahead of the first utterance."""


class MockEngine(Engine):
    """Sine tone lasting 0.07 s per character: deterministic audio for tests.

    `delay` simulates rendering time; `calls` records (text, started, finished) per call."""

    name = "mock"
    voice = "sine"

    def __init__(self, sample_rate=24000, seconds_per_char=SECONDS_PER_CHAR, frequency=220.0, delay=0.0):
        self.sample_rate = sample_rate
        self.seconds_per_char = seconds_per_char
        self.frequency = frequency
        self.delay = delay
        self.calls = []

    def synthesize(self, text):
        started = time.monotonic()
        if self.delay:
            time.sleep(self.delay)
        try:
            return self._tone(text)
        finally:
            self.calls.append((text, started, time.monotonic()))

    def _tone(self, text):
        count = int(round(len(text) * self.seconds_per_char * self.sample_rate))
        t = np.arange(count) / self.sample_rate
        tone = 0.25 * np.sin(2 * np.pi * self.frequency * t)
        edge = min(count // 2, int(0.005 * self.sample_rate))
        if edge:
            ramp = np.linspace(0.0, 1.0, edge)
            tone[:edge] *= ramp
            tone[count - edge:] *= ramp[::-1]
        return to_int16(tone), self.sample_rate


def parse_voice_spec(spec):
    """"am_michael:0.55,am_puck:0.45" -> [("am_michael", 0.55), ("am_puck", 0.45)] (weights sum to 1)."""
    parts = []
    for chunk in str(spec).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, _, weight = chunk.partition(":")
        name = name.strip()
        if not re.fullmatch(r"[a-z]{2}_[a-z0-9]+", name):
            raise ValueError(f"invalid voice name {name!r} (expected e.g. am_michael)")
        try:
            value = float(weight) if weight.strip() else 1.0
        except ValueError:
            raise ValueError(f"invalid weight {weight!r} for voice {name}")
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"weight for voice {name} must be positive")
        parts.append((name, value))
    if not parts:
        raise ValueError("empty voice")
    total = sum(weight for _, weight in parts)
    return [(name, weight / total) for name, weight in parts]


class KokoroEngine(Engine):
    """Kokoro-82M on CPU (the GPU belongs to the game). Models come from the HuggingFace
    cache (HF_HOME). The voice is a weighted blend of stock voice tensors."""

    name = "kokoro"
    RATE = 24000
    REPO = "hexgrad/Kokoro-82M"

    def __init__(self, voice=DEFAULT_VOICE, speed=1.0, threads=0, lang_code="a"):
        self.blend = parse_voice_spec(voice)
        self.voice = ",".join(f"{name}:{weight:.2f}" for name, weight in self.blend)
        self.speed = min(2.0, max(0.5, float(speed)))
        self.seconds_per_char = SECONDS_PER_CHAR / self.speed
        self.synth_rtf = 0.3  # assumption for CPU Kokoro-82M; only shapes estimated_seconds
        self.threads = int(threads)
        self.lang_code = lang_code
        self._pipeline = None
        self._pack = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._pipeline is not None:
                return
            started = time.monotonic()
            import torch  # lazy: the server and its tests do not need torch
            from kokoro import KPipeline

            if self.threads > 0:
                torch.set_num_threads(self.threads)
            pipeline = KPipeline(lang_code=self.lang_code, repo_id=self.REPO, device="cpu")
            blended = None
            for name, weight in self.blend:
                pack = pipeline.load_single_voice(name)
                blended = pack * weight if blended is None else blended + pack * weight
            self._pack = blended.to(torch.float32)
            self._pipeline = pipeline
            log(f"kokoro loaded in {time.monotonic() - started:.1f}s (voice {self.voice}, HF_HOME={os.environ.get('HF_HOME', '<default>')})")

    def warmup(self):
        self._load()
        self.synthesize("Ready.")

    def synthesize(self, text):
        self._load()
        chunks = []
        for result in self._pipeline(text, voice=self._pack, speed=self.speed):
            audio = getattr(result, "audio", None)
            if audio is None and isinstance(result, tuple) and len(result) >= 3:
                audio = result[2]
            if audio is None:
                continue
            array = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
            chunks.append(np.asarray(array, dtype=np.float32).reshape(-1))
        if not chunks:
            raise EngineError("kokoro returned no audio")
        return to_int16(np.concatenate(chunks)), self.RATE


class ChatterboxEngine(Engine):
    """Chatterbox (Resemble AI) on the GPU. The identity comes from an optional reference WAV
    (a synthetic one, never a real person's voice); without it the model's built-in voice is used.
    Rendering takes about as long as the speech itself, hence the short-first-chunk pipelining."""

    name = "chatterbox"
    synth_rtf = 0.9  # measured on the pod: 5-8 s to render a 7 s sentence
    first_chunk_chars = 90

    def __init__(self, voice_prompt=None, exaggeration=0.45, cfg_weight=0.5, device="cuda"):
        if voice_prompt and not Path(voice_prompt).is_file():
            raise ValueError(f"voice prompt {voice_prompt} is not a file")
        self.voice_prompt = str(voice_prompt) if voice_prompt else None
        self.voice = Path(voice_prompt).name if voice_prompt else "built-in"
        self.exaggeration = float(exaggeration)
        self.cfg_weight = float(cfg_weight)
        self.device = device
        self.loaded = False
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is not None:
                return
            started = time.monotonic()
            import torch  # lazy: only the pod's realtime venv has chatterbox
            if self.device.startswith("cuda") and not torch.cuda.is_available():
                raise EngineError("CUDA is not available")
            from chatterbox.tts import ChatterboxTTS

            model = ChatterboxTTS.from_pretrained(device=self.device)
            if self.voice_prompt:  # embed the reference once instead of on every sentence
                model.prepare_conditionals(self.voice_prompt, exaggeration=self.exaggeration)
            self._model, self.loaded = model, True
            log(f"chatterbox loaded in {time.monotonic() - started:.1f}s on {self.device} "
                f"(prompt {self.voice}, HF_HOME={os.environ.get('HF_HOME', '<default>')})")

    def warmup(self):
        self._load()
        self.synthesize("Ready.")

    def synthesize(self, text):
        self._load()
        wav = self._model.generate(text, exaggeration=self.exaggeration, cfg_weight=self.cfg_weight)
        array = wav.detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav)
        array = np.asarray(array, dtype=np.float32).reshape(-1)
        if array.size == 0:
            raise EngineError("chatterbox returned no audio")
        return to_int16(array), int(getattr(self._model, "sr", 24000))


class FallbackEngine(Engine):
    """Runs `primary`; if it cannot load (missing package, no CUDA) or hits a CUDA error, logs once
    and uses `fallback` from then on. name/voice/estimates always describe the active engine."""

    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback
        self.active = primary
        self.fallback_reason = None
        self._lock = threading.Lock()

    name = property(lambda self: self.active.name)
    voice = property(lambda self: self.active.voice)
    seconds_per_char = property(lambda self: self.active.seconds_per_char)
    synth_rtf = property(lambda self: self.active.synth_rtf)
    first_chunk_chars = property(lambda self: self.active.first_chunk_chars)

    def _switch(self, error):
        with self._lock:
            if self.active is self.fallback:
                return
            self.fallback_reason = short(f"{type(error).__name__}: {error}", 160)
            log(f"{self.primary.name} unavailable ({self.fallback_reason}); falling back to {self.fallback.name}")
            self.active = self.fallback

    def _should_switch(self, error):
        text = str(error).lower()
        return (isinstance(error, ImportError) or not getattr(self.primary, "loaded", True)
                or "cuda" in text or "out of memory" in text)

    def warmup(self):
        if self.active is self.primary:
            try:
                return self.primary.warmup()
            except Exception as error:
                if not self._should_switch(error):
                    raise
                self._switch(error)
        return self.active.warmup()

    def synthesize(self, text):
        if self.active is self.primary:
            try:
                return self.primary.synthesize(text)
            except Exception as error:
                if not self._should_switch(error):
                    raise
                self._switch(error)
        return self.active.synthesize(text)


class ElevenLabsEngine(Engine):
    """ElevenLabs text-to-speech, raw PCM 24 kHz. Only built when ELEVENLABS_API_KEY is set."""

    name = "elevenlabs"
    RATE = 24000

    def __init__(self, api_key, voice_id, model_id="eleven_flash_v2_5", base_url="https://api.elevenlabs.io",
                 timeout=20.0, trust_env=True):
        if not api_key:
            raise ValueError("ELEVENLABS_API_KEY is not set")
        if not voice_id:
            raise ValueError("an ElevenLabs voice id is required (--voice)")
        self._api_key = api_key
        self.voice = voice_id
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.trust_env = trust_env  # honour HTTPS_PROXY & co.

    async def _fetch(self, text):
        import aiohttp
        from urllib.parse import quote

        url = f"{self.base_url}/v1/text-to-speech/{quote(self.voice, safe='')}"
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=self.trust_env) as session:
            async with session.post(
                url,
                params={"output_format": "pcm_24000"},
                headers={"xi-api-key": self._api_key, "Accept": "audio/pcm"},
                json={"text": text, "model_id": self.model_id},
            ) as response:
                if response.status != 200:
                    detail = (await response.text())[:200]
                    raise EngineError(f"ElevenLabs HTTP {response.status}: {detail}")
                return await response.read()

    def synthesize(self, text):
        raw = asyncio.run(self._fetch(text))  # worker thread: no running loop of its own
        raw = raw[: len(raw) // 2 * 2]
        if not raw:
            raise EngineError("ElevenLabs returned no audio")
        return np.frombuffer(raw, dtype="<i2").astype(np.int16), self.RATE


# ---------------------------------------------------------------- PCM sink

def ensure_fifo(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = os.stat(path).st_mode
    except FileNotFoundError:
        os.mkfifo(path, 0o600)
        return
    if not stat.S_ISFIFO(mode):
        log(f"{path} is not a FIFO; replacing it")
        os.unlink(path)
        os.mkfifo(path, 0o600)


class PcmSink:
    """Emits one block of 48 kHz stereo s16le every 20 ms, forever: queued speech or silence.

    The FIFO is opened non-blocking and re-opened on demand, so a missing or restarted
    reader never stalls the clock; audio is simply not delivered while nobody reads.
    """

    def __init__(self, fifo_path=None, clock=time.monotonic):
        self.path = Path(fifo_path) if fifo_path else None
        self._clock = clock
        self._lock = threading.Lock()
        self._chunks = collections.deque()
        self._head = 0
        self._buffered = 0
        self._stop = threading.Event()
        self._thread = None
        self._fd = None
        self._pending = b""
        self._written = 0
        self._next_open = 0.0
        self._last_warning = 0.0
        self.blocks = 0
        self.dropped_bytes = 0
        if self.path:
            ensure_fifo(self.path)

    # -- producer side (any thread)
    def push(self, pcm):
        if pcm:
            with self._lock:
                self._chunks.append(bytes(pcm))
                self._buffered += len(pcm)

    def buffered_bytes(self):
        return self._buffered

    def buffered_seconds(self):
        return self._buffered / (FRAME_BYTES * OUT_RATE)

    def cut(self):
        """Drop what is queued, keeping a 10 ms faded tail so the stream does not click.

        Returns (dropped_bytes, kept_bytes): the kept bytes are the faded start of what was queued.
        """
        with self._lock:
            total = self._buffered
            if total == 0:
                return 0, 0
            keep = min(FADE_FRAMES * FRAME_BYTES, total)
            head = bytearray()
            for index, chunk in enumerate(self._chunks):
                begin = self._head if index == 0 else 0
                head += chunk[begin: begin + keep - len(head)]
                if len(head) >= keep:
                    break
            tail = fade_out(head)
            self._chunks.clear()
            self._head = 0
            self._chunks.append(tail)
            self._buffered = len(tail)
            return total - keep, keep

    # -- clock thread
    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="voice-sink", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(2)
        self._close_fifo(None)

    def fifo_state(self):
        if not self.path:
            return "none"
        return "connected" if self._fd is not None else "waiting"

    def _take(self, nbytes):
        out = bytearray()
        with self._lock:
            while len(out) < nbytes and self._chunks:
                first = self._chunks[0]
                available = len(first) - self._head
                need = nbytes - len(out)
                if available <= need:
                    out += first[self._head:]
                    self._chunks.popleft()
                    self._head = 0
                else:
                    out += first[self._head: self._head + need]
                    self._head += need
            self._buffered -= len(out)
        if len(out) < nbytes:
            out += bytes(nbytes - len(out))
        return bytes(out)

    def _run(self):
        interval = BLOCK_SECONDS
        next_time = self._clock()
        while not self._stop.is_set():
            wait = next_time - self._clock()
            if wait > 0:
                if self._stop.wait(wait):
                    break
            elif wait < -1.0:
                next_time = self._clock()  # stalled for over a second: resync, no burst
            self._emit(self._take(BLOCK_FRAMES * FRAME_BYTES))
            self.blocks += 1
            next_time += interval

    def _warn(self, message):
        now = self._clock()
        if now - self._last_warning > 5.0:
            self._last_warning = now
            log(message)

    def _close_fifo(self, reason):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            if reason:
                log(f"fifo reader gone ({reason})")
        self._pending = b""
        self._written = 0

    def _emit(self, block):
        if self.path is None:
            return
        if self._fd is None:
            now = self._clock()
            if now < self._next_open:
                return
            self._next_open = now + FIFO_RETRY
            try:
                self._fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
            except OSError as error:
                if error.errno not in (errno.ENXIO, errno.ENOENT):
                    self._warn(f"fifo open failed: {error}")
                elif error.errno == errno.ENOENT:
                    try:
                        ensure_fifo(self.path)
                    except OSError:
                        pass
                return
            try:
                fcntl.fcntl(self._fd, getattr(fcntl, "F_SETPIPE_SZ", 1031), 262144)
            except OSError:
                pass
            self._pending, self._written = b"", 0
            log("fifo reader attached")
        data = self._pending + block
        try:
            count = os.write(self._fd, data)
        except (BlockingIOError, InterruptedError):
            count = 0
        except OSError as error:  # EPIPE: the reader went away
            self._close_fifo(error.strerror or error.errno)
            return
        self._written += count
        self._pending = data[count:]
        if len(self._pending) > FIFO_PENDING_MAX:
            drop = len(self._pending) - FIFO_PENDING_MAX
            drop += (-(self._written + drop)) % FRAME_BYTES  # stay on a frame boundary
            self._pending = self._pending[drop:]
            self._written += drop
            self.dropped_bytes += drop
            self._warn(f"fifo reader is not keeping up: dropped {drop / (FRAME_BYTES * OUT_RATE) * 1000:.0f} ms of audio")


# ---------------------------------------------------------------- service

class Refused(Exception):
    def __init__(self, reason, status, message):
        super().__init__(message)
        self.reason, self.status, self.message = reason, status, message


def write_json_atomic(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


class Item:
    def __init__(self, ident, tag, sentences, head, priority, max_seconds, truncated, speech, estimate, enqueued):
        self.id = ident
        self.tag = tag
        self.sentences = sentences
        self.head = head  # chunks that make up the first sentence
        self.text = " ".join(sentences)
        self.priority = priority
        self.rank = PRIORITIES[priority]
        self.max_seconds = max_seconds
        self.truncated = truncated
        self.speech = speech      # estimated seconds of speech
        self.estimate = estimate  # estimated seconds until the speech ends, rendering lead-in included
        self.enqueued = enqueued
        self.cut = threading.Event()
        self.cut_reason = None
        self.started_wall = None
        self.ends_wall = None


class VoiceService:
    def __init__(self, engine, sink, streamer_dir, *, max_age=MAX_AGE, queue_bound=QUEUE_BOUND,
                 clock=time.monotonic, wall=time.time, keep_hours=24.0, synth_timeout=SYNTH_TIMEOUT):
        self.engine = engine
        self.sink = sink
        self.dir = Path(streamer_dir)
        self.speech_dir = self.dir / "speech"
        self.speech_dir.mkdir(parents=True, exist_ok=True)
        self.stop_file = self.dir / "STOP"
        self.max_age = max_age
        self.queue_bound = queue_bound
        self.keep_hours = keep_hours
        self.synth_timeout = synth_timeout
        self._clock, self._wall = clock, wall
        self._cond = threading.Condition(threading.Lock())
        self._file_lock = threading.Lock()
        self._queue = []
        self.current = None
        self._seq = 0
        self._closing = threading.Event()
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-synth")
        self._threads = []
        self._last_prune = 0.0
        self.ready = False
        self.last_error = None
        self.stats = {"spoken": 0, "dropped": 0, "cut": 0, "errors": 0, "rejected": 0}

    # -- lifecycle
    def start(self):
        self._write_speaking(None)
        self.sink.start()
        for target, name in ((self._player, "voice-player"), (self._watchdog, "voice-watchdog")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def close(self):
        if self._closing.is_set():
            return
        self._closing.set()
        with self._cond:
            if self.current is not None:
                self._cut_locked(self.current, "shutdown")
            self._queue.clear()
            self._cond.notify_all()
        for thread in self._threads:
            thread.join(2)
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.sink.stop()
        self._write_speaking(None)

    def warmup(self):
        started = time.monotonic()
        try:
            self._pool.submit(self.engine.warmup).result()
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {error}"
            log(f"engine {self.engine.name} warmup failed: {self.last_error}")
            return False
        self.ready = True
        log(f"engine {self.engine.name} ready in {time.monotonic() - started:.1f}s")
        return True

    # -- public API (thread-safe)
    def kill_active(self):
        return self.stop_file.exists()

    def submit(self, text, priority="normal", max_seconds=None, tag=""):
        text = clean_text(text)
        if not any(char.isalnum() for char in text):
            raise ValueError("Nothing to say")
        if len(text) > MAX_TEXT:
            raise ValueError(f"Text is longer than {MAX_TEXT} characters")
        if self.kill_active():
            self.stats["rejected"] += 1
            raise Refused("kill_switch", 503, "Kill switch is active (STOP file present)")
        spc = self.engine.seconds_per_char
        sentences, truncated = truncate_sentences(split_sentences(text), max_seconds, spc)
        sentences, head = shorten_first(sentences, self.engine.first_chunk_chars)
        speech = sum(len(s) for s in sentences) * spc
        estimate = estimate_seconds(sentences, spc, self.engine.synth_rtf)
        rank = PRIORITIES[priority]
        with self._cond:
            now = self._clock()
            self._prune_locked(now)
            self._seq += 1
            ident = f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime(self._wall()))}-{self._seq:04d}"
            item = Item(ident, tag, sentences, head, priority, max_seconds, truncated, speech, estimate, now)
            if rank == PRIORITIES["high"]:
                for queued in [q for q in self._queue if q.rank == PRIORITIES["low"]]:
                    self._drop_locked(queued, f"dropped by high priority {ident}")
                if self.current is not None:
                    self._cut_locked(self.current, f"cut by high priority {ident}")
            if len(self._queue) >= self.queue_bound:
                victim = min(self._queue, key=lambda q: (q.rank, q.enqueued))
                if victim.rank < rank:
                    self._drop_locked(victim, f"evicted by {ident}")
                else:
                    self.stats["rejected"] += 1
                    log(f"rejected id={ident} priority={priority}: queue full ({len(self._queue)})")
                    raise Refused("queue_full", 429, "Voice queue is full")
            position = sum(1 for q in self._queue if q.rank >= rank)
            ahead = self._queue[:position]
            self._queue.insert(position, item)
            wait = sum(q.estimate for q in ahead)
            current = self.current
            if current is not None and not current.cut.is_set():
                wait += max(0.0, current.ends_wall - self._wall()) if current.ends_wall else current.estimate
            self._cond.notify_all()
            log(f"queued id={ident} priority={priority} tag={tag!r} sentences={len(sentences)} est={item.estimate:.1f}s text={short(item.text)!r}")
            return {"id": ident, "queued": True, "estimated_seconds": round(item.estimate, 2),
                    "speech_seconds": round(speech, 2), "starts_in_seconds": round(wait, 2),
                    "position": position, "queue": len(self._queue), "truncated": truncated}

    def stop(self, reason="stop", wait=0.0):
        with self._cond:
            dropped = len(self._queue)
            for queued in list(self._queue):
                self._drop_locked(queued, reason)
            current = self.current
            if current is not None:
                self._cut_locked(current, reason)
            if current is not None and wait > 0:
                self._cond.wait_for(lambda: self.current is not current, timeout=wait)
            return {"ok": True, "stopped": current is not None, "dropped": dropped}

    def state(self):
        with self._cond:
            self._prune_locked(self._clock())
            current = self.current
            speaking = current is not None and current.started_wall is not None
            return {
                "speaking": speaking,
                "current": None if current is None else {
                    "id": current.id, "tag": current.tag, "started": current.started_wall, "text": current.text},
                "queue": len(self._queue),
                "engine": self.engine.name,
                "voice": self.engine.voice,
                "ready": self.ready,
                "waiting": [{"id": q.id, "tag": q.tag, "priority": q.priority, "text": short(q.text)} for q in self._queue],
                "fallback": getattr(self.engine, "fallback_reason", None),
                "killed": self.kill_active(),
                "fifo": self.sink.fifo_state(),
                "last_error": self.last_error,
                "stats": dict(self.stats),
            }

    # -- queue internals (lock held)
    def _drop_locked(self, item, reason):
        if item in self._queue:
            self._queue.remove(item)
        self.stats["dropped"] += 1
        log(f"dropped id={item.id} ({reason}) text={short(item.text)!r}")

    def _cut_locked(self, item, reason):
        if not item.cut.is_set():
            item.cut_reason = reason
            item.cut.set()

    def _prune_locked(self, now):
        for item in [q for q in self._queue if now - q.enqueued > self.max_age]:
            self._drop_locked(item, f"older than {self.max_age:g}s, waited {now - item.enqueued:.1f}s")

    # -- threads
    def _watchdog(self):
        while not self._closing.wait(0.2):
            if self.kill_active():
                with self._cond:
                    busy = self.current is not None or self._queue
                if busy:
                    self.stop("kill switch (STOP file)")
            with self._cond:
                self._prune_locked(self._clock())

    def _player(self):
        while not self._closing.is_set():
            with self._cond:
                self._prune_locked(self._clock())
                if not self._queue:
                    self._cond.wait(0.1)
                    continue
                item = self._queue.pop(0)
                self.current = item
            try:
                self._play(item)
            except Exception as error:  # never let the player die
                self.stats["errors"] += 1
                self.last_error = f"{type(error).__name__}: {error}"
                log(f"playback failed id={item.id}: {self.last_error}")
                try:
                    self.sink.cut()
                    self._end(item)
                except Exception:
                    pass

    def _submit_synth(self, sentence):
        return self._pool.submit(self._synth, sentence)

    def _synth(self, sentence):
        samples, rate = self.engine.synthesize(sentence)
        pcm = to_stereo_48k(samples, rate)
        self.ready = True
        return pcm, len(pcm) / (FRAME_BYTES * OUT_RATE)

    def _await(self, future, item):
        """The synthesized sentence, or None when the item was cut meanwhile."""
        deadline = self._clock() + self.synth_timeout
        while True:
            concurrent.futures.wait([future], timeout=0.01)
            if future.done():
                return future.result()
            if item.cut.is_set() or self._closing.is_set():
                future.cancel()
                return None
            if self._clock() > deadline:
                self._pool.shutdown(wait=False, cancel_futures=True)  # abandon the stuck worker
                self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="voice-synth")
                raise EngineError(f"synthesis timed out after {self.synth_timeout:g}s")

    def _play(self, item):
        sink = self.sink
        count = len(item.sentences)
        spc = self.engine.seconds_per_char
        parts, spoken = [], []
        seconds_played = 0.0
        error = None
        future = self._submit_synth(item.sentences[0])
        try:
            for index, sentence in enumerate(item.sentences):
                try:
                    result = self._await(future, item)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    self.stats["errors"] += 1
                    self.last_error = error
                    log(f"synthesis failed id={item.id} sentence {index + 1}/{count}: {error}")
                    break
                future = None
                if result is None:
                    break
                pcm, seconds = result
                if seconds > 0:
                    if index >= item.head and item.max_seconds and seconds_played + seconds > item.max_seconds + 1e-6:
                        item.truncated = True
                        break
                    while sink.buffered_seconds() > LOOKAHEAD:  # play the previous sentence first
                        if item.cut.wait(0.005):
                            break
                    if item.cut.is_set():
                        break
                    now = self._wall()
                    if item.started_wall is None:
                        item.started_wall = now
                    else:
                        late = (now - item.started_wall) - seconds_played
                        if late > 1.5 * BLOCK_SECONDS:  # the sink ran dry: keep the WAV on the stream's clock
                            gap = silence(late)
                            parts.append(gap)
                            seconds_played += len(gap) / (FRAME_BYTES * OUT_RATE)
                    sink.push(pcm)
                    parts.append(pcm)
                    seconds_played += seconds
                    spoken.append(sentence)
                    rest = sum(len(s) for s in item.sentences[index + 1:]) * spc
                    item.ends_wall = item.started_wall + seconds_played + rest
                    self._write_speaking(item)
                if index + 1 < count:
                    future = self._submit_synth(item.sentences[index + 1])
            while sink.buffered_bytes() > 0:  # let the pushed audio finish
                if item.cut.wait(0.005):
                    break
        finally:
            if future is not None:
                future.cancel()
        self._finish(item, parts, spoken, error)

    def _finish(self, item, parts, spoken, error):
        dropped = kept = 0
        if item.cut.is_set():
            dropped, kept = self.sink.cut()
        audio = b"".join(parts)
        if dropped:
            audio = audio[: max(0, len(audio) - dropped)]
        if kept and audio:
            kept = min(kept, len(audio))
            audio = audio[:-kept] + fade_out(audio[-kept:])
        cut = item.cut.is_set() and (dropped > 0 or len(spoken) < len(item.sentences))
        if audio:
            start = item.started_wall
            end = start + len(audio) / (FRAME_BYTES * OUT_RATE)
            self._store(item, audio, spoken, start, end, cut, error)
            self.stats["spoken"] += 1
            log(f"spoken id={item.id} tag={item.tag!r} {end - start:.2f}s cut={cut}"
                + (f" ({item.cut_reason})" if cut else "") + (" truncated" if item.truncated else "")
                + f" text={short(' '.join(spoken))!r}")
        else:
            reason = f"cut before audio ({item.cut_reason})" if item.cut.is_set() else (f"error: {error}" if error else "no audio")
            log(f"nothing played id={item.id}: {reason}")
        if cut:
            self.stats["cut"] += 1
        self._end(item)

    def _end(self, item):
        self._write_speaking(None)
        with self._cond:
            if self.current is item:
                self.current = None
            self._cond.notify_all()

    def _store(self, item, audio, spoken, start, end, cut, error):
        try:
            wav = self.speech_dir / f"{item.id}.wav"
            tmp = wav.with_suffix(".wav.tmp")
            with wave.open(str(tmp), "wb") as handle:
                handle.setnchannels(OUT_CHANNELS)
                handle.setsampwidth(2)
                handle.setframerate(OUT_RATE)
                handle.writeframes(audio)
            os.replace(tmp, wav)
            entry = {"id": item.id, "tag": item.tag, "text": " ".join(spoken),
                     "start_utc": round(start, 3), "end_utc": round(end, 3), "cut": bool(cut)}
            if item.truncated:
                entry["truncated"] = True
            if error:
                entry["error"] = error
            with open(self.speech_dir / "timeline.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
            self._prune_wavs()
        except OSError as exc:
            self.last_error = f"cannot store {item.id}: {exc}"
            log(self.last_error)

    def _prune_wavs(self):
        now = time.time()
        if not self.keep_hours or now - self._last_prune < 600:
            return
        self._last_prune = now
        removed = 0
        for path in self.speech_dir.glob("*.wav"):
            try:
                if now - path.stat().st_mtime > self.keep_hours * 3600:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        if removed:
            log(f"removed {removed} speech files older than {self.keep_hours:g} h")

    def _write_speaking(self, item):
        if item is None:
            data = {"speaking": False, "started_utc": None, "ends_utc": None, "text": "", "id": None}
        else:
            data = {"speaking": True, "started_utc": round(item.started_wall, 3), "ends_utc": round(item.ends_wall, 3),
                    "text": item.text, "id": item.id, "tag": item.tag}
        try:
            with self._file_lock:
                write_json_atomic(self.dir / "speaking.json", data)
        except OSError as error:
            log(f"cannot write speaking.json: {error}")


# ---------------------------------------------------------------- HTTP

async def read_json(request):
    raw = await request.content.read(16385)
    if len(raw) > 16384:
        raise web.HTTPRequestEntityTooLarge(max_size=16384, actual_size=len(raw))
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise web.HTTPBadRequest(text="Invalid JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Expected object")
    return data


def create_app(service, token):
    if not isinstance(token, str) or len(token) < MIN_TOKEN:
        raise ValueError("An operator credential of at least 12 characters is required")
    secret = token.encode()
    no_store = {"Cache-Control": "no-store"}

    @web.middleware
    async def guard(request, handler):
        if request.path != "/healthz":
            supplied = request.headers.get("X-Admin-Token", "").encode()
            if not hmac.compare_digest(supplied, secret):
                raise web.HTTPForbidden(text="Operator authentication required")
        return await handler(request)

    async def healthz(request):
        return web.json_response({"ok": True, "engine": service.engine.name, "ready": service.ready}, headers=no_store)

    async def speak(request):
        data = await read_json(request)
        text = data.get("text")
        if not isinstance(text, str):
            raise web.HTTPBadRequest(text="text must be a string")
        priority = data.get("priority", "normal")
        if priority not in PRIORITIES:
            raise web.HTTPBadRequest(text="priority must be low, normal or high")
        max_seconds = data.get("max_seconds")
        if max_seconds is not None:
            if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) \
                    or not math.isfinite(max_seconds) or not 0 < max_seconds <= 600:
                raise web.HTTPBadRequest(text="max_seconds must be a number between 0 and 600")
        tag = data.get("tag", "")
        if not isinstance(tag, str) or len(tag) > MAX_TAG:
            raise web.HTTPBadRequest(text=f"tag must be a string of at most {MAX_TAG} characters")
        try:
            result = service.submit(text, priority, max_seconds, tag)
        except Refused as refusal:
            return web.json_response({"id": None, "queued": False, "reason": refusal.reason, "error": refusal.message},
                                     status=refusal.status, headers=no_store)
        except ValueError as error:
            raise web.HTTPBadRequest(text=str(error))
        return web.json_response(result, headers=no_store)

    async def stop(request):
        result = await asyncio.to_thread(service.stop, "stop requested", 0.5)
        return web.json_response(result, headers=no_store)

    async def state(request):
        return web.json_response(service.state(), headers=no_store)

    app = web.Application(middlewares=[guard], client_max_size=16384)
    app.router.add_get("/healthz", healthz)
    app.router.add_post("/speak", speak)
    app.router.add_post("/stop", stop)
    app.router.add_get("/state", state)
    return app


# ---------------------------------------------------------------- entry point

def load_token(token_file):
    if token_file:
        return Path(token_file).read_text().strip()
    return os.environ.get("SUB01_ADMIN_TOKEN", "").strip()


def _parse_fallback(value):
    """voice.json `fallback` -> None (no fallback) or {"voice": spec|None, "speed": float|None}.

    Accepts "kokoro", "kokoro:am_puck", "am_puck", "none"/null, or {"engine": "kokoro", "voice", "speed"}."""
    if value is None or value is False or value in ("", "none", "off"):
        return None
    voice = speed = None
    if isinstance(value, str):
        head, _, rest = value.partition(":")
        voice = rest or None if head == "kokoro" else value
    elif isinstance(value, dict):
        if value.get("engine", "kokoro") != "kokoro":
            raise ValueError(f"unsupported fallback engine {value.get('engine')!r} (only kokoro)")
        voice, speed = value.get("voice"), value.get("speed")
    else:
        raise ValueError(f"cannot read fallback {value!r}")
    if voice is not None:
        parse_voice_spec(voice)
    if speed is not None and (isinstance(speed, bool) or not isinstance(speed, (int, float))):
        raise ValueError("fallback speed must be a number")
    return {"voice": voice, "speed": speed}


def load_voice_config(path):
    """Read a `sub01.streamer-voice.v1` JSON file: engine, voice_prompt, exaggeration, cfg_weight, fallback.

    Returns only the keys present. A relative voice_prompt is relative to the file."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read voice config {path}: {error}")
    if not isinstance(data, dict):
        raise ValueError(f"voice config {path} must be a JSON object")
    if data.get("schema", VOICE_CONFIG_SCHEMA) != VOICE_CONFIG_SCHEMA:
        raise ValueError(f"voice config schema {data['schema']!r} is not {VOICE_CONFIG_SCHEMA}")
    config = {}
    if data.get("engine") is not None:
        if data["engine"] not in ENGINES:
            raise ValueError(f"voice config engine {data['engine']!r} is not one of {', '.join(ENGINES)}")
        config["engine"] = data["engine"]
    if data.get("voice_prompt"):
        prompt = Path(str(data["voice_prompt"]))
        config["voice_prompt"] = str(prompt if prompt.is_absolute() else path.parent / prompt)
    for key, high in (("exaggeration", 2.0), ("cfg_weight", 1.0)):
        if data.get(key) is not None:
            value = data[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= high:
                raise ValueError(f"voice config {key} must be a number between 0 and {high:g}")
            config[key] = float(value)
    if "fallback" in data:
        config["fallback"] = _parse_fallback(data["fallback"])
    return config


def resolve_settings(args, streamer_dir):
    """Effective engine settings. Precedence: command-line flags, then --voice-config, then the defaults."""
    config = load_voice_config(args.voice_config) if args.voice_config else {}
    engine = args.engine or config.get("engine", DEFAULT_ENGINE)
    settings = types.SimpleNamespace(
        engine=engine, device=args.device, threads=args.threads, eleven_model=args.eleven_model,
        speed=args.speed if args.speed is not None else 1.0, voice=args.voice, voice_prompt=None,
        exaggeration=args.exaggeration if args.exaggeration is not None else config.get("exaggeration", DEFAULT_EXAGGERATION),
        cfg_weight=args.cfg_weight if args.cfg_weight is not None else config.get("cfg_weight", DEFAULT_CFG_WEIGHT),
        fallback_voice=None, fallback_speed=None, config=config)
    if engine != "chatterbox":
        return settings
    prompt = args.voice_prompt or config.get("voice_prompt")
    if not prompt:  # the pod's copy first, then the one in the repository
        candidates = [Path(streamer_dir) / "voice" / DEFAULT_PROMPT, ROOT / "assets" / "voice" / DEFAULT_PROMPT]
        prompt = next((str(c) for c in candidates if c.is_file()), None)
        if not prompt:
            raise ValueError("no voice prompt: pass --voice-prompt (looked for " + ", ".join(str(c) for c in candidates) + ")")
    settings.voice_prompt = prompt
    if args.fallback == "none":
        fallback = None
    elif args.fallback == "kokoro" or "fallback" not in config:
        fallback = {"voice": None, "speed": None}
    else:
        fallback = config["fallback"]
    if fallback is not None:
        settings.fallback_voice = args.voice or fallback["voice"] or DEFAULT_VOICE
        settings.fallback_speed = args.speed if args.speed is not None else (fallback["speed"] or 1.0)
    return settings


def build_engine(settings):
    if settings.engine == "mock":
        return MockEngine()
    if settings.engine == "elevenlabs":
        key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        voice = settings.voice or os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        return ElevenLabsEngine(key, voice, model_id=settings.eleven_model)
    if settings.engine == "kokoro":
        return KokoroEngine(settings.voice or DEFAULT_VOICE, speed=settings.speed, threads=settings.threads)
    primary = ChatterboxEngine(settings.voice_prompt, settings.exaggeration, settings.cfg_weight, device=settings.device)
    if settings.fallback_voice is None:
        return primary
    return FallbackEngine(primary, KokoroEngine(settings.fallback_voice, speed=settings.fallback_speed, threads=settings.threads))


async def serve(args, engine, token):
    streamer = Path(args.streamer_dir)
    streamer.mkdir(parents=True, exist_ok=True)
    sink = PcmSink(streamer / "voice.pcm")
    service = VoiceService(engine, sink, streamer, keep_hours=args.keep_hours)
    service.start()
    threading.Thread(target=service.warmup, name="voice-warmup", daemon=True).start()
    runner = web.AppRunner(create_app(service, token), access_log=None)  # request lines are not logged
    await runner.setup()
    try:
        await web.TCPSite(runner, args.host, args.port).start()
        fallback = getattr(engine, "fallback", None)
        log(f"listening on http://{args.host}:{args.port} engine={engine.name} voice={engine.voice}"
            + (f" fallback={fallback.name}:{fallback.voice}" if fallback else "") + f" streamer-dir={streamer}")
        stop = asyncio.Event()
        for name in ("SIGINT", "SIGTERM"):
            try:
                asyncio.get_running_loop().add_signal_handler(getattr(signal, name), stop.set)
            except (NotImplementedError, AttributeError):
                pass
        await stop.wait()
    finally:
        log("shutting down")
        await runner.cleanup()
        service.close()


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--token-file", help="file holding the operator credential (else SUB01_ADMIN_TOKEN)")
    parser.add_argument("--streamer-dir", default=os.environ.get("STREAMER_DIR", DEFAULT_STREAMER_DIR))
    parser.add_argument("--voice-config", help=f"JSON file ({VOICE_CONFIG_SCHEMA}) with engine, voice_prompt, exaggeration, "
                        "cfg_weight, fallback; command-line flags override it")
    parser.add_argument("--engine", choices=list(ENGINES), help=f"default {DEFAULT_ENGINE}")
    parser.add_argument("--voice", help=f"kokoro (also the chatterbox fallback): weighted blend, default {DEFAULT_VOICE!r}, "
                        "e.g. 'am_michael:0.55,am_puck:0.45'; elevenlabs: voice id")
    parser.add_argument("--voice-prompt", help=f"chatterbox: synthetic reference WAV that sets the identity (never a real person); "
                        f"default <streamer-dir>/voice/{DEFAULT_PROMPT}, else assets/voice/ in the repository")
    parser.add_argument("--exaggeration", type=float, help=f"chatterbox expressiveness, default {DEFAULT_EXAGGERATION}")
    parser.add_argument("--cfg-weight", type=float, help=f"chatterbox pacing / guidance, default {DEFAULT_CFG_WEIGHT}")
    parser.add_argument("--device", default="cuda", help="chatterbox device")
    parser.add_argument("--fallback", choices=["kokoro", "none"],
                        help="chatterbox: engine to switch to when it cannot load or CUDA fails (default kokoro)")
    parser.add_argument("--speed", type=float, help="kokoro speaking speed (0.5-2.0), default 1.0")
    parser.add_argument("--threads", type=int, default=0, help="torch CPU threads for kokoro (0 = torch default)")
    parser.add_argument("--eleven-model", default="eleven_flash_v2_5")
    parser.add_argument("--keep-hours", type=float, default=24.0, help="delete speech WAVs older than this (0 = keep all)")
    parser.add_argument("--offline", action="store_true", help="never contact HuggingFace (model must be in HF_HOME)")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.host not in LOOPBACK:
        parser.error("the voice server binds only to loopback")
    token = load_token(args.token_file)
    if len(token) < MIN_TOKEN:
        parser.error("set SUB01_ADMIN_TOKEN or --token-file (at least 12 characters)")
    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    try:
        engine = build_engine(resolve_settings(args, args.streamer_dir))
    except ValueError as error:
        parser.error(str(error))
    try:
        asyncio.run(serve(args, engine, token))
    except OSError as error:
        print(f"voice: cannot start: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
