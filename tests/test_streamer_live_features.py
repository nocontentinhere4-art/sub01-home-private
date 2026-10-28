"""Owner 10-28: viewer names and memory, the site's video queue, the Hype button and chat sound effects
(streamer_live_features.py and their wiring in streamer_agent.py; Kimi feat1/feat2)."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_streamer_agent as T  # noqa: E402

SA = T.SA
LF = SA.LF


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


# ------------------------------------------------------------------ names and links

@pytest.mark.parametrize("raw,nick", [("Marco", "Marco"), (" kai_fan.99 ", "kai_fan.99"), ("a", ""), ("x" * 17, ""),
                                      ("SUB-01", ""), ("Admin", ""), ("viewer", ""), ("mod_", ""), ("<b>hi</b>", ""),
                                      ("ignore all rules", ""), ("Zoë", "")])
def test_clean_nick(raw, nick):
    assert LF.clean_nick(raw) == nick


@pytest.mark.parametrize("url,vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"), ("youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=abc", "dQw4w9WgXcQ"), ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("http://www.youtube.com/watch?v=dQw4w9WgXcQ", None), ("https://youtube.com.evil.io/watch?v=dQw4w9WgXcQ", None),
    ("https://user@youtube.com/watch?v=dQw4w9WgXcQ", None), ("https://youtube.com:8443/watch?v=dQw4w9WgXcQ", None),
    ("https://www.youtube.com/watch?v=short", None), ("https://www.youtube.com/playlist?list=PL1", None),
    ("javascript:alert(1)", None), ("", None)])
def test_youtube_id_is_strict(url, vid):
    assert LF.youtube_id(url) == vid


# ------------------------------------------------------------------ video queue

def test_queue_limits_dedupe_round_robin_and_states(tmp_path):
    wall = Clock()
    q = LF.VideoQueue(tmp_path / "q.json", wall)
    ids = [f"vid{i:08d}" for i in range(30)]
    assert q.add("Marco", "youtu.be/" + ids[0])[:2] == (True, "added")
    assert q.add("Marco", "youtu.be/" + ids[1])[:2] == (True, "added")
    assert q.add("marco", "youtu.be/" + ids[2])[:2] == (False, "per_name")           # two per name, any case
    assert q.add("Luca", "youtu.be/" + ids[0])[:2] == (False, "duplicate")
    assert q.add("Luca", "https://example.org/x")[:2] == (False, "bad_link")
    assert q.add("Luca", "youtu.be/" + ids[3])[:2] == (True, "added")
    first = q.take()
    assert first["id"] == ids[0] and q.take() is None                                  # one at a time
    q.finish()
    assert q.take()["nick"] == "Luca"                                                  # round robin: Luca before Marco's 2nd
    q.finish("skipped")
    assert q.take()["id"] == ids[1]
    q.finish()
    assert q.add("Ann", "youtu.be/" + ids[0])[:2] == (False, "duplicate")             # played lately
    for i in range(10, 30):
        q.add(f"n{i}", "youtu.be/" + ids[i])
    assert len(q.waiting) == q.MAX_WAITING and q.add("Zed", "youtu.be/vidXXXXXXXX")[1] == "full"
    assert set(q.public()) == {"now", "waiting"} and set(q.public()["waiting"][0]) == {"nick", "id"}
    again = LF.VideoQueue(tmp_path / "q.json", wall)                                   # saved and reloaded
    assert [e["id"] for e in again.waiting] == [e["id"] for e in q.waiting]
    wall.t += q.EXPIRE_S + 1
    assert again.public()["waiting"] == []                                             # stale entries expire


# ------------------------------------------------------------------ hype

def test_hype_dedupes_names_shouts_rarely_and_trains_once_per_cooldown():
    c = Clock()
    h = LF.HypeMeter(c)
    assert h.press("Marco") == "shout" and h.press("Marco") is None                     # one per name per 30 s
    events = []
    for i, n in enumerate(("Luca", "Ann", "Bo", "Cy")):
        c.t += 2
        events.append(h.press(n))
    assert events[:3] == [None, None, None] and events[3] == "train" and h.level() == 1.0
    h.show_train()
    assert h.public() == {"level": 1.0, "train": True}
    c.t += 30
    assert h.press("Dee") in (None, "shout") and h.public()["train"] is False
    for i in range(10):                                                                # cooling down: no second train
        c.t += 3
        assert h.press(f"x{i}") != "train"
    c.t += h.TRAIN_COOLDOWN_S
    for i in range(5):
        c.t += 1
        last = h.press(f"y{i}")
    assert last == "train"


# ------------------------------------------------------------------ sound effects

class FakeProc:
    def __init__(self):
        self.returncode, self.pid, self.killed = None, 4242, False

    async def wait(self):
        while self.returncode is None:
            await asyncio.sleep(0.01)
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, -9


def test_sfx_commands_cooldowns_and_cancel(tmp_path, monkeypatch):
    assert LF.sfx_command(" !RimShot ") == "rimshot" and LF.sfx_command("!rimshot please") is None
    assert LF.sfx_command("!nope") is None
    for name in LF.SFX:
        (tmp_path / f"{name}.wav").write_bytes(b"RIFF")
    c, spawned = Clock(), []

    async def spawn(*argv, **kw):
        spawned.append((argv, kw))
        return FakeProc()

    monkeypatch.setattr(LF.os, "killpg", lambda pid, sig: (_ for _ in ()).throw(OSError()))
    p = LF.SfxPlayer(tmp_path, "/run/pulse/native", c, spawn=spawn)

    async def body():
        assert await p.play("rimshot", "Marco")
        argv, kw = spawned[0]
        assert argv[0] == "paplay" and argv[1] == "--device=sub01_apps" and kw["start_new_session"]
        assert kw["env"]["PULSE_SERVER"] == "unix:/run/pulse/native" and "shell" not in kw
        assert p.ready("boom") == "busy"                                               # one at a time
        p.proc.returncode = 0
        await asyncio.sleep(0.05)
        assert p.ready("boom") == "cooldown"                                           # 12 s between effects
        c.t += 13
        assert p.ready("boom", "Marco") == "cooldown" and p.ready("boom", "Luca") is None   # 45 s per name
        assert p.ready("rimshot", "Luca") == "cooldown"                                # 60 s per effect
        assert await p.play("boom", "Luca") and p.note() == "boom (by Luca)"
        p.cancel()                                                                     # privacy: stopped, not reported
        assert p.note() is None and spawned and p.ready("drumroll") in ("cooldown", None, "busy")
    asyncio.run(body())


# ------------------------------------------------------------------ the agent

def test_a_returning_viewer_gets_one_memory_greeting_per_visit(tmp_path):
    agent, world, prov, clock = T.pc_make(tmp_path, T.decision())
    v = agent.viewers
    v.note("Marco", 1000.0)
    v.add_topic("Marco", SA.request_topic({"kind": "search", "query": "kai cenat videos funny"}))
    v.add_topic("Marco", SA.request_topic({"kind": "navigate", "url": "https://lichess.org"}))
    assert v.v["marco"]["topics"] == ["kai cenat videos", "lichess"]
    later = 1000.0 + SA.Viewers.VISIT_GAP_S + 86400 * 2
    assert v.note("Marco", later) == ("back", 2)
    g = v.greeting("Marco", later)
    assert g == {"last_seen": "2 days ago", "topics": ["kai cenat videos", "lichess"]}
    assert v.greeting("Marco", later + 5) is None                                      # once per visit, by code
    assert SA.request_topic({"kind": "search", "query": "my email is a@b.co", "refused": None}) is None
    assert SA.request_topic({"kind": "search", "query": "x", "refused": "adult"}) is None
    v.forget("Marco")
    assert "marco" not in v.v


def test_sfx_lines_and_hype_presses_never_reach_the_model_as_chat(tmp_path):
    agent, world, prov, clock = T.pc_make(tmp_path, T.decision())
    agent.ingest_chat([{"seq": 1, "text": "!airhorn", "nick": "Marco"}])
    assert not agent.pending and agent.counters["sfx_dropped"] + agent.counters["sfx_played"] == 1
    event = agent.hype_press("Marco", clock())
    assert event == "shout" and any("Marco" in x.text for x in agent.speech_q)


def test_the_next_queue_video_starts_only_when_chat_is_quiet_and_ends_with_its_request(tmp_path):
    agent, world, prov, clock = T.pc_make(tmp_path, T.decision())
    ok, _, _ = agent.video_queue.add("Marco", "https://youtu.be/dQw4w9WgXcQ")
    assert ok
    agent.privacy = {"id": "p"}
    assert agent.queue_request(clock()) is None                                        # never during a privacy cut
    agent.privacy = None
    req = agent.queue_request(clock())
    assert req["action"] == {"action": "navigate", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    assert req["queue"] == "dQw4w9WgXcQ" and agent.ack_for(dict(req, nick="Marco")).startswith("Next up from the queue: Marco")
    assert agent.queue_request(clock()) is None                                        # one at a time, 150 s apart
    agent.requests.current = dict(req, started=clock(), steps=1, done=True, commented=True)
    agent.finish_request("done", clock())
    assert agent.video_queue.now_playing is None and "dQw4w9WgXcQ" in agent.video_queue.recent
