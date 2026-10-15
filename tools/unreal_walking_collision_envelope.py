"""Explicit private review of a physical envelope enclosing the measured eye.

The existing 16cm capsule does not enclose the actual eye 22.5cm ahead of its
axis. A 25cm capsule contains that eye plus a 2.5cm near-plane guard. This is
not enabled automatically: actual stairs/doors/device routes must be retested.
"""
from pathlib import Path

POLICY=r'''#pragma once
#include <cmath>
namespace Sub01WalkingEnvelope {
inline bool ContainsEye(double X,double Y,double Z,double Radius,double HalfHeight,double NearPlane,double Guard=2.5){
 if(!std::isfinite(X)||!std::isfinite(Y)||!std::isfinite(Z)||!std::isfinite(Radius)||!std::isfinite(HalfHeight)||!std::isfinite(NearPlane)||!std::isfinite(Guard)||Radius<=0||HalfHeight<Radius||NearPlane<=0||NearPlane>1||Guard<2.5)return false;
 const double DZ=std::fmax(0.,std::fabs(Z)-(HalfHeight-Radius));
 return std::sqrt(X*X+Y*Y+DZ*DZ)+Guard<=Radius;
}
}
'''
FIELDS=r'''
 UFUNCTION(Exec) void InspectWalkingEnvelope();
 UFUNCTION(Exec) void ReviewWalkingEnvelope();
'''
METHODS=r'''
void ASub01HomeCharacter::InspectWalkingEnvelope(){
 auto* C=GetCapsuleComponent();if(!C)return;
 UE_LOG(LogTemp,Display,TEXT("SUB01_WALKING_ENVELOPE_INSPECT radius=%.6f halfHeight=%.6f actualNearClip=%.6f eyeOffset=%s pawn=%s; route acceptance separate"),C->GetScaledCapsuleRadius(),C->GetScaledCapsuleHalfHeight(),GNearClippingPlane,*WalkingCameraOffset.ToString(),*GetActorLocation().ToString());
}
void ASub01HomeCharacter::ReviewWalkingEnvelope(){
 auto Refuse=[](const TCHAR* Why){UE_LOG(LogTemp,Warning,TEXT("SUB01_WALKING_ENVELOPE_REFUSED %s"),Why);};
 auto* C=GetCapsuleComponent();const FVector ReviewedEye(22.208150954150312,3.5805613130220593,64.61018215994386);
 if(PrivateViewMode!=EPrivateViewMode::Manual||LiveHome||HandsDiagnostic||HandsPosture!=TEXT("Walk")||NativeSeatVerified||MinecraftFocused||(PCBridge&&PCBridge->HasOperatorFocus())||!GetCharacterMovement()->IsMovingOnGround()||GetVelocity().Size()>1){Refuse(TEXT("stationary grounded manual Walk required"));return;}
 if(!C||!C->GetComponentScale().Equals(FVector::OneVector,.00001f)||!FMath::IsNearlyEqual(C->GetUnscaledCapsuleHalfHeight(),91.f,.001f)||(!FMath::IsNearlyEqual(C->GetUnscaledCapsuleRadius(),16.f,.001f)&&!FMath::IsNearlyEqual(C->GetUnscaledCapsuleRadius(),25.f,.001f))||!WalkingCameraOffset.Equals(ReviewedEye,.001f)||!FMath::IsFinite(GNearClippingPlane)||GNearClippingPlane<1){Refuse(TEXT("reviewed eye and original physical capsule required"));return;}
 if(!Sub01WalkingEnvelope::ContainsEye(WalkingCameraOffset.X,WalkingCameraOffset.Y,WalkingCameraOffset.Z,25,91,1)){Refuse(TEXT("candidate does not contain eye/near-plane guard"));return;}
 FCollisionQueryParams Q(SCENE_QUERY_STAT(Sub01WalkingEnvelope),false);Q.AddIgnoredActor(this);
 if(GetWorld()->OverlapBlockingTestByChannel(GetActorLocation(),GetActorQuat(),ECC_Pawn,FCollisionShape::MakeCapsule(25.f,91.f),Q)){Refuse(TEXT("candidate overlaps actual blocking world; physically move to clear space first"));return;}
 const FVector Before=GetActorLocation();const float OldRadius=C->GetUnscaledCapsuleRadius(),OldNear=GNearClippingPlane;
 C->SetCapsuleSize(25.f,91.f,true);
 if(!FMath::IsNearlyEqual(C->GetScaledCapsuleRadius(),25.f,.001f)||!GetActorLocation().Equals(Before,.00001f)){C->SetCapsuleSize(OldRadius,91.f,true);Refuse(TEXT("physical readback changed unexpectedly"));return;}
 SetNearClipPlaneGlobals(1.f);
 UE_LOG(LogTemp,Warning,TEXT("SUB01_WALKING_ENVELOPE_REVIEW oldRadius=%.6f oldNear=%.6f radius=%.6f actualNear=%.6f pawnUnchanged=true; actual route/door/device retest REQUIRED"),OldRadius,OldNear,C->GetScaledCapsuleRadius(),GNearClippingPlane);
}
'''


def stage(module):
    (Path(module)/'Sub01WalkingEnvelopePolicy.h').write_text(POLICY)


def install(header,cpp):
    declaration=' void Forward(float Value);'
    include='#include "Sub01HomeLab.h"'
    if header.count(declaration)!=1 or cpp.count(include)!=1 or 'ReviewWalkingEnvelope(' in header:
        raise ValueError('Unique physical walking-envelope integration required')
    includes='\n#include "CoreGlobals.h"\n#include "RenderCore.h"\n#include "Sub01WalkingEnvelopePolicy.h"'
    return header.replace(declaration,FIELDS+declaration,1),cpp.replace(include,include+includes,1)+METHODS
