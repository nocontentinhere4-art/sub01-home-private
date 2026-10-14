"""Native fixed bind-space plantar and localized toe/heel support witness.

Reads the original imported feet and a supplied real pose/floor. Never changes a
pose, physics, a contact gate, or NativeSeatVerified. Raised heels are retained.
"""
HEADER=r'''
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static int32 FinishPendingStaticCompilation();
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static FString AnalyzeFixedPlantarSupport(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld,float LeftFloorZ,float RightFloorZ);
'''
POLICY_CPP=r'''
namespace Sub01FixedPlantar {
inline bool Member(double Z,double NormalZ,double MinFootZ,double Weight){
 return std::isfinite(Z)&&std::isfinite(NormalZ)&&std::isfinite(MinFootZ)&&std::isfinite(Weight)
  &&Weight>=.30&&Z>=MinFootZ-1e-5&&Z<=MinFootZ+.4&&NormalZ<-.7;
}
struct Point {double X,Y,Z,NormalZ;};
inline double SupportArea(const Point& A,const Point& B,const Point& C,double Floor){
 const Point P[3]={A,B,C};if(!std::isfinite(Floor))return 0;
 for(const auto& V:P)if(!std::isfinite(V.X)||!std::isfinite(V.Y)||!std::isfinite(V.Z)||!std::isfinite(V.NormalZ)||V.Z<Floor||V.Z>Floor+1||V.NormalZ>=-.1)return 0;
 return .5*std::fabs((B.X-A.X)*(C.Y-A.Y)-(B.Y-A.Y)*(C.X-A.X));
}
}
'''
CPP=r'''
#if WITH_EDITOR
#include "StaticMeshCompiler.h"
#endif
int32 USub01HomeHandsInstance::FinishPendingStaticCompilation(){
#if WITH_EDITOR
 auto& Manager=FStaticMeshCompilingManager::Get();Manager.FinishAllCompilation();return Manager.GetNumRemainingMeshes();
#else
 return -1;
#endif
}
'''+POLICY_CPP+r'''
FString USub01HomeHandsInstance::AnalyzeFixedPlantarSupport(USkeletalMesh* Mesh,const TArray<FTransform>& Pose,const FTransform& Body,float LeftFloor,float RightFloor){
#if WITH_EDITOR
 if(!Mesh||Mesh->GetPathName()!=TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner"))return TEXT("{\"error\":\"exact original owner required\"}");
 if(Body.ContainsNaN()||Body.GetScale3D().GetMin()<=0)return TEXT("{\"error\":\"finite positive-scale body transform required\"}");
 if(!FMath::IsFinite(LeftFloor)||!FMath::IsFinite(RightFloor))return TEXT("{\"error\":\"finite actual per-foot floor required\"}");
 const auto& Ref=Mesh->GetRefSkeleton();const auto& Inv=Mesh->GetRefBasesInvMatrix();auto* Model=Mesh->GetImportedModel();
 if(!Model||!Model->LODModels.Num()||Pose.Num()!=Ref.GetNum()||Inv.Num()!=Ref.GetNum())return TEXT("{\"error\":\"incomplete actual skin\"}");
 const auto& LOD=Model->LODModels[0];int32 Invalid=0;double MinBind=DBL_MAX;
 auto FootSection=[Mesh](int32 Material){return Mesh->GetMaterials().IsValidIndex(Material)&&Mesh->GetMaterials()[Material].MaterialSlotName==FName(TEXT("feet"));};
 auto SideWeight=[&Ref,&Invalid](const auto& Section,const auto& V,int32& Side)->double{
  uint64 Sum=0;double Weights[2]={0,0};
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;Sum+=W;const int32 L=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(L)){++Invalid;continue;}const int32 B=Section.BoneMap[L];if(!Ref.GetRefBoneInfo().IsValidIndex(B)){++Invalid;continue;}const FString N=Ref.GetBoneName(B).ToString();
   if(N.EndsWith(TEXT("LeftFoot"))||N.EndsWith(TEXT("LeftToeBase")))Weights[0]+=W;
   if(N.EndsWith(TEXT("RightFoot"))||N.EndsWith(TEXT("RightToeBase")))Weights[1]+=W;}
  Side=Weights[0]>=Weights[1]?0:1;return Sum?Weights[Side]/Sum:0.;
 };
 for(const auto& S:LOD.Sections)if(FootSection(S.MaterialIndex))for(const auto& V:S.SoftVertices){int32 Side=0;if(SideWeight(S,V,Side)>=.30)MinBind=FMath::Min(MinBind,double(V.Position.Z));}
 if(MinBind==DBL_MAX||Invalid)return TEXT("{\"error\":\"missing feet section or invalid bone weights\"}");
 TMap<int32,Sub01FixedPlantar::Point> Points[2];double Min[2]={DBL_MAX,DBL_MAX},Max[2]={-DBL_MAX,-DBL_MAX},Area[2]={0,0};int32 Contact[2]={0,0},Penetrating[2]={0,0},Triangles[2]={0,0};const double Floor[2]={LeftFloor,RightFloor};
 for(const auto& S:LOD.Sections)if(FootSection(S.MaterialIndex))for(int32 Id=0;Id<S.SoftVertices.Num();++Id){const auto& V=S.SoftVertices[Id];int32 Side=0;const double Weight=SideWeight(S,V,Side);
  if(!Sub01FixedPlantar::Member(V.Position.Z,V.TangentZ.Z,MinBind,Weight))continue;
  uint64 Sum=0;for(const auto W:V.InfluenceWeights)Sum+=W;if(!Sum){++Invalid;continue;}FVector P=FVector::ZeroVector,N=FVector::ZeroVector;
  const FVector3f BindNormal(V.TangentZ.X,V.TangentZ.Y,V.TangentZ.Z);
  for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;const int32 Local=V.InfluenceBones[I];if(!S.BoneMap.IsValidIndex(Local)){++Invalid;continue;}const int32 B=S.BoneMap[Local];if(!Inv.IsValidIndex(B)){++Invalid;continue;}const double F=double(W)/Sum;
   P+=Pose[B].TransformPosition(FVector(Inv[B].TransformPosition(V.Position)))*F;
   N+=Pose[B].TransformVectorNoScale(FVector(Inv[B].TransformVector(BindNormal)))*F;}
  P=Body.TransformPosition(P);N=Body.TransformVectorNoScale(N).GetSafeNormal();if(P.ContainsNaN()||N.ContainsNaN()){++Invalid;continue;}
  Points[Side].Add(S.BaseVertexIndex+Id,Sub01FixedPlantar::Point{P.X,P.Y,P.Z,N.Z});const double Gap=P.Z-Floor[Side];Min[Side]=FMath::Min(Min[Side],Gap);Max[Side]=FMath::Max(Max[Side],Gap);if(Gap<0)++Penetrating[Side];if(Gap>=0&&Gap<=1&&N.Z<-.1)++Contact[Side];
 }
 if(Invalid||!Points[0].Num()||!Points[1].Num())return TEXT("{\"error\":\"invalid or empty fixed plantar membership\"}");
 for(const auto& S:LOD.Sections)if(FootSection(S.MaterialIndex))for(uint32 T=0;T<S.NumTriangles;++T){const uint32 At=S.BaseIndex+3*T;if(At+2>=uint32(LOD.IndexBuffer.Num()))return TEXT("{\"error\":\"invalid imported topology\"}");
  for(int32 Side=0;Side<2;++Side){const auto* A=Points[Side].Find(LOD.IndexBuffer[At]);const auto* B=Points[Side].Find(LOD.IndexBuffer[At+1]);const auto* C=Points[Side].Find(LOD.IndexBuffer[At+2]);if(!A||!B||!C)continue;const double LocalArea=Sub01FixedPlantar::SupportArea(*A,*B,*C,Floor[Side]);if(LocalArea>0){Area[Side]+=LocalArea;++Triangles[Side];}}
 }
 auto Root=MakeShared<FJsonObject>();Root->SetStringField(TEXT("schema"),TEXT("sub01.fixed-plantar-support.v1"));Root->SetBoolField(TEXT("runtime_ready"),false);Root->SetBoolField(TEXT("contact_accepted"),false);Root->SetNumberField(TEXT("invalidInfluences"),Invalid);Root->SetNumberField(TEXT("bindFootMinZCm"),MinBind);Root->SetNumberField(TEXT("bindBandCm"),.4);
 Root->SetStringField(TEXT("selection"),TEXT("Exact feet material; fixed original bind floor+4mm, bind normal Z<-.7, foot/toe normalized weight>=.30. All selected plantar skin checked for penetration; actual heel raise preserved."));
 Root->SetStringField(TEXT("limitation"),TEXT("Per-foot floors must come from actual support traces; this witness does not certify seat, whole-body collision or readiness. Projected toe/heel patch uses complete actual triangles wholly in floor0..1cm band, never a median-flat sole requirement."));
 TArray<TSharedPtr<FJsonValue>> Regions;for(int32 Side=0;Side<2;++Side){auto R=MakeShared<FJsonObject>();R->SetStringField(TEXT("side"),Side?TEXT("right"):TEXT("left"));R->SetNumberField(TEXT("fixedVertices"),Points[Side].Num());R->SetNumberField(TEXT("floorCm"),Floor[Side]);R->SetNumberField(TEXT("minGapCm"),Min[Side]);R->SetNumberField(TEXT("maxGapCm"),Max[Side]);R->SetNumberField(TEXT("penetratingVertices"),Penetrating[Side]);R->SetNumberField(TEXT("supportBandVertices"),Contact[Side]);R->SetNumberField(TEXT("supportTriangles"),Triangles[Side]);R->SetNumberField(TEXT("projectedSupportAreaCm2"),Area[Side]);Regions.Add(MakeShared<FJsonValueObject>(R));}
 Root->SetArrayField(TEXT("regions"),Regions);FString Output;FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Output));return Output;
#else
 return TEXT("{\"error\":\"editor only witness\"}");
#endif
}
'''
