"""Trusted loopback-only relay to the existing authenticated private GPU viewer.

No GPU work on the Mac. Credentials remain server-side in memory; no cookie,
query token, personal browser profile or public listener is created.
"""
import argparse
import asyncio
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web

PREFIX = '/proxy/8892/'
ROUTES = {'', 'index.html', 'health', 'settings', 'frame.jpg', 'socket', 'input', 'mode'}
RESPONSE_HEADERS = {'content-type', 'cache-control', 'etag', 'x-native-sequence', 'x-native-capture-utc'}


def local_request_allowed(host, origin, port, method, websocket, fetch_site=''):
    allowed = {f'localhost:{port}', f'127.0.0.1:{port}'}
    if host not in allowed or fetch_site not in ('', 'none', 'same-origin'):
        return False
    if origin and origin != 'http://' + host:
        return False
    return bool(origin) if websocket or method == 'POST' else True


def create_app(base, token, port, prefix=PREFIX):
    remote = urlsplit(base)
    if remote.scheme != 'https' or not remote.hostname or not remote.hostname.endswith('.proxy.runpod.net') or remote.query or remote.username or remote.path not in ('', '/'):
        raise ValueError('Exact HTTPS private Runpod origin required')
    if not re.fullmatch(r'/proxy/[0-9]{4,5}/', prefix):
        raise ValueError('The viewer prefix must be /proxy/<port>/ on the Jupyter server')
    PREFIX = prefix    # noqa: N806  (the viewer's port differs between pods: 8892 on the 2026-10-14 host, 8893 on the current one)
    origin = base.rstrip('/')
    session_key = web.AppKey('remote_session', ClientSession)

    async def lifecycle(app):
        app[session_key] = ClientSession(headers={'Authorization': 'token ' + token},
            timeout=ClientTimeout(total=None, connect=10, sock_read=35))
        yield
        await app[session_key].close()

    async def relay(request):
        websocket = request.headers.get('Upgrade', '').lower() == 'websocket'
        try:
            loopback = ipaddress.ip_address(request.remote or '').is_loopback
        except ValueError:
            loopback = False
        if not loopback or not local_request_allowed(request.host, request.headers.get('Origin', ''), port,
                request.method, websocket, request.headers.get('Sec-Fetch-Site', '')):
            raise web.HTTPForbidden(text='Local viewer origin required')
        if request.path == '/' and request.method == 'GET':
            raise web.HTTPFound(PREFIX)
        suffix = request.path.removeprefix(PREFIX)
        if not request.path.startswith(PREFIX) or suffix not in ROUTES or len(request.query_string) > 2048:
            raise web.HTTPNotFound()
        if request.method not in ('GET', 'POST') or (request.method == 'POST' and suffix not in ('input', 'mode', 'settings')):
            raise web.HTTPMethodNotAllowed(request.method, ['GET', 'POST'])
        target = origin + request.path + ('?' + request.query_string if request.query_string else '')
        client = request.app[session_key]
        if websocket:
            if suffix != 'socket':
                raise web.HTTPNotFound()
            try:
                remote_ws = await client.ws_connect(target, origin=origin, heartbeat=20, max_msg_size=2*1024*1024)
            except Exception as error:
                print('LOCAL_NATIVE_WS_UPSTREAM_ERROR',type(error).__name__,getattr(error,'status',None),str(getattr(error,'message',''))[:160],flush=True)
                raise web.HTTPServiceUnavailable(text='Private house stream is warming up') from None
            print('LOCAL_NATIVE_WS_UPSTREAM_OPEN',flush=True)
            local_ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4096)
            await local_ws.prepare(request)

            async def pump(source, destination):
                async for msg in source:
                    if msg.type == WSMsgType.TEXT:
                        await destination.send_str(msg.data)
                    elif msg.type == WSMsgType.BINARY:
                        await destination.send_bytes(msg.data)
                    else:
                        break

            tasks = [asyncio.create_task(pump(local_ws, remote_ws)), asyncio.create_task(pump(remote_ws, local_ws))]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await remote_ws.close()
                await local_ws.close()
            return local_ws
        headers = {'Origin': origin}
        for name in ('Content-Type', 'If-None-Match'):
            if name in request.headers:
                headers[name] = request.headers[name]
        body = await request.read() if request.method == 'POST' else None
        try:
            async with client.request(request.method, target, headers=headers, data=body, allow_redirects=False) as response:
                if 300 <= response.status < 400 and response.status != 304:
                    raise web.HTTPServiceUnavailable(text='Private viewer authentication unavailable')
                payload = await response.read()
                return web.Response(status=response.status, body=payload,
                    headers={k:v for k,v in response.headers.items() if k.lower() in RESPONSE_HEADERS})
        except web.HTTPException:
            raise
        except Exception:
            raise web.HTTPServiceUnavailable(text='Private house is warming up') from None

    app = web.Application(client_max_size=4096)
    app.cleanup_ctx.append(lifecycle)
    app.router.add_route('*', '/{path:.*}', relay)
    return app


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--port', type=int, default=8791)
    args = p.parse_args()
    config = json.loads(args.config.read_text())
    tokens = list(config['tokens'].values())
    if not tokens or not isinstance(tokens[0], str) or len(tokens[0]) < 12:
        raise ValueError('Existing private viewer credential required')
    app = create_app(config['base_url'], tokens[0], args.port, config.get('prefix', PREFIX))
    web.run_app(app, host='127.0.0.1', port=args.port, access_log=None, print=None)


if __name__ == '__main__':
    main()
