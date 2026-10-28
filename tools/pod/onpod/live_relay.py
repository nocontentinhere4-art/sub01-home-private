"""Temporary public viewer relay. No operator routes, credentials, or generic proxy."""
import argparse, asyncio, collections, io, re, time
from pathlib import Path
import aiohttp
from aiohttp import web
from PIL import Image
ORIGIN = 'https://subzerone.live'
LIVE_KEEP, START_OFFSET = 4, 4.0      # public playlist: newest 4 segments (8 s), start 4 s from the live edge (owner 10-28)
CARTOON = re.compile(r'^\W{0,2}(?:!\s*cartoon\b|cartoon\s*:)', re.I)   # the agent's CARTOON_PREFIX: sent straight to it
SEGMENT = re.compile(r'^sub01-[0-9]{8}-[0-9]{6}-[0-9]+\.ts$')
HEADERS = {'Access-Control-Allow-Origin': ORIGIN, 'Vary': 'Origin', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}

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
    def limited(ip, kind, period, maximum):
        now = time.monotonic(); key = (ip, kind)
        q = rates.setdefault(key, collections.deque()); rates.move_to_end(key)
        while q and q[0] < now-period: q.popleft()
        while len(rates) > 2048: rates.popitem(last=False)
        if len(q) >= maximum: return True
        q.append(now); return False
    @web.middleware
    async def boundary(request, handler):
        if request.headers.get('Origin') not in (None, ORIGIN):
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
    async def status(request):
        raw, _ = playlist()
        return web.json_response({'online':raw is not None, 'agent':'paused' if Path(stop_file).exists() else 'checks', 'messages':list(messages)})
    async def chat(request):
        if request.headers.get('Origin') != ORIGIN or request.content_type != 'text/plain': raise web.HTTPForbidden()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        now = time.monotonic()
        while global_chat and global_chat[0] < now-10: global_chat.popleft()
        if len(global_chat) >= 20 or limited(ip, 'chat', 12, 1): return web.json_response({'ok':False,'code':'rate_limited','why':'Please wait a few seconds.'}, status=429)
        text = (await request.text()).strip()
        if not 1 <= len(text) <= 280 or any(ord(c)<32 and c not in '\n\t' for c in text): raise web.HTTPBadRequest()
        global_chat.append(now)
        if token_file:   # owner 10-28 "no filter for the chat": every line goes straight to the agent (cartoon lines
            try:         # to its cartoon moderation); the backend's filtered chat path is only the fallback
                async with asyncio.timeout(8):
                    async with aiohttp.ClientSession() as client:
                        path = '/cartoon' if CARTOON.match(text) else '/chat'
                        async with client.post('http://127.0.0.1:8836' + path, json={'text':text,'nick':'viewer'},
                                               headers={'X-Admin-Token':Path(token_file).read_text().strip()}) as r:
                            if r.status == 200 and (await r.json()).get('ok') is True:
                                messages.append({'text':text,'at':int(time.time())})
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
    app = web.Application(client_max_size=2048, middlewares=[boundary])
    app.router.add_get('/hls/{name}', media, allow_head=False)
    app.router.add_get('/screen.png', screen, allow_head=False)
    app.router.add_get('/screen.jpg', screen_jpg, allow_head=False)
    app.router.add_get('/status', status, allow_head=False)
    app.router.add_post('/chat', chat)
    return app

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--hls', required=True);p.add_argument('--stop',required=True);p.add_argument('--token-file');p.add_argument('--port',type=int,default=8841);a=p.parse_args()
    web.run_app(create_app(a.hls,a.stop,a.token_file),host='127.0.0.1',port=a.port,access_log=None)
