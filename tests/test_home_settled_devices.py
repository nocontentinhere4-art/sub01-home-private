import asyncio

from home_computer import Computer
from home_minecraft import MinecraftConsole
from home_world import HomeWorld


def test_linux_and_minecraft_wait_until_settled_and_pause_on_departure(tmp_path, monkeypatch):
    monkeypatch.setenv('SUB01_MINECRAFT', '1')
    for activity, node, device in [('use_computer', 'desk', Computer(tmp_path)),
                                    ('play_console', 'sofa', MinecraftConsole(tmp_path))]:
        home = HomeWorld({'node': node, 'console_game': 'minecraft'})
        messages = []

        async def send(message):
            messages.append(message)
            return True

        device.send = send
        if activity == 'use_computer':
            device.ready, device.paused = True, True
        else:
            device.state = {'connected': True, 'busy': False}
        for _ in range(30):
            home.update(.05, .05, {'activity': activity}, {})
            asyncio.run(device.agent_step(home, {}))
            assert not messages, 'the device must remain paused while settling into its seat'
        home.update(.05, .05, {'activity': activity}, {})
        assert home.seated == 1
        asyncio.run(device.agent_step(home, {}))
        assert messages[0] == ({'type': 'resume'} if activity == 'use_computer'
                               else {'type': 'active', 'value': True})
        if activity == 'use_computer':
            device.input_until = 0  # end deliberate operator-input grace period
        home.update(.05, .05, {'activity': 'use_bathroom'}, {})
        asyncio.run(device.agent_step(home, {}))
        assert messages[-1] == ({'type': 'pause'} if activity == 'use_computer'
                                else {'type': 'active', 'value': False})


def test_pong_waits_until_seated_and_stops_before_getting_up():
    home = HomeWorld({'node': 'sofa', 'console_game': 'pong'})
    for _ in range(30):
        home.update(.05, .05, {'activity': 'play_console'}, {})
        assert not home.pong.active
    home.update(.05, .05, {'activity': 'play_console'}, {})
    assert home.activity_ready('play_console') and home.pong.active
    home.update(.05, .05, {'activity': 'phone'}, {})
    assert not home.pong.active and not home.activity_ready('play_console')
