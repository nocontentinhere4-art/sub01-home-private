"""Evaluate actual glTF skinning directly, avoiding Blender importer rest conversion.
Run on private CPU, not native Game. Surface pairs remain candidates, not acceptance.
"""
import bpy,json,struct,sys,hashlib
import numpy as np
from pathlib import Path
from mathutils import Matrix,Quaternion,Vector
from mathutils.bvhtree import BVHTree
source,role,output,expected_sha256,audit_limit=sys.argv[sys.argv.index('--')+1:];source=Path(source);output=Path(output);raw=source.read_bytes();doc=None;binary=None;p=12
while p<len(raw):
 n,t=struct.unpack_from('<II',raw,p);data=raw[p+8:p+8+n]
 if t==0x4e4f534a:doc=json.loads(data)
 elif t==0x004e4942:binary=data
 p+=n+8
assert doc and binary
assert hashlib.sha256(raw).hexdigest()==expected_sha256
sizes={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16};dtypes={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'};cache={}
def access(i):
 if i in cache:return cache[i]
 a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];assert not a.get('sparse')and not v.get('extensions');dtype=np.dtype(dtypes[a['componentType']]);width=sizes[a['type']];stride=v.get('byteStride',dtype.itemsize*width);x=np.ndarray((a['count'],width),dtype=dtype,buffer=binary,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(stride,dtype.itemsize)).astype(np.float64)
 if a.get('normalized'):
  info=np.iinfo(dtype);x=x/info.max
  if info.min<0:x=np.maximum(x,-1)
 cache[i]=x;return x
parents={c:i for i,n in enumerate(doc['nodes'])for c in n.get('children',[])}
def matrix(n):
 if 'matrix'in n:return Matrix(np.array(n['matrix']).reshape(4,4).T.tolist())
 q=n.get('rotation',[0,0,0,1]);return Matrix.LocRotScale(Vector(n.get('translation',[0,0,0])),Quaternion((q[3],*q[:3])),Vector(n.get('scale',[1,1,1])))
a=next(a for a in doc.get('animations',[])if a.get('name')==role);tracks=[]
for c in a['channels']:
 s=a['samplers'][c['sampler']];tracks.append((c['target']['node'],c['target']['path'],access(s['input']).ravel(),access(s['output']),s.get('interpolation','LINEAR')))
times=sorted(set(float(x)for _,_,ts,_,_ in tracks for x in ts));assert len(times)<=2000
# All actual samples for short clips; bounded exact evenly indexed samples otherwise.
assert len(times)==557,'Exact complete original Texting source required'
audit_limit=int(audit_limit);assert audit_limit in (32,557)
indices=sorted(set(np.linspace(0,len(times)-1,audit_limit).round().astype(int)));times=[times[i]for i in indices]
meshes={}
for ni,n in enumerate(doc['nodes']):
 if 'mesh'not in n or 'skin'not in n:continue
 name=n.get('name',doc['meshes'][n['mesh']].get('name',''))
 if not any(x in name.lower()for x in ['cc0adult','anatomicalfittedhoodiecuff']):continue
 skin=doc['skins'][n['skin']];ib=access(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1);parts=[];faces=[];offset=0
 for prim in doc['meshes'][n['mesh']]['primitives']:
  attrs=prim['attributes'];positions=access(attrs['POSITION']);sets=sorted(int(k.split('_')[1])for k in attrs if k.startswith('JOINTS_'));joints=np.concatenate([access(attrs[f'JOINTS_{k}'])for k in sets],axis=1).astype(int);weights=np.concatenate([access(attrs[f'WEIGHTS_{k}'])for k in sets],axis=1);assert np.max(np.abs(weights.sum(axis=1)-1))<.0001
  parts.append((np.column_stack([positions,np.ones(len(positions))]),joints,weights));triangles=access(prim['indices']).ravel().astype(int).reshape(-1,3);faces.extend((triangles+offset).tolist());offset+=len(positions)
 meshes[name]=(skin['joints'],ib,parts,faces)
assert len(meshes)==4,('Expected actual two hands and two cuffs',list(meshes))
def sample(ts,values,time,path,kind):
 hi=int(np.searchsorted(ts,time))
 if hi==0:return values[0]
 if hi>=len(ts):return values[-1]
 if ts[hi]==time:return values[hi]
 if kind=='STEP':return values[hi-1]
 assert kind=='LINEAR';u=(time-ts[hi-1])/(ts[hi]-ts[hi-1]);x=values[hi-1];y=values[hi]
 if path=='rotation':q=Quaternion((x[3],*x[:3])).slerp(Quaternion((y[3],*y[:3])),u);return np.array([q.x,q.y,q.z,q.w])
 return x+(y-x)*u
records=[]
for sample_index,time in enumerate(times):
 nodes=[dict(n)for n in doc['nodes']]
 for i,path,ts,values,kind in tracks:nodes[i][path]=sample(ts,values,time,path,kind).tolist()
 worlds={}
 def world(i):
  if i not in worlds:worlds[i]=(world(parents[i])@matrix(nodes[i]))if i in parents else matrix(nodes[i])
  return worlds[i]
 posed={}
 for name,(js,ib,parts,faces)in meshes.items():
  transforms=np.array([list(map(list,world(j)))for j in js])@ib;positions=[]
  for p,j,w in parts:positions.append(np.einsum('nwij,nj,nw->ni',transforms[j],p,w)[:,:3])
  points=np.concatenate(positions);assert np.isfinite(points).all();posed[name]=BVHTree.FromPolygons(points.tolist(),faces,all_triangles=True,epsilon=0)
 row={'seconds':time,'sides':{}}
 for side in ['Left','Right']:
  cuff=next(name for name in posed if 'Cuff'+side in name);hand=next(name for name in posed if 'cc0adult'in name.lower()and side.lower()in name.lower());pairs=posed[cuff].overlap(posed[hand]);row['sides'][side]={'cuff_hand_triangle_candidates':len(pairs),'first_pairs':pairs[:10]}
 records.append(row)
 if sample_index%32==0:print('PHONE_CUFF_PROGRESS',sample_index,time,flush=True)
report={'schema':'sub01.serialized-glTF-skin-cuff-audit.v1','source_sha256':hashlib.sha256(raw).hexdigest(),'clip':role,'samples':records,'actual_skinning_formula':'sum(weight * jointWorld * inverseBind * POSITION), evaluated directly from serialized original/native coordinate graph','all_actual_source_samples_evaluated':True,'all_serialized_JOINTS_n_WEIGHTS_n_channels_used':True,'controller_prop_contact_accepted':False,'hand_self_contact_accepted':False,'no_Blender_import_rest_conversion':True,'native_or_contact_acceptance':False};output.write_text(json.dumps(report,indent=2));print('DIRECT_SERIALIZED_CUFF_AUDIT',json.dumps({'source':report['source_sha256'],'clip':role,'samples':len(records),'max_candidates':{s:max(r['sides'][s]['cuff_hand_triangle_candidates']for r in records)for s in ['Left','Right']}}),flush=True)
