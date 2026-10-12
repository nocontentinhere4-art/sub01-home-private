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


def timed_life(activity, place):
    import random
    from life import Life
    from twin.body import Body
    life = Life({'activity': activity, 'place': place}, rng=random.Random(1),
                body=Body({'since_meal_h': .5, 'ghrelin': .1, 'glucose': 110}))
    life.hungry_now = lambda *args: False
    life.wish_now = lambda *args: False
    return life


def test_full_duration_starts_after_house_arrival_and_survives_save():
    from life import Life
    life = timed_life('research', 'desk')
    ready = False
    life.arrival_check = lambda: ready
    life.start('watch_video', 1000, 'test')  # same old-room place, different house state
    duration = life.dur
    assert duration and not life.path
    life.update(1000 + duration + 30, .2, .2, 'AWAKE', {})
    assert life.activity == 'watch_video' and life.dur == duration
    saved = Life(life.to_dict(), body=life.body)
    assert saved.dur == duration
    ready = True
    arrived_at = 1000 + duration + 31
    life.update(arrived_at, .2, .2, 'AWAKE', {})
    assert life.dur is None and life.until == pytest.approx(arrived_at + duration)


def test_sleep_can_interrupt_pending_house_arrival_without_consuming_food():
    life = timed_life('eat', 'table')
    life.food = 1
    life.food_items = ['bento']
    life.arrival_check = lambda: False
    life.start('eat', 1000, 'test')
    life.choose = lambda *args: 'sleep'
    life.update(2000, .2, .2, 'NREM', {})
    assert life.activity == 'sleep'
    assert life.food == 1 and life.food_items == ['bento']


def test_house_and_life_clocks_follow_the_complete_two_floor_route():
    life = timed_life('phone', 'bed')
    home = HomeWorld()
    home.node = home.target = 'bed'
    home.position = list(NODES['bed'])
    home.path = []
    home.activity = 'phone'
    live = Live.__new__(Live)
    live.life, live.home = life, home
    life.arrival_check = live.activity_arrived
    life.start('research', 1000, 'test')
    duration = life.dur
    visited = set()
    for tick in range(1, 1000):
        # Accelerated simulated clock exposes expiry during real-time walking.
        t = 1000 + tick * 10
        life.update(t, .1, 10, 'AWAKE', {})
        home.update(.1, 10, life.snapshot(), {})
        visited.add(home.node)
        assert life.activity == 'research'
        if life.dur is None:
            assert live.activity_arrived()
            assert life.until == pytest.approx(t + duration)
            break
    else:
        pytest.fail('House clock never started')
    assert {'stair_top', 'stair_bottom', 'desk'} <= visited
