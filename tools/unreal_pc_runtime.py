"""Actual private PC component wiring, exact authored monitor only."""
FIELDS=r'''
 UPROPERTY() TObjectPtr<USub01PCBridge> PCBridge;
 void ConfigureActualPC();
 void UpdateNativePCPrivacy();
 UFUNCTION(Exec) void NativePCCommand(const FString& Line);
'''
METHODS=r'''
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
 if(PCBridge->Configure(Screen,0,Material)){
  Screen->ComponentTags.AddUnique(TEXT("SUB01Device:Desk"));
  UE_LOG(LogTemp,Display,TEXT("SUB01_ACTUAL_PC_MONITOR_BOUND component=%s boundsCenter=%s slot=0; actual backend status=%s"),*Screen->GetName(),*Screen->CalcBounds(Screen->GetComponentTransform()).Origin.ToString(),*PCBridge->GetPCStatus());
 }
}
void ASub01HomeCharacter::UpdateNativePCPrivacy(){
 if(!PCBridge)return;
 const FVector Eye=ViewCamera->GetComponentLocation();
 // Exact source bathroomBounds converted x,z,y metres -> UE x,y,z centimetres.
 PCBridge->SetLocalPrivacy(Eye.Z>300&&Eye.X>-378&&Eye.X<-85&&Eye.Y>50&&Eye.Y<270);
}
void ASub01HomeCharacter::NativePCCommand(const FString& Line){
 if(!PCBridge)return;
 UpdateNativePCPrivacy();PCBridge->SetOperatorFocus(true);PCBridge->SetTypedLine(Line);PCBridge->SubmitTypedLine();
 UE_LOG(LogTemp,Display,TEXT("SUB01_PC_OPERATOR_INPUT requested through authenticated real backend; status=%s"),*PCBridge->GetPCStatus());
}
'''
