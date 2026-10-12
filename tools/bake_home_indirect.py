"""Bake actual diffuse light bounces with Blender Cycles, offline and CPU-only.

Run with Blender --background --python this_file -- source.glb atlas.glb output_dir
[day|night] --samples 128 --threads 4 --seed 0.
The atlas is prepared by prepare_home_lightmap.py; moving devices keep live lighting.
"""
import json
import sys
import argparse
import hashlib
import time
from pathlib import Path

import bpy
from mathutils import Vector

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source',type=Path)
parser.add_argument('atlas',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('mode',nargs='?',choices=['day','night'],default='day')
parser.add_argument('--samples',type=int,default=128)
parser.add_argument('--threads',type=int,default=4)
parser.add_argument('--seed',type=int,default=0)
options=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
if not 1 <= options.samples <= 4096 or not 1 <= options.threads <= 32:
    parser.error('Use 1..4096 samples and 1..32 CPU threads')
source,atlas,output=options.source,options.atlas,options.output
mode=options.mode
started=time.monotonic()
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
sys.path.insert(0, str(Path(__file__).parent))
from home_material_grades import apply_browser_material_grades
print('OAK_MATERIALS_GRADED', apply_browser_material_grades(), flush=True)
original = {o.get("bakeId"): o for o in bpy.context.scene.objects if o.get("bakeId")}
before = set(bpy.context.scene.objects)
bpy.ops.import_scene.gltf(filepath=str(atlas))
receivers = [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"]
assert receivers, "No atlas receivers"
for obj in receivers:
    old = original.get(obj.get("bakeId") or obj.name)
    assert old, f"No source geometry for {obj.name}"
    obj.data.materials.clear()
    for material in old.data.materials:
        obj.data.materials.append(material.copy())
    old.hide_render = True
    assert len(obj.data.uv_layers) == 2
    obj.data.uv_layers.active_index = 1

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = options.samples
scene.cycles.seed = options.seed
scene.cycles.use_animated_seed = False
scene.cycles.use_adaptive_sampling = False
scene.cycles.max_bounces = 5
scene.cycles.diffuse_bounces = 4
scene.cycles.use_denoising = False
scene.render.threads_mode = "FIXED"
scene.render.threads = options.threads
scene.world = bpy.data.worlds.new("Private home ambient sky")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.76, 0.84, 1.0, 1)
scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12 if mode == "day" else 0
# Remove the moving direct sunlight and fixtures: runtime still renders those.
for obj in list(scene.objects):
    if obj.type == "LIGHT" and (mode == "day" or obj.data.type == "SUN"):
        bpy.data.objects.remove(obj, do_unlink=True)

def window_light(name, position, target, width, height):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = 180
    data.shape = "RECTANGLE"
    data.size, data.size_y = width, height
    data.color = (1.0, 0.93, 0.82)
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = position
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

if mode == "day":
    for i, z in enumerate((-2.6, 0, 2.6)):
        window_light(f"West window {i}", (-3.84, 1.65, z), (0, 1.65, z), 2.35, 1.9)
    window_light("Front window", (0, 1.65, 3.84), (0, 1.65, 0), 2.5, 1.9)
    window_light("Loft balcony", (-2.1, 4.4, 3.84), (-2.1, 4.4, 0), 3.3, 2.2)

# glTF metadata records the real rectangular atlas size.
raw = atlas.read_bytes()
meta = json.loads(raw[20:20 + int.from_bytes(raw[12:16], "little")])
width, height = meta["extras"]["width"], meta["extras"]["height"]
image = bpy.data.images.new("Home indirect irradiance", width, height, alpha=False, float_buffer=True)
image.colorspace_settings.name = "Non-Color"
for obj in receivers:
    for material in obj.data.materials:
        material.use_nodes = True
        node = material.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        material.node_tree.nodes.active = node
bpy.ops.object.select_all(action="DESELECT")
for obj in receivers:
    obj.select_set(True)
bpy.context.view_layer.objects.active = receivers[0]
scene.render.bake.use_pass_direct = False
scene.render.bake.use_pass_indirect = True
scene.render.bake.use_pass_color = False
scene.render.bake.use_clear = False
scene.render.bake.margin = 6
record={'mode':mode,'samples':scene.cycles.samples,'threads':scene.render.threads,
        'seed':scene.cycles.seed,'adaptive_sampling':scene.cycles.use_adaptive_sampling,
        'denoising':scene.cycles.use_denoising,'receivers':len(receivers),'width':width,'height':height,
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'atlas_sha256':hashlib.sha256(atlas.read_bytes()).hexdigest(),
        'direct':False,'indirect':True,'surface_albedo':False,'finished':False,
        'kind':'Cycles diffuse indirect white-receiver outgoing radiance; runtime PI conversion unchanged'}
(output/'bake.json').write_text(json.dumps(record,indent=2)+'\n')
print(f"BAKE_START {len(receivers)} meshes {width}x{height} samples={scene.cycles.samples} threads={scene.render.threads} seed={scene.cycles.seed}", flush=True)
bpy.ops.object.bake(type="DIFFUSE")
image.filepath_raw = str(output / "indirect.exr")
image.file_format = "OPEN_EXR"
image.save()
record.update(finished=True,elapsed_seconds=time.monotonic()-started,
              output_sha256=hashlib.sha256((output/'indirect.exr').read_bytes()).hexdigest())
(output/'bake.json').write_text(json.dumps(record,indent=2)+'\n')
print("BAKE_DONE", image.filepath_raw, flush=True)
