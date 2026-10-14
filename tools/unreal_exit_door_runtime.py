"""Actual imported front-door hinge motion; generator owner installs this adapter.

Exact geometry: full-home.glb nodes51/52, meshes43/44. UE centimetres are
100*(glTF x,z,y). Binding refuses missing/ambiguous geometry. This only moves
those existing collidable components; it does not create a door/outdoor world.
"""
GEOMETRY = {'leaf': {'node':51,'mesh':43,'center_cm':(199.5,390.,110.),'extent_cm':(52.5,3.75,110.)},
            'knob': {'node':52,'mesh':44,'center_cm':(241.,384.,105.),'extent_cm':(2.7,2.7,2.7)},
            'hinge_cm':(147.,390.,0.), 'verified_entry_floor_cm':2.5001, 'sweep_hinge_collar_cm':4., 'sweep_min_z_cm':2.55, 'tag':'SUB01Door:Front'}
# Engine-independent actual stepping policy, compiled/executed by the tests.
POLICY = r'''
#include <cmath>
namespace Sub01ExitDoor {
template<class Blocked> double Advance(double angle,double target,double dt,Blocked blocked){
 if(!std::isfinite(angle)||!std::isfinite(target)||!std::isfinite(dt)||dt<=0)return angle;
 target=std::fmax(0.0,std::fmin(86.4,target));
 const double distance=std::fmin(std::fabs(target-angle),70.0*std::fmin(dt,0.05));
 const int steps=int(std::ceil(distance/1.0));if(!steps)return angle;
 const double direction=target>angle?1.0:-1.0;
 // Test every intermediate pose before committing any motion this tick.
 for(int i=1;i<=steps;++i)if(blocked(angle+direction*distance*i/steps))return angle;
 return angle+direction*distance;
}
}
'''
INCLUDES = r'''
#include "Components/StaticMeshComponent.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "HAL/PlatformTime.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "HAL/PlatformMisc.h"
'''+POLICY
FIELDS = r'''
 UPROPERTY() TObjectPtr<UStaticMeshComponent> ExitDoorLeaf;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> ExitDoorKnob;
 FTransform ExitDoorClosedLeaf,ExitDoorClosedKnob;
 float ExitDoorAngle=0,ExitDoorTarget=0;
 FString ExitDoorOrigin,ExitDoorToken;
 bool ExitDoorPollPending=false,ExitDoorActionPending=false,ExitDoorLocked=true;
 double ExitDoorPollAt=0,ExitDoorStateAt=-10;
 void PollActualExitDoor();
 void ConfigureActualExitDoor();
 bool TryNativeExitDoor(UActorComponent* HitComponent);
 void UpdateActualExitDoor(float DeltaSeconds);
 bool ExitDoorPoseBlocked(float Angle) const;
 FTransform ExitDoorPose(const FTransform& Closed,float Angle) const;
'''
METHODS = r'''
FTransform ASub01HomeCharacter::ExitDoorPose(const FTransform& Closed,float Angle) const{
 const FVector Hinge(147,390,0);const FQuat Swing(FVector::UpVector,FMath::DegreesToRadians(Angle));
 return FTransform(Swing*Closed.GetRotation(),Hinge+Swing.RotateVector(Closed.GetLocation()-Hinge),Closed.GetScale3D());
}
void ASub01HomeCharacter::ConfigureActualExitDoor(){
 UStaticMeshComponent* Leaf=nullptr;UStaticMeshComponent* Knob=nullptr;int Leaves=0,Knobs=0;
 for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UStaticMeshComponent*> Parts;It->GetComponents(Parts);
  for(auto* C:Parts){if(!C->GetStaticMesh())continue;const auto B=C->CalcBounds(C->GetComponentTransform());
   if(FVector::Dist(B.Origin,FVector(199.5,390,110))<.2&&FVector::Dist(B.BoxExtent,FVector(52.5,3.75,110))<.2){Leaf=C;++Leaves;}
   if(FVector::Dist(B.Origin,FVector(241,384,105))<.2&&FVector::Dist(B.BoxExtent,FVector(2.7,2.7,2.7))<.2){Knob=C;++Knobs;}
  }
 }
 if(Leaves!=1||Knobs!=1){UE_LOG(LogTemp,Error,TEXT("SUB01_EXIT_DOOR_REFUSED unique authored geometry required leaf=%d knob=%d"),Leaves,Knobs);return;}
 ExitDoorOrigin=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_HOME_ORIGIN"));
 ExitDoorToken=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN"));
 if(ExitDoorOrigin!=TEXT("http://127.0.0.1:8821")||ExitDoorToken.IsEmpty()){UE_LOG(LogTemp,Error,TEXT("SUB01_EXIT_DOOR_REFUSED actual authenticated loopback bridge required"));return;}
 ExitDoorLeaf=Leaf;ExitDoorKnob=Knob;ExitDoorClosedLeaf=Leaf->GetComponentTransform();ExitDoorClosedKnob=Knob->GetComponentTransform();
 for(auto* C:{Leaf,Knob}){C->SetMobility(EComponentMobility::Movable);C->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);C->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);C->SetCollisionResponseToChannel(ECC_Visibility,ECR_Block);C->ComponentTags.AddUnique(TEXT("SUB01Door:Front"));}
 UE_LOG(LogTemp,Display,TEXT("SUB01_EXIT_DOOR_BOUND leaf=%s knob=%s hinge=147,390,0"),*Leaf->GetName(),*Knob->GetName());
}
bool ASub01HomeCharacter::TryNativeExitDoor(UActorComponent* HitComponent){
 if(!ExitDoorLeaf||!ExitDoorKnob||(HitComponent!=ExitDoorLeaf&&HitComponent!=ExitDoorKnob))return false;
 const double Now=FPlatformTime::Seconds();if(ExitDoorActionPending||Now-ExitDoorStateAt>2){UE_LOG(LogTemp,Warning,TEXT("SUB01_EXIT_DOOR_INPUT_REFUSED fresh backend door state required"));return true;}
 // Normal authenticated operator setting; no local fake backend state.
 const bool Open=ExitDoorTarget<.1f;ExitDoorActionPending=true;
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(ExitDoorOrigin+TEXT("/home/controls"));Request->SetVerb(TEXT("POST"));Request->SetTimeout(1.2f);Request->SetHeader(TEXT("X-Admin-Token"),ExitDoorToken);Request->SetHeader(TEXT("Content-Type"),TEXT("application/json"));
 Request->SetContentAsString(Open?TEXT("{\"doors\":{\"front\":\"open\"}}"):TEXT("{\"doors\":{\"front\":\"closed\"}}"));
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){ExitDoorActionPending=false;ExitDoorPollAt=0;if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200)UE_LOG(LogTemp,Warning,TEXT("SUB01_EXIT_DOOR_SETTING_REJECTED actual backend did not accept request"));});
 if(!Request->ProcessRequest())ExitDoorActionPending=false;
 UE_LOG(LogTemp,Display,TEXT("SUB01_EXIT_DOOR_INTERACT actualHit=%s requestedOpen=%d awaiting real published state"),*HitComponent->GetName(),Open?1:0);return true;
}
bool ASub01HomeCharacter::ExitDoorPoseBlocked(float Angle) const{
 if(!ExitDoorLeaf||!ExitDoorKnob||!GetWorld())return true;
 FCollisionQueryParams Query(SCENE_QUERY_STAT(Sub01ExitDoor),false);
 Query.AddIgnoredComponent(ExitDoorLeaf);Query.AddIgnoredComponent(ExitDoorKnob);
 const FVector Hinge(147,390,0);const FQuat Q(FVector::UpVector,FMath::DegreesToRadians(Angle));
 // Keep the player capsule and every other world collider in the query. Never
 // ignore the actor owning imported parts (it may also own walls/frame).
// Actual native floor top is2.5001cm. Original leaf base0 already intersects
 // this fixed floor; probe only its moving footprint above2.55cm. Keep the
 // actual original mesh/collision unchanged, and retain every wall/capsule.
 // Left jamb endsX147.25 while leaf starts147: omit the fixed first4cm
 // hinge-contact collar from the motion probe, rather than ignore that actor.
 // This is a bounded moving-footprint check, not a complete hinge/base contact audit.
 for(int Index=0;Index<2;++Index){const FVector Closed=Index?FVector(241,384,105):FVector(201.5,390,111.275f);
  const FVector Extent=Index?FVector(2.7,2.7,2.7):FVector(50.5,3.75,108.725f);
  if(GetWorld()->OverlapBlockingTestByChannel(Hinge+Q.RotateVector(Closed-Hinge),Q,ECC_Pawn,FCollisionShape::MakeBox(Extent),Query))return true;
 }
 return false;
}
void ASub01HomeCharacter::PollActualExitDoor(){
 if(ExitDoorPollPending||!ExitDoorLeaf)return;ExitDoorPollPending=true;ExitDoorPollAt=FPlatformTime::Seconds()+.5;
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(ExitDoorOrigin+TEXT("/home/state"));Request->SetVerb(TEXT("GET"));Request->SetTimeout(1.2f);Request->SetHeader(TEXT("X-Admin-Token"),ExitDoorToken);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){
  ExitDoorPollPending=false;if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200)return;
  TSharedPtr<FJsonObject> Doc;if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Response->GetContentAsString()),Doc)||!Doc.IsValid())return;
  const TSharedPtr<FJsonObject>* Source=nullptr;const TSharedPtr<FJsonObject>* Doors=nullptr;const TSharedPtr<FJsonObject>* Front=nullptr;FString Status;bool Open=false,Locked=true;
  if(!Doc->TryGetObjectField(TEXT("source"),Source)||!(*Source)->TryGetStringField(TEXT("status"),Status)||Status!=TEXT("live")||!Doc->TryGetObjectField(TEXT("doors"),Doors)||!(*Doors)->TryGetObjectField(TEXT("front"),Front)||!(*Front)->TryGetBoolField(TEXT("open"),Open)||!(*Front)->TryGetBoolField(TEXT("locked"),Locked))return;
  ExitDoorStateAt=FPlatformTime::Seconds();ExitDoorLocked=Locked;ExitDoorTarget=Open&&!Locked?86.4f:0.f;
 });if(!Request->ProcessRequest())ExitDoorPollPending=false;
}
void ASub01HomeCharacter::UpdateActualExitDoor(float DeltaSeconds){
 if(!ExitDoorLeaf||!ExitDoorKnob)return;
 const double Now=FPlatformTime::Seconds();if(Now>=ExitDoorPollAt)PollActualExitDoor();
 if(Now-ExitDoorStateAt>2)return;
 const float Next=float(Sub01ExitDoor::Advance(ExitDoorAngle,ExitDoorTarget,DeltaSeconds,[this](double A){return ExitDoorPoseBlocked(float(A));}));
 if(Next==ExitDoorAngle)return;
 ExitDoorLeaf->SetWorldTransform(ExitDoorPose(ExitDoorClosedLeaf,Next),false,nullptr,ETeleportType::None);
 ExitDoorKnob->SetWorldTransform(ExitDoorPose(ExitDoorClosedKnob,Next),false,nullptr,ETeleportType::None);
 ExitDoorAngle=Next;
}
'''
def install(header, cpp):
    """Call after existing generator runtime adapters; refuse missing hooks."""
    if 'ConfigureActualExitDoor' in cpp:
        raise ValueError('Exit door adapter already installed')
    for marker in [' ConfigureActualPC();',' Super::Tick(DeltaSeconds);',' FString Device;\n']:
        if cpp.count(marker)!=1:raise ValueError('Missing/ambiguous native door hook: '+marker.strip())
    if header.count(' void Forward(float Value);')!=1:raise ValueError('Missing native class hook')
    header=header.replace(' void Forward(float Value);',FIELDS+'\n void Forward(float Value);',1)
    cpp=INCLUDES+cpp
    cpp=cpp.replace(' ConfigureActualPC();',' ConfigureActualPC();\n ConfigureActualExitDoor();',1)
    cpp=cpp.replace(' Super::Tick(DeltaSeconds);',' Super::Tick(DeltaSeconds);\n UpdateActualExitDoor(DeltaSeconds);',1)
    cpp=cpp.replace(' FString Device;\n',' if(TryNativeExitDoor(Hit.GetComponent()))return;\n FString Device;\n',1)
    return header,cpp+METHODS
