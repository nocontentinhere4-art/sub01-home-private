"""Explicit authentic Gaming pose review; never sofa/grip/activity acceptance."""
FIELDS=r'''
 bool ControllerGripReview=false,ControllerGripPlaying=false;
 UPROPERTY()TObjectPtr<UAnimSequence> ControllerGripCapturedClip;
 FName ControllerGripHead,ControllerGripLeft,ControllerGripRight;
 float ControllerGripPoseTime=4;
 void ConfigurePrivateControllerGripReview();void UpdatePrivateControllerGripReview();
'''
METHODS=r'''
#include "Animation/AnimSingleNodeInstance.h"
void ASub01HomeCharacter::ConfigurePrivateControllerGripReview(){
 if(!FParse::Param(FCommandLine::Get(),TEXT("Sub01ControllerGripDiagnostic")))return;
 FString Role;FParse::Value(FCommandLine::Get(),TEXT("Sub01HandsDiagnostic="),Role);
 auto* Clip=HandsClips.FindRef(TEXT("Gaming")).Get();
 if(!HandsDiagnostic||Role!=TEXT("Gaming")||!FirstPersonBody||!FirstPersonBody->GetSkeletalMeshAsset()||!Clip
  ||FirstPersonBody->GetSkeletalMeshAsset()->GetPathName()!=TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner")
  ||Clip->GetPathName()!=TEXT("/Game/Sub01Hands/Controller/SUB01_Gaming.SUB01_Gaming")
  ||Clip->GetSkeleton()!=FirstPersonBody->GetSkeletalMeshAsset()->GetSkeleton()){
  UE_LOG(LogTemp,Error,TEXT("SUB01_CONTROLLER_REVIEW_REFUSED exact actual owner and genuine Gaming USkeleton required"));return;}
 float Time=4;FParse::Value(FCommandLine::Get(),TEXT("Sub01ControllerPoseTime="),Time);
 if(!FMath::IsFinite(Time)||Time<0||Time>Clip->GetPlayLength()){UE_LOG(LogTemp,Error,TEXT("SUB01_CONTROLLER_REVIEW_REFUSED finite original captured time required"));return;}
 const auto& Ref=FirstPersonBody->GetSkeletalMeshAsset()->GetRefSkeleton();
 for(int32 I=0;I<Ref.GetNum();++I){const FString N=Ref.GetBoneName(I).ToString();
  if(N.EndsWith(TEXT("Head")))ControllerGripHead=Ref.GetBoneName(I);
  if(N.EndsWith(TEXT("LeftHand")))ControllerGripLeft=Ref.GetBoneName(I);
  if(N.EndsWith(TEXT("RightHand")))ControllerGripRight=Ref.GetBoneName(I);}
 if(ControllerGripHead.IsNone()||ControllerGripLeft.IsNone()||ControllerGripRight.IsNone())return;
 PrivateViewMode=EPrivateViewMode::Diagnostic;GetCharacterMovement()->StopMovementImmediately();
 HandsPosture=TEXT("Gaming");HandsFailure=TEXT("Unaccepted captured Gaming pose review; sofa/contact/held controller not verified");
 FirstPersonBody->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);
 FirstPersonBody->SetRelativeRotation(HandsMeshRotation);FirstPersonBody->SetRelativeLocation(WalkMeshOffset);FirstPersonBody->SetVisibility(true);
 ControllerGripCapturedClip=Clip;ControllerGripPoseTime=Time;
 FirstPersonBody->PlayAnimation(Clip,false);FirstPersonBody->SetPosition(Time,false);FirstPersonBody->SetPlayRate(0);FirstPersonBody->RefreshBoneTransforms();FirstPersonBody->UpdateComponentToWorld();
 ControllerGripReview=true;UpdatePrivateControllerGripReview();
 UE_LOG(LogTemp,Warning,TEXT("SUB01_CONTROLLER_POSE_REVIEW original Gaming time=%.3f unchanged captured fingers/rig; existing actor retained; NO sofa/seat/held-controller acceptance"),Time);
}
void ASub01HomeCharacter::UpdatePrivateControllerGripReview(){
 if(!ControllerGripReview||PrivateViewMode!=EPrivateViewMode::Diagnostic||!FirstPersonBody)return;
 auto* A=FirstPersonBody->GetSingleNodeInstance();if(!A||A->GetCurrentAsset()!=ControllerGripCapturedClip.Get())return;
 const float ActualTime=A->GetCurrentTime();if(!FMath::IsFinite(ActualTime)||ActualTime<0||ActualTime>ControllerGripCapturedClip->GetPlayLength()+.01f||(!ControllerGripPlaying&&FMath::Abs(ActualTime-ControllerGripPoseTime)>.01f))return;
 const FTransform H=FirstPersonBody->GetSocketTransform(ControllerGripHead,RTS_World);
 // Same original head/skin: physical iris-surface midpoint from independently verified
 // native local frame. A unit quaternion deliberately excludes hidden Head zero scale.
 const FVector Eye=H.GetLocation()+H.GetRotation().GetNormalized().RotateVector(FVector(.11885198390986161,-13.382490930007885,12.634526097714183));
 if(Eye.ContainsNaN())return;ViewCamera->SetUsingAbsoluteLocation(true);ViewCamera->SetWorldLocation(Eye);
 static double Last=-1;const double Now=FPlatformTime::Seconds();if(Last>=0&&Now-Last<2)return;Last=Now;
 const FTransform L=FirstPersonBody->GetSocketTransform(ControllerGripLeft,RTS_World),R=FirstPersonBody->GetSocketTransform(ControllerGripRight,RTS_World);
 UE_LOG(LogTemp,Display,TEXT("SUB01_CONTROLLER_CAPTURED_GEOMETRY unaccepted time=%.3f eye=%s forward=%s left=%s leftQ=%s right=%s rightQ=%s head=%s headQ=%s body=%s actualpawn=%s"),ActualTime,*Eye.ToString(),*ViewCamera->GetForwardVector().ToString(),*L.GetLocation().ToString(),*L.GetRotation().ToString(),*R.GetLocation().ToString(),*R.GetRotation().ToString(),*H.GetLocation().ToString(),*H.GetRotation().ToString(),*FirstPersonBody->GetComponentTransform().ToString(),*GetActorLocation().ToString());
}
'''
CLEANUP=r'''
 // An explicit transition out of review restores the actual animation class/camera,
 // without moving the pawn, changing captured bones or claiming a physical seat.
 ControllerGripReview=false;ControllerGripPlaying=false;
 if(ViewCamera)ViewCamera->SetUsingAbsoluteLocation(false);
 if(FirstPersonBody&&!Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()))FirstPersonBody->SetAnimInstanceClass(USub01HomeHandsInstance::StaticClass());
'''
def install(header,cpp):
    anchors=(' void ConfigureActualPC();',' ConfigureActualPC();',' Super::Tick(DeltaSeconds);')
    if header.count(anchors[0])!=1 or cpp.count(anchors[1])!=1 or cpp.count(anchors[2])!=1:
        raise ValueError('Unique actual native review setup/tick hooks required')
    role=' if(Role!=TEXT("Phone")&&Role!=TEXT("DeskTyping")&&Role!=TEXT("Walk"))'
    bind=' HandsClips.Add(FName(*Role),Clip);SetHandsPosture(FName(*Role));'
    reset=' LiveHome=false;LiveHomeFresh=false;LiveHomeBindWaiting=false;NativeSeatVerified=false;'
    if cpp.count(role)!=1 or cpp.count(bind)!=1 or cpp.count(reset)!=1:
        raise ValueError('Unique actual role/bind/ownership hooks required')
    cpp=cpp.replace(role,' if(Role!=TEXT("Phone")&&Role!=TEXT("DeskTyping")&&Role!=TEXT("Walk")&&!(Role==TEXT("Gaming")&&FParse::Param(FCommandLine::Get(),TEXT("Sub01ControllerGripDiagnostic"))))',1)
    cpp=cpp.replace(bind,' HandsClips.Add(FName(*Role),Clip);if(Role!=TEXT("Gaming"))SetHandsPosture(FName(*Role));',1)
    header=header.replace(anchors[0],anchors[0]+FIELDS,1)
    cpp=cpp.replace(anchors[1],anchors[1]+'\n ConfigurePrivateControllerGripReview();',1)
    cpp=cpp.replace(anchors[2],anchors[2]+'\n UpdatePrivateControllerGripReview();',1)
    cpp=cpp.replace(reset,CLEANUP+reset,1)
    control=' FString Capture;if(Doc->TryGetStringField(TEXT("capture"),Capture)'
    if cpp.count(control)!=1:raise ValueError('Unique protected capture callback required')
    replay=r'''
 bool GamingReplay=false;if(Doc->TryGetBoolField(TEXT("replayGaming"),GamingReplay)&&GamingReplay&&ControllerGripReview&&PrivateViewMode==EPrivateViewMode::Diagnostic&&FirstPersonBody){
  auto* Actual=FirstPersonBody->GetSingleNodeInstance();
  if(Actual&&Actual->GetCurrentAsset()==ControllerGripCapturedClip.Get()){
   ControllerGripPlaying=true;Actual->SetPosition(0,false);Actual->SetLooping(false);Actual->SetPlayRate(1);Actual->SetPlaying(true);
   UE_LOG(LogTemp,Warning,TEXT("SUB01_CONTROLLER_AUTHENTIC_REPLAY source 0..%.6fs unchanged captured motion; no sofa/grip acceptance"),ControllerGripCapturedClip->GetPlayLength());
  }
 }
'''
    cpp=cpp.replace(control,replay+control,1)
    first='#include "Sub01HomeLab.h"'
    if cpp.count(first)!=1:raise ValueError('Unique native first include required')
    cpp=cpp.replace(first,first+'\n#include "Animation/AnimSingleNodeInstance.h"',1)
    return header,cpp+'\n'+METHODS
