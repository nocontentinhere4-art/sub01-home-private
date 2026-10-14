"""Live native X11 pixels and bounded physical input, behind authenticated Jupyter.

Run as unreal on the authorized server. This is an HTTP fallback, not WebRTC.
It never launches Unreal or moves an actor through a backend/state API.
"""
import argparse
import base64
import hashlib
import struct
import ctypes
import ctypes.util
import json
import os
import signal
import subprocess
import threading
import time
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

KEYS = {**{f"Key{x.upper()}": x for x in "abcdefghijklmnopqrstuvwxyz"},
        **{f"Digit{x}": x for x in "0123456789"},
        "Space": "space", "Enter": "Return", "Escape": "Escape",
        "Backspace": "BackSpace", "ShiftLeft": "Shift_L", "ShiftRight": "Shift_R",
        "Minus": "minus", "Equal": "equal", "Period": "period", "Comma": "comma",
        "Slash": "slash", "Semicolon": "semicolon", "Quote": "apostrophe",
        "BracketLeft": "bracketleft", "BracketRight": "bracketright", "Backslash": "backslash"}

def validate_input(value):
    if not isinstance(value, dict):
        raise ValueError("Expected input object")
    action = value.get("action")
    if action == "release" and set(value) == {"action"}:
        return value
    if action == "key" and set(value) == {"action", "code", "down"}:
        if value["code"] in KEYS and type(value["down"]) is bool:
            return value
    if action == "mouse" and set(value) == {"action", "dx", "dy"}:
        if all(type(value[x]) is int and abs(value[x]) <= 100 for x in ("dx", "dy")):
            return value
    if action == "button" and set(value) == {"action", "button", "down"}:
        if type(value["button"]) is int and value["button"] in (1, 3) and type(value["down"]) is bool:
            return value
    raise ValueError("Unsupported input")

LAMPS = {"DeskLamp", "BedLamp", "KitchenWork", "LowerPendant", "UpperPendant"}

def validate_settings(value, capabilities):
    """Validate the whole request before altering any native control file."""
    import math
    if not isinstance(value, dict) or not value or set(value)-{'fov','hour','lamps'}:
        raise ValueError('Unsupported view settings')
    for name, low, high in [('fov',50,110),('hour',0,24)]:
        if name in value:
            v=value[name]
            if capabilities.get(name) is not True or type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high:
                raise ValueError('View setting unavailable or out of bounds')
    if 'lamps' in value:
        lamps=value['lamps'];available=capabilities.get('lamps',[])
        if not isinstance(available,list) or not isinstance(lamps,dict) or not lamps:
            raise ValueError('Indoor lamps unavailable')
        if any(k not in LAMPS or k not in available or type(v) is not bool for k,v in lamps.items()):
            raise ValueError('Unsupported indoor lamp')
    return value

def canonical_privacy(document):
    if not isinstance(document,dict) or set(document)!={'target','sequence','activity','privacy'}:return None
    if type(document['privacy']) is not bool or type(document['sequence']) is not int:return None
    if any(not isinstance(document[k],str) or not 0<len(document[k])<=80 for k in ('target','activity')):return None
    return document['privacy']

def native_camera_privacy(receipt, identity, now):
    import math
    if not isinstance(receipt,dict) or identity is None:return None
    if (receipt.get('native_pid'),receipt.get('native_start_ticks'))!=identity:return None
    utc=receipt.get('captured_utc')
    if type(utc) not in (float,int) or not math.isfinite(utc) or not -.25<=now-utc<=1:return None
    private=receipt.get('physical_camera_private')
    return private if type(private) is bool else None

def native_view_mode(receipt, identity, now):
    """Mode is useful only while its actual process/camera heartbeat is fresh."""
    if native_camera_privacy(receipt,identity,now) is None:return None
    mode=receipt.get('view_mode')
    return mode if mode in ('manual','live','diagnostic') else None

ACTIVITY_LABELS={'sleep':'Rest','phone':'Phone','eat':'Meal','buy_bread':'Bakery','buy_konbini':'Shop','window':'Window','park':'Park','research':'Research','order_food':'Ordering food','get_delivery':'Delivery','chat':'Conversation','watch_video':'Videos','play_chess':'Chess','use_computer':'Computer','play_console':'Game','use_bathroom':'Bathroom','listen_music':'Music'}

def public_live_activity(document):
    """Return only the existing bridge's public, current stage and activity label."""
    if not isinstance(document,dict) or document.get('privacy') is not False:return None
    source=document.get('source');brain=document.get('brain')
    if not isinstance(source,dict) or source.get('status')!='live' or not isinstance(brain,dict):return None
    stage=brain.get('stage')
    if stage not in ('AWAKE','NREM','REM'):return None
    return {'awake':stage=='AWAKE','activity':ACTIVITY_LABELS.get(brain.get('activity')) if isinstance(brain.get('activity'),str) else None}

def combine_privacy(backend,physical):
    if backend is True or physical is True:return True
    return False if backend is False and physical is False else None

def private_egress_event(event):
    return (event['action']=='release' or event['action']=='mouse' or
            event['action']=='key' and event['code'] in {'KeyW','KeyA','KeyS','KeyD'})

class PhysicalInput:
    def __init__(self):
        self.x = ctypes.CDLL(ctypes.util.find_library("X11"))
        self.xt = ctypes.CDLL(ctypes.util.find_library("Xtst"))
        self.x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x.XOpenDisplay.restype = ctypes.c_void_p
        self.x.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x.XStringToKeysym.restype = ctypes.c_ulong
        self.x.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x.XKeysymToKeycode.restype = ctypes.c_uint
        self.x.XFlush.argtypes = [ctypes.c_void_p]
        for name in ("XTestFakeKeyEvent", "XTestFakeButtonEvent"):
            getattr(self.xt, name).argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        self.xt.XTestFakeRelativeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        self.display = self.x.XOpenDisplay(b":99")
        if not self.display:
            raise RuntimeError("Private native display unavailable")
        self.held = set()
        self.buttons = set()

    def send(self, event):
        action = event["action"]
        if action == "release":
            for code in list(self.held):
                self.send({"action": "key", "code": code, "down": False})
            for button in list(self.buttons):
                self.send({"action": "button", "button": button, "down": False})
        elif action == "key":
            code = event["code"]
            key = self.x.XKeysymToKeycode(self.display, self.x.XStringToKeysym(KEYS[code].encode()))
            if not key or not self.xt.XTestFakeKeyEvent(self.display, key, event["down"], 0):
                raise RuntimeError("Native key delivery failed")
            self.held.add(code) if event["down"] else self.held.discard(code)
        elif action == "button":
            if not self.xt.XTestFakeButtonEvent(self.display, event["button"], event["down"], 0):
                raise RuntimeError("Native button delivery failed")
            self.buttons.add(event["button"]) if event["down"] else self.buttons.discard(event["button"])
        elif not self.xt.XTestFakeRelativeMotionEvent(self.display, event["dx"], event["dy"], 0):
            raise RuntimeError("Native mouse delivery failed")
        self.x.XFlush(self.display)

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>SUB-01 · Home</title>
<style>
[hidden]{display:none!important}
:root{font-family:Inter,Arial,sans-serif;color:#f6f0e9;background:#151411;color-scheme:dark;--accent:#ff713d}*{box-sizing:border-box}body{margin:0;height:100dvh;overflow:hidden}button{font:inherit;color:inherit;cursor:pointer;border:1px solid #ffffff2b;background:#24221eee;border-radius:9px;padding:10px 15px;transition:background .15s}button:hover{background:#383229}button:disabled{opacity:.45;cursor:default}button.primary{background:var(--accent);color:#24140d;border-color:var(--accent);font-weight:600}button.primary:hover{background:#ff8c61}header{height:72px;padding:0 26px;display:flex;align-items:center;gap:20px;background:#191714;border-bottom:1px solid #ffffff12}.brand{display:flex;align-items:center;gap:10px;font-size:19px;font-weight:700;letter-spacing:.12em}.mark{width:20px;height:20px;background:var(--accent);border-radius:5px 5px 5px 0;transform:rotate(-8deg)}.private{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#938d84;border-left:1px solid #4b453e;padding-left:20px}.actions{margin-left:auto;display:flex;gap:9px}.view{height:calc(100dvh - 72px);position:relative;display:flex;align-items:center;justify-content:center;background:#0b0b0a}#game{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;display:block}.bottom{position:absolute;bottom:20px;left:22px;right:22px;display:flex;align-items:center;justify-content:space-between;gap:14px;pointer-events:none}.pill{background:#191714e8;border:1px solid #ffffff1c;padding:10px 14px;border-radius:30px;font-size:12px;color:#ded5ca;backdrop-filter:blur(12px)}.dot{display:inline-block;width:6px;height:6px;background:#999287;border-radius:50%;margin-right:8px}.dot.live{background:#77bf8a}.help{font-size:12px;color:#dfd7cc;text-shadow:0 1px 4px #000;background:#161411bd;padding:9px 14px;border-radius:25px}.empty{position:absolute;text-align:center;color:#aaa195;padding:24px}.empty strong{display:block;font-size:23px;font-weight:400;color:#e4ddd3;margin-bottom:12px}.view:fullscreen{height:100dvh}dialog{border:1px solid #ffffff20;border-radius:18px;background:#211e19;color:#ede6dd;width:min(440px,90vw);padding:28px;box-shadow:0 25px 100px #0008}dialog::backdrop{background:#0008;backdrop-filter:blur(6px)}h2{margin:0 0 25px;font-size:23px;font-weight:500}.row{display:flex;justify-content:space-between;align-items:center;margin:18px 0}input[type=range]{width:180px;accent-color:var(--accent)}.muted{font-size:12px;color:#aaa195;line-height:1.6}kbd{font:11px inherit;border:1px solid #ffffff30;border-radius:4px;padding:2px 5px}.close{float:right;background:none;padding:4px 8px}.operator{margin-top:24px;border-top:1px solid #ffffff20;padding-top:17px;font-size:12px;color:#aba397}.operator summary{cursor:pointer}.operator p{line-height:1.6}.sr{position:absolute;left:-10000px}@media(max-width:600px){header{padding:0 14px;gap:12px}.private{display:none}.actions{gap:5px}button{padding:9px 11px}.help{display:none}.bottom{left:12px;bottom:12px}.brand{font-size:16px}}
</style></head><body>
<header><div class="brand"><span class="mark" aria-hidden="true"></span>SUB-01</div><span class="private">Private home</span><div class="actions"><button id="control" class="primary" disabled>Enter home</button><button id="full" aria-label="Fullscreen">⤢</button><button id="settings" aria-label="Settings">⚙</button></div></header>
<main class="view" id="view"><img id="game" alt="Live first-person view of the home" hidden><div class="empty" id="empty"><strong>Your home, live.</strong><span id="emptyText">Connecting to the private session…</span></div><div class="bottom"><div class="pill"><span id="dot" class="dot"></span><span id="status" aria-live="polite">Connecting</span></div><span class="help" id="help" hidden>WASD move · Mouse look · E interact · Esc release</span></div></main>
<dialog id="panel"><button class="close" id="close" aria-label="Close settings">×</button><h2>Settings</h2><label class="row">Look sensitivity <input id="sensitivity" type="range" min="0.25" max="2" step="0.05" value="1"></label><p class="muted">Click Enter home to take control. Press <kbd>Esc</kbd> to release the mouse and open settings.</p><div id="nativeSettings" hidden></div><details class="operator"><summary>Session</summary><p id="sessionState">Private connection · Live native view</p><p>The view comes directly from the running home. Controls are available only when the native session releases them.</p></details></dialog>
<script>
const game=document.querySelector('#game'),status=document.querySelector('#status'),panel=document.querySelector('#panel'),control=document.querySelector('#control'),empty=document.querySelector('#empty'),dot=document.querySelector('#dot');
const base=location.pathname.endsWith('/')?location.pathname:location.pathname.replace(/[^/]*$/,'');
let streamOpenedAt=0;
let active=false,lastMouse=0,accepted=0,inputQueue=Promise.resolve(),streaming=false,permission=false,privateEgress=false,live=false,previous=null,streamGeneration=0;
window.nativeViewerDecodedFrames=0;window.nativeViewerTransport='connecting';
function xsrf(){return document.cookie.split('; ').find(v=>v.startsWith('_xsrf='))?.split('=').slice(1).join('=')||'';}
function settings(){if(!panel.open)panel.showModal();}
function clearPixels(){game.hidden=true;game.removeAttribute('src');if(previous){URL.revokeObjectURL(previous);previous=null;}}
function releaseNativeFocus(){if(permission){send({action:'key',code:'Escape',down:true}).catch(()=>{});send({action:'key',code:'Escape',down:false}).catch(()=>{});}}
function release(){if(active)releaseNativeFocus();active=false;send({action:'release'}).catch(()=>{});if(document.pointerLockElement)document.exitPointerLock();}
document.querySelector('#settings').onclick=()=>{release();settings();};document.querySelector('#close').onclick=()=>panel.close();
document.querySelector('#full').onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else document.querySelector('#view').requestFullscreen();};
async function deliver(event){const r=await fetch(base+'input',{method:'POST',headers:{'Content-Type':'application/json','X-XSRFToken':decodeURIComponent(xsrf())},body:JSON.stringify(event)});const p=await r.json();if(r.ok){accepted=p.acceptedInputs;window.nativeViewerAcceptedInputs=accepted;}else{active=false;status.textContent=p.error;}return p;}
function send(event){const operation=inputQueue.then(()=>deliver(event));inputQueue=operation.catch(()=>{active=false;status.textContent='Control connection interrupted';});return operation;}
control.onclick=async()=>{const h=await fetch(base+'health').then(r=>r.json());if(!h.inputEnabled&&!h.privacyEgressEnabled)return;privateEgress=!h.inputEnabled&&h.privacyEgressEnabled;panel.close();active=true;(privateEgress?document.querySelector('#view'):game).requestPointerLock();};
document.addEventListener('pointerlockchange',()=>{if(document.pointerLockElement!==game&&document.pointerLockElement!==document.querySelector('#view')){const was=active;if(was)releaseNativeFocus();active=false;send({action:'release'}).catch(()=>{});if(was)settings();}});window.addEventListener('blur',()=>release());
const allowed=new Set(%KEYS%);
for(const [name,down]of[['keydown',true],['keyup',false]])document.addEventListener(name,e=>{if(e.code==='Escape'&&down){if(active)release();else settings();return;}if(!active||!allowed.has(e.code)||(privateEgress&&!['KeyW','KeyA','KeyS','KeyD'].includes(e.code))||e.ctrlKey||e.metaKey||e.altKey)return;e.preventDefault();if(!e.repeat)send({action:'key',code:e.code,down}).catch(()=>{});});
document.addEventListener('mousemove',e=>{if(!active||(document.pointerLockElement!==game&&document.pointerLockElement!==document.querySelector('#view'))||performance.now()-lastMouse<30)return;lastMouse=performance.now();const s=Number(document.querySelector('#sensitivity').value);send({action:'mouse',dx:Math.max(-100,Math.min(100,Math.round(e.movementX*s))),dy:Math.max(-100,Math.min(100,Math.round(e.movementY*s)))}).catch(()=>{});});
for(const[name,down]of[['mousedown',true],['mouseup',false]])game.addEventListener(name,e=>{if(active&&!privateEgress&&(e.button===0||e.button===2)){e.preventDefault();send({action:'button',button:e.button===0?1:3,down}).catch(()=>{});}});game.oncontextmenu=e=>e.preventDefault();
async function decode(blob,sequence,captured,generation){const url=URL.createObjectURL(blob);let retained=false;try{if(generation!==streamGeneration)return;const decoded=new Image();decoded.src=url;await Promise.race([decoded.decode(),new Promise((_,reject)=>setTimeout(()=>reject(Error('Frame decode timeout')),1500))]);if(generation!==streamGeneration)return;game.src=url;if(previous)URL.revokeObjectURL(previous);previous=url;retained=true;window.nativeViewerDecodedFrames++;window.nativeViewerLastSequence=sequence;window.nativeViewerLastCaptureUtc=captured;window.nativeViewerLastDecodedAt=performance.now();game.hidden=false;empty.hidden=true;}catch(e){throw e;}finally{if(!retained)URL.revokeObjectURL(url);}}
async function finite(generation){window.nativeViewerTransport='https-jpeg';let after=0;while(streaming&&generation===streamGeneration){const r=await fetch(base+'frame.jpg?after='+after,{cache:'no-store'});if(!r.ok)throw new Error('Capture unavailable');after=Number(r.headers.get('X-Native-Sequence'));await decode(await r.blob(),after,Number(r.headers.get('X-Native-Capture-Utc')),generation);}}
function streamNative(){streamOpenedAt=performance.now();window.nativeViewerLastDecodedAt=0;const generation=++streamGeneration;let decoding=false,opened=false;const ws=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+base+'socket');window.nativeViewerSocket=ws;ws.binaryType='arraybuffer';ws.onopen=()=>{opened=true;window.nativeViewerTransport='wss-jpeg';};ws.onmessage=async e=>{if(decoding||e.data.byteLength<18)return;decoding=true;try{const d=new DataView(e.data);await decode(new Blob([e.data.slice(16)],{type:'image/jpeg'}),Number(d.getBigUint64(0)),d.getFloat64(8),generation);}catch(e){}finally{decoding=false;}};ws.onclose=()=>{if(generation!==streamGeneration||!streaming)return;finite(generation).catch(()=>{if(generation===streamGeneration){streaming=false;status.textContent='Live view unavailable';clearPixels();empty.hidden=false;}});};ws.onerror=()=>{};setTimeout(()=>{if(!opened&&generation===streamGeneration)ws.close();},2500);}
async function ready(){try{const h=await fetch(base+'health'+(active?'?hold=1':'')).then(r=>r.json());live=h.nativeAlive&&h.captureEnabled;document.querySelector('.private').textContent=h.privacy===false&&h.viewMode==='manual'?'Explore home':h.privacy===false&&h.viewMode==='live'?'Live home':'Private home';permission=live&&h.inputEnabled;privateEgress=h.privacy===true&&h.privacyEgressEnabled;control.disabled=!permission&&!privateEgress;control.textContent=privateEgress?'Move to exit':active?'In the home':'Enter home';document.querySelector('#help').hidden=!permission&&!privateEgress;document.querySelector('#help').textContent=privateEgress?'WASD move to leave · Mouse look · Esc release':'WASD move · Mouse look · E interact · Esc release';dot.classList.toggle('live',live);document.querySelector('#sessionState').textContent=live?(permission?'Private connection · Control available':'Private connection · View only'):'Private connection · Home unavailable';if(!live){if(active&&!privateEgress)release();streaming=false;streamGeneration++;window.nativeViewerSocket?.close();clearPixels();empty.hidden=false;status.textContent=!h.nativeAlive?'Home unavailable':h.privacy===true?(privateEgress?'Private · Movement only':'Privacy'):h.privacy===null?'Privacy state unavailable':h.nativeAlive?'Preparing live view':'Home unavailable';document.querySelector('#emptyText').textContent=!h.nativeAlive?'The home is paused. Waiting for a fresh live session.':h.privacy===true?(privateEgress?'The view stays private. Use movement controls to leave the bathroom.':'The home is private. Live view and controls are paused.'):h.privacy===null?'Live view is paused until privacy can be verified.':h.nativeAlive?'The private session is preparing the view.':'The native session is not running.';return;}if(streaming&&performance.now()-(window.nativeViewerLastDecodedAt||streamOpenedAt)>3500){streaming=false;streamGeneration++;window.nativeViewerSocket?.close();clearPixels();empty.hidden=false;status.textContent='Live view interrupted';document.querySelector('#emptyText').textContent='Waiting for fresh frames from the home.';if(active)release();control.disabled=true;return;}status.textContent=h.viewMode==='live'&&h.activity&&typeof h.activity.awake==='boolean'?(h.activity.awake?'Awake':'Asleep')+(h.activity.activity?' · '+h.activity.activity:''):active?'You are in control':permission?'Live · Ready to enter':'Live · View only';if(!streaming){streaming=true;streamNative();}}catch(e){active=false;permission=false;privateEgress=false;live=false;streaming=false;streamGeneration++;window.nativeViewerSocket?.close();clearPixels();empty.hidden=false;control.disabled=true;if(document.pointerLockElement)document.exitPointerLock();status.textContent='Private connection unavailable';document.querySelector('#emptyText').textContent='Live view is paused until the private connection returns.';}}

let supported='',settingsPending=false;
function syncSettingValues(p){
 if(settingsPending)return;
 for(const input of document.querySelectorAll('#nativeSettings input[data-native-key]'))if(input!==document.activeElement)input.value=p.values[input.dataset.nativeKey];
 for(const input of document.querySelectorAll('#nativeSettings input[data-native-lamp]'))input.checked=p.values.lamps[input.dataset.nativeLamp];
 const master=document.querySelector('#nativeSettings input[data-native-master]');
 if(master){const values=(p.capabilities.lamps||[]).map(name=>p.values.lamps[name]);master.checked=values.every(Boolean);master.indeterminate=values.some(Boolean)&&!master.checked;}
}
async function refreshSettings(){
 try{
  const r=await fetch(base+'settings');if(!r.ok)return;
  const p=await r.json(),caps=p.capabilities,holder=document.querySelector('#nativeSettings'),signature=JSON.stringify(caps);
  if(supported===signature){syncSettingValues(p);return;}
  supported=signature;holder.replaceChildren();holder.hidden=false;
  const apply=async value=>{
   settingsPending=true;
   try{
    const r=await fetch(base+'settings',{method:'POST',headers:{'Content-Type':'application/json','X-XSRFToken':decodeURIComponent(xsrf())},body:JSON.stringify(value)});
    const q=await r.json();if(!r.ok){status.textContent=q.error;return;}
    for(let n=0;n<10;n++){
     await new Promise(r=>setTimeout(r,150));const ack=await fetch(base+'settings').then(r=>r.json());
     if(ack.revision===q.revision){status.textContent=ack.accepted?'Setting applied':ack.error;settingsPending=false;syncSettingValues(ack);return;}
    }
    status.textContent='Waiting for the native setting';
   }catch(e){status.textContent='Setting connection interrupted';}finally{settingsPending=false;}
  };
  for(const[name,label,min,max]of[['fov','Field of view',50,110],['hour','Daylight',0,24]])if(caps[name]){
   const row=document.createElement('label');row.className='row';row.textContent=label;
   const slider=document.createElement('input');slider.type='range';slider.min=min;slider.max=max;slider.step=name==='hour'?0.25:1;slider.dataset.nativeKey=name;slider.value=p.values[name];
   slider.onchange=()=>apply({[name]:Number(slider.value)});row.append(slider);holder.append(row);
  }
  if((caps.lamps||[]).length){
   const row=document.createElement('label');row.className='row';row.textContent='Indoor lights';const master=document.createElement('input');master.type='checkbox';master.dataset.nativeMaster='true';
   master.onchange=()=>apply({lamps:Object.fromEntries(caps.lamps.map(name=>[name,master.checked]))});row.append(master);holder.append(row);
  }
  let lampHolder=holder;
  if((caps.lamps||[]).length){const details=document.createElement('details');details.className='operator';const summary=document.createElement('summary');summary.textContent='Individual lights';details.append(summary);holder.append(details);lampHolder=details;}
  for(const name of caps.lamps||[]){
   const row=document.createElement('label');row.className='row';row.textContent=name.replace(/([a-z])([A-Z])/g,'$1 $2');
   const check=document.createElement('input');check.type='checkbox';check.dataset.nativeLamp=name;check.onchange=()=>apply({lamps:{[name]:check.checked}});row.append(check);lampHolder.append(row);
  }
  syncSettingValues(p);
 }catch(e){}
}
setInterval(()=>{if(permission)refreshSettings();else{document.querySelector('#nativeSettings').hidden=true;supported='';}},1500);
setInterval(ready,1000);ready();
</script></body></html>
'''.replace('%KEYS%', json.dumps(list(KEYS)))

class LiveState:
    def __init__(self, deadline, fps=8, width=960):
        self.deadline = deadline
        self.fps=fps;self.width=width;self.viewer_lock=threading.Lock()
        self.private = Path('/home/unreal/.sub01-private')
        self.session = uuid.uuid4().hex
        self.capture_lock = threading.Lock()
        self.input_lock = threading.Lock()
        self.settings_lock = threading.Lock()
        self.privacy_lock = threading.Lock()
        self.privacy_checked = 0
        self.privacy_value = None
        self.backend_privacy_value = None
        self.input = None
        self.accepted = 0
        self.frames = 0
        self.last_input = 0
        self.last_lease = time.monotonic()
        self.proc = None
        self.condition = threading.Condition()
        self.latest_frame = b''
        self.sequence = 0
        self.capture_utc = 0
        self.last_view_request = 0
        self.native_checked_at = 0
        self.native_identity = None

    def enabled(self, name):
        if time.time()>=self.deadline:return False
        identity=self.native()
        if identity is None:return False
        try:flag=json.loads((self.private/name).read_text())
        except (OSError,ValueError):return False
        allowed=isinstance(flag,dict) and flag.get('native_pid')==identity[0] and flag.get('native_start_ticks')==identity[1]
        if allowed and self.privacy() is not False:
            with self.condition:self.latest_frame=b'';self.capture_utc=0
            return False
        return allowed

    def native(self):
        if time.monotonic()-self.native_checked_at<1:return self.native_identity
        matches=[]
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                args=(p/'cmdline').read_bytes().split(b'\0')
                if args[0]!=b'/workspace/sub01-unreal/UE/Engine/Binaries/Linux/UnrealEditor-Cmd' or b'-game' not in args:continue
                status=(p/'status').read_text()
                if 'Uid:\t1001\t' not in status:continue
                ticks=int((p/'stat').read_text().rsplit(')',1)[1].split()[19])
                matches.append((int(p.name),ticks))
            except (OSError,ValueError):continue
        self.native_identity=matches[0] if len(matches)==1 else None
        self.native_checked_at=time.monotonic()
        return self.native_identity

    def privacy(self):
        # Only the canonical backend command decides privacy; no activity writes.
        with self.privacy_lock:
            if time.monotonic()-self.privacy_checked<.1:return self.privacy_value
            value=None
            try:
                token=(self.private/'operator-token').read_text().strip()
                request=urllib.request.Request('http://127.0.0.1:8820/api/home/native_command',headers={'X-Admin-Token':token})
                with urllib.request.urlopen(request,timeout=.5) as response:
                    raw=response.read(1025)
                    if len(raw)>1024:raise ValueError('Privacy response bounds')
                    document=json.loads(raw)
                    value=canonical_privacy(document)
            except (OSError,ValueError,TypeError):pass
            self.backend_privacy_value=value
            physical=None
            try:
                path=self.private/'native-view-privacy.json'
                if path.stat().st_size<=1024:physical=native_camera_privacy(json.loads(path.read_text()),self.native(),time.time())
            except (OSError,ValueError):pass
            value=combine_privacy(value,physical)
            self.privacy_value=value;self.privacy_checked=time.monotonic()
            return value

    def view_mode(self):
        if self.privacy() is not False:return None
        try:
            path=self.private/'native-view-privacy.json'
            if path.stat().st_size>1024:return None
            return native_view_mode(json.loads(path.read_text()),self.native(),time.time())
        except (OSError,ValueError):return None

    def live_activity(self):
        if self.view_mode()!='live':return None
        try:
            token=(self.private/'operator-token').read_text().strip()
            request=urllib.request.Request('http://127.0.0.1:8821/home/state',headers={'X-Admin-Token':token})
            with urllib.request.urlopen(request,timeout=.5) as response:
                raw=response.read(8193)
                if len(raw)>8192:return None
                return public_live_activity(json.loads(raw))
        except (OSError,ValueError,TypeError):return None

    def can_private_egress(self):
        if time.time()>=self.deadline or self.privacy() is not True or type(self.backend_privacy_value) is not bool:return False
        identity=self.native()
        if identity is None:return False
        try:
            flag=json.loads((self.private/'native-viewer-input-enabled').read_text())
            if not isinstance(flag,dict) or (flag.get('native_pid'),flag.get('native_start_ticks'))!=identity or flag.get('view_mode')!='manual':return False
            path=self.private/'native-view-privacy.json'
            if path.stat().st_size>1024:return False
            receipt=json.loads(path.read_text())
            return native_camera_privacy(receipt,identity,time.time()) is True and receipt.get('private_egress_ready') is True
        except (OSError,ValueError):return False

    def settings_receipt(self):
        identity=self.native()
        if not identity or time.time()>=self.deadline or self.privacy() is not False:return None
        try:
            path=self.private/'native-view-settings-receipt.json'
            if path.stat().st_size>4096:return None
            receipt=json.loads(path.read_text())
            if not isinstance(receipt,dict) or (receipt.get('native_pid'),receipt.get('native_start_ticks'))!=identity:return None
            if not isinstance(receipt.get('capabilities'),dict) or not isinstance(receipt.get('values'),dict):return None
            return receipt
        except (OSError,ValueError):return None

    def ensure_capture(self):
        with self.capture_lock:
            if self.proc and self.proc.poll() is None:return
            with self.condition:self.latest_frame=b'';self.capture_utc=0
            process=subprocess.Popen(['ffmpeg','-nostdin','-loglevel','error','-f','x11grab','-framerate',str(self.fps),'-video_size','1280x720','-i',':99.0','-vf',f'scale={self.width}:{self.width*9//16}','-filter_threads','1','-threads','1','-c:v','mjpeg','-q:v','5','-f','image2pipe','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            self.proc=process
            threading.Thread(target=self.capture,args=(process,),daemon=True).start()

    def capture(self,process):
        buffer=b''
        try:
            while self.enabled('native-viewer-capture-enabled') and time.monotonic()-self.last_view_request<10:
                block=process.stdout.read1(65536)
                if not block:break
                buffer+=block
                if len(buffer)>2*1024*1024:raise RuntimeError('Frame bounds exceeded')
                while True:
                    start=buffer.find(b'\xff\xd8');end=buffer.find(b'\xff\xd9',max(0,start))
                    if start<0 or end<0:break
                    frame=buffer[start:end+2];buffer=buffer[end+2:]
                    with self.condition:
                        self.latest_frame=frame;self.sequence+=1;self.capture_utc=time.time();self.condition.notify_all()
        finally:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill()
            with self.capture_lock:
                if self.proc is process:self.proc=None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def json(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        state = self.server.state
        if urlsplit(self.path).path=='/socket':
            self.websocket_video();return
        if self.path.split('?')[0]=='/settings':
            receipt=state.settings_receipt()
            self.json(200,receipt) if receipt else self.json(409,{'error':'Native settings unavailable'})
            return
        if self.path.split('?')[0] == '/health':
            if self.path.endswith('?hold=1') and (state.enabled('native-viewer-input-enabled') or state.can_private_egress()):state.last_lease=time.monotonic()
            self.json(200, {'transport':'live-native-X11-JPEG','session':state.session,
                           'expiresEpoch':state.deadline,'captureEnabled':state.enabled('native-viewer-capture-enabled'),
                           'inputEnabled':state.enabled('native-viewer-input-enabled'),'privacyEgressEnabled':state.can_private_egress(),
                           'framesDelivered':state.frames,'acceptedInputs':state.accepted,'nativeAlive':state.native() is not None,'nativeIdentity':state.native(),'viewMode':state.view_mode(),'activity':state.live_activity(),'privacy':state.privacy(),'captureFps':state.fps,'captureWidth':state.width})
            return
        if self.path.split('?')[0] in ('/', '/index.html'):
            data=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if urlsplit(self.path).path != '/frame.jpg':
            self.json(404, {'error':'Unknown route'});return
        if not state.enabled('native-viewer-capture-enabled'):
            self.json(409, {'error':'Native capture is locked'});return
        try:
            after=int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0])
            if after<0:raise ValueError()
        except ValueError:self.json(400,{'error':'Invalid frame sequence'});return
        state.last_view_request=time.monotonic();state.ensure_capture()
        with state.condition:
            state.condition.wait_for(lambda:state.sequence>after and bool(state.latest_frame),timeout=2)
            if not state.latest_frame or not state.enabled('native-viewer-capture-enabled'):self.json(503,{'error':'Native pixels unavailable'});return
            frame=state.latest_frame;sequence=state.sequence;captured=state.capture_utc
        self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(frame)));self.send_header('X-Native-Sequence',str(sequence));self.send_header('X-Native-Capture-Utc',str(captured));self.end_headers()
        try:self.wfile.write(frame);state.frames+=1
        except (BrokenPipeError,ConnectionResetError):pass

    def websocket_video(self):
        state=self.server.state
        if not state.enabled('native-viewer-capture-enabled'):
            self.json(409,{'error':'Native capture is locked'});return
        if self.headers.get('Upgrade','').lower()!='websocket' or 'upgrade' not in [v.strip().lower() for v in self.headers.get('Connection','').split(',')]:
            self.json(400,{'error':'Websocket upgrade required'});return
        origin=self.headers.get('Origin','')
        if origin!='https://5ldnm4vax9kelh-8888.proxy.runpod.net':
            self.json(403,{'error':'Private viewer origin required'});return
        try:
            key=self.headers.get('Sec-WebSocket-Key','')
            if len(base64.b64decode(key,validate=True))!=16 or self.headers.get('Sec-WebSocket-Version')!='13':raise ValueError()
        except ValueError:self.json(400,{'error':'Invalid websocket request'});return
        if not state.viewer_lock.acquire(blocking=False):
            self.json(409,{'error':'One private viewer is already connected'});return
        ended=threading.Event();writing=threading.Lock()
        def send(opcode,payload):
            size=len(payload)
            header=bytes([0x80|opcode])+(bytes([size]) if size<126 else bytes([126])+struct.pack('!H',size) if size<65536 else bytes([127])+struct.pack('!Q',size))
            with writing:self.wfile.write(header+payload);self.wfile.flush()
        def controls():
            try:
                while not ended.is_set():
                    head=self.rfile.read(2)
                    if len(head)!=2:break
                    opcode=head[0]&15;size=head[1]&127
                    if not head[0]&128 or not head[1]&128 or size>125:break
                    mask=self.rfile.read(4);raw=self.rfile.read(size)
                    if len(mask)!=4 or len(raw)!=size:break
                    data=bytes(b^mask[i%4] for i,b in enumerate(raw))
                    if opcode==8:send(8,b'');break
                    if opcode==9:send(10,data)
                    elif opcode!=10:break
            except (OSError,ConnectionResetError):pass
            finally:ended.set()
        try:
            self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade')
            self.send_header('Sec-WebSocket-Accept',base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode());self.end_headers();self.wfile.flush()
            threading.Thread(target=controls,daemon=True).start();sequence=state.sequence
            while not ended.is_set() and state.enabled('native-viewer-capture-enabled'):
                state.last_view_request=time.monotonic();state.ensure_capture()
                with state.condition:
                    state.condition.wait_for(lambda:state.sequence>sequence or ended.is_set(),timeout=1)
                    if not state.latest_frame or state.sequence<=sequence:continue
                    frame=state.latest_frame;sequence=state.sequence;captured=state.capture_utc
                if not state.enabled('native-viewer-capture-enabled'):break
                send(2,struct.pack('!Qd',sequence,captured)+frame);state.frames+=1
        except (OSError,BrokenPipeError,ConnectionResetError):pass
        finally:
            ended.set();state.viewer_lock.release();self.close_connection=True


    def do_POST(self):
        state=self.server.state
        if self.path.split('?')[0]=='/settings':
            self.post_settings();return
        if self.path.split('?')[0]!='/input':self.json(404,{'error':'Unknown route'});return
        if not state.enabled('native-viewer-input-enabled') and not state.can_private_egress():self.json(409,{'error':'Native input is locked'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024:raise ValueError('Input size exceeded')
            event=validate_input(json.loads(self.rfile.read(length)))
            with state.input_lock:
                if not state.enabled('native-viewer-input-enabled') and not (state.can_private_egress() and private_egress_event(event)):
                    self.json(409,{'error':'Private movement only; devices and settings remain locked'});return
                if event['action']!='release' and event.get('down',True) and time.monotonic()-state.last_input<.005:self.json(429,{'error':'Input rate exceeded'});return
                if state.input is None:state.input=PhysicalInput()
                state.input.send(event);state.last_input=time.monotonic();state.last_lease=state.last_input;state.accepted+=1
                self.json(200,{'acceptedInputs':state.accepted,'physicalDelivery':'XTest','session':state.session})
        except (ValueError,TypeError,json.JSONDecodeError):self.json(400,{'error':'Unsupported input'})
        except Exception:self.json(503,{'error':'Native input unavailable'})

    def post_settings(self):
        state=self.server.state
        if not state.enabled('native-viewer-input-enabled'):
            self.json(409,{'error':'Native controls are locked'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024:raise ValueError('Settings size exceeded')
            request=json.loads(self.rfile.read(length))
            with state.settings_lock:
                receipt=state.settings_receipt()
                if not receipt:raise ValueError('Native settings unavailable')
                settings=validate_settings(request,receipt['capabilities'])
                path=state.private/'native-control.json'
                existing=json.loads(path.read_text()) if path.exists() and path.stat().st_size<=4096 else {}
                revision=max(int(existing.get('revision',0)),int(receipt.get('revision',0)))+1
                if not 0<revision<2147483647 or not state.enabled('native-viewer-input-enabled'):raise ValueError('Native control changed')
                # Previous replay, routing or capture commands are not resubmitted.
                temp=state.private/'native-viewer-settings-control.tmp'
                temp.write_text(json.dumps({'revision':revision,'viewSettings':settings}));temp.chmod(0o600);temp.replace(path)
                self.json(202,{'revision':revision,'pending':True})
        except (ValueError,TypeError,OSError):self.json(400,{'error':'View settings refused'})

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--deadline-epoch',type=int,required=True);parser.add_argument('--capture-fps',type=int,choices=[8,15,24,30],default=8);parser.add_argument('--capture-width',type=int,choices=[960,1280],default=960);args=parser.parse_args()
    if os.getuid()!=1001 or time.time()>=args.deadline_epoch:raise SystemExit('Authorized nonroot runtime required')
    os.environ['DISPLAY']=':99';os.environ['XAUTHORITY']='/home/unreal/.sub01-private/native-xauthority'
    server=ThreadingHTTPServer(('127.0.0.1',8892),Handler);server.daemon_threads=True;server.state=LiveState(args.deadline_epoch,args.capture_fps,args.capture_width)
    def stop(*_):
        if server.state.proc:server.state.proc.terminate()
        if server.state.input:
            with server.state.input_lock:server.state.input.send({'action':'release'})
        threading.Thread(target=server.shutdown,daemon=True).start()
    def release_expired_input():
        while time.time()<args.deadline_epoch:
            time.sleep(.5)
            if server.state.input and (time.monotonic()-server.state.last_lease>5 or not (server.state.enabled('native-viewer-input-enabled') or server.state.can_private_egress())):
                with server.state.input_lock:server.state.input.send({'action':'release'})
    threading.Thread(target=release_expired_input,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    timer=threading.Timer(max(0,args.deadline_epoch-time.time()),stop);timer.daemon=True;timer.start()
    print('PRIVATE_NATIVE_HTTP_VIEWER_LOOPBACK_8892',args.deadline_epoch,flush=True);server.serve_forever();server.server_close()

if __name__=='__main__':main()
