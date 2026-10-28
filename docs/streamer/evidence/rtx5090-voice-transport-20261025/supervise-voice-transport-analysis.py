"""Independent 30s supervisor; only a newly created worker and descendants."""
import ctypes,hashlib,json,os,signal,subprocess,time
from pathlib import Path
START=time.monotonic();END=START+300
signal.signal(signal.SIGALRM,lambda *_:os._exit(124));signal.setitimer(signal.ITIMER_REAL,max(.001,END-time.monotonic()))
S=Path('/tmp/sub01-share');WORKER=S/'analyse-voice-transport-v8.py'
if ctypes.CDLL(None).prctl(36,1,0,0,0)!=0:raise SystemExit('Subreaper unavailable')
manifest=json.loads((S/'voice-transport-analysis-manifest.json').read_text())
for path,key in ((WORKER,'runner_sha256'),(Path(__file__),'supervisor_sha256')):
 if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest[key]:raise SystemExit('Source hash mismatch')
# Hard exit even if /proc or filesystem stalls; no ordinary output at deadline.
owned={};fds={}
def stat(pid):
 try:
  fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
  return (int(fields[19]),int(fields[1]),fields[0])
 except (FileNotFoundError,ProcessLookupError):return None
def pin(pid,tick):
 try:fd=os.pidfd_open(pid,0)
 except ProcessLookupError:return False
 x=stat(pid)
 if not x or x[0]!=tick:os.close(fd);return False
 owned[pid]=tick;fds[pid]=fd;return True
def discover():
 rows={int(p.name):stat(int(p.name)) for p in Path('/proc').iterdir() if p.name.isdigit()}
 more=True
 while more:
  more=False
  for pid,x in rows.items():
   if not x or pid in owned:continue
   parent=rows.get(x[1])
   descendant=x[1] in owned and parent and parent[0]==owned[x[1]]
   adopted=x[1]==os.getpid() and x[0]>=worker_ticks
   if descendant or adopted:
    more=pin(pid,x[0]) or more
 # Once pinned, pidfds remain valid even if the process exits or changes parent.
def live():
 return [p for p,t in owned.items() if (x:=stat(p)) and x[0]==t and x[2]!='Z']
def kill_all():
 discover()
 for p in live():
  try:signal.pidfd_send_signal(fds[p],signal.SIGKILL)
  except ProcessLookupError:pass

env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','OPENBLAS_NUM_THREADS':'4','OMP_NUM_THREADS':'4','SUB01_DIAGNOSTIC_START':str(START)}
worker=None;worker_ticks=0
try:
 worker=subprocess.Popen(['/home/unreal/voice-rt-venv/bin/python','-I',str(WORKER)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,start_new_session=True)
 x=stat(worker.pid)
 if not x:raise RuntimeError('Worker identity unavailable')
 worker_ticks=x[0]
 if not pin(worker.pid,worker_ticks):raise RuntimeError('Worker vanished before initial pin')
 # All ordinary worker activity is stopped by 26s; reserve 4s for independent cleanup.
 while time.monotonic()<START+296:
  discover()
  if worker.poll() is not None:break
  time.sleep(.01)
except BaseException:
 # Every post-launch exception reaches bounded cleanup. A vanished leader has
 # no pidfd, but adopted children remain discoverable through the subreaper.
 pass
while time.monotonic()<START+299:
 try:
  kill_all()
  while True:
   try:
    p,_=os.waitpid(-1,os.WNOHANG)
    if p==0:break
   except ChildProcessError:break
  discover()
  if not live():
   # Two distinct quiescent scans and no unreaped children are required.
   time.sleep(.01);discover()
   if not live():
    try:p,_=os.waitpid(-1,os.WNOHANG)
    except ChildProcessError:os._exit(0 if worker.returncode==0 else 1)
  time.sleep(.01)
 except BaseException:
  # Retain the independent hard alarm and retry cleanup; never report success.
  time.sleep(.01)
os._exit(125)
