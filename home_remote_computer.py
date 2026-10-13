"""Authenticated loopback client for the single authoritative private guest."""
import asyncio
import json
import time
from pathlib import Path
from aiohttp import ClientSession, ClientTimeout
from scripts.home_device_proxy import loopback_origin


class RemoteComputer:
    def __init__(self, data_dir, origin, token_file):
        self.origin = loopback_origin(origin)
        path = Path(token_file)
        if not path.is_absolute():
            raise ValueError('Guest operator token path must be absolute')
        self.token = path.read_text().strip()
        if not self.token:
            raise ValueError('Guest operator token is empty')
        self.session = None
        self.revision = 0
        self.framebuffer_png = None
        self.last_agent = 0
        self._privacy_sent = None
        self._using_sent = None
        self._session_at = 0
        self._state = {}
        self._clear()

    def _clear(self):
        self.ready, self.paused, self.status = False, True, 'unavailable'
        self.output, self.last_command, self.commands = '', '', 0
        self.display = {'kind': 'unavailable', 'available': False}
        self.framebuffer_png = None
        self.error = 'Actual private guest is unavailable'
        self._state = {}
        self._privacy_sent, self._using_sent, self._session_at = None, None, 0
        self.revision += 1

    def view(self):
        return {**self._state, 'ready': self.ready, 'paused': self.paused,
                'status': self.status, 'output': self.output, 'display': dict(self.display),
                'error': self.error, 'revision': self.revision}

    async def request(self, method, path, data=None):
        if self.session is None:
            self.session = ClientSession(timeout=ClientTimeout(total=3))
        async with self.session.request(method, self.origin + path, json=data,
                headers={'X-Admin-Token': self.token}, allow_redirects=False) as response:
            chunks, total = [], 0
            async for chunk in response.content.iter_chunked(65536):
                total += len(chunk)
                if total > 6 * 1024 * 1024:
                    raise ValueError('Guest response exceeds bound')
                chunks.append(chunk)
            if response.status != 200:
                raise RuntimeError('Actual guest refused request')
            return b''.join(chunks)

    async def refresh(self):
        try:
            state = json.loads(await self.request('GET', '/pc/state'))
            pixels = None
            display = state.get('display', {})
            if not state.get('privacy') and display.get('available'):
                identity = display.get('frame_id', '')
                if not isinstance(identity, str) or not identity or any(c not in '0123456789abcdef-' for c in identity):
                    raise ValueError('Invalid guest frame identity')
                pixels = await self.request('GET', '/pc/frame.png?revision=' + identity)
                after = json.loads(await self.request('GET', '/pc/state'))
                if after.get('privacy') or after.get('display', {}).get('frame_id') != identity:
                    raise RuntimeError('Guest privacy or frame changed')
                if not pixels.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Guest frame is not PNG')
                state = after
            if state.get('privacy'):
                state = {**state, 'output': '', 'display': {'kind': 'private', 'available': False}, 'ready': False}
            self._state = state
            self.ready, self.paused = bool(state.get('ready')), bool(state.get('paused', True))
            self.status, self.output = str(state.get('status', 'unavailable')), str(state.get('output', ''))
            self.display, self.framebuffer_png = dict(state.get('display', {})), pixels
            self.last_command, self.commands = state.get('last_command'), state.get('commands', 0)
            self.error = str(state.get('error', ''))
            self.revision += 1
        except Exception:
            self._clear()

    async def input(self, text):
        # A serial command is meaningful only in an actual serial guest. A GUI
        # requires focused keyboard input, not writes to an unused serial UART.
        if not self.ready or self.display.get('kind') != 'serial':
            return False
        try:
            return bool(json.loads(await self.request('POST', '/pc/input', {'input': text, 'raw': True})).get('ok'))
        except Exception:
            self._clear()
            return False

    async def graphical_input(self, data):
        if not self.ready:
            return False
        try:
            return bool(json.loads(await self.request('POST', '/pc/graphical-input', data)).get('ok'))
        except Exception:
            self._clear()
            return False

    async def send(self, message):
        if message.get('type') not in {'pause', 'resume'}:
            return False
        try:
            await self.request('POST', '/pc/session', {'active': message['type'] == 'resume'})
            return True
        except Exception:
            self._clear()
            return False

    async def agent_step(self, home, rel):
        private = bool(home.view().get('privacy'))
        using = not private and home.activity == 'use_computer' and home.activity_ready('use_computer')
        try:
            if private != self._privacy_sent:
                if private:
                    self._clear()
                await self.request('POST', '/pc/privacy', {'active': private, 'source': 'home'})
                self._privacy_sent = private
            now = time.monotonic()
            if using != self._using_sent or (using and now - self._session_at > 20):
                if using or self._using_sent:
                    await self.request('POST', '/pc/session', {'active': using})
                self._using_sent, self._session_at = using, now
        except Exception:
            self._clear()
        # No synthetic command history: agent GUI commands remain gated until
        # an actual focused terminal and rendered text have been verified.

    async def run(self):
        try:
            while True:
                await self.refresh()
                await asyncio.sleep(1)
        finally:
            if self.session:
                await self.session.close()
