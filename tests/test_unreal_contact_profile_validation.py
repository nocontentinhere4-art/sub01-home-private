"""Reject unsafe or empty contact evidence, independent of private assets."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'contact_profile_validation',
    Path(__file__).resolve().parents[1] / 'tools/validate_unreal_contact_profile.py',
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def profile():
    hand = {'selectedVertices': 200, 'overKeyVertices': 100, 'penetrationCm': 0}
    hands = [dict(hand, side=side) for side in ('left', 'right')]
    row = {
        'invalidInfluences': 0,
        'finger_local_max_error_degrees': 0,
        'bone_length_max_error_cm': 0,
        'hands': hands,
        'corrected': {'invalidInfluences': 0, 'hands': copy.deepcopy(hands)},
        'corrected_local_arms': {
            name: {'translation': [0, 0, 0], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}
            for name in module.ARMS
        },
    }
    rows = [dict(copy.deepcopy(row), time=3 + i / 30) for i in range(151)]
    return {'samples': rows}


def test_complete_measured_contract_is_accepted():
    assert module.validate(profile())['samples'] == 151


def test_complete_60hz_profile_uses_correct_sample_times():
    data = profile()
    template = data['samples'][0]
    data['samples'] = [dict(copy.deepcopy(template), time=3 + i / 60) for i in range(301)]
    assert module.validate(data)['sample_rate_hz'] == 60
    data['samples'][61]['time'] += .01
    with pytest.raises(ValueError):
        module.validate(data)


@pytest.mark.parametrize('field', ['time', 'finger_local_max_error_degrees', 'bone_length_max_error_cm'])
@pytest.mark.parametrize('value', [float('nan'), float('inf')])
def test_nonfinite_measurement_cannot_pass_comparison(field, value):
    data = profile()
    data['samples'][60][field] = value
    with pytest.raises(ValueError):
        module.validate(data)


@pytest.mark.parametrize('change', ['empty_overlap', 'nan_penetration', 'duplicate_side', 'invalid_weights', 'missing_frame'])
def test_incomplete_or_false_contact_evidence_is_rejected(change):
    data = profile()
    corrected = data['samples'][60]['corrected']
    if change == 'empty_overlap':
        corrected['hands'][0]['overKeyVertices'] = 0
    elif change == 'nan_penetration':
        corrected['hands'][1]['penetrationCm'] = float('nan')
    elif change == 'duplicate_side':
        corrected['hands'][1]['side'] = 'left'
    elif change == 'invalid_weights':
        corrected['invalidInfluences'] = 1
    else:
        data['samples'].pop(60)
    with pytest.raises(ValueError):
        module.validate(data)


def test_reference_does_not_certify_rendered_naturalness():
    assert 'POV not certified' in module.validate(profile())['acceptance']
