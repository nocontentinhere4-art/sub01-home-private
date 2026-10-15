import hashlib,json,struct
from pathlib import Path
from tools import unreal_import_reference_bedding as module


def test_names_only_preparation_preserves_document_and_all_binary(tmp_path,monkeypatch):
 import sys
 monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'tools'))
 from home_asset_audit import read_gltf
 doc={'asset':{'version':'2.0'},'scenes':[{'nodes':[0,1,2,3]}],'scene':0,'nodes':[{'name':n,'mesh':i,'translation':[i,.3,0]}for i,n in enumerate(module.NAMES)],'meshes':[{'name':'Original '+str(i),'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'indices':3}]}for i in range(4)],'buffers':[{'byteLength':8}]}
 text=json.dumps(doc).encode();text+=b' '*(-len(text)%4);binary=b'\x00\x80\xff\x7fdata';source=tmp_path/'source.glb';source.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary)
 monkeypatch.setattr(module,'SHA',hashlib.sha256(source.read_bytes()).hexdigest());target=tmp_path/'prepared.glb';actual,blob=module.prepare(source,target)
 assert bytes(blob)==binary
 assert [n['translation']for n in actual['nodes']]==[n['translation']for n in doc['nodes']]
 assert {n['name']for n in actual['nodes']}==set(module.NAMES.values())
 assert [m['primitives']for m in actual['meshes']]==[m['primitives']for m in doc['meshes']]
