"""Private owner/cuff first-person candidate; original source files immutable."""
import bpy,bmesh,json,sys,hashlib,math,statistics
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
owner=Path('/home/unreal/runtime-tools/canonical-walk-owner.glb');hands_path=Path('/home/unreal/runtime-tools/official-hands-walk-candidate-r8.glb');out=Path('/workspace/sub01-home-private/human-base-hands-r1/owner-composite-r15');out.mkdir(exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene;s.render.fps=30;bpy.ops.import_scene.gltf(filepath=str(owner));oldrig=next(o for o in s.objects if o.type=='ARMATURE');assert len(oldrig.data.bones)==65;oldrig.animation_data_create();oldrig.animation_data.action=list(bpy.data.actions)[0]
for track in oldrig.animation_data.nla_tracks:track.mute=True
oldmeshes=[o for o in s.objects if o.type=='MESH'];body_rest={b.name:oldrig.matrix_world@b.matrix_local for b in oldrig.data.bones};body_action=oldrig.animation_data.action
before=set(bpy.data.actions);bpy.ops.import_scene.gltf(filepath=str(hands_path));newrig=next(o for o in s.objects if o.type=='ARMATURE'and o!=oldrig);assert len(newrig.data.bones)==44;newaction=next(a for a in bpy.data.actions if a not in before).copy();newaction.name='Recorded finger layer; captured body owns wrist once';newrig.animation_data_create();newrig.animation_data.action=newaction
for track in newrig.animation_data.nla_tracks:track.mute=True
for slot in newaction.slots:
 for layer in newaction.layers:
  for strip in layer.strips:
   try:bag=strip.channelbag(slot)
   except Exception:continue
   if bag:
    for fc in list(bag.fcurves):
     if any('pose.bones[\"mixamorig:'+side+'Hand\"]'in fc.data_path for side in['Left','Right']):bag.fcurves.remove(fc);continue
     modifier=fc.modifiers.new('CYCLES');modifier.mode_before='REPEAT';modifier.mode_after='REPEAT'
for side in['Left','Right']:newrig.pose.bones['mixamorig:'+side+'Hand'].matrix_basis=Matrix.Identity(4)
source_meshes={side:bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']for side in['Left','Right']};new_rest={b.name:newrig.matrix_world@b.matrix_local for b in newrig.data.bones}
def handframe(rest,side):
 p=rest['mixamorig:'+side+'Hand'].translation;m=rest['mixamorig:'+side+'HandMiddle1'].translation;i=rest['mixamorig:'+side+'HandIndex1'].translation;k=rest['mixamorig:'+side+'HandPinky1'].translation;y=(p-rest['mixamorig:'+side+'ForeArm'].translation).normalized();x=(i-k).normalized();x=(x-y*x.dot(y)).normalized();z=x.cross(y).normalized();return Matrix(((x.x,y.x,z.x,p.x),(x.y,y.y,z.y,p.y),(x.z,y.z,z.z,p.z),(0,0,0,1)))
# New candidate only: retire original hand surfaces beneath their existing cuffs.
# Every retained original vertex coordinate/weight remains unchanged.
removed=[];skin_colors=[];pixel_cache={};cuff_planes={};cloth_near_wrist={side:[]for side in['Left','Right']};genuine_cuff_vertices={}
def face_rgb(o,face):
 uv=o.data.uv_layers.active
 if not uv:return None
 mat=o.material_slots[face.material_index].material if face.material_index<len(o.material_slots)else None
 images=[n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE'and n.image]if mat and mat.use_nodes else[]
 if not images:return None
 image=images[0]
 if image.name not in pixel_cache:pixel_cache[image.name]=tuple(image.pixels[:]);print('CACHED_SKIN_IMAGE',image.name,image.size[:],flush=True)
 u=sum(uv.data[i].uv.x for i in face.loop_indices)/len(face.loop_indices);v=sum(uv.data[i].uv.y for i in face.loop_indices)/len(face.loop_indices);x=min(image.size[0]-1,max(0,int(u*image.size[0])));y=min(image.size[1]-1,max(0,int(v*image.size[1])));idx=(y*image.size[0]+x)*4
 return tuple(pixel_cache[image.name][idx+j]for j in range(3))
for o in oldmeshes:
 if not o.vertex_groups:continue
 o.data=o.data.copy();selected=set();face_ids=set();by_side={side:[]for side in['Left','Right']}
 for v in o.data.vertices:
  hand_weight=sum(g.weight for g in v.groups if'Hand'in o.vertex_groups[g.group].name)
  if hand_weight>.3:selected.add(v.index)
 for face in o.data.polygons:
  if not all(i in selected for i in face.vertices):continue
  rgb=face_rgb(o,face)
  # Classify actual authored skin palette, never retire black hoodie by bone weights.
  if rgb is None:continue
  if max(rgb)<.30 and min(rgb)>.75*max(rgb):
   genuine_cuff_vertices.setdefault(o.name,set()).update(face.vertices)
  if not(rgb[0]>.08 and rgb[0]>rgb[1]*1.03 and rgb[0]>rgb[2]*1.08):
   for side in['Left','Right']:
    wrist=body_rest['mixamorig:'+side+'Hand'].translation
    for i in face.vertices:
     point=o.matrix_world@o.data.vertices[i].co
     if(point-wrist).length<.07:cloth_near_wrist[side].append(point)
   continue
  face_ids.add(face.index)
  if len(skin_colors)<256:skin_colors.append(rgb)
  centroid=sum((o.matrix_world@o.data.vertices[i].co for i in face.vertices),Vector())/len(face.vertices)
  side=min(['Left','Right'],key=lambda side:(centroid-body_rest['mixamorig:'+side+'Hand'].translation).length)
  by_side[side].extend(o.matrix_world@o.data.vertices[i].co for i in face.vertices)
 for side,points in by_side.items():
  if not points:continue
  wrist=body_rest['mixamorig:'+side+'Hand'].translation;elbow=body_rest['mixamorig:'+side+'ForeArm'].translation;axis=(wrist-elbow).normalized();depth=min((p-wrist).dot(axis)for p in points)-.008
  if side not in cuff_planes or depth<cuff_planes[side][2]:cuff_planes[side]=(wrist,axis,depth)
 bm=bmesh.new();bm.from_mesh(o.data);bm.faces.ensure_lookup_table();faces=[f for f in bm.faces if f.index in face_ids];count=len(faces);bmesh.ops.delete(bm,geom=faces,context='FACES_ONLY');bm.to_mesh(o.data);bm.free();removed.append({'mesh':o.name,'faces':count,'selection':'Actual skin RGB plus >30% Hand weights; all clothing retained, candidate-only'})
assert set(cuff_planes)=={'Left','Right'},'Both real owner cuff skin bounds required'
for side,(wrist,axis,depth)in cuff_planes.items():
 assert cloth_near_wrist[side],'Actual sleeve cuff witnesses required'
 lo=min((p-wrist).dot(axis)for p in cloth_near_wrist[side]);hi=max((p-wrist).dot(axis)for p in cloth_near_wrist[side]);cuff_planes[side]=(wrist,axis,depth)
 print('REAL_CUFF_CLOTH_AXIAL_RANGE',side,lo,hi,'MEASURED_CROP',hi-.002,flush=True)

print('OWNER_HAND_FACES_RETIRED',removed,'CUFF_DEPTHS',{k:v[2]for k,v in cuff_planes.items()},flush=True)
encoded_color=tuple(statistics.median(v[i]for v in skin_colors)for i in range(3))if skin_colors else(.69,.54,.46)
def srgb_linear(v):return v/12.92 if v<=.04045 else((v+.055)/1.055)**2.4
color=tuple(srgb_linear(v)for v in encoded_color)
mat=bpy.data.materials.new('Owner-matched skin candidate, procedural microsurface');mat.use_nodes=True;nodes=mat.node_tree.nodes;p=nodes['Principled BSDF'];p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=.48;p.inputs['IOR'].default_value=1.4;p.inputs['Subsurface Weight'].default_value=.1;p.inputs['Subsurface Scale'].default_value=.0008;p.inputs['Subsurface Radius'].default_value=(1,.4,.2)
noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=650;noise.inputs['Detail'].default_value=2;bump=nodes.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.00003;bump.inputs['Strength'].default_value=.15;mat.node_tree.links.new(noise.outputs['Fac'],bump.inputs['Height']);mat.node_tree.links.new(bump.outputs['Normal'],p.inputs['Normal'])
mounts={};mount_offsets={};s.frame_set(1);bpy.context.view_layer.update()
for side,o in source_meshes.items():
 r=newrig.copy();r.data=newrig.data.copy();r.name='Anatomical'+side+'OwnerCandidate';bpy.context.scene.collection.objects.link(r);r.animation_data_create();r.animation_data.action=newaction
 for track in r.animation_data.nla_tracks:track.mute=True
 o.parent=r;o.matrix_parent_inverse=Matrix.Identity(4);o.matrix_basis=Matrix.Identity(4)
 for modifier in o.modifiers:
  if modifier.type=='ARMATURE':modifier.object=r
 o.data.materials.clear();o.data.materials.append(mat);align=handframe(body_rest,side)@handframe(new_rest,side).inverted()
 # Retain genuine hand anatomy, cut only surplus forearm 8mm behind actual owner skin cuff seam.
 wrist,axis,depth=cuff_planes[side]
 # Match genuine forearm axis and wrist center, not mismatched old palm direction.
 # Keep every strongly phalange-weighted vertex; only trim surplus proximal skin.
 inverse=align.inverted();normal_local=(align.to_3x3().transposed()@axis).normalized()
 protected_vertices=[v for v in o.data.vertices if sum(g.weight for g in v.groups if 'Hand'in o.vertex_groups[g.group].name and not o.vertex_groups[g.group].name.endswith('Hand'))>.5]
 finger_min=min(((align@v.co)-wrist).dot(axis)for v in protected_vertices);depth=min(depth,finger_min-.003);mount_offsets[side]={'distal_shift_m':0,'source_forearm_axis_matches_owner':True,'protected_skin_min_before_m':finger_min,'source_finger_anatomy_unchanged':True,'actual_proximal_trim_m':depth}
 print('MEASURED_ANATOMICAL_MOUNT',side,mount_offsets[side],flush=True)
 plane_world=wrist+axis*depth;plane_local=inverse@plane_world;o.data=o.data.copy()
 protected=[v.index for v in o.data.vertices if sum(g.weight for g in v.groups if 'Hand'in o.vertex_groups[g.group].name and not o.vertex_groups[g.group].name.endswith('Hand'))>.5 and (v.co-plane_local).dot(normal_local)<-1e-7]
 print('GENUINE_FINGER_VERTICES_BEHIND_CUFF_CROP',side,len(protected),flush=True)
 assert not protected,'Measured cuff crop would alter actual finger anatomy'
 bm=bmesh.new();bm.from_mesh(o.data);bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=1e-7,plane_co=plane_local,plane_no=normal_local,clear_inner=True,clear_outer=False);bm.to_mesh(o.data);bm.free()
 mounts[side]=(r,align,body_rest['mixamorig:'+side+'Hand'].inverted());r.matrix_world=align
 constraint=r.constraints.new('CHILD_OF');constraint.name='ActualCapturedOwnerHandMount'+side;constraint.target=oldrig;constraint.subtarget='mixamorig:'+side+'Hand';constraint.inverse_matrix=body_rest['mixamorig:'+side+'Hand'].inverted()
# Properly authored replacement cuff from actual original garment boundary.
sys.path.insert(0,str(Path(__file__).parent));from build_anatomical_hoodie_cuffs_blender import fitted_cuff
garment_fit=[];new_cuffs=[];main_cloth=next(o for o in oldmeshes if o.name.startswith('tripo'))
for side,(r,align,inverse_rest)in mounts.items():
 wrist,axis,_=cuff_planes[side];roll=handframe(body_rest,side).to_3x3().col[0]
 cuff,receipt=fitted_cuff(main_cloth,oldrig,source_meshes[side],align,side,wrist,axis,roll);new_cuffs.append(cuff);garment_fit.append(receipt)
print('ACTUAL_NEW_TAILORED_CUFFS',len(new_cuffs),flush=True)
newrig.hide_render=True;newrig.hide_set(True)
for o in bpy.data.objects:
 if o.type=='MESH'and any(o==p.custom_shape for a in[oldrig,*[r[0]for r in mounts.values()]]for p in a.pose.bones):o.hide_render=True
world=bpy.data.worlds.new('Owner candidate studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.13,.14,.16,1);world.node_tree.nodes['Background'].inputs[1].default_value=.35;s.world=world
bpy.ops.object.camera_add();camera=bpy.context.object;s.camera=camera;lights=[]
for energy,size in[(180,3),(80,2)]:bpy.ops.object.light_add(type='AREA');o=bpy.context.object;o.data.energy=energy;o.data.size=size;lights.append(o)
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=24;s.cycles.use_denoising=True;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX';records=[]
bpy.ops.wm.save_as_mainfile(filepath=str(out/'owner-anatomical-hands-candidate.blend'))
for frame in[7,21]:
 s.frame_set(frame);bpy.context.view_layer.update();wrists={}
 for side,(r,align,inverse_rest)in mounts.items():
  current=oldrig.matrix_world@oldrig.pose.bones['mixamorig:'+side+'Hand'].matrix;expected=current@inverse_rest@align;actual=r.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world;error=max(abs(actual[i][j]-expected[i][j])for i in range(4)for j in range(4));assert error<1e-5,('Actual bone mount constraint differs',side,error);wrists[side]=current.translation
 bpy.context.view_layer.update();center=oldrig.matrix_world@oldrig.pose.bones['mixamorig:Hips'].head;target=Vector((center.x,center.y,.95))
 for light,offset in zip(lights,[Vector((-2,-3,4)),Vector((3,2,2))]):light.location=target+offset;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
 views=[('body',target,Vector((2.8,-5,1)),2.2)]
 for side in['Left','Right']:views.append((side.lower()+'-cuff',wrists[side],Vector((.7 if side=='Left'else-.7,-.25,.25)),.38))
 for name,target,direction,scale in views:
  camera.data.type='ORTHO';camera.data.ortho_scale=scale;camera.location=target+direction;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();s.render.resolution_x=750;s.render.resolution_y=950;s.render.resolution_percentage=100;s.render.filepath=str(out/f'owner-{name}-{frame:04}.png');bpy.ops.render.render(write_still=True);records.append({'frame':frame,'view':name,'image':s.render.filepath})
 # True annotated original eye-surface point moved by the existing Head bone.
 eye_reference=Vector((.0111436461,-.1099004381,1.5920442536));head_delta=(oldrig.matrix_world@oldrig.pose.bones['mixamorig:Head'].matrix)@body_rest['mixamorig:Head'].inverted();camera.data.type='PERSP';camera.data.sensor_width=36;camera.data.lens=36/(2*math.tan(math.radians(75)/2));camera.location=head_delta@eye_reference;direction=head_delta.to_quaternion()@Vector((0,-math.cos(math.radians(75)),-math.sin(math.radians(75))));camera.rotation_euler=direction.to_track_quat('-Z','Y').to_euler();s.render.resolution_x=1280;s.render.resolution_y=720;s.render.filepath=str(out/f'owner-first-person-{frame:04}.png');bpy.ops.render.render(write_still=True);records.append({'frame':frame,'view':'first-person inspection75degreesdown','image':s.render.filepath,'eye_source':'Original source annotated iris-surface midpoint transformed by actual Head pose; native camera acceptance not implied'})
bpy.ops.wm.save_as_mainfile(filepath=str(out/'owner-anatomical-hands-candidate.blend'))
report={'owner_sha256':hashlib.sha256(owner.read_bytes()).hexdigest(),'new_hand_clip_sha256':hashlib.sha256(hands_path.read_bytes()).hexdigest(),'candidate_only_removed_old_faces':removed,'skin_color_linear':color,'source_photo_skin_palette_srgb':encoded_color,'original_skin_texture_samples':len(skin_colors),'garment_cuff_fitted_vertices':garment_fit,'garment_fit_is_candidate_only':True,'garment_source_texture_and_weights_preserved':True,'anatomical_mount_offsets':mount_offsets,'anatomical_geometry_scale':1,'forearm_trim_behind_actual_skin_cuff_m':{k:v[2]for k,v in cuff_planes.items()},'genuine_hand_and_nail_geometry_edited':False,'first_person_hands_visible_verified':False,'body_pose_channels_edited':False,'body_captured_wrist_drives_once':True,'new_hand_layer_wrist_tracks_removed_to_avoid_double_application':True,'actual_saved_scene_has_live_owner_hand_constraints':True,'source_original_files_modified':False,'frames':records,'physical_cuff_penetration_verified':False,'native_imported':False,'visual_accepted':False};(out/'composite-report.json').write_text(json.dumps(report,indent=2)+'\n');print('OWNER_CUFF_COMPOSITE_RENDERED',flush=True)
