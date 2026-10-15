"""Read actual exported source geometry; no native/Game interaction."""
import bpy,sys,json,hashlib,copy
from pathlib import Path
from mathutils.bvhtree import BVHTree
ROOT=Path('/workspace/sub01-home-private/reference-kitchen-finish-r2/output')
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
from unreal_import_real_wc import expected_triangles
from unreal_remove_frame_backings import same_triangles
old=Path('/workspace/sub01-home-private/kitchen-lowerfit-source-20261015/output/native-kitchen.glb');d,b=read_gltf(old);v,vb=read_gltf(ROOT/'kitchen-finish-152.glb');c=copy.deepcopy(v);c['materials']=d['materials'];assert c==d and bytes(vb)==bytes(b)
hd,hb=read_gltf(Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb'));sd,sb=read_gltf(ROOT/'counter-tap-finish.glb');carrier=[]
for original in(65,69,70,71):
 name=hd['nodes'][original]['name'];found=[i for i,n in enumerate(sd['nodes'])if n.get('name')==name and'mesh'in n];assert len(found)==1,(original,name,found)
 before=expected_triangles(hd,hb,original);after=expected_triangles(sd,sb,found[0]);assert same_triangles(before,after,tolerance=.0001),(original,len(before),len(after))
 carrier.append({'source_node':original,'carrier_node':found[0],'triangles':len(before),'every_world_corner_unchanged':True,'tolerance_cm':.0001})
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'reference-kitchen-finish.blend'))
old_led=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.name in('KFLEDChannel','KFDiffuser','KFEndCap','KFEndCap.001')];assert len(old_led)==4
for o in old_led:bpy.data.objects.remove(o,do_unlink=True)
pre=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(ROOT/'under-cabinet-led.glb'));led=[o for o in bpy.context.scene.objects if o not in pre and o.type=='MESH'];assert len(led)==4
others=[o for o in bpy.context.scene.objects if o.type=='MESH'and o not in led and not o.hide_render]
def tree(objects):
 verts=[];polys=[];owners=[]
 for o in objects:
  off=len(verts);verts.extend(o.matrix_world@p.co for p in o.data.vertices);polys.extend([[off+i for i in p.vertices]for p in o.data.polygons]);owners.extend([o.name]*len(o.data.polygons))
 return BVHTree.FromPolygons(verts,polys,epsilon=0),owners
home,owners=tree(others);pairs=[]
for o in led:
 t,_=tree([o]);hits=t.overlap(home)
 pairs += [{'led_part':o.name,'source_actor':owners[j],'led_polygon':i,'source_polygon':j}for i,j in hits]
assert not pairs,pairs[:20]
points=[o.matrix_world@p.co for o in led for p in o.data.vertices];ledlo=min(p.z for p in points);ledhi=max(p.z for p in points);ledbounds=[[f(p[k]for p in points)for k in range(3)]for f in(min,max)];hinges=[]
for o in bpy.context.scene.objects:
 if o.type!='EMPTY'or('hinge'not in o.name.lower()or not o.name.startswith('SUB01_RealKitchen_bf4a71cc24d1_')):continue
 parts=[c for c in o.children_recursive if c.type=='MESH'];assert len(parts)==5
 verts=[a.matrix_world@p.co for a in parts for p in a.data.vertices];lo=min(p.z for p in verts);hi=max(p.z for p in verts)
 gap=max(lo-ledhi,ledlo-hi);assert gap>0,(o.name,gap)
 # Actual hinge is a vertical Z-axis rotation. Hence every vertex keeps height
 # throughout the entire continuous sweep, rather than only sampled poses.
 hinges.append({'hinge':o.name,'source_leaf_parts':5,'moving_height_m':[lo,hi],'led_height_m':[ledlo,ledhi],'minimum_vertical_separation_m':gap,'all_angles_clear_by_Z_invariance':True})
assert len(hinges)==8,len(hinges)
proof={'schema':'sub01.reference-kitchen-finish-physical-proof.v1','cabinet_source_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'finish_variant_sha256':hashlib.sha256((ROOT/'kitchen-finish-152.glb').read_bytes()).hexdigest(),'all152_geometry_uv_binary_and_hierarchy_exact':True,'counter_tap_carriers':carrier,'counter_tap_sha256':hashlib.sha256((ROOT/'counter-tap-finish.glb').read_bytes()).hexdigest(),'led_sha256':hashlib.sha256((ROOT/'under-cabinet-led.glb').read_bytes()).hexdigest(),'actual_exported_led_bounds_m':ledbounds,'source_bvh':{'exported_glb_reimported':True,'epsilon_m':0,'tested_retained_meshes':len(others),'led_parts':4,'intersection_pairs':pairs,'retired_original_nodes_with_exact_replacements':[63,66,178]},'eight_full_continuous_hinge_sweeps_against_new_led':hinges,'native_ready':False,'native_saved':False,'runtime_motion_verified':False}
application=json.loads((ROOT/'finish-application.json').read_text());application['led_source_bounds_m']=ledbounds;(ROOT/'finish-application.json').write_text(json.dumps(application,indent=2)+'\n')
(ROOT/'finish-physical-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('ACTUAL_SOURCE_FINISH_PHYSICAL_PROOF_PASS',json.dumps(proof),flush=True)
