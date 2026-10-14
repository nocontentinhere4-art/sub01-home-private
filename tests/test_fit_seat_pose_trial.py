"""Seat pose-fit TRIAL on the actual source capture (tools/export_seat_fit_source.py, tools/fit_seat_pose_trial.py).

Parity and data tests need the repo GLBs (web/room/char_mixamo.glb, web/room/mh_mx/room_mx_typing.glb)
and Node for the vendored meshopt decoder; they skip when either is absent. Kinematics tests are
synthetic and always run.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import export_seat_fit_source as E  # noqa: E402
import fit_seat_pose_trial as F  # noqa: E402
import validate_unreal_contact_profile as contact_profile  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402

QUICK = [0, 60, 120, 180, 220, 230, 240, 300]          # 3, 4, 5, 6, 6.667, 6.833, 7, 8 s


@pytest.fixture(scope='module')
def source(tmp_path_factory):
    if not (E.OWNER.exists() and E.CLIP.exists()):
        pytest.skip('owner / typing GLB not in this checkout')
    if not shutil.which('node'):
        pytest.skip('node unavailable for the vendored meshopt decoder')
    out = tmp_path_factory.mktemp('seatfit')
    path = E.save(E.build(cache=out / 'cache'), out / 'seat-fit-source.npz')
    return E.Source.load(path), path


@pytest.fixture(scope='module')
def trial(source, tmp_path_factory):
    src, _ = source
    tri, meta = F.cushion_proxy(tmp_path_factory.mktemp('chair'))
    return F.Trial(src, tri, F.keycaps_from_glb()), meta


# ---------------------------------------------------------------- actual data
def test_sole_parity_with_root_ue_numbers(source):
    src, _ = source
    parity = E.parity(src)
    assert parity['max_abs_error_cm'] <= 1e-4                     # measured: 5e-6 cm
    assert parity['left']['root_ue_cm'] == [-.161045, 10.39739, 24.26818]
    assert parity['right']['root_ue_cm'] == [-.360148, 7.52677, 14.81967]
    assert parity['left']['vertices'] + parity['right']['vertices'] == 4177   # root's plantar rule on the GLB


def test_horizontal_parity_with_root_buttock_bounds(source):
    src, _ = source
    pos, nrm = src.skin('buttocks')
    p, n = E.to_ue(pos), E.to_ue_dir(nrm)
    facing = p[n[..., 2] <= -.5]
    assert np.allclose(facing.min(axis=0), [185.272, -246.152, 56.511], atol=.002)
    assert facing.max(axis=0)[:2] == pytest.approx([223.788, -218.797], abs=.002)


def test_compact_export_size_bounds(source):
    src, path = source
    assert path.stat().st_size < 8_000_000                          # vs ~70M posed JSON vertices
    assert src.joint_world.shape == (301, 65, 4, 4) and len(src.times) == 301
    counts = src.meta['counts']
    assert counts['left_sole'] + counts['right_sole'] == 4177
    assert all(counts[p] > 0 for p in E.PATCHES)
    assert sum(counts.values()) < 60_000
    with np.load(path) as z:
        assert z['joint_world'].dtype == np.float64 and z['buttocks.pos'].dtype == np.float32


def test_keyboard_reconstruction_matches_root(trial):
    t, _ = trial
    assert t.keys['top_cm'] == pytest.approx(F.ROOT_KEY_TOP_CM, abs=1e-5)
    assert t.keys['keycaps'] == 87


def test_arm_reach_computed_per_frame_before_and_after_lowering(trial):
    t, _ = trial
    _, before = t.fit_arms(t.W0.copy())
    right = before['right']
    assert len(right['requested_cm']) == 301                       # every frame, not one sample
    worst = int(np.argmax(right['requested_cm']))
    assert t.src.times[worst] == pytest.approx(6.833333, abs=1e-5)
    assert right['requested_cm'][worst] == pytest.approx(51.84344, abs=.002)   # root, UE
    assert right['arm_cm'][worst] == pytest.approx(50.85667, abs=.002)
    raise_cm = {'left': 2.7, 'right': 2.9}
    W, _ = t.fit_legs(t.lowered(5.), raise_cm)
    _, after = t.fit_arms(W)
    assert after['right']['requested_cm'][worst] < right['requested_cm'][worst]   # lowering helps reach
    # The fixed 0.08 cm target is used unchanged: the vertical shift is measured to KeyTop + 0.08.
    assert F.KEY_CONTACT_TARGET_CM == .08 and F.KEY_GAP_MAX_CM == contact_profile.KEY_GAP_MAX_CM == .2


def test_lowering_solved_from_data_and_legs_preserve_toe_plant(source, trial):
    src, _ = source
    t0, _ = trial
    t = F.Trial(src.subset(QUICK), t0.cushion_tri - [t0.chair_shift[0], t0.chair_shift[1], 0], t0.keys)
    L, interval, raise_cm = t.solve()
    W, _, _ = t.run(L, raise_cm, arms=False)
    seat = t.seat(W)
    worst = max(np.nanmax(seat[n]['lowest']) for n in F.SEAT_PATCHES)
    assert abs(worst) < 1e-5                                      # touching on the worst frame, by construction
    assert 3. < L < 10.                                           # measured, not a constant
    soles = t.soles(W)
    for side in ('left', 'right'):
        assert np.nanmin(soles[f'{side}_sole']['lowest_any_z']) == pytest.approx(F.SUPPORT_Z_CM, abs=1e-5)
        assert raise_cm[side] > 0
    for chain in F.LEGS.values():
        f = t.sk.j(chain[2])
        assert np.allclose(W[:, f, :3, :3], t.W0[:, f, :3, :3], atol=1e-12)   # captured foot world rotation
    for k, p in enumerate(t.sk.parents):
        if p >= 0:
            a = np.linalg.norm(t.W0[:, k, :3, 3] - t.W0[:, p, :3, 3], axis=1)
            b = np.linalg.norm(W[:, k, :3, 3] - W[:, p, :3, 3], axis=1)
            assert np.abs(a - b).max() * 100 < 1e-8                # bone lengths constant (cm)


# ---------------------------------------------------------------- kinematics (synthetic)
def test_two_bone_ik_never_stretches():
    root = np.zeros((3, 3))
    joint = np.tile([0., -.3, .05], (3, 1))
    end = np.tile([0., -.6, 0.], (3, 1))
    pole = joint + [0, 0, .1]
    effector = np.array([[0., -.45, -.1], [0., -.9, 0.], [.1, -.5, .1]])
    j, e, reach, length, dist = F.two_bone(root, joint, end, effector, pole)
    l1, l2 = np.linalg.norm(joint - root, axis=1), np.linalg.norm(end - joint, axis=1)
    assert np.allclose(np.linalg.norm(j - root, axis=1), l1) and np.allclose(np.linalg.norm(e - j, axis=1), l2)
    assert reach.tolist() == [True, False, True]
    assert np.allclose(e[[0, 2]], effector[[0, 2]])
    assert np.linalg.norm(e[1] - effector[1]) == pytest.approx(dist[1] - length[1])   # short, not stretched
    assert (j - root)[0] @ [0, 0, 1] > 0                                             # bends toward the pole


def test_find_between_is_minimal_rotation():
    u, v = np.array([[1., 0, 0]]), np.array([[0., 1, 0]])
    R = F.find_between(u, v)
    assert np.allclose(R[0] @ u[0], v[0]) and np.allclose(R[0] @ [0, 0, 1], [0, 0, 1])
    assert np.allclose(R[0] @ R[0].T, np.eye(3))


def test_trial_gates_use_the_validator_constants():
    assert F.SEAT_BAND_CM is seat_contact.SEAT_BAND_CM and F.SOLE_BAND_CM is seat_contact.SOLE_BAND_CM
    assert F.MIN_SUPPORT_VERTICES == seat_contact.MIN_SUPPORT_VERTICES == 12
    m = {'over': np.array([20, 20, 5]), 'lowest': np.array([.2, -3., .1]), 'band': np.array([30, 30, 30])}
    passed, fails = F.support_gate(m, F.SEAT_BAND_CM)
    assert passed.tolist() == [True, False, False] and fails['penetration'].tolist() == [False, True, False]


def test_report_if_present_is_trial_only():
    path = ROOT / 'private-audit/native-seat-pose-trial.json'
    if not path.exists():
        pytest.skip('trial report is written on demand, not committed')
    r = json.loads(path.read_text())
    assert r['label'] == 'trial' and r['verified'] is False and r['requires_server_reaudit'] is True
    assert 'NativeSeatVerified' not in path.read_text()
