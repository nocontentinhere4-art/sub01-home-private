import dataclasses
import pytest
from impulse import KEYWORD_RULES, REACTIONS, Impulse, parse
from life import ACTIVITIES


def test_empty_and_whitespace_text_is_reply_only():
    for text in ('', '   ', '\n\t '):
        assert parse(text) == Impulse('reply_only', None, None, 'Hm? Say that again.', 'empty message')


def test_link_opens_url():
    got = parse('look at https://example.com/a?b=1 please')
    assert got == Impulse('open_url', None, 'https://example.com/a?b=1', 'On it, let me open that.', 'a link was sent')


def test_url_trailing_punctuation_is_removed():
    assert parse('see https://example.com/page.').url == 'https://example.com/page'
    assert parse('(https://example.com/x), thanks').url == 'https://example.com/x'


def test_url_is_capped_at_2000_characters():
    url = parse('https://example.com/' + 'a' * 3000).url
    assert len(url) == 2000 and url.startswith('https://example.com/')


def test_url_wins_over_keywords():
    assert parse('https://example.com/chess').kind == 'open_url'


def test_other_schemes_are_never_urls():
    for text in ('javascript:alert(1)', 'file:///etc/hosts', 'data:text/html,hello', 'ftp://example.com/x'):
        got = parse(text)
        assert got.kind == 'reply_only' and got.url is None
    assert parse('javascript:alert(1) then chess').kind == 'activity'


@pytest.mark.parametrize('text, activity', [
    ('open the laptop', 'use_computer'),
    ('please look up the train times', 'research'),
    ('put on the TV', 'play_console'),
    ('want to play chess', 'play_chess'),
    ('check tiktok', 'phone'),
    ('put on some music', 'listen_music'),
    ('show me a youtube clip', 'watch_video'),
    ('are you hungry', 'eat'),
    ('order a pizza', 'order_food'),
    ('go to the bakery', 'buy_bread'),
    ('get something at the konbini', 'buy_konbini'),
    ('take a walk', 'park'),
    ('look through the window', 'window'),
    ('time for a nap', 'sleep'),
    ('use the bathroom', 'use_bathroom'),
    ('please reply to me', 'chat'),
])
def test_keyword_maps_to_activity(text, activity):
    assert parse(text) == Impulse('activity', activity, None, REACTIONS[activity], f'asked in chat: {activity}')


def test_keywords_are_case_insensitive_whole_words():
    assert parse('CHESS?').activity == 'play_chess'
    assert parse('Hungry!').activity == 'eat'
    assert parse('go   out').activity == 'park'
    assert parse('the convenience\nstore').activity == 'buy_konbini'
    assert parse('bedrooms and kitchens').kind == 'reply_only'
    assert parse('two computers').activity == 'use_computer'


def test_first_matching_rule_wins():
    assert parse('use the computer to look up chess').activity == 'use_computer'
    assert parse('go out and eat').activity == 'eat'


def test_no_match_is_reply_only():
    assert parse('what is your favourite colour') == Impulse(
        'reply_only', None, None, 'Not doing that one. Ask me something else.', 'no action matched')


def test_mapped_activities_exist_in_life_and_reactions_fit():
    names = {name for name, _ in KEYWORD_RULES}
    assert set(REACTIONS) == names
    assert names <= set(ACTIVITIES)
    lines = list(REACTIONS.values()) + [parse(t).reaction for t in ('', 'https://example.com', 'what is your favourite colour')]
    assert all(0 < len(line) <= 60 for line in lines)


def test_bare_domain_after_an_opening_verb_gets_https():
    assert parse('open formo.family').url == 'https://formo.family'
    assert parse('apri formo.family').url == 'https://formo.family'
    assert parse('visit example.com/a.').url == 'https://example.com/a'
    assert parse('open the laptop').kind == 'activity'
    assert parse('look at the window').activity == 'window'


def test_plurals_match_their_activity():
    assert parse('play some games').activity == 'play_console'
    assert parse('check the videos').activity == 'watch_video'
    assert parse('take the walks').activity == 'park'


def test_impulse_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        parse('chess').kind = 'reply_only'
