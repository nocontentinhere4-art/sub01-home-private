"""Reject wrong-family/partial transport proof before an existing Skeleton is used."""
import importlib.util,json
from pathlib import Path
import pytest
BASE=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('idle',BASE/'tools/unreal_import_anatomical_idle_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def proof():return json.loads((BASE/'docs/proposed/official-ual-relaxed-idle-r9/animation-conversion-proof.json').read_text())
def test_actual_frozen76_frame_official_idle_contract():assert m.contract(proof())
@pytest.mark.parametrize('key,value',[('source_new_owner_family_sha256','old-twisted-idle'),('samples',75),('all65_joint_pose_samples',4875),('maximum_bind_matrix_component_error',.995),('maximum_world_joint_head_error_m',float('nan')),('same_axis_flags_as_validated_final_owner',False),('FBX_curve_key_counts',[75,76])])
def test_no_wrong_rest_partial_or_nonfinite_animation_on_approved_skeleton(key,value):
 p=proof();p[key]=value
 with pytest.raises(AssertionError):m.contract(p)
