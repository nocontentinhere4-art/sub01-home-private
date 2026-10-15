from types import SimpleNamespace
import importlib.util
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('grain',Path(__file__).parents[1]/'tools/unreal_candidate_kitchen_grain.py');grain=importlib.util.module_from_spec(spec);spec.loader.exec_module(grain)

def shader(scale):
 return SimpleNamespace(MaterialEditingLibrary=SimpleNamespace(get_material_instance_vector_parameter_value=lambda m,n:SimpleNamespace(r=0,g=0,b=scale,a=scale),get_material_instance_scalar_parameter_value=lambda m,n:0))
def source():return {'pbrMetallicRoughness':{'baseColorTexture':{'index':0,'extensions':{'KHR_texture_transform':{'scale':[3,3]}}}},'normalTexture':{'index':1,'extensions':{'KHR_texture_transform':{'scale':[3,3]}}}}
def test_actual_shader_must_apply_both_colour_and_normal_frequency():
 rows=grain.verify_sampling(shader(3),object(),source());assert len(rows)==2 and all(r['actual_offset_scale']==[0,0,3,3]for r in rows)
def test_unsupported_texture_transform_fails_closed():
 with pytest.raises(RuntimeError,match='UV offset/scale'):grain.verify_sampling(shader(1),object(),source())
def test_wrong_shader_rotation_is_rejected():
 u=shader(3);u.MaterialEditingLibrary.get_material_instance_scalar_parameter_value=lambda m,n:0.25 if n.endswith('_Rotation')else 0
 with pytest.raises(RuntimeError,match='rotation/coordinate'):grain.verify_sampling(u,object(),source())
