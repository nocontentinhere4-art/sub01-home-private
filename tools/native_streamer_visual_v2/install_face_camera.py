"""v2 follow-up ON TOP of an installed `-Sub01StreamerVisual` v2: the "face" camera and the desk root-motion guard.

    python tools/native_streamer_visual_v2/install_face_camera.py --source <dir> [--dry-run]

<dir> holds the v2-patched pod files (install.py already applied): Sub01HomeLab.cpp/.h and Sub01HomeHands.cpp/.h.
Refused (exit 2, nothing written) when v2 is absent from any of them, when the marker `// SUB01_STREAMER_VISUAL_V2_FACE`
is already present, or when any anchor is not found exactly once. Same atomic writes, line-ending handling and JSON
report (before/after sha256) as install.py.

1. Camera "face" (v2 event field `camera`): the stream's webcam just above the monitor, looking back at his face.
   Location = monitor bounds centre (217,-367.67,114.75) + 28 cm up, pulled 10 cm towards him along the body facing used
   by "monitor"; aimed at the Head bone world location (sampled once per selection), else body transform + (0,0,120);
   FOV 42. A separate 1 s eased layer (location, rotation, FOV 65 -> 42) over the unchanged spectator/monitor blend.
2. Desk guard (field report: the chair was empty in `mouse`/`idle` while body_world stayed put). The streamer branch never
   sets RootMotionMode, so the instance keeps UE's RootMotionFromMontagesOnly: these sequence players never extract root
   motion and a clip's root track (an authored station offset or root travel) lands in the pose unless the asset has
   bForceRootLock. Now every v2 frame the bones above the pelvis take R9's reference locals and the pelvis stays within
   8 cm / 25 deg of R9@0.7 (the pose the authored body transform was placed with). Each clip's pelvis is audited against
   R9 once (5 phases, logged with bEnableRootMotion/bForceRootLock/RootMotionRootLock and the instance RootMotionMode);
   a clip further than 25 cm / 25 deg is treated as authored at another station: typing/mouse play the sitting loop,
   the sitting loop falls back to the frozen R9. Until the audit is published only the (pinned) sitting loop plays.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_install', Path(__file__).resolve().parent / 'install.py')
v2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v2)
Refused = v2.Refused

MARKER = '// SUB01_STREAMER_VISUAL_V2_FACE'
V2_BEGIN, V2_END = v2.MARKER + ' BEGIN', v2.MARKER + ' END'  # not prefixes of the face marker
FILES = dict(v2.FILES)  # header, cpp, hands_header, hands_cpp
FACE_FOV = 42.0
FACE_UP_CM, FACE_TOWARDS_CM = 28.0, 10.0
PIN_RADIUS_CM, PIN_MAX_DEG, DESK_STATION_CM, DESK_STATION_DEG = 8.0, 25.0, 25.0, 25.0

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_FIELDS = r''' // SUB01_STREAMER_VISUAL_V2_FACE BEGIN (tools/native_streamer_visual_v2/install_face_camera.py): "face" webcam, desk guard.
 void ApplyStreamerVisualFaceCamera(float Dt);
 int32 StreamerVisualDeskSlot(class USub01HomeHandsInstance* Anim,int32 Slot);
 FVector StreamerVisualFaceLocation=FVector::ZeroVector;
 FRotator StreamerVisualFaceLook=FRotator::ZeroRotator;
 float StreamerVisualFaceAlpha=0;
 bool StreamerVisualFaceAimed=false,StreamerVisualAuditLogged=false;
 FString StreamerVisualFaceAimSource;
 // SUB01_STREAMER_VISUAL_V2_FACE END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
CPP_METHODS = r'''// SUB01_STREAMER_VISUAL_V2_FACE BEGIN (tools/native_streamer_visual_v2/install_face_camera.py)
#include "UObject/UnrealType.h"
void ASub01HomeCharacter::ApplyStreamerVisualFaceCamera(float Dt){
 // "face" = the stream's webcam just above the monitor, looking back at his face. A separate 1 s eased layer over the
 // spectator/monitor blend above, which keeps running unchanged underneath (a fresh "face" slides from wherever it is).
 const bool Face=StreamerVisualCameraTarget==TEXT("face");
 if(Face&&!StreamerVisualFaceAimed){ // aimed once per selection: Head bone world location, else body transform + (0,0,120)
  const FVector BodyAt=FirstPersonBody?FirstPersonBody->GetComponentLocation():FVector(214,-289,6.19);
  const bool HasHead=FirstPersonBody&&FirstPersonBody->GetBoneIndex(TEXT("Head"))!=INDEX_NONE;
  FVector Aim=HasHead?FirstPersonBody->GetBoneLocation(TEXT("Head")):FVector::ZeroVector;StreamerVisualFaceAimSource=TEXT("head");
  if(!HasHead||Aim.ContainsNaN()||FVector::Dist(Aim,BodyAt)>250){Aim=BodyAt+FVector(0,0,120);StreamerVisualFaceAimSource=TEXT("body+120");}
  StreamerVisualFaceLook=(Aim-StreamerVisualFaceLocation).Rotation();StreamerVisualFaceAimed=true;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_FACE_CAMERA location=%s aim=%s source=%s look=%s fov=@@FOV@@"),*StreamerVisualFaceLocation.ToString(),*Aim.ToString(),*StreamerVisualFaceAimSource,*StreamerVisualFaceLook.ToString());
 }
 if(!Face)StreamerVisualFaceAimed=false;
 const float Goal=Face?1.f:0.f;
 if(!ViewCamera||(Goal==0&&StreamerVisualFaceAlpha<=0))return; // spectator/monitor only: the v2 camera path alone, untouched
 StreamerVisualFaceAlpha=Goal>StreamerVisualFaceAlpha?FMath::Min(Goal,StreamerVisualFaceAlpha+Dt):FMath::Max(Goal,StreamerVisualFaceAlpha-Dt);
 if(StreamerVisualFaceAlpha<=0){ // fade-out done: FOV back to 65; exact spectator pose when the base rests there (else the v2 block set it this tick)
  ViewCamera->SetFieldOfView(65.f);
  if(StreamerVisualCameraAlpha<=0){ViewCamera->SetWorldLocationAndRotation(FVector(334,-209,151),StreamerVisualSpectatorLook);if(Controller)Controller->SetControlRotation(StreamerVisualSpectatorLook);}
  return;
 }
 const float Base=FMath::SmoothStep(0.f,1.f,StreamerVisualCameraAlpha),Ease=FMath::SmoothStep(0.f,1.f,StreamerVisualFaceAlpha);
 const FVector Under=FMath::Lerp(FVector(334,-209,151),StreamerVisualMonitorLocation,double(Base));
 const FQuat UnderQ=FQuat::Slerp(StreamerVisualSpectatorLook.Quaternion(),StreamerVisualMonitorLook.Quaternion(),double(Base));
 const FRotator Rotation=FQuat::Slerp(UnderQ,StreamerVisualFaceLook.Quaternion(),double(Ease)).Rotator();
 ViewCamera->SetWorldLocationAndRotation(FMath::Lerp(Under,StreamerVisualFaceLocation,double(Ease)),Rotation);ViewCamera->SetFieldOfView(FMath::Lerp(65.f,@@FOVF@@,Ease));
 if(Controller)Controller->SetControlRotation(Rotation);
}
int32 ASub01HomeCharacter::StreamerVisualDeskSlot(USub01HomeHandsInstance* Anim,int32 Slot){
 // Desk guard: these players never extract root motion (the instance keeps RootMotionFromMontagesOnly), so a clip's root
 // track lands in the pose. The proxy pins the pelvis to R9 every frame and audits each clip's pelvis against R9 once; a
 // clip > @@STATION_CM@@ cm / @@STATION_DEG@@ deg away was authored at another station and is not played: typing/mouse -> sitting loop,
 // sitting loop -> frozen R9 (-1). A missing clip keeps the v2 rule (frozen R9). Before the audit only the sitting loop plays.
 if(!Anim)return Slot;
 if(Anim->StreamerVisualAuditClips.Num()!=StreamerVisualV2Clips.Num())Anim->StreamerVisualAuditClips=StreamerVisualV2Clips;
 const bool Done=Anim->StreamerVisualAuditDone;
 auto Safe=[Anim,Done](int32 S){return Done&&Anim->StreamerVisualClipOffsetCm.IsValidIndex(S)&&Anim->StreamerVisualClipAngleDeg.IsValidIndex(S)&&Anim->StreamerVisualClipOffsetCm[S]>=0&&Anim->StreamerVisualClipOffsetCm[S]<=@@STATION_CM@@.f&&Anim->StreamerVisualClipAngleDeg[S]<=@@STATION_DEG@@.f;};
 if(Done&&!StreamerVisualAuditLogged){
  StreamerVisualAuditLogged=true;const FByteProperty* RootModeProperty=FindFProperty<FByteProperty>(UAnimInstance::StaticClass(),TEXT("RootMotionMode"));const int32 RootMode=RootModeProperty?int32(RootModeProperty->GetPropertyValue_InContainer(Anim)):-1;
  for(int32 S=0;S<StreamerVisualV2Clips.Num();++S){const UAnimSequence* C=StreamerVisualV2Clips[S].Get();
   UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CLIP_AUDIT slot=%d clip=%s pelvisOffsetFromR9Cm=%.1f pelvisAngleFromR9Deg=%.1f deskStation=%d enableRootMotion=%d forceRootLock=%d rootLock=%d instanceRootMotionMode=%d"),
    S,C?*C->GetPathName():TEXT("missing"),Anim->StreamerVisualClipOffsetCm.IsValidIndex(S)?Anim->StreamerVisualClipOffsetCm[S]:-1.f,Anim->StreamerVisualClipAngleDeg.IsValidIndex(S)?Anim->StreamerVisualClipAngleDeg[S]:-1.f,
    Safe(S)?1:0,C&&C->bEnableRootMotion?1:0,C&&C->bForceRootLock?1:0,C?int32(C->RootMotionRootLock.GetValue()):-1,RootMode);
  }
 }
 if(!StreamerVisualV2Clips.IsValidIndex(Slot)||!StreamerVisualV2Clips[Slot])return Slot;
 if(Slot==0)return !Done||Safe(0)?0:-1;
 if(Safe(Slot))return Slot;
 return StreamerVisualV2Clips[0]&&(!Done||Safe(0))?0:-1;
}
// SUB01_STREAMER_VISUAL_V2_FACE END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.h
HANDS_FIELDS = r''' // SUB01_STREAMER_VISUAL_V2_FACE BEGIN (tools/native_streamer_visual_v2/install_face_camera.py): desk guard.
 UPROPERTY(Transient) TArray<TObjectPtr<UAnimSequence>> StreamerVisualAuditClips; // v2 slot order, set by the character
 UPROPERTY(Transient) bool StreamerVisualAuditDone=false;
 UPROPERTY(Transient) TArray<float> StreamerVisualClipOffsetCm; // per slot: max pelvis distance from R9 over 5 phases (-1 missing)
 UPROPERTY(Transient) TArray<float> StreamerVisualClipAngleDeg;
 UPROPERTY(Transient) float StreamerVisualDeskOffsetCm=-1; // last frame: pelvis distance from R9 before the pin
 // SUB01_STREAMER_VISUAL_V2_FACE END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.cpp
PROXY_MEMBERS = r''' // SUB01_STREAMER_VISUAL_V2_FACE BEGIN (tools/native_streamer_visual_v2/install_face_camera.py): desk pin + clip audit.
 // These players never extract root motion, so a clip's root track is applied to the pose. Every v2 frame the bones above
 // the pelvis take R9's reference locals and the pelvis stays within @@PIN_CM@@ cm / @@PIN_DEG@@ deg of R9's (R9@0.7 is the pose the
 // authored body transform was placed with). Raw sequence pointers here are kept alive by UPROPERTYs on the instance.
 UAnimSequenceBase* StreamerV2Reference=nullptr;float StreamerV2ReferenceSeconds=.7f;TArray<UAnimSequenceBase*> StreamerV2AuditClips;
 bool StreamerV2PinReady=false,StreamerV2PinTried=false,StreamerV2Audited=false;int32 StreamerV2PinCount=-1;float StreamerV2LastPinCm=-1;
 TArray<int32> StreamerV2PinChain;TArray<FTransform> StreamerV2PinLocals;FTransform StreamerV2PinPelvis=FTransform::Identity;
 TArray<float> StreamerV2AuditOffsetCm,StreamerV2AuditAngleDeg;
 static constexpr double StreamerV2PinRadiusCm=@@PIN_CM@@,StreamerV2PinMaxRadians=@@PIN_RAD@@;
 bool StreamerV2Pelvis(const FCompactPose& Source,FTransform& Pelvis) const { // component space: pelvis local * parents (chain pelvis -> root)
  const auto& Bones=Source.GetBoneContainer();Pelvis=FTransform::Identity;
  for(const int32 B:StreamerV2PinChain){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(Compact.GetInt()<0)return false;Pelvis=Pelvis*Source[Compact];}
  return !Pelvis.ContainsNaN();
 }
 bool PrepareStreamerV2Pin(FPoseContext& Output){
  const auto& Ref=Output.Pose.GetBoneContainer().GetReferenceSkeleton();
  if(StreamerV2PinCount!=Ref.GetNum()){StreamerV2PinCount=Ref.GetNum();StreamerV2PinReady=StreamerV2PinTried=false;}
  if(StreamerV2PinReady||StreamerV2PinTried||!StreamerV2Reference)return StreamerV2PinReady;
  StreamerV2PinTried=true;StreamerV2PinChain.Reset();StreamerV2PinLocals.Reset();
  int32 PelvisBone=Ref.FindBoneIndex(FName(TEXT("Hips")));for(int32 B=0;PelvisBone==INDEX_NONE&&B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(TEXT("Hips")))PelvisBone=B;if(PelvisBone==INDEX_NONE)PelvisBone=0;
  for(int32 B=PelvisBone;B!=INDEX_NONE&&StreamerV2PinChain.Num()<=8;B=Ref.GetParentIndex(B))StreamerV2PinChain.Add(B);
  if(Ref.GetNum()<1||StreamerV2PinChain.Num()>8)return false;
  StreamerV2Probe.SetSequence(StreamerV2Reference);StreamerV2Probe.SetLoopAnimation(false);StreamerV2Probe.SetPlayRate(0);StreamerV2Probe.SetAccumulatedTime(StreamerV2ReferenceSeconds);
  FPoseContext Probe(Output.AnimInstanceProxy);StreamerV2Probe.Evaluate_AnyThread(Probe);const auto& Bones=Probe.Pose.GetBoneContainer();
  for(const int32 B:StreamerV2PinChain){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(Compact.GetInt()<0){StreamerV2PinLocals.Reset();return false;}StreamerV2PinLocals.Add(Probe.Pose[Compact]);}
  if(!StreamerV2Pelvis(Probe.Pose,StreamerV2PinPelvis))return false;
  StreamerV2PinReady=true;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_DESK_PIN pelvisBone=%d chain=%d reference=R9@%.2fs pelvis=%s radiusCm=@@PIN_CM@@ maxDeg=@@PIN_DEG@@"),PelvisBone,StreamerV2PinChain.Num(),StreamerV2ReferenceSeconds,*StreamerV2PinPelvis.GetTranslation().ToString());
  return true;
 }
 void AuditStreamerV2Clips(FPoseContext& Output){ // once: each clip's unpinned pelvis vs R9 at 0, 1/4, 1/2, 3/4, 1 of its length
  StreamerV2Audited=true;StreamerV2AuditOffsetCm.Reset();StreamerV2AuditAngleDeg.Reset();
  for(UAnimSequenceBase* Clip:StreamerV2AuditClips){
   float MaxCm=-1,MaxDeg=-1;const float Length=Clip?float(Clip->GetPlayLength()):0.f;
   for(int32 K=0;Clip&&Length>0&&K<=4;++K){
    StreamerV2Probe.SetSequence(Clip);StreamerV2Probe.SetLoopAnimation(false);StreamerV2Probe.SetPlayRate(0);StreamerV2Probe.SetAccumulatedTime(Length*K/4);
    FPoseContext Probe(Output.AnimInstanceProxy);StreamerV2Probe.Evaluate_AnyThread(Probe);FTransform Pelvis=FTransform::Identity;
    if(!StreamerV2Pelvis(Probe.Pose,Pelvis)){MaxCm=MaxDeg=1e6f;break;}
    MaxCm=FMath::Max(MaxCm,float(FVector::Dist(Pelvis.GetTranslation(),StreamerV2PinPelvis.GetTranslation())));
    MaxDeg=FMath::Max(MaxDeg,float(FMath::RadiansToDegrees(StreamerV2PinPelvis.GetRotation().AngularDistance(Pelvis.GetRotation()))));
   }
   StreamerV2AuditOffsetCm.Add(MaxCm);StreamerV2AuditAngleDeg.Add(MaxDeg);
  }
 }
 void PinStreamerV2(FCompactPose& Composed,bool Record){
  if(!StreamerV2PinReady||StreamerV2PinLocals.Num()!=StreamerV2PinChain.Num())return;
  if(Record){FTransform Pelvis=FTransform::Identity;StreamerV2LastPinCm=StreamerV2Pelvis(Composed,Pelvis)?float(FVector::Dist(Pelvis.GetTranslation(),StreamerV2PinPelvis.GetTranslation())):-1.f;}
  const auto& Bones=Composed.GetBoneContainer();
  for(int32 I=0;I<StreamerV2PinChain.Num();++I){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(StreamerV2PinChain[I]));if(Compact.GetInt()<0)continue;
   auto& T=Composed[Compact];const FTransform& Reference=StreamerV2PinLocals[I];
   if(I>0){T=Reference;continue;} // bones above the pelvis (root): exactly R9's, so no authored station offset survives
   const FVector Delta=T.GetTranslation()-Reference.GetTranslation();const double Cm=Delta.Size();
   if(Cm>StreamerV2PinRadiusCm)T.SetTranslation(Reference.GetTranslation()+Delta*(StreamerV2PinRadiusCm/Cm));
   const double Angle=Reference.GetRotation().AngularDistance(T.GetRotation());
   if(Angle>StreamerV2PinMaxRadians)T.SetRotation(FQuat::Slerp(Reference.GetRotation(),T.GetRotation(),StreamerV2PinMaxRadians/Angle));
  }
 }
 // SUB01_STREAMER_VISUAL_V2_FACE END
'''

_SUBST = {'@@FOVF@@': f'{FACE_FOV:g}.f', '@@FOV@@': f'{FACE_FOV:g}', '@@PIN_CM@@': f'{PIN_RADIUS_CM:g}',
          '@@PIN_DEG@@': f'{PIN_MAX_DEG:g}', '@@PIN_RAD@@': repr(PIN_MAX_DEG * 3.141592653589793 / 180),
          '@@STATION_CM@@': f'{DESK_STATION_CM:g}', '@@STATION_DEG@@': f'{DESK_STATION_DEG:g}'}


def _fill(text: str) -> str:
    for key, value in _SUBST.items():
        text = text.replace(key, value)
    return text


CPP_METHODS, PROXY_MEMBERS = _fill(CPP_METHODS), _fill(PROXY_MEMBERS)

MONITOR_LINE = (' StreamerVisualMonitorLocation=Pivot+Facing*-70.+Side*45.+FVector(0,0,45);StreamerVisualMonitorLook=(Monitor-StreamerVisualMonitorLocation).Rotation();'
                'StreamerVisualMonitorAxis=AxisNames[Chosen];\n')
APPLY_TAIL = ('  ViewCamera->SetWorldLocationAndRotation(Location,Rotation);if(Controller)Controller->SetControlRotation(Rotation);\n'
              ' }\n}\n// SUB01_STREAMER_VISUAL_V2 END\n')
SLOT_LINE = '  const int32 Slot=StreamerVisualState==TEXT("typing")?1:StreamerVisualState==TEXT("mouse")?2:0;\n'
PARSE_CAMERAS = '(Camera==TEXT("spectator")||Camera==TEXT("monitor"))'
RECEIPT_TAIL = 'Receipt->SetStringField(TEXT("monitor_camera_facing_axis"),StreamerVisualMonitorAxis);}\n'
PROXY_COPY = ('  StreamerV2=Hands->StreamerVisualV2;StreamerV2Spine[0]=Hands->StreamerVisualSpine1Offset;'
              'StreamerV2Spine[1]=Hands->StreamerVisualSpine2Offset; // SUB01_STREAMER_VISUAL_V2\n')
PROXY_MATCH = '  if(StreamerV2Match&&StreamerVisualActive&&StreamerV2)MatchStreamerV2Phase(Output);StreamerV2Match=false; // SUB01_STREAMER_VISUAL_V2\n'
PROBE_EVAL = 'StreamerV2Probe.Evaluate_AnyThread(Probe);\n    FVector L=FVector::ZeroVector'
EVAL_HEAD = '  const auto& Bones=Output.Pose.GetBoneContainer();ResolveStreamerV2(Bones.GetReferenceSkeleton());\n  StreamerV2HandsValid='
PUBLISH = (' StreamerVisualEvaluatedTime=Proxy.StreamerV2?Proxy.Current.GetAccumulatedTime():-1.f;'
           'StreamerVisualMatchedSeconds=Proxy.StreamerV2MatchedSeconds; // SUB01_STREAMER_VISUAL_V2\n')

EDITS = [
    ('header', ' ' + V2_END + '\n', ' ' + V2_END + '\n' + HEADER_FIELDS),
    ('cpp', MONITOR_LINE, MONITOR_LINE +
     f' StreamerVisualFaceLocation=Monitor+FVector(0,0,{FACE_UP_CM:g})-Facing*{FACE_TOWARDS_CM:g}.; // SUB01_STREAMER_VISUAL_V2_FACE: webcam above the monitor, pulled towards him\n'
     ' UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_FACE_READY location=%s fov=' + f'{FACE_FOV:g}' + '"),*StreamerVisualFaceLocation.ToString()); // SUB01_STREAMER_VISUAL_V2_FACE\n'),
    ('cpp', PARSE_CAMERAS, '(Camera==TEXT("spectator")||Camera==TEXT("monitor")||Camera==TEXT("face")/* SUB01_STREAMER_VISUAL_V2_FACE */)'),
    ('cpp', SLOT_LINE,
     '  const int32 Slot=StreamerVisualDeskSlot(Anim,StreamerVisualState==TEXT("typing")?1:StreamerVisualState==TEXT("mouse")?2:0); // SUB01_STREAMER_VISUAL_V2_FACE: off-desk clip -> sitting loop / frozen R9\n'),
    ('cpp', APPLY_TAIL,
     '  ViewCamera->SetWorldLocationAndRotation(Location,Rotation);if(Controller)Controller->SetControlRotation(Rotation);\n'
     ' }\n ApplyStreamerVisualFaceCamera(Dt); // SUB01_STREAMER_VISUAL_V2_FACE: webcam layer over the blend above\n}\n'
     + V2_END + '\n' + CPP_METHODS),
    ('cpp', RECEIPT_TAIL,
     'Receipt->SetStringField(TEXT("monitor_camera_facing_axis"),StreamerVisualMonitorAxis);\n'
     '   Receipt->SetNumberField(TEXT("face_camera_blend"),StreamerVisualFaceAlpha);Receipt->SetNumberField(TEXT("camera_fov"),ViewCamera->FieldOfView);'
     'Receipt->SetStringField(TEXT("face_camera_aim_source"),StreamerVisualFaceAimSource);\n'
     '   Receipt->SetNumberField(TEXT("desk_offset_before_pin_cm"),V2Anim?V2Anim->StreamerVisualDeskOffsetCm:-1.f);'
     'Receipt->SetBoolField(TEXT("clip_audit_done"),V2Anim&&V2Anim->StreamerVisualAuditDone);} // SUB01_STREAMER_VISUAL_V2_FACE\n'),
    ('hands_header', ' ' + V2_END + '\n', ' ' + V2_END + '\n' + HANDS_FIELDS),
    ('hands_cpp', ' ' + V2_END + '\n', ' ' + V2_END + '\n' + PROXY_MEMBERS),
    ('hands_cpp', PROXY_COPY, PROXY_COPY +
     '  StreamerV2Reference=Hands->StreamerVisualFreezeSequence.Get();StreamerV2ReferenceSeconds=Hands->StreamerVisualFreezeSeconds;'
     'if(!StreamerV2Audited){StreamerV2AuditClips.Reset();for(const auto& Clip:Hands->StreamerVisualAuditClips)StreamerV2AuditClips.Add(Clip.Get());} // SUB01_STREAMER_VISUAL_V2_FACE\n'),
    ('hands_cpp', PROXY_MATCH,
     '  if(StreamerVisualActive&&StreamerV2&&PrepareStreamerV2Pin(Output)&&!StreamerV2Audited&&StreamerV2AuditClips.Num())AuditStreamerV2Clips(Output); // SUB01_STREAMER_VISUAL_V2_FACE\n'
     + PROXY_MATCH),
    ('hands_cpp', PROBE_EVAL, 'StreamerV2Probe.Evaluate_AnyThread(Probe);PinStreamerV2(Probe.Pose,false); // SUB01_STREAMER_VISUAL_V2_FACE: phases of the pinned clip\n    FVector L=FVector::ZeroVector'),
    ('hands_cpp', EVAL_HEAD,
     '  const auto& Bones=Output.Pose.GetBoneContainer();ResolveStreamerV2(Bones.GetReferenceSkeleton());\n'
     '  PinStreamerV2(Output.Pose,true); // SUB01_STREAMER_VISUAL_V2_FACE: desk pin before hands, breathing and head\n'
     '  StreamerV2HandsValid='),
    ('hands_cpp', PUBLISH, PUBLISH +
     ' if(Proxy.StreamerV2Audited&&!StreamerVisualAuditDone){StreamerVisualClipOffsetCm=Proxy.StreamerV2AuditOffsetCm;StreamerVisualClipAngleDeg=Proxy.StreamerV2AuditAngleDeg;StreamerVisualAuditDone=true;}'
     'StreamerVisualDeskOffsetCm=Proxy.StreamerV2LastPinCm; // SUB01_STREAMER_VISUAL_V2_FACE\n'),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts {'header','cpp','hands_header','hands_cpp'}; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (face camera / desk guard already installed)'
                for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the v2 install ({V2_BEGIN} ... {V2_END}); run install.py first'
                for key in FILES if V2_BEGIN not in sources[key] or V2_END not in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    out, edits = dict(sources), []
    for key, anchor, replacement in EDITS:
        count = out[key].count(anchor)
        edits.append({'file': FILES[key], 'anchor': anchor.strip()[:96], 'count': count})
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
    report = {'schema': 'sub01.native-streamer-visual-v2-face-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': v2.MARKER, 'cameras': ['spectator', 'monitor', 'face'],
              'face': {'location': f'monitor bounds centre + (0,0,{FACE_UP_CM:g}) - facing*{FACE_TOWARDS_CM:g}',
                       'aim': 'Head bone world location at selection, else body transform + (0,0,120)', 'fov': FACE_FOV,
                       'blend_seconds': 1.0},
              'desk_guard': {'reference': 'R9_Sitting @0.7 s (frozen v1 pose)', 'above_pelvis': 'pinned to the reference',
                             'pelvis_radius_cm': PIN_RADIUS_CM, 'pelvis_max_deg': PIN_MAX_DEG,
                             'desk_station_cm': DESK_STATION_CM, 'desk_station_deg': DESK_STATION_DEG,
                             'off_station': {'typing': 'sitting loop', 'mouse': 'sitting loop', 'sitting loop': 'frozen R9'}},
              'edits': result['edits'],
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
    parser.add_argument('--source', type=Path, required=True, help='directory with the v2-patched pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-face-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
