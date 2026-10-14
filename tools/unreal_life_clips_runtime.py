"""Native life clips adapter: binding gate, bed evidence gate, C++ integration and install hooks.

Owns tools/native_life/Sub01LifeClips.h and this file only. Nothing here is staged by default,
and no renderer-owned generator (unreal_hands_bindings.py, unreal_home_hands_runtime.py) is
edited. The runtime owner applies `install_module()` to already staged sources; until then the
live home is unchanged.

What it fixes, and only with genuine captured clips:
- Standing still: the renderer already prefers HandsClips["Idle"] while the Walk posture is not
  moving, but plays it at rate 0. With a bound Idle the adapter plays it looping at rate 1 (real
  breathing). Without one it refuses (ClipMissing / SkeletonMismatch / NotValidated) and leaves
  the renderer's choice alone; it never poses a bone or holds a hand-picked frame.
- Bed: lie down, sleep loop, get up, only with a measured bed surface, an accepted placement and
  all three captured clips on the owner skeleton. Otherwise it refuses (BedUnmeasured,
  BedPlacementMissing, ClipMissing, ...). Movement is off from the first frame of lying down
  until the get-up has played. Nothing sets an actor location.

Python side (runs anywhere):
    python tools/unreal_life_clips_runtime.py config INVENTORY.json UNREAL_LIFE_IMPORT.json OUT.ini
    python tools/unreal_life_clips_runtime.py audit-fbx INVENTORY.json OUT_DIR ROLE=PATH [ROLE=PATH ...]
    python tools/unreal_life_clips_runtime.py check-bed <UE project dir>
    python tools/unreal_life_clips_runtime.py install <project>/Source/Sub01HomeLab
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

HEADER_FILE = Path(__file__).resolve().parent / 'native_life' / 'Sub01LifeClips.h'
LIFE_CLIP_DIR = '/Game/Sub01Hands/Life'          # tools/unreal_import_life_fbx.py
ROLES = ('Idle', 'LieDown', 'SleepLoop', 'GetUp')
BED_ROLES = ('LieDown', 'SleepLoop', 'GetUp')
LOOPING_ROLES = ('Idle', 'SleepLoop')
MIN_MATTRESS_AREA_CM2 = 15000.0   # a single mattress top is ~17,000 cm2; a pillow or the frame rail is not a bed
CHARACTER_SECTION = '[/Script/Sub01HomeLab.Sub01HomeCharacter]'


def life_id(text: str) -> int:
    """FNV-1a over the low byte of each character, identical to Sub01LifeId()."""
    value = 1469598103934665603
    for char in text:
        value ^= ord(char) & 0xFF
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def clip_object_path(role: str) -> str:
    return f'{LIFE_CLIP_DIR}/SUB01_{role}.SUB01_{role}'


# ---------------------------------------------------------------- binding gate (config fragment)
def role_bindings(inventory: dict, import_report: dict) -> dict:
    """Per role: the object path it may bind, or the explicit reason it may not.

    A role binds only when the inventory measured an accepted candidate on the owner skeleton
    (and, for Idle/SleepLoop, a loop), and the server import put exactly that file onto the
    existing owner USkeleton at the conventional path.
    """
    rows = {r['role']: r for r in import_report.get('clips', [])}
    result = {}
    for role in ROLES:
        candidates = [c for c in inventory.get('candidates', []) if c.get('role') == role]
        accepted = [c for c in candidates if c.get('verdict') == 'Candidate']
        row = rows.get(role)
        if not accepted:
            mismatch = any(c.get('verdict') == 'SkeletonMismatch' for c in candidates) and not any(
                c.get('skeleton', {}).get('same_owner_skeleton') for c in candidates)
            result[role] = {'bound': False, 'refusal': 'SkeletonMismatch' if mismatch else 'ClipMissing',
                            'reason': 'no genuine captured clip on the owner skeleton' if not mismatch
                            else 'clips exist only on other skeletons; no retarget is substituted'}
            continue
        if not row:
            result[role] = {'bound': False, 'refusal': 'NotImported', 'reason': 'no server import row'}
            continue
        source = [c for c in accepted if c.get('sha256') == row.get('inventory_sha256')]
        if len(source) != 1:
            result[role] = {'bound': False, 'refusal': 'ClipMissing', 'reason': 'imported file is not an accepted inventory candidate'}
            continue
        source = source[0]
        if row.get('same_existing_skeleton') is not True or not source.get('skeleton', {}).get('same_owner_skeleton'):
            result[role] = {'bound': False, 'refusal': 'SkeletonMismatch', 'reason': 'not imported on the existing owner USkeleton'}
            continue
        if row.get('object_path') != clip_object_path(role):
            result[role] = {'bound': False, 'refusal': 'ClipMissing', 'reason': f'expected {clip_object_path(role)}'}
            continue
        if role in LOOPING_ROLES and source.get('loop', {}).get('loops') is not True:
            result[role] = {'bound': False, 'refusal': 'NotLooping', 'reason': 'first and last poses differ'}
            continue
        if abs(float(row.get('duration_s', -1)) - float(source.get('duration_s', -2))) > 2 / 30:
            result[role] = {'bound': False, 'refusal': 'ClipMissing', 'reason': 'imported duration differs from the measured capture'}
            continue
        result[role] = {'bound': True, 'object_path': row['object_path'], 'source': source['file'], 'source_sha256': source['sha256']}
    # The bed is all three clips or nothing: a lone sleep loop must never play without its way in and out.
    if not all(result[r]['bound'] for r in BED_ROLES):
        missing = [r for r in BED_ROLES if not result[r]['bound']]
        for r in BED_ROLES:
            if result[r]['bound']:
                result[r] = {'bound': False, 'refusal': 'ClipMissing', 'reason': f'bed set incomplete: {", ".join(missing)} missing'}
    return result


def config_fragment(inventory: dict, import_report: dict) -> tuple[str, dict]:
    """Lines to ADD to the renderer's [Sub01HomeCharacter] section, and the refusals.

    A separate fragment: unreal_hands_bindings.py stays the renderer's. Only proven roles add
    `+ValidatedHandsPostures=<Role>`, so the renderer's own Bind() gate still decides at runtime.
    """
    roles = role_bindings(inventory, import_report)
    lines = []
    if roles['Idle']['bound']:
        lines += [f'IdleClipPath={roles["Idle"]["object_path"]}', '+ValidatedHandsPostures=Idle']
    for role in BED_ROLES:
        if roles[role]['bound']:
            lines.append(f'+ValidatedHandsPostures={role}')
    refusals = {r: v for r, v in roles.items() if not v['bound']}
    text = (CHARACTER_SECTION + '\n' + '\n'.join(lines) + '\n') if lines else ''
    return text, refusals


# ---------------------------------------------------------------- bed evidence gate
def mattress_triangles(bed: dict):
    if bed.get('errors') != []:
        raise ValueError('BedUnmeasured: the bed report has errors or no error list')
    tris = []
    for section in bed.get('bed', {}).get('sections', []):
        verts = section.get('vertices_world_cm')
        faces = section.get('mattress_surface', {}).get('triangle_indices')
        if verts is None or faces is None:
            continue
        for face in faces:
            if len(face) != 3 or any(not (0 <= i < len(verts)) or len(verts[i]) != 3 for i in face):
                raise ValueError('BedUnmeasured: malformed mattress triangle')
            tris.extend(verts[i] for i in face)
    if not tris:
        raise ValueError('BedUnmeasured: no measured mattress triangles')
    return tris


def mattress_area_cm2(tris) -> float:
    area = 0.0
    for a, b, c in zip(tris[0::3], tris[1::3], tris[2::3]):
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        area += .5 * math.sqrt(sum(x * x for x in cross))
    return area


def validate_bed(bed_text: str, evidence: dict | None) -> dict:
    """Mirror of the native loader. Raises ValueError('BedUnmeasured: ...'/'BedPlacementMissing: ...').

    native-bed-surface.json: {"errors": [], "bed": {"component": ..., "sections": [{"vertices_world_cm": [...],
        "mattress_surface": {"triangle_indices": [[i,j,k], ...]}}]}}
    native-life-bed-evidence.json: {"schema": "sub01.native-life-bed-evidence.v1", "bed_revision": "<life_id(bed text)>",
        "approach_cm": [x, y], "yaw_deg": yaw, "accepted": true}  -- written by a server placement audit
        that plays the imported LieDown/SleepLoop/GetUp at that approach and measures the skin against
        the mattress. No such audit exists in this repository yet.
    """
    bed = json.loads(bed_text)
    tris = mattress_triangles(bed)
    area = mattress_area_cm2(tris)
    if area < MIN_MATTRESS_AREA_CM2:
        raise ValueError(f'BedUnmeasured: mattress area {area:.0f} cm2 is not a bed')
    if not evidence:
        raise ValueError('BedPlacementMissing: no accepted bed placement evidence')
    approach, yaw = evidence.get('approach_cm'), evidence.get('yaw_deg')
    if evidence.get('schema') != 'sub01.native-life-bed-evidence.v1' or evidence.get('accepted') is not True:
        raise ValueError('BedPlacementMissing: placement evidence is not accepted')
    if str(evidence.get('bed_revision')) != str(life_id(bed_text)):
        raise ValueError('BedPlacementMissing: placement was measured against another bed report')
    if not (isinstance(approach, list) and len(approach) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v) for v in [*approach, yaw if isinstance(yaw, (int, float)) and not isinstance(yaw, bool) else math.nan])):
        raise ValueError('BedPlacementMissing: approach/yaw must be finite numbers')
    return {'area_cm2': area, 'approach_cm': approach, 'yaw_deg': yaw, 'bed_revision': str(life_id(bed_text))}


def check_bed(project: Path) -> dict:
    audit = Path(project) / 'private-audit'
    surface = audit / 'native-bed-surface.json'
    if not surface.is_file():
        raise ValueError('BedUnmeasured: private-audit/native-bed-surface.json does not exist')
    placement = audit / 'native-life-bed-evidence.json'
    return validate_bed(surface.read_text(), json.loads(placement.read_text()) if placement.is_file() else None)


# ---------------------------------------------------------------- direct FBX sources (server)
def audit_fbx(inventory: dict, out_dir: Path, sources: dict) -> dict:
    """Stage operator-declared FBX captures (e.g. a Mixamo idle kept out of Git) for the import.

    Each must be an accepted inventory candidate for its role (same bytes: sha256), so the
    import and the binding gate refer to one measured file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for role, path in sources.items():
        path = Path(path)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        match = [c for c in inventory['candidates'] if c.get('role') == role and c.get('sha256') == sha and c.get('verdict') == 'Candidate']
        if len(match) != 1:
            raise ValueError(f'{role}: {path} is not an accepted inventory candidate (run the inventory with --extra {role}={path})')
        target = out_dir / f'{role}.fbx'
        shutil.copy2(path, target)
        rows.append({'role': role, 'file': target.name, 'sha256': sha, 'inventory_sha256': sha, 'duration_s': match[0]['duration_s'],
                     'source': 'operator FBX, imported unchanged'})
    doc = {'bone_names': sorted(owner_bones()), 'bone_edits': False, 'clips': rows, 'runtime_ready': False}
    (out_dir / 'life-fbx-audit.json').write_text(json.dumps(doc, indent=2) + '\n')
    return doc


def owner_bones():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import inventory_native_life_clips as inv  # noqa: E402
    return inv.owner_reference()['bones']


# ---------------------------------------------------------------- native integration
CHARACTER_INCLUDE = '#include "Sub01LifeClips.h"\n'

CHARACTER_FIELDS = r'''
 // Native life clips (tools/unreal_life_clips_runtime.py).
 void LoadLifeClips(); void UpdateLifeClips(class USub01HomeHandsInstance* Instance,float Dt); bool LifeMovementLocked() const;
 FSub01LifeMachine LifeMachine; FSub01LifeOutputs LifeOut; FSub01LifeRoleState LifeRoles;
 UPROPERTY() TMap<FName,TObjectPtr<UAnimSequence>> LifeClips;
 uint32 LifeAppliedSerial=0; ESub01LifePhase LifeLoggedPhase=ESub01LifePhase::Standing;
 ESub01LifeRefusal LifeLoggedRefusal=ESub01LifeRefusal::None,LifeLoggedIdleRefusal=ESub01LifeRefusal::None;
 bool LifeBedMeasured=false,LifeBedPlacementValid=false,LifeMovementDisabled=false,LifeCameraOnHead=false;
 uint64 LifeBedRevision=0; FVector2D LifeBedApproach=FVector2D::ZeroVector; float LifeBedYaw=0;
'''

CHARACTER_METHODS = r'''
void ASub01HomeCharacter::LoadLifeClips(){
 LifeRoles=FSub01LifeRoleState();LifeClips.Empty();LifeBedMeasured=false;LifeBedPlacementValid=false;
 USkeletalMesh* Mesh=FirstPersonBody?FirstPersonBody->GetSkeletalMeshAsset():nullptr;
 // Idle: the renderer's own binding (IdleClipPath, same skeleton, ValidatedHandsPostures) decides;
 // these bits only name why it is missing.
 if(!IdleClipPath.IsEmpty())if(auto* Clip=LoadObject<UAnimSequence>(nullptr,*IdleClipPath)){
  LifeRoles.Loaded|=Sub01LifeBit(ESub01LifeRole::Idle);
  if(Mesh&&Clip->GetSkeleton()==Mesh->GetSkeleton())LifeRoles.SameSkeleton|=Sub01LifeBit(ESub01LifeRole::Idle);
 }
 if(ValidatedHandsPostures.Contains(FName(TEXT("Idle"))))LifeRoles.Validated|=Sub01LifeBit(ESub01LifeRole::Idle);
 // Bed clips: the imported captures on the SAME owner skeleton, listed by the renderer's gate, or nothing.
 const TPair<const TCHAR*,ESub01LifeRole> Bed[]={{TEXT("LieDown"),ESub01LifeRole::LieDown},{TEXT("SleepLoop"),ESub01LifeRole::SleepLoop},{TEXT("GetUp"),ESub01LifeRole::GetUp}};
 for(const auto& Role:Bed){
  const FString Path=FString::Printf(TEXT("%s/SUB01_%s.SUB01_%s"),TEXT("@@LIFE_CLIP_DIR@@"),Role.Key,Role.Key);
  auto* Clip=LoadObject<UAnimSequence>(nullptr,*Path);const uint32 Bit=Sub01LifeBit(Role.Value);
  if(Clip)LifeRoles.Loaded|=Bit;
  if(Clip&&Mesh&&Clip->GetSkeleton()==Mesh->GetSkeleton())LifeRoles.SameSkeleton|=Bit;
  if(ValidatedHandsPostures.Contains(FName(Role.Key)))LifeRoles.Validated|=Bit;
  if(Clip&&(LifeRoles.SameSkeleton&Bit)&&(LifeRoles.Validated&Bit))LifeClips.Add(FName(Role.Key),Clip);
  else UE_LOG(LogTemp,Warning,TEXT("SUB01_LIFE_ROLE_MISSING %s loaded=%d"),*Path,Clip?1:0);
 }
 // Bed surface: the measured mattress report; its exact text is the bed revision.
 const FString Audit=FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit"));FString BedText;TSharedPtr<FJsonObject> Report;double Area=0;
 if(FFileHelper::LoadFileToString(BedText,*FPaths::Combine(Audit,TEXT("native-bed-surface.json")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(BedText),Report)&&Report.IsValid()){
  const TArray<TSharedPtr<FJsonValue>>* Errors=nullptr;const TSharedPtr<FJsonObject>* BedObject=nullptr;const TArray<TSharedPtr<FJsonValue>>* Sections=nullptr;
  if(Report->TryGetArrayField(TEXT("errors"),Errors)&&Errors->Num()==0&&Report->TryGetObjectField(TEXT("bed"),BedObject)&&(*BedObject)->TryGetArrayField(TEXT("sections"),Sections)){
   bool Valid=true;int32 Triangles=0;
   for(const auto& SectionValue:*Sections){
    const auto Section=SectionValue->AsObject();const TArray<TSharedPtr<FJsonValue>> *Vertices=nullptr,*Faces=nullptr;const TSharedPtr<FJsonObject>* Surface=nullptr;
    if(!Section.IsValid()||!Section->TryGetArrayField(TEXT("vertices_world_cm"),Vertices)||!Section->TryGetObjectField(TEXT("mattress_surface"),Surface)||!(*Surface)->TryGetArrayField(TEXT("triangle_indices"),Faces))continue;
    for(const auto& Face:*Faces){const auto& C=Face->AsArray();FVector P[3];
     if(C.Num()!=3){Valid=false;break;}
     for(int32 K=0;K<3;++K){const int32 I=int32(C[K]->AsNumber());if(!Vertices->IsValidIndex(I)||(*Vertices)[I]->AsArray().Num()!=3){Valid=false;break;}
      const auto& V=(*Vertices)[I]->AsArray();P[K]=FVector(V[0]->AsNumber(),V[1]->AsNumber(),V[2]->AsNumber());}
     if(!Valid)break;Area+=.5*FVector::CrossProduct(P[1]-P[0],P[2]-P[0]).Size();++Triangles;}
   }
   LifeBedMeasured=Valid&&Triangles>0&&Area>=@@MIN_MATTRESS_AREA@@;
   if(LifeBedMeasured)LifeBedRevision=Sub01LifeId(*BedText);
   else UE_LOG(LogTemp,Warning,TEXT("SUB01_LIFE_BED_REFUSED area=%.1fcm2 triangles=%d; a bed needs the measured mattress top"),Area,Triangles);
  }
 }
 // Placement: an accepted server audit of the captured bed clips at this approach on THIS bed report.
 FString EvidenceText;TSharedPtr<FJsonObject> E;
 if(LifeBedMeasured&&FFileHelper::LoadFileToString(EvidenceText,*FPaths::Combine(Audit,TEXT("native-life-bed-evidence.json")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(EvidenceText),E)&&E.IsValid()){
  FString Schema,Revision;bool Accepted=false;double Yaw=NAN;const TArray<TSharedPtr<FJsonValue>>* Approach=nullptr;
  if(E->TryGetStringField(TEXT("schema"),Schema)&&Schema==TEXT("sub01.native-life-bed-evidence.v1")&&E->TryGetBoolField(TEXT("accepted"),Accepted)&&Accepted
     &&E->TryGetStringField(TEXT("bed_revision"),Revision)&&FCString::Strtoui64(*Revision,nullptr,10)==LifeBedRevision
     &&E->TryGetArrayField(TEXT("approach_cm"),Approach)&&Approach->Num()==2&&E->TryGetNumberField(TEXT("yaw_deg"),Yaw)){
   LifeBedApproach=FVector2D((*Approach)[0]->AsNumber(),(*Approach)[1]->AsNumber());LifeBedYaw=float(Yaw);
   LifeBedPlacementValid=FMath::IsFinite(LifeBedApproach.X)&&FMath::IsFinite(LifeBedApproach.Y)&&FMath::IsFinite(Yaw);
  }
 }
 UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_READY idleBound=%d loaded=%u sameSkeleton=%u validated=%u bedMeasured=%d bedArea=%.1fcm2 placement=%d approach=%s"),
  HandsClips.Contains(FName(TEXT("Idle")))?1:0,LifeRoles.Loaded,LifeRoles.SameSkeleton,LifeRoles.Validated,LifeBedMeasured?1:0,Area,LifeBedPlacementValid?1:0,*LifeBedApproach.ToString());
}
bool ASub01HomeCharacter::LifeMovementLocked() const{return !LifeOut.MovementAllowed;}
void ASub01HomeCharacter::UpdateLifeClips(USub01HomeHandsInstance* Instance,float Dt){
 if(!Instance)return;const double Now=FPlatformTime::Seconds();
 static const TCHAR* ClipRoles[]={TEXT(""),TEXT("Walk"),TEXT("Idle"),TEXT("LieDown"),TEXT("SleepLoop"),TEXT("GetUp")};
 FSub01LifeInputs In;In.NowSeconds=Now;
 // The renderer's own gate and motion test, unchanged.
 In.PostureGate=HandsFailure.IsEmpty()&&HandsPosture==TEXT("Walk");
 In.Moving=In.PostureGate&&GetCharacterMovement()->IsMovingOnGround()&&GetVelocity().Size2D()>1;
 In.IdleBound=HandsClips.Contains(FName(TEXT("Idle"))); In.Roles=LifeRoles;
 In.WantSleep=LiveHome&&LiveHomeActivity==TEXT("sleep")&&LiveHomeTarget==TEXT("bed")&&LiveHomeNode==TEXT("bed")&&LiveHomePath.Num()==0;
 In.Fresh=LiveHome&&LiveHomeFresh&&Now>=LiveHomeLastReceived&&Now-LiveHomeLastReceived<=3;In.Private=LiveHomePrivate;In.Blocked=LiveHomeBlocked;
 In.BedMeasured=LifeBedMeasured;In.BedPlacementValid=LifeBedPlacementValid;
 const FVector Here=GetActorLocation();const FVector2D ToApproach=LifeBedApproach-FVector2D(Here.X,Here.Y);
 In.AtBedApproach=LifeBedPlacementValid&&ToApproach.Size()<12&&GetCharacterMovement()->IsMovingOnGround();
 const float ViewYaw=Controller?Controller->GetControlRotation().Yaw:GetActorRotation().Yaw;In.YawErrorDeg=FMath::FindDeltaAngleDegrees(ViewYaw,LifeBedYaw);
 // Playback as the hands proxy actually evaluated it (sequence, applied serial, accumulated time).
 UAnimSequence* Requested=uint8(LifeOut.Clip)>=uint8(ESub01LifeClip::LieDown)?LifeClips.FindRef(FName(ClipRoles[uint8(LifeOut.Clip)])):nullptr;
 In.ClipPlaying=Requested&&Instance->LifeEvaluatedSequence==Requested&&Instance->LifeEvaluatedTime>=0;
 In.ClipSerial=uint32(Instance->LifeEvaluatedSerial);In.ClipSeconds=Instance->LifeEvaluatedTime;
 if(UAnimSequence* Down=LifeClips.FindRef(FName(TEXT("LieDown"))))In.LieDownSeconds=Down->GetPlayLength();
 if(UAnimSequence* Up=LifeClips.FindRef(FName(TEXT("GetUp"))))In.GetUpSeconds=Up->GetPlayLength();
 LifeOut=LifeMachine.Tick(In);
 if(LifeOut.Phase!=LifeLoggedPhase||LifeOut.Refusal!=LifeLoggedRefusal){
  UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_PHASE %d clip=%d serial=%u refusal=%s movement=%d"),int32(LifeOut.Phase),int32(LifeOut.Clip),LifeOut.ClipSerial,ANSI_TO_TCHAR(Sub01LifeRefusalName(LifeOut.Refusal)),LifeOut.MovementAllowed?1:0);
  LifeLoggedPhase=LifeOut.Phase;LifeLoggedRefusal=LifeOut.Refusal;
 }
 if(LifeOut.IdleRefusal!=LifeLoggedIdleRefusal){
  if(LifeOut.IdleRefusal!=ESub01LifeRefusal::None)UE_LOG(LogTemp,Warning,TEXT("SUB01_LIFE_IDLE_REFUSED %s; standing still keeps the renderer's clip (no captured idle bound)"),ANSI_TO_TCHAR(Sub01LifeRefusalName(LifeOut.IdleRefusal)));
  else UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_IDLE_OK captured Idle loops at rate 1 while standing still"));
  LifeLoggedIdleRefusal=LifeOut.IdleRefusal;
 }
 // A new bed clip starts once per serial; the proxy applies start time and looping when Current holds it.
 if(LifeOut.ClipSerial!=LifeAppliedSerial){
  LifeAppliedSerial=LifeOut.ClipSerial;
  Instance->LifeStartSequence=uint8(LifeOut.Clip)>=uint8(ESub01LifeClip::LieDown)?LifeClips.FindRef(FName(ClipRoles[uint8(LifeOut.Clip)])):nullptr;
  Instance->LifeStartSerial=int32(LifeOut.ClipSerial);Instance->LifeNoLoop=!LifeOut.Loop;
 }
 // Animation: after the renderer chose its posture clip. Idle loops at rate 1 instead of the
 // renderer's rate 0; bed clips replace it while lying. Walk and None leave the renderer's choice.
 if(LifeOut.OverrideRate&&LifeOut.Clip!=ESub01LifeClip::None&&LifeOut.Clip!=ESub01LifeClip::Walk){
  if(LifeOut.Clip==ESub01LifeClip::Idle){
   // Only the renderer's own Idle choice gets its rate; a clip another adapter (the seat) chose is left alone.
   UAnimSequence* Idle=HandsClips.FindRef(FName(TEXT("Idle")));
   if(Idle&&Instance->TargetSequence==Idle)Instance->TargetRate=1.f;
  }else if(UAnimSequence* Clip=LifeClips.FindRef(FName(ClipRoles[uint8(LifeOut.Clip)]))){Instance->TargetSequence=Clip;Instance->TargetRate=1.f;}
 }
 // Movement: off (not just stopped) from the first frame of lying down until the get-up has played.
 if(!LifeOut.MovementAllowed&&!LifeMovementDisabled){GetCharacterMovement()->StopMovementImmediately();GetCharacterMovement()->DisableMovement();LifeMovementDisabled=true;}
 else if(LifeOut.MovementAllowed&&LifeMovementDisabled){GetCharacterMovement()->SetMovementMode(MOVE_Walking);LifeMovementDisabled=false;}
 // In bed the eye follows the captured Head bone; the body stays on the capsule (never on the camera).
 const bool InBed=LifeOut.Phase==ESub01LifePhase::LyingDown||LifeOut.Phase==ESub01LifePhase::Asleep||LifeOut.Phase==ESub01LifePhase::GettingUp;
 if(InBed&&!LifeCameraOnHead&&FirstPersonBody&&FirstPersonBody->GetSkeletalMeshAsset()&&FirstPersonBody->GetAttachParent()==GetRootComponent()){
  FName Head;const auto& Ref=FirstPersonBody->GetSkeletalMeshAsset()->GetRefSkeleton();
  for(int32 I=0;I<Ref.GetNum();++I)if(Ref.GetBoneName(I).ToString().EndsWith(TEXT("Head")))Head=Ref.GetBoneName(I);
  if(!Head.IsNone()){ViewCamera->AttachToComponent(FirstPersonBody,FAttachmentTransformRules::SnapToTargetNotIncludingScale,Head);ViewCamera->SetUsingAbsoluteRotation(true);LifeCameraOnHead=true;}
 }else if(!InBed&&LifeCameraOnHead){
  ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);ViewCamera->SetUsingAbsoluteRotation(false);
  ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);LifeCameraOnHead=false;
 }
 // Walking to the measured approach: CharacterMovement input only, then a bounded turn in place.
 if(LifeOut.WalkToBed&&Controller){const float Distance=ToApproach.Size();if(Distance>1)AddMovementInput(FVector(ToApproach.X/Distance,ToApproach.Y/Distance,0),FMath::Clamp(Distance/45.f,.15f,1.f));}
 else if(LifeOut.TurnInPlace&&Controller){const float Step=103.1324f*FMath::Min(Dt,.1f);Controller->SetControlRotation(FRotator(-4,ViewYaw+FMath::Clamp(In.YawErrorDeg,-Step,Step),0));}
}
'''

HANDS_FIELDS = r'''
 // Life clip start (tools/unreal_life_clips_runtime.py): applied once per serial, and what the
 // proxy actually evaluated (sequence, applied serial, accumulated time).
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> LifeStartSequence;
 UPROPERTY(Transient) int32 LifeStartSerial=0;
 UPROPERTY(Transient) bool LifeNoLoop=false;
 UPROPERTY(Transient) TObjectPtr<UAnimSequence> LifeEvaluatedSequence;
 UPROPERTY(Transient) int32 LifeEvaluatedSerial=0;
 UPROPERTY(Transient) float LifeEvaluatedTime=-1;
'''

PROXY_FIELDS = ' int32 LifeSerial=0,LifeEvaluatedSerial=0;UAnimSequence* LifeEvaluatedSequence=nullptr;float LifeEvaluatedTime=-1;\n'
PROXY_APPLY = (
    '  Hands->LifeEvaluatedSequence=LifeEvaluatedSequence;Hands->LifeEvaluatedSerial=LifeEvaluatedSerial;Hands->LifeEvaluatedTime=LifeEvaluatedTime;\n'
    '  if(LifeSerial!=Hands->LifeStartSerial&&Current.GetSequence()==Hands->LifeStartSequence.Get()){\n'
    '   LifeSerial=Hands->LifeStartSerial;\n'
    '   if(Hands->LifeStartSequence){Current.SetAccumulatedTime(0);Current.SetLoopAnimation(!Hands->LifeNoLoop);}\n'
    '  }\n')
PROXY_EVALUATED = ('  LifeEvaluatedSequence=Cast<UAnimSequence>(Current.GetSequence());LifeEvaluatedTime=LifeEvaluatedSequence?Current.GetAccumulatedTime():-1.f;'
                   'LifeEvaluatedSerial=LifeSerial;\n')

LIVE_GATE = (' // Lying (or getting up) never walks off: the captured get-up must finish first.\n'
             ' if(LifeMovementLocked()){GetCharacterMovement()->StopMovementImmediately();if(PCBridge)PCBridge->SetOperatorFocus(false);return;}\n')

# The renderer now plays a bound, chosen Idle at rate 1 itself (PlayingIdle, root main 178f52a).
RATE_ANCHOR = 'Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?float(Sub01FirstPersonMotion::AuthoredWalkRate(Speed)):(PlayingIdle?1.f:0.f)):1.f;\n'

RATE_PREFIX = 'Instance->TargetRate=HandsPosture==TEXT("Walk")?'


def _resolve_rate_line(cpp: str, anchor: str) -> str:
    """The renderer's walk-rate line changes form (e.g. AuthoredWalkRate); hook whichever single
    line starts with RATE_PREFIX, so the hook stays after the posture's own rate choice."""
    if cpp.count(anchor) == 1:
        return anchor
    lines = [l + '\n' for l in cpp.split('\n') if l.strip().startswith(RATE_PREFIX)]
    if len(lines) != 1:
        raise ValueError(f'Walk-rate anchor not unique: {len(lines)} lines start with {RATE_PREFIX!r}')
    return lines[0].lstrip()


# (file key, anchor, replacement); every anchor must occur exactly once in the staged source, and
# every replacement keeps its anchor, so the seat adapter's anchors survive in either install order.
EDITS = [
    ('header', '#include "Sub01HomeLab.generated.h"', CHARACTER_INCLUDE + '#include "Sub01HomeLab.generated.h"'),
    ('header', ' void Forward(float Value);', CHARACTER_FIELDS + '\n void Forward(float Value);'),
    ('cpp', ' LoadPrivateHandsDiagnostic();\n', ' LoadPrivateHandsDiagnostic();\n LoadLifeClips();\n'),
    ('cpp', ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(', LIVE_GATE + ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus('),
    ('cpp', RATE_ANCHOR, RATE_ANCHOR + ' UpdateLifeClips(Instance,DeltaSeconds);\n'),
    ('hands_header', ' protected:', HANDS_FIELDS + ' protected:'),
    ('hands_cpp', ' FAnimNode_TwoWayBlend Blend;\n', ' FAnimNode_TwoWayBlend Blend;\n' + PROXY_FIELDS),
    ('hands_cpp', '  Current.SetPlayRate(Hands->TargetRate);\n', PROXY_APPLY + '  Current.SetPlayRate(Hands->TargetRate);\n'),
    ('hands_cpp', '  Blend.Evaluate_AnyThread(Output);\n', '  Blend.Evaluate_AnyThread(Output);\n' + PROXY_EVALUATED),
]

SOURCE_FILES = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp', 'hands_header': 'Sub01HomeHands.h', 'hands_cpp': 'Sub01HomeHands.cpp'}


def install(sources: dict) -> dict:
    """Apply the life integration to staged sources {'header','cpp','hands_header','hands_cpp'}."""
    out = dict(sources)
    if 'FSub01LifeMachine LifeMachine;' in out['header']:
        raise ValueError('Life integration is already installed')
    for key, anchor, replacement in EDITS:
        if anchor == RATE_ANCHOR:
            live = _resolve_rate_line(out[key], anchor)
            anchor, replacement = live, replacement.replace(RATE_ANCHOR, live)
        if out[key].count(anchor) != 1:
            raise ValueError(f'Life integration anchor not unique in {key}: {anchor[:60]!r}')
        out[key] = out[key].replace(anchor, replacement)
    out['cpp'] += CHARACTER_METHODS.replace('@@LIFE_CLIP_DIR@@', LIFE_CLIP_DIR).replace('@@MIN_MATTRESS_AREA@@', f'{MIN_MATTRESS_AREA_CM2:.1f}')
    return out


def install_module(module: Path) -> None:
    """Apply to an already staged Source/Sub01HomeLab directory and copy the header."""
    module = Path(module)
    patched = install({key: (module / name).read_text() for key, name in SOURCE_FILES.items()})
    for key, name in SOURCE_FILES.items():
        (module / name).write_text(patched[key])
    shutil.copy2(HEADER_FILE, module / HEADER_FILE.name)


def main(argv):
    if len(argv) >= 1 and argv[0] == 'config' and len(argv) == 4:
        text, refusals = config_fragment(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
        if text:
            Path(argv[3]).write_text(text)
        print(json.dumps({'written': bool(text), 'refusals': refusals}, indent=2))
        return 0 if text else 3
    if len(argv) >= 4 and argv[0] == 'audit-fbx':
        sources = dict(item.split('=', 1) for item in argv[3:])
        print(json.dumps(audit_fbx(json.loads(Path(argv[1]).read_text()), Path(argv[2]), sources), indent=2))
        return 0
    if len(argv) == 2 and argv[0] == 'check-bed':
        print(json.dumps(check_bed(Path(argv[1])), indent=2))
        return 0
    if len(argv) == 2 and argv[0] == 'install':
        install_module(Path(argv[1]))
        print('Life clips adapter installed into staged sources; not compiled or running yet.')
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
