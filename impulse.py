"""Chat impulse: one chat message becomes one immediate, in-character step.

Pure, deterministic, stdlib only. This module never imports life, live_server or chat.
Every activity name below must exist in life.ACTIVITIES; tests/test_impulse.py checks that.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Impulse:
    kind: str             # 'activity' | 'open_url' | 'reply_only'
    activity: str | None  # a life.ACTIVITIES name, only when kind == 'activity'
    url: str | None       # only when kind == 'open_url'
    reaction: str         # one short in-character English line, at most 60 characters, shown at once
    why: str              # short reason for the life log


URL_RE = re.compile(r'https?://[^\s<>"\']+')
URL_TRAILING = '.,;)]'
URL_MAX = 2000
# a bare domain after an opening verb gets the https scheme: 'open formo.family' -> https://formo.family
BARE_DOMAIN_RE = re.compile(r'\b(?:open|visit|check|go to|look at|apri|vai su)\s+((?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>"\']*)?)',
                            re.IGNORECASE)

# keyword rules in priority order: the first activity with a whole-word match wins
KEYWORD_RULES = (
    ('use_computer', ('pc', 'computer', 'laptop')),
    ('research', ('research', 'look up', 'read about')),
    ('play_console', ('tv', 'console', 'game', 'pong', 'minecraft')),
    ('play_chess', ('chess',)),
    ('phone', ('phone', 'tiktok', 'scroll')),
    ('listen_music', ('music', 'song', 'headphones')),
    ('watch_video', ('video', 'youtube')),
    ('eat', ('eat', 'hungry', 'lunch', 'dinner', 'breakfast')),
    ('order_food', ('order', 'delivery', 'deliver')),
    ('buy_bread', ('bakery', 'bread')),
    ('buy_konbini', ('konbini', 'convenience store')),
    ('park', ('park', 'go out', 'outside', 'walk')),
    ('window', ('window',)),
    ('sleep', ('sleep', 'bed', 'nap')),
    ('use_bathroom', ('bathroom', 'toilet', 'shower')),
    ('chat', ('reply', 'answer')),
)

REACTIONS = {
    'use_computer': 'Sure, heading to the computer.',
    'research': 'Good question. Let me look into it.',
    'play_console': 'Sure, the TV it is. Grabbing the controller.',
    'play_chess': 'Chess, yes. Setting up the board now.',
    'phone': 'Okay, checking my phone.',
    'listen_music': 'Music, yes. Let me pick something.',
    'watch_video': 'A video, sure. Let me find one.',
    'eat': 'Good idea. Bread at the table, then.',
    'order_food': 'Okay, ordering something on the phone.',
    'buy_bread': 'Bakery run. Back in a few minutes.',
    'buy_konbini': 'Konbini it is. Be right back.',
    'park': 'The park sounds nice. Heading out.',
    'window': 'Okay, I will look out the window.',
    'sleep': 'Okay, bed. Good night.',
    'use_bathroom': 'One sec, heading to the bathroom.',
    'chat': 'Okay, I will answer at the computer.',
}


def _whole_words(words):
    """One case-insensitive pattern: any word or phrase as a whole word. A single word also matches its plural (-s, -es);
    spaces in a phrase match any whitespace run."""
    parts = [word.replace(' ', r'\s+') if ' ' in word else word + r'(?:e?s)?' for word in words]
    return re.compile(r'\b(?:' + '|'.join(parts) + r')\b', re.IGNORECASE)


RULE_PATTERNS = tuple((activity, _whole_words(words)) for activity, words in KEYWORD_RULES)


def _first_url(text):
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(URL_TRAILING)[:URL_MAX]
        if not url.endswith('://'):  # nothing left after the scheme
            return url
    bare = BARE_DOMAIN_RE.search(text)
    if bare:
        return ('https://' + bare.group(1).rstrip(URL_TRAILING))[:URL_MAX]
    return None


def parse(text: str) -> Impulse:
    if not text or not text.strip():
        return Impulse('reply_only', None, None, 'Hm? Say that again.', 'empty message')
    url = _first_url(text)
    if url:
        return Impulse('open_url', None, url, 'On it, let me open that.', 'a link was sent')
    for activity, pattern in RULE_PATTERNS:
        if pattern.search(text):
            return Impulse('activity', activity, None, REACTIONS[activity], f'asked in chat: {activity}')
    return Impulse('reply_only', None, None, 'Not doing that one. Ask me something else.', 'no action matched')
