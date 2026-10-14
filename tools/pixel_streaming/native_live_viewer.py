"""Live native X11 pixels and bounded physical input, behind authenticated Jupyter.

Run as unreal on the authorized server. This is an HTTP fallback, not WebRTC.
It never launches Unreal or moves an actor through a backend/state API.
"""
import argparse
import ctypes
import ctypes.util
import json
import os
import signal
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><title>Private live home</title>
<style>body{margin:0;background:#101319;color:#e7eaf0;font:16px system-ui}header{padding:12px 20px;display:flex;gap:20px;align-items:center}small{color:#aab4c4}img{display:block;width:min(100vw,1280px);margin:auto;cursor:crosshair}button{font:inherit;padding:8px 14px}#status{padding:12px 20px}</style></head>
<body><header><strong>Private live home</strong><small>Live view · Hand motion diagnostic</small><button id="control">Control the home</button></header>
<img id="game" alt="Live native Unreal home"><div id="status">Waiting for the native window.</div>
<script>
const game=document.querySelector('#game'), status=document.querySelector('#status');
const base=location.pathname.endsWith('/')?location.pathname:location.pathname.replace(/[^/]*$/,'');
let active=false,lastMouse=0,accepted=0,inputQueue=Promise.resolve();
function xsrf(){return document.cookie.split('; ').find(v=>v.startsWith('_xsrf='))?.split('=').slice(1).join('=')||'';}
async function deliver(event){let r=await fetch(base+'input',{method:'POST',headers:{'Content-Type':'application/json','X-XSRFToken':decodeURIComponent(xsrf())},body:JSON.stringify(event)});let p=await r.json();if(r.ok){accepted=p.acceptedInputs;status.textContent='You are controlling the home.';}else status.textContent=p.error;return p;}
function send(event){const operation=inputQueue.then(()=>deliver(event));inputQueue=operation.catch(()=>{active=false;status.textContent='The input connection was interrupted.';});return operation;}
document.querySelector('#control').onclick=async()=>{let h=await fetch(base+'health').then(r=>r.json());if(!h.inputEnabled){status.textContent='Input is locked while the first native capture completes.';return;}active=true;game.requestPointerLock();};
document.addEventListener('pointerlockchange',()=>{if(document.pointerLockElement!==game){active=false;send({action:'release'});}});
window.addEventListener('blur',()=>{active=false;send({action:'release'});});
const allowed=new Set(%KEYS%);
for(const [name,down] of [['keydown',true],['keyup',false]])document.addEventListener(name,e=>{if(!active||!allowed.has(e.code)||e.ctrlKey||e.metaKey||e.altKey)return;e.preventDefault();if(!e.repeat)send({action:'key',code:e.code,down});});
document.addEventListener('mousemove',e=>{if(!active||document.pointerLockElement!==game||performance.now()-lastMouse<50)return;lastMouse=performance.now();send({action:'mouse',dx:Math.max(-100,Math.min(100,Math.round(e.movementX))),dy:Math.max(-100,Math.min(100,Math.round(e.movementY)))});});
for(const [name,down] of [['mousedown',true],['mouseup',false]])game.addEventListener(name,e=>{if(active&&(e.button===0||e.button===2)){e.preventDefault();send({action:'button',button:e.button===0?1:3,down});}});
game.oncontextmenu=e=>e.preventDefault();
let streaming=false;async function ready(){let h=await fetch(base+'health'+(active?'?hold=1':'')).then(r=>r.json());if(h.captureEnabled&&!streaming){streaming=true;game.src=base+'stream';status.textContent='Live native window. WASD moves, mouse looks, E uses devices, Escape releases control.';}else if(!streaming)status.textContent='Waiting for the first native capture to complete.';}
setInterval(ready,1000);ready();
</script></body></html>'''.replace('%KEYS%', json.dumps(list(KEYS)))

class LiveState:
    def __init__(self, deadline):
        self.deadline = deadline
        self.private = Path('/home/unreal/.sub01-private')
        self.session = uuid.uuid4().hex
        self.capture_lock = threading.Lock()
        self.input_lock = threading.Lock()
        self.input = None
        self.accepted = 0
        self.frames = 0
        self.last_input = 0
        self.last_lease = time.monotonic()
        self.proc = None

    def enabled(self, name):
        return time.time() < self.deadline and (self.private/name).is_file()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def json(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        state = self.server.state
        if self.path.split('?')[0] == '/health':
            if self.path.endswith('?hold=1') and state.enabled('native-viewer-input-enabled'):state.last_lease=time.monotonic()
            self.json(200, {'transport':'live-native-X11-MJPEG','session':state.session,
                           'expiresEpoch':state.deadline,'captureEnabled':state.enabled('native-viewer-capture-enabled'),
                           'inputEnabled':state.enabled('native-viewer-input-enabled'),
                           'framesDelivered':state.frames,'acceptedInputs':state.accepted})
            return
        if self.path.split('?')[0] in ('/', '/index.html'):
            data=HTML.encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
        if self.path.split('?')[0] != '/stream':
            self.json(404, {'error':'Unknown route'});return
        if not state.enabled('native-viewer-capture-enabled'):
            self.json(409, {'error':'Native capture is locked'});return
        if not state.capture_lock.acquire(blocking=False):
            self.json(409, {'error':'One private live viewer is already connected'});return
        process=None
        try:
            process=subprocess.Popen(['ffmpeg','-nostdin','-loglevel','error','-f','x11grab','-framerate','8','-video_size','1280x720','-i',':99.0','-vf','scale=960:540','-filter_threads','1','-threads','1','-c:v','mjpeg','-q:v','5','-f','image2pipe','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            state.proc=process
            self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=nativeframe');self.send_header('Cache-Control','no-store');self.send_header('X-Accel-Buffering','no');self.end_headers()
            buffer=b''
            while state.enabled('native-viewer-capture-enabled'):
                block=process.stdout.read1(65536)
                if not block:break
                buffer+=block
                if len(buffer)>2*1024*1024:raise RuntimeError('Frame bounds exceeded')
                while True:
                    start=buffer.find(b'\xff\xd8');end=buffer.find(b'\xff\xd9',max(0,start))
                    if start<0 or end<0:break
                    frame=buffer[start:end+2];buffer=buffer[end+2:]
                    self.wfile.write(b'--nativeframe\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(frame)).encode()+b'\r\n\r\n'+frame+b'\r\n');self.wfile.flush();state.frames+=1
        except (BrokenPipeError,ConnectionResetError):
            pass
        finally:
            if process:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill()
            state.proc=None;state.capture_lock.release()

    def do_POST(self):
        state=self.server.state
        if self.path.split('?')[0]!='/input':self.json(404,{'error':'Unknown route'});return
        if not state.enabled('native-viewer-input-enabled'):self.json(409,{'error':'Native input is locked'});return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024:raise ValueError('Input size exceeded')
            event=validate_input(json.loads(self.rfile.read(length)))
            with state.input_lock:
                if event['action']!='release' and event.get('down',True) and time.monotonic()-state.last_input<.005:self.json(429,{'error':'Input rate exceeded'});return
                if state.input is None:state.input=PhysicalInput()
                state.input.send(event);state.last_input=time.monotonic();state.last_lease=state.last_input;state.accepted+=1
                self.json(200,{'acceptedInputs':state.accepted,'physicalDelivery':'XTest','session':state.session})
        except (ValueError,TypeError,json.JSONDecodeError):self.json(400,{'error':'Unsupported input'})
        except Exception:self.json(503,{'error':'Native input unavailable'})

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--deadline-epoch',type=int,required=True);args=parser.parse_args()
    if os.getuid()!=1001 or time.time()>=args.deadline_epoch:raise SystemExit('Authorized nonroot runtime required')
    os.environ['DISPLAY']=':99';os.environ['XAUTHORITY']='/home/unreal/.sub01-private/native-xauthority'
    server=ThreadingHTTPServer(('127.0.0.1',8892),Handler);server.daemon_threads=True;server.state=LiveState(args.deadline_epoch)
    def stop(*_):
        if server.state.proc:server.state.proc.terminate()
        if server.state.input:
            with server.state.input_lock:server.state.input.send({'action':'release'})
        threading.Thread(target=server.shutdown,daemon=True).start()
    def release_expired_input():
        while time.time()<args.deadline_epoch:
            time.sleep(.5)
            if server.state.input and time.monotonic()-server.state.last_lease>5:
                with server.state.input_lock:server.state.input.send({'action':'release'})
    threading.Thread(target=release_expired_input,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    timer=threading.Timer(max(0,args.deadline_epoch-time.time()),stop);timer.daemon=True;timer.start()
    print('PRIVATE_NATIVE_HTTP_VIEWER_LOOPBACK_8892',args.deadline_epoch,flush=True);server.serve_forever();server.server_close()

if __name__=='__main__':main()
