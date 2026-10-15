"""One owner-authorized exact Editor recovery for the unbounded old dense proof.

Never stops the actual Game, devices, display, viewer or pod. Accepted asset
bytes and saved map are frozen independently; unaccepted ControllerWIP is kept.
"""
from pathlib import Path
import os,json,time,hashlib,subprocess,signal,shutil,sys
sys.path.insert(0,'/home/unreal/runtime-tools')
from private_home_candidate_scope import CANDIDATE,SCOPE,SOURCE,MAP_SHA,MODULE_SHA,PLAYABLE,PLAYABLE_MAP_SHA,PLAYABLE_MODULE_SHA,proc,trusted_json,sha
from launch_private_home_candidate import ENGINE,PRIVATE,user
from launch_private_persistent_editor import verified_window,verified_private_crash_preference

def filehash(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for chunk in iter(lambda:f.read(2**20),b''):h.update(chunk)
 return h.hexdigest()

def run():
 verified_window(Path('/run/sub01-home-private/runtime-window.json'));verified_private_crash_preference(ENGINE);scope=trusted_json(SCOPE)
 assert scope['editor_pid']==175718 and scope['editor_start_ticks']==977713981
 old=proc(175718);assert old[0]==977713981 and old[1]!='Z'and str(CANDIDATE/'Sub01HomeLab.uproject').encode()in old[2]and b'-game'not in old[2]and b'-nullrhi'not in old[2]
 def live():
  assert proc(193148)[0]==978377926 and proc(193148)[1]!='Z'and proc(198702)[0]==978621779
  assert sha(PLAYABLE/'Content/Sub01Home/ActualHome.umap')==PLAYABLE_MAP_SHA and sha(PLAYABLE/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==PLAYABLE_MODULE_SHA
  assert sha(SOURCE/'Content/Sub01Home/ActualHome.umap')==MAP_SHA and sha(SOURCE/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE_SHA
 live();assert json.loads((PRIVATE/'walking-warm-binding.json').read_text())['status']=='warm-bound-awaiting-private-walk-QA'
 mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';assert sha(mapfile)==PLAYABLE_MAP_SHA
 # Only058/059 are allowed incomplete: new quarantined asset import, then a
 # read-only body comparison queued behind it. No accepted scene mutation.
 pending=[]
 for request in sorted((SCOPE.parent/'candidate-requests').glob('*.json')):
  result=CANDIDATE/'private-audit'/(request.stem+'-result.json')
  if not result.exists():
   d=trusted_json(request);assert request.name in ('058-reference_controller_assets.json','059-grip_body_pose_audit.json')and d['candidate_editor_pid']==175718;pending.append(request.name)
 assert '058-reference_controller_assets.json'in pending
 root=Path('/workspace/sub01-home-private')/('candidate-dense-proof-recovery-'+str(time.time_ns()));root.mkdir(mode=0o700);shutil.copy2(mapfile,root/'ActualHome.umap');shutil.copy2(SCOPE,root/'candidate-scope-before.json')
 grants={n:sha(PRIVATE/n)for n in('native-viewer-capture-enabled','native-viewer-input-enabled')if(PRIVATE/n).is_file()};rows=[]
 for p in sorted((CANDIDATE/'Content').rglob('*')):
  if p.is_file()and '/ControllerWIP/'not in str(p):
   assert not p.is_symlink();rows.append({'path':str(p.relative_to(CANDIDATE)),'sha256':filehash(p),'bytes':p.stat().st_size})
 report={'schema':'sub01.exact-candidate-dense-proof-recovery.v1','old_editor_pid':175718,'old_editor_start_ticks':977713981,'game_pid':193148,'game_start_ticks':978377926,'backend_pid':198702,'backend_start_ticks':978621779,'accepted_map_sha256':PLAYABLE_MAP_SHA,'accepted_files':rows,'accepted_bytes':sum(x['bytes']for x in rows),'pending_unaccepted_requests':pending,'controller_wip_preserved':True,'grants_before':grants,'started_epoch':time.time(),'reason':'Owner-approved pathological old dense centroid comparator recovery; new exact tolerance-size verifier installed before relaunch'}
 (root/'preflight.json').write_text(json.dumps(report,indent=2)+'\n');print('ACCEPTED_PERSISTENT_FILES_FROZEN',len(rows),report['accepted_bytes'],flush=True)
 live();assert sha(mapfile)==PLAYABLE_MAP_SHA
 os.kill(175718,signal.SIGTERM);exited=False
 for _ in range(150):
  try:
   state=proc(175718);assert state[0]==977713981
   if state[1]=='Z':exited=True;break
  except FileNotFoundError:exited=True;break
  time.sleep(.1)
 if not exited:
  assert proc(175718)[0]==977713981 and str(CANDIDATE/'Sub01HomeLab.uproject').encode()in proc(175718)[2];os.kill(175718,signal.SIGKILL)
  for _ in range(50):
   try:
    state=proc(175718)
    if state[1]=='Z':break
    assert state[0]==977713981
   except FileNotFoundError:break
   time.sleep(.1)
  else:raise RuntimeError('Exact candidate process still present; no duplicate renderer may start')
  report['bounded_forced_candidate_exit']=True
 else:report['bounded_forced_candidate_exit']=False
 live();assert all(sha(PRIVATE/n)==v for n,v in grants.items())
 if sha(mapfile)!=PLAYABLE_MAP_SHA:shutil.copy2(root/'ActualHome.umap',mapfile);assert sha(mapfile)==PLAYABLE_MAP_SHA;report['shutdown_map_write_restored_from_exact_backup']=True
 for row in rows:assert filehash(CANDIDATE/row['path'])==row['sha256'],'Accepted persistent asset changed during interrupted proof: '+row['path']
 for name in pending:
  request=SCOPE.parent/'candidate-requests'/name;shutil.copy2(request,root/name)
  result={'schema':'sub01.private-next-home-task-result.v1','task':trusted_json(request)['task'],'editor_pid':175718,'ok':False,'interrupted_by_authorized_candidate_recovery':True,'accepted_disk_map_and_assets_preserved':True,'original_game_preserved':True,'promoted_to_live':False,'reason':report['reason'],'finished_epoch':time.time()};(CANDIDATE/'private-audit'/(request.stem+'-result.json')).write_text(json.dumps(result,indent=2)+'\n')
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/unreal','LANG':'C.UTF-8','DISPLAY':':100','XAUTHORITY':str(PRIVATE/'candidate-xauthority'),'XDG_RUNTIME_DIR':str(PRIVATE/'xdg-runtime'),'OMP_NUM_THREADS':'3','OPENBLAS_NUM_THREADS':'1'}
 args=[str(ENGINE/'Engine/Binaries/Linux/UnrealEditor'),str(CANDIDATE/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-vulkan','-NoSplash','-Unattended','-NoSound','-NoLiveCoding','-NoHotReloadFromIDE','-corelimit=3','-physicalcorelimit=3','-ExecutePythonScript=/home/unreal/runtime-tools/private_home_candidate_bootstrap.py','-ExecCmds=t.MaxFPS 1,r.VSync 0','-log','-stdout','-FullStdOutLogOutput','-Windowed','-ResX=1280','-ResY=720']
 logpath=PRIVATE/('candidate-dense-proof-recovery-'+str(time.time_ns())+'.log');log=logpath.open('wb',buffering=0);p=subprocess.Popen(args,env=env,preexec_fn=user,stdout=log,stderr=log,start_new_session=True)
 for _ in range(30):
  try:start=proc(p.pid)[0];break
  except FileNotFoundError:time.sleep(.05)
 scope.update(editor_pid=p.pid,editor_start_ticks=start,started_epoch=time.time(),prior_dense_proof_editor_pid=175718);SCOPE.write_text(json.dumps(scope,indent=2)+'\n');SCOPE.chmod(0o644)
 report.update(new_editor_pid=p.pid,new_editor_start_ticks=start,new_log=str(logpath),accepted_file_hashes_preserved=True,saved_map_preserved=True,game_backend_grants_preserved=True,game_pod_devices_restarted=False,status='candidate-relaunched-awaiting-actual-probe',finished_epoch=time.time())
 live();assert all(sha(PRIVATE/n)==v for n,v in grants.items());(root/'rollout.json').write_text(json.dumps(report,indent=2)+'\n');(PRIVATE/'candidate-dense-proof-recovery.json').write_text(json.dumps({k:v for k,v in report.items()if k!='accepted_files'},indent=2)+'\n');print('CANDIDATE_RECOVERY',json.dumps({k:v for k,v in report.items()if k!='accepted_files'}),flush=True)
if __name__=='__main__':run()
