import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from home_minecraft import MinecraftConsole, eula_accepted
from home_world import HomeWorld

def test_eula_is_an_explicit_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("SUB01_MINECRAFT", "1")
    console = MinecraftConsole(tmp_path)
    console.directory.mkdir()
    (console.directory / "eula.txt").write_text("# eula=true\neula=false\n")
    assert not eula_accepted(console.directory)
    async def run():
        task = asyncio.create_task(console.run())
        await asyncio.sleep(.02)
        assert console.status == "needs_eula"
        assert console.server is None and console.worker is None
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(run())
    (console.directory / "eula.txt").write_text("eula=true\n")
    assert eula_accepted(console.directory)

def test_actions_follow_resources_and_live_threat_signals(tmp_path):
    console = MinecraftConsole(tmp_path)
    console.state = {"inventory": [], "wood": None, "threats": []}
    assert {console.choose({}) for _ in range(100)} <= {"explore", "gather_soil"}
    console.state["wood"] = {"name": "oak_log", "position": [1, 64, 3]}
    assert "mine_wood" in {console.choose({"attention": 2}) for _ in range(100)}
    console.state["threats"] = [{"name": "creeper", "distance": 2}]
    assert sum(console.choose({"fear": 10}) == "escape" for _ in range(1000)) > 850

def test_console_selection_persists_and_other_games_do_not_run(tmp_path):
    home = HomeWorld({"console_game": "minecraft"})
    restored = HomeWorld(home.to_dict())
    assert restored.console_game == "minecraft"
    restored.update(.05, .05, {"activity": "play_console"}, {})
    assert not restored.pong.active
    assert HomeWorld({"console_game": "unknown"}).console_game == "pong"

def test_agent_does_not_play_while_home_activity_is_elsewhere(tmp_path, monkeypatch):
    monkeypatch.setenv("SUB01_MINECRAFT", "1")
    console = MinecraftConsole(tmp_path)
    console.state = {"connected": True, "busy": False}
    messages = []
    async def send(message):
        messages.append(message)
        return True
    console.send = send
    home = SimpleNamespace(activity="research", path=[], console_game="minecraft")
    asyncio.run(console.agent_step(home, {}))
    assert messages == []
    home.activity = "play_console"
    asyncio.run(console.agent_step(home, {}))
    assert messages[0] == {"type": "active", "value": True}
    assert messages[1]["type"] == "action"
    home.activity = "sleep"
    asyncio.run(console.agent_step(home, {}))
    assert messages[-1] == {"type": "active", "value": False}


def test_isolated_game_ports_keep_main_instance_separate(tmp_path,monkeypatch):
    import pytest
    monkeypatch.setenv('SUB01_MC_SERVER_PORT','25570')
    monkeypatch.setenv('SUB01_MC_VIEW_PORT','8805')
    console=MinecraftConsole(tmp_path)
    assert (console.server_port,console.viewer_port)==(25570,8805)
    monkeypatch.setenv('SUB01_MC_VIEW_PORT','25570')
    with pytest.raises(ValueError,match='distinct'): MinecraftConsole(tmp_path)
    monkeypatch.setenv('SUB01_MC_VIEW_PORT','80')
    with pytest.raises(ValueError): MinecraftConsole(tmp_path)
