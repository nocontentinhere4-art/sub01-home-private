"""Real house travel must finish before a device activity starts."""
from types import SimpleNamespace

import pytest

from home_world import HomeWorld, NODES
from live_server import Live


@pytest.mark.parametrize('activity,device', [('research', 'desk'), ('watch_video', 'desk'), ('phone', 'phone')])
def test_screen_waits_for_new_house_route(activity, device):
    live = Live.__new__(Live)
    live.life = SimpleNamespace(activity=activity, path=[])
    live.engine = SimpleNamespace(stage='AWAKE')
    home = live.home = HomeWorld()
    # The old route has already ended, but the real house has not.
    origin = 'desk' if activity == 'phone' else 'bed'
    home.node = home.target = origin
    home.position = list(NODES[origin])
    home.path = []
    home.activity = 'phone' if origin == 'bed' else 'research'
    assert live.screen_device() is None
    for _ in range(1000):
        home.update(.1, .1, {'activity': activity}, {})
        if home.path:
            assert live.screen_device() is None
        elif home.node == home.desired(activity):
            break
    else:
        pytest.fail('House route never arrived')
    assert live.screen_device() == device
    live.engine.stage = 'NREM'
    assert live.screen_device() is None


def test_old_room_remains_available_without_home():
    live = Live.__new__(Live)
    live.life = SimpleNamespace(activity='research', path=[])
    live.engine = SimpleNamespace(stage='AWAKE')
    assert live.screen_device() == 'desk'
    live.life.path = ['desk']
    assert live.screen_device() is None
