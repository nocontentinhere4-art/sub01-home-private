"""The chat pipeline: every accepted message gets one in-character reaction at once, and an action asked for is carried
out at once, waits for the end of a walk or for the morning, or is dropped with an honest line when it is impossible now
(life.why_not). handle_chat -> life.request_impulse -> life.update, with the real Live object.

    python -m pytest tests/test_chat_pipeline.py -q
No network, no AI calls (the mind is a fake when it is on) and no Vagon call (the bridge is a fake).
"""
import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import life as L
import live_server
import mind as M
from impulse import REACTIONS
from sleep import TZ


def run(coro):
    return asyncio.run(coro)


def at(h, m=0, day=2):
    """A Tokyo time on 2026-10-02 (a Friday; day=3 is the Saturday)."""
    return datetime(2026, 10, day, h, m, tzinfo=TZ).timestamp()


class Fake:
    name = "fake"
    model = "claude-haiku-4-5"

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def ask(self, system, user):
        self.calls.append((system, user))
        a = self.answers.pop(0) if self.answers else ""
        return (a if isinstance(a, str) else json.dumps(a)), 800, 100


class WS:
    def __init__(self):
        self.sent = []

    async def send_json(self, d):
        self.sent.append(d)


def make_live(tmp_path, hour=10, minute=0):
    start = datetime(2026, 10, 2, hour, minute, tzinfo=TZ).timestamp()
    live = live_server.Live("m", True, time_scale=1.000001, data_dir=tmp_path, start=start)   # 1.0 ignores start
    live.sent = []

    async def broadcast(msg):
        live.sent.append(msg)
    live.broadcast = broadcast
    return live


def settle(life, act, t):
    """He is at `act` in its place, with time left on it (a fresh Life is on its way from the bed to the window)."""
    life.start(act, t, "test")
    life.place = L.ACTIVITIES[act][0]
    life.x, life.z = L.PLACES[life.place]
    life.path, life.dur, life.until, life.trip = [], None, t + 3600, None


def fed(life):
    """A body just fed: no hunger interruption gets in the way of what the tests look at."""
    life.body.ghrelin, life.body.glucose, life.body.since_meal_h = 0.1, 110.0, 0.5


def chat(live, key, text, nick=""):
    """One message on its own socket; returns its ack."""
    ws = WS()
    run(live.handle_chat(ws, key, text, nick))
    return ws.sent[-1]


def reactions(live):
    return [m for m in live.sent if m["type"] == "reaction"]


def tick(life, t, stage="AWAKE"):
    life.update(t, 1.0, 1.0, stage, {}, 0.0, 0.0)


# --- the reaction ----------------------------------------------------------------------------------------------------
def test_every_accepted_message_gets_a_reaction_without_the_mind_or_the_spiking_net(tmp_path, monkeypatch):
    live = make_live(tmp_path)
    assert live.mind is None and live.spiking is None
    t = live.clock.now()
    settle(live.life, "window", t)
    ack = chat(live, "1.1.1.1", "want to play chess", "mika")
    assert ack["ok"] and not ack["queued"] and ack["impulse"] == "activity" and ack["reaction"] == REACTIONS["play_chess"]
    assert live.sent[-2]["type"] == "chat"                                 # the message goes out, then the reaction
    assert reactions(live)[-1] == {"type": "reaction", "text": REACTIONS["play_chess"], "nick": "mika", "t": ack["t"]}
    ack = chat(live, "1.1.1.2", "what is your favourite colour")
    assert ack["impulse"] == "reply_only" and ack["reaction"] == "Not doing that one. Ask me something else."
    assert reactions(live)[-1]["text"] == ack["reaction"] and reactions(live)[-1]["nick"] == ""
    # a link: the bridge is off, so a bare domain passes the filter and is answered honestly (a full link is refused)
    ack = chat(live, "1.1.1.3", "open formo.family")
    assert ack["ok"] and ack["impulse"] == "open_url" and ack["reaction"] == "I cannot open links yet."
    # the bridge on: the link goes to the PC with the canned line; a busy PC says so
    opened = []
    monkeypatch.setattr(live_server, "vagon_enabled", lambda: True)
    monkeypatch.setattr(live_server, "vagon_open_url_async", lambda url: opened.append(url) or True)
    ack = chat(live, "1.1.1.4", "look at https://example.com/a?b=1 please")
    assert ack["impulse"] == "open_url" and ack["reaction"] == "On it, let me open that."
    assert opened == ["https://example.com/a?b=1"]
    monkeypatch.setattr(live_server, "vagon_open_url_async", lambda url: False)
    assert chat(live, "1.1.1.5", "and https://example.com/two")["reaction"].startswith("The PC is busy")
    # a nickname the filter refuses is not shown with the reaction
    chat(live, "1.1.1.6", "check tiktok", "you idiot")
    assert reactions(live)[-1]["nick"] == ""
    assert len(reactions(live)) == 6 and all(0 < len(m["text"]) <= 60 for m in reactions(live))


def test_a_refused_message_gets_no_reaction_and_changes_nothing(tmp_path):
    live = make_live(tmp_path)
    life = live.life
    settle(life, "window", live.clock.now())
    ws = WS()
    run(live.handle_chat(ws, "7.7.7.7", "want to play chess"))
    assert ws.sent[-1]["ok"] and life.impulse[0] == "play_chess"
    n = len(live.sent)
    run(live.handle_chat(ws, "7.7.7.7", "put on some music"))              # the same viewer within RATE_S
    assert ws.sent[-1] == {"type": "chat_ack", "ok": False, "reason": "one message every 10 s"}
    for key, text in (("7.7.7.8", "https://example.com/x"), ("7.7.7.9", "you idiot, play chess"),
                      ("7.7.7.10", "want to play chess")):                 # a link (bridge off), an insult, a duplicate
        run(live.handle_chat(ws, key, text))
        assert not ws.sent[-1]["ok"] and "reaction" not in ws.sent[-1]
    assert len(live.sent) == n and life.impulse[0] == "play_chess"         # nothing shown, nothing heard


# --- the impulse -----------------------------------------------------------------------------------------------------
def test_a_request_is_carried_out_at_once_when_he_is_awake_at_home(tmp_path):
    live = make_live(tmp_path)
    t, life = live.clock.now(), live.life
    settle(life, "window", t)
    chat(live, "2.2.2.2", "want to play chess")
    assert life.impulse[:2] == ("play_chess", "asked in chat: play_chess") and abs(life.impulse[2] - t) < 5
    tick(life, t + 1)
    assert life.activity == "play_chess" and life.impulse is None and life.started[-1] == (t + 1, "play_chess")
    assert life.say == "asked in chat: play_chess" and life.log[-1] == {"t": t + 1, "what": "asked in chat: play_chess"}
    assert life.path and life.path[-1] == "desk"                           # from the window to the desk
    # only the latest request is kept
    settle(life, "window", t + 10)
    chat(live, "2.2.2.3", "put on some music")
    chat(live, "2.2.2.4", "check tiktok")
    assert life.impulse[0] == "phone"
    tick(life, t + 11)
    assert life.activity == "phone" and life.path[-1] == "bed"
    # asked for what he is doing (or on his way to): nothing restarts, and he says so
    ack = chat(live, "2.2.2.5", "check your phone")
    assert ack["reaction"] == L.ALREADY_LINE == "I am already on it." and life.impulse is None


def test_a_request_on_the_way_runs_on_arrival(tmp_path):
    live = make_live(tmp_path)
    t, life = live.clock.now(), live.life
    fed(life)
    settle(life, "window", t)
    life.start("park", t, "test")
    assert life.path and life.trip == "home-park"
    ack = chat(live, "3.3.3.3", "want to play chess")
    assert ack["reaction"] == REACTIONS["play_chess"] and life.impulse[0] == "play_chess"
    t1 = t
    while life.path:
        t1 += 1.0
        tick(life, t1)
        assert life.activity == "park" and life.impulse is not None       # the walk is not interrupted
        assert t1 - t < 3600
    assert life.place == "bench"
    tick(life, t1 + 1)
    assert life.activity == "play_chess" and life.impulse is None and life.path[-1] == "desk"
    assert life.log[-1]["what"] == "asked in chat: play_chess"


def test_an_impossible_request_is_dropped_with_an_honest_line(tmp_path):
    live = make_live(tmp_path, hour=21)
    t, life = live.clock.now(), live.life
    fed(life)
    settle(life, "window", t)
    cases = [("go to the bakery", "The bakery is closed at this hour."), ("take a walk", "The park is closed at this hour."),
             ("eat something", "There is nothing to eat at home."), ("put on the TV", "There is no TV in this room."),
             ("open the laptop", "The Linux computer is not set up here."),
             ("use the bathroom", "There is no bathroom in this room."),
             ("please reply to me", "No reply is possible right now.")]
    for k, (text, line) in enumerate(cases):
        ack = chat(live, f"4.4.4.{k}", text)
        assert ack["ok"] and ack["impulse"] == "activity" and ack["reaction"] == line, text
        assert reactions(live)[-1]["text"] == line and life.impulse is None
    life.last_order = t - 60
    assert chat(live, "4.4.5.1", "order a pizza")["reaction"] == "The last order was not long ago."
    life.last_order = -1e18
    life.delivery = {"ordered": t, "leaves": t + 600, "arrives": t + 1200, "dish": "ramen"}
    assert chat(live, "4.4.5.2", "order some sushi")["reaction"] == "An order is already on its way."
    assert chat(live, "4.4.5.3", "get something at the konbini")["reaction"] == "A delivery is on its way; staying in."
    life.delivery = None
    life.last_chess = t - 3600
    assert chat(live, "4.4.5.4", "want to play chess")["reaction"] == "There was a chess game today already."
    life.can_watch = False
    assert chat(live, "4.4.5.5", "show me a youtube clip")["reaction"] == "There is nothing to watch right now."
    tick(life, t + 1)
    assert life.activity == "window" and not any("asked in chat" in e["what"] for e in life.log)
    assert all(len(m["text"]) <= 60 for m in reactions(live))


def test_why_not_follows_the_hard_rules_of_scores():
    lf = L.Life(rng=random.Random(0))
    for act in ("research", "window", "watch_video"):
        assert lf.why_not(act, at(3)) == "Not in the middle of the night." and lf.why_not(act, at(6, 5)) is None
    lf.chat_waiting = 1
    assert lf.why_not("research", at(3)) is None and lf.why_not("chat", at(3)) is None   # messages waiting: the desk is open
    lf.chat_waiting = 0
    assert lf.why_not("play_chess", at(7, 30)) == "No chess at this hour." and lf.why_not("play_chess", at(8)) is None
    assert lf.why_not("order_food", at(9, 30)) == "The kitchens are closed at this hour."
    assert lf.why_not("order_food", at(23, 20)) is None
    lf.food = 1
    assert lf.why_not("order_food", at(12)) == "There is a meal waiting here already." and lf.why_not("eat", at(12)) is None
    lf.food = 0
    assert lf.why_not("buy_bread", at(19, 50)) is None                     # he gets there before eight
    assert lf.why_not("buy_bread", at(19, 59)) == "The bakery is closed at this hour."
    assert lf.why_not("park", at(7, 30)) == "The park is closed at this hour." and lf.why_not("park", at(7, 30, day=3)) is None
    assert lf.why_not("buy_konbini", at(3)) is None                        # 24 h
    assert all(lf.why_not(act, at(h)) is None for act in ("phone", "listen_music") for h in (3, 12, 23))
    lf.home_enabled = True
    assert lf.why_not("play_console", at(12)) is None and lf.why_not("play_console", at(3)) == "Not in the middle of the night."
    assert lf.why_not("use_bathroom", at(3)) is None
    # what why_not refuses, scores() gives no weight to (the same rules); and every line fits the chat
    lines = {L.ASLEEP_LINE, L.ALREADY_LINE}
    for h in (3, 7, 12, 19, 21, 23):
        s = lf.scores(at(h), {}, 0.0, 0.0)
        for act in L.ACTIVITIES:
            why = lf.why_not(act, at(h))
            if why:
                lines.add(why)
                assert s.get(act, 0.0) == 0.0, (h, act, why)
    assert len(lines) >= 8 and all(0 < len(x) <= 60 for x in lines)


def test_a_request_while_asleep_waits_for_the_morning_if_still_sensible(tmp_path):
    live = make_live(tmp_path, hour=6, minute=30)
    t, life = live.clock.now(), live.life
    fed(life)
    settle(life, "sleep", t)
    tick(life, t, "NREM")
    assert life.stage == "NREM" and life.activity == "sleep" and life.place == "bed"
    assert chat(live, "5.5.5.4", "take a walk")["reaction"] == "The park is closed at this hour."   # closed beats asleep
    ack = chat(live, "5.5.5.5", "put on some music")
    assert ack["reaction"] == L.ASLEEP_LINE and life.impulse[0] == "listen_music"
    tick(life, t + 600, "NREM")
    assert life.activity == "sleep" and life.impulse                        # still asleep: it waits
    tick(life, t + 1800)                                                    # wakes within the hour: carried out
    assert life.activity == "listen_music" and life.impulse is None
    assert life.say == "wakes up; asked in chat: listen_music" and life.log[-1]["what"] == life.say
    # a request from more than IMPULSE_TTL before he wakes is stale: dropped, and the log says so
    t2 = t + 3600
    settle(life, "sleep", t2)
    tick(life, t2, "NREM")
    chat(live, "5.5.5.6", "check tiktok")
    assert life.impulse[0] == "phone"
    tick(life, t2 + 2 * 3600)
    assert life.impulse is None and life.say == "wakes up" and life.log[-1]["what"] == "wakes up"
    assert life.log[-2]["what"] == "asked in chat: phone; not any more: that was more than an hour ago"


def test_a_pending_request_is_checked_again_when_he_can_act():
    lf = L.Life({"place": "bench", "activity": "park", "until": 1e18}, rng=random.Random(0))
    lf.impulse = ("buy_bread", "asked in chat: buy_bread", at(19, 50))     # possible when asked, on the bench
    tick(lf, at(19, 59))                                                   # by now the bakery is closed by arrival
    assert lf.impulse is None and lf.activity == "park" and lf.place == "bench"
    assert lf.log[-1]["what"] == "asked in chat: buy_bread; not any more: the bakery is closed at this hour"
    lf.impulse = ("park", "asked in chat: park", at(19, 59))                # what he is doing already: dropped quietly
    tick(lf, at(19, 59) + 30)
    assert lf.impulse is None and lf.log[-1]["what"].startswith("asked in chat: buy_bread")


def test_a_pending_request_survives_a_restart(tmp_path):
    live = make_live(tmp_path)
    t, life = live.clock.now(), live.life
    settle(life, "window", t)
    life.start("park", t, "test")
    chat(live, "6.6.6.6", "want to play chess")
    d = life.to_dict()
    assert d["impulse"] == list(life.impulse) and d["impulse"][:2] == ["play_chess", "asked in chat: play_chess"]
    saved = {str(p): json.loads(json.dumps(obj, **kw)) for p, obj, kw in live.state_files()}   # the periodic save
    assert saved[str(live.life_path)]["impulse"] == d["impulse"]
    again = L.Life(json.loads(json.dumps(d)))
    assert again.impulse == life.impulse and again.activity == "park" and again.path     # restored on the way
    again.place, again.path = "bench", []
    again.x, again.z = L.PLACES["bench"]
    tick(again, t + 60)
    assert again.activity == "play_chess" and again.impulse is None
    # a save from before this, or a broken one, starts with none
    for s in ({}, {"impulse": None}, {"impulse": "play_chess"}, {"impulse": ["sleep", "x", 0]}, {"impulse": ["chart", "x", 0]},
              {"impulse": ["park", 1, 0]}, {"impulse": [["park"], "x", 0]}, {"impulse": ["park", "x", True]}):
        assert L.Life(s).impulse is None


def test_please_reply_is_taken_only_when_a_reply_is_possible(tmp_path):
    live = make_live(tmp_path)
    t, life = live.clock.now(), live.life
    fed(life)
    settle(life, "window", t)
    ack = chat(live, "8.8.8.8", "please reply to me")                      # no mind: nobody writes replies
    assert ack["reaction"] == "No reply is possible right now." and not ack["queued"] and life.impulse is None
    live.mind = M.Mind(tmp_path, Fake("Hello there."), M.mind_budget(tmp_path), clock=live.clock.now)
    ack = chat(live, "8.8.8.9", "please answer me", "mika")
    assert ack["queued"] and ack["will_reply"] and ack["reaction"] == REACTIONS["chat"]
    assert live.chat_inbox[-1]["text"] == "please answer me" and life.chat_waiting >= 1 and life.impulse[0] == "chat"
    tick(life, t + 1)
    assert life.activity == "chat" and life.path[-1] == "desk"


def test_a_named_game_asked_at_the_tv_switches_it_without_a_new_start(tmp_path):
    from home_world import HomeWorld
    live = make_live(tmp_path)
    t, life = live.clock.now(), live.life
    fed(life)
    life.home_enabled, life.console_games = True, {"pong", "minecraft"}
    settle(life, "play_console", t)
    life.console_choice = ("minecraft", t - 60)
    home = HomeWorld({"console_game": "minecraft", "last_console_choice": ["minecraft", t - 60]})
    ack = chat(live, "9.9.9.1", "switch to pong")                          # during the Minecraft session
    assert ack["reaction"] == "Okay, switching the TV to pong." and life.impulse is None
    assert life.activity == "play_console" and life.console_choice[0] == "pong" and life.console_wish is None
    assert life.log[-1]["what"] == "asked in chat: the TV switches to pong"
    home.update(0.05, 0.05, life.snapshot(), {})
    assert home.console_game == "pong"
    assert chat(live, "9.9.9.2", "play pong")["reaction"] == L.ALREADY_LINE   # the game on already: nothing to switch
    assert life.console_choice[0] == "pong" and life.console_wish is None
    # asked on the way to the TV: the same, before he gets there
    settle(life, "research", t)
    life.start("play_console", t + 1, "test")
    assert life.path and life.console_choice is None
    assert chat(live, "9.9.9.3", "play minecraft")["reaction"] == "Okay, switching the TV to minecraft."
    assert life.console_choice[0] == "minecraft" and life.impulse is None
    # a pending console request that finds him at the TV already does the same (the drop in update)
    settle(life, "play_console", t + 2)
    life.console_choice = ("minecraft", t + 2)
    life.hear("switch to pong", t + 3)
    life.impulse = ("play_console", "asked in chat: play_console", t + 3)
    tick(life, t + 4)
    assert life.impulse is None and life.console_choice[0] == "pong" and life.activity == "play_console"
