"""Voice server: speak/queue/priority cut/stop, timeline, speaking.json, FIFO pacing, sentence splitting.

Everything runs on MockEngine (sine tone, no model) in a temporary streamer directory, in real time
with short utterances; the suite takes a few seconds.
"""

import asyncio
import importlib.util
import json
import os
import sys
import threading
import time
import types
import wave
from pathlib import Path

import numpy as np
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("voice_server", ROOT / "scripts/voice_server.py")
vs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vs)

TOKEN = "operator-credential-test"
AUTH = {"X-Admin-Token": TOKEN}
FAST = 0.01  # seconds of mock speech per character: a 25 character sentence lasts 0.25 s
LONG = "This sentence is long enough to be interrupted well before it ends, said the voice."  # 84 chars
BYTES_PER_SECOND = vs.OUT_RATE * vs.FRAME_BYTES


def until(predicate, timeout=5.0, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError(f"timed out waiting for {what}")


def idle(svc):
    state = svc.state()
    return state["current"] is None and state["queue"] == 0


def timeline(path):
    file = Path(path) / "speech" / "timeline.jsonl"
    return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []


def speaking(path):
    return json.loads((Path(path) / "speaking.json").read_text())


def read_wav(path, ident):
    with wave.open(str(Path(path) / "speech" / f"{ident}.wav")) as handle:
        info = (handle.getnchannels(), handle.getsampwidth(), handle.getframerate())
        frames = np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16).reshape(-1, 2)
    return info, frames


@pytest.fixture
def make_service(tmp_path):
    made = []

    def factory(engine=None, **options):
        svc = vs.VoiceService(engine or vs.MockEngine(seconds_per_char=FAST), vs.PcmSink(tmp_path / "voice.pcm"),
                              tmp_path, **options)
        svc.start()
        svc.warmup()
        made.append(svc)
        return svc

    yield factory
    for svc in made:
        svc.close()


# ---------------------------------------------------------------- text and audio helpers

def test_sentence_splitting():
    split = vs.split_sentences
    assert split("I saw Dr. Smith at 3.5 percent. He left, e.g. early. Then it rained!") == [
        "I saw Dr. Smith at 3.5 percent.", "He left, e.g. early.", "Then it rained!"]
    assert split("J. Smith went home. He was tired.") == ["J. Smith went home.", "He was tired."]
    assert split("Well... maybe not today. Okay then, see you tomorrow.") == [
        "Well... maybe not today.", "Okay then, see you tomorrow."]
    assert split("First line here\nSecond line here") == ["First line here", "Second line here"]
    # tiny fragments join their neighbour instead of being synthesized alone
    assert split("Yes. That was wonderful to see.") == ["Yes. That was wonderful to see."]
    assert split("That was wonderful to see. Yes.") == ["That was wonderful to see. Yes."]
    assert split("") == [] and split("  \n \t ") == []
    assert split("no punctuation at all") == ["no punctuation at all"]
    long_text = "word, " * 100 + "end."
    pieces = split(long_text)
    assert len(pieces) > 1 and all(len(piece) <= 240 for piece in pieces)
    assert " ".join(pieces).split() == long_text.split()
    assert all(len(piece) <= 50 for piece in split("x" * 400, max_chars=50)) and len(split("x" * 400, max_chars=50)) == 8


def test_truncation_keeps_whole_sentences():
    sentences = ["a" * 10, "b" * 10, "c" * 10]
    assert vs.truncate_sentences(sentences, 2.5, 0.1) == (sentences[:2], True)
    assert vs.truncate_sentences(sentences, 3.0, 0.1) == (sentences, False)
    assert vs.truncate_sentences(sentences, None, 0.1) == (sentences, False)
    assert vs.truncate_sentences(sentences, 0.2, 0.1) == (sentences[:1], True)  # the first sentence always stays


def test_first_chunk_and_estimates():
    first = "This is a fairly long opening clause, and then the rest of the sentence continues until it ends."
    chunks, head = vs.shorten_first([first, "Next one."], 50)
    assert head == 2 and chunks[0] == "This is a fairly long opening clause," and chunks[1].startswith("and then")
    assert chunks[2] == "Next one." and " ".join(chunks[:2]) == first
    assert vs.shorten_first([first], None) == ([first], 1)
    assert vs.shorten_first(["word " * 30], 50)[1] == 1  # no clause break to use
    two = ["a" * 10, "b" * 10]
    assert vs.estimate_seconds(two, 0.1, 0.0) == pytest.approx(2.0)
    assert vs.estimate_seconds(two, 0.1, 0.5) == pytest.approx(2.5)  # 0.5 s lead-in, the second chunk is ready in time
    assert vs.estimate_seconds(two, 0.1, 2.0) == pytest.approx(5.0)  # rendering slower than speech: it stalls


def test_resampling_and_stereo():
    ramp = (np.arange(1000) * 10).astype(np.int16)
    pcm = vs.to_stereo_48k(ramp, 24000)
    frames = np.frombuffer(pcm, dtype=np.int16).reshape(-1, 2)
    assert len(frames) == 2000 and (frames[:, 0] == frames[:, 1]).all()
    assert (frames[:1999, 0] == 5 * np.arange(1999)).all()  # linear interpolation between neighbours
    assert len(vs.to_stereo_48k(ramp, 48000)) == 1000 * vs.FRAME_BYTES
    assert vs.to_stereo_48k(np.zeros(0, dtype=np.int16), 24000) == b""
    assert np.array_equal(vs.to_int16(np.array([0.0, 1.0, -1.0, 3.0])), [0, 32767, -32767, 32767])


def test_mock_engine_lasts_seven_hundredths_of_a_second_per_character():
    samples, rate = vs.MockEngine().synthesize("x" * 100)
    assert samples.dtype == np.int16 and rate == 24000
    assert len(samples) == round(100 * 0.07 * 24000)
    assert np.abs(samples).max() > 1000


def test_voice_spec():
    assert vs.parse_voice_spec("am_michael:0.55,am_puck:0.45") == [("am_michael", pytest.approx(0.55)), ("am_puck", pytest.approx(0.45))]
    assert vs.parse_voice_spec("am_michael") == [("am_michael", 1.0)]
    assert vs.parse_voice_spec("am_michael:3, am_puck:1") == [("am_michael", pytest.approx(0.75)), ("am_puck", pytest.approx(0.25))]
    for bad in ["", "Michael", "am_michael:0", "am_michael:x", "am_michael:-1", "am_michael:nan"]:
        with pytest.raises(ValueError):
            vs.parse_voice_spec(bad)
    assert vs.KokoroEngine().voice == "am_puck:1.00"
    assert vs.KokoroEngine("am_michael:0.55,am_puck:0.45").voice == "am_michael:0.55,am_puck:0.45"


def test_cut_leaves_a_faded_tail():
    sink = vs.PcmSink(None)
    pcm = np.full(vs.OUT_RATE * 2, 10000, dtype=np.int16).tobytes()  # one second, stereo
    sink.push(pcm)
    dropped, kept = sink.cut()
    assert kept == vs.FADE_FRAMES * vs.FRAME_BYTES and dropped == len(pcm) - kept
    tail = np.frombuffer(sink._take(kept), dtype=np.int16).reshape(-1, 2)
    assert tail[0, 0] == 10000 and abs(int(tail[-1, 0])) < 100
    assert (np.diff(tail[:, 0].astype(int)) <= 0).all()
    assert sink.buffered_bytes() == 0


# ---------------------------------------------------------------- service behaviour

def test_speak_plays_and_is_recorded(make_service, tmp_path):
    svc = make_service()
    before = time.time()
    text = "Hello there, this is a test."  # 28 characters: 0.28 s
    result = svc.submit(text, tag="greet")
    assert result["queued"] is True and result["id"] and result["queue"] == 1
    assert result["estimated_seconds"] == pytest.approx(0.28, abs=0.01)
    until(lambda: svc.state()["speaking"], what="speech to start")
    state = svc.state()
    assert state["current"]["id"] == result["id"] and state["current"]["tag"] == "greet"
    assert state["current"]["text"] == text and isinstance(state["current"]["started"], float)
    assert (state["engine"], state["voice"], state["queue"]) == ("mock", "sine", 0)
    live = speaking(tmp_path)
    assert live["speaking"] is True and live["id"] == result["id"] and live["text"] == text
    assert live["ends_utc"] - live["started_utc"] == pytest.approx(0.28, abs=0.05)
    until(lambda: idle(svc), what="speech to end")
    assert speaking(tmp_path) == {"speaking": False, "started_utc": None, "ends_utc": None, "text": "", "id": None}
    [entry] = timeline(tmp_path)
    assert set(entry) == {"id", "tag", "text", "start_utc", "end_utc", "cut"}
    assert (entry["id"], entry["tag"], entry["text"], entry["cut"]) == (result["id"], "greet", text, False)
    assert before - 0.1 <= entry["start_utc"] <= time.time() and entry["end_utc"] - entry["start_utc"] == pytest.approx(0.28, abs=0.03)
    (channels, width, rate), frames = read_wav(tmp_path, result["id"])
    assert (channels, width, rate) == (2, 2, 48000)
    assert len(frames) / 48000 == pytest.approx(entry["end_utc"] - entry["start_utc"], abs=0.001)
    assert np.abs(frames).max() > 1000 and (frames[:, 0] == frames[:, 1]).all()
    assert svc.state()["stats"]["spoken"] == 1


def test_queue_order_bound_and_eviction(make_service, tmp_path):
    svc = make_service()
    svc.submit("This one keeps the voice busy for a while.", tag="current")
    until(lambda: svc.state()["speaking"])
    svc.submit("Second thing.", tag="n1")
    svc.submit("Third thing.", "low", tag="l1")
    svc.submit("Fourth thing.", tag="n2")
    assert [w["tag"] for w in svc.state()["waiting"]] == ["n1", "n2", "l1"]  # priority first, then arrival
    with pytest.raises(vs.Refused) as full:
        svc.submit("Fifth thing here.", "low")
    assert full.value.status == 429 and full.value.reason == "queue_full"
    svc.submit("Sixth thing here.", tag="n3")  # a normal item evicts the waiting low one
    assert [w["tag"] for w in svc.state()["waiting"]] == ["n1", "n2", "n3"]
    with pytest.raises(vs.Refused):
        svc.submit("Seventh thing.")  # normal against a full queue of normals
    stats = svc.state()["stats"]
    assert (stats["dropped"], stats["rejected"]) == (1, 2)
    until(lambda: idle(svc) and len(timeline(tmp_path)) == 4, what="the queue to play out")
    assert [e["tag"] for e in timeline(tmp_path)] == ["current", "n1", "n2", "n3"]


def test_high_priority_cuts_current_and_drops_low(make_service, tmp_path):
    svc = make_service()
    svc.submit(LONG, tag="long")
    until(lambda: svc.state()["speaking"])
    time.sleep(0.15)
    svc.submit("A low priority remark.", "low", tag="low1")
    svc.submit("A normal remark here.", tag="norm1")
    asked = time.monotonic()
    urgent = svc.submit("Urgent message now.", "high", tag="urgent")
    assert urgent["position"] == 0
    assert [w["tag"] for w in svc.state()["waiting"]] == ["urgent", "norm1"]
    until(lambda: len(timeline(tmp_path)) >= 1, what="the cut utterance to be recorded")
    assert time.monotonic() - asked < 0.5
    cut = timeline(tmp_path)[0]
    assert cut["tag"] == "long" and cut["cut"] is True
    assert 0.1 < cut["end_utc"] - cut["start_utc"] < 0.6  # nowhere near the 0.84 s of the full sentence
    _, frames = read_wav(tmp_path, cut["id"])
    assert len(frames) / 48000 == pytest.approx(cut["end_utc"] - cut["start_utc"], abs=0.001)
    assert np.abs(frames[-1]).max() < 100  # faded out, not chopped
    until(lambda: idle(svc) and len(timeline(tmp_path)) == 3, what="the rest to play")
    assert [e["tag"] for e in timeline(tmp_path)] == ["long", "urgent", "norm1"]
    assert [e["cut"] for e in timeline(tmp_path)] == [True, False, False]
    assert svc.state()["stats"]["cut"] == 1


def test_stop_cuts_and_clears(make_service, tmp_path):
    svc = make_service()
    svc.submit(LONG, tag="a")
    svc.submit("Another one here.", tag="b")
    until(lambda: svc.state()["speaking"])
    assert svc.stop(wait=1.0) == {"ok": True, "stopped": True, "dropped": 1}
    state = svc.state()
    assert state["speaking"] is False and state["current"] is None and state["queue"] == 0
    assert speaking(tmp_path)["speaking"] is False
    assert [(e["tag"], e["cut"]) for e in timeline(tmp_path)] == [("a", True)]
    assert svc.stop() == {"ok": True, "stopped": False, "dropped": 0}
    svc.submit("Back again, friend.", tag="c")  # still serving
    until(lambda: len(timeline(tmp_path)) == 2)
    assert timeline(tmp_path)[1]["cut"] is False


def test_stale_items_are_dropped_and_logged(make_service, capsys):
    svc = make_service(max_age=0.3)
    svc.submit("x" * 60, tag="busy")  # 0.6 s
    svc.submit("Stale before it starts.", tag="late")
    until(lambda: svc.state()["queue"] == 0, timeout=2.0, what="the old item to be dropped")
    assert svc.state()["stats"]["dropped"] == 1
    out = capsys.readouterr().out
    assert "voice: dropped" in out and "older than 0.3s" in out


def test_kill_file_cuts_speech_and_refuses_new(make_service, tmp_path):
    svc = make_service()
    svc.submit(LONG, tag="long")
    until(lambda: svc.state()["speaking"])
    (tmp_path / "STOP").write_text("")
    until(lambda: idle(svc), timeout=1.5, what="the kill file to cut speech")
    assert timeline(tmp_path)[0]["cut"] is True
    with pytest.raises(vs.Refused) as refused:
        svc.submit("Not while killed.")
    assert refused.value.status == 503 and svc.state()["killed"] is True
    (tmp_path / "STOP").unlink()
    svc.submit("Back on the air.")
    until(lambda: len(timeline(tmp_path)) == 2)


def test_max_seconds_stops_at_a_sentence_boundary(make_service, tmp_path):
    svc = make_service()
    text = "First sentence here now. Second sentence here now. Third sentence here now. Fourth sentence here now."
    result = svc.submit(text, max_seconds=0.6, tag="cap")
    assert result["truncated"] is True and result["speech_seconds"] == pytest.approx(0.49, abs=0.01)
    until(lambda: len(timeline(tmp_path)) == 1)
    [entry] = timeline(tmp_path)
    assert entry["text"] == "First sentence here now. Second sentence here now."
    assert entry["cut"] is False and entry["truncated"] is True


def test_max_seconds_is_enforced_on_actual_durations(make_service, tmp_path):
    class Understated(vs.MockEngine):
        def _tone(self, text):
            return super()._tone(text * 2)  # speaks twice as long as it advertises

    svc = make_service(Understated(seconds_per_char=FAST))
    svc.submit("First sentence here now. Second sentence here now.", max_seconds=0.6)
    until(lambda: len(timeline(tmp_path)) == 1)
    assert timeline(tmp_path)[0]["text"] == "First sentence here now."
    assert timeline(tmp_path)[0]["truncated"] is True


def test_synthesis_errors_never_stop_the_server(make_service, tmp_path, capsys):
    class Flaky(vs.MockEngine):
        def _tone(self, text):
            if "BOOM" in text:
                raise RuntimeError("engine exploded")
            return super()._tone(text)

    svc = make_service(Flaky(seconds_per_char=FAST))
    svc.submit("BOOM goes the engine.", tag="bad")
    until(lambda: idle(svc) and svc.state()["stats"]["errors"] == 1, what="the failure to be handled")
    state = svc.state()
    assert state["speaking"] is False and "engine exploded" in state["last_error"]
    assert timeline(tmp_path) == [] and speaking(tmp_path)["speaking"] is False
    assert "voice: synthesis failed" in capsys.readouterr().out
    svc.submit("Fine first sentence here. BOOM in the second sentence.", tag="partial")
    until(lambda: idle(svc) and len(timeline(tmp_path)) == 1, what="the partial utterance")
    [entry] = timeline(tmp_path)
    assert entry["text"] == "Fine first sentence here." and entry["cut"] is False and "engine exploded" in entry["error"]
    svc.submit("All good again.", tag="ok")
    until(lambda: len(timeline(tmp_path)) == 2)
    assert svc.state()["stats"]["errors"] == 2


def test_first_sentence_plays_while_the_next_is_synthesized(make_service, tmp_path):
    svc_holder = {}
    seen = []

    class Probe(vs.MockEngine):
        def synthesize(self, text):
            seen.append(svc_holder["svc"].state()["speaking"])  # is audio already playing as this call starts?
            return super().synthesize(text)

    engine = Probe(seconds_per_char=0.025, delay=0.1)  # 25 characters: 0.625 s of speech, 0.1 s to render
    svc = make_service(engine)
    svc_holder["svc"] = svc
    seen.clear()
    engine.calls.clear()
    text = "First sentence goes here. Second sentence goes here. Third sentence goes here."
    svc.submit(text)
    until(lambda: len(timeline(tmp_path)) == 1, timeout=6, what="the utterance")
    order = [call[0] for call in engine.calls]
    assert order == ["First sentence goes here.", "Second sentence goes here.", "Third sentence goes here."]
    assert seen == [False, True, True]  # rendering of 2 and 3 happened under playing audio
    (_, _, end1), (_, start2, end2), (_, start3, _) = engine.calls
    assert start2 >= end1 - 0.01  # one synthesis at a time, in order
    assert start3 - end2 > 0.15  # but never more than about one sentence ahead of playback
    [entry] = timeline(tmp_path)
    assert entry["end_utc"] - entry["start_utc"] == pytest.approx(3 * 0.625, abs=0.06)  # gapless


def test_a_late_sentence_leaves_a_gap_in_the_wav(make_service, tmp_path):
    svc = make_service(vs.MockEngine(seconds_per_char=FAST, delay=0.4))  # renders slower than it speaks
    svc.submit("First sentence goes here. Second sentence goes here.")
    until(lambda: len(timeline(tmp_path)) == 1, timeout=6)
    [entry] = timeline(tmp_path)
    # 0.25 s + about 0.15 s of silence the stream really carried + 0.25 s
    assert entry["end_utc"] - entry["start_utc"] == pytest.approx(0.65, abs=0.08)
    _, frames = read_wav(tmp_path, entry["id"])
    silent = np.abs(frames[:, 0]) < 5
    assert 0.1 < silent.sum() / 48000 < 0.4  # sine zero crossings aside, the gap is silent


def test_a_long_first_sentence_is_rendered_in_two_chunks(make_service, tmp_path):
    engine = vs.MockEngine(seconds_per_char=0.005)
    engine.first_chunk_chars = 40
    svc = make_service(engine)
    engine.calls.clear()
    text = "Well then, this opening goes on and on, so it is split into two chunks. Short follow up here."
    result = svc.submit(text, tag="two")
    until(lambda: len(timeline(tmp_path)) == 1)
    assert [c[0] for c in engine.calls][0] == "Well then, this opening goes on and on,"
    assert len(engine.calls) == 3
    assert timeline(tmp_path)[0]["text"] == text and result["queue"] == 1


# ---------------------------------------------------------------- engines

def test_fallback_engine_switches_once_when_the_primary_cannot_load(monkeypatch, capsys, make_service, tmp_path):
    monkeypatch.setitem(sys.modules, "torch", None)  # `import torch` fails, as on a machine without CUDA torch
    engine = vs.FallbackEngine(vs.ChatterboxEngine(device="cuda"), vs.MockEngine(seconds_per_char=FAST))
    assert (engine.name, engine.voice) == ("chatterbox", "built-in")
    svc = make_service(engine)  # warmup already fell back
    assert svc.state()["engine"] == "mock" and "torch" in svc.state()["fallback"]
    svc.submit("Spoken by the fallback.")
    until(lambda: len(timeline(tmp_path)) == 1)
    engine.synthesize("again")
    assert capsys.readouterr().out.count("falling back to mock") == 1


def test_fallback_engine_keeps_the_primary_for_ordinary_errors():
    class Primary(vs.Engine):
        name, loaded = "primary", True

        def synthesize(self, text):
            raise ValueError("bad text")

    engine = vs.FallbackEngine(Primary(), vs.MockEngine())
    with pytest.raises(ValueError):
        engine.synthesize("hello")
    assert engine.name == "primary" and engine.fallback_reason is None

    class Cuda(Primary):
        def synthesize(self, text):
            raise RuntimeError("CUDA out of memory")

    engine = vs.FallbackEngine(Cuda(), vs.MockEngine())
    assert engine.synthesize("hello")[1] == 24000 and engine.name == "mock"


class Tensor:
    """Just enough of a torch tensor for the engines' glue code."""

    def __init__(self, array):
        self.array = np.asarray(array, dtype=np.float32)

    def __mul__(self, weight):
        return Tensor(self.array * weight)

    def __add__(self, other):
        return Tensor(self.array + other.array)

    def to(self, dtype):
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.array


def test_chatterbox_engine_calls_the_documented_api(monkeypatch, tmp_path):
    calls = {"generate": []}

    class Model:
        sr = 24000

        def prepare_conditionals(self, path, exaggeration=0.5):
            calls["prepared"] = (path, exaggeration)

        def generate(self, text, **options):
            calls["generate"].append((text, options))
            return Tensor(np.full((1, 2400), 0.5))

    class Chatterbox:
        @staticmethod
        def from_pretrained(device):
            calls["device"] = device
            return Model()

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: True)))
    monkeypatch.setitem(sys.modules, "chatterbox", types.ModuleType("chatterbox"))
    monkeypatch.setitem(sys.modules, "chatterbox.tts", types.SimpleNamespace(ChatterboxTTS=Chatterbox))
    prompt = tmp_path / "reference.wav"
    prompt.write_bytes(b"RIFF")
    engine = vs.ChatterboxEngine(prompt, exaggeration=0.45, cfg_weight=0.5)
    assert engine.voice == "reference.wav" and engine.loaded is False
    samples, rate = engine.synthesize("Hello there.")
    assert rate == 24000 and samples.dtype == np.int16 and len(samples) == 2400 and samples[0] == 16384
    assert calls["device"] == "cuda" and calls["prepared"] == (str(prompt), 0.45)  # reference embedded once
    assert calls["generate"] == [("Hello there.", {"exaggeration": 0.45, "cfg_weight": 0.5})]
    assert engine.loaded is True
    with pytest.raises(ValueError):
        vs.ChatterboxEngine(tmp_path / "missing.wav")


def test_kokoro_engine_blends_voices_on_cpu(monkeypatch):
    seen = {}
    packs = {"am_michael": np.full(4, 1.0), "am_puck": np.full(4, 3.0)}

    class Pipeline:
        def __init__(self, lang_code, repo_id=None, device=None):
            seen["init"] = (lang_code, repo_id, device)

        def load_single_voice(self, name):
            return Tensor(packs[name])

        def __call__(self, text, voice=None, speed=1):
            seen["call"] = (text, voice, speed)
            yield types.SimpleNamespace(audio=Tensor(np.full(2400, 0.5)))
            yield types.SimpleNamespace(audio=Tensor(np.full(2400, -0.25)))

    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(float32="float32", set_num_threads=lambda n: seen.update(threads=n)))
    monkeypatch.setitem(sys.modules, "kokoro", types.SimpleNamespace(KPipeline=Pipeline))
    engine = vs.KokoroEngine("am_michael:0.55,am_puck:0.45", speed=1.1, threads=3)
    samples, rate = engine.synthesize("Hello there.")
    assert rate == 24000 and len(samples) == 4800 and samples[0] == 16384 and samples[-1] == -8192
    assert seen["init"] == ("a", "hexgrad/Kokoro-82M", "cpu") and seen["threads"] == 3
    text, voice, speed = seen["call"]
    assert text == "Hello there." and speed == pytest.approx(1.1)
    assert voice.array[0] == pytest.approx(0.55 * 1.0 + 0.45 * 3.0)


def test_elevenlabs_engine_requests_pcm(tmp_path):
    seen = {}

    async def handler(request):
        seen.update(path=request.path, query=dict(request.query), key=request.headers.get("xi-api-key"), body=await request.json())
        if seen["body"]["text"] == "reject":
            return web.Response(status=401, text="invalid key")
        return web.Response(body=np.arange(240, dtype="<i2").tobytes() + b"\x01", content_type="audio/pcm")

    async def body():
        app = web.Application()
        app.router.add_post("/v1/text-to-speech/{voice}", handler)
        server = TestServer(app)
        await server.start_server()
        try:
            engine = vs.ElevenLabsEngine("secret-key", "VOICE1", base_url=str(server.make_url("")), trust_env=False)
            samples, rate = await asyncio.to_thread(engine.synthesize, "Hello there")
            assert rate == 24000 and samples.dtype == np.int16 and len(samples) == 240  # the odd trailing byte is dropped
            assert seen["path"] == "/v1/text-to-speech/VOICE1" and seen["query"] == {"output_format": "pcm_24000"}
            assert seen["key"] == "secret-key" and seen["body"]["text"] == "Hello there"
            with pytest.raises(vs.EngineError) as failure:
                await asyncio.to_thread(engine.synthesize, "reject")
            assert "401" in str(failure.value) and "secret-key" not in str(failure.value)
        finally:
            await server.close()

    asyncio.run(body())
    with pytest.raises(ValueError):
        vs.ElevenLabsEngine("", "VOICE1")


def cli(*argv):
    return vs.build_parser().parse_args(list(argv))


def settings_for(tmp_path, *argv):
    return vs.resolve_settings(cli(*argv), tmp_path)


def test_defaults_are_the_owners_voice(tmp_path):
    prompt = tmp_path / "voice" / vs.DEFAULT_PROMPT
    prompt.parent.mkdir()
    prompt.write_bytes(b"RIFF")
    s = settings_for(tmp_path)
    assert (s.engine, s.voice_prompt, s.exaggeration, s.cfg_weight, s.device) == ("chatterbox", str(prompt), 0.45, 0.5, "cuda")
    assert (s.fallback_voice, s.fallback_speed) == ("am_puck", 1.0)
    engine = vs.build_engine(s)
    assert isinstance(engine, vs.FallbackEngine) and engine.name == "chatterbox" and engine.voice == vs.DEFAULT_PROMPT
    assert engine.fallback.name == "kokoro" and engine.fallback.voice == "am_puck:1.00"
    s = settings_for(tmp_path, "--fallback", "none")
    assert isinstance(vs.build_engine(s), vs.ChatterboxEngine)


@pytest.mark.skipif(not (ROOT / "assets/voice" / vs.DEFAULT_PROMPT).is_file(), reason="reference WAV is not in this checkout")
def test_default_prompt_falls_back_to_the_repository_copy(tmp_path):
    assert settings_for(tmp_path).voice_prompt == str(ROOT / "assets/voice" / vs.DEFAULT_PROMPT)


def test_voice_config_and_precedence(tmp_path):
    (tmp_path / "ref.wav").write_bytes(b"RIFF")
    config = tmp_path / "voice.json"
    config.write_text(json.dumps({"schema": "sub01.streamer-voice.v1", "engine": "chatterbox", "voice_prompt": "ref.wav",
                                  "exaggeration": 0.6, "cfg_weight": 0.3, "fallback": "kokoro:am_michael:0.55,am_puck:0.45",
                                  "note": "unknown fields are ignored"}))
    s = settings_for(tmp_path, "--voice-config", str(config))
    assert (s.engine, s.voice_prompt, s.exaggeration, s.cfg_weight) == ("chatterbox", str(tmp_path / "ref.wav"), 0.6, 0.3)
    assert s.fallback_voice == "am_michael:0.55,am_puck:0.45"
    s = settings_for(tmp_path, "--voice-config", str(config), "--exaggeration", "0.9", "--voice", "am_puck", "--speed", "1.2")
    assert (s.exaggeration, s.cfg_weight, s.fallback_voice, s.fallback_speed) == (0.9, 0.3, "am_puck", 1.2)  # flags win
    assert settings_for(tmp_path, "--voice-config", str(config), "--fallback", "none").fallback_voice is None
    assert settings_for(tmp_path, "--voice-config", str(config), "--engine", "mock").engine == "mock"
    assert vs.load_voice_config(config)["voice_prompt"] == str(tmp_path / "ref.wav")  # relative to the file
    for value, expected in [("none", None), (None, None), ("kokoro", {"voice": None, "speed": None}),
                            ("am_puck", {"voice": "am_puck", "speed": None}),
                            ({"engine": "kokoro", "voice": "am_puck", "speed": 1.1}, {"voice": "am_puck", "speed": 1.1})]:
        config.write_text(json.dumps({"fallback": value}))
        assert vs.load_voice_config(config)["fallback"] == expected
    for bad in [{"schema": "other.v2"}, {"engine": "piper"}, {"exaggeration": 5}, {"cfg_weight": "high"},
                {"fallback": "piper:x"}, {"fallback": {"engine": "chatterbox"}}, {"fallback": 3}]:
        config.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            vs.load_voice_config(config)
    config.write_text("[1]")
    with pytest.raises(ValueError):
        vs.load_voice_config(config)
    with pytest.raises(ValueError):
        vs.load_voice_config(tmp_path / "missing.json")


def test_command_line_checks(tmp_path, monkeypatch, capsys):
    token = tmp_path / "token"
    token.write_text("operator-credential-test\n")
    base = ["--token-file", str(token), "--streamer-dir", str(tmp_path / "streamer")]
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    for argv, message in [(["--host", "0.0.0.0"], "loopback"), (["--engine", "elevenlabs"], "ELEVENLABS_API_KEY"),
                          (["--voice-prompt", str(tmp_path / "nope.wav")], "not a file"),
                          (["--engine", "kokoro", "--voice", "Bad Voice"], "invalid voice"),
                          (["--voice-config", str(tmp_path / "missing.json")], "cannot read voice config")]:
        with pytest.raises(SystemExit):
            vs.main(base + argv)
        assert message in capsys.readouterr().err


# ---------------------------------------------------------------- HTTP

def test_http_contract(make_service, tmp_path):
    svc = make_service()

    async def body():
        http = TestClient(TestServer(vs.create_app(svc, TOKEN)))
        await http.start_server()
        try:
            health = await http.get("/healthz")
            assert health.status == 200 and (await health.json())["engine"] == "mock"
            for method, path in [("get", "/state"), ("post", "/speak"), ("post", "/stop")]:
                assert (await getattr(http, method)(path, json={})).status == 403
            assert (await http.get("/state", headers={"X-Admin-Token": "wrong-credential-x"})).status == 403
            text = "hello there"
            for payload in [{}, {"text": 5}, {"text": ""}, {"text": " ... "}, {"text": text, "priority": "urgent"},
                            {"text": text, "max_seconds": 0}, {"text": text, "max_seconds": True},
                            {"text": text, "max_seconds": "3"}, {"text": text, "tag": 5}, {"text": "x" * 2001}]:
                assert (await http.post("/speak", json=payload, headers=AUTH)).status == 400, payload
            assert (await http.post("/speak", data="not json", headers=AUTH)).status == 400
            reply = await http.post("/speak", json={"text": LONG, "priority": "normal", "max_seconds": 30, "tag": "t1"}, headers=AUTH)
            result = await reply.json()
            assert reply.status == 200 and result["queued"] is True and result["id"]
            assert result["estimated_seconds"] == pytest.approx(len(LONG) * FAST, abs=0.01)
            for _ in range(200):
                state = await (await http.get("/state", headers=AUTH)).json()
                if state["speaking"]:
                    break
                await asyncio.sleep(0.01)
            assert state["speaking"] and state["current"]["id"] == result["id"] and state["current"]["tag"] == "t1"
            assert {"speaking", "current", "queue", "engine", "voice"} <= set(state)
            for _ in range(4):
                await http.post("/speak", json={"text": "queued behind"}, headers=AUTH)
            full = await http.post("/speak", json={"text": "one too many"}, headers=AUTH)
            assert full.status == 429 and (await full.json())["queued"] is False
            stopped = await http.post("/stop", headers=AUTH)
            assert stopped.status == 200 and await stopped.json() == {"ok": True, "stopped": True, "dropped": 3}
            state = await (await http.get("/state", headers=AUTH)).json()
            assert state["speaking"] is False and state["current"] is None and state["queue"] == 0
            (tmp_path / "STOP").write_text("")
            blocked = await http.post("/speak", json={"text": "silenced"}, headers=AUTH)
            assert blocked.status == 503 and (await blocked.json())["reason"] == "kill_switch"
        finally:
            await http.close()

    asyncio.run(body())


# ---------------------------------------------------------------- FIFO sink

def read_fifo(path, seconds, out):
    """What ffmpeg does: block opening the FIFO, then read until the deadline."""
    fd = os.open(path, os.O_RDONLY)
    try:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            data = os.read(fd, 65536)
            if not data:
                break
            out.append((time.monotonic(), data))
    finally:
        os.close(fd)


def run_reader(path, seconds):
    out = []
    thread = threading.Thread(target=read_fifo, args=(path, seconds, out), daemon=True)
    thread.start()
    thread.join(seconds + 5)
    assert not thread.is_alive()
    return out


def test_fifo_carries_real_time_stereo_pcm(tmp_path):
    path = tmp_path / "voice.pcm"
    assert not path.exists()
    sink = vs.PcmSink(path)
    assert path.is_fifo()
    sink.start()
    try:
        out = []
        reader = threading.Thread(target=read_fifo, args=(path, 1.8, out), daemon=True)
        reader.start()
        time.sleep(0.4)
        pattern = np.full(int(0.25 * vs.OUT_RATE) * 2, 1000, dtype=np.int16)  # 0.25 s of stereo
        sink.push(pattern.tobytes())
        reader.join(8)
        assert not reader.is_alive()
    finally:
        sink.stop()
    first, last = out[0][0], out[-1][0]
    total = sum(len(data) for _, data in out)
    rate = (total - len(out[0][1])) / (last - first)
    assert BYTES_PER_SECOND * 0.95 < rate < BYTES_PER_SECOND * 1.05, rate  # 48 kHz x 2 channels x 2 bytes, real time
    samples = np.frombuffer(b"".join(data for _, data in out)[: total // 4 * 4], dtype=np.int16)
    loud = np.flatnonzero(samples)
    assert len(loud) == len(pattern) and loud[-1] - loud[0] + 1 == len(pattern)  # exactly the pushed audio, contiguous
    assert loud[0] % 2 == 0  # frame aligned
    assert sink.buffered_bytes() == 0 and sink.dropped_bytes == 0


def test_fifo_without_reader_does_not_block_and_reattaches(tmp_path):
    path = tmp_path / "voice.pcm"
    sink = vs.PcmSink(path)
    sink.start()
    try:
        started, blocks = time.monotonic(), sink.blocks
        sink.push(bytes(int(0.3 * BYTES_PER_SECOND)))
        until(lambda: sink.buffered_bytes() == 0, timeout=2, what="the buffer to drain with nobody reading")
        elapsed = time.monotonic() - started
        assert 0.2 < elapsed < 0.7  # played out at real-time pace although the FIFO has no reader
        assert sink.fifo_state() == "waiting"
        assert (sink.blocks - blocks) * vs.BLOCK_SECONDS == pytest.approx(elapsed, abs=0.15)
        for _ in range(2):  # a reader attaches, goes away, another attaches
            got = sum(len(data) for _, data in run_reader(path, 0.4))
            assert got > 0.2 * BYTES_PER_SECOND
            time.sleep(0.05)
    finally:
        sink.stop()


def test_a_fifo_is_created_over_a_regular_file(tmp_path):
    path = tmp_path / "voice.pcm"
    path.write_bytes(b"not a fifo")
    vs.PcmSink(path)
    assert path.is_fifo()


# ---------------------------------------------------------------- mouth signal (mouth.json)

def mouth(path):
    return json.loads((Path(path) / "mouth.json").read_text())


def stereo_block(level, blocks=1):
    """`blocks` 20 ms stereo s16le blocks at a constant sample value."""
    return np.full(vs.BLOCK_FRAMES * vs.OUT_CHANNELS * blocks, level, dtype=np.int16).tobytes()


class Pulsed(vs.MockEngine):
    """The mock tone switched on and off every `period` seconds: equal bursts and gaps."""

    def __init__(self, period=0.2, **options):
        super().__init__(**options)
        self.period = period

    def _tone(self, text):
        samples, rate = super()._tone(text)
        on = (np.floor(np.arange(len(samples)) / rate / self.period) % 2) == 0
        return (samples * on).astype(np.int16), rate


def test_block_rms():
    assert vs.block_rms(b"").size == 0
    levels = vs.block_rms(stereo_block(8000, 3) + stereo_block(0, 2) + stereo_block(400)[:100])
    assert levels.tolist() == pytest.approx([8000 / 32768] * 3 + [0.0, 0.0])  # the trailing partial block is ignored
    assert vs.block_rms(stereo_block(8000)[:400]).tolist() == pytest.approx([8000 / 32768])  # shorter than a block: one block


def test_mouth_envelope_follows_the_blocks_being_played(tmp_path):
    tracker = vs.MouthTracker(tmp_path / "mouth.json")
    loud, quiet, silent = stereo_block(8000), stereo_block(400), stereo_block(0)
    tracker.feed(loud)
    assert tracker.open == 0  # nothing is being spoken: blocks are ignored
    tracker.begin("u1")
    tracker.reference(stereo_block(8000, 10))
    assert tracker.level == pytest.approx(8000 / 32768)
    tracker.feed(loud)
    assert tracker.open == pytest.approx(1 - np.exp(-1), abs=1e-9)  # 20 ms attack: 63 % after one 20 ms block
    tracker.feed(loud)
    tracker.feed(loud)
    assert tracker.open > 0.9 and tracker.energy < tracker.open  # energy is the slower loudness
    peak = tracker.open
    tracker.feed(silent)
    assert tracker.open == pytest.approx(peak * np.exp(-0.25), abs=1e-9)  # 80 ms release: 22 % down per block
    for _ in range(30):
        tracker.feed(silent)
    assert tracker.open == 0  # closed exactly, not asymptotically
    tracker.feed(quiet)
    assert tracker.open == 0  # 5 % of the level: under the gate
    tracker.reference(stereo_block(16000, 10))  # a louder sentence raises the utterance level
    assert tracker.level == pytest.approx(16000 / 32768)
    for _ in range(12):
        tracker.feed(loud)
    assert tracker.open == pytest.approx((0.5 - vs.MOUTH_GATE) / (1 - vs.MOUTH_GATE), abs=0.01)  # half the level: 0.456
    snapshot = tracker.snapshot()
    assert snapshot["speaking"] is True and snapshot["id"] == "u1" and snapshot["schema"] == vs.MOUTH_SCHEMA
    started = time.perf_counter()
    for _ in range(1000):
        tracker.feed(loud)
    assert time.perf_counter() - started < 0.5  # cheap enough for the 20 ms clock thread (about 15 us a block)
    tracker.finish()
    assert tracker.open == 0 and tracker.speaking is False
    data = mouth(tmp_path)
    assert data == {"schema": vs.MOUTH_SCHEMA, "utc": data["utc"], "open": 0, "energy": 0, "speaking": False, "id": None}
    assert abs(data["utc"] - time.time()) < 1 and oct(os.stat(tmp_path / "mouth.json").st_mode & 0o777) == "0o600"
    tracker.begin("u2")
    tracker.reference(stereo_block(0, 10))  # a silent sentence: the floor keeps noise from opening the mouth
    assert tracker.level == vs.MOUTH_FLOOR
    tracker.feed(stereo_block(30))
    assert tracker.open == 0


def test_mouth_json_tracks_the_audio_being_played(make_service, tmp_path):
    svc = make_service(Pulsed(period=0.2, seconds_per_char=FAST))
    first = mouth(tmp_path)  # written at start: closed
    assert (first["open"], first["speaking"], first["id"]) == (0, False, None) and svc.state()["mouth"] == {"open": 0, "energy": 0}
    writes = svc.mouth.writes
    result = svc.submit("x" * 160, tag="pulse")  # 1.6 s: tone during 0-0.2, 0.4-0.6, ... and silence between
    until(lambda: speaking(tmp_path)["speaking"])
    started = speaking(tmp_path)["started_utc"]
    samples = []
    while not idle(svc):
        try:
            samples.append(mouth(tmp_path))
        except (OSError, ValueError):
            pass
        time.sleep(0.005)
    final = mouth(tmp_path)
    assert final["open"] == 0 and final["speaking"] is False and final["id"] is None
    live = [s for s in samples if s["speaking"]]
    assert len(live) > 20 and all(s["id"] == result["id"] and s["schema"] == vs.MOUTH_SCHEMA for s in live)
    phases = [((s["utc"] - started) % 0.4, s["open"]) for s in live]
    burst = [o for p, o in phases if 0.10 <= p <= 0.18]  # mid-burst: open
    gap = [o for p, o in phases if 0.36 <= p <= 0.40]  # end of the gap: released
    assert burst and gap and min(burst) > 0.6 and max(gap) < 0.35, (burst, gap)
    assert max(o for _, o in phases) > 0.9 and min(o for _, o in phases) < 0.15  # a 0.2 s gap releases to about e^-2.2
    assert all(0 <= s["energy"] <= 1 for s in live) and max(s["energy"] for s in live) > 0.5
    assert 1.6 * 25 * 0.6 < svc.mouth.writes - writes < 1.6 * 25 * 1.4 + 4  # about 25 writes per second while speaking
    assert svc.state()["mouth"] == {"open": 0, "energy": 0}


def test_mouth_closes_at_once_when_speech_is_cut(make_service, tmp_path):
    svc = make_service()
    svc.submit(LONG, tag="long")
    until(lambda: mouth(tmp_path)["open"] > 0.5, what="the mouth to open")
    assert svc.stop(wait=1.0)["stopped"] is True
    data = mouth(tmp_path)  # written by the cut itself, before /stop returns
    assert data["open"] == 0 and data["speaking"] is False and data["id"] is None
    svc.submit(LONG, tag="killed")
    until(lambda: mouth(tmp_path)["open"] > 0.5)
    (tmp_path / "STOP").write_text("")
    until(lambda: idle(svc), timeout=1.5, what="the kill file to cut speech")
    assert mouth(tmp_path)["open"] == 0 and mouth(tmp_path)["speaking"] is False
    (tmp_path / "STOP").unlink()
    cut = svc.submit(LONG, tag="cut")
    until(lambda: mouth(tmp_path)["id"] == cut["id"] and mouth(tmp_path)["open"] > 0.5)
    urgent = svc.submit("Urgent message now, said twice over.", "high", tag="urgent")
    until(lambda: mouth(tmp_path)["id"] == urgent["id"] and mouth(tmp_path)["open"] > 0.5, what="the urgent utterance to open the mouth")
    until(lambda: idle(svc) and len(timeline(tmp_path)) == 4)
    assert [e["cut"] for e in timeline(tmp_path)] == [True, True, True, False]
    assert mouth(tmp_path)["open"] == 0 and svc.state()["mouth"]["open"] == 0
