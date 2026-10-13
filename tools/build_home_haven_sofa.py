"""Licensed Innerscene CC0 modern sofa preparation; no CAD copying or new images."""
import bpy,json,hashlib,sys,math
from pathlib import Path
from mathutils import Vector
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'web/house/home.js').is_file())
SRC=ROOT/'web/house/assets/haven-sofa/source.glb'
RATIO=float(sys.argv[sys.argv.index('--ratio')+1]) if '--ratio' in sys.argv else .55
OUT=ROOT/'web/house/assets/haven-sofa' if '--study' not in sys.argv else ROOT/('out/sofa-reference/innerscene-haven/optimized' if RATIO<1 else 'out/sofa-reference/innerscene-haven/full')
OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(SRC))
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
points=[o.matrix_world@v.co for o in objects for v in o.data.vertices]
lo=Vector(tuple(min(v[i] for v in points) for i in range(3)));hi=Vector(tuple(max(v[i] for v in points) for i in range(3)))
seat=[]
for o in objects:
 if 'loose seat cushion' in o.name:
  seat += [(o.matrix_world@v.co).z-lo.z for v in o.data.vertices]
 for v in o.data.vertices:
  q=o.matrix_world@v.co;q.x-=(lo.x+hi.x)/2;q.y-=(lo.y+hi.y)/2;q.z-=lo.z;v.co=q
 o.matrix_world.identity()
 if RATIO<1 and 'Oatmeal' in o.data.materials[0].name:
  mod=o.modifiers.new('Measured browser LOD, only broad upholstery','DECIMATE');mod.ratio=RATIO;mod.use_collapse_triangulate=True
  bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=mod.name)
names={'Linen cord':'Haven_seams','Charcoal felt':'Haven_felt','Oatmeal':'Haven_linen','Smoked walnut':'Haven_legs'}
for prefix,name in names.items():
 members=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.data.materials and o.data.materials[0].name.startswith(prefix)]
 bpy.ops.object.select_all(action='DESELECT')
 for o in members:o.select_set(True)
 bpy.context.view_layer.objects.active=members[0];bpy.ops.object.join();members[0].name=name
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
points=[o.matrix_world@v.co for o in meshes for v in o.data.vertices];bounds=[[min(v[i] for v in points) for i in range(3)],[max(v[i] for v in points) for i in range(3)]]
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'sofa.blend'))
bpy.ops.object.select_all(action='DESELECT')
for o in meshes:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'sofa.glb'),use_selection=True,export_materials='NONE',export_cameras=False,export_lights=False)
triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in meshes)
metadata={'generator':'tools/build_home_haven_sofa.py','texture_preparation':'tools/prepare_home_haven_textures.py','source':'https://www.innerscene.com/tools/library/3d-parts/haven-224-oatmeal-two-seat-sofa-40262c27','author':'Innerscene','license':'CC0-1.0','license_url':'https://www.innerscene.com/tools/library/terms','source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'preparation':'Ground aligned and horizontally centred; source physical dimensions preserved; merged same-material objects into four groups. Optional upholstery-only collapse LOD preserves separate piping/feet/felt.','source_geometry':'Modeled modern fabric sofa; not photogrammetric scan.','ratio':RATIO,'triangles':triangles,'groups':len(meshes),'blender_bounds':bounds,'seat_top_m':max(seat),'seat_camera_delta_m':max(seat)-.4375,'runtime_origin':[-1.8,0,.1],'runtime_yaw':-math.pi/2,'collision_envelope':[.95,2.5],'glb_bytes':(OUT/'sofa.glb').stat().st_size,'sha256':hashlib.sha256((OUT/'sofa.glb').read_bytes()).hexdigest(),'embedded_images':False}
(OUT/'sofa.json').write_text(json.dumps(metadata,indent=2))
# Identical width and lighting diagnostic, not exported scene content.
scale=2.5/(bounds[1][0]-bounds[0][0])
for o in meshes:o.scale*=scale
bpy.ops.mesh.primitive_plane_add(size=20,location=(0,0,-.001));floor=bpy.context.object
m=bpy.data.materials.new('Studio');m.use_nodes=True;m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.2,.2,.2,1);floor.data.materials.append(m)
w=bpy.data.worlds.new('Controlled studio');w.use_nodes=True;bpy.context.scene.world=w;w.node_tree.nodes['Background'].inputs[0].default_value=(.45,.45,.45,1);w.node_tree.nodes['Background'].inputs[1].default_value=.35
for loc,power,size in [((-2,-3,4),300,3),((2,1,3),220,2)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.size=size;l.rotation_euler=(Vector((0,0,.4))-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(3.1,-4.3,2.25));c=bpy.context.object;c.rotation_euler=(Vector((0,0,.4))-c.location).to_track_quat('-Z','Y').to_euler();c.data.type='ORTHO';c.data.ortho_scale=3.2
s=bpy.context.scene;s.camera=c;s.render.engine='CYCLES';s.cycles.samples=48;s.render.resolution_x=1100;s.render.resolution_y=760;s.render.resolution_percentage=100;studio=ROOT/'out/sofa-reference/innerscene-haven';studio.mkdir(parents=True,exist_ok=True);s.render.filepath=str(studio/('installed-studio.png' if '--study' not in sys.argv else 'study-studio.png'));bpy.ops.render.render(write_still=True)
print('HAVEN_PREPARED',json.dumps(metadata),flush=True)
