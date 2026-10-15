"""Ergonomic layout refit (tools/ergonomic_layout_refit.py): synthetic, always-run tests of the frames, the layout
record, the device-segment weights, the swivel smoothing and the readiness rule. No GLB or Context is loaded."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ergonomic_layout_refit as R  # noqa: E402


def test_ue_gltf_round_trip():
    rng = np.random.default_rng(0)
    p = rng.normal(size=(50, 3))
    back = R.ue_to_gltf_points(R.E.to_ue(p))
    assert np.allclose(back, p, atol=1e-12)


def test_layout_original_is_identity_and_reversible():
    lay = R.Layout()
    assert np.allclose(lay.roll[:2], R.CHAIR_ROLL_ORIGINAL_CM)
    # the original typing roll is 11.221 cm less pull-in than the solver frame
    assert np.allclose(lay.shift, [0., 11.221, 0.], atol=1e-9)
    d = lay.describe()
    assert d['keyboard']['proposed_three_m'] == list(R.KEYBOARD_THREE_M)
    assert d['mouse']['proposed_three_m'] == list(R.MOUSE_THREE_M)


def test_layout_deltas_map_to_home_js():
    lay = R.Layout(kb=(0., 15.), mouse=(-8., 11.), chair_dy=-5.)
    d = lay.describe()
    # +UE Y (toward the body) is +three.js z
    assert d['keyboard']['proposed_three_m'] == pytest.approx([2.0, 0.846, -2.79])
    assert d['mouse']['proposed_three_m'] == pytest.approx([2.32, 0.846, -2.80])
    assert lay.roll[1] == pytest.approx(R.CHAIR_ROLL_ORIGINAL_CM[1] - 5.)
    assert lay.shift[1] == pytest.approx(11.221 - 5.)
    assert np.allclose(R.three_to_ue(R.KEYBOARD_THREE_M), [200., -294., 84.6])


def test_segment_weights_quintic_and_ends():
    K, M, Tr = R.MODE_KEY, R.MODE_MOUSE, R.MODE_TRANSIT
    mode = np.array([K] * 5 + [Tr] * 9 + [M] * 5 + [Tr] * 3)
    w = R.segment_weights(mode, 1 / 60)
    assert np.all(w[:5] == 0) and np.all(w[14:19] == 1)
    ramp = w[5:14]
    assert np.all(np.diff(ramp) > 0) and 0 < ramp[0] < .05 and .95 < ramp[-1] < 1
    assert np.all(w[19:] == 1)          # a transit run at the clip end takes the neighbour's device


def test_gaussian_periodic_preserves_constant_and_wraps():
    x = np.full(40, 7.)
    assert np.allclose(R.gaussian(x, 3.), 7.)
    y = np.zeros(40)
    y[0] = 1.
    s = R.gaussian(y, 2., periodic=True)
    assert s[-1] > 0 and s[1] == pytest.approx(s[-1])
    assert s.sum() == pytest.approx(1.)


def test_ready_rule_never_native():
    gates = {'a': True, 'b': True}
    r = R.readiness(gates)
    assert r == {'source_ready': True, 'native_ready': False, 'ready': False}
    assert R.readiness({'a': True, 'b': False})['source_ready'] is False


def test_ergo_flags_use_unchanged_targets():
    m = {'elbow_above_top_cm': np.array([-1., 0., 10., 10.5]), 'upper_arm_deg': np.array([20., 20.1, 0., 0.]),
         'wrist_flexion_deg': np.array([15., -15., 15.1, 0.]), 'wrist_deviation_deg': np.zeros(4)}
    e, u, w, d = R.ergo_flags(m)
    assert e.tolist() == [False, True, True, False]
    assert u.tolist() == [True, False, True, True]
    assert w.tolist() == [True, True, False, True]
    assert R.ERGO_ELBOW_ABOVE_DESK_CM == (0., 10.) and R.ERGO_UPPER_ARM_MAX_DEG == 20.
