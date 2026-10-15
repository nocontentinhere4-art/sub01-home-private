"""Warm review of the exact imported two-hand Gaming grip; never play readiness.

Uses the existing hidden physical controller component and original owner. This
is a diagnostic at the unchanged pawn, not a sofa pose or Minecraft input gate.
"""
FIELDS=r'''
 bool DerivedControllerVisualReview=false;
 UFUNCTION(Exec) void ReviewDerivedController(bool Play);
 void UpdateDerivedControllerVisualReview();
'''
METHODS=r'''
void ASub01HomeCharacter::ReviewDerivedController(bool Play){
 auto Refuse=[](const TCHAR* Reason){UE_LOG(LogTemp,Warning,TEXT("SUB01_DERIVED_CONTROLLER_REVIEW_REFUSED %s"),Reason);};
 if(PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||HandsDiagnostic||NativeSeatVerified||MinecraftFocused||ControllerPlayActive||(PCBridge&&PCBridge->HasOperatorFocus())){Refuse(TEXT("manual idle view required"));return;}
 auto* Owner=FirstPersonBody?FirstPersonBody->GetSkeletalMeshAsset():nullptr;
 if(!Owner||Owner->GetPathName()!=TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner")||!Owner->GetSkeleton()||!ControllerPlayProp||!ControllerPlayProp->GetStaticMesh()){Refuse(TEXT("actual original owner and physical controller required"));return;}
 FString Raw;TSharedPtr<FJsonObject> R;const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
 if(!FFileHelper::LoadFileToString(Raw,*FPaths::Combine(FPaths::ProjectDir(),TEXT("unreal-gaming-grip-import.json")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),R)||!R.IsValid()){Refuse(TEXT("actual derived import receipt required"));return;}
 FString Schema,OwnerPath,Skeleton;
 if(!R->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("sub01.unreal-gaming-grip-import.v1")||!R->TryGetStringField(TEXT("owner"),OwnerPath)||OwnerPath!=Owner->GetPathName()||!R->TryGetStringField(TEXT("skeleton"),Skeleton)||Skeleton!=Owner->GetSkeleton()->GetPathName()||!R->TryGetArrayField(TEXT("clips"),Rows)||Rows->Num()!=1){Refuse(TEXT("exact owner/import identity required"));return;}
 auto Row=(*Rows)[0]->AsObject();FString Role,Object,Derived,Source;double Frames=0,Duration=0;bool Same=false;
 if(!Row.IsValid()||!Row->TryGetStringField(TEXT("role"),Role)||Role!=TEXT("Gaming")||!Row->TryGetStringField(TEXT("object_path"),Object)||Object!=TEXT("/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip")||!Row->TryGetStringField(TEXT("derived_glb_sha256"),Derived)||Derived!=TEXT("bf31d64518d85f6eefd8150009a758ddddc95ca6afd63d5d83bdf29a2dcdaaf9")||!Row->TryGetStringField(TEXT("source_fbx_sha256"),Source)||Source!=TEXT("84dfc60ab9e13b9c896e89def81478a5e47f45b80cc3d8902c5b8a0ae8d8fc7f")||!Row->TryGetNumberField(TEXT("frames"),Frames)||Frames!=152||!Row->TryGetNumberField(TEXT("duration_s"),Duration)||!FMath::IsFinite(Duration)||FMath::Abs(Duration-151./30.)>.001||!Row->TryGetBoolField(TEXT("same_existing_skeleton"),Same)||!Same){Refuse(TEXT("exact derived clip receipt required"));return;}
 auto* Clip=LoadObject<UAnimSequence>(nullptr,*Object);
 if(!Clip||Clip->GetSkeleton()!=Owner->GetSkeleton()||FMath::Abs(Clip->GetPlayLength()-Duration)>.001||!FirstPersonBody->DoesSocketExist(TEXT("Head"))||!FirstPersonBody->DoesSocketExist(TEXT("RightHand"))||!FirstPersonBody->DoesSocketExist(TEXT("LeftHand"))){Refuse(TEXT("actual compatible clip and sockets required"));return;}
 FString AssetRaw;TSharedPtr<FJsonObject> Asset;const TSharedPtr<FJsonObject>* Physical=nullptr;FString AssetSchema,AssetSource,MeshPath;
 if(!FFileHelper::LoadFileToString(AssetRaw,*FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit/native-controller-asset.json")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(AssetRaw),Asset)||!Asset.IsValid()||!Asset->TryGetStringField(TEXT("schema"),AssetSchema)||AssetSchema!=TEXT("sub01.native-controller-asset.v1")||!Asset->TryGetStringField(TEXT("source_sha256"),AssetSource)||AssetSource!=TEXT("c034a1444711a44f0726e7264b1e2e2b47b1bbdba0e5dd615eef27001a4717e4")||!Asset->TryGetObjectField(TEXT("physical_assembly"),Physical)||!(*Physical)->TryGetStringField(TEXT("mesh"),MeshPath)||MeshPath.Contains(TEXT("contact"),ESearchCase::IgnoreCase)||ControllerPlayProp->GetStaticMesh()->GetPathName()!=MeshPath){Refuse(TEXT("exact imported physical controller required"));return;}
 GetCharacterMovement()->StopMovementImmediately();RouteActive=false;HandsDiagnostic=true;HandsPosture=TEXT("Gaming");PrivateViewMode=EPrivateViewMode::Diagnostic;
 DerivedControllerVisualReview=true;ControllerGripReview=true;ControllerGripPlaying=Play;ControllerGripCapturedClip=Clip;ControllerGripPoseTime=Play?0.f:4.f;
 ControllerGripHead=TEXT("Head");ControllerGripLeft=TEXT("LeftHand");ControllerGripRight=TEXT("RightHand");
 FirstPersonBody->PlayAnimation(Clip,Play);FirstPersonBody->SetPosition(ControllerGripPoseTime,false);FirstPersonBody->SetPlayRate(Play?1.f:0.f);FirstPersonBody->RefreshBoneTransforms();FirstPersonBody->UpdateComponentToWorld();FirstPersonBody->SetVisibility(true);
 UpdatePrivateControllerGripReview();UpdateDerivedControllerVisualReview();
 UE_LOG(LogTemp,Warning,TEXT("SUB01_DERIVED_CONTROLLER_VISUAL_REVIEW play=%d exact152keys; no sofa/contact/input/activity acceptance"),Play?1:0);
}
void ASub01HomeCharacter::UpdateDerivedControllerVisualReview(){
 if(!DerivedControllerVisualReview||!ControllerGripReview||PrivateViewMode!=EPrivateViewMode::Diagnostic||!FirstPersonBody||!ControllerPlayProp)return;
 auto* A=FirstPersonBody->GetSingleNodeInstance();if(!A||A->GetCurrentAsset()!=ControllerGripCapturedClip.Get())return;
 // Rigid transform from the exact bf31d645 derived report, same glTF->UE
 // convention as ue_grip(). Native alignment remains subject to visual review.
 const FTransform W=FirstPersonBody->GetSocketTransform(ControllerGripRight,RTS_World);
 const FQuat Q=Sub01ControllerSourceHandFrameRotation(W.GetRotation().GetNormalized());
 const FVector P=W.GetLocation()+Q.RotateVector(FVector(-.4953816746105376,9.019971890640429,10.536509174570956));
 const FQuat R=Q*FQuat(-.6482862729184252,.5822889827099884,-.373853500296671,.31764446992829865);
 if(P.ContainsNaN()||R.ContainsNaN())return;
 ControllerPlayProp->SetWorldLocationAndRotation(Sub01ControllerSourceMountPosition(P,R,ControllerPlaySourceOffset),R*ControllerPlaySourceRotation);ControllerPlayProp->SetVisibility(true);
}
'''
CLEANUP=r'''
 if(DerivedControllerVisualReview){if(ControllerPlayProp)ControllerPlayProp->SetVisibility(false);DerivedControllerVisualReview=false;HandsDiagnostic=false;}
'''


def install(header,cpp):
    declaration=' bool ControllerGripReview=false,ControllerGripPlaying=false;'
    tick=' UpdatePrivateControllerGripReview();'
    cleanup=' ControllerGripReview=false;ControllerGripPlaying=false;'
    for text,hook in ((header,declaration),(cpp,tick),(cpp,cleanup)):
        if text.count(hook)!=1:raise ValueError('Unique existing controller review hook required')
    if 'ReviewDerivedController(' in header:raise ValueError('Derived controller review already installed')
    return (header.replace(declaration,declaration+FIELDS,1),
            cpp.replace(tick,tick+'\n UpdateDerivedControllerVisualReview();',1).replace(cleanup,CLEANUP+cleanup,1)+METHODS)
