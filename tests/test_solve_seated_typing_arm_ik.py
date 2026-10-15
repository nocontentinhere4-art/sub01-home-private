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


def test_point_triangle_distance_exact_cases():
    a, b, c = np.array([[0., 0, 0]]), np.array([[1., 0, 0]]), np.array([[0., 1, 0]])
    pts = np.array([[.2, .2, .5], [2., 0, 0], [-1., -1, 0], [.5, .5, -1.]])
    d = [K.point_triangle_distance(p[None], a, b, c)[0] for p in pts]
    assert np.allclose(d, [.5, 1., math.sqrt(2), 1.])


def test_complete_chair_is_the_measured_native_chair_with_arms_base_and_castors():
    pytest.importorskip('scipy')
    chair = K.load_chair()
    assert np.allclose(chair['translation_cm'], [200.0199556350708, -186.69002056121826, 60.68757772445679])
    c = K.load_complete_chair(chair)
    assert c['source_sha256'] == K.CHAIR_SOURCE_SHA256
    assert set(c['triangles_by_material']) >= {'chair_fabric', 'chair_plastic', 'chair_armpad', 'chair_base', 'chair_caster', 'chair_lift'}
    assert c['measured_shell_on_source_surface_cm']['max'] <= K.CHAIR_MATCH_TOL_CM
    assert c['armrest_top_cm'] > 60                      # the actual chair HAS arm pads (about 67 cm)
    col = K.ChairCollider(c)
    m, mat = col.margin(np.array([[170.5, -190., 75.], [170.5, -190., 66.]]), np.zeros(3))
    assert m[0] > 0 and m[1] < 0 and mat[1] == 'chair_armpad'       # above the pad clear; inside it refused


def test_complete_chair_roll_clears_the_desk_and_keeps_its_floor_contact():
    pytest.importorskip('scipy')
    chair = K.load_chair()
    c = K.load_complete_chair(chair)
    B, nodes = K.desk_boxes(K.load_geometry())
    rep = K.chair_path_clearance(c, K.ChairRoll(chair['translation_cm'], K.ROLL_OFFSET_CM), B, nodes, samples=21)
    assert rep['desk_clear_all_samples'] and rep['floor_gap_constant_along_roll']
    # the measured chair's caster bottoms sit at 0.0 cm, the support plane is 2.5 cm: reported AND gated, never hidden
    assert rep['floor_gap_cm'][0] == pytest.approx(c['lowest_cm'] - K.FLOOR_CM)
    assert rep['floor_no_penetration'] == (c['lowest_cm'] >= K.FLOOR_CM)


def test_finger_contract_refuses_any_finger_change():
    sk, W, ibm = synthetic()
    ctx = SimpleNamespace(sk=sk, finger_joints=[NAMES.index(n) for n in NAMES if 'Hand' in n and n != 'LeftHand'])
    W3 = np.repeat(W, 3, axis=0)
    t = np.array([0., 1 / 30, 2 / 30])
    ok = K.finger_contract(ctx, W3, W3, t)
    assert ok['pass']
    bent = W3.copy()
    k = NAMES.index('LeftHandMiddle2')
    R = rot((0, 0, 1), .2)
    piv = bent[1, k, :3, 3].copy()
    for j in (k, k + 1):
        bent[1, j, :3, :3] = R @ bent[1, j, :3, :3]
        bent[1, j, :3, 3] = piv + R @ (bent[1, j, :3, 3] - piv)
    bad = K.finger_contract(ctx, bent, W3, t)
    assert not bad['pass'] and bad['worst_error']['value'] == pytest.approx(.2, abs=1e-6)


def test_exit_code_refuses_unless_every_gate_passes(monkeypatch):
    assert K.exit_code({'ready': True, 'gates': {'a': True, 'b': True}}) == 0
    assert K.exit_code({'ready': True, 'gates': {'a': True, 'b': False}}) == K.EXIT_REFUSED != 0
    assert K.exit_code({'ready': False, 'gates': {'a': True}}) == K.EXIT_REFUSED
    assert K.exit_code({}) == K.EXIT_REFUSED
    for ready, want in ((False, K.EXIT_REFUSED), (True, 0)):
        summary = {'ready': ready, 'gates': {'g': ready}}
        monkeypatch.setattr(K, 'run', lambda args, s=summary: (s, {}))
        assert K.main(['--out-dir', '/nonexistent-not-written']) == want


# ---------------------------------------------------------------- the committed proposal
PROPOSAL = ROOT / 'docs/proposed/seated-typing-ik/seated-typing-ik.proposal.json'


@pytest.mark.skipif(not PROPOSAL.exists(), reason='no committed proposal')
def test_committed_proposal_is_labelled_and_consistent():
    p = json.loads(PROPOSAL.read_text())
    assert p['label'] == 'proposal' and p['verified'] is False and p['requires_server_reaudit'] is True
    assert p['geometry']['sha256'] == hashlib.sha256(K.GEOMETRY_JSON.read_bytes()).hexdigest()
    assert p['native_verified'] is False and 'bounded' in p
    if 'partial' in p:          # a bounded run that stopped between stages: never ready, stage and blocker stated
        assert p['ready'] is False and p['partial']['stage_reached'] and p['partial']['blocker']
    else:
        roll = p['chair_roll_activity']
        assert np.allclose(roll['start_transform_cm'], p['chair']['translation_cm'], atol=1e-3)
        assert roll['reversibility']['reversible'] and roll['reversibility']['final_equals_initial_exact']
        assert p['gates']['roll_reversible_exact'] is True
        assert p['ready'] == all(p['gates'].values())
        assert p['gates']['roll_complete_chair_clear_of_desk'] == roll['complete_chair_clearance_along_path']['desk_clear_all_samples']
    for name, clip in p['clips'].items():
        path = ROOT / clip['glb']
        assert path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == clip['sha256']
        assert str(path).startswith(str(ROOT / 'docs/proposed/seated-typing-ik'))
        rep = json.loads((path.parent / (path.stem + '.report.json')).read_text())
        assert rep['all_gates_pass'] == clip['all_gates_pass']
    assert p['constants']['key_gap_max_cm'] == .2 and p['constants']['min_support_vertices'] == 12


# ---------------------------------------------------------------- main's strong seat rule, ergonomics, warm-start inputs
def test_main_strong_seat_rule_needs_median_touch_and_half_coverage():
    def metrics(over, band, lowest, median):
        F = len(over)
        return {'over': np.array(over), 'band': np.array(band), 'lowest': np.array(lowest, float), 'median': np.array(median, float),
                'facing': np.array(over)}
    good = metrics([100, 100], [60, 50], [-1., -.5], [.3, .5])
    sparse = metrics([100, 100], [60, 12], [-1., -.5], [.3, .4])      # passes the branch's 12-vertex rule, not coverage
    floating = metrics([100, 100], [60, 60], [-1., -.5], [.3, .6])    # median above the band
    fit = SimpleNamespace(trial=SimpleNamespace(seat=lambda W: {'buttocks': good, 'left_posterior_thigh': sparse,
                                                                'right_posterior_thigh': floating},
                                                soles=lambda W: {'left_sole': metrics([50, 50], [30, 30], [0., 0.], [.2, .9]),
                                                                 'right_sole': metrics([50, 50], [30, 30], [0., 0.], [.2, 1.2])}))
    r = K.main_strong_seat_rule(fit, None, np.array([0., 1.]))
    reg = r['regions']
    assert reg['buttocks']['pass_all_frames'] and reg['left_sole']['pass_all_frames']
    assert not reg['left_posterior_thigh']['pass_all_frames'] and reg['left_posterior_thigh']['failing_frames'] == 1
    assert not reg['right_posterior_thigh']['pass_all_frames'] and not reg['right_sole']['pass_all_frames']
    assert not r['pass'] and K.MAIN_MIN_BAND_COVERAGE == .5 and 'origin/main' in r['rule']


def test_ergonomic_cost_is_zero_inside_the_soft_targets_and_grows_outside():
    ik = K.ClipArmIK.__new__(K.ClipArmIK)
    ik.geometry = {'tabletop_slab': {'top_cm': 84.5}}
    c = ik.ergonomic_cost(np.array([84.5, 90., 94.5, 100., 80.]), np.array([0., 15., 20., 20., 10.]))
    assert np.allclose(c[:3], 0.) and c[3] > 0 and c[4] > 0
    assert ik.ergonomic_cost(np.array([90.]), np.array([40.]))[0] > ik.ergonomic_cost(np.array([90.]), np.array([30.]))[0]


def test_given_chair_transform_moves_the_whole_chair_rigidly():
    pytest.importorskip('scipy')
    m = K.load_chair()
    lifted = K.load_chair(translation_cm=np.asarray(m['translation_cm']) + [0, 0, 2.5])
    assert np.allclose(lifted['proposed_delta_cm'], [0, 0, 2.5]) and not lifted['translation_is_measured']
    assert np.allclose(lifted['cushion_triangles_cm'], m['cushion_triangles_cm'] + [0, 0, 2.5])
    c = K.load_complete_chair(lifted)
    assert c['lowest_cm'] == pytest.approx(2.5)
    B, nodes = K.desk_boxes(K.load_geometry())
    rep = K.chair_path_clearance(c, K.ChairRoll(lifted['translation_cm'], K.ROLL_OFFSET_CM), B, nodes, samples=11)
    assert rep['floor_no_penetration'] and rep['desk_clear_all_samples']


def test_keycaps_from_world_json(tmp_path):
    tri = [[[0, 0, 87.], [1, 0, 87.], [0, 1, 87.]]]
    doc = {'keycaps': [{'topTrianglesUECm': tri, 'topCm': 87., 'minCm': [0, 0, 86], 'maxCm': [1, 1, 87]},
                       {'topTrianglesUECm': [], 'topCm': 86.5, 'minCm': [2, 0, 86], 'maxCm': [3, 1, 86.5]}]}
    p = tmp_path / 'keyboard-keycaps-world.json'
    p.write_text(json.dumps(doc))
    k = K.keycaps_from_world_json(p)
    assert k['triangles'].shape == (1, 3, 3) and k['top_cm'] == 87. and k['keycaps'] == 1
    assert np.allclose(k['key_min'], [0, 0, 86]) and np.allclose(k['key_max'], [3, 1, 87])


def test_configure_warm_start_inputs():
    old = (K.FIT_DIR, K.ROLL_OFFSET_CM)
    try:
        d, r = K.configure('docs/proposed/seat-pose-anatomical', (3.875, -30.))
        assert d == ROOT / 'docs/proposed/seat-pose-anatomical' and r == (3.875, -30.)
    finally:
        K.FIT_DIR, K.ROLL_OFFSET_CM = old


# ---------------------------------------------------------------- SitDown / GetUp desk-clearance arm pass
def test_box_push_directions():
    lo, hi = np.zeros(3), np.array([10., 10., 2.])
    d = K.box_push(np.array([[5, 5, 1.9], [5, 5, .1], [5, 9.9, 1.], [12, 5, 1.]]), lo, hi)
    assert np.allclose(d, [[0, 0, 1], [0, 0, -1], [0, 1, 0], [1, 0, 0]])
    d = K.box_push(np.array([[5, 5, .1], [5, .05, .1]]), lo, hi, no_down=True)
    assert np.allclose(d, [[0, 0, 1], [0, -1, 0]])


def test_desk_clear_arms_lifts_the_hand_out_of_a_slab_and_keeps_protected_frames():
    sk, W, ibm = synthetic()
    F = 6
    W = np.repeat(W, F, axis=0)
    h = NAMES.index('LeftHand')
    # skin: two points riding on the hand (the wrist and a little below it)
    pos = np.array([BIND['LeftHand'], np.add(BIND['LeftHand'], (.02, -.02, 0))], float)
    jts = np.full((2, 4), h)
    wts = np.array([[1., 0, 0, 0]] * 2)
    hand_ue = K.E.to_ue(W[0, h, :3, 3])
    slab = np.array([[[hand_ue[0] - 20, hand_ue[1] - 20, hand_ue[2] - 5], [hand_ue[0] + 20, hand_ue[1] + 20, hand_ue[2] + 1.]]])
    ctx = SimpleNamespace(sk=sk, base=SimpleNamespace(ibm=ibm, names=NAMES), boxes=slab,
                          arms={'left': {'skin': (pos, jts, wts), 'part': np.array(['hand', 'hand'])}})
    protect = np.zeros(F, bool)
    protect[-1] = True
    times = np.arange(F) / 30.
    shift = np.zeros((F, 3))
    out, info = K.desk_clear_arms(ctx, W, shift, times, protect, sides=('left',))
    pts = K.E.to_ue(K.P.skin_points((pos, jts, wts), ibm, out))
    d, _ = K.boxes_min_distance(pts, slab)
    assert (d.min(1)[:-1] >= K.FOREARM_TARGET_CLEARANCE_CM - 1e-6).all()
    assert np.allclose(out[-1], W[-1])                                         # protected frame untouched
    for a, b in ((2, 3), (3, 4)):                                              # no stretch
        assert np.allclose(np.linalg.norm(out[:, b, :3, 3] - out[:, a, :3, 3], axis=1), np.linalg.norm(W[:, b, :3, 3] - W[:, a, :3, 3], axis=1))
    assert np.allclose(K.arm_locals(sk, out)[:, NAMES.index('LeftHandMiddle2')], K.arm_locals(sk, W)[:, NAMES.index('LeftHandMiddle2')])


def test_base_invariance_allows_only_the_arm_chains():
    sk, W, ibm = synthetic()
    ctx = SimpleNamespace(sk=SimpleNamespace(names=NAMES, subtree=sk.subtree, j=sk.j))
    old = K.SIDES
    try:
        K.SIDES = {'left': 'Left'}
        W2 = pose_hand(W, rot((0, 0, 1), 20))               # an arm change: allowed
        r = K.base_invariance(ctx, W2, W, np.array([0.]))
        assert r['pass'] and r['joints_checked'] == 1       # Hips (the shoulder girdle belongs to the arm step)
        W3 = W2.copy()
        W3[:, 0, :3, 3] += [0, .001, 0]                     # the pelvis moves 0.1 cm: refused
        r = K.base_invariance(ctx, W3, W, np.array([0.]))
        assert not r['pass'] and r['max_position_cm']['value'] == pytest.approx(.1)
    finally:
        K.SIDES = old


# ---------------------------------------------------------------- segmentation, mouse, girdle, fast paths
def test_segment_hand_key_mouse_transit():
    keys = {'key_max': np.array([218.55, -287.9, 87.4])}
    F = 60
    on = np.zeros(F, bool)
    on[:20] = True
    palm = np.zeros((F, 3))
    palm[:20, 0] = 205.
    palm[20:30, 0] = np.linspace(205, 235, 10)      # fast travel to the mouse
    palm[30:, 0] = 235.                             # resting on the mouse
    mode = K.segment_hand(on, palm, 1 / 30, keys, mouse={'palm_target_cm': np.zeros(3)})
    assert (mode[:20] == K.MODE_KEY).all() and (mode[45:] == K.MODE_MOUSE).all() and (mode[20:28] == K.MODE_TRANSIT).all()
    assert (K.segment_hand(on, palm, 1 / 30, keys, None)[20:] == K.MODE_TRANSIT).all()


def test_keyboard_between_keys_reclassifies_only_runs_flanked_by_keyboard():
    K_, M_, T_ = K.MODE_KEY, K.MODE_MOUSE, K.MODE_TRANSIT
    mode = np.array([T_, T_, K_, K_, T_, T_, K_, T_, T_, M_, M_, T_, K_, T_])
    out = K.keyboard_between_keys(mode)
    assert out[4:6].tolist() == [K_, K_]                       # between two keyboard segments: keyboard
    assert out[:2].tolist() == [T_, T_] and out[-1] == T_      # clip ends stay transit
    assert out[7:9].tolist() == [T_, T_] and out[11] == T_     # keyboard <-> mouse stays transit
    assert (out[mode != T_] == mode[mode != T_]).all()         # keyboard / mouse frames never change
    assert (K.keyboard_between_keys(out) == out).all()


def test_key_field_pull_brings_enough_vertices_inside_the_field():
    lo, hi = np.array([180., -300., 0.]), np.array([220., -290., 0.])
    p = np.zeros((2, 20, 2))
    p[0] = np.c_[np.linspace(222, 230, 20), np.full(20, -295.)]   # right of the field
    p[1] = np.c_[np.linspace(200, 210, 20), np.full(20, -295.)]   # already inside
    pull = K.key_field_pull(p, lo, hi, n=8, margin=.5)
    q = p[0] + pull[0]
    assert ((q[:, 0] <= hi[0]) & (q[:, 0] >= lo[0])).sum() >= 8
    assert np.allclose(pull[1], 0.)


def test_girdle_clearance_candidates_stay_inside_the_cited_ranges():
    for dep, pro in K.GIRDLE_CLEAR_CANDIDATES:
        assert -10. <= dep <= 0.                                       # elevation only, at most 10 deg
        assert K.GIRDLE_PROTRACTION_DEG[0] <= pro <= 0.                # retraction inside the cited +-15 deg
    deps = [d for d, _ in K.GIRDLE_CLEAR_CANDIDATES]
    assert deps == sorted(deps, reverse=True)                          # smallest elevation first
    assert K.POLISH_ACCEPT_GAP_CM[0] >= 0. and K.POLISH_ACCEPT_GAP_CM[1] < K.contact_profile.KEY_GAP_MAX_CM
    assert K.POLISH_ACCEPT_GAP_CM[0] >= -K.P.KEY_PENETRATION_MAX_CM


def test_axis_rotation_and_clearance_candidates():
    R = K.axis_rotation([0., 0., 1.], np.radians([90., 0.]))
    assert np.allclose(R[0] @ [1., 0., 0.], [0., 1., 0.]) and np.allclose(R[1], np.eye(3))
    assert all(0. < c <= 45. for c in K.PITCH_CLEAR_CANDIDATES)       # added flexion; the soft +-15 deg limit follows
    assert list(K.PITCH_CLEAR_CANDIDATES) == sorted(K.PITCH_CLEAR_CANDIDATES)


def test_seam_taper_is_zero_at_the_seam_and_c1():
    w = K.seam_taper(40, [0, 39], 1 / 30, .2)
    assert w[0] == 0. and w[39] == 0. and np.allclose(w[6:34], 1.)
    assert w[1] < .05 and w[38] < .05 and np.all(np.diff(w[:7]) >= 0)


def test_transit_blend_is_c1_and_meets_the_segment_values():
    ik = K.ClipArmIK.__new__(K.ClipArmIK)
    F = 30
    ik.mode = {'right': np.r_[np.full(10, K.MODE_KEY), np.full(10, K.MODE_TRANSIT), np.full(10, K.MODE_MOUSE)]}
    ik.hand_xy = {'right': np.r_[np.zeros((10, 3)), np.zeros((10, 3)), np.tile([.1, 0, 0], (10, 1))]}
    d = ik.blend_transit('right', np.r_[np.full(10, 2.), np.zeros(10), np.full(10, 5.)])
    assert np.all(np.diff(d[9:21]) >= -1e-12) and d[9] == 2. and d[20] == 5.
    steps = np.diff(d[9:21])
    assert steps[0] < steps[5] and steps[-1] < steps[5]                     # slow at both ends (zero slope)
    assert np.isclose(ik.hand_xy['right'][14, 0], .1 * float(K.smootherstep(np.array(5 / 11))))


def test_shoulder_girdle_depression_and_protraction_carry_the_arm():
    sk, W, ibm = synthetic()
    k, a = NAMES.index('LeftShoulder'), NAMES.index('LeftArm')
    out = K.shoulder_girdle(sk, W.copy(), 'left', np.array([[10., 0.]]))
    v0, v1 = W[0, a, :3, 3] - W[0, k, :3, 3], out[0, a, :3, 3] - out[0, k, :3, 3]
    assert np.isclose(np.linalg.norm(v0), np.linalg.norm(v1)) and v1[1] < v0[1] - 1e-6        # lateral end down
    assert np.isclose(math.degrees(math.atan2(-v1[1], v1[0])), 10., atol=1e-6)
    out = K.shoulder_girdle(sk, W.copy(), 'left', np.array([[0., 15.]]))
    v1 = out[0, a, :3, 3] - out[0, k, :3, 3]
    assert v1[2] > 0 and np.isclose(math.degrees(math.atan2(v1[2], v1[0])), 15., atol=1e-6)    # forward (+z)
    assert np.allclose(K.arm_locals(sk, out)[:, NAMES.index('LeftForeArm')], K.arm_locals(sk, W)[:, NAMES.index('LeftForeArm')])


def test_fast_lbs_and_shift_match_the_reference():
    sk, W, ibm = synthetic()
    rng_ = np.random.default_rng(3)
    pos = rng_.normal(0, .3, (50, 3)) + [.5, 1.3, 0]
    jts = rng_.integers(0, len(NAMES), (50, 4))
    wts = rng_.random((50, 4))
    wts /= wts.sum(1, keepdims=True)
    Wp = pose_hand(W, rot((1, 1, 0), 30))
    assert np.allclose(K.lbs((pos, jts, wts), ibm, Wp), K.P.skin_points((pos, jts, wts), ibm, Wp), atol=1e-12)
    d = np.array([[1., -2., 3.], [0., 5., -1.]])
    assert np.allclose(K.gltf_shift(d), np.stack([K.P.ue_delta_to_gltf(v) for v in d]))


def test_rasters_agree_with_the_exact_surface_test():
    from fit_seat_rigid_placement import Surface
    tri = np.array([[[0., 0, 1], [2, 0, 1], [0, 2, 1]], [[3., 3, 2], [5, 3, 2], [3, 5, 2]]])
    keys = {'key_min': np.array([0., 0, 0]), 'key_max': np.array([5., 5, 2]), 'triangles': tri}
    r, h = K.KeyRaster(keys), K.HeightRaster(tri)
    xy = np.random.default_rng(4).uniform(0, 5, (20000, 2))
    f, z = Surface(tri).height(xy)
    assert (r.over(xy) != f).mean() < .01
    fh, zh = h.height(xy)
    both = fh & f
    assert (fh != f).mean() < .01 and np.allclose(zh[both], z[both])


def test_mouse_is_the_actual_mouse_at_its_record_footprint():
    m = K.mouse_geometry()
    lo, hi = np.array(m['footprint_ue_cm'][0]), np.array(m['footprint_ue_cm'][1])
    assert np.allclose(lo[:2], [229., -301.45], atol=1e-3) and np.allclose(hi[:2], [251., -280.55], atol=1e-3)
    t = m['palm_target_cm']
    assert np.isclose(t[0], m['shell_top_cm'][0] + 1.2) and np.isclose(t[1], m['shell_top_cm'][1] + 2.2)
    assert np.isclose(t[2], m['shell_surface_at_palm_cm'] + 1.6) and lo[2] == pytest.approx(84.6)
