"""Exact source-only preservation of non-bath faces in two shared home batches."""
import copy,hashlib,json,struct
from pathlib import Path
from prepare_frame_backing_remainder import read,elements,SOURCE_SHA
from prepare_real_wc_bundle import glb
SCOPE={163:(122,8,1840,1640,1800),167:(126,68,288,0,96)}
def prepare(home,output):
 raw=Path(home).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('Immutable955 home required')
 d,b=read(raw);output=Path(output);output.mkdir(exist_ok=True);rows=[]
 for ni,(mi,material,count,start,end)in SCOPE.items():
  n=d['nodes'][ni]
  if n.get('mesh')!=mi or any(k in n for k in ('matrix','translation','rotation','scale')):raise ValueError('Exact root shared node required')
  ps=d['meshes'][mi]['primitives']
  if len(ps)!=1 or ps[0]['material']!=material:raise ValueError('Exact shared material required')
  p=ps[0];vals,fmt=elements(d,b,p['indices']);ids=[struct.unpack(fmt,v)[0]for v in vals]
  if len(ids)!=count*3:raise ValueError('Exact source face count required '+str(ni))
  keep=[i for i in range(count)if not start<=i<end];corners=[j for i in keep for j in ids[i*3:i*3+3]];vertices=sorted(set(corners));mapping={old:i for i,old in enumerate(vertices)}
  out={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'name':'SUB01_BathPreserved_'+str(ni),'mesh':0}],'meshes':[{'name':'SUB01_BathPreserved_'+str(ni),'primitives':[]}],'materials':[{'name':'REQUIRE_ORIGINAL_Material_'+str(material)}],'bufferViews':[],'accessors':[],'buffers':[]};blob=bytearray()
  def append(raw,meta,target):
   blob.extend(b'\0'*(-len(blob)%4));offset=len(blob);blob.extend(raw);vi=len(out['bufferViews']);out['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(raw),'target':target});a={k:copy.deepcopy(v)for k,v in meta.items()if k not in ('bufferView','byteOffset','sparse')};a['bufferView']=vi;out['accessors'].append(a);return len(out['accessors'])-1
  attrs={}
  for key,ai in p['attributes'].items():
   vv,ff=elements(d,b,ai);meta=copy.deepcopy(d['accessors'][ai]);meta['count']=len(vertices);decoded=[struct.unpack(ff,vv[i])for i in vertices]
   if 'min'in meta:meta['min']=[min(v[k]for v in decoded)for k in range(len(decoded[0]))]
   if 'max'in meta:meta['max']=[max(v[k]for v in decoded)for k in range(len(decoded[0]))]
   attrs[key]=append(b''.join(vv[i]for i in vertices),meta,34962)
  ix=append(struct.pack('<'+'I'*len(corners),*(mapping[i]for i in corners)),{'componentType':5125,'type':'SCALAR','count':len(corners)},34963);out['meshes'][0]['primitives']=[{'attributes':attrs,'indices':ix,'material':0,'mode':4}];out['buffers']=[{'byteLength':len(blob)}];encoded=glb(out,blob);rd,rb=read(encoded);rp=rd['meshes'][0]['primitives'][0];iv,iff=elements(rd,rb,rp['indices']);ii=[struct.unpack(iff,v)[0]for v in iv]
  for key,ai in p['attributes'].items():
   before,_=elements(d,b,ai);after,_=elements(rd,rb,rp['attributes'][key])
   if [before[i]for i in corners]!=[after[i]for i in ii]:raise ValueError('Unrelated retained corner changed')
  (output/('remainder-'+str(ni)+'.glb')).write_bytes(encoded);rows.append({'source_node':ni,'mesh':mi,'material':material,'source_triangles':count,'removed_face_range':[start,end],'retained_triangles':len(keep),'retained_corner_bytes_exact':True,'sha256':hashlib.sha256(encoded).hexdigest()})
 report={'schema':'sub01.authentic-bath-remainders.v1','home_sha256':SOURCE_SHA,'parts':rows,'native_changed':False};(output/'remainder-proof.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--home',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(prepare(a.home,a.output)))
