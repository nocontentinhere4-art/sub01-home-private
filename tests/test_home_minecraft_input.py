"""Native-TV admission fixtures; these are not actual native/gameplay proofs."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from home_world import HomeWorld
from home_minecraft_input import NativeTVInput,PROJECT,add_minecraft_input_routes

C='1'*32;E='2'*32

def receipt():
 return {'captured_utc':100,'mode':'manual','focused':True,'privacy':False,'device':'tv',
         'consumer_id':C,'focus_event_id':E,'frame_id':'actual-fixture-frame',
         'native_pid':123,'native_start_ticks':456,'component_identity':'fixture unique component',
         'surface_tag':'SUB01Device:tv','surface_unique':True,
         'surface_bounds':{'center_cm':[-374.7,-5,165],'extent_cm':[0,83,47.5]},
         'actor_cm':[-275,-5,95.65],'eye_cm':[-275,-5,169.65],'hit_cm':[-374.7,-5,165]}

def fixture(tmp_path,enabled=True):
 p=tmp_path/'receipt.json';p.write_text(json.dumps(receipt()));p.chmod(0o600);clock=[100.]
 policy=NativeTVInput(enabled=enabled,receipt=p,uid=os.getuid(),wall=lambda:clock[0],monotonic=lambda:clock[0],
                      process=lambda pid:(os.getuid(),456,[PROJECT.encode(),b'-game']))
 return policy,p,clock

def focus():return {'consumer_id':C,'focus_event_id':E,'frame_id':'actual-fixture-frame'}
def packet(n=1,operation='controls'):
 return {**focus(),'input_id':n,'operation':operation,**({'keys':{'forward':True},'look_delta':[.1,0]}if operation=='controls'else{})}

def test_independent_process_receipt_required_and_feature_stays_off(tmp_path):
 import pytest
 p,file,clock=fixture(tmp_path,False)
 with pytest.raises(PermissionError):p.focus(focus(),'actual-fixture-frame',False)
 p.enabled=True
 for change in [{'mode':'live'},{'privacy':True},{'focused':False},{'native_start_ticks':457},
                {'surface_unique':False},{'actor_cm':[0,0,0]},{'hit_cm':[-374.7,200,165]},
                {'frame_id':'old'},{'captured_utc':99.0},{'consumer_id':[]}]:
  file.write_text(json.dumps({**receipt(),**change}))
  with pytest.raises((ValueError,TypeError)):p.focus(focus(),'actual-fixture-frame',False)
  assert p.owner is None and p.until==0
 file.write_text(json.dumps(receipt()));file.chmod(0o644)
 with pytest.raises(ValueError):p.focus(focus(),'actual-fixture-frame',False)
 file.chmod(0o600);p.process=lambda pid:(os.getuid(),456,[PROJECT.encode(),b'-run=pythonscript'])
 with pytest.raises(ValueError):p.focus(focus(),'actual-fixture-frame',False)

def test_freshness_frame_order_bounded_keys_and_release(tmp_path):
 import pytest
 p,file,clock=fixture(tmp_path);p.focus(focus(),'actual-fixture-frame',False)
 sent=p.control(packet(),'actual-fixture-frame',False);assert sent['hold_ms']==250 and sent['keys']=={'forward':True}
 expiry=p.until
 for data in [packet(),{**packet(2),'keys':{'forward':1}},{**packet(2),'look_delta':[1,0]},
              {**packet(2),'input_id':True},{**packet(2),'operation':'teleport'}]:
  with pytest.raises((PermissionError,ValueError)):p.control(data,'actual-fixture-frame',False)
  assert p.counter==1 and p.until==expiry
 # A new current frame is insufficient unless the independent displayed receipt matches it.
 with pytest.raises(PermissionError):p.control({**packet(2),'frame_id':'new-frame'},'new-frame',False)
 clock[0]=100.8;assert not p.active()
 with pytest.raises(PermissionError):p.control(packet(2),'actual-fixture-frame',False)
 assert p.control({**packet(2,'release'),'frame_id':'stale'},'different',True)['operation']=='release'
 assert not p.active()

def test_actual_registered_native_http_auth_privacy_and_worker_ack(tmp_path,monkeypatch):
 async def run():
  import home_minecraft_input as module
  policy,file,clock=fixture(tmp_path);monkeypatch.setattr(module,'NativeTVInput',lambda:policy)
  world=HomeWorld({'native_consumer_required':True});world.console_game='minecraft';packets=[]
  async def sender(p):packets.append(p);return {'accepted':True,'input_id':p['input_id'],'kind':'fixture worker ack'}
  console=SimpleNamespace(enabled=True,frame_tag='actual-fixture-frame',operator_input=sender)
  app=web.Application();add_minecraft_input_routes(app,SimpleNamespace(home=world,minecraft=console),lambda r:r.headers.get('X-Admin-Token')=='fixture token')
  client=TestClient(TestServer(app));await client.start_server();auth={'X-Admin-Token':'fixture token'}
  try:
   assert(await client.post('/api/home/minecraft/focus',json=focus())).status==403
   assert(await client.post('/api/home/minecraft/input',json=packet())).status==403
   assert(await client.post('/api/home/minecraft/focus',headers=auth,json=focus())).status==200
   assert(await client.post('/api/home/minecraft/input',headers=auth,json=packet())).status==200
   assert len(packets)==1 and packets[0]['hold_ms']==250
   assert world.native_feedback.required and not world.activity_ready('play_console')
   world.node=world.target='bathroom'
   assert(await client.post('/api/home/minecraft/input',headers=auth,json=packet(2))).status==409
   assert len(packets)==1
   assert(await client.post('/api/home/minecraft/input',headers=auth,json=packet(2,'release'))).status==200
   assert packets[-1]['operation']=='release'
   policy.enabled=False;world.node=world.target='desk'
   assert(await client.post('/api/home/minecraft/focus',headers=auth,json=focus())).status==409
  finally:await client.close()
 asyncio.run(run())

def test_console_requires_worker_receipt_not_pipe_ack(tmp_path):
 async def run():
  from home_minecraft import MinecraftConsole
  import json
  c=MinecraftConsole(tmp_path);stream=asyncio.StreamReader()
  c.worker=SimpleNamespace(stdout=stream)
  async def send(p):
   # An unrelated late input cannot acknowledge this operation.
   stream.feed_data((json.dumps({'type':'input_receipt','consumer_id':C,'focus_event_id':E,'input_id':3,'accepted':True})+'\n').encode())
   return True
  c.send=send
  reader=asyncio.create_task(c.read_worker())
  pending=asyncio.create_task(c.operator_input({'consumer_id':C,'focus_event_id':E,'input_id':4}))
  await asyncio.sleep(.01);assert not pending.done()
  stream.feed_data((json.dumps({'type':'input_receipt','consumer_id':C,'focus_event_id':E,'input_id':4,'accepted':False,'reason':'not connected'})+'\n').encode())
  result=await pending;assert result['accepted'] is False
  stream.feed_eof();await reader
 asyncio.run(run())

def test_manual_activation_is_separate_from_sofa_and_never_runs_autonomous_choice(tmp_path):
 async def run():
  from home_minecraft import MinecraftConsole
  c=MinecraftConsole(tmp_path);c.enabled=True;c.state={'connected':True};sent=[]
  world=HomeWorld({'native_consumer_required':True});world.console_game='minecraft';world.activity='phone'
  lease={'allowed':False}
  c.native_input=SimpleNamespace(active=lambda private:lease['allowed'] and not private)
  async def sender(p):sent.append(p);return True
  c.send=sender
  c.choose=lambda rel:(_ for _ in ()).throw(AssertionError('Manual ownership must not synthesize autonomous play'))
  await c.agent_step(world,{});assert not sent and not c.active
  lease['allowed']=True
  await c.agent_step(world,{});assert sent[-1]=={'type':'active','value':True} and c.active
  assert not world.activity_ready('play_console') and world.native_feedback.required
  world.node=world.target='bathroom'
  await c.agent_step(world,{});assert sent[-1]=={'type':'active','value':False} and not c.active
 asyncio.run(run())

def test_cancel_revokes_focus_lease_even_with_stale_frame(tmp_path):
 import pytest
 p,file,clock=fixture(tmp_path);p.focus(focus(),'actual-fixture-frame',False)
 assert p.active()
 p.control({**packet(1,'cancel'),'frame_id':'old'},'new',True)
 assert p.until==0 and not p.active()
 with pytest.raises(PermissionError):p.control(packet(2),'actual-fixture-frame',False)


def test_recovered_project_is_exact_and_legacy_or_editor_receipts_refuse(tmp_path):
 import pytest
 assert PROJECT == '/workspace/sub01-private-recovered-project/Sub01HomeLab/Sub01HomeLab.uproject'
 policy, file, clock = fixture(tmp_path)
 policy.focus(focus(), 'actual-fixture-frame', False)
 for args in [
  [b'/workspace/sub01-home-private/project/Sub01HomeLab/Sub01HomeLab.uproject', b'-game'],
  [PROJECT.encode() + b'.other', b'-game'],
  [PROJECT.encode(), b'-run=pythonscript'],
  [PROJECT.encode(), b'-game-other'],
 ]:
  policy.owner = None; policy.until = 0
  policy.process = lambda pid, args=args: (os.getuid(), 456, args)
  with pytest.raises(ValueError, match='Native process identity changed'):
   policy.focus(focus(), 'actual-fixture-frame', False)
  assert policy.owner is None and policy.until == 0
