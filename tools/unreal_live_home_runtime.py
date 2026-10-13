"""Opt-in native consumer of the verified private HomeState bridge.

Physical movement is bounded CharacterMovement input. The source graph is
serialized at staging time; neither camera coordinates nor backend positions
are assigned to the pawn. This does not assert seated/phone animation readiness.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from home_world import NODES, EDGES
try:
    from .unreal_native_feedback_sender import FIELDS as FEEDBACK_FIELDS, METHODS as FEEDBACK_METHODS
except ImportError:  # runtime staging imports tools directly
    from unreal_native_feedback_sender import FIELDS as FEEDBACK_FIELDS, METHODS as FEEDBACK_METHODS

FIELDS=r'''
 void BeginLiveHome(); void UpdateLiveHome(float Dt); void PollLiveHome();
 void PlanLiveHome(const FString& Target); void ApplyLiveHome(const TSharedPtr<FJsonObject>& Doc);
 bool LiveHome=false,LiveHomeFresh=false,LiveHomePrivate=false,LiveHomePending=false,LiveHomeBlocked=false,LiveHomeBindWaiting=false,NativeSeatVerified=false;
 FString LiveHomeOrigin,LiveHomeToken,LiveHomeNode=TEXT("door"),LiveHomeTarget,LiveHomeEpoch;
 FString LiveHomeActivity; TArray<FString> LiveHomePath;
 double LiveHomePollAt=0,LiveHomeLastReceived=0,LiveHomeProgressAt=0;
 float LiveHomeBest=BIG_NUMBER;
 TMap<FString,FVector> LiveHomeNodes;TMap<FString,TArray<FString>> LiveHomeEdges;
'''
METHODS=r'''
#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"
#include "Camera/PlayerCameraManager.h"
#include <cmath>
void ASub01HomeCharacter::BeginLiveHome(){
 if(!FParse::Param(FCommandLine::Get(),TEXT("Sub01LiveHome")))return;
 if(HandsDiagnosticSeat||RouteActive){UE_LOG(LogTemp,Error,TEXT("SUB01_LIVE_HOME_REFUSED controlled pose/route diagnostic active"));return;}
 if(PCBridge)PCBridge->SetOperatorFocus(false);NativeSeatVerified=false;
 LiveHomeOrigin=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_HOME_ORIGIN"));
 if(LiveHomeOrigin!=TEXT("http://127.0.0.1:8821")){UE_LOG(LogTemp,Error,TEXT("SUB01_LIVE_HOME_REFUSED validated loopback bridge required"));return;}
 LiveHomeToken=FPlatformMisc::GetEnvironmentVariable(TEXT("SUB01_ADMIN_TOKEN"));if(LiveHomeToken.IsEmpty())return;
 const FVector Actual=GetActorLocation();const FFindFloorResult& Contact=GetCharacterMovement()->CurrentFloor;
 if(!GetCharacterMovement()->IsMovingOnGround()||!Contact.bBlockingHit){LiveHomeBindWaiting=true;return;}
 LiveHomeBindWaiting=false;LiveHomeNodes.Empty();LiveHomeEdges.Empty();
 //@@SOURCE_GRAPH@@
 float Best=BIG_NUMBER;FString StartNode;
 for(const auto& Node:LiveHomeNodes){const float XY=FVector2D(Actual.X-Node.Value.X,Actual.Y-Node.Value.Y).Size();const float Z=FMath::Abs(Contact.HitResult.ImpactPoint.Z-Node.Value.Z);if(XY<20&&Z<20&&XY+Z<Best){Best=XY+Z;StartNode=Node.Key;}}
 if(StartNode.IsEmpty()){UE_LOG(LogTemp,Error,TEXT("SUB01_LIVE_HOME_REFUSED actual pawn not at verified graph node; no position reset"));return;}
 LiveHomeNode=StartNode;LiveHomePath.Empty();LiveHomeTarget.Empty();LiveHomeEpoch.Empty();
 LiveHome=true;LiveHomeProgressAt=FPlatformTime::Seconds();PollLiveHome();
 UE_LOG(LogTemp,Display,TEXT("SUB01_LIVE_HOME_BOUND real bridge; native physical graph movement only; seated actions not accepted"));
}
void ASub01HomeCharacter::PollLiveHome(){
 if(!LiveHome||LiveHomePending)return;LiveHomePending=true;LiveHomePollAt=FPlatformTime::Seconds()+.5;
 auto Request=FHttpModule::Get().CreateRequest();Request->SetURL(LiveHomeOrigin+TEXT("/home/state"));Request->SetVerb(TEXT("GET"));Request->SetTimeout(3);Request->SetHeader(TEXT("X-Admin-Token"),LiveHomeToken);
 Request->OnProcessRequestComplete().BindWeakLambda(this,[this](FHttpRequestPtr,FHttpResponsePtr Response,bool Ok){
  LiveHomePending=false;if(!LiveHome)return;TSharedPtr<FJsonObject> Doc;
  if(!Ok||!Response.IsValid()||Response->GetResponseCode()!=200||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Response->GetContentAsString()),Doc)){LiveHomeFresh=false;return;}ApplyLiveHome(Doc);
 });Request->ProcessRequest();
}
void ASub01HomeCharacter::PlanLiveHome(const FString& Target){
 if(!LiveHomeNodes.Contains(Target)){LiveHomeFresh=false;return;}
 // Replan from our next actually traversed edge endpoint, not the backend's
 // already-ahead node. Finish that physical edge before following the new path.
 const FString Start=LiveHomePath.Num()?LiveHomePath[0]:LiveHomeNode;
 TArray<FString> Open;Open.Add(Start);TMap<FString,FString> Previous;Previous.Add(Start,TEXT(""));TMap<FString,double> Costs;Costs.Add(Start,0);
 while(Open.Num()){
  int32 Best=0;for(int32 I=1;I<Open.Num();++I)if(Costs.FindChecked(Open[I])<Costs.FindChecked(Open[Best]))Best=I;
  const FString Current=Open[Best];Open.RemoveAt(Best);if(Current==Target)break;
  for(const FString& Next:LiveHomeEdges.FindChecked(Current)){const double Cost=Costs.FindChecked(Current)+FVector::Dist(LiveHomeNodes.FindChecked(Current),LiveHomeNodes.FindChecked(Next));const double* Known=Costs.Find(Next);if(!Known||Cost<*Known){Costs.Add(Next,Cost);Previous.Add(Next,Current);Open.AddUnique(Next);}}
 }
 if(!Previous.Contains(Target)){LiveHomeFresh=false;return;}TArray<FString> Path;FString Node=Target;
 while(Node!=Start){Path.Insert(Node,0);Node=Previous.FindChecked(Node);}if(Start!=LiveHomeNode)Path.Insert(Start,0);
 NativeSeatVerified=false;if(PCBridge)PCBridge->SetOperatorFocus(false);
 LiveHomePath=MoveTemp(Path);LiveHomeTarget=Target;LiveHomeBlocked=false;LiveHomeBest=BIG_NUMBER;LiveHomeProgressAt=FPlatformTime::Seconds();
 UE_LOG(LogTemp,Display,TEXT("SUB01_LIVE_HOME_ROUTE actualNode=%s target=%s remaining=%d"),*LiveHomeNode,*Target,LiveHomePath.Num());
}
void ASub01HomeCharacter::ApplyLiveHome(const TSharedPtr<FJsonObject>& Doc){
 FString Schema;if(!Doc.IsValid()||!Doc->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("sub01.home-state.v1")){LiveHomeFresh=false;return;}
 const TSharedPtr<FJsonObject>* Source=nullptr;FString Status;
 if(!Doc->TryGetObjectField(TEXT("source"),Source)||!(*Source)->TryGetStringField(TEXT("status"),Status)||Status!=TEXT("live")){LiveHomeFresh=false;return;}
 const TSharedPtr<FJsonObject>* Coordinates=nullptr;FString Units,Height;
 if(!Doc->TryGetObjectField(TEXT("coordinates"),Coordinates)||!(*Coordinates)->TryGetStringField(TEXT("units"),Units)||Units!=TEXT("cm")||!(*Coordinates)->TryGetStringField(TEXT("waypoint_height"),Height)||Height!=TEXT("floor")){LiveHomeFresh=false;return;}
 bool Private=false;if(!Doc->TryGetBoolField(TEXT("privacy"),Private)){LiveHomeFresh=false;return;}
 if(Private){LiveHomeFresh=true;LiveHomeLastReceived=FPlatformTime::Seconds();LiveHomePrivate=true;if(PCBridge)PCBridge->SetLocalPrivacy(true);LiveHomeActivity.Empty();return;}
 const TSharedPtr<FJsonObject>* Actor=nullptr;FString Target;
 if(!Doc->TryGetObjectField(TEXT("actor"),Actor)||!(*Actor)->TryGetStringField(TEXT("target"),Target)||!LiveHomeNodes.Contains(Target)){LiveHomeFresh=false;return;}
 double Sequence=-1;if(!(*Actor)->TryGetNumberField(TEXT("route_sequence"),Sequence)||!FMath::IsFinite(Sequence)||Sequence<0||Sequence>9007199254740991.0||std::floor(Sequence)!=Sequence){LiveHomeFresh=false;return;}LiveHomeCommandSequence=static_cast<int64>(Sequence);
 LiveHomeFresh=true;LiveHomeLastReceived=FPlatformTime::Seconds();LiveHomePrivate=false;
 const TSharedPtr<FJsonObject>* Brain=nullptr;if(Doc->TryGetObjectField(TEXT("brain"),Brain))(*Brain)->TryGetStringField(TEXT("activity"),LiveHomeActivity);
 FString Epoch;Doc->TryGetStringField(TEXT("epoch"),Epoch);if(Target!=LiveHomeTarget||Epoch!=LiveHomeEpoch){LiveHomeEpoch=Epoch;PlanLiveHome(Target);}
}
void ASub01HomeCharacter::UpdateLiveHome(float Dt){
 if(!LiveHome){if(LiveHomeBindWaiting)BeginLiveHome();return;}const double Now=FPlatformTime::Seconds();if(Now>=LiveHomePollAt)PollLiveHome();
 UpdateNativeFeedback();
 if(!LiveHomeFresh||Now-LiveHomeLastReceived>3||LiveHomePrivate||LiveHomeBlocked){GetCharacterMovement()->StopMovementImmediately();if(PCBridge)PCBridge->SetOperatorFocus(false);NativeSeatVerified=false;if(!LiveHomeBlocked){LiveHomeProgressAt=Now;LiveHomeBest=BIG_NUMBER;}return;}
 if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(NativeSeatVerified&&NativeFeedbackSeatReady()&&LiveHomeNode==TEXT("desk")&&(LiveHomeActivity==TEXT("use_computer")||LiveHomeActivity==TEXT("research")||LiveHomeActivity==TEXT("chart")));return;}
 if(PCBridge)PCBridge->SetOperatorFocus(false);
 const FString Next=LiveHomePath[0];const FVector Here=GetActorLocation(),Floor=LiveHomeNodes.FindChecked(Next);const FVector Delta(Floor.X-Here.X,Floor.Y-Here.Y,0);
 const FFindFloorResult& ActualFloor=GetCharacterMovement()->CurrentFloor;
 const float SolidFloorZ=ActualFloor.bBlockingHit?ActualFloor.HitResult.ImpactPoint.Z:Here.Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
 const float Distance=Delta.Size(),Height=FMath::Abs(SolidFloorZ-Floor.Z);
 if(Distance<12&&Height<20&&GetCharacterMovement()->IsMovingOnGround()){
  LiveHomeNode=Next;LiveHomePath.RemoveAt(0);LiveHomeBest=BIG_NUMBER;LiveHomeProgressAt=Now;
  UE_LOG(LogTemp,Display,TEXT("SUB01_LIVE_HOME_REACHED node=%s pawn=%s floor=1 solidFloorCm=%.4f nominalFootCm=%.4f expectedFloorCm=%.4f"),*Next,*Here.ToString(),SolidFloorZ,Here.Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight(),Floor.Z);return;
 }
 const float Score=Distance+Height;if(Score<LiveHomeBest-1){LiveHomeBest=Score;LiveHomeProgressAt=Now;}
 if(Now-LiveHomeProgressAt>4){LiveHomeBlocked=true;GetCharacterMovement()->StopMovementImmediately();UE_LOG(LogTemp,Warning,TEXT("SUB01_LIVE_HOME_BLOCKED node=%s target=%s; collision not bypassed"),*LiveHomeNode,*Next);return;}
 if(Controller&&Distance>1){Controller->SetControlRotation(FRotator(-4,Delta.Rotation().Yaw,0));AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));}
}
'''

FIELDS += FEEDBACK_FIELDS
METHODS += FEEDBACK_METHODS

def graph_source():
    lines=[]
    for name,(x,y,z) in NODES.items():
        lines.append(f' LiveHomeNodes.Add(TEXT("{name}"),FVector({x*100:.6f},{z*100:.6f},{(y-1.65)*100:.6f}));')
    for a,b in EDGES:
        lines.append(f' LiveHomeEdges.FindOrAdd(TEXT("{a}")).Add(TEXT("{b}"));LiveHomeEdges.FindOrAdd(TEXT("{b}")).Add(TEXT("{a}"));')
    return '\n'.join(lines)

def install(header,cpp):
    header=header.replace('class USub01PCBridge;','class USub01PCBridge;\nclass FJsonObject;',1)
    header=header.replace(' void Forward(float Value);',FIELDS+'\n void Forward(float Value);',1)
    cpp=cpp.replace(' ConfigureActualPC();',' ConfigureActualPC();\n BeginLiveHome();',1)
    cpp=cpp.replace(' UpdateNativeRouteTest();',' UpdateNativeRouteTest();\n UpdateLiveHome(DeltaSeconds);',1)
    cpp=cpp.replace('const bool Hidden=Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270;', 'const bool Hidden=LiveHomePrivate||(Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270);',1)
    cpp=cpp.replace(' if(PCBridge)PCBridge->SetLocalPrivacy(Hidden);',' if(auto* Player=Cast<APlayerController>(Controller))if(Player->PlayerCameraManager)Player->PlayerCameraManager->StartCameraFade(Hidden?1:0,Hidden?1:0,0,FLinearColor::Black,false,Hidden);\n if(PCBridge)PCBridge->SetLocalPrivacy(Hidden);',1)
    return header,cpp+METHODS.replace('//@@SOURCE_GRAPH@@',graph_source())
