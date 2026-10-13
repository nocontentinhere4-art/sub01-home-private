#include "Sub01HomeDeviceBridge.h"
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
class FSub01DeviceInput:public IInputProcessor{
 TWeakObjectPtr<USub01HomeDeviceBridge> Bridge;bool Up=false,Down=false;
public:
 explicit FSub01DeviceInput(USub01HomeDeviceBridge* B):Bridge(B){}
 void Tick(const float,FSlateApplication&,TSharedRef<ICursor>)override{if(!Bridge.IsValid()||Bridge->GetFocusedDevice().IsNone()){Up=Down=false;}}
 bool HandleKeyDownEvent(FSlateApplication&,const FKeyEvent& Event)override{
  auto* B=Bridge.Get();if(!B||B->GetFocusedDevice().IsNone())return false;const FKey K=Event.GetKey();
  if(K==EKeys::Escape){B->ReleaseFocus();return true;}
  if(B->GetFocusedDevice()==TEXT("phone")){
   if(K==EKeys::Up)B->PhoneAction(TEXT("scroll_up"));if(K==EKeys::Down)B->PhoneAction(TEXT("scroll_down"));if(K==EKeys::BackSpace)B->PhoneAction(TEXT("back"));if(K==EKeys::Enter)B->PhoneAction(TEXT("close_notice"));
  }else{
   if(K==EKeys::Up)Up=true;if(K==EKeys::Down)Down=true;B->SetPongDirection(float(Down)-float(Up));
   if(K==EKeys::One)B->TVGame(TEXT("pong"));if(K==EKeys::Two)B->TVGame(TEXT("chess"));if(K==EKeys::Three)B->TVGame(TEXT("minecraft"));
  }return true;
 }
 bool HandleKeyUpEvent(FSlateApplication&,const FKeyEvent& Event)override{auto* B=Bridge.Get();if(!B||B->GetFocusedDevice().IsNone())return false;if(Event.GetKey()==EKeys::Up)Up=false;if(Event.GetKey()==EKeys::Down)Down=false;B->SetPongDirection(float(Down)-float(Up));return true;}
 bool HandleMouseMoveEvent(FSlateApplication&,const FPointerEvent&)override{return Bridge.IsValid()&&!Bridge->GetFocusedDevice().IsNone();}
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
void USub01HomeDeviceBridge::Clear(){++Generation;Private=true;Busy=false;FocusedDevice=NAME_None;PongDirection=0;PongState.Reset();PhoneFrameId.Empty();Images.Empty();ImageIdentity.Empty();FramePending.Empty();for(auto& Pair:Materials)if(Pair.Value)Pair.Value->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);}
void USub01HomeDeviceBridge::SetLocalPrivacy(bool Hidden){if(Hidden==LocalPrivacy)return;LocalPrivacy=Hidden;if(Hidden)Clear();}
bool USub01HomeDeviceBridge::FocusHit(UActorComponent* Component){if(Private||LocalPrivacy)return false;for(auto& Pair:Screens)if(Pair.Key==Component){FocusedDevice=Pair.Value;return true;}return false;}
void USub01HomeDeviceBridge::ReleaseFocus(){if(FocusedDevice==TEXT("tv")&&!Private&&!LocalPrivacy){auto B=MakeShared<FJsonObject>();B->SetNumberField(TEXT("direction"),0);Action(TEXT("tv"),B);}FocusedDevice=NAME_None;PongDirection=0;}
void USub01HomeDeviceBridge::ReadHome(TFunction<void(TSharedPtr<FJsonObject>)> Done){
 auto Callback=MakeShared<TFunction<void(TSharedPtr<FJsonObject>)>>(MoveTemp(Done));auto R=FHttpModule::Get().CreateRequest();R->SetURL(Origin+TEXT("/devices/state"));R->SetVerb(TEXT("GET"));R->SetTimeout(3);R->SetHeader(TEXT("X-Admin-Token"),Token);
 R->OnProcessRequestComplete().BindWeakLambda(this,[Callback](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){TSharedPtr<FJsonObject> State;if(OK&&Response&&Response->GetResponseCode()==200){auto Reader=TJsonReaderFactory<>::Create(Response->GetContentAsString());FJsonSerializer::Deserialize(Reader,State);}(*Callback)(State);});if(!R->ProcessRequest())(*Callback)(nullptr);
}
bool USub01HomeDeviceBridge::PublicHome(const TSharedPtr<FJsonObject>& State)const{const TSharedPtr<FJsonObject>* Home=nullptr;bool Hidden=true;return !LocalPrivacy&&State&&State->TryGetObjectField(TEXT("home"),Home)&&Home&&(*Home)->TryGetBoolField(TEXT("privacy"),Hidden)&&!Hidden;}
void USub01HomeDeviceBridge::Poll(){
 if(LocalPrivacy||Busy||Token.IsEmpty())return;Busy=true;const uint64 Epoch=Generation;
 ReadHome([this,Epoch](TSharedPtr<FJsonObject> State){if(Epoch!=Generation)return;Busy=false;if(!PublicHome(State)){Clear();return;}Private=false;
  const TSharedPtr<FJsonObject>* Phone=nullptr;FString Identity;if(State->TryGetObjectField(TEXT("phone_browser_screen"),Phone)&&Phone&&(*Phone)->TryGetStringField(TEXT("frame_id"),Identity)&&!Identity.IsEmpty())FetchFrame(TEXT("phone"),Identity,Epoch);
  else if(Materials.Contains(TEXT("phone"))){Materials[TEXT("phone")]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);Images.Remove(TEXT("phone"));ImageIdentity.Remove(TEXT("phone"));PhoneFrameId.Empty();}
  const TSharedPtr<FJsonObject>* Home=nullptr;State->TryGetObjectField(TEXT("home"),Home);FString Game;(*Home)->TryGetStringField(TEXT("console_game"),Game);
  if(Game==TEXT("minecraft"))FetchFrame(TEXT("tv"),TEXT(""),Epoch);
  else if(Game==TEXT("pong")){const TSharedPtr<FJsonObject>* Pong=nullptr;if((*Home)->TryGetObjectField(TEXT("pong"),Pong)&&Pong){PongState=*Pong;if(TVCanvas){TVCanvas->UpdateResource();if(Materials.Contains(TEXT("tv")))Materials[TEXT("tv")]->SetTextureParameterValue(TEXT("PCFrame"),TVCanvas);}}}
  else if(Materials.Contains(TEXT("tv")))Materials[TEXT("tv")]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);
  if(FocusedDevice==TEXT("tv")&&Game==TEXT("pong")){auto Body=MakeShared<FJsonObject>();Body->SetNumberField(TEXT("direction"),PongDirection);Action(TEXT("tv"),Body);}
 });
}
void USub01HomeDeviceBridge::FetchFrame(FName Device,const FString& Identity,uint64 Epoch){
 if(!Materials.Contains(Device)||LocalPrivacy||FramePending.Contains(Device))return;
 if(Device==TEXT("phone")&&Images.Contains(Device)&&ImageIdentity.FindRef(Device)==Identity)return;FramePending.Add(Device);auto R=FHttpModule::Get().CreateRequest();R->SetURL(Origin+TEXT("/devices/")+Device.ToString()+TEXT("/frame.jpg")+(Identity.IsEmpty()?TEXT(""):TEXT("?frame_id=")+Identity));R->SetVerb(TEXT("GET"));R->SetTimeout(3);R->SetHeader(TEXT("X-Admin-Token"),Token);
 R->OnProcessRequestComplete().BindWeakLambda(this,[this,Device,Identity,Epoch](FHttpRequestPtr,FHttpResponsePtr Response,bool OK){if(Epoch!=Generation)return;if(!OK||!Response||Response->GetResponseCode()!=200){FramePending.Remove(Device);if(Materials.Contains(Device))Materials[Device]->SetTextureParameterValue(TEXT("PCFrame"),BlankCanvas);Images.Remove(Device);ImageIdentity.Remove(Device);return;}const FString Tag=Response->GetHeader(TEXT("ETag"));const TArray<uint8> Pixels=Response->GetContent();if(Pixels.Num()>6*1024*1024){FramePending.Remove(Device);return;}
  ReadHome([this,Device,Identity,Epoch,Pixels,Tag](TSharedPtr<FJsonObject> After){if(Epoch!=Generation)return;FramePending.Remove(Device);if(!PublicHome(After)){Clear();return;}const TSharedPtr<FJsonObject>* Current=nullptr;FString Id;
   if(Device==TEXT("phone")&&(!After->TryGetObjectField(TEXT("phone_browser_screen"),Current)||!Current||!(*Current)->TryGetStringField(TEXT("frame_id"),Id)||Id!=Identity))return;
   if(Device==TEXT("tv")){const TSharedPtr<FJsonObject>* Home=nullptr;FString Game;if(!After->TryGetObjectField(TEXT("home"),Home)||!Home||!(*Home)->TryGetStringField(TEXT("console_game"),Game)||Game!=TEXT("minecraft"))return;}
   const FString CurrentIdentity=Device==TEXT("phone")?Identity:Tag;
   if(!CurrentIdentity.IsEmpty()&&Images.Contains(Device)&&ImageIdentity.FindRef(Device)==CurrentIdentity){if(Materials.Contains(Device))Materials[Device]->SetTextureParameterValue(TEXT("PCFrame"),Images[Device]);return;}
   auto* Texture=FImageUtils::ImportBufferAsTexture2D(Pixels);if(!Texture||Texture->GetSizeX()>2048||Texture->GetSizeY()>2048)return;Texture->SRGB=true;Texture->UpdateResource();Images.Add(Device,Texture);ImageIdentity.Add(Device,CurrentIdentity);if(Materials.Contains(Device))Materials[Device]->SetTextureParameterValue(TEXT("PCFrame"),Texture);if(Device==TEXT("phone"))PhoneFrameId=Identity;
  });});if(!R->ProcessRequest())FramePending.Remove(Device);
}
void USub01HomeDeviceBridge::Action(FName Device,const TSharedPtr<FJsonObject>& Body){if(Private||LocalPrivacy||Token.IsEmpty())return;const uint64 Epoch=Generation;
 ReadHome([this,Device,Body,Epoch](TSharedPtr<FJsonObject> Before){if(Epoch!=Generation)return;if(!PublicHome(Before)){Clear();return;}FString Data;auto Writer=TJsonWriterFactory<>::Create(&Data);FJsonSerializer::Serialize(Body.ToSharedRef(),Writer);auto R=FHttpModule::Get().CreateRequest();R->SetURL(Origin+TEXT("/devices/")+Device.ToString()+TEXT("/action"));R->SetVerb(TEXT("POST"));R->SetTimeout(3);R->SetHeader(TEXT("Content-Type"),TEXT("application/json"));R->SetHeader(TEXT("X-Admin-Token"),Token);R->SetContentAsString(Data);// The existing 150 ms poll refreshes state. Calling Poll from this reply
   // recursively re-sends held Pong input faster than the backend rate limit.
   R->ProcessRequest();});
}
void USub01HomeDeviceBridge::PhoneAction(const FString& ActionName){if(PhoneFrameId.IsEmpty())return;auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("action"),ActionName);B->SetStringField(TEXT("frame_id"),PhoneFrameId);Action(TEXT("phone"),B);}
void USub01HomeDeviceBridge::PhoneNavigate(const FString& URL){if(URL.IsEmpty()||URL.Len()>2048||!URL.StartsWith(TEXT("https://"),ESearchCase::IgnoreCase))return;auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("action"),TEXT("navigate"));B->SetStringField(TEXT("url"),URL);if(!PhoneFrameId.IsEmpty())B->SetStringField(TEXT("frame_id"),PhoneFrameId);Action(TEXT("phone"),B);}
void USub01HomeDeviceBridge::TVGame(const FString& Game){auto B=MakeShared<FJsonObject>();B->SetStringField(TEXT("game"),Game);Action(TEXT("tv"),B);}
void USub01HomeDeviceBridge::DrawTV(UCanvas* Canvas,int32 Width,int32 Height){if(!Canvas||Private||LocalPrivacy||!PongState)return;const TArray<TSharedPtr<FJsonValue>> *Paddles=nullptr,*Ball=nullptr,*Score=nullptr;if(!PongState->TryGetArrayField(TEXT("paddles"),Paddles)||!PongState->TryGetArrayField(TEXT("ball"),Ball)||!PongState->TryGetArrayField(TEXT("score"),Score)||Paddles->Num()!=2||Ball->Num()!=2||Score->Num()!=2)return;
 Canvas->SetDrawColor(FColor(217,232,217));Canvas->K2_DrawBox(FVector2D(.04f*Width,(*Paddles)[0]->AsNumber()*Height-.1f*Height),FVector2D(8,.2f*Height),4,FLinearColor(FColor(217,232,217)));Canvas->K2_DrawBox(FVector2D(.95f*Width,(*Paddles)[1]->AsNumber()*Height-.1f*Height),FVector2D(8,.2f*Height),4,FLinearColor(FColor(217,232,217)));Canvas->K2_DrawBox(FVector2D((*Ball)[0]->AsNumber()*Width-4,(*Ball)[1]->AsNumber()*Height-4),FVector2D(8,8),4,FLinearColor(FColor(217,232,217)));if(GEngine)Canvas->DrawText(GEngine->GetSmallFont(),FString::Printf(TEXT("%d : %d"),int32((*Score)[0]->AsNumber()),int32((*Score)[1]->AsNumber())),Width*.44f,24,2,2);
}
