"""Owner decision 2026-10-13: the eye is open only while he sleeps (NREM: eyes closed, REM: the dream) or while he
is outside (what he sees on the way). Awake at home: no frame and no paid call. Every provider is mocked."""
import asyncio
import json
from types import SimpleNamespace

import pytest

import eye as E
import live_server
from test_costs import Calls, mocked_eye


@pytest.mark.parametrize("stage,presence,privacy,mode", [
    ("AWAKE", "home", False, "off"), ("NREM", "home", False, "closed"), ("REM", "home", False, "dream"),
    ("AWAKE", "leaving", False, "outside"), ("AWAKE", "away", False, "outside"), ("AWAKE", "returning", False, "outside"),
    ("REM", "home", True, "off"), ("AWAKE", "away", True, "off")])
def test_eye_mode_table(stage, presence, privacy, mode):
    assert E.eye_mode(stage, presence, privacy) == mode
    assert mode in E.EYE_MODES


def test_life_presence_and_outside_view_come_from_real_life_state():
    assert E.life_presence({"place": "desk", "geo": None}) == "home"
    assert E.life_presence({"place": "street_bakery"}) == "away"
    assert E.life_presence({"place": "door_out", "geo": {"lat": 35.7}}) == "away"
    v = E.outside_view({"place": "street_home", "walking": True, "path_to": "counter", "doing": "buying bread",
                        "geo": {"route": "home-bakery"}})
    assert v == {"where": "Kichijoji, Tokyo", "walking": True, "doing": "buying bread",
                 "toward": "the bakery counter", "route": "home-bakery"}
    v = E.outside_view({"place": "bench", "walking": False, "doing": "sitting on the park bench"})
    assert v["at"] == "the park bench" and "route" not in v
    assert "toward" not in E.outside_view({"place": "somewhere-unknown", "walking": True, "path_to": "nowhere"})


def make_live(tmp_path, monkeypatch, stage, presence="home", privacy=False, life=None):
    calls = Calls()
    live = live_server.Live("m", True, data_dir=tmp_path)
    live.sent = []

    async def broadcast(msg):
        live.sent.append(msg)
    live.broadcast = broadcast
    live.eye = mocked_eye(tmp_path, monkeypatch, calls)
    live.eye.ledger = live.ledger
    live.eye_every = 0.01
    live.diary = None
    live.clients.add(object())                                   # someone is watching
    live.engine.stage = stage
    live.home = SimpleNamespace(interactions=SimpleNamespace(presence=presence), privacy=lambda: privacy)
    snap = dict(live.life.snapshot(), **(life or {}))
    live.life.snapshot = lambda: snap
    return live, calls


def run_eye(live, seconds=0.3):
    async def run():
        task = asyncio.create_task(live.run_eye())
        await asyncio.sleep(seconds)
        task.cancel()
    asyncio.run(run())


def test_awake_at_home_spends_nothing_and_says_off(tmp_path, monkeypatch):
    live, calls = make_live(tmp_path, monkeypatch, "AWAKE")
    steps = []
    monkeypatch.setattr(live.eye, "step", lambda *a, **k: steps.append(a) or {})
    run_eye(live)
    assert steps == [] and calls.n == 0 and not live.ledger.path.exists()
    assert not list((tmp_path / "frames").glob("*.jpg"))
    assert [m["type"] for m in live.sent] == ["eye_state"] and live.sent[0]["mode"] == "off"
    assert live.sent[0]["since"] > 0
    assert live.eye_hello() == [live.eye_state()]               # a new viewer gets no frame either
    live.last_frame = {"t": "12:00", "stage": "AWAKE", "img": "/eye/1.jpg", "thought": ""}
    assert [m["type"] for m in live.eye_hello()] == ["eye_state"]


def test_bathroom_privacy_turns_the_eye_off(tmp_path, monkeypatch):
    live, calls = make_live(tmp_path, monkeypatch, "AWAKE", presence="away", privacy=True)
    run_eye(live)
    assert calls.n == 0 and live.sent[0]["mode"] == "off"


def test_rem_dream_frames_are_made_and_labelled(tmp_path, monkeypatch):
    live, calls = make_live(tmp_path, monkeypatch, "REM")
    run_eye(live)
    assert calls.n >= 2                                          # thought + image, mocked
    assert live.sent[0] == {"type": "eye_state", "mode": "dream", "since": live.sent[0]["since"]}
    frames = [m for m in live.sent if m["type"] == "eye"]
    assert frames and all(f["mode"] == "dream" and f["stage"] == "REM" for f in frames)
    assert live.eye_hello()[0]["mode"] == "dream" and live.eye_hello()[1]["type"] == "eye"


def test_nrem_is_closed_eyes(tmp_path, monkeypatch):
    live, calls = make_live(tmp_path, monkeypatch, "NREM")
    run_eye(live)
    assert live.sent[0]["mode"] == "closed"
    assert all(f["mode"] == "closed" for f in live.sent if f["type"] == "eye")


def test_outside_frames_follow_the_real_destination(tmp_path, monkeypatch):
    live, calls = make_live(tmp_path, monkeypatch, "AWAKE", presence="away",
                            life={"place": "street_home", "walking": True, "path_to": "bench",
                                  "doing": "sitting on the park bench", "geo": {"route": "home-park"}})
    asked, prompts = [], []
    real_post = E.replicate_post

    def spy_post(url, token, payload, **kw):
        asked.append(json.loads(payload["input"]["prompt"]))
        return real_post(url, token, payload, **kw)
    monkeypatch.setattr(E, "replicate_post", spy_post)
    real_gen = E.ReplicateImages.generate

    def spy_gen(self, prompt, seed, w, h):
        prompts.append(prompt)
        return real_gen(self, prompt, seed, w, h)
    monkeypatch.setattr(E.ReplicateImages, "generate", spy_gen)
    run_eye(live)
    assert live.sent[0]["mode"] == "outside"
    assert asked and asked[0]["outside"]["toward"] == "the park bench" and asked[0]["outside"]["route"] == "home-park"
    assert "home" not in asked[0]                               # not the apartment: the street he is on
    assert prompts and E.STYLE["OUTSIDE"] in prompts[0]
    frames = [m for m in live.sent if m["type"] == "eye"]
    assert frames and frames[0]["mode"] == "outside" and frames[0]["why"]["outside"]["toward"] == "the park bench"


def test_outside_respects_the_daily_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("SUB01_CAP_EYE_USD", "0")
    live, calls = make_live(tmp_path, monkeypatch, "AWAKE", presence="leaving")
    run_eye(live)
    assert calls.n == 0 and live.eye_resting and "eye" in live.eye_resting


def test_waking_up_stops_the_eye_and_says_so(tmp_path, monkeypatch):
    live, calls = make_live(tmp_path, monkeypatch, "REM")

    async def run():
        task = asyncio.create_task(live.run_eye())
        await asyncio.sleep(0.2)
        live.engine.stage = "AWAKE"
        n = calls.n
        await asyncio.sleep(0.3)
        task.cancel()
        return n
    n = asyncio.run(run())
    assert calls.n == n                                          # no paid call after he woke at home
    assert [m["mode"] for m in live.sent if m["type"] == "eye_state"] == ["dream", "off"]


def test_eye_only_token_is_used_by_the_eye(monkeypatch):
    monkeypatch.delenv("REPLICATE_API_TOKEN", raising=False)
    monkeypatch.setenv(E.EYE_TOKEN_ENV, "eye-only")
    assert E.replicate_token() == "eye-only"
    monkeypatch.delenv(E.EYE_TOKEN_ENV)
    assert E.replicate_token() == ""
