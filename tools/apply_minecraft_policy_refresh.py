"""Exact guarded backend-only graceful refresh after verified world/guest saves."""
import datetime,hashlib,json,os,signal,socket,stat,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path('/workspace/sub01-home-private');BACKEND=Path('/home/unreal/sub01-backend');SNAP=ROOT/'minecraft-policy-refresh-20261015T202040Z';PRIVATE=Path('/home/unreal/.sub01-private');pre=json.loads((SNAP/'preflight.json').read_text());assert os.getuid()==1001 and pre['restart_preconditions_verified']
NEW=Path('/home/unreal/runtime-tools/home_minecraft_input.promoted.py');OLD='d52edeaaedeae5d597731532f5b40a3af62334dd4f067545e2d882930013b386';EXPECTED_NEW='dcdd6475befb566f421ee4f4f26b03c03a6ae3d8d7ce8c507e1dbecb2becb3b5'
report={'schema':'sub01.exact-minecraft-policy-rollout.v1','snapshot_directory':str(SNAP),'game_or_pod_restarted':False,'pc_guest_restarted':False,'started_epoch':time.time()}
def running(pid,start):
 try:
  p=Path('/proc')/str(pid);v=(p/'stat').read_text().rsplit(')',1)[1].split();return int(v[19])==start and v[0]!='Z'and int((p/'status').read_text().split('Uid:')[1].split()[0])==1001
 except(OSError,ValueError,IndexError):return False
def window():
 p=Path('/run/sub01-home-private/runtime-window.json');s=p.stat();d=json.loads(p.read_text());assert s.st_uid==0 and not s.st_mode&0o022 and d['pod']=='dgtgepkz7h1zy5'and d['stop_guards_authenticated']and time.time()<d['deadline_epoch']-180;return d
try:
 w=window();assert running(193148,978377926)and running(62755,975065256)and running(62757,975065274)and running(158534,976752252)
 focus=json.loads((PRIVATE/'native-tv-focus.json').read_text());assert focus.get('focused')is False
 # All controls remain released; preserve exactly the old service environment.
 state=json.load(urllib.request.urlopen('http://127.0.0.1:8820/api/home',timeout=3));assert not state['minecraft']['active']
 env=dict(v.split(b'=',1)for v in Path('/proc/158534/environ').read_bytes().split(b'\0')if b'='in v);argv=[v.decode()for v in Path('/proc/158534/cmdline').read_bytes().split(b'\0')if v];assert argv[1]=='live_server.py'and argv[argv.index('--port')+1]=='8820'
 policy=BACKEND/'home_minecraft_input.py';assert hashlib.sha256(policy.read_bytes()).hexdigest()==OLD;assert hashlib.sha256(NEW.read_bytes()).hexdigest()==EXPECTED_NEW
 # Install only the policy source; preserve its exact previous private backup.
 temporary=policy.with_suffix('.py.promoted.tmp');temporary.write_bytes(NEW.read_bytes());temporary.chmod(0o600);os.replace(temporary,policy)
 report['policy_before_sha256']=OLD;report['policy_after_sha256']=EXPECTED_NEW
 os.kill(158534,signal.SIGTERM)
 for _ in range(450):
  if not any(running(pid,ticks)for pid,ticks in [(158534,976752252),(158535,976752327),(158580,976753319)]):break
  time.sleep(.1)
 else:raise RuntimeError('Old backend/world failed graceful close; no replacement launched')
 assert running(193148,978377926)and running(62755,975065256)and running(62757,975065274)
 # No second listener/server can be started, even if an unrelated process appears.
 for port in [8820,25569,8803]:
  with socket.socket()as s:assert s.connect_ex(('127.0.0.1',port))!=0,('Old listener still present',port)
 serverlog=ROOT/'backend-state/minecraft/server.log';tail=serverlog.read_text(errors='replace')[-7000:];assert 'All dimensions are saved'in tail or 'Saved the game'in tail;report['graceful_minecraft_save_log_tail']=tail[-3000:]
 # Restore the private simulation's current saved local minute, not the old15:00 launch seed.
 saved=json.loads((ROOT/'backend-state/state.json').read_text());epoch=saved['engine']['t'];assert isinstance(epoch,(int,float))and epoch>0;resume=datetime.datetime.fromtimestamp(epoch,datetime.timezone(datetime.timedelta(hours=9))).strftime('%H:%M');argv[argv.index('--start')+1]=resume;report['clock_resume_start_HHMM']=resume
 w=window();remaining=int(w['deadline_epoch']-time.time())-35;assert remaining>120
 log=PRIVATE/'minecraft-policy-refresh-backend.log';stream=log.open('ab',buffering=0);process=subprocess.Popen(['/usr/bin/timeout','--signal=TERM','--kill-after=10',str(remaining),*argv],cwd=BACKEND,env=env,stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True);stream.close();report['timeout_pid']=process.pid
 newpid=None
 for _ in range(400):
  if process.poll()is not None:raise RuntimeError('Replacement backend exited; inspect private log')
  try:
   children=(Path('/proc')/str(process.pid)/'task'/str(process.pid)/'children').read_text().split()
   for child in children:
    p=Path('/proc')/child;a=(p/'cmdline').read_bytes().split(b'\0')
    if b'live_server.py'in a:newpid=int(child);report['backend_pid']=newpid;report['backend_start_ticks']=int((p/'stat').read_text().rsplit(')',1)[1].split()[19])
   result=json.load(urllib.request.urlopen('http://127.0.0.1:8820/api/home',timeout=.5))
   if newpid and result.get('minecraft',{}).get('has_frame'):
    report['minecraft_after']=result['minecraft'];break
  except (OSError,ValueError,TimeoutError):pass
  time.sleep(.1)
 else:raise RuntimeError('Backend did not restore an actual Minecraft bootstrap frame within40seconds')
 assert running(193148,978377926)and running(62755,975065256)and running(62757,975065274)
 actual_env=dict(v.split(b'=',1)for v in Path('/proc',str(newpid),'environ').read_bytes().split(b'\0')if b'='in v);assert actual_env==env;report['service_environment_restored_exact']=True
 report['origins_unchanged']={'backend':'http://127.0.0.1:8820','PC':'http://127.0.0.1:8811','minecraft_server':'127.0.0.1:25569','minecraft_viewer':'http://127.0.0.1:8803'};report['game_identity_unchanged']={'pid':193148,'start_ticks':978377926};report['PC_identity_unchanged']={'runner_pid':62755,'vm_pid':62757};report['status']='backend-refreshed-awaiting-root-manual-QA';report['automated_input_sent']=False;report['finished_epoch']=time.time()
except Exception as error:
 report['status']='failed-no-automatic-retry';report['error_type']=type(error).__name__;report['error']=str(error)[:300];raise
finally:
 path=SNAP/'rollout.json';path.write_text(json.dumps(report,indent=2));path.chmod(0o600);print(json.dumps({k:report[k]for k in ['status','backend_pid','backend_start_ticks','clock_resume_start_HHMM','error_type','error']if k in report}),flush=True)
