import importlib.util
from pathlib import Path
from copy import deepcopy
import pytest
p=Path(__file__).parents[1]/'tools/unreal_anatomical_source_materials.py'
spec=importlib.util.spec_from_file_location('anatomical_pbr',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def records():
 source={'doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':[.02,.02,.02,1],'metallicFactor':0,'roughnessFactor':.82},'normalTexture':{'index':0,'extensions':{'KHR_texture_transform':{'offset':[0,-624],'scale':[625,625]}}},'extensions':{'KHR_materials_sheen':{'sheenColorFactor':[.02,.02,.02],'sheenRoughnessFactor':.5}}}
 actual={'actual_two_sided':True,'actual_blend_mode':'<BlendMode.BLEND_OPAQUE: 0>','vectors':{'BaseColorFactor':[.02,.02,.02,1],'NormalTexture_OffsetScale':[0,-624,625,625],'SheenColorFactor':[.02,.02,.02,1]},'scalars':{'MetallicFactor':0,'RoughnessFactor':.82,'NormalScale':1,'SheenRoughnessFactor':.5},'textures':{'NormalTexture':'/Game/Fresh/MetricNormal.MetricNormal'}}
 return source,actual

def test_physical_cuff_metric_frequency_and_sheen_pass():assert m.validate_record(*records(),'/Game/Fresh')
@pytest.mark.parametrize('section,key,value',[('vectors','NormalTexture_OffsetScale',[0,0,1,1]),('vectors','SheenColorFactor',[1,1,1,1]),('scalars','RoughnessFactor',.5),('textures','NormalTexture','/InterchangeAssets/DefaultNormal')])
def test_reject_lost_cloth_frequency_or_default_shader(section,key,value):
 source,actual=records();actual[section][key]=value
 with pytest.raises(AssertionError):m.validate_record(source,actual,'/Game/Fresh')

def test_double_sided_source_must_survive():
 source,actual=records();actual['actual_two_sided']=False
 with pytest.raises(AssertionError):m.validate_record(source,actual,'/Game/Fresh')
