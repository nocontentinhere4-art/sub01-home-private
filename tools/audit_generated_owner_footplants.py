"""Read-only actual owner shoe/contact audit; no native placement or pose changes."""
import bpy,json,hashlib,struct,math,sys
from pathlib import Path
import numpy as np
from mathutils import Vector
IK='--contact-ik'in sys.argv
RIGID='--rigid'in sys.argv
ROOT=Path('/workspace/sub01-home-private/motion-runtime')/('footplant-audit-r4-contact-ik'if IK else'footplant-audit-r3-rigid'if RIGID else'footplant-audit-r2');ROOT.mkdir(exist_ok=True)
GENERATED=Path('/home/unreal/runtime-tools/generated-walk-owner.glb');WALK=Path('/home/unreal/runtime-tools/original-walking-owner-clip.glb');SOMA=Path('/workspace/sub01-home-private/motion-runtime/generated-r2-verified-adapters/relaxed-walk-stop.npz')
if RIGID:GENERATED=Path('/home/unreal/runtime-tools/generated-walk-rigid-owner.glb')
if IK:GENERATED=Path('/home/unreal/runtime-tools/generated-walk-contact-ik-owner.glb')
assert hashlib.sha256(GENERATED.read_bytes()).hexdigest()==('d26e9db52feabed7ec9aaf6f45cf89f777673e73172877553a67596f2a8b5864'if IK else'16b8ab6a32931f9abd175bcbca5b47a332bd7f17d4176e017929ae49c2d03000'if RIGID else'd7349ae34d74c0f7f36fc38f64e4d77612f5f397e6f4fe6e9fbe2c6e103056da')
assert hashlib.sha256(WALK.read_bytes()).hexdigest()=='9a7937e050a96c8f58dad1ffcfc8f5ff61f0c0699237afd5b996035f006d3f70'
def read(path):
 raw=path.read_bytes();length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length]);at=20+length;size=struct.unpack_from('<I',raw,at)[0];return doc,raw[at+8:at+8+size]
def merge_original():
 gd,gb=read(GENERATED);wd,wb=read(WALK);index={n.get('name'):i for i,n in enumerate(gd['nodes'])};baseview=len(gd['bufferViews']);baseacc=len(gd['accessors']);offset=len(gb)
 for view in wd['bufferViews']:
  view=dict(view);assert view.get('buffer',0)==0;view['byteOffset']=view.get('byteOffset',0)+offset;gd['bufferViews'].append(view)
 for accessor in wd['accessors']:
  accessor=dict(accessor);accessor['bufferView']+=baseview;gd['accessors'].append(accessor)
 for animation in wd['animations']:
  for sampler in animation['samplers']:sampler['input']+=baseacc;sampler['output']+=baseacc
  for channel in animation['channels']:
   name=wd['nodes'][channel['target']['node']]['name'];assert name in index;channel['target']['node']=index[name]
 gd['animations']=wd['animations'];binary=gb+wb;gd['buffers'][0]['byteLength']=len(binary);text=json.dumps(gd,separators=(',',':')).encode();text+=b' '*(-len(text)%4);binary+=b'\0'*(-len(binary)%4);p=ROOT/'original-walking-same-owner.glb';p.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary);return p
def owner_reference_graph():
 doc,binary=read(GENERATED);doc.pop('animations',None);text=json.dumps(doc,separators=(',',':')).encode();text+=b' '*(-len(text)%4);p=ROOT/'original-owner-reference-graph.glb';p.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(binary))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary);return p
source=np.load(SOMA,allow_pickle=False);metadata={};contacts={};source_positions={}
for key in source.files:
 array=source[key];metadata[key]={'shape':list(array.shape),'dtype':str(array.dtype)}
 if array.dtype.kind in'biuf':
  metadata[key].update(min=float(np.min(array)),max=float(np.max(array)))
  if 'contact'in key.lower():contacts[key]=array.tolist()
  if array.shape==(90,77,3):source_positions[key]=array[:,[69,70,71,74,75,76]].tolist()
result={'schema':'sub01.actual-generated-owner-footplant-audit.v1','generated_sha256':hashlib.sha256(GENERATED.read_bytes()).hexdigest(),'original_owner_sha256':'7609eccbe81631c00d123e69c54241597e28861d1dc947999425cd6c3257adbb','original_walking_clip_sha256':hashlib.sha256(WALK.read_bytes()).hexdigest(),'soma_sha256':hashlib.sha256(SOMA.read_bytes()).hexdigest(),'soma_arrays':metadata,'soma_contact_arrays':contacts,'soma_contact_joint_order':['LeftFoot','LeftToeBase','LeftToeEnd','RightFoot','RightToeBase','RightToeEnd'],'soma_contact_order_source':'kimodo/skeleton/definitions.py SOMASkeleton77 foot_joint_idx and SOMASkeleton30 conversion','soma_actual_foot_positions_y_up':source_positions,'source_position_joint_indices':[69,70,71,74,75,76],'source_position_joint_names':['LeftFoot','LeftToeBase','LeftToeEnd','RightFoot','RightToeBase','RightToeEnd'],'review_floor_m':-.015,'native_character_configuration':{'capsule_half_height_cm':91,'walk_mesh_offset_cm':[0,0,-91],'hands_mesh_yaw_degrees':-90,'mesh_origin_relative_capsule_bottom_cm':0,'actual_live_floor_distance_not_queried':True},'clips':{},'native_changed':False,'foot_contact_accepted':False}
def evaluate(path,label):
 bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=30;bpy.ops.import_scene.gltf(filepath=str(path));arm=next(o for o in scene.objects if o.type=='ARMATURE');assert len(arm.data.bones)==65;arm.animation_data_create();actions=list(bpy.data.actions);assert len(actions)<=1
 if actions:arm.animation_data.action=actions[0]
 for track in arm.animation_data.nla_tracks:track.mute=True
 meshes=[o for o in scene.objects if o.type=='MESH'];selection={side:[]for side in('Left','Right')}
 for o in meshes:
  for side in selection:
   groups={g.index for g in o.vertex_groups if g.name in('mixamorig:'+side+'Foot','mixamorig:'+side+'ToeBase','mixamorig:'+side+'Toe_End')}
   indices=[v.index for v in o.data.vertices if sum(q.weight for q in v.groups if q.group in groups)>.5]
   if indices:selection[side].append((o,indices))
 assert all(selection.values());dg=bpy.context.evaluated_depsgraph_get();records=[]
 def sample(frame):
  scene.frame_set(frame);bpy.context.view_layer.update();record={'frame':frame,'time_s':frame/30,'hips_world_m':list(arm.matrix_world@arm.pose.bones['mixamorig:Hips'].head),'feet':{}}
  for side,parts in selection.items():
   points=[];by_mesh=[]
   for o,indices in parts:
    evaluated=o.evaluated_get(dg);mesh=evaluated.to_mesh();pts=[evaluated.matrix_world@mesh.vertices[i].co for i in indices];points.extend(pts);by_mesh.append({'mesh':o.name,'material_names':[m.name for m in o.data.materials],'vertices':len(indices)});evaluated.to_mesh_clear()
   heights=np.array([p.z for p in points]);minimum=float(min(heights));band=[p for p in points if p.z<minimum+.001];joints={name:list(arm.matrix_world@arm.pose.bones['mixamorig:'+side+name].head)for name in('UpLeg','Leg','Foot','ToeBase')}
   record['feet'][side]={'min_shoe_surface_world_z_m':minimum,'sole_surface_p01_world_z_m':float(np.quantile(heights,.01)),'clearance_above_review_floor_m':minimum+.015,'lowest_1mm_band_centroid_world_m':list(sum(band,Vector())/len(band)),'selected_source_parts':by_mesh,'actual_joints_world_m':joints}
  return record
 frame_range=list(actions[0].frame_range)if actions else[0,0]
 for frame in range(int(round(frame_range[0])),int(round(frame_range[1]))+1):records.append(sample(frame))
 arm.data.pose_position='REST';rest=sample(0);arm.data.pose_position='POSE'
 rest_bones={}
 for side in('Left','Right'):
  for parent,child in [('UpLeg','Leg'),('Leg','Foot'),('Foot','ToeBase')]:
   a=arm.matrix_world@arm.data.bones['mixamorig:'+side+parent].head_local;b=arm.matrix_world@arm.data.bones['mixamorig:'+side+child].head_local
   rest_bones[side+parent+'->'+child]={'head_world':list(a),'child_joint_world':list(b),'joint_head_chain_length_m':(b-a).length}
 return {'frame_range':frame_range,'frames':records,'blender_inverse_bind_pose_diagnostic_skin':rest,'owner_reference_joint_head_chain_lengths':rest_bones,'sole_vertex_selection':'Full deformed source vertices with actual sum of Foot/ToeBase/Toe_End weights>0.5; selected actual source slides+socks independently; complete source mesh/texture unchanged'}
result['clips']['generated']=evaluate(GENERATED,'generated');result['clips']['original_walking']=evaluate(merge_original(),'original_walking');result['clips']['owner_default_reference_graph']=evaluate(owner_reference_graph(),'owner_default_reference_graph');(ROOT/'actual-footplant-audit.json').write_text(json.dumps(result,indent=2)+'\n')
for name,clip in result['clips'].items():
 for side in('Left','Right'):
  values=[r['feet'][side]['min_shoe_surface_world_z_m']for r in clip['frames']];print('ACTUAL_SHOE_SURFACE',name,side,'frames',len(values),'min/median/max_m',[float(f(values))for f in(np.min,np.median,np.max)],'rest_m',clip['blender_inverse_bind_pose_diagnostic_skin']['feet'][side]['min_shoe_surface_world_z_m'],flush=True)
print('SOMA_ARRAY_METADATA',json.dumps(metadata),flush=True)
