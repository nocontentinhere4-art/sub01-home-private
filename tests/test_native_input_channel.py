"""Real shared permission gate and browser socket ordering, without an X server."""
import json
import shutil
import subprocess
import threading
from types import SimpleNamespace

import pytest

from tools.pixel_streaming.native_input_channel import INPUT_SOCKET_JS, dispatch, packet
from tools.pixel_streaming.native_live_viewer import HTML, private_egress_event, validate_input


class Clock:
    def __init__(self): self.now=100.; self.sleeps=[]
    def __call__(self): return self.now
    def sleep(self, seconds): self.sleeps.append(seconds); self.now+=seconds


def state():
    sink=SimpleNamespace(events=[])
    sink.send=lambda event:sink.events.append(event)
    value=SimpleNamespace(input_lock=threading.Lock(),input=sink,last_input=0.,last_lease=0.,accepted=0,session='test',allowed=True,egress=False)
    value.enabled=lambda flag:value.allowed
    value.can_private_egress=lambda:value.egress
    return value


def deliver(value,event,clock,**kwargs):
    return dispatch(value,event,validate_input,lambda:None,private_egress_event,clock,**kwargs)


@pytest.mark.parametrize('value',[
    {}, {'id':True,'event':{}}, {'id':0,'event':{}}, {'id':2**53,'event':{}},
    {'id':1,'event':{},'command':'anything'}, [], {'id':1},
])
def test_packet_is_bounded_and_unambiguous(value):
    with pytest.raises(ValueError):packet(value)


def test_identifiers_cannot_replay():
    assert packet({'id':4,'event':{'action':'release'}},3)==(4,{'action':'release'})
    with pytest.raises(ValueError):packet({'id':4,'event':{}},4)


def test_http_rate_limit_unchanged_and_release_never_waits():
    value=state();clock=Clock();event={'action':'key','code':'KeyW','down':True}
    assert deliver(value,event,clock)[0]==200
    assert deliver(value,event,clock)[0]==429
    assert deliver(value,{'action':'key','code':'KeyW','down':False},clock)[0]==200
    assert deliver(value,{'action':'release'},clock)[0]==200
    assert clock.sleeps==[] and value.accepted==3


def test_socket_paces_same_original_rate_instead_of_dropping_bursts():
    value=state();clock=Clock()
    for event in [{'action':'mouse','dx':1,'dy':0},{'action':'key','code':'KeyW','down':True},{'action':'key','code':'KeyE','down':True}]:
        assert deliver(value,event,clock,pace=True,sleeper=clock.sleep)[0]==200
    assert value.accepted==3 and len(clock.sleeps)==2
    assert all(0<s<=.005 for s in clock.sleeps)
    assert clock.now>=100.01-1e-9


def test_privacy_or_identity_can_change_during_the_pacing_wait():
    value=state();clock=Clock();value.last_input=clock.now
    def wait(seconds):clock.sleep(seconds);value.allowed=False
    assert deliver(value,{'action':'key','code':'KeyE','down':True},clock,pace=True,sleeper=wait)[0]==409
    assert value.input.events==[] and value.accepted==0


def test_early_timer_does_not_bypass_original_rate():
    value=state();clock=Clock();value.last_input=clock.now
    assert deliver(value,{'action':'mouse','dx':1,'dy':0},clock,pace=True,sleeper=lambda seconds:None)[0]==429
    assert value.input.events==[]


@pytest.mark.parametrize('event,accepted',[
    ({'action':'key','code':'KeyW','down':True},True),
    ({'action':'mouse','dx':1,'dy':0},True),
    ({'action':'release'},True),
    ({'action':'key','code':'KeyE','down':True},False),
    ({'action':'button','button':1,'down':True},False),
])
def test_private_egress_remains_only_physical_movement(event,accepted):
    value=state();value.allowed=False;value.egress=True
    assert (deliver(value,event,Clock())[0]==200)==accepted
    assert len(value.input.events)==int(accepted)


def test_no_unknown_physical_or_host_command_reaches_sink():
    value=state()
    with pytest.raises(ValueError):deliver(value,{'action':'shell','command':'anything'},Clock())
    assert value.input.events==[]


def test_actual_browser_socket_pipelines_and_settles_only_its_acks():
    node=shutil.which('node')
    if not node:pytest.skip('Node unavailable')
    # Exercise the actual shipped send() too, including its public drain barrier.
    send=HTML[HTML.index('function send(event){'):HTML.index('control.onclick=')]
    javascript=r'''
const assert=require('assert');
let accepted=0,inputQueue=Promise.resolve(),active=true,status={textContent:''};
let timers=new Map(),timerId=0;
const setTimeout=(fn,ms)=>{timers.set(++timerId,fn);return timerId;};
const clearTimeout=id=>timers.delete(id);
const makeSocket=()=>({readyState:1,bufferedAmount:0,messages:[],send(text){this.messages.push(JSON.parse(text));}});
let socket=makeSocket(),fallback=[];const window={nativeViewerSocket:socket};
const deliver=async event=>{fallback.push(event);return {acceptedInputs:++accepted};};
'''+INPUT_SOCKET_JS+'\n'+send+r'''
(async()=>{
 const down=send({action:'key',code:'KeyW',down:true});
 const up=send({action:'key',code:'KeyW',down:false});
 assert.equal(socket.messages.length,2,'must send both before any ack');
 assert.deepEqual(socket.messages.map(v=>v.id),[1,2]);
 let drained=false;inputQueue.then(()=>{drained=true;});await Promise.resolve();assert.equal(drained,false);
 acknowledgeNativeSocketInput(makeSocket(),JSON.stringify({type:'input-ack',id:1,status:200,acceptedInputs:999}));
 assert.equal(nativePendingInputs.size,2,'different socket cannot ack');
 acknowledgeNativeSocketInput(socket,JSON.stringify({type:'input-ack',id:1,status:200,acceptedInputs:1}));
 acknowledgeNativeSocketInput(socket,JSON.stringify({type:'input-ack',id:2,status:200,acceptedInputs:2}));
 await Promise.all([down,up,inputQueue]);assert.equal(accepted,2);assert.equal(drained,true);assert.equal(timers.size,0);
 const closing=sendNativeSocketInput({action:'release'}).catch(e=>e.message);
 closeNativeSocketInputs(socket);assert.equal(await closing,'Control socket closed');assert.equal(timers.size,0);
 const timeout=sendNativeSocketInput({action:'release'}).catch(e=>e.message);
 [...timers.values()][0]();assert.equal(await timeout,'Control acknowledgement timed out');assert.equal(nativePendingInputs.size,0);timers.clear();
 socket.bufferedAmount=16385;assert.match(await sendNativeSocketInput({action:'release'}).catch(e=>e.message),/overloaded/);socket.bufferedAmount=0;
 let bounded=[];for(let n=0;n<64;n++)bounded.push(sendNativeSocketInput({action:'release'}).catch(e=>e.message));
 assert.match(await sendNativeSocketInput({action:'release'}).catch(e=>e.message),/overloaded/);
 closeNativeSocketInputs(socket);await Promise.all(bounded);assert.equal(nativePendingInputs.size,0);
 window.nativeViewerSocket=null;await send({action:'release'});assert.equal(fallback.length,1);
 console.log('physical-socket-ordering-pass');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result=subprocess.run([node,'-e',javascript],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert 'physical-socket-ordering-pass' in result.stdout


def test_actual_websocket_wire_acks_and_disconnect_releases_keys():
    """Actual HTTP upgrade/framing/Handler; fake only native pixels and X sink."""
    import base64
    import socket
    import struct
    import time
    from http.server import ThreadingHTTPServer
    from tools.pixel_streaming.native_live_viewer import Handler, PRIVATE_VIEWER_ORIGIN
    value=state();value.viewer_lock=threading.Lock();value.condition=threading.Condition()
    value.sequence=0;value.latest_frame=b'\xff\xd8real-test-boundary\xff\xd9'
    value.capture_utc=time.time();value.frames=0
    def capture():
        with value.condition:
            value.sequence+=1;value.capture_utc=time.time();value.condition.notify_all()
    value.ensure_capture=capture
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.state=value
    serving=threading.Thread(target=server.serve_forever,daemon=True);serving.start()
    connection=socket.create_connection(server.server_address,timeout=2)
    def exact(length):
        raw=b''
        while len(raw)<length:
            chunk=connection.recv(length-len(raw))
            if not chunk:raise EOFError('Websocket closed')
            raw+=chunk
        return raw
    def frame():
        head=exact(2);size=head[1]&127
        if size==126:size=struct.unpack('!H',exact(2))[0]
        elif size==127:size=struct.unpack('!Q',exact(8))[0]
        return head[0]&15,exact(size)
    def send(value):
        raw=json.dumps(value,separators=(',',':')).encode();assert len(raw)<=125
        mask=b'abcd';connection.sendall(bytes([0x81,0x80|len(raw)])+mask+bytes(b^mask[i%4] for i,b in enumerate(raw)))
    try:
        key=base64.b64encode(b'0123456789abcdef').decode()
        connection.sendall((f'GET /socket HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nOrigin: {PRIVATE_VIEWER_ORIGIN}\r\n\r\n').encode())
        headers=b''
        while not headers.endswith(b'\r\n\r\n'):headers+=exact(1)
        assert headers.startswith(b'HTTP/1.0 101')
        send({'id':1,'event':{'action':'key','code':'KeyW','down':True}})
        send({'id':2,'event':{'action':'key','code':'KeyW','down':False}})
        acks=[];pixels=False
        while len(acks)<2:
            opcode,payload=frame()
            if opcode==1:acks.append(json.loads(payload))
            elif opcode==2:
                pixels=True;assert payload[16:]==value.latest_frame
        assert [ack['id'] for ack in acks]==[1,2]
        assert all(ack['type']=='input-ack' and ack['status']==200 for ack in acks)
        if not pixels:
            assert frame()[0]==2
        assert value.input.events[:2]==[{'action':'key','code':'KeyW','down':True},{'action':'key','code':'KeyW','down':False}]
        connection.shutdown(socket.SHUT_RDWR);connection.close()
        deadline=time.monotonic()+2
        while value.viewer_lock.locked() and time.monotonic()<deadline:time.sleep(.01)
        assert not value.viewer_lock.locked()
        assert value.input.events[-1]=={'action':'release'}
    finally:
        connection.close();server.shutdown();server.server_close();serving.join(timeout=2)


def test_disconnected_socket_cannot_actuate_after_release():
    value=state();clock=Clock();ended=threading.Event();ended.set()
    assert deliver(value,{'action':'key','code':'KeyW','down':True},clock,cancelled=ended.is_set)[0]==409
    assert value.input.events==[]


def test_socket_disconnect_during_pacing_cannot_leave_a_pressed_key():
    value=state();clock=Clock();value.last_input=clock.now;ended=threading.Event()
    def wait(seconds):clock.sleep(seconds);ended.set()
    assert deliver(value,{'action':'key','code':'KeyW','down':True},clock,pace=True,sleeper=wait,cancelled=ended.is_set)[0]==409
    assert value.input.events==[]
