import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('written_grip_verifier', Path(__file__).resolve().parents[1] / 'tools/verify_written_controller_grip_all_frames.py')
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)


def frame():
    side = {'palm_min_gap_cm': -.209, 'palm_band_vertices': 15, 'palm_support_patch': True,
            'hand_min_signed_cm': -.274, 'hand_vertices_penetrating': 0, 'hand_vertices_inside': 83,
            'thumb_to_target_cm': {'stick': 1.75}, 'index_to_trigger_cm': 2.859}
    return {'left': copy.deepcopy(side), 'right': copy.deepcopy(side), 'grip': True}


GATES = {'palm_band_cm': (-.3, .3), 'min_support_vertices': 12, 'penetration_limit_cm': -.3,
         'thumb_cm': 2., 'index_cm': 3., 'wrist_displacement_cm': 10., 'wrist_rotation_deg': 25.}
WRISTS = {'left': {'displacement_cm': 10., 'rotation_deg': 25.},
          'right': {'displacement_cm': 10., 'rotation_deg': 25.}}


def test_inside_zero_count_discrepancy_is_explicit_unknown_and_not_gate_acceptance():
    actual = frame()
    expected = copy.deepcopy(actual['left'])
    expected['hand_vertices_inside'] = 84
    mismatch = V.compare_metric_rows(actual['left'], expected, 15, 'left')
    assert mismatch == [{'frame': 15, 'side': 'left', 'field': 'hand_vertices_inside',
                         'actual': 83, 'reported': 84, 'delta': -1, 'cause': 'unexplained',
                         'geometric_gate': False, 'quantization_proven': False}]
    assert V.strict_written_frame_gate(actual, WRISTS, GATES)


@pytest.mark.parametrize('key,value', [('hand_vertices_penetrating', 1), ('palm_support_patch', False),
                                     ('palm_band_vertices', 11), ('palm_min_gap_cm', -.31)])
def test_other_report_comparisons_remain_strict(key, value):
    actual = frame()['left']
    expected = copy.deepcopy(actual)
    actual[key] = value
    with pytest.raises(AssertionError):
        V.compare_metric_rows(actual, expected, 15, 'left')


@pytest.mark.parametrize('key,value', [('palm_min_gap_cm', -.300000001), ('palm_min_gap_cm', .300000001),
                                     ('hand_min_signed_cm', -.300000001), ('hand_vertices_penetrating', 1),
                                     ('palm_band_vertices', 11), ('palm_support_patch', False),
                                     ('index_to_trigger_cm', 3.000000001), ('palm_min_gap_cm', float('nan'))])
def test_direct_geometry_cannot_pass_a_weakened_threshold(key, value):
    actual = frame()
    actual['left'][key] = value
    assert not V.strict_written_frame_gate(actual, WRISTS, GATES)


def test_thumb_and_wrist_thresholds_have_no_extra_tolerance():
    actual = frame()
    actual['right']['thumb_to_target_cm'] = {'stick': 2.000000001}
    assert not V.strict_written_frame_gate(actual, WRISTS, GATES)
    for key, limit in [('displacement_cm', 10.), ('rotation_deg', 25.)]:
        wrists = copy.deepcopy(WRISTS)
        wrists['left'][key] = limit+1e-9
        assert not V.strict_written_frame_gate(frame(), wrists, GATES)
