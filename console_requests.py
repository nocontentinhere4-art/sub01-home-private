"""Named console suggestions; these are preferences, never immediate commands."""
import math
import re

GAMES = frozenset({'pong', 'minecraft'})
TTL = 3600

def game_music_context(text):
    return bool(isinstance(text, str) and re.search(r'\b(minecraft|pong)\b', text, re.I)
        and re.search(r'\b(music|song|soundtrack|theme|canzone|musica)\b', text, re.I))

def game_request(text):
    if not isinstance(text, str) or re.search(r'\b(music|song|soundtrack|theme|canzone|musica)\b', text, re.I):
        return None
    match = re.search(r'\b(?:play|try|start|gioca(?:re)?(?:\s+a)?|avvia)\s+(?:some\s+|a game of\s+)?(minecraft|pong)\b', text, re.I)
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
