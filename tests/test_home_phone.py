"""Actual registered phone HTTP routes, real JPEGs and untouched saved entries."""
import asyncio
import io
import copy
from types import SimpleNamespace
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image
from home_world import HomeWorld
import home_phone
from test_home_native_feedback import add_home_routes, AUTH, TOKEN
from test_home_device_proxy import proxy


def test_real_phone_route_proxy_data_identity_and_privacy():
    async def run():
        world = HomeWorld(); world.notes=[{'text':'Owner note: read the real book.'}]
        world.memories=[{'what':'Walked to the kitchen.'}]
        originals=(copy.deepcopy(world.notes),copy.deepcopy(world.memories)); world.phone['battery']=73
        live=SimpleNamespace(home=world,computer=SimpleNamespace(view=lambda:{}),
             life=SimpleNamespace(snapshot=lambda:{}),engine=SimpleNamespace(stage='awake'),
             clock=SimpleNamespace(now=lambda:0))
        app=web.Application();add_home_routes(app,live,lambda r:r.headers.get('X-Admin-Token')==TOKEN)
        backend=TestClient(TestServer(app));await backend.start_server()
        device=proxy.HomeDeviceProxy(str(backend.make_url('')).rstrip('/'),TOKEN,SimpleNamespace(privacy=False,privacy_epoch=0))
        app=web.Application();app.router.add_get('/{device}/frame',device.frame);app.router.add_post('/{device}/action',device.action)
        client=TestClient(TestServer(app));await client.start_server()
        try:
            state=await (await backend.get('/api/home')).json();first=state['phone_screen']['frame_id']
            assert (await backend.get('/api/home/phone/frame.jpg?frame_id='+first)).status==403
            assert (await backend.post('/api/home/phone/action',json={'action':'home','frame_id':first})).status==403
            response=await client.get('/phone/frame?frame_id='+first);assert response.status==200
            pixels=await response.read();assert Image.open(io.BytesIO(pixels)).size==(256,512)
            assert response.headers['Content-Type']=='image/jpeg';assert response.headers['Cache-Control']=='no-store'
            tag=response.headers['ETag']
            response=await backend.get('/api/home/phone/frame.jpg?frame_id='+first,headers={**AUTH,'If-None-Match':tag});assert response.status==304
            assert (await client.post('/phone/action',json={'action':'open_app','app':'notes','frame_id':first})).status==200
            state=await (await backend.get('/api/home')).json();notes=state['phone_screen']['frame_id']
            assert notes!=first;assert state['phone_screen']['app']=='notes'
            assert home_phone.snapshot(world)['entries']==['Owner note: read the real book.']
            assert (await client.get('/phone/frame?frame_id='+first)).status==409
            response=await client.get('/phone/frame?frame_id='+notes);assert response.status==200;assert await response.read()!=pixels
            world.notes[0]['text']='Actual edited data for identity test.'
            assert (await client.get('/phone/frame?frame_id='+notes)).status==409
            world.notes=originals[0]
            assert (await client.post('/phone/action',json={'action':'open_app','app':[], 'frame_id':notes})).status==400
            assert (await client.post('/phone/action',json={'action':'open_app','app':'browser','frame_id':notes})).status==200
            data=home_phone.snapshot(world);assert data['browser'] is None
            assert home_phone.status(data)['kind']=='owned_app' # Truthful unavailable UI, no site imitation.
            assert world.notes==originals[0] and world.memories==originals[1]
            world.node='bathroom';world.target='bathroom'
            assert (await backend.get('/api/home/phone/frame.jpg?frame_id='+notes,headers=AUTH)).status==409
            assert (await client.get('/phone/frame?frame_id='+notes)).status==409
            assert (await backend.post('/api/home/phone/action',headers=AUTH,json={'action':'home','frame_id':notes})).status==409
            assert (await (await backend.get('/api/home')).json())['phone_screen'] is None
        finally:
            await client.close();await device.close();await backend.close()
    asyncio.run(run())


def test_notes_save_registered_route_persists_real_world_and_rejects_invalid_input(tmp_path):
    async def run():
        import json
        world=HomeWorld();world.phone['app']='notes'
        world.notes=[{'id':1,'text':'Existing fixture entry.'}]
        original=copy.deepcopy(world.notes);saved=[]
        async def save():
            value=world.to_dict();saved.append(value)
            (tmp_path/'world.json').write_text(json.dumps(value))
        live=SimpleNamespace(home=world,save_state=save)
        app=web.Application();add_home_routes(app,live,lambda r:r.headers.get('X-Admin-Token')==TOKEN)
        client=TestClient(TestServer(app));await client.start_server()
        def frame():return home_phone.status(home_phone.snapshot(world))['frame_id']
        async def post(payload, auth=True):
            return await client.post('/api/home/phone/action',json=payload,headers=AUTH if auth else {})
        try:
            first=frame();seq=world.sequence
            clean={'action':'save_note','frame_id':first,'title':'Reading','text':'Read the real book.'}
            assert (await post(clean,False)).status==403
            assert (await post({**clean,'frame_id':'old'})).status==409
            for bad in [dict(text=''),dict(text='  \n '),dict(text=None),dict(text=[]),dict(text='x'*2001),
                        dict(title=None),dict(title=[]),dict(title='x'*121),dict(title='a',text='x'*2000)]:
                assert (await post({**clean,**bad})).status==400
                assert world.notes==original and world.sequence==seq and not saved
            world.phone['app']='home'
            assert (await post({**clean,'frame_id':frame()})).status==409
            world.phone['app']='notes';world.node=world.target='bathroom'
            assert (await post(clean)).status==409
            world.node=world.target='desk'
            response=await post({**clean,'title':' Reading ','text':' Read the real book. '})
            assert response.status==200;result=await response.json()
            assert world.notes[0]==original[0]
            assert world.notes[-1]['text']=='Reading\nRead the real book.'
            assert world.sequence==seq+1 and len(saved)==1
            restored=HomeWorld(json.loads((tmp_path/'world.json').read_text()))
            assert restored.notes==world.notes
            current=frame();assert current!=first and result['phone_screen']['frame_id']==current
            assert (await post(clean)).status==409 # Retried old frame cannot duplicate a saved note.
            assert len(saved)==1 and len(world.notes)==2
            response=await client.get('/api/home/phone/frame.jpg?frame_id='+current,headers=AUTH)
            assert response.status==200
            assert await response.read()==home_phone.render(home_phone.snapshot(world))
            assert home_phone.snapshot(world)['entries'][0]=='Reading\nRead the real book.'
            # Title is optional and the existing add_note semantics trim whitespace.
            response=await post({'action':'save_note','frame_id':current,'text':' Untitled fixture note. '})
            assert response.status==200 and world.notes[-1]['text']=='Untitled fixture note.'
        finally:await client.close()
    asyncio.run(run())


def test_notes_write_through_actual_authenticated_runner_proxy_and_backend(tmp_path):
    async def run():
        import json
        from test_home_pc_runner import pc, FakeComputer
        world=HomeWorld();world.phone['app']='notes'
        world.notes=[{'text':'Fixture only existing note.'}]
        original=copy.deepcopy(world.notes);writes=[]
        async def save():
            writes.append(copy.deepcopy(world.to_dict()))
            (tmp_path/'saved.json').write_text(json.dumps(world.to_dict()))
        live=SimpleNamespace(home=world,save_state=save,computer=SimpleNamespace(view=lambda:{}),
             life=SimpleNamespace(snapshot=lambda:{}),engine=SimpleNamespace(stage='awake'),clock=SimpleNamespace(now=lambda:0))
        app=web.Application();add_home_routes(app,live,lambda r:r.headers.get('X-Admin-Token')==TOKEN)
        backend=TestServer(app);await backend.start_server()
        computer=FakeComputer();runner=pc.PCRunner(computer,TOKEN)
        runner.home_devices=proxy.HomeDeviceProxy(str(backend.make_url('')).rstrip('/'),TOKEN,runner)
        client=TestClient(TestServer(pc.create_app(runner)));await client.start_server()
        def frame():return home_phone.status(home_phone.snapshot(world))['frame_id']
        async def post(data,auth=True):return await client.post('/devices/phone/action',json=data,headers=AUTH if auth else {})
        try:
            old=frame();payload={'action':'save_note','frame_id':old,'title':'Today','text':'A fixture reminder.'}
            assert (await post(payload,False)).status==403
            assert (await post({**payload,'frame_id':'stale'})).status==409
            for bad in [dict(title='t'*121),dict(text=''),dict(text=[]),dict(title=None),dict(text='x'*2001),dict(title='t',text='x'*2000)]:
                assert (await post({**payload,**bad})).status==400
            assert (await client.post('/devices/phone/action',headers=AUTH,data=json.dumps({**payload,'padding':'x'*5000}))).status==413
            world.phone['app']='home'
            assert (await post({**payload,'frame_id':frame()})).status==409
            world.phone['app']='notes';world.node=world.target='bathroom'
            assert (await post(payload)).status==409
            world.node=world.target='desk';runner.privacy=True
            assert (await post(payload)).status==409
            runner.privacy=False
            assert not writes and world.notes==original
            assert computer.inputs==[] and computer.sent==[] # No PC/browser input mapping.
            response=await post({**payload,'device':'desk','url':'https://example.org/'})
            assert response.status==200;reply=await response.json();current=reply['phone_screen']['frame_id'];assert current!=old
            assert world.notes[-1]['text']=='Today\nA fixture reminder.'
            restored=HomeWorld(json.loads((tmp_path/'saved.json').read_text()));assert restored.notes==world.notes
            assert len(writes)==1 and computer.inputs==[] and computer.sent==[]
            response=await client.get('/devices/phone/frame.jpg?frame_id='+current,headers=AUTH)
            assert response.status==200 and response.headers['Content-Type']=='image/jpeg'
            assert await response.read()==home_phone.render(home_phone.snapshot(world))
            assert response.headers['ETag'] and response.headers['Cache-Control']=='no-store'
            assert (await post(payload)).status==409 and len(writes)==1
            assert (await client.get('/devices/phone/frame.jpg?frame_id='+old,headers=AUTH)).status==409
        finally:
            await client.close();await runner.home_devices.close();await backend.close()
    asyncio.run(run())


def test_notes_identical_full_list_keeps_write_frames_unique():
    world=HomeWorld();world.phone['app']='notes'
    for _ in range(10):world.add_note('Repeated actual text.')
    first=home_phone.snapshot(world);old=home_phone.status(first)['frame_id']
    world.add_note('Repeated actual text.')
    second=home_phone.snapshot(world)
    assert first['entries']==second['entries']
    assert home_phone.status(second)['frame_id']!=old
    world.add_note('Newest actual note.')
    assert home_phone.snapshot(world)['entries'][0]=='Newest actual note.'


def test_phone_ticks_keep_explicit_notes_composer_and_real_navigation_transitions(tmp_path):
    async def run():
        import json
        world=HomeWorld();world.node=world.target='bed';world.path=[];world.seated=1
        writes=[]
        async def save():
            writes.append(copy.deepcopy(world.to_dict()))
            (tmp_path/'phone-world.json').write_text(json.dumps(world.to_dict()))
        live=SimpleNamespace(home=world,save_state=save)
        app=web.Application();add_home_routes(app,live,lambda r:r.headers.get('X-Admin-Token')==TOKEN)
        client=TestClient(TestServer(app));await client.start_server()
        def frame():return home_phone.status(home_phone.snapshot(world))['frame_id']
        def tick(activity='phone'):
            world.update(.1,0,{'activity':activity,'screen':{'kind':'browser','frame_id':'paint-only'}},{})
        async def action(data):return await client.post('/api/home/phone/action',headers=AUTH,json=data)
        try:
            tick();first=frame();sequence=world.sequence
            response=await action({'action':'open_app','app':'notes','frame_id':first});assert response.status==200
            assert (await response.json())['changed'] is True
            revision=world.phone_selection_revision;notes=frame()
            for _ in range(10):tick()
            assert world.phone['app']=='notes' and frame()==notes
            assert world.phone_selection_revision==revision and world.sequence==sequence
            # Even a real new background page cannot steal an operator's active composer.
            assert not world.phone_browser_navigation({'device':'phone','url':'https://example.org/background'})
            assert world.phone['app']=='notes' and frame()==notes
            response=await action({'action':'open_app','app':'notes','frame_id':notes})
            assert (await response.json())['changed'] is False and frame()==notes
            response=await action({'action':'save_note','frame_id':notes,'text':'Only this advancing-tick fixture is written.'})
            assert response.status==200 and len(writes)==1
            assert HomeWorld(json.loads((tmp_path/'phone-world.json').read_text())).notes==world.notes
            written=frame();tick();assert world.phone['app']=='notes' and frame()==written
            assert (await action({'action':'save_note','frame_id':notes,'text':'Old composer retry.'})).status==409
            # Leaving the actual session releases ownership and invalidates its old input frame.
            tick('eat');assert world.phone_selection_revision==revision+1
            assert (await action({'action':'save_note','frame_id':written,'text':'Expired session write.'})).status==409
            tick();assert world.phone['app']=='notes' # No default browser or stale-screen switch.
            assert world.phone_browser_navigation({'device':'phone','url':'https://example.org/new-session-page'})
            assert world.phone['app']=='browser'
            current=frame()
            assert not world.phone_browser_navigation({'device':'phone','url':'https://example.org/new-session-page','frame_id':'new-paint'})
            assert frame()==current
            assert home_phone.status(home_phone.snapshot(world))['kind']=='owned_app' # Browser unavailable, not invented content.
            # Restored app/revision persist, but an old operator lock does not.
            world.select_phone_app('notes');snapshot=world.to_dict();restored=HomeWorld(snapshot)
            assert restored.phone['app']=='notes' and restored.phone_selection_revision==world.phone_selection_revision
            restored.activity='phone'
            assert restored.phone_browser_navigation({'device':'phone','url':'https://example.org/after-restart'})
            assert restored.phone['app']=='browser'
            # Failed/unavailable navigation cannot steal Notes; a successful
            # explicit operator navigation deliberately supersedes its lock.
            world.select_phone_app('notes')
            response=await client.post('/api/home/browser',headers=AUTH,json={'device':'phone','url':'https://example.org/open'})
            assert response.status==409 and world.phone['app']=='notes'
            navigated=[]
            async def navigate(device,url):
                navigated.append((device,url));return {'device':device,'url':url}
            async def on_screen(status):world.phone_browser_navigation(status)
            live.browser=SimpleNamespace(navigate=navigate);live.on_screen=on_screen
            response=await client.post('/api/home/browser',headers=AUTH,json={'device':'phone','url':'https://example.org/open'})
            assert response.status==200 and world.phone['app']=='browser'
            assert navigated==[('phone','https://example.org/open')]
            # Explicit Home and Browser selections are actual supported app intents.
            response=await action({'action':'home','frame_id':frame()});assert response.status==200 and world.phone['app']=='home'
            response=await action({'action':'open_app','app':'browser','frame_id':frame()});assert response.status==200 and world.phone['app']=='browser'
        finally:await client.close()
    asyncio.run(run())


def test_actual_new_page_hook_respects_operator_lock_and_ignores_same_url_redraw():
    import ast,time
    from screens import ScreensStatus
    root=__import__('pathlib').Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'live_server.py').read_text())
    method=next(n for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body
                if isinstance(n,ast.AsyncFunctionDef) and n.name=='on_screen')
    namespace={'time':time,'SCREENS_SAVE_S':9999}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(root/'live_server.py'),'exec'),namespace)
    world=HomeWorld();world.activity='phone';world.select_phone_app('notes')
    subject=SimpleNamespace(home=world,screens=ScreensStatus(),browser=SimpleNamespace(),screens_saved=time.time(),da_bursts=None)
    async def run():
        await namespace['on_screen'](subject,{'device':'phone','url':'https://example.org/page-a'})
        assert world.phone['app']=='notes'
        world.update(.1,0,{'activity':'eat'},{})
        world.update(.1,0,{'activity':'phone'},{})
        revision=world.phone_selection_revision
        await namespace['on_screen'](subject,{'device':'phone','url':'https://example.org/page-a','frame_id':'redraw'})
        assert world.phone['app']=='notes' and world.phone_selection_revision==revision
        await namespace['on_screen'](subject,{'device':'phone','url':'https://example.org/page-b'})
        assert world.phone['app']=='browser'
    asyncio.run(run())
