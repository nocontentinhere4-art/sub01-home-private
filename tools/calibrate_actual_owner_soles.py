"""Read-only measured slides-sole patches in actual glTF bone frames."""
import bpy,json,math,struct,hashlib
from pathlib import Path
import numpy as np
from mathutils import Vector,Matrix,Quaternion
ROOT=Path('/workspace/sub01-home-private/motion-runtime/footplant-audit-r2');SOURCE=ROOT/'original-owner-reference-graph.glb';OUT=ROOT/'actual-owner-sole-calibration.json'
raw=SOURCE.read_bytes();length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length]);parents={c:i for i,n in enumerate(doc['nodes'])for c in n.get('children',[])};world={}
def wm(i):
 if i in world:return world[i]
 n=doc['nodes'][i]
 if'matrix'in n:m=Matrix(np.array(n['matrix']).reshape((4,4),order='F').tolist())
 else:
  t=n.get('translation',[0,0,0]);r=n.get('rotation',[0,0,0,1]);s=n.get('scale',[1,1,1]);m=Matrix.Translation(Vector(t))@Quaternion((r[3],r[0],r[1],r[2])).to_matrix().to_4x4()@Matrix.Diagonal(Vector((*s,1)))
 world[i]=wm(parents[i])@m if i in parents else m;return world[i]
index={n.get('name'):i for i,n in enumerate(doc['nodes'])}
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(SOURCE));scene=bpy.context.scene;arm=next(o for o in scene.objects if o.type=='ARMATURE');shoe=bpy.data.objects['slides'];dg=bpy.context.evaluated_depsgraph_get();bpy.context.view_layer.update();evaluated=shoe.evaluated_get(dg);mesh=evaluated.to_mesh();points=[evaluated.matrix_world@v.co for v in mesh.vertices]
result={'schema':'sub01.actual-owner-sole-calibration.v1','owner_sha256':'7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb','reference_graph_sha256':hashlib.sha256(raw).hexdigest(),'source_mesh':'slides','coordinate_system':'glTF Y-up; world points metres, inverse full original bone matrix produces local centimetres for this0.01-scaled owner','feet':{},'native_imported':False,'contact_accepted':False}
for side in('Left','Right'):
 groups={g.index for g in shoe.vertex_groups if g.name in('mixamorig:'+side+'Foot','mixamorig:'+side+'ToeBase','mixamorig:'+side+'Toe_End')};ids=[v.index for v in shoe.data.vertices if sum(q.weight for q in v.groups if q.group in groups)>.5];assert ids
 pts=[Vector((points[i].x,points[i].z,-points[i].y))for i in ids];ankle=wm(index['mixamorig:'+side+'Foot']).translation;toe=wm(index['mixamorig:'+side+'ToeBase']).translation;forward=toe-ankle;forward.y=0;forward.normalize();right=forward.cross(Vector((0,1,0))).normalized();along=[(p-ankle).dot(forward)for p in pts];low,high=min(along),max(along);heel=[p for p,d in zip(pts,along)if d<low+.25*(high-low)];front=[p for p,d in zip(pts,along)if d>high-.25*(high-low)];width=[(p-ankle).dot(right)for p in front];split=(min(width)+max(width))/2;inner=[p for p,w in zip(front,width)if w<=split];outer=[p for p,w in zip(front,width)if w>split]
 patches={}
 for name,candidates,bone in [('heel',heel,'Foot'),('toe_inner',inner,'ToeBase'),('toe_outer',outer,'ToeBase')]:
  ymin=min(p.y for p in candidates);band=[p for p in candidates if p.y<=ymin+.0005];point=sum(band,Vector())/len(band);matrix=wm(index['mixamorig:'+side+bone]);local=matrix.inverted()@point;roundtrip=matrix@local
  assert(roundtrip-point).length<1e-6
  patches[name]={'bone':'mixamorig:'+side+bone,'local_offset_cm':list(local),'actual_reference_world_m':list(point),'reference_surface_samples':len(band),'max_band_above_actual_patch_min_m':.0005,'roundtrip_world_error_m':(roundtrip-point).length}
 h=Vector(patches['heel']['actual_reference_world_m']);a=Vector(patches['toe_inner']['actual_reference_world_m']);b=Vector(patches['toe_outer']['actual_reference_world_m']);normal=(a-h).cross(b-h).normalized()
 if normal.y<0:normal=-normal
 result['feet'][side]={'patches':patches,'shoe_weighted_vertices':len(ids),'reference_sole_plane_normal_world':list(normal),'reference_sole_pitch_tilt_degrees':math.degrees(math.acos(max(-1,min(1,normal.y)))),'joint_head_chain_lengths_m':{a+'->'+b:(wm(index['mixamorig:'+side+b]).translation-wm(index['mixamorig:'+side+a]).translation).length for a,b in [('UpLeg','Leg'),('Leg','Foot')]}}
evaluated.to_mesh_clear();OUT.write_text(json.dumps(result,indent=2)+'\n');print('ACTUAL_SOLE_CALIBRATION',json.dumps(result),flush=True)
