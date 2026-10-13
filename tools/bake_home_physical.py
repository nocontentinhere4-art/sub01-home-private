"""Bake immutable physical home inputs, without installation or live changes.

Blender --background --python tools/bake_home_physical.py -- SOURCE ATLAS OUT
  day|night|sky --source-sha SHA --atlas-sha SHA --geometry-proof JSON
  --hdr HDR --hdr-sha SHA [--samples 2048 --threads 4 --receiver ID]
Subset outputs are diagnostic only. OUT must be new or empty. CPU is default;
--device METAL explicitly selects a detected GPU with CPU devices disabled.
"""
import argparse
import json
import sys
import time
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).parent))
from home_physical_recipe import apply_physical_recipe, validate_inputs, sha256
from home_material_grades import apply_browser_material_grades

parser = argparse.ArgumentParser(description=__doc__)
for name in ('source', 'atlas', 'output'):
    parser.add_argument(name, type=Path)
parser.add_argument('mode', choices=('day', 'night', 'sky'))
for name in ('source-sha', 'atlas-sha', 'hdr-sha'):
    parser.add_argument('--' + name, required=True)
parser.add_argument('--geometry-proof', type=Path, required=True)
parser.add_argument('--hdr', type=Path, required=True)
parser.add_argument('--samples', type=int, default=2048)
parser.add_argument('--threads', type=int, default=4)
parser.add_argument('--seed', type=int, default=0)
parser.add_argument('--receiver', action='append', default=[])
parser.add_argument('--device', choices=('CPU', 'METAL'), default='CPU')
options = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
if not 1 <= options.samples <= 4096 or not 1 <= options.threads <= 32:
    parser.error('Samples must be 1..4096 and threads 1..32')
inputs = validate_inputs(options.source, options.atlas, options.source_sha,
                         options.atlas_sha, options.geometry_proof)
if sha256(options.hdr) != options.hdr_sha:
    parser.error('Immutable HDR SHA mismatch')
if options.output.exists() and any(options.output.iterdir()):
    parser.error('Refusing to overwrite an existing bake output')
started = time.monotonic()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(options.source))
apply_browser_material_grades()
scene = bpy.context.scene
originals = {}
for obj in scene.objects:
    key = obj.get('bakeId')
    if key:
        if key in originals:
            raise ValueError('Duplicate source receiver ID: ' + key)
        originals[key] = obj
before = set(scene.objects)
bpy.ops.import_scene.gltf(filepath=str(options.atlas))
receivers = [obj for obj in scene.objects if obj not in before and obj.type == 'MESH']
if len(receivers) != inputs['receivers']:
    raise ValueError('Imported atlas receiver count mismatch')
by_id = {}
for obj in receivers:
    key = obj.get('bakeId') or obj.name
    if key in by_id or key not in originals:
        raise ValueError('Duplicate or missing source receiver: ' + key)
    old = originals[key]
    obj.data.materials.clear()
    for material in old.data.materials:
        obj.data.materials.append(material.copy())
    old.hide_render = True
    if len(obj.data.uv_layers) != 2:
        raise ValueError('Receiver needs exact original and atlas UVs: ' + key)
    obj.data.uv_layers.active_index = 1
    by_id[key] = obj
if set(options.receiver) - by_id.keys():
    raise ValueError('Unknown requested receiver ID')
selected = [by_id[key] for key in dict.fromkeys(options.receiver)] if options.receiver else receivers
recipe = apply_physical_recipe(bpy, scene,
    mode='night' if options.mode == 'night' else 'day', world_only=options.mode == 'sky',
    hdr_path=options.hdr, hdr_sha256=options.hdr_sha)
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
gpu_names = []
if options.device == 'METAL':
    preferences = bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type = 'METAL'
    preferences.get_devices()
    for device in preferences.devices:
        device.use = device.type == 'METAL'
        if device.use:
            gpu_names.append(device.name)
    if not gpu_names:
        raise ValueError('No Metal GPU detected; no silent CPU fallback')
    scene.cycles.device = 'GPU'
scene.cycles.samples = options.samples
scene.cycles.seed = options.seed
scene.cycles.use_animated_seed = False
scene.cycles.use_adaptive_sampling = False
scene.cycles.use_denoising = False
scene.cycles.max_bounces = 5
scene.cycles.diffuse_bounces = 4
scene.render.threads_mode = 'FIXED'
scene.render.threads = options.threads
image = bpy.data.images.new('Physical home radiance', inputs['width'], inputs['height'],
                            alpha=False, float_buffer=True)
image.colorspace_settings.name = 'Non-Color'
for obj in selected:
    for material in obj.data.materials:
        material.use_nodes = True
        node = material.node_tree.nodes.new('ShaderNodeTexImage')
        node.image = image
        material.node_tree.nodes.active = node
bpy.ops.object.select_all(action='DESELECT')
for obj in selected:
    obj.select_set(True)
bpy.context.view_layer.objects.active = selected[0]
scene.render.bake.use_pass_direct = options.mode == 'sky'
scene.render.bake.use_pass_indirect = options.mode != 'sky'
scene.render.bake.use_pass_color = False
scene.render.bake.use_clear = False
scene.render.bake.margin = 6
record = dict(inputs, mode='day' if options.mode == 'sky' else options.mode,
    component=options.mode, samples=options.samples, threads=options.threads,
    seed=options.seed, adaptive_sampling=False, denoising=False,
    device=options.device, gpu_names=gpu_names,
    direct=options.mode == 'sky', indirect=options.mode != 'sky', surface_albedo=False,
    world_only=options.mode == 'sky', emissive_materials_disabled=options.mode != 'night',
    diagnostic_only=bool(options.receiver), written_receiver_ids=[obj.get('bakeId') or obj.name for obj in selected],
    source_receiver_count=len(receivers), bake_margin=6, atlas_padding=3,
    all_other_receivers_remain_visible=True, preparation=recipe,
    geometry_proof_sha256=sha256(options.geometry_proof),
    source_recipe_sha256=sha256(__file__),
    preparation_recipe_sha256=sha256(Path(__file__).with_name('home_physical_recipe.py')),
    material_grades_sha256=sha256(Path(__file__).with_name('home_material_grades.py')),
    finished=False)
options.output.mkdir(parents=True, exist_ok=True)
manifest = options.output / 'bake.json'
manifest.write_text(json.dumps(record, indent=2) + '\n')
print('PHYSICAL_BAKE_START', len(selected), options.mode, options.device, flush=True)
bpy.ops.object.bake(type='DIFFUSE')
image.filepath_raw = str(options.output / 'indirect.exr')
image.file_format = 'OPEN_EXR'
image.save()
if sha256(options.source) != options.source_sha or sha256(options.atlas) != options.atlas_sha or sha256(options.hdr) != options.hdr_sha:
    raise ValueError('Input changed during bake; output not marked finished')
record.update(finished=True, elapsed_seconds=time.monotonic() - started,
              output_sha256=sha256(options.output / 'indirect.exr'))
manifest.write_text(json.dumps(record, indent=2) + '\n')
print('PHYSICAL_BAKE_DONE', options.output, flush=True)
