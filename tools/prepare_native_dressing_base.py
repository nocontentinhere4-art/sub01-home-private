"""Create a private editable dressing baseline from the actual native GLB.

Run only on the authorized server with Blender. This saves an authoring copy;
it never exports or replaces the Unreal house, devices, materials or collisions.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def main():
    import bpy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    source = args.source.resolve(strict=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != args.source_sha256:
        raise RuntimeError('Actual native source changed; inspect before authoring')
    if args.output.resolve() == source:
        raise RuntimeError('Authoring output cannot replace the native source')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    if not meshes:
        raise RuntimeError('Actual native source contains no mesh objects')
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1
    scene['privateOnly'] = True
    scene['sub01NativeSourceSha256'] = digest
    scene['sub01AuthoringBasis'] = 'Exact current native GLB; additive dressing only'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output.resolve()))
    report = {
        'schema': 'sub01.native-dressing-base.v1', 'source_sha256': digest,
        'mesh_objects': len(meshes), 'vertices': sum(len(obj.data.vertices) for obj in meshes),
        'output': str(args.output.resolve()), 'native_house_replaced': False,
        'rendered': False,
    }
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print('SUB01_NATIVE_DRESSING_BASE ' + json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
