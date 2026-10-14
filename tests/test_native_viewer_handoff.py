"""Ownership is granted only by a fresh acknowledgement from the same native game."""
import json
import time
import pytest
from tools.pixel_streaming import native_live_viewer as viewer


@pytest.mark.parametrize('value',[{},[],True,'manual',{'mode':'live'},{'mode':'diagnostic'},{'mode':'manual','position':[0,0,0]},{'mode':'manual','capture':'anything.png'}])
def test_mode_request_cannot_route_replay_or_assign_position(value):
    with pytest.raises(ValueError):viewer.validate_manual_handoff(value)


def acknowledgement(identity,revision_value,now,**changes):
    value={'native_pid':identity[0],'native_start_ticks':identity[1],'revision':revision_value,'captured_utc':now,'accepted':True,'device_focus_cleared':True,'target':'manual','view_mode':'manual'}
    value.update(changes)
    return value


@pytest.mark.parametrize('changes',[
    {'native_pid':501},{'native_start_ticks':901},{'revision':11},{'revision':True},
    {'captured_utc':time.time()-10},{'captured_utc':time.time()+10},{'captured_utc':float('nan')},
    {'accepted':False},{'device_focus_cleared':False},{'target':'live'},{'view_mode':'diagnostic'},
])
def test_incompatible_or_stale_ack_cannot_unlock(changes):
    identity=(500,900)
    assert not viewer.manual_handoff_ack(acknowledgement(identity,10,time.time(),**changes),identity,10,time.time())


class Clock:
    def __init__(self,consumer):self.elapsed=0;self.utc=time.time();self.consumer=consumer
    def time(self):return self.utc+self.elapsed
    def monotonic(self):return self.elapsed
    def sleep(self,seconds):self.elapsed+=seconds;self.consumer()


def prepared(tmp_path):
    state=viewer.LiveState(time.time()+30)
    state.private=tmp_path;state.test_identity=(500,900);state.test_mode='live'
    state.native=lambda:state.test_identity
    state.privacy=lambda:False
    state.view_mode=lambda:state.test_mode
    identity={'native_pid':500,'native_start_ticks':900}
    (tmp_path/'native-viewer-capture-enabled').write_text(json.dumps({**identity,'accepted_game_pixels':True}))
    (tmp_path/'native-viewer-input-enabled').write_text(json.dumps({**identity,'view_mode':'manual'}))
    (tmp_path/'native-control.json').write_text(json.dumps({'revision':7,'capture':'old.png','routeReview':True}))
    (tmp_path/'native-view-privacy.json').write_text(json.dumps({**identity,'captured_utc':time.time(),'physical_camera_private':False,'view_mode':'live','view_mode_revision':10,'viewer_handoff_capable':True,'can_take_control':True}))
    return state


@pytest.mark.parametrize('mode',['live','diagnostic',None])
def test_previous_manual_input_flag_does_not_authorize_another_owner(tmp_path,mode):
    state=prepared(tmp_path);state.test_mode=mode
    assert state.enabled('native-viewer-capture-enabled')
    assert not state.enabled('native-viewer-input-enabled')


def test_native_ack_precedes_input_grant_and_previous_commands_are_not_replayed(tmp_path,monkeypatch):
    state=prepared(tmp_path)
    def consume():
        command=json.loads((tmp_path/'native-control.json').read_text())
        assert command=={'revision':11,'viewerHandoff':'manual','native_pid':500,'native_start_ticks':900}
        assert not (tmp_path/'native-viewer-input-enabled').exists()
        state.test_mode='manual'
        (tmp_path/'native-viewer-handoff-receipt.json').write_text(json.dumps(acknowledgement((500,900),11,clock.time())))
    clock=Clock(consume);monkeypatch.setattr(viewer,'time',clock)
    result=state.take_manual_control({'mode':'manual'})
    assert result=={'mode':'manual','revision':11,'nativeIdentity':[500,900],'inputEnabled':True}
    flag=tmp_path/'native-viewer-input-enabled'
    assert json.loads(flag.read_text())['view_mode']=='manual'
    assert flag.stat().st_mode & 0o777==0o600


@pytest.mark.parametrize('failure',['wrong_identity','wrong_revision','old_ack','focused','replaced','privacy'])
def test_failed_handoff_leaves_input_revoked(tmp_path,monkeypatch,failure):
    state=prepared(tmp_path)
    def consume():
        state.test_mode='manual'
        changes={}
        if failure=='wrong_identity':changes['native_start_ticks']=901
        elif failure=='wrong_revision':changes['revision']=12
        elif failure=='old_ack':changes['captured_utc']=clock.time()-5
        elif failure=='focused':changes['device_focus_cleared']=False
        elif failure=='replaced':state.test_identity=(501,901)
        elif failure=='privacy':state.privacy=lambda:True
        (tmp_path/'native-viewer-handoff-receipt.json').write_text(json.dumps(acknowledgement((500,900),11,clock.time(),**changes)))
    clock=Clock(consume);monkeypatch.setattr(viewer,'time',clock)
    with pytest.raises(ValueError):state.take_manual_control({'mode':'manual'})
    assert not (tmp_path/'native-viewer-input-enabled').exists()


@pytest.mark.parametrize('change',[
    {'view_mode':'diagnostic'},{'captured_utc':time.time()-5},
    {'viewer_handoff_capable':False},{'can_take_control':False},{'physical_camera_private':True},
])
def test_unready_native_cannot_receive_a_handoff_command(tmp_path,change):
    state=prepared(tmp_path);p=tmp_path/'native-view-privacy.json';receipt=json.loads(p.read_text());receipt.update(change);p.write_text(json.dumps(receipt))
    before=(tmp_path/'native-control.json').read_text()
    with pytest.raises(ValueError):state.take_manual_control({'mode':'manual'})
    assert (tmp_path/'native-control.json').read_text()==before
    assert not state.enabled('native-viewer-input-enabled')

@pytest.mark.parametrize('origin,body,expected',[
    (None,b'{"mode":"manual"}',403),
    ('https://other.example',b'{"mode":"manual"}',403),
    (viewer.PRIVATE_VIEWER_ORIGIN,b'{"mode":"live"}',409),
    (viewer.PRIVATE_VIEWER_ORIGIN,b' '*129,409),
    (viewer.PRIVATE_VIEWER_ORIGIN,b'{"mode":"manual"}',200),
    ('https://5ldnm4vax9kelh-8888.proxy.runpod.net',b'{"mode":"manual"}',403),
])
def test_http_handoff_surface_requires_exact_private_origin_and_bounded_body(origin,body,expected):
    import threading
    import urllib.request
    import urllib.error
    calls=[]
    class State:
        def take_manual_control(self,value):
            viewer.validate_manual_handoff(value);calls.append(value);return {'mode':'manual','inputEnabled':True}
    server=viewer.ThreadingHTTPServer(('127.0.0.1',0),viewer.Handler);server.state=State()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/mode',data=body,method='POST',headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=2) as response:status=response.status
        except urllib.error.HTTPError as error:status=error.code
        assert status==expected
        assert calls==([{'mode':'manual'}] if expected==200 else [])
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
