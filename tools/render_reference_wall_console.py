"""Actual source-only lit assembly review with preserved TV/cabinet geometry."""
import bpy,math,json
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/reference-wall-console-r1/output')
bpy.ops.wm.read_factory_settings(use_empty=True)
# Reuse exact original cabinet meshes, omitting the six retired separate device materials.
with bpy.data.libraries.load('/workspace/sub01-home-private/real-media-console-source-r1/output/media-console-side.blend',link=False)as(src,dst):dst.objects=src.objects
for o in dst.objects:
 if o is None:continue
 if o.type=='MESH' and any(m and(m.name.startswith('Console ')or m.name=='controller')for m in o.data.materials):continue
 bpy.context.scene.collection.objects.link(o)
bpy.ops.import_scene.gltf(filepath='/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
bpy.ops.import_scene.gltf(filepath=str(ROOT/'wall-console.glb'))
bpy.ops.object.camera_add(location=(-.82,.20,1.65));camera=bpy.context.object;target=Vector((-3.8,.17,1.40));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=36;bpy.context.scene.camera=camera
world=bpy.context.scene.world or bpy.data.worlds.new('Neutral private review lighting');bpy.context.scene.world=world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.35,.39,.45,1);world.node_tree.nodes['Background'].inputs[1].default_value=.3
for name,loc,power,size in [('Soft daylight',(-1.5,-3.4,2.6),450,2),('Warm bounce',(-1.2,1.8,2.3),170,2)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.name=name;l.data.energy=power;l.data.shape='DISK';l.data.size=size;l.rotation_euler=(Vector((-3.6,-.3,1.3))-l.location).to_track_quat('-Z','Y').to_euler()
s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=24;s.cycles.use_denoising=True;s.render.resolution_x=1400;s.render.resolution_y=1000;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.render.filepath=str(ROOT/'wall-console-source-review.png');s.view_settings.view_transform='AgX';bpy.ops.render.render(write_still=True)
