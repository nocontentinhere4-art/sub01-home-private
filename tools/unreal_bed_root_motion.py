"""Bed mesh root motion: a proposed install step AFTER tools/unreal_life_clips_runtime.py (private; not run).

The 67af5f8 adapter turns movement off in bed, and the renderer's standing capsule (radius 16-17, half-height
91-92) cannot and must not enter the mattress. So the in-place bed clips (tools/bed_transition_corrections.py,
SUB01_<Role>.corrected.in_place.glb) get their measured horizontal root path back as an offset of the BODY MESH
relative to the capsule, while the capsule stays on the floor:

- LyingDown: the capsule stays at the bedside approach point (where WalkToBed/TurnInPlace left it); the mesh
  offset follows the LieDown root path sampled at the clip time the hands proxy actually evaluated.
- Asleep: the body is anchored in the world; the capsule (invisible, camera on the head bone) walks by
  CharacterMovement input on the floor to the GetUp's measured end point, and the mesh offset is recomputed
  every tick so the body does not move. Collision is CharacterMovement's own; it never enters the bed.
- GettingUp: the mesh offset follows the GetUp root path; at its last frame the offset is ~0 (the capsule is
  already under the standing body), so the mesh goes back to the renderer's own offset ("then return").
- If the bed's collision stops the capsule within RESIDUAL_MAX_CM of that end point (he stands up close to the
  edge; the capsule is radius 16-17), the residual body offset decays linearly with the distance the capsule then
  walks natively (over ABSORB_CM): a foot slide of at most RESIDUAL_MAX_CM / ABSORB_CM per cm walked, logged as
  SUB01_LIFE_ROOT_RETURN_SHORT. Farther than that, movement stays locked and SUB01_LIFE_ROOT_RETURN_BLOCKED is
  logged: the body is never snapped to the capsule.
No SetActorLocation, no teleport, no actor placement, no bone writes. Actor yaw is held (bUseControllerRotationYaw
off) while the root path is active, so mouse look cannot swing the body around the capsule.

The path file, <project>/private-audit/native-life-root-paths.json, is staged by `stage-paths` only when every
role's in-place clip hash equals the inventory candidate that role binds (life.role_bindings), and the C++ loader
also checks each role's sample count against the imported clip's play length. Without it the adapter logs
SUB01_LIFE_ROOT_MOTION_REFUSED and the 67af5f8 behaviour is unchanged (in-place clips would then lie down on the
spot: the bed roles must not be validated without it).

    python3 tools/unreal_bed_root_motion.py install <project>/Source/Sub01HomeLab     # after life install
    python3 tools/unreal_bed_root_motion.py stage-paths ROOT_PATHS.json INVENTORY.json UNREAL_LIFE_IMPORT.json <project>
    python3 tools/unreal_bed_root_motion.py config INVENTORY.json UNREAL_LIFE_IMPORT.json OUT.ini
        (= unreal_life_clips_runtime config, plus a visible provenance comment per bound derived_library_asset)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unreal_life_clips_runtime as life  # noqa: E402  (read-only import)

ROOT_PATH_SCHEMA = 'sub01.bed-mesh-root-path.v1'
ROOT_PATH_FILE = 'native-life-root-paths.json'
ARRIVE_CM = 2.0
RETURN_TIMEOUT_S = 8.0
RETURN_MAX_INPUT = 0.5          # x MaxWalkSpeed 140 = 70 cm/s at most, while asleep
RESIDUAL_MAX_CM = 20.0          # a capsule stopped by the bed this close to the body's end point still counts as returned
ABSORB_CM = 60.0                # ... and that residual decays over the first 60 cm the capsule walks afterwards

FIELDS = r'''
 // Bed mesh root motion (tools/unreal_bed_root_motion.py): the in-place bed clips' measured root path drives the
 // body mesh offset while the capsule stays on the floor; never an actor placement.
 void LoadLifeRootPath(); void UpdateLifeRootMotion(class USub01HomeHandsInstance* Instance);
 FVector2D SampleLifeRootPath(FName Role,float Seconds,bool Loop) const;
 TMap<FName,TArray<FVector2D>> LifeRootPath; float LifeRootFps=30;
 bool LifeRootReady=false,LifeRootActive=false,LifeRootReturning=false,LifeRootArrived=false,LifeRootBlockedLogged=false,LifeRootRefusedLogged=false;
 FVector LifeRootOrigin=FVector::ZeroVector; float LifeRootYaw=0; double LifeRootReturnStarted=0; FVector2D LifeRootLast=FVector2D::ZeroVector;
 bool LifeRootAbsorbing=false; FVector LifeRootAbsorbOffset=FVector::ZeroVector,LifeRootPrev=FVector::ZeroVector; float LifeRootWalked=0;
'''

LOAD_CALL = ' LoadLifeRootPath();\n'

LOCK_OLD = 'bool ASub01HomeCharacter::LifeMovementLocked() const{return !LifeOut.MovementAllowed;}'
LOCK_NEW = ('bool ASub01HomeCharacter::LifeMovementLocked() const{return !LifeOut.MovementAllowed||LifeRootReturning;}'
            ' // + root return (unreal_bed_root_motion.py)')

UPDATE_CALL = ' UpdateLifeRootMotion(Instance);\n'

# The life LIVE_GATE stops the capsule every tick while locked; the root return must be able to walk it.
GATE_OLD = ' if(LifeMovementLocked()){GetCharacterMovement()->StopMovementImmediately();'
GATE_NEW = ' if(LifeMovementLocked()){if(!LifeRootReturning)GetCharacterMovement()->StopMovementImmediately();'

METHODS = r'''
void ASub01HomeCharacter::LoadLifeRootPath(){
 LifeRootPath.Empty();LifeRootReady=false;
 FString Text;TSharedPtr<FJsonObject> Doc;const TSharedPtr<FJsonObject>* Roles=nullptr;FString Schema;
 const FString File=FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit"),TEXT("@@ROOT_PATH_FILE@@"));
 if(!FFileHelper::LoadFileToString(Text,*File)||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Doc)||!Doc.IsValid()
    ||!Doc->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("@@ROOT_PATH_SCHEMA@@")||!Doc->TryGetObjectField(TEXT("roles"),Roles)){
  UE_LOG(LogTemp,Warning,TEXT("SUB01_LIFE_ROOT_MOTION_REFUSED no valid %s; bed clips keep the 67af5f8 behaviour"),*File);return;}
 double Fps=30;Doc->TryGetNumberField(TEXT("fps"),Fps);LifeRootFps=float(Fps);bool Valid=Fps>0;
 for(const TCHAR* Role:{TEXT("LieDown"),TEXT("SleepLoop"),TEXT("GetUp")}){
  const TSharedPtr<FJsonObject>* R=nullptr;const TArray<TSharedPtr<FJsonValue>> *F=nullptr,*Ri=nullptr;
  if(!(*Roles)->TryGetObjectField(Role,R)||!(*R)->TryGetArrayField(TEXT("forward_cm"),F)||!(*R)->TryGetArrayField(TEXT("right_cm"),Ri)||F->Num()!=Ri->Num()||F->Num()<2){Valid=false;break;}
  TArray<FVector2D>& Path=LifeRootPath.Add(FName(Role));
  for(int32 I=0;I<F->Num();++I)Path.Add(FVector2D((*F)[I]->AsNumber(),(*Ri)[I]->AsNumber()));
  // The path must belong to the imported clip: same length (one sample per frame).
  UAnimSequence* Clip=LifeClips.FindRef(FName(Role));
  if(!Clip||FMath::Abs(Clip->GetPlayLength()-(Path.Num()-1)/LifeRootFps)>2.f/30.f){Valid=false;break;}
 }
 LifeRootReady=Valid;
 if(!Valid){LifeRootPath.Empty();UE_LOG(LogTemp,Warning,TEXT("SUB01_LIFE_ROOT_MOTION_REFUSED path does not match the imported LieDown/SleepLoop/GetUp"));}
 else UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_ROOT_MOTION_READY fps=%.1f getUpEnd=%s"),LifeRootFps,*LifeRootPath[FName(TEXT("GetUp"))].Last().ToString());
}
FVector2D ASub01HomeCharacter::SampleLifeRootPath(FName Role,float Seconds,bool Loop) const{
 const TArray<FVector2D>* Path=LifeRootPath.Find(Role);if(!Path||Path->Num()<2)return LifeRootLast;
 const float Last=float(Path->Num()-1);float X=Seconds*LifeRootFps;
 X=Loop?FMath::Fmod(FMath::Max(X,0.f),Last):FMath::Clamp(X,0.f,Last);
 const int32 A=FMath::Clamp(FMath::FloorToInt(X),0,Path->Num()-1),B=FMath::Min(A+1,Path->Num()-1);
 return FMath::Lerp((*Path)[A],(*Path)[B],X-A);
}
void ASub01HomeCharacter::UpdateLifeRootMotion(USub01HomeHandsInstance* Instance){
 const bool InBed=LifeOut.Phase==ESub01LifePhase::LyingDown||LifeOut.Phase==ESub01LifePhase::Asleep||LifeOut.Phase==ESub01LifePhase::GettingUp;
 const bool OnCapsule=FirstPersonBody&&FirstPersonBody->GetAttachParent()==GetRootComponent();
 if(LifeRootAbsorbing){
  // After the get-up, a short residual (the capsule stopped by the bed's collision before the body's end point)
  // decays with the distance the capsule actually walks: never a jump (RESIDUAL_MAX_CM over ABSORB_CM, unreal_bed_root_motion.py).
  const FVector Now=GetActorLocation();LifeRootWalked+=FVector2D(Now.X-LifeRootPrev.X,Now.Y-LifeRootPrev.Y).Size();LifeRootPrev=Now;
  const float Keep=FMath::Clamp(1.f-LifeRootWalked/@@ABSORB_CM@@,0.f,1.f);
  if(InBed||!OnCapsule||Keep<=0.f){
   LifeRootAbsorbing=false;LifeRootActive=false;bUseControllerRotationYaw=true;
   UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_ROOT_END absorbed=%.2fcm walked=%.1fcm"),LifeRootAbsorbOffset.Size(),LifeRootWalked);
  }else FirstPersonBody->SetRelativeLocation(HandsBaseOffset+LifeRootAbsorbOffset*Keep);
  return;
 }
 if(!LifeRootActive){
  if(!InBed)return;
  if(!LifeRootReady||!Instance||!OnCapsule){
   if(!LifeRootRefusedLogged)UE_LOG(LogTemp,Warning,TEXT("SUB01_LIFE_ROOT_MOTION_REFUSED ready=%d body_on_capsule=%d"),LifeRootReady?1:0,OnCapsule?1:0);
   LifeRootRefusedLogged=true;return;}
  // The capsule's own location and yaw when lying down starts: the approach point, after the turn in place.
  LifeRootActive=true;LifeRootArrived=false;LifeRootBlockedLogged=false;LifeRootOrigin=GetActorLocation();LifeRootYaw=GetActorRotation().Yaw;
  bUseControllerRotationYaw=false;LifeRootLast=FVector2D::ZeroVector;
  UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_ROOT_BEGIN origin=%s yaw=%.2f"),*LifeRootOrigin.ToString(),LifeRootYaw);
 }
 // The root path at the clip time the proxy actually evaluated (never the requested time).
 static const TCHAR* Names[]={TEXT(""),TEXT("Walk"),TEXT("Idle"),TEXT("LieDown"),TEXT("SleepLoop"),TEXT("GetUp")};
 if(InBed&&uint8(LifeOut.Clip)>=uint8(ESub01LifeClip::LieDown)){
  const FName Role(Names[uint8(LifeOut.Clip)]);UAnimSequence* Clip=LifeClips.FindRef(Role);
  if(Clip&&Instance&&Instance->LifeEvaluatedSequence==Clip&&Instance->LifeEvaluatedTime>=0)
   LifeRootLast=SampleLifeRootPath(Role,Instance->LifeEvaluatedTime,LifeOut.Clip==ESub01LifeClip::SleepLoop);
 }
 const FRotator Yaw(0,LifeRootYaw,0);
 const FVector Body=LifeRootOrigin+Yaw.RotateVector(FVector(LifeRootLast.X,LifeRootLast.Y,0));
 const FVector2D End=LifeRootPath[FName(TEXT("GetUp"))].Last();
 const FVector Target=LifeRootOrigin+Yaw.RotateVector(FVector(End.X,End.Y,0));
 const FVector Here=GetActorLocation();const FVector2D ToTarget(Target.X-Here.X,Target.Y-Here.Y);
 // Return: while asleep (and until arrived), the invisible capsule walks on the floor to the get-up's end point.
 const bool MayReturn=LifeOut.Phase==ESub01LifePhase::Asleep||LifeOut.Phase==ESub01LifePhase::GettingUp||!InBed;
 if(MayReturn&&!LifeRootArrived){
  if(ToTarget.Size()>@@ARRIVE_CM@@){
   if(!LifeRootReturning){LifeRootReturning=true;LifeRootReturnStarted=FPlatformTime::Seconds();}
   if(GetCharacterMovement()->MovementMode==MOVE_None)GetCharacterMovement()->SetMovementMode(MOVE_Walking);
   AddMovementInput(FVector(ToTarget.X,ToTarget.Y,0).GetSafeNormal(),FMath::Clamp(ToTarget.Size()/45.f,.15f,@@RETURN_MAX_INPUT@@f));
   const double Since=FPlatformTime::Seconds()-LifeRootReturnStarted;
   const bool Stuck=(Since>1.0&&GetVelocity().Size2D()<1.f)||Since>@@RETURN_TIMEOUT_S@@;
   if(Stuck&&ToTarget.Size()<=@@RESIDUAL_MAX_CM@@){
    // The bed's own collision stopped the capsule just short of the body (he stands up close to the edge).
    LifeRootArrived=true;LifeRootReturning=false;GetCharacterMovement()->StopMovementImmediately();if(InBed)GetCharacterMovement()->DisableMovement();
    UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_ROOT_RETURN_SHORT remaining=%.1fcm; absorbed by the first native steps"),ToTarget.Size());
   }else if(Stuck&&!LifeRootBlockedLogged){
    UE_LOG(LogTemp,Warning,TEXT("SUB01_LIFE_ROOT_RETURN_BLOCKED remaining=%.1fcm target=%s; the body stays where it is, movement stays locked"),ToTarget.Size(),*Target.ToString());
    LifeRootBlockedLogged=true;}
  }else{
   LifeRootArrived=true;LifeRootReturning=false;GetCharacterMovement()->StopMovementImmediately();
   if(InBed)GetCharacterMovement()->DisableMovement();
   UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_ROOT_RETURNED capsule=%s target=%s"),*GetActorLocation().ToString(),*Target.ToString());
  }
 }
 // The body: world-anchored at the root path, expressed relative to wherever the capsule is now.
 const FVector Offset=GetActorRotation().UnrotateVector(FVector(Body.X-GetActorLocation().X,Body.Y-GetActorLocation().Y,0));
 if(OnCapsule)FirstPersonBody->SetRelativeLocation(HandsBaseOffset+Offset);
 if(!InBed&&LifeRootArrived){
  if(Offset.Size()<=@@ARRIVE_CM@@){
   LifeRootActive=false;LifeRootReturning=false;bUseControllerRotationYaw=true;
   if(OnCapsule)FirstPersonBody->SetRelativeLocation(HandsBaseOffset);
   UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_ROOT_END residual=%.2fcm"),Offset.Size());
  }else{LifeRootAbsorbing=true;LifeRootAbsorbOffset=Offset;LifeRootWalked=0;LifeRootPrev=GetActorLocation();LifeRootReturning=false;}
 }
}
'''


# (file key, anchor, replacement). Anchors are the life adapter's own installed text; each must occur exactly once.
EDITS = [
    ('header', ' FSub01LifeMachine LifeMachine; FSub01LifeOutputs LifeOut;',
     FIELDS + ' FSub01LifeMachine LifeMachine; FSub01LifeOutputs LifeOut;'),
    ('cpp', ' UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_READY', LOAD_CALL + ' UE_LOG(LogTemp,Display,TEXT("SUB01_LIFE_READY'),
    ('cpp', LOCK_OLD, LOCK_NEW),
    ('cpp', GATE_OLD, GATE_NEW),
    ('cpp', ' // In bed the eye follows the captured Head bone;', UPDATE_CALL + ' // In bed the eye follows the captured Head bone;'),
]


def methods() -> str:
    return (METHODS.replace('@@ROOT_PATH_FILE@@', ROOT_PATH_FILE).replace('@@ROOT_PATH_SCHEMA@@', ROOT_PATH_SCHEMA)
            .replace('@@ARRIVE_CM@@', f'{ARRIVE_CM:.1f}f').replace('@@RETURN_MAX_INPUT@@', f'{RETURN_MAX_INPUT:.2f}')
            .replace('@@RETURN_TIMEOUT_S@@', f'{RETURN_TIMEOUT_S:.1f}')
            .replace('@@RESIDUAL_MAX_CM@@', f'{RESIDUAL_MAX_CM:.1f}f').replace('@@ABSORB_CM@@', f'{ABSORB_CM:.1f}f'))


def install(sources: dict) -> dict:
    """Apply to staged sources that already carry the life adapter ({'header','cpp',...})."""
    out = dict(sources)
    if 'FSub01LifeMachine LifeMachine;' not in out['header']:
        raise ValueError('install unreal_life_clips_runtime first (the root motion extends its bed phases)')
    if 'LoadLifeRootPath();' in out['header']:
        raise ValueError('Bed root motion is already installed')
    for key, anchor, replacement in EDITS:
        if out[key].count(anchor) != 1:
            raise ValueError(f'Bed root motion anchor not unique in {key}: {anchor[:60]!r}')
        out[key] = out[key].replace(anchor, replacement)
    out['cpp'] += methods()
    return out


def install_module(module: Path) -> None:
    module = Path(module)
    patched = install({key: (module / name).read_text() for key, name in life.SOURCE_FILES.items()})
    for key, name in life.SOURCE_FILES.items():
        (module / name).write_text(patched[key])


# ---------------------------------------------------------------- the path file (server, root)
def validate_paths(paths: dict, inventory: dict, import_report: dict) -> dict:
    """The root path file, only if every bed role binds and binds exactly the clip the path was measured on."""
    if paths.get('schema') != ROOT_PATH_SCHEMA:
        raise ValueError('RootPathInvalid: schema')
    roles = life.role_bindings(inventory, import_report)
    out = {'schema': ROOT_PATH_SCHEMA, 'fps': paths['fps'], 'roles': {}}
    for role in life.BED_ROLES:
        r, bind = paths.get('roles', {}).get(role), roles[role]
        if not bind['bound']:
            raise ValueError(f'RootPathRefused: {role} is not bound ({bind["refusal"]})')
        if not r or r.get('clip_sha256_in_place') != bind['source_sha256']:
            raise ValueError(f'RootPathRefused: {role} path was measured on another clip than the bound one')
        if len(r['forward_cm']) != len(r['right_cm']) or len(r['forward_cm']) < 2:
            raise ValueError(f'RootPathInvalid: {role} samples')
        out['roles'][role] = {k: r[k] for k in ('clip_sha256_in_place', 'forward_cm', 'right_cm')}
    return out


def stage_paths(paths_file: Path, inventory_file: Path, import_file: Path, project: Path) -> Path:
    doc = validate_paths(json.loads(Path(paths_file).read_text()), json.loads(Path(inventory_file).read_text()),
                         json.loads(Path(import_file).read_text()))
    target = Path(project) / 'private-audit' / ROOT_PATH_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(doc, sort_keys=True) + '\n')
    return target


def config_with_labels(inventory: dict, import_report: dict):
    """life.config_fragment, plus one comment per bound derived_library_asset so the label stays visible."""
    text, refusals = life.config_fragment(inventory, import_report)
    if not text:
        return text, refusals
    roles = life.role_bindings(inventory, import_report)
    notes = []
    for role, bind in roles.items():
        if not bind['bound']:
            continue
        row = next(c for c in inventory['candidates'] if c.get('role') == role and c.get('sha256') == bind['source_sha256'])
        if row.get('provenance') == 'derived_library_asset':
            label = (row.get('provenance_label') or {}).get('label')
            if label != 'derived_library_asset':
                raise ValueError(f'{role}: derived clip bound without its visible label')
            notes.append(f'; SUB01 provenance {role}=derived_library_asset ({bind["source"]}): '
                         'preview/mh-motion clips retargeted via mh_retarget.mjs; capture method undocumented')
    return text + ''.join(n + '\n' for n in notes), refusals


def main(argv):
    if len(argv) == 2 and argv[0] == 'install':
        install_module(Path(argv[1]))
        print('Bed root motion installed into staged sources (after the life adapter); not compiled or running yet.')
        return 0
    if len(argv) == 5 and argv[0] == 'stage-paths':
        print(stage_paths(*map(Path, argv[1:])))
        return 0
    if len(argv) == 4 and argv[0] == 'config':
        text, refusals = config_with_labels(json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text()))
        if text:
            Path(argv[3]).write_text(text)
        print(json.dumps({'written': bool(text), 'refusals': refusals}, indent=2))
        return 0 if text else 3
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
