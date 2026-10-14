"""Private authenticated passthrough to the actual home phone/console backend.

No browser process, screenshot generation, static page, game simulation or guest
is created here. A missing configured backend is reported as unavailable.
"""
import json
import math
import ipaddress
import re
from urllib.parse import urlsplit
from aiohttp import web, ClientSession, ClientTimeout


def loopback_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', '::1', 'localhost'}
            or parsed.username or parsed.password or parsed.path not in {'', '/'}
            or parsed.query or parsed.fragment or not parsed.port):
        raise ValueError('Home device backend must be an explicit loopback HTTP origin with a port')
    return value.rstrip('/')


def phone_navigation_url(value):
    """Bound the operator URL; the real browser still checks DNS and redirects."""
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Expected a public HTTPS URL')
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').encode('idna').decode('ascii').lower().rstrip('.')
        if parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443} or not host:
            raise ValueError('Expected a public HTTPS URL')
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if ('.' not in host or host.endswith(('.local', '.internal', '.localhost', '.lan', '.home', '.corp'))
                    or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in host.split('.'))):
                raise ValueError('Expected a public HTTPS URL')
        else:
            if not address.is_global:
                raise ValueError('Expected a public HTTPS URL')
    except (UnicodeError, ValueError):
        raise ValueError('Expected a public HTTPS URL') from None
    return value


class HomeDeviceProxy:
    def __init__(self, origin, token, runner, session=None):
        self.origin = loopback_origin(origin)
        self.token, self.runner, self.session = token, runner, session

    async def close(self):
        if self.session:
            await self.session.close()

    async def request(self, method, path, *, data=None, query=None):
        if self.session is None:
            self.session = ClientSession(timeout=ClientTimeout(total=4))
        async with self.session.request(method, self.origin + path, params=query, json=data,
                                        headers={'X-Admin-Token': self.token}, allow_redirects=False) as response:
            chunks, total = [], 0
            async for chunk in response.content.iter_chunked(65536):
                total += len(chunk)
                if total > 6 * 1024 * 1024:
                    raise web.HTTPBadGateway(text='Actual device response exceeds the supported bound')
                chunks.append(chunk)
            body = b''.join(chunks)
            if response.status != 200:
                if response.status in {400, 403, 404, 409, 503}:
                    raise {400: web.HTTPBadRequest, 403: web.HTTPForbidden, 404: web.HTTPNotFound, 409: web.HTTPConflict, 503: web.HTTPServiceUnavailable}[response.status](text='Actual home device unavailable')
                raise web.HTTPBadGateway(text='Actual home device backend is unavailable')
            return body, response.headers.get('Content-Type', ''), response.headers.get('ETag')

    def guard(self, epoch):
        if self.runner.privacy or self.runner.privacy_epoch != epoch:
            raise web.HTTPConflict(text='Bathroom privacy is active')

    async def home(self, epoch):
        self.guard(epoch)
        body, _, _ = await self.request('GET', '/api/home')
        self.guard(epoch)
        try:
            state = json.loads(body)
            private = state['home']['privacy']
        except (ValueError, KeyError, TypeError):
            raise web.HTTPBadGateway(text='Actual home state is unavailable')
        if private is not False:
            raise web.HTTPConflict(text='Bathroom privacy is active')
        return state

    async def state(self, request):
        epoch = self.runner.privacy_epoch
        return web.json_response(await self.home(epoch), headers={'Cache-Control': 'no-store'})

    async def frame(self, request):
        epoch = self.runner.privacy_epoch
        state = await self.home(epoch)
        device = request.match_info['device']
        if device == 'phone':
            identity = (state.get('phone_screen') or state.get('phone_browser_screen') or {}).get('frame_id')
            expected = request.query.get('frame_id')
            if not identity:
                raise web.HTTPNotFound(text='Actual phone browser has no current frame')
            if expected is not None and expected != identity:
                raise web.HTTPConflict(text='Actual phone frame changed')
            path = '/api/home/phone/frame.jpg' if state.get('phone_screen') else '/api/screen/phone.jpg'
            query = {'frame_id': identity}
        elif device == 'tv':
            if state['home'].get('console_game') != 'minecraft' or not state.get('minecraft', {}).get('enabled'):
                raise web.HTTPNotFound(text='Actual TV JPEG is only available for configured Minecraft')
            path, query = '/api/home/minecraft/frame.jpg', None
        else:
            raise web.HTTPNotFound()
        pixels, content, tag = await self.request('GET', path, query=query)
        after = await self.home(epoch)
        if device == 'phone' and (after.get('phone_screen') or after.get('phone_browser_screen') or {}).get('frame_id') != identity:
            raise web.HTTPConflict(text='Actual phone frame changed')
        if device == 'tv' and after['home'].get('console_game') != 'minecraft':
            raise web.HTTPConflict(text='Actual console activity changed')
        if content.split(';')[0] != 'image/jpeg':
            raise web.HTTPBadGateway(text='Actual device returned no JPEG frame')
        headers = {'Cache-Control': 'no-store'}
        if tag:
            headers['ETag'] = tag
        return web.Response(body=pixels, content_type='image/jpeg', headers=headers)

    async def action(self, request):
        epoch = self.runner.privacy_epoch
        state = await self.home(epoch)
        if request.content_length is not None and request.content_length > 4096:
            raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=request.content_length)
        chunks, total = [], 0
        async for chunk in request.content.iter_chunked(4096):
            total += len(chunk)
            if total > 4096:
                raise web.HTTPRequestEntityTooLarge(max_size=4096, actual_size=total)
            chunks.append(chunk)
        try:
            data = json.loads(b''.join(chunks))
        except (ValueError, UnicodeDecodeError):
            raise web.HTTPBadRequest(text='Invalid device action')
        if not isinstance(data, dict):
            raise web.HTTPBadRequest(text='Expected device action object')
        device = request.match_info['device']
        if device == 'phone' and isinstance(data, dict) and data.get('action') == 'navigate':
            try:
                url = phone_navigation_url(data.get('url'))
            except ValueError:
                raise web.HTTPBadRequest(text='Expected a public HTTPS URL')
            current = (state.get('phone_screen') or state.get('phone_browser_screen') or {}).get('frame_id')
            expected = data.get('frame_id')
            if (current and expected != current) or (not current and expected is not None and expected != ''):
                raise web.HTTPConflict(text='Actual phone frame changed')
            path, clean = '/api/home/browser', {'device': 'phone', 'url': url}
        elif device == 'phone' and data.get('action') == 'save_note':
            screen = state.get('phone_screen') or {}
            if screen.get('app') != 'notes':
                raise web.HTTPConflict(text='Open Notes before saving a note')
            current = screen.get('frame_id')
            if not current or data.get('frame_id') != current:
                raise web.HTTPConflict(text='Actual phone frame changed')
            title, text = data.get('title', ''), data.get('text')
            if (not isinstance(title, str) or len(title) > 120
                    or not isinstance(text, str) or len(text) > 2000 or not text.strip()
                    or len((title.strip() + '\n' if title.strip() else '') + text.strip()) > 2000):
                raise web.HTTPBadRequest(text='Expected bounded note title and nonempty text')
            path, clean = '/api/home/phone/action', {k:data[k] for k in ('action', 'frame_id', 'title', 'text') if k in data}
        elif device == 'phone' and isinstance(data, dict) and data.get('action') in {'home', 'open_app'}:
            current = (state.get('phone_screen') or {}).get('frame_id')
            if not current or data.get('frame_id') != current:
                raise web.HTTPConflict(text='Actual phone frame changed')
            if data.get('action') == 'open_app' and data.get('app') not in ('home', 'notes', 'memory', 'browser'):
                raise web.HTTPBadRequest(text='Expected supported phone app')
            path, clean = '/api/home/phone/action', {k:data[k] for k in ('action', 'app', 'frame_id') if k in data}
        elif device == 'phone':
            if (not isinstance(data, dict) or data.get('action') not in {'scroll_up', 'scroll_down', 'back', 'close_notice'}
                    or not isinstance(data.get('frame_id'), str) or not 1 <= len(data['frame_id']) <= 100):
                raise web.HTTPBadRequest(text='Expected current phone frame and supported browser action')
            path, clean = '/api/home/browser/action', {'device': 'phone', 'action': data['action'], 'frame_id': data['frame_id']}
        elif device == 'tv' and isinstance(data, dict) and 'direction' in data:
            direction = data['direction']
            if isinstance(direction, bool) or not isinstance(direction, (int, float)) or not math.isfinite(direction) or abs(direction) > 1:
                raise web.HTTPBadRequest(text='Expected actual Pong paddle direction')
            path, clean = '/api/home/pong', {'direction': direction}
        elif device == 'tv':
            if not isinstance(data, dict) or data.get('game') not in {'pong', 'chess', 'minecraft'}:
                raise web.HTTPBadRequest(text='Expected actual console game selection')
            path, clean = '/api/home/game', {'game': data['game']}
        else:
            raise web.HTTPNotFound()
        self.guard(epoch)
        body, _, _ = await self.request('POST', path, data=clean)
        await self.home(epoch)
        return web.Response(body=body, content_type='application/json', headers={'Cache-Control': 'no-store'})
