"""Evaluate actual glTF skinning directly, avoiding Blender importer rest conversion.
Run on private CPU, not native Game. Surface pairs remain candidates, not acceptance.
"""
import bpy,json,struct,sys,hashlib
import numpy as np
from pathlib import Path
from mathutils import Matrix,Quaternion,Vector
from mathutils.bvhtree import BVHTree
source,role,output,expected_sha256=sys.argv[sys.argv.index('--')+1:];source=Path(source);output=Path(output);raw=source.read_bytes();doc=None;binary=None;p=12
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
assert len(times)<=300,'Bounded full auxiliary source audit only'
indices=list(range(len(times)));times=[times[i]for i in indices]
def sample(ts,values,time,path,kind):
 hi=int(np.searchsorted(ts,time))
 if hi==0:return values[0]
 if hi>=len(ts):return values[-1]
 if ts[hi]==time:return values[hi]
 if kind=='STEP':return values[hi-1]
 assert kind=='LINEAR';u=(time-ts[hi-1])/(ts[hi]-ts[hi-1]);x=values[hi-1];y=values[hi]
 if path=='rotation':q=Quaternion((x[3],*x[:3])).slerp(Quaternion((y[3],*y[:3])),u);return np.array([q.x,q.y,q.z,q.w])
 return x+(y-x)*u

# Exact owner shoe region: material feet, not an inferred ankle-only floor.
regions=[]
for ni,n in enumerate(doc['nodes']):
 if 'mesh'not in n or 'skin'not in n:continue
 skin=doc['skins'][n['skin']];ib=access(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
 for primitive in doc['meshes'][n['mesh']]['primitives']:
  if doc['materials'][primitive.get('material',0)].get('name')!='feet':continue
  attrs=primitive['attributes'];p=access(attrs['POSITION']);sets=sorted(int(k.split('_')[1])for k in attrs if k.startswith('JOINTS_'));j=np.concatenate([access(attrs[f'JOINTS_{k}'])for k in sets],axis=1).astype(int);weights=np.concatenate([access(attrs[f'WEIGHTS_{k}'])for k in sets],axis=1)
  names=[doc['nodes'][i].get('name','')for i in skin['joints']]
  for side in ['Left','Right']:
   ids=[k for k,n in enumerate(names)if side+'Foot'in n or side+'Toe'in n];mask=np.isin(j,ids);owned=(weights*mask).sum(axis=1)>.99;assert owned.any();regions.append((side,skin['joints'],ib,np.column_stack([p[owned],np.ones(owned.sum())]),j[owned],weights[owned]))
assert len(regions)>=2,('No exact feet material regions',len(regions))
patch_masks={}
def evaluate(time):
 nodes=[dict(n)for n in doc['nodes']]
 if time is not None:
  for i,path,ts,values,kind in tracks:nodes[i][path]=sample(ts,values,time,path,kind).tolist()
 worlds={}
 def world(i):
  if i not in worlds:worlds[i]=(world(parents[i])@matrix(nodes[i]))if i in parents else matrix(nodes[i])
  return worlds[i]
 groups={}
 for side,js,ib,p,j,w in regions:
  transforms=np.array([list(map(list,world(k)))for k in js])@ib;v=np.einsum('nwij,nj,nw->ni',transforms[j],p,w)[:,:3];groups.setdefault(side,[]).append(v)
 row={}
 for side,parts in groups.items():
  v=np.concatenate(parts);patch_masks.setdefault(side,v[:,1]<v[:,1].min()+.001);patch=v[patch_masks[side]];row[side]={'sole_min_world_y_m':float(v[:,1].min()),'bounds_min_m':v.min(axis=0).tolist(),'bounds_max_m':v.max(axis=0).tolist(),'shoe_vertices':len(v),'fixed_first_pose_sole_patch_centroid_m':patch.mean(axis=0).tolist(),'fixed_first_pose_sole_patch_vertices':len(patch)}
 return row
rest=evaluate(None);patch_masks.clear();records=[{'time_seconds':t,'sides':evaluate(t)}for t in times];report={'schema':'sub01.official-idle-exact-shoe-support.v1','sourceSha256':hashlib.sha256(raw).hexdigest(),'restShoes':rest,'samples':records,'nativeFloorUnknown':True,'physicalSupportAccepted':False,'fixed_sole_patch_horizontal_displacement_range_m':{s:float(np.linalg.norm(np.array([r['sides'][s]['fixed_first_pose_sole_patch_centroid_m']for r in records])[:,[0,2]]-np.array(records[0]['sides'][s]['fixed_first_pose_sole_patch_centroid_m'])[[0,2]],axis=1).max())for s in ['Left','Right']}}
output.write_text(json.dumps(report,indent=2));print(json.dumps({'rest':rest,'stance_minmax_y_m':{s:[min(r['sides'][s]['sole_min_world_y_m']for r in records),max(r['sides'][s]['sole_min_world_y_m']for r in records)]for s in ['Left','Right']}}),flush=True)
