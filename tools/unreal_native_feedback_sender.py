"""Actual native-to-private-backend feedback; physical seat verification remains external."""

FIELDS = r'''
 void UpdateNativeFeedback();
 const TCHAR* NativeFeedbackPhase() const;
 int64 LiveHomeCommandSequence=-1,NativeFeedbackSequence=-1;
 FString NativeFeedbackEpoch,NativeFeedbackActivity;
 bool NativeFeedbackBound=false,NativeFeedbackPending=false;
 double NativeFeedbackAt=0;
'''

METHODS = r'''
const TCHAR* ASub01HomeCharacter::NativeFeedbackPhase() const{
 if(LiveHomeBlocked)return TEXT("blocked");
 if(!NativeFeedbackBound||LiveHomePath.Num()||LiveHomeNode!=LiveHomeTarget)return TEXT("walking");
 if(NativeSeatVerified&&(LiveHomeNode==TEXT("desk")||LiveHomeNode==TEXT("sofa")||LiveHomeNode==TEXT("bed")))return TEXT("seated");
 return TEXT("arrived");
}
void ASub01HomeCharacter::UpdateNativeFeedback(){
 const double Now=FPlatformTime::Seconds();
 if(!LiveHome||!LiveHomeFresh||LiveHomePrivate||LiveHomeEpoch.IsEmpty()||LiveHomeCommandSequence<0||Now<LiveHomeLastReceived||Now-LiveHomeLastReceived>3)return;
 if(NativeFeedbackEpoch!=LiveHomeEpoch||NativeFeedbackSequence!=LiveHomeCommandSequence||NativeFeedbackActivity!=LiveHomeActivity){
  NativeFeedbackEpoch=LiveHomeEpoch;NativeFeedbackSequence=LiveHomeCommandSequence;NativeFeedbackActivity=LiveHomeActivity;NativeFeedbackBound=false;
 }
 if(NativeFeedbackPending||Now<NativeFeedbackAt)return;
 NativeFeedbackAt=Now+.5;NativeFeedbackPending=true;
 const FString Epoch=LiveHomeEpoch,Activity=LiveHomeActivity;const int64 Sequence=LiveHomeCommandSequence;const bool Bind=!NativeFeedbackBound;
 auto Doc=MakeShared<FJsonObject>();Doc->SetStringField(TEXT("epoch"),Epoch);Doc->SetNumberField(TEXT("sequence"),Sequence);
 Doc->SetStringField(TEXT("activity"),Activity);Doc->SetStringField(TEXT("node"),LiveHomeNode);
 // Binding is always walking, including when the pawn is already at its target.
 const FString Phase=Bind?TEXT("walking"):NativeFeedbackPhase();Doc->SetStringField(TEXT("phase"),Phase);Doc->SetBoolField(TEXT("bind"),Bind);
 if(Phase==TEXT("seated"))Doc->SetStringField(TEXT("chair"),LiveHomeNode==TEXT("desk")?TEXT("desk_chair"):LiveHomeNode);
 FString Body;FJsonSerializer::Serialize(Doc,TJsonWriterFactory<>::Create(&Body));
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(LiveHomeOrigin+TEXT("/home/native_state"));Request->SetVerb(TEXT("POST"));
 Request->SetTimeout(1.5);Request->SetHeader(TEXT("X-Admin-Token"),LiveHomeToken);Request->SetHeader(TEXT("Content-Type"),TEXT("application/json"));Request->SetContentAsString(Body);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this,Epoch,Sequence,Activity](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){
  NativeFeedbackPending=false;
  if(!LiveHome||LiveHomeEpoch!=Epoch||LiveHomeCommandSequence!=Sequence||LiveHomeActivity!=Activity)return;
  const double Age=FPlatformTime::Seconds()-LiveHomeLastReceived;
  if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200||!LiveHomeFresh||LiveHomePrivate||Age<0||Age>3){
   NativeFeedbackBound=false;NativeSeatVerified=false;if(PCBridge)PCBridge->SetOperatorFocus(false);return;
  }
  NativeFeedbackBound=true;
 });
 if(!Request->ProcessRequest()){NativeFeedbackPending=false;NativeFeedbackBound=false;NativeSeatVerified=false;if(PCBridge)PCBridge->SetOperatorFocus(false);}
}
'''
