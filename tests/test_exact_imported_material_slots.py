import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_real_bathroom_pendant import source_slot_binding

class Material:
 def get_path_name(self):return '/Game/PrivateFresh/Material.Material'
class Slot:
 def __init__(self,name,material):self.values={'material_slot_name':name,'material_interface':material}
 def get_editor_property(self,name):return self.values[name]
class Mesh:
 def __init__(self,slot):self.slot=slot
 def get_editor_property(self,name):assert name=='static_materials';return[self.slot]
class Component:
 def __init__(self,name):self.material=Material();self.mesh=Mesh(Slot(name,self.material))
 def get_editor_property(self,name):assert name=='static_mesh';return self.mesh
 def get_material(self,index):assert index==0;return self.material

@pytest.mark.parametrize('slot',['Window warm white factory coating','Window_warm_white_factory_coating'])
def test_full_source_or_observed_space_sanitization_only(slot):
 assert source_slot_binding(Component(slot),{'name':'Window warm white factory coating'},'/Game/PrivateFresh')=={'Window warm white factory coating':'/Game/PrivateFresh/Material.Material'}

@pytest.mark.parametrize('slot',['Win_ing','Windowwarmwhitefactorycoating','Window_warm_white_factory_coating_1'])
def test_no_truncated_fuzzy_or_numbered_alias(slot):
 with pytest.raises(RuntimeError):source_slot_binding(Component(slot),{'name':'Window warm white factory coating'},'/Game/PrivateFresh')
