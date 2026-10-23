import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import home_minecraft
from home_minecraft import MinecraftConsole, OFFLINE_GRACE, eula_accepted
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
    home = HomeWorld({'node': 'sofa', 'seated': 1, 'console_game': 'minecraft'})
    home.activity = 'research'
    asyncio.run(console.agent_step(home, {}))
    assert messages == []
    home.activity = "play_console"
    asyncio.run(console.agent_step(home, {}))
    assert messages[0] == {"type": "active", "value": True}
    assert messages[1]["type"] == "action"
    home.activity = "sleep"
    asyncio.run(console.agent_step(home, {}))
    assert messages[-1] == {"type": "active", "value": False}


def test_missing_runtime_is_reported_offline_without_booting_the_server(tmp_path, monkeypatch, capsys):
    """No prepared server, Java or node_modules: the console says which (status, reason, one log line) and starts nothing."""
    monkeypatch.setenv("SUB01_MINECRAFT", "1")
    modules = tmp_path / "no_modules"
    monkeypatch.setattr(home_minecraft, "NODE_MODULES", modules)
    console = MinecraftConsole(tmp_path)
    console.directory.mkdir()
    missing = console.requirements()
    assert any("bootstrap" in reason for reason in missing) and any("npm ci" in reason for reason in missing)
    async def run():
        task = asyncio.create_task(console.run())
        await asyncio.sleep(.02)
        assert console.status == "offline" and "bootstrap" in console.error
        assert console.offline_reason() == console.error
        assert console.server is None and console.worker is None, "nothing heavy starts while the runtime is incomplete"
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(run())
    out = capsys.readouterr().out
    assert out.count("console offline:") == 1 and "bootstrap" in out
    # Prepared and accepted, but the Node packages are absent: still offline, naming only what is missing.
    (console.directory / "eula.txt").write_text("eula=true\n")
    (console.directory / "server.jar").write_bytes(b"fixture, never run")
    java = tmp_path / "java"
    java.write_text("#!/bin/sh\n")
    java.chmod(0o755)
    (console.directory / "downloads.json").write_text(json.dumps({"java": str(java)}))
    (console.directory / "server.properties").write_text(f"server-ip=127.0.0.1\nserver-port={console.server_port}\n")
    missing = console.requirements()
    assert any("npm ci" in reason for reason in missing)
    assert not any("bootstrap" in reason or "Java" in reason or "server.properties" in reason for reason in missing)
    for name in home_minecraft.node_packages():
        (modules / name).mkdir(parents=True)
        (modules / name / "package.json").write_text("{}")
    monkeypatch.setattr(home_minecraft.shutil, "which", lambda name: "/usr/bin/node")
    monkeypatch.setattr(home_minecraft, "importlib", SimpleNamespace(util=SimpleNamespace(find_spec=lambda name: object())))
    assert console.requirements() == []
    (console.directory / "server.properties").write_text("server-ip=0.0.0.0\nserver-port=25565\n")
    assert console.requirements() == [f"server.properties must bind 127.0.0.1:{console.server_port}"]


def test_offline_console_hands_the_tv_to_pong_and_says_why(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SUB01_MINECRAFT", "1")
    console = MinecraftConsole(tmp_path)
    home = HomeWorld({"node": "sofa", "seated": 1, "console_game": "minecraft"})
    home.activity = "play_console"
    assert console.offline_fallback(home, now=0) is False and home.console_game == "minecraft", "starting up is not offline"
    console.status = "offline"
    console.error = "Node packages missing in games/minecraft/node_modules: mineflayer (run `npm ci` in games/minecraft)"
    assert console.offline_fallback(home, now=0) is True
    assert home.console_game == "pong" and console.fallback["reason"] == console.error
    assert "console offline: Node packages missing" in capsys.readouterr().out
    view = console.view()
    assert view["offline_reason"] == console.error and view["fallback"]["to"] == "pong"
    home.update(.05, .05, {"activity": "play_console"}, {})
    assert home.pong.active, "the game that needs nothing installed actually runs"
    home.console_game = "minecraft"                       # selected again while still offline
    assert console.offline_fallback(home, now=1) is True and home.console_game == "pong"
    # An unexpected crash waits OFFLINE_GRACE for the supervised restart; a restart in progress keeps the clock running.
    console.status, console.error = "error", "Minecraft process ended (server=1, player=None); see local logs"
    console.offline_since = None
    home.console_game = "minecraft"
    assert console.offline_fallback(home, now=100) is False and home.console_game == "minecraft"
    console.status = "starting_server"
    assert console.offline_fallback(home, now=105) is False and console.offline_since == 100
    console.status = "error"
    assert console.offline_fallback(home, now=100 + OFFLINE_GRACE) is True and home.console_game == "pong"
    console.status, console.error = "playing", ""
    home.console_game = "minecraft"
    assert console.offline_fallback(home, now=200) is False
    assert console.fallback is None and console.offline_since is None, "back online: nothing left to explain"
    console.status, console.error = "needs_eula", "the owner has not accepted the Minecraft EULA (data/minecraft/eula.txt)"
    asyncio.run(console.agent_step(home, {}))
    assert home.console_game == "pong", "agent_step applies the fallback before anything else"


def test_unconfigured_console_never_keeps_minecraft_on_the_tv(tmp_path, monkeypatch):
    monkeypatch.delenv("SUB01_MINECRAFT", raising=False)
    console = MinecraftConsole(tmp_path)
    home = HomeWorld({"console_game": "minecraft"})
    asyncio.run(console.agent_step(home, {}))
    assert home.console_game == "pong" and "not configured" in console.fallback["reason"]


def test_chat_request_reaches_the_tv_and_an_offline_console_falls_back_to_pong(tmp_path, monkeypatch):
    """The whole path on the real server object: chat -> impulse + named game -> life.start -> HomeWorld -> console."""
    from live_server import Live
    monkeypatch.setenv("HOME_ENABLED", "1")
    monkeypatch.setenv("SUB01_MINECRAFT", "1")
    live = Live("m", True, time_scale=1, data_dir=tmp_path)
    live.engine.stage = "AWAKE"
    live.life.start("research", live.clock.now(), "test fixture")
    live.life.path = []

    class WS:
        def __init__(self):
            self.sent = []

        async def send_json(self, message):
            self.sent.append(message)

    ws = WS()
    asyncio.run(live.handle_chat(ws, "viewer-a", "play minecraft"))
    ack = ws.sent[-1]
    assert ack["ok"] is True and ack["impulse"] == "activity"
    assert live.life.impulse[0] == "play_console" and live.life.console_wish[0] == "minecraft"
    t = live.clock.now()
    live.life.update(t, 0.0, 0.0, "AWAKE", {})
    assert live.life.activity == "play_console" and live.life.console_choice[0] == "minecraft"
    live.home.update(.05, .05, live.life.snapshot(), {})
    assert live.home.console_game == "minecraft" and live.home.target == "sofa"
    assert live.minecraft.enabled and live.minecraft.status == "preparing"
    # The runtime is not installed on this machine: the supervised task reports it and the TV plays Pong.
    live.minecraft.status, live.minecraft.error = "offline", "; ".join(live.minecraft.requirements()) or "fixture: offline"
    asyncio.run(live.minecraft.agent_step(live.home, {}))
    assert live.home.console_game == "pong"
    assert live.minecraft.view()["fallback"]["reason"] == live.minecraft.error
    # A later "play pong" is a named wish: it is honoured when the console activity (re)starts.
    asyncio.run(live.handle_chat(WS(), "viewer-b", "switch to pong"))
    assert live.life.console_wish[0] == "pong"


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
