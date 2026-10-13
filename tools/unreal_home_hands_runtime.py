"""Native real-clip first-person skeletal pose blending, staged for server compilation."""
HEADER = r'''#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Sub01HomeHands.generated.h"
class UAnimSequence;
UCLASS(Transient)
class SUB01HOMELAB_API USub01HomeHandsInstance : public UAnimInstance {
 GENERATED_BODY()
 public:
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> TargetSequence;
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> PreviousSequence;
 UPROPERTY(Transient) float TargetRate=0;
 protected:
 virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
 virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;
};
'''
CPP = r'''#include "Sub01HomeHands.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNode_SequencePlayer.h"
#include "Animation/AnimSequence.h"
#include "AnimNodes/AnimNode_TwoWayBlend.h"
struct FSub01HandsProxy : FAnimInstanceProxy {
 FAnimNode_SequencePlayer_Standalone Previous,Current;
 FAnimNode_TwoWayBlend Blend;
 float Progress=1;
 FSub01HandsProxy(UAnimInstance* Instance):FAnimInstanceProxy(Instance){}
 virtual void Initialize(UAnimInstance* Instance) override {
  FAnimInstanceProxy::Initialize(Instance);
  Blend.A.SetLinkNode(&Previous); Blend.B.SetLinkNode(&Current);
  Previous.SetLoopAnimation(true); Current.SetLoopAnimation(true);
  FAnimationInitializeContext Context(this); Blend.Initialize_AnyThread(Context);
 }
 virtual void PreUpdate(UAnimInstance* Instance,float DeltaSeconds) override {
  FAnimInstanceProxy::PreUpdate(Instance,DeltaSeconds);
  auto* Hands=Cast<USub01HomeHandsInstance>(Instance);
  if(!Hands)return;
  if(Current.GetSequence()!=Hands->TargetSequence) {
   Hands->PreviousSequence=Cast<UAnimSequence>(Current.GetSequence());
   Previous.SetSequence(Hands->PreviousSequence?Hands->PreviousSequence.Get():Hands->TargetSequence.Get());
   Previous.SetAccumulatedTime(Current.GetAccumulatedTime());
   Previous.SetPlayRate(0);
   Current.SetSequence(Hands->TargetSequence); Current.SetAccumulatedTime(0);
   Progress=Hands->PreviousSequence?0:1;
  }
  Current.SetPlayRate(Hands->TargetRate);
 }
 virtual void CacheBones() override {
  FAnimationCacheBonesContext Context(this); Blend.CacheBones_AnyThread(Context);
 }
 virtual void Update(float DeltaSeconds) override {
  Progress=FMath::Min(1.f,Progress+FMath::Min(DeltaSeconds,.1f)/.24f);
  Blend.Alpha=Progress;
  FAnimationUpdateContext Context(this,DeltaSeconds); Blend.Update_AnyThread(Context);
 }
 virtual bool Evaluate(FPoseContext& Output) override {Blend.Evaluate_AnyThread(Output);return true;}
};
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy(){return new FSub01HandsProxy(this);}
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy){delete Proxy;}
'''

CHARACTER_FIELDS = r'''
 public:
 virtual void Tick(float DeltaSeconds) override;
 UFUNCTION(BlueprintCallable,Category="SUB01|Hands") bool SetHandsPosture(FName Posture);
 UFUNCTION(BlueprintPure,Category="SUB01|Hands") FString GetHandsReadiness() const;
 UFUNCTION(Exec) void PreviewHandsPose(FName Posture);
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString HandsMeshPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString IdleClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString WalkClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString TypingClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString MouseClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString PhoneClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") TArray<FName> ValidatedHandsPostures;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FVector WalkMeshOffset=FVector(0,0,-165);
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FVector DeskMeshOffset=FVector(0,0,-128);
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FRotator HandsMeshRotation=FRotator::ZeroRotator;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") TArray<FName> HiddenHeadBones;
 private:
 UPROPERTY() TObjectPtr<USkeletalMeshComponent> FirstPersonBody;
 UPROPERTY() TMap<FName,TObjectPtr<UAnimSequence>> HandsClips;
 FName HandsPosture=TEXT("Walk");
 FString HandsFailure=TEXT("No verified first-person skeletal assets are bound.");
 FVector HandsBaseOffset;
 float WalkPhase=0,MotionWeight=0;
 void LoadHandsAssets();
 void UpdateNativeCapture();
 double CaptureStarted=0,CaptureRequestedAt=0;
 float CaptureAfter=-1;
 FString CapturePath;
 bool CaptureRequested=false;
'''

CHARACTER_METHODS = r'''
void ASub01HomeCharacter::UpdateNativeCapture() {
 if(CaptureAfter<0)return;
 const double Now=FPlatformTime::Seconds();
 if(!CaptureRequested&&Now-CaptureStarted>=CaptureAfter){
  CaptureRequested=true;CaptureRequestedAt=Now;
  const FVector Eye=ViewCamera->GetComponentLocation(),Position=GetActorLocation();
  UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_GAME_CAPTURE pawn=%s eye=%s capsuleRadius=%.3f capsuleHalfHeight=%.3f mode=%d floor=%d hands=%s path=%s"),*Position.ToString(),*Eye.ToString(),GetCapsuleComponent()->GetScaledCapsuleRadius(),GetCapsuleComponent()->GetScaledCapsuleHalfHeight(),int32(GetCharacterMovement()->MovementMode),GetCharacterMovement()->IsMovingOnGround()?1:0,*GetHandsReadiness(),*CapturePath);
  FScreenshotRequest::RequestScreenshot(CapturePath,false,false);
 }
 if(CaptureRequested&&Now-CaptureRequestedAt>1&&IFileManager::Get().FileSize(*CapturePath)>0){
  UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_GAME_CAPTURE_SAVED bytes=%lld"),IFileManager::Get().FileSize(*CapturePath));
  CaptureAfter=-1;FPlatformMisc::RequestExit(false);
 }else if(CaptureRequested&&Now-CaptureRequestedAt>40){
  UE_LOG(LogTemp,Error,TEXT("SUB01_NATIVE_GAME_CAPTURE_FAILED no image written"));
  CaptureAfter=-1;FPlatformMisc::RequestExitWithStatus(false,2);
 }
}

void ASub01HomeCharacter::LoadHandsAssets() {
 auto* Mesh=HandsMeshPath.IsEmpty()?nullptr:LoadObject<USkeletalMesh>(nullptr,*HandsMeshPath);
 if(!Mesh){HandsFailure=TEXT("First-person skeletal mesh is missing.");return;}
 FirstPersonBody->SetSkeletalMeshAsset(Mesh);
 FirstPersonBody->SetRelativeLocation(WalkMeshOffset);FirstPersonBody->SetRelativeRotation(HandsMeshRotation);
 FirstPersonBody->SetAnimInstanceClass(USub01HomeHandsInstance::StaticClass());
 for(const FName& Bone:HiddenHeadBones)if(Mesh->GetRefSkeleton().FindBoneIndex(Bone)!=INDEX_NONE)
  FirstPersonBody->HideBoneByName(Bone,EPhysBodyOp::PBO_None);
 auto Bind=[&](FName Role,const FString& Path){
  auto* Clip=Path.IsEmpty()?nullptr:LoadObject<UAnimSequence>(nullptr,*Path);
  if(!Clip||Clip->GetSkeleton()!=Mesh->GetSkeleton()||!ValidatedHandsPostures.Contains(Role))return;
  HandsClips.Add(Role,Clip);
 };
 Bind(TEXT("Idle"),IdleClipPath);Bind(TEXT("Walk"),WalkClipPath);
 Bind(TEXT("DeskTyping"),TypingClipPath);Bind(TEXT("DeskMouse"),MouseClipPath);Bind(TEXT("Phone"),PhoneClipPath);
 SetHandsPosture(HandsPosture);
}
bool ASub01HomeCharacter::SetHandsPosture(FName Posture) {
 if(Posture!=TEXT("Walk")&&Posture!=TEXT("DeskTyping")&&Posture!=TEXT("DeskMouse")&&Posture!=TEXT("Phone"))return false;
 HandsPosture=Posture;
 if(!FirstPersonBody->GetSkeletalMeshAsset()||!HandsClips.Contains(Posture)){
  FirstPersonBody->SetVisibility(false);
  HandsFailure=Posture.ToString()+TEXT(": actual compatible animation/retarget binding is not verified.");
  return false;
 }
 HandsBaseOffset=Posture.ToString().StartsWith(TEXT("Desk"))?DeskMeshOffset:WalkMeshOffset;
 if(auto* Instance=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance())){
  Instance->TargetSequence=HandsClips.FindRef(Posture);
  Instance->TargetRate=Posture==TEXT("Walk")?0.f:1.f;
 }
 FirstPersonBody->SetRelativeLocation(HandsBaseOffset);
 FirstPersonBody->SetVisibility(true);HandsFailure.Empty();
 return true;
}
FString ASub01HomeCharacter::GetHandsReadiness() const {
 return HandsFailure.IsEmpty()?HandsPosture.ToString()+TEXT(": verified native skeletal clip bound."):HandsFailure;
}
void ASub01HomeCharacter::PreviewHandsPose(FName Posture) {
 SetHandsPosture(Posture);
 UE_LOG(LogTemp,Display,TEXT("SUB01_HANDS_PREVIEW_ONLY %s; backend/device activity unchanged."),*GetHandsReadiness());
}
void ASub01HomeCharacter::Tick(float DeltaSeconds) {
 Super::Tick(DeltaSeconds);
 UpdateNativeCapture();
 if(!HandsFailure.IsEmpty())return;
 auto* Instance=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance());if(!Instance)return;
 const float Speed=GetVelocity().Size2D();
 const bool Moving=HandsPosture==TEXT("Walk")&&GetCharacterMovement()->IsMovingOnGround()&&Speed>1;
 const float Weight=Moving?FMath::Clamp(Speed/140.f,0.f,1.f):0;
 MotionWeight=FMath::FInterpTo(MotionWeight,Weight,DeltaSeconds,10);
 if(Moving)WalkPhase+=FMath::Min(DeltaSeconds,.1f)*(Speed/140.f)*7.5f;
 // Only sub-centimetre camera-relative sway; no finger/bone deformation.
 // Phase freezes at idle and amplitude fades to zero, never perpetual bob.
 FirstPersonBody->SetRelativeLocation(HandsBaseOffset+FVector(0,FMath::Sin(WalkPhase)*.25f*MotionWeight,FMath::Sin(2*WalkPhase)*.15f*MotionWeight));
 UAnimSequence* Clip=HandsClips.FindRef(HandsPosture);
 if(HandsPosture==TEXT("Walk")&&!Moving&&HandsClips.Contains(TEXT("Idle")))Clip=HandsClips.FindRef(TEXT("Idle"));
 Instance->TargetSequence=Clip;
 Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?FMath::Clamp(Speed/140.f,.1f,1.2f):0.f):1.f;
}
'''

def stage_hands(module):
    (module/'Sub01HomeHands.h').write_text(HEADER)
    (module/'Sub01HomeHands.cpp').write_text(CPP)
