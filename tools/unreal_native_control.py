"""Private file-owned runtime controls; avoids rebooting warmed UE for live acceptance.

Only the designated rootfs file is read. No arbitrary console strings, code,
positions or backend activity writes are accepted. Switching a controlled desk
pose review to a physical live view is explicit and logged as a view-mode switch.
"""
FIELDS=r'''
 void UpdatePrivateNativeControl();
 double NativeControlPollAt=0;int32 NativeControlRevision=0;
'''
METHODS=r'''
void ASub01HomeCharacter::UpdatePrivateNativeControl(){
 const double Now=FPlatformTime::Seconds();if(Now<NativeControlPollAt)return;NativeControlPollAt=Now+.5;
 FString Path;if(!FParse::Value(FCommandLine::Get(),TEXT("Sub01NativeControl="),Path))return;
 if(Path!=TEXT("/home/unreal/.sub01-private/native-control.json"))return;
 if(IFileManager::Get().FileSize(*Path)>4096)return;FString Raw;TSharedPtr<FJsonObject> Doc;
 if(!FFileHelper::LoadFileToString(Raw,*Path)||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),Doc)||!Doc.IsValid())return;
 double Revision=0;if(!Doc->TryGetNumberField(TEXT("revision"),Revision)||!FMath::IsFinite(Revision)||Revision>MAX_int32||Revision<=NativeControlRevision)return;NativeControlRevision=int32(Revision);
 bool Live=false;if(Doc->TryGetBoolField(TEXT("live"),Live)&&Live&&!LiveHome){
  auto* Walk=LoadObject<UAnimSequence>(nullptr,TEXT("/Game/Sub01Hands/FBX/SUB01_Walk.SUB01_Walk"));
  if(!Walk||!FirstPersonBody->GetSkeletalMeshAsset()||Walk->GetSkeleton()!=FirstPersonBody->GetSkeletalMeshAsset()->GetSkeleton()){UE_LOG(LogTemp,Error,TEXT("SUB01_NATIVE_LIVE_SWITCH_REFUSED no compatible real Walk asset"));return;}
  HandsDiagnosticSeat=false;HandsClips.Add(TEXT("Walk"),Walk);SetHandsPosture(TEXT("Walk"));
  ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);ViewCamera->SetUsingAbsoluteRotation(false);ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);ViewCamera->FieldOfView=75;
  GetCharacterMovement()->SetMovementMode(MOVE_Walking);
  UE_LOG(LogTemp,Display,TEXT("SUB01_EXPLICIT_VIEW_MODE_SWITCH controlled desk review -> actual entry pawn; no actor teleport, backend unchanged"));
  BeginLiveHome();
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
    return header,cpp+METHODS
