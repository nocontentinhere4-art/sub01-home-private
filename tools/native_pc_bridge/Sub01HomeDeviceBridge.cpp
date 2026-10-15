#include "Sub01HomeDeviceBridge.h"
#include "Sub01DeviceScreenPolicy.h"
#include "Components/MeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/CanvasRenderTarget2D.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/Engine.h"
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "ImageUtils.h"
#include "TimerManager.h"
#include "Framework/Application/SlateApplication.h"
#include "Framework/Application/IInputProcessor.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/PlayerController.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SMultiLineEditableTextBox.h"
#include "Widgets/Text/STextBlock.h"
// Current phone frame: GET /api/home phone_screen {kind:"owned_app"|"browser",available,frame_id}
// first, else the older phone_browser_screen.frame_id. Empty when no frame is available.
static FString Sub01PhoneIdentity(const TSharedPtr<FJsonObject>& State,bool* OwnedApp=nullptr){
 const TSharedPtr<FJsonObject>* Screen=nullptr;FString Id,Kind;bool Available=false;if(OwnedApp)*OwnedApp=false;
 if(State.IsValid()&&State->TryGetObjectField(TEXT("phone_screen"),Screen)&&Screen&&(*Screen).IsValid()){
  if(!(*Screen)->TryGetBoolField(TEXT("available"),Available)||!Available||!(*Screen)->TryGetStringField(TEXT("kind"),Kind)||(Kind!=TEXT("owned_app")&&Kind!=TEXT("browser"))
   ||!(*Screen)->TryGetStringField(TEXT("frame_id"),Id)||Id.IsEmpty()||Id.Len()>100)return FString();
  if(OwnedApp)*OwnedApp=Kind==TEXT("owned_app");return Id;
 }
 if(State.IsValid()&&State->TryGetObjectField(TEXT("phone_browser_screen"),Screen)&&Screen&&(*Screen).IsValid()&&(*Screen)->TryGetStringField(TEXT("frame_id"),Id)&&!Id.IsEmpty()&&Id.Len()<=100)return Id;
 return FString();
}
// The exact request body Action sends (also measured before a note is sent).
static FString Sub01JsonBody(const TSharedPtr<FJsonObject>& Body){
 FString Data;auto Writer=TJsonWriterFactory<>::Create(&Data);FJsonSerializer::Serialize(Body.ToSharedRef(),Writer);return Data;
}
// The screen-policy inputs of one /devices/state document (Poll and the final
// paint check read the same fields the same way). PublicHome is decided by the caller.
static FSub01DeviceScreenInputs Sub01ScreenInputs(const TSharedPtr<FJsonObject>& State,FString* PhoneIdentity=nullptr,FString* Game=nullptr){
 FSub01DeviceScreenInputs In;In.PublicHome=true;FString Activity,Console;
 const TSharedPtr<FJsonObject>* Home=nullptr;
 if(State.IsValid()&&State->TryGetObjectField(TEXT("home"),Home)&&Home&&(*Home).IsValid()){(*Home)->TryGetStringField(TEXT("console_game"),Console);(*Home)->TryGetStringField(TEXT("activity"),Activity);}
 In.PhoneActivity=Activity==TEXT("phone");In.MinecraftSelected=Console==TEXT("minecraft");
 const TSharedPtr<FJsonObject>* Minecraft=nullptr;
 if(State.IsValid()&&State->TryGetObjectField(TEXT("minecraft"),Minecraft)&&Minecraft&&(*Minecraft).IsValid()){(*Minecraft)->TryGetBoolField(TEXT("enabled"),In.MinecraftEnabled);(*Minecraft)->TryGetBoolField(TEXT("has_frame"),In.MinecraftFrame);}
 bool OwnedApp=false;const FString Identity=Sub01PhoneIdentity(State,&OwnedApp);In.PhoneAppFrame=OwnedApp;In.PhoneFrame=!OwnedApp&&!Identity.IsEmpty();
 if(PhoneIdentity)*PhoneIdentity=Identity;if(Game)*Game=Console;return In;
}
// Downloaded bytes may be painted only if the fresh state still allows that exact
// frame by the same policy Poll used: same phone identity and still showable
// (owned app while public; browser only while he is on the phone), or Minecraft
// still selected, enabled and with a frame.
static bool Sub01FrameStillCurrent(bool Phone,const FString& Identity,const TSharedPtr<FJsonObject>& After,bool PhysicalPhoneFocus=false){
 FString CurrentIdentity;const FSub01DeviceScreenInputs In=Sub01ScreenInputs(After,&CurrentIdentity);
 if(Phone)return !Identity.IsEmpty()&&CurrentIdentity==Identity&&Sub01PhoneFrame(In,PhysicalPhoneFocus)!=ESub01PhoneFrame::None;
 return Sub01TVFetchesMinecraft(In);
}
class FSub01DeviceInput:public IInputProcessor{
 TWeakObjectPtr<USub01HomeDeviceBridge> Bridge;bool Up=false,Down=false,NotePressed=false,AddressPressed=false;
public:
 explicit FSub01DeviceInput(USub01HomeDeviceBridge* B):Bridge(B){}
 void Tick(const float,FSlateApplication&,TSharedRef<ICursor>)override{if(!Bridge.IsValid()||Bridge->GetFocusedDevice().IsNone()){Up=Down=false;}}
 bool HandleKeyDownEvent(FSlateApplication&,const FKeyEvent& Event)override{
  auto* B=Bridge.Get();if(!B)return false;const FKey K=Event.GetKey();
  if(B->IsComposingAddress()){
   if(K==EKeys::Escape){B->ClosePhoneAddress(false);return true;}
   if(K==EKeys::Enter){B->SubmitPhoneAddress();return true;}
   return false; // Slate owns text; WASD never moves the pawn while editing.
  }
  if(B->IsComposingNote()){
   // Text widgets receive every other key, Backspace/Enter included; game input is UI-only meanwhile.
   if(K==EKeys::Escape){B->CloseNoteComposer(false);return true;}
   if(K==EKeys::Enter&&Event.IsControlDown()){B->SubmitNoteComposer();return true;}
   return false;
  }
  if(B->GetFocusedDevice().IsNone())return false;
  if(K==EKeys::Escape){B->ReleaseFocus();return true;}
  if(B->GetFocusedDevice()==TEXT("phone")){
   if(K==EKeys::Up)B->PhoneAction(TEXT("scroll_up"));if(K==EKeys::Down)B->PhoneAction(TEXT("scroll_down"));if(K==EKeys::BackSpace)B->PhoneAction(TEXT("back"));if(K==EKeys::Enter)B->PhoneAction(TEXT("close_notice"));
   if(K==EKeys::Home)B->PhoneAction(TEXT("home"));if(K==EKeys::One)B->PhoneOpenApp(TEXT("home"));if(K==EKeys::Two)B->PhoneOpenApp(TEXT("notes"));if(K==EKeys::Three)B->PhoneOpenApp(TEXT("memory"));if(K==EKeys::Four)B->PhoneOpenApp(TEXT("browser"));
   if(K==EKeys::B)AddressPressed=true;
   if(K==EKeys::N)NotePressed=true; // opened on release, so the N character never reaches the editor
  }else{
   if(K==EKeys::Up)Up=true;if(K==EKeys::Down)Down=true;B->SetPongDirection(float(Down)-float(Up));
   if(K==EKeys::One)B->TVGame(TEXT("pong"));if(K==EKeys::Two)B->TVGame(TEXT("chess"));if(K==EKeys::Three)B->TVGame(TEXT("minecraft"));
  }return true;
 }
 bool HandleKeyUpEvent(FSlateApplication&,const FKeyEvent& Event)override{auto* B=Bridge.Get();if(!B||B->IsComposingNote())return false;if(B->IsComposingAddress())return false;if(B->GetFocusedDevice().IsNone()){NotePressed=AddressPressed=false;return false;}
  if(Event.GetKey()==EKeys::B&&AddressPressed){AddressPressed=false;if(B->GetFocusedDevice()==TEXT("phone"))B->OpenPhoneAddress();return true;}
  if(Event.GetKey()==EKeys::N&&NotePressed){NotePressed=false;if(B->GetFocusedDevice()==TEXT("phone"))B->OpenNoteComposer();return true;}
 if(Event.GetKey()==EKeys::Up)Up=false;if(Event.GetKey()==EKeys::Down)Down=false;B->SetPongDirection(float(Down)-float(Up));return true;}
 bool HandleMouseMoveEvent(FSlateApplication&,const FPointerEvent&)override{return Bridge.IsValid()&&!Bridge->IsComposingNote()&&!Bridge->IsComposingAddress()&&!Bridge->GetFocusedDevice().IsNone();}
};
USub01HomeDeviceBridge::USub01HomeDeviceBridge(){PrimaryComponentTick.bCanEverTick=false;}
bool USub01HomeDeviceBridge::Configure(FName Device,UMeshComponent* Screen,int32 Slot,UMaterialInterface* Parent){
 const FString Configured=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_PC_ORIGIN"));
 if(!Configured.IsEmpty()){
  const bool Host=Configured.StartsWith(TEXT("http://127.0.0.1:"))||Configured.StartsWith(TEXT("http://localhost:"))||Configured.StartsWith(TEXT("http://[::1]:"));
  int32 Colon=0;Configured.FindLastChar(':',Colon);const FString Port=Configured.Mid(Colon+1);bool Digits=Port.Len()>0&&Port.Len()<=5;for(TCHAR C:Port)Digits&=FChar::IsDigit(C);
  if(!Host||!Digits||FCString::Atoi(*Port)<1||FCString::Atoi(*Port)>65535){return false;}Origin=Configured;
 }

 if((Device!=TEXT("phone")&&Device!=TEXT("tv"))||!Screen||!Parent||Slot<0||Slot>=Screen->GetNumMaterials())return false;
 Token=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN"));if(Token.IsEmpty())return false;
 if(!BlankCanvas){BlankCanvas=UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(GetWorld(),UCanvasRenderTarget2D::StaticClass(),8,8);BlankCanvas->ClearColor=FLinearColor::Black;BlankCanvas->UpdateResource();}
 auto* Material=UMaterialInstanceDynamic::Create(Parent,this);Material->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);Screen->SetMaterial(Slot,Material);Materials.Add(Device,Material);Screens.Add(Screen,Device);
 if(Device==TEXT("tv")){TVCanvas=UCanvasRenderTarget2D::CreateCanvasRenderTarget2D(GetWorld(),UCanvasRenderTarget2D::StaticClass(),800,460);TVCanvas->ClearColor=FLinearColor(.05,.1,.1,1);TVCanvas->OnCanvasRenderTargetUpdate.AddDynamic(this,&USub01HomeDeviceBridge::DrawTV);}
 if(!Input&&FSlateApplication::IsInitialized()){Input=MakeShared<FSub01DeviceInput>(this);FSlateApplication::Get().RegisterInputPreProcessor(Input,0);}
 GetWorld()->GetTimerManager().SetTimer(Timer,this,&USub01HomeDeviceBridge::Poll,.15f,true);return true;
}
void USub01HomeDeviceBridge::EndPlay(const EEndPlayReason::Type Reason){Clear();GetWorld()->GetTimerManager().ClearTimer(Timer);if(Input&&FSlateApplication::IsInitialized())FSlateApplication::Get().UnregisterInputPreProcessor(Input);Input.Reset();Token.Empty();Super::EndPlay(Reason);}
void USub01HomeDeviceBridge::Clear(){MinecraftVisible=false;MinecraftStateReceived=0;ClosePhoneAddress(true);CloseNoteComposer(true);PhoneApp.Empty();++Generation;Private=true;Busy=false;FocusedDevice=NAME_None;PongDirection=0;PongState.Reset();PhoneFrameId.Empty();Images.Empty();ImageIdentity.Empty();FramePending.Empty();for(auto& Pair:Materials)if(Pair.Value)Pair.Value->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);}
void USub01HomeDeviceBridge::SetLocalPrivacy(bool Hidden){if(Hidden==LocalPrivacy)return;LocalPrivacy=Hidden;if(Hidden)Clear();}
bool USub01HomeDeviceBridge::FocusHit(UActorComponent* Component){if(Private||LocalPrivacy)return false;for(auto& Pair:Screens)if(Pair.Key==Component){FocusedDevice=Pair.Value;return true;}return false;}
void USub01HomeDeviceBridge::ReleaseFocus(){if(NoteComposer.Open)CloseNoteComposer(false);if(AddressOpen)ClosePhoneAddress(false);if(FocusedDevice==TEXT("tv")&&!Private&&!LocalPrivacy){auto B=MakeShared<FJsonObject>();B->SetNumberField(TEXT("direction"),0);Action(TEXT("tv"),B);}FocusedDevice=NAME_None;PongDirection=0;}
void USub01HomeDeviceBridge::ReadHome(TFunction<void(TSharedPtr<FJsonObject>)> Done){
 auto Callback=MakeShared<TFunction<void(TSharedPtr<FJsonObject>)>>(MoveTemp(Done));auto R=FHttpModule::Get().CreateRequest();R->SetURL(Origin+TEXT("/devices/state"));R->SetVerb(TEXT("GET"));R->SetTimeout(3);R->SetHeader(TEXT("X-Admin-Token"),Token);
 R->OnProcessRequestComplete().BindWeakLambda(this,[Callback](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){TSharedPtr<FJsonObject> State;if(OK&&Response&&Response->GetResponseCode()==200){auto Reader=TJsonReaderFactory<>::Create(Response->GetContentAsString());FJsonSerializer::Deserialize(Reader,State);}(*Callback)(State);});if(!R->ProcessRequest())(*Callback)(nullptr);
}
bool USub01HomeDeviceBridge::PublicHome(const TSharedPtr<FJsonObject>& State)const{const TSharedPtr<FJsonObject>* Home=nullptr;bool Hidden=true;return !LocalPrivacy&&State&&State->TryGetObjectField(TEXT("home"),Home)&&Home&&(*Home)->TryGetBoolField(TEXT("privacy"),Hidden)&&!Hidden;}
void USub01HomeDeviceBridge::Poll(){
 if(LocalPrivacy||Busy||Token.IsEmpty())return;Busy=true;const uint64 Epoch=Generation;
 ReadHome([this,Epoch](TSharedPtr<FJsonObject> State){if(Epoch!=Generation)return;Busy=false;if(!PublicHome(State)){Clear();return;}Private=false;
  const TSharedPtr<FJsonObject>* Home=nullptr;State->TryGetObjectField(TEXT("home"),Home);FString Game,Identity;
  const FSub01DeviceScreenInputs Screen=Sub01ScreenInputs(State,&Identity,&Game);
  MinecraftVisible=Sub01TVFetchesMinecraft(Screen);MinecraftStateReceived=FPlatformTime::Seconds();
  PhoneApp.Empty();{const TSharedPtr<FJsonObject>* PhoneScreen=nullptr;if(State->TryGetObjectField(TEXT("phone_screen"),PhoneScreen)&&PhoneScreen)(*PhoneScreen)->TryGetStringField(TEXT("app"),PhoneApp);}
  if(AddressOpen&&PhoneApp!=TEXT("browser"))ClosePhoneAddress(false);
  // Browser parity (Sub01DeviceScreenPolicy.h): a browser page only while he is on the
  // phone or physically focused by the operator; same authenticated route.
  if(Sub01PhoneFrame(Screen,FocusedDevice==TEXT("phone"))!=ESub01PhoneFrame::None)FetchFrame(TEXT("phone"),Identity,Epoch);
  else if(Materials.Contains(TEXT("phone"))){Materials[TEXT("phone")]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);Images.Remove(TEXT("phone"));ImageIdentity.Remove(TEXT("phone"));PhoneFrameId.Empty();}
  // Minecraft only with a live frame; selected without one, the TV stays blank (below).
  if(Sub01TVFetchesMinecraft(Screen))FetchFrame(TEXT("tv"),TEXT(""),Epoch);
  else if(Game==TEXT("pong")){const TSharedPtr<FJsonObject>* Pong=nullptr;if((*Home)->TryGetObjectField(TEXT("pong"),Pong)&&Pong){PongState=*Pong;if(TVCanvas){TVCanvas->UpdateResource();if(Materials.Contains(TEXT("tv")))Materials[TEXT("tv")]->SetTextureParameterValue(TEXT("PCFrame"),TVCanvas);}}}
  else if(Materials.Contains(TEXT("tv")))Materials[TEXT("tv")]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);
  if(FocusedDevice==TEXT("tv")&&Game==TEXT("pong")){auto Body=MakeShared<FJsonObject>();Body->SetNumberField(TEXT("direction"),PongDirection);Action(TEXT("tv"),Body);}
 });
}
void USub01HomeDeviceBridge::FetchFrame(FName Device,const FString& Identity,uint64 Epoch){
 if(!Materials.Contains(Device)||LocalPrivacy||FramePending.Contains(Device))return;
 if(Device==TEXT("phone")&&Images.Contains(Device)&&ImageIdentity.FindRef(Device)==Identity)return;FramePending.Add(Device);auto R=FHttpModule::Get().CreateRequest();R->SetURL(Origin+TEXT("/devices/")+Device.ToString()+TEXT("/frame.jpg")+(Identity.IsEmpty()?TEXT(""):TEXT("?frame_id=")+Identity));R->SetVerb(TEXT("GET"));R->SetTimeout(3);R->SetHeader(TEXT("X-Admin-Token"),Token);
 R->OnProcessRequestComplete().BindWeakLambda(this,[this,Device,Identity,Epoch](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){if(Epoch!=Generation)return;if(!OK||!Response||Response->GetResponseCode()!=200){FramePending.Remove(Device);if(Materials.Contains(Device))Materials[Device]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);Images.Remove(Device);ImageIdentity.Remove(Device);return;}const FString Tag=Response->GetHeader(TEXT("ETag"));const TArray<uint8> Pixels=Response->GetContent();if(Pixels.Num()>6*1024*1024){FramePending.Remove(Device);return;}
  ReadHome([this,Device,Identity,Epoch,Pixels,Tag](TSharedPtr<FJsonObject> After){if(Epoch!=Generation)return;FramePending.Remove(Device);if(!PublicHome(After)){Clear();return;}
   // Same policy as Poll, re-evaluated on the fresh state at the moment of painting.
   if(!Sub01FrameStillCurrent(Device==TEXT("phone"),Identity,After,FocusedDevice==TEXT("phone")))return;
   const FString CurrentIdentity=Device==TEXT("phone")?Identity:Tag;
   if(!CurrentIdentity.IsEmpty()&&Images.Contains(Device)&&ImageIdentity.FindRef(Device)==CurrentIdentity){if(Materials.Contains(Device))Materials[Device]->SetTextureParameterValue(TEXT("PCFrame"),Images[Device]);return;}
   auto* Texture=FImageUtils::ImportBufferAsTexture2D(Pixels);if(!Texture||Texture->GetSizeX()>2048||Texture->GetSizeY()>2048)return;Texture->SRGB=true;Texture->UpdateResource();Images.Add(Device,Texture);ImageIdentity.Add(Device,CurrentIdentity);if(Materials.Contains(Device))Materials[Device]->SetTextureParameterValue(TEXT("PCFrame"),Texture);if(Device==TEXT("phone"))PhoneFrameId=Identity;
  });});if(!R->ProcessRequest())FramePending.Remove(Device);
}
void USub01HomeDeviceBridge::Action(FName Device,const TSharedPtr<FJsonObject>& Body,TFunction<void(int32,const FString&)> Done){
 auto Result=MakeShared<TFunction<void(int32,const FString&)>>(MoveTemp(Done));
 if(Private||LocalPrivacy||Token.IsEmpty()){if(*Result)(*Result)(0,FString());return;}const uint64 Epoch=Generation;
 ReadHome([this,Device,Body,Epoch,Result](TSharedPtr<FJsonObject> Before){if(Epoch!=Generation)return;if(!PublicHome(Before)){Clear();return;}const FString Data=Sub01JsonBody(Body);auto R=FHttpModule::Get().CreateRequest();R->SetURL(Origin+TEXT("/devices/")+Device.ToString()+TEXT("/action"));R->SetVerb(TEXT("POST"));FString ActionName;Body->TryGetStringField(TEXT("action"),ActionName);R->SetTimeout(Device==TEXT("phone")&&ActionName==TEXT("navigate")?35.f:3.f);R->SetHeader(TEXT("Content-Type"),TEXT("application/json"));R->SetHeader(TEXT("X-Admin-Token"),Token);R->SetContentAsString(Data);// The existing 150 ms poll refreshes state. Calling Poll from this reply
   // recursively re-sends held Pong input faster than the backend rate limit.
   if(*Result)R->OnProcessRequestComplete().BindWeakLambda(this,[this,Epoch,Result](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){
    if(Epoch!=Generation)return;(*Result)(OK&&Response?Response->GetResponseCode():0,OK&&Response?Response->GetContentAsString():FString());});
   if(!R->ProcessRequest()&&*Result)(*Result)(0,FString());});
}
void USub01HomeDeviceBridge::PhoneAction(const FString& ActionName){if(PhoneFrameId.IsEmpty())return;auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("action"),ActionName);B->SetStringField(TEXT("frame_id"),PhoneFrameId);Action(TEXT("phone"),B);}
void USub01HomeDeviceBridge::PhoneOpenApp(const FString& App){if(PhoneFrameId.IsEmpty()||(App!=TEXT("home")&&App!=TEXT("notes")&&App!=TEXT("memory")&&App!=TEXT("browser")))return;auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("action"),TEXT("open_app"));B->SetStringField(TEXT("app"),App);B->SetStringField(TEXT("frame_id"),PhoneFrameId);Action(TEXT("phone"),B);}
void USub01HomeDeviceBridge::PhoneSaveNote(const FString& Title,const FString& Text){
 const ESub01NoteCheck Check=Sub01CheckNote(*Title,size_t(Title.Len()),*Text,size_t(Text.Len()));
 if(Check!=ESub01NoteCheck::Ok){ShowNoteStatus(UTF8_TO_TCHAR(Sub01NoteMessage(Check)));return;}
 if(PhoneFrameId.IsEmpty()||PhoneApp!=TEXT("notes")){ShowNoteStatus(UTF8_TO_TCHAR(Sub01NoteMessage(ESub01NoteSave::Stale)));return;}
 if(NoteComposer.Saving){ShowNoteStatus(TEXT("Saving the previous note..."));return;}
 auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("action"),TEXT("save_note"));B->SetStringField(TEXT("frame_id"),PhoneFrameId);
 if(!Title.TrimStartAndEnd().IsEmpty())B->SetStringField(TEXT("title"),Title);B->SetStringField(TEXT("text"),Text);
 // The proxy and backend bound the request body in bytes; measure exactly what Action will send.
 const FString Encoded=Sub01JsonBody(B);
 if(Sub01CheckEncodedNote(Sub01Utf8Length(*Encoded,size_t(Encoded.Len())))!=ESub01NoteCheck::Ok){ShowNoteStatus(UTF8_TO_TCHAR(Sub01NoteMessage(ESub01NoteCheck::EncodedTooLarge)));return;}
 const unsigned long long Id=NoteComposer.TryBeginSave(Check);if(!Id)return;ShowNoteStatus(TEXT("Saving..."));
 Action(TEXT("phone"),B,[this,Id](int32 Code,const FString& Reply){
  TSharedPtr<FJsonObject> Json;bool Ok=false;
  if(Code==200&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Reply),Json)&&Json.IsValid())Json->TryGetBoolField(TEXT("ok"),Ok);
  if(!NoteComposer.Saving||Id!=NoteComposer.Request)return; // a superseded request: never reported
  const ESub01NoteSave Outcome=Sub01NoteSaveOutcome(Code,Ok);
  // Only a confirmed save clears the draft; stale, rejected or failed saves keep it.
  if(NoteComposer.Finish(Id,Outcome)){DraftTitle.Empty();DraftText.Empty();CloseNoteComposer(false);}
  ShowNoteStatus(UTF8_TO_TCHAR(Sub01NoteMessage(Outcome)));
 });
}
bool USub01HomeDeviceBridge::OpenNoteComposer(){
 if(AddressOpen)ClosePhoneAddress(false);
 if(NoteComposer.Open)return true;
 if(NoteComposer.Saving){ShowNoteStatus(TEXT("Saving the previous note..."));return false;}
 if(!NoteComposer.TryOpen(!Private&&!LocalPrivacy&&!Token.IsEmpty(),PhoneApp==TEXT("notes"),!PhoneFrameId.IsEmpty())){ShowNoteStatus(TEXT("Open Notes on the phone (key 2), then press N to write."));return false;}
 if(!GEngine||!GEngine->GameViewport){NoteComposer.Close();return false;}
 TWeakObjectPtr<USub01HomeDeviceBridge> Weak(this);
 NoteWidget=SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Center)[SNew(SBox).WidthOverride(560)[SNew(SBorder).Padding(16)[
  SNew(SVerticalBox)
  +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)[SNew(STextBlock).Text(FText::FromString(TEXT("New note")))]
  +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)[SAssignNew(NoteTitleBox,SEditableTextBox).HintText(FText::FromString(TEXT("Title (optional)"))).Text(FText::FromString(DraftTitle))
   .IsReadOnly_Lambda([Weak](){return !Weak.IsValid()||!Weak->NoteComposer.CanEdit();}).OnTextChanged_Lambda([Weak](const FText&){if(Weak.IsValid()&&!Weak->NoteProgrammatic)Weak->NoteComposer.Edited();})]
  +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)[SNew(SBox).HeightOverride(220)[SAssignNew(NoteTextBox,SMultiLineEditableTextBox).HintText(FText::FromString(TEXT("Note"))).Text(FText::FromString(DraftText)).AutoWrapText(true)
   .IsReadOnly_Lambda([Weak](){return !Weak.IsValid()||!Weak->NoteComposer.CanEdit();}).OnTextChanged_Lambda([Weak](const FText&){if(Weak.IsValid()&&!Weak->NoteProgrammatic)Weak->NoteComposer.Edited();})]]
  +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)[SAssignNew(NoteStatus,STextBlock).Text(FText::FromString(TEXT("Ctrl+Enter saves. Esc closes and keeps the draft."))).AutoWrapText(true)]
  +SVerticalBox::Slot().AutoHeight()[SNew(SHorizontalBox)
   +SHorizontalBox::Slot().AutoWidth().Padding(0,0,8,0)[SNew(SButton).Text(FText::FromString(TEXT("Save"))).IsEnabled_Lambda([Weak](){return Weak.IsValid()&&Weak->NoteComposer.CanEdit();}).OnClicked_Lambda([Weak](){if(Weak.IsValid())Weak->SubmitNoteComposer();return FReply::Handled();})]
   +SHorizontalBox::Slot().AutoWidth()[SNew(SButton).Text(FText::FromString(TEXT("Close"))).OnClicked_Lambda([Weak](){if(Weak.IsValid())Weak->CloseNoteComposer(false);return FReply::Handled();})]]
 ]]];
 GEngine->GameViewport->AddViewportWidgetContent(NoteWidget.ToSharedRef(),100);
 // UI-only input: typed keys never move the operator while the editor is open.
 if(APlayerController* Player=GetWorld()?GetWorld()->GetFirstPlayerController():nullptr){FInputModeUIOnly Mode;Mode.SetWidgetToFocus(NoteTextBox);Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);Player->SetInputMode(Mode);Player->SetShowMouseCursor(true);}
 return true;
}
void USub01HomeDeviceBridge::ReadNoteDraft(){
 if(NoteTitleBox.IsValid())DraftTitle=NoteTitleBox->GetText().ToString();
 if(NoteTextBox.IsValid())DraftText=NoteTextBox->GetText().ToString();
}
void USub01HomeDeviceBridge::SubmitNoteComposer(){if(!NoteComposer.Open)return;ReadNoteDraft();PhoneSaveNote(DraftTitle,DraftText);}
void USub01HomeDeviceBridge::CloseNoteComposer(bool Discard){
 if(Discard){NoteComposer.Reset();DraftTitle.Empty();DraftText.Empty();NoteStatusText.Empty();}
 else{if(NoteComposer.Open)ReadNoteDraft();NoteComposer.Close();}
 NoteProgrammatic=true;
 if(NoteTitleBox.IsValid())NoteTitleBox->SetText(FText::GetEmpty());
 if(NoteTextBox.IsValid())NoteTextBox->SetText(FText::GetEmpty());
 NoteProgrammatic=false;
 if(NoteWidget.IsValid()&&GEngine&&GEngine->GameViewport)GEngine->GameViewport->RemoveViewportWidgetContent(NoteWidget.ToSharedRef());
 const bool Shown=NoteWidget.IsValid();NoteWidget.Reset();NoteTitleBox.Reset();NoteTextBox.Reset();NoteStatus.Reset();
 if(Shown)if(APlayerController* Player=GetWorld()?GetWorld()->GetFirstPlayerController():nullptr){Player->SetInputMode(FInputModeGameOnly());Player->SetShowMouseCursor(false);}
}
void USub01HomeDeviceBridge::ShowNoteStatus(const FString& Message){
 NoteStatusText=Message;if(NoteStatus.IsValid())NoteStatus->SetText(FText::FromString(Message));
 else if(GEngine&&!Message.IsEmpty())GEngine->AddOnScreenDebugMessage(-1,4,FColor::Orange,Message);
}
void USub01HomeDeviceBridge::PhoneNavigate(const FString& URL){if(URL.IsEmpty()||URL.Len()>2048||!URL.StartsWith(TEXT("https://"),ESearchCase::IgnoreCase))return;auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("action"),TEXT("navigate"));B->SetStringField(TEXT("url"),URL);if(!PhoneFrameId.IsEmpty())B->SetStringField(TEXT("frame_id"),PhoneFrameId);Action(TEXT("phone"),B);}
void USub01HomeDeviceBridge::TVGame(const FString& Game){auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("game"),Game);Action(TEXT("tv"),B);}
void USub01HomeDeviceBridge::DrawTV(UCanvas* Canvas,int32 Width,int32 Height){if(!Canvas||Private||LocalPrivacy||!PongState)return;const TArray<TSharedPtr<FJsonValue>> *Paddles=nullptr,*Ball=nullptr,*Score=nullptr;if(!PongState->TryGetArrayField(TEXT("paddles"),Paddles)||!PongState->TryGetArrayField(TEXT("ball"),Ball)||!PongState->TryGetArrayField(TEXT("score"),Score)||Paddles->Num()!=2||Ball->Num()!=2||Score->Num()!=2)return;
 Canvas->SetDrawColor(FColor(217,232,217));Canvas->K2_DrawBox(FVector2D(.04f*Width,(*Paddles)[0]->AsNumber()*Height-.1f*Height),FVector2D(8,.2f*Height),4,FLinearColor(FColor(217,232,217)));Canvas->K2_DrawBox(FVector2D(.95f*Width,(*Paddles)[1]->AsNumber()*Height-.1f*Height),FVector2D(8,.2f*Height),4,FLinearColor(FColor(217,232,217)));Canvas->K2_DrawBox(FVector2D((*Ball)[0]->AsNumber()*Width-4,(*Ball)[1]->AsNumber()*Height-4),FVector2D(8,8),4,FLinearColor(FColor(217,232,217)));if(GEngine)Canvas->DrawText(GEngine->GetSmallFont(),FString::Printf(TEXT("%d : %d"),int32((*Score)[0]->AsNumber()),int32((*Score)[1]->AsNumber())),Width*.44f,24,2,2);
}

bool USub01HomeDeviceBridge::GetDisplayedMinecraftFrame(FString& Frame)const{
 Frame.Empty();const double Age=FPlatformTime::Seconds()-MinecraftStateReceived;
 if(Private||LocalPrivacy||!MinecraftVisible||Age<0||Age>.75||!Images.Contains(TEXT("tv"))||!Materials.Contains(TEXT("tv")))return false;
 UTexture* Painted=nullptr;auto* M=Materials.FindRef(TEXT("tv")).Get();
 if(!M||!M->GetTextureParameterValue(FMaterialParameterInfo(TEXT("PCFrame")),Painted)||Painted!=Images.FindRef(TEXT("tv")))return false;
 Frame=ImageIdentity.FindRef(TEXT("tv"));Frame.ReplaceInline(TEXT("\""),TEXT(""));return !Frame.IsEmpty();
}

// Real phone address entry. This is local UI, not a substitute browser image.
// The existing authenticated proxy validates public HTTPS and exact frame ID;
// it alone starts the isolated product browser and returns actual page pixels.
bool USub01HomeDeviceBridge::OpenPhoneAddress(){
 if(AddressOpen)return true;
 if(Private||LocalPrivacy||Token.IsEmpty()||FocusedDevice!=TEXT("phone")||PhoneApp!=TEXT("browser")||PhoneFrameId.IsEmpty()||!GEngine||!GEngine->GameViewport){ShowNoteStatus(TEXT("Open Browser on the phone (key 4), then press B for an address."));return false;}
 if(NoteComposer.Open)CloseNoteComposer(false);
 AddressOpen=true;AddressPending=false;++AddressRequest;TWeakObjectPtr<USub01HomeDeviceBridge> Weak(this);
 AddressWidget=SNew(SBox).HAlign(HAlign_Center).VAlign(VAlign_Center)[SNew(SBox).WidthOverride(600)[SNew(SBorder).Padding(20)[
  SNew(SVerticalBox)
  +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)[SNew(STextBlock).Text(FText::FromString(TEXT("Phone browser")))]
  +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)[SAssignNew(AddressBox,SEditableTextBox).HintText(FText::FromString(TEXT("https://example.com"))).Text(FText::FromString(AddressDraft))
    .IsReadOnly_Lambda([Weak](){return !Weak.IsValid()||Weak->AddressPending;})]
  +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)[SAssignNew(AddressStatus,STextBlock).Text(FText::FromString(TEXT("Enter opens the page. Esc closes and keeps the address."))).AutoWrapText(true)]
  +SVerticalBox::Slot().AutoHeight()[SNew(SHorizontalBox)
    +SHorizontalBox::Slot().AutoWidth().Padding(0,0,10,0)[SNew(SButton).Text(FText::FromString(TEXT("Open page"))).IsEnabled_Lambda([Weak](){return Weak.IsValid()&&!Weak->AddressPending;}).OnClicked_Lambda([Weak](){if(Weak.IsValid())Weak->SubmitPhoneAddress();return FReply::Handled();})]
    +SHorizontalBox::Slot().AutoWidth()[SNew(SButton).Text(FText::FromString(TEXT("Close"))).OnClicked_Lambda([Weak](){if(Weak.IsValid())Weak->ClosePhoneAddress(false);return FReply::Handled();})]]
 ]]];
 GEngine->GameViewport->AddViewportWidgetContent(AddressWidget.ToSharedRef(),100);
 if(APlayerController* Player=GetWorld()?GetWorld()->GetFirstPlayerController():nullptr){FInputModeUIOnly Mode;Mode.SetWidgetToFocus(AddressBox);Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);Player->SetInputMode(Mode);Player->SetShowMouseCursor(true);}
 return true;
}
void USub01HomeDeviceBridge::SubmitPhoneAddress(){
 if(!AddressOpen||AddressPending||!AddressBox.IsValid()||Private||LocalPrivacy||FocusedDevice!=TEXT("phone")||PhoneApp!=TEXT("browser")||PhoneFrameId.IsEmpty())return;
 AddressDraft=AddressBox->GetText().ToString().TrimStartAndEnd();
 if(AddressDraft.IsEmpty()||AddressDraft.Len()>2048||!AddressDraft.StartsWith(TEXT("https://"),ESearchCase::IgnoreCase)){if(AddressStatus.IsValid())AddressStatus->SetText(FText::FromString(TEXT("Enter a public HTTPS address (up to 2048 characters).")));return;}
 auto Body=MakeShared<FJsonObject>();Body->SetStringField(TEXT("action"),TEXT("navigate"));Body->SetStringField(TEXT("url"),AddressDraft);Body->SetStringField(TEXT("frame_id"),PhoneFrameId);
 AddressPending=true;const uint64 Request=++AddressRequest;if(AddressStatus.IsValid())AddressStatus->SetText(FText::FromString(TEXT("Opening the page...")));
 Action(TEXT("phone"),Body,[this,Request](int32 Code,const FString& Reply){
  if(!AddressOpen||!AddressPending||Request!=AddressRequest||Private||LocalPrivacy||FocusedDevice!=TEXT("phone"))return;
  AddressPending=false;TSharedPtr<FJsonObject> Json;bool Ok=false;
  if(Code==200&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Reply),Json)&&Json.IsValid())Json->TryGetBoolField(TEXT("ok"),Ok);
  if(Code==200&&Ok){ClosePhoneAddress(false);return;}
  if(AddressStatus.IsValid())AddressStatus->SetText(FText::FromString(Code==409?TEXT("The phone changed or the page is unavailable. Your address is kept; try again."):TEXT("The page did not open. Your address is kept; try again.")));
 });
}
void USub01HomeDeviceBridge::ClosePhoneAddress(bool Discard){
 if(!Discard&&AddressBox.IsValid())AddressDraft=AddressBox->GetText().ToString();
 if(Discard)AddressDraft.Empty();AddressOpen=false;AddressPending=false;++AddressRequest;
 const bool Shown=AddressWidget.IsValid();
 if(Shown&&GEngine&&GEngine->GameViewport)GEngine->GameViewport->RemoveViewportWidgetContent(AddressWidget.ToSharedRef());
 AddressWidget.Reset();AddressBox.Reset();AddressStatus.Reset();
 if(Shown)if(APlayerController* Player=GetWorld()?GetWorld()->GetFirstPlayerController():nullptr){Player->SetInputMode(FInputModeGameOnly());Player->SetShowMouseCursor(false);}
}
