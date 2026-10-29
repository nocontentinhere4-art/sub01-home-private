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


def test_a_vague_request_from_another_viewer_continues_the_last_one():
    q = [(100.0, "kai cenat videos")]
    for text, want in (("Go on videos and look at some of them", "kai cenat videos"),
                       ("show us more videos", "kai cenat videos"), ("watch some clips", "kai cenat clips"),
                       ("check out his latest videos", "kai cenat videos")):
        assert SA.contextual_query(SA.parse_request(text)["query"], [], 150.0, q) == want, text
    assert SA.contextual_query("videos and look", [], 100.0 + SA.CONTEXT_S + 1, q) == "videos and look"   # too old
    assert SA.contextual_query("minecraft speedruns", [], 150.0, q) == "minecraft speedruns"            # a new topic
    assert SA.topic_words("React to some kai cenat videos") == [] and "react" in SA.TOPIC_SKIP
    assert "Read chat as one conversation" in SA.SYSTEM_PC or "Read chat as one conversation" in SA.SYSTEM


def test_a_click_beside_a_playing_video_goes_through(tmp_path):
    base = T.big_frame(box=(1000, 0, 1280, 720))                          # the sidebar on the right stays put
    playing = T.big_frame((240, 240, 240), stripes=False, box=(1000, 0, 1280, 720))   # the video area changed entirely
    assert SA.frame_diff(SA.frame_signature(base), SA.frame_signature(playing)) > SA.STALE_DIFF
    click = {"action": "click", "point": [1150, 400]}
    agent, world, prov, clock = T.pc_make(tmp_path, T.decision())
    world.frame = base
    prov.script, prov.n = [T.slow_decision(clock, lambda: setattr(world, "frame", playing), click, state="mouse", say="")], 0
    asyncio.run(T.decide_once(agent, clock, dt=3))
    assert world.acts == [click], agent.last_outcome


def test_leave_and_another_request_is_that_request_not_the_desk_line():
    r = SA.parse_request("leave and go on some casino websites", pc=True)
    assert r["kind"] == "search" and r["query"] == "casino websites"
    assert SA.parse_request("leave this video and search kai cenat", pc=True)["query"] == "kai cenat"
    assert SA.parse_request("leave the desk and play games")["refused"] == "leave_desk"
    assert not SA.leaves_desk("leave") and SA.leaves_desk("leave the room and go outside")


@pytest.mark.parametrize("text,query", [
    ("open youtube and find something about elon musk to react to", "elon musk"),
    ("find something on youtube about elon musk", "elon musk"),
    ("search for something funny about dogs", "funny dogs"),
    ("look up stuff about GTA 6 and react to it", "GTA 6"),
    ("go on youtube and search kai cenat", "kai cenat"),
    ("search the GTA 6 trailer", "GTA 6 trailer"),
    ("search youtube for mrbeast videos", "mrbeast videos")])
def test_a_request_searches_its_subject_not_the_sentence(text, query):
    assert SA.parse_request(text, pc=True)["query"] == query


@pytest.mark.parametrize("text,kind,url", [
    ("search for reaction to people do something crazy in gameplays", "look", None),     # long: the model writes it
    ("search kai cenat videos", "search", SA.YT_RESULTS + "kai+cenat+videos"),
    ("open youtube and find something about elon musk to react to", "search", SA.YT_RESULTS + "elon+musk"),
    ("search best ramen in Shinjuku", "search", None),                                   # not about videos: the web
    ("search who won the champions league", "search", None)])
def test_video_searches_open_youtube_and_long_ones_go_to_the_model(text, kind, url):
    req = SA.parse_request(text, pc=True)
    out = SA.search_target(dict(req, text=text))
    assert out["kind"] == kind and (out.get("action") or {}).get("url") == url
    if kind == "look":
        assert out["intent"] == "search" and SA.ACK_LOOK_LINES["search"]


def test_the_model_writes_the_youtube_search_for_a_long_request(tmp_path):
    step = T.decision(state="mouse", action={"action": "navigate",
                                             "url": SA.YT_RESULTS + "crazy+gameplay+moments+reaction"}, say="")
    agent, world, prov, clock = T.pc_make(tmp_path, step)
    world.chat_msgs = [T.msg(1, "search for reaction to people do something crazy in gameplays", "v")]
    asyncio.run(T.decide_once(agent, clock, dt=3))
    asyncio.run(T.decide_once(agent, clock, dt=3))
    assert any(SA.SEARCH_HINT in h for c in prov.calls for h in c["state"].get("hints", [])), prov.calls[-1]["state"]["hints"]


def test_ai_getting_tortured_is_a_meme_search_and_real_harm_is_not():
    assert SA.parse_request("Bro search for ai getting tortured", pc=True)["query"] == "ai getting tortured"
    assert SA.parse_request("search robots getting kicked", pc=True)["query"] == "robots getting kicked"
    assert SA.parse_request("search people getting tortured", pc=True)["refused"] == "query_filter"
    for q in ("AI and people getting tortured", "robot torturing people", "robot kills dog", "robot kills puppy",
              "robot torturing my mom"):
        assert not SA.ai_meme_query(q), q                  # the exception never applies with any other subject (Kimi)
    assert SA.ai_meme_query("chatgpt getting tortured by prompts") and SA.ai_meme_query("ai getting tortured")
    assert SA.parse_request("search AI and people getting tortured", pc=True)["refused"] == "query_filter"
    assert "keep at most 3 open" in SA.SYSTEM_PC + SA.SYSTEM


def test_react_at_a_youtube_video_about_something_searches_the_something():
    assert SA.parse_request("React at a youtube video about AI getting tortured", pc=True)["query"] == "AI getting tortured"


# ------------------------------------------------------------------ live 10-29 fixes

@pytest.mark.parametrize("text", ["Bro can you play some games ?", "play a game", "can you play video games"])
def test_play_some_games_opens_a_browser_game_site(text):
    r = SA.parse_request(text)
    assert r["kind"] == "navigate" and r["url"] == SA.GAMES_SITE


def test_slang_vid_leaves_the_query_but_still_means_youtube():
    r = dict(SA.parse_request("Can you watch a tjr vid"), text="Can you watch a tjr vid")
    assert r["query"] == "tjr" and SA.search_target(r)["url"].endswith("search_query=tjr")
    assert SA.parse_request("watch some kai cenat clips")["query"] == "kai cenat clips"


def test_new_lines_pass_the_filters():
    for line in SA.ACK_NAVIGATE_LINES + (SA.ACK_LOOK_LINES["play"],):
        assert SA.reply_problem(line) is None and "tab audio" not in line


def test_the_pc_prompt_keeps_the_fomo_tab_and_never_invites_deposits():
    p = SA.system_prompt(pc=True, allow_credentials=True)
    assert "fomo.family tab that always stays open" in p and "Never invite chat to deposit" in p
    assert "he cannot drag" in p and "at least two minutes" in p


@pytest.mark.parametrize("text,query", [("Play Minecraft and hit up other streamers to join", "Minecraft play online free"),
                                        ("play roblox", "roblox play online free")])
def test_play_a_named_game_is_a_game_not_leaving_the_desk(text, query):
    r = SA.parse_request(text, pc=True)
    assert r["kind"] == "search" and r["query"] == query and not SA.leaves_desk(text)


@pytest.mark.parametrize("text", ["stand up and play minecraft", "get up and play roblox"])
def test_explicit_off_desk_still_refused(text):
    assert SA.parse_request(text, pc=True)["refused"] == "leave_desk"


def test_play_music_or_a_video_stays_a_video_request():
    assert SA.parse_request("play some music", pc=True)["query"] == "music"
    assert SA.parse_request("play the video", pc=True)["intent"] == "play"
