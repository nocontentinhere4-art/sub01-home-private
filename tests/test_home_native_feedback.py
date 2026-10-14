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
    assert world.view()['native_consumer'] == {'bound': True, 'required': True, 'awaiting_binding': False,
                                             'phase': 'seated', 'fresh': True, 'physical_ready': True}
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
    assert world.view()['native_consumer'] == {'bound': True, 'required': True, 'awaiting_binding': False,
                                             'phase': None, 'fresh': False, 'physical_ready': False}
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
    # Restart retains only required policy, never a serialized native result.
    restored = HomeWorld(world.to_dict())
    assert restored.native_feedback.epoch is None
    assert restored.native_feedback.required
    assert not restored.native_feedback.ready(sequence=restored.sequence, activity=restored.activity, target=restored.target)
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
                                  get_native_command=feed.get_native_command,
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


def test_private_bathroom_movement_control_and_feedback_do_not_unmask_devices():
    async def run():
        from home_world import NODES
        world = HomeWorld(); world.node = world.target = 'bathroom'
        world.position = list(NODES['bathroom']); world.activity = 'use_bathroom'; world.path = []
        clock = [100.]
        world.native_feedback = NativeFeedback(lambda: clock[0])
        live = SimpleNamespace(home=world, computer=SimpleNamespace(view=lambda: {'output':'private guest'}),
            life=SimpleNamespace(snapshot=lambda: {}), engine=SimpleNamespace(stage='AWAKE'),
            clock=SimpleNamespace(now=lambda: 123.), screen_status=lambda d: {'frame_id':'private-frame'}, browser=object())
        app = web.Application(); add_home_routes(app, live, lambda r: r.headers.get('X-Admin-Token') == TOKEN)
        backend = TestServer(app); await backend.start_server()
        direct = TestClient(backend); await direct.start_server()
        model = HomeStateModel(); model.apply_rest({'home': world.view()}); model.set_connected(True)
        feed = BackendFeed(model, str(backend.make_url('')).rstrip('/'), TOKEN)
        adapter = SimpleNamespace(post_native_state=feed.post_native_state, get_native_command=feed.get_native_command,
                                  run=lambda **kw: asyncio.sleep(3600))
        bridge_app = create_app(model, TOKEN, adapter)
        client = TestClient(TestServer(bridge_app)); await client.start_server()
        def report(phase, **patch):
            data = dict(epoch=model.epoch, sequence=world.sequence, activity='use_bathroom',
                        node='bathroom', phase=phase)
            data.update(patch); return data
        try:
            assert world.privacy()
            assert (await direct.get('/api/home/native_command')).status == 403
            assert (await client.get('/home/native_control')).status == 403
            assert (await client.get('/home/native_control', headers={'X-Admin-Token':'wrong'})).status == 403
            public = await (await client.get('/home/state', headers=AUTH)).json()
            assert public['privacy'] is True and public['actor'] is None and public['brain'] is None
            public_backend = await (await direct.get('/api/home')).json()
            assert public_backend['computer']['output'] == ''
            assert public_backend['phone_browser_screen'] == {'device':'phone','privacy':True}
            command_response = await direct.get('/api/home/native_command', headers=AUTH)
            assert command_response.headers['Cache-Control'] == 'no-store'
            command = await command_response.json()
            assert command == {'target':'bathroom','sequence':world.sequence,'activity':'use_bathroom','privacy':True}
            response = await client.get('/home/native_control', headers=AUTH)
            assert response.status == 200 and response.headers['Cache-Control'] == 'no-store'
            control = await response.json()
            assert control == {'schema':'sub01.home-state.v1','epoch':model.epoch,'source':{'status':'live'},
                               'coordinates':{'units':'cm','waypoint_height':'floor'},
                               'privacy':True,'actor':{'target':'bathroom','route_sequence':world.sequence},
                               'brain':{'activity':'use_bathroom'}}
            # Backend privacy wins when its next public bridge tick is delayed.
            model.home['privacy'] = False; model.refresh()
            assert (await (await client.get('/home/native_control',headers=AUTH)).json())['privacy'] is True
            world.node=world.target='desk'; world.position=list(NODES['desk']); world.activity='research'
            model.home['privacy'] = True; model.refresh()
            exited = await (await client.get('/home/native_control',headers=AUTH)).json()
            assert exited['privacy'] is False and exited['actor']['target'] == 'desk'
            world.node=world.target='bathroom'; world.position=list(NODES['bathroom']); world.activity='use_bathroom'
            assert (await client.post('/home/native_state', headers=AUTH, json=report('walking',bind=True,node='bath_door'))).status == 200
            assert not world.activity_ready()
            world.bladder = .9
            world.update(.2,0,{'activity':'use_bathroom'}, {})
            assert world.bladder == .9  # No simulated completion before real arrival.
            for phase, patch in [('seated',{'chair':'desk_chair'}), ('walking',{'node':'desk'}),
                                 ('arrived',{'node':'bath_door'}), ('arrived',{'sequence':99})]:
                assert (await client.post('/home/native_state', headers=AUTH, json=report(phase,**patch))).status == 409
            assert (await client.post('/home/native_state', headers=AUTH, json=report('arrived'))).status == 200
            assert world.activity_ready('use_bathroom')
            world.update(.2,0,{'activity':'use_bathroom'}, {})
            assert world.bladder < .9
            assert (await direct.post('/api/home/computer', headers=AUTH, json={'input':'uname'})).status == 409
            assert (await direct.post('/api/home/browser', headers=AUTH, json={'url':'https://example.org','device':'phone'})).status == 409
            assert (await direct.get('/api/home/minecraft/frame.jpg', headers=AUTH)).status == 409
            clock[0] += 3.01
            assert not world.activity_ready()
            assert (await client.post('/home/native_state', headers=AUTH, json=report('blocked'))).status == 200
            assert not world.activity_ready()
            # Actual remote peer rejected despite correct auth and spoofed loopback header.
            class PublicRequest:
                remote='203.0.113.2'
                headers={**AUTH,'X-Forwarded-For':'127.0.0.1'}
            for routes, path in [(app.router.routes(), '/api/home/native_command'),
                                 (bridge_app.router.routes(), '/home/native_control')]:
                handler = next(r.handler for r in routes if r.resource.canonical == path and r.method=='GET')
                try: await handler(PublicRequest())
                except web.HTTPForbidden: pass
                else: raise AssertionError('Public native movement consumer admitted')
            world.target='desk'; world.activity='research'
            assert (await direct.post('/api/home/native_state',headers=AUTH,json=report('walking',activity='research'))).status == 409
            model.set_connected(False)
            assert (await client.get('/home/native_control', headers=AUTH)).status == 409
        finally:
            await client.close(); await direct.close()
    # Browser policy import is isolated; privacy rejection occurs before use.
    with patch.dict(sys.modules, {'browse': SimpleNamespace(url_ok=lambda u: True)}):
        asyncio.run(run())


def test_native_required_policy_survives_real_serialization_and_restart(monkeypatch):
    import json
    monkeypatch.delenv('HOME_NATIVE_REQUIRED', raising=False)
    world = HomeWorld({'seated':1})
    assert world.activity_ready('research')
    assert not world.native_feedback.required
    data = dict(epoch='first-native', sequence=world.sequence, activity='research',
                node='desk', phase='walking', bind=True)
    world.native_feedback.accept(data, sequence=world.sequence, activity=world.activity, target='desk', nodes={'desk'})
    data.update(phase='seated', bind=False, chair='desk_chair')
    world.native_feedback.accept(data, sequence=world.sequence, activity=world.activity, target='desk', nodes={'desk'})
    assert world.activity_ready('research')
    saved = json.loads(json.dumps(world.to_dict()))
    assert saved['native_consumer_required'] is True
    assert not any(k.startswith('native_') for k in saved if k != 'native_consumer_required')
    restored = HomeWorld(saved)
    feedback = restored.native_feedback
    assert feedback.required and feedback.epoch is None and feedback.report is None and feedback.received is None
    assert restored.view()['native_consumer'] == {'bound':False,'required':True,'awaiting_binding':True,
                                                  'phase':None,'fresh':False,'physical_ready':False}
    restored.update(10,0,{'activity':'research'}, {})
    assert restored.seated == 1 and not restored.activity_ready('research')
    try:
        feedback.accept(data,sequence=restored.sequence,activity='research',target='desk',nodes={'desk'})
    except RuntimeError: pass
    else: raise AssertionError('Old result restored without a new native bind')
    data.update(epoch='new-native', phase='walking',bind=True,chair=None)
    feedback.accept(data,sequence=restored.sequence,activity='research',target='desk',nodes={'desk'})
    assert not restored.activity_ready('research')
    data.update(phase='seated',bind=False,chair='desk_chair')
    feedback.accept(data,sequence=restored.sequence,activity='research',target='desk',nodes={'desk'})
    assert restored.activity_ready('research')
    # Explicit startup policy closes even a new backend before its first bind.
    monkeypatch.setenv('HOME_NATIVE_REQUIRED','1')
    new_native = HomeWorld({'seated':1})
    assert new_native.native_feedback.required and not new_native.activity_ready('research')
    monkeypatch.setenv('HOME_NATIVE_REQUIRED','0')
    assert HomeWorld({'seated':1}).activity_ready('research')
    assert not HomeWorld(saved).activity_ready('research')  # Env cannot clear persisted policy.


def test_ordered_reports_reject_late_counterless_and_retired_consumers_over_http():
    async def run():
        clock=[100.]
        world=HomeWorld({'seated':1});world.native_feedback=NativeFeedback(lambda:clock[0])
        live=SimpleNamespace(home=world)
        app=web.Application();add_home_routes(app,live,lambda r:r.headers.get('X-Admin-Token')==TOKEN)
        backend=TestServer(app);await backend.start_server()
        model=HomeStateModel();model.apply_rest({'home':world.view()});model.set_connected(True)
        feed=BackendFeed(model,str(backend.make_url('')).rstrip('/'),TOKEN)
        entered,release=asyncio.Event(),asyncio.Event()
        async def ordered_post(session,data):
            if data.get('report_id')==2:
                entered.set();await release.wait()
            return await feed.post_native_state(session,data)
        adapter=SimpleNamespace(post_native_state=ordered_post,get_native_command=feed.get_native_command,
                                run=lambda **kw:asyncio.sleep(3600))
        client=TestClient(TestServer(create_app(model,TOKEN,adapter)));await client.start_server()
        first='11111111111141118111111111111111';second='22222222222242228222222222222222'
        def report(phase='walking',**patch):
            data=dict(epoch=model.epoch,sequence=world.sequence,activity=world.activity,node='desk',
                      phase=phase,consumer_id=first,report_id=1)
            if phase=='seated':data['chair']='desk_chair'
            data.update(patch);return data
        async def post(data):return await client.post('/home/native_state',headers=AUTH,json=data)
        try:
            # Legacy sender still works until an explicitly ordered binding.
            legacy=report(bind=True);legacy.pop('consumer_id');legacy.pop('report_id')
            assert (await post(legacy)).status==200
            assert (await post(report(bind=True))).status==200
            pending=asyncio.create_task(post(report(report_id=2)))
            await entered.wait();clock[0]+=1
            assert (await post(report('seated',report_id=3))).status==200
            received=world.native_feedback.received
            release.set();assert (await pending).status==409
            assert world.native_feedback.received==received and world.activity_ready()
            assert (await post(legacy)).status==409  # No downgrade, even explicit bind.
            assert (await post(report('seated',report_id=3))).status==409
            for patch in [dict(report_id=True),dict(report_id=0),dict(report_id=2**53),
                          dict(consumer_id='not-a-guid'),dict(consumer_id=None)]:
                assert (await post(report('seated',**{'report_id':4,**patch}))).status==400
                assert world.native_feedback.received==received
            only_id=report(report_id=4);only_id.pop('consumer_id')
            assert (await post(only_id)).status==400
            assert (await post(report(consumer_id=second,report_id=1))).status==409
            assert (await post(report(consumer_id=second,report_id=1,bind=True))).status==200
            assert not world.activity_ready()
            assert (await post(report('seated',consumer_id=second,report_id=4))).status==200
            received=world.native_feedback.received
            # Retired native process cannot regain authority through a late bind.
            assert (await post(report(report_id=99,bind=True))).status==409
            assert world.native_feedback.received==received and world.activity_ready()
            # Counter continues across commands instead of restarting at one.
            world.add_note('new sequence');model.apply_rest({'home':world.view()})
            assert not world.activity_ready()
            assert (await post(report(consumer_id=second,report_id=4,bind=True))).status==409
            assert (await post(report(consumer_id=second,report_id=5,bind=True))).status==200
        finally:
            release.set();await client.close();await backend.close()
    asyncio.run(run())


def test_native_bridge_forward_timeout_is_shorter_than_native_sender_timeout():
    async def run():
        gate=asyncio.Event()
        async def slow(request):
            assert request.headers.get('X-Admin-Token')==TOKEN
            await gate.wait();return web.json_response({'ok':True})
        app=web.Application();app.router.add_post('/api/home/native_state',slow)
        backend=TestServer(app);await backend.start_server()
        model=HomeStateModel();world=HomeWorld();model.apply_rest({'home':world.view()});model.set_connected(True)
        feed=BackendFeed(model,str(backend.make_url('')).rstrip('/'),TOKEN)
        adapter=SimpleNamespace(post_native_state=feed.post_native_state,get_native_command=feed.get_native_command,
                                run=lambda **kw:asyncio.sleep(3600))
        client=TestClient(TestServer(create_app(model,TOKEN,adapter)));await client.start_server()
        try:
            before=asyncio.get_running_loop().time()
            response=await client.post('/home/native_state',headers=AUTH,json=dict(epoch=model.epoch,sequence=world.sequence,
                activity=world.activity,node='desk',phase='walking',bind=True))
            elapsed=asyncio.get_running_loop().time()-before
            assert response.status==503
            assert 1.0<=elapsed<1.5
        finally:
            gate.set();await client.close();await backend.close()
    asyncio.run(run())
