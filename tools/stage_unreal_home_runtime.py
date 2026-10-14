"""Generate a native walking Character module for the already staged private UE project.

Run on the server; compile with the official Unreal Build.sh. No Python tick
pretends to be runtime player controls and no backend action is faked.
"""
import argparse
import json
import shutil
from pathlib import Path
from unreal_home_hands_runtime import CHARACTER_FIELDS, CHARACTER_METHODS, stage_hands
from unreal_native_route import FIELDS as ROUTE_FIELDS, METHODS as ROUTE_METHODS
from unreal_hands_diagnostic import FIELDS as DIAGNOSTIC_FIELDS, METHODS as DIAGNOSTIC_METHODS
from unreal_pc_runtime import FIELDS as PC_FIELDS, METHODS as PC_METHODS
from unreal_contact_recording import FIELDS as CONTACT_RECORD_FIELDS, METHODS as CONTACT_RECORD_METHODS
from unreal_live_home_runtime import install as install_live_home
from unreal_native_control import install as install_native_control
from unreal_native_view_settings import install as install_native_view_settings
from unreal_exit_door_runtime import install as install_exit_doors
from unreal_minecraft_tv_input import install as install_minecraft_tv_input
from unreal_phone_grip_diagnostic import install as install_phone_grip_diagnostic
from unreal_native_viewer_handoff import install as install_native_viewer_handoff
from unreal_controller_grip_diagnostic import install as install_controller_grip_diagnostic
from exterior_backdrop_geometry import patch_native_view_settings
from unreal_first_person_motion import install as install_first_person_motion, stage as stage_first_person_motion

HEADER = r'''#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "Sub01HomeLab.generated.h"
class UCameraComponent;
class UAnimSequence;
class USkeletalMeshComponent;
class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class USub01PCBridge;
UCLASS(Config=Game)
class SUB01HOMELAB_API ASub01HomeCharacter : public ACharacter {
 GENERATED_BODY()
 public: ASub01HomeCharacter();
 virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
 virtual void BeginPlay() override;
 private: UPROPERTY() TObjectPtr<UCameraComponent> ViewCamera;
 void Forward(float Value); void Right(float Value); void Interact();
};
UCLASS()
class SUB01HOMELAB_API ASub01HomeGameMode : public AGameModeBase {
 GENERATED_BODY()
 public: ASub01HomeGameMode();
};
'''
CPP = r'''#include "Sub01HomeLab.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "CollisionShape.h"
#include "CollisionQueryParams.h"
#include "Modules/ModuleManager.h"
#include "Misc/CoreDelegates.h"
class FSub01HomeRuntimeModule : public FDefaultGameModuleImpl {
 FDelegateHandle EngineFrameHandle,WorldTickHandle;
 bool EngineFrameLogged=false,WorldTickLogged=false;
 public:
 virtual void StartupModule() override {
  FDefaultGameModuleImpl::StartupModule();
  EngineFrameHandle=FCoreDelegates::OnBeginFrame.AddLambda([this](){if(!EngineFrameLogged){EngineFrameLogged=true;UE_LOG(LogTemp,Display,TEXT("SUB01_FIRST_ENGINE_BEGIN_FRAME independent of actor tick"));}});
  WorldTickHandle=FWorldDelegates::OnWorldTickStart.AddLambda([this](UWorld* World,ELevelTick TickType,float Dt){if(World&&World->IsGameWorld()&&!WorldTickLogged){WorldTickLogged=true;UE_LOG(LogTemp,Display,TEXT("SUB01_FIRST_GAME_WORLD_TICK world=%s type=%d dt=%.6f independent of actor tick"),*World->GetName(),int32(TickType),Dt);}});
 }
 virtual void ShutdownModule() override {
  FCoreDelegates::OnBeginFrame.Remove(EngineFrameHandle);
  FWorldDelegates::OnWorldTickStart.Remove(WorldTickHandle);
  FDefaultGameModuleImpl::ShutdownModule();
 }
};
IMPLEMENT_PRIMARY_GAME_MODULE(FSub01HomeRuntimeModule,Sub01HomeLab,"Sub01HomeLab");
ASub01HomeCharacter::ASub01HomeCharacter() {
 GetCapsuleComponent()->InitCapsuleSize(16.f,91.f);
 GetMesh()->SetVisibility(false);
 bUseControllerRotationYaw=true;
 ViewCamera=CreateDefaultSubobject<UCameraComponent>(TEXT("FirstPersonEye"));
 ViewCamera->SetupAttachment(GetCapsuleComponent());
 ViewCamera->PostProcessSettings.bOverride_MotionBlurAmount=true;ViewCamera->PostProcessSettings.MotionBlurAmount=0;ViewCamera->PostProcessSettings.bOverride_MotionBlurMax=true;ViewCamera->PostProcessSettings.MotionBlurMax=0;
 ViewCamera->SetRelativeLocation(FVector(0,0,74)); // 91+74=165cm eye above feet.
 ViewCamera->bUsePawnControlRotation=true; ViewCamera->FieldOfView=75;
 auto* Movement=GetCharacterMovement();
 Movement->MaxWalkSpeed=140; Movement->MaxAcceleration=450;
 Movement->BrakingDecelerationWalking=700; Movement->MaxStepHeight=22;
 Movement->SetWalkableFloorAngle(50); Movement->bOrientRotationToMovement=false;
}
void ASub01HomeCharacter::BeginPlay() {
 Super::BeginPlay();
 UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_INIT_INPUT_MODE_BEGIN controller=%s"),*GetNameSafe(GetController()));
 if(auto* Player=Cast<APlayerController>(GetController())) {
  Player->SetInputMode(FInputModeGameOnly()); Player->bShowMouseCursor=false;
 }
 UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_BEGINPLAY_RETURN tickCanEver=%d tickEnabled=%d"),PrimaryActorTick.bCanEverTick?1:0,IsActorTickEnabled()?1:0);
}
void ASub01HomeCharacter::SetupPlayerInputComponent(UInputComponent* Input) {
 Super::SetupPlayerInputComponent(Input);
 Input->BindAxis("MoveForward",this,&ASub01HomeCharacter::Forward);
 Input->BindAxis("MoveRight",this,&ASub01HomeCharacter::Right);
 Input->BindAxis("Turn",this,&APawn::AddControllerYawInput);
 Input->BindAxis("LookUp",this,&APawn::AddControllerPitchInput);
 Input->BindAction("Interact",IE_Pressed,this,&ASub01HomeCharacter::Interact);
}
void ASub01HomeCharacter::Forward(float Value) {
 if(Controller&&Value!=0) AddMovementInput(FRotationMatrix(FRotator(0,Controller->GetControlRotation().Yaw,0)).GetUnitAxis(EAxis::X),Value);
}
void ASub01HomeCharacter::Right(float Value) {
 if(Controller&&Value!=0) AddMovementInput(FRotationMatrix(FRotator(0,Controller->GetControlRotation().Yaw,0)).GetUnitAxis(EAxis::Y),Value);
}
void ASub01HomeCharacter::Interact() {
 FHitResult Hit; FCollisionQueryParams Query; Query.AddIgnoredActor(this);
 const FVector Start=ViewCamera->GetComponentLocation();
 if(!GetWorld()->LineTraceSingleByChannel(Hit,Start,Start+ViewCamera->GetForwardVector()*200,ECC_Visibility,Query)) return;
 FString Device;
 if(auto* Component=Hit.GetComponent()) for(const auto& Tag:Component->ComponentTags)
  if(Tag.ToString().StartsWith(TEXT("SUB01Device:"))) { Device=Tag.ToString().RightChop(12); break; }
 if(Device.IsEmpty()) return;
 // Explicit until the existing authenticated backend is actually wired; never
 // launch synthetic browser/game actions or present a static screen as live.
 if(GEngine)GEngine->AddOnScreenDebugMessage(-1,4,FColor::Orange,Device+TEXT(": backend is not connected in this Unreal authoring build."));
}
ASub01HomeGameMode::ASub01HomeGameMode(){DefaultPawnClass=ASub01HomeCharacter::StaticClass();}
'''

def stage(project):
    project=Path(project)
    module=project/'Source/Sub01HomeLab';module.mkdir(parents=True,exist_ok=True)
    header = HEADER.replace(' void Forward(float Value);', CHARACTER_FIELDS + ROUTE_FIELDS + DIAGNOSTIC_FIELDS + PC_FIELDS + CONTACT_RECORD_FIELDS + '\n void Forward(float Value);')
    cpp = CPP.replace('#include "Sub01HomeLab.h"', '#include "Sub01HomeLab.h"\n#include "Sub01HomeHands.h"\n#include "Animation/AnimSequence.h"\n#include "Engine/SkeletalMesh.h"\n#include "Sub01PCBridge.h"\n#include "Components/StaticMeshComponent.h"\n#include "Materials/MaterialInterface.h"\n#include "EngineUtils.h"\n#include "TimerManager.h"\n#include "UnrealClient.h"\n#include "Components/SceneCaptureComponent2D.h"\n#include "Engine/TextureRenderTarget2D.h"\n#include "ImageUtils.h"\n#include "RenderingThread.h"\n#include "Misc/FileHelper.h"\n#include "Serialization/JsonSerializer.h"\n#include "Serialization/JsonReader.h"\n#include "Misc/CommandLine.h"\n#include "Misc/Parse.h"\n#include "Misc/Paths.h"\n#include "HAL/FileManager.h"\n#include "HAL/PlatformTime.h"\n#include "HAL/PlatformMisc.h"')
    cpp = cpp.replace(' GetCapsuleComponent()->InitCapsuleSize', ''' PrimaryActorTick.bCanEverTick=true;
 PCBridge=CreateDefaultSubobject<USub01PCBridge>(TEXT("ActualPrivatePCBridge"));
 FirstPersonBody=CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("RealFirstPersonBody"));
 GetCapsuleComponent()->InitCapsuleSize''')
    cpp = cpp.replace(' ViewCamera->bUsePawnControlRotation', ''' FirstPersonBody->SetupAttachment(ViewCamera);
 FirstPersonBody->SetOnlyOwnerSee(true);FirstPersonBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
 FirstPersonBody->SetCastShadow(false);FirstPersonBody->SetVisibility(false);
 ViewCamera->bUsePawnControlRotation''')
    cpp = cpp.replace(' Super::BeginPlay();', ''' Super::BeginPlay();
 UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_INIT_BEGIN"));
 LoadHandsAssets();
 UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_INIT_ASSETS_DONE"));
 LoadPrivateHandsDiagnostic();
 UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_INIT_POSE_DONE"));
 ConfigureActualPC();
 UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_INIT_PC_DONE"));
 if(FParse::Value(FCommandLine::Get(),TEXT("Sub01CaptureAfter="),CaptureAfter)){
  CaptureAfter=FMath::Clamp(CaptureAfter,1.f,180.f);CaptureStarted=FPlatformTime::Seconds();
  CaptureViewport=FParse::Param(FCommandLine::Get(),TEXT("Sub01CaptureViewport"));
  FParse::Value(FCommandLine::Get(),TEXT("Sub01CapturePath="),CapturePath);
  if(CapturePath.IsEmpty())CapturePath=FPaths::Combine(FPaths::ProjectSavedDir(),TEXT("Screenshots/Sub01NativeGame.png"));
  CapturePath=FPaths::ConvertRelativePathToFull(CapturePath);
  IFileManager::Get().MakeDirectory(*FPaths::GetPath(CapturePath),true);
  IFileManager::Get().Delete(*CapturePath);
 }''' )
    (module/'Sub01HomeLab.h').write_text(header)
    input_marker=' UE_LOG(LogTemp,Display,TEXT("SUB01_NATIVE_INIT_INPUT_MODE_BEGIN controller=%s"),*GetNameSafe(GetController()));'
    cpp=cpp.replace(input_marker,' BeginNativeRouteTest();\n'+input_marker,1)
    cpp=cpp.replace(' if(Device.IsEmpty()) return;', ' if(Device.IsEmpty()) return;\n if(Device==TEXT("Desk")&&PCBridge){if(LiveHome&&!NativeSeatVerified){PCBridge->SetOperatorFocus(false);if(GEngine)GEngine->AddOnScreenDebugMessage(-1,4,FColor::Orange,TEXT("Physical seating is not verified"));return;}PCBridge->SetOperatorFocus(true);if(GEngine)GEngine->AddOnScreenDebugMessage(-1,4,FColor::Orange,PCBridge->GetPCStatus());return;}')
    cpp=cpp.replace(' FString Device;\n', ' if(TryNativeHomeDevice(Hit.GetComponent()))return;\n FString Device;\n',1)
    header,cpp=install_live_home(header,cpp + CHARACTER_METHODS.replace(' UpdateNativeCapture();', ' UpdateNativeContactRecording();\n UpdateNativeCapture();') + ROUTE_METHODS + DIAGNOSTIC_METHODS + PC_METHODS + CONTACT_RECORD_METHODS)
    header,cpp=install_native_control(header,cpp)
    header,cpp=install_native_view_settings(header,cpp)
    cpp=patch_native_view_settings(cpp)
    header,cpp=install_minecraft_tv_input(header,cpp)
    header,cpp=install_native_viewer_handoff(header,cpp)
    header,cpp=install_phone_grip_diagnostic(header,cpp)
    header,cpp=install_controller_grip_diagnostic(header,cpp)
    header,cpp=install_exit_doors(header,cpp)
    header,cpp=install_first_person_motion(header,cpp)
    stage_first_person_motion(module)
    header=header.replace(' void Forward(float Value);',' bool ActualNativeTickLogged=false;\n void Forward(float Value);',1)
    cpp=cpp.replace(' Super::Tick(DeltaSeconds);',' Super::Tick(DeltaSeconds);\n if(!ActualNativeTickLogged){ActualNativeTickLogged=true;UE_LOG(LogTemp,Display,TEXT("SUB01_FIRST_ACTUAL_GAME_TICK dt=%.6f pawn=%s"),DeltaSeconds,*GetActorLocation().ToString());}',1)
    (module/'Sub01HomeLab.h').write_text(header)
    # Every adapter may add includes; the native module header must remain first.
    cpp=cpp.replace('#include \"Sub01HomeLab.h\"\n','',1)
    cpp='#include \"Sub01HomeLab.h\"\n'+cpp
    (module/'Sub01HomeLab.cpp').write_text(cpp)
    bridge=Path(__file__).parent/'native_pc_bridge'
    for name in ['Sub01PCBridge.h','Sub01PCBridge.cpp','Sub01GuestInputQueue.h','Sub01GuestFrameLayout.h','Sub01HomeDeviceBridge.h','Sub01HomeDeviceBridge.cpp','Sub01DeviceScreenPolicy.h','Sub01NoteDraft.h']:
        shutil.copy2(bridge/name,module/name)
    stage_hands(module)
    (module/'Sub01HomeLab.Build.cs').write_text('using UnrealBuildTool; public class Sub01HomeLab : ModuleRules { public Sub01HomeLab(ReadOnlyTargetRules Target):base(Target) { PCHUsage=PCHUsageMode.UseExplicitOrSharedPCHs; PublicDependencyModuleNames.AddRange(new string[]{"Core","CoreUObject","Engine","InputCore","AnimGraphRuntime","AnimationCore","RenderCore","RHI","HTTP","Json","JsonUtilities","Slate","SlateCore","ApplicationCore","ImageCore"}); } }\n')
    for name,kind in [('Sub01HomeLab','Game'),('Sub01HomeLabEditor','Editor')]:
        (project/'Source'/f'{name}.Target.cs').write_text(f'using UnrealBuildTool; public class {name}Target : TargetRules {{ public {name}Target(TargetInfo Target):base(Target) {{ Type=TargetType.{kind}; DefaultBuildSettings=BuildSettingsVersion.Latest; ExtraModuleNames.Add("Sub01HomeLab"); }} }}\n')
    path=project/'Sub01HomeLab.uproject';doc=json.loads(path.read_text());doc['Modules']=[{'Name':'Sub01HomeLab','Type':'Runtime','LoadingPhase':'Default'}];path.write_text(json.dumps(doc,indent=2)+'\n')
    (project/'Config/DefaultInput.ini').write_text('''[/Script/Engine.InputSettings]
+AxisMappings=(AxisName="MoveForward",Scale=1.000000,Key=W)
+AxisMappings=(AxisName="MoveForward",Scale=-1.000000,Key=S)
+AxisMappings=(AxisName="MoveRight",Scale=1.000000,Key=D)
+AxisMappings=(AxisName="MoveRight",Scale=-1.000000,Key=A)
+AxisMappings=(AxisName="Turn",Scale=1.000000,Key=MouseX)
+AxisMappings=(AxisName="LookUp",Scale=-1.000000,Key=MouseY)
+ActionMappings=(ActionName="Interact",Key=E)
''')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project',type=Path);args=parser.parse_args();stage(args.project)
    print('Native first-person Character sources staged; not compiled or running yet.')
