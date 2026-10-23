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


def test_generic_browser_frame_binds_selection_revision_and_maps_only_approved_raw_actions():
    async def run():
        from test_home_pc_runner import pc, FakeComputer
        world=HomeWorld();world.activity='phone';world.select_phone_app('browser')
        raw='fixture-actual-browser-a';calls=[];reads=[]
        image=Image.new('RGB',(256,512),'#2d4663');output=io.BytesIO();image.save(output,format='JPEG');pixels=output.getvalue()
        browser_status={'device':'phone','frame_id':raw,'width':256,'height':512,'url':'https://example.org/fixture','title':'Fixture only','age':1}
        async def frame(device,expected):
            reads.append((device,expected));assert expected==raw
            return pixels,raw
        async def operator_action(device,action,expected):
            calls.append((device,action,expected));assert expected==raw
            return {'ok':True}
        live=SimpleNamespace(home=world,browser=SimpleNamespace(frame=frame,operator_action=operator_action),
             screen_status=lambda device:dict(browser_status),computer=SimpleNamespace(view=lambda:{}),
             life=SimpleNamespace(snapshot=lambda:{}),engine=SimpleNamespace(stage='fixture'),clock=SimpleNamespace(now=lambda:0))
        app=web.Application();add_home_routes(app,live,lambda r:r.headers.get('X-Admin-Token')==TOKEN)
        backend=TestClient(TestServer(app));await backend.start_server()
        computer=FakeComputer();runner=pc.PCRunner(computer,TOKEN)
        runner.home_devices=proxy.HomeDeviceProxy(str(backend.make_url('')).rstrip('/'),TOKEN,runner)
        client=TestClient(TestServer(pc.create_app(runner)));await client.start_server()
        def identity():return home_phone.status(home_phone.snapshot(world,browser_status))['frame_id']
        try:
            logical=identity();assert logical!=raw
            state=await (await backend.get('/api/home')).json()
            assert state['phone_browser_screen']['frame_id']==raw # Legacy source identity stays unchanged.
            assert state['phone_screen']['frame_id']==logical
            browser_status['age']=2;browser_status['title']='A repaint status, same source pixels'
            assert identity()==logical
            unavailable=home_phone.status(home_phone.snapshot(world,{**browser_status,'restarting':True}))
            assert unavailable['kind']=='owned_app'
            assert unavailable['frame_id']==home_phone.status(home_phone.snapshot(world,{**browser_status,'restarting':True,'age':300}))['frame_id']
            response=await client.get('/devices/phone/frame.jpg?frame_id='+logical,headers=AUTH)
            assert response.status==200 and await response.read()==pixels
            assert reads==[('phone',raw)] # Generic frame is translated only at the actual source read.
            response=await client.post('/devices/phone/action',headers=AUTH,json={'action':'scroll_down','frame_id':logical})
            assert response.status==200 and calls==[('phone','scroll_down',raw)]
            assert (await client.post('/devices/phone/action',headers=AUTH,json={'action':'scroll_down','frame_id':raw})).status==409
            # Legacy direct browser-action clients retain their raw-frame contract.
            assert (await backend.post('/api/home/browser/action',headers=AUTH,json={'device':'phone','action':'back','frame_id':raw})).status==200
            assert calls[-1]==('phone','back',raw)
            world.select_phone_app('home');world.select_phone_app('browser')
            current=identity();assert current!=logical and browser_status['frame_id']==raw
            assert (await client.get('/devices/phone/frame.jpg?frame_id='+logical,headers=AUTH)).status==409
            count=len(calls)
            assert (await client.post('/devices/phone/action',headers=AUTH,json={'action':'scroll_down','frame_id':logical})).status==409
            assert len(calls)==count
            # A selection change between the proxy's GET and POST is rejected by
            # the registered backend, rather than applying a raw-frame stale action.
            original=runner.home_devices.request
            async def between(method,path,**kwargs):
                if method=='POST' and path=='/api/home/browser/action':world.select_phone_app('notes')
                return await original(method,path,**kwargs)
            runner.home_devices.request=between
            assert (await client.post('/devices/phone/action',headers=AUTH,json={'action':'scroll_down','frame_id':current})).status==409
            assert len(calls)==count and world.notes==[]
            world.node=world.target='bathroom'
            assert (await client.get('/devices/phone/frame.jpg?frame_id='+current,headers=AUTH)).status==409
            assert computer.inputs==[] and computer.sent==[]
        finally:await client.close();await runner.home_devices.close();await backend.close()
    asyncio.run(run())


def test_operator_navigation_starts_isolated_service_after_auth_validation_and_preserves_native_gate():
    async def run():
        world=HomeWorld({'native_consumer_required':True});events=[];down=False;make_private=False
        async def ensure():
            events.append('ensure')
            if make_private:world.node=world.target='bathroom'
            return 'down'if down else 'started'
        async def init(state):events.append(('init',state))
        async def navigate(device,url):events.append(('navigate',device,url));return {'device':device,'url':url}
        async def on_screen(status):events.append('on_screen')
        local=SimpleNamespace(ensure=ensure,init_state=lambda s:dict(s))
        live=SimpleNamespace(home=world,local_browser=local,browser=SimpleNamespace(init=init,navigate=navigate),
                             browsing_state={'used':['fixture history']},on_screen=on_screen)
        app=web.Application();add_home_routes(app,live,lambda r:r.headers.get('X-Admin-Token')==TOKEN)
        client=TestClient(TestServer(app));await client.start_server()
        payload={'device':'phone','url':'https://example.org/fixture'}
        try:
            assert(await client.post('/api/home/browser',json=payload)).status==403
            assert(await client.post('/api/home/browser',headers=AUTH,json={**payload,'url':'http://127.0.0.1/'})).status==400
            assert not events
            world.node=world.target='bathroom'
            assert(await client.post('/api/home/browser',headers=AUTH,json=payload)).status==409
            assert not events
            world.node=world.target='desk';down=True
            assert(await client.post('/api/home/browser',headers=AUTH,json=payload)).status==503
            assert events==['ensure'];events.clear();down=False;make_private=True
            assert(await client.post('/api/home/browser',headers=AUTH,json=payload)).status==409
            assert not any(isinstance(e,tuple)and e[0]=='navigate'for e in events)
            world.node=world.target='desk';make_private=False;events.clear()
            assert(await client.post('/api/home/browser',headers=AUTH,json=payload)).status==200
            assert events==['ensure',('init',{'used':['fixture history']}),('navigate','phone','https://example.org/fixture'),'on_screen']
            assert world.phone['app']=='browser'
            assert world.native_feedback.required and not world.activity_ready('phone')
        finally:await client.close()
    asyncio.run(run())


# --- the phone while his life has it in hand: chat_lines, life_view, order_view and short_videos.shows_short ----------
def _phone_lines():
    viewer = [{'t': '21:03', 'text': '  hello   from chat ', 'networks': {'x': 1}, 'emotion': 0.4, 'nick': 'nosy',
               'key': 'secret-viewer-key'},
              {'t': '21:05', 'text': 'a second one', 'stage': 'AWAKE'}]
    replies = [{'t': '21:03', 'text': 'Hi there.', 'replying_to': 'hello from chat', 'tag': 'his reply (AI-written)',
                'to': 'nosy', 'source': 'chat'},
               {'t': '21:06', 'text': 'Cap note', 'replying_to': '', 'tag': 'a note from the room, not his words',
                'source': 'note'},
               {'t': '21:07', 'text': 'forged', 'replying_to': 'x' * 80, 'tag': 'SUB-01 says', 'source': 'chat'}]
    reactions = [{'t': '21:03', 'text': 'Okay, checking my phone.', 'nick': 'nosy'}]
    return viewer, replies, reactions


def test_chat_lines_keep_public_lines_in_feed_order_with_honest_tags_and_no_identities():
    import json
    viewer, replies, reactions = _phone_lines()
    lines = home_phone.chat_lines(viewer, replies, reactions)
    assert [(x['kind'], x['t']) for x in lines] == [
        ('viewer', '21:03'), ('reaction', '21:03'), ('reply', '21:03'), ('viewer', '21:05'), ('reply', '21:06'), ('reply', '21:07')]
    assert lines[0]['text'] == 'hello from chat' and lines[0]['who'] == 'a viewer'
    assert lines[1]['who'] == home_phone.TAG_REACTION and lines[1]['text'] == 'Okay, checking my phone.'
    assert lines[2] == {'kind': 'reply', 't': '21:03', 'who': 'his reply (AI-written)', 'text': 'Hi there.', 're': 'hello from chat'}
    assert lines[4]['who'] == 'a note from the room, not his words'          # a cap note keeps its own tag
    assert lines[5]['who'] == 'his reply (AI-written)'                        # a tag that is not one of ours is replaced
    assert len(lines[5]['re']) == home_phone.REPLY_CUT - 1 and lines[5]['re'].endswith('…')   # the answered words are cut
    assert all(set(x) == {'kind', 't', 'who', 'text', 're'} for x in lines)
    dumped = json.dumps(lines, ensure_ascii=False)
    assert 'nosy' not in dumped and 'secret-viewer-key' not in dumped and 'networks' not in dumped and 'emotion' not in dumped


def test_chat_app_shows_the_newest_lines_only_and_no_short_reason_when_it_is_the_chat():
    lines = home_phone.chat_lines([{'t': '20:%02d' % i, 'text': f'line {i}'} for i in range(12)])
    view = home_phone.chat_view(lines)
    assert [x['text'] for x in view['lines']] == [f'line {i}' for i in range(12 - home_phone.CHAT_LINES, 12)]
    assert view['app'] == 'chat' and view['why'] == ''


def test_phone_in_bed_with_no_short_on_it_shows_the_chat_app_never_a_blank_glass():
    viewer, replies, reactions = _phone_lines()
    lines = home_phone.chat_lines(viewer, replies, reactions)
    bed = {'activity': 'phone', 'phone': 'tiktok', 'walking': False, 'path': None}
    no_short = [None, {'device': 'phone', 'restarting': True},
                {'device': 'phone', 'url': 'https://www.google.com/search?q=bread', 'title': 'bread'},
                {'device': 'phone', 'url': 'https://en.wikipedia.org/wiki/Bread', 'title': 'Bread'},
                {'device': 'phone', 'url': 'https://www.youtube.com/watch?v=abcdefghijk', 'title': 'a video'},
                {'device': 'desk', 'url': 'https://www.tiktok.com/@cook.hub/video/7312345678901234567'}]
    for screen in no_short:
        view = home_phone.life_view(bed, screen, lines)
        assert view['app'] == 'chat' and view['why'] == home_phone.NO_SHORT, screen
        assert view['lines'][0]['text'] == 'hello from chat'
    short = {'device': 'phone', 'url': 'https://www.tiktok.com/@cook.hub/video/7312345678901234567', 'title': 'Miso soup'}
    assert home_phone.life_view(bed, short, lines) == {'app': 'short'}
    shorts_page = {'device': 'phone', 'url': 'https://www.youtube.com/shorts/abcdefghijk'}
    assert home_phone.life_view({'activity': 'phone', 'phone': 'tiktok', 'walking': False}, shorts_page, lines) == {'app': 'short'}
    chat = dict(bed, phone='chat')
    assert home_phone.life_view(chat, short, lines) == home_phone.chat_view(lines)     # the chat app never shows a short


def test_order_app_follows_the_courier_only_while_he_orders():
    import json
    base = {'activity': 'order_food', 'phone': None, 'walking': False, 'order': 'ramen', 'courier': None}
    assert home_phone.life_view(base) == {'app': 'order', 'dish': 'ramen', 'status': 'choosing what to eat', 'eta_min': None,
                                          'step': 0, 'steps': list(home_phone.ORDER_STEPS)}
    preparing = home_phone.life_view(dict(base, courier={'status': 'being prepared', 'eta_min': 12, 'geo': None, 'dish': 'ramen'}))
    assert (preparing['status'], preparing['eta_min'], preparing['step'], preparing['dish']) == ('being prepared', 12, 1, 'ramen')
    riding = dict(base, courier={'status': 'on the way', 'eta_min': 3, 'geo': {'lat': 35.7, 'lng': 139.57, 'heading': 90},
                                 'dish': 'sushi'})
    v = home_phone.life_view(riding)
    assert (v['status'], v['eta_min'], v['step'], v['dish']) == ('on the way', 3, 2, 'sushi')
    assert home_phone.life_view(dict(base, courier={'status': 'at the door', 'eta_min': 0, 'geo': None, 'dish': 'ramen'}))['step'] == 2
    assert home_phone.life_view(dict(base, walking=True)) is None                  # the phone is not in his hand on the way
    assert home_phone.life_view(dict(base, activity='eat')) is None
    assert home_phone.life_view({'privacy': True}) is None                         # the privacy mask carries no life
    assert json.loads(json.dumps(v)) == v


def test_the_phone_view_follows_the_real_life_snapshot():
    import random
    import life as life_mod
    lf = life_mod.Life({'activity': 'order_food', 'place': 'bed', 'until': 1e12}, rng=random.Random(3))
    lf.order_dish = 'curry'
    view = home_phone.life_view(lf.snapshot())
    assert view['dish'] == 'curry' and view['status'] == 'choosing what to eat'
    lf.delivery = {'ordered': 0.0, 'leaves': 100.0, 'arrives': 700.0, 'dish': 'curry'}
    view = home_phone.life_view(lf.snapshot())          # the courier's status at the snapshot's own clock (life.courier)
    assert view['app'] == 'order' and view['status'] == 'being prepared' and view['eta_min'] == 12 and view['step'] == 1
    lf.activity, lf.phone_app = 'phone', 'tiktok'
    view = home_phone.life_view(lf.snapshot())          # no browser: the chat app, and why
    assert view['app'] == 'chat' and view['why'] == home_phone.NO_SHORT


def test_only_a_tiktok_or_youtube_shorts_page_on_the_phone_is_a_short():
    import short_videos as SV
    tiktok = 'https://www.tiktok.com/@cook.hub/video/7312345678901234567'
    assert SV.shows_short({'device': 'phone', 'url': tiktok})
    assert SV.shows_short({'device': 'phone', 'url': 'https://www.tiktok.com/tag/bread'})          # a tag feed
    assert SV.shows_short({'device': 'phone', 'url': 'https://www.youtube.com/shorts/abcdefghijk'})
    assert not SV.shows_short({'device': 'phone', 'url': 'https://www.youtube.com/watch?v=abcdefghijk'})
    assert not SV.shows_short({'device': 'phone', 'url': 'https://www.google.com/search?q=shorts'})
    assert not SV.shows_short({'device': 'phone', 'restarting': True, 'url': tiktok})
    assert not SV.shows_short({'device': 'desk', 'url': tiktok})
    assert not SV.shows_short({'device': 'phone', 'url': ''}) and not SV.shows_short({'device': 'phone'})
    assert not SV.shows_short({'device': 'phone', 'url': 'http://[::1'}) and not SV.shows_short(None)
    fresh = {'device': 'phone', 'url': tiktok, 't': 1000.0}                  # opened at 1000 s (wall clock)
    assert SV.shows_short(fresh, now=1000.0 + SV.SHORT_STALE_S)
    assert not SV.shows_short(fresh, now=1000.0 + SV.SHORT_STALE_S + 1)     # a stalled feed is not a short any more


def test_a_stalled_short_on_the_glass_gives_way_to_the_chat_app():
    viewer, replies, reactions = _phone_lines()
    lines = home_phone.chat_lines(viewer, replies, reactions)
    bed = {'activity': 'phone', 'phone': 'tiktok', 'walking': False, 'path': None}
    stalled = {'device': 'phone', 'url': 'https://www.tiktok.com/@cook.hub/video/7312345678901234567', 't': 1000.0}
    view = home_phone.life_view(bed, stalled, lines, now=1000.0 + 60)
    assert view == {'app': 'short'}
    view = home_phone.life_view(bed, stalled, lines, now=1000.0 + 10 * 60)
    assert view['app'] == 'chat' and view['why'] == home_phone.NO_SHORT
