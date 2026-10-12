"""Build an original unbranded compact espresso machine for the private house.

Reference proportions/mechanics: official De'Longhi Dedica EC685 product photos.
No reference photo, manufacturer logo, or manufacturer geometry is exported.
Blender -Y is the front, glTF +Z the front; origin sits on the kitchen counter.
"""
import bpy
import hashlib
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/house/assets/coffee-machine'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
parts = []

def material(name, color, metal=0, rough=.4):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    shader = m.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Metallic'].default_value = metal
    shader.inputs['Roughness'].default_value = rough
    m.diffuse_color = (*color, 1)
    return m

black = material('Graphite powder-coated housing', (.027, .031, .033), .18, .39)
steel = material('Brushed stainless steel', (.47, .50, .52), 1, .29)
chrome = material('Polished brew metal', (.66, .70, .72), 1, .17)
rubber = material('Matte black grip and feet', (.011, .013, .015), 0, .63)
ceramic = material('Warm porcelain', (.77, .74, .67), 0, .22)
coffee = material('Espresso crema', (.19, .071, .018), 0, .38)
indicator = material('Small amber indicator', (.85, .31, .025), 0, .3)

def finish(o, name, mat, bevel=0):
    o.name = name
    o.data.materials.append(mat)
    if bevel:
        mod = o.modifiers.new('Manufactured edge radius', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in o.data.polygons:
        p.use_smooth = True
    weighted = o.modifiers.new('Weighted face normals', 'WEIGHTED_NORMAL')
    weighted.keep_sharp = True
    bpy.ops.object.modifier_apply(modifier=weighted.name)
    parts.append(o)
    return o

def box(name, dims, loc, mat, bevel=.003):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o, name, mat, bevel)

def cyl(name, radius, depth, loc, mat, axis=(0, 0, 1), bevel=.001, vertices=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    o = bpy.context.object
    o.rotation_euler = Vector(axis).to_track_quat('Z', 'Y').to_euler()
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    return finish(o, name, mat, bevel)

def pipe(name, points, radius, mat):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 8
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    s = curve.splines.new('BEZIER')
    s.bezier_points.add(len(points)-1)
    for b, p in zip(s.bezier_points, points):
        b.co = p
        b.handle_left_type = b.handle_right_type = 'AUTO'
    o = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o.select_set(False)
    return finish(o, name, mat)

# Base is wide enough for two espresso cups; upright stays behind the brew bay.
box('Base', (.218, .267, .034), (0, -.012, .023), black, .013)
for x in [-.075, .075]:
    for y in [-.1, .08]:
        cyl('Rubber foot', .012, .006, (x, y, .003), rubber)
box('Rear water reservoir', (.16, .061, .287), (0, .091, .177), black, .009)
box('Rear spine', (.174, .10, .289), (0, .031, .178), black, .014)
box('Upper curved housing', (.195, .188, .116), (0, .014, .292), black, .027)
box('Top warming plate', (.168, .153, .008), (0, .021, .352), steel, .004)
for y in [.002, .028, .054]:
    box('Warming plate shallow rib', (.125, .003, .0015), (0, y, .3568), chrome, .0005)
box('Brushed front control strip', (.176, .008, .029), (0, -.082, .329), steel, .008)
for i, x in enumerate([-.05, 0, .05]):
    cyl('Control bezel', .011, .003, (x, -.088, .329), chrome, (0,-1,0))
    cyl('Control button', .0078, .0035, (x, -.09, .329), rubber, (0,-1,0))
    box('Control mark', (.002, .001, .005 if i==0 else .003), (x, -.092, .329), steel, .0004)
cyl('Amber status dot', .0016, .001, (.073, -.087, .331), indicator, (0,-1,0), 0, 12)
# Real brew-head geometry and two small outlets, not a black solid appliance box.
cyl('Brew head ring', .046, .018, (0, -.064, .225), chrome)
cyl('Portafilter cup', .034, .042, (0, -.067, .199), steel)
cyl('Portafilter collar', .033, .008, (0, -.067, .175), chrome)
pipe('Twin outlet', [(-.018,-.067,.166),(0,-.067,.170),(.018,-.067,.166)], .004, chrome)
for x in [-.018, .018]:
    cyl('Espresso outlet', .004, .011, (x, -.067, .163), chrome)
cyl('Portafilter handle mount', .009, .024, (0, -.107, .196), chrome, (0,-1,0))
cyl('Portafilter grip', .012, .060, (0, -.128, .194), rubber, (0,-1,-.10))
cyl('Grip end', .012, .004, (0, -.159, .191), steel, (0,-1,-.10))
# Side steam wand and adjustable knob.
cyl('Steam knob shaft', .015, .017, (.105, .012, .282), chrome, (1,0,0))
cyl('Steam adjustment knob', .019, .017, (.122, .012, .282), rubber, (1,0,0))
for a in range(12):
    theta=a*math.tau/12
    box('Steam knob grip rib', (.014,.0028,.0028), (.123,.012+math.sin(theta)*.019,.282+math.cos(theta)*.019), rubber,.0006)
pipe('Steam wand', [(.094,-.013,.246),(.115,-.035,.232),(.121,-.060,.195),(.123,-.075,.133)], .0045, chrome)
cyl('Steam sleeve', .009, .029, (.123,-.071,.153), rubber, (0,-.15,-1))
cyl('Steam tip', .006, .015, (.125,-.079,.118), steel, (0,-.15,-1))
# Drip tray rails have actual gaps into a dark recessed basin.
box('Drip basin', (.19,.118,.008), (0,-.081,.044), rubber,.009)
for x in [-.092,.092]:
    box('Drip tray side rim', (.007,.12,.007), (x,-.081,.051), chrome,.002)
for y in [-.138,-.024]:
    box('Drip tray end rim', (.18,.007,.007), (0,y,.051), chrome,.002)
for i in range(10):
    box('Drip tray grille rail', (.173,.004,.005), (0,-.127+i*.0103,.052), steel,.001)
# Hollow cup, joined ring profiles rather than a solid capped cylinder.
profile=[(.022,0),(.025,.004),(.026,.052),(.025,.055),(.022,.055),(.022,.009),(.004,.006),(.004,0)]
verts=[]; faces=[]; n=40
for radius,z in profile:
    for j in range(n):
        a=j*math.tau/n
        verts.append((-.045+radius*math.cos(a),-.086+radius*math.sin(a),.055+z))
for k in range(len(profile)):
    for j in range(n):
        faces.append((k*n+j,k*n+(j+1)%n,((k+1)%len(profile))*n+(j+1)%n,((k+1)%len(profile))*n+j))
mesh=bpy.data.meshes.new('Hollow porcelain cup');mesh.from_pydata(verts,[],faces);mesh.update()
o=bpy.data.objects.new('Espresso cup',mesh);bpy.context.collection.objects.link(o)
finish(o,'Espresso cup',ceramic)
pipe('Cup handle', [(-.069,-.086,.1),(-.083,-.086,.096),(-.084,-.086,.077),(-.069,-.086,.07)], .003, ceramic)
cyl('Coffee surface', .0218,.001,(-.045,-.086,.100),coffee,bevel=0)

# Combine by material: seven runtime draw calls, stable unique bake IDs.
for mat in [black,steel,chrome,rubber,ceramic,coffee,indicator]:
    bpy.ops.object.select_all(action='DESELECT')
    members=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.data.materials[0] == mat]
    for o in members:o.select_set(True)
    bpy.context.view_layer.objects.active=members[0]
    bpy.ops.object.join()
    bpy.context.object.name=mat.name.replace(' ','_')
assets=[o for o in bpy.context.scene.objects if o.type=='MESH']
points=[o.matrix_world@v.co for o in assets for v in o.data.vertices]
lo=[min(p[i] for p in points) for i in range(3)]
hi=[max(p[i] for p in points) for i in range(3)]
assert hi[0]-lo[0] < .33 and hi[1]-lo[1] < .29 and hi[2]-lo[2] < .40
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'coffee-machine.blend'))
bpy.ops.export_scene.gltf(filepath=str(OUT/'coffee-machine.glb'),export_format='GLB',use_selection=False)
(OUT/'coffee-machine.json').write_text(json.dumps({
    'geometry':'Original unbranded Blender model. Adapted from manufacturer photo/mechanical layout; not manufacturer CAD.',
    'reference_url':'https://www.delonghi.com/en/p/dedica-manual-espresso-makers-dedica-style-manual-coffee-maker-ec685.bk/EC685.BK.html?pid=0132106140',
    'reference_image_url':'https://dam.delonghi.com/902x902/assets/223691',
    'reference_dimensions_mm':[149,330,305],
    'blender_bounds_m':[lo,hi],
    'runtime_materials':len(assets),'triangles':sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in assets),
    'glb_bytes':(OUT/'coffee-machine.glb').stat().st_size,
    'sha256':hashlib.sha256((OUT/'coffee-machine.glb').read_bytes()).hexdigest(),
    'runtime_counter_origin_m':[-1.25,.925,-3.5],
    'functionality':'Furnishing geometry only; brewing/cooking activity is not implemented by this asset.'
},indent=2))
# Diagnostic studio render is local/ignored, not a substitute for the real home.
floor=box('Diagnostic studio floor',(4,4,.02),(0,0,-.013),material('Diagnostic floor',(.24,.24,.24)),0)
world=bpy.data.worlds.new('Studio world');bpy.context.scene.world=world
world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.35,.35,.35,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.55
for loc,power,size in [((-.5,-.6,.8),35,.6),((.4,.2,.7),28,.4)]:
    bpy.ops.object.light_add(type='AREA',location=loc)
    light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size
    light.rotation_euler=(Vector((0,0,.18))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(.55,-.75,.46))
cam=bpy.context.object;cam.rotation_euler=(Vector((0,-.015,.18))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO';cam.data.ortho_scale=.51;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
scene.render.resolution_x=800;scene.render.resolution_y=800;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
render=ROOT/'out/coffee-reference/coffee-machine-render.png';render.parent.mkdir(parents=True,exist_ok=True)
scene.render.filepath=str(render);bpy.ops.render.render(write_still=True)
print('COFFEE_MACHINE_BUILT', json.dumps({'bounds':[lo,hi],'glb_bytes':(OUT/'coffee-machine.glb').stat().st_size}),flush=True)
