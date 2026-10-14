"""Extract exactly the authenticated union remainder; never duplicate existing rails."""
import argparse,copy,hashlib,json,struct
from pathlib import Path
def run(source,report,output,sidecar):
 raw=Path(source).read_bytes();d=json.loads(Path(report).read_text())
 if hashlib.sha256(raw).hexdigest()!=d['output_sha256']:raise ValueError('Union source bytes differ')
 length,kind=struct.unpack_from('<II',raw,12);assert kind==0x4E4F534A
 doc=json.loads(raw[20:20+length]);pos=20+length;blen,bkind=struct.unpack_from('<II',raw,pos);assert bkind==0x004E4942;blob=raw[pos+8:pos+8+blen]
 hits=[n for n in doc['nodes'] if 'SUB01_PreservedSource_163_0' in n.get('name','') and 'mesh' in n]
 if len(hits)!=1:raise ValueError('Exact preserved mesh missing/ambiguous')
 node=copy.deepcopy(hits[0]);mesh=doc['meshes'][node['mesh']];node['mesh']=0;node.pop('children',None)
 doc['nodes']=[node];doc['meshes']=[mesh];doc['scenes']=[{'nodes':[0]}];doc['scene']=0
 for field in ('animations','skins','cameras'):doc.pop(field,None)
 j=json.dumps(doc,separators=(',',':')).encode();j+=b' '*((-len(j))%4);blob+=b'\0'*((-len(blob))%4)
 out=struct.pack('<III',0x46546C67,2,12+8+len(j)+8+len(blob))+struct.pack('<II',len(j),0x4E4F534A)+j+struct.pack('<II',len(blob),0x004E4942)+blob
 Path(output).write_bytes(out);d['output_sha256']=hashlib.sha256(out).hexdigest();d['single_union_remainder_only']=True;d['new_rails_imported']=False;Path(sidecar).write_text(json.dumps(d,indent=2)+'\n');return d['output_sha256']
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--report',required=True);p.add_argument('--output',required=True);p.add_argument('--sidecar',required=True);a=p.parse_args();print('SINGLE_UNION_REMAINDER',run(a.source,a.report,a.output,a.sidecar))
