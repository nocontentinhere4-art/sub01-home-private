"""Explicit acceptance-test route: actual CharacterMovement input, never teleport."""
FIELDS=r'''
 void BeginNativeRouteTest();
 void UpdateNativeRouteTest();
 void FinishNativeRouteTest(bool Success,const TCHAR* Reason);
 bool RouteActive=false,RouteFailed=false;
 int32 RouteIndex=0;
 double RouteStarted=0,RouteStepStarted=0,RouteLastProgress=0;
 float RouteBestDistance=BIG_NUMBER,RouteCaptureDelay=45;
 TArray<FVector> RouteTargets;
 TArray<FString> RouteNames;
'''
METHODS=r'''
void ASub01HomeCharacter::BeginNativeRouteTest(){
 if(!FParse::Param(FCommandLine::Get(),TEXT("Sub01RouteTest")))return;
 // Actual source home_world.NODES, x/z metres -> verified UE x/y centimetres.
 // Capsule centre is floor + 91cm; no teleport, forced vertical position or jump.
 RouteNames={TEXT("door"),TEXT("front"),TEXT("stair_approach"),TEXT("stair_bottom"),TEXT("stair_top"),TEXT("landing"),TEXT("loft"),TEXT("bed")};
 RouteTargets={FVector(200,310,96),FVector(130,320,96),FVector(30,320,96),FVector(30,255,96),FVector(30,-170,396),FVector(30,-210,396),FVector(-50,-210,396),FVector(-120,-290,396)};
 RouteCaptureDelay=CaptureAfter>0?CaptureAfter:45;CaptureAfter=-1;
 RouteStarted=FPlatformTime::Seconds();RouteStepStarted=RouteStarted;RouteLastProgress=RouteStarted;
 RouteActive=true;
 UE_LOG(LogTemp,Display,TEXT("SUB01_ROUTE_TEST_ONLY native CharacterMovement input; brain/backend unchanged; no teleport"));
}
void ASub01HomeCharacter::FinishNativeRouteTest(bool Success,const TCHAR* Reason){
 RouteActive=false;RouteFailed=!Success;GetCharacterMovement()->StopMovementImmediately();
 UE_LOG(LogTemp,Display,TEXT("SUB01_ROUTE_RESULT success=%d reason=%s reached=%d/%d pawn=%s eye=%s floor=%d"),Success?1:0,Reason,RouteIndex,RouteTargets.Num(),*GetActorLocation().ToString(),*ViewCamera->GetComponentLocation().ToString(),GetCharacterMovement()->IsMovingOnGround()?1:0);
 CaptureStarted=FPlatformTime::Seconds();CaptureAfter=RouteCaptureDelay;
}
void ASub01HomeCharacter::UpdateNativeRouteTest(){
 if(!RouteActive)return;
 const double Now=FPlatformTime::Seconds();if(Now-RouteStarted<2)return;
 if(!Controller){FinishNativeRouteTest(false,TEXT("Missing actual player controller"));return;}
 const FVector Here=GetActorLocation(),Target=RouteTargets[RouteIndex];
 const FVector Delta(Target.X-Here.X,Target.Y-Here.Y,0);
 const float Distance=Delta.Size(),HeightError=FMath::Abs(Target.Z-Here.Z);
 if(Distance<12&&HeightError<20&&GetCharacterMovement()->IsMovingOnGround()){
  UE_LOG(LogTemp,Display,TEXT("SUB01_ROUTE_CHECKPOINT name=%s pawn=%s eye=%s floor=%d heightErrorCm=%.3f"),*RouteNames[RouteIndex],*Here.ToString(),*ViewCamera->GetComponentLocation().ToString(),GetCharacterMovement()->IsMovingOnGround()?1:0,HeightError);
  ++RouteIndex;RouteStepStarted=Now;RouteLastProgress=Now;RouteBestDistance=BIG_NUMBER;
  if(RouteIndex==RouteTargets.Num()){FinishNativeRouteTest(true,TEXT("Ground entry to loft bed walked physically"));return;}
  return;
 }
 const float Score=Distance+HeightError;
 if(Score<RouteBestDistance-1){RouteBestDistance=Score;RouteLastProgress=Now;}
 if(Now-RouteLastProgress>3||Now-RouteStepStarted>14||Now-RouteStarted>70){FinishNativeRouteTest(false,TEXT("Blocked or no progress; collision not bypassed"));return;}
 if(Here.Z<-100||Here.Z>750||FMath::Abs(Here.X)>600||FMath::Abs(Here.Y)>700){FinishNativeRouteTest(false,TEXT("Outside conservative house bounds"));return;}
 if(Distance>1){
  Controller->SetControlRotation(FRotator(-4,Delta.Rotation().Yaw,0));
  AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));
 }
}
'''
