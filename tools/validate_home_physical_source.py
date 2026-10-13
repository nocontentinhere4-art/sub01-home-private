"""Blender dry-run: import/prepare actual immutable inputs, validate, never bake.

Blender --background --python tools/validate_home_physical_source.py --
  source.glb atlas.glb report.json --source-sha SHA --atlas-sha SHA
  --geometry-proof proof.json --hdr room-light.hdr --hdr-sha SHA
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from home_physical_recipe import apply_physical_recipe, validate_inputs, sha256

def mesh_digest(scene):
    digest = hashlib.sha256()
    count = 0
    for obj in sorted((o for o in scene.objects if o.type == 'MESH'), key=lambda o: o.name):
        digest.update(obj.name.encode())
        digest.update(np.asarray(obj.matrix_world, dtype=np.float64).tobytes())
        for collection, field, width, dtype in [(obj.data.vertices, 'co', 3, np.float32), (obj.data.loops, 'vertex_index', 1, np.int32)]:
            values = np.empty(len(collection) * width, dtype=dtype)
            collection.foreach_get(field, values)
            digest.update(values.tobytes())
        for layer in obj.data.uv_layers:
            values = np.empty(len(layer.data) * 2, dtype=np.float32)
            layer.data.foreach_get('uv', values)
            digest.update(values.tobytes())
        count += 1
    return {'meshes': count, 'local_vertices_indexed_loops_uv_world_transforms_sha256': digest.hexdigest()}

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('atlas', type=Path)
parser.add_argument('report', type=Path)
parser.add_argument('--source-sha', required=True)
parser.add_argument('--atlas-sha', required=True)
parser.add_argument('--geometry-proof', type=Path, required=True)
parser.add_argument('--hdr', type=Path, required=True)
parser.add_argument('--hdr-sha', required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
inputs = validate_inputs(args.source, args.atlas, args.source_sha, args.atlas_sha, args.geometry_proof)
reports = []
for mode, world_only in [('day', False), ('night', False), ('day', True)]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.source))
    scene = bpy.context.scene
    before = mesh_digest(scene)
    recipe = apply_physical_recipe(bpy, scene, mode=mode, world_only=world_only, hdr_path=args.hdr, hdr_sha256=args.hdr_sha)
    after = mesh_digest(scene)
    assert before == after, 'Physical preparation changed source geometry/UVs/transforms'
    emitted = []
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        for node in material.node_tree.nodes:
            socket = node.inputs.get('Emission Strength') if node.type == 'BSDF_PRINCIPLED' else node.inputs.get('Strength') if node.type == 'EMISSION' else None
            if socket is not None and (socket.is_linked or socket.default_value > 0):
                emitted.append(material.name)
                assert mode == 'night' and not world_only and material.get('lampEmission', 0) > 0
    assert len(emitted) == len(recipe['enabled_fixtures'])
    assert {light['type'] for light in recipe['lights']} <= (set() if world_only else {'SUN'} if mode == 'day' else {'POINT', 'SPOT'})
    try:
        apply_physical_recipe(bpy, scene, mode=mode, world_only=world_only, hdr_path=args.hdr, hdr_sha256=args.hdr_sha)
        raise AssertionError('Double import-energy conversion was accepted')
    except ValueError:
        pass
    reports.append({'recipe': recipe, 'geometry_unchanged': before, 'actually_emitting_materials': emitted})
assert sha256(args.source) == args.source_sha and sha256(args.atlas) == args.atlas_sha
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps({'inputs': inputs, 'dry_run_only': True, 'bakes_executed': 0, 'cases': reports}, indent=2) + '\n')
print('PHYSICAL_SOURCE_VALIDATED', args.report, flush=True)
