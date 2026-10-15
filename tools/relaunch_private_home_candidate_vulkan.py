"""One deliberate candidate-only RHI handoff, preserving the actual live Game."""
import hashlib,json,os,signal,subprocess,time
from pathlib import Path
import sys
sys.path.insert(0,'/home/unreal/runtime-tools')
from launch_private_home_candidate import ENGINE,PRIVATE,user
from launch_private_persistent_editor import verified_window,verified_private_crash_preference
from private_home_candidate_scope import SOURCE,CANDIDATE,MAP_SHA,MODULE_SHA,SCOPE,sha,proc,trusted_json
def run():
 window=verified_window(Path('/run/sub01-home-private/runtime-window.json'));verified_private_crash_preference(ENGINE);scope=trusted_json(SCOPE)
 assert proc(159171)[0]==976840968 and proc(159171)[1]!='Z'
 assert sha(SOURCE/'Content/Sub01Home/ActualHome.umap')==MAP_SHA and sha(SOURCE/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE_SHA
 old_pid=scope['editor_pid'];old=proc(old_pid);assert old[0]==scope['editor_start_ticks']and old[1]!='Z'and str(CANDIDATE/'Sub01HomeLab.uproject').encode()in old[2]and b'-game'not in old[2]and b'-nullrhi'in old[2]
 requests=list((SCOPE.parent/'candidate-requests').glob('*.json'))
 for request in requests:
  result=CANDIDATE/'private-audit'/(request.stem+'-result.json');assert result.is_file(),'Never interrupt an unfinished native asset transaction'
 for name in('reference-wall-console-native.json','reference-teal-bathroom-native.json','reference-bed-finish-native.json'):
  assert json.loads((CANDIDATE/'private-audit'/name).read_text()).get('saved')is True,'Reviewed candidate upgrades must actually be saved before RHI handoff'
 free=subprocess.check_output(['/usr/bin/nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip();assert int(free.splitlines()[0])>=8192,'At least8GB free GPU memory required beside the original Game'
 prior_map=sha(CANDIDATE/'Content/Sub01Home/ActualHome.umap');grants={n:sha(PRIVATE/n)for n in('native-viewer-capture-enabled','native-viewer-input-enabled')if(PRIVATE/n).is_file()}
 os.kill(old_pid,signal.SIGTERM)
 for _ in range(300):
  try:
   state=proc(old_pid)
   if state[1]=='Z':break
   assert state[0]==scope['editor_start_ticks']
  except FileNotFoundError:break
  time.sleep(.1)
 else:raise RuntimeError('Candidate orderly exit still pending; do not kill or replace the live Game')
 assert sha(CANDIDATE/'Content/Sub01Home/ActualHome.umap')==prior_map
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/unreal','LANG':'C.UTF-8','DISPLAY':':100','XAUTHORITY':str(PRIVATE/'candidate-xauthority'),'XDG_RUNTIME_DIR':str(PRIVATE/'xdg-runtime'),'OMP_NUM_THREADS':'3','OPENBLAS_NUM_THREADS':'1'}
 binary=ENGINE/'Engine/Binaries/Linux/UnrealEditor';assert binary.open('rb').read(4)==b'\x7fELF'
 args=[str(binary),str(CANDIDATE/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-vulkan','-NoSplash','-Unattended','-NoSound','-NoLiveCoding','-NoHotReloadFromIDE','-corelimit=3','-physicalcorelimit=3','-ExecutePythonScript=/home/unreal/runtime-tools/private_home_candidate_bootstrap.py','-ExecCmds=t.MaxFPS 15,r.VSync 0','-log','-stdout','-FullStdOutLogOutput','-Windowed','-ResX=1280','-ResY=720']
 log=(PRIVATE/'candidate-vulkan-editor.log').open('wb',buffering=0);p=subprocess.Popen(args,env=env,preexec_fn=user,stdout=log,stderr=log,start_new_session=True)
 for _ in range(30):
  try:start=proc(p.pid)[0];break
  except FileNotFoundError:time.sleep(.05)
 scope.update(editor_pid=p.pid,editor_start_ticks=start,nullrhi=False,started_epoch=time.time(),prior_nullrhi_editor_pid=old_pid,candidate_map_sha256_at_rhi_handoff=prior_map,allowed_tasks=sorted(set(scope['allowed_tasks']+['visual_review'])))
 SCOPE.write_text(json.dumps(scope,indent=2)+'\n');SCOPE.chmod(0o644)
 assert proc(159171)[0]==976840968 and sha(SOURCE/'Content/Sub01Home/ActualHome.umap')==MAP_SHA
 assert all(sha(PRIVATE/n)==value for n,value in grants.items())
 receipt={'schema':'sub01.candidate-only-vulkan-handoff.v1','scope':scope,'original_grants_sha256_preserved':grants,'original_game_preserved':True,'pod_restart':False,'second_game_started':False,'actual_candidate_render_verified':False}
 (PRIVATE/'candidate-vulkan-handoff.json').write_text(json.dumps(receipt,indent=2)+'\n');print('CANDIDATE_VULKAN_EDITOR_STARTED',json.dumps(scope),flush=True)
if __name__=='__main__':run()
