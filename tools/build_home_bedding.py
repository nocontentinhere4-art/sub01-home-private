"""Bake physical bedding into lightweight geometry; run with Blender --background --python.

No cloth solver runs in the browser. Pillow geometry comes from the existing
CC0 Poly Haven throw_pillows_01 asset; materials reuse the home's linen maps.
"""
import bpy
import json
import hashlib
import math
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'web/house/assets/bedding'
OUTPUT.mkdir(exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.frame_end = 55
scene.render.fps = 30

# Coordinates are local to the mattress centre. The browser places the group
# at (-2.4, 3.57, -2.35). Blender Z is up; glTF converts to browser Y-up.
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, -.10))
mattress = bpy.context.object
mattress.name = 'Simulation mattress'
mattress.dimensions = (1.6, 2.13, .2)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
bevel = mattress.modifiers.new('Rounded mattress', 'BEVEL')
bevel.width = .055
bevel.segments = 3
bpy.ops.object.modifier_apply(modifier=bevel.name)
mattress.modifiers.new('Collision', 'COLLISION')
mattress.collision.thickness_outer = .01
mattress.collision.cloth_friction = 8

def cloth(name, width, depth, centre, height, thickness, pin, anchor_height=.025):
    nx, ny = 42, 48
    vertices, faces = [], []
    for iy in range(ny + 1):
        v = iy / ny
        y = (v - .5) * depth + centre
        for ix in range(nx + 1):
            u = ix / nx
            x = (u - .5) * width
            # A slightly rumpled starting sheet settles under real gravity.
            z = height + .025 * math.sin(u * 19 + v * 4) * math.sin(v * math.pi)
            z += .008 * math.sin(v * 27 + u * 11)
            vertices.append((x, y, z))
    for iy in range(ny):
        for ix in range(nx):
            a = iy * (nx + 1) + ix
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv = mesh.uv_layers.new(name='UVMap')
    for polygon in mesh.polygons:
        for loop in polygon.loop_indices:
            index = mesh.loops[loop].vertex_index
            uv.data[loop].uv = ((index % (nx + 1)) / nx, (index // (nx + 1)) / ny)
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    if pin:
        group = obj.vertex_groups.new(name='Pinned top edge')
        anchors = [i for i in range(nx + 1) if abs(vertices[i][0]) < .65]
        group.add(anchors, 1, 'REPLACE')
        for i in anchors:
            mesh.vertices[i].co.z = anchor_height
    sim = obj.modifiers.new('Settled cloth', 'CLOTH')
    sim.settings.quality = 6
    sim.settings.mass = .2
    sim.settings.tension_stiffness = 12
    sim.settings.compression_stiffness = 12
    sim.settings.shear_stiffness = 6
    sim.settings.bending_stiffness = .35
    if pin:
        sim.settings.vertex_group_mass = group.name
    sim.collision_settings.use_collision = True
    sim.collision_settings.distance_min = .01
    sim.collision_settings.use_self_collision = False
    sim.collision_settings.self_distance_min = .008
    sim.point_cache.frame_end = scene.frame_end
    return obj, thickness

# Main cover and folded foot throw remain inside the existing bed collider.
cover = cloth('Duvet', 1.92, 1.76, -.30, .11, .014, True)
def settle(obj):
    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier='Settled cloth')
settle(cover[0])
cover[0].modifiers.new('Throw collision surface', 'COLLISION')
cover[0].collision.thickness_outer = .01
scene.frame_set(1)
throw = cloth('Foot throw', 1.96, .52, -.82, .12, .005, True, .055)
settle(throw[0])

outputs = []
for obj, thickness in (cover, throw):
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        if modifier.type == 'COLLISION':
            obj.modifiers.remove(modifier)
    smooth = obj.modifiers.new('Soft fabric surface', 'SUBSURF')
    smooth.levels = 1
    bpy.ops.object.modifier_apply(modifier=smooth.name)
    shell = obj.modifiers.new('Fabric thickness', 'SOLIDIFY')
    shell.thickness = thickness
    bpy.ops.object.modifier_apply(modifier=shell.name)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    outputs.append(obj)

# Reuse and align a scanned cushion by its actual principal thickness axis.
import sys
sys.path.insert(0, str(Path(__file__).parent))
from bedding_pillows import sleeping_pillows
outputs.extend(sleeping_pillows(scene, ROOT / 'web/house/assets/throw_pillows_01/throw_pillows_01.gltf'))

bpy.ops.object.select_all(action='DESELECT')
for obj in outputs:
    obj.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUTPUT / 'bedding.glb'), export_format='GLB',
    use_selection=True, export_materials='NONE', export_cameras=False, export_lights=False)
stats = {o.name: {'vertices': len(o.data.vertices), 'faces': len(o.data.polygons)} for o in outputs}
for obj, _ in (cover, throw):
    bpy.context.view_layer.objects.active = obj
    simplify = obj.modifiers.new('Mobile fabric geometry', 'DECIMATE')
    simplify.ratio = .35
    bpy.ops.object.modifier_apply(modifier=simplify.name)
bpy.ops.export_scene.gltf(filepath=str(OUTPUT / 'bedding-lite.glb'), export_format='GLB',
    use_selection=True, export_materials='NONE', export_cameras=False, export_lights=False)
(OUTPUT / 'bedding.json').write_text(json.dumps({
    'source': 'https://polyhaven.com/a/throw_pillows_01',
    'pillow_license': 'CC0-1.0', 'cloth': 'Blender offline cloth simulation, 55 frames',
    'runtime_simulation': False, 'geometry': stats,
    'files': {name: {'bytes': (OUTPUT/name).stat().st_size,
        'sha256': hashlib.sha256((OUTPUT/name).read_bytes()).hexdigest()}
        for name in ('bedding.glb', 'bedding-lite.glb')},
}, indent=2))
print('Bedding exported', stats, flush=True)
