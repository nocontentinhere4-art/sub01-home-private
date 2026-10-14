"""Opt-in Manual-to-Live ownership; binding must be real before acknowledging.

Install after unreal_native_viewer_handoff. This candidate is not deployed.
"""
try:
    from .unreal_live_home_runtime import graph_source
except ImportError:  # direct staging-tool imports
    from unreal_live_home_runtime import graph_source

FIELDS = r'''
 bool CanPrivateViewerResumeLive() const;
 bool ApplyPrivateViewerResume(const TSharedPtr<FJsonObject>& Document,int32 Revision);
 void UpdatePrivateViewerResume();
 void WritePrivateViewerResumeReceipt(int32 Revision,bool Accepted,const FString& Error);
 int32 PrivateViewerResumeRevision=0; double PrivateViewerResumeUntil=0;
'''
METHODS = r'''
bool ASub01HomeCharacter::CanPrivateViewerResumeLive() const{
 if(PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||RouteActive||HandsDiagnosticSeat||NativeSeatVerified||!ViewCamera||!FParse::Param(FCommandLine::Get(),TEXT("Sub01LiveHome")))return false;
 if(FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_HOME_ORIGIN"))!=TEXT("http://127.0.0.1:8821")||FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN")).IsEmpty())return false;
 const auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>();
 if((PCBridge&&PCBridge->HasOperatorFocus())||MinecraftFocused||(Devices&&(!Devices->GetFocusedDevice().IsNone()||Devices->IsComposingNote())))return false;
 const FVector Eye=ViewCamera->GetComponentLocation();
 if(Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270)return false;
 const auto* Movement=GetCharacterMovement();const FFindFloorResult& Floor=Movement->CurrentFloor;
 if(!Movement->IsMovingOnGround()||!Floor.bBlockingHit)return false;
 TMap<FString,FVector> ResumeNodes;
 //@@RESUME_SOURCE_NODES@@
 const FVector Actual=GetActorLocation();
 for(const auto& Node:ResumeNodes){const float XY=FVector2D(Actual.X-Node.Value.X,Actual.Y-Node.Value.Y).Size();const float Z=FMath::Abs(Floor.HitResult.ImpactPoint.Z-Node.Value.Z);if(XY<20&&Z<20)return true;}
 return false;
}
void ASub01HomeCharacter::WritePrivateViewerResumeReceipt(int32 Revision,bool Accepted,const FString& Error){
 const FDateTime UTC=FDateTime::UtcNow();auto Receipt=MakeShared<FJsonObject>();
 Receipt->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());Receipt->SetNumberField(TEXT("native_start_ticks"),PrivateSettingsStartTicks());
 Receipt->SetNumberField(TEXT("captured_utc"),double(UTC.ToUnixTimestamp())+double(UTC.GetMillisecond())/1000.0);
 Receipt->SetNumberField(TEXT("revision"),Revision);Receipt->SetBoolField(TEXT("accepted"),Accepted);
 Receipt->SetStringField(TEXT("target"),TEXT("live"));Receipt->SetStringField(TEXT("view_mode"),PrivateViewMode==EPrivateViewMode::Live&&LiveHome?TEXT("live"):TEXT("manual"));
 Receipt->SetBoolField(TEXT("native_bound"),NativeFeedbackBound);Receipt->SetBoolField(TEXT("source_fresh"),LiveHomeFresh);Receipt->SetStringField(TEXT("error"),Error);
 FString Raw;FJsonSerializer::Serialize(Receipt,TJsonWriterFactory<>::Create(&Raw));const FString Temp=TEXT("/home/unreal/.sub01-private/native-viewer-resume-receipt.tmp");
 if(FFileHelper::SaveStringToFile(Raw,*Temp))IFileManager::Get().Move(TEXT("/home/unreal/.sub01-private/native-viewer-resume-receipt.json"),*Temp,true,true);
}
bool ASub01HomeCharacter::ApplyPrivateViewerResume(const TSharedPtr<FJsonObject>& Document,int32 Revision){
 if(!Document->HasField(TEXT("viewerResume")))return false;
 FString Target;double Pid=0,Ticks=0;
 if(PrivateViewerResumeRevision||Document->Values.Num()!=4||!Document->TryGetStringField(TEXT("viewerResume"),Target)||Target!=TEXT("live")||!Document->TryGetNumberField(TEXT("native_pid"),Pid)||!Document->TryGetNumberField(TEXT("native_start_ticks"),Ticks)||Pid!=FPlatformProcess::GetCurrentProcessId()||Ticks!=PrivateSettingsStartTicks()||!CanPrivateViewerResumeLive()){
  WritePrivateViewerResumeReceipt(Revision,false,TEXT("Live ownership unavailable"));return true;
 }
 if(!SwitchNativeWalkView(true)||!LiveHome){SwitchNativeWalkView(false);WritePrivateViewerResumeReceipt(Revision,false,TEXT("Physical source binding refused"));return true;}
 PrivateViewerResumeRevision=Revision;PrivateViewerResumeUntil=FPlatformTime::Seconds()+3;
 return true;
}
void ASub01HomeCharacter::UpdatePrivateViewerResume(){
 if(!PrivateViewerResumeRevision)return;
 const double Now=FPlatformTime::Seconds();const FVector Eye=ViewCamera->GetComponentLocation();
 const bool PhysicalPrivate=Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270;
 const int32 Revision=PrivateViewerResumeRevision;
 if(NativeControlRevision!=Revision){PrivateViewerResumeRevision=0;WritePrivateViewerResumeReceipt(Revision,false,TEXT("Ownership request superseded"));return;}
 if(!LiveHome||LiveHomePrivate||PhysicalPrivate||Now>PrivateViewerResumeUntil){
  PrivateViewerResumeRevision=0;SwitchNativeWalkView(false);WritePrivateViewerResumeReceipt(Revision,false,TEXT("Fresh public source binding not acknowledged"));return;
 }
 if(!LiveHomeFresh||!NativeFeedbackBound||NativeFeedbackLastAck<0||Now<NativeFeedbackLastAck||Now-NativeFeedbackLastAck>3)return;
 PrivateViewerResumeRevision=0;NativePrivacyPublishedAt=-10;PublishPrivateNativeCameraPrivacy(false);
 WritePrivateViewSettingsReceipt(Revision,true,TEXT(""));WritePrivateViewerResumeReceipt(Revision,true,TEXT(""));
 UE_LOG(LogTemp,Display,TEXT("SUB01_VIEWER_LIVE_RESUME revision=%d realbound actualpawnretained"),Revision);
}
'''


def install(header, cpp):
    if header.count(' bool CanPrivateViewerTakeControl() const;') != 1:
        raise ValueError('Install the ownership handoff first')
    header = header.replace(' bool CanPrivateViewerTakeControl() const;', FIELDS+'\n bool CanPrivateViewerTakeControl() const;', 1)
    hook = ' if(ApplyPrivateViewerHandoff(Doc,NativeControlRevision))return;'
    if cpp.count(hook) != 1:
        raise ValueError('Unique native handoff consumer required')
    cpp = cpp.replace(hook, hook+'\n if(ApplyPrivateViewerResume(Doc,NativeControlRevision))return;', 1)
    tick = ' const double Now=FPlatformTime::Seconds();\n ++NativeTelemetryTicks;'
    if cpp.count(tick) != 1:
        raise ValueError('Unique native control tick required')
    cpp = cpp.replace(tick, ' UpdatePrivateViewerResume();\n'+tick, 1)
    capability = 'Receipt->SetBoolField(TEXT("can_take_control"),!Hidden&&CanPrivateViewerTakeControl());'
    if cpp.count(capability) != 1:
        raise ValueError('Fresh native camera capability required')
    cpp = cpp.replace(capability, capability+'Receipt->SetBoolField(TEXT("viewer_resume_capable"),true);Receipt->SetBoolField(TEXT("can_resume_live"),!Hidden&&CanPrivateViewerResumeLive());', 1)
    nodes = '\n'.join(line.replace('LiveHomeNodes', 'ResumeNodes') for line in graph_source().splitlines() if 'LiveHomeNodes.Add' in line)
    return header, cpp+METHODS.replace('//@@RESUME_SOURCE_NODES@@', nodes)
