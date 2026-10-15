"""Compare every exported plant/pot triangle to its licensed source geometry."""
import bpy,json,hashlib,sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0,'/home/unreal/runtime-tools')
from unreal_remove_frame_backings import same_triangles
ROOT=Path('/workspace/sub01-home-private');OUT=ROOT/'reference-plants-ph-r1/output-r3';report=json.loads((OUT/'photo-plants-source.json').read_text());rows=[]
def triangles(o):
 bpy.context.view_layer.update();o.data.calc_loop_triangles();points=[o.matrix_world@v.co for v in o.data.vertices];return [[[float(a)*100 for a in points[i]]for i in t.vertices]for t in o.data.loop_triangles]
def tree(o):
 bpy.context.view_layer.update();return BVHTree.FromPolygons([o.matrix_world@v.co for v in o.data.vertices],[list(p.vertices)for p in o.data.polygons],epsilon=0)
for number,item in enumerate(report['plants']):
 bpy.ops.wm.read_factory_settings(use_empty=True);source=ROOT/'reference-plants-ph-r1/source'/item['species']/(item['species']+'_1k.gltf');bpy.ops.import_scene.gltf(filepath=str(source));original=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.name.split('.')[0].endswith('_'+item['authored_variant'])]
 for o in original:o.location+=Vector(item['source_translation_only_m'])
 expected=[triangles(o)for o in original]
 bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(ROOT/'reference-plants-r1/source/potted-areca-palm-aee9b13e.glb'));pots=[o for o in bpy.context.scene.objects if o.type=='MESH'and any(m and ('plant pot'in m.name.lower()or'potting soil'in m.name.lower())for m in o.data.materials)]
 assert len(pots)==3
 for o in pots:o.scale*=item['pot_uniform_scale'];o.location*=item['pot_uniform_scale']
 expected.extend(triangles(o)for o in pots)
 bpy.ops.wm.read_factory_settings(use_empty=True);path=OUT/(item['name']+'.glb');assert hashlib.sha256(path.read_bytes()).hexdigest()==item['prepared_sha256'];bpy.ops.import_scene.gltf(filepath=str(path));actual=sorted([o for o in bpy.context.scene.objects if o.type=='MESH'],key=lambda o:o.name);assert len(actual)==len(expected)
 for source_tri,obj in zip(expected,actual):assert same_triangles(source_tri,triangles(obj),tolerance=.0001),(number,obj.name,len(source_tri),len(triangles(obj)))
 soilparts=[o for o in actual[len(original):]if any(m and 'potting soil'in m.name.lower()for m in o.data.materials)]
 assert len(soilparts)==1
 soil_top=max((soilparts[0].matrix_world@v.co).z for v in soilparts[0].data.vertices)
 pot_top=max((o.matrix_world@v.co).z for o in actual[len(original):]for v in o.data.vertices)
 assert 0 < pot_top-soil_top < .03,(pot_top,soil_top)
 plants=actual[:len(original)];pot_surfaces=[o for o in actual[len(original):]if not any(m and 'potting soil'in m.name.lower()for m in o.data.materials)];crossings=[]
 for a in plants:
  for b in pot_surfaces:
   pairs=tree(a).overlap(tree(b))
   if pairs:crossings.append({'plant':a.name,'pot_surface':b.name,'polygon_pairs':len(pairs)})
 assert not crossings,crossings
 rows.append({'source':item['name'],'sha256':item['prepared_sha256'],'complete_positive_and_zero_source_triangle_count':sum(len(t)for t in expected),'all_original_plant_triangles_exact_after_translation':True,'all_original_pot_triangles_exact_after_uniform_scale':True,'tolerance_cm':.0001,'source_export_reimported':True,'source_leaf_or_stem_pot_wall_BVH_epsilon_m':0,'source_leaf_or_stem_pot_wall_intersections':crossings,'root_burial_depth_m':item['root_burial_depth_m'],'home_placement_not_tested':True})
proof={'schema':'sub01.reference-photo-plants-positive-source-proof.v1','plants':rows,'native_changes':False,'runtime_accepted':False};(OUT/'photo-plants-source-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print('PHOTO_PLANTS_SOURCE_PROOF_PASS',json.dumps(proof),flush=True)
