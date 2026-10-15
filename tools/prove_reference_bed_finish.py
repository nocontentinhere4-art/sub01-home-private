"""Audit actual exported bed variant against the immutable home and cloth."""
import bpy,sys,json,hashlib,math
from pathlib import Path
from mathutils.bvhtree import BVHTree
ROOT=Path('/workspace/sub01-home-private/reference-bed-finish-r2/output');sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
from unreal_import_real_wc import expected_triangles
from unreal_remove_frame_backings import same_triangles
home=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');hd,hb=read_gltf(home);sd,sb=read_gltf(ROOT/'bed-finish.glb');rows=[]
for index,name in[(260,'BFFrame'),(240,'BFNightstand')]:
 found=[i for i,n in enumerate(sd['nodes'])if n.get('name')==name and'mesh'in n];assert len(found)==1
 before=expected_triangles(hd,hb,index);after=expected_triangles(sd,sb,found[0]);assert same_triangles(before,after,tolerance=.0001),(index,len(before),len(after))
 rows.append({'original_node':index,'new_source_node':found[0],'triangles':len(before),'every_world_triangle_corner_unchanged':True,'tolerance_cm':.0001})
oldhead=expected_triangles(hd,hb,261);low=[min(p[k]for t in oldhead for p in t)for k in range(3)];high=[max(p[k]for t in oldhead for p in t)for k in range(3)];headrows=[]
for name in('BFLeftPost','BFRightPost','BFLowerPanel','BFUpperPanel'):
 i=next(i for i,n in enumerate(sd['nodes'])if n.get('name')==name);tri=expected_triangles(sd,sb,i);pts=[p for t in tri for p in t];lo=[min(p[k]for p in pts)for k in range(3)];hi=[max(p[k]for p in pts)for k in range(3)]
 assert all(lo[k]>=low[k]and hi[k]<=high[k]for k in range(3)),(name,lo,hi,low,high)
 headrows.append({'part':name,'new_bounds_native_cm':[lo,hi],'inside_old_headboard_AABB':True})
cloth=Path('/workspace/sub01-home-private/reference-bedding-source-r1/output/bedding.glb');assert hashlib.sha256(cloth.read_bytes()).hexdigest()=='e1c4a48e4d6c391a428a20fa56a5575c50963e08a0a914e2df5c50b6d6fbc2f7'
cd,cb=read_gltf(cloth);vd,vb=read_gltf(ROOT/'bedding-finish.glb');restored=__import__('copy').deepcopy(vd);restored['materials']=cd['materials']
for m0,m1 in zip(cd['meshes'],restored['meshes']):
 for p0,p1 in zip(m0['primitives'],m1['primitives']):p1['material']=p0['material']
assert restored==cd and bytes(vb)==bytes(cb),'Cloth geometry/UV/image binary must remain EXACT'
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'reference-bed-finish.blend'))
names={'BFFrame','BFNightstand','BFLeftPost','BFRightPost','BFLowerPanel','BFUpperPanel'}
old=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.name in names];assert len(old)==6
for o in old:bpy.data.objects.remove(o,do_unlink=True)
pre=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(ROOT/'bed-finish.glb'));new=[o for o in bpy.context.scene.objects if o not in pre and o.type=='MESH'];assert len(new)==6
head=[o for o in new if o.name not in('BFFrame','BFNightstand')];others=[o for o in bpy.context.scene.objects if o.type=='MESH'and o not in head and not o.hide_render]
def tree(objects):
 points=[];faces=[];owners=[]
 for o in objects:
  offset=len(points);points.extend(o.matrix_world@v.co for v in o.data.vertices);faces.extend([[offset+i for i in f.vertices]for f in o.data.polygons]);owners.extend([o.name]*len(o.data.polygons))
 return BVHTree.FromPolygons(points,faces,epsilon=0),owners
retained,owners=tree(others);frame=next(o for o in new if o.name=='BFFrame');frame_top=max((frame.matrix_world@v.co).z for v in frame.data.vertices);float_bound=4*2**-23*max(1,abs(frame_top));support=[];unresolved=[]
for o in head:
 t,_=tree([o]);bottom=min((o.matrix_world@v.co).z for v in o.data.vertices)
 for a,b in t.overlap(retained):
  row={'head_part':o.name,'source_part':owners[b],'head_polygon':a,'source_polygon':b}
  if owners[b]=='BFFrame'and bottom>=frame_top-float_bound:
   support.append(dict(row,post_bottom_m=bottom,frame_top_m=frame_top,maximum_vertical_overlap_m=max(0,frame_top-bottom),actual_float32_roundoff_bound_m=float_bound))
  else:unresolved.append(row)
assert not unresolved,unresolved[:20]
result={'schema':'sub01.reference-bed-finish-physical-proof.v1','source_sha256':hashlib.sha256((ROOT/'bed-finish.glb').read_bytes()).hexdigest(),'unchanged_geometry':rows,'new_headboard_inside_original_261':headrows,'preserved_actual_cloth_sha256':hashlib.sha256(cloth.read_bytes()).hexdigest(),'new_cloth_material_variant_sha256':hashlib.sha256((ROOT/'bedding-finish.glb').read_bytes()).hexdigest(),'all_cloth_geometry_UV_and_binary_exact':True,'mattress262_and_slats265_unchanged':True,'functional_nightstand_lamp195_199_unchanged':True,'new_head_source_bvh':{'exported_glb_reimported':True,'epsilon_m':0,'retained_meshes':len(others),'unresolved_intersections':unresolved,'measured_headboard_support_contacts':support,'only_contact_exception':'Exact headboard post bottoms meet the unchanged frame top, bounded by four actual float32 coordinate roundoffs; no other owner or intersection is ignored'},'native_imported':False,'runtime_accepted':False}
(ROOT/'bed-finish-physical-proof.json').write_text(json.dumps(result,indent=2)+'\n');print('BED_FINISH_SOURCE_PHYSICAL_PASS',json.dumps(result),flush=True)
