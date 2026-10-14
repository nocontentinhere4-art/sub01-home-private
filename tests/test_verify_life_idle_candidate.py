"""tools/verify_life_idle_candidate.py: measured invariants on synthetic owner-like GLBs (and the real owner)."""
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import life_clip_synth as S  # noqa: E402
import life_gltf as G  # noqa: E402
import verify_life_idle_candidate as V  # noqa: E402


@pytest.fixture()
def owner(tmp_path):
    return S.build(tmp_path / 'owner.glb')


def run(tmp_path, owner, name, clip=None, **kw):
    path = S.build(tmp_path / name, clip, **kw)
    return V.verify(path, owner)


def test_good_idle_passes_every_invariant(tmp_path, owner):
    r = run(tmp_path, owner, 'good.glb', S.idle_clip())
    assert r['pass'] and r['accepted_for_binding'], r['failed']
    inv = r['invariants']
    assert inv['rest_offsets']['max_deviation_cm'] == 0
    assert inv['bone_length_constancy']['max_stretch_cm'] < 1e-4
    assert inv['skeleton']['parity']['structural_root'] == 'mixamo'       # 66 nodes vs 65 joints is fine
    assert inv['soles']['selected_vertices'] == 32                         # sock and upward vertices excluded
    assert inv['timing']['fps'] == pytest.approx(30, abs=1e-3)
    assert inv['loop']['start_end_hips_relative_pose_cm'] < 1e-4


def test_stretched_bone_fails(tmp_path, owner):
    r = run(tmp_path, owner, 'stretch.glb', S.idle_clip(stretch=True))
    assert 'bone_length_constancy' in r['failed'] and not r['accepted_for_binding']
    assert r['invariants']['bone_length_constancy']['per_bone']['LeftForeArm']['max_dev_from_owner_cm'] == pytest.approx(0.5, abs=0.01)


def test_non_looping_clip_fails(tmp_path, owner):
    r = run(tmp_path, owner, 'ramp.glb', S.idle_clip(ramp=True))
    assert 'loop' in r['failed']
    assert r['invariants']['loop']['start_end_hips_relative_pose_cm'] > 5


def test_root_drift_fails(tmp_path, owner):
    r = run(tmp_path, owner, 'drift.glb', S.idle_clip(drift_cm=10.0))
    assert {'root_in_place', 'loop', 'feet_joints', 'soles'} <= set(r['failed'])
    assert r['invariants']['root_in_place']['hips_net_horizontal_cm'] == pytest.approx(10, abs=1e-3)


def test_foot_slide_without_drift_fails_feet_only_on_slide(tmp_path, owner):
    r = run(tmp_path, owner, 'slide.glb', S.idle_clip(slide_cm=3.0))
    assert 'feet_joints' in r['failed'] and 'soles' in r['failed'] and 'loop' not in r['failed']
    assert r['invariants']['soles']['feet']['left']['centroid_horizontal_slide_cm'] == pytest.approx(3, abs=0.01)


def test_missing_joint_fails(tmp_path, owner):
    r = run(tmp_path, owner, 'missing.glb', S.idle_clip(), drop=('LeftHandPinky4',))
    assert 'skeleton' in r['failed']
    assert any('missing owner joints' in f for f in r['invariants']['skeleton']['parity']['failures'])


def test_structural_root_rule(tmp_path, owner):
    # Animated structural root: refused (it would carry motion of its own).
    still = [(0.0, 0.0, 0.0)] * 61
    moving = [(0.0, 0.0, 30.0 * k / 60) for k in range(61)]
    assert run(tmp_path, owner, 'root_still.glb', S.idle_clip(), root_track=still)['pass']
    r = run(tmp_path, owner, 'root_moves.glb', S.idle_clip(), root_track=moving)
    assert 'skeleton' in r['failed'] and any('moves' in f for f in r['invariants']['skeleton']['parity']['failures'])
    # Mismatched parent: refused.
    r = run(tmp_path, owner, 'reparent.glb', S.idle_clip(), reparent={'LeftHand': 'LeftArm'})
    assert 'skeleton' in r['failed'] and any('LeftHand' in f for f in r['invariants']['skeleton']['parity']['failures'])


def test_other_prefix_is_the_same_skeleton(tmp_path, owner):
    r = run(tmp_path, owner, 'prefix.glb', S.idle_clip(), prefix='mixamorig1:')
    assert r['pass'] and r['invariants']['skeleton']['prefixes'] == ['mixamorig1:']


def test_gltf_json_with_bin_reads_the_same(tmp_path, owner):
    glb = S.build(tmp_path / 'g.glb', S.idle_clip())
    g = G.Gltf(glb)
    (tmp_path / 'g.bin').write_bytes(g.buffers[0])
    doc = dict(g.doc)
    doc['buffers'] = [{'byteLength': len(g.buffers[0]), 'uri': 'g.bin'}]
    (tmp_path / 'g.gltf').write_text(json.dumps(doc))
    a, b = V.verify(glb, owner), V.verify(tmp_path / 'g.gltf', owner)
    assert a['invariants']['loop'] == b['invariants']['loop'] and b['pass']


def test_mapping_mode_measures_ratios_and_never_binds(tmp_path, owner):
    path = S.build(tmp_path / 'other.glb', S.idle_clip(), prefix='src_')
    mapping = {n: 'src_' + n for n, _, _ in S.skeleton_spec()}
    r = V.verify(path, owner, mapping=mapping)
    assert r['pass'] and not r['accepted_for_binding']
    ratios = r['invariants']['rest_offsets']['bone_length_ratios']
    assert ratios['LeftForeArm']['owner_over_candidate'] == pytest.approx(1.0)
    del mapping['LeftHandPinky4']
    assert 'skeleton' in V.verify(path, owner, mapping=mapping)['failed']


def test_cli_exit_codes(tmp_path, owner):
    good = S.build(tmp_path / 'good.glb', S.idle_clip())
    bad = S.build(tmp_path / 'bad.glb', S.idle_clip(ramp=True))
    out = tmp_path / 'r.json'
    assert V.main([str(good), '--owner', str(owner), '--out', str(out)]) == 0
    assert json.loads(out.read_text())['pass']
    assert V.main([str(bad), '--owner', str(owner)]) == 1


def test_real_owner_against_itself_has_zero_rest_deviation():
    owner = ROOT / 'web/room/char_mixamo.glb'
    if not owner.is_file():
        pytest.skip('owner GLB not in this checkout')
    r = V.verify(owner, owner, soles=False)
    inv = r['invariants']
    assert inv['skeleton']['pass'] and inv['skeleton']['joint_count'] == 65
    assert inv['skeleton']['parity']['structural_root'] == 'mixamo'
    assert inv['rest_offsets']['pass'] and inv['rest_offsets']['max_deviation_cm'] == 0
    assert all(b['rest_rotation_dev_deg'] == 0 for b in inv['rest_offsets']['per_bone'].values())
    assert not r['pass'] and 'animation' in r['failed']                    # a rest pose is not an idle


def test_real_owner_sole_rule_selects_the_plantar_vertices():
    owner = ROOT / 'web/room/char_mixamo.glb'
    if not owner.is_file() or not shutil.which('node'):
        pytest.skip('owner GLB or node (vendored meshopt decoder) unavailable')
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        sole = V.sole_selection(G.Gltf(V.decoded(owner, Path(tmp))))
    assert sole['count'] == 4177
    assert 0 <= sole['rest_y_bounds_m'][0] and sole['rest_y_bounds_m'][1] == pytest.approx(0.0039926, abs=1e-6)
