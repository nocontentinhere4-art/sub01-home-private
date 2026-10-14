"""Actual imported front-door hinge motion; generator owner installs this adapter.

Exact geometry: current full-home.glb nodes58/59, meshes43/44. UE centimetres are
100*(glTF x,z,y). Binding refuses missing/ambiguous geometry. This only moves
those existing collidable components; it does not create a door/outdoor world.
"""
CURRENT_SOURCE_SHA256 = '9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
GEOMETRY = {'leaf': {'node':58,'mesh':43,'center_cm':(199.5,390.,110.),'extent_cm':(52.5,3.75,110.)},
            'knob': {'node':59,'mesh':44,'center_cm':(241.,384.,105.),'extent_cm':(2.7,2.7,2.7)},
            'hinge_cm':(147.,390.,0.), 'verified_entry_floor_cm':2.5001,  'tag':'SUB01Door:Front'}
FITTED_GEOMETRY = {'leaf_center_cm':(199.95,390.,111.85),'leaf_extent_cm':(52.5,3.75,109.25),
                   'knob_center_cm':(241.45,384.,107.6),'hinge_cm':(147.45,394.,2.6),
                   'leaf_vertical_scale':218.5/220, 'floor_clearance_cm':.0999,
                   'header_clearance_cm':.15, 'left_jamb_clearance_cm':.20,
                   'right_jamb_clearance_cm':.30,
                   'review':'Explicit physical fitting to measured floor/header/jamb; native audit pending'}
BATH_GEOMETRY={'node':118,'mesh':101,'center_cm':(-85.,135.,405.),'extent_cm':(3.25,44.5,100.),
               'fitted_center_cm':(-73.8,135.,405.),'slide_cm':95.,'floor_top_cm':302.50013071525075,
               'floor_clearance_cm':2.49986928474925,'skirting_clearance_cm':.20,
               'backwall_clearance_cm':.45,'header_lateral_clearance_cm':2.95,
               'tag':'SUB01Door:Bathroom','hardware':'No separate handle/track in actual full-home source'}
# Engine-independent actual stepping policy, compiled/executed by the tests.
POLICY = r'''
#include <cmath>
namespace Sub01ExitDoor {
inline constexpr double MaxArcDegrees=.25;
inline bool InsideBathroom(double x,double y,double feet){return x<-85&&x>-378&&y>50&&y<270&&feet>280&&feet<350;}
template<class Blocked> double AdvanceSlide(double position,double target,double dt,Blocked blocked){
 if(!std::isfinite(position)||!std::isfinite(target)||!std::isfinite(dt)||dt<=0)return position;
 target=std::fmax(0.0,std::fmin(95.0,target));
 const double distance=std::fmin(std::fabs(target-position),90.0*std::fmin(dt,.05));
 const double next=position+(target>position?distance:-distance);
 return distance==0||blocked(position,next)?position:next;
}

template<class Blocked> double Advance(double angle,double target,double dt,Blocked blocked){
 if(!std::isfinite(angle)||!std::isfinite(target)||!std::isfinite(dt)||dt<=0)return angle;
 target=std::fmax(0.0,std::fmin(86.4,target));
 const double distance=std::fmin(std::fabs(target-angle),70.0*std::fmin(dt,0.05));
 const int steps=int(std::ceil(distance/MaxArcDegrees));if(!steps)return angle;
 const double direction=target>angle?1.0:-1.0;
 // Test every intermediate pose before committing any motion this tick.
 for(int i=1;i<=steps;++i)if(blocked(angle+direction*distance*i/steps))return angle;
 return angle+direction*distance;
}
}
'''
INCLUDES = r'''
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
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
 UPROPERTY() TObjectPtr<UStaticMeshComponent> BathDoorLeaf;
 FTransform BathDoorClosed;float BathDoorSlide=0,BathDoorBackendTarget=0,BathDoorWanted=0;
 bool BathDoorLocked=true,BathDoorEgressRequested=false;
 void ConfigureActualBathroomDoor();
 bool TryNativeBathroomDoor(UActorComponent* HitComponent);
 bool BathDoorSweepBlocked(float From,float To) const;
 void UpdateActualBathroomDoor(float DeltaSeconds);
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
 mutable double ExitDoorBlockLogAt=0;
 bool ExitDoorSweepBlocked(float From,float To) const;
 FTransform ExitDoorPose(const FTransform& Closed,float Angle) const;
'''
METHODS = r'''
#include "Engine/OverlapResult.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
FTransform ASub01HomeCharacter::ExitDoorPose(const FTransform& Closed,float Angle) const{
 const FVector Hinge(147.45f,394,2.6f);const FQuat Swing(FVector::UpVector,FMath::DegreesToRadians(Angle));
 return FTransform(Swing*Closed.GetRotation(),Hinge+Swing.RotateVector(Closed.GetLocation()-Hinge),Closed.GetScale3D());
}
void ASub01HomeCharacter::ConfigureActualExitDoor(){
 if(ExitDoorLeaf||ExitDoorKnob)return;
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
 // Fit once from original imported transforms; repeated setup refuses because
 // its original bounds no longer match. Existing material and IDs are retained.
 if(!Leaf->GetComponentQuat().Equals(FQuat::Identity,.001f)){UE_LOG(LogTemp,Error,TEXT("SUB01_EXIT_DOOR_REFUSED imported local axes require separate fitting audit"));return;}
 Leaf->SetMobility(EComponentMobility::Movable);Knob->SetMobility(EComponentMobility::Movable);
 ExitDoorLeaf=Leaf;ExitDoorKnob=Knob;
 const auto BeforeLeaf=Leaf->CalcBounds(Leaf->GetComponentTransform());const auto BeforeKnob=Knob->CalcBounds(Knob->GetComponentTransform());
 ExitDoorClosedLeaf=Leaf->GetComponentTransform();ExitDoorClosedKnob=Knob->GetComponentTransform();
 FVector Scale=ExitDoorClosedLeaf.GetScale3D();Scale.Z*=218.5f/220.f;ExitDoorClosedLeaf.SetScale3D(Scale);
 ExitDoorClosedLeaf.AddToTranslation(FVector(.45f,0,1.85f));ExitDoorClosedKnob.AddToTranslation(FVector(.45f,0,2.6f));
 Leaf->SetWorldTransform(ExitDoorClosedLeaf,false,nullptr,ETeleportType::None);Knob->SetWorldTransform(ExitDoorClosedKnob,false,nullptr,ETeleportType::None);
 for(auto* C:{Leaf,Knob}){C->SetMobility(EComponentMobility::Movable);C->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);C->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);C->SetCollisionResponseToChannel(ECC_Visibility,ECR_Block);C->ComponentTags.AddUnique(TEXT("SUB01Door:Front"));}
 const auto AfterLeaf=Leaf->CalcBounds(Leaf->GetComponentTransform());const auto AfterKnob=Knob->CalcBounds(Knob->GetComponentTransform());
 UE_LOG(LogTemp,Display,TEXT("SUB01_EXIT_DOOR_ACTUAL_FIT beforeCenter=%s beforeExtent=%s afterCenter=%s afterExtent=%s knobBefore=%s knobAfter=%s"),*BeforeLeaf.Origin.ToString(),*BeforeLeaf.BoxExtent.ToString(),*AfterLeaf.Origin.ToString(),*AfterLeaf.BoxExtent.ToString(),*BeforeKnob.Origin.ToString(),*AfterKnob.Origin.ToString());
 UE_LOG(LogTemp,Display,TEXT("SUB01_EXIT_DOOR_BOUND leaf=%s knob=%s hinge=147.45,394,2.6 physicalFit leafDelta=.45,0,1.85 leafZScale=.9931818 knobDelta=.45,0,2.6"),*Leaf->GetName(),*Knob->GetName());
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
bool ASub01HomeCharacter::ExitDoorSweepBlocked(float From,float To) const{
 if(!ExitDoorLeaf||!ExitDoorKnob||!GetWorld())return true;
 FCollisionQueryParams Query(SCENE_QUERY_STAT(Sub01ExitDoor),false);
 Query.AddIgnoredComponent(ExitDoorLeaf.Get());Query.AddIgnoredComponent(ExitDoorKnob.Get());
 const FVector Hinge(147.45f,394,2.6f);const FQuat Mid(FVector::UpVector,FMath::DegreesToRadians((From+To)*.5f));
 const FQuat First(FVector::UpVector,FMath::DegreesToRadians(From)),Last(FVector::UpVector,FMath::DegreesToRadians(To));
 // Complete leaf/knob swept hull: endpoint corners in midpoint axes plus the
 // circular-arc sagitta bound enclose every point between both poses.
 for(int Index=0;Index<2;++Index){const FVector Closed=Index?FVector(241.45f,384,107.6f):FVector(199.95f,390,111.85f);
  const FVector Extent=Index?FVector(2.7,2.7,2.7):FVector(52.5,3.75,109.25f);FBox Hull(ForceInit);float Radius=0;
  for(float X:{-1.f,1.f})for(float Y:{-1.f,1.f})for(float Z:{-1.f,1.f}){
   const FVector P=Closed-Hinge+FVector(X*Extent.X,Y*Extent.Y,Z*Extent.Z);Radius=FMath::Max(Radius,float(FVector2D(P.X,P.Y).Size()));
   Hull+=Mid.UnrotateVector(First.RotateVector(P));Hull+=Mid.UnrotateVector(Last.RotateVector(P));
  }
  const float Sag=Radius*(1.f-FMath::Cos(FMath::DegreesToRadians(FMath::Abs(To-From)*.5f)));
  const FVector SweepExtent=Hull.GetExtent()+FVector(Sag,Sag,0);
  TArray<FOverlapResult> Overlaps;GetWorld()->OverlapMultiByChannel(Overlaps,Hinge+Mid.RotateVector(Hull.GetCenter()),Mid,ECC_Pawn,FCollisionShape::MakeBox(SweepExtent),Query);
  for(const auto& Hit:Overlaps)if(Hit.bBlockingHit){
   const double Now=FPlatformTime::Seconds();if(Now-ExitDoorBlockLogAt>2){ExitDoorBlockLogAt=Now;auto* Component=Hit.GetComponent();FVector Center=FVector::ZeroVector,Extent=FVector::ZeroVector;int Trace=-1,Convex=-1,Boxes=-1;
    if(Component){const auto B=Component->CalcBounds(Component->GetComponentTransform());Center=B.Origin;Extent=B.BoxExtent;if(auto* Mesh=Cast<UStaticMeshComponent>(Component))if(Mesh->GetStaticMesh())if(auto* Body=Mesh->GetStaticMesh()->GetBodySetup()){Trace=int(Body->CollisionTraceFlag);Convex=Body->AggGeom.ConvexElems.Num();Boxes=Body->AggGeom.BoxElems.Num();}}
    UE_LOG(LogTemp,Warning,TEXT("SUB01_EXIT_DOOR_ACTUAL_BLOCKED angle=%.4f->%.4f part=%d component=%s center=%s extent=%s trace=%d convex=%d boxes=%d; collision retained"),From,To,Index,*GetPathNameSafe(Component),*Center.ToString(),*Extent.ToString(),Trace,Convex,Boxes);
   }return true;
  }
 }
 return false;
}
void ASub01HomeCharacter::PollActualExitDoor(){
 if(ExitDoorPollPending||(!ExitDoorLeaf&&!BathDoorLeaf))return;ExitDoorPollPending=true;ExitDoorPollAt=FPlatformTime::Seconds()+.5;
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(ExitDoorOrigin+TEXT("/home/state"));Request->SetVerb(TEXT("GET"));Request->SetTimeout(1.2f);Request->SetHeader(TEXT("X-Admin-Token"),ExitDoorToken);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){
  ExitDoorPollPending=false;if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200)return;
  TSharedPtr<FJsonObject> Doc;if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Response->GetContentAsString()),Doc)||!Doc.IsValid())return;
  const TSharedPtr<FJsonObject>* Source=nullptr;const TSharedPtr<FJsonObject>* Doors=nullptr;const TSharedPtr<FJsonObject>* Front=nullptr;FString Status;bool Open=false,Locked=true;
  if(!Doc->TryGetObjectField(TEXT("source"),Source)||!(*Source)->TryGetStringField(TEXT("status"),Status)||Status!=TEXT("live")||!Doc->TryGetObjectField(TEXT("doors"),Doors)||!(*Doors)->TryGetObjectField(TEXT("front"),Front)||!(*Front)->TryGetBoolField(TEXT("open"),Open)||!(*Front)->TryGetBoolField(TEXT("locked"),Locked))return;
  const TSharedPtr<FJsonObject>* Bath=nullptr;bool BathOpen=false,BathLocked=true;
  if(!(*Doors)->TryGetObjectField(TEXT("bathroom"),Bath)||!(*Bath)->TryGetBoolField(TEXT("open"),BathOpen)||!(*Bath)->TryGetBoolField(TEXT("locked"),BathLocked))return;
  ExitDoorStateAt=FPlatformTime::Seconds();ExitDoorLocked=Locked;ExitDoorTarget=Open&&!Locked?86.4f:0.f;
  BathDoorLocked=BathLocked;BathDoorBackendTarget=BathOpen&&!BathLocked?95.f:0.f;
 });if(!Request->ProcessRequest())ExitDoorPollPending=false;
}
void ASub01HomeCharacter::UpdateActualExitDoor(float DeltaSeconds){
 if(!ExitDoorLeaf||!ExitDoorKnob)return;
 const double Now=FPlatformTime::Seconds();if(Now>=ExitDoorPollAt)PollActualExitDoor();
 if(Now-ExitDoorStateAt>2)return;
 float Previous=ExitDoorAngle;
 const float Next=float(Sub01ExitDoor::Advance(ExitDoorAngle,ExitDoorTarget,DeltaSeconds,[this,&Previous](double A){const bool Blocked=ExitDoorSweepBlocked(Previous,float(A));Previous=float(A);return Blocked;}));
 if(Next==ExitDoorAngle)return;
 ExitDoorLeaf->SetWorldTransform(ExitDoorPose(ExitDoorClosedLeaf,Next),false,nullptr,ETeleportType::None);
 ExitDoorKnob->SetWorldTransform(ExitDoorPose(ExitDoorClosedKnob,Next),false,nullptr,ETeleportType::None);
 ExitDoorAngle=Next;
}
'''
 
BATH_METHODS = r'''
void ASub01HomeCharacter::ConfigureActualBathroomDoor(){
 if(BathDoorLeaf)return;UStaticMeshComponent* Panel=nullptr;int Matches=0;
 for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UStaticMeshComponent*> Parts;It->GetComponents(Parts);for(auto* C:Parts){
  if(!C->GetStaticMesh())continue;const auto B=C->CalcBounds(C->GetComponentTransform());
  if(FVector::Dist(B.Origin,FVector(-85,135,405))<.2&&FVector::Dist(B.BoxExtent,FVector(3.25,44.5,100))<.2){Panel=C;++Matches;}
 }}
 if(Matches!=1){UE_LOG(LogTemp,Error,TEXT("SUB01_BATH_DOOR_REFUSED unique actual panel required matches=%d"),Matches);return;}
 ExitDoorOrigin=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_HOME_ORIGIN"));ExitDoorToken=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN"));
 if(ExitDoorOrigin!=TEXT("http://127.0.0.1:8821")||ExitDoorToken.IsEmpty())return;
 const auto Before=Panel->CalcBounds(Panel->GetComponentTransform());
 BathDoorLeaf=Panel;BathDoorClosed=Panel->GetComponentTransform();BathDoorClosed.AddToTranslation(FVector(11.2f,0,0));
 Panel->SetMobility(EComponentMobility::Movable);Panel->SetWorldTransform(BathDoorClosed,false,nullptr,ETeleportType::None);
 Panel->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);Panel->SetCollisionResponseToChannel(ECC_Pawn,ECR_Block);Panel->SetCollisionResponseToChannel(ECC_Visibility,ECR_Block);Panel->ComponentTags.AddUnique(TEXT("SUB01Door:Bathroom"));
 const auto After=Panel->CalcBounds(Panel->GetComponentTransform());
 UE_LOG(LogTemp,Display,TEXT("SUB01_BATH_DOOR_ACTUAL_FIT beforeCenter=%s beforeExtent=%s afterCenter=%s afterExtent=%s originalSizeRetained corridorFloor302.50013 bathFloor305.25001"),*Before.Origin.ToString(),*Before.BoxExtent.ToString(),*After.Origin.ToString(),*After.BoxExtent.ToString());
 UE_LOG(LogTemp,Display,TEXT("SUB01_BATH_DOOR_BOUND component=%s source9556495f node118/Mesh101 absoluteDelta=11.2,0,0 fullsize=6.5,89,200 slide=0..95; no invented track or handle"),*Panel->GetName());
}
bool ASub01HomeCharacter::TryNativeBathroomDoor(UActorComponent* HitComponent){
 if(!BathDoorLeaf||HitComponent!=BathDoorLeaf)return false;const double Now=FPlatformTime::Seconds();
 if(ExitDoorActionPending||Now-ExitDoorStateAt>2)return true;
 const FVector P=GetActorLocation();const float Feet=P.Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 const bool Inside=Sub01ExitDoor::InsideBathroom(P.X,P.Y,Feet);
 const bool Open=BathDoorWanted<.1f;BathDoorEgressRequested=Open&&Inside&&!LiveHome;
 ExitDoorActionPending=true;auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(ExitDoorOrigin+TEXT("/home/controls"));Request->SetVerb(TEXT("POST"));Request->SetTimeout(1.2f);Request->SetHeader(TEXT("X-Admin-Token"),ExitDoorToken);Request->SetHeader(TEXT("Content-Type"),TEXT("application/json"));
 Request->SetContentAsString(Open?TEXT("{\"doors\":{\"bathroom\":\"open\"}}"):TEXT("{\"doors\":{\"bathroom\":\"closed\"}}"));
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){ExitDoorActionPending=false;ExitDoorPollAt=0;if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200)UE_LOG(LogTemp,Warning,TEXT("SUB01_BATH_DOOR_SETTING_REJECTED"));});
 if(!Request->ProcessRequest())ExitDoorActionPending=false;
 UE_LOG(LogTemp,Display,TEXT("SUB01_BATH_DOOR_INTERACT actualHit=%s requestedOpen=%d realInsideEgress=%d privacy unchanged"),*HitComponent->GetName(),Open?1:0,BathDoorEgressRequested?1:0);return true;
}
bool ASub01HomeCharacter::BathDoorSweepBlocked(float From,float To) const{
 if(!BathDoorLeaf||!GetWorld())return true;FCollisionQueryParams Query(SCENE_QUERY_STAT(Sub01BathDoor),false);Query.AddIgnoredComponent(BathDoorLeaf.Get());
 // Exact full linear swept panel, with every capsule/structural collider retained.
 return GetWorld()->OverlapBlockingTestByChannel(FVector(-73.8f,135+(From+To)*.5f,405),FQuat::Identity,ECC_Pawn,FCollisionShape::MakeBox(FVector(3.25f,44.5f+FMath::Abs(To-From)*.5f,100)),Query);
}
void ASub01HomeCharacter::UpdateActualBathroomDoor(float DeltaSeconds){
 if(!BathDoorLeaf)return;const double Now=FPlatformTime::Seconds();if(Now>=ExitDoorPollAt)PollActualExitDoor();if(Now-ExitDoorStateAt>2)return;
 const bool LiveEdge=LiveHome&&LiveHomeFresh&&!LiveHomeBlocked&&LiveHomePath.Num()>0&&
  ((LiveHomeNode==TEXT("bath_door")&&LiveHomePath[0]==TEXT("bathroom"))||(LiveHomeNode==TEXT("bathroom")&&LiveHomePath[0]==TEXT("bath_door")));
 const FVector P=GetActorLocation();if(P.X>-50||LiveHome)BathDoorEgressRequested=false;
 // A fresh authenticated real route opens for its physical crossing before
 // model occupancy closes it. It never changes privacy or reports arrival.
 // Explicit manual egress is granted only from a measured inside-side capsule.
 BathDoorWanted=LiveEdge||BathDoorEgressRequested?95.f:BathDoorBackendTarget;
 const float Next=float(Sub01ExitDoor::AdvanceSlide(BathDoorSlide,BathDoorWanted,DeltaSeconds,[this](double A,double B){return BathDoorSweepBlocked(float(A),float(B));}));
 if(Next==BathDoorSlide)return;FTransform Pose=BathDoorClosed;Pose.AddToTranslation(FVector(0,Next,0));BathDoorLeaf->SetWorldTransform(Pose,false,nullptr,ETeleportType::None);BathDoorSlide=Next;
}
'''

def install(header, cpp):
    """Call after existing generator runtime adapters; refuse missing hooks."""
    if 'ConfigureActualExitDoor' in cpp:
        raise ValueError('Exit door adapter already installed')
    for marker in [' ConfigureActualPC();',' Super::Tick(DeltaSeconds);',' FString Device;\n']:
        if cpp.count(marker)!=1:raise ValueError('Missing/ambiguous native door hook: '+marker.strip())
    if header.count(' void Forward(float Value);')!=1:raise ValueError('Missing native class hook')
    if 'class UStaticMeshComponent;' not in header:
        header=header.replace('#include "Sub01HomeLab.generated.h"','#include "Sub01HomeLab.generated.h"\nclass UStaticMeshComponent;',1) if '#include "Sub01HomeLab.generated.h"' in header else 'class UStaticMeshComponent;\n'+header
    header=header.replace(' void Forward(float Value);',FIELDS+'\n void Forward(float Value);',1)
    cpp=INCLUDES+cpp

    cpp=cpp.replace(' ConfigureActualPC();',' ConfigureActualPC();\n ConfigureActualExitDoor();\n ConfigureActualBathroomDoor();',1)
    cpp=cpp.replace(' Super::Tick(DeltaSeconds);',' Super::Tick(DeltaSeconds);\n UpdateActualExitDoor(DeltaSeconds);\n UpdateActualBathroomDoor(DeltaSeconds);',1)
    cpp=cpp.replace(' FString Device;\n',' if(TryNativeExitDoor(Hit.GetComponent()))return;\n if(TryNativeBathroomDoor(Hit.GetComponent()))return;\n FString Device;\n',1)
    return header,cpp+METHODS+BATH_METHODS
