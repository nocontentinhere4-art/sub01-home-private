import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
spec=importlib.util.spec_from_file_location('plants',Path(__file__).parents[1]/'tools/unreal_import_candidate_photo_plants.py');plants=importlib.util.module_from_spec(spec);spec.loader.exec_module(plants)
class Overrides:
 def __init__(self):self.p={'opacity_mask_clip_value':0.,'override_opacity_mask_clip_value':False}
 def get_editor_property(self,k):return self.p[k]
 def set_editor_property(self,k,v):self.p[k]=v
class MI:
 def __init__(self,path):self.path=path;self.o=Overrides()
 def get_path_name(self):return self.path
 def get_editor_property(self,k):return self.o if k=='base_property_overrides'else None
 def set_editor_property(self,k,v):assert k=='base_property_overrides';self.o=v

def test_fresh_owned_mask_gets_explicit_authored_cutoff():
 m=MI('/Owned/New/Leaf.Leaf');u=SimpleNamespace(MaterialInstanceConstant=MI,MaterialEditingLibrary=SimpleNamespace(update_material_instance=lambda m:None));c=SimpleNamespace(get_material=lambda i:m)
 plants.apply_owned_alpha_cutoff(u,c,{'alphaMode':'MASK','alphaCutoff':.5},'/Owned/New');assert m.o.p=={'opacity_mask_clip_value':.5,'override_opacity_mask_clip_value':True}
def test_shared_material_never_mutated():
 m=MI('/InterchangeAssets/Shared.Shared');u=SimpleNamespace(MaterialInstanceConstant=MI);c=SimpleNamespace(get_material=lambda i:m)
 with pytest.raises(RuntimeError,match='fresh owned'):plants.apply_owned_alpha_cutoff(u,c,{'alphaMode':'MASK'},'/Owned/New')
 assert m.o.p['override_opacity_mask_clip_value']is False
