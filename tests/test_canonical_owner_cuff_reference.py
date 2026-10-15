"""Regression: native glTF normalized integer UV must not become 26000-tile UV."""
import json
import shutil
import struct
import subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]

def test_exact_original_reference_normalizes_uv_and_preserves_metres(tmp_path):
    node=shutil.which('node')
    if not node:
        pytest.skip('Node runtime unavailable')
    chunks=[struct.pack('<9f',.1,.2,.3,.4,.5,.6,.7,.8,.9),struct.pack('<6H',0,65535,32768,16384,65535,0),struct.pack('<3H',0,1,2),struct.pack('<16f',1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)]
    binary=b'';views=[]
    for data in chunks:
        binary+=bytes((-len(binary))%4)
        views.append({'buffer':0,'byteOffset':len(binary),'byteLength':len(data)})
        binary+=data
    binary+=bytes((-len(binary))%4)
    doc={'asset':{'version':'2.0'},'nodes':[{'name':'mixamorig:Hips'}],'buffers':[{'byteLength':len(binary)}],'bufferViews':views,'accessors':[{'bufferView':0,'componentType':5126,'type':'VEC3','count':3},{'bufferView':1,'componentType':5123,'type':'VEC2','count':3,'normalized':True},{'bufferView':2,'componentType':5123,'type':'SCALAR','count':3},{'bufferView':3,'componentType':5126,'type':'MAT4','count':1}],'meshes':[{'name':'tripo_source','primitives':[{'attributes':{'POSITION':0,'TEXCOORD_0':1},'indices':2,'material':0}]}],'skins':[{'joints':[0],'inverseBindMatrices':3}]}
    text=json.dumps(doc).encode();text+=b' '*((-len(text))%4)
    raw=b'glTF'+struct.pack('<II',2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary
    source=tmp_path/'source.glb';source.write_bytes(raw);output=tmp_path/'reference.json'
    subprocess.run([node,str(ROOT/'tools/extract_canonical_owner_cuff_reference.mjs'),str(source),str(output)],check=True,capture_output=True)
    result=json.loads(output.read_text())
    assert result['positions'][0]==pytest.approx([.1,-.3,.2])
    assert result['uvs'][0]==[0,0]
    assert result['uvs'][1]==pytest.approx([32768/65535,1-16384/65535])
    assert result['uvs'][2]==[1,1]
    assert result['faces']==[[0,1,2]]
    assert result['face_origins']==[{'primitive':0,'triangle':0}]
