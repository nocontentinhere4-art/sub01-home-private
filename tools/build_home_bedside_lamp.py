"""Original small linen/brass bedside lamp, modeled in Blender for the local home."""
import bpy,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUTPUT=ROOT/'web/house/assets/bedside-lamp';OUTPUT.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
parts=[]
def cylinder(name,radius,depth,z):
 bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=radius,depth=depth,location=(0,0,z))
 o=bpy.context.object;o.name=name
 b=o.modifiers.new('Soft metal edges','BEVEL');b.width=.002;b.segments=3;bpy.ops.object.modifier_apply(modifier=b.name)
 for face in o.data.polygons:face.use_smooth=True
 parts.append(o);return o
base=cylinder('Brass base',.085,.024,.014)
stem=cylinder('Brass stem',.008,.224,.138)
socket=cylinder('Brass socket',.015,.025,.245)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,radius=.026,location=(0,0,.268))
bulb=bpy.context.object;bulb.name='Bulb'
for f in bulb.data.polygons:f.use_smooth=True
parts.append(bulb)
bpy.ops.mesh.primitive_cone_add(vertices=64,radius1=.155,radius2=.115,depth=.22,end_fill_type='NOTHING',location=(0,0,.29))
shade=bpy.context.object;shade.name='Linen shade'
shell=shade.modifiers.new('Fabric shell and rims','SOLIDIFY');shell.thickness=.003;bpy.ops.object.modifier_apply(modifier=shell.name)
for f in shade.data.polygons:f.use_smooth=True
parts.append(shade)
linen=bpy.data.materials.new('Natural linen');linen.diffuse_color=(.73,.66,.51,1)
brass=bpy.data.materials.new('Brass');brass.diffuse_color=(.47,.34,.14,1)
glow=bpy.data.materials.new('Warm bulb');glow.diffuse_color=(1,.88,.65,1)
for o in parts:o.data.materials.append(linen if o==shade else glow if o==bulb else brass)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/'lamp.blend'))
bpy.ops.export_scene.gltf(filepath=str(OUTPUT/'lamp.glb'),export_format='GLB',use_selection=True,export_materials='NONE')
(OUTPUT/'lamp.json').write_text(json.dumps({'geometry':'Original Blender model: open linen shade, brass foot/stem/socket, bulb',
 'dimensions_m':[.31,.31,.40],'bulb_height_m':.268,'runtime_materials':'Existing CC0 linen maps, brass and switched bulb emission',
 'glb_bytes':(OUTPUT/'lamp.glb').stat().st_size,'sha256':hashlib.sha256((OUTPUT/'lamp.glb').read_bytes()).hexdigest()},indent=2))
print('LAMP_BUILT', (OUTPUT/'lamp.glb').stat().st_size,flush=True)
