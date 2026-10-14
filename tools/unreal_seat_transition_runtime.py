"""Native seat transition adapter: evidence builder, C++ integration and install hooks.

Owns tools/native_seating/Sub01SeatTransition.h and this file only. Nothing here is
staged by default: the runtime owner applies `install()` to the staged sources after the
renderer's measured chair/body report exists. Until then the live home is unchanged.

Python side (runs anywhere): build the quantitative evidence file the native side reads,
from the accepted reports written on the server:
    private-audit/native-chair-surface.json   (tools/unreal_chair_surface_audit.py)
    private-audit/native-seat-contact.json    (tools/unreal_audit_seat_contact.py)
  ->  private-audit/native-seat-evidence.json

    python tools/unreal_seat_transition_runtime.py <UE project dir>

Native side: the character feeds FSub01SeatTransition every live tick from its real
state (command, freshness, privacy, blocked route, capsule position/heading, bound clip
roles, playing clip and time, live mesh transform) and applies the outputs. It walks only
by CharacterMovement input, turns in place, stops while seat clips play, never sets an
actor location, and sets NativeSeatVerified only from ContactVerified (a quantitative,
pose-matched receipt while typing).
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_unreal_seat_contact as seat_contact  # noqa: E402

HEADER_FILE = Path(__file__).resolve().parent / 'native_seating' / 'Sub01SeatTransition.h'
OWNER_MESH = '/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'
TYPING_CLIP = '/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping'
SEAT_CLIP_DIR = '/Game/Sub01Hands/Seating'           # tools/unreal_import_seating_fbx.py
SEAT_ROLES = ('StandToSit', 'Sitting', 'SitToType', 'SitToStand')
PATCHES = ('buttocks', 'left_posterior_thigh', 'right_posterior_thigh', 'left_sole', 'right_sole')


def seat_id(text: str) -> int:
    """FNV-1a over the low byte of each character, identical to Sub01SeatId()."""
    value = 1469598103934665603
    for char in text:
        value ^= ord(char) & 0xFF
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def build_evidence(seat_report: dict, chair_text: str, mesh: str = OWNER_MESH, clip: str = TYPING_CLIP) -> dict:
    """Reduce an ACCEPTED seat contact report to the numbers the native receipt checks.

    Refuses (ValueError) unless validate_unreal_seat_contact.validate() accepts the report:
    an out-of-band report is evidence for a correction, never for a receipt.
    """
    chair = json.loads(chair_text)
    seat_contact.cushion_triangles(chair)                 # one audited cushion, no errors
    seat_contact.validate(seat_report)
    samples = seat_contact.regions_by_sample(seat_report)
    worst = {}
    for name in PATCHES:
        rows = [regions[name] for _, regions in samples]
        worst[name] = {'min_gap_cm': min(r['minGapCm'] for r in rows),
                       'max_median_cm': max(r['p50GapCm'] for r in rows),
                       'min_coverage': min(r['bandVertices'] / r['overSurfaceVertices'] for r in rows)}
    body, yaw = seat_report['body_cm'], seat_report['body_yaw']
    # unreal_audit_seat_contact.py poses the skin at Transform(body_cm, Rotator(yaw=body_yaw)),
    # unit scale; reports that state the full transform must agree with that yaw.
    rotation = seat_report.get('body_rotation_pyr', [0.0, yaw, 0.0])
    scale = seat_report.get('body_scale_xyz', [1.0, 1.0, 1.0])
    values = [*body, *rotation, *scale]
    if (len(body) != 3 or len(rotation) != 3 or len(scale) != 3
            or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
            or min(scale) <= 0):
        raise ValueError('Audited body transform must be a finite location, pitch/yaw/roll and 3-axis scale')
    if rotation[1] != yaw:
        raise ValueError('Audited body yaw disagrees with its full rotation')
    return {'schema': 'sub01.native-seat-evidence.v1', 'family': 'DeskTyping',
            'mesh': mesh, 'clip': clip, 'mesh_id': str(seat_id(mesh)), 'clip_id': str(seat_id(clip)),
            'chair_component': chair['chair']['component'], 'chair_revision': str(seat_id(chair_text)),
            'body_cm': list(body), 'body_yaw': yaw, 'body_rotation_pyr': list(rotation), 'body_scale_xyz': list(scale),
            'time_range_s': [samples[0][0], samples[-1][0]], 'patches': worst,
            'native_seat_verified': False,
            'note': 'Evidence for a pose-matched runtime receipt only; NativeSeatVerified follows the live receipt.'}


def write_evidence(project: Path) -> Path:
    audit = Path(project) / 'private-audit'
    chair_text = (audit / 'native-chair-surface.json').read_text()
    report = json.loads((audit / 'native-seat-contact.json').read_text())
    out = audit / 'native-seat-evidence.json'
    out.write_text(json.dumps(build_evidence(report, chair_text), indent=2) + '\n')
    return out


# ---------------------------------------------------------------- native integration
CHARACTER_INCLUDE = '#include "Sub01SeatTransition.h"\n'

CHARACTER_FIELDS = r'''
 // Native seat transition (tools/unreal_seat_transition_runtime.py).
 void LoadSeatTransition(); void UpdateSeatTransition(float Dt); void ApplySeatAnimation(class USub01HomeHandsInstance* Instance);
 FSub01SeatTransition SeatMachine; FSub01SeatOutputs SeatOut; FSub01SeatEvidence SeatEvidence;
 UPROPERTY() TMap<FName,TObjectPtr<UAnimSequence>> SeatClips;
 uint32 SeatRoles=0,SeatAppliedSerial=0; uint64 SeatChairRevision=0; ESub01SeatPhase SeatLoggedPhase=ESub01SeatPhase::Standing;
 bool SeatChairMeasured=false,SeatAnchorValid=false,SeatBodyAttached=false; float SeatYaw=-90;
 FVector2D SeatApproach=FVector2D::ZeroVector;
 // Live skin measurement at the actual seated transform, the audited cushion it is measured
 // against, the bounded settle, and the transform the keyboard contact profile was audited at.
 FSub01SeatMeasurement SeatMeasurement; TArray<FVector> SeatCushionTriangles; double SeatMeasuredAt=0; int32 SeatMeasurementLogged=-1;
 float SeatSettleTravel=0; bool SeatSettleBlocked=false; bool SeatProfilePoseLoaded=false; FSub01SeatLivePose SeatProfilePose;
 bool SeatLiveBody(FSub01SeatLivePose& L) const;
'''

CHARACTER_METHODS = r'''
#include "Misc/FileHelper.h"
void ASub01HomeCharacter::LoadSeatTransition(){
 SeatRoles=0;SeatClips.Empty();SeatChairMeasured=false;SeatAnchorValid=false;SeatEvidence=FSub01SeatEvidence();
 USkeletalMesh* Mesh=FirstPersonBody?FirstPersonBody->GetSkeletalMeshAsset():nullptr;if(!Mesh)return;
 // Seat clips: the imported captures on the SAME owner skeleton, or nothing (fail closed).
 const TPair<const TCHAR*,uint32> Roles[]={{TEXT("StandToSit"),SeatRoleStandToSit},{TEXT("Sitting"),SeatRoleSitting},{TEXT("SitToType"),SeatRoleSitToType},{TEXT("SitToStand"),SeatRoleSitToStand}};
 for(const auto& Role:Roles){
  const FString Path=FString::Printf(TEXT("%s/SUB01_%s.SUB01_%s"),TEXT("@@SEAT_CLIP_DIR@@"),Role.Key,Role.Key);
  auto* Clip=LoadObject<UAnimSequence>(nullptr,*Path);
  if(Clip&&Clip->GetSkeleton()==Mesh->GetSkeleton()){SeatClips.Add(FName(Role.Key),Clip);SeatRoles|=Role.Value;}
  else UE_LOG(LogTemp,Warning,TEXT("SUB01_SEAT_ROLE_MISSING %s"),*Path);
 }
 if(UAnimSequence* Typing=HandsClips.FindRef(TEXT("DeskTyping"))){SeatClips.Add(TEXT("DeskTyping"),Typing);SeatRoles|=SeatRoleDeskTyping;}
 // Chair: the audited cushion report; its exact text is the chair revision.
 const FString Audit=FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit"));FString ChairText;TSharedPtr<FJsonObject> Chair;
 if(FFileHelper::LoadFileToString(ChairText,*FPaths::Combine(Audit,TEXT("native-chair-surface.json")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ChairText),Chair)&&Chair.IsValid()){
  const TArray<TSharedPtr<FJsonValue>>* Errors=nullptr;const TSharedPtr<FJsonObject>* ChairObject=nullptr;
  if(Chair->TryGetArrayField(TEXT("errors"),Errors)&&Errors->Num()==0&&Chair->TryGetObjectField(TEXT("chair"),ChairObject)){
   SeatChairRevision=Sub01SeatId(*ChairText);SeatChairMeasured=true;SeatCushionTriangles.Reset();
   // The audited cushion triangles (world cm), what a live skin measurement is made against.
   const TArray<TSharedPtr<FJsonValue>>* AllSections=nullptr;
   if((*ChairObject)->TryGetArrayField(TEXT("sections"),AllSections))for(const auto& SectionValue:*AllSections){
    const auto Section=SectionValue->AsObject();const TArray<TSharedPtr<FJsonValue>> *Vertices=nullptr,*Faces=nullptr;const TSharedPtr<FJsonObject>* Cushion=nullptr;
    if(!Section->TryGetArrayField(TEXT("vertices_world_cm"),Vertices)||!Section->TryGetObjectField(TEXT("cushion_surface"),Cushion)||!(*Cushion)->TryGetArrayField(TEXT("triangle_indices"),Faces))continue;
    for(const auto& Face:*Faces){const auto& Corners=Face->AsArray();if(Corners.Num()!=3){SeatCushionTriangles.Reset();break;}
     for(const auto& Corner:Corners){const int32 I=int32(Corner->AsNumber());if(!Vertices->IsValidIndex(I)||(*Vertices)[I]->AsArray().Num()!=3){SeatCushionTriangles.Reset();break;}
      const auto& V=(*Vertices)[I]->AsArray();SeatCushionTriangles.Add(FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber()));}}
   }
   if(SeatCushionTriangles.Num()%3)SeatCushionTriangles.Reset();
   // Approach without contact evidence: cushion centre + the captured sit's hip travel (no receipt possible).
   const TArray<TSharedPtr<FJsonValue>>* Sections=nullptr;
   if((*ChairObject)->TryGetArrayField(TEXT("sections"),Sections)&&Sections->Num()){
    const auto Bounds=(*Sections)[0]->AsObject()->GetObjectField(TEXT("cushion_surface"))->GetObjectField(TEXT("world_bounds_cm"));
    const auto& Min=Bounds->GetArrayField(TEXT("min"));const auto& Max=Bounds->GetArrayField(TEXT("max"));
    if(Min.Num()==3&&Max.Num()==3){double X=0,Y=0;Sub01SeatApproachFromCushion((Min[0]->AsNumber()+Max[0]->AsNumber())/2,(Min[1]->AsNumber()+Max[1]->AsNumber())/2,SeatYaw,X,Y);SeatApproach=FVector2D(X,Y);SeatAnchorValid=FMath::IsFinite(X)&&FMath::IsFinite(Y);}
   }
  }
 }
 // Contact evidence: only an accepted, quantitative report (build_evidence()).
 FString EvidenceText;TSharedPtr<FJsonObject> E;
 if(SeatChairMeasured&&FFileHelper::LoadFileToString(EvidenceText,*FPaths::Combine(Audit,TEXT("native-seat-evidence.json")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(EvidenceText),E)&&E.IsValid()){
  FString Family,MeshId,ClipId,ChairRevision;const TArray<TSharedPtr<FJsonValue>> *Body=nullptr,*Rotation=nullptr,*Scale=nullptr,*Range=nullptr;const TSharedPtr<FJsonObject>* Patches=nullptr;
  if(E->TryGetStringField(TEXT("family"),Family)&&Family==TEXT("DeskTyping")&&E->TryGetStringField(TEXT("mesh_id"),MeshId)&&E->TryGetStringField(TEXT("clip_id"),ClipId)
     &&E->TryGetStringField(TEXT("chair_revision"),ChairRevision)&&E->TryGetArrayField(TEXT("body_cm"),Body)&&Body->Num()==3
     &&E->TryGetArrayField(TEXT("body_rotation_pyr"),Rotation)&&Rotation->Num()==3&&E->TryGetArrayField(TEXT("body_scale_xyz"),Scale)&&Scale->Num()==3
     &&E->TryGetArrayField(TEXT("time_range_s"),Range)&&Range->Num()==2&&E->TryGetObjectField(TEXT("patches"),Patches)
     &&FCString::Strtoui64(*ChairRevision,nullptr,10)==SeatChairRevision){
   FSub01SeatEvidence Loaded;Loaded.Loaded=true;Loaded.Family=ESub01SeatFamily::DeskTyping;
   Loaded.MeshId=FCString::Strtoui64(*MeshId,nullptr,10);Loaded.ClipId=FCString::Strtoui64(*ClipId,nullptr,10);Loaded.ChairRevision=SeatChairRevision;
   Loaded.X=(*Body)[0]->AsNumber();Loaded.Y=(*Body)[1]->AsNumber();Loaded.Z=(*Body)[2]->AsNumber();
   Loaded.PitchDeg=(*Rotation)[0]->AsNumber();Loaded.YawDeg=(*Rotation)[1]->AsNumber();Loaded.RollDeg=(*Rotation)[2]->AsNumber();
   Loaded.ScaleX=(*Scale)[0]->AsNumber();Loaded.ScaleY=(*Scale)[1]->AsNumber();Loaded.ScaleZ=(*Scale)[2]->AsNumber();
   Loaded.T0=(*Range)[0]->AsNumber();Loaded.T1=(*Range)[1]->AsNumber();
   const TCHAR* Names[5]={TEXT("buttocks"),TEXT("left_posterior_thigh"),TEXT("right_posterior_thigh"),TEXT("left_sole"),TEXT("right_sole")};bool Complete=true;
   for(int32 I=0;I<5;++I){const TSharedPtr<FJsonObject>* P=nullptr;if(!(*Patches)->TryGetObjectField(Names[I],P)||!(*P)->TryGetNumberField(TEXT("min_gap_cm"),Loaded.MinGap[I])||!(*P)->TryGetNumberField(TEXT("max_median_cm"),Loaded.MaxMedian[I])||!(*P)->TryGetNumberField(TEXT("min_coverage"),Loaded.MinCoverage[I]))Complete=false;}
   if(Complete&&Sub01SeatEvidenceInBand(Loaded)){
    SeatEvidence=Loaded;
    // The measured pose decides where the capsule stands: audited mesh anchor minus the mesh offset.
    SeatYaw=Loaded.YawDeg-(FirstPersonBody?HandsMeshRotation.Yaw:0);double X=0,Y=0;
    Sub01SeatApproachFromAnchor(Loaded.X,Loaded.Y,SeatYaw,WalkMeshOffset.X,WalkMeshOffset.Y,X,Y);SeatApproach=FVector2D(X,Y);SeatAnchorValid=true;
   }
  }
 }
 // The keyboard contact profile (when bound) was audited at one body world transform; it may
 // drive the arms only while the live body is at that transform.
 SeatProfilePoseLoaded=false;FString ProfilePath,ProfileText;TSharedPtr<FJsonObject> Profile;
 if(FParse::Value(FCommandLine::Get(),TEXT("Sub01ContactProfile="),ProfilePath)&&FFileHelper::LoadFileToString(ProfileText,*ProfilePath)
    &&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ProfileText),Profile)&&Profile.IsValid()){
  const TArray<TSharedPtr<FJsonValue>>* Body=nullptr;double Yaw=NAN;
  if(Profile->TryGetArrayField(TEXT("body_cm"),Body)&&Body->Num()==3&&Profile->TryGetNumberField(TEXT("body_yaw"),Yaw)){
   // unreal_audit_skinned_contact.py / the diagnostic seat place the body at body_cm, yaw body_yaw, no pitch or roll, unit scale.
   SeatProfilePose.X=(*Body)[0]->AsNumber();SeatProfilePose.Y=(*Body)[1]->AsNumber();SeatProfilePose.Z=(*Body)[2]->AsNumber();
   SeatProfilePose.PitchDeg=0;SeatProfilePose.YawDeg=Yaw;SeatProfilePose.RollDeg=0;SeatProfilePose.ScaleX=SeatProfilePose.ScaleY=SeatProfilePose.ScaleZ=1;
   SeatProfilePoseLoaded=Sub01SeatTransformFinite(SeatProfilePose);
  }
 }
 UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_TRANSITION_READY cushionTriangles=%d profilePose=%d"),SeatCushionTriangles.Num()/3,SeatProfilePoseLoaded?1:0);
 UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_TRANSITION_READY roles=%u chairMeasured=%d contactEvidence=%d approach=%s; NativeSeatVerified only from a live receipt"),SeatRoles,SeatChairMeasured?1:0,SeatEvidence.Loaded?1:0,*SeatApproach.ToString());
}
// The body as it is actually rendered for the seat: the owner mesh on the capsule (Walk
// attachment, no camera parent, no diagnostic world placement). Anything else has no transform.
bool ASub01HomeCharacter::SeatLiveBody(FSub01SeatLivePose& L) const{
 if(!FirstPersonBody||!FirstPersonBody->GetSkeletalMeshAsset()||HandsDiagnosticSeat||FirstPersonBody->GetAttachParent()!=GetRootComponent())return false;
 const FTransform Body=FirstPersonBody->GetComponentTransform();const FRotator R=Body.Rotator();const FVector S=Body.GetScale3D();
 L.MeshId=Sub01SeatId(*FirstPersonBody->GetSkeletalMeshAsset()->GetPathName());
 L.X=Body.GetLocation().X;L.Y=Body.GetLocation().Y;L.Z=Body.GetLocation().Z;L.PitchDeg=R.Pitch;L.YawDeg=R.Yaw;L.RollDeg=R.Roll;L.ScaleX=S.X;L.ScaleY=S.Y;L.ScaleZ=S.Z;
 return Sub01SeatTransformFinite(L);
}
void ASub01HomeCharacter::UpdateSeatTransition(float Dt){
 if(!LiveHome)return;const double Now=FPlatformTime::Seconds();
 const bool DeskActivity=LiveHomeActivity==TEXT("use_computer")||LiveHomeActivity==TEXT("research")||LiveHomeActivity==TEXT("chart")||LiveHomeActivity==TEXT("chat")||LiveHomeActivity==TEXT("watch_video")||LiveHomeActivity==TEXT("play_chess");
 FSub01SeatInputs In;In.NowSeconds=Now;
 In.Command=Sub01SeatId(*FString::Printf(TEXT("%s|%lld|%s"),*LiveHomeEpoch,LiveHomeCommandSequence,*LiveHomeActivity));
 In.WantSeat=SeatAnchorValid&&LiveHomeTarget==TEXT("desk")&&LiveHomeNode==TEXT("desk")&&LiveHomePath.Num()==0&&DeskActivity;
 In.WantTyping=In.WantSeat&&(LiveHomeActivity==TEXT("use_computer")||LiveHomeActivity==TEXT("research")||LiveHomeActivity==TEXT("chart"));
 In.Fresh=LiveHomeFresh&&Now>=LiveHomeLastReceived&&Now-LiveHomeLastReceived<=3;In.Private=LiveHomePrivate;In.Blocked=LiveHomeBlocked;
 In.ChairMeasured=SeatChairMeasured;In.ChairRevision=SeatChairRevision;In.RolesAvailable=SeatRoles;
 const FVector Here=GetActorLocation();const FVector2D ToApproach=SeatApproach-FVector2D(Here.X,Here.Y);
 In.AtApproach=SeatAnchorValid&&ToApproach.Size()<12&&GetCharacterMovement()->IsMovingOnGround();
 const float ViewYaw=Controller?Controller->GetControlRotation().Yaw:GetActorRotation().Yaw;In.YawErrorDeg=FMath::FindDeltaAngleDegrees(ViewYaw,SeatYaw);
 FSub01SeatLivePose Live;const bool HasBody=SeatLiveBody(Live);
 // Precise arrival is measured on the rendered body against the audited body anchor, never the capsule.
 if(SeatEvidence.Loaded&&HasBody){In.SettleErrorCm=FVector2D(SeatEvidence.X-Live.X,SeatEvidence.Y-Live.Y).Size();In.YawErrorDeg=FMath::FindDeltaAngleDegrees(Live.YawDeg,SeatEvidence.YawDeg);}
 In.SettleBlocked=SeatSettleBlocked;
 auto* Instance=FirstPersonBody?Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()):nullptr;
 static const TCHAR* ClipRoles[]={TEXT(""),TEXT("StandToSit"),TEXT("Sitting"),TEXT("SitToType"),TEXT("DeskTyping"),TEXT("SitToStand")};
 UAnimSequence* Requested=SeatOut.Clip==ESub01SeatClip::None?nullptr:SeatClips.FindRef(ClipRoles[uint8(SeatOut.Clip)]);
 // Playback as the hands proxy actually evaluated it: its sequence, the start serial it
 // applied and its accumulated time (not the requested target, not a wall clock).
 In.ClipPlaying=Requested&&Instance&&Instance->SeatEvaluatedSequence==Requested&&Instance->SeatEvaluatedTime>=0;
 In.ClipSerial=Instance?uint32(Instance->SeatEvaluatedSerial):0;In.ClipSeconds=Instance?Instance->SeatEvaluatedTime:0;
 if(SeatOut.Clip==ESub01SeatClip::DeskTyping&&HasBody&&Requested){
  FSub01SeatLivePose L=Live;L.ClipId=Sub01SeatId(*Requested->GetPathName());L.Family=ESub01SeatFamily::DeskTyping;
  L.ChairRevision=SeatChairRevision;L.ClipSeconds=In.ClipSeconds;L.ClipPlaying=In.ClipPlaying&&In.ClipSerial==SeatOut.ClipSerial;
  // Live measurement (5 Hz while typing): the actual evaluated skin at the actual body transform,
  // against the audited cushion and the floor the capsule actually stands on.
  const FFindFloorResult& Floor=GetCharacterMovement()->CurrentFloor;
  if(L.ClipPlaying&&SeatCushionTriangles.Num()&&Floor.IsWalkableFloor()&&Now-SeatMeasuredAt>=.2){
   SeatMeasuredAt=Now;SeatMeasurement=FSub01SeatMeasurement();
   const FString Report=USub01HomeHandsInstance::AnalyzeCapturedSeatSkin(FirstPersonBody->GetSkeletalMeshAsset(),FirstPersonBody->GetComponentSpaceTransforms(),FirstPersonBody->GetComponentTransform(),SeatCushionTriangles,Floor.HitResult.ImpactPoint.Z);
   TSharedPtr<FJsonObject> J;const TArray<TSharedPtr<FJsonValue>>* Regions=nullptr;double Invalid=-1;
   if(FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Report),J)&&J.IsValid()&&!J->HasField(TEXT("error"))&&J->TryGetNumberField(TEXT("invalidInfluences"),Invalid)&&J->TryGetArrayField(TEXT("regions"),Regions)&&Regions->Num()==5){
    FSub01SeatMeasurement M;M.MeshId=L.MeshId;M.ChairRevision=SeatChairRevision;M.ClipSerial=In.ClipSerial;M.MeasuredAt=Now;M.InvalidInfluences=int(Invalid);
    M.X=L.X;M.Y=L.Y;M.Z=L.Z;M.PitchDeg=L.PitchDeg;M.YawDeg=L.YawDeg;M.RollDeg=L.RollDeg;M.ScaleX=L.ScaleX;M.ScaleY=L.ScaleY;M.ScaleZ=L.ScaleZ;
    const TCHAR* Names[5]={TEXT("buttocks"),TEXT("left_posterior_thigh"),TEXT("right_posterior_thigh"),TEXT("left_sole"),TEXT("right_sole")};bool Complete=true;
    for(int32 I=0;I<5;++I){const auto R=(*Regions)[I]->AsObject();FString Name;double Facing=0,Over=0,Band=0;
     if(!R->TryGetStringField(TEXT("region"),Name)||Name!=Names[I]||!R->TryGetNumberField(TEXT("facingVertices"),Facing)||!R->TryGetNumberField(TEXT("overSurfaceVertices"),Over)||!R->TryGetNumberField(TEXT("bandVertices"),Band)
        ||!R->TryGetNumberField(TEXT("minGapCm"),M.MinGap[I])||!R->TryGetNumberField(TEXT("p50GapCm"),M.Median[I])||Over<=0){Complete=false;break;}
     M.Facing[I]=int(Facing);M.Coverage[I]=Band/Over;}
    M.Valid=Complete;SeatMeasurement=M;
   }
   const int32 InBand=Sub01SeatMeasuredReceipt(SeatMeasurement,L,In.ClipSerial,Now)?1:0;
   if(InBand!=SeatMeasurementLogged){SeatMeasurementLogged=InBand;UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_LIVE_MEASUREMENT inBand=%d floorCm=%.4f %s"),InBand,Floor.HitResult.ImpactPoint.Z,*Report.Left(600));}
  }
  In.Receipt=Sub01SeatReceipt(SeatEvidence,L)||Sub01SeatMeasuredReceipt(SeatMeasurement,L,In.ClipSerial,Now);
 }
 // The keyboard contact profile drives the arms only at the body transform it was audited at.
 if(Instance)Instance->ContactProfileAllowed=SeatProfilePoseLoaded&&HasBody&&Sub01SeatSameTransform(SeatProfilePose,Live);
 SeatOut=SeatMachine.Tick(In);
 if(SeatOut.Phase!=SeatLoggedPhase||SeatOut.Refusal!=ESub01SeatRefusal::None){
  if(SeatOut.Phase!=SeatLoggedPhase)UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_PHASE %d clip=%d serial=%u refusal=%d contact=%d"),int32(SeatOut.Phase),int32(SeatOut.Clip),SeatOut.ClipSerial,int32(SeatOut.Refusal),SeatOut.ContactVerified?1:0);
  // The exact live body transform while typing: what a re-audit must pose the skin at for a receipt.
  if(SeatOut.Phase!=SeatLoggedPhase&&SeatOut.Phase==ESub01SeatPhase::Typing&&FirstPersonBody){const FTransform B=FirstPersonBody->GetComponentTransform();const FRotator R=B.Rotator();const FVector S=B.GetScale3D();
   UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_LIVE_BODY cm=[%.4f,%.4f,%.4f] pyr=[%.4f,%.4f,%.4f] scale=[%.6f,%.6f,%.6f]"),B.GetLocation().X,B.GetLocation().Y,B.GetLocation().Z,R.Pitch,R.Yaw,R.Roll,S.X,S.Y,S.Z);}
  SeatLoggedPhase=SeatOut.Phase;
 }
 // A new clip starts only when its serial changes (never restarted per tick). The proxy applies
 // start time and looping once per serial, even when the same sequence is already playing,
 // and reports the serial back with what it evaluated.
 if(SeatOut.ClipSerial!=SeatAppliedSerial&&Instance){
  SeatAppliedSerial=SeatOut.ClipSerial;
  Instance->SeatStartSequence=SeatOut.Clip==ESub01SeatClip::None?nullptr:SeatClips.FindRef(ClipRoles[uint8(SeatOut.Clip)]);
  Instance->SeatStartSeconds=SeatOut.ClipStartSeconds;Instance->SeatStartSerial=int32(SeatOut.ClipSerial);
  Instance->SeatNoLoop=SeatOut.Clip==ESub01SeatClip::StandToSit||SeatOut.Clip==ESub01SeatClip::SitToType||SeatOut.Clip==ESub01SeatClip::SitToStand;
 }
 // Body and camera follow the captured clip while seated; restored when standing again.
 const bool Seated=!SeatOut.MovementInput;
 if(Seated&&!SeatBodyAttached&&FirstPersonBody&&FirstPersonBody->GetSkeletalMeshAsset()){
  SetHandsPosture(TEXT("Walk"));FName Head;const auto& Ref=FirstPersonBody->GetSkeletalMeshAsset()->GetRefSkeleton();
  for(int32 I=0;I<Ref.GetNum();++I)if(Ref.GetBoneName(I).ToString().EndsWith(TEXT("Head")))Head=Ref.GetBoneName(I);
  if(!Head.IsNone()){ViewCamera->AttachToComponent(FirstPersonBody,FAttachmentTransformRules::SnapToTargetNotIncludingScale,Head);ViewCamera->SetUsingAbsoluteRotation(true);}
  SeatBodyAttached=true;
 }else if(!Seated&&SeatBodyAttached){
  ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);ViewCamera->SetUsingAbsoluteRotation(false);
  ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);SeatBodyAttached=false;
 }
 // Movement: only CharacterMovement input toward the approach point, a bounded turn in place, a
 // bounded swept settle while standing, or nothing. A seated body never moves.
 if(SeatOut.Phase!=ESub01SeatPhase::Aligning){SeatSettleTravel=0;SeatSettleBlocked=false;}
 if(!SeatOut.MovementInput)GetCharacterMovement()->StopMovementImmediately();
 else if(SeatOut.TurnInPlace&&Controller){
  const float Step=103.1324f*FMath::Min(Dt,.1f);Controller->SetControlRotation(FRotator(-4,ViewYaw+FMath::Clamp(In.YawErrorDeg,-Step,Step),0));
  if(SeatOut.SettleMove&&HasBody){
   // At most 0.25 cm and 15 cm/s per tick, 15 cm in total, horizontal only, swept against
   // collision: a hit ends the settle (no depenetration, no sliding along what it hit).
   const FVector2D To(SeatEvidence.X-Live.X,SeatEvidence.Y-Live.Y);const float Distance=To.Size();
   const float Step2=FMath::Min3(Distance,.25f,15.f*FMath::Min(Dt,.1f));
   if(Distance>0&&Step2>0&&SeatSettleTravel+Step2<=15.f){
    GetCharacterMovement()->StopMovementImmediately();FHitResult Hit;
    GetCharacterMovement()->MoveUpdatedComponent(FVector(To.X/Distance*Step2,To.Y/Distance*Step2,0),GetActorQuat(),true,&Hit);
    SeatSettleTravel+=Step2;if(Hit.bBlockingHit||Hit.bStartPenetrating)SeatSettleBlocked=true;
   }else SeatSettleBlocked=true;
  }
 }
 else if(In.WantSeat&&In.Fresh&&!In.Private&&!In.Blocked&&SeatOut.Phase==ESub01SeatPhase::Standing&&!In.AtApproach&&Controller){
  const float Distance=ToApproach.Size();if(Distance>1)AddMovementInput(FVector(ToApproach.X/Distance,ToApproach.Y/Distance,0),FMath::Clamp(Distance/45.f,.15f,1.f));
 }
 // NativeSeatVerified only from a live, pose-matched receipt; PC focus never without it.
 NativeSeatVerified=SeatOut.ContactVerified;
 if(!SeatOut.PCFocusAllowed&&PCBridge)PCBridge->SetOperatorFocus(false);
}
void ASub01HomeCharacter::ApplySeatAnimation(USub01HomeHandsInstance* Instance){
 if(!Instance||SeatOut.Clip==ESub01SeatClip::None)return;
 static const TCHAR* ClipRoles[]={TEXT(""),TEXT("StandToSit"),TEXT("Sitting"),TEXT("SitToType"),TEXT("DeskTyping"),TEXT("SitToStand")};
 if(UAnimSequence* Clip=SeatClips.FindRef(ClipRoles[uint8(SeatOut.Clip)])){Instance->TargetSequence=Clip;Instance->TargetRate=1.f;}
}
'''

HANDS_FIELDS = r'''
 // The keyboard contact profile may drive the arms (false in the live home unless the body is
 // at the profile's audited world transform).
 UPROPERTY(Transient) bool ContactProfileAllowed=true;
 // Seat clip start (tools/unreal_seat_transition_runtime.py): applied once per serial, and
 // what the proxy actually evaluated (sequence, applied serial, accumulated time).
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> SeatStartSequence;
 UPROPERTY(Transient) float SeatStartSeconds=0;
 UPROPERTY(Transient) int32 SeatStartSerial=0;
 UPROPERTY(Transient) bool SeatNoLoop=false;
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> SeatEvaluatedSequence;
 UPROPERTY(Transient) int32 SeatEvaluatedSerial=0;
 UPROPERTY(Transient) float SeatEvaluatedTime=-1;
'''

# Proxy side. PreUpdate publishes the last evaluation, then (after the target switch) applies
# a new serial's start once Current holds that serial's sequence: also when the sequence did not
# change. The measured contact profile keeps its own start and non-looping on DeskTyping.
PROXY_APPLY = (
    '  ContactAllowed=Hands->ContactProfileAllowed;\n'
    '  Hands->SeatEvaluatedSequence=SeatEvaluatedSequence;Hands->SeatEvaluatedSerial=SeatEvaluatedSerial;Hands->SeatEvaluatedTime=SeatEvaluatedTime;\n'
    '  if(SeatSerial!=Hands->SeatStartSerial&&Current.GetSequence()==Hands->SeatStartSequence.Get()){\n'
    '   SeatSerial=Hands->SeatStartSerial;\n'
    '   if(Hands->SeatStartSequence&&!(ContactTimes.Num()&&Current.GetSequence()==ContactSequence)){Current.SetAccumulatedTime(Hands->SeatStartSeconds);Current.SetLoopAnimation(!Hands->SeatNoLoop);}\n'
    '  }\n')
PROXY_EVALUATED = ('  SeatEvaluatedSequence=Cast<UAnimSequence>(Current.GetSequence());SeatEvaluatedTime=SeatEvaluatedSequence?Current.GetAccumulatedTime():-1.f;'
                   'SeatEvaluatedSerial=SeatSerial;\n')

# (file key, anchor, replacement); every anchor must occur exactly once in the staged source.
EDITS = [
    ('header', '#include "Sub01HomeLab.generated.h"', CHARACTER_INCLUDE + '#include "Sub01HomeLab.generated.h"'),
    ('header', ' void Forward(float Value);', CHARACTER_FIELDS + '\n void Forward(float Value);'),
    ('cpp', ' ConfigureActualPC();\n BeginLiveHome();\n', ' ConfigureActualPC();\n BeginLiveHome();\n LoadSeatTransition();\n'),
    ('cpp', ' UpdateNativeFeedback();\n', ' UpdateNativeFeedback();\n UpdateSeatTransition(Dt);\n'),
    ('cpp', ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(',
     ' // A seated body never walks off: the captured get-up must finish first.\n'
     ' if(!SeatOut.MovementInput&&LiveHomePath.Num()){GetCharacterMovement()->StopMovementImmediately();if(PCBridge)PCBridge->SetOperatorFocus(false);return;}\n'
     ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus('),
    ('cpp', 'Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?FMath::Clamp(Speed/140.f,.1f,1.2f):0.f):1.f;\n',
     'Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?FMath::Clamp(Speed/140.f,.1f,1.2f):0.f):1.f;\n ApplySeatAnimation(Instance);\n'),
    ('hands_header', ' protected:', HANDS_FIELDS + ' protected:'),
    ('hands_cpp', ' float Progress=1;\n',
     ' float Progress=1;int32 SeatSerial=0,SeatEvaluatedSerial=0;UAnimSequence* SeatEvaluatedSequence=nullptr;float SeatEvaluatedTime=-1;bool ContactAllowed=true;\n'),
    ('hands_cpp', '  Current.SetPlayRate(Hands->TargetRate);\n', PROXY_APPLY + '  Current.SetPlayRate(Hands->TargetRate);\n'),
    ('hands_cpp', '  Blend.Evaluate_AnyThread(Output);\n', '  Blend.Evaluate_AnyThread(Output);\n' + PROXY_EVALUATED),
    ('hands_cpp', '  if(Current.GetSequence()!=ContactSequence||ContactTimes.Num()<2',
     '  if(!ContactAllowed)return true;   // the raw clip, without the arm profile\n  if(Current.GetSequence()!=ContactSequence||ContactTimes.Num()<2'),
]


def install(sources: dict) -> dict:
    """Apply the seat integration to staged sources {'header','cpp','hands_header','hands_cpp'}."""
    out = dict(sources)
    for key, anchor, replacement in EDITS:
        if out[key].count(anchor) != 1:
            raise ValueError(f'Seat integration anchor not unique in {key}: {anchor[:60]!r}')
        out[key] = out[key].replace(anchor, replacement)
    out['cpp'] += CHARACTER_METHODS.replace('@@SEAT_CLIP_DIR@@', SEAT_CLIP_DIR)
    return out


def install_module(module: Path) -> None:
    """Apply to an already staged Source/Sub01HomeLab directory and copy the header."""
    module = Path(module)
    files = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp', 'hands_header': 'Sub01HomeHands.h', 'hands_cpp': 'Sub01HomeHands.cpp'}
    patched = install({key: (module / name).read_text() for key, name in files.items()})
    for key, name in files.items():
        (module / name).write_text(patched[key])
    shutil.copy2(HEADER_FILE, module / HEADER_FILE.name)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: python tools/unreal_seat_transition_runtime.py <UE project dir>')
    print(write_evidence(Path(sys.argv[1])))
