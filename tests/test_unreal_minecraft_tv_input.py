from tools import unreal_minecraft_tv_input as native

def test_install_targets_character_and_real_hit_only():
 h='class World{GENERATED_BODY()};class Character{GENERATED_BODY()\n void ConfigureActualPC();};'
 c='void Begin(){ ConfigureActualPC();}\nvoid Tick(){ Super::Tick(DeltaSeconds);}\nvoid Interact(){if(TryNativeHomeDevice(Hit.GetComponent()))return;}'
 header,cpp=native.install(h,c)
 assert header.index('MinecraftInputId')>header.index('class Character')
 assert 'FocusMinecraftTV(Hit);return;' in cpp
 assert cpp.count(' ConfigureMinecraftTVInput();')==1 and cpp.count(' TickMinecraftTVInput();')==1
 assert 'PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||RouteActive||HandsDiagnosticSeat' in cpp
 assert 'LineTraceSingleByChannel' in cpp and 'Count==1' in cpp
 assert 'native_start_ticks' in cpp and 'chmod(TCHAR_TO_UTF8(*Temp),0600)' in cpp
 assert 'if(OK&&Response&&Response->GetResponseCode()==200)SendMinecraftTVInput' in cpp
 assert 'SetActorLocation' not in cpp and 'SetWorldLocation' not in cpp

def test_bounded_native_proc_reader_executes_against_real_process(tmp_path):
 import shutil,subprocess,pytest
 compiler=shutil.which('c++')
 if not compiler:pytest.skip('C++ compiler unavailable')
 code=native.METHODS.split('static uint64 Sub01MinecraftReadStartTicks',1)[1].split('class FSub01MinecraftTVInput',1)[0]
 source=tmp_path/'read.cpp';binary=tmp_path/'read'
 source.write_text('#include <cstdio>\n#include <cstring>\n#include <cstdlib>\n#include <cstdint>\n#include <unistd.h>\nusing uint64=uint64_t;using uint32=uint32_t;\nstatic uint64 Sub01MinecraftReadStartTicks'+code+'''\nint main(){unsigned int pid=getpid();auto ticks=Sub01MinecraftReadStartTicks(pid);printf("%u %llu\\n",pid,(unsigned long long)ticks);fflush(stdout);char input;return read(0,&input,1)==1?0:1;}''')
 subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
 proc=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 try:
  pid,ticks=map(int,proc.stdout.readline().split())
  # Linux procfs exists on the runtime target; on macOS the bounded reader must fail closed.
  from pathlib import Path
  stat=Path('/proc')/str(pid)/'stat'
  if stat.exists():assert ticks==int(stat.read_text().rsplit(')',1)[1].split()[19]) and ticks>0
  else:assert ticks==0
 finally:proc.communicate('x',timeout=3)
 assert proc.returncode==0
