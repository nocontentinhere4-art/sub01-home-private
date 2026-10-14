import sys,tempfile
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_controller_grip_diagnostic as adapter
import stage_unreal_home_runtime as runtime


def test_installs_only_explicit_gaming_review_with_source_asset_and_safe_cleanup():
    with tempfile.TemporaryDirectory()as d:
        p=Path(d);(p/'Config').mkdir();(p/'Sub01HomeLab.uproject').write_text('{}');runtime.stage(p)
        module=p/'Source/Sub01HomeLab';h=(module/'Sub01HomeLab.h').read_text();c=(module/'Sub01HomeLab.cpp').read_text()
    assert h.count('void ConfigurePrivateControllerGripReview();')==1
    assert 'Role==TEXT("Gaming")&&FParse::Param' in c
    assert 'if(Role!=TEXT("Gaming"))SetHandsPosture' in c
    method=c.split('void ASub01HomeCharacter::ConfigurePrivateControllerGripReview(){',1)[1]
    assert '/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming' in method
    assert 'Clip->GetSkeleton()!=FirstPersonBody->GetSkeletalMeshAsset()->GetSkeleton()' in method
    assert 'SetPlayRate(0)' in method and 'SetUsingAbsoluteLocation(true)' in method
    assert 'SetActorLocation' not in adapter.METHODS and 'SetBone' not in adapter.METHODS
    assert 'NativeSeatVerified=true' not in adapter.METHODS
    switch=c.split('bool ASub01HomeCharacter::SwitchNativeWalkView',1)[1].split('void ASub01HomeCharacter::UpdatePrivateNativeControl',1)[0]
    assert switch.index('ControllerGripReview=false')<switch.index('SetUsingAbsoluteLocation(false)')<switch.index('ViewCamera->AttachToComponent(GetRootComponent()')
    assert 'SetAnimInstanceClass(USub01HomeHandsInstance::StaticClass())' in switch
    with pytest.raises(ValueError):adapter.install(h,c)


def test_real_gaming_owner_clip_time_gate_executes_without_ue(tmp_path):
    import shutil,subprocess
    compiler=shutil.which('clang++')or shutil.which('g++')
    if not compiler:pytest.skip('No C++ compiler')
    source=adapter.METHODS
    condition=source.split(' if(!HandsDiagnostic||Role!=',1)[1].split('){\n  UE_LOG',1)[0]
    condition='!HandsDiagnostic||Role!='+condition
    time=source.split(' if(!FMath::IsFinite(Time)||Time<0||Time>',1)[1].split('){UE_LOG',1)[0]
    time='!FMath::IsFinite(Time)||Time<0||Time>'+time
    cpp=tmp_path/'gate.cpp';cpp.write_text('''#include <string>
#include <cmath>
#define TEXT(x) x
struct Asset{std::string path;int skeleton=1;std::string GetPathName(){return path;}int GetSkeleton(){return skeleton;}float GetPlayLength(){return 5.033333f;}};
struct Component{Asset* mesh;Asset* GetSkeletalMeshAsset(){return mesh;}};
struct FMath{static bool IsFinite(float t){return std::isfinite(t);}};
bool Reject(bool HandsDiagnostic,std::string Role,Component* FirstPersonBody,Asset* Clip){return '''+condition+''';}
bool BadTime(float Time,Asset* Clip){return '''+time+''';}
int main(){Asset owner{"/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner"},clip{"/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming"};Component body{&owner};
if(Reject(true,"Gaming",&body,&clip)||BadTime(4,&clip))return 1;
if(!Reject(false,"Gaming",&body,&clip)||!Reject(true,"Phone",&body,&clip)||!Reject(true,"Gaming",nullptr,&clip)||!Reject(true,"Gaming",&body,nullptr))return 2;
owner.path="OtherOwner";if(!Reject(true,"Gaming",&body,&clip))return 3;owner.path="/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner";
clip.skeleton=2;if(!Reject(true,"Gaming",&body,&clip))return 4;clip.skeleton=1;clip.path="OtherClip";if(!Reject(true,"Gaming",&body,&clip))return 5;
if(!BadTime(NAN,&clip)||!BadTime(-1,&clip)||!BadTime(6,&clip))return 6;return 0;}
''')
    result=subprocess.run([compiler,'-std=c++17','-Wall','-Werror',str(cpp),'-o',str(tmp_path/'gate')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert subprocess.run([str(tmp_path/'gate')]).returncode==0
