"""First-person motion refinement; no pawn placement or skeletal pose changes.

Renderer owns integration/build. Manual input and CharacterMovement properties
remain intact. Authored walk playback follows actual planar speed through braking,
using the existing 140 cm/s playback reference, without a minimum cadence floor.
"""
from pathlib import Path

POLICY=r'''#pragma once
#include <algorithm>
#include <cmath>
namespace Sub01FirstPersonMotion {
inline double HeadingWalkScale(double BodyYaw,double TravelYaw){
 if(!std::isfinite(BodyYaw)||!std::isfinite(TravelYaw))return 0;
 const double Error=std::abs(std::remainder(TravelYaw-BodyYaw,360.));
 if(Error>=90.)return 0;
 // Turn before stepping into a new corridor. Captured forward walking must
 // not run at full speed sideways while the body catches up with the gaze.
 const double Forward=std::cos(Error*3.14159265358979323846/180.);
 return Forward*Forward*Forward*Forward;
}
inline double AuthoredWalkRate(double PlanarSpeed,double ReferenceSpeed=140.){
 if(!std::isfinite(PlanarSpeed)||PlanarSpeed<=0||!std::isfinite(ReferenceSpeed)||ReferenceSpeed<=0)return 0;
 return std::clamp(PlanarSpeed/ReferenceSpeed,0.,1.2);
}
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
WALK_RATE='FMath::Clamp(Speed/140.f,.1f,1.2f)'
MEASURED_WALK_RATE='float(Sub01FirstPersonMotion::AuthoredWalkRate(Speed))'
LIVE_MOVE='AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f));'
ALIGNED_MOVE='AddMovementInput(Delta/Distance,FMath::Clamp(Distance/45.f,.15f,1.f)*float(Sub01FirstPersonMotion::HeadingWalkScale(GetActorRotation().Yaw,Delta.Rotation().Yaw)));'

def stage(module):
    (Path(module)/'Sub01FirstPersonMotionPolicy.h').write_text(POLICY)

def install(header,cpp):
    include='#include "Sub01HomeLab.h"'
    method='void ASub01HomeCharacter::UpdateLiveHome(float Dt){'
    if cpp.count(include)!=1 or cpp.count(method)!=1 or cpp.count(SWAY)!=1 or cpp.count(WALK_RATE)!=1:
        raise ValueError('Unique original native Live look and body-sway hooks required')
    start=cpp.index(method);end=cpp.index('\n}',start)+2
    live=cpp[start:end]
    if live.count(SNAP)!=1 or live.count(LIVE_MOVE)!=1:
        raise ValueError('Unique Live gaze hook required; diagnostic route is separate')
    cpp=cpp[:start]+live.replace(SNAP,SMOOTH,1).replace(LIVE_MOVE,ALIGNED_MOVE,1)+cpp[end:]
    cpp=cpp.replace(include,include+'\n#include "Sub01FirstPersonMotionPolicy.h"',1)
    return header,cpp.replace(SWAY,AUTHORED_ONLY,1).replace(WALK_RATE,MEASURED_WALK_RATE,1)
