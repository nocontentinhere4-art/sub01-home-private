"""Manual real gamepad intent for actual focused Minecraft; no home/PC keys.
Independent of the unaccepted held-controller/sofa/autonomous gameplay gates.
"""
FIELDS=r'''
 TMap<FString,bool> MinecraftKeyboardKeys,MinecraftPadKeys;
 FString MinecraftPadProducer;
 double MinecraftPadSequence=0;
 bool MinecraftPadActive=false,MinecraftPadMine=false,MinecraftPadPlace=false;
 void ApplyManualMinecraftGamepad();
 void ReleaseManualMinecraftGamepad();
 void MergeManualMinecraftKeys();
'''
METHODS=r'''
#include <unistd.h>
void ASub01HomeCharacter::MergeManualMinecraftKeys(){
 for(const TCHAR* K:{TEXT("forward"),TEXT("back"),TEXT("left"),TEXT("right"),TEXT("jump"),TEXT("sneak"),TEXT("sprint")})MinecraftKeys.Add(K,MinecraftKeyboardKeys.FindRef(K)||MinecraftPadKeys.FindRef(K));
}
void ASub01HomeCharacter::ReleaseManualMinecraftGamepad(){
 if(!MinecraftPadActive)return;const bool Mining=MinecraftPadMine;MinecraftPadActive=false;MinecraftPadMine=false;MinecraftPadPlace=false;MinecraftPadKeys.Empty();MergeManualMinecraftKeys();
 if(Mining)SendMinecraftTVInput(TEXT("cancel"));
}
void ASub01HomeCharacter::ApplyManualMinecraftGamepad(){
 if(!MinecraftFocused||PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||RouteActive||HandsDiagnosticSeat){ReleaseManualMinecraftGamepad();return;}
 const char* Path="/home/unreal/.sub01-private/native-tv-gamepad-input.json";struct stat Info;
 if(lstat(Path,&Info)!=0||!S_ISREG(Info.st_mode)||Info.st_uid!=getuid()||(Info.st_mode&0077)||Info.st_size<=0||Info.st_size>2048){ReleaseManualMinecraftGamepad();return;}
 FString Raw;if(!FFileHelper::LoadFileToString(Raw,UTF8_TO_TCHAR(Path))){ReleaseManualMinecraftGamepad();return;}
 TSharedPtr<FJsonObject> J;if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),J)||!J.IsValid()){ReleaseManualMinecraftGamepad();return;}
 double Stamp=0,Pid=0,Ticks=0,Sequence=0;FString Schema,Consumer,Event,Frame,Producer;const TArray<TSharedPtr<FJsonValue>>* Axes=nullptr;const TSharedPtr<FJsonObject>* Buttons=nullptr;
 const FDateTime Now=FDateTime::UtcNow();const double UTC=Now.ToUnixTimestamp()+Now.GetMillisecond()/1000.0;
 if(!J->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("sub01.manual-minecraft-gamepad.v1")||!J->TryGetNumberField(TEXT("captured_utc"),Stamp)||!FMath::IsFinite(Stamp)||UTC-Stamp<-.05||UTC-Stamp>.25||!J->TryGetNumberField(TEXT("native_pid"),Pid)||Pid!=FPlatformProcess::GetCurrentProcessId()||!J->TryGetNumberField(TEXT("native_start_ticks"),Ticks)||Ticks!=MinecraftStartTicks||!J->TryGetStringField(TEXT("consumer_id"),Consumer)||Consumer!=MinecraftConsumerId||!J->TryGetStringField(TEXT("focus_event_id"),Event)||Event!=MinecraftFocusEvent||!J->TryGetStringField(TEXT("frame_id"),Frame)||Frame!=MinecraftFrame||!J->TryGetStringField(TEXT("producer_session"),Producer)||Producer.Len()!=32||!J->TryGetNumberField(TEXT("sequence"),Sequence)||!FMath::IsFinite(Sequence)||Sequence<1||Sequence>=9007199254740992.0||Sequence!=double(uint64(Sequence))||!J->TryGetArrayField(TEXT("axes"),Axes)||Axes->Num()!=4||!J->TryGetObjectField(TEXT("buttons"),Buttons)){ReleaseManualMinecraftGamepad();return;}
 if(Producer==MinecraftPadProducer&&Sequence<MinecraftPadSequence){ReleaseManualMinecraftGamepad();return;}
 double A[4];for(int32 I=0;I<4;++I)if(!(*Axes)[I]->TryGetNumber(A[I])||!FMath::IsFinite(A[I])||FMath::Abs(A[I])>1){ReleaseManualMinecraftGamepad();return;}
 bool Jump=false,Sneak=false,Sprint=false,Mine=false,Place=false;
 if(!(*Buttons)->TryGetBoolField(TEXT("jump"),Jump)||!(*Buttons)->TryGetBoolField(TEXT("sneak"),Sneak)||!(*Buttons)->TryGetBoolField(TEXT("sprint"),Sprint)||!(*Buttons)->TryGetBoolField(TEXT("mine"),Mine)||!(*Buttons)->TryGetBoolField(TEXT("place"),Place)){ReleaseManualMinecraftGamepad();return;}
 MinecraftPadProducer=Producer;MinecraftPadSequence=Sequence;MinecraftPadActive=true;
 MinecraftPadKeys.Add(TEXT("left"),A[0]<-.2);MinecraftPadKeys.Add(TEXT("right"),A[0]>.2);MinecraftPadKeys.Add(TEXT("forward"),A[1]<-.2);MinecraftPadKeys.Add(TEXT("back"),A[1]>.2);MinecraftPadKeys.Add(TEXT("jump"),Jump);MinecraftPadKeys.Add(TEXT("sneak"),Sneak);MinecraftPadKeys.Add(TEXT("sprint"),Sprint);MergeManualMinecraftKeys();
 auto Dead=[](double V){return FMath::Abs(V)<=.15?0.0:FMath::Sign(V)*(FMath::Abs(V)-.15)/.85;};MinecraftLook.X=FMath::Clamp(MinecraftLook.X-float(Dead(A[2])*.12),-.35f,.35f);MinecraftLook.Y=FMath::Clamp(MinecraftLook.Y-float(Dead(A[3])*.08),-.35f,.35f);
 if(Mine&&!MinecraftPadMine)SendMinecraftTVInput(TEXT("mine"));if(!Mine&&MinecraftPadMine)SendMinecraftTVInput(TEXT("cancel"));if(Place&&!MinecraftPadPlace)SendMinecraftTVInput(TEXT("place"));MinecraftPadMine=Mine;MinecraftPadPlace=Place;
}
'''
def install(header,cpp):
 if 'ApplyManualMinecraftGamepad'in cpp:raise ValueError('Manual realgamepad adapter alreadyinstalled')
 if header.count(' void TickMinecraftTVInput();')!=1:raise ValueError('Actual Minecraft TV consumer required')
 header=header.replace(' void TickMinecraftTVInput();',' void TickMinecraftTVInput();'+FIELDS,1)
 hooks={
 'A->MinecraftKeys.Add(K,true);':'A->MinecraftKeyboardKeys.Add(K,true);A->MinecraftKeys.Add(K,true);',
 'A->MinecraftKeys.Add(K,false);':'A->MinecraftKeyboardKeys.Add(K,false);A->MinecraftKeys.Add(K,A->MinecraftPadKeys.FindRef(K));',
 'MinecraftLastSend=Now;SendMinecraftTVInput(TEXT("focus"));':'MinecraftLastSend=Now;ApplyManualMinecraftGamepad();SendMinecraftTVInput(TEXT("focus"));',
 'void ASub01HomeCharacter::ReleaseMinecraftTVInput(){':'void ASub01HomeCharacter::ReleaseMinecraftTVInput(){\n ReleaseManualMinecraftGamepad();MinecraftKeyboardKeys.Empty();',
 }
 for before,after in hooks.items():
  if cpp.count(before)!=1:raise ValueError('Actualunique Minecraft consumer hookrequired '+before)
  cpp=cpp.replace(before,after,1)
 return header,cpp+'\n'+METHODS
