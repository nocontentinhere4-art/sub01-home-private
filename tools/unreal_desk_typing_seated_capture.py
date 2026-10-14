"""SERVER UE editor capture (root only): the IMPORTED seated-fit typing clip on the ACTUAL owner mesh against the actual
keycaps, every 60 Hz frame of the whole clip, at the measured seat placement. Observation only.

    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject \
        -ExecutePythonScript="<repo>/tools/unreal_desk_typing_seated_capture.py" -unattended

then, on any CPU:

    python3 tools/desk_typing_seated_contact_profile.py <project> <project>/private-audit/desk-typing-seated-contact-capture.json

Pattern: tools/unreal_audit_skinned_contact.py (the renderer's keyboard profile audit of the OLD clip), unchanged in
method: AnimationLibrary.get_bone_poses_for_time composed down the parent chain, the renderer's native
USub01HomeHandsInstance.AnalyzeCapturedFingerSkin (imported soft vertices, distal-weight >= 0.30, over-key test against
the actual keycap top triangles) before and after the renderer's native SolveCapturedKeyboardArmContact (the existing
Sub01KeyboardContactCorrection, 0.08 cm target, 12 cm cap), then the corrected six arm locals and the bone-length,
finger and wrist errors exactly as that audit computes them. Both natives are BlueprintCallable already, so no C++ hook
is installed here.

Inputs (every one read from the server, nothing defaulted; any missing or inconsistent input refuses, writing nothing):
  * <project>/private-audit/unreal-seated-fit-import.json (tools/unreal_import_seated_fit_fbx.py): the DeskTypingSeated
    row must be imported, accepted, fit_pass, same_existing_skeleton, at /Game/Sub01Hands/Seating/SUB01_DeskTypingSeated,
    60 fps, with its GLB sha256 equal to the committed fit GLB. The clip is loaded from that path and must be on the owner
    skeleton with the receipt's length; frames = the receipt's GLB key count, at t = frame / 60 (the whole clip).
  * <project>/private-audit/native-seat-evidence.json (the seat adapter's measured body anchor, LoadSeatTransition) and
    <project>/private-audit/native-chair-surface.json (its chair revision must be the evidence's): the body is posed
    at the evidence's full transform (location, pitch/yaw/roll, 3-axis scale).
  * <project>/../../keyboard-keycaps-world.json, bound to <project>/SourceAssets/full-home.glb by sha256, 87 keycaps,
    top spread at most 0.2 cm (the same keycap source and checks as tools/unreal_audit_skinned_contact.py). The native
    home has no SUB01Device keyboard tag (tools/unreal_setup_home.py tags Desk/Kitchen/Bed/TV only), so the keycaps
    are the actual extracted keycap geometry of the imported house source, as for the renderer's profile.
Writes <project>/private-audit/desk-typing-seated-contact-capture.json (schema below), atomically. It changes no mesh,
actor, pose, asset, config, receipt or profile and claims no contact or readiness: acceptance is the offline
evaluator's, from this observation only.
NOT RUN in this repository (no engine here); tests/test_desk_typing_seated_contact_profile.py runs it on a fake engine.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import uuid
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_import_seated_fit_fbx as seated_import  # noqa: E402  (no unreal at import)

CAPTURE_SCHEMA = 'sub01.desk-typing-seated-contact-capture.v1'
CAPTURE_FILE = 'desk-typing-seated-contact-capture.json'          # in <project>/private-audit/
OBSERVATION = 'native_editor_clip_evaluation'
SKIN_ANALYZER = 'USub01HomeHandsInstance::AnalyzeCapturedFingerSkin'
ARM_SOLVER = 'USub01HomeHandsInstance::SolveCapturedKeyboardArmContact'
ROLE = seat.SEATED_TYPING_ROLE
RATE_HZ = 60
EVIDENCE_FILE = 'native-seat-evidence.json'
CHAIR_FILE = 'native-chair-surface.json'
KEYCAPS_FILE = 'keyboard-keycaps-world.json'                       # <project>/../../ as unreal_audit_skinned_contact.py
HOUSE_SOURCE = 'SourceAssets/full-home.glb'
KEYCAP_COUNT = 87                                                   # unreal_audit_skinned_contact.py
KEY_TOP_SPREAD_MAX_CM = .2                                          # unreal_audit_skinned_contact.py / DistalGap
FINGERS = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')


class Refused(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def receipt_row(receipt: dict) -> dict:
    """The accepted DeskTypingSeated import row, or Refused (the same conditions the seat adapter binds the slot on)."""
    if not isinstance(receipt, dict) or receipt.get('schema') != seat.SEATED_FIT_RECEIPT_SCHEMA \
            or receipt.get('skeleton') != seat.OWNER_SKELETON:
        raise Refused('ReceiptMissing: no seated-fit import receipt on the owner skeleton')
    rows = [r for r in receipt.get('clips', []) if isinstance(r, dict) and r.get('role') == ROLE]
    if len(rows) != 1:
        raise Refused(f'ReceiptRow: expected exactly one {ROLE} row, found {len(rows)}')
    row = rows[0]
    path = seat.seated_fit_object_path(ROLE)
    for field, want in (('imported', True), ('accepted', True), ('fit_pass', True), ('same_existing_skeleton', True),
                        ('object_path', path), ('fps', RATE_HZ), ('glb_sha256', seated_import.GLB_SHA256[ROLE])):
        if row.get(field) != want:
            raise Refused(f'ReceiptRow: {ROLE} {field}={row.get(field)!r}, expected {want!r}')
    if not isinstance(row.get('fbx_sha256'), str) or len(row['fbx_sha256']) != 64:
        raise Refused(f'ReceiptRow: {ROLE} has no FBX sha256')
    frames, duration = row.get('frames'), row.get('glb_duration_s')
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 2 \
            or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise Refused(f'ReceiptRow: {ROLE} frames/duration missing')
    if abs((frames - 1) / RATE_HZ - duration) > 1e-3:
        raise Refused(f'ReceiptRow: {frames} keys do not span {duration} s at {RATE_HZ} Hz')
    return row


def frame_times(frames: int, duration: float) -> list:
    """Every key of the whole clip: t = frame / 60, the last clamped to the imported length."""
    return [min(f / RATE_HZ, duration) for f in range(frames)]


def placement(evidence_text: str, chair_text: str) -> dict:
    """The seat adapter's measured body anchor (native-seat-evidence.json), bound to the current chair report."""
    evidence = json.loads(evidence_text)
    if evidence.get('schema') != 'sub01.native-seat-evidence.v1' or evidence.get('family') != 'DeskTyping':
        raise Refused('PlacementMissing: native-seat-evidence.json is not the seat adapter evidence')
    if str(evidence.get('chair_revision')) != str(seat.seat_id(chair_text)):
        raise Refused('PlacementStale: native-seat-evidence.json was measured on another chair report')
    body, rotation, scale = evidence.get('body_cm'), evidence.get('body_rotation_pyr'), evidence.get('body_scale_xyz')
    values = (body or []) + (rotation or []) + (scale or [])
    if not (isinstance(body, list) and isinstance(rotation, list) and isinstance(scale, list)
            and len(body) == 3 and len(rotation) == 3 and len(scale) == 3
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
            and min(scale) > 0):
        raise Refused('PlacementMissing: the evidence has no finite body location, pitch/yaw/roll and positive scale')
    return {'body_cm': list(body), 'body_rotation_pyr': list(rotation), 'body_scale_xyz': list(scale),
            'chair_revision': str(evidence['chair_revision'])}


def keycaps(caps: dict, house_sha256: str) -> dict:
    """The actual extracted keycap tops (same checks as tools/unreal_audit_skinned_contact.py)."""
    if caps.get('sourceSHA256') != house_sha256:
        raise Refused('KeyboardStale: keycap geometry does not match the imported house source')
    tops = [p[2] for cap in caps.get('keycaps', []) for tri in cap['topTrianglesUECm'] for p in tri]
    if len(caps.get('keycaps', [])) != KEYCAP_COUNT or not tops:
        raise Refused(f'KeyboardMissing: expected {KEYCAP_COUNT} keycaps with top triangles')
    spread = max(tops) - min(tops)
    if spread > KEY_TOP_SPREAD_MAX_CM:
        raise Refused('KeyboardSpread: key top spread exceeds 2 mm; per-triangle height required before contact acceptance')
    bounds = caps['geometryBoundsUECm']
    return {'triangles': [p for cap in caps['keycaps'] for tri in cap['topTrianglesUECm'] for p in tri],
            'min_cm': list(bounds['minCm']), 'max_cm': list(bounds['maxCm']), 'key_top_spread_cm': spread}


def _quat_degrees(a, b) -> float:
    dot = abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w)
    return math.degrees(2 * math.acos(min(1., dot)))


def sample(u, mesh, clip, names, parents, time, body, key_min, key_max, key_triangles) -> dict:
    """One frame, exactly as tools/unreal_audit_skinned_contact.py computes a row (the renderer's natives)."""
    poses = u.AnimationLibrary.get_bone_poses_for_time(clip, names, time, False, mesh)
    local = {str(n): p for n, p in zip(names, poses)}
    resolved = {}

    def component(n):
        if n not in resolved:
            par = parents[n]
            resolved[n] = u.MathLibrary.compose_transforms(local[n], component(par)) if par in local else local[n]
        return resolved[n]
    pose = [component(str(n)) for n in names]
    hands = u.Sub01HomeHandsInstance
    report = json.loads(hands.analyze_captured_finger_skin(mesh, pose, body, key_min, key_max, key_triangles))
    corrected = hands.solve_captured_keyboard_arm_contact(mesh, pose, body, key_min, key_max, key_triangles)
    after = json.loads(hands.analyze_captured_finger_skin(mesh, corrected, body, key_min, key_max, key_triangles))
    by_name = {str(n): t for n, t in zip(names, corrected)}
    finger_error = length_error = wrist_error = 0.
    for name, t in by_name.items():
        parent = parents[name]
        if parent not in by_name:
            continue
        old_length = (resolved[name].translation - resolved[parent].translation).length()
        new_length = (t.translation - by_name[parent].translation).length()
        length_error = max(length_error, abs(old_length - new_length))
        if name.endswith('LeftHand') or name.endswith('RightHand'):
            wrist_error = max(wrist_error, _quat_degrees(t.rotation, resolved[name].rotation))
        if any('Hand' + finger in name for finger in FINGERS):
            relative = u.MathLibrary.compose_transforms(t, u.MathLibrary.invert_transform(by_name[parent]))
            finger_error = max(finger_error, _quat_degrees(relative.rotation, local[name].rotation))
    arms, offsets = {}, {}
    for side in ('Left', 'Right'):
        hand = next(n for n in by_name if n.endswith(side + 'Hand'))
        offsets[side] = [by_name[hand].translation.z - resolved[hand].translation.z]
        for name in (hand, parents[hand], parents[parents[hand]]):
            parent = parents[name]
            t = (u.MathLibrary.compose_transforms(by_name[name], u.MathLibrary.invert_transform(by_name[parent]))
                 if parent in by_name else by_name[name])
            q, p, s = t.rotation, t.translation, t.scale3d
            arms[name] = {'translation': [p.x, p.y, p.z], 'rotation': [q.x, q.y, q.z, q.w], 'scale': [s.x, s.y, s.z]}
    if 'error' in report or 'error' in after:
        raise Refused(f'AnalyzerError: {report.get("error") or after.get("error")}')
    return {**report, 'corrected_local_arms': arms, 'corrected': after, 'arm_world_offsets_cm': offsets,
            'finger_local_max_error_degrees': finger_error, 'bone_length_max_error_cm': length_error,
            'wrist_world_max_error_degrees': wrist_error}


def main(u, root: Path | None = None) -> Path:
    root = Path(root or u.Paths.project_dir()).resolve()
    audit = root / 'private-audit'
    receipt_path = root / seat.SEATED_FIT_RECEIPT
    for path, why in ((receipt_path, 'ReceiptMissing'), (audit / EVIDENCE_FILE, 'PlacementMissing'),
                      (audit / CHAIR_FILE, 'ChairUnmeasured'), (root.parent.parent / KEYCAPS_FILE, 'KeyboardMissing'),
                      (root / HOUSE_SOURCE, 'KeyboardMissing')):
        if not path.is_file():
            raise Refused(f'{why}: {path} does not exist')
    receipt_raw = receipt_path.read_bytes()
    row = receipt_row(json.loads(receipt_raw))
    evidence_raw, chair_raw = (audit / EVIDENCE_FILE).read_bytes(), (audit / CHAIR_FILE).read_bytes()
    place = placement(evidence_raw.decode(), chair_raw.decode())
    caps_raw = (root.parent.parent / KEYCAPS_FILE).read_bytes()
    keys = keycaps(json.loads(caps_raw), sha256_bytes((root / HOUSE_SOURCE).read_bytes()))

    mesh = u.load_asset(seat.OWNER_MESH)
    clip = u.load_asset(row['object_path'])
    if not mesh or not isinstance(clip, u.AnimSequence):
        raise Refused(f'ClipMissing: owner mesh or {row["object_path"]} not loadable')
    skeleton = mesh.get_editor_property('skeleton')
    if clip.get_editor_property('skeleton') != skeleton or skeleton.get_path_name() != seat.OWNER_SKELETON:
        raise Refused('ClipSkeleton: the imported clip is not on the owner skeleton')
    if clip.get_path_name() != row['object_path']:
        raise Refused(f'ClipPath: loaded {clip.get_path_name()}, receipt names {row["object_path"]}')
    duration = float(clip.get_editor_property('sequence_length'))
    if abs(duration - row['glb_duration_s']) > seated_import.DURATION_TOLERANCE_S:
        raise Refused(f'ClipLength: {duration:.4f} s differs from the receipt {row["glb_duration_s"]:.4f} s')
    u.Sub01HomeHandsInstance.finish_pending_skin_compilation()
    probe = u.SkeletalMeshComponent()
    probe.set_skeletal_mesh_asset(mesh)
    names = [probe.get_bone_name(i) for i in range(probe.get_num_bones())]
    parents = {str(n): str(probe.get_parent_bone(n)) for n in names}
    pitch, yaw, roll = place['body_rotation_pyr']
    body = u.Transform(location=u.Vector(*place['body_cm']), rotation=u.Rotator(roll=roll, pitch=pitch, yaw=yaw),
                       scale=u.Vector(*place['body_scale_xyz']))
    key_min, key_max = u.Vector(*keys['min_cm']), u.Vector(*keys['max_cm'])
    key_triangles = [u.Vector(*p) for p in keys['triangles']]
    rows = []
    for frame, time in enumerate(frame_times(row['frames'], duration)):
        rows.append({'frame': frame, 'time': time,
                     **sample(u, mesh, clip, names, parents, time, body, key_min, key_max, key_triangles)})
    version = getattr(u.SystemLibrary, 'get_engine_version', None)
    capture = {
        'schema': CAPTURE_SCHEMA, 'observation': OBSERVATION, 'capture_id': uuid.uuid4().hex,
        'analyzer': {'skin': SKIN_ANALYZER, 'arm_solver': ARM_SOLVER, 'method': 'tools/unreal_audit_skinned_contact.py'},
        'engine_version': version() if version else None,
        'mesh': mesh.get_path_name(), 'skeleton': skeleton.get_path_name(),
        'clip': {'role': ROLE, 'object_path': clip.get_path_name(), 'sequence_length_s': duration, 'rate_hz': RATE_HZ,
                 'frames': row['frames'], 'glb_sha256': row['glb_sha256'], 'fbx_sha256': row['fbx_sha256']},
        'receipt': {'file': seat.SEATED_FIT_RECEIPT, 'sha256': sha256_bytes(receipt_raw), 'row': row},
        'placement': {'source': f'private-audit/{EVIDENCE_FILE}', 'sha256': sha256_bytes(evidence_raw),
                      'chair_surface_sha256': sha256_bytes(chair_raw), **place},
        'keyboard': {'file': KEYCAPS_FILE, 'sha256': sha256_bytes(caps_raw), 'keycaps': KEYCAP_COUNT,
                     'key_top_spread_cm': keys['key_top_spread_cm'], 'key_min_cm': keys['min_cm'], 'key_max_cm': keys['max_cm'],
                     'source': 'actual extracted keycap top triangles of SourceAssets/full-home.glb (no keyboard device tag exists)'},
        'frames': rows,
        'claims': {'contact_verified': False, 'typing_ready': False, 'note': 'observation only; the offline evaluator decides'},
    }
    out = audit / CAPTURE_FILE
    temp = out.with_name(out.name + f'.{capture["capture_id"]}.tmp')
    temp.write_text(json.dumps(capture) + '\n')
    temp.replace(out)
    u.log(f'SUB01_DESK_TYPING_SEATED_CAPTURE_WRITTEN {out} frames={len(rows)}')
    return out


if __name__ == '__main__':  # pragma: no cover - server only (Unreal Editor Python)
    import unreal
    main(unreal)
