"""Original upholstered sofa fitted to the private house, not manufacturer CAD.

Karimoku N-S03 reference: restrained fabric/oak division and softly rounded form.
Our dimensions adapt to the existing lounge/camera rather than copying the product.
Front is Blender -Y / glTF +Z. Runtime yaw -pi/2 faces the house television.
"""
import bpy
import hashlib
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'web/house/assets/sofa-original';OUT.mkdir(parents=True,exist_ok=True)
STUDIO=ROOT/'out/sofa-reference';STUDIO.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
parts=[]

def material(name,color,source=None):
    m=bpy.data.materials.new(name);m.use_nodes=True;m.diffuse_color=(*color,1)
    shader=m.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Roughness'].default_value=.96 if source=='rough_linen' else .94
    if source:
        maps=[('diff.jpg','Base Color')]
        if source!='rough_linen':maps.append(('rough.jpg','Roughness'))
        for filename,socket in maps:
            image=bpy.data.images.load(str(ROOT/'web/house/assets'/source/filename),check_existing=True)
            if filename!='diff.jpg':image.colorspace_settings.name='Non-Color'
            node=m.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
            mapping=m.node_tree.nodes.new('ShaderNodeVectorMath');mapping.operation='SCALE';mapping.inputs[3].default_value=2
            uv=m.node_tree.nodes.new('ShaderNodeTexCoord')
            m.node_tree.links.new(uv.outputs['UV'],mapping.inputs[0]);m.node_tree.links.new(mapping.outputs[0],node.inputs['Vector'])
            if filename=='diff.jpg':
                tint=m.node_tree.nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[2].default_value=(*color,1)
                m.node_tree.links.new(node.outputs['Color'],tint.inputs[1]);m.node_tree.links.new(tint.outputs[0],shader.inputs[socket])
            else:m.node_tree.links.new(node.outputs['Color'],shader.inputs[socket])
        if source=='rough_linen':
            image=bpy.data.images.load(str(ROOT/'web/house/assets'/source/'normal.jpg'),check_existing=True)
            image.colorspace_settings.name='Non-Color'
            node=m.node_tree.nodes.new('ShaderNodeTexImage');node.image=image
            m.node_tree.links.new(mapping.outputs[0],node.inputs['Vector'])
            normal=m.node_tree.nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.55
            m.node_tree.links.new(node.outputs['Color'],normal.inputs['Color']);m.node_tree.links.new(normal.outputs[0],shader.inputs['Normal'])
    return m

cloth=material('Upholstery',(1,.67,.38),'rough_linen')
pillowmat=material('Plain pillows',(1,.72,.44),'rough_linen')
seammat=material('Tailored seams',(.69,.45,.25),'rough_linen')
oak=material('Oak legs',(.70,.57,.39),'fine_grained_wood')

def metric_uv(o):
    layer=o.data.uv_layers.active or o.data.uv_layers.new(name='Fabric meters')
    # Project each face's dominant normal in meters, matching the runtime shared maps.
    for p in o.data.polygons:
        axis=max(range(3),key=lambda i:abs(p.normal[i]))
        coords=(1,2) if axis==0 else (0,2) if axis==1 else (0,1)
        for li in p.loop_indices:
            v=o.data.vertices[o.data.loops[li].vertex_index].co
            layer.data[li].uv=(v[coords[0]],v[coords[1]])

def finish(o,name,mat):
    o.name=name;o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    metric_uv(o);parts.append(o);return o

def cushion(name,dims,loc,roundness,mat,rotation=0):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc)
    o=bpy.context.object;o.dimensions=dims
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    b=o.modifiers.new('Soft sewn cushion radius','BEVEL');b.width=roundness;b.segments=5
    bpy.ops.object.modifier_apply(modifier=b.name)
    # Keep larger faces stable, soften edges without turning seat into a balloon.
    n=o.modifiers.new('Weighted upholstery normals','WEIGHTED_NORMAL');n.keep_sharp=True
    bpy.ops.object.modifier_apply(modifier=n.name)
    o.rotation_euler.x=rotation
    return finish(o,name,mat)

def pipe(name,points,radius,mat,cyclic=False):
    curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=3
    curve.bevel_depth=radius;curve.bevel_resolution=1
    s=curve.splines.new('POLY');s.points.add(len(points)-1)
    for b,p in zip(s.points,points):b.co=(*p,1)
    s.use_cyclic_u=cyclic
    o=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active=o;o.select_set(True)
    bpy.ops.object.convert(target='MESH');o.select_set(False)
    return finish(o,name,mat)

def rounded_ring(cx,cy,z,w,d,r):
    points=[]
    for x,y,start in [(cx+w/2-r,cy+d/2-r,0),(cx-w/2+r,cy+d/2-r,90),
                      (cx-w/2+r,cy-d/2+r,180),(cx+w/2-r,cy-d/2+r,270)]:
        for i in range(9):
            a=math.radians(start+i*90/8)
            points.append((x+math.cos(a)*r,y+math.sin(a)*r,z))
    return points

# Four round wood legs lift upholstery clear of floor, as in the real reference.
for x in [-.97,.97]:
    for y in [-.295,.28]:
        bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.052,depth=.215,location=(x,y,.1075))
        o=bpy.context.object
        bevel=o.modifiers.new('Oak edge radius','BEVEL');bevel.width=.006;bevel.segments=3
        bpy.ops.object.modifier_apply(modifier=bevel.name);finish(o,'Round oak leg',oak)

cushion('Upholstered foundation',(2.35,.81,.19),(0,-.025,.273),.073,cloth)
pipe('Base upholstered welt',rounded_ring(0,-.025,.257,2.345,.804,.072),.0018,seammat,True)
# Two seat cushions with a readable center split and gently rounded fronts.
for x in [-.51,.51]:
    cushion('Seat cushion',(.99,.619,.161),(x,-.105,.357),.069,cloth)
    pipe('Seat lower welt',rounded_ring(x,-.105,.325,.985,.614,.067),.00155,seammat,True)
# Angled back cushions create a stable support, not a huge antique rolled back.
for x in [-.535,.535]:
    cushion('Back cushion',(1.055,.179,.425),(x,.287,.623),.067,cloth,-.11)
    # Tailored side seams at the top/back, sparse enough not to read as stripes.
    pipe('Back top seam',[(x-.455,.326,.818),(x,.345,.830),(x+.455,.326,.818)],.00135,seammat)
for x in [-1.075,1.075]:
    cushion('Soft arm',(.246,.746,.336),(x,-.015,.511),.099,cloth)
    # Tiny structural seam follows front curve rather than outlining every edge.
    pipe('Arm tailored front seam',[(x-.071,-.376,.389),(x-.089,-.383,.492),(x-.071,-.373,.617),
                                   (x,-.368,.644),(x+.071,-.373,.617),(x+.089,-.383,.492),(x+.071,-.376,.389)],.0013,seammat)

def pillow(name,x,y,z,tilt,roll):
    # Two inflated cloth surfaces, thin joined hem, restrained asymmetric wrinkles.
    n=22;verts=[];faces=[];edges=[]
    for side in [-1,1]:
        for j in range(n+1):
            v=-1+2*j/n
            for i in range(n+1):
                u=-1+2*i/n
                px=.212*u*(1-.12*abs(v)**8)
                pz=.203*v*(1-.12*abs(u)**8)
                inner=max(0,(1-u*u)*(1-v*v))
                thickness=.009+.058*inner**.46
                wrinkle=.0035*math.sin(22*u+6*v)*math.exp(-((abs(v)-.79)/.16)**2)*inner
                sag=-.014*inner*(.7+u*.3)
                verts.append((px,side*(thickness+wrinkle),pz+sag))
    stride=n+1;surface=stride*stride
    for side in range(2):
        for j in range(n):
            for i in range(n):
                a=side*surface+j*stride+i
                f=(a,a+1,a+1+stride,a+stride)
                faces.append(f if side==0 else f[::-1])
    boundary=list(range(stride))+[j*stride+n for j in range(1,stride)]+list(range(n*stride+n-1,n*stride-1,-1))+[j*stride for j in range(n-1,0,-1)]
    for i,a in enumerate(boundary):
        b=boundary[(i+1)%len(boundary)];faces.append((a,b,b+surface,a+surface))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    o=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(o)
    o.location=(x,y,z);o.rotation_euler=(tilt,0,roll)
    finish(o,name,pillowmat)
    seam=[((verts[i][0]+verts[i+surface][0])/2,0,(verts[i][2]+verts[i+surface][2])/2) for i in boundary]
    hem=pipe(name+' soft hem',seam,.0016,seammat,True);hem.location=o.location;hem.rotation_euler=o.rotation_euler

pillow('Left relaxed pillow',-.71,.065,.617,-.19,-.14)
pillow('Right relaxed pillow',.72,.041,.610,-.23,.18)

# Pack source .blend for editing, but export no textures/materials: house shares CC0 maps.
bpy.ops.object.select_all(action='DESELECT')
for mat in [cloth,pillowmat,seammat,oak]:
    members=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.data.materials[0]==mat]
    bpy.ops.object.select_all(action='DESELECT')
    for o in members:o.select_set(True)
    bpy.context.view_layer.objects.active=members[0];bpy.ops.object.join()
    o=bpy.context.object;o.name=mat.name.replace(' ','_')
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
assets=[o for o in bpy.context.scene.objects if o.type=='MESH']
points=[o.matrix_world@v.co for o in assets for v in o.data.vertices]
lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
assert hi[0]-lo[0] <=2.4 and hi[1]-lo[1] <=.90 and hi[2]-lo[2]<.86
bpy.ops.object.select_all(action='SELECT');bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'sofa.blend'))
bpy.ops.export_scene.gltf(filepath=str(OUT/'sofa.glb'),export_format='GLB',export_materials='NONE',export_cameras=False,export_lights=False)
(OUT/'sofa.json').write_text(json.dumps({
    'geometry':'Original soft fabric sofa and two relaxed plain pillows. Adapted design/proportions, not manufacturer CAD.',
    'reference_url':'https://www.karimoku-case.com/furniture/n-s03/',
    'reference_dimensions_m':[1.815,.720,.670],'reference_seat_height_m':.4,
    'actual_blender_bounds_m':[lo,hi],'seat_top_m':.4375,
    'runtime_origin_m':[-1.8,0,.1],'runtime_yaw_radians':-math.pi/2,
    'runtime_material_sources':['https://polyhaven.com/a/rough_linen','https://polyhaven.com/a/fine_grained_wood'],
    'runtime_materials':'4 shared house materials; linen main/pillows/seams, oak legs; no embedded bitmaps',
    'vertices':sum(len(o.data.vertices) for o in assets),'triangles':sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in assets),
    'glb_bytes':(OUT/'sofa.glb').stat().st_size,'sha256':hashlib.sha256((OUT/'sofa.glb').read_bytes()).hexdigest()
},indent=2))

# Ignored diagnostic render, actual integration verified by root in the browser.
bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,-.001))
floor=bpy.context.object;floor.data.materials.append(material('Studio floor',(.23,.23,.23)))
world=bpy.data.worlds.new('Studio world');world.use_nodes=True;bpy.context.scene.world=world
world.node_tree.nodes['Background'].inputs[0].default_value=(.45,.45,.45,1)
world.node_tree.nodes['Background'].inputs[1].default_value=.35
for loc,power,size in [((-2,-3,4),300,3),((2,1,3),220,2)]:
    bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.size=size
    l.rotation_euler=(Vector((0,0,.4))-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(3.1,-4.3,2.25));cam=bpy.context.object
cam.rotation_euler=(Vector((0,0,.4))-cam.location).to_track_quat('-Z','Y').to_euler()
cam.data.type='ORTHO';cam.data.ortho_scale=3.2;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=32
scene.render.resolution_x=1100;scene.render.resolution_y=760;scene.render.resolution_percentage=100
scene.render.filepath=str(STUDIO/'sofa-render.png');bpy.ops.render.render(write_still=True)
print('SOFA_BUILT',json.dumps({'bounds':[lo,hi],'bytes':(OUT/'sofa.glb').stat().st_size}),flush=True)
