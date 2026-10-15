"""Optional real bathroom fixture switching; old maps retain their five lights.

Requires exact independently imported source namespace and authentic source
emission. Only creates a per-component MID; imported/shared materials stay exact.
Sole renderer integrates/builds with the real fixture in a later batch.
"""
FIELDS = r'''
 UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> BathroomLampMID;
 bool PrepareNativeBathroomLamp();
 void ApplyNativeBathroomLamp(bool Enabled);
'''
METHODS = r'''
bool ASub01HomeCharacter::PrepareNativeBathroomLamp(){
 auto* LightActor=FindAuthoredSettingsActor(TEXT("SUB01_AuthoredLight_BathroomCeiling"));
 if(!LightActor)return true; // Optional: older maps have no advertised sixth lamp.
 auto Refuse=[](const FString& Why){UE_LOG(LogTemp,Error,TEXT("SUB01_BATHROOM_LAMP_REFUSED %s"),*Why);return false;};
 auto* Light=LightActor->FindComponentByClass<ULightComponent>();
 if(!Light||!FMath::IsFinite(Light->Intensity)||Light->Intensity<0)return Refuse(TEXT("Unique actual bathroom lamp unavailable"));
 auto* GlobeActor=FindAuthoredSettingsActor(TEXT("SUB01_RealBathroomPendant_Globe"));
 if(!GlobeActor)return Refuse(TEXT("Unique actual source globe actor unavailable"));
 TArray<UStaticMeshComponent*> Parts;GlobeActor->GetComponents(Parts);
 if(Parts.Num()!=1)return Refuse(TEXT("Actual globe component differs"));
 auto* Globe=Parts[0];
 const FString Prefix=TEXT("/Game/Sub01Home/RealBathroomPendant/V_c953ce762552/Attempt_");
 if(!Globe||!Globe->GetStaticMesh()||!Globe->GetStaticMesh()->GetPathName().StartsWith(Prefix)||Globe->GetNumMaterials()!=1)return Refuse(TEXT("Genuine source c953 three-part globe identity differs"));
 if(BathroomLampMID){if(Globe->GetMaterial(0)!=BathroomLampMID)return Refuse(TEXT("Globe MID binding changed"));return true;}
 const auto& SourceSlots=Globe->GetStaticMesh()->GetStaticMaterials();
 if(SourceSlots.Num()!=1||SourceSlots[0].MaterialSlotName!=FName(TEXT("modern_ceiling_globe")))return Refuse(TEXT("Exact original source globe material slot differs"));
 auto* Original=Cast<UMaterialInstance>(Globe->GetMaterial(0));FLinearColor Factor;
 if(!Original||!Original->GetPathName().StartsWith(Prefix)||SourceSlots[0].MaterialInterface.Get()!=Original||!Original->GetVectorParameterValue(FMaterialParameterInfo(TEXT("EmissiveFactor")),Factor))return Refuse(TEXT("Actual owned original source emission unavailable"));
 if(!FMath::IsFinite(Factor.R)||!FMath::IsFinite(Factor.G)||!FMath::IsFinite(Factor.B)||!FMath::IsFinite(Factor.A)||!FMath::IsNearlyEqual(Factor.R,.6229580641f,.00001f)||!FMath::IsNearlyEqual(Factor.G,.5416215658f,.00001f)||!FMath::IsNearlyEqual(Factor.B,.4745504856f,.00001f))return Refuse(TEXT("Imported globe emission differs original CC0 source"));
 auto* Prepared=UMaterialInstanceDynamic::Create(Original,this);if(!Prepared)return Refuse(TEXT("Owned globe dynamic material unavailable"));
 Prepared->SetVectorParameterValue(TEXT("EmissiveFactor"),Light->Intensity>0?Factor:FLinearColor(0,0,0,0));
 Globe->SetMaterial(0,Prepared);BathroomLampMID=Prepared;
 UE_LOG(LogTemp,Display,TEXT("SUB01_BATHROOM_LAMP_READY genuine three-part fixture; original imported materials unchanged"));return true;
}
void ASub01HomeCharacter::ApplyNativeBathroomLamp(bool Enabled){
 if(BathroomLampMID)BathroomLampMID->SetVectorParameterValue(TEXT("EmissiveFactor"),Enabled?FLinearColor(.6229580641f,.5416215658f,.4745504856f,1.f):FLinearColor(0,0,0,0));
}
'''


def install(header, cpp):
    fields=' void InitializePrivateViewSettings();'
    maps='{TEXT("UpperPendant"),10.f}};'
    preflight=' // All fields are validated before any renderer state is changed. SUN is not an indoor lamp.'
    apply='Light->SetIntensity(Enabled?Lamps[LampName]:0.f);'
    init=' if(PrivateSettingsInitialized)return;PrivateSettingsInitialized=true;'
    if (header.count(fields)!=1 or cpp.count(maps)!=2 or cpp.count(preflight)!=1
            or cpp.count(apply)!=1 or cpp.count(init)!=1 or 'PrepareNativeBathroomLamp' in cpp):
        raise ValueError('Exact optional lamp integration hooks required')
    header=header.replace(fields,FIELDS+'\n'+fields,1)
    cpp=cpp.replace(maps,'{TEXT("UpperPendant"),10.f},{TEXT("BathroomCeiling"),5.5f}};')
    cpp=cpp.replace(init,init+'if(!PrepareNativeBathroomLamp()){WritePrivateViewSettingsReceipt(0,false,TEXT("Bathroom fixture source binding differs"));return;}',1)
    cpp=cpp.replace(preflight,' if(LampChanges&&(*LampChanges)->HasField(TEXT("BathroomCeiling"))&&!PrepareNativeBathroomLamp()){WritePrivateViewSettingsReceipt(Revision,false,TEXT("Actual bathroom fixture unavailable"));return;}\n'+preflight,1)
    cpp=cpp.replace(apply,apply+'if(LampName==TEXT("BathroomCeiling"))ApplyNativeBathroomLamp(Enabled);',1)
    return header,cpp+METHODS
