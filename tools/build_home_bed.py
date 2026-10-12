"""Original Blender oak platform bed, fitted to the existing private-home bed collider.
Reference: MUJI oak platform-bed photography; original adapted geometry, not a product CAD copy.
"""
import bpy
import json
import hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'web/house/assets/bed';OUTPUT.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
wood=bpy.data.materials.new('Oak');wood.diffuse_color=(.65,.47,.28,1);wood.use_nodes=True
bsdf=wood.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Roughness'].default_value=.65
for filename,socket in [('diff.jpg','Base Color'),('rough.jpg','Roughness')]:
 image=bpy.data.images.load(str(ROOT/'web/house/assets/fine_grained_wood'/filename))
 if filename!='diff.jpg': image.colorspace_settings.name='Non-Color'
 texture=wood.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image
 wood.node_tree.links.new(texture.outputs['Color'],bsdf.inputs[socket])
parts=[]
def plank(name,size,location,bevel=.004):
 bpy.ops.mesh.primitive_cube_add(size=1,location=location)
 o=bpy.context.object;o.name=name;o.dimensions=size
 bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 o.data.materials.append(wood)
 b=o.modifiers.new('Soft joinery edges','BEVEL');b.width=bevel;b.segments=3
 bpy.ops.object.modifier_apply(modifier=b.name)
 n=o.modifiers.new('Face weighted normals','WEIGHTED_NORMAL');n.keep_sharp=True
 bpy.ops.object.modifier_apply(modifier=n.name)
 parts.append(o);return o
# The mattress surface remains exactly at the current house height (.57 above floor).
for x in (-.815,.815): plank('Side rail',(.07,2.22,.07),(x,0,.32))
for y in (-1.075,1.075): plank('End rail',(1.56,.07,.07),(0,y,.32))
plank('Centre support',(.065,2.08,.075),(0,0,.3075))
for i in range(14): plank('Slat',(1.54,.075,.025),(0,-.97+i*.149,.3525),.003)
for x in (-.72,.72):
 for y in (-.96,.96):
  bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.043,depth=.285,location=(x,y,.1425))
  o=bpy.context.object;o.name='Round oak leg';o.data.materials.append(wood)
  b=o.modifiers.new('Leg edge bevel','BEVEL');b.width=.003;b.segments=2;bpy.ops.object.modifier_apply(modifier=b.name)
  for f in o.data.polygons:f.use_smooth=True
  parts.append(o)
# A restrained headboard, with posts and a chamfered panel rather than a padded block.
for x in (-.70,.70):plank('Headboard post',(.055,.065,.93),(x,1.058,.465),.004)
plank('Headboard panel',(1.70,.045,.52),(0,1.083,.69),.009)
# Join static oak parts into one browser draw call.
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join()
frame=bpy.context.object;frame.name='Oak frame'
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT/'bed.blend'))
bpy.ops.export_scene.gltf(filepath=str(OUTPUT/'bed.glb'),export_format='GLB',use_selection=True,
 export_materials='NONE',export_cameras=False,export_lights=False)
metadata={'reference':'https://www.muji.eu/products/double-platform-bed-frame-oak-18913',
 'geometry':'Original adapted oak platform-bed geometry; no manufacturer CAD or product textures',
 'dimensions_m':[1.70,2.22,.95],'mattress_top_m':.57,'collision_envelope_m':[1.75,2.3],
 'wood_material':'Existing Poly Haven fine_grained_wood CC0 maps',
 'vertices':len(frame.data.vertices),'faces':len(frame.data.polygons),
 'glb_bytes':(OUTPUT/'bed.glb').stat().st_size,'sha256':hashlib.sha256((OUTPUT/'bed.glb').read_bytes()).hexdigest()}
(OUTPUT/'bed.json').write_text(json.dumps(metadata,indent=2))
print('BED_BUILT',metadata,flush=True)
