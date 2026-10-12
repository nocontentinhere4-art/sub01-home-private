"""Replace only the pillows in existing bedding; preserve settled cloth exactly."""
import bpy
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from bedding_pillows import sleeping_pillows
from glb_pillows import replace_pillows
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'web/house/assets/bedding'
for name in ['bedding.glb', 'bedding-lite.glb']:
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(OUTPUT / name))
    cloth = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.name.startswith('Pillow')]
    for obj in list(bpy.context.scene.objects):
        if obj.name.startswith('Pillow'): bpy.data.objects.remove(obj, do_unlink=True)
    pillows = sleeping_pillows(bpy.context.scene, ROOT / 'web/house/assets/throw_pillows_01/throw_pillows_01.gltf')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in pillows: obj.select_set(True)
    temporary = OUTPUT / 'pillows-only.glb'
    bpy.ops.export_scene.gltf(filepath=str(temporary), export_format='GLB', use_selection=True,
        export_materials='NONE', export_cameras=False, export_lights=False)
    replace_pillows(OUTPUT / name, temporary)
    temporary.unlink()
meta = json.loads((OUTPUT / 'bedding.json').read_text())
meta['pillow_alignment'] = 'pillow02 scan; right-handed principal axes; longest axis across bed, thickness vertical'
for name in ['bedding.glb', 'bedding-lite.glb']:
    meta['files'][name] = {'bytes':(OUTPUT/name).stat().st_size, 'sha256':hashlib.sha256((OUTPUT/name).read_bytes()).hexdigest()}
for obj in pillows:
    meta['geometry'][obj.name] = {'vertices':len(obj.data.vertices), 'faces':len(obj.data.polygons)}
(OUTPUT/'bedding.json').write_text(json.dumps(meta,indent=2))
