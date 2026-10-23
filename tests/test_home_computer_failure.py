"""Every way the PC fails is visible and recoverable: a dead worker clears the cached desktop, a missing guest
(the gitignored .bin files) or a dead worker is named in the view with the fix and retried, nothing is swallowed.

    BROWSE=0 python -m pytest tests/test_home_computer_failure.py -q
No network: bootstrap's download and the worker are replaced by fixtures.
"""
import asyncio
import hashlib
import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

import home_computer
from computer import bootstrap
from home_computer import Computer, RETRY_S


def test_dead_guest_clears_pixels_text_and_input_capability(tmp_path, monkeypatch):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    c = Computer(tmp_path)
    c.ready, c.status, c.output, c.last_command = True, 'ready', 'private terminal text', 'uname -a'
    c.display = {'kind': 'graphical', 'available': True, 'keyboard_available': True}
    c.framebuffer_png = b'old real guest pixels'
    c.instruction_counter = 12345
    c.mouse_state = {"ps2_mouse_id": 4, "ps2_stream_active": True}
    c.process = SimpleNamespace(returncode=1)
    assert asyncio.run(c.graphical_input({'type': 'vga-keyboard', 'scancodes': [30, 158]})) is False
    state = c.view()
    assert not state['ready'] and state['status'] == 'offline'
    assert state['output'] == '' and state['last_command'] == ''
    assert state['instruction_counter'] is None and state['mouse_state'] is None
    assert c.framebuffer_png is None and not state['display']['available']
    assert not state['display'].get('keyboard_available')


# --- the view says what the computer is doing, or why it is not ------------------------------------------------------
def test_view_carries_summary_hint_and_guest_and_the_summary_follows_the_status(tmp_path, monkeypatch):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    c = Computer(tmp_path)
    v = c.view()
    assert v['status'] == 'starting' and v['summary'] == 'Starting his computer…' and v['hint'] == ''
    assert v['guest'] == {'assets': None, 'worker': None, 'restarts': 0, 'exit_code': None}
    c.status = 'preparing'
    assert 'pinned Linux guest files' in c.summary()
    c.status = 'booting'
    assert c.summary() == 'Linux is booting…'
    c.status, c.ready, c.paused = 'ready', True, True
    assert c.summary() == 'Buildroot Linux / x86 · paused while he is away from the desk'
    c.paused = False
    assert c.summary() == 'Buildroot Linux / x86 · running'
    c.status, c.error = 'unavailable', 'Node.js is not installed'
    assert c.summary() == 'Node.js is not installed'
    r = c.revision
    c.hint = 'Install Node.js'
    assert c.revision == r + 1, 'a changed hint refreshes the page like any other visible field'
    assert json.dumps(c.view())                                                       # JSON-serialisable for /api/home


# --- run(): nothing fails silently -----------------------------------------------------------------------------------
def test_missing_node_is_named_and_the_task_ends(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    monkeypatch.setattr(home_computer.shutil, 'which', lambda name: None)
    c = Computer(tmp_path)
    asyncio.run(c.run())
    assert c.status == 'unavailable' and c.error == 'Node.js is not installed'
    assert 'Node.js' in c.hint and c.summary() == 'Node.js is not installed'
    assert 'home computer: Node.js is not installed' in capsys.readouterr().out


def _cancel_after(monkeypatch, n):
    """asyncio.sleep that records its waits and ends the loop at the n-th call (as test_screens does)."""
    waits = []

    async def fake_sleep(s):
        waits.append(s)
        if len(waits) >= n:
            raise asyncio.CancelledError
    monkeypatch.setattr(home_computer.asyncio, 'sleep', fake_sleep)
    return waits


def test_missing_guest_files_are_named_with_the_fix_logged_once_and_retried(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    monkeypatch.setattr(home_computer.shutil, 'which', lambda name: '/usr/bin/node')

    def no_download(destination, prefer_bundled=True):
        raise RuntimeError('Could not download seabios.bin from https://copy.sh/v86/bios/seabios.bin: Network is unreachable')
    monkeypatch.setattr(bootstrap, 'ensure', no_download)
    monkeypatch.setattr(bootstrap, 'status', lambda destination=None: {
        'installed': False, 'source': None, 'path': str(destination),
        'missing': ['seabios.bin', 'vgabios.bin', 'buildroot-bzimage.bin']})
    waits = _cancel_after(monkeypatch, 2)
    c = Computer(tmp_path)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(c.run())
    v = c.view()
    assert v['status'] == 'unavailable' and not v['ready']
    assert v['error'].startswith('Linux guest not installed: 3 of 3 pinned files missing (seabios.bin')
    assert 'Could not download seabios.bin' in v['error'] and 'Network is unreachable' in v['error']
    assert 'python computer/bootstrap.py' in v['hint'] and 'retries by itself' in v['hint']
    assert v['summary'] == v['error']
    assert waits == [RETRY_S[0], RETRY_S[1]], 'retried with the bounded backoff, never returned silently'
    out = capsys.readouterr().out
    assert out.count('Linux guest not installed') == 1, 'the same failure is logged once, not every retry'
    assert 'next try in 30 s' in out and 'bootstrap.py' in out


class Pipe:
    def __init__(self):
        self.sent = []

    def write(self, payload):
        self.sent.append(json.loads(payload))

    async def drain(self):
        pass


class FakeWorker:
    """A node worker that prints some JSON lines and then exits with `code` (stderr lines are what node would print)."""

    def __init__(self, lines, stderr=(), code=1):
        self.pid, self.returncode, self.code = 4242, None, code
        self.stdin = Pipe()
        self.stdout = self._stream(lines, final=True)
        self.stderr = self._stream(stderr)

    async def _stream(self, items, final=False):
        for item in items:
            raw = json.dumps(item) if isinstance(item, dict) else item
            yield (raw.encode() if isinstance(raw, str) else raw) + b'\n'
        if final:
            self.returncode = self.code

    async def wait(self):
        if self.returncode is None:
            self.returncode = self.code
        return self.returncode

    def kill(self):
        self.returncode = -9


def test_a_worker_that_dies_is_logged_with_its_stderr_shown_in_the_view_and_restarted(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    monkeypatch.setattr(home_computer.shutil, 'which', lambda name: '/usr/bin/node')
    assets = tmp_path / 'assets'
    assets.mkdir()
    monkeypatch.setattr(bootstrap, 'ensure', lambda destination, prefer_bundled=True: assets)
    spawned = []

    async def spawn(*args, **kwargs):
        spawned.append((args, kwargs))
        return FakeWorker([
            {'type': 'terminal', 'ready': False, 'output': 'Linux version 5.6.15', 'paused': False},
            {'type': 'restored'},
            {'type': 'terminal', 'ready': True, 'output': 'Linux version 5.6.15\n~# ', 'paused': False, 'instruction_counter': 7},
            b'not json at all',
            {'type': 'error', 'message': 'VM snapshot failed'},
        ], stderr=['Error: Cannot find module ./libv86.cjs', '    at Module._load'], code=1)
    monkeypatch.setattr(home_computer.asyncio, 'create_subprocess_exec', spawn)
    waits = _cancel_after(monkeypatch, 1)
    c = Computer(tmp_path)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(c.run())
    args, kwargs = spawned[0]
    assert args[0] == '/usr/bin/node' and args[-1].endswith('computer/worker.cjs')
    assert kwargs['env']['SUB01_VM_ASSETS'] == str(assets) and kwargs['env']['SUB01_VM_STATE'] == str(tmp_path / 'computer.bin')
    assert kwargs['stderr'] == asyncio.subprocess.PIPE, 'the worker\'s stderr is read, not thrown away'
    v = c.view()
    assert v['status'] == 'offline' and not v['ready'] and v['output'] == ''
    assert v['error'].startswith('Linux guest worker exited with code 1; stderr: Error: Cannot find module ./libv86.cjs')
    assert v['guest'] == {'assets': 'cache', 'worker': 'exited', 'restarts': 1, 'exit_code': 1}
    assert 'restarts by itself' in v['hint'] and v['summary'] == v['error']
    assert waits == [RETRY_S[0]]
    out = capsys.readouterr().out
    assert 'guest worker started (pid 4242, cache assets' in out
    assert 'Linux guest ready after' in out and 'Linux restored from its saved state' in out
    assert 'the guest worker reports: VM snapshot failed' in out
    assert 'exited with code 1; stderr: Error: Cannot find module ./libv86.cjs | ' in out
    assert 'restarting the guest worker in 30 s (restart 1)' in out


def test_ready_guest_clears_an_older_error_and_bundled_assets_are_named(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv('HOME_COMPUTER_ORIGIN', raising=False)
    monkeypatch.setattr(home_computer.shutil, 'which', lambda name: '/usr/bin/node')
    monkeypatch.setattr(bootstrap, 'ensure', lambda destination, prefer_bundled=True: bootstrap.ROOT)
    seen = {}

    async def spawn(*args, **kwargs):
        worker = FakeWorker([{'type': 'terminal', 'ready': True, 'output': '~# ', 'paused': True}], code=0)
        seen['worker'] = worker
        return worker
    monkeypatch.setattr(home_computer.asyncio, 'create_subprocess_exec', spawn)
    _cancel_after(monkeypatch, 1)
    c = Computer(tmp_path)
    c.error, c.hint = 'Linux guest not installed', 'run bootstrap'

    original = c._handle

    def handle(m, worker, boot):
        original(m, worker, boot)
        if c.ready:
            seen['ready_view'] = c.view()
    c._handle = handle
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(c.run())
    ready = seen['ready_view']
    assert ready['status'] == 'ready' and ready['error'] == '' and ready['hint'] == ''
    assert ready['guest']['assets'] == 'bundled' and ready['guest']['worker'] == 'running'
    assert ready['summary'] == 'Buildroot Linux / x86 · paused while he is away from the desk'
    assert '(bundled assets)' in capsys.readouterr().out


# --- the house route says why a command was not taken ----------------------------------------------------------------
def test_operator_command_on_an_unready_guest_returns_the_reason(monkeypatch):
    from tests.test_home_api import client

    class Unready:
        def view(self):
            return {'status': 'unavailable', 'ready': False, 'output': '', 'error': 'Linux guest not installed: 3 of 3 pinned files missing',
                    'hint': 'run `python computer/bootstrap.py` once', 'summary': 'Linux guest not installed: 3 of 3 pinned files missing'}

        async def input(self, text):
            return False

    async def run():
        c, live = await client()
        live.computer = Unready()
        try:
            r = await c.post('/api/home/computer', json={'input': 'uname -a'}, headers={'X-Admin-Token': 'test'})
            assert r.status == 200
            body = await r.json()
            assert body == {'ok': False, 'status': 'unavailable', 'error': 'Linux guest not installed: 3 of 3 pinned files missing',
                            'hint': 'run `python computer/bootstrap.py` once'}
            state = await (await c.get('/api/home')).json()
            assert state['computer']['summary'].startswith('Linux guest not installed')
        finally:
            await c.close()
    asyncio.run(run())


# --- bootstrap: what is installed, and a download failure that says what failed --------------------------------------
def _manifest(monkeypatch, content=b'pinned guest bytes'):
    guest = [{'file': 'seabios.bin', 'source': 'https://copy.sh/v86/bios/seabios.bin',
              'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}]
    monkeypatch.setattr(bootstrap, 'GUEST', guest)
    return content


def test_bootstrap_status_names_the_missing_files_and_the_cache_that_has_them(tmp_path, monkeypatch):
    content = _manifest(monkeypatch)
    monkeypatch.setattr(bootstrap, 'ROOT', tmp_path / 'repo')           # a fresh clone: no .bin files
    cache = tmp_path / 'cache'
    st = bootstrap.status(cache)
    assert st == {'installed': False, 'source': None, 'missing': ['seabios.bin'], 'path': str(tmp_path / 'repo')}
    assert bootstrap.describe(st) == 'Linux guest not installed: 1 of 1 pinned files missing (seabios.bin)'
    assert 'python computer/bootstrap.py' in bootstrap.RUN_HINT
    cache.mkdir()
    (cache / 'seabios.bin').write_bytes(content)
    st = bootstrap.status(cache)
    assert st['installed'] and st['source'] == 'cache' and st['missing'] == []
    assert bootstrap.describe(st) == f'Linux guest installed (cache assets in {cache})'
    assert bootstrap.ensure(cache) == cache, 'valid cached files are used without a download'
    (cache / 'seabios.bin').write_bytes(b'corrupt')
    assert not bootstrap.status(cache)['installed'], 'a wrong size or hash counts as missing'


def test_bootstrap_download_failure_says_which_file_and_why(tmp_path, monkeypatch):
    _manifest(monkeypatch)
    monkeypatch.setattr(bootstrap, 'ROOT', tmp_path / 'repo')

    def refuse(request, timeout=30):
        raise urllib.error.URLError(OSError(101, 'Network is unreachable'))
    monkeypatch.setattr(bootstrap.urllib.request, 'urlopen', refuse)
    with pytest.raises(RuntimeError) as error:
        bootstrap.ensure(tmp_path / 'cache')
    assert str(error.value).startswith('Could not download seabios.bin from https://copy.sh/v86/bios/seabios.bin: ')
    assert 'Network is unreachable' in str(error.value)
    assert not list((tmp_path / 'cache').glob('*.bin')), 'nothing half-written is left behind'
