import hashlib,json,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from tools import unreal_import_reference_media as module

def test_short_unique_material_names_preserve_every_factor_and_source_byte(tmp_path,monkeypatch):
 nodes=[{'name':n,'mesh':i}for i,n in enumerate(module.NAMES)]
 materials=[{'name':'Console '+('white'if i==5 else'black')+' textured polymer','pbrMetallicRoughness':{'baseColorFactor':[.82,.83,.81,1]if i==5 else[.012,.014,.017,1]}}for i in range(11)]
 doc={'asset':{'version':'2.0'},'nodes':nodes,'meshes':[{'name':n['name'],'primitives':[{'attributes':{'NORMAL':0,'TEXCOORD_0':1},'material':i}]}for i,n in enumerate(nodes)],'materials':materials,'buffers':[{'byteLength':4}]}
 text=json.dumps(doc).encode();text+=b' '*(-len(text)%4);binary=b'\0\xff\x80\x7f';source=tmp_path/'media.glb';source.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+4)+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',4,0x004e4942)+binary)
 original=source.read_bytes();monkeypatch.setattr(module,'SHA',hashlib.sha256(original).hexdigest());actual,blob=module.prepare(source,tmp_path/'prepared.glb')
 assert [m['name']for m in actual['materials']]==['RM'+format(i,'02d')for i in range(11)]
 assert actual['materials'][5]['pbrMetallicRoughness']==materials[5]['pbrMetallicRoughness']
 assert actual['materials'][0]['pbrMetallicRoughness']==materials[0]['pbrMetallicRoughness']
 assert bytes(blob)==binary and source.read_bytes()==original
 assert [m['primitives']for m in actual['meshes']]==[m['primitives']for m in doc['meshes']]
