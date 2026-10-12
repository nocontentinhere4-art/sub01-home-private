"""Create an editable Blender scene from the actual private browser-house export.
Run: Blender --background --python this_file -- source.glb output.blend
The browser source remains authoritative until exported furniture is integrated.
"""
import sys
from pathlib import Path
import bpy
from mathutils import Vector
source, destination = map(Path,sys.argv[sys.argv.index('--')+1:])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source.resolve()))
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.unit_settings.scale_length=1
scene.render.engine='CYCLES'
scene.cycles.samples=32
scene.render.resolution_x=1600
scene.render.resolution_y=900
scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Home ambient')
scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.15,.18,.21,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.15
bpy.ops.object.camera_add(location=(-1.2,1.64,4.65))
camera=bpy.context.object
camera.name='Bedroom comparison camera'
camera.rotation_euler=(Vector((-2.4,2.35,3.65))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.lens=28
scene.camera=camera
text=bpy.data.texts.new('SUB-01 furniture references')
text.write('''PRIVATE LOCAL SUB-01 HOME\nEditable scene imported from the functioning browser house.\nThe browser source is still authoritative; furniture must be exported as GLB and integrated with existing collision and device controls.\n\nModern oak platform-bed reference:\nhttps://www.muji.eu/products/double-platform-bed-frame-oak-18913\nReference only: original modeled geometry, no manufacturer model included.\n\nExisting scanned furniture and materials:\nhttps://polyhaven.com/models/furniture (CC0; individual provenance is in web/house/assets/manifest.json)\n\nKeep the bedroom comparison camera for before/after validation.\nDo not deploy this work or publish the private scene.\n''')
bpy.ops.file.pack_all()
destination.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(destination.resolve()))
print('EDITABLE_HOME_SAVED',destination.resolve(),flush=True)
