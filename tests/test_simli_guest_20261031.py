"""Simli live stack (owner 10-31): the guest driver, the voice server's per-speaker routing, the stage's guest mode."""
import asyncio
import json
import sys
import time
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import guest_driver as G  # noqa: E402
import voice_server as V  # noqa: E402


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make_guest(tmp_path, replies=("Yo SUB-01, happy Halloween!",), speaking=False):
    calls = []
    sdir = tmp_path / "streamer"
    (sdir / "speech").mkdir(parents=True)
    cfg = types.SimpleNamespace(streamer_dir=str(sdir), voice="kimchi", voice_url="http://v", agent_url="http://a",
                                token="tok", key_file="k", model="m")
    replies = list(replies)

    def call(method, url, body=None, headers=None, timeout=10.0):
        calls.append((method, url, body))
        if url.endswith("/state"):
            return {"speaking": speaking, "queue": 0}
        return {"ok": True}

    clock = Clock()
    g = G.Guest(cfg, llm=lambda system, user: replies.pop(0) if replies else "", call=call, clock=clock)
    return g, calls, clock, sdir


def say(sdir, text, tag=""):
    with open(sdir / "speech" / "timeline.jsonl", "a") as f:
        f.write(json.dumps({"id": "x", "tag": tag, "text": text}) + "\n")


def test_guest_silent_while_switch_off(tmp_path):
    g, calls, clock, sdir = make_guest(tmp_path)
    assert g.step() is None and calls == []


def test_guest_hello_then_replies_to_sub01_and_feeds_the_agent(tmp_path):
    g, calls, clock, sdir = make_guest(tmp_path, replies=["Yo SUB-01, happy Halloween chat!", "Bro that costume is wild."])
    say(sdir, "old line from before the show")
    (sdir / "guest-on").touch()
    assert g.step() == "Yo SUB-01, happy Halloween chat!"     # the hello; the timeline offset starts at the end
    speak = [c for c in calls if c[1].endswith("/speak")][-1]
    assert speak[2]["tag"] == "guest:kimchi"
    chat = [c for c in calls if c[1].endswith("/chat")][-1]
    assert chat[2]["nick"] == "Kimchi" and "your guest on stream" in chat[2]["text"]
    clock.t += 5
    say(sdir, "Kimchi, what are you dressed as?")
    assert g.step() is None                          # the gap since his last line
    clock.t += 20
    assert g.step() == "Bro that costume is wild."
    assert ("SUB-01", "Kimchi, what are you dressed as?") in g.history
    assert all("old line" not in t for _, t in g.history)


def test_guest_waits_while_voice_speaks_and_ignores_own_lines(tmp_path):
    g, calls, clock, sdir = make_guest(tmp_path, speaking=True)
    (sdir / "guest-on").touch()
    g.step()
    assert g.step() is None and not any(c[1].endswith("/speak") for c in calls)
    say(sdir, "my own line", tag="guest:kimchi")
    g.poll_timeline()
    assert all(t != "my own line" for _, t in g.history)


def test_guest_stop_file_and_hourly_cap(tmp_path):
    g, calls, clock, sdir = make_guest(tmp_path, replies=["hi"] * 200)
    (sdir / "guest-on").touch()
    (sdir / "STOP").touch()
    assert g.step() is None
    (sdir / "STOP").unlink()
    spoken = 0
    for _ in range(int(3500 // (G.GAP_S + 1))):       # a line is allowed every ~15 s for most of an hour
        clock.t += G.GAP_S + 1
        say(sdir, "SUB-01 keeps talking")
        spoken += g.step() is not None
    assert G.LINES_PER_HOUR - 5 <= spoken <= G.LINES_PER_HOUR


def test_clean_line_trims_words_and_marks():
    assert G.clean_line('"*grins* yo"') == "grins yo"
    assert len(G.clean_line("word " * 80).split()) == G.MAX_WORDS


def test_sink_routes_speaker_to_tap():
    sink = V.PcmSink(None)
    got = []
    sink.on_tap = lambda block, who: got.append(who)
    block = (np.ones(V.BLOCK_FRAMES * 2) * 500).astype("<i2").tobytes()
    sink.push(block, "kimchi")
    sink.push(block)
    sink.start()
    time.sleep(0.12)
    sink.stop()
    assert got[0] == "kimchi" and got[1] is None


def test_tap_flushes_on_speaker_change():
    tap = V.SimliTap.__new__(V.SimliTap)
    tap.chunk_blocks, tap._buf, tap._who = 5, [], None
    tap._queue, tap._event = __import__("collections").deque(), types.SimpleNamespace(set=lambda: None)
    b = bytes(V.BLOCK_FRAMES * 4)
    tap.feed(b, None)
    tap.feed(b, "kimchi")
    assert [w for w, _ in tap._queue] == [None]
    assert tap._who == "kimchi" and len(tap._buf) == 1


def test_guest_lines_use_the_guest_voice(tmp_path):
    class Eng(V.Engine):
        name, voice = "remote", "sub01"

        def __init__(self):
            self.seen = []

        def synthesize(self, text):
            self.seen.append(("sub01", text))
            return np.zeros(2400, dtype=np.int16), 24000

        def synthesize_as(self, text, voice):
            self.seen.append((voice, text))
            return np.zeros(2400, dtype=np.int16), 24000

    eng = Eng()
    svc = V.VoiceService(eng, V.PcmSink(None), tmp_path)
    svc._synth("hello", "kimchi")
    svc._synth("hi", None)
    assert eng.seen == [("kimchi", "hello"), ("sub01", "hi")]


def test_stage_guest_config_and_face_byte(tmp_path):
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer
    import simli_stage as S

    (tmp_path / "key").write_text("k")
    (tmp_path / "guest-face").write_text("03cb4fc7-90f7-437c-9027-ba8cbf2c475d")
    args = S.argparse.Namespace(key_file=str(tmp_path / "key"), face_id="40e54165-998f-405b-b8b3-e8f092429c31",
                                face_image=None, bg_image=None, guest_image=None, session_s=60, idle_s=60,
                                guest_switch=str(tmp_path / "guest-on"), guest_face_file=str(tmp_path / "guest-face"),
                                guest_voice="kimchi", guest_name="KIMCHI", frame="halloween")

    async def run():
        client = TestClient(TestServer(S.create_app(args)))
        await client.start_server()
        try:
            assert (await (await client.get("/config")).json())["guest"] is False
            (tmp_path / "guest-on").touch()
            assert (await (await client.get("/config")).json())["guest_name"] == "KIMCHI"
            ws = await client.ws_connect("/ws")
            await client.post("/pcm?face=kimchi", data=b"\x01\x00" * 4)
            assert (await ws.receive_bytes())[0] == 1
            await client.post("/pcm", data=b"\x01\x00" * 4)
            assert (await ws.receive_bytes())[0] == 0
            await ws.close()
        finally:
            await client.close()

    asyncio.run(run())
