"""Original thin oak wall shelving for the existing private SUB-01 office.

Design references: Karimoku N-SS01 restrained oak structure and MUJI wall shelf.
Adapted wall-mounted construction, not product CAD. Books and desktop stay where
they are: six shelf surfaces retain the procedural shelf's exact heights.
"""
import bpy
import hashlib
import json
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'web/house/assets/office-shelves-original';OUT.mkdir(parents=True,exist_ok=True)
PREVIEW=ROOT/'out/reference-design';PREVIEW.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
oak=bpy.data.materials.new('Oak shelves');oak.use_nodes=True
shader=oak.node_tree.nodes.get('Principled BSDF');shader.inputs['Roughness'].default_value=.92
for file,socket in [('diff.jpg','Base Color'),('rough.jpg','Roughness')]:
    image=bpy.data.images.load(str(ROOT/'web/house/assets/home_oak_veneer'/file))
    if file!='diff.jpg':image.colorspace_settings.name='Non-Color'
    texture=oak.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image
    if file=='rough.jpg':
        factor=oak.node_tree.nodes.new('ShaderNodeMath');factor.operation='MULTIPLY';factor.inputs[1].default_value=.92
        oak.node_tree.links.new(texture.outputs[0],factor.inputs[0]);oak.node_tree.links.new(factor.outputs[0],shader.inputs[socket])
    else:oak.node_tree.links.new(texture.outputs[0],shader.inputs[socket])
metal=bpy.data.materials.new('Dark shelf brackets');metal.use_nodes=True
shader=metal.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(.018,.020,.019,1)
shader.inputs['Metallic'].default_value=.35;shader.inputs['Roughness'].default_value=.74

def block(name,dims,loc,mat=oak,bevel=.001):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    o=bpy.context.object;o.name=name;o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if bevel:
        mod=o.modifiers.new('Subtle milled edge','BEVEL');mod.width=bevel;mod.segments=2
        bpy.ops.object.modifier_apply(modifier=mod.name)
    normal=o.modifiers.new('Joinery face normals','WEIGHTED_NORMAL');normal.keep_sharp=True
    bpy.ops.object.modifier_apply(modifier=normal.name)
    o.data.materials.append(mat)
    layer=o.data.uv_layers.active or o.data.uv_layers.new(name='Oak meters')
    for face in o.data.polygons:
        for li in face.loop_indices:
            v=o.data.vertices[o.data.loops[li].vertex_index].co
            if abs(face.normal.z)>.5:uv=(v.y/1.83,v.x/1.83)
            elif abs(face.normal.x)>.5:uv=(v.y/1.83,v.z/1.83)
            else:uv=(v.x/1.83,v.z/1.83) if 'cleat' in name else (v.z/1.83,v.x/1.83)
            layer.data[li].uv=uv
    return o

# Three wall-fixed cleats support six wide thin oak surfaces; front circulation
# stays identical and the cleats do not stick through the desk's monitor.
for x in [-1.045,0,1.045]:
    block('Vertical oak wall cleat',(.030,.026,2.39),(x,.151,1.32),bevel=.0015)
for i in range(6):
    surface=.2675+i*.45
    block('Thin oak shelf',(2.35,.34,.022),(0,0,surface-.011),bevel=.001)
    for x in [-1.045,0,1.045]:
        # Actual unobtrusive L brackets seated on the wall cleats, not floating slabs.
        block('Bracket vertical',(.017,.005,.056),(x,.134,surface-.050),metal,.0007)
        block('Bracket underside support',(.017,.284,.005),(x,-.005,surface-.0245),metal,.0007)
        # Short rear screw head identifies attachment at first-person range.
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8,ring_count=4,radius=.002,location=(x,.130,surface-.063))
        screw=bpy.context.object;screw.name='Bracket screw';screw.scale=(1,.3,1);screw.data.materials.append(metal)

assets=[]
for mat,name in [(oak,'Oak_shelves'),(metal,'Shelf_hardware')]:
    bpy.ops.object.select_all(action='DESELECT')
    members=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.data.materials and o.data.materials[0]==mat]
    for o in members:o.select_set(True)
    bpy.context.view_layer.objects.active=members[0];bpy.ops.object.join()
    o=bpy.context.object;o.name=name;bpy.ops.object.transform_apply(location=True,rotation=True,scale=True);assets.append(o)
points=[v.co for o in assets for v in o.data.vertices]
lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
assert hi[0]-lo[0]<=2.351 and hi[1]-lo[1]<=.341
assert abs(hi[2]-2.5175)<.001 and abs(lo[2]-.125)<.001
bpy.ops.object.select_all(action='SELECT');bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shelves.blend'))
bpy.ops.export_scene.gltf(filepath=str(OUT/'shelves.glb'),export_format='GLB',export_materials='NONE',export_lights=False,export_cameras=False)
p=OUT/'shelves.glb'
(OUT/'shelves.json').write_text(json.dumps({
    'geometry':'Original wall-mounted oak shelf assembly with six thin shelves, three wall cleats and small visible L brackets. Not manufacturer CAD.',
    'reference_urls':['https://www.karimoku-case.com/furniture/n-ss01/','https://www.muji.com/jp/ja/store/cmdty/detail/4550344505007'],
    'karimoku_reference_dimensions_m':[1.427,.420,1.692],
    'actual_blender_bounds_m':[lo,hi],'runtime_origin_m':[2.125,0,-3.72],'runtime_yaw_radians':0,
    'shelf_top_heights_m':[.2675+i*.45 for i in range(6)],'shelf_thickness_m':.022,
    'existing_footprint_m':[2.35,.34],'fixed_books':'Keep books at original y+0.02; shelf tops remain y+0.0175, leaving 2.5mm clearance.',
    'monitor_clearance':'Frontmost geometry remains world z=-3.55; monitor rear is z=-3.3175, retaining ~.23m clearance.',
    'runtime_materials':{'Oak_shelves':'M.architectureOak, physical UVs /1.83m; no second light-oak grade','Shelf_hardware':'M.black or matching dark matte metal'},
    'texture_source':'https://polyhaven.com/a/oak_veneer_01','embedded_textures':False,
    'triangles':sum(sum(len(f.vertices)-2 for f in o.data.polygons) for o in assets),
    'glb_bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()
},indent=2))

# Ignored studio render; the editable source and exported GLB contain only assembly.
bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,-.001));floor=bpy.context.object
studio=bpy.data.materials.new('Studio');studio.use_nodes=True;studio.node_tree.nodes.get('Principled BSDF').inputs[0].default_value=(.24,.24,.24,1)
floor.data.materials.append(studio)
wall=block('Studio wall',(8,.02,4),(0,.19,2),studio,0)
world=bpy.data.worlds.new('Studio');world.use_nodes=True;bpy.context.scene.world=world
world.node_tree.nodes['Background'].inputs['Color'].default_value=(.5,.5,.5,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.3
for loc,power,size in [((-2,-3,4),250,3),((3,-1,3),180,2)]:
    bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.size=size
    light.rotation_euler=(Vector((0,0,1.4))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(3.1,-5.7,3.3));cam=bpy.context.object
cam.rotation_euler=(Vector((0,0,1.32))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO';cam.data.ortho_scale=3.6;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.filepath=str(PREVIEW/'office-shelves-studio.png');bpy.ops.render.render(write_still=True)
print('OFFICE_SHELVES_BUILT',json.dumps({'bounds':[lo,hi],'bytes':p.stat().st_size}),flush=True)
