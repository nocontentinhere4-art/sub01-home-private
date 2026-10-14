"""Gated brain/gamepad semantics; visual state comes only from the actual worker ACK.

No prop, seat or grip is inferred here. Until a reviewed assembly/capture is
registered and the current native consumer proves both contacts, this is neutral.
"""
import asyncio
import json
import math
import os
import re
import stat
import time
import uuid
from pathlib import Path
from home_minecraft_input import native_process, PROJECT

NEUTRAL = {'left_stick': [0.0, 0.0], 'right_stick': [0.0, 0.0],
           'buttons': {'jump': False, 'sneak': False, 'sprint': False, 'mine': False, 'place': False, 'use': False}}


def neutral():
    return {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in NEUTRAL.items()}


class ControllerEvidence:
    def __init__(self, path=Path('/home/unreal/.sub01-private/native-controller-grip.json'),
                 *, process=native_process, wall=time.time, uid=1001, assembly=None, source_sha=None, contact_review=None):
        self.path=Path(path);self.process=process;self.wall=wall;self.uid=uid
        self.assembly=assembly if assembly is not None else os.environ.get('SUB01_CONTROLLER_ASSEMBLY')
        self.source_sha=source_sha if source_sha is not None else os.environ.get('SUB01_CONTROLLER_SOURCE_SHA')
        self.contact_review=contact_review if contact_review is not None else os.environ.get('SUB01_CONTROLLER_CONTACT_REVIEW')

    def __call__(self, home, frame):
        if (not self.assembly or not self.source_sha or not re.fullmatch("[0-9a-f]{64}",self.source_sha) or not frame
                or not self.contact_review or not re.fullmatch("[0-9a-f]{64}",self.contact_review)
                or home.privacy() or home.activity!='play_console' or home.console_game!='minecraft'
                or home.target!='sofa' or not home.activity_ready('play_console')):
            return None
        feedback=getattr(home,'native_feedback',None)
        if not feedback or not feedback.required or not feedback.epoch:return None
        s=self.path.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=self.uid or s.st_mode&0o077 or s.st_size>4096:return None
        d=json.loads(self.path.read_text())
        if not isinstance(d,dict):return None
        stamp=d.get('captured_utc');sequence=d.get('route_sequence');pose_time=d.get('capture_time')
        if type(stamp)not in(int,float)or not math.isfinite(stamp)or not -.05<=self.wall()-stamp<=.75:return None
        if (d.get('schema')!='sub01-native-controller-v1' or d.get('mode')!='live'
                or d.get('privacy') is not False or d.get('activity')!='play_console'
                or d.get('node')!='sofa' or d.get('chair')!='sofa'
                or type(sequence)is not int or sequence!=home.sequence
                or type(pose_time)not in(int,float)or not math.isfinite(pose_time)or not 0<=pose_time<=5.0334
                or d.get('contact_review_sha')!=self.contact_review
                or d.get('epoch')!=feedback.epoch or d.get('frame_id')!=frame
                or d.get('seat_verified')is not True or d.get('grip_verified')is not True
                or d.get('assembly_asset')!=self.assembly or d.get('source_sha')!=self.source_sha
                or d.get('owner_asset')!='/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'
                or d.get('capture_asset')!='/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming'):
            return None
        uid,ticks,args=self.process(d.get('native_pid'))
        if uid!=self.uid or ticks!=d.get('native_start_ticks')or PROJECT.encode()not in args or b'-game'not in args:return None
        # The tuple binds all queued replies to this exact physical-consumer session.
        return (d['native_pid'],ticks,feedback.epoch,sequence,self.assembly,self.source_sha,self.contact_review)


class BrainController:
    def __init__(self, *, enabled=None, evidence=None, clock=time.monotonic):
        self.enabled=(os.environ.get('SUB01_BRAIN_CONTROLLER')=='1')if enabled is None else enabled
        self.evidence=evidence if evidence is not None else ControllerEvidence()
        self.clock=clock;self.home=None;self.desired=None;self.desired_until=0
        self.consumer_id=uuid.uuid4().hex;self.event_id=None;self.owner=None
        self.counter=0;self.last_ack=0;self.pose=neutral();self.pose_until=0
        self.action_sent=False;self.action_task=None;self.last_sent=False
        self.pose_owner=None;self.pose_received_utc=None;self.pose_epoch=None;self.pose_sequence=None;self.pose_ack_id=0

    def ready(self, home, frame):
        if not self.enabled:return None
        try:return self.evidence(home,frame)
        except (OSError,ValueError,TypeError,KeyError,AttributeError):return None

    def plan(self, home, action, turn):
        self.home=home
        if action not in {'explore','escape','mine_wood','gather_soil','place_block','eat'}:raise ValueError('Unknown actual game decision')
        if type(turn)not in(int,float)or not math.isfinite(turn):raise ValueError('Invalid controller turn')
        self.desired=(action,max(-1.,min(1.,turn)));self.desired_until=self.clock()+2
        self.action_sent=False

    def packet(self, operation, keys=None, look=None):
        self.counter+=1
        return {'type':'operator_input','consumer_id':self.consumer_id,'focus_event_id':self.event_id,
                'input_id':self.counter,'operation':operation,'keys':keys or {},'look_delta':look or [0,0],'hold_ms':250}

    def accept_ack(self, ack, packet, owner):
        if (not isinstance(ack,dict)or ack.get('accepted')is not True or owner!=self.owner
                or ack.get('consumer_id')!=self.consumer_id or ack.get('focus_event_id')!=self.event_id
                or type(ack.get('input_id'))is not int or ack['input_id']!=packet['input_id']
                or ack['input_id']<=self.last_ack):return False
        self.last_ack=ack['input_id']
        applied=ack.get('controller_state')
        if not isinstance(applied,dict):return False
        keys=applied.get('keys');look=applied.get('look_delta');operation=applied.get('pending_operation')
        if (not isinstance(keys,dict)or set(keys)-{'forward','back','left','right','jump','sneak','sprint'}
                or any(type(v)is not bool for v in keys.values())or not isinstance(look,list)or len(look)!=2
                or any(type(v)not in(int,float)or not math.isfinite(v)or abs(v)>.35 for v in look)
                or operation not in(None,'mine','place','use')):return False
        pose=neutral();pose['left_stick']=[float(keys.get('right',False))-float(keys.get('left',False)),float(keys.get('forward',False))-float(keys.get('back',False))]
        pose['right_stick']=[max(-1.,min(1.,look[0]/.035)),max(-1.,min(1.,look[1]/.035))]
        for name in ('jump','sneak','sprint'):pose['buttons'][name]=keys.get(name,False)
        for name in ('mine','place','use'):pose['buttons'][name]=operation==name
        self.pose=pose;self.pose_until=self.clock()+.25
        self.pose_owner=owner;self.pose_received_utc=time.time();self.pose_ack_id=ack['input_id']
        self.pose_epoch=getattr(getattr(self.home,'native_feedback',None),'epoch',None)
        self.pose_sequence=getattr(self.home,'sequence',None)
        return True

    async def _send(self, console, packet, owner):
        ack=await console.operator_input(packet)
        if self.ready(self.home,console.frame_tag)==owner:self.accept_ack(ack,packet,owner)

    async def step(self, console):
        self.current_frame=console.frame_tag
        owner=self.ready(self.home,console.frame_tag)if self.home else None
        valid=bool(owner and self.desired and self.clock()<self.desired_until and console.state.get('connected')and console.active)
        if not valid:
            self.pose=neutral();self.pose_until=0
            if self.last_sent and self.event_id:
                await console.operator_input(self.packet('release'))
            self.last_sent=False;self.owner=None;self.event_id=None
            return
        if self.owner!=owner:
            self.pose=neutral();self.pose_until=0;self.pose_owner=None
            self.owner=owner;self.event_id=uuid.uuid4().hex;self.action_sent=False
        action,turn=self.desired;keys={};look=[0,0]
        if action in {'explore','escape'}:
            keys={'forward':action=='explore','back':action=='escape','sprint':action=='escape'};look=[turn*.035,0]
        packet=self.packet('controls',keys,look);self.last_sent=True
        await self._send(console,packet,owner)
        operation={'mine_wood':'mine','gather_soil':'mine','place_block':'place','eat':'use'}.get(action)
        if operation and not self.action_sent and (self.action_task is None or self.action_task.done()):
            self.action_sent=True;self.action_task=asyncio.create_task(self._send(console,self.packet(operation),owner))

    async def run(self, console):
        try:
            while True:
                await self.step(console);await asyncio.sleep(.1)
        finally:
            self.pose=neutral();self.pose_until=0
            if self.action_task:self.action_task.cancel();await asyncio.gather(self.action_task,return_exceptions=True)
            if self.last_sent and self.event_id:await console.send(self.packet('release'))

    def view(self):
        valid=bool(self.home and self.owner is not None and self.last_sent and self.ready(self.home,getattr(self,'current_frame',None))==self.owner)
        fresh=bool(valid and self.pose_owner==self.owner and self.clock()<self.pose_until)
        return {'enabled':self.enabled,'ready':valid,'pose_fresh':fresh,
                'ack_input_id':self.pose_ack_id if fresh else 0,
                'consumer_id':self.consumer_id if fresh else None,'event_id':self.event_id if fresh else None,
                'epoch':self.pose_epoch if fresh else None,'sequence':self.pose_sequence if fresh else None,
                'pose_received_utc':self.pose_received_utc if fresh else None,
                'pose_lease_ms':max(0,min(250,int((self.pose_until-self.clock())*1000))) if fresh else 0,
                'pose':self.pose if fresh else neutral()}
