"""Optional native hinge adapter, generated ONLY from the proved kitchen manifest.

No controller files are edited here. The sole generator owner calls install.
Closed-pose visual import works without this adapter; activation additionally
requires SUB01_KITCHEN_RUNTIME=1 and fresh authenticated nonprivate backend state.
"""
import json
import re
from prepare_real_kitchen_native_bundle import validate_manifest

POLICY = r'''
#include <cmath>
namespace Sub01Kitchen {
inline constexpr double OpenDegrees=88.2;
template<class Blocked> double Advance(double angle,double target,double dt,Blocked blocked){
 if(!std::isfinite(angle)||!std::isfinite(target)||!std::isfinite(dt)||dt<=0||angle<0||angle>OpenDegrees)return angle;
 target=std::fmax(0.,std::fmin(OpenDegrees,target));
 const double distance=std::fmin(std::fabs(target-angle),70.*std::fmin(dt,.05));
 const int count=int(std::ceil(distance/.25));if(!count)return angle;
 const double direction=target>angle?1.:-1.;double previous=angle;
 for(int i=1;i<=count;++i){const double next=angle+direction*distance*i/count;if(blocked(previous,next))return angle;previous=next;}
 return previous;
}
}
'''

INCLUDES = r'''
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Engine/OverlapResult.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
'''+POLICY

FIELDS = r'''
 UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> KitchenParts;
 TArray<FTransform> KitchenClosed;
 float KitchenAngles[8]={};bool KitchenBackendOpen[8]={};
 bool KitchenReady=false,KitchenPollPending=false,KitchenActionPending=false;
 double KitchenStateAt=-10,KitchenPollAt=0;
 mutable double KitchenBlockLogAt=0;
 FString KitchenOrigin,KitchenToken;
 void ConfigureActualKitchen();
 void PollActualKitchen();
 void UpdateActualKitchen(float DeltaSeconds);
 bool TryNativeKitchen(UActorComponent* HitComponent);
 UFUNCTION(Exec) void InspectActualKitchen();
 bool KitchenSweepBlocked(int Door,float From,float To) const;
'''

METHODS = r'''
namespace {
struct FSub01KitchenSpec {int Door;const TCHAR* Tag;FVector Minimum;FVector Maximum;};
const FSub01KitchenSpec KitchenSpecs[]={@@SPECS@@};
const FVector KitchenHinges[]={@@HINGES@@};
const TCHAR* KitchenOwnedPrefix=TEXT("@@DEST@@");
}
void ASub01HomeCharacter::InspectActualKitchen(){
 const double Now=FPlatformTime::Seconds();
 if(PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||RouteActive||HandsDiagnosticSeat||NativePrivacyLast||Now-NativePrivacyPublishedAt>.5){
  UE_LOG(LogTemp,Warning,TEXT("SUB01_KITCHEN_INSPECT_REFUSED fresh public manual view required"));return;
 }
 if(!KitchenReady||KitchenParts.Num()!=40||KitchenClosed.Num()!=40){UE_LOG(LogTemp,Warning,TEXT("SUB01_KITCHEN_INSPECT_REFUSED exact 8hinge/40part binding absent"));return;}
 for(int I=0;I<40;++I){const auto* C=KitchenParts[I].Get();if(!IsValid(C)||!C->GetStaticMesh()||!C->GetStaticMesh()->GetPathName().StartsWith(KitchenOwnedPrefix)||!C->ComponentHasTag(FName(KitchenSpecs[I].Tag))){UE_LOG(LogTemp,Warning,TEXT("SUB01_KITCHEN_INSPECT_REFUSED source binding differs part=%d"),I);return;}}
 const uint32 Pid=FPlatformProcess::GetCurrentProcessId();const int64 Ticks=PrivateSettingsStartTicks();
 UE_LOG(LogTemp,Display,TEXT("SUB01_KITCHEN_INSPECT_BEGIN pid=%u start=%lld binding=%s stateAge=%.6f sourceFresh=%d actionPending=%d; read_only=true"),Pid,Ticks,KitchenOwnedPrefix,Now-KitchenStateAt,int(Now-KitchenStateAt<=2),int(KitchenActionPending));
 for(int Door=0;Door<8;++Door)UE_LOG(LogTemp,Display,TEXT("SUB01_KITCHEN_INSPECT_DOOR index=%d actualDegrees=%.9f backendOpen=%d targetDegrees=%.9f hinge=%s"),Door,KitchenAngles[Door],int(KitchenBackendOpen[Door]),KitchenBackendOpen[Door]?Sub01Kitchen::OpenDegrees:0.,*KitchenHinges[Door].ToString());
 for(int I=0;I<40;++I){const auto* C=KitchenParts[I].Get();const FTransform T=C->GetComponentTransform();const FTransform& Closed=KitchenClosed[I];
  UE_LOG(LogTemp,Display,TEXT("SUB01_KITCHEN_INSPECT_PART index=%d door=%d component=%s mesh=%s position=%s quaternion=%s scale=%s closedPosition=%s closedQuaternion=%s closedScale=%s collision=%d visible=%d"),I,I/5,*C->GetPathName(),*C->GetStaticMesh()->GetPathName(),*T.GetLocation().ToString(),*T.GetRotation().ToString(),*T.GetScale3D().ToString(),*Closed.GetLocation().ToString(),*Closed.GetRotation().ToString(),*Closed.GetScale3D().ToString(),int(C->GetCollisionEnabled()),int(C->IsVisible()));
 }
 UE_LOG(LogTemp,Display,TEXT("SUB01_KITCHEN_INSPECT_END pid=%u start=%lld doors=8 parts=40; geometry_movement_settings_unchanged=true"),Pid,Ticks);
}
void ASub01HomeCharacter::ConfigureActualKitchen(){
 if(FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_KITCHEN_RUNTIME"))!=TEXT("1"))return;
 KitchenOrigin=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_HOME_ORIGIN"));
 KitchenToken=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN"));
 if(KitchenOrigin!=TEXT("http://127.0.0.1:8821")||KitchenToken.IsEmpty())return;
 TArray<UStaticMeshComponent*> Found;Found.Init(nullptr,40);int Tagged=0;
 for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UStaticMeshComponent*> Parts;It->GetComponents(Parts);
  for(auto* C:Parts){for(const auto& Tag:C->ComponentTags)if(Tag.ToString().StartsWith(TEXT("SUB01Kitchen:")))++Tagged;
   for(int I=0;I<40;++I)if(C->ComponentHasTag(FName(KitchenSpecs[I].Tag))){
    if(Found[I]||!C->GetStaticMesh()||!C->GetStaticMesh()->GetPathName().StartsWith(KitchenOwnedPrefix)||
       C->GetCollisionEnabled()!=ECollisionEnabled::QueryAndPhysics||C->Mobility!=EComponentMobility::Movable||!C->IsVisible()||C->GetOwner()->IsHidden())return;
    const auto Box=C->CalcBounds(C->GetComponentTransform()).GetBox();
    if(!Box.Min.Equals(KitchenSpecs[I].Minimum,.05)||!Box.Max.Equals(KitchenSpecs[I].Maximum,.05))return;
    Found[I]=C;
   }
  }
 }
 if(Tagged!=40)return;for(auto* C:Found)if(!C)return;
 for(auto* C:Found){KitchenParts.Add(C);KitchenClosed.Add(C->GetComponentTransform());}
 KitchenReady=true;
 UE_LOG(LogTemp,Display,TEXT("SUB01_KITCHEN_BOUND 8hinges/40actualmovingparts from152part sourcepacket; backend state and blocked-motion tests pending"));
}
bool ASub01HomeCharacter::KitchenSweepBlocked(int Door,float From,float To) const{
 if(!KitchenReady||Door<0||Door>=8||KitchenParts.Num()!=40||!GetWorld())return true;
 FCollisionQueryParams Query(SCENE_QUERY_STAT(Sub01KitchenHinge),false);
 for(int J=0;J<5;++J){if(!IsValid(KitchenParts[Door*5+J]))return true;Query.AddIgnoredComponent(KitchenParts[Door*5+J].Get());}
 const FVector Hinge=KitchenHinges[Door];
 const FQuat First(FVector::UpVector,FMath::DegreesToRadians(From)),Last(FVector::UpVector,FMath::DegreesToRadians(To));
 const FQuat Mid(FVector::UpVector,FMath::DegreesToRadians((From+To)*.5f));
 for(int J=0;J<5;++J){const int I=Door*5+J;FVector Minimum,Maximum;KitchenParts[I]->GetLocalBounds(Minimum,Maximum);FBox Hull(ForceInit);float Radius=0;
  for(int X=0;X<2;++X)for(int Y=0;Y<2;++Y)for(int Z=0;Z<2;++Z){
   const FVector Corner=KitchenClosed[I].TransformPosition(FVector(X?Maximum.X:Minimum.X,Y?Maximum.Y:Minimum.Y,Z?Maximum.Z:Minimum.Z))-Hinge;
   Radius=FMath::Max(Radius,float(FVector2D(Corner.X,Corner.Y).Size()));
   Hull+=Mid.UnrotateVector(First.RotateVector(Corner));Hull+=Mid.UnrotateVector(Last.RotateVector(Corner));
  }
  const float Sag=Radius*(1.f-FMath::Cos(FMath::DegreesToRadians(FMath::Abs(To-From)*.5f)));
  TArray<FOverlapResult> Hits;
  GetWorld()->OverlapMultiByChannel(Hits,Hinge+Mid.RotateVector(Hull.GetCenter()),Mid,ECC_Pawn,
      FCollisionShape::MakeBox(Hull.GetExtent()+FVector(Sag,Sag,0)),Query);
  for(const auto& Hit:Hits)if(Hit.bBlockingHit){
   const double Now=FPlatformTime::Seconds();if(Now-KitchenBlockLogAt>2){KitchenBlockLogAt=Now;
    UE_LOG(LogTemp,Warning,TEXT("SUB01_KITCHEN_BLOCKED actual door=%d angle=%.3f->%.3f part=%d blocker=%s; motion stopped, collision retained"),Door,From,To,J,*GetPathNameSafe(Hit.GetComponent()));
   }return true;
  }
 }
 return false;
}
void ASub01HomeCharacter::PollActualKitchen(){
 if(!KitchenReady||KitchenPollPending)return;KitchenPollPending=true;KitchenPollAt=FPlatformTime::Seconds()+.5;
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(KitchenOrigin+TEXT("/home/state"));Request->SetVerb(TEXT("GET"));Request->SetTimeout(1.2f);Request->SetHeader(TEXT("X-Admin-Token"),KitchenToken);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){
  KitchenPollPending=false;KitchenStateAt=-10;if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200)return;
  TSharedPtr<FJsonObject> Doc;if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Response->GetContentAsString()),Doc)||!Doc.IsValid())return;
  const TSharedPtr<FJsonObject>* Source=nullptr;const TSharedPtr<FJsonObject>* Kitchen=nullptr;FString Status;bool Private=true;
  if(!Doc->TryGetObjectField(TEXT("source"),Source)||!(*Source)->TryGetStringField(TEXT("status"),Status)||Status!=TEXT("live")||
     !Doc->TryGetBoolField(TEXT("privacy"),Private)||Private||!Doc->TryGetObjectField(TEXT("kitchen"),Kitchen))return;
  bool Values[8];
  for(int Group=0;Group<2;++Group){const TArray<TSharedPtr<FJsonValue>>* Array=nullptr;
   if(!(*Kitchen)->TryGetArrayField(Group?TEXT("lowerCabinets"):TEXT("cabinets"),Array)||Array->Num()!=4)return;
   for(int J=0;J<4;++J)if(!(*Array)[J].IsValid()||!(*Array)[J]->TryGetBool(Values[Group*4+J]))return;
  }
  for(int I=0;I<8;++I)KitchenBackendOpen[I]=Values[I];KitchenStateAt=FPlatformTime::Seconds();
 });
 if(!Request->ProcessRequest()){KitchenPollPending=false;KitchenStateAt=-10;}
}
bool ASub01HomeCharacter::TryNativeKitchen(UActorComponent* HitComponent){
 if(!KitchenReady)return false;int Door=-1;UStaticMeshComponent* HitPart=nullptr;
 for(int I=0;I<KitchenParts.Num();++I)if(HitComponent==KitchenParts[I].Get()){Door=I/5;HitPart=KitchenParts[I].Get();break;}
 if(Door<0)return false;
 if(!HitPart||FVector::Dist(GetActorLocation(),HitPart->Bounds.GetBox().GetClosestPointTo(GetActorLocation()))>200||
    KitchenActionPending||FPlatformTime::Seconds()-KitchenStateAt>2)return true;
 const int Base=Door<4?0:4;bool Values[4];for(int I=0;I<4;++I)Values[I]=KitchenBackendOpen[Base+I];Values[Door-Base]=!Values[Door-Base];
 const auto Bool=[](bool V){return V?TEXT("true"):TEXT("false");};
 const FString Body=FString::Printf(TEXT("{\"%s\":[%s,%s,%s,%s]}"),Base?TEXT("lowerCabinets"):TEXT("cabinets"),Bool(Values[0]),Bool(Values[1]),Bool(Values[2]),Bool(Values[3]));
 KitchenActionPending=true;auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(KitchenOrigin+TEXT("/home/controls"));Request->SetVerb(TEXT("POST"));Request->SetTimeout(1.2f);
 Request->SetHeader(TEXT("X-Admin-Token"),KitchenToken);Request->SetHeader(TEXT("Content-Type"),TEXT("application/json"));Request->SetContentAsString(Body);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){KitchenActionPending=false;KitchenPollAt=0;
  if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200)UE_LOG(LogTemp,Warning,TEXT("SUB01_KITCHEN_SETTING_REFUSED awaiting actual backend publication"));});
 if(!Request->ProcessRequest())KitchenActionPending=false;return true;
}
void ASub01HomeCharacter::UpdateActualKitchen(float DeltaSeconds){
 if(!KitchenReady)return;const double Now=FPlatformTime::Seconds();if(Now>=KitchenPollAt)PollActualKitchen();if(Now-KitchenStateAt>2)return;
 for(int Door=0;Door<8;++Door){
  const float Next=float(Sub01Kitchen::Advance(KitchenAngles[Door],KitchenBackendOpen[Door]?Sub01Kitchen::OpenDegrees:0.,DeltaSeconds,
      [this,Door](double A,double B){return KitchenSweepBlocked(Door,float(A),float(B));}));
  if(Next==KitchenAngles[Door])continue;
  const FQuat Swing(FVector::UpVector,FMath::DegreesToRadians(Next));const FVector Hinge=KitchenHinges[Door];
  for(int J=0;J<5;++J){const int I=Door*5+J;const FTransform& Closed=KitchenClosed[I];
   const FTransform Pose(Swing*Closed.GetRotation(),Hinge+Swing.RotateVector(Closed.GetLocation()-Hinge),Closed.GetScale3D());
   KitchenParts[I]->SetWorldTransform(Pose,false,nullptr,ETeleportType::None);
  }
  KitchenAngles[Door]=Next;
 }
}
'''


def native_asset_root(proof, native_receipt):
    """Use the actual saved import namespace, including reviewed retry versions."""
    validate_manifest(proof)
    if not isinstance(native_receipt, dict) or native_receipt.get('schema') != 'sub01.real-kitchen-native-import.v1':
        raise ValueError('Actual saved kitchen import receipt required; no guessed asset prefix')
    rows = native_receipt.get('parts', [])
    if (native_receipt.get('export_sha256') != proof['export_sha256']
            or len(rows) != 152 or len({r.get('part') for r in rows}) != 152
            or {r.get('part') for r in rows} != {p['name'] for p in proof['parts']}
            or native_receipt.get('hinges') != proof['hinges']
            or type(native_receipt.get('protected_originals_verified')) is not int
            or native_receipt['protected_originals_verified'] <= 0
            or any(r.get('surface_parity', {}).get('all_native_triangles_matched') is not True for r in rows)):
        raise ValueError('Complete source-matching 152-part/eight-hinge native import required')
    pattern = re.compile(r'^(/Game/Sub01Home/RealKitchen/V_'+proof['export_sha256'][:12]+r'(?:_R[1-9][0-9]{0,2})?)/')
    roots = set()
    for row in rows:
        path = row.get('mesh')
        match = pattern.match(path) if isinstance(path, str) else None
        if not match or '/StaticMeshes/' not in path:
            raise ValueError('Actual native kitchen asset is outside the exact owned namespace')
        roots.add(match.group(1)+'/')
    if len(roots) != 1:
        raise ValueError('Native kitchen mixes distinct import versions')
    return roots.pop()


def methods(proof, native_receipt=None):
    asset_root = native_asset_root(proof, native_receipt)
    parts = {p['name']: p for p in proof['parts']}
    specs, hinges = [], []
    vector = lambda values: 'FVector('+','.join(format(float(v), '.12g') for v in values)+')'
    for hinge in proof['hinges']:
        hinges.append(vector(hinge['hinge_ue_cm']))
        for part in sorted((parts[n] for n in hinge['parts']), key=lambda p: p['source_part']):
            if part['source_part'] not in {'mesh-'+str(i) for i in range(5)}:
                raise ValueError('Unexpected moving source part')
            tag = f"SUB01Kitchen:{proof['export_sha256']}:D{hinge['index']}:{part['source_part']}"
            lo, hi = [[p[k]*100 for k in (0, 2, 1)] for p in part['bounds_browser_m']]
            specs.append('{'+str(hinge['index'])+',TEXT('+json.dumps(tag)+'),'+vector(lo)+','+vector(hi)+'}')
    return METHODS.replace('@@SPECS@@', ',\n'.join(specs)).replace('@@HINGES@@', ','.join(hinges)).replace(
        '@@DEST@@', asset_root)


def install(header, cpp, proof, native_receipt=None):
    """Optional later compile; never required for the closed-pose visual import."""
    validate_manifest(proof)
    if 'ConfigureActualKitchen' in cpp:
        raise ValueError('Kitchen adapter already installed')
    for marker in (' ConfigureActualPC();', ' Super::Tick(DeltaSeconds);', ' FString Device;\n'):
        if cpp.count(marker) != 1:
            raise ValueError('Missing/ambiguous actual native hook '+marker.strip())
    if header.count(' void Forward(float Value);') != 1:
        raise ValueError('Missing actual character class hook')
    if 'class UStaticMeshComponent;' not in header:
        marker = '#include "Sub01HomeLab.generated.h"'
        header = header.replace(marker, marker+'\nclass UStaticMeshComponent;', 1) if marker in header else 'class UStaticMeshComponent;\n'+header
    header = header.replace(' void Forward(float Value);', FIELDS+'\n void Forward(float Value);', 1)
    cpp = cpp.replace(' ConfigureActualPC();', ' ConfigureActualPC();\n ConfigureActualKitchen();', 1)
    cpp = cpp.replace(' Super::Tick(DeltaSeconds);', ' Super::Tick(DeltaSeconds);\n UpdateActualKitchen(DeltaSeconds);', 1)
    cpp = cpp.replace(' FString Device;\n', ' if(TryNativeKitchen(Hit.GetComponent()))return;\n FString Device;\n', 1)
    return header, INCLUDES+cpp+methods(proof, native_receipt)
