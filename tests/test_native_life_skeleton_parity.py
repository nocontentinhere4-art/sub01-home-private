"""UE 66-bone skeleton vs the 65-joint owner skin: structural-root parity, never a raw count."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import native_life_skeleton_parity as parity  # noqa: E402

OWNER = {'mixamorig:Hips': None, 'mixamorig:Spine': 'mixamorig:Hips', 'mixamorig:LeftUpLeg': 'mixamorig:Hips',
         'mixamorig:LeftLeg': 'mixamorig:LeftUpLeg', 'mixamorig:Head': 'mixamorig:Spine'}
STILL = [(t, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0)) for t in (0.0, 3.0, 8.0)]


def ue(structural='Armature'):
    parents = {n: (structural if p is None else p) for n, p in OWNER.items()}
    if structural:
        parents[structural] = None
    names = ([structural] if structural else []) + list(OWNER)
    return names, parents


def test_constant_structural_root_passes_despite_count():
    names, parents = ue()
    result = parity.structural_root_parity(names, parents, OWNER, STILL)
    assert result['pass'] and result['structural_root'] == 'Armature' and result['ue_bone_count'] == len(OWNER) + 1


def test_no_structural_root_passes():
    names, parents = ue(None)
    assert parity.structural_root_parity(names, parents, OWNER)['pass']


@pytest.mark.parametrize('samples,why', [
    ([STILL[0], (3.0, (0.0, 0.2, 0.0), (0, 0, 0, 1), (1, 1, 1)), STILL[2]], 'moves'),
    ([STILL[0], STILL[1], (8.0, (0, 0, 0), (0.0, 0.0, 0.0087, 0.99996), (1, 1, 1))], 'moves'),
    ([STILL[0], STILL[1], (8.0, (0, 0, 0), (0, 0, 0, 1), (1.01, 1, 1))], 'moves'),
    ([STILL[0]], 'needs transform samples'),
])
def test_animated_or_unsampled_root_fails(samples, why):
    names, parents = ue()
    result = parity.structural_root_parity(names, parents, OWNER, samples)
    assert not result['pass'] and any(why in f for f in result['failures'])


def test_parent_mismatch_missing_joint_and_second_extra_bone_fail():
    names, parents = ue()
    parents['mixamorig:Head'] = 'mixamorig:Hips'
    assert any('mixamorig:Head' in f for f in parity.structural_root_parity(names, parents, OWNER, STILL)['failures'])
    names, parents = ue()
    names.remove('mixamorig:LeftLeg')
    parents.pop('mixamorig:LeftLeg')
    assert any('missing owner joints' in f for f in parity.structural_root_parity(names, parents, OWNER, STILL)['failures'])
    names, parents = ue()
    names.append('IK_Foot')
    parents['IK_Foot'] = 'Armature'
    assert any('more than one' in f for f in parity.structural_root_parity(names, parents, OWNER, STILL)['failures'])
    names, parents = ue()
    parents['mixamorig:Hips'] = None                                   # owner root not under the structural node
    assert not parity.structural_root_parity(names, parents, OWNER, STILL)['pass']


def test_sample_times_clamp_to_the_clip():
    assert parity.sample_times(10) == [0, 3, 8]
    assert parity.sample_times(6.2) == [0, 3, 6.2]
    assert parity.sample_times(2) == [0, 2]


def test_real_owner_skin_has_65_joints_and_one_root():
    inv = pytest.importorskip('inventory_native_life_clips')
    try:
        owner = inv.owner_reference()
    except FileNotFoundError:
        pytest.skip('owner GLB not in this checkout')
    parents = {n: owner['parents'][n] for n in owner['skin_joints']}
    assert len(parents) == 65 and [n for n, p in parents.items() if p not in parents] == [n for n, p in parents.items() if p is None or p not in parents]
    names, ue_parents = ['Armature'] + list(parents), {n: (p if p in parents else 'Armature') for n, p in parents.items()}
    ue_parents['Armature'] = None
    owner_parents = {n: (p if p in parents else None) for n, p in parents.items()}
    assert parity.structural_root_parity(names, ue_parents, owner_parents, STILL)['pass']
