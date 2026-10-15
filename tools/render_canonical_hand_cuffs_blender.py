"""Canonical original body bind-space cuff review, not actual native motion."""
import bpy,json,sys
from pathlib import Path
from mathutils import Vector
R=Path('/workspace/sub01-home-private/human-base-hands-r1/canonical-hand-cuffs-r1');source=Path(sys.argv[sys.argv.index('--')+1])if '--'in sys.argv else R/'canonical-anatomical-hand-cuffs.blend';bpy.ops.wm.open_mainfile(filepath=str(source));s=bpy.context.scene;out=source.parent/'canonical-body-review';out.mkdir(exist_ok=True)
for o in s.objects:
 if o.type=='MESH':o.hide_render=not(o.name.startswith('CC0Adult_')or o.name.startswith('AnatomicalFittedHoodieCuff')or o.name=='EXACT_SERIALIZED_ORIGINAL_BODY_BIND_REFERENCE')
w=bpy.data.worlds.new('Bind source studio');w.use_nodes=True;w.node_tree.nodes['Background'].inputs[0].default_value=(.15,.17,.2,1);w.node_tree.nodes['Background'].inputs[1].default_value=.4;s.world=w
bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=1.2;s.camera=camera;target=Vector((0,-.02,1.04));camera.location=target+Vector((0,-2,.4));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
for power,offset in[(180,(-.8,-1.1,1)),(80,(.9,.7,.7))]:bpy.ops.object.light_add(type='AREA');light=bpy.context.object;light.data.energy=power;light.data.size=1.8;light.location=target+Vector(offset);light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=16;s.cycles.use_denoising=True;s.render.resolution_x=1200;s.render.resolution_y=900;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX';s.render.filepath=str(out/'actual-canonical-owner-upperbody-cuffs.png');bpy.ops.render.render(write_still=True)
print('ACTUAL_CANONICAL_BODY_CUFF_REVIEW_RENDERED',flush=True)
