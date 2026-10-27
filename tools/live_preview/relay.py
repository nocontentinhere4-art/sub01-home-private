"""Temporary public viewer relay. No operator routes, credentials, or generic proxy."""
import argparse, asyncio, collections, re, time
from pathlib import Path
import aiohttp
from aiohttp import web
ORIGIN = 'https://subzerone.live'
SEGMENT = re.compile(r'^sub01-[0-9]{8}-[0-9]{6}-[0-9]+\.ts$')
HEADERS = {'Access-Control-Allow-Origin': ORIGIN, 'Vary': 'Origin', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}

def create_app(root, stop_file, token_file=None):
    root = Path(root).resolve()
    messages = collections.deque(maxlen=30)
    rates = collections.OrderedDict()
    global_chat = collections.deque()
    slots = asyncio.Semaphore(8)
    screen_lock = asyncio.Lock()
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
        if limited(ip, 'all', 10, 120) or limited('global', 'all', 1, 100):
            return web.Response(status=429, text='Please wait', headers=HEADERS)
        try: response = await handler(request)
        except web.HTTPException as exc: response = web.Response(status=exc.status, text='Unavailable')
        response.headers.update(HEADERS)
        return response
    def playlist():
        p = root/'live.m3u8'
        if not p.is_file() or time.time()-p.stat().st_mtime > 20: return None, set()
        raw = p.read_text()
        if len(raw) > 65536: return None, set()
        names = {line.strip() for line in raw.splitlines() if line.strip() and not line.startswith('#')}
        if not names or not all(SEGMENT.fullmatch(n) for n in names): return None, set()
        return raw, names
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
    async def screen(request):
        if request.query_string or token_file is None: raise web.HTTPNotFound()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        if screen_lock.locked() or limited(ip, 'screen', 1, 1):
            raise web.HTTPTooManyRequests()
        async with screen_lock:
            try:
                token = Path(token_file).read_text().strip()
                async with asyncio.timeout(3):
                    async with aiohttp.ClientSession() as client:
                        async with client.get('http://127.0.0.1:8838/pc/frame.png',
                                headers={'X-Admin-Token':token}, allow_redirects=False) as r:
                            if r.status != 200 or r.content_type != 'image/png':
                                raise web.HTTPServiceUnavailable()
                            data = bytearray()
                            async for chunk in r.content.iter_chunked(65536):
                                data.extend(chunk)
                                if len(data) > 4*1024*1024: raise web.HTTPServiceUnavailable()
                            if not data.startswith(b'\x89PNG\r\n\x1a\n'): raise web.HTTPServiceUnavailable()
                            return web.Response(body=bytes(data),content_type='image/png')
            except (TimeoutError, aiohttp.ClientError, OSError, ValueError):
                raise web.HTTPServiceUnavailable()
    async def status(request):
        raw, _ = playlist()
        return web.json_response({'online':raw is not None, 'agent':'paused' if Path(stop_file).exists() else 'checks', 'messages':list(messages)})
    async def chat(request):
        if request.headers.get('Origin') != ORIGIN or request.content_type != 'text/plain': raise web.HTTPForbidden()
        ip = request.headers.get('CF-Connecting-IP', request.remote or 'local')[:64]
        now = time.monotonic()
        while global_chat and global_chat[0] < now-10: global_chat.popleft()
        if len(global_chat) >= 20 or limited(ip, 'chat', 12, 1): return web.json_response({'ok':False,'why':'Attendi qualche secondo.'}, status=429)
        text = (await request.text()).strip()
        if not 1 <= len(text) <= 280 or any(ord(c)<32 and c not in '\n\t' for c in text): raise web.HTTPBadRequest()
        global_chat.append(now)
        try:
            async with asyncio.timeout(12):
                async with aiohttp.ClientSession() as client:
                    async with client.ws_connect('http://127.0.0.1:8830/ws', max_msg_size=2*1024*1024) as ws:
                        await ws.send_json({'type':'chat','nick':'viewer','text':text})
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = msg.json()
                                if data.get('type') == 'chat_ack':
                                    ok = data.get('ok') is True
                                    if ok: messages.append({'text':text,'at':int(time.time())})
                                    return web.json_response({'ok':ok,'why':'Messaggio ricevuto.' if ok else 'Messaggio rifiutato dal filtro della chat.'})
        except (TimeoutError, aiohttp.ClientError, ValueError): pass
        return web.json_response({'ok':False,'why':'Chat non disponibile. Riprova più tardi.'}, status=503)
    app = web.Application(client_max_size=2048, middlewares=[boundary])
    app.router.add_get('/hls/{name}', media, allow_head=False)
    app.router.add_get('/screen.png', screen, allow_head=False)
    app.router.add_get('/status', status, allow_head=False)
    app.router.add_post('/chat', chat)
    return app

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--hls', required=True);p.add_argument('--stop',required=True);p.add_argument('--token-file');p.add_argument('--port',type=int,default=8841);a=p.parse_args()
    web.run_app(create_app(a.hls,a.stop,a.token_file),host='127.0.0.1',port=a.port,access_log=None)
