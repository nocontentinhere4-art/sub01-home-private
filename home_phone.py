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
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    tag = hashlib.sha256(raw).hexdigest()[:24]
    browser = data.get('browser')
    real = data['app'] == 'browser' and browser and browser.get('frame_id')
    return {'device': 'phone', 'app': data['app'], 'frame_id': browser['frame_id'] if real else tag,
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
