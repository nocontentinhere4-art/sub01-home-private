"""Opt-in replay of verified nonstretch arm IK samples, retaining captured fingers."""
HEADER=r'''
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> ContactSequence;
 UPROPERTY(Transient) TArray<float> ContactTimes;
 UPROPERTY(Transient) TArray<FName> ContactBones;
 UPROPERTY(Transient) TArray<FTransform> ContactLocalTransforms;
 UPROPERTY(Transient) float ContactFreezeTime=-1;
 UPROPERTY(Transient) int32 ContactRestartSerial=0;
 UPROPERTY(Transient) float ContactEvaluatedTime=-1;
'''
PROXY_FIELDS=r'''
 TObjectPtr<UAnimSequence> ContactSequence;TArray<float> ContactTimes;TArray<FName> ContactBones;TArray<FTransform> ContactLocals;float ContactFreeze=-1;int32 RestartSerial=0;float EvaluatedContactTime=-1;
'''
PREUPDATE=r'''
  ContactSequence=Hands->ContactSequence;ContactFreeze=Hands->ContactFreezeTime;Hands->ContactEvaluatedTime=EvaluatedContactTime;
  if(RestartSerial!=Hands->ContactRestartSerial){RestartSerial=Hands->ContactRestartSerial;Current.SetAccumulatedTime(3);}
  if(ContactTimes.Num()!=Hands->ContactTimes.Num()){ContactTimes=Hands->ContactTimes;ContactBones=Hands->ContactBones;ContactLocals=Hands->ContactLocalTransforms;ContactFreeze=Hands->ContactFreezeTime;}
'''
SEQUENCE_START=r'''
   Current.SetLoopAnimation(true);
   if(ContactTimes.Num()&&Current.GetSequence()==ContactSequence){Current.SetLoopAnimation(false);Current.SetAccumulatedTime(ContactFreeze>=0?ContactFreeze:ContactTimes[0]);}
'''
RATE=r'''
  if(ContactTimes.Num()&&Current.GetSequence()==ContactSequence&&(ContactFreeze>=0||Current.GetAccumulatedTime()>=ContactTimes.Last()))Current.SetPlayRate(0);
'''
EVALUATE=r'''
 virtual bool Evaluate(FPoseContext& Output) override {
  Blend.Evaluate_AnyThread(Output);
  if(Current.GetSequence()!=ContactSequence||ContactTimes.Num()<2||ContactBones.Num()!=6||ContactLocals.Num()!=ContactTimes.Num()*6)return true;
  const float Time=Current.GetAccumulatedTime();EvaluatedContactTime=Time;int32 A=0;while(A+1<ContactTimes.Num()&&ContactTimes[A+1]<=Time)++A;const int32 B=FMath::Min(A+1,ContactTimes.Num()-1);const float W=A==B?0:FMath::Clamp((Time-ContactTimes[A])/(ContactTimes[B]-ContactTimes[A]),0.f,1.f);
  const auto& Bones=Output.Pose.GetBoneContainer();const auto& Ref=Bones.GetReferenceSkeleton();
  for(int32 I=0;I<6;++I){const int32 MeshIndex=Ref.FindBoneIndex(ContactBones[I]);if(MeshIndex<0)continue;const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(MeshIndex));if(Compact.GetInt()<0)continue;FTransform T;T.Blend(ContactLocals[A*6+I],ContactLocals[B*6+I],W);Output.Pose[Compact]=T;}
  return true;
 }
'''
LOAD=r'''
 FString ProfilePath;
 if(Role==TEXT("DeskTyping")&&FParse::Value(FCommandLine::Get(),TEXT("Sub01ContactProfile="),ProfilePath)){
  FString Raw;TSharedPtr<FJsonObject> Root;bool Valid=FFileHelper::LoadFileToString(Raw,*ProfilePath)&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),Root);
  const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;Valid=Valid&&Root.IsValid()&&Root->TryGetArrayField(TEXT("samples"),Rows)&&Rows->Num()==151;
  auto* Instance=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance());TArray<float> Times;TArray<FName> Names;TArray<FTransform> Values;
  if(Valid&&Instance){for(const auto& RowValue:*Rows){auto Row=RowValue->AsObject();if(Row->GetNumberField(TEXT("bone_length_max_error_cm"))>.01||Row->GetNumberField(TEXT("finger_local_max_error_degrees"))>.1){Valid=false;break;}auto Corrected=Row->GetObjectField(TEXT("corrected"));for(const auto& H:Corrected->GetArrayField(TEXT("hands")))if(H->AsObject()->GetNumberField(TEXT("penetrationCm"))>.1)Valid=false;
   auto Arms=Row->GetObjectField(TEXT("corrected_local_arms"));if(Names.IsEmpty()){for(const auto& Pair:Arms->Values)Names.Add(FName(*Pair.Key));Names.Sort([](const FName& A,const FName& B){return A.LexicalLess(B);});}if(Names.Num()!=6){Valid=false;break;}Times.Add(Row->GetNumberField(TEXT("time")));
   for(const auto& Name:Names){auto T=Arms->GetObjectField(Name.ToString());const auto& P=T->GetArrayField(TEXT("translation"));const auto& Q=T->GetArrayField(TEXT("rotation"));const auto& S=T->GetArrayField(TEXT("scale"));if(P.Num()!=3||Q.Num()!=4||S.Num()!=3){Valid=false;break;}Values.Add(FTransform(FQuat(Q[0]->AsNumber(),Q[1]->AsNumber(),Q[2]->AsNumber(),Q[3]->AsNumber()),FVector(P[0]->AsNumber(),P[1]->AsNumber(),P[2]->AsNumber()),FVector(S[0]->AsNumber(),S[1]->AsNumber(),S[2]->AsNumber())));}
  }}
  if(Valid&&Instance&&Values.Num()==Times.Num()*6){Instance->ContactSequence=Clip;Instance->ContactTimes=MoveTemp(Times);Instance->ContactBones=MoveTemp(Names);Instance->ContactLocalTransforms=MoveTemp(Values);FParse::Value(FCommandLine::Get(),TEXT("Sub01ContactFreeze="),Instance->ContactFreezeTime);FString RecordDir;if(FParse::Value(FCommandLine::Get(),TEXT("Sub01ContactRecordDir="),RecordDir))Instance->ContactFreezeTime=3;UE_LOG(LogTemp,Display,TEXT("SUB01_CONTACT_PROFILE_BOUND 151 samples; six arm bones only; captured fingerlocals retained; onepass; requires visual acceptance"));}
  else UE_LOG(LogTemp,Error,TEXT("SUB01_CONTACT_PROFILE_REFUSED invalid/unresolved surface/finger/bone checks"));
 }
'''

def install(header,cpp,diagnostic):
 header=header.replace(' protected:',HEADER+'\n protected:')
 cpp=cpp.replace(' float Progress=1;',PROXY_FIELDS+'\n float Progress=1;')
 cpp=cpp.replace('  if(Current.GetSequence()!=Hands->TargetSequence)',PREUPDATE+'\n  if(Current.GetSequence()!=Hands->TargetSequence)')
 cpp=cpp.replace('   Progress=Hands->PreviousSequence?0:1;',SEQUENCE_START+'\n   Progress=Hands->PreviousSequence?0:1;')
 cpp=cpp.replace('  Current.SetPlayRate(Hands->TargetRate);','  Current.SetPlayRate(Hands->TargetRate);\n'+RATE)
 cpp=cpp.replace(' virtual bool Evaluate(FPoseContext& Output) override {Blend.Evaluate_AnyThread(Output);return true;}',EVALUATE)
 diagnostic=diagnostic.replace(' HandsClips.Add(FName(*Role),Clip);SetHandsPosture(FName(*Role));',' HandsClips.Add(FName(*Role),Clip);SetHandsPosture(FName(*Role));\n'+LOAD)
 return header,cpp,diagnostic
