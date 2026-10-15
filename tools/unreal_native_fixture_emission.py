"""Disabled-by-default native fixture emission, activated only after actual audit review.

Renderer owns integration/build. Reviewed config must set NativeFixtureEmissionVerified,
actual parent paths for Material13/63/91 (or explicitly reviewed common fallback),
and exact source SHA below. The saved posed genuine DeskLamp must also match
its exact actor, two material slots and owned derivative mesh namespace. Only
its bulb slot receives source emission factor and glTF default strength1. No asset writes;
original shared materials stay untouched. install hooks the native view settings.
"""
from pathlib import Path

POLICY = r'''#pragma once
#include <cmath>
namespace Sub01NativeFixtureEmission {
inline bool ValidOriginalFactor(double R,double G,double B,double A){
 return std::isfinite(R)&&std::isfinite(G)&&std::isfinite(B)&&std::isfinite(A)&&R>=0&&G>=0&&B>=0&&(R>0||G>0||B>0);
}
inline bool ValidBinding(int Node,bool BoundIsOriginal,bool BoundParentReviewed,bool BoundIsExactOwned,bool OwnedParentIsOriginal,bool OriginalParentReviewed){
 return BoundIsOriginal?BoundParentReviewed:(Node==199&&BoundIsExactOwned&&OwnedParentIsOriginal&&OriginalParentReviewed);
}
inline bool SameFactor(double R,double G,double B,double A,double OR,double OG,double OB,double OA){
 return R==OR&&G==OG&&B==OB&&A==OA;
}
}
'''
INCLUDES = r'''
#include "Sub01NativeFixtureEmissionPolicy.h"
#include "Materials/MaterialInstance.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
'''
FIELDS = r'''
 UPROPERTY(Config) bool NativeFixtureEmissionVerified=false;
 UPROPERTY(Config) FString NativeFixtureEmissionParentPath;
 UPROPERTY(Config) FString NativeFixtureEmissionParentMaterial13;
 UPROPERTY(Config) FString NativeFixtureEmissionParentMaterial63;
 UPROPERTY(Config) FString NativeFixtureEmissionParentMaterial91;
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
 if(NativeFixtureEmissionSourceSHA!=TEXT("9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b"))return Refuse(TEXT("Reviewed source identity receipt missing"));
 if(NativeFixtureMIDs.Num()){
  if(NativeFixtureMIDs.Num()!=7||NativeFixtureComponents.Num()!=7||NativeFixtureOriginalFactors.Num()!=7||NativeFixtureLampNames.Num()!=7)return Refuse(TEXT("Incomplete owned fixture state"));
  for(int32 I=0;I<7;++I)if(!IsValid(NativeFixtureComponents[I])||!IsValid(NativeFixtureMIDs[I])||NativeFixtureComponents[I]->GetMaterial(I==6?1:0)!=NativeFixtureMIDs[I])return Refuse(TEXT("Owned fixture slot changed externally"));
  return true;
 }
 struct FTarget {int32 Node;const TCHAR* Material;const TCHAR* Lamp;};
 const FTarget Targets[]={{66,TEXT("Material_13"),TEXT("KitchenWork")},{126,TEXT("Material_63"),TEXT("DeskLamp")},{127,TEXT("Material_63"),TEXT("LowerPendant")},{129,TEXT("Material_63"),TEXT("UpperPendant")},{198,TEXT("Material_63"),TEXT("BedLamp")},{199,TEXT("Material_91"),TEXT("BedLamp")}};
 TArray<UStaticMeshComponent*> Components;TArray<UMaterialInstance*> Originals,SourceOriginals;TArray<FLinearColor> Factors;TArray<bool> Enabled;
 for(const auto& Target:Targets){
  AActor* Found=nullptr;const FString ActorName=FString::Printf(TEXT("full-home_node_%d"),Target.Node);
  for(TActorIterator<AActor> It(GetWorld());It;++It)if(It->GetName()==ActorName){if(Found)return Refuse(TEXT("Duplicate exact source fixture actor"));Found=*It;}
  if(!Found)return Refuse(TEXT("Exact source fixture actor missing: ")+ActorName);
  TArray<UStaticMeshComponent*> Meshes;Found->GetComponents<UStaticMeshComponent>(Meshes);
  if(Meshes.Num()!=1||Meshes[0]->GetName()!=TEXT("StaticMeshComponent0")||Meshes[0]->GetNumMaterials()!=1)return Refuse(TEXT("Exact fixture component/slot identity differs"));
  auto* Component=Meshes[0];auto* Material=Cast<UMaterialInstance>(Component->GetMaterial(0));
  const FString Expected=FString(TEXT("/Game/Sub01Home/ImportedScene/full-home/Materials/"))+Target.Material+TEXT(".")+Target.Material;
  const FString ConfiguredParent=Target.Node==66?NativeFixtureEmissionParentMaterial13:(Target.Node==199?NativeFixtureEmissionParentMaterial91:NativeFixtureEmissionParentMaterial63);
  const FString ReviewedParent=ConfiguredParent.IsEmpty()?NativeFixtureEmissionParentPath:ConfiguredParent;
  if(!Material||ReviewedParent.IsEmpty())return Refuse(TEXT("Reviewed actual fixture parent receipt missing"));
  const FString Owned=TEXT("/Game/Sub01Home/MaterialFix/SUB01_MatFix_AlbedoMI_Material_91.SUB01_MatFix_AlbedoMI_Material_91");
  const bool BoundOriginal=Material->GetPathName()==Expected;
  auto* SourceOriginal=BoundOriginal?Material:Cast<UMaterialInstance>(Material->Parent);
  const bool ParentReviewed=Material->Parent&&Material->Parent->GetPathName()==ReviewedParent;
  const bool OwnedParentOriginal=SourceOriginal&&SourceOriginal->GetPathName()==Expected;
  const bool OriginalParentReviewed=SourceOriginal&&SourceOriginal->Parent&&SourceOriginal->Parent->GetPathName()==ReviewedParent;
  if(!Sub01NativeFixtureEmission::ValidBinding(Target.Node,BoundOriginal,ParentReviewed,Material->GetPathName()==Owned,OwnedParentOriginal,OriginalParentReviewed))return Refuse(TEXT("Actual fixture binding/parent differs from exact reviewed original or node199 colour MIC"));
  TArray<FMaterialParameterInfo> Infos;TArray<FGuid> IDs;Material->GetAllVectorParameterInfo(Infos,IDs);
  int32 Matches=0;for(const auto& Info:Infos)if(Info.Name==TEXT("EmissiveFactor")&&Info.Association==EMaterialParameterAssociation::GlobalParameter)++Matches;
  FLinearColor Factor;
  if(Matches!=1||!Material->GetVectorParameterValue(FMaterialParameterInfo(TEXT("EmissiveFactor")),Factor)||!Sub01NativeFixtureEmission::ValidOriginalFactor(Factor.R,Factor.G,Factor.B,Factor.A))return Refuse(TEXT("Enumerated effective EmissiveFactor missing, nonfinite, negative or zero"));
  FLinearColor SourceFactor;
  if(!SourceOriginal->GetVectorParameterValue(FMaterialParameterInfo(TEXT("EmissiveFactor")),SourceFactor)||!Sub01NativeFixtureEmission::SameFactor(Factor.R,Factor.G,Factor.B,Factor.A,SourceFactor.R,SourceFactor.G,SourceFactor.B,SourceFactor.A))return Refuse(TEXT("Bound effective EmissiveFactor differs from exact original vector"));
  auto* LampActor=FindAuthoredSettingsActor(FString(TEXT("SUB01_AuthoredLight_"))+Target.Lamp);auto* Light=LampActor?LampActor->FindComponentByClass<ULightComponent>():nullptr;
  if(!Light||!FMath::IsFinite(Light->Intensity)||Light->Intensity<0)return Refuse(TEXT("Exact associated native lamp intensity unavailable"));
  Components.Add(Component);Originals.Add(Material);SourceOriginals.Add(SourceOriginal);Factors.Add(Factor);Enabled.Add(Light->Intensity>0);
 }
 // The saved genuine articulated desk lamp has a distinct light surface in
 // slot1. Its importer deliberately zeroed factor AND strength. Restore only
 // this source-authored emitter on a per-component MID; the red body stays put.
 AActor* RealDesk=nullptr;
 const FString RealActor=TEXT("/Game/Sub01Home/ActualHome.ActualHome:PersistentLevel.StaticMeshActor_5");
 for(TActorIterator<AActor> It(GetWorld());It;++It)if(It->GetPathName()==RealActor){if(RealDesk)return Refuse(TEXT("Duplicate genuine desk lamp"));RealDesk=*It;}
 if(!RealDesk)return Refuse(TEXT("Saved genuine desk lamp missing"));
 TArray<UStaticMeshComponent*> RealMeshes;RealDesk->GetComponents<UStaticMeshComponent>(RealMeshes);
 if(RealMeshes.Num()!=1||RealMeshes[0]->GetName()!=TEXT("StaticMeshComponent0")||RealMeshes[0]->GetNumMaterials()!=2||!RealMeshes[0]->GetStaticMesh()||!RealMeshes[0]->GetStaticMesh()->GetPathName().StartsWith(TEXT("/Game/Sub01Home/RealEdgeClampLamp/V_8ec48458a8f0/Attempt_")))return Refuse(TEXT("Saved genuine posed lamp identity differs"));
 auto* RealComponent=RealMeshes[0];
 const FString RealRoot=TEXT("/Game/Sub01Home/RealLamps/DeskLamp/SUB01_RealLamp_DeskLamp/Materials/");
 const FString BodyName=TEXT("SUB01_RealLamp_DeskLamp_desk_lamp_arm_01_001"),BulbName=TEXT("SUB01_RealLamp_DeskLamp_desk_lamp_arm_01_light_001");
 auto* Bulb=Cast<UMaterialInstance>(RealComponent->GetMaterial(1));
 if(!RealComponent->GetMaterial(0)||RealComponent->GetMaterial(0)->GetPathName()!=RealRoot+BodyName+TEXT(".")+BodyName||!Bulb||Bulb->GetPathName()!=RealRoot+BulbName+TEXT(".")+BulbName)return Refuse(TEXT("Saved genuine lamp body/bulb material binding differs"));
 TArray<FMaterialParameterInfo> BulbVectors,BulbScalars;TArray<FGuid> BulbVectorIDs,BulbScalarIDs;
 Bulb->GetAllVectorParameterInfo(BulbVectors,BulbVectorIDs);Bulb->GetAllScalarParameterInfo(BulbScalars,BulbScalarIDs);
 int32 FactorMatches=0,StrengthMatches=0;
 for(const auto& Info:BulbVectors)if(Info.Name==TEXT("EmissiveFactor")&&Info.Association==EMaterialParameterAssociation::GlobalParameter)++FactorMatches;
 for(const auto& Info:BulbScalars)if(Info.Name==TEXT("EmissiveStrength")&&Info.Association==EMaterialParameterAssociation::GlobalParameter)++StrengthMatches;
 FLinearColor SavedBulb;float SavedStrength=0;
 if(FactorMatches!=1||StrengthMatches!=1||!Bulb->GetVectorParameterValue(FMaterialParameterInfo(TEXT("EmissiveFactor")),SavedBulb)||!Bulb->GetScalarParameterValue(FMaterialParameterInfo(TEXT("EmissiveStrength")),SavedStrength)||!FMath::IsFinite(SavedStrength)||!FMath::IsFinite(SavedBulb.A)||SavedStrength!=0.f||SavedBulb.R!=0.f||SavedBulb.G!=0.f||SavedBulb.B!=0.f)return Refuse(TEXT("Actual genuine bulb zeroed factor/strength receipt differs"));
 // Original Poly Haven glTF SHA2ac8389a... has this factor, no strength
 // extension (glTF default1). No light, wall or lamp-body colour is changed.
 Components.Add(RealComponent);Originals.Add(Bulb);SourceOriginals.Add(Bulb);
 Factors.Add(FLinearColor(1.f,.9837890267372131f,.649111270904541f,1.f));const bool RealEnabled=Enabled[1];Enabled.Add(RealEnabled);
 // Any additional mesh slot using an original fixture material is ambiguous,
 // including screens. No original material is ever modified.
 for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UMeshComponent*> Meshes;It->GetComponents<UMeshComponent>(Meshes);
  for(auto* Mesh:Meshes)for(int32 Slot=0;Slot<Mesh->GetNumMaterials();++Slot){auto* User=Cast<UMaterialInstance>(Mesh->GetMaterial(Slot));if((Originals.Contains(User)||SourceOriginals.Contains(User))&&(Components.IndexOfByKey(Cast<UStaticMeshComponent>(Mesh))==INDEX_NONE||Slot!=(Components.IndexOfByKey(Cast<UStaticMeshComponent>(Mesh))==6?1:0)))return Refuse(TEXT("Unexpected shared original fixture material user"));}
 }
 TArray<UMaterialInstanceDynamic*> Prepared;
 for(int32 I=0;I<7;++I){auto* MID=UMaterialInstanceDynamic::Create(Originals[I],this);if(!MID)return Refuse(TEXT("MID allocation failed; no fixture slot/light changed"));MID->SetVectorParameterValue(TEXT("EmissiveFactor"),Enabled[I]?Factors[I]:FLinearColor(0,0,0,0));if(I==6)MID->SetScalarParameterValue(TEXT("EmissiveStrength"),Enabled[I]?1.f:0.f);Prepared.Add(MID);}
 // All seven bindings, effective original vectors and allocations validated first.
 for(int32 I=0;I<7;++I){NativeFixtureComponents.Add(Components[I]);NativeFixtureMIDs.Add(Prepared[I]);NativeFixtureOriginalFactors.Add(Factors[I]);NativeFixtureLampNames.Add(I==6?TEXT("DeskLamp"):Targets[I].Lamp);Components[I]->SetMaterial(I==6?1:0,Prepared[I]);}
 NativeFixtureEmissionError.Empty();UE_LOG(LogTemp,Display,TEXT("SUB01_FIXTURE_EMISSION_READY exactTargets=7 originalsUnchanged=true"));return true;
}
void ASub01HomeCharacter::ApplyNativeFixtureEmission(const FString& Lamp,bool Enabled){
 if(!NativeFixtureEmissionVerified)return;
 for(int32 I=0;I<NativeFixtureMIDs.Num();++I)if(NativeFixtureLampNames[I]==Lamp){NativeFixtureMIDs[I]->SetVectorParameterValue(TEXT("EmissiveFactor"),Enabled?NativeFixtureOriginalFactors[I]:FLinearColor(0,0,0,0));if(I==6)NativeFixtureMIDs[I]->SetScalarParameterValue(TEXT("EmissiveStrength"),Enabled?1.f:0.f);}
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
    cpp=cpp.replace(receipt_hook,receipt_hook+'Receipt->SetBoolField(TEXT("fixture_emission_ready"),NativeFixtureEmissionVerified&&NativeFixtureMIDs.Num()==7&&NativeFixtureEmissionError.IsEmpty());Receipt->SetStringField(TEXT("fixture_emission_diagnostic"),NativeFixtureEmissionError);',1)
    return header,cpp+METHODS


def stage(module):
    (Path(module)/'Sub01NativeFixtureEmissionPolicy.h').write_text(POLICY)
