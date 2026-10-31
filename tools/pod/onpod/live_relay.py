"""Temporary public viewer relay. No operator routes, credentials, or generic proxy."""
import argparse, asyncio, collections, hashlib, io, json, os, re, time
from pathlib import Path
import aiohttp
from aiohttp import web
from PIL import Image
ORIGIN = 'https://subzerone.live'
LIVE_KEEP, START_OFFSET = 4, 2.0      # public playlist: newest 4 segments (8 s), start 2 s from the live edge (owner 10-28; 10-31 "correggi tutti i ritardi": 4 -> 2 s)
CARTOON = re.compile(r'^\W{0,2}(?:!\s*cartoon\b|cartoon\s*:)', re.I)   # the agent's CARTOON_PREFIX: sent straight to it
SEGMENT = re.compile(r'^sub01-[0-9]{8}-[0-9]{6}-[0-9]+\.ts$')
NICK = re.compile(r'[A-Za-z0-9_.-]{2,16}')          # owner 10-28: self-chosen names (unverified, greetings only)
RESERVED = set('sub01 sub-01 sub_01 subzerone owner admin administrator mod moderator streamer system viewer anon anonymous staff support official bot'.split())
VOTER_SALT = os.urandom(16)          # owner 10-28 trading votes: one vote per connection, the IP itself never leaves here
def voter_key(ip):
    return hashlib.sha256(VOTER_SALT + str(ip).encode()).hexdigest()[:16]
VIEWER_WINDOW_S = 70.0   # owner 10-29 "show how many are online": a page polls /status every 5 s (a background tab ~1/min)
QUEUE_WHY = {'added':'Added to the queue.', 'bad_link':'Only YouTube video links (youtube.com/watch, youtu.be, shorts).',
             'duplicate':'That video is already in the queue or was just played.', 'full':'The queue is full. Try again later.',
             'per_name':'You already have two videos waiting.'}

def clean_nick(raw):
    nick = str(raw or '').strip()
    return nick if NICK.fullmatch(nick) and nick.lower() not in RESERVED and nick.lower().strip('._-') not in RESERVED else ''

def body_json(text):
    """A text/plain body that is a small JSON object, or None (plain chat text stays plain)."""
    if not text.startswith('{'): return None
    try: d = json.loads(text)
    except ValueError: return None
    return d if isinstance(d, dict) else None

HEADERS = {'Access-Control-Allow-Origin': ORIGIN, 'Vary': 'Origin', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
# owner 10-29 avatars phase 1: the Simli avatar page and its calls (list, session, say, submit), forwarded to
# avatar_service.py (loopback); the page is served here, so its own origin is accepted on /avatar paths only
AVATAR_PAGE = Path(__file__).with_name('avatar.html')
AVATAR_VOICES = Path(__file__).with_name('avatar-voices')     # short previews of the avatar voices
VOICE_PREVIEW = re.compile(r'[a-z]{2,12}\.mp3')
AVATAR_SERVICE = 'http://127.0.0.1:8843'
AVATAR_SUBMIT_MAX = 4_300_000      # a base64 photo of up to 3 MB plus its fields (the page shrinks photos first)

def chat_ack_response(data):
    ok = data.get('ok') is True
    reason = str(data.get('reason') or '')
    if ok: code, why, status = 'received', 'Message received.', 200
    elif reason == 'duplicate': code, why, status = 'duplicate', 'This message was already received. Try a different message.', 409
    elif reason.startswith('one message every ') or 'busy' in reason.lower():
        code, why, status = 'rate_limited', 'Chat is busy. Please wait 10 seconds and try again.', 429
    else: code, why, status = 'filtered', 'Message rejected by the chat filter.', 400
    return web.json_response({'ok':ok, 'code':code, 'why':why}, status=status)

def create_app(root, stop_file, token_file=None):
    root = Path(root).resolve()
    messages = collections.deque(maxlen=30)
    rates = collections.OrderedDict()
    global_chat = collections.deque()
    slots = asyncio.Semaphore(8)
    screen_task = None
    screen_jpg_task = None
    screen_jpg_cache = None
    online = collections.OrderedDict()   # connection hash -> last /status poll (salted hashes only, never an IP)
    def count_online(ip):
        now = time.monotonic(); key = voter_key(ip)
        online[key] = now; online.move_to_end(key)
        while online and (now - next(iter(online.values())) > VIEWER_WINDOW_S or len(online) > 5000): online.popitem(last=False)
        return len(online)
    viewer_cache = {'t': -1e9, 'data': {'queue': {'now': None, 'waiting': []}, 'hype': {'level': 0, 'train': False}}}
    async def agent_call(method, path, payload=None, timeout=6):
        """The agent's API with the operator token (never sent to browsers). -> (status, json) or (None, None)."""
        if not token_file: return None, None
        try:
            async with asyncio.timeout(timeout):
                async with aiohttp.ClientSession() as client:
                    async with client.request(method, 'http://127.0.0.1:8836' + path, json=payload,
                                              headers={'X-Admin-Token':Path(token_file).read_text().strip()}) as r:
                        return r.status, await r.json()
        except (TimeoutError, aiohttp.ClientError, ValueError, OSError): return None, None
    async def viewer_state():
        now = time.monotonic()
        if now - viewer_cache['t'] > 3:
            viewer_cache['t'] = now
            status, data = await agent_call('GET', '/viewer_state', timeout=2)
            if status == 200 and isinstance(data, dict): viewer_cache['data'] = {'queue': data.get('queue'), 'hype': data.get('hype')}
        return viewer_cache['data']
    def limited(ip, kind, period, maximum):
        now = time.monotonic(); key = (ip, kind)
        q = rates.setdefault(key, collections.deque()); rates.move_to_end(key)
        while q and q[0] < now-period: q.popleft()
        while len(rates) > 2048: rates.popitem(last=False)
        if len(q) >= maximum: return True
        q.append(now); return False
    @web.middleware
    async def boundary(request, handler):
        origin = request.headers.get('Origin')
        if origin not in (None, ORIGIN) and not (request.path.startswith('/avatar') and origin == 'https://' + request.host):
            return web.Response(status=403, text='Origin refused')
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        if request.path != '/screen.jpg' and (limited(ip, 'all', 10, 120) or limited('global', 'all', 1, 100)):
            return web.Response(status=429, text='Please wait', headers=HEADERS)
        try: response = await handler(request)
        except web.HTTPException as exc: response = web.Response(status=exc.status, text='Unavailable')
        response.headers.update(HEADERS)
        return response
    def trim_live(raw, keep=LIVE_KEEP):
        """The public playlist keeps only the newest `keep` segments and asks players to start START_OFFSET s from
        the live edge (owner 10-28: viewers drifted 1-2 min behind; a player that falls further behind gets 404 for
        a dropped segment and re-syncs to live). The director's own playlist and segments are untouched."""
        head, entries, cur = [], [], []
        for line in raw.splitlines():
            if not entries and not cur and line.startswith('#') and not line.startswith(('#EXTINF', '#EXT-X-PROGRAM-DATE-TIME', '#EXT-X-DISCONTINUITY')):
                head.append(line); continue
            cur.append(line)
            if line.strip() and not line.startswith('#'):
                entries.append(cur); cur = []
        drop = max(0, len(entries) - keep)
        if drop and any(l.startswith('#EXT-X-DISCONTINUITY') for e in entries[:drop] for l in e): return raw, {e[-1].strip() for e in entries}
        kept = entries[drop:]
        out = []
        for line in head:
            if line.startswith('#EXT-X-MEDIA-SEQUENCE:'):
                try: line = f'#EXT-X-MEDIA-SEQUENCE:{int(line.split(":", 1)[1]) + drop}'
                except ValueError: return raw, {e[-1].strip() for e in entries}
            out.append(line)
        out.append(f'#EXT-X-START:TIME-OFFSET=-{START_OFFSET:g}')
        for e in kept: out.extend(e)
        out.extend(cur)
        return '\n'.join(out) + '\n', {e[-1].strip() for e in kept}
    def playlist():
        p = root/'live.m3u8'
        if not p.is_file() or time.time()-p.stat().st_mtime > 20: return None, set()
        raw = p.read_text()
        if len(raw) > 65536: return None, set()
        names = {line.strip() for line in raw.splitlines() if line.strip() and not line.startswith('#')}
        if not names or not all(SEGMENT.fullmatch(n) for n in names): return None, set()
        return trim_live(raw)
    async def media(request):
        if '%' in request.raw_path or request.query_string: raise web.HTTPNotFound()
        name = request.match_info['name']; raw, names = playlist()
        if raw is None: return web.Response(status=503, text='Stream offline')
        if name == 'live.m3u8': return web.Response(text=raw, content_type='application/vnd.apple.mpegurl')
        # Only currently referenced media; neither arbitrary files nor paths are accepted.
        if name not in names or not SEGMENT.fullmatch(name): raise web.HTTPNotFound()
        p = root/name
        if p.is_symlink() or p.resolve().parent != root or not p.is_file(): raise web.HTTPNotFound()
        if p.stat().st_size > 32*1024*1024: raise web.HTTPServiceUnavailable()
        async with slots:
            data = await asyncio.to_thread(p.read_bytes)
        return web.Response(body=data, content_type='video/mp2t')
    async def capture_screen():
        try:
            token = Path(token_file).read_text().strip()
            async with asyncio.timeout(3):
                async with aiohttp.ClientSession() as client:
                    async with client.get('http://127.0.0.1:8838/pc/frame.png',
                            headers={'X-Admin-Token':token}, allow_redirects=False) as r:
                        if r.status != 200 or r.content_type != 'image/png': raise web.HTTPServiceUnavailable()
                        data = bytearray()
                        async for chunk in r.content.iter_chunked(65536):
                            data.extend(chunk)
                            if len(data) > 4*1024*1024: raise web.HTTPServiceUnavailable()
                        if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise web.HTTPServiceUnavailable()
                        return bytes(data)
        except (TimeoutError, aiohttp.ClientError, OSError, ValueError):
            raise web.HTTPServiceUnavailable()
    def transcode_screen(data):
        with Image.open(io.BytesIO(data)) as source:
            image = source.convert('RGB').resize((960, 540), Image.BILINEAR)
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=70)
            return output.getvalue()
    async def capture_screen_jpg():
        nonlocal screen_jpg_cache
        cached = screen_jpg_cache
        try:
            token = Path(token_file).read_text().strip()
            headers = {'X-Admin-Token':token}
            if cached is not None and cached[1]: headers['If-None-Match'] = cached[1]
            async with asyncio.timeout(3):
                async with aiohttp.ClientSession() as client:
                    async with client.get('http://127.0.0.1:8838/pc/frame.png',
                            headers=headers, allow_redirects=False) as r:
                        if r.status == 304 and cached is not None:
                            screen_jpg_cache = (cached[0], cached[1], time.monotonic())
                            return cached[0]
                        if r.status != 200 or r.content_type != 'image/png': raise web.HTTPServiceUnavailable()
                        data = bytearray()
                        async for chunk in r.content.iter_chunked(65536):
                            data.extend(chunk)
                            if len(data) > 4*1024*1024: raise web.HTTPServiceUnavailable()
                        if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise web.HTTPServiceUnavailable()
                        etag = r.headers.get('ETag')
            jpeg = await asyncio.to_thread(transcode_screen, bytes(data))
            screen_jpg_cache = (jpeg, etag, time.monotonic())
            return jpeg
        except Exception:
            screen_jpg_cache = None
            raise web.HTTPServiceUnavailable() from None
    def discard_capture(task):
        nonlocal screen_task
        if screen_task is task: screen_task = None
        if not task.cancelled(): task.exception()
    def discard_jpg_capture(task):
        nonlocal screen_jpg_task
        if screen_jpg_task is task: screen_jpg_task = None
        if not task.cancelled(): task.exception()
    async def screen(request):
        nonlocal screen_task
        if request.query_string or token_file is None: raise web.HTTPNotFound()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        if limited(ip, 'screen', 10, 30) or limited('global', 'screen', 1, 15): raise web.HTTPTooManyRequests()
        if screen_task is None or screen_task.done():
            screen_task = asyncio.create_task(capture_screen())
            screen_task.add_done_callback(discard_capture)
        task = screen_task
        data = await asyncio.shield(task)
        return web.Response(body=data,content_type='image/png')
    async def screen_jpg(request):
        nonlocal screen_jpg_task
        if request.query_string or token_file is None: raise web.HTTPNotFound()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        if limited(ip, 'screenjpg', 10, 120) or limited('global', 'screenjpg', 1, 300): raise web.HTTPTooManyRequests()
        if screen_jpg_cache is not None and time.monotonic()-screen_jpg_cache[2] < 0.1:
            return web.Response(body=screen_jpg_cache[0], content_type='image/jpeg')
        if screen_jpg_task is None or screen_jpg_task.done():
            screen_jpg_task = asyncio.create_task(capture_screen_jpg())
            screen_jpg_task.add_done_callback(discard_jpg_capture)
        task = screen_jpg_task
        data = await asyncio.shield(task)
        return web.Response(body=data, content_type='image/jpeg')
    director_cache = {'t': -1e9, 'layout': None}
    async def director_layout():   # owner 10-28: the page hides its PC SCREEN box while the stream shows the PC big
        now = time.monotonic()
        if now - director_cache['t'] >= 2 and token_file:
            director_cache['t'] = now
            try:
                async with asyncio.timeout(2):
                    async with aiohttp.ClientSession() as client:
                        async with client.get('http://127.0.0.1:8837/director/state',
                                              headers={'X-Admin-Token':Path(token_file).read_text().strip()}) as r:
                            d = await r.json() if r.status == 200 else {}
                            name = d.get('layout') if isinstance(d, dict) else None
                            director_cache['layout'] = name if name in ('webcam', 'webcam_only', 'desktop', 'split', 'room', 'cartoon') else None
            except (TimeoutError, aiohttp.ClientError, ValueError, OSError):
                director_cache['layout'] = None
        return director_cache['layout']
    audience_file = Path(stop_file).parent / 'watching.json'   # owner 10-29 (costs): the agent idles with nobody watching
    audience_written = {'t': -1e9, 'n': None}
    def write_audience(n):
        now = time.monotonic()
        if n == audience_written['n'] and now - audience_written['t'] < 5: return
        try:
            tmp = audience_file.with_name('.watching.json.tmp')
            tmp.write_text(json.dumps({'watching': n, 't': round(time.time(), 1)})); os.replace(tmp, audience_file)
            audience_written.update(t=now, n=n)
        except OSError:
            pass
    async def status(request):
        raw, _ = playlist()
        watching = count_online(request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64])
        write_audience(watching)
        return web.json_response({'online':raw is not None, 'agent':'paused' if Path(stop_file).exists() else 'checks', 'messages':list(messages),
                                  'watching':watching,
                                  'layout':await director_layout(), **(await viewer_state())})
    async def chat(request):
        if request.headers.get('Origin') != ORIGIN or request.content_type != 'text/plain': raise web.HTTPForbidden()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        now = time.monotonic()
        while global_chat and global_chat[0] < now-10: global_chat.popleft()
        if len(global_chat) >= 20 or limited(ip, 'chat', 12, 1): return web.json_response({'ok':False,'code':'rate_limited','why':'Please wait a few seconds.'}, status=429)
        text = (await request.text()).strip()
        nick = ''
        d = body_json(text)                                  # owner 10-28: {"nick","text"} from the page's name field
        if d is not None:
            text, nick = str(d.get('text') or '').strip(), clean_nick(d.get('nick'))
        if not 1 <= len(text) <= 280 or any(ord(c)<32 and c not in '\n\t' for c in text): raise web.HTTPBadRequest()
        global_chat.append(now)
        if token_file:   # owner 10-28 "no filter for the chat": every line goes straight to the agent (cartoon lines
            try:         # to its cartoon moderation); the backend's filtered chat path is only the fallback
                async with asyncio.timeout(8):
                    async with aiohttp.ClientSession() as client:
                        path = '/cartoon' if CARTOON.match(text) else '/chat'
                        async with client.post('http://127.0.0.1:8836' + path, json={'text':text,'nick':nick or 'viewer','voter':voter_key(ip)},
                                               headers={'X-Admin-Token':Path(token_file).read_text().strip()}) as r:
                            if r.status == 200 and (await r.json()).get('ok') is True:
                                messages.append({'text':text,'nick':nick,'at':int(time.time())})
                                return chat_ack_response({'ok':True})
            except (TimeoutError, aiohttp.ClientError, ValueError, OSError): pass   # the agent is away: the chat path
        try:
            async with asyncio.timeout(12):
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(local_addr=('127.0.0.2',0))) as client:
                    async with client.ws_connect('http://127.0.0.1:8830/ws', max_msg_size=2*1024*1024) as ws:
                        await ws.send_json({'type':'chat','nick':'viewer','text':text})
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = msg.json()
                                if data.get('type') == 'chat_ack':
                                    ok = data.get('ok') is True
                                    if ok: messages.append({'text':text,'at':int(time.time())})
                                    return chat_ack_response(data)
        except (TimeoutError, aiohttp.ClientError, ValueError): pass
        return web.json_response({'ok':False,'code':'offline','why':'Chat unavailable. Please try again later.'}, status=503)
    async def small_post(request, kind, period):
        """Shared guard of /queue and /hype: the page's Origin, text/plain, a small JSON object, per-IP and global limits."""
        if request.headers.get('Origin') != ORIGIN or request.content_type != 'text/plain': raise web.HTTPForbidden()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        if limited(ip, kind, period, 1) or limited('global', kind, 2, 10):
            return None, web.json_response({'ok':False,'code':'rate_limited','why':'Please wait a bit.'}, status=429)
        d = body_json((await request.text()).strip()[:600])
        if d is None: raise web.HTTPBadRequest()
        return d, None
    async def queue(request):
        d, refused = await small_post(request, 'queue', 30)
        if refused: return refused
        status, data = await agent_call('POST', '/queue', {'nick':clean_nick(d.get('nick')), 'url':str(d.get('url') or '')[:300]})
        if status is None or not isinstance(data, dict):
            return web.json_response({'ok':False,'code':'offline','why':'The queue is offline right now.'}, status=503)
        reason = str(data.get('reason') or 'bad_link')
        viewer_cache['t'] = -1e9
        return web.json_response({'ok':data.get('ok') is True, 'code':reason, 'why':QUEUE_WHY.get(reason, 'Not added.'),
                                  'position':data.get('position')}, status=200 if data.get('ok') is True else 409)
    async def hype(request):
        d, refused = await small_post(request, 'hype', 10)
        if refused: return refused
        status, data = await agent_call('POST', '/hype', {'nick':clean_nick(d.get('nick'))})
        if status is None or not isinstance(data, dict): return web.json_response({'ok':False,'code':'offline'}, status=503)
        viewer_cache['t'] = -1e9
        return web.json_response({'ok':True, 'level':data.get('level'), 'train':data.get('train')})
    async def avatar_page(request):
        if not AVATAR_PAGE.is_file(): raise web.HTTPNotFound()
        return web.FileResponse(AVATAR_PAGE, headers={'Content-Type': 'text/html; charset=utf-8'})
    async def avatar_voice(request):
        name = request.match_info['name']
        if not VOICE_PREVIEW.fullmatch(name) or not (AVATAR_VOICES / name).is_file(): raise web.HTTPNotFound()
        return web.FileResponse(AVATAR_VOICES / name, headers={'Content-Type': 'audio/mpeg', 'Cache-Control': 'public, max-age=86400'})
    async def avatar_forward(path, payload=None):
        try:
            async with asyncio.timeout(90):
                async with aiohttp.ClientSession() as client:
                    call = client.post(AVATAR_SERVICE + path, json=payload) if payload is not None else client.get(AVATAR_SERVICE + path)
                    async with call as r:
                        data = await r.json(content_type=None)
                        return web.json_response(data if isinstance(data, dict) else {'ok':False}, status=r.status)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return web.json_response({'ok':False,'why':'The avatars are offline right now.'}, status=503)
    async def avatar_call(request, path, period, maximum, fields, limit=6000, per_day=None):
        """the avatar page's JSON calls: the connection's salted hash as `client` (never the IP), per-IP and global
        limits here too; the service answers with its own status and JSON."""
        if request.content_type != 'application/json': raise web.HTTPForbidden()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        if request.content_length is None or request.content_length > limit: raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=request.content_length or 0)
        if limited(ip, path, period, maximum) or limited('global', path, 60, 30) or (per_day and limited('global', path + '/day', 86400, per_day)):
            return web.json_response({'ok':False,'why':'Please wait a bit.'}, status=429)
        raw = bytearray()                       # read here, bounded, instead of the app-wide small body limit
        while len(raw) <= limit and (chunk := await request.content.read(65536)): raw += chunk
        d = body_json(raw.decode('utf-8', 'replace').strip()) if len(raw) <= limit else None
        if d is None: raise web.HTTPBadRequest()
        return await avatar_forward(path, {'client': voter_key(ip), **{k: d.get(k) for k in fields}})
    async def avatar_list(request): return await avatar_forward('/avatars')
    async def avatar_session(request): return await avatar_call(request, '/session', 600, 2, ('avatar_id',))
    async def avatar_say(request): return await avatar_call(request, '/say', 3, 1, ('avatar_id', 'text', 'history'))
    async def avatar_submit(request):          # owner 10-29: a viewer's photo for a new avatar (the owner reviews every one)
        return await avatar_call(request, '/submit', 3600, 3, ('name', 'persona', 'voice', 'consent', 'photo_b64'),
                                 limit=AVATAR_SUBMIT_MAX, per_day=40)
    app = web.Application(client_max_size=2048, middlewares=[boundary])
    app.router.add_get('/avatar', avatar_page, allow_head=False)
    app.router.add_get('/avatar/list', avatar_list, allow_head=False)
    app.router.add_get('/avatar/voice/{name}', avatar_voice, allow_head=False)
    app.router.add_post('/avatar/session', avatar_session)
    app.router.add_post('/avatar/say', avatar_say)
    app.router.add_post('/avatar/submit', avatar_submit)
    app.router.add_get('/hls/{name}', media, allow_head=False)
    app.router.add_get('/screen.png', screen, allow_head=False)
    app.router.add_get('/screen.jpg', screen_jpg, allow_head=False)
    app.router.add_get('/status', status, allow_head=False)
    app.router.add_post('/chat', chat)
    app.router.add_post('/queue', queue)
    app.router.add_post('/hype', hype)
    return app

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--hls', required=True);p.add_argument('--stop',required=True);p.add_argument('--token-file');p.add_argument('--port',type=int,default=8841);a=p.parse_args()
    web.run_app(create_app(a.hls,a.stop,a.token_file),host='127.0.0.1',port=a.port,access_log=None)
