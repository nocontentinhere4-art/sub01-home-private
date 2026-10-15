"""Runpod-only FBX format experiment: serialized skin truth, no native import/readiness."""
import bpy,numpy as np,sys,json,struct,hashlib,math,time
from pathlib import Path
from mathutils import Vector
source,out,expected,*options= sys.argv[sys.argv.index('--')+1:];source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=False)
raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==expected;size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);length,kind=struct.unpack_from('<II',raw,20+size);assert kind==0x004e4942;binary=raw[28+size:28+size+length]
def acc(i):
 a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']];assert not a.get('sparse')and not v.get('extensions');dtype={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']];n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];dt=np.dtype(dtype);ar=np.ndarray((a['count'],n),dtype=dt,buffer=binary,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',dt.itemsize*n),dt.itemsize)).astype(np.float64)
 if a.get('normalized'):ar=np.maximum(-1,ar/np.iinfo(dt).max)
 return ar
parents={c:i for i,n in enumerate(doc['nodes'])for c in n.get('children',[])}
from mathutils import Matrix,Quaternion

def worlds(frame=None):
 local=[]
 for n in doc['nodes']:
  if 'matrix'in n:m=np.asarray(n['matrix']).reshape(4,4).T
  else:
   q=n.get('rotation',[0,0,0,1]);m=np.asarray(Quaternion((q[3],*q[:3])).to_matrix().to_4x4(),dtype=float);m[:3,:3]=m[:3,:3]@np.diag(n.get('scale',[1,1,1]));m[:3,3]=n.get('translation',[0,0,0])
  local.append(m)
 if frame is not None:
  for c in doc['animations'][0]['channels']:
   s=doc['animations'][0]['samplers'][c['sampler']];value=acc(s['output'])[frame];i=c['target']['node'];p=c['target']['path']
   if p=='rotation':local[i][:3,:3]=np.asarray(Quaternion((value[3],*value[:3])).to_matrix())@np.diag(doc['nodes'][i].get('scale',[1,1,1]))
   elif p=='translation':local[i][:3,3]=value
   else:raise RuntimeError('Unexpected animated scaling')
 result={}
 def W(i):
  if i not in result:result[i]=W(parents[i])@local[i]if i in parents else local[i]
  return result[i]
 return[W(i)for i in range(len(local))]
mesh_nodes=[(i,n)for i,n in enumerate(doc['nodes'])if 'mesh'in n and 'skin'in n];assert len(mesh_nodes)>=5
frames=len(acc(doc['animations'][0]['samplers'][0]['input']));probes=list(range(frames))if '--all-frames'in options else sorted(set([0,frames//2,frames-1]));fps=30
index_cache={};duplicate_evidence=[]
def actual_unique_indices(p):
 key=id(p)
 if key in index_cache:return index_cache[key]
 idx=acc(p['indices']).astype(int).reshape(-1,3);seen={};keep=[];dupes=0
 def winding(row):
  at=int(np.argmin(row));return tuple(np.roll(row,-at))
 for i,row in enumerate(idx):
  k=tuple(sorted(row))
  if k in seen:
   assert doc['materials'][p['material']].get('doubleSided')is True,'Cannot drop a source backface without double-sided material'
   assert winding(row)!=winding(idx[seen[k]]),'Unexpected same-winding duplicate'
   dupes+=1
  else:seen[k]=i;keep.append(i)
 index_cache[key]=idx[np.asarray(keep)];duplicate_evidence.append({'material':p['material'],'raw_triangles':len(idx),'unique_triangles':len(keep),'exact_opposite_winding_duplicate_faces':dupes,'duplicate_surface_attributes_identical_by_same_vertex_indices':True,'double_sided_material':bool(doc['materials'][p['material']].get('doubleSided'))});return index_cache[key]

def source_geometry(frame):
 w=worlds(frame);result={}
 for ni,node in mesh_nodes:
  skin=doc['skins'][node['skin']];ibm=acc(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1);mat=np.asarray([w[i]for i in skin['joints']])@ibm;parts=[]
  for p in doc['meshes'][node['mesh']]['primitives']:
   a=p['attributes'];pos=acc(a['POSITION']);h=np.c_[pos,np.ones(len(pos))];posed=np.zeros((len(pos),4))
   for set_ in [0,1]:
    if 'JOINTS_'+str(set_)not in a:continue
    joints=acc(a['JOINTS_'+str(set_)]).astype(int);weights=acc(a['WEIGHTS_'+str(set_)])
    for k in range(4):posed+=np.einsum('nij,nj->ni',mat[joints[:,k]],h)*weights[:,k,None]
   idx=actual_unique_indices(p);points=posed[:,:3][:,[0,2,1]]*np.array([1,-1,1]);parts.append(points[idx])
  result[node['name']]=np.concatenate(parts)
 return result
truth={f:source_geometry(f)for f in probes}

def snapshot(arm,frame):
 bpy.context.scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update();result={};dg=bpy.context.evaluated_depsgraph_get()
 for _,node in mesh_nodes:
  obj=bpy.data.objects.get(node['name']);assert obj is not None,node['name'];assert any(m.type=='ARMATURE'and m.object==arm for m in obj.modifiers)
  ev=obj.evaluated_get(dg);m=ev.to_mesh();m.calc_loop_triangles();coords=np.empty(len(m.vertices)*3);m.vertices.foreach_get('co',coords);coords=coords.reshape(-1,3);world=np.asarray(ev.matrix_world);coords=coords@world[:3,:3].T+world[:3,3];idx=np.asarray([list(t.vertices)for t in m.loop_triangles]);result[node['name']]=coords[idx];ev.to_mesh_clear()
 return result

def compare(a,b):
 rows=[]
 for name,tri in a.items():
  actual=b[name]
  if actual.shape!=tri.shape:rows.append({'mesh':name,'same_triangles':False,'source':len(tri),'target':len(actual)});continue
  # Imported/exported triangles must preserve the original ordered topology;
  # allow only corner winding permutation, never nearest-neighbour masking.
  best=np.full(len(tri),np.inf)
  for perm in[(0,1,2),(0,2,1),(1,0,2),(1,2,0),(2,0,1),(2,1,0)]:best=np.minimum(best,np.linalg.norm(tri-actual[:,perm,:],axis=2).max(axis=1))
  rows.append({'mesh':name,'same_triangles':True,'triangles':len(tri),'max_ordered_triangle_corner_error_m':float(best.max()),'p99_error_m':float(np.quantile(best,.99))})
 return rows
def material_slot_proof():
 result=[]
 for _,node in mesh_nodes:
  obj=bpy.data.objects[node['name']];mesh=obj.data;mesh.calc_loop_triangles();expected_names=[]
  for p in doc['meshes'][node['mesh']]['primitives']:
   expected_names += [doc['materials'][p['material']]['name']]*len(actual_unique_indices(p))
  actual_names=[obj.material_slots[mesh.polygons[t.polygon_index].material_index].material.name for t in mesh.loop_triangles]
  assert len(expected_names)==len(actual_names)
  mismatch=sum(a!=b for a,b in zip(expected_names,actual_names))
  slots=[]
  for index,slot in enumerate(obj.material_slots):
   names=[i for i,m in enumerate(doc['materials'])if m['name']==slot.material.name];assert len(names)==1
   source_index=names[0];mat=doc['materials'][source_index]
   slots.append({'blender_fbx_slot_index':index,'material_name':slot.material.name,'source_glTF_material_index':source_index,'source_doubleSided_required':bool(mat.get('doubleSided',False)),'observed_Blender_use_backface_culling':bool(slot.material.use_backface_culling),'native_TwoSided_verified':False})
  result.append({'mesh':node['name'],'unique_triangles':len(actual_names),'triangle_material_assignment_mismatches':mismatch,'ordered_triangle_material_sequence_sha256':hashlib.sha256('\0'.join(actual_names).encode()).hexdigest(),'slots':slots})
  assert mismatch==0,'FBX changed material-to-triangle assignment'
 return result
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=fps;bpy.ops.import_scene.gltf(filepath=str(source));arm=next(o for o in scene.objects if o.type=='ARMATURE');assert len(arm.data.bones)==65
assert len(bpy.data.actions)==1;action=list(bpy.data.actions)[0];arm.animation_data.action=action
for t in arm.animation_data.nla_tracks:t.mute=True
start,end=action.frame_range;assert abs(end-start-(frames-1))<.001
source_material_slots=material_slot_proof()
imported={f:snapshot(arm,start+f)for f in probes};source_comparison={str(f):compare(truth[f],imported[f])for f in probes}
# Preserve actual imported bone frame; no edit-mode bone alignment or pose-as-rest.
selected=[arm]+[bpy.data.objects[n['name']]for _,n in mesh_nodes]
for o in scene.objects:o.select_set(o in selected)
bpy.context.view_layer.objects.active=arm;scene.frame_start=round(start);scene.frame_end=round(end);scene.frame_set(round(start));fbx=out/'serialized-owner-diagnostic.fbx'
flags=dict(use_selection=True,object_types={'ARMATURE','MESH'},add_leaf_bones=False,use_armature_deform_only=False,use_mesh_modifiers=False,apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0,bake_anim_step=1,path_mode='COPY',embed_textures=True)
bpy.ops.export_scene.fbx(filepath=str(fbx),**flags)
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=fps;bpy.ops.import_scene.fbx(filepath=str(fbx),use_anim=True,automatic_bone_orientation=False,anim_offset=0.0)
arm=next(o for o in scene.objects if o.type=='ARMATURE');assert len(arm.data.bones)==65;assert len(bpy.data.actions)==1;action=list(bpy.data.actions)[0];arm.animation_data.action=action
for t in arm.animation_data.nla_tracks:t.mute=True
rs,re=action.frame_range;assert abs(re-rs-(frames-1))<.001
fbx_material_slots=material_slot_proof()
roundtrip={f:snapshot(arm,rs+f)for f in probes};fbx_comparison={str(f):compare(truth[f],roundtrip[f])for f in probes}
report={'schema':'sub01.serialized-owner-fbx-source-experiment.v1','source_sha256':expected,'fbx_sha256':hashlib.sha256(fbx.read_bytes()).hexdigest(),'blender':bpy.app.version_string,'source_frames':frames,'fps':fps,'probe_frames':probes,'source_blender_range':[start,end],'fbx_blender_range':[rs,re],'no_bone_alignment_or_pose_as_rest':True,'source_GLTF_to_Blender':source_comparison,'source_GLTF_to_FBX_reimport':fbx_comparison,'source_Blender_material_slots':source_material_slots,'FBX_reimport_material_slots':fbx_material_slots,'native_TwoSided_and_material_assignment_pending':True,'source_exact_duplicate_face_evidence':duplicate_evidence,'raw_triangle_multiplicity_preserved':False,'only_exact_opposite_winding_doubleSided_duplicates_compacted':True,'native_imported':False,'native_or_contact_accepted':False}
(out/'conversion-proof.json').write_text(json.dumps(report,indent=2)+'\n');print('ACTUAL_FBX_CONVERSION_PROOF',json.dumps(report),flush=True)
