"""Barycentric measured skin/sleeve weight-field transfer; no geometry/pose edits."""
import json,struct,hashlib,sys
from pathlib import Path
import numpy as np
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
R=Path('/workspace/sub01-home-private/human-base-hands-r1');out=R/'canonical-hand-cuffs-r1/weight-transfer-r6';out.mkdir(exist_ok=False)
def read(path):
 raw=Path(path).read_bytes();d=b=None;p=12
 while p<len(raw):
  n,t=struct.unpack_from('<II',raw,p)
  if t==0x4e4f534a:d=json.loads(raw[p+8:p+8+n])
  if t==0x004e4942:b=raw[p+8:p+8+n]
  p+=n+8
 return {'doc':d,'bin':b,'raw':raw}
def access(f,i):
 a=f['doc']['accessors'][i];v=f['doc']['bufferViews'][a['bufferView']];dtype=np.dtype({5121:'u1',5123:'<u2',5125:'<u4',5126:'<f4',5122:'<i2'}[a['componentType']]);width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];x=np.ndarray((a['count'],width),dtype=dtype,buffer=f['bin'],offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dtype.itemsize*width),dtype.itemsize)).astype(float)
 if a.get('normalized'):x=x/np.iinfo(dtype).max
 return x
def surface(f,mesh,filter_faces=None):
 skin=f['doc']['skins'][0];names=[f['doc']['nodes'][i]['name']for i in skin['joints']];points=[];weights=[];triangles=[]
 for prim in mesh['primitives']:
  attrs=prim['attributes'];p=access(f,attrs['POSITION']);sets=sorted(int(k.split('_')[1])for k in attrs if k.startswith('JOINTS_'));js=np.concatenate([access(f,attrs[f'JOINTS_{k}'])for k in sets],axis=1).astype(int);ws=np.concatenate([access(f,attrs[f'WEIGHTS_{k}'])for k in sets],axis=1);offset=len(points);points.extend(p.tolist())
  for j,w in zip(js,ws):
   row={}
   for i,v in zip(j,w):
    if v>0:row[names[i]]=row.get(names[i],0)+v
   total=sum(row.values());assert abs(total-1)<.01;weights.append({k:v/total for k,v in row.items()})
  for tri in access(f,prim['indices']).astype(int).reshape(-1,3):
   face=tuple(int(i+offset)for i in tri)
   if filter_faces is None or filter_faces([Vector(points[i])for i in face]):triangles.append(face)
 return points,weights,triangles
base=read(R/'canonical-hand-cuffs-r1/portable-materials-r4/canonical-anatomical-hand-cuffs-portable.glb');original=read('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/owner-with-clips-unreal.glb');d=base['doc'];skin=d['skins'][0];names=[d['nodes'][i]['name']for i in skin['joints']];name_index={n:i for i,n in enumerate(names)};oskin=original['doc']['skins'][0];ibms=access(original,oskin['inverseBindMatrices']);bind={original['doc']['nodes'][node]['name']:Matrix(ibms[j].reshape(4,4).T.tolist()).inverted()for j,node in enumerate(oskin['joints'])}
def lookup(surface,point):
 points,weights,triangles,tree=surface;hit,_,index,distance=tree.find_nearest(point);assert hit is not None
 ids=triangles[index];a,b,c=[np.array(points[i],dtype=np.float64)for i in ids];v0=b-a;v1=c-a;v2=np.array(hit)-a;cross=np.cross(v0,v1);den=np.dot(cross,cross);assert den>0,('Exactly zero source triangle selected',index,ids);v=float(np.dot(np.cross(v2,v1),cross)/den);w=float(np.dot(np.cross(v0,v2),cross)/den);bs=[max(0,1-v-w),max(0,v),max(0,w)];s=sum(bs);row={}
 for i,t in zip(ids,bs):
  for k,value in weights[i].items():row[k]=row.get(k,0)+value*t/s
 return row,distance
parts=[base['bin']];offset=len(base['bin']);receipts=[]
def append(array,typ,component):
 global offset
 array=np.array(array,dtype='<f4'if component==5126 else'<u2');b=array.tobytes();vi=len(d['bufferViews']);d['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(b)});parts.extend([b,bytes((-len(b))%4)]);offset+=len(b)+(-len(b))%4;ai=len(d['accessors']);d['accessors'].append({'bufferView':vi,'componentType':component,'type':typ,'count':len(array)});return ai
for side in ['Left','Right']:
 wrist=bind['mixamorig:'+side+'Hand'].translation;axis=(wrist-bind['mixamorig:'+side+'ForeArm'].translation).normalized()
 hand_mesh=next(m for m in d['meshes']if'CC0Adult'+side in m['name']);hp,hw,ht=surface(base,hand_mesh);hands=(hp,hw,ht,BVHTree.FromPolygons(hp,ht,all_triangles=True,epsilon=0))
 def proximal(face):
  center=sum(face,Vector())/3;delta=center-wrist;depth=delta.dot(axis);radial=(delta-axis*depth).length;return -.13<depth<-.054 and radial<.13
 body_mesh=next(m for m in original['doc']['meshes']if m['name'].startswith('tripo'));bp,bw,bt=surface(original,body_mesh,proximal);assert len(bt)>10;sleeve=(bp,bw,bt,BVHTree.FromPolygons(bp,bt,all_triangles=True,epsilon=0))
 mesh=next(m for m in d['meshes']if 'Cuff'+side in m['name']);records=[]
 for prim in mesh['primitives']:
  positions=access(base,prim['attributes']['POSITION']);jout=[];wout=[]
  for point in positions:
   point=Vector(point);depth=(point-wrist).dot(axis);hand,hd=lookup(hands,point);body,bd=lookup(sleeve,point);t=max(0,min(1,(depth+.052)/.022));row={k:hand.get(k,0)*t+body.get(k,0)*(1-t)for k in set(hand)|set(body)};row={k:v for k,v in row.items()if v>1e-8};assert set(row)<=set(names),('Original sleeve requires missing source helper bone',set(row)-set(names));ordered=sorted(row.items(),key=lambda x:-x[1]);assert len(ordered)<=8,('More than8 actual field influences',len(ordered));total=sum(v for _,v in ordered);jout.append([name_index[k]for k,_ in ordered]+[0]*(8-len(ordered)));wout.append([v/total for _,v in ordered]+[0.]*(8-len(ordered)));records.append({'depth_m':depth,'skin_distance_m':hd,'sleeve_distance_m':bd,'skin_blend':t,'weights':dict(ordered)})
  for k in [0,1]:prim['attributes'][f'JOINTS_{k}']=append(np.array(jout)[:,k*4:(k+1)*4],'VEC4',5123);prim['attributes'][f'WEIGHTS_{k}']=append(np.array(wout)[:,k*4:(k+1)*4],'VEC4',5126)
 receipts.append({'side':side,'vertices':len(records),'source_fields':'Nearest actual genuine hand full8-influence skin field distal; original serialized hoodie boundary skin field proximal; triangle barycentric interpolation','blend_depth_range_m':[-.052,-.03],'geometry_unchanged':True,'records':records})
d['buffers'][0]['byteLength']=offset;binary=b''.join(parts);text=json.dumps(d,separators=(',',':')).encode();text+=b' '*((-len(text))%4);raw=b'glTF'+struct.pack('<II',2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary;target=out/'canonical-anatomical-hand-cuffs-weighted.glb';target.write_bytes(raw);report={'schema':'sub01.measured-cuff-weight-field-transfer.v1','source_sha256':hashlib.sha256(base['raw']).hexdigest(),'output_sha256':hashlib.sha256(raw).hexdigest(),'positions_normals_uv_indices_rest_unchanged':True,'records':receipts,'no_arbitrary_joint_angles_or_global_enlargement':True,'motion_contact_accepted':False,'native_imported':False};(out/'weight-transfer-report.json').write_text(json.dumps(report,indent=2));print('CANONICAL_CUFF_REAL_WEIGHT_TRANSFER',report['output_sha256'],flush=True)
