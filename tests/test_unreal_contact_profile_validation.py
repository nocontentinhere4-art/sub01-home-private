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
    hand = {'selectedVertices': 200, 'overKeyVertices': 100, 'penetrationCm': 0, 'overMinCm': 3.05}
    hands = [dict(hand, side=side) for side in ('left', 'right')]
    row = {
        'invalidInfluences': 0,
        'finger_local_max_error_degrees': 0,
        'bone_length_max_error_cm': 0,
        'hands': hands,
        'corrected': {'invalidInfluences': 0, 'keyTopCm': 3.0, 'hands': copy.deepcopy(hands)},
        'corrected_local_arms': {
            name: {'translation': [0, 0, 0], 'rotation': [0, 0, 0, 1], 'scale': [1, 1, 1]}
            for name in module.ARMS
        },
    }
    rows = [dict(copy.deepcopy(row), time=3 + i / 60) for i in range(301)]
    return {'samples': rows}


def test_complete_measured_contract_is_accepted():
    result = module.validate(profile())
    assert result['samples'] == 301 and result['sample_rate_hz'] == 60
    assert result['max_corrected_key_gap_cm'] == pytest.approx({'left': .05, 'right': .05})


def test_30hz_profile_is_refused_like_the_native_loader():
    # The native loader binds exactly 301 rows; 30 Hz samples missed midpoint penetration.
    data = profile()
    data['samples'] = [dict(copy.deepcopy(data['samples'][0]), time=3 + i / 30) for i in range(151)]
    with pytest.raises(ValueError):
        module.validate(data)


@pytest.mark.parametrize('side', [0, 1])
@pytest.mark.parametrize('gap,ok', [(0, True), (.2, True), (.21, False), (.5, False), (1.1, False)])
def test_fingertips_hovering_over_the_keys_are_refused(side, gap, ok):
    # docs/qa/contact.md: fingertips touch the keycaps 0 to +2 mm through the whole clip.
    data = profile()
    row = data['samples'][200]
    row['corrected']['hands'][side]['overMinCm'] = row['corrected']['keyTopCm'] + gap
    if ok:
        assert module.validate(data)['max_corrected_key_gap_cm'][('left', 'right')[side]] == pytest.approx(max(gap, .05))
    else:
        with pytest.raises(ValueError, match='hover'):
            module.validate(data)


@pytest.mark.parametrize('field', ['keyTopCm', 'overMinCm'])
def test_gap_measurement_must_be_present_and_finite(field):
    for value in (None, float('nan')):
        data = profile()
        corrected = data['samples'][7]['corrected']
        target = corrected if field == 'keyTopCm' else corrected['hands'][0]
        if value is None:
            del target[field]
        else:
            target[field] = value
        with pytest.raises((ValueError, KeyError)):
            module.validate(data)


def test_complete_60hz_profile_uses_correct_sample_times():
    data = profile()
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


LOADER_STUBS = r"""
#include <cmath>
#include <map>
#include <memory>
#include <string>
#include <vector>
@@POLICY@@
#define TEXT(x) x
struct FMath { static bool IsFinite(double V) { return std::isfinite(V); } };
struct FJsonObject;
struct FJsonValue { std::shared_ptr<FJsonObject> O; std::shared_ptr<FJsonObject> AsObject() const { return O; } };
struct FJsonObject {
  std::map<std::string, double> Numbers; std::vector<std::shared_ptr<FJsonValue>> Hands;
  double GetNumberField(const char* K) const { auto I = Numbers.find(K); return I == Numbers.end() ? 0 : I->second; }
  bool TryGetNumberField(const char* K, double& Out) const { auto I = Numbers.find(K); if (I == Numbers.end()) return false; Out = I->second; return true; }
  const std::vector<std::shared_ptr<FJsonValue>>& GetArrayField(const char*) const { return Hands; }
};
std::shared_ptr<FJsonObject> Hand(double Penetration, double Low, bool HasLow = true) {
  auto H = std::make_shared<FJsonObject>(); H->Numbers["penetrationCm"] = Penetration; if (HasLow) H->Numbers["overMinCm"] = Low; return H;
}
bool Row(double Top, std::shared_ptr<FJsonObject> L, std::shared_ptr<FJsonObject> R, bool HasTop = true) {
  auto Corrected = std::make_shared<FJsonObject>(); if (HasTop) Corrected->Numbers["keyTopCm"] = Top;
  for (auto& H : {L, R}) { auto V = std::make_shared<FJsonValue>(); V->O = H; Corrected->Hands.push_back(V); }
  bool Valid = true;
  const double CapSpread = 0;
  const bool PoseReview = false;
@@STATEMENT@@
  return Valid;
}
int main() {
  if (!Row(3, Hand(0, 3.05), Hand(.1, 2.9))) return 1;                 // touching, within 1 mm inside
  if (!Row(3, Hand(0, 3.2), Hand(0, 3.0))) return 2;                   // +2 mm is still contact
  if (Row(3, Hand(0, 3.21), Hand(0, 3.0))) return 3;                   // left hovers
  if (Row(3, Hand(0, 3.0), Hand(0, 4.1))) return 4;                    // right hovers 1.1 cm (the G12 defect)
  if (Row(3, Hand(.11, 2.89), Hand(0, 3.0))) return 5;                 // penetration still refused
  if (Row(3, Hand(0, 3.0, false), Hand(0, 3.0))) return 6;             // no measurement, no acceptance
  if (Row(3, Hand(0, 3.0), Hand(0, 3.0), false)) return 7;
  if (Row(3, Hand(0, NAN), Hand(0, 3.0))) return 8;
  return 0;
}
"""


def test_native_loader_applies_the_same_two_sided_gate_compiled():
    import re, shutil, subprocess, tempfile
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler unavailable')
    from unreal_contact_profile_runtime import LOAD
    from unreal_typing_review_policy import CPP as actual_policy
    statement = 'double KeyTop=0;' + LOAD.split('double KeyTop=0;', 1)[1].split('\n   auto Arms=', 1)[0]
    assert 'Sub01TypingReview::DistalGap(Low-KeyTop,CapSpread,PoseReview)' in statement
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'gate.cpp', Path(tmp) / 'gate'
        cpp.write_text(LOADER_STUBS.replace('@@POLICY@@', actual_policy).replace('@@STATEMENT@@', statement))
        built = subprocess.run([compiler, '-std=c++17', '-Wall', '-Werror', str(cpp), '-o', str(exe)], capture_output=True, text=True)
        assert built.returncode == 0, built.stderr[-2000:]
        assert subprocess.run([str(exe)]).returncode == 0
