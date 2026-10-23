"""Real house travel must finish before a device activity starts."""
import math
import random
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import home_interactions as hi
from home_world import EDGES, HomeWorld, NODES
from life import ACTIVITIES, Life
from live_server import Live


@pytest.mark.parametrize('activity,device', [('research', 'desk'), ('watch_video', 'desk'), ('phone', 'phone')])
def test_screen_waits_for_new_house_route(activity, device):
    live = Live.__new__(Live)
    live.life = SimpleNamespace(activity=activity, path=[], phone_app='tiktok')   # the phone shows a browser page only for shorts
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
        if not home.activity_ready(activity):
            assert live.screen_device() is None
        else:
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


@pytest.mark.parametrize('activity,node', [('research', 'desk'), ('phone', 'bed'), ('play_console', 'sofa')])
def test_activity_timer_waits_for_the_complete_seated_transition(activity, node):
    life = timed_life('research', 'desk')
    home = HomeWorld({'node': node})
    live = Live.__new__(Live)
    live.life, live.home = life, home
    life.arrival_check = live.activity_arrived
    life.start(activity, 1000, 'test')
    life.path = []  # old-room route is already finished
    duration = life.dur
    for tick in range(1, 40):
        now = 1000 + tick * 10
        life.update(now, .05, 10, 'AWAKE', {})
        if not home.activity_ready(activity):
            assert life.dur == duration
        home.update(.05, 10, life.snapshot(), {})
        if life.dur is None:
            assert home.seated == 1 and live.activity_arrived()
            assert life.until == pytest.approx(now + duration)
            break
    else:
        pytest.fail('Seated transition did not release the activity timer')


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


def test_native_required_cannot_fall_back_to_the_old_room(monkeypatch):
    monkeypatch.setenv('HOME_NATIVE_REQUIRED', '1')
    live = Live.__new__(Live)
    live.life = SimpleNamespace(activity='research', path=[])
    live.engine = SimpleNamespace(stage='AWAKE')
    assert not live.activity_arrived()
    assert live.screen_device() is None


TICK = .1
TOKYO_NOON = datetime(2026, 10, 12, 12, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()
OUT = hi.OUTDOOR_PLACES   # the life places on the real streets; the house keeps him outside while life is there


class Rig:
    """Life and the house stepped the way live_server steps them: life first, then the house, once per tick."""

    def __init__(self, life_state, home_state, scale=1.0):
        from twin.body import Body
        self.life = Life(life_state, rng=random.Random(4),
                         body=Body({'since_meal_h': .5, 'ghrelin': .1, 'glucose': 110}))
        self.life.time_scale = scale
        self.life.hungry_now = lambda *args: False
        self.life.wish_now = lambda *args: False
        self.home = HomeWorld(home_state)
        self.live = Live.__new__(Live)
        self.live.life, self.live.home = self.life, self.home
        self.life.arrival_check = self.live.activity_arrived
        self.scale, self.t, self.rows = scale, TOKYO_NOON, []

    def tick(self, stage='AWAKE'):
        life, home = self.life, self.home
        life.update(self.t, TICK, TICK * self.scale, stage, {}, 0.0, 0.0)
        snap = life.snapshot()
        home.update(TICK, TICK * self.scale, snap, {}, now=self.t)
        self.rows.append(dict(
            t=self.t, life=(life.activity, life.place, bool(life.path), snap['path_to']),
            impulse=life.impulse is not None, node=home.node, target=home.target,
            pos=list(home.position), path=len(home.path), seated=home.seated,
            front=home.interactions.door_state('front'), privacy=home.privacy(),
            ready=home.activity_ready(life.activity)))
        self.t += TICK * self.scale
        return self.rows[-1]


def on_house_edges(p):
    """The position is on one of the house's walking edges: he never cuts through furniture or walls."""
    for a, b in EDGES:
        A, B = NODES[a], NODES[b]
        d = [y - x for x, y in zip(A, B)]
        n = sum(v * v for v in d) or 1.0
        s = max(0.0, min(1.0, sum((q - x) * v for q, x, v in zip(p, A, d)) / n))
        if math.dist(p, [x + v * s for x, v in zip(A, d)]) < 1e-6:
            return True
    return False


def check_walk_home(rows):
    """Row by row, a walk home from the street: no teleport, house edges only, he waits outside while life is
    outdoors, he is walked in only once life is off the street, the door is open whenever he crosses it, and
    a walk ends where its activity's place is. Returns the first row where he is walked back in."""
    turn = None
    for i, row in enumerate(rows):
        assert on_house_edges(row['pos']), row
        if i:
            prev = rows[i - 1]
            assert math.dist(row['pos'], prev['pos']) <= 1.25 * TICK + 1e-6, (prev, row)
            if hi.outside_house(prev['pos']) != hi.outside_house(row['pos']):
                assert row['front'] == 'open', row
            if hi.outside_house(prev['pos']) and not hi.outside_house(row['pos']):
                assert row['life'][1] not in OUT, row
            if turn is None and prev['target'] == 'outside' and row['target'] != 'outside':
                turn = i
        if row['life'][1] in OUT:
            assert row['target'] == 'outside', row
        if row['life'][2]:
            assert row['life'][3] == ACTIVITIES[row['life'][0]][0], row
    assert turn is not None, 'he was never walked back in'
    return turn


def stand_up_seconds(rows):
    """Seconds from the first tick of a walk that starts from a seat to the first step taken."""
    start = next(i for i, r in enumerate(rows) if r['path'])
    moved = next(i for i in range(start, len(rows)) if rows[i]['pos'] != rows[start]['pos'])
    return rows[moved]['t'] - rows[start]['t']


def test_walk_home_from_the_park_waits_outside_then_comes_in_at_door_out_to_bed():
    rig = Rig({'activity': 'research', 'place': 'desk'}, {'node': 'desk', 'seated': 1})
    rig.life.start('park', rig.t, 'test')
    stage = 'AWAKE'
    for _ in range(40000):
        row = rig.tick(stage)
        if stage == 'AWAKE' and rig.life.place == 'bench' and not row['life'][2] and row['node'] == 'outside':
            stage = 'NREM'     # a sleep stage begins at the bench: the walk home is a walk to bed
        if rig.life.activity == 'sleep' and rig.life.place == 'bed' and row['ready']:
            break
    else:
        raise AssertionError('never got to bed')
    rows = rig.rows
    turn = check_walk_home(rows)
    assert rows[turn]['life'][1] == 'door_out' and rows[turn]['target'] == 'bed'
    bench = next(r for r in rows if r['life'][1] == 'bench')
    assert bench['node'] == 'outside' and not bench['path'] and bench['front'] == 'locked'
    assert 1.2 <= stand_up_seconds(rows) <= 2.5
    assert rows[-1]['node'] == 'bed' and rows[-1]['seated'] == 1 and not rows[-1]['path']


def test_walk_home_from_the_bakery_comes_in_at_door_out_to_the_table_for_a_meal():
    rig = Rig({'activity': 'research', 'place': 'desk'}, {'node': 'desk', 'seated': 1})
    rig.life.start('buy_bread', rig.t, 'test')
    rig.life.choose = lambda t, stage, *args: 'eat' if stage == 'AWAKE' else 'sleep'
    for _ in range(40000):
        row = rig.tick()
        if rig.life.activity == 'eat' and rig.life.place == 'table' and row['ready'] and not row['life'][2]:
            break
    else:
        raise AssertionError('never sat down to eat')
    rows = rig.rows
    turn = check_walk_home(rows)
    assert rows[turn]['life'][1] == 'door_out' and rows[turn]['target'] == 'kitchen'
    counter = next(r for r in rows if r['life'][1] == 'counter')
    assert counter['node'] == 'outside' and not counter['path'] and counter['front'] == 'locked'
    assert 1.2 <= stand_up_seconds(rows) <= 2.5
    assert rows[-1]['node'] == 'kitchen' and not rows[-1]['path']


def test_courier_turning_him_back_on_the_street_brings_him_in_at_door_out():
    rig = Rig({'activity': 'research', 'place': 'desk'}, {'node': 'desk', 'seated': 1})
    rig.life.start('park', rig.t, 'test')
    rig.life.delivery = {'ordered': rig.t, 'leaves': rig.t, 'arrives': rig.t + 30, 'dish': 'ramen'}
    for _ in range(40000):
        row = rig.tick()
        if rig.life.activity == 'get_delivery' and row['node'] == 'door' and row['ready'] and not row['life'][2]:
            break
    else:
        raise AssertionError('the courier was never answered at the door')
    rows = rig.rows
    turn = check_walk_home(rows)
    turned = next(r for r in rows if r['life'][0] == 'get_delivery')
    assert turned['life'][1] in OUT and turned['life'][2]                 # he turns back mid-walk, on the street
    assert rows[turn]['life'][1] == 'door_out' and rows[turn]['target'] == 'door'


def test_chat_impulse_mid_walk_waits_for_arrival_and_keeps_him_out_until_then():
    rig = Rig({'activity': 'research', 'place': 'desk'}, {'node': 'desk', 'seated': 1})
    rig.life.start('park', rig.t, 'test')
    sent = None
    for _ in range(40000):
        if sent is None and rig.life.place == 'street_home' and rig.life.path:
            rig.life.request_impulse(SimpleNamespace(kind='activity', activity='research',
                                                     why='chat asks for research'), rig.t)
            sent = len(rig.rows)
        row = rig.tick()
        if sent is not None and rig.life.activity == 'research' and row['node'] == 'desk' \
                and not row['path'] and row['ready']:
            break
    else:
        raise AssertionError('the chat request was never carried out')
    rows = rig.rows
    switch = next(i for i, r in enumerate(rows) if r['life'][0] == 'research')
    waiting = rows[sent:switch]
    assert waiting and all(r['impulse'] and r['life'][0] == 'park' for r in waiting)
    assert waiting[-1]['life'][1] == 'bench' and not waiting[-1]['life'][2]     # carried out at the bench
    assert not rows[switch]['impulse']
    turn = check_walk_home(rows)
    assert rows[turn]['life'][1] == 'door_out' and rows[turn]['target'] == 'desk'


def test_sleep_stage_beginning_on_the_way_home_takes_him_to_bed_from_outside():
    rig = Rig({'activity': 'research', 'place': 'desk'}, {'node': 'desk', 'seated': 1})
    rig.life.start('park', rig.t, 'test')
    rig.life.choose = lambda t, stage, *args: 'sleep' if stage != 'AWAKE' else 'research'
    stage, ended = 'AWAKE', False
    for _ in range(40000):
        row = rig.tick(stage)
        if not ended and rig.life.place == 'bench' and not row['life'][2] and row['node'] == 'outside':
            rig.life.end_activity(rig.t)                       # the park is over: he walks home to research
            ended = True
        if stage == 'AWAKE' and ended and rig.life.place == 'street_home' and row['life'][2]:
            stage = 'NREM'                                     # the sleep stage begins on the way home
        if rig.life.activity == 'sleep' and rig.life.place == 'bed' and row['ready']:
            break
    else:
        raise AssertionError('never got to bed')
    rows = rig.rows
    turn = check_walk_home(rows)
    assert rows[turn]['life'][1] == 'door_out' and rows[turn]['target'] == 'desk'
    assert any(r['life'][0] == 'research' and r['life'][2] for r in rows)   # the walk home was the research one
    assert rows[-1]['node'] == 'bed' and rows[-1]['seated'] == 1 and not rows[-1]['path']


@pytest.mark.parametrize('scale', [1, 24, 60])
def test_use_bathroom_arrives_in_private_and_empties_the_bladder_at_any_speed(scale):
    rig = Rig({'activity': 'research', 'place': 'desk'}, {'node': 'desk', 'seated': 1, 'bladder': .9}, scale)
    rig.life.start('use_bathroom', rig.t, 'test')
    arrived = None
    for _ in range(100000):
        rig.life.home_bladder = rig.home.bladder
        row = rig.tick()
        if arrived is None and row['node'] == 'bathroom' and not row['path'] and row['ready']:
            arrived = row
        if arrived is not None and rig.life.activity != 'use_bathroom':
            break
    else:
        raise AssertionError('the visit never ended')
    visit = [r for r in rig.rows if r['t'] >= arrived['t']]
    assert all(r['privacy'] and r['node'] == 'bathroom' for r in visit[:-1])
    assert visit[-1]['t'] - arrived['t'] >= 59           # the visit's clock starts on arrival: one to two minutes
    assert rig.home.bladder < .01                         # and it empties him at any speed (a tick short at most)
