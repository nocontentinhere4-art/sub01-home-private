"""Evaluate actual glTF skinning directly, avoiding Blender importer rest conversion.
Run on private CPU, not native Game. Surface pairs remain candidates, not acceptance.
"""
import bpy,bmesh,json,struct,sys,hashlib
import numpy as np
from pathlib import Path
from mathutils import Matrix,Quaternion,Vector
from mathutils.bvhtree import BVHTree
source,role,output,expected_sha=sys.argv[sys.argv.index('--')+1:];source=Path(source);output=Path(output);raw=source.read_bytes();doc=None;binary=None;p=12
while p<len(raw):
 n,t=struct.unpack_from('<II',raw,p);data=raw[p+8:p+8+n]
 if t==0x4e4f534a:doc=json.loads(data)
 elif t==0x004e4942:binary=data
 p+=n+8
assert doc and binary
assert hashlib.sha256(raw).hexdigest()==expected_sha
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
assert len(times)==557;times=[11.833333015441895]
meshes={};metadata={}
for ni,n in enumerate(doc['nodes']):
 if 'mesh'not in n or 'skin'not in n:continue
 name=n.get('name',doc['meshes'][n['mesh']].get('name',''))
 if not any(x in name.lower()for x in ['cc0adult','anatomicalfittedhoodiecuff']):continue
 skin=doc['skins'][n['skin']];ib=access(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1);parts=[];faces=[];offset=0
 for prim in doc['meshes'][n['mesh']]['primitives']:
  attrs=prim['attributes'];positions=access(attrs['POSITION']);sets=sorted(int(k.split('_')[1])for k in attrs if k.startswith('JOINTS_'));joints=np.concatenate([access(attrs[f'JOINTS_{k}'])for k in sets],axis=1).astype(int);weights=np.concatenate([access(attrs[f'WEIGHTS_{k}'])for k in sets],axis=1);assert np.max(np.abs(weights.sum(axis=1)-1))<.0001
  parts.append((np.column_stack([positions,np.ones(len(positions))]),joints,weights));triangles=access(prim['indices']).ravel().astype(int).reshape(-1,3);faces.extend((triangles+offset).tolist());offset+=len(positions)
 meshes[name]=(skin['joints'],ib,parts,faces);metadata[name]={'joints':np.concatenate([p[1]for p in parts]),'weights':np.concatenate([p[2]for p in parts]),'faces':np.asarray(faces),'bone_names':[doc['nodes'][i]['name']for i in skin['joints']]}
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
for time in times:
 nodes=[dict(n)for n in doc['nodes']]
 for i,path,ts,values,kind in tracks:nodes[i][path]=sample(ts,values,time,path,kind).tolist()
 worlds={}
 def world(i):
  if i not in worlds:worlds[i]=(world(parents[i])@matrix(nodes[i]))if i in parents else matrix(nodes[i])
  return worlds[i]
 posed={};posed_points={}
 for name,(js,ib,parts,faces)in meshes.items():
  transforms=np.array([list(map(list,world(j)))for j in js])@ib;positions=[]
  for p,j,w in parts:positions.append(np.einsum('nwij,nj,nw->ni',transforms[j],p,w)[:,:3])
  points=np.concatenate(positions);assert np.isfinite(points).all();posed_points[name]=points;posed[name]=BVHTree.FromPolygons(points.tolist(),faces,all_triangles=True,epsilon=0)
 row={'seconds':time,'sides':{}}
 for side in ['Left','Right']:
  cuff=next(name for name in posed if 'Cuff'+side in name);hand=next(name for name in posed if 'cc0adult'in name.lower()and side.lower()in name.lower());pairs=posed[cuff].overlap(posed[hand]);meta=metadata[hand];unique=sorted(set(p[1]for p in pairs));cuff_unique=sorted(set(p[0]for p in pairs));categories={};dominant={};projections=[]
  names={n.get('name'):i for i,n in enumerate(doc['nodes'])};wrist=np.asarray(world(names['mixamorig:'+side+'Hand']).translation);elbow=np.asarray(world(names['mixamorig:'+side+'ForeArm']).translation);axis=elbow-wrist;axis/=np.linalg.norm(axis)
  import re
  for triangle in unique:
   ids=meta['faces'][triangle];weights={}
   for i in ids:
    for j,weight in zip(meta['joints'][i],meta['weights'][i]):
     if weight:weights[meta['bone_names'][j]]=weights.get(meta['bone_names'][j],0)+float(weight)/3
   strongest=max(weights,key=weights.get);dominant[strongest]=dominant.get(strongest,0)+1
   finger=sum(v for n,v in weights.items()if re.search(r'Hand(Thumb|Index|Middle|Ring|Pinky)',n));forearm=sum(v for n,v in weights.items()if n.endswith('ForeArm'));region='finger'if finger>.5 else 'forearm'if forearm>.5 else 'palm_or_wrist';categories[region]=categories.get(region,0)+1
   center=posed_points[hand][ids].mean(axis=0);projections.append(float((center-wrist)@axis))
  ring_counts={};cuff_meta=metadata[cuff]
  for triangle in cuff_unique:
   for index in cuff_meta['faces'][triangle]:
    ring=str(int(index)//26);ring_counts[ring]=ring_counts.get(ring,0)+1
  row['sides'][side]={'cuff_hand_triangle_candidates':len(pairs),'unique_hand_triangles':len(unique),'unique_cuff_triangles':len(cuff_unique),'touched_hand_region_by_majority_skin_weight':categories,'dominant_hand_bone_histogram':dominant,'hand_triangle_centroid_wrist_toward_elbow_projection_range_m':[min(projections),max(projections)]if projections else None,'wrist_world_glTF_m':wrist.tolist(),'forearm_joint_world_glTF_m':elbow.tolist(),'cuff_unique_triangle_sample':cuff_unique[:20],'hand_unique_triangle_sample':unique[:20],'first_pairs':pairs[:10]}

 records.append(row)
# Analysis-only closure of the genuine forearm cut: original sampled skin and
# cloth geometry remain unchanged. Distances use ORIGINAL skin, not cap faces.
depth=[]
for side in ['Right']:
 cuff=next(name for name in posed if 'Cuff'+side in name);hand=next(name for name in posed if 'cc0adult'in name.lower()and side.lower()in name.lower())
 points=posed_points[hand];triangles=metadata[hand]['faces'];temp=bpy.data.meshes.new('AnalysisOnlyHandClosure');temp.from_pydata(points.tolist(),[],triangles.tolist());temp.update();bm=bmesh.new();bm.from_mesh(temp);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=1.e-7);boundary=[e for e in bm.edges if e.is_boundary];before=len(bm.faces);bmesh.ops.holes_fill(bm,edges=boundary,sides=0);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.verts.ensure_lookup_table();closed=not any(not e.is_manifold for e in bm.edges);cap_faces=len(bm.faces)-before
 assert closed,'No penetration-depth claim from a nonclosed analysis surface'
 tree=BVHTree.FromPolygons([v.co for v in bm.verts],[[v.index for v in f.verts]for f in bm.faces],all_triangles=False,epsilon=0);bm.free();bpy.data.meshes.remove(temp)
 directions=[Vector((1,.179,.317)).normalized(),Vector((.237,1,.119)).normalized(),Vector((.131,.229,1)).normalized()]
 cuff_indices=sorted(set(a for a,b in posed[cuff].overlap(posed[hand])));inside=[];ambiguous=0;total=0
 for face in cuff_indices:
  ids=metadata[cuff]['faces'][face];v=posed_points[cuff][ids]
  for a in range(33):
   for b in range(33-a):
    p=Vector(v[0]*(a/32)+v[1]*(b/32)+v[2]*(1-(a+b)/32));votes=[];total+=1
    for direction in directions:
     start=p.copy();hits=0
     for _ in range(100):
      hit,normal,index,length=tree.ray_cast(start,direction,2)
      if hit is None:break
      hits+=1;start=hit+direction*1.e-5
     votes.append(hits%2==1)
    if len(set(votes))!=1:ambiguous+=1
    if all(votes):
     near,normal,triangle,distance=posed[hand].find_nearest(p)
     inside.append({'cloth_triangle':face,'point_glTF_m':list(p),'nearest_actual_skin_glTF_m':list(near),'actual_skin_triangle':triangle,'depth_m':distance,'unanimous_three_rays':True})
 depth.append({'side':side,'samples':total,'inside_samples':len(inside),'ambiguous_samples':ambiguous,'max_sampled_depth_mm':max((x['depth_m']*1000 for x in inside),default=0),'worst_witness':max(inside,key=lambda x:x['depth_m'])if inside else None,'analysis_closure_faces_added':cap_faces,'analysis_manifold_closed':closed,'spacing':'barycentric 32 subdivisions per intersecting original cloth triangle; sampled maximum is not a continuous global maximum','depth_reference':'nearest original genuine hand surface, excludes analysis cap from distance','geometry_edited':False})
report={'schema':'sub01.serialized-glTF-skin-cuff-audit.v1','source_sha256':hashlib.sha256(raw).hexdigest(),'clip':role,'samples':records,'actual_skinning_formula':'sum(weight * jointWorld * inverseBind * POSITION), evaluated directly from serialized original/native coordinate graph','no_Blender_import_rest_conversion':True,'native_or_contact_acceptance':False,'sampled_cloth_into_genuine_skin_depth':depth};output.write_text(json.dumps(report,indent=2));print('DIRECT_SERIALIZED_CUFF_AUDIT',json.dumps({'source':report['source_sha256'],'clip':role,'samples':len(records),'max_candidates':{s:max(r['sides'][s]['cuff_hand_triangle_candidates']for r in records)for s in ['Left','Right']}}),flush=True)
