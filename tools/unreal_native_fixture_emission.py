"""Disabled-by-default native fixture emission, activated only after actual audit review.

Renderer owns integration/build. Reviewed config must set NativeFixtureEmissionVerified
and NativeFixtureEmissionParentPath, plus exact source SHA below. No asset writes;
original shared materials stay untouched. install hooks the native view settings.
"""
from pathlib import Path

POLICY = r'''#pragma once
#include <cmath>
namespace Sub01NativeFixtureEmission {
inline bool ValidOriginalFactor(double R,double G,double B,double A){
 return std::isfinite(R)&&std::isfinite(G)&&std::isfinite(B)&&std::isfinite(A)&&R>=0&&G>=0&&B>=0&&(R>0||G>0||B>0);
}
}
'''
INCLUDES = r'''
#include "Sub01NativeFixtureEmissionPolicy.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Components/StaticMeshComponent.h"
'''
FIELDS = r'''
 UPROPERTY(Config) bool NativeFixtureEmissionVerified=false;
 UPROPERTY(Config) FString NativeFixtureEmissionParentPath;
 UPROPERTY(Config) FString NativeFixtureEmissionSourceSHA;
 UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> NativeFixtureComponents;
 UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> NativeFixtureMIDs;
 TArray<FLinearColor> NativeFixtureOriginalFactors;
 TArray<FString> NativeFixtureLampNames;
 FString NativeFixtureEmissionError;
 bool PrepareNativeFixtureEmission();
 void ApplyNativeFixtureEmission(const FString& Lamp,bool Enabled);
'''
METHODS = r'''
bool ASub01HomeCharacter::PrepareNativeFixtureEmission(){
 if(!NativeFixtureEmissionVerified){NativeFixtureEmissionError=TEXT("Fixture emission disabled pending actual parameter/parent receipt review");return true;}
 auto Refuse=[&](const FString& Error){NativeFixtureEmissionError=Error;UE_LOG(LogTemp,Error,TEXT("SUB01_FIXTURE_EMISSION_UNAVAILABLE %s"),*Error);return false;};
 if(NativeFixtureEmissionSourceSHA!=TEXT("9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b")||NativeFixtureEmissionParentPath.IsEmpty())return Refuse(TEXT("Reviewed source identity/parent receipt missing"));
 if(NativeFixtureMIDs.Num()){
  if(NativeFixtureMIDs.Num()!=6||NativeFixtureComponents.Num()!=6||NativeFixtureOriginalFactors.Num()!=6||NativeFixtureLampNames.Num()!=6)return Refuse(TEXT("Incomplete owned fixture state"));
  for(int32 I=0;I<6;++I)if(!IsValid(NativeFixtureComponents[I])||!IsValid(NativeFixtureMIDs[I])||NativeFixtureComponents[I]->GetMaterial(0)!=NativeFixtureMIDs[I])return Refuse(TEXT("Owned fixture slot changed externally"));
  return true;
 }
 struct FTarget {int32 Node;const TCHAR* Material;const TCHAR* Lamp;};
 const FTarget Targets[]={{66,TEXT("Material_13"),TEXT("KitchenWork")},{126,TEXT("Material_63"),TEXT("DeskLamp")},{127,TEXT("Material_63"),TEXT("LowerPendant")},{129,TEXT("Material_63"),TEXT("UpperPendant")},{198,TEXT("Material_63"),TEXT("BedLamp")},{199,TEXT("Material_91"),TEXT("BedLamp")}};
 TArray<UStaticMeshComponent*> Components;TArray<UMaterialInstance*> Originals;TArray<FLinearColor> Factors;TArray<bool> Enabled;
 for(const auto& Target:Targets){
  AActor* Found=nullptr;const FString ActorName=FString::Printf(TEXT("full-home_node_%d"),Target.Node);
  for(TActorIterator<AActor> It(GetWorld());It;++It)if(It->GetName()==ActorName){if(Found)return Refuse(TEXT("Duplicate exact source fixture actor"));Found=*It;}
  if(!Found)return Refuse(TEXT("Exact source fixture actor missing: ")+ActorName);
  TArray<UStaticMeshComponent*> Meshes;Found->GetComponents<UStaticMeshComponent>(Meshes);
  if(Meshes.Num()!=1||Meshes[0]->GetName()!=TEXT("StaticMeshComponent0")||Meshes[0]->GetNumMaterials()!=1)return Refuse(TEXT("Exact fixture component/slot identity differs"));
  auto* Component=Meshes[0];auto* Material=Cast<UMaterialInstance>(Component->GetMaterial(0));
  const FString Expected=FString(TEXT("/Game/Sub01Home/ImportedScene/full-home/Materials/"))+Target.Material+TEXT(".")+Target.Material;
  if(!Material||Material->GetPathName()!=Expected||!Material->Parent||Material->Parent->GetPathName()!=NativeFixtureEmissionParentPath)return Refuse(TEXT("Actual fixture binding/parent differs from reviewed receipt"));
  TArray<FMaterialParameterInfo> Infos;TArray<FGuid> IDs;Material->GetAllVectorParameterInfo(Infos,IDs);
  int32 Matches=0;for(const auto& Info:Infos)if(Info.Name==TEXT("EmissiveFactor")&&Info.Association==EMaterialParameterAssociation::GlobalParameter)++Matches;
  FLinearColor Factor;
  if(Matches!=1||!Material->GetVectorParameterValue(FMaterialParameterInfo(TEXT("EmissiveFactor")),Factor)||!Sub01NativeFixtureEmission::ValidOriginalFactor(Factor.R,Factor.G,Factor.B,Factor.A))return Refuse(TEXT("Enumerated effective EmissiveFactor missing, nonfinite, negative or zero"));
  auto* LampActor=FindAuthoredSettingsActor(FString(TEXT("SUB01_AuthoredLight_"))+Target.Lamp);auto* Light=LampActor?LampActor->FindComponentByClass<ULightComponent>():nullptr;
  if(!Light||!FMath::IsFinite(Light->Intensity)||Light->Intensity<0)return Refuse(TEXT("Exact associated native lamp intensity unavailable"));
  Components.Add(Component);Originals.Add(Material);Factors.Add(Factor);Enabled.Add(Light->Intensity>0);
 }
 // Any additional mesh slot using an original fixture material is ambiguous,
 // including screens. No original material is ever modified.
 for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UMeshComponent*> Meshes;It->GetComponents<UMeshComponent>(Meshes);
  for(auto* Mesh:Meshes)for(int32 Slot=0;Slot<Mesh->GetNumMaterials();++Slot)if(Originals.Contains(Cast<UMaterialInstance>(Mesh->GetMaterial(Slot)))&&(!Components.Contains(Cast<UStaticMeshComponent>(Mesh))||Slot!=0))return Refuse(TEXT("Unexpected shared original fixture material user"));
 }
 TArray<UMaterialInstanceDynamic*> Prepared;
 for(int32 I=0;I<6;++I){auto* MID=UMaterialInstanceDynamic::Create(Originals[I],this);if(!MID)return Refuse(TEXT("MID allocation failed; no fixture slot/light changed"));MID->SetVectorParameterValue(TEXT("EmissiveFactor"),Enabled[I]?Factors[I]:FLinearColor(0,0,0,0));Prepared.Add(MID);}
 // All six bindings, effective original vectors and allocations validated first.
 for(int32 I=0;I<6;++I){NativeFixtureComponents.Add(Components[I]);NativeFixtureMIDs.Add(Prepared[I]);NativeFixtureOriginalFactors.Add(Factors[I]);NativeFixtureLampNames.Add(Targets[I].Lamp);Components[I]->SetMaterial(0,Prepared[I]);}
 NativeFixtureEmissionError.Empty();UE_LOG(LogTemp,Display,TEXT("SUB01_FIXTURE_EMISSION_READY exactTargets=6 originalsUnchanged=true"));return true;
}
void ASub01HomeCharacter::ApplyNativeFixtureEmission(const FString& Lamp,bool Enabled){
 if(!NativeFixtureEmissionVerified)return;
 for(int32 I=0;I<NativeFixtureMIDs.Num();++I)if(NativeFixtureLampNames[I]==Lamp)NativeFixtureMIDs[I]->SetVectorParameterValue(TEXT("EmissiveFactor"),Enabled?NativeFixtureOriginalFactors[I]:FLinearColor(0,0,0,0));
}
'''


def install(header, cpp):
    field_hook=' void InitializePrivateViewSettings();'
    init_hook=' if(PrivateSettingsInitialized)return;PrivateSettingsInitialized=true;WritePrivateViewSettingsReceipt(0,true,TEXT(""));'
    preflight=' // All fields are validated before any renderer state is changed. SUN is not an indoor lamp.'
    apply_hook='Light->SetIntensity(Enabled?Lamps[LampName]:0.f);'
    receipt_hook='Receipt->SetStringField(TEXT("error"),Error);'
    include='#include "Sub01HomeLab.h"'
    for text, hook in ((header, field_hook), (cpp, init_hook), (cpp, preflight), (cpp, apply_hook), (cpp, include), (cpp, receipt_hook)):
        if text.count(hook) != 1:
            raise ValueError('Unique native view fixture emission integration hook required')
    if 'PrepareNativeFixtureEmission' in cpp:
        raise ValueError('Native fixture emission already installed')
    if header.count('class UCameraComponent;') != 1:
        raise ValueError('Unique native type declaration hook required')
    header=header.replace('class UCameraComponent;','class UCameraComponent;\nclass UStaticMeshComponent;\nclass UMaterialInstanceDynamic;',1)
    header=header.replace(field_hook,FIELDS+'\n'+field_hook,1)
    cpp=cpp.replace(include,include+'\n'+INCLUDES,1)
    cpp=cpp.replace(init_hook,' if(PrivateSettingsInitialized)return;PrivateSettingsInitialized=true;\n if(!PrepareNativeFixtureEmission()){WritePrivateViewSettingsReceipt(0,false,NativeFixtureEmissionError);return;}\n WritePrivateViewSettingsReceipt(0,true,TEXT(""));',1)
    cpp=cpp.replace(preflight,' if(LampChanges&&!PrepareNativeFixtureEmission()){WritePrivateViewSettingsReceipt(Revision,false,NativeFixtureEmissionError);return;}\n'+preflight,1)
    cpp=cpp.replace(apply_hook,apply_hook+'ApplyNativeFixtureEmission(LampName,Enabled);',1)
    cpp=cpp.replace(receipt_hook,receipt_hook+'Receipt->SetBoolField(TEXT("fixture_emission_ready"),NativeFixtureEmissionVerified&&NativeFixtureMIDs.Num()==6&&NativeFixtureEmissionError.IsEmpty());Receipt->SetStringField(TEXT("fixture_emission_diagnostic"),NativeFixtureEmissionError);',1)
    return header,cpp+METHODS


def stage(module):
    (Path(module)/'Sub01NativeFixtureEmissionPolicy.h').write_text(POLICY)
