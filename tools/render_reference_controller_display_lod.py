"""Private source lit front/side review; not an actual native hand/contact verdict."""
import bpy
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/reference-controller-r11/output')
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(ROOT/'controller-r11-display-lod.glb'))
bpy.ops.object.camera_add(location=(0,-.16,.32));camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=.205;camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler();bpy.context.scene.camera=camera
world=bpy.data.worlds.new('Neutral source review');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.28,.30,.33,1);world.node_tree.nodes['Background'].inputs[1].default_value=.22;bpy.context.scene.world=world
for loc,energy,size in[((-.12,-.09,.20),1.6,.16),((.16,.08,.13),.7,.14)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=energy;l.data.shape='DISK';l.data.size=size;l.rotation_euler=(Vector((0,0,0))-l.location).to_track_quat('-Z','Y').to_euler()
s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=24;s.cycles.use_denoising=True;s.render.resolution_x=1200;s.render.resolution_y=900;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX'
for name,loc in [('front',(0,-.16,.32)),('side',(.24,-.14,.10))]:
 camera.location=loc;camera.rotation_euler=(Vector((0,0,0))-camera.location).to_track_quat('-Z','Y').to_euler();s.render.filepath=str(ROOT/f'controller-r11-display-lod-{name}.png');bpy.ops.render.render(write_still=True)
