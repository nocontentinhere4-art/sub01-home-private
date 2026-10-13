"""SERVER ONLY: convert merged owned skin/fitted sit captures to animation-only FBX.
No render, rig edits, finger edits, root-motion removal or runtime seat acceptance.
Prepare merged source with existing uncompress_unreal_glb.mjs + merge_unreal_skin_clips.mjs.
Run: blender -b --python tools/export_unreal_seating_fbx.py -- MERGED.glb OUTPUT_DIRECTORY
"""
import bpy,hashlib,json,math,sys
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);out=Path(args[1]);out.mkdir(parents=True,exist_ok=True)
raw=source.read_bytes();doc=json.loads(raw[20:20+int.from_bytes(raw[12:16],'little')])
roles={'SitDown':'room_mx_stand_to_sit','GetUp':'room_mx_sit_to_stand','Sitting':'room_mx_sitting','SitToType':'room_mx_sit_to_type'}
expected_bones={doc['nodes'][i]['name']for i in doc['skins'][0]['joints']}
if len(expected_bones)!=65:raise RuntimeError('Actual owner65joint contract changed')
expected={a['name']:max(doc['accessors'][s['input']]['max'][0]for s in a['samplers'])for a in doc['animations']}
if set(expected)!=set(roles.values()):raise RuntimeError('Expected exactly four real seating captures, no substituted clip')
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=30
bpy.ops.import_scene.gltf(filepath=str(source.resolve()))
arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
if len(arms)!=1:raise RuntimeError('Expected one actual source armature')
arm=arms[0]
if set(b.name for b in arm.data.bones)!=expected_bones:raise RuntimeError('Imported bone names differ; do not retarget silently')
for track in arm.animation_data.nla_tracks:track.mute=True
for obj in bpy.context.scene.objects:obj.select_set(obj==arm)
bpy.context.view_layer.objects.active=arm
rows=[]
for role,name in roles.items():
 actions=[a for a in bpy.data.actions if a.name==name or a.name.startswith(name+'.')]
 if len(actions)!=1:raise RuntimeError('Ambiguous source seating action '+name)
 action=actions[0];arm.animation_data.action=action;start,end=action.frame_range
 if abs((end-start)/30-expected[name])>1e-4:raise RuntimeError('Actual captured duration changed')
 bpy.context.scene.frame_start=math.floor(start);bpy.context.scene.frame_end=math.ceil(end);bpy.context.scene.frame_set(math.floor(start))
 path=out/(role+'.fbx')
 bpy.ops.export_scene.fbx(filepath=str(path.resolve()),use_selection=True,object_types={'ARMATURE'},add_leaf_bones=False,use_armature_deform_only=False,apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0,bake_anim_step=1)
 rows.append({'role':role,'source_action':name,'duration_s':expected[name],'source_frame_range':[start,end],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'file':path.name})
(out/'seating-fbx-audit.json').write_text(json.dumps({'source_sha256':hashlib.sha256(raw).hexdigest(),'bone_names':sorted(expected_bones),'clips':rows,'bone_edits':False,'fps':30,'blender':bpy.app.version_string,'physical_seat_contact_verified':False,'runtime_ready':False},indent=2)+'\n')
