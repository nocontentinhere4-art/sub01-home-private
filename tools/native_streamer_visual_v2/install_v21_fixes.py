"""v21 fixes ON TOP of the full v20 stack (stream pass, cam2, mouth, pose fix): 60 fps instrumentation and the visual fixes.

    python tools/native_streamer_visual_v2/install_v21_fixes.py --source <dir> [--dry-run]

Requires the stream pass, cam2 and the pose fix in Sub01HomeLab.h/.cpp (the only two files this layer edits); refused when
`// SUB01_STREAMER_VISUAL_V2_V21` is already present or any anchor is not found exactly once. Same atomic writes, line
endings and JSON report as the other layers. Decided with Kimi (docs/streamer/kimi/native-v21-perf.md).

Why: on the pod the container's cgroup allows 10.2 CPUs while 48 are visible; game l (v20) ran at 15 fps (frame 50-65 ms)
with the GPU at 11 ms because the whole container was throttled in every 100 ms period. A CPU partition (launcher, not
this file) takes it to ~40 fps with cam2 on; what is left is measured and tuned with the tools below.

1. PERF thread times: `SUB01_STREAMER_VISUAL_PERF` adds game_ms, render_ms, rhi_ms, swap_ms (GSwapBufferTime: present),
   render_wait_ms, game_wait_ms (the engine's own latest per-frame cycle counters, sampled once per tick: estimates, not a
   frame-time breakdown to be summed; swap = the time around the present call, not present latency); the window is
   `perf_window_s` (default PERF_WINDOW_S, 5..60) so an A/B needs seconds, not half a minute. Receipt `perf_game_ms`,
   `perf_render_ms`, `perf_rhi_ms`, `perf_swap_ms`, `perf_render_wait_ms`, `perf_game_wait_ms`, `perf_window_s`.
2. Live console channel: CONSOLE_PATH (same rules as the tuning file: regular, the game's uid, mode 0600, <= 2048 bytes)
   `{"schema":"sub01.private-streamer-visual-console.v1","sequence":N,"commands":["r.Foo 1"]}` runs ONCE when `sequence`
   grows, polled every 0.5 s while streamer mode runs. Grammar (Kimi's review: no strings, chaining or paths): a query
   `<cvar>` or a numeric set `<cvar> <number>` of a cvar under CONSOLE_PREFIXES or the exact name t.MaxFPS, or exactly
   `csvprofile start|stop|frames=<n>`; at most CONSOLE_MAX_COMMANDS commands of CONSOLE_MAX_CHARS characters; each accepted
   command goes through GEngine->Exec on the game thread and is logged with the cvar's value after it
   (`SUB01_STREAMER_VISUAL_CONSOLE`); refusals and unhandled commands are logged and counted. Receipt `console_applied`,
   `console_refused`, `console_last`.
3. cam2 renders only for a reader: while nobody holds the FIFO the capture, readback and JPEG encode are skipped (v20
   captured and encoded every frame and dropped them at the writer: ~50 ms of CPU per frame for nothing). Every
   PROBE_SECONDS the game thread tries a non-blocking open (ENXIO = still nobody) and hands the descriptor to the writer,
   which owns it from then on. The probe is the ONLY opener (the writer's own open path is gone, Kimi's review): the writer
   stores Reader before it clears the hand-off slot, so the probe never opens a second fd; frames in flight when a reader
   leaves are dropped, never carried to the next reader; the v20 SIGPIPE block around every write stays (a reader that
   leaves gives EPIPE, the writer closes, the probing resumes). A pause for
   lack of a reader is a pause like `cam2` 0 (stale copies are never shown after it). cam2.json `idle_no_reader`.
   `cam2_lite` 1 (default CAM2_LITE): the capture skips ambient occlusion, screen-space reflections, contact shadows,
   volumetric fog, lens flares and particles, culls beyond `cam2_view_cm` (default CAM2_VIEW_CM) and uses
   LODDistanceFactor CAM2_LOD_FACTOR (cheaper far LODs); 0 = the v20 capture. Applied on change, logged `..._CAM2_LITE`.
4. cam2 shows him: a scene capture has no view owner (USceneCaptureComponent::GetViewOwner() is null), so the
   first-person body and its followers, all bOnlyOwnerSee, were culled from it (desk and chair EMPTY in the v20 cam2).
   Streamer mode films him from outside only: at cam2 start every primitive of his with bOnlyOwnerSee becomes visible to
   every view (`SUB01_STREAMER_VISUAL_BODY_SEEN onlyOwnerSeeCleared=N`).
5. Key light, soft and low: the house is exposed for very dim interior light (measured on game l: the old 2500 cd x 0.0005
   = 1.25 cd already clipped his face; 0.125-0.25 cd lift it without clipping). New keys (the v20 `key_light` level is
   ignored by v21, so a v20 game and a v21 game can share the tuning file): `key_cd` candelas (default KEY_CD, 0..5; 0 =
   off), `key_soft_cm` (source width, default KEY_SOFT_CM), `key_radius_cm` (attenuation, default KEY_RADIUS_CM: him, not
   the hall), cones KEY_CONES deg, and `key_body_only` 1 (default): the light is on lighting channel 1 only and his
   primitives get channels 0+1, so its DIRECT light lifts him and not the chair, desk or walls (the v20 chair glow in cam2;
   Lumen's indirect bounce is not channel-masked). The light keeps the v20 candela units (SetIntensityUnits(Candelas)).
   Log `SUB01_STREAMER_VISUAL_KEY_LIGHT cd=...`; receipt `key_light_cd`, `key_body_only`.
6. Chair fit finds the backrest by geometry: v20 logged "no backrest among the chair parts". Each chair part is logged once
   in his frame (`SUB01_STREAMER_VISUAL_CHAIR_PART name behindCm sideCm topAbovePelvisCm halfDepth/Width/Height prim=`).
   Game m (v21 first launch) showed why v20 found nothing: every chair part lies IN FRONT of his pelvis (the backrest
   node_249, 45 x 10 x 45 cm, sits 7 cm in front of it: the chair cuts ~29 cm into him, QA bug 4). The backrest is now the
   part that is tall (top >= BACKREST_MIN_TOP_CM above the pelvis, half height >= BACKREST_MIN_HALF_HEIGHT_CM), central
   (|side| <= BACKREST_MAX_SIDE_CM), near (|along his facing| <= BACKREST_MAX_ALONG_CM, in front OR behind) and THIN along
   his facing (half depth <= max(BACKREST_THIN_CM, BACKREST_THIN_RATIO x half width)); its surface is then traced at sacrum
   height (hits kept within TRACE_BEHIND_CM behind / TRACE_FRONT_CM in front of the pelvis), else its bounds' front face;
   the fit clamp grows from 25 to CHAIR_FIT_MAX_CM cm.
   Also the pose fix's per-part rotation record had landed inside a comment in the desk-prop scan (so the chair never
   turned with `seat_yaw_deg`): it is a statement again.
7. The props really follow him: the keyboard pack and chair parts are Static-mobility StaticMeshActors, so every
   SetActorLocation of the pull-back failed ("Mobility ... has to be 'Movable' if you'd like to move", 605 warnings on game
   m2): since the seat fix's pull-back (seat_back_cm 36) he moved back alone, leaving the chair 22-29 cm into his back (QA bug
   4) and the keyboard 36 cm ahead of him (the hands IK stretched his arms to reach it). Each accepted prop's root is made
   Movable once at the scan (receipt `desk_props_made_movable`).
Typing head pitch: checked on game l frames (face camera, typing): `typing_head_deg` 15 with `posture_head_deg` 0 puts his
eyes on the screen (POSE headPitch 11-15); 0 and below hide the face. The compiled default stays 15.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


posefix = _load('sub01_streamer_visual_v2_posefix', 'install_pose_fix.py')
cam2 = _load('sub01_streamer_visual_v2_cam2', 'install_cam2.py')
streampass, mouth = posefix.streampass, posefix.mouth
seatfix, v2, Refused = streampass.seatfix, streampass.v2, streampass.Refused
_f, _d = streampass._f, posefix._d

MARKER = '// SUB01_STREAMER_VISUAL_V2_V21'
FILES = {key: v2.FILES[key] for key in ('header', 'cpp')}
PERF_WINDOW_S = 10.0
CONSOLE_PATH = '/home/unreal/.sub01-private/streamer-visual-console.json'
CONSOLE_SCHEMA = 'sub01.private-streamer-visual-console.v1'
CONSOLE_PREFIXES = ('r.', 'sg.', 'fx.', 'a.', 'foliage.', 'grass.')   # + the exact name t.MaxFPS and exactly `csvprofile start|stop|frames=<n>`
CONSOLE_MAX_COMMANDS, CONSOLE_MAX_CHARS = 8, 96
PROBE_SECONDS = 1.0
CAM2_LITE, CAM2_VIEW_CM, CAM2_LOD_FACTOR = 0, 2500.0, 2.0
KEY_CD, KEY_SOFT_CM, KEY_RADIUS_CM, KEY_BODY_ONLY = 0.15, 20.0, 160.0, 1
KEY_CONES = (30.0, 55.0)
BACKREST_MIN_TOP_CM, BACKREST_MIN_HALF_HEIGHT_CM, BACKREST_MAX_SIDE_CM = 10.0, 8.0, 25.0
BACKREST_THIN_CM, BACKREST_THIN_RATIO, BACKREST_MAX_ALONG_CM = 6.0, 0.6, 40.0
TRACE_BEHIND_CM, TRACE_FRONT_CM, CHAIR_FIT_MAX_CM = 40.0, 30.0, 40.0   # trace hits kept within [-40, +30] cm of the pelvis along his facing; fit clamp
TUNING_LIMITS = {'perf_window_s': (5, 60), 'cam2_lite': (0, 1), 'cam2_view_cm': (300, 100000), 'key_cd': (0, 5), 'key_soft_cm': (0, 60),
                 'key_radius_cm': (50, 400), 'key_body_only': (0, 1)}
TUNING_FIELDS = {'perf_window_s': 'StreamerVisualPerfWindowSeconds', 'cam2_lite': 'StreamerVisualCam2Lite', 'cam2_view_cm': 'StreamerVisualCam2ViewCm',
                 'key_cd': 'StreamerVisualKeyLightCd', 'key_soft_cm': 'StreamerVisualKeyLightSoftCm', 'key_radius_cm': 'StreamerVisualKeyLightRadiusCm',
                 'key_body_only': 'StreamerVisualKeyLightBodyOnly'}
assert set(TUNING_FIELDS) == set(TUNING_LIMITS)
PERF_THREADS = ('game_ms', 'render_ms', 'rhi_ms', 'swap_ms', 'render_wait_ms', 'game_wait_ms')
PERF_GLOBALS = ('GGameThreadTime', 'GRenderThreadTime', 'GRHIThreadTime', 'GSwapBufferTime', 'GRenderThreadWaitTime', 'GGameThreadWaitTime')

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_CAM2_END = ' // SUB01_STREAMER_VISUAL_V2_CAM2 END\n'
HEADER_FIELDS = f''' // SUB01_STREAMER_VISUAL_V2_V21 BEGIN (tools/native_streamer_visual_v2/install_v21_fixes.py): perf thread times, live console, cam2 reader gate,
 // lite capture and his visibility in it, the soft key light on his lighting channel, the backrest found by geometry.
 void ReadStreamerVisualConsole();void MakeStreamerVisualBodySeenByCaptures();bool ProbeStreamerVisualCam2Reader(double Now);void ApplyStreamerVisualCam2Lite();
 void LogStreamerVisualChairParts(const FVector& Pelvis,const FVector& Facing,const FVector& Side);static bool StreamerVisualConsoleAllowed(const FString& Command);
 double StreamerVisualConsoleAt=0,StreamerVisualConsoleSequence=0,StreamerVisualCam2ProbeAt=0;int32 StreamerVisualConsoleApplied=0,StreamerVisualConsoleRefused=0;FString StreamerVisualConsoleLast;
 double StreamerVisualPerfThreadSum[6]={{0,0,0,0,0,0}};float StreamerVisualPerfThreadMs[6]={{-1,-1,-1,-1,-1,-1}};int32 StreamerVisualPerfThreadSamples=0;float StreamerVisualPerfWindowSeconds={_f(PERF_WINDOW_S)};
 float StreamerVisualCam2Lite={_f(CAM2_LITE)},StreamerVisualCam2ViewCm={_f(CAM2_VIEW_CM)},StreamerVisualCam2LiteApplied=-1,StreamerVisualCam2ViewApplied=-1;int64 StreamerVisualCam2Idle=0;int32 StreamerVisualBodySeenCount=-1;
 float StreamerVisualKeyLightCd={_f(KEY_CD)},StreamerVisualKeyLightSoftCm={_f(KEY_SOFT_CM)},StreamerVisualKeyLightRadiusCm={_f(KEY_RADIUS_CM)},StreamerVisualKeyLightBodyOnly={_f(KEY_BODY_ONLY)};
 float StreamerVisualKeyLightState[6]={{-1,-1,-1,-1,-1,-1}};int32 StreamerVisualKeyLightBodyPrims=0,StreamerVisualDeskPropsMadeMovable=0;bool StreamerVisualChairPartsLogged=false;
 // SUB01_STREAMER_VISUAL_V2_V21 END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
INCLUDE_ANCHOR = '#include "RHIGPUReadback.h"\n'
INCLUDE_V21 = INCLUDE_ANCHOR + ('#include "RenderTimer.h" // SUB01_STREAMER_VISUAL_V2_V21: GGameThreadTime, GRenderThreadTime, GRHIThreadTime, GSwapBufferTime\n'
                                '#include "Engine/Engine.h" // SUB01_STREAMER_VISUAL_V2_V21: GEngine->Exec for the live console\n'
                                '#include "HAL/IConsoleManager.h" // SUB01_STREAMER_VISUAL_V2_V21\n')

FACE_BEGIN = '// SUB01_STREAMER_VISUAL_V2_FACE BEGIN (tools/native_streamer_visual_v2/install_face_camera.py)\n'
_PREFIX_LIST = ','.join(f'TEXT("{p}")' for p in CONSOLE_PREFIXES)
_PREFIX_TEXT = ' '.join(CONSOLE_PREFIXES) + ' t.MaxFPS'
CPP_METHODS = f'''// SUB01_STREAMER_VISUAL_V2_V21 BEGIN (tools/native_streamer_visual_v2/install_v21_fixes.py)
bool ASub01HomeCharacter::StreamerVisualConsoleAllowed(const FString& Command){{
 // A query (`<cvar>`) or a NUMERIC set (`<cvar> <number>`) of a cvar under the whitelisted prefixes (or t.MaxFPS), or exactly `csvprofile start`,
 // `csvprofile stop`, `csvprofile frames=<n>` (Kimi's review: no strings, no chaining, no paths, nothing that draws on the webcam: no stat).
 static const TCHAR* const Prefixes[]={{{_PREFIX_LIST}}};
 if(Command.Len()<=0||Command.Len()>{CONSOLE_MAX_CHARS})return false;
 if(Command==TEXT("csvprofile start")||Command==TEXT("csvprofile stop"))return true;
 auto Number=[](const FString& Text,int32 From,bool Signed){{int32 Count=0,Dots=0;for(int32 I=From;I<Text.Len();++I){{const TCHAR Ch=Text[I];
  if(Ch>=TEXT('0')&&Ch<=TEXT('9'))++Count;else if(Ch==TEXT('-')&&Signed&&I==From){{}}else if(Ch==TEXT('.')&&Signed&&Dots==0)++Dots;else return false;}}return Count>0;}};
 if(Command.StartsWith(TEXT("csvprofile frames="),ESearchCase::CaseSensitive))return Number(Command,18,false);
 FString CvarName=Command,CvarValue;if(Command.Split(TEXT(" "),&CvarName,&CvarValue)&&!Number(CvarValue,0,true))return false;
 for(const TCHAR Ch:CvarName)if(!((Ch>=TEXT('a')&&Ch<=TEXT('z'))||(Ch>=TEXT('A')&&Ch<=TEXT('Z'))||(Ch>=TEXT('0')&&Ch<=TEXT('9'))||Ch==TEXT('.')||Ch==TEXT('_')))return false;
 if(CvarName==TEXT("t.MaxFPS"))return true;
 for(const TCHAR* Prefix:Prefixes){{int32 Length=0;while(Prefix[Length])++Length;if(CvarName.Len()>Length&&CvarName.StartsWith(Prefix,ESearchCase::CaseSensitive))return true;}}
 return false;
}}
void ASub01HomeCharacter::ReadStreamerVisualConsole(){{
 // The private live console ({CONSOLE_PATH}, same file rules as the tuning file): runs once when `sequence` grows.
 TSharedPtr<FJsonObject> J;FString Schema;double Sequence=0;const TArray<TSharedPtr<FJsonValue>>* Commands=nullptr;
 if(!Sub01StreamerVisualPrivateJson("{CONSOLE_PATH}",J)||!J->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("{CONSOLE_SCHEMA}")||!J->TryGetNumberField(TEXT("sequence"),Sequence)||!FMath::IsFinite(Sequence)||Sequence<=StreamerVisualConsoleSequence)return;
 StreamerVisualConsoleSequence=Sequence;if(!J->TryGetArrayField(TEXT("commands"),Commands)||!Commands)return;
 int32 Seen=0;
 for(const TSharedPtr<FJsonValue>& Value:*Commands){{FString Command;if(!Value.IsValid()||!Value->TryGetString(Command))continue;
  if(++Seen>{CONSOLE_MAX_COMMANDS}||!StreamerVisualConsoleAllowed(Command)){{++StreamerVisualConsoleRefused;
   UE_LOG(LogTemp,Warning,TEXT("SUB01_STREAMER_VISUAL_CONSOLE refused seq=%.0f cmd=\\"%s\\" (at most {CONSOLE_MAX_COMMANDS} commands; <cvar> [number] under {_PREFIX_TEXT}; csvprofile start|stop|frames=N)"),Sequence,*Command);continue;}}
  const bool Handled=GEngine&&GEngine->Exec(GetWorld(),*Command);++(Handled?StreamerVisualConsoleApplied:StreamerVisualConsoleRefused);StreamerVisualConsoleLast=Command;
  FString CvarName=Command,CvarRest;Command.Split(TEXT(" "),&CvarName,&CvarRest);IConsoleVariable* Cvar=IConsoleManager::Get().FindConsoleVariable(*CvarName);
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CONSOLE seq=%.0f cmd=\\"%s\\" handled=%d value=%s"),Sequence,*Command,Handled?1:0,Cvar?*Cvar->GetString():TEXT("-"));
 }}
}}
void ASub01HomeCharacter::MakeStreamerVisualBodySeenByCaptures(){{
 // A scene capture has no view owner (USceneCaptureComponent::GetViewOwner() is null): every bOnlyOwnerSee primitive (the first-person body and
 // its followers) was culled from cam2. Streamer mode films him from outside only, so they become visible to every view.
 TArray<UPrimitiveComponent*> Prims;GetComponents(Prims);int32 Cleared=0;
 for(UPrimitiveComponent* Prim:Prims)if(Prim&&Prim->bOnlyOwnerSee){{Prim->SetOnlyOwnerSee(false);++Cleared;}}
 StreamerVisualBodySeenCount=Cleared;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_BODY_SEEN onlyOwnerSeeCleared=%d (a scene capture has no view owner: his owner-only primitives were hidden from cam2)"),Cleared);
}}
bool ASub01HomeCharacter::ProbeStreamerVisualCam2Reader(double Now){{
 // cam2 renders only for a reader. While none holds the FIFO the capture, readback and encode are skipped; every {PROBE_SECONDS:g} s the game thread
 // tries a non-blocking open (ENXIO = still nobody) and hands the descriptor to the writer task, which owns it from then on.
 FSub01StreamerCam2& Pipe=*StreamerVisualCam2Pipe;if(Pipe.Reader.load()||Pipe.HandoffFd.load()>=0)return true;
 if(Now<StreamerVisualCam2ProbeAt){{++StreamerVisualCam2Idle;return false;}}StreamerVisualCam2ProbeAt=Now+{_d(PROBE_SECONDS)};
 const int Probed=::open(TCHAR_TO_UTF8(*Pipe.FifoPath),O_WRONLY|O_NONBLOCK|O_CLOEXEC);
 if(Probed<0){{Pipe.OpenErrno.store(errno==ENXIO?0:errno);++StreamerVisualCam2Idle;return false;}}
 Pipe.HandoffFd.store(Probed);return true;
}}
void ASub01HomeCharacter::ApplyStreamerVisualCam2Lite(){{
 // cam2_lite 1: a cheaper second view (no AO/SSR/contact shadows/volumetric fog/lens flares/particles, culled beyond cam2_view_cm, LOD factor {CAM2_LOD_FACTOR:g}).
 if(!StreamerVisualCam2||(StreamerVisualCam2Lite==StreamerVisualCam2LiteApplied&&StreamerVisualCam2ViewCm==StreamerVisualCam2ViewApplied))return;
 StreamerVisualCam2LiteApplied=StreamerVisualCam2Lite;StreamerVisualCam2ViewApplied=StreamerVisualCam2ViewCm;const bool Lite=StreamerVisualCam2Lite>0;
 StreamerVisualCam2->ShowFlags.SetAmbientOcclusion(!Lite);StreamerVisualCam2->ShowFlags.SetScreenSpaceReflections(!Lite);StreamerVisualCam2->ShowFlags.SetContactShadows(!Lite);
 StreamerVisualCam2->ShowFlags.SetVolumetricFog(!Lite);StreamerVisualCam2->ShowFlags.SetLensFlares(!Lite);StreamerVisualCam2->ShowFlags.SetParticles(!Lite);
 StreamerVisualCam2->MaxViewDistanceOverride=Lite?StreamerVisualCam2ViewCm:-1.f;StreamerVisualCam2->LODDistanceFactor=Lite?{_f(CAM2_LOD_FACTOR)}:1.f;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CAM2_LITE lite=%d viewCm=%.0f lodFactor=%.1f"),Lite?1:0,Lite?StreamerVisualCam2ViewCm:-1.f,Lite?{_f(CAM2_LOD_FACTOR)}:1.f);
}}
void ASub01HomeCharacter::LogStreamerVisualChairParts(const FVector& Pelvis,const FVector& Facing,const FVector& Side){{
 // Once: every chair part in his frame (behind > 0 = behind the pelvis; depth = half size along his facing), to see which one is the backrest.
 for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){{AActor* A=StreamerVisualDeskProps[I].Get();if(!A||!StreamerVisualDeskPropIsChair.IsValidIndex(I)||!StreamerVisualDeskPropIsChair[I])continue;
  FVector Origin=FVector::ZeroVector,Extent=FVector::ZeroVector;A->GetActorBounds(false,Origin,Extent);const FVector Rel=Origin-Pelvis;
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_CHAIR_PART name=%s behindCm=%.1f sideCm=%.1f topAbovePelvisCm=%.1f halfDepth=%.1f halfWidth=%.1f halfHeight=%.1f prim=%d"),*A->GetName(),
   -FVector::DotProduct(Rel,Facing),FVector::DotProduct(Rel,Side),Origin.Z+Extent.Z-Pelvis.Z,FMath::Abs(Extent.X*Facing.X)+FMath::Abs(Extent.Y*Facing.Y),FMath::Abs(Extent.X*Side.X)+FMath::Abs(Extent.Y*Side.Y),Extent.Z,A->FindComponentByClass<UPrimitiveComponent>()?1:0);}}
}}
// SUB01_STREAMER_VISUAL_V2_V21 END
'''

# 1. perf thread times + window
PERF_FIRST = ('  StreamerVisualPerfLastNow=StreamerVisualPerfWindowStart=Now;StreamerVisualPerfWindowAt=Now+30;StreamerVisualPerfMaxMs=StreamerVisualPerfGpuSumMs=0;'
              'StreamerVisualPerfFrames=StreamerVisualPerfGpuSamples=0;return;}\n')
PERF_FIRST_V21 = ('  StreamerVisualPerfLastNow=StreamerVisualPerfWindowStart=Now;StreamerVisualPerfWindowAt=Now+StreamerVisualPerfWindowSeconds;StreamerVisualPerfMaxMs=StreamerVisualPerfGpuSumMs=0;'
                  'StreamerVisualPerfFrames=StreamerVisualPerfGpuSamples=0;for(double& Sum:StreamerVisualPerfThreadSum)Sum=0;StreamerVisualPerfThreadSamples=0;return;} // SUB01_STREAMER_VISUAL_V2_V21: perf_window_s\n')
PERF_SAMPLE = ' const uint32 Cycles=RHIGetGPUFrameCycles();if(Cycles>0){StreamerVisualPerfGpuSumMs+=FPlatformTime::ToMilliseconds(Cycles);++StreamerVisualPerfGpuSamples;}\n'
PERF_SAMPLE_V21 = PERF_SAMPLE + (' {const uint32 ThreadCycles[6]={' + ','.join(PERF_GLOBALS) + '}; // SUB01_STREAMER_VISUAL_V2_V21: the engine\'s per-frame cycle counters\n'
                                 '  for(int32 K=0;K<6;++K)StreamerVisualPerfThreadSum[K]+=FPlatformTime::ToMilliseconds(ThreadCycles[K]);++StreamerVisualPerfThreadSamples;}\n')
PERF_LOG = (' UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_PERF fps=%.1f ms=%.2f max_ms=%.1f gpu_ms=%.2f frames=%d window_s=%.0f gpu_samples=%d"),StreamerVisualPerfFps,'
            'StreamerVisualPerfFrameMs,StreamerVisualPerfMaxFrameMs,StreamerVisualPerfGpuMs,StreamerVisualPerfFrames,Span,StreamerVisualPerfGpuSamples);\n')
PERF_LOG_V21 = (' for(int32 K=0;K<6;++K)StreamerVisualPerfThreadMs[K]=StreamerVisualPerfThreadSamples?float(StreamerVisualPerfThreadSum[K]/StreamerVisualPerfThreadSamples):-1.f; // SUB01_STREAMER_VISUAL_V2_V21\n'
                ' UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_PERF fps=%.1f ms=%.2f max_ms=%.1f gpu_ms=%.2f frames=%d window_s=%.0f gpu_samples=%d '
                + ' '.join(f'{k}=%.2f' for k in PERF_THREADS) + '"),StreamerVisualPerfFps,'
                'StreamerVisualPerfFrameMs,StreamerVisualPerfMaxFrameMs,StreamerVisualPerfGpuMs,StreamerVisualPerfFrames,Span,StreamerVisualPerfGpuSamples,'
                + ','.join(f'StreamerVisualPerfThreadMs[{k}]' for k in range(6)) + ');\n')
PERF_RESET = (' StreamerVisualPerfWindowStart=Now;StreamerVisualPerfWindowAt=Now+30;StreamerVisualPerfMaxMs=StreamerVisualPerfGpuSumMs=0;'
              'StreamerVisualPerfFrames=StreamerVisualPerfGpuSamples=0;\n')
PERF_RESET_V21 = (' StreamerVisualPerfWindowStart=Now;StreamerVisualPerfWindowAt=Now+StreamerVisualPerfWindowSeconds;StreamerVisualPerfMaxMs=StreamerVisualPerfGpuSumMs=0;'
                  'StreamerVisualPerfFrames=StreamerVisualPerfGpuSamples=0;for(double& Sum:StreamerVisualPerfThreadSum)Sum=0;StreamerVisualPerfThreadSamples=0; // SUB01_STREAMER_VISUAL_V2_V21\n')

# 2. console poll (every tick of streamer mode, any schema)
TUNING_POLL = ('  if(StreamerVisualSchemaVersion==2&&Now>=StreamerVisualFaceTuningAt){StreamerVisualFaceTuningAt=Now+.5;if(ReadStreamerVisualFaceTuning()){StreamerVisualTuningChanged=true;'
               'StreamerVisualChairFitPasses=0;} /* SUB01_STREAMER_VISUAL_V2_POSEFIX: a tuning change re-fits the chair */}\n')
TUNING_POLL_V21 = ('  if(Now>=StreamerVisualConsoleAt){StreamerVisualConsoleAt=Now+.5;ReadStreamerVisualConsole();} // SUB01_STREAMER_VISUAL_V2_V21: the private live console\n'
                   + TUNING_POLL)

# 3. cam2: reader handoff, gate, lite flags, status
CAM2_ATOMICS = ' std::atomic<int32> EncodeBusy{0},OpenErrno{0};std::atomic<bool> Reader{false};std::atomic<int64> DroppedStale{0};\n'
CAM2_ATOMICS_V21 = CAM2_ATOMICS.rstrip('\n') + ' std::atomic<int> HandoffFd{-1}; // SUB01_STREAMER_VISUAL_V2_V21: a descriptor the game thread\'s reader probe opened\n'
CAM2_DTOR = ' ~FSub01StreamerCam2(){if(Fd>=0)::close(Fd);}\n'
CAM2_DTOR_V21 = ' ~FSub01StreamerCam2(){if(Fd>=0)::close(Fd);const int Handed=HandoffFd.exchange(-1);if(Handed>=0)::close(Handed);} // SUB01_STREAMER_VISUAL_V2_V21\n'
CAM2_OPEN = ('  const double Now=FPlatformTime::Seconds();\n'
             '  if(Fd<0){if(Now<NextOpenAt){++DroppedNoReader;return;}NextOpenAt=Now+1;\n'
             '   Fd=::open(TCHAR_TO_UTF8(*FifoPath),O_WRONLY|O_NONBLOCK|O_CLOEXEC); // ENXIO: nobody reads the FIFO yet\n'
             '   if(Fd<0){OpenErrno.store(errno==ENXIO?0:errno);Reader.store(false);++DroppedNoReader;return;} // ENXIO = no reader yet; any other errno is reported (status open_errno)\n'
             '   ::fcntl(Fd,F_SETPIPE_SZ,1048576);PipeBytes=::fcntl(Fd,F_GETPIPE_SZ);Rest.Reset();RestAt=0;Reader.store(true);OpenErrno.store(0);}\n')
CAM2_OPEN_V21 = ('  if(Fd<0){const int Offered=HandoffFd.load(); // SUB01_STREAMER_VISUAL_V2_V21: the game thread\'s probe is the ONLY opener; the writer adopts its fd\n'
                 '   if(Offered<0){++DroppedNoReader;return;} // no reader: frames still in flight when it left are dropped, never carried to the next one\n'
                 '   Reader.store(true);HandoffFd.store(-1);Fd=Offered; // Reader first: the probe never sees "no reader, no fd" while this one is adopted\n'
                 '   ::fcntl(Fd,F_SETPIPE_SZ,1048576);PipeBytes=::fcntl(Fd,F_GETPIPE_SZ);Rest.Reset();RestAt=0;OpenErrno.store(0);}\n')
CAM2_START = ' StreamerVisualCam2->ShowFlags.SetMotionBlur(false);StreamerVisualCam2->ShowFlags.SetDepthOfField(false);StreamerVisualCam2->RegisterComponent();\n'
CAM2_START_V21 = CAM2_START + ' MakeStreamerVisualBodySeenByCaptures();ApplyStreamerVisualCam2Lite(); // SUB01_STREAMER_VISUAL_V2_V21: he is in cam2; the lite flags from the tuning\n'
CAM2_GATE = ' const bool On=StreamerVisualCam2On>0&&StreamerVisualCam2Reason.IsEmpty();\n'
CAM2_GATE_V21 = (' ApplyStreamerVisualCam2Lite(); // SUB01_STREAMER_VISUAL_V2_V21\n'
                 ' const bool On=StreamerVisualCam2On>0&&StreamerVisualCam2Reason.IsEmpty()&&ProbeStreamerVisualCam2Reader(Now); // SUB01_STREAMER_VISUAL_V2_V21: no reader = a pause (nothing rendered)\n')
CAM2_STATUS = ' const int64 Last=Pipe.LastWrittenMs.load();Status->SetNumberField(TEXT("last_frame_utc"),Last>0?double(Last)/1000.:0.);\n'
CAM2_STATUS_V21 = CAM2_STATUS + (' Status->SetNumberField(TEXT("idle_no_reader"),double(StreamerVisualCam2Idle));Status->SetBoolField(TEXT("lite"),StreamerVisualCam2Lite>0); // SUB01_STREAMER_VISUAL_V2_V21\n')

# 4. tuning keys


def _tuning_anchor() -> str:
    """The cam2 layer's tuning line (one line of Field(...) calls ending with its marker)."""
    for key, anchor, new in cam2.EDITS:
        for line in new.split('\n'):
            if line.startswith(' Field(TEXT("cam2"),'):
                return line + '\n'
    raise Refused('cam2 tuning line not found in install_cam2.py')


TUNING_LINE = _tuning_anchor()
TUNING_LINE_V21 = TUNING_LINE + (' ' + ''.join(f'Field(TEXT("{k}"),{TUNING_FIELDS[k]},{lo},{hi});' for k, (lo, hi) in TUNING_LIMITS.items())
                                 + ' // SUB01_STREAMER_VISUAL_V2_V21\n')

# 5. key light (the whole function)
KEY_HEAD = 'void ASub01HomeCharacter::UpdateStreamerVisualKeyLight(double Now){\n'
KEY_END = 'void ASub01HomeCharacter::ApplyStreamerVisualBodyLook(){\n'
KEY_NEW = f'''void ASub01HomeCharacter::UpdateStreamerVisualKeyLight(double Now){{
 // SUB01_STREAMER_VISUAL_V2_V21: a SOFT, LOW key for the webcam, above the monitor centre, 6 cm towards him, the face camera's side offset to his left,
 // aimed at the face camera's head mean (else the Head bone sampled every 2 s). The house is exposed for very dim light: 1.25 cd already clipped
 // his face (game l), so `key_cd` is in candelas (default {KEY_CD:g}; 0 hides it), `key_soft_cm` widens the source, `key_radius_cm` keeps it on him;
 // `key_body_only` 1 puts it on lighting channel 1 and his primitives on channels 0+1: it never lights the chair, the desk or the walls.
 if(!StreamerVisualKeyLight)return;const float Cd=StreamerVisualSchemaVersion==2?StreamerVisualKeyLightCd:0.f;
 if(StreamerVisualFaceAimed)StreamerVisualKeyLightAim=StreamerVisualFaceAim;
 else if(Now>=StreamerVisualKeyLightSampleAt||StreamerVisualKeyLightAim.IsNearlyZero()){{StreamerVisualKeyLightSampleAt=Now+2;const FVector BodyAt=FirstPersonBody?FirstPersonBody->GetComponentLocation():FVector(214,-289,6.19);
  const bool HasHead=FirstPersonBody&&FirstPersonBody->GetBoneIndex(TEXT("Head"))!=INDEX_NONE;FVector Head=HasHead?FirstPersonBody->GetBoneLocation(TEXT("Head")):FVector::ZeroVector;
  StreamerVisualKeyLightAim=HasHead&&!Head.ContainsNaN()&&FVector::Dist(Head,BodyAt)<=250?Head:BodyAt+FVector(0,0,120);}}
 const FVector Monitor(217,-367.67,114.75);FVector Towards(StreamerVisualKeyLightAim.X-Monitor.X,StreamerVisualKeyLightAim.Y-Monitor.Y,0);
 Towards=Towards.Size()>10?Towards.GetSafeNormal():FVector(0,1,0);const FVector Side=FVector::CrossProduct(FVector::UpVector,-Towards);
 const FVector Location=Monitor+Towards*6.+Side*double(StreamerVisualFaceSideCm)+FVector(0,0,StreamerVisualKeyLightUpCm);
 StreamerVisualKeyLight->SetWorldLocationAndRotation(Location,(StreamerVisualKeyLightAim-Location).Rotation());
 const float Want[6]={{Cd,StreamerVisualKeyLightTempK,StreamerVisualKeyLightUpCm,StreamerVisualKeyLightSoftCm,StreamerVisualKeyLightRadiusCm,StreamerVisualKeyLightBodyOnly}};bool Same=true;
 for(int32 K=0;K<6;++K)Same=Same&&Want[K]==StreamerVisualKeyLightState[K];if(Same)return;for(int32 K=0;K<6;++K)StreamerVisualKeyLightState[K]=Want[K];
 const bool BodyOnly=StreamerVisualKeyLightBodyOnly>0;
 StreamerVisualKeyLight->SetIntensity(Cd);StreamerVisualKeyLight->SetTemperature(StreamerVisualKeyLightTempK);StreamerVisualKeyLight->SetAttenuationRadius(StreamerVisualKeyLightRadiusCm);
 StreamerVisualKeyLight->SetSourceRadius(StreamerVisualKeyLightSoftCm*.5f);StreamerVisualKeyLight->SetSoftSourceRadius(StreamerVisualKeyLightSoftCm);
 StreamerVisualKeyLight->SetInnerConeAngle({_f(KEY_CONES[0])});StreamerVisualKeyLight->SetOuterConeAngle({_f(KEY_CONES[1])});StreamerVisualKeyLight->SetLightingChannels(!BodyOnly,BodyOnly,false);
 TArray<UPrimitiveComponent*> Prims;GetComponents(Prims);int32 Lit=0;
 for(UPrimitiveComponent* Prim:Prims)if(Prim&&FirstPersonBody&&(Prim==FirstPersonBody||Prim->IsAttachedTo(FirstPersonBody))){{Prim->SetLightingChannels(true,BodyOnly,false);++Lit;}}
 StreamerVisualKeyLightBodyPrims=Lit;StreamerVisualKeyLight->SetVisibility(Cd>0);
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_KEY_LIGHT cd=%.3f tempK=%.0f upCm=%.1f softCm=%.1f radiusCm=%.0f bodyOnly=%d bodyPrims=%d location=%s aim=%s"),Cd,StreamerVisualKeyLightTempK,StreamerVisualKeyLightUpCm,
  StreamerVisualKeyLightSoftCm,StreamerVisualKeyLightRadiusCm,BodyOnly?1:0,Lit,*Location.ToString(),*StreamerVisualKeyLightAim.ToString());
}}
'''

# 6. chair fit: the backrest by trace on every part, else by shape; the parts logged once
FIT_PROBE = ' const FVector Probe=Sacrum+FVector(0,0,6);double Front=-1e9,Traced=-1e9;int32 Parts=0;FString Name,TracedName;\n'
FIT_LOOP_OLD = (
    ' for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){AActor* A=StreamerVisualDeskProps[I].Get();if(!A||!StreamerVisualDeskPropIsChair.IsValidIndex(I)||!StreamerVisualDeskPropIsChair[I])continue;\n'
    '  FVector Origin=FVector::ZeroVector,Extent=FVector::ZeroVector;A->GetActorBounds(false,Origin,Extent);const FVector Rel=Origin-Pelvis;\n'
    '  if(FVector::DotProduct(Rel,Facing)>-3||Origin.Z+Extent.Z<Pelvis.Z+15||FMath::Abs(FVector::DotProduct(Rel,Side))>20)continue; // not the backrest (seat, legs, armrests)\n'
    '  if(UPrimitiveComponent* Prim=A->FindComponentByClass<UPrimitiveComponent>()){FHitResult Hit;const FCollisionQueryParams Params(FName(TEXT("Sub01ChairFit")),true); // its real surface at sacrum height\n'
    '   if(Prim->LineTraceComponent(Hit,Probe+Facing*30,Probe-Facing*40,Params)){const double At=FVector::DotProduct(FVector(Hit.ImpactPoint),Facing);if(At>Traced){Traced=At;TracedName=A->GetName();}}}\n'
    "  const double F=FVector::DotProduct(Origin,Facing)+FMath::Abs(Extent.X*Facing.X)+FMath::Abs(Extent.Y*Facing.Y); // the box's front-most point along the facing\n"
    '  if(F>Front){Front=F;Name=A->GetName();}++Parts;\n'
    ' }\n')
FIT_LOOP_NEW = (
    ' if(!StreamerVisualChairPartsLogged){StreamerVisualChairPartsLogged=true;LogStreamerVisualChairParts(Pelvis,Facing,Side);} // SUB01_STREAMER_VISUAL_V2_V21: the backrest by shape, then its traced surface\n'
    ' const double PelvisAt=FVector::DotProduct(Pelvis,Facing);\n'
    ' for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){AActor* A=StreamerVisualDeskProps[I].Get();if(!A||!StreamerVisualDeskPropIsChair.IsValidIndex(I)||!StreamerVisualDeskPropIsChair[I])continue;\n'
    '  FVector Origin=FVector::ZeroVector,Extent=FVector::ZeroVector;A->GetActorBounds(false,Origin,Extent);const FVector Rel=Origin-Pelvis;\n'
    '  const double AlongFacing=FVector::DotProduct(Rel,Facing),HalfDepth=FMath::Abs(Extent.X*Facing.X)+FMath::Abs(Extent.Y*Facing.Y),HalfWidth=FMath::Abs(Extent.X*Side.X)+FMath::Abs(Extent.Y*Side.Y);\n'
    f'  if(Origin.Z+Extent.Z<Pelvis.Z+{_d(BACKREST_MIN_TOP_CM)}||Extent.Z<{_d(BACKREST_MIN_HALF_HEIGHT_CM)}||FMath::Abs(FVector::DotProduct(Rel,Side))>{_d(BACKREST_MAX_SIDE_CM)}||FMath::Abs(AlongFacing)>{_d(BACKREST_MAX_ALONG_CM)}'
    f'||HalfDepth>FMath::Max({_d(BACKREST_THIN_CM)},{_d(BACKREST_THIN_RATIO)}*HalfWidth))continue; // the backrest: tall, central, near, THIN along his facing (it may cut through him)\n'
    '  if(UPrimitiveComponent* Prim=A->FindComponentByClass<UPrimitiveComponent>()){FHitResult Hit;const FCollisionQueryParams Params(FName(TEXT("Sub01ChairFit")),true); // its real surface at sacrum height\n'
    f'   if(Prim->LineTraceComponent(Hit,Probe+Facing*30,Probe-Facing*40,Params)){{const double At=FVector::DotProduct(FVector(Hit.ImpactPoint),Facing);if(At>=PelvisAt-{_d(TRACE_BEHIND_CM)}&&At<=PelvisAt+{_d(TRACE_FRONT_CM)}&&At>Traced){{Traced=At;TracedName=A->GetName();}}}}}}\n'
    "  const double F=FVector::DotProduct(Origin,Facing)+HalfDepth; // the box's front-most point along the facing\n"
    '  if(F>Front){Front=F;Name=A->GetName();}++Parts;\n'
    ' }\n')
FIT_CLAMP = 'Facing)+Move,-25.,25.);'
FIT_CLAMP_V21 = f'Facing)+Move,-{_d(CHAIR_FIT_MAX_CM)},{_d(CHAIR_FIT_MAX_CM)}); /* SUB01_STREAMER_VISUAL_V2_V21: +-{CHAIR_FIT_MAX_CM:g} cm (the backrest cut ~29 cm into him on the pod) */'
FIT_NONE = ' if(!Parts){StreamerVisualChairFitPasses=4;StreamerVisualBackrestName=TEXT("none");\n'
FIT_NONE_V21 = FIT_NONE  # unchanged: the trace runs on shape candidates only

# 7. the pose fix's rotation record that a comment swallowed in the desk-prop scan
SCAN_LINE = ('  if(!DeskProp&&!ChairPart)continue;StreamerVisualDeskProps.Add(A);StreamerVisualDeskPropOrigins.Add(L);StreamerVisualDeskPropIsChair.Add(ChairPart); '
             '// SUB01_STREAMER_VISUAL_V2_STREAMPASS StreamerVisualDeskPropRotations.Add(A->GetActorQuat()); // SUB01_STREAMER_VISUAL_V2_POSEFIX\n')
SCAN_LINE_V21 = ('  if(!DeskProp&&!ChairPart)continue;StreamerVisualDeskProps.Add(A);StreamerVisualDeskPropOrigins.Add(L);StreamerVisualDeskPropIsChair.Add(ChairPart);'
                 'StreamerVisualDeskPropRotations.Add(A->GetActorQuat()); // SUB01_STREAMER_VISUAL_V2_STREAMPASS; SUB01_STREAMER_VISUAL_V2_POSEFIX (a statement again: SUB01_STREAMER_VISUAL_V2_V21)\n'
                 '  if(USceneComponent* PropRoot=A->GetRootComponent()){if(PropRoot->GetMobility()!=EComponentMobility::Movable){PropRoot->SetMobility(EComponentMobility::Movable);++StreamerVisualDeskPropsMadeMovable;}} '
                 '// SUB01_STREAMER_VISUAL_V2_V21: the level\'s props are Static: every move failed ("has to be \'Movable\'", 605 warnings on game m2), so the keyboard and the chair never followed him\n')

# 8. receipt
RECEIPT = ('   Receipt->SetBoolField(TEXT("mouse_prop"),StreamerVisualMouseActor.IsValid());Receipt->SetNumberField(TEXT("key_light"),'
           'StreamerVisualSchemaVersion==2?StreamerVisualKeyLightLevel:0.f);\n')
RECEIPT_V21 = RECEIPT + ('   Receipt->SetNumberField(TEXT("key_light_cd"),StreamerVisualSchemaVersion==2?StreamerVisualKeyLightCd:0.f);Receipt->SetNumberField(TEXT("key_body_only"),StreamerVisualKeyLightBodyOnly);'
                         'Receipt->SetNumberField(TEXT("body_seen_cleared"),StreamerVisualBodySeenCount);Receipt->SetNumberField(TEXT("desk_props_made_movable"),StreamerVisualDeskPropsMadeMovable); // SUB01_STREAMER_VISUAL_V2_V21\n'
                         + '   ' + ''.join(f'Receipt->SetNumberField(TEXT("perf_{k}"),StreamerVisualPerfThreadMs[{i}]);' for i, k in enumerate(PERF_THREADS))
                         + 'Receipt->SetNumberField(TEXT("perf_window_s"),StreamerVisualPerfWindowSeconds);\n'
                         '   Receipt->SetNumberField(TEXT("console_applied"),StreamerVisualConsoleApplied);Receipt->SetNumberField(TEXT("console_refused"),StreamerVisualConsoleRefused);'
                         'Receipt->SetStringField(TEXT("console_last"),StreamerVisualConsoleLast);Receipt->SetNumberField(TEXT("cam2_idle_no_reader"),double(StreamerVisualCam2Idle));'
                         'Receipt->SetBoolField(TEXT("cam2_lite"),StreamerVisualCam2Lite>0);\n')

EDITS = [
    ('header', HEADER_CAM2_END, HEADER_CAM2_END + HEADER_FIELDS),
    ('cpp', INCLUDE_ANCHOR, INCLUDE_V21),
    ('cpp', FACE_BEGIN, CPP_METHODS + FACE_BEGIN),
    ('cpp', PERF_FIRST, PERF_FIRST_V21),
    ('cpp', PERF_SAMPLE, PERF_SAMPLE_V21),
    ('cpp', PERF_LOG, PERF_LOG_V21),
    ('cpp', PERF_RESET, PERF_RESET_V21),
    ('cpp', TUNING_POLL, TUNING_POLL_V21),
    ('cpp', CAM2_ATOMICS, CAM2_ATOMICS_V21),
    ('cpp', CAM2_DTOR, CAM2_DTOR_V21),
    ('cpp', CAM2_OPEN, CAM2_OPEN_V21),
    ('cpp', CAM2_START, CAM2_START_V21),
    ('cpp', CAM2_GATE, CAM2_GATE_V21),
    ('cpp', CAM2_STATUS, CAM2_STATUS_V21),
    ('cpp', TUNING_LINE, TUNING_LINE_V21),
    ('cpp', FIT_LOOP_OLD, FIT_LOOP_NEW),
    ('cpp', FIT_CLAMP, FIT_CLAMP_V21),
    ('cpp', SCAN_LINE, SCAN_LINE_V21),
    ('cpp', RECEIPT, RECEIPT_V21),
]
KEY_EDIT = ('cpp', KEY_HEAD, KEY_END)  # the whole UpdateStreamerVisualKeyLight, replaced by span


def plan(sources: dict) -> dict:
    """Pure transformation of the two LF texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (v21 fixes already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    for name, marker in (('the stream pass', streampass.MARKER), ('cam2', cam2.MARKER), ('the pose fix', posefix.MARKER)):
        problems += [f'{FILES[key]} lacks {name} ({marker}); run the v20 stack first' for key in FILES if marker + ' BEGIN' not in sources[key]]
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
    key, head, end = KEY_EDIT
    count = out[key].count(head)
    edits.append({'file': FILES[key], 'anchor': head.strip()[:96], 'anchor_sha256': v2.sha256(head), 'count': count})
    if count != 1 or out[key].count(end) != 1 or out[key].index(head) > out[key].index(end):
        problems.append(f'key light function span not found exactly once in {FILES[key]}')
    else:
        i, j = out[key].index(head), out[key].index(end)
        out[key] = out[key][:i] + KEY_NEW + out[key][j:]
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
    report = {'schema': 'sub01.native-streamer-visual-v2-v21-install.v1', 'source': str(source), 'dry_run': dry_run, 'marker': MARKER,
              'requires': [posefix.MARKER, cam2.MARKER, streampass.MARKER, seatfix.MARKER, v2.MARKER],
              'perf': {'window_s': PERF_WINDOW_S, 'threads': dict(zip(PERF_THREADS, PERF_GLOBALS))},
              'console': {'path': CONSOLE_PATH, 'schema': CONSOLE_SCHEMA, 'prefixes': list(CONSOLE_PREFIXES), 'max_commands': CONSOLE_MAX_COMMANDS, 'max_chars': CONSOLE_MAX_CHARS},
              'cam2': {'reader_probe_s': PROBE_SECONDS, 'lite': CAM2_LITE, 'view_cm': CAM2_VIEW_CM, 'lod_factor': CAM2_LOD_FACTOR, 'body_only_owner_see_cleared': True},
              'key_light': {'cd': KEY_CD, 'soft_cm': KEY_SOFT_CM, 'radius_cm': KEY_RADIUS_CM, 'body_only': KEY_BODY_ONLY, 'cones_deg': list(KEY_CONES)},
              'backrest': {'min_top_cm': BACKREST_MIN_TOP_CM, 'min_half_height_cm': BACKREST_MIN_HALF_HEIGHT_CM, 'max_side_cm': BACKREST_MAX_SIDE_CM,
                           'max_along_cm': BACKREST_MAX_ALONG_CM, 'thin_cm': BACKREST_THIN_CM, 'thin_ratio': BACKREST_THIN_RATIO,
                           'trace_window_cm': [-TRACE_BEHIND_CM, TRACE_FRONT_CM], 'fit_clamp_cm': CHAIR_FIT_MAX_CM},
              'tuning_limits': TUNING_LIMITS, 'edits': result['edits'],
              'files': {FILES[key]: {'before_sha256': v2.sha256(raw[key]), 'after_sha256': v2.sha256(after[key]),
                                     'bytes_before': len(raw[key].encode()), 'bytes_after': len(after[key].encode()),
                                     'line_ending': 'CRLF' if eol[key] == '\r\n' else 'LF',
                                     'edits': sum(1 for k, _, _ in EDITS if k == key) + (1 if key == KEY_EDIT[0] else 0)} for key in FILES}}
    if not dry_run:
        v2.write_atomically({source / FILES[key]: after[key] for key in FILES})
        for key in FILES:
            if v2.sha256(v2.read_raw(source / FILES[key])) != report['files'][FILES[key]]['after_sha256']:
                raise Refused(f'{FILES[key]}: written bytes differ from the plan')
    report['status'] = 'planned' if dry_run else 'applied'
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='directory with the v20 pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-v21-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
