"""Generate a native walking Character module for the already staged private UE project.

Run on the server; compile with the official Unreal Build.sh. No Python tick
pretends to be runtime player controls and no backend action is faked.
"""
import argparse
import json
from pathlib import Path

HEADER = r'''#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "GameFramework/GameModeBase.h"
#include "Sub01HomeLab.generated.h"
class UCameraComponent;
UCLASS()
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
#include "Modules/ModuleManager.h"
IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl,Sub01HomeLab,"Sub01HomeLab");
ASub01HomeCharacter::ASub01HomeCharacter() {
 GetCapsuleComponent()->InitCapsuleSize(16.f,91.f);
 GetMesh()->SetVisibility(false);
 bUseControllerRotationYaw=true;
 ViewCamera=CreateDefaultSubobject<UCameraComponent>(TEXT("FirstPersonEye"));
 ViewCamera->SetupAttachment(GetCapsuleComponent());
 ViewCamera->SetRelativeLocation(FVector(0,0,74)); // 91+74=165cm eye above feet.
 ViewCamera->bUsePawnControlRotation=true; ViewCamera->FieldOfView=75;
 auto* Movement=GetCharacterMovement();
 Movement->MaxWalkSpeed=140; Movement->MaxAcceleration=450;
 Movement->BrakingDecelerationWalking=700; Movement->MaxStepHeight=22;
 Movement->SetWalkableFloorAngle(50); Movement->bOrientRotationToMovement=false;
}
void ASub01HomeCharacter::BeginPlay() {
 Super::BeginPlay();
 if(auto* Player=Cast<APlayerController>(GetController())) {
  Player->SetInputMode(FInputModeGameOnly()); Player->bShowMouseCursor=false;
 }
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
    (module/'Sub01HomeLab.h').write_text(HEADER)
    (module/'Sub01HomeLab.cpp').write_text(CPP)
    (module/'Sub01HomeLab.Build.cs').write_text('using UnrealBuildTool; public class Sub01HomeLab : ModuleRules { public Sub01HomeLab(ReadOnlyTargetRules Target):base(Target) { PCHUsage=PCHUsageMode.UseExplicitOrSharedPCHs; PublicDependencyModuleNames.AddRange(new string[]{"Core","CoreUObject","Engine","InputCore"}); } }\n')
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
