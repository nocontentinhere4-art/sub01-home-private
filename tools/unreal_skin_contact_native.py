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
 for(int32 Side=0;Side<2;++Side){auto HandReport=(*Hands)[Side]->AsObject();double Shift=0.;if(!Sub01KeyboardContactCorrection(KeyMax.Z,HandReport->GetNumberField(TEXT("overMinCm")),HandReport->GetIntegerField(TEXT("overKeyVertices")),Shift))continue;
   int32 Hand=INDEX_NONE;const FString Suffix=Side==0?TEXT("LeftHand"):TEXT("RightHand");for(int32 B=0;B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(Suffix)){Hand=B;break;}if(Hand==INDEX_NONE)continue;
   const int32 Elbow=Ref.GetParentIndex(Hand),Upper=Ref.GetParentIndex(Elbow);if(Upper<0||Elbow<0)continue;
   FTransform A=Result[Upper],B=Result[Elbow],C=Result[Hand];const FQuat CapturedWrist=C.GetRotation();
   const FVector Up=BodyWorld.InverseTransformVectorNoScale(FVector(0,0,Shift));const FVector Effector=C.GetTranslation()+Up;
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
SEAT_HEADER = r"""
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static FString AnalyzeCapturedSeatSkin(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,const TArray<FVector>& CushionTriangles,float FloorZ);
"""
SEAT_CPP = r"""
// Highest surface height under (X,Y) among world triangles (vertical projection);
// false when (X,Y) is over none of them. Degenerate triangles are ignored.
static bool Sub01SurfaceHeightAt(const FVector* Tris,int32 Count,double X,double Y,double& Z){
 bool Found=false;
 for(int32 T=0;T+2<Count;T+=3){
  const FVector& A=Tris[T];const FVector& B=Tris[T+1];const FVector& C=Tris[T+2];
  const double Det=(B.Y-C.Y)*(A.X-C.X)+(C.X-B.X)*(A.Y-C.Y);if(Det>-1.e-9&&Det<1.e-9)continue;
  const double L1=((B.Y-C.Y)*(X-C.X)+(C.X-B.X)*(Y-C.Y))/Det,L2=((C.Y-A.Y)*(X-C.X)+(A.X-C.X)*(Y-C.Y))/Det,L3=1-L1-L2;
  if(L1<-1.e-6||L2<-1.e-6||L3<-1.e-6)continue;
  const double H=L1*A.Z+L2*B.Z+L3*C.Z;if(!Found||H>Z)Z=H;Found=true;
 }
 return Found;
}
// docs/qa/contact.md, seated: buttocks AND back of each thigh touch the cushion
// (-2.5..+0.5 cm), each sole touches the floor (0..+1 cm). Rule 4: measured where the
// contact belongs, as separate patches of downward-facing skin (posed normal toward the
// surface), with coverage counts and gap quantiles; never one lowest vertex for a region.
// Probe only: it changes nothing and never sets NativeSeatVerified.
FString USub01HomeHandsInstance::AnalyzeCapturedSeatSkin(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,const TArray<FVector>& CushionTriangles,float FloorZ){
#if WITH_EDITOR
 if(!Mesh)return TEXT("{\"error\":\"missing mesh\"}");
 if(CushionTriangles.Num()<3||CushionTriangles.Num()%3)return TEXT("{\"error\":\"missing cushion triangles\"}");
 const auto& Ref=Mesh->GetRefSkeleton();const auto& Inv=Mesh->GetRefBasesInvMatrix();auto* Model=Mesh->GetImportedModel();
 if(!Model||!Model->LODModels.Num()||ComponentPose.Num()!=Ref.GetNum()||Inv.Num()!=Ref.GetNum())return TEXT("{\"error\":\"incomplete pose or imported model\"}");
 // 0 buttocks (Hips), 1 left / 2 right posterior thigh (UpLeg), 3 left / 4 right sole (Foot/ToeBase).
 struct FRegion{int32 Count=0,Facing=0,Over=0,Band=0;TArray<double> Gaps;};FRegion R[5];int32 Invalid=0;
 const TCHAR* Names[5]={TEXT("buttocks"),TEXT("left_posterior_thigh"),TEXT("right_posterior_thigh"),TEXT("left_sole"),TEXT("right_sole")};
 for(const auto& Section:Model->LODModels[0].Sections)for(const auto& V:Section.SoftVertices){
  uint64 Sum=0;double W5[5]={0,0,0,0,0};
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;Sum+=W;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local)){++Invalid;continue;}const int32 B=Section.BoneMap[Local];if(!Ref.GetRefBoneInfo().IsValidIndex(B)){++Invalid;continue;}
   const FString Name=Ref.GetBoneName(B).ToString();
   if(Name.EndsWith(TEXT("Hips")))W5[0]+=W;else if(Name.EndsWith(TEXT("LeftUpLeg")))W5[1]+=W;else if(Name.EndsWith(TEXT("RightUpLeg")))W5[2]+=W;
   else if(Name.EndsWith(TEXT("LeftFoot"))||Name.EndsWith(TEXT("LeftToeBase")))W5[3]+=W;else if(Name.EndsWith(TEXT("RightFoot"))||Name.EndsWith(TEXT("RightToeBase")))W5[4]+=W;}
  if(!Sum)continue;int32 Which=-1;double Best=.30*Sum;for(int32 K=0;K<5;++K)if(W5[K]>=Best){Best=W5[K];Which=K;}if(Which<0)continue;
  FVector P=FVector::ZeroVector,N=FVector::ZeroVector;const FVector3f BindNormal(V.TangentZ.X,V.TangentZ.Y,V.TangentZ.Z);
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local))continue;const int32 B=Section.BoneMap[Local];if(!Inv.IsValidIndex(B))continue;const double F=double(W)/double(Sum);
   P+=ComponentPose[B].TransformPosition(FVector(Inv[B].TransformPosition(V.Position)))*F;N+=ComponentPose[B].TransformVectorNoScale(FVector(Inv[B].TransformVector(BindNormal)))*F;}
  P=BodyWorld.TransformPosition(P);N=BodyWorld.TransformVectorNoScale(N).GetSafeNormal();
  auto& Region=R[Which];++Region.Count;if(N.Z>-.5)continue;++Region.Facing; // only skin facing down onto the surface
  double Gap=0;
  if(Which<3){double Top=0;if(!Sub01SurfaceHeightAt(CushionTriangles.GetData(),CushionTriangles.Num(),P.X,P.Y,Top))continue;Gap=P.Z-Top;if(Gap>=-2.5&&Gap<=.5)++Region.Band;}
  else{Gap=P.Z-FloorZ;if(Gap>=0&&Gap<=1)++Region.Band;}
  ++Region.Over;Region.Gaps.Add(Gap);
 }
 FString Result=FString::Printf(TEXT("{\"invalidInfluences\":%d,\"floorCm\":%.8f,\"regions\":["),Invalid,FloorZ);
 for(int32 K=0;K<5;++K){auto& G=R[K].Gaps;G.Sort();auto Q=[&G](double F){return G.Num()?G[FMath::Clamp(int32(F*(G.Num()-1)+.5),0,G.Num()-1)]:0.;};
  Result+=FString::Printf(TEXT("%s{\"region\":\"%s\",\"selectedVertices\":%d,\"facingVertices\":%d,\"overSurfaceVertices\":%d,\"bandVertices\":%d,\"minGapCm\":%.8f,\"p10GapCm\":%.8f,\"p50GapCm\":%.8f,\"p90GapCm\":%.8f,\"maxGapCm\":%.8f}"),
   K?TEXT(","):TEXT(""),Names[K],R[K].Count,R[K].Facing,R[K].Over,R[K].Band,Q(0),Q(.1),Q(.5),Q(.9),Q(1));}
 return Result+TEXT("]}");
#else
 return TEXT("{\"error\":\"editor only\"}");
#endif
}
"""
HEADER += IK_HEADER + SEAT_HEADER
from unreal_keyboard_contact_target import CPP as KEY_CONTACT_CPP
CPP = '#include <cmath>\n#include "TwoBoneIK.h"\n#include "Serialization/JsonSerializer.h"\n#include "Serialization/JsonReader.h"\n' + CPP + KEY_CONTACT_CPP + IK_CPP + SEAT_CPP
