"""Independent TV focus evidence, no OS-key fallbacks, and actual bounded wire data."""
import json,math,os,sys,threading
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.pixel_streaming.native_gamepad_input import GamepadIntent,validate_gamepad,read_focus,gamepad_html
from tools.pixel_streaming.native_live_viewer import HTML,validate_input,private_egress_event
from tools.pixel_streaming.native_input_channel import dispatch
from tools.pixel_streaming.native_h264_frontend import h264_html

def focus():
 return {'captured_utc':100.,'native_pid':321,'native_start_ticks':999,'mode':'manual','privacy':False,'focused':True,'device':'tv','surface_tag':'SUB01Device:tv','surface_unique':True,'consumer_id':'a'*32,'focus_event_id':'b'*32,'frame_id':'minecraft-actual-1','surface_bounds':{'center_cm':[-374.7,-5,165],'extent_cm':[0,83,47.5]},'actor_cm':[-250,-5,91],'eye_cm':[-250,-5,165],'hit_cm':[-374.7,-5,165]}

def write(tmp_path,row):
 p=tmp_path/'native-tv-focus.json';p.write_text(json.dumps(row));p.chmod(0o600);return p

def event():return {'action':'gamepad','axes':[0.,-1.,.2,.1],'buttons':9}

@pytest.mark.parametrize('field,value',[('mode','live'),('privacy',True),('focused',False),('device','phone'),('native_pid',123),('native_start_ticks',1),('captured_utc',99.6),('frame_id',''),('surface_unique',False),('consumer_id','bad')])
def test_actual_manual_tv_lease_required(tmp_path,field,value):
 r=focus();r[field]=value;write(tmp_path,r)
 assert read_focus(tmp_path,(321,999),now=100,uid=os.getuid())is None

@pytest.mark.parametrize('axes,buttons',[(None,0),([0,0,0],0),([0,0,0,math.nan],0),([0,0,0,1.01],0),([False,0,0,0],0),([0,0,0,0],True),([0,0,0,0],32),([0,0,0,0],{'jump':True})])
def test_malformed_controls_cannot_enter_intent(axes,buttons):
 with pytest.raises(ValueError):validate_gamepad({'action':'gamepad','axes':axes,'buttons':buttons})

def test_intent_is_server_bound_to_real_current_frame_and_focus(tmp_path):
 write(tmp_path,focus());bridge=GamepadIntent(tmp_path,'c'*32,lambda:(321,999),lambda:True,clock=lambda:100)
 assert bridge.deliver(event())==1
 actual=json.loads(bridge.path.read_text())
 assert actual['native_pid']==321 and actual['native_start_ticks']==999
 assert actual['consumer_id']=='a'*32 and actual['focus_event_id']=='b'*32
 assert actual['frame_id']=='minecraft-actual-1' and actual['captured_utc']==100
 assert actual['buttons']=={'jump':True,'sneak':False,'sprint':False,'mine':True,'place':False}
 assert bridge.path.stat().st_mode&0o077==0
 r=focus();r['privacy']=True;write(tmp_path,r)
 with pytest.raises(PermissionError):bridge.deliver(event())
 assert not bridge.path.exists()

def test_neutral_and_disconnect_remove_only_this_producer(tmp_path):
 write(tmp_path,focus());b=GamepadIntent(tmp_path,'c'*32,lambda:(321,999),lambda:True,clock=lambda:100);b.deliver(event());b.deliver({'action':'gamepad','axes':[0,0,0,0],'buttons':0});assert not b.path.exists()
 b.deliver(event());other=GamepadIntent(tmp_path,'d'*32,lambda:(321,999),lambda:True,clock=lambda:100);other.release();assert b.path.exists();b.release();assert not b.path.exists()

def test_gamepad_wire_stays_inside_existing_short_control_frame_bound():
 payload={'id':2**53-1,'event':{'action':'gamepad','axes':[-.999,-.999,-.999,-.999],'buttons':31}}
 assert len(json.dumps(payload,separators=(',',':')).encode())<=125
 assert validate_input(payload['event'])==payload['event']
 assert private_egress_event(payload['event'])is False

def test_gamepad_never_creates_physical_os_input_and_focus_loss_keeps_video(tmp_path):
 write(tmp_path,focus());b=GamepadIntent(tmp_path,'c'*32,lambda:(321,999),lambda:True,clock=lambda:100)
 class State:
  input_lock=threading.Lock();last_input=0;last_lease=0;accepted=0;session='c'*32;gamepad=b;input=None
  def enabled(self,name):return True
  def can_private_egress(self):return False
 state=State()
 def forbidden():raise AssertionError('Gamepad must not inject OS/home keys')
 status,ack=dispatch(state,event(),validate_input,forbidden,private_egress_event,clock=lambda:10)
 assert status==200 and ack['gamepadAccepted']is True and ack['delivery']=='nativeTVGamepadIntent'
 write(tmp_path,{**focus(),'focused':False});state.last_input=0
 status,ack=dispatch(state,event(),validate_input,forbidden,private_egress_event,clock=lambda:11)
 assert status==200 and ack['gamepadAccepted']is False and ack['delivery']=='none'and state.accepted==1
 assert not b.path.exists()

def test_focus_symbolic_link_and_wrong_permissions_refused(tmp_path):
 p=write(tmp_path,focus());p.chmod(0o644);assert read_focus(tmp_path,(321,999),100)is None
 p.chmod(0o600);target=tmp_path/'elsewhere';p.rename(target);p.symlink_to(target);assert read_focus(tmp_path,(321,999),100)is None

def test_h264_wrap_retains_real_gamepad_focus_gate_and_no_wasd_mapping():
 page=gamepad_html(h264_html(HTML));assert 'nativeMinecraftFocus=h.minecraftFocus===true' in page
 assert 'nativeMinecraftFocus&&!panel.open' in page and "document.visibilityState==='visible'"in page
 assert "action:'gamepad'"in page and "delivery':'XTest'" not in page
 assert 'navigator.getGamepads' in page and 'VideoDecoder' in page
 assert page.count('</script>')==1
