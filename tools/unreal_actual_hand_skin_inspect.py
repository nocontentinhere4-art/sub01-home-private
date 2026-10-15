"""Explicit bounded actual diagnostic skin readback, never a contact approval."""

FIELDS = r'''
 double HandSkinInspectAt=-10;
 UFUNCTION(Exec) void InspectCapturedHandSkin();
'''

METHODS = r'''
void ASub01HomeCharacter::InspectCapturedHandSkin(){
 auto Refuse=[](const TCHAR* Why){UE_LOG(LogTemp,Warning,TEXT("SUB01_HAND_SKIN_INSPECT_REFUSED %s"),Why);};
 const double Now=FPlatformTime::Seconds();
 if(Now-HandSkinInspectAt<1){Refuse(TEXT("bounded one-second interval"));return;}
 HandSkinInspectAt=Now;
 if(PrivateViewMode!=EPrivateViewMode::Diagnostic||LiveHome||LiveHomePrivate||!ViewCamera||!FirstPersonBody||
    !(DerivedControllerVisualReview||DerivedPhoneVisualReview)){Refuse(TEXT("explicit public derived diagnostic only"));return;}
 const FVector Eye=ViewCamera->GetComponentLocation();
 if(Eye.ContainsNaN()||(Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270)){Refuse(TEXT("physical privacy"));return;}
 auto* Mesh=FirstPersonBody->GetSkeletalMeshAsset();auto* Anim=FirstPersonBody->GetSingleNodeInstance();
 if(!Mesh||Mesh->GetPathName()!=TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner")||!Anim||Anim->IsPlaying()){Refuse(TEXT("actual original owner and already-paused diagnostic required"));return;}
 auto* Clip=Cast<UAnimSequence>(Anim->GetCurrentAsset());
 const FString Expected=DerivedControllerVisualReview?TEXT("/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip"):TEXT("/Game/Sub01Hands/Phone/SUB01_PhoneGrip.SUB01_PhoneGrip");
 const double Phase=Anim->GetCurrentTime();
 if(!Clip||Clip->GetSkeleton()!=Mesh->GetSkeleton()||Clip->GetPathName()!=Expected||!FMath::IsFinite(Phase)||Phase<0||Phase>Clip->GetPlayLength()+.001){Refuse(TEXT("actual derived phase required"));return;}
 const FString Raw=USub01HomeHandsInstance::DumpImportedHandWitness(Mesh,FirstPersonBody->GetComponentSpaceTransforms(),FirstPersonBody->GetComponentTransform());
 TSharedPtr<FJsonObject> Skin;
 if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),Skin)||!Skin.IsValid()||Skin->HasField(TEXT("error"))){Refuse(TEXT("imported skin unavailable"));return;}
 double Invalid=0;const TArray<TSharedPtr<FJsonValue>>* Vertices=nullptr;
 if(!Skin->TryGetNumberField(TEXT("invalidInfluences"),Invalid)||Invalid!=0||!Skin->TryGetArrayField(TEXT("vertices"),Vertices)||Vertices->Num()<1||Vertices->Num()>20000){Refuse(TEXT("invalid or unbounded imported skin"));return;}
 auto Doc=MakeShared<FJsonObject>();Doc->SetStringField(TEXT("schema"),TEXT("sub01.actual-hand-skin-witness.v1"));
 const FDateTime Stamp=FDateTime::UtcNow();Doc->SetNumberField(TEXT("captured_utc"),Stamp.ToUnixTimestamp()+Stamp.GetMillisecond()/1000.);
 Doc->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());Doc->SetNumberField(TEXT("native_start_ticks"),PrivateSettingsStartTicks());
 Doc->SetStringField(TEXT("owner_asset"),Mesh->GetPathName());Doc->SetStringField(TEXT("capture_asset"),Clip->GetPathName());Doc->SetNumberField(TEXT("capture_time"),Phase);
 Doc->SetStringField(TEXT("body_world"),FirstPersonBody->GetComponentTransform().ToString());Doc->SetStringField(TEXT("eye_cm"),Eye.ToString());
 Doc->SetStringField(TEXT("left_wrist"),FirstPersonBody->GetSocketTransform(TEXT("LeftHand"),RTS_World).ToString());
 Doc->SetStringField(TEXT("right_wrist"),FirstPersonBody->GetSocketTransform(TEXT("RightHand"),RTS_World).ToString());
 Doc->SetBoolField(TEXT("contact_accepted"),false);Doc->SetBoolField(TEXT("activity_ready"),false);Doc->SetObjectField(TEXT("skin"),Skin);
 TArray<TSharedPtr<FJsonValue>> Props;
 auto AddProp=[&Props](UStaticMeshComponent* C){if(!C||!C->GetStaticMesh())return;auto P=MakeShared<FJsonObject>();P->SetStringField(TEXT("component"),C->GetPathName());P->SetStringField(TEXT("mesh"),C->GetStaticMesh()->GetPathName());P->SetStringField(TEXT("world"),C->GetComponentTransform().ToString());Props.Add(MakeShared<FJsonValueObject>(P));};
 if(DerivedControllerVisualReview)AddProp(ControllerPlayProp);else for(auto& Part:PhoneGripParts)AddProp(Part.Get());
 Doc->SetArrayField(TEXT("actual_props"),Props);
 FString Output;FJsonSerializer::Serialize(Doc,TJsonWriterFactory<>::Create(&Output));
 const FString Path=FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit"),FString::Printf(TEXT("native-hand-skin-%u.json"),FPlatformProcess::GetCurrentProcessId()));
 const FString Temp=Path+TEXT(".tmp");
 if(!FFileHelper::SaveStringToFile(Output,*Temp,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM)){Refuse(TEXT("write failed"));return;}
 if(chmod(TCHAR_TO_UTF8(*Temp),0600)!=0||std::rename(TCHAR_TO_UTF8(*Temp),TCHAR_TO_UTF8(*Path))!=0){Refuse(TEXT("atomic private publication failed"));return;}
 UE_LOG(LogTemp,Display,TEXT("SUB01_HAND_SKIN_INSPECT actual phase=%.6f vertices=%d bytes=%d path=%s; readback only NO contact/activity acceptance"),Phase,Vertices->Num(),Output.Len(),*Path);
}
'''


def install(header, cpp):
    anchor = ' void PublishPrivateVisualMetrics();'
    if header.count(anchor) != 1 or 'PrivateSettingsStartTicks' not in cpp:
        raise ValueError('Actual identity and visual diagnostic hooks required')
    if 'InspectCapturedHandSkin(' in header:
        raise ValueError('Hand skin inspection already installed')
    return header.replace(anchor, anchor + FIELDS, 1), cpp + METHODS
