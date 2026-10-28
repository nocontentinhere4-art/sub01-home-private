"""Chat impulse: one chat message becomes one immediate, in-character step.

Pure, deterministic, stdlib only. This module never imports life, live_server or chat.
Every activity name below must exist in life.ACTIVITIES; tests/test_impulse.py checks that.

parse() decides in this order:
1. Links win over keywords, wherever they stand. A link is a full http(s) URL, or a bare domain after an opening
   verb ('open formo.family'). A bare domain must end in a known TLD, so 'life.py' and 'e.g.' are never links.
2. Keywords win by position. Each whole word or phrase in KEYWORD_RULES (English or Italian) counts where it stands,
   and the earliest one wins: 'order lunch' -> order_food, 'go to the park and eat' -> park. Two keywords at the
   same position: the rule earlier in KEYWORD_RULES wins ('lunch delivery' -> order_food).
   WEAK_RULES (generic play verbs such as 'gioca', and 'fuori') count only when the message matches no
   KEYWORD_RULES word at all: 'gioca a scacchi' is play_chess, 'mangia fuori' is eat.
   Sleep is never carried out from chat (life ignores it), so a sleep word yields to any other live keyword:
   "I'm sleepy and hungry" is eat.
3. Negation: a keyword or link is skipped when a negation word ('don't', 'non', 'senza') stands before it in the same
   clause (no comma, full stop, 'and', 'but', 'then', 'e', 'ma', 'poi' or 'quindi' in between) and within
   NEG_WINDOW words. 'don't sleep' does nothing; 'don't go out and eat' eats.
4. Questions: a question about his state ('are you playing?', 'sei pronto?') turns the action into a reply.
   A request marker ('can you', 'please', 'puoi', 'vuoi', "let's") makes it a request. A bare 'chess?' is a request.
5. Nothing left: a skipped keyword or link gets NEGATED_REACTION; no keyword or link at all gets the default reply.
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


def _phrase(word, plural=True):
    """A word or phrase as a regex: spaces match any whitespace run; the last word takes an optional -s or -es."""
    *head, last = word.split()
    parts = [re.escape(w) for w in head]
    parts.append(re.escape(last) + (r'(?:e?s)?' if plural else ''))
    return r'\s+'.join(parts)


def _alternation(words, plural=True):
    """Longer phrases first, so 'open up' is tried before 'open'."""
    return '|'.join(_phrase(w, plural) for w in sorted(words, key=len, reverse=True))


def _whole_words(words):
    """One case-insensitive pattern: any listed word or phrase as a whole word."""
    return re.compile(r'\b(?:' + _alternation(words) + r')\b', re.IGNORECASE)


URL_RE = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
URL_TRAILING = '.,;:!?)]'   # sentence punctuation after a link is not part of the link
URL_MAX = 2000
# a bare domain must end in one of these: the top-level domains chat.py also treats as links; 'life.py' is not one
TLDS = ('com', 'net', 'org', 'edu', 'gov', 'io', 'ai', 'co', 'me', 'ly', 'to', 'xyz', 'fun', 'app', 'gg', 'sol', 'ru',
        'info', 'biz', 'link', 'site', 'online', 'club', 'finance', 'exchange', 'money', 'pro', 'tech', 'dev', 'family',
        'news', 'blog', 'world', 'tv', 'cc', 'it', 'uk', 'jp', 'de', 'fr', 'es', 'eu', 'us', 'ca', 'au', 'nl', 'ch')
# an opening verb, then a bare domain: 'open formo.family' -> https://formo.family
BARE_VERBS = ('open up', 'open', 'visit', 'check out', 'check', 'go to', 'go on', 'look at', 'browse', 'navigate to',
              'guarda', 'apri', 'visita', 'vai su', 'vai a', 'controlla')
BARE_DOMAIN_RE = re.compile(
    r'\b(?:' + _alternation(BARE_VERBS) + r')\s+'
    r'((?:[a-z0-9-]+\.)+(?:' + _alternation(TLDS, plural=False) + r')\b(?::\d{1,5})?(?:[/?#][^\s<>"\']*)?)',
    re.IGNORECASE)

# keyword rules in priority order: at one position the earlier rule wins (see the module docstring)
KEYWORD_RULES = (
    ('use_computer', ('pc', 'computer', 'laptop', 'desktop', 'portatile')),
    ('research', ('research', 'search', 'google', 'look up', 'look into', 'read about', 'learn about', 'find out',
                  'cerca', 'cerco', 'cercare', 'ricerca', 'ricercare', 'informati', 'informarti', 'leggi su')),
    ('play_console', ('tv', 'televisore', 'televisione', 'console', 'playstation', 'ps4', 'ps5', 'xbox', 'controller',
                      'gaming', 'gamer', 'game', 'pong', 'minecraft', 'videogame', 'video game', 'videogioco',
                      'videogiochi')),
    ('play_chess', ('chess', 'checkmate', 'scacchi', 'scacchiera', 'scacco')),
    ('phone', ('phone', 'cellphone', 'smartphone', 'telefono', 'telefonino', 'cellulare', 'sms', 'tiktok', 'instagram',
               'scroll', 'scrolling', 'scrolla', 'scrollare', 'text me', 'text him', 'text her', 'text them',
               'texting', 'send a text', 'send me a text', 'send a message', 'send me a message', 'message me',
               'message him', 'message her', 'manda un messaggio', 'mandami un messaggio', 'manda un sms',
               'mandami un sms', 'scrivimi', 'scrivi un messaggio')),
    ('listen_music', ('music', 'musica', 'song', 'canzone', 'canzoni', 'headphones', 'earphones', 'earbuds', 'cuffie',
                      'spotify', 'playlist')),
    ('watch_video', ('video', 'youtube', 'clip', 'movie', 'film', 'filmato', 'filmati')),
    ('order_food', ('order', 'ordina', 'ordino', 'ordinare', 'ordini', 'delivery', 'deliver', 'delivered', 'delivering',
                    'takeaway', 'takeout', 'food delivery', 'food delivered', 'meal delivery', 'meal delivered',
                    'lunch delivery', 'lunch delivered', 'dinner delivery', 'dinner delivered', 'breakfast delivery',
                    'consegna', 'consegne', 'consegnare', 'domicilio')),
    ('eat', ('eat', 'eating', 'food', 'meal', 'snack', 'hungry', 'starving', 'lunch', 'dinner', 'breakfast',
             'mangia', 'mangiare', 'mangi', 'mangio', 'mangiamo', 'fame', 'affamato', 'affamata', 'pranzo',
             'pranziamo', 'pranzare', 'cena', 'ceno', 'ceniamo', 'cenare', 'colazione', 'spuntino', 'merenda')),
    ('buy_bread', ('bread', 'bakery', 'baker', 'pane', 'panetteria', 'panetterie', 'panificio', 'fornaio', 'fornaia',
                   'panettiere')),
    ('buy_konbini', ('konbini', 'convenience store', 'corner shop', 'shop', 'store', 'negozio', 'negozi',
                     'minimarket')),
    ('park', ('park', 'walk', 'stroll', 'go out', 'going out', 'go outside', 'going outside', 'step outside',
              'get outside', 'outdoors', 'parco', 'parchi', 'esci', 'esco', 'uscire', 'passeggiata', 'passeggiare',
              'passeggio', 'camminare', 'cammina', 'camminata', 'fuori casa', 'vai fuori', 'andare fuori',
              'andiamo fuori')),
    ('window', ('window', 'look outside', 'finestra', 'guarda fuori', 'guardare fuori')),
    ('sleep', ('sleep', 'sleeping', 'sleepy', 'bed', 'bedtime', 'nap', 'dormi', 'dormire', 'dormo', 'dormiamo', 'nanna',
               'sonno', 'sonnellino', 'pisolino', 'assonnato', 'addormentarsi', 'a letto', 'in letto', 'nel letto')),
    ('use_bathroom', ('bathroom', 'toilet', 'loo', 'restroom', 'washroom', 'shower', 'bagno', 'bagni', 'doccia',
                      'docce', 'gabinetto', 'toilette', 'wc')),
    ('chat', ('reply', 'answer', 'respond', 'rispondi', 'rispondo', 'rispondere', 'rispondimi')),
)
# generic play verbs and 'fuori': used only when no KEYWORD_RULES word matches the message at all
WEAK_RULES = (
    ('play_console', ('gioca', 'giocare', 'giochiamo', 'giochi')),
    ('park', ('fuori',)),
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
    'sleep': 'I sleep when my body says so.',
    'use_bathroom': 'One sec, heading to the bathroom.',
    'chat': 'Okay, I will answer at the computer.',
}
QUESTION_REACTION = 'Good question. I will answer at the computer.'
NEGATED_REACTION = 'Okay, I will not do that one.'

NEG_WINDOW = 4          # words before a keyword that a negation may stand in
NEGATIONS = frozenset((
    'not', 'no', 'never', 'nope', 'without', "don't", 'dont', "doesn't", 'doesnt', "didn't", 'didnt', "won't", 'wont',
    "can't", 'cant', 'cannot', 'non', 'mai', 'niente', 'nessun', 'nessuno', 'nessuna', 'senza', 'basta', 'smetti',
    'neanche', 'neppure'))
CLAUSE_BREAKS = frozenset(('.', ',', ';', ':', '!', '?', 'and', 'but', 'then', 'e', 'ma', 'poi', 'quindi'))
WORD_RE = re.compile(r"[\w']+|[.,;:!?]")
# a question about his state: 'are you ...', 'sei ...?', 'è ...?'; a bare 'chess?' is not one
QUESTION_START_RE = re.compile(
    r"^\W*(?:(?:are|is|am|was|were|do|does|did|what|why|when|where|who|which|sei|stai|sta|sono|hai|quando|perché"
    r"|perche|dove|chi|cosa)\b|(?:è|e'|c'è|c'e')(?=\s|$))", re.IGNORECASE)
QUESTION_YOU_RE = re.compile(r"^\W*(?:are|r|do|does|did|have|has|sei|stai|hai)\s+(?:you|u|ya|tu)\b", re.IGNORECASE)
# a request even when it is phrased as a question
REQUEST_RE = re.compile(
    r"\b(?:(?:can|could|would|will|may)\s+(?:you|u|ya)|please|pls|plz|wanna|want\s+(?:to|you\s+to)|let'?s"
    r"|shall\s+we|what\s+about|how\s+about|feel\s+like|fancy|up\s+for|in\s+the\s+mood"
    r"|puoi|potresti|potrebbe|vuoi|ti\s+va|vorrei|facciamo|andiamo)\b",
    re.IGNORECASE)

RULE_PATTERNS = tuple((activity, _whole_words(words)) for activity, words in KEYWORD_RULES)
WEAK_PATTERNS = tuple((activity, _whole_words(words)) for activity, words in WEAK_RULES)


def _clean(url):
    return url.rstrip(URL_TRAILING)[:URL_MAX]


def _links(text):
    """Every link as (start, url), in text order. A full URL keeps its scheme; a bare domain gets https."""
    found = []
    for match in URL_RE.finditer(text):
        url = _clean(match.group(0))
        if not url.endswith('://'):      # nothing after the scheme
            found.append((match.start(), url))
    for match in BARE_DOMAIN_RE.finditer(text):
        found.append((match.start(), _clean('https://' + match.group(1))))
    return sorted(found)


def _hits(text, patterns):
    """Every keyword match as (start, rule rank, activity), by start; at one start the earlier rule comes first."""
    return sorted((m.start(), rank, activity)
                  for rank, (activity, pattern) in enumerate(patterns) for m in pattern.finditer(text))


def _negated(text, pos):
    """True when a negation word stands before pos in the same clause, within NEG_WINDOW words."""
    for word in reversed(WORD_RE.findall(text[:pos].lower())[-NEG_WINDOW:]):
        if word in NEGATIONS:
            return True
        if word in CLAUSE_BREAKS:
            return False
    return False


def _is_question(text):
    """A question about his state, not a request: a request marker anywhere makes it a request."""
    if REQUEST_RE.search(text):
        return False
    return bool(QUESTION_YOU_RE.match(text) or (QUESTION_START_RE.match(text) and '?' in text))


def parse(text: str) -> Impulse:
    if not text or not text.strip():
        return Impulse('reply_only', None, None, 'Hm? Say that again.', 'empty message')
    text = text.replace('’', "'")
    links = _links(text)
    strong = _hits(text, RULE_PATTERNS)
    weak = [] if strong else _hits(text, WEAK_PATTERNS)    # weak words only when no strong keyword matches at all
    live_links = [url for pos, url in links if not _negated(text, pos)]
    live_strong = [activity for pos, _, activity in strong if not _negated(text, pos)]
    live_weak = [activity for pos, _, activity in weak if not _negated(text, pos)]
    if live_links or live_strong or live_weak:
        if _is_question(text):
            return Impulse('reply_only', None, None, QUESTION_REACTION, 'a question, no action')
        if live_links:
            return Impulse('open_url', None, live_links[0], 'On it, let me open that.', 'a link was sent')
        # sleep is never carried out from chat (life ignores it), so any other live keyword takes its place
        awake = [name for name in live_strong if name != 'sleep']
        activity = (awake or live_strong or live_weak)[0]
        return Impulse('activity', activity, None, REACTIONS[activity], f'asked in chat: {activity}')
    if links or strong or weak:
        return Impulse('reply_only', None, None, NEGATED_REACTION, 'a negated request, no action')
    return Impulse('reply_only', None, None, 'Not doing that one. Ask me something else.', 'no action matched')
