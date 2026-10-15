"""Seated typing whole-arm IK (tools/solve_seated_typing_arm_ik.py): IK math on synthetic chains, the wrist soft zone,
real-desk slab clearance, the reversible chair roll, and the committed geometry / proposal.

Synthetic tests always run. The LINEA source re-derivation runs when the source GLB is reachable (SUB01_LINEA140_GLB or
`git show origin/main:web/house/assets/real-linea140/originalsource.glb`); the committed-proposal test runs when
docs/proposed/seated-typing-ik/ holds the proposal.
"""
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import solve_seated_typing_arm_ik as K  # noqa: E402
import fit_seat_pose_trial as T  # noqa: E402

# ---------------------------------------------------------------- a synthetic left arm (glTF metres, Y up)
NAMES = ['Hips', 'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand', 'LeftHandIndex1', 'LeftHandPinky1',
         'LeftHandMiddle1', 'LeftHandMiddle2', 'LeftHandMiddle4']
PARENTS = [-1, 0, 1, 2, 3, 4, 4, 4, 7, 8]
BIND = {'Hips': (0, 1., 0), 'LeftShoulder': (.05, 1.4, 0), 'LeftArm': (.18, 1.4, 0), 'LeftForeArm': (.46, 1.4, 0),
        'LeftHand': (.70, 1.4, 0), 'LeftHandIndex1': (.79, 1.4, .03), 'LeftHandPinky1': (.78, 1.4, -.03),
        'LeftHandMiddle1': (.80, 1.4, 0), 'LeftHandMiddle2': (.84, 1.4, 0), 'LeftHandMiddle4': (.88, 1.39, 0)}


def synthetic():
    """Bind = T-pose, every bind rotation identity (joint axes = world axes); palmar side is -Y (fingertip below)."""
    J = len(NAMES)
    Wb = np.tile(np.eye(4), (J, 1, 1))
    for k, n in enumerate(NAMES):
        Wb[k, :3, 3] = BIND[n]
    ibm = np.linalg.inv(Wb)
    src = SimpleNamespace(names=NAMES, parents=np.array(PARENTS))
    return T.Skeleton(src), Wb[None].copy(), ibm


def rot(axis, deg):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    return K.P.rodrigues(axis[None], np.radians([deg]))[0]


def pose_hand(W, R_rel):
    """Rotate the hand (and carry the fingers) by R_rel about the wrist, in world."""
    W = W.copy()
    h = NAMES.index('LeftHand')
    piv = W[:, h, :3, 3].copy()
    M = np.eye(4)
    M[:3, :3] = R_rel
    M[:3, 3] = piv - R_rel @ piv[0]
    for k in range(h, len(NAMES)):
        W[:, k] = M @ W[:, k]
    return W


def test_two_bone_reaches_target_keeps_lengths_and_pole_plane():
    sk, W, ibm = synthetic()
    A = W[:, 2, :3, 3]
    target = A + np.array([[.30, -.25, .20]])
    pole = A + np.array([[.2, -.4, -.1]])
    out, reach, length, dist, _ = K.solve_arm(sk, W.copy(), 'left', target, pole, ibm, D=np.eye(3)[None], limit=False)
    assert reach.all()
    assert np.allclose(out[:, 4, :3, 3], target, atol=1e-9)
    for a, b in ((2, 3), (3, 4)):
        assert np.isclose(np.linalg.norm(out[0, b, :3, 3] - out[0, a, :3, 3]), np.linalg.norm(W[0, b, :3, 3] - W[0, a, :3, 3]))
    n = np.cross(target[0] - A[0], pole[0] - A[0])
    assert abs(np.dot(out[0, 3, :3, 3] - A[0], n / np.linalg.norm(n))) < 1e-9     # elbow in the shoulder-target-pole plane
    assert np.dot(out[0, 3, :3, 3] - A[0], pole[0] - A[0]) > 0                      # on the pole side


def test_two_bone_never_stretches():
    sk, W, ibm = synthetic()
    A = W[:, 2, :3, 3]
    target = A + np.array([[1.5, 0, 0]])
    out, reach, length, dist, _ = K.solve_arm(sk, W.copy(), 'left', target, A + [[0, -1, 0]], ibm, D=np.eye(3)[None], limit=False)
    assert not reach.any()
    assert np.isclose(np.linalg.norm(out[0, 4, :3, 3] - A[0]), .52, atol=1e-9)


def test_swivel_rotates_elbow_about_shoulder_target_axis():
    sk, W, ibm = synthetic()
    A = W[:, 2, :3, 3]
    target = A + np.array([[.25, -.30, .15]])
    pole = A + np.array([[.1, -.3, -.2]])
    base, *_ = K.solve_arm(sk, W.copy(), 'left', target, pole, ibm, D=np.eye(3)[None], limit=False)
    axis = (target - A)[0] / np.linalg.norm(target - A)
    for phi in (15., 60., 110.):
        p = K.swivel_pole(A, target, pole, np.radians([phi]))
        assert np.isclose(np.linalg.norm(p - A), np.linalg.norm(pole - A))
        out, *_ = K.solve_arm(sk, W.copy(), 'left', target, p, ibm, D=np.eye(3)[None], limit=False)
        e0, e1 = base[0, 3, :3, 3] - A[0], out[0, 3, :3, 3] - A[0]
        assert np.isclose(np.dot(e0, axis), np.dot(e1, axis))                         # same circle
        u0, u1 = e0 - np.dot(e0, axis) * axis, e1 - np.dot(e1, axis) * axis
        ang = math.degrees(math.atan2(np.dot(np.cross(u0, u1), axis), np.dot(u0, u1)))
        assert np.isclose(ang, phi, atol=1e-6)
        assert np.allclose(out[:, 4, :3, 3], target, atol=1e-9)


def test_fingers_ride_on_the_hand_with_unchanged_locals():
    sk, W, ibm = synthetic()
    W = pose_hand(W, rot((0, 0, 1), -20))
    A = W[:, 2, :3, 3]
    out, *_ = K.solve_arm(sk, W.copy(), 'left', A + [[.2, -.3, .2]], A + [[0, -.4, -.2]], ibm, hand_world=W[:, 4, :3, :3])
    L0, L1 = K.arm_locals(sk, W), K.arm_locals(sk, out)
    for n in ('LeftHandIndex1', 'LeftHandPinky1', 'LeftHandMiddle1', 'LeftHandMiddle2', 'LeftHandMiddle4'):
        assert np.allclose(L0[:, NAMES.index(n)], L1[:, NAMES.index(n)], atol=1e-9)


def test_wrist_angles_flexion_and_deviation():
    sk, W, ibm = synthetic()
    b, r, n = K.wrist_frame_bind(NAMES, ibm, 'left')
    assert np.allclose(b, (1, 0, 0)) and np.allclose(r, (0, 0, 1)) and np.allclose(n, (0, -1, 0))
    flex_axis = np.cross(b, n)            # rotating b toward the palm (n)
    for deg in (-30., 12.):
        fl, dv, tw = K.wrist_angles(pose_hand(W, rot(flex_axis, deg)), NAMES, ibm, 'left')
        assert np.isclose(fl[0], deg, atol=1e-6) and abs(dv[0]) < 1e-6 and abs(tw[0]) < 1e-6
    dev_axis = np.cross(b, r)             # rotating b toward the radial side (r)
    fl, dv, tw = K.wrist_angles(pose_hand(W, rot(dev_axis, -18)), NAMES, ibm, 'left')
    assert np.isclose(dv[0], -18, atol=1e-6) and abs(fl[0]) < 1e-6
    fl, dv, tw = K.wrist_angles(pose_hand(W, rot(b, 25)), NAMES, ibm, 'left')
    assert abs(fl[0]) < 1e-6 and abs(dv[0]) < 1e-6 and np.isclose(abs(tw[0]), 25, atol=1e-6)


def test_soft_limit_is_smooth_bounded_and_identity_inside():
    a = np.linspace(-90, 90, 721)
    out = K.soft_limit(a, -15., 15.)
    assert np.all(np.diff(out) > 0) and out.min() > -15 - 1e-9 and out.max() < 15 + 1e-9
    assert abs(K.soft_limit(0., -15., 15.)) < 1e-9 and abs(K.soft_limit(5., -15., 15.) - 5.) < .15


def test_limit_wrist_moves_only_flexion_and_deviation_into_the_zone():
    sk, W, ibm = synthetic()
    b, r, n = K.wrist_frame_bind(NAMES, ibm, 'left')
    Wp = pose_hand(pose_hand(W, rot(np.cross(b, n), -45)), rot(b, 30))     # 45 deg extension, then 30 deg pronation
    D = K.wrist_relative(Wp, NAMES, ibm, 'left')
    D2, info = K.limit_wrist(D, NAMES, ibm, 'left')
    Wl = Wp.copy()
    Wl[:, 4, :3, :3] = K.hand_world_rotation(Wp, NAMES, ibm, 'left', D2)
    fl, dv, tw = K.wrist_angles(Wl, NAMES, ibm, 'left')
    fl0, dv0, tw0 = K.wrist_angles(Wp, NAMES, ibm, 'left')
    assert np.isclose(fl0[0], -45, atol=1e-6) and np.isclose(info['flex_in'][0], -45, atol=1e-6)
    assert K.WRIST_SOFT_FLEX_DEG[0] - 1e-6 <= fl[0] <= K.WRIST_SOFT_FLEX_DEG[0] + .01      # saturated at extension 15
    assert abs(dv[0]) < .15                                                                # 0 stays ~0 (asymmetric zone)
    assert np.isclose(abs(tw[0]), abs(tw0[0]), atol=.5)                                    # twist kept


def test_envelope_never_below_need_and_smooth():
    need = np.zeros(60)
    need[30] = 1.
    env = K.envelope(need, 1 / 30)
    assert np.all(env >= need) and env[30] == 1. and env[0] < 1e-6 and np.abs(np.diff(env)).max() < .2


def test_blend_arm_locals_endpoints():
    sk, W, ibm = synthetic()
    Wb = pose_hand(W, rot((0, 0, 1), 30))
    W2 = np.concatenate([W, W])
    T2 = np.concatenate([Wb, Wb])
    out = K.blend_arm_locals(sk, W2, T2, np.array([0., 1.]), sides=('left',))
    assert np.allclose(out[0], W[0], atol=1e-12) and np.allclose(out[1], Wb[0], atol=1e-9)


# ---------------------------------------------------------------- real desk slab clearance
def test_box_signed_distance_cases():
    lo, hi = np.array([0., 0., 0.]), np.array([10., 10., 2.])
    pts = np.array([[5, 5, 3], [5, 5, 1.5], [12, 5, 1], [13, 14, 2], [5, 5, -1]], float)
    d = K.box_signed_distance(pts, lo, hi)
    assert np.allclose(d, [1., -.5, 2., 5., 1.])


def test_slab_clearance_vertical_and_footprint():
    slab = {'min_cm': [0, 0, 81.4589], 'max_cm': [100, 50, 84.5]}
    pts = np.array([[50, 25, 85.], [50, 25, 84.], [50, 25, 80.], [150, 25, 70.]])
    v, d = K.slab_clearance(pts, slab)
    assert np.allclose(v[:3], [.5, -.5, 1.4589]) and np.isinf(v[3])
    assert np.isclose(d[1], -.5)


def test_reach_culling_matches_full_distance():
    g = K.load_geometry()
    B, _ = K.desk_boxes(g)
    pts = np.random.default_rng(1).uniform([130, -340, 0], [290, -260, 95], (20000, 3))
    full, wf = K.boxes_min_distance(pts, B)
    cut, wc = K.boxes_min_distance(pts, B, reach_cm=2.)
    assert np.allclose(np.minimum(full, 2.), cut)
    assert np.all(wf[full < 2.] == wc[full < 2.])


def test_committed_real_desk_geometry_matches_root_placement():
    g = K.load_geometry()
    slab = g['tabletop_slab']
    assert g['source_sha256'] == K.LINEA_SHA256 == '99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'
    assert np.isclose(g['scale'], (.845 - .025) / .755) and g['translation_m'] == [2.1, .025, -3.02]
    assert slab['node'] == 44 and np.isclose(slab['top_cm'], 84.5, atol=1e-4)
    assert np.isclose(slab['thickness_cm'], 2.8 * K.LINEA_SCALE, atol=1e-3)                 # 28 mm walnut, scaled
    assert np.allclose(slab['centre_xy_cm'], [210., -302.], atol=1e-3)
    assert np.isclose(slab['front_edge_y_cm'], -302 + 32.5 * K.LINEA_SCALE, atol=1e-3)
    assert np.allclose(g['overall_dims_cm'], [140 * K.LINEA_SCALE, 65 * K.LINEA_SCALE, 75.83 * K.LINEA_SCALE], atol=2e-3)
    assert np.isclose(g['floor_cm'], 2.5, atol=1e-6)
    # root's record (real-linea140-guarded-placement-20261014.json knee_bay) has the same leg/drawer faces
    assert np.isclose(g['knee_bay_cm']['left_leg_inner_x'], 143.69403968978403, atol=1e-3)
    assert np.isclose(g['knee_bay_cm']['drawer_carcass_left_x'], 237.20662151395487, atol=1e-3)
    assert len(g['parts']) == 54


def linea_source():
    env = os.environ.get('SUB01_LINEA140_GLB')
    if env and Path(env).exists():
        return Path(env)
    try:
        raw = subprocess.run(['git', '-C', str(ROOT), 'show', 'origin/main:web/house/assets/real-linea140/originalsource.glb'],
                             capture_output=True, check=True, timeout=60).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    if hashlib.sha256(raw).hexdigest() != K.LINEA_SHA256:
        return None
    return raw


def test_geometry_rederives_from_the_actual_source(tmp_path):
    src = linea_source()
    if src is None:
        pytest.skip('LINEA140 source GLB not reachable')
    if isinstance(src, bytes):
        p = tmp_path / 'source.glb'
        p.write_bytes(src)
        src = p
    assert K.desk_geometry(src) == K.load_geometry()


# ---------------------------------------------------------------- the chair roll activity
def test_roll_is_reversible_quintic_and_floor_bound():
    roll = K.ChairRoll([200.02, -186.69, 60.6876], (3.875, -32.5))
    t_in, t_out = np.linspace(0, 1.2, 37), np.linspace(0, .9333, 29)
    s_in, s_out = K.ChairRoll.pull_in_s(t_in), K.ChairRoll.push_back_s(t_out)
    a, b = roll.transform(s_in), roll.transform(s_out)
    assert np.allclose(a[0], roll.start) and np.allclose(b[-1], roll.start) and np.allclose(a[-1], b[0])
    assert np.allclose(a[-1], roll.start + [3.875, -32.5, 0])
    assert np.all(a[:, 2] == roll.start[2]) and np.all(b[:, 2] == roll.start[2])
    rev = K.reversibility(roll, t_in, t_out)
    assert rev['reversible'] and rev['same_path_max_deviation_cm'] < 1e-9
    h = 1e-6
    for s in (0., 1.):
        v = (roll.offset(min(s + h, 1)) - roll.offset(max(s - h, 0))) / h
        assert np.linalg.norm(v) < 1e-6                                   # zero velocity at both ends
    s = np.linspace(0, 1, 101)
    d = np.linalg.norm(roll.offset(s)[1:] - roll.offset(s)[:-1], axis=1)
    assert np.isclose(d.sum(), np.linalg.norm(roll.roll), atol=1e-9)   # straight line, monotone


def test_chair_shell_clears_the_real_desk_along_the_roll():
    chair = K.load_chair()
    assert np.allclose(chair['translation_cm'], [200.0199556350708, -186.69002056121826, 60.68757772445679])
    g = K.load_geometry()
    B, nodes = K.desk_boxes(g)
    roll = K.ChairRoll(chair['translation_cm'], K.ROLL_OFFSET_CM)
    rep = K.chair_path_clearance(chair, roll, B, nodes, samples=21)
    assert rep['clear_all_samples'] and rep['worst']['min_cm'] > 0
    # the measured chair has no armrests: away from the seat centre the shell never rises above the cushion
    v = chair['shell_vertices_cm']
    side = np.abs(v[:, 0] - chair['translation_cm'][0]) > 20
    assert v[side & (v[:, 1] < -177), 2].max() < 52.


# ---------------------------------------------------------------- the committed proposal
PROPOSAL = ROOT / 'docs/proposed/seated-typing-ik/seated-typing-ik.proposal.json'


@pytest.mark.skipif(not PROPOSAL.exists(), reason='no committed proposal')
def test_committed_proposal_is_labelled_and_consistent():
    p = json.loads(PROPOSAL.read_text())
    assert p['label'] == 'proposal' and p['verified'] is False and p['requires_server_reaudit'] is True
    assert p['geometry']['sha256'] == hashlib.sha256(K.GEOMETRY_JSON.read_bytes()).hexdigest()
    roll = p['chair_roll_activity']
    assert np.allclose(roll['start_transform_cm'], p['chair']['translation_cm'], atol=1e-3)
    assert roll['reversibility']['reversible'] and roll['chair_shell_clearance_along_path']['clear_all_samples']
    for name, clip in p['clips'].items():
        path = ROOT / clip['glb']
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == clip['sha256']
        assert str(path).startswith(str(ROOT / 'docs/proposed/seated-typing-ik'))
        rep = json.loads((path.parent / (path.stem + '.report.json')).read_text())
        assert rep['all_gates_pass'] == clip['all_gates_pass']
    assert p['constants']['key_gap_max_cm'] == .2 and p['constants']['min_support_vertices'] == 12
