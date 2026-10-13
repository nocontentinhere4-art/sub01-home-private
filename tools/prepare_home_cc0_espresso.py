"""Prepare licensed CC0 porta-espresso geometry without running Blender/rendering.
Preserves authored geometry, UVs, normals and material textures; merges draw groups.
"""
from pathlib import Path
import copy,hashlib,json,struct
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'web/house/assets/cc0-porta-espresso';SRC=OUT/'source.glb'
raw=SRC.read_bytes();assert raw[:4]==b'glTF';jl=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+jl]);binary=raw[28+jl:];groups={}
def read(index):
 a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']];dt={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
 assert not v.get('byteStride'),'Interleaved source needs explicit decoder'
 return np.frombuffer(binary,dt,a['count']*components,v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(a['count'],components).copy()
def matrix(n):
 if 'matrix'in n:return np.array(n['matrix']).reshape(4,4).T
 x,y,z,w=n.get('rotation',[0,0,0,1]);m=np.eye(4);m[:3,:3]=np.array([[1-2*y*y-2*z*z,2*x*y-2*z*w,2*x*z+2*y*w],[2*x*y+2*z*w,1-2*x*x-2*z*z,2*y*z-2*x*w],[2*x*z-2*y*w,2*y*z+2*x*w,1-2*x*x-2*y*y]])@np.diag(n.get('scale',[1,1,1]));m[:3,3]=n.get('translation',[0,0,0]);return m
parts=[]
def walk(i,parent):
 n=doc['nodes'][i];world=parent@matrix(n)
 if 'mesh'in n:
  for p in doc['meshes'][n['mesh']]['primitives']:
   assert p.get('mode',4)==4
   a=p['attributes'];xyz=read(a['POSITION']);xyz=(world@np.c_[xyz,np.ones(len(xyz))].T).T[:,:3];nor=read(a['NORMAL'])@np.linalg.inv(world[:3,:3]);nor/=np.linalg.norm(nor,axis=1)[:,None];uv=read(a['TEXCOORD_0']);idx=read(p['indices']).reshape(-1)
   g=groups.setdefault(p['material'],[]);g.append((xyz,nor,uv,idx));parts.append({'name':n.get('name'),'material':p['material'],'triangles':len(idx)//3,'bounds':[xyz.min(0).tolist(),xyz.max(0).tolist()]})
 for c in n.get('children',[]):walk(c,world)
for i in doc['scenes'][doc.get('scene',0)]['nodes']:walk(i,np.eye(4))
buf=bytearray();views=[];access=[]
def chunk(data,target=None):
 while len(buf)%4:buf.append(0)
 offset=len(buf);buf.extend(data);v={'buffer':0,'byteOffset':offset,'byteLength':len(data)}
 if target:v['target']=target
 views.append(v);return len(views)-1
def attr(a,typ,component=5126,target=34962):
 a=np.ascontiguousarray(a,dtype='<f4'if component==5126 else'<u4');v=chunk(a.tobytes(),target);r={'bufferView':v,'componentType':component,'count':len(a),'type':typ}
 if typ=='VEC3':r['min']=a.min(0).tolist();r['max']=a.max(0).tolist()
 access.append(r);return len(access)-1
nodes=[];meshes=[];allpts=[];triangles=0
for material,members in sorted(groups.items()):
 pos=[];norm=[];uvs=[];indices=[];offset=0
 for xyz,nor,uv,idx in members:pos.append(xyz);norm.append(nor);uvs.append(uv);indices.append(idx+offset);offset+=len(xyz)
 xyz=np.concatenate(pos);allpts.append(xyz);ind=np.concatenate(indices);triangles+=len(ind)//3
 name='CC0_espresso_'+str(material);p={'attributes':{'POSITION':attr(xyz,'VEC3'),'NORMAL':attr(np.concatenate(norm),'VEC3'),'TEXCOORD_0':attr(np.concatenate(uvs),'VEC2')},'indices':attr(ind[:,None],'SCALAR',5125,34963),'material':material,'mode':4};meshes.append({'name':name,'primitives':[p]});nodes.append({'name':name,'mesh':len(meshes)-1})
images=copy.deepcopy(doc.get('images',[]))
for image in images:
 v=doc['bufferViews'][image['bufferView']];image['bufferView']=chunk(binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])
new={'asset':{'version':'2.0','generator':'SUB01 CC0-bed geometry-preserving preparation'},'scene':0,'scenes':[{'nodes':list(range(len(nodes)))}],'nodes':nodes,'meshes':meshes,'accessors':access,'bufferViews':views,'buffers':[{'byteLength':len(buf)}],'materials':doc['materials'],'textures':doc.get('textures',[]),'images':images,'samplers':doc.get('samplers',[])}
for k in ['extensionsUsed','extensionsRequired']: 
 if k in doc:new[k]=doc[k]
j=json.dumps(new,separators=(',',':')).encode();j+=b' '*(-len(j)%4);buf+=b'\0'*(-len(buf)%4);result=struct.pack('<4sII',b'glTF',2,28+len(j)+len(buf))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(buf),0x004e4942)+buf;(OUT/'porta-espresso.glb').write_bytes(result)
xyz=np.concatenate(allpts);meta={'source_sha256':hashlib.sha256(raw).hexdigest(),'prepared_sha256':hashlib.sha256(result).hexdigest(),'source_bytes':len(raw),'prepared_bytes':len(result),'source_meshes':len(parts),'prepared_draw_groups':len(nodes),'triangles':triangles,'bounds':[xyz.min(0).tolist(),xyz.max(0).tolist()],'dimensions_m':(xyz.max(0)-xyz.min(0)).tolist(),'geometry':'authored external CC0 model; not a photogrammetric scan; no new handmade substitute geometry','preparation':'World transforms baked, same-material meshes merged. Source vertex shape, normals, UV and all embedded licensed textures retained. No rendering/no texture upscaling.','runtime_position':[-1.25,.925,-3.5],'runtime_yaw':0,'integration':'Replace old coffee-machine asset at(-1.25,.925,-3.5), preserve licensed source material assignments. Use source actual metric scale and floor alignment. Depth fits .65mcounter without scaling. Orientation needs server reference review. No active collider enlargement; parent handles final scene.','parts':parts};(OUT/'porta-espresso.json').write_text(json.dumps(meta,indent=2));print(json.dumps({k:v for k,v in meta.items()if k!='parts'}))
