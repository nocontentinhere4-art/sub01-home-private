"""SERVER UE editor audit (root only): seat contact of the IMPORTED seated-fit DeskTyping clip, by the existing audit.

    UnrealEditor-Cmd <project>/Sub01HomeLab.uproject \
        -ExecutePythonScript="<repo>/tools/unreal_audit_seated_typing_seat_contact.py" -unattended
    python3 tools/unreal_seat_transition_runtime.py <project>        # -> private-audit/native-seat-evidence.json

When the seat adapter binds /Game/Sub01Hands/Seating/SUB01_DeskTypingSeated into the DeskTyping slot, the live receipt
(Sub01SeatReceipt) compares the evidence clip id to THAT clip, so the evidence must be measured on it. This wrapper runs
tools/unreal_audit_seat_contact.py run() itself, unchanged (the renderer's AnalyzeCapturedSeatSkin per 60 Hz frame of
3..8 s, the audited cushion triangles, the measured native floor and its evidence), changing in-process ONLY:
  * the clip loader: its literal load of /Game/Sub01Hands/FBX/SUB01_DeskTyping returns the seated clip instead (any
    other asset loads as before; exactly one redirected load is required, else refused);
  * BODY_CM / BODY_YAW: the placement the seated clip was fitted at, read from the committed fit summary
    (docs/proposed/seat-pose-fit/seat-pose-fit.report.json source_meta), bound to this clip by its GLB sha256;
  * the project dir: a private staging copy holding only the measured chair report, so the audit's own output never
    lands in private-audit/ without the clip identity.
Nothing is defaulted. Inputs (any missing or inconsistent one refuses before anything is written):
  * <project>/private-audit/unreal-seated-fit-import.json: exactly one DeskTypingSeated row, imported, accepted,
    fit_pass, same_existing_skeleton, at the seated path, 60 fps, the committed fit GLB sha256 and an FBX sha256
    (tools/unreal_desk_typing_seated_capture.receipt_row). The clip loaded from that path must be on the owner skeleton
    with the receipt's length, and span the audited 3..8 s window.
  * the fit summary: its DeskTyping_seated clip sha256 equals the receipt's GLB sha256 and its audited times are
    3..8 s at 60 Hz, 301 samples (the window validate_unreal_seat_contact and desk_typing_seated_contact_profile use).
  * <project>/private-audit/native-chair-surface.json (tools/unreal_chair_surface_audit.py), as for the original audit.
Writes <project>/private-audit/native-seat-contact.json and native-seat-correction.json (the original audit's files;
a different earlier file is kept as <name>.superseded-<sha256[:12]>.json, never deleted), each naming the audited
clip (role, object path, GLB/FBX sha256, 60 Hz) and the receipt, placement and chair sha256s. When the contact is out
of band, an earlier native-seat-evidence.json for the seated clip is moved aside the same way, so acceptance never
outlives a failing observation. A fit solved with the chair shifted (nonzero chair_horizontal_shift_cm) is refused
before any audit: the native chair transform is protected and a hypothetical chair is never evidence. The report also
records the measured chair bounds against the fit's expected bounds (diagnostic only; validate() is the gate).
Probe only: no mesh, actor, pose, asset or collision changes, and nothing sets NativeSeatVerified.
NOT RUN in this repository (no engine here); tests/test_unreal_audit_seated_typing_seat_contact.py runs it on a fake.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import math
import shutil
import sys
import types
import uuid
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_import_seated_fit_fbx as seated_import  # noqa: E402  (no unreal at import)
import unreal_desk_typing_seated_capture as capture_tool  # noqa: E402  (receipt row reader; no unreal at import)
import validate_unreal_seat_contact as seat_contact  # noqa: E402

ROLE = seat.SEATED_TYPING_ROLE
RATE_HZ = seat.SEATED_TYPING_RATE_HZ
FIT_KEY = seated_import.ROLES[ROLE][1]                    # 'DeskTyping_seated' in the fit summary's clips
FIT_SUMMARY = seated_import.SUMMARY_REPORT                # docs/proposed/seat-pose-fit/seat-pose-fit.report.json
WINDOW = {'start_s': 3, 'end_s': 8, 'rate_hz': 60, 'count': 301}   # validate_unreal_seat_contact.regions_by_sample
AUDIT_MODULE = 'unreal_audit_seat_contact'
CONTACT_FILE, CORRECTION_FILE, EVIDENCE_FILE = 'native-seat-contact.json', 'native-seat-correction.json', 'native-seat-evidence.json'
CHAIR_FILE = 'native-chair-surface.json'


class Refused(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def fit_placement(summary_raw: bytes, row: dict) -> dict:
    """The body transform the seated clip was fitted at, bound to the receipt's GLB by sha256."""
    try:
        summary = json.loads(summary_raw)
        clip = summary['clips'][FIT_KEY]
        meta = summary['source_meta']
    except (ValueError, KeyError, TypeError):
        raise Refused(f'PlacementMissing: {FIT_SUMMARY} has no {FIT_KEY} clip or source_meta') from None
    if clip.get('sha256') != row['glb_sha256']:
        raise Refused(f'PlacementStale: {FIT_SUMMARY} {FIT_KEY} sha256 is not the imported GLB {row["glb_sha256"]}')
    if meta.get('times') != WINDOW:
        raise Refused(f'Window: the fit was audited at {meta.get("times")!r}, not {WINDOW}')
    body, yaw = meta.get('body_cm'), meta.get('body_yaw')
    if not (isinstance(body, list) and len(body) == 3 and all(_finite(v) for v in body) and _finite(yaw)):
        raise Refused(f'PlacementMissing: {FIT_SUMMARY} source_meta has no finite body_cm/body_yaw')
    shift = summary.get('chair_horizontal_shift_cm')
    if shift is not None and (not isinstance(shift, list) or any(v != 0 for v in shift)):
        raise Refused(f'ShiftedChairFit: {FIT_SUMMARY} was solved with the chair moved by {shift!r} cm; the native chair '
                      'transform is protected, so this placement is not evidence for the actual chair. Refit on the '
                      'measured chair, or have root approve a physical chair reposition first.')
    expected = (summary.get('capsule') or {}).get('chair_aabb_after_shift_cm')
    return {'body_cm': list(body), 'body_yaw': yaw, 'chair_horizontal_shift_cm': summary.get('chair_horizontal_shift_cm'),
            'expected_chair_bounds_cm': expected}


def chair_alignment(chair: dict, expected) -> dict:
    """Diagnostic: measured chair component bounds minus the bounds the fit was solved against."""
    measured = (chair.get('chair') or {}).get('component_world_bounds_cm')
    if not (isinstance(measured, dict) and isinstance(expected, dict)):
        return {'measured_bounds_cm': measured, 'expected_bounds_cm': expected, 'offset_cm': None}
    try:
        offset = {k: [round(measured[k][i] - expected[k][i], 4) for i in range(3)] for k in ('min', 'max')}
    except (KeyError, IndexError, TypeError):
        offset = None
    return {'measured_bounds_cm': measured, 'expected_bounds_cm': expected, 'offset_cm': offset,
            'note': 'diagnostic only; a nonzero horizontal offset means the native chair is not where the clip was fitted'}


class _Engine:
    """The real `unreal` module with only the project dir and the original DeskTyping clip load redirected."""

    def __init__(self, real, staging: Path, clip_path: str):
        self._real, self._clip_path, self.redirected = real, clip_path, 0
        self.Paths = types.SimpleNamespace(project_dir=lambda: str(staging))

    def __getattr__(self, name):
        return getattr(self._real, name)

    def load_asset(self, path):
        if path == seat.TYPING_CLIP:
            self.redirected += 1
            return self._real.load_asset(self._clip_path)
        return self._real.load_asset(path)


def _publish(path: Path, data: dict, token: str) -> None:
    """Atomic write; a different earlier file is kept as <name>.superseded-<sha12>.json."""
    text = json.dumps(data, indent=2, default=str) + '\n'
    if path.is_file():
        old = path.read_bytes()
        if old != text.encode():
            shutil.copy2(path, path.with_name(f'{path.stem}.superseded-{sha256_bytes(old)[:12]}{path.suffix}'))
    temp = path.with_name(f'{path.name}.{token}.tmp')
    temp.write_text(text)
    temp.replace(path)


def _retire_seated_evidence(audit: Path) -> Path | None:
    path = audit / EVIDENCE_FILE
    try:
        evidence = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if evidence.get('clip') != seat.seated_fit_object_path(ROLE):
        return None
    aside = path.with_name(f'{path.stem}.superseded-{sha256_bytes(path.read_bytes())[:12]}{path.suffix}')
    path.replace(aside)
    return aside


def main(u, root: Path | None = None, repo: Path = seated_import.REPO) -> Path:
    root = Path(root or u.Paths.project_dir()).resolve()
    audit_dir = root / 'private-audit'
    receipt_path, chair_path, summary_path = root / seat.SEATED_FIT_RECEIPT, audit_dir / CHAIR_FILE, Path(repo) / FIT_SUMMARY
    for path, why in ((receipt_path, 'ReceiptMissing'), (chair_path, 'ChairUnmeasured'), (summary_path, 'PlacementMissing')):
        if not path.is_file():
            raise Refused(f'{why}: {path} does not exist')
    receipt_raw, chair_raw, summary_raw = receipt_path.read_bytes(), chair_path.read_bytes(), summary_path.read_bytes()
    try:
        row = capture_tool.receipt_row(json.loads(receipt_raw))
    except capture_tool.Refused as error:
        raise Refused(str(error)) from None
    place = fit_placement(summary_raw, row)
    chair = json.loads(chair_raw)
    seat_contact.cushion_triangles(chair)                  # the audited cushion, no errors (ValueError otherwise)

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
    if duration < WINDOW['end_s']:
        raise Refused(f'ClipLength: {duration:.4f} s does not span the audited {WINDOW["start_s"]}..{WINDOW["end_s"]} s')

    original = importlib.import_module(AUDIT_MODULE)     # root's audit, unedited (imports the real `unreal`)
    token = uuid.uuid4().hex
    staging = audit_dir / f'.seated-typing-seat-contact-{token}'
    (staging / 'private-audit').mkdir(parents=True)
    saved = {k: getattr(original, k) for k in ('u', 'BODY_CM', 'BODY_YAW')}
    engine = _Engine(u, staging, row['object_path'])
    try:
        shutil.copy2(chair_path, staging / 'private-audit' / CHAIR_FILE)
        original.u, original.BODY_CM, original.BODY_YAW = engine, tuple(place['body_cm']), place['body_yaw']
        original.run()
        if engine.redirected != 1:
            raise Refused(f'AuditChanged: {AUDIT_MODULE}.run() loaded the DeskTyping clip {engine.redirected} times, expected 1')
        result = json.loads((staging / 'private-audit' / CONTACT_FILE).read_text())
        proposal = json.loads((staging / 'private-audit' / CORRECTION_FILE).read_text())
    finally:
        for k, v in saved.items():
            setattr(original, k, v)
        shutil.rmtree(staging, ignore_errors=True)
    if result.get('body_cm') != place['body_cm'] or result.get('body_yaw') != place['body_yaw']:
        raise Refused('AuditChanged: the audit did not pose the body at the fitted placement')

    identity = {
        'clip': {'role': ROLE, 'object_path': clip.get_path_name(), 'glb_sha256': row['glb_sha256'],
                 'fbx_sha256': row['fbx_sha256'], 'rate_hz': RATE_HZ, 'frames': row['frames'], 'sequence_length_s': duration},
        'mesh': seat.OWNER_MESH,
        'audit': {'method': f'tools/{AUDIT_MODULE}.py run() (clip loader, BODY_CM/BODY_YAW and project dir redirected in-process)',
                  'sha256': sha256_bytes(Path(original.__file__).read_bytes()), 'window': WINDOW},
        'receipt': {'file': seat.SEATED_FIT_RECEIPT, 'sha256': sha256_bytes(receipt_raw), 'row': row},
        'placement': {'source': FIT_SUMMARY, 'sha256': sha256_bytes(summary_raw), 'body_cm': place['body_cm'],
                      'body_yaw': place['body_yaw'], 'chair_horizontal_shift_cm': place['chair_horizontal_shift_cm']},
        'chair_surface_sha256': sha256_bytes(chair_raw), 'chair_revision': str(seat.seat_id(chair_raw.decode())),
        'chair_alignment': chair_alignment(chair, place['expected_chair_bounds_cm']),
    }
    report = {**result, 'body_rotation_pyr': [0, place['body_yaw'], 0], 'body_scale_xyz': [1, 1, 1], **identity,
              'native_seat_verified': False}
    try:
        summary = seat_contact.validate(report)
        in_band, why = True, None
    except ValueError as error:
        summary, in_band, why = None, False, str(error)
    report['probe_in_band'], report['probe_refusal'] = in_band, why
    _publish(audit_dir / CONTACT_FILE, report, token)
    _publish(audit_dir / CORRECTION_FILE, {**proposal, 'clip': identity['clip'], 'native_seat_verified': False}, token)
    if in_band:
        u.log('SUB01_SEATED_TYPING_SEAT_CONTACT_IN_BAND ' + json.dumps(summary, default=str))
    else:
        aside = _retire_seated_evidence(audit_dir)
        u.log_warning(f'SUB01_SEATED_TYPING_SEAT_CONTACT_OUT_OF_BAND {why}; retired evidence: {aside}')
    return audit_dir / CONTACT_FILE


if __name__ == '__main__':  # pragma: no cover - server only (Unreal Editor Python)
    import unreal
    main(unreal)
