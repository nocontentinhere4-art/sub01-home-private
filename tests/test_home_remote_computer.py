import asyncio
import json
from types import SimpleNamespace
import pytest
from home_remote_computer import RemoteComputer


def client(tmp_path):
    path = tmp_path / 'token'
    path.write_text('test-private-secret')
    return RemoteComputer(tmp_path, 'http://127.0.0.1:8811', str(path))


def test_remote_origin_and_factory_do_not_create_worker(tmp_path, monkeypatch):
    path = tmp_path / 'token'
    path.write_text('test-private-secret')
    with pytest.raises(ValueError):
        RemoteComputer(tmp_path, 'https://example.com', str(path))
    monkeypatch.setenv('HOME_COMPUTER_ORIGIN', 'http://127.0.0.1:8811')
    monkeypatch.setenv('HOME_COMPUTER_TOKEN_FILE', str(path))
    from home_computer import Computer
    computer = Computer(tmp_path)
    assert isinstance(computer, RemoteComputer)
    assert computer.ready is False and computer.framebuffer_png is None
    assert not hasattr(computer, 'process')


def test_frame_privacy_race_clears_all_guest_pixels(tmp_path):
    async def check():
        c = client(tmp_path)
        responses = [
            json.dumps({'ready': True, 'display': {'available': True, 'kind': 'graphical', 'frame_id': 'abcdef-1'}, 'output': 'secret'}).encode(),
            b'\x89PNG\r\n\x1a\nactual',
            json.dumps({'privacy': True}).encode(),
        ]
        async def request(*args):
            return responses.pop(0)
        c.request = request
        await c.refresh()
        assert not c.ready and c.output == '' and c.framebuffer_png is None
        assert not c.display['available']
    asyncio.run(check())


def test_gui_agent_does_not_claim_unrendered_serial_commands(tmp_path):
    async def check():
        c = client(tmp_path)
        calls = []
        async def request(method, path, data=None):
            calls.append((method, path, data))
            if path == '/pc/state':
                return json.dumps({'ready': True, 'paused': False, 'display': {'kind': 'vga-text', 'available': False, 'keyboard_available': True}}).encode()
            return b'{"ok":true}'
        c.request = request
        home = SimpleNamespace(view=lambda: {'privacy': False}, activity='use_computer', activity_ready=lambda action: True)
        await c.agent_step(home, {})
        await c.refresh()
        assert await c.input('uname -a\n') is False
        assert not any(path == '/pc/input' for _, path, _ in calls)
        assert calls[0] == ('POST', '/pc/privacy', {'active': False, 'source': 'home'})
        assert calls[1] == ('POST', '/pc/session', {'active': True, 'source': 'home'})
        async def unavailable(*args):
            raise RuntimeError('offline')
        c.request = unavailable
        await c.refresh()
        assert c.view()['ready'] is False and c.output == ''
    asyncio.run(check())


def test_real_runner_protocol_and_independent_privacy_sources(tmp_path):
    async def check():
        from aiohttp.test_utils import TestServer
        from scripts.home_pc_runner import PCRunner, create_app
        class Guest:
            ready, paused, revision, input_until = True, False, 1, 0
            inputs = []
            def view(self):
                return {'ready': True, 'paused': self.paused, 'status': 'ready', 'output': 'shell', 'display': {'kind': 'serial', 'available': False}}
            async def input(self, text):
                self.inputs.append(text)
                return True
            async def send(self, data):
                self.paused = data['type'] == 'pause'
                return True
        guest = Guest()
        runner = PCRunner(guest, 'test-private-secret')
        server = TestServer(create_app(runner))
        await server.start_server()
        c = client(tmp_path)
        c.origin = str(server.make_url('')).rstrip('/')
        try:
            await c.refresh()
            assert await c.input('uname -a\n') is True
            assert guest.inputs == ['uname -a\n']
            await runner.set_privacy(True, 'native')
            await c.request('POST', '/pc/privacy', {'active': False, 'source': 'home'})
            assert runner.privacy
            await c.refresh()
            assert c.output == '' and not c.ready and c.framebuffer_png is None
            await runner.set_privacy(True, 'home')
            await runner.set_privacy(False, 'native')
            assert runner.privacy
            await runner.set_privacy(False, 'home')
            assert not runner.privacy
        finally:
            if c.session:
                await c.session.close()
            await server.close()
    asyncio.run(check())
