"""Seat pelvis-pitch TRIAL (tools/fit_seat_pelvis_pitch.py): kinematics, gates, chair swap, stable window, seam.

Synthetic tests always run. The committed-report test runs when docs/proposed/seat-pose-fit/ holds a report.
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import fit_seat_pelvis_pitch as P  # noqa: E402
import fit_seat_pose_trial as T  # noqa: E402
import validate_unreal_contact_profile as contact_profile  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402

NAMES = ['Hips', 'Spine', 'Spine1', 'Head', 'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase',
         'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase']
PARENTS = [-1, 0, 1, 2, 0, 4, 5, 6, 0, 8, 9, 10]
OFFSETS = {'Spine': (0, .1, -.02), 'Spine1': (0, .12, 0), 'Head': (0, .3, .02), 'LeftUpLeg': (.09, -.07, 0),
           'LeftLeg': (0, -.42, 0), 'LeftFoot': (0, -.40, 0), 'LeftToeBase': (0, -.05, .12), 'RightUpLeg': (-.09, -.07, 0),
           'RightLeg': (0, -.42, 0), 'RightFoot': (0, -.40, 0), 'RightToeBase': (0, -.05, .12)}


def synthetic(frames=5, seed=0):
    rng = np.random.default_rng(seed)
    src = SimpleNamespace(names=NAMES, parents=np.array(PARENTS))
    sk = T.Skeleton(src)
    W = np.zeros((frames, len(NAMES), 4, 4))
    for f in range(frames):
        for k, n in enumerate(NAMES):
            L = np.eye(4)
            ang = rng.normal(0, .3, 3)
            L[:3, :3] = P.rodrigues(ang[None] / max(np.linalg.norm(ang), 1e-9), np.array([np.linalg.norm(ang)]))[0]
            L[:3, 3] = (0, .74, .07) if n == 'Hips' else OFFSETS[n]
            if n == 'Hips':
                L[:3, :3] *= .01 / .01       # unit scale here; the real source carries 0.01 and unit_rot handles it
            W[f, k] = L if PARENTS[k] < 0 else W[f, PARENTS[k]] @ L
    return sk, W


def lengths(sk, W):
    return np.array([[np.linalg.norm(W[f, k, :3, 3] - W[f, p, :3, 3]) for k, p in enumerate(sk.parents) if p >= 0]
                     for f in range(len(W))])


def test_pelvis_pitch_keeps_bone_lengths_and_spine_world_orientation():
    sk, W = synthetic()
    axis = P.hips_lateral_local(sk, W)
    out = P.pelvis_pitch(sk, W, 17., 6.5, axis)
    assert np.abs(lengths(sk, out) - lengths(sk, W)).max() < 1e-12
    for n in ('Spine', 'Spine1', 'Head'):
        assert P.rot_angle_deg(W[:, sk.j(n), :3, :3], out[:, sk.j(n), :3, :3]).max() < 1e-6
    # the spine base is the pivot: it only moves by the lowering
    d = out[:, sk.j('Spine'), :3, 3] - W[:, sk.j('Spine'), :3, 3]
    assert np.allclose(d, [0, -.065, 0], atol=1e-12)
    # the hips really rotate by the pitch about the pelvis lateral axis
    assert np.allclose(P.rot_angle_deg(W[:, 0, :3, :3], out[:, 0, :3, :3]), 17., atol=1e-6)


def test_positive_pitch_lifts_the_knees_relative_to_the_hips():
    sk, W = synthetic(1, seed=3)
    W[:] = 0
    for k, n in enumerate(NAMES):            # upright rest pose, knees forward (+z)
        L = np.eye(4)
        L[:3, 3] = (0, .74, .07) if n == 'Hips' else OFFSETS[n]
        if n.endswith('Leg') and 'Up' not in n:
            L[:3, 3] = (0, 0, .42)
        W[0, k] = L if PARENTS[k] < 0 else W[0, PARENTS[k]] @ L
    out = P.pelvis_pitch(sk, W, 10., 0., P.hips_lateral_local(sk, W))
    assert out[0, sk.j('LeftLeg'), 1, 3] > W[0, sk.j('LeftLeg'), 1, 3]


def test_weighted_pitch_is_per_frame_and_zero_weight_is_identity():
    sk, W = synthetic(4)
    axis = P.hips_lateral_local(sk, W)
    out = P.pelvis_pitch(sk, W, np.array([0., 5., 10., 20.]), np.array([0., 1., 2., 3.]), axis, weight=np.array([0., 1., 1., .5]))
    assert np.allclose(out[0], W[0], atol=1e-12)
    assert np.allclose(P.rot_angle_deg(W[:, 0, :3, :3], out[:, 0, :3, :3]), [0, 5, 10, 10], atol=1e-6)


def test_leg_ik_does_not_stretch_and_keeps_the_foot_world_rotation():
    sk, W = synthetic(6, seed=1)
    chain = T.LEGS['left']
    foot = W[:, sk.j(chain[2])].copy()
    target = foot[:, :3, 3] + np.array([0, .03, 0])
    target[0] += [0, -2., 0]                                  # unreachable: must stay short, never stretch
    out, reach, length, dist = sk.two_bone_pose(W.copy(), chain, target, W[:, sk.j(chain[1]), :3, 3], end_world_rot=foot)
    assert np.abs(lengths(sk, out) - lengths(sk, W)).max() < 1e-12
    assert not reach[0] and reach[1:].all()
    assert np.allclose(out[1:, sk.j(chain[2]), :3, 3], target[1:], atol=1e-12)
    assert P.rot_angle_deg(foot[:, :3, :3], out[:, sk.j(chain[2]), :3, :3]).max() < 1e-6
    # descendants (toes) keep their local transform
    for M0, M1 in ((W, out),):
        l0 = np.linalg.inv(M0[:, sk.j(chain[2])]) @ M0[:, sk.j('LeftToeBase')]
        l1 = np.linalg.inv(M1[:, sk.j(chain[2])]) @ M1[:, sk.j('LeftToeBase')]
        assert np.allclose(l0, l1, atol=1e-12)


def test_contact_gates_come_from_the_validator_constants():
    assert P.SEAT_BAND_CM == seat_contact.SEAT_BAND_CM == (-2.5, .5)
    assert P.SOLE_BAND_CM == seat_contact.SOLE_BAND_CM == (0., 1.)
    assert P.MIN_SUPPORT_VERTICES == seat_contact.MIN_SUPPORT_VERTICES == 12
    assert P.MIN_PATCH_VERTICES == seat_contact.MIN_PATCH_VERTICES
    assert P.KEY_GAP_MAX_CM == contact_profile.KEY_GAP_MAX_CM == .2
    assert P.KEY_PENETRATION_MAX_CM == .1 and T.KEY_CONTACT_TARGET_CM == .08 and P.NATIVE_KEY_CAP_CM == 12.
    assert P.BAND_CENTRE_CM == -1.


def synthetic_chair_report(z=50.):
    verts = [[180., -210., z], [220., -210., z], [220., -170., z], [180., -170., z + 1.]]
    return {'errors': [], 'chair': {'transform': {'translation_cm': [200, -190, 60]},
                                   'component_world_bounds_cm': {'min': [175, -215, 40], 'max': [225, -165, 70]},
                                   'sections': [{'vertices_world_cm': verts,
                                                 'cushion_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]]}}]}}


def test_chair_switch_swaps_the_cushion(tmp_path):
    path = tmp_path / 'chair.json'
    path.write_text(json.dumps(synthetic_chair_report(50.)))
    tri, meta = P.load_cushion(path)
    assert not meta['proxy'] and tri.shape == (2, 3, 3)
    assert meta['chair_transform']['translation_cm'] == [200, -190, 60]
    surface = T.Surface(tri + np.array([3.875, -36.875, 0.]))
    found, h = surface.height(np.array([[190. + 3.875, -200. - 36.875]]))
    assert found[0] and h[0] == pytest.approx(50.)
    path.write_text(json.dumps(synthetic_chair_report(47.)))
    tri2, _ = P.load_cushion(path)
    assert np.allclose(tri2[..., 2] - tri[..., 2], -3.)
    if P.REAL_CHAIR.exists():                                  # the committed actual native cushion is the default
        real, meta_real = P.load_cushion()
        assert not meta_real['proxy'] and len(real) > 2
        lo, hi = real.reshape(-1, 3).min(0), real.reshape(-1, 3).max(0)
        assert lo == pytest.approx([173.661, -214.063, 44.357], abs=1e-3)
        assert hi == pytest.approx([226.132, -166.341, 51.407], abs=1e-3)


def test_stable_window_search_finds_the_still_part_of_a_synthetic_sitting_clip():
    fps = 30
    t = np.arange(0, 4.5, 1 / fps)
    hips = np.zeros((len(t), 3))
    s = P.smootherstep(t / 2.)                                  # 2 s sit-down: 36 cm back, 16 cm down
    hips[:, 2] = 38 * (1 - s)
    hips[:, 1] = 74 + 16 * (1 - s)
    hips[:, 0] = .05 * np.sin(t * 3)                            # breathing-size sway once seated
    wins, speed = P.stable_windows(hips, fps)
    assert len(wins) == 1
    a, b = wins[0]
    assert t[a] >= 1.6 and t[b] == pytest.approx(t[-1])
    assert speed[a:b + 1].max() <= P.STABLE_MAX_HIPS_SPEED_CM_S
    assert P.stable_windows(np.c_[np.arange(len(t)) * 1., hips[:, 1], hips[:, 2]], fps)[0] == []    # 30 cm/s drift


def test_seam_blend_is_continuous_and_closes_the_loop():
    F, J, n = 60, 3, 8
    rng = np.random.default_rng(2)
    ang = np.cumsum(rng.normal(0, .02, (F, J)), axis=0)
    q = np.stack([np.zeros((F, J)), np.sin(ang / 2), np.zeros((F, J)), np.cos(ang / 2)], axis=-1)
    ht = np.cumsum(rng.normal(0, .1, (F, 3)), axis=0)
    qb, tb, w = P.seam_blend_arrays(q, ht, n)
    assert len(qb) == F - n
    assert np.allclose(np.abs(np.sum(qb[-1] * qb[0], axis=-1)), 1., atol=1e-9)         # last frame == first
    assert np.allclose(tb[-1], tb[0], atol=1e-12)
    # untouched frames are captured frames
    assert np.allclose(qb[:F - 3 * n - 1], q[n:F - 2 * n - 1])
    # velocity across the seam: last step equals the first step (C1 through the loop), and no jumps inside
    step = np.diff(np.r_[tb, tb[1:2]], axis=0)
    assert np.abs(np.diff(step, axis=0)).max() < 4 * np.abs(np.diff(np.diff(ht, axis=0), axis=0)).max() + 1e-9
    assert w[0] == 0 and w[-1] == pytest.approx(1.)


def test_quaternion_from_matrix_round_trip():
    rng = np.random.default_rng(5)
    axes = rng.normal(size=(50, 3))
    ang = rng.uniform(0, math.pi, 50)
    R = P.rodrigues(axes, ang)
    q = P.quat_from_matrix(R * .01)                            # scale removed
    x, y, z, w = q.T
    R2 = np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                   np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                   np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)
    assert np.allclose(R, R2, atol=1e-12)


REPORT = ROOT / 'docs/proposed/seat-pose-fit/seat-pose-fit.report.json'


@pytest.mark.skipif(not REPORT.exists(), reason='no committed seat-pose-fit report')
def test_committed_report_is_trial_only_on_the_actual_cushion():
    r = json.loads(REPORT.read_text())
    assert r['label'] == 'trial' and r['verified'] is False and r['requires_server_reaudit'] is True
    assert r['cushion']['proxy'] is False
    assert r['constants']['seat_band_cm'] == list(seat_contact.SEAT_BAND_CM)
    for clip in r['clips'].values():
        p = ROOT / clip['glb']
        assert p.exists() and p.stat().st_size < 2_000_000
        doc = json.loads(p.read_bytes()[20:20 + int.from_bytes(p.read_bytes()[12:16], 'little')])
        labels = doc['asset']['extras']['sub01_labels']
        assert labels['label'] == 'trial' and labels['verified'] is False and labels['corrections']
