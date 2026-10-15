"""Explicit owned-arms visual review at the real desk, with the camera retained.

The reviewer first walks physically to the desk. Only a separate visual component
uses the declared source placement. The pawn, original owner mesh and normal
camera/body offsets remain untouched. This cannot grant typing or seat readiness.
"""

FIELDS=r'''
 UPROPERTY() TObjectPtr<USkeletalMeshComponent> FPSKeyboardReviewArms;
 bool FPSKeyboardVisualReview=false,FPSKeyboardOwnerVisible=false;
 UFUNCTION(Exec) void ReviewFPSKeyboard(bool Play);
'''

METHODS=r'''
void ASub01HomeCharacter::ReviewFPSKeyboard(bool Play){
 auto Refuse=[](const TCHAR* Why){UE_LOG(LogTemp,Warning,TEXT("SUB01_FPS_KEYBOARD_REVIEW_REFUSED %s"),Why);};
 const double Now=FPlatformTime::Seconds();
 if(PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||HandsDiagnostic||NativeSeatVerified||MinecraftFocused||ControllerPlayActive||
    (PCBridge&&PCBridge->HasOperatorFocus())||!FirstPersonBody||!ViewCamera||NativePrivacyLast||Now-NativePrivacyPublishedAt>.5||
    !GetCharacterMovement()->IsMovingOnGround()||GetVelocity().Size()>1){Refuse(TEXT("stationary physically public manual desk approach required"));return;}
 const FVector Pawn=GetActorLocation(),Eye=ViewCamera->GetComponentLocation();
 if(Pawn.ContainsNaN()||Eye.ContainsNaN()||Pawn.Z<90||Pawn.Z>110||FVector2D::Distance(FVector2D(Pawn.X,Pawn.Y),FVector2D(230,-295))>200){Refuse(TEXT("physically reachable ground-floor desk vicinity required; no placement"));return;}
 auto* Owner=FirstPersonBody->GetSkeletalMeshAsset();
 if(!Owner||Owner->GetPathName()!=TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner")||!Owner->GetSkeleton()){Refuse(TEXT("actual immutable original owner required"));return;}
 FString Raw;TSharedPtr<FJsonObject> R;
 if(!FFileHelper::LoadFileToString(Raw,*FPaths::Combine(FPaths::ProjectDir(),TEXT("unreal-fp-keyboard-review-import.json")))||
    !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),R)||!R.IsValid()){Refuse(TEXT("actual owned review import receipt required"));return;}
 FString Schema,FBX,SourceMesh,SourceClip,MeshPath,ClipPath,SkeletonPath,MaterialPath,Slot;double Keys=0,Rate=0,Duration=0;bool Original=false,World=false,Native=false,Activity=false;
 if(!R->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("sub01.unreal-fp-keyboard-review-import.v1")||
    !R->TryGetStringField(TEXT("fbx_sha256"),FBX)||FBX!=TEXT("07baf00adbe6e9fa49f22ea954787e3590ba602a5c7ab6f247cc990a50205d53")||
    !R->TryGetStringField(TEXT("arms_mesh_sha256"),SourceMesh)||SourceMesh!=TEXT("a862cbd3457c2b25da227c0eea2e04dcd8fe1f637115da0ccc69fbcf888ad154")||
    !R->TryGetStringField(TEXT("derived_clip_sha256"),SourceClip)||SourceClip!=TEXT("0cd1395b0b1d8187c928aeb93950df69abc67f7eeefa91ed1df58c1ea761f5db")||
    !R->TryGetStringField(TEXT("mesh"),MeshPath)||!R->TryGetStringField(TEXT("clip"),ClipPath)||
    !R->TryGetStringField(TEXT("skeleton"),SkeletonPath)||SkeletonPath!=Owner->GetSkeleton()->GetPathName()||
    !R->TryGetStringField(TEXT("authentic_material"),MaterialPath)||!R->TryGetStringField(TEXT("authentic_material_slot"),Slot)||
    Slot!=TEXT("tripo_material_6bf04053-4eb9-4c81-aed9-ebf290057e82")||
    !R->TryGetNumberField(TEXT("keys"),Keys)||Keys!=409||!R->TryGetNumberField(TEXT("fps"),Rate)||Rate!=120||
    !R->TryGetNumberField(TEXT("duration_s"),Duration)||!FMath::IsFinite(Duration)||FMath::Abs(Duration-3.4)>.001||
    !R->TryGetBoolField(TEXT("original_owner_untouched"),Original)||!Original||!R->TryGetBoolField(TEXT("world_and_config_untouched"),World)||!World||
    !R->TryGetBoolField(TEXT("native_ready"),Native)||Native||!R->TryGetBoolField(TEXT("activity_ready"),Activity)||Activity){Refuse(TEXT("exact review-only source/owner/material receipt required"));return;}
 const FString Prefix=TEXT("/Game/Sub01Hands/KeyboardReview/V_07baf00adbe6_");
 auto Namespace=[&Prefix](const FString& Path){
  if(!Path.StartsWith(Prefix)||Path.Len()>512||Path.Len()<=Prefix.Len()+32||Path[Prefix.Len()+32]!=TCHAR('/'))return FString();
  for(int32 I=0;I<32;++I)if(!FChar::IsHexDigit(Path[Prefix.Len()+I]))return FString();
  return Path.Left(Prefix.Len()+32);
 };
 const FString MeshNamespace=Namespace(MeshPath);
 if(MeshNamespace.IsEmpty()||Namespace(ClipPath)!=MeshNamespace){Refuse(TEXT("same exact unique source-pinned asset namespace required"));return;}
 auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*MeshPath);auto* Clip=LoadObject<UAnimSequence>(nullptr,*ClipPath);
 if(!Mesh||!Clip||Mesh->GetSkeleton()!=Owner->GetSkeleton()||Clip->GetSkeleton()!=Owner->GetSkeleton()||FMath::Abs(Clip->GetPlayLength()-Duration)>.001){Refuse(TEXT("actual compatible arms mesh/clip required"));return;}
 const auto& Materials=Mesh->GetMaterials();const auto& OwnerMaterials=Owner->GetMaterials();int32 OwnerMatches=0;
 for(const auto& M:OwnerMaterials)if(M.MaterialSlotName==FName(*Slot)&&M.MaterialInterface&&M.MaterialInterface->GetPathName()==MaterialPath)++OwnerMatches;
 if(Materials.Num()!=1||Materials[0].MaterialSlotName!=FName(*Slot)||!Materials[0].MaterialInterface||Materials[0].MaterialInterface->GetPathName()!=MaterialPath||OwnerMatches!=1){Refuse(TEXT("actual exact original owner material binding required"));return;}
 if(!FPSKeyboardReviewArms){
  FPSKeyboardReviewArms=NewObject<USkeletalMeshComponent>(this,TEXT("SUB01_FPSKeyboardReviewArms"));
  FPSKeyboardReviewArms->SetupAttachment(GetRootComponent());FPSKeyboardReviewArms->SetCollisionEnabled(ECollisionEnabled::NoCollision);
  FPSKeyboardReviewArms->SetAbsolute(true,true,true);
  FPSKeyboardReviewArms->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
  FPSKeyboardReviewArms->SetOnlyOwnerSee(true);FPSKeyboardReviewArms->RegisterComponent();
 }
 FPSKeyboardReviewArms->SetSkeletalMeshAsset(Mesh);
 // Declared diagnostic SOURCE component placement; never a pawn assignment.
 FPSKeyboardReviewArms->SetWorldTransform(FTransform(FRotator(0,180,0),FVector(203.9,-232.3,-.6),FVector::OneVector));
 FPSKeyboardReviewArms->PlayAnimation(Clip,Play);FPSKeyboardReviewArms->SetPosition(Play?0.f:1.7f,false);FPSKeyboardReviewArms->SetPlayRate(Play?1.f:0.f);
 FPSKeyboardReviewArms->RefreshBoneTransforms();FPSKeyboardReviewArms->UpdateComponentToWorld();FPSKeyboardReviewArms->SetVisibility(true);
 FPSKeyboardOwnerVisible=FirstPersonBody->IsVisible();FirstPersonBody->SetVisibility(false);
 GetCharacterMovement()->StopMovementImmediately();RouteActive=false;HandsDiagnostic=true;HandsPosture=TEXT("KeyboardReview");PrivateViewMode=EPrivateViewMode::Diagnostic;FPSKeyboardVisualReview=true;
 UE_LOG(LogTemp,Warning,TEXT("SUB01_FPS_KEYBOARD_VISUAL_REVIEW play=%d exact409keys/120Hz/3.4s sourceBody=%s actualPawn=%s unchangedActualEye=%s; source camera NOT applied; NO contact/seat/device-input/activity acceptance"),Play?1:0,*FPSKeyboardReviewArms->GetComponentTransform().ToString(),*Pawn.ToString(),*Eye.ToString());
}
'''

CLEANUP=r'''
 if(FPSKeyboardVisualReview){
  if(FPSKeyboardReviewArms){FPSKeyboardReviewArms->SetVisibility(false);FPSKeyboardReviewArms->SetSkeletalMeshAsset(nullptr);}
  if(FirstPersonBody)FirstPersonBody->SetVisibility(FPSKeyboardOwnerVisible);
  FPSKeyboardVisualReview=false;HandsDiagnostic=false;
 }
'''


def install(header,cpp):
    declaration=' bool DerivedControllerVisualReview=false;'
    cleanup=' ControllerGripReview=false;ControllerGripPlaying=false;'
    if header.count(declaration)!=1 or cpp.count(cleanup)!=1 or 'ReviewFPSKeyboard('in header:
        raise ValueError('Exact existing warm review/restore hooks required')
    return header.replace(declaration,declaration+FIELDS,1),cpp.replace(cleanup,CLEANUP+cleanup,1)+METHODS
