"""Actual private PC component wiring, exact authored monitor only."""
FIELDS=r'''
 UPROPERTY() TObjectPtr<USub01PCBridge> PCBridge;
 void ConfigureActualPC();
 void UpdateNativePCPrivacy();
 bool TryNativeHomeDevice(UActorComponent* Component);
 UFUNCTION(Exec) void NativePhoneAction(const FString& Action);
 UFUNCTION(Exec) void NativePhoneNavigate(const FString& URL);
 UFUNCTION(Exec) void NativeTVGame(const FString& Game);
 UFUNCTION(Exec) void NativePCCommand(const FString& Line);
'''
METHODS=r'''
#include "Sub01HomeDeviceBridge.h"
void ASub01HomeCharacter::ConfigureActualPC(){
 UStaticMeshComponent* Screen=nullptr;int32 Count=0;
 const FVector Expected(200,-327.6,116),Extent(34,0,20);
 for(TActorIterator<AActor> It(GetWorld());It;++It){
  TArray<UStaticMeshComponent*> Components;It->GetComponents(Components);
  for(auto* C:Components){
   if(!C->GetStaticMesh())continue;
   const FBoxSphereBounds B=C->CalcBounds(C->GetComponentTransform());
   if(FVector::Dist(B.Origin,Expected)<1.5f&&FVector::Dist(B.BoxExtent,Extent)<1.5f){Screen=C;++Count;}
  }
 }
 if(Count!=1){UE_LOG(LogTemp,Error,TEXT("SUB01_PC_MONITOR_REFUSED exact authored screen matches=%d"),Count);return;}
 auto* Material=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Sub01Home/Devices/M_Sub01LivePC.M_Sub01LivePC"));
 if(!Material){UE_LOG(LogTemp,Error,TEXT("SUB01_PC_MATERIAL_MISSING"));return;}
 auto* Devices=NewObject<USub01HomeDeviceBridge>(this);AddInstanceComponent(Devices);Devices->RegisterComponent();
 struct DevicePlane {FName Device;FVector Center;FVector Extent;};
 for(const DevicePlane Plane: {DevicePlane{TEXT("phone"),FVector(270,-292,86.6),FVector(3.35,6.85,0)},DevicePlane{TEXT("tv"),FVector(-374.7,-5,165),FVector(0,83,47.5)}}){
  UStaticMeshComponent* Match=nullptr;int32 Matches=0;
  for(TActorIterator<AActor> It(GetWorld());It;++It){TArray<UStaticMeshComponent*> Parts;It->GetComponents(Parts);for(auto* C:Parts){if(!C->GetStaticMesh())continue;const auto B=C->CalcBounds(C->GetComponentTransform());if(FVector::Dist(B.Origin,Plane.Center)<.2f&&FVector::Dist(B.BoxExtent,Plane.Extent)<.2f){Match=C;++Matches;}}}
  if(Matches==1&&Devices->Configure(Plane.Device,Match,0,Material))Match->ComponentTags.AddUnique(FName(*(TEXT("SUB01Device:")+Plane.Device.ToString())));
  else UE_LOG(LogTemp,Warning,TEXT("SUB01_HOME_DEVICE_SURFACE_UNAVAILABLE device=%s matches=%d"),*Plane.Device.ToString(),Matches);
 }
 if(PCBridge->Configure(Screen,0,Material)){
  Screen->ComponentTags.AddUnique(TEXT("SUB01Device:Desk"));
  UE_LOG(LogTemp,Display,TEXT("SUB01_ACTUAL_PC_MONITOR_BOUND component=%s boundsCenter=%s slot=0; actual backend status=%s"),*Screen->GetName(),*Screen->CalcBounds(Screen->GetComponentTransform()).Origin.ToString(),*PCBridge->GetPCStatus());
 }
}
void ASub01HomeCharacter::UpdateNativePCPrivacy(){
 const FVector Eye=ViewCamera->GetComponentLocation();
 // Exact source bathroomBounds converted x,z,y metres -> UE x,y,z centimetres.
 const bool Hidden=Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270;
 if(PCBridge)PCBridge->SetLocalPrivacy(Hidden);
 if(auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>())Devices->SetLocalPrivacy(Hidden);
}
bool ASub01HomeCharacter::TryNativeHomeDevice(UActorComponent* Component){
 UpdateNativePCPrivacy();if(auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>()){if(Devices->FocusHit(Component)){if(PCBridge)PCBridge->SetOperatorFocus(false);return true;}}return false;
}
void ASub01HomeCharacter::NativePhoneAction(const FString& Action){UpdateNativePCPrivacy();if(auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>())Devices->PhoneAction(Action);}
void ASub01HomeCharacter::NativePhoneNavigate(const FString& URL){UpdateNativePCPrivacy();if(auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>())Devices->PhoneNavigate(URL);}
void ASub01HomeCharacter::NativeTVGame(const FString& Game){UpdateNativePCPrivacy();if(auto* Devices=FindComponentByClass<USub01HomeDeviceBridge>())Devices->TVGame(Game);}
void ASub01HomeCharacter::NativePCCommand(const FString& Line){
 if(!PCBridge)return;
 UpdateNativePCPrivacy();
 const double Now=FPlatformTime::Seconds();
 if(LiveHome&&(!NativeSeatVerified||!NativeFeedbackSeatReady()||!LiveHomeFresh||LiveHomePrivate||LiveHomeBlocked||Now-LiveHomeLastReceived>3||Now<LiveHomeLastReceived||LiveHomePath.Num()!=0||LiveHomeNode!=TEXT("desk")||LiveHomeTarget!=TEXT("desk")||(LiveHomeActivity!=TEXT("use_computer")&&LiveHomeActivity!=TEXT("research")&&LiveHomeActivity!=TEXT("chart")))){
  PCBridge->SetOperatorFocus(false);
  UE_LOG(LogTemp,Warning,TEXT("SUB01_PC_OPERATOR_INPUT_REFUSED live home requires a fresh acknowledged physical desk seat"));return;
 }
 PCBridge->SetOperatorFocus(true);PCBridge->SetTypedLine(Line);PCBridge->SubmitTypedLine();
 UE_LOG(LogTemp,Display,TEXT("SUB01_PC_OPERATOR_INPUT requested through authenticated real backend; status=%s"),*PCBridge->GetPCStatus());
}
'''
