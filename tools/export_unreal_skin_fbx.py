"""Server-only format fallback for authentic source rig/clips, no retarget edits."""
import bpy,json,sys,hashlib,math
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);out=Path(args[1]);out.mkdir(parents=True,exist_ok=True)
raw=source.read_bytes();doc=json.loads(raw[20:20+int.from_bytes(raw[12:16],'little')])
source_duration={a['name']:max(doc['accessors'][s['input']]['max'][0]for s in a['samplers'])for a in doc['animations']}
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps=30
bpy.ops.import_scene.gltf(filepath=str(source))
arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'and any(m.type=='ARMATURE' for m in o.modifiers)]
if len(arms)!=1 or len(meshes)!=5:raise RuntimeError('Expected actual single source rig and nonempty mesh objects')
arm=arms[0]
if len(arm.data.bones)!=65:raise RuntimeError('Source65joint owner changed during format import')
if any(not len(o.data.vertices) for o in meshes):raise RuntimeError('Empty actual source mesh')
rows=[{'name':o.name,'vertices':len(o.data.vertices),'polygons':len(o.data.polygons)}for o in meshes]
bpy.context.scene.render.fps=30
for o in bpy.context.scene.objects:o.select_set(o in [arm,*meshes])
bpy.context.view_layer.objects.active=arm
for track in arm.animation_data.nla_tracks:track.mute=True
arm.animation_data.action=None
common=dict(use_selection=True,object_types={'ARMATURE','MESH'},add_leaf_bones=False,use_armature_deform_only=False,apply_unit_scale=True,axis_forward='-Z',axis_up='Y',path_mode='COPY',embed_textures=True)
bpy.ops.export_scene.fbx(filepath=str(out/'owner.fbx'),bake_anim=False,**common)
# Animation-only FBX avoids evaluating300K skin vertices for every captured frame.
# Owner geometry/materials are already exported once; animation retains same rig.
for o in bpy.context.scene.objects:o.select_set(o==arm)
clips=[]
for role in ['typing','texting','walking']:
 actions=[a for a in bpy.data.actions if role in a.name.lower()]
 if len(actions)!=1:raise RuntimeError('Ambiguous authentic source capture '+role+': '+repr([a.name for a in actions]))
 action=actions[0];arm.animation_data.action=action
 start,end=action.frame_range
 if abs((end-start)/30-source_duration[role])>1e-4:raise RuntimeError('Captured duration changed in format conversion '+role)
 bpy.context.scene.frame_start=math.floor(start);bpy.context.scene.frame_end=math.ceil(end)
 bpy.context.scene.frame_set(math.floor(start));path=out/(role+'.fbx')
 bpy.ops.export_scene.fbx(filepath=str(path),bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0,bake_anim_step=1,**common)
 clips.append({'role':role,'action':action.name,'source_frames':[start,end],'export_frames':[math.floor(start),math.ceil(end)],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'blender':bpy.app.version_string,'fps':30,'bones':len(arm.data.bones),'meshes':rows,'clips':clips,'owner_fbx_sha256':hashlib.sha256((out/'owner.fbx').read_bytes()).hexdigest(),'scope':'Format conversion from original T-reference source; no custom finger/bone deformation, no contact/POV acceptance. FBX channel resampling at original30fps must be checked after actual UE import.'}
(out/'fbx-source-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('SUB01_ACTUAL_FBX_SOURCE_EXPORTED',json.dumps(report))
