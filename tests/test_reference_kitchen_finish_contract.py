import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reference_kitchen_finish_contract import validate_material_only_variant,WOOD,HARDWARE

def packet():
 old={'meshes':[{'primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':1},'indices':2}]}for _ in range(152)],'nodes':[{'mesh':0,'translation':[1,2,3]}], 'materials':[{}, {}, {}],'images':[{'bufferView':3}]}
 new=copy.deepcopy(old);new['materials']=[{'pbrMetallicRoughness':dict(WOOD),'normalTexture':{'scale':.34}},{'pbrMetallicRoughness':dict(HARDWARE)},{'pbrMetallicRoughness':dict(HARDWARE)}]
 return old,new

def test_finish_preserves_every_nonmaterial_value():
 old,new=packet();assert validate_material_only_variant(old,b'actual_geometry',new,b'actual_geometry')['material_only']

@pytest.mark.parametrize('which',['position','hinge','uv','image','binary'])
def test_geometry_or_hinge_or_texture_payload_changes_refuse(which):
 old,new=packet();blob=b'actual_geometry'
 if which=='position':new['meshes'][0]['primitives'][0]['attributes']['POSITION']=4
 if which=='hinge':new['nodes'][0]['translation'][0]=1.000000001
 if which=='uv':new['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_0']=5
 if which=='image':new['images'][0]['bufferView']=9
 if which=='binary':blob=b'changed_geometry'
 with pytest.raises(ValueError):validate_material_only_variant(old,b'actual_geometry',new,blob)

def test_unreviewed_emissive_wood_refuses():
 old,new=packet();new['materials'][0]['emissiveFactor']=[.001,0,0]
 with pytest.raises(ValueError):validate_material_only_variant(old,b'a',new,b'a')
