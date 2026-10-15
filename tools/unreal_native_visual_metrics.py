"""Read-only, rate-limited metrics from the sole real game view and exact fixtures.

No render submission, settings writes, material mutation, or pose changes. Metering
is the engine's last completed eye-adaptation readback, unavailable when zero.
"""
INCLUDES=r'''
#include "Engine/LocalPlayer.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PostProcessVolume.h"
#include "Camera/PlayerCameraManager.h"
#include "SceneView.h"
#include "HAL/IConsoleManager.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstance.h"
#include "CoreGlobals.h"
'''
FIELDS=r'''
 void PublishPrivateVisualMetrics();
 double PrivateVisualMetricsAt=-10;
'''
METHODS=r'''
void ASub01HomeCharacter::PublishPrivateVisualMetrics(){
 const double Now=FPlatformTime::Seconds();if(Now-PrivateVisualMetricsAt<1.0)return;PrivateVisualMetricsAt=Now;
 auto Doc=MakeShared<FJsonObject>();const FDateTime UTC=FDateTime::UtcNow();
 Doc->SetStringField(TEXT("schema"),TEXT("sub01.native-visual-metrics.v1"));Doc->SetBoolField(TEXT("read_only"),true);
 Doc->SetNumberField(TEXT("native_pid"),FPlatformProcess::GetCurrentProcessId());Doc->SetNumberField(TEXT("native_start_ticks"),PrivateSettingsStartTicks());
 Doc->SetNumberField(TEXT("captured_utc"),double(UTC.ToUnixTimestamp())+double(UTC.GetMillisecond())/1000.0);
 auto Num=[](const TSharedPtr<FJsonObject>& O,const TCHAR* Key,double Value){if(FMath::IsFinite(Value))O->SetNumberField(Key,Value);};
 Num(Doc,TEXT("actual_near_clip_cm"),GNearClippingPlane);
 if(auto* C=GetCapsuleComponent()){Num(Doc,TEXT("actual_capsule_radius_cm"),C->GetScaledCapsuleRadius());Num(Doc,TEXT("actual_capsule_half_height_cm"),C->GetScaledCapsuleHalfHeight());}
 auto Color=[&](const FLinearColor& C){auto O=MakeShared<FJsonObject>();Num(O,TEXT("r"),C.R);Num(O,TEXT("g"),C.G);Num(O,TEXT("b"),C.B);Num(O,TEXT("a"),C.A);return O;};
 auto PP=[&](const FPostProcessSettings& S){auto O=MakeShared<FJsonObject>();O->SetNumberField(TEXT("method"),int32(S.AutoExposureMethod));Num(O,TEXT("min_brightness"),S.AutoExposureMinBrightness);Num(O,TEXT("max_brightness"),S.AutoExposureMaxBrightness);Num(O,TEXT("bias"),S.AutoExposureBias);Num(O,TEXT("white_temperature"),S.WhiteTemp);Num(O,TEXT("white_tint"),S.WhiteTint);O->SetBoolField(TEXT("override_method"),S.bOverride_AutoExposureMethod);O->SetBoolField(TEXT("override_min"),S.bOverride_AutoExposureMinBrightness);O->SetBoolField(TEXT("override_max"),S.bOverride_AutoExposureMaxBrightness);O->SetBoolField(TEXT("override_bias"),S.bOverride_AutoExposureBias);O->SetBoolField(TEXT("override_white_temperature"),S.bOverride_WhiteTemp);return O;};
 const auto* EV=IConsoleManager::Get().FindConsoleVariable(TEXT("r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange"));Doc->SetBoolField(TEXT("extended_luminance_cvar_available"),EV!=nullptr);if(EV)Doc->SetNumberField(TEXT("extended_luminance_cvar"),EV->GetInt());
 if(ViewCamera){Doc->SetObjectField(TEXT("camera_postprocess"),PP(ViewCamera->PostProcessSettings));Num(Doc,TEXT("camera_postprocess_weight"),ViewCamera->PostProcessBlendWeight);Num(Doc,TEXT("fov"),ViewCamera->FieldOfView);}
 TArray<TSharedPtr<FJsonValue>> Volumes;
 for(TActorIterator<APostProcessVolume> It(GetWorld());It;++It){auto O=PP(It->Settings);O->SetStringField(TEXT("actor"),It->GetPathName());O->SetBoolField(TEXT("enabled"),It->bEnabled);O->SetBoolField(TEXT("unbound"),It->bUnbound);Num(O,TEXT("priority"),It->Priority);Num(O,TEXT("weight"),It->BlendWeight);Volumes.Add(MakeShared<FJsonValueObject>(O));}Doc->SetArrayField(TEXT("volumes"),Volumes);
 auto* Player=Cast<APlayerController>(GetController());
 if(Player&&Player->PlayerCameraManager){const auto& POV=Player->PlayerCameraManager->GetCameraCacheView();Doc->SetObjectField(TEXT("cached_camera_postprocess"),PP(POV.PostProcessSettings));Num(Doc,TEXT("cached_camera_weight"),POV.PostProcessBlendWeight);}
 Doc->SetBoolField(TEXT("blended_view_available"),false);Doc->SetBoolField(TEXT("last_completed_metering_available"),false);
 if(Player&&Player->GetLocalPlayer()&&GEngine&&GEngine->GameViewport&&GEngine->GameViewport->Viewport&&GetWorld()->Scene){
  FSceneViewFamilyContext Family(FSceneViewFamily::ConstructionValues(GEngine->GameViewport->Viewport,GetWorld()->Scene,GEngine->GameViewport->EngineShowFlags).SetRealtimeUpdate(true));
  FVector Location;FRotator Rotation;FSceneView* View=Player->GetLocalPlayer()->CalcSceneView(&Family,Location,Rotation,GEngine->GameViewport->Viewport);
  if(View){Doc->SetBoolField(TEXT("blended_view_available"),true);Doc->SetObjectField(TEXT("final_blended_postprocess"),PP(View->FinalPostProcessSettings));const float Exposure=View->GetLastEyeAdaptationExposure(),Luminance=View->GetLastAverageSceneLuminance();Doc->SetBoolField(TEXT("last_completed_metering_available"),FMath::IsFinite(Exposure)&&Exposure>0);Num(Doc,TEXT("last_completed_exposure_scale"),Exposure);Num(Doc,TEXT("last_completed_average_luminance"),Luminance);}
 }
 TArray<TSharedPtr<FJsonValue>> Lights;
 const TCHAR* Labels[]={TEXT("SUB01_AuthoredLight_SUN"),TEXT("SUB01_AuthoredLight_DeskLamp"),TEXT("SUB01_AuthoredLight_BedLamp"),TEXT("SUB01_AuthoredLight_KitchenWork"),TEXT("SUB01_AuthoredLight_LowerPendant"),TEXT("SUB01_AuthoredLight_UpperPendant"),TEXT("SUB01_ActualHDR_Sky")};
 for(const TCHAR* Label:Labels){auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("label"),Label);auto* Actor=FindAuthoredSettingsActor(Label);O->SetBoolField(TEXT("unique_actor"),Actor!=nullptr);if(Actor){O->SetStringField(TEXT("actor"),Actor->GetPathName());if(auto* L=Actor->FindComponentByClass<ULightComponentBase>()){Num(O,TEXT("intensity"),L->Intensity);O->SetObjectField(TEXT("light_color"),Color(L->GetLightColor()));Num(O,TEXT("indirect_intensity"),L->IndirectLightingIntensity);}if(auto* L=Actor->FindComponentByClass<ULightComponent>()){O->SetBoolField(TEXT("use_temperature"),L->bUseTemperature);Num(O,TEXT("temperature"),L->Temperature);}}Lights.Add(MakeShared<FJsonValueObject>(O));}Doc->SetArrayField(TEXT("lights"),Lights);
 TArray<TSharedPtr<FJsonValue>> Fixtures;const int32 Nodes[]={66,126,127,129,198,199};
 for(int32 Node:Nodes){auto O=MakeShared<FJsonObject>();O->SetNumberField(TEXT("source_node"),Node);const FString Name=FString::Printf(TEXT("full-home_node_%d"),Node);AActor* Found=nullptr;int32 Count=0;for(TActorIterator<AActor> It(GetWorld());It;++It)if(It->GetName()==Name){Found=*It;++Count;}O->SetNumberField(TEXT("actor_count"),Count);
  TArray<TSharedPtr<FJsonValue>> Slots;if(Count==1&&Found){TArray<UStaticMeshComponent*> Components;Found->GetComponents(Components);for(auto* C:Components)for(int32 Slot=0;Slot<C->GetNumMaterials();++Slot){auto* M=C->GetMaterial(Slot);if(!M)continue;auto S=MakeShared<FJsonObject>();S->SetStringField(TEXT("component"),C->GetPathName());S->SetNumberField(TEXT("slot"),Slot);S->SetStringField(TEXT("material"),M->GetPathName());TArray<TSharedPtr<FJsonValue>> Parents;UMaterialInterface* Parent=M;TSet<UMaterialInterface*> Seen;for(int32 Depth=0;Parent&&Depth<16&&!Seen.Contains(Parent);++Depth){Seen.Add(Parent);Parents.Add(MakeShared<FJsonValueString>(Parent->GetPathName()));auto* MI=Cast<UMaterialInstance>(Parent);Parent=MI?MI->Parent.Get():nullptr;}S->SetArrayField(TEXT("parent_chain"),Parents);
   TArray<FMaterialParameterInfo> Info;TArray<FGuid> IDs;auto Scalars=MakeShared<FJsonObject>();M->GetAllScalarParameterInfo(Info,IDs);for(const auto& P:Info){float V;if(M->GetScalarParameterValue(FHashedMaterialParameterInfo(P),V))Num(Scalars,*P.Name.ToString(),V);}S->SetObjectField(TEXT("scalars"),Scalars);
   Info.Reset();IDs.Reset();auto Vectors=MakeShared<FJsonObject>();M->GetAllVectorParameterInfo(Info,IDs);for(const auto& P:Info){FLinearColor V;if(M->GetVectorParameterValue(FHashedMaterialParameterInfo(P),V))Vectors->SetObjectField(P.Name.ToString(),Color(V));}S->SetObjectField(TEXT("vectors"),Vectors);Slots.Add(MakeShared<FJsonValueObject>(S));}}
  O->SetArrayField(TEXT("slots"),Slots);Fixtures.Add(MakeShared<FJsonValueObject>(O));}Doc->SetArrayField(TEXT("fixtures"),Fixtures);
 // Native owner/camera witness only; no camera or body placement mutation.
 if(ViewCamera){auto V=MakeShared<FJsonObject>();const FVector P=ViewCamera->GetComponentLocation();Num(V,TEXT("x"),P.X);Num(V,TEXT("y"),P.Y);Num(V,TEXT("z"),P.Z);Doc->SetObjectField(TEXT("actual_camera_world_cm"),V);}
 if(FirstPersonBody&&FirstPersonBody->GetSkeletalMeshAsset()&&FirstPersonBody->GetSkeletalMeshAsset()->GetPathName()==TEXT("/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner")&&FirstPersonBody->DoesSocketExist(TEXT("Head"))){
  const FTransform H=FirstPersonBody->GetSocketTransform(TEXT("Head"),RTS_World);
  const FVector Eye=H.GetLocation()+H.GetRotation().GetNormalized().RotateVector(FVector(.11885198390986161,-13.382490930007885,12.634526097714183));
  auto V=MakeShared<FJsonObject>();Num(V,TEXT("x"),Eye.X);Num(V,TEXT("y"),Eye.Y);Num(V,TEXT("z"),Eye.Z);Doc->SetObjectField(TEXT("owner_iris_surface_midpoint_world_cm"),V);
  Doc->SetStringField(TEXT("eye_witness_source"),TEXT("45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8"));
 }
 Num(Doc,TEXT("actual_speed_cm_s"),GetVelocity().Size2D());if(auto* Anim=FirstPersonBody?Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()):nullptr)Num(Doc,TEXT("target_animation_rate"),Anim->TargetRate);
 FString Raw;FJsonSerializer::Serialize(Doc,TJsonWriterFactory<>::Create(&Raw));const FString Temp=TEXT("/home/unreal/.sub01-private/native-visual-metrics.tmp");if(FFileHelper::SaveStringToFile(Raw,*Temp)&&std::rename(TCHAR_TO_UTF8(*Temp),"/home/unreal/.sub01-private/native-visual-metrics.json")!=0)UE_LOG(LogTemp,Error,TEXT("SUB01_NATIVE_VISUAL_METRICS_ATOMIC_PUBLICATION_FAILED"));
}
'''
def install(header,cpp):
    anchor='#include "Sub01HomeLab.h"'
    if cpp.count(anchor)!=1 or cpp.count(' Super::Tick(DeltaSeconds);')!=1:raise ValueError('Unique actual module/tick hooks required')
    if 'PrivateSettingsStartTicks' not in cpp:raise ValueError('Native identity helper must be installed first')
    header=header.replace(' private: UPROPERTY() TObjectPtr<UCameraComponent> ViewCamera;', ' private: UPROPERTY() TObjectPtr<UCameraComponent> ViewCamera;'+FIELDS,1)
    if 'void PublishPrivateVisualMetrics();' not in header:raise ValueError('Character declaration hook missing')
    cpp=cpp.replace(anchor,anchor+INCLUDES,1).replace(' Super::Tick(DeltaSeconds);',' Super::Tick(DeltaSeconds);\n PublishPrivateVisualMetrics();',1)+METHODS
    from unreal_native_projection_metrics import install as install_projection
    return header,install_projection(cpp)
