"""Prepared cabinet material primitives preserve exact geometry payload and TRS."""
import importlib.util,json,struct,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('zone',ROOT/'tools/unreal_import_reference_living_tv_zone.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def source(path,count=5):
 rawblob=struct.pack('<9f',0,0,0,1,0,0,0,1,0)
 doc={'asset':{'version':'2.0'},'nodes':[{'name':'OriginalCabinet','mesh':0,'translation':[1,2,3],'scale':[2,2,2]}],'scenes':[{'nodes':[0]}],'scene':0,'meshes':[{'primitives':[{'attributes':{'POSITION':0},'material':i}for i in range(count)]}],'materials':[{'name':f'Exact{i}','pbrMetallicRoughness':{'baseColorFactor':[.2,.3,.4,1],'roughnessFactor':.7}}for i in range(count)],'buffers':[{'byteLength':len(rawblob)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(rawblob)}],'accessors':[{'bufferView':0,'componentType':5126,'count':3,'type':'VEC3'}]}
 raw=json.dumps(doc).encode();raw+=b' '*(-len(raw)%4);path.write_bytes(struct.pack('<III',0x46546c67,2,28+len(raw)+len(rawblob))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(rawblob),0x004e4942)+rawblob);return doc,rawblob

def test_source_material_split_keeps_binary_each_primitive_and_world_trs(tmp_path):
 a=tmp_path/'source.glb';original,blob=source(a);target=tmp_path/'prepared.glb';doc,payload=m.prepare(a,target,'LTC',True)
 assert bytes(payload)==blob
 for i,node in enumerate(doc['nodes']):
  assert node['translation']==[1,2,3]and node['scale']==[2,2,2]
  assert doc['meshes'][node['mesh']]['primitives']==[original['meshes'][0]['primitives'][i]]
  assert {k:v for k,v in doc['materials'][i].items()if k!='name'}=={k:v for k,v in original['materials'][i].items()if k!='name'}
 assert len(doc['nodes'])==5
 with pytest.raises(AssertionError):m.prepare(a,target,'LTC',True)

def test_wrong_number_of_real_cabinet_groups_refuses(tmp_path):
 a=tmp_path/'source.glb';source(a,4)
 with pytest.raises(AssertionError):m.prepare(a,tmp_path/'prepared.glb','LTC',True)
