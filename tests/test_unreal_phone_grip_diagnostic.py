from tools import unreal_phone_grip_diagnostic as phone

def test_install_is_explicit_diagnostic_only_and_preserves_five_parts():
 h='class World{GENERATED_BODY()};class Character{GENERATED_BODY()\n void ConfigureActualPC();};'
 c='void Begin(){ ConfigureActualPC();}\nvoid Tick(){ Super::Tick(DeltaSeconds);}'
 from tools.unreal_native_control import METHODS as control
 c+=control
 header,cpp=phone.install(h,c)
 assert header.index('PhoneGripReview')>header.index('class Character')
 assert cpp.count(' ConfigurePrivatePhoneGripReview();')==1
 assert cpp.count(' UpdatePrivatePhoneGripReview();')==1
 assert 'PrivateViewMode=EPrivateViewMode::Diagnostic;' in cpp
 assert 'Sub01PhoneGripDiagnostic' in cpp and 'Role!=TEXT("Phone")' in cpp
 assert 'Sub01PhoneMountCm=' in cpp and 'Sub01PhoneMountEuler=' in cpp
 assert 'PlayAnimation(Clip,false)' in cpp and 'SetPosition' in cpp
 assert len(phone.PARTS)==5 and phone.PARTS[0][1]==(3.75,7.5,.75)
 # No finger/bone pose replacement, altered readiness, added static phone image, or duplicate prop.
 assert 'SetBone' not in phone.METHODS and 'NativeSeatVerified=' not in phone.METHODS
 assert 'NewObject<UStaticMeshComponent>' not in cpp and 'SetMaterial' not in cpp
 assert 'PhoneGripOriginalTransforms[I]*FromOriginal*Rigid' in cpp


def test_rejects_ambiguous_header_and_setup_hooks():
 import pytest
 with pytest.raises(ValueError):phone.install(' void ConfigureActualPC();'*2,' ConfigureActualPC(); Super::Tick(DeltaSeconds);')

def test_protected_candidate_handler_executes_only_bounded_named_field(tmp_path):
 import shutil,subprocess,pytest
 compiler=shutil.which('c++')
 if not compiler:pytest.skip('C++ compiler unavailable')
 src=tmp_path/'candidate.cpp';exe=tmp_path/'candidate'
 src.write_text(r'''
#include <string>
#include <cassert>
#define TEXT(x) x
struct FString:std::string{using std::string::string;bool IsEmpty()const{return empty();}int Len()const{return size();}};
struct Document{std::string key,value;bool string=true;bool TryGetStringField(const char* name,FString& out){if(!string||key!=name)return false;out=FString(value.c_str());return true;}};
struct Handler{Document* Doc;int calls=0;FString last;void NativePhoneGripCandidate(const FString& p){++calls;last=p;}void Handle(){
'''+phone.CONTROL+r'''
}};
int main(){Document doc;Handler handler{&doc};
 doc.key="command";doc.value="NativePC";handler.Handle();assert(handler.calls==0);
 doc.key="phoneGripCandidate";doc.value="";handler.Handle();assert(handler.calls==0);
 doc.value=std::string(201,'x');handler.Handle();assert(handler.calls==0);
 doc.string=false;doc.value="X=1 Y=2 Z=3|P=0 Y=0 R=0";handler.Handle();assert(handler.calls==0);
 doc.string=true;handler.Handle();assert(handler.calls==1&&handler.last==doc.value);
}
''')
 subprocess.run([compiler,'-std=c++17',str(src),'-o',str(exe)],check=True,capture_output=True)
 subprocess.run([str(exe)],check=True,capture_output=True)
 # Forwarding remains behind the existing runtime isolation, clip, time and finite limits.
 assert 'PhoneGripReview||PrivateViewMode!=EPrivateViewMode::Diagnostic' in phone.METHODS
 assert 'Animation->GetCurrentAsset()!=PhoneGripCapturedClip.Get()' in phone.METHODS
 assert 'FMath::Abs(Animation->GetCurrentTime()-PhoneGripPoseTime)>.01f' in phone.METHODS
 assert 'Offset.ContainsNaN()||Rotation.ContainsNaN()||Offset.Size()>30' in phone.METHODS
 assert 'if(!FMath::IsFinite(Time))return;' in phone.METHODS
