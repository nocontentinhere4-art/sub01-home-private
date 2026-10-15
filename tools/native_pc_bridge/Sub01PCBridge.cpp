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
#include "ImageUtils.h"
#include "Engine/Texture2D.h"
#include "ImageCore.h"
#include "Sub01GuestFrameLayout.h"
#include "Sub01PCInputAckPolicy.h"

#include "Framework/Application/SlateApplication.h"
#include "Framework/Application/IInputProcessor.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"

// Scoped to PC focus. PixelStreaming2 supplies printable CharacterCode in the
// native Slate FKeyEvent (verified in its actual UE5.8 InputHandler.cpp).
class FSub01PCInputProcessor final : public IInputProcessor {
 TWeakObjectPtr<USub01PCBridge> Bridge;
 bool LeftShiftHeld=false,RightShiftHeld=false;
 bool MouseLeft=false,MouseMiddle=false,MouseRight=false;
 uint32 ScanFor(const FKey& Key)const{
  static const TMap<FString,uint32> Map={
   {TEXT("One"),2},{TEXT("Two"),3},{TEXT("Three"),4},{TEXT("Four"),5},{TEXT("Five"),6},{TEXT("Six"),7},{TEXT("Seven"),8},{TEXT("Eight"),9},{TEXT("Nine"),10},{TEXT("Zero"),11},
   {TEXT("Hyphen"),12},{TEXT("Equals"),13},{TEXT("BackSpace"),14},{TEXT("Tab"),15},
   {TEXT("Q"),16},{TEXT("W"),17},{TEXT("E"),18},{TEXT("R"),19},{TEXT("T"),20},{TEXT("Y"),21},{TEXT("U"),22},{TEXT("I"),23},{TEXT("O"),24},{TEXT("P"),25},{TEXT("LeftBracket"),26},{TEXT("RightBracket"),27},{TEXT("Enter"),28},
   {TEXT("A"),30},{TEXT("S"),31},{TEXT("D"),32},{TEXT("F"),33},{TEXT("G"),34},{TEXT("H"),35},{TEXT("J"),36},{TEXT("K"),37},{TEXT("L"),38},{TEXT("Semicolon"),39},{TEXT("Apostrophe"),40},{TEXT("Tilde"),41},{TEXT("Backslash"),43},
   {TEXT("Z"),44},{TEXT("X"),45},{TEXT("C"),46},{TEXT("V"),47},{TEXT("B"),48},{TEXT("N"),49},{TEXT("M"),50},{TEXT("Comma"),51},{TEXT("Period"),52},{TEXT("Slash"),53},{TEXT("SpaceBar"),57},{TEXT("CapsLock"),58},
   {TEXT("Up"),0xE048},{TEXT("Down"),0xE050},{TEXT("Left"),0xE04B},{TEXT("Right"),0xE04D},{TEXT("Delete"),0xE053},{TEXT("Home"),0xE047},{TEXT("End"),0xE04F},{TEXT("PageUp"),0xE049},{TEXT("PageDown"),0xE051}};
  const uint32* Scan=Map.Find(Key.GetFName().ToString());return Scan?*Scan:0;
 }
public:
 explicit FSub01PCInputProcessor(USub01PCBridge* InBridge):Bridge(InBridge){}
 void ResetModifiers(){LeftShiftHeld=false;RightShiftHeld=false;MouseLeft=MouseMiddle=MouseRight=false;}
 void Tick(const float,FSlateApplication&,TSharedRef<ICursor>) override {if(!Bridge.IsValid()||!Bridge->IsAcceptingNativeInput())ResetModifiers();}
 bool HandleKeyDownEvent(FSlateApplication&,const FKeyEvent& Event) override {
  auto* PC=Bridge.Get();if(!PC||!PC->IsAcceptingNativeInput()){ResetModifiers();return false;}
  const FKey Key=Event.GetKey();
  if(Key==EKeys::LeftShift){LeftShiftHeld=true;return true;}
  if(Key==EKeys::RightShift){RightShiftHeld=true;return true;}
  const bool Shift=LeftShiftHeld||RightShiftHeld||Event.IsShiftDown();
  if(Key==EKeys::Escape){PC->SetOperatorFocus(false);return true;}
  if(PC->IsGraphicalInputActive()){const uint32 Scan=ScanFor(Key);if(Scan)PC->SendGraphicalKey(Scan,Shift,Event.IsControlDown(),Event.IsAltDown());return true;}
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
 bool HandleMouseMoveEvent(FSlateApplication&,const FPointerEvent& Event) override {
  auto* PC=Bridge.Get();if(!PC||!PC->IsAcceptingNativeInput())return false;
  if(PC->IsGraphicalInputActive()){const FVector2D Delta=Event.GetCursorDelta();PC->SendGraphicalMouse(Delta.X,Delta.Y,0,MouseLeft,MouseMiddle,MouseRight);}return true;
 }
 bool MouseButton(const FPointerEvent& Event,bool Down){
  auto* PC=Bridge.Get();if(!PC||!PC->IsAcceptingNativeInput())return false;
  if(Event.GetEffectingButton()==EKeys::LeftMouseButton)MouseLeft=Down;
  if(Event.GetEffectingButton()==EKeys::MiddleMouseButton)MouseMiddle=Down;
  if(Event.GetEffectingButton()==EKeys::RightMouseButton)MouseRight=Down;
  if(PC->IsGraphicalInputActive())PC->SendGraphicalMouse(0,0,0,MouseLeft,MouseMiddle,MouseRight);return true;
 }
 bool HandleMouseButtonDownEvent(FSlateApplication&,const FPointerEvent& Event)override{return MouseButton(Event,true);}
 bool HandleMouseButtonUpEvent(FSlateApplication&,const FPointerEvent& Event)override{return MouseButton(Event,false);}
 bool HandleMouseWheelOrGestureEvent(FSlateApplication&,const FPointerEvent& WheelEvent,const FPointerEvent*)override{
  auto* PC=Bridge.Get();if(!PC||!PC->IsAcceptingNativeInput())return false;
  if(PC->IsGraphicalInputActive())PC->SendGraphicalMouse(0,0,WheelEvent.GetWheelDelta(),MouseLeft,MouseMiddle,MouseRight);return true;
 }
 const TCHAR* GetDebugName() const override {return TEXT("Sub01FocusedPCInput");}
};

void USub01PCBridge::ResetNativeModifiers(){if(NativeInputProcessor)StaticCastSharedPtr<FSub01PCInputProcessor>(NativeInputProcessor)->ResetModifiers();}
USub01PCBridge::USub01PCBridge(){PrimaryComponentTick.bCanEverTick=false;}
bool USub01PCBridge::Configure(UMeshComponent* Screen,int32 Slot,UMaterialInterface* Parent){
 if(Screen){const FVector Extent=Screen->CalcBounds(Screen->GetComponentTransform()).BoxExtent;if(Extent.X>0&&Extent.Z>0)ScreenAspect=Extent.X/Extent.Z;}
 const FString Configured=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_PC_ORIGIN"));
 if(!Configured.IsEmpty()){
  const bool Host=Configured.StartsWith(TEXT("http://127.0.0.1:"))||Configured.StartsWith(TEXT("http://localhost:"))||Configured.StartsWith(TEXT("http://[::1]:"));
  int32 Colon=0;Configured.FindLastChar(':',Colon);const FString Port=Configured.Mid(Colon+1);bool Digits=Port.Len()>0&&Port.Len()<=5;for(TCHAR C:Port)Digits&=FChar::IsDigit(C);
  if(!Host||!Digits||FCString::Atoi(*Port)<1||FCString::Atoi(*Port)>65535){Status=TEXT("Private PC origin is invalid");return false;}Origin=Configured;
 }

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
 GraphicalInputs.Cancel();OperatorToken.Empty();TerminalOutput.Empty();TypedLine.Empty();
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
 GraphicalInputs.Cancel();GuestPS2Input=false;GraphicalFrame=nullptr;FrameRevision.Empty();FrameBusy=false;
 Private=true;Focused=false;ResetNativeModifiers();++Generation;TerminalOutput.Empty();TypedLine.Empty();Status=Reason;
 if(MonitorMaterial&&TerminalCanvas){MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),TerminalCanvas);TerminalCanvas->UpdateResource();}
}
void USub01PCBridge::ApplyTerminal(const TSharedPtr<FJsonObject>& State){
 bool Ready=false;FString Output;
 if(!State){ClearPrivateState(TEXT("PC backend disconnected"));return;}
 State->TryGetBoolField(TEXT("ready"),Ready);State->TryGetStringField(TEXT("output"),Output);
 GuestPS2Input=false;const TSharedPtr<FJsonObject>* Display=nullptr;if(State->TryGetObjectField(TEXT("display"),Display)&&Display){bool Pixels=false;(*Display)->TryGetBoolField(TEXT("keyboard_available"),GuestPS2Input);(*Display)->TryGetBoolField(TEXT("available"),Pixels);GuestPS2Input|=Pixels;}
 Private=false;TerminalOutput=Output.Right(6000);Status=GuestPS2Input?TEXT("Actual guest VGA display"):Ready?TEXT("Live Linux computer"):TEXT("Linux computer is starting");
 // Keep the last authenticated real guest image while the next VGA image is
 // fetched. Switching to a text canvas on every poll causes visible flicker.
 if(Display&&*Display&&GraphicalFrame&&MonitorMaterial){bool Pixels=false;FString Kind;(*Display)->TryGetBoolField(TEXT("available"),Pixels);(*Display)->TryGetStringField(TEXT("kind"),Kind);if(Pixels&&Kind==TEXT("graphical")){MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),GraphicalFrame);return;}}
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
   FetchGraphicalFrame(After);

  });
 });
}
void USub01PCBridge::SendGraphicalInput(const TSharedPtr<FJsonObject>& Body){
 if(!IsGraphicalInputActive()||OperatorToken.IsEmpty())return;
 if(!GraphicalInputs.Push(Body)){SetOperatorFocus(false);Status=TEXT("Graphical input queue full; PC focus released");return;}
 PumpGraphicalInput();
}
void USub01PCBridge::PumpGraphicalInput(){
 TSharedPtr<FJsonObject> Body;std::uint64_t Ticket=0;
 if(!GraphicalInputs.Begin(Body,Ticket))return;
 const uint64 Epoch=Generation;
 const bool Correlated=FSub01PCInputAckPolicy::BoundedIdentity(Ticket)&&FSub01PCInputAckPolicy::BoundedIdentity(Epoch);
 FString Operation;Body->TryGetStringField(TEXT("type"),Operation);
 const FString ExpectedLevel=Operation==TEXT("vga-keyboard")?TEXT("GuestKeyboardInjected"):Operation==TEXT("vga-mouse")?TEXT("GuestMouseInjected"):TEXT("");
 if(Correlated){auto Receipt=MakeShared<FJsonObject>();Receipt->SetNumberField(TEXT("input_id"),static_cast<double>(Ticket));Receipt->SetNumberField(TEXT("generation"),static_cast<double>(Epoch));Body->SetObjectField(TEXT("native_receipt"),Receipt);}
 FString JSON;auto Writer=TJsonWriterFactory<>::Create(&JSON);FJsonSerializer::Serialize(Body.ToSharedRef(),Writer);
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(Origin+TEXT("/pc/graphical-input"));Request->SetVerb(TEXT("POST"));Request->SetTimeout(3);
 Request->SetHeader(TEXT("Content-Type"),TEXT("application/json"));Request->SetHeader(TEXT("X-Admin-Token"),OperatorToken);Request->SetContentAsString(JSON);
 auto Finish=[this,Epoch,Ticket](bool OK){
  if(Epoch!=Generation||!GraphicalInputs.Complete(Ticket))return;
  if(!OK){
   // Do not recursively enqueue a release if ProcessRequest itself failed.
   GraphicalInputs.Cancel();Focused=false;ResetNativeModifiers();
   SendFlag(TEXT("/pc/session"),false,[](bool){});Status=TEXT("Graphical input unavailable or refused");return;
  }
  PumpGraphicalInput();
 };
 Request->OnProcessRequestComplete().BindWeakLambda(this,[Finish,Correlated,Ticket,Epoch,ExpectedLevel](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){
  bool Accepted=false;TSharedPtr<FJsonObject> Result;
  if(OK&&Response&&Response->GetResponseCode()==200&&Response->GetContent().Num()<=16384){
   auto Reader=TJsonReaderFactory<>::Create(Response->GetContentAsString());
   if(FJsonSerializer::Deserialize(Reader,Result)&&Result)Result->TryGetBoolField(TEXT("ok"),Accepted);
  }
  if(Accepted&&Correlated){
   const TSharedPtr<FJsonObject>* Receipt=nullptr;double InputId=0,ReceiptGeneration=0,QueuedAt=-1,AckAt=-1,WorkerStarted=-1,WorkerFinished=-1;FString Level;
   const bool Fields=Result->TryGetObjectField(TEXT("native_receipt"),Receipt)&&Receipt&&Receipt->IsValid()&&(*Receipt)->Values.Num()==2&&(*Receipt)->TryGetNumberField(TEXT("input_id"),InputId)&&(*Receipt)->TryGetNumberField(TEXT("generation"),ReceiptGeneration);
   Result->TryGetStringField(TEXT("ack_level"),Level);Result->TryGetNumberField(TEXT("queued_at"),QueuedAt);Result->TryGetNumberField(TEXT("ack_received_at"),AckAt);Result->TryGetNumberField(TEXT("worker_started_ms"),WorkerStarted);Result->TryGetNumberField(TEXT("worker_finished_ms"),WorkerFinished);
   Accepted=FSub01PCInputAckPolicy::Correlated(Accepted,Fields,InputId,ReceiptGeneration,Ticket,Epoch,!ExpectedLevel.IsEmpty()&&Level==ExpectedLevel,QueuedAt,AckAt,WorkerStarted,WorkerFinished);
  }
  Finish(Accepted);
 });
 if(!Request->ProcessRequest())Finish(false);
}
void USub01PCBridge::SendGraphicalKey(uint32 Scan,bool Shift,bool Control,bool Alt){
 TArray<TSharedPtr<FJsonValue>> Codes;
 auto Add=[&Codes](uint32 Code){Codes.Add(MakeShared<FJsonValueNumber>(Code));};
 if(Control)Add(29);if(Alt)Add(56);if(Shift)Add(42);
 if(Scan>255)Add(224);Add(Scan&255);if(Scan>255)Add(224);Add((Scan&255)|128);
 if(Shift)Add(170);if(Alt)Add(184);if(Control)Add(157);
 auto Body=MakeShared<FJsonObject>();Body->SetStringField(TEXT("type"),TEXT("vga-keyboard"));Body->SetArrayField(TEXT("scancodes"),Codes);SendGraphicalInput(Body);
}
void USub01PCBridge::SendGraphicalMouse(float X,float Y,float Wheel,bool Left,bool Middle,bool Right){
 auto Body=MakeShared<FJsonObject>();Body->SetStringField(TEXT("type"),TEXT("vga-mouse"));Body->SetNumberField(TEXT("dx"),FMath::Clamp(X,-100.f,100.f));Body->SetNumberField(TEXT("dy"),FMath::Clamp(Y,-100.f,100.f));Body->SetNumberField(TEXT("wheel"),FMath::Clamp(Wheel,-100.f,100.f));
 TArray<TSharedPtr<FJsonValue>> Buttons={MakeShared<FJsonValueBoolean>(Left),MakeShared<FJsonValueBoolean>(Middle),MakeShared<FJsonValueBoolean>(Right)};Body->SetArrayField(TEXT("buttons"),Buttons);SendGraphicalInput(Body);
}
void USub01PCBridge::FetchGraphicalFrame(const TSharedPtr<FJsonObject>& State){
 const TSharedPtr<FJsonObject>* Display=nullptr;FString Kind;bool Available=false;double Revision=0;
 if(!IsPublicState(State)||!State->TryGetObjectField(TEXT("display"),Display)||!Display||!(*Display)->TryGetStringField(TEXT("kind"),Kind)||Kind!=TEXT("graphical")||!(*Display)->TryGetBoolField(TEXT("available"),Available)||!Available||!(*Display)->TryGetNumberField(TEXT("revision"),Revision)){
  GraphicalFrame=nullptr;FrameRevision.Empty();return;
 }
 FString Wanted;(*Display)->TryGetStringField(TEXT("frame_id"),Wanted);
 if(Wanted.IsEmpty())Wanted=FString::Printf(TEXT("%.0f"),Revision);
 if(GraphicalFrame&&FrameRevision==Wanted){if(MonitorMaterial)MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),GraphicalFrame);return;}
 if(FrameBusy)return;FrameBusy=true;const uint64 Epoch=Generation;
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(Origin+TEXT("/pc/frame.png?revision=")+Wanted);
 Request->SetVerb(TEXT("GET"));Request->SetTimeout(3);Request->SetHeader(TEXT("X-Admin-Token"),OperatorToken);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this,Epoch,Wanted](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){
  if(Epoch!=Generation)return;
  if(!OK||!Response||Response->GetResponseCode()!=200||Response->GetContent().Num()>6*1024*1024){FrameBusy=false;return;}
  const TArray<uint8> Pixels=Response->GetContent();
  // The frame is not applied until a second authenticated state read confirms
  // privacy and the exact VGA revision after the frame HTTP boundary.
  ReadState([this,Epoch,Wanted,Pixels](TSharedPtr<FJsonObject> After){
   if(Epoch!=Generation)return;FrameBusy=false;
   if(!IsPublicState(After)){ClearPrivateState(TEXT("Private screen hidden"));return;}
   const TSharedPtr<FJsonObject>* Display=nullptr;double Current=-1;bool Available=false;
   if(!After->TryGetObjectField(TEXT("display"),Display)||!Display||!(*Display)->TryGetNumberField(TEXT("revision"),Current)||!(*Display)->TryGetBoolField(TEXT("available"),Available)||!Available)return;
   FString CurrentKind;if(!(*Display)->TryGetStringField(TEXT("kind"),CurrentKind)||CurrentKind!=TEXT("graphical"))return;
   FString CurrentId;(*Display)->TryGetStringField(TEXT("frame_id"),CurrentId);if(CurrentId.IsEmpty())CurrentId=FString::Printf(TEXT("%.0f"),Current);if(CurrentId!=Wanted)return;
   FImage Decoded,BGRA,Padded;
   if(!FImageUtils::DecompressImage(Pixels.GetData(),Pixels.Num(),Decoded))return;
   FSub01GuestFrameLayout Layout;
   if(!Sub01GuestFrameLayout(Decoded.SizeX,Decoded.SizeY,ScreenAspect,Layout)||Decoded.NumSlices!=1)return;
   Decoded.CopyTo(BGRA,ERawImageFormat::BGRA8,EGammaSpace::sRGB);
   Padded.Init(Layout.Width,Layout.Height,ERawImageFormat::BGRA8,EGammaSpace::sRGB);
   if(!Sub01PadGuestBGRA(BGRA.RawData.GetData(),BGRA.RawData.Num(),Padded.RawData.GetData(),Padded.RawData.Num(),Layout))return;
   UTexture2D* Texture=FImageUtils::CreateTexture2DFromImage(Padded);
   if(!Texture)return;
   Texture->SRGB=true;Texture->UpdateResource();GraphicalFrame=Texture;FrameRevision=Wanted;
   if(MonitorMaterial)MonitorMaterial->SetTextureParameterValue(TEXT("PCFrame"),GraphicalFrame);
  });
 });
 if(!Request->ProcessRequest())FrameBusy=false;
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
 if(!Focus){GraphicalInputs.ClearPending();if(IsGraphicalInputActive())SendGraphicalMouse(0,0,0,false,false,false);}
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
