"""Offline evaluator: the NATIVE seated typing capture -> the keyboard contact profile the seat adapter binds to the
seated-fit DeskTyping clip. Reads only that observation; it never creates one.

    python3 tools/desk_typing_seated_contact_profile.py <project> [<capture.json>]
        (default capture: <project>/private-audit/desk-typing-seated-contact-capture.json,
         written on the server by tools/unreal_desk_typing_seated_capture.py)
    python3 tools/desk_typing_seated_contact_profile.py --check <project> [<capture.json>]   # gates only, writes nothing

It ALWAYS writes <project>/private-audit/desk-typing-seated-contact-evaluation.json (ready true/false, every refusal),
and writes <project>/private-audit/desk-typing-seated-contact-profile.json (atomically) ONLY when every gate passes:

  binding   the capture is the renderer's native skin analyzer + arm solver observation, of the clip the import receipt
            accepted (the receipt read now is byte-identical to the one the capture read; object path, GLB and FBX
            sha256, 60 Hz, the committed fit GLB), covering the WHOLE clip: one frame per receipt key, t = frame / 60;
  placement the body was posed at the seat adapter's measured anchor (native-seat-evidence.json, on the current chair
            report, both byte-identical to what the capture read); the adapter's profile pose is pitch/roll-free and
            unit-scale, so any other evidence transform is refused rather than approximated;
  skin      every frame: no invalid influences, both hands selected (as tools/unreal_audit_skinned_contact.py asserts);
  typing    the 3..8 s window at 60 Hz (301 samples, the renderer's audited interval, the one the profile replays)
            passes tools/validate_unreal_contact_profile.py validate() (key gap <= 0.2 cm, penetration <= 0.1 cm,
            finger change <= 0.1 deg, no stretch over 0.01 cm, six arm bones only) and the adapter's own reader
            (unreal_seat_transition_runtime.seated_typing_profile_binding, the Python twin of the native
            Sub01TypingProfileSample binding: key-top spread at most 0.2 cm, gap + spread <= 0.2 cm).
No tolerance is defined here; all come from those files.

The renderer's profile for the OLD clip (<project>/unreal-skinned-contact-audit.json) is never opened for writing,
moved or deleted: the seated profile is a separate file, and the evaluation records the old file's sha256 before and
after. When a newer capture fails, an earlier seated profile is moved aside to
desk-typing-seated-contact-profile.superseded-<capture sha256[:12]>.json (kept, never deleted; the
tools/native_support_contact_evidence.py _retire pattern), so readiness never outlives a failing observation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import uuid
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_import_seated_fit_fbx as seated_import  # noqa: E402
import validate_unreal_contact_profile as profile_gate  # noqa: E402  (the existing typing contact gate)
import unreal_desk_typing_seated_capture as capture_tool  # noqa: E402  (schema, receipt/placement readers)

PROFILE_FILE = seat.SEATED_TYPING_PROFILE_FILE
PROFILE_SCHEMA = seat.SEATED_TYPING_PROFILE_SCHEMA
EVALUATION_FILE = 'desk-typing-seated-contact-evaluation.json'
EVALUATION_SCHEMA = 'sub01.desk-typing-seated-contact-evaluation.v1'
OLD_PROFILE = 'unreal-skinned-contact-audit.json'       # the renderer's old-clip profile, <project>/ (never written)
WINDOW_FRAMES = (180, 480)                              # 3..8 s at 60 Hz, the renderer's audited interval (301 rows)
SAMPLE_FIELDS = ('invalidInfluences', 'keyTopCm', 'hands', 'corrected', 'corrected_local_arms', 'arm_world_offsets_cm',
                 'finger_local_max_error_degrees', 'bone_length_max_error_cm', 'wrist_world_max_error_degrees')


class Refused(Exception):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_binding(capture: dict, receipt_raw: bytes) -> dict:
    if capture.get('schema') != capture_tool.CAPTURE_SCHEMA or capture.get('observation') != capture_tool.OBSERVATION:
        raise Refused('NotNative: not a native seated typing capture')
    analyzer = capture.get('analyzer') or {}
    if analyzer.get('skin') != capture_tool.SKIN_ANALYZER or analyzer.get('arm_solver') != capture_tool.ARM_SOLVER:
        raise Refused('NotNative: capture was not made by the renderer\'s native skin analyzer and arm solver')
    if capture.get('mesh') != seat.OWNER_MESH or capture.get('skeleton') != seat.OWNER_SKELETON:
        raise Refused('Mesh: capture is not the owner mesh on the owner skeleton')
    if (capture.get('receipt') or {}).get('sha256') != sha256_bytes(receipt_raw):
        raise Refused('ReceiptChanged: the import receipt differs from the one the capture read')
    try:
        row = capture_tool.receipt_row(json.loads(receipt_raw))
    except capture_tool.Refused as error:
        raise Refused(str(error)) from None
    clip = capture.get('clip') or {}
    for field, want in (('role', capture_tool.ROLE), ('object_path', row['object_path']), ('glb_sha256', row['glb_sha256']),
                        ('fbx_sha256', row['fbx_sha256']), ('rate_hz', row['fps']), ('frames', row['frames'])):
        if clip.get(field) != want:
            raise Refused(f'ClipBinding: capture {field}={clip.get(field)!r}, receipt row {want!r}')
    if clip['glb_sha256'] != seated_import.GLB_SHA256[capture_tool.ROLE]:
        raise Refused('ClipBinding: not the committed seated typing fit GLB')
    length = clip.get('sequence_length_s')
    if not _finite(length) or abs(length - row['glb_duration_s']) > seated_import.DURATION_TOLERANCE_S:
        raise Refused('ClipBinding: imported length differs from the receipt')
    frames = capture.get('frames')
    want = capture_tool.frame_times(row['frames'], length)
    if not isinstance(frames, list) or len(frames) != len(want):
        raise Refused(f'Coverage: {len(frames) if isinstance(frames, list) else 0} frames, the clip has {len(want)} keys')
    for i, (f, t) in enumerate(zip(frames, want)):
        if not isinstance(f, dict) or f.get('frame') != i or not _finite(f.get('time')) or abs(f['time'] - t) > 1e-6:
            raise Refused(f'Coverage: frame {i} missing or not at t = {t:.6f} s')
    return row


def check_placement(capture: dict, evidence_raw: bytes, chair_raw: bytes) -> dict:
    recorded = capture.get('placement') or {}
    if recorded.get('sha256') != sha256_bytes(evidence_raw) or recorded.get('chair_surface_sha256') != sha256_bytes(chair_raw):
        raise Refused('PlacementChanged: seat evidence or chair report differs from what the capture read')
    try:
        now = capture_tool.placement(evidence_raw.decode(), chair_raw.decode())
    except (capture_tool.Refused, ValueError) as error:
        raise Refused(str(error)) from None
    for key in ('body_cm', 'body_rotation_pyr', 'body_scale_xyz', 'chair_revision'):
        if recorded.get(key) != now[key]:
            raise Refused(f'PlacementChanged: capture {key} differs from the measured seat evidence')
    pitch, yaw, roll = now['body_rotation_pyr']
    if pitch != 0 or roll != 0 or now['body_scale_xyz'] != [1, 1, 1]:
        raise Refused('PlacementTransform: the adapter\'s profile pose is pitch/roll-free unit scale; this evidence is not')
    return now


def check_skin(frames) -> None:
    for f in frames:
        for part in (f, f.get('corrected') or {}):
            if part.get('invalidInfluences') != 0:
                raise Refused(f'Skin: invalid imported influences at frame {f["frame"]}')
            hands = part.get('hands') or []
            if len(hands) != 2 or [h.get('side') for h in hands] != ['left', 'right'] \
                    or not all(_finite(h.get('selectedVertices')) and h['selectedVertices'] > 0 for h in hands):
                raise Refused(f'Skin: both hands must be selected at frame {f["frame"]}')


def whole_clip_summary(frames) -> dict:
    """Reported, not gated: the profile replays 3..8 s only (the seat-pose-fit gates the rest where a hand is on keys)."""
    out = {}
    for side, i in (('left', 0), ('right', 1)):
        over = [f for f in frames if f['corrected']['hands'][i].get('overKeyVertices', 0) > 0]
        gaps = [f['corrected']['hands'][i]['overMinCm'] - f['corrected']['keyTopCm'] for f in over]
        out[side] = {'frames': len(frames), 'frames_over_keys': len(over),
                     'max_corrected_penetration_cm': max((f['corrected']['hands'][i]['penetrationCm'] for f in over), default=0.0),
                     'corrected_gap_cm': [min(gaps), max(gaps)] if gaps else None}
    return out


def build_profile(capture: dict, capture_sha: str, receipt_sha: str, row: dict, place: dict) -> dict:
    start, end = WINDOW_FRAMES
    window = [f for f in capture['frames'] if start <= f['frame'] <= end]
    samples = [{'time': f['time'], **{k: f[k] for k in SAMPLE_FIELDS}} for f in window]
    yaw = place['body_rotation_pyr'][1]
    return {'schema': PROFILE_SCHEMA, 'ready': True, 'family': 'DeskTyping', 'role': capture_tool.ROLE,
            'kind': 'actual imported distal-influenced skinned surface; not joint estimate',
            'clip_object_path': row['object_path'], 'glb_sha256': row['glb_sha256'], 'fbx_sha256': row['fbx_sha256'],
            'receipt_sha256': receipt_sha, 'capture_sha256': capture_sha, 'capture_id': capture.get('capture_id'),
            'mesh': capture['mesh'], 'source_interval_seconds': [3, 8], 'selected_threshold': .30,
            'key_xy_status': 'actual87keycaps toptriangle narrowphase; keycaps sha256 ' + str(capture['keyboard'].get('sha256')),
            'key_top_spread_cm': capture['keyboard']['key_top_spread_cm'],
            'body_cm': place['body_cm'], 'body_yaw': yaw, 'body_rotation_pyr': [0, yaw, 0], 'body_scale_xyz': [1, 1, 1],
            'placement_source': capture['placement']['source'], 'chair_revision': place['chair_revision'],
            'samples': samples, 'native_seat_verified': False,
            'note': 'Keyboard arm profile of the seated-fit typing clip only; the renderer\'s old-clip profile is kept.'}


def evaluate(project: Path, capture_raw: bytes) -> tuple:
    """(profile, report) when every gate passes; Refused otherwise. Writes nothing."""
    project = Path(project)
    audit = project / 'private-audit'
    try:
        capture = json.loads(capture_raw)
    except ValueError:
        raise Refused('Malformed: capture is not JSON') from None
    if not isinstance(capture, dict):
        raise Refused('Malformed: capture is not an object')
    files = {'receipt': project / seat.SEATED_FIT_RECEIPT, 'evidence': audit / capture_tool.EVIDENCE_FILE,
             'chair': audit / capture_tool.CHAIR_FILE}
    for name, path in files.items():
        if not path.is_file():
            raise Refused(f'Missing: {path} does not exist')
    receipt_raw = files['receipt'].read_bytes()
    try:
        row = check_binding(capture, receipt_raw)
        place = check_placement(capture, files['evidence'].read_bytes(), files['chair'].read_bytes())
        frames = capture['frames']
        check_skin(frames)
        spread = (capture.get('keyboard') or {}).get('key_top_spread_cm')
        if not _finite(spread) or not 0 <= spread <= capture_tool.KEY_TOP_SPREAD_MAX_CM:
            raise Refused('Keyboard: key top spread missing or over 2 mm')
        profile = build_profile(capture, sha256_bytes(capture_raw), sha256_bytes(receipt_raw), row, place)
        try:
            accepted = profile_gate.validate(profile)                        # the existing typing contact gate
        except (ValueError, KeyError, TypeError) as error:
            raise Refused(f'TypingContact: {error}') from None
        binding = seat.seated_typing_profile_binding(profile, json.loads(receipt_raw), row['object_path'])
        if not binding['bound']:                                              # the adapter's own reader
            raise Refused(f'AdapterReader: {binding["refusal"]}')
    except (KeyError, TypeError, IndexError, AttributeError) as error:
        raise Refused(f'Malformed: {type(error).__name__} {error}') from None
    profile['acceptance'] = accepted
    return profile, {'gate': accepted, 'whole_clip': whole_clip_summary(frames), 'frames': len(frames)}


def _old_profile(project: Path):
    path = Path(project) / OLD_PROFILE
    return sha256_bytes(path.read_bytes()) if path.is_file() else None


def _retire(audit: Path, sha: str) -> list:
    """Move an earlier seated profile aside (kept, never deleted) when a newer observation fails."""
    path = audit / PROFILE_FILE
    if not path.is_file():
        return []
    moved = path.with_name(f'{path.stem}.superseded-{sha[:12]}{path.suffix}')
    path.replace(moved)
    return [str(moved)]


def _atomic(path: Path, text: str) -> None:
    temp = path.with_name(path.name + f'.{uuid.uuid4().hex[:12]}.tmp')
    temp.write_text(text)
    temp.replace(path)


def write(project: Path, capture_path: Path | None = None) -> dict:
    project = Path(project)
    audit = project / 'private-audit'
    audit.mkdir(parents=True, exist_ok=True)
    capture_path = Path(capture_path or audit / capture_tool.CAPTURE_FILE)
    old_before = _old_profile(project)
    record = {'schema': EVALUATION_SCHEMA, 'capture': str(capture_path), 'profile': str(audit / PROFILE_FILE),
              'old_clip_profile': {'file': OLD_PROFILE, 'sha256_before': old_before}}
    if not capture_path.is_file():
        result = {'ready': False, 'error': f'NoObservation: {capture_path} does not exist', 'retired': []}
    else:
        raw = capture_path.read_bytes()
        sha = sha256_bytes(raw)
        record['capture_sha256'] = sha
        try:
            profile, report = evaluate(project, raw)
        except Refused as error:
            result = {'ready': False, 'error': str(error), 'retired': _retire(audit, sha)}
        else:
            text = json.dumps(profile, indent=2) + '\n'
            _atomic(audit / PROFILE_FILE, text)
            result = {'ready': True, 'error': '', 'retired': [], 'profile_sha256': sha256_bytes(text.encode()), **report}
    record['old_clip_profile']['sha256_after'] = _old_profile(project)
    if record['old_clip_profile']['sha256_after'] != old_before:          # never ours to change; say so loudly
        result.update(ready=False, error=(result.get('error') or '') + '; old-clip profile changed during evaluation',
                      retired=result.get('retired', []) + _retire(audit, record.get('capture_sha256', 'unobserved')))
    record.update(result, accepted=result['ready'])
    _atomic(audit / EVALUATION_FILE, json.dumps(record, indent=2) + '\n')
    return record


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--check', action='store_true', help='run every gate and print the verdict; write nothing')
    p.add_argument('project', type=Path)
    p.add_argument('capture', type=Path, nargs='?')
    a = p.parse_args(argv)
    if a.check:
        path = a.capture or a.project / 'private-audit' / capture_tool.CAPTURE_FILE
        try:
            _, report = evaluate(a.project, path.read_bytes())
            result = {'ready': True, **report}
        except (Refused, OSError) as error:
            result = {'ready': False, 'error': str(error)}
    else:
        result = write(a.project, a.capture)
    print(json.dumps(result, indent=2))
    return 0 if result['ready'] else 3


if __name__ == '__main__':
    sys.exit(main())
