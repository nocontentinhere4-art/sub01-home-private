"""Exercise the generated eligibility getter, including real graph boundaries."""
import shutil
import subprocess
import pytest
from tools import unreal_native_viewer_resume as resume
from tools.unreal_live_home_runtime import graph_source


def test_generated_resume_eligibility_executes_actual_node_and_floor_checks(tmp_path):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if compiler is None:
        pytest.skip('A C++ compiler is required for the generated getter')
    nodes = '\n'.join(s.replace('LiveHomeNodes', 'ResumeNodes') for s in graph_source().splitlines() if 'LiveHomeNodes.Add' in s)
    getter = resume.METHODS.split('void ASub01HomeCharacter::WritePrivateViewerResumeReceipt', 1)[0].replace('//@@RESUME_SOURCE_NODES@@', nodes)
    stub = r'''
#include <cassert>
#include <cmath>
#include <string>
#include <vector>
#define TEXT(x) x
struct FString:std::string{using std::string::string;bool IsEmpty()const{return empty();}};
struct FVector{float X,Y,Z;FVector(float x=0,float y=0,float z=0):X(x),Y(y),Z(z){}};
struct FVector2D{float X,Y;FVector2D(float x,float y):X(x),Y(y){}float Size()const{return std::sqrt(X*X+Y*Y);}};
template<class K,class V>struct TMap{struct Pair{K Key;V Value;};std::vector<Pair> items;void Add(K k,V v){items.push_back({k,v});}auto begin(){return items.begin();}auto end(){return items.end();}};
struct FMath{static float Abs(float x){return std::abs(x);}};
struct FCommandLine{static const char* Get(){return "";}};
bool commandEnabled=true;
struct FParse{static bool Param(const char*,const char*){return commandEnabled;}};
FString origin="http://127.0.0.1:8821",token="test-only";
struct FPlatformMisc{static FString GetEnvironmentVariable(const char* name){return std::string(name)=="SUB01_HOME_ORIGIN"?origin:token;}};
struct Name{bool none=true;bool IsNone()const{return none;}};
struct USub01HomeDeviceBridge{bool composing=false;Name focus;Name GetFocusedDevice()const{return focus;}bool IsComposingNote()const{return composing;}};
struct PC{bool focus=false;bool HasOperatorFocus()const{return focus;}};
struct Camera{FVector eye{200,320,170};FVector GetComponentLocation()const{return eye;}};
struct FFindFloorResult{bool bBlockingHit=true;struct{FVector ImpactPoint{200,320,2.5};}HitResult;};
struct Movement{FFindFloorResult CurrentFloor;bool grounded=true;bool IsMovingOnGround()const{return grounded;}};
struct ASub01HomeCharacter{
 enum class EPrivateViewMode{Manual,Live,Diagnostic};EPrivateViewMode PrivateViewMode=EPrivateViewMode::Manual;
 bool LiveHome=false,RouteActive=false,HandsDiagnosticSeat=false,NativeSeatVerified=false,MinecraftFocused=false;
 Camera camera;Camera* ViewCamera=&camera;PC pc;PC* PCBridge=&pc;USub01HomeDeviceBridge device;
 Movement movement;FVector actor{200,320,95.65};
 template<class T>const T* FindComponentByClass()const{return &device;}
 const Movement* GetCharacterMovement()const{return &movement;}FVector GetActorLocation()const{return actor;}
 bool CanPrivateViewerResumeLive()const;
};
'''
    cases = r'''
int main(){
 ASub01HomeCharacter a;assert(a.CanPrivateViewerResumeLive());
 a.actor.X=219.99;assert(a.CanPrivateViewerResumeLive());a.actor.X=220;assert(!a.CanPrivateViewerResumeLive());a.actor.X=200;
 a.movement.CurrentFloor.HitResult.ImpactPoint.Z=20;assert(!a.CanPrivateViewerResumeLive());a.movement.CurrentFloor.HitResult.ImpactPoint.Z=2.5;
 a.actor=FVector(8000,8000,95);assert(!a.CanPrivateViewerResumeLive());a.actor=FVector(200,320,95.65);
 a.movement.grounded=false;assert(!a.CanPrivateViewerResumeLive());a.movement.grounded=true;
 a.movement.CurrentFloor.bBlockingHit=false;assert(!a.CanPrivateViewerResumeLive());a.movement.CurrentFloor.bBlockingHit=true;
 a.camera.eye=FVector(-150,135,400);assert(!a.CanPrivateViewerResumeLive());a.camera.eye=FVector(200,320,170);
 a.pc.focus=true;assert(!a.CanPrivateViewerResumeLive());a.pc.focus=false;
 a.device.composing=true;assert(!a.CanPrivateViewerResumeLive());a.device.composing=false;
 a.MinecraftFocused=true;assert(!a.CanPrivateViewerResumeLive());a.MinecraftFocused=false;
 a.NativeSeatVerified=true;assert(!a.CanPrivateViewerResumeLive());a.NativeSeatVerified=false;
 a.PrivateViewMode=ASub01HomeCharacter::EPrivateViewMode::Diagnostic;assert(!a.CanPrivateViewerResumeLive());a.PrivateViewMode=ASub01HomeCharacter::EPrivateViewMode::Manual;
 commandEnabled=false;assert(!a.CanPrivateViewerResumeLive());commandEnabled=true;
 origin="http://127.0.0.1:9999";assert(!a.CanPrivateViewerResumeLive());origin="http://127.0.0.1:8821";
 token="";assert(!a.CanPrivateViewerResumeLive());return 0;
}
'''
    source=tmp_path/'eligibility.cpp';source.write_text(stub+getter+cases)
    binary=tmp_path/'eligibility'
    subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True,text=True,timeout=30)
    subprocess.run([str(binary)],check=True,capture_output=True,text=True,timeout=5)


def test_resume_ack_requires_actual_fresh_native_binding_and_preserves_operator_revision():
    assert '!SwitchNativeWalkView(true)||!LiveHome' in resume.METHODS
    assert '!LiveHomeFresh||!NativeFeedbackBound||NativeFeedbackLastAck<0' in resume.METHODS
    assert 'Now-NativeFeedbackLastAck>3' in resume.METHODS
    superseded=resume.METHODS.split('if(NativeControlRevision!=Revision)',1)[1].split('\n',1)[0]
    assert 'SwitchNativeWalkView' not in superseded
    assert 'Ownership request superseded' in superseded
    assert 'SetActorLocation' not in resume.METHODS
    assert 'SetActorTransform' not in resume.METHODS
    assert 'Document->Values.Num()!=4' in resume.METHODS


def test_incompatible_native_integration_is_rejected():
    with pytest.raises(ValueError):resume.install('', '')
