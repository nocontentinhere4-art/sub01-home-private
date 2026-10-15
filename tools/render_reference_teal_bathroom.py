"""Read-only source review in Blender; not a native Game or lighting claim."""
from pathlib import Path
import argparse,sys
import bpy
from mathutils import Vector

parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,required=True);args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);ROOT=args.source_root
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'teal-bathroom.blend'))
before=set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath='/workspace/sub01-home-private/bathroom-corridor-source-r1/bath-corridor.glb')
# Actual current floor and building architecture; door and fixture leftovers
# from the old home are excluded from this authoring review.
for o in list(bpy.data.objects):
 if o not in before and (o.type!='MESH' or o.name not in ('SUB01_BathCorridor_SourceNode_117','SUB01_BathCorridor_SourceNode_158')):
  bpy.data.objects.remove(o,do_unlink=True)
# Original shower pan remains unchanged in the functioning home.
before=set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath='/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
for o in list(bpy.data.objects):
 if o not in before and (o.type!='MESH' or o.name!='house-static-61'):
  bpy.data.objects.remove(o,do_unlink=True)
for m in bpy.data.materials:
 if m.name.startswith('Clear glass') and m.use_nodes:
  s=m.node_tree.nodes.get('Principled BSDF')
  if s:s.inputs['Transmission Weight'].default_value=1;s.inputs['Roughness'].default_value=.045
bpy.ops.object.camera_add(location=(-1.55,-.78,4.62))
camera=bpy.context.object;target=Vector((-3.48,-1.66,4.12))
camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=22;bpy.context.scene.camera=camera
world=bpy.context.scene.world or bpy.data.worlds.new('Neutral authoring environment');bpy.context.scene.world=world;world.use_nodes=True
world.node_tree.nodes['Background'].inputs[0].default_value=(.45,.49,.56,1);world.node_tree.nodes['Background'].inputs[1].default_value=.24
for label,loc,target,power,size,color in [('Bathroom softbox',(-2,-1.2,5.65),(-3.3,-1.55,3.9),170,1.5,(1,.88,.73)),('Vanity fill',(-1.3,-.72,4.8),(-3.75,-1.1,4.4),75,1.2,(1,.95,.88))]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.name=label;l.visible_glossy=False;l.data.energy=power;l.data.shape='DISK';l.data.size=size;l.data.color=color;l.rotation_euler=(Vector(target)-l.location).to_track_quat('-Z','Y').to_euler()
s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=24;s.cycles.use_denoising=True
s.render.resolution_x=1100;s.render.resolution_y=900;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG'
s.render.filepath=str(ROOT/'teal-bathroom-source-review.png');s.view_settings.view_transform='AgX';bpy.ops.render.render(write_still=True)
