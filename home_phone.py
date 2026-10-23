"""Owned phone apps drawn from actual HomeWorld state, never browser substitutes."""
import hashlib
import io
import json
import textwrap

APPS = ('home', 'notes', 'memory', 'browser')
WIDTH, HEIGHT = 256, 512


def snapshot(home, browser=None):
    app = home.phone.get('app', 'home')
    if app not in APPS:
        app = 'home'
    data = {'app': app, 'battery': home.phone.get('battery', 100),
            'selection_revision': getattr(home, 'phone_selection_revision', 0)}
    if app == 'notes':
        notes = home.notes[-10:][::-1]
        data['entries'] = [str(n.get('text', '')) for n in notes]
        # Stable real record identities invalidate writes even when visible text repeats.
        data['entry_revisions'] = [[n.get('id'), n.get('at')] for n in notes]
    elif app == 'memory':
        data['entries'] = [str(m.get('command') or m.get('what') or
                              f"{m.get('activity', '')} · {m.get('place', '')}") for m in home.memories[-20:]]
    elif app == 'browser':
        data['browser'] = browser or None
    return data


def status(data):
    browser = data.get('browser')
    real = (data['app'] == 'browser' and browser and not browser.get('restarting')
            and isinstance(browser.get('frame_id'), str) and 1 <= len(browser['frame_id']) <= 100)
    identity = ({'app': 'browser', 'selection_revision': data.get('selection_revision', 0),
                 'browser_frame_id': browser['frame_id']} if real else
                {k:v for k,v in data.items() if k != 'browser'})
    raw = json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()
    tag = hashlib.sha256(raw).hexdigest()[:24]
    return {'device': 'phone', 'app': data['app'], 'frame_id': tag,
            'width': browser.get('width', WIDTH) if real else WIDTH,
            'height': browser.get('height', HEIGHT) if real else HEIGHT,
            'kind': 'browser' if real else 'owned_app', 'available': True}


def render(data):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (WIDTH, HEIGHT), '#101b2b')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=12)
    draw.text((16, 15), 'SUB01', font=small, fill='#a9bdcf')
    draw.text((184, 15), f"{data['battery']}%", font=small, fill='#a9bdcf')
    title = {'home':'Home', 'notes':'Notes', 'memory':'Memory', 'browser':'Browser'}[data['app']]
    draw.text((16, 54), title, font=font, fill='white')
    y = 96
    if data['app'] == 'notes':
        draw.rounded_rectangle((16, 87, 240, 121), radius=6, fill='#26435b')
        draw.text((28, 96), '+ Add note', font=small, fill='white')
        y = 145
    lines = ['Notes', 'Memory', 'Browser'] if data['app'] == 'home' else data.get('entries', [])
    if data['app'] in ('notes', 'memory') and not lines:
        lines = ['No saved notes.' if data['app']=='notes' else 'No recorded memories.']
    if data['app'] == 'browser':
        lines = ['Browser unavailable.', 'No browser content is being shown.']
    for entry in lines:
        for line in textwrap.wrap(entry, width=27)[:7]:
            if y > 448: break
            draw.text((16, y), line, font=small, fill='#e0eaf2'); y += 19
        y += 14
        if y > 448: break
    draw.line((16, 473, 240, 473), fill='#314458')
    draw.text((16, 487), 'Home  ·  Private phone', font=small, fill='#a9bdcf')
    out = io.BytesIO(); image.save(out, format='JPEG', quality=90)
    return out.getvalue()


# --- the phone while his life has it in hand ----------------------------------------------------------------------------
# life_view decides what the phone shows, from life.snapshot() (activity, phone, walking, order, courier) and the phone's
# browser screen. The pages only draw the view they are given: room_phone.js (the classic room) and
# web/house/phone_screen.mjs (the house page), from /api/home's phone_view.
CHAT_LINES = 8                       # the newest lines on the chat app: viewers' messages, his replies and his reactions
LINE_MAX = 200                       # characters of one line (a viewer's message is already at most that)
REPLY_CUT = 60                       # the viewer's words a reply answers, cut as the room's chat feed cuts them
TAG_VIEWER = 'a viewer'
TAG_REACTION = 'his reaction (a fixed line)'      # impulse.REACTIONS: canned lines, not written by the AI
REPLY_TAGS = ('his reply (AI-written)', 'a note from the room, not his words')   # the only tags a reply may carry
ORDER_STEPS = ('order placed', 'being prepared', 'courier on the way', 'delivered')
COURIER_STEP = {'being prepared': 1, 'on the way': 2, 'at the door': 2}
NO_SHORT = 'no short video can show right now'
LIFE_RANK = {'viewer': 0, 'reaction': 1, 'reply': 2}


def _line_text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def chat_lines(viewer=(), replies=(), reactions=()):
    """The chat app's lines in time order (HH:MM; on a tie a viewer's message, then a reaction, then a reply), each
    {kind, t, who, text, re}. viewer: public(m) dicts {t, text}; replies: his reply records {t, text, replying_to, tag};
    reactions: SUB-01's reaction lines {t, text}. Nicknames, ids, networks and emotions are never kept."""
    out = []
    for x in viewer or ():
        text = _line_text(x.get('text'), LINE_MAX) if isinstance(x, dict) else ''
        if text:
            out.append({'kind': 'viewer', 't': str(x.get('t') or '')[:5], 'who': TAG_VIEWER, 'text': text, 're': ''})
    for x in reactions or ():
        text = _line_text(x.get('text'), LINE_MAX) if isinstance(x, dict) else ''
        if text:
            out.append({'kind': 'reaction', 't': str(x.get('t') or '')[:5], 'who': TAG_REACTION, 'text': text, 're': ''})
    for x in replies or ():
        text = _line_text(x.get('text'), LINE_MAX) if isinstance(x, dict) else ''
        if text:
            tag = x.get('tag') if x.get('tag') in REPLY_TAGS else REPLY_TAGS[0]
            answers = _line_text(x.get('replying_to'), LINE_MAX)          # the viewer's words it answers, cut as the room cuts
            if len(answers) > REPLY_CUT:
                answers = answers[:REPLY_CUT - 2] + '…'
            out.append({'kind': 'reply', 't': str(x.get('t') or '')[:5], 'who': tag, 'text': text, 're': answers})
    out.sort(key=lambda x: (x['t'], LIFE_RANK[x['kind']]))
    return out


def chat_view(lines=(), why=''):
    """The chat app: its newest CHAT_LINES lines, and why it is shown in place of a short video when that is the case."""
    rows = []
    for x in list(lines or ())[-CHAT_LINES:]:
        if not isinstance(x, dict) or not x.get('text'):
            continue
        kind = x.get('kind') if x.get('kind') in LIFE_RANK else 'viewer'   # an unknown line is a viewer's, never his
        # the tag is fixed for a viewer and a reaction; a reply keeps only one of the tags a reply may carry
        who = {'viewer': TAG_VIEWER, 'reaction': TAG_REACTION}.get(kind) or (
            x.get('who') if x.get('who') in REPLY_TAGS else REPLY_TAGS[0])
        rows.append({'kind': kind, 't': str(x.get('t') or ''), 'who': who,
                     'text': str(x.get('text')), 're': str(x.get('re') or '')})
    return {'app': 'chat', 'lines': rows, 'why': str(why or '')[:80]}


def order_view(life):
    """The order app while he orders: the courier's status (life.courier) once a delivery is on its way, else choosing."""
    c = life.get('courier') if isinstance(life.get('courier'), dict) else None
    dish = _line_text((c or {}).get('dish') or life.get('order'), 40)
    if c is None:
        return {'app': 'order', 'dish': dish, 'status': 'choosing what to eat', 'eta_min': None, 'step': 0,
                'steps': list(ORDER_STEPS)}
    status = _line_text(c.get('status'), 40)
    try:
        eta = None if isinstance(c.get('eta_min'), bool) else max(0, int(c.get('eta_min')))
    except (TypeError, ValueError, OverflowError):
        eta = None
    return {'app': 'order', 'dish': dish, 'status': status, 'eta_min': eta,
            'step': COURIER_STEP.get(status, 1), 'steps': list(ORDER_STEPS)}


def life_view(life, screen=None, lines=(), now=None):
    """What the phone shows for his life right now, decided here and only here:
    - order_food: the order app, with the courier's status while it is on its way (order_view);
    - phone (life.phone 'chat' or 'tiktok') and not walking: the browser's short video when phone_app is 'tiktok' and the
      phone's screen really shows one (short_videos.shows_short) - {'app': 'short'}, the page draws the browser frame;
      otherwise the chat app with the latest public lines. A 'tiktok' phone with no short showing says so (NO_SHORT):
      no browser, a restart, no clip, a refused title, a stalled feed or a page that is not a short. So the glass is
      never blank while he holds the phone;
    - anything else, or walking (the phone is not in his hand): None, and the pages keep their own idle screen.
    now: the wall-clock time for the stalled-feed check (time.time() when None)."""
    if not isinstance(life, dict) or life.get('walking'):
        return None
    activity = life.get('activity')
    if activity == 'order_food':
        return order_view(life)
    if activity == 'phone' and life.get('phone') in ('chat', 'tiktok'):
        import short_videos                              # lazy: the house's own imports stay light
        if life['phone'] == 'tiktok' and short_videos.shows_short(screen, now):
            return {'app': 'short'}
        return chat_view(lines, NO_SHORT if life['phone'] == 'tiktok' else '')
    return None


def view_of(live, life, screen=None):
    """life_view for a live server, built the same way for the brain tick and /api/home: its public chat lines, his
    replies and SUB-01's reactions (the last CHAT_LINES of each). None unless his phone or his order is in hand."""
    if not isinstance(life, dict) or life.get('activity') not in ('phone', 'order_food'):
        return None
    memory, public = getattr(live, 'memory', None), getattr(live, 'public', None)
    try:
        viewer = [public(m) for m in memory.chat()[-CHAT_LINES:]] if memory is not None and public is not None else []
    except (KeyError, TypeError, ValueError):       # a stored line missing a field is not shown; the brain loop goes on
        viewer = []
    lines = chat_lines(viewer=viewer, replies=list(getattr(live, 'replies', None) or [])[-CHAT_LINES:],
                       reactions=list(getattr(live, 'sub01_reactions', None) or [])[-CHAT_LINES:])
    return life_view(life, screen, lines)
