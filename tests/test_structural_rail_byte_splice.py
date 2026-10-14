import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from splice_structural_rail_remainder import splice
from validate_structural_rail_remainder import validate


def glb(path,doc,binary):
    text=json.dumps(doc).encode();text+=b' '*(-len(text)%4);binary+=b'\0'*(-len(binary)%4)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4E4F534A)+text+struct.pack('<II',len(binary),0x004E4942)+binary)


class SourceByteSpliceTests(unittest.TestCase):
    def test_bypasses_changed_export_normals_and_retains_exact_nonrail_attributes(self):
        positions=[(0,0,0),(1,0,0),(0,1,0),(2,0,0),(3,0,0),(2,1,0)]
        p=b''.join(struct.pack('<fff',*v) for v in positions)
        normals=struct.pack('<'+'f'*18,*([0,0,1]*6));uv=struct.pack('<'+'f'*12,*([0,0,1,0,0,1]*2));indices=struct.pack('<IIIIII',0,1,2,3,4,5)
        binary=p+normals+uv+indices
        doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':len(binary)}],
             'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(p)},{'buffer':0,'byteOffset':len(p),'byteLength':len(normals)},{'buffer':0,'byteOffset':len(p)+len(normals),'byteLength':len(uv)},{'buffer':0,'byteOffset':len(p)+len(normals)+len(uv),'byteLength':len(indices)}],
             'accessors':[{'bufferView':0,'componentType':5126,'type':'VEC3','count':6,'min':[0,0,0],'max':[3,1,0]}, {'bufferView':1,'componentType':5126,'type':'VEC3','count':6}, {'bufferView':2,'componentType':5126,'type':'VEC2','count':6}, {'bufferView':3,'componentType':5125,'type':'SCALAR','count':6}],
             'materials':[{}],'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'TEXCOORD_0':2},'indices':3,'material':0}]}],
             'nodes':[{} for _ in range(163)]+[{'mesh':0}],'scenes':[{'nodes':[163]}]}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.glb';generated=root/'generated.glb';sidecar=root/'sidecar.json';output=root/'new.glb';new_sidecar=root/'new.json'
            glb(source,doc,binary);source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
            doc['nodes']=[{'name':'SUB01_PreservedSource_163_0','mesh':0}];doc['scenes']=[{'nodes':[0]}]
            wrong_normals=struct.pack('<'+'f'*18,*([0,1,0]*6));glb(generated,doc,p+wrong_normals+uv+indices)
            sidecar.write_text(json.dumps({'source_audit':{'source_sha256':source_hash,'matched_rails':[{'source_node_index':163,'primitive_index':0,'triangle_indices':[0]}]},'output_sha256':hashlib.sha256(generated.read_bytes()).hexdigest(),'scoped_original_mesh_remainder':[{'source_node_index':163,'primitive_index':0}]}))
            splice(source,generated,sidecar,output,new_sidecar)
            result=validate(source,output,new_sidecar)
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['checks'][0]['triangle_count'],1)
            self.assertEqual(result['checks'][0]['max_absolute_difference'],{'position':0.,'normal':0.,'uv':0.})
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),source_hash)


if __name__=='__main__':unittest.main()
