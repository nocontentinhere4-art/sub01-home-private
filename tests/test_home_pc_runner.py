"""Private headless PC runner: auth, real input semantics, privacy (incl. in-flight), long-poll, idle pause."""

import asyncio
import importlib.util
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("home_pc_runner", ROOT / "scripts/home_pc_runner.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)
TOKEN = "operator-credential-test"
AUTH = {"X-Admin-Token": TOKEN}


class FakeComputer:
    """Same surface as home_computer.Computer (view/input/send/ready/paused/revision)."""

    def __init__(self):
        self.ready, self.paused, self.revision, self.output = True, True, 1, "~% "
        self.input_until, self.sent, self.inputs, self.gate = 0.0, [], [], None

    def view(self):
        return {"status": "ready", "ready": self.ready, "paused": self.paused,
                "output": self.output, "last_command": "", "revision": self.revision}

    async def send(self, message):
        self.sent.append(message["type"])
        return True

    async def input(self, text):
        if self.gate:
            await self.gate.wait()
        self.inputs.append(text)
        self.paused = False
        self.revision += 1
        return True


async def started(clock=None):
    computer = FakeComputer()
    runner = pc.PCRunner(computer, TOKEN, **({"clock": clock} if clock else {}))
    http = TestClient(TestServer(pc.create_app(runner)))
    await http.start_server()
    return http, runner, computer


def run(coro):
    asyncio.run(coro)


def test_every_route_but_health_requires_the_operator_credential():
    async def body():
        http, _, computer = await started()
        try:
            assert (await http.get("/healthz")).status == 200
            for method, path in [("get", "/pc/state"), ("post", "/pc/input"), ("post", "/pc/session"), ("post", "/pc/privacy")]:
                assert (await getattr(http, method)(path, json={})).status == 403
                assert (await getattr(http, method)(path, json={}, headers={"X-Admin-Token": "wrong-credential-x"})).status == 403
            assert computer.inputs == []
        finally:
            await http.close()
    run(body())


def test_input_reaches_the_guest_console_with_existing_semantics():
    async def body():
        http, _, computer = await started()
        try:
            r = await http.post("/pc/input", json={"input": "uname -m"}, headers=AUTH)
            assert r.status == 200 and (await r.json()) == {"ok": True, "revision": 2}
            await http.post("/pc/input", json={"input": "q", "raw": True}, headers=AUTH)
            assert computer.inputs == ["uname -m\n", "q"]
            assert (await http.post("/pc/input", json={"input": "x" * 2001}, headers=AUTH)).status == 400
            assert (await http.post("/pc/input", json={"input": 5}, headers=AUTH)).status == 400
            assert (await http.post("/pc/input", data=b"[]", headers=AUTH)).status == 400
            assert (await http.post("/pc/input", data=b"x" * 5000, headers=AUTH)).status == 413
        finally:
            await http.close()
    run(body())


def test_privacy_blanks_state_and_refuses_input_including_in_flight():
    async def body():
        http, runner, computer = await started()
        try:
            computer.output, computer.paused = "secret terminal", False
            computer.gate = asyncio.Event()
            pending = asyncio.ensure_future(http.post("/pc/input", json={"input": "ls"}, headers=AUTH))
            await asyncio.sleep(0.05)
            on = await http.post("/pc/privacy", json={"active": True}, headers=AUTH)
            assert (await on.json())["output"] == "" and "pause" in computer.sent
            computer.gate.set()
            late = await pending
            assert late.status == 409 and "secret" not in await late.text()
            state = await (await http.get("/pc/state", headers=AUTH)).json()
            assert state == {"status": "ready", "ready": True, "paused": True, "output": "",
                             "last_command": None, "revision": None, "privacy": True}
            refused = await http.post("/pc/input", json={"input": "ls"}, headers=AUTH)
            assert refused.status == 409 and await refused.text() == "Bathroom privacy is active"
            assert (await http.post("/pc/session", json={"active": True}, headers=AUTH)).status == 409
            await http.post("/pc/privacy", json={"active": False}, headers=AUTH)
            assert (await (await http.get("/pc/state", headers=AUTH)).json())["output"] == "secret terminal"
        finally:
            await http.close()
    run(body())


def test_long_poll_returns_on_revision_and_privacy_change_and_masks_after_waiting():
    async def body():
        http, runner, computer = await started()
        try:
            r = await http.get("/pc/state?since=1&wait=0", headers=AUTH)
            assert (await r.json())["revision"] == 1
            waiting = asyncio.ensure_future(http.get("/pc/state?since=1&wait=5", headers=AUTH))
            await asyncio.sleep(0.05)
            computer.output, computer.revision = "~% ls\nbin", 2
            runner.notify()
            assert (await (await waiting).json())["revision"] == 2
            waiting = asyncio.ensure_future(http.get("/pc/state?since=2&wait=5", headers=AUTH))
            await asyncio.sleep(0.05)
            await runner.set_privacy(True)
            assert (await (await waiting).json())["output"] == "", "a waiter released by privacy sees the masked view"
            assert (await http.get("/pc/state?since=x", headers=AUTH)).status == 400
        finally:
            await http.close()
    run(body())


def test_session_keeps_vm_running_and_idle_pauses_it():
    async def body():
        now = [100.0]
        http, runner, computer = await started(clock=lambda: now[0])
        try:
            r = await http.post("/pc/session", json={"active": True}, headers=AUTH)
            assert (await r.json())["session"] is True and computer.sent == ["resume"] and not computer.paused
            await runner.idle_step()
            assert computer.paused is False
            now[0] += pc.SESSION_SECONDS + 1
            await runner.idle_step()
            assert computer.paused is True and computer.sent[-1] == "pause"
        finally:
            await http.close()
    run(body())


def test_runner_refuses_public_binds_weak_credentials_and_repo_data(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        pc.PCRunner(FakeComputer(), "short")
    monkeypatch.setenv("SUB01_ADMIN_TOKEN", TOKEN)
    for argv in (["--host", "0.0.0.0", "--data-dir", str(tmp_path)],
                 ["--data-dir", str(ROOT / "runtime")]):
        with pytest.raises(SystemExit):
            pc.main(argv)
    monkeypatch.setenv("SUB01_ADMIN_TOKEN", "")
    with pytest.raises(SystemExit):
        pc.main(["--data-dir", str(tmp_path)])
    token_file = tmp_path / "token"
    token_file.write_text(TOKEN + "\n")
    assert pc.load_token(str(token_file)) == TOKEN
    assert TOKEN not in (pc.__doc__ or "")


def test_privacy_beginning_during_session_resume_never_leaves_the_guest_running():
    async def body():
        http, runner, computer = await started()
        try:
            computer.output = "secret terminal"
            gate, original = asyncio.Event(), computer.send

            async def slow_send(message):
                if message["type"] == "resume":
                    computer.sent.append("resume")  # written to the worker; drain still pending
                    await gate.wait()
                    return True
                return await original(message)

            computer.send = slow_send
            pending = asyncio.ensure_future(http.post("/pc/session", json={"active": True}, headers=AUTH))
            await asyncio.sleep(0.05)
            assert computer.sent == ["resume"]
            await runner.set_privacy(True)
            gate.set()
            response = await (await pending).json()
            assert response["output"] == "" and response["privacy"] is True, "response stays masked"
            assert computer.sent[-1] == "pause", "the worker's last command is a pause, after the resume"
            assert computer.paused is True and runner.session_until == 0.0, "no session survives privacy"
            await runner.idle_step()
            assert computer.sent[-1] == "pause"
        finally:
            await http.close()
    run(body())


def test_raw_input_stays_one_json_line_to_the_isolated_worker(tmp_path):
    """Raw text (even with newlines or JSON) is one escaped `input` message for the
    v86 serial console; it can never become a second worker command or a host shell."""
    from home_computer import Computer

    class Pipe:
        def __init__(self):
            self.data = b""

        def write(self, data):
            self.data += data

        async def drain(self):
            pass

    async def body():
        computer = Computer(tmp_path)
        computer.ready = True
        computer.process = type("P", (), {"returncode": None, "stdin": Pipe()})()
        payload = 'x\n{"type": "shutdown"}\n$(reboot)\u0003'
        assert await computer.input(payload)
        lines = computer.process.stdin.data.decode().splitlines()
        assert len(lines) == 1
        message = __import__("json").loads(lines[0])
        assert message == {"type": "input", "text": payload}
    run(body())


def test_actual_frame_protocol_requires_auth_revision_and_privacy():
    async def body():
        http, runner, computer = await started()
        try:
            assert (await http.get('/pc/frame.png')).status == 403
            assert (await http.get('/pc/frame.png', headers=AUTH)).status == 404
            computer.framebuffer_png = b'\x89PNG\r\n\x1a\nactual-test-frame'
            computer.display = {'kind': 'graphical', 'available': True, 'revision': 12}
            response = await http.get('/pc/frame.png?revision=12', headers=AUTH)
            assert response.status == 200 and await response.read() == computer.framebuffer_png
            assert response.headers['Cache-Control'] == 'no-store'
            assert response.headers['ETag'] == '"vga-12"'
            assert (await http.get('/pc/frame.png?revision=11', headers=AUTH)).status == 409
            assert (await http.get('/pc/frame.png', headers={**AUTH, 'If-None-Match': '"vga-12"'})).status == 304
            await runner.set_privacy(True)
            assert (await http.get('/pc/frame.png', headers={**AUTH, 'If-None-Match': '"vga-12"'})).status == 409
            state = await (await http.get('/pc/state', headers=AUTH)).json()
            assert 'display' not in state and state['output'] == ''
        finally:
            await http.close()
    run(body())



def test_graphical_guest_ps2_input_is_bounded_authenticated_and_privacy_safe():
    async def body():
        http, runner, computer = await started()
        events = []
        gate = asyncio.Event()
        async def guest_input(data):
            if data.get('scancodes') == [30, 158]:
                await gate.wait()
            events.append(data)
            return True
        computer.graphical_input = guest_input
        try:
            assert (await http.post('/pc/graphical-input', json={'type': 'vga-keyboard', 'scancodes': [30]})).status == 403
            assert (await http.post('/pc/graphical-input', json={'type': 'vga-keyboard', 'scancodes': [30]}, headers=AUTH)).status == 409
            computer.display = {'kind': 'graphical', 'available': True, 'revision': 1}
            assert (await http.post('/pc/graphical-input', json={'type': 'vga-keyboard', 'scancodes': [256]}, headers=AUTH)).status == 400
            assert (await http.post('/pc/graphical-input', json={'type': 'vga-keyboard', 'scancodes': [True]}, headers=AUTH)).status == 400
            mouse = {'type': 'vga-mouse', 'dx': 4, 'dy': -2, 'wheel': 0, 'buttons': [True, False, False]}
            assert (await http.post('/pc/graphical-input', json=mouse, headers=AUTH)).status == 200
            assert events == [mouse]
            pending = asyncio.ensure_future(http.post('/pc/graphical-input', json={'type': 'vga-keyboard', 'scancodes': [30, 158]}, headers=AUTH))
            await asyncio.sleep(.01)
            await runner.set_privacy(True)
            gate.set()
            assert (await pending).status == 409
            assert computer.paused and computer.sent[-1] == 'pause'
            assert (await http.post('/pc/graphical-input', json=mouse, headers=AUTH)).status == 409
        finally:
            gate.set()
            await http.close()
    run(body())


def test_home_release_cannot_clear_native_focus_and_leases_expire_independently():
    async def body():
        now = [100.0]
        http, runner, computer = await started(clock=lambda: now[0])
        try:
            for source in ('native', 'home'):
                assert (await http.post('/pc/session', json={'active': True, 'source': source}, headers=AUTH)).status == 200
            await http.post('/pc/session', json={'active': False, 'source': 'home'}, headers=AUTH)
            await runner.idle_step()
            assert runner.view()['session'] and not computer.paused
            now[0] = 150
            await http.post('/pc/session', json={'active': True, 'source': 'home'}, headers=AUTH)
            now[0] = 161  # native expired; home remains active
            await runner.idle_step()
            assert not computer.paused
            await http.post('/pc/session', json={'active': False}, headers=AUTH)
            await runner.idle_step()
            assert not computer.paused, 'legacy native release cannot clear home lease'
            now[0] = 211
            await runner.idle_step()
            assert computer.paused
            assert (await http.post('/pc/session', json={'active': True, 'source': 'other'}, headers=AUTH)).status == 400
        finally:
            await http.close()
    run(body())


def test_new_operator_focus_during_idle_pause_is_resumed_but_privacy_clears_both():
    async def body():
        http, runner, computer = await started()
        try:
            computer.paused = False
            gate = asyncio.Event()
            original = computer.send
            async def slow_pause(message):
                if message['type'] == 'pause':
                    computer.sent.append('pause')
                    await gate.wait()
                    return True
                return await original(message)
            computer.send = slow_pause
            pending = asyncio.create_task(runner.idle_step())
            await asyncio.sleep(0)
            await runner.set_session(True, 'native')
            gate.set()
            await pending
            assert computer.sent == ['pause', 'resume'] and not computer.paused
            await runner.set_session(True, 'home')
            await runner.set_privacy(True, 'home')
            assert computer.paused and runner.session_until == 0
            await runner.set_privacy(False, 'home')
            assert not runner.view()['session'], 'clearing privacy cannot revive old focus'
        finally:
            await http.close()
    run(body())
