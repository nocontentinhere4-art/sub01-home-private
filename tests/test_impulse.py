import dataclasses
import pytest
from impulse import KEYWORD_RULES, NEGATED_REACTION, QUESTION_REACTION, REACTIONS, WEAK_RULES, Impulse, parse
from life import ACTIVITIES

NO_MATCH = Impulse('reply_only', None, None, 'Not doing that one. Ask me something else.', 'no action matched')
NEGATED = Impulse('reply_only', None, None, NEGATED_REACTION, 'a negated request, no action')
QUESTION = Impulse('reply_only', None, None, QUESTION_REACTION, 'a question, no action')


def activity(name):
    return Impulse('activity', name, None, REACTIONS[name], f'asked in chat: {name}')


def link(url):
    return Impulse('open_url', None, url, 'On it, let me open that.', 'a link was sent')


def test_empty_and_whitespace_text_is_reply_only():
    for text in ('', '   ', '\n\t '):
        assert parse(text) == Impulse('reply_only', None, None, 'Hm? Say that again.', 'empty message')


def test_link_opens_url():
    assert parse('look at https://example.com/a?b=1 please') == link('https://example.com/a?b=1')


def test_url_trailing_punctuation_is_removed():
    assert parse('see https://example.com/page.').url == 'https://example.com/page'
    assert parse('(https://example.com/x), thanks').url == 'https://example.com/x'
    assert parse('open https://example.com/x?!').url == 'https://example.com/x'


def test_url_is_capped_at_2000_characters():
    url = parse('https://example.com/' + 'a' * 3000).url
    assert len(url) == 2000 and url.startswith('https://example.com/')


def test_link_beats_keywords_wherever_it_stands():
    assert parse('https://example.com/chess').kind == 'open_url'
    assert parse('chess https://example.com').kind == 'open_url'


def test_other_schemes_are_never_urls():
    for text in ('javascript:alert(1)', 'file:///etc/hosts', 'data:text/html,hello', 'ftp://example.com/x'):
        got = parse(text)
        assert got.kind == 'reply_only' and got.url is None
    assert parse('javascript:alert(1) then chess').kind == 'activity'


@pytest.mark.parametrize('text, name', [
    ('open the laptop', 'use_computer'),
    ('please look up the train times', 'research'),
    ('put on the TV', 'play_console'),
    ('want to play chess', 'play_chess'),
    ('check tiktok', 'phone'),
    ('put on some music', 'listen_music'),
    ('show me a youtube clip', 'watch_video'),
    ('I am so hungry', 'eat'),
    ('order a pizza', 'order_food'),
    ('go to the bakery', 'buy_bread'),
    ('get something at the konbini', 'buy_konbini'),
    ('take a walk', 'park'),
    ('look through the window', 'window'),
    ('time for a nap', 'sleep'),
    ('use the bathroom', 'use_bathroom'),
    ('please reply to me', 'chat'),
])
def test_keyword_maps_to_activity(text, name):
    assert parse(text) == activity(name)


@pytest.mark.parametrize('text, name', [
    ('accendo il portatile', 'use_computer'),
    ('cerca i treni', 'research'),
    ('fammi vedere la tv', 'play_console'),
    ('giochiamo alla playstation', 'play_console'),
    ('gioca a scacchi', 'play_chess'),
    ('metti una canzone', 'listen_music'),
    ('ho le cuffie', 'listen_music'),
    ('guarda un filmato', 'watch_video'),
    ('ho fame', 'eat'),
    ('pranziamo insieme', 'eat'),
    ('mangio qualcosa', 'eat'),
    ('ceno presto', 'eat'),
    ('ordina una pizza', 'order_food'),
    ('ordino una pizza', 'order_food'),
    ('cerco i treni', 'research'),
    ('rispondo dopo', 'chat'),
    ('vado in panetteria', 'buy_bread'),
    ('vado al negozio', 'buy_konbini'),
    ('esci fuori', 'park'),
    ('facciamo una passeggiata', 'park'),
    ('guarda fuori dalla finestra', 'window'),
    ('dormi bene', 'sleep'),
    ('vado a letto', 'sleep'),
    ('vado in bagno', 'use_bathroom'),
    ('faccio la doccia', 'use_bathroom'),
    ('rispondimi', 'chat'),
])
def test_italian_keyword_maps_to_activity(text, name):
    assert parse(text) == activity(name)


@pytest.mark.parametrize('text, name', [
    ('turn on the PS5', 'play_console'),
    ('grab the controller', 'play_console'),
    ('gaming time', 'play_console'),
    ('open your laptop', 'use_computer'),
    ('let us have a snack', 'eat'),
    ('I am starving', 'eat'),
    ('go for a stroll', 'park'),
    ('I need a nap', 'sleep'),
    ('so sleepy', 'sleep'),
    ('where is the loo', 'use_bathroom'),
    ('text me', 'phone'),
    ('send a message', 'phone'),
    ('message me later', 'phone'),
])
def test_english_synonym_maps_to_activity(text, name):
    assert parse(text) == activity(name)


def test_bare_text_and_message_are_not_actions():
    for text in ('this text is nice', 'this message is cool', 'the messages'):
        assert parse(text) == NO_MATCH


def test_sleep_gets_its_own_reaction():
    assert parse('time for a nap').reaction == 'I sleep when my body says so.'


def test_keywords_are_case_insensitive_whole_words():
    assert parse('CHESS?').activity == 'play_chess'
    assert parse('Hungry!').activity == 'eat'
    assert parse('go   out').activity == 'park'
    assert parse('the convenience\nstore').activity == 'buy_konbini'
    assert parse('bedrooms and kitchens') == NO_MATCH
    assert parse('two computers').activity == 'use_computer'


def test_earliest_keyword_in_the_text_wins():
    assert parse('order lunch') == activity('order_food')
    assert parse('look outside the window') == activity('window')
    assert parse('go to the park and eat') == activity('park')
    assert parse('eat, then go out') == activity('eat')
    assert parse('go out and eat') == activity('park')
    assert parse('use the computer to look up chess') == activity('use_computer')
    assert parse("I'm starving, order sushi") == activity('eat')    # the earliest keyword, as the rule says


def test_same_position_goes_to_the_earlier_rule():
    assert parse('lunch delivery').activity == 'order_food'
    assert parse('food delivery').activity == 'order_food'
    assert parse('could we get food delivered?').activity == 'order_food'
    assert parse('video game').activity == 'play_console'
    assert parse('video games please').activity == 'play_console'


def test_sleep_yields_to_another_keyword():
    assert parse("I'm sleepy and hungry") == activity('eat')
    assert parse('sleep and eat') == activity('eat')
    assert parse('time for a nap') == activity('sleep')


def test_generic_play_verbs_count_only_without_a_strong_keyword():
    assert parse('gioca') == activity('play_console')
    assert parse('giochiamo?') == activity('play_console')
    assert parse('gioca a scacchi') == activity('play_chess')
    assert parse('gioca e mangia') == activity('eat')
    assert parse('fuori') == activity('park')
    assert parse('mangia fuori') == activity('eat')
    assert parse('fuori dalla finestra') == activity('window')
    assert parse('non mangiare fuori') == NEGATED


@pytest.mark.parametrize('text', [
    "don't sleep",
    "I really don't want to sleep",
    "I can't eat",
    'no chess',
    'senza mangiare',
    'non dormire',
    'non ho fame',
    'non dormire, gioca',
])
def test_negated_request_does_nothing(text):
    assert parse(text) == NEGATED


def test_a_clause_break_ends_a_negation():
    assert parse("don't sleep but eat") == activity('eat')
    assert parse("don't sleep. eat") == activity('eat')
    assert parse("don't go out and eat") == activity('eat')
    assert parse("don't open formo.family, play chess") == activity('play_chess')


def test_negated_link_is_not_opened():
    assert parse("don't open formo.family") == NEGATED
    assert parse("don't open https://example.com") == NEGATED


@pytest.mark.parametrize('text', [
    'are you hungry',
    'are you playing chess?',
    'r u playing chess',
    'sei pronto a giocare?',
    'stai giocando a scacchi?',
    'is https://example.com safe?',
])
def test_question_about_his_state_does_nothing(text):
    assert parse(text) == QUESTION


def test_question_without_a_keyword_is_no_match():
    assert parse('are you playing?') == NO_MATCH
    assert parse('what is your favourite colour') == NO_MATCH


@pytest.mark.parametrize('text, name', [
    ('can you play chess?', 'play_chess'),
    ('could you order a pizza?', 'order_food'),
    ('would you put on some music?', 'listen_music'),
    ('do you want to play chess?', 'play_chess'),
    ('what about the park?', 'park'),
    ('are you up for chess?', 'play_chess'),
    ('do you feel like a walk?', 'park'),
    ("let's play chess", 'play_chess'),
    ('vuoi giocare?', 'play_console'),
    ('ti va di mangiare?', 'eat'),
    ('chess?', 'play_chess'),
])
def test_request_marker_keeps_a_question_a_request(text, name):
    assert parse(text) == activity(name)


@pytest.mark.parametrize('text, url', [
    ('open formo.family', 'https://formo.family'),
    ('apri formo.family', 'https://formo.family'),
    ('visit formo.family', 'https://formo.family'),
    ('check formo.family', 'https://formo.family'),
    ('check out formo.family', 'https://formo.family'),
    ('go to formo.family', 'https://formo.family'),
    ('go on formo.family', 'https://formo.family'),
    ('navigate to formo.family', 'https://formo.family'),
    ('open up formo.family', 'https://formo.family'),
    ('look at formo.family', 'https://formo.family'),
    ('browse formo.family', 'https://formo.family'),
    ('guarda formo.family', 'https://formo.family'),
    ('vai su formo.family', 'https://formo.family'),
    ('vai a formo.family', 'https://formo.family'),
])
def test_bare_domain_after_an_opening_verb_gets_https(text, url):
    assert parse(text) == link(url)


def test_bare_domain_keeps_path_and_query_and_port():
    assert parse('guarda formo.family/a/b?x=1&y=2').url == 'https://formo.family/a/b?x=1&y=2'
    assert parse('open formo.family?x=1').url == 'https://formo.family?x=1'
    assert parse('open formo.family:8080/x').url == 'https://formo.family:8080/x'
    assert parse('visit example.com/a.').url == 'https://example.com/a'
    assert parse('open formo.family.').url == 'https://formo.family'


def test_code_names_and_abbreviations_are_never_links():
    for text in ('open life.py', 'check life.py', 'open config.json', 'check README.md', 'open main.go', 'open app.js'):
        assert parse(text) == NO_MATCH
    assert parse('look at e.g. the window') == activity('window')
    assert parse('visit i.e. the bakery') == activity('buy_bread')


def test_bare_domain_needs_an_opening_verb():
    assert parse('formo.family is cool') == NO_MATCH
    assert parse('is formo.family up?') == NO_MATCH


def test_plurals_match_their_activity():
    assert parse('play some games').activity == 'play_console'
    assert parse('check the videos').activity == 'watch_video'
    assert parse('take the walks').activity == 'park'


def test_mapped_activities_exist_in_life_and_reactions_fit():
    names = {name for name, _ in KEYWORD_RULES + WEAK_RULES}
    assert set(REACTIONS) == names
    assert names <= set(ACTIVITIES)
    lines = list(REACTIONS.values()) + [QUESTION_REACTION, NEGATED_REACTION] + [
        parse(t).reaction for t in ('', 'https://example.com', 'what is your favourite colour', "don't sleep")]
    assert all(0 < len(line) <= 60 for line in lines)


def test_impulse_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        parse('chess').kind = 'reply_only'
