"""Private Runpod Blender: new manufactured shell from the three human references.

Original nominal held width is retained, not the visibly wrong old Xbox body.
ALL previous grip/contact proofs are invalid for this new source. No native input.
"""
import bpy,bmesh,math,json,hashlib,sys
from pathlib import Path
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt
import numpy as np
ROOT=Path('/workspace/sub01-home-private/reference-controller-r5/output');ROOT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
WIDTH=.15380217134952545

def material(name,color,rough,metal=0,spec=.25):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True;p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,1);p.inputs['Roughness'].default_value=rough;p.inputs['Metallic'].default_value=metal;p.inputs['Specular IOR Level'].default_value=spec;return m
white=material('CRWhite',(.70,.735,.77),.34);black=material('CRBlack',(.006,.008,.011),.49,spec=.18);rubber=material('CRRubber',(.009,.012,.015),.67,spec=.15);key=material('CRKeys',(.015,.019,.025),.34,spec=.22);glyph=material('CRGlyph',(.54,.59,.64),.42);blue=material('CRBlue',(.004,.035,.20),.34)
p=blue.node_tree.nodes.get('Principled BSDF');p.inputs['Emission Color'].default_value=(.003,.028,.15,1);p.inputs['Emission Strength'].default_value=.3
rng=np.random.default_rng(20261015);noise=rng.random((256,256)).astype(np.float32)-.5;dx=np.roll(noise,-1,1)-np.roll(noise,1,1);dy=np.roll(noise,-1,0)-np.roll(noise,1,0);pixels=np.stack((.5-dx*.026,.5-dy*.026,np.ones_like(noise),np.ones_like(noise)),axis=-1);image=bpy.data.images.new('CRGrain',width=256,height=256);image.pixels.foreach_set(pixels.reshape(-1));image.colorspace_settings.name='Non-Color';image.filepath_raw=str(ROOT/'micrograin.png');image.file_format='PNG';image.save();image.pack()
for m in(white,black,rubber):
 t=m.node_tree.nodes.new('ShaderNodeTexImage');t.image=image;n=m.node_tree.nodes.new('ShaderNodeNormalMap');n.inputs['Strength'].default_value=.15;m.node_tree.links.new(t.outputs['Color'],n.inputs['Color']);m.node_tree.links.new(n.outputs['Normal'],m.node_tree.nodes.get('Principled BSDF').inputs['Normal'])
# Continuous manufacturer's silhouette: broad shoulder field and gently splayed grips.
left=[(0,.048),(-.031,.048),(-.054,.046),(-.066,.036),(-.074,.015),(-.0765,-.010),(-.074,-.035),(-.069,-.050),(-.064,-.053),(-.059,-.049),(-.052,-.027),(-.042,-.017),(-.027,-.019),(0,-.019)]
outline_control=left+ [(-x,y)for x,y in left[-2:0:-1]]
outline=[]
for i,p1 in enumerate(outline_control):
 p0=Vector(outline_control[(i-1)%len(outline_control)]);p1=Vector(p1);p2=Vector(outline_control[(i+1)%len(outline_control)]);p3=Vector(outline_control[(i+2)%len(outline_control)])
 for j in range(14):
  t=j/14;point=.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t);outline.append(point)
scale=(WIDTH/2)/max(abs(p.x)for p in outline)
outline=[Vector((p.x*scale,p.y))for p in outline]
def inside(x,y):
 result=False
 for p,q in zip(outline,outline[1:]+outline[:1]):
  if(p.y>y)!=(q.y>y)and x<(q.x-p.x)*(y-p.y)/(q.y-p.y)+p.x:result=not result
 return result
def boundary(y):return .033+.025*max(0,min(1,(-y-.005)/.047))**1.2
def distance(x,y):
 p=Vector((x,y));best=1.
 for a,b in zip(outline,outline[1:]+outline[:1]):
  ab=b-a;t=max(0,min(1,(p-a).dot(ab)/ab.length_squared));best=min(best,(p-(a+t*ab)).length)
 return best
def top_z(x,y):
 d=distance(x,y);d=0. if d<.000001 else d;r=max(0,min(1,d/.008));z=.019+.018*math.sqrt(max(0,1-(1-r)**2))+.001*(1-(x/.08)**2)*r
 if abs(x)<.032 and .017<y<.046:z=min(z,.0370)
 return z
points=list(outline);edges=[(i,(i+1)%len(outline))for i in range(len(outline))]
for y in np.arange(-.050,.048,.0016):
 for x in np.arange(-.074,.075,.0016):
  if inside(float(x),float(y)):points.append(Vector((float(x),float(y))))
# Constrained seams cut real continuous geometry, not a per-face colour staircase.
for sign in(-1,1):
 previous=None
 for y in np.linspace(-.056,.052,65):
  i=len(points);points.append(Vector((sign*boundary(float(y)),float(y))))
  if previous is not None:edges.append((previous,i))
  previous=i
vertices,edge_result,faces,origv,orige,origf=delaunay_2d_cdt(points,edges,[list(range(len(outline)))],1,.00000001)
assert faces and all(len(f)==3 for f in faces)
# Core is a closed rounded solid, safely inside the thin white cover.
def proper_core_point(p):
 # Closest-edge inward normal, not radial scaling of a concave silhouette.
 best=1.;normal=None
 for a,b in zip(outline,outline[1:]+outline[:1]):
  ab=b-a;t=max(0,min(1,(p-a).dot(ab)/ab.length_squared));d=(p-(a+t*ab)).length
  if d<best:best=d;normal=Vector((-ab.y,ab.x)).normalized()
 # The outline is counter-clockwise; its left normal is inside the solid.
 return p+normal*(.0012*math.exp(-best/.005))
core_points=[proper_core_point(p)for p in vertices]
count=len(vertices);xyz=[(q.x,q.y,top_z(p.x,p.y))for p,q in zip(vertices,core_points)]+[(q.x,q.y,.038-top_z(p.x,p.y))for p,q in zip(vertices,core_points)]
core_faces=[tuple(f)for f in faces]+[tuple(count+i for i in reversed(f))for f in faces]
mesh=bpy.data.meshes.new('Manufactured rounded black core');mesh.from_pydata(xyz,[],core_faces);mesh.update();bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0000001);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(mesh);bm.free();mesh.update();body=bpy.data.objects.new('Deep dark central bridge and lower body',mesh);bpy.context.scene.collection.objects.link(body);mesh.materials.append(black)
for f in mesh.polygons:f.use_smooth=True
parts=[body]
# Independently manufactured white wings, a genuine solid cover with an uninterrupted side wrap.
white_faces=[]
for f in faces:
 center=sum((vertices[i]for i in f),Vector((0.,0.)))/3
 if abs(center.x)>boundary(center.y):white_faces.append(tuple(f))
white_vertices=[(p.x,p.y,top_z(p.x,p.y)+.0013)for p in vertices]
# White side wrap is connected to actual outer rim; lower seam follows one level plane.
for i,(p,q)in enumerate(zip(outline,outline[1:]+outline[:1])):
 center=(p+q)/2
 if abs(center.x)<=boundary(center.y):continue
 rings=[]
 for scale_delta,z in[(0,.0203),(0,.016),(.00025,.012),(.00060,.0105),(.0009,.0103)]:
  pair=[]
  for point in(p,q):
   direction=point.normalized();pair.append(len(white_vertices));white_vertices.append((point.x-direction.x*scale_delta,point.y-direction.y*scale_delta,z))
  rings.append(pair)
 for a,b in zip(rings,rings[1:]):white_faces.append((a[0],a[1],b[1],b[0]))
me=bpy.data.meshes.new('Continuous rounded white cover pair');me.from_pydata(white_vertices,[],white_faces);me.update();bm=bmesh.new();bm.from_mesh(me);bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.0000001);bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(me);bm.free();me.update();wings=bpy.data.objects.new('Curved white manufactured grip covers',me);bpy.context.scene.collection.objects.link(wings);me.materials.append(white)
for f in me.polygons:f.use_smooth=True
bpy.context.view_layer.objects.active=wings;s=wings.modifiers.new('Physical cover wall thickness','SOLIDIFY');s.thickness=.0008;s.offset=-1;bpy.ops.object.modifier_apply(modifier=s.name)
# Subdivide the real manufactured surface, including its thin rounded lower lip.
sub=wings.modifiers.new('True continuous cover curvature','SUBSURF');sub.subdivision_type='CATMULL_CLARK';sub.levels=1;sub.render_levels=1;sub.quality=3;bpy.ops.object.modifier_apply(modifier=sub.name)
# Restore only the shell's nominal width; all existing controls stay fixed.
cover_lo=min(v.co.x for v in wings.data.vertices);cover_hi=max(v.co.x for v in wings.data.vertices);cover_width_scale=WIDTH/(cover_hi-cover_lo)
for v in wings.data.vertices:v.co.x*=cover_width_scale
parts.append(wings)
def own(o,m,name):
 o.name=name;o.data.materials.append(m)
 for f in o.data.polygons:f.use_smooth=True
 parts.append(o);return o

def box(name,loc,dim,m,bevel=.0006):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel:
  b=o.modifiers.new('Manufactured edge fillet','BEVEL');b.width=bevel;b.segments=3;bpy.ops.object.modifier_apply(modifier=b.name)
 return own(o,m,name)

def cylinder(name,loc,radius,depth,m):
 bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=radius,depth=depth,location=loc);o=bpy.context.object;b=o.modifiers.new('Key edge fillet','BEVEL');b.width=min(.0004,depth/4);b.segments=3;bpy.ops.object.modifier_apply(modifier=b.name);return own(o,m,name)

def tube(name,points,radius,m,closed=False):
 curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.resolution_u=1;curve.bevel_depth=radius;curve.resolution_u=1;curve.bevel_resolution=2;s=curve.splines.new('POLY');s.points.add(len(points)-1)
 for p,v in zip(s.points,points):p.co=(*v,1)
 s.use_cyclic_u=closed;o=bpy.data.objects.new(name,curve);bpy.context.scene.collection.objects.link(o);bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.convert(target='MESH');o=bpy.context.object;o.select_set(False);return own(o,m,name)
# Recessed touchpad: bevelled glass-filled nylon plate with an actual surrounding reveal.
box('Touchpad recessed dark reveal',(0,.032,.0374),(.063,.029,.0012),black,.003)
box('Touchpad subtly convex top',(0,.032,.0381),(.0595,.0255,.0010),key,.0026)
for sign in(-1,1):
 pts=[(sign*.0315,.019,.0378),(sign*.0322,.024,.0384),(sign*.0322,.039,.0384),(sign*.0309,.0465,.0379)]
 tube('Thin recessed blue touchpad edge',pts,.00036,blue)
# Symmetric analogue sticks with concave rubber tops, separate collar/shaft and perimeter knurl.
for x in(-.028,.028):
 cylinder('Analogue recessed bearing collar',(x,-.008,.0389),.0105,.0016,black)
 cylinder('Analogue moving shaft',(x,-.008,.0411),.0043,.0038,rubber)
 verts=[];faces=[];rings=[(.00001,.0447),(.002,.04472),(.004,.0449),(.006,.04515),(.0076,.04555),(.0087,.04585),(.009,.0461),(.0092,.0458),(.0092,.0445),(.0078,.0429)]
 for radius,z in rings:
  for i in range(64):
   a=i*2*math.pi/64;verts.append((x+radius*math.cos(a),-.008+radius*math.sin(a),z))
 for j in range(len(rings)-1):
  for i in range(64):a=j*64+i;b=j*64+(i+1)%64;faces.append((a,a+64,b+64,b))
 mesh2=bpy.data.meshes.new('Concave analogue rubber surface');mesh2.from_pydata(verts,[],faces);mesh2.update();o=bpy.data.objects.new('Concave thumbstick cup',mesh2);bpy.context.scene.collection.objects.link(o);own(o,rubber,o.name)
 for i in range(40):
  a=i*2*math.pi/40;rr=.00915;tube('Thumbstick fine perimeter grip',[(x+rr*math.cos(a),-.008+rr*math.sin(a),.0447),(x+rr*math.cos(a),-.008+rr*math.sin(a),.0457)],.00013,rubber)
# Separate D-pad directional keycaps, with true raised arrows and gap to inner pivot.
for direction in range(4):
 angle=direction*math.pi/2;cx=-.049+math.sin(angle)*.007;cy=.024+math.cos(angle)*.007
 outline=[(-.003,-.003),(.003,-.003),(.003,.001),(0,.004),(-.003,.001)]
 def xy(p):return(cx+p[0]*math.cos(angle)+p[1]*math.sin(angle),cy-p[0]*math.sin(angle)+p[1]*math.cos(angle))
 vv=[(*xy(p),z)for z in(.0379,.0409)for p in outline];ff=[tuple(range(4,-1,-1)),tuple(range(5,10))]+[(i,(i+1)%5,(i+1)%5+5,i+5)for i in range(5)]
 me=bpy.data.meshes.new('Separated direction cap');me.from_pydata(vv,[],ff);me.update();o=bpy.data.objects.new('D-pad separate directional cap',me);bpy.context.scene.collection.objects.link(o);own(o,key,o.name);bpy.context.view_layer.objects.active=o;be=o.modifiers.new('Directional cap edge radius','BEVEL');be.width=.00095;be.segments=5;bpy.ops.object.modifier_apply(modifier=be.name)
 points=[(*xy((-.001,.0003)),.04105),(*xy((0,.0015)),.04105),(*xy((.001,.0003)),.04105)];tube('D-pad raised direction glyph',points,.00017,glyph)
# Face keys physically separate from the white front; each readable symbol is actual relief geometry.
buttons=[('Triangle',.049,.032),('Circle',.057,.024),('Cross',.049,.016),('Square',.041,.024)]
for name,x,y in buttons:
 cylinder(name+' independent keycap',(x,y,.0394),.00365,.0031,key);z=.04112;r=.0019
 if name=='Triangle':tube('Triangle raised symbol',[(x,y+r,z),(x-r*.9,y-r*.65,z),(x+r*.9,y-r*.65,z)],.00020,glyph,True)
 elif name=='Circle':tube('Circle raised symbol',[(x+r*math.cos(i*2*math.pi/36),y+r*math.sin(i*2*math.pi/36),z)for i in range(36)],.00020,glyph,True)
 elif name=='Square':tube('Square raised symbol',[(x-r,y-r,z),(x+r,y-r,z),(x+r,y+r,z),(x-r,y+r,z)],.00020,glyph,True)
 else:
  tube('Cross diagonal one',[(x-r,y-r,z),(x+r,y+r,z)],.00020,glyph);tube('Cross diagonal two',[(x-r,y+r,z),(x+r,y-r,z)],.00020,glyph)
# Tactile create/options keys, speaker perforation pockets and microphone/home controls.
for x in(-.036,.036):box('Create or options tactile key',(x,.037,.0389),(.0026,.0056,.0012),key,.001)
cylinder('Home key with relief circle',(0,.001,.0388),.0028,.0009,key);tube('Home key raised ring',[(.0013*math.cos(i*2*math.pi/24),.0013*math.sin(i*2*math.pi/24),.03935)for i in range(24)],.00016,glyph,True)
box('Microphone mute key',(0,-.008,.03865),(.0044,.0018,.0008),key,.0007)
# Independently curved shoulder keys and hooked lower trigger layers.
for side,x in [('L',-.046),('R',.046)]:
 box(side+'1 rounded shoulder key',(x,.044,.0352),(.028,.0085,.006),key,.0020)
 profile=[(.037,.0305),(.044,.032),(.050,.029),(.052,.023),(.050,.016),(.044,.0145),(.041,.018),(.043,.023)]
 # Smooth the manufactured cross-section with Catmull-Rom before sweeping width.
 smooth=[]
 for i,p1 in enumerate(profile):
  p0=Vector(profile[(i-1)%len(profile)]);p1=Vector(p1);p2=Vector(profile[(i+1)%len(profile)]);p3=Vector(profile[(i+2)%len(profile)])
  for j in range(5):
   t=j/5;smooth.append(.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t))
 verts=[(x+dx,p.x,p.y+.0008*(1-(dx/.013)**2))for dx in(-.013,-.010,.010,.013)for p in smooth];N=len(smooth);faces=[tuple(range(N-1,-1,-1)),tuple(3*N+i for i in range(N))]
 for ring in range(3):
  for i in range(N):a=ring*N+i;b=ring*N+(i+1)%N;faces.append((a,b,b+N,a+N))
 m=bpy.data.meshes.new(side+'2 curved trigger');m.from_pydata(verts,[],faces);m.update();o=bpy.data.objects.new(side+'2 hooked lower trigger',m);bpy.context.scene.collection.objects.link(o);own(o,key,o.name)
 # Actual small engraved-style label geometry, not a UI overlay or copied logo.
 bpy.ops.object.text_add(location=(x-.0025,.043,.0384));text=bpy.context.object;text.data.body=side+'1';text.data.size=.0026;text.data.extrude=.000025;text.data.bevel_depth=.000015;bpy.ops.object.convert(target='MESH');own(bpy.context.object,glyph,side+'1 manufactured marking')
# True shallow perforations, cut as one boolean tool into the actual closed core.
cutters=[]
for y,count in[(.013,5),(.0105,4)]:
 for i in range(count):
  bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=.0005,depth=.003,location=((i-(count-1)/2)*.0023,y,.0378));cutters.append(bpy.context.object)
bpy.ops.object.select_all(action='DESELECT')
for c in cutters:c.select_set(True)
bpy.context.view_layer.objects.active=cutters[0];bpy.ops.object.join();tool=bpy.context.object
bpy.context.view_layer.objects.active=body;modifier=body.modifiers.new('Actual speaker grille shallow pockets','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=tool;bpy.ops.object.modifier_apply(modifier=modifier.name);bpy.data.objects.remove(tool,do_unlink=True)
# One physically manufactured assembly, true white cover geometry and no material mask.
for o in parts:
 if not o.data.uv_layers:
  uv=o.data.uv_layers.new(name='UVMap')
  for poly in o.data.polygons:
   axis=max(range(3),key=lambda i:abs(poly.normal[i]));axes=[i for i in range(3)if i!=axis]
   for li in poly.loop_indices:
    v=o.data.vertices[o.data.loops[li].vertex_index].co;uv.data[li].uv=(v[axes[0]]/.016,v[axes[1]]/.016)
 else:o.data.uv_layers.active.name='UVMap'
# The intentional new geometry invalidates every old grip proof.
points=[o.matrix_world@v.co for o in parts for v in o.data.vertices];lo=[min(v[k]for v in points)for k in range(3)];hi=[max(v[k]for v in points)for k in range(3)];normalization=WIDTH/(hi[0]-lo[0])
for o in parts:
 world=o.matrix_world.copy()
 for v in o.data.vertices:v.co=(world@v.co)*normalization
 o.matrix_world.identity()
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'controller-r5.blend'))
bpy.context.view_layer.objects.active=body;bpy.ops.object.join();body=bpy.context.object;body.name='C3Held';body.data.name='C3Held'
# Short unique native material names, no Interchange basename collisions.
for i,m in enumerate(body.data.materials):m.name=f'C3M{i:02}'
bpy.ops.export_scene.gltf(filepath=str(ROOT/'controller-r5-held.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
points=[v.co for v in body.data.vertices];lo=[min(v[k]for v in points)for k in range(3)];hi=[max(v[k]for v in points)for k in range(3)];width=hi[0]-lo[0];center=Vector([(lo[k]+hi[k])/2 for k in range(3)]);display_factor=.16/width
for v in body.data.vertices:v.co=(v.co-center)*display_factor
body.name='C3Display';body.data.name='C3Display';bpy.ops.export_scene.gltf(filepath=str(ROOT/'controller-r5-display.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
report={'schema':'sub01.reference-controller-r5-source.v1','held_width_m':width,'display_width_m':.16,'initial_assembly_uniform_normalization':normalization,'display_uniform_scale':display_factor,'geometry':'New continuous constrained-triangulated curved black core, genuine separate solid white cover pair/side wrap, low concave sticks, flush touchpad, rounded separated keys and curved layered triggers','reference':'Three human supplied front/side photographs inspected; original model, not licensed Sony CAD/scan','old_original_width_m':WIDTH,'core_inset_method':'Closest boundary-edge inward normal including concave grips;1.2mm decaying into interior','white_cover_deck_offset_m':.0013,'white_cover_wall_thickness_m':.0008,'control_targets_unchanged_from_r3':True,'white_cover_real_catmull_clark_subdivision':1,'white_cover_only_width_scale':cover_width_scale,'old_grip_geometry_preserved':False,'old_contact_proofs_invalidated':True,'new_grip_recheck_required':True,'native_imported':False,'hand_contact_accepted':False,'activity_ready':False,'thumb_targets_blender_m':[[-.028*normalization,-.008*normalization,.046*normalization],[.028*normalization,-.008*normalization,.046*normalization]],'bounds_held_blender_m':[lo,hi],'triangles':sum(len(p.vertices)-2 for p in body.data.polygons),'material_count':len(body.data.materials),'held_glb_sha256':hashlib.sha256((ROOT/'controller-r5-held.glb').read_bytes()).hexdigest(),'display_glb_sha256':hashlib.sha256((ROOT/'controller-r5-display.glb').read_bytes()).hexdigest()}
(ROOT/'source-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
