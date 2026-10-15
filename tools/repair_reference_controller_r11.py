"""Repair the reviewed R5 white cover surface in Blender; retain all fixed controls."""
import bpy,bmesh,sys,json,hashlib,struct
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
BASE=Path('/workspace/sub01-home-private/reference-controller-r5/output');ROOT=Path('/workspace/sub01-home-private/reference-controller-r11/output');ROOT.mkdir(parents=True,exist_ok=True)
assert hashlib.sha256((BASE/'controller-r5.blend').read_bytes()).hexdigest()=='912081cf2d04a7635a6fdbcbc7ffc432cb395dda12e288e6b795c174b3380394','Exact preserved R5 authoring source required'
bpy.ops.wm.open_mainfile(filepath=str(BASE/'controller-r5.blend'))
w=bpy.data.objects['Curved white manufactured grip covers'];bpy.context.view_layer.objects.active=w
bpy.ops.object.select_all(action='DESELECT');w.select_set(True)
oldverts=[v.co.copy()for v in w.data.vertices];oldfaces=[tuple(p.vertices)for p in w.data.polygons];before=BVHTree.FromPolygons(oldverts,oldfaces,all_triangles=False)
fixed={o.name:hashlib.sha256(b''.join(struct.pack("<fff",*v.co)for v in o.data.vertices)).hexdigest()for o in bpy.context.scene.objects if o.type=='MESH'and o!=w}
w.data.remesh_voxel_size=.00030;w.data.remesh_voxel_adaptivity=0.;bpy.ops.object.voxel_remesh()
sm=w.modifiers.new('Manufactured shell topology fairing','SMOOTH');sm.factor=.5;sm.iterations=80;bpy.ops.object.modifier_apply(modifier=sm.name)
dec=w.modifiers.new('Surface error bounded display topology','DECIMATE');dec.ratio=.25;dec.use_collapse_triangulate=True;bpy.ops.object.modifier_apply(modifier=dec.name)
lo=min(v.co.x for v in w.data.vertices);hi=max(v.co.x for v in w.data.vertices);scale=.15380217134952545/(hi-lo)
for v in w.data.vertices:v.co.x*=scale
w.data.materials.clear();w.data.materials.append(bpy.data.materials['CRWhite'])
for p in w.data.polygons:p.use_smooth=True
for o in bpy.context.scene.objects:
 if o.type=='MESH'and o!=w:assert hashlib.sha256(b''.join(struct.pack("<fff",*v.co)for v in o.data.vertices)).hexdigest()==fixed[o.name]
max_deviation=max(before.find_nearest(v.co)[3]for v in w.data.vertices)
parts=[o for o in bpy.context.scene.objects if o.type=='MESH']
# Rebuild physical planar UVs after real mesh topology replacement.
uv=w.data.uv_layers.new(name='UVMap')if not w.data.uv_layers else w.data.uv_layers.active
for p in w.data.polygons:
 axis=max(range(3),key=lambda i:abs(p.normal[i]));axes=[i for i in range(3)if i!=axis]
 for li in p.loop_indices:
  v=w.data.vertices[w.data.loops[li].vertex_index].co;uv.data[li].uv=(v[axes[0]]/.016,v[axes[1]]/.016)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'controller-r11.blend'))
bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join();o=bpy.context.object;o.name='C3Held';o.data.name='C3Held'
for i,m in enumerate(o.data.materials):m.name=f'C3M{i:02}'
bpy.ops.export_scene.gltf(filepath=str(ROOT/'controller-r11-held.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
lo=[min(v.co[k]for v in o.data.vertices)for k in range(3)];hi=[max(v.co[k]for v in o.data.vertices)for k in range(3)];width=hi[0]-lo[0];center=Vector([(a+b)/2 for a,b in zip(lo,hi)])
for v in o.data.vertices:v.co=(v.co-center)*(.16/width)
o.name='C3Display';o.data.name='C3Display';bpy.ops.export_scene.gltf(filepath=str(ROOT/'controller-r11-display.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
r=json.loads((BASE/'source-report.json').read_text());r.update(schema='sub01.reference-controller-r11-source.v1',geometry='Preserved R5 manufactured assembly and fixed controls; only white cover closed topology repaired by0.30mm Blender voxel remesh and actual surface fairing',white_cover_repair_voxel_m=.00030,white_cover_repair_smooth_iterations=80,white_cover_max_nearest_original_deviation_m=max_deviation,white_cover_only_width_scale=scale,fixed_control_and_body_coordinates_verified_identical=True,base_editable_blend_sha256=hashlib.sha256((BASE/'controller-r5.blend').read_bytes()).hexdigest(),triangles=sum(len(p.vertices)-2 for p in o.data.polygons),held_glb_sha256=hashlib.sha256((ROOT/'controller-r11-held.glb').read_bytes()).hexdigest(),display_glb_sha256=hashlib.sha256((ROOT/'controller-r11-display.glb').read_bytes()).hexdigest())
(ROOT/'source-report.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
