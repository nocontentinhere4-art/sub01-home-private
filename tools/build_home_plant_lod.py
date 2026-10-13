"""Private plant geometry variant. Run in Blender; no downloads or scene changes.

Blender --background --python tools/build_home_plant_lod.py -- --candidate /ignored/candidate.glb
Then python tools/package_home_plant_lod.py --candidate /ignored/candidate.glb
The package step keeps original non-leaf bytes, materials and image URLs.
"""
import argparse
from pathlib import Path
import sys
import bpy

parser = argparse.ArgumentParser()
parser.add_argument('--candidate', required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
root = Path(__file__).resolve().parents[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(root / 'web/house/assets/potted_plant_01/potted_plant_01.gltf'))
originals = [o for o in bpy.context.scene.objects if o.type == 'MESH']
candidates = []
for original in originals:
    candidate = original.copy()
    candidate.data = original.data.copy()
    candidate.name = 'LOD_' + original.name
    bpy.context.scene.collection.objects.link(candidate)
    candidates.append(candidate)
    if original.name != 'potted_plant_01_leaves':
        continue
    bpy.context.view_layer.objects.active = candidate
    decimate = candidate.modifiers.new('Leaf-only 20 percent topology', 'DECIMATE')
    decimate.decimate_type = 'COLLAPSE'
    decimate.ratio = .20
    decimate.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=decimate.name)
    normals = candidate.modifiers.new('Preserve scanned split normals', 'DATA_TRANSFER')
    normals.object = original
    normals.use_loop_data = True
    normals.data_types_loops = {'CUSTOM_NORMAL'}
    normals.loop_mapping = 'POLYINTERP_NEAREST'
    bpy.ops.object.modifier_apply(modifier=normals.name)
bpy.ops.object.select_all(action='DESELECT')
for candidate in candidates:
    candidate.select_set(True)
path = Path(args.candidate).resolve()
path.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(path), export_format='GLB', use_selection=True)
