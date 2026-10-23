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
        view = c.view()
        assert view['ready'] is False and c.output == ''
        # The house says what to check, like the local guest does (same summary/hint contract).
        assert view['status'] == 'unavailable' and view['summary'] == view['error']
        assert 'home_pc_runner.py' in view['hint'] and 'http://127.0.0.1:8811' in view['hint']
    asyncio.run(check())


def test_remote_availability_transitions_are_logged_once(tmp_path, capsys):
    async def check():
        c = client(tmp_path)
        async def down(*args):
            raise RuntimeError('connection refused')
        c.request = down
        await c.refresh()
        await c.refresh()
        async def up(method, path, data=None):
            return json.dumps({'ready': True, 'paused': True, 'status': 'ready', 'output': '~# ',
                               'summary': 'Buildroot Linux / x86 · paused while he is away from the desk',
                               'display': {'kind': 'serial', 'available': False}}).encode()
        c.request = up
        await c.refresh()
        assert c.view()['summary'] == 'Buildroot Linux / x86 · paused while he is away from the desk'
        assert c.view()['hint'] == ''
        out = capsys.readouterr().out
        assert out.count('is unavailable (RuntimeError: connection refused)') == 1
        assert out.count('answers (guest status: ready)') == 1
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


@pytest.mark.parametrize('exit_before_reply', [False, True])
def test_pending_public_gui_reply_cannot_undo_home_privacy(tmp_path, exit_before_reply):
    """Delay the actual PC state response across privacy, including enter/exit ABA."""
    async def check():
        from aiohttp import web
        from aiohttp.test_utils import TestServer
        from scripts.home_pc_runner import PCRunner, create_app

        class Guest:
            ready, paused, revision, input_until = True, False, 1, 0
            framebuffer_png = b'\x89PNG\r\n\x1a\ncached-public-frame'
            display = {'kind': 'graphical', 'available': True, 'frame_id': 'abcdef-1'}

            def view(self):
                return {'ready': True, 'paused': self.paused, 'status': 'ready',
                        'output': 'public-before-privacy', 'display': dict(self.display)}

            async def send(self, message):
                self.paused = message['type'] == 'pause'
                return True

        entered, release = asyncio.Event(), asyncio.Event()
        reads = 0

        @web.middleware
        async def delay_second_state(request, handler):
            nonlocal reads
            response = await handler(request)
            if request.path == '/pc/state':
                reads += 1
                if reads == 2:
                    # The post-frame state has already been constructed public.
                    entered.set()
                    await release.wait()
            return response

        runner = PCRunner(Guest(), 'test-private-secret')
        app = create_app(runner)
        app.middlewares.append(delay_second_state)
        server = TestServer(app)
        await server.start_server()
        c = client(tmp_path)
        c.origin = str(server.make_url('')).rstrip('/')
        private = {'active': True}
        home = SimpleNamespace(view=lambda: {'privacy': private['active']},
                               activity='research', activity_ready=lambda _: False)
        pending = asyncio.create_task(c.refresh())
        try:
            await asyncio.wait_for(entered.wait(), 2)
            await c.agent_step(home, {})
            assert runner.privacy
            if exit_before_reply:
                private['active'] = False
                await c.agent_step(home, {})
                assert not runner.privacy
            release.set()
            await asyncio.wait_for(pending, 2)
            assert c.output == '' and c.framebuffer_png is None
            assert not c.ready and not c.display['available']
            # A new response after actual privacy exit may show the real GUI again.
            private['active'] = False
            await c.agent_step(home, {})
            await c.refresh()
            assert c.ready and c.framebuffer_png == runner.computer.framebuffer_png
        finally:
            release.set()
            await asyncio.gather(pending, return_exceptions=True)
            if c.session:
                await c.session.close()
            await server.close()
    asyncio.run(check())
