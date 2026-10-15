"""Seated typing seat contact audit: root's unedited audit run on the seated clip (fake engine) -> seat evidence."""
import json
import shutil
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_import_seated_fit_fbx as seated_import  # noqa: E402
import unreal_audit_seated_typing_seat_contact as wrapper  # noqa: E402

SEATED = seat.seated_fit_object_path('DeskTypingSeated')
FRAMES = 989
DURATION = (FRAMES - 1) / 60
CHAIR = json.dumps({'errors': [], 'chair': {
    'component': '/Game/Sub01Home/ActualHome.Chair:Cushion',
    'component_world_bounds_cm': {'min': [173.444, -214.673, 40.098], 'max': [226.292, -161.033, 73.682]},
    'sections': [{'vertices_world_cm': [[180, -210, 50.5], [220, -210, 50.5], [220, -170, 50.5], [180, -170, 50.5]],
                  'triangles': [0, 1, 2, 0, 2, 3],
                  'cushion_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]],
                                      'world_bounds_cm': {'min': [180, -210, 50.5], 'max': [220, -170, 50.5]}}}]}})
IN_BAND = {'buttocks': (-1.2, -.6), 'left_posterior_thigh': (-.9, -.2), 'right_posterior_thigh': (-.8, -.1),
           'left_sole': (.1, .3), 'right_sole': (.1, .4)}


def receipt_row(**override):
    row = {'role': 'DeskTypingSeated', 'object_path': SEATED, 'fit_pass': True, 'fps': 60,
           'glb_sha256': seated_import.GLB_SHA256['DeskTypingSeated'], 'fbx_sha256': 'f' * 64, 'glb_duration_s': DURATION,
           'frames': FRAMES, 'imported': True, 'accepted': True, 'same_existing_skeleton': True}
    row.update(override)
    return row


def make_project(tmp, row=None):
    project = Path(tmp) / 'Sub01HomeLab'
    audit = project / 'private-audit'
    audit.mkdir(parents=True)
    (audit / 'unreal-seated-fit-import.json').write_text(json.dumps(
        {'schema': seat.SEATED_FIT_RECEIPT_SCHEMA, 'skeleton': seat.OWNER_SKELETON, 'clips': [row or receipt_row()]}))
    (audit / 'native-chair-surface.json').write_text(CHAIR)
    return project


class Vec:
    def __init__(self, x=0., y=0., z=0.):
        self.x, self.y, self.z = x, y, z


class Xf:
    def __init__(self, location=None, rotation=None):
        self.location, self.rotation = location, rotation


def fake_unreal(project, regions=IN_BAND, skeleton_path=seat.OWNER_SKELETON, length=DURATION, seen=None):
    seen = {} if seen is None else seen
    skeleton = types.SimpleNamespace(get_path_name=lambda: skeleton_path)

    class AnimSequence:
        def __init__(self, path):
            self.path = path

        def get_editor_property(self, k):
            return {'skeleton': skeleton, 'sequence_length': length}[k]

        def get_path_name(self):
            return self.path
    owner_skeleton = skeleton if skeleton_path == seat.OWNER_SKELETON else types.SimpleNamespace(get_path_name=lambda: seat.OWNER_SKELETON)
    mesh = types.SimpleNamespace(get_editor_property=lambda k: owner_skeleton, get_path_name=lambda: seat.OWNER_MESH)
    assets = {seat.OWNER_MESH: mesh, SEATED: AnimSequence(SEATED), seat.TYPING_CLIP: AnimSequence(seat.TYPING_CLIP)}
    names = ['Hips', 'LeftUpLeg', 'RightUpLeg']

    class Component:
        def set_skeletal_mesh_asset(self, m):
            pass

        def get_num_bones(self):
            return len(names)

        def get_bone_name(self, i):
            return names[i]

        def get_parent_bone(self, n):
            return 'None' if n == 'Hips' else 'Hips'

    def poses(clip, ns, t, extract, m):
        seen.setdefault('clips', set()).add(clip.get_path_name())
        seen.setdefault('times', []).append(t)
        return [Xf() for _ in ns]

    def analyze(m, pose, body, triangles, floor):
        seen['body'], seen['floor'], seen['triangles'] = body, floor, len(triangles)
        return json.dumps({'invalidInfluences': 0, 'floorCm': floor, 'regions': [
            {'region': n, 'selectedVertices': 900, 'facingVertices': 300, 'overSurfaceVertices': 200, 'bandVertices': 150,
             'minGapCm': lo, 'p10GapCm': lo + .1, 'p50GapCm': med, 'p90GapCm': med + .4, 'maxGapCm': med + 1}
            for n, (lo, med) in regions.items()]})
    u = types.SimpleNamespace()
    u.AnimSequence = AnimSequence
    u.load_asset = lambda p: assets.get(p)
    u.SkeletalMeshComponent = Component
    u.AnimationLibrary = types.SimpleNamespace(get_bone_poses_for_time=poses)
    u.MathLibrary = types.SimpleNamespace(compose_transforms=lambda a, b: Xf())
    u.Sub01HomeHandsInstance = types.SimpleNamespace(finish_pending_skin_compilation=lambda: None, analyze_captured_seat_skin=analyze)
    u.Transform, u.Vector = Xf, Vec
    u.Rotator = lambda roll=0, pitch=0, yaw=0: (pitch, yaw, roll)
    u.Paths = types.SimpleNamespace(project_dir=lambda: str(project))
    u.log = u.log_warning = lambda *_: None
    return u, seen


@pytest.fixture(autouse=True)
def engine_module(monkeypatch):
    # root's audit does `import unreal as u` at import time; the wrapper replaces `u` in-process anyway.
    monkeypatch.setitem(sys.modules, 'unreal', types.SimpleNamespace())


def run(project, **kw):
    # The committed fit summary, solved on the actual (unshifted) chair.
    u, seen = fake_unreal(project, **kw)
    return wrapper.main(u, project, repo=seated_import.REPO), seen


def test_root_audit_is_reused_unedited_and_restored(tmp_path):
    original = (ROOT / 'tools/unreal_audit_seat_contact.py').read_text()
    assert f"u.load_asset('{seat.TYPING_CLIP}')" in original      # the literal the wrapper redirects
    import unreal_audit_seat_contact as audit
    before = (audit.BODY_CM, audit.BODY_YAW, audit.u)
    run(make_project(tmp_path))
    assert (audit.BODY_CM, audit.BODY_YAW, audit.u) == before
    assert (ROOT / 'tools/unreal_audit_seat_contact.py').read_text() == original


def test_seated_clip_audited_at_the_fitted_placement_becomes_seated_evidence(tmp_path):
    project = make_project(tmp_path)
    out, seen = run(project)
    report = json.loads(out.read_text())
    # only the seated clip was evaluated, every 60 Hz frame of 3..8 s, at the fitted body placement and measured floor
    import unreal_audit_seat_contact as audit
    assert seen['clips'] == {SEATED} and len(seen['times']) == 301 and seen['times'][0] == 3 and seen['times'][-1] == 8
    summary = json.loads((ROOT / seated_import.SUMMARY_REPORT).read_text())
    assert report['body_cm'] == summary['source_meta']['body_cm'] and report['body_yaw'] == summary['source_meta']['body_yaw']
    assert seen['body'].location.__dict__ == dict(zip('xyz', summary['source_meta']['body_cm']))
    assert seen['floor'] == audit.FLOOR_CM and report['floor_evidence'] == audit.FLOOR_EVIDENCE and seen['triangles'] == 6
    assert report['clip'] == {'role': 'DeskTypingSeated', 'object_path': SEATED, 'glb_sha256': seated_import.GLB_SHA256['DeskTypingSeated'],
                              'fbx_sha256': 'f' * 64, 'rate_hz': 60, 'frames': FRAMES, 'sequence_length_s': DURATION}
    receipt_raw = (project / seat.SEATED_FIT_RECEIPT).read_bytes()
    assert report['receipt']['sha256'] == wrapper.sha256_bytes(receipt_raw)
    assert report['chair_surface_sha256'] == wrapper.sha256_bytes(CHAIR.encode()) and report['chair_revision'] == str(seat.seat_id(CHAIR))
    assert report['chair_alignment']['offset_cm']['min'][1] == pytest.approx(-214.673 - summary['capsule']['chair_aabb_after_shift_cm']['min'][1])
    assert report['probe_in_band'] is True and report['native_seat_verified'] is False
    correction = json.loads((project / 'private-audit/native-seat-correction.json').read_text())
    assert correction['clip'] == report['clip'] and correction['recommended_delta_cm'] == 0
    assert not list((project / 'private-audit').glob('.seated-typing-seat-contact-*'))
    evidence = json.loads(seat.write_evidence(project).read_text())
    assert evidence['clip'] == SEATED and evidence['clip_id'] == str(seat.seat_id(SEATED))
    assert evidence['body_cm'] == report['body_cm'] and evidence['body_rotation_pyr'] == [0, 180, 0]


def test_out_of_band_seated_contact_retires_earlier_seated_evidence(tmp_path):
    project = make_project(tmp_path)
    run(project)
    seat.write_evidence(project)
    old_evidence = (project / 'private-audit/native-seat-evidence.json').read_bytes()
    first = (project / 'private-audit/native-seat-contact.json').read_bytes()
    out, _ = run(project, regions={**IN_BAND, 'left_posterior_thigh': (1.5, 2.2)})
    report = json.loads(out.read_text())
    assert report['probe_in_band'] is False and 'posterior_thigh' in report['probe_refusal']
    assert not (project / 'private-audit/native-seat-evidence.json').exists()
    kept = {p.read_bytes() for p in (project / 'private-audit').glob('*.superseded-*.json')}
    assert old_evidence in kept and first in kept                 # kept aside, never deleted
    with pytest.raises(ValueError, match='posterior_thigh'):
        seat.write_evidence(project)


def test_old_clip_evidence_is_not_retired_by_a_failing_seated_audit(tmp_path):
    project = make_project(tmp_path)
    old = json.dumps({'clip': seat.TYPING_CLIP})
    (project / 'private-audit/native-seat-evidence.json').write_text(old)
    run(project, regions={**IN_BAND, 'buttocks': (3.0, 4.0)})
    assert (project / 'private-audit/native-seat-evidence.json').read_text() == old


def _summary_repo(tmp_path, mutate):
    repo = tmp_path / 'repo'
    target = repo / seated_import.SUMMARY_REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / seated_import.SUMMARY_REPORT).read_text())
    mutate(data)
    target.write_text(json.dumps(data))
    return repo


@pytest.mark.parametrize('row,kw,mutate,match', [
    (receipt_row(accepted=False), {}, None, 'accepted'),
    (receipt_row(fit_pass=False), {}, None, 'fit_pass'),
    (receipt_row(fps=30), {}, None, 'fps'),
    (receipt_row(glb_sha256='0' * 64), {}, None, 'glb_sha256'),
    (receipt_row(fbx_sha256=None), {}, None, 'FBX'),
    (receipt_row(frames=301, glb_duration_s=5.0), {'length': 5.0}, None, 'does not span'),
    (None, {'length': DURATION - 1}, None, 'ClipLength'),
    (None, {'skeleton_path': '/Game/Other.Other'}, None, 'ClipSkeleton'),
    (None, {}, lambda d: d['clips']['DeskTyping_seated'].update(sha256='0' * 64), 'PlacementStale'),
    (None, {}, lambda d: d['source_meta'].update(times={'start_s': 0, 'end_s': 5, 'rate_hz': 60, 'count': 301}), 'Window'),
    (None, {}, lambda d: d['source_meta'].pop('body_cm'), 'PlacementMissing'),
    (None, {}, lambda d: d.update(chair_horizontal_shift_cm=[0.0, -0.5]), 'ShiftedChairFit'),
])
def test_refuses_inconsistent_inputs_and_writes_nothing(tmp_path, row, kw, mutate, match):
    project = make_project(tmp_path, row)
    u, _ = fake_unreal(project, **kw)
    repo = _summary_repo(tmp_path, lambda d: mutate and mutate(d))
    with pytest.raises(wrapper.Refused, match=match):
        wrapper.main(u, project, repo=repo)
    assert sorted(p.name for p in (project / 'private-audit').iterdir()) == ['native-chair-surface.json', 'unreal-seated-fit-import.json']


def test_committed_fit_summary_is_solved_on_the_unmoved_chair():
    raw = (ROOT / seated_import.SUMMARY_REPORT).read_bytes()
    summary = json.loads(raw)
    assert summary['chair_horizontal_shift_cm'] == [0.0, 0.0]
    place = wrapper.fit_placement(raw, receipt_row())
    assert place['chair_horizontal_shift_cm'] == [0.0, 0.0]
    assert place['body_cm'] == summary['source_meta']['body_cm'] == [200.025, -199.8, -0.6]
    # The committed DeskTyping_seated verdict itself fails on the actual chair, so the importer never writes the
    # accepted row this wrapper requires (receipt_row() above is a synthetic accepted row).
    assert summary['clips'][wrapper.FIT_KEY]['all_gates_pass'] is False


def test_refuses_without_receipt_or_chair(tmp_path):
    project = make_project(tmp_path)
    (project / seat.SEATED_FIT_RECEIPT).unlink()
    with pytest.raises(wrapper.Refused, match='ReceiptMissing'):
        run(project)
    project = make_project(tmp_path / 'b')
    (project / 'private-audit/native-chair-surface.json').unlink()
    with pytest.raises(wrapper.Refused, match='ChairUnmeasured'):
        run(project)
