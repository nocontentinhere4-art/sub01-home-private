"""Original metric compact kitchen upper cabinet; existing home footprint retained."""
import bpy
import hashlib
import json
from mathutils import Vector
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web/house/assets/kitchen-cabinet-original"
OUTPUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
parts = []


def box(name, dimensions, location, radius=.0015):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = obj.modifiers.new("Manufactured softened edge", "BEVEL")
    bevel.width = radius
    bevel.segments = 2
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    normals = obj.modifiers.new("Weighted panel normals", "WEIGHTED_NORMAL")
    bpy.ops.object.modifier_apply(modifier=normals.name)
    parts.append(obj)
    return obj


white = bpy.data.materials.new("Cabinet satin white")
white.diffuse_color = (.79, .77, .71, 1)
brass = bpy.data.materials.new("Cabinet brushed brass")
brass.diffuse_color = (.47, .34, .14, 1)
brass.use_nodes = True
bsdf = brass.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Metallic"].default_value = .85
bsdf.inputs["Roughness"].default_value = .45

# Blender x / y / z map to browser x / -z / y. Front faces Blender -y.
carcass = [
    box("Carcass back", (3.064, .012, .664), (0, .174, 0)),
    box("Carcass top", (3.10, .36, .018), (0, 0, .341)),
    box("Carcass bottom", (3.10, .36, .018), (0, 0, -.341)),
    box("Carcass left", (.018, .36, .664), (-1.541, 0, 0)),
    box("Carcass right", (.018, .36, .664), (1.541, 0, 0)),
]
for x in [-.775, 0, .775]:
    carcass.append(box("Carcass divider", (.018, .32, .664), (x, .018, 0)))
bpy.ops.object.select_all(action="DESELECT")
for obj in carcass:
    obj.select_set(True)
bpy.context.view_layer.objects.active = carcass[0]
bpy.ops.object.join()
carcass_obj = bpy.context.object
carcass_obj.name = "Cabinet carcass"
carcass_obj.data.materials.append(white)
parts = [carcass_obj]

door_specs = []
for i in range(4):
    center = -1.1625 + i * .775
    door = box(f"Cabinet door {i + 1}", (.771, .018, .66), (center, -.165, 0))
    door.data.materials.append(white)
    # Each original door is an independent mesh with a useful hinge origin.
    hinge_x = center - .771 / 2
    bpy.context.scene.cursor.location = (hinge_x, -.165, 0)
    bpy.context.view_layer.objects.active = door
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    handle = box(f"Cabinet brass pull {i + 1}", (.17, .008, .008), (center + .17, -.176, -.275), .001)
    handle.data.materials.append(brass)
    handle.parent = door
    handle.matrix_parent_inverse = door.matrix_world.inverted()
    door_specs.append({"node": door.name, "hingeLocalBrowser": [hinge_x, 0, .165], "axisBrowser": [0, 1, 0]})

bpy.ops.object.select_all(action="DESELECT")
for obj in parts:
    obj.select_set(True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "cabinet.blend"))
bpy.ops.export_scene.gltf(filepath=str(OUTPUT / "cabinet.glb"), export_format="GLB", use_selection=True, export_materials="EXPORT")
metadata = {"geometry": "Original Blender construction: four independent fronts, real thin carcass, reveals and understated lower brass pulls.",
            "referenceSources": ["https://house.muji.com/life/resident/kinoie/index_211102/", "https://www.woodone.co.jp/product/item/housing/suiji/"],
            "referenceUse": "Manufacturer references inform compact white/wood kitchen proportions; no source imagery, CAD or textures included.",
            "dimensions_m_browser": [3.10, .70, .36], "worldCenter_browser": [-2.2, 2.05, -3.71],
            "doors": door_specs, "runtimeMaterials": "Reuse M.white for carcass/fronts and M.brass for pulls; no new textures.",
            "runtimeIntegration": "Replace only the existing 3.1×0.7×0.36 white box. Add GLTF scene at existing center with no further scale/rotation. Leave under-cabinet light strip and all kitchen collisions unchanged.",
            "openingImplemented": False,
            "glb_bytes": (OUTPUT / "cabinet.glb").stat().st_size,
            "sha256": hashlib.sha256((OUTPUT / "cabinet.glb").read_bytes()).hexdigest()}
(OUTPUT / "cabinet.json").write_text(json.dumps(metadata, indent=2) + "\n")
print("UPPER_CABINET_BUILT", metadata["glb_bytes"], flush=True)
