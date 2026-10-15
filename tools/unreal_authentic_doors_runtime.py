"""Receipt-gated real multipart doors; absent receipt keeps runtime byte-identical.
Requires actual complete owned76part native import, unique fullsurface/PBR proof.
All sweeps retain the actual pawn, walls and otherdoor collisions. Only members
of the same certified mechanical assembly are excluded from their own motion.
"""
import json,math,re
from pathlib import Path
SHA='5b8a2bb8b4bb8fe19af1d0c086fb78f3e7f9dff9e06170a06642a8f3d1761a0c'
PREFIX='/Game/Sub01Home/AuthenticDoors/V_'+SHA[:12]+'/Attempt_'
RECEIPT='private-audit/authentic-doors-native.json'
GROUP={'entry':0,'bathroom':1,'balcony':2}
FIELDS=r'''
 bool AuthenticDoorPacket=false,AuthenticDoorsBound=false;
 UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> AuthenticDoorMoving;
 UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> AuthenticDoorFixed;
 TArray<int32> AuthenticDoorGroups,AuthenticDoorFixedGroups;
 TArray<FTransform> AuthenticDoorClosed;
 FVector AuthenticDoorCenter[3],AuthenticDoorExtent[3];
 float AuthenticBalconySlide=0,AuthenticBalconyTarget=0;
 mutable double AuthenticDoorBlockedLogAt=0;
 void ConfigureAuthenticDoors();
 bool TryAuthenticDoor(UActorComponent* HitComponent);
 void UpdateAuthenticDoors(float DeltaSeconds);
 bool AuthenticDoorBlocked(int32 Group,float From,float To) const;
 void ApplyAuthenticDoor(int32 Group,float Position);
'''
METHODS=r'''
void ASub01HomeCharacter::ConfigureAuthenticDoors(){
 AuthenticDoorPacket=true;if(AuthenticDoorsBound)return;
 ExitDoorOrigin=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_HOME_ORIGIN"));ExitDoorToken=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN"));
 if(ExitDoorOrigin!=TEXT("http://127.0.0.1:8821")||ExitDoorToken.IsEmpty()){UE_LOG(LogTemp,Error,TEXT("SUB01_AUTHENTIC_DOORS_REFUSED private authenticated statebridge required"));return;}
 struct FExpected{const TCHAR* Mesh;const TCHAR* Tag;int32 Group;bool Moving;FVector Center;FVector Extent;};
 const FExpected Expected[]={
__EXPECTED__
 };
 FVector Lo[3]={FVector(DBL_MAX),FVector(DBL_MAX),FVector(DBL_MAX)};
 FVector Hi[3]={FVector(-DBL_MAX),FVector(-DBL_MAX),FVector(-DBL_MAX)};
 int Counts[3]={0,0,0};
 for(const auto& E:Expected){UStaticMeshComponent* Found=nullptr;int Matches=0;
  for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UStaticMeshComponent*> Parts;It->GetComponents(Parts);for(auto* C:Parts){
   if(!C->GetStaticMesh()||C->GetStaticMesh()->GetPathName()!=E.Mesh)continue;
   if(!C->ComponentHasTag(FName(E.Tag))||!C->IsVisible()||C->GetOwner()->IsHidden()||C->GetCollisionEnabled()==ECollisionEnabled::NoCollision){UE_LOG(LogTemp,Error,TEXT("SUB01_AUTHENTIC_DOORS_REFUSED exact active mesh/tag/collision changed"));return;}
   const auto B=C->CalcBounds(C->GetComponentTransform());if(!B.Origin.Equals(E.Center,.02)||!B.BoxExtent.Equals(E.Extent,.02)){UE_LOG(LogTemp,Error,TEXT("SUB01_AUTHENTIC_DOORS_REFUSED exact saved closedgeometry changed"));return;}
   Found=C;++Matches;
  }}
  if(Matches!=1){UE_LOG(LogTemp,Error,TEXT("SUB01_AUTHENTIC_DOORS_REFUSED nonunique actualcomponent count=%d"),Matches);return;}
  if(E.Moving){AuthenticDoorMoving.Add(Found);AuthenticDoorGroups.Add(E.Group);AuthenticDoorClosed.Add(Found->GetComponentTransform());++Counts[E.Group];Lo[E.Group]=Lo[E.Group].ComponentMin(E.Center-E.Extent);Hi[E.Group]=Hi[E.Group].ComponentMax(E.Center+E.Extent);}
  else{AuthenticDoorFixed.Add(Found);AuthenticDoorFixedGroups.Add(E.Group);}
 }
 if(AuthenticDoorMoving.Num()!=34||AuthenticDoorFixed.Num()!=42||Counts[0]!=23||Counts[1]!=3||Counts[2]!=8){UE_LOG(LogTemp,Error,TEXT("SUB01_AUTHENTIC_DOORS_REFUSED complete34moving/42fixed parts required"));return;}
 for(int32 G=0;G<3;++G){AuthenticDoorCenter[G]=(Lo[G]+Hi[G])*.5;AuthenticDoorExtent[G]=(Hi[G]-Lo[G])*.5;}
 for(int32 I=0;I<AuthenticDoorMoving.Num();++I){auto* C=AuthenticDoorMoving[I].Get();C->SetMobility(EComponentMobility::Movable);
  if(AuthenticDoorGroups[I]==0&&!ExitDoorLeaf){ExitDoorLeaf=C;ExitDoorKnob=C;}
  if(AuthenticDoorGroups[I]==1&&!BathDoorLeaf)BathDoorLeaf=C;
 }
 AuthenticDoorsBound=true;UE_LOG(LogTemp,Display,TEXT("SUB01_AUTHENTIC_DOORS_BOUND actual76parts entry23 bath3 balcony8 hinge154.3,402.2 source5b8a2bb8b4bb nolegacygeometrybinding"));
}
bool ASub01HomeCharacter::TryAuthenticDoor(UActorComponent* HitComponent){
 if(!AuthenticDoorPacket)return false;
 int32 Group=-1;for(int32 I=0;I<AuthenticDoorMoving.Num();++I)if(AuthenticDoorMoving[I].Get()==HitComponent){Group=AuthenticDoorGroups[I];break;}
 if(Group<0)return false;if(!AuthenticDoorsBound)return true;
 const double Now=FPlatformTime::Seconds();if(ExitDoorActionPending||Now-ExitDoorStateAt>2)return true;
 const float Wanted=Group==0?ExitDoorTarget:Group==1?BathDoorWanted:AuthenticBalconyTarget;const bool Open=Wanted<.1f;
 if(Group==1){const FVector P=GetActorLocation();const float Feet=P.Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight();BathDoorEgressRequested=Open&&Sub01ExitDoor::InsideBathroom(P.X,P.Y,Feet)&&!LiveHome;}
 const TCHAR* Key=Group==0?TEXT("front"):Group==1?TEXT("bathroom"):TEXT("balcony");
 ExitDoorActionPending=true;auto R=FHttpModule::Get().CreateRequest();R->SetURL(ExitDoorOrigin+TEXT("/home/controls"));R->SetVerb(TEXT("POST"));R->SetTimeout(1.2f);R->SetHeader(TEXT("X-Admin-Token"),ExitDoorToken);R->SetHeader(TEXT("Content-Type"),TEXT("application/json"));R->SetContentAsString(FString::Printf(TEXT("{\"doors\":{\"%s\":\"%s\"}}"),Key,Open?TEXT("open"):TEXT("closed")));
 R->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){ExitDoorActionPending=false;ExitDoorPollAt=0;if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200)UE_LOG(LogTemp,Warning,TEXT("SUB01_AUTHENTIC_DOOR_BACKEND_REFUSED"));});if(!R->ProcessRequest())ExitDoorActionPending=false;
 UE_LOG(LogTemp,Display,TEXT("SUB01_AUTHENTIC_DOOR_PHYSICAL_E group=%d requestOpen=%d actualHit=%s"),Group,Open?1:0,*HitComponent->GetName());return true;
}
bool ASub01HomeCharacter::AuthenticDoorBlocked(int32 Group,float From,float To) const{
 if(!AuthenticDoorsBound||!GetWorld()||Group<0||Group>2)return true;
 FCollisionQueryParams Q(SCENE_QUERY_STAT(Sub01AuthenticDoor),false);
 // These are the exact measured moving leaf+hinges/track/frame of THIS door.
 // Real pawn, architecture, furniture and all other mechanical groups remain.
 for(int32 I=0;I<AuthenticDoorMoving.Num();++I)if(AuthenticDoorGroups[I]==Group)Q.AddIgnoredComponent(AuthenticDoorMoving[I].Get());
 for(int32 I=0;I<AuthenticDoorFixed.Num();++I)if(AuthenticDoorFixedGroups[I]==Group)Q.AddIgnoredComponent(AuthenticDoorFixed[I].Get());
 FVector Center=AuthenticDoorCenter[Group],Extent=AuthenticDoorExtent[Group];FQuat Rotation=FQuat::Identity;
 if(Group==0){const FVector Pivot(154.3,402.2,2.5);const float Middle=(From+To)*.5f;Rotation=FQuat(FVector::UpVector,FMath::DegreesToRadians(Middle));Center=Pivot+Rotation.RotateVector(Center-Pivot);
  // Bounding every corner over the complete arc, not sampling endpoints only:
  // distance from any midpoint corner <= radius*halfAngle for each arc segment.
  const FVector Offset=AuthenticDoorCenter[0]-Pivot;const float Radius=FMath::Sqrt(FMath::Square(FMath::Abs(Offset.X)+AuthenticDoorExtent[0].X)+FMath::Square(FMath::Abs(Offset.Y)+AuthenticDoorExtent[0].Y));const float Expand=Radius*FMath::Abs(FMath::DegreesToRadians(To-From))*.5f+.0001f;Extent.X+=Expand;Extent.Y+=Expand;
 }else{const FVector Axis=Group==1?FVector(0,1,0):FVector(1,0,0);Center+=Axis*((From+To)*.5f);Extent+=Axis*(FMath::Abs(To-From)*.5f);}
 const bool Blocked=GetWorld()->OverlapBlockingTestByChannel(Center,Rotation,ECC_Pawn,FCollisionShape::MakeBox(Extent),Q);
 const double Now=FPlatformTime::Seconds();if(Blocked&&Now-AuthenticDoorBlockedLogAt>1){AuthenticDoorBlockedLogAt=Now;UE_LOG(LogTemp,Display,TEXT("SUB01_AUTHENTIC_DOOR_BLOCKED group=%d from=%.5f to=%.5f realPawnAndWallsRetained=1"),Group,From,To);}return Blocked;
}
void ASub01HomeCharacter::ApplyAuthenticDoor(int32 Group,float Position){
 const FVector Pivot(154.3,402.2,2.5);const FQuat Rotation(FVector::UpVector,FMath::DegreesToRadians(Position));
 for(int32 I=0;I<AuthenticDoorMoving.Num();++I){if(AuthenticDoorGroups[I]!=Group)continue;FTransform Pose=AuthenticDoorClosed[I];
  if(Group==0){Pose.SetTranslation(Pivot+Rotation.RotateVector(Pose.GetTranslation()-Pivot));Pose.SetRotation(Rotation*Pose.GetRotation());}
  else Pose.AddToTranslation(Group==1?FVector(0,Position,0):FVector(Position,0,0));
  AuthenticDoorMoving[I]->SetWorldTransform(Pose,false,nullptr,ETeleportType::None);
 }
}
void ASub01HomeCharacter::UpdateAuthenticDoors(float DeltaSeconds){
 if(!AuthenticDoorsBound)return;const double Now=FPlatformTime::Seconds();if(Now>=ExitDoorPollAt)PollActualExitDoor();if(Now-ExitDoorStateAt>2)return;
 const bool LiveEdge=LiveHome&&LiveHomeFresh&&!LiveHomeBlocked&&LiveHomePath.Num()>0&&((LiveHomeNode==TEXT("bath_door")&&LiveHomePath[0]==TEXT("bathroom"))||(LiveHomeNode==TEXT("bathroom")&&LiveHomePath[0]==TEXT("bath_door")));
 if(GetActorLocation().X>-56.7||LiveHome)BathDoorEgressRequested=false;BathDoorWanted=LiveEdge||BathDoorEgressRequested?95.f:BathDoorBackendTarget;
 float Previous=ExitDoorAngle;const float Entry=float(Sub01ExitDoor::Advance(ExitDoorAngle,ExitDoorTarget,DeltaSeconds,[this,&Previous](double To){const bool B=AuthenticDoorBlocked(0,Previous,float(To));Previous=float(To);return B;}));
 const float Bath=float(Sub01ExitDoor::AdvanceSlide(BathDoorSlide,BathDoorWanted,DeltaSeconds,[this](double A,double B){return AuthenticDoorBlocked(1,float(A),float(B));}));
 const float Balcony=float(Sub01ExitDoor::AdvanceSlide(AuthenticBalconySlide,AuthenticBalconyTarget,DeltaSeconds,[this](double A,double B){return AuthenticDoorBlocked(2,float(A),float(B));}));
 if(Entry!=ExitDoorAngle){ApplyAuthenticDoor(0,Entry);ExitDoorAngle=Entry;}
 if(Bath!=BathDoorSlide){ApplyAuthenticDoor(1,Bath);BathDoorSlide=Bath;}
 if(Balcony!=AuthenticBalconySlide){ApplyAuthenticDoor(2,Balcony);AuthenticBalconySlide=Balcony;}
}
'''

def receipt_profile(project):
 p=Path(project)/RECEIPT
 if not p.exists():return None
 if p.is_symlink()or p.stat().st_size>500000:raise ValueError('Bounded actualdoor receipt required')
 r=json.loads(p.read_text());parts=r.get('parts',[])
 if r.get('schema')!='sub01.authentic-doors-native.v1'or r.get('source_sha256')!=SHA or r.get('saved')is not True or r.get('originals_preserved')is not True or r.get('protected_originals_unchanged')is not True or len(parts)!=76 or not r.get('owned_destination','').startswith(PREFIX):raise ValueError('Actual saved complete realdoor receipt required')
 paths=set();names=set();counts={k:0 for k in GROUP}
 for row in parts:
  if not re.fullmatch(r'SUB01_AuthenticDoor_\d{3}',row.get('name',''))or row['name']in names or not row.get('mesh','').startswith(r['owned_destination']+'/')or row['mesh']in paths or row.get('full_source_geometry_verified')is not True or row.get('assembly')not in GROUP:raise ValueError('Exact uniqueactualdoor component proof required')
  names.add(row['name']);paths.add(row['mesh'])
  if row.get('moving_group'):
   if row['moving_group']not in GROUP or row['moving_group']!=row['assembly']:raise ValueError('Unknown or cross-assembly movingdoor role')
   counts[row['moving_group']]+=1
  for field in ('world_center_cm','world_extent_cm'):
   v=row.get(field,[])
   if len(v)!=3 or any(not isinstance(x,(int,float))or not math.isfinite(x)or abs(x)>2000 for x in v)or(field=='world_extent_cm'and any(x<=0 for x in v)):raise ValueError('Finite nondegenerate actualclosed doorbounds required')
 if counts!={'entry':23,'bathroom':3,'balcony':8}:raise ValueError('Complete actualdoor movinggroups required')
 return r

def install(header,cpp,project):
 r=receipt_profile(project)
 if r is None:return header,cpp
 if 'AuthenticDoorPacket'in header:raise ValueError('Actualrealdoor runtime alreadyinstalled')
 replacements={
 ' void Forward(float Value);':FIELDS+'\n void Forward(float Value);',
 }
 for before,after in replacements.items():
  if header.count(before)!=1:raise ValueError('Unique nativeclass insertion required')
  header=header.replace(before,after,1)
 hooks={
 ' ConfigureActualExitDoor();':' ConfigureAuthenticDoors();\n ConfigureActualExitDoor();',
 ' UpdateActualExitDoor(DeltaSeconds);':' UpdateAuthenticDoors(DeltaSeconds);\n UpdateActualExitDoor(DeltaSeconds);',
 ' if(TryNativeExitDoor(Hit.GetComponent()))return;':' if(TryAuthenticDoor(Hit.GetComponent()))return;\n if(TryNativeExitDoor(Hit.GetComponent()))return;',
 'void ASub01HomeCharacter::ConfigureActualExitDoor(){':'void ASub01HomeCharacter::ConfigureActualExitDoor(){\n if(AuthenticDoorPacket)return;',
 'void ASub01HomeCharacter::ConfigureActualBathroomDoor(){':'void ASub01HomeCharacter::ConfigureActualBathroomDoor(){\n if(AuthenticDoorPacket)return;',
 'void ASub01HomeCharacter::UpdateActualExitDoor(float DeltaSeconds){':'void ASub01HomeCharacter::UpdateActualExitDoor(float DeltaSeconds){\n if(AuthenticDoorPacket)return;',
 'void ASub01HomeCharacter::UpdateActualBathroomDoor(float DeltaSeconds){':'void ASub01HomeCharacter::UpdateActualBathroomDoor(float DeltaSeconds){\n if(AuthenticDoorPacket)return;',
 '  BathDoorLocked=BathLocked;BathDoorBackendTarget=BathOpen&&!BathLocked?95.f:0.f;':'  BathDoorLocked=BathLocked;BathDoorBackendTarget=BathOpen&&!BathLocked?95.f:0.f;\n  const TSharedPtr<FJsonObject>* Balcony=nullptr;bool BalconyOpen=false,BalconyLocked=true;AuthenticBalconyTarget=((*Doors)->TryGetObjectField(TEXT("balcony"),Balcony)&&(*Balcony)->TryGetBoolField(TEXT("open"),BalconyOpen)&&(*Balcony)->TryGetBoolField(TEXT("locked"),BalconyLocked)&&BalconyOpen&&!BalconyLocked)?91.f:0.f;',
 }
 for before,after in hooks.items():
  if cpp.count(before)!=1:raise ValueError('Missingambiguous realdoor hook '+before[:100])
  cpp=cpp.replace(before,after,1)
 def vec(v):return 'FVector('+','.join(format(float(x),'.9f')for x in v)+')'
 rows=[]
 for p in r['parts']:
  moving=p.get('moving_group');role=moving or p['assembly'];tag='SUB01AuthenticDoors:'+SHA+(':'+'moving:'+role if moving else':fixed:'+role)
  rows.append('  {TEXT('+json.dumps(p['mesh'])+'),TEXT('+json.dumps(tag)+'),'+str(GROUP[role])+','+('true'if moving else'false')+','+vec(p['world_center_cm'])+','+vec(p['world_extent_cm'])+'},')
 cpp='#include <cfloat>\n'+cpp
 cpp+='\n'+METHODS.replace('__EXPECTED__','\n'.join(rows));return header,cpp
