"""Named console games asked for in the chat ("play pong", "switch to minecraft").

The name is a wish for which game the wall TV shows: life.py keeps the latest one for TTL
seconds and applies it when he next starts (or is asked to start) the console; the activity
itself comes from the chat impulse (impulse.py). A game that is not configured is never chosen.
"""
import math
import re

GAMES = frozenset({'pong', 'minecraft'})
TTL = 3600   # seconds a named game stays wished for (life.CONSOLE_WISH_TTL)
MUSIC_WORDS = r'\b(music|song|soundtrack|theme|canzone|musica)\b'
# "play X", "switch to X", "put on X", "gioca a X" ...: the verbs that name the game to show
REQUEST = re.compile(r'\b(?:play|try|start|launch|load|run|open|switch\s+to|put\s+on|gioca(?:re)?(?:\s+a)?|avvia|metti)'
                     r'\s+(?:some\s+|a game of\s+|a bit of\s+|the\s+|su\s+)?(minecraft|pong)\b', re.I)

def game_music_context(text):
    return bool(isinstance(text, str) and re.search(r'\b(minecraft|pong)\b', text, re.I)
        and re.search(MUSIC_WORDS, text, re.I))

def game_request(text):
    """The game a message asks for ('pong' | 'minecraft'), or None (a soundtrack request is music, not a game)."""
    if not isinstance(text, str) or re.search(MUSIC_WORDS, text, re.I):
        return None
    match = REQUEST.search(text)
    if not match:
        match = re.fullmatch(r'\s*(minecraft|pong)[.!?]*\s*', text, re.I)
    return match.group(1).lower() if match else None

def valid_choice(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not isinstance(value[0], str) or value[0] not in GAMES:
        return None
    when = value[1]
    if isinstance(when, bool) or not isinstance(when, (float, int)) or not math.isfinite(when):
        return None
    return (value[0], when)
