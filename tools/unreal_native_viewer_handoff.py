"""Bounded Live-to-Manual ownership handoff, with actual native acknowledgement.

Integrate after native settings and Minecraft input. No actor position, backend
activity, arbitrary console command, or new network credential is accepted.
"""
FIELDS=r'''
 bool CanPrivateViewerTakeControl() const;
 bool ApplyPrivateViewerHandoff(const TSharedPtr<FJsonObject>& Document,int32 Revision);
 void WritePrivateViewerHandoffReceipt(int32 Revision,bool Accepted,const FString& Error);
'''
METHODS=r'''
bool ASub01HomeCharacter::CanPrivateViewerTakeControl() const{
 if(PrivateViewMode!=EPrivateViewMode::Live||!LiveHome||LiveHomePrivate||RouteActive||HandsDiagnosticSeat||NativeSeatVerified||!ViewCamera||GetCharacterMovement()->MovementMode!=MOVE_Walking)return false;
 const FVector Eye=ViewCamera->GetComponentLocation();
 return !(Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270);
}
void ASub01HomeCharacter::WritePrivateViewerHandoffReceipt(int32 Revision,bool Accepted,const FString& Error){
 const auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>();
 const bool Cleared=(!PCBridge||!PCBridge->HasOperatorFocus())&&(!Devices||(Devices->GetFocusedDevice().IsNone()&&!Devices->IsComposingNote()))&&!MinecraftFocused;
 const FDateTime UTC=FDateTime::UtcNow();auto Receipt=MakeShared<FJsonObject>();
 Receipt->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());Receipt->SetNumberField(TEXT("native_start_ticks"),PrivateSettingsStartTicks());
 Receipt->SetNumberField(TEXT("captured_utc"),double(UTC.ToUnixTimestamp())+double(UTC.GetMillisecond())/1000.0);
 Receipt->SetNumberField(TEXT("revision"),Revision);Receipt->SetBoolField(TEXT("accepted"),Accepted);Receipt->SetBoolField(TEXT("device_focus_cleared"),Cleared);
 Receipt->SetStringField(TEXT("target"),TEXT("manual"));Receipt->SetStringField(TEXT("view_mode"),PrivateViewMode==EPrivateViewMode::Manual&&!LiveHome&&!RouteActive&&!HandsDiagnosticSeat?TEXT("manual"):TEXT("unavailable"));Receipt->SetStringField(TEXT("error"),Error);
 FString Raw;FJsonSerializer::Serialize(Receipt,TJsonWriterFactory<>::Create(&Raw));const FString Temp=TEXT("/home/unreal/.sub01-private/native-viewer-handoff-receipt.tmp");
 if(FFileHelper::SaveStringToFile(Raw,*Temp))IFileManager::Get().Move(TEXT("/home/unreal/.sub01-private/native-viewer-handoff-receipt.json"),*Temp,true,true);
}
bool ASub01HomeCharacter::ApplyPrivateViewerHandoff(const TSharedPtr<FJsonObject>& Document,int32 Revision){
 if(!Document->HasField(TEXT("viewerHandoff")))return false;
 FString Target;double Pid=0,Ticks=0;
 if(Document->Values.Num()!=4||!Document->TryGetStringField(TEXT("viewerHandoff"),Target)||Target!=TEXT("manual")||!Document->TryGetNumberField(TEXT("native_pid"),Pid)||!Document->TryGetNumberField(TEXT("native_start_ticks"),Ticks)||Pid!=FPlatformProcess::GetCurrentProcessId()||Ticks!=PrivateSettingsStartTicks()||!CanPrivateViewerTakeControl()){
  WritePrivateViewerHandoffReceipt(Revision,false,TEXT("Manual handoff unavailable"));return true;
 }
 if(!SwitchNativeWalkView(false)){WritePrivateViewerHandoffReceipt(Revision,false,TEXT("Genuine walking view unavailable"));return true;}
 if(PCBridge)PCBridge->SetOperatorFocus(false);
 if(MinecraftFocused)ReleaseMinecraftTVInput();
 if(auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>())Devices->ReleaseFocus();
 NativePrivacyPublishedAt=-10;
 const FVector Eye=ViewCamera->GetComponentLocation();PublishPrivateNativeCameraPrivacy(Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270);
 WritePrivateViewerHandoffReceipt(Revision,true,TEXT(""));
 UE_LOG(LogTemp,Display,TEXT("SUB01_VIEWER_MANUAL_HANDOFF revision=%d actualpawnretained"),Revision);return true;
}
'''

def install(header,cpp):
    if header.count(' void ConfigureMinecraftTVInput();')!=1 or header.count(' bool SwitchNativeWalkView(bool UseLiveSource);')!=1:
        raise ValueError('Native walker and device adapters are required')
    header=header.replace(' void ConfigureMinecraftTVInput();',FIELDS+'\n void ConfigureMinecraftTVInput();',1)
    hook='NativeControlRevision=int32(Revision);\n bool Review=false;'
    if cpp.count(hook)!=1:
        raise ValueError('Unique native revision consumer missing')
    cpp=cpp.replace(hook,'NativeControlRevision=int32(Revision);\n if(ApplyPrivateViewerHandoff(Doc,NativeControlRevision))return;\n bool Review=false;',1)
    privacy=' Receipt->SetStringField(TEXT("view_mode"),PrivateViewMode==EPrivateViewMode::Manual&&!LiveHome&&!RouteActive&&!HandsDiagnosticSeat?TEXT("manual"):PrivateViewMode==EPrivateViewMode::Live&&LiveHome?TEXT("live"):TEXT("diagnostic"));'
    if cpp.count(privacy)!=1:
        raise ValueError('Unique actual camera ownership heartbeat missing')
    cpp=cpp.replace(privacy,privacy+'\n Receipt->SetNumberField(TEXT("view_mode_revision"),NativeControlRevision);Receipt->SetBoolField(TEXT("viewer_handoff_capable"),true);Receipt->SetBoolField(TEXT("can_take_control"),!Hidden&&CanPrivateViewerTakeControl());',1)
    return header,cpp+METHODS
