"""Native real-clip first-person skeletal pose blending, staged for server compilation."""
from unreal_skin_contact_native import HEADER as SKIN_CONTACT_HEADER, CPP as SKIN_CONTACT_CPP

HEADER = r'''#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Sub01HomeHands.generated.h"
class UAnimSequence;
class USkeletalMesh;
UCLASS(Transient)
class SUB01HOMELAB_API USub01HomeHandsInstance : public UAnimInstance {
 GENERATED_BODY()
 public:
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static int32 FinishPendingSkinCompilation();
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static FString DescribeImportedSkinGeometry(USkeletalMesh* Mesh);
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
#include "Engine/SkeletalMesh.h"
#include "AnimNodes/AnimNode_TwoWayBlend.h"
#if WITH_EDITOR
#include "SkinnedAssetCompiler.h"
#include "Rendering/SkeletalMeshModel.h"
#include "Rendering/SkeletalMeshLODModel.h"
#endif
int32 USub01HomeHandsInstance::FinishPendingSkinCompilation(){
#if WITH_EDITOR
 auto& Manager=FSkinnedAssetCompilingManager::Get();
 Manager.FinishAllCompilation();
 return Manager.GetNumRemainingJobs();
#else
 return -1;
#endif
}
FString USub01HomeHandsInstance::DescribeImportedSkinGeometry(USkeletalMesh* Mesh){
#if WITH_EDITOR
 if(!Mesh)return TEXT("missing");
 auto* Model=Mesh->GetImportedModel();int32 SoftCount=0;FBox Bounds(ForceInit);
 if(Model&&Model->LODModels.Num())for(const auto& Section:Model->LODModels[0].Sections)for(const auto& Vertex:Section.SoftVertices){++SoftCount;Bounds+=FVector(Vertex.Position);}
 return FString::Printf(TEXT("importedVertices=%d lods=%d softVertices=%d min=%s max=%s"),Mesh->GetNumImportedVertices(),Model?Model->LODModels.Num():0,SoftCount,*Bounds.Min.ToString(),*Bounds.Max.ToString());
#else
 return TEXT("editor-only");
#endif
}
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
   if(Progress<1&&Hands->TargetSequence&&Previous.GetSequence()==Hands->TargetSequence.Get()){
    // Reversal of an unfinished blend: swap the players with their own sample times and loop flags,
    // so the blended pose is unchanged at this frame and the way back takes Progress*0.24 s.
    UAnimSequenceBase* Out=Current.GetSequence();const float OutTime=Current.GetAccumulatedTime();const bool OutLoop=Current.IsLooping();
    Current.SetSequence(Previous.GetSequence());Current.SetAccumulatedTime(Previous.GetAccumulatedTime());Current.SetLoopAnimation(Previous.IsLooping());
    Previous.SetSequence(Out);Previous.SetAccumulatedTime(OutTime);Previous.SetLoopAnimation(OutLoop);Previous.SetPlayRate(0);
    Hands->PreviousSequence=Cast<UAnimSequence>(Out);Progress=1-Progress;
   }else{
   Hands->PreviousSequence=Cast<UAnimSequence>(Current.GetSequence());
   Previous.SetSequence(Hands->PreviousSequence?Hands->PreviousSequence.Get():Hands->TargetSequence.Get());
   Previous.SetAccumulatedTime(Current.GetAccumulatedTime());Previous.SetLoopAnimation(Current.IsLooping());
   Previous.SetPlayRate(0);
   Current.SetSequence(Hands->TargetSequence); Current.SetAccumulatedTime(0);
   Progress=Hands->PreviousSequence?0:1;
   }
  }
  Current.SetPlayRate(Hands->TargetRate);
 }
 virtual void CacheBones() override {
  FAnimationCacheBonesContext Context(this); Blend.CacheBones_AnyThread(Context);
 }
 virtual void Update(float DeltaSeconds) override {
  Progress=FMath::Min(1.f,Progress+FMath::Min(DeltaSeconds,.1f)/.24f);
  Blend.Alpha=Progress;
 }
 virtual void UpdateAnimationNode(const FAnimationUpdateContext& Context) override {
  Blend.Update_AnyThread(Context);
 }
 virtual bool Evaluate(FPoseContext& Output) override {Blend.Evaluate_AnyThread(Output);return true;}
};
FAnimInstanceProxy* USub01HomeHandsInstance::CreateAnimInstanceProxy(){return new FSub01HandsProxy(this);}
void USub01HomeHandsInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy){delete Proxy;}
'''

HEADER = HEADER.replace(' protected:', SKIN_CONTACT_HEADER + '\n protected:')
CPP += SKIN_CONTACT_CPP
from unreal_contact_profile_runtime import install as install_contact_profile
import unreal_hands_diagnostic
HEADER,CPP,unreal_hands_diagnostic.METHODS=install_contact_profile(HEADER,CPP,unreal_hands_diagnostic.METHODS)

CHARACTER_FIELDS = r'''
 public:
 virtual void Tick(float DeltaSeconds) override;
 UFUNCTION(BlueprintCallable,Category="SUB01|Hands") bool SetHandsPosture(FName Posture);
 UFUNCTION(BlueprintPure,Category="SUB01|Hands") FString GetHandsReadiness() const;
 UFUNCTION(Exec) void PreviewHandsPose(FName Posture);
 UFUNCTION(Exec) void ReloadPrivateWalkingHands();
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString HandsMeshPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString IdleClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString WalkClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString TypingClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString MouseClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FString PhoneClipPath;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") TArray<FName> ValidatedHandsPostures;
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FVector WalkMeshOffset=FVector(0,0,-91);
 UPROPERTY(EditAnywhere,Config,Category="SUB01|Hands") FVector WalkingCameraOffset=FVector(0,0,74);
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
 bool CaptureViewport=false;
 UPROPERTY() TObjectPtr<USceneCaptureComponent2D> NativeCapture;
 UPROPERTY() TObjectPtr<UTextureRenderTarget2D> NativeCaptureTarget;
 int32 CaptureWarmFrames=0;
'''

CHARACTER_METHODS = r'''
void ASub01HomeCharacter::UpdateNativeCapture() {
 if(CaptureAfter<0)return;
 const double Now=FPlatformTime::Seconds();
 if(!CaptureRequested&&Now-CaptureStarted>=CaptureAfter){
  CaptureRequested=true;CaptureRequestedAt=Now;
  const FVector Eye=ViewCamera->GetComponentLocation(),Position=GetActorLocation();
  UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_GAME_CAPTURE pawn=%s eye=%s capsuleRadius=%.3f capsuleHalfHeight=%.3f mode=%d floor=%d hands=%s path=%s"),*Position.ToString(),*Eye.ToString(),GetCapsuleComponent()->GetScaledCapsuleRadius(),GetCapsuleComponent()->GetScaledCapsuleHalfHeight(),int32(GetCharacterMovement()->MovementMode),GetCharacterMovement()->IsMovingOnGround()?1:0,*GetHandsReadiness(),*CapturePath);
  if(CaptureViewport){
   UE_LOG(LogTemp,Display,TEXT("SUB01_CAPTURE_METHOD actual GameViewport FScreenshotRequest; no separate scene pass"));
   FScreenshotRequest::RequestScreenshot(CapturePath,false,false);
  }else{
  NativeCaptureTarget=NewObject<UTextureRenderTarget2D>(this);
  NativeCaptureTarget->InitCustomFormat(1280,720,PF_B8G8R8A8,false);
  NativeCaptureTarget->UpdateResourceImmediate(true);
  NativeCapture=NewObject<USceneCaptureComponent2D>(this);
  NativeCapture->TextureTarget=NativeCaptureTarget;
  NativeCapture->CaptureSource=ESceneCaptureSource::SCS_FinalColorLDR;
  NativeCapture->bCaptureEveryFrame=false;NativeCapture->bCaptureOnMovement=false;
  NativeCapture->bAlwaysPersistRenderingState=true;
  NativeCapture->PostProcessSettings=ViewCamera->PostProcessSettings;
  NativeCapture->PostProcessBlendWeight=ViewCamera->PostProcessBlendWeight;
  NativeCapture->RegisterComponent();
  UE_LOG(LogTemp,Display,TEXT("SUB01_CAPTURE_METHOD SceneCapture2D actual pawn POV; separate view history, not viewport-identical"));
  }
 }
 if(NativeCapture&&NativeCaptureTarget&&CaptureWarmFrames<32){
  NativeCapture->SetWorldTransform(ViewCamera->GetComponentTransform());
  NativeCapture->FOVAngle=ViewCamera->FieldOfView;
  NativeCapture->CaptureScene();++CaptureWarmFrames;
  if(CaptureWarmFrames==32){
   FlushRenderingCommands();
   TArray<FColor> Pixels;FReadSurfaceDataFlags Flags(RCM_UNorm);Flags.SetLinearToGamma(false);
   const bool Read=NativeCaptureTarget->GameThread_GetRenderTargetResource()->ReadPixels(Pixels,Flags);
   UE_LOG(LogTemp,Display,TEXT("SUB01_CAPTURE_READ read=%d pixels=%d target=%dx%d path=%s directoryExists=%d"),Read?1:0,Pixels.Num(),NativeCaptureTarget->SizeX,NativeCaptureTarget->SizeY,*CapturePath,IFileManager::Get().DirectoryExists(*FPaths::GetPath(CapturePath))?1:0);
   if(Read&&Pixels.Num()==1280*720){
    // This is an opaque POV frame, not a compositing matte. FinalColorLDR
    // alpha can be zero even when its RGB contains a valid captured scene.
    for(FColor& Pixel:Pixels)Pixel.A=255;
    TArray64<uint8> PNG;
    FImageUtils::PNGCompressImageArray(1280,720,TArrayView64<const FColor>(Pixels.GetData(),Pixels.Num()),PNG);
    UE_LOG(LogTemp,Display,TEXT("SUB01_CAPTURE_ENCODE pngBytes=%lld firstPixel=%s PNGSignature=%d"),int64(PNG.Num()),*Pixels[0].ToString(),PNG.Num()>8&&PNG[0]==137&&PNG[1]==80&&PNG[2]==78&&PNG[3]==71?1:0);
    const bool Saved=FFileHelper::SaveArrayToFile(PNG,*CapturePath);
    const uint32 SaveError=FPlatformMisc::GetLastError();
    UE_LOG(LogTemp,Display,TEXT("SUB01_CAPTURE_SAVE saved=%d fileBytes=%lld osError=%u path=%s"),Saved?1:0,IFileManager::Get().FileSize(*CapturePath),SaveError,*CapturePath);
    if(!Saved)UE_LOG(LogTemp,Error,TEXT("SUB01_CAPTURE_WRITE_FAILED"));
   }else UE_LOG(LogTemp,Error,TEXT("SUB01_CAPTURE_READ_FAILED pixels=%d"),Pixels.Num());
   NativeCapture->DestroyComponent();NativeCapture=nullptr;
   NativeCaptureTarget->ReleaseResource();NativeCaptureTarget=nullptr;
  }
 }
 if(CaptureRequested&&Now-CaptureRequestedAt>1&&IFileManager::Get().FileSize(*CapturePath)>0){
  UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_GAME_CAPTURE_SAVED bytes=%lld"),IFileManager::Get().FileSize(*CapturePath));
  CaptureAfter=-1;
  if(FParse::Param(FCommandLine::Get(),TEXT("Sub01ExitAfterCapture")))FPlatformMisc::RequestExitWithStatus(false,RouteFailed?2:0);
 }else if(CaptureRequested&&Now-CaptureRequestedAt>40){
  UE_LOG(LogTemp,Error,TEXT("SUB01_NATIVE_GAME_CAPTURE_FAILED no image written"));
  CaptureAfter=-1;
  if(FParse::Param(FCommandLine::Get(),TEXT("Sub01ExitAfterCapture")))FPlatformMisc::RequestExitWithStatus(false,2);
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
 // A full body follows capsule yaw, never camera pitch. Looking down must
 // not rotate the feet through the floor. Legacy desk placement remains gated;
 // the verified private desk diagnostic applies its explicit world anchor below.
 if(Posture==TEXT("Walk")||Posture==TEXT("Phone")){
  FirstPersonBody->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);
  FirstPersonBody->SetRelativeRotation(HandsMeshRotation);
 }else if(!HandsDiagnosticSeat){
  FirstPersonBody->AttachToComponent(ViewCamera,FAttachmentTransformRules::KeepWorldTransform);
 }
 HandsBaseOffset=Posture.ToString().StartsWith(TEXT("Desk"))?DeskMeshOffset:WalkMeshOffset;
 if(auto* Instance=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance())){
  Instance->TargetSequence=HandsClips.FindRef(Posture);
  Instance->TargetRate=Posture==TEXT("Walk")?0.f:1.f;
 }
 // Stable eye offset is reviewed independently of floor/body alignment.
 if(Posture==TEXT("Walk")&&!HandsDiagnostic&&ViewCamera->GetAttachParent()==GetRootComponent()&&!WalkingCameraOffset.ContainsNaN())ViewCamera->SetRelativeLocation(WalkingCameraOffset);
 FirstPersonBody->SetRelativeLocation(HandsBaseOffset);
 FirstPersonBody->SetVisibility(true);HandsFailure.Empty();
 return true;
}
FString ASub01HomeCharacter::GetHandsReadiness() const {
 if(HandsDiagnostic)return TEXT("UNVERIFIED PRIVATE POSE DIAGNOSTIC: ")+HandsPosture.ToString();
 return HandsFailure.IsEmpty()?HandsPosture.ToString()+TEXT(": verified native skeletal clip bound."):HandsFailure;
}
void ASub01HomeCharacter::PreviewHandsPose(FName Posture) {
 SetHandsPosture(Posture);
 UE_LOG(LogTemp,Display,TEXT("SUB01_HANDS_PREVIEW_ONLY %s; backend/device activity unchanged."),*GetHandsReadiness());
}
void ASub01HomeCharacter::ReloadPrivateWalkingHands() {
 // Manual private QA only: never tear down an active seat/device pose.
 if(HandsDiagnostic||HandsPosture!=TEXT("Walk")||NativeSeatVerified||MinecraftFocused||
    (PCBridge&&PCBridge->HasOperatorFocus())){
  UE_LOG(LogTemp,Warning,TEXT("SUB01_WALKING_CONFIG_RELOAD_REFUSED active posture/device"));return;
 }
 ReloadConfig();
 HandsClips.Empty();
 FirstPersonBody->SetVisibility(false);
 LoadHandsAssets();
 UE_LOG(LogTemp,Display,TEXT("SUB01_WALKING_CONFIG_RELOADED binding=%s; floor/POV acceptance remains separate"),*GetHandsReadiness());
}
void ASub01HomeCharacter::Tick(float DeltaSeconds) {
 Super::Tick(DeltaSeconds);
 UpdateNativeRouteTest();
 UpdateNativePCPrivacy();
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
 if(!HandsDiagnosticSeat){
  const bool CameraRelative=FirstPersonBody->GetAttachParent()==ViewCamera;
  FirstPersonBody->SetRelativeLocation(HandsBaseOffset+(CameraRelative?FVector(0,FMath::Sin(WalkPhase)*.25f*MotionWeight,FMath::Sin(2*WalkPhase)*.15f*MotionWeight):FVector::ZeroVector));
 }
 UAnimSequence* Clip=HandsClips.FindRef(HandsPosture);
 if(HandsPosture==TEXT("Walk")&&!Moving&&HandsClips.Contains(TEXT("Idle")))Clip=HandsClips.FindRef(TEXT("Idle"));
 Instance->TargetSequence=Clip;
 const bool PlayingIdle=HandsPosture==TEXT("Walk")&&!Moving&&Clip&&Clip==HandsClips.FindRef(TEXT("Idle")).Get();
 Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?FMath::Clamp(Speed/140.f,.1f,1.2f):(PlayingIdle?1.f:0.f)):1.f;
}
'''

def stage_hands(module):
    (module/'Sub01HomeHands.h').write_text(HEADER)
    (module/'Sub01HomeHands.cpp').write_text(CPP)
