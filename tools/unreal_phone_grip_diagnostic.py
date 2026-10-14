"""Explicit private captured-pose review, never a normal phone activity binding."""
SOURCE_SHA='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
PARTS=[((270,-292,85.8),(3.75,7.5,.75)),((270,-298.2,86.7),(.95,.15,.05)),
       ((266.2,-294,85.8),(.1,1.25,.2)),((273.8,-294,85.8),(.1,.7,.2)),
       ((270,-292,86.6),(3.35,6.85,0))]
FIELDS=r'''
 bool PhoneGripReview=false;
 FName PhoneGripWrist;
 FVector PhoneGripOffset=FVector::ZeroVector;
 FRotator PhoneGripRotation=FRotator::ZeroRotator;
 UPROPERTY()TArray<TObjectPtr<UStaticMeshComponent>> PhoneGripParts;
 TArray<FTransform> PhoneGripOriginalTransforms;
 void ConfigurePrivatePhoneGripReview();
 void UpdatePrivatePhoneGripReview();
'''
METHODS=r'''
#include "Animation/AnimSingleNodeInstance.h"
void ASub01HomeCharacter::ConfigurePrivatePhoneGripReview(){
 if(!FParse::Param(FCommandLine::Get(),TEXT("Sub01PhoneGripDiagnostic")))return;
 FString Role;FParse::Value(FCommandLine::Get(),TEXT("Sub01HandsDiagnostic="),Role);
 if(!HandsDiagnostic||Role!=TEXT("Phone")||!FirstPersonBody||!HandsClips.Contains(TEXT("Phone"))){UE_LOG(LogTemp,Error,TEXT("SUB01_PHONE_GRIP_REFUSED requires original captured Phone diagnostic"));return;}
 PrivateViewMode=EPrivateViewMode::Diagnostic;
 const auto& Ref=FirstPersonBody->GetSkeletalMeshAsset()->GetRefSkeleton();
 for(int32 I=0;I<Ref.GetNum();++I)if(Ref.GetBoneName(I).ToString().EndsWith(TEXT("RightHand")))PhoneGripWrist=Ref.GetBoneName(I);
 if(PhoneGripWrist.IsNone())return;
 float Time=4;FParse::Value(FCommandLine::Get(),TEXT("Sub01PhonePoseTime="),Time);auto* Clip=HandsClips.FindRef(TEXT("Phone"));
 FirstPersonBody->PlayAnimation(Clip,false);FirstPersonBody->SetPosition(FMath::Clamp(Time,0.f,Clip->GetPlayLength()),false);FirstPersonBody->SetPlayRate(0);
 FirstPersonBody->RefreshBoneTransforms();FirstPersonBody->UpdateComponentToWorld();
 const FTransform W=FirstPersonBody->GetSocketTransform(PhoneGripWrist,RTS_World);
 UE_LOG(LogTemp,Display,TEXT("SUB01_PHONE_CAPTURED_WRIST unaccepted original fingers unchanged time=%.3f bone=%s position=%s rotation=%s scale=%s"),Time,*PhoneGripWrist.ToString(),*W.GetLocation().ToString(),*W.GetRotation().ToString(),*W.GetScale3D().ToString());
 FString Offset,Euler;if(!FParse::Value(FCommandLine::Get(),TEXT("Sub01PhoneMountCm="),Offset)||!FParse::Value(FCommandLine::Get(),TEXT("Sub01PhoneMountEuler="),Euler)||!PhoneGripOffset.InitFromString(Offset)||!PhoneGripRotation.InitFromString(Euler)){UE_LOG(LogTemp,Warning,TEXT("SUB01_PHONE_GRIP_REVIEW no mount: explicit measured wrist-frame offset/euler required"));return;}
 if(PhoneGripOffset.Size()>30||PhoneGripOffset.ContainsNaN()||PhoneGripRotation.ContainsNaN())return;
 struct Part{FVector Center,Extent;};const Part Expected[]={
 {FVector(270,-292,85.8),FVector(3.75,7.5,.75)}, {FVector(270,-298.2,86.7),FVector(.95,.15,.05)},
 {FVector(266.2,-294,85.8),FVector(.1,1.25,.2)}, {FVector(273.8,-294,85.8),FVector(.1,.7,.2)},
 {FVector(270,-292,86.6),FVector(3.35,6.85,0)}};
 TArray<UStaticMeshComponent*> Found;
 for(const auto& E:Expected){UStaticMeshComponent* Match=nullptr;int32 Count=0;for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UStaticMeshComponent*> Components;It->GetComponents(Components);for(auto* C:Components){if(!C->GetStaticMesh())continue;const auto B=C->CalcBounds(C->GetComponentTransform());if(FVector::Dist(B.Origin,E.Center)<.1&&FVector::Dist(B.BoxExtent,E.Extent)<.1){Match=C;++Count;}}}if(Count!=1){UE_LOG(LogTemp,Error,TEXT("SUB01_PHONE_GRIP_REFUSED original five-part assembly matchcount=%d"),Count);return;}Found.Add(Match);}
 for(auto* C:Found){PhoneGripOriginalTransforms.Add(C->GetComponentTransform());PhoneGripParts.Add(C);C->SetMobility(EComponentMobility::Movable);}
 PhoneGripReview=true;UpdatePrivatePhoneGripReview();
 UE_LOG(LogTemp,Warning,TEXT("SUB01_UNACCEPTED_PHONE_GRIP_CANDIDATE original five-part assembly7.5x15x1.5cm materials and live screen unchanged offset=%s rotation=%s; NO normal activity acceptance"),*PhoneGripOffset.ToString(),*PhoneGripRotation.ToString());
}
void ASub01HomeCharacter::UpdatePrivatePhoneGripReview(){
 if(!PhoneGripReview||!FirstPersonBody)return;
 const FTransform W=FirstPersonBody->GetSocketTransform(PhoneGripWrist,RTS_World);
 // Rigid assembly uses real world centimetres, independent of imported bone scale.
 const FQuat Rotation=W.GetRotation()*PhoneGripRotation.Quaternion();
 const FVector Center=W.GetLocation()+W.GetRotation().RotateVector(PhoneGripOffset);
 const FTransform Rigid(Rotation,Center,FVector::OneVector),FromOriginal(FQuat::Identity,FVector(-270,292,-85.8));
 for(int32 I=0;I<PhoneGripParts.Num();++I)if(PhoneGripParts[I])PhoneGripParts[I]->SetWorldTransform(PhoneGripOriginalTransforms[I]*FromOriginal*Rigid);
}
'''
def install(header,cpp):
    if header.count(' void ConfigureActualPC();')!=1 or cpp.count(' ConfigureActualPC();')!=1 or cpp.count(' Super::Tick(DeltaSeconds);')!=1:
        raise ValueError('Unique actual character setup/tick hooks required')
    header=header.replace(' void ConfigureActualPC();',' void ConfigureActualPC();'+FIELDS,1)
    cpp=cpp.replace(' ConfigureActualPC();',' ConfigureActualPC();\n ConfigurePrivatePhoneGripReview();',1)
    cpp=cpp.replace(' Super::Tick(DeltaSeconds);',' Super::Tick(DeltaSeconds);\n UpdatePrivatePhoneGripReview();',1)
    return header,cpp+'\n'+METHODS
