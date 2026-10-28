"""Finite private audio transport diagnostic. Not approved to execute until reviewed."""
from pathlib import Path
import ctypes,hashlib,json,os,signal,socket,stat,subprocess,sys,time,traceback,uuid
from contextlib import contextmanager
if not __debug__ or sys.flags.optimize or os.environ.get("PYTHONOPTIMIZE"):
 raise SystemExit("Refusing optimized interpreter mode")
import urllib.request
P=Path('/home/unreal/.sub01-private');SHARE=Path('/tmp/sub01-share')
ROOT=P/'voice-director-diagnostic-v7-20261025';BASE=ROOT/'confined';BROKER=ROOT/'broker';SOURCE=P/'latest-source-20261023/scripts'
MAIN=P/'streamer/main.mjpeg';MAINJSON=P/'streamer/main.json';STOP=P/'streamer/STOP'
LEASE=SHARE/'MEASURING';OWNER='codex-voice-director-'+uuid.uuid4().hex
WRAPPER=SHARE/'restrict-diagnostic-child-v2.py';NATIVE=(29950,53274039)
started=time.monotonic();hard_deadline=started+300;deadline=started+280;children={};identities={};errors=[];fault=[];last_guard=-10;controller_pid=os.getpid()
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN=None;lease_owned=False;voice_inode=None

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(p):
 try:return json.loads(Path(p).read_text())
 except (OSError,ValueError):return {}
def proc(pid):
 a=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
 return int(a[19]),int(a[1]),a[0],int(a[3])
def native():
 value=proc(NATIVE[0]);assert value[0]==NATIVE[1] and value[2]!='Z' and STOP.exists(),'native identity/STOP lost'
 r=read(P/'streamer-visual-receipt.json')
 assert r.get('native_pid')==NATIVE[0] and r.get('native_start_ticks')==NATIVE[1] and 0<=time.time()-r.get('captured_utc',0)<=3,'stale native receipt'
def alive(pid,ticks):
 try:
  value=proc(pid);return value[0]==ticks and value[2]!='Z'
 except (OSError,ValueError):return False
def save(path,data):Path(path).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def log(event,**data):
 with (BASE/'journal.jsonl').open('a')as f:f.write(json.dumps(dict(event=event,utc=time.time(),monotonic=time.monotonic(),**data))+'\n')
def fifo(path):
 assert path.resolve()==path and not path.is_symlink()
 s=path.stat();assert stat.S_ISFIFO(s.st_mode) and s.st_uid==1001 and stat.S_IMODE(s.st_mode)==0o600
 return s.st_dev,s.st_ino

def fifo_users(identity):
 found={}
 for d in Path('/proc').iterdir():
  if not d.name.isdigit():continue
  try:
   for fd in (d/'fd').iterdir():
    try:
     s=fd.stat()
     if (s.st_dev,s.st_ino)!=identity:continue
     flags=next(x.split()[1]for x in (d/'fdinfo'/fd.name).read_text().splitlines()if x.startswith('flags:'))
     found.setdefault(int(d.name),set()).add(int(flags,8)&3)
    except (OSError,StopIteration):continue
  except OSError:continue
 for pid,data in observe().items():
  if data.get('observation_error'):raise RuntimeError('uninspectable UID1001 process')
  modes=data.get('fifos',{}).get(str(identity[0])+':'+str(identity[1]))
  if modes:found.setdefault(int(pid),set()).update(modes)
 return found

OBSERVATIONS={};OBSERVED_AT=-10
OBSERVER=SHARE/'read-diagnostic-proc.py'
def observe(force=False):
 global OBSERVATIONS,OBSERVED_AT
 if not force and time.monotonic()-OBSERVED_AT<.5:return OBSERVATIONS
 args=['/usr/bin/python3','-I',str(OBSERVER),'--base',str(BASE)]
 for path in (MAIN,BASE/'voice/voice.pcm'):
  if path.exists():
   ident=fifo(path);args+=['--fifo',str(ident[0])+':'+str(ident[1])]
 with bounded(3):
  r=subprocess.run(args,user=1001,group=1001,extra_groups=[],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2,close_fds=True,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'})
  assert r.returncode==0 and len(r.stdout)<=2*1024**2,'observer failure'
  body=json.loads(r.stdout);assert body['uid']==1001 and 0<=time.time()-body['utc']<3
 OBSERVATIONS=body['processes'];OBSERVED_AT=time.monotonic();return OBSERVATIONS

def user_observation(pid):
 data=observe().get(str(pid),{})
 if not data:data=observe(force=True).get(str(pid),{})
 if not data or data.get('observation_error'):raise ProcessLookupError('missing UID1001 process observation')
 assert data['ticks']==proc(pid)[0],'observer identity mismatch'
 return data

def executable_id(path):
 text=str(path)
 if text.startswith('/proc/')and text.endswith('/exe'):
  return tuple(user_observation(int(text.split('/')[2]))['exe'])
 s=Path(path).stat();return s.st_dev,s.st_ino
EXPECTED_EXE={executable_id(p)for p in ('/usr/bin/ffmpeg','/usr/bin/taskset','/home/unreal/venv/bin/python','/home/unreal/voice-rt-venv/bin/python')}
FFMPEG_EXE=executable_id('/usr/bin/ffmpeg')
def descendant(pid):
 seen=set()
 while pid>1 and pid not in seen:
  if pid==controller_pid:return True
  seen.add(pid)
  try:pid=proc(pid)[1]
  except (OSError,ValueError):return False
 return False

def register(pid):
 tick,parent,state,sid=proc(pid)
 assert pid!=NATIVE[0] and tick>=controller_ticks and sid==pid and descendant(parent)
 assert Path(f'/proc/{pid}').stat().st_uid==1001
 exe=executable_id(f'/proc/{pid}/exe');assert exe in EXPECTED_EXE
 identities[pid]={'ticks':tick,'sid':sid,'exe':exe}

def owned(pid,identity):
 if not alive(pid,identity['ticks']):return False
 _,parent,_,sid=proc(pid)
 return (pid!=NATIVE[0] and sid==identity['sid'] and descendant(parent)
         and Path(f'/proc/{pid}').stat().st_uid==1001
         and executable_id(f'/proc/{pid}/exe') in EXPECTED_EXE)

def scan_owned_ffmpeg():
 # Local subreaper keeps orphaned descendants parented to this controller.
 # Session, actual executable inode, ancestry, UID and start ticks are required;
 # argv/output path is an additional scope check, never sole ownership proof.
 for d in Path('/proc').iterdir():
  if not d.name.isdigit():continue
  pid=int(d.name)
  if pid==NATIVE[0]:continue
  try:
   if d.stat().st_uid!=1001:continue
   tick,parent,state,sid=proc(pid)
   if tick<controller_ticks or sid!=pid or not descendant(parent):continue
   exe=executable_id(d/'exe')
   if exe not in EXPECTED_EXE:continue
   observation=user_observation(pid)
   if not observation['base_arg']:continue
   if exe==FFMPEG_EXE:assert observation['recording_arg']
   register(pid)
  except (OSError,ValueError):continue

def listeners():
 rows={}
 for table in ('tcp','tcp6'):
  for line in Path('/proc/net/'+table).read_text().splitlines()[1:]:
   a=line.split();port=int(a[1].split(':')[1],16)
   if port not in (8855,8856) or a[3]!='0A':continue
   assert table=='tcp' and a[1].split(':')[0]=='0100007F','non-loopback listener'
   rows[port]=a[9]
 for port,inode in rows.items():
  role='voice'if port==8855 else'director';p=children.get(role)
  assert p and p.poll()is None,'unexpected listener'
  sockets=user_observation(p.pid)['sockets']
  if inode not in sockets:
   observe(force=True);sockets=user_observation(p.pid)['sockets']
  assert inode in sockets,'listener not owned after fresh UID1001 observation'
 return rows

def guard():
 global last_guard
 native();assert time.monotonic()<deadline,'operation deadline280s (20s cleanup reserve)'
 assert read(LEASE).get('owner')==OWNER,'lease ownership changed'
 if time.monotonic()-last_guard<1:return
 last_guard=time.monotonic()
 assert os.statvfs('/').f_bavail*os.statvfs('/').f_frsize>10*1024**3,'root reserve'
 size=0
 for path in ROOT.rglob('*'):
  try:
   if path.is_file()and not path.is_symlink():size+=path.stat().st_size
  except FileNotFoundError:pass
 assert size<=512*1024**2,'artifact budget512MiB'
 listeners();scan_owned_ffmpeg()
 for role,p in list(children.items()):assert p.poll()is None,role+' exited'

def alarm_expired(signum,frame):raise TimeoutError('absolute controller/request deadline')
signal.signal(signal.SIGALRM,alarm_expired)
@contextmanager
def bounded(seconds):
 end=min(deadline,time.monotonic()+seconds)
 if end<=time.monotonic():raise TimeoutError('deadline already expired')
 signal.setitimer(signal.ITIMER_REAL,max(.001,end-time.monotonic()))
 try:yield
 finally:signal.setitimer(signal.ITIMER_REAL,max(.001,deadline-time.monotonic()))

def api(port,path,body=None,timeout=2):
 guard()
 headers={'X-Admin-Token':TOKEN}
 data=None if body is None else json.dumps(body).encode()
 if data is not None:headers['Content-Type']='application/json'
 req=urllib.request.Request(f'http://127.0.0.1:{port}'+path,data=data,headers=headers)
 with bounded(timeout):
  with HTTP.open(req,timeout=timeout)as response:
   assert response.status==200
   payload=response.read(2*1024*1024+1);assert len(payload)<=2*1024*1024,'API body bound'
   return json.loads(payload)

def wait_for(fn,seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  guard()
  try:v=fn()
  except (OSError,ValueError):v=None
  if v:return v
  time.sleep(.2)
 raise RuntimeError('bounded readiness timeout')

def newdir(path):path.mkdir(mode=0o700);os.chown(path,1001,1001)
def launch(role,python,args,port):
 cache=BASE/(role+'-cache');newdir(cache)
 for sub in ('tmp','xdg','cuda','triton','numba'):newdir(cache/sub)
 env=dict(PATH='/home/unreal/venv/bin:/usr/bin:/bin',HOME=str(cache),USER='unreal',LANG='C.UTF-8',
  PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(cache/'tmp'),XDG_CACHE_HOME=str(cache/'xdg'),CUDA_CACHE_PATH=str(cache/'cuda'),
  TRITON_CACHE_DIR=str(cache/'triton'),NUMBA_CACHE_DIR=str(cache/'numba'),HF_HOME='/home/unreal/.cache/sub01-voice-offline',
  HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',XAUTHORITY=str(P/'native-xauthority'),DISPLAY='unix:99',
  OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1')
 if role=='director':env.update(SUB01_WRITER_CONFIG=str(BROKER/'targets.json'),SUB01_WRITER_SNAPSHOT=str(BROKER/'snapshot.json'))
 cmd=['/usr/bin/taskset','-c','6-13',python,str(WRAPPER),'--directory',str(BASE),'--bind-port',str(port),'--',python,*args]
 with (BASE/(role+'.log')).open('wb')as f:p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=f,stderr=f,env=env,user=1001,group=1001,extra_groups=[],start_new_session=True,close_fds=True)
 children[role]=p;register(p.pid);log('child-start',role=role,pid=p.pid,identity=identities[p.pid])
 return p

def interrupted(signum,frame):raise KeyboardInterrupt('controller interrupted')
signal.signal(signal.SIGTERM,interrupted)

result={'schema':'sub01.voice-director-diagnostic.v1','status':'preflight','owner':OWNER,'native':NATIVE,'services_acceptance':False}
try:
 os.sched_setaffinity(0,{13});controller_ticks=proc(os.getpid())[0]
 libc=ctypes.CDLL(None,use_errno=True)
 if libc.prctl(36,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),'child subreaper')
 signal.setitimer(signal.ITIMER_REAL,max(.001,deadline-time.monotonic()))
 native();assert not LEASE.exists() and not ROOT.exists()
 assert not listeners(),'occupied diagnostic port'
 for port in (8855,8856):
  with socket.socket()as s:
   s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port))
 proof_path=SHARE/'cuda-driver-fixed-result.json'
 assert sha(proof_path)=='726476b35ee495a209c5b1f8232a236a3c8172acd60c68cbcbe63b31c9271612','CUDA evidence changed'
 proof=read(proof_path);assert proof.get('cleanup_verified') is True
 assert len(proof.get('runs',[]))==1
 run=proof['runs'][0];assert run['returncode']==0
 cuda=run['probe'];assert cuda['cuInit']==0 and cuda['cuDeviceGetCount']==0 and cuda['count']==1
 fixture=cuda['fixture'];assert fixture['all_pass'] is True
 residual=fixture['results']['residual-own-task-subtree-write'];assert residual['acknowledged'] is True and residual['comm_only'] is False
 for pid in proof['owned']:assert not Path('/proc/'+pid).exists(),'prior CUDA process remains'
 assert sha(OBSERVER)=='acbf714e8a0466aafb858544bd16e0dd1d7e22cd469984bbbe48afa028bf18ae'
 assert sha(WRAPPER)=='68710e0196159a242afdc82377a152f9dea7659dd3da38f7bee49248fb9bdf17'
 assert sha(SHARE/'voice-writer-broker.py')=='13212849f4c28a6cf09cab30e3375b7bb9c55cefd85d19be7d10b1031680dbdb'
 assert sha(SHARE/'director-with-writer-proof.py')=='b4351230e60e6df00ec9ba13666b5f2f0b1818eaf26909867bcf092745b756fe'
 assert sha(SHARE/'voice-writer-proof-validation.py')=='2bea39a3cf92ba05c9fc1fb84154521607bfd347b024e815c2e2557950eba63d'
 proof_validation=__import__('runpy').run_path(str(SHARE/'voice-writer-proof-validation.py'))
 assert sha(SOURCE/'voice_server.py')=='95758eb8fd0a4341d6e6fe1a684c1511ca0c98fc8c6f89a753f226a4f5eefce5'
 assert sha(SOURCE/'streamer_director.py')=='d7ff873b40ac390c2004c248e5aa825255bcefd49e44684a077b78d91c799b8c'
 cfgpath=P/'streamer/voice/voice.json';cfg=read(cfgpath);assert cfg['chosen']=='K07'and cfg['engine']=='chatterbox'
 assert sha(cfg['voice_prompt'])=='d8ce97537faff90e4f37044b2260157bede82775c6c97264ae523f9b775180c0'
 token_stat=(P/'operator-token').lstat();assert stat.S_ISREG(token_stat.st_mode)and token_stat.st_uid==1001 and stat.S_IMODE(token_stat.st_mode)==0o600
 TOKEN=(P/'operator-token').read_text().strip();assert len(TOKEN)>=12
 main_inode=fifo(MAIN);assert not fifo_users(main_inode),'main FIFO already has users (including writer)'
 tuning=P/'streamer-visual-face-tuning.json';tuning_before=sha(tuning)
 manifest_path=SHARE/'voice-public-model-manifest.json'
 assert sha(manifest_path)=='56b3bdca9852fb5ecc29c3489071c364271e513f68996622ee1b5af5f4de9021'
 manifest=read(manifest_path)
 for item in manifest['files'].values():assert sha(item['source'])==item['sha256'],'ROOT cache changed'
 newdir(ROOT);newdir(BASE);newdir(BROKER);newdir(BASE/'voice');newdir(BASE/'director');newdir(BASE/'director/recordings')
 result['inputs']={'controller_sha256':sha(__file__),'observer_sha256':sha(OBSERVER),'wrapper_sha256':sha(WRAPPER),'voice_source_sha256':sha(SOURCE/'voice_server.py'),'director_source_sha256':sha(SOURCE/'streamer_director.py'),'config_sha256':sha(cfgpath),'reference_sha256':sha(cfg['voice_prompt']),'cache_manifest_sha256':sha(manifest_path),'tuning_before_sha256':tuning_before,'main_inode':main_inode}
 save(BASE/'inputs.json',result['inputs'])
 fd=os.open(LEASE,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w')as f:json.dump({'owner':OWNER,'pid':os.getpid(),'ticks':controller_ticks,'started_utc':time.time(),'expires_utc':time.time()+330},f);f.flush();os.fsync(f.fileno())
 lease_owned=True
 launch('voice','/home/unreal/voice-rt-venv/bin/python',[str(SOURCE/'voice_server.py'),'--host','127.0.0.1','--port','8855','--token-file',str(P/'operator-token'),'--streamer-dir',str(BASE/'voice'),'--voice-config',str(cfgpath),'--engine','chatterbox','--fallback','none','--device','cuda','--threads','4','--offline','--keep-hours','0'],8855)
 health=wait_for(lambda:(lambda h:h if h.get('ready')is True and h.get('engine')=='chatterbox'else None)(api(8855,'/healthz')),120)
 save(BASE/'voice-ready.json',health);voice_fifo=BASE/'voice/voice.pcm';voice_inode=fifo(voice_fifo)
 targets=[{'role':'native','pid':NATIVE[0],'ticks':NATIVE[1],'fifo':list(main_inode)},{'role':'voice','pid':children['voice'].pid,'ticks':identities[children['voice'].pid]['ticks'],'fifo':list(voice_inode)}]
 assert proof_validation['targets_ok'](targets)
 save(BROKER/'targets.json',targets);os.chmod(BROKER/'targets.json',0o600);os.chown(BROKER/'targets.json',1001,1001)
 with (ROOT/'broker.log').open('wb')as output:
  broker=subprocess.Popen(['/home/unreal/venv/bin/python','-I',str(SHARE/'voice-writer-broker.py'),'--config',str(BROKER/'targets.json'),'--output',str(BROKER),'--owner-base',str(BASE)],user=1001,group=1001,extra_groups=[],env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},stdin=subprocess.DEVNULL,stdout=output,stderr=output,start_new_session=True)
 children['broker']=broker;register(broker.pid);log('child-start',role='broker',pid=broker.pid,identity=identities[broker.pid])
 launch('director','/home/unreal/venv/bin/python',[str(SHARE/'director-with-writer-proof.py'),'--host','127.0.0.1','--port','8856','--token-file',str(P/'operator-token'),'--streamer-dir',str(BASE/'director'),'--recordings-dir',str(BASE/'director/recordings'),'--voice-fifo',str(voice_fifo),'--main-fifo',str(MAIN),'--main-json',str(MAINJSON),'--ffmpeg','/usr/bin/ffmpeg','--game-source','fifo','--layout','webcam_only','--desktop-display',':99.0','--encoder','libx264','--fps','60','--preset','veryfast','--crf','23','--keep-segments','0'],8856)
 readiness_last=[-10.0]
 def ready():
  d=api(8856,'/director/state');m=d.get('main')or{}
  if time.monotonic()-readiness_last[0]>=1:
   snapshot=read(BROKER/'snapshot.json');moment=time.monotonic()
   decisions={t['role']:proof_validation['valid'](snapshot,t,moment) for t in targets}
   diagnostic={'utc':time.time(),'director':d,'voice':api(8855,'/state'),'broker_snapshot':snapshot,'broker_age':moment-snapshot.get('monotonic',0),'broker_decisions':decisions}
   with (BASE/'readiness-states.jsonl').open('a')as f:f.write(json.dumps(diagnostic)+'\n')
   readiness_last[0]=time.monotonic()
  return d if d.get('voice')is True and m.get('source')=='fifo'and m.get('fresh')is True and m.get('main_tap_ok')is True else None
 initial=wait_for(ready,45);save(BASE/'director-ready.json',initial)
 log('recording-window-start',director=initial);window=time.monotonic();sent=False;last_sample=0;last_check=0
 while time.monotonic()-window<90:
  guard();now=time.monotonic()
  if not sent and now-window>=10:
   sent=True;log('speak-request-issued')
   response=api(8855,'/speak',{'text':'Ready for the private audio transport check.','priority':'normal','max_seconds':10,'tag':'isolated-transport-diagnostic'},5)
   save(BASE/'speak-response.json',response);log('speak-request-returned',id=response.get('id'))
  if now-last_sample>=.04:
   mouth=read(BASE/'voice/mouth.json')
   with (BASE/'mouth-observations.jsonl').open('a')as f:f.write(json.dumps({'sampled_utc':time.time(),'mouth':mouth})+'\n')
   last_sample=now
  if now-last_check>=5:
   d=api(8856,'/director/state');v=api(8855,'/state');log('states',director=d,voice=v)
   assert v.get('fallback')is None and v.get('last_error')is None
   m=d.get('main')or{}
   assert d.get('run')==initial.get('run')and d.get('voice')is True and m.get('source')=='fifo'and m.get('fresh')is True,'transport source/run changed'
   assert fifo(MAIN)==main_inode and fifo(voice_fifo)==voice_inode
   for ident,expected in ((main_inode,children['director'].pid),(voice_inode,children['director'].pid)):
    readers={p for p,modes in fifo_users(ident).items()if modes&{0,2}}
    assert readers=={expected},'unexpected FIFO reader'
   writers={p for p,modes in fifo_users(voice_inode).items()if modes&{1,2}}
   assert writers<={children['voice'].pid},'unexpected PCM writer'
   last_check=now
  time.sleep(.01)
 assert sent;result.update(status='capture-ended-analysis-pending',recording_window_seconds=time.monotonic()-window)
except BaseException:
 result.update(status='failed',error=traceback.format_exc())
finally:
 deadline=hard_deadline
 signal.setitimer(signal.ITIMER_REAL,max(.001,hard_deadline-time.monotonic()))
 # Discover independently-sessioned ffmpeg children by this unique output directory.
 try:observe(force=True);scan_owned_ffmpeg()
 except BaseException as e:errors.append('ffmpeg scan: '+str(e))
 for sig,grace in ((signal.SIGTERM,8),(signal.SIGKILL,2)):
  for pid,identity in list(identities.items()):
   try:
    assert pid!=NATIVE[0]
    if owned(pid,identity):os.kill(pid,sig)
   except OSError as e:errors.append(type(e).__name__)
  until=time.monotonic()+grace
  while time.monotonic()<until and any(alive(pid,i['ticks'])for pid,i in identities.items()):
   for p in children.values():p.poll()
   time.sleep(.1)
 # Reap orphaned descendants adopted by this local subreaper.
 for pid in list(identities):
  try:os.waitpid(pid,os.WNOHANG)
  except ChildProcessError:pass
 for p in children.values():
  try:p.wait(timeout=1)
  except BaseException as e:errors.append(str(e))
 try:
  observe(force=True);scan_owned_ffmpeg();assert not any(alive(pid,i['ticks'])for pid,i in identities.items()),'owned process remains'
  native();assert sha(P/'streamer-visual-face-tuning.json')==tuning_before,'tuning changed'
  assert sha(cfgpath)==result['inputs']['config_sha256'] and sha(cfg['voice_prompt'])==result['inputs']['reference_sha256'],'voice inputs changed'
  assert not {p for p,m in fifo_users(main_inode).items()if m&{0,2}},'main reader remains'
  assert not listeners(),'listener remains after cleanup'
  for port in (8855,8856):
   with socket.socket()as s:
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port))
 except BaseException as e:errors.append('postcondition: '+str(e))
 result.update(cleanup_complete=not errors,cleanup_errors=errors,finished_utc=time.time(),watchdog_fault=fault)
 if BASE.exists():save(BASE/'result.json',result)
 save(SHARE/'voice-director-result.json',result)
 if lease_owned and not errors and read(LEASE).get('owner')==OWNER:os.rename(LEASE,BASE/'measurement-lease-completed.json')
 signal.setitimer(signal.ITIMER_REAL,0)
 print(json.dumps(result,indent=2))
