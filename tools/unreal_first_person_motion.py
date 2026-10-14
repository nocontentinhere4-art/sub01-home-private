"""First-person motion refinement; no pawn placement or skeletal pose changes.

Renderer owns integration/build. Manual input and CharacterMovement properties
remain intact; only automatic Live gaze and legacy procedural body sway change.
"""
from pathlib import Path

POLICY=r'''#pragma once
#include <algorithm>
#include <cmath>
namespace Sub01FirstPersonMotion {
inline double SmoothAngle(double Current,double Target,double Dt,double MaxDegreesPerSecond){
 if(!std::isfinite(Current))return 0;
 if(!std::isfinite(Target)||!std::isfinite(Dt)||Dt<=0||!std::isfinite(MaxDegreesPerSecond)||MaxDegreesPerSecond<=0)return Current;
 const double StepTime=std::min(Dt,.1);
 const double Error=std::remainder(Target-Current,360.);
 const double Alpha=-std::expm1(-8.*StepTime);
 const double Limit=MaxDegreesPerSecond*StepTime;
 return std::remainder(Current+std::clamp(Error*Alpha,-Limit,Limit),360.);
}
}
'''
SNAP='Controller->SetControlRotation(FRotator(-4,Delta.Rotation().Yaw,0));'
SMOOTH=r'''const FRotator CurrentLook=Controller->GetControlRotation();
  Controller->SetControlRotation(FRotator(
   Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Pitch,-4,Dt,90),
   Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Yaw,Delta.Rotation().Yaw,Dt,180),
   Sub01FirstPersonMotion::SmoothAngle(CurrentLook.Roll,0,Dt,90)));'''
SWAY=r''' MotionWeight=FMath::FInterpTo(MotionWeight,Weight,DeltaSeconds,10);
 if(Moving)WalkPhase+=FMath::Min(DeltaSeconds,.1f)*(Speed/140.f)*7.5f;
 // Only sub-centimetre camera-relative sway; no finger/bone deformation.
 // Phase freezes at idle and amplitude fades to zero, never perpetual bob.
 if(!HandsDiagnosticSeat){
  const bool CameraRelative=FirstPersonBody->GetAttachParent()==ViewCamera;
  FirstPersonBody->SetRelativeLocation(HandsBaseOffset+(CameraRelative?FVector(0,FMath::Sin(WalkPhase)*.25f*MotionWeight,FMath::Sin(2*WalkPhase)*.15f*MotionWeight):FVector::ZeroVector));
 }
'''
AUTHORED_ONLY=' // The captured skeletal clip supplies motion; no extra procedural body sine.\n if(!HandsDiagnosticSeat)FirstPersonBody->SetRelativeLocation(HandsBaseOffset);\n'

def stage(module):
    (Path(module)/'Sub01FirstPersonMotionPolicy.h').write_text(POLICY)

def install(header,cpp):
    include='#include "Sub01HomeLab.h"'
    if cpp.count(include)!=1 or cpp.count(SNAP)!=1 or cpp.count(SWAY)!=1:
        raise ValueError('Unique original native Live look and body-sway hooks required')
    cpp=cpp.replace(include,include+'\n#include "Sub01FirstPersonMotionPolicy.h"',1)
    return header,cpp.replace(SNAP,SMOOTH,1).replace(SWAY,AUTHORED_ONLY,1)
