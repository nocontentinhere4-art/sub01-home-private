"""Original oak office desk with fixed SUB-01 desktop height and clear knee space.

Reference: MUJI Oak Wooden Desk 4550512841050, original adapted proportions.
No commercial CAD or product photos are exported. The runtime shares existing
CC0 oak maps; this GLB contains geometry only. Front = Blender -Y = glTF +Z.
"""
import bpy
import hashlib
import json
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'web/house/assets/office-desk-original';OUT.mkdir(parents=True,exist_ok=True)
PREVIEW=ROOT/'out/reference-design';PREVIEW.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
oak=bpy.data.materials.new('Oak desk');oak.use_nodes=True
shader=oak.node_tree.nodes.get('Principled BSDF');shader.inputs['Roughness'].default_value=.92
for file,socket in [('diff.jpg','Base Color'),('rough.jpg','Roughness')]:
    img=bpy.data.images.load(str(ROOT/'web/house/assets/home_oak_veneer'/file))
    if file!='diff.jpg':img.colorspace_settings.name='Non-Color'
    node=oak.node_tree.nodes.new('ShaderNodeTexImage');node.image=img
    if file=='rough.jpg':
        mult=oak.node_tree.nodes.new('ShaderNodeMath');mult.operation='MULTIPLY';mult.inputs[1].default_value=.92
        oak.node_tree.links.new(node.outputs['Color'],mult.inputs[0]);oak.node_tree.links.new(mult.outputs[0],shader.inputs[socket])
    else:oak.node_tree.links.new(node.outputs['Color'],shader.inputs[socket])
hardware=bpy.data.materials.new('Dark desk hardware');hardware.use_nodes=True
h=hardware.node_tree.nodes.get('Principled BSDF');h.inputs['Base Color'].default_value=(.015,.018,.017,1)
h.inputs['Roughness'].default_value=.65
parts=[]

def finish(o,name,mat,bevel=.002):
    o.name=name
    if bevel:
        m=o.modifiers.new('Tactile furniture edge','BEVEL');m.width=bevel;m.segments=3
        bpy.ops.object.modifier_apply(modifier=m.name)
    m=o.modifiers.new('Joinery face normals','WEIGHTED_NORMAL');m.keep_sharp=True
    bpy.ops.object.modifier_apply(modifier=m.name)
    o.data.materials.append(mat)
    layer=o.data.uv_layers.active or o.data.uv_layers.new(name='Oak scan physical scale')
    for p in o.data.polygons:
        for li in p.loop_indices:
            v=o.data.vertices[o.data.loops[li].vertex_index].co
            # Source grain runs along texture V: long desktop/aprons lengthwise,
            # four legs vertically. Maintain the actual 1.83m scan density.
            if abs(p.normal.z)>.5:uv=(v.y/1.83,v.x/1.83)
            elif abs(p.normal.x)>.5:
                uv=(v.z/1.83,v.y/1.83) if name=='Side stiffening apron' else (v.y/1.83,v.z/1.83)
            else:
                horizontal=name in ['Rear stiffening apron','Drawer housing','Drawer oak front']
                uv=(v.z/1.83,v.x/1.83) if horizontal else (v.x/1.83,v.z/1.83)
            layer.data[li].uv=uv
    parts.append(o);return o

def block(name,dims,loc,mat=oak,bevel=.002):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    o=bpy.context.object;o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return finish(o,name,mat,bevel)

top=block('Continuous oak desktop',(2.4,.8,.033),(0,0,.8285),bevel=.0025)
# Real through-opening: a small recessed cable grommet away from fixed devices.
bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.024,depth=.08,location=(.82,.30,.83))
cutter=bpy.context.object
boolean=top.modifiers.new('Cable through opening','BOOLEAN');boolean.operation='DIFFERENCE';boolean.object=cutter
bpy.context.view_layer.objects.active=top;bpy.ops.object.modifier_apply(modifier=boolean.name)
bpy.data.objects.remove(cutter,do_unlink=True)
bpy.ops.mesh.primitive_torus_add(major_segments=32,minor_segments=8,major_radius=.0245,minor_radius=.0025,location=(.82,.30,.8425))
finish(bpy.context.object,'Cable grommet rim',hardware,0)

for x in [-1.075,1.075]:
    for y in [-.316,.316]:
        block('Solid oak leg',(.062,.062,.812),(x,y,.406),bevel=.003)
# Aprons keep this 2.4m work surface structurally believable; front knee bay stays open.
block('Rear stiffening apron',(2.10,.028,.084),(0,.316,.764),bevel=.0015)
for x in [-1.075,1.075]:
    block('Side stiffening apron',(.028,.57,.084),(x,0,.764),bevel=.0015)
# Side drawers are original proportions; central free bay is 1.02m wide.
for x in [-.795,.795]:
    block('Drawer housing',(.546,.525,.102),(x,-.04,.747),bevel=.0015)
    block('Drawer recessed shadow',(.526,.010,.083),(x,-.308,.747),hardware,.001)
    block('Drawer oak front',(.520,.018,.077),(x,-.316,.746),bevel=.0015)
    # Small underside pull has physical depth but does not become a bright brass stripe.
    block('Drawer finger pull',(.105,.016,.009),(x,-.329,.712),hardware,.0015)

assets=[]
for mat,name in [(oak,'Oak_desk'),(hardware,'Desk_hardware')]:
    bpy.ops.object.select_all(action='DESELECT')
    members=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.data.materials and o.data.materials[0]==mat]
    for o in members:o.select_set(True)
    bpy.context.view_layer.objects.active=members[0];bpy.ops.object.join()
    o=bpy.context.object;o.name=name;bpy.ops.object.transform_apply(location=True,rotation=True,scale=True);assets.append(o)
points=[v.co for o in assets for v in o.data.vertices]
lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
assert hi[0]-lo[0]<=2.401 and hi[1]-lo[1]<=.801
assert abs(hi[2]-.845)<.001 and abs(lo[2])<.001
bpy.ops.object.select_all(action='SELECT');bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'desk.blend'))
bpy.ops.export_scene.gltf(filepath=str(OUT/'desk.glb'),export_format='GLB',export_materials='NONE',export_cameras=False,export_lights=False)
p=OUT/'desk.glb'
(OUT/'desk.json').write_text(json.dumps({
    'geometry':'Original enlarged oak desk with thin continuous desktop, four legs, structural aprons, two side drawers, central knee bay, real cable opening. Decorative drawers, not interactive.',
    'reference_url':'https://www.muji.eu/products/oak-wooden-desk-20226',
    'verified_manufacturer_manual':'https://www.muji.com/public/media/jp/doc/item/02_2200009922336_00002.pdf',
    'reference_product':'MUJI Oak Wooden Desk 4550512841050',
    'reference_dimensions_m':[1.1,.55,.7],
    'original_dimensions_m':[2.4,.8,.845],'desktop_thickness_m':.033,
    'blender_bounds_m':[lo,hi],'runtime_origin_m':[2,0,-3.1],'runtime_yaw_radians':0,
    'fixed_devices':'Monitor, keyboard, mouse and lamp coordinates remain unchanged; desktop top remains .845m.',
    'runtime_materials':{'Oak_desk':'M.architectureOak shared maps; metric UV / 1.83m source scan; no second oak grade','Desk_hardware':'M.black or matching dark matte material'},
    'texture_source':'https://polyhaven.com/a/oak_veneer_01','embedded_textures':False,
    'glb_bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
    'triangles':sum(sum(len(f.vertices)-2 for f in o.data.polygons) for o in assets)
},indent=2))

bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,-.001))
floor=bpy.context.object
mat=bpy.data.materials.new('Studio floor');mat.use_nodes=True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.23,.23,.23,1)
floor.data.materials.append(mat)
world=bpy.data.worlds.new('Studio');world.use_nodes=True;bpy.context.scene.world=world
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.5,.5,.5,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35
for loc,power,size in [((-2,-3,4),250,3),((3,1,3),180,2)]:
    bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.size=size
    light.rotation_euler=(Vector((0,0,.4))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(3.2,-4.6,2.4));cam=bpy.context.object
cam.rotation_euler=(Vector((0,0,.4))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO';cam.data.ortho_scale=3.1;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
scene.render.resolution_x=1100;scene.render.resolution_y=780;scene.render.resolution_percentage=100
scene.render.filepath=str(PREVIEW/'office-desk-studio.png');bpy.ops.render.render(write_still=True)
print('OFFICE_DESK_BUILT',json.dumps({'bounds':[lo,hi],'bytes':p.stat().st_size}),flush=True)
