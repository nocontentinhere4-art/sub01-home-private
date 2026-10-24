"""Seat fix ON TOP of v2 + face + pin fix + no-pin: the body sits in the chair with the v2 loops; measured face camera.

    python tools/native_streamer_visual_v2/install_seat_fix.py --source <dir> [--dry-run]

Field result (builds v10..v14, game e on 2026-10-23): the Desk7 loops are authored ~1 m behind R9's station in component
space (pelvis at 0 s (-0.058,-92.651,73.049) vs R9@0.7 (0.908,6.407,88.529), 25.6 deg apart) and these players never
extract root motion, so the body sat in the air 1 m behind the chair. Pinning bones (v11/v13) also moved the body because
every camera switch calls SetControlRotation and ACharacter::bUseControllerRotationYaw turns the root (and the attached
mesh) to the camera look: the receipt's body_world yaw read -146.31 (the spectator look) instead of the authored 165.4.

1. Seat offset on the MESH COMPONENT, never on bones: for every clip the proxy computes once, in component space, the
   transform D with  clipPelvis(reference time) * D = R9Pelvis@0.7 s  (translation exactly; rotation = the yaw twist of
   R9 * clip^-1, so the authored pelvis tilt of the clip is kept). Each evaluation publishes D of the playing clip,
   blended with the crossfade weight from the previous clip's D (the frozen R9 gives the identity by construction).
   The character sets the mesh relative transform to D * (authored relative transform) when it changes (> 0.01 cm/deg) and
   restores the authored one when v2 ends. The clips themselves play untouched (the no-pin guard still only measures).
2. `bUseControllerRotationYaw=false` at v2 start: the root keeps the authored yaw; camera looks no longer turn the body.
3. Face camera = a webcam ON the monitor: monitor bounds centre + FACE_UP_CM up, FACE_FORWARD_CM towards him, FACE_SIDE_CM
   to his right (a fixed point), aimed at the MEASURED Head bone (mean over FACE_SAMPLE_SECONDS, the loops sway the head
   ~5 cm) minus FACE_AIM_DROP_CM, FOV FACE_FOV; aimed once per selection after the seat offset has settled (else after
   2 s). An optional private tuning file (`streamer-visual-face-tuning.json`, uid/0600 like the event, clamped) re-aims
   when its `sequence` grows: the compiled defaults are the verified framing. The body's BoundsScale is raised to
   BOUNDS_SCALE: with the component origin ~1.2 m from the pose, the fixed ref-pose bounds were frustum-culled from the
   face camera (empty chair in frame while the spectator camera showed him).
   Pull-back knob (`seat_back_cm` 0..40, `seat_side_cm` -20..20 in the same file): a constant translation away from the
   monitor along the body facing, composed with the clip offset on the mesh component (restored when v2 ends); the small
   StaticMeshActors in the keyboard/mouse region (half extents <= 40/40/15 cm) move by the same world delta so the hands
   keep contact; logged as `SUB01_STREAMER_VISUAL_SEAT_BACK` and `..._DESK_PROPS`.
4. Receipt adds `seat_offset`, `seat_offset_cm`, `seat_offset_yaw_deg`, `seat_offset_applied`, `seat_offset_settled`,
   `pelvis_world`, `head_world`, `face_camera_location`, `face_camera_aim`, `face_camera_tuning_sequence`, `camera_world`.
   Logs: `SUB01_STREAMER_VISUAL_SEAT_FIX_READY`, `..._SEAT_OFFSET` (per clip), `..._FACE_RIG` (bones/morph targets the
   skeleton offers for mouth movement; report only), `..._FACE_CAMERA` (final numbers).
All four files change (anchors found exactly once, all or nothing). Refused when the no-pin patch is absent or
`// SUB01_STREAMER_VISUAL_V2_SEATFIX` is already present.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location('sub01_streamer_visual_v2_nopin', Path(__file__).resolve().parent / 'install_no_pin.py')
nopin = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(nopin)
pinfix, face, v2, Refused = nopin.pinfix, nopin.pinfix.face, nopin.v2, nopin.Refused

MARKER = '// SUB01_STREAMER_VISUAL_V2_SEATFIX'
FILES = dict(v2.FILES)
TUNING_PATH = '/home/unreal/.sub01-private/streamer-visual-face-tuning.json'
TUNING_SCHEMA = 'sub01.private-streamer-visual-face-tuning.v1'
# Webcam on the monitor: FACE_UP_CM above the monitor bounds centre (the panel top edge is ~15 cm above it, the light bar on
# it ~20), FACE_FORWARD_CM towards him, FACE_SIDE_CM to his right; aimed at the mean Head bone of FACE_SAMPLE_SECONDS minus
# FACE_AIM_DROP_CM. Verified on the pod (game g, 2026-10-23): his head leans to ~35 cm from the screen, so FOV 70 is what
# frames face + shoulders + the room; the owner's 40-45 shows the face alone (set fov_deg in the tuning file to compare).
FACE_UP_CM, FACE_FORWARD_CM, FACE_SIDE_CM, FACE_AIM_DROP_CM, FACE_FOV, FACE_SAMPLE_SECONDS = 6.0, 2.0, -12.0, 0.0, 65.0, 1.0
# Pull-back of the seat (him, keyboard and mouse) away from the monitor along the body facing, so a webcam on the monitor
# can frame head + shoulders + upper chest: a knob of the same tuning file (default 0 = the authored station).
SEAT_BACK_CM, SEAT_SIDE_CM = 0.0, 0.0
TUNING_LIMITS = {'up_cm': (-30, 120), 'forward_cm': (-30, 150), 'side_cm': (-100, 100), 'aim_drop_cm': (-50, 80), 'fov_deg': (20, 110),
                 'seat_back_cm': (0, 40), 'seat_side_cm': (-20, 20), 'desk_props': (0, 1), 'posture_lean_deg': (-20, 20), 'posture_head_deg': (-20, 20)}
# "Sit up" posture layer: posture_lean_deg of local pitch split over Spine1/Spine2 (the breathing axis), posture_head_deg on
# the Head (the gaze axis), eased at POSTURE_RATE_DEG_PER_S; compiled default 0 (the clips as authored).
POSTURE_LEAN_DEG, POSTURE_HEAD_DEG, POSTURE_RATE_DEG_PER_S = 0.0, 0.0, 12.0
# Keyboard and mouse on the pod level (game h scan, 2026-10-23): the keyboard is the "R15Part*" pack split into ~140 small
# StaticMeshActors (body 592/593, keycaps, knob, feet) at X 194..225, Y -346..-329, Z ~80; the desk itself is
# "SUB01_RealLinea140_*" (never moved), the mat R15Part0000/0016 is large, the clock R15Part0249 sits at X 253, the macro
# pad at X 182, the glowing mouse is not a StaticMeshActor (any actor named *mouse*/*keyboard* with a static mesh follows).
DESK_PROP_REGION = {'x': (188, 245), 'y': (-348, -320), 'z': (66, 96)}
DESK_PROP_MAX_EXTENT = (25, 12, 8)  # half extents: anything larger (desk parts, mats) never moves
DESK_PROP_MESH_PREFIX = 'R15Part'
# The chair: static-mesh actors around the authored pelvis (the chair parts, armrests included) move with him; the desk
# (SUB01_RealLinea140_*) and anything large (floor, rug, walls) never do.
CHAIR_ZONE = {'x': (170, 260), 'y': (-322, -250), 'z': (-10, 100)}
CHAIR_MAX_EXTENT = (60, 60, 80)
DESK_MESH_PREFIX = 'SUB01_RealLinea140'
SEAT_EPSILON = 0.01
MONITOR = (217, -367.67, 114.75)
BOUNDS_SCALE = 4.0  # the clips' poses sit ~1.2 m from the (offset) component origin: the fixed ref-pose bounds would be frustum-culled


def _line(text: str, start: str) -> str:
    hits = [line for line in text.splitlines(keepends=True) if line.startswith(start)]
    if len(hits) != 1:
        raise RuntimeError(f'expected one line starting with {start!r}, found {len(hits)}')
    return hits[0]


# ------------------------------------------------------------------------------------------------ Sub01HomeLab.h
HEADER_FACE_BEGIN = _line(face.HEADER_FIELDS, ' // SUB01_STREAMER_VISUAL_V2_FACE BEGIN')
HEADER_FIELDS = f''' // SUB01_STREAMER_VISUAL_V2_SEATFIX BEGIN (tools/native_streamer_visual_v2/install_seat_fix.py): seat offset on the mesh component,
 // root yaw decoupled from the camera look, face camera from the measured head (optional private tuning file).
 bool ReadStreamerVisualFaceTuning();
 FTransform StreamerVisualBodyRelative=FTransform::Identity,StreamerVisualSeatApplied=FTransform::Identity;
 bool StreamerVisualBodyRelativeValid=false,StreamerVisualSeatHas=false,StreamerVisualControllerYawWas=true;
 double StreamerVisualFaceSelectedAt=-10,StreamerVisualFaceTuningAt=0,StreamerVisualFaceTuningSequence=0,StreamerVisualFaceSampleAt=-10;
 float StreamerVisualFaceUpCm={FACE_UP_CM:g}.f,StreamerVisualFaceForwardCm={FACE_FORWARD_CM:g}.f,StreamerVisualFaceSideCm={FACE_SIDE_CM:g}.f,StreamerVisualFaceAimDropCm={FACE_AIM_DROP_CM:g}.f,StreamerVisualFaceFov={FACE_FOV:g}.f;
 FVector StreamerVisualFaceAim=FVector::ZeroVector,StreamerVisualFaceHeadSum=FVector::ZeroVector;int32 StreamerVisualFaceHeadCount=0;
 // Pull-back knob (seat_back_cm / seat_side_cm of the tuning file): him and the small desk props move together, away from the monitor.
 void ScanStreamerVisualDeskProps();void ApplyStreamerVisualDeskProps(const FVector& WorldDelta);
 FVector StreamerVisualFacingLocal=FVector(0,1,0),StreamerVisualRightLocal=FVector(-1,0,0),StreamerVisualDeskPropDelta=FVector::ZeroVector;
 FTransform StreamerVisualBodyAuthoredWorld=FTransform::Identity;
 float StreamerVisualSeatBackCm={SEAT_BACK_CM:g}.f,StreamerVisualSeatSideCm={SEAT_SIDE_CM:g}.f,StreamerVisualSeatBackApplied=-1,StreamerVisualSeatSideApplied=0;
 bool StreamerVisualTuningChanged=false,StreamerVisualDeskPropsScanned=false;int32 StreamerVisualDeskPropsMoved=0,StreamerVisualChairParts=0;float StreamerVisualDeskPropsEnabled=1;
 float StreamerVisualPostureLeanDeg={POSTURE_LEAN_DEG:g}.f,StreamerVisualPostureHeadDeg={POSTURE_HEAD_DEG:g}.f,StreamerVisualPostureLeanApplied=0,StreamerVisualPostureHeadApplied=0,StreamerVisualPostureLeanLogged=-999,StreamerVisualPostureHeadLogged=-999;
 TArray<TWeakObjectPtr<AActor>> StreamerVisualDeskProps;TArray<FVector> StreamerVisualDeskPropOrigins;
 // SUB01_STREAMER_VISUAL_V2_SEATFIX END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeLab.cpp
CPP_FACE_BEGIN = '// SUB01_STREAMER_VISUAL_V2_FACE BEGIN (tools/native_streamer_visual_v2/install_face_camera.py)\n#include "UObject/UnrealType.h"\n'
CPP_HELPERS = f'''// SUB01_STREAMER_VISUAL_V2_SEATFIX BEGIN (tools/native_streamer_visual_v2/install_seat_fix.py)
#include "Animation/MorphTarget.h"
#include "Engine/StaticMeshActor.h"
static bool Sub01StreamerVisualPrivateJson(const char* Path,TSharedPtr<FJsonObject>& J){{ // the v1 event file rules: regular, own uid, no group/other bits, <= 2048 bytes
 struct stat S;FString Raw;
 return lstat(Path,&S)==0&&S_ISREG(S.st_mode)&&S.st_uid==getuid()&&!(S.st_mode&0077)&&S.st_size>0&&S.st_size<=2048&&FFileHelper::LoadFileToString(Raw,UTF8_TO_TCHAR(Path))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Raw),J)&&J.IsValid();
}}
bool ASub01HomeCharacter::ReadStreamerVisualFaceTuning(){{
 // Optional private tuning of the face camera ({TUNING_PATH}): applied when `sequence` grows, every value clamped;
 // the compiled defaults are the verified framing. Returns true when the camera must be aimed again.
 TSharedPtr<FJsonObject> J;FString Schema;double Sequence=0;
 if(!Sub01StreamerVisualPrivateJson("{TUNING_PATH}",J)||!J->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("{TUNING_SCHEMA}")||!J->TryGetNumberField(TEXT("sequence"),Sequence)||!FMath::IsFinite(Sequence)||Sequence<=StreamerVisualFaceTuningSequence)return false;
 auto Field=[&J](const TCHAR* Key,float& Out,double Lo,double Hi){{double V=0;if(J->TryGetNumberField(Key,V)&&FMath::IsFinite(V))Out=float(FMath::Clamp(V,Lo,Hi));}};
 Field(TEXT("up_cm"),StreamerVisualFaceUpCm,{TUNING_LIMITS['up_cm'][0]},{TUNING_LIMITS['up_cm'][1]});Field(TEXT("forward_cm"),StreamerVisualFaceForwardCm,{TUNING_LIMITS['forward_cm'][0]},{TUNING_LIMITS['forward_cm'][1]});Field(TEXT("side_cm"),StreamerVisualFaceSideCm,{TUNING_LIMITS['side_cm'][0]},{TUNING_LIMITS['side_cm'][1]});
 Field(TEXT("aim_drop_cm"),StreamerVisualFaceAimDropCm,{TUNING_LIMITS['aim_drop_cm'][0]},{TUNING_LIMITS['aim_drop_cm'][1]});Field(TEXT("fov_deg"),StreamerVisualFaceFov,{TUNING_LIMITS['fov_deg'][0]},{TUNING_LIMITS['fov_deg'][1]});
 Field(TEXT("seat_back_cm"),StreamerVisualSeatBackCm,{TUNING_LIMITS['seat_back_cm'][0]},{TUNING_LIMITS['seat_back_cm'][1]});Field(TEXT("seat_side_cm"),StreamerVisualSeatSideCm,{TUNING_LIMITS['seat_side_cm'][0]},{TUNING_LIMITS['seat_side_cm'][1]});Field(TEXT("desk_props"),StreamerVisualDeskPropsEnabled,{TUNING_LIMITS['desk_props'][0]},{TUNING_LIMITS['desk_props'][1]});
 Field(TEXT("posture_lean_deg"),StreamerVisualPostureLeanDeg,{TUNING_LIMITS['posture_lean_deg'][0]},{TUNING_LIMITS['posture_lean_deg'][1]});Field(TEXT("posture_head_deg"),StreamerVisualPostureHeadDeg,{TUNING_LIMITS['posture_head_deg'][0]},{TUNING_LIMITS['posture_head_deg'][1]});
 StreamerVisualFaceTuningSequence=Sequence;return true;
}}
void ASub01HomeCharacter::ScanStreamerVisualDeskProps(){{
 // Followers of the pull-back: (1) keyboard and mouse, the "{DESK_PROP_MESH_PREFIX}*" pack (the keyboard split into small actors) in the zone in
 // front of the chair plus any actor named mouse/keyboard with a static mesh; (2) the chair: every static-mesh actor around the
 // authored pelvis that is chair-sized (armrests included). Desk parts ({DESK_MESH_PREFIX}_*), the mat, the clock, the macro
 // pad, the floor/rug/walls never move (zone, size or name; all candidates logged).
 StreamerVisualDeskPropsScanned=true;StreamerVisualDeskProps.Reset();StreamerVisualDeskPropOrigins.Reset();FString Found,Chair;int32 Count=0,ChairCount=0;
 if(!GetWorld())return;
 for(TActorIterator<AActor> It(GetWorld());It;++It){{AActor* A=*It;if(!A)continue;const UStaticMeshComponent* SMC=A->FindComponentByClass<UStaticMeshComponent>();if(!SMC)continue;const FVector L=A->GetActorLocation();
  const bool InDesk=L.X>={DESK_PROP_REGION['x'][0]}&&L.X<={DESK_PROP_REGION['x'][1]}&&L.Y>={DESK_PROP_REGION['y'][0]}&&L.Y<={DESK_PROP_REGION['y'][1]}&&L.Z>={DESK_PROP_REGION['z'][0]}&&L.Z<={DESK_PROP_REGION['z'][1]};
  const bool InChair=L.X>={CHAIR_ZONE['x'][0]}&&L.X<={CHAIR_ZONE['x'][1]}&&L.Y>={CHAIR_ZONE['y'][0]}&&L.Y<={CHAIR_ZONE['y'][1]}&&L.Z>={CHAIR_ZONE['z'][0]}&&L.Z<={CHAIR_ZONE['z'][1]};
  if(!InDesk&&!InChair)continue;
  FVector Origin=FVector::ZeroVector,Extent=FVector::ZeroVector;A->GetActorBounds(false,Origin,Extent);
  const FString Mesh=SMC->GetStaticMesh()?SMC->GetStaticMesh()->GetName():FString(TEXT("none")),Name=A->GetName();
  const bool Named=Name.Contains(TEXT("mouse"))||Name.Contains(TEXT("keyboard"))||Mesh.Contains(TEXT("mouse"))||Mesh.Contains(TEXT("keyboard"));
  const bool DeskProp=InDesk&&Extent.X<={DESK_PROP_MAX_EXTENT[0]}&&Extent.Y<={DESK_PROP_MAX_EXTENT[1]}&&Extent.Z<={DESK_PROP_MAX_EXTENT[2]}&&(Mesh.StartsWith(TEXT("{DESK_PROP_MESH_PREFIX}"))||Named);
  const bool ChairPart=!DeskProp&&InChair&&Extent.X<={CHAIR_MAX_EXTENT[0]}&&Extent.Y<={CHAIR_MAX_EXTENT[1]}&&Extent.Z<={CHAIR_MAX_EXTENT[2]}&&!Mesh.StartsWith(TEXT("{DESK_MESH_PREFIX}"))&&!Mesh.StartsWith(TEXT("{DESK_PROP_MESH_PREFIX}"));
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_%s_CANDIDATE actor=%s class=%s mesh=%s location=%s extent=%s follows=%d"),InChair&&!InDesk?TEXT("CHAIR"):TEXT("DESK_PROP"),*Name,*A->GetClass()->GetName(),*Mesh,*L.ToString(),*Extent.ToString(),DeskProp||ChairPart?1:0);
  if(!DeskProp&&!ChairPart)continue;StreamerVisualDeskProps.Add(A);StreamerVisualDeskPropOrigins.Add(L);
  if(ChairPart){{if(ChairCount<8){{if(ChairCount)Chair+=TEXT(",");Chair+=Name;}}++ChairCount;}}else{{if(Count<8){{if(Count)Found+=TEXT(",");Found+=Name;}}++Count;}}
 }}
 StreamerVisualChairParts=ChairCount;
 UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_DESK_PROPS found=%d [%s] chairParts=%d [%s] (keyboard pack / mouse in front of the chair, chair-sized static meshes around the pelvis; 0 = nothing to move)"),Count,*Found,ChairCount,*Chair);
}}
void ASub01HomeCharacter::ApplyStreamerVisualDeskProps(const FVector& WorldDelta){{
 if(!StreamerVisualDeskPropsScanned){{if(WorldDelta.IsNearlyZero())return;ScanStreamerVisualDeskProps();}}
 if(WorldDelta.Equals(StreamerVisualDeskPropDelta,.01))return;StreamerVisualDeskPropDelta=WorldDelta;int32 Moved=0;
 for(int32 I=0;I<StreamerVisualDeskProps.Num();++I){{AActor* A=StreamerVisualDeskProps[I].Get();if(!A||!StreamerVisualDeskPropOrigins.IsValidIndex(I))continue;A->SetActorLocation(StreamerVisualDeskPropOrigins[I]+WorldDelta,false,nullptr,ETeleportType::TeleportPhysics);++Moved;}}
 StreamerVisualDeskPropsMoved=Moved;UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_DESK_PROPS moved=%d delta=%s"),Moved,*WorldDelta.ToString());
}}
// SUB01_STREAMER_VISUAL_V2_SEATFIX END
'''

START_LINE = ' StreamerVisualStartedAt=FPlatformTime::Seconds();StreamerVisualSpectatorLook=SpectatorLook;StreamerVisualActiveClip=StreamerVisualClip;StreamerVisualCameraAlpha=0;\n'
START_SEAT = (START_LINE +
              ' // SUB01_STREAMER_VISUAL_V2_SEATFIX: the authored body transform is the seat; the clips\' station offset goes on the mesh component (ApplyStreamerVisualV2)\n'
              ' // and the root no longer follows the camera look (SetControlRotation turned the body on every camera switch while bUseControllerRotationYaw held).\n'
              ' StreamerVisualBodyRelative=FirstPersonBody?FirstPersonBody->GetRelativeTransform():FTransform::Identity;StreamerVisualBodyRelativeValid=!!FirstPersonBody;StreamerVisualSeatApplied=FTransform::Identity;StreamerVisualSeatHas=false;\n'
              ' StreamerVisualControllerYawWas=bUseControllerRotationYaw;bUseControllerRotationYaw=false;StreamerVisualBodyAuthoredWorld=FirstPersonBody?FirstPersonBody->GetComponentTransform():FTransform::Identity;StreamerVisualDeskPropsScanned=false;StreamerVisualDeskPropDelta=FVector::ZeroVector;\n'
              f' if(FirstPersonBody){{FirstPersonBody->BoundsScale={BOUNDS_SCALE:g}.f;FirstPersonBody->UpdateBounds();}} // the loops pose ~1.2 m from the offset component origin: the fixed ref-pose bounds would be frustum-culled by the face camera\n'
              f' UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_SEAT_FIX_READY bodyRelative=%s bodyWorld=%s controllerYawWas=%d boundsScale={BOUNDS_SCALE:g} bounds=%s"),*StreamerVisualBodyRelative.ToString(),FirstPersonBody?*FirstPersonBody->GetComponentTransform().ToString():TEXT("none"),StreamerVisualControllerYawWas?1:0,FirstPersonBody?*FirstPersonBody->Bounds.ToString():TEXT("none"));\n')
MONITOR_COMMENT = ' // Monitor framing from the body\'s own basis: the facing is the body axis (+-X/+-Y; imported meshes face +Y) that points at\n'
FACE_RIG = (''' if(BodyMesh){ // SUB01_STREAMER_VISUAL_V2_SEATFIX: what the skeleton offers for mouth movement (report only; nothing here drives a face)
  const FReferenceSkeleton& RefSkel=BodyMesh->GetRefSkeleton();FString FaceBones;int32 FaceCount=0;
  for(int32 B=0;B<RefSkel.GetNum();++B){const FString Name=RefSkel.GetBoneName(B).ToString();
   if(Name.Contains(TEXT("jaw"))||Name.Contains(TEXT("mouth"))||Name.Contains(TEXT("lip"))||Name.Contains(TEXT("tongue"))||Name.Contains(TEXT("teeth"))||Name.Contains(TEXT("eye"))||Name.Contains(TEXT("brow"))||Name.Contains(TEXT("cheek"))||Name.Contains(TEXT("head"))||Name.Contains(TEXT("neck"))||Name.Contains(TEXT("face"))){if(FaceCount<48){if(FaceCount)FaceBones+=TEXT(",");FaceBones+=Name;}++FaceCount;}}
  FString Morphs;int32 MorphCount=0;for(const auto& Morph:BodyMesh->GetMorphTargets()){if(!Morph)continue;if(MorphCount<48){if(MorphCount)Morphs+=TEXT(",");Morphs+=Morph->GetName();}++MorphCount;}
  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_FACE_RIG bones=%d faceOrHeadBones=%d [%s] morphTargets=%d [%s]"),RefSkel.GetNum(),FaceCount,*FaceBones,MorphCount,*Morphs);
 }
''' + MONITOR_COMMENT)
FACE_READY_LINE = (' UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_FACE_READY location=%s fov=' + f'{face.FACE_FOV:g}' +
                   '"),*StreamerVisualFaceLocation.ToString()); // SUB01_STREAMER_VISUAL_V2_FACE\n')
FACE_READY_SEAT = (' StreamerVisualFacingLocal=FVector(Chosen==0?1:Chosen==1?-1:0,Chosen==2?1:Chosen==3?-1:0,0);StreamerVisualRightLocal=FVector::CrossProduct(FVector::UpVector,StreamerVisualFacingLocal); // SUB01_STREAMER_VISUAL_V2_SEATFIX: the facing in component space (pull-back axis), his right\n'
                   ' UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_FACE_READY webcam on the monitor aimed at the measured Head bone: upCm=%.1f forwardCm=%.1f sideCm=%.1f aimDropCm=%.1f fov=%.1f (placeholder location=%s until aimed)"),'
                   'StreamerVisualFaceUpCm,StreamerVisualFaceForwardCm,StreamerVisualFaceSideCm,StreamerVisualFaceAimDropCm,StreamerVisualFaceFov,*StreamerVisualFaceLocation.ToString()); // SUB01_STREAMER_VISUAL_V2_FACE; SUB01_STREAMER_VISUAL_V2_SEATFIX\n')
CAMERA_COMMENT = ' // Camera: "spectator" = the authored v1 view, untouched while it holds; "monitor" = over-the-shoulder framing, 1 s eased blend.\n'
APPLY_SEAT = (f''' {{ // SUB01_STREAMER_VISUAL_V2_SEATFIX: the mesh component carries the playing clip's seat offset (component space, blended by the proxy with
  // the crossfade weight): the clip's reference pelvis lands where R9's did on the authored transform while the clip plays untouched.
  // The pull-back knob (tuning file) adds a constant translation away from the monitor along the body facing; keyboard/mouse props follow.
  if(StreamerVisualSchemaVersion==2&&Now>=StreamerVisualFaceTuningAt){{StreamerVisualFaceTuningAt=Now+.5;if(ReadStreamerVisualFaceTuning())StreamerVisualTuningChanged=true;}}
  if(StreamerVisualSeatBackCm!=StreamerVisualSeatBackApplied||StreamerVisualSeatSideCm!=StreamerVisualSeatSideApplied){{StreamerVisualSeatBackApplied=StreamerVisualSeatBackCm;StreamerVisualSeatSideApplied=StreamerVisualSeatSideCm;
   UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_SEAT_BACK cm=%.1f sideCm=%.1f facingLocal=%s rightLocal=%s (away from the monitor; small desk props follow)"),StreamerVisualSeatBackCm,StreamerVisualSeatSideCm,*StreamerVisualFacingLocal.ToString(),*StreamerVisualRightLocal.ToString());}}
  const FVector PullLocal=StreamerVisualFacingLocal*double(-StreamerVisualSeatBackCm)+StreamerVisualRightLocal*double(StreamerVisualSeatSideCm);
  FTransform Seat=FTransform::Identity;const bool SeatValid=StreamerVisualSchemaVersion==2&&Anim&&Anim->StreamerVisualSeatOffsetValid;if(SeatValid)Seat=Anim->StreamerVisualSeatOffset*FTransform(FQuat::Identity,PullLocal);
  if(FirstPersonBody&&StreamerVisualBodyRelativeValid&&(SeatValid||StreamerVisualSeatHas)){{
   if(!Seat.Equals(StreamerVisualSeatApplied,{SEAT_EPSILON:g})){{StreamerVisualSeatApplied=Seat;FirstPersonBody->SetRelativeTransform(Seat*StreamerVisualBodyRelative,false,nullptr,ETeleportType::TeleportPhysics);}}
   StreamerVisualSeatHas=SeatValid;
  }}
  ApplyStreamerVisualDeskProps(SeatValid&&StreamerVisualDeskPropsEnabled>0?StreamerVisualBodyAuthoredWorld.GetRotation().RotateVector(PullLocal):FVector::ZeroVector);
 }}
''' + CAMERA_COMMENT)

_start = face.CPP_METHODS.index('void ASub01HomeCharacter::ApplyStreamerVisualFaceCamera(float Dt){')
OLD_FACE_CAMERA = face.CPP_METHODS[_start:face.CPP_METHODS.index('int32 ASub01HomeCharacter::StreamerVisualDeskSlot(')]
NEW_FACE_CAMERA = f'''void ASub01HomeCharacter::ApplyStreamerVisualFaceCamera(float Dt){{
 // SUB01_STREAMER_VISUAL_V2_SEATFIX (tools/native_streamer_visual_v2/install_seat_fix.py): "face" = the stream's webcam ON the monitor:
 // monitor bounds centre + {FACE_UP_CM:g} cm up, {FACE_FORWARD_CM:g} cm towards him, {FACE_SIDE_CM:g} cm to his right (a fixed point), aimed at the MEASURED Head bone
 // (mean over {FACE_SAMPLE_SECONDS:g} s: the loops sway the head ~5 cm) minus {FACE_AIM_DROP_CM:g} cm, FOV {FACE_FOV:g}: face and shoulders centred, the room behind him.
 // Aimed once per selection after the seat offset has settled (else after 2 s), again when the private tuning file's sequence
 // grows. A separate 1 s eased layer over the spectator/monitor blend above, which keeps running unchanged underneath.
 const double Now=FPlatformTime::Seconds();const bool Face=StreamerVisualCameraTarget==TEXT("face");
 if(Face&&StreamerVisualFaceSelectedAt<0)StreamerVisualFaceSelectedAt=Now;
 if(StreamerVisualTuningChanged){{StreamerVisualTuningChanged=false;if(Face){{StreamerVisualFaceAimed=false;StreamerVisualFaceHeadCount=0;}}}} // re-aim on a tuning change (polled in ApplyStreamerVisualV2)
 auto* SeatAnim=FirstPersonBody?Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()):nullptr;
 const bool Settled=StreamerVisualSchemaVersion!=2||(SeatAnim&&SeatAnim->StreamerVisualSeatSettled&&StreamerVisualSeatHas&&StreamerVisualSeatApplied.Equals(SeatAnim->StreamerVisualSeatOffset,{SEAT_EPSILON:g}));
 if(Face&&!StreamerVisualFaceAimed&&(Settled||Now-StreamerVisualFaceSelectedAt>=2)){{
  const FVector BodyAt=FirstPersonBody?FirstPersonBody->GetComponentLocation():FVector(214,-289,6.19);
  const bool HasHead=FirstPersonBody&&FirstPersonBody->GetBoneIndex(TEXT("Head"))!=INDEX_NONE;
  FVector Head=HasHead?FirstPersonBody->GetBoneLocation(TEXT("Head")):FVector::ZeroVector;const bool HeadOk=HasHead&&!Head.ContainsNaN()&&FVector::Dist(Head,BodyAt)<=250;
  if(!HeadOk)Head=BodyAt+FVector(0,0,120);
  if(StreamerVisualFaceHeadCount<=0){{StreamerVisualFaceHeadSum=FVector::ZeroVector;StreamerVisualFaceHeadCount=0;StreamerVisualFaceSampleAt=Now;}}
  StreamerVisualFaceHeadSum=StreamerVisualFaceHeadSum+Head;++StreamerVisualFaceHeadCount;
  if(!HeadOk||Now-StreamerVisualFaceSampleAt>={FACE_SAMPLE_SECONDS:g}){{
   const FVector Mean=StreamerVisualFaceHeadSum*(1./StreamerVisualFaceHeadCount);StreamerVisualFaceAimSource=HeadOk?TEXT("head"):TEXT("body+120");
   const FVector Monitor({MONITOR[0]},{MONITOR[1]},{MONITOR[2]});FVector Towards(Mean.X-Monitor.X,Mean.Y-Monitor.Y,0); // from the monitor towards him
   Towards=Towards.Size()>10?Towards.GetSafeNormal():FVector(0,1,0);const FVector Side=FVector::CrossProduct(FVector::UpVector,-Towards); // UE is left-handed: Up x (his facing) = his right
   StreamerVisualFaceLocation=Monitor+Towards*double(StreamerVisualFaceForwardCm)+Side*double(StreamerVisualFaceSideCm)+FVector(0,0,StreamerVisualFaceUpCm);
   StreamerVisualFaceAim=Mean-FVector(0,0,StreamerVisualFaceAimDropCm);
   StreamerVisualFaceLook=(StreamerVisualFaceAim-StreamerVisualFaceLocation).Rotation();StreamerVisualFaceAimed=true;
   UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_FACE_CAMERA location=%s aim=%s headMean=%s samples=%d source=%s look=%s fov=%.1f upCm=%.1f forwardCm=%.1f sideCm=%.1f aimDropCm=%.1f tuningSequence=%.0f settled=%d"),*StreamerVisualFaceLocation.ToString(),*StreamerVisualFaceAim.ToString(),*Mean.ToString(),StreamerVisualFaceHeadCount,*StreamerVisualFaceAimSource,*StreamerVisualFaceLook.ToString(),StreamerVisualFaceFov,StreamerVisualFaceUpCm,StreamerVisualFaceForwardCm,StreamerVisualFaceSideCm,StreamerVisualFaceAimDropCm,StreamerVisualFaceTuningSequence,Settled?1:0);
   StreamerVisualFaceHeadCount=0;
  }}
 }}
 if(!Face){{StreamerVisualFaceAimed=false;StreamerVisualFaceSelectedAt=-10;StreamerVisualFaceHeadCount=0;}}
 const float Goal=Face?1.f:0.f;
 if(!ViewCamera||(Goal==0&&StreamerVisualFaceAlpha<=0))return; // spectator/monitor only: the v2 camera path alone, untouched
 if(Face&&!StreamerVisualFaceAimed)return; // waiting for the seat offset / sampling the head: the camera stays as the blend above left it this tick
 StreamerVisualFaceAlpha=Goal>StreamerVisualFaceAlpha?FMath::Min(Goal,StreamerVisualFaceAlpha+Dt):FMath::Max(Goal,StreamerVisualFaceAlpha-Dt);
 if(StreamerVisualFaceAlpha<=0){{ // fade-out done: FOV back to 65; exact spectator pose when the base rests there (else the v2 block set it this tick)
  ViewCamera->SetFieldOfView(65.f);
  if(StreamerVisualCameraAlpha<=0){{ViewCamera->SetWorldLocationAndRotation(FVector(334,-209,151),StreamerVisualSpectatorLook);if(Controller)Controller->SetControlRotation(StreamerVisualSpectatorLook);}}
  return;
 }}
 const float Base=FMath::SmoothStep(0.f,1.f,StreamerVisualCameraAlpha),Ease=FMath::SmoothStep(0.f,1.f,StreamerVisualFaceAlpha);
 const FVector Under=FMath::Lerp(FVector(334,-209,151),StreamerVisualMonitorLocation,double(Base));
 const FQuat UnderQ=FQuat::Slerp(StreamerVisualSpectatorLook.Quaternion(),StreamerVisualMonitorLook.Quaternion(),double(Base));
 const FRotator Rotation=FQuat::Slerp(UnderQ,StreamerVisualFaceLook.Quaternion(),double(Ease)).Rotator();
 ViewCamera->SetWorldLocationAndRotation(FMath::Lerp(Under,StreamerVisualFaceLocation,double(Ease)),Rotation);ViewCamera->SetFieldOfView(FMath::Lerp(65.f,StreamerVisualFaceFov,Ease));
 if(Controller)Controller->SetControlRotation(Rotation);
}}
'''
RECEIPT_FACE_TAIL = 'Receipt->SetBoolField(TEXT("clip_audit_done"),V2Anim&&V2Anim->StreamerVisualAuditDone);} // SUB01_STREAMER_VISUAL_V2_FACE\n'
RECEIPT_SEAT = ('Receipt->SetBoolField(TEXT("clip_audit_done"),V2Anim&&V2Anim->StreamerVisualAuditDone); // SUB01_STREAMER_VISUAL_V2_FACE\n'
                '   Receipt->SetStringField(TEXT("seat_offset"),StreamerVisualSeatApplied.ToString());Receipt->SetNumberField(TEXT("seat_offset_cm"),StreamerVisualSeatApplied.GetTranslation().Size());Receipt->SetNumberField(TEXT("seat_offset_yaw_deg"),StreamerVisualSeatApplied.Rotator().Yaw);'
                'Receipt->SetBoolField(TEXT("seat_offset_applied"),StreamerVisualSeatHas);Receipt->SetBoolField(TEXT("seat_offset_settled"),V2Anim&&V2Anim->StreamerVisualSeatSettled); // SUB01_STREAMER_VISUAL_V2_SEATFIX\n'
                '   Receipt->SetStringField(TEXT("pelvis_world"),V2Anim&&V2Anim->StreamerVisualPelvisBone>=0?FirstPersonBody->GetBoneTransform(V2Anim->StreamerVisualPelvisBone).GetTranslation().ToString():FString());'
                'Receipt->SetStringField(TEXT("head_world"),FirstPersonBody->GetBoneIndex(TEXT("Head"))!=INDEX_NONE?FirstPersonBody->GetBoneLocation(TEXT("Head")).ToString():FString());\n'
                '   Receipt->SetStringField(TEXT("face_camera_location"),StreamerVisualFaceLocation.ToString());Receipt->SetStringField(TEXT("face_camera_aim"),StreamerVisualFaceAim.ToString());Receipt->SetNumberField(TEXT("face_camera_tuning_sequence"),StreamerVisualFaceTuningSequence);'
                'Receipt->SetStringField(TEXT("camera_world"),ViewCamera->GetComponentTransform().ToString());Receipt->SetStringField(TEXT("body_bounds"),FirstPersonBody->Bounds.ToString());\n'
                '   Receipt->SetNumberField(TEXT("seat_back_cm"),StreamerVisualSeatBackApplied);Receipt->SetNumberField(TEXT("seat_side_cm"),StreamerVisualSeatSideApplied);Receipt->SetNumberField(TEXT("desk_props_moved"),StreamerVisualDeskPropsMoved);Receipt->SetStringField(TEXT("desk_props_delta"),StreamerVisualDeskPropDelta.ToString());Receipt->SetNumberField(TEXT("chair_parts"),StreamerVisualChairParts);\n'
                '   Receipt->SetNumberField(TEXT("posture_lean_deg"),StreamerVisualPostureLeanApplied);Receipt->SetNumberField(TEXT("posture_head_deg"),StreamerVisualPostureHeadApplied);} // SUB01_STREAMER_VISUAL_V2_SEATFIX\n')

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.h
HANDS_FACE_BEGIN = _line(face.HANDS_FIELDS, ' // SUB01_STREAMER_VISUAL_V2_FACE BEGIN')
HANDS_FIELDS = ''' // SUB01_STREAMER_VISUAL_V2_SEATFIX BEGIN (tools/native_streamer_visual_v2/install_seat_fix.py): published after evaluation.
 UPROPERTY(Transient) FTransform StreamerVisualSeatOffset; // component space: the playing clip's reference pelvis onto R9's (crossfade-blended)
 UPROPERTY(Transient) bool StreamerVisualSeatOffsetValid=false;
 UPROPERTY(Transient) bool StreamerVisualSeatSettled=false; // no crossfade in progress
 UPROPERTY(Transient) int32 StreamerVisualPelvisBone=-1;
 // SUB01_STREAMER_VISUAL_V2_SEATFIX END
'''

# ------------------------------------------------------------------------------------------------ Sub01HomeHands.cpp
PROXY_FACE_BEGIN = _line(pinfix.NEW_PROXY, ' // SUB01_STREAMER_VISUAL_V2_FACE BEGIN')
PROXY_MEMBERS = ''' // SUB01_STREAMER_VISUAL_V2_SEATFIX BEGIN (tools/native_streamer_visual_v2/install_seat_fix.py): per-clip seat offset in component space.
 // D with clipPelvis * D = R9Pelvis: translation exact, rotation = the yaw twist of R9 * clip^-1 (the clip's own pelvis tilt stays).
 FTransform StreamerV2Seat=FTransform::Identity;bool StreamerV2SeatValid=false,StreamerV2SeatSettled=false;
 static FQuat StreamerV2YawTwist(const FQuat& Q){const FQuat T(0,0,Q.Z,Q.W);return FMath::Abs(Q.Z)+FMath::Abs(Q.W)>1e-6?T.GetNormalized():FQuat::Identity;}
 static FTransform StreamerV2SeatFor(const FTransform& R9,const FTransform& Clip){
  const FQuat Twist=StreamerV2YawTwist(R9.GetRotation()*Clip.GetRotation().Inverse());
  return FTransform(Twist,R9.GetTranslation()-Twist.RotateVector(Clip.GetTranslation()));
 }
 void PublishStreamerV2Seat(){ // this frame's offset: the Current clip's, blended from the Previous clip's with the crossfade weight; the frozen R9 gives the identity
  StreamerV2SeatValid=false;StreamerV2SeatSettled=false;StreamerV2Seat=FTransform::Identity;if(!StreamerV2PinReady)return;
  const FStreamerV2ClipRef* To=StreamerV2ClipRef(Current.GetSequence());if(!To||!To->SeatValid)return;
  const FStreamerV2ClipRef* From=Progress>=1?nullptr:StreamerV2ClipRef(Previous.GetSequence());
  StreamerV2Seat=To->Seat;if(From&&From->SeatValid)StreamerV2Seat.Blend(From->Seat,To->Seat,Progress);
  StreamerV2SeatValid=true;StreamerV2SeatSettled=Progress>=1;
 }
 // SUB01_STREAMER_VISUAL_V2_SEATFIX END
'''
CLIP_REF_STRUCT = _line(pinfix.NEW_PROXY, ' struct FStreamerV2ClipRef{')
CLIP_REF_SEAT = (' struct FStreamerV2ClipRef{const UAnimSequenceBase* Key=nullptr;TArray<FTransform> Locals;FTransform Seat=FTransform::Identity;bool SeatValid=false;};'
                 'FStreamerV2ClipRef StreamerV2ClipRefs[6];int32 StreamerV2ClipRefNext=0; // SUB01_STREAMER_VISUAL_V2_SEATFIX: Seat per clip\n')
REF_PELVIS = ('  FTransform Pelvis=FTransform::Identity;StreamerV2Pelvis(Probe.Pose,Pelvis);\n'
              '  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_DRIFT_REFERENCE at=%.2fs pelvis=%s"),At,*Pelvis.GetTranslation().ToString());\n')
REF_PELVIS_SEAT = ('  FTransform Pelvis=FTransform::Identity;const bool PelvisValid=StreamerV2Pelvis(Probe.Pose,Pelvis); // SUB01_STREAMER_VISUAL_V2_SEATFIX\n'
                   '  UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_DRIFT_REFERENCE at=%.2fs pelvis=%s"),At,*Pelvis.GetTranslation().ToString());\n'
                   '  if(PelvisValid){Entry.Seat=StreamerV2SeatFor(StreamerV2PinPelvis,Pelvis);Entry.SeatValid=true; // SUB01_STREAMER_VISUAL_V2_SEATFIX: once per clip\n'
                   '   UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_SEAT_OFFSET clip=%s at=%.2fs offsetCm=%.1f yawDeg=%.1f offset=%s r9Pelvis=%s"),*Seq->GetPathName(),At,Entry.Seat.GetTranslation().Size(),Entry.Seat.Rotator().Yaw,*Entry.Seat.ToString(),*StreamerV2PinPelvis.GetTranslation().ToString());}\n')
EVAL_PIN = '  PinStreamerV2(Output.Pose,true); // SUB01_STREAMER_VISUAL_V2_FACE: desk pin before hands, breathing and head\n'
PUBLISH_FACE = (' if(Proxy.StreamerV2Audited&&!StreamerVisualAuditDone){StreamerVisualClipOffsetCm=Proxy.StreamerV2AuditOffsetCm;StreamerVisualClipAngleDeg=Proxy.StreamerV2AuditAngleDeg;StreamerVisualAuditDone=true;}'
                'StreamerVisualDeskOffsetCm=Proxy.StreamerV2LastPinCm; // SUB01_STREAMER_VISUAL_V2_FACE\n')

SPINE_LINE = '  Anim->StreamerVisualSpine1Offset=FRotator(.6*FMath::Sin(W),0,0);Anim->StreamerVisualSpine2Offset=FRotator(.6*FMath::Sin(W-1.1),0,0);\n'
SPINE_POSTURE = (f'''  // SUB01_STREAMER_VISUAL_V2_SEATFIX: "sit up" posture layer from the tuning file, eased at {POSTURE_RATE_DEG_PER_S:g} deg/s: the lean split over Spine1/Spine2
  // (the breathing axis), the head pitch on the gaze axis (composed with the gaze/nod offset set by the tick above).
  StreamerVisualPostureLeanApplied+=FMath::Clamp(StreamerVisualPostureLeanDeg-StreamerVisualPostureLeanApplied,-{POSTURE_RATE_DEG_PER_S:g}.f*Dt,{POSTURE_RATE_DEG_PER_S:g}.f*Dt);StreamerVisualPostureHeadApplied+=FMath::Clamp(StreamerVisualPostureHeadDeg-StreamerVisualPostureHeadApplied,-{POSTURE_RATE_DEG_PER_S:g}.f*Dt,{POSTURE_RATE_DEG_PER_S:g}.f*Dt);
  if(StreamerVisualPostureLeanDeg!=StreamerVisualPostureLeanLogged||StreamerVisualPostureHeadDeg!=StreamerVisualPostureHeadLogged){{StreamerVisualPostureLeanLogged=StreamerVisualPostureLeanDeg;StreamerVisualPostureHeadLogged=StreamerVisualPostureHeadDeg;UE_LOG(LogTemp,Display,TEXT("SUB01_STREAMER_VISUAL_POSTURE leanDeg=%.1f (Spine1+Spine2 pitch, half each) headDeg=%.1f (Head pitch)"),StreamerVisualPostureLeanDeg,StreamerVisualPostureHeadDeg);}}
  Anim->StreamerVisualSpine1Offset=FRotator(.6*FMath::Sin(W)+StreamerVisualPostureLeanApplied*.5,0,0);Anim->StreamerVisualSpine2Offset=FRotator(.6*FMath::Sin(W-1.1)+StreamerVisualPostureLeanApplied*.5,0,0);Anim->StreamerVisualHeadOffset.Pitch+=StreamerVisualPostureHeadApplied;
''')

EDITS = [
    ('header', HEADER_FACE_BEGIN, HEADER_FIELDS + HEADER_FACE_BEGIN),
    ('cpp', SPINE_LINE, SPINE_POSTURE),
    ('cpp', CPP_FACE_BEGIN, CPP_HELPERS + CPP_FACE_BEGIN),
    ('cpp', START_LINE, START_SEAT),
    ('cpp', MONITOR_COMMENT, FACE_RIG),
    ('cpp', FACE_READY_LINE, FACE_READY_SEAT),
    ('cpp', CAMERA_COMMENT, APPLY_SEAT),
    ('cpp', OLD_FACE_CAMERA, NEW_FACE_CAMERA),
    ('cpp', RECEIPT_FACE_TAIL, RECEIPT_SEAT),
    ('hands_header', HANDS_FACE_BEGIN, HANDS_FIELDS + HANDS_FACE_BEGIN),
    ('hands_cpp', PROXY_FACE_BEGIN, PROXY_MEMBERS + PROXY_FACE_BEGIN),
    ('hands_cpp', CLIP_REF_STRUCT, CLIP_REF_SEAT),
    ('hands_cpp', REF_PELVIS, REF_PELVIS_SEAT),
    ('hands_cpp', EVAL_PIN, '  PublishStreamerV2Seat(); // SUB01_STREAMER_VISUAL_V2_SEATFIX: this frame\'s component-space seat offset for the character\n' + EVAL_PIN),
    ('hands_cpp', PUBLISH_FACE, PUBLISH_FACE +
     ' StreamerVisualSeatOffset=Proxy.StreamerV2Seat;StreamerVisualSeatOffsetValid=Proxy.StreamerV2SeatValid;StreamerVisualSeatSettled=Proxy.StreamerV2SeatSettled;'
     'StreamerVisualPelvisBone=Proxy.StreamerV2PinChain.Num()?Proxy.StreamerV2PinChain[0]:-1; // SUB01_STREAMER_VISUAL_V2_SEATFIX\n'),
]


def plan(sources: dict) -> dict:
    """Pure transformation of the four LF texts; raises Refused, never partial."""
    problems = [f'{FILES[key]} already carries {MARKER} (seat fix already installed)' for key in FILES if MARKER in sources[key]]
    if problems:
        raise Refused('; '.join(problems))
    problems = [f'{FILES[key]} lacks the no-pin patch ({nopin.MARKER}); run install.py, install_face_camera.py, install_pin_fix.py and install_no_pin.py first'
                for key in ('hands_cpp',) if nopin.MARKER not in sources[key]]
    problems += [f'{FILES[key]} lacks the face patch ({face.MARKER})' for key in FILES if face.MARKER + ' BEGIN' not in sources[key]]
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
    report = {'schema': 'sub01.native-streamer-visual-v2-seatfix-install.v1', 'source': str(source), 'dry_run': dry_run,
              'marker': MARKER, 'requires': [nopin.MARKER, pinfix.MARKER, face.MARKER, v2.MARKER],
              'seat': {'where': 'mesh component relative transform = D * authored relative (bones untouched)',
                       'd': 'clipPelvis(reference) * D = R9Pelvis@0.7 s: translation exact, rotation = yaw twist of R9 * clip^-1',
                       'crossfade': "D blended from the previous clip's D with the players' weight", 'epsilon': SEAT_EPSILON,
                       'controller_yaw': 'bUseControllerRotationYaw=false at v2 start (camera looks no longer turn the root)'},
              'bounds_scale': BOUNDS_SCALE,
              'posture': {'lean_deg': POSTURE_LEAN_DEG, 'head_deg': POSTURE_HEAD_DEG, 'rate_deg_per_s': POSTURE_RATE_DEG_PER_S,
                          'tuning_keys': ['posture_lean_deg', 'posture_head_deg'], 'where': 'Spine1+Spine2 pitch (half each) and Head pitch, local, eased'},
              'chair': {'zone': CHAIR_ZONE, 'max_half_extent': list(CHAIR_MAX_EXTENT), 'never': DESK_MESH_PREFIX + '_*, larger meshes'},
              'pull_back': {'seat_back_cm': SEAT_BACK_CM, 'seat_side_cm': SEAT_SIDE_CM, 'tuning_keys': ['seat_back_cm', 'seat_side_cm', 'desk_props'],
                            'desk_props': f'small {DESK_PROP_MESH_PREFIX}* actors (the keyboard pack) and actors named mouse/keyboard in the zone follow (logged), the rest never moves',
                            'region': DESK_PROP_REGION, 'max_half_extent': list(DESK_PROP_MAX_EXTENT), 'mesh_prefix': DESK_PROP_MESH_PREFIX},
              'face': {'location': 'monitor bounds centre + up, towards him (the mean head), to his right', 'monitor': list(MONITOR),
                       'aim': f'mean Head bone over {FACE_SAMPLE_SECONDS:g} s (else body + 120) minus aim_drop_cm',
                       'up_cm': FACE_UP_CM, 'forward_cm': FACE_FORWARD_CM, 'side_cm': FACE_SIDE_CM, 'aim_drop_cm': FACE_AIM_DROP_CM,
                       'fov': FACE_FOV, 'aimed': 'once per selection after the seat offset settled (else 2 s)',
                       'tuning_file': TUNING_PATH, 'tuning_schema': TUNING_SCHEMA, 'tuning_limits': TUNING_LIMITS},
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
    parser.add_argument('--source', type=Path, required=True, help='directory with the v2+face+pinfix+nopin pod files (patched in place)')
    parser.add_argument('--dry-run', action='store_true', help='check every anchor and print the report; write nothing')
    args = parser.parse_args(argv)
    try:
        report = run(args.source, args.dry_run)
    except Refused as error:
        print(json.dumps({'schema': 'sub01.native-streamer-visual-v2-seatfix-install.v1', 'source': str(args.source),
                          'dry_run': args.dry_run, 'status': 'refused', 'reason': str(error)}, indent=2))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
