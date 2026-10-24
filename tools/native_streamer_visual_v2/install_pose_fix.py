"""Pose fix ON TOP of the stream pass and the mouth layer: the visual QA of build v19 (docs/streamer/VISUAL-QA-20261023.md).

    python tools/native_streamer_visual_v2/install_pose_fix.py --source <dir> [--dry-run]

Requires the stream pass (install_stream_pass.py) and the mouth layer (install_mouth.py) in the four files; cam2
(install_cam2.py) may come before or after. Refused when `// SUB01_STREAMER_VISUAL_V2_POSEFIX` is already present or any
anchor is not found exactly once. Same atomic writes, line endings and JSON report as the other layers.

1. Body-frame offsets (QA bug 3). On this Mixamo import FRotator(Pitch) on Spine1/Spine2/Head turns the bone about its long
   (twist) axis: the sit-up layer twisted the torso, the nod was a head shake, gaze pitch turned the head. The offsets are now
   applied about HIS axes, read from the pose every evaluation: lateral = right thigh - left thigh (flattened; else the
   import's -X), up = component Z, forward = lateral x up; per bone  local' = parent^-1 * Delta * parent * local  (the bone
   turns in component space about its own pivot). Spine channel: the lean (posture_lean + typing_lean, FORWARD degrees,
   negative = sit up) spread over Spine/Spine1/Spine2 by LEAN_WEIGHTS with a gain adapted every frame so the pelvis-to-head
   line turns by the commanded angle (Kimi's acceptance: +10 -> 10 +- 1 deg); breathing (pitch) on Spine1/Spine2. Head
   channel: pitch (gaze, nod, talking cadence, posture_head, typing_head, the mouth emphasis; nose UP positive) and yaw
   (gaze, sway, `head_yaw_deg`; to his RIGHT positive) spread over Neck/Head by HEAD_WEIGHTS. After this build the live
   tuning's posture_head_deg = 14 (a yaw stop-gap) must go back to 0 and its value to `head_yaw_deg`.
2. Loop seam (QA bug 2): within `loop_fade_s` (default LOOP_FADE_SECONDS) of a desk loop's end, Previous keeps playing the end
   while Current restarts at 0, through the same Previous/Current crossfade a state change uses, faded over that time (the
   7-9 cm head pop every ~5.5 s becomes a blend). Counted (`loop_seams`).
3. Face camera aims ONCE (QA bug 7): the Head bone is tracked every tick while v2 runs (any camera) as an exponential mean
   (time constant FACE_MEAN_SECONDS); the first selection aims at once from it (>= FACE_MIN_SECONDS of samples, else after 2 s)
   and the aim is kept across camera switches; only a tuning change re-aims (after a fresh mean), easing from the old aim
   over 1 s when the webcam is on screen (no cut).
4. Seat yaw (QA bug 8): `seat_yaw_deg` turns him about the seated pelvis (R9's pelvis, published by the proxy) on the mesh
   component, composed between the clip offset and the pull-back; the chair parts turn with him about the same vertical.
5. Chair fit (QA bug 4): with `chair_fit` 1 (default) the chair parts behind and above the pelvis (not the armrests) are the
   backrest; their bounds' front face along his facing is compared with the sacrum (pelvis bone - facing * `sacrum_back_cm`)
   and the chair is moved along the facing until the backrest stands `backrest_gap_cm` (default 1; recipe 0-2) behind it:
   passes 1 s apart after the seat settles, at most CHAIR_FIT_PASSES per tuning change, clamped to +-CHAIR_FIT_MAX_CM. The
   backrest's front is first TRACED (LineTraceComponent on each chair part at sacrum height, from in front of him backwards;
   the bounds overestimate a reclined backrest) and the chair glides there at CHAIR_FIT_SPEED_CM_S (no jump on stream).
   Logged as `SUB01_STREAMER_VISUAL_CHAIR_FIT`; receipt `backrest_gap_cm`, `chair_fit_cm`, `backrest`.
Log `SUB01_STREAMER_VISUAL_POSE leanCmd= leanMeasured= gain= headPitch= headYaw= seatYaw= loopSeams= bodyRight=` every 10 s;
receipt `lean_measured_deg`, `lean_gain`, `head_yaw_deg`, `seat_yaw_deg`, `loop_seams`, `face_aim_mean_s`.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_streampass', _HERE / 'install_stream_pass.py')
streampass = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(streampass)
_MSPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_mouth', _HERE / 'install_mouth.py')
mouth = importlib.util.module_from_spec(_MSPEC)
_MSPEC.loader.exec_module(mouth)
seatfix, v2, Refused = streampass.seatfix, streampass.v2, streampass.Refused
_f, _line = streampass._f, streampass._line


def _d(value: float) -> str:
    """A C++ double literal: 3 -> 3., 0.5 -> 0.5 (FMath::Clamp needs one type)."""
    text = f'{value:g}'
    return text if '.' in text or 'e' in text else text + '.'


MARKER = '// SUB01_STREAMER_VISUAL_V2_POSEFIX'
FILES = dict(v2.FILES)
LEAN_WEIGHTS = (0.5, 0.3, 0.2)            # Spine, Spine1, Spine2 (lower bones turn the pelvis-to-head line more)
HEAD_WEIGHTS = (0.4, 0.6)                 # Neck, Head
LEAN_GAIN_LIMITS, LEAN_GAIN_TAU_S, LEAN_MEASURE_MIN_DEG = (0.5, 3.0), 0.08, 2.0  # the gain converges with a 0.08 s time constant at any frame rate
MOUTH_HEAD_DEG = 2.0                      # the mouth layer's head emphasis, now a nose-DOWN pitch in the head channel
LOOP_FADE_SECONDS = 0.5
FACE_MEAN_SECONDS, FACE_MIN_SECONDS = 5.0, 2.0
CHAIR_FIT, SACRUM_BACK_CM, BACKREST_GAP_CM = 1, 11.0, 1.0
CHAIR_FIT_PASSES, CHAIR_FIT_MAX_CM, CHAIR_FIT_DEADBAND_CM = 4, 25.0, 0.5
CHAIR_FIT_SPEED_CM_S = 60.0               # the chair glides to its fitted place (Kimi: no instantaneous jumps on stream)
SACRUM_UP_CM, TRACE_FRONT_CM, TRACE_BACK_CM = 6.0, 30.0, 40.0  # the probe: sacrum height above the Hips bone, traced from in front of him backwards
LEAN_ACHIEVED_MIN_DEG = 0.25             # the gain adapts only on a measurable achievement (no chatter)
BACKREST_MIN_BEHIND_CM, BACKREST_MIN_ABOVE_CM, BACKREST_MAX_SIDE_CM = 3.0, 15.0, 20.0
TUNING_LIMITS = {'head_yaw_deg': (-30, 30), 'seat_yaw_deg': (-30, 30), 'loop_fade_s': (0, 1), 'chair_fit': (0, 1), 'sacrum_back_cm': (5, 20),
                 'backrest_gap_cm': (-2, 6)}
TUNING_FIELDS = {'head_yaw_deg': 'StreamerVisualHeadYawDeg', 'seat_yaw_deg': 'StreamerVisualSeatYawDeg', 'loop_fade_s': 'StreamerVisualLoopFadeSeconds',
                 'chair_fit': 'StreamerVisualChairFit', 'sacrum_back_cm': 'StreamerVisualSacrumBackCm', 'backrest_gap_cm': 'StreamerVisualBackrestGapCm'}
assert set(TUNING_FIELDS) == set(TUNING_LIMITS)

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_STREAM_END = ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS END\n'
HEADER_FIELDS = f''' // SUB01_STREAMER_VISUAL_V2_POSEFIX BEGIN (tools/native_streamer_visual_v2/install_pose_fix.py): head yaw, seat yaw, chair fit, the face
 // camera's background head mean, pose log. The body-frame offsets themselves live in the anim proxy.
 void FitStreamerVisualChair(double Now,float Dt,class USub01HomeHandsInstance* Anim);void LogStreamerVisualPose(double Now,class USub01HomeHandsInstance* Anim);
 float StreamerVisualHeadYawDeg=0,StreamerVisualHeadYawApplied=0,StreamerVisualSeatYawDeg=0,StreamerVisualLoopFadeSeconds={_f(LOOP_FADE_SECONDS)};
 float StreamerVisualChairFit={_f(CHAIR_FIT)},StreamerVisualSacrumBackCm={_f(SACRUM_BACK_CM)},StreamerVisualBackrestGapCm={_f(BACKREST_GAP_CM)};
 float StreamerVisualChairYaw=0,StreamerVisualChairYawApplied=0,StreamerVisualBackrestGapMeasured=-99,StreamerVisualChairFitCm=0;int32 StreamerVisualChairFitPasses=0;
 double StreamerVisualChairFitAt=0,StreamerVisualPoseLogAt=0,StreamerVisualFaceMeanSeconds=0;float StreamerVisualFaceReaim=1;FVector StreamerVisualFacePrevLocation=FVector::ZeroVector;FRotator StreamerVisualFacePrevLook=FRotator::ZeroRotator;
 FVector StreamerVisualChairFitWorld=FVector::ZeroVector,StreamerVisualChairFitShown=FVector::ZeroVector,StreamerVisualChairPivotWorld=FVector::ZeroVector;FString StreamerVisualBackrestName;TArray<FQuat> StreamerVisualDeskPropRotations;
 // SUB01_STREAMER_VISUAL_V2_POSEFIX END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
STREAM_METHODS_BEGIN = '// SUB01_STREAMER_VISUAL_V2_STREAMPASS BEGIN (tools/native_streamer_visual_v2/install_stream_pass.py)\n'
CPP_METHODS = f'''// SUB01_STREAMER_VISUAL_V2_POSEFIX BEGIN (tools/native_streamer_visual_v2/install_pose_fix.py)
void ASub01HomeCharacter::FitStreamerVisualChair(double Now,float Dt,USub01HomeHandsInstance* Anim){{
 // The backrest {BACKREST_GAP_CM:g} cm (backrest_gap_cm) behind the sacrum: after the seat settles, the chair parts behind ({BACKREST_MIN_BEHIND_CM:g} cm) and reaching
 // above ({BACKREST_MIN_ABOVE_CM:g} cm) the pelvis, within {BACKREST_MAX_SIDE_CM:g} cm sideways (not the armrests), are the backrest; the front-most point of their bounds along his facing
 // is compared with the sacrum (pelvis bone - facing * sacrum_back_cm) and the chair moves along the facing by the difference: passes
 // 1 s apart until within {CHAIR_FIT_DEADBAND_CM:g} cm, at most {CHAIR_FIT_PASSES} per tuning change, clamped to +-{CHAIR_FIT_MAX_CM:g} cm. chair_fit 0 = the plain pull-back.
 {{const FVector Step=StreamerVisualChairFitWorld-StreamerVisualChairFitShown;const double Max={CHAIR_FIT_SPEED_CM_S:g}*double(Dt); // the chair glides ({CHAIR_FIT_SPEED_CM_S:g} cm/s), never jumps
  StreamerVisualChairFitShown=Step.Size()<=Max?StreamerVisualChairFitWorld:StreamerVisualChairFitShown+Step.GetSafeNormal()*Max;}}
 if(StreamerVisualChairFit<=0){{StreamerVisualChairFitWorld=FVector::ZeroVector;StreamerVisualChairFitCm=0;return;}}
 if(!StreamerVisualChairFitShown.Equals(StreamerVisualChairFitWorld,.01))return; // measure only where the chair really is
 if(!(StreamerVisualSchemaVersion==2&&StreamerVisualSeatHas&&Anim&&Anim->StreamerVisualSeatSettled&&Anim->StreamerVisualPelvisBone>=0&&FirstPersonBody&&StreamerVisualDeskPropsEnabled>0&&StreamerVisualDeskPropsScanned))return;
 if(StreamerVisualChairFitPasses>={CHAIR_FIT_PASSES}||Now<StreamerVisualChairFitAt)return;StreamerVisualChairFitAt=Now+1;++StreamerVisualChairFitPasses;
 const FQuat SeatTurn(FVector::UpVector,FMath::DegreesToRadians(double(StreamerVisualSeatYawDeg)));
 const FVector Facing=SeatTurn.RotateVector(StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(StreamerVisualFacingLocal)*FVector(1,1,0)).GetSafeNormal(),Side=FVector::CrossProduct(FVector::UpVector,Facing);
 const FVector Pelvis=FirstPersonBody->GetBoneTransform(Anim->StreamerVisualPelvisBone).GetTranslation(),Sacrum=Pelvis-Facing*double(StreamerVisualSacrumBackCm);
 // first choice: the backrest's real surface, traced at sacrum height from in front of him backwards (chair components only); else the bounds
 const FVector Probe=Sacrum+FVector(0,0,{SACRUM_UP_CM:g});double Front=-1e9,Traced=-1e9;int32 Parts=0;FString Name,TracedName;
 for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){{AActor* A=StreamerVisualDeskProps[I].Get();if(!A||!StreamerVisualDeskPropIsChair.IsValidIndex(I)||!StreamerVisualDeskPropIsChair[I])continue;
  FVector Origin=FVector::ZeroVector,Extent=FVector::ZeroVector;A->GetActorBounds(false,Origin,Extent);const FVector Rel=Origin-Pelvis;
  if(FVector::DotProduct(Rel,Facing)>-{BACKREST_MIN_BEHIND_CM:g}||Origin.Z+Extent.Z<Pelvis.Z+{BACKREST_MIN_ABOVE_CM:g}||FMath::Abs(FVector::DotProduct(Rel,Side))>{BACKREST_MAX_SIDE_CM:g})continue; // not the backrest (seat, legs, armrests)
  if(UPrimitiveComponent* Prim=A->FindComponentByClass<UPrimitiveComponent>()){{FHitResult Hit;const FCollisionQueryParams Params(FName(TEXT("Sub01ChairFit")),true); // its real surface at sacrum height
   if(Prim->LineTraceComponent(Hit,Probe+Facing*{TRACE_FRONT_CM:g},Probe-Facing*{TRACE_BACK_CM:g},Params)){{const double At=FVector::DotProduct(FVector(Hit.ImpactPoint),Facing);if(At>Traced){{Traced=At;TracedName=A->GetName();}}}}}}
  const double F=FVector::DotProduct(Origin,Facing)+FMath::Abs(Extent.X*Facing.X)+FMath::Abs(Extent.Y*Facing.Y); // the box's front-most point along the facing
  if(F>Front){{Front=F;Name=A->GetName();}}++Parts;
 }}
 const bool ByTrace=Traced>-1e8;if(ByTrace){{Front=Traced;Name=TracedName;}}
 if(!Parts){{StreamerVisualChairFitPasses={CHAIR_FIT_PASSES};StreamerVisualBackrestName=TEXT("none");
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CHAIR_FIT no backrest among the chair parts (behind and above the pelvis %s); the chair keeps the pull-back"),*Pelvis.ToString());return;}}
 const double Gap=FVector::DotProduct(Sacrum,Facing)-Front,Move=Gap-double(StreamerVisualBackrestGapCm); // gap > 0: the backrest stands behind the sacrum; move > 0: the chair comes forward
 StreamerVisualBackrestGapMeasured=float(Gap);StreamerVisualBackrestName=Name;
 if(FMath::Abs(Move)>{CHAIR_FIT_DEADBAND_CM:g}){{const double Along=FMath::Clamp(FVector::DotProduct(StreamerVisualChairFitWorld,Facing)+Move,-{_d(CHAIR_FIT_MAX_CM)},{_d(CHAIR_FIT_MAX_CM)});StreamerVisualChairFitWorld=Facing*Along;}}
 else StreamerVisualChairFitPasses={CHAIR_FIT_PASSES}; // fitted
 StreamerVisualChairFitCm=float(FVector::DotProduct(StreamerVisualChairFitWorld,Facing));
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CHAIR_FIT pass=%d method=%s backrest=%s parts=%d sacrum=%s backrestFront=%.1f gapCm=%.1f targetCm=%.1f chairFitCm=%.1f"),StreamerVisualChairFitPasses,ByTrace?TEXT("trace"):TEXT("bounds"),*Name,Parts,*Sacrum.ToString(),Front,Gap,StreamerVisualBackrestGapCm,StreamerVisualChairFitCm);
}}
void ASub01HomeCharacter::LogStreamerVisualPose(double Now,USub01HomeHandsInstance* Anim){{
 if(!Anim||StreamerVisualSchemaVersion!=2||Now<StreamerVisualPoseLogAt)return;StreamerVisualPoseLogAt=Now+10;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_POSE leanCmd=%.1f leanMeasured=%.1f gain=%.2f headPitch=%.1f headYaw=%.1f seatYaw=%.1f loopSeams=%d loopFade=%.2f bodyRight=%s faceMeanS=%.1f backrestGapCm=%.1f"),
  Anim->StreamerVisualLeanDeg,Anim->StreamerVisualLeanMeasuredDeg,Anim->StreamerVisualLeanGain,Anim->StreamerVisualHeadOffset.Pitch,Anim->StreamerVisualHeadOffset.Yaw,StreamerVisualSeatYawDeg,Anim->StreamerVisualLoopSeams,StreamerVisualLoopFadeSeconds,
  *Anim->StreamerVisualBodyRight.ToString(),StreamerVisualFaceMeanSeconds,StreamerVisualBackrestGapMeasured);
}}
// SUB01_STREAMER_VISUAL_V2_POSEFIX END
'''
TUNING_ANCHOR = _line(streampass.TUNING_STREAM, ' Field(TEXT("typing_lean_deg")')
TUNING_POSE = TUNING_ANCHOR + ' ' + ''.join(f'Field(TEXT("{k}"),{TUNING_FIELDS[k]},{lo},{hi});' for k, (lo, hi) in TUNING_LIMITS.items()) + ' // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
TUNING_POLL = _line(seatfix.APPLY_SEAT, '  if(StreamerVisualSchemaVersion==2&&Now>=StreamerVisualFaceTuningAt)')
TUNING_POLL_POSE = TUNING_POLL.replace('if(ReadStreamerVisualFaceTuning())StreamerVisualTuningChanged=true;',
                                       'if(ReadStreamerVisualFaceTuning()){StreamerVisualTuningChanged=true;StreamerVisualChairFitPasses=0;} /* SUB01_STREAMER_VISUAL_V2_POSEFIX: a tuning change re-fits the chair */')
assert TUNING_POLL_POSE != TUNING_POLL
SPINE_SEND = _line(seatfix.SPINE_POSTURE, '  Anim->StreamerVisualSpine1Offset=')
SPINE_SEND_POSE = ('  // SUB01_STREAMER_VISUAL_V2_POSEFIX: breathing stays on the Spine1/Spine2 channel, the lean goes to its own channel (forward degrees, spread over the\n'
                   '  // spine with a measured gain in the proxy); head pitch (nose up) and yaw (to his right, head_yaw_deg eased like the posture) about HIS axes\n'
                   '  Anim->StreamerVisualSpine1Offset=FRotator(.6*FMath::Sin(W),0,0);Anim->StreamerVisualSpine2Offset=FRotator(.6*FMath::Sin(W-1.1),0,0);Anim->StreamerVisualLeanDeg=StreamerVisualPostureLeanApplied;Anim->StreamerVisualHeadOffset.Pitch+=StreamerVisualPostureHeadApplied;\n'
                   f'  StreamerVisualHeadYawApplied+=FMath::Clamp(StreamerVisualHeadYawDeg-StreamerVisualHeadYawApplied,-{seatfix.POSTURE_RATE_DEG_PER_S:g}.f*Dt,{seatfix.POSTURE_RATE_DEG_PER_S:g}.f*Dt);Anim->StreamerVisualHeadOffset.Yaw+=StreamerVisualHeadYawApplied;Anim->StreamerVisualLoopFadeSeconds=StreamerVisualLoopFadeSeconds;\n')
SEAT_LINE = _line(seatfix.APPLY_SEAT, '  FTransform Seat=FTransform::Identity;')
SEAT_LINE_POSE = SEAT_LINE.replace('if(SeatValid)Seat=Anim->StreamerVisualSeatOffset*FTransform(FQuat::Identity,PullLocal);',
                                   'if(SeatValid){const FQuat SeatTurn(FVector::UpVector,FMath::DegreesToRadians(double(StreamerVisualSeatYawDeg)));const FVector Pivot=Anim->StreamerVisualSeatPivot; // SUB01_STREAMER_VISUAL_V2_POSEFIX: seat_yaw_deg about the seated pelvis\n'
                                   '   Seat=Anim->StreamerVisualSeatOffset*FTransform(SeatTurn,Pivot-SeatTurn.RotateVector(Pivot))*FTransform(FQuat::Identity,PullLocal);}')
assert SEAT_LINE_POSE != SEAT_LINE
CHAIR_DELTA = '   StreamerVisualChairDelta=SeatValid&&StreamerVisualDeskPropsEnabled>0?StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(ChairLocal):FVector::ZeroVector;}\n'
CHAIR_DELTA_POSE = ('   StreamerVisualChairDelta=SeatValid&&StreamerVisualDeskPropsEnabled>0?StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(ChairLocal)+StreamerVisualChairFitShown:FVector::ZeroVector; // + SUB01_STREAMER_VISUAL_V2_POSEFIX: the chair fit (eased)\n'
                    '   StreamerVisualChairYaw=SeatValid&&StreamerVisualDeskPropsEnabled>0?StreamerVisualSeatYawDeg:0.f;if(SeatValid)StreamerVisualChairPivotWorld=StreamerVisualBodyAuthoredWorld.TransformPosition(Anim->StreamerVisualSeatPivot);}\n')
MOVE_ANCHOR = streampass.MOVE_STREAM
MOVE_POSE = (' for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){AActor* A=StreamerVisualDeskProps[I].Get();if(!A||!StreamerVisualDeskPropOrigins.IsValidIndex(I))continue;'
             'const bool Chair=StreamerVisualDeskPropIsChair.IsValidIndex(I)&&StreamerVisualDeskPropIsChair[I];\n'
             '  if(Chair&&StreamerVisualDeskPropRotations.IsValidIndex(I)){const FQuat Yaw(FVector::UpVector,FMath::DegreesToRadians(double(StreamerVisualChairYaw))); // SUB01_STREAMER_VISUAL_V2_POSEFIX: the chair turns with him about the seat\n'
             '   A->SetActorLocationAndRotation(StreamerVisualChairPivotWorld+Yaw.RotateVector(StreamerVisualDeskPropOrigins[I]-StreamerVisualChairPivotWorld)+StreamerVisualChairDelta,Yaw*StreamerVisualDeskPropRotations[I],false,nullptr,ETeleportType::TeleportPhysics);}\n'
             '  else A->SetActorLocation(StreamerVisualDeskPropOrigins[I]+(Chair?StreamerVisualChairDelta:WorldDelta),false,nullptr,ETeleportType::TeleportPhysics);++Moved;} // SUB01_STREAMER_VISUAL_V2_STREAMPASS: chair parts by the chair delta\n')
GATE_ANCHOR = streampass.GATE_STREAM
GATE_POSE = GATE_ANCHOR.replace('StreamerVisualChairDelta.Equals(StreamerVisualChairDeltaApplied,.01))return;StreamerVisualChairDeltaApplied=StreamerVisualChairDelta;',
                                'StreamerVisualChairDelta.Equals(StreamerVisualChairDeltaApplied,.01)&&StreamerVisualChairYaw==StreamerVisualChairYawApplied)return;StreamerVisualChairDeltaApplied=StreamerVisualChairDelta;StreamerVisualChairYawApplied=StreamerVisualChairYaw; /* SUB01_STREAMER_VISUAL_V2_POSEFIX */')
assert GATE_POSE != GATE_ANCHOR
SCAN_ADD_ANCHOR = streampass.SCAN_ADD_STREAM
SCAN_ADD_POSE = SCAN_ADD_ANCHOR.rstrip('\n') + ' StreamerVisualDeskPropRotations.Add(A->GetActorQuat()); // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
SCAN_RESET_ANCHOR = next(new for key, anchor, new in streampass.EDITS if anchor == streampass.SCAN_RESET)
SCAN_RESET_POSE = SCAN_RESET_ANCHOR + ' StreamerVisualDeskPropRotations.Reset(); // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
MOUSE_ADD_ANCHOR = _line(streampass.CPP_METHODS, '  if(Mouse){StreamerVisualMouseActor=A;')
MOUSE_ADD_POSE = MOUSE_ADD_ANCHOR.replace('StreamerVisualDeskPropIsChair.Add(false);', 'StreamerVisualDeskPropIsChair.Add(false);StreamerVisualDeskPropRotations.Add(A->GetActorQuat());')
assert MOUSE_ADD_POSE != MOUSE_ADD_ANCHOR
TICK_ANCHOR = streampass.TICK_STREAM
TICK_POSE = TICK_ANCHOR + '  FitStreamerVisualChair(Now,Dt,Anim);LogStreamerVisualPose(Now,Anim); // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
RECEIPT_ANCHOR = '   Receipt->SetNumberField(TEXT("hide_slot"),StreamerVisualHideSlotApplied);Receipt->SetNumberField(TEXT("forced_lod"),StreamerVisualForcedLodApplied);\n'
assert RECEIPT_ANCHOR in streampass.RECEIPT_STREAM
RECEIPT_POSE = (RECEIPT_ANCHOR +
                '   Receipt->SetNumberField(TEXT("lean_measured_deg"),V2Anim?V2Anim->StreamerVisualLeanMeasuredDeg:0.f);Receipt->SetNumberField(TEXT("lean_gain"),V2Anim?V2Anim->StreamerVisualLeanGain:0.f);Receipt->SetNumberField(TEXT("head_yaw_deg"),StreamerVisualHeadYawApplied);'
                'Receipt->SetNumberField(TEXT("seat_yaw_deg"),StreamerVisualSeatYawDeg);Receipt->SetNumberField(TEXT("loop_seams"),V2Anim?V2Anim->StreamerVisualLoopSeams:0); // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
                '   Receipt->SetNumberField(TEXT("backrest_gap_cm"),StreamerVisualBackrestGapMeasured);Receipt->SetNumberField(TEXT("chair_fit_cm"),StreamerVisualChairFitCm);Receipt->SetStringField(TEXT("backrest"),StreamerVisualBackrestName);Receipt->SetNumberField(TEXT("face_aim_mean_s"),StreamerVisualFaceMeanSeconds);\n')
FACE_OLD = seatfix.NEW_FACE_CAMERA
FACE_NEW = f'''void ASub01HomeCharacter::ApplyStreamerVisualFaceCamera(float Dt){{
 // SUB01_STREAMER_VISUAL_V2_POSEFIX (tools/native_streamer_visual_v2/install_pose_fix.py): the webcam ON the monitor aims ONCE and keeps the aim across
 // camera switches; only a tuning change re-aims. The Head bone is tracked every tick while v2 runs (any camera) as an exponential mean
 // (time constant {FACE_MEAN_SECONDS:g} s: the loops sway the head ~6 cm), so a selection aims at once from it (>= {FACE_MIN_SECONDS:g} s of samples, else after 2 s).
 // Placement as the seat fix: monitor bounds centre + up, towards him, to his right; FOV from the tuning. 1 s eased layer over the v2 blend.
 const double Now=FPlatformTime::Seconds();const bool Face=StreamerVisualCameraTarget==TEXT("face");
 if(Face&&StreamerVisualFaceSelectedAt<0)StreamerVisualFaceSelectedAt=Now;
 if(StreamerVisualTuningChanged){{StreamerVisualTuningChanged=false;StreamerVisualFaceAimed=false;StreamerVisualFaceHeadCount=0;StreamerVisualFaceMeanSeconds=0;if(Face)StreamerVisualFaceSelectedAt=Now;}} // a fresh mean, then a new aim
 const FVector BodyAt=FirstPersonBody?FirstPersonBody->GetComponentLocation():FVector(214,-289,6.19);
 const bool HasHead=FirstPersonBody&&FirstPersonBody->GetBoneIndex(TEXT("Head"))!=INDEX_NONE;
 const FVector Head=HasHead?FirstPersonBody->GetBoneLocation(TEXT("Head")):FVector::ZeroVector;const bool HeadOk=HasHead&&!Head.ContainsNaN()&&FVector::Dist(Head,BodyAt)<=250;
 if(HeadOk&&StreamerVisualSchemaVersion==2&&StreamerVisualSeatHas){{const double K=1.-FMath::Exp(-double(Dt)/{FACE_MEAN_SECONDS:g}); // exact for any frame time
  StreamerVisualFaceHeadSum=StreamerVisualFaceHeadCount>0?StreamerVisualFaceHeadSum+(Head-StreamerVisualFaceHeadSum)*K:Head;++StreamerVisualFaceHeadCount;StreamerVisualFaceMeanSeconds+=Dt;}}
 if(Face&&!StreamerVisualFaceAimed&&(StreamerVisualFaceMeanSeconds>={FACE_MIN_SECONDS:g}||Now-StreamerVisualFaceSelectedAt>=2)){{
  const bool FromMean=StreamerVisualFaceHeadCount>0&&StreamerVisualFaceMeanSeconds>={FACE_MIN_SECONDS:g};const FVector Mean=FromMean?StreamerVisualFaceHeadSum:HeadOk?Head:BodyAt+FVector(0,0,120);
  StreamerVisualFaceAimSource=FromMean?TEXT("head_mean"):HeadOk?TEXT("head"):TEXT("body+120");
  const FVector Monitor({seatfix.MONITOR[0]},{seatfix.MONITOR[1]},{seatfix.MONITOR[2]});FVector Towards(Mean.X-Monitor.X,Mean.Y-Monitor.Y,0); // from the monitor towards him
  Towards=Towards.Size()>10?Towards.GetSafeNormal():FVector(0,1,0);const FVector Side=FVector::CrossProduct(FVector::UpVector,-Towards); // UE is left-handed: Up x (his facing) = his right
  if(StreamerVisualFaceAlpha>0){{StreamerVisualFacePrevLocation=StreamerVisualFaceLocation;StreamerVisualFacePrevLook=StreamerVisualFaceLook;StreamerVisualFaceReaim=0;}} // on screen: ease from the old aim
  StreamerVisualFaceLocation=Monitor+Towards*double(StreamerVisualFaceForwardCm)+Side*double(StreamerVisualFaceSideCm)+FVector(0,0,StreamerVisualFaceUpCm);
  StreamerVisualFaceAim=Mean-FVector(0,0,StreamerVisualFaceAimDropCm);
  StreamerVisualFaceLook=(StreamerVisualFaceAim-StreamerVisualFaceLocation).Rotation();StreamerVisualFaceAimed=true;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_FACE_CAMERA location=%s aim=%s headMean=%s meanSeconds=%.1f source=%s look=%s fov=%.1f upCm=%.1f forwardCm=%.1f sideCm=%.1f aimDropCm=%.1f tuningSequence=%.0f kept until the tuning changes"),*StreamerVisualFaceLocation.ToString(),*StreamerVisualFaceAim.ToString(),*Mean.ToString(),StreamerVisualFaceMeanSeconds,*StreamerVisualFaceAimSource,*StreamerVisualFaceLook.ToString(),StreamerVisualFaceFov,StreamerVisualFaceUpCm,StreamerVisualFaceForwardCm,StreamerVisualFaceSideCm,StreamerVisualFaceAimDropCm,StreamerVisualFaceTuningSequence);
 }}
 if(!Face)StreamerVisualFaceSelectedAt=-10; // the aim itself is kept
 const float Goal=Face?1.f:0.f;
 if(!ViewCamera||(Goal==0&&StreamerVisualFaceAlpha<=0))return; // spectator/monitor only: the v2 camera path alone, untouched
 if(Face&&!StreamerVisualFaceAimed)return; // no aim yet (the first selection, < {FACE_MIN_SECONDS:g} s of samples): the camera stays as the blend above left it
 StreamerVisualFaceAlpha=Goal>StreamerVisualFaceAlpha?FMath::Min(Goal,StreamerVisualFaceAlpha+Dt):FMath::Max(Goal,StreamerVisualFaceAlpha-Dt);
 if(StreamerVisualFaceAlpha<=0){{ // fade-out done: FOV back to 65; exact spectator pose when the base rests there (else the v2 block set it this tick)
  ViewCamera->SetFieldOfView(65.f);
  if(StreamerVisualCameraAlpha<=0){{ViewCamera->SetWorldLocationAndRotation(FVector(334,-209,151),StreamerVisualSpectatorLook);if(Controller)Controller->SetControlRotation(StreamerVisualSpectatorLook);}}
  return;
 }}
 StreamerVisualFaceReaim=FMath::Min(1.f,StreamerVisualFaceReaim+Dt);const float Reaim=FMath::SmoothStep(0.f,1.f,StreamerVisualFaceReaim);
 const FVector Location=FMath::Lerp(StreamerVisualFacePrevLocation,StreamerVisualFaceLocation,double(Reaim));const FQuat Look=FQuat::Slerp(StreamerVisualFacePrevLook.Quaternion(),StreamerVisualFaceLook.Quaternion(),double(Reaim));
 const float Base=FMath::SmoothStep(0.f,1.f,StreamerVisualCameraAlpha),Ease=FMath::SmoothStep(0.f,1.f,StreamerVisualFaceAlpha);
 const FVector Under=FMath::Lerp(FVector(334,-209,151),StreamerVisualMonitorLocation,double(Base));
 const FQuat UnderQ=FQuat::Slerp(StreamerVisualSpectatorLook.Quaternion(),StreamerVisualMonitorLook.Quaternion(),double(Base));
 const FRotator Rotation=FQuat::Slerp(UnderQ,Look,double(Ease)).Rotator();
 ViewCamera->SetWorldLocationAndRotation(FMath::Lerp(Under,Location,double(Ease)),Rotation);ViewCamera->SetFieldOfView(FMath::Lerp(65.f,StreamerVisualFaceFov,Ease));
 if(Controller)Controller->SetControlRotation(Rotation);
}}
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.h
HANDS_STREAM_END = ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS END\n'
HANDS_FIELDS = ''' // SUB01_STREAMER_VISUAL_V2_POSEFIX BEGIN (tools/native_streamer_visual_v2/install_pose_fix.py): body-frame lean, loop seam, published measurements.
 UPROPERTY(Transient) float StreamerVisualLeanDeg=0; // FORWARD lean of the trunk, degrees (negative = sit up), spread over the spine by the proxy
 UPROPERTY(Transient) float StreamerVisualLoopFadeSeconds=.5f; // crossfade of a desk loop's end into its start (0 = off)
 UPROPERTY(Transient) FVector StreamerVisualSeatPivot=FVector::ZeroVector; // published: R9's seated pelvis, component space (the seat yaw pivot)
 UPROPERTY(Transient) float StreamerVisualLeanMeasuredDeg=0; // published: the pelvis-to-head inclination change the lean produced
 UPROPERTY(Transient) float StreamerVisualLeanGain=1;
 UPROPERTY(Transient) int32 StreamerVisualLoopSeams=0;
 UPROPERTY(Transient) FVector StreamerVisualBodyRight=FVector::ZeroVector; // published: his right in component space (from the thighs)
 // SUB01_STREAMER_VISUAL_V2_POSEFIX END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.cpp
PROXY_STREAM_BEGIN = _line(streampass.PROXY_MEMBERS, ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS BEGIN')
PROXY_MEMBERS = f''' // SUB01_STREAMER_VISUAL_V2_POSEFIX BEGIN (tools/native_streamer_visual_v2/install_pose_fix.py): offsets about HIS axes, loop seam crossfade.
 // FRotator(Pitch) on these Mixamo bones turns them about their long (twist) axis; here every offset is a component-space rotation about
 // his lateral axis (pitch) or the vertical (yaw), applied per bone as local' = parent^-1 * Delta * parent * local (about the bone's pivot).
 int32 StreamerV2PoseBones[8]={{INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE}},StreamerV2PoseCount=-1; // Hips Spine Spine1 Spine2 Neck Head LeftUpLeg RightUpLeg
 const FReferenceSkeleton* StreamerV2PoseRef=nullptr;
 float StreamerV2Dt=1.f/60,StreamerV2LeanCmd=0,StreamerV2LeanGain=1,StreamerV2LeanMeasured=0,StreamerV2MouthPitch=0,StreamerV2LoopFadeSeconds={_f(LOOP_FADE_SECONDS)},StreamerV2SeamFade=.24f;
 bool StreamerV2SeamFading=false;int32 StreamerV2Seams=0;const UAnimSequenceBase* StreamerV2SeamSequence=nullptr;FVector StreamerV2BodyRight=FVector::ZeroVector;
 FVector StreamerV2RightInHips=FVector::ZeroVector,StreamerV2LastRight=FVector(-1,0,0); // the thigh line calibrated once into the Hips frame; the last valid axis
 void ResolveStreamerV2Pose(const FReferenceSkeleton& Ref){{
  if(StreamerV2PoseRef==&Ref&&StreamerV2PoseCount==Ref.GetNum())return;StreamerV2PoseRef=&Ref;StreamerV2PoseCount=Ref.GetNum();StreamerV2RightInHips=FVector::ZeroVector;
  static const TCHAR* const Names[8]={{TEXT("Hips"),TEXT("Spine"),TEXT("Spine1"),TEXT("Spine2"),TEXT("Neck"),TEXT("Head"),TEXT("LeftUpLeg"),TEXT("RightUpLeg")}};
  for(int32 K=0;K<8;++K){{int32 Index=Ref.FindBoneIndex(FName(Names[K]));for(int32 B=0;Index==INDEX_NONE&&B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(Names[K]))Index=B;StreamerV2PoseBones[K]=Index;}}
 }}
 FVector StreamerV2Right(const FCompactPose& Pose){{ // his right in component space: the thigh line (right - left, flattened) calibrated ONCE into the Hips
  // frame, then carried by the Hips rotation every frame (moving legs do not turn it); a bad frame keeps the last valid axis (else -X)
  FTransform H;if(!StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[0],H))return StreamerV2LastRight;
  if(StreamerV2RightInHips.IsNearlyZero()){{FTransform L,R;if(StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[6],L)&&StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[7],R)){{
   FVector D=R.GetTranslation()-L.GetTranslation();D.Z=0;if(D.Size()>5)StreamerV2RightInHips=H.GetRotation().Inverse().RotateVector(D.GetSafeNormal());}}}}
  if(!StreamerV2RightInHips.IsNearlyZero()){{FVector Right=H.GetRotation().RotateVector(StreamerV2RightInHips);Right.Z=0;if(Right.Size()>.5)StreamerV2LastRight=Right.GetSafeNormal();}}
  return StreamerV2LastRight;
 }}
 static void StreamerV2Turn(FCompactPose& Pose,int32 Bone,const FQuat& Delta){{ // the bone turns by Delta (component space) about its own pivot
  if(Bone==INDEX_NONE)return;const auto& Bones=Pose.GetBoneContainer();const int32 Parent=Bones.GetReferenceSkeleton().GetParentIndex(Bone);
  FTransform P=FTransform::Identity;if(Parent!=INDEX_NONE&&!StreamerV2ComponentTransform(Pose,Parent,P))return;
  const auto C=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(Bone));if(C.GetInt()<0)return;
  const FQuat Q=P.GetRotation();Pose[C].SetRotation((Q.Inverse()*Delta*Q*Pose[C].GetRotation()).GetNormalized());
 }}
 static double StreamerV2Incline(const FVector& PelvisToHead,const FVector& Forward){{return FMath::RadiansToDegrees(FMath::Atan2(FVector::DotProduct(PelvisToHead,Forward),PelvisToHead.Z));}}
 void ApplyStreamerV2Body(FPoseContext& Output){{ // spine channel: the lean spread over Spine/Spine1/Spine2 with a measured gain, then breathing on Spine1/Spine2
  auto& Pose=Output.Pose;ResolveStreamerV2Pose(Pose.GetBoneContainer().GetReferenceSkeleton());
  const FVector Right=StreamerV2Right(Pose),Forward=FVector::CrossProduct(Right,FVector::UpVector);StreamerV2BodyRight=Right; // a turn about Right by +a tips the trunk forward
  FTransform Pelvis,Head0,Head1;const bool Measure=FMath::Abs(StreamerV2LeanCmd)>={_f(LEAN_MEASURE_MIN_DEG)}&&StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[0],Pelvis)&&StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[5],Head0);
  static const double Weights[3]={{{LEAN_WEIGHTS[0]:g},{LEAN_WEIGHTS[1]:g},{LEAN_WEIGHTS[2]:g}}};
  for(int32 K=0;K<3;++K){{const double Deg=double(StreamerV2LeanCmd)*StreamerV2LeanGain*Weights[K];if(FMath::Abs(Deg)>1e-4)StreamerV2Turn(Pose,StreamerV2PoseBones[1+K],FQuat(Right,FMath::DegreesToRadians(Deg)));}}
  if(Measure&&StreamerV2ComponentTransform(Pose,StreamerV2PoseBones[5],Head1)){{ // the pelvis is below every turned bone: the line's change is the lean achieved
   const double Achieved=StreamerV2Incline(Head1.GetTranslation()-Pelvis.GetTranslation(),Forward)-StreamerV2Incline(Head0.GetTranslation()-Pelvis.GetTranslation(),Forward);StreamerV2LeanMeasured=float(Achieved);
   if(Achieved*StreamerV2LeanCmd>0&&FMath::Abs(Achieved)>={_d(LEAN_ACHIEVED_MIN_DEG)}){{const double Target=FMath::Clamp(double(StreamerV2LeanGain)*StreamerV2LeanCmd/Achieved,{_d(LEAN_GAIN_LIMITS[0])},{_d(LEAN_GAIN_LIMITS[1])});StreamerV2LeanGain+=float((Target-StreamerV2LeanGain)*(1.-FMath::Exp(-double(StreamerV2Dt)/{LEAN_GAIN_TAU_S:g})));}}
  }}else StreamerV2LeanMeasured=0;
  for(int32 K=0;K<2;++K)if(FMath::Abs(StreamerV2Spine[K].Pitch)>1e-4)StreamerV2Turn(Pose,StreamerV2PoseBones[2+K],FQuat(Right,FMath::DegreesToRadians(double(StreamerV2Spine[K].Pitch)))); // breathing
 }}
 void ApplyStreamerV2Head(FPoseContext& Output){{ // head channel: pitch (nose UP positive) about his lateral axis, yaw (to his RIGHT positive) about the vertical
  auto& Pose=Output.Pose;ResolveStreamerV2Pose(Pose.GetBoneContainer().GetReferenceSkeleton());const FVector Right=StreamerV2Right(Pose);StreamerV2BodyRight=Right;
  const double Pitch=double(StreamerVisualHeadOffset.Pitch)+StreamerV2MouthPitch,Yaw=double(StreamerVisualHeadOffset.Yaw);StreamerV2MouthPitch=0;
  const bool Neck=StreamerV2PoseBones[4]!=INDEX_NONE;static const double Weights[2]={{{HEAD_WEIGHTS[0]:g},{HEAD_WEIGHTS[1]:g}}};
  for(int32 K=0;K<2;++K){{const double W=Neck?Weights[K]:(K?1.:0.);if(W<=0)continue;
   StreamerV2Turn(Pose,StreamerV2PoseBones[4+K],FQuat(FVector::UpVector,FMath::DegreesToRadians(Yaw*W))*FQuat(Right,FMath::DegreesToRadians(-Pitch*W)));}}
 }}
 void StreamerV2LoopSeam(float DeltaSeconds){{ // within the fade of a desk loop's end: Previous keeps the end, Current restarts at 0, crossfaded (no pop)
  const UAnimSequenceBase* Seq=Current.GetSequence();if(!Seq||StreamerV2LoopFadeSeconds<=.02f||Progress<1||!Current.IsLooping())return;
  const float Length=float(Seq->GetPlayLength()),Rate=Current.GetPlayRate(),Time=Current.GetAccumulatedTime(),Fade=FMath::Min(StreamerV2LoopFadeSeconds,Length*.25f);
  if(!(Length>1.f)||Rate<=0||Time+DeltaSeconds*Rate<Length-Fade)return;
  Previous.SetSequence(Current.GetSequence());Previous.SetAccumulatedTime(Time);Previous.SetLoopAnimation(false);Previous.SetPlayRate(0);PreviousCapturedRate=Rate;
  Current.SetAccumulatedTime(0);Progress=0;StreamerV2SeamFading=true;StreamerV2SeamFade=Fade;StreamerV2SeamSequence=Seq;++StreamerV2Seams;
 }}
 // SUB01_STREAMER_VISUAL_V2_POSEFIX END
'''
SPINE_APPLY = ('  for(int32 K=0;K<2;++K)if(StreamerV2Bones[K]!=INDEX_NONE){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(StreamerV2Bones[K]));'
               'if(Compact.GetInt()>=0){auto& T=Output.Pose[Compact];T.SetRotation((T.GetRotation()*StreamerV2Spine[K].Quaternion()).GetNormalized());}}\n')
SPINE_APPLY_POSE = '  ApplyStreamerV2Body(Output); // SUB01_STREAMER_VISUAL_V2_POSEFIX: lean + breathing about his lateral axis (FRotator pitch twisted these bones)\n'
HEAD_APPLY = ('   const auto& Bones=Output.Pose.GetBoneContainer();const int32 Index=Bones.GetReferenceSkeleton().FindBoneIndex(TEXT("Head"));\n'
              '   if(Index!=INDEX_NONE){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(Index));if(Compact.GetInt()>=0){auto& T=Output.Pose[Compact];T.SetRotation((T.GetRotation()*StreamerVisualHeadOffset.Quaternion()).GetNormalized());}}\n')
HEAD_APPLY_POSE = '   ApplyStreamerV2Head(Output); // SUB01_STREAMER_VISUAL_V2_POSEFIX: gaze/nod/posture pitch and yaw about his axes, over Neck and Head\n'
MOUTH_APPLY = '  auto& T=Output.Pose[Compact];T.SetRotation((T.GetRotation()*FRotator(Deg*FMath::Clamp(StreamerV2Mouth,0.f,1.f),0,0).Quaternion()).GetNormalized());\n'
MOUTH_APPLY_POSE = (f'  if(StreamerV2JawBone==INDEX_NONE){{StreamerV2MouthPitch=-{_f(MOUTH_HEAD_DEG)}*FMath::Clamp(StreamerV2Mouth,0.f,1.f);return;}} // SUB01_STREAMER_VISUAL_V2_POSEFIX: the head emphasis joins the body-frame head pitch (nose down)\n'
                    + MOUTH_APPLY)
STATE_CHANGE = '  if(Current.GetSequence()!=Hands->TargetSequence) {\n'
STATE_CHANGE_POSE = ('  if(Current.GetSequence()!=Hands->TargetSequence&&!(StreamerV2SeamFading&&Progress<1)) { // SUB01_STREAMER_VISUAL_V2_POSEFIX: a state change waits for a running '
                     'loop seam (<= loop_fade_s): switching mid-seam would drop the blended pose\n')
PREUPDATE_V2 = '  if(StreamerVisualActive&&StreamerV2)PreUpdateStreamerV2(Hands);else StreamerV2Entered=false; // SUB01_STREAMER_VISUAL_V2: no forced Progress, crossfades run\n'
PREUPDATE_POSE = PREUPDATE_V2 + '  StreamerV2Dt=DeltaSeconds;if(StreamerVisualActive&&StreamerV2)StreamerV2LoopSeam(DeltaSeconds); // SUB01_STREAMER_VISUAL_V2_POSEFIX: desk loops wrap through a crossfade\n'
UPDATE_LINE = '  Progress=FMath::Min(1.f,Progress+FMath::Min(DeltaSeconds,.1f)/.24f);\n'
UPDATE_POSE = ('  Progress=FMath::Min(1.f,Progress+FMath::Min(DeltaSeconds,.1f)/(StreamerV2SeamFading&&Current.GetSequence()==StreamerV2SeamSequence?FMath::Max(.05f,StreamerV2SeamFade):.24f)); // SUB01_STREAMER_VISUAL_V2_POSEFIX: a loop seam fades over its own time\n'
               '  if(Progress>=1)StreamerV2SeamFading=false;\n')
COPY_ANCHOR = _line(streampass.FACE_COPY_STREAM, '  StreamerV2HandPole[0]=')
COPY_POSE = COPY_ANCHOR + '  StreamerV2LeanCmd=Hands->StreamerVisualLeanDeg;StreamerV2LoopFadeSeconds=Hands->StreamerVisualLoopFadeSeconds; // SUB01_STREAMER_VISUAL_V2_POSEFIX\n'
PUBLISH_ANCHOR = _line(streampass.SEAT_PUBLISH_STREAM, ' StreamerVisualFingerMcpLeft=')
PUBLISH_POSE = (PUBLISH_ANCHOR + ' StreamerVisualSeatPivot=Proxy.StreamerV2PinPelvis.GetTranslation();StreamerVisualLeanMeasuredDeg=Proxy.StreamerV2LeanMeasured;StreamerVisualLeanGain=Proxy.StreamerV2LeanGain;'
                'StreamerVisualLoopSeams=Proxy.StreamerV2Seams;StreamerVisualBodyRight=Proxy.StreamerV2BodyRight; // SUB01_STREAMER_VISUAL_V2_POSEFIX\n')

EDITS = [
    ('header', HEADER_STREAM_END, HEADER_STREAM_END + HEADER_FIELDS),
    ('cpp', STREAM_METHODS_BEGIN, CPP_METHODS + STREAM_METHODS_BEGIN),
    ('cpp', TUNING_ANCHOR, TUNING_POSE),
    ('cpp', TUNING_POLL, TUNING_POLL_POSE),
    ('cpp', SPINE_SEND, SPINE_SEND_POSE),
    ('cpp', SEAT_LINE, SEAT_LINE_POSE),
    ('cpp', CHAIR_DELTA, CHAIR_DELTA_POSE),
    ('cpp', MOVE_ANCHOR, MOVE_POSE),
    ('cpp', GATE_ANCHOR, GATE_POSE),
    ('cpp', SCAN_ADD_ANCHOR, SCAN_ADD_POSE),
    ('cpp', SCAN_RESET_ANCHOR, SCAN_RESET_POSE),
    ('cpp', MOUSE_ADD_ANCHOR, MOUSE_ADD_POSE),
    ('cpp', TICK_ANCHOR, TICK_POSE),
    ('cpp', RECEIPT_ANCHOR, RECEIPT_POSE),
    ('cpp', FACE_OLD, FACE_NEW),
    ('hands_header', HANDS_STREAM_END, HANDS_STREAM_END + HANDS_FIELDS),
    ('hands_cpp', PROXY_STREAM_BEGIN, PROXY_MEMBERS + PROXY_STREAM_BEGIN),
    ('hands_cpp', SPINE_APPLY, SPINE_APPLY_POSE),
    ('hands_cpp', HEAD_APPLY, HEAD_APPLY_POSE),
    ('hands_cpp', MOUTH_APPLY, MOUTH_APPLY_POSE),
    ('hands_cpp', STATE_CHANGE, STATE_CHANGE_POSE),
    ('hands_cpp', PREUPDATE_V2, PREUPDATE_POSE),
    ('hands_cpp', UPDATE_LINE, UPDATE_POSE),
    ('hands_cpp', COPY_ANCHOR, COPY_POSE),
    ('hands_cpp', PUBLISH_ANCHOR, PUBLISH_POSE),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (pose fix already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the stream pass ({streampass.MARKER}); run the stack up to install_stream_pass.py first'
                for key in FILES if streampass.MARKER + ' BEGIN' not in sources[key]]
    problems += [f'{FILES["hands_cpp"]} lacks the mouth layer ({mouth.MARKER}); run install_mouth.py first'] if mouth.MARKER + ' BEGIN' not in sources['hands_cpp'] else []
    if problems:
        raise Refused('; '.join(problems))
    out, edits = dict(sources), []
    for key, anchor, replacement in EDITS:
        count = out[key].count(anchor)
        edits.append({'file': FILES[key], 'anchor': anchor.strip()[:96], 'anchor_sha256': v2.sha256(anchor), 'count': count})
        if count != 1:
            problems.append(f'anchor {"missing" if count == 0 else f"found {count}x"} in {FILES[key]}: {anchor.strip()[:96]!r}')
            continue
        out[key] = out[key].replace(anchor, replacement, 1)
    if problems:
        raise Refused('; '.join(problems))
    for key in FILES:
        if v2.balance(sources[key]) != v2.balance(out[key]):
            raise Refused(f'{FILES[key]}: bracket balance changed by the install')
        if MARKER not in out[key]:
            raise Refused(f'{FILES[key]}: marker missing after install')
    return {'sources': out, 'edits': edits}


def run(source: Path, dry_run: bool) -> dict:
    source = Path(source).resolve()
    missing = [n for n in FILES.values() if not (source / n).is_file()]
    if missing:
        raise Refused(f'missing in {source}: {", ".join(missing)}')
    raw = {key: v2.read_raw(source / name) for key, name in FILES.items()}
    eol = {key: v2.line_ending(FILES[key], raw[key]) for key in FILES}
    result = plan({key: text.replace('\r\n', '\n') for key, text in raw.items()})
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in FILES}
    report = {'schema': 'sub01.native-streamer-visual-v2-posefix-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': [streampass.MARKER, mouth.MARKER, seatfix.MARKER, v2.MARKER],
              'axes': {'lateral': 'right thigh - left thigh, flattened (else -X)', 'per_bone': "local' = parent^-1 * Delta * parent * local",
                       'lean_weights': dict(zip(('Spine', 'Spine1', 'Spine2'), LEAN_WEIGHTS)), 'head_weights': dict(zip(('Neck', 'Head'), HEAD_WEIGHTS)),
                       'lean_gain_limits': list(LEAN_GAIN_LIMITS), 'lean_gain_tau_s': LEAN_GAIN_TAU_S, 'mouth_head_deg_nose_down': MOUTH_HEAD_DEG,
                       'signs': 'spine channel: forward lean positive (posture_lean -16 = sit up); head: pitch nose up positive, yaw to his right positive'},
              'loop_fade_s': LOOP_FADE_SECONDS, 'face': {'mean_seconds': FACE_MEAN_SECONDS, 'min_seconds': FACE_MIN_SECONDS, 'aim': 'once, kept across switches, re-aimed on a tuning change'},
              'chair_fit': {'on': CHAIR_FIT, 'sacrum_back_cm': SACRUM_BACK_CM, 'backrest_gap_cm': BACKREST_GAP_CM, 'passes': CHAIR_FIT_PASSES, 'max_cm': CHAIR_FIT_MAX_CM,
                            'deadband_cm': CHAIR_FIT_DEADBAND_CM, 'backrest': {'min_behind_cm': BACKREST_MIN_BEHIND_CM, 'min_above_cm': BACKREST_MIN_ABOVE_CM, 'max_side_cm': BACKREST_MAX_SIDE_CM}},
              'tuning_limits': TUNING_LIMITS, 'edits': result['edits'],
              'files': {FILES[key]: {'before_sha256': v2.sha256(raw[key]), 'after_sha256': v2.sha256(after[key]),
                                     'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                     'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                     'edits': sum(1 for k, _, _ in EDITS if k == key)} for key in FILES}}
    if not dry_run:
        v2.write_atomically({source / FILES[key]: after[key] for key in FILES})
        for key in FILES:
            if v2.sha256(v2.read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the stream-passed + mouth pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-posefix-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
