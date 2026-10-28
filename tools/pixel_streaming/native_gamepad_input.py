"""Authenticated private viewer gamepad intent; never forwards OS/home keys.
The native Minecraft consumer independently validates this short lease before
applying to the real game worker. An intent receipt is not a gameplay ACK.
"""
import json,math,os,re,stat,time,uuid
from pathlib import Path
BUTTON_ORDER=('jump','sneak','sprint','mine','place')
BUTTONS=set(BUTTON_ORDER)
SCHEMA='sub01.manual-minecraft-gamepad.v1'

def validate_gamepad(event):
 if not isinstance(event,dict)or set(event)!={'action','axes','buttons'}or event.get('action')!='gamepad':raise ValueError('Bounded gamepad event required')
 axes=event['axes'];buttons=event['buttons']
 if not isinstance(axes,list)or len(axes)!=4 or any(type(x)not in(int,float)or not math.isfinite(x)or abs(x)>1 for x in axes):raise ValueError('Four finite bounded gamepad axes required')
 if type(buttons)is not int or not 0<=buttons<32:raise ValueError('Exact fivebit gamepad buttons required')
 return {'action':'gamepad','axes':[float(x)for x in axes],'buttons':buttons}

def read_focus(private,identity,now=None,uid=None):
 now=time.time()if now is None else now;uid=os.getuid()if uid is None else uid
 if not isinstance(identity,(tuple,list))or len(identity)!=2:return None
 p=Path(private)/'native-tv-focus.json'
 try:
  s=p.lstat()
  if not stat.S_ISREG(s.st_mode)or s.st_uid!=uid or s.st_mode&0o077 or not 0<s.st_size<=4096:return None
  fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
  try:
   ss=os.fstat(fd)
   if (ss.st_ino,ss.st_dev)!=(s.st_ino,s.st_dev):return None
   raw=os.read(fd,4097)
  finally:os.close(fd)
  if len(raw)>4096:return None
  r=json.loads(raw);stamp=r.get('captured_utc')
  if type(stamp)not in(int,float)or not math.isfinite(stamp)or not -.05<=now-stamp<=.35:return None
  if (r.get('native_pid'),r.get('native_start_ticks'))!=tuple(identity)or r.get('mode')!='manual'or r.get('privacy')is not False or r.get('focused')is not True or r.get('device')!='tv'or r.get('surface_tag')!='SUB01Device:tv'or r.get('surface_unique')is not True:return None
  for field in ('consumer_id','focus_event_id'):
   if not isinstance(r.get(field),str)or not re.fullmatch('[a-f0-9]{32}',r[field]):return None
  if not isinstance(r.get('frame_id'),str)or not 0<len(r['frame_id'])<=128:return None
  bounds=r.get('surface_bounds',{});c=bounds.get('center_cm');e=bounds.get('extent_cm')
  def vector(v):return isinstance(v,list)and len(v)==3 and all(type(x)in(int,float)and math.isfinite(x)for x in v)
  if not vector(c)or not vector(e)or any(abs(c[i]-v)>.2 for i,v in enumerate((-374.7,-5,165)))or any(abs(e[i]-v)>.2 for i,v in enumerate((0,83,47.5))):return None
  actor=r.get('actor_cm');eye=r.get('eye_cm');hit=r.get('hit_cm')
  if not all(vector(v)for v in (actor,eye,hit))or not(-430<actor[0]<430 and -450<actor[1]<800 and 50<actor[2]<750)or math.hypot(eye[0]-actor[0],eye[1]-actor[1])>35 or not 40<=eye[2]-actor[2]<=100 or abs(hit[0]+374.7)>.2 or abs(hit[1]+5)>83.2 or abs(hit[2]-165)>47.7 or math.dist(eye,hit)>200.2:return None
  return r
 except(OSError,ValueError,TypeError,AttributeError):return None

class GamepadIntent:
 def __init__(self,private,session,identity,allowed,clock=time.time,uid=None):
  self.private=Path(private);self.session=session;self.identity=identity;self.allowed=allowed;self.clock=clock;self.uid=os.getuid()if uid is None else uid;self.sequence=0
 @property
 def path(self):return self.private/'native-tv-gamepad-input.json'
 def focus(self):
  if not self.allowed():return None
  return read_focus(self.private,self.identity(),self.clock(),self.uid)
 def deliver(self,event):
  event=validate_gamepad(event)
  if event['buttons']==0 and all(x==0 for x in event['axes']):self.release();self.sequence+=1;return self.sequence
  r=self.focus()
  if not r:self.release();raise PermissionError('Actual focused Minecraft TV required')
  self.sequence+=1
  d={k:r[k]for k in ('native_pid','native_start_ticks','consumer_id','focus_event_id','frame_id')};d.update(schema=SCHEMA,captured_utc=self.clock(),producer_session=self.session,sequence=self.sequence,axes=event['axes'],buttons={name:bool(event['buttons']&(1<<i))for i,name in enumerate(BUTTON_ORDER)})
  temp=self.private/('.native-tv-gamepad-'+uuid.uuid4().hex+'.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  try:
   with os.fdopen(fd,'w')as f:json.dump(d,f,separators=(',',':'),allow_nan=False)
   # Recheck actual focus after I/O, never deliver an old native/TV session.
   current=self.focus()
   if not current or any(current[k]!=r[k]for k in ('native_pid','native_start_ticks','consumer_id','focus_event_id','frame_id')):raise PermissionError('Actual Minecraft focus changed')
   os.replace(temp,self.path)
  finally:
   try:temp.unlink()
   except FileNotFoundError:pass
  return self.sequence
 def release(self):
  try:
   p=self.path;s=p.lstat()
   if stat.S_ISREG(s.st_mode)and s.st_uid==self.uid and s.st_size<=2048 and json.loads(p.read_text()).get('producer_session')==self.session:p.unlink()
  except(OSError,ValueError,TypeError):pass

GAMEPAD_JS=r'''
let nativeMinecraftFocus=false,nativePadPending=false,nativePadWasActive=false;
const padButton=(p,i)=>Boolean(p.buttons?.[i]?.pressed||Number(p.buttons?.[i]?.value)>.5);
function minecraftPadValue(p){
 if(!p||p.connected===false||p.mapping!=='standard'||!Array.isArray(p.axes)||p.axes.length<4)return null;
 const axes=p.axes.slice(0,4).map(x=>Number.isFinite(x)?Math.round(Math.max(-1,Math.min(1,x))*1000)/1000:0);
 return {action:'gamepad',axes,buttons:(padButton(p,0)?1:0)|(padButton(p,1)?2:0)|(padButton(p,10)?4:0)|(padButton(p,7)?8:0)|(padButton(p,6)?16:0)};
}
async function releaseMinecraftPad(){if(!nativePadWasActive)return;nativePadWasActive=false;try{await send({action:'gamepad',axes:[0,0,0,0],buttons:0});}catch(e){}}
async function pollMinecraftPad(){
 if(nativePadPending)return;
 const eligible=active&&permission&&!privateEgress&&nativeMinecraftFocus&&!panel.open&&document.visibilityState==='visible'&&document.hasFocus();
 const pads=eligible&&navigator.getGamepads?Array.from(navigator.getGamepads()):[];const p=pads.map(minecraftPadValue).find(Boolean);
 if(!eligible||!p){releaseMinecraftPad();return;}
 nativePadPending=true;nativePadWasActive=true;
 try{const pending=sendNativeSocketInput(p);if(!pending){nativePadWasActive=false;return;}const ack=await pending;if(ack?.gamepadAccepted===false){nativeMinecraftFocus=false;nativePadWasActive=false;return;}document.querySelector('#help').textContent='Controller · Left stick move · Right stick look · A jump · Triggers mine / place · Esc release';}
 catch(e){nativePadWasActive=false;nativeMinecraftFocus=false;}
 finally{nativePadPending=false;}
}
setInterval(pollMinecraftPad,50);window.addEventListener('gamepaddisconnected',releaseMinecraftPad);document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseMinecraftPad();});window.addEventListener('blur',releaseMinecraftPad);
'''
def gamepad_html(html):
 marker='async function ready(){readyAt=performance.now();try{const h=await readHealth();'
 if html.count(marker)!=1 or html.count('</script>')!=1:raise ValueError('Actualnative viewer hooks required')
 html=html.replace(marker,marker+"nativeMinecraftFocus=h.minecraftFocus===true;",1)
 return html.replace('</script>',GAMEPAD_JS+'\n</script>',1)
