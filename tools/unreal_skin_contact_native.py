"""Native imported-vertex LBS diagnostics; does not modify captured poses."""
HEADER = r'''
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static FString AnalyzeCapturedFingerSkin(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,FVector KeyMin,FVector KeyMax,const TArray<FVector>& KeyTriangles);
'''
CPP = r'''
FString USub01HomeHandsInstance::AnalyzeCapturedFingerSkin(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,FVector KeyMin,FVector KeyMax,const TArray<FVector>& KeyTriangles){
#if WITH_EDITOR
 if(!Mesh)return TEXT("{\"error\":\"missing mesh\"}");
 const auto& Ref=Mesh->GetRefSkeleton();const auto& Inv=Mesh->GetRefBasesInvMatrix();auto* Model=Mesh->GetImportedModel();
 if(!Model||!Model->LODModels.Num()||ComponentPose.Num()!=Ref.GetNum()||Inv.Num()!=Ref.GetNum())return TEXT("{\"error\":\"incomplete pose or imported model\"}");
 struct FSide {int32 Count=0,Over=0;double Min=DBL_MAX,Max=-DBL_MAX,MinOver=DBL_MAX,MaxOver=-DBL_MAX;};FSide Sides[2];int32 Invalid=0;
 for(const auto& Section:Model->LODModels[0].Sections)for(const auto& V:Section.SoftVertices){
  uint64 Sum=0;double Distal[2]={0,0};
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;Sum+=W;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local)){++Invalid;continue;}const int32 B=Section.BoneMap[Local];if(!Ref.GetRefBoneInfo().IsValidIndex(B)){++Invalid;continue;}const FString Name=Ref.GetBoneName(B).ToString();if(Name.EndsWith(TEXT("3"))&&(Name.Contains(TEXT("Index"))||Name.Contains(TEXT("Middle"))||Name.Contains(TEXT("Ring"))||Name.Contains(TEXT("Pinky"))||Name.Contains(TEXT("Thumb")))){if(Name.Contains(TEXT("LeftHand")))Distal[0]+=W;else if(Name.Contains(TEXT("RightHand")))Distal[1]+=W;}}
  if(!Sum)continue;const int32 Side=Distal[0]>=.30*Sum?0:(Distal[1]>=.30*Sum?1:-1);if(Side<0)continue;
  FVector P=FVector::ZeroVector;
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local))continue;const int32 B=Section.BoneMap[Local];if(!Inv.IsValidIndex(B))continue;const FVector Bind=FVector(Inv[B].TransformPosition(V.Position));P+=ComponentPose[B].TransformPosition(Bind)*(double(W)/double(Sum));}
  P=BodyWorld.TransformPosition(P);auto& S=Sides[Side];++S.Count;S.Min=FMath::Min(S.Min,P.Z);S.Max=FMath::Max(S.Max,P.Z);
  bool Over=false;if(P.X>=KeyMin.X&&P.X<=KeyMax.X&&P.Y>=KeyMin.Y&&P.Y<=KeyMax.Y){for(int32 T=0;T+2<KeyTriangles.Num();T+=3){const auto& A=KeyTriangles[T];const auto& B=KeyTriangles[T+1];const auto& C=KeyTriangles[T+2];auto Cross=[](const FVector& U,const FVector& V,const FVector& Q){return (V.X-U.X)*(Q.Y-U.Y)-(V.Y-U.Y)*(Q.X-U.X);};const double D1=Cross(A,B,P),D2=Cross(B,C,P),D3=Cross(C,A,P);if((D1>=-1.e-6&&D2>=-1.e-6&&D3>=-1.e-6)||(D1<=1.e-6&&D2<=1.e-6&&D3<=1.e-6)){Over=true;break;}}}if(Over){++S.Over;S.MinOver=FMath::Min(S.MinOver,P.Z);S.MaxOver=FMath::Max(S.MaxOver,P.Z);}
 }
 FString Result=FString::Printf(TEXT("{\"invalidInfluences\":%d,\"keyTopCm\":%.8f,\"hands\":["),Invalid,KeyMax.Z);
 for(int32 I=0;I<2;++I){const auto& S=Sides[I];if(I)Result+=TEXT(",");Result+=FString::Printf(TEXT("{\"side\":\"%s\",\"selectedVertices\":%d,\"overKeyVertices\":%d,\"minCm\":%.8f,\"maxCm\":%.8f,\"overMinCm\":%.8f,\"overMaxCm\":%.8f,\"penetrationCm\":%.8f}"),I==0?TEXT("left"):TEXT("right"),S.Count,S.Over,S.Count?S.Min:0,S.Count?S.Max:0,S.Over?S.MinOver:0,S.Over?S.MaxOver:0,S.Over?FMath::Max(0.,KeyMax.Z-S.MinOver):0);}
 return Result+TEXT("]}");
#else
 return TEXT("{\"error\":\"editor only\"}");
#endif
}
'''
IK_HEADER = r'''
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static TArray<FTransform> SolveCapturedKeyboardArmContact(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,FVector KeyMin,FVector KeyMax,const TArray<FVector>& KeyTriangles);
'''
IK_CPP = r'''
TArray<FTransform> USub01HomeHandsInstance::SolveCapturedKeyboardArmContact(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,FVector KeyMin,FVector KeyMax,const TArray<FVector>& KeyTriangles){
 TArray<FTransform> Result=ComponentPose;
 if(!Mesh||Result.Num()!=Mesh->GetRefSkeleton().GetNum())return Result;
 const auto& Ref=Mesh->GetRefSkeleton();TArray<FTransform> OriginalLocal;OriginalLocal.SetNum(Result.Num());
 for(int32 B=0;B<Result.Num();++B){const int32 P=Ref.GetParentIndex(B);OriginalLocal[B]=P>=0?ComponentPose[B].GetRelativeTransform(ComponentPose[P]):ComponentPose[B];}
 for(int32 Iter=0;Iter<3;++Iter){
  const FString Audit=AnalyzeCapturedFingerSkin(Mesh,Result,BodyWorld,KeyMin,KeyMax,KeyTriangles);TSharedPtr<FJsonObject> Root;auto Reader=TJsonReaderFactory<>::Create(Audit);if(!FJsonSerializer::Deserialize(Reader,Root)||!Root.IsValid())break;
  const TArray<TSharedPtr<FJsonValue>>* Hands=nullptr;if(!Root->TryGetArrayField(TEXT("hands"),Hands)||Hands->Num()!=2)break;
  bool Changed=false;
  for(int32 Side=0;Side<2;++Side){auto HandReport=(*Hands)[Side]->AsObject();if(HandReport->GetIntegerField(TEXT("overKeyVertices"))<4)continue;const double Pen=FMath::Max(0.,KeyMax.Z-HandReport->GetNumberField(TEXT("minCm")));if(Pen<=.001||Pen>12)continue;
   int32 Hand=INDEX_NONE;const FString Suffix=Side==0?TEXT("LeftHand"):TEXT("RightHand");for(int32 B=0;B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(Suffix)){Hand=B;break;}if(Hand==INDEX_NONE)continue;
   const int32 Elbow=Ref.GetParentIndex(Hand),Upper=Ref.GetParentIndex(Elbow);if(Upper<0||Elbow<0)continue;
   FTransform A=Result[Upper],B=Result[Elbow],C=Result[Hand];const FQuat CapturedWrist=C.GetRotation();
   const FVector Up=BodyWorld.InverseTransformVectorNoScale(FVector(0,0,Pen+.08));const FVector Effector=C.GetTranslation()+Up;
   AnimationCore::SolveTwoBoneIK(A,B,C,B.GetTranslation(),Effector,false,1.,1.);
   C.SetRotation(CapturedWrist);const int32 Parent=Ref.GetParentIndex(Upper);
   TArray<FTransform> Local=OriginalLocal;
   for(int32 N=0;N<Result.Num();++N){const int32 P=Ref.GetParentIndex(N);Local[N]=P>=0?Result[N].GetRelativeTransform(Result[P]):Result[N];const FString Name=Ref.GetBoneName(N).ToString();if(Name.Contains(TEXT("HandThumb"))||Name.Contains(TEXT("HandIndex"))||Name.Contains(TEXT("HandMiddle"))||Name.Contains(TEXT("HandRing"))||Name.Contains(TEXT("HandPinky")))Local[N]=OriginalLocal[N];}
   Local[Upper]=Parent>=0?A.GetRelativeTransform(Result[Parent]):A;Local[Elbow]=B.GetRelativeTransform(A);Local[Hand]=C.GetRelativeTransform(B);
   // Descendant finger local transforms remain bit-for-bit captured; no finger overrides.
   for(int32 N=0;N<Result.Num();++N){const int32 P=Ref.GetParentIndex(N);Result[N]=P>=0?Local[N]*Result[P]:Local[N];}
   Changed=true;
  }
  if(!Changed)break;
 }
 return Result;
}
'''
HEADER += IK_HEADER
CPP = '#include "TwoBoneIK.h"\n#include "Serialization/JsonSerializer.h"\n#include "Serialization/JsonReader.h"\n' + CPP + IK_CPP
