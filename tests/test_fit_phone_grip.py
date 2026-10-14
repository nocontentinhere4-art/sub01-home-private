import json
import math
from pathlib import Path

import numpy as np
import pytest

from tools import fit_phone_grip as fit
from tools import phone_grip_transition as tr
from tools import unreal_phone_grip_diagnostic as diag

ROOT = Path(__file__).resolve().parents[1]


def test_phone_parts_are_the_original_assembly_mirrored():
    phone = fit.default_phone()
    names = [p['name'] for p in phone['parts']]
    assert names == ['case', 'speaker', 'volume', 'power', 'screen']
    assert [tuple(e) for _, _, e in fit.UE_PARTS] == [tuple(e) for _, e in diag.PARTS]
    assert [tuple(c) for _, c, _ in fit.UE_PARTS] == [tuple(c) for c, _ in diag.PARTS]
    case, screen = phone['parts'][0], phone['parts'][4]
    assert np.allclose(np.array(case['half_extent'])*2, [7.5, 15, 1.5])
    assert np.allclose(np.array(screen['half_extent'][:2])*2, [6.7, 13.7])
    assert screen['center'][2] == pytest.approx(.8)
    # Speaker is at the top (+y in the mirrored frame); power +x, volume -x, as viewed from the screen.
    assert phone['parts'][1]['center'][1] > 6 and phone['parts'][3]['center'][0] > 0 > phone['parts'][2]['center'][0]


def test_eye_constant_matches_native_diagnostic():
    assert 'FVector(.11885198390986161,-13.382490930007885,12.634526097714183)' in diag.METHODS
    assert fit.UE_EYE_HEAD_LOCAL == (.11885198390986161, -13.382490930007885, 12.634526097714183)


def test_unreal_rotator_and_mirror_round_trip():
    rng = np.random.default_rng(3)
    for _ in range(50):
        p, y, r = rng.uniform(-89, 89), rng.uniform(-179, 179), rng.uniform(-179, 179)
        assert np.allclose(fit.ue_rotator_from_quat(fit.ue_quat_from_rotator(p, y, r)), (p, y, r), atol=1e-7)
        R, t = fit.rotvec_to_matrix(rng.normal(size=3)), rng.normal(size=3)*5
        off, q, rot = fit.gltf_to_ue_local(t, R)
        t2, R2 = fit.ue_to_gltf_local(off, *rot)
        assert np.allclose(t, t2) and np.allclose(R, R2, atol=1e-9)
        assert np.linalg.det(fit.quat_to_matrix(q)) == pytest.approx(1)


def test_known_unreal_rotator_convention():
    # FRotator(0,90,0): yaw +90 maps +X to +Y in Unreal.
    R = fit.quat_to_matrix(fit.ue_quat_from_rotator(0, 90, 0))
    assert np.allclose(R@[1, 0, 0], [0, 1, 0], atol=1e-12)


def test_box_sdf_and_triangle_overlap():
    h = np.array([3.75, 7.5, .75])
    assert fit.box_sdf(np.array([[0, 0, 1.0]]), [0, 0, 0], h)[0] == pytest.approx(.25)
    assert fit.box_sdf(np.array([[0, 0, .5]]), [0, 0, 0], h)[0] == pytest.approx(-.25)
    a, b, c = (np.array([[x]]) for x in ([-1, -1, 2.0], [1, -1, -2.0], [0, 1, 0.0]))
    a, b, c = a[0], b[0], c[0]
    assert fit.tri_box_overlap(a, b, c, h).all()
    assert not fit.tri_box_overlap(a+[0, 0, 5], b+[0, 0, 5], c+[0, 0, 5], h).any()
    # Large triangle whose vertices are all outside but whose face cuts the box: vertex tests miss it.
    a, b, c = np.array([[-20, -20, 0.1]]), np.array([[20, -20, 0.1]]), np.array([[0, 30, 0.1]])
    assert fit.tri_box_overlap(a, b, c, h).all()
    # Zero-thickness screen rectangle is crossed by a triangle that pierces it.
    scr = np.array([3.35, 6.85, 0])
    assert fit.tri_box_overlap(np.array([[0, 0, -1.0]]), np.array([[.5, 0, 1.0]]), np.array([[0, .5, 1.0]]), scr).all()
    assert not fit.tri_box_overlap(np.array([[0, 0, .2]]), np.array([[.5, 0, 1.0]]), np.array([[0, .5, 1.0]]), scr).any()


def test_rays_blocked_only_by_intervening_triangles():
    tri = [np.array([[-1, -1, 5.0]]), np.array([[1, -1, 5.0]]), np.array([[0, 1, 5.0]])]
    blocked = fit.ray_hits(np.array([[0, 0, 0.0], [5, 5, 0.0]]), np.array([0, 0, 10.0]), *tri)
    assert blocked.tolist() == [True, False]


def test_support_hull_and_pinch():
    half = np.array([3.75, 7.5, .75])
    under = np.array([[x, y, -.75] for x in (-3, 3) for y in (-6, 6)])
    assert fit.Evaluator.support(under, np.zeros(3), half, np.array([0, 0, -1.0]))['supported']
    one_side = np.array([[x, y, -.75] for x in (2, 3) for y in (5, 6)])
    assert not fit.Evaluator.support(one_side, np.zeros(3), half, np.array([0, 0, -1.0]))['supported']
    pinch = np.array([[3.75, 0, 0], [-3.75, 0, 0]])
    assert fit.Evaluator.support(pinch, np.zeros(3), half, np.array([0, 0, -1.0]))['opposing_side_pinch']


def test_transition_is_continuous_and_never_moves_phone_at_attach_or_release():
    n = 60
    times = np.arange(n)/30
    rest = (np.eye(3), np.array([270.0, -292, 85.8]))
    wrists = []
    for i in range(n):
        lift = max(0.0, (i-10)/30)*12 if i < 45 else max(0.0, (55-i)/10)*12
        ang = math.radians(min(max(i-10, 0), 20)*2)
        R = fit.rotvec_to_matrix([ang, 0, 0])
        wrists.append((R, rest[1]+[0, 0, 4+lift]))
    mount = (fit.rotvec_to_matrix([0.6, 0, 0]), np.array([0.0, 3, 5]))
    poses, report = tr.plan(wrists, times, rest, mount, grasp_index=10, lift_seconds=.6,
                            release_index=55, lower_seconds=.3, desk_top=85.05)
    assert report['verified'] is False
    assert np.allclose(poses[10][1], rest[1]) and np.allclose(poses[55][1], rest[1])
    assert report['phases'][0] == 'world' and 'use' in report['phases'] and report['phases'][-1] == 'world'
    assert report['max_step_cm'] < 3


def test_real_capture_export_if_present():
    cache = sorted((ROOT/'out/phone-grip').glob('hand-7609eccbe816-8a6dfc041cd4-r*.json'))
    if not cache:
        pytest.skip('Real owner/Texting skin export not generated here (out/phone-grip is private cache)')
    hand = fit.HandExport(cache[0].with_suffix(''))
    assert hand.meta['owner']['vertices'] == 249148 and hand.meta['modified'] == {'bones': False, 'fingers': False, 'clip': False}
    ev = fit.Evaluator(hand, fit.default_phone(), fit.MIRROR@np.array(fit.UE_EYE_HEAD_LOCAL), 4.0)
    assert 25 < np.linalg.norm(ev.eyes[ev.pose]) < 60


def test_committed_fit_report_is_never_acceptance():
    for path in (ROOT/'docs/proposed/phone-grip').glob('*.fit.json'):
        doc = json.loads(path.read_text())
        assert doc['verified'] is False and doc['requires_native_reaudit'] is True and doc['visual_accepted'] is False
        assert doc['owner']['sha256'] == '7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb'
        assert doc['clip']['sha256'] == '8a6dfc041cd4768016c6348dfb90f1275cab4c09cfe6083537fb88ba6d11ae75'


class _FakeHand:
    """Geometry-unit fixture only (never runtime evidence): one body vertex sheet near a phone."""
    def __init__(self, body_z):
        xs, ys = np.meshgrid(np.linspace(-5, 5, 11), np.linspace(-9, 9, 19))
        body = np.stack([xs.ravel(), ys.ravel(), np.full(xs.size, body_z)], 1)
        self.positions = body[None].astype(np.float32)
        self.labels = np.zeros(len(body), np.uint8)
        self.triangles = np.zeros((0, 3), np.int64)
        self.times = np.array([4.0])
        self.joints = ['mixamorigSpine', 'mixamorigRightHand']
        ident = [0, 0, 0, 1]
        self.meta = {'wrists': [{'position': [0, 0, 0], 'quaternion': ident}],
                     'heads': [{'position': [0, 0, 40], 'quaternion': ident}],
                     'arms': [[[0, 30, 0], [0, 30, 0], [0, 15, 0]]]}

    def frame_index(self, time):
        return 0

    def eye_in_wrist(self, f, local):
        return np.array([0, 0, 40.0])

    def gravity_in_wrist(self, f):
        return np.array([0, -1.0, 0])


def test_ik_delta_clears_body_with_smallest_bounded_move_and_upright_metric():
    ev = fit.Evaluator(_FakeHand(body_z=-0.6), fit.default_phone(), [0, 0, 0], 4.0)
    R, t = np.eye(3), np.zeros(3)
    delta, ok = ev.ik_delta(0, R, t, np.zeros(3))
    assert ok and 0 < np.linalg.norm(delta) <= 1.5 and delta[2] > 0
    assert ev.sdf(ev.local(0, R, t+delta)).min() >= ev.clear
    clear = fit.Evaluator(_FakeHand(body_z=-5.0), fit.default_phone(), [0, 0, 0], 4.0)
    assert np.allclose(clear.ik_delta(0, R, t, np.zeros(3))[0], 0)
    # Head up is +y: an unrotated phone reads upright, a 180 degree roll reads upside down.
    assert ev.upright(0, R) == pytest.approx(1)
    assert ev.upright(0, fit.rotvec_to_matrix([0, 0, math.pi])) == pytest.approx(-1)


def test_wrist_correction_counter_rotates_only_non_hand_geometry():
    hand = _FakeHand(body_z=-5.0)
    hand.labels = np.array([1]*10+[0]*(len(hand.labels)-10), np.uint8)   # first ten: right-hand rigid
    ev = fit.Evaluator(hand, fit.default_phone(), [0, 0, 0], 4.0)
    C = fit.rotvec_to_matrix([0, 0, 0.4])
    ev.set_correction(C)
    P = ev.points(0)
    assert np.allclose(P[:10], hand.positions[0][:10])
    assert np.allclose(P[10:], hand.positions[0][10:]@C)
    assert np.allclose(ev.eyes[0], C.T@ev.eyes0[0])
    rec = fit.correction_record(C)
    assert rec['angle_deg'] == pytest.approx(math.degrees(0.4))
    # UE value is the handedness mirror of the glTF correction.
    assert np.allclose(fit.quat_to_matrix(rec['ue_right_hand_local_post_multiply_xyzw']), fit.MIRROR@C@fit.MIRROR, atol=1e-7)
