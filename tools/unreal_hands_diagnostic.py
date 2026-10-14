"""CLI-only unaccepted pose review from authentic clips; no runtime gate mutation."""
FIELDS=r'''
 void LoadPrivateHandsDiagnostic();
 bool HandsDiagnostic=false;
 bool HandsDiagnosticSeat=false;
 UPROPERTY() TArray<TObjectPtr<USkeletalMeshComponent>> DiagnosticFollowers;
'''
METHODS=r'''
void ASub01HomeCharacter::LoadPrivateHandsDiagnostic(){
 FString Role,MeshPath,ClipPath,Parts;float Yaw=-90;
 if(!FParse::Value(FCommandLine::Get(),TEXT("Sub01HandsDiagnostic="),Role))return;
 if(Role!=TEXT("Phone")&&Role!=TEXT("DeskTyping")&&Role!=TEXT("Walk")){UE_LOG(LogTemp,Error,TEXT("SUB01_DIAGNOSTIC invalid captured role"));return;}
 FParse::Value(FCommandLine::Get(),TEXT("Sub01DiagnosticMesh="),MeshPath);
 FParse::Value(FCommandLine::Get(),TEXT("Sub01DiagnosticClip="),ClipPath);
 FParse::Value(FCommandLine::Get(),TEXT("Sub01DiagnosticParts="),Parts);
 FParse::Value(FCommandLine::Get(),TEXT("Sub01DiagnosticYaw="),Yaw);
 auto* Mesh=LoadObject<USkeletalMesh>(nullptr,*MeshPath);
 auto* Clip=LoadObject<UAnimSequence>(nullptr,*ClipPath);
 if(!Mesh||!Clip||Mesh->GetSkeleton()!=Clip->GetSkeleton()){UE_LOG(LogTemp,Error,TEXT("SUB01_DIAGNOSTIC requires actual mesh/clip shared USkeleton"));return;}
 const FVector Extent=Mesh->GetBounds().BoxExtent;
 if(Extent.X<=0||Extent.Y<=0||Extent.Z<=0){UE_LOG(LogTemp,Error,TEXT("SUB01_DIAGNOSTIC rejects zero built mesh bounds"));return;}
 HandsDiagnostic=true;
 FirstPersonBody->SetSkeletalMeshAsset(Mesh);
 FirstPersonBody->SetAnimInstanceClass(USub01HomeHandsInstance::StaticClass());
 FirstPersonBody->SetRelativeRotation(FRotator(0,Yaw,0));
 HandsMeshRotation=FRotator(0,Yaw,0);
 const auto& Ref=Mesh->GetRefSkeleton();
 for(int32 I=0;I<Ref.GetNum();++I)if(Ref.GetBoneName(I).ToString().EndsWith(TEXT("Head")))FirstPersonBody->HideBoneByName(Ref.GetBoneName(I),EPhysBodyOp::PBO_None);
 TArray<FString> Paths;Parts.ParseIntoArray(Paths,TEXT(";"),true);
 for(const FString& Path:Paths){
  auto* Part=LoadObject<USkeletalMesh>(nullptr,*Path);
  if(!Part||Part==Mesh||Part->GetSkeleton()!=Mesh->GetSkeleton()){UE_LOG(LogTemp,Error,TEXT("SUB01_DIAGNOSTIC invalid follower %s"),*Path);continue;}
  auto* Follower=NewObject<USkeletalMeshComponent>(this);
  Follower->SetupAttachment(FirstPersonBody);Follower->SetSkeletalMeshAsset(Part);
  Follower->SetCollisionEnabled(ECollisionEnabled::NoCollision);Follower->SetCastShadow(false);Follower->SetOnlyOwnerSee(true);
  Follower->SetLeaderPoseComponent(FirstPersonBody,true,false);Follower->RegisterComponent();DiagnosticFollowers.Add(Follower);
 }
 HandsClips.Add(FName(*Role),Clip);SetHandsPosture(FName(*Role));
 if(Role==TEXT("DeskTyping")&&FParse::Param(FCommandLine::Get(),TEXT("Sub01DiagnosticSeat"))){
  // Controlled pose review, NOT a physical navigation/sit transition assertion.
  // Original contact-anchor whole-body transform; actual imported clip unchanged.
  HandsDiagnosticSeat=true;PrivateViewMode=EPrivateViewMode::Diagnostic;GetCharacterMovement()->StopMovementImmediately();GetCharacterMovement()->DisableMovement();
  FirstPersonBody->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);
  FirstPersonBody->SetWorldLocationAndRotation(FVector(203.9,-232.3,-.6),FRotator(0,180,0));
  HandsBaseOffset=FirstPersonBody->GetRelativeLocation();
  FName HeadBone;
  for(int32 I=0;I<Ref.GetNum();++I)if(Ref.GetBoneName(I).ToString().EndsWith(TEXT("Head")))HeadBone=Ref.GetBoneName(I);
  if(!HeadBone.IsNone()){
   ViewCamera->AttachToComponent(FirstPersonBody,FAttachmentTransformRules::SnapToTargetNotIncludingScale,HeadBone);
   ViewCamera->SetUsingAbsoluteRotation(true);
   if(Controller)Controller->SetControlRotation(FRotator(-14,-90,0));
   GetWorld()->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this,[this](){
    if(Controller)Controller->SetControlRotation(FRotator(-14,-90,0));
   }));
   ViewCamera->FieldOfView=90;
  }
  UE_LOG(LogTemp,Display,TEXT("SUB01_STATIC_DESK_POSE_DIAGNOSTIC camera follows actual captured Head bone; body contact-anchor only; no navigation/seating acceptance; head=%s"),*HeadBone.ToString());
 }

 UE_LOG(LogTemp,Display,TEXT("SUB01_UNVERIFIED_PRIVATE_HANDS_DIAGNOSTIC role=%s mesh=%s clip=%s followers=%d bounds=%s; contact/POV/runtime not accepted; brain/backend unchanged"),*Role,*MeshPath,*ClipPath,DiagnosticFollowers.Num(),*Extent.ToString());
}
'''
