"""Evaluate actual glTF skinning directly, avoiding Blender importer rest conversion.
Run on private CPU, not native Game. Surface pairs remain candidates, not acceptance.
"""
import bpy,bmesh,json,struct,sys,hashlib
import numpy as np
from pathlib import Path
from mathutils import Matrix,Quaternion,Vector
from mathutils.bvhtree import BVHTree
source,role,output=sys.argv[sys.argv.index('--')+1:];source=Path(source);output=Path(output);raw=source.read_bytes();doc=None;binary=None;p=12
while p<len(raw):
 n,t=struct.unpack_from('<II',raw,p);data=raw[p+8:p+8+n]
 if t==0x4e4f534a:doc=json.loads(data)
 elif t==0x004e4942:binary=data
 p+=n+8
assert doc and binary
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
indices=sorted(set(np.linspace(0,len(times)-1,min(32,len(times))).round().astype(int)));times=[times[i]for i in indices]

# Import for actual PBR materials only; all imported geometry/armatures are hidden.
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source));s=bpy.context.scene
for o in list(s.objects):o.hide_render=True
material_names={m['name']:next(x for x in bpy.data.materials if x.name==m['name']or x.name.startswith(m['name']+'.'))for m in doc['materials']}
time=21/30;nodes=[dict(n)for n in doc['nodes']]
for i,path,ts,values,kind in tracks:
 hi=int(np.searchsorted(ts,time))
 if hi==0:value=values[0]
 elif hi>=len(ts):value=values[-1]
 elif ts[hi]==time:value=values[hi]
 elif kind=='STEP':value=values[hi-1]
 else:
  assert kind=='LINEAR';u=(time-ts[hi-1])/(ts[hi]-ts[hi-1]);x=values[hi-1];y=values[hi]
  if path=='rotation':q=Quaternion((x[3],*x[:3])).slerp(Quaternion((y[3],*y[:3])),u);value=np.array([q.x,q.y,q.z,q.w])
  else:value=x+(y-x)*u
 nodes[i][path]=value.tolist()
worlds={}
def world(i):
 if i not in worlds:worlds[i]=(world(parents[i])@matrix(nodes[i]))if i in parents else matrix(nodes[i])
 return worlds[i]
def zup(value):return Vector((value[0],-value[2],value[1]))
objects=[];head_hide_masks=[]
for ni,n in enumerate(doc['nodes']):
 if 'mesh'not in n or 'skin'not in n:continue
 skin=doc['skins'][n['skin']];ib=access(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1);transforms=np.array([list(map(list,world(j)))for j in skin['joints']])@ib
 for pi,prim in enumerate(doc['meshes'][n['mesh']]['primitives']):
  attrs=prim['attributes'];positions=access(attrs['POSITION']);sets=sorted(int(k.split('_')[1])for k in attrs if k.startswith('JOINTS_'));j=np.concatenate([access(attrs[f'JOINTS_{k}'])for k in sets],axis=1).astype(int);weights=np.concatenate([access(attrs[f'WEIGHTS_{k}'])for k in sets],axis=1);assert np.max(np.abs(weights.sum(axis=1)-1))<.01;p=np.column_stack([positions,np.ones(len(positions))]);posed=np.einsum('nwij,nj,nw->ni',transforms[j],p,weights)[:,:3];assert np.isfinite(posed).all();triangles=access(prim['indices']).ravel().astype(int).reshape(-1,3)
  mesh=bpy.data.meshes.new(n.get('name','Owner')+str(pi));mesh.from_pydata([(v[0],-v[2],v[1])for v in posed],[],triangles.tolist());mesh.update();o=bpy.data.objects.new(mesh.name,mesh);s.collection.objects.link(o);objects.append(o)
  uv=access(attrs['TEXCOORD_0']);layer=mesh.uv_layers.new(name='UVMap')
  for face in mesh.polygons:
   face.use_smooth=True
   for loop in face.loop_indices:
    value=uv[mesh.loops[loop].vertex_index];layer.data[loop].uv=(value[0],1-value[1])
  mesh.materials.append(material_names[doc['materials'][prim['material']]['name']]);head_joints=[ii for ii,jj in enumerate(skin['joints'])if doc['nodes'][jj].get('name')in ['mixamorig:Head','mixamorig:HeadTop_End']];head_weight=np.sum(weights*np.isin(j,head_joints),axis=1);head_hide_masks.append((o,np.mean(head_weight[triangles],axis=1)>.5))
name_indices={n.get('name'):i for i,n in enumerate(doc['nodes'])};left=zup(world(name_indices['mixamorig:LeftHand']).translation);right=zup(world(name_indices['mixamorig:RightHand']).translation);head=zup(world(name_indices['mixamorig:Head']).translation);hip=zup(world(name_indices['mixamorig:Hips']).translation);center=(left+right)*.5
w=bpy.data.worlds.new('Actual serialized owner source studio');w.use_nodes=True;w.node_tree.nodes['Background'].inputs[0].default_value=(.13,.15,.18,1);w.node_tree.nodes['Background'].inputs[1].default_value=.4;s.world=w
lights=[]
for power,offset in[(160,(-.8,-1.1,1)),(75,(.9,.7,.7))]:bpy.ops.object.light_add(type='AREA');light=bpy.context.object;light.data.energy=power;light.data.size=1.8;light.location=hip+Vector(offset);light.rotation_euler=(hip-light.location).to_track_quat('-Z','Y').to_euler();lights.append(light)
bpy.ops.object.camera_add();camera=bpy.context.object;s.camera=camera;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=16;s.cycles.use_denoising=True;s.render.resolution_x=1200;s.render.resolution_y=900;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX';output.mkdir(parents=True,exist_ok=True)
camera.data.type='ORTHO';camera.data.ortho_scale=1.65;target=hip+Vector((0,0,.17));camera.location=target+Vector((0,-2,.25));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();s.render.filepath=str(output/'actual-serialized-owner-Walk021-body.png');bpy.ops.render.render(write_still=True)
# Match first-person native head-subtree visibility; never move hands to camera.
for object,mask in head_hide_masks:
 bm=bmesh.new();bm.from_mesh(object.data);bm.faces.ensure_lookup_table();bmesh.ops.delete(bm,geom=[face for face in bm.faces if mask[face.index]],context='FACES');bm.to_mesh(object.data);bm.free()
head_top=zup(world(name_indices['mixamorig:HeadTop_End']).translation)
camera.data.type='PERSP';camera.data.lens=24;camera.data.sensor_width=36;camera.data.clip_start=.012;left_shoulder=zup(world(name_indices['mixamorig:LeftShoulder']).translation);right_shoulder=zup(world(name_indices['mixamorig:RightShoulder']).translation);across=left_shoulder-right_shoulder;across.z=0;forward=across.cross(Vector((0,0,1))).normalized();camera.location=head_top+forward*.13-Vector((0,0,.065));look=forward*.342-Vector((0,0,.94));camera.rotation_euler=look.to_track_quat('-Z','Y').to_euler();s.render.filepath=str(output/'actual-serialized-owner-Walk021-firstperson.png');bpy.ops.render.render(write_still=True)
report={'schema':'sub01.actual-serialized-owner-source-render.v1','source_sha256':hashlib.sha256(raw).hexdigest(),'clip':role,'seconds':time,'actual_serialized_skin_world_evaluated_directly':True,'materials_imported_from_same_glTF':True,'pose_not_Blender_retargeted':True,'left_wrist_world_blender':list(left),'right_wrist_world_blender':list(right),'head_world_blender':list(head),'source_camera_eye_reference':'HeadTop minus65mm +130mm body-anterior from actual shoulder axis; look70deg down anatomical forward, original Head subtree hidden as native FPS does','native_house_verified':False,'contact_accepted':False};(output/'render-report.json').write_text(json.dumps(report,indent=2));print('ACTUAL_SERIALIZED_OWNER_RENDERED',json.dumps(report),flush=True)
