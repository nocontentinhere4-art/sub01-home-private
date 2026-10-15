"""Private manual-TV leases backed by an independent native process receipt.

This does not establish seating or alter HomeWorld readiness. Manual controls
stay disabled until explicitly qualified; the receipt alone cannot enable them.
"""
import ipaddress
import json
import math
import os
import re
import stat
import time
from pathlib import Path
from aiohttp import web

RECEIPT = Path('/home/unreal/.sub01-private/native-tv-focus.json')
PROJECT = '/workspace/sub01-private-recovered-project/Sub01HomeLab/Sub01HomeLab.uproject'
MAX_COUNTER = 2**53-1
CONTROLS = {'forward','back','left','right','jump','sneak','sprint'}


def identity(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-fA-F]{32}',value):
        raise ValueError('Expected native focus identity')
    return value.lower()


def vector(value):
    if (not isinstance(value,list) or len(value)!=3 or
        any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value)):
        raise ValueError('Invalid native evidence vector')
    return value


def native_process(pid):
    if isinstance(pid,bool) or not isinstance(pid,int) or pid<1:raise ValueError('Invalid native process')
    p=Path('/proc')/str(pid)
    uid=int((p/'status').read_text().split('Uid:')[1].split()[0])
    ticks=int((p/'stat').read_text().rsplit(')',1)[1].split()[19])
    args=(p/'cmdline').read_bytes().split(b'\0')
    return uid,ticks,args


class NativeTVInput:
    def __init__(self, *, enabled=None, receipt=RECEIPT, process=native_process,
                 uid=1001, wall=time.time, monotonic=time.monotonic):
        self.enabled=(os.environ.get('HOME_NATIVE_MANUAL_TV_INPUT')=='1') if enabled is None else enabled
        self.receipt=Path(receipt);self.process=process;self.uid=uid
        self.wall=wall;self.monotonic=monotonic
        self.owner=None;self.until=0;self.counter=0

    def evidence(self, consumer=None, event=None, frame=None):
        s=self.receipt.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=self.uid or s.st_mode&0o077 or s.st_size>4096:
            raise ValueError('Untrusted native receipt')
        d=json.loads(self.receipt.read_text())
        if not isinstance(d,dict):raise ValueError('Invalid native receipt')
        age=self.wall()-d.get('captured_utc',float('-inf'))
        if not math.isfinite(age) or not -.05<=age<=.75:raise ValueError('Native receipt expired')
        if d.get('mode')!='manual' or d.get('focused') is not True or d.get('privacy') is not False or d.get('device')!='tv':
            raise ValueError('Native manual TV ownership is absent')
        cid=identity(d.get('consumer_id'));eid=identity(d.get('focus_event_id'))
        if (consumer is not None and cid!=consumer) or (event is not None and eid!=event):
            raise ValueError('Native focus changed')
        if not isinstance(d.get('frame_id'),str) or not d['frame_id'] or len(d['frame_id'])>128 or (frame is not None and d['frame_id']!=frame):
            raise ValueError('Displayed native frame changed')
        pid=d.get('native_pid');uid,ticks,args=self.process(pid)
        if uid!=self.uid or ticks!=d.get('native_start_ticks') or PROJECT.encode()not in args or b'-game'not in args:
            raise ValueError('Native process identity changed')
        if d.get('surface_tag')!='SUB01Device:tv' or d.get('surface_unique') is not True or not isinstance(d.get('component_identity'),str) or not d['component_identity']:
            raise ValueError('Actual unique TV component is absent')
        bounds=d.get('surface_bounds')
        if not isinstance(bounds,dict):raise ValueError('Actual TV bounds absent')
        c=vector(bounds.get('center_cm'));e=vector(bounds.get('extent_cm'))
        if any(abs(c[i]-v)>.2 for i,v in enumerate((-374.7,-5,165))) or any(abs(e[i]-v)>.2 for i,v in enumerate((0,83,47.5))):
            raise ValueError('Actual TV surface changed')
        actor=vector(d.get('actor_cm'));eye=vector(d.get('eye_cm'));hit=vector(d.get('hit_cm'))
        if not(-430<actor[0]<430 and -450<actor[1]<800 and 50<actor[2]<750):raise ValueError('Native capsule outside home')
        if math.hypot(eye[0]-actor[0],eye[1]-actor[1])>35 or not 40<=eye[2]-actor[2]<=100:
            raise ValueError('Eye is not attached to actual capsule')
        if abs(hit[0]+374.7)>.2 or abs(hit[1]+5)>83.2 or abs(hit[2]-165)>47.7 or math.dist(eye,hit)>200.2:
            raise ValueError('Actual TV ray hit is out of reach')
        return (cid,eid,pid,ticks)

    def focus(self,data,current_frame,private):
        if not self.enabled:raise PermissionError('Manual Minecraft input awaits native qualification')
        if private:raise PermissionError('Bathroom privacy is active')
        if not isinstance(data,dict) or set(data)!={'consumer_id','focus_event_id','frame_id'}:raise ValueError('Expected focus identities only')
        cid=identity(data['consumer_id']);eid=identity(data['focus_event_id'])
        if not current_frame or data['frame_id']!=current_frame:raise PermissionError('Actual Minecraft frame changed')
        owner=self.evidence(cid,eid,current_frame)
        if self.owner is not None and self.monotonic()<self.until and self.owner[0]!=owner[0]:raise PermissionError('Another native focus owns the console')
        if self.owner is None or self.owner[0]!=owner[0]:self.counter=0
        self.owner=owner;self.until=self.monotonic()+.75
        return {'ok':True,'lease_ms':750,'frame_id':current_frame}

    def active(self,private=False):
        if not self.enabled or private or self.owner is None or self.monotonic()>=self.until:return False
        try:return self.evidence(self.owner[0],self.owner[1])==self.owner
        except (ValueError,OSError,TypeError,KeyError):return False

    def control(self,data,current_frame,private):
        if not isinstance(data,dict):raise ValueError('Expected bounded Minecraft controls')
        common={'consumer_id','focus_event_id','frame_id','input_id','operation'}
        if not common<=set(data) or set(data)-common-{'keys','look_delta'}:raise ValueError('Unknown Minecraft input fields')
        cid=identity(data['consumer_id']);eid=identity(data['focus_event_id']);counter=data['input_id']
        if isinstance(counter,bool) or not isinstance(counter,int) or not 1<=counter<=MAX_COUNTER:raise ValueError('Invalid input order')
        if self.owner is None or self.owner[:2]!=(cid,eid) or counter<=self.counter:raise PermissionError('Native input is stale')
        operation=data['operation']
        if operation not in {'controls','mine','place','release','cancel'}:raise ValueError('Unsupported Minecraft operation')
        if operation not in {'release','cancel'}:
            if not self.active(private) or not current_frame or data['frame_id']!=current_frame:raise PermissionError('Native focus/frame is unavailable')
            try:
                if self.evidence(cid,eid,current_frame)!=self.owner:raise ValueError('Focus changed')
            except (ValueError,OSError,TypeError,KeyError):raise PermissionError('Displayed native frame is unavailable')
        keys=data.get('keys',{});look=data.get('look_delta',[0,0])
        if not isinstance(keys,dict) or set(keys)-CONTROLS or any(type(v)is not bool for v in keys.values()):raise ValueError('Invalid bounded keys')
        if not isinstance(look,list) or len(look)!=2 or any(isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v)or abs(v)>.35 for v in look):raise ValueError('Invalid bounded look')
        if operation!='controls' and (keys or look!=[0,0]):raise ValueError('Action carries unrelated controls')
        self.counter=counter
        if operation in {'release','cancel'}:self.until=0
        return {'type':'operator_input','consumer_id':cid,'focus_event_id':eid,'operation':operation,'input_id':counter,'keys':keys,'look_delta':look,'hold_ms':250}


def add_minecraft_input_routes(app,live,admin_ok):
    policy=NativeTVInput()
    if getattr(live,'minecraft',None) is not None:live.minecraft.native_input=policy
    async def checked(request):
        if not admin_ok(request):raise web.HTTPForbidden()
        try:local=ipaddress.ip_address(request.remote or '').is_loopback
        except ValueError:local=False
        if not local:raise web.HTTPForbidden(text='Native TV input requires actual loopback')
        if not getattr(live,'home',None):raise web.HTTPNotFound()
        if request.content_length is not None and request.content_length>2048:raise web.HTTPRequestEntityTooLarge(max_size=2048,actual_size=request.content_length)
        raw=bytearray()
        async for chunk in request.content.iter_chunked(2048):
            raw.extend(chunk)
            if len(raw)>2048:raise web.HTTPRequestEntityTooLarge(max_size=2048,actual_size=len(raw))
        try:d=json.loads(raw)
        except (ValueError,UnicodeDecodeError):raise web.HTTPBadRequest()
        return d
    async def focus(request):
        data=await checked(request);console=getattr(live,'minecraft',None)
        if not console or not console.enabled or live.home.console_game!='minecraft':raise web.HTTPConflict(text='Actual Minecraft console is unavailable')
        try:result=policy.focus(data,console.frame_tag,live.home.privacy())
        except PermissionError as e:raise web.HTTPConflict(text=str(e))
        except (ValueError,OSError,TypeError,KeyError):raise web.HTTPBadRequest(text='Native focus evidence rejected')
        return web.json_response(result,headers={'Cache-Control':'no-store'})
    async def controls(request):
        data=await checked(request);console=getattr(live,'minecraft',None)
        if not console or not console.enabled:raise web.HTTPConflict(text='Actual Minecraft console is unavailable')
        try:packet=policy.control(data,console.frame_tag,live.home.privacy())
        except PermissionError as e:raise web.HTTPConflict(text=str(e))
        except (ValueError,OSError,TypeError,KeyError):raise web.HTTPBadRequest(text='Native controls rejected')
        if packet['operation'] not in {'release','cancel'} and live.home.console_game!='minecraft':raise web.HTTPConflict(text='Console game changed')
        sender=getattr(console,'operator_input',None)
        if sender is None:raise web.HTTPServiceUnavailable(text='Actual worker input is unavailable')
        result=await sender(packet)
        if not result or result.get('accepted') is not True:raise web.HTTPConflict(text='Actual game worker did not accept input')
        return web.json_response({'ok':True,'worker':result},headers={'Cache-Control':'no-store'})
    app.router.add_post('/api/home/minecraft/focus',focus)
    app.router.add_post('/api/home/minecraft/input',controls)
    return policy
