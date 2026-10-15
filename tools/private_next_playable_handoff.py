"""One reversible private Game handoff; backend processes and warm Editor stay.

Requires a completely verified independent playable-copy receipt. Credentials
and prior state remain only in the private mode0700 rollback directory.
"""
from pathlib import Path
import hashlib,json,os,signal,shutil,subprocess,time,urllib.request,struct,ast
PRIVATE=Path('/home/unreal/.sub01-private');OLD=Path('/workspace/sub01-private-playable-14acd9d355c6/Sub01HomeLab');OLDPID=193148;OLDSTART=978377926
ENGINE=Path('/workspace/sub01-private-recovered-engine/Engine/Binaries/Linux/UnrealEditor-Cmd')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def proc(pid):
 p=Path('/proc',str(pid));s=(p/'stat').read_text().rsplit(')',1)[1].split();return int(s[19]),s[0],(p/'cmdline').read_bytes().split(b'\0')
def matching(project):
 rows=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   start,state,args=proc(int(p.name))
   if state!='Z'and args[0]==str(ENGINE).encode()and str(project/'Sub01HomeLab.uproject').encode()in args and b'-game'in args and p.stat().st_uid==1001:rows.append((int(p.name),start))
  except OSError:pass
 return rows

def atomic(path,data,uid=1001):
 tmp=path.with_name(path.name+'.promotion-pending');tmp.write_bytes(data);os.chown(tmp,uid,uid);tmp.chmod(0o600);os.replace(tmp,path)
def complete_frame(path,after):
 try:
  b=Path(path).read_bytes();return Path(path).stat().st_mtime>=after and len(b)>100 and b[:8]==b'\x89PNG\r\n\x1a\n'and struct.unpack('>II',b[16:24])==(1280,720)and b[-12:]==b'\0\0\0\0IEND\xaeB`\x82'
 except OSError:return False
def fresh(pid,start):
 try:
  d=json.loads((PRIVATE/'native-view-privacy.json').read_text());return d if(d.get('native_pid'),d.get('native_start_ticks'))==(pid,start)and -.25<=time.time()-d.get('captured_utc',0)<=1 and d.get('physical_camera_private')is False and d.get('view_mode')=='manual'else None
 except(OSError,ValueError):return None

def consumer_policy_constants(text):
 values={}
 for node in ast.parse(text).body:
  if not isinstance(node,ast.Assign):continue
  for target in node.targets:
   if isinstance(target,ast.Name)and target.id in ('PROJECT','NATIVE_PID','NATIVE_START_TICKS'):
    assert target.id not in values,'Duplicate consumer policy identity'
    values[target.id]=ast.literal_eval(node.value)
 assert set(values)=={'PROJECT','NATIVE_PID','NATIVE_START_TICKS'}
 assert isinstance(values['PROJECT'],str)and type(values['NATIVE_PID'])is int and type(values['NATIVE_START_TICKS'])is int
 return values

def assert_minecraft_consumer_policy(project,pid,start,rollout_path):
 """Read-only independent consumer check; viewer grants alone are insufficient."""
 policy=Path('/home/unreal/sub01-backend/home_minecraft_input.py');values=consumer_policy_constants(policy.read_text())
 assert values=={'PROJECT':str(Path(project)/'Sub01HomeLab.uproject'),'NATIVE_PID':pid,'NATIVE_START_TICKS':start},'Minecraft consumer requires exact fresh Game policy refresh'
 rollout=json.loads(Path(rollout_path).read_text());assert rollout['schema']=='sub01.exact-minecraft-policy-rollout.v1'and rollout['policy_after_sha256']==sha(policy)
 assert rollout['game_identity_unchanged']=={'pid':pid,'start_ticks':start}
 backend=rollout['backend_pid'];assert proc(backend)[0]==rollout['backend_start_ticks']and proc(backend)[1]!='Z','Policy rollout must belong to current actual backend'
 boot=next(int(line.split()[1])for line in Path('/proc/stat').read_text().splitlines()if line.startswith('btime '));backend_epoch=boot+rollout['backend_start_ticks']/os.sysconf('SC_CLK_TCK')
 assert policy.stat().st_mtime<=backend_epoch+1 and rollout['started_epoch']<=backend_epoch+1<=rollout['finished_epoch']+2,'Backend must start after this installed policy, not use an older cached module'
 assert proc(pid)[0]==start and b'-game'in proc(pid)[2]and str(Path(project)/'Sub01HomeLab.uproject').encode()in proc(pid)[2]
 return {'exact_consumer_project_pid_start_verified':True,'backend_pid':backend,'backend_start_ticks':rollout['backend_start_ticks'],'policy_sha256':rollout['policy_after_sha256'],'backend_started_after_policy_install':True,'functional_input_frame_QA_still_required':True}

def run(target):
 from launch_private_persistent_editor import verified_window
 from private_home_candidate_scope import trusted_json
 target=Path(target).resolve();w=verified_window(Path('/run/sub01-home-private/runtime-window.json'));approval=trusted_json(Path('/run/sub01-home-private/promotion-approved.json'));copy=json.loads((target/'private-audit/playable-copy.json').read_text());assert approval.get('execute_handoff')is True and approval.get('playable_project')==str(target)and approval.get('old_game_identity')==[OLDPID,OLDSTART];assert target==Path(copy['playable_project'])and copy['map_sha256']==approval['map_sha256']and copy['module_sha256']==approval['module_sha256']and copy['all_file_hashes_verified']and copy['independent_writable_copies'];assert matching(OLD)==[(OLDPID,OLDSTART)]and not matching(target)
 assert sha(target/'Content/Sub01Home/ActualHome.umap')==copy['map_sha256']and sha(target/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==copy['module_sha256'];assert sha(OLD/'Content/Sub01Home/ActualHome.umap')=='14acd9d355c66741b7ddfd17d34acbdc5f5f75f8fc71f0a708504f06ff0eeb00'and sha(OLD/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')=='e571937b708c8e860d05373f1d3de428bc22a4c547cf80ded1ef80db706ace96'
 assert target==Path('/workspace/sub01-private-playable-next-20261016/Sub01HomeLab')
 assert copy['module_sha256']=='e571937b708c8e860d05373f1d3de428bc22a4c547cf80ded1ef80db706ace96'
 assert sha(OLD/'Config/DefaultGame.ini')=='7d3ee40243d426fdc173300d812e018ebd17c589f37302b908675f6262a8218d'
 assert approval.get('fresh_pose_preserved')is True and approval.get('source_e571_and_approved_live_hands_preserved')is True
 # Independent copied revision integrity is rechecked before the sole Game exits.
 for row in copy['files']:assert sha(target/row['path'])==row['sha256'],row['path']
 oldproc=Path('/proc',str(OLDPID));args=[x.decode()for x in(oldproc/'cmdline').read_bytes().split(b'\0')if x];assert args[0]==str(ENGINE)and'-game'in args and'-Sub01ManualView'in args and'-Sub01LiveHome'in args
 assert not any(x.startswith('-ExecutePythonScript=')or x in ['-Sub01ExitAfterCapture','-Sub01RouteReview']for x in args)
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/unreal','LANG':'C.UTF-8','DISPLAY':':99','SDL_VIDEODRIVER':'x11','XAUTHORITY':str(PRIVATE/'native-xauthority'),'XDG_RUNTIME_DIR':str(PRIVATE/'xdg-runtime'),'SUB01_HOME_ORIGIN':'http://127.0.0.1:8821','SUB01_PC_ORIGIN':'http://127.0.0.1:8811','SUB01_ADMIN_TOKEN':(PRIVATE/'operator-token').read_text().strip(),'SUB01_KITCHEN_RUNTIME':'1','OMP_NUM_THREADS':'6','OPENBLAS_NUM_THREADS':'1'}
 # Exact previously verified normal-game launcher recipe. Container root lacks
 # CAP_SYS_PTRACE for another UID's /proc/environ; no protected environment read
 # is needed or attempted. Current literal argv/UID/affinity are still verified.
 assert env.get('DISPLAY')==':99'and env.get('SUB01_HOME_ORIGIN')=='http://127.0.0.1:8821'and env.get('SUB01_PC_ORIGIN')=='http://127.0.0.1:8811';cpus=sorted(os.sched_getaffinity(OLDPID));backup=PRIVATE/('playable-promotion-rollback-'+str(time.time_ns()));backup.mkdir(mode=0o700);metadata={'schema':'sub01.private-playable-promotion.v1','started_epoch':time.time(),'old_pid':OLDPID,'old_start':OLDSTART,'old_project':str(OLD),'new_project':str(target),'map_sha256':copy['map_sha256'],'module_sha256':copy['module_sha256'],'backup':str(backup),'status':'prepared','environment_source':'verified normal-game launcher recipe; no proc environ access','backend_restarted':False,'pod_restarted':False,'public_changes':False}
 for name in ['native-viewer-capture-enabled','native-viewer-input-enabled','native-control.json','native-view-privacy.json','native-view-settings-receipt.json','native-visual-metrics.json','native-device-state.json','native-tv-focus.json']:
  p=PRIVATE/name
  if p.is_file():shutil.copy2(p,backup/name);(backup/name).chmod(0o600)
 (backup/'prior-process-private.json').write_text(json.dumps({'args':args,'environment':env,'cpus':cpus},indent=2));(backup/'prior-process-private.json').chmod(0o600)
 def persist():atomic(PRIVATE/'playable-promotion-result.json',json.dumps(metadata,indent=2).encode(),0)
 def launch(project,label):
  newargs=[str(project/'Sub01HomeLab.uproject')if x==str(OLD/'Sub01HomeLab.uproject')else x for x in args]
  newargs=[('-Sub01CapturePath='+str(project/'evidence'/('promotion-first-'+label+'.png')))if x.startswith('-Sub01CapturePath=')else x for x in newargs];(project/'evidence').mkdir(exist_ok=True)
  control=json.loads((backup/'native-control.json').read_text())if(backup/'native-control.json').exists()else{};atomic(PRIVATE/'native-control.json',json.dumps({'revision':max(1,int(control.get('revision',0))+1),'mode':'manual'}).encode())
  logfile=PRIVATE/('playable-promotion-'+label+'-'+str(time.time_ns())+'.log');stream=logfile.open('wb',buffering=0);command=['/usr/sbin/runuser','-u','unreal','--','timeout','--kill-after=10',str(max(1,int(w['deadline_epoch']-time.time()))),'taskset','-c',','.join(map(str,cpus)),*newargs];child=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,start_new_session=True);return child,str(logfile)
 def grants(pid,start):
  key=(PRIVATE/'operator-token').read_text().strip();request=urllib.request.Request('http://127.0.0.1:8820/api/home/native_command',headers={'X-Admin-Token':key})
  with urllib.request.urlopen(request,timeout=5)as response:d=json.load(response)
  assert d.get('privacy')is False and fresh(pid,start)
  for name in ['native-viewer-capture-enabled','native-viewer-input-enabled']:
   value={'native_pid':pid,'native_start_ticks':start,'purpose':'owner-authorized-private-playable-QA','accepted_game_pixels':True}
   if name.endswith('input-enabled'):value['view_mode']='manual'
   atomic(PRIVATE/name,json.dumps(value).encode())
 def wait(project,limit=660):
  until=time.time()+min(limit,max(1,w['deadline_epoch']-time.time()-600))
  while time.time()<until:
   rows=matching(project)
   if len(rows)==1 and fresh(*rows[0]):return rows[0]
   if len(rows)>1:raise RuntimeError('More than one exact private Game; grants stay disabled')
   time.sleep(.5)
  raise RuntimeError('Actual private Game did not publish fresh physical privacy/manual state')
 def device_phase(phase,*values):
  # Existing UID1001 service and guest preflight recipes require that owner.
  # JSON result is kept private; no operator token or environment is printed.
  phase_code=('import json;from next_game_device_policy_refresh import '+phase+';print("SUB01_PHASE_RESULT="+json.dumps('+phase+'('+','.join(repr(v)for v in values)+')))')
  result=subprocess.run(['/usr/sbin/runuser','-u','unreal','--','/usr/bin/python3','-c',phase_code],cwd='/home/unreal/runtime-tools',capture_output=True,text=True,timeout=180)
  private_log=backup/(phase+'.log');private_log.write_text(result.stdout+'\n'+result.stderr);private_log.chmod(0o600)
  if result.returncode:raise RuntimeError('Private '+phase+' failed; inspect '+str(private_log))
  rows=[line.split('=',1)[1]for line in result.stdout.splitlines()if line.startswith('SUB01_PHASE_RESULT=')]
  assert len(rows)==1,'Missing unique device-phase result';return json.loads(rows[0])
 persist()
 try:
  # A root-owned approval is scoped to an independently reviewed map and an
  # inactive human tour. Recheck immediately before withdrawing input grants.
  idle=json.loads((PRIVATE/'native-visual-metrics.json').read_text())
  assert(idle['native_pid'],idle['native_start_ticks'])==(OLDPID,OLDSTART)and time.time()-idle['captured_utc']<2 and idle['actual_speed_cm_s']<.01
  assert fresh(OLDPID,OLDSTART),'No current public manual physical view'
  def viewer_state():
   with urllib.request.urlopen('http://127.0.0.1:8892/health',timeout=3)as response:return json.load(response)
  viewer_before=viewer_state();assert viewer_before.get('nativeAlive')and viewer_before.get('inputEnabled')and viewer_before.get('captureEnabled')and viewer_before.get('privacy')is False and viewer_before.get('viewMode')=='manual'
  assert type(viewer_before.get('acceptedInputs'))is int
  assert viewer_before['acceptedInputs']==approval['pose_accepted_inputs'],'Human moved since pose readback: refresh exact pose before handoff'
  snapshot=device_phase('preflight_before_handoff')
  viewer_after=viewer_state();assert viewer_after.get('acceptedInputs')==viewer_before['acceptedInputs'],'Human input arrived: preserve original Game and do not hand off'
  assert fresh(OLDPID,OLDSTART)
  metadata['device_snapshot_directory']=snapshot;metadata['accepted_inputs_unchanged_during_saves']=viewer_before['acceptedInputs'];persist()
  (PRIVATE/'native-viewer-input-enabled').unlink(missing_ok=True);(PRIVATE/'native-viewer-capture-enabled').unlink(missing_ok=True);time.sleep(1.2)
  assert viewer_state().get('acceptedInputs')==viewer_before['acceptedInputs'],'Last human input arrived while grants were closing: preserve old Game'
  stopped_metrics=json.loads((PRIVATE/'native-visual-metrics.json').read_text());assert time.time()-stopped_metrics['captured_utc']<2 and stopped_metrics['actual_speed_cm_s']<.01
  assert proc(OLDPID)[0]==OLDSTART;os.kill(OLDPID,signal.SIGTERM);until=time.time()+45
  while time.time()<until:
   try:
    if proc(OLDPID)[1]=='Z':break
   except FileNotFoundError:break
   time.sleep(.2)
  else:raise RuntimeError('Old Game did not exit; do not launch another renderer')
  assert not matching(OLD);child,log=launch(target,'new');metadata.update(status='warming',new_wrapper_pid=child.pid,new_log=log);persist();pid,start=wait(target);first_frame=target/'evidence/promotion-first-new.png';until=time.time()+90
  while time.time()<until and not complete_frame(first_frame,metadata['started_epoch']):time.sleep(.25)
  if not complete_frame(first_frame,metadata['started_epoch']):raise RuntimeError('Actual newGame first1280x720PNG was not completed; grants remain disabled')
  metadata.update(first_frame=str(first_frame),first_frame_sha256=sha(first_frame),first_frame_png_verified=True);metadata.update(new_pid=pid,new_start=start,status='fresh-physical-manual-ready',grants_refreshed=False);persist();rollout=device_phase('apply_after_launch',snapshot,pid,start);metadata['backend_restarted']=True;metadata['minecraft_consumer_policy']=assert_minecraft_consumer_policy(target,pid,start,Path(snapshot)/'rollout.json');persist();grants(pid,start);metadata.update(status='promoted-private-awaiting-functional-QA',grants_refreshed=True,finished_epoch=time.time(),devices_operational=False)
  # A fresh renderer identity also invalidates backend TV consumer policy. Do
  # not claim device operation from privacy/viewer grants or reset the world.
  rollouts=sorted(Path('/workspace/sub01-home-private').glob('minecraft-policy-refresh-*/rollout.json'))
  try:
   assert rollouts,'No actual backend consumer policy rollout proof'
   metadata['minecraft_consumer_policy']=assert_minecraft_consumer_policy(target,pid,start,rollouts[-1])
  except Exception as policy_error:
   metadata['minecraft_consumer_policy']={'exact_consumer_project_pid_start_verified':False,'required_action':'refresh exact backend consumer policy before device QA','reason':str(policy_error),'functional_input_frame_QA_still_required':True}
  persist();print(json.dumps({k:v for k,v in metadata.items()if k not in ['backup']}),flush=True)
 except Exception as error:
  metadata.update(status='rollback',error=str(error));persist();(PRIVATE/'native-viewer-input-enabled').unlink(missing_ok=True);(PRIVATE/'native-viewer-capture-enabled').unlink(missing_ok=True)
  if metadata.get('backend_restarted'):
   metadata.update(status='new-game-preserved-grants-disabled-after-policy-refresh');persist();raise
  policy_values=consumer_policy_constants(Path('/home/unreal/sub01-backend/home_minecraft_input.py').read_text())
  if policy_values['PROJECT']!=str(OLD/'Sub01HomeLab.uproject'):
   metadata.update(status='new-game-preserved-policy-changed-inspect-private-log');persist();raise
  for pid,start in matching(target):
   assert proc(pid)[0]==start;os.kill(pid,signal.SIGTERM)
  until=time.time()+45
  while matching(target)and time.time()<until:time.sleep(.2)
  if matching(target):raise RuntimeError('New Game still exiting; keep grants disabled instead of launching duplicates')from error
  if not matching(OLD):child,log=launch(OLD,'rollback');metadata.update(rollback_wrapper_pid=child.pid,rollback_log=log)
  pid,start=wait(OLD)
  if(pid,start)==(OLDPID,OLDSTART):
   grants(pid,start);metadata.update(status='original-game-preserved-after-preflight-refusal',rollback_pid=pid,rollback_start=start,finished_epoch=time.time())
  else:
   # Relaunching the old project creates a NEW identity. Its backend consumer
   # remains bound to the departed old PID until an exact refresh is verified.
   metadata.update(status='rolled-back-renderer-awaiting-exact-device-policy',rollback_pid=pid,rollback_start=start,devices_operational=False,grants_refreshed=False,finished_epoch=time.time(),required_action='Refresh exact rollback PID/start in backend before enabling grants or claiming devices')
  persist();raise
if __name__=='__main__':
 import sys
 if len(sys.argv)!=2:raise SystemExit('Expected exact independently verified playable project path')
 run(sys.argv[1])
