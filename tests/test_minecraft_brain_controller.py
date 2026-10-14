"""Disposable source fixtures; no owner state, native seat or grip is fabricated."""
import asyncio,json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from home_minecraft_controller import BrainController,ControllerEvidence,neutral
from home_minecraft_input import PROJECT

class Home:
 activity='play_console';console_game='minecraft';target='sofa';sequence=7
 native_feedback=SimpleNamespace(required=True,epoch='fixture-epoch')
 private=False;seat=True
 def privacy(self):return self.private
 def activity_ready(self,activity):return self.seat

class Console:
 def __init__(self):self.frame_tag='fixture-frame';self.active=True;self.state={'connected':True};self.packets=[]
 async def operator_input(self,p):
  self.packets.append(p)
  return {'accepted':True,'consumer_id':p['consumer_id'],'focus_event_id':p['focus_event_id'],'input_id':p['input_id'],
          'controller_state':{'keys':p['keys'],'look_delta':p['look_delta'],'pending_operation':None}}
 async def send(self,p):self.packets.append(p);return True

def test_no_readiness_no_accepted_pose_and_default_off():
 with patch.dict('os.environ',{},clear=True):assert BrainController().enabled is False
 async def run():
  c=Console();b=BrainController(enabled=True,evidence=lambda h,f:None);b.plan(Home(),'explore',1);await b.step(c)
  assert not c.packets and b.view()['pose']==neutral()
 asyncio.run(run())

def test_ack_order_correlations_and_expiry():
 clock=[10.];b=BrainController(enabled=True,evidence=lambda h,f:('fixture',),clock=lambda:clock[0]);b.home=Home();b.current_frame='fixture-frame';b.owner=('fixture',);b.last_sent=True;b.event_id='e'*32
 p=b.packet('controls',{'forward':True},[.035,0])
 ack={'accepted':True,'consumer_id':b.consumer_id,'focus_event_id':b.event_id,'input_id':p['input_id'],
      'controller_state':{'keys':{'forward':True},'look_delta':[.035,0],'pending_operation':'mine'}}
 assert not b.accept_ack({**ack,'consumer_id':'wrong'},p,b.owner)
 assert not b.accept_ack({**ack,'accepted':False},p,b.owner)
 assert b.accept_ack(ack,p,b.owner)
 assert b.view()['pose']['left_stick']==[0,1] and b.view()['pose']['buttons']['mine']is True
 assert not b.accept_ack(ack,p,b.owner) # duplicate cannot renew the pose lease
 clock[0]=10.251;assert b.view()['pose']==neutral()
 p2=b.packet('controls',{},[0,0]);ack2={**ack,'input_id':p2['input_id'],'controller_state':{'keys':{},'look_delta':[0,0],'pending_operation':None}}
 assert b.accept_ack(ack2,p2,b.owner)
 assert not b.accept_ack(ack,p,b.owner) # late mine response cannot restore an older press
 assert b.view()['pose']==neutral()

def test_privacy_disconnect_and_lost_grip_send_release():
 async def run():
  home=Home();c=Console();b=BrainController(enabled=True,evidence=lambda h,f:None if h.private else('fixture',));b.plan(home,'explore',.4)
  await b.step(c);assert c.packets[-1]['keys']['forward'] and b.view()['pose']['left_stick']==[0,1]
  home.private=True;await b.step(c);assert c.packets[-1]['operation']=='release'and b.view()['pose']==neutral()
  home.private=False;b.plan(home,'escape',0);await b.step(c);c.state['connected']=False;await b.step(c)
  assert c.packets[-1]['operation']=='release'and b.view()['pose']==neutral()
 asyncio.run(run())

def test_protected_receipt_requires_registered_actual_assets_and_same_seat_epoch(tmp_path):
 path=tmp_path/'receipt';home=Home();sha='a'*64
 d={'schema':'sub01-native-controller-v1','mode':'live','privacy':False,'activity':'play_console','node':'sofa','chair':'sofa','route_sequence':7,'epoch':'fixture-epoch','frame_id':'fixture-frame','seat_verified':True,'grip_verified':True,'assembly_asset':'fixture-assembly','source_sha':sha,'import_sha':'d'*64,'capture_time':4.,'contact_review_sha':'b'*64,'owner_asset':'/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','capture_asset':'/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming','captured_utc':100.,'native_pid':123,'native_start_ticks':456}
 def write():path.write_text(json.dumps(d));path.chmod(0o600)
 write();uid=path.stat().st_uid
 e=ControllerEvidence(path,process=lambda pid:(uid,456,[PROJECT.encode(),b'-game']),wall=lambda:100.,uid=uid,assembly='fixture-assembly',source_sha=sha,import_sha='d'*64,contact_review='b'*64)
 assert e(home,'fixture-frame')
 assert not ControllerEvidence(path,uid=uid,assembly='',source_sha=sha)(home,'fixture-frame')
 for key,value in [('grip_verified',False),('seat_verified',False),('mode','manual'),('epoch','old'),('route_sequence',6),('native_start_ticks',457),('captured_utc',99.),('capture_asset','other'),('capture_time',6.),('contact_review_sha','c'*64),('import_sha','e'*64),('frame_id','old-frame')]:
  before=d[key];d[key]=value;write();assert not e(home,'fixture-frame');d[key]=before
 write();home.seat=False;assert not e(home,'fixture-frame');home.seat=True;path.chmod(0o644);assert not e(home,'fixture-frame')

def test_intent_expiry_releases_without_replaying_old_acks():
 async def run():
  clock=[10.];home=Home();c=Console();b=BrainController(enabled=True,evidence=lambda h,f:('fixture',),clock=lambda:clock[0]);b.plan(home,'explore',.2)
  await b.step(c);old_owner=b.owner;old_packet=c.packets[-1];old_ack={'accepted':True,'consumer_id':b.consumer_id,'focus_event_id':b.event_id,'input_id':old_packet['input_id'],'controller_state':{'keys':{'forward':True},'look_delta':[.007,0],'pending_operation':None}}
  clock[0]=12.001;await b.step(c)
  assert c.packets[-1]['operation']=='release'and b.view()['pose']==neutral()
  assert not b.accept_ack(old_ack,old_packet,old_owner)
 asyncio.run(run())

def test_real_home_model_sequence_and_native_seat_are_required(tmp_path):
 from home_world import HomeWorld,NODES
 world=HomeWorld({'node':'sofa','seated':1,'sequence':7,'native_consumer_required':True,'console_game':'minecraft'})
 world.activity='play_console'
 p=tmp_path/'receipt';uid=__import__('os').getuid();sha='a'*64;review='b'*64
 d={'schema':'sub01-native-controller-v1','mode':'live','privacy':False,'activity':'play_console','node':'sofa','chair':'sofa','route_sequence':7,'epoch':'fixture-epoch','frame_id':'fixture-frame','seat_verified':True,'grip_verified':True,'assembly_asset':'fixture-assembly','source_sha':sha,'import_sha':'d'*64,'owner_asset':'/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner','capture_asset':'/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming','capture_time':4.,'contact_review_sha':review,'captured_utc':100.,'native_pid':123,'native_start_ticks':456}
 p.write_text(json.dumps(d));p.chmod(0o600)
 e=ControllerEvidence(p,process=lambda pid:(uid,456,[PROJECT.encode(),b'-game']),wall=lambda:100.,uid=uid,assembly='fixture-assembly',source_sha=sha,import_sha='d'*64,contact_review=review)
 assert not e(world,'fixture-frame') # saved timer seating is insufficient
 common={'epoch':'fixture-epoch','sequence':7,'activity':'play_console','node':'sofa'}
 world.native_feedback.accept({**common,'bind':True,'phase':'walking'},sequence=7,activity='play_console',target='sofa',nodes=NODES)
 assert not e(world,'fixture-frame')
 world.native_feedback.accept({**common,'phase':'seated','chair':'sofa'},sequence=7,activity='play_console',target='sofa',nodes=NODES)
 assert e(world,'fixture-frame')
 world.sequence+=1;assert not e(world,'fixture-frame')

def test_new_physical_owner_cannot_display_previous_owner_ack():
 async def run():
  owner=[('first',)];home=Home();c=Console();b=BrainController(enabled=True,evidence=lambda h,f:owner[0]);b.plan(home,'explore',0)
  await b.step(c);assert b.view()['pose_fresh']is True
  owner[0]=('second',)
  pending=asyncio.Event();finish=asyncio.Event()
  async def delayed(p):pending.set();await finish.wait();return None
  c.operator_input=delayed;step=asyncio.create_task(b.step(c));await pending.wait()
  assert b.view()['pose_fresh']is False and b.view()['ack_input_id']==0 and b.view()['pose']==neutral()
  finish.set();await step
 asyncio.run(run())
