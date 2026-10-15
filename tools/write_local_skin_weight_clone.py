"""Sparse owner skin patch: all bytes outside listed joint/weight slots stay exact."""
import copy
import hashlib
import json
import struct
from pathlib import Path


def patch(doc, binary, changes):
    out=bytearray(binary);allowed=set();touched=[]
    formats={5121:('B',1),5123:('H',2),5126:('f',4)}
    for row in changes:
        attrs=doc['meshes'][row['mesh']]['primitives'][row['primitive']]['attributes']
        for vertex in row['vertices']:
            for field,key in [('JOINTS_0','new_joints'),('WEIGHTS_0','new_weights')]:
                accessor=doc['accessors'][attrs[field]];view=doc['bufferViews'][accessor['bufferView']]
                assert accessor['type']=='VEC4' and view.get('buffer',0)==0 and 'sparse'not in accessor
                fmt,size=formats[accessor['componentType']];values=vertex[key]
                if field=='WEIGHTS_0'and accessor.get('normalized'):
                    maximum={5121:255,5123:65535}[accessor['componentType']]
                    scaled=[x*maximum/sum(values)for x in values];values=[int(x)for x in scaled]
                    order=sorted(range(4),key=lambda i:scaled[i]-values[i],reverse=True)
                    for i in order[:maximum-sum(values)]:values[i]+=1
                elif fmt!='f':values=[int(x)for x in values]
                offset=view.get('byteOffset',0)+accessor.get('byteOffset',0)+vertex['id']*view.get('byteStride',4*size)
                raw=struct.pack('<'+fmt*4,*values);out[offset:offset+len(raw)]=raw;allowed.update(range(offset,offset+len(raw)))
            touched.append(vertex['id'])
    actual={i for i,(a,b)in enumerate(zip(binary,out))if a!=b}
    assert len(out)==len(binary) and actual<=allowed
    return bytes(out),{'changed_bytes':len(actual),'allowed_attribute_bytes':len(allowed),'affected_vertex_entries':len(touched),'all_unlisted_bytes_exact':True}


def run(owner_path, report_path, output_path):
    import sys
    sys.path.insert(0,'/workspace/sub01-home-private/upright-footrest-full-9cd/tools')
    import life_gltf as G
    original=G.Gltf(owner_path);assert original.sha256=='45e917725f02836dee6d051d9b47dd2785208c78b503fa935ddb322fe69adea8'
    import gzip
    raw=Path(report_path).read_bytes();report=json.loads(gzip.decompress(raw)if str(report_path).endswith('.gz')else raw);binary,proof=patch(original.doc,original.buffers[0],report['changes']);path=Path(output_path);assert not path.exists();G.write_glb(path,copy.deepcopy(original.doc),binary)
    proof.update({'schema':'sub01.sparse-owner-weight-clone.v1','original_sha256':original.sha256,'derived_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'document_identical':True,'all_unlisted_hand_lower_body_weight_attribute_bytes_exact':True,'source_ready':False,'native_ready':False})
    path.with_suffix('.proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--owner',required=True);parser.add_argument('--report',required=True);parser.add_argument('--output',required=True);args=parser.parse_args();run(args.owner,args.report,args.output)
