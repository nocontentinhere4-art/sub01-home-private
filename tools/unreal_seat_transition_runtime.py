"""Native seat transition adapter: evidence builder, C++ integration and install hooks.

Owns tools/native_seating/Sub01SeatTransition.h and this file only. Nothing here is
staged by default: the runtime owner applies `install()` to the staged sources after the
renderer's measured chair/body report exists. Until then the live home is unchanged.

Python side (runs anywhere): build the quantitative evidence file the native side reads,
from the accepted reports written on the server:
    private-audit/native-chair-surface.json   (tools/unreal_chair_surface_audit.py)
    private-audit/native-seat-contact.json    (tools/unreal_audit_seat_contact.py, or for the seated-fit
                                              DeskTyping clip tools/unreal_audit_seated_typing_seat_contact.py,
                                              checked against private-audit/unreal-seated-fit-import.json)
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

import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_unreal_seat_contact as seat_contact  # noqa: E402
import unreal_controller_play_runtime as controller_play  # noqa: E402

HEADER_FILE = Path(__file__).resolve().parent / 'native_seating' / 'Sub01SeatTransition.h'
OWNER_MESH = '/Game/Sub01Hands/FBX/SUB01_OriginalOwner.SUB01_OriginalOwner'
TYPING_CLIP = '/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping'
SEAT_CLIP_DIR = '/Game/Sub01Hands/Seating'           # tools/unreal_import_seating_fbx.py
SEAT_ROLE_ASSETS = {'StandToSit': 'SitDown', 'Sitting': 'Sitting', 'SitToType': 'SitToType', 'SitToStand': 'GetUp'}
SEAT_ROLES = tuple(SEAT_ROLE_ASSETS)
OWNER_SKELETON = '/Game/Sub01Hands/FBX/SUB01_OriginalOwner_Skeleton.SUB01_OriginalOwner_Skeleton'
# Seated-fit clips (docs/proposed/seat-pose-fit/, imported by tools/unreal_import_seated_fit_fbx.py). Each may replace
# the captured clip in ONE existing slot, only when that importer's receipt ACCEPTED the row (its per-clip fit gates
# passed), the row names the committed GLB whose committed verdict passes (plan_clips(), compiled in at install) and the
# renderer's ValidatedHandsPostures lists the role. Without the receipt nothing changes.
SEATED_FIT_RECEIPT = 'private-audit/unreal-seated-fit-import.json'
SEATED_FIT_RECEIPT_SCHEMA = 'sub01.unreal-seated-fit-import.v1'
# SitDown/GetUp seated bind only once their per-clip fit passes (the importer never imports a failed fit). TypeToSit has
# no slot in the transition. Durations equal the captured clips' (FSub01SeatClips), so phase timing is unchanged.
SEATED_FIT_SLOTS = {'SitDownSeated': ('StandToSit', 'SeatRoleStandToSit'), 'SeatedIdle': ('Sitting', 'SeatRoleSitting'),
                    'SitToTypeSeated': ('SitToType', 'SeatRoleSitToType'), 'DeskTypingSeated': ('DeskTyping', 'SeatRoleDeskTyping'),
                    'GetUpSeated': ('SitToStand', 'SeatRoleSitToStand')}
# The seated typing clip's keyboard arm profile (tools/desk_typing_seated_contact_profile.py writes it only when the
# native capture of THAT clip passes every typing contact gate; a later failing capture retires it). LoadSeatTransition
# binds it to the seated-fit DeskTyping slot; the renderer's profile for /Game/Sub01Hands/FBX/SUB01_DeskTyping never is.
SEATED_TYPING_ROLE = 'DeskTypingSeated'
SEATED_TYPING_PROFILE_FILE = 'desk-typing-seated-contact-profile.json'        # in <project>/private-audit/
SEATED_TYPING_PROFILE_SCHEMA = 'sub01.desk-typing-seated-contact-profile.v1'
MIN_CUSHION_AREA_CM2 = 1000.0      # the broad seat cushion is 2228 cm^2; the 58 cm^2 lumbar top is not a seat
PATCHES = ('buttocks', 'left_posterior_thigh', 'right_posterior_thigh', 'left_sole', 'right_sole')


def seated_fit_object_path(role: str) -> str:
    return f'{SEAT_CLIP_DIR}/SUB01_{role}.SUB01_{role}'


# Committed seated-fit verdicts: the receipt alone never binds. LoadSeatTransition() carries an immutable table generated
# at install time from tools/unreal_import_seated_fit_fbx.plan_clips() (role -> committed GLB sha256 -> the per-clip
# report's all_gates_pass, checked there against the summary report); Sub01SeatedFitCommitted() in the header and
# seated_fit_committed() here require the receipt row to name exactly that GLB and the committed verdict to pass.
SEATED_FIT_UNCOMMITTED = 'receipt row is not the committed GLB with a passing committed verdict'
SEATED_TYPING_UNCOMMITTED = 'committed fit verdict refuses the seated typing clip'
SEATED_FIT_VERDICTS_UNAVAILABLE = 'committed seated-fit verdicts unavailable'


def _sha256_text(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _checked_verdicts(rows) -> dict:
    import unreal_import_seated_fit_fbx as fit
    table = {}
    for row in rows:
        role, digest, verdict = row.get('role'), row.get('glb_sha256'), row.get('fit_pass')
        if role not in fit.ROLES or role in table:
            raise RuntimeError(f'{SEATED_FIT_VERDICTS_UNAVAILABLE}: unexpected or repeated role {role!r}')
        if not _sha256_text(digest) or not isinstance(verdict, bool):
            raise RuntimeError(f'{SEATED_FIT_VERDICTS_UNAVAILABLE}: {role} has no committed GLB sha256 and verdict')
        table[role] = {'glb_sha256': digest, 'all_gates_pass': verdict}
    if set(table) != set(fit.ROLES):
        raise RuntimeError(f'{SEATED_FIT_VERDICTS_UNAVAILABLE}: expected exactly the roles {sorted(fit.ROLES)}')
    return dict(sorted(table.items()))


def committed_seated_fit_verdicts(repo=None) -> dict:
    """role -> {'glb_sha256', 'all_gates_pass'}, re-read from plan_clips(); RuntimeError when plan_clips refuses."""
    import unreal_import_seated_fit_fbx as fit
    try:
        rows = fit.plan_clips() if repo is None else fit.plan_clips(Path(repo))
    except Exception as error:   # any refusal of the committed fit: nothing is generated, nothing binds
        raise RuntimeError(f'{SEATED_FIT_VERDICTS_UNAVAILABLE}: {error}') from error
    return _checked_verdicts({'role': r.get('role'), 'glb_sha256': r.get('glb_sha256'), 'fit_pass': r.get('fit_pass')}
                             for r in rows)


def seated_fit_verdict_table_cpp(verdicts: dict) -> str:
    """The C++ initializer of LoadSeatTransition()'s FSub01SeatedFitVerdict table: deterministic, sorted by role."""
    table = _checked_verdicts({'role': role, 'glb_sha256': v.get('glb_sha256'), 'fit_pass': v.get('all_gates_pass')}
                              for role, v in verdicts.items())
    return ','.join('{"%s","%s",%s}' % (role, v['glb_sha256'], 'true' if v['all_gates_pass'] else 'false')
                    for role, v in table.items())


def seated_fit_committed(verdicts: dict, role, accepted, fit_pass, glb_sha256) -> bool:
    """Python mirror of Sub01SeatedFitCommitted()."""
    committed = verdicts.get(role) if isinstance(verdicts, dict) else None
    return (accepted is True and fit_pass is True and isinstance(committed, dict)
            and committed.get('all_gates_pass') is True and _sha256_text(committed.get('glb_sha256'))
            and glb_sha256 == committed['glb_sha256'])


def _verdicts_or_none(verdicts):
    if verdicts is not None:
        return verdicts
    try:
        return committed_seated_fit_verdicts()
    except RuntimeError:
        return None


def seated_fit_bindings(receipt, validated=(), verdicts=None) -> dict:
    """Python mirror of the native seated-fit binding in LoadSeatTransition(): slot -> what binds there.

    A slot binds its seated-fit role only for an accepted, fit-passing row on the owner skeleton at the exact path,
    and only when `validated` (the renderer's ValidatedHandsPostures) lists the role. The row must also name exactly
    the committed GLB whose committed verdict passes (`verdicts`, default re-read from plan_clips(); unavailable
    verdicts bind nothing). Otherwise the slot keeps the clip it binds today (captured Sitting / the renderer's
    DeskTyping) and the refusal says why.
    """
    verdicts = _verdicts_or_none(verdicts)
    rows = {}
    ok_receipt = (isinstance(receipt, dict) and receipt.get('schema') == SEATED_FIT_RECEIPT_SCHEMA
                  and receipt.get('skeleton') == OWNER_SKELETON)
    if ok_receipt:
        for row in receipt.get('clips', []):
            if isinstance(row, dict) and row.get('role') in SEATED_FIT_SLOTS:
                rows.setdefault(row['role'], row)
    out = {}
    for role, (slot, _) in SEATED_FIT_SLOTS.items():
        row = rows.get(role)
        if not ok_receipt:
            why = 'no seated-fit import receipt on the owner skeleton'
        elif row is None:
            why = 'role not in the import receipt'
        elif not (row.get('accepted') is True and row.get('fit_pass') is True):
            why = 'fit gates failed or row not accepted'
        elif row.get('same_existing_skeleton') is not True or row.get('object_path') != seated_fit_object_path(role):
            why = f'not imported at {seated_fit_object_path(role)} on the owner skeleton'
        elif verdicts is None:
            why = SEATED_FIT_VERDICTS_UNAVAILABLE
        elif not seated_fit_committed(verdicts, role, row.get('accepted'), row.get('fit_pass'), row.get('glb_sha256')):
            why = SEATED_FIT_UNCOMMITTED
        elif role not in validated:
            why = f'ValidatedHandsPostures does not list {role}'
        else:
            out[slot] = {'bound': True, 'role': role, 'object_path': row['object_path']}
            continue
        out[slot] = {'bound': False, 'role': role, 'refusal': why}
    return out


def typing_profile_sample(index: int, row: dict, spread) -> bool:
    """Python mirror of Sub01TypingProfileSample() (native_seating/Sub01SeatTransition.h, FSub01TypingProfileRules)."""
    import validate_unreal_contact_profile as profile_gate
    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    try:
        corrected = row['corrected']
        hands = corrected['hands']
        values = [row['time'], spread, row['bone_length_max_error_cm'], row['finger_local_max_error_degrees'],
                  corrected['invalidInfluences'], corrected['keyTopCm']]
        if len(hands) != 2 or [h.get('side') for h in hands] != ['left', 'right']:
            return False
        values += [h[k] for h in hands for k in ('overMinCm', 'penetrationCm', 'overKeyVertices')]
    except (KeyError, TypeError):
        return False
    if not all(num(v) for v in values) or not 0 <= index < 301:
        return False
    time, spread, bone, finger, invalid, top = values[:6]
    gap_max, pen_max = profile_gate.KEY_GAP_MAX_CM, .1
    if abs(time - (3 + index / 60)) > 1e-6 or not 0 <= spread <= .2 or not 0 <= bone <= .01 or not 0 <= finger <= .1 or invalid != 0:
        return False
    for h in hands:
        gap = h['overMinCm'] - top
        if h['overKeyVertices'] <= 0 or not 0 <= h['penetrationCm'] <= pen_max or gap < -pen_max or gap + spread > gap_max + 1e-9:
            return False
    return True


def seated_typing_profile_binding(profile, receipt, bound_object_path: str, verdicts=None) -> dict:
    """Python mirror of the seated typing profile binding in LoadSeatTransition(): {'bound': bool, 'refusal': str}.

    Also requires the committed DeskTypingSeated verdict (`verdicts`, default re-read from plan_clips()) for exactly
    the receipt row's GLB.
    """
    def refuse(why):
        return {'bound': False, 'refusal': why}
    if bound_object_path != seated_fit_object_path(SEATED_TYPING_ROLE):
        return refuse('DeskTyping slot does not hold the seated typing clip')
    row = None
    for r in (receipt or {}).get('clips', []) if isinstance(receipt, dict) else []:
        if (isinstance(r, dict) and r.get('role') == SEATED_TYPING_ROLE and r.get('object_path') == bound_object_path
                and r.get('accepted') is True and r.get('fit_pass') is True and r.get('same_existing_skeleton') is True):
            row = r
    if not row or not row.get('glb_sha256') or not row.get('fbx_sha256'):
        return refuse('no accepted import receipt row for the seated typing clip')
    if not isinstance(profile, dict):
        return refuse('no seated typing profile')
    if profile.get('schema') != SEATED_TYPING_PROFILE_SCHEMA or profile.get('ready') is not True:
        return refuse('profile schema/readiness')
    if (profile.get('clip_object_path') != bound_object_path or profile.get('glb_sha256') != row['glb_sha256']
            or profile.get('fbx_sha256') != row['fbx_sha256']):
        return refuse('profile is bound to another clip, GLB or FBX')
    samples, spread = profile.get('samples'), profile.get('key_top_spread_cm')
    if not isinstance(samples, list) or len(samples) != 301 or not isinstance(spread, (int, float)):
        return refuse('profile samples')
    body, yaw = profile.get('body_cm'), profile.get('body_yaw')
    if (not isinstance(body, list) or len(body) != 3 or not isinstance(yaw, (int, float))
            or profile.get('body_rotation_pyr') != [0, yaw, 0] or profile.get('body_scale_xyz') != [1, 1, 1]):
        return refuse('profile body transform (pitch/roll-free, unit scale)')
    verdicts = _verdicts_or_none(verdicts)
    if verdicts is None or not seated_fit_committed(verdicts, SEATED_TYPING_ROLE, row.get('accepted'), row.get('fit_pass'),
                                                    row.get('glb_sha256')):
        return refuse(SEATED_TYPING_UNCOMMITTED)
    names = None
    for i, row_ in enumerate(samples):
        if not isinstance(row_, dict) or not typing_profile_sample(i, row_, spread):
            return refuse(f'sample {i} outside the typing contact gates')
        arms = row_.get('corrected_local_arms')
        if not isinstance(arms, dict) or len(arms) != 6 or (names is not None and set(arms) != names):
            return refuse('profile must hold six arm bones only')
        names = set(arms)
        for t in arms.values():
            q, sc, tr = t.get('rotation', []), t.get('scale', []), t.get('translation', [])
            if len(tr) != 3 or len(q) != 4 or len(sc) != 3 or abs(sum(v * v for v in q) - 1) > .001 or min(sc) <= 0:
                return refuse('invalid arm transform')
    if not all(math.isfinite(v) for v in body) or not math.isfinite(yaw):
        return refuse('profile body transform (pitch/roll-free, unit scale)')
    return {'bound': True, 'object_path': bound_object_path, 'samples': 301, 'body_cm': list(body), 'body_yaw': yaw}


def seat_id(text: str) -> int:
    """FNV-1a over the low byte of each character, identical to Sub01SeatId()."""
    value = 1469598103934665603
    for char in text:
        value ^= ord(char) & 0xFF
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def cushion_area_cm2(triangles) -> float:
    area = 0.0
    for a, b, c in zip(triangles[0::3], triangles[1::3], triangles[2::3]):
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        area += .5 * math.sqrt(sum(x * x for x in cross))
    return area


def build_evidence(seat_report: dict, chair_text: str, mesh: str = OWNER_MESH, clip: str = TYPING_CLIP) -> dict:
    """Reduce an ACCEPTED seat contact report to the numbers the native receipt checks.

    Refuses (ValueError) unless validate_unreal_seat_contact.validate() accepts the report:
    an out-of-band report is evidence for a correction, never for a receipt.
    """
    chair = json.loads(chair_text)
    triangles = seat_contact.cushion_triangles(chair)     # audited cushion triangles, no errors
    if cushion_area_cm2(triangles) < MIN_CUSHION_AREA_CM2:
        raise ValueError(f'Cushion area {cushion_area_cm2(triangles):.1f} cm2 is not the broad seat cushion')
    seat_contact.validate(seat_report)
    samples = seat_contact.regions_by_sample(seat_report)
    worst = {}
    for name in PATCHES:
        rows = [regions[name] for _, regions in samples]
        worst[name] = {'min_gap_cm': min(r['minGapCm'] for r in rows),
                       'max_median_cm': max(r['p50GapCm'] for r in rows),
                       'min_coverage': min(r['bandVertices'] / r['overSurfaceVertices'] for r in rows),
                       'min_band_vertices': min(r['bandVertices'] for r in rows)}
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


SEATED_TYPING_RATE_HZ = 60      # the seated typing clip's import fps; the contact audit samples it at 3..8 s @ 60 Hz


def seated_typing_receipt_row(receipt) -> dict:
    """The one accepted DeskTypingSeated row of the seated-fit import receipt, under the same conditions
    LoadSeatTransition() binds it into the DeskTyping slot on (plus GLB/FBX sha256 and 60 Hz); else ValueError."""
    if not (isinstance(receipt, dict) and receipt.get('schema') == SEATED_FIT_RECEIPT_SCHEMA
            and receipt.get('skeleton') == OWNER_SKELETON):
        raise ValueError('No seated-fit import receipt on the owner skeleton')
    rows = [r for r in receipt.get('clips', []) if isinstance(r, dict) and r.get('role') == SEATED_TYPING_ROLE]
    if len(rows) != 1:
        raise ValueError(f'Expected exactly one {SEATED_TYPING_ROLE} receipt row, found {len(rows)}')
    row = rows[0]
    for field, want in (('accepted', True), ('fit_pass', True), ('same_existing_skeleton', True),
                        ('object_path', seated_fit_object_path(SEATED_TYPING_ROLE)), ('fps', SEATED_TYPING_RATE_HZ)):
        if row.get(field) != want:
            raise ValueError(f'{SEATED_TYPING_ROLE} receipt row {field}={row.get(field)!r}, expected {want!r}')
    for field in ('glb_sha256', 'fbx_sha256'):
        if not (isinstance(row.get(field), str) and len(row[field]) == 64):
            raise ValueError(f'{SEATED_TYPING_ROLE} receipt row has no {field}')
    return row


def audited_clip(report: dict, receipt_text=None) -> tuple:
    """The clip a seat contact report was audited on: (object path, extra evidence fields).

    A report that names no clip, or the captured DeskTyping clip, is the original audit (TYPING_CLIP, unchanged).
    A report naming the seated typing clip must match the ACCEPTED import receipt row exactly (object path, GLB and
    FBX sha256, 60 Hz); `receipt_text` is called for the receipt text only then. Anything else is refused.
    """
    clip = report.get('clip')
    path = clip.get('object_path') if isinstance(clip, dict) else clip
    if path is None or path == TYPING_CLIP:
        return TYPING_CLIP, {}
    seated = seated_fit_object_path(SEATED_TYPING_ROLE)
    if path != seated or not isinstance(clip, dict):
        raise ValueError(f'Seat contact report names clip {path!r}: neither {TYPING_CLIP} nor {seated}')
    if receipt_text is None:
        raise ValueError('Seated typing seat contact report needs the seated-fit import receipt')
    raw = receipt_text()
    row = seated_typing_receipt_row(json.loads(raw))
    for field, want in (('role', SEATED_TYPING_ROLE), ('object_path', row['object_path']), ('glb_sha256', row['glb_sha256']),
                        ('fbx_sha256', row['fbx_sha256']), ('rate_hz', SEATED_TYPING_RATE_HZ)):
        if clip.get(field) != want:
            raise ValueError(f'Seat contact report clip {field}={clip.get(field)!r} disagrees with the accepted receipt ({want!r})')
    return seated, {'clip_role': SEATED_TYPING_ROLE, 'clip_glb_sha256': row['glb_sha256'], 'clip_fbx_sha256': row['fbx_sha256'],
                    'seated_fit_receipt_sha256': hashlib.sha256(raw.encode() if isinstance(raw, str) else raw).hexdigest()}


def write_evidence(project: Path) -> Path:
    audit = Path(project) / 'private-audit'
    chair_text = (audit / 'native-chair-surface.json').read_text()
    report = json.loads((audit / 'native-seat-contact.json').read_text())
    # The evidence clip id is the clip the report was audited on: the seated typing clip only when the accepted
    # import receipt row matches it (Sub01SeatReceipt then compares it to the clip actually bound in the slot).
    clip, extra = audited_clip(report, lambda: (Path(project) / SEATED_FIT_RECEIPT).read_bytes())
    evidence = build_evidence(report, chair_text, clip=clip)
    evidence.update(extra)
    out = audit / 'native-seat-evidence.json'
    out.write_text(json.dumps(evidence, indent=2) + '\n')
    return out


# ---------------------------------------------------------------- native integration
CHARACTER_INCLUDE = '#include "Sub01SeatTransition.h"\n'

# Seated desk camera: the SAME measured eye and easing as controller play (tools/unreal_controller_play_runtime.py):
# the iris-midpoint offset in the owner's Head bone frame, applied only on the original owner skin, reached with
# 1-exp(-rate*min(dt,.1)) (95% in 0.30 s at any frame rate), and eased back to the standing eye before the camera is
# handed back to the capsule. A camera attached to the hidden (zero-scale) Head bone would collapse any relative
# offset, so the eye is placed in world space. The alpha function gets its own name (both adapters share one .cpp).
assert OWNER_MESH == controller_play.OWNER_MESH_OBJECT_PATH
EYE_OFFSET_HEAD_CM = controller_play.EYE_OFFSET_HEAD_CM
EYE_EASE_RATE = controller_play.EYE_EASE_RATE
SEAT_EYE_ALPHA_CPP = controller_play.EYE_ALPHA_CPP.replace('Sub01ControllerPlayEyeAlpha', 'Sub01SeatEyeAlpha')

CHARACTER_FIELDS = r'''
 // Native seat transition (tools/unreal_seat_transition_runtime.py).
 void LoadSeatTransition(); void UpdateSeatTransition(float Dt); void ApplySeatAnimation(class USub01HomeHandsInstance* Instance);
 FSub01SeatTransition SeatMachine; FSub01SeatOutputs SeatOut; FSub01SeatEvidence SeatEvidence;
 UPROPERTY() TMap<FName,TObjectPtr<UAnimSequence>> SeatClips;
 uint32 SeatRoles=0,SeatAppliedSerial=0; uint64 SeatChairRevision=0; ESub01SeatPhase SeatLoggedPhase=ESub01SeatPhase::Standing;
 bool SeatChairMeasured=false,SeatAnchorValid=false,SeatBodyAttached=false; float SeatYaw=-90;
 void UpdateSeatCamera(float Dt); FVector SeatEye=FVector::ZeroVector,SeatEyeOffset=FVector::ZeroVector; FName SeatHead; bool SeatCameraEasing=false;
 FVector2D SeatApproach=FVector2D::ZeroVector;
 // Live skin measurement at the actual seated transform, the audited cushion it is measured
 // against, the bounded settle, and the transform the keyboard contact profile was audited at.
 FSub01SeatMeasurement SeatMeasurement; TArray<FVector> SeatCushionTriangles; double SeatMeasuredAt=0; int32 SeatMeasurementLogged=-1;
 float SeatSettleTravel=0; bool SeatSettleBlocked=false; bool SeatProfilePoseLoaded=false; FSub01SeatLivePose SeatProfilePose;
 bool SeatLiveBody(FSub01SeatLivePose& L) const; bool SeatSoleSupport(int32 Side,double& FloorZ,FString& Surface) const;
'''

CHARACTER_METHODS = r'''
#include "Misc/FileHelper.h"
#include <cmath>
@@SEAT_EYE_ALPHA@@
void ASub01HomeCharacter::LoadSeatTransition(){
 SeatRoles=0;SeatClips.Empty();SeatChairMeasured=false;SeatAnchorValid=false;SeatEvidence=FSub01SeatEvidence();
 USkeletalMesh* Mesh=FirstPersonBody?FirstPersonBody->GetSkeletalMeshAsset():nullptr;if(!Mesh)return;
 // Committed seated-fit verdicts (role, committed GLB sha256, all_gates_pass), generated at install from
 // tools/unreal_import_seated_fit_fbx.plan_clips(). No receipt can bind a seated-fit clip this table refuses.
 static const FSub01SeatedFitVerdict SeatedFitVerdicts[]={@@SEATED_FIT_VERDICTS@@};
 const int32 SeatedFitVerdictCount=int32(sizeof(SeatedFitVerdicts)/sizeof(SeatedFitVerdicts[0]));
 // Seat clips: the imported captures on the SAME owner skeleton, or nothing (fail closed).
 struct FSeatRoleBinding{const TCHAR* Key;const TCHAR* Asset;uint32 Value;};
 const FSeatRoleBinding Roles[]={@@SEAT_ROLE_BINDINGS@@};
 for(const auto& Role:Roles){
  const FString Path=FString::Printf(TEXT("%s/SUB01_%s.SUB01_%s"),TEXT("@@SEAT_CLIP_DIR@@"),Role.Asset,Role.Asset);
  auto* Clip=LoadObject<UAnimSequence>(nullptr,*Path);
  // The renderer's gate: only clips it lists in ValidatedHandsPostures, on the same skeleton.
  if(Clip&&Clip->GetSkeleton()==Mesh->GetSkeleton()&&ValidatedHandsPostures.Contains(FName(Role.Key))){SeatClips.Add(FName(Role.Key),Clip);SeatRoles|=Role.Value;}
  else UE_LOG(LogTemp,Warning,TEXT("SUB01_SEAT_ROLE_MISSING %s"),*Path);
 }
 if(UAnimSequence* Typing=HandsClips.FindRef(TEXT("DeskTyping"))){SeatClips.Add(TEXT("DeskTyping"),Typing);SeatRoles|=SeatRoleDeskTyping;}
 // Seated-fit clips (tools/unreal_import_seated_fit_fbx.py) replace the clip in their slot only when the import
 // receipt ACCEPTED the row (its seat-pose-fit gates passed), at the exact path, on this owner skeleton, for exactly
 // the committed GLB whose committed verdict passes (SeatedFitVerdicts), and the renderer's ValidatedHandsPostures
 // lists the role. Otherwise every slot keeps what it bound above. They never verify a seat:
 // contact evidence and the keyboard profile still compare against the clip actually bound.
 {FString FitText,FitSchema,FitSkeleton;TSharedPtr<FJsonObject> Fit;const TArray<TSharedPtr<FJsonValue>>* FitRows=nullptr;
  if(FFileHelper::LoadFileToString(FitText,*FPaths::Combine(FPaths::ProjectDir(),TEXT("@@SEATED_FIT_RECEIPT@@")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(FitText),Fit)&&Fit.IsValid()
     &&Fit->TryGetStringField(TEXT("schema"),FitSchema)&&FitSchema==TEXT("@@SEATED_FIT_SCHEMA@@")&&Fit->TryGetStringField(TEXT("skeleton"),FitSkeleton)
     &&Mesh->GetSkeleton()&&FitSkeleton==Mesh->GetSkeleton()->GetPathName()&&Fit->TryGetArrayField(TEXT("clips"),FitRows)){
   struct FSeatFitSlot{const TCHAR* Role;const TCHAR* Slot;uint32 Value;};
   const FSeatFitSlot FitSlots[]={@@SEATED_FIT_BINDINGS@@};
   for(const auto& S:FitSlots){
    const FString Path=FString::Printf(TEXT("%s/SUB01_%s.SUB01_%s"),TEXT("@@SEAT_CLIP_DIR@@"),S.Role,S.Role);bool Accepted=false,Claimed=false;
    for(const auto& RowValue:*FitRows){const TSharedPtr<FJsonObject>* Row=nullptr;FString Role,Object,Glb;bool A=false,P=false,Same=false;
     if(RowValue.IsValid()&&RowValue->TryGetObject(Row)&&(*Row)->TryGetStringField(TEXT("role"),Role)&&Role==S.Role&&(*Row)->TryGetBoolField(TEXT("accepted"),A)&&A
        &&(*Row)->TryGetBoolField(TEXT("fit_pass"),P)&&P&&(*Row)->TryGetBoolField(TEXT("same_existing_skeleton"),Same)&&Same&&(*Row)->TryGetStringField(TEXT("object_path"),Object)&&Object==Path){
      Claimed=true;
      // The receipt's claim counts only for exactly the committed GLB whose committed verdict passes.
      if((*Row)->TryGetStringField(TEXT("glb_sha256"),Glb)&&Sub01SeatedFitCommitted(SeatedFitVerdicts,SeatedFitVerdictCount,S.Role,A,P,*Glb))Accepted=true;}}
    if(Claimed&&!Accepted)UE_LOG(LogTemp,Warning,TEXT("SUB01_SEAT_FIT_REFUSED %s (receipt row is not the committed GLB with a passing committed verdict)"),*Path);
    auto* Clip=Accepted&&ValidatedHandsPostures.Contains(FName(S.Role))?LoadObject<UAnimSequence>(nullptr,*Path):nullptr;
    if(Clip&&Clip->GetSkeleton()==Mesh->GetSkeleton()){SeatClips.Add(FName(S.Slot),Clip);SeatRoles|=S.Value;UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_FIT_BOUND %s=%s"),S.Slot,*Path);}
    else if(Accepted)UE_LOG(LogTemp,Warning,TEXT("SUB01_SEAT_FIT_REFUSED %s (not validated, missing or another skeleton)"),*Path);
   }
  }
 }
 // Chair: the audited cushion report; its exact text is the chair revision.
 const FString Audit=FPaths::Combine(FPaths::ProjectDir(),TEXT("private-audit"));FString ChairText;TSharedPtr<FJsonObject> Chair;
 if(FFileHelper::LoadFileToString(ChairText,*FPaths::Combine(Audit,TEXT("native-chair-surface.json")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(ChairText),Chair)&&Chair.IsValid()){
  const TArray<TSharedPtr<FJsonValue>>* Errors=nullptr;const TSharedPtr<FJsonObject>* ChairObject=nullptr;
  if(Chair->TryGetArrayField(TEXT("errors"),Errors)&&Errors->Num()==0&&Chair->TryGetObjectField(TEXT("chair"),ChairObject)){
   SeatChairRevision=Sub01SeatId(*ChairText);SeatCushionTriangles.Reset();
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
   // Only the broad connected seat cushion is a seat (measured 2228 cm^2); a small patch such as
   // the 58 cm^2 lumbar top is refused, so the chair stays unmeasured.
   double Area=0;FBox Cushion(ForceInit);
   for(int32 T=0;T+2<SeatCushionTriangles.Num();T+=3){const FVector& A=SeatCushionTriangles[T];const FVector& B=SeatCushionTriangles[T+1];const FVector& C=SeatCushionTriangles[T+2];
    Area+=.5*FVector::CrossProduct(B-A,C-A).Size();Cushion+=A;Cushion+=B;Cushion+=C;}
   SeatChairMeasured=SeatCushionTriangles.Num()>=3&&Area>=1000&&Cushion.IsValid;
   if(!SeatChairMeasured){SeatCushionTriangles.Reset();UE_LOG(LogTemp,Warning,TEXT("SUB01_SEAT_CUSHION_REFUSED area=%.2fcm2; a seat needs the broad connected cushion"),Area);}
   else{
    // Approach without contact evidence: cushion centre + the captured sit's hip travel (no receipt possible).
    double X=0,Y=0;const FVector Centre=Cushion.GetCenter();Sub01SeatApproachFromCushion(Centre.X,Centre.Y,SeatYaw,X,Y);SeatApproach=FVector2D(X,Y);SeatAnchorValid=FMath::IsFinite(X)&&FMath::IsFinite(Y);
    UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_CUSHION area=%.2fcm2 bounds=%s"),Area,*Cushion.ToString());
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
   for(int32 I=0;I<5;++I){const TSharedPtr<FJsonObject>* P=nullptr;if(!(*Patches)->TryGetObjectField(Names[I],P)||!(*P)->TryGetNumberField(TEXT("min_gap_cm"),Loaded.MinGap[I])||!(*P)->TryGetNumberField(TEXT("max_median_cm"),Loaded.MaxMedian[I])||!(*P)->TryGetNumberField(TEXT("min_coverage"),Loaded.MinCoverage[I])||!(*P)->TryGetNumberField(TEXT("min_band_vertices"),Loaded.MinBandVertices[I]))Complete=false;}
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
 // Seated typing profile (tools/desk_typing_seated_contact_profile.py). When the DeskTyping slot holds the seated-fit
 // clip, the renderer's profile (measured on /Game/Sub01Hands/FBX/SUB01_DeskTyping) never applies to it: typing needs
 // the profile measured natively on THIS clip (its object path and the import receipt row's GLB/FBX sha256), every
 // sample passing Sub01TypingProfileSample, at a pitch/roll-free unit-scale body. It is bound here only when no other
 // profile is already bound (the proxy copies arm samples only when their count changes); otherwise typing stays pending.
 if(UAnimSequence* SeatedTyping=SeatClips.FindRef(TEXT("DeskTyping"))){if(SeatedTyping->GetPathName()==TEXT("@@SEATED_TYPING_PATH@@")){
  SeatProfilePoseLoaded=false;FString TypingWhy;auto* TypingHands=FirstPersonBody?Cast<USub01HomeHandsInstance>(FirstPersonBody->GetAnimInstance()):nullptr;
  FString TypingReceiptText,TypingProfileText,TypingGlb,TypingFbx;bool TypingCommitted=false;TSharedPtr<FJsonObject> TypingReceipt,TypingProfile;const TArray<TSharedPtr<FJsonValue>> *TypingRows=nullptr,*TypingSamples=nullptr,*TypingBody=nullptr,*TypingRotation=nullptr,*TypingScale=nullptr;
  if(FFileHelper::LoadFileToString(TypingReceiptText,*FPaths::Combine(FPaths::ProjectDir(),TEXT("@@SEATED_FIT_RECEIPT@@")))&&FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(TypingReceiptText),TypingReceipt)&&TypingReceipt.IsValid()&&TypingReceipt->TryGetArrayField(TEXT("clips"),TypingRows))
   for(const auto& RowValue:*TypingRows){const TSharedPtr<FJsonObject>* Row=nullptr;FString Role,Object;bool A=false,F=false,Same=false;
    if(RowValue.IsValid()&&RowValue->TryGetObject(Row)&&(*Row)->TryGetStringField(TEXT("role"),Role)&&Role==TEXT("@@SEATED_TYPING_ROLE@@")&&(*Row)->TryGetStringField(TEXT("object_path"),Object)&&Object==SeatedTyping->GetPathName()
       &&(*Row)->TryGetBoolField(TEXT("accepted"),A)&&A&&(*Row)->TryGetBoolField(TEXT("fit_pass"),F)&&F&&(*Row)->TryGetBoolField(TEXT("same_existing_skeleton"),Same)&&Same){(*Row)->TryGetStringField(TEXT("glb_sha256"),TypingGlb);(*Row)->TryGetStringField(TEXT("fbx_sha256"),TypingFbx);
     TypingCommitted=Sub01SeatedFitCommitted(SeatedFitVerdicts,SeatedFitVerdictCount,TEXT("@@SEATED_TYPING_ROLE@@"),A,F,*TypingGlb);}}
  FString TypingSchema,TypingProfileClip,TypingProfileGlb,TypingProfileFbx;double TypingSpread=NAN,TypingYaw=NAN;bool TypingReady=false;
  if(!TypingHands)TypingWhy=TEXT("no hands instance");
  else if(TypingHands->ContactTimes.Num()&&TypingHands->ContactSequence!=SeatedTyping)TypingWhy=TEXT("another clip's contact profile is already bound (launch without -Sub01ContactProfile)");
  else if(TypingGlb.IsEmpty()||TypingFbx.IsEmpty())TypingWhy=TEXT("no accepted import receipt row for the seated typing clip");
  else if(!FFileHelper::LoadFileToString(TypingProfileText,*FPaths::Combine(Audit,TEXT("@@SEATED_TYPING_PROFILE_FILE@@")))||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(TypingProfileText),TypingProfile)||!TypingProfile.IsValid())TypingWhy=TEXT("no seated typing profile");
  else if(!TypingProfile->TryGetStringField(TEXT("schema"),TypingSchema)||TypingSchema!=TEXT("@@SEATED_TYPING_PROFILE_SCHEMA@@")||!TypingProfile->TryGetBoolField(TEXT("ready"),TypingReady)||!TypingReady)TypingWhy=TEXT("profile schema/readiness");
  else if(!TypingProfile->TryGetStringField(TEXT("clip_object_path"),TypingProfileClip)||TypingProfileClip!=SeatedTyping->GetPathName()||!TypingProfile->TryGetStringField(TEXT("glb_sha256"),TypingProfileGlb)||TypingProfileGlb!=TypingGlb||!TypingProfile->TryGetStringField(TEXT("fbx_sha256"),TypingProfileFbx)||TypingProfileFbx!=TypingFbx)TypingWhy=TEXT("profile is bound to another clip, GLB or FBX");
  else if(!TypingProfile->TryGetNumberField(TEXT("key_top_spread_cm"),TypingSpread)||!TypingProfile->TryGetArrayField(TEXT("samples"),TypingSamples)||TypingSamples->Num()!=FSub01TypingProfileRules::Samples)TypingWhy=TEXT("profile samples");
  else if(!TypingProfile->TryGetArrayField(TEXT("body_cm"),TypingBody)||TypingBody->Num()!=3||!TypingProfile->TryGetNumberField(TEXT("body_yaw"),TypingYaw)||!TypingProfile->TryGetArrayField(TEXT("body_rotation_pyr"),TypingRotation)||TypingRotation->Num()!=3||!TypingProfile->TryGetArrayField(TEXT("body_scale_xyz"),TypingScale)||TypingScale->Num()!=3
          ||(*TypingRotation)[0]->AsNumber()!=0||(*TypingRotation)[1]->AsNumber()!=TypingYaw||(*TypingRotation)[2]->AsNumber()!=0||(*TypingScale)[0]->AsNumber()!=1||(*TypingScale)[1]->AsNumber()!=1||(*TypingScale)[2]->AsNumber()!=1)TypingWhy=TEXT("profile body transform (pitch/roll-free, unit scale)");
  else if(!TypingCommitted)TypingWhy=TEXT("@@SEATED_TYPING_UNCOMMITTED@@");
  TArray<float> TypingTimes;TArray<FName> TypingNames;TArray<FTransform> TypingValues;
  for(int32 I=0;TypingWhy.IsEmpty()&&I<TypingSamples->Num();++I){
   const TSharedPtr<FJsonObject>* Row=nullptr;const TSharedPtr<FJsonObject> *Corrected=nullptr,*Arms=nullptr;const TArray<TSharedPtr<FJsonValue>>* HandRows=nullptr;double Time=NAN,Bone=NAN,Finger=NAN,Invalid=NAN,Top=NAN;
   if(!(*TypingSamples)[I]->TryGetObject(Row)||!(*Row)->TryGetNumberField(TEXT("time"),Time)||!(*Row)->TryGetNumberField(TEXT("bone_length_max_error_cm"),Bone)||!(*Row)->TryGetNumberField(TEXT("finger_local_max_error_degrees"),Finger)
      ||!(*Row)->TryGetObjectField(TEXT("corrected"),Corrected)||!(*Corrected)->TryGetNumberField(TEXT("invalidInfluences"),Invalid)||!(*Corrected)->TryGetNumberField(TEXT("keyTopCm"),Top)
      ||!(*Corrected)->TryGetArrayField(TEXT("hands"),HandRows)||HandRows->Num()!=2||!(*Row)->TryGetObjectField(TEXT("corrected_local_arms"),Arms)){TypingWhy=FString::Printf(TEXT("sample %d incomplete"),I);break;}
   double Low[2]={NAN,NAN},Pen[2]={NAN,NAN},Over[2]={NAN,NAN};const TCHAR* Sides[2]={TEXT("left"),TEXT("right")};
   for(int32 S=0;S<2;++S){const TSharedPtr<FJsonObject>* H=nullptr;FString Side;if((*HandRows)[S]->TryGetObject(H)&&(*H)->TryGetStringField(TEXT("side"),Side)&&Side==Sides[S]){(*H)->TryGetNumberField(TEXT("overMinCm"),Low[S]);(*H)->TryGetNumberField(TEXT("penetrationCm"),Pen[S]);(*H)->TryGetNumberField(TEXT("overKeyVertices"),Over[S]);}}
   if(!Sub01TypingProfileSample(I,Time,TypingSpread,Bone,Finger,Invalid,Top,Low,Pen,Over)){TypingWhy=FString::Printf(TEXT("sample %d outside the typing contact gates"),I);break;}
   if(TypingNames.IsEmpty()){for(const auto& Pair:(*Arms)->Values)TypingNames.Add(FName(*Pair.Key));TypingNames.Sort([](const FName& A,const FName& B){return A.LexicalLess(B);});}
   if(TypingNames.Num()!=6||(*Arms)->Values.Num()!=6){TypingWhy=TEXT("profile must hold six arm bones only");break;}
   TypingTimes.Add(Time);
   for(const auto& Name:TypingNames){const TSharedPtr<FJsonObject>* T=nullptr;const TArray<TSharedPtr<FJsonValue>> *Pv=nullptr,*Qv=nullptr,*Sv=nullptr;
    if(!(*Arms)->TryGetObjectField(Name.ToString(),T)||!(*T)->TryGetArrayField(TEXT("translation"),Pv)||!(*T)->TryGetArrayField(TEXT("rotation"),Qv)||!(*T)->TryGetArrayField(TEXT("scale"),Sv)||Pv->Num()!=3||Qv->Num()!=4||Sv->Num()!=3){TypingWhy=TEXT("malformed arm transform");break;}
    const FQuat Q((*Qv)[0]->AsNumber(),(*Qv)[1]->AsNumber(),(*Qv)[2]->AsNumber(),(*Qv)[3]->AsNumber());const FVector Sc((*Sv)[0]->AsNumber(),(*Sv)[1]->AsNumber(),(*Sv)[2]->AsNumber());
    if(Q.ContainsNaN()||FMath::Abs(Q.SizeSquared()-1)>.001||Sc.ContainsNaN()||Sc.GetMin()<=0){TypingWhy=TEXT("invalid arm transform");break;}
    TypingValues.Add(FTransform(Q,FVector((*Pv)[0]->AsNumber(),(*Pv)[1]->AsNumber(),(*Pv)[2]->AsNumber()),Sc));}
  }
  if(TypingWhy.IsEmpty()&&TypingValues.Num()==TypingTimes.Num()*6&&TypingTimes.Num()==FSub01TypingProfileRules::Samples){
   TypingHands->ContactSequence=SeatedTyping;TypingHands->ContactTimes=MoveTemp(TypingTimes);TypingHands->ContactBones=MoveTemp(TypingNames);TypingHands->ContactLocalTransforms=MoveTemp(TypingValues);
   SeatProfilePose=FSub01SeatLivePose();SeatProfilePose.X=(*TypingBody)[0]->AsNumber();SeatProfilePose.Y=(*TypingBody)[1]->AsNumber();SeatProfilePose.Z=(*TypingBody)[2]->AsNumber();
   SeatProfilePose.PitchDeg=0;SeatProfilePose.YawDeg=TypingYaw;SeatProfilePose.RollDeg=0;SeatProfilePose.ScaleX=SeatProfilePose.ScaleY=SeatProfilePose.ScaleZ=1;
   SeatProfilePoseLoaded=Sub01SeatTransformFinite(SeatProfilePose);
   UE_LOG(LogTemp,Display,TEXT("SUB01_SEATED_TYPING_PROFILE_BOUND %s samples=%d glb=%s; arms only, captured finger locals retained"),*SeatedTyping->GetPathName(),TypingHands->ContactTimes.Num(),*TypingGlb);
  }else UE_LOG(LogTemp,Warning,TEXT("SUB01_SEATED_TYPING_PROFILE_REFUSED %s: %s; typing stays pending"),*SeatedTyping->GetPathName(),TypingWhy.IsEmpty()?TEXT("incomplete"):*TypingWhy);
 }}
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
// The actual surface under one sole's footprint: three downward traces against complex
// collision (heel/ankle, mid-foot, toe) must all hit the same component, flat (normal Z >= 0.98)
// and level within 0.2 cm. The sole gap is then measured to that surface, not the capsule floor.
bool ASub01HomeCharacter::SeatSoleSupport(int32 Side,double& FloorZ,FString& Surface) const{
 FloorZ=NAN;Surface.Reset();if(!FirstPersonBody||!FirstPersonBody->GetSkeletalMeshAsset()||!GetWorld())return false;
 const auto& Ref=FirstPersonBody->GetSkeletalMeshAsset()->GetRefSkeleton();FName Foot,Toe;
 for(int32 I=0;I<Ref.GetNum();++I){const FString Name=Ref.GetBoneName(I).ToString();
  if(Name.EndsWith(Side?TEXT("RightFoot"):TEXT("LeftFoot")))Foot=Ref.GetBoneName(I);else if(Name.EndsWith(Side?TEXT("RightToeBase"):TEXT("LeftToeBase")))Toe=Ref.GetBoneName(I);}
 if(Foot.IsNone()||Toe.IsNone())return false;
 const FVector A=FirstPersonBody->GetBoneLocation(Foot),B=FirstPersonBody->GetBoneLocation(Toe);const FVector Points[3]={A,(A+B)/2,B};
 FCollisionQueryParams Params(TEXT("Sub01SoleSupport"),true,this);const UPrimitiveComponent* Component=nullptr;double Low=DBL_MAX,High=-DBL_MAX;
 for(const FVector& P:Points){FHitResult Hit;
  if(!GetWorld()->LineTraceSingleByChannel(Hit,P+FVector(0,0,20),P-FVector(0,0,60),ECC_Visibility,Params)||!Hit.bBlockingHit||Hit.bStartPenetrating||Hit.ImpactNormal.Z<.98)return false;
  if(Component&&Hit.GetComponent()!=Component)return false;Component=Hit.GetComponent();Low=FMath::Min(Low,Hit.ImpactPoint.Z);High=FMath::Max(High,Hit.ImpactPoint.Z);}
 if(!Component||High-Low>.2)return false;
 FloorZ=High;Surface=Component->GetPathName();return true;
}
void ASub01HomeCharacter::UpdateSeatTransition(float Dt){
 if(!LiveHome)return;const double Now=FPlatformTime::Seconds();
 const bool DeskActivity=LiveHomeActivity==TEXT("use_computer")||LiveHomeActivity==TEXT("research")||LiveHomeActivity==TEXT("chart")||LiveHomeActivity==TEXT("chat")||LiveHomeActivity==TEXT("watch_video")||LiveHomeActivity==TEXT("play_chess");
 FSub01SeatInputs In;In.NowSeconds=Now;
 In.Command=Sub01SeatId(*FString::Printf(TEXT("%s|%lld|%s"),*LiveHomeEpoch,LiveHomeCommandSequence,*LiveHomeActivity));
 In.WantSeat=SeatAnchorValid&&LiveHomeTarget==TEXT("desk")&&LiveHomeNode==TEXT("desk")&&LiveHomePath.Num()==0&&DeskActivity;
 In.WantTyping=In.WantSeat&&(LiveHomeActivity==TEXT("use_computer")||LiveHomeActivity==TEXT("research")||LiveHomeActivity==TEXT("chart"));
 In.Fresh=LiveHomeFresh&&Now>=LiveHomeLastReceived&&Now-LiveHomeLastReceived<=3;In.Private=LiveHomePrivate;In.Blocked=LiveHomeBlocked;
 // Seat clips play only while the renderer's posture gate holds (Walk bound, no hands failure).
 const bool PostureGate=HandsFailure.IsEmpty()&&HandsPosture==TEXT("Walk");
 In.ChairMeasured=SeatChairMeasured;In.ChairRevision=SeatChairRevision;In.RolesAvailable=PostureGate?SeatRoles:0;
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
  // against the audited cushion. Each sole is measured to the surface actually under its own
  // footprint (an office rug is 3 cm where the capsule arrives, the floor 2.5 cm elsewhere).
  if(L.ClipPlaying&&SeatCushionTriangles.Num()&&Now-SeatMeasuredAt>=.2){
   SeatMeasuredAt=Now;SeatMeasurement=FSub01SeatMeasurement();
   FSub01SeatMeasurement M;M.MeshId=L.MeshId;M.ChairRevision=SeatChairRevision;M.ClipSerial=In.ClipSerial;M.MeasuredAt=Now;
   M.X=L.X;M.Y=L.Y;M.Z=L.Z;M.PitchDeg=L.PitchDeg;M.YawDeg=L.YawDeg;M.RollDeg=L.RollDeg;M.ScaleX=L.ScaleX;M.ScaleY=L.ScaleY;M.ScaleZ=L.ScaleZ;
   FString Surfaces[2],Reports[2];bool Complete=true;
   for(int32 Side=0;Side<2;++Side){
    M.SoleSupportVerified[Side]=SeatSoleSupport(Side,M.SoleFloorZ[Side],Surfaces[Side]);
    if(!M.SoleSupportVerified[Side]){Complete=false;continue;}
    Reports[Side]=USub01HomeHandsInstance::AnalyzeCapturedSeatSkin(FirstPersonBody->GetSkeletalMeshAsset(),FirstPersonBody->GetComponentSpaceTransforms(),FirstPersonBody->GetComponentTransform(),SeatCushionTriangles,M.SoleFloorZ[Side]);
    TSharedPtr<FJsonObject> J;const TArray<TSharedPtr<FJsonValue>>* Regions=nullptr;double Invalid=-1;
    if(!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Reports[Side]),J)||!J.IsValid()||J->HasField(TEXT("error"))||!J->TryGetNumberField(TEXT("invalidInfluences"),Invalid)||!J->TryGetArrayField(TEXT("regions"),Regions)||Regions->Num()!=5){Complete=false;continue;}
    M.InvalidInfluences=FMath::Max(M.InvalidInfluences,int(Invalid));
    const TCHAR* Names[5]={TEXT("buttocks"),TEXT("left_posterior_thigh"),TEXT("right_posterior_thigh"),TEXT("left_sole"),TEXT("right_sole")};
    // Seat patches (cushion, independent of the floor) from the left pass; each sole from its own pass.
    for(int32 I=0;I<5;++I){if(I==3+(1-Side)||(Side==1&&I<3))continue;
     const auto R=(*Regions)[I]->AsObject();FString Name;double Facing=0,Over=0,Band=0;
     if(!R->TryGetStringField(TEXT("region"),Name)||Name!=Names[I]||!R->TryGetNumberField(TEXT("facingVertices"),Facing)||!R->TryGetNumberField(TEXT("overSurfaceVertices"),Over)||!R->TryGetNumberField(TEXT("bandVertices"),Band)
        ||!R->TryGetNumberField(TEXT("minGapCm"),M.MinGap[I])||!R->TryGetNumberField(TEXT("p50GapCm"),M.Median[I])||Over<=0){Complete=false;break;}
     M.Facing[I]=int(Facing);M.Coverage[I]=Band/Over;M.BandCount[I]=Band;}
   }
   M.Valid=Complete;SeatMeasurement=M;
   const int32 InBand=Sub01SeatMeasuredReceipt(SeatMeasurement,L,In.ClipSerial,Now)?1:0;
   if(InBand!=SeatMeasurementLogged){SeatMeasurementLogged=InBand;UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_LIVE_MEASUREMENT inBand=%d soles=[%s %.4f | %s %.4f] %s"),InBand,*Surfaces[0],M.SoleFloorZ[0],*Surfaces[1],M.SoleFloorZ[1],*Reports[0].Left(600));}
  }
  In.Receipt=Sub01SeatReceipt(SeatEvidence,L)||Sub01SeatMeasuredReceipt(SeatMeasurement,L,In.ClipSerial,Now);
 }
 // Typing only with the accepted keyboard profile bound to the typing clip AND the live body at
 // the transform that profile was audited at; otherwise he stays in the Sitting idle.
 UAnimSequence* TypingClip=SeatClips.FindRef(TEXT("DeskTyping"));
 In.TypingProfileReady=Instance&&TypingClip&&Instance->ContactSequence==TypingClip&&Instance->ContactTimes.Num()==301&&Instance->ContactLocalTransforms.Num()==301*6
  &&SeatProfilePoseLoaded&&HasBody&&Sub01SeatSameTransform(SeatProfilePose,Live);
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
  if(!SetHandsPosture(TEXT("Walk")))UE_LOG(LogTemp,Warning,TEXT("SUB01_SEAT_POSTURE_GATE %s"),*HandsFailure);FName Head;const auto& Ref=FirstPersonBody->GetSkeletalMeshAsset()->GetRefSkeleton();
  for(int32 I=0;I<Ref.GetNum();++I)if(Ref.GetBoneName(I).ToString().EndsWith(TEXT("Head")))Head=Ref.GetBoneName(I);
  // Eye camera in world space, eased from wherever the view is now (never a one-frame drop to the Head joint).
  // The measured eye offset belongs to the original owner skin only; any other skin keeps the Head joint.
  if(!Head.IsNone()){
   SeatHead=Head;SeatEyeOffset=FirstPersonBody->GetSkeletalMeshAsset()->GetPathName()==TEXT("@@OWNER_MESH@@")?FVector(@@EYE_OFFSET@@):FVector::ZeroVector;
   if(!SeatCameraEasing)SeatEye=ViewCamera->GetComponentLocation();
   SeatCameraEasing=true;ViewCamera->SetUsingAbsoluteLocation(true);ViewCamera->SetUsingAbsoluteRotation(true);
  }
  SeatBodyAttached=true;
 }else if(!Seated&&SeatBodyAttached){
  // The camera eases back to the standing eye in UpdateSeatCamera and is then handed back to the capsule.
  SeatBodyAttached=false;
 }
 UpdateSeatCamera(Dt);
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
void ASub01HomeCharacter::UpdateSeatCamera(float Dt){
 if(!SeatCameraEasing||!ViewCamera||!FirstPersonBody)return;
 // Standing eye: the renderer's capsule-relative camera (0,0,74). Seated: the captured Head socket at the eye.
 const FVector Standing=GetRootComponent()->GetComponentTransform().TransformPosition(FVector(0,0,74));
 FVector Target=Standing;
 if(SeatBodyAttached&&!SeatHead.IsNone()){const FTransform H=FirstPersonBody->GetSocketTransform(SeatHead,RTS_World);Target=H.GetLocation()+H.GetRotation().GetNormalized().RotateVector(SeatEyeOffset);}
 if(Target.ContainsNaN())return;
 SeatEye=FMath::Lerp(SeatEye,Target,float(Sub01SeatEyeAlpha(Dt)));
 ViewCamera->SetWorldLocation(SeatEye);
 if(!SeatBodyAttached&&FVector::Dist(SeatEye,Standing)<.5f){
  ViewCamera->SetUsingAbsoluteLocation(false);ViewCamera->SetUsingAbsoluteRotation(false);
  ViewCamera->AttachToComponent(GetRootComponent(),FAttachmentTransformRules::KeepWorldTransform);
  ViewCamera->SetRelativeLocation(FVector(0,0,74));ViewCamera->SetRelativeRotation(FRotator::ZeroRotator);SeatCameraEasing=false;
 }
}
void ASub01HomeCharacter::ApplySeatAnimation(USub01HomeHandsInstance* Instance){
 if(!Instance||SeatOut.Clip==ESub01SeatClip::None||!HandsFailure.IsEmpty()||HandsPosture!=TEXT("Walk"))return;
 static const TCHAR* ClipRoles[]={TEXT(""),TEXT("StandToSit"),TEXT("Sitting"),TEXT("SitToType"),TEXT("DeskTyping"),TEXT("SitToStand")};
 if(UAnimSequence* Clip=SeatClips.FindRef(ClipRoles[uint8(SeatOut.Clip)])){Instance->TargetSequence=Clip;Instance->TargetRate=1.f;}
}
'''

HANDS_FIELDS = r'''
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
    '  Hands->SeatEvaluatedSequence=SeatEvaluatedSequence;Hands->SeatEvaluatedSerial=SeatEvaluatedSerial;Hands->SeatEvaluatedTime=SeatEvaluatedTime;\n'
    '  if(SeatSerial!=Hands->SeatStartSerial&&Current.GetSequence()==Hands->SeatStartSequence.Get()){\n'
    '   SeatSerial=Hands->SeatStartSerial;\n'
    '   if(Hands->SeatStartSequence&&!(ContactTimes.Num()&&Current.GetSequence()==ContactSequence)){Current.SetAccumulatedTime(Hands->SeatStartSeconds);Current.SetLoopAnimation(!Hands->SeatNoLoop);}\n'
    '  }\n')
PROXY_EVALUATED = ('  SeatEvaluatedSequence=Cast<UAnimSequence>(Current.GetSequence());SeatEvaluatedTime=SeatEvaluatedSequence?Current.GetAccumulatedTime():-1.f;'
                   'SeatEvaluatedSerial=SeatSerial;\n')

SEAT_RATE_ANCHOR = 'Instance->TargetRate=HandsPosture==TEXT("Walk")?(Moving?float(Sub01FirstPersonMotion::AuthoredWalkRate(Speed)):(PlayingIdle?1.f:0.f)):1.f;\n'

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


# (file key, anchor, replacement); every anchor must occur exactly once in the staged source.
EDITS = [
    ('header', '#include "Sub01HomeLab.generated.h"', CHARACTER_INCLUDE + '#include "Sub01HomeLab.generated.h"'),
    ('header', ' void Forward(float Value);', CHARACTER_FIELDS + '\n void Forward(float Value);'),
    ('cpp', ' BeginLiveHome();\n', ' BeginLiveHome();\n LoadSeatTransition();\n'),
    ('cpp', ' UpdateNativeFeedback();\n', ' UpdateNativeFeedback();\n UpdateSeatTransition(Dt);\n'),
    ('cpp', ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(',
     ' // A seated body never walks off: the captured get-up must finish first.\n'
     ' if(!SeatOut.MovementInput&&LiveHomePath.Num()){GetCharacterMovement()->StopMovementImmediately();if(PCBridge)PCBridge->SetOperatorFocus(false);return;}\n'
     ' if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus('),
    ('cpp', SEAT_RATE_ANCHOR, SEAT_RATE_ANCHOR + ' ApplySeatAnimation(Instance);\n'),
    ('hands_header', ' protected:', HANDS_FIELDS + ' protected:'),
    ('hands_cpp', ' float Progress=1;\n',
     ' float Progress=1;\n int32 SeatSerial=0,SeatEvaluatedSerial=0;UAnimSequence* SeatEvaluatedSequence=nullptr;float SeatEvaluatedTime=-1;\n'),
    ('hands_cpp', '  Current.SetPlayRate(Hands->TargetRate);\n', PROXY_APPLY + '  Current.SetPlayRate(Hands->TargetRate);\n'),
    ('hands_cpp', '  Blend.Evaluate_AnyThread(Output);\n', '  Blend.Evaluate_AnyThread(Output);\n' + PROXY_EVALUATED),
]


def install(sources: dict, verdicts=None) -> dict:
    """Apply the seat integration to staged sources {'header','cpp','hands_header','hands_cpp'}.

    The committed seated-fit verdict table is generated here (committed_seated_fit_verdicts(), i.e. plan_clips());
    if plan_clips refuses, nothing is installed.
    """
    table = seated_fit_verdict_table_cpp(committed_seated_fit_verdicts() if verdicts is None else verdicts)
    out = dict(sources)
    for key, anchor, replacement in EDITS:
        if anchor == SEAT_RATE_ANCHOR:
            live = _resolve_rate_line(out[key], anchor)
            anchor, replacement = live, replacement.replace(SEAT_RATE_ANCHOR, live)
        if out[key].count(anchor) != 1:
            raise ValueError(f'Seat integration anchor not unique in {key}: {anchor[:60]!r}')
        out[key] = out[key].replace(anchor, replacement)
    bindings = ','.join('{TEXT("%s"),TEXT("%s"),SeatRole%s}' % (role, asset, role)
                        for role, asset in SEAT_ROLE_ASSETS.items())
    fits = ','.join('{TEXT("%s"),TEXT("%s"),%s}' % (role, slot, bit) for role, (slot, bit) in SEATED_FIT_SLOTS.items())
    out['cpp'] += (CHARACTER_METHODS.replace('@@SEAT_EYE_ALPHA@@', SEAT_EYE_ALPHA_CPP).replace('@@OWNER_MESH@@', OWNER_MESH)
                   .replace('@@EYE_OFFSET@@', ','.join(repr(v) for v in EYE_OFFSET_HEAD_CM))
                   .replace('@@SEAT_CLIP_DIR@@', SEAT_CLIP_DIR).replace('@@SEAT_ROLE_BINDINGS@@', bindings)
                   .replace('@@SEATED_FIT_BINDINGS@@', fits).replace('@@SEATED_FIT_RECEIPT@@', SEATED_FIT_RECEIPT)
                   .replace('@@SEATED_FIT_SCHEMA@@', SEATED_FIT_RECEIPT_SCHEMA)
                   .replace('@@SEATED_FIT_VERDICTS@@', table)
                   .replace('@@SEATED_TYPING_UNCOMMITTED@@', SEATED_TYPING_UNCOMMITTED)
                   .replace('@@SEATED_TYPING_PATH@@', seated_fit_object_path(SEATED_TYPING_ROLE))
                   .replace('@@SEATED_TYPING_ROLE@@', SEATED_TYPING_ROLE)
                   .replace('@@SEATED_TYPING_PROFILE_FILE@@', SEATED_TYPING_PROFILE_FILE)
                   .replace('@@SEATED_TYPING_PROFILE_SCHEMA@@', SEATED_TYPING_PROFILE_SCHEMA))
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
