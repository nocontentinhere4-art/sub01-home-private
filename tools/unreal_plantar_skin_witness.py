"""Read-only imported bind-space foot witnesses; no posed-normal contact selection.

The native dump keeps fixed section/vertex identity, material, original bind
position/normal, bone weights and topology alongside each sampled world position.
It deliberately does not label this broad foot-weight set as plantar contact.
"""
HEADER = r'''
 UFUNCTION(BlueprintCallable,Category="SUB01|PrivateDiagnostics") static FString DumpImportedFootWitness(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld);
'''
CPP = r'''
FString USub01HomeHandsInstance::DumpImportedFootWitness(USkeletalMesh* Mesh,const TArray<FTransform>& ComponentPose,const FTransform& BodyWorld){
#if WITH_EDITOR
 if(!Mesh)return TEXT("{\"error\":\"missing mesh\"}");
 const auto& Ref=Mesh->GetRefSkeleton();const auto& Inv=Mesh->GetRefBasesInvMatrix();const auto* Model=Mesh->GetImportedModel();
 if(!Model||!Model->LODModels.Num()||ComponentPose.Num()!=Ref.GetNum()||Inv.Num()!=Ref.GetNum())return TEXT("{\"error\":\"incomplete imported skin\"}");
 auto Root=MakeShared<FJsonObject>();TArray<TSharedPtr<FJsonValue>> Vertices,Triangles;int32 Invalid=0,SectionId=0;
 auto Vector=[](const FVector& P){TArray<TSharedPtr<FJsonValue>> A;A.Add(MakeShared<FJsonValueNumber>(P.X));A.Add(MakeShared<FJsonValueNumber>(P.Y));A.Add(MakeShared<FJsonValueNumber>(P.Z));return A;};
 for(const auto& Section:Model->LODModels[0].Sections){TSet<int32> Selected;int32 LocalId=0;
  for(const auto& V:Section.SoftVertices){const int32 VertexId=LocalId++;uint64 Sum=0;double Left=0,Right=0;TArray<TSharedPtr<FJsonValue>> Weights;
   for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;Sum+=W;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local)){++Invalid;continue;}const int32 B=Section.BoneMap[Local];if(!Ref.GetRefBoneInfo().IsValidIndex(B)){++Invalid;continue;}const FString Name=Ref.GetBoneName(B).ToString();
    if(Name.EndsWith(TEXT("LeftFoot"))||Name.EndsWith(TEXT("LeftToeBase")))Left+=W;
    if(Name.EndsWith(TEXT("RightFoot"))||Name.EndsWith(TEXT("RightToeBase")))Right+=W;
    auto Weight=MakeShared<FJsonObject>();Weight->SetStringField(TEXT("bone"),Name);Weight->SetNumberField(TEXT("raw"),W);Weights.Add(MakeShared<FJsonValueObject>(Weight));}
   if(!Sum||(Left<.30*Sum&&Right<.30*Sum))continue;Selected.Add(Section.BaseVertexIndex+VertexId);
   FVector P=FVector::ZeroVector;for(int32 I=0;I<UE_ARRAY_COUNT(V.InfluenceWeights);++I){const auto W=V.InfluenceWeights[I];if(!W)continue;const int32 Local=V.InfluenceBones[I];if(!Section.BoneMap.IsValidIndex(Local))continue;const int32 B=Section.BoneMap[Local];if(!Inv.IsValidIndex(B))continue;P+=ComponentPose[B].TransformPosition(FVector(Inv[B].TransformPosition(V.Position)))*(double(W)/double(Sum));}
   auto Item=MakeShared<FJsonObject>();Item->SetNumberField(TEXT("section"),SectionId);Item->SetNumberField(TEXT("vertex"),VertexId);Item->SetNumberField(TEXT("globalVertex"),Section.BaseVertexIndex+VertexId);Item->SetNumberField(TEXT("materialIndex"),Section.MaterialIndex);Item->SetStringField(TEXT("side"),Left>=Right?TEXT("left"):TEXT("right"));Item->SetNumberField(TEXT("footWeightFraction"),FMath::Max(Left,Right)/Sum);
   if(Mesh->GetMaterials().IsValidIndex(Section.MaterialIndex)){const auto& Mat=Mesh->GetMaterials()[Section.MaterialIndex];Item->SetStringField(TEXT("materialSlot"),Mat.MaterialSlotName.ToString());Item->SetStringField(TEXT("materialPath"),Mat.MaterialInterface?Mat.MaterialInterface->GetPathName():TEXT(""));}
   Item->SetArrayField(TEXT("bindPositionCm"),Vector(FVector(V.Position)));Item->SetArrayField(TEXT("bindNormal"),Vector(FVector(V.TangentZ.X,V.TangentZ.Y,V.TangentZ.Z)));Item->SetArrayField(TEXT("worldPositionCm"),Vector(BodyWorld.TransformPosition(P)));Item->SetArrayField(TEXT("weights"),Weights);Vertices.Add(MakeShared<FJsonValueObject>(Item));
  }
  for(uint32 T=0;T<Section.NumTriangles;++T){const uint32 Offset=Section.BaseIndex+3*T;if(Offset+2>=uint32(Model->LODModels[0].IndexBuffer.Num())){++Invalid;break;}const auto& Indices=Model->LODModels[0].IndexBuffer;const int32 A=Indices[Offset],B=Indices[Offset+1],C=Indices[Offset+2];if(!Selected.Contains(A)&&!Selected.Contains(B)&&!Selected.Contains(C))continue;TArray<TSharedPtr<FJsonValue>> Tri;Tri.Add(MakeShared<FJsonValueNumber>(A));Tri.Add(MakeShared<FJsonValueNumber>(B));Tri.Add(MakeShared<FJsonValueNumber>(C));Triangles.Add(MakeShared<FJsonValueArray>(Tri));}
  ++SectionId;
 }
 Root->SetStringField(TEXT("selection"),TEXT("fixed imported foot/toe weight >=30%; NOT plantar acceptance"));Root->SetNumberField(TEXT("invalidInfluences"),Invalid);Root->SetArrayField(TEXT("vertices"),Vertices);Root->SetArrayField(TEXT("adjacentTrianglesGlobalIds"),Triangles);FString Output;FJsonSerializer::Serialize(Root,TJsonWriterFactory<>::Create(&Output));return Output;
#else
 return TEXT("{\"error\":\"editor only\"}");
#endif
}
'''
