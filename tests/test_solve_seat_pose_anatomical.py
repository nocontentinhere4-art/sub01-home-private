"""Anatomical seated pose solver (tools/solve_seat_pose_anatomical.py): synthetic chain, limits, skinning, main margins."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import export_seat_fit_source as E  # noqa: E402
import fit_seat_pelvis_pitch as P  # noqa: E402
import fit_seat_pose_trial as T  # noqa: E402
import solve_seat_pose_anatomical as A  # noqa: E402

NAMES = ['Hips', 'Spine', 'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase', 'RightUpLeg', 'RightLeg', 'RightFoot',
         'RightToeBase']
PARENTS = [-1, 0, 0, 2, 3, 4, 0, 6, 7, 8]
OFFSETS = {'Hips': (0, .9, 0), 'Spine': (0, .1, 0), 'LeftUpLeg': (.1, -.06, 0), 'LeftLeg': (0, -.42, 0),
           'LeftFoot': (0, -.40, 0), 'LeftToeBase': (0, -.07, .12), 'RightUpLeg': (-.1, -.06, 0),
           'RightLeg': (0, -.42, 0), 'RightFoot': (0, -.40, 0), 'RightToeBase': (0, -.07, .12)}


def rx(a):
    c, s = np.cos(np.radians(a)), np.sin(np.radians(a))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rz(a):
    c, s = np.cos(np.radians(a)), np.sin(np.radians(a))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def fk(local_rot):
    """World matrices (1, J, 4, 4) of the synthetic legs; local_rot: name -> 3x3 (bind = identity everywhere)."""
    W = np.zeros((1, len(NAMES), 4, 4))
    for k, n in enumerate(NAMES):
        L = np.eye(4)
        L[:3, :3] = local_rot.get(n, np.eye(3))
        L[:3, 3] = OFFSETS[n]
        W[0, k] = L if PARENTS[k] < 0 else W[0, PARENTS[k]] @ L
    return W


BIND = fk({})[0]


def test_bind_is_anatomical_zero():
    ang = A.joint_angles(BIND[None], BIND, NAMES)
    assert all(abs(float(v[0])) < 1e-9 for v in ang.values())
    assert A.limit_excess(ang).max() == 0


@pytest.mark.parametrize('side', ['left', 'right'])
def test_sagittal_signs(side):
    pre = A.SIDES[side]
    W = fk({f'{pre}UpLeg': rx(-40), f'{pre}Leg': rx(70), f'{pre}Foot': rx(-15)})   # thigh forward, shin back, toes up
    ang = A.joint_angles(W, BIND, NAMES)
    assert ang[f'{side}_hip_flexion'][0] == pytest.approx(40, abs=1e-6)
    assert ang[f'{side}_knee_flexion'][0] == pytest.approx(70, abs=1e-6)
    assert ang[f'{side}_ankle_dorsiflexion'][0] == pytest.approx(15, abs=1e-6)
    thigh = W[0, NAMES.index(f'{pre}Leg'), :3, 3] - W[0, NAMES.index(f'{pre}UpLeg'), :3, 3]
    assert thigh[2] > 0                                                 # flexion moves the knee forward (+Z)


@pytest.mark.parametrize('side,sign', [('left', 1.), ('right', -1.)])
def test_abduction_and_inversion_signs(side, sign):
    pre = A.SIDES[side]
    W = fk({f'{pre}UpLeg': rz(sign * 20), f'{pre}Foot': rz(-sign * 10)})
    ang = A.joint_angles(W, BIND, NAMES)
    assert ang[f'{side}_hip_abduction'][0] == pytest.approx(20, abs=1e-6)
    assert ang[f'{side}_subtalar_inversion'][0] == pytest.approx(10, abs=1e-6)
    knee = W[0, NAMES.index(f'{pre}Leg'), :3, 3]
    assert np.sign(knee[0]) == sign                                     # abduction moves the knee laterally


def test_limit_excess_counts_degrees_outside_the_ranges():
    W = fk({'LeftFoot': rx(-30), 'RightLeg': rx(-10)})                  # 30 deg dorsiflexion (>20), knee hyperextended 10
    ex = A.limit_excess(A.joint_angles(W, BIND, NAMES))
    assert ex[0] == pytest.approx(10 + 5, abs=1e-6)
    ok = A.limit_excess(A.joint_angles(fk({'LeftFoot': rx(-19), 'RightLeg': rx(100)}), BIND, NAMES))
    assert ok[0] == 0


def test_pelvis_tilt_edit_bound_is_relative_to_the_capture():
    cap = A.joint_angles(fk({'Hips': rx(-5)}), BIND, NAMES)
    assert cap['pelvis_posterior_tilt'][0] == pytest.approx(5, abs=1e-6)
    lim = A.EDIT_LIMITS['pelvis_tilt_change_deg']
    W = fk({'Hips': rx(-(5 + lim + 3))})                                # inside the absolute 0..45 range
    ex = A.limit_excess(A.joint_angles(W, BIND, NAMES), cap)
    assert ex[0] == pytest.approx(3, abs=1e-6)


def test_twist_about_y_recovers_heading_under_swing():
    for a in (-50., 0., 35.):
        R = A.yaw_matrix(np.radians(a)) @ rx(-30)
        assert np.degrees(A.twist_about_y(R[None]))[0] == pytest.approx(a, abs=1e-6)


def test_two_bone_leg_keeps_bone_lengths_and_reaches():
    W = np.repeat(fk({'LeftUpLeg': rx(-80), 'LeftLeg': rx(80)}), 3, axis=0)
    sk = T.Skeleton(SimpleNamespace(names=NAMES, parents=np.array(PARENTS)))
    lengths = [np.linalg.norm(W[:, k, :3, 3] - W[:, p, :3, 3], axis=1) for k, p in enumerate(PARENTS) if p >= 0]
    tgt = W[:, NAMES.index('LeftFoot'), :3, 3] + np.array([0, -.03, .05])
    M = np.tile(np.eye(4), (3, 1, 1))
    W2, reach, _, _ = sk.two_bone_pose(W.copy(), ('LeftUpLeg', 'LeftLeg', 'LeftFoot'), tgt,
                                      W[:, NAMES.index('LeftLeg'), :3, 3], end_world_rot=M)
    assert reach.all()
    assert np.allclose(W2[:, NAMES.index('LeftFoot'), :3, 3], tgt, atol=1e-12)
    after = [np.linalg.norm(W2[:, k, :3, 3] - W2[:, p, :3, 3], axis=1) for k, p in enumerate(PARENTS) if p >= 0]
    assert max(np.abs(a - b).max() for a, b in zip(lengths, after)) < 1e-12


def synthetic_source(rng):
    J = 3
    names, parents = ['Hips', 'LeftUpLeg', 'RightUpLeg'], np.array([-1, 0, 0])
    ibm = np.tile(np.eye(4), (J, 1, 1))
    W = np.tile(np.eye(4), (2, J, 1, 1))
    W[:, :, :3, 3] = rng.normal(0, .1, (2, J, 3))
    d = {'meta': np.array(json.dumps({'counts': {}})), 'names': np.array(names), 'parents': parents, 'ibm': ibm,
         'joint_world': W}
    for n in T.SEAT_PATCHES + T.SOLE_PATCHES:
        N = 40
        w = rng.random((N, 4))
        d[f'{n}.pos'] = rng.normal(0, .2, (N, 3)).astype(np.float32)
        d[f'{n}.nrm'] = rng.normal(0, 1, (N, 3)).astype(np.float32)
        d[f'{n}.joints'] = rng.integers(0, J, (N, 4)).astype(np.int16)
        d[f'{n}.weights'] = (w / w.sum(1, keepdims=True)).astype(np.float32)
    return E.Source(d)


def test_fast_skinning_equals_the_fitter_skinning():
    src = synthetic_source(np.random.default_rng(3))
    fm = A.FastMeasure(SimpleNamespace(src=src))
    W = src.joint_world
    W[1, 1, :3, :3] = rx(25)
    for n in T.SEAT_PATCHES + T.SOLE_PATCHES:
        p0, n0 = src.skin(n, W)
        p1, n1 = fm.skin(n, W)
        assert np.abs(p0 - p1).max() < 1e-12 and np.abs(n0 - n1).max() < 1e-12


def _main_validator():
    import recheck_seat_fit_main_rule as R
    try:
        return R, R.load_main_validator(R.main_validator_bytes())
    except subprocess.CalledProcessError:
        pytest.skip('origin/main is not available in this checkout')


def test_margins_agree_with_mains_validate():
    R, V = _main_validator()
    rng = np.random.default_rng(7)
    for _ in range(200):
        m = {}
        for n in V.REGIONS:
            over = int(rng.integers(5, 60))
            m[n] = {'over': np.array([over]), 'facing': np.array([over]), 'band': np.array([int(rng.integers(0, over + 1))]),
                    'lowest': np.array([rng.uniform(-3.5, 1.)]), 'median': np.array([rng.uniform(-1., 2.)])}
        ok = A.worst_margin(A.main_margins(V, m))[0] >= 0
        assert ok == (R.judge_frame(V, R.frame_regions(m, 0)) is None)


def test_param_bounds_and_edit_cost():
    assert A.param_bounds_excess(np.zeros(len(A.PARAMS))) == 0
    x = np.zeros(len(A.PARAMS))
    x[1] = 20.                                                          # 20 cm down: the vertical bound is -14
    assert A.param_bounds_excess(x) == pytest.approx(6.)
    assert A.edit_cost(np.zeros(len(A.PARAMS))) == 0


def test_committed_report_is_labelled_and_main_judged():
    path = ROOT / 'docs/proposed/seat-pose-anatomical/seat-pose-anatomical.report.json'
    if not path.exists():
        pytest.skip('no committed anatomical report')
    rep = json.loads(path.read_text())
    assert rep['label'] == 'proposal' and rep['verified'] is False and rep['changes_importer_pins_or_verdicts'] is False
    assert rep['main_validator']['sha256'] == 'dd95f1b1a8c3fc9a7d08b6d599985b86440c84752d85ae9f12fa8d480397a18f'
    assert 'no local-support' in rep['objective']
    seen = 0
    for cand in rep['candidates'].values():
        for clip, c in cand.get('clips', {}).items():
            seen += 1
            assert c['main_rule']['gated_frames'] > 0
            assert c['bone_length_max_error_cm'] <= 1e-3
            assert all((r.get('local_translation_change_cm') or 0) <= 1e-4 for r in c.get('joint_edits_vs_capture', {}).values())
            glb = ROOT / c['glb']
            assert glb.exists() and hashlib.sha256(glb.read_bytes()).hexdigest() == c['sha256']
    assert seen


def _clip(**over):
    c = {'main_rule': {'pass_main_rule': True}, 'anatomical_limits_ok': True,
         'clearance': {'chair_complete': {'clear': True}, 'desk': {'clear': True}}}
    for k, v in over.items():
        if k == 'desk':
            c['clearance']['desk']['clear'] = v
        else:
            c[k] = v
    return c


def test_source_ready_requires_every_clip_and_check():
    good = {n: _clip() for n in A.REQUIRED_CLIPS}
    assert A.source_ready(good)
    r = A.readiness({'x': good})
    assert r['source_ready'] == {'x': True} and r['native_ready'] is False and r['ready'] is False
    assert not A.source_ready(dict(good, SitDown=_clip(desk=False)))                 # desk clearance failed
    assert not A.source_ready(dict(good, SeatedIdle=_clip(anatomical_limits_ok=False)))  # ankle over the limit
    assert not A.source_ready(dict(good, GetUp={'skipped': 'wall-clock cap'}))       # skipped transition
    assert not A.source_ready({k: v for k, v in good.items() if k != 'GetUp'})       # missing transition
    assert not A.source_ready(dict(good, GetUp=_clip(main_rule={'pass_main_rule': False})))
