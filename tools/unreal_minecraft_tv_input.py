"""Separate manual-TV controls and independently published real native focus.

Installer runs after the device/live/manual adapters. Backend qualification flag
is OFF by default. This does not assert seating or change actor positions.
"""
FIELDS=r'''
 friend class FSub01MinecraftTVInput;
 TSharedPtr<IInputProcessor> MinecraftTVInput;
 FString MinecraftConsumerId, MinecraftFocusEvent, MinecraftFrame;
 FString MinecraftTVToken;
 uint64 MinecraftInputId=0, MinecraftStartTicks=0;
 double MinecraftLastReceipt=0, MinecraftLastSend=0;
 bool MinecraftFocused=false, MinecraftHTTPPending=false;
 TMap<FString,bool> MinecraftKeys;
 FVector2D MinecraftLook=FVector2D::ZeroVector;
 void ConfigureMinecraftTVInput();
 void FocusMinecraftTV(const FHitResult& Hit);
 bool PublishMinecraftTVReceipt(bool Clear=false);
 void TickMinecraftTVInput();
 void SendMinecraftTVInput(const FString& Operation);
 void ReleaseMinecraftTVInput();
'''
METHODS=r'''
#include "HAL/PlatformProcess.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
class FSub01MinecraftTVInput:public IInputProcessor{
 TWeakObjectPtr<ASub01HomeCharacter> Owner;
 FString KeyName(FKey K){if(K==EKeys::W||K==EKeys::Up)return TEXT("forward");if(K==EKeys::S||K==EKeys::Down)return TEXT("back");if(K==EKeys::A||K==EKeys::Left)return TEXT("left");if(K==EKeys::D||K==EKeys::Right)return TEXT("right");if(K==EKeys::SpaceBar)return TEXT("jump");if(K==EKeys::LeftShift)return TEXT("sneak");if(K==EKeys::LeftControl)return TEXT("sprint");return FString();}
public:
 explicit FSub01MinecraftTVInput(ASub01HomeCharacter* A):Owner(A){}
 void Tick(const float,FSlateApplication&,TSharedRef<ICursor>)override{}
 bool HandleKeyDownEvent(FSlateApplication&,const FKeyEvent& E)override{auto* A=Owner.Get();if(!A||!A->MinecraftFocused)return false;if(E.GetKey()==EKeys::Escape){A->ReleaseMinecraftTVInput();return true;}FString K=KeyName(E.GetKey());if(K.IsEmpty())return false;A->MinecraftKeys.Add(K,true);return true;}
 bool HandleKeyUpEvent(FSlateApplication&,const FKeyEvent& E)override{auto* A=Owner.Get();if(!A||!A->MinecraftFocused)return false;FString K=KeyName(E.GetKey());if(K.IsEmpty())return false;A->MinecraftKeys.Add(K,false);return true;}
 bool HandleMouseMoveEvent(FSlateApplication&,const FPointerEvent& E)override{auto* A=Owner.Get();if(!A||!A->MinecraftFocused)return false;auto D=E.GetCursorDelta();A->MinecraftLook.X=FMath::Clamp(A->MinecraftLook.X-D.X*.002f,-.35f,.35f);A->MinecraftLook.Y=FMath::Clamp(A->MinecraftLook.Y-D.Y*.002f,-.35f,.35f);return true;}
 bool HandleMouseButtonDownEvent(FSlateApplication&,const FPointerEvent& E)override{auto* A=Owner.Get();if(!A||!A->MinecraftFocused)return false;if(E.GetEffectingButton()==EKeys::LeftMouseButton){A->SendMinecraftTVInput(TEXT("mine"));return true;}if(E.GetEffectingButton()==EKeys::RightMouseButton){A->SendMinecraftTVInput(TEXT("place"));return true;}return false;}
 bool HandleMouseButtonUpEvent(FSlateApplication&,const FPointerEvent& E)override{auto* A=Owner.Get();if(!A||!A->MinecraftFocused)return false;if(E.GetEffectingButton()==EKeys::LeftMouseButton){A->SendMinecraftTVInput(TEXT("cancel"));return true;}return E.GetEffectingButton()==EKeys::RightMouseButton;}
};
void ASub01HomeCharacter::ConfigureMinecraftTVInput(){
 MinecraftConsumerId=FGuid::NewGuid().ToString(EGuidFormats::Digits).ToLower();
 FFileHelper::LoadFileToString(MinecraftTVToken,TEXT("/home/unreal/.sub01-private/operator-token"));MinecraftTVToken.TrimStartAndEndInline();
 FString Stat; if(FFileHelper::LoadFileToString(Stat,*FString::Printf(TEXT("/proc/%u/stat"),FPlatformProcess::GetCurrentProcessId()))){int32 End; if(Stat.FindLastChar(')',End)){TArray<FString> Fields;Stat.Mid(End+1).ParseIntoArrayWS(Fields);if(Fields.Num()>19)MinecraftStartTicks=FCString::Strtoui64(*Fields[19],nullptr,10);}}
 if(FSlateApplication::IsInitialized()){MinecraftTVInput=MakeShared<FSub01MinecraftTVInput>(this);FSlateApplication::Get().RegisterInputPreProcessor(MinecraftTVInput,0);}
}
void ASub01HomeCharacter::FocusMinecraftTV(const FHitResult& Hit){
 auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>();FString Frame;
 if(!Devices||Devices->GetFocusedDevice()!=TEXT("tv")||!Devices->GetDisplayedMinecraftFrame(Frame)||!Hit.GetComponent()||!Hit.GetComponent()->ComponentHasTag(TEXT("SUB01Device:tv")))return;
 if(PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||RouteActive||HandsDiagnosticSeat)return;
 MinecraftFocusEvent=FGuid::NewGuid().ToString(EGuidFormats::Digits).ToLower();MinecraftFocused=true;MinecraftFrame=Frame;
 if(!PublishMinecraftTVReceipt()){ReleaseMinecraftTVInput();return;}MinecraftLastSend=0;
}
bool ASub01HomeCharacter::PublishMinecraftTVReceipt(bool Clear){
 auto J=MakeShared<FJsonObject>();const FDateTime Captured=FDateTime::UtcNow();J->SetNumberField(TEXT("captured_utc"),Captured.ToUnixTimestamp()+Captured.GetMillisecond()/1000.0);
 J->SetBoolField(TEXT("focused"),false);J->SetStringField(TEXT("consumer_id"),MinecraftConsumerId);J->SetStringField(TEXT("focus_event_id"),MinecraftFocusEvent);
 bool Valid=false;
 if(!Clear&&MinecraftFocused&&PrivateViewMode==EPrivateViewMode::Manual&&!LiveHome&&!RouteActive&&!HandsDiagnosticSeat){
  UpdateNativePCPrivacy();auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>();FString Frame;const FVector Eye=ViewCamera->GetComponentLocation();FHitResult Hit;FCollisionQueryParams Q;Q.AddIgnoredActor(this);
  const bool Ray=GetWorld()->LineTraceSingleByChannel(Hit,Eye,Eye+ViewCamera->GetForwardVector()*200,ECC_Visibility,Q);
  int32 Count=0;for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UActorComponent*> C;It->GetComponents(C);for(auto* P:C)if(P->ComponentHasTag(TEXT("SUB01Device:tv")))++Count;}
  const bool Hidden=Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270;
  if(Devices&&Devices->GetFocusedDevice()==TEXT("tv")&&Devices->GetDisplayedMinecraftFrame(Frame)&&Ray&&Hit.GetComponent()&&Hit.GetComponent()->ComponentHasTag(TEXT("SUB01Device:tv"))&&Count==1&&!Hidden&&MinecraftStartTicks){
   auto V=[](FVector P){return TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(P.X),MakeShared<FJsonValueNumber>(P.Y),MakeShared<FJsonValueNumber>(P.Z)};};
   const auto B=Hit.GetComponent()->CalcBounds(Hit.GetComponent()->GetComponentTransform());auto Bounds=MakeShared<FJsonObject>();Bounds->SetArrayField(TEXT("center_cm"),V(B.Origin));Bounds->SetArrayField(TEXT("extent_cm"),V(B.BoxExtent));
   J->SetObjectField(TEXT("surface_bounds"),Bounds);J->SetArrayField(TEXT("actor_cm"),V(GetActorLocation()));J->SetArrayField(TEXT("eye_cm"),V(Eye));J->SetArrayField(TEXT("hit_cm"),V(Hit.ImpactPoint));
   J->SetStringField(TEXT("mode"),TEXT("manual"));J->SetBoolField(TEXT("privacy"),false);J->SetStringField(TEXT("device"),TEXT("tv"));J->SetBoolField(TEXT("focused"),true);J->SetStringField(TEXT("frame_id"),Frame);
   J->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());J->SetNumberField(TEXT("native_start_ticks"),MinecraftStartTicks);
   J->SetStringField(TEXT("component_identity"),Hit.GetComponent()->GetPathName());J->SetStringField(TEXT("surface_tag"),TEXT("SUB01Device:tv"));J->SetBoolField(TEXT("surface_unique"),true);MinecraftFrame=Frame;Valid=true;
  }
 }
 FString Data;auto Writer=TJsonWriterFactory<>::Create(&Data);FJsonSerializer::Serialize(J.ToSharedRef(),Writer);
 const FString Path=TEXT("/home/unreal/.sub01-private/native-tv-focus.json"),Temp=Path+TEXT(".tmp");
 if(!FFileHelper::SaveStringToFile(Data,*Temp,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))return false;
 chmod(TCHAR_TO_UTF8(*Temp),0600);if(rename(TCHAR_TO_UTF8(*Temp),TCHAR_TO_UTF8(*Path))!=0)return false;MinecraftLastReceipt=FPlatformTime::Seconds();return Valid;
}
void ASub01HomeCharacter::SendMinecraftTVInput(const FString& Operation){
 if(MinecraftTVToken.IsEmpty()||MinecraftFocusEvent.IsEmpty())return;
 if(Operation!=TEXT("release")&&Operation!=TEXT("cancel")&&!PublishMinecraftTVReceipt())return;
 auto Body=MakeShared<FJsonObject>();Body->SetStringField(TEXT("consumer_id"),MinecraftConsumerId);Body->SetStringField(TEXT("focus_event_id"),MinecraftFocusEvent);Body->SetStringField(TEXT("frame_id"),MinecraftFrame);
 const bool Focus=Operation==TEXT("focus");if(!Focus){Body->SetNumberField(TEXT("input_id"),++MinecraftInputId);Body->SetStringField(TEXT("operation"),Operation);}
 if(Operation==TEXT("controls")){auto Keys=MakeShared<FJsonObject>();for(auto& K:MinecraftKeys)Keys->SetBoolField(K.Key,K.Value);Body->SetObjectField(TEXT("keys"),Keys);Body->SetArrayField(TEXT("look_delta"),{MakeShared<FJsonValueNumber>(MinecraftLook.X),MakeShared<FJsonValueNumber>(MinecraftLook.Y)});MinecraftLook=FVector2D::ZeroVector;}
 FString Data;auto Writer=TJsonWriterFactory<>::Create(&Data);FJsonSerializer::Serialize(Body.ToSharedRef(),Writer);auto R=FHttpModule::Get().CreateRequest();R->SetURL(TEXT("http://127.0.0.1:8820/api/home/minecraft/")+(Focus?TEXT("focus"):TEXT("input")));R->SetVerb(TEXT("POST"));R->SetTimeout((Operation==TEXT("mine")||Operation==TEXT("place"))?7.5f:1.f);R->SetHeader(TEXT("X-Admin-Token"),MinecraftTVToken);R->SetHeader(TEXT("Content-Type"),TEXT("application/json"));R->SetContentAsString(Data);
 if(Focus){if(MinecraftHTTPPending)return;MinecraftHTTPPending=true;const FString Event=MinecraftFocusEvent,Frame=MinecraftFrame;
  R->OnProcessRequestComplete().BindWeakLambda(this,[this,Event,Frame](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){MinecraftHTTPPending=false;if(!MinecraftFocused||MinecraftFocusEvent!=Event||MinecraftFrame!=Frame)return;if(OK&&Response&&Response->GetResponseCode()==200)SendMinecraftTVInput(TEXT("controls"));});}
 if(!R->ProcessRequest()&&Focus)MinecraftHTTPPending=false;
}
void ASub01HomeCharacter::TickMinecraftTVInput(){
 if(!MinecraftFocused)return;if(!PublishMinecraftTVReceipt()){ReleaseMinecraftTVInput();return;}
 const double Now=FPlatformTime::Seconds();if(Now-MinecraftLastSend<.1)return;MinecraftLastSend=Now;SendMinecraftTVInput(TEXT("focus"));
}
void ASub01HomeCharacter::ReleaseMinecraftTVInput(){
 SendMinecraftTVInput(TEXT("release"));MinecraftFocused=false;MinecraftKeys.Empty();MinecraftLook=FVector2D::ZeroVector;PublishMinecraftTVReceipt(true);
 if(auto* D=FindComponentByClass<USub01HomeDeviceBridge>())D->ReleaseFocus();
}
'''

def install(header,cpp):
    for hook in ('if(TryNativeHomeDevice(Hit.GetComponent()))return;', ' Super::Tick(DeltaSeconds);', ' ConfigureActualPC();'):
        if cpp.count(hook)!=1:raise ValueError('Minecraft TV adapter requires unique '+hook)
    if header.count(' void ConfigureActualPC();')!=1:raise ValueError('Unique character declaration required')
    header=header.replace(' void ConfigureActualPC();', ' void ConfigureActualPC();'+FIELDS,1)
    cpp=cpp.replace(' ConfigureActualPC();',' ConfigureActualPC();\n ConfigureMinecraftTVInput();',1)
    cpp=cpp.replace(' Super::Tick(DeltaSeconds);',' Super::Tick(DeltaSeconds);\n TickMinecraftTVInput();',1)
    cpp=cpp.replace('if(TryNativeHomeDevice(Hit.GetComponent()))return;', 'if(TryNativeHomeDevice(Hit.GetComponent())){FocusMinecraftTV(Hit);return;}',1)
    return header,cpp+'\n#include <sys/stat.h>\n#include <cstdio>\n'+METHODS
