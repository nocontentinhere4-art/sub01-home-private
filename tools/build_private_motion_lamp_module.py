"""One bounded sibling-only compile; loaded original/candidate projects untouched."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time,signal
import sys
sys.path.insert(0,'/home/unreal/runtime-tools')
from launch_private_persistent_editor import verified_window
from prepare_private_home_candidate import invariants
from unreal_candidate_configurable_motion import install as motion
from unreal_candidate_bed_lamp_power import install as lamp
P=Path('/workspace/sub01-private-native-build/Sub01HomeLab');ENGINE=Path('/workspace/sub01-private-recovered-engine')
HSHA='bda916f22a5bc114660454b3d8a0dd16f8f09dab00be829ae94153b2126ba5de';CSHA='be016bca02559ab0981c4fe0642264395978b8db8fbff1fce41e80abfb48ceef'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stable():
 d=invariants();d['game'].pop('state',None);return d

def run():
 window=verified_window(Path('/run/sub01-home-private/runtime-window.json'));assert time.time()+900<window['deadline_epoch'];original=stable();os.setgroups([]);os.setgid(1001);os.setuid(1001);os.umask(0o077);result=P/'candidate-motion-lamp-build.json';assert not result.exists(),'Never replace or duplicate an actual build job'
 for d in Path('/proc').iterdir():
  if not d.name.isdigit():continue
  try:
   args=(d/'cmdline').read_bytes().split(b'\0')
   if args and Path(args[0].decode()).name=='dotnet'and any(b'UnrealBuildTool.dll'in x for x in args):raise RuntimeError('Another UBT is active; preserve it')
  except(OSError,UnicodeError):pass
 h=P/'Source/Sub01HomeLab/Sub01HomeLab.h';cpp=P/'Source/Sub01HomeLab/Sub01HomeLab.cpp';assert sha(h)==HSHA and sha(cpp)==CSHA;hh,cc=motion(h.read_text(),cpp.read_text());hh,cc=lamp(hh,cc)
 backup=P/'Saved/BeforeMotionLamp'/str(time.time_ns());backup.mkdir(parents=True)
 for p in [h,cpp,*[P/'Binaries/Linux'/n for n in ['libUnrealEditor-Sub01HomeLab.so','libUnrealEditor-Sub01HomeLab.debug','libUnrealEditor-Sub01HomeLab.sym','UnrealEditor.modules','Sub01HomeLabEditor.target']]]:
  if p.is_file():q=backup/p.relative_to(P);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);assert sha(q)==sha(p)
 assert stable()==original;h.write_text(hh);cpp.write_text(cc)
 record={'schema':'sub01.private-candidate-motion-lamp-build.v1','started_epoch':time.time(),'backup':str(backup),'source_header_sha256':sha(h),'source_cpp_sha256':sha(cpp),'status':'running','original_runtime':original,'loaded_projects_changed':False,'runtime_gates_changed':False,'native_compiled':False};result.write_text(json.dumps(record,indent=2)+'\n')
 env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':'/home/unreal','USER':'unreal','LOGNAME':'unreal','LANG':'C.UTF-8','DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1','DOTNET_NOLOGO':'1','DOTNET_CLI_HOME':str(P/'Saved/DotNet'),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
 command=['/usr/bin/nice','-n','19','/usr/bin/taskset','-c','5,6,7','/bin/bash',str(ENGINE/'Engine/Build/BatchFiles/Linux/Build.sh'),'Sub01HomeLabEditor','Linux','Development','-Project='+str(P/'Sub01HomeLab.uproject'),'-WaitMutex','-NoHotReloadFromIDE','-NoEngineChanges','-MaxParallelActions=3','-NoUBA']
 with(P/'candidate-motion-lamp-build.log').open('w')as log:
  child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);record.update(child_pid=child.pid,child_start_ticks=int(Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19]));result.write_text(json.dumps(record,indent=2)+'\n')
  try:code=child.wait(timeout=900)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGTERM);code=child.wait(timeout=15)
 record.update(status='finished',exit=code,finished_epoch=time.time(),original_runtime_unchanged=stable()==original)
 if code==0:
  record.update(native_compiled=True,module_sha256=sha(P/'Binaries/Linux/libUnrealEditor-Sub01HomeLab.so'),module_build_id=json.loads((P/'Binaries/Linux/UnrealEditor.modules').read_text())['BuildId'])
 result.write_text(json.dumps(record,indent=2)+'\n');print('CANDIDATE_MOTION_LAMP_BUILD_FINISHED',code,record.get('module_sha256'),flush=True)
if __name__=='__main__':run()
