"""Actual shared65 skin matrices and source-weighted wrist collapse, no edits."""
import json,struct,sys,hashlib,math
from pathlib import Path
import numpy as np
from mathutils import Matrix,Quaternion,Vector
idle,walk,original,output=sys.argv[sys.argv.index('--')+1:]
def load(path):
 raw=Path(path).read_bytes();n=struct.unpack_from('<I',raw,12)[0];d=json.loads(raw[20:20+n]);ln,k=struct.unpack_from('<II',raw,20+n);b=raw[28+n:28+n+ln];cache={}
 def acc(i):
  if i in cache:return cache[i]
  a=d['accessors'][i];v=d['bufferViews'][a['bufferView']];dt=np.dtype({5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']]);width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];x=np.ndarray((a['count'],width),dtype=dt,buffer=b,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',width*dt.itemsize),dt.itemsize)).astype(float)
  if a.get('normalized'):x=np.maximum(-1,x/np.iinfo(dt).max)
  cache[i]=x;return x
 return d,acc,hashlib.sha256(raw).hexdigest()
def deform(path,seconds):
 d,a,sha=load(path);nodes=[dict(n)for n in d['nodes']];anim=d['animations'][0]
 for c in anim['channels']:
  s=anim['samplers'][c['sampler']];ts=a(s['input']).ravel();i=int(np.argmin(abs(ts-seconds)));assert abs(ts[i]-seconds)<1e-6;nodes[c['target']['node']][c['target']['path']]=a(s['output'])[i].tolist()
 parents={c:i for i,n in enumerate(nodes)for c in n.get('children',[])};world={}
 def W(i):
  if i not in world:
   n=nodes[i]
   if'matrix'in n:m=Matrix(np.asarray(n['matrix']).reshape(4,4).T)
   else:
    q=n.get('rotation',[0,0,0,1]);m=Matrix.LocRotScale(Vector(n.get('translation',[0,0,0])),Quaternion((q[3],*q[:3])),Vector(n.get('scale',[1,1,1])))
   world[i]=W(parents[i])@m if i in parents else m
  return world[i]
 skin=d['skins'][0];names=[d['nodes'][i]['name']for i in skin['joints']];ibm=a(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1);trans=np.asarray([W(i)for i in skin['joints']])@ibm
 return d,a,sha,names,ibm,trans
orig,oa,osha=load(original);onames=[orig['nodes'][i]['name']for i in orig['skins'][0]['joints']];oibm=oa(orig['skins'][0]['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
report={'schema':'sub01.shared65-actual-wrist-skin-matrix-diagnostic.v1','original_sha256':osha,'clips':[],'source_geometry_weights_body_and_poses_changed':False}
for path,seconds in [(idle,0.0),(walk,21/30)]:
 d,a,sha,names,ibm,trans=deform(path,seconds);assert names==onames;clip={'source_sha256':sha,'seconds':seconds,'sides':{}}
 for side in ['Left','Right']:
  fi=names.index('mixamorig:'+side+'ForeArm');hi=names.index('mixamorig:'+side+'Hand');assert np.array_equal(ibm[[fi,hi]],oibm[[fi,hi]])
  FA,H=trans[fi],trans[hi];rel=H[:3,:3]@FA[:3,:3].T;q=Matrix(rel.tolist()).to_quaternion().normalized();angle=math.degrees(q.angle);angle=min(angle,360-angle)
  wrist=np.linalg.inv(oibm[hi])[:3,3];elbow=np.linalg.inv(oibm[fi])[:3,3];axis=(wrist-elbow);axis/=np.linalg.norm(axis);posed_axis=FA[:3,:3]@axis;vector=np.array([q.x,q.y,q.z]);signed=float(vector@posed_axis);twist=math.degrees(2*math.atan2(signed,q.w));twist=(twist+180)%360-180
  row={'original_forearm_hand_IBMs_byte_values_equal':True,'ForeArm_jointWorld_times_originalIBM':FA.tolist(),'Hand_jointWorld_times_originalIBM':H.tolist(),'ForeArm_determinant':float(np.linalg.det(FA[:3,:3])),'Hand_determinant':float(np.linalg.det(H[:3,:3])),'relative_skin_rotation_angle_degrees':angle,'relative_skin_twist_about_posed_forearm_axis_degrees':twist,'regions':[]}
  sets=[('original_body_forearm',orig,oa,orig['meshes'][0])]
  for mesh in d['meshes']:
   if ('CC0Adult'+side in mesh.get('name',''))or('Cuff'+side in mesh.get('name','')):sets.append((mesh['name'],d,a,mesh))
  for label,doc,access,mesh in sets:
   records=[]
   for p in mesh['primitives']:
    attrs=p['attributes'];pos=access(attrs['POSITION']);delta=pos-wrist;axial=delta@axis;radial=np.linalg.norm(delta-axial[:,None]*axis,axis=1);mask=(abs(axial)<.03)&(radial<.075)
    if label=='original_body_forearm':mask&=(delta@np.array([1.,0,0])*(1 if side=='Left'else-1)>-.075)
    jsets=sorted(int(k.split('_')[1])for k in attrs if k.startswith('JOINTS_'));j=np.concatenate([access(attrs['JOINTS_'+str(k)])for k in jsets],axis=1).astype(int);weights=np.concatenate([access(attrs['WEIGHTS_'+str(k)])for k in jsets],axis=1)
    for index in np.nonzero(mask)[0]:
     relevant=sum(w for bone,w in zip(j[index],weights[index])if bone in[fi,hi])
     if relevant<.95:continue
     blend=np.sum(trans[j[index],:3,:3]*weights[index,:,None,None],axis=0);sv=np.linalg.svd(blend,compute_uv=False);records.append((float(np.linalg.det(blend)),float(sv[-1]),float(sum(w for bone,w in zip(j[index],weights[index])if bone==fi)),float(sum(w for bone,w in zip(j[index],weights[index])if bone==hi))))
   ar=np.asarray(records)
   row['regions'].append({'mesh':label,'wrist_axial_window_m':[-.03,.03],'source_vertices':len(records),'skin_blend_determinant_range':[float(ar[:,0].min()),float(ar[:,0].max())]if len(ar)else None,'minimum_singular_value_range':[float(ar[:,1].min()),float(ar[:,1].max())]if len(ar)else None,'vertices_with_min_singular_value_below_0p2':int((ar[:,1]<.2).sum())if len(ar)else 0,'ForeArm_weight_range':[float(ar[:,2].min()),float(ar[:,2].max())]if len(ar)else None,'Hand_weight_range':[float(ar[:,3].min()),float(ar[:,3].max())]if len(ar)else None})
  clip['sides'][side]=row
 report['clips'].append(clip)
Path(output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
