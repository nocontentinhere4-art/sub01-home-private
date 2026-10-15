import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('grip',Path(__file__).parents[1]/'tools/unreal_import_anatomical_grip_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def valid():
 return {'schema':'sub01.serialized-owner-animation-only-fbx-roundtrip.v1','source_sha256':m.SOURCE,'fbx_sha256':m.SHA,'source_new_owner_family_sha256':m.FAMILY,'samples':152,'fps':30,'all65_joint_pose_samples':9880,'FBX_curve_key_counts':[152],'same_axis_flags_as_validated_final_owner':True,'maximum_world_joint_head_error_m':4.9e-6,'maximum_pose_matrix_component_error':4.4e-6,'maximum_bind_matrix_component_error':2.2e-6,'duration_seconds':151/30}
def test_matching_family_transport_passes_source_contract():assert m.contract(valid())
@pytest.mark.parametrize('key,value',[('source_new_owner_family_sha256','old-owner'),('samples',151),('maximum_bind_matrix_component_error',.995),('maximum_world_joint_head_error_m',float('nan')),('same_axis_flags_as_validated_final_owner',False),('FBX_curve_key_counts',[151,152]),('duration_seconds',151/24)])
def test_wrong_family_missing_bind_or_incomplete_pose_proof_refuses(key,value):
 p=valid();p[key]=value
 with pytest.raises(AssertionError):m.contract(p)
