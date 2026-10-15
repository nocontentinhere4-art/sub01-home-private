"""Private Runpod Blender source: reuse real curved console/controller for wall mount.

The user's second supplied room photograph is reference only, never a texture.
Original display geometry is rigidly transformed; the held/input controller is untouched.
"""
import bpy,sys,math,json,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/real-media-console-source-r1/output')
OUT=Path('/workspace/sub01-home-private/reference-wall-console-r1/output');OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'media-console-side.blend'))
console=[];controller=[]
for o in list(bpy.context.scene.objects):
 if o.type!='MESH':continue
 names=[m.name for m in o.data.materials if m]
 if names==['controller']:controller.append(o)
 elif names and all(n.startswith('Console ')for n in names):console.append(o)
assert console and len(controller)==1
stand=[o for o in console if o.name=='Low circular console stand'];assert len(stand)==1
console=[o for o in console if o not in stand]
keep=console+controller
for o in list(bpy.context.scene.objects):
 if o not in keep:bpy.data.objects.remove(o,do_unlink=True)
# Freeze existing world meshes: source vertex coordinates then one rigid rotation.
def bake(o):
 w=o.matrix_world.copy();o.parent=None
 for v in o.data.vertices:v.co=w@v.co
 o.matrix_world.identity()
for o in keep:bake(o)
def bounds(objects):
 points=[v.co for o in objects for v in o.data.vertices]
 return Vector([min(v[i]for v in points)for i in range(3)]),Vector([max(v[i]for v in points)for i in range(3)])
lo,hi=bounds(console);pivot=(lo+hi)*.5;rotation=Matrix.Rotation(-math.pi/2,3,'Z')
# Broad white shell faces the room, like the supplied photograph, rather than its thin edge.
for o in console:
 for v in o.data.vertices:v.co=rotation@(v.co-pivot)
lo,hi=bounds(console);delta=Vector((-3.745,-.94,1.258))-Vector((lo.x,(lo.y+hi.y)/2,lo.z))
for o in console:
 for v in o.data.vertices:v.co+=delta
console_bounds=bounds(console)
# The separate 16cm display controller rotates upright; no held controller/source/scale change.
lo,hi=bounds(controller);pivot=(lo+hi)*.5;r=Matrix.Rotation(math.pi/2,3,'Y')
for o in controller:
 for v in o.data.vertices:v.co=r@(v.co-pivot)
lo,hi=bounds(controller);delta=Vector((-3.735,-.94,1.055))-Vector((lo.x,(lo.y+hi.y)/2,lo.z))
for o in controller:
 for v in o.data.vertices:v.co+=delta
controller_bounds=bounds(controller)
# Powder-coated steel bracket manufactured as a continuous folded backplate/tray.
mat=bpy.data.materials.new('Wall mount powder coated steel');mat.diffuse_color=(.019,.023,.029,1);mat.use_nodes=True
s=mat.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(.019,.023,.029,1);s.inputs['Roughness'].default_value=.34;s.inputs['Metallic'].default_value=.72
hardware=[]
def box(name,loc,dim,bevel=.001):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel:
  mod=o.modifiers.new('Manufactured folded edge radius','BEVEL');mod.width=bevel;mod.segments=3;bpy.ops.object.modifier_apply(modifier=mod.name)
 o.data.materials.append(mat)
 for f in o.data.polygons:f.use_smooth=True
 hardware.append(o);return o
# Actual TV wall plane X=-3.77; bracket rear contact is exact, without embedding source wall.
box('Console bracket wall backplate',(-3.7675,-.94,1.408),(.005,.15,.30))
box('Console bracket load bearing tray',(-3.6775,-.94,1.254),(.185,.23,.008))
for y in(-1.052,-.828):box('Console tray retention side lip',(-3.665,y,1.265),(.16,.006,.03))
# Controller cradle: wall backing plus a shelf under both grips, with a raised retention edge.
box('Controller dock backplate',(-3.7675,-.94,1.112),(.005,.15,.14))
box('Controller dock grip support',(-3.6875,-.94,1.051),(.165,.18,.008))
box('Controller dock front retaining lip',(-3.608,-.94,1.062),(.006,.18,.03))
# Countersunk wall-anchor heads and separate positive attachment documentation.
for z in(1.295,1.51,1.075,1.165):
 bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.004,depth=.0015,location=(-3.76425,-.94,z),rotation=(0,math.pi/2,0));o=bpy.context.object;o.name='Recessed wall anchor head';o.data.materials.append(mat);hardware.append(o)
# Recessed connection and short jumper are fully concealed behind the real shell.
box('Concealed recessed connection plate',(-3.7665,-.94,1.43),(.003,.07,.12),.001)
bpy.ops.mesh.primitive_cylinder_add(vertices=20,radius=.0022,depth=.019,location=(-3.7555,-.94,1.42),rotation=(0,math.pi/2,0));o=bpy.context.object;o.name='Concealed power jumper behind shell';o.data.materials.append(mat);hardware.append(o)
# Mirror the reference arrangement to the opposite side of this actual TV.
# This wall strip fits the complete shell; the other strip opens into a window.
for o in console+controller+hardware:o.location.y+=1.975
bpy.context.view_layer.update()
def world_bounds(objects):
 points=[o.matrix_world@v.co for o in objects for v in o.data.vertices]
 return [Vector([min(v[i]for v in points)for i in range(3)]),Vector([max(v[i]for v in points)for i in range(3)])]
console_bounds=world_bounds(console);controller_bounds=world_bounds(controller)
# Save meaningful unbatched authoring asset before exact material grouping.
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'wall-console.blend'))
groups={}
for o in console+controller+hardware:
 assert len(o.data.materials)==1
 groups.setdefault(o.data.materials[0].name,[]).append(o)
parts=[];mapping=[]
for index,(old,objects)in enumerate(sorted(groups.items())):
 bpy.ops.object.select_all(action='DESELECT')
 for o in objects:o.select_set(True)
 bpy.context.view_layer.objects.active=objects[0];bpy.ops.object.join();o=bpy.context.object;o.name=f'WCPart{index:02}';o.data.name=o.name;o.data.materials[0].name=f'WCM{index:02}';parts.append(o);mapping.append({'node':o.name,'material':f'WCM{index:02}','source_material':old})
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
out=OUT/'wall-console.glb';bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
report={'schema':'sub01.reference-wall-console-source.v1','sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'source_blend_sha256':hashlib.sha256((ROOT/'media-console-side.blend').read_bytes()).hexdigest(),'console_geometry':'Existing original curved console shell rigidly rotated; old circular floor stand omitted for wall bracket','controller_display_width_m':.16,'controller_held_source_changed':False,'native_imported':False,'gameplay_available':False,'actual_tv_screen_geometry_or_minecraft_changed':False,'existing_cabinet_changed':False,'reference_arrangement_mirrored_for_actual_wall_fit':True,'console_bounds_blender_m':[list(v)for v in console_bounds],'controller_bounds_blender_m':[list(v)for v in controller_bounds],'parts':mapping,'triangles':sum(sum(len(f.vertices)-2 for f in o.data.polygons)for o in parts),'wall_contact_x_m':-3.77,'attachment':'5mm folded steel wall backplate,8mm load-bearing tray,4anchors; separate controller dock','reference':'User supplied second minimalist wall-mounted console+TV photograph; reference only, not texture'}
(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
