"""Stream pass ON TOP of the seat fix: hands IK on the keyboard/mouse, typing posture, body LOD/material look, key light, perf.

    python tools/native_streamer_visual_v2/install_stream_pass.py --source <dir> [--dry-run]

Requires the seat fix (install_seat_fix.py) in all four files; refused when `// SUB01_STREAMER_VISUAL_V2_STREAMPASS`
is already present or any anchor is not found exactly once. Same atomic writes, line endings and JSON report.
Everything new is tunable live from the seat fix's private tuning file (`streamer-visual-face-tuning.json`); the
defaults follow the reviewed hands recipe (docs/streamer/kimi/posture.md, section 3):

1. Hands: own two-bone solve (no AnimationCore node) on LeftArm/LeftForeArm/LeftHand and Right*, in component space
   after breathing/posture and before the head: the upper arm turns by the minimal rotation onto the new elbow, the
   forearm is carried with it and then bent at the elbow (hinge-like, no forearm roll), bone lengths kept, the hand's
   local rotation untouched; slerp-blended with an alpha eased over HAND_BLEND_SECONDS. The bend plane is the clip's (the
   previous frame's when it degenerates), pulled towards an elbow pole "down, back and slightly out" by `elbow_pole` (0 = the
   clip's plane; nearly opposite directions take the pole instead of flipping through zero). Targets (world,
   converted to component space every tick) are WRIST positions on the keyboard body (the widest follower of the seat
   fix's keyboard pack, its bounds centre): `hand_span_cm` apart (recipe 18-22), `hand_back_cm` towards him from the
   keyboard's centre line, `hand_height_cm` above the desk (the keyboard's bottom; recipe 4-5); in `mouse` the right wrist
   goes behind the mouse prop (`mouse_back_cm`) if the level has one (any actor with a primitive in MOUSE_ZONE, small,
   not the keyboard/desk pack; it then follows the pull-back) else to the tuning point `mouse_x/y/z`. A target change
   glides in `hand_move_s` (recipe 0.25 s) on a `hand_arc_cm` (recipe 4) high arc, eased; the left hand stays planted.
   Optional finger curl: `finger_curl_deg` added to the proximal (x1) and middle (x1.2) phalanges of index..pinky about
   the local axis `finger_curl_axis` (0/1/2 = X/Y/Z), scaled by the IK alpha (default 0 = the clip's curl; the measured
   curl is logged so the recipe's 20-35 / 25-40 deg can be checked first). Log `SUB01_STREAMER_VISUAL_HANDS target=...
   reach=... alpha=... elbow=... fingers=...`; receipt `hand_left`/`hand_right` ("<target> <distance cm>"),
   `hands_alpha`, `elbow_left_deg`/`elbow_right_deg` (recipe 85-100), `finger_curl_deg_measured`, `mouse_prop`.
2. Typing posture: `typing_lean_deg` / `typing_head_deg` added to the seat fix's posture targets while the typing loop
   plays (same 12 deg/s easing); `desk_base` 1 makes the typing loop the desk-work base (every state but `reading`).
   The chair follows the seat pull-back (`chair_back_cm` -1) or its own distance.
3. Body look: `forced_lod` (default 1 = LOD0 forced in streamer mode) and `hide_slot` (material slot hidden at LOD0,
   -1 = none) applied on change; the body's material slot names and LOD count logged once
   (`SUB01_STREAMER_VISUAL_BODY_LOOK`) so the collar can be diagnosed from the log.
4. Key light: a movable SpotLight created at v2 start (candelas, temperature KEY_LIGHT_TEMP_K, cones 25/45 deg,
   300 cm, no shadows) sitting KEY_LIGHT_UP_CM above the monitor centre, 6 cm towards him and the face camera's side
   offset to his left, aimed at the face camera's head mean (else the Head bone sampled every 2 s); `key_light` 0..1
   scales KEY_LIGHT_MAX_CD (0 hides it); `key_light_temp_k`, `key_light_up_cm`. Log `SUB01_STREAMER_VISUAL_KEY_LIGHT`.
5. Perf: `SUB01_STREAMER_VISUAL_PERF fps= ms= max_ms= gpu_ms=` every PERF_LOG_SECONDS (the wall clock between ticks; the RHI
   GPU frame time sampled once per tick, -1 when unavailable); receipt `fps`, `frame_ms`, `frame_max_ms`, `gpu_ms`.
The new engine headers are included at the top of Sub01HomeLab.cpp: StartStreamerVisualV2 (which creates the light)
comes before the appended methods block (build v20 failed on an incomplete USpotLightComponent).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_seatfix', Path(__file__).resolve().parent / 'install_seat_fix.py')
seatfix = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seatfix)
nopin, pinfix, face, v2, Refused = seatfix.nopin, seatfix.pinfix, seatfix.face, seatfix.v2, seatfix.Refused

MARKER = '// SUB01_STREAMER_VISUAL_V2_STREAMPASS'
FILES = dict(v2.FILES)
# Hands recipe (docs/streamer/kimi/posture.md 3): wrists 4-5 cm above the desk, home-row wrists 18-22 cm apart, elbows
# 85-100 deg (measured, logged), right wrist to the mouse in 0.25 s on a 4 cm arc, left hand planted.
HAND_BLEND_SECONDS = 0.3                  # IK alpha in/out
HAND_HEIGHT_CM = 4.5                      # wrist above the desk (the keyboard body's bottom)
HAND_SPAN_CM = 20.0                       # left/right wrist distance
HAND_BACK_CM = 13.0                       # wrists towards him from the keyboard centre line (curled fingers reach the home row)
HAND_MOVE_SECONDS, HAND_ARC_CM = 0.25, 4.0
HAND_GLIDE_RESTART_CM = 2.0               # a goal jump above this starts a new glide; smaller drift (props following) is tracked
ELBOW_POLE = 0.5                          # 0 = the clip's bend plane, 1 = the pole (down, back, slightly out)
ELBOW_POLE_VECTOR = (-1.0, 0.5, 0.3)      # (up, back, out) weights of the pole in his frame: down, back, out
FINGER_CURL_DEG, FINGER_CURL_AXIS = 0.0, 2
FINGER_MIDDLE_FACTOR = 1.2
MOUSE_BACK_CM = 7.0                       # the wrist behind the mouse prop's centre (palm on the mouse)
DESK_BASE, CHAIR_BACK_CM = 1, -1.0  # desk_base 1: the typing loop is the desk-work base, the reading loop only for `reading`; chair_back_cm -1 = the chair follows the seat pull-back
MOUSE_POINT = (237.0, -333.0, 82.0)
MOUSE_ZONE = {'x': (225, 256), 'y': (-346, -318), 'z': (70, 96)}
MOUSE_MAX_EXTENT = (12, 12, 8)
TYPING_LEAN_DEG, TYPING_HEAD_DEG = -6.0, 15.0  # visual QA 2026-10-23: the typing loop bows the head (crown only); 15-20 deg of extension wanted (needs the pose fix axes)
KEY_LIGHT_LEVEL, KEY_LIGHT_MAX_CD, KEY_LIGHT_TEMP_K, KEY_LIGHT_UP_CM = 0.5, 2500.0, 4500.0, 25.0
FORCED_LOD, HIDE_SLOT = 1, -1
PERF_LOG_SECONDS = 30.0
FINGERS = ('Index', 'Middle', 'Ring', 'Pinky')
TUNING_LIMITS = {'hands_ik': (0, 1), 'hand_height_cm': (0, 15), 'hand_span_cm': (12, 40), 'hand_back_cm': (-10, 25), 'hand_move_s': (0.1, 1),
                 'hand_arc_cm': (0, 10), 'elbow_pole': (0, 1), 'finger_curl_deg': (-30, 45), 'finger_curl_axis': (0, 2), 'mouse_back_cm': (0, 15),
                 'mouse_x': (0, 600), 'mouse_y': (-600, 600), 'mouse_z': (0, 200),
                 'typing_lean_deg': (-20, 20), 'typing_head_deg': (-20, 20), 'key_light': (0, 1), 'key_light_temp_k': (2500, 8000),
                 'key_light_up_cm': (-20, 80), 'hide_slot': (-1, 32), 'forced_lod': (0, 8), 'desk_base': (0, 1), 'chair_back_cm': (-1, 40)}
TUNING_FIELDS = {'hands_ik': 'StreamerVisualHandsIK', 'hand_height_cm': 'StreamerVisualHandHeightCm', 'hand_span_cm': 'StreamerVisualHandSpanCm',
                 'hand_back_cm': 'StreamerVisualHandBackCm', 'hand_move_s': 'StreamerVisualHandMoveS', 'hand_arc_cm': 'StreamerVisualHandArcCm',
                 'elbow_pole': 'StreamerVisualElbowPole', 'finger_curl_deg': 'StreamerVisualFingerCurlDeg', 'finger_curl_axis': 'StreamerVisualFingerCurlAxis',
                 'mouse_back_cm': 'StreamerVisualMouseBackCm', 'mouse_x': 'StreamerVisualMouseX', 'mouse_y': 'StreamerVisualMouseY', 'mouse_z': 'StreamerVisualMouseZ',
                 'typing_lean_deg': 'StreamerVisualTypingLeanDeg', 'typing_head_deg': 'StreamerVisualTypingHeadDeg', 'key_light': 'StreamerVisualKeyLightLevel',
                 'key_light_temp_k': 'StreamerVisualKeyLightTempK', 'key_light_up_cm': 'StreamerVisualKeyLightUpCm', 'hide_slot': 'StreamerVisualHideSlot',
                 'forced_lod': 'StreamerVisualForcedLod', 'desk_base': 'StreamerVisualDeskBase', 'chair_back_cm': 'StreamerVisualChairBackCm'}
assert set(TUNING_FIELDS) == set(TUNING_LIMITS)


def _f(value: float) -> str:
    """A C++ float literal: 0.5 -> 0.5f, 25 -> 25.f (never 0.5.f)."""
    text = f'{value:g}'
    return text + ('f' if '.' in text or 'e' in text else '.f')


def _line(text: str, start: str) -> str:
    hits = [line for line in text.splitlines(keepends=True) if line.startswith(start)]
    if len(hits) != 1:
        raise RuntimeError(f'expected one line starting with {start!r}, found {len(hits)}')
    return hits[0]


# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_SEAT_END = ' // SUB01_STREAMER_VISUAL_V2_SEATFIX END\n'
HEADER_FIELDS = f''' // SUB01_STREAMER_VISUAL_V2_STREAMPASS BEGIN (tools/native_streamer_visual_v2/install_stream_pass.py): hands IK targets, typing posture,
 // body look (forced LOD / hidden slot), key light, mouse prop scan, perf window. All live from the seat fix's tuning file.
 void UpdateStreamerVisualHands(class USub01HomeHandsInstance* Anim,float Dt);void UpdateStreamerVisualKeyLight(double Now);void ApplyStreamerVisualBodyLook();void ScanStreamerVisualMouse();
 UPROPERTY() TObjectPtr<class USpotLightComponent> StreamerVisualKeyLight;
 TWeakObjectPtr<AActor> StreamerVisualKeyboardActor,StreamerVisualMouseActor;FVector StreamerVisualKeyboardExtent=FVector::ZeroVector,StreamerVisualMouseExtent=FVector::ZeroVector,StreamerVisualKeyboardCentreOffset=FVector::ZeroVector,StreamerVisualMouseCentreOffset=FVector::ZeroVector;
 FVector StreamerVisualHandWorld[2]={{FVector::ZeroVector,FVector::ZeroVector}},StreamerVisualKeyLightAim=FVector::ZeroVector;FString StreamerVisualHandTargetName[2];
 float StreamerVisualHandAlpha=0,StreamerVisualHandDist[2]={{-1,-1}},StreamerVisualElbowDeg[2]={{-1,-1}},StreamerVisualFingerCurlMeasured[4]={{-1,-1,-1,-1}};bool StreamerVisualHandWorldValid=false;double StreamerVisualHandsLogAt=0,StreamerVisualKeyLightSampleAt=0;
 float StreamerVisualHandsIK=1,StreamerVisualHandHeightCm={_f(HAND_HEIGHT_CM)},StreamerVisualHandSpanCm={_f(HAND_SPAN_CM)},StreamerVisualHandBackCm={_f(HAND_BACK_CM)},StreamerVisualHandMoveS={_f(HAND_MOVE_SECONDS)},StreamerVisualHandArcCm={_f(HAND_ARC_CM)};
 float StreamerVisualElbowPole={_f(ELBOW_POLE)},StreamerVisualFingerCurlDeg={_f(FINGER_CURL_DEG)},StreamerVisualFingerCurlAxis={_f(FINGER_CURL_AXIS)},StreamerVisualMouseBackCm={_f(MOUSE_BACK_CM)};
 float StreamerVisualMouseX={_f(MOUSE_POINT[0])},StreamerVisualMouseY={_f(MOUSE_POINT[1])},StreamerVisualMouseZ={_f(MOUSE_POINT[2])};
 float StreamerVisualTypingLeanDeg={_f(TYPING_LEAN_DEG)},StreamerVisualTypingHeadDeg={_f(TYPING_HEAD_DEG)};
 float StreamerVisualKeyLightLevel={_f(KEY_LIGHT_LEVEL)},StreamerVisualKeyLightTempK={_f(KEY_LIGHT_TEMP_K)},StreamerVisualKeyLightUpCm={_f(KEY_LIGHT_UP_CM)},StreamerVisualKeyLightApplied=-1;
 float StreamerVisualHideSlot={_f(HIDE_SLOT)},StreamerVisualForcedLod={_f(FORCED_LOD)},StreamerVisualHideSlotApplied=-1,StreamerVisualForcedLodApplied=-99;
 float StreamerVisualDeskBase={_f(DESK_BASE)},StreamerVisualChairBackCm={_f(CHAIR_BACK_CM)};bool StreamerVisualTypingBase=false;FVector StreamerVisualChairDelta=FVector::ZeroVector,StreamerVisualChairDeltaApplied=FVector::ZeroVector;TArray<bool> StreamerVisualDeskPropIsChair;
 FVector StreamerVisualHandMoveFrom[2]={{FVector::ZeroVector,FVector::ZeroVector}},StreamerVisualHandMoveTo[2]={{FVector::ZeroVector,FVector::ZeroVector}},StreamerVisualHandSent[2]={{FVector::ZeroVector,FVector::ZeroVector}};double StreamerVisualHandMoveP[2]={{1,1}};
 // Frame-time window for SUB01_STREAMER_VISUAL_PERF (every {PERF_LOG_SECONDS:g} s) and the receipt's fps / frame_ms.
 void UpdateStreamerVisualPerf(double Now,float Dt);
 double StreamerVisualPerfWindowAt=0,StreamerVisualPerfWindowStart=0,StreamerVisualPerfLastNow=0,StreamerVisualPerfMaxMs=0,StreamerVisualPerfGpuSumMs=0;int32 StreamerVisualPerfFrames=0,StreamerVisualPerfGpuSamples=0;float StreamerVisualPerfFps=0,StreamerVisualPerfFrameMs=0,StreamerVisualPerfMaxFrameMs=0,StreamerVisualPerfGpuMs=0;
 // SUB01_STREAMER_VISUAL_V2_STREAMPASS END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
CPP_TOP = '#include "Sub01HomeLab.h"\n'
CPP_TOP_INCLUDES = (CPP_TOP + '#include "Components/SpotLightComponent.h" // SUB01_STREAMER_VISUAL_V2_STREAMPASS: ahead of StartStreamerVisualV2 (the key light), which precedes the appended methods\n'
                    '#include "Components/InstancedStaticMeshComponent.h"\n#include "RHI.h"\n')
CPP_SEAT_BEGIN = '// SUB01_STREAMER_VISUAL_V2_SEATFIX BEGIN (tools/native_streamer_visual_v2/install_seat_fix.py)\n#include "Animation/MorphTarget.h"\n'
CPP_METHODS = f'''// SUB01_STREAMER_VISUAL_V2_STREAMPASS BEGIN (tools/native_streamer_visual_v2/install_stream_pass.py)
void ASub01HomeCharacter::UpdateStreamerVisualPerf(double Now,float Dt){{
 // Frame time from the WALL clock between ticks (the game's delta can be clamped, smoothed or dilated): fps = frames / window,
 // frame_ms = window / frames, max_ms = the longest tick gap; GPU time = the mean of the RHI's last-frame samples that were non-zero
 // (sampled once per tick: an estimate; -1 when the RHI reports none). Logged once per {PERF_LOG_SECONDS:g} s window; the last window in the receipt.
 (void)Dt;if(StreamerVisualPerfLastNow<=0||Now<StreamerVisualPerfLastNow){{ // the first tick (or a clock step back): a clean window
  StreamerVisualPerfLastNow=StreamerVisualPerfWindowStart=Now;StreamerVisualPerfWindowAt=Now+{PERF_LOG_SECONDS:g};StreamerVisualPerfMaxMs=StreamerVisualPerfGpuSumMs=0;StreamerVisualPerfFrames=StreamerVisualPerfGpuSamples=0;return;}}
 StreamerVisualPerfMaxMs=FMath::Max(StreamerVisualPerfMaxMs,(Now-StreamerVisualPerfLastNow)*1000.);StreamerVisualPerfLastNow=Now;++StreamerVisualPerfFrames;
 const uint32 Cycles=RHIGetGPUFrameCycles();if(Cycles>0){{StreamerVisualPerfGpuSumMs+=FPlatformTime::ToMilliseconds(Cycles);++StreamerVisualPerfGpuSamples;}}
 if(Now<StreamerVisualPerfWindowAt||StreamerVisualPerfFrames<1)return;
 const double Span=Now-StreamerVisualPerfWindowStart;StreamerVisualPerfFps=float(StreamerVisualPerfFrames/Span);StreamerVisualPerfFrameMs=float(Span*1000./StreamerVisualPerfFrames);StreamerVisualPerfMaxFrameMs=float(StreamerVisualPerfMaxMs);
 StreamerVisualPerfGpuMs=StreamerVisualPerfGpuSamples?float(StreamerVisualPerfGpuSumMs/StreamerVisualPerfGpuSamples):-1.f;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_PERF fps=%.1f ms=%.2f max_ms=%.1f gpu_ms=%.2f frames=%d window_s=%.0f gpu_samples=%d"),StreamerVisualPerfFps,StreamerVisualPerfFrameMs,StreamerVisualPerfMaxFrameMs,StreamerVisualPerfGpuMs,StreamerVisualPerfFrames,Span,StreamerVisualPerfGpuSamples);
 StreamerVisualPerfWindowStart=Now;StreamerVisualPerfWindowAt=Now+{PERF_LOG_SECONDS:g};StreamerVisualPerfMaxMs=StreamerVisualPerfGpuSumMs=0;StreamerVisualPerfFrames=StreamerVisualPerfGpuSamples=0;
}}
void ASub01HomeCharacter::ScanStreamerVisualMouse(){{
 // The glowing mouse is not a StaticMeshActor: any actor with a primitive in the mouse zone, small and not of the keyboard/desk
 // packs, becomes the mouse prop (it follows the pull-back and is the right hand's target in `mouse`); none = the mouse is merged
 // into another mesh (or elsewhere) and the IK uses the tuning point mouse_x/y/z. Every candidate is logged with its class.
 StreamerVisualMouseActor=nullptr;StreamerVisualMouseExtent=StreamerVisualMouseCentreOffset=FVector::ZeroVector;if(!GetWorld())return;int32 Found=0;
 for(TActorIterator<AActor> It(GetWorld());It;++It){{AActor* A=*It;if(!A||A==this)continue;const FVector L=A->GetActorLocation();
  if(L.X<{MOUSE_ZONE['x'][0]}||L.X>{MOUSE_ZONE['x'][1]}||L.Y<{MOUSE_ZONE['y'][0]}||L.Y>{MOUSE_ZONE['y'][1]}||L.Z<{MOUSE_ZONE['z'][0]}||L.Z>{MOUSE_ZONE['z'][1]})continue;
  if(!A->FindComponentByClass<UPrimitiveComponent>())continue;FVector Origin=FVector::ZeroVector,Extent=FVector::ZeroVector;A->GetActorBounds(false,Origin,Extent);
  const bool Skel=A->FindComponentByClass<USkeletalMeshComponent>()!=nullptr,Inst=A->FindComponentByClass<UInstancedStaticMeshComponent>()!=nullptr;const UStaticMeshComponent* SMC=A->FindComponentByClass<UStaticMeshComponent>();
  const FString Mesh=SMC&&SMC->GetStaticMesh()?SMC->GetStaticMesh()->GetName():FString(TEXT("none")),Name=A->GetName();
  const bool Small=Extent.X<={MOUSE_MAX_EXTENT[0]}&&Extent.Y<={MOUSE_MAX_EXTENT[1]}&&Extent.Z<={MOUSE_MAX_EXTENT[2]},Pack=Mesh.StartsWith(TEXT("{seatfix.DESK_PROP_MESH_PREFIX}"))||Mesh.StartsWith(TEXT("{seatfix.DESK_MESH_PREFIX}"));
  const bool Mouse=Small&&!Pack&&!StreamerVisualMouseActor.IsValid();
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MOUSE_CANDIDATE actor=%s class=%s mesh=%s skeletal=%d instanced=%d location=%s extent=%s mouse=%d"),*Name,*A->GetClass()->GetName(),*Mesh,Skel?1:0,Inst?1:0,*L.ToString(),*Extent.ToString(),Mouse?1:0);
  if(Mouse){{StreamerVisualMouseActor=A;StreamerVisualMouseExtent=Extent;StreamerVisualMouseCentreOffset=Origin-L;StreamerVisualDeskProps.Add(A);StreamerVisualDeskPropOrigins.Add(L);StreamerVisualDeskPropIsChair.Add(false);++Found;}}
 }}
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_MOUSE_PROP found=%d (0 = no small primitive actor in the mouse zone: merged into another mesh or elsewhere; the right hand uses mouse_x/y/z=(%.1f,%.1f,%.1f))"),Found,StreamerVisualMouseX,StreamerVisualMouseY,StreamerVisualMouseZ);
}}
void ASub01HomeCharacter::UpdateStreamerVisualHands(USub01HomeHandsInstance* Anim,float Dt){{
 // World WRIST targets on the keyboard body (the widest follower of the keyboard pack, its bounds centre): hand_span_cm apart,
 // hand_back_cm towards him, hand_height_cm above the desk (its bottom); the right wrist behind the mouse in `mouse`. A goal jump
 // glides in hand_move_s on a hand_arc_cm arc (eased); converted to component space for the proxy, alpha eased over {HAND_BLEND_SECONDS:g} s.
 if(!Anim||!FirstPersonBody)return;if(!StreamerVisualDeskPropsScanned)ScanStreamerVisualDeskProps();
 AActor* KB=StreamerVisualKeyboardActor.Get();const bool Have=StreamerVisualSchemaVersion==2&&StreamerVisualHandsIK>0&&KB!=nullptr;
 // his facing (authored body) and, snapped to the level's axes (the keyboard is axis-aligned), "towards him" and "his right" on the keys
 const FVector Facing=StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(StreamerVisualFacingLocal);
 const FVector Toward=FMath::Abs(Facing.Y)>=FMath::Abs(Facing.X)?FVector(0,Facing.Y>0?-1:1,0):FVector(Facing.X>0?-1:1,0,0),Right=FVector::CrossProduct(FVector::UpVector,-Toward);
 FVector Goal[2]={{FVector::ZeroVector,FVector::ZeroVector}};FString Name[2];
 if(Have){{const FVector K=KB->GetActorLocation()+StreamerVisualKeyboardCentreOffset,E=StreamerVisualKeyboardExtent;
  const FVector Base=K+Toward*double(StreamerVisualHandBackCm)+FVector(0,0,-E.Z+StreamerVisualHandHeightCm),Half=Right*(double(StreamerVisualHandSpanCm)*.5);
  Goal[0]=Base-Half;Name[0]=TEXT("keyboard_left");Goal[1]=Base+Half;Name[1]=TEXT("keyboard_right");
  if(StreamerVisualState==TEXT("mouse")){{AActor* M=StreamerVisualMouseActor.Get(); // the left hand stays planted on the keys
   Goal[1]=M?M->GetActorLocation()+StreamerVisualMouseCentreOffset+Toward*double(StreamerVisualMouseBackCm)+FVector(0,0,-StreamerVisualMouseExtent.Z+StreamerVisualHandHeightCm):FVector(StreamerVisualMouseX,StreamerVisualMouseY,StreamerVisualMouseZ);
   Name[1]=M?TEXT("mouse_prop"):TEXT("mouse_point");}}
 }}
 const double MoveS=FMath::Max(.05,double(StreamerVisualHandMoveS));FVector Sent[2]={{FVector::ZeroVector,FVector::ZeroVector}};
 if(Have){{for(int32 S=0;S<2;++S){{
   if(!StreamerVisualHandWorldValid){{StreamerVisualHandWorld[S]=StreamerVisualHandSent[S]=StreamerVisualHandMoveFrom[S]=StreamerVisualHandMoveTo[S]=Goal[S];StreamerVisualHandMoveP[S]=1;}}
   else{{if(FVector::Dist(Goal[S],StreamerVisualHandMoveTo[S])>{HAND_GLIDE_RESTART_CM:g}){{StreamerVisualHandMoveFrom[S]=StreamerVisualHandSent[S];StreamerVisualHandMoveP[S]=0;}} // a new glide from where the wrist was shown (arc included: no pop)
    StreamerVisualHandMoveTo[S]=Goal[S];StreamerVisualHandMoveP[S]=FMath::Min(1.,StreamerVisualHandMoveP[S]+Dt/MoveS);
    StreamerVisualHandWorld[S]=FMath::Lerp(StreamerVisualHandMoveFrom[S],Goal[S],FMath::SmoothStep(0.,1.,StreamerVisualHandMoveP[S]));}}
   Sent[S]=StreamerVisualHandWorld[S];
   if(StreamerVisualHandMoveP[S]<1)Sent[S].Z+=double(StreamerVisualHandArcCm)*FMath::Sin(PI*FMath::SmoothStep(0.,1.,StreamerVisualHandMoveP[S])); // the glide arcs up, never through the desk
   StreamerVisualHandSent[S]=Sent[S];
  }}StreamerVisualHandWorldValid=true;}}
 StreamerVisualHandAlpha+=FMath::Clamp((Have?1.f:0.f)-StreamerVisualHandAlpha,-Dt/{_f(HAND_BLEND_SECONDS)},Dt/{_f(HAND_BLEND_SECONDS)});
 const FTransform W=FirstPersonBody->GetComponentTransform();const FQuat ToComponent=W.GetRotation().Inverse();
 Anim->StreamerVisualHandIK=StreamerVisualHandAlpha>0&&StreamerVisualHandWorldValid;Anim->StreamerVisualHandAlpha=StreamerVisualHandAlpha;
 Anim->StreamerVisualHandTargetLeft=W.InverseTransformPosition(Have?Sent[0]:StreamerVisualHandSent[0]);Anim->StreamerVisualHandTargetRight=W.InverseTransformPosition(Have?Sent[1]:StreamerVisualHandSent[1]); // fading out: the last shown target
 // elbow poles in component space: down, back (away from the monitor), slightly out (his own facing, not the snapped one)
 const FVector Flat=FVector(Facing.X,Facing.Y,0).GetSafeNormal(),BodyRight=FVector::CrossProduct(FVector::UpVector,Flat);
 Anim->StreamerVisualHandPoleLeft=ToComponent.RotateVector(FVector::UpVector*{ELBOW_POLE_VECTOR[0]:g}-Flat*{ELBOW_POLE_VECTOR[1]:g}-BodyRight*{ELBOW_POLE_VECTOR[2]:g});
 Anim->StreamerVisualHandPoleRight=ToComponent.RotateVector(FVector::UpVector*{ELBOW_POLE_VECTOR[0]:g}-Flat*{ELBOW_POLE_VECTOR[1]:g}+BodyRight*{ELBOW_POLE_VECTOR[2]:g});
 Anim->StreamerVisualElbowPole=StreamerVisualElbowPole;Anim->StreamerVisualFingerCurlDeg=StreamerVisualFingerCurlDeg;Anim->StreamerVisualFingerCurlAxis=int32(StreamerVisualFingerCurlAxis);
 StreamerVisualHandDist[0]=Anim->StreamerVisualHandDistLeft;StreamerVisualHandDist[1]=Anim->StreamerVisualHandDistRight;StreamerVisualElbowDeg[0]=Anim->StreamerVisualElbowDegLeft;StreamerVisualElbowDeg[1]=Anim->StreamerVisualElbowDegRight;
 StreamerVisualFingerCurlMeasured[0]=Anim->StreamerVisualFingerMcpLeft;StreamerVisualFingerCurlMeasured[1]=Anim->StreamerVisualFingerPipLeft;StreamerVisualFingerCurlMeasured[2]=Anim->StreamerVisualFingerMcpRight;StreamerVisualFingerCurlMeasured[3]=Anim->StreamerVisualFingerPipRight;
 const double Now=FPlatformTime::Seconds();
 if(Have&&(Name[0]!=StreamerVisualHandTargetName[0]||Name[1]!=StreamerVisualHandTargetName[1]||Now>=StreamerVisualHandsLogAt)){{StreamerVisualHandTargetName[0]=Name[0];StreamerVisualHandTargetName[1]=Name[1];StreamerVisualHandsLogAt=Now+10;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_HANDS target=left:%s%s right:%s%s reach=L%.1f/R%.1f alpha=%.2f elbow=L%.0f/R%.0f fingers=L%.0f/%.0f R%.0f/%.0f heightCm=%.1f spanCm=%.1f backCm=%.1f pole=%.2f curlDeg=%.1f axis=%d"),*Name[0],*Goal[0].ToString(),*Name[1],*Goal[1].ToString(),StreamerVisualHandDist[0],StreamerVisualHandDist[1],StreamerVisualHandAlpha,
   StreamerVisualElbowDeg[0],StreamerVisualElbowDeg[1],StreamerVisualFingerCurlMeasured[0],StreamerVisualFingerCurlMeasured[1],StreamerVisualFingerCurlMeasured[2],StreamerVisualFingerCurlMeasured[3],StreamerVisualHandHeightCm,StreamerVisualHandSpanCm,StreamerVisualHandBackCm,StreamerVisualElbowPole,StreamerVisualFingerCurlDeg,int32(StreamerVisualFingerCurlAxis));}}
}}
void ASub01HomeCharacter::UpdateStreamerVisualKeyLight(double Now){{
 // Soft key light for the webcam: above the monitor centre, 6 cm towards him, the face camera's side offset to his left, aimed at
 // the face camera's head mean (else the Head bone sampled every 2 s). Candelas scaled by key_light (0 hides it).
 if(!StreamerVisualKeyLight)return;const float Level=StreamerVisualSchemaVersion==2?StreamerVisualKeyLightLevel:0.f;
 if(StreamerVisualFaceAimed)StreamerVisualKeyLightAim=StreamerVisualFaceAim;
 else if(Now>=StreamerVisualKeyLightSampleAt||StreamerVisualKeyLightAim.IsNearlyZero()){{StreamerVisualKeyLightSampleAt=Now+2;const FVector BodyAt=FirstPersonBody?FirstPersonBody->GetComponentLocation():FVector(214,-289,6.19);
  const bool HasHead=FirstPersonBody&&FirstPersonBody->GetBoneIndex(TEXT("Head"))!=INDEX_NONE;FVector Head=HasHead?FirstPersonBody->GetBoneLocation(TEXT("Head")):FVector::ZeroVector;
  StreamerVisualKeyLightAim=HasHead&&!Head.ContainsNaN()&&FVector::Dist(Head,BodyAt)<=250?Head:BodyAt+FVector(0,0,120);}}
 const FVector Monitor({seatfix.MONITOR[0]},{seatfix.MONITOR[1]},{seatfix.MONITOR[2]});FVector Towards(StreamerVisualKeyLightAim.X-Monitor.X,StreamerVisualKeyLightAim.Y-Monitor.Y,0);
 Towards=Towards.Size()>10?Towards.GetSafeNormal():FVector(0,1,0);const FVector Side=FVector::CrossProduct(FVector::UpVector,-Towards);
 const FVector Location=Monitor+Towards*6.+Side*double(StreamerVisualFaceSideCm)+FVector(0,0,StreamerVisualKeyLightUpCm);
 StreamerVisualKeyLight->SetWorldLocationAndRotation(Location,(StreamerVisualKeyLightAim-Location).Rotation());
 const float Key=Level*100.f+StreamerVisualKeyLightTempK*1e-5f+StreamerVisualKeyLightUpCm*1e-3f;
 if(Key!=StreamerVisualKeyLightApplied){{StreamerVisualKeyLightApplied=Key;StreamerVisualKeyLight->SetIntensity(Level*{_f(KEY_LIGHT_MAX_CD)});StreamerVisualKeyLight->SetTemperature(StreamerVisualKeyLightTempK);StreamerVisualKeyLight->SetVisibility(Level>0);
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_KEY_LIGHT level=%.2f cd=%.0f tempK=%.0f upCm=%.1f location=%s aim=%s"),Level,Level*{_f(KEY_LIGHT_MAX_CD)},StreamerVisualKeyLightTempK,StreamerVisualKeyLightUpCm,*Location.ToString(),*StreamerVisualKeyLightAim.ToString());}}
}}
void ASub01HomeCharacter::ApplyStreamerVisualBodyLook(){{
 // forced_lod (1 = LOD0 forced, 0 = automatic) and hide_slot (a material slot hidden at LOD0, -1 = none) on change; the slot
 // names and LOD count logged once so the hoodie collar can be matched to a slot from the log.
 if(!FirstPersonBody)return;
 if(StreamerVisualForcedLodApplied!=StreamerVisualForcedLod){{StreamerVisualForcedLodApplied=StreamerVisualForcedLod;FirstPersonBody->SetForcedLOD(int32(StreamerVisualForcedLod));
  FString Slots;const TArray<FName> Names=FirstPersonBody->GetMaterialSlotNames();for(int32 I=0;I<Names.Num();++I){{if(I)Slots+=TEXT(",");Slots+=FString::FromInt(I)+TEXT(":")+Names[I].ToString();}}
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_BODY_LOOK forcedLod=%d lods=%d materials=%d [%s] hideSlot=%d"),int32(StreamerVisualForcedLod),FirstPersonBody->GetNumLODs(),Names.Num(),*Slots,int32(StreamerVisualHideSlot));}}
 if(StreamerVisualHideSlotApplied!=StreamerVisualHideSlot){{if(StreamerVisualHideSlotApplied>=0)FirstPersonBody->ShowMaterialSection(int32(StreamerVisualHideSlotApplied),INDEX_NONE,true,0);
  StreamerVisualHideSlotApplied=StreamerVisualHideSlot;if(StreamerVisualHideSlot>=0)FirstPersonBody->ShowMaterialSection(int32(StreamerVisualHideSlot),INDEX_NONE,false,0);
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_BODY_LOOK hideSlot=%d (LOD0 sections of that material slot hidden; -1 = all shown)"),int32(StreamerVisualHideSlot));}}
}}
// SUB01_STREAMER_VISUAL_V2_STREAMPASS END
'''

TUNING_POSTURE_LINE = _line(seatfix.CPP_HELPERS, ' Field(TEXT("posture_lean_deg"),')


def _fields(keys) -> str:
    return ''.join(f'Field(TEXT("{k}"),{TUNING_FIELDS[k]},{TUNING_LIMITS[k][0]},{TUNING_LIMITS[k][1]});' for k in keys)


_KEYS = list(TUNING_LIMITS)
TUNING_STREAM = (TUNING_POSTURE_LINE +
                 ' ' + _fields(_KEYS[:13]) + ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'
                 ' ' + _fields(_KEYS[13:18]) + '\n'
                 ' ' + _fields(_KEYS[18:]) + ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n')
SEAT_READY_LOG = _line(seatfix.START_SEAT, ' UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_SEAT_FIX_READY')
KEY_LIGHT_CREATE = (''' if(!StreamerVisualKeyLight){ // SUB01_STREAMER_VISUAL_V2_STREAMPASS: the webcam key light (streamer mode only), placed and scaled every tick
  StreamerVisualKeyLight=NewObject<USpotLightComponent>(this,TEXT("StreamerVisualKeyLight"));StreamerVisualKeyLight->SetMobility(EComponentMobility::Movable);StreamerVisualKeyLight->SetIntensityUnits(ELightUnits::Candelas);
  StreamerVisualKeyLight->SetInnerConeAngle(25.f);StreamerVisualKeyLight->SetOuterConeAngle(45.f);StreamerVisualKeyLight->SetAttenuationRadius(300.f);StreamerVisualKeyLight->SetCastShadows(false);StreamerVisualKeyLight->bUseTemperature=true;
  StreamerVisualKeyLight->SetIntensity(0.f);StreamerVisualKeyLight->SetVisibility(false);StreamerVisualKeyLight->RegisterComponent(); // dark until the first update places and scales itStreamerVisualKeyLight->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);StreamerVisualKeyLightApplied=-1;
 }
''' + SEAT_READY_LOG)
SCAN_RESET = _line(seatfix.CPP_HELPERS, ' StreamerVisualDeskPropsScanned=true;StreamerVisualDeskProps.Reset();')
SCAN_COUNT_LINE = _line(seatfix.CPP_HELPERS, '  if(ChairPart){if(ChairCount<8)')
SCAN_CHAIR_LINE = ' StreamerVisualChairParts=ChairCount;\n'
SCAN_ADD_LINE = _line(seatfix.CPP_HELPERS, '  if(!DeskProp&&!ChairPart)continue;StreamerVisualDeskProps.Add(A);')
SCAN_ADD_STREAM = SCAN_ADD_LINE.rstrip('\n') + 'StreamerVisualDeskPropIsChair.Add(ChairPart); // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'
MOVE_LINE = _line(seatfix.CPP_HELPERS, ' for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){AActor* A=StreamerVisualDeskProps[I].Get();')
MOVE_STREAM = (' for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){AActor* A=StreamerVisualDeskProps[I].Get();if(!A||!StreamerVisualDeskPropOrigins.IsValidIndex(I))continue;'
               'const bool Chair=StreamerVisualDeskPropIsChair.IsValidIndex(I)&&StreamerVisualDeskPropIsChair[I];A->SetActorLocation(StreamerVisualDeskPropOrigins[I]+(Chair?StreamerVisualChairDelta:WorldDelta),false,nullptr,ETeleportType::TeleportPhysics);++Moved;} // SUB01_STREAMER_VISUAL_V2_STREAMPASS: chair parts by the chair delta\n')
GATE_LINE = _line(seatfix.CPP_HELPERS, ' if(WorldDelta.Equals(StreamerVisualDeskPropDelta,.01))return;')
GATE_STREAM = GATE_LINE.replace('if(WorldDelta.Equals(StreamerVisualDeskPropDelta,.01))return;', 'if(WorldDelta.Equals(StreamerVisualDeskPropDelta,.01)&&StreamerVisualChairDelta.Equals(StreamerVisualChairDeltaApplied,.01))return;StreamerVisualChairDeltaApplied=StreamerVisualChairDelta; /* SUB01_STREAMER_VISUAL_V2_STREAMPASS */')
DESK_APPLY_LINE = _line(seatfix.APPLY_SEAT, '  ApplyStreamerVisualDeskProps(')
POSTURE_EASE_LINE = _line(seatfix.SPINE_POSTURE, '  StreamerVisualPostureLeanApplied+=')
POSTURE_EASE_TYPING = POSTURE_EASE_LINE.replace(
    'FMath::Clamp(StreamerVisualPostureLeanDeg-StreamerVisualPostureLeanApplied,',
    'FMath::Clamp((StreamerVisualPostureLeanDeg+(StreamerVisualTypingBase?StreamerVisualTypingLeanDeg:0.f))-StreamerVisualPostureLeanApplied,').replace(
    'FMath::Clamp(StreamerVisualPostureHeadDeg-StreamerVisualPostureHeadApplied,',
    'FMath::Clamp((StreamerVisualPostureHeadDeg+(StreamerVisualTypingBase?StreamerVisualTypingHeadDeg:0.f))-StreamerVisualPostureHeadApplied,').rstrip('\n') + ' // SUB01_STREAMER_VISUAL_V2_STREAMPASS: the typing loop adds its own sit-up\n'
assert POSTURE_EASE_TYPING != POSTURE_EASE_LINE
SLOT_FACE = ('  const int32 Slot=StreamerVisualDeskSlot(Anim,StreamerVisualState==TEXT("typing")?1:StreamerVisualState==TEXT("mouse")?2:0); // SUB01_STREAMER_VISUAL_V2_FACE: off-desk clip -> sitting loop / frozen R9\n')
SLOT_STREAM = ('  // SUB01_STREAMER_VISUAL_V2_STREAMPASS: desk_base 1 = the typing loop is the desk-work base (idle/talking/reacting/mouse), the reading loop only for reading\n'
               '  const int32 Slot=StreamerVisualDeskSlot(Anim,StreamerVisualState==TEXT("typing")||(StreamerVisualDeskBase>0&&StreamerVisualState!=TEXT("reading"))?1:StreamerVisualState==TEXT("mouse")?2:0);StreamerVisualTypingBase=Slot==1;\n')
TICK_STREAM = '  UpdateStreamerVisualHands(Anim,Dt);ApplyStreamerVisualBodyLook();UpdateStreamerVisualKeyLight(Now);UpdateStreamerVisualPerf(Now,Dt); // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'
RECEIPT_SEAT_TAIL = '   Receipt->SetNumberField(TEXT("posture_lean_deg"),StreamerVisualPostureLeanApplied);Receipt->SetNumberField(TEXT("posture_head_deg"),StreamerVisualPostureHeadApplied);} // SUB01_STREAMER_VISUAL_V2_SEATFIX\n'
RECEIPT_STREAM_TAIL = '   Receipt->SetNumberField(TEXT("fps"),StreamerVisualPerfFps);Receipt->SetNumberField(TEXT("frame_ms"),StreamerVisualPerfFrameMs);Receipt->SetNumberField(TEXT("frame_max_ms"),StreamerVisualPerfMaxFrameMs);Receipt->SetNumberField(TEXT("gpu_ms"),StreamerVisualPerfGpuMs);} // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'
RECEIPT_STREAM = ('   Receipt->SetNumberField(TEXT("posture_lean_deg"),StreamerVisualPostureLeanApplied);Receipt->SetNumberField(TEXT("posture_head_deg"),StreamerVisualPostureHeadApplied); // SUB01_STREAMER_VISUAL_V2_SEATFIX\n'
                  '   Receipt->SetStringField(TEXT("hand_left"),StreamerVisualHandTargetName[0]+(StreamerVisualHandDist[0]>=0?FString::Printf(TEXT(" %.1fcm"),StreamerVisualHandDist[0]):FString(TEXT(" -"))));Receipt->SetStringField(TEXT("hand_right"),StreamerVisualHandTargetName[1]+(StreamerVisualHandDist[1]>=0?FString::Printf(TEXT(" %.1fcm"),StreamerVisualHandDist[1]):FString(TEXT(" -"))));\n'
                  '   Receipt->SetNumberField(TEXT("hands_alpha"),StreamerVisualHandAlpha);Receipt->SetNumberField(TEXT("elbow_left_deg"),StreamerVisualElbowDeg[0]);Receipt->SetNumberField(TEXT("elbow_right_deg"),StreamerVisualElbowDeg[1]);'
                  'Receipt->SetStringField(TEXT("finger_curl_deg_measured"),FString::Printf(TEXT("L %.0f/%.0f R %.0f/%.0f"),StreamerVisualFingerCurlMeasured[0],StreamerVisualFingerCurlMeasured[1],StreamerVisualFingerCurlMeasured[2],StreamerVisualFingerCurlMeasured[3]));\n'
                  '   Receipt->SetBoolField(TEXT("mouse_prop"),StreamerVisualMouseActor.IsValid());Receipt->SetNumberField(TEXT("key_light"),StreamerVisualSchemaVersion==2?StreamerVisualKeyLightLevel:0.f);\n'
                  '   Receipt->SetNumberField(TEXT("hide_slot"),StreamerVisualHideSlotApplied);Receipt->SetNumberField(TEXT("forced_lod"),StreamerVisualForcedLodApplied);\n'
                  + RECEIPT_STREAM_TAIL)

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.h
HANDS_SEAT_END = ' // SUB01_STREAMER_VISUAL_V2_SEATFIX END\n'
HANDS_FIELDS = ''' // SUB01_STREAMER_VISUAL_V2_STREAMPASS BEGIN (tools/native_streamer_visual_v2/install_stream_pass.py): hands IK, set by the character every tick.
 UPROPERTY(Transient) bool StreamerVisualHandIK=false;
 UPROPERTY(Transient) float StreamerVisualHandAlpha=0;
 UPROPERTY(Transient) FVector StreamerVisualHandTargetLeft=FVector::ZeroVector; // component space: wrist targets
 UPROPERTY(Transient) FVector StreamerVisualHandTargetRight=FVector::ZeroVector;
 UPROPERTY(Transient) FVector StreamerVisualHandPoleLeft=FVector::ZeroVector; // component space: elbow pole directions
 UPROPERTY(Transient) FVector StreamerVisualHandPoleRight=FVector::ZeroVector;
 UPROPERTY(Transient) float StreamerVisualElbowPole=0; // 0 = the clip's bend plane, 1 = the pole
 UPROPERTY(Transient) float StreamerVisualFingerCurlDeg=0; // added to the proximal (x1) and middle (x1.2) phalanges, scaled by the alpha
 UPROPERTY(Transient) int32 StreamerVisualFingerCurlAxis=2; // local axis 0/1/2 = X/Y/Z
 UPROPERTY(Transient) float StreamerVisualHandDistLeft=-1; // published after evaluation: wrist to target, cm (-1 = no solve)
 UPROPERTY(Transient) float StreamerVisualHandDistRight=-1;
 UPROPERTY(Transient) float StreamerVisualElbowDegLeft=-1; // published: interior elbow angle (180 = straight)
 UPROPERTY(Transient) float StreamerVisualElbowDegRight=-1;
 UPROPERTY(Transient) float StreamerVisualFingerMcpLeft=-1; // published: mean index..pinky flexion at the knuckle / the middle joint, deg
 UPROPERTY(Transient) float StreamerVisualFingerPipLeft=-1;
 UPROPERTY(Transient) float StreamerVisualFingerMcpRight=-1;
 UPROPERTY(Transient) float StreamerVisualFingerPipRight=-1;
 // SUB01_STREAMER_VISUAL_V2_STREAMPASS END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.cpp
_FINGER_NAMES = ','.join('{' + ','.join('{' + ','.join(f'TEXT("{side}Hand{finger}{k}")' for k in (1, 2, 3)) + '}' for finger in FINGERS) + '}'
                         for side in ('Left', 'Right'))
PROXY_SEAT_BEGIN = _line(seatfix.PROXY_MEMBERS, ' // SUB01_STREAMER_VISUAL_V2_SEATFIX BEGIN')
PROXY_MEMBERS = f''' // SUB01_STREAMER_VISUAL_V2_STREAMPASS BEGIN (tools/native_streamer_visual_v2/install_stream_pass.py): two-bone IK on both arms.
 // Own solve in component space (no AnimationCore node): the upper arm turns by the minimal rotation onto the new elbow, the forearm is
 // carried with it and bent at the elbow (no forearm roll), bone lengths are kept, only those two local rotations change (slerp by
 // alpha); the hand's local rotation stays. Optional finger curl on the proximal/middle phalanges; elbow and finger angles measured.
 bool StreamerV2HandIK=false;float StreamerV2HandAlpha=0,StreamerV2ElbowPole=0,StreamerV2FingerCurlDeg=0;int32 StreamerV2FingerCurlAxis=2;
 FVector StreamerV2HandTarget[2]={{FVector::ZeroVector,FVector::ZeroVector}},StreamerV2HandPole[2]={{FVector::ZeroVector,FVector::ZeroVector}};
 int32 StreamerV2ArmBones[2][3]={{{{INDEX_NONE,INDEX_NONE,INDEX_NONE}},{{INDEX_NONE,INDEX_NONE,INDEX_NONE}}}},StreamerV2FingerBones[2][4][3]={{}},StreamerV2ArmCount=-1;const FReferenceSkeleton* StreamerV2ArmRef=nullptr;
 FVector StreamerV2LastBend[2]={{FVector::ZeroVector,FVector::ZeroVector}}; // the previous frame's bend direction per arm (component space): used when the clip's plane degenerates
 float StreamerV2HandDist[2]={{-1,-1}},StreamerV2ElbowDeg[2]={{-1,-1}},StreamerV2FingerFlex[2][2]={{{{-1,-1}},{{-1,-1}}}};
 void ResolveStreamerV2Arms(const FReferenceSkeleton& Ref){{
  if(StreamerV2ArmRef==&Ref&&StreamerV2ArmCount==Ref.GetNum())return;StreamerV2ArmRef=&Ref;StreamerV2ArmCount=Ref.GetNum();StreamerV2LastBend[0]=StreamerV2LastBend[1]=FVector::ZeroVector; // a new skeleton: resolve again
  auto Find=[&Ref](const TCHAR* Name){{int32 Index=Ref.FindBoneIndex(FName(Name));for(int32 B=0;Index==INDEX_NONE&&B<Ref.GetNum();++B)if(Ref.GetBoneName(B).ToString().EndsWith(Name))Index=B;return Index;}};
  static const TCHAR* const Names[2][3]={{{{TEXT("LeftArm"),TEXT("LeftForeArm"),TEXT("LeftHand")}},{{TEXT("RightArm"),TEXT("RightForeArm"),TEXT("RightHand")}}}};
  static const TCHAR* const Fingers[2][4][3]={{{_FINGER_NAMES}}};
  for(int32 S=0;S<2;++S){{for(int32 K=0;K<3;++K)StreamerV2ArmBones[S][K]=Find(Names[S][K]);for(int32 G=0;G<4;++G)for(int32 K=0;K<3;++K)StreamerV2FingerBones[S][G][K]=Find(Fingers[S][G][K]);}}
 }}
 static bool StreamerV2ComponentTransform(const FCompactPose& Source,int32 MeshBone,FTransform& Out){{ // bone local * parents up to the root
  if(MeshBone==INDEX_NONE)return false;const auto& Bones=Source.GetBoneContainer();const auto& Ref=Bones.GetReferenceSkeleton();Out=FTransform::Identity;int32 Guard=0;
  for(int32 B=MeshBone;B!=INDEX_NONE;B=Ref.GetParentIndex(B)){{if(++Guard>512)return false;const auto Compact=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(B));if(Compact.GetInt()<0)return false;Out=Out*Source[Compact];}}
  return !Out.ContainsNaN();
 }}
 static bool StreamerV2SolveTwoBone(const FVector& A,const FVector& B,const FVector& C,const FVector& T,FVector& OutB,FVector& OutC,const FVector& Pole=FVector::ZeroVector,double PoleWeight=0,FVector* LastBend=nullptr){{
  // A upper arm, B elbow, C wrist, T target: new elbow/wrist positions with the bone lengths kept; the bend in the clip's plane
  // (degenerate: the previous frame's bend, reprojected), pulled towards the pole (projected off the shoulder-target axis) by
  // PoleWeight; a mix of nearly opposite directions takes the pole alone instead of flipping through zero.
  const double L1=(B-A).Size(),L2=(C-B).Size();if(L1<1e-3||L2<1e-3)return false;
  FVector Axis=T-A;double D=Axis.Size();if(D<1e-3)return false;Axis=Axis*(1./D);D=FMath::Clamp(D,FMath::Abs(L1-L2)+.1,(L1+L2)*.999);
  FVector Bend=(B-A)-Axis*FVector::DotProduct(B-A,Axis);if(Bend.Size()<1e-3&&LastBend&&!LastBend->IsNearlyZero())Bend=*LastBend-Axis*FVector::DotProduct(*LastBend,Axis);
  if(Bend.Size()<1e-3){{Bend=FVector::CrossProduct(Axis,FVector::UpVector);if(Bend.Size()<1e-3)Bend=FVector::CrossProduct(Axis,FVector::ForwardVector);}}Bend=Bend.GetSafeNormal();
  if(PoleWeight>0){{const FVector P=Pole-Axis*FVector::DotProduct(Pole,Axis);if(P.Size()>1e-3){{const FVector PN=P.GetSafeNormal(),Mixed=Bend*(1-PoleWeight)+PN*PoleWeight;Bend=Mixed.Size()>.3?Mixed.GetSafeNormal():PN;}}}}
  if(LastBend)*LastBend=Bend;
  const double CosA=FMath::Clamp((L1*L1+D*D-L2*L2)/(2*L1*D),-1.,1.),SinA=FMath::Sqrt(FMath::Max(0.,1-CosA*CosA));
  OutB=A+Axis*(L1*CosA)+Bend*(L1*SinA);OutC=A+Axis*D;return true;
 }}
 static double StreamerV2AngleDeg(const FVector& U,const FVector& V){{ // angle between two directions, degrees (-1 if degenerate)
  const FVector A=U.GetSafeNormal(),B=V.GetSafeNormal();if(A.IsNearlyZero()||B.IsNearlyZero())return -1;
  return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(A,B),-1.,1.)));
 }}
 void EvaluateStreamerV2Hands(FPoseContext& Output){{ // after breathing/posture, before the head: both arms towards their targets
  StreamerV2HandDist[0]=StreamerV2HandDist[1]=StreamerV2ElbowDeg[0]=StreamerV2ElbowDeg[1]=-1;for(int32 S=0;S<2;++S)StreamerV2FingerFlex[S][0]=StreamerV2FingerFlex[S][1]=-1;
  if(!StreamerV2HandIK||StreamerV2HandAlpha<=0)return;
  const auto& Bones=Output.Pose.GetBoneContainer();const auto& Ref=Bones.GetReferenceSkeleton();ResolveStreamerV2Arms(Ref);
  for(int32 S=0;S<2;++S){{
   const int32 U=StreamerV2ArmBones[S][0],F=StreamerV2ArmBones[S][1],H=StreamerV2ArmBones[S][2];if(U==INDEX_NONE||F==INDEX_NONE||H==INDEX_NONE)continue;
   if(Ref.GetParentIndex(F)!=U||Ref.GetParentIndex(H)!=F)continue;const int32 P=Ref.GetParentIndex(U);if(P==INDEX_NONE)continue;
   FTransform CsU,CsF,CsH,CsP;if(!StreamerV2ComponentTransform(Output.Pose,U,CsU)||!StreamerV2ComponentTransform(Output.Pose,F,CsF)||!StreamerV2ComponentTransform(Output.Pose,H,CsH)||!StreamerV2ComponentTransform(Output.Pose,P,CsP))continue;
   const FVector A=CsU.GetTranslation(),B=CsF.GetTranslation(),C=CsH.GetTranslation();FVector NB=B,NC=C;
   if(!StreamerV2SolveTwoBone(A,B,C,StreamerV2HandTarget[S],NB,NC,StreamerV2HandPole[S],FMath::Clamp(double(StreamerV2ElbowPole),0.,1.),&StreamerV2LastBend[S]))continue;
   const FQuat D1=FQuat::FindBetweenNormals((B-A).GetSafeNormal(),(NB-A).GetSafeNormal());
   const FQuat D2=FQuat::FindBetweenNormals(D1.RotateVector((C-B).GetSafeNormal()),(NC-NB).GetSafeNormal()); // the forearm carried by the upper arm, then bent at the elbow
   const FQuat NewU=D1*CsU.GetRotation(),NewF=D2*D1*CsF.GetRotation();const FQuat LocalU=CsP.GetRotation().Inverse()*NewU,LocalF=NewU.Inverse()*NewF;
   const auto CU=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(U)),CF=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(F));if(CU.GetInt()<0||CF.GetInt()<0)continue;
   Output.Pose[CU].SetRotation(FQuat::Slerp(Output.Pose[CU].GetRotation(),LocalU,StreamerV2HandAlpha).GetNormalized());
   Output.Pose[CF].SetRotation(FQuat::Slerp(Output.Pose[CF].GetRotation(),LocalF,StreamerV2HandAlpha).GetNormalized());
   FTransform DoneU,DoneF,Done;if(!StreamerV2ComponentTransform(Output.Pose,H,Done))continue; // the measurements need the solved hand
   StreamerV2HandDist[S]=float(FVector::Dist(Done.GetTranslation(),StreamerV2HandTarget[S]));
   if(StreamerV2ComponentTransform(Output.Pose,U,DoneU)&&StreamerV2ComponentTransform(Output.Pose,F,DoneF))StreamerV2ElbowDeg[S]=float(StreamerV2AngleDeg(DoneU.GetTranslation()-DoneF.GetTranslation(),Done.GetTranslation()-DoneF.GetTranslation()));
   // finger curl (optional, additive on the clip) about the local axis, then the measured flexion (mean of the fingers found)
   const double Curl=double(StreamerV2FingerCurlDeg)*StreamerV2HandAlpha;const FVector CurlAxis(StreamerV2FingerCurlAxis==0?1:0,StreamerV2FingerCurlAxis==1?1:0,StreamerV2FingerCurlAxis==2?1:0);
   double Mcp=0,Pip=0;int32 Count=0;
   for(int32 G=0;G<4;++G){{const int32 K1=StreamerV2FingerBones[S][G][0],K2=StreamerV2FingerBones[S][G][1],K3=StreamerV2FingerBones[S][G][2];if(K1==INDEX_NONE||K2==INDEX_NONE||K3==INDEX_NONE)continue;
    if(FMath::Abs(Curl)>1e-3)for(int32 J=0;J<2;++J){{const auto CJ=Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(J?K2:K1));if(CJ.GetInt()<0)continue;
     Output.Pose[CJ].SetRotation((Output.Pose[CJ].GetRotation()*FQuat(CurlAxis,FMath::DegreesToRadians(Curl*(J?{FINGER_MIDDLE_FACTOR:g}:1.)))).GetNormalized());}}
    FTransform T1,T2,T3;if(!StreamerV2ComponentTransform(Output.Pose,K1,T1)||!StreamerV2ComponentTransform(Output.Pose,K2,T2)||!StreamerV2ComponentTransform(Output.Pose,K3,T3))continue;
    const double M=StreamerV2AngleDeg(T1.GetTranslation()-Done.GetTranslation(),T2.GetTranslation()-T1.GetTranslation()),Q=StreamerV2AngleDeg(T2.GetTranslation()-T1.GetTranslation(),T3.GetTranslation()-T2.GetTranslation());
    if(M>=0&&Q>=0){{Mcp+=M;Pip+=Q;++Count;}}
   }}
   StreamerV2FingerFlex[S][0]=Count?float(Mcp/Count):-1.f;StreamerV2FingerFlex[S][1]=Count?float(Pip/Count):-1.f;
  }}
 }}
 // SUB01_STREAMER_VISUAL_V2_STREAMPASS END
'''
FACE_COPY_LINE = ('  StreamerV2Reference=Hands->StreamerVisualFreezeSequence.Get();StreamerV2ReferenceSeconds=Hands->StreamerVisualFreezeSeconds;'
                  'if(!StreamerV2Audited){StreamerV2AuditClips.Reset();for(const auto& Clip:Hands->StreamerVisualAuditClips)StreamerV2AuditClips.Add(Clip.Get());} // SUB01_STREAMER_VISUAL_V2_FACE\n')
FACE_COPY_STREAM = (FACE_COPY_LINE +
                    '  StreamerV2HandIK=Hands->StreamerVisualHandIK;StreamerV2HandAlpha=Hands->StreamerVisualHandAlpha;StreamerV2HandTarget[0]=Hands->StreamerVisualHandTargetLeft;StreamerV2HandTarget[1]=Hands->StreamerVisualHandTargetRight; // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'
                    '  StreamerV2HandPole[0]=Hands->StreamerVisualHandPoleLeft;StreamerV2HandPole[1]=Hands->StreamerVisualHandPoleRight;StreamerV2ElbowPole=Hands->StreamerVisualElbowPole;StreamerV2FingerCurlDeg=Hands->StreamerVisualFingerCurlDeg;StreamerV2FingerCurlAxis=Hands->StreamerVisualFingerCurlAxis;\n')
PROXY_EVAL = '   if(StreamerV2)EvaluateStreamerV2(Output); // SUB01_STREAMER_VISUAL_V2: reference hands (pre-additive), then breathing; head below\n'
SEAT_PUBLISH = (' StreamerVisualSeatOffset=Proxy.StreamerV2Seat;StreamerVisualSeatOffsetValid=Proxy.StreamerV2SeatValid;StreamerVisualSeatSettled=Proxy.StreamerV2SeatSettled;'
                'StreamerVisualPelvisBone=Proxy.StreamerV2PinChain.Num()?Proxy.StreamerV2PinChain[0]:-1; // SUB01_STREAMER_VISUAL_V2_SEATFIX\n')
SEAT_PUBLISH_STREAM = (SEAT_PUBLISH +
                       ' StreamerVisualHandDistLeft=Proxy.StreamerV2HandDist[0];StreamerVisualHandDistRight=Proxy.StreamerV2HandDist[1];StreamerVisualElbowDegLeft=Proxy.StreamerV2ElbowDeg[0];StreamerVisualElbowDegRight=Proxy.StreamerV2ElbowDeg[1]; // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'
                       ' StreamerVisualFingerMcpLeft=Proxy.StreamerV2FingerFlex[0][0];StreamerVisualFingerPipLeft=Proxy.StreamerV2FingerFlex[0][1];StreamerVisualFingerMcpRight=Proxy.StreamerV2FingerFlex[1][0];StreamerVisualFingerPipRight=Proxy.StreamerV2FingerFlex[1][1];\n')

EDITS = [
    ('header', HEADER_SEAT_END, HEADER_SEAT_END + HEADER_FIELDS),
    ('cpp', CPP_TOP, CPP_TOP_INCLUDES),
    ('cpp', CPP_SEAT_BEGIN, CPP_METHODS + CPP_SEAT_BEGIN),
    ('cpp', TUNING_POSTURE_LINE, TUNING_STREAM),
    ('cpp', SEAT_READY_LOG, KEY_LIGHT_CREATE),
    ('cpp', SCAN_RESET, SCAN_RESET + ' StreamerVisualKeyboardActor=nullptr;StreamerVisualKeyboardExtent=StreamerVisualKeyboardCentreOffset=FVector::ZeroVector;StreamerVisualDeskPropIsChair.Reset(); // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'),
    ('cpp', SCAN_COUNT_LINE, '  if(DeskProp&&Extent.X>StreamerVisualKeyboardExtent.X){StreamerVisualKeyboardActor=A;StreamerVisualKeyboardExtent=Extent;StreamerVisualKeyboardCentreOffset=Origin-L;} // SUB01_STREAMER_VISUAL_V2_STREAMPASS: the keyboard body = the widest follower (bounds centre)\n' + SCAN_COUNT_LINE),
    ('cpp', SCAN_CHAIR_LINE, ' StreamerVisualChairParts=ChairCount;ScanStreamerVisualMouse(); // SUB01_STREAMER_VISUAL_V2_STREAMPASS\n'),
    ('cpp', SCAN_ADD_LINE, SCAN_ADD_STREAM),
    ('cpp', MOVE_LINE, MOVE_STREAM),
    ('cpp', GATE_LINE, GATE_STREAM),
    ('cpp', SLOT_FACE, SLOT_STREAM),
    ('cpp', DESK_APPLY_LINE,
     '  {const float ChairBack=StreamerVisualChairBackCm<0?StreamerVisualSeatBackCm:StreamerVisualChairBackCm;const FVector ChairLocal=StreamerVisualFacingLocal*double(-ChairBack)+StreamerVisualRightLocal*double(StreamerVisualSeatSideCm); // SUB01_STREAMER_VISUAL_V2_STREAMPASS: the chair by chair_back_cm (-1 = with the seat)\n'
     '   StreamerVisualChairDelta=SeatValid&&StreamerVisualDeskPropsEnabled>0?StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(ChairLocal):FVector::ZeroVector;}\n'
     + DESK_APPLY_LINE + TICK_STREAM),
    ('cpp', POSTURE_EASE_LINE, POSTURE_EASE_TYPING),
    ('cpp', RECEIPT_SEAT_TAIL, RECEIPT_STREAM),
    ('hands_header', HANDS_SEAT_END, HANDS_SEAT_END + HANDS_FIELDS),
    ('hands_cpp', PROXY_SEAT_BEGIN, PROXY_MEMBERS + PROXY_SEAT_BEGIN),
    ('hands_cpp', FACE_COPY_LINE, FACE_COPY_STREAM),
    ('hands_cpp', PROXY_EVAL, PROXY_EVAL + '   if(StreamerV2)EvaluateStreamerV2Hands(Output); // SUB01_STREAMER_VISUAL_V2_STREAMPASS: two-bone IK after breathing/posture, before the head\n'),
    ('hands_cpp', SEAT_PUBLISH, SEAT_PUBLISH_STREAM),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (stream pass already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the seat fix ({seatfix.MARKER}); run the stack up to install_seat_fix.py first'
                for key in FILES if seatfix.MARKER + ' BEGIN' not in sources[key]]
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
    report = {'schema': 'sub01.native-streamer-visual-v2-streampass-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': [seatfix.MARKER, nopin.MARKER, pinfix.MARKER, face.MARKER, v2.MARKER],
              'hands': {'solve': 'own two-bone, component space, minimal upper-arm turn + forearm carried then bent at the elbow, lengths kept',
                        'bones': ['LeftArm/LeftForeArm/LeftHand', 'RightArm/RightForeArm/RightHand'],
                        'blend_seconds': HAND_BLEND_SECONDS, 'height_above_desk_cm': HAND_HEIGHT_CM, 'span_cm': HAND_SPAN_CM, 'back_cm': HAND_BACK_CM,
                        'move_seconds': HAND_MOVE_SECONDS, 'arc_cm': HAND_ARC_CM, 'glide_restart_cm': HAND_GLIDE_RESTART_CM,
                        'elbow_pole': ELBOW_POLE, 'elbow_pole_up_back_out': list(ELBOW_POLE_VECTOR),
                        'finger_curl_deg': FINGER_CURL_DEG, 'finger_curl_axis': FINGER_CURL_AXIS, 'finger_middle_factor': FINGER_MIDDLE_FACTOR,
                        'mouse_back_cm': MOUSE_BACK_CM, 'mouse_point': list(MOUSE_POINT), 'mouse_zone': MOUSE_ZONE, 'mouse_max_half_extent': list(MOUSE_MAX_EXTENT),
                        'recipe': 'docs/streamer/kimi/posture.md section 3'},
              'typing_posture': {'lean_deg': TYPING_LEAN_DEG, 'head_deg': TYPING_HEAD_DEG, 'applies': 'whenever the typing loop plays (desk_base 1: idle/talking/reacting/mouse too)'},
              'desk_base': DESK_BASE, 'chair_back_cm': CHAIR_BACK_CM,
              'body_look': {'forced_lod': FORCED_LOD, 'hide_slot': HIDE_SLOT},
              'key_light': {'level': KEY_LIGHT_LEVEL, 'max_cd': KEY_LIGHT_MAX_CD, 'temp_k': KEY_LIGHT_TEMP_K, 'up_cm': KEY_LIGHT_UP_CM, 'cones_deg': [25, 45], 'radius_cm': 300},
              'perf': {'log_seconds': PERF_LOG_SECONDS, 'receipt': ['fps', 'frame_ms', 'frame_max_ms', 'gpu_ms']},
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
    parser.add_argument('--source', type=Path, required=True, help='directory with the seat-fixed pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-streampass-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
