"""GPU-server evidence capture of the real assembled house, not UE runtime.

blender --background --python tools/render_home_server.py -- \
  --source out/home114-assembled/house.blend \
  --hdr web/house/assets/lighting/room-light.hdr \
  --exterior web/house/assets/tokyo-residential/residential-4096.webp \
  --output-dir out/house-evidence
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path


def main():
    import bpy
    from mathutils import Vector
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--hdr', type=Path, required=True)
    parser.add_argument('--exterior', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=64)
    parser.add_argument('--width', type=int, default=1280)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if not all(p.is_file() for p in (args.source, args.hdr, args.exterior)):
        raise RuntimeError('Actual assembled scene and actual room HDR are required')
    bpy.ops.wm.open_mainfile(filepath=str(args.source.resolve()))
    scene = bpy.context.scene
    if not scene.get('privateOnly'):
        raise RuntimeError('Expected private assembled house, not a substitute scene')
    scene.render.engine = 'CYCLES'
    preferences = bpy.context.preferences.addons['cycles'].preferences
    gpu = []
    for backend in ('OPTIX', 'CUDA'):
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
            gpu = [d for d in preferences.devices if d.type == backend]
            if gpu:
                break
        except (TypeError, RuntimeError):
            pass
    if not gpu:
        raise RuntimeError('No server CUDA/OptiX GPU; refusing a slow CPU render')
    for device in preferences.devices:
        device.use = device in gpu
    scene.cycles.device = 'GPU'
    scene.cycles.samples = args.samples
    # Ubuntu's server Blender may lack OpenImageDenoiser. Capture the actual
    # sampled result rather than failing after rendering or hiding defects.
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = .035
    scene.cycles.max_bounces = 6
    scene.cycles.diffuse_bounces = 4
    scene.render.resolution_x = args.width
    scene.render.resolution_y = round(args.width * 9 / 16)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = 0
    scene.world = bpy.data.worlds.new('Actual SUB01 room HDR daylight')
    scene.world.use_nodes = True
    nodes = scene.world.node_tree.nodes
    environment = nodes.new('ShaderNodeTexEnvironment')
    environment.image = bpy.data.images.load(str(args.hdr.resolve()))
    scene.world.node_tree.links.new(environment.outputs['Color'], nodes['Background'].inputs['Color'])
    nodes['Background'].inputs['Strength'].default_value = .65
    # Interior room HDR is an illumination/reflection probe, not outdoors.
    # Camera/transmission rays use the SAME licensed historical Tokyo capture
    # as the functioning house. This photograph adds no invented lighting/fill.
    links = scene.world.node_tree.links
    exterior = nodes.new('ShaderNodeTexEnvironment')
    exterior.image = bpy.data.images.load(str(args.exterior.resolve()))
    exterior.image.colorspace_settings.name = 'sRGB'
    photographed_background = nodes.new('ShaderNodeBackground')
    photographed_background.inputs['Strength'].default_value = 1
    links.new(exterior.outputs['Color'], photographed_background.inputs['Color'])
    rays = nodes.new('ShaderNodeLightPath')
    visible = nodes.new('ShaderNodeMath')
    visible.operation = 'MAXIMUM'
    links.new(rays.outputs['Is Camera Ray'], visible.inputs[0])
    links.new(rays.outputs['Is Transmission Ray'], visible.inputs[1])
    background_mix = nodes.new('ShaderNodeMixShader')
    links.new(visible.outputs[0], background_mix.inputs[0])
    links.new(nodes['Background'].outputs[0], background_mix.inputs[1])
    links.new(photographed_background.outputs[0], background_mix.inputs[2])
    links.new(background_mix.outputs[0], nodes['World Output'].inputs['Surface'])
    # Recreate browser noon sun in correct glTF -> Blender coordinates.
    # Preserve fixture geometry/materials; do not replace room with a generated set.
    for obj in list(scene.objects):
        if obj.type == 'LIGHT' and obj.data.type == 'SUN':
            bpy.data.objects.remove(obj, do_unlink=True)
    data = bpy.data.lights.new('SUB01 noon window sun', 'SUN')
    data.energy = 2.3
    data.angle = math.radians(3)
    data.color = (1, .88, .72)
    sun = bpy.data.objects.new(data.name, data)
    scene.collection.objects.link(sun)
    sun.location = (0, -12, 18)
    sun.rotation_euler = (-sun.location).to_track_quat('-Z', 'Y').to_euler()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    views = [
        ('entrance-living', (.65, -3.2, 1.65), (-2.6, -.15, 1.1)),
        ('kitchen-desk', (1.25, 2.05, 1.65), (-.2, 3.35, 1.05)),
        ('loft-bedroom', (-.65, 1.35, 4.65), (-2.4, 2.35, 3.55)),
    ]
    results = []
    for name, position, target in views:
        bpy.ops.object.camera_add(location=position)
        camera = bpy.context.object
        camera.name = 'Evidence ' + name
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.lens = 21 if name == 'kitchen-desk' else 25
        camera.data.clip_start = .06
        scene.camera = camera
        scene.render.filepath = str((args.output_dir / (name + '.png')).resolve())
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        results.append({'view': name, 'camera_blender_m': position,
                        'target_blender_m': target, 'eye_above_floor_m': 1.65,
                        'seconds': time.monotonic() - start, 'png': scene.render.filepath})
    report = {'source': str(args.source), 'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'hdr': str(args.hdr), 'hdr_sha256': hashlib.sha256(args.hdr.read_bytes()).hexdigest(),
              'exterior': str(args.exterior),
              'exterior_scope': 'Actual runtime historical static Tokyo panorama; not 3D city geometry or live capture. CC BY2 attribution: web/house/assets/tokyo-residential/manifest.json.',
              'fixtures': [{'name': o.name, 'type': o.data.type, 'energy': o.data.energy,
                            'position_blender_m': list(o.matrix_world.translation)}
                           for o in scene.objects if o.type == 'LIGHT'],
              'gpu': [d.name for d in gpu], 'samples': args.samples,
              'scope': 'Actual assembled Blender geometry/material snapshots; not UE runtime, not functional-device proof.',
              'coordinate_contract': 'Blender=(browser x,-browser z,browser y)', 'views': results}
    (args.output_dir / 'capture.json').write_text(json.dumps(report, indent=2) + '\n')
    print('HOME_SERVER_CAPTURE', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
