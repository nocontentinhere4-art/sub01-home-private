"""Exercise the real renderer loop with deferred page I/O; no Chromium/game launch."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_minecraft import MinecraftConsole

class Page:
    def __init__(self):
        self.navigations = []
        self.shots = 0
        self.defer = None
        self.shot_started = asyncio.Event()
        self.fail_navigation = False
        self.terrain_ready = True

    async def goto(self, url, **kwargs):
        self.navigations.append(url)
        if self.fail_navigation and url != 'about:blank':
            self.fail_navigation = False
            raise RuntimeError('Viewer disconnected')

    async def wait_for_selector(self, selector, **kwargs):
        assert selector == 'canvas'

    async def wait_for_function(self, predicate, **kwargs):
        assert 'sub01TerrainReady' in predicate
        if not self.terrain_ready:
            raise RuntimeError('Actual terrain meshes or textures unavailable')

    async def screenshot(self, **kwargs):
        self.shots += 1
        self.shot_started.set()
        if self.defer is not None:
            frame = await self.defer
            self.defer = None
            return frame
        return f'JPEG-{self.shots}'.encode()

class Harness:
    def __init__(self, console, page):
        self.console, self.page = console, page
        self.waits = asyncio.Queue()
        self.task = asyncio.create_task(console._render_frame_loop(page, self.sleep))

    async def sleep(self, delay):
        future = asyncio.get_running_loop().create_future()
        await self.waits.put((delay, future))
        await future

    async def waiting(self):
        return await asyncio.wait_for(self.waits.get(), 1)

    async def close(self):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass

class RendererTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.console = MinecraftConsole(self.directory.name)
        self.console.worker = object()
        self.console.server = object()
        self.messages = []
        async def send(message):
            self.messages.append(message)
            return True
        self.console.send = send

    def tearDown(self):
        self.directory.cleanup()

    def state(self, connected=True, active=False):
        self.console.active = active
        self.console.state = {'connected': connected, 'active': active}
        self.console._render_generation += 1

    async def test_one_bootstrap_then_blank_pause_resume_and_reconnect(self):
        self.state()
        page = Page();h = Harness(self.console, page)
        _, wait = await h.waiting()
        self.assertEqual(page.shots, 1)
        self.assertEqual(page.navigations[-1], 'about:blank')
        self.assertEqual(self.console.frame_kind, 'initial_idle')
        self.assertEqual(self.messages, [{'type': 'viewer_release'}])
        saved = self.console.frame
        for _ in range(3):
            wait.set_result(None);_, wait = await h.waiting()
        self.assertEqual(page.shots, 1)
        self.assertEqual(len(page.navigations), 2, 'paused bootstrap viewer unloads exactly once')
        self.state(active=True);wait.set_result(None);delay, wait = await h.waiting()
        self.assertEqual(delay, .125);self.assertEqual(page.shots, 2)
        self.assertNotEqual(self.console.frame, saved)
        self.state(active=False);wait.set_result(None);_, wait = await h.waiting()
        retained = self.console.frame
        self.assertEqual(page.navigations[-1], 'about:blank')
        self.state(connected=False);wait.set_result(None);_, wait = await h.waiting()
        self.state(connected=True);wait.set_result(None);_, wait = await h.waiting()
        self.assertEqual(page.shots, 2, 'reconnect while paused retains last real frame without another bootstrap')
        self.assertEqual(self.console.frame, retained)
        self.assertIsNotNone(self.console.worker);self.assertIsNotNone(self.console.server)
        await h.close()

    async def test_late_frame_cannot_replace_cache_after_pause_or_reconnect(self):
        for disconnect in (False, True):
            with self.subTest(disconnect=disconnect):
                self.state(active=True);self.console.frame = b'last-valid-JPEG'
                page = Page();page.defer = asyncio.get_running_loop().create_future();h = Harness(self.console, page)
                await asyncio.wait_for(page.shot_started.wait(), 1)
                self.state(connected=not disconnect, active=False)
                page.defer.set_result(b'late-old-JPEG')
                _, wait = await h.waiting()
                self.assertEqual(self.console.frame, b'last-valid-JPEG')
                self.assertEqual(page.navigations[-1], 'about:blank')
                wait.set_result(None);_, wait = await h.waiting()
                self.assertEqual(page.shots, 1)
                await h.close()

    async def test_leave_return_epoch_rejects_old_screenshot(self):
        self.state(active=True);self.console.frame = b'old-cache'
        page = Page();page.defer = asyncio.get_running_loop().create_future();h = Harness(self.console, page)
        await asyncio.wait_for(page.shot_started.wait(), 1)
        self.state(active=False);self.state(active=True)
        page.defer.set_result(b'old-owner')
        _, wait = await h.waiting();self.assertEqual(self.console.frame, b'old-cache')
        wait.set_result(None);_, wait = await h.waiting();self.assertEqual(self.console.frame, b'JPEG-2')
        await h.close()

    async def test_navigation_failure_blanks_and_retries_without_losing_world(self):
        self.state(active=True);self.console.frame = b'last-frame'
        page = Page();page.fail_navigation = True;h = Harness(self.console, page)
        _, wait = await h.waiting()
        self.assertEqual(page.navigations[-1], 'about:blank');self.assertEqual(page.shots, 0)
        self.assertEqual(self.console.frame, b'last-frame')
        self.assertTrue(self.console.error.startswith('Minecraft viewer: '))
        wait.set_result(None);_, wait = await h.waiting()
        self.assertEqual(page.shots, 1);self.assertEqual(self.console.error, '')
        await h.close()

    async def test_canvas_without_real_terrain_does_not_publish_idle_frame(self):
        self.state(); page = Page(); page.terrain_ready = False
        h = Harness(self.console, page)
        _, wait = await h.waiting()
        self.assertEqual(page.shots, 0)
        self.assertIsNone(self.console.frame)
        self.assertEqual(self.messages, [], 'No capture or release acknowledgment fabricated')
        self.assertEqual(page.navigations[-1], 'about:blank')
        page.terrain_ready = True; wait.set_result(None)
        _, wait = await h.waiting()
        self.assertEqual(page.shots, 1)
        self.assertEqual(self.messages, [{'type': 'viewer_release'}])
        await h.close()

    async def test_worker_ack_and_connection_changes_invalidate_actual_owner(self):
        self.console.enabled = True
        self.console.state = {'connected': True, 'active': False}
        self.console.send = lambda _message: asyncio.sleep(0, result=True)
        home = SimpleNamespace(activity='play_console', activity_ready=lambda _activity: True, console_game='minecraft')
        owner = self.console._render_owner()
        await self.console.agent_step(home, {})
        self.assertNotEqual(self.console._render_owner(), owner)
        self.console.frame = b'cached'
        page = Page();h = Harness(self.console, page)
        _, wait = await h.waiting();self.assertEqual(page.shots, 0, 'no viewer before actual worker active acknowledgement')
        class Stream:
            def __init__(self):self.lines=[json.dumps({'type':'state','connected':True,'active':True}).encode()+b'\n',b'']
            async def readline(self):return self.lines.pop(0)
        self.console.worker = SimpleNamespace(stdout=Stream())
        before = self.console._render_owner();await self.console.read_worker();self.assertNotEqual(self.console._render_owner(), before)
        wait.set_result(None);_, wait = await h.waiting();self.assertEqual(page.shots, 1)
        await h.close()

    async def test_render_frames_cancellation_closes_browser_even_during_page_acquisition(self):
        for acquiring in (False, True):
            with self.subTest(acquiring=acquiring):
                self.state(active=True);self.console.frame = b'cached'
                page = Page();page.defer = asyncio.get_running_loop().create_future()
                acquisition = asyncio.Event();closed=[]
                async def new_page(**kwargs):
                    acquisition.set()
                    if acquiring:await asyncio.Future()
                    return page
                async def close():closed.append(True)
                browser = SimpleNamespace(new_page=new_page, close=close)
                async def launch(**kwargs):return browser
                class Context:
                    async def __aenter__(self):return SimpleNamespace(chromium=SimpleNamespace(launch=launch))
                    async def __aexit__(self,*args):pass
                module=ModuleType('playwright.async_api');module.async_playwright=lambda:Context()
                with patch.dict(sys.modules,{'playwright':ModuleType('playwright'),'playwright.async_api':module}):
                    task=asyncio.create_task(self.console.render_frames())
                    await asyncio.wait_for(acquisition.wait() if acquiring else page.shot_started.wait(),1)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):await task
                self.assertEqual(closed,[True]);self.assertEqual(self.console.frame,b'cached')

    async def test_frame_receipt_uses_actual_viewer_entities_and_new_pixel_identity(self):
        self.state(); self.console.directory.mkdir()
        page = Page()
        actual_receipts = [{'id': 921, 'type': 110, 'name': 'oak_log', 'count': 1,
                            'status': 'textured_registry_log'}]
        async def evaluate(expression):
            self.assertIn('sub01ItemRenderReceipts', expression)
            return actual_receipts
        page.evaluate = evaluate
        h = Harness(self.console, page)
        await h.waiting()
        receipt = json.loads((self.console.directory / 'frame-rendering.json').read_text())
        self.assertEqual(receipt['entities'], actual_receipts)
        self.assertEqual(receipt['frame_tag'], self.console.frame_tag)
        self.assertEqual(self.console.frame_kind, 'initial_idle')
        await h.close()

if __name__ == '__main__':unittest.main()
