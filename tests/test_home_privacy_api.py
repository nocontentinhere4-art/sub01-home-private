"""Bathroom privacy is enforced by the home API, not only by the page."""

import asyncio
import ast
from pathlib import Path
from types import SimpleNamespace
from aiohttp import web
from tests.test_home_api import client


def test_privacy_withholds_screen_pixels_terminal_text_and_guest_input():
    async def run():
        http, live = await client()
        live.minecraft = SimpleNamespace(enabled=True, frame=b"real-frame-bytes", view=lambda: {"enabled": True})
        original = live.home.view
        private = {"on": False}
        live.home.view = lambda *a, **k: {**original(*a, **k), "privacy": private["on"]}
        headers = {"X-Admin-Token": "test"}
        try:
            assert (await http.get("/api/home/minecraft/frame.jpg")).status == 200
            assert (await (await http.get("/api/home/computer")).json())["output"] == "guest only"
            private["on"] = True
            frame = await http.get("/api/home/minecraft/frame.jpg")
            assert frame.status == 409 and await frame.text() == "Bathroom privacy is active"
            for path in ("/api/home/computer", "/api/home"):
                data = await (await http.get(path)).json()
                view = data if path.endswith("computer") else data["computer"]
                assert view["output"] == "" and view["privacy"] is True
            blocked = await http.post("/api/home/computer", json={"input": "ls"}, headers=headers)
            assert blocked.status == 409 and live.computer.inputs == []
            private["on"] = False
            assert (await http.get("/api/home/minecraft/frame.jpg")).status == 200
            assert (await http.post("/api/home/computer", json={"input": "ls"}, headers=headers)).status == 200
            assert live.computer.inputs == ["ls\n"]
        finally:
            await http.close()
    asyncio.run(run())


def test_bathroom_entry_during_frame_read_withholds_completed_pixels():
    # Exercise the actual nested screen handler without starting the full MRI
    # service. The browser finishes its asynchronous read after bathroom entry.
    tree = ast.parse((Path(__file__).parents[1] / 'live_server.py').read_text())
    handler = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == 'screen_shot')
    private = {'on': False}
    calls = []
    async def frame(device, expected):
        calls.append(device)
        await asyncio.sleep(0)
        private['on'] = True
        return (b'pixels from before bathroom entry', 'frame-1')
    live = SimpleNamespace(
        home=SimpleNamespace(view=lambda: {'privacy': private['on']}),
        browser=SimpleNamespace(frame=frame, screens={'desk': {'device': 'desk'}}),
        screen_status=lambda device: {'device': device})
    namespace = {'live': live, 'web': web, 'screen_showable': lambda status: True,
                 'FrameChanged': type('FrameChanged', (Exception,), {}),
                 'BrowserDown': type('BrowserDown', (Exception,), {})}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), 'actual_screen_handler', 'exec'), namespace)
    request = SimpleNamespace(match_info={'device': 'desk'}, query={})
    async def run():
        try:
            await namespace['screen_shot'](request)
        except web.HTTPConflict as error:
            assert error.text == 'Bathroom privacy is active'
        else:
            raise AssertionError('Pixels escaped after bathroom entry during the read')
        assert calls == ['desk']
    asyncio.run(run())


def test_private_observer_withholds_life_frame_identity_controller_and_gui_metadata():
    async def run():
        http, live = await client()
        original = live.home.view
        live.home.view = lambda *a, **k: {**original(*a, **k), 'privacy': True}
        live.computer.view = lambda: {'output': 'private terminal', 'ready': True,
            'display': {'kind': 'graphical', 'available': True, 'frame_id': 'private-pc'}}
        live.minecraft = SimpleNamespace(view=lambda: {'enabled': True, 'frame_id': 'private-world',
            'controller': {'pose_fresh': True, 'ack_input_id': 99}})
        live.screens = SimpleNamespace(public=lambda: {'browser': {'url': 'private-page'}})
        try:
            value = await (await http.get('/api/home')).json()
            assert value['life'] == {'privacy': True} and value['stage'] is None
            assert value['browser'] is None
            assert 'frame_id' not in value['minecraft'] and 'controller' not in value['minecraft']
            assert value['computer']['ready'] is False
            assert value['computer']['display'] == {'kind': 'private', 'available': False}
        finally:
            await http.close()
    asyncio.run(run())
