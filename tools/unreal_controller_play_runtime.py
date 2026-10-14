"""TRIAL native adapter: SUB01 plays Minecraft seated on the sofa holding the controller in both hands.

verified: false. Owns this file only; nothing is staged by default and no renderer-owned generator is
edited. The runtime owner applies `install_module()` to already staged sources (additions only, unique
anchors, refuses when anything is missing or already installed). Until then the live home is unchanged.

What the native fragment does, only with MEASURED evidence:
- binds the captured Gaming clip (owner skeleton) through the renderer's own gate: the clip must be on
  the SAME USkeleton and listed in ValidatedHandsPostures (`+ValidatedHandsPostures=Gaming`, written by
  `config_fragment()` only when the evidence passes); SetHandsPosture(TEXT("Walk")) must succeed first
  (it is never bypassed; the renderer's whitelist is not edited), then the clip replaces the renderer's
  choice the same way the seat and life adapters do;
- shows the actual controller static mesh ONLY while playing, rigidly at the right Hand socket with the
  solved grip offset (socket rotation and location, imported bone scale excluded: the phone-review rule);
- places the BODY component (never the actor/capsule) on the measured sofa seat from the evidence body
  offset; the capsule stays standing at the measured approach outside the sofa; the camera rides the
  captured Head socket while playing and is restored after;
- leaves Minecraft input to the existing plumbing (TickMinecraftTVInput -> /api/home/minecraft/input ->
  games/minecraft/native_input.cjs). It sends no input of its own;
- exposes ControllerPlayReady(): true only when the measured sofa surface, sofa seat contact, capsule
  clearance and every-frame two-hand grip gates all passed and the clip/mesh are bound.

Python side:
    python tools/unreal_controller_play_runtime.py evidence <UE project> GRIP_REPORT.json SOFA_CONTACT.json
    python tools/unreal_controller_play_runtime.py config <UE project> IMPORT_REPORT.json OUT.ini
    python tools/unreal_controller_play_runtime.py install <project>/Source/Sub01HomeLab
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_unreal_seat_contact as seat_contact  # noqa: E402

ROLE = 'Gaming'
# The native side plays the DERIVED grip clip (tools/derive_controller_grip_clip.py), never the raw retarget.
CLIP_OBJECT_PATH = '/Game/Sub01Hands/Play/SUB01_GamingGrip.SUB01_GamingGrip'
DERIVED_SCHEMA, DERIVED_LABEL = 'sub01.controller-grip-derived.v1', 'derived_from_capture'
GAMING_OWNER_GLB_SHA256 = 'f8b00ce59716683d9ea511ccf1d38d311446ba6668afdc351d98abe4988f6c09'   # root's owner-skeleton retarget
CLIP_FRAMES = 152
FINGER_DELTA_MAX_DEG = 15.0
RUNTIME_PROOF = 'native-controller-play-runtime-proof.json'
RUNTIME_PROOF_SCHEMA = 'sub01.native-controller-play-runtime-proof.v1'
# Root's tools/unreal_import_controller_prop.py writes the imported physical assembly (contact shadow excluded) here.
CONTROLLER_ASSET_RECEIPT = 'native-controller-asset.json'
CONTROLLER_ASSET_SCHEMA = 'sub01.native-controller-asset.v1'
CONTROLLER_SOURCE_SHA256 = 'c034a1444711a44f0726e7264b1e2e2b47b1bbdba0e5dd615eef27001a4717e4'
GAMING_FBX_SHA256 = '84dfc60ab9e13b9c896e89def81478a5e47f45b80cc3d8902c5b8a0ae8d8fc7f'   # owner's private Mixamo Gaming.fbx
GLTF_FIRST_KEY_S = 1 / 30          # Gaming GLB keys start at 1/30 s: native AnimSequence t = glTF t - 1/30 (native 4 s = glTF 4.033333 s)
FIXED_OFFSET_TOLERANCE = (.3, 1.)  # cm, deg: a searched per-frame grip must be this close to one socket offset
EVIDENCE_SCHEMA = 'sub01.native-controller-play-evidence.v1'
SOFA_REPORT = 'native-sofa-surface.json'
EVIDENCE = 'native-controller-play-evidence.json'
MIN_SEAT_AREA_CM2 = 4000.0         # the two authored seat cushions are ~5,800 cm2 each; an arm top is not a seat
APPROACH_TOLERANCE_CM, YAW_TOLERANCE_DEG = 12.0, 5.0
CAPSULE_RADIUS_CM = 17.0
SOFA_REGIONS = seat_contact.SEAT_REGIONS + seat_contact.SOLE_REGIONS
CHARACTER_SECTION = '[/Script/Sub01HomeLab.Sub01HomeCharacter]'


def play_id(text: str) -> int:
    """FNV-1a over the low byte of each character, identical to Sub01ControllerPlayId()."""
    value = 1469598103934665603
    for char in text:
        value ^= ord(char) & 0xFF
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def _finite(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


# ---------------------------------------------------------------- gates (all measured, none assumed)
def sofa_seat_triangles(sofa: dict):
    """World triangles (cm) of the measured native sofa seat; refuses anything unmeasured."""
    if sofa.get('errors') != []:
        raise ValueError('SofaUnmeasured: the native sofa report has errors or no error list')
    tris = []
    for section in sofa.get('sofa', {}).get('sections', []):
        verts, faces = section.get('vertices_world_cm'), section.get('seat_surface', {}).get('triangle_indices')
        if verts is None or faces is None:
            continue
        for face in faces:
            if len(face) != 3 or any(not isinstance(i, int) or not 0 <= i < len(verts) or len(verts[i]) != 3 or not _finite(*verts[i]) for i in face):
                raise ValueError('SofaUnmeasured: malformed seat triangle')
            tris.extend(verts[i] for i in face)
    if not tris:
        raise ValueError('SofaUnmeasured: no measured seat triangles')
    area = 0.
    for a, b, c in zip(tris[0::3], tris[1::3], tris[2::3]):
        u, v = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
        area += .5 * math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2 + (u[0] * v[1] - u[1] * v[0]) ** 2)
    if area < MIN_SEAT_AREA_CM2:
        raise ValueError(f'SofaUnmeasured: seat area {area:.0f} cm2 is not a sofa seat')
    return tris, area


def validate_sofa_contact(data: dict):
    """Seat rule of validate_unreal_seat_contact (local support patch + non-penetration per region), over the
    WHOLE captured Gaming clip at >= 30 Hz against the measured sofa seat and floor."""
    rows = data.get('samples', [])
    duration = data.get('clip_duration_s')
    if not _finite(duration) or duration <= 0 or len(rows) < int(duration * 30):
        raise ValueError('SofaContactIncomplete: samples must cover the whole clip at >= 30 Hz')
    worst = {}
    for row in rows:
        regions = {r['region']: r for r in row.get('regions', [])}
        if set(regions) != set(SOFA_REGIONS) or row.get('invalidInfluences') != 0:
            raise ValueError('SofaContactIncomplete: buttocks, posterior thighs, both soles and valid influences required')
        for name, r in regions.items():
            low, high = seat_contact.band(name)
            if not _finite(r.get('minGapCm'), r.get('bandVertices'), r.get('overSurfaceVertices')):
                raise ValueError('SofaContactIncomplete: nonfinite metric')
            if r['overSurfaceVertices'] < seat_contact.MIN_PATCH_VERTICES:
                raise ValueError(f'{name}: not over its surface at {row.get("time")}')
            if r['minGapCm'] < low:
                raise ValueError(f'{name}: penetration {r["minGapCm"]:.3f} cm below {low} cm at {row.get("time")}')
            if r['minGapCm'] > high or r['bandVertices'] < seat_contact.MIN_SUPPORT_VERTICES:
                raise ValueError(f'{name}: no support patch (lowest {r["minGapCm"]:.3f} cm, {r["bandVertices"]} vertices) at {row.get("time")}')
            w = worst.setdefault(name, {'min_gap_cm': math.inf, 'min_band_vertices': math.inf})
            w['min_gap_cm'] = min(w['min_gap_cm'], r['minGapCm'])
            w['min_band_vertices'] = min(w['min_band_vertices'], r['bandVertices'])
    return {'samples': len(rows), 'worst': worst, 'passed': True}


def native_time(gltf_t: float) -> float:
    return float(gltf_t) - GLTF_FIRST_KEY_S


def gltf_time(native_t: float) -> float:
    return float(native_t) + GLTF_FIRST_KEY_S


def validate_search(report: dict):
    """Penetration-aware search (option 1): every frame must pass, the right-hand grip must be ONE socket offset, and
    the clip the native side plays must be the derived clip with the bounded IK baked in (finger locals unchanged)."""
    s = report['summary']
    if s['frames'] < 2 or s['frames_passing'] != s['frames']:
        raise ValueError(f'GripFailed: penetration-aware search passes {s["frames_passing"]}/{s["frames"]} frames')
    v = s.get('right_grip_variation', {})
    if not (v.get('max_translation_cm', 1e9) <= FIXED_OFFSET_TOLERANCE[0] and v.get('max_rotation_deg', 1e9) <= FIXED_OFFSET_TOLERANCE[1]):
        raise ValueError('GripFailed: the searched right-hand grip varies; no single socket offset')
    if report.get('clip', {}).get('ik_baked') is not True:
        raise ValueError('GripUnmeasured: the bounded arm IK must be baked into a derived clip that the native side plays')
    import fit_controller_grip as fit  # noqa: E402  (same directory)
    return {'frames': s['frames'], 'controller_in_right_hand_gltf': fit.grip_variation(report['per_frame'])['mean_controller_in_hand']}


def validate_derived(report: dict):
    """The derived grip clip report (tools/derive_controller_grip_clip.py): labelled, every frame passing, one fixed
    right-socket offset, bounded finger deltas, made from root's owner-skeleton Gaming retarget."""
    if report.get('label') != DERIVED_LABEL:
        raise ValueError('GripUnmeasured: the clip is not labelled derived_from_capture')
    if report.get('source_clip', {}).get('sha256') != GAMING_OWNER_GLB_SHA256:
        raise ValueError('GripUnmeasured: not derived from the owner-skeleton Gaming capture')
    frames = report.get('frames')
    rows = report.get('per_frame', [])
    if report.get('all_frames_pass') is not True or frames != CLIP_FRAMES or len(rows) != frames or not all(r.get('pass') is True for r in rows) \
            or report.get('frames_passing') != frames:
        raise ValueError(f'GripFailed: derived clip passes {report.get("frames_passing")}/{frames} frames (all_frames_pass required)')
    if report.get('fixed_offset', {}).get('holds') is not True:
        raise ValueError('GripFailed: no single fixed right-socket controller offset')
    if not report.get('finger_deltas_deg', {}).get('max_abs_deg', 1e9) <= FINGER_DELTA_MAX_DEG:
        raise ValueError('GripFailed: finger deltas exceed the bound')
    if report.get('controller', {}).get('oversized') is not False or not report.get('output_glb_sha256'):
        raise ValueError('GripUnmeasured: controller size or derived GLB identity missing')
    return {'frames': frames, 'controller_in_right_hand_gltf': report['fixed_offset']['controller_in_right_hand_gltf'],
            'grip_clip_sha256': report['output_glb_sha256']}


def validate_grip(report: dict):
    """Native play needs the DERIVED clip report; raw-capture fits and searches are diagnostics and are refused."""
    if report.get('schema') == DERIVED_SCHEMA:
        return validate_derived(report)
    if report.get('schema') != 'sub01.controller-grip-trial.v1':
        raise ValueError('GripUnmeasured: not a controller grip report')
    if report.get('mode') == 'penetration_aware_joint_search':
        if report.get('clip', {}).get('source_fbx_sha256') != GAMING_FBX_SHA256:
            raise ValueError('GripUnmeasured: the fit is not of the owner\'s captured Gaming clip')
        return validate_search(report)
    if report.get('clip', {}).get('source_fbx_sha256') != GAMING_FBX_SHA256:
        raise ValueError('GripUnmeasured: the fit is not of the owner\'s captured Gaming clip')
    if report.get('seated', {}).get('seated') is not True:
        raise ValueError('GripUnmeasured: the captured clip is not seated in every frame')
    s = report['fixed']['summary']
    frames = s['frames']
    if frames < 2 or s['frames_full_grip'] != frames:
        raise ValueError(f'GripFailed: full two-hand grip in {s["frames_full_grip"]}/{frames} frames')
    for side in ('left', 'right'):
        if s[side]['palm_support_patch_frames'] != frames or s[side]['frames_with_penetration']:
            raise ValueError(f'GripFailed: {side} palm patch/penetration')
    X = report['fixed']['controller_in_right_hand']
    return {'frames': frames, 'controller_in_right_hand_gltf': X}


def ue_grip(X):
    """glTF hand-frame 4x4 (metres) -> UE socket-frame offset (cm) and quaternion (x,y,z,w).

    Contract of export_seat_fit_source.py: UE = 100 * (x, z, y). A reflection P conjugates rotations into
    proper rotations: R_ue = P R P. Unverified for the static-mesh import until root's import receipt.
    """
    P = [[1, 0, 0], [0, 0, 1], [0, 1, 0]]
    R = [[sum(P[i][k] * X[k][m] * 1 for k in range(3)) for m in range(3)] for i in range(3)]
    R = [[sum(R[i][m] * P[m][j] for m in range(3)) for j in range(3)] for i in range(3)]
    t = [100 * X[0][3], 100 * X[2][3], 100 * X[1][3]]
    w = math.sqrt(max(0., 1 + R[0][0] + R[1][1] + R[2][2])) / 2
    if w > 1e-6:
        q = [(R[2][1] - R[1][2]) / (4 * w), (R[0][2] - R[2][0]) / (4 * w), (R[1][0] - R[0][1]) / (4 * w), w]
    else:
        i = max(range(3), key=lambda k: R[k][k])
        j, k = (i + 1) % 3, (i + 2) % 3
        s = math.sqrt(max(0., 1 + R[i][i] - R[j][j] - R[k][k])) * 2
        q = [0., 0., 0., (R[k][j] - R[j][k]) / s]
        q[i], q[j], q[k] = s / 4, (R[j][i] + R[i][j]) / s, (R[k][i] + R[i][k]) / s
    return t, q


def capsule_clearance(approach, footprint_min, footprint_max, radius=CAPSULE_RADIUS_CM):
    dx = max(footprint_min[0] - approach[0], 0., approach[0] - footprint_max[0])
    dy = max(footprint_min[1] - approach[1], 0., approach[1] - footprint_max[1])
    return math.hypot(dx, dy) - radius


def build_evidence(sofa_text: str, grip: dict, contact: dict, placement: dict) -> dict:
    """Evidence the native side reads. `accepted` is computed from the gates; never written by hand.

    placement: {"approach_cm":[x,y], "yaw_deg":yaw, "body_offset_cm":[x,y,z], "body_yaw_deg":yaw,
                "sofa_footprint_cm":{"min":[x,y],"max":[x,y]}}  (measured on the server, cm, UE world)
    """
    sofa = json.loads(sofa_text)
    _, area = sofa_seat_triangles(sofa)
    g = validate_grip(grip)
    c = validate_sofa_contact(contact)
    a, yaw, body, body_yaw = (placement.get(k) for k in ('approach_cm', 'yaw_deg', 'body_offset_cm', 'body_yaw_deg'))
    fp = placement.get('sofa_footprint_cm', {})
    if not (isinstance(a, list) and len(a) == 2 and isinstance(body, list) and len(body) == 3 and _finite(*a, *body, yaw, body_yaw)
            and isinstance(fp.get('min'), list) and isinstance(fp.get('max'), list) and _finite(*fp['min'], *fp['max'])):
        raise ValueError('PlacementMissing: approach/yaw/body offset/footprint must be finite measured numbers')
    clearance = capsule_clearance(a, fp['min'], fp['max'])
    if clearance <= 0:
        raise ValueError(f'CapsuleInsideSofa: standing capsule overlaps the sofa footprint by {-clearance:.2f} cm')
    if 'grip_clip_sha256' not in g:
        raise ValueError('GripUnmeasured: native play needs the derived grip clip report (the raw capture never holds the controller)')
    t, q = ue_grip(g['controller_in_right_hand_gltf'])
    return {'schema': EVIDENCE_SCHEMA, 'clip_object_path': CLIP_OBJECT_PATH, 'grip_clip_sha256': g['grip_clip_sha256'], 'label': DERIVED_LABEL, 'sofa_revision': str(play_id(sofa_text)), 'seat_area_cm2': area,
            'approach_cm': a, 'yaw_deg': yaw, 'body_offset_cm': body, 'body_yaw_deg': body_yaw,
            'capsule_clearance_cm': clearance, 'grip_offset_cm': t, 'grip_rotation_xyzw': q,
            'grip_frames': g['frames'], 'grip_report_sha256': hashlib.sha256(json.dumps(grip, sort_keys=True).encode()).hexdigest(),
            'seat_contact': c, 'time_mapping': 'native AnimSequence t = glTF key t - 1/30 s', 'grip_gates_passed': True, 'seat_contact_passed': True, 'accepted': True,
            'verified': False, 'note': 'Measured gates passed; visual/first-person review and live Minecraft output remain separate.'}


def write_evidence(project: Path, grip_path: Path, contact_path: Path, placement_path: Path) -> Path:
    audit = Path(project) / 'private-audit'
    sofa = audit / SOFA_REPORT
    if not sofa.is_file():
        raise ValueError(f'SofaUnmeasured: {sofa} does not exist (run the native sofa audit first)')
    ev = build_evidence(sofa.read_text(), json.loads(Path(grip_path).read_text()), json.loads(Path(contact_path).read_text()),
                        json.loads(Path(placement_path).read_text()))
    out = audit / EVIDENCE
    out.write_text(json.dumps(ev, indent=2) + '\n')
    return out


def validate_runtime_proof(proof_text: str, evidence_text: str) -> dict:
    """Root's NATIVE runtime proof (mirror of the native loader): without it ControllerPlayReady() stays false.

    private-audit/native-controller-play-runtime-proof.json, written by root's native capture/contact run:
      {"schema": "sub01.native-controller-play-runtime-proof.v1", "accepted": true,
       "clip_object_path": CLIP_OBJECT_PATH, "evidence_revision": "<play_id(evidence text)>",
       "frames_measured": >=152, "frames_passing": == frames_measured,
       "native_capture": {"path": ..., "sha256": ...}, "max_penetration_cm": >= -0.3}
    """
    p, ev = json.loads(proof_text), json.loads(evidence_text)
    if p.get('schema') != RUNTIME_PROOF_SCHEMA or p.get('accepted') is not True:
        raise ValueError('RuntimeProofMissing: no accepted native runtime proof')
    if p.get('clip_object_path') != CLIP_OBJECT_PATH or p.get('evidence_revision') != str(play_id(evidence_text)):
        raise ValueError('RuntimeProofMissing: proof is for another clip or evidence revision')
    m, k = p.get('frames_measured'), p.get('frames_passing')
    if not _finite(m, k) or m < CLIP_FRAMES or k != m:
        raise ValueError(f'RuntimeProofFailed: native frames passing {k}/{m}')
    if not _finite(p.get('max_penetration_cm')) or p['max_penetration_cm'] < -0.3 or not p.get('native_capture', {}).get('sha256'):
        raise ValueError('RuntimeProofFailed: native penetration beyond the band or no native capture')
    return {'frames': m, 'grip_clip_sha256': ev.get('grip_clip_sha256')}


def config_fragment(project: Path, import_report: dict) -> tuple[str, dict]:
    """`+ValidatedHandsPostures=Gaming` only with accepted evidence on THIS sofa report and the exact import row."""
    audit = Path(project) / 'private-audit'
    refusals, ev = {}, {}
    try:
        sofa_text = (audit / SOFA_REPORT).read_text()
        ev = json.loads((audit / EVIDENCE).read_text())
        if ev.get('schema') != EVIDENCE_SCHEMA or ev.get('accepted') is not True or ev.get('sofa_revision') != str(play_id(sofa_text)):
            refusals['evidence'] = 'evidence not accepted for this sofa report'
    except (OSError, ValueError) as error:
        refusals['evidence'] = f'missing: {error}'
    rows = [r for r in import_report.get('clips', []) if r.get('role') == ROLE]
    want = ev.get('grip_clip_sha256') if isinstance(ev, dict) else None
    if len(rows) != 1 or rows[0].get('object_path') != CLIP_OBJECT_PATH or rows[0].get('same_existing_skeleton') is not True \
            or rows[0].get('source_fbx_sha256') != GAMING_FBX_SHA256 or not want or rows[0].get('derived_glb_sha256') != want:
        refusals['clip'] = f'expected one {CLIP_OBJECT_PATH} import of the derived grip GLB (evidence sha) on the existing owner USkeleton'
    if refusals:
        return '', refusals
    return CHARACTER_SECTION + f'\n+ValidatedHandsPostures={ROLE}\n', {}


# ---------------------------------------------------------------- native integration
CHARACTER_FIELDS = r'''
 // Controller play on the sofa (tools/unreal_controller_play_runtime.py). TRIAL, verified false.
 void LoadControllerPlay(); void UpdateControllerPlay(class USub01HomeHandsInstance* Instance,float Dt); bool ControllerPlayReady() const;
 UPROPERTY() TObjectPtr<UAnimSequence> ControllerPlayClip;
 UPROPERTY() TObjectPtr<UStaticMeshComponent> ControllerPlayProp;
 FName ControllerPlayHand,ControllerPlayHead; FVector ControllerPlayGripOffset=FVector::ZeroVector; FQuat ControllerPlayGripRotation=FQuat::Identity;
 FVector ControllerPlayBodyOffset=FVector::ZeroVector; float ControllerPlayBodyYaw=0; FVector2D ControllerPlayApproach=FVector2D::ZeroVector; float ControllerPlayYaw=0;
 bool ControllerPlayEvidence=false,ControllerPlayRuntimeProof=false,ControllerPlayActive=false,ControllerPlayLoggedReady=false; FString ControllerPlayRefusal=TEXT("not loaded");
'''

LIVE_GATE = (' // Playing on the sofa never walks off: the body leaves the seat first (next tick).\n'
             ' if(ControllerPlayActive&&LiveHomePath.Num()){GetCharacterMovement()->StopMovementImmediately();return;}\n')
LIVE_ANCHOR = ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus('
# The renderer's final rate assignment in Tick (its walk-rate expression changes between root revisions, so the anchor
# is the unique LINE that starts with this prefix; the call is inserted right after that line).
RATE_PREFIX = ' Instance->TargetRate=HandsPosture==TEXT("Walk")?'
RATE_ANCHOR = RATE_PREFIX.strip()

CHARACTER_METHODS = r'''
#include "Engine/StaticMesh.h"
static uint64 Sub01ControllerPlayId(const FString& Text){uint64 V=1469598103934665603ull;for(TCHAR C:Text){V^=uint64(uint8(C));V*=1099511628211ull;}return V;}
bool ASub01HomeCharacter::ControllerPlayReady() const{return ControllerPlayEvidence&&ControllerPlayRuntimeProof&&ControllerPlayClip&&ControllerPlayProp&&!ControllerPlayHand.IsNone()&&!ControllerPlayHead.IsNone();}
void ASub01HomeCharacter::LoadControllerPlay(){
 ControllerPlayEvidence=false;ControllerPlayClip=nullptr;
 USkeletalMesh* Mesh=FirstPersonBody?FirstPersonBody->GetSkeletalMeshAsset():nullptr;
 if(!Mesh){ControllerPlayRefusal=TEXT("no owner mesh");return;}
 // The renderer's gate: the captured clip on the SAME skeleton and listed in ValidatedHandsPostures, or nothing.
 auto* Clip=LoadObject<UAnimSequence>(nullptr,TEXT("@@CLIP@@"));
 if(!Clip)ControllerPlayRefusal=TEXT("ClipMissing");
 else if(Clip->GetSkeleton()!=Mesh->GetSkeleton())ControllerPlayRefusal=TEXT("SkeletonMismatch");
 else if(!ValidatedHandsPostures.Contains(FName(TEXT("@@ROLE@@"))))ControllerPlayRefusal=TEXT("NotValidated");
 else ControllerPlayClip=Clip;
 const auto& Ref=Mesh->GetRefSkeleton();
 for(int32 I=0;I<Ref.GetNum();++I){const FString N=Ref.GetBoneName(I).ToString();if(N.EndsWith(TEXT("RightHand")))ControllerPlayHand=Ref.GetBoneName(I);if(N.EndsWith(TEXT("Head")))ControllerPlayHead=Ref.GetBoneName(I);}
 // The actual controller mesh named by root's import receipt (physical assembly only; the baked shadow is excluded):
 // one component, hidden until play, no collision (it never pushes the pawn).
 FString AssetText,MeshPath,AssetSchema,AssetSource;TSharedPtr<FJsonObject> Asset;const TSharedPtr<FJsonObject>* Physical=nullptr;
 if(FFileHelper::LoadFileToString(AssetText,*FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit"),TEXT("@@ASSET_RECEIPT@@")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(AssetText),Asset)&&Asset.IsValid()
  &&Asset->TryGetStringField(TEXT("schema"),AssetSchema)&&AssetSchema==TEXT("@@ASSET_SCHEMA@@")&&Asset->TryGetStringField(TEXT("source_sha256"),AssetSource)&&AssetSource==TEXT("@@ASSET_SHA@@")
  &&Asset->TryGetObjectField(TEXT("physical_assembly"),Physical)&&(*Physical)->TryGetStringField(TEXT("mesh"),MeshPath)&&!MeshPath.Contains(TEXT("contact"),ESearchCase::IgnoreCase)){}
 else MeshPath.Empty();
 if(auto* Prop=MeshPath.IsEmpty()?nullptr:LoadObject<UStaticMesh>(nullptr,*MeshPath)){
  ControllerPlayProp=NewObject<UStaticMeshComponent>(this,TEXT("ActualControllerPlayProp"));ControllerPlayProp->SetStaticMesh(Prop);
  ControllerPlayProp->SetCollisionEnabled(ECollisionEnabled::NoCollision);ControllerPlayProp->SetMobility(EComponentMobility::Movable);
  ControllerPlayProp->SetUsingAbsoluteLocation(true);ControllerPlayProp->SetUsingAbsoluteRotation(true);
  ControllerPlayProp->SetupAttachment(GetRootComponent());ControllerPlayProp->RegisterComponent();ControllerPlayProp->SetVisibility(false);
 }else if(ControllerPlayClip)ControllerPlayRefusal=TEXT("ControllerMeshMissing");
 // Measured sofa seat (its exact text is the revision) and the computed evidence for THIS report.
 const FString Audit=FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit"));FString SofaText,EvidenceText;TSharedPtr<FJsonObject> Sofa,E;
 if(!FFileHelper::LoadFileToString(SofaText,*FPaths::Combine(Audit,TEXT("@@SOFA@@")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(SofaText),Sofa)||!Sofa.IsValid()){ControllerPlayRefusal=TEXT("SofaUnmeasured");return;}
 const TArray<TSharedPtr<FJsonValue>>* Errors=nullptr;
 if(!Sofa->TryGetArrayField(TEXT("errors"),Errors)||Errors->Num()!=0){ControllerPlayRefusal=TEXT("SofaUnmeasured");return;}
 if(!FFileHelper::LoadFileToString(EvidenceText,*FPaths::Combine(Audit,TEXT("@@EVIDENCE@@")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(EvidenceText),E)||!E.IsValid()){ControllerPlayRefusal=TEXT("EvidenceMissing");return;}
 FString Schema,Revision;bool Accepted=false,Grip=false,Seat=false;double Yaw=NAN,BodyYaw=NAN,Clearance=NAN;
 const TArray<TSharedPtr<FJsonValue>> *A=nullptr,*B=nullptr,*T=nullptr,*Q=nullptr;
 if(!E->TryGetStringField(TEXT("schema"),Schema)||Schema!=TEXT("@@SCHEMA@@")||!E->TryGetBoolField(TEXT("accepted"),Accepted)||!Accepted
  ||!E->TryGetBoolField(TEXT("grip_gates_passed"),Grip)||!Grip||!E->TryGetBoolField(TEXT("seat_contact_passed"),Seat)||!Seat
  ||!E->TryGetStringField(TEXT("sofa_revision"),Revision)||FCString::Strtoui64(*Revision,nullptr,10)!=Sub01ControllerPlayId(SofaText)
  ||!E->TryGetNumberField(TEXT("capsule_clearance_cm"),Clearance)||!(Clearance>0)
  ||!E->TryGetArrayField(TEXT("approach_cm"),A)||A->Num()!=2||!E->TryGetNumberField(TEXT("yaw_deg"),Yaw)
  ||!E->TryGetArrayField(TEXT("body_offset_cm"),B)||B->Num()!=3||!E->TryGetNumberField(TEXT("body_yaw_deg"),BodyYaw)
  ||!E->TryGetArrayField(TEXT("grip_offset_cm"),T)||T->Num()!=3||!E->TryGetArrayField(TEXT("grip_rotation_xyzw"),Q)||Q->Num()!=4){ControllerPlayRefusal=TEXT("EvidenceRejected");return;}
 ControllerPlayApproach=FVector2D((*A)[0]->AsNumber(),(*A)[1]->AsNumber());ControllerPlayYaw=float(Yaw);ControllerPlayBodyYaw=float(BodyYaw);
 ControllerPlayBodyOffset=FVector((*B)[0]->AsNumber(),(*B)[1]->AsNumber(),(*B)[2]->AsNumber());
 ControllerPlayGripOffset=FVector((*T)[0]->AsNumber(),(*T)[1]->AsNumber(),(*T)[2]->AsNumber());
 ControllerPlayGripRotation=FQuat((*Q)[0]->AsNumber(),(*Q)[1]->AsNumber(),(*Q)[2]->AsNumber(),(*Q)[3]->AsNumber()).GetNormalized();
 ControllerPlayEvidence=!ControllerPlayBodyOffset.ContainsNaN()&&!ControllerPlayGripOffset.ContainsNaN()&&ControllerPlayGripOffset.Size()<=30&&FMath::IsFinite(Yaw)&&FMath::IsFinite(BodyYaw)&&FMath::IsFinite(ControllerPlayApproach.X)&&FMath::IsFinite(ControllerPlayApproach.Y);
 if(ControllerPlayEvidence&&ControllerPlayClip&&ControllerPlayProp)ControllerPlayRefusal.Empty();else if(ControllerPlayRefusal.IsEmpty())ControllerPlayRefusal=TEXT("EvidenceRejected");
 // Root's NATIVE runtime capture/contact proof for THIS evidence and clip: without it play is never ready.
 ControllerPlayRuntimeProof=false;FString ProofText;TSharedPtr<FJsonObject> Proof;
 if(ControllerPlayEvidence&&FFileHelper::LoadFileToString(ProofText,*FPaths::Combine(Audit,TEXT("@@PROOF@@")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ProofText),Proof)&&Proof.IsValid()){
  FString PSchema,PClip,PRevision;bool PAccepted=false;double Measured=0,Passing=-1,Penetration=NAN;const TSharedPtr<FJsonObject>* Capture=nullptr;FString CaptureSha;
  ControllerPlayRuntimeProof=Proof->TryGetStringField(TEXT("schema"),PSchema)&&PSchema==TEXT("@@PROOF_SCHEMA@@")&&Proof->TryGetBoolField(TEXT("accepted"),PAccepted)&&PAccepted
   &&Proof->TryGetStringField(TEXT("clip_object_path"),PClip)&&PClip==TEXT("@@CLIP@@")
   &&Proof->TryGetStringField(TEXT("evidence_revision"),PRevision)&&FCString::Strtoui64(*PRevision,nullptr,10)==Sub01ControllerPlayId(EvidenceText)
   &&Proof->TryGetNumberField(TEXT("frames_measured"),Measured)&&Proof->TryGetNumberField(TEXT("frames_passing"),Passing)&&Measured>=@@FRAMES@@&&Passing==Measured
   &&Proof->TryGetNumberField(TEXT("max_penetration_cm"),Penetration)&&Penetration>=-0.3
   &&Proof->TryGetObjectField(TEXT("native_capture"),Capture)&&(*Capture)->TryGetStringField(TEXT("sha256"),CaptureSha)&&!CaptureSha.IsEmpty();
 }
 if(!ControllerPlayRuntimeProof&&ControllerPlayRefusal.IsEmpty())ControllerPlayRefusal=TEXT("RuntimeProofMissing");
 UE_LOG(LogTemp,Display,TEXT("SUB01_CONTROLLER_PLAY_READY ready=%d refusal=%s approach=%s"),ControllerPlayReady()?1:0,*ControllerPlayRefusal,*ControllerPlayApproach.ToString());
}
void ASub01HomeCharacter::UpdateControllerPlay(USub01HomeHandsInstance* Instance,float Dt){
 if(!Instance||!FirstPersonBody)return;const double Now=FPlatformTime::Seconds();
 const bool Want=LiveHome&&LiveHomeFresh&&Now>=LiveHomeLastReceived&&Now-LiveHomeLastReceived<=3&&!LiveHomePrivate&&!LiveHomeBlocked
  &&LiveHomeActivity==TEXT("play_console")&&LiveHomeNode==TEXT("sofa")&&LiveHomePath.Num()==0;
 const FVector Here=GetActorLocation();const float ViewYaw=Controller?Controller->GetControlRotation().Yaw:GetActorRotation().Yaw;
 const bool AtSeat=ControllerPlayEvidence&&FVector2D::Distance(ControllerPlayApproach,FVector2D(Here.X,Here.Y))<@@APPROACH@@
  &&FMath::Abs(FMath::FindDeltaAngleDegrees(ViewYaw,ControllerPlayYaw))<@@YAW@@&&GetCharacterMovement()->IsMovingOnGround();
 bool Play=Want&&ControllerPlayReady()&&AtSeat;
 if(Play&&!ControllerPlayActive){
  // The renderer's posture gate first (never bypassed): only a bound, validated Walk posture may host the clip.
  if(!SetHandsPosture(TEXT("Walk"))||!HandsFailure.IsEmpty()){UE_LOG(LogTemp,Warning,TEXT("SUB01_CONTROLLER_PLAY_POSTURE_GATE %s"),*HandsFailure);Play=false;}
  else{
   ControllerPlayActive=true;GetCharacterMovement()->StopMovementImmediately();
   ViewCamera->AttachToComponent(FirstPersonBody,FAttachmentTransformRules::SnapToTargetNotIncludingScale,ControllerPlayHead);ViewCamera->SetUsingAbsoluteRotation(true);
   UE_LOG(LogTemp,Display,TEXT("SUB01_CONTROLLER_PLAY_BEGIN TRIAL seated Gaming clip; minecraftFocused=%d (input stays with the existing TV input path)"),MinecraftFocused?1:0);
  }
 }
 if(!Play&&ControllerPlayActive){
  if(ControllerPlayProp)ControllerPlayProp->SetVisibility(false);
  FirstPersonBody->SetRelativeLocation(HandsBaseOffset);FirstPersonBody->SetRelativeRotation(HandsMeshRotation);
  ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);ViewCamera->SetUsingAbsoluteRotation(false);
  ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);
  ControllerPlayActive=false;UE_LOG(LogTemp,Display,TEXT("SUB01_CONTROLLER_PLAY_END"));
 }
 if(!ControllerPlayActive)return;
 // The captured clip after the renderer's choice (as the seat/life adapters do); the capsule never moves.
 GetCharacterMovement()->StopMovementImmediately();
 Instance->TargetSequence=ControllerPlayClip;Instance->TargetRate=1.f;
 FirstPersonBody->SetRelativeLocation(ControllerPlayBodyOffset);FirstPersonBody->SetRelativeRotation(HandsMeshRotation+FRotator(0,ControllerPlayBodyYaw,0));
 // Rigid at the captured right Hand socket: socket rotation and location, imported bone scale excluded.
 const FTransform W=FirstPersonBody->GetSocketTransform(ControllerPlayHand,RTS_World);const FQuat R=W.GetRotation().GetNormalized();
 ControllerPlayProp->SetWorldLocationAndRotation(W.GetLocation()+R.RotateVector(ControllerPlayGripOffset),R*ControllerPlayGripRotation);
 ControllerPlayProp->SetVisibility(true);
}
'''

EDITS = [
    ('header', ' void Forward(float Value);', CHARACTER_FIELDS + '\n void Forward(float Value);'),
    ('cpp', ' LoadPrivateHandsDiagnostic();\n', ' LoadPrivateHandsDiagnostic();\n LoadControllerPlay();\n'),
    ('cpp', LIVE_ANCHOR, LIVE_GATE + LIVE_ANCHOR),
]


def _after_rate_line(cpp: str) -> str:
    lines = [l for l in cpp.split('\n') if l.startswith(RATE_PREFIX)]
    if len(lines) != 1:
        raise ValueError(f'Controller play anchor not unique in cpp: {RATE_PREFIX!r} ({len(lines)} lines)')
    return cpp.replace(lines[0] + '\n', lines[0] + '\n UpdateControllerPlay(Instance,DeltaSeconds);\n', 1)
SOURCE_FILES = {'header': 'Sub01HomeLab.h', 'cpp': 'Sub01HomeLab.cpp'}
REQUIRED = (' bool MinecraftFocused', 'TickMinecraftTVInput();', 'bool ASub01HomeCharacter::SetHandsPosture(FName Posture)',
            'TArray<FName> ValidatedHandsPostures;', 'LiveHomeActivity', 'LiveHomeFresh', 'LiveHomeLastReceived')


def methods():
    return (CHARACTER_METHODS.replace('@@CLIP@@', CLIP_OBJECT_PATH).replace('@@ROLE@@', ROLE).replace('@@ASSET_RECEIPT@@', CONTROLLER_ASSET_RECEIPT)
            .replace('@@ASSET_SCHEMA@@', CONTROLLER_ASSET_SCHEMA).replace('@@ASSET_SHA@@', CONTROLLER_SOURCE_SHA256)
            .replace('@@SOFA@@', SOFA_REPORT).replace('@@PROOF@@', RUNTIME_PROOF).replace('@@PROOF_SCHEMA@@', RUNTIME_PROOF_SCHEMA)
            .replace('@@FRAMES@@', str(CLIP_FRAMES)).replace('@@EVIDENCE@@', EVIDENCE).replace('@@SCHEMA@@', EVIDENCE_SCHEMA)
            .replace('@@APPROACH@@', f'{APPROACH_TOLERANCE_CM:.1f}f').replace('@@YAW@@', f'{YAW_TOLERANCE_DEG:.1f}f'))


def install(sources: dict) -> dict:
    """Apply to staged sources {'header','cpp', ...}; additions only, every anchor unique, refuses otherwise."""
    out = dict(sources)
    if 'ControllerPlayActive' in out['header'] or 'UpdateControllerPlay(' in out['cpp']:
        raise ValueError('Controller play integration is already installed')
    both = out['header'] + out['cpp']
    for needle in REQUIRED:
        if needle not in both:
            raise ValueError(f'Controller play requires the staged renderer/TV input: missing {needle!r}')
    for key, anchor, replacement in EDITS:
        if out[key].count(anchor) != 1:
            raise ValueError(f'Controller play anchor not unique in {key}: {anchor[:60]!r}')
        out[key] = out[key].replace(anchor, replacement)
    out['cpp'] = _after_rate_line(out['cpp'])
    out['cpp'] += methods()
    return out


def install_module(module: Path) -> None:
    module = Path(module)
    patched = install({key: (module / name).read_text() for key, name in SOURCE_FILES.items()})
    for key, name in SOURCE_FILES.items():
        (module / name).write_text(patched[key])


def main(argv):
    if len(argv) == 5 and argv[0] == 'evidence':
        print(write_evidence(Path(argv[1]), Path(argv[2]), Path(argv[3]), Path(argv[4])))
        return 0
    if len(argv) == 4 and argv[0] == 'config':
        text, refusals = config_fragment(Path(argv[1]), json.loads(Path(argv[2]).read_text()))
        if text:
            Path(argv[3]).write_text(text)
        print(json.dumps({'written': bool(text), 'refusals': refusals}, indent=2))
        return 0 if text else 3
    if len(argv) == 2 and argv[0] == 'install':
        install_module(Path(argv[1]))
        print('Controller play adapter installed into staged sources; not compiled or running yet (TRIAL).')
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
