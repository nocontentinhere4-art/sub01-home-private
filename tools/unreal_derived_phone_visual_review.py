"""Warm manual visual review of the exact imported derived phone clip.

No activity/readiness proof, scene save, arbitrary path, or normal phone binding.
Returning to manual Walk uses the existing real assembly restoration.
"""
FIELDS=r'''
 bool DerivedPhoneVisualReview=false;
 TArray<EComponentMobility::Type> DerivedPhoneOriginalMobility;
 UFUNCTION(Exec) void ReviewDerivedPhone(bool Play);
 void UpdateDerivedPhoneVisualReview();
'''
METHODS=r'''
#include "Animation/Skeleton.h"
void ASub01HomeCharacter::ReviewDerivedPhone(bool Play){
 if(PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||HandsDiagnostic||NativeSeatVerified||MinecraftFocused||(PCBridge&&PCBridge->HasOperatorFocus())||!FirstPersonBody||!FirstPersonBody->GetSkeletalMeshAsset())return;
 auto* Owner=FirstPersonBody->GetSkeletalMeshAsset();
 if(Owner->GetPathName()!=TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner"))return;
 FString Raw;TSharedPtr<FJsonObject> R;
 if(!FFileHelper::LoadFileToString(Raw,*FPaths::Combine(FPaths::ProjectDir(),TEXT("unreal-phone-grip-import.json")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),R)||!R.IsValid())return;
 FString Schema,Derived,FBX,Object,Skeleton;double Keys=0,Duration=0;
 if(!R->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("sub01.unreal-phone-grip-import.v1")||!R->TryGetStringField(TEXT("derived_glb_sha256"),Derived)||Derived!=TEXT("81c1d4e10c0a71f46cb4aac36eafd605f92f2fa9397f8d444cc10775445823b2")||!R->TryGetStringField(TEXT("fbx_sha256"),FBX)||FBX!=TEXT("30ce52419d204f914bda05d1a73aefbd49affd0c3f3bfd62f2ccfeacdb82e9d4")||!R->TryGetStringField(TEXT("object_path"),Object)||Object!=TEXT("/Game/Sub01Hands/Phone/SUB01_PhoneGrip.SUB01_PhoneGrip")||!R->TryGetStringField(TEXT("skeleton"),Skeleton)||!R->TryGetNumberField(TEXT("sampled_keys"),Keys)||Keys!=557||!R->TryGetNumberField(TEXT("duration_s"),Duration)||!FMath::IsFinite(Duration)||FMath::Abs(Duration-556./30.)>.001)return;
 auto* Clip=LoadObject<UAnimSequence>(nullptr,*Object);
 if(!Clip||Clip->GetSkeleton()!=Owner->GetSkeleton()||!Owner->GetSkeleton()||Owner->GetSkeleton()->GetPathName()!=Skeleton||FMath::Abs(Clip->GetPlayLength()-Duration)>.001)return;
 if(!FirstPersonBody->DoesSocketExist(TEXT("RightHand"))||!FirstPersonBody->DoesSocketExist(TEXT("Head")))return;
 struct Part{FVector Center,Extent;};const Part Expected[]={
 {FVector(270,-292,85.8),FVector(3.75,7.5,.75)},{FVector(270,-298.2,86.7),FVector(.95,.15,.05)},
 {FVector(266.2,-294,85.8),FVector(.1,1.25,.2)},{FVector(273.8,-294,85.8),FVector(.1,.7,.2)},
 {FVector(270,-292,86.6),FVector(3.35,6.85,0)}};
 TArray<UStaticMeshComponent*> Found;
 for(const auto& E:Expected){UStaticMeshComponent* Match=nullptr;int32 Count=0;for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UStaticMeshComponent*> Cs;It->GetComponents(Cs);for(auto* C:Cs){if(!C->GetStaticMesh())continue;const auto B=C->CalcBounds(C->GetComponentTransform());if(FVector::Dist(B.Origin,E.Center)<.1&&FVector::Dist(B.BoxExtent,E.Extent)<.1){Match=C;++Count;}}}if(Count!=1)return;Found.Add(Match);}
 PhoneGripParts.Empty();PhoneGripOriginalTransforms.Empty();DerivedPhoneOriginalMobility.Empty();
 for(auto* C:Found){PhoneGripParts.Add(C);PhoneGripOriginalTransforms.Add(C->GetComponentTransform());DerivedPhoneOriginalMobility.Add(C->Mobility);C->SetMobility(EComponentMobility::Movable);}
 GetCharacterMovement()->StopMovementImmediately();RouteActive=false;
 HandsDiagnostic=true;HandsPosture=TEXT("Phone");PrivateViewMode=EPrivateViewMode::Diagnostic;
 DerivedPhoneVisualReview=true;PhoneGripReview=true;PhoneGripMounted=true;PhoneGripWrist=TEXT("RightHand");PhoneGripCapturedClip=Clip;PhoneGripPoseTime=Play?0.f:4.f;
 PhoneGripOffset=FVector(.75422,-9.68499,4.71232);PhoneGripRotation=FRotator(-22.42641,59.35637,4.24461);
 FirstPersonBody->PlayAnimation(Clip,Play);FirstPersonBody->SetPosition(PhoneGripPoseTime,false);FirstPersonBody->SetPlayRate(Play?1.f:0.f);FirstPersonBody->RefreshBoneTransforms();FirstPersonBody->UpdateComponentToWorld();FirstPersonBody->SetVisibility(true);
 UpdateDerivedPhoneVisualReview();UpdatePrivatePhoneGripReview();
 UE_LOG(LogTemp,Warning,TEXT("SUB01_DERIVED_PHONE_VISUAL_REVIEW play=%d source=81c1d4e1 exact imported557keys; not activity/contact acceptance"),Play?1:0);
}
void ASub01HomeCharacter::UpdateDerivedPhoneVisualReview(){
 if(!DerivedPhoneVisualReview||!PhoneGripReview||PrivateViewMode!=EPrivateViewMode::Diagnostic||!FirstPersonBody||!ViewCamera)return;
 auto* A=FirstPersonBody->GetSingleNodeInstance();if(!A||A->GetCurrentAsset()!=PhoneGripCapturedClip.Get())return;
 const FTransform H=FirstPersonBody->GetSocketTransform(TEXT("Head"),RTS_World);
 const FVector Eye=H.GetLocation()+H.GetRotation().GetNormalized().RotateVector(FVector(.11885198390986161,-13.382490930007885,12.634526097714183));
 if(Eye.ContainsNaN())return;ViewCamera->SetUsingAbsoluteLocation(true);ViewCamera->SetWorldLocation(Eye);
}
'''
CLEANUP=r'''
 if(DerivedPhoneVisualReview){
  for(int32 I=0;I<PhoneGripParts.Num()&&I<DerivedPhoneOriginalMobility.Num();++I)if(PhoneGripParts[I])PhoneGripParts[I]->SetMobility(DerivedPhoneOriginalMobility[I]);
  DerivedPhoneVisualReview=false;DerivedPhoneOriginalMobility.Empty();HandsDiagnostic=false;
 }
'''


def install(header,cpp):
    declaration=' bool PhoneGripReview=false,PhoneGripMounted=false;'
    tick=' UpdatePrivatePhoneGripReview();'
    cleanup=' PhoneGripReview=false;PhoneGripMounted=false;'
    for text,hook in ((header,declaration),(cpp,tick),(cpp,cleanup)):
        if text.count(hook)!=1:raise ValueError('Unique existing phone review/cleanup hook required')
    if 'ReviewDerivedPhone(' in header:raise ValueError('Derived phone review already installed')
    return header.replace(declaration,declaration+FIELDS,1),cpp.replace(tick,' UpdateDerivedPhoneVisualReview();\n'+tick,1).replace(cleanup,cleanup+CLEANUP,1)+METHODS
