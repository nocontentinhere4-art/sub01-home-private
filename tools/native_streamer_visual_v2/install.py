"""Install `-Sub01StreamerVisual` v2 into copies of the pod sources (string-anchored, exact-once, all or nothing).

    python tools/native_streamer_visual_v2/install.py --source <dir> [--dry-run]

<dir> holds the five pod files: Sub01HomeLab.cpp/.h and Sub01HomeHands.cpp/.h (patched) plus Sub01PCBridge.h (read
only: the streamer branch now calls USub01PCBridge::HasOperatorFocus()). Every anchor must occur exactly once in the
text it edits, otherwise nothing is written. A file already carrying the marker `// SUB01_STREAMER_VISUAL_V2` is
refused (no double install). Files are replaced atomically (temporary file in the same directory, fsync, rename) and a
JSON report with before/after sha256 is printed. Exit 0 = applied (or would apply with --dry-run), 2 = refused.

What v2 changes (see README.md): v2 events (`sub01.private-streamer-visual-event.v2`, source `streamer_agent`, `state`,
`intensity`, optional `camera`) next to the untouched v1 path; state -> clip through the AnimInstance's existing
Previous/Current crossfade with a hand-matched loop phase; deterministic breathing (Spine1/Spine2), head sway, talking
cadence and reacting nod; optional over-the-shoulder monitor camera; extra receipt fields. Nothing is compiled here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

MARKER = '// SUB01_STREAMER_VISUAL_V2'
FILES = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp',
         'hands_header': 'Sub01HomeHands.h', 'hands_cpp': 'Sub01HomeHands.cpp'}
READ_ONLY = {'pc_bridge_header': ('Sub01PCBridge.h', 'bool HasOperatorFocus() const')}
SCHEMA_V1 = 'sub01.private-streamer-visual-event.v1'
SCHEMA_V2 = 'sub01.private-streamer-visual-event.v2'
R9_CLIP = '/Game/Sub01Hands/AnatomicalCandidate/DirectPlantedSeat_eaddbc7f5f8c47b58bffe7d3ab24b859/Sitting/R9_Sitting.R9_Sitting'
CLIPS = {  # slot: (path, loop, states)
    'sitting': ('/Game/Sub01Hands/Cinematic20261022/Desk7_f6961034aace44a99bb8b0431082264a/SupportedWebsite.SupportedWebsite',
                True, ('idle', 'reading', 'talking', 'reacting')),
    'typing': ('/Game/Sub01Hands/Cinematic20261022/Desk7_1da89c8bada540468cf190aceb633b1f/SupportedDeskTyping.SupportedDeskTyping',
               True, ('typing',)),
    'reach': ('/Game/Sub01Hands/Cinematic20261022/Reach_c8accd7a0070407c8af117eed5df534d/AuthoredReach.AuthoredReach',
              False, ('mouse',)),
}
STATES = ('idle', 'reading', 'typing', 'mouse', 'talking', 'reacting')


class Refused(Exception):
    pass


# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_FIELDS = r''' // SUB01_STREAMER_VISUAL_V2 BEGIN (tools/native_streamer_visual_v2/install.py): v2 states -> curated clips through the
 // AnimInstance crossfade, breathing/sway/nod, optional over-the-shoulder monitor camera. v1 events keep the frozen R9 path.
 void StartStreamerVisualV2(const FRotator& SpectatorLook);
 bool ParseStreamerVisualV2(const TSharedPtr<FJsonObject>& J,FString& Frame,FString& State,double& Intensity,FString& Camera) const;
 void AcceptStreamerVisualV2(int32 Version,const FString& State,double Intensity,const FString& Camera,double Nod);
 FRotator TickStreamerVisualV2(double Now);
 void ApplyStreamerVisualV2(double Now,float Dt);
 UPROPERTY() TArray<TObjectPtr<UAnimSequence>> StreamerVisualV2Clips;
 UPROPERTY() TObjectPtr<UAnimSequence> StreamerVisualActiveClip;
 int32 StreamerVisualSchemaVersion=2;
 FString StreamerVisualState=TEXT("idle"),StreamerVisualRequestedState=TEXT("idle"),StreamerVisualCameraTarget=TEXT("spectator"),StreamerVisualRequestedCamera=TEXT("spectator"),StreamerVisualMonitorAxis;
 double StreamerVisualStartedAt=0,StreamerVisualStateAt=-10,StreamerVisualNodAt=-10;
 float StreamerVisualIntensity=.5f,StreamerVisualNodStrength=0,StreamerVisualNodGain=0,StreamerVisualCameraAlpha=0;
 FVector StreamerVisualMonitorLocation=FVector::ZeroVector;
 FRotator StreamerVisualMonitorLook=FRotator::ZeroRotator,StreamerVisualSpectatorLook=FRotator::ZeroRotator;
 // SUB01_STREAMER_VISUAL_V2 END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
CPP_METHODS = r'''// SUB01_STREAMER_VISUAL_V2 BEGIN (tools/native_streamer_visual_v2/install.py). Visual performance only: no seat/contact claim.
// Clips play through the AnimInstance's existing Previous/Current 0.24 s crossfade; a clip that is missing (or on another
// skeleton) falls back to the v1 frozen R9_Sitting for its states. All liveliness is a deterministic, bounded function of time.
static double Sub01StreamerVisualV2Noise(double X,uint32 Seed){
 // Smooth value noise in [-1,1], two octaves: slow, continuous and repeatable for a given time (a bounded "random walk").
 auto Hash=[Seed](int64 K){uint32 H=uint32(K)*0x9E3779B1u^Seed;H^=H>>16;H*=0x7FEB352Du;H^=H>>15;H*=0x846CA68Bu;H^=H>>16;return double(H)/4294967295.0*2-1;};
 auto Octave=[&Hash](double V){const double F=FMath::FloorToDouble(V),U=V-F,S=U*U*(3-2*U);const int64 I=int64(F);return Hash(I)+(Hash(I+1)-Hash(I))*S;};
 return FMath::Clamp((Octave(X)+.35*Octave(X*2.7+17.3))/1.35,-1.,1.);
}
void ASub01HomeCharacter::StartStreamerVisualV2(const FRotator& SpectatorLook){
 StreamerVisualStartedAt=FPlatformTime::Seconds();StreamerVisualSpectatorLook=SpectatorLook;StreamerVisualActiveClip=StreamerVisualClip;StreamerVisualCameraAlpha=0;
 static const TCHAR* const Paths[3]={
  TEXT("@@CLIP_SITTING@@"),    // 0 idle/reading/talking/reacting: sitting loop
  TEXT("@@CLIP_TYPING@@"),     // 1 typing: loop
  TEXT("@@CLIP_REACH@@")};     // 2 mouse: one play, then held on its last frame
 USkeletalMesh* BodyMesh=FirstPersonBody?FirstPersonBody->GetSkeletalMeshAsset():nullptr;StreamerVisualV2Clips.Reset();int32 Loaded=0;
 for(const TCHAR* Path:Paths){
  UAnimSequence* Clip=LoadObject<UAnimSequence>(nullptr,Path);
  if(!Clip||!BodyMesh||Clip->GetSkeleton()!=BodyMesh->GetSkeleton()||!(Clip->GetPlayLength()>.05f)){UE_LOG(LogTemp,Warning,TEXT("SUB01_STREAMER_VISUAL_CLIP_MISSING %s"),Path);Clip=nullptr;}else ++Loaded;
  StreamerVisualV2Clips.Add(Clip);
 }
 // Monitor framing from the body's own basis: the facing is the body axis (+-X/+-Y; imported meshes face +Y) that points at
 // the monitor bounds centre (SUB01_ACTUAL_PC_MONITOR_BOUND); camera = pivot -70 facing, +45 right, +45 up, aimed at the monitor.
 const FTransform BodyWorld=FirstPersonBody->GetComponentTransform();const FVector Pivot(214,-289,116),Monitor(217,-367.67,114.75);
 const FVector ToMonitor=FVector(Monitor.X-Pivot.X,Monitor.Y-Pivot.Y,0).GetSafeNormal();
 const FVector Axes[4]={BodyWorld.GetUnitAxis(EAxis::X),-BodyWorld.GetUnitAxis(EAxis::X),BodyWorld.GetUnitAxis(EAxis::Y),-BodyWorld.GetUnitAxis(EAxis::Y)};
 static const TCHAR* const AxisNames[4]={TEXT("+X"),TEXT("-X"),TEXT("+Y"),TEXT("-Y")};
 FVector Facing=FVector::ForwardVector;double Best=-2;int32 Chosen=0;
 for(int32 K=0;K<4;++K){const FVector Flat=FVector(Axes[K].X,Axes[K].Y,0).GetSafeNormal();const double Dot=FVector::DotProduct(Flat,ToMonitor);if(Dot>Best){Best=Dot;Facing=Flat;Chosen=K;}}
 const FVector Side=FVector::CrossProduct(FVector::UpVector,Facing); // UE is left-handed: Up x Facing = his right
 StreamerVisualMonitorLocation=Pivot+Facing*-70.+Side*45.+FVector(0,0,45);StreamerVisualMonitorLook=(Monitor-StreamerVisualMonitorLocation).Rotation();StreamerVisualMonitorAxis=AxisNames[Chosen];
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_V2_READY clips=%d/3 facingAxis=%s facingDot=%.3f monitorCamera=%s look=%s; v1 events keep the frozen R9 path"),Loaded,AxisNames[Chosen],Best,*StreamerVisualMonitorLocation.ToString(),*StreamerVisualMonitorLook.ToString());
}
bool ASub01HomeCharacter::ParseStreamerVisualV2(const TSharedPtr<FJsonObject>& J,FString& Frame,FString& State,double& Intensity,FString& Camera) const{
 // v2 = the v1 envelope (uid, mode, pid, start ticks, expiry, sequence, gaze, nod: checked by the caller) + state, intensity, camera.
 if(!J->TryGetStringField(TEXT("state"),State)||(State!=TEXT("idle")&&State!=TEXT("reading")&&State!=TEXT("typing")&&State!=TEXT("mouse")&&State!=TEXT("talking")&&State!=TEXT("reacting")))return false;
 Intensity=.5;if(J->HasField(TEXT("intensity"))&&!(J->TryGetNumberField(TEXT("intensity"),Intensity)&&FMath::IsFinite(Intensity)&&Intensity>=0&&Intensity<=1))return false;
 Camera=TEXT("spectator");if(J->HasField(TEXT("camera"))&&!(J->TryGetStringField(TEXT("camera"),Camera)&&(Camera==TEXT("spectator")||Camera==TEXT("monitor"))))return false;
 if(!J->HasField(TEXT("source_frame_id"))){Frame=TEXT("streamer_agent");return true;}
 return J->TryGetStringField(TEXT("source_frame_id"),Frame)&&!Frame.IsEmpty()&&Frame.Len()<=128;
}
void ASub01HomeCharacter::AcceptStreamerVisualV2(int32 Version,const FString& State,double Intensity,const FString& Camera,double Nod){
 if(Version!=StreamerVisualSchemaVersion)UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_SCHEMA v%d (was v%d)"),Version,StreamerVisualSchemaVersion);
 StreamerVisualSchemaVersion=Version;if(Version!=2)return; // v1: the unchanged frozen-R9 path (gaze, nod on every new event)
 StreamerVisualNod=0; // v2 nods only on entry into "reacting" (TickStreamerVisualV2), never on every event
 StreamerVisualRequestedState=State;StreamerVisualIntensity=float(Intensity);StreamerVisualRequestedCamera=Camera;StreamerVisualNodStrength=float(FMath::Clamp(Nod,0.,1.));
}
FRotator ASub01HomeCharacter::TickStreamerVisualV2(double Now){
 const bool Fresh=Now-StreamerVisualEventAt<=2; // same 2 s freshness as the gaze; stale -> idle + spectator camera
 const FString Wanted=Fresh?StreamerVisualRequestedState:FString(TEXT("idle"));
 // Debounce: at most one state change per 0.6 s (the latest request wins when the window ends); "reacting" applies at once.
 if(Wanted!=StreamerVisualState&&(Wanted==TEXT("reacting")||Now-StreamerVisualStateAt>=.6)){
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_STATE %s -> %s"),*StreamerVisualState,*Wanted);
  StreamerVisualState=Wanted;StreamerVisualStateAt=Now;
  if(Wanted==TEXT("reacting")){StreamerVisualNodAt=Now;StreamerVisualNodGain=StreamerVisualNodStrength>0?StreamerVisualNodStrength:.5f;}
 }
 StreamerVisualCameraTarget=Fresh?StreamerVisualRequestedCamera:FString(TEXT("spectator"));
 const double Scale=.5+.5*(Fresh?StreamerVisualIntensity:.5f),T=Now-StreamerVisualStartedAt; // intensity scales sway and nod
 FRotator Motion(1.5*Scale*Sub01StreamerVisualV2Noise(T*.16,0x51u),1.5*Scale*Sub01StreamerVisualV2Noise(T*.12,0xA7u),0); // sway <=1.5 deg
 if(StreamerVisualState==TEXT("talking")){Motion.Pitch+=.9*Scale*FMath::Sin(2*PI*1.3*T)*(.6+.4*FMath::Sin(2*PI*.37*T));Motion.Yaw+=.6*Scale*FMath::Sin(2*PI*.8*T+1.1);} // speech cadence <=0.9/0.6 deg
 const double Since=Now-StreamerVisualNodAt;if(Since>=0&&Since<=.75)Motion.Pitch+=FMath::Sin(Since/.75*2*PI)*6*StreamerVisualNodGain*Scale; // the v1 nod shape, once per entry
 return Motion;
}
void ASub01HomeCharacter::ApplyStreamerVisualV2(double Now,float Dt){
 auto* Anim=FirstPersonBody?Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()):nullptr;
 if(StreamerVisualSchemaVersion!=2){StreamerVisualActiveClip=StreamerVisualClip;StreamerVisualCameraTarget=TEXT("spectator");if(Anim)Anim->StreamerVisualV2=false;}
 else if(Anim){
  // idle/reading/talking/reacting -> sitting loop, typing -> typing loop, mouse -> reach played once and held; missing -> frozen R9.
  const int32 Slot=StreamerVisualState==TEXT("typing")?1:StreamerVisualState==TEXT("mouse")?2:0;
  UAnimSequence* Clip=StreamerVisualV2Clips.IsValidIndex(Slot)?StreamerVisualV2Clips[Slot].Get():nullptr;
  StreamerVisualActiveClip=Clip?Clip:StreamerVisualClip.Get();
  Anim->TargetSequence=StreamerVisualActiveClip;Anim->TargetRate=Clip?1.f:0.f;Anim->StreamerVisualV2=true;
  Anim->StreamerVisualFreezeSequence=StreamerVisualClip;Anim->StreamerVisualFreezeSeconds=.7f;Anim->StreamerVisualStartSeconds=0;
  Anim->StreamerVisualLoop=Slot!=2;Anim->StreamerVisualMatchHands=Clip!=nullptr&&Slot!=2;
  // Breathing: 0.6 deg at 0.22 Hz on Spine1, Spine2 lagging 1.1 rad (same local-rotation convention as the head offset).
  const double W=2*PI*.22*(Now-StreamerVisualStartedAt);
  Anim->StreamerVisualSpine1Offset=FRotator(.6*FMath::Sin(W),0,0);Anim->StreamerVisualSpine2Offset=FRotator(.6*FMath::Sin(W-1.1),0,0);
 }
 // Camera: "spectator" = the authored v1 view, untouched while it holds; "monitor" = over-the-shoulder framing, 1 s eased blend.
 const float Goal=StreamerVisualCameraTarget==TEXT("monitor")?1.f:0.f;
 if(ViewCamera&&(Goal>0||StreamerVisualCameraAlpha>0)){
  StreamerVisualCameraAlpha=Goal>StreamerVisualCameraAlpha?FMath::Min(Goal,StreamerVisualCameraAlpha+Dt):FMath::Max(Goal,StreamerVisualCameraAlpha-Dt);
  const float Ease=FMath::SmoothStep(0.f,1.f,StreamerVisualCameraAlpha);
  const FVector Location=FMath::Lerp(FVector(334,-209,151),StreamerVisualMonitorLocation,double(Ease));
  const FRotator Rotation=FQuat::Slerp(StreamerVisualSpectatorLook.Quaternion(),StreamerVisualMonitorLook.Quaternion(),double(Ease)).Rotator();
  ViewCamera->SetWorldLocationAndRotation(Location,Rotation);if(Controller)Controller->SetControlRotation(Rotation);
 }
}
// SUB01_STREAMER_VISUAL_V2 END
'''.replace('@@CLIP_SITTING@@', CLIPS['sitting'][0]).replace('@@CLIP_TYPING@@', CLIPS['typing'][0]).replace('@@CLIP_REACH@@', CLIPS['reach'][0])

TICK_ANCHOR = ('// Explicitly human-requested visual performance mode: NOT seated skill proof.\n'
               'bool ASub01HomeCharacter::TickPrivateStreamerVisual(float Dt){\n')
V1_SCHEMA_LINES = ('   J->TryGetStringField(TEXT("schema"),Schema)&&Schema==TEXT("sub01.private-streamer-visual-event.v1")&&\n'
                   '   J->TryGetStringField(TEXT("source"),Source)&&Source==TEXT("human_vagon_observation")&&J->TryGetStringField(TEXT("source_frame_id"),Frame)&&!Frame.IsEmpty()&&Frame.Len()<=128&&\n')
V1V2_SCHEMA_LINES = ('   J->TryGetStringField(TEXT("schema"),Schema)&&J->TryGetStringField(TEXT("source"),Source)&&( // SUB01_STREAMER_VISUAL_V2: v1 exactly as before, or v2\n'
                     '   (Schema==TEXT("sub01.private-streamer-visual-event.v1")&&Source==TEXT("human_vagon_observation")&&J->TryGetStringField(TEXT("source_frame_id"),Frame)&&!Frame.IsEmpty()&&Frame.Len()<=128)||\n'
                     '   (Schema==TEXT("sub01.private-streamer-visual-event.v2")&&Source==TEXT("streamer_agent")&&ParseStreamerVisualV2(J,Frame,V2State,V2Intensity,V2Camera)))&&\n')
ACCEPT_LINE = '  if(Valid&&uint64(Sequence)>StreamerVisualSequence){StreamerVisualSequence=uint64(Sequence);StreamerVisualDesired=FRotator(Pitch,Yaw,0);StreamerVisualNod=Nod;StreamerVisualEventAt=Now;StreamerVisualSourceFrame=Frame;}\n'
TARGET_LINE = ' FRotator Target=StreamerVisualDesired;const double Since=Now-StreamerVisualEventAt;if(Since>=0&&Since<=.75)Target.Pitch+=float(FMath::Sin(Since/.75*2*PI)*6*StreamerVisualNod);\n'
ANIM_LINE = ' if(auto* Anim=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance())){Anim->TargetSequence=StreamerVisualClip;Anim->TargetRate=0;Anim->StreamerVisualActive=true;Anim->StreamerVisualHeadOffset=StreamerVisualCurrent;}\n'
FOCUS_LINES = ' NativeSeatVerified=false;if(PCBridge)PCBridge->SetOperatorFocus(false);\n if(Now>=StreamerVisualPollAt){\n'
DECL_LINE = '  FString Raw;TSharedPtr<FJsonObject> J;FString Schema,Frame,Source;double PID=0,Start=0,At=0,Until=0,Sequence=0,Yaw=0,Pitch=0,Nod=0;\n'
RECEIPT_LINE = 'Receipt->SetStringField(TEXT("authored_head_offset"),StreamerVisualCurrent.ToString());\n'
RECEIPT_V2 = ('  {auto* V2Anim=Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()); // SUB01_STREAMER_VISUAL_V2 receipt fields; existing ones kept, "clip" = active clip\n'
              '   Receipt->SetNumberField(TEXT("schema_version"),StreamerVisualSchemaVersion);Receipt->SetStringField(TEXT("state"),StreamerVisualSchemaVersion==2?StreamerVisualState:FString(TEXT("v1_frozen")));Receipt->SetStringField(TEXT("requested_state"),StreamerVisualSchemaVersion==2?StreamerVisualRequestedState:FString(TEXT("v1_frozen")));\n'
              '   Receipt->SetStringField(TEXT("clip"),StreamerVisualActiveClip?StreamerVisualActiveClip->GetPathName():StreamerVisualClip->GetPathName());Receipt->SetStringField(TEXT("base_clip"),StreamerVisualClip->GetPathName());Receipt->SetBoolField(TEXT("clip_fallback_frozen"),!StreamerVisualActiveClip||StreamerVisualActiveClip==StreamerVisualClip);\n'
              '   Receipt->SetNumberField(TEXT("clip_time"),V2Anim?V2Anim->StreamerVisualEvaluatedTime:-1.f);Receipt->SetNumberField(TEXT("matched_start_seconds"),V2Anim?V2Anim->StreamerVisualMatchedSeconds:-1.f);Receipt->SetNumberField(TEXT("intensity"),StreamerVisualIntensity);Receipt->SetBoolField(TEXT("breathing"),StreamerVisualSchemaVersion==2);\n'
              '   Receipt->SetStringField(TEXT("camera"),StreamerVisualCameraTarget);Receipt->SetNumberField(TEXT("camera_blend"),StreamerVisualCameraAlpha);Receipt->SetStringField(TEXT("monitor_camera_facing_axis"),StreamerVisualMonitorAxis);}\n')

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.h
HANDS_FIELDS = r''' // SUB01_STREAMER_VISUAL_V2 BEGIN (tools/native_streamer_visual_v2/install.py): written by the character every tick.
 UPROPERTY(Transient) bool StreamerVisualV2=false;
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> StreamerVisualFreezeSequence;
 UPROPERTY(Transient) float StreamerVisualFreezeSeconds=.7f;
 UPROPERTY(Transient) float StreamerVisualStartSeconds=0;
 UPROPERTY(Transient) bool StreamerVisualLoop=true;
 UPROPERTY(Transient) bool StreamerVisualMatchHands=false;
 UPROPERTY(Transient) FRotator StreamerVisualSpine1Offset=FRotator::ZeroRotator;
 UPROPERTY(Transient) FRotator StreamerVisualSpine2Offset=FRotator::ZeroRotator;
 // Published after evaluation: the Current player time and the hand-matched start phase (-1 when none).
 UPROPERTY(Transient) float StreamerVisualEvaluatedTime=-1;
 UPROPERTY(Transient) float StreamerVisualMatchedSeconds=-1;
 // SUB01_STREAMER_VISUAL_V2 END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.cpp
PROXY_MEMBERS = r''' // SUB01_STREAMER_VISUAL_V2 BEGIN (tools/native_streamer_visual_v2/install.py): curated clips through the same Previous/Current
 // crossfade; a fresh loop starts at the phase whose hands are closest to the last evaluated hands; additive breathing on
 // Spine1/Spine2, found like the Head bone (exact name, else the bone whose name ends with it). Raw sequence keys are compared only.
 bool StreamerV2=false,StreamerV2Fresh=false,StreamerV2Entered=false,StreamerV2Match=false,StreamerV2HandsValid=false;
 FRotator StreamerV2Spine[2]={FRotator::ZeroRotator,FRotator::ZeroRotator};FVector StreamerV2Hands[2]={FVector::ZeroVector,FVector::ZeroVector};
 int32 StreamerV2BoneCount=-1,StreamerV2Bones[4]={INDEX_NONE,INDEX_NONE,INDEX_NONE,INDEX_NONE},StreamerV2PhaseNext=0;float StreamerV2MatchedSeconds=-1;
 static constexpr int32 StreamerV2PhaseCount=24;
 struct FStreamerV2Phases{const UAnimSequenceBase* Key=nullptr;float Length=0;TArray<FVector> Points;};FStreamerV2Phases StreamerV2Phases[4];
 FAnimNode_SequencePlayer_Standalone StreamerV2Probe;
 void ResolveStreamerV2(const FReferenceSkeleton& Ref){
  if(StreamerV2BoneCount==Ref.GetNum())return;StreamerV2BoneCount=Ref.GetNum();
  static const TCHAR* const Names[4]={TEXT("Spine1"),TEXT("Spine2"),TEXT("LeftHand"),TEXT("RightHand")};
  for(int32 K=0;K<4;++K){int32 Index=Ref.FindBoneIndex(FName(Names[K]));for(int32 B=0;Index==INDEX_NONE&&B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(Names[K]))Index=B;StreamerV2Bones[K]=Index;}
 }
 static bool StreamerV2Component(const FCompactPose& Source,int32 MeshBone,FVector& Position){
  if(MeshBone==INDEX_NONE)return false;const auto& Bones=Source.GetBoneContainer();const auto& Ref=Bones.GetReferenceSkeleton();FTransform T=FTransform::Identity;int32 Guard=0;
  for(int32 B=MeshBone;B!=INDEX_NONE;B=Ref.GetParentIndex(B)){if(++Guard>512)return false;const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(Compact.GetInt()<0)return false;T=T*Source[Compact];}
  Position=T.GetTranslation();return !Position.ContainsNaN();
 }
 void PreUpdateStreamerV2(USub01HomeHandsInstance* Hands){
  UAnimSequenceBase* Seq=Current.GetSequence();
  if(Seq&&Seq==Hands->StreamerVisualFreezeSequence.Get()){Current.SetLoopAnimation(false);Current.SetAccumulatedTime(Hands->StreamerVisualFreezeSeconds);Current.SetPlayRate(0);StreamerV2Match=false;}
  else if(StreamerV2Fresh&&Seq&&Seq==Hands->TargetSequence.Get()){Current.SetLoopAnimation(Hands->StreamerVisualLoop);Current.SetAccumulatedTime(FMath::Clamp(Hands->StreamerVisualStartSeconds,0.f,float(Seq->GetPlayLength())));StreamerV2Match=Hands->StreamerVisualMatchHands&&Hands->StreamerVisualLoop;}
  if(!StreamerV2Entered){StreamerV2Entered=true;Progress=1;StreamerV2Match=false;} // first v2 frame: instant placement, as v1
 }
 void MatchStreamerV2Phase(FPoseContext& Output){
  StreamerV2Match=false;UAnimSequenceBase* Seq=Current.GetSequence();if(!Seq||!StreamerV2HandsValid||!Current.IsLooping())return;
  const float Length=float(Seq->GetPlayLength());if(!(Length>.05f))return;
  ResolveStreamerV2(Output.Pose.GetBoneContainer().GetReferenceSkeleton());if(StreamerV2Bones[2]==INDEX_NONE||StreamerV2Bones[3]==INDEX_NONE)return;
  FStreamerV2Phases* Table=nullptr;for(auto& Entry:StreamerV2Phases)if(Entry.Key==Seq&&Entry.Length==Length&&Entry.Points.Num()==2*StreamerV2PhaseCount)Table=&Entry;
  if(!Table){ // once per clip: component-space hands of the clip itself at 24 phases (the same sequence-player evaluation as Current)
   Table=&StreamerV2Phases[StreamerV2PhaseNext];StreamerV2PhaseNext=(StreamerV2PhaseNext+1)%4;Table->Key=Seq;Table->Length=Length;Table->Points.Reset();
   StreamerV2Probe.SetSequence(Seq);StreamerV2Probe.SetLoopAnimation(true);StreamerV2Probe.SetPlayRate(0);
   for(int32 K=0;K<StreamerV2PhaseCount;++K){
    StreamerV2Probe.SetAccumulatedTime(Length*K/StreamerV2PhaseCount);FPoseContext Probe(Output.AnimInstanceProxy);StreamerV2Probe.Evaluate_AnyThread(Probe);
    FVector L=FVector::ZeroVector,R=FVector::ZeroVector;if(!StreamerV2Component(Probe.Pose,StreamerV2Bones[2],L)||!StreamerV2Component(Probe.Pose,StreamerV2Bones[3],R)){Table->Key=nullptr;Table->Points.Reset();return;}
    Table->Points.Add(L);Table->Points.Add(R);
   }
  }
  int32 Best=0;double BestCost=DBL_MAX;
  for(int32 K=0;K<StreamerV2PhaseCount;++K){const double Cost=FVector::DistSquared(Table->Points[2*K],StreamerV2Hands[0])+FVector::DistSquared(Table->Points[2*K+1],StreamerV2Hands[1]);if(Cost<BestCost){BestCost=Cost;Best=K;}}
  StreamerV2MatchedSeconds=Length*Best/StreamerV2PhaseCount;Current.SetAccumulatedTime(StreamerV2MatchedSeconds);
 }
 void EvaluateStreamerV2(FPoseContext& Output){
  const auto& Bones=Output.Pose.GetBoneContainer();ResolveStreamerV2(Bones.GetReferenceSkeleton());
  StreamerV2HandsValid=StreamerV2Component(Output.Pose,StreamerV2Bones[2],StreamerV2Hands[0])&&StreamerV2Component(Output.Pose,StreamerV2Bones[3],StreamerV2Hands[1]);
  for(int32 K=0;K<2;++K)if(StreamerV2Bones[K]!=INDEX_NONE){const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(StreamerV2Bones[K]));if(Compact.GetInt()>=0){auto& T=Output.Pose[Compact];T.SetRotation((T.GetRotation()*StreamerV2Spine[K].Quaternion()).GetNormalized());}}
 }
 // SUB01_STREAMER_VISUAL_V2 END
'''
V1_PROXY_FREEZE = '  if(StreamerVisualActive){Current.SetLoopAnimation(false);Current.SetAccumulatedTime(.7f);Current.SetPlayRate(0);Progress=1;}\n'

# (file key, anchor, replacement). Each anchor must occur exactly once in the text as left by the previous edits.
EDITS = [
    ('header', ' UPROPERTY() TObjectPtr<UAnimSequence> StreamerVisualClip;\n',
     ' UPROPERTY() TObjectPtr<UAnimSequence> StreamerVisualClip;\n' + HEADER_FIELDS),
    ('cpp', TICK_ANCHOR, CPP_METHODS + TICK_ANCHOR),
    ('cpp', '  StreamerVisualStarted=true;\n',
     '  StreamerVisualStarted=true;\n  StartStreamerVisualV2(Look); // SUB01_STREAMER_VISUAL_V2: clips, monitor framing\n'),
    ('cpp', FOCUS_LINES,
     ' NativeSeatVerified=false;if(PCBridge&&PCBridge->HasOperatorFocus())PCBridge->SetOperatorFocus(false); // SUB01_STREAMER_VISUAL_V2: an unfocused call only POSTs /pc/session and redraws the canvas every tick\n'
     ' if(Now>=StreamerVisualPollAt){\n'),
    ('cpp', DECL_LINE, DECL_LINE + '  FString V2State,V2Camera;double V2Intensity=.5; // SUB01_STREAMER_VISUAL_V2\n'),
    ('cpp', V1_SCHEMA_LINES, V1V2_SCHEMA_LINES),
    ('cpp', ACCEPT_LINE,
     '  const bool V2Accept=Valid&&uint64(Sequence)>StreamerVisualSequence; // SUB01_STREAMER_VISUAL_V2\n' + ACCEPT_LINE +
     '  if(V2Accept)AcceptStreamerVisualV2(Schema==TEXT("sub01.private-streamer-visual-event.v2")?2:1,V2State,V2Intensity,V2Camera,Nod); // SUB01_STREAMER_VISUAL_V2\n'),
    ('cpp', TARGET_LINE,
     TARGET_LINE + ' if(StreamerVisualSchemaVersion==2)Target+=TickStreamerVisualV2(Now); // SUB01_STREAMER_VISUAL_V2: state debounce, sway, talking, reacting nod (bounded)\n'),
    ('cpp', ANIM_LINE,
     ANIM_LINE + ' ApplyStreamerVisualV2(Now,Dt); // SUB01_STREAMER_VISUAL_V2: state clip, breathing, camera (v1: frozen R9, spectator)\n'),
    ('cpp', RECEIPT_LINE, RECEIPT_LINE + RECEIPT_V2),
    ('hands_header', ' UPROPERTY(Transient) FRotator StreamerVisualHeadOffset=FRotator::ZeroRotator;\n',
     ' UPROPERTY(Transient) FRotator StreamerVisualHeadOffset=FRotator::ZeroRotator;\n' + HANDS_FIELDS),
    ('hands_cpp', ' bool StreamerVisualActive=false;FRotator StreamerVisualHeadOffset=FRotator::ZeroRotator;\n',
     ' bool StreamerVisualActive=false;FRotator StreamerVisualHeadOffset=FRotator::ZeroRotator;\n' + PROXY_MEMBERS),
    ('hands_cpp', 'PhoneSeatBase.Initialize_AnyThread(Context);\n',
     'PhoneSeatBase.Initialize_AnyThread(Context);StreamerV2Probe.Initialize_AnyThread(Context); // SUB01_STREAMER_VISUAL_V2\n'),
    ('hands_cpp', '  StreamerVisualActive=Hands->StreamerVisualActive;StreamerVisualHeadOffset=Hands->StreamerVisualHeadOffset;\n',
     '  StreamerVisualActive=Hands->StreamerVisualActive;StreamerVisualHeadOffset=Hands->StreamerVisualHeadOffset;\n'
     '  StreamerV2=Hands->StreamerVisualV2;StreamerV2Spine[0]=Hands->StreamerVisualSpine1Offset;StreamerV2Spine[1]=Hands->StreamerVisualSpine2Offset; // SUB01_STREAMER_VISUAL_V2\n'),
    ('hands_cpp', '   Current.SetSequence(Hands->TargetSequence); Current.SetAccumulatedTime(0);\n',
     '   Current.SetSequence(Hands->TargetSequence); Current.SetAccumulatedTime(0);\n'
     '   StreamerV2Fresh=true; // SUB01_STREAMER_VISUAL_V2: a fresh switch (never the reversal swap) may take a start phase\n'),
    ('hands_cpp', V1_PROXY_FREEZE,
     '  if(StreamerVisualActive&&!StreamerV2){Current.SetLoopAnimation(false);Current.SetAccumulatedTime(.7f);Current.SetPlayRate(0);Progress=1;}\n'
     '  if(StreamerVisualActive&&StreamerV2)PreUpdateStreamerV2(Hands);else StreamerV2Entered=false; // SUB01_STREAMER_VISUAL_V2: no forced Progress, crossfades run\n'
     '  StreamerV2Fresh=false;\n'),
    ('hands_cpp', '  if(EvaluateCinema(Output))return true;\n  Blend.Evaluate_AnyThread(Output);\n',
     '  if(EvaluateCinema(Output))return true;\n'
     '  if(StreamerV2Match&&StreamerVisualActive&&StreamerV2)MatchStreamerV2Phase(Output);StreamerV2Match=false; // SUB01_STREAMER_VISUAL_V2\n'
     '  Blend.Evaluate_AnyThread(Output);\n'),
    ('hands_cpp', '  if(StreamerVisualActive){\n',
     '  if(StreamerVisualActive){\n'
     '   if(StreamerV2)EvaluateStreamerV2(Output); // SUB01_STREAMER_VISUAL_V2: reference hands (pre-additive), then breathing; head below\n'),
    ('hands_cpp', ' PhoneCompositionEvaluated=Proxy.PhoneCompositionEvaluated;\n',
     ' PhoneCompositionEvaluated=Proxy.PhoneCompositionEvaluated;\n'
     ' StreamerVisualEvaluatedTime=Proxy.StreamerV2?Proxy.Current.GetAccumulatedTime():-1.f;StreamerVisualMatchedSeconds=Proxy.StreamerV2MatchedSeconds; // SUB01_STREAMER_VISUAL_V2\n'),
]


# ------------------------------------------------------------------------------------------------ text checks
def strip_code(text: str) -> str:
    """Comments and string/char literal contents become spaces (newlines kept) so braces can be counted."""
    out, i, n = list(text), 0, len(text)
    while i < n:
        c = text[i]
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                out[i] = ' '
                i += 1
        elif c == '/' and i + 1 < n and text[i + 1] == '*':
            end = text.find('*/', i + 2)
            end = n if end < 0 else end + 2
            for k in range(i, end):
                if text[k] != '\n':
                    out[k] = ' '
            i = end
        elif c in '"\'':
            k = i + 1
            while k < n and text[k] != c and text[k] != '\n':
                if text[k] == '\\':
                    out[k] = ' '
                    k += 1
                if k < n:
                    out[k] = ' '
                k += 1
            i = k + 1
        else:
            i += 1
    return ''.join(out)


def balance(text: str) -> dict:
    s = strip_code(text)
    out = {}
    for opener, closer in ('{}', '()', '[]'):
        depth = low = 0
        for c in s:
            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                low = min(low, depth)
        out[opener + closer] = (depth, low)
    return out


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ------------------------------------------------------------------------------------------------ plan / apply
def plan(sources: dict) -> dict:
    """Pure transformation of {'header','cpp','hands_header','hands_cpp'} texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (v2 already installed)' for key in FILES if MARKER in sources[key]]
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
        before, after = balance(sources[key]), balance(out[key])
        if after != before:
            raise Refused(f'{FILES[key]}: bracket balance changed by the install {before} -> {after}')
        if MARKER not in out[key]:
            raise Refused(f'{FILES[key]}: marker missing after install')
    return {'sources': out, 'edits': edits}


def line_ending(name: str, raw: str) -> str:
    """'\\r\\n' when every line ends in CRLF (the pod copies do), '\\n' when none does; mixed files are refused."""
    crlf, lf = raw.count('\r\n'), raw.count('\n')
    if crlf and crlf != lf or '\r' in raw.replace('\r\n', ''):
        raise Refused(f'{name}: mixed line endings ({crlf} CRLF of {lf} lines); normalize it before installing')
    return '\r\n' if crlf else '\n'


def read_raw(path: Path) -> str:
    with open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


def read_sources(source: Path) -> tuple:
    """({key: raw text}, {key: line ending}); anchors and replacements are LF, applied to the LF view of each file."""
    missing = [name for name in [*FILES.values(), *(n for n, _ in READ_ONLY.values())] if not (source / name).is_file()]
    if missing:
        raise Refused(f'missing in {source}: {", ".join(missing)}')
    raw, eol = {}, {}
    for key, name in FILES.items():
        raw[key] = read_raw(source / name)
        eol[key] = line_ending(name, raw[key])
    for name, needle in READ_ONLY.values():
        if needle not in read_raw(source / name):
            raise Refused(f'{name} lacks `{needle}` that the v2 streamer branch calls')
    return raw, eol


def write_atomically(files: dict) -> None:
    """Write every file to a temporary sibling first, then rename them all (no partial install on a write error)."""
    staged = []
    try:
        for path, text in files.items():
            fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.v2tmp', dir=path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, path.stat().st_mode & 0o7777)
            staged.append((tmp, path))
        for tmp, path in staged:
            os.replace(tmp, path)
        staged = []
    finally:
        for tmp, _ in staged:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def run(source: Path, dry_run: bool) -> dict:
    source = Path(source).resolve()
    report = {'schema': 'sub01.native-streamer-visual-v2-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'event_schemas': [SCHEMA_V1, SCHEMA_V2], 'states': list(STATES),
              'clips': {slot: {'path': path, 'loop': loop, 'states': list(states)} for slot, (path, loop, states) in CLIPS.items()},
              'fallback_clip': R9_CLIP}
    raw, eol = read_sources(source)
    result = plan({key: text.replace('\r\n', '\n') for key, text in raw.items()})
    after = {key: result['sources'][key].replace('\n', eol[key]) for key in FILES}
    report['edits'] = result['edits']
    report['files'] = {FILES[key]: {'before_sha256': sha256(raw[key]), 'after_sha256': sha256(after[key]),
                                    'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                    'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                    'edits': sum(1 for k, _, _ in EDITS if k == key)} for key in FILES}
    report['read_only'] = {name: sha256(read_raw(source / name)) for name, _ in READ_ONLY.values()}
    if not dry_run:
        write_atomically({source / FILES[key]: after[key] for key in FILES})
        for key in FILES:
            if sha256(read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the five pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
