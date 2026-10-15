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
 assert 'Targets.Add(Original*FromOriginal*Rigid)' in cpp


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

def test_measured_eye_camera_refuses_other_owner_clip_and_pose(tmp_path):
 import shutil,subprocess,re,pytest
 compiler=shutil.which('c++')
 if not compiler:pytest.skip('C++ compiler unavailable')
 guard=re.search(r' if\(EyeCamera&&\(FMath::Abs\(Time-4\.f\).*?\n',phone.METHODS).group(0)
 source=tmp_path/'eye_gate.cpp';binary=tmp_path/'eye_gate'
 source.write_text(r'''
#include <string>
#include <cmath>
#include <cassert>
#define TEXT(x) x
#define UE_LOG(...)
struct FMath{static float Abs(float x){return std::fabs(x);}};
struct Asset{std::string path;std::string GetPathName(){return path;}};
struct Body{Asset* mesh;Asset* GetSkeletalMeshAsset(){return mesh;}};
bool Check(bool EyeCamera,float Time,Body* FirstPersonBody,Asset* Clip){bool accepted=false;auto Run=[&](){
'''+guard+r'''
accepted=true;};Run();return accepted;}
int main(){Asset owner{"/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner"};Asset clip{"/Game/Sub01Hands/FBX/SUB01_Phone.SUB01_Phone"};Body body{&owner};
 assert(Check(true,4,&body,&clip));assert(!Check(true,3.9f,&body,&clip));
 owner.path="other-owner";assert(!Check(true,4,&body,&clip));
 owner.path="/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner";clip.path="other-clip";assert(!Check(true,4,&body,&clip));
 assert(Check(false,3.9f,&body,&clip));
}
''')
 subprocess.run([compiler,'-std=c++17',str(source),'-o',str(binary)],check=True,capture_output=True)
 subprocess.run([str(binary)],check=True,capture_output=True)
 assert 'if(HeadCamera&&EyeCamera)' in phone.METHODS
 assert 'H.GetRotation().GetNormalized().RotateVector' in phone.METHODS
 assert 'A->GetCurrentAsset()!=PhoneGripCapturedClip.Get()' in phone.METHODS
 assert 'FMath::Abs(A->GetCurrentTime()-4.f)>.01f' in phone.METHODS
 assert 'PrivateViewMode!=EPrivateViewMode::Diagnostic&&ViewCamera)ViewCamera->SetUsingAbsoluteLocation(false)' in phone.METHODS

def test_walk_cleanup_restores_assembly_animation_and_camera_before_walk(tmp_path):
 import shutil,subprocess,pytest
 from tools.unreal_native_control import METHODS as control
 compiler=shutil.which('c++')
 if not compiler:pytest.skip('C++ compiler unavailable')
 src=tmp_path/'walk_cleanup.cpp';exe=tmp_path/'walk_cleanup'
 helper=phone.METHODS.split('bool ASub01HomeCharacter::ApplyPrivatePhoneAssemblyTransforms(const TArray<FTransform>& Targets){',1)[1].split('\n}',1)[0]
 src.write_text(r'''
#include <vector>
#include <cassert>
#include <algorithm>
#define TEXT(x) x
#define UE_LOG(...) ((void)0)
using int32=int;
template<class T>struct TArray:std::vector<T>{using std::vector<T>::vector;int Num()const{return this->size();}bool Contains(T x)const{return std::find(this->begin(),this->end(),x)!=this->end();}void Add(T x){this->push_back(x);}};
struct FTransform{int value;bool ContainsNaN()const{return false;}};
struct Anim{virtual ~Anim()=default;};
struct USub01HomeHandsInstance:Anim{static int StaticClass(){return 1;}};
template<class T>T* Cast(Anim* a){return dynamic_cast<T*>(a);}
struct Part{int transform=100,writes=0;Part* parent=nullptr;std::vector<Part*>children;Part* GetAttachParent(){return parent;}void Shift(int delta){transform+=delta;for(auto* c:children)c->Shift(delta);}void SetWorldTransform(FTransform t){Shift(t.value-transform);++writes;}};
struct Ptr{Part* p;Part* Get()const{return p;}Part* operator->()const{return p;}operator bool()const{return p!=nullptr;}};
bool IsValid(Ptr p){return bool(p);}
struct Body{Anim* anim;USub01HomeHandsInstance walk;int resets=0;Anim* GetAnimInstance(){return anim;}void SetAnimInstanceClass(int){anim=&walk;++resets;}};
struct Camera{bool absolute=true;void SetUsingAbsoluteLocation(bool x){absolute=x;}};
struct Fixture{bool PhoneGripMounted=true,PhoneGripReview=true;TArray<Ptr> PhoneGripParts;TArray<FTransform> PhoneGripOriginalTransforms;Body* FirstPersonBody;Camera* ViewCamera;
bool ApplyPrivatePhoneAssemblyTransforms(const TArray<FTransform>&Targets){
'''+helper+r'''
}
bool Leave(){
'''+phone.WALK_CLEANUP+r'''
return true;}};
int main(){Anim single;Body body{&single};Camera camera;Part parts[5];Fixture f;f.FirstPersonBody=&body;f.ViewCamera=&camera;
 for(int i=0;i<5;++i){f.PhoneGripParts.push_back({&parts[i]});f.PhoneGripOriginalTransforms.push_back({i+10});}
 for(int i:{1,2,3}){parts[i].parent=&parts[4];parts[4].children.push_back(&parts[i]);}
 // Source order really breaks a one-shot restore when part4 owns buttons1..3.
 Part old[5];for(int i:{1,2,3}){old[i].parent=&old[4];old[4].children.push_back(&old[i]);}
 for(int i=0;i<5;++i)old[i].SetWorldTransform({i+10});assert(old[1].transform!=11);
 assert(f.Leave());assert(!f.PhoneGripReview&&!f.PhoneGripMounted&&!camera.absolute&&body.resets==1);
 for(int i=0;i<5;++i)assert(parts[i].transform==i+10&&parts[i].writes==1);
 assert(f.Leave());assert(body.resets==1);for(auto& p:parts)assert(p.writes==1);
 // A cycle, destroyed part or truncated evidence is refused before ANY write.
 parts[4].parent=&parts[1];assert(!f.ApplyPrivatePhoneAssemblyTransforms(f.PhoneGripOriginalTransforms));parts[4].parent=nullptr;
 f.PhoneGripMounted=true;f.PhoneGripParts[0]={nullptr};f.PhoneGripOriginalTransforms.resize(2);assert(!f.Leave());assert(f.PhoneGripReview==false&&f.PhoneGripMounted);
 for(auto& p:parts)assert(p.writes==1);
}
''')
 subprocess.run([compiler,'-std=c++17',str(src),'-o',str(exe)],check=True,capture_output=True)
 subprocess.run([str(exe)],check=True,capture_output=True)
 header,cpp=phone.install(' void ConfigureActualPC();',' ConfigureActualPC(); Super::Tick(DeltaSeconds);'+control)
 start=cpp.index('bool ASub01HomeCharacter::SwitchNativeWalkView(')
 end=cpp.index('void ASub01HomeCharacter::',start+5)
 walk=cpp[start:end]
 assert walk.index('if(!Walk||')<walk.index(phone.WALK_CLEANUP)
 assert walk.index(phone.WALK_CLEANUP)<walk.index('HandsDiagnosticSeat=false;HandsClips.Add')
 assert walk.index('SetUsingAbsoluteLocation(false)')<walk.index('ViewCamera->AttachToComponent(GetRootComponent()')
 assert 'SetActorLocation' not in phone.WALK_CLEANUP and 'NativeSeatVerified' not in phone.WALK_CLEANUP
