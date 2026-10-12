"""The actual shared chess controller works at a settled sofa and at the desk."""
import asyncio
import json
import threading

import chess
import pytest

import chess_game
import live_server
from home_world import HomeWorld
from live_server import Live


def setup_live(tmp_path, monkeypatch, activity="play_console"):
    monkeypatch.setenv("HOME_ENABLED", "1")
    monkeypatch.setenv("SUB01_MINECRAFT", "0")
    monkeypatch.setattr(live_server, "CHESS_MIN_GAP_S", 0)
    monkeypatch.setattr(live_server, "CHESS_THINK_S", (0, 0))
    monkeypatch.setattr(live_server, "CHESS_REPLY_S", (0, 0))
    live = Live("m", True, time_scale=1, data_dir=tmp_path)
    live.engine.stage = "AWAKE"
    live.life.start(activity, live.clock.now(), "operator test fixture")
    live.life.path = []
    live.home = HomeWorld({"node": "sofa" if activity == "play_console" else "desk", "console_game": "chess"})
    live.home.update(.05, .05, {"activity": activity}, {})
    live.home.seated = 1
    live.sent = []
    async def broadcast(message):
        live.sent.append(message)
    live.broadcast = broadcast
    return live


def test_tv_chess_requires_selected_activity_awake_and_complete_seating(tmp_path, monkeypatch):
    live = setup_live(tmp_path, monkeypatch)
    for stage, seated, path in [("NREM", 1, []), ("AWAKE", .8, []), ("AWAKE", 1, ["window"])]:
        live.engine.stage, live.home.seated, live.life.path = stage, seated, path
        asyncio.run(live.chess_step())
        assert live.chess is None
    live.engine.stage, live.home.seated, live.life.path = "AWAKE", 1, []
    live.home.console_game = "pong"
    asyncio.run(live.chess_step())
    assert live.chess is None
    live.home.console_game = "chess"
    live.life.activity = "research"
    asyncio.run(live.chess_step())
    assert live.chess is None, "Choosing a TV game must not force his activity"
    live.life.activity = "play_console"
    asyncio.run(live.chess_step())
    assert live.chess is not None and live.chess.home_venue == "tv"


@pytest.mark.parametrize("activity,venue", [("play_console", "tv"), ("play_chess", "desk")])
def test_actual_controller_legal_game_finishes_and_ends_correct_venue(tmp_path, monkeypatch, activity, venue):
    monkeypatch.setattr(chess_game, "MAX_PLIES", 6)
    live = setup_live(tmp_path, monkeypatch, activity)
    async def play():
        for _ in range(20):
            await live.chess_step()
            if live.chess_last:
                break
    asyncio.run(play())
    assert live.chess is None and live.chess_last["plies"] == 6
    rows = [json.loads(line) for line in live.chess_path.read_text().splitlines()]
    board = chess.Board()
    for san in rows[0]["moves"].split():
        board.push_san(san)
    assert board.fen() == live.chess_last["fen"]
    assert live.chess_last["vote"]
    assert live.sent[-1]["finished"]
    assert live.life.until <= live.clock.now()


def test_switching_tv_game_finishes_board_without_ending_other_console_game(tmp_path, monkeypatch):
    live = setup_live(tmp_path, monkeypatch)
    asyncio.run(live.chess_step())
    until = live.life.until
    live.home.console_game = "pong"
    asyncio.run(live.chess_step())
    assert live.chess is None and live.chess_last["reason"] == "he got up"
    assert live.life.activity == "play_console" and live.life.until == until


def test_tv_chess_holds_and_then_applies_audience_vote(tmp_path, monkeypatch):
    live = setup_live(tmp_path, monkeypatch)
    asyncio.run(live.chess_step())
    t = live.clock.now()
    live.votes.pending = {"act": "window", "label": "look out of the window", "round": 1, "votes": 1, "total": 1, "at": t}
    message = {"type": "tick"}
    asyncio.run(live.audience_tick(message, t, {}, 0))
    assert live.votes.pending and message["aud"]["held"] == "after the game"
    live.chess.stop("test complete")
    asyncio.run(live.finish_chess(live.chess, t))
    assert live.votes.pending is None and live.life.nudge(t) == "window"


def test_queued_tv_move_is_not_applied_after_operator_switches_game(tmp_path, monkeypatch):
    live = setup_live(tmp_path, monkeypatch)
    entered, release = threading.Event(), threading.Event()
    async def run():
        await live.chess_step()
        game = live.chess
        game.color = chess.WHITE
        candidates = game.candidates
        def paused_candidates():
            entered.set()
            assert release.wait(5)
            return candidates()
        game.candidates = paused_candidates
        task = asyncio.create_task(live.chess_step())
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            live.home.console_game = "pong"
            release.set()
            await task
            assert game.public()["plies"] == 0, "No stale worker result may move a switched-away board"
            await live.chess_step()
            assert live.chess is None
        finally:
            release.set()
    asyncio.run(run())
