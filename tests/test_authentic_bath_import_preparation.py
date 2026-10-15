"""Legal import identifiers and removal of mathematically empty geometry only."""
import json,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_real_wc_bundle import glb
from prepare_frame_backing_remainder import read,elements
from unreal_import_authentic_bath_fixtures import prepare_import

def test_legal_identity_preparation_preserves_every_physical_corner_and_original_binary(tmp_path):
 positions=struct.pack('<12f',0,0,0,1,0,0,0,1,0,0,0,0);uv=struct.pack('<8f',0,0,1,0,0,1,0,0);indices=struct.pack('<6I',0,1,2,0,0,3);blob=positions+uv+indices
 d={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':'Original | part.001','mesh':0}],'meshes':[{'name':'Cube.031','primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':1},'indices':2,'material':0}]}],'materials':[{'name':'Original PBR','pbrMetallicRoughness':{'baseColorFactor':[.2,.3,.4,1],'roughnessFactor':.6}}],'buffers':[{'byteLength':len(blob)}],'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(positions)},{'buffer':0,'byteOffset':len(positions),'byteLength':len(uv)},{'buffer':0,'byteOffset':len(positions)+len(uv),'byteLength':len(indices)}],'accessors':[{'bufferView':0,'componentType':5126,'count':4,'type':'VEC3'},{'bufferView':1,'componentType':5126,'count':4,'type':'VEC2'},{'bufferView':2,'componentType':5125,'count':6,'type':'SCALAR'}]}
 source=tmp_path/'source.glb';target=tmp_path/'prepared.glb';source.write_bytes(glb(d,blob));before=source.read_bytes();out,binary,proof=prepare_import(source,target,'SUB01_AuthenticDoor_')
 assert source.read_bytes()==before
 assert out['nodes'][0]['name']==out['meshes'][0]['name']=='SUB01_AuthenticDoor_000'
 assert out['materials']==d['materials']
 assert binary[:len(blob)]==blob
 assert proof['exact_zero_area_faces_removed']=={'SUB01_AuthenticDoor_000:0':[1]}
 assert proof['all_positive_triangle_corner_bytes_exact']is True
 p=out['meshes'][0]['primitives'][0];iv,fmt=elements(out,binary,p['indices']);ids=[struct.unpack(fmt,v)[0]for v in iv]
 assert ids==[0,1,2]
 assert p['attributes']==d['meshes'][0]['primitives'][0]['attributes']
 assert proof['names']=={'Original | part.001':'SUB01_AuthenticDoor_000'}
