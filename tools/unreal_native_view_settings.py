"""Bounded private camera and exact authored-light controls, with native receipts.

The generator owner integrates FIELDS/METHODS and calls Initialize/Apply from
the existing private native-control revision consumer. This module never edits
the actor position, backend activity, or an arbitrary console variable.
"""

INCLUDES = r'''
#include "EngineUtils.h"
#include "HAL/PlatformProcess.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Serialization/JsonSerializer.h"
#include "Camera/CameraComponent.h"
#include "Components/LightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Math/RotationMatrix.h"
'''

FIELDS = r'''
 void InitializePrivateViewSettings();
 void ApplyPrivateViewSettings(const TSharedPtr<FJsonObject>& Document,int32 Revision);
 void WritePrivateViewSettingsReceipt(int32 Revision,bool Accepted,const FString& Error);
 AActor* FindAuthoredSettingsActor(const FString& Label) const;
 int64 PrivateSettingsStartTicks() const;
 bool PrivateSettingsInitialized=false;
 float PrivateEnvironmentHour=11.f;
'''

METHODS = r'''
AActor* ASub01HomeCharacter::FindAuthoredSettingsActor(const FString& Label) const{
 AActor* Found=nullptr;
 for(TActorIterator<AActor> It(GetWorld());It;++It){
  bool Matches=It->ActorHasTag(FName(*Label));
#if WITH_EDITOR
  Matches=Matches||It->GetActorLabel()==Label;
#endif
  if(Matches){if(Found)return nullptr;Found=*It;}
 }
 return Found;
}
int64 ASub01HomeCharacter::PrivateSettingsStartTicks() const{
 FString Raw;if(!FFileHelper::LoadFileToString(Raw,TEXT("/proc/self/stat")))return 0;
 int32 Close=INDEX_NONE;if(!Raw.FindLastChar(TEXT(')'),Close))return 0;
 TArray<FString> Fields;Raw.Mid(Close+1).ParseIntoArrayWS(Fields);
 return Fields.Num()>19?FCString::Atoi64(*Fields[19]):0;
}
void ASub01HomeCharacter::WritePrivateViewSettingsReceipt(int32 Revision,bool Accepted,const FString& Error){
 const TMap<FString,float> Lamps={{TEXT("DeskLamp"),12.f},{TEXT("BedLamp"),3.5f},{TEXT("KitchenWork"),2.4f},{TEXT("LowerPendant"),10.f},{TEXT("UpperPendant"),10.f}};
 auto Receipt=MakeShared<FJsonObject>();Receipt->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());Receipt->SetNumberField(TEXT("native_start_ticks"),PrivateSettingsStartTicks());
 Receipt->SetNumberField(TEXT("revision"),Revision);Receipt->SetBoolField(TEXT("accepted"),Accepted);Receipt->SetStringField(TEXT("error"),Error);
 auto Capabilities=MakeShared<FJsonObject>();Capabilities->SetBoolField(TEXT("fov"),ViewCamera!=nullptr);
 const auto* SunActor=FindAuthoredSettingsActor(TEXT("SUB01_AuthoredLight_SUN"));const auto* SkyActor=FindAuthoredSettingsActor(TEXT("SUB01_ActualHDR_Sky"));
 Capabilities->SetBoolField(TEXT("hour"),SunActor&&SunActor->FindComponentByClass<UDirectionalLightComponent>()&&SkyActor&&SkyActor->FindComponentByClass<USkyLightComponent>());
 TArray<TSharedPtr<FJsonValue>> Available;auto LampValues=MakeShared<FJsonObject>();
 for(const auto& Pair:Lamps){const auto* Actor=FindAuthoredSettingsActor(TEXT("SUB01_AuthoredLight_")+Pair.Key);const auto* Light=Actor?Actor->FindComponentByClass<ULightComponent>():nullptr;
  if(Light){Available.Add(MakeShared<FJsonValueString>(Pair.Key));LampValues->SetBoolField(Pair.Key,Light->Intensity>0.f);}
 }
 Capabilities->SetArrayField(TEXT("lamps"),Available);Receipt->SetObjectField(TEXT("capabilities"),Capabilities);
 auto Values=MakeShared<FJsonObject>();if(ViewCamera)Values->SetNumberField(TEXT("fov"),ViewCamera->FieldOfView);Values->SetNumberField(TEXT("hour"),PrivateEnvironmentHour);Values->SetObjectField(TEXT("lamps"),LampValues);Receipt->SetObjectField(TEXT("values"),Values);
 FString Raw;FJsonSerializer::Serialize(Receipt,TJsonWriterFactory<>::Create(&Raw));
 const FString Temp=TEXT("/home/unreal/.sub01-private/native-view-settings-receipt.tmp");
 if(FFileHelper::SaveStringToFile(Raw,*Temp))IFileManager::Get().Move(TEXT("/home/unreal/.sub01-private/native-view-settings-receipt.json"),*Temp,true,true);
}
void ASub01HomeCharacter::InitializePrivateViewSettings(){
 if(PrivateSettingsInitialized)return;PrivateSettingsInitialized=true;WritePrivateViewSettingsReceipt(0,true,TEXT(""));
}
void ASub01HomeCharacter::ApplyPrivateViewSettings(const TSharedPtr<FJsonObject>& Document,int32 Revision){
 const TSharedPtr<FJsonObject>* Settings=nullptr;if(!Document->TryGetObjectField(TEXT("viewSettings"),Settings)||!Settings||!Settings->IsValid())return;
 const TMap<FString,float> Lamps={{TEXT("DeskLamp"),12.f},{TEXT("BedLamp"),3.5f},{TEXT("KitchenWork"),2.4f},{TEXT("LowerPendant"),10.f},{TEXT("UpperPendant"),10.f}};
 double Fov=0,Hour=0;const bool HasFov=(*Settings)->HasField(TEXT("fov")),HasHour=(*Settings)->HasField(TEXT("hour"));const TSharedPtr<FJsonObject>* LampChanges=nullptr;
 for(const auto& Field:(*Settings)->Values)if(Field.Key!=TEXT("fov")&&Field.Key!=TEXT("hour")&&Field.Key!=TEXT("lamps")){WritePrivateViewSettingsReceipt(Revision,false,TEXT("Unknown view setting"));return;}
 if(HasFov&&(!(*Settings)->TryGetNumberField(TEXT("fov"),Fov)||!FMath::IsFinite(Fov)||Fov<50||Fov>110||!ViewCamera)){WritePrivateViewSettingsReceipt(Revision,false,TEXT("Invalid camera field of view"));return;}
 AActor* SunActor=FindAuthoredSettingsActor(TEXT("SUB01_AuthoredLight_SUN"));AActor* SkyActor=FindAuthoredSettingsActor(TEXT("SUB01_ActualHDR_Sky"));
 auto* Sun=SunActor?SunActor->FindComponentByClass<UDirectionalLightComponent>():nullptr;auto* Sky=SkyActor?SkyActor->FindComponentByClass<USkyLightComponent>():nullptr;
 if(HasHour&&(!(*Settings)->TryGetNumberField(TEXT("hour"),Hour)||!FMath::IsFinite(Hour)||Hour<0||Hour>24||!Sun||!Sky)){WritePrivateViewSettingsReceipt(Revision,false,TEXT("Daylight control unavailable"));return;}
 if((*Settings)->HasField(TEXT("lamps"))){
  if(!(*Settings)->TryGetObjectField(TEXT("lamps"),LampChanges)||!LampChanges||!LampChanges->IsValid()){WritePrivateViewSettingsReceipt(Revision,false,TEXT("Invalid indoor lamp request"));return;}
  for(const auto& Pair:(*LampChanges)->Values){bool Enabled=false;AActor* Actor=FindAuthoredSettingsActor(TEXT("SUB01_AuthoredLight_")+Pair.Key);
   if(!Lamps.Contains(Pair.Key)||!Pair.Value->TryGetBool(Enabled)||!Actor||!Actor->FindComponentByClass<ULightComponent>()){WritePrivateViewSettingsReceipt(Revision,false,TEXT("Requested indoor lamp unavailable"));return;}
  }
 }
 // All fields are validated before any renderer state is changed. SUN is not an indoor lamp.
 if(HasFov)ViewCamera->SetFieldOfView(float(Fov));
 if(HasHour){
  PrivateEnvironmentHour=float(Hour);const float Angle=(PrivateEnvironmentHour-6.f)/12.f*PI;const float Elevation=FMath::Max(0.f,FMath::Sin(Angle));
  const FVector Position(-1400.f*FMath::Cos(Angle),1200.f*Elevation,300.f+1500.f*Elevation);SunActor->SetActorLocationAndRotation(Position,FRotationMatrix::MakeFromX(FVector(0,0,100)-Position).Rotator());
  Sun->SetIntensity(3.2f*Elevation);Sky->SetIntensity(.4225f*FMath::Max(.08f,Elevation));
 }
 if(LampChanges)for(const auto& Pair:(*LampChanges)->Values){bool Enabled=false;Pair.Value->TryGetBool(Enabled);auto* Light=FindAuthoredSettingsActor(TEXT("SUB01_AuthoredLight_")+Pair.Key)->FindComponentByClass<ULightComponent>();Light->SetIntensity(Enabled?Lamps[Pair.Key]:0.f);}
 WritePrivateViewSettingsReceipt(Revision,true,TEXT(""));UE_LOG(LogTemp,Display,TEXT("SUB01_PRIVATE_VIEW_SETTINGS_APPLIED revision=%d"),Revision);
}
'''

def install(header, cpp):
    """Integrate after a verified baseline; never call the project generator here."""
    header = header.replace(' void UpdatePrivateNativeControl();', FIELDS + '\n void UpdatePrivateNativeControl();', 1)
    cpp = INCLUDES + cpp
    cpp = cpp.replace(' const double Now=FPlatformTime::Seconds();\n ++NativeTelemetryTicks;',
                      ' InitializePrivateViewSettings();\n const double Now=FPlatformTime::Seconds();\n ++NativeTelemetryTicks;', 1)
    cpp = cpp.replace(' FString Capture;if(Doc->TryGetStringField',
                      ' ApplyPrivateViewSettings(Doc,NativeControlRevision);\n FString Capture;if(Doc->TryGetStringField', 1)
    return header, cpp + METHODS
