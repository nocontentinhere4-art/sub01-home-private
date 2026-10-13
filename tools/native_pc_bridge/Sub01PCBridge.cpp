#include "Sub01PCBridge.h"
#include "Components/MeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/Canvas.h"
#include "Engine/CanvasRenderTarget2D.h"
#include "Engine/Engine.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonWriter.h"
#include "Dom/JsonObject.h"
#include "TimerManager.h"

#include "Framework/Application/SlateApplication.h"
#include "Framework/Application/IInputProcessor.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"

// Scoped to PC focus. PixelStreaming2 supplies printable CharacterCode in the
// native Slate FKeyEvent (verified in its actual UE5.8 InputHandler.cpp).
class FSub01PCInputProcessor final : public IInputProcessor {
 TWeakObjectPtr<USub01PCBridge> Bridge;
 bool LeftShiftHeld=false,RightShiftHeld=false;
public:
 explicit FSub01PCInputProcessor(USub01PCBridge* InBridge):Bridge(InBridge){}
 void ResetModifiers(){LeftShiftHeld=false;RightShiftHeld=false;}
 void Tick(const float,FSlateApplication&,TSharedRef<ICursor>) override {if(!Bridge.IsValid()||!Bridge->IsAcceptingNativeInput())ResetModifiers();}
 bool HandleKeyDownEvent(FSlateApplication&,const FKeyEvent& Event) override {
  auto* PC=Bridge.Get();if(!PC||!PC->IsAcceptingNativeInput()){ResetModifiers();return false;}
  const FKey Key=Event.GetKey();
  if(Key==EKeys::LeftShift){LeftShiftHeld=true;return true;}
  if(Key==EKeys::RightShift){RightShiftHeld=true;return true;}
  const bool Shift=LeftShiftHeld||RightShiftHeld||Event.IsShiftDown();
  if(Key==EKeys::Escape){PC->SetOperatorFocus(false);return true;}
  if(Key==EKeys::Enter){PC->SubmitTypedLine();return true;}
  if(Key==EKeys::BackSpace){PC->BackspaceNativeCharacter();return true;}
  if(Event.IsControlDown()||Event.IsAltDown()||Event.IsCommandDown())return true;
  uint32 Code=Event.GetCharacter();
  if(Code>=32&&Code<=126){
   TCHAR Char=TCHAR(Code);
   if(Char>=TEXT('A')&&Char<=TEXT('Z')&&!Shift)Char=TCHAR(Char+32);
   else if(Char>=TEXT('a')&&Char<=TEXT('z')&&Shift)Char=TCHAR(Char-32);
   else if(Shift){
    const FString Base=TEXT("1234567890-=[];'/.,`\\");
    const FString ShiftChars=TEXT("!@#$%^&*()_+{}:\"?><~|");
    const int32 At=Base.Find(FString::Chr(Char));if(At!=INDEX_NONE&&At<ShiftChars.Len())Char=ShiftChars[At];
   }
   PC->AppendNativeCharacter(Char);
  }
  // Suppress world movement and console keys while the player types at the PC.
  return true;
 }
 bool HandleKeyUpEvent(FSlateApplication&,const FKeyEvent& Event) override {
  if(Event.GetKey()==EKeys::LeftShift)LeftShiftHeld=false;
  if(Event.GetKey()==EKeys::RightShift)RightShiftHeld=false;
  const bool Active=Bridge.IsValid()&&Bridge->IsAcceptingNativeInput();if(!Active)ResetModifiers();return Active;
 }
 bool HandleMouseMoveEvent(FSlateApplication&,const FPointerEvent&) override {return Bridge.IsValid()&&Bridge->IsAcceptingNativeInput();}
 const TCHAR* GetDebugName() const override {return TEXT("Sub01FocusedPCInput");}
};

void USub01PCBridge::ResetNativeModifiers(){if(NativeInputProcessor)StaticCastSharedPtr<FSub01PCInputProcessor>(NativeInputProcessor)->ResetModifiers();}
USub01PCBridge::USub01PCBridge(){PrimaryComponentTick.bCanEverTick=false;}
bool USub01PCBridge::Configure(UMeshComponent* Screen,int32 Slot,UMaterialInterface* Parent){
 if(!Screen||!Parent||Slot<0||Slot>=Screen->GetNumMaterials())return false;
 OperatorToken=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN"));
 if(OperatorToken.IsEmpty()){Status=TEXT("PC operator is not connected");return false;}
 MonitorMaterial=UMaterialInstanceDynamic::Create(Parent,this);
 Screen->SetMaterial(Slot,MonitorMaterial);
 TerminalCanvas=UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(GetWorld(),UCanvasRenderTarget2D::StaticClass(),1024,600);
 if(!TerminalCanvas)return false;
 TerminalCanvas->ClearColor=FLinearColor(.015,.02,.025,1);
 TerminalCanvas->OnCanvasRenderTargetUpdate.AddDynamic(this,&USub01PCBridge::DrawTerminal);
 MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),TerminalCanvas);
 TerminalCanvas->UpdateResource();
 if(FSlateApplication::IsInitialized()){NativeInputProcessor=MakeShared<FSub01PCInputProcessor>(this);FSlateApplication::Get().RegisterInputPreProcessor(NativeInputProcessor,0);}
 GetWorld()->GetTimerManager().SetTimer(PollTimer,this,&USub01PCBridge::Poll,.5f,true);
 Poll();return true;
}
void USub01PCBridge::EndPlay(const EEndPlayReason::Type Reason){
 ++Generation;ResetNativeModifiers();GetWorld()->GetTimerManager().ClearTimer(PollTimer);
 if(NativeInputProcessor&&FSlateApplication::IsInitialized())FSlateApplication::Get().UnregisterInputPreProcessor(NativeInputProcessor);NativeInputProcessor.Reset();
 OperatorToken.Empty();TerminalOutput.Empty();TypedLine.Empty();
 Super::EndPlay(Reason);
}
void USub01PCBridge::ReadState(TFunction<void(TSharedPtr<FJsonObject>)> Done){
 auto Callback=MakeShared<TFunction<void(TSharedPtr<FJsonObject>)>>(MoveTemp(Done));
 auto Completed=MakeShared<bool>(false);
 auto Finish=[Callback,Completed](TSharedPtr<FJsonObject> State){if(!*Completed){*Completed=true;(*Callback)(State);}};
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(Origin+TEXT("/pc/state"));
 Request->SetVerb(TEXT("GET"));Request->SetTimeout(3);Request->SetHeader(TEXT("X-Admin-Token"),OperatorToken);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[Finish](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){
  TSharedPtr<FJsonObject> State;
  if(OK&&Response&&Response->GetResponseCode()==200){auto Reader=TJsonReaderFactory<>::Create(Response->GetContentAsString());FJsonSerializer::Deserialize(Reader,State);}
  Finish(State);
 });
 if(!Request->ProcessRequest()){Finish(nullptr);}
}
bool USub01PCBridge::IsPublicState(const TSharedPtr<FJsonObject>& State)const{
 if(LocalPrivacy||!State)return false;bool Privacy=true;
 return State->TryGetBoolField(TEXT("privacy"),Privacy)&&!Privacy;
}
void USub01PCBridge::ClearPrivateState(const FString& Reason){
 Private=true;Focused=false;ResetNativeModifiers();++Generation;TerminalOutput.Empty();TypedLine.Empty();Status=Reason;
 if(MonitorMaterial&&TerminalCanvas){MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),TerminalCanvas);TerminalCanvas->UpdateResource();}
}
void USub01PCBridge::ApplyTerminal(const TSharedPtr<FJsonObject>& State){
 bool Ready=false;FString Output;
 if(!State){ClearPrivateState(TEXT("PC backend disconnected"));return;}
 State->TryGetBoolField(TEXT("ready"),Ready);State->TryGetStringField(TEXT("output"),Output);
 Private=false;TerminalOutput=Output.Right(6000);Status=Ready?TEXT("Live Linux computer"):TEXT("Linux computer is starting");
 if(MonitorMaterial&&TerminalCanvas){MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),TerminalCanvas);TerminalCanvas->UpdateResource();}
}
void USub01PCBridge::Poll(){
 if(Busy||LocalPrivacy||OperatorToken.IsEmpty())return;
 if(Focused&&!LocalPrivacy&&FPlatformTime::Seconds()-LastSessionHeartbeat>30){LastSessionHeartbeat=FPlatformTime::Seconds();SendFlag(TEXT("/pc/session"),true,[](bool){});}
 Busy=true;const uint64 Epoch=Generation;
 ReadState([this,Epoch](TSharedPtr<FJsonObject> Before){
  if(Epoch!=Generation){Busy=false;return;}
  if(!IsPublicState(Before)){Busy=false;ClearPrivateState(TEXT("Private screen hidden or backend unavailable"));return;}
  // Second API read after the async boundary prevents stale terminal text leaking.
  ReadState([this,Epoch](TSharedPtr<FJsonObject> After){
   Busy=false;if(Epoch!=Generation)return;
   if(!IsPublicState(After)){ClearPrivateState(TEXT("Private screen hidden or backend unavailable"));return;}
   ApplyTerminal(After);

  });
 });
}
void USub01PCBridge::SendFlag(const FString& Path,bool Active,TFunction<void(bool)> Done){
 auto Callback=MakeShared<TFunction<void(bool)>>(MoveTemp(Done));auto Completed=MakeShared<bool>(false);
 auto Finish=[Callback,Completed](bool OK){if(!*Completed){*Completed=true;(*Callback)(OK);}};
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(Origin+Path);Request->SetVerb(TEXT("POST"));Request->SetTimeout(3);
 Request->SetHeader(TEXT("Content-Type"),TEXT("application/json"));Request->SetHeader(TEXT("X-Admin-Token"),OperatorToken);
 Request->SetContentAsString(Active?TEXT("{\"active\":true}"):TEXT("{\"active\":false}"));
 Request->OnProcessRequestComplete().BindWeakLambda(this,[Finish](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){Finish(OK&&Response&&Response->GetResponseCode()==200);});
 if(!Request->ProcessRequest())Finish(false);
}
void USub01PCBridge::SetOperatorFocus(bool Focus){
 Focused=Focus&&!Private&&!LocalPrivacy;ResetNativeModifiers();
 LastSessionHeartbeat=FPlatformTime::Seconds();SendFlag(TEXT("/pc/session"),Focused,[](bool){});
 if(TerminalCanvas)TerminalCanvas->UpdateResource();
}
void USub01PCBridge::SetLocalPrivacy(bool Hidden){
 const bool Changed=Hidden!=PrivacyDesired;
 if(Changed){PrivacyDesired=Hidden;PrivacyKnown=false;LastPrivacyAttempt=-10;LocalPrivacy=true;ClearPrivateState(TEXT("Private screen hidden"));}
 if(PrivacyKnown&&PrivacyAcknowledged==PrivacyDesired)return;
 // First synchronization and failed retries remain closed, but unchanged Tick
 // calls neither clear the canvas nor increment the generation repeatedly.
 if(!LocalPrivacy){LocalPrivacy=true;ClearPrivateState(TEXT("PC privacy synchronization pending"));}
 if(PrivacyRequestPending||FPlatformTime::Seconds()-LastPrivacyAttempt<2)return;
 PrivacyRequestPending=true;LastPrivacyAttempt=FPlatformTime::Seconds();
 const bool Requested=PrivacyDesired;const uint64 Epoch=Generation;
 SendFlag(TEXT("/pc/privacy"),Requested,[this,Requested,Epoch](bool OK){
  PrivacyRequestPending=false;
  if(Requested!=PrivacyDesired||Epoch!=Generation){LastPrivacyAttempt=-10;SetLocalPrivacy(PrivacyDesired);return;}
  if(!OK){Status=TEXT("PC privacy synchronization unavailable");if(TerminalCanvas)TerminalCanvas->UpdateResource();return;}
  PrivacyKnown=true;PrivacyAcknowledged=Requested;LocalPrivacy=Requested;
  if(!Requested)Poll();
 });
}
void USub01PCBridge::AppendNativeCharacter(TCHAR Character){if(IsAcceptingNativeInput()&&TypedLine.Len()<2000){TypedLine.AppendChar(Character);if(TerminalCanvas)TerminalCanvas->UpdateResource();}}
void USub01PCBridge::BackspaceNativeCharacter(){if(IsAcceptingNativeInput()&&!TypedLine.IsEmpty()){TypedLine.LeftChopInline(1);if(TerminalCanvas)TerminalCanvas->UpdateResource();}}
void USub01PCBridge::SetTypedLine(const FString& Line){if(Focused&&!Private){TypedLine=Line.Left(2000);if(TerminalCanvas)TerminalCanvas->UpdateResource();}}
void USub01PCBridge::SubmitTypedLine(){
 if(!Focused||Private||CommandBusy||TypedLine.IsEmpty()||OperatorToken.IsEmpty())return;
 const FString Input=TypedLine;const uint64 Epoch=Generation;CommandBusy=true;
 ReadState([this,Input,Epoch](TSharedPtr<FJsonObject> Before){
  if(Epoch!=Generation||!Focused||!IsPublicState(Before)){CommandBusy=false;ClearPrivateState(TEXT("PC input unavailable during privacy"));return;}
  auto Body=MakeShared<FJsonObject>();Body->SetStringField(TEXT("input"),Input);FString JSON;auto Writer=TJsonWriterFactory<>::Create(&JSON);FJsonSerializer::Serialize(Body,Writer);
  auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(Origin+TEXT("/pc/input"));Request->SetVerb(TEXT("POST"));Request->SetTimeout(3);Request->SetHeader(TEXT("Content-Type"),TEXT("application/json"));Request->SetHeader(TEXT("X-Admin-Token"),OperatorToken);Request->SetContentAsString(JSON);
  Request->OnProcessRequestComplete().BindWeakLambda(this,[this,Epoch](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){
   if(Epoch!=Generation){CommandBusy=false;return;}bool Accepted=false;TSharedPtr<FJsonObject> Result;
   if(OK&&Response&&Response->GetResponseCode()==200){auto Reader=TJsonReaderFactory<>::Create(Response->GetContentAsString());if(FJsonSerializer::Deserialize(Reader,Result)&&Result)Result->TryGetBoolField(TEXT("ok"),Accepted);}
   ReadState([this,Epoch,Accepted](TSharedPtr<FJsonObject> After){
    CommandBusy=false;if(Epoch!=Generation)return;if(!IsPublicState(After)){ClearPrivateState(TEXT("Private screen hidden"));return;}
    if(Accepted)TypedLine.Empty();ApplyTerminal(After);if(!Accepted)Status=TEXT("PC command was refused");
   });
  });if(!Request->ProcessRequest()){CommandBusy=false;Status=TEXT("PC backend disconnected");}
 });
}
void USub01PCBridge::DrawTerminal(UCanvas* Canvas,int32 Width,int32 Height){
 if(!Canvas||!GEngine)return;UFont* Font=GEngine->GetSmallFont();if(!Font)return;
 Canvas->SetDrawColor(FColor(155,255,180));float Y=24;
 Canvas->DrawText(Font,Status,24,Y,2.2f,2.2f);Y+=54;
 if(Private)return;
 TArray<FString> Lines;TerminalOutput.ParseIntoArrayLines(Lines,false);const int32 Visible=FMath::Max(1,(Height-140)/38);int32 First=FMath::Max(0,Lines.Num()-Visible);
 for(int32 I=First;I<Lines.Num();++I){Canvas->DrawText(Font,Lines[I].Left(60),24,Y,2.5f,2.5f);Y+=38;if(Y>Height-76)break;}
 if(Focused)Canvas->DrawText(Font,TEXT("> ")+TypedLine.Left(60),24,Height-48,2.5f,2.5f);
}
