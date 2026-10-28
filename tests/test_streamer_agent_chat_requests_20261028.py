"""Owner 10-28, live chat: "leave full screen", "watch some other games", "react to some kai cenat", "play poker online"
were refused or never carried out (a playing video made every key and search stale_refused)."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_streamer_agent as T  # noqa: E402

SA = T.SA


@pytest.mark.parametrize("text", ["Bro leave full screan and do it, fuck gta 6", "exit fullscreen", "leave full screen",
                                  "get out of full-screen"])
def test_exit_full_screen_is_the_escape_key(text):
    r = SA.parse_request(text)
    assert r["kind"] == "key" and r["action"] == {"action": "key", "key": "Escape"}


@pytest.mark.parametrize("text", ["open full screen so we can watch", "bro go full screen", "full screen"])
def test_full_screen_is_a_click_for_the_model_not_a_search(text):
    r = SA.parse_request(text)
    assert r["kind"] == "look" and r["thing"] == "Full screen"


@pytest.mark.parametrize("text", ["Watch some others games", "Let's watch some other games trailers and react on it",
                                  "leave this video and open youtube"])
def test_screen_requests_are_not_leaving_the_desk(text):
    r = SA.parse_request(text)
    assert r is None or r["refused"] != "leave_desk"


@pytest.mark.parametrize("text", ["get up and dance", "leave the desk", "dance for us", "go outside and stream",
                                  "go to sleep and watch youtube", "leave the desk and play games", "take a nap on stream",
                                  "bro dance for the chat on screen", "stand up and show the screen"])
def test_leaving_the_desk_is_still_the_desk_line(text):
    r = SA.parse_request(text)
    assert SA.leaves_desk(text) and (r is None or r["refused"] == "leave_desk"), r


def test_react_to_something_searches_it_and_impressions_still_refuse():
    assert SA.parse_request("React to some kai cenat")["query"] == "kai cenat"
    assert SA.parse_request("lets react to new game trailers")["query"] == "new game trailers"
    assert SA.parse_request("react to this") is None and SA.parse_request("react to chat") is None
    assert SA.parse_request("do a kai cenat impression")["refused"] == "impression"


def test_poker_searches_pass_and_money_or_adult_ones_do_not():
    assert SA.parse_request("play free poker online")["query"] == "free poker"
    assert SA.parse_request("play poker")["query"] == "poker online free"
    assert SA.parse_request("search poker tips")["query"] == "poker tips"
    assert SA.parse_request("search poker porn")["refused"] == "adult"
    assert SA.parse_request("search best casino deposit bonus")["refused"] == "payment"
    assert "never deposits" in SA.SYSTEM_PC or "never deposits" in SA.SYSTEM


@pytest.mark.parametrize("action,sent", [({"action": "key", "key": "Escape"}, True),
                                         ({"action": "search", "query": "new game trailers"}, True),
                                         ({"action": "click", "point": [640, 360]}, False)])
def test_a_changing_picture_refuses_only_a_click(tmp_path, action, sent):
    base, moved = T.big_frame(), T.big_frame((250, 250, 250), stripes=False)         # a video playing: the whole frame changed
    assert SA.frame_diff(SA.frame_signature(base), SA.frame_signature(moved)) > SA.STALE_DIFF
    agent, world, prov, clock = T.pc_make(tmp_path, T.decision())
    world.frame = base
    prov.script, prov.n = [T.slow_decision(clock, lambda: setattr(world, "frame", moved), action, state="mouse", say="")], 0
    asyncio.run(T.decide_once(agent, clock, dt=3))
    assert (world.acts == [action]) is sent, agent.last_outcome


def test_play_chess_or_poker_online_happens_in_the_browser():
    for text in ("Go play some chess online", "play chess", "lets play a game of chess"):
        r = SA.parse_request(text)
        assert r["kind"] == "navigate" and r["url"] == "https://lichess.org", text
    assert SA.parse_request("Go play some poker online")["query"] == "poker online free"
    assert SA.parse_request("play a game of blackjack")["query"] == "blackjack online free"
    assert SA.parse_request("play detroit", pc=True)["kind"] == "launch_game"         # PC games keep their routine


@pytest.mark.parametrize("text", ["watch some dance videos on youtube", "search tiktok dance challenge",
                                  "leave this video and open youtube"])
def test_screen_requests_with_dance_or_leave_words_still_happen(text):
    r = SA.parse_request(text)
    assert not SA.leaves_desk(text) and (r is None or r["refused"] != "leave_desk"), r
