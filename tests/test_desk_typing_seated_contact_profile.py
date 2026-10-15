"""Seated typing keyboard profile: native capture (fake engine), offline gates, retirement, and the adapter's reader."""
import copy
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import unreal_seat_transition_runtime as seat  # noqa: E402
import unreal_import_seated_fit_fbx as seated_import  # noqa: E402
import validate_unreal_contact_profile as profile_gate  # noqa: E402
import unreal_desk_typing_seated_capture as cap  # noqa: E402
import desk_typing_seated_contact_profile as ev  # noqa: E402
from unreal_typing_review_policy import CPP as TYPING_REVIEW_CPP  # noqa: E402

FRAMES = 989                      # the committed DeskTyping_seated GLB key count
DURATION = (FRAMES - 1) / 60
KEY_TOP = 87.38975858
CHAIR = json.dumps({'errors': [], 'chair': {'component': '/Game/Sub01Home/ActualHome.Chair:Cushion', 'sections': [{
    'vertices_world_cm': [[180, -210, 50.5], [220, -210, 50.5], [220, -170, 50.5], [180, -170, 50.5]],
    'triangles': [0, 1, 2, 0, 2, 3],
    'cushion_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]],
                        'world_bounds_cm': {'min': [180, -210, 50.5], 'max': [220, -170, 50.5]}}}]}})


def seat_report():
    regions = {'buttocks': (-1.2, -.6), 'left_posterior_thigh': (-.9, -.2), 'right_posterior_thigh': (-.8, -.1),
               'left_sole': (.1, .3), 'right_sole': (.1, .4)}
    row = {'invalidInfluences': 0, 'floorCm': 0.0, 'regions': [
        {'region': n, 'selectedVertices': 900, 'facingVertices': 300, 'overSurfaceVertices': 200, 'bandVertices': 150,
         'minGapCm': lo, 'p10GapCm': lo + .1, 'p50GapCm': med, 'p90GapCm': med + .4, 'maxGapCm': med + 1}
        for n, (lo, med) in regions.items()]}
    return {'schema': 'sub01.native-seat-contact.v1', 'body_cm': [203.9, -232.3, -.6], 'body_yaw': 180, 'floor_cm': 0.0,
            'samples': [dict(copy.deepcopy(row), time=3 + i / 60) for i in range(301)]}


def receipt_row(**override):
    row = {'role': 'DeskTypingSeated', 'object_path': seat.seated_fit_object_path('DeskTypingSeated'), 'fit_pass': True,
           'fps': 60, 'glb': 'docs/proposed/seat-pose-fit/SUB01_DeskTyping_seated.glb',
           'glb_sha256': seated_import.GLB_SHA256['DeskTypingSeated'], 'report_sha256': 'c' * 64, 'fbx_sha256': 'f' * 64,
           'glb_duration_s': DURATION, 'frames': FRAMES, 'imported': True, 'accepted': True, 'preserved_existing': False,
           'duration_s': DURATION, 'sample_rate_hz': 60, 'same_existing_skeleton': True}
    row.update(override)
    return row


def hypothetical_passing_verdicts():
    """The committed verdicts with DeskTypingSeated passing for the SAME committed GLB: what a future passing seat fit
    would commit. The profile's own gates are exercised under it; the real committed verdict refuses (tested below)."""
    verdicts = copy.deepcopy(seat.committed_seated_fit_verdicts())
    verdicts['DeskTypingSeated']['all_gates_pass'] = True
    return verdicts


@pytest.fixture
def passing_typing_fit(monkeypatch):
    verdicts = hypothetical_passing_verdicts()
    monkeypatch.setattr(seat, 'committed_seated_fit_verdicts', lambda repo=None: copy.deepcopy(verdicts))
    return verdicts


def make_project(tmp, row=None, evidence=None):
    project = Path(tmp) / 'srv' / 'project' / 'Sub01HomeLab'
    audit = project / 'private-audit'
    audit.mkdir(parents=True)
    (audit / 'unreal-seated-fit-import.json').write_text(json.dumps(
        {'schema': seat.SEATED_FIT_RECEIPT_SCHEMA, 'skeleton': seat.OWNER_SKELETON, 'clips': [row or receipt_row()]}))
    (audit / 'native-chair-surface.json').write_text(CHAIR)
    (audit / 'native-seat-evidence.json').write_text(json.dumps(evidence or seat.build_evidence(seat_report(), CHAIR)))
    (project / 'SourceAssets').mkdir()
    (project / 'SourceAssets/full-home.glb').write_bytes(b'actual house source')
    tri = [[200.0, -290.0, KEY_TOP], [201.0, -290.0, KEY_TOP], [201.0, -289.0, KEY_TOP]]
    (project.parent.parent / 'keyboard-keycaps-world.json').write_text(json.dumps({
        'sourceSHA256': hashlib.sha256(b'actual house source').hexdigest(),
        'geometryBoundsUECm': {'minCm': [182.5, -304, 85.0], 'maxCm': [217.5, -284, KEY_TOP]},
        'keycaps': [{'topTrianglesUECm': [tri]} for _ in range(87)]}))
    (project / ev.OLD_PROFILE).write_text('{"samples": "the renderer\'s old-clip profile"}\n')
    return project


# ------------------------------------------------------------------ fake engine
class Vec:
    def __init__(self, x=0., y=0., z=0.):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __sub__(self, o):
        return Vec(self.x - o.x, self.y - o.y, self.z - o.z)

    def __add__(self, o):
        return Vec(self.x + o.x, self.y + o.y, self.z + o.z)

    def length(self):
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)


class Quat:
    x = y = z = 0.
    w = 1.


class Xf:
    def __init__(self, location=None, rotation=None, scale=None):
        self.translation, self.rotation, self.scale3d = location or Vec(), Quat(), scale or Vec(1, 1, 1)
        self.rotator = rotation


BONES = {'Hips': 'None', 'LeftArm': 'Hips', 'LeftForeArm': 'LeftArm', 'LeftHand': 'LeftForeArm', 'LeftHandIndex3': 'LeftHand',
         'RightArm': 'Hips', 'RightForeArm': 'RightArm', 'RightHand': 'RightForeArm', 'RightHandIndex3': 'RightHand'}


def fake_unreal(project, gap_at=lambda t: .08, path_name=None, length=DURATION, observed=None):
    u = types.SimpleNamespace()
    skeleton = types.SimpleNamespace(get_path_name=lambda: seat.OWNER_SKELETON)

    class AnimSequence:
        def get_editor_property(self, k):
            return {'skeleton': skeleton, 'sequence_length': length}[k]

        def get_path_name(self):
            return path_name or seat.seated_fit_object_path('DeskTypingSeated')
    mesh = types.SimpleNamespace(get_editor_property=lambda k: skeleton, get_path_name=lambda: seat.OWNER_MESH)
    clip = AnimSequence()
    names = list(BONES)

    class Component:
        def set_skeletal_mesh_asset(self, m):
            pass

        def get_num_bones(self):
            return len(names)

        def get_bone_name(self, i):
            return names[i]

        def get_parent_bone(self, n):
            return BONES[str(n)]
    times = observed if observed is not None else []

    def poses(c, ns, t, extract, m):
        times.append(t)
        return [Xf(Vec(0, 0, 10)) for _ in ns]

    def analyze(m, pose, body, kmin, kmax, tris):
        t = times[-1]
        hand = lambda side: {'side': side, 'selectedVertices': 900, 'overKeyVertices': 200, 'minCm': KEY_TOP - 1,
                             'maxCm': KEY_TOP + 3, 'overMinCm': KEY_TOP + gap_at(t), 'overMaxCm': KEY_TOP + 2,
                             'penetrationCm': max(0., -gap_at(t))}
        return json.dumps({'invalidInfluences': 0, 'keyTopCm': kmax.z, 'hands': [hand('left'), hand('right')]})
    u.AnimSequence = AnimSequence
    u.load_asset = lambda p: {seat.OWNER_MESH: mesh, seat.seated_fit_object_path('DeskTypingSeated'): clip}.get(p)
    u.SkeletalMeshComponent = Component
    u.AnimationLibrary = types.SimpleNamespace(get_bone_poses_for_time=poses)
    u.MathLibrary = types.SimpleNamespace(compose_transforms=lambda a, b: Xf(a.translation + b.translation),
                                          invert_transform=lambda a: Xf(Vec() - a.translation))
    u.Sub01HomeHandsInstance = types.SimpleNamespace(finish_pending_skin_compilation=lambda: None,
                                                     analyze_captured_finger_skin=analyze,
                                                     solve_captured_keyboard_arm_contact=lambda m, p, *a: list(p))
    u.Transform, u.Vector, u.Rotator = Xf, Vec, (lambda roll=0, pitch=0, yaw=0: (pitch, yaw, roll))
    u.Paths = types.SimpleNamespace(project_dir=lambda: str(project))
    u.SystemLibrary = types.SimpleNamespace(get_engine_version=lambda: '5.x fake')
    u.log = lambda *_: None
    return u


def capture(project, **kw):
    return cap.main(fake_unreal(project, **kw), project)


# ------------------------------------------------------------------ constants: reused, never invented
def test_native_rules_are_the_existing_tolerances():
    header = seat.HEADER_FILE.read_text()
    rules = header.split('struct FSub01TypingProfileRules {', 1)[1].split('};', 1)[0]
    assert 'Samples=301;' in rules and 'StartSeconds=3,RateHz=60' in rules
    assert f'KeyGapMaxCm={str(profile_gate.KEY_GAP_MAX_CM).lstrip("0")}' in rules
    # validate_unreal_contact_profile: penetration .1, finger .1 deg, bone .01 cm; DistalGap (no review): gap >= -.1,
    # spread <= .2, gap + spread <= .2.
    source = (ROOT / 'tools/validate_unreal_contact_profile.py').read_text()
    assert "h['penetrationCm']>.1" in source and "<=.1:raise ValueError('Captured finger" in source and "<=.01:raise ValueError('Bone" in source
    assert 'PenetrationMaxCm=.1' in rules and 'FingerLocalMaxDeg=.1' in rules and 'BoneLengthMaxCm=.01' in rules
    assert 'CapSpread<=.2&&Gap>=-.1&&Gap+CapSpread<=(ExplicitPoseReview?.5:.2)' in TYPING_REVIEW_CPP and 'CapSpreadMaxCm=.2' in rules
    assert cap.KEY_TOP_SPREAD_MAX_CM == .2 and ev.WINDOW_FRAMES == (180, 480)


# ------------------------------------------------------------------ capture (fake engine)
def test_capture_covers_the_whole_imported_clip_at_the_measured_placement(tmp_path):
    project = make_project(tmp_path)
    observed = []
    out = cap.main(fake_unreal(project, observed=observed), project)
    data = json.loads(out.read_text())
    assert out == project / 'private-audit' / cap.CAPTURE_FILE
    assert len(data['frames']) == FRAMES and [f['frame'] for f in data['frames']] == list(range(FRAMES))
    assert observed[:3] == [0, 1 / 60, 2 / 60] and observed[-1] == pytest.approx(DURATION)
    assert data['clip']['object_path'] == seat.seated_fit_object_path('DeskTypingSeated') and data['clip']['rate_hz'] == 60
    assert data['clip']['glb_sha256'] == seated_import.GLB_SHA256['DeskTypingSeated'] and data['clip']['fbx_sha256'] == 'f' * 64
    evidence = json.loads((project / 'private-audit/native-seat-evidence.json').read_text())
    assert data['placement']['body_cm'] == evidence['body_cm'] and data['placement']['body_rotation_pyr'] == evidence['body_rotation_pyr']
    assert data['placement']['sha256'] == hashlib.sha256((project / 'private-audit/native-seat-evidence.json').read_bytes()).hexdigest()
    assert set(data['frames'][0]['corrected_local_arms']) == profile_gate.ARMS
    assert data['claims'] == {'contact_verified': False, 'typing_ready': False, 'note': data['claims']['note']}


@pytest.mark.parametrize('breaks, match', [
    (lambda p: (p / 'private-audit/unreal-seated-fit-import.json').unlink(), 'ReceiptMissing'),
    (lambda p: (p / 'private-audit/native-seat-evidence.json').unlink(), 'PlacementMissing'),
    (lambda p: (p / 'private-audit/native-chair-surface.json').write_text(CHAIR.replace('50.5', '51.5')), 'PlacementStale'),
    (lambda p: (p / 'SourceAssets/full-home.glb').write_bytes(b'other house'), 'KeyboardStale'),
    (lambda p: (p / 'private-audit/unreal-seated-fit-import.json').write_text(json.dumps(
        {'schema': seat.SEATED_FIT_RECEIPT_SCHEMA, 'skeleton': seat.OWNER_SKELETON, 'clips': [receipt_row(accepted=False)]})), 'ReceiptRow'),
    (lambda p: (p / 'private-audit/unreal-seated-fit-import.json').write_text(json.dumps(
        {'schema': seat.SEATED_FIT_RECEIPT_SCHEMA, 'skeleton': seat.OWNER_SKELETON, 'clips': [receipt_row(glb_sha256='0' * 64)]})), 'ReceiptRow'),
])
def test_capture_refuses_without_measured_inputs_and_writes_nothing(tmp_path, breaks, match):
    project = make_project(tmp_path)
    breaks(project)
    with pytest.raises(cap.Refused, match=match):
        capture(project)
    assert not (project / 'private-audit' / cap.CAPTURE_FILE).exists()


def test_capture_refuses_a_clip_of_another_length(tmp_path):
    project = make_project(tmp_path)
    with pytest.raises(cap.Refused, match='ClipLength'):
        capture(project, length=DURATION - .2)


# ------------------------------------------------------------------ the adapter's own reader, native and Python
def compiler():
    found = shutil.which('clang++') or shutil.which('g++')
    if not found:
        pytest.skip('C++ compiler unavailable')
    return found


def native_accepts(profile):
    """Run the header's Sub01TypingProfileSample over every profile sample; returns the accepted count."""
    rows = []
    for i, r in enumerate(profile['samples']):
        h = r['corrected']['hands']
        nums = [r['time'], profile['key_top_spread_cm'], r['bone_length_max_error_cm'], r['finger_local_max_error_degrees'],
                r['corrected']['invalidInfluences'], r['corrected']['keyTopCm']]
        rows.append('{%d,{%s},{%s,%s},{%s,%s},{%s,%s}}' % (
            i, ','.join(f'{v!r}' for v in nums), repr(h[0]['overMinCm']), repr(h[1]['overMinCm']),
            repr(h[0]['penetrationCm']), repr(h[1]['penetrationCm']), float(h[0]['overKeyVertices']), float(h[1]['overKeyVertices'])))
    source = ('#include <cstdio>\n#include "Sub01SeatTransition.h"\nstruct R{int I;double V[6];double L[2],P[2],O[2];};\n'
              'static const R Rows[]={' + ','.join(rows) + '};\nint main(){int N=0;for(const R& r:Rows)'
              'N+=Sub01TypingProfileSample(r.I,r.V[0],r.V[1],r.V[2],r.V[3],r.V[4],r.V[5],r.L,r.P,r.O);std::printf("%d",N);return 0;}')
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'a.cpp', Path(tmp) / 'a'
        cpp.write_text(source)
        built = subprocess.run([compiler(), '-std=c++17', '-Wall', '-Werror', f'-I{seat.HEADER_FILE.parent}', str(cpp), '-o', str(exe)],
                               capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        return int(subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout)


def test_passing_native_capture_writes_a_profile_every_gate_reader_accepts(tmp_path, passing_typing_fit):
    project = make_project(tmp_path)
    old = (project / ev.OLD_PROFILE).read_bytes()
    capture(project)
    record = ev.write(project)
    assert record['ready'] is True and record['accepted'] is True and record['error'] == ''
    profile_path = project / 'private-audit' / seat.SEATED_TYPING_PROFILE_FILE
    profile = json.loads(profile_path.read_text())
    # bound to the import receipt row and the measured placement
    assert profile['clip_object_path'] == seat.seated_fit_object_path('DeskTypingSeated')
    assert profile['glb_sha256'] == seated_import.GLB_SHA256['DeskTypingSeated'] and profile['fbx_sha256'] == 'f' * 64
    assert profile['body_cm'] == [203.9, -232.3, -.6] and profile['body_yaw'] == 180
    assert [s['time'] for s in profile['samples']] == [f / 60 for f in range(180, 481)]
    # the existing typing gate, the adapter's Python reader and the native header all accept it
    assert profile_gate.validate(profile)['samples'] == 301
    receipt = json.loads((project / 'private-audit/unreal-seated-fit-import.json').read_text())
    assert seat.seated_typing_profile_binding(profile, receipt, profile['clip_object_path'])['bound'] is True
    assert native_accepts(profile) == 301
    # the old-clip profile is kept byte for byte
    assert (project / ev.OLD_PROFILE).read_bytes() == old
    assert record['old_clip_profile']['sha256_before'] == record['old_clip_profile']['sha256_after'] == hashlib.sha256(old).hexdigest()
    assert record['whole_clip']['left']['frames'] == FRAMES


def test_no_observation_writes_no_profile(tmp_path):
    project = make_project(tmp_path)
    record = ev.write(project)
    assert record['ready'] is False and record['error'].startswith('NoObservation')
    assert not (project / 'private-audit' / seat.SEATED_TYPING_PROFILE_FILE).exists()
    assert json.loads((project / 'private-audit' / ev.EVALUATION_FILE).read_text())['ready'] is False


def write_capture(project, mutate):
    path = project / 'private-audit' / cap.CAPTURE_FILE
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data))


@pytest.mark.parametrize('mutate, match', [
    (lambda d: d.update(observation='synthetic'), 'NotNative'),
    (lambda d: d['analyzer'].update(skin='python estimate'), 'NotNative'),
    (lambda d: d['clip'].update(glb_sha256='0' * 64), 'ClipBinding'),
    (lambda d: d['clip'].update(fbx_sha256='e' * 64), 'ClipBinding'),
    (lambda d: d['clip'].update(object_path='/Game/Sub01Hands/FBX/SUB01_DeskTyping.SUB01_DeskTyping'), 'ClipBinding'),
    (lambda d: d['clip'].update(rate_hz=30), 'ClipBinding'),
    (lambda d: d['frames'].pop(), 'Coverage'),
    (lambda d: d['frames'][500].update(time=d['frames'][500]['time'] + .01), 'Coverage'),
    (lambda d: d['receipt'].update(sha256='0' * 64), 'ReceiptChanged'),
    (lambda d: d['placement'].update(body_cm=[203.9, -232.3, 5]), 'PlacementChanged'),
    (lambda d: d['frames'][3]['corrected'].update(invalidInfluences=2), 'Skin'),
    (lambda d: d['frames'][250]['corrected']['hands'][1].update(overMinCm=KEY_TOP + .3), 'TypingContact'),
    (lambda d: d['frames'][250]['corrected']['hands'][0].update(penetrationCm=.2, overMinCm=KEY_TOP - .2), 'TypingContact'),
    (lambda d: d['frames'][300].update(finger_local_max_error_degrees=.5), 'TypingContact'),
    (lambda d: d['keyboard'].update(key_top_spread_cm=.15), 'AdapterReader'),   # gap .08 + spread .15 > .2 (DistalGap)
])
def test_failing_or_unbound_observations_never_write_a_profile(tmp_path, mutate, match):
    project = make_project(tmp_path)
    capture(project)
    write_capture(project, mutate)
    record = ev.write(project)
    assert record['ready'] is False and match in record['error'], record['error']
    assert not (project / 'private-audit' / seat.SEATED_TYPING_PROFILE_FILE).exists()


def test_evidence_with_pitch_is_refused_not_approximated(tmp_path):
    evidence = seat.build_evidence(dict(seat_report(), body_rotation_pyr=[2.0, 180, 0]), CHAIR)
    project = make_project(tmp_path, evidence=evidence)
    capture(project)
    record = ev.write(project)
    assert record['ready'] is False and 'PlacementTransform' in record['error']


def test_a_newer_failing_capture_retires_the_seated_profile_and_keeps_the_old_one(tmp_path, passing_typing_fit):
    project = make_project(tmp_path)
    old = (project / ev.OLD_PROFILE).read_bytes()
    capture(project)
    assert ev.write(project)['ready'] is True
    accepted = (project / 'private-audit' / seat.SEATED_TYPING_PROFILE_FILE).read_bytes()
    capture(project, gap_at=lambda t: .5 if abs(t - 5) < 1e-9 else .08)        # a later native observation hovers
    record = ev.write(project)
    assert record['ready'] is False and 'TypingContact' in record['error']
    assert not (project / 'private-audit' / seat.SEATED_TYPING_PROFILE_FILE).exists()
    [moved] = record['retired']
    assert Path(moved).read_bytes() == accepted and f'.superseded-{record["capture_sha256"][:12]}.json' in moved
    assert (project / ev.OLD_PROFILE).read_bytes() == old


def test_committed_failing_typing_fit_refuses_even_a_passing_capture(tmp_path):
    # The committed DeskTypingSeated verdict is false (typing is infeasible on the actual chair): the adapter's reader,
    # and so the writer, refuse a profile that passes every contact gate, even with a receipt row claiming the fit.
    assert seat.committed_seated_fit_verdicts()['DeskTypingSeated']['all_gates_pass'] is False
    project = make_project(tmp_path)
    capture(project)
    record = ev.write(project)
    assert record['ready'] is False and 'AdapterReader' in record['error'] and seat.SEATED_TYPING_UNCOMMITTED in record['error']
    assert not (project / 'private-audit' / seat.SEATED_TYPING_PROFILE_FILE).exists()


@pytest.mark.parametrize('row, verdict', [
    (dict(fit_pass=False), True), (dict(accepted=False), True), (dict(glb_sha256='b' * 64), True),
    (dict(glb_sha256=None), True), ({}, False),
])
def test_forged_receipt_rows_never_bind_the_seated_typing_profile(tmp_path, monkeypatch, row, verdict):
    verdicts = hypothetical_passing_verdicts()
    monkeypatch.setattr(seat, 'committed_seated_fit_verdicts', lambda repo=None: copy.deepcopy(verdicts))
    project = make_project(tmp_path)
    capture(project)
    assert ev.write(project)['ready'] is True
    profile = json.loads((project / 'private-audit' / seat.SEATED_TYPING_PROFILE_FILE).read_text())
    path = profile['clip_object_path']
    genuine = {'clips': [receipt_row()]}
    assert seat.seated_typing_profile_binding(profile, genuine, path, verdicts)['bound'] is True
    verdicts['DeskTypingSeated']['all_gates_pass'] = verdict
    out = seat.seated_typing_profile_binding(profile, {'clips': [receipt_row(**row)]}, path, verdicts)
    assert out['bound'] is False
    # a genuine row under a failing committed verdict (today's) refuses as well
    failing = copy.deepcopy(verdicts)
    failing['DeskTypingSeated']['all_gates_pass'] = False
    assert seat.seated_typing_profile_binding(profile, genuine, path, failing)['refusal'] == seat.SEATED_TYPING_UNCOMMITTED


def test_python_reader_refuses_profiles_for_another_clip_or_import():
    good = {'schema': seat.SEATED_TYPING_PROFILE_SCHEMA, 'ready': True}
    receipt = {'clips': [receipt_row()]}
    path = seat.seated_fit_object_path('DeskTypingSeated')
    assert 'does not hold' in seat.seated_typing_profile_binding(good, receipt, seat.TYPING_CLIP)['refusal']
    assert 'receipt row' in seat.seated_typing_profile_binding(good, {'clips': [receipt_row(accepted=False)]}, path)['refusal']
    assert 'another clip' in seat.seated_typing_profile_binding(dict(good, clip_object_path=path, glb_sha256='x', fbx_sha256='f' * 64),
                                                               receipt, path)['refusal']
    assert 'readiness' in seat.seated_typing_profile_binding(dict(good, ready=False), receipt, path)['refusal']


def test_native_sample_gate_boundaries():
    cases = [  # (index, time, spread, bone, finger, invalid, top, low, pen, over) -> expected
        (0, 3.0, 0, 0, 0, 0, 10, (10.08, 10.2), (0, 0), (5, 5), 1),
        (0, 3.0, 0, 0, 0, 0, 10, (10.08, 10.21), (0, 0), (5, 5), 0),     # gap over 0.2 cm
        (0, 3.0, .1, 0, 0, 0, 10, (10.08, 10.1), (0, 0), (5, 5), 1),
        (0, 3.0, .1, 0, 0, 0, 10, (10.08, 10.12), (0, 0), (5, 5), 0),    # gap + spread over 0.2 cm
        (0, 3.0, 0, 0, 0, 0, 10, (9.9, 10.0), (.1, 0), (5, 5), 1),
        (0, 3.0, 0, 0, 0, 0, 10, (9.89, 10.0), (.11, 0), (5, 5), 0),     # penetration over 0.1 cm
        (0, 3.0, 0, .011, 0, 0, 10, (10, 10), (0, 0), (5, 5), 0),        # stretch
        (0, 3.0, 0, 0, .11, 0, 10, (10, 10), (0, 0), (5, 5), 0),         # finger change
        (0, 3.0, 0, 0, 0, 1, 10, (10, 10), (0, 0), (5, 5), 0),           # invalid influences
        (0, 3.0, 0, 0, 0, 0, 10, (10, 10), (0, 0), (0, 5), 0),           # no true key overlap
        (1, 3.0, 0, 0, 0, 0, 10, (10, 10), (0, 0), (5, 5), 0),           # wrong time
        (300, 8.0, 0, 0, 0, 0, 10, (10, 10), (0, 0), (5, 5), 1),
        (301, 3 + 301 / 60, 0, 0, 0, 0, 10, (10, 10), (0, 0), (5, 5), 0),
        (0, 3.0, .21, 0, 0, 0, 10, (10, 10), (0, 0), (5, 5), 0),         # spread over 2 mm
        (0, 3.0, 0, 0, 0, 0, float('nan'), (10, 10), (0, 0), (5, 5), 0),
    ]
    body = ''
    for i, t, s, b, f, inv, top, low, pen, over, want in cases:
        body += ('{const double L[2]={%r,%r},P[2]={%r,%r},O[2]={%r,%r};std::printf("%%d",(int)Sub01TypingProfileSample(%d,%r,%r,%r,%r,%r,%s,L,P,O));}'
                 % (float(low[0]), float(low[1]), float(pen[0]), float(pen[1]), float(over[0]), float(over[1]), i, float(t), float(s),
                    float(b), float(f), float(inv), 'NAN' if math.isnan(top) else repr(float(top))))
    source = '#include <cstdio>\n#include "Sub01SeatTransition.h"\nint main(){' + body + 'return 0;}'
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'a.cpp', Path(tmp) / 'a'
        cpp.write_text(source)
        built = subprocess.run([compiler(), '-std=c++17', '-Wall', '-Werror', f'-I{seat.HEADER_FILE.parent}', str(cpp), '-o', str(exe)],
                               capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-3000:]
        out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
    assert out == ''.join(str(c[-1]) for c in cases)
    # the Python twin agrees on every case
    for i, t, s, b, f, inv, top, low, pen, over, want in cases:
        row = {'time': t, 'bone_length_max_error_cm': b, 'finger_local_max_error_degrees': f,
               'corrected': {'invalidInfluences': inv, 'keyTopCm': top, 'hands': [
                   {'side': side, 'overMinCm': low[k], 'penetrationCm': pen[k], 'overKeyVertices': over[k]}
                   for k, side in enumerate(('left', 'right'))]}}
        assert seat.typing_profile_sample(i, row, s) is bool(want), (i, t, s, low)


# ------------------------------------------------------------------ the installed native binding
def installed_methods():
    sources = {'header': '#include "Sub01HomeLab.generated.h"\n void Forward(float Value);\n',
               'cpp': ' BeginLiveHome();\n UpdateNativeFeedback();\n if(!LiveHomePath.Num()){if(PCBridge)PCBridge->SetOperatorFocus(\n '
                      + seat.SEAT_RATE_ANCHOR,
               'hands_header': ' protected:\n', 'hands_cpp': ' float Progress=1;\n  Current.SetPlayRate(Hands->TargetRate);\n  Blend.Evaluate_AnyThread(Output);\n'}
    return seat.install(sources)['cpp']


def test_native_binding_accepts_only_the_seated_profile_for_the_bound_clip():
    cpp = installed_methods()
    assert '@@' not in cpp
    load = cpp.split('void ASub01HomeCharacter::LoadSeatTransition(){', 1)[1].split('\n}\n', 1)[0]
    block = load.split(' // Seated typing profile (tools/desk_typing_seated_contact_profile.py).', 1)[1].split(' UE_LOG(LogTemp,Display,TEXT("SUB01_SEAT_TRANSITION_READY', 1)[0]
    assert load.index('SeatProfilePoseLoaded=Sub01SeatTransformFinite(SeatProfilePose);') < load.index(' // Seated typing profile')
    assert 'SeatedTyping->GetPathName()==TEXT("/Game/Sub01Hands/Seating/SUB01_DeskTypingSeated.SUB01_DeskTypingSeated")' in block
    assert 'TEXT("desk-typing-seated-contact-profile.json")' in block and 'TEXT("sub01.desk-typing-seated-contact-profile.v1")' in block
    assert 'TEXT("private-audit/unreal-seated-fit-import.json")' in block and 'Role==TEXT("DeskTypingSeated")' in block
    for gate in ('TypingClipPath!=SeatedTyping->GetPathName()', 'TypingProfileGlb!=TypingGlb', 'TypingProfileFbx!=TypingFbx',
                 'TypingSamples->Num()!=FSub01TypingProfileRules::Samples', 'Sub01TypingProfileSample(I,Time,TypingSpread,Bone,Finger,Invalid,Top,Low,Pen,Over)',
                 'TypingHands->ContactTimes.Num()&&TypingHands->ContactSequence!=SeatedTyping', 'TypingNames.Num()!=6'):
        assert gate in block
    # the old-clip profile pose never applies to the seated clip; binding is all-or-nothing
    assert block.index('SeatProfilePoseLoaded=false;') < block.index('TypingHands->ContactSequence=SeatedTyping;')
    assert block.count('TypingHands->ContactSequence=SeatedTyping;') == 1
    assert 'SUB01_SEATED_TYPING_PROFILE_REFUSED' in block and 'NativeSeatVerified' not in block
    # the typing gate itself is unchanged
    assert ('In.TypingProfileReady=Instance&&TypingClip&&Instance->ContactSequence==TypingClip&&Instance->ContactTimes.Num()==301'
            '&&Instance->ContactLocalTransforms.Num()==301*6\n  &&SeatProfilePoseLoaded&&HasBody&&Sub01SeatSameTransform(SeatProfilePose,Live);') in cpp
    # locals never shadow the function's own (UE treats shadowing as an error)
    function_scope = {'Mesh', 'Roles', 'Audit', 'ChairText', 'Chair', 'EvidenceText', 'E', 'ProfilePath', 'ProfileText', 'Profile',
                      'SeatedFitVerdicts', 'SeatedFitVerdictCount'}
    declared = set(re.findall(r'(?:FString|TSharedPtr<FJsonObject>|double|bool|auto\*|TArray<[^>]+>)\s+\*?(\w+)', block))
    assert not (declared & function_scope), declared & function_scope
