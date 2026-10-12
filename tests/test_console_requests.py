import random
import json
import pytest
from console_requests import game_request, valid_choice, TTL
from life import Life
from home_world import HomeWorld
from music import wish


def home_life():
    life = Life({'activity':'research', 'place':'desk'}, rng=random.Random(4))
    life.home_enabled = True
    life.console_games = {'pong','minecraft'}
    return life


def test_named_games_are_suggestions_and_not_song_queries():
    life = home_life()
    life.hear('Please play Minecraft on the TV',100)
    assert life.activity == 'research'
    assert life.console_wish == ('minecraft',100)
    assert life.desire('play_console',100) > 0
    assert life.desire('listen_music',100) == 0
    assert wish('play Minecraft') is None
    assert game_request('TRY PONG') == 'pong'
    assert game_request('gioca a Minecraft') == 'minecraft'
    assert game_request('what is Minecraft?') is None


def test_soundtrack_is_still_music_not_console():
    life = home_life()
    life.hear('play Minecraft soundtrack',100)
    assert life.console_wish is None
    assert life.desire('play_console',100) == 0
    assert life.desire('listen_music',100) > 0
    assert wish('play Minecraft soundtrack') == 'Minecraft soundtrack'


def test_choice_is_accepted_only_when_starting_console_and_not_reapplied():
    life = home_life(); home = HomeWorld({'console_game':'pong'})
    life.hear('play Minecraft',100)
    home.update(.05,.05,life.snapshot(),{})
    assert home.console_game == 'pong'
    assert home.view()['pending_console_game'] == 'minecraft'
    life.start('play_console',101,'test: selected through the activity gate')
    home.update(.05,.05,life.snapshot(),{})
    assert home.console_game == 'minecraft'
    assert home.view()['pending_console_game'] is None
    home.console_game = 'pong'  # subsequent explicit operator selection
    restored = HomeWorld(home.to_dict())
    restored.update(.05,.05,life.snapshot(),{})
    assert restored.console_game == 'pong'
    assert life.console_wish is None


def test_unavailable_and_expired_requests_do_not_select_a_game():
    life = home_life();life.console_games={'pong'}
    life.hear('play Minecraft',100)
    assert life.console_wish is None and life.desire('play_console',100) == 0
    life.hear('play Pong',100)
    life.start('play_console',100+TTL+1,'test: expired request')
    assert life.console_choice is None


def test_idle_suggestion_expires_without_waiting_for_console():
    life = home_life()
    life.hear('play Pong',100)
    life.until = 100 + TTL + 1000
    life.update(100 + TTL + 1,0,0,'AWAKE',{})
    assert life.console_wish is None


def test_pending_request_survives_state_serialization():
    life = home_life()
    life.hear('play Minecraft',100)
    restored = Life(json.loads(json.dumps(life.to_dict())))
    restored.console_games = {'pong','minecraft'}
    assert restored.console_wish == ('minecraft',100)
    restored.start('play_console',110,'test: activity selected after restore')
    assert restored.console_choice == ('minecraft',100)


@pytest.mark.parametrize('value',[None,[],[{},1],['minecraft',float('nan')],['pong',True],['unknown',1]])
def test_malformed_saved_choices_are_ignored(value):
    assert valid_choice(value) is None
