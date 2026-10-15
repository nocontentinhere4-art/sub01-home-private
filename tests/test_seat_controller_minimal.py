"""Minimal seat + controller packet for origin/main: gates stay strict, readiness stays false, install is additive.

Runs both on the Claude branch and in a clean origin/main worktree with only the packet's new files copied in
(docs/proposed/root-packet-seat-controller-minimal-20261015.md).
"""
import copy
import json
import random
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

contract = pytest.importorskip('controller_clip_contract', reason='origin/main tools/controller_clip_contract.py (the packet targets main)')
import controller_play_minimal as cpm  # noqa: E402
import install_seat_controller_adapters as installer  # noqa: E402
import unreal_controller_play_runtime as runtime  # noqa: E402
import unreal_seat_transition_runtime as seat  # noqa: E402
import validate_unreal_seat_contact as seat_contact  # noqa: E402

SEAT_PATCHED = installer.EARLY_BRACE not in seat.CHARACTER_METHODS


# ------------------------------------------------------------------------------------------------ fixtures
def region(name, over=40, band=30, lo=None, p50=None):
    low, high = seat_contact.band(name)
    lo = (low + high) / 2 if lo is None else lo
    p50 = high - .1 if p50 is None else p50
    return {'region': name, 'selectedVertices': over + 10, 'facingVertices': over + 5, 'overSurfaceVertices': over,
            'bandVertices': band, 'minGapCm': lo, 'p10GapCm': lo, 'p50GapCm': p50, 'p90GapCm': p50 + 1, 'maxGapCm': p50 + 2}


def clip_contact(n=152, **override):
    rows = [{'time': i / 38, 'invalidInfluences': 0, 'regions': [region(r, **override.get(r, {})) for r in seat_contact.REGIONS]}
            for i in range(n)]
    return {'clip_duration_s': 4.0, 'samples': rows}


def main_contact():
    rows = [{'time': 3 + i / 60, 'invalidInfluences': 0, 'regions': [region(r) for r in seat_contact.REGIONS]} for i in range(301)]
    return {'samples': rows}


def sofa_text():
    v = [[0, 0, 45], [80, 0, 45], [80, 80, 45], [0, 80, 45]]
    return json.dumps({'errors': [], 'sofa': {'sections': [{'vertices_world_cm': v, 'seat_surface': {'triangle_indices': [[0, 1, 2], [0, 2, 3]]}}]}})


def derived_grip():
    X = [[1, 0, 0, .02], [0, 1, 0, .05], [0, 0, 1, .01], [0, 0, 0, 1]]
    return {'schema': runtime.DERIVED_SCHEMA, 'label': runtime.DERIVED_LABEL, 'source_clip': {'sha256': runtime.GAMING_OWNER_GLB_SHA256},
            'frames': 152, 'frames_passing': 152, 'all_frames_pass': True, 'per_frame': [{'pass': True}] * 152,
            'fixed_offset': {'holds': True, 'controller_in_right_hand_gltf': X}, 'finger_deltas_deg': {'max_abs_deg': 4.},
            'controller': {'oversized': False}, 'output_glb_sha256': 'a' * 64}


PLACEMENT = {'approach_cm': [-60, 40], 'yaw_deg': 0, 'body_offset_cm': [40, 0, -50], 'body_yaw_deg': 0,
             'sofa_footprint_cm': {'min': [0, 0], 'max': [80, 80]}}


# ------------------------------------------------------------------------------------------------ pins / closure
def test_runtime_pins_equal_main_contract():
    for name in cpm.PINS:
        assert getattr(runtime, name) == getattr(contract, name) == getattr(cpm, name)


def test_minimal_path_never_imports_the_branch_grip_fitter():
    code = ('import sys;sys.path.insert(0,sys.argv[1]);import controller_play_minimal, install_seat_controller_adapters;'
            'print(sorted(m for m in sys.modules if m in ("fit_controller_grip","export_seat_fit_source","life_gltf",'
            '"install_native_adapters_bundle","unreal_controller_grip_contact_native")))')
    import subprocess
    out = subprocess.run([sys.executable, '-c', code, str(ROOT / 'tools')], capture_output=True, text=True, check=True).stdout.strip()
    assert out == '[]'


def test_support_constant_reuses_main_patch_minimum():
    assert cpm.SUPPORT_MIN_VERTICES == seat_contact.MIN_PATCH_VERTICES == 12


# ------------------------------------------------------------------------------------------------ sofa contact gate
def test_whole_clip_contact_passes_only_main_rule_and_support_patch():
    assert cpm.validate_sofa_contact(clip_contact())['passed'] is True


@pytest.mark.parametrize('name,override,why', [
    ('left_sole', {'p50': 7.5}, 'gap, median'),                 # raised heel: main's median rule is not relaxed
    ('right_sole', {'over': 40, 'band': 19}, 'gap, median'),   # coverage 47% < 50%
    ('buttocks', {'over': 20, 'band': 11}, 'support patch'),    # coverage 55% but < 12 vertices in band
    ('buttocks', {'lo': -2.6}, 'penetration'),
    ('left_sole', {'lo': -.01}, 'penetration'),
    ('right_posterior_thigh', {'over': 11, 'band': 11}, 'over the surface'),
])
def test_contact_refusals(name, override, why):
    with pytest.raises(ValueError, match=why):
        cpm.validate_sofa_contact(clip_contact(**{name: override}))


def test_contact_requires_main_metric_set_and_whole_clip():
    data = clip_contact()
    del data['samples'][5]['regions'][0]['p50GapCm']
    with pytest.raises(ValueError, match='SofaContactIncomplete'):
        cpm.validate_sofa_contact(data)
    with pytest.raises(ValueError, match='30 Hz'):
        cpm.validate_sofa_contact(clip_contact(n=100))
    data = clip_contact()
    data['samples'][3]['time'] = data['samples'][2]['time']
    with pytest.raises(ValueError, match='increasing'):
        cpm.validate_sofa_contact(data)


def test_per_patch_rule_never_accepts_what_main_validator_refuses():
    """Randomized: whenever main's validate() refuses a 301-sample report, the controller gate refuses it too."""
    rng = random.Random(7)
    base = main_contact()
    for _ in range(300):
        data = copy.deepcopy(base)
        r = data['samples'][rng.randrange(301)]['regions'][rng.randrange(5)]
        r['overSurfaceVertices'] = rng.randrange(8, 40)
        r['bandVertices'] = rng.randrange(0, r['overSurfaceVertices'] + 1)
        r['minGapCm'] = rng.uniform(-3.5, 1.5)
        r['p50GapCm'] = r['minGapCm'] + rng.uniform(0, 3)
        try:
            seat_contact.validate(data)
            main_ok = True
        except ValueError:
            main_ok = False
        ours = dict(data, clip_duration_s=5.0)
        ours['samples'] = [dict(s, time=s['time'] - 3) for s in data['samples']]
        try:
            cpm.validate_sofa_contact(ours)
            ok = True
        except ValueError:
            ok = False
        assert not (ok and not main_ok)


# ------------------------------------------------------------------------------------------------ evidence / config
def test_evidence_from_derived_clip_only():
    ev = cpm.build_evidence(sofa_text(), derived_grip(), clip_contact(), PLACEMENT)
    assert ev['accepted'] is True and ev['verified'] is False and ev['schema'] == runtime.EVIDENCE_SCHEMA
    raw = {'schema': 'sub01.controller-grip-trial.v1', 'mode': 'penetration_aware_joint_search'}
    with pytest.raises(ValueError, match='derived'):
        cpm.build_evidence(sofa_text(), raw, clip_contact(), PLACEMENT)
    with pytest.raises(ValueError, match='CapsuleInsideSofa'):
        cpm.build_evidence(sofa_text(), derived_grip(), clip_contact(), dict(PLACEMENT, approach_cm=[40, 40]))


def test_no_gaming_posture_and_not_ready_without_proofs(tmp_path):
    (tmp_path / 'private-audit').mkdir()
    text, refusals = cpm.config_fragment(tmp_path, {'clips': []})
    assert text == '' and set(refusals) == {'evidence', 'clip'}
    s = cpm.status(tmp_path)
    assert s['ready_python_mirror'] is False and s['evidence'] is False and s['runtime_proof'] is False
    # accepted evidence alone is still not ready: no native runtime proof, no controller asset receipt
    (tmp_path / 'private-audit' / runtime.SOFA_REPORT).write_text(sofa_text())
    (tmp_path / 'private-audit' / runtime.EVIDENCE).write_text(json.dumps(cpm.build_evidence(sofa_text(), derived_grip(), clip_contact(), PLACEMENT)))
    s = cpm.status(tmp_path)
    assert s['evidence'] is True and s['runtime_proof'] is False and s['ready_python_mirror'] is False


# ------------------------------------------------------------------------------------------------ installer
def staged(tmp_path):
    from stage_unreal_home_runtime import stage
    project = tmp_path / 'project'
    (project / 'Config').mkdir(parents=True)
    (project / 'Sub01HomeLab.uproject').write_text('{}')
    stage(project)
    return project, project / 'Source/Sub01HomeLab'


def test_installer_refuses_main_seat_adapter_with_the_early_brace(tmp_path, monkeypatch):
    _, module = staged(tmp_path)
    before = {p.name: p.read_bytes() for p in module.iterdir()}
    monkeypatch.setattr(seat, 'CHARACTER_METHODS', 'x' + installer.EARLY_BRACE)
    with pytest.raises(installer.Refused, match='early'):
        installer.install(module)
    assert {p.name: p.read_bytes() for p in module.iterdir()} == before


@pytest.mark.skipif(not SEAT_PATCHED, reason='seat adapter still has the early brace; apply the packet patch')
def test_installer_is_additive_keeps_readiness_false_and_refuses_twice(tmp_path):
    project, module = staged(tmp_path)
    fresh = {k: (module / n).read_text() for k, n in installer.FILES.items()}
    config_before = {p.name: p.read_bytes() for p in (project / 'Config').iterdir()}
    report = installer.install(module)
    assert report['ok'] is True and report['installed'] == ['seat', 'controller']
    assert report['readiness']['validated_gaming_posture_in_config'] == []
    assert {p.name: p.read_bytes() for p in (project / 'Config').iterdir()} == config_before
    after = {k: (module / n).read_text() for k, n in installer.FILES.items()}
    for k in fresh:  # every staged line survives in order (additions/same-line extensions only)
        it = iter(after[k].split('\n'))
        assert all(any(line == old or line.startswith(old) for line in it) for old in fresh[k].split('\n') if old)
    assert 'NativeSeatVerified=false' in after['header'] and 'ControllerPlayRuntimeProof=false' in after['header']
    assert 'ValidatedHandsPostures.Add' not in after['cpp'] and '+ValidatedHandsPostures' not in after['cpp']
    assert (module / 'Sub01SeatTransition.h').is_file()
    with pytest.raises(installer.Refused, match='already installed'):
        installer.install(module)


@pytest.mark.skipif(not SEAT_PATCHED or not shutil.which('g++'), reason='needs the patched seat adapter and g++')
def test_compile_closure_only_seat_controller(tmp_path):
    import check_native_adapters_compile_closure as closure
    report = closure.check(tmp_path, None, ('seat', 'controller'))
    assert report['installed'] == ['seat', 'controller']
    assert report['ok'], report['failures']
    assert all(a['count'] == 1 for a in report['anchors'])
