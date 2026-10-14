from tools import unreal_minecraft_tv_input as native

def test_install_targets_character_and_real_hit_only():
 h='class World{GENERATED_BODY()};class Character{GENERATED_BODY()\n void ConfigureActualPC();};'
 c='void Begin(){ ConfigureActualPC();}\nvoid Tick(){ Super::Tick(DeltaSeconds);}\nvoid Interact(){if(TryNativeHomeDevice(Hit.GetComponent()))return;}'
 header,cpp=native.install(h,c)
 assert header.index('class IInputProcessor;')<header.index('class World')
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

def test_real_e_event_refocus_requires_current_tv_ray_and_frame(tmp_path):
 """Execute the installed handler against device/event stubs, including the Pong switch."""
 import shutil,subprocess,pytest
 compiler=shutil.which('c++')
 if not compiler:pytest.skip('C++ compiler unavailable')
 handler=native.METHODS.split(' bool HandleKeyDownEvent',1)[1].split(' bool HandleKeyUpEvent',1)[0]
 source=tmp_path/'events.cpp';binary=tmp_path/'events'
 source.write_text(r'''
#include <string>
#include <map>
#include <cassert>
#define TEXT(x) x
struct FString:std::string{using std::string::string;bool IsEmpty()const{return empty();}};
enum class EKeys{E,Escape,W,Other};using FKey=EKeys;
struct FSlateApplication{};struct FKeyEvent{EKeys key;bool repeat=false;EKeys GetKey()const{return key;}bool IsRepeat()const{return repeat;}};
struct FVector{double x=0;FVector operator+(FVector b)const{return{x+b.x};}FVector operator*(double b)const{return{x*b};}};
struct Component{bool tag=true;bool ComponentHasTag(const char*)const{return tag;}};
struct FHitResult{Component* component=nullptr;Component* GetComponent(){return component;}};
struct FCollisionQueryParams{void AddIgnoredActor(void*){}};constexpr int ECC_Visibility=0;
struct Camera{FVector GetComponentLocation(){return{};}FVector GetForwardVector(){return{1};}};
struct World{bool ray=true;int queries=0;Component component;bool LineTraceSingleByChannel(FHitResult& h,FVector,FVector,int,FCollisionQueryParams){++queries;h.component=&component;return ray;}};
struct USub01HomeDeviceBridge{FString focus="tv";bool frame=false;FString GetFocusedDevice(){return focus;}bool GetDisplayedMinecraftFrame(FString& s){s="actual-frame";return frame;}};
struct Keys{std::map<std::string,bool> values;void Add(FString k,bool v){values[k]=v;}};
struct Actor{bool MinecraftFocused=false,allow=true;int focusCalls=0;Keys MinecraftKeys;USub01HomeDeviceBridge device;World world;Camera camera;Camera* ViewCamera=&camera;
 template<class T>T* FindComponentByClass(){return &device;}World* GetWorld(){return &world;}
 void FocusMinecraftTV(const FHitResult&){++focusCalls;if(allow)MinecraftFocused=true;}
 void ReleaseMinecraftTVInput(){MinecraftFocused=false;MinecraftKeys.values.clear();}
};
struct OwnerRef{Actor* actor;Actor* Get(){return actor;}};
struct Handler{OwnerRef Owner;FString KeyName(FKey k){return k==EKeys::W?FString("forward"):FString();}
 bool HandleKeyDownEvent'''+handler.replace('override','')+r'''
};
int main(){FSlateApplication app;Actor a;Handler h{{&a}};
 // Pong is focused but there are no current Minecraft pixels: E cannot mint a lease.
 assert(!h.HandleKeyDownEvent(app,{EKeys::E}));assert(a.focusCalls==0&&a.world.queries==0);
 a.device.frame=true;a.world.ray=false;assert(!h.HandleKeyDownEvent(app,{EKeys::E}));assert(a.focusCalls==0);
 a.world.ray=true;a.world.component.tag=false;assert(!h.HandleKeyDownEvent(app,{EKeys::E}));assert(a.focusCalls==0);
 a.world.component.tag=true;int before=a.world.queries;assert(!h.HandleKeyDownEvent(app,{EKeys::E,true}));assert(a.world.queries==before);
 a.allow=false;assert(!h.HandleKeyDownEvent(app,{EKeys::E}));assert(a.focusCalls==1&&!a.MinecraftFocused);
 a.allow=true;assert(h.HandleKeyDownEvent(app,{EKeys::E}));assert(a.focusCalls==2&&a.MinecraftFocused);
 assert(!h.HandleKeyDownEvent(app,{EKeys::E}));assert(a.focusCalls==2); // no repeated identity renewal
 assert(h.HandleKeyDownEvent(app,{EKeys::W}));assert(a.MinecraftKeys.values["forward"]);
 assert(h.HandleKeyDownEvent(app,{EKeys::Escape}));assert(!a.MinecraftFocused&&a.MinecraftKeys.values.empty());
 assert(!h.HandleKeyDownEvent(app,{EKeys::W}));
}
''')
 subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
 subprocess.run([str(binary)],check=True,capture_output=True)
