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
    scale = seat_report.get('body_scale', 1.0)
    values = [*body, yaw, scale]
    if len(body) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values) or scale <= 0:
        raise ValueError('Audited body transform must be finite')
    return {'schema': 'sub01.native-seat-evidence.v1', 'family': 'DeskTyping',
            'mesh': mesh, 'clip': clip, 'mesh_id': str(seat_id(mesh)), 'clip_id': str(seat_id(clip)),
            'chair_component': chair['chair']['component'], 'chair_revision': str(seat_id(chair_text)),
            'body_cm': list(body), 'body_yaw': yaw, 'body_scale': scale,
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
 double SeatClipStartedAt=0,SeatClipStartOffset=0; FVector2D SeatApproach=FVector2D::ZeroVector;
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
   SeatChairRevision=Sub01SeatId(*ChairText);SeatChairMeasured=true;
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
  FString Family,MeshId,ClipId,ChairRevision;const TArray<TSharedPtr<FJsonValue>> *Body=nullptr,*Range=nullptr;const TSharedPtr<FJsonObject>* Patches=nullptr;double Yaw=NAN,Scale=NAN;
  if(E->TryGetStringField(TEXT("family"),Family)&&Family==TEXT("DeskTyping")&&E->TryGetStringField(TEXT("mesh_id"),MeshId)&&E->TryGetStringField(TEXT("clip_id"),ClipId)
     &&E->TryGetStringField(TEXT("chair_revision"),ChairRevision)&&E->TryGetArrayField(TEXT("body_cm"),Body)&&Body->Num()==3&&E->TryGetNumberField(TEXT("body_yaw"),Yaw)
     &&E->TryGetNumberField(TEXT("body_scale"),Scale)&&E->TryGetArrayField(TEXT("time_range_s"),Range)&&Range->Num()==2&&E->TryGetObjectField(TEXT("patches"),Patches)
     &&FCString::Strtoui64(*ChairRevision,nullptr,10)==SeatChairRevision){
   FSub01SeatEvidence Loaded;Loaded.Loaded=true;Loaded.Family=ESub01SeatFamily::DeskTyping;
   Loaded.MeshId=FCString::Strtoui64(*MeshId,nullptr,10);Loaded.ClipId=FCString::Strtoui64(*ClipId,nullptr,10);Loaded.ChairRevision=SeatChairRevision;
   Loaded.X=(*Body)[0]->AsNumber();Loaded.Y=(*Body)[1]->AsNumber();Loaded.Z=(*Body)[2]->AsNumber();Loaded.YawDeg=Yaw;Loaded.Scale=Scale;
   Loaded.T0=(*Range)[0]->AsNumber();Loaded.T1=(*Range)[1]->AsNumber();
   const TCHAR* Names[5]={TEXT("buttocks"),TEXT("left_posterior_thigh"),TEXT("right_posterior_thigh"),TEXT("left_sole"),TEXT("right_sole")};bool Complete=true;
   for(int32 I=0;I<5;++I){const TSharedPtr<FJsonObject>* P=nullptr;if(!(*Patches)->TryGetObjectField(Names[I],P)||!(*P)->TryGetNumberField(TEXT("min_gap_cm"),Loaded.MinGap[I])||!(*P)->TryGetNumberField(TEXT("max_median_cm"),Loaded.MaxMedian[I])||!(*P)->TryGetNumberField(TEXT("min_coverage"),Loaded.MinCoverage[I]))Complete=false;}
   if(Complete&&Sub01SeatEvidenceInBand(Loaded)){
    SeatEvidence=Loaded;
    // The measured pose decides where the capsule stands: audited mesh anchor minus the mesh offset.
    SeatYaw=Yaw-(FirstPersonBody?HandsMeshRotation.Yaw:0);double X=0,Y=0;
    Sub01SeatApproachFromAnchor(Loaded.X,Loaded.Y,SeatYaw,WalkMeshOffset.X,WalkMeshOffset.Y,X,Y);SeatApproach=FVector2D(X,Y);SeatAnchorValid=true;
   }
  }
 }
 UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_TRANSITION_READY roles=%u chairMeasured=%d contactEvidence=%d approach=%s; NativeSeatVerified only from a live receipt"),SeatRoles,SeatChairMeasured?1:0,SeatEvidence.Loaded?1:0,*SeatApproach.ToString());
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
 auto* Instance=FirstPersonBody?Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()):nullptr;
 static const TCHAR* ClipRoles[]={TEXT(""),TEXT("StandToSit"),TEXT("Sitting"),TEXT("SitToType"),TEXT("DeskTyping"),TEXT("SitToStand")};
 UAnimSequence* Requested=SeatOut.Clip==ESub01SeatClip::None?nullptr:SeatClips.FindRef(ClipRoles[uint8(SeatOut.Clip)]);
 In.ClipPlaying=Requested&&Instance&&Instance->TargetSequence==Requested;
 In.ClipSeconds=SeatClipStartOffset+(Now-SeatClipStartedAt);
 // Typing replays the measured contact profile: use its actually evaluated time when bound.
 if(SeatOut.Clip==ESub01SeatClip::DeskTyping&&Instance&&Instance->ContactSequence==Requested&&Instance->ContactEvaluatedTime>=0)In.ClipSeconds=Instance->ContactEvaluatedTime;
 if(SeatOut.Clip==ESub01SeatClip::DeskTyping&&SeatEvidence.Loaded&&FirstPersonBody&&FirstPersonBody->GetSkeletalMeshAsset()&&Requested){
  FSub01SeatLivePose L;const FTransform Body=FirstPersonBody->GetComponentTransform();
  L.MeshId=Sub01SeatId(*FirstPersonBody->GetSkeletalMeshAsset()->GetPathName());L.ClipId=Sub01SeatId(*Requested->GetPathName());L.Family=ESub01SeatFamily::DeskTyping;
  L.ChairRevision=SeatChairRevision;L.X=Body.GetLocation().X;L.Y=Body.GetLocation().Y;L.Z=Body.GetLocation().Z;L.YawDeg=Body.Rotator().Yaw;L.Scale=Body.GetScale3D().X;
  L.ClipSeconds=In.ClipSeconds;L.ClipPlaying=In.ClipPlaying;In.Receipt=Sub01SeatReceipt(SeatEvidence,L);
 }
 SeatOut=SeatMachine.Tick(In);
 if(SeatOut.Phase!=SeatLoggedPhase||SeatOut.Refusal!=ESub01SeatRefusal::None){
  if(SeatOut.Phase!=SeatLoggedPhase)UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_PHASE %d clip=%d serial=%u refusal=%d contact=%d"),int32(SeatOut.Phase),int32(SeatOut.Clip),SeatOut.ClipSerial,int32(SeatOut.Refusal),SeatOut.ContactVerified?1:0);
  SeatLoggedPhase=SeatOut.Phase;
 }
 // A new clip starts only when its serial changes (never restarted per tick).
 if(SeatOut.ClipSerial!=SeatAppliedSerial){
  SeatAppliedSerial=SeatOut.ClipSerial;SeatClipStartedAt=Now;SeatClipStartOffset=SeatOut.ClipStartSeconds;
  if(Instance){Instance->SeatStartSeconds=SeatOut.ClipStartSeconds;++Instance->SeatStartSerial;Instance->SeatNoLoop=SeatOut.Clip==ESub01SeatClip::StandToSit||SeatOut.Clip==ESub01SeatClip::SitToType||SeatOut.Clip==ESub01SeatClip::SitToStand;}
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
 // Movement: only CharacterMovement input toward the approach point, a bounded turn in place, or nothing.
 if(!SeatOut.MovementInput)GetCharacterMovement()->StopMovementImmediately();
 else if(SeatOut.TurnInPlace&&Controller){const float Step=103.1324f*FMath::Min(Dt,.1f);Controller->SetControlRotation(FRotator(-4,ViewYaw+FMath::Clamp(In.YawErrorDeg,-Step,Step),0));}
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
 // Seat clip start (tools/unreal_seat_transition_runtime.py): applied once per serial.
 UPROPERTY(Transient) float SeatStartSeconds=0;
 UPROPERTY(Transient) int32 SeatStartSerial=0;
 UPROPERTY(Transient) bool SeatNoLoop=false;
'''

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
    ('hands_cpp', ' float Progress=1;\n', ' float Progress=1;int32 SeatSerial=0;\n'),
    ('hands_cpp', '   Progress=Hands->PreviousSequence?0:1;\n',
     '   Progress=Hands->PreviousSequence?0:1;\n'
     '   if(SeatSerial!=Hands->SeatStartSerial){SeatSerial=Hands->SeatStartSerial;Current.SetAccumulatedTime(Hands->SeatStartSeconds);Current.SetLoopAnimation(!Hands->SeatNoLoop);}\n'),
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
