"""Private file-owned runtime controls; avoids rebooting warmed UE for live acceptance.

Only the designated rootfs file is read. No arbitrary console strings, code,
positions or backend activity writes are accepted. Switching a controlled desk
pose review to a physical live view is explicit and logged as a view-mode switch.
"""
FIELDS=r'''
 void UpdatePrivateNativeControl();
 bool SwitchNativeWalkView(bool UseLiveSource);
 enum class EPrivateViewMode:uint8 {Manual,Diagnostic,Live};
 EPrivateViewMode PrivateViewMode=EPrivateViewMode::Manual;
 double NativeControlPollAt=0,NativeTelemetryAt=0;int32 NativeControlRevision=0,NativeTelemetryTicks=0;
'''
METHODS=r'''
bool ASub01HomeCharacter::SwitchNativeWalkView(bool UseLiveSource){
 auto* Walk=LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk"));
 if(!Walk||!FirstPersonBody->GetSkeletalMeshAsset()||Walk->GetSkeleton()!=FirstPersonBody->GetSkeletalMeshAsset()->GetSkeleton()){
  UE_LOG(LogTemp,Error,TEXT("SUB01_VIEW_SWITCH_REFUSED no compatible genuine Walk asset"));return false;
 }
 LiveHome=false;LiveHomeFresh=false;LiveHomeBindWaiting=false;NativeSeatVerified=false;
 if(!UseLiveSource)LiveHomePrivate=false;
 NativeFeedbackBound=false;NativeFeedbackLastAck=-1;NativeFeedbackAckPhase.Empty();
 NativeFeedbackConsumer=FGuid::NewGuid().ToString(EGuidFormats::Digits);NativeFeedbackPendingReportId=0;NativeFeedbackPending=false;
 if(PCBridge)PCBridge->SetOperatorFocus(false);
 RouteActive=false;GetCharacterMovement()->StopMovementImmediately();
 HandsDiagnosticSeat=false;HandsClips.Add(TEXT("Walk"),Walk);SetHandsPosture(TEXT("Walk"));
 ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);
 ViewCamera->SetUsingAbsoluteRotation(false);ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);ViewCamera->FieldOfView=75;
 GetCharacterMovement()->SetMovementMode(MOVE_Walking);
 PrivateViewMode=UseLiveSource?EPrivateViewMode::Live:EPrivateViewMode::Manual;
 UE_LOG(LogTemp,Display,TEXT("SUB01_EXPLICIT_VIEW_MODE_SWITCH mode=%s actualpawnretained; no actor teleport or seating claim"),UseLiveSource?TEXT("live"):TEXT("manual"));
 if(UseLiveSource)BeginLiveHome();
 return true;
}
void ASub01HomeCharacter::UpdatePrivateNativeControl(){
 const double Now=FPlatformTime::Seconds();
 ++NativeTelemetryTicks;if(NativeTelemetryAt==0){NativeTelemetryAt=Now;NativeTelemetryTicks=0;}else if(Now-NativeTelemetryAt>=5){UE_LOG(LogTemp,Display,TEXT("SUB01_ACTUAL_GAME_TICK_RATE ticks=%d seconds=%.6f Hz=%.6f pawn=%s live=%d"),NativeTelemetryTicks,Now-NativeTelemetryAt,NativeTelemetryTicks/(Now-NativeTelemetryAt),*GetActorLocation().ToString(),LiveHome?1:0);NativeTelemetryAt=Now;NativeTelemetryTicks=0;}
 if(Now<NativeControlPollAt)return;NativeControlPollAt=Now+.5;
 FString Path;if(!FParse::Value(FCommandLine::Get(),TEXT("Sub01NativeControl="),Path))return;
 if(Path!=TEXT("/home/unreal/.sub01-private/native-control.json"))return;
 if(IFileManager::Get().FileSize(*Path)>4096)return;FString Raw;TSharedPtr<FJsonObject> Doc;
 if(!FFileHelper::LoadFileToString(Raw,*Path)||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),Doc)||!Doc.IsValid())return;
 double Revision=0;if(!Doc->TryGetNumberField(TEXT("revision"),Revision)||!FMath::IsFinite(Revision)||Revision>MAX_int32||Revision<=NativeControlRevision)return;NativeControlRevision=int32(Revision);
 bool Review=false;if(Doc->TryGetBoolField(TEXT("routeReview"),Review)&&Review){
  if(FVector::Dist(GetActorLocation(),FVector(200,310,95.65))>20){UE_LOG(LogTemp,Warning,TEXT("SUB01_ROUTE_REVIEW_REFUSED actual entry capsule required; no position reset"));return;}
  auto* Walk=LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk"));
  if(!Walk||!FirstPersonBody->GetSkeletalMeshAsset()||Walk->GetSkeleton()!=FirstPersonBody->GetSkeletalMeshAsset()->GetSkeleton())return;
  if(!SwitchNativeWalkView(false))return;
  GetCharacterMovement()->SetMovementMode(MOVE_Walking);ForceRouteReview=true;RouteIndex=0;BeginNativeRouteTest();
 }
 FString Mode;bool Live=false;
 if(Doc->TryGetStringField(TEXT("mode"),Mode)){
  if(Mode==TEXT("manual")){if(!SwitchNativeWalkView(false))return;}
  else if(Mode==TEXT("live")){if(!SwitchNativeWalkView(true))return;}
  else if(Mode==TEXT("diagnostic")&&HandsDiagnosticSeat){PrivateViewMode=EPrivateViewMode::Diagnostic;}
  else {UE_LOG(LogTemp,Warning,TEXT("SUB01_VIEW_MODE_REFUSED unavailable diagnostic or unknown mode"));return;}
 }else if(Doc->TryGetBoolField(TEXT("live"),Live)){if(!SwitchNativeWalkView(Live))return;}
 bool Replay=false;if(Doc->TryGetBoolField(TEXT("replayTyping"),Replay)&&Replay){
  auto* Hands=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance());
  if(HandsDiagnosticSeat&&Hands&&Hands->ContactTimes.Num()==301&&Hands->ContactSequence==HandsClips.FindRef(TEXT("DeskTyping"))){Hands->ContactFreezeTime=-1;++Hands->ContactRestartSerial;UE_LOG(LogTemp,Display,TEXT("SUB01_ACTUAL_TYPING_REPLAY original3to8 onepass;301armprofile;fingerlocalsunchanged;no PNGcapture"));}
  else UE_LOG(LogTemp,Warning,TEXT("SUB01_TYPING_REPLAY_REFUSED controlledactualDeskTypingprofile required"));
 }
 FString Capture;if(Doc->TryGetStringField(TEXT("capture"),Capture)&&!Capture.IsEmpty()&&Capture.Len()<80){
  bool Safe=true;for(TCHAR C:Capture)if(!FChar::IsAlnum(C)&&C!=TEXT('-')&&C!=TEXT('_')&&C!=TEXT('.'))Safe=false;
  if(Safe&&Capture.EndsWith(TEXT(".png"))){const FString Out=FPaths::Combine(TEXT("/workspace/sub01-home-private/evidence/native"),Capture);FScreenshotRequest::RequestScreenshot(Out,false,false);UE_LOG(LogTemp,Display,TEXT("SUB01_PRIVATE_OPERATOR_VIEWPORT_CAPTURE %s"),*Capture);}
 }
}
'''
def install(header,cpp):
    header=header.replace(' void Forward(float Value);',FIELDS+'\n void Forward(float Value);',1)
    cpp=cpp.replace(' UpdateNativeRouteTest();',' UpdatePrivateNativeControl();\n UpdateNativeRouteTest();',1)
    cpp=cpp.replace(' if(Controller&&Value!=0) AddMovementInput(',
                    ' if(PrivateViewMode==EPrivateViewMode::Manual&&!LiveHome&&!RouteActive&&!HandsDiagnosticSeat&&Controller&&Value!=0) AddMovementInput(')
    cpp=cpp.replace(' if(!FParse::Param(FCommandLine::Get(),TEXT("Sub01LiveHome")))return;',
                    ' if(!FParse::Param(FCommandLine::Get(),TEXT("Sub01LiveHome")))return;\n if(FParse::Param(FCommandLine::Get(),TEXT("Sub01ManualView"))&&PrivateViewMode==EPrivateViewMode::Manual)return;',1)
    return header,cpp+METHODS
