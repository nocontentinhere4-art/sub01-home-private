"""Independent decoded-GLB geometry comparison across anatomical rig revisions."""
import hashlib,json,struct,sys
from pathlib import Path

def load(path):
 raw=path.read_bytes();assert raw[:4]==b'glTF';doc=binary=None;offset=12
 while offset<len(raw):
  length,kind=struct.unpack_from('<II',raw,offset);data=raw[offset+8:offset+8+length]
  if kind==0x4e4f534a:doc=json.loads(data)
  elif kind==0x004e4942:binary=data
  offset+=8+length
 assert doc is not None and binary is not None
 return raw,doc,binary

def packed_accessor(doc,binary,index):
 a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];assert not a.get('sparse')and not v.get('extensions');width={5126:4,5125:4,5123:2,5121:1}[a['componentType']]*{'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];start=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',width)
 return {'count':a['count'],'type':a['type'],'componentType':a['componentType'],'normalized':a.get('normalized',False)},b''.join(binary[start+i*stride:start+i*stride+width]for i in range(a['count']))

def prove(a_path,b_path,out):
 ar,ad,ab=load(a_path);br,bd,bb=load(b_path);assert len(ad['meshes'])==len(bd['meshes'])==2;rows=[]
 for am,bm in zip(ad['meshes'],bd['meshes']):
  assert am['name']==bm['name']and len(am['primitives'])==len(bm['primitives'])
  for ap,bp in zip(am['primitives'],bm['primitives']):
   names=['POSITION','NORMAL'];assert all(n in ap['attributes']and n in bp['attributes']for n in names);assert ('TEXCOORD_0'in ap['attributes'])==('TEXCOORD_0'in bp['attributes'])
   if 'TEXCOORD_0'in ap['attributes']:names.append('TEXCOORD_0')
   hashes={}
   for name in names+['indices']:
    ai=ap['indices']if name=='indices'else ap['attributes'][name];bi=bp['indices']if name=='indices'else bp['attributes'][name];av,abytes=packed_accessor(ad,ab,ai);bv,bbytes=packed_accessor(bd,bb,bi);assert av==bv and abytes==bbytes,(am['name'],name,'Original surface differs');hashes[name]={'sha256':hashlib.sha256(abytes).hexdigest(),**av}
   rows.append({'mesh':am['name'],'exact_attributes':hashes})
 result={'schema':'sub01.actual-anatomical-rig-surface-preservation.v1','before_sha256':hashlib.sha256(ar).hexdigest(),'after_sha256':hashlib.sha256(br).hexdigest(),'all_position_normal_uv_indices_byte_exact':True,'meshes':rows,'scope':'Rig joints, inverse-bind matrices and fresh weights intentionally changed; this proof only accepts unchanged actual exported mesh geometry/UV, never digit identity or contact','digit_identity_accepted':False,'native_imported':False};out.write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 a,b,out=map(Path,sys.argv[1:]);r=prove(a,b,out);print(json.dumps({'all_original_surface_attributes_exact':r['all_position_normal_uv_indices_byte_exact'],'meshes':len(r['meshes']),'after_sha256':r['after_sha256']}))
