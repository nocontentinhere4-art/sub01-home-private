"""Actual-backend proxy protocol and async privacy checks, no rendering fixtures."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('device_proxy',ROOT/'scripts/home_device_proxy.py');proxy=importlib.util.module_from_spec(spec);spec.loader.exec_module(proxy)


def test_origin_refuses_public_redirect_style_and_credentials():
    assert proxy.loopback_origin('http://127.0.0.1:8811')=='http://127.0.0.1:8811'
    for value in ['https://example.com:80','http://127.0.0.1:8811@evil:80','http://localhost:8811/path','http://localhost:8811?secret=1']:
        with pytest.raises(ValueError):proxy.loopback_origin(value)


def test_actual_phone_pixels_actions_and_midflight_privacy():
    async def run():
        private={'native':False,'home':False};epoch={'v':0};calls=[];gate=asyncio.Event();block=False
        async def state(request):
            assert request.headers['X-Admin-Token']=='existing-operator'
            return web.json_response({'home':{'privacy':private['home'],'console_game':'minecraft'},'phone_browser_screen':{'frame_id':'frame-a'},'minecraft':{'enabled':True}})
        async def image(request):
            assert request.query['frame_id']=='frame-a'
            if block:await gate.wait()
            return web.Response(body=b'actual-backend-pixel-fixture',content_type='image/jpeg')
        async def action(request):calls.append(await request.json());return web.json_response({'ok':True})
        app=web.Application();app.router.add_get('/api/home',state);app.router.add_get('/api/screen/phone.jpg',image);app.router.add_post('/api/home/browser/action',action)
        upstream=TestServer(app);await upstream.start_server()
        runner=SimpleNamespace(privacy=False,privacy_epoch=0)
        device=proxy.HomeDeviceProxy(str(upstream.make_url('')).rstrip('/'),'existing-operator',runner)
        server=web.Application();server.router.add_get('/{device}/frame',device.frame);server.router.add_post('/{device}/action',device.action)
        client=TestClient(TestServer(server));await client.start_server()
        try:
            response=await client.get('/phone/frame?frame_id=frame-a');assert response.status==200;assert await response.read()==b'actual-backend-pixel-fixture';assert response.headers['Cache-Control']=='no-store'
            assert (await client.get('/phone/frame?frame_id=stale')).status==409
            assert (await client.post('/phone/action',json={'action':'scroll_down','frame_id':'frame-a'})).status==200
            assert calls==[{'device':'phone','action':'scroll_down','frame_id':'frame-a'}]
            block=True;pending=asyncio.ensure_future(client.get('/phone/frame'));await asyncio.sleep(.01);private['home']=True;gate.set();assert (await pending).status==409
            private['home']=False;gate.clear();pending=asyncio.ensure_future(client.get('/phone/frame'));await asyncio.sleep(.01);runner.privacy=True;runner.privacy_epoch+=1;gate.set();assert (await pending).status==409
        finally:
            gate.set();await client.close();await device.close();await upstream.close()
    asyncio.run(run())


def test_phone_navigation_uses_current_frame_auth_and_private_backend():
    async def run():
        current = {'frame': 'current-a', 'private': False}
        calls = []
        entered, release = asyncio.Event(), asyncio.Event()
        blocked = False
        runner = SimpleNamespace(privacy=False, privacy_epoch=0)
        async def state(request):
            assert request.headers['X-Admin-Token'] == 'existing-operator'
            return web.json_response({'home': {'privacy': current['private']},
                                      'phone_browser_screen': {'frame_id': current['frame']}})
        async def navigate(request):
            assert request.headers['X-Admin-Token'] == 'existing-operator'
            calls.append(await request.json())
            if blocked:
                entered.set()
                await release.wait()
            return web.json_response({'ok': True})
        app = web.Application()
        app.router.add_get('/api/home', state)
        app.router.add_post('/api/home/browser', navigate)
        upstream = TestServer(app)
        await upstream.start_server()
        device = proxy.HomeDeviceProxy(str(upstream.make_url('')).rstrip('/'), 'existing-operator', runner)
        app = web.Application()
        app.router.add_post('/{device}/action', device.action)
        # The standalone runner applies authentication before this proxy handler.
        client = TestClient(TestServer(app))
        await client.start_server()
        def body(url='https://example.org/page', frame='current-a'):
            return {'action': 'navigate', 'url': url, 'frame_id': frame}
        try:
            assert (await client.post('/phone/action', json=body())).status == 200
            assert calls == [{'device': 'phone', 'url': 'https://example.org/page'}]
            for url in ['http://example.org', 'https://127.0.0.1', 'https://[::1]',
                        'https://169.254.169.254', 'https://localhost', 'https://host.internal',
                        'https://u:p@example.org', 'https://example.org:444', 'javascript:alert(1)',
                        'https://example.org/\npage', 'https://bad_.org', 'https://[broken']:
                assert (await client.post('/phone/action', json=body(url))).status == 400
            assert len(calls) == 1
            assert (await client.post('/phone/action', json=body(frame='stale'))).status == 409
            assert (await client.post('/phone/action', json=body(frame=None))).status == 409
            current['frame'] = None
            assert (await client.post('/phone/action', json=body(frame=['bad']))).status == 409
            assert (await client.post('/phone/action', json=body(frame=None))).status == 200
            assert len(calls) == 2
            blocked = True
            pending = asyncio.ensure_future(client.post('/phone/action', json=body(frame=None)))
            await entered.wait()
            current['private'] = True
            release.set()
            assert (await pending).status == 409
            current['private'] = False
            entered.clear(); release.clear()
            pending = asyncio.ensure_future(client.post('/phone/action', json=body(frame=None)))
            await entered.wait()
            runner.privacy = True; runner.privacy_epoch += 1
            release.set()
            assert (await pending).status == 409
            assert (await client.post('/phone/action', json=body(frame=None))).status == 409
            assert len(calls) == 4
        finally:
            release.set()
            await client.close(); await device.close(); await upstream.close()
    asyncio.run(run())
