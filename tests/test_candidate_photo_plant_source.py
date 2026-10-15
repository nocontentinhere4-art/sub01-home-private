import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_candidate_photo_plants import validate_placed_source,actual_material_property

def sample():
 original={'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':'Leaf','mesh':0}],'meshes':[{'name':'Leaf','primitives':[{'attributes':{'POSITION':0,'NORMAL':1},'material':0}]}],'materials':[{'name':'Real photographed foliage','doubleSided':True,'pbrMetallicRoughness':{'baseColorTexture':{'index':0}}}]}
 placed=copy.deepcopy(original);placed['nodes'][0]['name']='PP2_00';placed['meshes'][0]['name']='PP2_00';placed['materials'][0]['name']='PP2M00';placed['nodes'].append({'name':'PPPlacement2','translation':[-3.05,.0250013,3.5],'children':[0]});placed['scenes'][0]['nodes']=[1]
 return original,placed

def test_only_rigid_placement_and_names_can_change():
 a,b=sample();validate_placed_source(a,b'actual geometry image bytes',b,b'actual geometry image bytes',2,[-305,350,2.50013])

@pytest.mark.parametrize('alter',[
 lambda d:d['materials'][0]['pbrMetallicRoughness'].update(baseColorFactor=[0,0,0,1]),
 lambda d:d['nodes'][0].update(scale=[2,2,2]),
 lambda d:d['nodes'][-1].update(translation=[0,0,0]),
 lambda d:d['meshes'][0]['primitives'][0]['attributes'].pop('NORMAL'),
])
def test_forged_pbr_or_shape_rejected(alter):
 a,b=sample();alter(b)
 with pytest.raises(RuntimeError):validate_placed_source(a,b'geometry',b,b'geometry',2,[-305,350,2.50013])

def test_changed_embedded_photographic_pixels_rejected():
 a,b=sample()
 with pytest.raises(RuntimeError):validate_placed_source(a,b'original',b,b'repainted',2,[-305,350,2.50013])

class Material:
 def __init__(self,path,**fields):self.path=path;self.fields=fields
 def get_path_name(self):return self.path
 def get_editor_property(self,key):
  if key not in self.fields:raise AttributeError(key)
  return self.fields[key]

def test_actual_override_takes_precedence_over_parent():
 root=Material('real parent',blend_mode='OPAQUE')
 overrides=Material('overrides',override_blend_mode=True,blend_mode='MASKED')
 instance=Material('new imported source',base_property_overrides=overrides,parent=root)
 assert actual_material_property(instance,'blend_mode','override_blend_mode')=='MASKED'

def test_actual_unoverridden_material_inherits_real_parent():
 root=Material('real parent',two_sided=True);overrides=Material('overrides',override_two_sided=False)
 instance=Material('new imported source',base_property_overrides=overrides,parent=root)
 assert actual_material_property(instance,'two_sided','override_two_sided')is True
