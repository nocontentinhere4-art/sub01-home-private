"""Original light-oak coffee table for the actual private SUB-01 lounge.

Official Karimoku NF-CT01 photos inform restrained oak joinery, not copied CAD.
Adapted dimensions fit the existing .70 x 1.40m table collider. One draw call,
no embedded runtime textures; the house reuses its existing CC0 oak material.
"""
import bpy
import hashlib
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'web/house/assets/coffee-table-original';OUT.mkdir(parents=True,exist_ok=True)
PREVIEW=ROOT/'out/reference-design';PREVIEW.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
oak=bpy.data.materials.new('Original oak table');oak.use_nodes=True;oak.diffuse_color=(.64,.49,.31,1)
bsdf=oak.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Roughness'].default_value=.72
for filename,socket in [('diff.jpg','Base Color'),('rough.jpg','Roughness')]:
    image=bpy.data.images.load(str(ROOT/'web/house/assets/fine_grained_wood'/filename))
    if filename!='diff.jpg':image.colorspace_settings.name='Non-Color'
    texture=oak.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image
    if filename=='diff.jpg':
        tint=oak.node_tree.nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1
        # Match kitchenOak #e7d5b5 in linear color, then existing shared oak grade.
        tint.inputs[2].default_value=(.799,.665,.462,1)
        oak.node_tree.links.new(texture.outputs['Color'],tint.inputs[1])
        gamma=oak.node_tree.nodes.new('ShaderNodeGamma');gamma.inputs['Gamma'].default_value=.45
        oak.node_tree.links.new(tint.outputs[0],gamma.inputs['Color'])
        finish=oak.node_tree.nodes.new('ShaderNodeVectorMath');finish.operation='MULTIPLY';finish.inputs[1].default_value=(.95,.90,.80)
        oak.node_tree.links.new(gamma.outputs[0],finish.inputs[0]);oak.node_tree.links.new(finish.outputs[0],bsdf.inputs[socket])
    else:
        factor=oak.node_tree.nodes.new('ShaderNodeMath');factor.operation='MULTIPLY';factor.inputs[1].default_value=.72
        oak.node_tree.links.new(texture.outputs['Color'],factor.inputs[0]);oak.node_tree.links.new(factor.outputs[0],bsdf.inputs[socket])
parts=[]

def component(name,dims,loc,bevel=.002):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    o=bpy.context.object;o.name=name;o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    mod=o.modifiers.new('Small tactile oak radius','BEVEL');mod.width=bevel;mod.segments=3
    bpy.ops.object.modifier_apply(modifier=mod.name)
    n=o.modifiers.new('Planar joinery normals','WEIGHTED_NORMAL');n.keep_sharp=True
    bpy.ops.object.modifier_apply(modifier=n.name)
    o.data.materials.append(oak)
    layer=o.data.uv_layers.active or o.data.uv_layers.new(name='Oak grain meters')
    for p in o.data.polygons:
        for li in p.loop_indices:
            v=o.data.vertices[o.data.loops[li].vertex_index].co
            # Horizontal faces follow the long top; vertical leg faces keep grain up.
            if abs(p.normal.z)>.5:uv=(v.x,v.y)
            elif abs(p.normal.x)>.5:uv=(v.z,v.y)
            else:uv=(v.z,v.x)
            layer.data[li].uv=uv
    parts.append(o);return o

# Continuous solid oak slab with a restrained hand-safe perimeter edge.
component('Solid oak top',(1.38,.68,.026),(0,0,.377),.0025)
# Four pairs of shoulders visibly support the top; no giant patchwork texture planes.
for x in [-.563,.563]:
    for y in [-.261,.261]:
        leg=component('Oak shoulder leg',(.060,.095,.364),(x,y,.182),.002)
        # Restrained taper toward the foot, keeping exact top shoulder/contact height.
        for v in leg.data.vertices:
            if v.co.z<0:
                t=max(0,min(1,-v.co.z/.182))
                v.co.x*=1-.16*t
                v.co.y*=1-.08*t
for y in [-.261,.261]:
    component('Long recessed rail',(1.096,.028,.048),(0,y,.329),.0015)
for x in [-.563,.563]:
    component('Short recessed rail',(.028,.448,.048),(x,0,.329),.0015)

bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join()
table=bpy.context.object;table.name='Oak_coffee_table'
bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
points=[v.co for v in table.data.vertices]
lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
assert hi[0]-lo[0]<=1.401 and hi[1]-lo[1]<=.701 and hi[2]-lo[2]<=.46
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'coffee-table.blend'))
bpy.ops.export_scene.gltf(filepath=str(OUT/'coffee-table.glb'),export_format='GLB',use_selection=True,
                          export_materials='NONE',export_cameras=False,export_lights=False)
glb=OUT/'coffee-table.glb'
(OUT/'coffee-table.json').write_text(json.dumps({
    'geometry':'Original oak coffee table with continuous slab, four tapered shoulder legs and recessed support rails; no manufacturer CAD.',
    'reference_url':'https://www.karimoku-case.com/furniture/nf-ct01/',
    'reference_photo_url':'https://www.karimoku-case.com/wp/wp-content/uploads/2022/10/KCS_NF_commons_20221105_003-scaled.jpg',
    'manufacturer_reference_dimensions_m':[1.5,.6,.305],
    'original_dimensions_m':[1.38,.68,.39],'blender_bounds_m':[lo,hi],
    'runtime_origin_m':[-3.2,0,.1],'runtime_yaw_radians':-math.pi/2,
    'runtime_world_footprint_m':[.68,1.38],'existing_collision_envelope_m':[.70,1.40],
    'runtime_material':'Existing house M.kitchenOak (light-oak grade) or equivalent clone sharing existing CC0 fine_grained_wood maps; metric UVs.',
    'texture_source':'https://polyhaven.com/a/fine_grained_wood','embedded_textures':False,
    'vertices':len(table.data.vertices),'triangles':sum(len(p.vertices)-2 for p in table.data.polygons),
    'glb_bytes':glb.stat().st_size,'sha256':hashlib.sha256(glb.read_bytes()).hexdigest()
},indent=2))

# Ignored studio reference inspection only; original .blend was saved without studio.
bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,-.002))
floor=bpy.context.object
mat=bpy.data.materials.new('Studio floor');mat.use_nodes=True
mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.22,.22,.22,1)
floor.data.materials.append(mat)
world=bpy.data.worlds.new('Studio');world.use_nodes=True;bpy.context.scene.world=world
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.5,.5,.5,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value=.35
for loc,power,size in [((-2,-2,3),200,2),((2,1,2),120,1.5)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    light=bpy.context.object;light.data.energy=power;light.data.size=size
    light.rotation_euler=(Vector((0,0,.2))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(2.3,-2.5,1.7));camera=bpy.context.object
camera.rotation_euler=(Vector((0,0,.2))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type='ORTHO';camera.data.ortho_scale=1.85;bpy.context.scene.camera=camera
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
scene.render.resolution_x=1000;scene.render.resolution_y=720;scene.render.resolution_percentage=100
scene.render.filepath=str(PREVIEW/'coffee-table-studio.png');bpy.ops.render.render(write_still=True)
print('COFFEE_TABLE_BUILT',json.dumps({'bounds':[lo,hi],'bytes':glb.stat().st_size}),flush=True)
