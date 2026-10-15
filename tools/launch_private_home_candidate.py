"""Launch only the independently copied home with NullRHI on isolated X100."""
import hashlib,json,os,stat,time,subprocess,secrets
from pathlib import Path
import sys
sys.path.insert(0,'/home/unreal/runtime-tools')
from launch_private_persistent_editor import verified_window,verified_private_crash_preference
from private_home_candidate_scope import SOURCE,CANDIDATE,MAP_SHA,MODULE_SHA,SCOPE,sha,proc
ENGINE=Path('/workspace/sub01-private-recovered-engine')
PRIVATE=Path('/home/unreal/.sub01-private')
XSERVER=PRIVATE/'candidate-xvfb/root/usr/bin/Xvfb'
def user():
 os.setgroups([]);os.setgid(1001);os.setuid(1001);os.umask(0o077);os.sched_setaffinity(0,{5,6,7})
def run():
 window=verified_window(Path('/run/sub01-home-private/runtime-window.json'));verified_private_crash_preference(ENGINE)
 assert proc(159171)[0]==976840968 and proc(159171)[1]!='Z'
 assert sha(SOURCE/'Content/Sub01Home/ActualHome.umap')==MAP_SHA and sha(SOURCE/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so')==MODULE_SHA
 copy_path=CANDIDATE/'private-audit/candidate-copy.json';copy=json.loads(copy_path.read_text());assert copy['all_writable_project_files_are_independent_copies']and copy['all_copied_file_hashes_verified']and copy['copied_bytes']<1_100_000_000
 assert XSERVER.is_file(),'Owned isolated virtual X server required'
 assert not Path('/tmp/.X11-unix/X100').exists(),'Never adopt another display';assert not SCOPE.exists(),'Never replace an existing candidate authority'
 requestdir=SCOPE.parent/'candidate-requests';requestdir.mkdir(mode=0o755,exist_ok=False)
 auth=PRIVATE/'candidate-xauthority';auth.touch(mode=0o600,exist_ok=False);os.chown(auth,1001,1001)
 subprocess.run(['/usr/bin/xauth','-f',str(auth),'add',':100','MIT-MAGIC-COOKIE-1',secrets.token_hex(16)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 os.chown(auth,1001,1001)
 xlog=(PRIVATE/'candidate-x100.log').open('wb',buffering=0)
 x=subprocess.Popen([str(XSERVER),':100','-screen','0','1280x720x24','-nolisten','tcp','-auth',str(auth),'-noreset'],preexec_fn=user,stdout=xlog,stderr=xlog,start_new_session=True)
 for _ in range(30):
  if Path('/tmp/.X11-unix/X100').exists():break
  assert x.poll()is None;time.sleep(.1)
 assert Path('/tmp/.X11-unix/X100').exists()
 binary=ENGINE/'Engine/Binaries/Linux/UnrealEditor-Cmd';assert binary.open('rb').read(4)==b'\x7fELF'
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/unreal','LANG':'C.UTF-8','DISPLAY':':100','XAUTHORITY':str(auth),'XDG_RUNTIME_DIR':str(PRIVATE/'xdg-runtime'),'OMP_NUM_THREADS':'3','OPENBLAS_NUM_THREADS':'1'}
 args=[str(binary),str(CANDIDATE/'Sub01HomeLab.uproject'),'/Game/Sub01Home/ActualHome','-nullrhi','-NoSplash','-Unattended','-NoSound','-NoLiveCoding','-NoHotReloadFromIDE','-corelimit=3','-physicalcorelimit=3','-ExecutePythonScript=/home/unreal/runtime-tools/private_home_candidate_bootstrap.py','-log','-stdout','-FullStdOutLogOutput','-Windowed','-ResX=1280','-ResY=720']
 log=(PRIVATE/'candidate-nullrhi-editor.log').open('wb',buffering=0);p=subprocess.Popen(args,env=env,preexec_fn=user,stdout=log,stderr=log,start_new_session=True)
 for _ in range(30):
  try:start=proc(p.pid)[0];break
  except FileNotFoundError:time.sleep(.05)
 scope={'schema':'sub01.private-next-home-candidate-scope.v1','source_project':str(SOURCE),'candidate_project':str(CANDIDATE),'game_pid':159171,'game_start_ticks':976840968,'editor_pid':p.pid,'editor_start_ticks':start,'original_map_sha256':MAP_SHA,'module_sha256':MODULE_SHA,'copy_receipt_sha256':sha(copy_path),'deadline_epoch':window['deadline_epoch'],'no_live_promotion':True,'allowed_tasks':['probe'],'candidate_xdisplay':':100','candidate_xserver_pid':x.pid,'nullrhi':True,'started_epoch':time.time()};SCOPE.write_text(json.dumps(scope,indent=2)+'\n');SCOPE.chmod(0o644);print('ISOLATED_CANDIDATE_NULLRHI_STARTED',json.dumps(scope),flush=True)
if __name__=='__main__':run()
