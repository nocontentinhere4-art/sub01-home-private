"""Exercise the actual launch argument validator before any server process starts."""
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from run_unreal_native_window_recording import phone_review_arguments


def test_unmounted_original_phone_review_has_no_live_or_seat_claim():
    args = phone_review_arguments(4)
    assert '-Sub01PhoneGripDiagnostic' in args
    assert '-Sub01HandsDiagnostic=Phone' in args
    assert '-Sub01PhonePoseTime=4' in args
    assert not any('LiveHome' in x or 'DiagnosticSeat' in x or 'Mount' in x for x in args)


def test_measured_rigid_candidate_stays_one_argument_per_field():
    offset = 'X=-0.368 Y=5.488 Z=0.998'
    euler = 'P=0 Y=-3.78 R=0'
    args = phone_review_arguments(4, offset, euler)
    assert args[-2:] == ['-Sub01PhoneMountCm=' + offset, '-Sub01PhoneMountEuler=' + euler]


@pytest.mark.parametrize('time', [math.nan, math.inf, -1, 61])
def test_bad_time_refuses_before_launch(time):
    with pytest.raises(ValueError):
        phone_review_arguments(time)


@pytest.mark.parametrize('offset,euler', [
    ('X=1 Y=2 Z=3', None),
    ('X=31 Y=0 Z=0', 'P=0 Y=0 R=0'),
    ('X=0 Y=0 Z=0', 'P=0 Y=181 R=0'),
    ('X=nan Y=0 Z=0', 'P=0 Y=0 R=0'),
    ('X=0 Y=0 Z=0 -ExecCmds=quit', 'P=0 Y=0 R=0'),
])
def test_unbounded_or_extra_fields_refuse(offset, euler):
    with pytest.raises(ValueError):
        phone_review_arguments(4, offset, euler)
