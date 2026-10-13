"""Real router roundtrip and ephemeral physical-consumer readiness contract."""
import asyncio
import ast
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from home_world import HomeWorld
from home_native_feedback import NativeFeedback
from tools.unreal_home_state_bridge import HomeStateModel, BackendFeed, create_app

# Load the real HTTP router without importing the unrelated numerical brain.
# Its only life dependency is this literal activity catalog, read from source.
ROOT = Path(__file__).resolve().parents[1]
activities = next(ast.literal_eval(n.value) for n in ast.parse((ROOT / 'life.py').read_text()).body
                  if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'ACTIVITIES' for t in n.targets))
spec = importlib.util.spec_from_file_location('_native_route_home_api', ROOT / 'home_api.py')
router = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'life': SimpleNamespace(ACTIVITIES=activities)}):
    spec.loader.exec_module(router)
add_home_routes = router.add_home_routes

TOKEN = 'private-test-operator'
AUTH = {'X-Admin-Token': TOKEN}


def test_feedback_readiness_expiry_and_station_identity():
    now = [100.0]
    world = HomeWorld()
    world.seated = 1
    world.native_feedback = NativeFeedback(lambda: now[0])
    assert world.activity_ready('research')
    def report(phase, **patch):
        data = dict(epoch='native-one', sequence=world.sequence, activity=world.activity,
                    node=world.target, phase=phase, chair='desk_chair')
        data.update(patch)
        world.native_feedback.accept(data, sequence=world.sequence, activity=world.activity,
                                     target=world.target, nodes={'desk', 'kitchen'})
    report('walking', bind=True)
    assert not world.activity_ready()
    report('arrived')
    assert not world.activity_ready()
    report('seated')
    assert world.activity_ready()
    assert world.view()['native_consumer'] == {'bound': True, 'phase': 'seated', 'fresh': True, 'physical_ready': True}
    now[0] += 2
    for patch in [dict(sequence=42), dict(epoch='stale'), dict(chair='made-up-chair'), dict(sequence=True)]:
        try:
            report('seated', **patch)
        except (ValueError, RuntimeError):
            pass
        else:
            raise AssertionError('Invalid feedback accepted')
    now[0] += 1.01
    assert not world.activity_ready()  # Failed reports did not renew evidence.
    assert world.view()['native_consumer'] == {'bound': True, 'phase': None, 'fresh': False, 'physical_ready': False}
    report('blocked')
    assert not world.activity_ready()
    report('seated')
    world.activity = 'use_computer'  # Same node and sequence, different command.
    assert not world.activity_ready()
    report('walking', bind=True, epoch='native-two')
    assert not world.activity_ready()
    world.node = world.target = 'kitchen'
    world.activity = 'eat'
    report('arrived', epoch='native-two', chair=None)
    assert world.native_feedback.ready(sequence=world.sequence, activity='eat', target='kitchen')
    # Restart retains browser timer behavior, never a serialized native seat.
    restored = HomeWorld(world.to_dict())
    assert restored.native_feedback.epoch is None
    for target, activity, chair in [('sofa', 'play_console', 'sofa'), ('bed', 'phone', 'bed')]:
        world.node = world.target = target; world.activity = activity; world.seated = 1
        data = dict(epoch='native-two', sequence=world.sequence, activity=activity,
                    node=target, phase='arrived')
        world.native_feedback.accept(data, sequence=world.sequence, activity=activity, target=target, nodes={target})
        assert not world.activity_ready()
        data.update(phase='seated', chair=chair)
        world.native_feedback.accept(data, sequence=world.sequence, activity=activity, target=target, nodes={target})
        assert world.activity_ready()
    assert world.add_note('new home revision')
    assert not world.activity_ready()  # The actual sequence mutation invalidates the old seat.
    assert not world.view()['native_consumer']['physical_ready']


def test_actual_bridge_backend_feedback_route_auth_epoch_and_privacy():
    async def run():
        world = HomeWorld(); world.seated = 1
        live = SimpleNamespace(home=world)
        app = web.Application()
        add_home_routes(app, live, lambda r: r.headers.get('X-Admin-Token') == TOKEN)
        backend = TestServer(app); await backend.start_server()
        model = HomeStateModel(); model.apply_rest({'home': world.view()}); model.set_connected(True)
        feed = BackendFeed(model, str(backend.make_url('')).rstrip('/'), TOKEN)
        # Only the actual POST adapter is needed; no persistent feed task.
        adapter = SimpleNamespace(post_native_state=feed.post_native_state,
                                  run=lambda **kw: asyncio.sleep(3600))
        client = TestClient(TestServer(create_app(model, TOKEN, adapter)))
        await client.start_server()
        direct = TestClient(backend); await direct.start_server()
        def report(phase_name='walking', **patch):
            d = dict(epoch=model.epoch, sequence=world.sequence, activity=world.activity,
                     node='desk', phase=phase_name, bind=phase_name == 'walking')
            if phase_name == 'seated': d['chair'] = 'desk_chair'
            d.update(patch); return d
        try:
            assert (await client.post('/home/native_state', json=report())).status == 403
            assert (await direct.post('/api/home/native_state', json=report())).status == 403
            assert world.native_feedback.epoch is None
            assert (await client.post('/home/native_state', json=report(epoch='old'), headers=AUTH)).status == 409
            assert world.native_feedback.epoch is None
            assert (await client.post('/home/native_state', json=report(node={}), headers=AUTH)).status == 400
            assert world.native_feedback.epoch is None
            assert (await client.post('/home/native_state', json=report(), headers=AUTH)).status == 200
            assert world.native_feedback.epoch == model.epoch
            assert not world.activity_ready()
            assert (await client.post('/home/native_state', json=report('arrived'), headers=AUTH)).status == 200
            assert not world.activity_ready()
            assert (await client.post('/home/native_state', json=report('seated'), headers=AUTH)).status == 200
            assert world.activity_ready()
            received = world.native_feedback.received
            for patch, status in [(dict(sequence=True),409), (dict(chair='unknown'),400),
                                  (dict(sequence=world.sequence+1),409), (dict(extra=1),400),
                                  (dict(node=[]),400), (dict(phase=[]),400), (dict(bind='yes'),400)]:
                assert (await client.post('/home/native_state', json=report('seated', **patch), headers=AUTH)).status == status
                assert world.native_feedback.received == received
            world.activity = 'use_computer'
            assert (await client.post('/home/native_state', json=report('seated'), headers=AUTH)).status == 409
            model.apply_rest({'home': world.view()})
            assert (await client.post('/home/native_state', json=report('blocked'), headers=AUTH)).status == 200
            assert not world.activity_ready()
            model.home['privacy'] = True; model.refresh()
            assert (await client.post('/home/native_state', json=report('seated'), headers=AUTH)).status == 409
            # Freshness is unchanged when the real backend becomes private,
            # even before the bridge has received the newer privacy tick.
            model.home['privacy'] = False; model.refresh()
            world.node = 'bathroom'
            assert world.view()['native_consumer'] is None
            received = world.native_feedback.received
            assert (await client.post('/home/native_state', json=report('seated'), headers=AUTH)).status == 409
            assert world.native_feedback.received == received
            # No spoofed forwarded address permits public binding: actual peer is authoritative.
            class RemoteRequest:
                remote = '203.0.113.5'
                headers = AUTH
            handler = next(r.handler for r in app.router.routes() if r.resource.canonical == '/api/home/native_state')
            try:
                await handler(RemoteRequest())
            except web.HTTPForbidden:
                pass
            else:
                raise AssertionError('Public native consumer accepted')
        finally:
            await client.close(); await direct.close()
    asyncio.run(run())


def test_phone_proxy_targets_actual_registered_navigation_route():
    async def run():
        from scripts.home_device_proxy import HomeDeviceProxy
        calls = []
        async def navigate(device, url):
            calls.append((device, url)); return {'frame_id': 'new-frame'}
        async def on_screen(status):
            pass
        home = HomeWorld()
        live = SimpleNamespace(home=home, browser=SimpleNamespace(navigate=navigate), on_screen=on_screen)
        app = web.Application()
        add_home_routes(app, live, lambda r: r.headers.get('X-Admin-Token') == TOKEN)
        backend = TestServer(app); await backend.start_server()
        proxy = HomeDeviceProxy(str(backend.make_url('')).rstrip('/'), TOKEN,
                                SimpleNamespace(privacy=False, privacy_epoch=0))
        # Proxy state ordinarily contains full device data. Keep the real POST
        # router under test while using a minimal actual-home snapshot here.
        original_request = proxy.request
        async def request(method, path, **kwargs):
            if method == 'GET' and path == '/api/home':
                import json
                return json.dumps({'home': home.view()}).encode(), 'application/json', None
            return await original_request(method, path, **kwargs)
        proxy.request = request
        app = web.Application(); app.router.add_post('/{device}/action', proxy.action)
        client = TestClient(TestServer(app)); await client.start_server()
        # Real navigate imports browse's policy; inject only that unrelated
        # policy dependency to avoid numerical/browser runtime imports.
        try:
            with patch.dict(sys.modules, {'browse': SimpleNamespace(url_ok=lambda u: u == 'https://example.org/page')}):
                response = await client.post('/phone/action', json={'action':'navigate', 'url':'https://example.org/page'})
                assert response.status == 200
            assert calls == [('phone', 'https://example.org/page')]
        finally:
            await client.close(); await proxy.close(); await backend.close()
    asyncio.run(run())
