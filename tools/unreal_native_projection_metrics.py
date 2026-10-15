"""Add read-only actual-viewport projection diagnostics to installed metrics.

No camera pose, FOV/aspect write, viewport resize, input, scene submission or
privacy-gate change. Uses the exact UE5.8 GetProjectionData API inspected on the
private server. Angular spans come from the actual perspective matrix, including
asymmetric principal-point shifts, rather than an assumed axis policy.
"""
INCLUDES='''
#include "Engine/LocalPlayer.h"
#include "Engine/GameViewportClient.h"
#include "Camera/CameraComponent.h"
#include "SceneView.h"
#include "UnrealClient.h"
#include "HAL/IConsoleManager.h"
#include <cmath>
#include <initializer_list>
'''
POLICY=r'''
namespace Sub01ProjectionMetrics {
struct FAngles {
 bool Valid=false;
 double Left=0,Right=0,Bottom=0,Top=0,Horizontal=0,Vertical=0;
};
inline FAngles FromPerspective(double M00,double M11,double M20,double M21,double M23,double M33){
 FAngles Result;
 for(double Value:{M00,M11,M20,M21,M23,M33})if(!std::isfinite(Value))return Result;
 if(M00<=0||M11<=0||std::fabs(M23-1.)>1.e-9||std::fabs(M33)>1.e-9)return Result;
 const double Degrees=180./std::acos(-1.);
 // UE row-vector convention: NDCx=M00*(viewX/viewZ)+M20, and similarly Y.
 Result.Left=std::atan2(-1.-M20,M00)*Degrees;
 Result.Right=std::atan2(1.-M20,M00)*Degrees;
 Result.Bottom=std::atan2(-1.-M21,M11)*Degrees;
 Result.Top=std::atan2(1.-M21,M11)*Degrees;
 Result.Horizontal=Result.Right-Result.Left;Result.Vertical=Result.Top-Result.Bottom;
 Result.Valid=std::isfinite(Result.Horizontal)&&std::isfinite(Result.Vertical)&&
  Result.Horizontal>0&&Result.Horizontal<180&&Result.Vertical>0&&Result.Vertical<180;
 return Result;
}
}
'''
BLOCK=r'''
 // SUB01_READ_ONLY_ACTUAL_PROJECTION_V1: intrinsics only; no pose/settings writes.
 auto Projection=MakeShared<FJsonObject>();Projection->SetStringField(TEXT("schema"),TEXT("sub01.native-projection-metrics.v1"));
 Projection->SetBoolField(TEXT("read_only"),true);Projection->SetBoolField(TEXT("valid"),false);
 Projection->SetBoolField(TEXT("projection_data_available"),false);
 Projection->SetStringField(TEXT("unavailable_reason"),TEXT("viewport_or_local_player_unavailable"));
 const auto* LegacyY=IConsoleManager::Get().FindConsoleVariable(TEXT("r.UseLegacyMaintainYFOVViewMatrix"));
 Projection->SetBoolField(TEXT("legacy_maintain_y_cvar_available"),LegacyY!=nullptr);
 if(LegacyY)Projection->SetNumberField(TEXT("legacy_maintain_y_cvar"),LegacyY->GetInt());
 if(ViewCamera){
  Num(Projection,TEXT("camera_field_of_view_degrees"),ViewCamera->FieldOfView);
  Num(Projection,TEXT("camera_aspect_ratio"),ViewCamera->AspectRatio);
  Projection->SetBoolField(TEXT("camera_constrain_aspect_ratio"),ViewCamera->bConstrainAspectRatio);
  Projection->SetBoolField(TEXT("camera_axis_constraint_overridden"),ViewCamera->bOverrideAspectRatioAxisConstraint);
  Projection->SetNumberField(TEXT("camera_axis_constraint"),int32(ViewCamera->AspectRatioAxisConstraint.GetValue()));
 }
 if(Player&&Player->PlayerCameraManager){
  const auto& CameraPOV=Player->PlayerCameraManager->GetCameraCacheView();
  Num(Projection,TEXT("cached_camera_field_of_view_degrees"),CameraPOV.FOV);Num(Projection,TEXT("cached_camera_aspect_ratio"),CameraPOV.AspectRatio);
  Projection->SetBoolField(TEXT("cached_camera_constrain_aspect_ratio"),CameraPOV.bConstrainAspectRatio);
  Projection->SetBoolField(TEXT("cached_camera_axis_constraint_overridden"),CameraPOV.AspectRatioAxisConstraint.IsSet());
  if(CameraPOV.AspectRatioAxisConstraint.IsSet())Projection->SetNumberField(TEXT("cached_camera_axis_constraint"),int32(CameraPOV.AspectRatioAxisConstraint.GetValue()));
 }
 auto* LocalProjectionPlayer=Player?Player->GetLocalPlayer():nullptr;
 FViewport* ActualProjectionViewport=(GEngine&&GEngine->GameViewport)?GEngine->GameViewport->Viewport:nullptr;
 if(LocalProjectionPlayer){Projection->SetNumberField(TEXT("local_player_axis_constraint"),int32(LocalProjectionPlayer->AspectRatioAxisConstraint.GetValue()));}
 if(LocalProjectionPlayer&&ActualProjectionViewport){
  const FIntPoint Size=ActualProjectionViewport->GetSizeXY();Projection->SetNumberField(TEXT("viewport_width_px"),Size.X);Projection->SetNumberField(TEXT("viewport_height_px"),Size.Y);
  FSceneViewProjectionData Data;
  if(LocalProjectionPlayer->GetProjectionData(ActualProjectionViewport,Data)){
   Projection->SetBoolField(TEXT("projection_data_available"),true);
   const FIntRect& ViewRect=Data.GetViewRect();const FIntRect& ConstrainedRect=Data.GetConstrainedViewRect();
   Projection->SetNumberField(TEXT("view_rect_width_px"),ViewRect.Width());Projection->SetNumberField(TEXT("view_rect_height_px"),ViewRect.Height());
   Projection->SetNumberField(TEXT("constrained_width_px"),ConstrainedRect.Width());Projection->SetNumberField(TEXT("constrained_height_px"),ConstrainedRect.Height());
   const FMatrix& Matrix=Data.ProjectionMatrix;
   Num(Projection,TEXT("matrix_m00"),Matrix.M[0][0]);Num(Projection,TEXT("matrix_m11"),Matrix.M[1][1]);
   Num(Projection,TEXT("matrix_m20"),Matrix.M[2][0]);Num(Projection,TEXT("matrix_m21"),Matrix.M[2][1]);
   Num(Projection,TEXT("matrix_m23"),Matrix.M[2][3]);Num(Projection,TEXT("matrix_m33"),Matrix.M[3][3]);
   bool Finite=true;for(int32 Row=0;Row<4;++Row)for(int32 Column=0;Column<4;++Column)Finite=Finite&&FMath::IsFinite(Matrix.M[Row][Column]);
   Projection->SetBoolField(TEXT("projection_matrix_finite"),Finite);Projection->SetBoolField(TEXT("perspective"),Data.IsPerspectiveProjection());
   const auto Angles=Sub01ProjectionMetrics::FromPerspective(Matrix.M[0][0],Matrix.M[1][1],Matrix.M[2][0],Matrix.M[2][1],Matrix.M[2][3],Matrix.M[3][3]);
   const bool RectValid=Size.X>0&&Size.Y>0&&ViewRect.Width()>0&&ViewRect.Height()>0&&ConstrainedRect.Width()>0&&ConstrainedRect.Height()>0;
   // This derivation requires the standard unskewed perspective structure. Lens
   // shift is supported, while an oblique/skewed projection stays unavailable.
   const bool Unskewed=FMath::Abs(Matrix.M[0][1])<1.e-9&&FMath::Abs(Matrix.M[1][0])<1.e-9&&FMath::Abs(Matrix.M[0][3])<1.e-9&&FMath::Abs(Matrix.M[1][3])<1.e-9&&FMath::Abs(Matrix.M[3][0])<1.e-9&&FMath::Abs(Matrix.M[3][1])<1.e-9;
   const bool Valid=Finite&&Data.IsPerspectiveProjection()&&Angles.Valid&&RectValid&&Unskewed;
   Projection->SetBoolField(TEXT("valid"),Valid);
   if(Valid){
    Num(Projection,TEXT("horizontal_fov_degrees"),Angles.Horizontal);Num(Projection,TEXT("vertical_fov_degrees"),Angles.Vertical);
    Num(Projection,TEXT("left_ray_degrees"),Angles.Left);Num(Projection,TEXT("right_ray_degrees"),Angles.Right);
    Num(Projection,TEXT("bottom_ray_degrees"),Angles.Bottom);Num(Projection,TEXT("top_ray_degrees"),Angles.Top);
    Projection->RemoveField(TEXT("unavailable_reason"));
   }else Projection->SetStringField(TEXT("unavailable_reason"),TEXT("non_perspective_or_invalid_matrix_or_rect"));
  }else Projection->SetStringField(TEXT("unavailable_reason"),TEXT("projection_data_unavailable"));
 }
 Doc->SetObjectField(TEXT("projection"),Projection);
 // SUB01_READ_ONLY_ACTUAL_PROJECTION_V1_END
'''


def install(cpp):
 """Extend exactly one already-installed real metrics method; no regeneration."""
 start='void ASub01HomeCharacter::PublishPrivateVisualMetrics(){'
 end=' FString Raw;FJsonSerializer::Serialize(Doc,TJsonWriterFactory<>::Create(&Raw));'
 anchor=' auto* Player=Cast<APlayerController>(GetController());'
 if cpp.count(start)!=1 or 'SUB01_READ_ONLY_ACTUAL_PROJECTION_V1' in cpp:
  raise ValueError('Exactly one existing metrics method without projection extension required')
 first=cpp.index(start);last=cpp.find(end,first)
 if last<0:raise ValueError('Exact existing atomic metrics publication required')
 body=cpp[first:last]
 if body.count(anchor)!=1 or 'auto Num=' not in body:
  raise ValueError('Existing local-player and finite-number metrics anchors required')
 index=first+body.index(anchor)+len(anchor)
 cpp=cpp[:index]+BLOCK+cpp[index:]
 include_anchor='#include "Sub01HomeLab.h"'
 if cpp.count(include_anchor)!=1:raise ValueError('Exact native module include anchor required')
 missing=''.join(line+'\n'for line in INCLUDES.splitlines()if line.startswith('#include')and line not in cpp)
 return cpp.replace(include_anchor,include_anchor+'\n'+missing+POLICY,1)
