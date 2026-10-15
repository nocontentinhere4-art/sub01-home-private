"""Runpod Blender authoring of CC0 media cabinet and reference-guided console.

No game payload or gameplay is included. The console shell is an original mesh
modeled against the official Sony product photograph, not a licensed Sony scan.
"""
import argparse,sys,json,hashlib,math
from pathlib import Path
import bpy
from mathutils import Vector
p=argparse.ArgumentParser();p.add_argument('--cabinet',type=Path,required=True);p.add_argument('--controller',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(a.cabinet));cabinet=[o for o in bpy.context.scene.objects if o.type=='MESH']
# The source is183x48x53cm. Its front is glTF+Z / Blender-Y.
anchor=bpy.data.objects.new('SUB01_MediaCabinetPlacement',None);bpy.context.scene.collection.objects.link(anchor);anchor.location=(-3.45,.05,.025);anchor.rotation_euler.z=math.pi/2
for o in cabinet:
 w=o.matrix_world.copy();o.parent=anchor;o.matrix_parent_inverse.identity();o.matrix_basis=w

def material(name,color,rough,metal=0):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True;s=m.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(*color,1);s.inputs['Roughness'].default_value=rough;s.inputs['Metallic'].default_value=metal;return m
white=material('Console white textured polymer',(.82,.83,.81),.32)
black=material('Console satin black polymer',(.012,.014,.017),.28)
vent=material('Console vent shadow',(.004,.005,.006),.78)
steel=material('Console stand satin steel',(.32,.34,.35),.24,.8)
blue=material('Console dim blue status trim',(.015,.10,.4),.26)
console=[]
def part(obj,mat):
 obj.data.materials.append(mat)
 for f in obj.data.polygons:f.use_smooth=True
 console.append(obj);return obj

def box(name,loc,dim,mat,bevel=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel:
  b=o.modifiers.new('Manufactured softened edge','BEVEL');b.width=bevel;b.segments=3;bpy.ops.object.modifier_apply(modifier=b.name)
 return part(o,mat)
# Approximate Slim envelope from product reference; exact manufacturing CAD is not claimed.
box('PS5 style black inner chassis',(0,0,.18),(.067,.195,.345),black,.009)
for side in (-1,1):
 for z0,z1,label in [(0.009,.172,'lower'),(.176,.358,'upper')]:
  verts=[];faces=[];nx,nz=24,24
  for k in range(nz+1):
   z=z0+(z1-z0)*k/nz;t=z/.358
   for j in range(nx+1):
    v=j/nx;y=-.112+v*.216
    # Swept concave profile, flared front lip and higher rear corner.
    x=side*(.034+.010*(abs(2*v-1)**2)+.010*t*t+.004*math.sin(t*math.pi))
    zz=z+.005*v*t
    verts.append((x,y,zz))
  for k in range(nz):
   for j in range(nx):
    q=k*(nx+1)+j;faces.append((q,q+1,q+nx+2,q+nx+1)if side>0 else(q+nx+1,q+nx+2,q+1,q))
  m=bpy.data.meshes.new('Curved removable cover');m.from_pydata(verts,[],faces);m.update();o=bpy.data.objects.new(f'Console {side} {label} curved cover',m);bpy.context.scene.collection.objects.link(o);part(o,white)
  bpy.context.view_layer.objects.active=o;s=o.modifiers.new('Polymer wall thickness','SOLIDIFY');s.thickness=.0022;bpy.ops.object.modifier_apply(modifier=s.name);b=o.modifiers.new('Cover edge radius','BEVEL');b.width=.0008;b.segments=2;bpy.ops.object.modifier_apply(modifier=b.name)
 for i in range(24):box('Rear cooling fin',(side*.036,.092,.025+i*.012),(.003,.008,.0015),vent,.0004)
 box('Status light recessed strip',(side*.035,-.099,.252),(.0008,.001,.135),blue,.0002)
box('Disc drive rounded volume',(.044,.004,.077),(.025,.17,.137),white,.01)
box('Disc drive slot',(.057,-.082,.076),(.0012,.003,.107),black,.0005)
for z in [.074,.108]:box('USB C port',(0,-.0985,z),(.0068,.0018,.0026),vent,.0008)
box('Power key',(0,-.099,.025),(.004,.0018,.006),black,.0008)
bpy.ops.mesh.primitive_cylinder_add(vertices=64,radius=.070,depth=.004,location=(0,0,.002));part(bpy.context.object,steel).name='Low circular console stand'
# Local furniture placement: top right, ventilated above the closed cabinet.
for o in console:
 w=o.matrix_world.copy();o.parent=anchor;o.matrix_parent_inverse.identity();o.matrix_basis=w;o.location+=Vector((.55,0,.535))
before={o.as_pointer()for o in bpy.context.scene.objects}
bpy.ops.import_scene.gltf(filepath=str(a.controller));controller=[]
for o in list(bpy.context.scene.objects):
 if o.as_pointer()in before or o.type!='MESH':continue
 if not o.data.materials or any('contact' in m.name.lower()for m in o.data.materials if m):bpy.data.objects.remove(o,do_unlink=True);continue
 controller.append(o)
assert controller,'Actual existing physical controller required'
pts=[o.matrix_world@Vector(v)for o in controller for v in o.bound_box];lo=Vector([min(p[i]for p in pts)for i in range(3)]);hi=Vector([max(p[i]for p in pts)for i in range(3)]);center=(lo+hi)*.5;scale=.16/max(hi.x-lo.x,hi.y-lo.y)
for o in controller:
 w=o.matrix_world.copy();o.parent=None
 for v in o.data.vertices:v.co=(w@v.co-center)*scale
 o.matrix_world.identity();pts=[v.co for v in o.data.vertices];bottom=min(v.z for v in pts);o.location=(-.42,-.04,.54-bottom);o.parent=anchor
outputs=cabinet+console+controller;bpy.ops.object.select_all(action='DESELECT')
for o in outputs:o.select_set(True)
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(a.output/'media-console.blend'));bpy.ops.export_scene.gltf(filepath=str(a.output/'media-console.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
report={'schema':'sub01.reference-media-console-source.v1','native_imported':False,'gameplay_available':False,'cabinet_source':'https://www.innerscene.com/tools/library/3d-parts/channel-180-oak-media-console-50ef2e72','cabinet_license':'CC0','console_reference':'https://direct.playstation.com/en-us/buy-consoles/playstation5-console-1-tb','console_geometry':'Original Blender curved shell authored against official reference; approximate dimensions, not scanned/CAD model','placement_gltf_m':[-3.45,.025,-.05],'controller_display_width_m':.16,'meshes':len(outputs),'triangles':sum(sum(len(f.vertices)-2 for f in o.data.polygons)for o in outputs),'files':{n:hashlib.sha256((a.output/n).read_bytes()).hexdigest()for n in ['media-console.glb','media-console.blend']}}
(a.output/'media-console.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
